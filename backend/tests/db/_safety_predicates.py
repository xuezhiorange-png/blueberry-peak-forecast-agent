"""Slice 1 (continued) — pure validator and dataclass for Postgres test identity.

Carried forward from Batch 3 Slice 1 (per PR #47 / Issue #23 sub-area 1).
Provides the safety predicates used by the dev-DB safeguard and the
``Makefile test-pg`` guard.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

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

#: Ports that must NEVER appear in a test profile.
FORBIDDEN_DATABASE_PORTS: frozenset[int] = frozenset({5432})

#: APP_ENV values that must NEVER appear in a test profile.
PRODUCTION_APP_ENVS: frozenset[str] = frozenset(
    {"production", "prod", "dev", "development", "staging"}
)

#: APP_ENV values that mark a profile as safe-for-test.
SAFE_TEST_APP_ENVS: frozenset[str] = frozenset({"test"})

#: Default database name used when env doesn't supply one.
DEFAULT_TEST_DB_NAME: str = "blueberry_peak_test"

#: Default port used when env doesn't supply one.
DEFAULT_TEST_DB_PORT: int = 55432

#: Default APP_ENV used when env doesn't supply one.
DEFAULT_TEST_APP_ENV: str = "test"

#: Default database user used when env doesn't supply one.
DEFAULT_TEST_DB_USER: str = "postgres"

#: Default host used when env doesn't supply one.
DEFAULT_TEST_DB_HOST: str = "localhost"


@dataclass(frozen=True)
class PostgresTestIdentity:
    """Resolved Postgres test identity (pure data, no I/O).

    All fields are populated by :func:`resolve_postgres_test_identity`.
    Defaults are recorded in ``used_defaults`` so the validator and
    the formatter can distinguish explicit profiles from safe
    fallbacks.
    """

    database_name: str
    port: int
    app_env: str
    database_user: str
    host: str
    worker_id: str = "master"
    used_defaults: tuple[str, ...] = field(default_factory=tuple)

    def to_summary(self) -> str:
        return format_postgres_test_identity(self)


def resolve_postgres_test_identity(
    env: dict[str, str] | None = None,
    *,
    worker_id: str = "master",
) -> PostgresTestIdentity:
    """Resolve a Postgres test identity from a given env (default ``os.environ``)."""
    src = os.environ if env is None else env
    used: list[str] = []

    def pick(name: str, default: str) -> str:
        raw = src.get(name, "").strip()
        if raw:
            return raw
        used.append(name)
        return default

    db_name = pick("POSTGRES_DB", DEFAULT_TEST_DB_NAME)
    port_str = pick("POSTGRES_PORT", str(DEFAULT_TEST_DB_PORT))
    app_env = pick("APP_ENV", DEFAULT_TEST_APP_ENV)
    db_user = pick("POSTGRES_USER", DEFAULT_TEST_DB_USER)
    host = pick("POSTGRES_HOST", DEFAULT_TEST_DB_HOST)

    return PostgresTestIdentity(
        database_name=db_name,
        port=int(port_str),
        app_env=app_env,
        database_user=db_user,
        host=host,
        worker_id=worker_id,
        used_defaults=tuple(used),
    )


def validate_postgres_test_identity(identity: PostgresTestIdentity) -> None:
    """Fail-closed validator.

    Raises :class:`ValueError` on any unsafe profile. Pure function over
    the identity dataclass; never connects to a database.
    """
    if identity.database_name in FORBIDDEN_DATABASE_NAMES:
        raise ValueError(
            f"refuse to connect to forbidden database name: {identity.database_name!r}"
        )
    if identity.port in FORBIDDEN_DATABASE_PORTS:
        raise ValueError(
            f"refuse to connect to forbidden port: {identity.port}"
        )
    if identity.app_env in PRODUCTION_APP_ENVS:
        raise ValueError(
            f"refuse to connect with APP_ENV={identity.app_env!r} (must be test)"
        )
    if identity.app_env not in SAFE_TEST_APP_ENVS:
        raise ValueError(
            f"APP_ENV must be one of {sorted(SAFE_TEST_APP_ENVS)}, got {identity.app_env!r}"
        )


def assert_safe_postgres_test_identity(
    env: dict[str, str] | None = None,
    *,
    worker_id: str = "master",
) -> PostgresTestIdentity:
    """Resolve and validate a Postgres test identity (fail-closed)."""
    identity = resolve_postgres_test_identity(env, worker_id=worker_id)
    validate_postgres_test_identity(identity)
    return identity


def format_postgres_test_identity(identity: PostgresTestIdentity) -> str:
    """Format identity for log output (no secrets, no passwords)."""
    return (
        f"db={identity.database_name} port={identity.port} "
        f"app_env={identity.app_env} user={identity.database_user} "
        f"host={identity.host} worker={identity.worker_id}"
    )


__all__ = [
    "FORBIDDEN_DATABASE_NAMES",
    "FORBIDDEN_DATABASE_PORTS",
    "PRODUCTION_APP_ENVS",
    "SAFE_TEST_APP_ENVS",
    "DEFAULT_TEST_DB_NAME",
    "DEFAULT_TEST_DB_PORT",
    "DEFAULT_TEST_APP_ENV",
    "DEFAULT_TEST_DB_USER",
    "DEFAULT_TEST_DB_HOST",
    "PostgresTestIdentity",
    "resolve_postgres_test_identity",
    "validate_postgres_test_identity",
    "assert_safe_postgres_test_identity",
    "format_postgres_test_identity",
]