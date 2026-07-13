"""Real PostgreSQL session evidence for the Slice B orchestration boundary."""

import os
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agent.orchestration import AgentOrchestrator, StaticSeasonCalendarPolicy
from backend.app.agent.schemas import LocationInput, PeakMetricPolicy, UncertaintyWideningPolicy
from backend.app.harvest_state.persistence import (
    load_harvest_state_output_by_id,
    save_harvest_state_output,
)
from backend.app.harvest_state.service import run_harvest_state_model
from backend.app.models.harvest_state import HarvestStateRun
from backend.app.models.master_data import Factory, Farm, Season, Subfarm, Variety
from backend.app.models.maturity import MaturityForecastRun, MaturityModelArtifact, MaturityModelRun
from backend.app.models.planning import AgroClimateZone, LocationReference
from backend.app.models.production_plan import FarmSeasonVarietyPlan
from backend.app.residual_model.persistence import (
    load_residual_prediction_run_by_id,
    save_residual_prediction_run,
)
from backend.app.residual_model.service import structural_only_prediction
from backend.tests.agent.test_orchestration import _request
from backend.tests.agent.test_production_wiring import (
    _hash,
)
from backend.tests.harvest_state.conftest import make_request


async def _seed_valid_task9(
    session: AsyncSession,
    *,
    model_run: MaturityModelRun,
    artifact: MaturityModelArtifact,
    forecast: MaturityForecastRun,
) -> HarvestStateRun:
    """Generate and persist Task 9 through its public production entrypoint."""
    request = make_request()
    request["destination_factory_id"] = 601
    for prediction in request["task8_daily_predictions"]:
        source_ref = prediction["source_ref"]
        verification = prediction["verification_snapshot"]
        source_ref.update(
            {
                "maturity_model_run_id": model_run.id,
                "maturity_model_version": model_run.model_version,
                "maturity_model_config_hash": model_run.config_hash,
                "maturity_model_source_signature": model_run.source_signature,
                "maturity_model_artifact_id": artifact.id,
                "maturity_model_artifact_hash": artifact.artifact_hash,
                "maturity_forecast_run_id": forecast.id,
                "maturity_forecast_source_signature": forecast.source_signature,
                "maturity_forecast_as_of_date": forecast.as_of_date,
                "plan_id": forecast.plan_id,
                "location_reference_id": forecast.location_reference_id,
            }
        )
        verification.update(
            {
                "maturity_model_run_id": model_run.id,
                "maturity_model_version": model_run.model_version,
                "maturity_model_config_hash": model_run.config_hash,
                "maturity_model_source_signature": model_run.source_signature,
                "maturity_model_artifact_id": artifact.id,
                "maturity_model_artifact_run_id": model_run.id,
                "maturity_model_artifact_hash": artifact.artifact_hash,
                "maturity_forecast_run_id": forecast.id,
                "maturity_forecast_model_run_id": model_run.id,
                "maturity_forecast_artifact_id": artifact.id,
                "maturity_forecast_source_signature": forecast.source_signature,
                "maturity_forecast_as_of_date": forecast.as_of_date,
                "maturity_forecast_prediction_start_date": forecast.prediction_start_date,
                "maturity_forecast_prediction_end_date": forecast.prediction_end_date,
                "maturity_daily_prediction_forecast_run_id": forecast.id,
                "plan_id": forecast.plan_id,
                "location_reference_id": forecast.location_reference_id,
            }
        )
    output = run_harvest_state_model(request)
    assert output.status == "completed"
    return await save_harvest_state_output(session, output=output)


