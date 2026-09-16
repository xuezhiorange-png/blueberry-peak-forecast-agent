"""Compatibility projections for MCP client input-schema discovery."""

from copy import deepcopy
from typing import Any, cast


class MCPInputSchemaProjectionError(ValueError):
    """Raised when a compatibility projection would risk changing a schema."""


def project_mcp_input_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Project equivalent integer constraints for clients with limited JSON Schema support.

    This function changes only the schema exposed through MCP discovery. Runtime request
    validation remains owned by the original Pydantic models. A conflicting pre-existing
    ``minimum`` fails closed rather than being overwritten.
    """

    projected = deepcopy(schema)
    return cast(dict[str, Any], _project_node(projected))


def _project_node(node: Any) -> Any:
    if isinstance(node, dict):
        projected = {key: _project_node(value) for key, value in node.items()}
        exclusive_minimum = projected.get("exclusiveMinimum")
        if (
            projected.get("type") == "integer"
            and isinstance(exclusive_minimum, (int, float))
            and not isinstance(exclusive_minimum, bool)
            and exclusive_minimum == 0
        ):
            if "minimum" in projected and projected["minimum"] != 1:
                raise MCPInputSchemaProjectionError(
                    "cannot project integer exclusiveMinimum when minimum already exists"
                )
            projected["minimum"] = 1
            del projected["exclusiveMinimum"]
        return projected
    if isinstance(node, list):
        return [_project_node(value) for value in node]
    return node


__all__ = ["MCPInputSchemaProjectionError", "project_mcp_input_schema"]
