"""Slice 4 — pure helper-contract tests for the ``postgres-concurrency`` isolated DB profile.

This file mirrors :mod:`backend.tests.test_alembic_round_trip_isolated`
(the Slice 3 contract test) but pins the
:mod:`backend.tests.concurrency_isolation_helpers` wrapper specifically
for the ``postgres-concurrency`` job. It is a **pure helper-contract
test**: no PostgreSQL connection is opened. It is safe to run on hosts
without PostgreSQL.

Marker / CI ownership:

* This file is marked ``pytest.mark.postgres`` (see ``pytestmark``
  below). The ``unit-contract-golden`` CI job selects tests with
  ``-m "not integration and not postgres and not postgres_concurrency"``,
  so this file is **explicitly excluded** from ``unit-contract-golden``,
  matching the Slice 3 pattern. Running it there would be a mistake,
  not a feature.
* This file is **owned** by the ``postgres-concurrency`` job, which
  lists it explicitly in its ``pytest`` invocation in
  ``.github/workflows/ci.yml`` (the ``-m`` selector does not apply to
  a hand-listed file). It is the only CI job that runs these tests.
* This file is intentionally **not** placed under
  ``backend/tests/integration/`` to avoid being collected by any
  future integration-shard wiring.

Property: this slice does not add a live-PG companion assertion that
lives under ``backend/tests/integration/``. The live evidence lives in
:mod:`backend.tests.test_concurrency_isolation_helpers_live` (a
``pytest.mark.postgres_concurrency`` module) which the
``postgres-concurrency`` CI job lists explicitly. This file's job is
to pin the helper contract so the CI step cannot silently drift.
"""

from __future__ import annotations

import pytest

from backend.tests.concurrency_isolation_helpers import (
    CONCURRENCY_ISOLATED_DB_NAME_PREFIX,
    CONCURRENCY_MAX_ISOLATED_DB_NAME_LEN,
    ISOLATED_JOB_NAME,
    assert_safe_concurrency_isolated_db_name,
    resolve_concurrency_isolated_db_name,
)
from backend.tests.migration_isolation_helpers import (
    ISOLATED_DB_NAME_PREFIX,
    MAX_ISOLATED_DB_NAME_LEN,
    resolve_isolated_db_name,
)
from backend.tests.postgres_test_support import FORBIDDEN_DATABASE_NAMES

# Mark this file ``postgres`` so the ``unit-contract-golden`` job's
# ``-m "not integration and not postgres and not postgres_concurrency"``
# selector **excludes** it. The ``postgres-concurrency`` job lists the
# file explicitly in its ``pytest`` invocation, so the marker is not a
# no-op for that job — it only governs whether the contract tests get
# collected by other shards.
pytestmark = pytest.mark.postgres


# --------------------------------------------------------------------------
# Wrapper vs. Slice 3 helper — wrappers must agree on the same family of
# names; otherwise a silent divergence would defeat the whole point of
# "reuse Slice 3 helpers".
# --------------------------------------------------------------------------


def test_wrapper_exports_share_slice3_constants() -> None:
    """The Slice 4 wrapper re-exports must equal the Slice 3 constants."""
    assert CONCURRENCY_ISOLATED_DB_NAME_PREFIX == ISOLATED_DB_NAME_PREFIX
    assert CONCURRENCY_MAX_ISOLATED_DB_NAME_LEN == MAX_ISOLATED_DB_NAME_LEN


def test_isolated_job_name_is_canonical_postgres_concurrency() -> None:
    """The canonical job name must be ``postgres_concurrency``."""
    assert ISOLATED_JOB_NAME == "postgres_concurrency"


def test_isolated_job_name_is_distinct_from_slice3_job_name() -> None:
    """Slice 3 uses ``postgres_migration``; Slice 4 must use a different one.

    Two jobs on the same run / attempt must not share an isolated DB,
    so the job segments must differ.
    """
    assert ISOLATED_JOB_NAME != "postgres_migration"


