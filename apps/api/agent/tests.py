"""Tests for the agent API security layer (auth, throttling, audit)."""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.authtoken.models import Token

from apps.audit.models import AuditLog
from apps.products.models import Category, Product

User = get_user_model()


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def category(db):
    return Category.objects.create(name="Eletrônicos", is_active=True)


@pytest.fixture
def product(db, category):
    return Product.objects.create(
        name="Teclado",
        price=Decimal("199.90"),
        stock=5,
        category=category,
        is_published=True,
    )


@pytest.fixture
def agent_user(db):
    return User.objects.create_user(
        username="agent-n8n", password="x", is_staff=True
    )


@pytest.fixture
def agent_token(agent_user):
    return Token.objects.create(user=agent_user)


@pytest.fixture
def agent_client(client, agent_token):
    client.defaults["HTTP_AUTHORIZATION"] = f"Token {agent_token.key}"
    return client


def agent_url(name, **kwargs):
    return reverse(f"agent:{name}", kwargs=kwargs)


@pytest.mark.django_db
class TestAgentAuth:
    def test_no_token_rejected(self, client):
        response = client.get(agent_url("agent-product-list"))
        assert response.status_code in (401, 403)

    def test_invalid_token_rejected(self, client):
        response = client.get(
            agent_url("agent-product-list"),
            HTTP_AUTHORIZATION="Token invalido",
        )
        assert response.status_code in (401, 403)

    def test_valid_token_accepted(self, agent_client, product):
        response = agent_client.get(agent_url("agent-product-list"))
        assert response.status_code == 200

    def test_non_staff_user_rejected(self, client, db):
        user = User.objects.create_user(username="comum", password="x")
        token = Token.objects.create(user=user)
        response = client.get(
            agent_url("agent-product-list"),
            HTTP_AUTHORIZATION=f"Token {token.key}",
        )
        assert response.status_code == 403

    def test_inactive_user_rejected(self, client, db):
        user = User.objects.create_user(
            username="desligado", password="x", is_staff=True, is_active=False
        )
        token = Token.objects.create(user=user)
        response = client.get(
            agent_url("agent-product-list"),
            HTTP_AUTHORIZATION=f"Token {token.key}",
        )
        assert response.status_code in (401, 403)


@pytest.mark.django_db
class TestAgentProductWrite:
    def test_create_product(self, agent_client, category):
        response = agent_client.post(
            agent_url("agent-product-list"),
            data={
                "name": "Mouse Gamer",
                "price": "99.90",
                "stock": 3,
                "category": category.pk,
                "is_published": False,
                "is_active": True,
            },
        )
        assert response.status_code == 201, response.json()
        product = Product.objects.get(name="Mouse Gamer")
        assert product.slug  # auto-generated, not client-supplied

    def test_create_is_audited(self, agent_client, category):
        agent_client.post(
            agent_url("agent-product-list"),
            data={
                "name": "Mouse Gamer",
                "price": "99.90",
                "stock": 3,
                "category": category.pk,
            },
        )
        log = AuditLog.objects.get(action="create", resource="product")
        assert log.actor_type == "agent"
        assert log.actor_id == "agent-n8n"
        assert log.new_value["name"] == "Mouse Gamer"
        assert "key" not in str(log.new_value).lower()

    def test_slug_is_read_only(self, agent_client, category):
        response = agent_client.post(
            agent_url("agent-product-list"),
            data={
                "name": "Nome Real",
                "slug": "slug-forjado",
                "price": "10.00",
                "stock": 1,
                "category": category.pk,
            },
        )
        assert response.status_code == 201
        assert Product.objects.get(name="Nome Real").slug == "nome-real"

    def test_update_product_and_audit_old_new(self, agent_client, product):
        url = agent_url("agent-product-detail", slug=product.slug)
        response = agent_client.patch(
            url, data={"price": "149.90"}, content_type="application/json"
        )
        assert response.status_code == 200
        product.refresh_from_db()
        assert product.price == Decimal("149.90")
        log = AuditLog.objects.get(action="update")
        assert log.old_value["price"] == "199.90"
        assert log.new_value["price"] == "149.90"

    def test_negative_price_rejected(self, agent_client, category):
        response = agent_client.post(
            agent_url("agent-product-list"),
            data={
                "name": "X",
                "price": "-5.00",
                "stock": 1,
                "category": category.pk,
            },
        )
        assert response.status_code == 400

    def test_delete_is_soft(self, agent_client, product):
        url = agent_url("agent-product-detail", slug=product.slug)
        response = agent_client.delete(url)
        assert response.status_code == 204
        product.refresh_from_db()
        assert product.is_active is False
        assert product.is_published is False
        assert Product.objects.filter(pk=product.pk).exists()  # not deleted
        log = AuditLog.objects.get(action="deactivate")
        assert log.resource_id == str(product.pk)


@pytest.mark.django_db
class TestAgentThrottling:
    def test_throttle_limit(self, agent_client, settings, product):
        settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {"agent": "3/minute"}
        from apps.api.agent.throttling import AgentRateThrottle

        AgentRateThrottle.THROTTLE_RATES = {"agent": "3/minute"}
        cache.clear()
        url = agent_url("agent-product-list")
        codes = [agent_client.get(url).status_code for _ in range(4)]
        assert codes[:3] == [200, 200, 200]
        assert codes[3] == 429


# ---------- FASE 11: product image upload ----------


def _png_bytes():
    # 1x1 transparent PNG (67 bytes, well under 5MB)
    import base64

    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )


