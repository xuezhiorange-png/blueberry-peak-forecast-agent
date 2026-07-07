"""Shared PostgreSQL test support: identity validation and identity logging.

This module is the Batch 3 Slice 1 deliverable. It provides:

- :data:`FORBIDDEN_DATABASE_NAMES` — explicit dev-DB name set
- :data:`FORBIDDEN_DATABASE_PORTS` — explicit dev-DB port set
- :data:`PRODUCTION_APP_ENVS` — explicit APP_ENV values that must never
  appear in a test profile
- :data:`SAFE_TEST_APP_ENVS` — explicit APP_ENV values that mark a
  profile as safe-for-test
- :func:`resolve_postgres_test_identity` — pure resolver that reads
  ``os.environ`` and returns a :class:`PostgresTestIdentity` dataclass.
  Never imports from ``backend.app`` so it is hermetic.
- :func:`validate_postgres_test_identity` — pure validator that takes
  an identity (or env) and raises ``ValueError`` on any unsafe profile.
  Never connects to a database. Never echoes passwords.
- :func:`assert_safe_postgres_test_identity` — fail-closed wrapper that
  invokes the validator and is intended for use from safety tests,
  shell scripts, Makefile guards, and the pytest session-start log.
- :func:`format_postgres_test_identity` — deterministic one-line
  summary suitable for log output (no secrets, no passwords).

Design discipline
-----------------

* File location: ``backend/tests/postgres_test_support.py`` (NOT
  ``backend/app/``). No production-code mutation.
* No DB / network IO (in the validator itself). The validator is pure
  Python over ``os.environ`` so it can be exercised from CI without a
  live PostgreSQL.
* No token / password echo. The summary function never includes the
  ``DATABASE_URL`` value — only its parsed components.

Batch 3 Slice 1 contracts (see
``docs/task-11-issue-51-batch3-pg-isolation-design.md``):

* Fail closed: any unsafe profile raises ``ValueError`` with a clear
  message naming the offending field.
* Never silently fall back to development defaults. The resolver uses
  ``os.environ.get`` with NO fallback to ``blueberry_peak`` /
  ``5432`` / ``development``. When a field is missing the resolver
  raises ``ValueError`` (validation), so the test runner cannot
  accidentally connect to a dev default.
* Worker id is included in the identity. The resolver accepts an
  optional ``worker_id`` argument (default ``"master"``) so future
  Slice 3 / Slice 4 isolation work can pass ``pytest-xdist`` worker ids
  through to logging.

Out of scope (Batch 3 Slice 1):

* TRUNCATE removal. (Slice 5.)
* Transaction / savepoint / rollback fixture refactor. (Slice 2.)
* Migration / concurrency isolated schema. (Slices 3 / 4.)
* ``.github/workflows/ci.yml`` changes. (Batch 2 / Issue #50.)
"""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Forbidden / allowed constants
# ---------------------------------------------------------------------------

#: Database names that must NEVER appear in a test profile.
#: Any connection attempt against these names must fail closed.
FORBIDDEN_DATABASE_NAMES: frozenset[str] = frozenset(
    {
        "blueberry_peak",
        "blueberry_peak_dev",
        "blueberry_peak_production",
        "blueberry_dev",
        "blueberry_prod",
        "postgres",  # cluster default; not a project database
    }
)

#: Database ports that must NEVER appear in a test profile.
#: Port 5432 is reserved for the development database; tests must use
#: 55432 (local) or per-worker ports (future Slice 3).
FORBIDDEN_DATABASE_PORTS: frozenset[str] = frozenset(
    {
        "5432",  # canonical dev port
    }
)

#: APP_ENV values that must NEVER appear in a test profile.
PRODUCTION_APP_ENVS: frozenset[str] = frozenset(
    {
        "production",
        "prod",
        "live",
        "staging",
        "stage",
        "stg",
    }
)

