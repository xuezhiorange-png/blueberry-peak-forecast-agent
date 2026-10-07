"""Authority-derived technical hierarchy; no geographic or identity inference."""

from typing import Any

from backend.app.area_yield.data import digest
from backend.app.forecast_intelligence.errors import HierarchicalForecastError

COMPANY_ID = "COMPANY_AGGREGATE_ROOT_V1"
CONTRACT_VERSION = "V0_16_HIERARCHY_R1"
COMPANY_SEMANTICS = "TECHNICAL_FORECAST_AGGREGATION_ROOT_NOT_LEGAL_ENTITY_IDENTITY"


def build_hierarchy(
    registry: dict[str, Any], authority_hash: str, registry_hash: str
) -> dict[str, Any]:
    values = registry.get("bases")
    if isinstance(values, dict):
        values = list(values.values())
    if not isinstance(values, list) or not values:
        raise HierarchicalForecastError("HIERARCHY_AUTHORITY_INCOMPLETE")
    bases: list[dict[str, Any]] = []
    regions: dict[str, list[str]] = {}
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, dict):
            raise HierarchicalForecastError("HIERARCHY_AUTHORITY_INCOMPLETE")
        base_id, name = value.get("base_id"), value.get("canonical_base_name")
        active = bool(value.get("active", True))  # Operational Peak's frozen semantics.
        region = value.get("region_scope")
        if (
            not isinstance(base_id, str)
            or not base_id
            or base_id in seen
            or not isinstance(name, str)
            or not name
            or (active and (not isinstance(region, str) or not region.strip()))
        ):
            raise HierarchicalForecastError("HIERARCHY_AUTHORITY_INCOMPLETE")
        seen.add(base_id)
        # Inactive entries are retained for audit, but never admitted as children.
        region_id = region if isinstance(region, str) and region.strip() else None
        bases.append(
            {
                "base_id": base_id,
                "canonical_base_name": name,
                "region_id": region_id,
                "active": active,
            }
        )
        if active:
            assert isinstance(region, str)
            regions.setdefault(region, []).append(base_id)
    if not regions:
        raise HierarchicalForecastError("HIERARCHY_AUTHORITY_INCOMPLETE")
    payload = {
        "hierarchy_contract_version": CONTRACT_VERSION,
        "source_operational_peak_authority_hash": authority_hash,
        "source_base_registry_hash": registry_hash,
        "company": {
            "entity_id": COMPANY_ID,
            "entity_label": "ALL_REGISTERED_BASES",
            "entity_semantics": COMPANY_SEMANTICS,
        },
        "regions": [
            {"region_id": r, "region_name": r, "active_child_base_ids": sorted(regions[r])}
            for r in sorted(regions)
        ],
        "bases": sorted(bases, key=lambda b: b["base_id"]),
    }
    return {**payload, "hierarchy_authority_hash": digest(payload)}


def validate_hierarchy(snapshot: dict[str, Any]) -> None:
    """Rebuild stored sanitized snapshot without the current authority file."""
    try:
        registry = {"bases": [{**b, "region_scope": b["region_id"]} for b in snapshot["bases"]]}
        rebuilt = build_hierarchy(
            registry,
            snapshot["source_operational_peak_authority_hash"],
            snapshot["source_base_registry_hash"],
        )
        if snapshot != rebuilt:
            raise ValueError
    except (KeyError, TypeError, ValueError) as exc:
        raise HierarchicalForecastError(
            "HIERARCHICAL_FORECAST_PERSISTENCE_INTEGRITY_FAILED", 500
        ) from exc
