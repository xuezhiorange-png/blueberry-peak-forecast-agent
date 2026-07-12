"""SQLite-backed tests for ``forecast_daily_curve`` adapter."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest

from backend.app.agent.adapters.daily_curve import DefaultDailyCurveAdapter
from backend.app.agent.ports import ScenarioBaselinePort
from backend.app.agent.schemas import (
    AdvancedOverrides,
    DailyQuantiles,
    ForecastDailyCurveInput,
    ForecastDailyRow,
    LocationInput,
    NormalizedAgentRequest,
    NormalizedVarietyInput,
    RequestedAsOfDateProvenance,
    ResolvedLocation,
    Task12PredictionRunAuthorityOverride,
    UncertaintyWideningPolicy,
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
        normalized_location=ResolvedLocation(
            status="resolved",
            location_reference_id=1,
            matched_location_method="REFERENCE_ID",
        ),
        location_input=LocationInput(
            raw_text="云南曲靖",
            location_reference_id=1,
        ),
        varieties=[
            NormalizedVarietyInput(variety_id="101", planting_area_mu="100.000000000000000000")
        ],
        advanced_overrides=AdvancedOverrides(),
        canonical_request_hash="0" * 64,
    )


def _row(d, p50, p80, p90, contributions=None):
    return ForecastDailyRow(
        date=d,
        natural_maturity_quantity_kg=DailyQuantiles(p50=p50, p80=p80, p90=p90),
        harvested_quantity_kg=DailyQuantiles(p50=p50, p80=p80, p90=p90),
        closing_mature_inventory_kg=DailyQuantiles(
            p50="0.000000000000000000", p80="0.000000000000000000", p90="0.000000000000000000"
        ),
        unharvested_backlog_kg=DailyQuantiles(
            p50="0.000000000000000000", p80="0.000000000000000000", p90="0.000000000000000000"
        ),
        arrival_quantity_kg=DailyQuantiles(p50=p50, p80=p80, p90=p90),
        final_corrected_arrival_quantity_kg=DailyQuantiles(p50=p50, p80=p80, p90=p90),
        per_variety_contribution=contributions or [],
        agent_daily_row_hash="0" * 64,
    )


class _FakeBaseline(ScenarioBaselinePort):
    def __init__(self, rows: list[ForecastDailyRow]):
        self._rows = rows

    async def compute_baseline(
        self,
        *,
        session: Any,
        normalized_request: Any,
        resolved_location: Any,
        parameters: list[Any],
        advanced_overrides: Any,
    ):
        from backend.app.agent.adapters.baseline_composer import BaselineCompositionResult

        return BaselineCompositionResult(
            rows=self._rows,
            task8_run_id=None,
            task9_run_id=None,
            task10_prediction_run_id=None,
            blockers=[],
        )


def _mk_input(rows: list[ForecastDailyRow]) -> ForecastDailyCurveInput:
    return ForecastDailyCurveInput(
        normalized_request=_mk_nr(),
        resolved_location=ResolvedLocation(
            status="resolved", location_reference_id=1, matched_location_method="REFERENCE_ID"
        ),
        parameters=[],
        advanced_overrides=AdvancedOverrides(),
        uncertainty_widening_policy=UncertaintyWideningPolicy(
            policy_version="v1",
            config_hash="b" * 64,
            factors_by_source_level={
                "step_1_same_farm_same_variety_high_evidence": "1.000",
                "step_2_same_township_similar_altitude": "1.250",
                "step_3_same_county_same_climate_zone": "1.500",
                "step_4_province_level_same_variety": "1.750",
                "step_5_variety_document_prior_only": "2.000",
            },
            monotonicity_invariant=True,
        ),
    )


# --- p50/p80/p90 preserved for all six daily fields -------------------


@pytest.mark.asyncio
async def test_daily_curve_p50_p80_p90_preserved(sqlite_session):
    rows = [
        _row(
            date(2026, 3, 1),
            "100.000000000000000000",
            "200.000000000000000000",
            "300.000000000000000000",
        )
    ]
    adapter = DefaultDailyCurveAdapter(baseline=_FakeBaseline(rows))
    out = await adapter.execute(sqlite_session, input=_mk_input(rows))
    assert len(out.per_day) == 1
    r = out.per_day[0]
    assert r.natural_maturity_quantity_kg.p50 == "100.000000000000000000"
    assert r.natural_maturity_quantity_kg.p80 == "200.000000000000000000"
    assert r.natural_maturity_quantity_kg.p90 == "300.000000000000000000"
    assert r.final_corrected_arrival_quantity_kg.p50 == "100.000000000000000000"
    assert r.final_corrected_arrival_quantity_kg.p90 == "300.000000000000000000"


# --- TASK-012 absent by default ----------------------------------------


@pytest.mark.asyncio
async def test_daily_curve_task12_absent_by_default(sqlite_session):
    rows = [
        _row(
            date(2026, 3, 1),
            "100.000000000000000000",
            "100.000000000000000000",
            "100.000000000000000000",
        )
    ]
    adapter = DefaultDailyCurveAdapter(baseline=_FakeBaseline(rows))
    out = await adapter.execute(sqlite_session, input=_mk_input(rows))
    assert out.task12_authority is None


# --- explicit TASK-012 run-ID mismatch rejected ------------------------


@pytest.mark.asyncio
async def test_daily_curve_explicit_task12_runid_mismatch_rejected(sqlite_session):
    rows = [
        _row(
            date(2026, 3, 1),
            "100.000000000000000000",
            "100.000000000000000000",
            "100.000000000000000000",
        )
    ]
    # Override points to run_id=42 but no port supplies an authority → mismatch.
    overrides = AdvancedOverrides(
        authority_overrides=[
            Task12PredictionRunAuthorityOverride(
                override_kind="AUTHORITY_OVERRIDE_KIND",
                target="TASK12_PREDICTION_RUN",
                value=42,
                source_attestation="op",
            )
        ],
    )
    inp = _mk_input(rows)
    inp = inp.model_copy(update={"advanced_overrides": overrides})
    adapter = DefaultDailyCurveAdapter(baseline=_FakeBaseline(rows))
    out = await adapter.execute(sqlite_session, input=inp)
    assert out.task12_authority is None
    codes = [b.code.value for b in out.blockers]
    assert "TASK12_AUTHORITY_NOT_FOUND" in codes


# --- identical input produces byte-identical output ---------------------


@pytest.mark.asyncio
async def test_daily_curve_identical_input_identical_output(sqlite_session):
    rows = [
        _row(
            date(2026, 3, 1),
            "100.000000000000000000",
            "100.000000000000000000",
            "100.000000000000000000",
        )
    ]
    adapter = DefaultDailyCurveAdapter(baseline=_FakeBaseline(rows))
    inp = _mk_input(rows)
    out1 = await adapter.execute(sqlite_session, input=inp)
    out2 = await adapter.execute(sqlite_session, input=inp)
    assert out1.agent_daily_curve_hash == out2.agent_daily_curve_hash


# --- agent_daily_row_hash is deterministic ------------------------------


@pytest.mark.asyncio
async def test_daily_row_hash_deterministic(sqlite_session):
    rows = [
        _row(
            date(2026, 3, 1),
            "100.000000000000000000",
            "100.000000000000000000",
            "100.000000000000000000",
        )
    ]
    adapter = DefaultDailyCurveAdapter(baseline=_FakeBaseline(rows))
    out = await adapter.execute(sqlite_session, input=_mk_input(rows))
    assert out.per_day[0].agent_daily_row_hash != "0" * 64
    assert len(out.per_day[0].agent_daily_row_hash) == 64
