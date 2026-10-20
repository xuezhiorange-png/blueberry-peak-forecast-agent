"""Loopback-only test launcher: one owned socket from bind(0) through exit.

No production entry imports this module. Business ASGI and lifespan messages
are forwarded unchanged; the reserved ownership endpoint proves which child
actually answered, not merely that some server is listening on a port.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
from typing import Any

import uvicorn
from uvicorn.importer import import_from_string

PREFIX = "SYNTHETIC_OWNED_SERVER "


async def probe_app(scope: Any, receive: Any, send: Any) -> None:
    """Lifecycle-test probe only, never a substitute for business responses."""
    if scope["type"] == "lifespan":
        while True:
            event = await receive()
            if event["type"] == "lifespan.startup":
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
        await send({"type": "http.response.start", "status": 404, "headers": []})
        await send({"type": "http.response.body", "body": b"SYNTHETIC_LIFECYCLE_PROBE"})


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

        def emit(phase: str) -> None:
            print(PREFIX + json.dumps({"phase": phase, **owner}), flush=True)

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

        server = OwnedServer(uvicorn.Config(owned_app, host="127.0.0.1", port=0, workers=1))
        server.run(sockets=[listener])


if __name__ == "__main__":
    main()
