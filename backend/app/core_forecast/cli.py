from __future__ import annotations

import argparse
import json
import re
from collections.abc import Awaitable, Mapping
from datetime import date, timedelta
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Annotated, Literal, NoReturn, Protocol, TextIO

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.core_forecast.application import execute_core_forecast_run
from backend.app.core_forecast.repository import CoreForecastRepository
from backend.app.core_forecast.schemas import (
    QUANTILES,
    CompleteDailyMarketableCurveRequest,
    CoreForecastExecutionResult,
    ExecuteCoreForecastRunRequest,
    MarketableRetentionPolicyEntry,
    MarketableRetentionPolicySnapshot,
)
from backend.app.rolling_backtest.canonical import canonical_json_dumps

FIXTURE_ID = "v0_1_complete_season_case_01"
EXPECTED_CALENDAR_DAYS = 90
EXPECTED_ROW_COUNT = 1080
EXPECTED_POLICY_SCOPE_COUNT = 4
_FIXED_SIX_RE = re.compile(r"^(?:0|[1-9]\d*)\.\d{6}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FIXTURE_QUANTITY_FIELDS = (
    "natural_maturity_supply_kg",
    "opening_mature_inventory_kg",
    "available_mature_quantity_kg",
    "mature_inventory_loss_quantity_kg",
    "harvestable_mature_quantity_kg",
    "effective_harvest_capacity_kg",
    "model_harvested_marketable_quantity_kg",
    "closing_mature_inventory_kg",
    "unharvested_backlog_kg",
    "effective_marketable_quantity_kg",
)
_FIXTURE_RATE_FIELDS = ("sorting_retention_rate", "postharvest_retention_rate")
_FIXTURE_OUTPUT_FIELDS = (
    "date",
    "forecast_quantile",
    "farm_id",
    "subfarm_id",
    "variety_id",
    "destination_factory_id",
    *_FIXTURE_QUANTITY_FIELDS,
    *_FIXTURE_RATE_FIELDS,
    "task8_forecast_run_id",
    "task9_harvest_state_run_id",
    "task8_artifact_hash",
    "task9_result_hash",
    "marketable_policy_version",
    "marketable_policy_hash",
)

FixturePositiveInt = Annotated[int, Field(strict=True, gt=0)]


class _FixtureModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def _fixture_decimal_string(value: object) -> str:
    if not isinstance(value, str) or not value or value.startswith("-"):
        raise ValueError("fixture decimal must be a non-negative string")
    if "e" in value.lower():
        raise ValueError("fixture decimal must not use scientific notation")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("fixture decimal must be parseable") from exc
    if not parsed.is_finite() or parsed < 0 or format(parsed, "f") != value:
        raise ValueError("fixture decimal must be finite and canonical")
    return value


def _fixture_rate_string(value: object) -> str:
    value = _fixture_decimal_string(value)
    if Decimal(value) > Decimal("1"):
        raise ValueError("fixture rate must be within [0, 1]")
    return value


def _fixture_fixed_six_string(value: object) -> str:
    if not isinstance(value, str) or not _FIXED_SIX_RE.fullmatch(value):
        raise ValueError("fixture daily quantity must have exactly six decimal places")
    return _fixture_decimal_string(value)


def _fixture_hash(value: object) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError("fixture hash must be lowercase SHA-256")
    return value


def _fixture_error(message: str) -> NoReturn:
    raise CoreForecastCliError(
        "CORE_FORECAST_CLI_INPUT_INVALID",
        message,
        exit_code=2,
    )


def _fixture_value_decimal(value: object, *, label: str) -> Decimal:
    if not isinstance(value, str):
        _fixture_error(f"{label} must be a Decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise CoreForecastCliError(
            "CORE_FORECAST_CLI_INPUT_INVALID",
            f"{label} must be a parseable Decimal string",
            exit_code=2,
        ) from exc
    if not parsed.is_finite() or parsed < 0:
        _fixture_error(f"{label} must be finite and non-negative")
    return parsed


def _fixture_mapping(value: object, *, label: str) -> Mapping[str, object]:
    return _mapping(value, label=label)


def _fixture_list(value: object, *, label: str) -> list[object]:
    if not isinstance(value, list):
        _fixture_error(f"{label} must be a list")
    return value


