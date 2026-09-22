"""Write serializers for the agent API.

Deliberately separate from the public read serializers: only fields the
agent is allowed to mutate are writable, and slugs are read-only
(auto-generated from the name).
"""
from decimal import Decimal

from rest_framework import serializers

from apps.products.models import Product


class ProductAgentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "price",
            "wholesale_price",
            "stock",
            "category",
            "is_published",
            "is_active",
        ]
        read_only_fields = ["id", "slug"]

    def validate_price(self, value):
        if value < Decimal("0.00"):
            raise serializers.ValidationError("Preço não pode ser negativo.")
        return value
