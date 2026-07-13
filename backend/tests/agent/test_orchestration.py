import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from backend.app.agent.canonical import sha256_payload
from backend.app.agent.orchestration import (
    AgentOrchestrator,
    StaticSeasonCalendarPolicy,
    UnsupportedToolError,
)
from backend.app.agent.schemas import (
    AdvancedOverrides,
    AsOfOverride,
    ForecastDailyCurveOutput,
    InferParametersOutput,
    LocationInput,
    MinimalInputRequest,
    MinimalVarietyInput,
    PeakMetricPolicy,
    ResolvedLocation,
    ResolveLocationOutput,
    UncertaintyWideningPolicy,
)


class _Location:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    async def execute(self, session: object, *, input: object) -> ResolveLocationOutput:
        self.calls.append("RESOLVE_LOCATION")
        return ResolveLocationOutput(
            resolved_location=ResolvedLocation(
                status="resolved",
                location_reference_id=601,
                matched_location_method="REFERENCE_ID",
            ),
            location_catalog_version="catalog/v1",
        )


class _BrokenLocation:
    async def execute(self, session: object, *, input: object) -> ResolveLocationOutput:
        raise RuntimeError("secret traceback must not escape")


class _Parameters:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    async def execute(self, session: object, *, input: object) -> InferParametersOutput:
        self.calls.append("INFER_PARAMETERS")
        return InferParametersOutput(
            parameters=[],
            uncertainty_widening_policy_version="uncertainty-widening/v1",
            uncertainty_widening_policy_config_hash="b" * 64,
            parameters_hash="d" * 64,
        )


class _Daily:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    async def execute(self, session: object, *, input: object) -> ForecastDailyCurveOutput:
        self.calls.append("FORECAST_DAILY_CURVE")
        return ForecastDailyCurveOutput(per_day=[], agent_daily_curve_hash="e" * 64)


class _Peak:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def execute(self, *, input: object) -> object:
        self.calls.append("FORECAST_PEAK")
        return type(
            "PeakOutput",
            (),
            {
                "agent_peak_hash": "f" * 64,
                "model_dump": lambda self, mode="json": {"agent_peak_hash": self.agent_peak_hash},
                "blockers": [],
            },
        )()


class _Scenario:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    async def execute(self, session: object, *, input: object) -> object:
        self.calls.append("SIMULATE_SCENARIO")
        return type("ScenarioOutput", (), {"scenario_config_hash": "1" * 64, "blockers": []})()


def _request() -> MinimalInputRequest:
    return MinimalInputRequest(
        request_id="request-1",
        location=LocationInput(raw_text="Yunnan, China"),
        varieties=[MinimalVarietyInput(variety_id="101", planting_area_mu="100.0")],
    )


def _orchestrator(calls: list[str]) -> AgentOrchestrator:
    return AgentOrchestrator(
        season_calendar=StaticSeasonCalendarPolicy(),
        location_adapter=_Location(calls),
        parameter_adapter=_Parameters(calls),
        daily_curve_adapter=_Daily(calls),
        peak_adapter=_Peak(calls),
        scenario_adapter=_Scenario(calls),
        uncertainty_widening_policy=UncertaintyWideningPolicy(
            policy_version="uncertainty-widening/v1",
            config_hash="b" * 64,
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
            policy_config_hash="c" * 64,
            sustained_window_days=3,
            peak_window_days_before=7,
            peak_window_days_after=7,
            high_load_threshold_ratio="0.900",
        ),
    )


@pytest.mark.asyncio
async def test_orchestration_is_ordered_and_byte_stable() -> None:
    first_calls: list[str] = []
    second_calls: list[str] = []
    received_at = datetime(2026, 3, 1, 8, tzinfo=UTC)
    first = await _orchestrator(first_calls).execute(
        None, request=_request(), request_received_at=received_at
    )
    second = await _orchestrator(second_calls).execute(
        None, request=_request(), request_received_at=received_at
    )

    assert first_calls == [
        "RESOLVE_LOCATION",
        "INFER_PARAMETERS",
        "FORECAST_DAILY_CURVE",
        "FORECAST_PEAK",
        "SIMULATE_SCENARIO",
    ]
    assert first.model_dump_json() == second.model_dump_json()
    assert first.provenance["agent_forecast_output_hash"]
    golden = json.loads(
        (Path(__file__).parent / "golden" / "slice_b_ordinary_user.json").read_text()
    )
    assert {
        "effective_as_of_date": first.normalized_request.effective_as_of_date.isoformat(),
        "effective_forecast_season": first.normalized_request.effective_forecast_season,
        "request_id": first.request_id,
        "request_status": first.request_status,
        "scenario_config_hash": first.provenance["scenario_config_hash"],
        "tool_order": first_calls,
    } == golden


