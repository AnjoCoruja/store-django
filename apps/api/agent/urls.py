from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AgentCategoryViewSet, AgentProductViewSet, ConfirmActionView

app_name = "agent"

router = DefaultRouter()
router.register("products", AgentProductViewSet, basename="agent-product")
router.register("categories", AgentCategoryViewSet, basename="agent-category")

urlpatterns = [
    path(
        "actions/<uuid:action_id>/confirm/",
        ConfirmActionView.as_view(),
        name="confirm-action",
    ),
    path("", include(router.urls)),
]
