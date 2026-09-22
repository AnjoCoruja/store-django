"""Audit helper for agent API mutations.

Writes an append-only AuditLog entry. Never log secrets, tokens or
passwords — call sites must pass only business fields.
"""
from apps.audit.models import AuditLog


def log_agent_action(
    request,
    *,
    action,
    resource,
    resource_id="",
    old_value=None,
    new_value=None,
    status=AuditLog.Status.SUCCESS,
):
    ip = request.META.get("REMOTE_ADDR")
    return AuditLog.objects.create(
        actor_type=AuditLog.ActorType.AGENT,
        actor_id=str(request.user.username or request.user.pk),
        action=action,
        resource=resource,
        resource_id=str(resource_id),
        old_value=old_value,
        new_value=new_value,
        status=status,
        ip=ip,
    )
