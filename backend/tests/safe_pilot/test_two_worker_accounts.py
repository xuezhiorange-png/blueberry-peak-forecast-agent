"""Two actual POSIX MCP worker processes share policy and canonical PostgreSQL."""

import asyncio
import hashlib
import multiprocessing
import os
import socket
import ssl
import subprocess
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import httpx2
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pydantic import SecretStr
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.forecast_intelligence.read_service import ForecastIntelligenceReadService
from backend.app.mcp.forecast_intelligence_http import MCP_PATH
from backend.app.models.operational_peak import OperationalPeakForecastRun
from backend.tests.mcp.test_v0_17_s3_productization import HEADER, KEY, account, grant_for
from backend.tests.mcp.test_v0_18_s3_policy import document, policy
from backend.tests.safe_pilot.test_restore_and_ingress import seed

pytestmark = pytest.mark.postgres
OTHER_KEY = "SYNTHETIC_TWO_WORKER_OTHER"
ROTATED_KEY = "SYNTHETIC_TWO_WORKER_ROTATED"


def worker(listener, database_url, policy_path, certificate, key, ready, reads, log):
    """Trusted test composition only; no production entry imports this module."""
    import uvicorn

    from backend.app.db import session
    from backend.app.mcp.forecast_intelligence_http import create_service_account_app

    async def serve():
        engine = create_async_engine(database_url)
        session.AsyncSessionMaker = async_sessionmaker(engine, expire_on_commit=False)
        os.environ["FORECAST_INTELLIGENCE_MCP_POLICY_FILE"] = str(policy_path)

        @event.listens_for(engine.sync_engine, "before_cursor_execute")
        def observe(connection, cursor, statement, parameters, context, many):
            del connection, cursor, parameters, context, many
            if "operational_peak_forecast" in statement.lower():
                with reads.get_lock():
                    reads.value += 1

        class ReadyServer(uvicorn.Server):
            async def startup(self, sockets=None):
                await super().startup(sockets=sockets)
                if self.started:
                    ready.set()

        server = ReadyServer(
            uvicorn.Config(
                create_service_account_app(),
                ssl_certfile=str(certificate),
                ssl_keyfile=str(key),
                proxy_headers=False,
                access_log=False,
                lifespan="off",
                log_level="warning",
                timeout_graceful_shutdown=1,
            )
        )

        try:
            await server.serve(sockets=[listener])
        finally:
            await engine.dispose()

    with Path(log).open("w") as output, redirect_stdout(output), redirect_stderr(output):
        asyncio.run(serve())


