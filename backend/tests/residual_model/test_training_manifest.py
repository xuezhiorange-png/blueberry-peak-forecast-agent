from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest
from sqlalchemy import JSON, Integer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.analytics.config import load_analytics_config
from backend.app.analytics.daily_facts import build_daily_facts_for_season
from backend.app.analytics.peak_metrics import build_analysis_calendar
from backend.app.harvest_state.persistence import save_harvest_state_output
from backend.app.harvest_state.service import run_harvest_state_model
from backend.app.models.analytics import (
    AnalyticsBuildRun,
    FactorySeasonPeakMetric,
    FactReceiptDaily,
)
from backend.app.models.harvest_state import (
    HarvestStateCohortTransitionRowModel,
    HarvestStateDailyMemberRowModel,
    HarvestStateDailyPoolRowModel,
    HarvestStateFutureArrivalRowModel,
    HarvestStateRun,
)
from backend.app.models.historical_import import FactReceiptRaw, IngestFile
from backend.app.models.master_data import Factory, Grade, Holiday, Season, Variety
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
from backend.tests.residual_model.support import repo_root, residual_model_config_path

TABLES = [
    Season.__table__,
    Holiday.__table__,
    Factory.__table__,
    Variety.__table__,
    Grade.__table__,
    IngestFile.__table__,
    FactReceiptRaw.__table__,
    AnalyticsBuildRun.__table__,
    FactReceiptDaily.__table__,
    FactorySeasonPeakMetric.__table__,
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
    AnalyticsBuildRun.__table__.c.id.type = Integer()
    FactorySeasonPeakMetric.__table__.c.id.type = Integer()
    FactReceiptDaily.__table__.c.id.type = Integer()
    IngestFile.__table__.c.id.type = Integer()
    FactReceiptRaw.__table__.c.id.type = Integer()
    AnalyticsBuildRun.__table__.c.config_snapshot.type = JSON()
    FactReceiptDaily.__table__.c.holiday_codes.type = JSON()
    FactReceiptDaily.__table__.c.holiday_codes.server_default = None
    IngestFile.__table__.c.config_snapshot.type = JSON()
    IngestFile.__table__.c.quality_report.type = JSON()
    FactReceiptRaw.__table__.c.raw_payload.type = JSON()
    FactReceiptRaw.__table__.c.exclusion_reasons.type = JSON()
    FactReceiptRaw.__table__.c.parse_errors.type = JSON()
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
    grade = Grade(id=301, code="优果", is_analysis_eligible_default=True)
    session.add_all([season, factory, variety, grade])
    await session.flush()
    return season.id, factory.id, variety.id


async def _seed_season(
    session: AsyncSession,
    *,
    season_id: int,
    code: str,
    start_date: date,
    end_date: date,
) -> int:
    season = Season(
        id=season_id,
        code=code,
        start_date=start_date,
        end_date=end_date,
    )
    session.add(season)
    await session.flush()
    return season.id


async def _persist_task9_run(
    session: AsyncSession,
    *,
    payload: dict[str, Any] | None = None,
    payload_overrides: dict[str, object] | None = None,
) -> tuple[int, object]:
    payload = payload.copy() if payload is not None else make_request()
    if payload_overrides:
        payload.update(payload_overrides)
    output = run_harvest_state_model(payload)
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
    config_snapshot: dict[str, object] | None = None,
    covered_factory_ids: tuple[int, ...] = (),
    analysis_start_date: date | None = None,
    analysis_end_date: date | None = None,
) -> AnalyticsBuildRun:
    build = AnalyticsBuildRun(
        id=build_run_id,
        season_id=season_id,
        aggregation_version="task3-v1",
        source_max_raw_id=source_max_raw_id,
        config_hash=config_hash,
        config_snapshot=config_snapshot
        or {
            "version": "task3-v1",
            "analysis_months": [1, 2, 3, 4],
        },
        status="completed",
        source_eligible_row_count=1,
        source_eligible_weight_kg=Decimal("1"),
        daily_fact_row_count=1,
        started_at=finished_at,
        finished_at=finished_at,
    )
    session.add(build)
    await session.flush()
    if covered_factory_ids:
        season = await session.get(Season, season_id)
        assert season is not None
        analysis_start = analysis_start_date or season.start_date
        analysis_end = analysis_end_date or min(season.end_date, finished_at.date())
        analysis_months = tuple(cast(list[int], build.config_snapshot["analysis_months"]))
        calendar_day_count = len(
            build_analysis_calendar(
                start_date=analysis_start,
                end_date=analysis_end,
                analysis_months=analysis_months,
            )
        )
        for index, factory_id in enumerate(covered_factory_ids, start=1):
            session.add(
                FactorySeasonPeakMetric(
                    id=build_run_id * 1000 + index,
                    build_run_id=build.id,
                    season_id=season_id,
                    factory_id=factory_id,
                    analysis_start_date=analysis_start,
                    analysis_end_date=analysis_end,
                    calendar_day_count=calendar_day_count,
                    observed_day_count=0,
                    total_weight_kg=Decimal("1"),
                    single_day_peak_kg=Decimal("1"),
                    single_day_peak_date=analysis_start,
                    stable_median_3d_peak_kg=Decimal("1"),
                    stable_median_3d_peak_date=analysis_start,
                    mean_3d_peak_kg=Decimal("1"),
                    mean_3d_peak_date=analysis_start,
                    peak_concentration=Decimal("0"),
                    variety_hhi=Decimal("0"),
                    farm_hhi=Decimal("0"),
                    subfarm_hhi=Decimal("0"),
                    unknown_farm_weight_share=Decimal("0"),
                    unknown_subfarm_weight_share=Decimal("0"),
                    spring_festival_day_count=0,
                    computed_at=finished_at,
                )
            )
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
    farm_key: str = "farm-a",
    subfarm_key: str = "subfarm-a",
) -> None:
    session.add(
        FactReceiptDaily(
            id=fact_id,
            build_run_id=build_run_id,
            season_id=season_id,
            receipt_date=receipt_date,
            factory_id=factory_id,
            farm_key=farm_key,
            subfarm_key=subfarm_key,
            variety_id=variety_id,
            weight_kg=weight_kg,
            source_row_count=1,
            holiday_codes=[],
            is_spring_festival=False,
        )
    )


