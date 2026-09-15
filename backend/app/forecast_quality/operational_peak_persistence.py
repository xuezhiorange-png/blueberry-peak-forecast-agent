"""Caller-owned immutable persistence for S6 operational peak runs."""

from __future__ import annotations

import base64
import binascii
import json
import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.area_yield.data import digest
from backend.app.forecast_quality.operational_peak import (
    DailyForecast,
    OperationalPeakForecastError,
    OperationalPeakForecastRequest,
    OperationalPeakForecastResult,
    PeakWindowForecast,
    canonical_result_hash,
    dates_between,
    summarize_window,
)
from backend.app.forecast_quality.operational_peak_schemas import (
    OperationalPeakDailyRows,
    OperationalPeakRunHistory,
    OperationalPeakRunSummary,
    SavedOperationalPeakRun,
)
from backend.app.models.operational_peak import (
    OperationalPeakForecastDaily,
    OperationalPeakForecastRun,
)

EXECUTION_SCHEMA_VERSION = "OPERATIONAL_PEAK_RUN_V1"
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


class OperationalPeakPersistenceIntegrityError(RuntimeError):
    code = "OPERATIONAL_PEAK_PERSISTENCE_INTEGRITY_ERROR"
    status_code = 500


class OperationalPeakPersistenceConflictError(RuntimeError):
    code = "OPERATIONAL_PEAK_PERSISTENCE_CONFLICT"
    status_code = 409


class OperationalPeakRerunScopeMismatch(OperationalPeakPersistenceConflictError):
    code = "OPERATIONAL_PEAK_RERUN_SCOPE_MISMATCH"


class OperationalPeakWriteFailure(RuntimeError):
    code = "OPERATIONAL_PEAK_WRITE_FAILURE"
    status_code = 503


class OperationalPeakRunNotFoundError(RuntimeError):
    code = "OPERATIONAL_PEAK_RUN_NOT_FOUND"
    status_code = 404


def execution_hash(snapshot: dict[str, Any], authority_hash: str, policy_version: str) -> str:
    """Hash the canonical request, product policy and one authority snapshot."""

    return digest(
        {
            "schema_version": EXECUTION_SCHEMA_VERSION,
            "canonical_request": snapshot,
            "authority_hash": authority_hash,
            "policy_version": policy_version,
        }
    )


def request_snapshot(request: OperationalPeakForecastRequest) -> dict[str, str]:
    return {
        "base_id": request.base_id,
        "target_season": request.target_season,
        "origin_date": request.origin_date.isoformat(),
    }


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _decimal(value: Any, label: str) -> Decimal:
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise OperationalPeakPersistenceIntegrityError(f"INVALID_{label.upper()}") from exc
    if not result.is_finite():
        raise OperationalPeakPersistenceIntegrityError(f"INVALID_{label.upper()}")
    return result


def _date(value: Any, label: str) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise OperationalPeakPersistenceIntegrityError(f"INVALID_{label.upper()}") from exc


def _peak_from_mapping(value: Any) -> PeakWindowForecast:
    if not isinstance(value, dict):
        raise OperationalPeakPersistenceIntegrityError("INVALID_WINDOW_SNAPSHOT")
    start = value.get("start_date")
    end = value.get("end_date")
    total = value.get("total_kg")
    peak_date = value.get("peak_date")
    peak_kg = value.get("peak_kg")
    return PeakWindowForecast(
        window_days=value.get("window_days"),
        status=str(value.get("status")),
        start_date=_date(start, "window_start") if start is not None else None,
        end_date=_date(end, "window_end") if end is not None else None,
        total_kg=_decimal(total, "window_total") if total is not None else None,
        peak_date=_date(peak_date, "window_peak_date") if peak_date is not None else None,
        peak_kg=_decimal(peak_kg, "window_peak_kg") if peak_kg is not None else None,
        available_days=int(value.get("available_days", 0)),
        reason=value.get("reason"),
    )


