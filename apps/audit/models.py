from django.db import models


class AuditLog(models.Model):
    """Append-only audit trail for important operations.

    Written on every mutation performed through the agent API (and other
    critical actions). Never stores secrets, tokens or passwords.
    """

    class ActorType(models.TextChoices):
        USER = "user", "User"
        AGENT = "agent", "Agent"

    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILURE = "failure", "Failure"

    actor_type = models.CharField(max_length=10, choices=ActorType.choices)
    actor_id = models.CharField(max_length=150, blank=True, default="")
    action = models.CharField(max_length=80, db_index=True)
    resource = models.CharField(max_length=80)
    resource_id = models.CharField(max_length=64, blank=True, default="")
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SUCCESS)
    ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.actor_type}:{self.action}:{self.resource}#{self.resource_id}"
