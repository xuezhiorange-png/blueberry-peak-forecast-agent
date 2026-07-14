"""Deterministic TASK-013 Slice B agent orchestration."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast

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
    Citation,
    CitationAuthorityEntry,
    CitationOverrideRef,
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
    Task8Authority,
    UncertaintyWideningPolicy,
)
from backend.app.agent.season_resolution import (
    DatabaseForecastSeasonResolver,
    ForecastSeasonResolver,
)
from backend.app.agent.slice_c.engine import build_slice_c_outputs


class UnsupportedToolError(ValueError):
    """Raised when a tool is outside the Slice B allowlist."""


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
        season_resolver: ForecastSeasonResolver | None = None,
        location_adapter: _AsyncAdapter | None = None,
        parameter_adapter: _AsyncAdapter | None = None,
        daily_curve_adapter: _AsyncAdapter | None = None,
        peak_adapter: Any | None = None,
        scenario_adapter: _AsyncAdapter | None = None,
        uncertainty_widening_policy: UncertaintyWideningPolicy | None = None,
        peak_metric_policy: PeakMetricPolicy | None = None,
    ) -> None:
        self._season_resolver = season_resolver or DatabaseForecastSeasonResolver()
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
        normalized, location, season_blocker = await self._normalize(
            session, request, request_received_at
        )
        if season_blocker is not None:
            return self._output(
                normalized,
                normalized.normalized_location,
                [],
                None,
                None,
                [season_blocker],
                "unresolved",
                scenario=None,
            )
        assert location is not None
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
        normalized = NormalizedAgentRequest(
            request_id=request.request_id,
            request_received_at=safe_received_at,
            effective_as_of_date=effective_as_of,
            requested_forecast_season=request.requested_forecast_season,
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
    ) -> tuple[NormalizedAgentRequest, Any | None, Blocker | None]:
        override = (
            request.advanced_overrides.as_of_overrides[0]
            if request.advanced_overrides and request.advanced_overrides.as_of_overrides
            else None
        )
        effective_as_of = override.value if override else request.requested_as_of_date
        effective_as_of = effective_as_of or received_at.date()
        resolution = await self._season_resolver.resolve(
            session,
            effective_as_of_date=effective_as_of,
            requested_forecast_season=request.requested_forecast_season,
        )
        provenance = RequestedAsOfDateProvenance(
            caller_requested_as_of_date=request.requested_as_of_date,
            effective_as_of_date=effective_as_of,
            override_applied=override is not None,
            override_kind="AS_OF_OVERRIDE" if override else None,
            source_attestation=override.source_attestation if override else None,
            source_ref=override.source_ref if override else None,
        )
        season_identity = resolution.identity
        provisional = NormalizedAgentRequest(
            request_id=request.request_id,
            request_received_at=received_at,
            effective_as_of_date=effective_as_of,
            requested_forecast_season=request.requested_forecast_season,
            effective_forecast_season_id=(
                season_identity.season_snapshot.season_id if season_identity else None
            ),
            effective_forecast_season_code=(
                season_identity.season_snapshot.season_code if season_identity else None
            ),
            season_record_hash=(
                season_identity.season_snapshot.season_record_hash if season_identity else None
            ),
            season_resolution_policy_version=(
                season_identity.season_resolution_policy_version if season_identity else None
            ),
            season_resolution_policy_config_hash=(
                season_identity.season_resolution_policy_config_hash if season_identity else None
            ),
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
        if resolution.blocker is not None:
            normalized = provisional.model_copy(
                update={
                    "canonical_request_hash": sha256_payload(provisional.model_dump(mode="python"))
                }
            )
            return normalized, None, resolution.blocker
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
        return normalized, output, None

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
            "requested_forecast_season": normalized.requested_forecast_season,
            "effective_forecast_season_id": normalized.effective_forecast_season_id,
            "effective_forecast_season_code": normalized.effective_forecast_season_code,
            "season_record_hash": normalized.season_record_hash,
            "season_resolution_policy_version": normalized.season_resolution_policy_version,
            "season_resolution_policy_config_hash": (
                normalized.season_resolution_policy_config_hash
            ),
            "uncertainty_widening_policy_version": uncertainty_version,
            "uncertainty_widening_policy_config_hash": uncertainty_hash,
            "peak_metric_policy_version": peak_version,
            "peak_metric_policy_config_hash": peak_hash,
            "agent_daily_curve_hash": getattr(daily, "agent_daily_curve_hash", None),
            "agent_peak_hash": getattr(peak, "agent_peak_hash", None),
            "agent_forecast_output_hash": None,
        }
        confidence = {
            "level": self._confidence(parameters),
            "evidence": confidence_evidence,
        }
        parameters = self._slice_c_parameters(
            normalized=normalized,
            parameters=parameters,
            daily=daily,
        )
        citations = self._slice_c_citations(
            normalized=normalized,
            parameters=parameters,
            daily=daily,
            peak=peak,
            provenance=provenance,
        )
        source_payload: dict[str, Any] = {
            "request_id": normalized.request_id,
            "request_status": status,
            "normalized_request": normalized.model_dump(mode="json"),
            "resolved_location": location.model_dump(mode="json"),
            "parameters": [parameter.model_dump(mode="json") for parameter in parameters],
            "daily_curve": [row.model_dump(mode="json") for row in getattr(daily, "per_day", [])],
            "peak": peak.model_dump(mode="json") if peak is not None else {},
            "citations": [citation.model_dump(mode="json") for citation in citations],
            "confidence": confidence,
            "provenance": provenance,
            "blockers": [blocker.model_dump(mode="json") for blocker in ordered],
            "warnings": [],
        }
        explanation, recommendations = build_slice_c_outputs(source_payload)
        output = AgentForecastOutput(
            request_id=normalized.request_id,
            request_status=status,
            normalized_request=normalized,
            resolved_location=location,
            parameters=parameters,
            daily_curve=list(getattr(daily, "per_day", [])),
            peak=peak.model_dump(mode="json") if peak is not None else {},
            citations=citations,
            recommendations=recommendations,
            explanation=explanation,
            confidence=confidence,
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
    def _override_refs(
        normalized: NormalizedAgentRequest,
        *,
        include_scenario: bool = False,
    ) -> list[CitationOverrideRef]:
        overrides = normalized.advanced_overrides
        if overrides is None:
            return []
        values: list[Any] = [
            *overrides.as_of_overrides,
            *overrides.parameter_overrides,
            *overrides.authority_overrides,
        ]
        if include_scenario:
            values.extend(overrides.scenario_overrides)
        return [
            CitationOverrideRef(
                override_ref_id=sha256_payload(value.model_dump(mode="python")),
                override_kind=value.override_kind,
                target=getattr(value, "target", getattr(value, "target_parameter", None)),
                source_attestation=value.source_attestation,
                source_ref=value.source_ref,
            )
            for value in values
        ]

    @staticmethod
    def _parameter_override_refs(
        normalized: NormalizedAgentRequest,
        *,
        parameter_name: str,
        variety_id: str,
    ) -> list[CitationOverrideRef]:
        overrides = normalized.advanced_overrides
        if overrides is None:
            return []
        values: list[Any] = [*overrides.as_of_overrides]
        values.extend(
            item
            for item in overrides.parameter_overrides
            if item.variety_id == variety_id and item.target_parameter.lower() == parameter_name
        )
        values.extend(
            item for item in overrides.authority_overrides if item.target == "TASK8_FORECAST_RUN"
        )
        return [
            CitationOverrideRef(
                override_ref_id=sha256_payload(value.model_dump(mode="python")),
                override_kind=value.override_kind,
                target=getattr(value, "target", getattr(value, "target_parameter", None)),
                source_attestation=value.source_attestation,
                source_ref=value.source_ref,
            )
            for value in values
        ]

    @staticmethod
    def _authority_entries(daily: Any | None) -> list[CitationAuthorityEntry]:
        entries: list[CitationAuthorityEntry] = []
        if daily is None:
            return entries
        for number in (8, 9, 10, 11, 12):
            authority = getattr(daily, f"task{number}_authority", None)
            if authority is not None:
                entries.append(
                    CitationAuthorityEntry.model_validate(
                        {
                            "authority_type": f"TASK_{number}_AUTHORITY",
                            "authority": authority.model_dump(mode="python"),
                        }
                    )
                )
        return entries

    @classmethod
    def _slice_c_parameters(
        cls,
        *,
        normalized: NormalizedAgentRequest,
        parameters: list[Any],
        daily: Any | None,
    ) -> list[Any]:
        task8 = next(
            (
                entry
                for entry in cls._authority_entries(daily)
                if entry.authority_type == "TASK_8_AUTHORITY"
            ),
            None,
        )
        if task8 is None:
            return parameters
        task8_authority = cast(Task8Authority, task8.authority)
        artifact_hash = task8_authority.maturity_model_artifact_hash
        enriched: list[Any] = []
        for index, parameter in enumerate(parameters):
            citation = getattr(parameter, "citation", None)
            if citation is None:
                enriched.append(parameter)
                continue
            override_refs = cls._parameter_override_refs(
                normalized,
                parameter_name=parameter.parameter_name,
                variety_id=parameter.variety_id,
            )
            enriched_citation = citation.model_copy(
                update={
                    "source_tasks": ["TASK_008"],
                    "authorities": [task8],
                    "agent_artifact_hash": artifact_hash,
                    "field_path": f"/parameters/{index}/p50",
                    "tags": ["OVERRIDE_APPLIED"] if override_refs else [],
                    "override_refs": override_refs,
                }
            )
            enriched.append(parameter.model_copy(update={"citation": enriched_citation}))
        return enriched

    @classmethod
    def _slice_c_citations(
        cls,
        *,
        normalized: NormalizedAgentRequest,
        parameters: list[Any],
        daily: Any | None,
        peak: Any | None,
        provenance: dict[str, Any],
    ) -> list[Citation]:
        citations: list[Citation] = []
        entries = cls._authority_entries(daily)
        source_tasks = (
            [
                f"TASK_{number:03d}"
                for number in range(8, 13)
                if getattr(daily, f"task{number}_authority", None) is not None
            ]
            if daily is not None
            else []
        )
        override_refs = cls._override_refs(normalized)
        tags = ["OVERRIDE_APPLIED"] if override_refs else []

        for index, parameter in enumerate(parameters):
            citation = getattr(parameter, "citation", None)
            if citation is not None and citation.field_path == f"/parameters/{index}/p50":
                citations.append(citation)

        if entries:
            for index, row in enumerate(getattr(daily, "per_day", [])):
                citations.append(
                    Citation(
                        source_tasks=source_tasks,
                        source_tool="FORECAST_DAILY_CURVE",
                        authorities=entries,
                        agent_artifact_hash=row.agent_daily_row_hash,
                        field_path=(
                            f"/daily_curve/{index}/final_corrected_arrival_quantity_kg/p50"
                        ),
                        effective_as_of_date=normalized.effective_as_of_date,
                        confidence_evidence=None,
                        tags=tags,
                        override_refs=override_refs,
                    )
                )
            if peak is not None:
                for field_path in (
                    "/peak/single_day_peak/P50/volume_kg",
                    "/peak/sustained_3day_peak/P50/rolling_daily_average_kg_per_day",
                ):
                    citations.append(
                        Citation(
                            source_tasks=source_tasks,
                            source_tool="FORECAST_PEAK",
                            authorities=entries,
                            agent_artifact_hash=peak.agent_peak_hash,
                            field_path=field_path,
                            effective_as_of_date=normalized.effective_as_of_date,
                            confidence_evidence=None,
                            tags=tags,
                            override_refs=override_refs,
                        )
                    )
        for number in (8, 9, 10, 11, 12):
            authority = provenance.get(f"task{number}_authority")
            if authority is None:
                continue
            entry = CitationAuthorityEntry.model_validate(
                {"authority_type": f"TASK_{number}_AUTHORITY", "authority": authority}
            )
            citations.append(
                Citation(
                    source_tasks=[f"TASK_{number:03d}"],
                    source_tool="EXPLAIN_FORECAST",
                    authorities=[entry],
                    agent_artifact_hash=None,
                    field_path=f"/provenance/task{number}_authority",
                    effective_as_of_date=normalized.effective_as_of_date,
                    confidence_evidence=None,
                    tags=tags,
                    override_refs=override_refs,
                )
            )
        scenario_hash = provenance.get("scenario_config_hash")
        scenario_refs = cls._override_refs(normalized, include_scenario=True)
        scenario_refs = [
            item for item in scenario_refs if item.override_kind == "SCENARIO_OVERRIDE_KIND"
        ]
        if isinstance(scenario_hash, str) and scenario_refs:
            citations.append(
                Citation(
                    source_tasks=source_tasks,
                    source_tool="SIMULATE_SCENARIO",
                    authorities=entries,
                    agent_artifact_hash=scenario_hash,
                    field_path="/provenance/scenario_config_hash",
                    effective_as_of_date=normalized.effective_as_of_date,
                    confidence_evidence=None,
                    tags=["OVERRIDE_APPLIED"],
                    override_refs=scenario_refs,
                )
            )
        return citations

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
    "UnsupportedToolError",
]
