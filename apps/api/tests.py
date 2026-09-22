"""Tests for the public read-only API v1."""
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.products.models import Category, Product, ProductImage


@pytest.fixture
def category(db):
    return Category.objects.create(name="Eletrônicos", is_active=True)


@pytest.fixture
def inactive_category(db):
    return Category.objects.create(name="Arquivada", is_active=False)


@pytest.fixture
def product(db, category):
    return Product.objects.create(
        name="Teclado Mecânico",
        description="Switch azul",
        price=Decimal("199.90"),
        wholesale_price=Decimal("149.90"),
        stock=10,
        category=category,
        is_published=True,
    )


@pytest.mark.django_db
class TestCategoryAPI:
    def test_list_categories(self, client, category):
        url = reverse("api:category-list")
        response = client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["results"][0]["slug"] == category.slug

    def test_inactive_category_not_listed(self, client, inactive_category):
        url = reverse("api:category-list")
        response = client.get(url)
        assert response.json()["count"] == 0

    def test_retrieve_category_by_slug(self, client, category):
        url = reverse("api:category-detail", kwargs={"slug": category.slug})
        response = client.get(url)
        assert response.status_code == 200
        assert response.json()["name"] == "Eletrônicos"

    def test_product_count_only_published(self, client, category, product):
        Product.objects.create(
            name="Rascunho",
            price=Decimal("10.00"),
            stock=1,
            category=category,
            is_published=False,
        )
        url = reverse("api:category-detail", kwargs={"slug": category.slug})
        response = client.get(url)
        assert response.json()["product_count"] == 1

    def test_category_is_read_only(self, client, category):
        url = reverse("api:category-list")
        response = client.post(url, data={"name": "X"})
        assert response.status_code == 405


@pytest.mark.django_db
class TestProductAPI:
    def test_list_products(self, client, product):
        url = reverse("api:product-list")
        response = client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["results"][0]["slug"] == product.slug

    def test_unpublished_product_hidden(self, client, category):
        Product.objects.create(
            name="Oculto",
            price=Decimal("5.00"),
            stock=0,
            category=category,
            is_published=False,
        )
        url = reverse("api:product-list")
        response = client.get(url)
        assert response.json()["count"] == 0

    def test_retrieve_product_by_slug(self, client, product):
        url = reverse("api:product-detail", kwargs={"slug": product.slug})
        response = client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Teclado Mecânico"
        assert data["price"] == "199.90"  # Decimal as string, no float
        assert data["category"]["slug"] == product.category.slug

    def test_price_is_not_float(self, client, product):
        url = reverse("api:product-detail", kwargs={"slug": product.slug})
        data = client.get(url).json()
        assert isinstance(data["price"], str)

    def test_filter_by_category(self, client, product, db):
        other = Category.objects.create(name="Móveis", is_active=True)
        Product.objects.create(
            name="Cadeira",
            price=Decimal("300.00"),
            stock=2,
            category=other,
            is_published=True,
        )
        url = reverse("api:product-list")
        response = client.get(url, {"category": other.slug})
        data = response.json()
        assert data["count"] == 1
        assert data["results"][0]["name"] == "Cadeira"

    def test_search_by_name(self, client, product):
        url = reverse("api:product-list")
        response = client.get(url, {"q": "teclado"})
        assert response.json()["count"] == 1

    def test_search_no_match(self, client, product):
        url = reverse("api:product-list")
        response = client.get(url, {"q": "inexistente"})
        assert response.json()["count"] == 0

    def test_pagination(self, client, category, monkeypatch):
        from rest_framework.pagination import PageNumberPagination

        monkeypatch.setattr(PageNumberPagination, "page_size", 5)
        for i in range(7):
            Product.objects.create(
                name=f"Produto {i}",
                price=Decimal("1.00"),
                stock=1,
                category=category,
                is_published=True,
            )
        url = reverse("api:product-list")
        response = client.get(url)
        data = response.json()
        assert data["count"] == 7
        assert len(data["results"]) == 5
        assert data["next"] is not None

    def test_images_in_detail(self, client, product, tmp_path, settings):
        settings.MEDIA_ROOT = tmp_path
        from django.core.files.uploadedfile import SimpleUploadedFile

        img = SimpleUploadedFile(
            "foto.jpg", b"\xff\xd8\xff" + b"0" * 100, content_type="image/jpeg"
        )
        ProductImage.objects.create(
            product=product, image=img, alt_text="Foto", is_primary=True
        )
        url = reverse("api:product-detail", kwargs={"slug": product.slug})
        data = client.get(url).json()
        assert len(data["images"]) == 1
        assert data["images"][0]["alt_text"] == "Foto"
        assert data["images"][0]["is_primary"] is True

    def test_product_is_read_only(self, client, product):
        url = reverse("api:product-list")
        response = client.post(url, data={"name": "X"})
        assert response.status_code == 405
        delete = client.delete(
            reverse("api:product-detail", kwargs={"slug": product.slug})
        )
        assert delete.status_code == 405