def _daily_from_model(row: OperationalPeakForecastDaily) -> DailyForecast:
    if row.row_index < 0 or row.reference_bin < 0:
        raise OperationalPeakPersistenceIntegrityError("INVALID_DAILY_ROW")
    predicted = _decimal(row.predicted_kg, "predicted_kg")
    kg_per_mu = _decimal(row.kg_per_mu, "kg_per_mu")
    if predicted < 0 or kg_per_mu < 0:
        raise OperationalPeakPersistenceIntegrityError("INVALID_DAILY_ROW")
    return DailyForecast(
        date=row.forecast_date,
        predicted_kg=predicted,
        kg_per_mu=kg_per_mu,
        business_season_day_index=row.business_season_day_index,
        reference_bin=row.reference_bin,
    )


def _result_from_model(
    model: OperationalPeakForecastRun, rows: list[OperationalPeakForecastDaily]
) -> OperationalPeakForecastResult:
    metadata = model.result_metadata
    if "daily_forecast" in metadata or not isinstance(metadata, dict):
        raise OperationalPeakPersistenceIntegrityError("MALFORMED_RESULT_SNAPSHOT")
    try:
        daily = tuple(_daily_from_model(row) for row in rows)
        result = OperationalPeakForecastResult(
            base_id=str(metadata["base_id"]),
            canonical_base_name=str(metadata["canonical_base_name"]),
            productive_area_mu=_decimal(metadata["productive_area_mu"], "area"),
            area_basis=metadata.get("area_basis"),
            target_season=str(metadata["target_season"]),
            origin_date=_date(metadata["origin_date"], "origin_date"),
            business_season_start=_date(metadata["business_season_start"], "season_start"),
            business_season_end=_date(metadata["business_season_end"], "season_end"),
            daily_forecast=daily,
            forecast_7d=_peak_from_mapping(metadata["forecast_7d"]),
            forecast_15d=_peak_from_mapping(metadata["forecast_15d"]),
            remaining_business_window=_peak_from_mapping(metadata["remaining_business_window"]),
            baseline_id=str(metadata["baseline_id"]),
            policy_version=str(metadata["policy_version"]),
            weather_used=bool(metadata["weather_used"]),
            weather=metadata.get("weather"),
            limitations=tuple(str(item) for item in metadata["limitations"]),
            result_hash=str(metadata["result_hash"]),
        )
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        raise OperationalPeakPersistenceIntegrityError("MALFORMED_RESULT_SNAPSHOT") from exc
    return result


def _check(condition: bool, reason: str = "CANONICAL_RELOAD_FAILED") -> None:
    if not condition:
        raise OperationalPeakPersistenceIntegrityError(reason)


