from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import JSON
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.harvest_state.persistence import save_harvest_state_output
from backend.app.harvest_state.service import run_harvest_state_model
from backend.app.models.analytics import AnalyticsBuildRun, FactReceiptDaily
from backend.app.models.harvest_state import (
    HarvestStateCohortTransitionRowModel,
    HarvestStateDailyMemberRowModel,
    HarvestStateDailyPoolRowModel,
    HarvestStateFutureArrivalRowModel,
    HarvestStateRun,
)
from backend.app.models.master_data import Factory, Holiday, Season, Variety
from backend.app.models.residual_model import (
    ResidualModelArtifact,
    ResidualModelManifestRow,
    ResidualModelMetric,
    ResidualModelPredictionRow,
    ResidualModelPredictionRun,
    ResidualModelTrainingRun,
)
from backend.app.residual_model.application import execute_residual_training
from backend.app.residual_model.config import load_residual_model_config
from backend.app.residual_model.schemas import FeatureValue, ResidualTrainingSampleSpec
from backend.app.residual_model.structural import aggregate_structural_arrivals
from backend.app.residual_model.training_manifest import (
    ResidualManifestBuildError,
    build_residual_training_manifest,
)
from backend.tests.harvest_state.conftest import make_request

TABLES = [
    Season.__table__,
    Holiday.__table__,
    Factory.__table__,
    Variety.__table__,
    AnalyticsBuildRun.__table__,
    FactReceiptDaily.__table__,
    HarvestStateRun.__table__,
    HarvestStateDailyPoolRowModel.__table__,
    HarvestStateDailyMemberRowModel.__table__,
    HarvestStateCohortTransitionRowModel.__table__,
    HarvestStateFutureArrivalRowModel.__table__,
    ResidualModelTrainingRun.__table__,
    ResidualModelManifestRow.__table__,
    ResidualModelArtifact.__table__,
    ResidualModelMetric.__table__,
    ResidualModelPredictionRun.__table__,
    ResidualModelPredictionRow.__table__,
]


@pytest.fixture
async def sqlite_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    AnalyticsBuildRun.__table__.c.config_snapshot.type = JSON()
    FactReceiptDaily.__table__.c.holiday_codes.type = JSON()
    FactReceiptDaily.__table__.c.holiday_codes.server_default = None
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Season.metadata.create_all(sync_conn, tables=TABLES)
        )
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sessionmaker() as session:
        yield session
    await engine.dispose()


async def _seed_master_data(session: AsyncSession) -> tuple[int, int, int]:
    season = Season(
        id=1,
        code="2025-2026",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 31),
    )
    factory = Factory(
        id=701,
        code="factory-a",
        name="Factory A",
        region_name="north",
        active=True,
    )
    variety = Variety(id=101, code="DX", name="Dx")
    session.add_all([season, factory, variety])
    await session.flush()
    return season.id, factory.id, variety.id


async def _persist_task9_run(session: AsyncSession) -> tuple[int, object]:
    output = run_harvest_state_model(make_request())
    assert output.status == "completed"
    run = await save_harvest_state_output(session, output=output)
    await session.commit()
    return run.id, output


async def _persist_blocked_task9_run(session: AsyncSession) -> int:
    payload = make_request()
    payload["farm_timezone"] = "Bad/Timezone"
    output = run_harvest_state_model(payload)
    assert output.status == "blocked"
    run = await save_harvest_state_output(session, output=output)
    await session.commit()
    return run.id


async def _seed_build_run(
    session: AsyncSession,
    *,
    build_run_id: int,
    season_id: int,
    source_max_raw_id: int,
    config_hash: str,
    finished_at: datetime,
) -> AnalyticsBuildRun:
    build = AnalyticsBuildRun(
        id=build_run_id,
        season_id=season_id,
        aggregation_version="task3-v1",
        source_max_raw_id=source_max_raw_id,
        config_hash=config_hash,
        config_snapshot={"version": "task3-v1"},
        status="completed",
        source_eligible_row_count=1,
        source_eligible_weight_kg=Decimal("1"),
        daily_fact_row_count=1,
        started_at=finished_at,
        finished_at=finished_at,
    )
    session.add(build)
    await session.flush()
    return build


