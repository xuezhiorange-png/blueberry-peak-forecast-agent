from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

QUANTILES = ("P50", "P80", "P90")
QUANTILE_RANK = {value: index for index, value in enumerate(QUANTILES)}
OUTPUT_QUANTUM = Decimal("0.000001")

StrictPositiveInt = Annotated[int, Field(strict=True, gt=0)]
StrictNonEmptyString = Annotated[str, Field(strict=True, min_length=1)]
SHA256Hex = Annotated[
    str,
    Field(strict=True, min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"),
]

CoreForecastBlockerCode = Literal[
    "TASK8_AUTHORITY_NOT_FOUND",
    "TASK9_AUTHORITY_NOT_FOUND",
    "AUTHORITY_SCOPE_MISMATCH",
    "AUTHORITY_LINEAGE_MISMATCH",
    "AUTHORITY_HASH_MALFORMED",
    "TASK8_TASK9_SUPPLY_RECONCILIATION_FAILED",
    "MARKETABLE_RETENTION_POLICY_MISSING",
    "MARKETABLE_RETENTION_POLICY_CONFLICT",
    "MARKETABLE_RETENTION_POLICY_INVALID",
    "DAILY_CURVE_DUPLICATE_KEY",
    "DAILY_CURVE_INCOMPLETE_SERIES",
    "DAILY_CURVE_STATE_INVARIANT_FAILED",
    "DAILY_CURVE_CONTINUITY_FAILED",
    "UPSTREAM_READ_FAILURE",
]


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CoreForecastScope(_FrozenModel):
    farm_id: StrictPositiveInt
    subfarm_id: StrictPositiveInt
    variety_id: StrictPositiveInt


class CompleteDailyMarketableCurveRequest(_FrozenModel):
    forecast_season_id: StrictPositiveInt
    forecast_season_code: StrictNonEmptyString
    forecast_start_date: date
    forecast_end_date: date
    destination_factory_id: StrictPositiveInt
    task8_forecast_run_id: StrictPositiveInt
    task9_harvest_state_run_id: StrictPositiveInt
    scopes: tuple[CoreForecastScope, ...]

    @field_validator("scopes")
    @classmethod
    def _scopes_are_unique_and_non_empty(
        cls,
        value: tuple[CoreForecastScope, ...],
    ) -> tuple[CoreForecastScope, ...]:
        if not value:
            raise ValueError("scopes must not be empty")
        keys = [(item.farm_id, item.subfarm_id, item.variety_id) for item in value]
        if len(keys) != len(set(keys)):
            raise ValueError("scopes must be unique")
        return value

    @model_validator(mode="after")
    def _date_range_is_valid(self) -> CompleteDailyMarketableCurveRequest:
        if self.forecast_end_date < self.forecast_start_date:
            raise ValueError("forecast_end_date must be >= forecast_start_date")
        return self


def _parse_rate(value: object) -> str:
    if not isinstance(value, str) or not value or "e" in value.lower():
        raise ValueError("retention rate must be a canonical decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("retention rate must be a decimal") from exc
    if not parsed.is_finite() or parsed < 0 or parsed > 1:
        raise ValueError("retention rate must be finite and within [0, 1]")
    if format(parsed, "f") != value:
        raise ValueError("retention rate must be a canonical decimal string")
    return value


class MarketableRetentionPolicyEntry(_FrozenModel):
    forecast_season_id: StrictPositiveInt
    forecast_season_code: StrictNonEmptyString
    farm_id: StrictPositiveInt
    subfarm_id: StrictPositiveInt
    variety_id: StrictPositiveInt
    sorting_retention_rate: StrictNonEmptyString
    postharvest_retention_rate: StrictNonEmptyString
    source: StrictNonEmptyString
    version: StrictNonEmptyString
    hash: SHA256Hex

    _validate_rates = field_validator(
        "sorting_retention_rate",
        "postharvest_retention_rate",
        mode="before",
    )(_parse_rate)


class MarketableRetentionPolicySnapshot(_FrozenModel):
    entries: tuple[MarketableRetentionPolicyEntry, ...]


_QUANTITY_FIELDS = (
    "natural_maturity_supply_kg",
    "opening_mature_inventory_kg",
    "available_mature_quantity_kg",
    "mature_inventory_loss_quantity_kg",
    "harvestable_mature_quantity_kg",
    "effective_harvest_capacity_kg",
    "model_harvested_marketable_quantity_kg",
    "closing_mature_inventory_kg",
    "unharvested_backlog_kg",
    "sorting_retention_rate",
    "postharvest_retention_rate",
    "effective_marketable_quantity_kg",
)


def _fixed_decimal_string(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"(?:0|[1-9]\d*)(?:\.\d+)?", value):
        raise ValueError("quantity must be a decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("quantity must be a decimal") from exc
    if not parsed.is_finite() or parsed < 0:
        raise ValueError("quantity must be finite and non-negative")
    quantized = parsed.quantize(OUTPUT_QUANTUM)
    if quantized != parsed or format(parsed, "f") != value:
        raise ValueError("quantity must be an exact six-place decimal string")
    return value


class CompleteDailyMarketableCurveRow(_FrozenModel):
    date: date
    forecast_quantile: Literal["P50", "P80", "P90"]
    farm_id: StrictPositiveInt
    subfarm_id: StrictPositiveInt
    variety_id: StrictPositiveInt
    destination_factory_id: StrictPositiveInt

    natural_maturity_supply_kg: StrictNonEmptyString
    opening_mature_inventory_kg: StrictNonEmptyString
    available_mature_quantity_kg: StrictNonEmptyString
    mature_inventory_loss_quantity_kg: StrictNonEmptyString
    harvestable_mature_quantity_kg: StrictNonEmptyString
    effective_harvest_capacity_kg: StrictNonEmptyString
    model_harvested_marketable_quantity_kg: StrictNonEmptyString
    closing_mature_inventory_kg: StrictNonEmptyString
    unharvested_backlog_kg: StrictNonEmptyString
    sorting_retention_rate: StrictNonEmptyString
    postharvest_retention_rate: StrictNonEmptyString
    effective_marketable_quantity_kg: StrictNonEmptyString

    task8_forecast_run_id: StrictPositiveInt
    task9_harvest_state_run_id: StrictPositiveInt
    task8_artifact_hash: SHA256Hex
    task9_result_hash: SHA256Hex
    marketable_policy_version: StrictNonEmptyString
    marketable_policy_hash: SHA256Hex
    row_hash: SHA256Hex

    _validate_quantities = field_validator(*_QUANTITY_FIELDS, mode="before")(_fixed_decimal_string)


class CoreForecastBlocker(_FrozenModel):
    code: CoreForecastBlockerCode
    message: StrictNonEmptyString


class CompleteDailyMarketableCurveResult(_FrozenModel):
    status: Literal["COMPLETED", "BLOCKED"]
    rows: tuple[CompleteDailyMarketableCurveRow, ...]
    curve_hash: SHA256Hex | None
    blockers: tuple[CoreForecastBlocker, ...]

    @model_validator(mode="after")
    def _status_is_consistent(self) -> CompleteDailyMarketableCurveResult:
        if self.status == "COMPLETED":
            if not self.rows or self.curve_hash is None or self.blockers:
                raise ValueError("completed result requires rows/hash and no blockers")
        elif self.rows or self.curve_hash is not None or not self.blockers:
            raise ValueError("blocked result requires blockers and no rows/hash")
        return self
