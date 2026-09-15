"""Deterministic no-weather operational peak-window forecast policy.

This module is the S5 domain/service boundary.  It consumes a frozen
``AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1`` profile and a registered base
snapshot; it does not train, access a database, load weather, or reconstruct a
full-season total.  The only quantity calculation is the authority area's
daily kg/mu profile multiplied by the registered base area.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Any

BASELINE_ID = "AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1"
POLICY_VERSION = "OPERATIONAL_PEAK_POLICY_V1"
LOCAL_TIMEZONE = "Asia/Shanghai"
BUSINESS_CUTOFF = "04-15_INCLUSIVE"
PEAK_TIE_BREAK = "EARLIEST_DATE"
WEATHER_USED = False
MISSING_BIN_POLICY = "NEAREST_AVAILABLE_TRAIN_BIN_EARLIER_TIE"
_SEASON_PATTERN = re.compile(r"^(?P<start>\d{4})-(?P<end>\d{4})$")
_KG_QUANTUM = Decimal("0.000001")
_PROFILE_QUANTUM = Decimal("0.000000000001")

COMPUTABLE_FULL_WINDOW = "COMPUTABLE_FULL_WINDOW"
NOT_COMPUTABLE_FULL_WINDOW = "NOT_COMPUTABLE_FULL_WINDOW"
COMPUTABLE_REMAINING_WINDOW = "COMPUTABLE_REMAINING_BUSINESS_WINDOW"
NO_REMAINING_WINDOW = "NO_REMAINING_BUSINESS_DAYS"


class OperationalPeakForecastError(ValueError):
    """Machine-readable fail-closed error raised at the S5 boundary."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.reason = message
        super().__init__(f"{code}: {message}")


def _decimal(value: Any, *, code: str, label: str) -> Decimal:
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise OperationalPeakForecastError(code, f"{label} must be a decimal") from exc
    if not number.is_finite():
        raise OperationalPeakForecastError(code, f"{label} must be finite")
    return number


def _positive_decimal(value: Any, *, code: str, label: str) -> Decimal:
    number = _decimal(value, code=code, label=label)
    if number <= 0:
        raise OperationalPeakForecastError(code, f"{label} must be positive")
    return number


def _nonnegative_decimal(value: Any, *, code: str, label: str) -> Decimal:
    number = _decimal(value, code=code, label=label)
    if number < 0:
        raise OperationalPeakForecastError(code, f"{label} must be non-negative")
    return number


def _fixed(value: Decimal, quantum: Decimal = _KG_QUANTUM) -> str:
    return format(value.quantize(quantum, rounding=ROUND_HALF_EVEN), "f")


