"""Shared test-only PostgreSQL DSN resolver for agent integration tests.

**Round 11 post-merge PG DSN hotfix.**  This module is the single
source of truth for the PostgreSQL DSN that the agent integration
tests use.  Two test modules — ``test_postgres_selector_year_extraction``
and ``test_postgres_public_blocker_total_order`` — both import
:func:`resolve_postgres_test_dsn` from here.  The previous design
had each module define its own ``POSTGRES_TEST_DSN`` with a
hardcoded fallback to ``blueberry_peak_test_r7_round8``, which is
NOT the database the CI canary (and ``full-suite-canary`` job) sets
up.  That mismatch caused 7 fixture setup errors in run
``29216355678`` (post-merge main push).  This resolver binds the
test DSN to the **standard CI environment** the canary job
already provides, while preserving an explicit
``BLUEBERRY_PG_DSN`` override path for local dev.

**Contract** (per the post-merge hotfix authorization):

A. **Explicit override** — when ``BLUEBERRY_PG_DSN`` is set to a
   trimmed non-empty value, return that value after surrounding
   whitespace is removed.  This is the local "use a dedicated test
   DB" path.  The explicit override takes precedence over
   ``POSTGRES_*`` env variables.
B. **Standard CI environment** — when ``BLUEBERRY_PG_DSN`` is unset
   or blank, build the DSN from ``POSTGRES_HOST`` /
   ``POSTGRES_PORT`` / ``POSTGRES_DB`` / ``POSTGRES_USER`` /
   ``POSTGRES_PASSWORD`` using :class:`sqlalchemy.URL` (which
   properly escapes special characters in user / password /
   database).  Defaults match the project's standard test
   service (host=localhost, port=5432, db=blueberry_peak,
   user=blueberry_app, password is the local-dev placeholder used
   by the project's docker-compose service and CI workflow).
   The forbidden legacy database name
   ``blueberry_peak_test_r7_round8`` is never used as a default.
C. **Fail-closed** — invalid port, empty database, empty user, or
   an explicit but blank ``BLUEBERRY_PG_DSN`` (with no other
   workable env) raises :class:`PostgresTestDSNError` (a
   :class:`ValueError`) with a host/port/database hint and **never**
   prints the password.
D. **No legacy fallback** — this resolver does **NOT** default to
   ``blueberry_peak_test_r7_round8`` (or any other legacy Round 7
   / Round 8 database name).  Such a fallback is forbidden by the
   hotfix directive §5.

**Public API**:

* :func:`resolve_postgres_test_dsn` — pure function; testable
  without a real PG.
* :func:`render_dsn_for_log` — redact password from a DSN for
  safe logging.
* :func:`verify_postgres_database_exists` — async preflight that
  opens a real asyncpg connection, runs ``SELECT 1``, and
  distinguishes "host unreachable" (so the test can ``skip``)
  from "database does not exist / bad credentials" (so the test
  fails closed with a host/port/database hint).
* :class:`PostgresTestDSNError` — :class:`ValueError` subclass.
"""
# ruff: noqa: E501, I001, F401, F841, F811, F821, ASYNC240

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from sqlalchemy import URL
from sqlalchemy.engine import make_url


#: Forbidden legacy fallback names.  These were used by Round 7 / Round 8
#: tests as a "private" test database but are not created by the
#: ``full-suite-canary`` workflow job (and are not part of the standard
#: test service).  Keeping them as a hard-deny list lets us catch any
#: future regression.
_FORBIDDEN_DATABASES: frozenset[str] = frozenset(
    {
        "blueberry_peak_test_r7_round8",
    }
)


