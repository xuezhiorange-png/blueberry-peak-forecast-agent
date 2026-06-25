from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.harvest_state.canonical import canonical_json_dumps, make_result_hash
from backend.app.harvest_state.persistence import (
    HarvestStateHashConflictError,
    HarvestStatePersistenceIntegrityError,
    HarvestStateResultHashMismatchError,
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


def _with_valid_result_hash(output: Task9ACompletedOutput) -> Task9ACompletedOutput:
    payload = output.model_dump(mode="python")
    payload.pop("result_hash", None)
    return output.model_copy(update={"result_hash": make_result_hash(payload)})


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
    run = await save_harvest_state_output(sqlite_session, output=output)
    await sqlite_session.execute(
        text(
            "UPDATE harvest_state_run "
            "SET canonical_output = :value, canonical_payload_hash = :payload_hash "
            "WHERE id = :run_id"
        ),
        {
            "value": canonical_json_dumps(
                output.model_copy(update={"warnings": ["persistence-conflict"]}).model_dump(
                    mode="json"
                )
            ),
            "payload_hash": "d" * 64,
            "run_id": run.id,
        },
    )
    await sqlite_session.commit()

    with pytest.raises(HarvestStateHashConflictError):
        await save_harvest_state_output(sqlite_session, output=output)


@pytest.mark.asyncio
async def test_child_insert_failure_rolls_back_entire_run(sqlite_session: AsyncSession) -> None:
    output = _completed_output()
    duplicate_row = output.daily_pool_state_rows[0]
    broken = _with_valid_result_hash(
        output.model_copy(
        update={
            "daily_pool_state_rows": [*output.daily_pool_state_rows, duplicate_row],
        },
        )
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
            canonical_output={
                "output_schema_version": "task9a-output-v1",
                "status": "blocked",
                "input_snapshot": {},
                "resolved_parameter_snapshot": None,
                "daily_pool_state_rows": [],
                "daily_member_state_rows": [],
                "cohort_transition_rows": [],
                "future_arrival_schedule": [],
                "source_ref_catalog": [],
                "warnings": [],
                "blockers": ["bad"],
                "config_hash": "a" * 64,
                "result_hash": "b" * 64,
            },
            config_hash="a" * 64,
            result_hash="b" * 64,
            canonical_payload_hash="c" * 64,
            forecast_start_date=datetime(2026, 3, 1, tzinfo=UTC).date(),
            forecast_end_date=datetime(2026, 3, 1, tzinfo=UTC).date(),
            as_of_date=datetime(2026, 2, 28, tzinfo=UTC).date(),
            destination_factory_id=1,
            pool_row_count=0,
            member_row_count=0,
            cohort_row_count=0,
            future_arrival_row_count=0,
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
            canonical_output={
                "output_schema_version": "task9a-output-v1",
                "status": "blocked",
                "input_snapshot": {},
                "resolved_parameter_snapshot": None,
                "daily_pool_state_rows": [],
                "daily_member_state_rows": [],
                "cohort_transition_rows": [],
                "future_arrival_schedule": [],
                "source_ref_catalog": [],
                "warnings": [],
                "blockers": ["bad"],
                "config_hash": "a" * 64,
                "result_hash": "not-a-sha",
            },
            config_hash="a" * 64,
            result_hash="not-a-sha",
            canonical_payload_hash="c" * 64,
            forecast_start_date=datetime(2026, 3, 1, tzinfo=UTC).date(),
            forecast_end_date=datetime(2026, 3, 1, tzinfo=UTC).date(),
            as_of_date=datetime(2026, 2, 28, tzinfo=UTC).date(),
            destination_factory_id=1,
            pool_row_count=0,
            member_row_count=0,
            cohort_row_count=0,
            future_arrival_row_count=0,
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


@pytest.mark.asyncio
async def test_first_save_rejects_mismatched_result_hash(sqlite_session: AsyncSession) -> None:
    output = _completed_output().model_copy(update={"result_hash": "f" * 64})

    with pytest.raises(HarvestStateResultHashMismatchError):
        await save_harvest_state_output(sqlite_session, output=output)


@pytest.mark.asyncio
async def test_empty_initial_inventory_with_exact_zero_is_valid(
    sqlite_session: AsyncSession,
) -> None:
    payload = make_request()
    payload["initial_inventory_cohorts"] = []
    payload["initial_opening_mature_inventory_kg"] = "0"
    output = run_harvest_state_model(payload)
    assert output.status == "completed"

    run = await save_harvest_state_output(sqlite_session, output=output)
    assert run.status == "completed"


@pytest.mark.asyncio
async def test_duplicate_member_business_key_with_null_subfarm_rejected(
    sqlite_session: AsyncSession,
) -> None:
    output = _with_valid_result_hash(_completed_output())
    updated_members = [
        row.model_copy(update={"subfarm_id": None}) for row in output.daily_member_state_rows
    ]
    updated_future = [
        row.model_copy(update={"subfarm_id": None}) for row in output.future_arrival_schedule
    ]
    run = await save_harvest_state_output(
        sqlite_session,
        output=_with_valid_result_hash(
            output.model_copy(
            update={
                "daily_member_state_rows": updated_members,
                "future_arrival_schedule": updated_future,
            },
            )
        ),
    )
    row = updated_members[0]
    sqlite_session.add(
        HarvestStateDailyMemberRowModel(
            harvest_state_run_id=run.id,
            subfarm_identity_key="NONE",
            **row.model_dump(mode="python"),
        )
    )

    with pytest.raises(IntegrityError):
        await sqlite_session.commit()
    await sqlite_session.rollback()


@pytest.mark.asyncio
async def test_duplicate_future_arrival_key_with_null_subfarm_rejected(
    sqlite_session: AsyncSession,
) -> None:
    output = _with_valid_result_hash(_completed_output())
    if not output.future_arrival_schedule:
        pytest.skip("fixture does not produce future arrivals")
    updated_members = [
        row.model_copy(update={"subfarm_id": None}) for row in output.daily_member_state_rows
    ]
    updated_future = [
        row.model_copy(update={"subfarm_id": None}) for row in output.future_arrival_schedule
    ]
    run = await save_harvest_state_output(
        sqlite_session,
        output=_with_valid_result_hash(
            output.model_copy(
            update={
                "daily_member_state_rows": updated_members,
                "future_arrival_schedule": updated_future,
            },
            )
        ),
    )
    row = updated_future[0]
    sqlite_session.add(
        HarvestStateFutureArrivalRowModel(
            harvest_state_run_id=run.id,
            subfarm_identity_key="NONE",
            harvest_to_arrival_lag_days=1,
            farm_timezone="Asia/Shanghai",
            destination_factory_timezone="Asia/Tokyo",
            **row.model_dump(mode="python"),
        )
    )

    with pytest.raises(IntegrityError):
        await sqlite_session.commit()
    await sqlite_session.rollback()


@pytest.mark.asyncio
async def test_load_rejects_missing_completed_pool_row(sqlite_session: AsyncSession) -> None:
    output = _completed_output()
    run = await save_harvest_state_output(sqlite_session, output=output)
    await sqlite_session.execute(
        text(
            """
            DELETE FROM harvest_state_daily_pool_row
            WHERE id = (
                SELECT id
                FROM harvest_state_daily_pool_row
                WHERE harvest_state_run_id = :run_id
                ORDER BY id
                LIMIT 1
            )
            """
        ),
        {"run_id": run.id},
    )
    await sqlite_session.commit()

    with pytest.raises(HarvestStatePersistenceIntegrityError):
        await load_harvest_state_output_by_id(sqlite_session, run_id=run.id)


@pytest.mark.asyncio
async def test_load_rejects_blocked_run_with_state_rows(sqlite_session: AsyncSession) -> None:
    blocked = _blocked_output()
    completed = _completed_output()
    run = await save_harvest_state_output(sqlite_session, output=blocked)
    sqlite_session.add(
        HarvestStateDailyPoolRowModel(
            harvest_state_run_id=run.id,
            **completed.daily_pool_state_rows[0].model_dump(mode="python"),
        )
    )
    await sqlite_session.commit()

    with pytest.raises(HarvestStatePersistenceIntegrityError):
        await load_harvest_state_output_by_id(sqlite_session, run_id=run.id)


@pytest.mark.asyncio
async def test_load_rejects_canonical_payload_hash_mismatch(
    sqlite_session: AsyncSession,
) -> None:
    output = _completed_output()
    run = await save_harvest_state_output(sqlite_session, output=output)
    await sqlite_session.execute(
        text(
            "UPDATE harvest_state_run "
            "SET canonical_payload_hash = :value "
            "WHERE id = :run_id"
        ),
        {"value": "e" * 64, "run_id": run.id},
    )
    await sqlite_session.commit()
    await sqlite_session.close()

    engine = sqlite_session.bind
    assert engine is not None
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sessionmaker() as fresh_session:
        with pytest.raises(HarvestStatePersistenceIntegrityError):
            await load_harvest_state_output_by_id(fresh_session, run_id=run.id)


@pytest.mark.asyncio
async def test_canonical_payload_hash_is_stable(sqlite_session: AsyncSession) -> None:
    output = _completed_output()

    first = await save_harvest_state_output(sqlite_session, output=output)
    loaded = await load_harvest_state_output_by_id(sqlite_session, run_id=first.id)
    assert loaded is not None
    second = await save_harvest_state_output(sqlite_session, output=loaded)

    assert first.id == second.id
