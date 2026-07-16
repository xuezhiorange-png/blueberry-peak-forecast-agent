from __future__ import annotations

import os

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core_forecast.persistence import CoreForecastRunRepository
from backend.app.models.core_forecast import (
    CoreForecastDailyRowModel,
    CoreForecastRunModel,
)
from backend.tests.core_forecast.s4_test_helpers import fixture_request_and_outputs
from backend.tests.integration.test_v0_1_s2_complete_daily_curve_postgres import (
    _seed_authorities,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
        reason="LOCAL_POSTGRES_NOT_AVAILABLE",
    ),
]


async def test_postgres_core_forecast_persistence_round_trip_and_integrity(
    transactional_pg_session: AsyncSession,
) -> None:
    await _seed_authorities(transactional_pg_session)
    (
        request,
        curve,
        metrics,
        policy_hash,
        input_hash,
        request_hash,
        result_hash,
    ) = await fixture_request_and_outputs()
    repository = CoreForecastRunRepository(transactional_pg_session)

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

    assert (
        persisted.run.curve_hash
        == "de81bfa3a23efcef0398758e5105199eede9222adb0aff4acda67f3fe9697687"
    )
    assert (
        persisted.run.metrics_hash
        == "cfba5f2af9236e907527ef72d2d8e0a34b99f2cad29aaac502e6159c1d6d586a"
    )
    assert len(await repository.list_daily_rows(persisted.run.run_id)) == 1080
    assert len(await repository.list_metrics(persisted.run.run_id)) == 3
    assert (
        await repository.get_run_by_request_hash(request_hash)
    ).run.run_id == persisted.run.run_id  # type: ignore[union-attr]
    assert (await repository.get_run_by_result_hash(result_hash)).run.run_id == persisted.run.run_id  # type: ignore[union-attr]

    duplicate = await repository.save_completed_run(
        request=request,
        forecast_input_hash=input_hash,
        request_hash=request_hash,
        result_hash=result_hash,
        retention_policy_snapshot_hash=policy_hash,
        curve=curve,
        metrics=metrics,
        rerun_of_run_id=None,
    )
    assert duplicate.run.run_id == persisted.run.run_id


async def test_postgres_core_forecast_parent_delete_is_restricted(
    transactional_pg_session: AsyncSession,
) -> None:
    await _seed_authorities(transactional_pg_session)
    (
        request,
        curve,
        metrics,
        policy_hash,
        input_hash,
        request_hash,
        result_hash,
    ) = await fixture_request_and_outputs()
    repository = CoreForecastRunRepository(transactional_pg_session)
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

    with pytest.raises(IntegrityError):
        await transactional_pg_session.execute(
            delete(CoreForecastRunModel).where(CoreForecastRunModel.id == persisted.run.run_id)
        )
        await transactional_pg_session.flush()
    await transactional_pg_session.rollback()


async def test_postgres_core_forecast_constraints_reject_duplicate_daily_key(
    transactional_pg_session: AsyncSession,
) -> None:
    await _seed_authorities(transactional_pg_session)
    (
        request,
        curve,
        metrics,
        policy_hash,
        input_hash,
        request_hash,
        result_hash,
    ) = await fixture_request_and_outputs()
    repository = CoreForecastRunRepository(transactional_pg_session)
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
    existing_row = await transactional_pg_session.scalar(
        select(CoreForecastDailyRowModel).where(
            CoreForecastDailyRowModel.core_forecast_run_id == persisted.run.run_id
        )
    )
    assert existing_row is not None
    duplicate = CoreForecastDailyRowModel(
        **{
            column.name: getattr(existing_row, column.name)
            for column in CoreForecastDailyRowModel.__table__.columns
            if column.name != "id"
        }
    )
    transactional_pg_session.add(duplicate)
    with pytest.raises(IntegrityError):
        await transactional_pg_session.flush()
    await transactional_pg_session.rollback()
