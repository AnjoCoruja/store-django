from rest_framework.throttling import SimpleRateThrottle


class AgentRateThrottle(SimpleRateThrottle):
    """Per-token rate limit for agent API requests (scope: 'agent')."""

    scope = "agent"

    def get_cache_key(self, request, view):
        if request.auth is None:
            return None  # unauthenticated requests are rejected by permissions
        return self.cache_format % {"scope": self.scope, "ident": request.auth.key}
