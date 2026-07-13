"""Deterministic TASK-013 Slice B agent orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agent.adapters.daily_curve import DefaultDailyCurveAdapter
from backend.app.agent.adapters.location import DefaultLocationAdapter
from backend.app.agent.adapters.parameters import DefaultParameterAdapter
from backend.app.agent.adapters.peak import DefaultPeakAdapter
from backend.app.agent.canonical import canonical_json_dumps, sha256_payload
from backend.app.agent.enums import BlockerCode
from backend.app.agent.schemas import (
    AgentForecastOutput,
    Blocker,
    ForecastDailyCurveInput,
    ForecastPeakInput,
    InferParametersInput,
    MinimalInputRequest,
    NormalizedAgentRequest,
    NormalizedVarietyInput,
    PeakMetricPolicy,
    RequestedAsOfDateProvenance,
    ResolvedLocation,
    ResolveLocationInput,
    UncertaintyWideningPolicy,
)


class UnsupportedToolError(ValueError):
    """Raised when a tool is outside the Slice B allowlist."""


class SeasonCalendarPolicy(Protocol):
    policy_version: str
    config_hash: str

    def resolve(
        self,
        *,
        request_received_at: datetime,
        requested_as_of_date: date | None,
        requested_forecast_season: int | None,
    ) -> SeasonResolution: ...


@dataclass(frozen=True)
class SeasonResolution:
    effective_as_of_date: date
    effective_forecast_season: int
    policy_version: str
    config_hash: str


@dataclass(frozen=True)
class StaticSeasonCalendarPolicy:
    """Explicit deterministic fallback policy; never reads the wall clock."""

    policy_version: str = "season-calendar/v1"
    config_hash: str = ""

    def __post_init__(self) -> None:
        if not self.config_hash:
            object.__setattr__(
                self,
                "config_hash",
                sha256_payload(
                    {
                        "policy_version": self.policy_version,
                        "as_of_source": "request_received_at.date",
                        "season_source": "effective_as_of_date.year",
                    }
                ),
            )

    def resolve(
        self,
        *,
        request_received_at: datetime,
        requested_as_of_date: date | None,
        requested_forecast_season: int | None,
    ) -> SeasonResolution:
        if request_received_at.tzinfo is None or request_received_at.utcoffset() != UTC.utcoffset(
            request_received_at
        ):
            raise ValueError("request_received_at must be aware UTC")
        as_of = requested_as_of_date or request_received_at.date()
        season = requested_forecast_season or as_of.year
        if season < 1:
            raise ValueError("effective_forecast_season must be positive")
        return SeasonResolution(as_of, season, self.policy_version, self.config_hash)


_TOOLS = frozenset(
    {"RESOLVE_LOCATION", "INFER_PARAMETERS", "FORECAST_DAILY_CURVE", "FORECAST_PEAK"}
)


class _AsyncAdapter(Protocol):
    async def execute(self, session: AsyncSession, *, input: Any) -> Any: ...


class AgentOrchestrator:
    """Compose Slice A adapters in one fixed, side-effect-free order."""

    def __init__(
        self,
        *,
        season_calendar: SeasonCalendarPolicy | None = None,
        location_adapter: _AsyncAdapter | None = None,
        parameter_adapter: _AsyncAdapter | None = None,
        daily_curve_adapter: _AsyncAdapter | None = None,
        peak_adapter: Any | None = None,
        uncertainty_widening_policy: UncertaintyWideningPolicy | None = None,
        peak_metric_policy: PeakMetricPolicy | None = None,
    ) -> None:
        self._season_calendar = season_calendar or StaticSeasonCalendarPolicy()
        if location_adapter is None:
            from backend.app.planning.config import load_parameter_inference_config

            config = load_parameter_inference_config(
                Path(__file__).resolve().parents[3] / "configs" / "parameter_inference.yaml"
            )
            location_adapter = DefaultLocationAdapter(rules=config.rules)
        self._location = location_adapter
        self._parameters = parameter_adapter or DefaultParameterAdapter()
        self._daily_curve = daily_curve_adapter or DefaultDailyCurveAdapter()
        self._peak = peak_adapter or DefaultPeakAdapter()
        self._uncertainty_policy = uncertainty_widening_policy
        self._peak_policy = peak_metric_policy

    @staticmethod
    def supported_tool(tool_name: str) -> str:
        if tool_name not in _TOOLS:
            raise UnsupportedToolError(f"tool is not executable in Slice B: {tool_name}")
        return tool_name

    async def execute(
        self,
        session: AsyncSession,
        *,
        request: MinimalInputRequest,
        request_received_at: datetime,
    ) -> AgentForecastOutput:
        normalized, location = await self._normalize(session, request, request_received_at)
        blockers = list(location.blockers)
        if location.resolved_location.status != "resolved":
            blockers.append(
                Blocker(
                    code=(
                        BlockerCode.LOCATION_AMBIGUOUS
                        if location.resolved_location.status == "ambiguous"
                        else BlockerCode.LOCATION_UNRESOLVED
                    ),
                    message="location did not resolve to exactly one authoritative location",
                    details={"status": location.resolved_location.status},
                    retry_hint="FIX_INPUT",
                )
            )
            return self._output(
                normalized,
                location.resolved_location,
                [],
                None,
                None,
                blockers,
                location.location_catalog_version,
            )

        uncertainty = self._uncertainty_policy or self._default_uncertainty_policy()
        parameter = await self._parameters.execute(
            session,
            input=InferParametersInput(
                normalized_request=normalized,
                resolved_location=location.resolved_location,
                uncertainty_widening_policy=uncertainty,
            ),
        )
        blockers.extend(parameter.blockers)
        daily = await self._daily_curve.execute(
            session,
            input=ForecastDailyCurveInput(
                normalized_request=normalized,
                resolved_location=location.resolved_location,
                parameters=parameter.parameters,
                advanced_overrides=request.advanced_overrides,
                uncertainty_widening_policy=uncertainty,
            ),
        )
        blockers.extend(daily.blockers)
        peak_policy = self._peak_policy or self._default_peak_policy()
        peak = self._peak.execute(
            input=ForecastPeakInput(
                normalized_request=normalized,
                daily_curve=daily,
                peak_metric_policy=peak_policy,
            )
        )
        blockers.extend(peak.blockers)
        return self._output(
            normalized,
            location.resolved_location,
            parameter.parameters,
            daily,
            peak,
            blockers,
            location.location_catalog_version,
        )

    async def _normalize(
        self, session: AsyncSession, request: MinimalInputRequest, received_at: datetime
    ) -> tuple[NormalizedAgentRequest, Any]:
        resolution = self._season_calendar.resolve(
            request_received_at=received_at,
            requested_as_of_date=request.requested_as_of_date,
            requested_forecast_season=request.requested_forecast_season,
        )
        override = (
            request.advanced_overrides.as_of_overrides[0]
            if request.advanced_overrides and request.advanced_overrides.as_of_overrides
            else None
        )
        effective_as_of = override.value if override else resolution.effective_as_of_date
        provenance = RequestedAsOfDateProvenance(
            caller_requested_as_of_date=request.requested_as_of_date,
            effective_as_of_date=effective_as_of,
            override_applied=override is not None,
            override_kind="AS_OF_OVERRIDE" if override else None,
            source_attestation=override.source_attestation if override else None,
            source_ref=override.source_ref if override else None,
        )
        provisional = NormalizedAgentRequest(
            request_id=request.request_id,
            request_received_at=received_at,
            effective_as_of_date=effective_as_of,
            effective_forecast_season=resolution.effective_forecast_season,
            season_resolution_policy_version=resolution.policy_version,
            season_calendar_config_hash=resolution.config_hash,
            requested_as_of_date_provenance=provenance,
            normalized_location=ResolvedLocation(
                status="unresolved", matched_location_method="REFERENCE_ID"
            ),
            location_input=request.location,
            varieties=[
                NormalizedVarietyInput(
                    variety_id=item.variety_id, planting_area_mu=item.planting_area_mu
                )
                for item in request.varieties
            ],
            advanced_overrides=request.advanced_overrides,
            canonical_request_hash="0" * 64,
        )
        output = await self._location.execute(
            session,
            input=ResolveLocationInput(
                normalized_request=provisional, location_input=request.location
            ),
        )
        normalized = provisional.model_copy(
            update={"normalized_location": output.resolved_location}
        )
        normalized = normalized.model_copy(
            update={"canonical_request_hash": sha256_payload(normalized.model_dump(mode="python"))}
        )
        return normalized, output

    def _output(
        self,
        normalized: NormalizedAgentRequest,
        location: Any,
        parameters: list[Any],
        daily: Any | None,
        peak: Any | None,
        blockers: list[Blocker],
        catalog_version: str,
    ) -> AgentForecastOutput:
        unique = {canonical_json_dumps(b.model_dump(mode="json")): b for b in blockers}
        ordered = [unique[key] for key in sorted(unique)]
        status = (
            "OK"
            if not ordered
            else (
                "PARTIAL"
                if all(b.code == BlockerCode.UNKNOWN_VARIETY for b in ordered)
                else "BLOCKED"
            )
        )
        authorities = {
            f"task{number}_authority": (
                getattr(daily, f"task{number}_authority").model_dump(mode="json")
                if daily is not None and getattr(daily, f"task{number}_authority", None) is not None
                else None
            )
            for number in (8, 9, 10, 11, 12)
        }
        uncertainty = self._uncertainty_policy or self._default_uncertainty_policy()
        peak_policy = self._peak_policy or self._default_peak_policy()
        prior_versions = sorted(
            {
                str(p.citation.confidence_evidence["prior_version"])
                for p in parameters
                if p.citation and p.citation.confidence_evidence.get("prior_version") is not None
            }
        )
        provenance: dict[str, Any] = {
            "requested_as_of_date_provenance": (
                normalized.requested_as_of_date_provenance.model_dump(mode="json")
            ),
            **authorities,
            "parameter_version_identities": prior_versions,
            "prior_versions_used": prior_versions,
            "location_catalog_version": catalog_version,
            "effective_as_of_date": normalized.effective_as_of_date,
            "effective_forecast_season": normalized.effective_forecast_season,
            "season_resolution_policy_version": normalized.season_resolution_policy_version,
            "season_calendar_config_hash": normalized.season_calendar_config_hash,
            "uncertainty_widening_policy_version": uncertainty.policy_version,
            "uncertainty_widening_policy_config_hash": uncertainty.config_hash,
            "peak_metric_policy_version": peak_policy.policy_version,
            "peak_metric_policy_config_hash": peak_policy.policy_config_hash,
            "agent_daily_curve_hash": getattr(daily, "agent_daily_curve_hash", None),
            "agent_peak_hash": getattr(peak, "agent_peak_hash", None),
            "agent_forecast_output_hash": None,
        }
        output = AgentForecastOutput(
            request_id=normalized.request_id,
            request_status=status,
            normalized_request=normalized,
            resolved_location=location,
            parameters=parameters,
            daily_curve=list(getattr(daily, "per_day", [])),
            peak=peak.model_dump(mode="json") if peak is not None else {},
            recommendations=[],
            explanation={},
            confidence={
                "level": self._confidence(parameters),
                "evidence": {"parameter_count": len(parameters)},
            },
            uncertainty_widening_policy_version=uncertainty.policy_version,
            uncertainty_widening_policy_config_hash=uncertainty.config_hash,
            peak_metric_policy_version=peak_policy.policy_version,
            peak_metric_policy_config_hash=peak_policy.policy_config_hash,
            provenance=provenance,
            blockers=ordered,
            warnings=[],
        )
        payload = output.model_dump(mode="python")
        payload["provenance"]["agent_forecast_output_hash"] = sha256_payload(payload)
        return output.model_copy(update={"provenance": payload["provenance"]})

    @staticmethod
    def _confidence(parameters: list[Any]) -> str:
        if not parameters:
            return "LOW"
        rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        return str(max(parameters, key=lambda item: rank.get(item.confidence, 2)).confidence)

    @staticmethod
    def _default_uncertainty_policy() -> UncertaintyWideningPolicy:
        return UncertaintyWideningPolicy(
            policy_version="uncertainty-widening/v1",
            config_hash="b" * 64,
            factors_by_source_level={
                "step_1_same_farm_same_variety_high_evidence": "1.000",
                "step_2_same_township_similar_altitude": "1.250",
                "step_3_same_county_same_climate_zone": "1.500",
                "step_4_province_level_same_variety": "1.750",
                "step_5_variety_document_prior_only": "2.000",
            },
        )

    @staticmethod
    def _default_peak_policy() -> PeakMetricPolicy:
        return PeakMetricPolicy(
            policy_version="peak-metric/v1",
            policy_config_hash="c" * 64,
            sustained_window_days=3,
            peak_window_days_before=7,
            peak_window_days_after=7,
            high_load_threshold_ratio="0.900",
        )


__all__ = [
    "AgentOrchestrator",
    "SeasonResolution",
    "StaticSeasonCalendarPolicy",
    "UnsupportedToolError",
]
