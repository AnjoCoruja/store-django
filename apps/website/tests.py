import pytest

from django.test import TestCase

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
