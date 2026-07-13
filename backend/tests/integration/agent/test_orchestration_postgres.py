"""Real PostgreSQL session evidence for the Slice B orchestration boundary."""

import os
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import cast

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agent.orchestration import AgentOrchestrator, StaticSeasonCalendarPolicy
from backend.app.agent.schemas import LocationInput, PeakMetricPolicy, UncertaintyWideningPolicy
from backend.app.harvest_state.canonical import canonical_json_value, sha256_hex
from backend.app.harvest_state.persistence import (
    _canonical_output_storage_payload,
    _extract_task8_identity,
    _subfarm_identity_key,
)
from backend.app.harvest_state.service import run_harvest_state_model
from backend.app.models.harvest_state import (
    HarvestStateCohortTransitionRowModel,
    HarvestStateDailyMemberRowModel,
    HarvestStateDailyPoolRowModel,
    HarvestStateFutureArrivalRowModel,
    HarvestStateRun,
)
from backend.app.models.master_data import Factory, Farm, Season, Subfarm, Variety
from backend.app.models.maturity import MaturityForecastRun, MaturityModelArtifact, MaturityModelRun
from backend.app.models.planning import AgroClimateZone, LocationReference
from backend.app.models.production_plan import FarmSeasonVarietyPlan
from backend.app.residual_model.persistence import save_residual_prediction_run
from backend.app.residual_model.service import structural_only_prediction
from backend.tests.agent.test_orchestration import _request
from backend.tests.agent.test_production_wiring import (
    _hash,
)
from backend.tests.harvest_state.conftest import make_request


