from datetime import UTC, date, datetime

import pytest

from backend.app.agent.orchestration import (
    AgentOrchestrator,
    StaticSeasonCalendarPolicy,
    UnsupportedToolError,
)
from backend.app.agent.schemas import (
    ForecastDailyCurveOutput,
    InferParametersOutput,
    LocationInput,
    MinimalInputRequest,
    MinimalVarietyInput,
    ResolvedLocation,
    ResolveLocationOutput,
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


def _request() -> MinimalInputRequest:
    return MinimalInputRequest(
        request_id="request-1",
        location=LocationInput(raw_text="Yunnan, China"),
        varieties=[MinimalVarietyInput(variety_id="101", planting_area_mu="100.0")],
    )


def _orchestrator(calls: list[str]) -> AgentOrchestrator:
    return AgentOrchestrator(
        location_adapter=_Location(calls),
        parameter_adapter=_Parameters(calls),
        daily_curve_adapter=_Daily(calls),
        peak_adapter=_Peak(calls),
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
    ]
    assert first.model_dump_json() == second.model_dump_json()
    assert first.provenance["agent_forecast_output_hash"]


def test_static_calendar_policy_is_not_wall_clock_dependent() -> None:
    policy = StaticSeasonCalendarPolicy()
    kwargs = {
        "request_received_at": datetime(2026, 3, 1, tzinfo=UTC),
        "requested_as_of_date": date(2026, 2, 28),
        "requested_forecast_season": 2026,
    }
    assert policy.resolve(**kwargs) == policy.resolve(**kwargs)
    assert len(policy.config_hash) == 64


def test_unsupported_tool_is_blocked_before_dispatch() -> None:
    with pytest.raises(UnsupportedToolError):
        AgentOrchestrator.supported_tool("RUN_BACKTEST")
