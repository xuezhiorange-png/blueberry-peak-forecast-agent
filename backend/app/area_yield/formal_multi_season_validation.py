"""Label-blind, deterministic validation primitives for V0.7-S1.

This module deliberately keeps the V0.5 Model A mathematics at the boundary:
the Base-aware total rule is the median of historical Base yields with an
explicit global-median rule for an unseen Base, while the daily reference is
the already frozen ``AREA_DAILY_RIDGE_V1`` artifact.  The new code is the
validation protocol, not a new estimator.

Validation labels are represented as optional values.  A missing/unknown day
is never converted to zero.  Predictions are sealed before the target source
is loaded by the orchestration script; scoring only consumes the sealed
prediction payload and a separately loaded actual authority.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Any

from backend.app.area_yield.base_product import _ridge_raw_value
from backend.app.area_yield.composite_r5 import compose
from backend.app.area_yield.data import digest

MODEL_A = "AREA_PLUS_HISTORICAL_HARVEST"
TOTAL_MODEL = "BASE_AWARE_BASELINE_R1"
TEMPORAL_MODEL = "AREA_DAILY_RIDGE_V1_FROZEN_REFERENCE"
BUSINESS_CUTOFF = "04-15_INCLUSIVE_PER_SEASON"
HISTORY_POLICY = "IMMEDIATE_PRIOR_SEASON_ONLY_FAIL_CLOSED_NO_GLOBAL_FALLBACK"
AREA_TYPE = "REFERENCE_AREA"
DEFAULT_BOUNDARY_AUTHORITY_SOURCE = (
    "configs/v0_5_area_forecast_model_v1.json:temporal_model.calendar"
)
DEFAULT_BOUNDARY_AUTHORITY_HASH = "cf0e1c4bffc4acc404dd0479c36b02f78df893ef25dda819359eaa317157dabf"
R7B_BOUNDARY_AUTHORITY_SOURCE = "docs/next-version/evidence/three-season-business-boundary-r7b.json"
R7B_BOUNDARY_AUTHORITY_HASH = "e8ccfc929f301690511e09601bb544ffe94c3b805a87ca498297ccf098af8cc4"
R7B_BOUNDARY_POLICY = "USER_CONFIRMED_2526_BUSINESS_WINDOW_R7B"
KNOWN_STATUSES = frozenset({"KNOWN_MAPPED_SUBTOTAL", "CONFIRMED_ZERO"})


class FormalValidationError(ValueError):
    """Raised when a validation contract cannot be established."""


@dataclass(frozen=True, slots=True)
class ActualDay:
    """One day from an actual authority, with explicit coverage semantics."""

    day: date
    quantity_kg: Decimal | None
    status: str
    source_hash: str


@dataclass(frozen=True, slots=True)
class BusinessBoundary:
    """A frozen season window selected before validation labels are read."""

    season: str
    start: date
    end: date
    authority_source: str
    authority_hash: str
    policy: str

    def payload(self) -> dict[str, str]:
        return {
            "season": self.season,
            "business_start": self.start.isoformat(),
            "business_end": self.end.isoformat(),
            "authority_source": self.authority_source,
            "authority_hash": self.authority_hash,
            "policy": self.policy,
        }


@dataclass(frozen=True, slots=True)
class TotalModel:
    """Frozen Model A total rule fitted only on past samples."""

    base_yields_kg_per_mu: Mapping[str, Decimal]
    prior_season: str
    training_sample_hash: str
    model_id: str = TOTAL_MODEL

    def payload(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "rule": HISTORY_POLICY,
            "prior_season": self.prior_season,
            "base_yields_kg_per_mu": {
                key: _decimal_text(self.base_yields_kg_per_mu[key])
                for key in sorted(self.base_yields_kg_per_mu)
            },
            "training_sample_hash": self.training_sample_hash,
        }

    @property
    def artifact_hash(self) -> str:
        return digest(self.payload())


def _decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise FormalValidationError("NONFINITE_DECIMAL")
    return format(value, "f")


def _season_years(season: str) -> tuple[int, int]:

    try:
        start_year = int(season[:4])
        end_year = int(season[5:])
    except (TypeError, ValueError) as exc:
        raise FormalValidationError("INVALID_SEASON") from exc
    if end_year != start_year + 1:
        raise FormalValidationError("INVALID_SEASON")
    return start_year, end_year


def business_boundary(season: str) -> BusinessBoundary:
    """Resolve the pre-sealed business window from frozen authority."""

    start_year, end_year = _season_years(season)
    if season == "2025-2026":
        return BusinessBoundary(
            season=season,
            start=date(2025, 7, 22),
            end=date(2026, 4, 15),
            authority_source=R7B_BOUNDARY_AUTHORITY_SOURCE,
            authority_hash=R7B_BOUNDARY_AUTHORITY_HASH,
            policy=R7B_BOUNDARY_POLICY,
        )
    return BusinessBoundary(
        season=season,
        start=date(start_year, 7, 1),
        end=date(end_year, 4, 15),
        authority_source=DEFAULT_BOUNDARY_AUTHORITY_SOURCE,
        authority_hash=DEFAULT_BOUNDARY_AUTHORITY_HASH,
        policy="EXISTING_JULY_01_THROUGH_APRIL_15_MODEL_AUTHORITY",
    )


def business_calendar(season: str, boundary: BusinessBoundary | None = None) -> list[date]:
    """Return the authority-selected inclusive business calendar."""

    resolved = boundary or business_boundary(season)
    if resolved.season != season or resolved.end < resolved.start:
        raise FormalValidationError("INVALID_BUSINESS_BOUNDARY")
    return [
        resolved.start + timedelta(days=index)
        for index in range((resolved.end - resolved.start).days + 1)
    ]


def model_calendar(season: str) -> list[date]:
    """Return the frozen temporal artifact's full July-01..April-15 axis."""

    start_year, end_year = _season_years(season)
    start = date(start_year, 7, 1)
    end = date(end_year, 4, 15)
    return [start + timedelta(days=index) for index in range((end - start).days + 1)]


