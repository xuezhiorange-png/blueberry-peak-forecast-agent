from __future__ import annotations

import os
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from backend.app.db.session import AsyncSessionMaker
from backend.app.harvest_state.canonical import canonical_json_dumps
from backend.app.harvest_state.persistence import (
    HarvestStateHashConflictError,
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

pytestmark = pytest.mark.integration


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


@pytest.mark.integration
async def test_harvest_state_migration_upgrade() -> None:
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
    conflicting = output.model_copy(
        update={
            "warnings": ["pg-conflict"],
            "result_hash": output.result_hash,
        }
    )

    async with AsyncSessionMaker() as session:
        await save_harvest_state_output(session, output=output)
        with pytest.raises(HarvestStateHashConflictError):
            await save_harvest_state_output(session, output=conflicting)


@pytest.mark.integration
async def test_harvest_state_transaction_rollback_on_child_failure() -> None:
    _require_postgres()
    output = _completed_output()
    broken = output.model_copy(
        update={
            "daily_pool_state_rows": [
                *output.daily_pool_state_rows,
                output.daily_pool_state_rows[0],
            ]
        }
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
                    config_hash,
                    result_hash,
                    forecast_start_date,
                    forecast_end_date,
                    as_of_date,
                    destination_factory_id
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
                    :config_hash,
                    :result_hash,
                    DATE '2026-03-01',
                    DATE '2026-03-01',
                    DATE '2026-02-28',
                    1
                )
                """
            ),
            {
                "config_hash": "a" * 64,
                "result_hash": "bad-hash",
            },
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()
