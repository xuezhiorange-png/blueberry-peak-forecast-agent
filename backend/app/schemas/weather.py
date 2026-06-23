from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WeatherMappingResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location_reference_id: int
    as_of_date: date


class WeatherHistoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location_reference_id: int
    as_of_date: date
    start_date: date
    end_date: date


class WeatherFeatureBuildRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    farm_id: int
    subfarm_id: int | None = None
    season_id: int
    variety_id: int
    as_of_date: date
    feature_date: date
    base_temperature_search_run_id: int | None = None
    anchor_event: str | None = None
    dry_run: bool = False


class BaseTemperatureTrainingSampleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: int
    anchor_event: str
    target_event: str
    sample_weight: Decimal = Field(gt=0)
    include: bool = True
    exclusion_reason: str | None = None


class BaseTemperatureSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    training_cutoff: date
    scope_type: str
    variety_id: int | None = None
    climate_zone_id: int | None = None
    dry_run: bool = False
    samples: list[BaseTemperatureTrainingSampleInput]


class WeatherTaskResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    run_id: int | None = None
    source_signature: str
    config_hash: str
    feature_version: str | None = None
    payload: dict[str, Any]