def _positive(value: Decimal) -> Decimal:
    if not value.is_finite() or value <= 0:
        raise FormalValidationError("NONPOSITIVE_MODEL_VALUE")
    return value


def fit_total_model(
    samples: Sequence[Mapping[str, Any]], *, prior_season: str | None = None
) -> TotalModel:
    """Fit the unchanged Base-aware historical-yield rule on past data.

    ``samples`` are mapped observed subtotals with a frozen reference area.
    They remain explicitly partial/coverage-limited; this function does not
    upgrade them to complete season totals.
    """

    normalized: list[dict[str, str]] = []
    by_base: dict[str, Decimal] = {}
    seasons: set[str] = set()
    for item in samples:
        try:
            base_id = str(item["base_id"])
            season = str(item["season"])
            quantity = _positive(Decimal(str(item["quantity_kg"])))
            area = _positive(Decimal(str(item["reference_area_mu"])))
        except (KeyError, InvalidOperation, TypeError) as exc:
            raise FormalValidationError("TRAINING_SAMPLE_INVALID") from exc
        seasons.add(season)
        if prior_season is not None and season != prior_season:
            raise FormalValidationError("NON_IMMEDIATE_PRIOR_TRAINING_SAMPLE")
        if base_id in by_base:
            raise FormalValidationError("DUPLICATE_IMMEDIATE_PRIOR_BASE_HISTORY")
        yield_value = (quantity / area).quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)
        normalized.append(
            {
                "base_id": base_id,
                "season": season,
                "quantity_kg": _decimal_text(quantity),
                "reference_area_mu": _decimal_text(area),
                "area_status": str(item.get("area_status", AREA_TYPE)),
                "quantity_semantics": str(
                    item.get("quantity_semantics", "MAPPED_OBSERVED_SUBTOTAL")
                ),
            }
        )
        by_base[base_id] = yield_value
    if not normalized:
        raise FormalValidationError("NO_TRAINING_SAMPLES")
    if prior_season is None:
        if len(seasons) != 1:
            raise FormalValidationError("PRIOR_SEASON_REQUIRED")
        prior_season = next(iter(seasons))
    if not prior_season or seasons != {prior_season}:
        raise FormalValidationError("NON_IMMEDIATE_PRIOR_TRAINING_SAMPLE")
    return TotalModel(
        base_yields_kg_per_mu=by_base,
        prior_season=prior_season,
        training_sample_hash=digest(
            sorted(normalized, key=lambda row: (row["season"], row["base_id"]))
        ),
    )


def predict_total(model: TotalModel, base_id: str, reference_area_mu: Decimal) -> dict[str, str]:
    """Predict one Base total without reading validation labels."""

    area = _positive(reference_area_mu)
    if base_id not in model.base_yields_kg_per_mu:
        raise FormalValidationError("PRIOR_SEASON_HISTORY_MISSING")
    yield_value = model.base_yields_kg_per_mu[base_id]
    basis = "IMMEDIATE_PRIOR_BASE_HISTORY"
    total = (area * yield_value).quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)
    return {
        "base_id": base_id,
        "reference_area_mu": _decimal_text(area),
        "predicted_yield_kg_per_mu": _decimal_text(yield_value),
        "predicted_season_total_kg": _decimal_text(total),
        "total_prediction_basis": basis,
    }


