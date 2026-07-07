"""Safety tests for the Batch 3 Slice 1 dev-DB safeguard + identity logging baseline.

This module extends ``backend/tests/safety/test_dev_db_protection.py``
(Batch 1 deliverable) with the Batch 3 Slice 1 tests, which exercise
the pure validator in :mod:`backend.tests.postgres_test_support`.

What is tested here (Slice 1 additions):

* The pure resolver returns the expected identity for a safe profile.
* The pure validator rejects every unsafe profile variant
  (dev-DB name / dev-DB port / production APP_ENV / unsafe
  DATABASE_URL / silent fallback).
* The pure validator accepts every documented safe profile variant.
* The one-line formatter never includes ``DATABASE_URL`` value or
  any token-shaped substring.
* The validator is independent of DB / network IO (no
  ``asyncpg``, no subprocess, no Docker).

Scope discipline:

* File location: ``backend/tests/safety/`` (NOT ``backend/app/``).
* No production-code mutation.
* No DB / network IO (in the test body itself).
* No token / password / DATABASE_URL value echoed in assertions.
"""

from __future__ import annotations

import pytest

from backend.tests.postgres_test_support import (
    DEFAULT_TEST_APP_ENV,
    DEFAULT_TEST_DB_HOST,
    DEFAULT_TEST_DB_NAME,
    DEFAULT_TEST_DB_PORT,
    FORBIDDEN_DATABASE_NAMES,
    FORBIDDEN_DATABASE_PORTS,
    PRODUCTION_APP_ENVS,
    SAFE_TEST_APP_ENVS,
    PostgresTestIdentity,
    assert_safe_postgres_test_identity,
    format_postgres_test_identity,
    resolve_postgres_test_identity,
    validate_postgres_test_identity,
)

# Standard "correct test profile" env, used to verify the guard accepts it.
SAFE_PROFILE_ENV: dict[str, str] = {
    "POSTGRES_DB": DEFAULT_TEST_DB_NAME,
    "POSTGRES_HOST": DEFAULT_TEST_DB_HOST,
    "POSTGRES_PORT": DEFAULT_TEST_DB_PORT,
    "APP_ENV": DEFAULT_TEST_APP_ENV,
}


# ---------------------------------------------------------------------------
# Resolver tests
# ---------------------------------------------------------------------------


def test_resolver_returns_safe_defaults_when_env_is_empty() -> None:
    """Resolver fills in safe defaults; identity is fully populated.

    This is what ``make test-pg`` (no user overrides) should produce.
    """
    identity = resolve_postgres_test_identity({})
    assert identity.database_name == DEFAULT_TEST_DB_NAME
    assert identity.database_host == DEFAULT_TEST_DB_HOST
    assert identity.database_port == DEFAULT_TEST_DB_PORT
    assert identity.app_env == DEFAULT_TEST_APP_ENV
    # All four required fields were defaulted.
    assert set(identity.used_defaults) == {
        "database_name",
        "database_host",
        "database_port",
        "app_env",
    }
    assert identity.worker_id == "master"
    assert identity.safety_profile_source == "env+defaults"


def test_resolver_marks_source_as_env_when_all_fields_set() -> None:
    """Resolver marks source=env when no defaults used."""
    identity = resolve_postgres_test_identity(SAFE_PROFILE_ENV)
    assert identity.used_defaults == {}
    assert identity.safety_profile_source == "env"


def test_resolver_accepts_worker_id_override() -> None:
    """Resolver accepts a worker_id override for pytest-xdist compatibility.

    This is forward-compatibility for Slice 3 / Slice 4 isolation work;
    Slice 1 itself does not exercise concurrency, but the API is
    wired up so future slices do not need to re-shape the dataclass.
    """
    identity = resolve_postgres_test_identity(SAFE_PROFILE_ENV, worker_id="gw0")
    assert identity.worker_id == "gw0"


