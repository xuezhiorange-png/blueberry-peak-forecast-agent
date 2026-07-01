from __future__ import annotations

import asyncio
import os
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from backend.app.db.session import AsyncSessionMaker
from backend.app.harvest_state.canonical import canonical_json_dumps, make_result_hash
from backend.app.harvest_state.persistence import (
    HarvestStateHashConflictError,
    HarvestStatePersistenceIntegrityError,
    HarvestStateResultHashMismatchError,
    load_harvest_state_output_by_id,
    load_harvest_state_output_by_result_hash,
    save_harvest_state_output,
)
from backend.app.harvest_state.service import run_harvest_state_model
from backend.app.models.harvest_state import (
    HarvestStateCohortTransitionRowModel,
    HarvestStateDailyMemberRowModel,
    HarvestStateDailyPoolRowModel,
    HarvestStateFutureArrivalRowModel,
    HarvestStateRun,
)
from backend.tests.harvest_state.conftest import make_request

pytestmark = [pytest.mark.integration, pytest.mark.postgres_concurrency]


def _require_postgres() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("set RUN_POSTGRES_INTEGRATION=1 when PostgreSQL is available")


def _canonical_output_json(output: object) -> str:
    if hasattr(output, "model_dump"):
        return canonical_json_dumps(output.model_dump(mode="python"))  # type: ignore[no-any-return]
    return canonical_json_dumps(output)


def _completed_output() -> object:
    result = run_harvest_state_model(make_request())
    assert result.status == "completed"
    return result


def _blocked_output() -> object:
    payload = make_request()
    payload["farm_timezone"] = "Bad/Timezone"
    result = run_harvest_state_model(payload)
    assert result.status == "blocked"
    return result


def _with_valid_result_hash(output: object) -> object:
    payload = output.model_dump(mode="python")
    payload.pop("result_hash", None)
    return output.model_copy(update={"result_hash": make_result_hash(payload)})


@pytest.mark.integration
async def test_harvest_state_tables_exist_after_migration_upgrade() -> None:
    _require_postgres()
    async with AsyncSessionMaker() as session:
        for table_name in (
            "harvest_state_run",
            "harvest_state_daily_pool_row",
            "harvest_state_daily_member_row",
            "harvest_state_cohort_transition_row",
            "harvest_state_future_arrival_row",
        ):
            exists = await session.scalar(select(func.to_regclass(table_name)))
            assert exists == table_name


@pytest.mark.integration
async def test_persist_and_load_completed_harvest_state_output_round_trip() -> None:
    _require_postgres()
    output = _completed_output()

    async with AsyncSessionMaker() as session:
        run = await save_harvest_state_output(session, output=output)
        loaded = await load_harvest_state_output_by_id(session, run_id=run.id)

        assert loaded is not None
        assert loaded.status == "completed"
        assert _canonical_output_json(loaded) == _canonical_output_json(output)
        assert await session.scalar(select(func.count()).select_from(HarvestStateRun)) == 1
        assert (
            await session.scalar(select(func.count()).select_from(HarvestStateDailyPoolRowModel))
            == len(output.daily_pool_state_rows)
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(HarvestStateDailyMemberRowModel)
            )
            == len(output.daily_member_state_rows)
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(HarvestStateCohortTransitionRowModel)
            )
            == len(output.cohort_transition_rows)
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(HarvestStateFutureArrivalRowModel)
            )
            == len(output.future_arrival_schedule)
        )


@pytest.mark.integration
async def test_persist_and_load_blocked_harvest_state_output_round_trip() -> None:
    _require_postgres()
    output = _blocked_output()

    async with AsyncSessionMaker() as session:
        run = await save_harvest_state_output(session, output=output)
        loaded = await load_harvest_state_output_by_id(session, run_id=run.id)

        assert loaded is not None
        assert loaded.status == "blocked"
        assert _canonical_output_json(loaded) == _canonical_output_json(output)
        assert await session.scalar(select(func.count()).select_from(HarvestStateRun)) == 1
        assert (
            await session.scalar(select(func.count()).select_from(HarvestStateDailyPoolRowModel))
            == 0
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(HarvestStateDailyMemberRowModel)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(HarvestStateCohortTransitionRowModel)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(HarvestStateFutureArrivalRowModel)
            )
            == 0
        )