async def _seed_valid_task9(session: AsyncSession) -> HarvestStateRun:
    """Persist a production-generated Task 9 output with a stable test id."""
    output = run_harvest_state_model(make_request())
    assert output.status == "completed"
    identity = _extract_task8_identity(output)
    canonical_output = _canonical_output_storage_payload(output)
    run = HarvestStateRun(
        id=9009,
        status=output.status,
        output_schema_version=output.output_schema_version,
        result_hash_schema_version="task9a-result-hash-v1",
        resolved_parameter_snapshot_schema_version="task9a-resolved-parameters-v1",
        source_ref_schema_version="task9a-source-ref-v1",
        stable_cohort_key_schema_version="task9a-cohort-key-v1",
        input_snapshot=cast(dict, canonical_json_value(output.input_snapshot)),
        resolved_parameter_snapshot=cast(
            dict,
            canonical_json_value(output.resolved_parameter_snapshot.model_dump(mode="python")),
        ),
        source_ref_catalog=cast(
            list,
            canonical_json_value(
                [item.model_dump(mode="python") for item in output.source_ref_catalog]
            ),
        ),
        warnings=list(output.warnings),
        blockers=list(output.blockers),
        mass_balance_result=cast(dict, canonical_json_value(output.mass_balance_result)),
        continuity_result=cast(dict, canonical_json_value(output.continuity_result)),
        canonical_output=canonical_output,
        config_hash=output.config_hash,
        result_hash=output.result_hash,
        canonical_payload_hash=sha256_hex(canonical_output),
        forecast_start_date=output.input_snapshot["forecast_start_date"],
        forecast_end_date=output.input_snapshot["forecast_end_date"],
        as_of_date=output.input_snapshot["as_of_date"],
        destination_factory_id=output.input_snapshot["destination_factory_id"],
        pool_row_count=len(output.daily_pool_state_rows),
        member_row_count=len(output.daily_member_state_rows),
        cohort_row_count=len(output.cohort_transition_rows),
        future_arrival_row_count=len(output.future_arrival_schedule),
        maturity_model_run_id=identity.maturity_model_run_id,
        maturity_model_version=identity.maturity_model_version,
        maturity_model_config_hash=identity.maturity_model_config_hash,
        maturity_model_source_signature=identity.maturity_model_source_signature,
        maturity_model_artifact_id=identity.maturity_model_artifact_id,
        maturity_model_artifact_hash=identity.maturity_model_artifact_hash,
        maturity_forecast_run_id=identity.maturity_forecast_run_id,
        maturity_forecast_source_signature=identity.maturity_forecast_source_signature,
    )
    session.add(run)
    await session.flush()
    catalog = {item.source_ref_hash: item.source_ref_payload for item in output.source_ref_catalog}
    membership = {
        (
            row.state_date,
            row.capacity_pool_id,
            row.forecast_quantile.value,
        ): row.capacity_pool_membership_hash
        for row in output.daily_pool_state_rows
    }
    for row in output.daily_pool_state_rows:
        session.add(
            HarvestStateDailyPoolRowModel(
                harvest_state_run_id=run.id,
                **row.model_dump(mode="python"),
            )
        )
    for row in output.daily_member_state_rows:
        session.add(
            HarvestStateDailyMemberRowModel(
                harvest_state_run_id=run.id,
                subfarm_identity_key=_subfarm_identity_key(row.subfarm_id),
                **row.model_dump(mode="python"),
            )
        )
    for row in output.cohort_transition_rows:
        session.add(
            HarvestStateCohortTransitionRowModel(
                harvest_state_run_id=run.id,
                source_ref=catalog[row.source_ref_hash],
                capacity_pool_membership_hash=membership[
                    (row.state_date, row.capacity_pool_id, row.forecast_quantile.value)
                ],
                **row.model_dump(mode="python"),
            )
        )
    lag_days = output.resolved_parameter_snapshot.run_parameters.harvest_to_arrival_lag_days
    for row in output.future_arrival_schedule:
        session.add(
            HarvestStateFutureArrivalRowModel(
                harvest_state_run_id=run.id,
                subfarm_identity_key=_subfarm_identity_key(row.subfarm_id),
                harvest_to_arrival_lag_days=lag_days,
                farm_timezone=output.resolved_parameter_snapshot.run_parameters.farm_timezone,
                destination_factory_timezone=output.resolved_parameter_snapshot.run_parameters.destination_factory_timezone,
                **row.model_dump(mode="python"),
            )
        )
    await session.flush()
    return run


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

    task9 = await _seed_valid_task9(transactional_pg_session)
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
        "INSUFFICIENT_HISTORY",
        "NO_PERSISTED_PRIOR_SOURCE",
        "SPRING_FESTIVAL_CALENDAR_POLICY_MISSING",
    }
    assert output.provenance["task8_authority"]["maturity_forecast_run_id"] == 9008
    assert output.provenance["task8_authority"] is not None
    assert output.provenance["task9_authority"] is not None
    assert output.provenance["task10_authority"] is not None
    assert (
        output.provenance["task8_authority"]["maturity_model_config_hash"] == model_run.config_hash
    )
    assert (
        output.provenance["task8_authority"]["maturity_model_artifact_hash"]
        == artifact.artifact_hash
    )
    assert (
        output.provenance["task8_authority"]["maturity_forecast_source_signature"]
        == forecast.source_signature
    )
    assert output.provenance["task9_authority"]["harvest_state_run_id"] == 9009
    assert (
        output.provenance["task9_authority"]["harvest_state_run_config_hash"] == task9.config_hash
    )
    assert (
        output.provenance["task9_authority"]["harvest_state_run_canonical_payload_hash"]
        == task9.canonical_payload_hash
    )
    assert output.provenance["task9_authority"]["pool_row_count"] == 9
    assert output.provenance["task9_authority"]["member_row_count"] == 9
    assert output.provenance["task10_authority"]["prediction_run_id"] == 9010
    assert output.provenance["task10_authority"]["prediction_hash"] == task10.prediction_hash
    assert output.provenance["task10_authority"]["prediction_config_hash"] == task10.config_hash
    assert (
        output.provenance["task10_authority"]["prediction_input_signature"]
        == task10.prediction_input_signature
    )
    assert (
        output.provenance["task10_authority"]["prediction_canonical_payload_hash"]
        == task10.canonical_payload_hash
    )
    assert (
        output.provenance["task9_authority"]["harvest_state_run_result_hash"] == task9.result_hash
    )
    assert output.provenance["task10_authority"]["task9_result_hash"] == task9.result_hash
    assert output.normalized_request.canonical_request_hash != "0" * 64
    assert len(output.provenance["agent_forecast_output_hash"]) == 64