def _validate_fixture_semantics(
    payload: Mapping[str, object],
    *,
    start: date,
    end: date,
    factory_id: int,
    scopes: tuple[tuple[int, int, int], ...],
) -> None:
    season = _fixture_mapping(_required(payload, "season", label="fixture"), label="season")
    season_code = _strict_string(
        _required(season, "season_code", label="season"),
        label="season_code",
    )
    if (
        _strict_positive_int(
            _required(season, "calendar_days", label="season"), label="calendar_days"
        )
        != EXPECTED_CALENDAR_DAYS
    ):
        _fixture_error("season calendar_days must be exactly 90")
    if (
        _date(
            _required(season, "forecast_start_date", label="season"),
            label="forecast_start_date",
        )
        != start
        or _date(
            _required(season, "forecast_end_date", label="season"),
            label="forecast_end_date",
        )
        != end
    ):
        _fixture_error("season dates do not match the requested calendar")
    master = _fixture_mapping(
        _required(payload, "master_data", label="fixture"),
        label="master_data",
    )
    farm = _fixture_mapping(_required(master, "farm", label="master_data"), label="farm")
    farm_id = _strict_positive_int(_required(farm, "farm_id", label="farm"), label="farm_id")
    subfarms = [
        _fixture_mapping(item, label="subfarm")
        for item in _fixture_list(
            _required(master, "subfarms", label="master_data"),
            label="subfarms",
        )
    ]
    varieties = [
        _fixture_mapping(item, label="variety")
        for item in _fixture_list(
            _required(master, "varieties", label="master_data"),
            label="varieties",
        )
    ]
    factory = _fixture_mapping(
        _required(master, "destination_factory", label="master_data"),
        label="destination_factory",
    )
    if len(subfarms) != 2 or len(varieties) != 2:
        _fixture_error("master_data must contain exactly two subfarms and two varieties")
    subfarm_ids = {
        _strict_positive_int(_required(item, "subfarm_id", label="subfarm"), label="subfarm_id")
        for item in subfarms
    }
    variety_ids = {
        _strict_positive_int(_required(item, "variety_id", label="variety"), label="variety_id")
        for item in varieties
    }
    if len(subfarm_ids) != 2 or len(variety_ids) != 2:
        _fixture_error("master_data identities must be unique")
    for item in subfarms:
        if (
            _strict_positive_int(
                _required(item, "farm_id", label="subfarm"), label="subfarm farm_id"
            )
            != farm_id
        ):
            _fixture_error("subfarm must belong to the fixture farm")
    if (
        _strict_positive_int(
            _required(factory, "destination_factory_id", label="destination_factory"),
            label="destination_factory_id",
        )
        != factory_id
    ):
        _fixture_error("destination factory identity does not match daily inputs")

    plans = [
        _fixture_mapping(item, label="production plan")
        for item in _fixture_list(
            _required(payload, "production_plan_inputs", label="fixture"),
            label="production_plan_inputs",
        )
    ]
    plan_keys = {
        (
            _strict_positive_int(
                _required(item, "farm_id", label="production plan"), label="farm_id"
            ),
            _strict_positive_int(
                _required(item, "subfarm_id", label="production plan"), label="subfarm_id"
            ),
            _strict_positive_int(
                _required(item, "variety_id", label="production plan"), label="variety_id"
            ),
        )
        for item in plans
    }
    if plan_keys != set(scopes) or len(plans) != len(scopes):
        _fixture_error("production plan must cover each requested scope exactly once")

    task8 = _fixture_mapping(
        _required(payload, "task8_authority", label="fixture"),
        label="task8_authority",
    )
    task9 = _fixture_mapping(
        _required(payload, "task9_authority", label="fixture"),
        label="task9_authority",
    )
    task8_run_id = _strict_positive_int(
        _required(task8, "model_run_id", label="task8_authority"),
        label="task8 model_run_id",
    )
    task9_run_id = _strict_positive_int(
        _required(task9, "run_id", label="task9_authority"),
        label="task9 run_id",
    )
    task8_artifact_hash = _strict_string(
        _required(task8, "artifact_hash", label="task8_authority"),
        label="task8 artifact_hash",
    )
    task9_result_hash = _strict_string(
        _required(task9, "result_hash", label="task9_authority"),
        label="task9 result_hash",
    )
    policy_entries = [
        _fixture_mapping(item, label="policy entry")
        for item in _fixture_list(
            _required(payload, "marketable_retention_policy", label="fixture"),
            label="marketable_retention_policy",
        )
    ]
    policy_by_scope: dict[tuple[int, int, int], Mapping[str, object]] = {}
    for entry in policy_entries:
        key = (
            _strict_positive_int(
                _required(entry, "farm_id", label="policy entry"), label="farm_id"
            ),
            _strict_positive_int(
                _required(entry, "subfarm_id", label="policy entry"), label="subfarm_id"
            ),
            _strict_positive_int(
                _required(entry, "variety_id", label="policy entry"), label="variety_id"
            ),
        )
        if key in policy_by_scope:
            _fixture_error("marketable retention policy scopes must be unique")
        if (
            _strict_string(
                _required(entry, "season_code", label="policy entry"), label="policy season_code"
            )
            != season_code
        ):
            _fixture_error("policy season code does not match season")
        policy_by_scope[key] = entry
    if set(policy_by_scope) != set(scopes):
        _fixture_error("marketable retention policy must cover every requested scope")

    rows = [
        _fixture_mapping(item, label="daily input row")
        for item in _fixture_list(
            _required(payload, "daily_inputs", label="fixture"),
            label="daily_inputs",
        )
    ]
    expected_dates = {start + timedelta(days=offset) for offset in range(EXPECTED_CALENDAR_DAYS)}
    series: dict[tuple[int, int, int, str], list[Mapping[str, object]]] = {}
    for row in rows:
        row_date = _date(_required(row, "date", label="daily input row"), label="date")
        row_key = (
            _strict_positive_int(
                _required(row, "farm_id", label="daily input row"), label="farm_id"
            ),
            _strict_positive_int(
                _required(row, "subfarm_id", label="daily input row"), label="subfarm_id"
            ),
            _strict_positive_int(
                _required(row, "variety_id", label="daily input row"), label="variety_id"
            ),
        )
        quantile = _strict_string(
            _required(row, "forecast_quantile", label="daily input row"),
            label="forecast_quantile",
        )
        if row_date not in expected_dates or row_key not in set(scopes):
            _fixture_error("daily inputs contain a date or scope outside the frozen contract")
        if (
            _strict_positive_int(
                _required(row, "farm_id", label="daily input row"), label="farm_id"
            )
            != farm_id
        ):
            _fixture_error("daily input farm does not match master data")
        if (
            _strict_positive_int(
                _required(row, "destination_factory_id", label="daily input row"),
                label="destination_factory_id",
            )
            != factory_id
        ):
            _fixture_error("daily input factory does not match master data")
        if (
            _strict_positive_int(
                _required(row, "task8_forecast_run_id", label="daily input row"),
                label="task8_forecast_run_id",
            )
            != task8_run_id
        ):
            _fixture_error("daily Task 8 run identity does not match authority")
        if (
            _strict_positive_int(
                _required(row, "task9_harvest_state_run_id", label="daily input row"),
                label="task9_harvest_state_run_id",
            )
            != task9_run_id
        ):
            _fixture_error("daily Task 9 run identity does not match authority")
        if (
            _strict_string(
                _required(row, "task8_artifact_hash", label="daily input row"),
                label="task8_artifact_hash",
            )
            != task8_artifact_hash
        ):
            _fixture_error("daily Task 8 artifact hash does not match authority")
        if (
            _strict_string(
                _required(row, "task9_result_hash", label="daily input row"),
                label="task9_result_hash",
            )
            != task9_result_hash
        ):
            _fixture_error("daily Task 9 result hash does not match authority")
        if not _fixture_list(
            _required(row, "source_references", label="daily input row"),
            label="source_references",
        ):
            _fixture_error("daily input source_references must not be empty")

        policy = policy_by_scope[row_key]
        for field in ("sorting_retention_rate", "postharvest_retention_rate"):
            if _required(row, field, label="daily input row") != _required(
                policy, field, label="policy entry"
            ):
                _fixture_error(f"daily {field} does not match its policy entry")
        if _required(row, "marketable_policy_version", label="daily input row") != _required(
            policy, "version", label="policy entry"
        ):
            _fixture_error("daily policy version does not match its policy entry")
        if _required(row, "marketable_policy_hash", label="daily input row") != _required(
            policy, "hash", label="policy entry"
        ):
            _fixture_error("daily policy hash does not match its policy entry")

        values = {
            field: _fixture_value_decimal(
                _required(row, field, label="daily input row"),
                label=field,
            )
            for field in _FIXTURE_QUANTITY_FIELDS
        }
        if values["available_mature_quantity_kg"] != (
            values["opening_mature_inventory_kg"] + values["natural_maturity_supply_kg"]
        ):
            _fixture_error("daily available mature quantity violates state equation")
        if values["harvestable_mature_quantity_kg"] != (
            values["available_mature_quantity_kg"] - values["mature_inventory_loss_quantity_kg"]
        ):
            _fixture_error("daily harvestable mature quantity violates state equation")
        if (
            values["model_harvested_marketable_quantity_kg"]
            > values["harvestable_mature_quantity_kg"]
        ):
            _fixture_error("daily harvested quantity exceeds harvestable quantity")
        if (
            values["model_harvested_marketable_quantity_kg"]
            > values["effective_harvest_capacity_kg"]
        ):
            _fixture_error("daily harvested quantity exceeds effective capacity")
        if values["closing_mature_inventory_kg"] != (
            values["harvestable_mature_quantity_kg"]
            - values["model_harvested_marketable_quantity_kg"]
        ):
            _fixture_error("daily closing inventory violates state equation")
        if values["unharvested_backlog_kg"] != values["closing_mature_inventory_kg"]:
            _fixture_error("daily backlog violates state equation")
        with localcontext() as context:
            context.prec = 50
            expected_effective = (
                values["model_harvested_marketable_quantity_kg"]
                * Decimal(
                    _strict_string(
                        _required(row, "sorting_retention_rate", label="daily input row"),
                        label="sorting_retention_rate",
                    )
                )
                * Decimal(
                    _strict_string(
                        _required(row, "postharvest_retention_rate", label="daily input row"),
                        label="postharvest_retention_rate",
                    )
                )
            ).quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)
        if values["effective_marketable_quantity_kg"] != expected_effective:
            _fixture_error("daily effective marketable quantity violates retention formula")
        series.setdefault((*row_key, quantile), []).append(row)

    if len(rows) != EXPECTED_ROW_COUNT:
        _fixture_error("fixture must contain exactly 1080 daily input rows")
    if len(series) != len(scopes) * len(QUANTILES):
        _fixture_error("daily inputs must contain exactly twelve complete series")
    for series_rows in series.values():
        ordered = sorted(series_rows, key=lambda item: _date(item["date"], label="date"))
        if [_date(item["date"], label="date") for item in ordered] != sorted(expected_dates):
            _fixture_error("daily input series must contain every calendar date exactly once")
        for previous, current in zip(ordered, ordered[1:], strict=False):
            if _fixture_value_decimal(
                _required(current, "opening_mature_inventory_kg", label="daily input row"),
                label="opening_mature_inventory_kg",
            ) != _fixture_value_decimal(
                _required(previous, "closing_mature_inventory_kg", label="daily input row"),
                label="closing_mature_inventory_kg",
            ):
                _fixture_error("daily input series violates cross-day inventory continuity")


def _validate_result_against_fixture(
    payload: Mapping[str, object],
    result: CoreForecastExecutionResult,
) -> None:
    if result.status != "COMPLETED":
        return
    if result.daily_curve is None:
        _fixture_error("completed CLI result did not contain a daily curve")
    expected_rows = [
        _fixture_mapping(item, label="daily input row")
        for item in _fixture_list(
            _required(payload, "daily_inputs", label="fixture"),
            label="daily_inputs",
        )
    ]
    expected_by_key: dict[tuple[str, int, int, int, str], Mapping[str, object]] = {}
    for row in expected_rows:
        key = (
            _strict_string(_required(row, "date", label="daily input row"), label="date"),
            _strict_positive_int(
                _required(row, "farm_id", label="daily input row"), label="farm_id"
            ),
            _strict_positive_int(
                _required(row, "subfarm_id", label="daily input row"), label="subfarm_id"
            ),
            _strict_positive_int(
                _required(row, "variety_id", label="daily input row"), label="variety_id"
            ),
            _strict_string(
                _required(row, "forecast_quantile", label="daily input row"),
                label="forecast_quantile",
            ),
        )
        expected_by_key[key] = row
    actual_rows = result.daily_curve.rows
    actual_by_key = {
        (
            row.date.isoformat(),
            row.farm_id,
            row.subfarm_id,
            row.variety_id,
            str(row.forecast_quantile),
        ): row
        for row in actual_rows
    }
    if set(actual_by_key) != set(expected_by_key) or len(actual_rows) != EXPECTED_ROW_COUNT:
        _fixture_error("production daily output does not match the complete fixture grid")
    for key, expected in expected_by_key.items():
        actual = actual_by_key[key].model_dump(mode="json")
        for field in _FIXTURE_OUTPUT_FIELDS:
            if actual[field] != expected[field]:
                _fixture_error(f"production daily output does not match fixture field {field}")


