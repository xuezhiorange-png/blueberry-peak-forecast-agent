"""Slice 1 (continued) — pure validator and dataclass for Postgres test identity.

Carried forward from Batch 3 Slice 1 (per PR #47 / Issue #23 sub-area 1).
Provides the safety predicates used by the dev-DB safeguard and the
``Makefile test-pg`` guard.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from urllib.parse import urlparse

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

    Public field compatibility (per PR #69 P0-2 fix + Charles brief
    "Preserve old PostgresTestIdentity public fields or provide
    explicit compatibility tests"):

    * ``database_host`` is an alias for :attr:`host` (legacy name).
      Both the constructor kwarg and the read-only attribute are
      supported.
    * ``database_port`` is an alias for :attr:`port` (legacy name).
      Both the constructor kwarg and the read-only attribute are
      supported.
    * ``used_defaults`` may be set as either a ``dict[str, bool]``
      (legacy form, used by ``backend.tests.safety.test_dev_db_safeguard_slice1``)
      or a ``tuple[str, ...]`` (current form). When set as a dict,
      the keys are normalized to a tuple internally.
    * ``safety_profile_source`` is exposed as a derived property
      (``"env"`` when no defaults used, ``"env+defaults"`` otherwise).

    The canonical / canonical-name fields are :attr:`host` and
    :attr:`port` (matching the production-side naming); the legacy
    aliases are kept so pre-PR-69 callers (and the Batch 3 Slice 1
    test suite) continue to work.
    """

    # Canonical fields (current production-side naming).
    database_name: str = ""
    port: int = 0
    app_env: str = ""
    database_user: str = ""
    host: str = ""
    worker_id: str = "master"
    used_defaults: tuple[str, ...] = field(default_factory=tuple)

    def __init__(
        self,
        database_name: str = "",
        port: int | None = None,
        app_env: str = "",
        database_user: str = "",
        host: str | None = None,
        worker_id: str = "master",
        used_defaults: tuple[str, ...] | dict[str, bool] | None = None,
        # Legacy kwargs (Batch 3 Slice 1 / pre-PR-69 callers).
        database_host: str | None = None,
        database_port: int | None = None,
    ) -> None:
        # Resolve host / database_host.
        resolved_host = host if host is not None else (database_host or "")
        # Resolve port / database_port.
        resolved_port = (
            port if port is not None else (database_port if database_port is not None else 0)
        )
        # Normalize used_defaults: dict[str, bool] → tuple[str, ...] of keys.
        if used_defaults is None:
            resolved_defaults: tuple[str, ...] = ()
        elif isinstance(used_defaults, dict):
            resolved_defaults = tuple(used_defaults.keys())
        else:
            resolved_defaults = tuple(used_defaults)
        # Assign via object.__setattr__ because the dataclass is frozen.
        object.__setattr__(self, "database_name", database_name)
        object.__setattr__(self, "port", resolved_port)
        object.__setattr__(self, "app_env", app_env)
        object.__setattr__(self, "database_user", database_user)
        object.__setattr__(self, "host", resolved_host)
        object.__setattr__(self, "worker_id", worker_id)
        object.__setattr__(self, "used_defaults", resolved_defaults)

    @property
    def database_host(self) -> str:
        """Legacy alias for :attr:`host` (Batch 3 Slice 1 compatibility)."""
        return self.host

    @property
    def database_port(self) -> int:
        """Legacy alias for :attr:`port` (Batch 3 Slice 1 compatibility)."""
        return self.port

    @property
    def safety_profile_source(self) -> str:
        """Whether the identity was fully env-supplied or fell back to defaults.

        ``"env"`` when ``used_defaults`` is empty; ``"env+defaults"``
        otherwise. Legacy field preserved from Batch 3 Slice 1.
        """
        return "env" if not self.used_defaults else "env+defaults"

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


