from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "actor_type",
        "actor_id",
        "action",
        "resource",
        "resource_id",
        "status",
    )
    list_filter = ("actor_type", "action", "status", "resource")
    search_fields = ("actor_id", "resource", "resource_id")
    readonly_fields = (
        "actor_type",
        "actor_id",
        "action",
        "resource",
        "resource_id",
        "old_value",
        "new_value",
        "status",
        "ip",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