def test_static_calendar_policy_is_not_wall_clock_dependent() -> None:
    policy = StaticSeasonCalendarPolicy()
    kwargs = {
        "request_received_at": datetime(2026, 3, 1, tzinfo=UTC),
        "requested_as_of_date": date(2026, 2, 28),
        "requested_forecast_season": 2026,
    }
    assert policy.resolve(**kwargs) == policy.resolve(**kwargs)
    assert len(policy.config_hash) == 64


def test_policy_hashes_are_derived_from_policy_payload() -> None:
    uncertainty = AgentOrchestrator._policy_placeholder_uncertainty()
    changed_uncertainty = uncertainty.model_copy(
        update={
            "factors_by_source_level": {
                **uncertainty.factors_by_source_level,
                "step_5_variety_document_prior_only": "2.100",
            }
        }
    )
    changed_uncertainty = changed_uncertainty.model_copy(
        update={
            "config_hash": sha256_payload(
                changed_uncertainty.model_dump(mode="python", exclude={"config_hash"})
            )
        }
    )
    peak = AgentOrchestrator._policy_placeholder_peak()
    changed_peak = peak.model_copy(update={"high_load_threshold_ratio": "0.800"})
    changed_peak = changed_peak.model_copy(
        update={
            "policy_config_hash": sha256_payload(
                changed_peak.model_dump(mode="python", exclude={"policy_config_hash"})
            )
        }
    )
    assert uncertainty.config_hash != changed_uncertainty.config_hash
    assert peak.policy_config_hash != changed_peak.policy_config_hash


def test_unsupported_tool_is_blocked_before_dispatch() -> None:
    with pytest.raises(UnsupportedToolError):
        AgentOrchestrator.supported_tool("RUN_BACKTEST")


@pytest.mark.asyncio
async def test_as_of_override_is_applied_before_season_resolution() -> None:
    request = _request().model_copy(
        update={
            "requested_as_of_date": date(2026, 12, 31),
            "requested_forecast_season": None,
            "advanced_overrides": AdvancedOverrides(
                as_of_overrides=[
                    AsOfOverride(
                        value=date(2027, 1, 1),
                        source_attestation="test-attestation",
                    )
                ]
            ),
        }
    )
    normalized, _ = await _orchestrator([])._normalize(
        None, request, datetime(2026, 12, 31, tzinfo=UTC)
    )
    assert normalized.effective_as_of_date == date(2027, 1, 1)
    assert normalized.effective_forecast_season == 2027
    assert normalized.requested_as_of_date_provenance.override_applied is True


@pytest.mark.asyncio
async def test_missing_runtime_policies_are_blockers() -> None:
    calls: list[str] = []
    orchestrator = AgentOrchestrator(
        season_calendar=StaticSeasonCalendarPolicy(),
        location_adapter=_Location(calls),
        parameter_adapter=_Parameters(calls),
        daily_curve_adapter=_Daily(calls),
        peak_adapter=_Peak(calls),
    )
    output = await orchestrator.execute(
        None, request=_request(), request_received_at=datetime(2026, 3, 1, tzinfo=UTC)
    )
    assert output.request_status == "BLOCKED"
    assert {blocker.code.value for blocker in output.blockers} == {
        "UNCERTAINTY_WIDENING_POLICY_MISSING",
        "PEAK_POLICY_MISSING",
    }
    assert calls == ["RESOLVE_LOCATION"]


@pytest.mark.asyncio
async def test_unexpected_adapter_error_is_stable_internal_failure() -> None:
    orchestrator = _orchestrator([])
    orchestrator._location = _BrokenLocation()
    output = await orchestrator.execute(
        None, request=_request(), request_received_at=datetime(2026, 3, 1, tzinfo=UTC)
    )
    assert output.request_status == "BLOCKED"
    assert [blocker.code.value for blocker in output.blockers] == ["INTERNAL_FAILURE"]
    assert "secret traceback" not in output.blockers[0].message