def validate_persisted_result(
    model: OperationalPeakForecastRun,
    rows: list[OperationalPeakForecastDaily],
) -> OperationalPeakForecastResult:
    """Rebuild and verify the product result without authority or reforecasting."""

    _check(model.status == "completed")
    _check(_utc(model.completed_at) >= _utc(model.created_at))
    _check(len(rows) == model.daily_row_count)
    _check([row.row_index for row in rows] == list(range(len(rows))))
    _check(len({row.forecast_date for row in rows}) == len(rows), "DUPLICATE_DAILY_DATE")
    result = _result_from_model(model, rows)
    expected_dates = dates_between(
        result.origin_date + timedelta(days=1),
        min(result.origin_date + timedelta(days=15), result.business_season_end),
    )
    _check(tuple(row.date for row in result.daily_forecast) == expected_dates, "DAILY_DATE_GAP")
    _check(result.base_id == model.base_id)
    _check(result.canonical_base_name == model.canonical_base_name)
    _check(result.target_season == model.target_season)
    _check(result.origin_date == model.origin_date)
    _check(result.business_season_start == model.business_season_start)
    _check(result.business_season_end == model.business_season_end)
    _check(result.productive_area_mu == model.productive_area_mu)
    _check(result.policy_version == model.policy_version)
    _check(result.baseline_id == model.baseline_id)
    _check(result.weather_used is model.weather_used)
    _check(result.result_hash == model.result_hash)
    _check(model.request_hash == model.execution_hash, "REQUEST_HASH_MISMATCH")
    _check(_HASH_RE.fullmatch(model.execution_hash) is not None)
    _check(_HASH_RE.fullmatch(model.authority_hash) is not None)
    _check(_HASH_RE.fullmatch(model.result_hash) is not None)
    _check(
        execution_hash(model.request_snapshot, model.authority_hash, model.policy_version)
        == model.execution_hash
    )

    expected_metadata = {
        key: value for key, value in result.to_mapping().items() if key != "daily_forecast"
    }
    _check(model.result_metadata == expected_metadata, "RESULT_METADATA_MISMATCH")
    _check(
        canonical_result_hash(result) == result.result_hash,
        "RESULT_HASH_MISMATCH",
    )
    for row, expected in zip(rows, result.daily_forecast, strict=True):
        _check(row.forecast_date == expected.date)
        _check(row.predicted_kg == expected.predicted_kg, "DAILY_QUANTITY_MISMATCH")
        _check(row.kg_per_mu == expected.kg_per_mu, "DAILY_KG_PER_MU_MISMATCH")
        _check(row.business_season_day_index == expected.business_season_day_index)
        _check(row.reference_bin == expected.reference_bin)

    w7 = summarize_window(
        result.daily_forecast,
        origin_date=result.origin_date,
        window_days=7,
        business_start=result.business_season_start,
        business_end=result.business_season_end,
    )
    w15 = summarize_window(
        result.daily_forecast,
        origin_date=result.origin_date,
        window_days=15,
        business_start=result.business_season_start,
        business_end=result.business_season_end,
    )
    _check(w7.to_mapping() == result.forecast_7d.to_mapping(), "W7_PERSISTENCE_MISMATCH")
    _check(w15.to_mapping() == result.forecast_15d.to_mapping(), "W15_PERSISTENCE_MISMATCH")
    _check(
        model.forecast_7d == result.forecast_7d.to_mapping(),
        "W7_PARENT_MISMATCH",
    )
    _check(
        model.forecast_15d == result.forecast_15d.to_mapping(),
        "W15_PARENT_MISMATCH",
    )
    _check(
        model.remaining_business_window == result.remaining_business_window.to_mapping(),
        "REMAINING_WINDOW_MISMATCH",
    )
    return result


def _summary(
    model: OperationalPeakForecastRun, result: OperationalPeakForecastResult
) -> OperationalPeakRunSummary:
    return OperationalPeakRunSummary(
        run_id=model.id,
        execution_hash=model.execution_hash,
        request_hash=model.request_hash,
        authority_hash=model.authority_hash,
        result_hash=model.result_hash,
        base_id=model.base_id,
        canonical_base_name=model.canonical_base_name,
        productive_area_mu=format(model.productive_area_mu, "f"),
        target_season=model.target_season,
        origin_date=model.origin_date,
        baseline_id=model.baseline_id,
        policy_version=model.policy_version,
        weather_used=model.weather_used,
        forecast_7d=result.forecast_7d.to_mapping(),
        forecast_15d=result.forecast_15d.to_mapping(),
        remaining_business_window=result.remaining_business_window.to_mapping(),
        created_at=_utc(model.created_at),
        completed_at=_utc(model.completed_at),
        rerun_of_run_id=model.rerun_of_run_id,
    )


