"""Thin saved-run transport operations; product/repository own all business rules."""

from typing import Any

from mcp.types import Tool, ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from backend.app.area_yield.product import AreaDrivenForecastRequest, DailyAreaForecast
from backend.app.area_yield.product_errors import AreaForecastInputError
from backend.app.area_yield.run_application import execute_area_forecast_run
from backend.app.area_yield.run_persistence import AreaForecastRunRepository
from backend.app.area_yield.run_schemas import (
    AreaRunHistory,
    CreateAreaForecastRun,
    SavedAreaForecastRun,
)
from backend.app.db.session import AsyncSessionMaker
from backend.app.mcp.schema_compat import project_mcp_input_schema

CREATE = "create_blueberry_area_forecast_run"
GET = "get_blueberry_area_forecast_run"
LIST = "list_blueberry_area_forecast_runs"
DAILY = "get_blueberry_area_forecast_daily"


class RunIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: int = Field(gt=0, strict=True)


class HistoryQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    canonical_farm: str | None = None
    target_season: str | None = None
    forecast_policy_version: str | None = None
    limit: int = Field(default=20, ge=1, le=100, strict=True)
    cursor: str | None = None


class SavedDailyForecast(BaseModel):
    run_id: int
    daily_forecast: list[DailyAreaForecast]


CONTRACTS: dict[str, tuple[type[BaseModel], type[BaseModel], str]] = {
    CREATE: (
        CreateAreaForecastRun,
        SavedAreaForecastRun,
        "Create or reuse an immutable area forecast run in the configured database. "
        "Explicit write; optional rerun requires identical farm, season and window. "
        "Same request, policy and authority reuse the saved run.",
    ),
    GET: (
        RunIdentity,
        SavedAreaForecastRun,
        "Read and integrity-check a saved run; no reforecast.",
    ),
    LIST: (
        HistoryQuery,
        AreaRunHistory,
        "List persisted run summaries, newest first, using opaque keyset pagination. "
        "Default limit 20, maximum 100; no daily payload and no reforecast.",
    ),
    DAILY: (
        RunIdentity,
        SavedDailyForecast,
        "Read integrity-checked persisted daily rows in ascending date order; no reforecast.",
    ),
}


def run_tools() -> list[Tool]:
    tools = []
    for name, (input_type, output_type, description) in CONTRACTS.items():
        schema = input_type.model_json_schema()
        if name == CREATE:
            schema["properties"].pop("forecast_method")
        schema = project_mcp_input_schema(schema)
        tools.append(
            Tool(
                name=name,
                description=description,
                input_schema=schema,
                output_schema=output_type.model_json_schema(),
                annotations=ToolAnnotations(
                    read_only_hint=name != CREATE,
                    destructive_hint=False,
                    idempotent_hint=True,
                    open_world_hint=False,
                ),
            )
        )
    return tools


async def call_run_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == CREATE and "forecast_method" in arguments:
        raise AreaForecastInputError("INVALID_REQUEST_DOCUMENT")
    body = CONTRACTS[name][0].model_validate(arguments)
    # Normal shared configured factory; each invocation owns a separate transaction.
    async with AsyncSessionMaker() as session, session.begin():
        repository = AreaForecastRunRepository(session)
        if isinstance(body, CreateAreaForecastRun):
            request = AreaDrivenForecastRequest.model_validate(
                body.model_dump(exclude={"rerun_of_run_id"})
            )
            result = (
                await execute_area_forecast_run(
                    session, request, rerun_of_run_id=body.rerun_of_run_id
                )
            ).model_dump(mode="json")
        elif isinstance(body, HistoryQuery):
            try:
                result = (await repository.history(**body.model_dump())).model_dump(mode="json")
            except ValueError as exc:
                raise AreaForecastInputError("INVALID_HISTORY_QUERY") from exc
        else:
            assert isinstance(body, RunIdentity)
            saved = await repository.get(body.run_id)
            result = (
                SavedDailyForecast(
                    run_id=body.run_id, daily_forecast=saved.result.daily_forecast
                ).model_dump(mode="json")
                if name == DAILY
                else saved.model_dump(mode="json")
            )
    # Return only after commit succeeds; repositories never own commit/rollback.
    return result
