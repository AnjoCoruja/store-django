from django.db.models import Prefetch, Q
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
    categories = Category.objects.filter(is_active=True, parent__isnull=True)[:6]
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


LINES = (("verao", "Verão"), ("inverno", "Inverno"))


def _subcategory_lines(sub, products_by_cat):
    """Abas em que uma subcategoria aparece: linha explícita ou linhas dos produtos."""
    if sub.line:
        return {sub.line}
    return products_by_cat.get(sub.pk, set())


def category_detail(request, slug):
    category = get_object_or_404(
        Category.objects.select_related("parent"), slug=slug, is_active=True
    )
    category_ids = category.descendant_ids()
    products = (
        Product.objects.filter(
            category_id__in=category_ids,
            category__is_active=True,
            is_active=True,
            is_published=True,
        )
        .select_related("category")
        .prefetch_related("images")
    )

    subcategories = list(category.subcategories.filter(is_active=True))

    # Mapeia subcategoria -> linhas presentes nos produtos dela (e descendentes).
    products_by_cat = {}
    for sub in subcategories:
        lines = set(
            Product.objects.filter(
                category_id__in=sub.descendant_ids(),
                is_active=True,
                is_published=True,
            ).values_list("line", flat=True)
        )
        products_by_cat[sub.pk] = lines

    active_line = request.GET.get("linha", "")
    valid_lines = {code for code, _ in LINES}
    if active_line not in valid_lines:
        active_line = ""

    tabs = []
    for code, label in LINES:
        tab_subs = [s for s in subcategories if code in _subcategory_lines(s, products_by_cat)]
        tabs.append(
            {
                "code": code,
                "label": label,
                "subcategories": tab_subs,
                "product_count": sum(1 for p in products if p.line == code),
            }
        )

    if not active_line:
        # Abre na primeira aba que tem conteúdo (padrão: Verão).
        active_line = next(
            (t["code"] for t in tabs if t["product_count"] or t["subcategories"]),
            "verao",
        )

    return render(
        request,
        "website/category_detail.html",
        {
            "category": category,
            "products": products,
            "subcategories": subcategories,
            "tabs": tabs,
            "active_line": active_line,
            "meta_title": f"{category.name} — Loja",
            "meta_description": (category.description or category.name)[:155],
        },
    )


def shop(request):
    """Vitrine em abas: Estação (Verão/Inverno) -> Categoria -> Produtos."""
    products_qs = Product.objects.filter(is_active=True, is_published=True).prefetch_related("images")
    tops = list(
        Category.objects.filter(is_active=True, parent__isnull=True)
        .prefetch_related(Prefetch("subcategories", queryset=Category.objects.filter(is_active=True)))
    )
    all_products = list(products_qs.select_related("category"))
    seasons = []
    for code, label in LINES:
        cats = []
        for cat in tops:
            ids = set(cat.descendant_ids())
            prods = [p for p in all_products if p.category_id in ids and p.line == code]
            if cat.line and cat.line != code:
                continue
            if not prods and cat.line != code:
                continue
            cats.append({"category": cat, "products": prods})
        seasons.append({"code": code, "label": label, "categories": cats})
    active = request.GET.get("linha")
    if active not in {c for c, _ in LINES}:
        active = next((s["code"] for s in seasons if s["categories"]), "verao")
    active_cat = request.GET.get("categoria", "")
    return render(
        request,
        "website/shop.html",
        {
            "seasons": seasons,
            "active_line": active,
            "active_category": active_cat,
            "meta_title": "Loja | Red Blue Line — Verão & Inverno",
            "meta_description": "Escolha a estação, a categoria e monte seu pedido. Finalize pelo WhatsApp.",
        },
    )
