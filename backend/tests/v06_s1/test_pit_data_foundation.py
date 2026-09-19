from __future__ import annotations

import importlib
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import delete, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.pit import (
    AreaRevisionInput,
    ForecastRunSnapshotInput,
    PhenologyObservationInput,
    PITConflictError,
    PITDataFoundationRepository,
    PITIntegrityError,
    RealizedWeatherObservationInput,
    WeatherForecastSnapshotInput,
    build_input_snapshot,
    record_visible_at,
    weather_forecast_visible_at,
)
from backend.app.pit.actual_harvest import (
    ACTUAL_HARVEST_REUSED,
    actual_harvest_visible_at,
    adapt_actual_harvest_record,
)
from backend.app.pit.models import (
    AreaRevision,
    ForecastRunSnapshot,
    ForecastRunSnapshotDaily,
    PhenologyObservation,
    RealizedWeatherObservation,
    WeatherForecastSnapshot,
)

NOW = datetime(2026, 9, 19, 4, 0, tzinfo=UTC)


def _upgrade_pit_schema(connection: object) -> None:
    context = MigrationContext.configure(connection)  # type: ignore[arg-type]
    operations = Operations(context)
    migration = importlib.import_module("backend.alembic.versions.0036_v06_pit_data_foundation")
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
        await connection.run_sync(_upgrade_pit_schema)
    session = AsyncSession(engine, expire_on_commit=False)
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


def _area_input(
    *,
    area_id: str = "area-rev-1",
    known_at: datetime = NOW,
    season: str = "REFERENCE",
    area_type: str = "REFERENCE_AREA",
) -> AreaRevisionInput:
    return AreaRevisionInput(
        area_revision_id=area_id,
        base_id="base-1",
        season=season,
        area_mu=Decimal("394"),
        area_type=area_type,
        effective_from=NOW - timedelta(days=30),
        recorded_at=NOW - timedelta(days=2),
        known_at=known_at,
        source="base-registry",
        source_reference="registry.json",
        basis="REFERENCE_AREA_ONLY",
    )


def _weather_input(
    *, weather_id: str = "weather-1", known_at: datetime = NOW
) -> WeatherForecastSnapshotInput:
    return WeatherForecastSnapshotInput(
        weather_snapshot_id=weather_id,
        provider="test-provider",
        base_id="base-1",
        issued_at=NOW - timedelta(hours=3),
        fetched_at=NOW - timedelta(hours=2),
        known_at=known_at,
        valid_at=NOW + timedelta(days=1),
        forecast_horizon_hours=24,
        temperature_mean=Decimal("18.2"),
        raw_payload_hash="a" * 64,
        normalized_payload_hash="b" * 64,
    )


def _phenology_input(
    *, observation_id: str = "phenology-1", known_at: datetime = NOW
) -> PhenologyObservationInput:
    return PhenologyObservationInput(
        observation_id=observation_id,
        base_id="base-1",
        season="2026-2027",
        phenology_stage="flowering",
        observed_at=NOW - timedelta(days=1),
        recorded_at=NOW - timedelta(hours=1),
        known_at=known_at,
        source="business-observation",
        source_reference="observation-1",
        quality_status="accepted",
    )


