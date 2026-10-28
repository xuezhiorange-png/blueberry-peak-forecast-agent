"""Loopback-only test launcher: one owned socket from bind(0) through exit.

No production entry imports this module. Business ASGI and lifespan messages
are forwarded unchanged; the reserved ownership endpoint proves which child
actually answered, not merely that some server is listening on a port.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import uvicorn
from uvicorn.importer import import_from_string

PREFIX = "SYNTHETIC_OWNED_SERVER "


async def probe_app(scope: Any, receive: Any, send: Any) -> None:
    """Lifecycle-test probe only, never a substitute for business responses."""
    if scope["type"] == "lifespan":
        while True:
            event = await receive()
            if event["type"] == "lifespan.startup":
                if os.environ.get("SYNTHETIC_FIXTURE_STDERR"):
                    print(os.environ["SYNTHETIC_FIXTURE_STDERR"], file=sys.stderr, flush=True)
                if os.environ.get("SYNTHETIC_FIXTURE_FAIL_STARTUP") == "1":
                    await send(
                        {"type": "lifespan.startup.failed", "message": "SYNTHETIC_STARTUP_FAILURE"}
                    )
                    return
                await send({"type": "lifespan.startup.complete"})
            elif event["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return
    elif scope["type"] == "http":
        if scope["path"] == "/__owned_probe__/held":
            while (await receive())["type"] != "http.disconnect":
                pass
            return
        await send({"type": "http.response.start", "status": 404, "headers": []})
        await send({"type": "http.response.body", "body": b"SYNTHETIC_LIFECYCLE_PROBE"})


def instrument_app(app: Any, emit: Callable[..., None]) -> Any:
    """Observe ASGI ordering without changing requests, responses or lifespan semantics."""

    async def traced(scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] == "lifespan":

            async def receive_lifespan() -> Any:
                event = await receive()
                if event["type"] in {"lifespan.startup", "lifespan.shutdown"}:
                    emit(event["type"].replace(".", "_").upper() + "_BEGIN")
                return event

            async def send_lifespan(event: Any) -> None:
                if event["type"] in {
                    "lifespan.startup.complete",
                    "lifespan.startup.failed",
                    "lifespan.shutdown.complete",
                    "lifespan.shutdown.failed",
                }:
                    # No failure message: it may contain application data or private paths.
                    emit(event["type"].replace(".", "_").upper())
                await send(event)

            await app(scope, receive_lifespan, send_lifespan)
            return
        if scope["type"] != "http":
            await app(scope, receive, send)
            return
        raw_id = next(
            (v for k, v in scope.get("headers", []) if k.lower() == b"x-e2e-owned-request"), b""
        ).decode("ascii", errors="replace")
        try:
            request_id = str(UUID(raw_id)) if str(UUID(raw_id)) == raw_id else None
        except ValueError:
            request_id = None
        kind = {
            "/__dashboard_test__/authority": "AUTHORITY",
            "/__e2e_owned_server__": "OWNERSHIP",
            "/__owned_probe__/held": "PROBE_HELD",
        }.get(scope["path"], "BUSINESS_HTTP")
        method = scope.get("method")
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
            method = "UNKNOWN"
        metadata = {"request_id": request_id, "request_kind": kind, "method": method}
        status = None
        emit("ASGI_REQUEST_BEGIN", **metadata)

        async def receive_http() -> Any:
            event = await receive()
            if event["type"] == "http.disconnect":
                emit("ASGI_DISCONNECT", **metadata)
            return event

        async def send_http(event: Any) -> None:
            nonlocal status
            if event["type"] == "http.response.start":
                status = event["status"]
            await send(event)

        try:
            await app(scope, receive_http, send_http)
        except BaseException as error:
            emit("ASGI_ERROR", **metadata, error_type=type(error).__name__)
            raise
        finally:
            emit("ASGI_REQUEST_END", **metadata, status=status)

    return traced


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", required=True)
    parser.add_argument("--nonce", required=True)
    args = parser.parse_args()
    if args.app not in {
        "frontend.e2e.support.dashboard_api:app",
        "frontend.e2e.support.s6_api:app",
        "frontend.e2e.support.owned_server:probe_app",
    }:
        parser.error("only explicit isolated test apps are allowed")
    # This socket is NEVER released to probe availability and rebound later.
    # Even import/lifespan failure remains inside this ownership context.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        owner = {"SYNTHETIC": True, "pid": os.getpid(), "nonce": args.nonce, "port": port}

        def emit(phase: str, **metadata: Any) -> None:
            print(
                PREFIX
                + json.dumps(
                    {
                        **metadata,
                        "phase": phase,
                        **owner,
                        "emitted_at_utc": datetime.now(UTC).isoformat(),
                    }
                ),
                flush=True,
            )

        emit("BOUND")
        app = import_from_string(args.app)

        async def owned_app(scope: Any, receive: Any, send: Any) -> None:
            if scope["type"] == "http" and scope["path"] == "/__e2e_owned_server__":
                body = json.dumps(owner).encode()
                await send(
                    {
                        "type": "http.response.start",
                        "status": 200,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"cache-control", b"no-store"),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body})
                return
            await app(scope, receive, send)

        class OwnedServer(uvicorn.Server):
            async def startup(self, sockets: list[socket.socket] | None = None) -> None:
                await super().startup(sockets=sockets)
                if self.started:
                    emit("READY")

            def handle_exit(self, sig: int, frame: Any) -> None:
                emit("SIGNAL_RECEIVED", signal=signal.Signals(sig).name)
                super().handle_exit(sig, frame)

            async def shutdown(self, sockets: list[socket.socket] | None = None) -> None:
                emit("SERVER_SHUTDOWN_BEGIN")
                try:
                    await super().shutdown(sockets=sockets)
                finally:
                    emit("SERVER_SHUTDOWN_END")

        server = OwnedServer(
            uvicorn.Config(instrument_app(owned_app, emit), host="127.0.0.1", port=0, workers=1)
        )
        try:
            server.run(sockets=[listener])
        finally:
            emit("PROCESS_MAIN_RETURN")


if __name__ == "__main__":
    main()
