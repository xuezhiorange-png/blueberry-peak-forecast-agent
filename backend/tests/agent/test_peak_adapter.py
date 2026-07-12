"""Pure-deterministic tests for ``forecast_peak`` adapter."""

from __future__ import annotations

from datetime import date

import pytest

from backend.app.agent.adapters.peak import DefaultPeakAdapter
from backend.app.agent.canonical import sha256_payload
from backend.app.agent.schemas import (
    AdvancedOverrides,
    DailyQuantiles,
    ForecastDailyCurveOutput,
    ForecastDailyRow,
    ForecastPeakInput,
    NormalizedAgentRequest,
    NormalizedVarietyInput,
    PeakMetricPolicy,
    RequestedAsOfDateProvenance,
    ResolvedLocation,
    VarietyContribution,
)


def _row(d, p50, p80, p90, contributions=None):
    return ForecastDailyRow(
        date=d,
        natural_maturity_quantity_kg=DailyQuantiles(p50=p50, p80=p80, p90=p90),
        harvested_quantity_kg=DailyQuantiles(p50=p50, p80=p80, p90=p90),
        closing_mature_inventory_kg=DailyQuantiles(p50="0.000000000000000000", p80="0.000000000000000000", p90="0.000000000000000000"),
        unharvested_backlog_kg=DailyQuantiles(p50="0.000000000000000000", p80="0.000000000000000000", p90="0.000000000000000000"),
        arrival_quantity_kg=DailyQuantiles(p50=p50, p80=p80, p90=p90),
        final_corrected_arrival_quantity_kg=DailyQuantiles(p50=p50, p80=p80, p90=p90),
        per_variety_contribution=contributions or [],
        agent_daily_row_hash="0" * 64,
    )


def _curve(rows):
    return ForecastDailyCurveOutput(
        per_day=rows,
        agent_daily_curve_hash=sha256_payload([{"date": str(r.date)} for r in rows]),
    )


def _policy(ratio="0.900000000000000000"):
    return PeakMetricPolicy(
        policy_version="peak-metric/v1",
        policy_config_hash="c" * 64,
        sustained_window_days=3,
        sustained_metric="ROLLING_DAILY_AVERAGE",
        tie_break="EARLIEST_START_DATE",
        peak_window_days_before=7,
        peak_window_days_after=7,
        high_load_reference="SINGLE_DAY_PEAK",
        high_load_threshold_ratio=ratio,
    )


def _input(rows, policy=None):
    from datetime import datetime, UTC
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
        varieties=[NormalizedVarietyInput(variety_id="101", planting_area_mu="100.000000000000000000")],
        advanced_overrides=AdvancedOverrides(),
        canonical_request_hash="0" * 64,
    )
    return ForecastPeakInput(
        normalized_request=nr,
        daily_curve=_curve(rows),
        peak_metric_policy=policy or _policy(),
    )


# --- 1. single-day max ---

def test_single_day_max():
    rows = [
        _row(date(2026, 3, 1), "100.000000000000000000", "100.000000000000000000", "100.000000000000000000"),
        _row(date(2026, 3, 2), "200.000000000000000000", "200.000000000000000000", "200.000000000000000000"),
        _row(date(2026, 3, 3), "150.000000000000000000", "150.000000000000000000", "150.000000000000000000"),
    ]
    out = DefaultPeakAdapter().execute(input=_input(rows))
    assert out.single_day_peak["P50"].date == date(2026, 3, 2)
    assert out.single_day_peak["P50"].volume_kg == "200.000000000000000000"


# --- 2. earliest-date tie-break ---

def test_earliest_date_tie_break():
    rows = [
        _row(date(2026, 3, 1), "100.000000000000000000", "100.000000000000000000", "100.000000000000000000"),
        _row(date(2026, 3, 3), "200.000000000000000000", "200.000000000000000000", "200.000000000000000000"),
        _row(date(2026, 3, 2), "200.000000000000000000", "200.000000000000000000", "200.000000000000000000"),
    ]
    out = DefaultPeakAdapter().execute(input=_input(rows))
    assert out.single_day_peak["P50"].date == date(2026, 3, 2)


