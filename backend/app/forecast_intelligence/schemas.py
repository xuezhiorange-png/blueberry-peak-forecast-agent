"""Strict transport contracts: no prediction, hierarchy or policy overrides."""

from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator


class CreateHierarchicalRun(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_entity_type: Literal["REGION", "COMPANY"]
    target_entity_id: StrictStr = Field(min_length=1, max_length=200)
    source_run_ids: list[Annotated[StrictInt, Field(gt=0)]] = Field(min_length=1)

    @field_validator("source_run_ids")
    @classmethod
    def unique_sorted(cls, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise ValueError("DUPLICATE_SOURCE_RUN_ID")
        return sorted(value)


class HierarchicalRunIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: StrictInt = Field(gt=0)


class HierarchicalHistoryQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_entity_type: Literal["REGION", "COMPANY"] | None = None
    target_entity_id: StrictStr | None = None
    target_season: StrictStr | None = None
    origin_date: date | None = None
    reconciliation_policy_version: StrictStr | None = None
    limit: StrictInt = Field(default=20, ge=1, le=100)
    cursor: StrictStr | None = None


class HierarchicalRunSummary(BaseModel):
    run_id: int
    status: str
    execution_hash: str
    result_hash: str
    hierarchy_authority_hash: str
    target_entity_type: str
    target_entity_id: str
    target_entity_label: str
    target_season: str
    origin_date: date
    reconciliation_policy_version: str
    child_expected_count: int
    child_included_count: int
    created_at: datetime
    completed_at: datetime


class SavedHierarchicalRun(BaseModel):
    run: HierarchicalRunSummary
    result: dict[str, Any]
    hierarchy_snapshot: dict[str, Any]
    reused_existing_run: bool = False


class HierarchicalRunHistory(BaseModel):
    items: list[HierarchicalRunSummary]
    next_cursor: str | None = None


class HierarchicalDailyRows(BaseModel):
    run_id: int
    daily_forecast: list[dict[str, str]]