class _FixtureSeason(_FixtureModel):
    season_code: str
    forecast_start_date: str
    forecast_end_date: str
    calendar_days: FixturePositiveInt


class _FixtureFarm(_FixtureModel):
    farm_id: FixturePositiveInt
    name: str


class _FixtureSubfarm(_FixtureModel):
    subfarm_id: FixturePositiveInt
    farm_id: FixturePositiveInt
    name: str


class _FixtureVariety(_FixtureModel):
    variety_id: FixturePositiveInt
    code: str
    name: str


class _FixtureLocation(_FixtureModel):
    location_id: FixturePositiveInt
    region_code: str
    timezone: str


class _FixtureFactory(_FixtureModel):
    destination_factory_id: FixturePositiveInt
    logical_name: str
    timezone: str


class _FixtureMasterData(_FixtureModel):
    farm: _FixtureFarm
    subfarms: list[_FixtureSubfarm]
    varieties: list[_FixtureVariety]
    location: _FixtureLocation
    destination_factory: _FixtureFactory


class _FixturePhenology(_FixtureModel):
    flowering_start_date: str
    flowering_peak_date: str
    flowering_end_date: str
    first_pick_date: str


class _FixtureSource(_FixtureModel):
    name: str
    version: str
    hash: Annotated[str, Field(strict=True, min_length=64, max_length=64)]

    _validate_hash = field_validator("hash")(_fixture_hash)


