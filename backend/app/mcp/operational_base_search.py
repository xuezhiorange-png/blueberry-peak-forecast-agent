"""Read-only discovery of active bases in the server-owned S6 authority."""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from typing import Any, Literal

from mcp.types import Tool, ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from backend.app.forecast_quality.operational_peak import (
    OperationalPeakForecastError,
    RegisteredBase,
)
from backend.app.forecast_quality.operational_peak_authority import (
    OperationalPeakAuthorityError,
    load_operational_peak_authority,
)
from backend.app.mcp.schema_compat import project_mcp_input_schema

SEARCH = "search_blueberry_operational_bases"
DEFAULT_LIMIT = 20
MAX_LIMIT = 100
MAX_QUERY_LENGTH = 200

MatchType = Literal[
    "ALL_ACTIVE_BASES",
    "EXACT_BASE_ID",
    "EXACT_CANONICAL_NAME",
    "CANONICAL_NAME_SUBSTRING",
    "BASE_ID_SUBSTRING",
]


class SearchOperationalBases(BaseModel):
    """Validated, deliberately small search input exposed by the MCP adapter."""

    model_config = ConfigDict(extra="forbid")

    query: StrictStr | None = Field(default=None, max_length=MAX_QUERY_LENGTH)
    limit: StrictInt = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)


class OperationalBaseSearchItem(BaseModel):
    base_id: str
    canonical_base_name: str
    productive_area_mu: str
    area_basis: str | None
    active: bool
    match_type: MatchType


class OperationalBaseSearchResult(BaseModel):
    query: str | None
    match_count: int
    items: list[OperationalBaseSearchItem]
    authority_hash: str


_MATCH_PRIORITY: dict[MatchType, int] = {
    "EXACT_BASE_ID": 0,
    "EXACT_CANONICAL_NAME": 1,
    "CANONICAL_NAME_SUBSTRING": 2,
    "BASE_ID_SUBSTRING": 3,
    "ALL_ACTIVE_BASES": 4,
}


def _normalize(value: str) -> str:
    """Apply only the discovery contract's Unicode normalization rules."""

    return unicodedata.normalize("NFKC", value.strip()).casefold()


def _active_bases(registry: Mapping[str, Any]) -> tuple[RegisteredBase, ...]:
    raw_bases = registry.get("bases")
    if not isinstance(raw_bases, list):
        raise OperationalPeakAuthorityError("REGISTRY_AUTHORITY_MISMATCH")

    bases: list[RegisteredBase] = []
    try:
        for raw_base in raw_bases:
            if not isinstance(raw_base, Mapping):
                raise OperationalPeakForecastError(
                    "INVALID_BASE_AUTHORITY", "registry base is not an object"
                )
            active = raw_base.get("active", True)
            if not isinstance(active, bool):
                raise OperationalPeakForecastError(
                    "INVALID_BASE_AUTHORITY", "registry active flag is not boolean"
                )
            if not active:
                continue
            bases.append(RegisteredBase.from_mapping(raw_base))
    except OperationalPeakForecastError as exc:
        raise OperationalPeakAuthorityError("REGISTRY_AUTHORITY_MISMATCH") from exc
    return tuple(bases)


def _item(base: RegisteredBase, match_type: MatchType) -> OperationalBaseSearchItem:
    return OperationalBaseSearchItem(
        base_id=base.base_id,
        canonical_base_name=base.canonical_base_name,
        productive_area_mu=str(base.productive_area_mu),
        area_basis=base.area_basis,
        active=base.active,
        match_type=match_type,
    )


def _sort_items(items: list[OperationalBaseSearchItem]) -> list[OperationalBaseSearchItem]:
    return sorted(
        items,
        key=lambda item: (
            _MATCH_PRIORITY[item.match_type],
            _normalize(item.canonical_base_name),
            _normalize(item.base_id),
        ),
    )


def search_operational_bases(
    request: SearchOperationalBases,
) -> OperationalBaseSearchResult:
    """Search active authority entries without resolving or selecting a base."""

    snapshot = load_operational_peak_authority()
    registry = snapshot.registry
    bases = _active_bases(registry)
    query = request.query
    normalized_query = _normalize(query) if query is not None else ""

    if not normalized_query:
        items = [_item(base, "ALL_ACTIVE_BASES") for base in bases]
    else:
        exact_ids = [base for base in bases if _normalize(base.base_id) == normalized_query]
        if exact_ids:
            items = [_item(base, "EXACT_BASE_ID") for base in exact_ids]
        else:
            exact_names = [
                base for base in bases if _normalize(base.canonical_base_name) == normalized_query
            ]
            if exact_names:
                items = [_item(base, "EXACT_CANONICAL_NAME") for base in exact_names]
            else:
                items = []
                for base in bases:
                    if normalized_query in _normalize(base.canonical_base_name):
                        items.append(_item(base, "CANONICAL_NAME_SUBSTRING"))
                    elif normalized_query in _normalize(base.base_id):
                        items.append(_item(base, "BASE_ID_SUBSTRING"))

    ordered = _sort_items(items)
    return OperationalBaseSearchResult(
        query=query,
        match_count=len(ordered),
        items=ordered[: request.limit],
        authority_hash=snapshot.authority_hash,
    )


def run_tools() -> list[Tool]:
    return [
        Tool(
            name=SEARCH,
            description=(
                "Search active registered operational bases by exact or substring match on "
                "base ID or canonical base name. Returns candidates only; it never selects a "
                "base or performs fuzzy, pinyin, geographic, or LLM matching."
            ),
            input_schema=project_mcp_input_schema(SearchOperationalBases.model_json_schema()),
            output_schema=OperationalBaseSearchResult.model_json_schema(),
            annotations=ToolAnnotations(
                read_only_hint=True,
                destructive_hint=False,
                idempotent_hint=True,
                open_world_hint=False,
            ),
        )
    ]


def call_operational_base_search_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name != SEARCH:
        raise ValueError("TOOL_NOT_SUPPORTED")
    request = SearchOperationalBases.model_validate(arguments)
    return search_operational_bases(request).model_dump(mode="json")


__all__ = [
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
    "MAX_QUERY_LENGTH",
    "OperationalBaseSearchItem",
    "OperationalBaseSearchResult",
    "SEARCH",
    "SearchOperationalBases",
    "call_operational_base_search_tool",
    "run_tools",
    "search_operational_bases",
]
