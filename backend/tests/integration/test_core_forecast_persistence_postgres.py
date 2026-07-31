from __future__ import annotations

import asyncio
import hashlib
import os
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core_forecast.persistence import (
    CoreForecastPersistenceConflictError,
    CoreForecastRunRepository,
)
from backend.app.core_forecast.repository import (
    MarketableRetentionPolicyConflictError,
    MarketableRetentionPolicyMissingError,
    SqlAlchemyCoreForecastRepository,
)
from backend.app.db.session import AsyncSessionMaker
from backend.app.models.core_forecast import (
    CoreForecastDailyRowModel,
    CoreForecastMetricModel,
    CoreForecastRunModel,
)
from backend.app.models.trial import (
    CoreForecastMarketablePolicyEntryModel,
    CoreForecastMarketablePolicyModel,
    TrialResourceBindingModel,
)
from backend.tests.core_forecast.s4_test_helpers import fixture_request_and_outputs
from backend.tests.integration.test_v0_1_s2_complete_daily_curve_postgres import (
    FACTORY_ID,
    SEASON_ID,
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


async def _seed_marketable_policy(
    session: AsyncSession,
    *,
    public_hash: str,
    status: str = "ACTIVE",
    scopes: tuple[tuple[int, int, int], ...] = ((101, 1101, 2101),),
    available_at: datetime = datetime(2026, 2, 1, tzinfo=UTC),
    effective_from: date = date(2026, 1, 1),
    effective_to: date | None = date(2026, 12, 31),
) -> None:
    header = CoreForecastMarketablePolicyModel(
        public_policy_hash=public_hash,
        row_set_hash="e" * 64,
        policy_version="marketable-v1",
        season_id=SEASON_ID,
        factory_id=FACTORY_ID,
        source_system="authority-fixture",
        source_record_key=f"record-{public_hash[:8]}",
        available_at=available_at,
        effective_from=effective_from,
        effective_to=effective_to,
        status=status,
    )
    session.add(header)
    await session.flush()
    for index, (farm_id, subfarm_id, variety_id) in enumerate(scopes):
        session.add(
            CoreForecastMarketablePolicyEntryModel(
                policy_id=header.id,
                farm_id=farm_id,
                subfarm_id=subfarm_id,
                variety_id=variety_id,
                sorting_retention_rate=Decimal("0.800000"),
                postharvest_retention_rate=Decimal("0.900000"),
                source_version="marketable-v1",
                row_hash=hashlib.sha256(f"{public_hash}:{index}".encode()).hexdigest(),
            )
        )
    await session.flush()


async def test_postgres_marketable_policy_selector_requires_exact_complete_scope(
    transactional_pg_session: AsyncSession,
) -> None:
    await _seed_authorities(transactional_pg_session)
    await _seed_marketable_policy(transactional_pg_session, public_hash="a" * 64)
    repository = SqlAlchemyCoreForecastRepository(transactional_pg_session)
    result = await repository.load_marketable_retention_policy(
        season_id=SEASON_ID,
        factory_id=FACTORY_ID,
        forecast_cutoff_at=datetime(2026, 2, 15, tzinfo=UTC),
        forecast_start_date=date(2026, 2, 1),
        forecast_end_date=date(2026, 4, 30),
        scopes=((101, 1101, 2101),),
    )
    assert result.entries[0].sorting_retention_rate == "0.800000"
    assert result.entries[0].hash == "a" * 64
    with pytest.raises(MarketableRetentionPolicyMissingError):
        await repository.load_marketable_retention_policy(
            season_id=SEASON_ID,
            factory_id=FACTORY_ID,
            forecast_cutoff_at=datetime(2026, 2, 15, tzinfo=UTC),
            forecast_start_date=date(2026, 2, 1),
            forecast_end_date=date(2026, 4, 30),
            scopes=((101, 1101, 2101), (101, 1102, 2102)),
        )


async def test_postgres_marketable_policy_selector_is_ambiguous_without_latest_winner(
    transactional_pg_session: AsyncSession,
) -> None:
    await _seed_authorities(transactional_pg_session)
    await _seed_marketable_policy(transactional_pg_session, public_hash="a" * 64)
    await _seed_marketable_policy(transactional_pg_session, public_hash="b" * 64)
    repository = SqlAlchemyCoreForecastRepository(transactional_pg_session)
    with pytest.raises(MarketableRetentionPolicyConflictError):
        await repository.load_marketable_retention_policy(
            season_id=SEASON_ID,
            factory_id=FACTORY_ID,
            forecast_cutoff_at=datetime(2026, 2, 15, tzinfo=UTC),
            forecast_start_date=date(2026, 2, 1),
            forecast_end_date=date(2026, 4, 30),
            scopes=((101, 1101, 2101),),
        )


async def test_postgres_trial_binding_identity_fields_are_database_immutable(
    transactional_pg_session: AsyncSession,
) -> None:
    binding = TrialResourceBindingModel(
        resource_kind="FORECAST",
        public_resource_id="a" * 64,
        owner_identity="actor:one",
        business_scope_hash="b" * 64,
        parent_forecast_public_id=None,
        parent_import_id=None,
    )
    transactional_pg_session.add(binding)
    await transactional_pg_session.flush()
    for field, value in {
        "resource_kind": "QUALITY_REPORT",
        "public_resource_id": "c" * 64,
        "owner_identity": "actor:two",
        "business_scope_hash": "d" * 64,
        "parent_forecast_public_id": "e" * 64,
        "parent_import_id": "import-2",
    }.items():
        with pytest.raises(IntegrityError):
            async with transactional_pg_session.begin_nested():
                await transactional_pg_session.execute(
                    update(TrialResourceBindingModel)
                    .where(TrialResourceBindingModel.id == binding.id)
                    .values(**{field: value})
                )
                await transactional_pg_session.flush()


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