def _date_value(value: Any, *, code: str, label: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise OperationalPeakForecastError(code, f"{label} must be ISO date") from exc
    raise OperationalPeakForecastError(code, f"{label} must be ISO date")


@dataclass(frozen=True, slots=True)
class RegisteredBase:
    """The minimum immutable base authority needed by S5."""

    base_id: str
    canonical_base_name: str
    productive_area_mu: Decimal
    area_basis: str | None = None
    active: bool = True

    def __post_init__(self) -> None:
        if not self.base_id or not self.canonical_base_name:
            raise OperationalPeakForecastError(
                "INVALID_BASE_AUTHORITY", "base_id and canonical_base_name are required"
            )
        _positive_decimal(
            self.productive_area_mu,
            code="INVALID_BASE_AUTHORITY",
            label="productive_area_mu",
        )
        if not self.active:
            raise OperationalPeakForecastError(
                "UNREGISTERED_BASE", "base is inactive in the supplied registry"
            )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> RegisteredBase:
        try:
            base_id = str(value["base_id"])
            name = str(value["canonical_base_name"])
            area = _positive_decimal(
                value["productive_area_mu"],
                code="INVALID_BASE_AUTHORITY",
                label="productive_area_mu",
            )
        except KeyError as exc:
            raise OperationalPeakForecastError(
                "INVALID_BASE_AUTHORITY", f"missing base field: {exc.args[0]}"
            ) from exc
        return cls(
            base_id=base_id,
            canonical_base_name=name,
            productive_area_mu=area,
            area_basis=str(value["area_basis"]) if value.get("area_basis") is not None else None,
            active=bool(value.get("active", True)),
        )


def _registry_entries(registry: Any) -> tuple[Mapping[str, Any], ...]:
    raw: Any = registry
    if isinstance(registry, Mapping) and "bases" in registry:
        raw = registry["bases"]
    if isinstance(raw, Mapping):
        entries: list[Mapping[str, Any]] = []
        for key, item in raw.items():
            if not isinstance(item, Mapping):
                continue
            copied = dict(item)
            copied.setdefault("base_id", str(key))
            entries.append(copied)
        return tuple(entries)
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        return tuple(item for item in raw if isinstance(item, Mapping))
    raise OperationalPeakForecastError(
        "INVALID_BASE_AUTHORITY", "registry bases are not a collection"
    )


def resolve_registered_base(registry: Any, base_id: str) -> RegisteredBase:
    """Resolve only an exact registered ID or exact canonical name.

    The canonical-name branch exists for callers that already possess an
    authority name.  It is exact and ambiguity-safe; no fuzzy or geographic
    matching is performed.
    """

    if not isinstance(base_id, str) or not base_id.strip():
        raise OperationalPeakForecastError("UNREGISTERED_BASE", "base identity is required")
    entries = _registry_entries(registry)
    id_matches = [item for item in entries if item.get("base_id") == base_id]
    matches = id_matches or [item for item in entries if item.get("canonical_base_name") == base_id]
    if len(matches) != 1:
        raise OperationalPeakForecastError("UNREGISTERED_BASE", "base identity is not registered")
    return RegisteredBase.from_mapping(matches[0])


def parse_business_season(season: str) -> tuple[int, int]:
    if not isinstance(season, str):
        raise OperationalPeakForecastError("INVALID_REQUEST", "target_season must be YYYY-YYYY")
    match = _SEASON_PATTERN.fullmatch(season)
    if match is None or int(match["end"]) != int(match["start"]) + 1:
        raise OperationalPeakForecastError(
            "INVALID_REQUEST", "target_season must be consecutive years"
        )
    return int(match["start"]), int(match["end"])


def business_season_window(season: str) -> tuple[date, date]:
    start_year, end_year = parse_business_season(season)
    return date(start_year, 7, 1), date(end_year, 4, 15)


season_window = business_season_window


def dates_between(start: date, end: date) -> tuple[date, ...]:
    if end < start:
        return ()
    return tuple(start + timedelta(days=offset) for offset in range((end - start).days + 1))


@dataclass(frozen=True, slots=True)
class OperationalPeakForecastRequest:
    base_id: str
    target_season: str
    origin_date: date

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> OperationalPeakForecastRequest:
        try:
            base_id = value["base_id"]
            season = value["target_season"]
            origin = value["origin_date"]
        except KeyError as exc:
            raise OperationalPeakForecastError(
                "INVALID_REQUEST", f"missing request field: {exc.args[0]}"
            ) from exc
        if not isinstance(base_id, str) or not base_id:
            raise OperationalPeakForecastError("INVALID_REQUEST", "base_id is required")
        if not isinstance(season, str):
            raise OperationalPeakForecastError("INVALID_REQUEST", "target_season is required")
        return cls(
            base_id=base_id,
            target_season=season,
            origin_date=_date_value(origin, code="INVALID_REQUEST", label="origin_date"),
        )


@dataclass(frozen=True, slots=True)
class DailyForecast:
    date: date
    predicted_kg: Decimal
    kg_per_mu: Decimal
    business_season_day_index: int
    reference_bin: int

    def __post_init__(self) -> None:
        _nonnegative_decimal(
            self.predicted_kg,
            code="INVALID_DAILY_PREDICTION",
            label="predicted_kg",
        )
        _nonnegative_decimal(
            self.kg_per_mu,
            code="INVALID_DAILY_PREDICTION",
            label="kg_per_mu",
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "date": self.date.isoformat(),
            "predicted_kg": _fixed(self.predicted_kg),
            "kg_per_mu": _fixed(self.kg_per_mu, _PROFILE_QUANTUM),
            "business_season_day_index": self.business_season_day_index,
            "reference_bin": self.reference_bin,
        }


@dataclass(frozen=True, slots=True)
class PeakWindowForecast:
    window_days: int | None
    status: str
    start_date: date | None
    end_date: date | None
    total_kg: Decimal | None
    peak_date: date | None
    peak_kg: Decimal | None
    available_days: int
    reason: str | None = None

    def to_mapping(self) -> dict[str, Any]:
        return {
            "window_days": self.window_days,
            "status": self.status,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "total_kg": _fixed(self.total_kg) if self.total_kg is not None else None,
            "peak_date": self.peak_date.isoformat() if self.peak_date else None,
            "peak_kg": _fixed(self.peak_kg) if self.peak_kg is not None else None,
            "available_days": self.available_days,
            "reason": self.reason,
        }


type DailyRowInput = DailyForecast | Mapping[str, Any]


def _coerce_daily_row(value: DailyRowInput) -> DailyForecast:
    if isinstance(value, DailyForecast):
        return value
    if not isinstance(value, Mapping):
        raise OperationalPeakForecastError(
            "INVALID_DAILY_PREDICTION", "daily prediction must be a row or mapping"
        )
    try:
        row_date = _date_value(value["date"], code="INVALID_DAILY_PREDICTION", label="date")
        predicted = _nonnegative_decimal(
            value["predicted_kg"], code="INVALID_DAILY_PREDICTION", label="predicted_kg"
        )
        kg_per_mu = _nonnegative_decimal(
            value.get("kg_per_mu", "0"),
            code="INVALID_DAILY_PREDICTION",
            label="kg_per_mu",
        )
        index = int(value.get("business_season_day_index", 0))
        reference_bin = int(value.get("reference_bin", 0))
    except (KeyError, TypeError, ValueError) as exc:
        raise OperationalPeakForecastError(
            "INVALID_DAILY_PREDICTION", "daily prediction fields are malformed"
        ) from exc
    return DailyForecast(row_date, predicted, kg_per_mu, index, reference_bin)


def _peak(rows: Sequence[DailyForecast]) -> tuple[date, Decimal]:
    if not rows:
        raise OperationalPeakForecastError("INVALID_DAILY_PREDICTION", "peak requires daily rows")
    selected = min(rows, key=lambda row: (-row.predicted_kg, row.date))
    return selected.date, selected.predicted_kg


def summarize_window(
    rows: Sequence[DailyRowInput],
    *,
    origin_date: date,
    window_days: int,
    business_start: date,
    business_end: date,
) -> PeakWindowForecast:
    """Summarize a complete future window without silently shortening it."""

    if window_days not in {7, 15}:
        raise OperationalPeakForecastError("INVALID_REQUEST", "window_days must be 7 or 15")
    expected = dates_between(
        origin_date + timedelta(days=1), origin_date + timedelta(days=window_days)
    )
    converted = tuple(_coerce_daily_row(row) for row in rows)
    by_date: dict[date, DailyForecast] = {}
    duplicate = False
    for row in converted:
        if row.date in by_date:
            duplicate = True
        by_date[row.date] = row
    in_scope = tuple(day for day in expected if business_start <= day <= business_end)
    available = sum(day in by_date for day in in_scope)
    start = expected[0]
    end = expected[-1]
    if duplicate:
        return PeakWindowForecast(
            window_days,
            NOT_COMPUTABLE_FULL_WINDOW,
            start,
            end,
            None,
            None,
            None,
            available,
            "DUPLICATE_DAILY_PREDICTION",
        )
    if end > business_end or start < business_start:
        return PeakWindowForecast(
            window_days,
            NOT_COMPUTABLE_FULL_WINDOW,
            start,
            end,
            None,
            None,
            None,
            available,
            "BUSINESS_SEASON_WINDOW_EXCEEDED",
        )
    selected = tuple(by_date[day] for day in expected if day in by_date)
    if len(selected) != len(expected):
        return PeakWindowForecast(
            window_days,
            NOT_COMPUTABLE_FULL_WINDOW,
            start,
            end,
            None,
            None,
            None,
            available,
            "MISSING_DAILY_PREDICTION",
        )
    peak_date, peak_kg = _peak(selected)
    return PeakWindowForecast(
        window_days,
        COMPUTABLE_FULL_WINDOW,
        start,
        end,
        sum((row.predicted_kg for row in selected), Decimal(0)),
        peak_date,
        peak_kg,
        len(selected),
    )


def _remaining_window(rows: Sequence[DailyForecast]) -> PeakWindowForecast:
    if not rows:
        return PeakWindowForecast(None, NO_REMAINING_WINDOW, None, None, None, None, None, 0)
    peak_date, peak_kg = _peak(rows)
    return PeakWindowForecast(
        None,
        COMPUTABLE_REMAINING_WINDOW,
        rows[0].date,
        rows[-1].date,
        sum((row.predicted_kg for row in rows), Decimal(0)),
        peak_date,
        peak_kg,
        len(rows),
    )


@dataclass(frozen=True, slots=True)
class OperationalPeakForecastResult:
    base_id: str
    canonical_base_name: str
    productive_area_mu: Decimal
    area_basis: str | None
    target_season: str
    origin_date: date
    business_season_start: date
    business_season_end: date
    daily_forecast: tuple[DailyForecast, ...]
    forecast_7d: PeakWindowForecast
    forecast_15d: PeakWindowForecast
    remaining_business_window: PeakWindowForecast
    baseline_id: str = BASELINE_ID
    policy_version: str = POLICY_VERSION
    weather_used: bool = WEATHER_USED
    weather: None = None
    limitations: tuple[str, ...] = (
        "NO_WEATHER_FEATURES",
        "NOT_FULL_SEASON_TOTAL_FORECAST",
        "BASE_PRODUCTIVE_AREA_AUTHORITY_ONLY",
        "FULL_WINDOW_REQUIRED_FOR_W7_W15",
    )
    result_hash: str = ""

    def payload(self) -> dict[str, Any]:
        return {
            "base_id": self.base_id,
            "canonical_base_name": self.canonical_base_name,
            "productive_area_mu": _fixed(self.productive_area_mu),
            "area_basis": self.area_basis,
            "target_season": self.target_season,
            "origin_date": self.origin_date.isoformat(),
            "business_season_start": self.business_season_start.isoformat(),
            "business_season_end": self.business_season_end.isoformat(),
            "daily_forecast": [row.to_mapping() for row in self.daily_forecast],
            "forecast_7d": self.forecast_7d.to_mapping(),
            "forecast_15d": self.forecast_15d.to_mapping(),
            "remaining_business_window": self.remaining_business_window.to_mapping(),
            "baseline_id": self.baseline_id,
            "policy_version": self.policy_version,
            "weather_used": self.weather_used,
            "weather": self.weather,
            "limitations": list(self.limitations),
        }

    def to_mapping(self) -> dict[str, Any]:
        return {**self.payload(), "result_hash": self.result_hash}


def canonical_result_hash(result: OperationalPeakForecastResult) -> str:
    payload = json.dumps(
        result.payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_frozen_reference_profile(payload: Mapping[str, Any]) -> dict[int, Decimal]:
    if payload.get("reference_id") != BASELINE_ID:
        raise OperationalPeakForecastError(
            "REFERENCE_PROFILE_UNAVAILABLE", "unexpected frozen reference profile"
        )
    if payload.get("validation_labels_used") is not False:
        raise OperationalPeakForecastError(
            "REFERENCE_PROFILE_UNAVAILABLE", "reference profile must be frozen before validation"
        )
    if payload.get("missing_bin_policy") != MISSING_BIN_POLICY:
        raise OperationalPeakForecastError(
            "REFERENCE_PROFILE_UNAVAILABLE", "reference profile policy is not frozen"
        )
    raw = payload.get("profile_kg_per_mu_by_7_day_bin")
    if not isinstance(raw, Mapping) or not raw:
        raise OperationalPeakForecastError(
            "REFERENCE_PROFILE_UNAVAILABLE", "reference profile has no bins"
        )
    return _coerce_profile(raw)


def _coerce_profile(profile: Mapping[Any, Any]) -> dict[int, Decimal]:
    result: dict[int, Decimal] = {}
    for raw_bin, raw_value in profile.items():
        try:
            bin_id = int(raw_bin)
        except (TypeError, ValueError) as exc:
            raise OperationalPeakForecastError(
                "REFERENCE_PROFILE_UNAVAILABLE", "reference bin is not an integer"
            ) from exc
        if bin_id < 0:
            raise OperationalPeakForecastError(
                "REFERENCE_PROFILE_UNAVAILABLE", "reference bin must be non-negative"
            )
        if bin_id in result:
            raise OperationalPeakForecastError(
                "REFERENCE_PROFILE_UNAVAILABLE", "duplicate reference bin"
            )
        result[bin_id] = _nonnegative_decimal(
            raw_value, code="REFERENCE_PROFILE_UNAVAILABLE", label="profile value"
        )
    if not result:
        raise OperationalPeakForecastError(
            "REFERENCE_PROFILE_UNAVAILABLE", "reference profile has no bins"
        )
    return result


def nearest_reference_bin(target_bin: int, available_bins: Sequence[int]) -> int:
    if not available_bins:
        raise OperationalPeakForecastError(
            "REFERENCE_PROFILE_UNAVAILABLE", "reference profile has no bins"
        )
    return min(available_bins, key=lambda candidate: (abs(candidate - target_bin), candidate))


def _daily_row(
    target_date: date,
    season_start: date,
    area: Decimal,
    profile: Mapping[int, Decimal],
) -> DailyForecast:
    day_index = (target_date - season_start).days
    target_bin = day_index // 7
    selected_bin = nearest_reference_bin(target_bin, sorted(profile))
    kg_per_mu = profile[selected_bin]
    return DailyForecast(
        date=target_date,
        predicted_kg=(area * kg_per_mu).quantize(_KG_QUANTUM, rounding=ROUND_HALF_EVEN),
        kg_per_mu=kg_per_mu,
        business_season_day_index=day_index,
        reference_bin=selected_bin,
    )


def forecast_operational_peak(
    request: OperationalPeakForecastRequest,
    registry: Any,
    reference_profile: Mapping[Any, Any],
) -> OperationalPeakForecastResult:
    """Generate the frozen S5 forecast for one registered base and origin."""

    if not isinstance(request, OperationalPeakForecastRequest):
        raise OperationalPeakForecastError("INVALID_REQUEST", "request type is invalid")
    season_start, season_end = business_season_window(request.target_season)
    origin = _date_value(request.origin_date, code="INVALID_REQUEST", label="origin_date")
    if origin < season_start or origin > season_end:
        raise OperationalPeakForecastError(
            "INVALID_REQUEST", "origin_date must be inside the business season"
        )
    base = resolve_registered_base(registry, request.base_id)
    profile = _coerce_profile(reference_profile)
    first_target = origin + timedelta(days=1)
    daily_end = min(origin + timedelta(days=15), season_end)
    daily_dates = dates_between(first_target, daily_end)
    daily_rows = tuple(
        _daily_row(day, season_start, base.productive_area_mu, profile) for day in daily_dates
    )
    remaining_dates = dates_between(first_target, season_end)
    remaining_rows = tuple(
        _daily_row(day, season_start, base.productive_area_mu, profile) for day in remaining_dates
    )
    result = OperationalPeakForecastResult(
        base_id=base.base_id,
        canonical_base_name=base.canonical_base_name,
        productive_area_mu=base.productive_area_mu,
        area_basis=base.area_basis,
        target_season=request.target_season,
        origin_date=origin,
        business_season_start=season_start,
        business_season_end=season_end,
        daily_forecast=daily_rows,
        forecast_7d=summarize_window(
            daily_rows,
            origin_date=origin,
            window_days=7,
            business_start=season_start,
            business_end=season_end,
        ),
        forecast_15d=summarize_window(
            daily_rows,
            origin_date=origin,
            window_days=15,
            business_start=season_start,
            business_end=season_end,
        ),
        remaining_business_window=_remaining_window(remaining_rows),
    )
    return replace(result, result_hash=canonical_result_hash(result))


build_operational_peak_forecast = forecast_operational_peak
