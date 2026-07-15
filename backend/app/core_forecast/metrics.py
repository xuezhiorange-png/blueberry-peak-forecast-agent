from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_EVEN, Decimal, DecimalException

from pydantic import ValidationError

from backend.app.core_forecast.canonical import (
    METRICS_SCHEMA_VERSION,
    compute_daily_curve_hash,
)
from backend.app.core_forecast.schemas import (
    OUTPUT_QUANTUM,
    QUANTILES,
    CompleteCoreForecastMetricsResult,
    CompleteDailyMarketableCurveResult,
    CompleteDailyMarketableCurveRow,
    CoreForecastBlocker,
    CoreForecastBlockerCode,
    QuantileCoreForecastMetrics,
    SingleDayPeakMetric,
    SustainedSevenDayPeakMetric,
)
from backend.app.rolling_backtest.canonical import canonical_json_dumps

_FIXED_6_RE = re.compile(r"^(?:0|[1-9]\d*)\.\d{6}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ROW_QUANTITY_FIELDS = (
    "natural_maturity_supply_kg",
    "opening_mature_inventory_kg",
    "available_mature_quantity_kg",
    "mature_inventory_loss_quantity_kg",
    "harvestable_mature_quantity_kg",
    "effective_harvest_capacity_kg",
    "model_harvested_marketable_quantity_kg",
    "closing_mature_inventory_kg",
    "unharvested_backlog_kg",
    "sorting_retention_rate",
    "postharvest_retention_rate",
    "effective_marketable_quantity_kg",
)


