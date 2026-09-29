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


@pytest.mark.django_db
class TestSeasonTabs:
    def _setup(self):
        parent = CategoryFactory(name="Feminino")
        praia = CategoryFactory(name="Moda Praia", parent=parent)
        jaquetas = CategoryFactory(name="Jaquetas", parent=parent, line="inverno")
        legging = CategoryFactory(name="Leggings", parent=parent)  # sem linha: detecta pelos produtos
        Product.objects.create(name="Biquini", price="40.00", category=praia, line="verao", is_published=True)
        Product.objects.create(name="Puffer", price="250.00", category=jaquetas, line="inverno", is_published=True)
        Product.objects.create(name="Legging UV", price="60.00", category=legging, line="verao", is_published=True)
        Product.objects.create(name="Legging Térmica", price="80.00", category=legging, line="inverno", is_published=True)
        return parent, praia, jaquetas, legging

    def test_parent_page_has_tabs_and_subcategories(self, client):
        parent, praia, jaquetas, legging = self._setup()
        resp = client.get(f"/categorias/{parent.slug}/")
        assert resp.status_code == 200
        tabs = {t["code"]: t for t in resp.context["tabs"]}
        assert [s.name for s in tabs["verao"]["subcategories"]] == ["Leggings", "Moda Praia"]
        assert [s.name for s in tabs["inverno"]["subcategories"]] == ["Jaquetas", "Leggings"]
        assert tabs["verao"]["product_count"] == 2
        assert tabs["inverno"]["product_count"] == 2
        content = resp.content.decode()
        assert 'data-tab="verao"' in content and 'data-tab="inverno"' in content
        # produtos de subcategorias aparecem na categoria pai
        assert "Biquini" in content and "Puffer" in content

    def test_linha_query_selects_tab(self, client):
        parent, *_ = self._setup()
        resp = client.get(f"/categorias/{parent.slug}/?linha=inverno")
        assert resp.context["active_line"] == "inverno"
        resp = client.get(f"/categorias/{parent.slug}/?linha=xyz")
        assert resp.context["active_line"] == "verao"

    def test_defaults_to_inverno_when_only_winter(self, client):
        cat = CategoryFactory(name="Casacos")
        Product.objects.create(name="Casaco", price="100.00", category=cat, line="inverno", is_published=True)
        resp = client.get(f"/categorias/{cat.slug}/")
        assert resp.context["active_line"] == "inverno"

    def test_home_lists_only_top_level(self, client):
        parent, praia, *_ = self._setup()
        resp = client.get("/")
        names = [c.name for c in resp.context["categories"]]
        assert "Feminino" in names and "Moda Praia" not in names

    def test_category_str_and_cycle_validation(self):
        from django.core.exceptions import ValidationError
        parent = CategoryFactory(name="A")
        child = CategoryFactory(name="B", parent=parent)
        assert str(child) == "A › B"
        parent.parent = child
        with pytest.raises(ValidationError):
            parent.clean()
        parent.parent = parent
        with pytest.raises(ValidationError):
            parent.clean()


@pytest.mark.django_db
class TestAddToCartButton:
    def test_js_args_are_valid(self, client):
        cat = CategoryFactory()
        Product.objects.create(
            name="Camisa", price="50.00", stock=1, category=cat, line="verao",
            wholesale_price_6="45.00", is_published=True,
        )
        for url in ["/", "/produtos/", f"/categorias/{cat.slug}/", "/produtos/camisa/"]:
            content = client.get(url).content.decode()
            assert "'Camisa', 50.00, 'verao', 45.00, null)" in content, url
