from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.harvest_state.canonical import canonical_json_dumps
from backend.app.harvest_state.persistence import (
    HarvestStateHashConflictError,
    load_harvest_state_output_by_id,
    load_harvest_state_output_by_result_hash,
    save_harvest_state_output,
)
from backend.app.harvest_state.schemas import Task9ACompletedOutput
from backend.app.harvest_state.service import run_harvest_state_model
from backend.app.models.harvest_state import (
    HarvestStateCohortTransitionRowModel,
    HarvestStateDailyMemberRowModel,
    HarvestStateDailyPoolRowModel,
    HarvestStateFutureArrivalRowModel,
    HarvestStateRun,
)
from backend.tests.harvest_state.conftest import make_request

HARVEST_STATE_TABLES = [
    HarvestStateRun.__table__,
    HarvestStateDailyPoolRowModel.__table__,
    HarvestStateDailyMemberRowModel.__table__,
    HarvestStateCohortTransitionRowModel.__table__,
    HarvestStateFutureArrivalRowModel.__table__,
]


def _canonical_output_json(output: object) -> str:
    if hasattr(output, "model_dump"):
        return canonical_json_dumps(output.model_dump(mode="python"))  # type: ignore[no-any-return]
    return canonical_json_dumps(output)


async def _table_counts(session: AsyncSession) -> dict[str, int]:
    return {
        "runs": int(await session.scalar(select(func.count()).select_from(HarvestStateRun)) or 0),
        "pool_rows": int(
            await session.scalar(select(func.count()).select_from(HarvestStateDailyPoolRowModel))
            or 0
        ),
        "member_rows": int(
            await session.scalar(select(func.count()).select_from(HarvestStateDailyMemberRowModel))
            or 0
        ),
        "cohort_rows": int(
            await session.scalar(
                select(func.count()).select_from(HarvestStateCohortTransitionRowModel)
            )
            or 0
        ),
        "future_arrivals": int(
            await session.scalar(
                select(func.count()).select_from(HarvestStateFutureArrivalRowModel)
            )
            or 0
        ),
    }


@pytest.fixture
async def sqlite_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: HarvestStateRun.metadata.create_all(
                sync_conn,
                tables=HARVEST_STATE_TABLES,
            )
        )
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sessionmaker() as session:
        yield session
    await engine.dispose()


def _completed_output() -> Task9ACompletedOutput:
    result = run_harvest_state_model(make_request())
    assert result.status == "completed"
    return result


def _blocked_output() -> object:
    payload = make_request()
    payload["farm_timezone"] = "Bad/Timezone"
    result = run_harvest_state_model(payload)
    assert result.status == "blocked"
    return result


@pytest.mark.asyncio
async def test_persist_completed_output(sqlite_session: AsyncSession) -> None:
    output = _completed_output()

    run = await save_harvest_state_output(sqlite_session, output=output)

    assert run.status == "completed"
    counts = await _table_counts(sqlite_session)
    assert counts == {
        "runs": 1,
        "pool_rows": len(output.daily_pool_state_rows),
        "member_rows": len(output.daily_member_state_rows),
        "cohort_rows": len(output.cohort_transition_rows),
        "future_arrivals": len(output.future_arrival_schedule),
    }


@pytest.mark.asyncio
async def test_load_completed_output(sqlite_session: AsyncSession) -> None:
    output = _completed_output()
    run = await save_harvest_state_output(sqlite_session, output=output)

    loaded = await load_harvest_state_output_by_id(sqlite_session, run_id=run.id)

    assert loaded is not None
    assert loaded.status == "completed"
    assert _canonical_output_json(loaded) == _canonical_output_json(output)


@pytest.mark.asyncio
async def test_completed_round_trip_is_canonically_equal(sqlite_session: AsyncSession) -> None:
    output = _completed_output()
    await save_harvest_state_output(sqlite_session, output=output)

    loaded = await load_harvest_state_output_by_result_hash(
        sqlite_session,
        result_hash=output.result_hash,
    )

    assert loaded is not None
    assert _canonical_output_json(loaded) == _canonical_output_json(output)


