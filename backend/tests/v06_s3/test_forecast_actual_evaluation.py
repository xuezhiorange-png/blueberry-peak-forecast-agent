from __future__ import annotations

import importlib
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.pit.canonical import build_input_snapshot, hash_payload
from backend.app.pit.evaluation import (
    ActualDailyRecord,
    ActualDailyStatus,
    EvaluationConflictError,
    RealizedWeatherPoint,
    align_forecast_actual,
    compute_forecast_actual_evaluation,
)
from backend.app.pit.evaluation_models import ForecastEvaluation
from backend.app.pit.evaluation_persistence import ForecastEvaluationRepository
from backend.app.pit.models import (
    ForecastRunSnapshotDaily,
)
from backend.app.pit.persistence import PITDataFoundationRepository
from backend.app.pit.schemas import (
    AreaRevisionInput,
    ForecastDailySnapshotInput,
    ForecastRunSnapshotInput,
    WeatherForecastSnapshotInput,
)

NOW = datetime(2026, 9, 19, 4, 0, tzinfo=UTC)
BASE_ID = "base-evaluation-1"
SEASON = "2026-2027"
START = date(2026, 10, 1)


def _upgrade_schema(connection: object) -> None:
    context = MigrationContext.configure(connection)  # type: ignore[arg-type]
    operations = Operations(context)
    for revision in (
        "0036_v06_pit_data_foundation",
        "0037_v06_pit_scope_time_integrity",
        "0038_v06_s3_forecast_actual_evaluation",
    ):
        migration = importlib.import_module(f"backend.alembic.versions.{revision}")
        migration.op = operations
        migration.upgrade()


@pytest.fixture
async def sqlite_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(_upgrade_schema)
    session = AsyncSession(engine, expire_on_commit=False)
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


def _area() -> AreaRevisionInput:
    return AreaRevisionInput(
        area_revision_id="area-evaluation-1",
        base_id=BASE_ID,
        season="REFERENCE",
        area_mu=Decimal("100"),
        area_type="REFERENCE_AREA",
        effective_from=NOW - timedelta(days=30),
        recorded_at=NOW - timedelta(days=2),
        known_at=NOW - timedelta(days=1),
        source="test-registry",
        source_reference="registry-test.json",
        basis="REFERENCE_AREA_ONLY",
    )


def _weather_inputs() -> list[WeatherForecastSnapshotInput]:
    result: list[WeatherForecastSnapshotInput] = []
    for index, horizon in enumerate((24, 72, 168, 360), start=1):
        issued = NOW - timedelta(hours=3)
        valid = NOW + timedelta(hours=horizon)
        result.append(
            WeatherForecastSnapshotInput(
                weather_snapshot_id=f"weather-evaluation-{horizon}",
                provider="ecmwf-ifs-open-data",
                base_id=BASE_ID,
                issued_at=issued,
                fetched_at=NOW - timedelta(hours=2),
                known_at=NOW - timedelta(hours=1),
                valid_at=valid,
                forecast_horizon_hours=horizon,
                temperature_mean=Decimal(str(18 + index)),
                precipitation=Decimal(index),
                raw_payload_hash=f"{index}" * 64,
                normalized_payload_hash=f"{index + 4}" * 64,
            )
        )
    return result