async def test_two_posix_sdk_workers_never_mix_accounts_and_refresh_policy(
    pg_auth,
    tmp_path,
    record_property,
):
    _, factory, _, user, _ = pg_auth
    first_query, _ = await seed(factory, user)
    async with factory() as db:
        row = await db.scalar(
            select(OperationalPeakForecastRun).where(
                OperationalPeakForecastRun.base_id == "SYNTHETIC_S5_OTHER_BASE"
            )
        )
        other_query = first_query.model_copy(
            update={
                "run_id": row.id,
                "entity_id": row.base_id,
                "expected_source_result_hash": row.result_hash,
            }
        )
        first = await ForecastIntelligenceReadService(db).curve(first_query)
        second = await ForecastIntelligenceReadService(db).curve(other_query)
    cert, key = tmp_path / "SYNTHETIC.crt", tmp_path / "SYNTHETIC.key"
    completed = await asyncio.to_thread(
        subprocess.run,
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=SYNTHETIC_ONLY",
            "-addext",
            "subjectAltName=IP:127.0.0.1",
            "-keyout",
            str(key),
            "-out",
            str(cert),
        ],
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0
    key.chmod(0o600)
    listeners = [socket.socket(), socket.socket()]
    for listener in listeners:
        listener.bind(("127.0.0.1", 0))
    ports = [s.getsockname()[1] for s in listeners]
    hosts = tuple(f"127.0.0.1:{p}" for p in ports)
    provider = policy(tmp_path)
    accounts = (
        account(run_grants=(grant_for(first),)),
        account(
            principal_id="SYNTHETIC_OTHER",
            secret=SecretStr(OTHER_KEY),
            quality_grants=(),
            run_grants=(grant_for(second, principal_id="SYNTHETIC_OTHER"),),
        ),
    )
    provider.publish(document(2, accounts=accounts, allowed_hosts=hosts))
    ctx = multiprocessing.get_context("spawn")
    ready = [ctx.Event(), ctx.Event()]
    counts = [ctx.Value("i", 0), ctx.Value("i", 0)]
    processes = [
        ctx.Process(
            target=worker,
            args=(
                listener,
                factory.kw["bind"].url.render_as_string(hide_password=False),
                provider.path,
                cert,
                key,
                ready[i],
                counts[i],
                tmp_path / f"SYNTHETIC-worker-{i}.log",
            ),
        )
        for i, listener in enumerate(listeners)
    ]
    try:
        for process in processes:
            process.start()
        assert all(await asyncio.gather(*(asyncio.to_thread(v.wait, 15) for v in ready)))
        assert len({p.pid for p in processes}) == 2 and os.getpid() not in {
            p.pid for p in processes
        }
        context = ssl.create_default_context(cafile=str(cert))

        async def invoke(worker_index, principal, *, denied_only=False, rotated=False):
            credential = (ROTATED_KEY if rotated else KEY) if principal == 0 else OTHER_KEY
            own, foreign = (
                (first_query, other_query) if principal == 0 else (other_query, first_query)
            )
            async with httpx2.AsyncClient(
                verify=context, trust_env=False, headers={HEADER: credential}
            ) as http:
                async with streamable_http_client(
                    f"https://{hosts[worker_index]}" + MCP_PATH, http_client=http
                ) as streams:
                    async with ClientSession(streams[0], streams[1]) as sdk:
                        await sdk.initialize()
                        denied = await sdk.call_tool(
                            "get_forecast_curve", foreign.model_dump(mode="json")
                        )
                        assert denied.is_error and denied.structured_content["code"] == "FORBIDDEN"
                        if not denied_only:
                            actual = await sdk.call_tool(
                                "get_forecast_curve", own.model_dump(mode="json")
                            )
                            assert not actual.is_error
                            assert actual.structured_content == (
                                first if principal == 0 else second
                            ).model_dump(mode="json")

        await asyncio.gather(*(invoke(w, p, denied_only=True) for w in range(2) for p in range(2)))
        assert [v.value for v in counts] == [0, 0]
        await asyncio.gather(*(invoke(w, p) for w in range(2) for p in range(2)))
        assert all(v.value > 0 for v in counts)
        provider.publish(
            document(
                3,
                allowed_hosts=hosts,
                accounts=(
                    accounts[0].model_copy(update={"secret": SecretStr(ROTATED_KEY)}),
                    accounts[1],
                ),
            )
        )
        for host in hosts:
            async with httpx2.AsyncClient(verify=context, trust_env=False) as http:
                assert (
                    await http.post(f"https://{host}" + MCP_PATH, json={}, headers={HEADER: KEY})
                ).status_code == 401
        await asyncio.gather(*(invoke(w, p, rotated=True) for w in range(2) for p in range(2)))
        record_property("worker_pids", str([p.pid for p in processes]))
        record_property("unauthorized_business_reads_before_legitimate_calls", "0")
        source = await asyncio.to_thread(Path(__file__).read_bytes)
        record_property("test_source_sha256", hashlib.sha256(source).hexdigest())
    finally:
        for process in processes:
            if process.pid is not None:
                process.terminate()  # only these exact test-created Process objects
        for process in processes:
            if process.pid is not None:
                await asyncio.to_thread(process.join, 10)
                if process.is_alive():
                    process.kill()
                    await asyncio.to_thread(process.join, 5)
                    pytest.fail("SYNTHETIC_WORKER_DID_NOT_SHUT_DOWN")
                assert process.exitcode in (0, -15)
        for listener in listeners:
            listener.close()
        for port in ports:
            with socket.socket() as probe:
                assert probe.connect_ex(("127.0.0.1", port)) != 0