def test_resolver_propagates_partial_env_partial_defaults() -> None:
    """Resolver marks only the missing fields as defaulted."""
    env = {"POSTGRES_DB": "blueberry_peak_test_gw3", "APP_ENV": "test"}
    identity = resolve_postgres_test_identity(env, worker_id="gw3")
    assert identity.database_name == "blueberry_peak_test_gw3"
    # used_defaults is dict[str, bool]; only the missing fields are present.
    assert set(identity.used_defaults.keys()) == {"database_host", "database_port"}
    assert all(identity.used_defaults.values())


# ---------------------------------------------------------------------------
# Validator: rejection tests (each unsafe profile variant)
# ---------------------------------------------------------------------------


def test_validator_rejects_explicit_forbidden_db_name() -> None:
    """POSTGRES_DB in FORBIDDEN_DATABASE_NAMES is rejected."""
    identity = PostgresTestIdentity(
        database_name="blueberry_peak",
        database_host=DEFAULT_TEST_DB_HOST,
        database_port="55432",
        app_env="test",
    )
    with pytest.raises(ValueError, match="FORBIDDEN_DATABASE_NAMES"):
        validate_postgres_test_identity(identity)


def test_validator_rejects_dev_db_pattern_without_test_suffix() -> None:
    """Dev-DB pattern ('blueberry_peak' without '_test') is rejected."""
    identity = PostgresTestIdentity(
        database_name="blueberry_peak_staging",
        database_host=DEFAULT_TEST_DB_HOST,
        database_port="55432",
        app_env="test",
    )
    with pytest.raises(ValueError, match="dev-DB pattern"):
        validate_postgres_test_identity(identity)


def test_validator_rejects_dev_port_with_localhost() -> None:
    """POSTGRES_PORT=5432 + POSTGRES_HOST=localhost is the dev-DB profile."""
    identity = PostgresTestIdentity(
        database_name=DEFAULT_TEST_DB_NAME,
        database_host="localhost",
        database_port="5432",
        app_env="test",
    )
    with pytest.raises(ValueError, match="dev-DB profile"):
        validate_postgres_test_identity(identity)


def test_validator_rejects_production_app_env() -> None:
    """Each value in PRODUCTION_APP_ENVS is rejected."""
    for bad_env in PRODUCTION_APP_ENVS:
        identity = PostgresTestIdentity(
            database_name=DEFAULT_TEST_DB_NAME,
            database_host=DEFAULT_TEST_DB_HOST,
            database_port=DEFAULT_TEST_DB_PORT,
            app_env=bad_env,
        )
        with pytest.raises(ValueError, match="PRODUCTION_APP_ENVS"):
            validate_postgres_test_identity(identity)


def test_validator_rejects_unknown_app_env() -> None:
    """APP_ENV outside SAFE_TEST_APP_ENVS is rejected."""
    identity = PostgresTestIdentity(
        database_name=DEFAULT_TEST_DB_NAME,
        database_host=DEFAULT_TEST_DB_HOST,
        database_port=DEFAULT_TEST_DB_PORT,
        app_env="some-other-env",
    )
    with pytest.raises(ValueError, match="not in SAFE_TEST_APP_ENVS"):
        validate_postgres_test_identity(identity)


def test_validator_accepts_each_safe_app_env() -> None:
    """Each value in SAFE_TEST_APP_ENVS is accepted."""
    for ok_env in SAFE_TEST_APP_ENVS:
        identity = PostgresTestIdentity(
            database_name=DEFAULT_TEST_DB_NAME,
            database_host=DEFAULT_TEST_DB_HOST,
            database_port=DEFAULT_TEST_DB_PORT,
            app_env=ok_env,
        )
        # Must not raise.
        validate_postgres_test_identity(identity)


def test_validator_rejects_silent_fallback_to_dev_defaults() -> None:
    """Silent fallback to a non-safe default value is rejected.

    Example: a profile where ``database_name`` was silently defaulted
    to a value that is NOT the safe ``DEFAULT_TEST_DB_NAME`` and NOT
    forbidden by name or pattern. We use ``local_dev_test_db`` here —
    it bypasses both the forbidden-name check and the dev-DB-pattern
    check, so only the silent-fallback check can fire.
    """
    identity = PostgresTestIdentity(
        database_name="local_dev_test_db",
        database_host=DEFAULT_TEST_DB_HOST,
        database_port=DEFAULT_TEST_DB_PORT,
        app_env="test",
        used_defaults={"database_name": True},
    )
    with pytest.raises(ValueError, match="silent fallback"):
        validate_postgres_test_identity(identity)


