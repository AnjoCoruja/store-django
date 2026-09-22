"""Write serializers for the agent API.

Deliberately separate from the public read serializers: only fields the
agent is allowed to mutate are writable, and slugs are read-only
(auto-generated from the name).
"""
from decimal import Decimal

from rest_framework import serializers

from apps.products.models import (
    ALLOWED_IMAGE_EXTENSIONS,
    Category,
    Product,
    ProductImage,
    validate_image_size,
)


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
            "line",
            "category",
            "is_published",
            "is_active",
        ]
        read_only_fields = ["id", "slug"]

    def validate_price(self, value):
        if value < Decimal("0.00"):
            raise serializers.ValidationError("Preço não pode ser negativo.")
        return value


class ProductImageAgentSerializer(serializers.ModelSerializer):
    """Upload of product images by the agent (multipart)."""

    class Meta:
        model = ProductImage
        fields = ["id", "image", "alt_text", "is_primary", "sort_order"]

    def validate_image(self, value):
        ext = value.name.rsplit(".", 1)[-1].lower() if "." in value.name else ""
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            raise serializers.ValidationError(
                f"Extensão não permitida: .{ext}. Use: {', '.join(ALLOWED_IMAGE_EXTENSIONS)}."
            )
        validate_image_size(value)
        return value


class CategoryAgentSerializer(serializers.ModelSerializer):
    """Write serializer for agent-managed categories (slug auto-generated)."""

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "description", "is_active", "sort_order"]
        read_only_fields = ["id", "slug"]
