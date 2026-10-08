"""Eight thin product capability descriptions and Pydantic-derived schemas."""

from dataclasses import dataclass
from typing import Any, Literal

from mcp.types import Tool, ToolAnnotations
from pydantic import BaseModel, TypeAdapter

from backend.app.forecast_intelligence.decision_schemas import (
    ComparisonData,
    ComparisonRequest,
    DecisionResponse,
    SimulationRequest,
    SimulationResult,
)
from backend.app.forecast_intelligence.read_schemas import (
    CurveData,
    ForecastReadQuery,
    HierarchyData,
    OverviewData,
    QualityData,
    QualityReadQuery,
    ReadModel,
    ReadResponse,
)
from backend.app.mcp.schema_compat import project_mcp_input_schema


class ToolError(ReadModel):
    status: Literal["ERROR"] = "ERROR"
    code: str
    data: None = None


@dataclass(frozen=True)
class ProductTool:
    method: str
    request: type[BaseModel]
    response: type[BaseModel]
    description: str


TOOLS = {
    "get_forecast_overview": ProductTool(
        "overview",
        ForecastReadQuery,
        ReadResponse[OverviewData],
        "Read saved H7/H15 prefix totals and peak; full authorized identity required. "
        "No new forecast.",
    ),
    "get_forecast_curve": ProductTool(
        "curve",
        ForecastReadQuery,
        ReadResponse[CurveData],
        "Read exact saved daily quantities. No latest selection, cross-run composition "
        "or fill-zero.",
    ),
    "get_hierarchical_forecast": ProductTool(
        "hierarchy",
        ForecastReadQuery,
        ReadResponse[HierarchyData],
        "Read saved BASE/REGION/COMPANY scope; missing children stay incomplete, never zero.",
    ),
    "get_forecast_uncertainty": ProductTool(
        "uncertainty",
        ForecastReadQuery,
        ReadResponse[ReadModel],
        "Read only compatible bound authority; currently NOT_AVAILABLE for Operational Peak. "
        "Point is not proven P50; planning bounds are not quantiles. "
        "Never substitute historical bounds.",
    ),
    "get_forecast_attribution": ProductTool(
        "attribution",
        ForecastReadQuery,
        ReadResponse[ReadModel],
        "Read only exact bound model attribution; currently NOT_AVAILABLE. Not causal explanation.",
    ),
    "get_forecast_quality": ProductTool(
        "quality",
        QualityReadQuery,
        ReadResponse[QualityData],
        "M1 EXPOSED_OOT 2025-2026 BASE_COHORT_AGGREGATE historical validation only. "
        "Coverage below nominal; strict PIT false. Current mode NO_CURRENT_ACTUAL, no actual read.",
    ),
    "simulate_capacity": ProductTool(
        "simulate",
        SimulationRequest,
        DecisionResponse[SimulationResult],
        "Evaluate explicit capacity on an authorized saved curve using S2. POINT supported; "
        "unbound upper levels NOT_AVAILABLE, never fall back. Synthetic loss units, "
        "not money/ROI. No action.",
    ),
    "compare_capacity_scenarios": ProductTool(
        "compare",
        ComparisonRequest,
        DecisionResponse[ComparisonData],
        "Conditional ordering of explicit scenarios under identical forecast/planning/cost "
        "authority. "
        "Synthetic cost only, no optimal plan, workforce recommendation or automatic execution.",
    ),
}


def output_schema(tool: ProductTool) -> dict[str, Any]:
    # SDK requires an object-shaped schema. Both union branches remain Pydantic-derived.
    union = TypeAdapter(tool.response | ToolError).json_schema()
    return {"type": "object", **union}


def tools() -> list[Tool]:
    return [
        Tool(
            name=name,
            description=tool.description,
            input_schema=project_mcp_input_schema(tool.request.model_json_schema()),
            output_schema=output_schema(tool),
            annotations=ToolAnnotations(
                read_only_hint=True,
                destructive_hint=False,
                idempotent_hint=True,
                open_world_hint=False,
            ),
        )
        for name, tool in TOOLS.items()
    ]
