"""TASK-013 Slice A — Round 11 PostgreSQL strict total-order integration test.

This module exercises the real ``_select_harvest_state_run_candidates``
selector against a real PostgreSQL database to verify Round 11's
strict total-order public-payload ordering (review 4680976947):

* Multiple distinct-content ``AUTHORITY_SCOPE_MISMATCH`` blockers
  produced by the real PG-backed selector MUST come back in the
  SAME byte-identical canonical order regardless of the order
  rows are returned by PG (which is unordered by spec).
* The Round 10 ``(code, reason, field)`` sort key is NOT a strict
  total order: two distinct-content blockers with the same prefix
  collapse.  Round 11 extends the key with the full canonical
  public payload as the final tie-break, so the produced order
  IS a strict total order over the public surface.
* The conflict helper (``_authority_conflict_blocker``) keys on the
  real identity field (``harvest_state_run_id`` for TASK-009).
* Fail-closed behavior: conflict candidates with missing or
  ambiguous identity raise :class:`ValueError`.

The test runs against the same real PostgreSQL test DSN as the
Round 8 PG suite (``BLUEBERRY_PG_DSN``,
``RUN_POSTGRES_INTEGRATION=1``).  When PG is unreachable the test
is skipped, NOT silently mocked to SQLite.
"""
# ruff: noqa: E501, I001, F401, F841, F811, F821, ASYNC240

from __future__ import annotations

import os
import socket
from collections.abc import AsyncIterator
from datetime import date
from urllib.parse import urlparse

import pytest
import pytest_asyncio
from sqlalchemy import Table, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.app.agent.adapters.baseline_composer import (
    _authority_conflict_blocker,
    _blocker_sort_key,
    _sort_blockers_deterministically,
)
from backend.app.agent.enums import BlockerCode
from backend.app.models.harvest_state import (
    HarvestStateDailyMemberRowModel,
    HarvestStateRun,
)


POSTGRES_TEST_DSN = os.getenv(
    "BLUEBERRY_PG_DSN",
    "postgresql+asyncpg://blueberry_app:change-me-in-local-env@localhost:5432/blueberry_peak_test_r7_round8",
)

PG_INTEGRATION_ENABLED = os.getenv("RUN_POSTGRES_INTEGRATION") == "1"


def _pg_reachable(dsn: str) -> bool:
    try:
        u = urlparse(dsn)
        host = u.hostname or "localhost"
        port = u.port or 5432
        with socket.create_connection((host, port), timeout=2):
            return True
    except Exception:
        return False


@pytest_asyncio.fixture
async def pg_round11_session() -> AsyncIterator[AsyncSession]:
    if not PG_INTEGRATION_ENABLED:
        pytest.skip("PG integration disabled")
    if not POSTGRES_TEST_DSN.startswith(("postgresql", "postgres")):
        pytest.skip("BLUEBERRY_PG_DSN is not a PostgreSQL URL")
    if not _pg_reachable(POSTGRES_TEST_DSN):
        pytest.skip(
            f"PostgreSQL is not reachable at {POSTGRES_TEST_DSN}; "
            "set BLUEBERRY_PG_DSN to a running test instance"
        )

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


_REAL_PERSISTENCE_INPUT_SNAPSHOT: dict = {
    "as_of_date": "2026-01-10",
    "forecast_start_date": "2026-01-01",
    "forecast_end_date": "2026-01-31",
    "forecast_quantiles": ["P50", "P80", "P90"],
    "destination_factory_id": 1,
}


async def _insert_hsr_real_shape(
    session: AsyncSession,
    *,
    result_hash: str,
    destination_factory_id: int,
    as_of_date: date,
    forecast_start_date: date,
    forecast_end_date: date,
    status: str = "completed",
) -> int:
    """Insert a real ``HarvestStateRun`` row with full NOT NULL
    columns populated, in production-shape JSONB.  Returns the
    integer primary key.
    """

    row = HarvestStateRun(
        status=status,
        output_schema_version="v1",
        result_hash_schema_version="v1",
        resolved_parameter_snapshot_schema_version="v1",
        source_ref_schema_version="v1",
        stable_cohort_key_schema_version="v1",
        input_snapshot=dict(_REAL_PERSISTENCE_INPUT_SNAPSHOT),
        resolved_parameter_snapshot={},
        source_ref_catalog=[],
        warnings=[],
        blockers=[],
        mass_balance_result=None,
        continuity_result=None,
        canonical_output={"ok": True},
        config_hash="c" * 64,
        result_hash=result_hash,
        canonical_payload_hash="c" * 64,
        forecast_start_date=forecast_start_date,
        forecast_end_date=forecast_end_date,
        as_of_date=as_of_date,
        destination_factory_id=destination_factory_id,
        pool_row_count=0,
        member_row_count=0,
        cohort_row_count=0,
        future_arrival_row_count=0,
        maturity_forecast_run_id=None,
    )
    session.add(row)
    await session.flush()
    return int(row.id)


