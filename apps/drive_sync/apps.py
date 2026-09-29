from django.apps import AppConfig


class DriveSyncConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.drive_sync"
    verbose_name = "Sincronização Google Drive"
