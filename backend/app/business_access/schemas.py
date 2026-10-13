"""Strict S2 inputs; client identity strings never confer permission."""

from datetime import date
from typing import Annotated, Literal

from pydantic import Field, StrictInt, StrictStr, model_validator

from backend.app.forecast_intelligence.read_schemas import (
    ForecastIdentity,
    Hash,
    HierarchyLevel,
    Identifier,
    ReadModel,
)


class Filters(ReadModel):
    target_season: str | None = Field(default=None, pattern=r"^\d{4}-\d{4}$")
    hierarchy_level: HierarchyLevel | None = None
    entity_id: Identifier | None = None
    forecast_family: Identifier | None = None
    origin_from: date | None = None
    origin_to: date | None = None
    page_size: int = Field(default=20, ge=1, le=100)
    cursor: Annotated[str, Field(min_length=1, max_length=2048)] | None = None

    @model_validator(mode="after")
    def ordered_dates(self) -> "Filters":
        if self.origin_from and self.origin_to and self.origin_from > self.origin_to:
            raise ValueError("Invalid date range")
        return self

    def signature_input(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"cursor"})


class Selection(ReadModel):
    forecast_identity: ForecastIdentity
    expected_source_result_hash: Hash
    grant_revision: Annotated[StrictInt, Field(gt=0)]
    catalog_snapshot: Hash
    handoff_token: Annotated[StrictStr, Field(min_length=1, max_length=8192)] | None = None


class TokenClaims(ReadModel):
    version: StrictInt
    purpose: Literal["cursor", "selection"]
    principal: StrictStr
    session: StrictStr
    auth_revision: StrictInt
    grant_revision: StrictInt
    grant_directory: Hash
    catalog_snapshot: Hash
    issued_at: StrictInt
    expires_at: StrictInt
    filter_hash: Hash | None = None
    last_key: tuple[str, str, str, int, str, str] | None = None
    forecast_identity: ForecastIdentity | None = None
    expected_source_result_hash: Hash | None = None

    @model_validator(mode="after")
    def purpose_binding(self) -> "TokenClaims":
        if self.purpose == "cursor":
            if (
                self.filter_hash is None
                or self.last_key is None
                or self.forecast_identity is not None
                or self.expected_source_result_hash is not None
            ):
                raise ValueError("Invalid cursor binding")
            date.fromisoformat(self.last_key[0])
            if (
                self.last_key[1] not in {"OPERATIONAL_PEAK", "HIERARCHICAL"}
                or self.last_key[3] <= 0
            ):
                raise ValueError("Invalid keyset")
        elif (
            self.forecast_identity is None
            or self.expected_source_result_hash is None
            or self.filter_hash is not None
            or self.last_key is not None
        ):
            raise ValueError("Invalid handoff binding")
        return self
