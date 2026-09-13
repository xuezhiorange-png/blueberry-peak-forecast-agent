"""Explicit saved-run contracts; stateless product contract is unchanged."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.app.area_yield.product import AreaDrivenForecastRequest, AreaDrivenForecastResult


class CreateAreaForecastRun(AreaDrivenForecastRequest):
    rerun_of_run_id: int | None = Field(default=None, gt=0)


class AreaRunSummary(BaseModel):
    run_id: int
    status: Literal["completed"] = "completed"
    created_at: datetime
    completed_at: datetime
    canonical_farm: str
    requested_productive_area_mu: str
    target_season: str
    predicted_total_kg: str
    single_day_peak: dict[str, str]
    rolling_7day_peak: dict[str, str]
    forecast_policy_version: str
    authority_hash: str
    result_hash: str
    request_hash: str
    rerun_of_run_id: int | None


class SavedAreaForecastRun(BaseModel):
    run: AreaRunSummary
    request_snapshot: dict[str, Any]
    result: AreaDrivenForecastResult
    reused_existing_run: bool = False


class AreaRunHistory(BaseModel):
    items: list[AreaRunSummary]
    next_cursor: str | None
