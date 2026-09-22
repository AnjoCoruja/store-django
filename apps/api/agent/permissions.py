from rest_framework.permissions import BasePermission


class IsAgentToken(BasePermission):
    """Allows access only to requests authenticated with an API token.

    The token identifies the agent/service account; the linked user must
    be active and staff (service accounts are created as staff users).
    """

    message = "Agent API requires token authentication (Authorization: Token <key>)."

    def has_permission(self, request, view):
        return bool(
            request.auth is not None
            and request.user
            and request.user.is_authenticated
            and request.user.is_active
            and request.user.is_staff
        )
