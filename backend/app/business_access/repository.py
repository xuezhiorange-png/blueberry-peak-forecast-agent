"""Minimal metadata SQL, restricted to already authorized physical run IDs.

No daily values, business totals, global counts, registry inference or writes.
All filters, deterministic ordering, keyset and LIMIT execute in PostgreSQL.
"""

from datetime import date
from typing import Any

from sqlalchemy import Select, and_, literal, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.business_access.schemas import Filters
from backend.app.forecast_intelligence.read_schemas import ForecastReadQuery
from backend.app.forecast_intelligence.read_service import FORECAST_FAMILY
from backend.app.local_auth.sessions import AuthError
from backend.app.models.hierarchical_forecast import HierarchicalForecastRun
from backend.app.models.operational_peak import OperationalPeakForecastRun


def metadata_statement(queries: list[ForecastReadQuery]) -> Any:
    branches = []
    for source_kind, model in (
        ("OPERATIONAL_PEAK", OperationalPeakForecastRun),
        ("HIERARCHICAL", HierarchicalForecastRun),
    ):
        ids = sorted({q.run_id for q in queries if q.source_kind == source_kind})
        if not ids:
            continue
        level: Any
        rerun: Any
        if source_kind == "OPERATIONAL_PEAK":
            level = literal("BASE")
            entity = OperationalPeakForecastRun.base_id
            label = OperationalPeakForecastRun.canonical_base_name
            policy = OperationalPeakForecastRun.policy_version
            rerun = OperationalPeakForecastRun.rerun_of_run_id
        else:
            level = HierarchicalForecastRun.target_entity_type
            entity = HierarchicalForecastRun.target_entity_id
            label = HierarchicalForecastRun.target_entity_label
            policy = HierarchicalForecastRun.source_policy_version
            rerun = literal(None)
        branches.append(
            select(
                literal(source_kind).label("source_kind"),
                literal(FORECAST_FAMILY).label("forecast_family"),
                model.id.label("run_id"),
                level.label("hierarchy_level"),
                entity.label("entity_id"),
                model.target_season,
                model.origin_date,
                model.baseline_id,
                policy.label("policy_version"),
                model.result_hash.label("source_result_hash"),
                label.label("entity_name"),
                model.status.label("source_status"),
                model.daily_row_count,
                model.created_at,
                rerun.label("rerun_of_run_id"),
            ).where(model.id.in_(ids))
        )
    if not branches:
        raise AuthError("FORBIDDEN")
    return union_all(*branches).subquery("authorized_saved_runs")


def ordered_statement(
    table: Any,
    filters: Filters | None = None,
    last_key: tuple[str, str, str, int, str, str] | None = None,
) -> Select[Any]:
    statement = select(table)
    if filters is not None:
        for field in ("target_season", "hierarchy_level", "entity_id", "forecast_family"):
            value = getattr(filters, field)
            if value is not None:
                statement = statement.where(getattr(table.c, field) == value)
        if filters.origin_from is not None:
            statement = statement.where(table.c.origin_date >= filters.origin_from)
        if filters.origin_to is not None:
            statement = statement.where(table.c.origin_date <= filters.origin_to)
    columns = (
        table.c.origin_date,
        table.c.source_kind,
        table.c.forecast_family,
        table.c.run_id,
        table.c.entity_id,
        table.c.source_result_hash,
    )
    descending = (True, False, False, True, False, False)
    if last_key is not None:
        values: tuple[Any, ...] = (date.fromisoformat(last_key[0]), *last_key[1:])
        terms = []
        for i, (column, desc) in enumerate(zip(columns, descending, strict=True)):
            terms.append(
                and_(
                    *(columns[j] == values[j] for j in range(i)),
                    column < values[i] if desc else column > values[i],
                )
            )
        statement = statement.where(or_(*terms))
    return statement.order_by(
        *(c.desc() if d else c.asc() for c, d in zip(columns, descending, strict=True))
    )


async def rows(
    db: AsyncSession,
    queries: list[ForecastReadQuery],
    *,
    filters: Filters | None = None,
    last_key: tuple[str, str, str, int, str, str] | None = None,
) -> list[dict[str, Any]]:
    statement = ordered_statement(metadata_statement(queries), filters, last_key)
    if filters is not None:
        statement = statement.limit(filters.page_size + 1)
    return [dict(row) for row in (await db.execute(statement)).mappings()]


def key(row: dict[str, Any]) -> tuple[str, str, str, int, str, str]:
    return (
        row["origin_date"].isoformat(),
        row["source_kind"],
        row["forecast_family"],
        row["run_id"],
        row["entity_id"],
        row["source_result_hash"],
    )
