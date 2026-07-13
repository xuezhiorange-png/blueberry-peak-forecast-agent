"""Unit / contract tests for :mod:`backend.tests.integration.agent._pg_dsn`.

These tests do NOT require a real PostgreSQL instance.  They cover:

* Explicit ``BLUEBERRY_PG_DSN`` override (returns the value verbatim).
* Standard ``POSTGRES_*`` env (builds the canary DSN with database
  ``blueberry_peak`` and the standard test service defaults).
* Special characters in username / password (must be URL-escaped
  and re-parseable to the same fields).
* Invalid ``POSTGRES_PORT`` (non-integer) → :class:`PostgresTestDSNError`.
* Empty ``POSTGRES_DB`` / ``POSTGRES_USER`` → :class:`PostgresTestDSNError`.
* Forbidden legacy database ``blueberry_peak_test_r7_round8`` →
  :class:`PostgresTestDSNError` even when explicitly named.
* Whitespace-only ``BLUEBERRY_PG_DSN`` falls through to the env path.
* :func:`render_dsn_for_log` never prints the password.
* Both PG test modules import the **same** resolver (no duplication).
"""
# ruff: noqa: E501, I001, F401, F841, F811, F821, ASYNC240

from __future__ import annotations

import importlib
from urllib.parse import urlparse

import pytest

from backend.tests.integration.agent._pg_dsn import (
    PostgresTestDSNError,
    render_dsn_for_log,
    resolve_postgres_test_dsn,
)


_CI_ENV: dict[str, str] = {
    "POSTGRES_HOST": "localhost",
    "POSTGRES_PORT": "5432",
    "POSTGRES_DB": "blueberry_peak",
    "POSTGRES_USER": "blueberry_app",
    "POSTGRES_PASSWORD": "change-me-in-local-env",
}


def test_explicit_blueberry_pg_dsn_override_preserved() -> None:
    """A. Explicit override path.  The value must be returned verbatim
    and must NOT be rebuilt from the env.
    """
    env = dict(_CI_ENV)
    env["BLUEBERRY_PG_DSN"] = "postgresql+asyncpg://u:p@db:9999/custom"
    assert resolve_postgres_test_dsn(env) == "postgresql+asyncpg://u:p@db:9999/custom"


def test_explicit_override_ignores_postgres_env_db() -> None:
    """Even if ``POSTGRES_DB`` points at a different database, an
    explicit ``BLUEBERRY_PG_DSN`` wins.
    """
    env = dict(_CI_ENV)
    env["POSTGRES_DB"] = "some_other_db"
    env["BLUEBERRY_PG_DSN"] = "postgresql+asyncpg://u:p@db:9999/custom"
    assert resolve_postgres_test_dsn(env) == "postgresql+asyncpg://u:p@db:9999/custom"


def test_standard_ci_env_resolves_to_blueberry_peak() -> None:
    """B. Standard CI env path.  No ``BLUEBERRY_PG_DSN``; resolve
    from the standard ``POSTGRES_*`` env.  The resulting DSN MUST
    point at ``blueberry_peak`` and MUST NOT contain the legacy
    ``blueberry_peak_test_r7_round8`` fallback.
    """
    env = dict(_CI_ENV)
    dsn = resolve_postgres_test_dsn(env)
    u = urlparse(dsn)
    assert u.hostname == "localhost"
    assert u.port == 5432
    assert u.username == "blueberry_app"
    assert (u.path or "").lstrip("/") == "blueberry_peak"
    assert "blueberry_peak_test_r7_round8" not in dsn
    # Rendered DSN must still be a SQLAlchemy-parseable URL.
    assert dsn.startswith("postgresql+asyncpg://")


def test_whitespace_only_override_falls_through_to_env() -> None:
    """Whitespace-only ``BLUEBERRY_PG_DSN`` is treated as unset;
    the standard env path is used.
    """
    env = dict(_CI_ENV)
    env["BLUEBERRY_PG_DSN"] = "   "
    dsn = resolve_postgres_test_dsn(env)
    assert (urlparse(dsn).path or "").lstrip("/") == "blueberry_peak"


def test_no_env_at_all_falls_back_to_standard_defaults() -> None:
    """When ``BLUEBERRY_PG_DSN`` is unset AND no ``POSTGRES_*``
    env is provided, the resolver falls back to the standard
    test service defaults (host=localhost, port=5432,
    db=blueberry_peak, user=blueberry_app, password=local-dev
    placeholder).  This matches the canary container's defaults
    and is the directive §5.B contract.
    """
    dsn = resolve_postgres_test_dsn({})
    u = urlparse(dsn)
    assert u.hostname == "localhost"
    assert u.port == 5432
    assert u.username == "blueberry_app"
    assert (u.path or "").lstrip("/") == "blueberry_peak"
    # Must NOT contain the forbidden legacy fallback.
    assert "blueberry_peak_test_r7_round8" not in dsn


