"""PostgreSQL evidence for the frozen TASK-009 v2 season selector contract.

``HarvestStateRun.forecast_season_id`` plus the validated Task 9 v2
canonical ``forecast_season_identity`` are the only season selector
authority. A v1 row or NULL FK is ineligible even when legacy
``input_snapshot["forecast_season"]`` JSON is forged to match the
request. A missing formal request season ID also fails closed.

The production selector never uses ``strftime``, ``as_of_date.year``,
legacy JSON season values, latest-row selection, or ID ordering. Default
and explicit-override paths share the same v2 validator.

These tests run against real PostgreSQL, exercise the production
``_select_harvest_state_run_candidates`` path, and are owned by the
``postgres-domain-1`` PR CI shard.

The test is skipped unless ``RUN_POSTGRES_INTEGRATION=1`` is set AND
``BLUEBERRY_PG_DSN`` points to a valid test DSN.  When
``BLUEBERRY_PG_DSN`` is absent, the shared resolver derives the DSN
from ``POSTGRES_*`` and defaults to the standard ``blueberry_peak``
test database (the legacy ``blueberry_peak_test_r7_round8`` default
is forbidden).
"""
# ruff: noqa: E501, I001, F401, F841, F811, F821, ASYNC240

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import Table, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.agent.adapters.baseline_composer import (
    SEASON_BINDING_UNAVAILABLE,
    _select_harvest_state_run_candidates,
)
from backend.app.agent.enums import BlockerCode
from backend.app.harvest_state.enums import (
    OUTPUT_SCHEMA_VERSION_V1,
    RESULT_HASH_SCHEMA_VERSION_V1,
)
from backend.app.models.harvest_state import (
    HarvestStateDailyMemberRowModel,
    HarvestStateRun,
)
from backend.app.models.master_data import Variety
from backend.tests.integration.agent._pg_dsn import (
    PostgresTestDSNError,
    describe_postgres_target,
    resolve_postgres_test_dsn,
    verify_postgres_database_exists,
)


POSTGRES_TEST_DSN = resolve_postgres_test_dsn()

PG_INTEGRATION_ENABLED = os.getenv("RUN_POSTGRES_INTEGRATION") == "1"


def _require_postgres() -> None:
    if not PG_INTEGRATION_ENABLED:
        pytest.skip(
            "set RUN_POSTGRES_INTEGRATION=1 to run the real PostgreSQL "
            "selector test; default is skip (SQLite unit test covers the "
            "Python post-filter path)"
        )


def _pg_dialect_compiles() -> bool:
    """Sanity-check: confirm the active SQLAlchemy dialect is PG."""
    return POSTGRES_TEST_DSN.startswith(("postgresql", "postgres"))


