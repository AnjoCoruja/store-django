from django.contrib import admin, messages

from .models import Category, Product, ProductImage


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ("image", "alt_text", "is_primary", "sort_order")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "line", "slug", "is_active", "sort_order")
    list_filter = ("is_active", "line", "parent")
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}
    list_editable = ("is_active", "sort_order")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "category",
        "line",
        "price",
        "stock",
        "is_active",
        "is_published",
        "updated_at",
    )
    list_display_links = ("name",)
    list_filter = ("is_active", "is_published", "line", "category")
    search_fields = ("name", "description", "slug")
    prepopulated_fields = {"slug": ("name",)}
    list_editable = ("price", "stock")
    inlines = [ProductImageInline]
    actions = ("publish_products", "unpublish_products")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("name", "slug", "description", "category", "line")}),
        ("Variações", {"fields": ("color", "size_range")}),
        (
            "Preço e estoque",
            {"fields": ("price", "wholesale_price", "wholesale_price_6", "wholesale_price_24", "stock")},
        ),
        ("Imagem externa (Drive)", {"fields": ("image_url", "drive_file_id"), "classes": ("collapse",)}),
        ("Visibilidade", {"fields": ("is_active", "is_published")}),
        ("Datas", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.action(description="Publicar produtos selecionados")
    def publish_products(self, request, queryset):
        updated = queryset.update(is_published=True)
        self.message_user(request, f"{updated} produto(s) publicado(s).", messages.SUCCESS)

    @admin.action(description="Despublicar produtos selecionados")
    def unpublish_products(self, request, queryset):
        updated = queryset.update(is_published=False)
        self.message_user(request, f"{updated} produto(s) despublicado(s).", messages.SUCCESS)