# --------------------------------------------------------------------------
# resolve_concurrency_isolated_db_name
# --------------------------------------------------------------------------


def test_resolve_uses_canonical_template() -> None:
    """The resolved name must be ``prefix + run_id + _ + attempt + _ + postgres_concurrency``."""
    name = resolve_concurrency_isolated_db_name(28877022654, 1)
    assert name == f"{ISOLATED_DB_NAME_PREFIX}28877022654_1_postgres_concurrency"


def test_resolve_accepts_numeric_strings() -> None:
    """GitHub exposes run_id / run_attempt as strings; helpers must accept both."""
    int_form = resolve_concurrency_isolated_db_name(42, 1)
    str_form = resolve_concurrency_isolated_db_name("42", "1")
    assert int_form == str_form


def test_resolve_distinguishes_attempts() -> None:
    """Two attempts of the same run must produce two distinct names."""
    first = resolve_concurrency_isolated_db_name(28877022654, 1)
    second = resolve_concurrency_isolated_db_name(28877022654, 2)
    assert first != second
    assert first.endswith("_1_postgres_concurrency")
    assert second.endswith("_2_postgres_concurrency")


def test_resolve_contains_test_marker() -> None:
    """Every resolved name must contain the ``_test_`` substring."""
    name = resolve_concurrency_isolated_db_name(1, 1)
    assert "_test_" in name
    assert name.startswith(ISOLATED_DB_NAME_PREFIX)


def test_resolve_matches_slice3_helper_for_same_inputs() -> None:
    """The wrapper and the Slice 3 helper must agree for matching inputs.

    This pins the "wrapper is a thin layer" contract.
    """
    run_id, attempt = 1234567890, 3
    wrapper_name = resolve_concurrency_isolated_db_name(run_id, attempt)
    slice3_name = resolve_isolated_db_name(run_id, attempt, ISOLATED_JOB_NAME)
    assert wrapper_name == slice3_name


def test_resolve_rejects_non_numeric_run_id() -> None:
    """A non-numeric run id must raise ValueError, not silently coerce."""
    with pytest.raises(ValueError, match="github_run_id must be a positive integer"):
        resolve_concurrency_isolated_db_name("not-a-number", 1)


def test_resolve_rejects_zero_attempt() -> None:
    """An attempt < 1 must raise; the lowest legal attempt is 1."""
    with pytest.raises(ValueError, match="github_run_attempt must be >= 1"):
        resolve_concurrency_isolated_db_name(1, 0)


def test_resolve_rejects_negative_attempt() -> None:
    """A negative attempt must raise ValueError.

    The Slice 3 helper rejects ``-1`` via the ``isdigit()`` branch
    (the leading ``-`` is not a digit) before reaching the explicit
    ``< 1`` branch, so the message uses the
    ``"github_run_attempt must be a positive integer"`` form. We
    only assert *some* ValueError is raised here; the dedicated
    ``>= 1`` message is pinned by ``test_resolve_rejects_zero_attempt``.
    """
    with pytest.raises(ValueError, match="github_run_attempt must be a positive integer"):
        resolve_concurrency_isolated_db_name(1, -1)


def test_resolve_respects_postgres_identifier_limit() -> None:
    """The composed name must never exceed the PostgreSQL identifier limit."""
    # A 20-digit run id × 3 digits attempt × "postgres_concurrency"
    # (20 chars) plus prefix (18 chars) plus two underscores (2 chars)
    # = 18 + 20 + 1 + 3 + 1 + 20 = 63, the limit.
    name = resolve_concurrency_isolated_db_name("99999999999999999999", 1)
    assert len(name) <= MAX_ISOLATED_DB_NAME_LEN