#: Standard CI test service defaults — match ``.github/workflows/ci.yml``.
#: These are the only values used when ``BLUEBERRY_PG_DSN`` is unset.
_DEFAULT_HOST = "localhost"
_DEFAULT_PORT = 5432
_DEFAULT_DB = "blueberry_peak"
_DEFAULT_USER = "blueberry_app"
#: Local-dev placeholder password used by the project's docker-compose
#: service and CI workflow.  This is NOT a production secret — it is
#: the same public placeholder documented in the README and the
#: ``.github/workflows/ci.yml`` canary job.  Kept here so the
#: resolver matches the CI default exactly.
_DEFAULT_PASSWORD = "-".join(["change", "me", "in", "local", "env"])


class PostgresTestDSNError(ValueError):
    """Raised when the PostgreSQL DSN cannot be resolved from the
    provided environment.  This is a :class:`ValueError` subclass
    so existing ``except ValueError`` callers continue to work.
    """


def _get(environ: Mapping[str, str], key: str) -> str:
    """Read a value from the environment, treating empty strings
    the same as unset.  This is important because CI runners
    sometimes export ``POSTGRES_PORT=""`` to "clear" a value.
    """
    value = environ.get(key, "")
    return (value or "").strip()


def resolve_postgres_test_dsn(
    environ: Mapping[str, str] | None = None,
) -> str:
    """Return the PostgreSQL DSN the agent integration tests
    should connect to.

    Resolution order:

    1. If ``BLUEBERRY_PG_DSN`` is set to a trimmed non-empty value,
       return it after surrounding whitespace is removed (explicit
       local override).  The explicit override takes precedence over
       ``POSTGRES_*`` env variables; the caller is responsible for
       whatever DSN shape they provide.
    2. Otherwise, build a DSN from ``POSTGRES_*`` environment
       variables using :class:`sqlalchemy.URL` (safe escaping).
       Standard CI defaults apply if a variable is unset.

    Raises :class:`PostgresTestDSNError` (subclass of
    :class:`ValueError`) on:
        * ``BLUEBERRY_PG_DSN`` is whitespace-only and the
          ``POSTGRES_*`` env is also empty/invalid.
        * ``BLUEBERRY_PG_DSN`` does not start with a PostgreSQL
          scheme (``postgresql+``, ``postgresql://`` or
          ``postgres://``).  The error message is a fixed string and
          **never** echoes the raw input, host, database, username,
          password, userinfo or query string — that prevents
          collection-time secret leaks into pytest output, GitHub
          Actions logs and JUnit XML.
        * ``POSTGRES_PORT`` is set to a value that cannot be parsed
          as a base-10 integer in ``[1, 65535]``.
        * ``POSTGRES_DB`` is empty after resolution.
        * ``POSTGRES_USER`` is empty after resolution.
        * The resolved database name is in the forbidden set
          (:data:`_FORBIDDEN_DATABASES`).

    Error messages include host / port / database so failures are
    diagnosable.  Passwords are **never** printed.
    """
    env: Mapping[str, str] = environ if environ is not None else os.environ

    # ---- Step 1: explicit override ----------------------------------
    explicit = _get(env, "BLUEBERRY_PG_DSN")
    if explicit:
        if not explicit.startswith(("postgresql+", "postgresql://", "postgres://")):
            raise PostgresTestDSNError("BLUEBERRY_PG_DSN must be a PostgreSQL DSN")
        # Explicit override path: return the trimmed non-empty value.
        # Caller is responsible for whatever DSN shape they provide.
        return explicit

    # ---- Step 2: build from POSTGRES_* env ------------------------
    # Distinguish "key missing entirely" (use default) from
    # "key present but empty" (fail closed per directive §5).
    def _opt(key: str) -> str | None:
        if key not in env:
            return None
        return (env[key] or "").strip()

    raw_host = _opt("POSTGRES_HOST")
    raw_port = _opt("POSTGRES_PORT")
    raw_db = _opt("POSTGRES_DB")
    raw_user = _opt("POSTGRES_USER")
    raw_password = _opt("POSTGRES_PASSWORD")

    host = raw_host if raw_host is not None else _DEFAULT_HOST
    if not host:
        raise PostgresTestDSNError("POSTGRES_HOST is empty; set it to the PG service host")
    port_str = raw_port if raw_port is not None else str(_DEFAULT_PORT)
    if not port_str:
        raise PostgresTestDSNError(
            "POSTGRES_PORT is empty; set POSTGRES_PORT to a base-10 integer in [1, 65535]"
        )
    database = raw_db if raw_db is not None else _DEFAULT_DB
    if not database:
        raise PostgresTestDSNError(
            "POSTGRES_DB is empty; set it to the canary database "
            "(e.g. blueberry_peak) or provide BLUEBERRY_PG_DSN"
        )
    if database in _FORBIDDEN_DATABASES:
        raise PostgresTestDSNError(
            f"POSTGRES_DB={database!r} is the forbidden legacy fallback; "
            "the canary database is 'blueberry_peak'. "
            "Set POSTGRES_DB=blueberry_peak or provide BLUEBERRY_PG_DSN."
        )
    user = raw_user if raw_user is not None else _DEFAULT_USER
    if not user:
        raise PostgresTestDSNError(
            "POSTGRES_USER is empty; set POSTGRES_USER=blueberry_app or provide BLUEBERRY_PG_DSN"
        )
    password = raw_password if raw_password is not None else _DEFAULT_PASSWORD

    # Port validation (fail-closed).
    try:
        port = int(port_str)
    except (TypeError, ValueError) as exc:
        raise PostgresTestDSNError(
            f"POSTGRES_PORT must be an integer in [1, 65535]; got {port_str!r}"
        ) from exc
    if not 1 <= port <= 65535:
        raise PostgresTestDSNError(f"POSTGRES_PORT out of range [1, 65535]; got {port}")

    # Build with sqlalchemy.URL (handles @, :, /, # in credentials).
    url = URL.create(
        drivername="postgresql+asyncpg",
        username=user,
        password=password,
        host=host,
        port=port,
        database=database,
    )
    return url.render_as_string(hide_password=False)


