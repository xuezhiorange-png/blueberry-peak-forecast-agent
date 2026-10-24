"""Explicit, immutable runtime authority; never inferred from historical years."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Name = Annotated[str, Field(min_length=1, max_length=200)]
Mode = Literal["RESEARCH_SHADOW", "RETROSPECTIVE_DATE_BOUND"]
TargetQuantityBasis = Literal[
    "FIELD_HARVEST_WEIGHT",
    "MARKETABLE_FRUIT_WEIGHT",
    "INBOUND_WEIGHT",
    "INBOUND_NET_WEIGHT",
    "RECORDED_INBOUND_WEIGHT",
]


class Contract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    @field_validator("*", mode="after")
    @classmethod
    def aware_time(cls, value: Any) -> Any:
        if isinstance(value, datetime) and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("TIMEZONE_REQUIRED")
        return value


class Calendar(Contract):
    reference: Name
    season: str = Field(pattern=r"^\d{4}-\d{4}$")
    start: date
    end: date
    timezone: Literal["Asia/Shanghai"] = "Asia/Shanghai"
    source_hash: Hash
    known_at: datetime | None

    @model_validator(mode="after")
    def valid_calendar(self) -> Self:
        if self.start >= self.end or (self.end - self.start).days > 400:
            raise ValueError("INVALID_SEASON_CALENDAR")
        return self


class Area(Contract):
    reference: Name
    base_id: Name
    season: str = Field(pattern=r"^\d{4}-\d{4}$")
    area_mu: Decimal = Field(gt=0, allow_inf_nan=False)
    unit: Literal["mu"] = "mu"
    source_hash: Hash
    known_at: datetime | None
    effective_from: date
    effective_until: date

    @model_validator(mode="after")
    def effective_range(self) -> Self:
        if self.effective_from > self.effective_until:
            raise ValueError("AREA_EFFECTIVE_RANGE_INVALID")
        return self


class Observation(Contract):
    base_id: Name
    season: str
    business_date: date
    quantity_kg: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    record_state: Literal[
        "VALID_OBSERVED", "CONFIRMED_ZERO", "UNKNOWN", "PARTIAL", "MISSING", "CONFLICTING"
    ]
    quantity_basis: TargetQuantityBasis
    source_system: Name
    source_identity: Name
    source_hash: Hash
    source_recorded_at: datetime | None
    server_ingested_at: datetime | None
    available_at_authority: Literal[
        "TRUSTED_SOURCE_TIMESTAMP", "MISSING", "USER_ASSERTED_UNVERIFIED", "CONFLICTING"
    ]
    observation_completeness: Literal["COMPLETE", "INCOMPLETE"]


class Issue(Contract):
    base_id: Name
    target_season: str = Field(pattern=r"^\d{4}-\d{4}$")
    origin_date: date
    origin_cutoff_at: datetime
    observation_snapshot_reference: Name
    area_authority_reference: Name
    frozen_model_artifact_reference: Name
    execution_mode: Mode
    rerun_of_run_id: int | None = Field(default=None, gt=0)
