"""Transport schemas for the S6 operational peak run boundary."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr


class CreateOperationalPeakRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_id: StrictStr = Field(min_length=1, max_length=200)
    target_season: StrictStr = Field(pattern=r"^\d{4}-\d{4}$")
    origin_date: date
    rerun_of_run_id: StrictInt | None = Field(default=None, gt=0)


class OperationalPeakRunIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: StrictInt = Field(gt=0)


class OperationalPeakHistoryQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_id: StrictStr | None = None
    target_season: StrictStr | None = None
    policy_version: StrictStr | None = None
    limit: StrictInt = Field(default=20, ge=1, le=100)
    cursor: str | None = None


class OperationalPeakRunSummary(BaseModel):
    run_id: int
    execution_hash: str
    request_hash: str
    authority_hash: str
    result_hash: str
    base_id: str
    canonical_base_name: str
    productive_area_mu: str
    target_season: str
    origin_date: date
    baseline_id: str
    policy_version: str
    weather_used: bool
    forecast_7d: dict[str, Any]
    forecast_15d: dict[str, Any]
    remaining_business_window: dict[str, Any]
    created_at: datetime
    completed_at: datetime
    rerun_of_run_id: int | None = None


class OperationalPeakRunHistory(BaseModel):
    items: list[OperationalPeakRunSummary]
    next_cursor: str | None = None


class OperationalPeakDailyRow(BaseModel):
    date: date
    predicted_kg: str
    kg_per_mu: str
    business_season_day_index: int
    reference_bin: int


class OperationalPeakDailyRows(BaseModel):
    run_id: int
    daily_forecast: list[OperationalPeakDailyRow]


class SavedOperationalPeakRun(BaseModel):
    run: OperationalPeakRunSummary
    request_snapshot: dict[str, Any]
    result: dict[str, Any]
    reused_existing_run: bool = False


__all__ = [
    "CreateOperationalPeakRun",
    "OperationalPeakDailyRow",
    "OperationalPeakDailyRows",
    "OperationalPeakHistoryQuery",
    "OperationalPeakRunHistory",
    "OperationalPeakRunIdentity",
    "OperationalPeakRunSummary",
    "SavedOperationalPeakRun",
]
