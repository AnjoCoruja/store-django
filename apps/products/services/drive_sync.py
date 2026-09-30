"""Sincroniza pastas/fotos do Google Drive com Categorias e Produtos."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from django.db import transaction

from apps.products.filename_parser import detect_season, parse_filename
from apps.products.models import Category, Product

from .google_drive import (
    DriveCatalogClient,
    DriveFolder,
    PublicDriveClient,
    extract_folder_id,
    get_catalog_client,
    public_image_url,
)

logger = logging.getLogger("apps.products")


@dataclass
class SyncReport:
    categories_created: int = 0
    products_created: int = 0
    products_updated: int = 0
    products_unpublished: int = 0
    descriptions_generated: int = 0
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def as_dict(self):
        return self.__dict__.copy()


class DriveSync:
    def __init__(self, client: DriveCatalogClient | PublicDriveClient, describer=None, regenerate_descriptions=False,
                 unpublish_missing=False):
        self.client = client
        self.describer = describer
        self.regenerate = regenerate_descriptions
        self.unpublish_missing = unpublish_missing
        self.report = SyncReport()
        self.seen_file_ids: set[str] = set()

    # ---------- categorias ----------
    def _get_category(self, name: str, parent: Category | None, season: str) -> Category:
        from django.db.models import Q

        season_label = "Verão" if season == "verao" else "Inverno"
        category = (
            Category.objects.filter(parent=parent)
            .filter(Q(name__iexact=name) | Q(name__iexact=f"{name} ({season_label})"))
            .filter(Q(line=season) | Q(line=""))
            .first()
        )
        if category is None:
            # nomes são únicos no banco: se já existir em outro lugar, diferencia pela estação
            unique_name = name
            if Category.objects.filter(name__iexact=name).exists():
                unique_name = f"{name} ({season_label})"
            category, created = Category.objects.get_or_create(
                name=unique_name, defaults={"parent": parent, "line": season}
            )
            if created:
                self.report.categories_created += 1
        if not category.line:
            category.line = season
            category.save(update_fields=["line", "updated_at"])
        return category

    # ---------- produtos ----------
    def _sync_images(self, folder: DriveFolder, category: Category, season: str):
        seen_names = set()
        for image in folder.images:
            key = image.name.strip().lower()
            if key in seen_names:
                self.report.skipped.append(f"{folder.name}/{image.name}: foto repetida (mesmo nome)")
                continue
            seen_names.add(key)
            parsed = parse_filename(image.name)
            if not parsed.is_valid:
                self.report.skipped.append(
                    f"{folder.name}/{image.name}: nome fora do padrão 'Nome, Cor, Tamanhos, Preço'"
                )
                continue
            self.seen_file_ids.add(image.id)
            try:
                self._upsert_product(image, parsed, category, season)
            except Exception as exc:  # não deixa uma foto derrubar a sincronização inteira
                logger.exception("Falha ao sincronizar %s", image.name)
                self.report.errors.append(f"{image.name}: {exc}")

    def _upsert_product(self, image, parsed, category, season):
        product = Product.objects.filter(drive_file_id=image.id).first()
        created = product is None
        if created:
            product = Product(drive_file_id=image.id, is_published=True, is_active=True)
        product.name = parsed.name[:200]
        product.category = category
        product.line = season
        product.color = parsed.color
        product.size_range = parsed.size_range
        product.price = parsed.price
        product.wholesale_price_6 = parsed.wholesale_price_6
        product.wholesale_price_24 = parsed.wholesale_price_24
        product.wholesale_price = parsed.wholesale_price_6
        product.image_url = public_image_url(image.id)
        if created:
            product.stock = 999  # estoque controlado pela loja; ajuste no admin se quiser

        if self.describer and (created or self.regenerate or not product.description):
            try:
                product.description = self.describer.describe(
                    image_bytes=self.client.download_bytes(image.id),
                    mime_type=image.mime_type,
                    name=parsed.name,
                    season=season,
                    category=category.name,
                    color=parsed.color,
                    sizes=parsed.size_range,
                )
                self.report.descriptions_generated += 1
            except Exception as exc:
                logger.warning("Gemini falhou para %s: %s", image.name, exc)
                self.report.errors.append(f"descrição de {image.name}: {exc}")
        if not product.description:
            product.description = _fallback_description(parsed, season)

        product.save()
        if created:
            self.report.products_created += 1
        else:
            self.report.products_updated += 1

    # ---------- árvore ----------
    def _walk(self, folder: DriveFolder, parent: Category, season: str):
        self._sync_images(folder, parent, season)
        for child in folder.children:
            sub = self._get_category(child.name.strip(), parent, season)
            self._walk(child, sub, season)

    @transaction.atomic
    def run(self, root: DriveFolder) -> SyncReport:
        for season_folder in root.children:
            season = detect_season(season_folder.name)
            if season is None:
                self.report.skipped.append(
                    f"pasta '{season_folder.name}': o nome precisa conter Verão ou Inverno"
                )
                continue
            if season_folder.images:
                self.report.skipped.append(
                    f"{len(season_folder.images)} foto(s) soltas em '{season_folder.name}': "
                    "coloque dentro de uma pasta de categoria"
                )
            for cat_folder in season_folder.children:
                category = self._get_category(cat_folder.name.strip(), None, season)
                self._walk(cat_folder, category, season)

        if self.unpublish_missing:
            self.report.products_unpublished = (
                Product.objects.exclude(drive_file_id__isnull=True)
                .exclude(drive_file_id__in=self.seen_file_ids)
                .filter(is_published=True)
                .update(is_published=False)
            )
        return self.report


def _fallback_description(parsed, season):
    estacao = "os dias quentes" if season == "verao" else "os dias frios"
    partes = [f"{parsed.name} da Red Blue Line, ideal para {estacao}."]
    if parsed.color:
        partes.append(f"Cores: {parsed.color}.")
    if parsed.size_range:
        partes.append(f"Tamanhos: {parsed.size_range}.")
    return " ".join(partes)


def run_drive_sync(root_folder_id, use_ai=True, regenerate=False, unpublish_missing=False,
                   client=None, describer=None) -> SyncReport:
    client = client or get_catalog_client()
    root_folder_id = extract_folder_id(root_folder_id)
    if use_ai and describer is None:
        from .ai_descriptions import GeminiNotConfigured, ProductDescriber

        try:
            describer = ProductDescriber()
        except GeminiNotConfigured as exc:
            logger.warning("%s Usando descrição padrão.", exc)
            describer = None
    tree = client.get_tree(root_folder_id, "raiz")
    return DriveSync(client, describer, regenerate, unpublish_missing).run(tree)