async def _create_ingest_file(
    session: AsyncSession,
    *,
    ingest_file_id: int,
    season_id: int,
    file_sha256: str,
) -> int:
    ingest = IngestFile(
        id=ingest_file_id,
        file_name=f"{file_sha256}.xls",
        source_path=f"{file_sha256}.xls",
        file_sha256=file_sha256,
        season_id=season_id,
        status="completed",
        sheet_count=1,
        row_count=1,
        inserted_row_count=1,
        suspected_duplicate_count=0,
        config_hash="import-hash",
        config_snapshot={"version": "task2"},
        quality_report={},
    )
    session.add(ingest)
    await session.flush()
    return ingest.id


async def _insert_raw_rows(
    session: AsyncSession,
    *,
    ingest_file_id: int,
    season_id: int,
    factory_id: int,
    variety_id: int,
    rows: list[dict[str, object]],
) -> None:
    for offset, row in enumerate(rows, start=1):
        session.add(
            FactReceiptRaw(
                id=ingest_file_id * 1000 + offset,
                ingest_file_id=ingest_file_id,
                season_id=season_id,
                source_sheet="SheetA",
                source_row_number=offset,
                raw_payload={},
                receipt_date_raw=str(row["receipt_date"]),
                link_name_raw=None,
                farm_raw=cast(str | None, row.get("farm_raw")),
                subfarm_raw=cast(str | None, row.get("subfarm_raw")),
                variety_raw="Dx",
                grade_raw="优果",
                weight_kg_raw=str(row["weight_kg"]),
                factory_raw="Factory A",
                receipt_date=cast(date, row["receipt_date"]),
                weight_kg=cast(Decimal, row["weight_kg"]),
                factory_normalized="Factory A",
                variety_normalized="Dx",
                factory_id=factory_id,
                variety_id=variety_id,
                grade_id=301,
                is_date_valid=True,
                is_weight_valid=True,
                is_factory_known=True,
                is_variety_known=True,
                is_suspected_duplicate=False,
                is_analysis_eligible=bool(row.get("eligible", True)),
                exclusion_reasons=[],
                parse_errors=[],
                source_row_fingerprint=f"raw-{ingest_file_id}-{offset}",
                business_fingerprint=f"biz-{season_id}-{ingest_file_id}-{offset}",
            )
        )