def _forecast_input() -> ForecastRunSnapshotInput:
    daily = []
    for offset in range(14):
        daily.append(
            ForecastDailySnapshotInput(
                forecast_date=START + timedelta(days=offset),
                predicted_quantity_kg=Decimal(str(10 + offset)),
                normalized_share=Decimal("0.0714285714285714285714285714"),
            )
        )
    # Use an exactly conserving share sequence; the last row absorbs only
    # canonical share residue, not quantity residue.
    daily[-1] = daily[-1].model_copy(
        update={
            "normalized_share": Decimal("1")
            - sum((row.normalized_share for row in daily[:-1]), Decimal("0"))
        }
    )
    input_json, input_hash = build_input_snapshot(
        request={"base_id": BASE_ID, "target_season": SEASON},
        base_identity={
            "base_id": BASE_ID,
            "canonical_base_name": "Evaluation Base",
            "covered_farms": [],
        },
        target_season=SEASON,
        target_area={"target_area_mu": Decimal("100")},
        area_revision_id="area-evaluation-1",
        prior_history={
            "season": "2025-2026",
            "quantity_kg": "100",
            "coverage_status": "COMPLETE",
            "source_hash": "a" * 64,
            "identity_mapping_hash": "b" * 64,
        },
        weather_snapshot_ids=[item.weather_snapshot_id for item in _weather_inputs()],
        weather_capture_status="CAPTURED",
        weather_provider="ecmwf-ifs-open-data",
        phenology_observation_ids=[],
        model={
            "total_model_id": "BASE_AWARE_BASELINE_R1",
            "temporal_model_id": "AREA_DAILY_RIDGE_V1_FROZEN_REFERENCE",
            "artifact_hashes": {"total": "c" * 64, "temporal": "d" * 64},
        },
        forecast_mode="SHADOW",
        coverage={"prior_history_coverage_status": "COMPLETE"},
        forecast_created_at=NOW,
    )
    candidate = ForecastRunSnapshotInput.model_validate(
        {
            "forecast_run_id": "forecast-evaluation-1",
            "forecast_created_at": NOW,
            "base_id": BASE_ID,
            "target_season": SEASON,
            "forecast_start_date": START,
            "forecast_end_date": START + timedelta(days=13),
            "target_area_mu": Decimal("100"),
            "forecast_mode": "SHADOW",
            "model_status": "EXPERIMENTAL",
            "total_model_id": "BASE_AWARE_BASELINE_R1",
            "temporal_model_id": "AREA_DAILY_RIDGE_V1_FROZEN_REFERENCE",
            "model_artifact_hashes": {"total": "c" * 64, "temporal": "d" * 64},
            "prior_history_season": "2025-2026",
            "prior_history_quantity_kg": Decimal("100"),
            "prior_history_coverage_status": "COMPLETE",
            "prior_history_source_hash": "a" * 64,
            "prior_history_identity_mapping_hash": "b" * 64,
            "area_revision_id": "area-evaluation-1",
            "weather_snapshot_ids": [item.weather_snapshot_id for item in _weather_inputs()],
            "weather_capture_status": "CAPTURED",
            "weather_provider": "ecmwf-ifs-open-data",
            "phenology_observation_ids": [],
            "input_snapshot_json": input_json,
            "input_snapshot_hash": input_hash,
            "predicted_season_total_kg": sum(
                (row.predicted_quantity_kg for row in daily), Decimal("0")
            ),
            "daily_curve": daily,
            "single_day_peak": {
                "date": (START + timedelta(days=13)).isoformat(),
                "quantity_kg": "23",
            },
            "rolling_7day_peak": {
                "start_date": (START + timedelta(days=7)).isoformat(),
                "end_date": (START + timedelta(days=13)).isoformat(),
                "quantity_kg": "140",
            },
            "result_hash": "0" * 64,
            "warnings": [],
        }
    )
    return candidate.model_copy(update={"result_hash": candidate.computed_result_hash()})


def _actual_records(*, missing: set[int] | None = None) -> tuple[ActualDailyRecord, ...]:
    missing = missing or set()
    records: list[ActualDailyRecord] = []
    for offset in range(14):
        if offset in missing:
            continue
        quantity = Decimal(str(11 + offset))
        records.append(
            ActualDailyRecord(
                base_id=BASE_ID,
                target_season=SEASON,
                harvest_date=START + timedelta(days=offset),
                quantity_kg=quantity,
                source="committed-test-authority",
                revision_id=f"logical-{offset}#revision-1",
                source_hash="e" * 64,
                known_at=NOW + timedelta(days=1),
                observed_at=NOW,
                recorded_at=NOW,
                authority_id="actual-commit-test",
            )
        )
    return tuple(records)


def _realized_weather() -> tuple[RealizedWeatherPoint, ...]:
    result: list[RealizedWeatherPoint] = []
    for index, horizon in enumerate((24, 72, 168, 360), start=1):
        result.append(
            RealizedWeatherPoint(
                base_id=BASE_ID,
                observation_time=NOW + timedelta(hours=horizon),
                temperature=Decimal(str(17 + index)),
                precipitation=Decimal(index) - Decimal("0.5"),
                known_at=NOW + timedelta(hours=400),
                observation_id=f"realized-{horizon}",
                source_hash="f" * 64,
            )
        )
    return tuple(result)