@pytest.mark.postgres
@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
    reason="set RUN_POSTGRES_INTEGRATION=1 for real PostgreSQL evidence",
)
async def test_slice_b_orchestration_uses_real_postgres_session(
    transactional_pg_session: AsyncSession,
) -> None:
    result = await transactional_pg_session.execute(text("SELECT 1"))
    assert result.scalar_one() == 1

    zone = AgroClimateZone(
        id=1601,
        code="slice-b-zone",
        name="Slice B Zone",
        country="CN",
        province="云南省",
        prefecture="红河州",
        county="弥勒市",
        centroid_latitude=Decimal("24.400000"),
        centroid_longitude=Decimal("103.400000"),
        min_altitude_m=Decimal("1700"),
        max_altitude_m=Decimal("1900"),
        zone_version="slice-b-v1",
        valid_from=date(2020, 1, 1),
        source_name="slice-b-fixture",
        source_version="slice-b-v1",
    )
    location = LocationReference(
        id=601,
        address_normalized="云南省红河州弥勒市西三镇",
        address_raw="云南省红河州弥勒市西三镇",
        latitude=Decimal("24.400000"),
        longitude=Decimal("103.400000"),
        altitude_m=Decimal("1800"),
        farm_name="slice-b-farm",
        province="云南省",
        prefecture="红河州",
        county="弥勒市",
        climate_zone_id=1601,
        location_source="slice-b-fixture",
        source_version="slice-b-v1",
        valid_from=date(2020, 1, 1),
        source_row_hash=_hash("slice-b-location"),
    )
    farm = Farm(id=1, name="slice-b-farm")
    subfarm = Subfarm(id=1, farm_id=1, name="slice-b-subfarm")
    season = Season(id=1, code="2026", start_date=date(2026, 1, 1), end_date=date(2026, 4, 30))
    variety = Variety(id=101, code="101", name="slice-b-variety")
    factory = Factory(id=601, name="slice-b-factory")
    plan = FarmSeasonVarietyPlan(
        id=1,
        farm_id=1,
        season_id=1,
        variety_id=101,
        planted_area_mu=Decimal("100.000000"),
        expected_yield_kg_per_mu=Decimal("100.000000"),
        marketable_rate=Decimal("0.9000000000"),
        version=1,
        effective_from=date(2026, 1, 1),
        available_at=date(2026, 1, 1),
        source_type="slice-b-fixture",
        row_hash=_hash("slice-b-plan"),
    )
    model_run = MaturityModelRun(
        id=1,
        model_version="slice-b-maturity/v1",
        config_hash=_hash("slice-b-model-config"),
        config_snapshot={},
        training_cutoff=date(2025, 12, 31),
        source_signature=_hash("slice-b-model-source"),
        status="completed",
        random_seed=1,
        model_family="slice-b",
        scope="slice-b",
        sample_count=1,
        distinct_season_count=1,
        distinct_farm_count=1,
        distinct_subfarm_count=0,
        training_metrics={},
        calibration_metrics={},
        warnings=[],
        blockers=[],
        input_snapshot={},
    )
    artifact = MaturityModelArtifact(
        id=1,
        run_id=1,
        artifact_hash=_hash("slice-b-artifact"),
        support_min_day=1,
        support_max_day=120,
        artifact_payload={},
    )
    forecast = MaturityForecastRun(
        id=9008,
        model_run_id=1,
        artifact_id=1,
        plan_id=1,
        location_reference_id=601,
        as_of_date=date(2026, 3, 1),
        prediction_start_date=date(2026, 3, 1),
        prediction_end_date=date(2026, 3, 3),
        expected_marketable_total_kg=Decimal("300.000000"),
        expected_total_source="slice-b-fixture",
        axis_mode="calendar_proxy_axis",
        source_signature=_hash("slice-b-forecast-source"),
        status="completed",
        warnings=[],
        blockers=[],
        input_snapshot={},
    )
    transactional_pg_session.add_all(
        [zone, farm, subfarm, season, variety, factory, plan, model_run]
    )
    await transactional_pg_session.flush()
    transactional_pg_session.add(location)
    await transactional_pg_session.flush()
    transactional_pg_session.add(artifact)
    await transactional_pg_session.flush()
    transactional_pg_session.add(forecast)
    await transactional_pg_session.flush()

    task9 = await _seed_valid_task9(
        transactional_pg_session,
        model_run=model_run,
        artifact=artifact,
        forecast=forecast,
    )
    task10_result = structural_only_prediction(
        model_run_id=None,
        task9_run_id=task9.id,
        task9_result_hash=task9.result_hash,
        config_hash=_hash("slice-b-task10-config"),
        structural_rows=[
            {
                "destination_factory_id": 601,
                "arrival_local_date": day,
                "forecast_horizon_days": 1,
                "structural_p50_kg": Decimal("100"),
                "structural_p80_kg": Decimal("110"),
                "structural_p90_kg": Decimal("120"),
            }
            for day in (date(2026, 3, 1), date(2026, 3, 2), date(2026, 3, 3))
        ],
        fallback_reason="slice_b_fixture_structural_only",
    )
    task10 = await save_residual_prediction_run(
        transactional_pg_session,
        result=task10_result,
        feature_schema_version="task10-features-v1",
        feature_schema_hash=task10_result.input_snapshot["feature_schema_hash"],
        artifact_hashes=[],
    )
    persisted_task9 = await load_harvest_state_output_by_id(
        transactional_pg_session,
        run_id=task9.id,
    )
    persisted_task10 = await load_residual_prediction_run_by_id(
        transactional_pg_session,
        run_id=task10.id,
    )
    assert persisted_task9 is not None
    assert persisted_task10 is not None
    assert task9.destination_factory_id == 601
    assert task9.maturity_model_run_id == model_run.id
    assert task9.maturity_model_artifact_id == artifact.id
    assert task9.maturity_forecast_run_id == forecast.id
    assert persisted_task10.task9_run_id == task9.id
    assert persisted_task10.task9_result_hash == task9.result_hash

    policy_source = AgentOrchestrator(
        season_calendar=StaticSeasonCalendarPolicy(),
        location_adapter=None,
        uncertainty_widening_policy=UncertaintyWideningPolicy(
            policy_version="uncertainty-widening/v1",
            config_hash="0" * 64,
            factors_by_source_level={
                "step_1_same_farm_same_variety_high_evidence": "1.000",
                "step_2_same_township_similar_altitude": "1.250",
                "step_3_same_county_same_climate_zone": "1.500",
                "step_4_province_level_same_variety": "1.750",
                "step_5_variety_document_prior_only": "2.000",
            },
        ),
        peak_metric_policy=PeakMetricPolicy(
            policy_version="peak-metric/v1",
            policy_config_hash="0" * 64,
            sustained_window_days=3,
            peak_window_days_before=7,
            peak_window_days_after=7,
            high_load_threshold_ratio="0.900",
        ),
    )
    request = _request().model_copy(
        update={
            "location": LocationInput(location_reference_id=601),
            "requested_as_of_date": date(2026, 3, 1),
            "requested_forecast_season": 2026,
            "varieties": [_request().varieties[0].model_copy(update={"variety_id": "101"})],
        }
    )
    output = await policy_source.execute(
        transactional_pg_session,
        request=request,
        request_received_at=datetime(2026, 3, 1, tzinfo=UTC),
    )
    assert output.request_status == "BLOCKED"
    assert output.normalized_request.normalized_location.status == "resolved"
    assert output.normalized_request.normalized_location.location_reference_id == 601
    assert output.normalized_request.normalized_location.climate_zone_id == 1601
    blocker_codes = {blocker.code.value for blocker in output.blockers}
    assert "INTERNAL_FAILURE" not in blocker_codes
    assert blocker_codes == {
        "AUTHORITY_SCOPE_MISMATCH",
        "EMPTY_CURVE",
        "INSUFFICIENT_HISTORY",
        "NO_PERSISTED_PRIOR_SOURCE",
        "SPRING_FESTIVAL_CALENDAR_POLICY_MISSING",
        "TASK10_AUTHORITY_NOT_FOUND",
    }
    scope_blocker = next(
        blocker for blocker in output.blockers if blocker.code.value == "AUTHORITY_SCOPE_MISMATCH"
    )
    assert scope_blocker.details["reason"] == "PERSISTED_FORECAST_SEASON_IDENTITY_UNAVAILABLE"
    assert scope_blocker.details["row_id"] == task9.id
    assert output.provenance["task8_authority"] is None
    assert output.provenance["task9_authority"] is None
    assert output.provenance["task10_authority"] is None
    assert output.normalized_request.canonical_request_hash != "0" * 64
    assert len(output.provenance["agent_forecast_output_hash"]) == 64