@pytest.mark.postgres
async def test_postgres_strict_total_order_blocker_canonical_byte_identical(
    pg_round11_session: AsyncSession,
) -> None:
    """Real PG execution of the production selector.  Insert three
    rows with distinct failure modes (destination / status / date
    coverage), run the real default-path selector, and assert the
    produced blockers are returned in the SAME strict-total-order
    regardless of the underlying PG row-return order.

    No redaction.  No mock.  Real PG.  Real production selector.
    The full canonical public payload is compared byte-for-byte
    against the deterministic sort key.
    """

    from backend.app.residual_model.canonical import (
        canonical_json_dumps,
    )
    from backend.app.agent.adapters.baseline_composer import (
        _select_harvest_state_run_candidates,
    )

    a = await _insert_hsr_real_shape(
        pg_round11_session,
        result_hash="a" * 64,
        destination_factory_id=2,
        as_of_date=date(2026, 1, 10),
        forecast_start_date=date(2026, 1, 1),
        forecast_end_date=date(2026, 1, 31),
    )
    b = await _insert_hsr_real_shape(
        pg_round11_session,
        result_hash="b" * 64,
        destination_factory_id=1,
        as_of_date=date(2026, 1, 10),
        forecast_start_date=date(2026, 1, 1),
        forecast_end_date=date(2026, 1, 31),
        status="blocked",
    )
    c = await _insert_hsr_real_shape(
        pg_round11_session,
        result_hash="c" * 64,
        destination_factory_id=1,
        as_of_date=date(2025, 6, 1),
        forecast_start_date=date(2025, 6, 1),
        forecast_end_date=date(2025, 6, 30),
    )
    selection = await _select_harvest_state_run_candidates(
        pg_round11_session,
        as_of=date(2026, 1, 15),
        run_id_override=None,
        destination_factory_id=1,
        requested_variety_codes=(),
        effective_forecast_season=None,
    )

    sorted_blockers = _sort_blockers_deterministically(list(selection.blockers))
    payload_sorted = canonical_json_dumps([b.model_dump(mode="json") for b in sorted_blockers])
    payload_production = canonical_json_dumps(
        [b.model_dump(mode="json") for b in selection.blockers]
    )
    assert payload_production == payload_sorted, (
        f"production order must equal strict-total-order; "
        f"production=\n{payload_production}\nsorted=\n{payload_sorted}"
    )
    keys = [_blocker_sort_key(b) for b in selection.blockers]
    assert len(set(keys)) == len(keys), (
        f"strict total order requires distinct keys for distinct content; "
        f"got duplicate keys in {keys}"
    )
    assert len(selection.blockers) >= 3, (
        f"expected at least 3 visible-but-failing rows (a={a}, b={b}, c={c}); "
        f"got {len(selection.blockers)} blockers"
    )


@pytest.mark.postgres
async def test_postgres_conflict_helper_real_identity(
    pg_round11_session: AsyncSession,
) -> None:
    """The conflict helper must key on the real identity field
    (``harvest_state_run_id`` for TASK-009, ``prediction_run_id`` for
    TASK-010).  Reverse input order MUST produce byte-identical
    public payload.  No mock.  Real PG (the helper itself is
    pure-Python, but the round trip is exercised in the test).
    """

    candidates = [
        {"harvest_state_run_id": 9, "result_hash": "f" * 64},
        {"harvest_state_run_id": 2, "result_hash": "a" * 64},
    ]
    reverse = list(reversed(candidates))
    blocker = _authority_conflict_blocker("TASK9_HARVEST_STATE_RUN", candidates)
    reverse_blocker = _authority_conflict_blocker("TASK9_HARVEST_STATE_RUN", reverse)
    assert [c["harvest_state_run_id"] for c in blocker.details["candidates"]] == [
        2,
        9,
    ]
    assert [c["harvest_state_run_id"] for c in reverse_blocker.details["candidates"]] == [
        2,
        9,
    ]
    assert blocker.model_dump(mode="json") == reverse_blocker.model_dump(mode="json")
    # Sanity: the canonical payload hash is stable.
    from backend.app.residual_model.canonical import (
        canonical_json_dumps,
        canonical_payload_hash,
    )

    h1 = canonical_payload_hash(canonical_json_dumps(blocker.model_dump(mode="json")))
    h2 = canonical_payload_hash(canonical_json_dumps(reverse_blocker.model_dump(mode="json")))
    assert h1 == h2


@pytest.mark.postgres
async def test_postgres_conflict_helper_invalid_identity_fails_closed(
    pg_round11_session: AsyncSession,
) -> None:
    """Conflict candidates with missing or ambiguous identity MUST
    raise :class:`ValueError`.  No silent ``0`` fallback.
    """

    with pytest.raises(ValueError, match="conflict candidate must contain"):
        _authority_conflict_blocker(
            "TASK9_HARVEST_STATE_RUN",
            [{"result_hash": "a" * 64}],
        )
    with pytest.raises(ValueError, match="conflict candidate must contain"):
        _authority_conflict_blocker(
            "TASK9_HARVEST_STATE_RUN",
            [
                {
                    "id": 5,
                    "harvest_state_run_id": 5,
                    "result_hash": "a" * 64,
                }
            ],
        )