@pytest.mark.unit
def test_alignment_distinguishes_missing_from_confirmed_zero() -> None:
    forecast_rows = tuple(
        type(
            "ForecastRow",
            (),
            {"forecast_date": START + timedelta(days=index), "predicted_quantity_kg": Decimal("1")},
        )()
        for index in range(7)
    )
    actual = list(_actual_records())[:6]
    actual.append(
        ActualDailyRecord(
            base_id=BASE_ID,
            target_season=SEASON,
            harvest_date=START + timedelta(days=6),
            quantity_kg=Decimal("0"),
            source="test",
            revision_id="zero",
            source_hash="1" * 64,
            known_at=NOW + timedelta(days=1),
            observed_at=NOW,
            recorded_at=NOW,
            authority_id="zero-authority",
        )
    )
    from backend.app.pit.evaluation import align_forecast_actual

    rows, coverage, _ = align_forecast_actual(
        base_id=BASE_ID,
        target_season=SEASON,
        forecast_start_date=START,
        forecast_end_date=START + timedelta(days=6),
        forecast_rows=forecast_rows,
        actual_records=actual[:-1],
        evaluation_mode="AS_OF_DATE",
        as_of_date=START + timedelta(days=6),
        evaluation_created_at=NOW + timedelta(days=20),
    )
    assert coverage.value == "PARTIAL"
    assert rows[-1].actual_status == ActualDailyStatus.MISSING
    assert rows[-1].actual_quantity_kg is None

    rows, coverage, _ = align_forecast_actual(
        base_id=BASE_ID,
        target_season=SEASON,
        forecast_start_date=START,
        forecast_end_date=START + timedelta(days=6),
        forecast_rows=forecast_rows,
        actual_records=tuple(actual),
        evaluation_mode="AS_OF_DATE",
        as_of_date=START + timedelta(days=6),
        evaluation_created_at=NOW + timedelta(days=2),
    )
    assert coverage.value == "COMPLETE"
    assert rows[-1].actual_status == ActualDailyStatus.CONFIRMED_ZERO
    assert rows[-1].actual_quantity_kg == 0


@pytest.mark.unit
def test_as_of_excludes_future_actual_and_revision_winner_is_deterministic() -> None:
    forecast_rows = tuple(
        type(
            "ForecastRow",
            (),
            {
                "forecast_date": START + timedelta(days=index),
                "predicted_quantity_kg": Decimal("1"),
            },
        )()
        for index in range(7)
    )
    first = _actual_records()[0]
    revision = replace(
        first,
        revision_id="logical-0#revision-2",
        revision_number=2,
        quantity_kg=Decimal("99"),
        source_hash="2" * 64,
    )
    future = replace(
        _actual_records()[7],
        harvest_date=START + timedelta(days=8),
        source_hash="3" * 64,
    )
    rows, coverage, _ = align_forecast_actual(
        base_id=BASE_ID,
        target_season=SEASON,
        forecast_start_date=START,
        forecast_end_date=START + timedelta(days=6),
        forecast_rows=forecast_rows,
        actual_records=tuple(_actual_records()[1:7]) + (first, revision, future),
        evaluation_mode="AS_OF_DATE",
        as_of_date=START + timedelta(days=6),
        evaluation_created_at=NOW + timedelta(days=20),
    )
    assert coverage.value == "COMPLETE"
    assert rows[0].actual_quantity_kg == Decimal("99")
    assert rows[-1].actual_quantity_kg == Decimal("17")


@pytest.mark.unit
def test_rolling_peak_is_not_computable_when_a_window_has_a_missing_day() -> None:
    from backend.app.pit.evaluation import _rolling_metrics

    rows, coverage, _ = align_forecast_actual(
        base_id=BASE_ID,
        target_season=SEASON,
        forecast_start_date=START,
        forecast_end_date=START + timedelta(days=6),
        forecast_rows=tuple(
            type(
                "ForecastRow",
                (),
                {
                    "forecast_date": START + timedelta(days=index),
                    "predicted_quantity_kg": Decimal("1"),
                },
            )()
            for index in range(7)
        ),
        actual_records=_actual_records(missing={3}),
        evaluation_mode="FULL_AVAILABLE_RANGE",
        as_of_date=None,
        evaluation_created_at=NOW + timedelta(days=20),
    )
    assert coverage.value == "PARTIAL"
    assert _rolling_metrics(rows)["status"] == "NOT_COMPUTABLE"