def _forecast_input(
    *,
    area_revision_id: str = "area-rev-1",
    weather_ids: list[str] | None = None,
    phenology_ids: list[str] | None = None,
) -> ForecastRunSnapshotInput:
    weather_ids = weather_ids or ["weather-1"]
    phenology_ids = phenology_ids or ["phenology-1"]
    daily = [
        {
            "forecast_date": date(2026, 10, 1),
            "predicted_quantity_kg": Decimal("40"),
            "normalized_share": Decimal("0.4"),
        },
        {
            "forecast_date": date(2026, 10, 2),
            "predicted_quantity_kg": Decimal("60"),
            "normalized_share": Decimal("0.6"),
        },
    ]
    input_json, input_hash = build_input_snapshot(
        request={"base_id": "base-1", "target_season": "2026-2027"},
        base_identity={"base_id": "base-1", "canonical_base_name": "Test Base"},
        target_season="2026-2027",
        target_area={"target_area_mu": Decimal("394")},
        area_revision_id=area_revision_id,
        prior_history={
            "season": "2025-2026",
            "quantity_kg": "100",
            "coverage_status": "INCOMPLETE",
            "source_hash": "c" * 64,
            "identity_mapping_hash": "d" * 64,
        },
        weather_snapshot_ids=weather_ids,
        phenology_observation_ids=phenology_ids,
        model={
            "total_model_id": "BASE_AWARE_BASELINE_R1",
            "temporal_model_id": "AREA_DAILY_RIDGE_V1_FROZEN_REFERENCE",
            "artifact_hashes": {"total": "e" * 64, "temporal": "f" * 64},
        },
        forecast_mode="SHADOW",
        coverage={"prior_history_coverage_status": "INCOMPLETE"},
        forecast_created_at=NOW,
        warnings=["PRIOR_SEASON_HISTORY_COVERAGE_INCOMPLETE"],
    )
    candidate = ForecastRunSnapshotInput.model_validate(
        {
            "forecast_run_id": "forecast-1",
            "forecast_created_at": NOW,
            "base_id": "base-1",
            "target_season": "2026-2027",
            "forecast_start_date": date(2026, 10, 1),
            "forecast_end_date": date(2026, 10, 2),
            "target_area_mu": Decimal("394"),
            "forecast_mode": "SHADOW",
            "model_status": "EXPERIMENTAL",
            "total_model_id": "BASE_AWARE_BASELINE_R1",
            "temporal_model_id": "AREA_DAILY_RIDGE_V1_FROZEN_REFERENCE",
            "model_artifact_hashes": {"total": "e" * 64, "temporal": "f" * 64},
            "prior_history_season": "2025-2026",
            "prior_history_quantity_kg": Decimal("100"),
            "prior_history_coverage_status": "INCOMPLETE",
            "prior_history_source_hash": "c" * 64,
            "prior_history_identity_mapping_hash": "d" * 64,
            "area_revision_id": area_revision_id,
            "weather_snapshot_ids": weather_ids,
            "phenology_observation_ids": phenology_ids,
            "input_snapshot_json": input_json,
            "input_snapshot_hash": input_hash,
            "predicted_season_total_kg": Decimal("100"),
            "daily_curve": daily,
            "single_day_peak": {"date": "2026-10-02", "quantity_kg": "60"},
            "rolling_7day_peak": {
                "start_date": "2026-10-01",
                "end_date": "2026-10-02",
                "quantity_kg": "100",
            },
            "result_hash": "0" * 64,
            "warnings": ["PRIOR_SEASON_HISTORY_COVERAGE_INCOMPLETE"],
        }
    )
    return candidate.model_copy(update={"result_hash": candidate.computed_result_hash()})


def _with_snapshot_mutation(
    forecast: ForecastRunSnapshotInput, path: tuple[str, ...], value: object
) -> ForecastRunSnapshotInput:
    snapshot = deepcopy(forecast.input_snapshot_json)
    target = snapshot
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    from backend.app.pit.canonical import hash_payload

    return forecast.model_copy(
        update={
            "input_snapshot_json": snapshot,
            "input_snapshot_hash": hash_payload(snapshot),
        }
    )


async def _seed_forecast_dependencies(repository: PITDataFoundationRepository) -> None:
    await repository.add_area_revision(_area_input())
    await repository.add_weather_forecast_snapshot(_weather_input())
    await repository.add_phenology_observation(_phenology_input())


@pytest.mark.unit
def test_canonical_input_snapshot_is_deterministic_and_binds_sources() -> None:
    first = build_input_snapshot(
        request={"base_id": "base-1"},
        base_identity={"base_id": "base-1"},
        target_season="2026-2027",
        target_area={"target_area_mu": Decimal("394.000")},
        area_revision_id="area-rev-1",
        prior_history={"source_hash": "a" * 64},
        weather_snapshot_ids=["weather-2", "weather-1"],
        phenology_observation_ids=["phenology-1"],
        model={"artifact": "b" * 64},
        forecast_mode="SHADOW",
        coverage={"status": "INCOMPLETE"},
    )
    same = build_input_snapshot(
        request={"base_id": "base-1"},
        base_identity={"base_id": "base-1"},
        target_season="2026-2027",
        target_area={"target_area_mu": Decimal("394")},
        area_revision_id="area-rev-1",
        prior_history={"source_hash": "a" * 64},
        weather_snapshot_ids=["weather-1", "weather-2"],
        phenology_observation_ids=["phenology-1"],
        model={"artifact": "b" * 64},
        forecast_mode="SHADOW",
        coverage={"status": "INCOMPLETE"},
    )
    assert first == same
    changed = build_input_snapshot(
        request={"base_id": "base-1"},
        base_identity={"base_id": "base-1"},
        target_season="2026-2027",
        target_area={"target_area_mu": Decimal("394")},
        area_revision_id="area-rev-1",
        prior_history={"source_hash": "c" * 64},
        weather_snapshot_ids=["weather-1", "weather-2"],
        phenology_observation_ids=["phenology-1"],
        model={"artifact": "b" * 64},
        forecast_mode="SHADOW",
        coverage={"status": "INCOMPLETE"},
    )
    assert first[1] != changed[1]


