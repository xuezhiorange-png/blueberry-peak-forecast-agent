"""SQLite-backed tests for ``simulate_scenario`` adapter."""

from __future__ import annotations

from datetime import date, datetime, UTC

import pytest

from backend.app.agent.enums import BlockerCode
from backend.app.agent.schemas import (
    ProcessorCapacityOverrideValue,
    ScenarioOverride,
    SimulateScenarioInput,
    StaffingOverrideValue,
)


def _ov_staffing(value: str) -> ScenarioOverride:
    return ScenarioOverride(
        override_kind="SCENARIO_OVERRIDE_KIND",
        target="STAFFING",
        value=StaffingOverrideValue(value=value),
        source_attestation="op",
    )


def _ov_capacity(value: str) -> ScenarioOverride:
    return ScenarioOverride(
        override_kind="SCENARIO_OVERRIDE_KIND",
        target="PROCESSOR_CAPACITY",
        value=ProcessorCapacityOverrideValue(value=value),
        source_attestation="op",
    )


def test_negative_staffing_rejected():
    """Validation should reject negative staffing values."""

    from backend.app.agent.adapters.scenario import _validate_overrides

    blockers = _validate_overrides([_ov_staffing("-1.0")])
    assert any(b.code == BlockerCode.SCENARIO_INVALID for b in blockers)


def test_negative_capacity_rejected():
    from backend.app.agent.adapters.scenario import _validate_overrides

    blockers = _validate_overrides([_ov_capacity("-5.0")])
    assert any(b.code == BlockerCode.SCENARIO_INVALID for b in blockers)


def test_non_negative_staffing_accepted():
    from backend.app.agent.adapters.scenario import _validate_overrides

    blockers = _validate_overrides([_ov_staffing("10.0")])
    assert blockers == []


def test_scenario_id_and_hash_stable():
    from backend.app.agent.adapters.scenario import _scenario_id_and_hash

    sid1, sh1 = _scenario_id_and_hash([_ov_staffing("10.0")])
    sid2, sh2 = _scenario_id_and_hash([_ov_staffing("10.0")])
    assert sid1 == sid2
    assert sh1 == sh2
    assert len(sid1) == 64


def test_scenario_id_changes_when_overrides_change():
    from backend.app.agent.adapters.scenario import _scenario_id_and_hash

    sid1, _ = _scenario_id_and_hash([_ov_staffing("10.0")])
    sid2, _ = _scenario_id_and_hash([_ov_staffing("20.0")])
    assert sid1 != sid2


def test_scenario_delta_quantiles_no_single_scalar():
    """The output contract MUST NOT carry a single ``sustained_3day_delta`` scalar."""

    from backend.app.agent.adapters.scenario import (
        _delta_quantiles,
    )
    from backend.app.agent.schemas import ScenarioDeltaQuantiles
    from decimal import Decimal

    baseline = {"P50": Decimal("100"), "P80": Decimal("120"), "P90": Decimal("140")}
    scenario = {"P50": Decimal("110"), "P80": Decimal("125"), "P90": Decimal("145")}
    d = _delta_quantiles(baseline, scenario)
    assert isinstance(d, ScenarioDeltaQuantiles)
    assert d.p50 == "10"
    assert d.p80 == "5"
    assert d.p90 == "5"