def predict_daily_curve(
    *,
    season: str,
    reference_area_mu: Decimal,
    predicted_total_kg: Decimal,
    temporal_model: Mapping[str, Any],
    boundary: BusinessBoundary | None = None,
) -> list[dict[str, str]]:
    """Use the existing frozen temporal implementation and deterministic peaks."""

    resolved_boundary = boundary or business_boundary(season)
    days = business_calendar(season, resolved_boundary)
    full_days = model_calendar(season)
    season_start = full_days[0]
    denominator = (full_days[-1] - season_start).days
    raw = [
        _ridge_raw_value(
            temporal_model,
            reference_area_mu,
            (day - season_start).days / denominator,
        )
        for day in full_days
    ]
    if not raw or not all(value >= 0 for value in raw):
        raise FormalValidationError("TEMPORAL_SHAPE_NOT_NORMALIZABLE")
    day_to_raw = dict(zip(full_days, raw, strict=True))
    window_raw = [day_to_raw[day] for day in days]
    raw_total = sum(window_raw)
    if not raw_total:
        raise FormalValidationError("TEMPORAL_SHAPE_NOT_NORMALIZABLE")
    shares = [value / raw_total for value in window_raw]
    if abs(sum(shares) - 1.0) > 1e-12:
        raise FormalValidationError("TEMPORAL_SHARE_NOT_NORMALIZED")
    quantities = compose(_decimal_text(predicted_total_kg), shares)
    return [
        {
            "date": day.isoformat(),
            "predicted_quantity_kg": str(quantity),
            "normalized_share": format(share, ".17g"),
        }
        for day, quantity, share in zip(days, quantities, shares, strict=True)
    ]


def _earliest_max(rows: Sequence[Mapping[str, Any]], value_key: str) -> Mapping[str, Any]:
    if not rows:
        raise FormalValidationError("EMPTY_SERIES")
    return max(rows, key=lambda row: (Decimal(str(row[value_key])), -int(row["date_index"])))


def derive_prediction_peaks(daily_rows: Sequence[Mapping[str, str]]) -> dict[str, str]:
    if not daily_rows:
        raise FormalValidationError("EMPTY_SERIES")
    indexed = [
        {
            **row,
            "date_index": index,
            "date_value": date.fromisoformat(row["date"]),
        }
        for index, row in enumerate(daily_rows)
    ]
    peak = _earliest_max(indexed, "predicted_quantity_kg")
    windows = [
        {
            "date_index": index,
            "date": indexed[index]["date"],
            "end_date": indexed[index + 6]["date"],
            "cumulative_quantity_kg": format(
                sum(
                    (
                        Decimal(str(indexed[j]["predicted_quantity_kg"]))
                        for j in range(index, index + 7)
                    ),
                    Decimal(0),
                ),
                "f",
            ),
        }
        for index in range(len(indexed) - 6)
    ]
    window = _earliest_max(windows, "cumulative_quantity_kg")
    return {
        "predicted_peak_date": str(peak["date"]),
        "predicted_peak_quantity_kg": str(peak["predicted_quantity_kg"]),
        "predicted_rolling7_start_date": str(window["date"]),
        "predicted_rolling7_end_date": str(window["end_date"]),
        "predicted_rolling7_quantity_kg": str(window["cumulative_quantity_kg"]),
    }


