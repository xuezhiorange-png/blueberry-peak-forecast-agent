from __future__ import annotations

import argparse
import json
from collections.abc import Awaitable, Mapping
from datetime import date, timedelta
from pathlib import Path
from typing import Protocol, TextIO

from pydantic import ValidationError
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
    return _mapping(payload, label="fixture")


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
    request = load_fixture_request(args.fixture, rerun_of_run_id=args.rerun_of)
    async with session_factory() as session:
        async with session.begin():
            result = await executor(
                session,
                request=request,
                upstream_repository=upstream_repository,
            )
    _write_summary(_summary(result), output_json=args.output_json, stdout=stdout)
    if result.status == "BLOCKED":
        blocker = result.blockers[0]
        raise CoreForecastCliError(blocker.code, blocker.message, exit_code=10)
