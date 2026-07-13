"""Real PostgreSQL session evidence for the Slice B orchestration boundary."""

import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from backend.app.agent.orchestration import AgentOrchestrator, StaticSeasonCalendarPolicy
from backend.app.agent.schemas import LocationInput, PeakMetricPolicy, UncertaintyWideningPolicy
from backend.tests.agent.test_orchestration import _request


@pytest.mark.postgres
@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
    reason="set RUN_POSTGRES_INTEGRATION=1 for real PostgreSQL evidence",
)
async def test_slice_b_orchestration_uses_real_postgres_session(transactional_pg_session) -> None:
    result = await transactional_pg_session.execute(text("SELECT 1"))
    assert result.scalar_one() == 1

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
    request = _request().model_copy(update={"location": LocationInput(location_reference_id=601)})
    output = await policy_source.execute(
        transactional_pg_session,
        request=request,
        request_received_at=datetime(2026, 3, 1, tzinfo=UTC),
    )
    assert output.normalized_request.canonical_request_hash != "0" * 64
    assert len(output.provenance["agent_forecast_output_hash"]) == 64
