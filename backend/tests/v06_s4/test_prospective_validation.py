from __future__ import annotations

import importlib
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.pit.canonical import hash_payload
from backend.app.pit.evaluation import ActualDailyRecord
from backend.app.pit.evaluation_models import ForecastEvaluation, ForecastEvaluationDaily
from backend.app.pit.models import (
    AreaRevision,
    ForecastRunSnapshot,
    PhenologyObservation,
    WeatherForecastSnapshot,
)
from backend.app.pit.prospective_models import (
    ProspectiveValidationRun,
    WeatherIncrementalValueAssessment,
)
from backend.app.pit.prospective_validation import (
    GDD_INCREMENTAL_VALUE_STATUS,
    MODEL_A_IDENTITY,
    PROSPECTIVE_POLICY_VERSION,
    EvaluationDailyEvidence,
    EvaluationEvidence,
    WeatherDiagnosticRow,
    _summarize_group,
    build_assessment,
    build_prospective_eligibility,
    compute_weather_diagnostic,
    weather_snapshot_is_pit_eligible,
)

NOW = datetime(2026, 9, 20, 8, 0, tzinfo=UTC)
BASE_ID = "base_000000000000000000000001"
SEASON = "2026-2027"


class Snapshot:
    forecast_run_id = "forecast-s4-1"
    base_id = BASE_ID
    target_season = SEASON
    forecast_created_at = NOW
    created_at = NOW + timedelta(seconds=1)
    forecast_mode = "SHADOW"
    input_snapshot_hash = "a" * 64
    result_hash = "b" * 64
    area_revision_id = "area-s4-1"
    prior_history_season = "2025-2026"
    prior_history_source_hash = "c" * 64
    prior_history_identity_mapping_hash = "d" * 64
    weather_snapshot_ids = ["weather-s4-1"]
    phenology_observation_ids: list[str] = []


class Weather:
    weather_snapshot_id = "weather-s4-1"
    provider = "ECMWF_IFS_OPEN_DATA"
    base_id = BASE_ID
    issued_at = NOW - timedelta(hours=2)
    fetched_at = NOW - timedelta(hours=1)
    known_at = NOW - timedelta(minutes=30)
    payload_hash = "f" * 64


class Area:
    area_revision_id = "area-s4-1"
    base_id = BASE_ID
    season = SEASON
    area_type = "ACTUAL_PRODUCTIVE_AREA"
    known_at = NOW - timedelta(days=1)
    effective_from = NOW - timedelta(days=30)
    effective_to = None


def _actual(
    *,
    offset: int = 1,
    observed_at: datetime = NOW + timedelta(days=1),
    known_at: datetime = NOW + timedelta(days=2),
) -> ActualDailyRecord:
    return ActualDailyRecord(
        base_id=BASE_ID,
        target_season=SEASON,
        harvest_date=date(2026, 10, 1) + timedelta(days=offset),
        quantity_kg=Decimal("10"),
        source="fixture-authority",
        revision_id=f"actual-{offset}#1",
        source_hash="e" * 64,
        known_at=known_at,
        observed_at=observed_at,
        recorded_at=observed_at,
        authority_id="actual-authority-s4",
    )