def test_validator_accepts_safe_defaults_when_no_env_exported() -> None:
    """The validator accepts the safe defaults that the resolver emits."""
    identity = resolve_postgres_test_identity({})
    # No exception.
    validate_postgres_test_identity(identity)


def test_validator_accepts_worker_suffixed_test_db() -> None:
    """Worker-suffixed test DB names ('*_test_gw0') are accepted.

    Forward-compatibility for Slice 3 (migration per-worker DB).
    """
    identity = PostgresTestIdentity(
        database_name="blueberry_peak_test_gw0",
        database_host=DEFAULT_TEST_DB_HOST,
        database_port="55433",  # per-worker port
        app_env="test",
        worker_id="gw0",
    )
    # Must not raise.
    validate_postgres_test_identity(identity)


# ---------------------------------------------------------------------------
# DATABASE_URL safety (independent of identity)
# ---------------------------------------------------------------------------


def test_database_url_with_dev_db_name_is_rejected() -> None:
    """DATABASE_URL containing dev-DB name pattern is rejected via wrapper."""
    env = dict(SAFE_PROFILE_ENV)
    env["DATABASE_URL"] = "postgresql://postgres:secret@localhost:55432/blueberry_peak"
    with pytest.raises(ValueError, match="DATABASE_URL contains a dev-DB name pattern"):
        assert_safe_postgres_test_identity(env)


def test_database_url_with_dev_port_is_rejected() -> None:
    """DATABASE_URL pointing at localhost:5432 is rejected via wrapper."""
    env = dict(SAFE_PROFILE_ENV)
    env["DATABASE_URL"] = "postgresql://postgres:secret@localhost:5432/blueberry_peak_test"
    with pytest.raises(ValueError, match="dev port"):
        assert_safe_postgres_test_identity(env)


def test_database_url_test_profile_is_accepted() -> None:
    """A DATABASE_URL pointing at the test profile is accepted."""
    env = dict(SAFE_PROFILE_ENV)
    env["DATABASE_URL"] = "postgresql://postgres:secret@localhost:55432/blueberry_peak_test"
    # Must not raise.
    identity = assert_safe_postgres_test_identity(env)
    assert identity.database_name == DEFAULT_TEST_DB_NAME


def test_database_url_empty_string_is_accepted() -> None:
    """Empty DATABASE_URL is treated as 'no URL override' (safe)."""
    env = dict(SAFE_PROFILE_ENV)
    env["DATABASE_URL"] = ""
    # Must not raise.
    assert_safe_postgres_test_identity(env)


# ---------------------------------------------------------------------------
# Wrapper: assert_safe_postgres_test_identity
# ---------------------------------------------------------------------------


def test_assert_safe_returns_full_identity_for_safe_profile() -> None:
    """The fail-closed wrapper returns the full identity dataclass."""
    identity = assert_safe_postgres_test_identity(SAFE_PROFILE_ENV, worker_id="test-worker")
    assert identity.database_name == DEFAULT_TEST_DB_NAME
    assert identity.database_host == DEFAULT_TEST_DB_HOST
    assert identity.database_port == DEFAULT_TEST_DB_PORT
    assert identity.app_env == DEFAULT_TEST_APP_ENV
    assert identity.worker_id == "test-worker"


def test_assert_safe_rejects_dev_db_combined_with_dev_port() -> None:
    """Combined dev-DB name + dev port is rejected (the worst-case profile)."""
    env = {
        "POSTGRES_DB": "blueberry_peak",
        "POSTGRES_HOST": "localhost",
        "POSTGRES_PORT": "5432",
        "APP_ENV": "test",
    }
    with pytest.raises(ValueError):
        assert_safe_postgres_test_identity(env)


# ---------------------------------------------------------------------------
# Formatter: one-line summary must not leak secrets
# ---------------------------------------------------------------------------