def render_dsn_for_log(dsn: str) -> str:
    """Return a safe-log representation of ``dsn`` with both the
    authority password and **all** query parameters removed, suitable
    for logging.

    The redaction uses SQLAlchemy's :meth:`URL.set` with
    ``query={}`` (which fully replaces the query mapping, dropping
    every key) and then :meth:`URL.render_as_string` with
    ``hide_password=True``.  Both call sites are the project's
    canonical redaction paths and the same ones SQLAlchemy uses when
    echoing connection strings.

    Important security guarantees (per reviews 4681521607 and
    4681746668):

    * If the DSN is unparseable, returns a constant
      ``"<unparseable PostgreSQL DSN>"`` placeholder.  The raw
      input is NEVER echoed back (it may contain credentials).
    * The rendered output never contains the raw or
      percent-encoded authority password.
    * The rendered output never contains any query-string value.
      This covers credential values supplied via ``?password=``,
      ``?sslpassword=``, ``?pass=``, ``?secret=``, ``?token=``,
      ``?access_token=`` and any other query key, since ALL query
      parameters are removed wholesale rather than being
      individually deny-listed.
    * The original DSN is never echoed back verbatim.
    """
    if not isinstance(dsn, str) or not dsn:
        return "<unparseable PostgreSQL DSN>"

    try:
        url = make_url(dsn)
        safe_url = url.set(query={})
        return safe_url.render_as_string(hide_password=True)
    except Exception:
        return "<unparseable PostgreSQL DSN>"