@pytest_asyncio.fixture
async def pg_selector_session() -> AsyncIterator[AsyncSession]:
    """A real PostgreSQL session bound to the test DSN.

    Creates a per-test ``harvest_state_run`` table subset and
    truncates after the test.  The schema subset uses the
    ``create_all`` ORM model for ``HarvestStateRun``,
    ``HarvestStateDailyMemberRowModel``, and ``Variety`` — sufficient
    to exercise ``_select_harvest_state_run_candidates``
    end-to-end.

    The session is bound to an engine scoped to this test; no global
    state is mutated.
    """
    if not PG_INTEGRATION_ENABLED:
        pytest.skip("PG integration disabled")
    if not _pg_dialect_compiles():
        pytest.skip("resolved DSN is not a PostgreSQL URL")
    if not _pg_reachable(POSTGRES_TEST_DSN):
        target = describe_postgres_target(POSTGRES_TEST_DSN)
        pytest.skip(
            f"PostgreSQL is not reachable ({target}); "
            "check POSTGRES_HOST/POSTGRES_PORT or "
            "set BLUEBERRY_PG_DSN"
        )
    # Real database preflight: confirm the database named in the
    # DSN actually exists AND credentials are accepted.  A TCP-only
    # probe can pass even when the database name is wrong
    # (e.g. legacy ``blueberry_peak_test_r7_round8`` not in the
    # canary container).  Fail-closed with a host/port/db hint.
    try:
        await verify_postgres_database_exists(POSTGRES_TEST_DSN)
    except ConnectionError as exc:
        target = describe_postgres_target(POSTGRES_TEST_DSN)
        pytest.skip(f"PostgreSQL is not reachable ({target}): {type(exc).__name__}")
    except PostgresTestDSNError as exc:
        pytest.fail(str(exc))

    engine = create_async_engine(POSTGRES_TEST_DSN, future=True)
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sm() as session:
        from backend.app.models.master_data import Variety as _Variety

        async with engine.begin() as conn:
            await conn.run_sync(
                lambda sync_conn: HarvestStateRun.metadata.create_all(
                    sync_conn,
                    tables=[
                        Table(_Variety.__tablename__, _Variety.metadata),
                        Table(
                            HarvestStateRun.__tablename__,
                            HarvestStateRun.metadata,
                        ),
                        Table(
                            HarvestStateDailyMemberRowModel.__tablename__,
                            HarvestStateDailyMemberRowModel.metadata,
                        ),
                    ],
                    checkfirst=True,
                )
            )

        yield session
        # Cleanup: delete all rows we inserted (in FK-safe order).
        try:
            await session.execute(text("DELETE FROM harvest_state_daily_member_row"))
        except Exception:
            pass
        try:
            await session.execute(text("DELETE FROM harvest_state_run"))
        except Exception:
            pass
        try:
            await session.execute(text("DELETE FROM variety"))
        except Exception:
            pass
        await session.commit()
    await engine.dispose()


def _pg_reachable(dsn: str) -> bool:
    """Quick TCP-level reachability check (no DSN parsing)."""
    try:
        import socket
        from urllib.parse import urlparse

        u = urlparse(dsn)
        host = u.hostname or "localhost"
        port = u.port or 5432
        with socket.create_connection((host, port), timeout=2) as _:
            return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Legacy v1 canary: a forged JSON season token must never compensate
# for the missing v2 FK/canonical season identity.
# ---------------------------------------------------------------------------

_FORGED_LEGACY_INPUT_SNAPSHOT: dict = {
    "as_of_date": "2026-01-10",
    "forecast_start_date": "2026-01-01",
    "forecast_end_date": "2026-01-31",
    "forecast_quantiles": ["P50", "P80", "P90"],
    "destination_factory_id": 1,
    "forecast_season": 2026,
}


@pytest.mark.postgres
async def test_postgres_real_persistence_no_season_binding_emits_scope_mismatch(
    pg_selector_session: AsyncSession,
) -> None:
    """A forged matching v1 JSON token cannot restore selector eligibility."""
    hsr_id = await _insert_hsr_real_shape(
        pg_selector_session,
        result_hash="a" * 64,
        config_hash="b" * 64,
        as_of_date=date(2026, 1, 10),
    )
    selection = await _select_harvest_state_run_candidates(
        pg_selector_session,
        as_of=date(2026, 1, 15),
        run_id_override=None,
        destination_factory_id=1,
        requested_variety_codes=(),
        effective_forecast_season_id=2026,
    )
    assert selection.candidates == (), (
        f"row {hsr_id} must be excluded (no persisted season identity); got {selection.candidates}"
    )
    assert selection.blockers, "selector must surface typed blockers, not silent empty"
    scope_blks = [b for b in selection.blockers if b.code == BlockerCode.AUTHORITY_SCOPE_MISMATCH]
    assert scope_blks, (
        f"expected AUTHORITY_SCOPE_MISMATCH (real row, no persisted season); "
        f"got {[b.code.value for b in selection.blockers]}"
    )
    details = scope_blks[0].details or {}
    assert details.get("reason") == SEASON_BINDING_UNAVAILABLE
    assert details.get("row_id") == hsr_id
    assert details.get("requested_effective_forecast_season_id") == 2026
    assert details.get("persisted_forecast_season_id") is None
    assert details.get("persisted_season_identity") is None


