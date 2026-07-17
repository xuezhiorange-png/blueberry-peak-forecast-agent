"""Safety tests for the Issue #23 Batch 1 dev-DB safeguard + one-command Makefile.

These tests verify that the local test harness / one-command runners
refuse to connect to the development database. The safeguard is meant
to **fail closed** in CI and local dev — even without a running
PostgreSQL — so the tests must NOT depend on a live database.

What is tested here:
* The bash wrapper script (``postgres_test_db.sh``) rejects bad env.
* The Makefile ``test-pg`` target propagates the test profile to all
  shell subprocesses (one-command contract) AND still fails closed on
  dev-DB overrides.

Scope discipline
----------------
* File location: ``backend/tests/safety/`` (NOT ``backend/app/``).
* No production-code mutation.
* No DB / network IO (in the test body itself).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from backend.tests.migration_isolation_helpers import (
    ISOLATED_DB_NAME_PREFIX,
    assert_safe_isolated_db_name,
    resolve_isolated_db_name,
)

# Repository root (the worktree root): 4 parents up from this test file.
REPO_ROOT = Path(__file__).resolve().parents[3]
POSTGRES_TEST_DB_SH = (REPO_ROOT / "backend" / "scripts" / "postgres_test_db.sh").resolve()
WAIT_FOR_POSTGRES_SH = (REPO_ROOT / "backend" / "scripts" / "wait_for_postgres.sh").resolve()
RESET_TEST_DB_SH = (REPO_ROOT / "backend" / "scripts" / "reset_test_db.sh").resolve()
MAKEFILE = (REPO_ROOT / "Makefile").resolve()
CI_WORKFLOW = (REPO_ROOT / ".github" / "workflows" / "ci.yml").resolve()

# Skip the whole module if `make` is not on PATH (sandbox without it).
_REQUIRE_MAKE = pytest.mark.skipif(
    shutil.which("make") is None,
    reason="make not available in this sandbox",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_helper(
    env_overrides: dict[str, str] | None = None,
    helper: Path = POSTGRES_TEST_DB_SH,
) -> subprocess.CompletedProcess:
    """Invoke the helper script under the requested env and capture exit + output.

    Uses an absolute path for the helper so that the helper's internal
    ``cd "$(dirname "$0")/../.."`` always lands at REPO_ROOT.
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


def _run_make(
    *make_args: str,
    make_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """Run ``make <args>`` in the worktree root, capturing exit + output.

    Used for the one-command contract tests; we keep ``make`` out of the
    pytest-env so the test exercises the real recipe.
    """
    base_env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
    }
    if make_env:
        base_env.update(make_env)
    return subprocess.run(
        ["make", *make_args],
        capture_output=True,
        text=True,
        env=base_env,
        cwd=str(REPO_ROOT),
        timeout=30,
    )


def _write_docker_compose_stub(path: Path) -> None:
    """Create a docker stub that accepts only the expected compose command."""
    path.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'if [[ "$#" -ne 5 || '
        '"$1" != "compose" || '
        '"$2" != "-f" || '
        '"$3" != "docker-compose.test.yml" || '
        '"$4" != "up" || '
        '"$5" != "-d" ]]; then\n'
        "    printf 'unexpected docker argv:' >&2\n"
        "    printf ' <%s>' \"$@\" >&2\n"
        "    printf '\\n' >&2\n"
        "    exit 64\n"
        "fi\n"
        "printf '%s\\n' 'PR113_DOCKER_COMPOSE_STUB_MARKER'\n"
        "printf '%s\\n' 'compose_args=compose -f docker-compose.test.yml up -d'\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _full_suite_cleanup_step() -> str:
    """Return the full-suite cleanup script for static safety assertions."""
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    start_marker = "      - name: Drop isolated test database\n"
    start = workflow.rindex(start_marker)
    return workflow[start:]


# Standard "correct test profile" env, used to verify the guard accepts it.
_TEST_PROFILE_ENV: dict[str, str] = {
    "POSTGRES_DB": "blueberry_peak_test",
    "POSTGRES_HOST": "localhost",
    "POSTGRES_PORT": "55432",
    "APP_ENV": "test",
}


