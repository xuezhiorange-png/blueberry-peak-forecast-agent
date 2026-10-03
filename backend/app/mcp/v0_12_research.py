"""Four optional research tools on the existing MCP server, no transport ownership."""

from typing import Any

import anyio
from mcp.types import Tool, ToolAnnotations
from pydantic import BaseModel, ValidationError

from backend.app.area_yield import research_mcp_application as application
from backend.app.mcp.schema_compat import project_mcp_input_schema

READINESS = "get_blueberry_v0_12_research_readiness"
CREATE = "create_blueberry_v0_12_test_forecast"
GET = "get_blueberry_v0_12_test_forecast"
VERIFY = "verify_blueberry_v0_12_test_forecast"
CONTRACTS: dict[str, tuple[type[BaseModel], str]] = {
    READINESS: (
        application.EmptyRequest,
        "Read V0.12 research engineering readiness; not accuracy approval.",
    ),
    CREATE: (
        application.TestForecastRequest,
        "Issue an immutable TEST_ONLY forecast using server-owned artifacts. "
        "Duplicate request IDs are rejected. No real/prospective or production authorization.",
    ),
    GET: (
        application.ForecastIdentity,
        "Read a verified TEST_NOT_PROSPECTIVE forecast including daily curves; no reforecast.",
    ),
    VERIFY: (
        application.ForecastIdentity,
        "Verify a sealed TEST_ONLY forecast; no model inference or training.",
    ),
}


def run_tools() -> list[Tool]:
    if not application.enabled():
        return []
    return [
        Tool(
            name=name,
            description=description,
            input_schema=project_mcp_input_schema(kind.model_json_schema()),
            annotations=ToolAnnotations(
                read_only_hint=name != CREATE,
                destructive_hint=False,
                idempotent_hint=name != CREATE,
                open_world_hint=False,
            ),
        )
        for name, (kind, description) in CONTRACTS.items()
    ]


def _dispatch(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if not application.enabled():
        raise ValueError("V0_12_RESEARCH_INTERFACE_DISABLED")
    CONTRACTS[name][0].model_validate(arguments)
    if name == READINESS:
        return application.readiness()
    if name == CREATE:
        return application.create_test_forecast(arguments)
    return application.get_test_forecast(arguments["forecast_id"], verify=name == VERIFY)


async def call_tool(name: str, arguments: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    try:
        return await anyio.to_thread.run_sync(_dispatch, name, arguments), False
    except ValidationError:
        code, reason = "V0_12_RESEARCH_REQUEST_INVALID", "INVALID_REQUEST_DOCUMENT"
    except FileNotFoundError:
        code = reason = "V0_12_RESEARCH_FORECAST_NOT_FOUND"
    except OSError:
        code = reason = "V0_12_RESEARCH_WRITE_FAILURE"
    except ValueError as exc:
        # Only map exact known tokens, never return arbitrary exception text.
        known = {
            "V0_12_RESEARCH_INTERFACE_DISABLED": "V0_12_RESEARCH_INTERFACE_DISABLED",
            "V0_12_RESEARCH_RUNTIME_NOT_READY": "V0_12_RESEARCH_RUNTIME_NOT_READY",
            "DUPLICATE_REQUEST_ISSUANCE": "V0_12_RESEARCH_DUPLICATE_REQUEST",
            "REAL_PROSPECTIVE_NOT_AUTHORIZED": "V0_12_REAL_PROSPECTIVE_NOT_AUTHORIZED",
        }
        code = known.get(str(exc), "V0_12_RESEARCH_INTEGRITY_FAILURE")
        if name == CREATE and code == "V0_12_RESEARCH_INTEGRITY_FAILURE":
            code = "V0_12_RESEARCH_REQUEST_INVALID"
        reason = "INVALID_REQUEST_DOCUMENT" if code == "V0_12_RESEARCH_REQUEST_INVALID" else code
    except Exception:
        code = reason = "V0_12_RESEARCH_INTEGRITY_FAILURE"
    return {"status": "error", "code": code, "reason": reason}, True
