"""Independent mandatory-auth stateless HTTP MCP application; not production-mounted."""

import anyio
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import Message, Receive, Scope, Send

from backend.app.mcp.forecast_intelligence_auth import (
    AUTH_HEADER,
    MCPServiceConfig,
    authenticate,
    environment_config,
)
from backend.app.mcp.forecast_intelligence_server import (
    RESPONSE_LIMIT,
    SessionFactory,
    create_server,
    database_session,
)

MCP_PATH = "/mcp/forecast-intelligence"
MCP_BODY_LIMIT = 262144
EXECUTION_SECONDS = 30


async def reject(scope: Scope, receive: Receive, send: Send, code: str, status: int) -> None:
    await JSONResponse({"error": {"code": code}}, status_code=status)(scope, receive, send)


class ForecastIntelligenceHTTP:
    def __init__(self, config: MCPServiceConfig | None, session_factory: SessionFactory) -> None:
        self.config = config
        self.session_factory = session_factory

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        config = self.config
        if config is None:
            await reject(scope, receive, send, "AUTHORIZATION_UNAVAILABLE", 503)
            return
        headers = list(scope.get("headers", []))
        account = authenticate(config, headers)
        if account is None:
            await reject(scope, receive, send, "UNAUTHENTICATED", 401)
            return
        hosts = [v.decode("latin1") for k, v in headers if k.lower() == b"host"]
        origins = [v.decode("latin1") for k, v in headers if k.lower() == b"origin"]
        if (
            (config.require_https and scope.get("scheme") != "https")
            or len(hosts) != 1
            or hosts[0] not in config.allowed_hosts
            or len(origins) > 1
            or (origins and origins[0] not in config.allowed_origins)
        ):
            await reject(scope, receive, send, "TRANSPORT_SCOPE_FORBIDDEN", 403)
            return
        # Read the actual stream, not only Content-Length. Disconnect owns cancellation.
        chunks: list[bytes] = []
        size = 0
        try:
            with anyio.fail_after(EXECUTION_SECONDS):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    chunk = message.get("body", b"")
                    size += len(chunk)
                    if size > MCP_BODY_LIMIT:
                        await reject(scope, receive, send, "RESOURCE_LIMIT_EXCEEDED", 413)
                        return
                    chunks.append(chunk)
                    if not message.get("more_body", False):
                        break
                body = b"".join(chunks)
                consumed = False

                async def replay() -> Message:
                    nonlocal consumed
                    if not consumed:
                        consumed = True
                        return {"type": "http.request", "body": body, "more_body": False}
                    return await receive()

                accept = b",".join(v for k, v in headers if k.lower() == b"accept")
                inner_scope = dict(scope)
                # Credential is consumed here, never forwarded to SDK/business contexts.
                headers = [(k, v) for k, v in headers if k.lower() != AUTH_HEADER]
                inner_scope["headers"] = headers
                if not accept.strip() or accept.strip() == b"*/*":
                    inner_scope["headers"] = [
                        (k, v) for k, v in headers if k.lower() != b"accept"
                    ] + [(b"accept", b"application/json")]
                messages: list[Message] = []
                response_size = 0

                async def collect(message: Message) -> None:
                    nonlocal response_size
                    response_size += len(message.get("body", b""))
                    if response_size > RESPONSE_LIMIT:
                        raise ResponseTooLarge
                    messages.append(message)

                manager = StreamableHTTPSessionManager(
                    create_server(account, self.session_factory),
                    stateless=True,
                    json_response=True,
                )
                async with manager.run():
                    await manager.handle_request(inner_scope, replay, collect)
                for message in messages:
                    await send(message)
        except TimeoutError:
            await reject(scope, receive, send, "EXECUTION_TIMEOUT", 503)
        except Exception as exc:
            # TaskGroup may wrap SDK send failures. Never expose nested exception text.
            code = "RESOURCE_LIMIT_EXCEEDED" if contains_limit(exc) else "TRANSPORT_UNAVAILABLE"
            await reject(scope, receive, send, code, 503)


class ResponseTooLarge(Exception):
    pass


def contains_limit(exc: BaseException) -> bool:
    return isinstance(exc, ResponseTooLarge) or (
        isinstance(exc, BaseExceptionGroup) and any(contains_limit(e) for e in exc.exceptions)
    )


def create_forecast_intelligence_app(
    config: MCPServiceConfig | None = None,
    *,
    session_factory: SessionFactory = database_session,
) -> Starlette:
    """Trusted composition only. Environment is independent of legacy connector config."""
    transport = ForecastIntelligenceHTTP(
        config if config is not None else environment_config(),
        session_factory,
    )
    return Starlette(routes=[Route(MCP_PATH, endpoint=transport, methods=["POST"])])
