from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("product", "product_name", "line", "size", "color", "qty", "unit_price", "subtotal")
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("__str__", "created_at", "customer_name", "total_qty", "tier", "total", "status", "planilha")
    list_filter = ("status", "tier", "created_at")
    list_editable = ("status",)
    readonly_fields = ("public_id", "total_qty", "tier", "total", "created_at", "planilha")
    inlines = [OrderItemInline]

    @admin.display(description="Planilha")
    def planilha(self, obj):
        if not obj.pk:
            return "-"
        return format_html('<a href="{}">Baixar XLSX</a>', reverse("orders:spreadsheet", args=[obj.public_id]))
