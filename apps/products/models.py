import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models
from django.utils.text import slugify

MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_IMAGE_EXTENSIONS = ["jpg", "jpeg", "png", "webp", "gif"]


def validate_image_size(file):
    if file.size > MAX_IMAGE_SIZE_BYTES:
        raise ValidationError("A imagem excede o tamanho máximo de 5 MB.")


def product_image_upload_path(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower()
    return f"products/{instance.product_id}/{uuid.uuid4().hex}.{ext}"


def category_image_upload_path(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower()
    return f"categories/{uuid.uuid4().hex}.{ext}"


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Category(TimeStampedModel):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, db_index=True)
    description = models.TextField(blank=True, default="")
    image = models.ImageField(
        upload_to=category_image_upload_path,
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(ALLOWED_IMAGE_EXTENSIONS),
            validate_image_size,
        ],
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._generate_unique_slug()
        super().save(*args, **kwargs)

    def _generate_unique_slug(self):
        base = slugify(self.name) or "category"
        slug = base
        counter = 2
        qs = Category.objects.all()
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        while qs.filter(slug=slug).exists():
            slug = f"{base}-{counter}"
            counter += 1
        return slug


class Product(TimeStampedModel):
    class Line(models.TextChoices):
        VERAO = "verao", "Verão / Calor (Red Line)"
        INVERNO = "inverno", "Inverno / Frio (Blue Line)"

    name = models.CharField(max_length=200)
    line = models.CharField(
        max_length=10,
        choices=Line.choices,
        default=Line.VERAO,
        db_index=True,
        verbose_name="Linha",
    )
    slug = models.SlugField(max_length=220, unique=True, db_index=True)
    description = models.TextField(blank=True, default="")
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    wholesale_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    # Campos de sincronizacao via Google Drive (Red Blue Line)
    color = models.CharField(max_length=60, blank=True, default="", verbose_name="Cor")
    size_range = models.CharField(
        max_length=60, blank=True, default="", verbose_name="Tamanhos"
    )
    wholesale_price_6 = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="Atacado 6+ peças",
    )
    wholesale_price_24 = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="Caixa 24+ peças",
    )
    drive_file_id = models.CharField(
        max_length=128,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="ID do arquivo no Google Drive",
    )
    image_url = models.URLField(blank=True, default="", verbose_name="URL da imagem (Drive)")
    stock = models.PositiveIntegerField(default=0)
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
    )
    is_active = models.BooleanField(default=True)
    is_published = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_published", "category"], name="product_pub_cat_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(price__gte=0), name="product_price_gte_zero"
            ),
            models.CheckConstraint(
                condition=models.Q(stock__gte=0), name="product_stock_gte_zero"
            ),
            models.CheckConstraint(
                condition=models.Q(wholesale_price__isnull=True)
                | models.Q(wholesale_price__gte=0),
                name="product_wholesale_price_gte_zero",
            ),
        ]

    _SIZE_ORDER = ["PP", "P", "M", "G", "GG", "XG", "G1", "G2", "G3", "G4"]

    def available_sizes(self):
        """Lista de tamanhos selecionáveis a partir do size_range."""
        if not self.size_range:
            return []
        s = self.size_range.strip()
        start = end = s
        for sep in (" ao ", " a ", "-", "–"):
            if sep in s:
                start, _, end = s.partition(sep)
                start, end = start.strip(), end.strip()
                break
        else:
            return [s]
        try:
            start_n, end_n = int(start), int(end)
            if start_n <= end_n and (end_n - start_n) <= 30:
                return [f"{n:02d}" for n in range(start_n, end_n + 1, 2)]
        except (ValueError, TypeError):
            pass
        def idx(x):
            try:
                return self._SIZE_ORDER.index(x.upper())
            except ValueError:
                return None
        i, j = idx(start), idx(end)
        if i is not None and j is not None and i <= j:
            return self._SIZE_ORDER[i:j + 1]
        return [start, end] if start != end else [start]

    def available_colors(self):
        """Lista de cores a partir do campo color (separadas por vírgula)."""
        if not self.color:
            return []
        return [c.strip() for c in self.color.split(",") if c.strip()]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._generate_unique_slug()
        super().save(*args, **kwargs)

    def _generate_unique_slug(self):
        base = slugify(self.name) or "product"
        slug = base
        counter = 2
        qs = Product.objects.all()
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        while qs.filter(slug=slug).exists():
            slug = f"{base}-{counter}"
            counter += 1
        return slug


class ProductImage(TimeStampedModel):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="images"
    )
    image = models.ImageField(
        upload_to=product_image_upload_path,
        validators=[
            FileExtensionValidator(ALLOWED_IMAGE_EXTENSIONS),
            validate_image_size,
        ],
    )
    alt_text = models.CharField(max_length=200, blank=True, default="")
    is_primary = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-is_primary", "sort_order", "created_at"]

    def __str__(self):
        return f"Image #{self.pk} of {self.product_id}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_primary:
            # Enforce a single primary image per product.
            ProductImage.objects.filter(product=self.product, is_primary=True).exclude(
                pk=self.pk
            ).update(is_primary=False)