@pytest.mark.unit
def test_visibility_requires_known_at_and_weather_issued_at() -> None:
    area = _area_input()
    assert record_visible_at(area, NOW)
    assert not record_visible_at(_area_input(known_at=NOW + timedelta(seconds=1)), NOW)
    weather = _weather_input()
    assert weather_forecast_visible_at(weather, NOW)
    assert not weather_forecast_visible_at(_weather_input(known_at=NOW + timedelta(seconds=1)), NOW)


@pytest.mark.unit
async def test_foundation_persists_and_reloads_without_commit(sqlite_session: AsyncSession) -> None:
    await sqlite_session.begin()
    repository = PITDataFoundationRepository(sqlite_session)
    await repository.add_area_revision(_area_input())
    await repository.add_weather_forecast_snapshot(_weather_input())
    await repository.add_phenology_observation(_phenology_input())
    forecast = _forecast_input()
    saved = await repository.save_forecast_run_snapshot(forecast)
    loaded = await repository.get_forecast_run_snapshot("forecast-1")
    assert saved.model_dump(mode="json") == loaded.model_dump(mode="json")
    assert loaded.input_snapshot_hash == forecast.input_snapshot_hash
    assert loaded.result_hash == forecast.result_hash
    assert len(loaded.daily_curve) == 2
    assert await sqlite_session.scalar(select(ForecastRunSnapshotDaily.id)) is not None

    with pytest.raises(DBAPIError):
        await sqlite_session.execute(update(ForecastRunSnapshot).values(model_status="TAMPERED"))
    await sqlite_session.rollback()
    assert await sqlite_session.scalar(select(ForecastRunSnapshot.forecast_run_id)) is None


@pytest.mark.unit
@pytest.mark.parametrize(
    ("path", "value"),
    (
        (("base_identity", "base_id"), "base-other"),
        (("model", "total_model_id"), "OTHER_TOTAL_MODEL"),
        (("model", "artifact_hashes", "total"), "a" * 64),
        (("prior_history", "quantity_kg"), "101"),
        (("prior_history", "source_hash"), "a" * 64),
        (("coverage", "prior_history_coverage_status"), "COMPLETE"),
        (("warnings",), ["DIFFERENT_WARNING"]),
    ),
)
async def test_input_snapshot_rejects_cross_field_mismatch(
    sqlite_session: AsyncSession,
    path: tuple[str, ...],
    value: object,
) -> None:
    repository = PITDataFoundationRepository(sqlite_session)
    with pytest.raises(PITIntegrityError):
        await repository.save_forecast_run_snapshot(
            _with_snapshot_mutation(_forecast_input(), path, value)
        )


