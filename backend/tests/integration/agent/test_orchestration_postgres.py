"""Real PostgreSQL session evidence for the Slice B orchestration boundary."""

import os
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agent.orchestration import AgentOrchestrator
from backend.app.agent.schemas import (
    AgentForecastOutput,
    LocationInput,
    PeakMetricPolicy,
    UncertaintyWideningPolicy,
)
from backend.app.harvest_state.canonical import make_season_record_hash
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
from backend.app.residual_model.config import load_residual_model_config
from backend.app.residual_model.persistence import (
    load_residual_prediction_run_by_id,
    save_residual_prediction_run,
    save_residual_training_run,
)
from backend.app.residual_model.service import (
    finalize_prediction_result,
    structural_only_prediction,
    train_residual_model_from_manifest,
)
from backend.tests.agent.test_orchestration import _request
from backend.tests.agent.test_production_wiring import (
    _hash,
)
from backend.tests.harvest_state.conftest import make_request
from backend.tests.residual_model.support import residual_model_config_path


async def _seed_valid_task9(
    session: AsyncSession,
    *,
    model_run: MaturityModelRun,
    artifact: MaturityModelArtifact,
    forecast: MaturityForecastRun,
    season: Season,
) -> HarvestStateRun:
    """Generate and persist Task 9 through its public production entrypoint."""
    request = make_request(destination_factory_id=601)
    request["forecast_season_identity"] = {
        "season_id": season.id,
        "season_code": season.code,
        "start_date": season.start_date,
        "end_date": season.end_date,
        "season_record_hash": make_season_record_hash(
            season_id=season.id,
            season_code=season.code,
            start_date=season.start_date,
            end_date=season.end_date,
        ),
    }
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
                "season_id": season.id,
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


async def _seed_valid_task10(
    session: AsyncSession,
    *,
    task9: HarvestStateRun,
    persisted_task9: object,
) -> object:
    training_result = train_residual_model_from_manifest(
        rows=[],
        config=load_residual_model_config(residual_model_config_path()),
    )
    training_run = await save_residual_training_run(
        session,
        result=training_result,
        manifest_rows=[],
    )
    rows_by_date: dict[date, dict[str, Decimal]] = {}
    for row in persisted_task9.daily_pool_state_rows:
        rows_by_date.setdefault(row.state_date, {})[row.forecast_quantile] = Decimal(
            row.arrival_quantity_kg
        )
    structural_rows = [
        {
            "destination_factory_id": task9.destination_factory_id,
            "arrival_local_date": row_date,
            "forecast_horizon_days": (row_date - task9.as_of_date).days,
            "structural_p50_kg": quantiles["P50"],
            "structural_p80_kg": quantiles["P80"],
            "structural_p90_kg": quantiles["P90"],
        }
        for row_date, quantiles in sorted(rows_by_date.items())
    ]
    structural_prediction = structural_only_prediction(
        model_run_id=training_run.id,
        task9_run_id=task9.id,
        task9_result_hash=task9.result_hash,
        config_hash=training_run.config_hash,
        structural_rows=structural_rows,
        fallback_reason="fixture_structural_seed",
        input_snapshot={
            "task9_run_id": task9.id,
            "task9_result_hash": task9.result_hash,
            "structural_row_count": len(structural_rows),
            "model_run_id": training_run.id,
            "training_signature": training_run.training_signature,
            "feature_analytics_build_run_id": None,
            "feature_actual_snapshot": None,
            "supplemental_feature_values": [],
            "feature_audit_hashes": [],
            "feature_rows": [],
            "artifact_hashes": [],
            "feature_schema_version": training_run.feature_schema_version,
            "feature_schema_hash": training_run.feature_schema_hash,
            "projection_version": "task10-projection-v1",
            "fallback_policy": "structural_only_fallback",
        },
    )
    prediction = finalize_prediction_result(
        execution_status="completed",
        mode="residual_corrected",
        model_run_id=training_run.id,
        task9_run_id=task9.id,
        task9_result_hash=task9.result_hash,
        config_hash=training_run.config_hash,
        warnings=(),
        blockers=(),
        fallback_reason=None,
        row_payloads=[
            {
                **row.model_dump(mode="python", exclude={"prediction_hash"}),
                "mode": "residual_corrected",
                "fallback_reason": None,
            }
            for row in structural_prediction.rows
        ],
        input_snapshot=structural_prediction.input_snapshot,
    )
    run = await save_residual_prediction_run(
        session,
        result=prediction,
        feature_schema_version=training_run.feature_schema_version,
        feature_schema_hash=training_run.feature_schema_hash,
        artifact_hashes=[],
    )
    loaded = await load_residual_prediction_run_by_id(session, run_id=run.id)
    assert loaded is not None
    assert loaded.task9_run_id == task9.id
    assert loaded.task9_result_hash == task9.result_hash
    return run


