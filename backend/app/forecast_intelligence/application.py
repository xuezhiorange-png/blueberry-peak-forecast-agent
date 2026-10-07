"""S1 create boundary: only saved, integrity-checked Operational Peak sources."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.forecast_intelligence.errors import HierarchicalForecastError
from backend.app.forecast_intelligence.hierarchy import build_hierarchy
from backend.app.forecast_intelligence.persistence import HierarchicalRunRepository, load_sources
from backend.app.forecast_intelligence.reconciliation import reconcile
from backend.app.forecast_intelligence.schemas import CreateHierarchicalRun, SavedHierarchicalRun
from backend.app.forecast_quality import operational_peak_authority


def current_hierarchy() -> dict[str, Any]:
    try:
        authority = operational_peak_authority.load_operational_peak_authority()
        return build_hierarchy(
            authority.registry,
            authority.authority_hash,
            operational_peak_authority.REGISTRY_PAYLOAD_HASH,
        )
    except HierarchicalForecastError:
        raise
    except Exception as exc:
        raise HierarchicalForecastError("HIERARCHY_AUTHORITY_INCOMPLETE", 503) from exc


async def execute_hierarchical_run(
    session: AsyncSession, request: CreateHierarchicalRun
) -> SavedHierarchicalRun:
    hierarchy = current_hierarchy()
    sources = await load_sources(session, request.source_run_ids)
    result = reconcile(hierarchy, request, sources)
    return await HierarchicalRunRepository(session).save(hierarchy, request, result, sources)