@pytest.mark.unit
async def test_forecast_run_idempotency_and_result_conflicts(
    sqlite_session: AsyncSession,
) -> None:
    repository = PITDataFoundationRepository(sqlite_session)
    await _seed_forecast_dependencies(repository)
    forecast = _forecast_input()
    first = await repository.save_forecast_run_snapshot(forecast)
    same = await repository.save_forecast_run_snapshot(forecast)
    assert same.forecast_run_id == first.forecast_run_id
    assert same.result_hash == first.result_hash

    changed_daily = [
        forecast.daily_curve[0].model_copy(update={"predicted_quantity_kg": Decimal("40.4")}),
        forecast.daily_curve[1].model_copy(update={"predicted_quantity_kg": Decimal("60")}),
    ]
    changed_result = forecast.model_copy(
        update={
            "predicted_season_total_kg": Decimal("100.4"),
            "daily_curve": changed_daily,
            "single_day_peak": {"date": "2026-10-02", "quantity_kg": "60.4"},
            "rolling_7day_peak": {
                "start_date": "2026-10-01",
                "end_date": "2026-10-02",
                "quantity_kg": "100.4",
            },
        }
    )
    changed_result = changed_result.model_copy(
        update={"result_hash": changed_result.computed_result_hash()}
    )
    with pytest.raises(PITConflictError, match="FORECAST_RUN_RESULT_CONFLICT"):
        await repository.save_forecast_run_snapshot(changed_result)

    from backend.app.pit.canonical import hash_payload

    changed_input_snapshot = deepcopy(forecast.input_snapshot_json)
    changed_input_snapshot["target_area"]["target_area_mu"] = "395"
    different_input = forecast.model_copy(
        update={
            "target_area_mu": Decimal("395"),
            "input_snapshot_json": changed_input_snapshot,
            "input_snapshot_hash": hash_payload(changed_input_snapshot),
        }
    )
    different_input = different_input.model_copy(
        update={"result_hash": different_input.computed_result_hash()}
    )
    with pytest.raises(PITConflictError, match="FORECAST_RUN_ID_CONFLICT"):
        await repository.save_forecast_run_snapshot(different_input)


@pytest.mark.unit
@pytest.mark.parametrize("area_type", ("ACTUAL_PRODUCTIVE_AREA", "PLANTED_AREA", "PLANNED_AREA"))
async def test_non_reference_area_revision_must_match_target_season(
    sqlite_session: AsyncSession,
    area_type: str,
) -> None:
    repository = PITDataFoundationRepository(sqlite_session)
    await repository.add_area_revision(_area_input(season="2025-2026", area_type=area_type))
    await repository.add_weather_forecast_snapshot(_weather_input())
    await repository.add_phenology_observation(_phenology_input())
    with pytest.raises(PITIntegrityError, match="AREA_REVISION_SEASON_MISMATCH"):
        await repository.save_forecast_run_snapshot(_forecast_input())


@pytest.mark.unit
async def test_non_reference_area_revision_matching_target_season_is_allowed(
    sqlite_session: AsyncSession,
) -> None:
    repository = PITDataFoundationRepository(sqlite_session)
    await repository.add_area_revision(
        _area_input(season="2026-2027", area_type="ACTUAL_PRODUCTIVE_AREA")
    )
    await repository.add_weather_forecast_snapshot(_weather_input())
    await repository.add_phenology_observation(_phenology_input())
    saved = await repository.save_forecast_run_snapshot(_forecast_input())
    assert saved.area_revision_id == "area-rev-1"


@pytest.mark.unit
async def test_pit_rejects_hindsight_dependencies(sqlite_session: AsyncSession) -> None:
    repository = PITDataFoundationRepository(sqlite_session)
    await repository.add_area_revision(_area_input())
    await repository.add_weather_forecast_snapshot(
        _weather_input(known_at=NOW + timedelta(seconds=1))
    )
    await repository.add_phenology_observation(
        _phenology_input(known_at=NOW + timedelta(seconds=1))
    )
    with pytest.raises(Exception, match="NOT_VISIBLE"):
        await repository.save_forecast_run_snapshot(_forecast_input())


@pytest.mark.unit
async def test_pit_rejects_hindsight_area_revision(sqlite_session: AsyncSession) -> None:
    repository = PITDataFoundationRepository(sqlite_session)
    await repository.add_area_revision(_area_input(known_at=NOW + timedelta(seconds=1)))
    await repository.add_weather_forecast_snapshot(_weather_input())
    await repository.add_phenology_observation(_phenology_input())
    with pytest.raises(Exception, match="AREA_REVISION_NOT_VISIBLE"):
        await repository.save_forecast_run_snapshot(_forecast_input())


@pytest.mark.unit
async def test_pit_rejects_hindsight_weather_snapshot(sqlite_session: AsyncSession) -> None:
    repository = PITDataFoundationRepository(sqlite_session)
    await repository.add_area_revision(_area_input())
    await repository.add_weather_forecast_snapshot(
        _weather_input(known_at=NOW + timedelta(seconds=1))
    )
    await repository.add_phenology_observation(_phenology_input())
    with pytest.raises(Exception, match="WEATHER_FORECAST_NOT_VISIBLE"):
        await repository.save_forecast_run_snapshot(_forecast_input())