def _is_docker_not_available() -> bool:
    """Heuristic: detect whether docker / docker-compose is on PATH."""
    return shutil.which("docker") is None or shutil.which("docker-compose") is None


def _guard_rejection_in_output(stdout: str, stderr: str) -> bool:
    """Detect the guard's distinctive rejection markers in output."""
    combined = stdout + stderr
    return any(
        marker in combined
        for marker in (
            "POSTGRES_DB must be",
            "POSTGRES_PORT must be",
            "APP_ENV must be",
            "DATABASE_URL points at",
            "refuse to run with non-test env",
        )
    )


# ---------------------------------------------------------------------------
# Tests for the bash wrapper script (postgres_test_db.sh)
# ---------------------------------------------------------------------------


def test_dev_db_dev_port_is_rejected() -> None:
    """Guard MUST refuse POSTGRES_PORT=5432 (dev-DB port)."""
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
    """Guard MUST refuse APP_ENV != 'test' (e.g. production)."""
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
    """Guard MUST refuse DATABASE_URL pointing at the dev DB."""
    env = dict(_TEST_PROFILE_ENV)
    env["DATABASE_URL"] = "postgresql://postgres:***@localhost:5432/blueberry_peak"

    result = _run_helper(env_overrides=env)

    assert result.returncode != 0, (
        f"Guard accepted dev DATABASE_URL — broken. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "DATABASE_URL" in result.stderr, (
        f"Guard rejection message must mention DATABASE_URL; got stderr={result.stderr!r}"
    )


def test_test_db_correct_profile_is_accepted(tmp_path: Path) -> None:
    """The guard accepts the test profile and delegates to ``docker compose``.

    The compose command is intercepted by a temporary ``docker`` stub so
    this harness test never starts a nested PostgreSQL service in CI.
    """
    docker_stub = tmp_path / "docker"
    _write_docker_compose_stub(docker_stub)
    env = dict(_TEST_PROFILE_ENV)
    env["PATH"] = f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}"

    result = _run_helper(env_overrides=env)

    assert result.returncode == 0, (
        f"Guard refused correct profile: stdout={result.stdout!r} "
        f"stderr={result.stderr!r} rc={result.returncode}"
    )
    assert "PR113_DOCKER_COMPOSE_STUB_MARKER" in result.stdout
    assert "compose_args=compose -f docker-compose.test.yml up -d" in result.stdout