def test_invalid_postgres_port_fails_closed() -> None:
    """``POSTGRES_PORT=not-a-number`` must raise
    :class:`PostgresTestDSNError` with a port hint.
    """
    env = dict(_CI_ENV)
    env["POSTGRES_PORT"] = "not-a-number"
    with pytest.raises(PostgresTestDSNError) as exc_info:
        resolve_postgres_test_dsn(env)
    assert "port" in str(exc_info.value).lower()


def test_empty_postgres_db_fails_closed() -> None:
    """``POSTGRES_DB=""`` must raise :class:`PostgresTestDSNError`
    with a database hint.
    """
    env = dict(_CI_ENV)
    env["POSTGRES_DB"] = ""
    with pytest.raises(PostgresTestDSNError) as exc_info:
        resolve_postgres_test_dsn(env)
    assert "database" in str(exc_info.value).lower()


def test_empty_postgres_user_fails_closed() -> None:
    """``POSTGRES_USER=""`` must raise :class:`PostgresTestDSNError`
    with a user hint.
    """
    env = dict(_CI_ENV)
    env["POSTGRES_USER"] = ""
    with pytest.raises(PostgresTestDSNError) as exc_info:
        resolve_postgres_test_dsn(env)
    assert "user" in str(exc_info.value).lower()


def test_legacy_blueberry_peak_test_r7_round8_fails_closed() -> None:
    """The forbidden legacy database name must NEVER be produced
    by the resolver, even when explicitly named in
    ``POSTGRES_DB``.  This is the regression guard the hotfix
    directive §5 requires.
    """
    env = dict(_CI_ENV)
    env["POSTGRES_DB"] = "blueberry_peak_test_r7_round8"
    with pytest.raises(PostgresTestDSNError) as exc_info:
        resolve_postgres_test_dsn(env)
    assert "blueberry_peak_test_r7_round8" in str(exc_info.value)


def test_special_characters_in_password_are_url_escaped() -> None:
    """Username / password with ``@ : / #`` must be URL-escaped
    and re-parseable to the same fields via :class:`urllib.parse`.
    SQLAlchemy's :class:`URL` provides the escaping.
    """
    from urllib.parse import unquote

    env = dict(_CI_ENV)
    env["POSTGRES_USER"] = "user@with:special/chars"
    env["POSTGRES_PASSWORD"] = "p@ss:word/with#special"
    dsn = resolve_postgres_test_dsn(env)
    u = urlparse(dsn)
    # ``urlparse`` does NOT decode the userinfo — we must
    # ``unquote`` to recover the original characters.
    assert unquote(u.username or "") == "user@with:special/chars"
    assert unquote(u.password or "") == "p@ss:word/with#special"
    assert u.hostname == "localhost"
    assert u.port == 5432
    assert (u.path or "").lstrip("/") == "blueberry_peak"


def test_render_dsn_for_log_redacts_password() -> None:
    """The redaction helper must never include the password in
    its output, even when the input DSN contains a non-trivial
    password.
    """
    dsn = "postgresql+asyncpg://u:p@ss@db:5432/db"
    out = render_dsn_for_log(dsn)
    assert "p@ss" not in out
    assert "p%40ss" not in out
    assert "u:***@db" in out or "u@***db" in out


def test_render_dsn_for_log_handles_plain_string() -> None:
    """Non-URL DSNs are returned unchanged (no crash)."""
    assert render_dsn_for_log("not a url") == "not a url"


def test_both_pg_test_modules_use_same_resolver() -> None:
    """The two PG test modules MUST import the SAME resolver
    function (no duplicated copies).  This is a guard against
    future drift.
    """
    year_mod = importlib.import_module(
        "backend.tests.integration.agent.test_postgres_selector_year_extraction"
    )
    round11_mod = importlib.import_module(
        "backend.tests.integration.agent.test_postgres_public_blocker_total_order"
    )
    shared = importlib.import_module("backend.tests.integration.agent._pg_dsn")
    # Both modules' module-level ``POSTGRES_TEST_DSN`` is the
    # result of ``resolve_postgres_test_dsn()`` (called at import).
    # They must therefore point at the same DSN string and the
    # same DB.
    assert year_mod.POSTGRES_TEST_DSN == round11_mod.POSTGRES_TEST_DSN
    year_db = (urlparse(year_mod.POSTGRES_TEST_DSN).path or "").lstrip("/")
    round11_db = (urlparse(round11_mod.POSTGRES_TEST_DSN).path or "").lstrip("/")
    assert year_db == round11_db == "blueberry_peak"
    # And the function identity must be the shared module's symbol.
    assert year_mod.resolve_postgres_test_dsn is shared.resolve_postgres_test_dsn
    assert round11_mod.resolve_postgres_test_dsn is shared.resolve_postgres_test_dsn
    # No legacy fallback anywhere.
    assert "blueberry_peak_test_r7_round8" not in year_mod.POSTGRES_TEST_DSN
    assert "blueberry_peak_test_r7_round8" not in round11_mod.POSTGRES_TEST_DSN
