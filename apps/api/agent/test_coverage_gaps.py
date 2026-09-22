"""Coverage gap tests (FASE 9): edge cases not hit by the main suites."""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import RequestFactory
from django.urls import reverse
from rest_framework.authtoken.models import Token

from apps.api.agent.models import PendingAction
from apps.products.models import Category, Product

User = get_user_model()


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def agent_client(client, db):
    user = User.objects.create_user(username="agent-n8n", password="x", is_staff=True)
    token = Token.objects.create(user=user)
    client.defaults["HTTP_AUTHORIZATION"] = f"Token {token.key}"
    return client


@pytest.mark.django_db
class TestSerializerValidation:
    def test_negative_price_serializer_message(self, agent_client, db):
        category = Category.objects.create(name="Cat", is_active=True)
        response = agent_client.post(
            reverse("agent:agent-product-list"),
            data={"name": "X", "price": "-0.01", "stock": 1, "category": category.pk},
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "price" in response.json()


@pytest.mark.django_db
class TestServiceValidationEdges:
    def test_invalid_price_string(self, agent_client, db):
        category = Category.objects.create(name="Cat", is_active=True)
        product = Product.objects.create(
            name="P", price=Decimal("1.00"), stock=1, category=category
        )
        url = reverse("agent:agent-product-set-price", kwargs={"slug": product.slug})
        response = agent_client.post(
            url, data={"price": "abc"}, content_type="application/json"
        )
        assert response.status_code == 400
        assert "price" in response.json()

    def test_missing_price(self, agent_client, db):
        category = Category.objects.create(name="Cat", is_active=True)
        product = Product.objects.create(
            name="P", price=Decimal("1.00"), stock=1, category=category
        )
        url = reverse("agent:agent-product-set-price", kwargs={"slug": product.slug})
        response = agent_client.post(url, data={}, content_type="application/json")
        assert response.status_code == 400

    def test_negative_stock(self, agent_client, db):
        category = Category.objects.create(name="Cat", is_active=True)
        product = Product.objects.create(
            name="P", price=Decimal("1.00"), stock=1, category=category
        )
        url = reverse("agent:agent-product-set-stock", kwargs={"slug": product.slug})
        response = agent_client.post(
            url, data={"stock": -1}, content_type="application/json"
        )
        assert response.status_code == 400


@pytest.mark.django_db
class TestModelStrsAndHelpers:
    def test_pending_action_str(self, db):
        user = User.objects.create_user(username="a", password="x", is_staff=True)
        category = Category.objects.create(name="Cat")
        product = Product.objects.create(
            name="P", price=Decimal("1.00"), stock=1, category=category
        )
        action = PendingAction.objects.create(
            action_type="set_price",
            product=product,
            payload={"price": "2.00"},
            summary={},
            created_by=user,
        )
        assert str(action) == f"set_price product#{product.pk} (pending)"
        assert action.expires_at is not None  # auto-set on save

    def test_primary_image_fallback_no_prefetch(self, db):
        """ProductListSerializer falls back to a query when no prefetch."""
        from apps.api.serializers import ProductListSerializer

        category = Category.objects.create(name="Cat")
        product = Product.objects.create(
            name="P", price=Decimal("1.00"), stock=1, category=category
        )
        serializer = ProductListSerializer(product)
        assert serializer.data["primary_image"] is None


@pytest.mark.django_db
class TestCreateAgentTokenNormalization:
    def test_normalizes_existing_user(self, capsys):
        user = User.objects.create_user(
            username="bagunçado", password="x", is_staff=False, is_superuser=True
        )
        call_command("create_agent_token", "bagunçado")
        out = capsys.readouterr().out
        user.refresh_from_db()
        assert user.is_staff and user.is_active and not user.is_superuser
        assert "normalized" in out


class TestThrottleWithoutAuth:
    def test_get_cache_key_none_without_token(self, db):
        from apps.api.agent.throttling import AgentRateThrottle

        throttle = AgentRateThrottle()
        request = RequestFactory().get("/")
        request.auth = None
        assert throttle.get_cache_key(request, view=None) is None


class TestPerformDestroyGuard:
    def test_perform_destroy_raises(self, db):
        from apps.api.agent.views import AgentProductViewSet

        view = AgentProductViewSet()
        with pytest.raises(NotImplementedError):
            view.perform_destroy(instance=None)