async def _seed_daily_fact(
    session: AsyncSession,
    *,
    fact_id: int,
    build_run_id: int,
    season_id: int,
    factory_id: int,
    variety_id: int,
    receipt_date: date,
    weight_kg: Decimal,
) -> None:
    session.add(
        FactReceiptDaily(
            id=fact_id,
            build_run_id=build_run_id,
            season_id=season_id,
            receipt_date=receipt_date,
            factory_id=factory_id,
            farm_key="farm-a",
            subfarm_key="subfarm-a",
            variety_id=variety_id,
            weight_kg=weight_kg,
            source_row_count=1,
            holiday_codes=[],
            is_spring_festival=False,
        )
    )


def _supplemental_features(*, as_of_date: date) -> tuple[FeatureValue, ...]:
    cutoff = datetime.combine(as_of_date, datetime.max.time(), tzinfo=UTC)
    return (
        FeatureValue.model_validate(
            {
                "feature_name": "weather_7d_rainfall",
                "value": Decimal("12.5"),
                "known_at": cutoff,
                "source_ref": {"weather_run": 1},
                "source_version": "task7-v1",
                "source_available_at": cutoff,
                "observation_date": as_of_date,
            }
        ),
        FeatureValue.model_validate(
            {
                "feature_name": "weather_7d_gdd",
                "value": Decimal("33.0"),
                "known_at": cutoff,
                "source_ref": {"weather_run": 1},
                "source_version": "task7-v1",
                "source_available_at": cutoff,
                "observation_date": as_of_date,
            }
        ),
    )


def _snapshot_as_of_date(output: object) -> date:
    raw = output.input_snapshot["as_of_date"]
    return raw if isinstance(raw, date) else date.fromisoformat(raw)


def _config():
    return load_residual_model_config(
        Path("/Users/charles/Documents/智能agent开发/configs/residual_model.yaml")
    )


@pytest.mark.asyncio
async def test_build_training_manifest_uses_explicit_label_and_feature_build_runs(
    sqlite_session: AsyncSession,
) -> None:
    season_id, factory_id, variety_id = await _seed_master_data(sqlite_session)
    task9_run_id, output = await _persist_task9_run(sqlite_session)
    structural_rows = aggregate_structural_arrivals(output)
    as_of_date = _snapshot_as_of_date(output)
    label_build = await _seed_build_run(
        sqlite_session,
        build_run_id=1,
        season_id=season_id,
        source_max_raw_id=100,
        config_hash="a" * 64,
        finished_at=datetime(2026, 3, 20, tzinfo=UTC),
    )
    feature_build = await _seed_build_run(
        sqlite_session,
        build_run_id=2,
        season_id=season_id,
        source_max_raw_id=50,
        config_hash="b" * 64,
        finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
    )
    target_date = structural_rows[0]["arrival_local_date"]
    await _seed_daily_fact(
        sqlite_session,
        fact_id=1,
        build_run_id=label_build.id,
        season_id=season_id,
        factory_id=factory_id,
        variety_id=variety_id,
        receipt_date=target_date,
        weight_kg=Decimal("140"),
    )
    await _seed_daily_fact(
        sqlite_session,
        fact_id=2,
        build_run_id=feature_build.id,
        season_id=season_id,
        factory_id=factory_id,
        variety_id=variety_id,
        receipt_date=as_of_date - timedelta(days=1),
        weight_kg=Decimal("11"),
    )
    await _seed_daily_fact(
        sqlite_session,
        fact_id=3,
        build_run_id=feature_build.id,
        season_id=season_id,
        factory_id=factory_id,
        variety_id=variety_id,
        receipt_date=as_of_date - timedelta(days=3),
        weight_kg=Decimal("13"),
    )
    await _seed_daily_fact(
        sqlite_session,
        fact_id=4,
        build_run_id=feature_build.id,
        season_id=season_id,
        factory_id=factory_id,
        variety_id=variety_id,
        receipt_date=as_of_date - timedelta(days=7),
        weight_kg=Decimal("17"),
    )
    await sqlite_session.commit()

    rows = await build_residual_training_manifest(
        sqlite_session,
        samples=[
            ResidualTrainingSampleSpec(
                task9_run_id=task9_run_id,
                label_analytics_build_run_id=label_build.id,
                feature_analytics_build_run_id=feature_build.id,
                split="train",
                supplemental_feature_values=_supplemental_features(as_of_date=as_of_date),
            )
        ],
    )

    assert len(rows) == len(structural_rows)
    first = rows[0]
    assert first.label_actual_snapshot.build_run_id == label_build.id
    assert first.feature_actual_snapshot.build_run_id == feature_build.id
    assert first.observed_effective_receipt_kg == Decimal("140")
    features = {item.feature_name: item.value for item in first.feature_values}
    assert features["actual_receipt_lag_1d_kg"] == Decimal("11")
    assert features["actual_receipt_lag_3d_kg"] == Decimal("13")
    assert features["actual_receipt_lag_7d_kg"] == Decimal("17")
    assert features["weather_7d_rainfall"] == Decimal("12.5")
    assert first.feature_visibility_audit is not None
    assert first.feature_visibility_audit.status == "completed"


