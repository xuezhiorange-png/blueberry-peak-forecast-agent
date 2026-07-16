from __future__ import annotations

import copy
import json
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from io import StringIO
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.cli import run_cli
from backend.app.core_forecast.application import execute_core_forecast_run
from backend.app.core_forecast.cli import load_fixture_request
from backend.app.core_forecast.schemas import (
    CoreForecastBlocker,
    CoreForecastExecutionResult,
)
from backend.app.models.core_forecast import (
    CoreForecastDailyRowModel,
    CoreForecastMetricModel,
    CoreForecastRunModel,
)
from backend.tests.core_forecast.test_complete_daily_curve_service import (
    FixtureRepository,
    _sources,
)

FIXTURE = Path("backend/tests/fixtures/v0_1_complete_season_case_01/input.json")


def _valid_policy_rerun_payload() -> dict[str, object]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    policy_rows = payload["marketable_retention_policy"]
    assert isinstance(policy_rows, list)
    policy = policy_rows[0]
    assert isinstance(policy, dict)
    new_policy_hash = "e" * 64
    policy["sorting_retention_rate"] = "0.990000"
    policy["hash"] = new_policy_hash
    daily_rows = payload["daily_inputs"]
    assert isinstance(daily_rows, list)
    for row in daily_rows:
        assert isinstance(row, dict)
        if (row["farm_id"], row["subfarm_id"], row["variety_id"]) != (101, 1101, 2101):
            continue
        row["sorting_retention_rate"] = "0.990000"
        row["marketable_policy_hash"] = new_policy_hash
        with localcontext() as context:
            context.prec = 50
            effective = (
                Decimal(row["model_harvested_marketable_quantity_kg"])
                * Decimal("0.990000")
                * Decimal(row["postharvest_retention_rate"])
            ).quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)
        row["effective_marketable_quantity_kg"] = format(effective, ".6f")
    return copy.deepcopy(payload)


def _session_factory(sqlite_session: AsyncSession) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=sqlite_session.bind,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def _fixture_executor(
    session: AsyncSession,
    *,
    request,
    upstream_repository=None,
) -> CoreForecastExecutionResult:
    task8, task9 = _sources()
    return await execute_core_forecast_run(
        session,
        request=request,
        upstream_repository=FixtureRepository(task8, task9),
    )


def _invoke(
    sqlite_session: AsyncSession,
    fixture: Path = FIXTURE,
    *,
    output_json: Path | None = None,
    rerun_of: int | None = None,
    executor=_fixture_executor,
) -> tuple[int, str, str]:
    stdout = StringIO()
    stderr = StringIO()
    argv = ["core-forecast", "--fixture", str(fixture)]
    if output_json is not None:
        argv.extend(["--output-json", str(output_json)])
    if rerun_of is not None:
        argv.extend(["--rerun-of", str(rerun_of)])
    code = run_cli(
        argv,
        session_factory=_session_factory(sqlite_session),
        stdout=stdout,
        stderr=stderr,
        core_executor=executor,
    )
    return code, stdout.getvalue(), stderr.getvalue()


