import pytest
from django.test import Client
from django.urls import reverse

from tests.factories import CategoryFactory, ProductFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return Client()


class TestHome:
    def test_home_responds_200(self, client):
        response = client.get(reverse("website:home"))
        assert response.status_code == 200
        assert b"<title>" in response.content

    def test_home_shows_published_products_only(self, client):
        ProductFactory(name="Produto Visível", is_published=True)
        ProductFactory(name="Produto Oculto", is_published=False)
        response = client.get(reverse("website:home"))
        assert "Produto Visível" in response.content.decode()
        assert "Produto Oculto" not in response.content.decode()


class TestProductList:
    def test_catalog_responds_200(self, client):
        assert client.get(reverse("website:product_list")).status_code == 200

    def test_search_filters_by_name(self, client):
        ProductFactory(name="Camisa Azul")
        ProductFactory(name="Calça Preta")
        response = client.get(reverse("website:product_list"), {"q": "Camisa"})
        assert "Camisa Azul" in response.content.decode()
        assert "Calça Preta" not in response.content.decode()

    def test_search_no_results_shows_empty_state(self, client):
        response = client.get(reverse("website:product_list"), {"q": "xyzinexistente"})
        assert "Nenhum produto disponível no momento.".encode() in response.content


class TestProductDetail:
    def test_detail_responds_200(self, client):
        product = ProductFactory()
        response = client.get(
            reverse("website:product_detail", kwargs={"slug": product.slug})
        )
        assert response.status_code == 200
        assert product.name.encode() in response.content

    def test_unpublished_product_returns_404(self, client):
        product = ProductFactory(is_published=False)
        response = client.get(
            reverse("website:product_detail", kwargs={"slug": product.slug})
        )
        assert response.status_code == 404

    def test_inactive_product_returns_404(self, client):
        product = ProductFactory(is_active=False)
        response = client.get(
            reverse("website:product_detail", kwargs={"slug": product.slug})
        )
        assert response.status_code == 404


class TestCategoryDetail:
    def test_category_responds_with_products(self, client):
        category = CategoryFactory(name="Camisetas")
        product = ProductFactory(category=category, name="Camisa Verde")
        response = client.get(
            reverse("website:category_detail", kwargs={"slug": category.slug})
        )
        assert response.status_code == 200
        assert "Camisa Verde" in response.content.decode()

    def test_inactive_category_returns_404(self, client):
        category = CategoryFactory(is_active=False)
        response = client.get(
            reverse("website:category_detail", kwargs={"slug": category.slug})
        )
        assert response.status_code == 404


class TestSeo:
    def test_canonical_and_description_present(self, client):
        response = client.get(reverse("website:home"))
        assert b'rel="canonical"' in response.content
        assert b'name="description"' in response.content
        assert b'property="og:title"' in response.content

    def test_robots_txt(self, client):
        response = client.get("/robots.txt")
        assert response.status_code == 200
        assert b"Disallow: /admin/" in response.content