def _application_fixture_models(
    *,
    phenology_base_id: str = BASE_ID,
    phenology_season: str = SEASON,
    phenology_known_at: datetime = NOW - timedelta(hours=3),
) -> tuple[
    ForecastRunSnapshot,
    AreaRevision,
    WeatherForecastSnapshot,
    PhenologyObservation,
    ForecastEvaluation,
    list[ForecastEvaluationDaily],
]:
    run_id = "forecast-s4-application"
    area_id = "area-s4-application"
    weather_id = "weather-s4-application"
    observation_id = "phenology-s4-application"
    evaluation_id = "evaluation-s4-application"
    forecast_date_1 = date(2026, 10, 1)
    forecast_date_2 = date(2026, 10, 2)
    evaluation_metrics = {
        "wape": {
            "status": "COMPUTABLE",
            "value": "0.500000",
            "comparable_row_count": 2,
        },
        "bias_kg": {
            "status": "COMPUTABLE",
            "value": "5.000000",
            "comparable_row_count": 2,
        },
        "predicted_total_kg": {
            "status": "COMPUTABLE",
            "value": "30.000000",
            "comparable_row_count": 2,
        },
        "actual_total_kg": {
            "status": "COMPUTABLE",
            "value": "20.000000",
            "comparable_row_count": 2,
        },
    }
    snapshot = ForecastRunSnapshot(
        forecast_run_id=run_id,
        forecast_created_at=NOW,
        base_id=BASE_ID,
        target_season=SEASON,
        forecast_start_date=forecast_date_1,
        forecast_end_date=forecast_date_2,
        target_area_mu=Decimal("100"),
        forecast_mode="SHADOW",
        model_status="EXPERIMENTAL",
        total_model_id="BASE_AWARE_BASELINE_R1",
        temporal_model_id="AREA_DAILY_RIDGE_V1_FROZEN_REFERENCE",
        model_artifact_hashes={"total": "1" * 64, "temporal": "2" * 64},
        prior_history_season="2025-2026",
        prior_history_quantity_kg=Decimal("100"),
        prior_history_coverage_status="INCOMPLETE",
        prior_history_source_hash="3" * 64,
        prior_history_identity_mapping_hash="4" * 64,
        area_revision_id=area_id,
        weather_snapshot_ids=[weather_id],
        phenology_observation_ids=[observation_id],
        input_snapshot_json={"fixture": "s4-application"},
        input_snapshot_hash="5" * 64,
        predicted_season_total_kg=Decimal("30"),
        single_day_peak={"date": forecast_date_1.isoformat(), "quantity_kg": "15"},
        rolling_7day_peak={"status": "NOT_COMPUTABLE"},
        result_hash="6" * 64,
        warnings=["PRIOR_SEASON_HISTORY_COVERAGE_INCOMPLETE"],
        daily_row_count=2,
        created_at=NOW + timedelta(seconds=1),
    )
    area = AreaRevision(
        area_revision_id=area_id,
        base_id=BASE_ID,
        season=SEASON,
        area_mu=Decimal("100"),
        area_type="REFERENCE_AREA",
        effective_from=NOW - timedelta(days=30),
        effective_to=None,
        recorded_at=NOW - timedelta(days=2),
        known_at=NOW - timedelta(days=1),
        source="s4-fixture",
        source_reference="s4-fixture-area",
        basis="fixture",
        payload_hash="7" * 64,
    )
    weather = WeatherForecastSnapshot(
        weather_snapshot_id=weather_id,
        provider="ECMWF_IFS_OPEN_DATA",
        base_id=BASE_ID,
        location_id=None,
        issued_at=NOW - timedelta(hours=2),
        fetched_at=NOW - timedelta(hours=1),
        known_at=NOW - timedelta(minutes=30),
        valid_at=NOW + timedelta(days=1),
        forecast_horizon_hours=24,
        temperature_min=Decimal("10"),
        temperature_max=Decimal("20"),
        temperature_mean=Decimal("15"),
        precipitation=Decimal("1"),
        relative_humidity=None,
        solar_radiation=None,
        wind_speed=None,
        raw_payload_reference="s4-fixture-weather",
        raw_payload_hash="8" * 64,
        normalized_payload_hash="9" * 64,
        payload_hash="a" * 64,
    )
    phenology = PhenologyObservation(
        observation_id=observation_id,
        base_id=phenology_base_id,
        farm_id=None,
        season=phenology_season,
        phenology_stage="FLOWERING",
        observed_at=NOW - timedelta(days=5),
        recorded_at=NOW - timedelta(days=4),
        known_at=phenology_known_at,
        source="s4-fixture",
        source_reference="s4-fixture-phenology",
        quality_status="OBSERVED",
        notes=None,
        payload_hash="b" * 64,
    )
    evaluation = ForecastEvaluation(
        evaluation_id=evaluation_id,
        forecast_run_id=run_id,
        base_id=BASE_ID,
        target_season=SEASON,
        evaluation_mode="FULL_AVAILABLE_RANGE",
        as_of_date=None,
        evaluation_created_at=NOW + timedelta(days=3),
        forecast_input_hash=snapshot.input_snapshot_hash,
        forecast_result_hash=snapshot.result_hash,
        actual_authority_ids=["actual-authority-s4"],
        actual_authority_hashes=["c" * 64],
        realized_weather_authority_ids=[],
        realized_weather_authority_hashes=[],
        evaluated_start_date=forecast_date_1,
        evaluated_end_date=forecast_date_2,
        actual_coverage_status="COMPLETE",
        season_total_metrics=evaluation_metrics,
        daily_metrics={"wape": evaluation_metrics["wape"]},
        single_day_peak_metrics={
            "status": "COMPUTABLE",
            "forecast_peak_quantity_kg": "15",
            "actual_peak_quantity_kg": "10",
            "peak_absolute_date_error_days": 1,
        },
        rolling_7day_peak_metrics={"status": "NOT_COMPUTABLE"},
        weather_metrics={
            "D1": {
                "temperature_mae": {"status": "COMPUTABLE", "value": "1"},
                "temperature_bias": {"status": "COMPUTABLE", "value": "0"},
                "precipitation_error": {"status": "COMPUTABLE", "value": "0"},
            }
        },
        warnings=[],
        evaluation_payload_json={"fixture": "s4-application"},
        evaluation_identity_hash="d" * 64,
        evaluation_payload_hash="e" * 64,
        evaluation_result_hash="f" * 64,
        daily_row_count=2,
        created_at=NOW + timedelta(days=3, seconds=1),
    )
    rows = [
        ForecastEvaluationDaily(
            evaluation_id=evaluation_id,
            row_index=0,
            evaluation_date=forecast_date_1,
            predicted_quantity_kg=Decimal("15"),
            actual_quantity_kg=Decimal("10"),
            actual_status="CONFIRMED_QUANTITY",
            actual_revision_id="actual-1#1",
            actual_source_hash="1" * 64,
            error_kg=Decimal("5"),
            absolute_error_kg=Decimal("5"),
            evaluation_as_of=None,
            row_hash=hash_payload({"fixture": "row-1"}),
        ),
        ForecastEvaluationDaily(
            evaluation_id=evaluation_id,
            row_index=1,
            evaluation_date=forecast_date_2,
            predicted_quantity_kg=Decimal("15"),
            actual_quantity_kg=Decimal("10"),
            actual_status="CONFIRMED_QUANTITY",
            actual_revision_id="actual-2#1",
            actual_source_hash="2" * 64,
            error_kg=Decimal("5"),
            absolute_error_kg=Decimal("5"),
            evaluation_as_of=None,
            row_hash=hash_payload({"fixture": "row-2"}),
        ),
    ]
    return snapshot, area, weather, phenology, evaluation, rows


