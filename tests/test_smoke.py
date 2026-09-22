"""Smoke tests for project initialization (FASE 2)."""

from django.conf import settings
from django.test import Client
from django.urls import reverse


def test_settings_loaded():
    assert settings.SECRET_KEY
    assert settings.ROOT_URLCONF == "config.urls"


def test_admin_login_page_responds(db):
    client = Client()
    response = client.get(reverse("admin:login"))
    assert response.status_code == 200


def test_database_engine_is_engine_agnostic():
    engine = settings.DATABASES["default"]["ENGINE"]
    assert engine in {
        "django.db.backends.sqlite3",
        "django.db.backends.postgresql",
    }
