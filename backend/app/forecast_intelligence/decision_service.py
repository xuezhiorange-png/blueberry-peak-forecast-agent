"""S1 saved-run adapter and frozen S6 engine composition; no persistence writes."""

from datetime import datetime, time, timedelta
from typing import Any, NoReturn
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from backend.app.forecast_intelligence import what_if
from backend.app.forecast_intelligence.business_loss import (
    BUSINESS_LOSS_POLICY_VERSION,
    COST_CONTRACT_POLICY_VERSION,
    FORMULA,
    BusinessCostContract,
    synthetic_contracts,
)
from backend.app.forecast_intelligence.decision_schemas import (
    BusinessLossExposure,
    ComparisonData,
    ComparisonRequest,
    ComparisonResult,
    CostContractView,
    CostSelection,
    DecisionResponse,
    DecisionSelection,
    DirectCapacity,
    ScenarioInput,
    SimulationRequest,
    SimulationResult,
    decimal_input,
)
from backend.app.forecast_intelligence.read_schemas import (
    CurveData,
    ForecastReadQuery,
    ReadError,
    ReadModel,
    ReadResponse,
)
from backend.app.forecast_intelligence.read_service import (
    ForecastIntelligenceReadService,
    projection_digest,
)

ADAPTER_POLICY = "V0_17_S2_SAVED_FORECAST_DECISION_ADAPTER_R1"
BASE_KIND = "S2_ATOMIC_FORECAST_SCOPE_BINDING_NOT_REGISTRY_HIERARCHY"
BASE_BINDING_POLICY = "BASE_SCOPED_FORECAST_AUTHORITY_BINDING_R1"
ENGINE_POLICIES = {
    "business_loss": BUSINESS_LOSS_POLICY_VERSION,
    "cost_contract": COST_CONTRACT_POLICY_VERSION,
    "what_if": what_if.POLICY_VERSION,
    "capacity": what_if.CAPACITY_POLICY_VERSION,
    "backlog": what_if.BACKLOG_POLICY_VERSION,
    "loss_mapping": what_if.LOSS_MAPPING_POLICY_VERSION,
    "comparison": what_if.COMPARISON_POLICY_VERSION,
    "ranking": what_if.RANKING_POLICY_VERSION,
    "utilization": what_if.UTILIZATION_POLICY_VERSION,
}
COST_HASHES = {
    "SYNTHETIC_BALANCED_R1": "35f8316fbf2688b108e173d0d8438ce6323aa0f9db208f7a143f72e07aa5679f",
    "SYNTHETIC_UNDER_4X_R1": "8d6f2567a18bd298f1a261a059a88b2772d77bcc6f03e313dc3853c9cd2f0f3f",
    "SYNTHETIC_OVER_4X_R1": "6cec3474d85b6421467d43ff71fb6a52a4b4904289cded15c4fdcea74e49fe36",
}


def cost_contract(selection: CostSelection) -> BusinessCostContract:
    contracts = {c.contract_id: c for c in synthetic_contracts()}
    if {k: c.contract_hash for k, c in contracts.items()} != COST_HASHES:
        raise ReadError("UPSTREAM_COST_AUTHORITY_DRIFT", 409)
    if selection.cost_contract_id not in contracts:
        raise ReadError("COST_CONTRACT_NOT_FOUND", 404)
    cost = contracts[selection.cost_contract_id]
    if cost.contract_hash != selection.expected_cost_contract_hash:
        raise ReadError("COST_CONTRACT_HASH_MISMATCH", 409)
    return cost


def decision_response[T: ReadModel](data_type: type[T], **values: Any) -> DecisionResponse[T]:
    result = DecisionResponse[data_type](  # type: ignore[valid-type]
        engine_policy_versions=ENGINE_POLICIES, projection_hash="0" * 64, **values
    )
    return result.model_copy(
        update={
            "projection_hash": projection_digest(
                result.model_dump(mode="json", exclude={"projection_hash"})
            )
        }
    )