@pytest.mark.asyncio
async def test_simulate_scenario_quantile_preserving_deltas(sqlite_session):
    """End-to-end: same scenario twice → same scenario_id/hash and identical deltas."""

    from datetime import date as _date
    from backend.app.agent.adapters.scenario import DefaultScenarioAdapter
    from backend.app.agent.adapters.daily_curve import DefaultDailyCurveAdapter
    from backend.app.agent.adapters.peak import DefaultPeakAdapter
    from backend.app.agent.ports import ScenarioBaselinePort
    from backend.app.agent.schemas import (
        AdvancedOverrides as AO,
        DailyQuantiles,
        ForecastDailyRow,
        NormalizedAgentRequest,
        NormalizedVarietyInput,
        PeakMetricPolicy,
        RequestedAsOfDateProvenance,
        ResolvedLocation,
        UncertaintyWideningPolicy,
    )

    class _StaticBaseline(ScenarioBaselinePort):
        async def compute_baseline(self, *, session, normalized_request, resolved_location, parameters, advanced_overrides):
            r = ForecastDailyRow(
                date=_date(2026, 3, 1),
                natural_maturity_quantity_kg=DailyQuantiles(p50="100.0", p80="100.0", p90="100.0"),
                harvested_quantity_kg=DailyQuantiles(p50="100.0", p80="100.0", p90="100.0"),
                closing_mature_inventory_kg=DailyQuantiles(p50="0.0", p80="0.0", p90="0.0"),
                unharvested_backlog_kg=DailyQuantiles(p50="0.0", p80="0.0", p90="0.0"),
                arrival_quantity_kg=DailyQuantiles(p50="100.0", p80="100.0", p90="100.0"),
                final_corrected_arrival_quantity_kg=DailyQuantiles(p50="100.0", p80="100.0", p90="100.0"),
                per_variety_contribution=[],
                agent_daily_row_hash="0" * 64,
            )
            return [r, r.model_copy(update={"date": _date(2026, 3, 2)}), r.model_copy(update={"date": _date(2026, 3, 3)})], []

    nr = NormalizedAgentRequest(
        request_id="r",
        request_received_at=datetime(2026, 3, 1, tzinfo=UTC),
        effective_as_of_date=date(2026, 3, 1),
        effective_forecast_season=2026,
        season_resolution_policy_version="season-calendar/v1",
        season_calendar_config_hash="a" * 64,
        requested_as_of_date_provenance=RequestedAsOfDateProvenance(
            caller_requested_as_of_date=date(2026, 3, 1),
            effective_as_of_date=date(2026, 3, 1),
            override_applied=False,
            override_kind=None,
            source_attestation=None,
            source_ref=None,
        ),
        normalized_location=ResolvedLocation(status="resolved", location_reference_id=1, matched_location_method="REFERENCE_ID"),
        varieties=[NormalizedVarietyInput(variety_id="101", planting_area_mu="100.0")],
        advanced_overrides=AO(),
        canonical_request_hash="0" * 64,
    )
    inp = SimulateScenarioInput(
        normalized_request=nr,
        resolved_location=ResolvedLocation(status="resolved", location_reference_id=1, matched_location_method="REFERENCE_ID"),
        parameters=[],
        scenario_overrides=[_ov_staffing("10.0")],
        uncertainty_widening_policy=UncertaintyWideningPolicy(
            policy_version="v1", config_hash="b" * 64,
            factors_by_source_level={
                "step_1_same_farm_same_variety_high_evidence": "1.000",
                "step_2_same_township_similar_altitude": "1.250",
                "step_3_same_county_same_climate_zone": "1.500",
                "step_4_province_level_same_variety": "1.750",
                "step_5_variety_document_prior_only": "2.000",
            },
            monotonicity_invariant=True,
        ),
        peak_metric_policy=PeakMetricPolicy(
            policy_version="peak-metric/v1",
            policy_config_hash="c" * 64,
            sustained_window_days=3,
            sustained_metric="ROLLING_DAILY_AVERAGE",
            tie_break="EARLIEST_START_DATE",
            peak_window_days_before=7,
            peak_window_days_after=7,
            high_load_reference="SINGLE_DAY_PEAK",
            high_load_threshold_ratio="0.9",
        ),
        advanced_overrides=AO(),
    )
    daily = DefaultDailyCurveAdapter(baseline=_StaticBaseline())
    peak = DefaultPeakAdapter()
    adapter = DefaultScenarioAdapter(daily_curve_adapter=daily, peak_adapter=peak)
    out1 = await adapter.execute(sqlite_session, input=inp)
    out2 = await adapter.execute(sqlite_session, input=inp)
    assert out1.scenario_id == out2.scenario_id
    assert out1.scenario_config_hash == out2.scenario_config_hash
    # All three delta fields must be quantile-bearing
    assert hasattr(out1.delta_vs_baseline, "single_day_peak_volume_delta_kg")
    assert hasattr(out1.delta_vs_baseline, "sustained_3day_daily_average_delta_kg_per_day")
    assert hasattr(out1.delta_vs_baseline, "sustained_3day_cumulative_delta_kg")
    assert not hasattr(out1.delta_vs_baseline, "sustained_3day_delta")  # single scalar MUST NOT exist
