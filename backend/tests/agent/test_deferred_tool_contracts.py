"""Schema-only / deferred-contract tests for tools 6–8."""

from __future__ import annotations

from datetime import date, datetime, UTC

import pytest
from pydantic import ValidationError

from backend.app.agent.enums import BlockerCode
from backend.app.agent.schemas import (
    AdvancedOverrides,
    Blocker,
    ExplainForecastInput,
    ExplainForecastOutput,
    ForecastDailyCurveOutput,
    ForecastPeakOutput,
    GenerateRecommendationsInput,
    NormalizedAgentRequest,
    NormalizedVarietyInput,
    Recommendation,
    RecommendationCategory,
    RequestedAsOfDateProvenance,
    ResolvedLocation,
    RunBacktestInput,
    RunBacktestOutput,
)


def _mk_nr() -> NormalizedAgentRequest:
    return NormalizedAgentRequest(
        request_id="r1",
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
        advanced_overrides=AdvancedOverrides(),
        canonical_request_hash="0" * 64,
    )


# --- run_backtest: schema + EXECUTION_DEFERRED only ----------------------

def test_run_backtest_output_must_be_execution_deferred():
    out = RunBacktestOutput(
        status="EXECUTION_DEFERRED",
        blocker=Blocker(
            code=BlockerCode.EXECUTION_DEFERRED,
            message="run_backtest is deferred in Slice A",
            retry_hint="CONTACT_OPS",
        ),
    )
    assert out.status == "EXECUTION_DEFERRED"
    assert out.blocker.code == BlockerCode.EXECUTION_DEFERRED


def test_run_backtest_output_rejects_non_deferred_status():
    with pytest.raises(ValidationError):
        RunBacktestOutput(
            status="OK",  # type: ignore[arg-type]
            blocker=Blocker(code=BlockerCode.EXECUTION_DEFERRED, message="x"),
        )


def test_run_backtest_never_invokes_task11():
    """The adapter does not exist in Slice A; ``run_backtest`` has NO runtime entry point."""

    import backend.app.agent.adapters  # noqa: F401

    # No "run_backtest" adapter module exists.
    import importlib.util

    spec = importlib.util.find_spec("backend.app.agent.adapters.run_backtest")
    assert spec is None, "run_backtest adapter must NOT exist in Slice A"


def test_run_backtest_input_schema_validates():
    RunBacktestInput(
        normalized_request=_mk_nr(),
        execution_override=None,
    )


# --- explain_forecast: schema only --------------------------------------

def test_explain_forecast_input_validates_with_daily_curve():
    inp = ExplainForecastInput(
        normalized_request=_mk_nr(),
        resolved_location=ResolvedLocation(status="resolved", location_reference_id=1, matched_location_method="REFERENCE_ID"),
        parameters=[],
        daily_curve=ForecastDailyCurveOutput(per_day=[], agent_daily_curve_hash="a" * 64),
        peak=ForecastPeakOutput(
            peak_metric_policy_version="v1",
            peak_metric_policy_config_hash="c" * 64,
            agent_peak_hash="a" * 64,
            single_day_peak={"P50": _sdp(date(2026, 3, 1), "100.0"), "P80": _sdp(date(2026, 3, 1), "200.0"), "P90": _sdp(date(2026, 3, 1), "300.0")},
            sustained_window_days=3,
            sustained_3day_peak={"P50": _sp(date(2026, 3, 1), date(2026, 3, 3), "100.0", "300.0"), "P80": _sp(date(2026, 3, 1), date(2026, 3, 3), "200.0", "600.0"), "P90": _sp(date(2026, 3, 1), date(2026, 3, 3), "300.0", "900.0")},
            peak_window_days_before=7,
            peak_window_days_after=7,
            peak_window_cumulative_quantity_kg={"P50": "100.0", "P80": "200.0", "P90": "300.0"},
            peak_duration_days={"P50": 1, "P80": 1, "P90": 1},
            high_load_threshold={"P50": "90.0", "P80": "180.0", "P90": "270.0"},
            dominant_variety={},
        ),
        citations=[],
    )
    assert inp.normalized_request.request_id == "r1"


def test_explain_forecast_output_empty_payload_allowed():
    """An empty structured_payload is allowed (no deterministic narrative in Slice A)."""

    out = ExplainForecastOutput()
    assert out.structured_payload == []


# --- generate_recommendations: schema only, 7 categories ----------------

def test_recommendation_seven_categories_allowed():
    """All 7 categories must be valid (6 operational + 1 data-quality)."""

    cats = list(RecommendationCategory.__args__)
    assert len(cats) == 7
    for c in cats:
        rec = Recommendation(
            category=c,
            kind=("OPERATIONAL" if c != "MISSING_DATA_IMPACT" else "DATA_QUALITY"),
            text=f"{c} recommendation",
            rule_id=f"rule-{c}",
            evidence=[],
            confidence="HIGH",
        )
        assert rec.category == c


def test_recommendation_rejects_invalid_category():
    with pytest.raises(ValidationError):
        Recommendation(
            category="INVALID_CATEGORY",
            kind="OPERATIONAL",
            text="x",
            rule_id="r",
            evidence=[],
            confidence="HIGH",
        )


def test_generate_recommendations_input_validates():
    GenerateRecommendationsInput(
        normalized_request=_mk_nr(),
        resolved_location=ResolvedLocation(status="resolved", location_reference_id=1, matched_location_method="REFERENCE_ID"),
        parameters=[],
        daily_curve=ForecastDailyCurveOutput(per_day=[], agent_daily_curve_hash="a" * 64),
        peak=ForecastPeakOutput(
            peak_metric_policy_version="v1",
            peak_metric_policy_config_hash="c" * 64,
            agent_peak_hash="a" * 64,
            single_day_peak={"P50": _sdp(date(2026, 3, 1), "100.0"), "P80": _sdp(date(2026, 3, 1), "200.0"), "P90": _sdp(date(2026, 3, 1), "300.0")},
            sustained_window_days=3,
            sustained_3day_peak={"P50": _sp(date(2026, 3, 1), date(2026, 3, 3), "100.0", "300.0"), "P80": _sp(date(2026, 3, 1), date(2026, 3, 3), "200.0", "600.0"), "P90": _sp(date(2026, 3, 1), date(2026, 3, 3), "300.0", "900.0")},
            peak_window_days_before=7,
            peak_window_days_after=7,
            peak_window_cumulative_quantity_kg={"P50": "100.0", "P80": "200.0", "P90": "300.0"},
            peak_duration_days={"P50": 1, "P80": 1, "P90": 1},
            high_load_threshold={"P50": "90.0", "P80": "180.0", "P90": "270.0"},
            dominant_variety={},
        ),
        citations=[],
    )


def test_no_deterministic_recommendation_engine_in_slice_a():
    """There MUST be no rule_id registry or threshold engine in Slice A."""

    import importlib.util

    for name in ("recommendation_engine", "rule_registry", "threshold_engine"):
        spec = importlib.util.find_spec(f"backend.app.agent.adapters.{name}")
        assert spec is None, f"{name} MUST NOT exist in Slice A"


# --- helpers ---------------------------------------------------------------

def _sdp(d, v):
    from backend.app.agent.schemas import SingleDayPeakEntry
    return SingleDayPeakEntry(date=d, volume_kg=v)


def _sp(s, e, m, c):
    from backend.app.agent.schemas import SustainedPeakEntry
    return SustainedPeakEntry(
        start_date=s,
        end_date=e,
        rolling_daily_average_kg_per_day=m,
        cumulative_quantity_kg=c,
    )
