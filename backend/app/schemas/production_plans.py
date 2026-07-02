from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.planning.json_types import canonical_decimal_string


class ProductionPlanBaseModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_encoders={Decimal: canonical_decimal_string},
    )


class ProductionPlanCreate(ProductionPlanBaseModel):
    farm_id: int
    subfarm_id: int | None = None
    season_id: int
    variety_id: int
    planted_area_mu: Decimal
    expected_yield_kg_per_mu: Decimal
    marketable_rate: Decimal
    tree_age_years: Decimal | None = None
    pruning_date: date | None = None
    flowering_start_date: date | None = None
    flowering_peak_date: date | None = None
    flowering_end_date: date | None = None
    first_pick_date: date | None = None
    expected_total_marketable_kg: Decimal | None = None
    version: int
    effective_from: date
    effective_to: date | None = None
    available_at: date
    source_type: str = Field(min_length=1)
    source_name: str | None = None
    source_version: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _validate_ranges(self) -> ProductionPlanCreate:
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must be later than effective_from")
        if self.flowering_start_date and self.flowering_peak_date:
            if self.flowering_start_date > self.flowering_peak_date:
                raise ValueError(
                    "flowering_start_date must be less than or equal to flowering_peak_date"
                )
        if self.flowering_peak_date and self.flowering_end_date:
            if self.flowering_peak_date > self.flowering_end_date:
                raise ValueError(
                    "flowering_peak_date must be less than or equal to flowering_end_date"
                )
        return self


class ProductionPlanRead(ProductionPlanBaseModel):
    plan_id: int
    farm_id: int
    farm_name: str
    subfarm_id: int | None
    subfarm_name: str | None
    season_id: int
    season_code: str
    variety_id: int
    variety_code: str
    variety_name: str
    planted_area_mu: Decimal
    expected_yield_kg_per_mu: Decimal
    marketable_rate: Decimal
    tree_age_years: Decimal | None
    pruning_date: date | None
    flowering_start_date: date | None
    flowering_peak_date: date | None
    flowering_end_date: date | None
    first_pick_date: date | None
    expected_total_marketable_kg: Decimal | None
    derived_total_marketable_kg: Decimal
    total_difference_kg: Decimal | None
    version: int
    effective_from: date
    effective_to: date | None
    available_at: date
    source_type: str
    source_name: str | None
    source_version: str | None
    notes: str | None
    row_hash: str
    warnings: list[str]
    created_at: datetime
    updated_at: datetime


class ProductionPlanList(ProductionPlanBaseModel):
    items: list[ProductionPlanRead]
    total: int
