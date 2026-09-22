import pytest

from apps.audit.models import AuditLog

pytestmark = pytest.mark.django_db


def test_audit_log_creation():
    log = AuditLog.objects.create(
        actor_type=AuditLog.ActorType.AGENT,
        actor_id="website-agent",
        action="UPDATE_PRICE",
        resource="Product",
        resource_id="15",
        old_value={"price": "79.90"},
        new_value={"price": "69.90"},
        status=AuditLog.Status.SUCCESS,
        ip="203.0.113.10",
    )
    assert log.pk is not None
    assert "agent:UPDATE_PRICE:Product#15" in str(log)


def test_audit_log_ordering_newest_first():
    AuditLog.objects.create(
        actor_type="agent", action="A", resource="Product"
    )
    last = AuditLog.objects.create(
        actor_type="agent", action="B", resource="Product"
    )
    assert AuditLog.objects.first() == last
