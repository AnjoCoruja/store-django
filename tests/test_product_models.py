"""Tests for the products models (constraints, slugs, variants)."""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.products.models import Category, Product


@pytest.mark.django_db
class TestProductVariants:
    def test_available_sizes_letter_range(self):
        p = Product(size_range="P ao GG")
        assert p.available_sizes() == ["P", "M", "G", "GG"]

    def test_available_sizes_numeric_range(self):
        p = Product(size_range="04 ao 16")
        assert p.available_sizes() == ["04", "06", "08", "10", "12", "14", "16"]

    def test_available_sizes_single(self):
        p = Product(size_range="Único")
        assert p.available_sizes() == ["Único"]

    def test_available_sizes_empty(self):
        p = Product(size_range="")
        assert p.available_sizes() == []

    def test_available_colors(self):
        p = Product(color="preto, branco, azul")
        assert p.available_colors() == ["preto", "branco", "azul"]

    def test_available_colors_empty(self):
        p = Product(color="")
        assert p.available_colors() == []
