import uuid
from decimal import Decimal

from django.db import models


class Order(models.Model):
    class Status(models.TextChoices):
        NOVO = "novo", "Novo (enviado ao WhatsApp)"
        CONFIRMADO = "confirmado", "Confirmado"
        CANCELADO = "cancelado", "Cancelado"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    customer_name = models.CharField("Cliente", max_length=120, blank=True, default="")
    total_qty = models.PositiveIntegerField(default=0)
    tier = models.CharField("Faixa de preço", max_length=20, blank=True, default="")
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NOVO)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "pedido"

    def __str__(self):
        return f"Pedido #{self.pk}"

    @property
    def code(self):
        return f"RBL-{self.pk:05d}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        "products.Product", on_delete=models.SET_NULL, null=True, related_name="order_items"
    )
    product_name = models.CharField(max_length=200)
    line = models.CharField(max_length=10, blank=True, default="")
    size = models.CharField(max_length=20, blank=True, default="")
    color = models.CharField(max_length=60, blank=True, default="")
    qty = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.qty}x {self.product_name}"
