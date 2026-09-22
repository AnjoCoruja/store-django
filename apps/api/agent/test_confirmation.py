"""Tests for critical action confirmation flow (FASE 8)."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone
from rest_framework.authtoken.models import Token

from apps.api.agent.models import PendingAction
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
        name="Teclado", price=Decimal("199.90"), stock=5, category=category
    )


@pytest.fixture
def agent_client(client, db):
    user = User.objects.create_user(username="agent-n8n", password="x", is_staff=True)
    token = Token.objects.create(user=user)
    client.defaults["HTTP_AUTHORIZATION"] = f"Token {token.key}"
    client._agent_user = user
    return client


def propose(client, product, field, value):
    url = reverse(
        f"agent:agent-product-set-{field}", kwargs={"slug": product.slug}
    )
    return client.post(url, data={field: value}, content_type="application/json")


def confirm(client, action_id):
    url = reverse("agent:confirm-action", kwargs={"action_id": action_id})
    return client.post(url)


@pytest.mark.django_db
class TestPropose:
    def test_price_proposal_does_not_apply(self, agent_client, product):
        response = propose(agent_client, product, "price", "149.90")
        assert response.status_code == 202
        data = response.json()
        assert data["requires_confirmation"] is True
        assert data["summary"] == {
            "field": "price",
            "current": "199.90",
            "new": "149.90",
        }
        product.refresh_from_db()
        assert product.price == Decimal("199.90")  # unchanged

    def test_stock_proposal_does_not_apply(self, agent_client, product):
        response = propose(agent_client, product, "stock", 42)
        assert response.status_code == 202
        product.refresh_from_db()
        assert product.stock == 5

    def test_negative_price_rejected(self, agent_client, product):
        response = propose(agent_client, product, "price", "-1.00")
        assert response.status_code == 400

    def test_invalid_stock_rejected(self, agent_client, product):
        response = propose(agent_client, product, "stock", "abc")
        assert response.status_code == 400

    def test_requires_auth(self, client, product):
        response = propose(client, product, "price", "1.00")
        assert response.status_code in (401, 403)


@pytest.mark.django_db
class TestConfirm:
    def test_confirm_applies_and_audits(self, agent_client, product):
        action_id = propose(agent_client, product, "price", "149.90").json()[
            "action_id"
        ]
        response = confirm(agent_client, action_id)
        assert response.status_code == 200
        assert response.json()["status"] == "confirmed"
        product.refresh_from_db()
        assert product.price == Decimal("149.90")
        log = AuditLog.objects.get(action="set_price")
        assert log.old_value == {"price": "199.90"}
        assert log.new_value == {"price": "149.90"}
        action = PendingAction.objects.get(pk=action_id)
        assert action.status == "confirmed"
        assert action.confirmed_at is not None

    def test_confirm_stock(self, agent_client, product):
        action_id = propose(agent_client, product, "stock", 42).json()["action_id"]
        assert confirm(agent_client, action_id).status_code == 200
        product.refresh_from_db()
        assert product.stock == 42

    def test_double_confirm_rejected(self, agent_client, product):
        action_id = propose(agent_client, product, "price", "150.00").json()[
            "action_id"
        ]
        assert confirm(agent_client, action_id).status_code == 200
        assert confirm(agent_client, action_id).status_code == 400

    def test_expired_action_rejected(self, agent_client, product):
        action_id = propose(agent_client, product, "price", "150.00").json()[
            "action_id"
        ]
        PendingAction.objects.filter(pk=action_id).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        response = confirm(agent_client, action_id)
        assert response.status_code == 400
        product.refresh_from_db()
        assert product.price == Decimal("199.90")
        assert PendingAction.objects.get(pk=action_id).status == "expired"

    def test_unknown_action_404(self, agent_client):
        import uuid

        assert confirm(agent_client, uuid.uuid4()).status_code == 404

    def test_other_agent_cannot_confirm(self, client, agent_client, product, db):
        action_id = propose(agent_client, product, "price", "150.00").json()[
            "action_id"
        ]
        other = User.objects.create_user(username="outro", password="x", is_staff=True)
        token = Token.objects.create(user=other)
        response = client.post(
            reverse("agent:confirm-action", kwargs={"action_id": action_id}),
            HTTP_AUTHORIZATION=f"Token {token.key}",
        )
        assert response.status_code == 403
        product.refresh_from_db()
        assert product.price == Decimal("199.90")


@pytest.mark.django_db
class TestCreateAgentTokenCommand:
    def test_creates_user_and_token(self, capsys):
        call_command("create_agent_token", "agente-teste")
        out = capsys.readouterr().out
        user = User.objects.get(username="agente-teste")
        assert user.is_staff and user.is_active and not user.is_superuser
        token = Token.objects.get(user=user)
        assert token.key in out

    def test_idempotent_no_duplicate(self, capsys):
        call_command("create_agent_token", "agente-teste")
        capsys.readouterr()
        call_command("create_agent_token", "agente-teste")
        out = capsys.readouterr().out
        assert "already exists" in out
        assert Token.objects.filter(user__username="agente-teste").count() == 1

    def test_rotate_issues_new_token(self, capsys):
        call_command("create_agent_token", "agente-teste")
        old = Token.objects.get(user__username="agente-teste").key
        call_command("create_agent_token", "agente-teste", rotate=True)
        out = capsys.readouterr().out
        new = Token.objects.get(user__username="agente-teste").key
        assert new != old and new in out
