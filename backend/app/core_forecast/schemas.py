from __future__ import annotations

import re
from datetime import date, datetime, timedelta
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
GitCommitSHA = Annotated[
    str,
    Field(strict=True, min_length=40, max_length=40, pattern=r"^[0-9a-f]{40}$"),
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
    "DAILY_CURVE_NOT_COMPLETED",
    "DAILY_CURVE_ROW_HASH_MISMATCH",
    "DAILY_CURVE_HASH_MISMATCH",
    "DAILY_CURVE_DECIMAL_INVALID",
    "DAILY_CURVE_SCHEMA_INVALID",
    "NO_COMPLETE_7DAY_WINDOW",
    "PEAK_METRIC_INVARIANT_FAILED",
    "UPSTREAM_READ_FAILURE",
    "CORE_FORECAST_PARENT_RUN_NOT_FOUND",
    "CORE_FORECAST_RERUN_SCOPE_MISMATCH",
    "CORE_FORECAST_RERUN_INPUT_UNCHANGED",
    "CORE_FORECAST_CODE_AUTHORITY_NOT_FOUND",
    "CORE_FORECAST_CODE_AUTHORITY_INVALID",
    "CORE_FORECAST_PERSISTENCE_CONFLICT",
    "CORE_FORECAST_PERSISTENCE_INTEGRITY_FAILED",
    "CORE_FORECAST_WRITE_FAILURE",
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
    if not isinstance(value, str) or not value or value.startswith("-") or "e" in value.lower():
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

_FIXED_6_RE = re.compile(r"^(?:0|[1-9]\d*)\.\d{6}$")


def _fixed_decimal_string(value: object) -> str:
    if not isinstance(value, str) or _FIXED_6_RE.fullmatch(value) is None:
        raise ValueError("quantity must be a fixed six-place decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("quantity must be a decimal") from exc
    if not parsed.is_finite() or parsed < 0:
        raise ValueError("quantity must be finite and non-negative")
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


class SingleDayPeakMetric(_FrozenModel):
    date: date
    quantity_kg: StrictNonEmptyString
    tie_break: Literal["EARLIEST_DATE"]

    _validate_quantity = field_validator("quantity_kg", mode="before")(_fixed_decimal_string)


class SustainedSevenDayPeakMetric(_FrozenModel):
    start_date: date
    end_date: date
    cumulative_quantity_kg: StrictNonEmptyString
    daily_average_kg_per_day: StrictNonEmptyString
    window_days: Literal[7]
    metric: Literal["ROLLING_CUMULATIVE"]
    date_continuity: Literal["STRICT_CALENDAR_DAYS"]
    tie_break: Literal["EARLIEST_START_DATE"]

    _validate_quantities = field_validator(
        "cumulative_quantity_kg",
        "daily_average_kg_per_day",
        mode="before",
    )(_fixed_decimal_string)

    @model_validator(mode="after")
    def _window_is_exactly_seven_days(self) -> SustainedSevenDayPeakMetric:
        if self.end_date != self.start_date + timedelta(days=6):
            raise ValueError("seven-day peak end_date must be start_date plus six days")
        return self


class QuantileCoreForecastMetrics(_FrozenModel):
    forecast_quantile: Literal["P50", "P80", "P90"]
    single_day_peak: SingleDayPeakMetric
    sustained_7day_peak: SustainedSevenDayPeakMetric
    season_cumulative_effective_marketable_kg: StrictNonEmptyString

    _validate_season_quantity = field_validator(
        "season_cumulative_effective_marketable_kg",
        mode="before",
    )(_fixed_decimal_string)


class CompleteCoreForecastMetricsResult(_FrozenModel):
    status: Literal["COMPLETED", "BLOCKED"]
    metrics_schema_version: str | None
    date_basis: Literal["HARVEST_BUSINESS_DATE"] | None
    source_curve_hash: SHA256Hex | None
    metrics: tuple[QuantileCoreForecastMetrics, ...]
    metrics_hash: SHA256Hex | None
    blockers: tuple[CoreForecastBlocker, ...]

    @model_validator(mode="after")
    def _status_is_consistent(self) -> CompleteCoreForecastMetricsResult:
        if self.status == "COMPLETED":
            if (
                self.metrics_schema_version != "v0.1-core-forecast-metrics-v1"
                or self.date_basis != "HARVEST_BUSINESS_DATE"
                or self.source_curve_hash is None
                or len(self.metrics) != 3
                or tuple(item.forecast_quantile for item in self.metrics) != ("P50", "P80", "P90")
                or self.metrics_hash is None
                or self.blockers
            ):
                raise ValueError("completed metrics require all quantiles, hashes, and no blockers")
        elif (
            self.metrics_schema_version is not None
            or self.date_basis is not None
            or self.source_curve_hash is not None
            or self.metrics
            or self.metrics_hash is not None
            or not self.blockers
        ):
            raise ValueError(
                "blocked metrics require no metrics or hashes and at least one blocker"
            )
        return self


class ExecuteCoreForecastRunRequest(_FrozenModel):
    curve_request: CompleteDailyMarketableCurveRequest
    retention_policy: MarketableRetentionPolicySnapshot
    rerun_of_run_id: StrictPositiveInt | None = None
    code_authority_id: StrictPositiveInt | None = None


def _timezone_aware(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value


class RegisterCoreForecastCodeAuthority(_FrozenModel):
    """Trusted, separately persisted build/config authority registration."""

    source_commit_sha: GitCommitSHA
    build_artifact_hash: SHA256Hex
    config_bundle_hash: SHA256Hex
    available_at: datetime

    _validate_available_at = field_validator("available_at", mode="before")(_timezone_aware)


class CoreForecastCodeAuthority(RegisterCoreForecastCodeAuthority):
    authority_id: StrictPositiveInt
    authority_schema_version: Literal["v0.1-core-forecast-code-authority-v1"]
    authority_hash: SHA256Hex
    created_at: datetime

    _validate_created_at = field_validator("created_at", mode="before")(_timezone_aware)


class CoreForecastRunSummary(_FrozenModel):
    run_id: StrictPositiveInt
    status: Literal["completed"]
    run_schema_version: Literal[
        "v0.1-core-forecast-run-v1",
        "v0.1-core-forecast-run-authority-v2",
    ]
    request_schema_version: Literal[
        "v0.1-core-forecast-request-v1",
        "v0.1-core-forecast-request-authority-v2",
    ]
    date_basis: Literal["HARVEST_BUSINESS_DATE"]

    forecast_input_hash: SHA256Hex
    request_hash: SHA256Hex
    result_hash: SHA256Hex
    retention_policy_snapshot_hash: SHA256Hex
    curve_hash: SHA256Hex
    metrics_hash: SHA256Hex
    code_authority_id: StrictPositiveInt | None = None
    code_authority_hash: SHA256Hex | None = None
    code_authority_available_at: datetime | None = None

    rerun_of_run_id: StrictPositiveInt | None
    forecast_season_id: StrictPositiveInt
    forecast_season_code: StrictNonEmptyString
    forecast_start_date: date
    forecast_end_date: date
    destination_factory_id: StrictPositiveInt
    task8_forecast_run_id: StrictPositiveInt
    task9_harvest_state_run_id: StrictPositiveInt
    daily_row_count: Annotated[int, Field(strict=True, gt=0)]
    metric_row_count: Literal[3]
    created_at: datetime
    completed_at: datetime

    _validate_created_at = field_validator(
        "created_at",
        "completed_at",
        "code_authority_available_at",
        mode="before",
    )(lambda value: None if value is None else _timezone_aware(value))

    @model_validator(mode="after")
    def _date_range_is_valid(self) -> CoreForecastRunSummary:
        if self.forecast_end_date < self.forecast_start_date:
            raise ValueError("forecast_end_date must be >= forecast_start_date")
        authority_values = (
            self.code_authority_id,
            self.code_authority_hash,
            self.code_authority_available_at,
        )
        authority_bound = self.run_schema_version == "v0.1-core-forecast-run-authority-v2"
        if authority_bound:
            if self.request_schema_version != "v0.1-core-forecast-request-authority-v2" or any(
                value is None for value in authority_values
            ):
                raise ValueError("authority-bound run requires exact persisted code authority")
        elif self.request_schema_version != "v0.1-core-forecast-request-v1" or any(
            value is not None for value in authority_values
        ):
            raise ValueError("legacy run must not carry backfilled code authority")
        return self


class CoreForecastExecutionResult(_FrozenModel):
    status: Literal["COMPLETED", "BLOCKED"]
    run: CoreForecastRunSummary | None
    daily_curve: CompleteDailyMarketableCurveResult | None
    metrics: CompleteCoreForecastMetricsResult | None
    reused_existing_run: bool
    blockers: tuple[CoreForecastBlocker, ...]

    @model_validator(mode="after")
    def _status_is_consistent(self) -> CoreForecastExecutionResult:
        if self.status == "COMPLETED":
            if (
                self.run is None
                or self.daily_curve is None
                or self.daily_curve.status != "COMPLETED"
                or self.metrics is None
                or self.metrics.status != "COMPLETED"
                or self.blockers
            ):
                raise ValueError("completed execution requires complete run, curve, and metrics")
        elif self.run is not None or self.daily_curve is not None or self.metrics is not None:
            raise ValueError("blocked execution must not expose partial output")
        elif not self.blockers or self.reused_existing_run:
            raise ValueError("blocked execution requires blockers and cannot be reused")
        return self


class PersistedCoreForecastRun(_FrozenModel):
    run: CoreForecastRunSummary
    request: ExecuteCoreForecastRunRequest
    daily_curve: CompleteDailyMarketableCurveResult
    metrics: CompleteCoreForecastMetricsResult
    code_authority: CoreForecastCodeAuthority | None = None

    @model_validator(mode="after")
    def _authority_matches_run(self) -> PersistedCoreForecastRun:
        if self.run.code_authority_id is None:
            if self.code_authority is not None or self.request.code_authority_id is not None:
                raise ValueError("legacy persisted run cannot carry code authority")
        elif (
            self.code_authority is None
            or self.request.code_authority_id != self.code_authority.authority_id
            or self.run.code_authority_id != self.code_authority.authority_id
            or self.run.code_authority_hash != self.code_authority.authority_hash
            or self.run.code_authority_available_at != self.code_authority.available_at
        ):
            raise ValueError("persisted code authority does not match run/request")
        return self