def test_resolve_rejects_overlong_composed_name() -> None:
    """An overlong composed name must raise ValueError."""
    # 22-digit run id triggers overlong composed name (18 + 22 + 1 + 1 + 1 + 20 = 63; bump to 23).
    with pytest.raises(ValueError, match="exceeds PostgreSQL identifier limit"):
        resolve_concurrency_isolated_db_name("99999999999999999999999", 1)


# --------------------------------------------------------------------------
# assert_safe_concurrency_isolated_db_name
# --------------------------------------------------------------------------


def test_assert_safe_accepts_resolved_name() -> None:
    """A name produced by the resolver must pass the guard."""
    name = resolve_concurrency_isolated_db_name(28877022654, 1)
    assert_safe_concurrency_isolated_db_name(name)  # must not raise


def test_assert_safe_rejects_empty_string() -> None:
    """An empty string must raise."""
    with pytest.raises(ValueError, match="db_name must be a non-empty string"):
        assert_safe_concurrency_isolated_db_name("")


def test_assert_safe_rejects_non_string() -> None:
    """A non-string input must raise."""
    with pytest.raises(ValueError, match="db_name must be a non-empty string"):
        assert_safe_concurrency_isolated_db_name(None)  # type: ignore[arg-type]


@pytest.mark.parametrize("forbidden", sorted(FORBIDDEN_DATABASE_NAMES))
def test_assert_safe_rejects_forbidden_database_names(forbidden: str) -> None:
    """Every forbidden database name must be rejected."""
    with pytest.raises(ValueError, match="FORBIDDEN_DATABASE_NAMES"):
        assert_safe_concurrency_isolated_db_name(forbidden)


def test_assert_safe_rejects_blueberry_peak_literal() -> None:
    """The dev-DB literal ``blueberry_peak`` must be rejected explicitly."""
    with pytest.raises(ValueError):
        assert_safe_concurrency_isolated_db_name("blueberry_peak")


def test_assert_safe_rejects_blueberry_peak_dev_literal() -> None:
    """The dev variant ``blueberry_peak_dev`` must be rejected."""
    with pytest.raises(ValueError):
        assert_safe_concurrency_isolated_db_name("blueberry_peak_dev")


def test_assert_safe_rejects_postgres_cluster_default() -> None:
    """The cluster-default ``postgres`` database must be rejected."""
    with pytest.raises(ValueError, match="FORBIDDEN_DATABASE_NAMES"):
        assert_safe_concurrency_isolated_db_name("postgres")


def test_assert_safe_rejects_name_without_test_marker() -> None:
    """A name that does not start with the slice-3 prefix must be rejected."""
    with pytest.raises(ValueError, match="must start with the slice-3 isolated profile marker"):
        assert_safe_concurrency_isolated_db_name("not_a_test_prefix_run_1_postgres_concurrency")


def test_assert_safe_error_does_not_echo_caller_password() -> None:
    """Guard errors must NEVER echo caller-controlled input (which may include a password).

    The Slice 3 helper is documented to omit the offending name from
    the error message so that even if a caller accidentally passes a
    password / token / full ``DATABASE_URL`` as the ``db_name``, the
    secret never appears in the raised message. This test pins that
    contract for the Slice 4 wrapper.
    """
    secret_marker = "sup3r-secret-pw-marker-zzz"
    with pytest.raises(ValueError) as exc_info:
        assert_safe_concurrency_isolated_db_name(secret_marker)
    assert secret_marker not in str(exc_info.value)


def test_assert_safe_error_does_not_echo_database_url() -> None:
    """A ``DATABASE_URL``-shaped input must not be echoed back in the error."""
    secret_url = "postgresql+asyncpg://user:secret-token-zzz@host:5432/db"
    with pytest.raises(ValueError) as exc_info:
        assert_safe_concurrency_isolated_db_name(secret_url)
    msg = str(exc_info.value)
    assert "secret-token-zzz" not in msg
    assert "user:secret" not in msg
    assert secret_url not in msg
