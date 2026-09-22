"""Pending critical actions awaiting explicit confirmation (ADR-7)."""
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class PendingAction(models.Model):
    """A critical operation (price/stock change) persisted but not executed.

    The agent proposes the action, receives a summary, and must call the
    /confirm/ endpoint before `expires_at` for it to be applied.
    """

    class ActionType(models.TextChoices):
        SET_PRICE = "set_price", "Set price"
        SET_STOCK = "set_stock", "Set stock"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        EXPIRED = "expired", "Expired"
        CANCELLED = "cancelled", "Cancelled"

    EXPIRATION_MINUTES = 10

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    action_type = models.CharField(max_length=20, choices=ActionType.choices)
    product = models.ForeignKey(
        "products.Product", on_delete=models.CASCADE, related_name="pending_actions"
    )
    payload = models.JSONField(
        help_text='Proposed new value(s), e.g. {"price": "10.00"}.'
    )
    summary = models.JSONField(
        help_text="Current -> proposed values shown to the agent for confirmation."
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timezone.timedelta(
                minutes=self.EXPIRATION_MINUTES
            )
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    def __str__(self):
        return f"{self.action_type} product#{self.product_id} ({self.status})"