class OperationalPeakRunRepository:
    """Repository that flushes only; transaction ownership stays at the boundary."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, run_id: int) -> SavedOperationalPeakRun:
        model = await self.session.scalar(
            select(OperationalPeakForecastRun)
            .where(OperationalPeakForecastRun.id == run_id)
            .execution_options(populate_existing=True)
        )
        if model is None:
            raise OperationalPeakRunNotFoundError("RUN_NOT_FOUND")
        try:
            rows = list(
                await self.session.scalars(
                    select(OperationalPeakForecastDaily)
                    .where(OperationalPeakForecastDaily.run_id == run_id)
                    .order_by(OperationalPeakForecastDaily.row_index)
                    .execution_options(populate_existing=True)
                )
            )
            result = validate_persisted_result(model, rows)
            snapshot = model.request_snapshot
            request = OperationalPeakForecastRequest.from_mapping(snapshot)
            _check(request.base_id == model.base_id)
            _check(request.target_season == model.target_season)
            _check(request.origin_date == model.origin_date)
            if model.rerun_of_run_id is not None:
                _check(model.rerun_of_run_id < model.id, "INVALID_RERUN_LINEAGE")
                parent = await self.get(model.rerun_of_run_id)
                if not _same_scope(parent.result, result):
                    raise OperationalPeakPersistenceIntegrityError("RERUN_SCOPE_MISMATCH")
            return SavedOperationalPeakRun(
                run=_summary(model, result),
                request_snapshot=snapshot,
                result=result.to_mapping(),
            )
        except OperationalPeakPersistenceIntegrityError:
            raise
        except (
            OperationalPeakForecastError,
            ValueError,
            KeyError,
            TypeError,
            ArithmeticError,
        ) as exc:
            raise OperationalPeakPersistenceIntegrityError("CANONICAL_RELOAD_FAILED") from exc

    async def existing(
        self, execution_id: str, snapshot: dict[str, Any]
    ) -> SavedOperationalPeakRun | None:
        model = await self.session.scalar(
            select(OperationalPeakForecastRun)
            .where(OperationalPeakForecastRun.execution_hash == execution_id)
            .execution_options(populate_existing=True)
        )
        if model is None:
            return None
        if model.request_snapshot != snapshot:
            raise OperationalPeakPersistenceConflictError("EXECUTION_SNAPSHOT_CONFLICT")
        loaded = await self.get(model.id)
        return loaded.model_copy(update={"reused_existing_run": True})

    async def save(
        self,
        snapshot: dict[str, Any],
        result: OperationalPeakForecastResult,
        execution_id: str,
        authority_hash: str,
        rerun_of_run_id: int | None,
    ) -> SavedOperationalPeakRun:
        if execution_hash(snapshot, authority_hash, result.policy_version) != execution_id:
            raise OperationalPeakPersistenceConflictError("EXECUTION_IDENTITY_CONFLICT")
        existing = await self.existing(execution_id, snapshot)
        if existing:
            if existing.result != result.to_mapping():
                raise OperationalPeakPersistenceConflictError("EXECUTION_RESULT_CONFLICT")
            return existing
        if rerun_of_run_id is not None:
            parent = await self.get(rerun_of_run_id)
            if not _same_scope(parent.result, result):
                raise OperationalPeakRerunScopeMismatch("RERUN_SCOPE_MISMATCH")

        now = datetime.now(UTC)
        metadata = {
            key: value for key, value in result.to_mapping().items() if key != "daily_forecast"
        }
        try:
            async with self.session.begin_nested():
                model = OperationalPeakForecastRun(
                    status="completed",
                    created_at=now,
                    completed_at=now,
                    execution_hash=execution_id,
                    request_hash=execution_id,
                    request_snapshot=snapshot,
                    result_metadata=metadata,
                    authority_hash=authority_hash,
                    policy_version=result.policy_version,
                    baseline_id=result.baseline_id,
                    base_id=result.base_id,
                    canonical_base_name=result.canonical_base_name,
                    productive_area_mu=result.productive_area_mu,
                    target_season=result.target_season,
                    origin_date=result.origin_date,
                    business_season_start=result.business_season_start,
                    business_season_end=result.business_season_end,
                    weather_used=result.weather_used,
                    result_hash=result.result_hash,
                    daily_row_count=len(result.daily_forecast),
                    forecast_7d=result.forecast_7d.to_mapping(),
                    forecast_15d=result.forecast_15d.to_mapping(),
                    remaining_business_window=result.remaining_business_window.to_mapping(),
                    rerun_of_run_id=rerun_of_run_id,
                )
                self.session.add(model)
                await self.session.flush()
                self.session.add_all(
                    [
                        OperationalPeakForecastDaily(
                            run_id=model.id,
                            row_index=index,
                            forecast_date=row.date,
                            predicted_kg=row.predicted_kg,
                            kg_per_mu=row.kg_per_mu,
                            business_season_day_index=row.business_season_day_index,
                            reference_bin=row.reference_bin,
                        )
                        for index, row in enumerate(result.daily_forecast)
                    ]
                )
                await self.session.flush()
                return await self.get(model.id)
        except IntegrityError as exc:
            existing = await self.existing(execution_id, snapshot)
            if existing and existing.result == result.to_mapping():
                return existing
            raise OperationalPeakPersistenceConflictError("EXECUTION_WRITE_CONFLICT") from exc
        except SQLAlchemyError as exc:
            raise OperationalPeakWriteFailure("ATOMIC_WRITE_FAILED") from exc

    async def history(
        self,
        *,
        base_id: str | None = None,
        target_season: str | None = None,
        policy_version: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> OperationalPeakRunHistory:
        if not 1 <= limit <= 100:
            raise ValueError("INVALID_HISTORY_LIMIT")
        query = select(OperationalPeakForecastRun.id)
        for column, value in (
            (OperationalPeakForecastRun.base_id, base_id),
            (OperationalPeakForecastRun.target_season, target_season),
            (OperationalPeakForecastRun.policy_version, policy_version),
        ):
            if value is not None:
                query = query.where(column == value)
        if cursor:
            try:
                stamp, run_id = json.loads(base64.urlsafe_b64decode(cursor.encode()))
                stamp = datetime.fromisoformat(stamp)
                if not isinstance(run_id, int) or run_id <= 0 or stamp.tzinfo is None:
                    raise ValueError
            except (
                binascii.Error,
                ValueError,
                TypeError,
                UnicodeError,
                json.JSONDecodeError,
            ) as exc:
                raise ValueError("INVALID_HISTORY_CURSOR") from exc
            query = query.where(
                or_(
                    OperationalPeakForecastRun.created_at < stamp,
                    and_(
                        OperationalPeakForecastRun.created_at == stamp,
                        OperationalPeakForecastRun.id < run_id,
                    ),
                )
            )
        ids = list(
            await self.session.scalars(
                query.order_by(
                    OperationalPeakForecastRun.created_at.desc(),
                    OperationalPeakForecastRun.id.desc(),
                ).limit(limit + 1)
            )
        )
        loaded = [await self.get(run_id) for run_id in ids[:limit]]
        items = [item.run for item in loaded]
        next_cursor = None
        if len(ids) > limit and items:
            last = items[-1]
            next_cursor = base64.urlsafe_b64encode(
                json.dumps([last.created_at.isoformat(), last.run_id]).encode()
            ).decode()
        return OperationalPeakRunHistory(items=items, next_cursor=next_cursor)

    async def daily(self, run_id: int) -> OperationalPeakDailyRows:
        saved = await self.get(run_id)
        return OperationalPeakDailyRows(
            run_id=run_id,
            daily_forecast=saved.result["daily_forecast"],
        )


def _same_scope(
    parent: dict[str, Any] | OperationalPeakForecastResult, child: OperationalPeakForecastResult
) -> bool:
    parent_base: Any
    parent_season: Any
    parent_origin: Any
    parent_start: Any
    parent_end: Any
    if isinstance(parent, OperationalPeakForecastResult):
        parent_base = parent.base_id
        parent_season = parent.target_season
        parent_origin = parent.origin_date
        parent_start = parent.business_season_start
        parent_end = parent.business_season_end
    else:
        parent_base = parent.get("base_id")
        parent_season = parent.get("target_season")
        parent_origin = parent.get("origin_date")
        parent_start = parent.get("business_season_start")
        parent_end = parent.get("business_season_end")
    return (
        parent_base == child.base_id
        and parent_season == child.target_season
        and str(parent_origin) == child.origin_date.isoformat()
        and str(parent_start) == child.business_season_start.isoformat()
        and str(parent_end) == child.business_season_end.isoformat()
    )


__all__ = [
    "EXECUTION_SCHEMA_VERSION",
    "OperationalPeakPersistenceConflictError",
    "OperationalPeakPersistenceIntegrityError",
    "OperationalPeakRerunScopeMismatch",
    "OperationalPeakRunNotFoundError",
    "OperationalPeakRunRepository",
    "OperationalPeakWriteFailure",
    "execution_hash",
    "request_snapshot",
    "validate_persisted_result",
]
