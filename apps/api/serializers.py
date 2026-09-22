"""Serializers for the public read API (v1).

Money values are serialized from DecimalField as strings by DRF's
DecimalField coercion to avoid float rounding issues for API consumers.
"""
from rest_framework import serializers

from apps.products.models import Category, Product, ProductImage


class CategorySerializer(serializers.ModelSerializer):
    product_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "image",
            "sort_order",
            "product_count",
        ]


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ["id", "image", "alt_text", "is_primary", "sort_order"]


class ProductListSerializer(serializers.ModelSerializer):
    category = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    primary_image = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "price",
            "stock",
            "line",
            "category",
            "primary_image",
        ]

    def get_primary_image(self, obj):
        image = getattr(obj, "prefetched_primary_image", None)
        if image is None:
            image = obj.images.filter(is_primary=True).first()
        if image is None:
            return None
        request = self.context.get("request")
        url = image.image.url
        return request.build_absolute_uri(url) if request else url


class ProductDetailSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "price",
            "wholesale_price",
            "line",
            "stock",
            "category",
            "images",
            "created_at",
            "updated_at",
        ]