@pytest.mark.asyncio
async def test_later_build_does_not_override_explicit_feature_build_for_as_of_features(
    sqlite_session: AsyncSession,
) -> None:
    season_id, factory_id, variety_id = await _seed_master_data(sqlite_session)
    task9_run_id, output = await _persist_task9_run(sqlite_session)
    as_of_date = _snapshot_as_of_date(output)
    label_build = await _seed_build_run(
        sqlite_session,
        build_run_id=1,
        season_id=season_id,
        source_max_raw_id=100,
        config_hash="a" * 64,
        finished_at=datetime(2026, 3, 20, tzinfo=UTC),
    )
    early_feature_build = await _seed_build_run(
        sqlite_session,
        build_run_id=2,
        season_id=season_id,
        source_max_raw_id=50,
        config_hash="b" * 64,
        finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
    )
    later_feature_build = await _seed_build_run(
        sqlite_session,
        build_run_id=3,
        season_id=season_id,
        source_max_raw_id=60,
        config_hash="c" * 64,
        finished_at=datetime(2026, 3, 5, 12, 0, tzinfo=UTC),
    )
    for build_run_id, lag_value in (
        (early_feature_build.id, Decimal("11")),
        (later_feature_build.id, Decimal("999")),
    ):
            await _seed_daily_fact(
                sqlite_session,
                fact_id=(build_run_id * 10) + 1,
                build_run_id=build_run_id,
            season_id=season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=as_of_date - timedelta(days=1),
            weight_kg=lag_value,
        )
            await _seed_daily_fact(
                sqlite_session,
                fact_id=(build_run_id * 10) + 2,
                build_run_id=build_run_id,
            season_id=season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=as_of_date - timedelta(days=3),
            weight_kg=lag_value,
        )
            await _seed_daily_fact(
                sqlite_session,
                fact_id=(build_run_id * 10) + 3,
                build_run_id=build_run_id,
            season_id=season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=as_of_date - timedelta(days=7),
            weight_kg=lag_value,
        )
    await sqlite_session.commit()

    rows = await build_residual_training_manifest(
        sqlite_session,
        samples=[
            ResidualTrainingSampleSpec(
                task9_run_id=task9_run_id,
                label_analytics_build_run_id=label_build.id,
                feature_analytics_build_run_id=early_feature_build.id,
                split="train",
                supplemental_feature_values=_supplemental_features(as_of_date=as_of_date),
            )
        ],
    )
    features = {item.feature_name: item.value for item in rows[0].feature_values}
    assert features["actual_receipt_lag_1d_kg"] == Decimal("11")


