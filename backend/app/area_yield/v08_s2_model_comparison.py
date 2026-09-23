"""Deterministic helpers for the V0.8-S2 frozen-history OOT comparison.

The official Model A mathematics and daily curve live in the existing V0.7
validation module. This module only validates S1 quantity semantics, builds
same-row prediction sets, and aggregates the requested comparison metrics.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from backend.app.area_yield.data import digest
from backend.app.area_yield.formal_multi_season_validation import (
    AREA_TYPE,
    BusinessBoundary,
    predict_daily_curve,
)

KNOWN_QUANTITY_STATUSES = frozenset({"KNOWN_MAPPED_SUBTOTAL", "CONFIRMED_ZERO"})
UNKNOWN_QUANTITY_STATUS = "UNKNOWN"
STRICT_HISTORICAL_AREA_STATUS = "BUSINESS_CONFIRMED_SOURCE_LABEL_BOUND"
AREA_SEMANTICS_REFERENCE_ONLY = "REFERENCE_AREA_ONLY"


class ModelComparisonContractError(ValueError):
    """Raised when an input cannot be used under the frozen S2 contract."""


def decimal_value(value: Any, *, field: str) -> Decimal:
    """Parse a finite decimal and give the failing field a stable error code."""

    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ModelComparisonContractError(f"INVALID_DECIMAL:{field}") from exc
    if not result.is_finite():
        raise ModelComparisonContractError(f"NONFINITE_DECIMAL:{field}")
    return result


def sum_known_mapped_subtotals(
    rows: Iterable[Mapping[str, Any]], *, included_seasons: set[str]
) -> dict[tuple[str, str], Decimal]:
    """Sum only S1 known mapped subtotals and authorized confirmed zeros.

    UNKNOWN rows must have no numeric value. They are never materialized as
    zero and never contribute to training aggregates.
    """

    totals: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    for row in rows:
        season = str(row.get("season", ""))
        if season not in included_seasons:
            continue
        base_id = str(row.get("base_id", ""))
        status = str(row.get("quantity_status", ""))
        raw_quantity = row.get("mapped_observed_subtotal_kg")
        if not base_id:
            raise ModelComparisonContractError("CANONICAL_ROW_BASE_ID_MISSING")
        if status == UNKNOWN_QUANTITY_STATUS:
            if raw_quantity not in (None, ""):
                raise ModelComparisonContractError("UNKNOWN_QUANTITY_MUST_REMAIN_NULL")
            continue
        if status not in KNOWN_QUANTITY_STATUSES:
            raise ModelComparisonContractError(f"UNAUTHORIZED_QUANTITY_STATUS:{status}")
        quantity = decimal_value(raw_quantity, field="mapped_observed_subtotal_kg")
        if quantity < 0:
            raise ModelComparisonContractError("NEGATIVE_CANONICAL_QUANTITY")
        if status == "CONFIRMED_ZERO" and quantity != 0:
            raise ModelComparisonContractError("CONFIRMED_ZERO_HAS_NONZERO_QUANTITY")
        totals[(base_id, season)] += quantity
    return dict(totals)


def strict_historical_area_authorized(row: Mapping[str, Any]) -> bool:
    """Return true only for the frozen identity-bound actual-area authority."""

    if row.get("historical_actual_productive_area_status") != STRICT_HISTORICAL_AREA_STATUS:
        return False
    raw_area = row.get("historical_actual_productive_area_mu")
    if raw_area in (None, ""):
        return False
    area = decimal_value(raw_area, field="historical_actual_productive_area_mu")
    return area > 0


def common_base_scope(
    *,
    v07_yield_by_base: Mapping[str, Decimal],
    canonical_history_by_base: Mapping[str, Decimal],
    registry_base_ids: set[str],
) -> list[str]:
    """Freeze comparison scope using prior-history authority only."""

    return sorted(set(v07_yield_by_base) & set(canonical_history_by_base) & registry_base_ids)


def seal_daily_predictions(
    *,
    fold_id: str,
    model_id: str,
    season: str,
    prior_season: str,
    base_scope: Sequence[str],
    yield_by_base: Mapping[str, Decimal],
    registry_by_id: Mapping[str, Mapping[str, Any]],
    temporal_model: Mapping[str, Any],
    boundary: BusinessBoundary,
) -> tuple[list[dict[str, str]], dict[str, dict[str, str]], str]:
    """Seal daily rows without receiving or loading any OOT actual labels."""

    rows: list[dict[str, str]] = []
    season_summaries: dict[str, dict[str, str]] = {}
    for base_id in sorted(base_scope):
        if base_id not in yield_by_base or base_id not in registry_by_id:
            raise ModelComparisonContractError("PREDICTION_SCOPE_HISTORY_OR_REGISTRY_MISSING")
        registry_row = registry_by_id[base_id]
        area = decimal_value(registry_row["productive_area_mu"], field="reference_area_mu")
        yield_value = yield_by_base[base_id]
        if area <= 0 or yield_value <= 0:
            raise ModelComparisonContractError("NONPOSITIVE_REFERENCE_MODEL_INPUT")
        total = (area * yield_value).quantize(Decimal("0.000001"))
        curve = predict_daily_curve(
            season=season,
            reference_area_mu=area,
            predicted_total_kg=total,
            temporal_model=temporal_model,
            boundary=boundary,
        )
        normalized = [
            {
                "fold_id": fold_id,
                "model_id": model_id,
                "base_id": base_id,
                "base_name": str(registry_row["canonical_base_name"]),
                "season": season,
                "date": str(curve_row["date"]),
                "predicted_quantity_kg": str(curve_row["predicted_quantity_kg"]),
                "predicted_season_total_kg": format(total, "f"),
                "prior_season": prior_season,
                "prior_yield_kg_per_mu": format(yield_value, "f"),
                "area_mu": format(area, "f"),
                "area_semantics": AREA_SEMANTICS_REFERENCE_ONLY,
                "area_type": AREA_TYPE,
            }
            for curve_row in curve
        ]
        rows.extend(normalized)
        season_summaries[base_id] = {
            "predicted_season_total_kg": format(total, "f"),
            "predicted_daily_row_count": str(len(curve)),
        }
    rows.sort(key=lambda row: (row["fold_id"], row["season"], row["base_id"], row["date"]))
    return rows, season_summaries, digest(rows)


def daily_metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, str | int]:
    """Compute pooled known-support daily metrics; unknown rows remain excluded."""

    scored: list[tuple[Decimal, Decimal]] = []
    unknown_count = 0
    for row in rows:
        status = str(row.get("actual_status", ""))
        actual_raw = row.get("actual_quantity_kg")
        if status == UNKNOWN_QUANTITY_STATUS:
            if actual_raw not in (None, ""):
                raise ModelComparisonContractError("UNKNOWN_ACTUAL_MUST_REMAIN_NULL")
            unknown_count += 1
            continue
        if status not in KNOWN_QUANTITY_STATUSES:
            raise ModelComparisonContractError(f"UNAUTHORIZED_ACTUAL_STATUS:{status}")
        actual = decimal_value(actual_raw, field="actual_quantity_kg")
        predicted = decimal_value(row["predicted_quantity_kg"], field="predicted_quantity_kg")
        if actual < 0 or predicted < 0:
            raise ModelComparisonContractError("NEGATIVE_SCORE_INPUT")
        scored.append((predicted, actual))
    if not scored:
        return {
            "status": "NOT_COMPUTABLE_NO_KNOWN_ACTUAL_ROWS",
            "scored_row_count": 0,
            "unknown_row_count": unknown_count,
        }
    absolute_errors = [abs(predicted - actual) for predicted, actual in scored]
    signed_errors = [predicted - actual for predicted, actual in scored]
    actual_total = sum((actual for _, actual in scored), Decimal(0))
    absolute_error_total = sum(absolute_errors, Decimal(0))
    if actual_total <= 0:
        wape = "NOT_COMPUTABLE_ZERO_ACTUAL_DENOMINATOR"
    else:
        wape = format(absolute_error_total / actual_total, "f")
    ordered = sorted(absolute_errors)
    return {
        "status": "COMPUTABLE",
        "scored_row_count": len(scored),
        "unknown_row_count": unknown_count,
        "actual_kg": format(actual_total, "f"),
        "absolute_error_kg": format(absolute_error_total, "f"),
        "daily_wape": wape,
        "daily_mae_kg": format(absolute_error_total / len(scored), "f"),
        "daily_bias_kg_per_row": format(sum(signed_errors, Decimal(0)) / len(scored), "f"),
        "bias_sign": "PREDICTED_MINUS_ACTUAL; POSITIVE_OVERPREDICTION",
        "median_absolute_error_kg": format(_percentile(ordered, Decimal("0.5")), "f"),
        "p75_absolute_error_kg": format(_percentile(ordered, Decimal("0.75")), "f"),
        "p90_absolute_error_kg": format(_percentile(ordered, Decimal("0.9")), "f"),
        "max_absolute_error_kg": format(ordered[-1], "f"),
    }


def _percentile(values: Sequence[Decimal], fraction: Decimal) -> Decimal:
    if not values:
        raise ModelComparisonContractError("PERCENTILE_REQUIRES_VALUES")
    if len(values) == 1:
        return values[0]
    position = fraction * Decimal(len(values) - 1)
    low = int(position)
    high = min(low + 1, len(values) - 1)
    return values[low] + (position - low) * (values[high] - values[low])


def actual_total_metric(
    *, predicted_totals: Sequence[Decimal], actual_totals: Sequence[Decimal]
) -> dict[str, str | int]:
    """Pool season-total evaluation rows with a zero-denominator fail-closed rule."""

    if len(predicted_totals) != len(actual_totals):
        raise ModelComparisonContractError("TOTAL_METRIC_ROW_COUNT_MISMATCH")
    if not actual_totals:
        return {
            "status": "NOT_COMPUTABLE_NO_COMPLETE_ACTUAL_TOTAL_AUTHORITY_IN_COMMON_SCOPE",
            "base_season_count": 0,
        }
    actual_sum = sum(actual_totals, Decimal(0))
    errors = [
        abs(predicted - actual)
        for predicted, actual in zip(predicted_totals, actual_totals, strict=True)
    ]
    signed_errors = [
        predicted - actual
        for predicted, actual in zip(predicted_totals, actual_totals, strict=True)
    ]
    error_sum = sum(errors, Decimal(0))
    return {
        "status": "COMPUTABLE" if actual_sum > 0 else "NOT_COMPUTABLE_ZERO_ACTUAL_DENOMINATOR",
        "base_season_count": len(actual_totals),
        "actual_total_kg": format(actual_sum, "f"),
        "absolute_error_kg": format(error_sum, "f"),
        "season_total_wape": (
            format(error_sum / actual_sum, "f")
            if actual_sum > 0
            else "NOT_COMPUTABLE_ZERO_ACTUAL_DENOMINATOR"
        ),
        "season_total_mae_kg": format(error_sum / len(actual_totals), "f"),
        "season_total_bias_kg_per_base": format(
            sum(signed_errors, Decimal(0)) / len(signed_errors), "f"
        ),
        "season_total_absolute_percentage_error": (
            format(error_sum / actual_sum, "f")
            if actual_sum > 0
            else "NOT_COMPUTABLE_ZERO_ACTUAL_DENOMINATOR"
        ),
    }


def complete_peak_authority(row: Mapping[str, Any], *, kind: str) -> bool:
    """Peak scoring requires both the frozen complete flag and eligible status."""

    if kind == "single_day":
        return row.get("single_day_peak_complete") == "true" and str(
            row.get("single_day_peak_coverage_status", "")
        ) not in {"", "NOT_COMPUTABLE_FROZEN_AUTHORITY_OR_BASE_SCOPE"}
    if kind == "rolling7":
        return row.get("rolling_7day_complete") == "true" and str(
            row.get("rolling_7day_coverage_status", "")
        ) not in {"", "NOT_COMPUTABLE_FROZEN_AUTHORITY_OR_BASE_SCOPE"}
    raise ModelComparisonContractError(f"UNKNOWN_PEAK_AUTHORITY_KIND:{kind}")


def date_at_iso(value: Any) -> date:
    """Small shared parser used by reporting and unit acceptance."""

    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ModelComparisonContractError("INVALID_CANONICAL_DATE") from exc
