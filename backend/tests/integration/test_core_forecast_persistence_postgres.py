from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import os
import re
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import and_, delete, func, not_, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.actual_harvest_import.api_auth import ActualHarvestActorContext
from backend.app.actual_harvest_import.enums import ActualHarvestImportChannel
from backend.app.core_forecast.persistence import (
    CoreForecastPersistenceConflictError,
    CoreForecastRunRepository,
)
from backend.app.core_forecast.repository import (
    MarketableRetentionPolicyConflictError,
    MarketableRetentionPolicyMissingError,
    SqlAlchemyCoreForecastRepository,
)
from backend.app.core_forecast.schemas import RegisterCoreForecastCodeAuthority
from backend.app.db.session import AsyncSessionMaker
from backend.app.models.core_forecast import (
    CoreForecastDailyRowModel,
    CoreForecastMetricModel,
    CoreForecastRunModel,
)
from backend.app.models.harvest_state import HarvestStateDailyMemberRowModel, HarvestStateRun
from backend.app.models.maturity import MaturityDailyPredictionModel
from backend.app.models.production_plan import FarmSeasonVarietyPlan
from backend.app.models.trial import (
    CoreForecastMarketablePolicyEntryModel,
    CoreForecastMarketablePolicyModel,
    TrialForecastEvidenceModel,
    TrialResourceBindingModel,
)
from backend.app.repositories.trial_forecast_evidence import (
    TrialForecastEvidenceConflictError,
    TrialForecastEvidenceIntegrityError,
    TrialForecastEvidenceNotFoundError,
    authorize_and_load_forecast_evidence,
    compute_trial_business_scope_hash,
    create_forecast_evidence_and_binding_in_result_boundary,
)
from backend.app.trial import (
    DefaultTrialApplicationService,
    TrialApiError,
    TrialApiErrorCode,
    TrialForecastCreateRequest,
)
from backend.tests.core_forecast.s4_test_helpers import fixture_request_and_outputs
from backend.tests.integration.test_v0_1_s2_complete_daily_curve_postgres import (
    FACTORY_ID,
    INPUT,
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


async def _cleanup_s4_rows(public_forecast_id: str | None = None) -> None:
    async with AsyncSessionMaker() as session:
        if public_forecast_id is not None:
            await session.execute(
                delete(TrialResourceBindingModel).where(
                    TrialResourceBindingModel.resource_kind == "FORECAST",
                    TrialResourceBindingModel.public_resource_id == public_forecast_id,
                )
            )
            await session.execute(
                delete(TrialForecastEvidenceModel).where(
                    TrialForecastEvidenceModel.public_forecast_id == public_forecast_id
                )
            )
        await session.execute(delete(CoreForecastMetricModel))
        await session.execute(delete(CoreForecastDailyRowModel))
        await session.execute(delete(CoreForecastRunModel))
        await session.commit()


async def _truncate_s4_rows_for_postgres_test() -> None:
    """Reset committed S4 rows without bypassing the immutable-row assertion."""

    async with AsyncSessionMaker() as session:
        await session.execute(
            text(
                "TRUNCATE trial_resource_binding, trial_forecast_evidence, "
                "core_forecast_metric, core_forecast_daily_row, core_forecast_run "
                "RESTART IDENTITY CASCADE"
            )
        )
        await session.commit()


async def _seed_committed_authorities() -> None:
    async with AsyncSessionMaker() as session:
        await _seed_authorities(session)
        await session.commit()


async def _persist_core_run(session: AsyncSession) -> str:
    await _seed_authorities(session)
    (
        request,
        curve,
        metrics,
        policy_hash,
        input_hash,
        request_hash,
        result_hash,
    ) = await fixture_request_and_outputs()
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
    assert persisted.run.request_hash == request_hash
    return request_hash


async def _persist_committed_core_run() -> str:
    async with AsyncSessionMaker() as session:
        async with session.begin():
            return await _persist_core_run(session)


def _evidence_input(
    public_forecast_id: str,
    *,
    owner_identity: str = "actor:postgres-evidence",
    forecast_input_authority_hash: str = "a" * 64,
    plan_row_hash: str = "b" * 64,
    farm_business_key: str = "farm-postgres",
    subfarm_business_key_or_null: str | None = "subfarm-postgres",
    season_business_key: str = "season-2026",
    variety_business_key: str = "variety-blue",
    destination_factory_business_key: str = "factory-main",
    plan_version: str = "plan-v1",
    planting_area_mu: Decimal = Decimal("12.340000"),
) -> dict[str, object]:
    return {
        "public_forecast_id": public_forecast_id,
        "owner_identity": owner_identity,
        "forecast_input_authority_hash": forecast_input_authority_hash,
        "authority_available_at": datetime(2026, 1, 1, tzinfo=UTC),
        "farm_business_key": farm_business_key,
        "subfarm_business_key_or_null": subfarm_business_key_or_null,
        "season_business_key": season_business_key,
        "variety_business_key": variety_business_key,
        "destination_factory_business_key": destination_factory_business_key,
        "plan_version": plan_version,
        "plan_row_hash": plan_row_hash,
        "planting_area_mu": planting_area_mu,
    }


async def _related_row_counts(
    session: AsyncSession,
    public_forecast_id: str,
) -> tuple[int, int, int]:
    core_run_count = await session.scalar(
        select(func.count())
        .select_from(CoreForecastRunModel)
        .where(CoreForecastRunModel.request_hash == public_forecast_id)
    )
    evidence_count = await session.scalar(
        select(func.count())
        .select_from(TrialForecastEvidenceModel)
        .where(TrialForecastEvidenceModel.public_forecast_id == public_forecast_id)
    )
    binding_count = await session.scalar(
        select(func.count())
        .select_from(TrialResourceBindingModel)
        .where(
            TrialResourceBindingModel.resource_kind == "FORECAST",
            TrialResourceBindingModel.public_resource_id == public_forecast_id,
        )
    )
    return int(core_run_count or 0), int(evidence_count or 0), int(binding_count or 0)


async def _all_forecast_row_counts(session: AsyncSession) -> tuple[int, int, int]:
    core_run_count = await session.scalar(select(func.count()).select_from(CoreForecastRunModel))
    evidence_count = await session.scalar(
        select(func.count()).select_from(TrialForecastEvidenceModel)
    )
    binding_count = await session.scalar(
        select(func.count())
        .select_from(TrialResourceBindingModel)
        .where(TrialResourceBindingModel.resource_kind == "FORECAST")
    )
    return int(core_run_count or 0), int(evidence_count or 0), int(binding_count or 0)


async def _cleanup_pg_failure_trigger(
    *,
    table_name: str,
    trigger_name: str,
    function_name: str,
) -> None:
    async with AsyncSessionMaker() as session:
        async with session.begin():
            await session.execute(text(f"DROP TRIGGER IF EXISTS {trigger_name} ON {table_name}"))
            await session.execute(text(f"DROP FUNCTION IF EXISTS {function_name}()"))


async def _install_pg_evidence_insert_failure_trigger(session: AsyncSession) -> None:
    await session.execute(
        text(
            """
            CREATE OR REPLACE FUNCTION test_trial_forecast_evidence_insert_failure()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION 'test evidence insert failure' USING ERRCODE = '23514';
            END;
            $$
            """
        )
    )
    await session.execute(
        text(
            """
            DROP TRIGGER IF EXISTS test_trial_forecast_evidence_insert_failure_trigger
                ON trial_forecast_evidence
            """
        )
    )
    await session.execute(
        text(
            """
            CREATE TRIGGER test_trial_forecast_evidence_insert_failure_trigger
            BEFORE INSERT ON trial_forecast_evidence
            FOR EACH ROW
            EXECUTE FUNCTION test_trial_forecast_evidence_insert_failure()
            """
        )
    )


async def _install_pg_forecast_binding_insert_failure_trigger(session: AsyncSession) -> None:
    await session.execute(
        text(
            """
            CREATE OR REPLACE FUNCTION test_trial_forecast_binding_insert_failure()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF NEW.resource_kind = 'FORECAST' THEN
                    RAISE EXCEPTION 'test forecast binding insert failure'
                        USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END;
            $$
            """
        )
    )
    await session.execute(
        text(
            """
            DROP TRIGGER IF EXISTS test_trial_forecast_binding_insert_failure_trigger
                ON trial_resource_binding
            """
        )
    )
    await session.execute(
        text(
            """
            CREATE TRIGGER test_trial_forecast_binding_insert_failure_trigger
            BEFORE INSERT ON trial_resource_binding
            FOR EACH ROW
            EXECUTE FUNCTION test_trial_forecast_binding_insert_failure()
            """
        )
    )


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


async def test_postgres_trial_forecast_evidence_readback_and_immutable_guards(
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
    persisted = await CoreForecastRunRepository(transactional_pg_session).save_completed_run(
        request=request,
        forecast_input_hash=input_hash,
        request_hash=request_hash,
        result_hash=result_hash,
        retention_policy_snapshot_hash=policy_hash,
        curve=curve,
        metrics=metrics,
        rerun_of_run_id=None,
    )
    assert persisted.run.request_hash == request_hash

    created = await create_forecast_evidence_and_binding_in_result_boundary(
        transactional_pg_session,
        public_forecast_id=request_hash,
        owner_identity="actor:postgres",
        forecast_input_authority_hash="a" * 64,
        authority_available_at=datetime(2026, 1, 1, tzinfo=UTC),
        farm_business_key="farm-postgres",
        subfarm_business_key_or_null="subfarm-postgres",
        season_business_key="season-2026",
        variety_business_key="variety-blue",
        destination_factory_business_key="factory-main",
        plan_version="plan-v1",
        plan_row_hash="b" * 64,
        planting_area_mu=Decimal("12.340000"),
    )
    replay = await create_forecast_evidence_and_binding_in_result_boundary(
        transactional_pg_session,
        public_forecast_id=request_hash,
        owner_identity="actor:postgres",
        forecast_input_authority_hash="a" * 64,
        authority_available_at=datetime(2026, 1, 1, tzinfo=UTC),
        farm_business_key="farm-postgres",
        subfarm_business_key_or_null="subfarm-postgres",
        season_business_key="season-2026",
        variety_business_key="variety-blue",
        destination_factory_business_key="factory-main",
        plan_version="plan-v1",
        plan_row_hash="b" * 64,
        planting_area_mu=Decimal("12.340000"),
    )
    assert replay == created
    loaded = await authorize_and_load_forecast_evidence(
        transactional_pg_session,
        public_forecast_id=request_hash,
        owner_identity="actor:postgres",
    )
    assert loaded == created
    assert (
        await transactional_pg_session.scalar(
            select(func.count()).select_from(TrialForecastEvidenceModel)
        )
    ) == 1
    assert (
        await transactional_pg_session.scalar(
            select(func.count()).select_from(TrialResourceBindingModel)
        )
    ) == 1

    for statement in (
        "UPDATE trial_forecast_evidence SET plan_version = 'tampered' "
        "WHERE public_forecast_id = :public_forecast_id",
        "DELETE FROM trial_forecast_evidence WHERE public_forecast_id = :public_forecast_id",
    ):
        with pytest.raises(DBAPIError) as caught:
            async with transactional_pg_session.begin_nested():
                await transactional_pg_session.execute(
                    text(statement),
                    {"public_forecast_id": request_hash},
                )
        original = caught.value.orig
        assert getattr(original, "sqlstate", None) == "23514"
        assert "trial forecast evidence is immutable" in str(original)


async def test_postgres_trial_forecast_evidence_and_binding_rollback_with_core_run(
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
    await CoreForecastRunRepository(transactional_pg_session).save_completed_run(
        request=request,
        forecast_input_hash=input_hash,
        request_hash=request_hash,
        result_hash=result_hash,
        retention_policy_snapshot_hash=policy_hash,
        curve=curve,
        metrics=metrics,
        rerun_of_run_id=None,
    )
    await create_forecast_evidence_and_binding_in_result_boundary(
        transactional_pg_session,
        public_forecast_id=request_hash,
        owner_identity="actor:rollback",
        forecast_input_authority_hash="c" * 64,
        authority_available_at=datetime(2026, 1, 1, tzinfo=UTC),
        farm_business_key="farm-rollback",
        subfarm_business_key_or_null=None,
        season_business_key="season-2026",
        variety_business_key="variety-blue",
        destination_factory_business_key="factory-main",
        plan_version="plan-v1",
        plan_row_hash="d" * 64,
        planting_area_mu=Decimal("1.000000"),
    )
    await transactional_pg_session.rollback()
    assert (
        await transactional_pg_session.scalar(
            select(func.count())
            .select_from(CoreForecastRunModel)
            .where(CoreForecastRunModel.request_hash == request_hash)
        )
    ) == 0
    assert (
        await transactional_pg_session.scalar(
            select(func.count())
            .select_from(TrialForecastEvidenceModel)
            .where(TrialForecastEvidenceModel.public_forecast_id == request_hash)
        )
    ) == 0
    assert (
        await transactional_pg_session.scalar(
            select(func.count())
            .select_from(TrialResourceBindingModel)
            .where(TrialResourceBindingModel.public_resource_id == request_hash)
        )
    ) == 0


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
    sorting_retention_rate: Decimal = Decimal("0.800000"),
    postharvest_retention_rate: Decimal = Decimal("0.900000"),
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
                sorting_retention_rate=sorting_retention_rate,
                postharvest_retention_rate=postharvest_retention_rate,
                source_version="marketable-v1",
                row_hash=hashlib.sha256(f"{public_hash}:{index}".encode()).hexdigest(),
            )
        )
    await session.flush()


def _forecast_actor(identity: str) -> ActualHarvestActorContext:
    return ActualHarvestActorContext(
        identity=identity,
        allowed_source_systems=frozenset({"trial-api"}),
        allowed_channels=frozenset({ActualHarvestImportChannel.API}),
        may_read_forecast_authority=True,
        may_create_forecast=True,
        may_read_forecast=True,
        may_export_forecast=True,
    )


async def _restrict_authorities_to_trial_scope(session: AsyncSession) -> None:
    farm_id, subfarm_id, variety_id = 101, 1101, 2101
    await session.execute(
        delete(HarvestStateDailyMemberRowModel).where(
            not_(
                and_(
                    HarvestStateDailyMemberRowModel.farm_id == farm_id,
                    HarvestStateDailyMemberRowModel.subfarm_id == subfarm_id,
                    HarvestStateDailyMemberRowModel.variety_id == variety_id,
                )
            )
        )
    )
    await session.execute(
        delete(MaturityDailyPredictionModel).where(
            MaturityDailyPredictionModel.forecast_run_id == 810001
        )
    )

    by_day_quantile: dict[tuple[date, str], Decimal] = defaultdict(lambda: Decimal("0"))
    for source in INPUT["daily_inputs"]:
        if (source["farm_id"], source["subfarm_id"], source["variety_id"]) == (
            farm_id,
            subfarm_id,
            variety_id,
        ):
            by_day_quantile[(date.fromisoformat(source["date"]), source["forecast_quantile"])] += (
                Decimal(source["natural_maturity_supply_kg"])
            )

    cumulative = {quantile: Decimal("0") for quantile in ("P50", "P80", "P90")}
    start = date.fromisoformat(INPUT["season"]["forecast_start_date"])
    for offset in range(90):
        current_date = start + timedelta(days=offset)
        values = {
            quantile: by_day_quantile[(current_date, quantile)]
            for quantile in ("P50", "P80", "P90")
        }
        for quantile, value in values.items():
            cumulative[quantile] += value
        session.add(
            MaturityDailyPredictionModel(
                forecast_run_id=810001,
                prediction_date=current_date,
                phenology_coordinate_day=Decimal(offset + 1),
                p50_kg=values["P50"],
                p80_kg=values["P80"],
                p90_kg=values["P90"],
                cumulative_p50_kg=cumulative["P50"],
                cumulative_p80_kg=cumulative["P80"],
                cumulative_p90_kg=cumulative["P90"],
                curve_share=Decimal("0.0100000000"),
                confidence_level="HIGH",
                quality_flags=[],
            )
        )
    await session.execute(
        update(HarvestStateRun).where(HarvestStateRun.id == 910001).values(member_row_count=270)
    )
    await session.flush()


async def _prepare_default_trial_forecast(
    session: AsyncSession,
    *,
    seed_policy: bool = True,
    policy_available_at: datetime = datetime(2026, 2, 1, tzinfo=UTC),
    policy_effective_from: date = date(2026, 1, 1),
) -> tuple[DefaultTrialApplicationService, TrialForecastCreateRequest, ActualHarvestActorContext]:
    await _seed_authorities(session)
    await _restrict_authorities_to_trial_scope(session)
    if seed_policy:
        await _seed_marketable_policy(
            session,
            public_hash="a" * 64,
            available_at=policy_available_at,
            effective_from=policy_effective_from,
            sorting_retention_rate=Decimal("1.000000"),
            postharvest_retention_rate=Decimal("1.000000"),
        )
    await session.execute(
        update(HarvestStateRun)
        .where(HarvestStateRun.id == 910001)
        .values(
            is_replay=True,
            forecast_effective_cutoff_at=datetime(2026, 2, 28, tzinfo=UTC),
            replay_executed_at=datetime(2026, 2, 28, 1, tzinfo=UTC),
            replay_code_version="a2-f-default-trial-fixture-v1",
            replay_run_correlation_id="a2-f-default-trial-fixture-910001",
        )
    )
    await CoreForecastRunRepository(session).register_code_authority(
        RegisterCoreForecastCodeAuthority(
            source_commit_sha="1" * 40,
            engine_code_hash="2" * 64,
            build_artifact_hash="3" * 64,
            config_bundle_hash="4" * 64,
            available_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    service = DefaultTrialApplicationService()
    actor = _forecast_actor("actor:postgres-default-trial")
    authority = await service.get_forecast_input_authority(session, actor)
    assert len(authority.items) == 1
    item = authority.items[0]
    request = TrialForecastCreateRequest(
        farm_business_key=item.farm_business_key,
        subfarm_business_key_or_null=item.subfarm_business_key_or_null,
        variety_business_key=item.variety_business_key,
        season_business_key=item.season_business_key,
        destination_factory_business_key=item.destination_factory_business_key,
        forecast_cutoff_at=datetime(2026, 2, 28, tzinfo=UTC),
        forecast_input_authority_hash=authority.forecast_input_authority_hash,
        plan_row_hash=item.plan_row_hash,
        planting_area_mu=item.planting_area_mu,
    )
    return service, request, actor


async def test_postgres_default_trial_service_create_replay_and_owner_readback(
    transactional_pg_session: AsyncSession,
) -> None:
    service, request, actor = await _prepare_default_trial_forecast(transactional_pg_session)
    created = await service.create_forecast(transactional_pg_session, request, actor)
    assert created.run_id == created.canonical_public_hash
    assert created.forecast_scope is not None
    assert created.forecast_scope.farm_business_key == request.farm_business_key
    assert (
        created.forecast_scope.subfarm_business_key_or_null == request.subfarm_business_key_or_null
    )
    assert created.forecast_scope.season_business_key == request.season_business_key
    assert created.forecast_scope.variety_business_key == request.variety_business_key
    assert (
        created.forecast_scope.destination_factory_business_key
        == request.destination_factory_business_key
    )

    counts = await _related_row_counts(transactional_pg_session, created.run_id)
    assert counts == (1, 1, 1)
    evidence = await authorize_and_load_forecast_evidence(
        transactional_pg_session,
        public_forecast_id=created.run_id,
        owner_identity=actor.identity,
    )
    assert evidence.business_scope_hash == compute_trial_business_scope_hash(
        farm_business_key=evidence.farm_business_key,
        subfarm_business_key_or_null=evidence.subfarm_business_key_or_null,
        season_business_key=evidence.season_business_key,
        variety_business_key=evidence.variety_business_key,
        destination_factory_business_key=evidence.destination_factory_business_key,
    )
    persisted = await CoreForecastRunRepository(transactional_pg_session).get_run_by_request_hash(
        created.run_id
    )
    assert persisted is not None
    persisted_p50 = next(
        item for item in persisted.metrics.metrics if item.forecast_quantile == "P50"
    )
    persisted_last_p50 = next(
        row for row in reversed(persisted.daily_curve.rows) if row.forecast_quantile == "P50"
    )
    assert created.single_day_peak.date == persisted_p50.single_day_peak.date
    assert created.single_day_peak.quantity_kg == Decimal(persisted_p50.single_day_peak.quantity_kg)
    assert created.single_day_peak.tie_break == persisted_p50.single_day_peak.tie_break
    assert (
        created.sustained_seven_day_peak.start_date == persisted_p50.sustained_7day_peak.start_date
    )
    assert created.sustained_seven_day_peak.end_date == persisted_p50.sustained_7day_peak.end_date
    assert created.sustained_seven_day_peak.cumulative_quantity_kg == Decimal(
        persisted_p50.sustained_7day_peak.cumulative_quantity_kg
    )
    assert created.sustained_seven_day_peak.daily_average_kg_per_day == Decimal(
        persisted_p50.sustained_7day_peak.daily_average_kg_per_day
    )
    assert (
        created.sustained_seven_day_peak.window_days
        == persisted_p50.sustained_7day_peak.window_days
    )
    assert created.sustained_seven_day_peak.metric == persisted_p50.sustained_7day_peak.metric
    assert (
        created.sustained_seven_day_peak.date_continuity
        == persisted_p50.sustained_7day_peak.date_continuity
    )
    assert created.sustained_seven_day_peak.tie_break == persisted_p50.sustained_7day_peak.tie_break
    assert created.mature_inventory_summary.opening_quantity_kg == Decimal(
        persisted_last_p50.opening_mature_inventory_kg
    )
    assert created.mature_inventory_summary.closing_quantity_kg == Decimal(
        persisted_last_p50.closing_mature_inventory_kg
    )
    assert created.backlog_summary.quantity_kg == Decimal(persisted_last_p50.unharvested_backlog_kg)
    assert created.policy_versions.forecast == persisted_last_p50.marketable_policy_version
    binding = await transactional_pg_session.scalar(
        select(TrialResourceBindingModel).where(
            TrialResourceBindingModel.resource_kind == "FORECAST",
            TrialResourceBindingModel.public_resource_id == created.run_id,
        )
    )
    assert binding is not None
    assert binding.owner_identity == actor.identity
    assert binding.business_scope_hash == evidence.business_scope_hash

    replay = await service.create_forecast(transactional_pg_session, request, actor)
    assert replay.model_dump(mode="json") == created.model_dump(mode="json")
    assert await _related_row_counts(transactional_pg_session, created.run_id) == (1, 1, 1)

    loaded = await service.get_forecast(transactional_pg_session, created.run_id, actor)
    assert loaded.model_dump(mode="json") == created.model_dump(mode="json")
    with pytest.raises(TrialApiError) as wrong_owner:
        await service.get_forecast(
            transactional_pg_session,
            created.run_id,
            _forecast_actor("actor:postgres-wrong-owner"),
        )
    assert wrong_owner.value.code is TrialApiErrorCode.RESOURCE_NOT_FOUND
    assert wrong_owner.value.status_code == 404
    with pytest.raises(TrialApiError) as conflicting_owner_replay:
        await service.create_forecast(
            transactional_pg_session,
            request,
            _forecast_actor("actor:postgres-conflicting-owner"),
        )
    assert conflicting_owner_replay.value.code is TrialApiErrorCode.CONFLICTING_REPLAY
    assert conflicting_owner_replay.value.status_code == 409
    assert await _related_row_counts(transactional_pg_session, created.run_id) == (1, 1, 1)


async def test_postgres_default_trial_service_historical_readback_is_stable(
    transactional_pg_session: AsyncSession,
) -> None:
    service, request, actor = await _prepare_default_trial_forecast(transactional_pg_session)
    created = await service.create_forecast(transactional_pg_session, request, actor)
    before_daily = await service.get_daily_curve(transactional_pg_session, created.run_id, actor)
    before_csv = await service.export_forecast(transactional_pg_session, created.run_id, actor)
    await transactional_pg_session.execute(
        update(FarmSeasonVarietyPlan)
        .where(FarmSeasonVarietyPlan.id == 3201)
        .values(planted_area_mu=Decimal("999.000000"), row_hash="f" * 64)
    )
    await transactional_pg_session.execute(
        update(CoreForecastMarketablePolicyModel)
        .where(CoreForecastMarketablePolicyModel.public_policy_hash == "a" * 64)
        .values(status="RETIRED")
    )
    await transactional_pg_session.flush()

    loaded = await service.get_forecast(transactional_pg_session, created.run_id, actor)
    after_daily = await service.get_daily_curve(transactional_pg_session, created.run_id, actor)
    after_csv = await service.export_forecast(transactional_pg_session, created.run_id, actor)
    assert loaded.forecast_scope == created.forecast_scope
    assert loaded.forecast_start_date == created.forecast_start_date
    assert loaded.forecast_end_date == created.forecast_end_date
    assert loaded.forecast_cutoff_at == created.forecast_cutoff_at
    assert loaded.forecast_input_authority_hash == created.forecast_input_authority_hash
    assert loaded.plan_row_hash == created.plan_row_hash
    assert loaded.planting_area_mu == created.planting_area_mu
    assert after_daily.model_dump(mode="json") == before_daily.model_dump(mode="json")
    assert after_csv.content == before_csv.content


async def test_postgres_default_trial_service_missing_policy_maps_public_error_and_writes_nothing(
    transactional_pg_session: AsyncSession,
) -> None:
    service, request, actor = await _prepare_default_trial_forecast(
        transactional_pg_session,
        policy_available_at=datetime(2026, 3, 1, tzinfo=UTC),
    )

    with pytest.raises(TrialApiError) as caught:
        await service.create_forecast(transactional_pg_session, request, actor)

    assert caught.value.status_code == 503
    assert caught.value.code is TrialApiErrorCode.MARKETABLE_RETENTION_POLICY_MISSING
    assert caught.value.retryable is True
    assert await _all_forecast_row_counts(transactional_pg_session) == (0, 0, 0)


async def test_postgres_default_trial_service_conflicting_policy_maps_error_and_writes_nothing(
    transactional_pg_session: AsyncSession,
) -> None:
    service, request, actor = await _prepare_default_trial_forecast(transactional_pg_session)
    await _seed_marketable_policy(transactional_pg_session, public_hash="b" * 64)

    with pytest.raises(TrialApiError) as caught:
        await service.create_forecast(transactional_pg_session, request, actor)

    assert caught.value.status_code == 409
    assert caught.value.code is TrialApiErrorCode.MARKETABLE_RETENTION_POLICY_CONFLICT
    assert caught.value.retryable is False
    assert await _all_forecast_row_counts(transactional_pg_session) == (0, 0, 0)


async def test_postgres_default_trial_service_csv_contract_is_stable_and_owner_scoped(
    transactional_pg_session: AsyncSession,
) -> None:
    service, request, actor = await _prepare_default_trial_forecast(transactional_pg_session)
    created = await service.create_forecast(transactional_pg_session, request, actor)
    loaded = await service.get_forecast(transactional_pg_session, created.run_id, actor)
    daily = await service.get_daily_curve(transactional_pg_session, created.run_id, actor)
    before_csv = await service.export_forecast(transactional_pg_session, created.run_id, actor)

    assert loaded.run_id == daily.run_id == created.run_id
    assert before_csv.filename == f"{created.run_id}.csv"
    rows = list(csv.reader(io.StringIO(before_csv.content.decode("utf-8"))))
    assert rows[0] == [
        "target_date",
        "p50_value_kg",
        "p80_value_kg",
        "p90_value_kg",
        "row_status",
    ]
    body_rows = rows[1:]
    dates = [row[0] for row in body_rows]
    assert dates == sorted(dates)
    assert len(dates) == len(set(dates)) == len(daily.rows)
    for row in body_rows:
        assert len(row) == 5
        assert all(re.fullmatch(r"\d+\.\d{6}", row[index]) for index in (1, 2, 3))
        assert row[4] == "COMPLETED"

    with pytest.raises(TrialApiError) as wrong_owner:
        await service.export_forecast(
            transactional_pg_session,
            created.run_id,
            _forecast_actor("actor:postgres-csv-wrong-owner"),
        )
    assert wrong_owner.value.code is TrialApiErrorCode.RESOURCE_NOT_FOUND
    assert wrong_owner.value.status_code == 404

    await transactional_pg_session.execute(
        update(FarmSeasonVarietyPlan)
        .where(FarmSeasonVarietyPlan.id == 3201)
        .values(planted_area_mu=Decimal("999.000000"), row_hash="f" * 64)
    )
    await transactional_pg_session.execute(
        update(CoreForecastMarketablePolicyModel)
        .where(CoreForecastMarketablePolicyModel.public_policy_hash == "a" * 64)
        .values(status="RETIRED")
    )
    await transactional_pg_session.flush()
    after_csv = await service.export_forecast(transactional_pg_session, created.run_id, actor)
    assert after_csv.filename == f"{daily.run_id}.csv"
    assert after_csv.content == before_csv.content


async def test_postgres_default_trial_service_nullable_subfarm_is_unsupported_before_writes(
    transactional_pg_session: AsyncSession,
) -> None:
    service, request, actor = await _prepare_default_trial_forecast(transactional_pg_session)
    unsupported = request.model_copy(update={"subfarm_business_key_or_null": None})
    with pytest.raises(TrialApiError) as caught:
        await service.create_forecast(transactional_pg_session, unsupported, actor)
    assert caught.value.code is TrialApiErrorCode.INPUT_NOT_SUPPORTED
    assert caught.value.status_code == 422
    assert await transactional_pg_session.scalar(select(func.count(CoreForecastRunModel.id))) == 0
    assert (
        await transactional_pg_session.scalar(select(func.count(TrialForecastEvidenceModel.id)))
        == 0
    )
    assert (
        await transactional_pg_session.scalar(select(func.count(TrialResourceBindingModel.id))) == 0
    )


async def test_postgres_default_trial_service_evidence_insert_failure_rolls_back_everything(
    transactional_pg_session: AsyncSession,
) -> None:
    service, request, actor = await _prepare_default_trial_forecast(transactional_pg_session)
    await _install_pg_evidence_insert_failure_trigger(transactional_pg_session)
    try:
        with pytest.raises(TrialApiError) as caught:
            await service.create_forecast(transactional_pg_session, request, actor)
        assert caught.value.code is TrialApiErrorCode.CONFLICTING_REPLAY
        assert (
            await transactional_pg_session.scalar(select(func.count(CoreForecastRunModel.id))) == 0
        )
        assert (
            await transactional_pg_session.scalar(select(func.count(TrialForecastEvidenceModel.id)))
            == 0
        )
        assert (
            await transactional_pg_session.scalar(select(func.count(TrialResourceBindingModel.id)))
            == 0
        )
    finally:
        await transactional_pg_session.execute(
            text(
                "DROP TRIGGER IF EXISTS test_trial_forecast_evidence_insert_failure_trigger "
                "ON trial_forecast_evidence"
            )
        )
        await transactional_pg_session.execute(
            text("DROP FUNCTION IF EXISTS test_trial_forecast_evidence_insert_failure()")
        )


async def test_postgres_default_trial_service_binding_insert_failure_rolls_back_everything(
    transactional_pg_session: AsyncSession,
) -> None:
    service, request, actor = await _prepare_default_trial_forecast(transactional_pg_session)
    await _install_pg_forecast_binding_insert_failure_trigger(transactional_pg_session)
    try:
        with pytest.raises(TrialApiError) as caught:
            await service.create_forecast(transactional_pg_session, request, actor)
        assert caught.value.code is TrialApiErrorCode.CONFLICTING_REPLAY
        assert (
            await transactional_pg_session.scalar(select(func.count(CoreForecastRunModel.id))) == 0
        )
        assert (
            await transactional_pg_session.scalar(select(func.count(TrialForecastEvidenceModel.id)))
            == 0
        )
        assert (
            await transactional_pg_session.scalar(select(func.count(TrialResourceBindingModel.id)))
            == 0
        )
    finally:
        await transactional_pg_session.execute(
            text(
                "DROP TRIGGER IF EXISTS test_trial_forecast_binding_insert_failure_trigger "
                "ON trial_resource_binding"
            )
        )
        await transactional_pg_session.execute(
            text("DROP FUNCTION IF EXISTS test_trial_forecast_binding_insert_failure()")
        )


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
        await _cleanup_s4_rows(request_hash or None)


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
        await _cleanup_s4_rows(request_hash)


async def test_postgres_concurrent_trial_forecast_evidence_exact_replay_is_single_row() -> None:
    request_hash = ""
    try:
        request_hash = await _persist_committed_core_run()
        barrier = asyncio.Barrier(2)
        evidence_input = _evidence_input(request_hash)

        async def create_once():
            async with AsyncSessionMaker() as session:
                async with session.begin():
                    await asyncio.wait_for(barrier.wait(), timeout=10)
                    return await create_forecast_evidence_and_binding_in_result_boundary(
                        session,
                        **evidence_input,
                    )

        results = await asyncio.wait_for(asyncio.gather(create_once(), create_once()), timeout=60)
        assert len(results) == 2
        assert results[0].public_forecast_id == request_hash
        assert results[0].forecast_evidence_hash == results[1].forecast_evidence_hash
        assert results[0].business_scope_hash == results[1].business_scope_hash
        assert results[0].canonical_payload == results[1].canonical_payload
        assert results[0].created_at == results[1].created_at

        async with AsyncSessionMaker() as verify:
            evidence_rows = (
                await verify.scalars(
                    select(TrialForecastEvidenceModel).where(
                        TrialForecastEvidenceModel.public_forecast_id == request_hash
                    )
                )
            ).all()
            binding_rows = (
                await verify.scalars(
                    select(TrialResourceBindingModel).where(
                        TrialResourceBindingModel.resource_kind == "FORECAST",
                        TrialResourceBindingModel.public_resource_id == request_hash,
                    )
                )
            ).all()
            assert len(evidence_rows) == 1
            assert len(binding_rows) == 1
            assert binding_rows[0].owner_identity == "actor:postgres-evidence"
            assert binding_rows[0].business_scope_hash == evidence_rows[0].business_scope_hash
            assert await _related_row_counts(verify, request_hash) == (1, 1, 1)
    finally:
        await _truncate_s4_rows_for_postgres_test()


async def test_postgres_concurrent_trial_forecast_evidence_conflict_is_single_winner() -> None:
    try:
        request_hash = await _persist_committed_core_run()
        barrier = asyncio.Barrier(2)

        async def create_once(owner_identity: str):
            async with AsyncSessionMaker() as session:
                async with session.begin():
                    await asyncio.wait_for(barrier.wait(), timeout=10)
                    try:
                        evidence = await create_forecast_evidence_and_binding_in_result_boundary(
                            session,
                            **_evidence_input(request_hash, owner_identity=owner_identity),
                        )
                    except TrialForecastEvidenceConflictError as exc:
                        return "conflict", owner_identity, exc
                    return "success", owner_identity, evidence

        results = await asyncio.wait_for(
            asyncio.gather(
                create_once("actor:postgres-conflict-a"),
                create_once("actor:postgres-conflict-b"),
            ),
            timeout=60,
        )
        assert [result[0] for result in results].count("success") == 1
        assert [result[0] for result in results].count("conflict") == 1
        successful_result = next(result for result in results if result[0] == "success")
        assert successful_result[2].public_forecast_id == request_hash

        async with AsyncSessionMaker() as verify:
            evidence_rows = (
                await verify.scalars(
                    select(TrialForecastEvidenceModel).where(
                        TrialForecastEvidenceModel.public_forecast_id == request_hash
                    )
                )
            ).all()
            binding_rows = (
                await verify.scalars(
                    select(TrialResourceBindingModel).where(
                        TrialResourceBindingModel.resource_kind == "FORECAST",
                        TrialResourceBindingModel.public_resource_id == request_hash,
                    )
                )
            ).all()
            assert len(evidence_rows) == 1
            assert len(binding_rows) == 1
            assert binding_rows[0].owner_identity in {
                "actor:postgres-conflict-a",
                "actor:postgres-conflict-b",
            }
            assert binding_rows[0].business_scope_hash == evidence_rows[0].business_scope_hash
            assert binding_rows[0].owner_identity == successful_result[1]
            assert await _related_row_counts(verify, request_hash) == (1, 1, 1)
    finally:
        await _truncate_s4_rows_for_postgres_test()


async def test_postgres_trial_forecast_evidence_insert_failure_rolls_back_outer_transaction(
    transactional_pg_session: AsyncSession,
) -> None:
    request_hash = await _persist_core_run(transactional_pg_session)
    try:
        await _install_pg_evidence_insert_failure_trigger(transactional_pg_session)
        with pytest.raises(TrialForecastEvidenceConflictError):
            await create_forecast_evidence_and_binding_in_result_boundary(
                transactional_pg_session,
                **_evidence_input(request_hash, owner_identity="actor:postgres-evidence-failure"),
            )
    finally:
        try:
            await transactional_pg_session.rollback()
        finally:
            await _cleanup_pg_failure_trigger(
                table_name="trial_forecast_evidence",
                trigger_name="test_trial_forecast_evidence_insert_failure_trigger",
                function_name="test_trial_forecast_evidence_insert_failure",
            )

    async with AsyncSessionMaker() as verify:
        assert await _related_row_counts(verify, request_hash) == (0, 0, 0)


async def test_postgres_trial_forecast_binding_insert_failure_rolls_back_outer_transaction(
    transactional_pg_session: AsyncSession,
) -> None:
    request_hash = await _persist_core_run(transactional_pg_session)
    try:
        await _install_pg_forecast_binding_insert_failure_trigger(transactional_pg_session)
        with pytest.raises(TrialForecastEvidenceConflictError):
            await create_forecast_evidence_and_binding_in_result_boundary(
                transactional_pg_session,
                **_evidence_input(request_hash, owner_identity="actor:postgres-binding-failure"),
            )
    finally:
        try:
            await transactional_pg_session.rollback()
        finally:
            await _cleanup_pg_failure_trigger(
                table_name="trial_resource_binding",
                trigger_name="test_trial_forecast_binding_insert_failure_trigger",
                function_name="test_trial_forecast_binding_insert_failure",
            )

    async with AsyncSessionMaker() as verify:
        assert await _related_row_counts(verify, request_hash) == (0, 0, 0)


async def test_postgres_trial_forecast_evidence_wrong_owner_is_concealed_not_found(
    transactional_pg_session: AsyncSession,
) -> None:
    request_hash = await _persist_core_run(transactional_pg_session)
    created = await create_forecast_evidence_and_binding_in_result_boundary(
        transactional_pg_session,
        **_evidence_input(request_hash, owner_identity="actor:postgres-owner"),
    )

    with pytest.raises(TrialForecastEvidenceNotFoundError):
        await authorize_and_load_forecast_evidence(
            transactional_pg_session,
            public_forecast_id=request_hash,
            owner_identity="actor:postgres-wrong-owner",
        )
    loaded = await authorize_and_load_forecast_evidence(
        transactional_pg_session,
        public_forecast_id=request_hash,
        owner_identity="actor:postgres-owner",
    )
    assert loaded == created
    row = await transactional_pg_session.scalar(
        select(TrialForecastEvidenceModel).where(
            TrialForecastEvidenceModel.public_forecast_id == request_hash
        )
    )
    assert row is not None
    assert row.forecast_evidence_hash == created.forecast_evidence_hash
    assert await _related_row_counts(transactional_pg_session, request_hash) == (1, 1, 1)


async def test_postgres_trial_forecast_evidence_only_half_state_fails_closed(
    transactional_pg_session: AsyncSession,
) -> None:
    request_hash = await _persist_core_run(transactional_pg_session)
    evidence_input = _evidence_input(request_hash, owner_identity="actor:postgres-half-evidence")
    created = await create_forecast_evidence_and_binding_in_result_boundary(
        transactional_pg_session,
        **evidence_input,
    )
    await transactional_pg_session.execute(
        delete(TrialResourceBindingModel).where(
            TrialResourceBindingModel.resource_kind == "FORECAST",
            TrialResourceBindingModel.public_resource_id == request_hash,
        )
    )
    await transactional_pg_session.flush()

    with pytest.raises(TrialForecastEvidenceIntegrityError):
        await create_forecast_evidence_and_binding_in_result_boundary(
            transactional_pg_session,
            **evidence_input,
        )
    with pytest.raises(TrialForecastEvidenceNotFoundError):
        await authorize_and_load_forecast_evidence(
            transactional_pg_session,
            public_forecast_id=request_hash,
            owner_identity="actor:postgres-half-evidence",
        )
    row = await transactional_pg_session.scalar(
        select(TrialForecastEvidenceModel).where(
            TrialForecastEvidenceModel.public_forecast_id == request_hash
        )
    )
    assert row is not None
    assert row.forecast_evidence_hash == created.forecast_evidence_hash
    assert await _related_row_counts(transactional_pg_session, request_hash) == (1, 1, 0)


async def test_postgres_trial_forecast_binding_only_half_state_fails_closed(
    transactional_pg_session: AsyncSession,
) -> None:
    request_hash = await _persist_core_run(transactional_pg_session)
    owner_identity = "actor:postgres-half-binding"
    scope_hash = compute_trial_business_scope_hash(
        farm_business_key="farm-postgres",
        subfarm_business_key_or_null="subfarm-postgres",
        season_business_key="season-2026",
        variety_business_key="variety-blue",
        destination_factory_business_key="factory-main",
    )
    transactional_pg_session.add(
        TrialResourceBindingModel(
            resource_kind="FORECAST",
            public_resource_id=request_hash,
            owner_identity=owner_identity,
            business_scope_hash=scope_hash,
            parent_forecast_public_id=None,
            parent_import_id=None,
        )
    )
    await transactional_pg_session.flush()
    evidence_input = _evidence_input(request_hash, owner_identity=owner_identity)

    with pytest.raises(TrialForecastEvidenceIntegrityError):
        await create_forecast_evidence_and_binding_in_result_boundary(
            transactional_pg_session,
            **evidence_input,
        )
    with pytest.raises(TrialForecastEvidenceIntegrityError):
        await authorize_and_load_forecast_evidence(
            transactional_pg_session,
            public_forecast_id=request_hash,
            owner_identity=owner_identity,
        )
    row = await transactional_pg_session.scalar(
        select(TrialResourceBindingModel).where(
            TrialResourceBindingModel.resource_kind == "FORECAST",
            TrialResourceBindingModel.public_resource_id == request_hash,
        )
    )
    assert row is not None
    assert row.owner_identity == owner_identity
    assert row.business_scope_hash == scope_hash
    assert await _related_row_counts(transactional_pg_session, request_hash) == (1, 0, 1)


async def test_postgres_trial_forecast_evidence_readback_is_stable_after_plan_change(
    transactional_pg_session: AsyncSession,
) -> None:
    request_hash = await _persist_core_run(transactional_pg_session)
    created = await create_forecast_evidence_and_binding_in_result_boundary(
        transactional_pg_session,
        **_evidence_input(request_hash, owner_identity="actor:postgres-stability"),
    )
    await transactional_pg_session.execute(
        update(FarmSeasonVarietyPlan)
        .where(FarmSeasonVarietyPlan.id == 3201)
        .values(planted_area_mu=Decimal("999.000000"), row_hash="f" * 64)
    )
    await transactional_pg_session.flush()
    changed_plan = await transactional_pg_session.scalar(
        select(FarmSeasonVarietyPlan).where(FarmSeasonVarietyPlan.id == 3201)
    )
    assert changed_plan is not None
    assert changed_plan.planted_area_mu == Decimal("999.000000")
    assert changed_plan.row_hash == "f" * 64

    loaded = await authorize_and_load_forecast_evidence(
        transactional_pg_session,
        public_forecast_id=request_hash,
        owner_identity="actor:postgres-stability",
    )
    assert loaded == created
    assert loaded.canonical_payload == created.canonical_payload
    assert loaded.forecast_evidence_hash == created.forecast_evidence_hash
    assert loaded.business_scope_hash == created.business_scope_hash
    assert loaded.plan_row_hash == "b" * 64
    assert loaded.planting_area_mu == Decimal("12.340000")
    row = await transactional_pg_session.scalar(
        select(TrialForecastEvidenceModel).where(
            TrialForecastEvidenceModel.public_forecast_id == request_hash
        )
    )
    assert row is not None
    assert row.plan_row_hash == "b" * 64
    assert row.forecast_evidence_hash == created.forecast_evidence_hash
    assert await _related_row_counts(transactional_pg_session, request_hash) == (1, 1, 1)


async def test_postgres_bare_default_catalog_produces_after_forecast_handoff(
    transactional_pg_session: AsyncSession,
) -> None:
    from unittest.mock import patch

    from backend.app.s3_daily_rowset import (
        s3_a2_coordinator_reviewed_live_origin_grain_identity_set as coord_identity_set,
    )
    from backend.app.s3_daily_rowset.catalog_artifact import (
        CatalogArtifactReasonCode,
        EvaluationInstanceCatalogArtifactProductionService,
    )
    from backend.app.s3_daily_rowset.forecast_artifact import IncumbentForecastArtifactAdapter
    from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_live_postgres_read import (
        clear_v0_2_live_postgres_session_provider,
    )
    from backend.tests.integration.s3_a2_pg_official_dataset_seed import (
        ReuseAsyncSessionMaker,
        seed_official_source_002_materialized_dataset,
    )
    from backend.tests.s3_daily_rowset.conftest import DATASET_IDENTITY

    coord_identity_set.uninstall_from_reviewed_set_loader()
    clear_v0_2_live_postgres_session_provider()
    await seed_official_source_002_materialized_dataset(transactional_pg_session)

    session_maker = ReuseAsyncSessionMaker(transactional_pg_session)
    with patch("backend.app.db.session.AsyncSessionMaker", session_maker):
        adapter = IncumbentForecastArtifactAdapter()
        assert adapter.has_versioned_artifact() is True
        resolved = adapter._resolved_artifact()
        assert resolved is not None
        assert resolved.content_identity_sha256 == (
            "06f45beb0c42be0ecf2750dede6783ca5f9a1e363d85ef3e26b0faccf14353f5"
        )
        assert len(resolved.rows) == 3

        produced = EvaluationInstanceCatalogArtifactProductionService(
            dataset_identity=DATASET_IDENTITY,
        ).produce()
    assert produced.reason_code is CatalogArtifactReasonCode.ARTIFACT_PRODUCED
    assert produced.catalog_identity_sha256 == (
        "00f6bc532dfd97f2d625fc1347bf2a7663299fda206bd472df4c2c32c54ab5af"
    )
    assert produced.catalog is not None
    assert len(produced.catalog.entries()) == 2427

    coord_identity_set.uninstall_from_reviewed_set_loader()
    clear_v0_2_live_postgres_session_provider()
