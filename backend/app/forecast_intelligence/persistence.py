"""Caller-owned atomic persistence and authority-independent canonical reload."""

import base64
import binascii
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.forecast_intelligence.errors import HierarchicalForecastError
from backend.app.forecast_intelligence.reconciliation import reconcile
from backend.app.forecast_intelligence.schemas import (
    CreateHierarchicalRun,
    HierarchicalDailyRows,
    HierarchicalHistoryQuery,
    HierarchicalRunHistory,
    HierarchicalRunSummary,
    SavedHierarchicalRun,
)
from backend.app.forecast_quality.operational_peak_persistence import OperationalPeakRunRepository
from backend.app.forecast_quality.operational_peak_schemas import SavedOperationalPeakRun
from backend.app.models.hierarchical_forecast import (
    HierarchicalForecastDaily,
    HierarchicalForecastRun,
    HierarchicalForecastSource,
)

PARENT_FIELDS = (
    "status",
    "execution_hash",
    "reconciliation_policy_version",
    "hierarchy_contract_version",
    "hierarchy_authority_hash",
    "source_authority_hash",
    "target_entity_type",
    "target_entity_id",
    "target_entity_label",
    "target_season",
    "baseline_id",
    "source_policy_version",
    "weather_used",
    "quantile_or_point_label",
    "scenario_id",
    "child_expected_count",
    "child_included_count",
    "child_base_ids_hash",
    "missing_base_ids_hash",
    "source_run_ids_hash",
    "source_result_hashes_hash",
    "result_hash",
)
DATE_FIELDS = ("origin_date", "business_season_start", "business_season_end")


def source_mapping(saved: SavedOperationalPeakRun) -> dict[str, Any]:
    return {
        "run_id": saved.run.run_id,
        "base_id": saved.run.base_id,
        "execution_hash": saved.run.execution_hash,
        "result_hash": saved.run.result_hash,
        "authority_hash": saved.run.authority_hash,
        "result": saved.result,
    }


async def load_sources(session: AsyncSession, ids: list[int]) -> list[dict[str, Any]]:
    try:
        repository = OperationalPeakRunRepository(session)
        return [source_mapping(await repository.get(run_id)) for run_id in ids]
    except Exception as exc:
        # Neither source corruption nor source-not-found is a valid reconciliation.
        raise HierarchicalForecastError("SOURCE_FORECAST_INTEGRITY_FAILED", 422) from exc


def _summary(model: HierarchicalForecastRun) -> HierarchicalRunSummary:
    return HierarchicalRunSummary(
        run_id=model.id,
        **{
            name: getattr(model, name)
            for name in HierarchicalRunSummary.model_fields
            if name != "run_id"
        },
    )


class HierarchicalRunRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, run_id: int) -> SavedHierarchicalRun:
        parent = await self.session.scalar(
            select(HierarchicalForecastRun)
            .where(HierarchicalForecastRun.id == run_id)
            .execution_options(populate_existing=True)
        )
        if parent is None:
            raise HierarchicalForecastError("HIERARCHICAL_FORECAST_RUN_NOT_FOUND", 404)
        try:
            links = list(
                (
                    await self.session.scalars(
                        select(HierarchicalForecastSource)
                        .where(HierarchicalForecastSource.hierarchical_run_id == run_id)
                        .order_by(HierarchicalForecastSource.source_operational_peak_run_id)
                        .execution_options(populate_existing=True)
                    )
                ).all()
            )
            daily = list(
                (
                    await self.session.scalars(
                        select(HierarchicalForecastDaily)
                        .where(HierarchicalForecastDaily.run_id == run_id)
                        .order_by(HierarchicalForecastDaily.row_index)
                        .execution_options(populate_existing=True)
                    )
                ).all()
            )
            request = CreateHierarchicalRun.model_validate(parent.request_snapshot)
            sources = await load_sources(self.session, request.source_run_ids)
            rebuilt = reconcile(parent.hierarchy_snapshot, request, sources)
            expected_links = [
                (s["run_id"], s["base_id"], s["execution_hash"], s["result_hash"]) for s in sources
            ]
            actual_links = [
                (
                    s.source_operational_peak_run_id,
                    s.base_id,
                    s.source_execution_hash,
                    s.source_result_hash,
                )
                for s in links
            ]
            expected_daily = [
                (i, date.fromisoformat(r["date"]), Decimal(r["predicted_kg"]))
                for i, r in enumerate(rebuilt["daily_forecast"])
            ]
            actual_daily = [(r.row_index, r.forecast_date, r.predicted_kg) for r in daily]
            if (
                expected_links != actual_links
                or expected_daily != actual_daily
                or parent.daily_row_count != len(daily)
                or parent.result_metadata
                != {k: v for k, v in rebuilt.items() if k != "daily_forecast"}
                or any(getattr(parent, k) != rebuilt[k] for k in PARENT_FIELDS)
                or any(getattr(parent, k).isoformat() != rebuilt[k] for k in DATE_FIELDS)
                or parent.created_at is None
                or parent.completed_at is None
            ):
                raise ValueError
            return SavedHierarchicalRun(
                run=_summary(parent), result=rebuilt, hierarchy_snapshot=parent.hierarchy_snapshot
            )
        except Exception as exc:
            raise HierarchicalForecastError(
                "HIERARCHICAL_FORECAST_PERSISTENCE_INTEGRITY_FAILED", 500
            ) from exc

    async def existing(self, execution_hash: str) -> SavedHierarchicalRun | None:
        run_id = await self.session.scalar(
            select(HierarchicalForecastRun.id).where(
                HierarchicalForecastRun.execution_hash == execution_hash
            )
        )
        if run_id is None:
            return None
        return (await self.get(run_id)).model_copy(update={"reused_existing_run": True})

    async def save(
        self,
        hierarchy: dict[str, Any],
        request: CreateHierarchicalRun,
        result: dict[str, Any],
        sources: list[dict[str, Any]],
    ) -> SavedHierarchicalRun:
        # Re-validate prior to any insert; repository is not an unchecked alternate writer.
        if reconcile(hierarchy, request, sources) != result:
            raise HierarchicalForecastError("HIERARCHICAL_FORECAST_PERSISTENCE_CONFLICT", 409)
        existing = await self.existing(result["execution_hash"])
        if existing:
            if existing.result != result:
                raise HierarchicalForecastError("HIERARCHICAL_FORECAST_PERSISTENCE_CONFLICT", 409)
            return existing
        try:
            async with self.session.begin_nested():
                now = datetime.now(UTC)
                parent = HierarchicalForecastRun(
                    **{k: result[k] for k in PARENT_FIELDS},
                    **{k: date.fromisoformat(result[k]) for k in DATE_FIELDS},
                    created_at=now,
                    completed_at=now,
                    hierarchy_snapshot=hierarchy,
                    request_snapshot=request.model_dump(mode="json"),
                    result_metadata={k: v for k, v in result.items() if k != "daily_forecast"},
                    daily_row_count=len(result["daily_forecast"]),
                )
                self.session.add(parent)
                await self.session.flush()
                self.session.add_all(
                    [
                        HierarchicalForecastSource(
                            hierarchical_run_id=parent.id,
                            source_operational_peak_run_id=s["run_id"],
                            base_id=s["base_id"],
                            source_execution_hash=s["execution_hash"],
                            source_result_hash=s["result_hash"],
                        )
                        for s in sources
                    ]
                )
                self.session.add_all(
                    [
                        HierarchicalForecastDaily(
                            run_id=parent.id,
                            row_index=i,
                            forecast_date=date.fromisoformat(row["date"]),
                            predicted_kg=Decimal(row["predicted_kg"]),
                        )
                        for i, row in enumerate(result["daily_forecast"])
                    ]
                )
                await self.session.flush()
                return await self.get(parent.id)
        except IntegrityError as exc:
            # Savepoint rollback clears failed inserts. Under READ COMMITTED a concurrent
            # unique winner is now visible; canonical reload still verifies its whole result.
            existing = await self.existing(result["execution_hash"])
            if existing and existing.result == result:
                return existing
            raise HierarchicalForecastError(
                "HIERARCHICAL_FORECAST_PERSISTENCE_CONFLICT", 409
            ) from exc
        except SQLAlchemyError as exc:
            raise HierarchicalForecastError("HIERARCHICAL_FORECAST_WRITE_FAILURE", 503) from exc

    async def daily(self, run_id: int) -> HierarchicalDailyRows:
        saved = await self.get(run_id)
        return HierarchicalDailyRows(run_id=run_id, daily_forecast=saved.result["daily_forecast"])

    async def history(self, query: HierarchicalHistoryQuery) -> HierarchicalRunHistory:
        statement = select(HierarchicalForecastRun)
        for name in (
            "target_entity_type",
            "target_entity_id",
            "target_season",
            "origin_date",
            "reconciliation_policy_version",
        ):
            if (value := getattr(query, name)) is not None:
                statement = statement.where(getattr(HierarchicalForecastRun, name) == value)
        if query.cursor:
            try:
                decoded = json.loads(base64.b64decode(query.cursor, altchars=b"-_", validate=True))
                if (
                    not isinstance(decoded, list)
                    or len(decoded) != 2
                    or type(decoded[1]) is not int
                    or decoded[1] <= 0
                ):
                    raise ValueError
                stamp, run_id = datetime.fromisoformat(decoded[0]), decoded[1]
                statement = statement.where(
                    or_(
                        HierarchicalForecastRun.created_at < stamp,
                        and_(
                            HierarchicalForecastRun.created_at == stamp,
                            HierarchicalForecastRun.id < run_id,
                        ),
                    )
                )
            except (ValueError, TypeError, binascii.Error) as exc:
                raise HierarchicalForecastError("INVALID_REQUEST") from exc
        models = list(
            (
                await self.session.scalars(
                    statement.order_by(
                        HierarchicalForecastRun.created_at.desc(), HierarchicalForecastRun.id.desc()
                    ).limit(query.limit + 1)
                )
            ).all()
        )
        items = [(await self.get(m.id)).run for m in models[: query.limit]]
        cursor = None
        if len(models) > query.limit:
            last = models[query.limit - 1]
            cursor = base64.urlsafe_b64encode(
                json.dumps([last.created_at.isoformat(), last.id]).encode()
            ).decode()
        return HierarchicalRunHistory(items=items, next_cursor=cursor)