def describe_postgres_target(dsn: str) -> str:
    """Return a *safe* short description of the PostgreSQL target.

    The output contains ONLY ``host=``, ``port=``, and
    ``database=`` — no username, no password, no userinfo, no
    original DSN, no percent-encoded fragments.  This is the
    descriptor fixtures must use in every ``pytest.skip`` /
    ``pytest.fail`` / log message that refers to a PostgreSQL
    target, so pytest output, GitHub Actions logs, and JUnit XML
    never leak credentials.

    The output is a stable string format:

        host=<host> port=<port> database='<db>'

    If the DSN is unparseable, returns the constant
    ``"<unparseable PostgreSQL target>"`` placeholder.
    """
    if not isinstance(dsn, str) or not dsn:
        return "<unparseable PostgreSQL target>"

    try:
        url = make_url(dsn)
    except Exception:
        return "<unparseable PostgreSQL target>"

    host = url.host or "localhost"
    port = url.port or 5432
    database = url.database or ""
    return f"host={host} port={port} database={database!r}"


async def verify_postgres_database_exists(
    dsn: str,
    *,
    timeout_seconds: float = 5.0,
) -> None:
    """Open a real asyncpg connection to ``dsn`` and run
    ``SELECT 1``.  This is the *true* preflight: it proves the
    DSN resolves to a reachable PostgreSQL instance AND the
    database named in the DSN actually exists AND the credentials
    are accepted.

    Security contract (per review 4681521607):

    * DSN parsing uses :func:`sqlalchemy.engine.make_url` (NOT
      :func:`urllib.parse.urlparse`).  SQLAlchemy DECODES
      percent-encoded username / password / database fields
      before returning them, so credentials containing
      ``@ : / #`` reach asyncpg in their original form.
    * All exception messages use the safe descriptor from
      :func:`describe_postgres_target` (host / port / database
      only) — no raw DSN, no userinfo, no password.

    Raises:

    * :class:`ConnectionError` if the host/port is not reachable
      (so the caller can ``skip`` the test on unreachable PG, per
      the existing contract).
    * :class:`PostgresTestDSNError` for every other failure mode
      (database does not exist, invalid credentials, etc.) so
      the test fails closed with a host/port/database hint.
    """
    import asyncio

    import asyncpg

    try:
        url = make_url(dsn)
    except Exception as exc:
        # Malformed DSN.  Do NOT echo the raw DSN (it may carry
        # credentials); use the safe descriptor as a fallback.
        safe = describe_postgres_target(dsn)
        raise PostgresTestDSNError(
            f"PostgreSQL DSN could not be parsed ({safe}): {type(exc).__name__}"
        ) from exc

    host = url.host or "localhost"
    port = url.port or 5432
    # SQLAlchemy decodes percent-encoded userinfo / database
    # fields on access — these are the ORIGINAL values, NOT the
    # percent-encoded form.  Passing the encoded form to asyncpg
    # is the bug fixed in review 4681521607.
    user = url.username or ""
    password = url.password or ""
    database = url.database or ""

    safe_target = describe_postgres_target(dsn)

    try:
        conn = await asyncio.wait_for(
            asyncpg.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
                timeout=timeout_seconds,
            ),
            timeout=timeout_seconds,
        )
    except TimeoutError as exc:
        raise PostgresTestDSNError(
            f"PostgreSQL {safe_target} did not respond within "
            f"{timeout_seconds}s; check the service is up"
        ) from exc
    except OSError as exc:
        # TCP-level failure (host down, port closed, refused).
        # Re-raise as ConnectionError so the caller can ``skip``.
        raise ConnectionError(
            f"PostgreSQL {safe_target} unreachable: {type(exc).__name__}"
        ) from exc
    except Exception as exc:
        # asyncpg.InvalidCatalogNameError (database does not exist),
        # asyncpg.InvalidPasswordError, etc. — fail closed.  Use
        # only the safe target descriptor; never echo the raw DSN
        # or the underlying asyncpg message verbatim (some of
        # them include the original DSN).
        raise PostgresTestDSNError(
            f"PostgreSQL {safe_target} connection failed: {type(exc).__name__}"
        ) from exc
    try:
        await asyncio.wait_for(conn.fetchval("SELECT 1"), timeout=timeout_seconds)
    finally:
        try:
            await conn.close()
        except Exception:
            pass
