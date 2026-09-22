import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from tests.factories import CategoryFactory, ProductFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client():
    user = User.objects.create_superuser(
        username="admin", email="admin@test.com", password="admin123"
    )
    client = Client()
    client.force_login(user)
    return client


class TestProductAdmin:
    def test_changelist_loads(self, admin_client):
        ProductFactory()
        response = admin_client.get(reverse("admin:products_product_changelist"))
        assert response.status_code == 200

    def test_create_product_via_admin(self, admin_client):
        category = CategoryFactory()
        data = {
            "name": "Produto Admin",
            "slug": "produto-admin",
            "description": "Criado pelo admin",
            "price": "99.90",
            "stock": 5,
            "category": category.pk,
            "is_active": "on",
            "images-TOTAL_FORMS": 0,
            "images-INITIAL_FORMS": 0,
            "images-MIN_NUM_FORMS": 0,
            "images-MAX_NUM_FORMS": 1000,
        }
        response = admin_client.post(
            reverse("admin:products_product_add"), data, follow=True
        )
        assert response.status_code == 200
        from apps.products.models import Product

        assert Product.objects.filter(slug="produto-admin").exists()

    def test_edit_price_and_stock_via_changeform(self, admin_client):
        product = ProductFactory(price="50.00", stock=3)
        data = {
            "name": product.name,
            "slug": product.slug,
            "description": product.description,
            "price": "45.00",
            "stock": 7,
            "category": product.category.pk,
            "is_active": "on",
            "is_published": "on",
            "images-TOTAL_FORMS": 0,
            "images-INITIAL_FORMS": 0,
            "images-MIN_NUM_FORMS": 0,
            "images-MAX_NUM_FORMS": 1000,
        }
        response = admin_client.post(
            reverse("admin:products_product_change", args=[product.pk]),
            data,
            follow=True,
        )
        assert response.status_code == 200
        product.refresh_from_db()
        assert str(product.price) == "45.00"
        assert product.stock == 7

    def test_publish_action(self, admin_client):
        p1 = ProductFactory(is_published=False)
        p2 = ProductFactory(is_published=False)
        data = {"action": "publish_products", "_selected_action": [p1.pk, p2.pk]}
        response = admin_client.post(
            reverse("admin:products_product_changelist"), data, follow=True
        )
        assert response.status_code == 200
        p1.refresh_from_db()
        p2.refresh_from_db()
        assert p1.is_published and p2.is_published

    def test_unpublish_action(self, admin_client):
        p1 = ProductFactory(is_published=True)
        data = {"action": "unpublish_products", "_selected_action": [p1.pk]}
        admin_client.post(reverse("admin:products_product_changelist"), data)
        p1.refresh_from_db()
        assert p1.is_published is False


class TestCategoryAdmin:
    def test_create_category(self, admin_client):
        data = {
            "name": "Nova Categoria",
            "slug": "nova-categoria",
            "description": "",
            "is_active": "on",
            "sort_order": 0,
        }
        response = admin_client.post(
            reverse("admin:products_category_add"), data, follow=True
        )
        assert response.status_code == 200
        from apps.products.models import Category

        assert Category.objects.filter(slug="nova-categoria").exists()


class TestAuditLogAdmin:
    def test_read_only(self, admin_client):
        from apps.audit.models import AuditLog

        AuditLog.objects.create(actor_type="agent", action="TEST", resource="Product")
        response = admin_client.get(reverse("admin:audit_auditlog_changelist"))
        assert response.status_code == 200
        # No add permission
        response = admin_client.get(reverse("admin:audit_auditlog_add"))
        assert response.status_code == 403

    def test_admin_requires_login(self):
        client = Client()
        response = client.get(reverse("admin:products_product_changelist"))
        assert response.status_code == 302  # redirect to login