class _FixtureProductionPlan(_FixtureModel):
    farm_id: FixturePositiveInt
    subfarm_id: FixturePositiveInt
    variety_id: FixturePositiveInt
    planting_area_mu: str
    expected_yield_kg_per_mu: str
    marketable_rate: str
    expected_total_marketable_kg: str
    tree_age_years: str
    facility_type: str
    phenology: _FixturePhenology
    effective_from: str
    effective_to: str | None
    source: _FixtureSource

    _validate_decimals = field_validator(
        "planting_area_mu",
        "expected_yield_kg_per_mu",
        "expected_total_marketable_kg",
        "tree_age_years",
    )(_fixture_decimal_string)
    _validate_market_rate = field_validator("marketable_rate")(_fixture_rate_string)


class _FixtureTask8Authority(_FixtureModel):
    basis: Literal["MARKETABLE"]
    model_run_id: FixturePositiveInt
    model_run_identity: str
    artifact_identity: str
    artifact_hash: str
    config_version: str
    config_hash: str
    source: str

    _validate_hashes = field_validator("artifact_hash", "config_hash")(_fixture_hash)


class _FixtureTask9Authority(_FixtureModel):
    run_id: FixturePositiveInt
    run_identity: str
    result_hash: str
    source: str

    _validate_hashes = field_validator("result_hash")(_fixture_hash)


class _FixturePolicyEntry(_FixtureModel):
    season_code: str
    farm_id: FixturePositiveInt
    subfarm_id: FixturePositiveInt
    variety_id: FixturePositiveInt
    sorting_retention_rate: str
    postharvest_retention_rate: str
    source: str
    version: str
    hash: str

    _validate_rates = field_validator("sorting_retention_rate", "postharvest_retention_rate")(
        _fixture_fixed_six_string
    )
    _validate_hash = field_validator("hash")(_fixture_hash)


class _FixtureDailyInput(_FixtureModel):
    date: str
    forecast_quantile: Literal["P50", "P80", "P90"]
    farm_id: FixturePositiveInt
    subfarm_id: FixturePositiveInt
    variety_id: FixturePositiveInt
    destination_factory_id: FixturePositiveInt
    natural_maturity_supply_kg: str
    opening_mature_inventory_kg: str
    available_mature_quantity_kg: str
    mature_inventory_loss_quantity_kg: str
    harvestable_mature_quantity_kg: str
    effective_harvest_capacity_kg: str
    model_harvested_marketable_quantity_kg: str
    closing_mature_inventory_kg: str
    unharvested_backlog_kg: str
    sorting_retention_rate: str
    postharvest_retention_rate: str
    effective_marketable_quantity_kg: str
    task8_forecast_run_id: FixturePositiveInt
    task9_harvest_state_run_id: FixturePositiveInt
    task8_artifact_hash: str
    task9_result_hash: str
    marketable_policy_version: str
    marketable_policy_hash: str
    planned_picker_count: str
    picker_productivity_kg_per_day: str
    labor_availability_ratio: str
    operational_efficiency_ratio: str
    weather_efficiency_ratio: str
    event_tags: list[str]
    source_references: list[str]

    _validate_quantities = field_validator(*_FIXTURE_QUANTITY_FIELDS, *_FIXTURE_RATE_FIELDS)(
        _fixture_fixed_six_string
    )
    _validate_hashes = field_validator("task8_artifact_hash", "task9_result_hash")(_fixture_hash)
    _validate_policy_hash = field_validator("marketable_policy_hash")(_fixture_hash)
    _validate_other_decimals = field_validator(
        "planned_picker_count",
        "picker_productivity_kg_per_day",
        "labor_availability_ratio",
        "operational_efficiency_ratio",
        "weather_efficiency_ratio",
    )(_fixture_decimal_string)


class _FixturePayload(_FixtureModel):
    fixture_id: str
    season: _FixtureSeason
    master_data: _FixtureMasterData
    production_plan_inputs: list[_FixtureProductionPlan]
    task8_authority: _FixtureTask8Authority
    task9_authority: _FixtureTask9Authority
    marketable_retention_policy: list[_FixturePolicyEntry]
    daily_inputs: list[_FixtureDailyInput]


