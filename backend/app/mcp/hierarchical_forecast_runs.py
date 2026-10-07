"""Thin, local MCP adapter; no deployment or independent business rules."""

from typing import Any

from mcp.types import Tool, ToolAnnotations
from pydantic import BaseModel

from backend.app.db.session import AsyncSessionMaker
from backend.app.forecast_intelligence.application import execute_hierarchical_run
from backend.app.forecast_intelligence.persistence import HierarchicalRunRepository
from backend.app.forecast_intelligence.schemas import (
    CreateHierarchicalRun,
    HierarchicalDailyRows,
    HierarchicalHistoryQuery,
    HierarchicalRunHistory,
    HierarchicalRunIdentity,
    SavedHierarchicalRun,
)
from backend.app.mcp.schema_compat import project_mcp_input_schema

CREATE = "create_blueberry_hierarchical_forecast_run"
GET = "get_blueberry_hierarchical_forecast_run"
LIST = "list_blueberry_hierarchical_forecast_runs"
DAILY = "get_blueberry_hierarchical_forecast_daily"
CONTRACTS: dict[str, tuple[type[BaseModel], type[BaseModel]]] = {
    CREATE: (CreateHierarchicalRun, SavedHierarchicalRun),
    GET: (HierarchicalRunIdentity, SavedHierarchicalRun),
    LIST: (HierarchicalHistoryQuery, HierarchicalRunHistory),
    DAILY: (HierarchicalRunIdentity, HierarchicalDailyRows),
}


def run_tools() -> list[Tool]:
    return [
        Tool(
            name=name,
            description=(
                "Immutable, integrity-checked BASE/REGION/COMPANY forecast reconciliation. "
                "Missing children are not zero."
            ),
            input_schema=project_mcp_input_schema(inputs.model_json_schema()),
            output_schema=outputs.model_json_schema(),
            annotations=ToolAnnotations(
                read_only_hint=name != CREATE,
                destructive_hint=False,
                idempotent_hint=True,
                open_world_hint=False,
            ),
        )
        for name, (inputs, outputs) in CONTRACTS.items()
    ]


async def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    saved: BaseModel
    body = CONTRACTS[name][0].model_validate(arguments)
    async with AsyncSessionMaker() as session:
        repository = HierarchicalRunRepository(session)
        if isinstance(body, CreateHierarchicalRun):
            async with session.begin():
                saved = await execute_hierarchical_run(session, body)
        elif isinstance(body, HierarchicalHistoryQuery):
            saved = await repository.history(body)
        elif isinstance(body, HierarchicalRunIdentity):
            saved = (
                await repository.daily(body.run_id)
                if name == DAILY
                else await repository.get(body.run_id)
            )
        else:
            raise ValueError("INVALID_REQUEST")
        return saved.model_dump(mode="json")
