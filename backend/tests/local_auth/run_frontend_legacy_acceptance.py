"""Run unchanged browser assertions against CI's real synthetic legacy fixtures.

Test-only runner; refuses non-loopback PostgreSQL. Owns its unique database and
server process, and removes only those resources in a finally block.
"""

import asyncio
import os
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path
from uuid import uuid4

import asyncpg
import yaml

ROOT = Path(__file__).resolve().parents[3]


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def check_ready(port):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health/ready", timeout=2) as response:
        assert response.status == 200
        assert response.headers["X-Blueberry-Test-Entry"] == "SYNTHETIC_LEGACY"


async def run():
    assert os.environ["POSTGRES_HOST"] in {"127.0.0.1", "localhost"}
    job = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]["frontend-e2e"]
    name = "blueberry_test_frontend_r3_" + uuid4().hex
    backend_port, frontend_port = free_port(), free_port()
    assert backend_port != frontend_port
    environment = {
        **os.environ,
        **job["env"],
        **{
            key: os.environ[key]
            for key in ("POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_USER", "POSTGRES_PASSWORD")
        },
        "POSTGRES_DB": name,
        "ISOLATED_DB_NAME": name,
        "BLUEBERRY_LEGACY_SYNTHETIC_TEST": "1",
        "TZ": "UTC",
        "DASHBOARD_TEST_PYTHON": str(ROOT / ".venv/bin/python"),
        "PLAYWRIGHT_BASE_URL": f"http://127.0.0.1:{frontend_port}",
        "VITE_TRIAL_API_PROXY_TARGET": f"http://127.0.0.1:{backend_port}",
        "FRONTEND_E2E_XLSX_DIR": "/tmp",
    }
    admin = await asyncpg.connect(
        host=environment["POSTGRES_HOST"],
        port=int(environment["POSTGRES_PORT"]),
        user=environment["POSTGRES_USER"],
        password=environment["POSTGRES_PASSWORD"],
        database="postgres",
    )
    await admin.execute(f'CREATE DATABASE "{name}"')
    server = None
    try:
        await asyncio.to_thread(
            subprocess.run,
            [sys.executable, "-m", "alembic", "-c", "backend/alembic.ini", "upgrade", "head"],
            cwd=ROOT,
            env=environment,
            check=True,
        )
        for step in job["steps"]:
            if step.get("name") in {
                "Seed real Trial authority and import mapping",
                "Generate real XLSX acceptance fixture",
            }:
                await asyncio.to_thread(
                    subprocess.run,
                    ["bash", "-ec", step["run"]],
                    cwd=ROOT,
                    env=environment,
                    check=True,
                )
        server = await asyncio.to_thread(
            subprocess.Popen,
            [
                sys.executable,
                "-m",
                "uvicorn",
                "backend.tests.support.legacy_test_app:create_live_legacy_test_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(backend_port),
            ],
            cwd=ROOT,
            env=environment,
        )
        for _ in range(100):
            assert server.poll() is None, "Owned backend exited"
            try:
                await asyncio.to_thread(check_ready, backend_port)
                break
            except OSError:
                await asyncio.sleep(0.1)
        else:
            raise RuntimeError("Synthetic backend readiness unavailable")
        result = await asyncio.to_thread(
            subprocess.run,
            ["npm", "run", "test:e2e", "--", "--workers=1", *sys.argv[1:]],
            cwd=ROOT / "frontend",
            env=environment,
        )
        return result.returncode
    finally:
        if server is not None and server.poll() is None:
            server.terminate()
            try:
                await asyncio.to_thread(server.wait, timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                await asyncio.to_thread(server.wait)
        if server is not None:
            with socket.socket() as connection:
                assert connection.connect_ex(("127.0.0.1", backend_port)) != 0
            with socket.socket() as connection:
                assert connection.connect_ex(("127.0.0.1", frontend_port)) != 0
        await admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        assert await admin.fetchval("SELECT 1 FROM pg_database WHERE datname=$1", name) is None
        await admin.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
