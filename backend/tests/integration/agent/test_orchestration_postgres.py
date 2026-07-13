"""Real PostgreSQL session evidence for the Slice B orchestration boundary."""

import os
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agent.orchestration import AgentOrchestrator, StaticSeasonCalendarPolicy
from backend.app.agent.schemas import LocationInput, PeakMetricPolicy, UncertaintyWideningPolicy
from backend.app.models.master_data import Factory, Farm, Season, Variety
from backend.app.models.maturity import MaturityForecastRun, MaturityModelArtifact, MaturityModelRun
from backend.app.models.planning import LocationReference
from backend.app.models.production_plan import FarmSeasonVarietyPlan
from backend.tests.agent.test_orchestration import _request
from backend.tests.agent.test_production_wiring import (
    _add_pool_row,
    _add_residual_prediction_row,
    _add_residual_prediction_run,
    _build_harvest_state_run,
    _hash,
)


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

    location = LocationReference(
        id=601,
        address_normalized="云南省红河州弥勒市西三镇",
        address_raw="云南省红河州弥勒市西三镇",
        latitude=Decimal("24.400000"),
        longitude=Decimal("103.400000"),
        altitude_m=Decimal("1800"),
        farm_name="slice-b-farm",
        location_source="slice-b-fixture",
        source_version="slice-b-v1",
        valid_from=date(2020, 1, 1),
        source_row_hash=_hash("slice-b-location"),
    )
    farm = Farm(id=1, name="slice-b-farm")
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
    transactional_pg_session.add_all([location, farm, season, variety, factory, plan, model_run])
    await transactional_pg_session.flush()
    transactional_pg_session.add(artifact)
    await transactional_pg_session.flush()
    transactional_pg_session.add(forecast)
    await transactional_pg_session.flush()

    task9 = _build_harvest_state_run(
        transactional_pg_session,
        run_id=9009,
        as_of_date=date(2026, 3, 1),
        forecast_start=date(2026, 3, 1),
        forecast_end=date(2026, 3, 3),
        destination_factory_id=601,
        maturity_forecast_run_id=9008,
        pool_row_count=9,
        input_snapshot={"forecast_season": 2026},
    )
    await transactional_pg_session.flush()
    for day in (date(2026, 3, 1), date(2026, 3, 2), date(2026, 3, 3)):
        for quantile in ("P50", "P80", "P90"):
            _add_pool_row(
                transactional_pg_session,
                harvest_state_run_id=task9.id,
                state_date=day,
                quantile=quantile,
                capacity_pool_id=1,
                harvested_kg=Decimal("100"),
                arrival_kg=Decimal("100"),
                natural_kg=Decimal("100"),
                closing_kg=Decimal("0"),
                backlog_kg=Decimal("0"),
            )
    task10 = _add_residual_prediction_run(
        transactional_pg_session,
        prediction_run_id=9010,
        task9_run_id=task9.id,
        task9_result_hash=task9.result_hash,
    )
    for day in (date(2026, 3, 1), date(2026, 3, 2), date(2026, 3, 3)):
        _add_residual_prediction_row(
            transactional_pg_session,
            prediction_run_id=task10.id,
            arrival_local_date=day,
            destination_factory_id=601,
            corrected_p50=Decimal("100"),
            corrected_p80=Decimal("110"),
            corrected_p90=Decimal("120"),
            task9_run_id=task9.id,
            task9_result_hash=task9.result_hash,
        )
    await transactional_pg_session.flush()

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
    blocker_codes = {blocker.code.value for blocker in output.blockers}
    assert "INTERNAL_FAILURE" not in blocker_codes
    assert output.provenance["task8_authority"]["maturity_forecast_run_id"] == 9008
    assert output.provenance["task9_authority"]["harvest_state_run_id"] == 9009
    assert output.provenance["task10_authority"]["prediction_run_id"] == 9010
    assert (
        output.provenance["task9_authority"]["harvest_state_run_result_hash"] == task9.result_hash
    )
    assert output.provenance["task10_authority"]["task9_result_hash"] == task9.result_hash
    assert output.normalized_request.canonical_request_hash != "0" * 64
    assert len(output.provenance["agent_forecast_output_hash"]) == 64