@pytest.mark.integration
async def test_harvest_state_result_hash_is_idempotent() -> None:
    _require_postgres()
    output = _completed_output()

    async with AsyncSessionMaker() as session:
        first = await save_harvest_state_output(session, output=output)
        second = await save_harvest_state_output(session, output=output)

        assert first.id == second.id
        assert await session.scalar(select(func.count()).select_from(HarvestStateRun)) == 1


@pytest.mark.integration
async def test_harvest_state_same_hash_different_payload_raises_conflict() -> None:
    _require_postgres()
    output = _completed_output()

    async with AsyncSessionMaker() as session:
        run = await save_harvest_state_output(session, output=output)
        await session.execute(
            text(
                """
                UPDATE harvest_state_run
                SET canonical_output = CAST(:value AS jsonb),
                    canonical_payload_hash = :payload_hash
                WHERE id = :run_id
                """
            ),
            {
                "value": canonical_json_dumps(
                    output.model_copy(update={"warnings": ["pg-conflict"]}).model_dump(
                        mode="json"
                    )
                ),
                "payload_hash": "d" * 64,
                "run_id": run.id,
            },
        )
        await session.commit()
        with pytest.raises(HarvestStateHashConflictError):
            await save_harvest_state_output(session, output=output)


@pytest.mark.integration
async def test_harvest_state_transaction_rollback_on_child_failure() -> None:
    _require_postgres()
    output = _completed_output()
    broken = _with_valid_result_hash(
        output.model_copy(
            update={
                "daily_pool_state_rows": [
                    *output.daily_pool_state_rows,
                    output.daily_pool_state_rows[0],
                ]
            }
        )
    )

    async with AsyncSessionMaker() as session:
        with pytest.raises(IntegrityError):
            await save_harvest_state_output(session, output=broken)

        assert await session.scalar(select(func.count()).select_from(HarvestStateRun)) == 0
        assert (
            await session.scalar(select(func.count()).select_from(HarvestStateDailyPoolRowModel))
            == 0
        )


@pytest.mark.integration
async def test_harvest_state_jsonb_numeric_and_timezone_round_trip() -> None:
    _require_postgres()
    output = _completed_output()

    async with AsyncSessionMaker() as session:
        run = await save_harvest_state_output(session, output=output)
        loaded = await load_harvest_state_output_by_result_hash(
            session,
            result_hash=output.result_hash,
        )

        assert loaded is not None
        first_task8 = loaded.input_snapshot["task8_daily_predictions"][0]
        assert "verification_snapshot" in first_task8
        completed = loaded
        cohort_rows = completed.cohort_transition_rows  # type: ignore[attr-defined]
        assert any(
            row.arrival_at is not None and row.arrival_at.tzinfo is not None
            for row in cohort_rows
        )
        assert isinstance(cohort_rows[0].opening_quantity_kg, Decimal)
        stored_hash = await session.scalar(
            select(HarvestStateRun.result_hash).where(HarvestStateRun.id == run.id)
        )
        assert stored_hash == output.result_hash


@pytest.mark.integration
async def test_harvest_state_invalid_result_hash_constraint() -> None:
    _require_postgres()
    async with AsyncSessionMaker() as session:
        with pytest.raises(IntegrityError):
            await session.execute(
                text(
                    """
                    INSERT INTO harvest_state_run (
                        status,
                        output_schema_version,
                        result_hash_schema_version,
                        resolved_parameter_snapshot_schema_version,
                        source_ref_schema_version,
                        stable_cohort_key_schema_version,
                        input_snapshot,
                        resolved_parameter_snapshot,
                        source_ref_catalog,
                        warnings,
                        blockers,
                        mass_balance_result,
                        continuity_result,
                        canonical_output,
                        config_hash,
                        result_hash,
                        canonical_payload_hash,
                        forecast_start_date,
                        forecast_end_date,
                        as_of_date,
                        destination_factory_id,
                        pool_row_count,
                        member_row_count,
                        cohort_row_count,
                        future_arrival_row_count
                    ) VALUES (
                        'blocked',
                        'task9a-output-v1',
                        'task9a-result-hash-v1',
                        'task9a-resolved-parameters-v1',
                        'task9a-source-ref-v1',
                        'task9a-cohort-key-v1',
                        '{}'::jsonb,
                        NULL,
                        '[]'::jsonb,
                        '[]'::jsonb,
                        '["x"]'::jsonb,
                        NULL,
                        NULL,
                        CAST(:canonical_output AS jsonb),
                        :config_hash,
                        :result_hash,
                        :canonical_payload_hash,
                        DATE '2026-03-01',
                        DATE '2026-03-01',
                        DATE '2026-02-28',
                        1,
                        0,
                        0,
                        0,
                        0
                    )
                    """
                ),
                {
                    "canonical_output": canonical_json_dumps(
                        {
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
                            "blockers": ["x"],
                            "config_hash": "a" * 64,
                            "result_hash": "bad-hash",
                        }
                    ),
                    "config_hash": "a" * 64,
                    "result_hash": "bad-hash",
                    "canonical_payload_hash": "c" * 64,
                },
            )
            await session.commit()
        await session.rollback()


