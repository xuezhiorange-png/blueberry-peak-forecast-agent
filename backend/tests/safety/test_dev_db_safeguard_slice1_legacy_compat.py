"""Explicit legacy-API compatibility tests for ``PostgresTestIdentity``.

Per PR #69 P0-fix + Charles brief:
"preserve old PostgresTestIdentity public fields or provide explicit
compatibility tests" — this module is the **explicit compatibility tests**
half of that clause.

Pre-PR-69 callers (and the Batch 3 Slice 1 test suite as it existed
prior to the P0 rewrite) used:

* ``database_host`` constructor kwarg + read attribute (alias for
  current ``host``)
* ``database_port`` constructor kwarg + read attribute (alias for
  current ``port``)
* ``safety_profile_source`` derived attribute (``"env"`` when no
  defaults used, ``"env+defaults"`` otherwise)
* ``used_defaults`` as ``dict[str, bool]`` (current API stores it as
  ``tuple[str, ...]``)

These tests verify all four legacy surfaces continue to work after
the PR #69 API unification. If any of these tests fail, downstream
callers (and the legacy compatibility shim) will break.
"""

from __future__ import annotations

from backend.tests.postgres_test_support import (
    DEFAULT_TEST_APP_ENV,
    DEFAULT_TEST_DB_HOST,
    DEFAULT_TEST_DB_NAME,
    DEFAULT_TEST_DB_PORT,
    PostgresTestIdentity,
    resolve_postgres_test_identity,
)


def test_legacy_database_host_kwarg_accepted() -> None:
    """The legacy ``database_host=`` constructor kwarg populates ``host``."""
    identity = PostgresTestIdentity(
        database_name=DEFAULT_TEST_DB_NAME,
        database_host=DEFAULT_TEST_DB_HOST,
        database_port=DEFAULT_TEST_DB_PORT,
        app_env=DEFAULT_TEST_APP_ENV,
    )
    assert identity.host == DEFAULT_TEST_DB_HOST
    assert identity.database_host == DEFAULT_TEST_DB_HOST


def test_legacy_database_port_kwarg_accepted() -> None:
    """The legacy ``database_port=`` constructor kwarg populates ``port``."""
    identity = PostgresTestIdentity(
        database_name=DEFAULT_TEST_DB_NAME,
        database_host=DEFAULT_TEST_DB_HOST,
        database_port=55432,
        app_env=DEFAULT_TEST_APP_ENV,
    )
    assert identity.port == 55432
    assert identity.database_port == 55432


def test_legacy_database_host_attribute_alias() -> None:
    """``database_host`` is a read alias for ``host``."""
    identity = PostgresTestIdentity(
        database_name=DEFAULT_TEST_DB_NAME,
        host="my-host.example",
        port=DEFAULT_TEST_DB_PORT,
        app_env=DEFAULT_TEST_APP_ENV,
    )
    assert identity.database_host == "my-host.example"
    assert identity.host == identity.database_host


def test_legacy_database_port_attribute_alias() -> None:
    """``database_port`` is a read alias for ``port``."""
    identity = PostgresTestIdentity(
        database_name=DEFAULT_TEST_DB_NAME,
        host=DEFAULT_TEST_DB_HOST,
        port=55432,
        app_env=DEFAULT_TEST_APP_ENV,
    )
    assert identity.database_port == 55432
    assert identity.port == identity.database_port


def test_safety_profile_source_env_when_no_defaults() -> None:
    """``safety_profile_source == 'env'`` when ``used_defaults`` is empty."""
    env = {
        "POSTGRES_DB": DEFAULT_TEST_DB_NAME,
        "POSTGRES_HOST": DEFAULT_TEST_DB_HOST,
        "POSTGRES_PORT": str(DEFAULT_TEST_DB_PORT),
        "POSTGRES_USER": "postgres",
        "APP_ENV": DEFAULT_TEST_APP_ENV,
    }
    identity = resolve_postgres_test_identity(env)
    assert identity.used_defaults == ()
    assert identity.safety_profile_source == "env"


def test_safety_profile_source_env_plus_defaults_when_partial() -> None:
    """``safety_profile_source == 'env+defaults'`` when some fields are defaulted."""
    identity = resolve_postgres_test_identity({})
    assert identity.used_defaults  # non-empty
    assert identity.safety_profile_source == "env+defaults"


def test_used_defaults_dict_form_normalized_to_tuple() -> None:
    """Legacy ``dict[str, bool]`` ``used_defaults`` is normalized to ``tuple[str, ...]`` of keys."""
    identity = PostgresTestIdentity(
        database_name=DEFAULT_TEST_DB_NAME,
        host=DEFAULT_TEST_DB_HOST,
        port=DEFAULT_TEST_DB_PORT,
        app_env=DEFAULT_TEST_APP_ENV,
        used_defaults={"database_name": True, "host": False},
    )
    # Normalized form: tuple of keys (no values, no ordering guarantee beyond insertion).
    assert isinstance(identity.used_defaults, tuple)
    assert set(identity.used_defaults) == {"database_name", "host"}


def test_used_defaults_tuple_form_passes_through() -> None:
    """Current-API ``tuple[str, ...]`` ``used_defaults`` is preserved as-is."""
    identity = PostgresTestIdentity(
        database_name=DEFAULT_TEST_DB_NAME,
        host=DEFAULT_TEST_DB_HOST,
        port=DEFAULT_TEST_DB_PORT,
        app_env=DEFAULT_TEST_APP_ENV,
        used_defaults=("POSTGRES_DB", "APP_ENV"),
    )
    assert identity.used_defaults == ("POSTGRES_DB", "APP_ENV")