def seal_prediction_rows(
    *,
    fold_id: str,
    train_seasons: Sequence[str],
    validation_season: str,
    base_scope: Sequence[Mapping[str, Any]],
    model: TotalModel,
    temporal_model: Mapping[str, Any],
    registry_file_sha256: str,
    temporal_artifact_sha256: str,
    training_input_hash: str,
    boundary: BusinessBoundary | None = None,
) -> dict[str, Any]:
    """Generate and seal predictions without accepting a target-label loader."""

    predictions: list[dict[str, Any]] = []
    resolved_boundary = boundary or business_boundary(validation_season)
    for base in sorted(base_scope, key=lambda row: str(row["base_id"])):
        base_id = str(base["base_id"])
        area = _positive(Decimal(str(base["productive_area_mu"])))
        total = predict_total(model, base_id, area)
        daily = predict_daily_curve(
            season=validation_season,
            reference_area_mu=area,
            predicted_total_kg=Decimal(total["predicted_season_total_kg"]),
            temporal_model=temporal_model,
            boundary=resolved_boundary,
        )
        predictions.append(
            {
                "base_id": base_id,
                "base_name": str(base["canonical_base_name"]),
                "season": validation_season,
                "predicted_daily": daily,
                "predicted_season_total_kg": total["predicted_season_total_kg"],
                "prediction_basis": total["total_prediction_basis"],
                "training_seasons": list(train_seasons),
                "model_a": MODEL_A,
                "total_model_id": TOTAL_MODEL,
                "temporal_model_id": TEMPORAL_MODEL,
                "total_model_artifact_hash": model.artifact_hash,
                "temporal_model_artifact_hash": temporal_artifact_sha256,
                "area_identity": {
                    "reference_area_mu": format(area, "f"),
                    "area_type": AREA_TYPE,
                    "area_semantics": "REFERENCE_AREA_ONLY",
                    "registry_file_sha256": registry_file_sha256,
                },
                "prediction_eligibility_status": "ELIGIBLE_REFERENCE_AREA",
                **derive_prediction_peaks(daily),
            }
        )
    prediction_hash = digest(predictions)
    manifest = {
        "fold_id": fold_id,
        "model_a": MODEL_A,
        "total_model_id": TOTAL_MODEL,
        "temporal_model_id": TEMPORAL_MODEL,
        "train_seasons": list(train_seasons),
        "validation_season": validation_season,
        "business_boundary": resolved_boundary.payload(),
        "history_policy": HISTORY_POLICY,
        "base_scope": [
            str(row["base_id"]) for row in sorted(base_scope, key=lambda row: row["base_id"])
        ],
        "training_input_hash": training_input_hash,
        "registry_file_sha256": registry_file_sha256,
        "temporal_artifact_sha256": temporal_artifact_sha256,
        "total_model_artifact_hash": model.artifact_hash,
        "prediction_hash": prediction_hash,
        "validation_labels_read": False,
        "prediction_sealed_before_validation_label_scoring": True,
        "algorithm_changed": False,
        "feature_set_changed": False,
        "objective_changed": False,
        "hyperparameter_search": False,
        "model_family_search": False,
    }
    manifest["artifact_manifest_hash"] = digest(manifest)
    return {"manifest": manifest, "predictions": predictions}


def _known_actual_rows(actual_rows: Iterable[ActualDay]) -> list[ActualDay]:
    return [
        row for row in actual_rows if row.status in KNOWN_STATUSES and row.quantity_kg is not None
    ]


def _percentile(values: Sequence[Decimal], fraction: Decimal) -> Decimal | None:
    if not values:
        return None
    ordered = sorted(values)
    position = fraction * Decimal(len(ordered) - 1)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (position - Decimal(low)) * (ordered[high] - ordered[low])


def aggregate_error_distribution(values: Sequence[Decimal]) -> dict[str, str | None]:
    return {
        "median": _decimal_text(v)
        if (v := _percentile(values, Decimal("0.5"))) is not None
        else None,
        "p75": _decimal_text(v)
        if (v := _percentile(values, Decimal("0.75"))) is not None
        else None,
        "p90": _decimal_text(v) if (v := _percentile(values, Decimal("0.9"))) is not None else None,
        "max": _decimal_text(max(values)) if values else None,
    }


def pooled_wape(abs_errors: Sequence[Decimal], actuals: Sequence[Decimal]) -> Decimal | None:
    denominator = sum(actuals, Decimal(0))
    if denominator <= 0:
        return None
    return sum(abs_errors, Decimal(0)) / denominator


