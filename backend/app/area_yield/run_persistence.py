"""Flush-only repository with caller-owned transactions and canonical reload gates."""

import base64
import json
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.area_yield.data import digest
from backend.app.area_yield.evaluation import summaries
from backend.app.area_yield.product import (
    POLICY,
    AreaDrivenForecastRequest,
    AreaDrivenForecastResult,
)
from backend.app.area_yield.run_schemas import (
    AreaRunHistory,
    AreaRunSummary,
    SavedAreaForecastRun,
    same_rerun_scope,
)
from backend.app.models.area_forecast import AreaForecastDailyRow, AreaForecastRun


class AreaForecastPersistenceIntegrityError(RuntimeError):
    code = "AREA_FORECAST_PERSISTENCE_INTEGRITY_FAILED"
    status_code = 500


class AreaForecastPersistenceConflictError(RuntimeError):
    code = "AREA_FORECAST_PERSISTENCE_CONFLICT"
    status_code = 409


class AreaForecastRerunScopeMismatch(AreaForecastPersistenceConflictError):
    code = "AREA_FORECAST_RERUN_SCOPE_MISMATCH"


class AreaForecastWriteFailure(RuntimeError):
    code = "AREA_FORECAST_WRITE_FAILURE"
    status_code = 503


class AreaForecastRunNotFoundError(RuntimeError):
    code = "AREA_FORECAST_RUN_NOT_FOUND"
    status_code = 404


def execution_hash(snapshot: dict[str, Any], authority_hash: str) -> str:
    return digest(
        {
            "schema_version": "AREA_RUN_EXECUTION_V1",
            "forecast_policy_version": POLICY,
            "request": snapshot,
            "authority_hash": authority_hash,
        }
    )


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _check(condition: bool) -> None:
    if not condition:
        raise AreaForecastPersistenceIntegrityError("CANONICAL_RELOAD_FAILED")


def validate_result(result: AreaDrivenForecastResult) -> None:
    """Validate stored output, not refit/reforecast. Existing product hash is unchanged."""
    with localcontext() as ctx:
        ctx.prec = 80
        rows = result.daily_forecast
        _check(len(rows) == (result.season_end - result.season_start).days + 1 and len(rows) >= 7)
        _check(
            [r.date for r in rows]
            == [result.season_start + timedelta(days=i) for i in range(len(rows))]
        )
        quantities = [Decimal(r.predicted_kg) for r in rows]
        shares = [Decimal(r.share) for r in rows]
        _check(all(q.is_finite() and q >= 0 for q in quantities + shares))
        _check(
            all(format(q, ".6f") == r.predicted_kg for q, r in zip(quantities, rows, strict=True))
        )
        _check(abs(sum(shares, Decimal(0)) - 1) <= Decimal("1e-12"))
        total = Decimal(result.predicted_total_kg)
        _check(total.is_finite() and total > 0)
        daily_sum = sum(quantities, Decimal(0))
        difference = daily_sum - total
        tolerance = Decimal("0.0000005") * len(rows) + total * Decimal("1e-12")
        b = result.mass_balance
        _check(
            Decimal(b["daily_sum_kg"]) == daily_sum and Decimal(b["predicted_total_kg"]) == total
        )
        _check(
            Decimal(b["difference_kg"]) == difference and Decimal(b["tolerance_kg"]) == tolerance
        )
        _check(b["pass"] is True and abs(difference) <= tolerance)
        metrics = summaries([r.date for r in rows], quantities)
        _check(
            result.single_day_peak
            == {
                "date": metrics["single_day_peak"]["date"],
                "kg": metrics["single_day_peak"]["quantity_kg"],
            }
        )
        week = metrics["rolling_7day_peak"]
        _check(
            result.rolling_7day_peak
            == {
                "start_date": week["start_date"],
                "end_date": week["end_date"],
                "total_kg": week["cumulative_quantity_kg"],
            }
        )
        _check(
            all(
                re.fullmatch(r"[0-9a-f]{64}", h) is not None
                for h in [
                    result.authority_hash,
                    result.shape_hash,
                    result.result_hash,
                    *result.source_hashes,
                ]
            )
        )
        _check(bool(result.source_hashes) and result.forecast_policy_version == POLICY)
        _check(
            digest(result.model_dump(mode="json", exclude={"result_hash"})) == result.result_hash
        )


class AreaForecastRunRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, run_id: int) -> SavedAreaForecastRun:
        model = await self.session.scalar(
            select(AreaForecastRun)
            .where(AreaForecastRun.id == run_id)
            .execution_options(populate_existing=True)
        )
        if model is None:
            raise AreaForecastRunNotFoundError("RUN_NOT_FOUND")
        try:
            rows = list(
                await self.session.scalars(
                    select(AreaForecastDailyRow)
                    .where(AreaForecastDailyRow.run_id == run_id)
                    .order_by(AreaForecastDailyRow.row_index)
                    .execution_options(populate_existing=True)
                )
            )
            _check(len(rows) == model.daily_row_count)
            _check([r.row_index for r in rows] == list(range(len(rows))))
            _check(
                all(
                    r.predicted_kg.is_finite()
                    and r.predicted_kg == Decimal(format(r.predicted_kg, ".6f"))
                    for r in rows
                )
            )
            _check(all(r.share == Decimal(r.share_text) for r in rows))
            _check("daily_forecast" not in model.result_metadata)
            payload = {
                **model.result_metadata,
                "daily_forecast": [
                    {
                        "date": r.date.isoformat(),
                        "predicted_kg": format(r.predicted_kg, ".6f"),
                        "share": r.share_text,
                    }
                    for r in rows
                ],
            }
            result = AreaDrivenForecastResult.model_validate(payload)
            _check(result.model_dump(mode="json") == payload)
            validate_result(result)
            request = AreaDrivenForecastRequest.model_validate(model.request_snapshot)
            _check(request.model_dump(mode="json") == model.request_snapshot)
            _check(
                execution_hash(model.request_snapshot, result.authority_hash) == model.request_hash
            )
            _check(
                model.status == "completed" and _utc(model.completed_at) >= _utc(model.created_at)
            )
            for key in (
                "canonical_farm",
                "target_season",
                "season_start",
                "season_end",
                "history_cutoff",
                "total_model",
                "total_model_source_season",
                "authority_hash",
                "shape_hash",
                "forecast_policy_version",
                "model_version",
                "result_hash",
            ):
                _check(getattr(model, key) == getattr(result, key))
            for key in (
                "requested_productive_area_mu",
                "predicted_yield_kg_per_mu",
                "predicted_total_kg",
            ):
                _check(getattr(model, key) == Decimal(getattr(result, key)))
            _check(request.productive_area_mu == result.requested_productive_area_mu)
            _check(request.target_season == result.target_season)
            _check(request.season_start is None or request.season_start == result.season_start)
            _check(request.season_end is None or request.season_end == result.season_end)
            _check(request.as_of is None or request.as_of == result.history_cutoff)
            if model.rerun_of_run_id is not None:
                _check(model.rerun_of_run_id < model.id)
                _check(
                    await self.session.scalar(
                        select(AreaForecastRun.id).where(
                            AreaForecastRun.id == model.rerun_of_run_id
                        )
                    )
                    is not None
                )
                parent = await self.get(model.rerun_of_run_id)
                _check(
                    same_rerun_scope(
                        parent.result,
                        canonical_farm=result.canonical_farm,
                        target_season=result.target_season,
                        season_start=result.season_start,
                        season_end=result.season_end,
                    )
                )
            summary = AreaRunSummary(
                run_id=model.id,
                created_at=_utc(model.created_at),
                completed_at=_utc(model.completed_at),
                request_hash=model.request_hash,
                rerun_of_run_id=model.rerun_of_run_id,
                **{
                    k: getattr(result, k)
                    for k in (
                        "canonical_farm",
                        "requested_productive_area_mu",
                        "target_season",
                        "predicted_total_kg",
                        "single_day_peak",
                        "rolling_7day_peak",
                        "forecast_policy_version",
                        "authority_hash",
                        "result_hash",
                    )
                },
            )
            return SavedAreaForecastRun(
                run=summary, request_snapshot=model.request_snapshot, result=result
            )
        except AreaForecastPersistenceIntegrityError:
            raise
        except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
            raise AreaForecastPersistenceIntegrityError("CANONICAL_RELOAD_FAILED") from exc

    async def existing(
        self, request_hash: str, snapshot: dict[str, Any]
    ) -> SavedAreaForecastRun | None:
        model = await self.session.scalar(
            select(AreaForecastRun)
            .where(AreaForecastRun.request_hash == request_hash)
            .execution_options(populate_existing=True)
        )
        if model is None:
            return None
        if model.request_snapshot != snapshot:
            raise AreaForecastPersistenceConflictError("EXECUTION_SNAPSHOT_CONFLICT")
        loaded = await self.get(model.id)
        return loaded.model_copy(update={"reused_existing_run": True})

    async def save(
        self,
        snapshot: dict[str, Any],
        result: AreaDrivenForecastResult,
        request_hash: str,
        rerun_of_run_id: int | None,
    ) -> SavedAreaForecastRun:
        if execution_hash(snapshot, result.authority_hash) != request_hash:
            raise AreaForecastPersistenceConflictError("EXECUTION_IDENTITY_CONFLICT")
        existing = await self.existing(request_hash, snapshot)
        if existing:
            if existing.result != result:
                raise AreaForecastPersistenceConflictError("EXECUTION_RESULT_CONFLICT")
            return existing
        validate_result(result)
        now = datetime.now(UTC)
        try:
            async with self.session.begin_nested():
                model = AreaForecastRun(
                    status="completed",
                    created_at=now,
                    completed_at=now,
                    request_hash=request_hash,
                    request_snapshot=snapshot,
                    result_metadata=result.model_dump(mode="json", exclude={"daily_forecast"}),
                    daily_row_count=len(result.daily_forecast),
                    rerun_of_run_id=rerun_of_run_id,
                    **{
                        k: getattr(result, k)
                        for k in (
                            "canonical_farm",
                            "target_season",
                            "season_start",
                            "season_end",
                            "history_cutoff",
                            "total_model",
                            "total_model_source_season",
                            "authority_hash",
                            "shape_hash",
                            "forecast_policy_version",
                            "model_version",
                            "result_hash",
                        )
                    },
                    **{
                        k: Decimal(getattr(result, k))
                        for k in (
                            "requested_productive_area_mu",
                            "predicted_yield_kg_per_mu",
                            "predicted_total_kg",
                        )
                    },
                )
                self.session.add(model)
                await self.session.flush()
                self.session.add_all(
                    [
                        AreaForecastDailyRow(
                            run_id=model.id,
                            row_index=i,
                            date=r.date,
                            predicted_kg=Decimal(r.predicted_kg),
                            share=Decimal(r.share),
                            share_text=r.share,
                        )
                        for i, r in enumerate(result.daily_forecast)
                    ]
                )
                await self.session.flush()
                # Validation belongs INSIDE savepoint so a failed reload leaves no partial run.
                return await self.get(model.id)
        except IntegrityError as exc:
            existing = await self.existing(request_hash, snapshot)
            if existing and existing.result == result:
                return existing
            raise AreaForecastPersistenceConflictError("EXECUTION_WRITE_CONFLICT") from exc
        except SQLAlchemyError as exc:
            raise AreaForecastWriteFailure("ATOMIC_WRITE_FAILED") from exc

    async def history(
        self,
        *,
        canonical_farm: str | None = None,
        target_season: str | None = None,
        forecast_policy_version: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> AreaRunHistory:
        if not 1 <= limit <= 100:
            raise ValueError("INVALID_HISTORY_LIMIT")
        query = select(AreaForecastRun.id)
        for key, value in (
            ("canonical_farm", canonical_farm),
            ("target_season", target_season),
            ("forecast_policy_version", forecast_policy_version),
        ):
            if value is not None:
                query = query.where(getattr(AreaForecastRun, key) == value)
        if cursor:
            try:
                stamp, run_id = json.loads(base64.urlsafe_b64decode(cursor.encode()))
                stamp = datetime.fromisoformat(stamp)
                if not isinstance(run_id, int) or run_id <= 0 or stamp.tzinfo is None:
                    raise ValueError
            except (ValueError, TypeError, UnicodeError) as exc:
                raise ValueError("INVALID_HISTORY_CURSOR") from exc
            query = query.where(
                or_(
                    AreaForecastRun.created_at < stamp,
                    and_(AreaForecastRun.created_at == stamp, AreaForecastRun.id < run_id),
                )
            )
        ids = list(
            await self.session.scalars(
                query.order_by(AreaForecastRun.created_at.desc(), AreaForecastRun.id.desc()).limit(
                    limit + 1
                )
            )
        )
        items = [(await self.get(i)).run for i in ids[:limit]]
        next_cursor = None
        if len(ids) > limit:
            last = items[-1]
            next_cursor = base64.urlsafe_b64encode(
                json.dumps([last.created_at.isoformat(), last.run_id]).encode()
            ).decode()
        return AreaRunHistory(items=items, next_cursor=next_cursor)