def base_scope_binding(source: ReadResponse[CurveData]) -> dict[str, str | int]:
    """Tagged atomic scope, never relabel a registry or source digest."""
    identity, authority, hierarchy = (
        source.forecast_identity,
        source.authority_identity,
        source.hierarchy_identity,
    )
    if (
        identity is None
        or authority is None
        or hierarchy is None
        or identity.hierarchy_level != "BASE"
        or identity.source_kind != "OPERATIONAL_PEAK"
        or hierarchy.hierarchy_level != "BASE"
        or hierarchy.entity_id != identity.entity_id
        or hierarchy.hierarchy_authority_hash is not None
        or authority.authority_hash == "0" * 64
        or source.source_result_hash in (None, "0" * 64)
    ):
        raise ReadError("BASE_SCOPE_AUTHORITY_UNAVAILABLE", 409)
    return {
        "binding_type": BASE_KIND,
        "binding_policy_version": BASE_BINDING_POLICY,
        "adapter_policy_version": ADAPTER_POLICY,
        **identity.model_dump(mode="json"),
        "source_authority_hash": authority.authority_hash,
        "source_result_hash": source.source_result_hash,
    }


def adapt_saved_curve(
    source: ReadResponse[CurveData], selection: DecisionSelection
) -> tuple[what_if.SavedForecastCurve, dict[str, Any]]:
    """Only verified S1 saved curves enter the immutable S6 contract."""
    identity, hierarchy, authority = (
        source.forecast_identity,
        source.hierarchy_identity,
        source.authority_identity,
    )
    if (
        source.projection_hash
        != projection_digest(source.model_dump(mode="json", exclude={"projection_hash"}))
        or identity != selection.forecast_selection
        or hierarchy is None
        or authority is None
        or source.source_result_hash != selection.expected_source_result_hash
        or source.source_run_id != selection.forecast_selection.run_id
        or source.source_kind != selection.forecast_selection.source_kind
        or hierarchy.hierarchy_level != identity.hierarchy_level
        or hierarchy.entity_id != identity.entity_id
        or authority.source_baseline_id != identity.baseline_id
        or authority.source_policy_version != identity.policy_version
        or source.source_result_hash == "0" * 64
        or authority.authority_hash == "0" * 64
    ):
        raise ReadError("SOURCE_ADAPTER_AUTHORITY_MISMATCH", 409)
    if source.data is None or not source.data.daily_rows:
        raise ReadError("SAVED_CURVE_UNAVAILABLE", 409)
    data = source.data
    if data.available_day_count != len(data.daily_rows) or not 1 <= len(data.daily_rows) <= 15:
        raise ReadError("SAVED_CURVE_INTEGRITY_FAILED", 409)
    for lead, row in enumerate(data.daily_rows, 1):
        if (
            row.lead_day != lead
            or row.target_date != identity.origin_date + timedelta(days=lead)
            or row.forecast_run_id != identity.run_id
            or row.hierarchy_level != identity.hierarchy_level
            or row.entity_id != identity.entity_id
            or row.origin_date != identity.origin_date
            or row.source_result_hash != source.source_result_hash
        ):
            raise ReadError("SAVED_CURVE_INTEGRITY_FAILED", 409)
    binding = None
    scope_hash: str | None
    if identity.hierarchy_level == "BASE":
        binding = base_scope_binding(source)
        scope_hash, kind = projection_digest(binding), BASE_KIND
        # Independent recomputation keeps the adapter scope separate from source identity.
        if scope_hash != projection_digest(base_scope_binding(source)):
            raise ReadError("BASE_SCOPE_AUTHORITY_UNAVAILABLE", 409)
    else:
        scope_hash, kind = hierarchy.hierarchy_authority_hash, "SAVED_HIERARCHY_SNAPSHOT"
        if scope_hash in (None, "0" * 64):
            raise ReadError("HIERARCHY_SCOPE_AUTHORITY_UNAVAILABLE", 409)
    assert scope_hash is not None
    anchor = datetime.combine(identity.origin_date, time.min, ZoneInfo("Asia/Shanghai"))
    curve = what_if.SavedForecastCurve(
        forecast_source_id=f"{identity.forecast_family}:{identity.source_kind}:{identity.run_id}",
        forecast_source_hash=selection.expected_source_result_hash,
        forecast_origin=anchor,
        hierarchy_level=identity.hierarchy_level,
        hierarchy_entity_id=identity.entity_id,
        hierarchy_authority_hash=scope_hash,
        daily_rows=tuple(
            what_if.SavedForecastDay(
                row.target_date, decimal_input(row.point_forecast_kg), None, None
            )
            for row in data.daily_rows
        ),
    )
    return curve, {
        "adapter_authority_hash": scope_hash,
        "adapter_authority_kind": kind,
        "adapter_authority_binding": binding,
        "adapter_saved_forecast_hash": curve.saved_forecast_hash,
        "origin_anchor": anchor.isoformat(),
    }