# --- 3. 3-day mean and cumulative ---

def test_sustained_3day_mean_and_cumulative():
    rows = [
        _row(date(2026, 3, 1), "100.000000000000000000", "100.000000000000000000", "100.000000000000000000"),
        _row(date(2026, 3, 2), "200.000000000000000000", "200.000000000000000000", "200.000000000000000000"),
        _row(date(2026, 3, 3), "300.000000000000000000", "300.000000000000000000", "300.000000000000000000"),
        _row(date(2026, 3, 4), "150.000000000000000000", "150.000000000000000000", "150.000000000000000000"),
    ]
    out = DefaultPeakAdapter().execute(input=_input(rows))
    sus = out.sustained_3day_peak["P50"]
    assert sus.start_date == date(2026, 3, 2)
    assert sus.end_date == date(2026, 3, 4)
    assert sus.rolling_daily_average_kg_per_day == "216.666666666666666667"
    assert sus.cumulative_quantity_kg == "650.000000000000000000"


# --- 4. no incomplete 3-day windows ---

def test_no_incomplete_3day_window():
    rows = [
        _row(date(2026, 3, 1), "100.000000000000000000", "100.000000000000000000", "100.000000000000000000"),
        _row(date(2026, 3, 3), "200.000000000000000000", "200.000000000000000000", "200.000000000000000000"),
    ]
    with pytest.raises(ValueError):
        DefaultPeakAdapter().execute(input=_input(rows))


# --- 5. boundary-clipped ±7 window ---

def test_boundary_clipped_seven_day_window():
    rows = [
        _row(date(2026, 3, 1), "100.000000000000000000", "100.000000000000000000", "100.000000000000000000"),
        _row(date(2026, 3, 2), "100.000000000000000000", "100.000000000000000000", "100.000000000000000000"),
        _row(date(2026, 3, 3), "100.000000000000000000", "100.000000000000000000", "100.000000000000000000"),
        _row(date(2026, 3, 4), "100.000000000000000000", "100.000000000000000000", "100.000000000000000000"),
        _row(date(2026, 3, 5), "500.000000000000000000", "500.000000000000000000", "500.000000000000000000"),
        _row(date(2026, 3, 6), "100.000000000000000000", "100.000000000000000000", "100.000000000000000000"),
        _row(date(2026, 3, 7), "100.000000000000000000", "100.000000000000000000", "100.000000000000000000"),
        _row(date(2026, 3, 8), "100.000000000000000000", "100.000000000000000000", "100.000000000000000000"),
        _row(date(2026, 3, 9), "100.000000000000000000", "100.000000000000000000", "100.000000000000000000"),
        _row(date(2026, 3, 10), "150.000000000000000000", "150.000000000000000000", "150.000000000000000000"),
    ]
    out = DefaultPeakAdapter().execute(input=_input(rows))
    peak_date = out.single_day_peak["P50"].date
    assert peak_date == date(2026, 3, 5)
    assert out.peak_window_cumulative_quantity_kg["P50"] == "1450.000000000000000000"


# --- 6. all three quantiles ---

def test_three_quantiles_separate():
    rows = [
        _row(date(2026, 3, 1), "100.000000000000000000", "200.000000000000000000", "300.000000000000000000"),
        _row(date(2026, 3, 2), "50.000000000000000000", "250.000000000000000000", "350.000000000000000000"),
        _row(date(2026, 3, 3), "50.000000000000000000", "50.000000000000000000", "50.000000000000000000"),
    ]
    out = DefaultPeakAdapter().execute(input=_input(rows))
    assert out.single_day_peak["P50"].volume_kg == "100.000000000000000000"
    assert out.single_day_peak["P80"].volume_kg == "250.000000000000000000"
    assert out.single_day_peak["P90"].volume_kg == "350.000000000000000000"


# --- 7. high-load threshold ---