def test_formatter_includes_all_required_fields() -> None:
    """The formatter includes worker_id / db / host:port / env / source."""
    identity = resolve_postgres_test_identity(SAFE_PROFILE_ENV, worker_id="gw0")
    summary = format_postgres_test_identity(identity)
    assert "worker_id=gw0" in summary
    assert f"db={DEFAULT_TEST_DB_NAME}" in summary
    assert f"host={DEFAULT_TEST_DB_HOST}:{DEFAULT_TEST_DB_PORT}" in summary
    assert f"env={DEFAULT_TEST_APP_ENV}" in summary
    assert "source=env" in summary


def test_formatter_never_includes_database_url_value() -> None:
    """The formatter must not include any URL-shaped substring (no leak)."""
    # Even if we somehow inject a DATABASE_URL value into the
    # environment, the formatter only reads identity fields — the URL
    # value itself never reaches the summary line.
    env = dict(SAFE_PROFILE_ENV)
    env["DATABASE_URL"] = "postgresql://postgres:SECRET_PASSWORD@localhost:55432/x"
    identity = resolve_postgres_test_identity(env)
    summary = format_postgres_test_identity(identity)
    assert "SECRET_PASSWORD" not in summary
    assert "postgresql://" not in summary
    assert "SECRET" not in summary


def test_formatter_includes_defaults_marker_when_env_was_empty() -> None:
    """The formatter surfaces which fields were defaulted (no silent fallback)."""
    identity = resolve_postgres_test_identity({})
    summary = format_postgres_test_identity(identity)
    assert "source=env+defaults" in summary
    # Formatter sorts the defaulted-field names alphabetically.
    assert "defaults=app_env,database_host,database_name,database_port" in summary


# ---------------------------------------------------------------------------
# Constants: self-audit
# ---------------------------------------------------------------------------


def test_forbidden_db_names_includes_blueberry_peak() -> None:
    """FORBIDDEN_DATABASE_NAMES must include the dev DB."""
    assert "blueberry_peak" in FORBIDDEN_DATABASE_NAMES


def test_forbidden_db_ports_includes_5432() -> None:
    """FORBIDDEN_DATABASE_PORTS must include 5432 (dev port)."""
    assert "5432" in FORBIDDEN_DATABASE_PORTS


def test_production_app_envs_is_nonempty_and_disjoint_from_safe() -> None:
    """PRODUCTION_APP_ENVS and SAFE_TEST_APP_ENVS must be disjoint."""
    assert PRODUCTION_APP_ENVS
    assert SAFE_TEST_APP_ENVS
    assert PRODUCTION_APP_ENVS.isdisjoint(SAFE_TEST_APP_ENVS)


def test_safe_default_test_db_name_is_in_safe_profile() -> None:
    """The default test DB name must satisfy the safe-profile checks."""
    identity = PostgresTestIdentity(
        database_name=DEFAULT_TEST_DB_NAME,
        database_host=DEFAULT_TEST_DB_HOST,
        database_port=DEFAULT_TEST_DB_PORT,
        app_env=DEFAULT_TEST_APP_ENV,
    )
    # Must not raise.
    validate_postgres_test_identity(identity)


# ---------------------------------------------------------------------------
# Wrapper: assert_safe_postgres_test_identity + read-environment variant
# ---------------------------------------------------------------------------


def test_assert_safe_reads_os_environ_when_env_is_none() -> None:
    """The wrapper falls back to ``os.environ`` when ``env`` is None.

    This is the path used by shell scripts / Makefile guards that call
    into the Python helper.
    """
    # We do not mutate os.environ here (would leak across tests); we
    # only assert the function does not raise TypeError on None.
    # Resolution may fail if os.environ does not match SAFE_PROFILE_ENV,
    # but that is the validator's job — not a contract violation.
    try:
        assert_safe_postgres_test_identity(None)
    except ValueError:
        # Expected when os.environ does not match the safe profile.
        pass
    except TypeError as exc:
        pytest.fail(f"wrapper must accept None env (got TypeError: {exc})")
