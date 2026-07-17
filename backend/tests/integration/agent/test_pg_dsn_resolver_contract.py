"""Unit / contract tests for :mod:`backend.tests.integration.agent._pg_dsn`.

These tests do NOT require a real PostgreSQL instance.  They cover:

* Explicit ``BLUEBERRY_PG_DSN`` override (returns the trimmed
  non-empty value — surrounding whitespace is removed).
* Standard ``POSTGRES_*`` env (builds the canary DSN with database
  ``blueberry_peak`` and the standard test service defaults).
* Special characters in username / password (must be URL-escaped
  and re-parseable to the same fields).
* Invalid ``POSTGRES_PORT`` (non-integer) → :class:`PostgresTestDSNError`.
* Empty ``POSTGRES_DB`` / ``POSTGRES_USER`` → :class:`PostgresTestDSNError`.
* Forbidden legacy database ``blueberry_peak_test_r7_round8`` supplied
  through ``POSTGRES_DB`` → :class:`PostgresTestDSNError`.  The same
  database name remains allowed when supplied through the trimmed
  explicit ``BLUEBERRY_PG_DSN`` override.
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


def test_explicit_blueberry_pg_dsn_override_trimmed_and_preserved() -> None:
    """A. Explicit override path.  The value must be returned after
    surrounding whitespace is removed (trimmed non-empty override),
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


def test_explicit_blueberry_pg_dsn_legacy_name_remains_explicit_override() -> None:
    """Security-fixup review 4681521607: an explicit, non-empty
    ``BLUEBERRY_PG_DSN`` is the trimmed non-empty local override.
    Even if its database name happens to be the legacy forbidden
    name, the explicit override is returned after surrounding
    whitespace is removed.  The forbidden-name check applies ONLY
    to the ``POSTGRES_DB``-derived path.

    The contract is dual:

    * ``POSTGRES_DB=blueberry_peak_test_r7_round8`` → rejected
      (see ``test_legacy_blueberry_peak_test_r7_round8_fails_closed``).
    * ``BLUEBERRY_PG_DSN=...blueberry_peak_test_r7_round8`` →
      returned after surrounding whitespace is removed (this test).

    These are NOT contradictory: explicit override is a controlled
    local-dev path; the legacy default fallback is the bug.
    """
    explicit = "postgresql+asyncpg://u:p@db:5432/blueberry_peak_test_r7_round8"
    env = {
        "BLUEBERRY_PG_DSN": explicit,
        "POSTGRES_DB": "blueberry_peak",  # would be ignored
    }
    assert resolve_postgres_test_dsn(env) == explicit


def test_describe_postgres_target_never_includes_userinfo_or_password() -> None:
    """Security-fixup review 4681521607 — Test B.

    ``describe_postgres_target(dsn)`` must return a string containing
    ONLY host / port / database.  Username, password, raw userinfo,
    percent-encoded credentials, and the original DSN must NOT
    appear in the output.  This is the helper the fixtures use to
    format skip / fail messages so pytest logs and JUnit XML never
    leak credentials.
    """
    from backend.tests.integration.agent._pg_dsn import (
        describe_postgres_target,
    )

    dsn = (
        "postgresql+asyncpg://"
        "user%40company%3Atest:p%40ss%3Aword%2Fwith%23chars"
        "@db.internal:5544/blueberry_peak"
    )
    out = describe_postgres_target(dsn)
    assert "host=db.internal" in out
    assert "port=5544" in out
    assert (
        "database='blueberry_peak'" in out
        or 'database="blueberry_peak"' in out
        or "blueberry_peak" in out
    )
    # Forbidden tokens — must NOT appear in the safe descriptor.
    assert "user%40company" not in out
    assert "user@company" not in out
    assert "company" not in out
    assert "p%40ss" not in out
    assert "p@ss" not in out
    assert "p@ss:word" not in out
    assert "password" not in out.lower()
    assert "userinfo" not in out.lower()
    # Raw DSN fragments must NOT appear in the safe descriptor.
    assert "postgresql+asyncpg://" not in out
    assert dsn not in out