def test_high_load_threshold_ratio_times_peak():
    rows = [
        _row(date(2026, 3, 1), "50.000000000000000000", "50.000000000000000000", "50.000000000000000000"),
        _row(date(2026, 3, 2), "200.000000000000000000", "200.000000000000000000", "200.000000000000000000"),
        _row(date(2026, 3, 3), "50.000000000000000000", "50.000000000000000000", "50.000000000000000000"),
    ]
    out = DefaultPeakAdapter().execute(input=_input(rows, policy=_policy("0.500000000000000000")))
    assert out.high_load_threshold["P50"] == "100.000000000000000000"


# --- 8. duration segment contains peak date ---

def test_peak_duration_contains_peak_date():
    rows = [
        _row(date(2026, 3, 1), "50.000000000000000000", "50.000000000000000000", "50.000000000000000000"),
        _row(date(2026, 3, 2), "50.000000000000000000", "50.000000000000000000", "50.000000000000000000"),
        _row(date(2026, 3, 3), "200.000000000000000000", "200.000000000000000000", "200.000000000000000000"),
        _row(date(2026, 3, 4), "200.000000000000000000", "200.000000000000000000", "200.000000000000000000"),
        _row(date(2026, 3, 5), "200.000000000000000000", "200.000000000000000000", "200.000000000000000000"),
        _row(date(2026, 3, 6), "200.000000000000000000", "200.000000000000000000", "200.000000000000000000"),
        _row(date(2026, 3, 7), "50.000000000000000000", "50.000000000000000000", "50.000000000000000000"),
    ]
    out = DefaultPeakAdapter().execute(input=_input(rows, policy=_policy("0.500000000000000000")))
    assert out.peak_duration_days["P50"] == 4


# --- 9. dominant-variety denominator ---

def test_dominant_variety_denominator_disclosed():
    contributions = [
        VarietyContribution(
            variety_id="101",
            volume_kg_p50="100.000000000000000000",
            volume_kg_p80="100.000000000000000000",
            volume_kg_p90="100.000000000000000000",
            contribution_rate_p50="0.500000000000000000",
            contribution_rate_p80="0.500000000000000000",
            contribution_rate_p90="0.500000000000000000",
        ),
        VarietyContribution(
            variety_id="102",
            volume_kg_p50="100.000000000000000000",
            volume_kg_p80="100.000000000000000000",
            volume_kg_p90="100.000000000000000000",
            contribution_rate_p50="0.500000000000000000",
            contribution_rate_p80="0.500000000000000000",
            contribution_rate_p90="0.500000000000000000",
        ),
    ]
    rows = [
        _row(date(2026, 3, 1), "200.000000000000000000", "200.000000000000000000", "200.000000000000000000", contributions),
        _row(date(2026, 3, 2), "200.000000000000000000", "200.000000000000000000", "200.000000000000000000", contributions),
        _row(date(2026, 3, 3), "200.000000000000000000", "200.000000000000000000", "200.000000000000000000", contributions),
    ]
    out = DefaultPeakAdapter().execute(input=_input(rows))
    dv = out.dominant_variety["P50"]
    assert dv.variety_id in ("101", "102")
    assert dv.numerator_kg == "300.000000000000000000"
    assert dv.denominator_kg == "600.000000000000000000"


# --- 10. stable hash ---

def test_agent_peak_hash_stable_for_same_input():
    rows = [
        _row(date(2026, 3, 1), "100.000000000000000000", "100.000000000000000000", "100.000000000000000000"),
        _row(date(2026, 3, 2), "200.000000000000000000", "200.000000000000000000", "200.000000000000000000"),
        _row(date(2026, 3, 3), "150.000000000000000000", "150.000000000000000000", "150.000000000000000000"),
    ]
    inp = _input(rows)
    out1 = DefaultPeakAdapter().execute(input=inp)
    out2 = DefaultPeakAdapter().execute(input=inp)
    assert out1.agent_peak_hash == out2.agent_peak_hash
