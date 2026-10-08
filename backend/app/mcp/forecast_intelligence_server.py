"""Trusted composition root; independent SDK registry, no legacy dispatcher."""

import json
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

from mcp.server import Server, ServerRequestContext
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
)
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.forecast_intelligence.decision_schemas import DecisionSelection
from backend.app.forecast_intelligence.decision_service import DecisionSupportService
from backend.app.forecast_intelligence.read_access import (
    ServiceAccount,
    authorize_quality,
    authorize_run,
    require_capability,
    verify_granted_result,
)
from backend.app.forecast_intelligence.read_schemas import (
    ForecastReadQuery,
    QualityReadQuery,
    ReadError,
)
from backend.app.forecast_intelligence.read_service import ForecastIntelligenceReadService
from backend.app.mcp.forecast_intelligence_tools import TOOLS, ToolError, tools

ARGUMENT_LIMIT = 131072
RESPONSE_LIMIT = 2097152
SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


def database_session() -> AbstractAsyncContextManager[AsyncSession]:
    # Lazy: unauthorized calls and quality never initialize a database dependency.
    from backend.app.db.session import AsyncSessionMaker

    return AsyncSessionMaker()


def encoded(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def result(value: dict[str, Any], *, error: bool = False) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=encoded(value))],
        structured_content=value,
        is_error=error,
    )


def failure(code: str) -> CallToolResult:
    return result(ToolError(code=code).model_dump(mode="json"), error=True)


SAFE_CODES = frozenset(
    {
        "FORBIDDEN",
        "AUTHORIZATION_UNAVAILABLE",
        "SAVED_RUN_NOT_FOUND",
        "AUTHORITY_MISMATCH",
        "SAVED_RUN_INTEGRITY_FAILED",
        "PUBLIC_EVIDENCE_AUTHORITY_MISMATCH",
        "INVALID_REQUEST",
        "PERSISTENCE_UNAVAILABLE",
        "READ_UNAVAILABLE",
        "DECISION_UNAVAILABLE",
        "COST_CONTRACT_NOT_FOUND",
    }
)


def create_server(
    account: ServiceAccount,
    session_factory: SessionFactory = database_session,
) -> Server[Any]:
    """Only trusted server code supplies account/grants; never tool arguments."""

    async def list_tools(
        ctx: ServerRequestContext[Any],
        params: PaginatedRequestParams | None,
    ) -> ListToolsResult:
        return ListToolsResult(tools=tools())

    async def call_tool(
        ctx: ServerRequestContext[Any],
        params: CallToolRequestParams,
    ) -> CallToolResult:
        tool = TOOLS.get(params.name)
        if tool is None:
            return failure("INVALID_REQUEST")
        decision = tool.method in ("simulate", "compare")
        try:
            require_capability(account, quality=tool.method == "quality")
            arguments = params.arguments or {}
            if len(encoded(arguments).encode("utf-8")) > ARGUMENT_LIMIT:
                return failure("RESOURCE_LIMIT_EXCEEDED")
            request = tool.request.model_validate(arguments)
            if tool.method == "quality":
                quality_query = QualityReadQuery.model_validate(request.model_dump())
                authorize_quality(account, quality_query)
                # The existing quality method is evidence-only; no DB session is created.
                reader = ForecastIntelligenceReadService(None)
                payload = (await reader.quality(quality_query)).model_dump(mode="json")
            else:
                if decision:
                    selection = DecisionSelection.model_validate(
                        {k: v for k, v in arguments.items() if k in DecisionSelection.model_fields}
                    )
                    query = ForecastReadQuery(
                        **selection.forecast_selection.model_dump(),
                        expected_source_result_hash=selection.expected_source_result_hash,
                    )
                else:
                    query = ForecastReadQuery.model_validate(request.model_dump())
                pinned = authorize_run(account, query)
                async with session_factory() as session:
                    reader = ForecastIntelligenceReadService(session)
                    if decision:
                        service = DecisionSupportService(reader)
                        response = await (
                            service.simulate(arguments)
                            if tool.method == "simulate"
                            else service.compare(arguments)
                        )
                    else:
                        response = await getattr(reader, tool.method)(pinned)
                    verify_granted_result(pinned, response.source_result_hash)
                    payload = response.model_dump(mode="json")
            if len(encoded(payload).encode("utf-8")) > RESPONSE_LIMIT:
                return failure("RESOURCE_LIMIT_EXCEEDED")
            return result(payload)
        except ValidationError:
            return failure("INVALID_REQUEST")
        except ReadError as exc:
            code = (
                exc.code
                if exc.code in SAFE_CODES
                else (
                    "INVALID_REQUEST"
                    if exc.status_code == 422
                    else "AUTHORITY_MISMATCH"
                    if exc.status_code == 409
                    else "SAVED_RUN_NOT_FOUND"
                    if exc.status_code == 404
                    else "DECISION_UNAVAILABLE"
                    if decision
                    else "READ_UNAVAILABLE"
                )
            )
            return failure(code)
        except SQLAlchemyError:
            return failure("PERSISTENCE_UNAVAILABLE")
        except Exception:
            return failure("DECISION_UNAVAILABLE" if decision else "READ_UNAVAILABLE")

    return Server(
        "blueberry-forecast-intelligence-v017",
        version="0.17.0",
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )
