"""Thin MCP adapters for persisted S6 operational peak runs."""

from __future__ import annotations

from typing import Any

from mcp.types import Tool, ToolAnnotations
from pydantic import BaseModel

from backend.app.db.session import AsyncSessionMaker
from backend.app.forecast_quality.operational_peak import OperationalPeakForecastRequest
from backend.app.forecast_quality.operational_peak_application import (
    execute_operational_peak_forecast_run,
)
from backend.app.forecast_quality.operational_peak_persistence import (
    OperationalPeakRunRepository,
)
from backend.app.forecast_quality.operational_peak_schemas import (
    CreateOperationalPeakRun,
    OperationalPeakDailyRows,
    OperationalPeakHistoryQuery,
    OperationalPeakRunHistory,
    OperationalPeakRunIdentity,
    SavedOperationalPeakRun,
)

CREATE = "create_blueberry_operational_peak_forecast_run"
GET = "get_blueberry_operational_peak_forecast_run"
LIST = "list_blueberry_operational_peak_forecast_runs"
DAILY = "get_blueberry_operational_peak_forecast_daily"


def _annotations(read_only: bool) -> ToolAnnotations:
    return ToolAnnotations(
        read_only_hint=read_only,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )


CONTRACTS: dict[str, tuple[type[BaseModel], type[BaseModel], str]] = {
    CREATE: (
        CreateOperationalPeakRun,
        SavedOperationalPeakRun,
        "Create or reuse an immutable operational peak forecast run from the server-owned "
        "registered-base authority. Same execution identity is idempotent.",
    ),
    GET: (
        OperationalPeakRunIdentity,
        SavedOperationalPeakRun,
        "Read an integrity-checked persisted operational peak run without reforecasting.",
    ),
    LIST: (
        OperationalPeakHistoryQuery,
        OperationalPeakRunHistory,
        "List persisted operational peak run summaries with opaque keyset pagination; "
        "daily rows are not included.",
    ),
    DAILY: (
        OperationalPeakRunIdentity,
        OperationalPeakDailyRows,
        "Read integrity-checked persisted operational peak daily rows in ascending date order.",
    ),
}


def run_tools() -> list[Tool]:
    return [
        Tool(
            name=name,
            description=description,
            input_schema=input_type.model_json_schema(),
            output_schema=output_type.model_json_schema(),
            annotations=_annotations(name != CREATE),
        )
        for name, (input_type, output_type, description) in CONTRACTS.items()
    ]


async def call_operational_peak_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    body = CONTRACTS[name][0].model_validate(arguments)
    async with AsyncSessionMaker() as session:
        repository = OperationalPeakRunRepository(session)
        if isinstance(body, CreateOperationalPeakRun):
            request = OperationalPeakForecastRequest.from_mapping(body.model_dump())
            async with session.begin():
                return (
                    await execute_operational_peak_forecast_run(
                        session,
                        request,
                        rerun_of_run_id=body.rerun_of_run_id,
                    )
                ).model_dump(mode="json")
        if isinstance(body, OperationalPeakHistoryQuery):
            return (await repository.history(**body.model_dump())).model_dump(mode="json")
        if isinstance(body, OperationalPeakRunIdentity):
            if name == DAILY:
                return (await repository.daily(body.run_id)).model_dump(mode="json")
            return (await repository.get(body.run_id)).model_dump(mode="json")
        raise ValueError("INVALID_REQUEST")


__all__ = [
    "CONTRACTS",
    "CREATE",
    "DAILY",
    "GET",
    "LIST",
    "call_operational_peak_tool",
    "run_tools",
]