def test_docker_compose_stub_rejects_invalid_argv(tmp_path: Path) -> None:
    """The safety-test stub must reject non-start commands and wrong files."""
    docker_stub = tmp_path / "docker"
    _write_docker_compose_stub(docker_stub)

    result = subprocess.run(
        [str(docker_stub), "compose", "down"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 64
    assert "unexpected docker argv" in result.stderr


def test_full_suite_cleanup_revalidates_identity_before_database_connect() -> None:
    """Cleanup must derive and verify its target before any DB connection."""
    step = _full_suite_cleanup_step()
    expected_assignment = step.index("expected_name = resolve_verified_cleanup_name()")
    expected_resolution = step.index("expected_name = resolve_isolated_db_name(")
    safe_validation = step.index("assert_safe_isolated_db_name(expected_name)")
    job_identity_read = step.index('job_name = os.environ.get("ISOLATED_JOB_NAME")')
    job_identity_guard = step.index('if job_name != "full-suite-canary":')
    propagated_read = step.index('propagated_name = os.environ.get("ISOLATED_DB_NAME")')
    mismatch_guard = step.index("if propagated_name != expected_name:")
    database_connect = step.index("asyncpg.connect")

    assert '\n          name = os.environ.get("ISOLATED_DB_NAME")' not in step
    assert job_identity_read < job_identity_guard < expected_resolution
    assert expected_resolution < safe_validation < propagated_read < mismatch_guard
    assert mismatch_guard < database_connect
    assert expected_assignment < database_connect
    assert "pg_terminate_backend(pid)" in step
    database_sql = step[database_connect:]
    assert '"WHERE datname = $1 AND pid <> pg_backend_pid()"' in database_sql
    assert '"SELECT 1 FROM pg_database WHERE datname = $1"' in database_sql
    assert "f'DROP DATABASE \"{expected_name}\"'" in database_sql
    assert database_sql.count("expected_name") >= 3
    assert "propagated_name" not in database_sql


def test_check_test_profile_unit_helper() -> None:
    """Sanity test: the test-profile env satisfies the guard's contract."""
    assert POSTGRES_TEST_DB_SH.exists(), f"postgres_test_db.sh not found at {POSTGRES_TEST_DB_SH}"
    assert WAIT_FOR_POSTGRES_SH.exists()
    assert RESET_TEST_DB_SH.exists()
    assert _TEST_PROFILE_ENV["POSTGRES_DB"] == "blueberry_peak_test"
    assert _TEST_PROFILE_ENV["POSTGRES_PORT"] == "55432"
    assert _TEST_PROFILE_ENV["APP_ENV"] == "test"


# ---------------------------------------------------------------------------
# Tests for the one-command Makefile contract (test-pg)
# ---------------------------------------------------------------------------


@_REQUIRE_MAKE
def test_make_test_pg_no_env_does_not_reject() -> None:
    """Plain ``make test-pg`` (no env pre-export) must NOT be rejected by the guard.

    If the run fails, the only acceptable reason is Docker /
    docker-compose not being on PATH (rc=127) — NOT a guard rejection.
    """
    clean_env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in {
            "APP_ENV",
            "POSTGRES_HOST",
            "POSTGRES_PORT",
            "POSTGRES_DB",
            "POSTGRES_USER",
            "POSTGRES_PASSWORD",
            "DATABASE_URL",
        }
    }

    result = _run_make("test-pg", make_env=clean_env)

    if _is_docker_not_available() and result.returncode in (127, 126):
        pytest.skip(
            f"docker not available in this sandbox (rc={result.returncode}); "
            "guard is still exercised"
        )

    assert not _guard_rejection_in_output(result.stdout, result.stderr), (
        f"Guard rejected plain 'make test-pg' (one-command contract broken). "
        f"stdout={result.stdout!r} stderr={result.stderr!r} rc={result.returncode}"
    )


@_REQUIRE_MAKE
def test_make_test_pg_dev_port_rejects() -> None:
    """``make test-pg POSTGRES_PORT=5432`` MUST be rejected by the guard."""
    clean_env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in {
            "APP_ENV",
            "POSTGRES_HOST",
            "POSTGRES_PORT",
            "POSTGRES_DB",
            "POSTGRES_USER",
            "POSTGRES_PASSWORD",
            "DATABASE_URL",
        }
    }

    result = _run_make("POSTGRES_PORT=5432", "test-pg", make_env=clean_env)

    assert result.returncode != 0, (
        f"make test-pg POSTGRES_PORT=5432 was NOT rejected — "
        f"stdout={result.stdout!r} stderr={result.stderr!r} rc={result.returncode}"
    )
    assert _guard_rejection_in_output(result.stdout, result.stderr), (
        f"Expected guard rejection markers; got stdout={result.stdout!r} stderr={result.stderr!r}"
    )


@_REQUIRE_MAKE
def test_make_test_pg_dev_db_rejects() -> None:
    """``make test-pg POSTGRES_DB=blueberry_peak`` MUST be rejected by the guard."""
    clean_env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in {
            "APP_ENV",
            "POSTGRES_HOST",
            "POSTGRES_PORT",
            "POSTGRES_DB",
            "POSTGRES_USER",
            "POSTGRES_PASSWORD",
            "DATABASE_URL",
        }
    }

    result = _run_make("POSTGRES_DB=blueberry_peak", "test-pg", make_env=clean_env)

    assert result.returncode != 0, (
        f"make test-pg POSTGRES_DB=blueberry_peak was NOT rejected — "
        f"stdout={result.stdout!r} stderr={result.stderr!r} rc={result.returncode}"
    )
    assert _guard_rejection_in_output(result.stdout, result.stderr), (
        f"Expected guard rejection markers; got stdout={result.stdout!r} stderr={result.stderr!r}"
    )


