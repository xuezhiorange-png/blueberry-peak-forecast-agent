"""Slice 3 — pure helper-contract tests for the isolated PostgreSQL profile.

This file is a **pure helper-contract test** for
:mod:`backend.tests.migration_isolation_helpers` (the pure helper that
the ``postgres-migration`` GitHub Actions job uses to derive and guard
its per-run isolated database name).

Property: this file does **not** open a PostgreSQL connection. It is
a pure-python validator of the helper, so it is safe to run on hosts
without PostgreSQL.

Marker / CI ownership (corrected contract):

* This file is marked ``pytest.mark.postgres`` (see ``pytestmark``
  below). The ``unit-contract-golden`` CI job selects tests with
  ``-m "not integration and not postgres and not postgres_concurrency"``,
  so this file is **explicitly excluded** from
  ``unit-contract-golden``. Running it there would be a mistake, not
  a feature: the contract being asserted is the *isolated-DB profile*
  used by the destructive ``postgres-migration`` job, not the
  unit-contract path.
* This file is **owned** by the ``postgres-migration`` job, which
  lists it explicitly in its ``pytest`` invocation in
  ``.github/workflows/ci.yml`` (the ``-m`` selector does not apply to
  a hand-listed file). It is the only CI job that runs these tests.
* This file is intentionally **not** placed under
  ``backend/tests/integration/`` to avoid being collected by any
  future integration-shard wiring.

This PR does **not** add a live-PG companion assertion
(``test_alembic_round_trip_uses_isolated_database``) under
``backend/tests/integration/`` or elsewhere. The CI round-trip
itself is the only live evidence in this slice; it is asserted at
the *CI step* level (the ``alembic upgrade head`` /
``downgrade 0010_harvest_state_persistence`` / ``upgrade head``
chain), not by a pytest module. This file's job is to pin the
helper contract so the CI step cannot silently drift.
"""

from __future__ import annotations

import pytest

from backend.tests.migration_isolation_helpers import (
    ISOLATED_DB_NAME_PREFIX,
    MAX_ISOLATED_DB_NAME_LEN,
    assert_safe_isolated_db_name,
    resolve_isolated_db_name,
)
from backend.tests.postgres_test_support import FORBIDDEN_DATABASE_NAMES

# Mark this file ``postgres`` so the ``unit-contract-golden`` job's
# ``-m "not integration and not postgres and not postgres_concurrency"``
# selector **excludes** it. The ``postgres-migration`` job lists the
# file explicitly in its ``pytest`` invocation, so the marker is not a
# no-op for that job — it only governs whether the contract tests get
# collected by other shards.
# Slice 1 Batch 4 marker annotation: add ``migration`` (canonical
# Issue #52 taxonomy) additively. Ownership remains ``postgres-migration``
# per ci-shard-manifest.yml.
pytestmark = [pytest.mark.postgres, pytest.mark.migration]


# ---------------------------------------------------------------------------
# resolve_isolated_db_name
# ---------------------------------------------------------------------------


def test_resolve_isolated_db_name_uses_canonical_template() -> None:
    """The resolved name must be ``prefix + run_id + _ + attempt + _ + job``."""
    name = resolve_isolated_db_name(28869639380, 1, "postgres_migration")
    assert name == f"{ISOLATED_DB_NAME_PREFIX}28869639380_1_postgres_migration"


def test_resolve_isolated_db_name_accepts_numeric_strings() -> None:
    """GitHub exposes run_id / run_attempt as strings; helpers must accept both."""
    int_form = resolve_isolated_db_name(42, 1, "postgres_migration")
    str_form = resolve_isolated_db_name("42", "1", "postgres_migration")
    assert int_form == str_form


def test_resolve_isolated_db_name_distinguishes_attempts() -> None:
    """Two attempts of the same run must produce two distinct names."""
    first = resolve_isolated_db_name(28869639380, 1, "postgres_migration")
    second = resolve_isolated_db_name(28869639380, 2, "postgres_migration")
    assert first != second
    assert first.endswith("_1_postgres_migration")
    assert second.endswith("_2_postgres_migration")


def test_resolve_isolated_db_name_distinguishes_jobs() -> None:
    """Different job names must produce different databases."""
    a = resolve_isolated_db_name(100, 1, "postgres_migration")
    b = resolve_isolated_db_name(100, 1, "postgres_domain_1")
    assert a != b


def test_resolve_isolated_db_name_contains_test_marker() -> None:
    """Every resolved name must contain the ``_test_`` substring.

    The slice-1 dev-DB safeguard
    (:func:`backend.tests.postgres_test_support.validate_postgres_test_identity`)
    refuses any name that contains ``blueberry_peak`` without a
    ``_test_`` substring. This test pins the helper to that contract.
    """
    name = resolve_isolated_db_name(1, 1, "postgres_migration")
    assert "_test_" in name
    assert name.startswith(ISOLATED_DB_NAME_PREFIX)


