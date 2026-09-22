"""Agent API endpoints (v1): authenticated write operations for the AI agent.

Security model (see docs/ARCHITECTURE.md):
- Token authentication (Authorization: Token <key>) against staff service users.
- Per-token rate limiting (scope 'agent').
- Every mutation is written to the append-only AuditLog (never secrets).
"""
from rest_framework import status, viewsets
from rest_framework.authentication import TokenAuthentication
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import AuditLog
from apps.products.models import Product

from ..serializers import ProductDetailSerializer
from .audit import log_agent_action
from .models import PendingAction
from .permissions import IsAgentToken
from .serializers import ProductAgentSerializer
from .services import (
    ActionValidationError,
    confirm_action,
    propose_price_change,
    propose_stock_change,
)
from .throttling import AgentRateThrottle


class AgentProductViewSet(viewsets.ModelViewSet):
    """Full product management for the agent. Lookup by slug."""

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAgentToken]
    throttle_classes = [AgentRateThrottle]
    lookup_field = "slug"
    queryset = Product.objects.select_related("category").all()

    def get_serializer_class(self):
        if self.action in ("list", "retrieve"):
            return ProductDetailSerializer
        return ProductAgentSerializer

    def perform_create(self, serializer):
        product = serializer.save()
        log_agent_action(
            self.request,
            action="create",
            resource="product",
            resource_id=product.pk,
            new_value=ProductAgentSerializer(product).data,
        )

    def perform_update(self, serializer):
        old_value = ProductAgentSerializer(self.get_object()).data
        product = serializer.save()
        log_agent_action(
            self.request,
            action="update",
            resource="product",
            resource_id=product.pk,
            old_value=old_value,
            new_value=ProductAgentSerializer(product).data,
        )

    def destroy(self, request, *args, **kwargs):
        """Soft-delete: deactivate instead of removing (no destructive ops)."""
        product = self.get_object()
        old_value = ProductAgentSerializer(product).data
        product.is_active = False
        product.is_published = False
        product.save(update_fields=["is_active", "is_published"])
        log_agent_action(
            request,
            action="deactivate",
            resource="product",
            resource_id=product.pk,
            old_value=old_value,
            new_value={"is_active": False, "is_published": False},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    def perform_destroy(self, instance):  # not used; destroy overridden above
        raise NotImplementedError

    @action(detail=True, methods=["post"], url_path="price")
    def set_price(self, request, slug=None):
        """Critical: propose a price change (requires /confirm/ to apply)."""
        product = self.get_object()
        try:
            pending = propose_price_change(
                product=product, user=request.user, new_price=request.data.get("price")
            )
        except ActionValidationError as exc:
            return Response(exc.errors, status=status.HTTP_400_BAD_REQUEST)
        return Response(_pending_payload(pending), status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"], url_path="stock")
    def set_stock(self, request, slug=None):
        """Critical: propose a stock change (requires /confirm/ to apply)."""
        product = self.get_object()
        try:
            pending = propose_stock_change(
                product=product, user=request.user, new_stock=request.data.get("stock")
            )
        except ActionValidationError as exc:
            return Response(exc.errors, status=status.HTTP_400_BAD_REQUEST)
        return Response(_pending_payload(pending), status=status.HTTP_202_ACCEPTED)


def _pending_payload(pending):
    return {
        "action_id": str(pending.pk),
        "summary": pending.summary,
        "requires_confirmation": True,
        "expires_at": pending.expires_at.isoformat(),
    }


class ConfirmActionView(APIView):
    """Confirm and execute a pending critical action."""

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAgentToken]
    throttle_classes = [AgentRateThrottle]

    def post(self, request, action_id):
        try:
            pending = PendingAction.objects.get(pk=action_id)
        except (PendingAction.DoesNotExist, ValueError):
            return Response(
                {"action": "Ação não encontrada."}, status=status.HTTP_404_NOT_FOUND
            )
        if pending.created_by_id != request.user.pk:
            return Response(
                {"action": "Ação pertence a outro agente."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            product, old_value, new_value = confirm_action(action=pending)
        except ActionValidationError as exc:
            return Response(exc.errors, status=status.HTTP_400_BAD_REQUEST)
        log_agent_action(
            request,
            action=pending.action_type,
            resource="product",
            resource_id=product.pk,
            old_value=old_value,
            new_value=new_value,
        )
        return Response(
            {
                "action_id": str(pending.pk),
                "status": "confirmed",
                "product": product.slug,
                "applied": new_value,
            }
        )