@pytest.mark.integration
async def test_postgres_round_trip_preserves_original_datetime_offsets() -> None:
    _require_postgres()
    output = _completed_output()

    async with AsyncSessionMaker() as session:
        run = await save_harvest_state_output(session, output=output)
        loaded = await load_harvest_state_output_by_id(session, run_id=run.id)

        assert loaded is not None
        original_rows = [
            row for row in output.cohort_transition_rows if row.arrival_at is not None
        ]
        loaded_rows = [
            row for row in loaded.cohort_transition_rows if row.arrival_at is not None  # type: ignore[attr-defined]
        ]
        assert original_rows
        assert loaded_rows
        assert loaded_rows[0].harvest_anchor_at is not None
        assert loaded_rows[0].arrival_at is not None
        assert original_rows[0].harvest_anchor_at is not None
        assert original_rows[0].arrival_at is not None
        assert (
            loaded_rows[0].harvest_anchor_at.isoformat()
            == original_rows[0].harvest_anchor_at.isoformat()
        )
        assert loaded_rows[0].arrival_at.isoformat() == original_rows[0].arrival_at.isoformat()


@pytest.mark.integration
async def test_duplicate_member_business_key_with_null_subfarm_rejected() -> None:
    _require_postgres()
    output = _with_valid_result_hash(_completed_output())
    completed = output.model_copy(
        update={
            "daily_member_state_rows": [
                row.model_copy(update={"subfarm_id": None})
                for row in output.daily_member_state_rows
            ],
            "future_arrival_schedule": [
                row.model_copy(update={"subfarm_id": None})
                for row in output.future_arrival_schedule
            ],
        }
    )
    completed = _with_valid_result_hash(completed)

    async with AsyncSessionMaker() as session:
        run = await save_harvest_state_output(session, output=completed)
        row = completed.daily_member_state_rows[0]
        session.add(
            HarvestStateDailyMemberRowModel(
                harvest_state_run_id=run.id,
                subfarm_identity_key="NONE",
                **row.model_dump(mode="python"),
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


@pytest.mark.integration
async def test_duplicate_future_arrival_key_with_null_subfarm_rejected() -> None:
    _require_postgres()
    output = _with_valid_result_hash(_completed_output())
    if not output.future_arrival_schedule:
        pytest.skip("fixture does not produce future arrivals")
    completed = output.model_copy(
        update={
            "daily_member_state_rows": [
                row.model_copy(update={"subfarm_id": None})
                for row in output.daily_member_state_rows
            ],
            "future_arrival_schedule": [
                row.model_copy(update={"subfarm_id": None})
                for row in output.future_arrival_schedule
            ],
        }
    )
    completed = _with_valid_result_hash(completed)

    async with AsyncSessionMaker() as session:
        run = await save_harvest_state_output(session, output=completed)
        row = completed.future_arrival_schedule[0]
        session.add(
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
            await session.commit()
        await session.rollback()


@pytest.mark.integration
async def test_load_rejects_missing_completed_pool_row() -> None:
    _require_postgres()
    output = _completed_output()

    async with AsyncSessionMaker() as session:
        run = await save_harvest_state_output(session, output=output)
        await session.execute(
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
        await session.commit()

        with pytest.raises(HarvestStatePersistenceIntegrityError):
            await load_harvest_state_output_by_id(session, run_id=run.id)


@pytest.mark.integration
async def test_load_rejects_blocked_run_with_state_rows() -> None:
    _require_postgres()
    blocked = _blocked_output()
    completed = _completed_output()

    async with AsyncSessionMaker() as session:
        run = await save_harvest_state_output(session, output=blocked)
        session.add(
            HarvestStateDailyPoolRowModel(
                harvest_state_run_id=run.id,
                **completed.daily_pool_state_rows[0].model_dump(mode="python"),
            )
        )
        await session.commit()

        with pytest.raises(HarvestStatePersistenceIntegrityError):
            await load_harvest_state_output_by_id(session, run_id=run.id)


@pytest.mark.integration
async def test_first_save_rejects_mismatched_result_hash() -> None:
    _require_postgres()
    output = _completed_output().model_copy(update={"result_hash": "f" * 64})

    async with AsyncSessionMaker() as session:
        with pytest.raises(HarvestStateResultHashMismatchError):
            await save_harvest_state_output(session, output=output)


@pytest.mark.integration
@pytest.mark.postgres_concurrency
async def test_concurrent_same_payload_save_creates_one_run() -> None:
    _require_postgres()
    output = _completed_output()

    async def save_once() -> int:
        async with AsyncSessionMaker() as session:
            run = await save_harvest_state_output(session, output=output)
            return run.id

    first_id, second_id = await asyncio.gather(save_once(), save_once())
    assert first_id == second_id

    async with AsyncSessionMaker() as session:
        run = await session.scalar(select(HarvestStateRun))
        assert run is not None
        assert await session.scalar(select(func.count()).select_from(HarvestStateRun)) == 1
        assert (
            await session.scalar(select(func.count()).select_from(HarvestStateDailyPoolRowModel))
            == len(output.daily_pool_state_rows)
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(HarvestStateDailyMemberRowModel)
            )
            == len(output.daily_member_state_rows)
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(HarvestStateCohortTransitionRowModel)
            )
            == len(output.cohort_transition_rows)
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(HarvestStateFutureArrivalRowModel)
            )
            == len(output.future_arrival_schedule)
        )


@pytest.mark.integration
@pytest.mark.postgres_concurrency
async def test_concurrent_same_hash_different_payload_conflicts() -> None:
    _require_postgres()
    output = _completed_output()
    conflicting_payload = output.model_copy(update={"warnings": ["pg-conflict"]}).model_dump(
        mode="json"
    )

    async def save_once() -> int:
        async with AsyncSessionMaker() as session:
            run = await save_harvest_state_output(session, output=output)
            return run.id

    async def insert_conflicting() -> str:
        async with AsyncSessionMaker() as session:
            as_of_date = output.input_snapshot["as_of_date"]
            await session.execute(
                text(
                    """
                    INSERT INTO harvest_state_run (
                        status,
                        output_schema_version,
                        result_hash_schema_version,
                        resolved_parameter_snapshot_schema_version,
                        source_ref_schema_version,
                        stable_cohort_key_schema_version,
                        input_snapshot,
                        resolved_parameter_snapshot,
                        source_ref_catalog,
                        warnings,
                        blockers,
                        mass_balance_result,
                        continuity_result,
                        canonical_output,
                        config_hash,
                        result_hash,
                        canonical_payload_hash,
                        forecast_start_date,
                        forecast_end_date,
                        as_of_date,
                        destination_factory_id,
                        pool_row_count,
                        member_row_count,
                        cohort_row_count,
                        future_arrival_row_count
                    ) VALUES (
                        'completed',
                        'task9a-output-v1',
                        'task9a-result-hash-v1',
                        'task9a-resolved-parameters-v1',
                        'task9a-source-ref-v1',
                        'task9a-cohort-key-v1',
                        CAST(:input_snapshot AS jsonb),
                        CAST(:resolved_parameter_snapshot AS jsonb),
                        CAST(:source_ref_catalog AS jsonb),
                        CAST(:warnings AS jsonb),
                        CAST(:blockers AS jsonb),
                        CAST(:mass_balance_result AS jsonb),
                        CAST(:continuity_result AS jsonb),
                        CAST(:canonical_output AS jsonb),
                        :config_hash,
                        :result_hash,
                        :canonical_payload_hash,
                        :forecast_start_date,
                        :forecast_end_date,
                        :as_of_date,
                        :destination_factory_id,
                        :pool_row_count,
                        :member_row_count,
                        :cohort_row_count,
                        :future_arrival_row_count
                    )
                    """
                ),
                {
                    "input_snapshot": canonical_json_dumps(output.input_snapshot),
                    "resolved_parameter_snapshot": canonical_json_dumps(
                        output.resolved_parameter_snapshot.model_dump(mode="json")
                    ),
                    "source_ref_catalog": canonical_json_dumps(
                        [item.model_dump(mode="json") for item in output.source_ref_catalog]
                    ),
                    "warnings": canonical_json_dumps(["pg-conflict"]),
                    "blockers": canonical_json_dumps([]),
                    "mass_balance_result": canonical_json_dumps(output.mass_balance_result),
                    "continuity_result": canonical_json_dumps(output.continuity_result),
                    "canonical_output": canonical_json_dumps(conflicting_payload),
                    "config_hash": output.config_hash,
                    "result_hash": output.result_hash,
                    "canonical_payload_hash": "d" * 64,
                    "forecast_start_date": output.forecast_start_date,
                    "forecast_end_date": output.forecast_end_date,
                    "as_of_date": (
                        date.fromisoformat(as_of_date)
                        if isinstance(as_of_date, str)
                        else as_of_date
                    ),
                    "destination_factory_id": output.input_snapshot["destination_factory_id"],
                    "pool_row_count": len(output.daily_pool_state_rows),
                    "member_row_count": len(output.daily_member_state_rows),
                    "cohort_row_count": len(output.cohort_transition_rows),
                    "future_arrival_row_count": len(output.future_arrival_schedule),
                },
            )
            await session.commit()
            return "inserted"

    service_result, raw_insert_result = await asyncio.gather(
        save_once(),
        insert_conflicting(),
        return_exceptions=True,
    )

    success_count = sum(
        not isinstance(item, BaseException)
        for item in (service_result, raw_insert_result)
    )
    assert success_count == 1
    if isinstance(service_result, BaseException):
        assert isinstance(
            service_result,
            (
                IntegrityError,
                HarvestStateHashConflictError,
                HarvestStatePersistenceIntegrityError,
            ),
        )
    else:
        assert isinstance(service_result, int)
    if isinstance(raw_insert_result, BaseException):
        assert isinstance(raw_insert_result, IntegrityError)
    else:
        assert raw_insert_result == "inserted"

    async with AsyncSessionMaker() as session:
        persisted = await session.scalar(select(HarvestStateRun))
        assert persisted is not None
        assert await session.scalar(select(func.count()).select_from(HarvestStateRun)) == 1
        pool_count = int(
            await session.scalar(select(func.count()).select_from(HarvestStateDailyPoolRowModel))
            or 0
        )
        member_count = int(
            await session.scalar(
                select(func.count()).select_from(HarvestStateDailyMemberRowModel)
            )
            or 0
        )
        cohort_count = int(
            await session.scalar(
                select(func.count()).select_from(HarvestStateCohortTransitionRowModel)
            )
            or 0
        )
        future_count = int(
            await session.scalar(
                select(func.count()).select_from(HarvestStateFutureArrivalRowModel)
            )
            or 0
        )

        if persisted.canonical_output == output.model_dump(mode="json"):
            loaded = await save_harvest_state_output(session, output=output)
            assert loaded.id == persisted.id
            assert pool_count == len(output.daily_pool_state_rows)
            assert member_count == len(output.daily_member_state_rows)
            assert cohort_count == len(output.cohort_transition_rows)
            assert future_count == len(output.future_arrival_schedule)
        else:
            assert persisted.canonical_output == conflicting_payload
            with pytest.raises(HarvestStateHashConflictError):
                await save_harvest_state_output(session, output=output)
            assert pool_count == 0
            assert member_count == 0
            assert cohort_count == 0
            assert future_count == 0
