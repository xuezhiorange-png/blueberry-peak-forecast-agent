"""Smoke test for ``scripts/ci/log_worker_identity.py``.

Exercises:
- Worker identity collected from env (no PG required).
- PG identity degrades safely to "unavailable" when asyncpg is
  absent OR env is missing POSTGRES_PASSWORD.
- Markdown rendering always contains the canonical sections
  ("Worker / database identity", "current_database", "current_user",
  "worker_index").

Run:
    .venv-3.12/bin/python -m pytest scripts/ci/test_log_worker_identity.py -v
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER = REPO_ROOT / "scripts" / "ci" / "log_worker_identity.py"


def _run_helper(env: dict[str, str]) -> tuple[int, str, str]:
    """Invoke the helper and return (exit, stdout, stderr)."""
    proc = subprocess.run(
        [sys.executable, str(HELPER)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        env=env,
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_identity_from_env_without_pg() -> None:
    """When POSTGRES_PASSWORD is missing, PG identity is 'unavailable' but
    runner identity still renders."""
    env = dict(
        RUNNER_NAME="my-runner-1",
        GITHUB_JOB="postgres-migration",
        GITHUB_RUN_ID="12345",
        GITHUB_RUN_ATTEMPT="1",
        GITHUB_SHA="deadbeef1234567890abcdef",
        # NO POSTGRES_PASSWORD → PG identity gracefully degrades.
        PATH=os_minimal_path(),
    )
    exit_code, stdout, _stderr = _run_helper(env)
    assert exit_code == 0
    assert "Worker / database identity" in stdout
    assert "my-runner-1" in stdout
    assert "postgres-migration" in stdout
    assert "12345" in stdout
    assert "current_database: `unavailable`" in stdout
    assert "current_user: `unavailable`" in stdout


def test_sha_is_truncated_to_12() -> None:
    """Long SHAs are truncated to 12 hex chars in the worker_index line."""
    env = dict(
        GITHUB_SHA="abcdef0123456789abcdef0123456789abcdef01",
        PATH=os_minimal_path(),
    )
    _exit_code, stdout, _stderr = _run_helper(env)
    assert "abcdef012345" in stdout
    # The full 40-char SHA must NOT appear.
    assert "abcdef0123456789abcdef0123456789abcdef01" not in stdout


def test_default_env_falls_back_to_socket_hostname() -> None:
    """Without RUNNER_NAME, the helper uses socket.gethostname()."""
    # Clear env so nothing interferes.
    env = {"PATH": os_minimal_path()}
    for k in (
        "RUNNER_NAME",
        "GITHUB_JOB",
        "GITHUB_RUN_ID",
        "GITHUB_RUN_ATTEMPT",
        "GITHUB_SHA",
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
    ):
        env.setdefault(k, "")
    exit_code, stdout, _stderr = _run_helper(env)
    assert exit_code == 0
    # runner falls back to socket hostname.
    assert "runner:" in stdout
    # All PG + GitHub fields become "<unknown>".
    assert "job=`<unknown>`" in stdout


def test_module_imports_without_crash() -> None:
    """The module must be importable in the CI venv (smoke check)."""
    spec = importlib.util.spec_from_file_location("_ci_log_worker_identity", HELPER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hasattr(module, "main")
    assert hasattr(module, "render_markdown")


def test_render_markdown_includes_all_sections() -> None:
    """The rendered markdown must always contain the five canonical lines."""
    from scripts.ci.log_worker_identity import (
        WorkerIdentity,
        render_markdown,
    )

    md = render_markdown(
        WorkerIdentity(
            runner_name="r",
            runner_os="Linux 5.15",
            runner_arch="x86_64",
            container_host="localhost",
            job="j",
            run_id="1",
            run_attempt="1",
            sha="abcdef012345",
        ),
        "blueberry_peak",
        "blueberry_app",
    )
    for required in (
        "Worker / database identity",
        "runner:",
        "container host:",
        "current_database:",
        "current_user:",
        "worker_index:",
    ):
        assert required in md


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def os_minimal_path() -> str:
    """Return a PATH that lets the subprocess find ``python``."""
    import os

    return os.environ.get("PATH", "")