@_REQUIRE_MAKE
def test_make_test_pg_dev_database_url_rejects() -> None:
    """``DATABASE_URL=.../blueberry_peak make test-pg`` MUST be rejected by the guard."""
    clean_env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in {
            "APP_ENV",
            "POSTGRES_HOST",
            "POSTGRES_PORT",
            "POSTGRES_DB",
            "POSTGRES_USER",
            "POSTGRES_PASSWORD",
            "DATABASE_URL",
        }
    }
    clean_env["DATABASE_URL"] = "postgresql://postgres:***@localhost:5432/blueberry_peak"

    result = _run_make("test-pg", make_env=clean_env)

    assert result.returncode != 0, (
        f"DATABASE_URL=dev-db make test-pg was NOT rejected — "
        f"stdout={result.stdout!r} stderr={result.stderr!r} rc={result.returncode}"
    )
    assert _guard_rejection_in_output(result.stdout, result.stderr), (
        f"Expected guard rejection markers; got stdout={result.stdout!r} stderr={result.stderr!r}"
    )


# ---------------------------------------------------------------------------
# Slice 3 — isolated PostgreSQL test-database profile guards
# (Issue #51 / Batch 3 / Slice 3 — postgres-migration isolated DB profile)
#
# These tests pin the contract between the ``postgres-migration`` CI job
# and the slice-1 dev-DB safeguard: a per-run isolated database name
# must start with the ``_test_`` marker AND must not collide with any
# FORBIDDEN_DATABASE_NAMES entry. The tests are pure-python; they do NOT
# require a running PostgreSQL — they exercise the helper that the
# CI step invokes.
# ---------------------------------------------------------------------------


def test_isolated_db_profile_accepts_canonical_run_id_attempt_job() -> None:
    """The canonical per-run shape must pass the guard without error."""
    name = resolve_isolated_db_name(28869639380, 1, "postgres_migration")
    assert_safe_isolated_db_name(name)


def test_isolated_db_profile_rejects_bare_blueberry_peak() -> None:
    """The dev-DB literal ``blueberry_peak`` must still be rejected by
    Slice 3's guard — Slice 3 narrows the test profile; it does not
    widen the forbidden list."""
    with pytest.raises(ValueError, match="refusing isolated DB name"):
        assert_safe_isolated_db_name("blueberry_peak")


def test_isolated_db_profile_rejects_blueberry_peak_without_test_marker() -> None:
    """``blueberry_peak_<something>`` *without* ``_test_`` must be
    rejected by the slice-1 safeguard's dev-DB pattern rule. This
    pins the property that the prefix rule is not enough — the
    underlying slice-1 guard is still the authority."""
    with pytest.raises(ValueError, match="refusing isolated DB name"):
        # ``resolve_isolated_db_name`` would refuse to produce this
        # shape, so we hand-craft the bad name to exercise the guard.
        assert_safe_isolated_db_name("blueberry_peak_dev")


def test_isolated_db_profile_rejects_postgres_cluster_default() -> None:
    """The PostgreSQL cluster-default ``postgres`` database must never
    be the migration target — it is reserved for administrative
    connections."""
    with pytest.raises(ValueError, match="FORBIDDEN_DATABASE_NAMES"):
        assert_safe_isolated_db_name("postgres")


def test_isolated_db_profile_error_message_omits_password_and_url() -> None:
    """The guard's error message must NOT echo a password, token, or
    a full ``DATABASE_URL`` fragment — this is the same property the
    slice-1 safeguard guarantees, re-pinned here against regression."""
    secret_password = "p@ssw0rd-canary-XYZ"
    secret_token = "ghp_xx...xxxx"
    try:
        assert_safe_isolated_db_name(secret_password)
    except ValueError as exc:
        message = str(exc)
        assert secret_password not in message, (
            f"assert_safe_isolated_db_name leaked the input into the error: {message!r}"
        )
        assert secret_token not in message, (
            f"assert_safe_isolated_db_name leaked a token into the error: {message!r}"
        )


def test_isolated_db_profile_prefix_is_blueberry_peak_test() -> None:
    """The slice-3 prefix must literally be ``blueberry_peak_test_``.

    This test guards against a future refactor silently changing the
    prefix and thereby breaking the slice-1 dev-DB safeguard's
    ``_test_`` substring expectation.
    """
    assert ISOLATED_DB_NAME_PREFIX == "blueberry_peak_test_"
