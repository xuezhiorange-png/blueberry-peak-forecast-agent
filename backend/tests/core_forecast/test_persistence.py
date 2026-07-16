from __future__ import annotations

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core_forecast.persistence import (
    CoreForecastPersistenceConflictError,
    CoreForecastPersistenceIntegrityError,
    CoreForecastRunRepository,
)
from backend.app.models.core_forecast import CoreForecastDailyRowModel, CoreForecastRunModel
from backend.tests.core_forecast.s4_test_helpers import fixture_request_and_outputs


@pytest.mark.unit
async def test_full_fixture_save_load_and_query_order(sqlite_session: AsyncSession) -> None:
    (
        request,
        curve,
        metrics,
        policy_hash,
        input_hash,
        request_hash,
        result_hash,
    ) = await fixture_request_and_outputs()
    repository = CoreForecastRunRepository(sqlite_session)
    persisted = await repository.save_completed_run(
        request=request,
        forecast_input_hash=input_hash,
        request_hash=request_hash,
        result_hash=result_hash,
        retention_policy_snapshot_hash=policy_hash,
        curve=curve,
        metrics=metrics,
        rerun_of_run_id=None,
    )
    loaded = await repository.get_run_by_id(persisted.run.run_id)
    assert loaded is not None
    assert loaded.run.result_hash == result_hash
    assert len(await repository.list_daily_rows(persisted.run.run_id)) == 1080
    assert tuple(
        item.forecast_quantile for item in await repository.list_metrics(persisted.run.run_id)
    ) == (
        "P50",
        "P80",
        "P90",
    )
    assert await sqlite_session.scalar(select(CoreForecastDailyRowModel.id)) is not None


@pytest.mark.unit
async def test_same_request_reuses_identical_run(sqlite_session: AsyncSession) -> None:
    (
        request,
        curve,
        metrics,
        policy_hash,
        input_hash,
        request_hash,
        result_hash,
    ) = await fixture_request_and_outputs()
    repository = CoreForecastRunRepository(sqlite_session)
    first = await repository.save_completed_run(
        request=request,
        forecast_input_hash=input_hash,
        request_hash=request_hash,
        result_hash=result_hash,
        retention_policy_snapshot_hash=policy_hash,
        curve=curve,
        metrics=metrics,
        rerun_of_run_id=None,
    )
    second = await repository.save_completed_run(
        request=request,
        forecast_input_hash=input_hash,
        request_hash=request_hash,
        result_hash=result_hash,
        retention_policy_snapshot_hash=policy_hash,
        curve=curve,
        metrics=metrics,
        rerun_of_run_id=None,
    )
    assert second.run.run_id == first.run.run_id


@pytest.mark.unit
async def test_same_request_hash_different_result_is_conflict(sqlite_session: AsyncSession) -> None:
    (
        request,
        curve,
        metrics,
        policy_hash,
        input_hash,
        request_hash,
        result_hash,
    ) = await fixture_request_and_outputs()
    repository = CoreForecastRunRepository(sqlite_session)
    await repository.save_completed_run(
        request=request,
        forecast_input_hash=input_hash,
        request_hash=request_hash,
        result_hash=result_hash,
        retention_policy_snapshot_hash=policy_hash,
        curve=curve,
        metrics=metrics,
        rerun_of_run_id=None,
    )
    with pytest.raises(CoreForecastPersistenceConflictError):
        await repository.save_completed_run(
            request=request,
            forecast_input_hash=input_hash,
            request_hash=request_hash,
            result_hash="c" * 64,
            retention_policy_snapshot_hash=policy_hash,
            curve=curve,
            metrics=metrics,
            rerun_of_run_id=None,
        )


@pytest.mark.unit
async def test_tampered_daily_row_fails_integrity_gate(sqlite_session: AsyncSession) -> None:
    (
        request,
        curve,
        metrics,
        policy_hash,
        input_hash,
        request_hash,
        result_hash,
    ) = await fixture_request_and_outputs()
    repository = CoreForecastRunRepository(sqlite_session)
    persisted = await repository.save_completed_run(
        request=request,
        forecast_input_hash=input_hash,
        request_hash=request_hash,
        result_hash=result_hash,
        retention_policy_snapshot_hash=policy_hash,
        curve=curve,
        metrics=metrics,
        rerun_of_run_id=None,
    )
    await sqlite_session.execute(
        update(CoreForecastDailyRowModel)
        .where(CoreForecastDailyRowModel.core_forecast_run_id == persisted.run.run_id)
        .values(effective_marketable_quantity_kg=999)
    )
    with pytest.raises(CoreForecastPersistenceIntegrityError):
        await repository.load_complete_run(persisted.run.run_id)


@pytest.mark.unit
async def test_repository_does_not_commit_and_caller_rollback_removes_all_rows(
    sqlite_session: AsyncSession,
) -> None:
    (
        request,
        curve,
        metrics,
        policy_hash,
        input_hash,
        request_hash,
        result_hash,
    ) = await fixture_request_and_outputs()
    repository = CoreForecastRunRepository(sqlite_session)
    connection = await sqlite_session.connection()
    await connection.exec_driver_sql("BEGIN")
    await repository.save_completed_run(
        request=request,
        forecast_input_hash=input_hash,
        request_hash=request_hash,
        result_hash=result_hash,
        retention_policy_snapshot_hash=policy_hash,
        curve=curve,
        metrics=metrics,
        rerun_of_run_id=None,
    )
    assert await sqlite_session.scalar(select(func.count(CoreForecastRunModel.id))) == 1
    await sqlite_session.rollback()
    assert await sqlite_session.scalar(select(func.count(CoreForecastRunModel.id))) == 0
    assert await sqlite_session.scalar(select(func.count(CoreForecastDailyRowModel.id))) == 0
