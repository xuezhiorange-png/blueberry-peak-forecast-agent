from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MaturityManifestRowInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    season_id: int
    analytics_build_run_id: int
    farm_key: str
    farm_id: int
    subfarm_key: str
    subfarm_id: int | None = None
    variety_id: int
    location_reference_id: int
    production_plan_id: int
    base_temperature_search_run_id: int
    anchor_event: str
    facility_type: str
    include: bool = True
    sample_weight: Decimal = Field(gt=0)
    exclusion_reason: str | None = None


class MaturityModelTrainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    training_cutoff: date
    manifest_rows: list[MaturityManifestRowInput]
    dry_run: bool = False


class MaturityForecastRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_run_id: int
    farm_id: int
    subfarm_id: int | None = None
    season_id: int
    variety_id: int
    as_of_date: date
    prediction_start_date: date
    prediction_end_date: date
    expected_marketable_total_kg: Decimal | None = Field(default=None, ge=0)
    facility_type: str
    dry_run: bool = False


class MaturityTaskResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    run_id: int | None = None
    source_signature: str
    config_hash: str
    model_version: str | None = None
    payload: dict[str, Any]