@pytest.mark.asyncio
async def test_zero_receipt_and_missing_fact_are_distinguished(
    sqlite_session: AsyncSession,
) -> None:
    season_id, factory_id, variety_id = await _seed_master_data(sqlite_session)
    task9_run_id, output = await _persist_task9_run(sqlite_session)
    as_of_date = _snapshot_as_of_date(output)
    label_build = await _seed_build_run(
        sqlite_session,
        build_run_id=1,
        season_id=season_id,
        source_max_raw_id=100,
        config_hash="a" * 64,
        finished_at=datetime(2026, 3, 20, tzinfo=UTC),
    )
    covered_feature_build = await _seed_build_run(
        sqlite_session,
        build_run_id=2,
        season_id=season_id,
        source_max_raw_id=50,
        config_hash="b" * 64,
        finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
    )
    missing_feature_build = await _seed_build_run(
        sqlite_session,
        build_run_id=3,
        season_id=season_id,
        source_max_raw_id=51,
        config_hash="c" * 64,
        finished_at=datetime(2026, 2, 28, 13, 0, tzinfo=UTC),
    )
    await _seed_daily_fact(
        sqlite_session,
        fact_id=1,
        build_run_id=covered_feature_build.id,
        season_id=season_id,
        factory_id=factory_id,
        variety_id=variety_id,
        receipt_date=as_of_date - timedelta(days=3),
        weight_kg=Decimal("9"),
    )
    await _seed_daily_fact(
        sqlite_session,
        fact_id=2,
        build_run_id=covered_feature_build.id,
        season_id=season_id,
        factory_id=factory_id,
        variety_id=variety_id,
        receipt_date=as_of_date - timedelta(days=7),
        weight_kg=Decimal("7"),
    )
    await _seed_daily_fact(
        sqlite_session,
        fact_id=3,
        build_run_id=label_build.id,
        season_id=season_id,
        factory_id=factory_id,
        variety_id=variety_id,
        receipt_date=output.forecast_start_date,
        weight_kg=Decimal("100"),
    )
    await sqlite_session.commit()

    rows = await build_residual_training_manifest(
        sqlite_session,
        samples=[
            ResidualTrainingSampleSpec(
                task9_run_id=task9_run_id,
                label_analytics_build_run_id=label_build.id,
                feature_analytics_build_run_id=covered_feature_build.id,
                split="train",
                supplemental_feature_values=_supplemental_features(as_of_date=as_of_date),
            ),
            ResidualTrainingSampleSpec(
                task9_run_id=task9_run_id,
                label_analytics_build_run_id=label_build.id,
                feature_analytics_build_run_id=missing_feature_build.id,
                split="train",
                supplemental_feature_values=_supplemental_features(as_of_date=as_of_date),
            ),
        ],
    )

    included_rows = [
        row
        for row in rows
        if row.feature_actual_snapshot.build_run_id == covered_feature_build.id
    ]
    excluded_rows = [
        row
        for row in rows
        if row.feature_actual_snapshot.build_run_id == missing_feature_build.id
    ]
    assert included_rows
    included_features = {item.feature_name: item.value for item in included_rows[0].feature_values}
    assert included_features["actual_receipt_lag_1d_kg"] == Decimal("0")
    assert excluded_rows
    assert all(row.include is False for row in excluded_rows)
    assert all(row.exclusion_reason == "factory_missing_from_build_run" for row in excluded_rows)


@pytest.mark.asyncio
async def test_task9_completed_only_is_required(sqlite_session: AsyncSession) -> None:
    season_id, _, _ = await _seed_master_data(sqlite_session)
    blocked_run_id = await _persist_blocked_task9_run(sqlite_session)
    label_build = await _seed_build_run(
        sqlite_session,
        build_run_id=1,
        season_id=season_id,
        source_max_raw_id=100,
        config_hash="a" * 64,
        finished_at=datetime(2026, 3, 20, tzinfo=UTC),
    )
    feature_build = await _seed_build_run(
        sqlite_session,
        build_run_id=2,
        season_id=season_id,
        source_max_raw_id=50,
        config_hash="b" * 64,
        finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
    )
    await sqlite_session.commit()

    with pytest.raises(ResidualManifestBuildError):
        await build_residual_training_manifest(
            sqlite_session,
            samples=[
                ResidualTrainingSampleSpec(
                    task9_run_id=blocked_run_id,
                    label_analytics_build_run_id=label_build.id,
                    feature_analytics_build_run_id=feature_build.id,
                    split="train",
        )
            ],
        )


