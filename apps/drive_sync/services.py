"""Google Drive -> Django product sync (replaces the former n8n workflow).

Folder layout (DRIVE_ROOT_FOLDER_ID):
    <root>/<Categoria>/<Nome - Cor - Tamanhos - Preço ...>.jpg
    Images placed directly in <root> go to category "Geral".
    Sub-folders inside a category folder inherit that category.

Behaviour:
- New photo      -> product created, image downloaded, AI caption, published.
- Renamed photo  -> product data updated (name/color/sizes/prices/category).
- Replaced photo -> image re-downloaded and caption regenerated.
- Removed photo  -> product unpublished (soft; nothing is deleted).
- Unchanged      -> skipped (no download, no AI call).
Products without a price are created unpublished for manual review.
"""
import io
import logging
from dataclasses import dataclass, field

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import ContentFile
from django.db import transaction
from PIL import Image

from apps.audit.models import AuditLog
from apps.products.models import (
    ALLOWED_IMAGE_EXTENSIONS,
    MAX_IMAGE_SIZE_BYTES,
    Category,
    Product,
    ProductImage,
)

from .client import FOLDER_MIME, GoogleDriveClient
from .describer import generate_description
from .parser import detect_line, parse_filename

logger = logging.getLogger("apps.drive_sync")

ACTOR_ID = "drive-sync"
DEFAULT_CATEGORY = "Geral"


@dataclass
class SyncReport:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    unpublished: int = 0
    errors: list = field(default_factory=list)

    def __str__(self):
        return (
            f"criados={self.created} atualizados={self.updated} "
            f"sem_alteracao={self.unchanged} despublicados={self.unpublished} "
            f"erros={len(self.errors)}"
        )


def _is_image(item):
    ext = item["name"].rsplit(".", 1)[-1].lower() if "." in item["name"] else ""
    return item.get("mimeType", "").startswith("image/") and ext in ALLOWED_IMAGE_EXTENSIONS


def _iter_images(client, folder_id, category_name=None):
    for item in client.list_children(folder_id):
        if item.get("mimeType") == FOLDER_MIME:
            yield from _iter_images(client, item["id"], category_name or item["name"].strip())
        elif _is_image(item):
            yield category_name or DEFAULT_CATEGORY, item


def _audit(action, product, old_value=None, new_value=None):
    AuditLog.objects.create(
        actor_type=AuditLog.ActorType.AGENT,
        actor_id=ACTOR_ID,
        action=action,
        resource="product",
        resource_id=str(product.pk),
        old_value=old_value,
        new_value=new_value,
    )


def _validate_image(data):
    if len(data) > MAX_IMAGE_SIZE_BYTES:
        raise ValueError("imagem excede 5 MB")
    try:
        Image.open(io.BytesIO(data)).verify()
    except Exception as exc:
        raise ValueError(f"arquivo não é uma imagem válida ({exc})") from exc


def _sync_file(client, category_name, item, describer):
    """Returns 'created', 'updated' or 'unchanged'."""
    file_id, filename = item["id"], item["name"]
    content_hash = item.get("md5Checksum") or item.get("modifiedTime", "")
    product = Product.objects.select_related("category").filter(drive_file_id=file_id).first()

    if (
        product is not None
        and product.drive_md5 == content_hash
        and product.drive_file_name == filename
        and product.category.name == category_name
    ):
        return "unchanged"

    parsed = parse_filename(filename)
    image_changed = product is None or product.drive_md5 != content_hash
    image_bytes = None
    if image_changed:
        image_bytes = client.download(file_id)
        _validate_image(image_bytes)

    category, _ = Category.objects.get_or_create(name=category_name)
    created = product is None
    old_value = None if created else {
        "name": product.name,
        "price": str(product.price),
        "category": product.category.name,
        "drive_file_name": product.drive_file_name,
    }

    with transaction.atomic():
        if created:
            product = Product(drive_file_id=file_id, is_active=True)
        product.name = parsed.name
        product.category = category
        product.line = detect_line(category_name, filename)
        product.color = parsed.color
        product.size_range = parsed.size_range
        if parsed.price is not None:
            product.price = parsed.price
        elif created:
            product.price = 0
        product.wholesale_price = parsed.wholesale_price_6
        product.wholesale_price_6 = parsed.wholesale_price_6
        product.wholesale_price_24 = parsed.wholesale_price_24
        product.drive_file_name = filename
        product.drive_md5 = content_hash
        product.image_url = ""
        if created:
            product.is_published = product.price > 0
        if image_changed:
            product.description = describer(
                parsed, category_name, image_bytes, item.get("mimeType", "image/jpeg")
            )
        product.save()

        if image_changed:
            for old in product.images.filter(is_primary=True):
                old.image.delete(save=False)
                old.delete()
            ProductImage.objects.create(
                product=product,
                image=ContentFile(image_bytes, name=filename),
                alt_text=parsed.name[:200],
                is_primary=True,
            )

    _audit(
        "create" if created else "update",
        product,
        old_value=old_value,
        new_value={
            "name": product.name,
            "price": str(product.price),
            "category": category.name,
            "drive_file_name": filename,
            "image_changed": image_changed,
        },
    )
    return "created" if created else "updated"


def sync_drive(client=None, describer=generate_description, root_folder_id=None):
    root_folder_id = root_folder_id or settings.DRIVE_ROOT_FOLDER_ID
    if not root_folder_id:
        raise ImproperlyConfigured("Defina DRIVE_ROOT_FOLDER_ID.")
    client = client or GoogleDriveClient.from_settings()
    report = SyncReport()

    # Listing is done up front: if the Drive API fails we abort before
    # unpublishing anything.
    items = list(_iter_images(client, root_folder_id))
    seen = set()
    for category_name, item in items:
        seen.add(item["id"])
        try:
            result = _sync_file(client, category_name, item, describer)
        except Exception as exc:
            logger.exception("Erro ao sincronizar %s", item.get("name"))
            report.errors.append(f"{item.get('name')}: {exc}")
            continue
        setattr(report, result, getattr(report, result) + 1)

    removed = Product.objects.filter(drive_file_id__isnull=False, is_published=True).exclude(
        drive_file_id__in=seen
    )
    for product in removed:
        product.is_published = False
        product.save(update_fields=["is_published", "updated_at"])
        _audit("unpublish", product, old_value={"is_published": True},
               new_value={"is_published": False, "reason": "removido do Drive"})
        report.unpublished += 1

    logger.info("Sync Drive: %s", report)
    return report