@pytest.mark.unit
@pytest.mark.contract
async def test_core_forecast_cli_full_season_success(
    sqlite_session: AsyncSession,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "summary.json"
    code, stdout, stderr = _invoke(sqlite_session, output_json=output_path)
    assert code == 0
    assert stderr == ""
    summary = json.loads(stdout)
    assert summary["status"] == "COMPLETED"
    assert summary["daily_row_count"] == 1080
    assert summary["metric_count"] == 3
    assert summary["forecast_start_date"] == "2026-03-01"
    assert summary["forecast_end_date"] == "2026-05-29"
    assert json.loads(output_path.read_text(encoding="utf-8")) == summary
    assert [item["forecast_quantile"] for item in summary["metrics"]] == ["P50", "P80", "P90"]


@pytest.mark.unit
@pytest.mark.contract
async def test_core_forecast_cli_json_output_is_deterministic(
    sqlite_session: AsyncSession,
    tmp_path: Path,
) -> None:
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    first_code, first_stdout, _ = _invoke(sqlite_session, output_json=first_path)
    second_code, second_stdout, _ = _invoke(sqlite_session, output_json=second_path)
    assert first_code == second_code == 0
    first = json.loads(first_stdout)
    second = json.loads(second_stdout)
    assert first["run_id"] == second["run_id"]
    assert first["result_hash"] == second["result_hash"]
    assert second["reused_existing_run"] is True
    assert first["metrics"] == second["metrics"]


@pytest.mark.unit
async def test_core_forecast_cli_same_request_is_idempotent(
    sqlite_session: AsyncSession,
) -> None:
    _invoke(sqlite_session)
    _invoke(sqlite_session)
    assert await sqlite_session.scalar(select(func.count(CoreForecastRunModel.id))) == 1
    assert await sqlite_session.scalar(select(func.count(CoreForecastDailyRowModel.id))) == 1080
    assert await sqlite_session.scalar(select(func.count(CoreForecastMetricModel.id))) == 3


@pytest.mark.unit
async def test_core_forecast_cli_explicit_rerun_preserves_parent(
    sqlite_session: AsyncSession,
    tmp_path: Path,
) -> None:
    first_code, first_stdout, _ = _invoke(sqlite_session)
    assert first_code == 0
    parent = json.loads(first_stdout)
    rerun_payload = _valid_policy_rerun_payload()
    rerun_path = tmp_path / "rerun.json"
    rerun_path.write_text(json.dumps(rerun_payload), encoding="utf-8")
    child_code, child_stdout, child_stderr = _invoke(
        sqlite_session,
        rerun_path,
        rerun_of=parent["run_id"],
    )
    assert child_code == 0
    assert child_stderr == ""
    child = json.loads(child_stdout)
    assert child["run_id"] != parent["run_id"]
    assert child["request_hash"] != parent["request_hash"]
    assert child["result_hash"] != parent["result_hash"]


@pytest.mark.unit
async def test_core_forecast_cli_unchanged_rerun_is_rejected(
    sqlite_session: AsyncSession,
) -> None:
    first_code, first_stdout, _ = _invoke(sqlite_session)
    assert first_code == 0
    parent_id = json.loads(first_stdout)["run_id"]
    code, stdout, stderr = _invoke(sqlite_session, rerun_of=parent_id)
    assert code != 0
    assert json.loads(stdout)["status"] == "BLOCKED"
    assert "CORE_FORECAST_RERUN_INPUT_UNCHANGED" in stderr
    assert await sqlite_session.scalar(select(func.count(CoreForecastRunModel.id))) == 1


@pytest.mark.unit
async def test_core_forecast_cli_blocked_execution_writes_nothing(
    sqlite_session: AsyncSession,
) -> None:
    async def blocked_executor(session, *, request, upstream_repository=None):
        return CoreForecastExecutionResult(
            status="BLOCKED",
            run=None,
            daily_curve=None,
            metrics=None,
            reused_existing_run=False,
            blockers=(
                CoreForecastBlocker(
                    code="TASK8_AUTHORITY_NOT_FOUND",
                    message="fixture authority is unavailable",
                ),
            ),
        )

    code, stdout, stderr = _invoke(sqlite_session, executor=blocked_executor)
    assert code != 0
    assert json.loads(stdout)["status"] == "BLOCKED"
    assert "TASK8_AUTHORITY_NOT_FOUND" in stderr
    assert await sqlite_session.scalar(select(func.count(CoreForecastRunModel.id))) == 0
    assert await sqlite_session.scalar(select(func.count(CoreForecastDailyRowModel.id))) == 0
    assert await sqlite_session.scalar(select(func.count(CoreForecastMetricModel.id))) == 0


@pytest.mark.unit
async def test_core_forecast_cli_invalid_fixture_exits_nonzero(
    sqlite_session: AsyncSession,
    tmp_path: Path,
) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps({"fixture_id": "wrong"}), encoding="utf-8")
    code, stdout, stderr = _invoke(sqlite_session, invalid)
    assert code != 0
    assert stdout == ""
    assert "CORE_FORECAST_CLI_INPUT_INVALID" in stderr
    assert await sqlite_session.scalar(select(func.count(CoreForecastRunModel.id))) == 0


@pytest.mark.unit
def test_core_forecast_fixture_request_is_strictly_reconstructable() -> None:
    request = load_fixture_request(str(FIXTURE))
    assert request.curve_request.forecast_season_id == 2026
    assert len(request.curve_request.scopes) == 4
    assert len(request.retention_policy.entries) == 4