def score_daily_series(
    *,
    predicted_daily: Sequence[Mapping[str, str]],
    actual_daily: Sequence[ActualDay],
    total_evaluable: bool | None = None,
    shape_evaluable: bool | None = None,
) -> dict[str, Any]:
    """Score known daily rows and refuse full-season/peak claims on gaps."""

    if len(predicted_daily) != len(actual_daily):
        raise FormalValidationError("NON_COMPARABLE_CALENDAR")
    known = _known_actual_rows(actual_daily)
    errors: list[Decimal] = []
    signed: list[Decimal] = []
    actual_values: list[Decimal] = []
    for prediction, actual in zip(predicted_daily, actual_daily, strict=True):
        if actual not in known:
            continue
        observed = actual.quantity_kg
        if observed is None:
            continue
        predicted = Decimal(prediction["predicted_quantity_kg"])
        error = predicted - observed
        errors.append(abs(error))
        signed.append(error)
        actual_values.append(observed)
    if not known:
        daily_metrics: dict[str, Any] = {
            "status": "NOT_COMPUTABLE_NO_KNOWN_ACTUAL_ROWS",
            "comparable_row_count": 0,
        }
    else:
        denominator = sum(actual_values, Decimal(0))
        daily_wape = pooled_wape(errors, actual_values)
        daily_metrics = {
            "status": "COMPUTABLE",
            "comparable_row_count": len(errors),
            "mae_kg": _decimal_text(sum(errors, Decimal(0)) / Decimal(len(errors))),
            "pooled_wape": (
                _decimal_text(daily_wape)
                if daily_wape is not None
                else "NOT_COMPUTABLE_ZERO_ACTUAL_DENOMINATOR"
            ),
            "bias_kg": _decimal_text(sum(signed, Decimal(0)) / Decimal(len(signed))),
            "bias_definition": "MEAN_PREDICTED_MINUS_ACTUAL; POSITIVE_OVERPREDICTION",
            "actual_kg_denominator": _decimal_text(denominator),
            "error_distribution_abs_kg": aggregate_error_distribution(errors),
        }
    complete = len(known) == len(actual_daily) and all(
        actual.status in KNOWN_STATUSES and actual.quantity_kg is not None
        for actual in actual_daily
    )
    total_ready = complete if total_evaluable is None else total_evaluable
    shape_ready = complete if shape_evaluable is None else shape_evaluable
    if not total_ready and not shape_ready:
        return {
            "daily": daily_metrics,
            "coverage_status": "PARTIAL",
            "known_row_count": len(known),
            "unknown_row_count": len(actual_daily) - len(known),
            "season_total": {"status": "NOT_COMPUTABLE_NO_COMPLETE_TOTAL_AUTHORITY"},
            "single_day_peak": {"status": "NOT_COMPUTABLE_PARTIAL_ACTUAL_COVERAGE"},
            "rolling7": {"status": "NOT_COMPUTABLE_PARTIAL_ACTUAL_COVERAGE"},
        }

    # R7B explicitly permits business-total and shape evaluation on the known
    # recorded ledger rows when the unknown global dates are outside the
    # active span.  No unknown row is converted to zero.
    actual_values_full = [row.quantity_kg for row in actual_daily]
    predicted_values = [Decimal(row["predicted_quantity_kg"]) for row in predicted_daily]
    actual_total = sum(
        (row.quantity_kg for row in actual_daily if row.quantity_kg is not None),
        Decimal(0),
    )
    predicted_total = sum(predicted_values, Decimal(0))
    total_abs = abs(predicted_total - actual_total)
    total_metrics: dict[str, Any] = (
        {
            "status": "COMPUTABLE",
            "actual_total_kg": _decimal_text(actual_total),
            "predicted_total_kg": _decimal_text(predicted_total),
            "mae_kg": _decimal_text(total_abs),
            "pooled_wape": (
                _decimal_text(total_abs / actual_total)
                if actual_total > 0
                else "NOT_COMPUTABLE_ZERO_ACTUAL_DENOMINATOR"
            ),
            "bias_kg": _decimal_text(predicted_total - actual_total),
            "relative_error": (
                _decimal_text((predicted_total - actual_total) / actual_total)
                if actual_total > 0
                else "NOT_COMPUTABLE_ZERO_ACTUAL_DENOMINATOR"
            ),
        }
        if total_ready
        else {"status": "NOT_COMPUTABLE_NO_COMPLETE_TOTAL_AUTHORITY"}
    )
    known_indices = [
        index
        for index, row in enumerate(actual_daily)
        if row.status in KNOWN_STATUSES and row.quantity_kg is not None
    ]

    def known_quantity(index: int) -> Decimal:
        value = actual_values_full[index]
        if value is None:
            raise FormalValidationError("KNOWN_ACTUAL_QUANTITY_MISSING")
        return value

    if not shape_ready or not known_indices:
        return {
            "daily": daily_metrics,
            "coverage_status": "COMPLETE" if complete else "PARTIAL",
            "known_row_count": len(known),
            "unknown_row_count": len(actual_daily) - len(known),
            "season_total": total_metrics
            if total_ready
            else {"status": "NOT_COMPUTABLE_NO_COMPLETE_TOTAL_AUTHORITY"},
            "single_day_peak": {"status": "NOT_COMPUTABLE_PARTIAL_ACTUAL_COVERAGE"},
            "rolling7": {"status": "NOT_COMPUTABLE_PARTIAL_ACTUAL_COVERAGE"},
        }
    actual_peak_index = max(
        known_indices,
        key=lambda index: (known_quantity(index), -index),
    )
    predicted_peak_index = max(
        range(len(predicted_daily)),
        key=lambda index: (predicted_values[index], -index),
    )
    predicted_dates = [date.fromisoformat(row["date"]) for row in predicted_daily]
    actual_windows: list[Decimal] = []
    actual_window_indices: list[int] = []
    for index in range(len(actual_daily) - 6):
        window_rows = actual_daily[index : index + 7]
        if all(row.status in KNOWN_STATUSES and row.quantity_kg is not None for row in window_rows):
            actual_window_indices.append(index)
            actual_windows.append(
                sum(
                    (known_quantity(position) for position in range(index, index + 7)),
                    Decimal(0),
                )
            )
    if not actual_windows:
        return {
            "daily": daily_metrics,
            "coverage_status": "COMPLETE" if complete else "PARTIAL",
            "known_row_count": len(known),
            "unknown_row_count": len(actual_daily) - len(known),
            "season_total": total_metrics
            if total_ready
            else {"status": "NOT_COMPUTABLE_NO_COMPLETE_TOTAL_AUTHORITY"},
            "single_day_peak": {
                "status": "COMPUTABLE",
                "actual_date": actual_daily[actual_peak_index].day.isoformat(),
                "predicted_date": predicted_dates[predicted_peak_index].isoformat(),
                "actual_quantity_kg": _decimal_text(known_quantity(actual_peak_index)),
                "predicted_quantity_kg": _decimal_text(predicted_values[predicted_peak_index]),
                "quantity_abs_error_kg": _decimal_text(
                    abs(predicted_values[predicted_peak_index] - known_quantity(actual_peak_index))
                ),
                "date_abs_error_days": abs(
                    (
                        predicted_dates[predicted_peak_index] - actual_daily[actual_peak_index].day
                    ).days
                ),
            },
            "rolling7": {"status": "NOT_COMPUTABLE_NO_COMPLETE_ROLLING7_WINDOW"},
        }
    predicted_windows = [
        sum(predicted_values[index : index + 7], Decimal(0))
        for index in range(len(predicted_daily) - 6)
    ]
    actual_window_position = max(
        range(len(actual_windows)), key=lambda position: (actual_windows[position], -position)
    )
    actual_window_index = actual_window_indices[actual_window_position]
    predicted_window_index = max(
        range(len(predicted_windows)), key=lambda index: (predicted_windows[index], -index)
    )
    actual_peak_date = predicted_dates[actual_peak_index]
    predicted_peak_date = predicted_dates[predicted_peak_index]
    actual_window_date = predicted_dates[actual_window_index]
    predicted_window_date = predicted_dates[predicted_window_index]
    return {
        "daily": daily_metrics,
        "coverage_status": (
            "COMPLETE" if complete else "BUSINESS_AUTHORITY_SHAPE_ELIGIBLE_WITH_UNKNOWN_ROWS"
        ),
        "known_row_count": len(known),
        "unknown_row_count": len(actual_daily) - len(known),
        "season_total": total_metrics,
        "single_day_peak": {
            "status": "COMPUTABLE",
            "actual_date": actual_peak_date.isoformat(),
            "predicted_date": predicted_peak_date.isoformat(),
            "actual_quantity_kg": _decimal_text(known_quantity(actual_peak_index)),
            "predicted_quantity_kg": _decimal_text(predicted_values[predicted_peak_index]),
            "quantity_abs_error_kg": _decimal_text(
                abs(predicted_values[predicted_peak_index] - known_quantity(actual_peak_index))
            ),
            "date_abs_error_days": abs((predicted_peak_date - actual_peak_date).days),
        },
        "rolling7": {
            "status": "COMPUTABLE",
            "actual_start_date": actual_window_date.isoformat(),
            "predicted_start_date": predicted_window_date.isoformat(),
            "actual_quantity_kg": _decimal_text(actual_windows[actual_window_position]),
            "predicted_quantity_kg": _decimal_text(predicted_windows[predicted_window_index]),
            "quantity_abs_error_kg": _decimal_text(
                abs(
                    predicted_windows[predicted_window_index]
                    - actual_windows[actual_window_position]
                )
            ),
            "start_date_abs_error_days": abs((predicted_window_date - actual_window_date).days),
        },
    }