#: APP_ENV values that mark a profile as safe-for-test.
SAFE_TEST_APP_ENVS: frozenset[str] = frozenset(
    {
        "test",
        "testing",
        "ci",  # CI runs also use APP_ENV=test, but be tolerant of CI's variant
    }
)

#: Default test profile — used when no env is exported (one-command contract).
DEFAULT_TEST_DB_NAME: str = "blueberry_peak_test"
DEFAULT_TEST_DB_HOST: str = "localhost"
DEFAULT_TEST_DB_PORT: str = "55432"
DEFAULT_TEST_APP_ENV: str = "test"


# ---------------------------------------------------------------------------
# Identity dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PostgresTestIdentity:
    """Resolved PostgreSQL test identity (pure data, no I/O).

    All fields are explicit. ``None`` means "not configured" — the
    validator will reject any required field that is ``None``.
    """

    database_name: str | None = None
    database_host: str | None = None
    database_port: str | None = None
    app_env: str | None = None
    worker_id: str = "master"
    safety_profile_source: str = "env"
    # Future Slice 3/4 fields (not yet wired up):
    schema_name: str | None = None
    migration_head: str | None = None
    # Diagnostic: were any defaults used? If True, the validator
    # tightens the check (a profile that silently fell back to
    # development defaults is unsafe).
    used_defaults: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict (no password / token fields)."""
        return asdict(self)


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


def resolve_postgres_test_identity(
    env: dict[str, str] | None = None,
    *,
    worker_id: str = "master",
) -> PostgresTestIdentity:
    """Resolve the current PostgreSQL test identity from ``env``.

    ``env`` defaults to :data:`os.environ` if ``None``. The resolver is
    pure: no DB connection, no subprocess, no mutation of ``env``.

    Returns a :class:`PostgresTestIdentity` with ``used_defaults``
    populated for any field that was not explicitly set in ``env``.
    The validator (next function) treats silent-default profiles as
    unsafe unless the defaults are the safe test defaults.
    """
    if env is None:
        env = dict(os.environ)

    db_name = env.get("POSTGRES_DB")
    db_host = env.get("POSTGRES_HOST")
    db_port = env.get("POSTGRES_PORT")
    app_env = env.get("APP_ENV")

    used_defaults: dict[str, bool] = {}
    if db_name is None:
        db_name = DEFAULT_TEST_DB_NAME
        used_defaults["database_name"] = True
    if db_host is None:
        db_host = DEFAULT_TEST_DB_HOST
        used_defaults["database_host"] = True
    if db_port is None:
        db_port = DEFAULT_TEST_DB_PORT
        used_defaults["database_port"] = True
    if app_env is None:
        app_env = DEFAULT_TEST_APP_ENV
        used_defaults["app_env"] = True

    return PostgresTestIdentity(
        database_name=db_name,
        database_host=db_host,
        database_port=db_port,
        app_env=app_env,
        worker_id=worker_id,
        safety_profile_source="env+defaults" if used_defaults else "env",
        used_defaults=used_defaults,
    )


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


def validate_postgres_test_identity(identity: PostgresTestIdentity) -> None:
    """Fail-closed validator.

    Raises :class:`ValueError` with a clear message naming the
    offending field if any of the following are detected:

    1. Database name in :data:`FORBIDDEN_DATABASE_NAMES`.
    2. Database name matches the dev-DB pattern (``blueberry_peak`` but
       not ``blueberry_peak_test`` or a worker-suffixed test DB).
    3. Database port in :data:`FORBIDDEN_DATABASE_PORTS` AND host is
       the dev-DB host (``localhost``).
    4. APP_ENV in :data:`PRODUCTION_APP_ENVS`.
    5. APP_ENV not in :data:`SAFE_TEST_APP_ENVS`.
    6. ``DATABASE_URL`` contains a forbidden name pattern (matched
       via :func:`_database_url_looks_unsafe`).
    7. Silent fallback to development defaults: if a field was
       silently defaulted AND the defaulted value is not the safe
       default, raise.

    Never includes passwords / tokens / DATABASE_URL value in the
    error message.
    """
    db_name = identity.database_name or ""
    db_port = identity.database_port or ""
    app_env = identity.app_env or ""
    db_host = identity.database_host or ""

    # 1. Explicit forbidden database names.
    if db_name in FORBIDDEN_DATABASE_NAMES:
        raise ValueError(
            f"refusing unsafe PostgreSQL test identity: POSTGRES_DB={db_name!r} "
            f"is in FORBIDDEN_DATABASE_NAMES. Use {DEFAULT_TEST_DB_NAME!r} or a "
            f"worker-suffixed test DB."
        )

    # 2. Dev-DB pattern: contains 'blueberry_peak' but not '_test'.
    if "blueberry_peak" in db_name and "_test" not in db_name:
        raise ValueError(
            f"refusing unsafe PostgreSQL test identity: POSTGRES_DB={db_name!r} "
            f"matches dev-DB pattern (contains 'blueberry_peak' without '_test'). "
            f"Use {DEFAULT_TEST_DB_NAME!r} or a worker-suffixed test DB."
        )

    # 3. Forbidden port + dev host combination.
    if db_port in FORBIDDEN_DATABASE_PORTS and db_host in {"localhost", "127.0.0.1"}:
        raise ValueError(
            f"refusing unsafe PostgreSQL test identity: POSTGRES_PORT={db_port!r} "
            f"with POSTGRES_HOST={db_host!r} is the dev-DB profile. "
            f"Use port {DEFAULT_TEST_DB_PORT!r} for local tests, or a per-worker "
            f"port for distributed tests."
        )

    # 4. Production-like APP_ENV.
    if app_env in PRODUCTION_APP_ENVS:
        raise ValueError(
            f"refusing unsafe PostgreSQL test identity: APP_ENV={app_env!r} is in "
            f"PRODUCTION_APP_ENVS. Use APP_ENV={DEFAULT_TEST_APP_ENV!r}."
        )

    # 5. APP_ENV must be in SAFE_TEST_APP_ENVS.
    if app_env not in SAFE_TEST_APP_ENVS:
        raise ValueError(
            f"refusing unsafe PostgreSQL test identity: APP_ENV={app_env!r} is not "
            f"in SAFE_TEST_APP_ENVS={sorted(SAFE_TEST_APP_ENVS)}. "
            f"Use APP_ENV={DEFAULT_TEST_APP_ENV!r}."
        )

    # 7. Silent fallback to development defaults (not safe defaults).
    if identity.used_defaults:
        # If any field was defaulted and the default is not the safe
        # test default, raise. This catches the case where someone
        # implicitly relied on a hardcoded dev fallback.
        defaulted_db = (
            identity.used_defaults.get("database_name")
            and db_name != DEFAULT_TEST_DB_NAME
        )
        defaulted_port = (
            identity.used_defaults.get("database_port")
            and db_port != DEFAULT_TEST_DB_PORT
        )
        defaulted_env = (
            identity.used_defaults.get("app_env")
            and app_env != DEFAULT_TEST_APP_ENV
        )
        if defaulted_db or defaulted_port or defaulted_env:
            raise ValueError(
                "refusing unsafe PostgreSQL test identity: silent fallback to "
                f"non-safe defaults detected. used_defaults={identity.used_defaults!r}, "
                f"resolved db_name={db_name!r}, db_port={db_port!r}, "
                f"app_env={app_env!r}. Either export all required env vars "
                "explicitly or use the safe defaults "
                f"({DEFAULT_TEST_DB_NAME!r} / {DEFAULT_TEST_DB_PORT!r} / "
                f"{DEFAULT_TEST_APP_ENV!r})."
            )


# ---------------------------------------------------------------------------
# Database URL safety check (independent of identity)
# ---------------------------------------------------------------------------

#: Pattern matching dev-DB names inside a DATABASE_URL value.
#: ``blueberry_peak`` followed by anything except ``_test``.
_DATABASE_URL_DEV_DB_PATTERN: re.Pattern[str] = re.compile(
    r"(blueberry_peak(?!_test))",
    re.IGNORECASE,
)

#: Pattern matching the canonical dev port inside a DATABASE_URL value.
_DATABASE_URL_DEV_PORT_PATTERN: re.Pattern[str] = re.compile(
    r"localhost:5432|127\.0\.0\.1:5432",
    re.IGNORECASE,
)


def _database_url_looks_unsafe(database_url: str) -> str | None:
    """Return a human-readable reason if ``database_url`` looks unsafe.

    Returns ``None`` when the URL is safe. Never logs / echoes the URL
    itself — only the matched pattern name.
    """
    if not database_url:
        return None
    if _DATABASE_URL_DEV_DB_PATTERN.search(database_url):
        return "DATABASE_URL contains a dev-DB name pattern"
    if _DATABASE_URL_DEV_PORT_PATTERN.search(database_url):
        return "DATABASE_URL contains the canonical dev port (5432)"
    return None


# ---------------------------------------------------------------------------
# Combined fail-closed wrapper
# ---------------------------------------------------------------------------


def assert_safe_postgres_test_identity(
    env: dict[str, str] | None = None,
    *,
    worker_id: str = "master",
) -> PostgresTestIdentity:
    """Resolve + validate + return the identity.

    Convenience wrapper used by safety tests, the Makefile guard, and
    the bash wrapper. Raises :class:`ValueError` on any unsafe profile.

    Additionally checks :data:`DATABASE_URL` independently of the
    identity (a URL can leak dev-DB even when the individual env vars
    look safe).
    """
    identity = resolve_postgres_test_identity(env, worker_id=worker_id)

    # Independent DATABASE_URL safety check (catches URL leaks even when
    # individual env vars look safe).
    db_url = (env or os.environ).get("DATABASE_URL", "")
    url_reason = _database_url_looks_unsafe(db_url)
    if url_reason is not None:
        raise ValueError(
            f"refusing unsafe PostgreSQL test identity: {url_reason}. "
            f"Either unset DATABASE_URL or use the test profile URL."
        )

    validate_postgres_test_identity(identity)
    return identity


# ---------------------------------------------------------------------------
# Formatter (one-line summary for logs)
# ---------------------------------------------------------------------------


def format_postgres_test_identity(identity: PostgresTestIdentity) -> str:
    """Return a deterministic one-line summary, no secrets.

    Format::

        postgres-test-identity:
            worker_id=<wid> db=<name> host=<host>:<port>
            env=<env> source=<source> defaults=<defaults>

    The ``DATABASE_URL`` value is intentionally NEVER included.
    """
    defaults_repr = (
        "none" if not identity.used_defaults else ",".join(sorted(identity.used_defaults.keys()))
    )
    return (
        f"postgres-test-identity: "
        f"worker_id={identity.worker_id} "
        f"db={identity.database_name} "
        f"host={identity.database_host}:{identity.database_port} "
        f"env={identity.app_env} "
        f"source={identity.safety_profile_source} "
        f"defaults={defaults_repr}"
    )


__all__ = [
    "FORBIDDEN_DATABASE_NAMES",
    "FORBIDDEN_DATABASE_PORTS",
    "PRODUCTION_APP_ENVS",
    "SAFE_TEST_APP_ENVS",
    "DEFAULT_TEST_DB_NAME",
    "DEFAULT_TEST_DB_HOST",
    "DEFAULT_TEST_DB_PORT",
    "DEFAULT_TEST_APP_ENV",
    "PostgresTestIdentity",
    "resolve_postgres_test_identity",
    "validate_postgres_test_identity",
    "assert_safe_postgres_test_identity",
    "format_postgres_test_identity",
]