async def _assert_invalid_fixture(
    sqlite_session: AsyncSession,
    tmp_path: Path,
    payload: dict[str, object],
) -> None:
    path = tmp_path / "invalid-fixture.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    code, stdout, stderr = _invoke(sqlite_session, path)
    assert code != 0
    assert stdout == ""
    assert "CORE_FORECAST_CLI_INPUT_INVALID" in stderr
    assert await sqlite_session.scalar(select(func.count(CoreForecastRunModel.id))) == 0
    assert await sqlite_session.scalar(select(func.count(CoreForecastDailyRowModel.id))) == 0
    assert await sqlite_session.scalar(select(func.count(CoreForecastMetricModel.id))) == 0


def _fixture_payload() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.mark.unit
async def test_cli_rejects_missing_daily_quantity_field(
    sqlite_session: AsyncSession,
    tmp_path: Path,
) -> None:
    payload = _fixture_payload()
    assert isinstance(payload["daily_inputs"], list)
    assert isinstance(payload["daily_inputs"][0], dict)
    del payload["daily_inputs"][0]["natural_maturity_supply_kg"]
    await _assert_invalid_fixture(sqlite_session, tmp_path, payload)


@pytest.mark.unit
async def test_cli_rejects_native_float_daily_quantity(
    sqlite_session: AsyncSession,
    tmp_path: Path,
) -> None:
    payload = _fixture_payload()
    assert isinstance(payload["daily_inputs"], list)
    assert isinstance(payload["daily_inputs"][0], dict)
    payload["daily_inputs"][0]["natural_maturity_supply_kg"] = 1.0
    await _assert_invalid_fixture(sqlite_session, tmp_path, payload)


@pytest.mark.unit
async def test_cli_rejects_daily_state_equation_mismatch(
    sqlite_session: AsyncSession,
    tmp_path: Path,
) -> None:
    payload = _fixture_payload()
    assert isinstance(payload["daily_inputs"], list)
    assert isinstance(payload["daily_inputs"][0], dict)
    payload["daily_inputs"][0]["available_mature_quantity_kg"] = "999.000000"
    await _assert_invalid_fixture(sqlite_session, tmp_path, payload)


@pytest.mark.unit
async def test_cli_rejects_cross_day_inventory_break(
    sqlite_session: AsyncSession,
    tmp_path: Path,
) -> None:
    payload = _fixture_payload()
    assert isinstance(payload["daily_inputs"], list)
    current = next(
        row
        for row in payload["daily_inputs"]
        if isinstance(row, dict)
        and row["date"] == "2026-03-02"
        and row["forecast_quantile"] == "P50"
        and row["subfarm_id"] == 1101
        and row["variety_id"] == 2101
    )
    current["opening_mature_inventory_kg"] = "999.000000"
    current["available_mature_quantity_kg"] = "1009.000000"
    current["harvestable_mature_quantity_kg"] = "1009.000000"
    current["closing_mature_inventory_kg"] = "1009.000000"
    current["unharvested_backlog_kg"] = "1009.000000"
    await _assert_invalid_fixture(sqlite_session, tmp_path, payload)


@pytest.mark.unit
async def test_cli_rejects_task8_artifact_hash_mismatch(
    sqlite_session: AsyncSession,
    tmp_path: Path,
) -> None:
    payload = _fixture_payload()
    assert isinstance(payload["task8_authority"], dict)
    payload["task8_authority"]["artifact_hash"] = "c" * 64
    await _assert_invalid_fixture(sqlite_session, tmp_path, payload)


@pytest.mark.unit
async def test_cli_rejects_task9_result_hash_mismatch(
    sqlite_session: AsyncSession,
    tmp_path: Path,
) -> None:
    payload = _fixture_payload()
    assert isinstance(payload["task9_authority"], dict)
    payload["task9_authority"]["result_hash"] = "c" * 64
    await _assert_invalid_fixture(sqlite_session, tmp_path, payload)


@pytest.mark.unit
async def test_cli_rejects_policy_hash_mismatch(
    sqlite_session: AsyncSession,
    tmp_path: Path,
) -> None:
    payload = _fixture_payload()
    assert isinstance(payload["marketable_retention_policy"], list)
    assert isinstance(payload["marketable_retention_policy"][0], dict)
    payload["marketable_retention_policy"][0]["hash"] = "e" * 64
    await _assert_invalid_fixture(sqlite_session, tmp_path, payload)


@pytest.mark.unit
async def test_cli_rejects_unknown_fixture_field(
    sqlite_session: AsyncSession,
    tmp_path: Path,
) -> None:
    payload = _fixture_payload()
    payload["unexpected_fixture_field"] = "not-authorized"
    await _assert_invalid_fixture(sqlite_session, tmp_path, payload)
