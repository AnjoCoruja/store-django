from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AgentProductViewSet, ConfirmActionView

app_name = "agent"

router = DefaultRouter()
router.register("products", AgentProductViewSet, basename="agent-product")

urlpatterns = [
    path(
        "actions/<uuid:action_id>/confirm/",
        ConfirmActionView.as_view(),
        name="confirm-action",
    ),
    path("", include(router.urls)),
]