def _application_actuals() -> dict[str, tuple[ActualDailyRecord, ...]]:
    return {
        "forecast-s4-application": (
            ActualDailyRecord(
                base_id=BASE_ID,
                target_season=SEASON,
                harvest_date=date(2026, 10, 1),
                quantity_kg=Decimal("10"),
                source="fixture-authority",
                revision_id="actual-1#1",
                source_hash="1" * 64,
                known_at=NOW + timedelta(days=2),
                observed_at=NOW + timedelta(days=1),
                recorded_at=NOW + timedelta(days=1),
                authority_id="actual-authority-s4",
            ),
            ActualDailyRecord(
                base_id=BASE_ID,
                target_season=SEASON,
                harvest_date=date(2026, 10, 2),
                quantity_kg=Decimal("10"),
                source="fixture-authority",
                revision_id="actual-2#1",
                source_hash="2" * 64,
                known_at=NOW + timedelta(days=2),
                observed_at=NOW + timedelta(days=1),
                recorded_at=NOW + timedelta(days=1),
                authority_id="actual-authority-s4",
            ),
        )
    }


def _upgrade_schema(connection: object) -> None:
    context = MigrationContext.configure(connection)  # type: ignore[arg-type]
    operations = Operations(context)
    for revision in (
        "0036_v06_pit_data_foundation",
        "0037_v06_pit_scope_time_integrity",
        "0038_v06_s3_forecast_actual_evaluation",
        "0039_v06_s4_prospective_validation",
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


@pytest.mark.unit
def test_true_prospective_eligibility_requires_actual_after_forecast() -> None:
    eligible = build_prospective_eligibility(
        Snapshot(),
        (_actual(),),
        evaluation_created_at=NOW + timedelta(days=3),
        actual_coverage_status="PARTIAL",
        area_revision=Area(),
        weather_snapshots=(Weather(),),
    )
    assert eligible.prospective_eligible is True
    assert eligible.ineligibility_reasons == ()
    assert eligible.first_actual_observed_at == NOW + timedelta(days=1)
    assert eligible.weather_snapshot_authority_hashes == ("f" * 64,)

    ineligible = build_prospective_eligibility(
        Snapshot(),
        (_actual(observed_at=NOW - timedelta(minutes=1)),),
        evaluation_created_at=NOW + timedelta(days=3),
        area_revision=Area(),
        weather_snapshots=(Weather(),),
    )
    assert ineligible.prospective_eligible is False
    assert "FORECAST_NOT_BEFORE_ACTUAL_OBSERVATION" in ineligible.ineligibility_reasons


@pytest.mark.unit
def test_empty_actual_and_replay_forecast_are_not_eligible() -> None:
    empty = build_prospective_eligibility(
        Snapshot(),
        (),
        evaluation_created_at=NOW + timedelta(days=3),
        weather_snapshots=(Weather(),),
    )
    assert empty.prospective_eligible is False
    assert "ACTUAL_NOT_MATURED" in empty.ineligibility_reasons

    replay = Snapshot()
    replay.forecast_mode = "REPLAY"
    result = build_prospective_eligibility(
        replay,
        (_actual(),),
        evaluation_created_at=NOW + timedelta(days=3),
        weather_snapshots=(Weather(),),
    )
    assert result.prospective_eligible is False
    assert "FORECAST_MODE_NOT_SHADOW" in result.ineligibility_reasons


@pytest.mark.unit
def test_hindsight_weather_is_rejected_and_weather_scope_is_bound() -> None:
    assert weather_snapshot_is_pit_eligible(Weather(), BASE_ID, NOW) is True

    hindsight = Weather()
    hindsight.known_at = NOW + timedelta(minutes=1)
    assert weather_snapshot_is_pit_eligible(hindsight, BASE_ID, NOW) is False

    wrong_base = Weather()
    wrong_base.base_id = "base_000000000000000000000002"
    assert weather_snapshot_is_pit_eligible(wrong_base, BASE_ID, NOW) is False


@pytest.mark.unit
def test_hindsight_area_is_rejected_and_target_season_is_bound() -> None:
    future_area = Area()
    future_area.known_at = NOW + timedelta(minutes=1)
    result = build_prospective_eligibility(
        Snapshot(),
        (_actual(),),
        evaluation_created_at=NOW + timedelta(days=3),
        area_revision=future_area,
    )
    assert result.prospective_eligible is False
    assert "HINDSIGHT_OR_UNBOUND_AREA" in result.ineligibility_reasons

    wrong_season = Area()
    wrong_season.season = "2025-2026"
    result = build_prospective_eligibility(
        Snapshot(),
        (_actual(),),
        evaluation_created_at=NOW + timedelta(days=3),
        area_revision=wrong_season,
    )
    assert result.prospective_eligible is False
    assert "AREA_REVISION_SEASON_MISMATCH" in result.ineligibility_reasons


@pytest.mark.unit
def test_weather_diagnostic_is_deterministic_and_keeps_gdd_unfrozen() -> None:
    rows = tuple(
        WeatherDiagnosticRow(
            forecast_run_id=f"run-{index}",
            base_id=BASE_ID,
            horizon_hours=24,
            temperature_signal=Decimal(index + 1),
            precipitation_signal=None if index == 2 else Decimal(index),
            timing_residual_days=Decimal(index + 1),
        )
        for index in range(4)
    )
    first = compute_weather_diagnostic(rows)
    second = compute_weather_diagnostic(tuple(reversed(rows)))
    assert first == second
    assert first["D1"]["sample_count"] == 4
    assert first["D1"]["temperature"]["pearson_correlation"] == Decimal("1")
    assert first["D1"]["precipitation"]["sample_count"] == 3
    assert first["gdd_incremental_value_status"] == GDD_INCREMENTAL_VALUE_STATUS

    d15 = compute_weather_diagnostic(
        (WeatherDiagnosticRow("run-d15", BASE_ID, 360, Decimal("2"), None, Decimal("1")),)
    )
    assert d15["D15"]["sample_count"] == 1
    no_signal = compute_weather_diagnostic(
        (WeatherDiagnosticRow("run-none", BASE_ID, 24, None, None, Decimal("1")),)
    )
    assert no_signal["weather_signal_found"] is False


@pytest.mark.unit
def test_weather_diagnostic_reports_cross_base_inconsistency() -> None:
    rows = (
        WeatherDiagnosticRow("r1", "base-a", 24, Decimal("1"), Decimal("1"), Decimal("1")),
        WeatherDiagnosticRow("r2", "base-a", 24, Decimal("2"), Decimal("2"), Decimal("2")),
        WeatherDiagnosticRow("r3", "base-b", 24, Decimal("1"), Decimal("1"), Decimal("-1")),
        WeatherDiagnosticRow("r4", "base-b", 24, Decimal("2"), Decimal("2"), Decimal("-2")),
    )
    result = compute_weather_diagnostic(rows)
    assert result["D1"]["base_count"] == 2
    assert result["D1"]["direction_consistency"] == Decimal("0.5")
    assert result["D1"]["cross_base_consistent"] is False


@pytest.mark.unit
def test_assessment_empty_real_evidence_is_explicitly_insufficient() -> None:
    computation = build_assessment(
        eligibility=(),
        evaluations=(),
        weather_diagnostic_rows=(),
        created_at=NOW,
    )
    assert computation.model_a_identity == MODEL_A_IDENTITY
    assert computation.policy_version == PROSPECTIVE_POLICY_VERSION
    assert computation.weather_incremental_value_conclusion == "INCONCLUSIVE"
    assert computation.v0_7_recommendation == "INSUFFICIENT_EVIDENCE"
    assert computation.evidence_sufficiency["eligible_forecast_run_count"] == 0
    assert computation.result_hash == computation.compute_result_hash()
    replay = build_assessment(
        eligibility=(), evaluations=(), weather_diagnostic_rows=(), created_at=NOW
    )
    assert replay.payload_hash == computation.payload_hash
    assert replay.result_hash == computation.result_hash


@pytest.mark.unit
async def test_s4_persistence_round_trip_and_immutability(sqlite_session: AsyncSession) -> None:
    from backend.app.pit.prospective_persistence import ProspectiveValidationRepository

    computation = build_assessment(
        eligibility=(), evaluations=(), weather_diagnostic_rows=(), created_at=NOW
    )
    repository = ProspectiveValidationRepository(sqlite_session)
    async with sqlite_session.begin():
        stored = await repository.save(computation)
    loaded = await repository.get_assessment(stored.validation_run_id)
    assert loaded.result_hash == computation.result_hash
    assert loaded.payload_hash == computation.payload_hash
    await sqlite_session.rollback()
    with pytest.raises(DBAPIError):
        await sqlite_session.execute(update(ProspectiveValidationRun).values(warnings=["tampered"]))
    await sqlite_session.rollback()
    with pytest.raises(DBAPIError):
        await sqlite_session.execute(
            update(WeatherIncrementalValueAssessment).values(warnings=["tampered"])
        )
    await sqlite_session.rollback()


@pytest.mark.unit
async def test_application_empty_authority_is_explicitly_insufficient(
    sqlite_session: AsyncSession,
) -> None:
    from backend.app.pit.prospective_application import (
        run_prospective_validation_assessment,
    )

    async with sqlite_session.begin():
        result = await run_prospective_validation_assessment(
            sqlite_session, evaluation_created_at=NOW
        )
    assert result.validation_run_id.startswith("prospective_validation_")
    assert result.warnings == ("INSUFFICIENT_MATURED_PIT_EVIDENCE",)
    assert result.evidence_sufficiency["eligible_forecast_run_count"] == 0


@pytest.mark.unit
async def test_application_loads_and_binds_forecast_time_phenology(
    sqlite_session: AsyncSession,
) -> None:
    from backend.app.pit.prospective_application import (
        run_prospective_validation_assessment,
    )
    from backend.app.pit.prospective_persistence import ProspectiveValidationRepository

    snapshot, area, weather, phenology, evaluation, daily_rows = _application_fixture_models()
    async with sqlite_session.begin():
        sqlite_session.add_all([snapshot, area, weather, phenology, evaluation, *daily_rows])
        await sqlite_session.flush()
        result = await run_prospective_validation_assessment(
            sqlite_session,
            evaluation_created_at=NOW + timedelta(days=3),
            actual_records_by_run=_application_actuals(),
        )

    assert result.eligibility[0].prospective_eligible is True
    assert result.eligibility[0].phenology_observation_ids == (phenology.observation_id,)
    assert result.baseline_metrics["COVERAGE_LIMITED_BASES"]["eligible_base_count"] == 1
    assert (
        result.sample_scope["stable_history_cohort"]["status"]
        == "NOT_COMPUTABLE_NO_FROZEN_COHORT_AUTHORITY"
    )
    pooled_daily = result.baseline_metrics["ALL_ELIGIBLE_BASES"]["metrics"]["daily_wape"]
    assert pooled_daily["aggregation"] == "POOLED_ABSOLUTE_DAILY_ERROR_OVER_ABSOLUTE_ACTUAL"
    assert pooled_daily["value"] == Decimal("0.5")

    stored = await ProspectiveValidationRepository(sqlite_session).get_assessment(
        result.validation_run_id
    )
    assert stored.result_hash == result.result_hash
    assert stored.payload_hash == result.payload_hash


@pytest.mark.unit
@pytest.mark.parametrize(
    ("phenology_base_id", "phenology_season", "phenology_known_at"),
    (
        ("base_wrong", SEASON, NOW - timedelta(hours=3)),
        (BASE_ID, "2025-2026", NOW - timedelta(hours=3)),
        (BASE_ID, SEASON, NOW + timedelta(minutes=1)),
    ),
)
async def test_application_rejects_unbound_or_hindsight_phenology(
    sqlite_session: AsyncSession,
    phenology_base_id: str,
    phenology_season: str,
    phenology_known_at: datetime,
) -> None:
    from backend.app.pit.prospective_application import (
        run_prospective_validation_assessment,
    )

    snapshot, area, weather, phenology, evaluation, daily_rows = _application_fixture_models(
        phenology_base_id=phenology_base_id,
        phenology_season=phenology_season,
        phenology_known_at=phenology_known_at,
    )
    async with sqlite_session.begin():
        sqlite_session.add_all([snapshot, area, weather, phenology, evaluation, *daily_rows])
        await sqlite_session.flush()
        result = await run_prospective_validation_assessment(
            sqlite_session,
            evaluation_created_at=NOW + timedelta(days=3),
            actual_records_by_run=_application_actuals(),
        )

    eligibility = result.eligibility[0]
    assert eligibility.prospective_eligible is False
    assert "HINDSIGHT_OR_SCOPE_MISMATCH_PHENOLOGY" in eligibility.ineligibility_reasons


@pytest.mark.unit
async def test_application_missing_phenology_reference_fails_closed(
    sqlite_session: AsyncSession,
) -> None:
    from backend.app.pit.prospective_application import (
        run_prospective_validation_assessment,
    )

    snapshot, area, weather, _phenology, evaluation, daily_rows = _application_fixture_models()
    async with sqlite_session.begin():
        sqlite_session.add_all([snapshot, area, weather, evaluation, *daily_rows])
        await sqlite_session.flush()
        result = await run_prospective_validation_assessment(
            sqlite_session,
            evaluation_created_at=NOW + timedelta(days=3),
            actual_records_by_run=_application_actuals(),
        )

    assert result.eligibility[0].prospective_eligible is False
    assert "HINDSIGHT_OR_SCOPE_MISMATCH_PHENOLOGY" in result.eligibility[0].ineligibility_reasons


@pytest.mark.unit
def test_cohort_caller_cannot_supply_unfrozen_stable_history_membership() -> None:
    with pytest.raises(ValueError, match="STABLE_HISTORY_COHORT_AUTHORITY_REQUIRED"):
        build_assessment(
            eligibility=(),
            evaluations=(),
            weather_diagnostic_rows=(),
            created_at=NOW,
            stable_history_base_ids=(BASE_ID,),
        )


@pytest.mark.unit
def test_cohort_wape_uses_pooled_numerator_and_denominator() -> None:
    def evidence(
        evaluation_id: str,
        base_id: str,
        predicted_total: str,
        actual_total: str,
    ) -> EvaluationEvidence:
        predicted = Decimal(predicted_total)
        actual = Decimal(actual_total)
        error = predicted - actual
        return EvaluationEvidence(
            evaluation_id=evaluation_id,
            forecast_run_id=f"run-{evaluation_id}",
            base_id=base_id,
            actual_coverage_status="COMPLETE",
            season_total_metrics={
                "predicted_total_kg": {
                    "status": "COMPUTABLE",
                    "value": predicted,
                },
                "actual_total_kg": {
                    "status": "COMPUTABLE",
                    "value": actual,
                },
            },
            daily_metrics={},
            single_day_peak_metrics={"status": "NOT_COMPUTABLE"},
            rolling_7day_peak_metrics={"status": "NOT_COMPUTABLE"},
            weather_metrics={},
            daily_rows=(
                EvaluationDailyEvidence(
                    evaluation_date=date(2026, 10, 1),
                    predicted_quantity_kg=predicted,
                    actual_quantity_kg=actual,
                    actual_status="CONFIRMED_QUANTITY",
                    error_kg=error,
                    absolute_error_kg=abs(error),
                ),
            ),
        )

    result = _summarize_group(
        (
            evidence("one", "base-one", "20", "10"),
            evidence("two", "base-two", "110", "100"),
        )
    )
    # Macro mean is (1.0 + 0.1) / 2 = 0.55; pooled WAPE is 20 / 110.
    assert result["metrics"]["season_total_wape"]["value"] == Decimal(20) / Decimal(110)
    assert result["metrics"]["daily_wape"]["value"] == Decimal(20) / Decimal(110)
    assert result["metrics"]["season_total_wape"]["aggregation"].startswith("POOLED_")


@pytest.mark.migration
def test_s4_migration_round_trip_and_single_revision() -> None:
    migration = importlib.import_module(
        "backend.alembic.versions.0039_v06_s4_prospective_validation"
    )
    assert migration.revision == "0039_v06_s4_prospective_validation"
    assert migration.down_revision == "0038_v06_s3_forecast_actual_evaluation"
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
            migration,
        ]
        for module in modules:
            module.op = operations
            module.upgrade()
        migration.downgrade()
        migration.upgrade()
        assert connection.execute(select(ProspectiveValidationRun)).first() is None
    engine.dispose()
