"""Leakage-safe, deterministic weather feature contracts for V0.7-S2.

This module consumes the accepted ERA5-Land daily projection only.  It does
not call a provider, read a database, fit a model, or turn realized weather
into an as-issued forecast.  The public builder is deliberately limited to
Lane A (past observed weather); Lane B and Lane C are represented as explicit
contracts so callers cannot silently mix their semantics.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from backend.app.area_yield.data import digest

WEATHER_FEATURE_POLICY_VERSION = "V0_7_S2_LEAKAGE_SAFE_PAST_OBSERVED_V1"
WEATHER_SOURCE = "ERA5_LAND"
WEATHER_ROLE = "HISTORICAL_REALIZED_OBSERVATION"
ORIGIN_POLICY = "ROLLING_DAILY_LOCAL_DAY_START"
ORIGIN_TIMEZONE = "Asia/Shanghai"
PRIMARY_WINDOWS_DAYS = (7, 14, 30)
PRIMARY_HORIZONS = {"H1": 1, "H7": 7, "H15": 15}
PRIMARY_FEATURE_COUNT = len(PRIMARY_WINDOWS_DAYS) * 6
ORACLE_LANE = "FUTURE_REALIZED_ORACLE"
LANE_A = "PAST_OBSERVED_WEATHER"
LANE_B = "AS_ISSUED_FORECAST_WEATHER"
LANE_C = ORACLE_LANE

_TZ = ZoneInfo(ORIGIN_TIMEZONE)
_VALUE_QUANTUM = Decimal("0.000000000001")


class WeatherFeatureError(ValueError):
    """Raised when weather provenance, visibility, or coverage is invalid."""


def _finite_decimal(value: Any, field: str) -> Decimal:
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise WeatherFeatureError(f"INVALID_WEATHER_VALUE:{field}") from exc
    if not decimal.is_finite():
        raise WeatherFeatureError(f"NONFINITE_WEATHER_VALUE:{field}")
    return decimal


def _value_text(value: Decimal) -> str:
    if not value.is_finite():
        raise WeatherFeatureError("NONFINITE_FEATURE_VALUE")
    return format(value.quantize(_VALUE_QUANTUM, rounding=ROUND_HALF_EVEN), "f")


def validate_weather_lane(
    *, lane: str, source: str, role: str, research_only: bool = False
) -> None:
    """Validate the source/role identity for one of the three weather lanes."""

    expected = {
        LANE_A: (WEATHER_SOURCE, WEATHER_ROLE),
        LANE_B: ("ECMWF_IFS_OPEN_DATA", "AS_ISSUED_FORECAST"),
        LANE_C: (WEATHER_SOURCE, ORACLE_LANE),
    }
    if lane not in expected:
        raise WeatherFeatureError("UNKNOWN_WEATHER_LANE")
    if (source, role) != expected[lane]:
        raise WeatherFeatureError("WEATHER_SOURCE_ROLE_MISMATCH")
    if lane == LANE_C and not research_only:
        raise WeatherFeatureError("ORACLE_WEATHER_REQUIRES_RESEARCH_ONLY")
    if lane != LANE_C and research_only:
        raise WeatherFeatureError("RESEARCH_ONLY_FLAG_INVALID_FOR_NON_ORACLE")


@dataclass(frozen=True, slots=True)
class WeatherDailyObservation:
    """One accepted daily row from ``BASE_WEATHER_DAILY_V1``."""

    base_id: str
    local_date: date
    mean_temperature_c: Decimal
    tmin_c: Decimal
    tmax_c: Decimal
    precipitation_mm: Decimal
    solar_energy_j_m2: Decimal
    wind_speed_m_s: Decimal
    source_row_hash: str
    source_dataset_hash: str

    def payload(self) -> dict[str, str]:
        return {
            "base_id": self.base_id,
            "local_date": self.local_date.isoformat(),
            "mean_temperature_c": _value_text(self.mean_temperature_c),
            "tmin_c": _value_text(self.tmin_c),
            "tmax_c": _value_text(self.tmax_c),
            "precipitation_mm": _value_text(self.precipitation_mm),
            "solar_energy_j_m2": _value_text(self.solar_energy_j_m2),
            "wind_speed_m_s": _value_text(self.wind_speed_m_s),
            "source_row_hash": self.source_row_hash,
            "source_dataset_hash": self.source_dataset_hash,
        }


def observation_from_daily_payload(
    payload: Mapping[str, Any], *, source_dataset_hash: str
) -> WeatherDailyObservation:
    """Parse the frozen daily JSONL schema without accepting alternate units."""

    if payload.get("processing_version") != "BASE_WEATHER_DAILY_V1":
        raise WeatherFeatureError("UNAUTHORIZED_DAILY_WEATHER_LAYER")
    if payload.get("hourly_sample_count") != 24:
        raise WeatherFeatureError("INCOMPLETE_LOCAL_DAY")
    base_id = str(payload.get("base_id", ""))
    row_hash = str(payload.get("row_hash", ""))
    if not base_id or not row_hash or len(source_dataset_hash) != 64:
        raise WeatherFeatureError("DAILY_WEATHER_IDENTITY_MISSING")
    try:
        local_date = date.fromisoformat(str(payload["local_date"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise WeatherFeatureError("INVALID_LOCAL_DATE") from exc
    return WeatherDailyObservation(
        base_id=base_id,
        local_date=local_date,
        mean_temperature_c=_finite_decimal(
            payload.get("local_day_mean_temperature_c"), "mean_temperature_c"
        ),
        tmin_c=_finite_decimal(payload.get("sampled_local_day_tmin_c"), "tmin_c"),
        tmax_c=_finite_decimal(payload.get("sampled_local_day_tmax_c"), "tmax_c"),
        precipitation_mm=_finite_decimal(
            payload.get("local_day_precipitation_mm"), "precipitation_mm"
        ),
        solar_energy_j_m2=_finite_decimal(
            payload.get("local_day_solar_energy_j_m2"), "solar_energy_j_m2"
        ),
        wind_speed_m_s=_finite_decimal(
            payload.get("local_day_mean_wind_speed_10m_m_s"), "wind_speed_m_s"
        ),
        source_row_hash=row_hash,
        source_dataset_hash=source_dataset_hash,
    )


def load_era5_daily_jsonl(
    path: Path, *, source_dataset_hash: str
) -> tuple[WeatherDailyObservation, ...]:
    """Load and validate the accepted private daily artifact.

    The path is supplied by the operator; no private absolute path is embedded
    in the repository.  Duplicate Base/date rows fail closed.
    """

    rows: list[WeatherDailyObservation] = []
    seen: set[tuple[str, date]] = set()
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise WeatherFeatureError(f"INVALID_DAILY_JSON:{line_number}") from exc
            if not isinstance(payload, Mapping):
                raise WeatherFeatureError(f"DAILY_ROW_NOT_OBJECT:{line_number}")
            observation = observation_from_daily_payload(
                payload, source_dataset_hash=source_dataset_hash
            )
            key = (observation.base_id, observation.local_date)
            if key in seen:
                raise WeatherFeatureError(f"DUPLICATE_DAILY_WEATHER_ROW:{key[0]}:{key[1]}")
            seen.add(key)
            rows.append(observation)
    return tuple(sorted(rows, key=lambda item: (item.base_id, item.local_date)))


def _local_origin(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise WeatherFeatureError("FORECAST_ORIGIN_MUST_BE_TIMEZONE_AWARE")
    local = value.astimezone(_TZ)
    if local.time() != time.min:
        raise WeatherFeatureError("FORECAST_ORIGIN_NOT_LOCAL_DAY_START")
    return local


def validate_observation_visibility(
    observations: Iterable[WeatherDailyObservation], *, forecast_origin: datetime
) -> None:
    """Reject an explicitly supplied realized row at or after the origin."""

    local_origin = _local_origin(forecast_origin)
    for observation in observations:
        if observation.local_date >= local_origin.date():
            raise WeatherFeatureError("FUTURE_REALIZED_WEATHER_NOT_VISIBLE")


def season_to_date_visible_observations(
    observations: Iterable[WeatherDailyObservation],
    *,
    season_start: date,
    forecast_origin: datetime,
) -> tuple[WeatherDailyObservation, ...]:
    """Return a deterministic past-only season-to-date view for diagnostics."""

    local_origin = _local_origin(forecast_origin)
    if season_start >= local_origin.date():
        raise WeatherFeatureError("INVALID_SEASON_TO_DATE_START")
    visible = [
        observation
        for observation in observations
        if season_start <= observation.local_date < local_origin.date()
    ]
    return tuple(sorted(visible, key=lambda item: (item.base_id, item.local_date)))


@dataclass(frozen=True, slots=True)
class WeatherFeatureRow:
    """Canonical, leakage-checked feature row for one origin and target window."""

    base_id: str
    forecast_origin: str
    target_start: date
    target_end: date
    feature_window_start: date
    feature_window_end: date
    max_source_observation_time: str
    weather_lane: str
    weather_source: str
    weather_role: str
    source_dataset_hash: str
    feature_policy_version: str
    feature_values: tuple[tuple[str, str], ...]
    source_observation_count: int
    feature_hash: str

    @property
    def features(self) -> dict[str, str]:
        return dict(self.feature_values)

    def payload_without_hash(self) -> dict[str, Any]:
        return {
            "base_id": self.base_id,
            "forecast_origin": self.forecast_origin,
            "target_start": self.target_start.isoformat(),
            "target_end": self.target_end.isoformat(),
            "feature_window_start": self.feature_window_start.isoformat(),
            "feature_window_end": self.feature_window_end.isoformat(),
            "max_source_observation_time": self.max_source_observation_time,
            "weather_lane": self.weather_lane,
            "weather_source": self.weather_source,
            "weather_role": self.weather_role,
            "source_dataset_hash": self.source_dataset_hash,
            "feature_policy_version": self.feature_policy_version,
            "features": self.features,
            "source_observation_count": self.source_observation_count,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self.payload_without_hash()
        payload["feature_hash"] = self.feature_hash
        return payload


def _mean(values: Sequence[Decimal]) -> Decimal:
    if not values:
        raise WeatherFeatureError("EMPTY_FEATURE_WINDOW")
    return sum(values, Decimal(0)) / Decimal(len(values))


def _observation_index(
    observations: Iterable[WeatherDailyObservation],
) -> dict[tuple[str, date], WeatherDailyObservation]:
    result: dict[tuple[str, date], WeatherDailyObservation] = {}
    for observation in observations:
        key = (observation.base_id, observation.local_date)
        if key in result:
            raise WeatherFeatureError(f"DUPLICATE_DAILY_WEATHER_ROW:{key[0]}:{key[1]}")
        result[key] = observation
    return result


def build_feature_row(
    *,
    observations: Iterable[WeatherDailyObservation],
    base_id: str,
    forecast_origin: datetime,
    target_start: date,
    target_end: date,
    source_dataset_hash: str,
    feature_policy_version: str = WEATHER_FEATURE_POLICY_VERSION,
) -> WeatherFeatureRow:
    """Build a primary Lane-A row using only completed local days before origin."""

    local_origin = _local_origin(forecast_origin)
    if target_start < local_origin.date() or target_end < target_start:
        raise WeatherFeatureError("TARGET_WINDOW_NOT_AFTER_ORIGIN")
    horizon_days = (target_end - target_start).days + 1
    if horizon_days not in PRIMARY_HORIZONS.values() or target_start != local_origin.date():
        raise WeatherFeatureError("UNSUPPORTED_TARGET_HORIZON")
    validate_weather_lane(lane=LANE_A, source=WEATHER_SOURCE, role=WEATHER_ROLE)
    if len(source_dataset_hash) != 64:
        raise WeatherFeatureError("SOURCE_DATASET_HASH_INVALID")

    index = _observation_index(observations)
    cutoff = local_origin.date() - timedelta(days=1)
    all_feature_values: dict[str, str] = {}
    total_source_count = 0
    for window_days in PRIMARY_WINDOWS_DAYS:
        window_start = cutoff - timedelta(days=window_days - 1)
        window = [
            index.get((base_id, window_start + timedelta(days=offset)))
            for offset in range(window_days)
        ]
        if any(item is None for item in window):
            raise WeatherFeatureError("HISTORICAL_WEATHER_WINDOW_INCOMPLETE")
        resolved = [item for item in window if item is not None]
        if any(item.local_date >= local_origin.date() for item in resolved):
            raise WeatherFeatureError("FUTURE_REALIZED_WEATHER_NOT_VISIBLE")
        total_source_count += len(resolved)
        prefix = f"w{window_days}_"
        all_feature_values[f"{prefix}mean_temperature_c"] = _value_text(
            _mean([item.mean_temperature_c for item in resolved])
        )
        all_feature_values[f"{prefix}mean_tmin_c"] = _value_text(
            _mean([item.tmin_c for item in resolved])
        )
        all_feature_values[f"{prefix}mean_tmax_c"] = _value_text(
            _mean([item.tmax_c for item in resolved])
        )
        all_feature_values[f"{prefix}precipitation_sum_mm"] = _value_text(
            sum((item.precipitation_mm for item in resolved), Decimal(0))
        )
        all_feature_values[f"{prefix}solar_radiation_mean_mj_m2"] = _value_text(
            _mean([item.solar_energy_j_m2 / Decimal("1000000") for item in resolved])
        )
        all_feature_values[f"{prefix}wind_speed_mean_m_s"] = _value_text(
            _mean([item.wind_speed_m_s for item in resolved])
        )

    feature_window_start = cutoff - timedelta(days=max(PRIMARY_WINDOWS_DAYS) - 1)
    max_source_time = datetime.combine(cutoff, time.max, tzinfo=_TZ)
    origin_text = local_origin.isoformat()
    payload = {
        "base_id": base_id,
        "forecast_origin": origin_text,
        "target_start": target_start.isoformat(),
        "target_end": target_end.isoformat(),
        "feature_window_start": feature_window_start.isoformat(),
        "feature_window_end": cutoff.isoformat(),
        "max_source_observation_time": max_source_time.isoformat(),
        "weather_lane": LANE_A,
        "weather_source": WEATHER_SOURCE,
        "weather_role": WEATHER_ROLE,
        "source_dataset_hash": source_dataset_hash,
        "feature_policy_version": feature_policy_version,
        "features": dict(sorted(all_feature_values.items())),
        "source_observation_count": total_source_count,
    }
    feature_hash = digest(payload)
    row = WeatherFeatureRow(
        base_id=base_id,
        forecast_origin=origin_text,
        target_start=target_start,
        target_end=target_end,
        feature_window_start=feature_window_start,
        feature_window_end=cutoff,
        max_source_observation_time=max_source_time.isoformat(),
        weather_lane=LANE_A,
        weather_source=WEATHER_SOURCE,
        weather_role=WEATHER_ROLE,
        source_dataset_hash=source_dataset_hash,
        feature_policy_version=feature_policy_version,
        feature_values=tuple(sorted(all_feature_values.items())),
        source_observation_count=total_source_count,
        feature_hash=feature_hash,
    )
    validate_feature_row(row)
    return row


def validate_feature_row(row: WeatherFeatureRow) -> None:
    """Validate persisted row identity and the strict past-weather cutoff."""

    origin = _local_origin(datetime.fromisoformat(row.forecast_origin))
    max_source = datetime.fromisoformat(row.max_source_observation_time)
    if max_source >= origin:
        raise WeatherFeatureError("FEATURE_SOURCE_NOT_BEFORE_ORIGIN")
    if row.weather_lane != LANE_A:
        raise WeatherFeatureError("PRIMARY_FEATURE_ROW_MUST_USE_LANE_A")
    validate_weather_lane(
        lane=row.weather_lane,
        source=row.weather_source,
        role=row.weather_role,
    )
    if digest(row.payload_without_hash()) != row.feature_hash:
        raise WeatherFeatureError("FEATURE_HASH_MISMATCH")


def build_feature_manifest(
    rows: Iterable[WeatherFeatureRow],
    *,
    source_dataset_hash: str,
    feature_policy_version: str = WEATHER_FEATURE_POLICY_VERSION,
) -> dict[str, Any]:
    """Build a stable manifest over sorted feature rows."""

    sorted_rows = sorted(
        rows,
        key=lambda row: (row.base_id, row.forecast_origin, row.target_start, row.target_end),
    )
    if any(row.source_dataset_hash != source_dataset_hash for row in sorted_rows):
        raise WeatherFeatureError("FEATURE_SOURCE_HASH_MISMATCH")
    payload = {
        "feature_policy_version": feature_policy_version,
        "weather_lane": LANE_A,
        "weather_source": WEATHER_SOURCE,
        "weather_role": WEATHER_ROLE,
        "source_dataset_hash": source_dataset_hash,
        "row_count": len(sorted_rows),
        "feature_hashes": [row.feature_hash for row in sorted_rows],
    }
    return {**payload, "manifest_hash": digest(payload)}


def replay_feature_manifest(
    rows: Iterable[WeatherFeatureRow],
    *,
    source_dataset_hash: str,
    feature_policy_version: str = WEATHER_FEATURE_POLICY_VERSION,
) -> dict[str, Any]:
    """Alias used by offline replay runners to make the replay intent explicit."""

    return build_feature_manifest(
        rows,
        source_dataset_hash=source_dataset_hash,
        feature_policy_version=feature_policy_version,
    )


__all__ = [
    "LANE_A",
    "LANE_B",
    "LANE_C",
    "ORACLE_LANE",
    "ORIGIN_POLICY",
    "ORIGIN_TIMEZONE",
    "PRIMARY_FEATURE_COUNT",
    "PRIMARY_FEATURES",
    "PRIMARY_HORIZONS",
    "PRIMARY_WINDOWS_DAYS",
    "WEATHER_FEATURE_POLICY_VERSION",
    "WEATHER_ROLE",
    "WEATHER_SOURCE",
    "WeatherDailyObservation",
    "WeatherFeatureError",
    "WeatherFeatureRow",
    "build_feature_manifest",
    "build_feature_row",
    "load_era5_daily_jsonl",
    "observation_from_daily_payload",
    "replay_feature_manifest",
    "season_to_date_visible_observations",
    "validate_feature_row",
    "validate_observation_visibility",
    "validate_weather_lane",
]


PRIMARY_FEATURES = tuple(
    f"w{window}_{name}"
    for window in PRIMARY_WINDOWS_DAYS
    for name in (
        "mean_temperature_c",
        "mean_tmin_c",
        "mean_tmax_c",
        "precipitation_sum_mm",
        "solar_radiation_mean_mj_m2",
        "wind_speed_mean_m_s",
    )
)