def aggregate_fold_scores(base_scores: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate with pooled denominators, never an arithmetic WAPE mean."""

    daily_rows = [row["daily"] for row in base_scores if row["daily"].get("status") == "COMPUTABLE"]
    abs_daily = [
        Decimal(row.get("_daily_abs_error_kg", row.get("daily_abs_error_kg", "0")))
        for row in base_scores
        if row.get("_daily_abs_error_kg", row.get("daily_abs_error_kg")) is not None
    ]
    actual_daily = [
        Decimal(row.get("_daily_actual_kg", row.get("daily_actual_kg", "0")))
        for row in base_scores
        if row.get("_daily_actual_kg", row.get("daily_actual_kg")) is not None
    ]
    daily_wape = pooled_wape(abs_daily, actual_daily)
    total_rows = [
        row["season_total"]
        for row in base_scores
        if row["season_total"].get("status") == "COMPUTABLE"
    ]
    total_abs = [Decimal(row["mae_kg"]) for row in total_rows]
    total_actual = [Decimal(row["actual_total_kg"]) for row in total_rows]
    total_signed = [
        Decimal(row["predicted_total_kg"]) - Decimal(row["actual_total_kg"]) for row in total_rows
    ]
    peak_rows = [
        row["single_day_peak"]
        for row in base_scores
        if row["single_day_peak"].get("status") == "COMPUTABLE"
    ]
    rolling_rows = [
        row["rolling7"] for row in base_scores if row["rolling7"].get("status") == "COMPUTABLE"
    ]
    peak_abs = [Decimal(row["quantity_abs_error_kg"]) for row in peak_rows]
    peak_actual = [Decimal(row["actual_quantity_kg"]) for row in peak_rows]
    rolling_abs = [Decimal(row["quantity_abs_error_kg"]) for row in rolling_rows]
    rolling_actual = [Decimal(row["actual_quantity_kg"]) for row in rolling_rows]
    peak_wape = pooled_wape(peak_abs, peak_actual)
    rolling_wape = pooled_wape(rolling_abs, rolling_actual)
    total_wape = pooled_wape(total_abs, total_actual)
    daily_signed = [
        Decimal(row.get("_daily_signed_error_kg", row.get("daily_signed_error_kg", "0")))
        for row in base_scores
        if row.get("_daily_signed_error_kg", row.get("daily_signed_error_kg")) is not None
    ]
    daily_abs_values = [
        Decimal(value) for row in base_scores for value in row.get("_daily_abs_errors_kg", [])
    ]
    total_relative_errors = [
        abs(Decimal(row["relative_error"]))
        for row in total_rows
        if not str(row.get("relative_error", "")).startswith("NOT_COMPUTABLE")
    ]
    peak_date_errors = [Decimal(str(row["date_abs_error_days"])) for row in peak_rows]
    rolling_date_errors = [Decimal(str(row["start_date_abs_error_days"])) for row in rolling_rows]
    return {
        "daily": {
            "status": "COMPUTABLE" if daily_rows else "NOT_COMPUTABLE_NO_COMPARABLE_ROWS",
            "pooled_wape": _decimal_text(daily_wape)
            if daily_wape is not None
            else (
                "NOT_COMPUTABLE_ZERO_ACTUAL_DENOMINATOR"
                if daily_rows
                else "NOT_COMPUTABLE_NO_COMPARABLE_ROWS"
            ),
            "comparable_row_count": sum(int(row["comparable_row_count"]) for row in daily_rows),
            "pooled_actual_kg": _decimal_text(sum(actual_daily, Decimal(0)))
            if actual_daily
            else "0",
            "pooled_absolute_error_kg": _decimal_text(sum(abs_daily, Decimal(0)))
            if abs_daily
            else "0",
            "bias_kg": (
                _decimal_text(
                    sum(daily_signed, Decimal(0))
                    / Decimal(sum(int(row["comparable_row_count"]) for row in daily_rows))
                )
                if daily_signed and daily_rows
                else None
            ),
            "bias_definition": "MEAN_PREDICTED_MINUS_ACTUAL; POSITIVE_OVERPREDICTION",
            "aggregation_policy": "POOLED_ABSOLUTE_ERROR_OVER_POOLED_ACTUAL",
            "error_distribution_abs_kg": aggregate_error_distribution(daily_abs_values),
        },
        "season_total": {
            "status": "COMPUTABLE" if total_rows else "NOT_COMPUTABLE_NO_COMPLETE_TOTAL_AUTHORITY",
            "pooled_wape": (
                _decimal_text(total_wape)
                if total_wape is not None
                else "NOT_COMPUTABLE_NO_COMPLETE_TOTAL_AUTHORITY"
            ),
            "computable_base_count": len(total_rows),
            "bias_kg": _decimal_text(sum(total_signed, Decimal(0))) if total_rows else None,
            "bias_definition": "SUM_PREDICTED_MINUS_ACTUAL_OVER_COMPUTABLE_BASE_SEASONS",
            "aggregation_policy": "POOLED_ABSOLUTE_ERROR_OVER_POOLED_ACTUAL",
            "error_distribution_abs_relative": aggregate_error_distribution(total_relative_errors),
        },
        "single_day_peak": {
            "status": "COMPUTABLE" if peak_rows else "NOT_COMPUTABLE_NO_COMPLETE_PEAK_AUTHORITY",
            "computable_base_count": len(peak_rows),
            "quantity_wape": (
                _decimal_text(peak_wape)
                if peak_wape is not None
                else (
                    "NOT_COMPUTABLE_ZERO_ACTUAL_DENOMINATOR"
                    if peak_rows
                    else "NOT_COMPUTABLE_NO_COMPLETE_PEAK_AUTHORITY"
                )
            ),
            "date_abs_error_days_mean": (
                _decimal_text(
                    sum(Decimal(str(row["date_abs_error_days"])) for row in peak_rows)
                    / Decimal(len(peak_rows))
                )
                if peak_rows
                else None
            ),
            "date_abs_error_days_distribution": aggregate_error_distribution(peak_date_errors),
        },
        "rolling7": {
            "status": "COMPUTABLE"
            if rolling_rows
            else "NOT_COMPUTABLE_NO_COMPLETE_ROLLING7_AUTHORITY",
            "computable_base_count": len(rolling_rows),
            "quantity_wape": (
                _decimal_text(rolling_wape)
                if rolling_wape is not None
                else (
                    "NOT_COMPUTABLE_ZERO_ACTUAL_DENOMINATOR"
                    if rolling_rows
                    else "NOT_COMPUTABLE_NO_COMPLETE_ROLLING7_AUTHORITY"
                )
            ),
            "date_abs_error_days_mean": (
                _decimal_text(
                    sum(Decimal(str(row["start_date_abs_error_days"])) for row in rolling_rows)
                    / Decimal(len(rolling_rows))
                )
                if rolling_rows
                else None
            ),
            "date_abs_error_days_distribution": aggregate_error_distribution(rolling_date_errors),
        },
    }


def actual_rows_from_mapping(
    *,
    season: str,
    raw_rows: Sequence[Mapping[str, Any]],
    label_to_base: Mapping[tuple[str, str], str],
    candidate_bases_by_label: Mapping[tuple[str, str], Sequence[str]],
    base_scope: Sequence[Mapping[str, Any]],
    source_hash: str,
    boundary: BusinessBoundary | None = None,
) -> dict[str, list[ActualDay]]:
    """Build a mapped actual authority without filling missing days."""

    calendar = business_calendar(season, boundary)
    global_dates = {
        row["date"]
        for row in raw_rows
        if row.get("date") is not None
        and calendar[0] <= row["date"] <= calendar[-1]
        and row.get("quantity") is not None
    }
    aggregate: dict[tuple[str, date], Decimal] = {}
    explicit_zero: set[tuple[str, date]] = set()
    candidate_by_base: dict[str, set[str]] = {}
    mapped_by_base: dict[str, set[str]] = {}
    for row in raw_rows:
        day = row.get("date")
        label = str(row.get("farm", ""))
        quantity = row.get("quantity")
        if day is None or quantity is None or not calendar[0] <= day <= calendar[-1]:
            continue
        mapping_key = (season, label)
        base_id = label_to_base.get(mapping_key)
        if base_id:
            key = (base_id, day)
            aggregate[key] = aggregate.get(key, Decimal(0)) + Decimal(str(quantity))
            mapped_by_base.setdefault(base_id, set()).add(label)
            if Decimal(str(quantity)) == 0:
                explicit_zero.add(key)
        for candidate in candidate_bases_by_label.get(mapping_key, ()):
            candidate_by_base.setdefault(candidate, set()).add(label)
    result: dict[str, list[ActualDay]] = {}
    for base in sorted(base_scope, key=lambda item: str(item["base_id"])):
        base_id = str(base["base_id"])
        rows: list[ActualDay] = []
        for day in calendar:
            key = (base_id, day)
            if day not in global_dates:
                rows.append(ActualDay(day, None, "UNKNOWN_GLOBAL_NO_RECORD", source_hash))
            elif key in aggregate:
                value = aggregate[key]
                status = "CONFIRMED_ZERO" if value == 0 else "KNOWN_MAPPED_SUBTOTAL"
                rows.append(ActualDay(day, value, status, source_hash))
            elif key in explicit_zero:
                rows.append(ActualDay(day, Decimal(0), "CONFIRMED_ZERO", source_hash))
            elif base_id in candidate_by_base:
                rows.append(ActualDay(day, None, "UNKNOWN_MEMBER_COVERAGE", source_hash))
            else:
                rows.append(ActualDay(day, None, "UNKNOWN_MISSING", source_hash))
        result[base_id] = rows
    return result


def fold_input_hash(
    *,
    train_samples: Sequence[Mapping[str, Any]],
    train_seasons: Sequence[str],
    validation_season: str,
    registry_file_sha256: str,
    temporal_artifact_sha256: str,
    boundary: BusinessBoundary | None = None,
) -> str:
    return digest(
        {
            "model_a": MODEL_A,
            "total_model": TOTAL_MODEL,
            "temporal_model": TEMPORAL_MODEL,
            "train_seasons": list(train_seasons),
            "validation_season": validation_season,
            "business_boundary": (boundary or business_boundary(validation_season)).payload(),
            "history_policy": HISTORY_POLICY,
            "registry_file_sha256": registry_file_sha256,
            "temporal_artifact_sha256": temporal_artifact_sha256,
            "train_samples": sorted(
                [dict(item) for item in train_samples],
                key=lambda item: (str(item["season"]), str(item["base_id"])),
            ),
            "weather_used": False,
        }
    )