def _production_orchestrator(*, season_resolver=None) -> AgentOrchestrator:
    return AgentOrchestrator(
        season_resolver=season_resolver,
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


def _production_request():
    return _request().model_copy(
        update={
            "location": LocationInput(location_reference_id=601),
            "requested_as_of_date": date(2026, 3, 1),
            "requested_forecast_season": 2026,
            "varieties": [
                _request().varieties[0].model_copy(update={"variety_id": "101"}),
                _request().varieties[0].model_copy(update={"variety_id": "102"}),
            ],
        }
    )


async def _production_postgres_outputs(
    transactional_pg_session: AsyncSession,
) -> tuple[AgentForecastOutput, AgentForecastOutput, AgentForecastOutput]:
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
    second_variety = Variety(id=102, code="102", name="slice-b-variety-2")
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
        as_of_date=date(2026, 2, 28),
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
        [zone, farm, subfarm, season, variety, second_variety, factory, plan, model_run]
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
        season=season,
    )
    persisted_task9 = await load_harvest_state_output_by_id(
        transactional_pg_session,
        run_id=task9.id,
    )
    assert persisted_task9 is not None
    assert task9.destination_factory_id == 601
    assert task9.maturity_model_run_id == model_run.id
    assert task9.maturity_model_artifact_id == artifact.id
    assert task9.maturity_forecast_run_id == forecast.id
    assert task9.forecast_season_id == season.id
    task10 = await _seed_valid_task10(
        transactional_pg_session,
        task9=task9,
        persisted_task9=persisted_task9,
    )

    policy_source = _production_orchestrator()
    request = _production_request()
    output = await policy_source.execute(
        transactional_pg_session,
        request=request,
        request_received_at=datetime(2026, 3, 1, tzinfo=UTC),
    )
    assert output.request_status == "BLOCKED"
    assert output.normalized_request.normalized_location.status == "resolved"
    assert output.normalized_request.normalized_location.location_reference_id == 601
    assert output.normalized_request.normalized_location.climate_zone_id == 1601
    assert output.normalized_request.effective_forecast_season_id == 1
    assert output.normalized_request.effective_forecast_season_code == "2026"
    blocker_codes = {blocker.code.value for blocker in output.blockers}
    assert "INTERNAL_FAILURE" not in blocker_codes
    assert "PERSISTED_FORECAST_SEASON_IDENTITY_UNAVAILABLE" not in {
        (blocker.details or {}).get("reason") for blocker in output.blockers
    }
    assert "TASK9_AUTHORITY_NOT_FOUND" not in blocker_codes
    assert "TASK10_AUTHORITY_NOT_FOUND" not in blocker_codes
    assert blocker_codes == {
        "INSUFFICIENT_HISTORY",
        "NO_PERSISTED_PRIOR_SOURCE",
        "SPRING_FESTIVAL_CALENDAR_POLICY_MISSING",
    }
    assert output.provenance["task8_authority"] is not None
    assert output.provenance["task9_authority"] is not None
    assert output.provenance["task10_authority"] is not None
    assert output.provenance["task9_authority"]["forecast_season_id"] == season.id
    assert output.provenance["task9_authority"]["harvest_state_run_id"] == task9.id
    assert output.provenance["task10_authority"]["prediction_run_id"] == task10.id
    assert output.provenance["task10_authority"]["task9_run_id"] == task9.id
    assert output.provenance["task10_authority"]["task9_result_hash"] == task9.result_hash
    assert output.daily_curve
    assert output.peak
    assert output.normalized_request.canonical_request_hash != "0" * 64
    assert len(output.provenance["agent_forecast_output_hash"]) == 64

    no_token_output = await policy_source.execute(
        transactional_pg_session,
        request=request.model_copy(update={"requested_forecast_season": None}),
        request_received_at=datetime(2026, 3, 1, tzinfo=UTC),
    )
    assert no_token_output.normalized_request.effective_forecast_season_id == season.id
    assert no_token_output.normalized_request.effective_forecast_season_code == season.code
    assert no_token_output.daily_curve
    assert no_token_output.peak

    repeated_output = await policy_source.execute(
        transactional_pg_session,
        request=request,
        request_received_at=datetime(2026, 3, 1, tzinfo=UTC),
    )
    return output, repeated_output, no_token_output


@pytest.mark.postgres
@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
    reason="set RUN_POSTGRES_INTEGRATION=1 for real PostgreSQL evidence",
)
async def test_slice_b_orchestration_uses_real_postgres_session(
    transactional_pg_session: AsyncSession,
) -> None:
    await _production_postgres_outputs(transactional_pg_session)