def test_resolve_isolated_db_name_rejects_non_numeric_run_id() -> None:
    """A non-numeric run id must raise ValueError, not silently coerce."""
    with pytest.raises(ValueError, match="github_run_id must be a positive integer"):
        resolve_isolated_db_name("not-a-number", 1, "postgres_migration")


def test_resolve_isolated_db_name_rejects_zero_attempt() -> None:
    """An attempt < 1 must raise; the lowest legal attempt is 1."""
    with pytest.raises(ValueError, match="github_run_attempt must be >= 1"):
        resolve_isolated_db_name(1, 0, "postgres_migration")


def test_resolve_isolated_db_name_rejects_empty_job_name() -> None:
    """An empty / whitespace job name must raise ValueError."""
    with pytest.raises(ValueError, match="job_name must be a non-empty string"):
        resolve_isolated_db_name(1, 1, "")


def test_resolve_isolated_db_name_rejects_shell_metacharacters_in_job_name() -> None:
    """Job names with shell-unsafe characters must raise early."""
    for bad in ("postgres migration", "postgres;rm", "postgres$1", "../escape"):
        with pytest.raises(ValueError, match="job_name must match"):
            resolve_isolated_db_name(1, 1, bad)


def test_resolve_isolated_db_name_respects_postgres_identifier_limit() -> None:
    """The composed name must fit in PostgreSQL's 63-byte identifier limit."""
    long_job = "a" * 100
    with pytest.raises(ValueError, match="PostgreSQL identifier limit"):
        resolve_isolated_db_name(1, 1, long_job)

    # A 38-char job keeps the full name at 20 + 1 + 1 + 1 + 38 = 61
    # characters, under the 63-byte cap.
    safe = resolve_isolated_db_name(1, 1, "a" * 38)
    assert len(safe) <= MAX_ISOLATED_DB_NAME_LEN
    assert safe.endswith("a" * 38)


# ---------------------------------------------------------------------------
# assert_safe_isolated_db_name
# ---------------------------------------------------------------------------


def test_assert_safe_accepts_canonical_isolated_db_name() -> None:
    """A canonical resolved name must be accepted without error."""
    name = resolve_isolated_db_name(28869639380, 1, "postgres_migration")
    # No exception == pass.
    assert_safe_isolated_db_name(name)


@pytest.mark.parametrize(
    "forbidden",
    sorted(FORBIDDEN_DATABASE_NAMES),
)
def test_assert_safe_rejects_forbidden_database_names(forbidden: str) -> None:
    """Every name in FORBIDDEN_DATABASE_NAMES must be rejected.

    The slice-1 FORBIDDEN_DATABASE_NAMES list is the strongest
    fail-closed gate, so we exercise the plain forbidden name
    (without the slice-3 prefix tacked on — adding the prefix would
    yield a different, allowed name like ``blueberry_peak_test_foo``,
    which the prefix + validator pass).
    """
    with pytest.raises(ValueError, match="refusing isolated DB name"):
        assert_safe_isolated_db_name(forbidden)


def test_assert_safe_rejects_dev_db_without_test_marker() -> None:
    """``blueberry_peak`` (no ``_test_``) must be rejected by the prefix rule."""
    with pytest.raises(ValueError, match="refusing isolated DB name"):
        assert_safe_isolated_db_name("blueberry_peak")


def test_assert_safe_rejects_cluster_default_name() -> None:
    """PostgreSQL's cluster-default ``postgres`` database must be rejected."""
    with pytest.raises(ValueError, match="FORBIDDEN_DATABASE_NAMES"):
        assert_safe_isolated_db_name("postgres")


def test_assert_safe_rejects_empty_string() -> None:
    """An empty name carries no signal and must be rejected."""
    with pytest.raises(ValueError, match="non-empty string"):
        assert_safe_isolated_db_name("")


def test_assert_safe_error_message_omits_password_and_url() -> None:
    """The error message must NOT contain a password, token, or DATABASE_URL.

    The slice-1 safeguard already enforces this; we pin the property
    here as a regression test in case a future refactor leaks
    credentials into the message.
    """
    secret_password = "p@ssw0rd-leak-canary-XYZ"
    secret_url_token = "ghp_thisisnotarealtoken"
    try:
        assert_safe_isolated_db_name(secret_password)
    except ValueError as exc:
        message = str(exc)
        assert secret_password not in message, (
            "assert_safe_isolated_db_name leaked the input into the error"
        )
        assert secret_url_token not in message

    # Also assert the helper never echoes a full DATABASE_URL fragment.
    try:
        assert_safe_isolated_db_name("postgres://user:secret@host/db")
    except ValueError as exc:
        message = str(exc)
        assert "secret" not in message
        assert "user:secret" not in message