@pytest.mark.asyncio
async def test_persist_blocked_output(sqlite_session: AsyncSession) -> None:
    output = _blocked_output()

    run = await save_harvest_state_output(sqlite_session, output=output)

    assert run.status == "blocked"
    counts = await _table_counts(sqlite_session)
    assert counts == {
        "runs": 1,
        "pool_rows": 0,
        "member_rows": 0,
        "cohort_rows": 0,
        "future_arrivals": 0,
    }


@pytest.mark.asyncio
async def test_blocked_round_trip_is_canonically_equal(sqlite_session: AsyncSession) -> None:
    output = _blocked_output()
    run = await save_harvest_state_output(sqlite_session, output=output)

    loaded = await load_harvest_state_output_by_id(sqlite_session, run_id=run.id)

    assert loaded is not None
    assert loaded.status == "blocked"
    assert _canonical_output_json(loaded) == _canonical_output_json(output)


@pytest.mark.asyncio
async def test_duplicate_result_hash_is_idempotent(sqlite_session: AsyncSession) -> None:
    output = _completed_output()

    first = await save_harvest_state_output(sqlite_session, output=output)
    second = await save_harvest_state_output(sqlite_session, output=output)

    assert first.id == second.id
    counts = await _table_counts(sqlite_session)
    assert counts["runs"] == 1
    assert counts["pool_rows"] == len(output.daily_pool_state_rows)


@pytest.mark.asyncio
async def test_duplicate_result_hash_does_not_duplicate_children(
    sqlite_session: AsyncSession,
) -> None:
    output = _completed_output()
    await save_harvest_state_output(sqlite_session, output=output)
    before = await _table_counts(sqlite_session)

    await save_harvest_state_output(sqlite_session, output=output)
    after = await _table_counts(sqlite_session)

    assert after == before


@pytest.mark.asyncio
async def test_same_result_hash_different_payload_raises_conflict(
    sqlite_session: AsyncSession,
) -> None:
    output = _completed_output()
    await save_harvest_state_output(sqlite_session, output=output)
    conflicting = output.model_copy(
        update={
            "warnings": ["persistence-conflict"],
            "result_hash": output.result_hash,
        }
    )

    with pytest.raises(HarvestStateHashConflictError):
        await save_harvest_state_output(sqlite_session, output=conflicting)


@pytest.mark.asyncio
async def test_child_insert_failure_rolls_back_entire_run(sqlite_session: AsyncSession) -> None:
    output = _completed_output()
    duplicate_row = output.daily_pool_state_rows[0]
    broken = output.model_copy(
        update={
            "daily_pool_state_rows": [*output.daily_pool_state_rows, duplicate_row],
        }
    )

    with pytest.raises(IntegrityError):
        await save_harvest_state_output(sqlite_session, output=broken)

    counts = await _table_counts(sqlite_session)
    assert counts == {
        "runs": 0,
        "pool_rows": 0,
        "member_rows": 0,
        "cohort_rows": 0,
        "future_arrivals": 0,
    }


@pytest.mark.asyncio
async def test_blocked_run_has_no_state_rows(sqlite_session: AsyncSession) -> None:
    output = _blocked_output()
    await save_harvest_state_output(sqlite_session, output=output)

    counts = await _table_counts(sqlite_session)
    assert counts["pool_rows"] == 0
    assert counts["member_rows"] == 0
    assert counts["cohort_rows"] == 0
    assert counts["future_arrivals"] == 0


@pytest.mark.asyncio
async def test_jsonb_verification_snapshot_is_preserved(sqlite_session: AsyncSession) -> None:
    output = _completed_output()
    run = await save_harvest_state_output(sqlite_session, output=output)

    loaded = await load_harvest_state_output_by_id(sqlite_session, run_id=run.id)
    assert loaded is not None
    first_input = loaded.input_snapshot["task8_daily_predictions"][0]
    original_input = output.input_snapshot["task8_daily_predictions"][0]
    assert first_input["verification_snapshot"] == original_input["verification_snapshot"]
    assert (
        first_input["verification_snapshot_hash"]
        == original_input["verification_snapshot_hash"]
    )


