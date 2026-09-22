"""Business logic for critical confirmed actions (ADR-7)."""
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from apps.products.models import Product

from .models import PendingAction


class ActionValidationError(Exception):
    """Domain validation failure; mapped to HTTP 400 by the views."""

    def __init__(self, errors):
        self.errors = errors
        super().__init__(str(errors))


def propose_price_change(*, product, user, new_price):
    try:
        price = Decimal(str(new_price))
    except (InvalidOperation, TypeError, ValueError):
        raise ActionValidationError({"price": "Valor inválido."})
    if price < Decimal("0.00"):
        raise ActionValidationError({"price": "Preço não pode ser negativo."})
    return PendingAction.objects.create(
        action_type=PendingAction.ActionType.SET_PRICE,
        product=product,
        payload={"price": str(price)},
        summary={"field": "price", "current": str(product.price), "new": str(price)},
        created_by=user,
    )


def propose_stock_change(*, product, user, new_stock):
    try:
        stock = int(new_stock)
    except (TypeError, ValueError):
        raise ActionValidationError({"stock": "Valor inválido."})
    if stock < 0:
        raise ActionValidationError({"stock": "Estoque não pode ser negativo."})
    return PendingAction.objects.create(
        action_type=PendingAction.ActionType.SET_STOCK,
        product=product,
        payload={"stock": stock},
        summary={"field": "stock", "current": product.stock, "new": stock},
        created_by=user,
    )


def confirm_action(*, action):
    """Apply a pending action atomically. Returns (product, old_value, new_value)."""
    # Mark expired actions outside the atomic block: the rollback triggered by
    # raising ActionValidationError must not undo the status update.
    if action.status == PendingAction.Status.PENDING and action.is_expired:
        action.status = PendingAction.Status.EXPIRED
        action.save(update_fields=["status"])
    with transaction.atomic():
        action = PendingAction.objects.select_for_update().get(pk=action.pk)
        if action.status != PendingAction.Status.PENDING:
            raise ActionValidationError(
                {"action": f"Ação não está pendente (status: {action.status})."}
            )

        product = Product.objects.select_for_update().get(pk=action.product.pk)
        if action.action_type == PendingAction.ActionType.SET_PRICE:
            old_value = {"price": str(product.price)}
            product.price = Decimal(action.payload["price"])
            product.save(update_fields=["price"])
            new_value = {"price": str(product.price)}
        else:  # SET_STOCK
            old_value = {"stock": product.stock}
            product.stock = int(action.payload["stock"])
            product.save(update_fields=["stock"])
            new_value = {"stock": product.stock}

        action.status = PendingAction.Status.CONFIRMED
        action.confirmed_at = timezone.now()
        action.save(update_fields=["status", "confirmed_at"])
    return product, old_value, new_value