def test_describe_postgres_target_handles_unparseable_dsn() -> None:
    """A malformed DSN must NOT be echoed back raw — the safe
    descriptor must fall back to a constant placeholder so we never
    accidentally emit userinfo we cannot parse.
    """
    from backend.tests.integration.agent._pg_dsn import (
        describe_postgres_target,
    )

    out = describe_postgres_target("not-a-url")
    assert "user" not in out.lower()
    assert "password" not in out.lower()
    # Must be a stable placeholder, not the raw input.
    assert out != "not-a-url"


def test_preflight_passes_decoded_credentials_to_asyncpg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Security-fixup review 4681521607 — Test A.

    ``verify_postgres_database_exists`` must call ``asyncpg.connect``
    with the DECODED username / password / database (not the
    percent-encoded form).  The starting-head implementation uses
    :func:`urllib.parse.urlparse` which does NOT decode userinfo;
    credentials containing ``@ : / #`` are sent incorrectly.
    """
    import asyncio
    from typing import Any

    from backend.tests.integration.agent._pg_dsn import (
        verify_postgres_database_exists,
    )

    captured: dict[str, Any] = {}

    class _FakeConnection:
        async def fetchval(self, query: str) -> int:
            assert query == "SELECT 1"
            return 1

        async def close(self) -> None:
            pass

    async def fake_connect(*args: Any, **kwargs: Any) -> _FakeConnection:
        # Capture keyword arguments verbatim.
        captured["kwargs"] = dict(kwargs)
        captured["args"] = args
        return _FakeConnection()

    monkeypatch.setattr("asyncpg.connect", fake_connect)

    env: dict[str, str] = {
        "POSTGRES_HOST": "db.internal",
        "POSTGRES_PORT": "5544",
        "POSTGRES_DB": "blueberry/special",
        "POSTGRES_USER": "user@company:test",
        "POSTGRES_PASSWORD": "p@ss:word/with#chars",
    }
    dsn = resolve_postgres_test_dsn(env)
    asyncio.run(verify_postgres_database_exists(dsn))

    kwargs = captured["kwargs"]
    assert kwargs["host"] == "db.internal"
    assert kwargs["port"] == 5544
    assert kwargs["database"] == "blueberry/special"
    assert kwargs["user"] == "user@company:test"
    assert kwargs["password"] == "p@ss:word/with#chars"
    # No percent-encoded chars in the decoded credentials.
    for token in ("%40", "%3A", "%2F", "%23"):
        assert token not in kwargs["user"]
        assert token not in kwargs["password"]
        assert token not in kwargs["database"]


def test_render_dsn_for_log_uses_sqlalchemy_hide_password() -> None:
    """Security-fixup review 4681521607 — render helper.

    The redaction helper must use SQLAlchemy's
    ``render_as_string(hide_password=True)``.  Raw and encoded
    password must never appear in the output, even for DSNs with
    multiple ``@`` / special characters / unparseable input.
    """
    cases = [
        "postgresql+asyncpg://u:p@ss@db:5432/db",
        "postgresql+asyncpg://u%40h:p%40ss@db:5432/db",
        "postgresql+asyncpg://u:p@ss:word/with#chars@db:5432/db",
    ]
    for dsn in cases:
        out = render_dsn_for_log(dsn)
        assert "p@ss" not in out
        assert "p%40ss" not in out
        assert "p%3Ass" not in out
        assert "p%2F" not in out
        assert "p%23" not in out

    # Malformed DSN must NOT be echoed raw.
    out = render_dsn_for_log("not a url with password=hunter2")
    assert "hunter2" not in out


def test_both_fixtures_use_safe_target_descriptor() -> None:
    """Security-fixup review 4681521607 — Test C.

    Both PG test modules MUST use the same safe target descriptor
    in their ``pytest.skip`` / ``pytest.fail`` paths.  They MUST
    NOT interpolate the raw ``POSTGRES_TEST_DSN`` (which carries
    userinfo / password) into user-visible messages.
    """
    import inspect

    modules = [
        importlib.import_module(
            "backend.tests.integration.agent.test_postgres_selector_year_extraction"
        ),
        importlib.import_module(
            "backend.tests.integration.agent.test_postgres_public_blocker_total_order"
        ),
    ]
    for mod in modules:
        source = inspect.getsource(mod)
        # The raw DSN must NOT be interpolated into a user-visible message.
        assert "POSTGRES_TEST_DSN};" not in source, (
            f"{mod.__name__} interpolates POSTGRES_TEST_DSN into a "
            "user-visible message (password leak risk)"
        )
        assert "at {POSTGRES_TEST_DSN}" not in source
        assert 'f"PostgreSQL is not reachable at {POSTGRES_TEST_DSN}"' not in source
        # The safe descriptor helper must be the one used.
        assert "describe_postgres_target" in source, (
            f"{mod.__name__} does not use describe_postgres_target()"
        )


def test_render_dsn_for_log_redacts_password() -> None:
    """The redaction helper must never include the raw or
    percent-encoded password in its output, even when the input
    DSN contains a non-trivial password.

    Per the security fixup (review 4681521607) the redaction
    helper uses SQLAlchemy's ``render_as_string(hide_password=True)``.
    SQLAlchemy's canonical redaction format is
    ``postgresql+asyncpg://user:***@host:port/db`` (the password
    is replaced with literal ``***``).
    """
    dsn = "postgresql+asyncpg://u:p@ss@db:5432/db"
    out = render_dsn_for_log(dsn)
    assert "p@ss" not in out
    assert "p%40ss" not in out
    # SQLAlchemy's canonical redaction format:
    assert "***" in out
    # Host / port / db must still be present in the redacted URL.
    assert "db" in out
    assert "5432" in out


def test_render_dsn_for_log_handles_unparseable_dsn_fail_closed() -> None:
    """A non-URL DSN must NOT be echoed back raw — the redaction
    helper must return a constant placeholder so we never
    accidentally emit userinfo we cannot parse.  This is the
    security-fixup contract (review 4681521607).
    """
    out = render_dsn_for_log("not a url")
    assert out == "<unparseable PostgreSQL DSN>"
    # And the raw input is NOT echoed back.
    assert "not a url" not in out
    # Malformed DSN with embedded password must not leak the password.
    out2 = render_dsn_for_log("not a url with password=hunter2")
    assert "hunter2" not in out2


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
    expected_dsn = shared.resolve_postgres_test_dsn()
    expected_db = (urlparse(expected_dsn).path or "").lstrip("/")
    assert year_mod.POSTGRES_TEST_DSN == round11_mod.POSTGRES_TEST_DSN
    year_db = (urlparse(year_mod.POSTGRES_TEST_DSN).path or "").lstrip("/")
    round11_db = (urlparse(round11_mod.POSTGRES_TEST_DSN).path or "").lstrip("/")
    assert year_db == round11_db == expected_db
    # And the function identity must be the shared module's symbol.
    assert year_mod.resolve_postgres_test_dsn is shared.resolve_postgres_test_dsn
    assert round11_mod.resolve_postgres_test_dsn is shared.resolve_postgres_test_dsn
    # No legacy fallback anywhere.
    assert "blueberry_peak_test_r7_round8" not in year_mod.POSTGRES_TEST_DSN
    assert "blueberry_peak_test_r7_round8" not in round11_mod.POSTGRES_TEST_DSN


# ---------------------------------------------------------------------------
# Round 12 secret-hygiene fixup tests (review 4681746668).
#
# Three findings to close:
#
# * P0 — non-PostgreSQL explicit DSN error must NEVER echo the raw
#   ``BLUEBERRY_PG_DSN`` value (collection-time secret leak).
# * P1 — ``render_dsn_for_log()`` must remove ALL query parameters, not
#   just the authority password, so credential values supplied via
#   ``?password=`` / ``?token=`` / ``?sslpassword=`` cannot land in
#   pytest / CI logs.
# * P2 — explicit override is actually a TRIMMED non-empty value, not a
#   strictly verbatim one.  The wording must reflect the real behaviour.
# ---------------------------------------------------------------------------


def test_invalid_explicit_dsn_scheme_never_echoes_secret() -> None:
    """P0 from review 4681746668.

    A non-PostgreSQL ``BLUEBERRY_PG_DSN`` MUST raise
    :class:`PostgresTestDSNError` whose message contains neither the
    raw input, the authority userinfo (password / username), the host,
    the database, nor any recognizable fragment of the original DSN.

    The original implementation interpolated ``{explicit!r}`` into the
    error message, which leaks the password into pytest collection
    output, GitHub Actions logs and JUnit XML.
    """
    secret = "real-secret"
    dsn = f"mysql://user:{secret}@db.internal/test"
    with pytest.raises(PostgresTestDSNError) as exc_info:
        resolve_postgres_test_dsn({"BLUEBERRY_PG_DSN": dsn})
    message = str(exc_info.value)
    assert secret not in message
    assert dsn not in message
    assert "mysql://user" not in message
    assert "db.internal/test" not in message


@pytest.mark.parametrize(
    "query",
    [
        "password=hunter2",
        "sslpassword=hunter2",
        "pass=hunter2",
        "secret=hunter2",
        "token=hunter2",
        "access_token=hunter2",
    ],
)
def test_render_dsn_for_log_redacts_sensitive_query_values(
    query: str,
) -> None:
    """P1 from review 4681746668.

    Even when ``render_dsn_for_log()`` redacts the authority password
    via ``hide_password=True``, query-string credentials must NOT
    survive into the safe-log output.  ``?password=``,
    ``?sslpassword=``, ``?pass=``, ``?secret=``, ``?token=`` and
    ``?access_token=`` are all sensitive query keys; a credential value
    (here ``hunter2``) and the authority password (``authority-secret``)
    must both be absent from the rendered string.
    """
    dsn = f"postgresql+asyncpg://user:authority-secret@db.internal:5432/blueberry_peak?{query}"
    output = render_dsn_for_log(dsn)
    assert "authority-secret" not in output
    assert "hunter2" not in output


def test_render_dsn_for_log_redacts_mixed_query() -> None:
    """P1 mixed-query variant.

    A realistic DSN mixes non-sensitive query parameters
    (``sslmode=require``, ``application_name=agent-tests``) with
    sensitive ones (``password=hunter2``, ``token=abc123``).  The
    safe-log output must not contain either credential value.  Non-
    sensitive query keys MAY be preserved, or ALL query parameters MAY
    be removed wholesale; the contract only forbids credential leak.
    """
    dsn = (
        "postgresql+asyncpg://user:authority-secret@"
        "db.internal:5432/blueberry_peak"
        "?sslmode=require&application_name=agent-tests"
        "&password=hunter2&token=abc123"
    )
    output = render_dsn_for_log(dsn)
    assert "authority-secret" not in output
    assert "hunter2" not in output
    assert "abc123" not in output


def test_render_dsn_for_log_unparseable_fail_closed() -> None:
    """P1 / existing contract: malformed input must yield the fixed
    placeholder, NEVER echo the raw input.
    """
    assert render_dsn_for_log("not a url with password=hunter2") == "<unparseable PostgreSQL DSN>"


def test_explicit_override_is_trimmed_non_empty_value() -> None:
    """P2 from review 4681746668.

    The explicit ``BLUEBERRY_PG_DSN`` override path strips surrounding
    whitespace before returning the value.  The contract wording must
    say "trimmed non-empty override", not "verbatim".
    """
    raw = " postgresql+asyncpg://u:p@db:5432/custom "
    assert (
        resolve_postgres_test_dsn({"BLUEBERRY_PG_DSN": raw})
        == "postgresql+asyncpg://u:p@db:5432/custom"
    )


def test_explicit_override_legacy_name_remains_explicit_override() -> None:
    """P2 follow-up: the legacy database name remains accepted ONLY
    via the trimmed explicit override path (because the explicit
    override bypasses the ``_FORBIDDEN_DATABASES`` check — the legacy
    name is forbidden only when *derived* from ``POSTGRES_DB``).
    """
    explicit = "postgresql+asyncpg://u:p@db:5432/blueberry_peak_test_r7_round8"
    assert resolve_postgres_test_dsn({"BLUEBERRY_PG_DSN": explicit}) == explicit