def make_scenario(
    curve: what_if.SavedForecastCurve,
    selection: DecisionSelection,
    cost: BusinessCostContract,
    request: ScenarioInput,
) -> what_if.DecisionScenario:
    capacities = tuple(
        what_if.CapacityDay(
            date=row.date,
            capacity_mode=row.capacity_mode,
            daily_handling_capacity_kg=decimal_input(row.daily_handling_capacity_kg)
            if isinstance(row, DirectCapacity)
            else None,
            workforce_count=None if isinstance(row, DirectCapacity) else row.workforce_count,
            productivity_kg_per_person_day=None
            if isinstance(row, DirectCapacity)
            else decimal_input(row.productivity_kg_per_person_day),
            buffer_supplied=row.buffer_handling_capacity_kg is not None,
            buffer_handling_capacity_kg=decimal_input(row.buffer_handling_capacity_kg or "0"),
        )
        for row in request.capacity_rows
    )
    return what_if.DecisionScenario(
        request.scenario_id,
        request.scenario_version,
        curve,
        selection.planning_level,
        cost,
        capacities,
    )


class DecisionSupportService:
    """One application layer; authorization stays in the existing HTTP boundary."""

    def __init__(self, reader: ForecastIntelligenceReadService):
        self.reader = reader

    def business_loss(self, selection: CostSelection) -> DecisionResponse[BusinessLossExposure]:
        cost = cost_contract(selection)
        return decision_response(
            BusinessLossExposure,
            capability="BUSINESS_LOSS_EXPOSURE",
            status="READY",
            cost_contract_id=cost.contract_id,
            cost_contract_hash=cost.contract_hash,
            data=BusinessLossExposure(
                cost_contract=CostContractView.model_validate(
                    cost.payload() | {"contract_hash": cost.contract_hash}
                ),
                formula=FORMULA,
            ),
        )

    async def _prepare(
        self, payload: dict[str, Any]
    ) -> tuple[DecisionSelection, ReadResponse[CurveData], BusinessCostContract, dict[str, Any]]:
        # Only selection fields are parsed first; capacity/scenario validation follows read.
        selected = DecisionSelection.model_validate(
            {k: v for k, v in payload.items() if k in DecisionSelection.model_fields}
        )
        query = ForecastReadQuery(
            **selected.forecast_selection.model_dump(),
            expected_source_result_hash=selected.expected_source_result_hash,
        )
        source = await self.reader.curve(query)
        cost = cost_contract(selected)
        return (
            selected,
            source,
            cost,
            {
                "forecast_identity": source.forecast_identity,
                "hierarchy_identity": source.hierarchy_identity,
                "authority_identity": source.authority_identity,
                "source_result_hash": source.source_result_hash,
                "source_rerun_of_run_id": source.source_rerun_of_run_id,
                "source_read_projection_hash": source.projection_hash,
                "origin_date": selected.forecast_selection.origin_date,
                "planning_level": selected.planning_level,
                "cost_contract_id": cost.contract_id,
                "cost_contract_hash": cost.contract_hash,
                "data_completeness": source.data.data_completeness if source.data else None,
                "available_day_count": source.data.available_day_count if source.data else 0,
            },
        )

    @staticmethod
    def _unavailable(source: ReadResponse[CurveData], selection: DecisionSelection) -> str | None:
        if selection.planning_level != "POINT":
            return "NO_EXACT_BOUND_M1_INTERVAL_AUTHORITY_FOR_SAVED_RUN"
        if source.data is None or source.status not in ("READY", "PARTIAL"):
            return "SAVED_CURVE_NOT_AVAILABLE"
        if source.data.data_completeness == "INCOMPLETE_CHILD_COVERAGE":
            return "INCOMPLETE_CHILD_COVERAGE"
        if not source.data.daily_rows:
            return "EMPTY_SAVED_CURVE"
        return None

    async def simulate(self, payload: dict[str, Any]) -> DecisionResponse[SimulationResult]:
        try:
            selection, source, cost, common = await self._prepare(payload)
            request = SimulationRequest.model_validate(payload)
            reason = self._unavailable(source, selection)
            if reason:
                return decision_response(
                    SimulationResult,
                    capability="SIMULATE_CAPACITY",
                    status="NOT_AVAILABLE",
                    unavailable_reason=reason,
                    **common,
                )
            curve, binding = adapt_saved_curve(source, selection)
            scenario = make_scenario(curve, selection, cost, request)
            result = what_if.simulate(scenario)
            return decision_response(
                SimulationResult,
                capability="SIMULATE_CAPACITY",
                status=source.status,
                engine_result_hash=result["result_hash"],
                data=SimulationResult.model_validate(result),
                **common,
                **binding,
            )
        except ValidationError:
            raise ReadError("INVALID_REQUEST", 422) from None
        except ValueError as exc:
            self._engine_error(exc)

    async def compare(self, payload: dict[str, Any]) -> DecisionResponse[ComparisonData]:
        try:
            selection, source, cost, common = await self._prepare(payload)
            request = ComparisonRequest.model_validate(payload)
            reason = self._unavailable(source, selection)
            if reason:
                return decision_response(
                    ComparisonData,
                    capability="COMPARE_CAPACITY_SCENARIOS",
                    status="NOT_AVAILABLE",
                    unavailable_reason=reason,
                    **common,
                )
            curve, binding = adapt_saved_curve(source, selection)
            scenarios = tuple(
                make_scenario(curve, selection, cost, r)
                for r in sorted(request.scenarios, key=lambda r: r.scenario_id)
            )
            compared = what_if.compare_and_rank(scenarios)
            if compared["scenario_comparison_status"] != "COMPARABLE":
                raise ReadError("NOT_COMPARABLE_AUTHORITY_MISMATCH", 409)
            results = [SimulationResult.model_validate(what_if.simulate(s)) for s in scenarios]
            return decision_response(
                ComparisonData,
                capability="COMPARE_CAPACITY_SCENARIOS",
                status=source.status,
                engine_result_hash=compared["comparison_hash"],
                data=ComparisonData(
                    comparison=ComparisonResult.model_validate(compared), scenario_results=results
                ),
                **common,
                **binding,
            )
        except ValidationError:
            raise ReadError("INVALID_REQUEST", 422) from None
        except ValueError as exc:
            self._engine_error(exc)

    @staticmethod
    def _engine_error(exc: ValueError) -> NoReturn:
        allowed = {
            "CAPACITY_DATE_COVERAGE_MISMATCH",
            "SCENARIO_DUPLICATE_OR_EMPTY",
            "SOURCE_NUMERIC_INVALID",
            "AUTHORITATIVE_PRECISION_EXCEEDED",
            "FORECAST_DATE_CONTINUITY_FAILED",
            "CAPACITY_MODE_CONFLICT",
        }
        if str(exc) == "SOURCE_FORECAST_DRIFT":
            raise ReadError("SOURCE_FORECAST_DRIFT", 409) from None
        if str(exc) in allowed:
            raise ReadError(str(exc), 422) from None
        raise ReadError("DECISION_ENGINE_UNAVAILABLE", 503) from None
