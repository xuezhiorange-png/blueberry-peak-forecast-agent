"""V0.5 BASE-grain area-driven forecast product.

This module is an inference boundary over frozen R1 artifacts.  It never fits
an estimator: total scale is the frozen Base-aware prior-yield rule and the
daily shape is the frozen Ridge artifact projected onto the requested season.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError, model_validator

from backend.app.area_yield.base_product_authority import (
    HISTORY_QUANTITY_SEMANTICS,
    PRODUCT_MODEL_VERSION,
    TEMPORAL_MODEL_ID,
    TOTAL_MODEL_ID,
    BaseAreaForecastAuthorityError,
    BaseAreaForecastError,
    BaseAreaForecastPersistenceError,
    BaseAreaForecastRequestError,
    BaseAreaForecastUnsupportedError,
    BaseProductAuthority,
    load_base_product_authority,
)
from backend.app.area_yield.composite_r5 import compose
from backend.app.area_yield.data import digest
from backend.app.area_yield.evaluation import summaries
from backend.app.area_yield.product import canonical_share_text
from backend.app.area_yield.total_yield_r4 import emit, positive

POLICY_VERSION = "V0_5_AREA_FORECAST_PRODUCT_V1"
BUSINESS_SEASON_WINDOW = "JULY_01_THROUGH_APRIL_15_INCLUSIVE"


class AreaForecastProductRequest(BaseModel):
    """Caller-owned business inputs; authority paths and model selectors are absent."""

    model_config = ConfigDict(extra="forbid")

    base_id: StrictStr | None = Field(default=None, min_length=1, max_length=80)
    base_name: StrictStr | None = Field(default=None, min_length=1, max_length=200)
    target_area_mu: StrictStr
    target_season: StrictStr = Field(pattern=r"^\d{4}-\d{4}$")
    forecast_start_date: date | None = None
    forecast_end_date: date | None = None

    @model_validator(mode="after")
    def validate_request(self) -> AreaForecastProductRequest:
        if (self.base_id is None) == (self.base_name is None):
            raise ValueError("exactly one of base_id or base_name is required")
        if self.base_id is not None and re.fullmatch(r"base_[0-9a-f]{24}", self.base_id) is None:
            raise ValueError("base_id format is invalid")
        try:
            positive(self.target_area_mu)
        except (TypeError, ValueError, InvalidOperation) as exc:
            raise ValueError("target_area_mu must be a positive decimal string") from exc
        start_year = int(self.target_season[:4])
        if int(self.target_season[5:]) != start_year + 1:
            raise ValueError("target_season must contain consecutive years")
        if not 1 <= start_year <= 9998:
            raise ValueError("target_season is outside supported range")
        if (self.forecast_start_date is None) != (self.forecast_end_date is None):
            raise ValueError("forecast start and end must be provided together")
        return self


class BaseDailyForecast(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    predicted_quantity_kg: StrictStr
    normalized_share: StrictStr


class BaseSingleDayPeak(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    quantity_kg: StrictStr


class BaseRolling7DayPeak(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_date: date
    end_date: date
    cumulative_quantity_kg: StrictStr


class AreaForecastProductResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: StrictStr = "AREA_FORECAST_PRODUCT_V1"
    canonical_base_id: StrictStr
    canonical_base_name: StrictStr
    reference_area_mu: StrictStr
    target_area_mu: StrictStr
    target_season: StrictStr
    forecast_start_date: date
    forecast_end_date: date
    predicted_yield_kg_per_mu: StrictStr
    predicted_season_total_kg: StrictStr
    total_model_id: StrictStr = TOTAL_MODEL_ID
    temporal_model_id: StrictStr = TEMPORAL_MODEL_ID
    model_version: StrictStr = PRODUCT_MODEL_VERSION
    model_status: StrictStr = "EXPERIMENTAL"
    season_total_status: StrictStr = "EXPERIMENTAL"
    daily_curve_status: StrictStr = "EXPLORATORY"
    single_day_peak_status: StrictStr = "EXPLORATORY"
    rolling_7day_peak_status: StrictStr = "EXPLORATORY"
    daily_curve: list[BaseDailyForecast]
    single_day_peak: BaseSingleDayPeak
    rolling_7day_peak: BaseRolling7DayPeak
    mass_balance: dict[str, Any]
    metadata: dict[str, Any]
    source_hashes: list[StrictStr]
    limitations: list[StrictStr]
    result_hash: StrictStr = ""


def _season_window(season: str) -> tuple[date, date]:
    try:
        year = int(season[:4])
    except (TypeError, ValueError) as exc:
        raise BaseAreaForecastRequestError("INVALID_TARGET_SEASON") from exc
    return date(year, 7, 1), date(year + 1, 4, 15)


def _calendar(start: date, end: date) -> list[date]:
    return [start + timedelta(days=index) for index in range((end - start).days + 1)]


def _resolve_base(
    request: AreaForecastProductRequest, authority: BaseProductAuthority
) -> dict[str, Any]:
    if request.base_id is not None:
        base = authority.bases_by_id.get(request.base_id)
    else:
        base = authority.bases_by_name.get(request.base_name or "")
    if base is None:
        raise BaseAreaForecastUnsupportedError("UNREGISTERED_BASE")
    return base


def _prior_history(
    base_id: str, target_season: str, authority: BaseProductAuthority
) -> dict[str, Any]:
    year = int(target_season[:4])
    required_season = f"{year - 1:04d}-{year:04d}"
    matches = [
        row
        for row in authority.history
        if row.get("base_id") == base_id and row.get("season") == required_season
    ]
    if not matches:
        raise BaseAreaForecastUnsupportedError("PRIOR_SEASON_HISTORY_MISSING")
    if len(matches) != 1:
        raise BaseAreaForecastAuthorityError("DUPLICATE_PRIOR_SEASON_HISTORY")
    return matches[0]


def _ridge_raw_value(temporal: Mapping[str, Any], area_mu: Decimal, progress: float) -> float:
    angle = 2.0 * math.pi * progress
    area = float(area_mu) / 1000.0
    values = [
        area,
        progress,
        math.sin(angle),
        math.cos(angle),
        math.sin(2.0 * angle),
        math.cos(2.0 * angle),
        area * math.sin(angle),
        area * math.cos(angle),
        area * math.sin(2.0 * angle),
        area * math.cos(2.0 * angle),
    ]
    means = [float(value) for value in temporal["feature_mean"]]
    scales = [float(value) for value in temporal["feature_scale"]]
    coefficients = [float(value) for value in temporal["coefficients"]]
    prediction = coefficients[0] + math.fsum(
        (value - mean) / scale * coefficient
        for value, mean, scale, coefficient in zip(
            values, means, scales, coefficients[1:], strict=True
        )
    )
    if not math.isfinite(prediction):
        raise BaseAreaForecastAuthorityError("NONFINITE_TEMPORAL_PREDICTION")
    return max(prediction, 0.0)


def _raw_shape(
    dates: list[date],
    season_start: date,
    season_end: date,
    area_mu: Decimal,
    authority: BaseProductAuthority,
) -> list[float]:
    denominator = (season_end - season_start).days
    if denominator <= 0:
        raise BaseAreaForecastRequestError("FORECAST_WINDOW_MUST_HAVE_POSITIVE_SPAN")
    return [
        _ridge_raw_value(
            authority.model["temporal_model"],
            area_mu,
            (day - season_start).days / denominator,
        )
        for day in dates
    ]


def _normalized_shape(
    dates: list[date],
    season_start: date,
    season_end: date,
    area_mu: Decimal,
    authority: BaseProductAuthority,
) -> list[float]:
    raw = _raw_shape(dates, season_start, season_end, area_mu, authority)
    total = math.fsum(raw)
    if not math.isfinite(total) or total <= 0:
        raise BaseAreaForecastAuthorityError("TEMPORAL_SHAPE_NOT_NORMALIZABLE")
    shares = [value / total for value in raw]
    if abs(math.fsum(shares) - 1.0) > 1e-12:
        raise BaseAreaForecastAuthorityError("TEMPORAL_SHAPE_NORMALIZATION_FAILED")
    return shares


def _shape_diagnostics(
    dates: list[date],
    season_start: date,
    season_end: date,
    area_mu: Decimal,
    authority: BaseProductAuthority,
) -> dict[str, Any]:
    """Expose window clipping explicitly without changing the shape calculation."""

    full_dates = _calendar(season_start, season_end)
    full_raw = _raw_shape(full_dates, season_start, season_end, area_mu, authority)
    full_total = math.fsum(full_raw)
    window_raw = _raw_shape(dates, season_start, season_end, area_mu, authority)
    window_total = math.fsum(window_raw)
    if not math.isfinite(full_total) or full_total <= 0 or window_total <= 0:
        raise BaseAreaForecastAuthorityError("TEMPORAL_SHAPE_NOT_NORMALIZABLE")
    full_normalized = [value / full_total for value in full_raw]
    window_normalized = [value / window_total for value in window_raw]
    window_start_index = (dates[0] - season_start).days
    window_end_index = window_start_index + len(dates)
    pre_window_mass = math.fsum(full_normalized[window_start_index:window_end_index])
    truncated = dates != full_dates
    return {
        "full_window_start": season_start.isoformat(),
        "full_window_end": season_end.isoformat(),
        "normalized_share_sum_pre_window": canonical_share_text(math.fsum(full_normalized)),
        "normalized_share_sum_in_window": canonical_share_text(math.fsum(window_normalized)),
        "in_window_share_mass_before_renormalization": canonical_share_text(pre_window_mass),
        "temporal_curve_truncated": truncated,
        "renormalization_applied": truncated,
        "clipped_mass_reallocated": False,
    }


def _nonnegative_decimal(value: str) -> Decimal:
    try:
        number = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("number must be finite and nonnegative") from exc
    if not number.is_finite() or number < 0:
        raise ValueError("number must be finite and nonnegative")
    return number


def forecast_base_area(
    request: AreaForecastProductRequest, authority: BaseProductAuthority
) -> AreaForecastProductResult:
    """Execute one frozen BASE-grain forecast with no model fitting or fallback."""

    base = _resolve_base(request, authority)
    season_start, season_end = _season_window(request.target_season)
    requested_start = request.forecast_start_date or season_start
    requested_end = request.forecast_end_date or season_end
    if (
        requested_start < season_start
        or requested_end > season_end
        or requested_end < requested_start
        or (requested_end - requested_start).days < 6
    ):
        raise BaseAreaForecastRequestError("FORECAST_WINDOW_MUST_BE_SEVEN_DAYS_INSIDE_SEASON")
    history = _prior_history(base["base_id"], request.target_season, authority)
    try:
        yield_value = positive(str(history["yield_kg_per_mu"]))
        target_area = positive(request.target_area_mu)
        reference_area = positive(str(base["productive_area_mu"]))
    except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
        raise BaseAreaForecastAuthorityError("AREA_OR_YIELD_AUTHORITY_INVALID") from exc

    dates = _calendar(requested_start, requested_end)
    # The frozen temporal artifact is evaluated at the Base reference area.
    # target_area_mu is an explicit scale input and must not change the
    # normalized temporal shape.
    shares = _normalized_shape(dates, season_start, season_end, reference_area, authority)
    shape_diagnostics = _shape_diagnostics(
        dates, season_start, season_end, reference_area, authority
    )
    predicted_total = emit(target_area * yield_value)
    quantities = compose(predicted_total, shares)
    metrics = summaries(dates, quantities)
    shape_diagnostics["peak_at_forecast_end_boundary"] = (
        metrics["single_day_peak"]["date"] == requested_end.isoformat()
    )
    daily_sum = sum(quantities, Decimal(0))
    total_decimal = Decimal(predicted_total)
    difference = daily_sum - total_decimal
    tolerance = Decimal("0.0000005") * len(quantities) + total_decimal * Decimal("1e-12")
    if abs(difference) > tolerance:
        raise BaseAreaForecastError("AREA_FORECAST_MASS_BALANCE_FAILED", "MASS_BALANCE_FAILED")

    source_hashes = sorted(
        {
            str(authority.registry["source_workbook_sha256"]),
            str(authority.registry_file_sha256),
            str(authority.model_file_sha256),
            str(authority.model["training_data_manifest_sha256"]),
            str(authority.model["history_provenance"]["identity_mapping_sha256"]),
            str(history["source_sha256"]),
        }
    )
    metadata: dict[str, Any] = {
        "forecast_policy_version": POLICY_VERSION,
        "reference_area_source": authority.registry["source_workbook_name"],
        "reference_area_source_sha256": authority.registry["source_workbook_sha256"],
        "reference_registry_artifact_sha256": authority.registry_file_sha256,
        "model_artifact_sha256": authority.model_file_sha256,
        "model_artifact_canonical_hash": authority.model["artifact_hash"],
        "training_data_manifest_sha256": authority.model["training_data_manifest_sha256"],
        "authority_hash": authority.authority_hash,
        "history_source_season": history["season"],
        "history_quantity_semantics": HISTORY_QUANTITY_SEMANTICS,
        "history_source_file": history["source_file"],
        "history_source_sha256": history["source_sha256"],
        "history_source_farm_labels": history["source_farm_labels"],
        "identity_mapping_sha256": history["identity_mapping_sha256"],
        "identity_mapping_status": history["identity_mapping_status"],
        "history_harvest_total_kg": history["harvest_total_kg"],
        "temporal_model_artifact_sha256": authority.model["research_artifacts"][
            "temporal_model_artifact_sha256"
        ],
        "total_model_source_canonical_hash": authority.model["research_artifacts"][
            "total_model_source_canonical_hash"
        ],
        "peak_at_forecast_boundary": shape_diagnostics["peak_at_forecast_end_boundary"],
        "temporal_shape_diagnostics": shape_diagnostics,
        "weather_used": False,
        "future_plan_used": False,
        "business_season_window": BUSINESS_SEASON_WINDOW,
        "normalized_share_sum": format(
            sum((Decimal(str(value)) for value in shares), Decimal(0)), "f"
        ),
        "research_evidence": authority.model["model_evidence"],
    }
    result = AreaForecastProductResult(
        canonical_base_id=base["base_id"],
        canonical_base_name=base["canonical_base_name"],
        reference_area_mu=emit(reference_area),
        target_area_mu=emit(target_area),
        target_season=request.target_season,
        forecast_start_date=requested_start,
        forecast_end_date=requested_end,
        predicted_yield_kg_per_mu=emit(yield_value),
        predicted_season_total_kg=predicted_total,
        daily_curve=[
            BaseDailyForecast(
                date=day,
                predicted_quantity_kg=emit(quantity),
                normalized_share=canonical_share_text(share),
            )
            for day, quantity, share in zip(dates, quantities, shares, strict=True)
        ],
        single_day_peak=BaseSingleDayPeak(
            date=date.fromisoformat(metrics["single_day_peak"]["date"]),
            quantity_kg=metrics["single_day_peak"]["quantity_kg"],
        ),
        rolling_7day_peak=BaseRolling7DayPeak(
            start_date=date.fromisoformat(metrics["rolling_7day_peak"]["start_date"]),
            end_date=date.fromisoformat(metrics["rolling_7day_peak"]["end_date"]),
            cumulative_quantity_kg=metrics["rolling_7day_peak"]["cumulative_quantity_kg"],
        ),
        mass_balance={
            "daily_sum_kg": emit(daily_sum),
            "predicted_season_total_kg": predicted_total,
            "difference_kg": emit(difference),
            "tolerance_kg": str(tolerance),
            "pass": True,
        },
        metadata=metadata,
        source_hashes=source_hashes,
        limitations=[
            "MODEL_STATUS_EXPERIMENTAL",
            "SEASON_TOTAL_WAPE_KNOWN_BASES_0.379265725",
            "SEASON_TOTAL_WAPE_STABLE_HISTORY_0.251107822",
            "DAILY_WAPE_0.694130360",
            "PEAK_DATE_MAE_22.230769_DAYS",
            "ROLLING_7DAY_PEAK_START_MAE_20.769231_DAYS",
            "REFERENCE_AREA_MAY_DRIFT_BY_SEASON",
            "TEMPORAL_CURVE_AND_PEAKS_EXPLORATORY",
            "NO_WEATHER_OR_FUTURE_PLAN_INPUT",
        ],
    )
    result.result_hash = digest(result.model_dump(mode="json", exclude={"result_hash"}))
    return result


def _check_result_integrity(result: AreaForecastProductResult) -> None:
    if (
        result.product_id != PRODUCT_MODEL_VERSION
        or result.total_model_id != TOTAL_MODEL_ID
        or result.temporal_model_id != TEMPORAL_MODEL_ID
        or result.model_version != PRODUCT_MODEL_VERSION
        or result.model_status != "EXPERIMENTAL"
        or result.season_total_status != "EXPERIMENTAL"
        or result.daily_curve_status != "EXPLORATORY"
        or result.single_day_peak_status != "EXPLORATORY"
        or result.rolling_7day_peak_status != "EXPLORATORY"
    ):
        raise BaseAreaForecastPersistenceError(
            "AREA_FORECAST_PERSISTENCE_INTEGRITY_ERROR", "MODEL_ID_OR_STATUS_INVALID"
        )
    rows = result.daily_curve
    if len(rows) < 7:
        raise BaseAreaForecastPersistenceError(
            "AREA_FORECAST_PERSISTENCE_INTEGRITY_ERROR", "DAILY_CURVE_TOO_SHORT"
        )
    dates = [row.date for row in rows]
    if dates != _calendar(result.forecast_start_date, result.forecast_end_date):
        raise BaseAreaForecastPersistenceError(
            "AREA_FORECAST_PERSISTENCE_INTEGRITY_ERROR", "DAILY_DATES_NOT_CONTIGUOUS"
        )
    try:
        quantities = [_nonnegative_decimal(row.predicted_quantity_kg) for row in rows]
        total = positive(result.predicted_season_total_kg)
        positive(result.predicted_yield_kg_per_mu)
        positive(result.reference_area_mu)
        positive(result.target_area_mu)
        shares = [Decimal(row.normalized_share) for row in rows]
    except (ValueError, InvalidOperation) as exc:
        raise BaseAreaForecastPersistenceError(
            "AREA_FORECAST_PERSISTENCE_INTEGRITY_ERROR", "DAILY_NUMERIC_PAYLOAD_INVALID"
        ) from exc
    if any(not share.is_finite() or share < 0 for share in shares):
        raise BaseAreaForecastPersistenceError(
            "AREA_FORECAST_PERSISTENCE_INTEGRITY_ERROR", "DAILY_SHARE_INVALID"
        )
    if abs(sum(shares, Decimal(0)) - Decimal(1)) > Decimal("1e-12"):
        raise BaseAreaForecastPersistenceError(
            "AREA_FORECAST_PERSISTENCE_INTEGRITY_ERROR", "DAILY_SHARE_SUM_INVALID"
        )
    shape_diagnostics = result.metadata.get("temporal_shape_diagnostics")
    if not isinstance(shape_diagnostics, dict):
        raise BaseAreaForecastPersistenceError(
            "AREA_FORECAST_PERSISTENCE_INTEGRITY_ERROR", "TEMPORAL_SHAPE_DIAGNOSTICS_MISSING"
        )
    expected_truncated = (
        result.forecast_start_date != _season_window(result.target_season)[0]
        or result.forecast_end_date != _season_window(result.target_season)[1]
    )
    if (
        result.metadata.get("peak_at_forecast_boundary")
        != (result.single_day_peak.date == result.forecast_end_date)
        or shape_diagnostics.get("temporal_curve_truncated") != expected_truncated
        or shape_diagnostics.get("renormalization_applied") != expected_truncated
        or shape_diagnostics.get("clipped_mass_reallocated") is not False
        or shape_diagnostics.get("peak_at_forecast_end_boundary")
        != (result.single_day_peak.date == result.forecast_end_date)
        or shape_diagnostics.get("normalized_share_sum_in_window") != "1.000000000000000"
    ):
        raise BaseAreaForecastPersistenceError(
            "AREA_FORECAST_PERSISTENCE_INTEGRITY_ERROR", "TEMPORAL_SHAPE_DIAGNOSTICS_INVALID"
        )
    difference = sum(quantities, Decimal(0)) - total
    tolerance = Decimal("0.0000005") * len(rows) + total * Decimal("1e-12")
    if abs(difference) > tolerance:
        raise BaseAreaForecastPersistenceError(
            "AREA_FORECAST_PERSISTENCE_INTEGRITY_ERROR", "DAILY_TOTAL_MISMATCH"
        )
    expected_mass_balance = {
        "daily_sum_kg": emit(sum(quantities, Decimal(0))),
        "predicted_season_total_kg": result.predicted_season_total_kg,
        "difference_kg": emit(difference),
        "tolerance_kg": str(tolerance),
        "pass": True,
    }
    if result.mass_balance != expected_mass_balance:
        raise BaseAreaForecastPersistenceError(
            "AREA_FORECAST_PERSISTENCE_INTEGRITY_ERROR", "MASS_BALANCE_MISMATCH"
        )
    metrics = summaries(dates, quantities)
    expected_single = {
        "date": metrics["single_day_peak"]["date"],
        "quantity_kg": metrics["single_day_peak"]["quantity_kg"],
    }
    expected_rolling = {
        "start_date": metrics["rolling_7day_peak"]["start_date"],
        "end_date": metrics["rolling_7day_peak"]["end_date"],
        "cumulative_quantity_kg": metrics["rolling_7day_peak"]["cumulative_quantity_kg"],
    }
    if result.single_day_peak.model_dump(mode="json") != expected_single:
        raise BaseAreaForecastPersistenceError(
            "AREA_FORECAST_PERSISTENCE_INTEGRITY_ERROR", "SINGLE_DAY_PEAK_MISMATCH"
        )
    if result.rolling_7day_peak.model_dump(mode="json") != expected_rolling:
        raise BaseAreaForecastPersistenceError(
            "AREA_FORECAST_PERSISTENCE_INTEGRITY_ERROR", "ROLLING_7DAY_PEAK_MISMATCH"
        )
    expected_hash = digest(result.model_dump(mode="json", exclude={"result_hash"}))
    if result.result_hash != expected_hash:
        raise BaseAreaForecastPersistenceError(
            "AREA_FORECAST_PERSISTENCE_INTEGRITY_ERROR", "RESULT_HASH_MISMATCH"
        )


def reload_base_forecast_result(payload: Mapping[str, Any]) -> AreaForecastProductResult:
    """Rebuild and verify a saved result without loading authority or reforecasting."""

    try:
        result = AreaForecastProductResult.model_validate(payload)
    except ValidationError as exc:
        raise BaseAreaForecastPersistenceError(
            "AREA_FORECAST_PERSISTENCE_INTEGRITY_ERROR", "RESULT_PAYLOAD_INVALID"
        ) from exc
    try:
        _check_result_integrity(result)
    except BaseAreaForecastPersistenceError:
        raise
    except (ValueError, InvalidOperation) as exc:
        raise BaseAreaForecastPersistenceError(
            "AREA_FORECAST_PERSISTENCE_INTEGRITY_ERROR", "RESULT_RELOAD_FAILED"
        ) from exc
    return result


def save_base_forecast_result(path: Path, result: AreaForecastProductResult) -> None:
    """Persist an immutable canonical result document; never overwrite a different result."""

    _check_result_integrity(result)
    payload = result.model_dump(mode="json")
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    try:
        if path.exists():
            existing = reload_base_forecast_result(json.loads(path.read_text(encoding="utf-8")))
            if existing.model_dump(mode="json") != payload:
                raise BaseAreaForecastPersistenceError(
                    "AREA_FORECAST_PERSISTENCE_CONFLICT", "IMMUTABLE_RESULT_CONFLICT"
                )
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(serialized + "\n", encoding="utf-8")
    except BaseAreaForecastPersistenceError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BaseAreaForecastPersistenceError(
            "AREA_FORECAST_PERSISTENCE_WRITE_ERROR", "RESULT_DOCUMENT_UNAVAILABLE"
        ) from exc


def load_saved_base_forecast_result(path: Path) -> AreaForecastProductResult:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BaseAreaForecastPersistenceError(
            "AREA_FORECAST_PERSISTENCE_READ_ERROR", "RESULT_DOCUMENT_UNAVAILABLE"
        ) from exc
    if not isinstance(payload, Mapping):
        raise BaseAreaForecastPersistenceError(
            "AREA_FORECAST_PERSISTENCE_INTEGRITY_ERROR", "RESULT_PAYLOAD_INVALID"
        )
    return reload_base_forecast_result(payload)


def run_base_area_forecast(
    request: AreaForecastProductRequest,
) -> AreaForecastProductResult:
    """Convenience boundary for transports; authority is always operator-owned."""

    authority = load_base_product_authority()
    return forecast_base_area(request, authority)
