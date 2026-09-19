"""Typed contracts for the V0.6-S1 PIT foundation."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.pit.canonical import hash_payload

AreaType = Literal[
    "REFERENCE_AREA",
    "ACTUAL_PRODUCTIVE_AREA",
    "PLANTED_AREA",
    "PLANNED_AREA",
]


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone-aware datetime is required")
    return value.astimezone(UTC)


def _sha(value: str, field: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{field} must be a lowercase SHA-256")
    return value


class _FrozenInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AreaRevisionInput(_FrozenInput):
    area_revision_id: str = Field(min_length=1)
    base_id: str = Field(min_length=1)
    season: str = Field(min_length=1)
    area_mu: Decimal = Field(gt=0)
    area_type: AreaType
    effective_from: datetime
    effective_to: datetime | None = None
    recorded_at: datetime
    known_at: datetime
    source: str = Field(min_length=1)
    source_reference: str = Field(min_length=1)
    basis: str = Field(min_length=1)
    supersedes_revision_id: str | None = None
    payload_hash: str | None = None

    @model_validator(mode="after")
    def validate_timestamps(self) -> AreaRevisionInput:
        self.effective_from = _aware(self.effective_from)
        self.recorded_at = _aware(self.recorded_at)
        self.known_at = _aware(self.known_at)
        if self.recorded_at > self.known_at:
            raise ValueError("recorded_at must be <= known_at")
        if self.effective_to is not None:
            self.effective_to = _aware(self.effective_to)
            if self.effective_to < self.effective_from:
                raise ValueError("effective_to must not precede effective_from")
        if self.payload_hash is not None:
            _sha(self.payload_hash, "payload_hash")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"payload_hash"})

    def computed_payload_hash(self) -> str:
        return hash_payload(self.payload())


class WeatherForecastSnapshotInput(_FrozenInput):
    weather_snapshot_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    base_id: str | None = None
    location_id: str | None = None
    issued_at: datetime
    fetched_at: datetime
    known_at: datetime
    valid_at: datetime
    forecast_horizon_hours: int = Field(ge=0)
    temperature_min: Decimal | None = None
    temperature_max: Decimal | None = None
    temperature_mean: Decimal | None = None
    precipitation: Decimal | None = None
    relative_humidity: Decimal | None = None
    solar_radiation: Decimal | None = None
    wind_speed: Decimal | None = None
    raw_payload_reference: str | None = None
    raw_payload_hash: str
    normalized_payload_hash: str
    payload_hash: str | None = None

    @model_validator(mode="after")
    def validate_snapshot(self) -> WeatherForecastSnapshotInput:
        self.issued_at = _aware(self.issued_at)
        self.fetched_at = _aware(self.fetched_at)
        self.known_at = _aware(self.known_at)
        self.valid_at = _aware(self.valid_at)
        if self.base_id is None and self.location_id is None:
            raise ValueError("base_id or location_id is required")
        if self.issued_at > self.fetched_at:
            raise ValueError("issued_at must be <= fetched_at")
        if self.issued_at > self.known_at:
            raise ValueError("issued_at must be <= known_at")
        if self.fetched_at < self.issued_at:
            raise ValueError("fetched_at must be >= issued_at")
        if self.fetched_at > self.known_at:
            raise ValueError("fetched_at must be <= known_at")
        _sha(self.raw_payload_hash, "raw_payload_hash")
        _sha(self.normalized_payload_hash, "normalized_payload_hash")
        if self.payload_hash is not None:
            _sha(self.payload_hash, "payload_hash")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"payload_hash"})

    def computed_payload_hash(self) -> str:
        return hash_payload(self.payload())


class RealizedWeatherObservationInput(_FrozenInput):
    weather_observation_id: str = Field(min_length=1)
    base_id: str | None = None
    location_id: str | None = None
    observation_time: datetime
    temperature: Decimal | None = None
    precipitation: Decimal | None = None
    humidity: Decimal | None = None
    solar_radiation: Decimal | None = None
    wind: Decimal | None = None
    source: str = Field(min_length=1)
    source_reference: str = Field(min_length=1)
    recorded_at: datetime
    known_at: datetime
    payload_hash: str | None = None

    @model_validator(mode="after")
    def validate_observation(self) -> RealizedWeatherObservationInput:
        self.observation_time = _aware(self.observation_time)
        self.recorded_at = _aware(self.recorded_at)
        self.known_at = _aware(self.known_at)
        if self.base_id is None and self.location_id is None:
            raise ValueError("base_id or location_id is required")
        if self.observation_time > self.known_at:
            raise ValueError("observation_time must be <= known_at")
        if self.recorded_at > self.known_at:
            raise ValueError("recorded_at must be <= known_at")
        if self.payload_hash is not None:
            _sha(self.payload_hash, "payload_hash")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"payload_hash"})

    def computed_payload_hash(self) -> str:
        return hash_payload(self.payload())


class PhenologyObservationInput(_FrozenInput):
    observation_id: str = Field(min_length=1)
    base_id: str = Field(min_length=1)
    farm_id: str | None = None
    season: str = Field(min_length=1)
    phenology_stage: str = Field(min_length=1)
    observed_at: datetime
    recorded_at: datetime
    known_at: datetime
    source: str = Field(min_length=1)
    source_reference: str = Field(min_length=1)
    quality_status: str = Field(min_length=1)
    notes: str | None = None
    payload_hash: str | None = None

    @model_validator(mode="after")
    def validate_observation(self) -> PhenologyObservationInput:
        self.observed_at = _aware(self.observed_at)
        self.recorded_at = _aware(self.recorded_at)
        self.known_at = _aware(self.known_at)
        if self.observed_at > self.known_at:
            raise ValueError("observed_at must be <= known_at")
        if self.recorded_at > self.known_at:
            raise ValueError("recorded_at must be <= known_at")
        if self.payload_hash is not None:
            _sha(self.payload_hash, "payload_hash")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"payload_hash"})

    def computed_payload_hash(self) -> str:
        return hash_payload(self.payload())


class ForecastDailySnapshotInput(_FrozenInput):
    forecast_date: date
    predicted_quantity_kg: Decimal = Field(ge=0)
    normalized_share: Decimal = Field(ge=0)


class ForecastRunSnapshotInput(_FrozenInput):
    forecast_run_id: str = Field(min_length=1)
    forecast_created_at: datetime
    base_id: str = Field(min_length=1)
    target_season: str = Field(min_length=1)
    forecast_start_date: date
    forecast_end_date: date
    target_area_mu: Decimal = Field(gt=0)
    forecast_mode: str = Field(min_length=1)
    model_status: str = Field(min_length=1)
    total_model_id: str = Field(min_length=1)
    temporal_model_id: str = Field(min_length=1)
    model_artifact_hashes: dict[str, str]
    prior_history_season: str | None = None
    prior_history_quantity_kg: Decimal | None = Field(default=None, ge=0)
    prior_history_coverage_status: str | None = None
    prior_history_source_hash: str | None = None
    prior_history_identity_mapping_hash: str | None = None
    area_revision_id: str = Field(min_length=1)
    weather_snapshot_ids: list[str] = Field(default_factory=list)
    phenology_observation_ids: list[str] = Field(default_factory=list)
    input_snapshot_json: dict[str, Any]
    input_snapshot_hash: str
    predicted_season_total_kg: Decimal = Field(ge=0)
    daily_curve: list[ForecastDailySnapshotInput] = Field(min_length=1)
    single_day_peak: dict[str, Any]
    rolling_7day_peak: dict[str, Any]
    result_hash: str
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_snapshot(self) -> ForecastRunSnapshotInput:
        self.forecast_created_at = _aware(self.forecast_created_at)
        if self.forecast_end_date < self.forecast_start_date:
            raise ValueError("forecast_end_date must not precede forecast_start_date")
        if len(self.weather_snapshot_ids) != len(set(self.weather_snapshot_ids)):
            raise ValueError("weather_snapshot_ids must not contain duplicates")
        if len(self.phenology_observation_ids) != len(set(self.phenology_observation_ids)):
            raise ValueError("phenology_observation_ids must not contain duplicates")
        _sha(self.input_snapshot_hash, "input_snapshot_hash")
        _sha(self.result_hash, "result_hash")
        for key, value in self.model_artifact_hashes.items():
            _sha(value, f"model_artifact_hashes[{key}]")
        return self

    def result_payload(self) -> dict[str, Any]:
        """Return the deterministic output envelope hashed by ``result_hash``."""

        return {
            "schema_version": "V0_6_FORECAST_RESULT_SNAPSHOT_V1",
            "base_id": self.base_id,
            "target_season": self.target_season,
            "forecast_start_date": self.forecast_start_date,
            "forecast_end_date": self.forecast_end_date,
            "target_area_mu": self.target_area_mu,
            "forecast_mode": self.forecast_mode,
            "model_status": self.model_status,
            "total_model_id": self.total_model_id,
            "temporal_model_id": self.temporal_model_id,
            "model_artifact_hashes": self.model_artifact_hashes,
            "prior_history_season": self.prior_history_season,
            "prior_history_quantity_kg": self.prior_history_quantity_kg,
            "prior_history_coverage_status": self.prior_history_coverage_status,
            "prior_history_source_hash": self.prior_history_source_hash,
            "prior_history_identity_mapping_hash": self.prior_history_identity_mapping_hash,
            "area_revision_id": self.area_revision_id,
            "weather_snapshot_ids": sorted(self.weather_snapshot_ids),
            "phenology_observation_ids": sorted(self.phenology_observation_ids),
            "predicted_season_total_kg": self.predicted_season_total_kg,
            "daily_curve": [row.model_dump(mode="python") for row in self.daily_curve],
            "single_day_peak": self.single_day_peak,
            "rolling_7day_peak": self.rolling_7day_peak,
            "warnings": sorted(self.warnings),
        }

    def computed_result_hash(self) -> str:
        return hash_payload(self.result_payload())


class ForecastRunSnapshot(ForecastRunSnapshotInput):
    """Canonical read model returned after a persistence reload."""

    created_at: datetime

    @model_validator(mode="after")
    def validate_created_at(self) -> ForecastRunSnapshot:
        self.created_at = _aware(self.created_at)
        return self


__all__ = [
    "AreaRevisionInput",
    "AreaType",
    "ForecastDailySnapshotInput",
    "ForecastRunSnapshot",
    "ForecastRunSnapshotInput",
    "PhenologyObservationInput",
    "RealizedWeatherObservationInput",
    "WeatherForecastSnapshotInput",
]
