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
from backend.app.agent.adapters.scenario import DefaultScenarioAdapter
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
    SimulateScenarioInput,
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
    {
        "RESOLVE_LOCATION",
        "INFER_PARAMETERS",
        "FORECAST_DAILY_CURVE",
        "FORECAST_PEAK",
        "SIMULATE_SCENARIO",
    }
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
        scenario_adapter: _AsyncAdapter | None = None,
        uncertainty_widening_policy: UncertaintyWideningPolicy | None = None,
        peak_metric_policy: PeakMetricPolicy | None = None,
    ) -> None:
        self._season_calendar = season_calendar
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
        self._scenario = scenario_adapter or DefaultScenarioAdapter()
        self._uncertainty_policy = self._canonical_uncertainty_policy(uncertainty_widening_policy)
        self._peak_policy = self._canonical_peak_policy(peak_metric_policy)

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
        try:
            return await self._execute(
                session,
                request=request,
                request_received_at=request_received_at,
            )
        except Exception:
            return self._internal_failure_output(request, request_received_at)

    async def _execute(
        self,
        session: AsyncSession,
        *,
        request: MinimalInputRequest,
        request_received_at: datetime,
    ) -> AgentForecastOutput:
        if self._season_calendar is None:
            return self._internal_failure_output(
                request,
                request_received_at,
                code=BlockerCode.SEASON_CALENDAR_POLICY_MISSING,
                message="season calendar policy is not registered",
            )
        normalized, location = await self._normalize(session, request, request_received_at)
        blockers = list(location.blockers)
        if location.resolved_location.status != "resolved":
            fallback_code = (
                BlockerCode.LOCATION_AMBIGUOUS
                if location.resolved_location.status == "ambiguous"
                else BlockerCode.LOCATION_UNRESOLVED
            )
            if not any(blocker.code == fallback_code for blocker in blockers):
                blockers.append(
                    Blocker(
                        code=fallback_code,
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
                scenario=None,
            )

        missing_policy_blockers = self._missing_policy_blockers()
        if missing_policy_blockers:
            return self._output(
                normalized,
                location.resolved_location,
                [],
                None,
                None,
                missing_policy_blockers,
                location.location_catalog_version,
                scenario=None,
            )

        uncertainty = self._uncertainty_policy
        assert uncertainty is not None
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
        peak_policy = self._peak_policy
        assert peak_policy is not None
        peak = self._peak.execute(
            input=ForecastPeakInput(
                normalized_request=normalized,
                daily_curve=daily,
                peak_metric_policy=peak_policy,
            )
        )
        blockers.extend(peak.blockers)
        scenario = await self._scenario.execute(
            session,
            input=SimulateScenarioInput(
                normalized_request=normalized,
                resolved_location=location.resolved_location,
                parameters=parameter.parameters,
                scenario_overrides=(
                    request.advanced_overrides.scenario_overrides
                    if request.advanced_overrides is not None
                    else []
                ),
                uncertainty_widening_policy=uncertainty,
                peak_metric_policy=peak_policy,
                advanced_overrides=request.advanced_overrides,
            ),
        )
        blockers.extend(scenario.blockers)
        return self._output(
            normalized,
            location.resolved_location,
            parameter.parameters,
            daily,
            peak,
            blockers,
            location.location_catalog_version,
            scenario=scenario,
        )

    def _internal_failure_output(
        self,
        request: MinimalInputRequest,
        request_received_at: datetime,
        *,
        code: BlockerCode = BlockerCode.INTERNAL_FAILURE,
        message: str = "agent orchestration failed",
    ) -> AgentForecastOutput:
        safe_received_at = (
            request_received_at
            if request_received_at.tzinfo is not None
            else request_received_at.replace(tzinfo=UTC)
        )
        effective_as_of = request.requested_as_of_date or safe_received_at.date()
        season = request.requested_forecast_season or effective_as_of.year
        normalized = NormalizedAgentRequest(
            request_id=request.request_id,
            request_received_at=safe_received_at,
            effective_as_of_date=effective_as_of,
            effective_forecast_season=season,
            season_resolution_policy_version="unresolved",
            season_calendar_config_hash=sha256_payload({"status": "unresolved"}),
            requested_as_of_date_provenance=RequestedAsOfDateProvenance(
                caller_requested_as_of_date=request.requested_as_of_date,
                effective_as_of_date=effective_as_of,
                override_applied=False,
                override_kind=None,
                source_attestation=None,
                source_ref=None,
            ),
            normalized_location=ResolvedLocation(
                status="unresolved", matched_location_method="REFERENCE_ID"
            ),
            location_input=request.location,
            varieties=[
                NormalizedVarietyInput(
                    variety_id=item.variety_id,
                    planting_area_mu=item.planting_area_mu,
                )
                for item in request.varieties
            ],
            advanced_overrides=request.advanced_overrides,
            canonical_request_hash="0" * 64,
        )
        normalized = normalized.model_copy(
            update={"canonical_request_hash": sha256_payload(normalized.model_dump(mode="python"))}
        )
        blocker = Blocker(
            code=code,
            message=message,
            details={"request_id": request.request_id},
            retry_hint="CONTACT_OPS",
        )
        return self._output(
            normalized,
            normalized.normalized_location,
            [],
            None,
            None,
            [blocker],
            "unresolved",
            scenario=None,
        )

    async def _normalize(
        self, session: AsyncSession, request: MinimalInputRequest, received_at: datetime
    ) -> tuple[NormalizedAgentRequest, Any]:
        override = (
            request.advanced_overrides.as_of_overrides[0]
            if request.advanced_overrides and request.advanced_overrides.as_of_overrides
            else None
        )
        if self._season_calendar is None:
            raise ValueError("season calendar policy is not registered")
        resolution = self._season_calendar.resolve(
            request_received_at=received_at,
            requested_as_of_date=override.value if override else request.requested_as_of_date,
            requested_forecast_season=request.requested_forecast_season,
        )
        effective_as_of = resolution.effective_as_of_date
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
        scenario: Any | None,
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
        uncertainty_version, uncertainty_hash = self._policy_identity(
            self._uncertainty_policy, kind="uncertainty"
        )
        peak_version, peak_hash = self._policy_identity(self._peak_policy, kind="peak")
        prior_versions = sorted(
            {
                str(p.citation.confidence_evidence["prior_version"])
                for p in parameters
                if p.citation
                and p.citation.confidence_evidence
                and p.citation.confidence_evidence.get("prior_version") is not None
            }
        )
        confidence_evidence = self._confidence_evidence(parameters)
        provenance: dict[str, Any] = {
            "requested_as_of_date_provenance": (
                normalized.requested_as_of_date_provenance.model_dump(mode="json")
            ),
            **authorities,
            "parameter_version_identities": prior_versions,
            "prior_versions_used": prior_versions,
            "location_catalog_version": catalog_version,
            "scenario_config_hash": (
                scenario.scenario_config_hash if scenario is not None else None
            ),
            "effective_as_of_date": normalized.effective_as_of_date,
            "effective_forecast_season": normalized.effective_forecast_season,
            "season_resolution_policy_version": normalized.season_resolution_policy_version,
            "season_calendar_config_hash": normalized.season_calendar_config_hash,
            "uncertainty_widening_policy_version": uncertainty_version,
            "uncertainty_widening_policy_config_hash": uncertainty_hash,
            "peak_metric_policy_version": peak_version,
            "peak_metric_policy_config_hash": peak_hash,
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
                "evidence": confidence_evidence,
            },
            uncertainty_widening_policy_version=uncertainty_version,
            uncertainty_widening_policy_config_hash=uncertainty_hash,
            peak_metric_policy_version=peak_version,
            peak_metric_policy_config_hash=peak_hash,
            provenance=provenance,
            blockers=ordered,
            warnings=[],
        )
        payload = output.model_dump(mode="python")
        payload["provenance"]["agent_forecast_output_hash"] = sha256_payload(payload)
        return output.model_copy(update={"provenance": payload["provenance"]})

    @staticmethod
    def _canonical_uncertainty_policy(
        policy: UncertaintyWideningPolicy | None,
    ) -> UncertaintyWideningPolicy | None:
        if policy is None:
            return None
        return policy.model_copy(
            update={
                "config_hash": sha256_payload(
                    policy.model_dump(mode="python", exclude={"config_hash"})
                )
            }
        )

    @staticmethod
    def _canonical_peak_policy(policy: PeakMetricPolicy | None) -> PeakMetricPolicy | None:
        if policy is None:
            return None
        return policy.model_copy(
            update={
                "policy_config_hash": sha256_payload(
                    policy.model_dump(mode="python", exclude={"policy_config_hash"})
                )
            }
        )

    @staticmethod
    def _confidence(parameters: list[Any]) -> str:
        if not parameters:
            return "LOW"
        rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        return str(max(parameters, key=lambda item: rank.get(item.confidence, 2)).confidence)

    @staticmethod
    def _confidence_evidence(parameters: list[Any]) -> dict[str, Any]:
        evidence: dict[str, Any] = {
            "parameter_count": len(parameters),
            "sample_count": sum(int(item.sample_count) for item in parameters),
            "covered_seasons": sorted(
                {
                    season
                    for item in parameters
                    for season in (
                        item.citation.confidence_evidence.get("covered_seasons", [])
                        if item.citation and item.citation.confidence_evidence
                        else []
                    )
                }
            ),
            "historical_mape": sorted(
                {
                    str(item.citation.confidence_evidence["historical_mape"])
                    for item in parameters
                    if item.citation
                    and item.citation.confidence_evidence
                    and item.citation.confidence_evidence.get("historical_mape") is not None
                }
            ),
            "historical_date_mae": sorted(
                {
                    str(item.citation.confidence_evidence["historical_date_mae"])
                    for item in parameters
                    if item.citation
                    and item.citation.confidence_evidence
                    and item.citation.confidence_evidence.get("historical_date_mae") is not None
                }
            ),
            "p90_coverage_rate": sorted(
                {
                    str(item.citation.confidence_evidence["p90_coverage_rate"])
                    for item in parameters
                    if item.citation
                    and item.citation.confidence_evidence
                    and item.citation.confidence_evidence.get("p90_coverage_rate") is not None
                }
            ),
            "key_missing_items": sorted(
                {missing for item in parameters for missing in item.missing_evidence}
            ),
        }
        return evidence

    @staticmethod
    def _policy_identity(
        policy: UncertaintyWideningPolicy | PeakMetricPolicy | None,
        *,
        kind: str,
    ) -> tuple[str, str]:
        if policy is None:
            return "unresolved", sha256_payload({"kind": kind, "status": "unresolved"})
        if isinstance(policy, UncertaintyWideningPolicy):
            return policy.policy_version, policy.config_hash
        return policy.policy_version, policy.policy_config_hash

    def _missing_policy_blockers(self) -> list[Blocker]:
        blockers: list[Blocker] = []
        if self._uncertainty_policy is None:
            blockers.append(
                Blocker(
                    code=BlockerCode.UNCERTAINTY_WIDENING_POLICY_MISSING,
                    message="uncertainty widening policy is not registered",
                    retry_hint="CONTACT_OPS",
                )
            )
        if self._peak_policy is None:
            blockers.append(
                Blocker(
                    code=BlockerCode.PEAK_POLICY_MISSING,
                    message="peak metric policy is not registered",
                    retry_hint="CONTACT_OPS",
                )
            )
        return blockers


__all__ = [
    "AgentOrchestrator",
    "SeasonResolution",
    "StaticSeasonCalendarPolicy",
    "UnsupportedToolError",
]
