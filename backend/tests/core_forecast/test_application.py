from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core_forecast.application import (
    execute_core_forecast_run,
    recalculate_core_forecast_run,
)
from backend.app.core_forecast.repository import SeasonSource
from backend.app.core_forecast.schemas import (
    ExecuteCoreForecastRunRequest,
    MarketableRetentionPolicySnapshot,
)
from backend.app.models.core_forecast import CoreForecastRunModel
from backend.tests.core_forecast.test_complete_daily_curve_service import (
    FixtureRepository,
    _policy,
    _request,
    _sources,
)


class MissingUpstream:
    async def load_task8_authority(self, run_id: int):
        return None

    async def load_task9_authority(self, run_id: int):
        return None

    async def load_season(self, season_id: int):
        return SeasonSource(season_id=season_id, code="2026-DEMO")


@pytest.mark.unit
async def test_blocked_s2_result_exposes_no_partial_output(sqlite_session: AsyncSession) -> None:
    request = ExecuteCoreForecastRunRequest(
        curve_request=_request(),
        retention_policy=_policy(),
    )
    result = await execute_core_forecast_run(
        sqlite_session,
        request=request,
        upstream_repository=MissingUpstream(),
    )
    assert result.status == "BLOCKED"
    assert result.run is None
    assert result.daily_curve is None
    assert result.metrics is None
    assert result.reused_existing_run is False
    assert result.blockers[0].code == "TASK8_AUTHORITY_NOT_FOUND"


@pytest.mark.unit
async def test_completed_run_is_reused_and_explicit_rerun_has_parent(
    sqlite_session: AsyncSession,
) -> None:
    request = ExecuteCoreForecastRunRequest(
        curve_request=_request(),
        retention_policy=_policy(),
    )
    upstream = FixtureRepository(*_sources())
    first = await execute_core_forecast_run(
        sqlite_session,
        request=request,
        upstream_repository=upstream,
    )
    assert first.status == "COMPLETED"
    assert first.run is not None
    assert len(first.daily_curve.rows) == 1080  # type: ignore[union-attr]

    reused = await execute_core_forecast_run(
        sqlite_session,
        request=request,
        upstream_repository=upstream,
    )
    assert reused.status == "COMPLETED"
    assert reused.reused_existing_run is True
    assert reused.run is not None
    assert reused.run.run_id == first.run.run_id

    original_policy = _policy()
    changed_policy = MarketableRetentionPolicySnapshot(
        entries=tuple(
            entry.model_copy(update={"postharvest_retention_rate": "0.940000"})
            if index == 0
            else entry
            for index, entry in enumerate(original_policy.entries)
        )
    )
    rerun = await recalculate_core_forecast_run(
        sqlite_session,
        source_run_id=first.run.run_id,
        curve_request=_request(),
        retention_policy=changed_policy,
        upstream_repository=upstream,
    )
    assert rerun.status == "COMPLETED"
    assert rerun.run is not None
    assert rerun.run.rerun_of_run_id == first.run.run_id
    assert rerun.run.run_id != first.run.run_id

    unchanged = await recalculate_core_forecast_run(
        sqlite_session,
        source_run_id=first.run.run_id,
        curve_request=_request(),
        retention_policy=original_policy,
        upstream_repository=upstream,
    )
    assert unchanged.status == "BLOCKED"
    assert unchanged.blockers[0].code == "CORE_FORECAST_RERUN_INPUT_UNCHANGED"
    assert await sqlite_session.scalar(select(func.count(CoreForecastRunModel.id))) == 2


@pytest.mark.unit
async def test_blocked_s3_result_writes_no_rows(
    sqlite_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = ExecuteCoreForecastRunRequest(
        curve_request=_request(),
        retention_policy=_policy(),
    )
    upstream = FixtureRepository(*_sources())

    from backend.app.core_forecast import application as application_module
    from backend.app.core_forecast.schemas import (
        CompleteCoreForecastMetricsResult,
        CoreForecastBlocker,
    )

    def blocked_metrics(*, daily_curve):
        del daily_curve
        return CompleteCoreForecastMetricsResult(
            status="BLOCKED",
            metrics_schema_version=None,
            date_basis=None,
            source_curve_hash=None,
            metrics=(),
            metrics_hash=None,
            blockers=(CoreForecastBlocker(code="NO_COMPLETE_7DAY_WINDOW", message="blocked"),),
        )

    monkeypatch.setattr(application_module, "compute_core_forecast_metrics", blocked_metrics)
    result = await execute_core_forecast_run(
        sqlite_session,
        request=request,
        upstream_repository=upstream,
    )
    assert result.status == "BLOCKED"
    assert result.run is None
    assert result.daily_curve is None
    assert result.metrics is None
    assert await sqlite_session.scalar(select(func.count(CoreForecastRunModel.id))) == 0
