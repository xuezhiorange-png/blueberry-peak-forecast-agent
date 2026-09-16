"""Area forecast tools; stdio owns transport, product/repository own business rules."""

import asyncio
import json
from typing import Any

import anyio
from mcp.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
    ToolAnnotations,
)
from pydantic import ValidationError

from backend.app.area_yield.product import (
    AreaDrivenForecastRequest,
    AreaDrivenForecastResult,
)
from backend.app.area_yield.product_authority import forecast_area_product
from backend.app.area_yield.product_errors import (
    AreaForecastAuthorityError,
    AreaForecastRequestError,
)
from backend.app.area_yield.run_persistence import (
    AreaForecastPersistenceConflictError,
    AreaForecastPersistenceIntegrityError,
    AreaForecastRunNotFoundError,
    AreaForecastWriteFailure,
)
from backend.app.forecast_quality.operational_peak import OperationalPeakForecastError
from backend.app.forecast_quality.operational_peak_authority import (
    OperationalPeakAuthorityError,
)
from backend.app.forecast_quality.operational_peak_persistence import (
    OperationalPeakPersistenceConflictError,
    OperationalPeakPersistenceIntegrityError,
    OperationalPeakRunNotFoundError,
    OperationalPeakWriteFailure,
)
from backend.app.mcp.operational_peak_runs import (
    CONTRACTS as OPERATIONAL_PEAK_CONTRACTS,
)
from backend.app.mcp.operational_peak_runs import (
    call_operational_peak_tool,
)
from backend.app.mcp.operational_peak_runs import (
    run_tools as operational_peak_run_tools,
)
from backend.app.mcp.persisted_runs import CONTRACTS, call_run_tool, run_tools
from backend.app.mcp.schema_compat import project_mcp_input_schema

TOOL_NAME = "forecast_blueberry_by_area"
SERVER_NAME = "blueberry-area-forecast"


def input_schema() -> dict[str, Any]:
    """Reuse the product schema, without exposing its fixed method discriminator."""
    schema = AreaDrivenForecastRequest.model_json_schema()
    schema["properties"].pop("forecast_method")
    return project_mcp_input_schema(schema)


def _result(payload: dict[str, Any], *, error: bool = False) -> CallToolResult:
    return CallToolResult(
        content=[
            TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, sort_keys=True))
        ],
        structured_content=payload,
        is_error=error,
    )


def _error(code: str, reason: str) -> CallToolResult:
    return _result({"status": "error", "code": code, "reason": reason}, error=True)


async def _list_tools(
    ctx: ServerRequestContext[Any], params: PaginatedRequestParams | None
) -> ListToolsResult:
    return ListToolsResult(
        tools=[
            Tool(
                name=TOOL_NAME,
                description=(
                    "Forecast blueberry harvest (= arrival) by canonical farm, requested "
                    "productive area (Decimal string), and season. Requires immediate prior-season "
                    "farm history; no automatic fallback. Returns daily quantities and peaks. "
                    "Point forecast only; no universal accuracy approval."
                ),
                input_schema=input_schema(),
                output_schema=AreaDrivenForecastResult.model_json_schema(),
                annotations=ToolAnnotations(
                    read_only_hint=True,
                    destructive_hint=False,
                    idempotent_hint=True,
                    open_world_hint=False,
                ),
            ),
            *run_tools(),
            *operational_peak_run_tools(),
        ]
    )


async def _call_tool(
    ctx: ServerRequestContext[Any], params: CallToolRequestParams
) -> CallToolResult:
    if params.name in CONTRACTS:
        try:
            payload = await call_run_tool(params.name, params.arguments or {})
        except ValidationError:
            return _error("AREA_FORECAST_REQUEST_INVALID", "INVALID_REQUEST_DOCUMENT")
        except (AreaForecastRequestError, AreaForecastAuthorityError) as exc:
            return _error(exc.code, exc.reason)
        except (
            AreaForecastPersistenceConflictError,
            AreaForecastPersistenceIntegrityError,
            AreaForecastRunNotFoundError,
            AreaForecastWriteFailure,
        ) as exc:
            return _error(exc.code, exc.code)
        except Exception:
            # SQLAlchemy/connection/commit and other infrastructure failures are not
            # authority failures. Never expose exception text, SQL, URLs or secrets.
            return _error("AREA_FORECAST_WRITE_FAILURE", "PERSISTENCE_SERVICE_UNAVAILABLE")
        return _result(payload)
    if params.name in OPERATIONAL_PEAK_CONTRACTS:
        try:
            payload = await call_operational_peak_tool(params.name, params.arguments or {})
        except ValidationError:
            return _error("INVALID_REQUEST", "INVALID_REQUEST_DOCUMENT")
        except OperationalPeakAuthorityError as exc:
            return _error(exc.code, exc.reason)
        except OperationalPeakForecastError as exc:
            return _error(exc.code, exc.reason)
        except ValueError:
            return _error("INVALID_REQUEST", "INVALID_HISTORY_QUERY")
        except (
            OperationalPeakPersistenceConflictError,
            OperationalPeakPersistenceIntegrityError,
            OperationalPeakRunNotFoundError,
            OperationalPeakWriteFailure,
        ) as exc:
            return _error(exc.code, exc.code)
        except Exception:
            return _error("OPERATIONAL_PEAK_WRITE_FAILURE", "PERSISTENCE_SERVICE_UNAVAILABLE")
        return _result(payload)
    if params.name != TOOL_NAME:
        return _error("AREA_FORECAST_REQUEST_INVALID", "TOOL_NOT_SUPPORTED")
    arguments = params.arguments or {}
    if set(arguments) - set(input_schema()["properties"]):
        return _error("AREA_FORECAST_REQUEST_INVALID", "INVALID_REQUEST_DOCUMENT")
    try:
        request = AreaDrivenForecastRequest.model_validate(arguments)
    except ValidationError:
        # ValidationError may contain caller values; never expose its text or input.
        return _error("AREA_FORECAST_REQUEST_INVALID", "INVALID_REQUEST_DOCUMENT")
    try:
        result = await anyio.to_thread.run_sync(forecast_area_product, request)
    except (AreaForecastRequestError, AreaForecastAuthorityError) as exc:
        return _error(exc.code, exc.reason)
    except Exception:
        # Fail closed without leaking arbitrary exception messages or filesystem paths.
        return _error("AREA_FORECAST_AUTHORITY_UNAVAILABLE", "AUTHORITY_PAYLOAD_INVALID")
    return _result(result.model_dump(mode="json"))


server: Server[Any] = Server(
    SERVER_NAME, version="1.0.0", on_list_tools=_list_tools, on_call_tool=_call_tool
)


async def main() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
