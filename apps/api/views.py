"""Public read-only API viewsets (v1).

Only published products and active categories are exposed. All endpoints
are read-only; write operations will be added in the agent API phase with
authentication, permissions and rate limiting (see docs/ARCHITECTURE.md).
"""
from django.db.models import Count, Prefetch, Q
from rest_framework import viewsets
from rest_framework.permissions import AllowAny

from apps.products.models import Category, Product, ProductImage

from .serializers import (
    CategorySerializer,
    ProductDetailSerializer,
    ProductListSerializer,
)


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """List and retrieve active categories. Lookup by slug."""

    serializer_class = CategorySerializer
    permission_classes = [AllowAny]
    lookup_field = "slug"

    def get_queryset(self):
        return (
            Category.objects.filter(is_active=True)
            .annotate(
                product_count=Count(
                    "products", filter=Q(products__is_published=True)
                )
            )
            .order_by("sort_order", "name")
        )


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    """List and retrieve published products. Lookup by slug.

    Supports filtering by category slug (?category=<slug>) and search
    (?q=<term>) over name and description.
    """

    permission_classes = [AllowAny]
    lookup_field = "slug"

    def get_queryset(self):
        qs = (
            Product.objects.filter(is_published=True)
            .select_related("category")
            .prefetch_related(
                Prefetch(
                    "images",
                    queryset=ProductImage.objects.order_by(
                        "-is_primary", "sort_order", "created_at"
                    ),
                )
            )
        )
        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(category__slug=category, category__is_active=True)
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
        return qs.order_by("-created_at")

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ProductDetailSerializer
        return ProductListSerializer