@pytest.mark.postgres
async def test_postgres_missing_effective_season_id_fails_closed(
    pg_selector_session: AsyncSession,
) -> None:
    """A direct selector call without formal season identity fails closed."""
    hsr_id = await _insert_hsr_real_shape(
        pg_selector_session,
        result_hash="a" * 64,
        config_hash="b" * 64,
        as_of_date=date(2026, 1, 10),
    )
    selection = await _select_harvest_state_run_candidates(
        pg_selector_session,
        as_of=date(2026, 1, 15),
        run_id_override=None,
        destination_factory_id=1,
        requested_variety_codes=(),
        effective_forecast_season_id=None,
    )
    assert selection.candidates == ()
    assert selection.blockers
    blocker = selection.blockers[0]
    assert blocker.code == BlockerCode.AUTHORITY_SCOPE_MISMATCH
    assert (blocker.details or {}).get("reason") == SEASON_BINDING_UNAVAILABLE
    assert (blocker.details or {}).get("row_id") == hsr_id
    assert (blocker.details or {}).get("requested_effective_forecast_season_id") is None
    assert (blocker.details or {}).get("persisted_forecast_season_id") is None


@pytest.mark.postgres
async def test_postgres_default_path_no_strftime_no_year_extraction(
    pg_selector_session: AsyncSession,
) -> None:
    """PostgreSQL returns a typed v2 binding blocker, not year-extraction SQL."""
    hsr_id = await _insert_hsr_real_shape(
        pg_selector_session,
        result_hash="a" * 64,
        config_hash="b" * 64,
        as_of_date=date(2026, 1, 10),
    )
    # If the SQL used strftime, PostgreSQL would raise
    # "function strftime(...) does not exist" — by NOT raising,
    # this test confirms the production code does not use it.
    selection = await _select_harvest_state_run_candidates(
        pg_selector_session,
        as_of=date(2026, 1, 15),
        run_id_override=None,
        destination_factory_id=1,
        requested_variety_codes=(),
        effective_forecast_season_id=2026,
    )
    assert selection.candidates == ()
    assert selection.blockers
    # The blocker MUST be AUTHORITY_SCOPE_MISMATCH (real-persistence
    # no persisted season), NOT TASK9_AUTHORITY_NOT_FOUND (silent
    # base-scope collapse).
    blocker = selection.blockers[0]
    assert blocker.code == BlockerCode.AUTHORITY_SCOPE_MISMATCH
    details = blocker.details or {}
    assert details.get("reason") == SEASON_BINDING_UNAVAILABLE
    assert details.get("row_id") == hsr_id
    assert details.get("requested_effective_forecast_season_id") == 2026
    assert details.get("persisted_forecast_season_id") is None


async def _insert_hsr_real_shape(
    session: AsyncSession,
    *,
    result_hash: str,
    config_hash: str,
    as_of_date: date,
) -> int:
    """Insert a v1 row with forged legacy JSON and no v2 season FK."""
    row = HarvestStateRun(
        status="completed",
        output_schema_version=OUTPUT_SCHEMA_VERSION_V1,
        result_hash_schema_version=RESULT_HASH_SCHEMA_VERSION_V1,
        resolved_parameter_snapshot_schema_version="v1",
        source_ref_schema_version="v1",
        stable_cohort_key_schema_version="v1",
        input_snapshot=dict(_FORGED_LEGACY_INPUT_SNAPSHOT),
        resolved_parameter_snapshot={},
        source_ref_catalog=[],
        warnings=[],
        blockers=[],
        mass_balance_result=None,
        continuity_result=None,
        canonical_output={"ok": True},
        config_hash=config_hash,
        result_hash=result_hash,
        canonical_payload_hash="c" * 64,
        forecast_start_date=as_of_date,
        forecast_end_date=as_of_date.replace(month=12, day=31),
        as_of_date=as_of_date,
        destination_factory_id=1,
        pool_row_count=0,
        member_row_count=0,
        cohort_row_count=0,
        future_arrival_row_count=0,
        maturity_forecast_run_id=None,
        forecast_season_id=None,
    )
    session.add(row)
    await session.flush()
    return int(row.id)


__all__ = [
    "test_postgres_real_persistence_no_season_binding_emits_scope_mismatch",
    "test_postgres_missing_effective_season_id_fails_closed",
    "test_postgres_default_path_no_strftime_no_year_extraction",
]