class CoreForecastCliError(RuntimeError):
    def __init__(self, code: str, message: str, *, exit_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code


class CoreForecastExecutor(Protocol):
    def __call__(
        self,
        session: AsyncSession,
        *,
        request: ExecuteCoreForecastRunRequest,
        upstream_repository: CoreForecastRepository | None = None,
    ) -> Awaitable[CoreForecastExecutionResult]: ...


def register_core_forecast_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser(
        "core-forecast",
        help="execute the V0.1 complete-season core forecast",
    )
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--output-json", default=None)
    parser.add_argument("--rerun-of", type=int, default=None)


def _mapping(value: object, *, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise CoreForecastCliError(
            "CORE_FORECAST_CLI_INPUT_INVALID",
            f"{label} must be a JSON object",
            exit_code=2,
        )
    return value


def _required(mapping: Mapping[str, object], key: str, *, label: str) -> object:
    if key not in mapping:
        raise CoreForecastCliError(
            "CORE_FORECAST_CLI_INPUT_INVALID",
            f"{label} is missing {key}",
            exit_code=2,
        )
    return mapping[key]


def _strict_positive_int(value: object, *, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise CoreForecastCliError(
            "CORE_FORECAST_CLI_INPUT_INVALID",
            f"{label} must be a positive integer",
            exit_code=2,
        )
    return value


def _strict_string(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise CoreForecastCliError(
            "CORE_FORECAST_CLI_INPUT_INVALID",
            f"{label} must be a non-empty string",
            exit_code=2,
        )
    return value


def _date(value: object, *, label: str) -> date:
    try:
        return date.fromisoformat(_strict_string(value, label=label))
    except ValueError as exc:
        raise CoreForecastCliError(
            "CORE_FORECAST_CLI_INPUT_INVALID",
            f"{label} must be an ISO date",
            exit_code=2,
        ) from exc


def _fixture_season_id(season: Mapping[str, object]) -> int:
    explicit = season.get("forecast_season_id")
    if explicit is not None:
        return _strict_positive_int(explicit, label="season.forecast_season_id")
    code = _strict_string(_required(season, "season_code", label="season"), label="season_code")
    prefix = code.split("-", maxsplit=1)[0]
    try:
        return _strict_positive_int(int(prefix), label="season_code prefix")
    except ValueError as exc:
        raise CoreForecastCliError(
            "CORE_FORECAST_CLI_INPUT_INVALID",
            "season code must contain a numeric season id",
            exit_code=2,
        ) from exc


def _read_fixture(path: str) -> Mapping[str, object]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoreForecastCliError(
            "CORE_FORECAST_CLI_INPUT_INVALID",
            "fixture could not be read as JSON",
            exit_code=2,
        ) from exc
    try:
        fixture = _FixturePayload.model_validate(payload)
    except ValidationError as exc:
        first_error = exc.errors()[0]
        location = ".".join(str(item) for item in first_error.get("loc", ()))
        _fixture_error(f"fixture schema is invalid at {location or 'root'}")
    return fixture.model_dump(mode="python")


def _validate_daily_inputs(
    payload: Mapping[str, object],
    *,
    start: date,
    end: date,
    factory_id: int,
) -> tuple[tuple[int, int, int], ...]:
    raw_rows = _required(payload, "daily_inputs", label="fixture")
    if not isinstance(raw_rows, list) or len(raw_rows) != EXPECTED_ROW_COUNT:
        raise CoreForecastCliError(
            "CORE_FORECAST_CLI_INPUT_INVALID",
            "fixture must contain exactly 1080 daily input rows",
            exit_code=2,
        )
    expected_dates = {start + timedelta(days=offset) for offset in range(EXPECTED_CALENDAR_DAYS)}
    keys: set[tuple[date, int, int, int, str]] = set()
    scopes: set[tuple[int, int, int]] = set()
    quantiles: set[str] = set()
    factories: set[int] = set()
    for raw_row in raw_rows:
        row = _mapping(raw_row, label="daily input row")
        row_date = _date(_required(row, "date", label="daily input row"), label="date")
        farm_id = _strict_positive_int(
            _required(row, "farm_id", label="daily input row"),
            label="farm_id",
        )
        subfarm_id = _strict_positive_int(
            _required(row, "subfarm_id", label="daily input row"),
            label="subfarm_id",
        )
        variety_id = _strict_positive_int(
            _required(row, "variety_id", label="daily input row"),
            label="variety_id",
        )
        quantile = _strict_string(
            _required(row, "forecast_quantile", label="daily input row"),
            label="forecast_quantile",
        )
        row_factory = _strict_positive_int(
            _required(row, "destination_factory_id", label="daily input row"),
            label="destination_factory_id",
        )
        key = (row_date, farm_id, subfarm_id, variety_id, quantile)
        if key in keys or row_date not in expected_dates or row_factory != factory_id:
            raise CoreForecastCliError(
                "CORE_FORECAST_CLI_INPUT_INVALID",
                "fixture daily inputs are not a complete unique canonical grid",
                exit_code=2,
            )
        keys.add(key)
        scopes.add((farm_id, subfarm_id, variety_id))
        quantiles.add(quantile)
        factories.add(row_factory)
    if (
        {item[0] for item in keys} != expected_dates
        or quantiles != set(QUANTILES)
        or len(scopes) != EXPECTED_POLICY_SCOPE_COUNT
        or factories != {factory_id}
    ):
        raise CoreForecastCliError(
            "CORE_FORECAST_CLI_INPUT_INVALID",
            "fixture daily inputs do not cover the complete season scope",
            exit_code=2,
        )
    return tuple(sorted(scopes))


def load_fixture_request(
    path: str,
    *,
    rerun_of_run_id: int | None = None,
) -> ExecuteCoreForecastRunRequest:
    payload = _read_fixture(path)
    if payload.get("fixture_id") != FIXTURE_ID:
        raise CoreForecastCliError(
            "CORE_FORECAST_CLI_INPUT_INVALID",
            f"fixture_id must be {FIXTURE_ID}",
            exit_code=2,
        )
    season = _mapping(_required(payload, "season", label="fixture"), label="season")
    master_data = _mapping(
        _required(payload, "master_data", label="fixture"),
        label="master_data",
    )
    factory = _mapping(
        _required(master_data, "destination_factory", label="master_data"),
        label="destination_factory",
    )
    season_code = _strict_string(
        _required(season, "season_code", label="season"),
        label="season_code",
    )
    start = _date(
        _required(season, "forecast_start_date", label="season"),
        label="forecast_start_date",
    )
    end = _date(_required(season, "forecast_end_date", label="season"), label="forecast_end_date")
    if end < start or (end - start).days + 1 != EXPECTED_CALENDAR_DAYS:
        raise CoreForecastCliError(
            "CORE_FORECAST_CLI_INPUT_INVALID",
            "fixture must describe exactly 90 calendar days",
            exit_code=2,
        )
    factory_id = _strict_positive_int(
        _required(factory, "destination_factory_id", label="destination_factory"),
        label="destination_factory_id",
    )
    scopes = _validate_daily_inputs(payload, start=start, end=end, factory_id=factory_id)
    _validate_fixture_semantics(
        payload,
        start=start,
        end=end,
        factory_id=factory_id,
        scopes=scopes,
    )

    task8 = _mapping(
        _required(payload, "task8_authority", label="fixture"),
        label="task8_authority",
    )
    task9 = _mapping(
        _required(payload, "task9_authority", label="fixture"),
        label="task9_authority",
    )
    season_id = _fixture_season_id(season)
    policy_rows = _required(payload, "marketable_retention_policy", label="fixture")
    if not isinstance(policy_rows, list):
        raise CoreForecastCliError(
            "CORE_FORECAST_CLI_INPUT_INVALID",
            "marketable_retention_policy must be a list",
            exit_code=2,
        )
    try:
        policy = MarketableRetentionPolicySnapshot(
            entries=tuple(
                MarketableRetentionPolicyEntry(
                    forecast_season_id=season_id,
                    forecast_season_code=_strict_string(
                        _required(item, "season_code", label="policy entry"),
                        label="policy season_code",
                    ),
                    farm_id=_strict_positive_int(
                        _required(item, "farm_id", label="policy entry"),
                        label="policy farm_id",
                    ),
                    subfarm_id=_strict_positive_int(
                        _required(item, "subfarm_id", label="policy entry"),
                        label="policy subfarm_id",
                    ),
                    variety_id=_strict_positive_int(
                        _required(item, "variety_id", label="policy entry"),
                        label="policy variety_id",
                    ),
                    sorting_retention_rate=_strict_string(
                        _required(item, "sorting_retention_rate", label="policy entry"),
                        label="sorting_retention_rate",
                    ),
                    postharvest_retention_rate=_strict_string(
                        _required(item, "postharvest_retention_rate", label="policy entry"),
                        label="postharvest_retention_rate",
                    ),
                    source=_strict_string(
                        _required(item, "source", label="policy entry"),
                        label="policy source",
                    ),
                    version=_strict_string(
                        _required(item, "version", label="policy entry"),
                        label="policy version",
                    ),
                    hash=_strict_string(
                        _required(item, "hash", label="policy entry"),
                        label="policy hash",
                    ),
                )
                for item in (_mapping(value, label="policy entry") for value in policy_rows)
            )
        )
    except ValidationError as exc:
        raise CoreForecastCliError(
            "CORE_FORECAST_CLI_INPUT_INVALID",
            "marketable retention policy failed strict validation",
            exit_code=2,
        ) from exc
    policy_keys = {(entry.farm_id, entry.subfarm_id, entry.variety_id) for entry in policy.entries}
    if policy_keys != set(scopes) or len(policy.entries) != EXPECTED_POLICY_SCOPE_COUNT:
        raise CoreForecastCliError(
            "CORE_FORECAST_CLI_INPUT_INVALID",
            "retention policy does not exactly cover the requested scopes",
            exit_code=2,
        )
    try:
        request = CompleteDailyMarketableCurveRequest(
            forecast_season_id=season_id,
            forecast_season_code=season_code,
            forecast_start_date=start,
            forecast_end_date=end,
            destination_factory_id=factory_id,
            task8_forecast_run_id=_strict_positive_int(
                _required(task8, "model_run_id", label="task8_authority"),
                label="task8 model_run_id",
            ),
            task9_harvest_state_run_id=_strict_positive_int(
                _required(task9, "run_id", label="task9_authority"),
                label="task9 run_id",
            ),
            scopes=tuple(
                {
                    "farm_id": farm_id,
                    "subfarm_id": subfarm_id,
                    "variety_id": variety_id,
                }
                for farm_id, subfarm_id, variety_id in scopes
            ),
        )
        return ExecuteCoreForecastRunRequest(
            curve_request=request,
            retention_policy=policy,
            rerun_of_run_id=rerun_of_run_id,
        )
    except ValidationError as exc:
        raise CoreForecastCliError(
            "CORE_FORECAST_CLI_INPUT_INVALID",
            "fixture request failed strict validation",
            exit_code=2,
        ) from exc


def _summary(result: CoreForecastExecutionResult) -> Mapping[str, object]:
    if result.status == "BLOCKED":
        return {
            "status": result.status,
            "reused_existing_run": False,
            "blockers": [blocker.model_dump(mode="json") for blocker in result.blockers],
        }
    assert result.run is not None
    assert result.metrics is not None
    metrics = []
    for item in result.metrics.metrics:
        metrics.append(
            {
                "forecast_quantile": item.forecast_quantile,
                "single_day_peak_date": item.single_day_peak.date.isoformat(),
                "single_day_peak_quantity_kg": item.single_day_peak.quantity_kg,
                "sustained_7day_start_date": item.sustained_7day_peak.start_date.isoformat(),
                "sustained_7day_end_date": item.sustained_7day_peak.end_date.isoformat(),
                "sustained_7day_cumulative_kg": item.sustained_7day_peak.cumulative_quantity_kg,
                "sustained_7day_daily_average_kg_per_day": (
                    item.sustained_7day_peak.daily_average_kg_per_day
                ),
                "season_cumulative_kg": item.season_cumulative_effective_marketable_kg,
            }
        )
    return {
        "status": result.status,
        "reused_existing_run": result.reused_existing_run,
        "run_id": result.run.run_id,
        "request_hash": result.run.request_hash,
        "result_hash": result.run.result_hash,
        "curve_hash": result.run.curve_hash,
        "metrics_hash": result.run.metrics_hash,
        "forecast_start_date": result.run.forecast_start_date.isoformat(),
        "forecast_end_date": result.run.forecast_end_date.isoformat(),
        "daily_row_count": result.run.daily_row_count,
        "metric_count": result.run.metric_row_count,
        "metrics": metrics,
    }


def _write_summary(
    summary: Mapping[str, object],
    *,
    output_json: str | None,
    stdout: TextIO,
) -> None:
    content = f"{canonical_json_dumps(summary)}\n"
    stdout.write(content)
    stdout.flush()
    if output_json is not None:
        try:
            Path(output_json).write_text(content, encoding="utf-8")
        except OSError as exc:
            raise CoreForecastCliError(
                "CORE_FORECAST_CLI_OUTPUT_FAILURE",
                "output JSON could not be written",
                exit_code=3,
            ) from exc


async def dispatch_core_forecast(
    args: argparse.Namespace,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    stdout: TextIO,
    executor: CoreForecastExecutor = execute_core_forecast_run,
    upstream_repository: CoreForecastRepository | None = None,
) -> None:
    payload = _read_fixture(args.fixture)
    request = load_fixture_request(args.fixture, rerun_of_run_id=args.rerun_of)
    async with session_factory() as session:
        async with session.begin():
            result = await executor(
                session,
                request=request,
                upstream_repository=upstream_repository,
            )
            _validate_result_against_fixture(payload, result)
    _write_summary(_summary(result), output_json=args.output_json, stdout=stdout)
    if result.status == "BLOCKED":
        blocker = result.blockers[0]
        raise CoreForecastCliError(blocker.code, blocker.message, exit_code=10)