@pytest.mark.unit
async def test_evaluation_metrics_weather_and_reload_are_deterministic(
    sqlite_session: AsyncSession,
) -> None:
    foundation = PITDataFoundationRepository(sqlite_session)
    async with sqlite_session.begin():
        await foundation.add_area_revision(_area())
        weather = _weather_inputs()
        for item in weather:
            await foundation.add_weather_forecast_snapshot(item)
        forecast = _forecast_input()
        saved = await foundation.save_forecast_run_snapshot(forecast)
    daily = list(
        await sqlite_session.scalars(
            select(ForecastRunSnapshotDaily).where(
                ForecastRunSnapshotDaily.forecast_run_id == saved.forecast_run_id
            )
        )
    )
    computation = compute_forecast_actual_evaluation(
        forecast_snapshot=saved,
        forecast_daily_rows=daily,
        actual_records=_actual_records(),
        evaluation_mode="FULL_AVAILABLE_RANGE",
        as_of_date=None,
        evaluation_created_at=NOW + timedelta(days=2),
        forecast_weather_snapshots=[
            await foundation.get_weather_forecast_snapshot(item.weather_snapshot_id)
            for item in weather
        ],
        realized_weather_observations=_realized_weather(),
    )
    assert computation.season_total_metrics["wape"]["status"] == "COMPUTABLE"
    assert computation.single_day_peak_metrics["status"] == "COMPUTABLE"
    assert computation.rolling_7day_peak_metrics["status"] == "COMPUTABLE"
    assert set(computation.weather_metrics) == {"D1", "D3", "D7", "D15"}
    repository = ForecastEvaluationRepository(sqlite_session)
    await sqlite_session.rollback()
    async with sqlite_session.begin():
        stored = await repository.save(computation)
    loaded = await repository.get_evaluation(stored.evaluation_id)
    assert loaded.evaluation_result_hash == computation.evaluation_result_hash
    assert loaded.evaluation_payload_hash == computation.evaluation_payload_hash
    await sqlite_session.rollback()
    async with sqlite_session.begin():
        replay = await repository.save(computation)
    assert replay.evaluation_id == stored.evaluation_id

    with pytest.raises(DBAPIError):
        await sqlite_session.execute(update(ForecastEvaluation).values(warnings=["TAMPERED"]))
    await sqlite_session.rollback()


@pytest.mark.unit
async def test_evaluation_same_identity_different_result_conflicts(
    sqlite_session: AsyncSession,
) -> None:
    foundation = PITDataFoundationRepository(sqlite_session)
    async with sqlite_session.begin():
        await foundation.add_area_revision(_area())
        for item in _weather_inputs():
            await foundation.add_weather_forecast_snapshot(item)
        saved = await foundation.save_forecast_run_snapshot(_forecast_input())
    daily = list(
        await sqlite_session.scalars(
            select(ForecastRunSnapshotDaily).where(
                ForecastRunSnapshotDaily.forecast_run_id == saved.forecast_run_id
            )
        )
    )
    computation = compute_forecast_actual_evaluation(
        forecast_snapshot=saved,
        forecast_daily_rows=daily,
        actual_records=_actual_records(),
        evaluation_mode="FULL_AVAILABLE_RANGE",
        as_of_date=None,
        evaluation_created_at=NOW + timedelta(days=20),
    )
    repository = ForecastEvaluationRepository(sqlite_session)
    await sqlite_session.rollback()
    async with sqlite_session.begin():
        await repository.save(computation)
    changed = replace(computation, warnings=("DIFFERENT_PAYLOAD",))
    changed = replace(
        changed,
        evaluation_result_hash=hash_payload(changed.result_payload()),
        evaluation_payload_hash=hash_payload(
            {"identity": changed.identity_payload(), "result": changed.result_payload()}
        ),
    )
    with pytest.raises(EvaluationConflictError, match="FORECAST_EVALUATION_CONFLICT"):
        async with sqlite_session.begin():
            await repository.save(changed)

    changed_input = replace(computation, as_of_date=START + timedelta(days=3))
    changed_input = replace(
        changed_input,
        evaluation_id=computation.evaluation_id,
        evaluation_identity_hash=hash_payload(changed_input.identity_payload()),
        evaluation_result_hash=hash_payload(changed_input.result_payload()),
        evaluation_payload_hash=hash_payload(
            {
                "identity": changed_input.identity_payload(),
                "result": changed_input.result_payload(),
            }
        ),
    )
    with pytest.raises(EvaluationConflictError, match="FORECAST_EVALUATION_CONFLICT"):
        async with sqlite_session.begin():
            await repository.save(changed_input)


@pytest.mark.migration
def test_s3_migration_is_single_next_revision_and_declares_immutable_tables() -> None:
    migration = importlib.import_module(
        "backend.alembic.versions.0038_v06_s3_forecast_actual_evaluation"
    )
    assert migration.revision == "0038_v06_s3_forecast_actual_evaluation"
    assert migration.down_revision == "0037_v06_pit_scope_time_integrity"
    assert migration._IMMUTABLE_TABLES == ("forecast_evaluation", "forecast_evaluation_daily")


@pytest.mark.migration
def test_s3_migration_upgrade_downgrade_upgrade_round_trip() -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        operations = Operations(context)
        modules = [
            importlib.import_module("backend.alembic.versions.0036_v06_pit_data_foundation"),
            importlib.import_module("backend.alembic.versions.0037_v06_pit_scope_time_integrity"),
            importlib.import_module(
                "backend.alembic.versions.0038_v06_s3_forecast_actual_evaluation"
            ),
        ]
        for module in modules:
            module.op = operations
            module.upgrade()
        modules[-1].downgrade()
        modules[-1].upgrade()
        assert (
            connection.execute(select(ForecastEvaluation.__table__.c.evaluation_id)).first() is None
        )
    engine.dispose()