def _supplemental_features(
    *,
    as_of_date: date,
    destination_factory_category: str | None = None,
    weather_7d_rainfall: Decimal = Decimal("12.5"),
    weather_7d_gdd: Decimal = Decimal("33.0"),
) -> tuple[FeatureValue, ...]:
    cutoff = datetime.combine(as_of_date, datetime.max.time(), tzinfo=UTC)
    values = [
        FeatureValue.model_validate(
            {
                "feature_name": "weather_7d_rainfall",
                "value": weather_7d_rainfall,
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
                "value": weather_7d_gdd,
                "known_at": cutoff,
                "source_ref": {"weather_run": 1},
                "source_version": "task7-v1",
                "source_available_at": cutoff,
                "observation_date": as_of_date,
            }
        ),
    ]
    if destination_factory_category is not None:
        values.append(
            FeatureValue.model_validate(
                {
                    "feature_name": "destination_factory_category",
                    "value": destination_factory_category,
                    "known_at": cutoff,
                    "source_ref": {
                        "master_data_snapshot_version": "task10-master-data-v1",
                        "category_hash": "f" * 64,
                    },
                    "source_version": "task10-master-data-v1",
                    "source_available_at": cutoff,
                }
            )
        )
    return tuple(values)


def _diverse_training_samples(
    *,
    task9_run_id: int,
    label_build_run_id: int,
    feature_build_run_id: int,
    as_of_date: date,
    validation_task9_run_id: int | None = None,
    validation_label_build_run_id: int | None = None,
    validation_feature_build_run_id: int | None = None,
    count: int = 30,
    train_category_prefix: str = "snapshot",
    validation_category_prefix: str | None = None,
) -> list[ResidualTrainingSampleSpec]:
    resolved_validation_category_prefix = (
        validation_category_prefix
        if validation_category_prefix is not None
        else train_category_prefix
    )
    train_count = max(count - 6, 1)
    validation_count = count - train_count
    samples: list[ResidualTrainingSampleSpec] = []
    for index in range(train_count):
        samples.append(
            ResidualTrainingSampleSpec(
                task9_run_id=task9_run_id,
                label_analytics_build_run_id=label_build_run_id,
                feature_analytics_build_run_id=feature_build_run_id,
                split="train",
                supplemental_feature_values=_supplemental_features(
                    as_of_date=as_of_date,
                    destination_factory_category=f"{train_category_prefix}-{index % 3}",
                    weather_7d_rainfall=Decimal("12.5") + Decimal(index % 5),
                    weather_7d_gdd=Decimal("33.0") + Decimal(index % 7),
                ),
            )
        )
    for index in range(validation_count):
        samples.append(
            ResidualTrainingSampleSpec(
                task9_run_id=validation_task9_run_id or task9_run_id,
                label_analytics_build_run_id=validation_label_build_run_id
                or (label_build_run_id + 100),
                feature_analytics_build_run_id=validation_feature_build_run_id
                or (feature_build_run_id + 100),
                split="validation",
                supplemental_feature_values=_supplemental_features(
                    as_of_date=as_of_date,
                    destination_factory_category=(
                        f"{resolved_validation_category_prefix}-{index % 2}"
                    ),
                    weather_7d_rainfall=Decimal("22.5") + Decimal(index % 3),
                    weather_7d_gdd=Decimal("43.0") + Decimal(index % 5),
                ),
            )
        )
    return samples


def _snapshot_as_of_date(output: object) -> date:
    raw = output.input_snapshot["as_of_date"]
    return raw if isinstance(raw, date) else date.fromisoformat(raw)