@pytest.mark.unit
async def test_pit_rejects_hindsight_phenology_observation(sqlite_session: AsyncSession) -> None:
    repository = PITDataFoundationRepository(sqlite_session)
    await repository.add_area_revision(_area_input())
    await repository.add_weather_forecast_snapshot(_weather_input())
    await repository.add_phenology_observation(
        _phenology_input(known_at=NOW + timedelta(seconds=1))
    )
    with pytest.raises(Exception, match="PHENOLOGY_NOT_VISIBLE"):
        await repository.save_forecast_run_snapshot(_forecast_input())


@pytest.mark.unit
async def test_area_revision_supersede_preserves_history(sqlite_session: AsyncSession) -> None:
    repository = PITDataFoundationRepository(sqlite_session)
    first = await repository.add_area_revision(_area_input())
    second_input = _area_input(area_id="area-rev-2").model_copy(
        update={
            "area_mu": Decimal("395"),
            "effective_from": NOW,
            "recorded_at": NOW,
            "supersedes_revision_id": first.area_revision_id,
        }
    )
    second = await repository.add_area_revision(second_input)
    visible = await repository.visible_area_revision(
        base_id="base-1", season="REFERENCE", forecast_created_at=NOW
    )
    assert visible is not None
    assert visible.area_revision_id == second.area_revision_id
    assert (await repository.get_area_revision(first.area_revision_id)).area_mu == Decimal("394")


@pytest.mark.unit
def test_weather_snapshot_requires_fetched_at_before_known_at() -> None:
    with pytest.raises(ValueError, match="fetched_at must be <= known_at"):
        _weather_input(known_at=NOW - timedelta(hours=2, minutes=30))


@pytest.mark.unit
def test_actual_harvest_reuses_existing_import_record_visibility() -> None:
    assert ACTUAL_HARVEST_REUSED is True
    record = SimpleNamespace(
        farm_code="farm-1",
        harvest_business_date=date(2026, 10, 1),
        actual_harvest_quantity_kg=Decimal("12.5"),
        source_system="actual-import",
        external_revision_id="revision-1",
        source_recorded_at=NOW - timedelta(hours=2),
        import_received_at=NOW - timedelta(hours=1),
        ingested_at=NOW - timedelta(minutes=30),
    )
    adapted = adapt_actual_harvest_record(record, base_id="base-1", payload_hash="a" * 64)
    assert adapted.base_id == "base-1"
    assert adapted.quantity_kg == Decimal("12.5")
    assert actual_harvest_visible_at(record, forecast_created_at=NOW)
    assert not actual_harvest_visible_at(record, forecast_created_at=NOW - timedelta(hours=2))


@pytest.mark.unit
async def test_area_weather_phenology_are_immutable(sqlite_session: AsyncSession) -> None:
    repository = PITDataFoundationRepository(sqlite_session)
    cases = (
        (update(AreaRevision).values(source="tampered"), "area"),
        (update(WeatherForecastSnapshot).values(provider="tampered"), "weather"),
        (update(PhenologyObservation).values(notes="tampered"), "phenology"),
        (delete(AreaRevision), "area"),
    )
    for statement, kind in cases:
        if kind == "area":
            await repository.add_area_revision(_area_input())
        elif kind == "weather":
            await repository.add_weather_forecast_snapshot(_weather_input())
        else:
            await repository.add_phenology_observation(_phenology_input())
        with pytest.raises(DBAPIError):
            await sqlite_session.execute(statement)
        await sqlite_session.rollback()
        repository = PITDataFoundationRepository(sqlite_session)


@pytest.mark.unit
async def test_realized_weather_is_separate_from_forecast_weather(
    sqlite_session: AsyncSession,
) -> None:
    repository = PITDataFoundationRepository(sqlite_session)
    realized = await repository.add_realized_weather_observation(
        RealizedWeatherObservationInput(
            weather_observation_id="realized-1",
            base_id="base-1",
            observation_time=NOW,
            temperature=Decimal("17"),
            source="era5-land",
            source_reference="raw-artifact",
            recorded_at=NOW,
            known_at=NOW,
        )
    )
    assert realized.weather_observation_id == "realized-1"
    assert (
        await sqlite_session.scalar(select(RealizedWeatherObservation.weather_observation_id))
        == "realized-1"
    )
    assert await sqlite_session.scalar(select(WeatherForecastSnapshot.weather_snapshot_id)) is None
