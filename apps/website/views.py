from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from apps.products.models import Category, Product


def about(request):
    return render(
        request,
        "website/about.html",
        {
            "meta_title": "Sobre Nós | Red Blue Line",
            "meta_description": "Conheça a Red Blue Line: mais de 10 anos de moda no Brás, atacado e varejo. Rua Tiers, 355, Shopping Tiers, Box 55.",
        },
    )


def home(request):
    featured = (
        Product.objects.filter(is_active=True, is_published=True)
        .select_related("category")
        .prefetch_related("images")[:8]
    )
    categories = Category.objects.filter(is_active=True)[:6]
    return render(
        request,
        "website/home.html",
        {
            "featured_products": featured,
            "categories": categories,
            "meta_title": "Loja — Início",
            "meta_description": "Catálogo de produtos da nossa loja.",
        },
    )


def product_list(request):
    qs = (
        Product.objects.filter(is_active=True, is_published=True)
        .select_related("category")
        .prefetch_related("images")
    )
    query = request.GET.get("q", "").strip()
    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(description__icontains=query))
    return render(
        request,
        "website/product_list.html",
        {
            "products": qs,
            "query": query,
            "meta_title": "Produtos — Loja",
            "meta_description": "Todos os produtos disponíveis.",
        },
    )


def product_detail(request, slug):
    product = get_object_or_404(
        Product.objects.select_related("category").prefetch_related("images"),
        slug=slug,
        is_active=True,
        is_published=True,
    )
    return render(
        request,
        "website/product_detail.html",
        {
            "product": product,
            "meta_title": f"{product.name} — Loja",
            "meta_description": product.description[:155],
        },
    )


def category_detail(request, slug):
    category = get_object_or_404(Category, slug=slug, is_active=True)
    products = (
        Product.objects.filter(category=category, is_active=True, is_published=True)
        .select_related("category")
        .prefetch_related("images")
    )
    return render(
        request,
        "website/category_detail.html",
        {
            "category": category,
            "products": products,
            "meta_title": f"{category.name} — Loja",
            "meta_description": (category.description or category.name)[:155],
        },
    )