@pytest.mark.asyncio
async def test_execute_residual_training_persists_and_reloads(sqlite_session: AsyncSession) -> None:
    season_id, factory_id, variety_id = await _seed_master_data(sqlite_session)
    task9_run_id, output = await _persist_task9_run(sqlite_session)
    as_of_date = _snapshot_as_of_date(output)
    label_build = await _seed_build_run(
        sqlite_session,
        build_run_id=1,
        season_id=season_id,
        source_max_raw_id=100,
        config_hash="a" * 64,
        finished_at=datetime(2026, 3, 20, tzinfo=UTC),
    )
    feature_build = await _seed_build_run(
        sqlite_session,
        build_run_id=2,
        season_id=season_id,
        source_max_raw_id=50,
        config_hash="b" * 64,
        finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
    )
    for index, target_date in enumerate((date(2026, 3, 1), date(2026, 3, 2), date(2026, 3, 3))):
        await _seed_daily_fact(
            sqlite_session,
            fact_id=100 + index,
            build_run_id=label_build.id,
            season_id=season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=target_date,
            weight_kg=Decimal("100") + Decimal(index),
        )
    for offset, weight in ((1, Decimal("11")), (3, Decimal("13")), (7, Decimal("17"))):
        await _seed_daily_fact(
            sqlite_session,
            fact_id=200 + offset,
            build_run_id=feature_build.id,
            season_id=season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=as_of_date - timedelta(days=offset),
            weight_kg=weight,
        )
    await sqlite_session.commit()

    loaded, run_id = await execute_residual_training(
        sqlite_session,
        samples=[
            ResidualTrainingSampleSpec(
                task9_run_id=task9_run_id,
                label_analytics_build_run_id=label_build.id,
                feature_analytics_build_run_id=feature_build.id,
                split="train",
                supplemental_feature_values=_supplemental_features(as_of_date=as_of_date),
            )
        ]
        * 30,
        config=_config(),
    )

    assert run_id > 0
    assert loaded.execution_status == "completed"
    assert loaded.training_signature


@pytest.mark.asyncio
async def test_execute_residual_training_reuses_existing_signature(
    sqlite_session: AsyncSession,
) -> None:
    season_id, factory_id, variety_id = await _seed_master_data(sqlite_session)
    task9_run_id, output = await _persist_task9_run(sqlite_session)
    as_of_date = _snapshot_as_of_date(output)
    label_build = await _seed_build_run(
        sqlite_session,
        build_run_id=1,
        season_id=season_id,
        source_max_raw_id=100,
        config_hash="a" * 64,
        finished_at=datetime(2026, 3, 20, tzinfo=UTC),
    )
    feature_build = await _seed_build_run(
        sqlite_session,
        build_run_id=2,
        season_id=season_id,
        source_max_raw_id=50,
        config_hash="b" * 64,
        finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
    )
    await _seed_daily_fact(
        sqlite_session,
        fact_id=1,
        build_run_id=label_build.id,
        season_id=season_id,
        factory_id=factory_id,
        variety_id=variety_id,
        receipt_date=output.forecast_start_date,
        weight_kg=Decimal("100"),
    )
    for offset, fact_id in ((1, 2), (3, 3), (7, 4)):
        await _seed_daily_fact(
            sqlite_session,
            fact_id=fact_id,
            build_run_id=feature_build.id,
            season_id=season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=as_of_date - timedelta(days=offset),
            weight_kg=Decimal("10") + Decimal(offset),
        )
    await sqlite_session.commit()
    samples = [
        ResidualTrainingSampleSpec(
            task9_run_id=task9_run_id,
            label_analytics_build_run_id=label_build.id,
            feature_analytics_build_run_id=feature_build.id,
            split="train",
            supplemental_feature_values=_supplemental_features(as_of_date=as_of_date),
        )
    ]

    _, first_run_id = await execute_residual_training(
        sqlite_session,
        samples=samples,
        config=_config(),
    )
    _, second_run_id = await execute_residual_training(
        sqlite_session,
        samples=samples,
        config=_config(),
    )

    assert first_run_id == second_run_id
