import pytest

from django.test import TestCase

from apps.products.models import Product

from tests.factories import CategoryFactory

# Create your tests here.


@pytest.mark.django_db
class TestAboutPage:
    def test_about_page_renders(self, client):
        response = client.get("/sobre/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "Red Blue Line" in content
        assert "Rua Tiers, 355" in content
        assert "Box 55" in content

    def test_footer_has_store_data(self, client):
        response = client.get("/")
        content = response.content.decode()
        assert "Shopping Tiers" in content
        assert "Brás" in content


@pytest.mark.django_db
class TestProductLine:
    def test_catalog_shows_line_filter(self, client, db):
        category = CategoryFactory()
        Product.objects.create(
            name="Camisa UV", price="50.00", stock=10, category=category,
            line="verao", is_published=True,
        )
        Product.objects.create(
            name="Jaqueta", price="200.00", stock=5, category=category,
            line="inverno", is_published=True,
        )
        response = client.get("/produtos/")
        content = response.content.decode()
        assert 'data-line="verao"' in content
        assert 'data-line="inverno"' in content
