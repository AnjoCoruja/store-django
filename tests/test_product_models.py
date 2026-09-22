import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.products.models import Category, Product, ProductImage
from tests.factories import CategoryFactory, ProductFactory

pytestmark = pytest.mark.django_db


class TestCategory:
    def test_slug_generated_from_name(self):
        cat = Category.objects.create(name="Camisetas Oversized")
        assert cat.slug == "camisetas-oversized"

    def test_slug_collision_gets_suffix(self):
        Category.objects.create(name="Camisetas")
        cat2 = Category.objects.create(name="CAMISETAS")
        assert cat2.slug == "camisetas-2"

    def test_name_is_unique(self):
        CategoryFactory(name="Calças")
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Category.objects.create(name="Calças")


class TestProduct:
    def test_slug_generated_and_unique(self):
        p1 = ProductFactory(name="Camisa Azul")
        p2 = ProductFactory(name="Camisa Azul")
        assert p1.slug == "camisa-azul"
        assert p2.slug == "camisa-azul-2"

    def test_price_is_decimal_not_float(self):
        p = ProductFactory(price="79.90")
        p.refresh_from_db()
        assert str(p.price) == "79.90"
        assert p.price.__class__.__name__ == "Decimal"

    def test_negative_price_rejected_by_check_constraint(self):
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                ProductFactory(price="-1.00")

    def test_negative_stock_rejected(self):
        with pytest.raises((IntegrityError, ValidationError)):
            p = ProductFactory.build(stock=-5)
            p.full_clean()

    def test_category_delete_protected(self):
        cat = CategoryFactory()
        ProductFactory(category=cat)
        with pytest.raises(Exception):
            cat.delete()
        assert Product.objects.filter(category=cat).exists()

    def test_published_category_index_queryset(self):
        ProductFactory.create_batch(3, is_published=True)
        ProductFactory.create_batch(2, is_published=False)
        assert Product.objects.filter(is_published=True).count() == 3


class TestProductImage:
    def test_only_one_primary_image(self):
        product = ProductFactory()
        img1 = ProductImage.objects.create(product=product, is_primary=True)
        img2 = ProductImage.objects.create(product=product, is_primary=True)
        img1.refresh_from_db()
        img2.refresh_from_db()
        assert img2.is_primary is True
        assert img1.is_primary is False

    def test_images_ordered_primary_first(self):
        product = ProductFactory()
        ProductImage.objects.create(product=product, is_primary=False, sort_order=0)
        primary = ProductImage.objects.create(product=product, is_primary=True)
        assert product.images.first() == primary
