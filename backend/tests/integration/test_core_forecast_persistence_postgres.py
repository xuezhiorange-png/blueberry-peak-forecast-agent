from __future__ import annotations

import asyncio
import os

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core_forecast.persistence import (
    CoreForecastPersistenceConflictError,
    CoreForecastRunRepository,
)
from backend.app.db.session import AsyncSessionMaker
from backend.app.models.core_forecast import (
    CoreForecastDailyRowModel,
    CoreForecastMetricModel,
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


async def _cleanup_s4_rows() -> None:
    async with AsyncSessionMaker() as session:
        await session.execute(delete(CoreForecastMetricModel))
        await session.execute(delete(CoreForecastDailyRowModel))
        await session.execute(delete(CoreForecastRunModel))
        await session.commit()


async def _seed_committed_authorities() -> None:
    async with AsyncSessionMaker() as session:
        await _seed_authorities(session)
        await session.commit()


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


async def test_concurrent_same_request_creates_one_physical_run() -> None:
    await _seed_committed_authorities()
    try:
        (
            request,
            curve,
            metrics,
            policy_hash,
            input_hash,
            request_hash,
            result_hash,
        ) = await fixture_request_and_outputs()
        barrier = asyncio.Barrier(2)

        async def save_once() -> int:
            async with AsyncSessionMaker() as session:
                async with session.begin():
                    await asyncio.wait_for(barrier.wait(), timeout=10)
                    persisted = await CoreForecastRunRepository(session).save_completed_run(
                        request=request,
                        forecast_input_hash=input_hash,
                        request_hash=request_hash,
                        result_hash=result_hash,
                        retention_policy_snapshot_hash=policy_hash,
                        curve=curve,
                        metrics=metrics,
                        rerun_of_run_id=None,
                    )
                    return persisted.run.run_id

        first_id, second_id = await asyncio.wait_for(
            asyncio.gather(save_once(), save_once()), timeout=60
        )
        assert first_id == second_id
        async with AsyncSessionMaker() as verify:
            assert await verify.scalar(select(func.count(CoreForecastRunModel.id))) == 1
            assert await verify.scalar(select(func.count(CoreForecastDailyRowModel.id))) == 1080
            assert await verify.scalar(select(func.count(CoreForecastMetricModel.id))) == 3
    finally:
        await _cleanup_s4_rows()


async def test_existing_same_hash_different_payload_raises_conflict() -> None:
    await _seed_committed_authorities()
    try:
        (
            request,
            curve,
            metrics,
            policy_hash,
            input_hash,
            request_hash,
            result_hash,
        ) = await fixture_request_and_outputs()
        async with AsyncSessionMaker() as session:
            async with session.begin():
                await CoreForecastRunRepository(session).save_completed_run(
                    request=request,
                    forecast_input_hash=input_hash,
                    request_hash=request_hash,
                    result_hash=result_hash,
                    retention_policy_snapshot_hash=policy_hash,
                    curve=curve,
                    metrics=metrics,
                    rerun_of_run_id=None,
                )

        async with AsyncSessionMaker() as conflict_session:
            repository = CoreForecastRunRepository(conflict_session)
            with pytest.raises(CoreForecastPersistenceConflictError) as exc_info:
                await repository.save_completed_run(
                    request=request,
                    forecast_input_hash=input_hash,
                    request_hash=request_hash,
                    result_hash="f" * 64,
                    retention_policy_snapshot_hash=policy_hash,
                    curve=curve,
                    metrics=metrics,
                    rerun_of_run_id=None,
                )
            assert str(exc_info.value) == (
                "request hash already exists with different canonical content"
            )
            await conflict_session.rollback()
    finally:
        await _cleanup_s4_rows()
