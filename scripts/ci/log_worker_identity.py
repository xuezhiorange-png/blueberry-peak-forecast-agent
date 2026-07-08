"""Log GitHub Actions runner + PostgreSQL worker / database identity.

Batch 6 (Issue #54 / Issue #23 sub-area 6) — CI diagnostics helper.

Logs:
- GitHub Actions runner name (host of the runner VM).
- PostgreSQL service container host (best-effort, from env).
- PostgreSQL ``current_database()`` and ``current_user()`` via asyncpg.
- Worker / shard identity: ``github.job``, ``github.run_id``,
  ``github.run_attempt``, ``github.sha``.

Output is markdown suitable for ``$GITHUB_STEP_SUMMARY``. The script
never raises — any PG connection failure degrades to a friendly
"(PG identity unavailable)" note so the CI step itself never fails.

The PG connection uses the env vars already set by the GitHub Actions
service container:
    POSTGRES_HOST  (default ``localhost``)
    POSTGRES_PORT  (default ``5432``)
    POSTGRES_DB    (default ``blueberry_peak``)
    POSTGRES_USER  (default ``blueberry_app``)
    POSTGRES_PASSWORD  (no default — required for service auth)

If any of POSTGRES_HOST / POSTGRES_PORT / POSTGRES_DB / POSTGRES_USER /
POSTGRES_PASSWORD is missing, the PG-identity section is skipped
gracefully (no crash) — the runner / worker identity is still logged.

Run:
    python scripts/ci/log_worker_identity.py
"""

from __future__ import annotations

import asyncio
import os
import platform
import socket
import sys
from typing import NamedTuple

# Best-effort import — asyncpg is a project runtime dep so it is always
# installed in the CI venv, but tolerate its absence for local smoke.
try:
    import asyncpg  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover — covered by CI env
    asyncpg = None


class WorkerIdentity(NamedTuple):
    runner_name: str
    runner_os: str
    runner_arch: str
    container_host: str
    job: str
    run_id: str
    run_attempt: str
    sha: str


def _collect_worker_identity() -> WorkerIdentity:
    def _env_or(key: str, default: str) -> str:
        value = os.environ.get(key, default)
        return value if value else default

    return WorkerIdentity(
        runner_name=_env_or("RUNNER_NAME", socket.gethostname()),
        runner_os=f"{platform.system()} {platform.release()}",
        runner_arch=platform.machine(),
        # Service container host — the GitHub Actions runner maps the
        # ``postgres`` service hostname to ``localhost`` on the runner
        # VM itself, so we surface the resolved connection target.
        container_host=_env_or("POSTGRES_HOST", "localhost"),
        job=_env_or("GITHUB_JOB", "<unknown>"),
        run_id=_env_or("GITHUB_RUN_ID", "<unknown>"),
        run_attempt=_env_or("GITHUB_RUN_ATTEMPT", "<unknown>"),
        sha=(_env_or("GITHUB_SHA", "<unknown>"))[:12],
    )


async def _query_pg_identity() -> tuple[str, str]:
    """Return ``(current_database, current_user)`` from a fresh connection.

    Returns ``(unavailable, unavailable)`` on any failure so the caller
    can degrade gracefully.
    """
    if asyncpg is None:
        return ("unavailable", "unavailable")
    try:
        host = os.environ.get("POSTGRES_HOST", "localhost")
        port = int(os.environ.get("POSTGRES_PORT", "5432"))
        db = os.environ.get("POSTGRES_DB", "blueberry_peak")
        user = os.environ.get("POSTGRES_USER", "blueberry_app")
        password = os.environ.get("POSTGRES_PASSWORD", "")
        if not password:
            return ("unavailable", "unavailable")
        conn = await asyncpg.connect(
            host=host, port=port, database=db, user=user, password=password
        )
        try:
            current_db = await conn.fetchval("SELECT current_database()")
            current_user = await conn.fetchval("SELECT current_user")
        finally:
            await conn.close()
    except Exception:
        return ("unavailable", "unavailable")
    return str(current_db), str(current_user)


def render_markdown(identity: WorkerIdentity, pg_db: str, pg_user: str) -> str:
    lines = [
        "### Worker / database identity",
        f"* runner: `{identity.runner_name}` ({identity.runner_os} / {identity.runner_arch})",
        f"* container host: `{identity.container_host}`",
        f"* current_database: `{pg_db}`",
        f"* current_user: `{pg_user}`",
        "* worker_index: "
        f"job=`{identity.job}` run_id=`{identity.run_id}` "
        f"attempt=`{identity.run_attempt}` sha=`{identity.sha}`",
    ]
    return "\n".join(lines)


def main() -> int:
    identity = _collect_worker_identity()
    pg_db, pg_user = asyncio.run(_query_pg_identity())
    sys.stdout.write(render_markdown(identity, pg_db, pg_user) + "\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
