"""Owned loopback TLS launcher for real S4/S6 apps, never production-mounted."""

import argparse
import asyncio
import json
import os
import signal
import socket
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from types import FrameType
from typing import Any

PREFIX = "SYNTHETIC_HTTPS_LIFECYCLE "


Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]


async def probe(scope: Any, receive: Receive, send: Send) -> None:
    """Lifecycle-only negative control, not a business response substitute."""
    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                gate = os.environ.get("SYNTHETIC_HTTPS_START_GATE_PORT")
                if gate:
                    reader, writer = await asyncio.open_connection("127.0.0.1", int(gate))
                    try:
                        await reader.readexactly(1)
                    finally:
                        writer.close()
                        await writer.wait_closed()
                if os.environ.get("SYNTHETIC_HTTPS_FAIL_START") == "1":
                    await send({"type": "lifespan.startup.failed", "message": "PROBE_START_RED"})
                    return
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                if os.environ.get("SYNTHETIC_HTTPS_FAIL_STOP") == "1":
                    await send({"type": "lifespan.shutdown.failed", "message": "PROBE_STOP_RED"})
                else:
                    await send({"type": "lifespan.shutdown.complete"})
                return
    else:
        await send({"type": "http.response.start", "status": 404, "headers": []})
        await send({"type": "http.response.body", "body": b"SYNTHETIC_PROBE_ONLY"})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--app", required=True, choices=["business_pg", "acceptance_s6_pg", "probe"]
    )
    parser.add_argument("--nonce", required=True)
    parser.add_argument("--cert", required=True)
    parser.add_argument("--key", required=True)
    args = parser.parse_args()
    assert os.environ.get("S4_SYNTHETIC_ONLY") == "1"
    stopped = False
    server: Any = None

    def request_stop(number: int, frame: FrameType | None) -> None:
        nonlocal stopped
        del number, frame
        stopped = True
        # SIG_IGN survives Python interpreter finalization. A late duplicate
        # must not turn already-verified cleanup into a signal-terminated exit.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        if server is not None:
            server.should_exit = True

    # Install before expensive imports. Repeated signals request shutdown but
    # never interrupt lifespan cleanup or escalate to force_exit.
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        origin = f"https://127.0.0.1:{port}"
        owner = {"SYNTHETIC": True, "pid": os.getpid(), "nonce": args.nonce, "port": port}

        def emit(phase: str, **fields: Any) -> None:
            print(PREFIX + json.dumps(dict(owner, phase=phase, **fields)), flush=True)

        emit("BOUND")
        os.environ["S4_HTTPS_ORIGIN"] = origin
        import uvicorn
        from uvicorn.importer import import_from_string

        app = (
            probe
            if args.app == "probe"
            else import_from_string(f"frontend.e2e.support.{args.app}:app")
        )
        database: str | None = None
        mcp_port: int | None = None

        async def verify_cleanup() -> dict[str, Any]:
            if args.app == "probe":
                return {"postgres": "NOT_APPLICABLE", "tls_mcp": "NOT_APPLICABLE"}
            import asyncpg

            assert database and database.startswith("blueberry_peak_test_s4_")
            conn = await asyncpg.connect(
                host=os.environ["POSTGRES_HOST"],
                port=int(os.environ["POSTGRES_PORT"]),
                user=os.environ["POSTGRES_USER"],
                password=os.environ["POSTGRES_PASSWORD"],
                database="postgres",
                timeout=5,
            )
            try:
                assert not await conn.fetchval(
                    "SELECT 1 FROM pg_database WHERE datname=$1", database
                )
            finally:
                await conn.close()
            if mcp_port is not None:
                try:
                    _, writer = await asyncio.wait_for(
                        asyncio.open_connection("127.0.0.1", mcp_port), 2
                    )
                except ConnectionRefusedError:
                    pass
                else:
                    writer.close()
                    await writer.wait_closed()
                    raise AssertionError("NESTED_TLS_MCP_LISTENER_STILL_OPEN")
            return {
                "postgres": "ABSENT_VERIFIED",
                "database": database,
                "tls_mcp": "CLOSED_VERIFIED" if mcp_port else "NOT_APPLICABLE",
            }

        async def wrapped(scope: Any, receive: Receive, send: Send) -> None:
            nonlocal database, mcp_port
            if scope["type"] == "http" and scope["path"] == "/__e2e_https_owner__":
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

            async def observe_receive() -> dict[str, Any]:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    emit("LIFESPAN_START")
                elif message["type"] == "lifespan.shutdown":
                    emit("LIFESPAN_STOP")
                return message

            async def observe_send(message: dict[str, Any]) -> None:
                nonlocal database, mcp_port
                if message["type"] == "lifespan.startup.complete":
                    if args.app != "probe":
                        from frontend.e2e.support import business_pg

                        observed_database: object = business_pg.STATE["database"]
                        assert isinstance(observed_database, str)
                        database = observed_database
                        nested = getattr(business_pg.outer.state, "s6_mcp", None)
                        if nested:
                            from urllib.parse import urlsplit

                            mcp_port = urlsplit(nested[0]).port
                    emit("LIFESPAN_READY")
                elif message["type"] == "lifespan.shutdown.complete":
                    emit("CLEANUP_VERIFIED", **await verify_cleanup())
                elif message["type"].endswith(".failed"):
                    emit("LIFESPAN_FAILED", event=message["type"])
                await send(message)

            await app(scope, observe_receive, observe_send)

        class OwnedTLS(uvicorn.Server):
            @contextmanager
            def capture_signals(self) -> Iterator[None]:
                # Do not re-raise received signals after graceful cleanup.
                yield

            async def startup(self, sockets: list[socket.socket] | None = None) -> None:
                await super().startup(sockets=sockets)
                if self.started:
                    if stopped:
                        # Older Uvicorn versions can return directly after a
                        # cancelled startup. Finalize acquired lifespan here.
                        await self.shutdown(sockets=sockets)
                        self.started = False
                    else:
                        emit("READY")

        server = OwnedTLS(
            uvicorn.Config(
                wrapped,
                host="127.0.0.1",
                port=0,
                lifespan="on",
                ssl_certfile=args.cert,
                ssl_keyfile=args.key,
                proxy_headers=False,
                access_log=False,
                timeout_graceful_shutdown=10,
            )
        )
        server.should_exit = stopped
        server.run(sockets=[listener])
    emit("SOCKET_CLOSED")


if __name__ == "__main__":
    main()