def _parse_database_url_safely(url: str) -> tuple[str, str, int] | None:
    """Parse a ``DATABASE_URL`` and return ``(database, host, port)``.

    Returns ``None`` when the URL is empty, malformed, or carries no
    resolvable database name. The parser is deliberately lenient — we
    only use it to extract the database name (the dev-DB safeguard's
    fail-closed predicate). The password component is **never** read
    and the original URL is **never** echoed into error messages.

    This is a defensive helper used by
    :func:`assert_safe_postgres_test_identity` to honor the
    Batch 3 Slice 1 contract that an obviously unsafe
    ``DATABASE_URL`` (one that points at a dev/prod database name
    or the cluster default) must be rejected independently from
    the typed identity object.
    """
    if not url or not isinstance(url, str):
        return None
    candidate = url.strip()
    if not candidate:
        return None
    try:
        parsed = urlparse(candidate)
    except (TypeError, ValueError):
        return None
    # urlparse puts the path in ``path`` (e.g. "/blueberry_peak").
    db_name = (parsed.path or "").lstrip("/")
    if not db_name:
        return None
    host = parsed.hostname or ""
    try:
        port = parsed.port if parsed.port is not None else 5432
    except ValueError:
        port = 5432
    return db_name, host, port


def _validate_database_url(url: str) -> None:
    """Fail-closed validator for a ``DATABASE_URL`` value.

    Raises :class:`ValueError` if the URL points at a forbidden
    database name (e.g. ``blueberry_peak``) or the cluster default
    ``postgres``. The error message contains the ``"dev-DB"``
    substring that the Slice 5 regression tests in
    ``backend/tests/integration/test_isolate_master_data_tables_slice5.py``
    pin, and **never** echoes the full URL or any password component.

    A URL that does not parse cleanly is treated as benign (the
    typed-identity validator below still runs).
    """
    parsed = _parse_database_url_safely(url)
    if parsed is None:
        return
    db_name, _host, _port = parsed
    if db_name in FORBIDDEN_DATABASE_NAMES:
        # Pin the "dev-DB" substring for regression tests, but never
        # echo the URL / db_name verbatim — those may carry secrets.
        raise ValueError(
            "refuse to connect to dev-DB via DATABASE_URL: "
            "target database name is forbidden by the Slice 1 "
            "dev-DB safeguard (input redacted for safety)"
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
        raise ValueError(f"refuse to connect to forbidden port: {identity.port}")
    if identity.app_env in PRODUCTION_APP_ENVS:
        raise ValueError(f"refuse to connect with APP_ENV={identity.app_env!r} (must be test)")
    if identity.app_env not in SAFE_TEST_APP_ENVS:
        raise ValueError(
            f"APP_ENV must be one of {sorted(SAFE_TEST_APP_ENVS)}, got {identity.app_env!r}"
        )


def assert_safe_postgres_test_identity(
    env: dict[str, str] | None = None,
    *,
    worker_id: str = "master",
) -> PostgresTestIdentity:
    """Resolve and validate a Postgres test identity (fail-closed).

    The validator runs in two layers, in this order:

    1. **DATABASE_URL guard** — if ``DATABASE_URL`` is present in
       ``env`` (or the process environment), parse the URL and
       reject if its target database name is in
       :data:`FORBIDDEN_DATABASE_NAMES`. This honors the Batch 3
       Slice 1 contract that an obviously unsafe ``DATABASE_URL``
       must be rejected independently from the typed identity
       object. The error message contains the ``"dev-DB"``
       substring pinned by the Slice 5 regression tests.
    2. **Typed-identity guard** — resolve
       :class:`PostgresTestIdentity` from ``POSTGRES_DB`` /
       ``POSTGRES_PORT`` / ``APP_ENV`` / ``POSTGRES_USER`` /
       ``POSTGRES_HOST`` and run
       :func:`validate_postgres_test_identity` (fail-closed on
       forbidden names / ports / APP_ENV).
    """
    src = os.environ if env is None else env
    database_url = src.get("DATABASE_URL", "")
    if database_url:
        _validate_database_url(database_url)
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