@pytest.mark.asyncio
async def test_timezone_aware_arrival_round_trip(sqlite_session: AsyncSession) -> None:
    output = _completed_output()
    run = await save_harvest_state_output(sqlite_session, output=output)

    loaded = await load_harvest_state_output_by_id(sqlite_session, run_id=run.id)
    assert loaded is not None
    completed = cast(Task9ACompletedOutput, loaded)
    harvested_rows = [
        row for row in completed.cohort_transition_rows if row.arrival_at is not None
    ]
    assert harvested_rows
    assert all(
        row.arrival_at is not None and row.arrival_at.tzinfo is not None
        for row in harvested_rows
    )


@pytest.mark.asyncio
async def test_invalid_status_rejected(sqlite_session: AsyncSession) -> None:
    sqlite_session.add(
        HarvestStateRun(
            status="bad",
            output_schema_version="task9a-output-v1",
            result_hash_schema_version="task9a-result-hash-v1",
            resolved_parameter_snapshot_schema_version="task9a-resolved-parameters-v1",
            source_ref_schema_version="task9a-source-ref-v1",
            stable_cohort_key_schema_version="task9a-cohort-key-v1",
            input_snapshot={},
            resolved_parameter_snapshot=None,
            source_ref_catalog=[],
            warnings=[],
            blockers=["bad"],
            mass_balance_result=None,
            continuity_result=None,
            config_hash="a" * 64,
            result_hash="b" * 64,
            forecast_start_date=datetime(2026, 3, 1, tzinfo=UTC).date(),
            forecast_end_date=datetime(2026, 3, 1, tzinfo=UTC).date(),
            as_of_date=datetime(2026, 2, 28, tzinfo=UTC).date(),
            destination_factory_id=1,
        )
    )
    with pytest.raises(IntegrityError):
        await sqlite_session.commit()
    await sqlite_session.rollback()


@pytest.mark.asyncio
async def test_invalid_result_hash_rejected(sqlite_session: AsyncSession) -> None:
    sqlite_session.add(
        HarvestStateRun(
            status="blocked",
            output_schema_version="task9a-output-v1",
            result_hash_schema_version="task9a-result-hash-v1",
            resolved_parameter_snapshot_schema_version="task9a-resolved-parameters-v1",
            source_ref_schema_version="task9a-source-ref-v1",
            stable_cohort_key_schema_version="task9a-cohort-key-v1",
            input_snapshot={},
            resolved_parameter_snapshot=None,
            source_ref_catalog=[],
            warnings=[],
            blockers=["bad"],
            mass_balance_result=None,
            continuity_result=None,
            config_hash="a" * 64,
            result_hash="not-a-sha",
            forecast_start_date=datetime(2026, 3, 1, tzinfo=UTC).date(),
            forecast_end_date=datetime(2026, 3, 1, tzinfo=UTC).date(),
            as_of_date=datetime(2026, 2, 28, tzinfo=UTC).date(),
            destination_factory_id=1,
        )
    )
    with pytest.raises(IntegrityError):
        await sqlite_session.commit()
    await sqlite_session.rollback()


@pytest.mark.asyncio
async def test_duplicate_pool_business_key_rejected(sqlite_session: AsyncSession) -> None:
    output = _completed_output()
    run = await save_harvest_state_output(sqlite_session, output=output)
    row = output.daily_pool_state_rows[0]
    sqlite_session.add(
        HarvestStateDailyPoolRowModel(
            harvest_state_run_id=run.id,
            **row.model_dump(mode="python"),
        )
    )
    with pytest.raises(IntegrityError):
        await sqlite_session.commit()
    await sqlite_session.rollback()
