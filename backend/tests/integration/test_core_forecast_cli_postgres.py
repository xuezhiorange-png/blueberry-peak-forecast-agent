"""PostgreSQL full-season acceptance for the unified V0.1 CLI."""

from __future__ import annotations

import asyncio
import copy
import json
import os
from argparse import Namespace
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from io import StringIO
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.core_forecast.cli import CoreForecastCliError, dispatch_core_forecast
from backend.app.core_forecast.persistence import CoreForecastRunRepository
from backend.app.models.core_forecast import (
    CoreForecastDailyRowModel,
    CoreForecastMetricModel,
    CoreForecastRunModel,
)
from backend.tests.actual_harvest_import.postgres_cases import (
    test_postgres_composite_fk_and_on_delete_restrict_are_database_enforced as actual_harvest_postgres_composite_fk_case,  # noqa: E501
    test_postgres_repository_does_not_commit_and_caller_rollback_removes_rows as actual_harvest_postgres_transaction_case,  # noqa: E501
    test_postgres_staging_round_trip_and_constraints as actual_harvest_postgres_round_trip_case,
    test_postgres_unique_constraints_and_conflict_mapping as actual_harvest_postgres_conflict_case,
)
from backend.tests.integration.test_v0_1_s2_complete_daily_curve_postgres import (
    _seed_authorities,
)

FIXTURE = Path("backend/tests/fixtures/v0_1_complete_season_case_01/input.json")
CURVE_HASH = "de81bfa3a23efcef0398758e5105199eede9222adb0aff4acda67f3fe9697687"
METRICS_HASH = "cfba5f2af9236e907527ef72d2d8e0a34b99f2cad29aaac502e6159c1d6d586a"
RESULT_HASH = "802504d0798f6ce1f46978806a4b986eefe2ff733616b60af7143ff3e641535a"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.postgres,
    pytest.mark.e2e,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
        reason="LOCAL_POSTGRES_NOT_AVAILABLE",
    ),
]


def _session_factory(session: AsyncSession) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=session.bind,
        class_=AsyncSession,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )


async def _dispatch(
    session: AsyncSession,
    fixture: Path = FIXTURE,
    *,
    rerun_of: int | None = None,
) -> dict[str, object]:
    output = StringIO()
    await dispatch_core_forecast(
        Namespace(
            fixture=str(fixture),
            output_json=None,
            rerun_of=rerun_of,
        ),
        session_factory=_session_factory(session),
        stdout=output,
    )
    return json.loads(output.getvalue())


async def _write_fixture(path: Path, payload: dict[str, object]) -> None:
    text = json.dumps(payload, sort_keys=True)
    await asyncio.to_thread(path.write_text, text, encoding="utf-8")


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


async def test_postgres_core_forecast_full_season_e2e(
    transactional_pg_session: AsyncSession,
    tmp_path: Path,
) -> None:
    await _seed_authorities(transactional_pg_session)
    first = await _dispatch(transactional_pg_session)

    assert first["status"] == "COMPLETED"
    assert first["daily_row_count"] == 1080
    assert first["metric_count"] == 3
    assert first["curve_hash"] == CURVE_HASH
    assert first["metrics_hash"] == METRICS_HASH
    assert first["result_hash"] == RESULT_HASH
    assert [item["forecast_quantile"] for item in first["metrics"]] == ["P50", "P80", "P90"]

    repository = CoreForecastRunRepository(transactional_pg_session)
    loaded = await repository.load_complete_run(first["run_id"])
    assert loaded.run.curve_hash == CURVE_HASH
    assert loaded.run.metrics_hash == METRICS_HASH
    assert len(loaded.daily_curve.rows) == 1080
    assert len(loaded.metrics.metrics) == 3

    second = await _dispatch(transactional_pg_session)
    assert second["run_id"] == first["run_id"]
    assert second["result_hash"] == first["result_hash"]
    assert second["reused_existing_run"] is True
    assert await transactional_pg_session.scalar(select(func.count(CoreForecastRunModel.id))) == 1
    assert (
        await transactional_pg_session.scalar(select(func.count(CoreForecastDailyRowModel.id)))
        == 1080
    )
    assert (
        await transactional_pg_session.scalar(select(func.count(CoreForecastMetricModel.id))) == 3
    )

    rerun_payload = _valid_policy_rerun_payload()
    rerun_fixture = tmp_path / "rerun.json"
    await _write_fixture(rerun_fixture, rerun_payload)
    child = await _dispatch(transactional_pg_session, rerun_fixture, rerun_of=first["run_id"])
    assert child["status"] == "COMPLETED"
    assert child["run_id"] != first["run_id"]
    assert child["request_hash"] != first["request_hash"]
    assert child["result_hash"] != first["result_hash"]
    child_run = await repository.get_run_by_id(child["run_id"])
    assert child_run is not None
    assert child_run.run.rerun_of_run_id == first["run_id"]
    parent_run = await repository.get_run_by_id(first["run_id"])
    assert parent_run is not None
    assert parent_run.run.rerun_of_run_id is None

    blocked_payload = copy.deepcopy(rerun_payload)
    blocked_payload["task9_authority"]["run_id"] = 999001
    for row in blocked_payload["daily_inputs"]:
        row["task9_harvest_state_run_id"] = 999001
    blocked_fixture = tmp_path / "blocked.json"
    await _write_fixture(blocked_fixture, blocked_payload)
    before_counts = (
        await transactional_pg_session.scalar(select(func.count(CoreForecastRunModel.id))),
        await transactional_pg_session.scalar(select(func.count(CoreForecastDailyRowModel.id))),
        await transactional_pg_session.scalar(select(func.count(CoreForecastMetricModel.id))),
    )
    with pytest.raises(CoreForecastCliError) as exc_info:
        await _dispatch(transactional_pg_session, blocked_fixture)
    assert exc_info.value.code == "TASK9_AUTHORITY_NOT_FOUND"
    after_counts = (
        await transactional_pg_session.scalar(select(func.count(CoreForecastRunModel.id))),
        await transactional_pg_session.scalar(select(func.count(CoreForecastDailyRowModel.id))),
        await transactional_pg_session.scalar(select(func.count(CoreForecastMetricModel.id))),
    )
    assert after_counts == before_counts


async def test_postgres_core_forecast_full_season_reload_parity(
    transactional_pg_session: AsyncSession,
) -> None:
    await _seed_authorities(transactional_pg_session)
    summary = await _dispatch(transactional_pg_session)
    repository = CoreForecastRunRepository(transactional_pg_session)
    loaded = await repository.load_complete_run(summary["run_id"])

    assert loaded.run.daily_row_count == 1080
    assert loaded.run.metric_row_count == 3
    assert loaded.run.curve_hash == CURVE_HASH
    assert loaded.run.metrics_hash == METRICS_HASH
    assert loaded.daily_curve.status == "COMPLETED"
    assert loaded.metrics.status == "COMPLETED"
    assert len(loaded.daily_curve.rows) == 1080
    assert tuple(item.forecast_quantile for item in loaded.metrics.metrics) == (
        "P50",
        "P80",
        "P90",
    )


async def test_actual_harvest_postgres_staging_round_trip_and_constraints() -> None:
    await actual_harvest_postgres_round_trip_case()


async def test_actual_harvest_postgres_unique_constraints_and_conflict_mapping() -> None:
    await actual_harvest_postgres_conflict_case()


async def test_actual_harvest_postgres_composite_fk_and_on_delete_restrict() -> None:
    await actual_harvest_postgres_composite_fk_case()


async def test_actual_harvest_postgres_repository_transaction_ownership() -> None:
    await actual_harvest_postgres_transaction_case()
