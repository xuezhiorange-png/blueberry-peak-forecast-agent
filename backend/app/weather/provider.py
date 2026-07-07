from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

from backend.app.planning.normalization import coerce_optional_decimal, validate_coordinate_pair
from backend.app.weather.schemas import DailyWeatherRecord, WeatherSourceLocationRecord


class WeatherProviderError(ValueError):
    pass


class WeatherValidationError(WeatherProviderError):
    pass


def _required_text(value: str | None, *, field: str) -> str:
    if value is None:
        raise WeatherValidationError(f"{field} is required")
    text = value.strip()
    if not text:
        raise WeatherValidationError(f"{field} is required")
    return text


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _date_value(value: str | None, *, field: str) -> date:
    text = _required_text(value, field=field)
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise WeatherValidationError(f"{field} must be ISO date") from exc


def _optional_date(value: str | None) -> date | None:
    if value is None or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise WeatherValidationError("optional date must be ISO date") from exc


def _decimal_value(value: str | None, *, field: str) -> Decimal:
    text = _required_text(value, field=field)
    try:
        parsed = Decimal(text)
    except InvalidOperation as exc:
        raise WeatherValidationError(f"{field} must be a decimal") from exc
    if not parsed.is_finite():
        raise WeatherValidationError(f"{field} must be finite")
    return parsed


def _optional_decimal(value: str | None) -> Decimal | None:
    if value is None or not value.strip():
        return None
    try:
        parsed = Decimal(value.strip())
    except InvalidOperation as exc:
        raise WeatherValidationError("optional decimal must be valid") from exc
    if not parsed.is_finite():
        raise WeatherValidationError("optional decimal must be finite")
    return parsed


def _location_type(value: str | None) -> Literal["station", "grid"]:
    text = _required_text(value, field="location_type").lower()
    if text not in {"station", "grid"}:
        raise WeatherValidationError("location_type must be station or grid")
    return text  # type: ignore[return-value]


def _quality_flags(value: str | None) -> tuple[str, ...]:
    if value is None or not value.strip():
        return ()
    return tuple(part.strip() for part in value.split(";") if part.strip())


@dataclass(frozen=True)
class CsvWeatherProvider:
    file_path: Path
    provider_code: str
    provider_version: str
    dataset_version: str
    location_type: Literal["station", "grid"]

    def _rows(self) -> list[dict[str, str]]:
        with self.file_path.open("r", encoding="utf-8", newline="") as file:
            return list(csv.DictReader(file))

    def parse_location_rows(self) -> list[WeatherSourceLocationRecord]:
        rows: list[WeatherSourceLocationRecord] = []
        for index, row in enumerate(self._rows(), start=2):
            latitude = _decimal_value(row.get("latitude"), field="latitude")
            longitude = _decimal_value(row.get("longitude"), field="longitude")
            validate_coordinate_pair(latitude, longitude)
            valid_from = _date_value(row.get("valid_from"), field="valid_from")
            valid_to = _optional_date(row.get("valid_to"))
            if valid_to is not None and valid_to < valid_from:
                raise WeatherValidationError("valid_to must not be earlier than valid_from")
            rows.append(
                WeatherSourceLocationRecord(
                    provider_code=self.provider_code,
                    provider_version=self.provider_version,
                    dataset_version=self.dataset_version,
                    external_location_id=_required_text(
                        row.get("external_location_id"),
                        field="external_location_id",
                    ),
                    location_type=_location_type(row.get("location_type") or self.location_type),
                    name=_optional_text(row.get("name")),
                    latitude=latitude,
                    longitude=longitude,
                    altitude_m=_optional_decimal(row.get("altitude_m")),
                    timezone_name=_required_text(row.get("timezone_name"), field="timezone_name"),
                    grid_resolution=_optional_text(row.get("grid_resolution")),
                    source_version=_required_text(
                        row.get("source_version"),
                        field="source_version",
                    ),
                    valid_from=valid_from,
                    valid_to=valid_to,
                    source_row_number=index,
                    quality_flags=_quality_flags(row.get("quality_flags")),
                )
            )
        return rows

    def parse_observation_rows(self) -> list[DailyWeatherRecord]:
        rows: list[DailyWeatherRecord] = []
        for index, row in enumerate(self._rows(), start=2):
            observation_date = _date_value(row.get("observation_date"), field="observation_date")
            minimum = _decimal_value(row.get("temperature_min_c"), field="temperature_min_c")
            maximum = _decimal_value(row.get("temperature_max_c"), field="temperature_max_c")
            if maximum < minimum:
                raise WeatherValidationError("temperature_max_c must be >= temperature_min_c")
            mean = _optional_decimal(row.get("temperature_mean_c"))
            mean_source: Literal["provided", "derived"]
            if mean is None:
                mean = (minimum + maximum) / Decimal("2")
                mean_source = "derived"
            else:
                if mean < minimum or mean > maximum:
                    raise WeatherValidationError("temperature_mean_c must be between min and max")
                mean_source = "provided"
            precipitation = _decimal_value(row.get("precipitation_mm"), field="precipitation_mm")
            if precipitation < 0:
                raise WeatherValidationError("precipitation_mm must be non-negative")
            solar = _optional_decimal(row.get("solar_radiation_mj_m2"))
            if solar is not None and solar < 0:
                raise WeatherValidationError("solar_radiation_mj_m2 must be non-negative")
            rows.append(
                DailyWeatherRecord(
                    provider_code=self.provider_code,
                    provider_version=self.provider_version,
                    dataset_version=self.dataset_version,
                    external_location_id=_required_text(
                        row.get("external_location_id"),
                        field="external_location_id",
                    ),
                    observation_date=observation_date,
                    temperature_min_c=minimum,
                    temperature_max_c=maximum,
                    temperature_mean_c=mean,
                    temperature_mean_source=mean_source,
                    precipitation_mm=precipitation,
                    solar_radiation_mj_m2=solar,
                    available_at=_date_value(row.get("available_at"), field="available_at"),
                    quality_code=_optional_text(row.get("quality_code")),
                    quality_flags=_quality_flags(row.get("quality_flags")),
                    source_version=_required_text(
                        row.get("source_version"),
                        field="source_version",
                    ),
                    source_row_number=index,
                )
            )
        return rows


def coerce_decimal_input(value: Decimal | int | float | str | None, *, field: str) -> Decimal:
    coerced = coerce_optional_decimal(value)
    if coerced is None:
        raise WeatherValidationError(f"{field} is required")
    if not coerced.is_finite():
        raise WeatherValidationError(f"{field} must be finite")
    return coerced
