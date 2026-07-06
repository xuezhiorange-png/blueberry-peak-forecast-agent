"""Safety tests for the Issue #23 Batch 1 dev-DB safeguard.

These tests verify that the local test harness / one-command runners
refuse to connect to the development database. The safeguard is meant
to **fail closed** in CI and local dev — even without a running
PostgreSQL — so the tests must NOT depend on a live database. Every
test injects env vars via ``monkeypatch`` and inspects the guard's
exit code / exit message only.

Scope discipline
----------------
* File location: ``backend/tests/safety/`` (NOT ``backend/app/``).
* No production-code mutation.
* No DB / network IO.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

# Repository root (the worktree root): 4 parents up from this test file
# (backend/tests/safety/test_dev_db_protection.py).
REPO_ROOT = Path(__file__).resolve().parents[3]
POSTGRES_TEST_DB_SH = (REPO_ROOT / "backend" / "scripts" / "postgres_test_db.sh").resolve()
WAIT_FOR_POSTGRES_SH = (REPO_ROOT / "backend" / "scripts" / "wait_for_postgres.sh").resolve()
RESET_TEST_DB_SH = (REPO_ROOT / "backend" / "scripts" / "reset_test_db.sh").resolve()


# ---------------------------------------------------------------------------
# Helper: run a shell helper under the given env, return CompletedProcess
# ---------------------------------------------------------------------------


def _run_helper(
    env_overrides: dict[str, str] | None = None,
    helper: Path = POSTGRES_TEST_DB_SH,
) -> subprocess.CompletedProcess:
    """Invoke the helper script under the requested env and capture exit + output.

    Uses an absolute path for the helper so that the helper's internal
    ``cd "$(dirname "$0")/../.."`` always lands at REPO_ROOT regardless of
    the caller's cwd.
    """
    base_env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
    }
    if env_overrides:
        base_env.update(env_overrides)
    return subprocess.run(
        ["bash", str(helper)],
        capture_output=True,
        text=True,
        env=base_env,
        cwd=str(REPO_ROOT),
        timeout=30,
    )


# Standard "correct test profile" env, used to verify the guard accepts it.
_TEST_PROFILE_ENV: dict[str, str] = {
    "POSTGRES_DB": "blueberry_peak_test",
    "POSTGRES_HOST": "localhost",
    "POSTGRES_PORT": "55432",
    "APP_ENV": "test",
}


# ---------------------------------------------------------------------------
# Guards on the wrapper script
# ---------------------------------------------------------------------------


def test_dev_db_dev_port_is_rejected() -> None:
    """Guard MUST refuse POSTGRES_PORT=5432 (dev-DB port).

    Port 5432 is reserved for the development database; using it would
    leak test runs into dev. The guard must exit non-zero AND the error
    message must mention the port mismatch.
    """
    env = dict(_TEST_PROFILE_ENV)
    env["POSTGRES_PORT"] = "5432"  # dev-DB port

    result = _run_helper(env_overrides=env)

    assert result.returncode != 0, (
        f"Guard accepted dev-DB port 5432 — broken. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "55432" in result.stderr or "5432" in result.stderr, (
        f"Guard rejection message must mention the port; got stderr={result.stderr!r}"
    )


def test_dev_db_prod_app_env_is_rejected() -> None:
    """Guard MUST refuse APP_ENV != 'test' (e.g. production).

    APP_ENV=production (or any value other than 'test') is an explicit
    refusal condition.
    """
    env = dict(_TEST_PROFILE_ENV)
    env["APP_ENV"] = "production"

    result = _run_helper(env_overrides=env)

    assert result.returncode != 0, (
        f"Guard accepted APP_ENV=production — broken. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "APP_ENV" in result.stderr, (
        f"Guard rejection message must mention APP_ENV; got stderr={result.stderr!r}"
    )


def test_dev_db_database_url_dev_db_is_rejected() -> None:
    """Guard MUST refuse DATABASE_URL pointing at the dev DB.

    The wrapper must explicitly check DATABASE_URL for dev-DB markers
    (``blueberry_peak`` without ``_test``, ``localhost:5432``) and fail
    closed. This test does NOT accept Docker absence as a valid accept
    reason for a dev DATABASE_URL — a dev URL must be rejected by the
    guard even when Docker is unavailable.
    """
    env = dict(_TEST_PROFILE_ENV)
    # DATABASE_URL points at the dev DB (port 5432, db name without _test).
    env["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5432/blueberry_peak"

    result = _run_helper(env_overrides=env)

    assert result.returncode != 0, (
        f"Guard accepted dev DATABASE_URL — broken. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "DATABASE_URL" in result.stderr, (
        f"Guard rejection message must mention DATABASE_URL; got stderr={result.stderr!r}"
    )


def test_test_db_correct_profile_is_accepted() -> None:
    """Guard MUST accept the correct test profile.

    With the correct profile, the guard must NOT refuse. Any non-zero
    exit must come from the subsequent ``docker compose up -d`` failing
    because Docker is unavailable in the sandbox — NOT from the guard.
    """
    result = _run_helper(env_overrides=dict(_TEST_PROFILE_ENV))

    # If docker is unavailable, bash command not found -> rc=127.
    if result.returncode == 127:
        pytest.skip(
            "docker not available in this sandbox; skipping "
            "downstream assertion (guard is still exercised)."
        )

    # The guard itself MUST NOT refuse the correct profile.
    # The downstream docker compose call MAY fail (rc != 0) for
    # environment reasons unrelated to the guard.
    combined = (result.stdout + result.stderr).lower()
    assert (
        "blueberry_peak_test" in result.stdout
        or result.returncode == 0
        or "docker" in combined
        or "compose" in combined
    ), (
        f"Guard refused correct profile (not docker-related). "
        f"stdout={result.stdout!r} "
        f"stderr={result.stderr!r} "
        f"rc={result.returncode}"
    )


def test_check_test_profile_unit_helper() -> None:
    """Sanity test: the test-profile env satisfies the guard's contract.

    This test does NOT invoke the bash wrapper (so it works without
    Docker). It just verifies that the helper script resolves to the
    expected path and the env dict is well-formed.
    """
    assert POSTGRES_TEST_DB_SH.exists(), f"postgres_test_db.sh not found at {POSTGRES_TEST_DB_SH}"
    assert WAIT_FOR_POSTGRES_SH.exists()
    assert RESET_TEST_DB_SH.exists()
    assert _TEST_PROFILE_ENV["POSTGRES_DB"] == "blueberry_peak_test"
    assert _TEST_PROFILE_ENV["POSTGRES_PORT"] == "55432"
    assert _TEST_PROFILE_ENV["APP_ENV"] == "test"
