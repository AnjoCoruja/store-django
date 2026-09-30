import json
from urllib.parse import quote

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from .models import Order
from .services import OrderError, create_order, order_xlsx, whatsapp_message


@require_POST
def checkout(request):
    try:
        payload = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "JSON inválido."}, status=400)
    try:
        order = create_order(payload.get("items"), payload.get("customer_name", ""))
    except OrderError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    sheet_url = request.build_absolute_uri(
        reverse("orders:spreadsheet", args=[order.public_id])
    )
    message = whatsapp_message(order, sheet_url)
    return JsonResponse(
        {
            "order": order.code,
            "total": f"{order.total:.2f}",
            "spreadsheet_url": sheet_url,
            "whatsapp_url": f"https://wa.me/{settings.WHATSAPP_NUMBER}?text={quote(message)}",
        },
        status=201,
    )


@require_GET
def spreadsheet(request, public_id):
    order = get_object_or_404(Order.objects.prefetch_related("items"), public_id=public_id)
    resp = HttpResponse(
        order_xlsx(order),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = f'attachment; filename="pedido-{order.code}.xlsx"'
    return resp
