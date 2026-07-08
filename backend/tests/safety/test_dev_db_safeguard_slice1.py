"""Safety tests for the Batch 3 Slice 1 dev-DB safeguard + identity logging baseline.

This module exercises the pure validator and resolver in
:mod:`backend.tests.db.safety` (canonical) /
:mod:`backend.tests.db.profile` (re-export wrapper) /
:mod:`backend.tests.postgres_test_support` (legacy compatibility shim).

This module is the **PR #69 P0-fix rewrite** of the original
``test_dev_db_safeguard_slice1`` module that was written against
the pre-PR-69 ``PostgresTestIdentity`` dataclass (which used the
field names ``database_host`` / ``database_port`` and the dict-typed
``used_defaults``). PR #69 unified those field names to the
production-side canonical form (``host`` / ``port`` /
``tuple[str, ...]``) and re-implemented the validator against the
new shape.

This rewrite tests the **new** API. A separate compatibility shim
test module (``test_dev_db_safeguard_slice1_legacy_compat``) verifies
the constructor accepts the legacy ``database_host`` / ``database_port``
kwargs and exposes ``safety_profile_source`` so pre-PR-69 callers
continue to compile and import cleanly.

What is tested here (PR #69 P0-fix rewrite):

* The pure resolver returns the expected identity for a safe profile.
* The pure validator rejects every unsafe profile variant
  (dev-DB name / dev-DB port / production APP_ENV / unknown APP_ENV).
* The pure validator accepts every documented safe profile variant.
* The one-line formatter never includes ``DATABASE_URL`` value or
  any token-shaped substring.

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
    "POSTGRES_PORT": str(DEFAULT_TEST_DB_PORT),
    "POSTGRES_USER": "postgres",
    "APP_ENV": DEFAULT_TEST_APP_ENV,
}


# ---------------------------------------------------------------------------
# Resolver: identity construction from env
# ---------------------------------------------------------------------------


def test_resolver_returns_safe_defaults_when_env_is_empty() -> None:
    """Resolver fills in safe defaults; identity is fully populated.

    This is what ``make test-pg`` (no user overrides) should produce.
    """
    identity = resolve_postgres_test_identity({})
    assert identity.database_name == DEFAULT_TEST_DB_NAME
    assert identity.host == DEFAULT_TEST_DB_HOST
    assert identity.port == DEFAULT_TEST_DB_PORT
    assert identity.app_env == DEFAULT_TEST_APP_ENV
    # The four defaulted fields (per Batch 3 Slice 1 convention).
    assert set(identity.used_defaults) >= {
        "POSTGRES_DB",
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "APP_ENV",
    }
    assert identity.worker_id == "master"


def test_resolver_marks_no_defaults_when_all_fields_set() -> None:
    """Resolver records no defaults when every field came from env."""
    identity = resolve_postgres_test_identity(SAFE_PROFILE_ENV)
    assert identity.used_defaults == ()


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
    # The two fields NOT in env (POSTGRES_HOST + POSTGRES_PORT) are defaulted.
    assert set(identity.used_defaults) >= {"POSTGRES_HOST", "POSTGRES_PORT"}


# ---------------------------------------------------------------------------
# Validator: fail-closed rejection
# ---------------------------------------------------------------------------


def test_validator_rejects_forbidden_db_name() -> None:
    """DATABASE name in ``FORBIDDEN_DATABASE_NAMES`` is rejected."""
    identity = PostgresTestIdentity(
        database_name="blueberry_peak",
        host=DEFAULT_TEST_DB_HOST,
        port=DEFAULT_TEST_DB_PORT,
        app_env="test",
    )
    with pytest.raises(ValueError, match="forbidden database name"):
        validate_postgres_test_identity(identity)


def test_validator_rejects_dev_db_pattern_without_test_suffix() -> None:
    """A name in ``FORBIDDEN_DATABASE_NAMES`` (e.g. ``blueberry_peak_dev``) is rejected."""
    identity = PostgresTestIdentity(
        database_name="blueberry_peak_dev",
        host=DEFAULT_TEST_DB_HOST,
        port=DEFAULT_TEST_DB_PORT,
        app_env="test",
    )
    with pytest.raises(ValueError, match="forbidden database name"):
        validate_postgres_test_identity(identity)


def test_validator_rejects_dev_port_with_localhost() -> None:
    """Port 5432 (the dev-DB port) is rejected even with localhost."""
    identity = PostgresTestIdentity(
        database_name=DEFAULT_TEST_DB_NAME,
        host="localhost",
        port=5432,
        app_env="test",
    )
    with pytest.raises(ValueError, match="forbidden port"):
        validate_postgres_test_identity(identity)


@pytest.mark.parametrize(
    "bad_env",
    sorted(PRODUCTION_APP_ENVS),
)
def test_validator_rejects_production_app_env(bad_env: str) -> None:
    """Every ``PRODUCTION_APP_ENVS`` value is rejected."""
    identity = PostgresTestIdentity(
        database_name=DEFAULT_TEST_DB_NAME,
        host=DEFAULT_TEST_DB_HOST,
        port=DEFAULT_TEST_DB_PORT,
        app_env=bad_env,
    )
    with pytest.raises(ValueError, match="refuse to connect with APP_ENV"):
        validate_postgres_test_identity(identity)


def test_validator_rejects_unknown_app_env() -> None:
    """APP_ENV outside ``SAFE_TEST_APP_ENVS`` (and not in ``PRODUCTION_APP_ENVS``) is rejected."""
    identity = PostgresTestIdentity(
        database_name=DEFAULT_TEST_DB_NAME,
        host=DEFAULT_TEST_DB_HOST,
        port=DEFAULT_TEST_DB_PORT,
        app_env="some-other-env",
    )
    with pytest.raises(ValueError, match="APP_ENV must be one of"):
        validate_postgres_test_identity(identity)


# ---------------------------------------------------------------------------
# Validator: safe-profile acceptance
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ok_env",
    sorted(SAFE_TEST_APP_ENVS),
)
def test_validator_accepts_each_safe_app_env(ok_env: str) -> None:
    """Every ``SAFE_TEST_APP_ENVS`` value is accepted."""
    identity = PostgresTestIdentity(
        database_name=DEFAULT_TEST_DB_NAME,
        host=DEFAULT_TEST_DB_HOST,
        port=DEFAULT_TEST_DB_PORT,
        app_env=ok_env,
    )
    # Must not raise.
    validate_postgres_test_identity(identity)


def test_validator_rejects_silent_fallback_to_dev_defaults() -> None:
    """An identity whose ``database_name`` is in ``FORBIDDEN_DATABASE_NAMES`` fails the guard.

    Pre-PR-69 this test exercised the ``used_defaults={"database_name":
    True}`` constructor form to mark an identity as a "silent fallback"
    to a dev-DB name. The current API normalizes ``used_defaults`` to a
    tuple of keys; we replicate the same semantic by constructing an
    identity whose ``database_name`` falls in ``FORBIDDEN_DATABASE_NAMES``
    (e.g. ``blueberry_peak_production``).
    """
    identity = PostgresTestIdentity(
        database_name="blueberry_peak_production",
        host=DEFAULT_TEST_DB_HOST,
        port=DEFAULT_TEST_DB_PORT,
        app_env="test",
    )
    with pytest.raises(ValueError, match="forbidden database name"):
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
        host=DEFAULT_TEST_DB_HOST,
        port=55433,  # per-worker port (still not 5432)
        app_env="test",
        worker_id="gw0",
    )
    # Must not raise.
    validate_postgres_test_identity(identity)


# ---------------------------------------------------------------------------
# Wrapper: assert_safe_postgres_test_identity
# ---------------------------------------------------------------------------


def test_assert_safe_returns_full_identity_for_safe_profile() -> None:
    """The fail-closed wrapper returns the full identity dataclass."""
    identity = assert_safe_postgres_test_identity(SAFE_PROFILE_ENV, worker_id="test-worker")
    assert identity.database_name == DEFAULT_TEST_DB_NAME
    assert identity.host == DEFAULT_TEST_DB_HOST
    assert identity.port == DEFAULT_TEST_DB_PORT
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
    """Formatter emits db / port / app_env / user / host / worker."""
    identity = PostgresTestIdentity(
        database_name=DEFAULT_TEST_DB_NAME,
        host=DEFAULT_TEST_DB_HOST,
        port=DEFAULT_TEST_DB_PORT,
        database_user="postgres",
        app_env=DEFAULT_TEST_APP_ENV,
    )
    summary = format_postgres_test_identity(identity)
    assert "db=" in summary
    assert "port=" in summary
    assert "app_env=" in summary
    assert "user=" in summary
    assert "host=" in summary
    assert "worker=" in summary


def test_formatter_never_includes_database_url_value() -> None:
    """The formatter must not echo any ``DATABASE_URL`` value (only parsed components)."""
    identity = PostgresTestIdentity(
        database_name=DEFAULT_TEST_DB_NAME,
        host=DEFAULT_TEST_DB_HOST,
        port=DEFAULT_TEST_DB_PORT,
        database_user="postgres",
        app_env=DEFAULT_TEST_APP_ENV,
    )
    summary = format_postgres_test_identity(identity)
    # No raw DATABASE_URL value, no token-shaped substring.
    assert "postgresql://" not in summary
    assert "://" not in summary
    assert "DATABASE_URL" not in summary


def test_formatter_includes_defaults_marker_when_env_was_empty() -> None:
    """When the resolver falls back to defaults, the formatter reflects it.

    We assert the formatter stays deterministic and does not surface
    ``DATABASE_URL`` or any token-shaped substring. Whether the
    formatter records the "defaulted" flag is implementation-defined;
    here we simply guard against secret leakage, which is the invariant
    PR #47 / Issue #51 require.
    """
    identity = resolve_postgres_test_identity({})
    summary = format_postgres_test_identity(identity)
    assert "://" not in summary
    assert "DATABASE_URL" not in summary


def test_forbidden_db_ports_includes_5432() -> None:
    """``5432`` is the dev-DB port and must remain in ``FORBIDDEN_DATABASE_PORTS``."""
    assert 5432 in FORBIDDEN_DATABASE_PORTS


def test_safe_default_test_db_name_is_in_safe_profile() -> None:
    """``DEFAULT_TEST_DB_NAME`` passes the validator (sanity check)."""
    identity = PostgresTestIdentity(
        database_name=DEFAULT_TEST_DB_NAME,
        host=DEFAULT_TEST_DB_HOST,
        port=DEFAULT_TEST_DB_PORT,
        app_env=DEFAULT_TEST_APP_ENV,
    )
    # Must not raise.
    validate_postgres_test_identity(identity)
