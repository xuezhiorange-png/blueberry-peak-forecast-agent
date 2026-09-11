from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LocationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    address: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    location_reference_id: int | None = None
    farm_id: int | None = Field(default=None, gt=0)
    altitude_m: Decimal | None = None
    province: str | None = None
    prefecture: str | None = None
    county: str | None = None
    township: str | None = None
    village: str | None = None
    farm_name: str | None = None

    @model_validator(mode="after")
    def _validate_one_of(self) -> LocationInput:
        if self.farm_id is not None:
            if any(
                value is not None for key, value in self.model_dump().items() if key != "farm_id"
            ):
                raise ValueError("canonical farm_id cannot be combined with location overrides")
            return self
        choices = int(self.address is not None)
        choices += int(self.latitude is not None and self.longitude is not None)
        choices += int(self.location_reference_id is not None)
        if choices != 1:
            raise ValueError(
                "location must provide exactly one of "
                "address, latitude+longitude, location_reference_id, or farm_id"
            )
        return self


class VarietyAreaInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variety_id: int | None = None
    variety_code: str | None = None
    variety_name: str | None = None
    planted_area_mu: Decimal = Field(gt=0)

    @model_validator(mode="after")
    def _validate_lookup(self) -> VarietyAreaInput:
        if self.variety_id is None and self.variety_code is None and self.variety_name is None:
            raise ValueError("variety lookup is required")
        return self


class MinimalPlanningTaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location: LocationInput
    varieties: list[VarietyAreaInput]
    as_of_date: date | None = None


class PlanningTaskResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    task_id: int | None
    run_id: int | None
    input_hash: str
    as_of_date: date
    resolver_version: str
    library_version: str | None
    config_hash: str
    source_signature: str
    resolved_location: dict[str, Any]
    similar_historical_samples: list[dict[str, Any]]
    variety_parameters: list[dict[str, Any]]
    warnings: list[str]
    missing_data: list[str]
    reproducibility_snapshot: dict[str, Any]
    error_message: str | None = None
