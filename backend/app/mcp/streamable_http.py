"""Doubao inbound POST JSON-RPC, sharing the unchanged stdio tool server.

Adapted from cold-storage Aily's stateless JSON response pattern. This project's
SDK provides the born-ready stateless connection via its public session manager;
its Server.run no longer accepts the older stateless=True argument.
"""

from hmac import compare_digest

from fastapi import FastAPI
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from backend.app.core.config import AppSettings
from backend.app.mcp.area_forecast import server

MCP_PATH = "/api/v1/blueberry/v1/mcp/sse"
MCP_ALIAS_PATH = "/api/v1/blueberry/v1/mcp"
CONNECTOR_HEADER = "X-Blueberry-Connector-Key"


class BlueberryMCPHTTP:
    """One transport per POST, no retained session, event store or GET SSE stream."""

    def __init__(self, settings: AppSettings) -> None:
        self._secret = settings.blueberry_mcp_connector_shared_secret

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        headers = list(scope.get("headers", []))
        secret = self._secret.get_secret_value().encode("utf-8")
        supplied = [value for key, value in headers if key.lower() == b"x-blueberry-connector-key"]
        if secret and (len(supplied) != 1 or not compare_digest(supplied[0], secret)):
            await JSONResponse(
                {"error": {"code": "BLUEBERRY_MCP_CONNECTOR_UNAUTHORIZED"}}, status_code=401
            )(scope, receive, send)
            return
        accept = b",".join(value for key, value in headers if key.lower() == b"accept")
        # Content-Type-only clients (and curl's */*) need JSON negotiation. Do
        # not override an explicit incompatible Accept.
        if not accept.strip() or accept.strip() == b"*/*":
            scope = dict(scope)
            scope["headers"] = [(k, v) for k, v in headers if k.lower() != b"accept"] + [
                (b"accept", b"application/json")
            ]
        # Like the reference, isolate each POST's transport lifetime. The SDK
        # constructs StreamableHTTPServerTransport(None, JSON=True, event_store=None)
        # and owns cancellation/termination. No engine, tool or model is rebuilt.
        manager = StreamableHTTPSessionManager(server, stateless=True, json_response=True)
        async with manager.run():
            await manager.handle_request(scope, receive, send)


def mount_blueberry_mcp(app: FastAPI, settings: AppSettings) -> None:
    transport = BlueberryMCPHTTP(settings)
    # Exact ASGI routes avoid Mount's trailing-slash redirect on the alias URL.
    # Both accepted URLs dispatch to the same ASGI app and same MCP Server.
    app.router.routes.extend(
        Route(path, endpoint=transport, methods=["POST"]) for path in (MCP_PATH, MCP_ALIAS_PATH)
    )