def _config():
    return load_residual_model_config(residual_model_config_path())


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
        covered_factory_ids=(factory_id,),
    )
    covered_feature_build = await _seed_build_run(
        sqlite_session,
        build_run_id=2,
        season_id=season_id,
        source_max_raw_id=50,
        config_hash="b" * 64,
        finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
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
async def test_fact_rows_are_aggregated_per_factory_date_and_prior_day_windows_are_strict(
    sqlite_session: AsyncSession,
) -> None:
    season_id, factory_id, variety_id = await _seed_master_data(sqlite_session)
    task9_run_id, output = await _persist_task9_run(sqlite_session)
    structural_rows = aggregate_structural_arrivals(output)
    as_of_date = _snapshot_as_of_date(output)
    label_build = await _seed_build_run(
        sqlite_session,
        build_run_id=11,
        season_id=season_id,
        source_max_raw_id=100,
        config_hash="1" * 64,
        finished_at=datetime(2026, 3, 20, tzinfo=UTC),
    )
    feature_build = await _seed_build_run(
        sqlite_session,
        build_run_id=12,
        season_id=season_id,
        source_max_raw_id=80,
        config_hash="2" * 64,
        finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
    )
    target_date = structural_rows[0]["arrival_local_date"]
    await _seed_daily_fact(
        sqlite_session,
        fact_id=101,
        build_run_id=label_build.id,
        season_id=season_id,
        factory_id=factory_id,
        variety_id=variety_id,
        receipt_date=target_date,
        weight_kg=Decimal("90"),
        farm_key="farm-a",
        subfarm_key="subfarm-a",
    )
    await _seed_daily_fact(
        sqlite_session,
        fact_id=102,
        build_run_id=label_build.id,
        season_id=season_id,
        factory_id=factory_id,
        variety_id=variety_id,
        receipt_date=target_date,
        weight_kg=Decimal("50"),
        farm_key="farm-b",
        subfarm_key="subfarm-b",
    )
    await _seed_daily_fact(
        sqlite_session,
        fact_id=201,
        build_run_id=feature_build.id,
        season_id=season_id,
        factory_id=factory_id,
        variety_id=variety_id,
        receipt_date=as_of_date,
        weight_kg=Decimal("500"),
        farm_key="farm-a",
        subfarm_key="subfarm-a",
    )
    for fact_id, offset, weight, farm_key, subfarm_key in (
        (202, 1, Decimal("10"), "farm-a", "subfarm-a"),
        (203, 1, Decimal("2"), "farm-b", "subfarm-b"),
        (204, 2, Decimal("6"), "farm-c", "subfarm-c"),
        (205, 3, Decimal("9"), "farm-a", "subfarm-a"),
        (206, 3, Decimal("4"), "farm-b", "subfarm-b"),
        (207, 7, Decimal("15"), "farm-a", "subfarm-a"),
        (208, 7, Decimal("2"), "farm-b", "subfarm-b"),
    ):
        await _seed_daily_fact(
            sqlite_session,
            fact_id=fact_id,
            build_run_id=feature_build.id,
            season_id=season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=as_of_date - timedelta(days=offset),
            weight_kg=weight,
            farm_key=farm_key,
            subfarm_key=subfarm_key,
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

    first = rows[0]
    features = {item.feature_name: item.value for item in first.feature_values}
    assert first.observed_effective_receipt_kg == Decimal("140")
    assert features["actual_receipt_lag_1d_kg"] == Decimal("12")
    assert features["actual_receipt_lag_3d_kg"] == Decimal("13")
    assert features["actual_receipt_lag_7d_kg"] == Decimal("17")
    assert features["actual_receipt_rolling_3d_mean_kg"] == Decimal("10.33333333333333333333333333")
    assert features["actual_receipt_rolling_7d_mean_kg"] == Decimal("6.857142857142857142857142857")
    assert features["actual_receipt_cumulative_to_as_of_kg"] == Decimal("48")
    assert features["realized_cumulative_residual_to_as_of_kg"] == Decimal("48") - Decimal(
        features["structural_cumulative_to_as_of_kg"]
    )


@pytest.mark.asyncio
async def test_uncovered_prior_day_receipt_does_not_silently_zero_fill(
    sqlite_session: AsyncSession,
) -> None:
    season_id, factory_id, variety_id = await _seed_master_data(sqlite_session)
    task9_run_id, output = await _persist_task9_run(sqlite_session)
    as_of_date = _snapshot_as_of_date(output)
    label_build = await _seed_build_run(
        sqlite_session,
        build_run_id=21,
        season_id=season_id,
        source_max_raw_id=100,
        config_hash="a" * 64,
        finished_at=datetime(2026, 3, 20, tzinfo=UTC),
    )
    feature_build = await _seed_build_run(
        sqlite_session,
        build_run_id=22,
        season_id=season_id,
        source_max_raw_id=50,
        config_hash="b" * 64,
        finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
        config_snapshot={
            "version": "task3-v1",
            "analysis_months": [1, 2, 3, 4],
        },
    )
    await _seed_daily_fact(
        sqlite_session,
        fact_id=301,
        build_run_id=label_build.id,
        season_id=season_id,
        factory_id=factory_id,
        variety_id=variety_id,
        receipt_date=output.forecast_start_date,
        weight_kg=Decimal("100"),
    )
    await _seed_daily_fact(
        sqlite_session,
        fact_id=302,
        build_run_id=feature_build.id,
        season_id=season_id,
        factory_id=factory_id,
        variety_id=variety_id,
        receipt_date=as_of_date - timedelta(days=3),
        weight_kg=Decimal("9"),
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

    assert rows
    assert all(row.include is False for row in rows)
    assert {row.exclusion_reason for row in rows} == {"receipt_date_not_covered_by_build"}


@pytest.mark.asyncio
async def test_manifest_uses_task9_holiday_snapshot_not_current_holiday_table(
    sqlite_session: AsyncSession,
) -> None:
    season_id, factory_id, variety_id = await _seed_master_data(sqlite_session)
    task9_run_id, output = await _persist_task9_run(sqlite_session)
    as_of_date = _snapshot_as_of_date(output)
    label_build = await _seed_build_run(
        sqlite_session,
        build_run_id=31,
        season_id=season_id,
        source_max_raw_id=100,
        config_hash="a" * 64,
        finished_at=datetime(2026, 3, 20, tzinfo=UTC),
    )
    feature_build = await _seed_build_run(
        sqlite_session,
        build_run_id=32,
        season_id=season_id,
        source_max_raw_id=50,
        config_hash="b" * 64,
        finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
    )
    await _seed_daily_fact(
        sqlite_session,
        fact_id=401,
        build_run_id=label_build.id,
        season_id=season_id,
        factory_id=factory_id,
        variety_id=variety_id,
        receipt_date=output.forecast_start_date,
        weight_kg=Decimal("100"),
    )
    for offset, fact_id in ((1, 402), (3, 403), (7, 404)):
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
    holiday = Holiday(
        id=99,
        season_id=season_id,
        code="spring_festival",
        name="Changed Holiday",
        start_date=date(2026, 3, 20),
        end_date=date(2026, 3, 25),
        active=True,
    )
    sqlite_session.add(holiday)
    await sqlite_session.commit()

    first = await build_residual_training_manifest(
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
    holiday.start_date = date(2026, 2, 1)
    holiday.end_date = date(2026, 2, 10)
    holiday.name = "Mutated Holiday"
    await sqlite_session.commit()
    second = await build_residual_training_manifest(
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

    first_flags = [
        next(
            feature.value
            for feature in row.feature_values
            if feature.feature_name == "spring_festival_window_flag"
        )
        for row in first
    ]
    second_flags = [
        next(
            feature.value
            for feature in row.feature_values
            if feature.feature_name == "spring_festival_window_flag"
        )
        for row in second
    ]
    assert first_flags == second_flags
    assert [row.feature_vector_hash for row in first] == [row.feature_vector_hash for row in second]


@pytest.mark.asyncio
async def test_manifest_uses_explicit_factory_category_snapshot_not_current_factory_row(
    sqlite_session: AsyncSession,
) -> None:
    season_id, factory_id, variety_id = await _seed_master_data(sqlite_session)
    task9_run_id, output = await _persist_task9_run(sqlite_session)
    as_of_date = _snapshot_as_of_date(output)
    label_build = await _seed_build_run(
        sqlite_session,
        build_run_id=41,
        season_id=season_id,
        source_max_raw_id=100,
        config_hash="a" * 64,
        finished_at=datetime(2026, 3, 20, tzinfo=UTC),
    )
    feature_build = await _seed_build_run(
        sqlite_session,
        build_run_id=42,
        season_id=season_id,
        source_max_raw_id=50,
        config_hash="b" * 64,
        finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
    )
    await _seed_daily_fact(
        sqlite_session,
        fact_id=501,
        build_run_id=label_build.id,
        season_id=season_id,
        factory_id=factory_id,
        variety_id=variety_id,
        receipt_date=output.forecast_start_date,
        weight_kg=Decimal("100"),
    )
    for offset, fact_id in ((1, 502), (3, 503), (7, 504)):
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

    first = await build_residual_training_manifest(
        sqlite_session,
        samples=[
            ResidualTrainingSampleSpec(
                task9_run_id=task9_run_id,
                label_analytics_build_run_id=label_build.id,
                feature_analytics_build_run_id=feature_build.id,
                split="train",
                supplemental_feature_values=_supplemental_features(
                    as_of_date=as_of_date,
                    destination_factory_category="snapshot-north",
                ),
            )
        ],
    )
    factory = await sqlite_session.get(Factory, factory_id)
    assert factory is not None
    factory.region_name = "mutated-region"
    await sqlite_session.commit()
    second = await build_residual_training_manifest(
        sqlite_session,
        samples=[
            ResidualTrainingSampleSpec(
                task9_run_id=task9_run_id,
                label_analytics_build_run_id=label_build.id,
                feature_analytics_build_run_id=feature_build.id,
                split="train",
                supplemental_feature_values=_supplemental_features(
                    as_of_date=as_of_date,
                    destination_factory_category="snapshot-north",
                ),
            )
        ],
    )

    first_categories = [
        next(
            feature.value
            for feature in row.feature_values
            if feature.feature_name == "destination_factory_category"
        )
        for row in first
    ]
    second_categories = [
        next(
            feature.value
            for feature in row.feature_values
            if feature.feature_name == "destination_factory_category"
        )
        for row in second
    ]
    assert first_categories == ["snapshot-north"] * len(first)
    assert second_categories == first_categories
    assert [row.feature_vector_hash for row in first] == [row.feature_vector_hash for row in second]


@pytest.mark.asyncio
async def test_real_task3_build_feeds_manifest_with_aggregated_actuals(
    sqlite_session: AsyncSession,
) -> None:
    season_id, factory_id, variety_id = await _seed_master_data(sqlite_session)
    task9_run_id, output = await _persist_task9_run(sqlite_session)
    as_of_date = _snapshot_as_of_date(output)
    analytics_config = load_analytics_config(repo_root() / "configs" / "analytics_rules.yaml")

    feature_ingest_id = await _create_ingest_file(
        sqlite_session,
        ingest_file_id=1,
        season_id=season_id,
        file_sha256="feature-build",
    )
    await _insert_raw_rows(
        sqlite_session,
        ingest_file_id=feature_ingest_id,
        season_id=season_id,
        factory_id=factory_id,
        variety_id=variety_id,
        rows=[
            {
                "receipt_date": date(2026, 1, 10),
                "weight_kg": Decimal("5"),
                "farm_raw": "farm-a",
                "subfarm_raw": "subfarm-a",
            },
            {
                "receipt_date": date(2026, 2, 21),
                "weight_kg": Decimal("17"),
                "farm_raw": "farm-a",
                "subfarm_raw": "subfarm-a",
            },
            {
                "receipt_date": date(2026, 2, 25),
                "weight_kg": Decimal("10"),
                "farm_raw": "farm-b",
                "subfarm_raw": "subfarm-b",
            },
            {
                "receipt_date": date(2026, 2, 25),
                "weight_kg": Decimal("13"),
                "farm_raw": "farm-c",
                "subfarm_raw": "subfarm-c",
            },
            {
                "receipt_date": date(2026, 2, 27),
                "weight_kg": Decimal("11"),
                "farm_raw": "farm-a",
                "subfarm_raw": "subfarm-d",
            },
        ],
    )
    await sqlite_session.commit()
    feature_build = await build_daily_facts_for_season(
        sqlite_session,
        "2025-2026",
        analytics_config,
    )
    assert feature_build.status == "completed"
    assert feature_build.build_run_id is not None

    label_ingest_id = await _create_ingest_file(
        sqlite_session,
        ingest_file_id=2,
        season_id=season_id,
        file_sha256="label-build",
    )
    await _insert_raw_rows(
        sqlite_session,
        ingest_file_id=label_ingest_id,
        season_id=season_id,
        factory_id=factory_id,
        variety_id=variety_id,
        rows=[
            {
                "receipt_date": date(2026, 3, 1),
                "weight_kg": Decimal("100"),
                "farm_raw": "farm-a",
                "subfarm_raw": "subfarm-a",
            },
            {
                "receipt_date": date(2026, 3, 2),
                "weight_kg": Decimal("101"),
                "farm_raw": "farm-b",
                "subfarm_raw": "subfarm-b",
            },
            {
                "receipt_date": date(2026, 3, 3),
                "weight_kg": Decimal("102"),
                "farm_raw": "farm-c",
                "subfarm_raw": "subfarm-c",
            },
        ],
    )
    await sqlite_session.commit()
    label_build = await build_daily_facts_for_season(
        sqlite_session,
        "2025-2026",
        analytics_config,
    )
    assert label_build.status == "completed"
    assert label_build.build_run_id is not None

    manifest_rows = await build_residual_training_manifest(
        sqlite_session,
        samples=[
            ResidualTrainingSampleSpec(
                task9_run_id=task9_run_id,
                label_analytics_build_run_id=label_build.build_run_id,
                feature_analytics_build_run_id=feature_build.build_run_id,
                split="train",
                supplemental_feature_values=_supplemental_features(
                    as_of_date=as_of_date,
                    destination_factory_category="snapshot-north",
                ),
            )
        ],
    )

    assert manifest_rows
    first_row = manifest_rows[0]
    feature_map = {item.feature_name: item.value for item in first_row.feature_values}
    assert first_row.feature_actual_snapshot.build_run_id == feature_build.build_run_id
    assert first_row.label_actual_snapshot.build_run_id == label_build.build_run_id
    assert feature_map["actual_receipt_lag_1d_kg"] == Decimal("11")
    assert feature_map["actual_receipt_lag_3d_kg"] == Decimal("23")
    assert feature_map["actual_receipt_lag_7d_kg"] == Decimal("17")
    assert feature_map["actual_receipt_rolling_3d_mean_kg"] == Decimal(
        "11.33333333333333333333333333"
    )
    assert feature_map["actual_receipt_rolling_7d_mean_kg"] == Decimal(
        "7.285714285714285714285714286"
    )
    assert feature_map["actual_receipt_cumulative_to_as_of_kg"] == Decimal("56")


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
    validation_season_id = await _seed_season(
        sqlite_session,
        season_id=2,
        code="2026-2027",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 31),
    )
    task9_run_id, output = await _persist_task9_run(sqlite_session)
    as_of_date = _snapshot_as_of_date(output)
    label_build = await _seed_build_run(
        sqlite_session,
        build_run_id=1,
        season_id=season_id,
        source_max_raw_id=100,
        config_hash="a" * 64,
        finished_at=datetime(2026, 3, 20, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
    )
    feature_build = await _seed_build_run(
        sqlite_session,
        build_run_id=2,
        season_id=season_id,
        source_max_raw_id=50,
        config_hash="b" * 64,
        finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
    )
    validation_label_build = await _seed_build_run(
        sqlite_session,
        build_run_id=101,
        season_id=validation_season_id,
        source_max_raw_id=200,
        config_hash="c" * 64,
        finished_at=datetime(2026, 3, 20, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
    )
    validation_feature_build = await _seed_build_run(
        sqlite_session,
        build_run_id=102,
        season_id=validation_season_id,
        source_max_raw_id=150,
        config_hash="d" * 64,
        finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
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
    for index, target_date in enumerate((date(2026, 3, 1), date(2026, 3, 2), date(2026, 3, 3))):
        await _seed_daily_fact(
            sqlite_session,
            fact_id=300 + index,
            build_run_id=validation_label_build.id,
            season_id=validation_season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=target_date,
            weight_kg=Decimal("120") + Decimal(index),
        )
    for offset, weight in ((1, Decimal("21")), (3, Decimal("23")), (7, Decimal("27"))):
        await _seed_daily_fact(
            sqlite_session,
            fact_id=400 + offset,
            build_run_id=validation_feature_build.id,
            season_id=validation_season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=as_of_date - timedelta(days=offset),
            weight_kg=weight,
        )
    await sqlite_session.commit()

    loaded, run_id = await execute_residual_training(
        sqlite_session,
        samples=_diverse_training_samples(
            task9_run_id=task9_run_id,
            label_build_run_id=label_build.id,
            feature_build_run_id=feature_build.id,
            as_of_date=as_of_date,
        ),
        config=_config(),
    )

    assert run_id > 0
    assert loaded.execution_status == "completed"
    assert loaded.eligibility_status == "ineligible"
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
