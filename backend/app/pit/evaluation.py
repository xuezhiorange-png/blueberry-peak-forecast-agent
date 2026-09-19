"""Deterministic V0.6-S3 forecast/actual evaluation.

This module owns the evaluation contract only.  It never mutates a forecast
snapshot and it never treats an absent actual observation as zero.  The
actual-harvest loader at the bottom of the module is an adapter over the
existing committed import/commit chain; it is deliberately not a second
actual-harvest store.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from enum import StrEnum
from typing import Any, Final, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.actual_harvest_import.commit_models import ActualHarvestCommitManifestModel
from backend.app.actual_harvest_import.enums import (
    ActualHarvestImportBatchStatus,
    ActualHarvestRecordStatus,
)
from backend.app.actual_harvest_import.models import (
    ActualHarvestImportBatchModel,
    ActualHarvestImportRecordModel,
)
from backend.app.pit.canonical import hash_payload
from backend.app.pit.visibility import weather_forecast_visible_at

EVALUATION_POLICY_VERSION: Final[str] = "V0_6_S3_FORECAST_ACTUAL_EVALUATION_V1"
ERROR_SIGN_CONVENTION: Final[str] = "FORECAST_MINUS_ACTUAL"
WAPE_DENOMINATOR_POLICY: Final[str] = "SUM_ABSOLUTE_ACTUAL"
MAPE_ZERO_ACTUAL_POLICY: Final[str] = "EXCLUDED_WITH_COUNT"
DATE_ERROR_UNIT: Final[str] = "CALENDAR_DAYS_SIGNED_FORECAST_MINUS_ACTUAL"
PARTIAL_SEASON_POLICY: Final[str] = "AS_OF_CLIPPED_RANGE_ONLY"
MISSING_DAY_POLICY: Final[str] = "NOT_ZERO_NOT_COMPARABLE"
GDD_EVALUATION_STATUS: Final[str] = "NOT_EVALUATED_DEFINITION_NOT_FROZEN"

EvaluationMode = Literal["FULL_AVAILABLE_RANGE", "AS_OF_DATE"]
MetricStatus = Literal["COMPUTABLE", "NOT_COMPUTABLE", "UNDEFINED_ZERO_DENOMINATOR"]


class EvaluationError(RuntimeError):
    """Base error for fail-closed S3 evaluation."""

    status_code = 400


class EvaluationIntegrityError(EvaluationError):
    status_code = 422


class EvaluationConflictError(EvaluationError):
    status_code = 409


class ActualCoverageStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    EMPTY = "EMPTY"


class ActualDailyStatus(StrEnum):
    CONFIRMED_QUANTITY = "CONFIRMED_QUANTITY"
    CONFIRMED_ZERO = "CONFIRMED_ZERO"
    MISSING = "MISSING"


@dataclass(frozen=True, slots=True)
class ForecastDailyPoint:
    forecast_date: date
    predicted_quantity_kg: Decimal

    def __post_init__(self) -> None:
        if not self.predicted_quantity_kg.is_finite() or self.predicted_quantity_kg < 0:
            raise ValueError("forecast quantity must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class ActualDailyRecord:
    """One source record projected from the committed actual-harvest authority."""

    base_id: str
    target_season: str
    harvest_date: date
    quantity_kg: Decimal
    source: str
    revision_id: str
    source_hash: str
    known_at: datetime
    observed_at: datetime
    recorded_at: datetime
    authority_id: str | None = None
    revision_number: int = 1
    status: ActualDailyStatus = ActualDailyStatus.CONFIRMED_QUANTITY

    def __post_init__(self) -> None:
        if not self.base_id or not self.target_season or not self.revision_id:
            raise ValueError("actual identity fields are required")
        if not self.quantity_kg.is_finite() or self.quantity_kg < 0:
            raise ValueError("actual quantity must be finite and non-negative")
        for value in (self.known_at, self.observed_at, self.recorded_at):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("actual timestamps must be timezone-aware")
        if self.observed_at > self.known_at or self.recorded_at > self.known_at:
            raise ValueError("actual timestamp ordering is invalid")
        if len(self.source_hash) != 64 or any(
            c not in "0123456789abcdef" for c in self.source_hash
        ):
            raise ValueError("source_hash must be a lowercase SHA-256")
        if self.quantity_kg == 0 and self.status == ActualDailyStatus.CONFIRMED_QUANTITY:
            object.__setattr__(self, "status", ActualDailyStatus.CONFIRMED_ZERO)


@dataclass(frozen=True, slots=True)
class RealizedWeatherPoint:
    """A realized observation used only as an evaluation target."""

    base_id: str
    observation_time: datetime
    temperature: Decimal | None
    precipitation: Decimal | None
    known_at: datetime
    observation_id: str
    source_hash: str

    def __post_init__(self) -> None:
        for value in (self.observation_time, self.known_at):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("weather timestamps must be timezone-aware")
        if self.observation_time > self.known_at:
            raise ValueError("realized weather observation is not yet known")


@dataclass(frozen=True, slots=True)
class AlignedDailyRow:
    evaluation_date: date
    predicted_quantity_kg: Decimal
    actual_quantity_kg: Decimal | None
    actual_status: ActualDailyStatus
    actual_revision_id: str | None
    actual_source_hash: str | None
    error_kg: Decimal | None
    absolute_error_kg: Decimal | None
    evaluation_as_of: date | None

    def payload(self) -> dict[str, Any]:
        return {
            "date": self.evaluation_date,
            "predicted_quantity_kg": self.predicted_quantity_kg,
            "actual_quantity_kg": self.actual_quantity_kg,
            "actual_status": self.actual_status.value,
            "actual_revision_id": self.actual_revision_id,
            "actual_source_hash": self.actual_source_hash,
            "error_kg": self.error_kg,
            "absolute_error_kg": self.absolute_error_kg,
            "evaluation_as_of": self.evaluation_as_of,
        }


@dataclass(frozen=True, slots=True)
class EvaluationComputation:
    evaluation_id: str
    evaluation_identity_hash: str
    evaluation_payload_hash: str
    evaluation_result_hash: str
    forecast_run_id: str
    base_id: str
    target_season: str
    evaluation_mode: EvaluationMode
    as_of_date: date | None
    evaluation_created_at: datetime
    forecast_input_hash: str
    forecast_result_hash: str
    actual_authority_ids: tuple[str, ...]
    actual_authority_hashes: tuple[str, ...]
    realized_weather_authority_ids: tuple[str, ...]
    realized_weather_authority_hashes: tuple[str, ...]
    evaluated_start_date: date
    evaluated_end_date: date
    actual_coverage_status: ActualCoverageStatus
    season_total_metrics: dict[str, Any]
    daily_metrics: dict[str, Any]
    single_day_peak_metrics: dict[str, Any]
    rolling_7day_peak_metrics: dict[str, Any]
    weather_metrics: dict[str, Any]
    warnings: tuple[str, ...]
    rows: tuple[AlignedDailyRow, ...]

    def identity_payload(self) -> dict[str, Any]:
        return {
            "policy_version": EVALUATION_POLICY_VERSION,
            "error_sign_convention": ERROR_SIGN_CONVENTION,
            "wape_denominator_policy": WAPE_DENOMINATOR_POLICY,
            "mape_zero_actual_policy": MAPE_ZERO_ACTUAL_POLICY,
            "date_error_unit": DATE_ERROR_UNIT,
            "partial_season_policy": PARTIAL_SEASON_POLICY,
            "missing_day_policy": MISSING_DAY_POLICY,
            "forecast_run_id": self.forecast_run_id,
            "forecast_input_hash": self.forecast_input_hash,
            "forecast_result_hash": self.forecast_result_hash,
            "base_id": self.base_id,
            "target_season": self.target_season,
            "evaluation_mode": self.evaluation_mode,
            "as_of_date": self.as_of_date,
            "actual_authority_ids": list(self.actual_authority_ids),
            "actual_authority_hashes": list(self.actual_authority_hashes),
            "realized_weather_authority_ids": list(self.realized_weather_authority_ids),
            "realized_weather_authority_hashes": list(self.realized_weather_authority_hashes),
            "evaluated_start_date": self.evaluated_start_date,
            "evaluated_end_date": self.evaluated_end_date,
        }

    def result_payload(self) -> dict[str, Any]:
        return {
            "actual_coverage_status": self.actual_coverage_status.value,
            "season_total_metrics": self.season_total_metrics,
            "daily_metrics": self.daily_metrics,
            "single_day_peak_metrics": self.single_day_peak_metrics,
            "rolling_7day_peak_metrics": self.rolling_7day_peak_metrics,
            "weather_metrics": self.weather_metrics,
            "warnings": list(self.warnings),
            "aligned_daily_rows": [row.payload() for row in self.rows],
        }

    def payload(self) -> dict[str, Any]:
        return {"identity": self.identity_payload(), "result": self.result_payload()}


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)


def _metric(
    value: Decimal | None,
    *,
    status: MetricStatus = "COMPUTABLE",
    comparable_row_count: int = 0,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "status": status,
        "value": None if value is None else _quantize(value),
        "comparable_row_count": comparable_row_count,
        **extra,
    }


def _date_range(start: date, end: date) -> list[date]:
    if end < start:
        raise EvaluationIntegrityError("EVALUATION_WINDOW_INVALID")
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def _require_aware(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise EvaluationIntegrityError(f"{field.upper()}_MUST_BE_TIMEZONE_AWARE")
    return value.astimezone(UTC)


def _select_actual_revisions(
    records: Iterable[ActualDailyRecord],
    *,
    base_id: str,
    target_season: str,
    evaluation_created_at: datetime,
    start: date,
    end: date,
) -> dict[date, ActualDailyRecord]:
    candidates: dict[tuple[date, str], list[ActualDailyRecord]] = defaultdict(list)
    for record in records:
        if record.base_id != base_id or record.target_season != target_season:
            continue
        if not start <= record.harvest_date <= end:
            continue
        if record.known_at.astimezone(UTC) > evaluation_created_at:
            continue
        candidates[(record.harvest_date, record.revision_id.split("#", 1)[0])].append(record)

    winners: dict[date, list[ActualDailyRecord]] = defaultdict(list)
    for (harvest_date, _logical_id), values in candidates.items():
        if len({item.revision_id for item in values}) != len(values):
            raise EvaluationIntegrityError("DUPLICATE_ACTUAL_RECORD")
        ordered = sorted(
            values,
            key=lambda item: (
                item.revision_number,
                item.known_at.astimezone(UTC),
                item.revision_id,
            ),
            reverse=True,
        )
        top = ordered[0]
        if any(
            (item.revision_number, item.known_at.astimezone(UTC))
            == (top.revision_number, top.known_at.astimezone(UTC))
            and item.revision_id != top.revision_id
            for item in ordered[1:]
        ):
            raise EvaluationIntegrityError("DUPLICATE_ACTUAL_REVISION_WINNER")
        if top.status != ActualDailyStatus.MISSING:
            winners[harvest_date].append(top)

    daily: dict[date, ActualDailyRecord] = {}
    for harvest_date, values in winners.items():
        if not values:
            continue
        # Multiple logical harvest records on one date are valid and must be
        # summed.  They remain individually represented by the authority hash
        # set in the evaluation identity.
        quantity = sum((item.quantity_kg for item in values), Decimal("0"))
        first = sorted(values, key=lambda item: item.revision_id)[0]
        source_hash = hash_payload(
            {
                "date": harvest_date,
                "records": [
                    {
                        "revision_id": item.revision_id,
                        "quantity_kg": item.quantity_kg,
                        "source_hash": item.source_hash,
                    }
                    for item in sorted(values, key=lambda item: item.revision_id)
                ],
            }
        )
        daily[harvest_date] = ActualDailyRecord(
            base_id=base_id,
            target_season=target_season,
            harvest_date=harvest_date,
            quantity_kg=quantity,
            source=first.source,
            revision_id="+".join(sorted(item.revision_id for item in values)),
            source_hash=source_hash,
            known_at=max(item.known_at for item in values),
            observed_at=max(item.observed_at for item in values),
            recorded_at=max(item.recorded_at for item in values),
            authority_id=first.authority_id,
            revision_number=max(item.revision_number for item in values),
            status=(
                ActualDailyStatus.CONFIRMED_ZERO
                if quantity == 0
                else ActualDailyStatus.CONFIRMED_QUANTITY
            ),
        )
    return daily


def _metric_rows(rows: Sequence[AlignedDailyRow]) -> list[AlignedDailyRow]:
    return [row for row in rows if row.actual_quantity_kg is not None]


def _mean(values: Iterable[Decimal]) -> Decimal | None:
    materialized = list(values)
    return (
        None if not materialized else sum(materialized, Decimal("0")) / Decimal(len(materialized))
    )


def _season_metrics(rows: Sequence[AlignedDailyRow]) -> dict[str, Any]:
    comparable = _metric_rows(rows)
    if len(comparable) != len(rows) or not comparable:
        return {
            name: _metric(None, status="NOT_COMPUTABLE", comparable_row_count=len(comparable))
            for name in ("mae_kg", "wape", "bias_kg", "mape")
        }
    predicted = sum((row.predicted_quantity_kg for row in comparable), Decimal("0"))
    actual = sum((row.actual_quantity_kg or Decimal("0") for row in comparable), Decimal("0"))
    error = predicted - actual
    abs_error = sum((abs(row.error_kg or Decimal("0")) for row in comparable), Decimal("0"))
    nonzero = [row for row in comparable if row.actual_quantity_kg != 0]
    mape = (
        _mean(
            abs(row.error_kg or Decimal("0")) / abs(row.actual_quantity_kg or Decimal("1"))
            for row in nonzero
        )
        if nonzero
        else None
    )
    result = {
        "mae_kg": _metric(
            abs_error / Decimal(len(comparable)), comparable_row_count=len(comparable)
        ),
        "wape": (
            _metric(abs_error / abs(actual), comparable_row_count=len(comparable))
            if actual != 0
            else _metric(
                None, status="UNDEFINED_ZERO_DENOMINATOR", comparable_row_count=len(comparable)
            )
        ),
        "bias_kg": _metric(error / Decimal(len(comparable)), comparable_row_count=len(comparable)),
        "mape": (
            _metric(
                mape,
                comparable_row_count=len(nonzero),
                zero_actual_excluded_count=len(comparable) - len(nonzero),
            )
            if mape is not None
            else _metric(
                None,
                status="UNDEFINED_ZERO_DENOMINATOR",
                comparable_row_count=0,
                zero_actual_excluded_count=len(comparable),
            )
        ),
    }
    result["predicted_total_kg"] = _metric(predicted, comparable_row_count=len(comparable))
    result["actual_total_kg"] = _metric(actual, comparable_row_count=len(comparable))
    return result


def _daily_metrics(rows: Sequence[AlignedDailyRow]) -> dict[str, Any]:
    comparable = _metric_rows(rows)
    if not comparable:
        return {
            name: _metric(None, status="NOT_COMPUTABLE", comparable_row_count=0)
            for name in ("mae_kg", "wape", "bias_kg", "mape")
        }
    abs_errors = [abs(row.error_kg or Decimal("0")) for row in comparable]
    errors = [row.error_kg or Decimal("0") for row in comparable]
    actual_abs = sum(
        (abs(row.actual_quantity_kg or Decimal("0")) for row in comparable), Decimal("0")
    )
    nonzero = [row for row in comparable if row.actual_quantity_kg != 0]
    mape = _mean(
        abs(row.error_kg or Decimal("0")) / abs(row.actual_quantity_kg or Decimal("1"))
        for row in nonzero
    )
    return {
        "mae_kg": _metric(_mean(abs_errors), comparable_row_count=len(comparable)),
        "wape": (
            _metric(
                sum(abs_errors, Decimal("0")) / actual_abs, comparable_row_count=len(comparable)
            )
            if actual_abs != 0
            else _metric(
                None, status="UNDEFINED_ZERO_DENOMINATOR", comparable_row_count=len(comparable)
            )
        ),
        "bias_kg": _metric(_mean(errors), comparable_row_count=len(comparable)),
        "mape": (
            _metric(
                mape,
                comparable_row_count=len(nonzero),
                zero_actual_excluded_count=len(comparable) - len(nonzero),
            )
            if mape is not None
            else _metric(
                None,
                status="UNDEFINED_ZERO_DENOMINATOR",
                comparable_row_count=0,
                zero_actual_excluded_count=len(comparable),
            )
        ),
    }


def _peak_metrics(rows: Sequence[AlignedDailyRow]) -> dict[str, Any]:
    comparable = _metric_rows(rows)
    if len(comparable) != len(rows) or not comparable:
        return {"status": "NOT_COMPUTABLE", "reason": MISSING_DAY_POLICY}
    forecast_peak = min(
        comparable, key=lambda row: (-row.predicted_quantity_kg, row.evaluation_date)
    )
    actual_peak = min(
        comparable, key=lambda row: (-(row.actual_quantity_kg or Decimal("0")), row.evaluation_date)
    )
    quantity_error = forecast_peak.predicted_quantity_kg - (
        actual_peak.actual_quantity_kg or Decimal("0")
    )
    date_error = (forecast_peak.evaluation_date - actual_peak.evaluation_date).days
    return {
        "status": "COMPUTABLE",
        "forecast_peak_date": forecast_peak.evaluation_date,
        "forecast_peak_quantity_kg": forecast_peak.predicted_quantity_kg,
        "actual_peak_date": actual_peak.evaluation_date,
        "actual_peak_quantity_kg": actual_peak.actual_quantity_kg,
        "peak_quantity_error_kg": _quantize(quantity_error),
        "peak_absolute_quantity_error_kg": _quantize(abs(quantity_error)),
        "peak_date_error_days": date_error,
        "peak_absolute_date_error_days": abs(date_error),
    }


def _rolling_windows(rows: Sequence[AlignedDailyRow]) -> list[tuple[date, date, Decimal]]:
    if len(rows) < 7:
        return []
    windows: list[tuple[date, date, Decimal]] = []
    for index in range(len(rows) - 6):
        window = rows[index : index + 7]
        if any(
            current.evaluation_date != previous.evaluation_date + timedelta(days=1)
            for previous, current in zip(window, window[1:], strict=False)
        ):
            continue
        if any(row.actual_quantity_kg is None for row in window):
            continue
        total = sum((row.actual_quantity_kg or Decimal("0") for row in window), Decimal("0"))
        windows.append((window[0].evaluation_date, window[-1].evaluation_date, total))
    return windows


def _forecast_rolling_windows(rows: Sequence[AlignedDailyRow]) -> list[tuple[date, date, Decimal]]:
    windows: list[tuple[date, date, Decimal]] = []
    if len(rows) < 7:
        return windows
    for index in range(len(rows) - 6):
        window = rows[index : index + 7]
        if any(
            current.evaluation_date != previous.evaluation_date + timedelta(days=1)
            for previous, current in zip(window, window[1:], strict=False)
        ):
            continue
        windows.append(
            (
                window[0].evaluation_date,
                window[-1].evaluation_date,
                sum((row.predicted_quantity_kg for row in window), Decimal("0")),
            )
        )
    return windows


def _rolling_metrics(rows: Sequence[AlignedDailyRow]) -> dict[str, Any]:
    forecast_windows = _forecast_rolling_windows(rows)
    actual_windows = _rolling_windows(rows)
    if not forecast_windows or not actual_windows:
        return {"status": "NOT_COMPUTABLE", "reason": "LESS_THAN_7_VALID_CONSECUTIVE_DAYS"}
    forecast = min(forecast_windows, key=lambda item: (-item[2], item[0]))
    actual = min(actual_windows, key=lambda item: (-item[2], item[0]))
    quantity_error = forecast[2] - actual[2]
    start_error = (forecast[0] - actual[0]).days
    return {
        "status": "COMPUTABLE",
        "forecast_7day_start_date": forecast[0],
        "forecast_7day_end_date": forecast[1],
        "forecast_7day_cumulative_kg": _quantize(forecast[2]),
        "actual_7day_start_date": actual[0],
        "actual_7day_end_date": actual[1],
        "actual_7day_cumulative_kg": _quantize(actual[2]),
        "rolling_7day_quantity_error_kg": _quantize(quantity_error),
        "rolling_7day_absolute_quantity_error_kg": _quantize(abs(quantity_error)),
        "rolling_7day_start_date_error_days": start_error,
        "rolling_7day_absolute_start_date_error_days": abs(start_error),
    }


def align_forecast_actual(
    *,
    base_id: str,
    target_season: str,
    forecast_start_date: date,
    forecast_end_date: date,
    forecast_rows: Sequence[ForecastDailyPoint],
    actual_records: Sequence[ActualDailyRecord],
    evaluation_mode: EvaluationMode,
    as_of_date: date | None,
    evaluation_created_at: datetime,
) -> tuple[tuple[AlignedDailyRow, ...], ActualCoverageStatus, tuple[str, ...]]:
    evaluation_created_at = _require_aware(evaluation_created_at, "evaluation_created_at")
    if evaluation_mode == "AS_OF_DATE" and as_of_date is None:
        raise EvaluationIntegrityError("AS_OF_DATE_REQUIRED")
    if evaluation_mode == "FULL_AVAILABLE_RANGE" and as_of_date is not None:
        raise EvaluationIntegrityError("FULL_RANGE_MUST_NOT_HAVE_AS_OF_DATE")
    end = min(forecast_end_date, as_of_date) if as_of_date is not None else forecast_end_date
    if end < forecast_start_date:
        raise EvaluationIntegrityError("NO_EVALUATION_DATES_AVAILABLE")
    expected = _date_range(forecast_start_date, end)
    by_date = {row.forecast_date: row for row in forecast_rows}
    if len(by_date) != len(forecast_rows) or any(day not in by_date for day in expected):
        raise EvaluationIntegrityError("FORECAST_DAILY_SERIES_NOT_COMPLETE")
    selected = _select_actual_revisions(
        actual_records,
        base_id=base_id,
        target_season=target_season,
        evaluation_created_at=evaluation_created_at,
        start=forecast_start_date,
        end=end,
    )
    rows: list[AlignedDailyRow] = []
    for day in expected:
        actual = selected.get(day)
        if actual is None:
            rows.append(
                AlignedDailyRow(
                    evaluation_date=day,
                    predicted_quantity_kg=by_date[day].predicted_quantity_kg,
                    actual_quantity_kg=None,
                    actual_status=ActualDailyStatus.MISSING,
                    actual_revision_id=None,
                    actual_source_hash=None,
                    error_kg=None,
                    absolute_error_kg=None,
                    evaluation_as_of=as_of_date,
                )
            )
            continue
        error = by_date[day].predicted_quantity_kg - actual.quantity_kg
        rows.append(
            AlignedDailyRow(
                evaluation_date=day,
                predicted_quantity_kg=by_date[day].predicted_quantity_kg,
                actual_quantity_kg=actual.quantity_kg,
                actual_status=actual.status,
                actual_revision_id=actual.revision_id,
                actual_source_hash=actual.source_hash,
                error_kg=_quantize(error),
                absolute_error_kg=_quantize(abs(error)),
                evaluation_as_of=as_of_date,
            )
        )
    comparable_count = sum(row.actual_quantity_kg is not None for row in rows)
    coverage = (
        ActualCoverageStatus.COMPLETE
        if comparable_count == len(rows)
        else ActualCoverageStatus.PARTIAL
        if comparable_count
        else ActualCoverageStatus.EMPTY
    )
    warnings = () if coverage == ActualCoverageStatus.COMPLETE else ("ACTUAL_COVERAGE_INCOMPLETE",)
    return tuple(rows), coverage, warnings


def _weather_metric(
    values: Sequence[Decimal], *, absolute: bool, bias: bool = False
) -> dict[str, Any]:
    if not values:
        return {"status": "NOT_COMPUTABLE", "value": None, "comparable_row_count": 0}
    selected = [abs(value) for value in values] if absolute else list(values)
    return {
        "status": "COMPUTABLE",
        "value": _quantize(sum(selected, Decimal("0")) / Decimal(len(selected))),
        "comparable_row_count": len(values),
        "metric": "BIAS" if bias else "MAE" if absolute else "ERROR",
    }


def evaluate_weather_forecast(
    *,
    forecast_snapshots: Sequence[Any],
    realized_observations: Sequence[RealizedWeatherPoint],
    forecast_created_at: datetime,
    evaluation_created_at: datetime,
    base_id: str,
    as_of_date: date | None = None,
) -> tuple[dict[str, Any], tuple[str, ...], tuple[str, ...]]:
    """Compare only persisted as-issued snapshots with exact-time realized data."""

    forecast_cutoff = _require_aware(forecast_created_at, "forecast_created_at")
    evaluation_cutoff = _require_aware(evaluation_created_at, "evaluation_created_at")
    realized_by_time = {
        observation.observation_time.astimezone(UTC): observation
        for observation in realized_observations
        if observation.base_id == base_id
        and observation.known_at.astimezone(UTC) <= evaluation_cutoff
        and (as_of_date is None or observation.observation_time.date() <= as_of_date)
    }
    output: dict[str, Any] = {}
    ids: list[str] = []
    hashes: list[str] = []
    for horizon in (24, 72, 168, 360):
        snapshots = [
            snapshot
            for snapshot in forecast_snapshots
            if snapshot.base_id == base_id
            and snapshot.forecast_horizon_hours == horizon
            and weather_forecast_visible_at(snapshot, forecast_cutoff)
        ]
        rows = []
        for snapshot in sorted(snapshots, key=lambda item: item.valid_at):
            ids.append(str(snapshot.weather_snapshot_id))
            hashes.append(str(snapshot.payload_hash))
            realized = realized_by_time.get(snapshot.valid_at.astimezone(UTC))
            if realized is None:
                continue
            if snapshot.temperature_mean is not None and realized.temperature is not None:
                rows.append((snapshot.temperature_mean - realized.temperature, "temperature"))
            if snapshot.precipitation is not None and realized.precipitation is not None:
                rows.append((snapshot.precipitation - realized.precipitation, "precipitation"))
        temperatures = [value for value, field in rows if field == "temperature"]
        precipitation = [value for value, field in rows if field == "precipitation"]
        output[f"D{horizon // 24}"] = {
            "forecast_horizon_hours": horizon,
            "temperature_mae": _weather_metric(temperatures, absolute=True),
            "temperature_bias": _weather_metric(temperatures, absolute=False, bias=True),
            "precipitation_error": _weather_metric(precipitation, absolute=False),
            "precipitation_mae": _weather_metric(precipitation, absolute=True),
            "gdd_evaluation_status": GDD_EVALUATION_STATUS,
        }
    return output, tuple(sorted(set(ids))), tuple(sorted(set(hashes)))


def compute_forecast_actual_evaluation(
    *,
    forecast_snapshot: Any,
    forecast_daily_rows: Sequence[Any],
    actual_records: Sequence[ActualDailyRecord],
    evaluation_mode: EvaluationMode,
    as_of_date: date | None,
    evaluation_created_at: datetime,
    realized_weather_observations: Sequence[RealizedWeatherPoint] = (),
    forecast_weather_snapshots: Sequence[Any] = (),
) -> EvaluationComputation:
    """Build an immutable evaluation authority from a saved forecast snapshot."""

    if evaluation_created_at.tzinfo is None or evaluation_created_at.utcoffset() is None:
        raise EvaluationIntegrityError("EVALUATION_CREATED_AT_MUST_BE_TIMEZONE_AWARE")
    forecast_rows = tuple(
        ForecastDailyPoint(
            forecast_date=row.forecast_date,
            predicted_quantity_kg=Decimal(str(row.predicted_quantity_kg)),
        )
        for row in forecast_daily_rows
    )
    rows, coverage, alignment_warnings = align_forecast_actual(
        base_id=forecast_snapshot.base_id,
        target_season=forecast_snapshot.target_season,
        forecast_start_date=forecast_snapshot.forecast_start_date,
        forecast_end_date=forecast_snapshot.forecast_end_date,
        forecast_rows=forecast_rows,
        actual_records=actual_records,
        evaluation_mode=evaluation_mode,
        as_of_date=as_of_date,
        evaluation_created_at=evaluation_created_at,
    )
    weather_metrics, weather_ids, weather_hashes = evaluate_weather_forecast(
        forecast_snapshots=forecast_weather_snapshots,
        realized_observations=realized_weather_observations,
        forecast_created_at=forecast_snapshot.forecast_created_at,
        evaluation_created_at=evaluation_created_at,
        base_id=forecast_snapshot.base_id,
        as_of_date=as_of_date,
    )
    evaluation_end = (
        min(forecast_snapshot.forecast_end_date, as_of_date)
        if as_of_date is not None
        else forecast_snapshot.forecast_end_date
    )
    eligible_actual_records = tuple(
        record
        for record in actual_records
        if record.base_id == forecast_snapshot.base_id
        and record.target_season == forecast_snapshot.target_season
        and record.harvest_date >= forecast_snapshot.forecast_start_date
        and record.harvest_date <= evaluation_end
        and record.known_at.astimezone(UTC) <= evaluation_created_at.astimezone(UTC)
    )
    authority_ids = tuple(
        sorted({record.authority_id for record in eligible_actual_records if record.authority_id})
    )
    authority_hashes = tuple(sorted({record.source_hash for record in eligible_actual_records}))
    provisional = EvaluationComputation(
        evaluation_id="pending",
        evaluation_identity_hash="pending",
        evaluation_payload_hash="pending",
        evaluation_result_hash="pending",
        forecast_run_id=forecast_snapshot.forecast_run_id,
        base_id=forecast_snapshot.base_id,
        target_season=forecast_snapshot.target_season,
        evaluation_mode=evaluation_mode,
        as_of_date=as_of_date,
        evaluation_created_at=evaluation_created_at.astimezone(UTC),
        forecast_input_hash=forecast_snapshot.input_snapshot_hash,
        forecast_result_hash=forecast_snapshot.result_hash,
        actual_authority_ids=authority_ids,
        actual_authority_hashes=authority_hashes,
        realized_weather_authority_ids=weather_ids,
        realized_weather_authority_hashes=weather_hashes,
        evaluated_start_date=rows[0].evaluation_date,
        evaluated_end_date=rows[-1].evaluation_date,
        actual_coverage_status=coverage,
        season_total_metrics=_season_metrics(rows),
        daily_metrics=_daily_metrics(rows),
        single_day_peak_metrics=_peak_metrics(rows),
        rolling_7day_peak_metrics=_rolling_metrics(rows),
        weather_metrics=weather_metrics,
        warnings=tuple(sorted(set(alignment_warnings))),
        rows=rows,
    )
    identity_hash = hash_payload(provisional.identity_payload())
    result_hash = hash_payload(provisional.result_payload())
    payload_hash = hash_payload(
        {"identity": provisional.identity_payload(), "result": provisional.result_payload()}
    )
    return replace(
        provisional,
        evaluation_id=f"evaluation_{identity_hash}",
        evaluation_identity_hash=identity_hash,
        evaluation_payload_hash=payload_hash,
        evaluation_result_hash=result_hash,
    )


# Stable descriptive alias for callers that do not need to know the internal
# computation naming.
evaluate_forecast_actual = compute_forecast_actual_evaluation


async def load_committed_actual_harvest_records(
    session: AsyncSession,
    *,
    base_id: str,
    target_season: str,
    farm_to_base: Mapping[str, str],
    evaluation_created_at: datetime,
) -> tuple[ActualDailyRecord, ...]:
    """Read committed actual harvest through the existing authority chain."""

    cutoff = _require_aware(evaluation_created_at, "evaluation_created_at")
    rows = list(
        (
            await session.execute(
                select(
                    ActualHarvestImportRecordModel,
                    ActualHarvestImportBatchModel,
                    ActualHarvestCommitManifestModel,
                )
                .join(
                    ActualHarvestImportBatchModel,
                    ActualHarvestImportRecordModel.batch_id == ActualHarvestImportBatchModel.id,
                )
                .join(
                    ActualHarvestCommitManifestModel,
                    ActualHarvestCommitManifestModel.batch_id == ActualHarvestImportBatchModel.id,
                )
                .where(
                    ActualHarvestImportBatchModel.status
                    == ActualHarvestImportBatchStatus.COMMITTED.value,
                    ActualHarvestImportRecordModel.season_code == target_season,
                    ActualHarvestImportRecordModel.import_received_at <= cutoff,
                )
                .order_by(
                    ActualHarvestImportRecordModel.external_logical_record_id,
                    ActualHarvestImportRecordModel.revision_number,
                    ActualHarvestImportRecordModel.external_revision_id,
                )
            )
        ).all()
    )
    records: list[ActualDailyRecord] = []
    for record, batch, manifest in rows:
        mapped_base = farm_to_base.get(record.farm_code)
        if mapped_base is None:
            raise EvaluationIntegrityError("ACTUAL_BASE_MAPPING_UNRESOLVED")
        if mapped_base != base_id:
            continue
        if record.record_status == ActualHarvestRecordStatus.VOID.value:
            status = ActualDailyStatus.MISSING
        else:
            status = (
                ActualDailyStatus.CONFIRMED_ZERO
                if Decimal(str(record.actual_harvest_quantity_kg)) == 0
                else ActualDailyStatus.CONFIRMED_QUANTITY
            )
        source_hash = batch.source_file_hash_or_null or batch.raw_payload_hash
        records.append(
            ActualDailyRecord(
                base_id=base_id,
                target_season=target_season,
                harvest_date=record.harvest_business_date,
                quantity_kg=Decimal(str(record.actual_harvest_quantity_kg)),
                source=batch.source_system,
                revision_id=record.external_logical_record_id + "#" + record.external_revision_id,
                source_hash=source_hash,
                known_at=record.import_received_at,
                observed_at=record.source_recorded_at or record.import_received_at,
                recorded_at=record.ingested_at,
                authority_id=f"actual_harvest_commit:{manifest.commit_manifest_hash}",
                revision_number=record.revision_number,
                status=status,
            )
        )
    return tuple(records)


__all__ = [
    "ActualCoverageStatus",
    "ActualDailyRecord",
    "ActualDailyStatus",
    "AlignedDailyRow",
    "DATE_ERROR_UNIT",
    "EVALUATION_POLICY_VERSION",
    "EvaluationComputation",
    "EvaluationConflictError",
    "EvaluationError",
    "EvaluationIntegrityError",
    "ForecastDailyPoint",
    "GDD_EVALUATION_STATUS",
    "MAPE_ZERO_ACTUAL_POLICY",
    "MISSING_DAY_POLICY",
    "PARTIAL_SEASON_POLICY",
    "RealizedWeatherPoint",
    "compute_forecast_actual_evaluation",
    "evaluate_forecast_actual",
    "align_forecast_actual",
    "evaluate_weather_forecast",
    "load_committed_actual_harvest_records",
]