@pytest.mark.django_db
class TestProductImageUpload:
    def _product(self, category):
        return Product.objects.create(
            name="Produto Foto", price="10.00", stock=1, category=category
        )

    def test_upload_image_creates_primary(self, agent_client, category):
        product = self._product(category)
        img = SimpleUploadedFile("foto.png", _png_bytes(), content_type="image/png")
        response = agent_client.post(
            f"/api/v1/agent/products/{product.slug}/images/",
            {"image": img, "is_primary": True, "alt_text": "Foto principal"},
            format="multipart",
        )
        assert response.status_code == 201
        assert product.images.count() == 1
        image = product.images.get()
        assert image.is_primary is True
        assert image.alt_text == "Foto principal"
        assert AuditLog.objects.filter(action="upload_image").exists()

    def test_second_primary_replaces_first(self, agent_client, category):
        product = self._product(category)
        for i in range(2):
            img = SimpleUploadedFile(f"foto{i}.png", _png_bytes(), content_type="image/png")
            agent_client.post(
                f"/api/v1/agent/products/{product.slug}/images/",
                {"image": img, "is_primary": True},
                format="multipart",
            )
        assert product.images.filter(is_primary=True).count() == 1

    def test_invalid_extension_rejected(self, agent_client, category):
        product = self._product(category)
        bad = SimpleUploadedFile("virus.exe", b"MZ", content_type="application/octet-stream")
        response = agent_client.post(
            f"/api/v1/agent/products/{product.slug}/images/",
            {"image": bad},
            format="multipart",
        )
        assert response.status_code == 400
        assert product.images.count() == 0

    def test_upload_requires_auth(self, client, category):
        product = self._product(category)
        img = SimpleUploadedFile("foto.png", _png_bytes(), content_type="image/png")
        response = client.post(
            f"/api/v1/agent/products/{product.slug}/images/",
            {"image": img},
            format="multipart",
        )
        assert response.status_code in (401, 403)


# ---------- FASE 12: agent categories ----------


@pytest.mark.django_db
class TestAgentCategories:
    def test_create_category(self, agent_client):
        response = agent_client.post(
            "/api/v1/agent/categories/",
            {"name": "Camisetas", "description": "Camisetas em geral"},
            format="json",
        )
        assert response.status_code == 201
        assert response.json()["slug"] == "camisetas"
        assert AuditLog.objects.filter(action="create", resource="category").exists()

    def test_list_categories(self, agent_client, category):
        response = agent_client.get("/api/v1/agent/categories/")
        assert response.status_code == 200
        names = [c["name"] for c in response.json()["results"]]
        assert category.name in names

    def test_update_category(self, agent_client, category):
        response = agent_client.patch(
            f"/api/v1/agent/categories/{category.slug}/",
            data='{"description": "Nova descricao"}',
            content_type="application/json",
        )
        assert response.status_code == 200
        category.refresh_from_db()
        assert category.description == "Nova descricao"

    def test_delete_is_soft_deactivate(self, agent_client, category):
        response = agent_client.delete(f"/api/v1/agent/categories/{category.slug}/")
        assert response.status_code == 204
        category.refresh_from_db()
        assert category.is_active is False

    def test_create_requires_auth(self, client):
        response = client.post(
            "/api/v1/agent/categories/", {"name": "Sem Auth"}, format="json"
        )
        assert response.status_code in (401, 403)


# ---------- FASE 13: product line (verao/inverno) ----------


@pytest.mark.django_db
class TestAgentProductLine:
    def test_agent_api_accepts_line(self, agent_client, category):
        response = agent_client.post(
            "/api/v1/agent/products/",
            data={
                "name": "Legging",
                "price": "89.90",
                "stock": 10,
                "category": category.pk,
                "line": "verao",
            },
            content_type="application/json",
        )
        assert response.status_code == 201
        assert Product.objects.get(name="Legging").line == "verao"


# ---------- FASE 14: sync from Google Drive ----------


@pytest.mark.django_db
class TestSyncProduct:
    URL = "/api/v1/agent/sync/product/"

    def test_sync_creates_product_and_category(self, agent_client):
        payload = {
            "drive_file_id": "drive123",
            "nome": "Camiseta UV - Azul - P ao G - 49.90",
            "categoria": "Camisetas UV",
            "cor": "Azul",
            "tamanho": "P ao G",
            "preco_unitario": "49.90",
            "preco_atacado_6": "44.90",
            "preco_caixa_24": "42.90",
            "url_imagem": "https://drive.google.com/file/d/drive123/view",
        }
        response = agent_client.post(self.URL, data=payload, format="json")
        assert response.status_code == 201
        product = Product.objects.get(drive_file_id="drive123")
        assert product.category.name == "Camisetas UV"
        assert product.color == "Azul"
        assert product.is_published is True

    def test_sync_updates_existing_product(self, agent_client, category):
        product = Product.objects.create(
            name="Antigo", price="10.00", stock=1, category=category,
            drive_file_id="drive999",
        )
        payload = {
            "drive_file_id": "drive999",
            "nome": "Novo Nome",
            "categoria": category.name,
            "preco_unitario": "59.90",
        }
        response = agent_client.post(self.URL, data=payload, format="json")
        assert response.status_code == 200
        product.refresh_from_db()
        assert product.name == "Novo Nome"
        assert product.price == Decimal("59.90")

    def test_sync_requires_drive_file_id(self, agent_client):
        response = agent_client.post(self.URL, data={"nome": "X"}, format="json")
        assert response.status_code == 400

    def test_sync_requires_auth(self, client):
        response = client.post(self.URL, data={"drive_file_id": "x"}, format="json")
        assert response.status_code in (401, 403)