class _MetricsDataError(ValueError):
    def __init__(self, code: CoreForecastBlockerCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _blocked(
    code: CoreForecastBlockerCode,
    message: str,
) -> CompleteCoreForecastMetricsResult:
    return CompleteCoreForecastMetricsResult(
        status="BLOCKED",
        metrics_schema_version=None,
        date_basis=None,
        source_curve_hash=None,
        metrics=(),
        metrics_hash=None,
        blockers=(CoreForecastBlocker(code=code, message=message),),
    )


def _parse_quantity(value: object) -> Decimal:
    if isinstance(value, (float, bool)) or not isinstance(value, str):
        raise _MetricsDataError(
            "DAILY_CURVE_DECIMAL_INVALID",
            "daily curve quantity is not a fixed decimal string",
        )
    if _FIXED_6_RE.fullmatch(value) is None:
        raise _MetricsDataError(
            "DAILY_CURVE_DECIMAL_INVALID",
            "daily curve quantity is not a fixed six-place decimal",
        )
    try:
        parsed = Decimal(value)
    except DecimalException as exc:
        raise _MetricsDataError(
            "DAILY_CURVE_DECIMAL_INVALID",
            "daily curve quantity is not Decimal-compatible",
        ) from exc
    if not parsed.is_finite() or parsed < 0 or (parsed.is_signed() and parsed == 0):
        raise _MetricsDataError(
            "DAILY_CURVE_DECIMAL_INVALID",
            "daily curve quantity must be finite and non-negative",
        )
    return parsed


def _format_quantity(value: Decimal) -> str:
    try:
        formatted = format(value.quantize(OUTPUT_QUANTUM, rounding=ROUND_HALF_EVEN), "f")
    except (DecimalException, OverflowError) as exc:
        raise _MetricsDataError(
            "PEAK_METRIC_INVARIANT_FAILED",
            "metric quantity cannot be quantized",
        ) from exc
    if _FIXED_6_RE.fullmatch(formatted) is None:
        raise _MetricsDataError(
            "PEAK_METRIC_INVARIANT_FAILED",
            "metric quantity is not a fixed six-place decimal",
        )
    return formatted


def _business_key(row: CompleteDailyMarketableCurveRow) -> tuple[date, int, int, int, str]:
    fields = (row.farm_id, row.subfarm_id, row.variety_id, row.destination_factory_id)
    if any(type(value) is not int or value <= 0 for value in fields):
        raise _MetricsDataError(
            "DAILY_CURVE_INCOMPLETE_SERIES",
            "daily curve contains an invalid scope identity",
        )
    if not isinstance(row.date, date) or row.forecast_quantile not in QUANTILES:
        raise _MetricsDataError(
            "DAILY_CURVE_INCOMPLETE_SERIES",
            "daily curve contains an invalid date or quantile",
        )
    return row.date, row.farm_id, row.subfarm_id, row.variety_id, row.forecast_quantile


def _verify_row_hash(row: CompleteDailyMarketableCurveRow) -> None:
    for field_name in _ROW_QUANTITY_FIELDS:
        _parse_quantity(getattr(row, field_name, None))
    if not isinstance(row.row_hash, str) or _SHA256_RE.fullmatch(row.row_hash) is None:
        raise _MetricsDataError(
            "DAILY_CURVE_ROW_HASH_MISMATCH",
            "daily curve row hash is not a lowercase SHA-256",
        )
    try:
        payload = row.model_dump(mode="json", exclude={"row_hash"})
        recomputed = hashlib.sha256(canonical_json_dumps(payload).encode("utf-8")).hexdigest()
    except (TypeError, ValueError, DecimalException) as exc:
        raise _MetricsDataError(
            "DAILY_CURVE_ROW_HASH_MISMATCH",
            "daily curve row hash cannot be recomputed",
        ) from exc
    if recomputed != row.row_hash:
        raise _MetricsDataError(
            "DAILY_CURVE_ROW_HASH_MISMATCH",
            "daily curve row hash does not match its payload",
        )


def _validate_completed_curve(
    daily_curve: CompleteDailyMarketableCurveResult,
) -> tuple[tuple[CompleteDailyMarketableCurveRow, ...], str, tuple[date, ...]]:
    if (
        daily_curve.status != "COMPLETED"
        or not isinstance(daily_curve.rows, tuple)
        or not daily_curve.rows
        or daily_curve.blockers
    ):
        raise _MetricsDataError(
            "DAILY_CURVE_NOT_COMPLETED",
            "daily curve is not a completed unblocked result",
        )
    if (
        not isinstance(daily_curve.curve_hash, str)
        or _SHA256_RE.fullmatch(daily_curve.curve_hash) is None
    ):
        raise _MetricsDataError(
            "DAILY_CURVE_HASH_MISMATCH",
            "daily curve hash is not a lowercase SHA-256",
        )

    seen: set[tuple[date, int, int, int, str]] = set()
    destinations: set[int] = set()
    parsed_rows: list[CompleteDailyMarketableCurveRow] = []
    for row in daily_curve.rows:
        _verify_row_hash(row)
        key = _business_key(row)
        if key in seen:
            raise _MetricsDataError(
                "DAILY_CURVE_DUPLICATE_KEY",
                "daily curve contains a duplicate business key",
            )
        seen.add(key)
        destinations.add(row.destination_factory_id)
        parsed_rows.append(row)

    if len(destinations) != 1:
        raise _MetricsDataError(
            "DAILY_CURVE_INCOMPLETE_SERIES",
            "daily curve must use one destination factory",
        )
    expected_curve_hash = compute_daily_curve_hash(tuple(parsed_rows))
    if expected_curve_hash != daily_curve.curve_hash:
        raise _MetricsDataError(
            "DAILY_CURVE_HASH_MISMATCH",
            "daily curve hash does not match its rows",
        )

    quantile_dates = {
        quantile: {row.date for row in parsed_rows if row.forecast_quantile == quantile}
        for quantile in QUANTILES
    }
    if any(not quantile_dates[quantile] for quantile in QUANTILES):
        raise _MetricsDataError(
            "DAILY_CURVE_INCOMPLETE_SERIES",
            "daily curve is missing a quantile",
        )
    dates = quantile_dates["P50"]
    if any(quantile_dates[quantile] != dates for quantile in QUANTILES[1:]):
        raise _MetricsDataError(
            "DAILY_CURVE_INCOMPLETE_SERIES",
            "quantile date ranges are not identical",
        )
    ordered_dates = tuple(sorted(dates))
    if any(
        current != previous + timedelta(days=1)
        for previous, current in zip(ordered_dates, ordered_dates[1:], strict=False)
    ):
        raise _MetricsDataError(
            "DAILY_CURVE_INCOMPLETE_SERIES",
            "daily curve dates are not strictly consecutive",
        )
    scope_sets = {
        (current_date, quantile): {
            (row.farm_id, row.subfarm_id, row.variety_id)
            for row in parsed_rows
            if row.date == current_date and row.forecast_quantile == quantile
        }
        for current_date in ordered_dates
        for quantile in QUANTILES
    }
    first_scope_set = next(iter(scope_sets.values()))
    if any(scope_set != first_scope_set for scope_set in scope_sets.values()):
        raise _MetricsDataError(
            "DAILY_CURVE_INCOMPLETE_SERIES",
            "daily curve scope sets are not consistent",
        )
    if len(ordered_dates) < 7:
        raise _MetricsDataError(
            "NO_COMPLETE_7DAY_WINDOW",
            "daily curve has no complete seven-day calendar window",
        )
    return tuple(parsed_rows), daily_curve.curve_hash, ordered_dates


def _compute_validated_metrics(
    daily_curve: CompleteDailyMarketableCurveResult,
) -> CompleteCoreForecastMetricsResult:
    rows, source_curve_hash, dates = _validate_completed_curve(daily_curve)
    daily_totals: dict[tuple[date, str], Decimal] = defaultdict(lambda: Decimal("0"))
    for row in rows:
        daily_totals[(row.date, row.forecast_quantile)] += _parse_quantity(
            row.effective_marketable_quantity_kg
        )

    metrics: list[QuantileCoreForecastMetrics] = []
    for quantile in QUANTILES:
        totals = [(current_date, daily_totals[(current_date, quantile)]) for current_date in dates]
        peak_quantity = max(quantity for _, quantity in totals)
        peak_date = min(
            current_date for current_date, quantity in totals if quantity == peak_quantity
        )

        windows: list[tuple[date, Decimal]] = []
        for index in range(len(dates) - 6):
            window_dates = dates[index : index + 7]
            if any(
                current != previous + timedelta(days=1)
                for previous, current in zip(window_dates, window_dates[1:], strict=False)
            ):
                continue
            windows.append(
                (
                    window_dates[0],
                    sum(
                        (daily_totals[(window_date, quantile)] for window_date in window_dates),
                        Decimal("0"),
                    ),
                )
            )
        if not windows:
            raise _MetricsDataError(
                "NO_COMPLETE_7DAY_WINDOW",
                "daily curve has no complete seven-day calendar window",
            )
        best_total = max(total for _, total in windows)
        best_start = min(start for start, total in windows if total == best_total)
        best_end = best_start + timedelta(days=6)
        average = (best_total / Decimal("7")).quantize(
            OUTPUT_QUANTUM,
            rounding=ROUND_HALF_EVEN,
        )

        try:
            metrics.append(
                QuantileCoreForecastMetrics(
                    forecast_quantile=quantile,
                    single_day_peak=SingleDayPeakMetric(
                        date=peak_date,
                        quantity_kg=_format_quantity(peak_quantity),
                        tie_break="EARLIEST_DATE",
                    ),
                    sustained_7day_peak=SustainedSevenDayPeakMetric(
                        start_date=best_start,
                        end_date=best_end,
                        cumulative_quantity_kg=_format_quantity(best_total),
                        daily_average_kg_per_day=_format_quantity(average),
                        window_days=7,
                        metric="ROLLING_CUMULATIVE",
                        date_continuity="STRICT_CALENDAR_DAYS",
                        tie_break="EARLIEST_START_DATE",
                    ),
                    season_cumulative_effective_marketable_kg=_format_quantity(
                        sum((quantity for _, quantity in totals), Decimal("0"))
                    ),
                )
            )
        except (ValidationError, ValueError, TypeError) as exc:
            raise _MetricsDataError(
                "PEAK_METRIC_INVARIANT_FAILED",
                "computed metric does not satisfy its canonical schema",
            ) from exc

    metrics_tuple = tuple(metrics)
    metrics_payload = {
        "schema_version": METRICS_SCHEMA_VERSION,
        "date_basis": "HARVEST_BUSINESS_DATE",
        "source_curve_hash": source_curve_hash,
        "metrics": [item.model_dump(mode="json") for item in metrics_tuple],
    }
    metrics_hash = hashlib.sha256(canonical_json_dumps(metrics_payload).encode("utf-8")).hexdigest()
    return CompleteCoreForecastMetricsResult(
        status="COMPLETED",
        metrics_schema_version=METRICS_SCHEMA_VERSION,
        date_basis="HARVEST_BUSINESS_DATE",
        source_curve_hash=source_curve_hash,
        metrics=metrics_tuple,
        metrics_hash=metrics_hash,
        blockers=(),
    )


def compute_core_forecast_metrics(
    *,
    daily_curve: CompleteDailyMarketableCurveResult,
) -> CompleteCoreForecastMetricsResult:
    """Compute canonical S3 metrics from a completed S2 curve only."""

    try:
        return _compute_validated_metrics(daily_curve)
    except _MetricsDataError as exc:
        return _blocked(exc.code, exc.message)
    except (ValueError, TypeError, DecimalException, OverflowError, ValidationError):
        return _blocked(
            "PEAK_METRIC_INVARIANT_FAILED",
            "metrics projection failed closed",
        )
