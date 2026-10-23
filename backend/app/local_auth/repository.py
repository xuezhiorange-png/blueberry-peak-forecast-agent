"""Controlled ingress is an explicit allowlist, not a legacy auth fallback."""

import re

from starlette.types import ASGIApp, Receive, Scope, Send

from backend.app.local_auth.sessions import AuthError, error

READS = frozenset(
    "/api/v1/forecast-intelligence/" + name
    for name in ("overview", "curve", "hierarchy", "uncertainty", "attribution", "quality")
)
DECISIONS = frozenset(
    "/api/v1/decision-support/" + name
    for name in ("business-loss", "simulate-capacity", "compare-capacity-scenarios")
)
BUSINESS_ACCESS = frozenset(
    "/api/v1/business-access/" + name for name in ("scope", "saved-runs", "selection")
)


class ControlledIngress:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
                return
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        allowed = (
            path in READS
            or path in DECISIONS
            or path in BUSINESS_ACCESS
            or re.fullmatch(
                r"/api/v1/rolling-forecast-runs(?:/compare|/[1-9][0-9]*(?:/daily|/review)?)?", path
            )
            is not None
            or path == "/health/live"
            or path
            in {
                "/api/v1/auth/csrf",
                "/api/v1/auth/login",
                "/api/v1/auth/logout",
                "/api/v1/auth/me",
                "/api/v1/auth/change-password",
            }
            or path.startswith("/api/v1/admin/users")
            or path.startswith("/api/v1/admin/resource-grants")
            or path == "/api/v1/admin/audit-events"
        )
        if not allowed:
            await error(AuthError("FORBIDDEN"))(scope, receive, send)
            return
        await self.app(scope, receive, send)
