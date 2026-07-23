from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core_forecast.application import (
    execute_core_forecast_run,
    recalculate_core_forecast_run,
)
from backend.app.core_forecast.persistence import CoreForecastRunRepository
from backend.app.core_forecast.repository import SeasonSource
from backend.app.core_forecast.schemas import (
    ExecuteCoreForecastRunRequest,
    MarketableRetentionPolicySnapshot,
    RegisterCoreForecastCodeAuthority,
)
from backend.app.models.core_forecast import (
    CoreForecastCodeAuthorityModel,
    CoreForecastRunModel,
)
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


async def _register_authority(
    session: AsyncSession,
    *,
    source_commit_sha: str = "a" * 40,
    build_artifact_hash: str = "b" * 64,
):
    await _ensure_code_authority_table(session)
    return await CoreForecastRunRepository(session).register_code_authority(
        RegisterCoreForecastCodeAuthority(
            source_commit_sha=source_commit_sha,
            engine_code_hash="e" * 64,
            build_artifact_hash=build_artifact_hash,
            config_bundle_hash="c" * 64,
            available_at=datetime(2026, 2, 28, tzinfo=UTC),
        )
    )


def _authority_upstream() -> FixtureRepository:
    task8, task9 = _sources()
    return FixtureRepository(
        task8,
        replace(
            task9,
            forecast_effective_cutoff_at=datetime(2026, 3, 1, tzinfo=UTC),
        ),
    )


async def _ensure_code_authority_table(session: AsyncSession) -> None:
    connection = await session.connection()
    await connection.run_sync(
        lambda sync_connection: CoreForecastCodeAuthorityModel.__table__.create(
            sync_connection,
            checkfirst=True,
        )
    )


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
    assert await sqlite_session.scalar(select(func.count(CoreForecastRunModel.id))) == 0


@pytest.mark.unit
async def test_missing_pre_registered_code_authority_blocks_before_forecast(
    sqlite_session: AsyncSession,
) -> None:
    await _ensure_code_authority_table(sqlite_session)
    result = await execute_core_forecast_run(
        sqlite_session,
        request=ExecuteCoreForecastRunRequest(
            curve_request=_request(),
            retention_policy=_policy(),
            code_authority_id=999999,
        ),
        upstream_repository=_authority_upstream(),
    )
    assert result.status == "BLOCKED"
    assert result.blockers[0].code == "CORE_FORECAST_CODE_AUTHORITY_NOT_FOUND"
    assert await sqlite_session.scalar(select(func.count(CoreForecastRunModel.id))) == 0


@pytest.mark.unit
async def test_authority_bound_run_hashes_code_identity_and_replays_idempotently(
    sqlite_session: AsyncSession,
) -> None:
    upstream = _authority_upstream()
    legacy = await execute_core_forecast_run(
        sqlite_session,
        request=ExecuteCoreForecastRunRequest(
            curve_request=_request(),
            retention_policy=_policy(),
        ),
        upstream_repository=upstream,
    )
    authority = await _register_authority(sqlite_session)
    request = ExecuteCoreForecastRunRequest(
        curve_request=_request(),
        retention_policy=_policy(),
        code_authority_id=authority.authority_id,
    )
    first = await execute_core_forecast_run(
        sqlite_session,
        request=request,
        upstream_repository=upstream,
    )
    replay = await execute_core_forecast_run(
        sqlite_session,
        request=request,
        upstream_repository=upstream,
    )
    assert legacy.status == first.status == replay.status == "COMPLETED"
    assert legacy.run is not None and first.run is not None and replay.run is not None
    assert first.run.run_schema_version == "v0.1-core-forecast-run-authority-v2"
    assert first.run.request_schema_version == "v0.1-core-forecast-request-authority-v2"
    assert first.run.code_authority_id == authority.authority_id
    assert first.run.forecast_input_hash != legacy.run.forecast_input_hash
    assert first.run.request_hash != legacy.run.request_hash
    assert first.run.result_hash != legacy.run.result_hash
    assert replay.run.run_id == first.run.run_id
    assert replay.reused_existing_run is True


@pytest.mark.unit
async def test_different_persisted_code_authority_changes_run_identity(
    sqlite_session: AsyncSession,
) -> None:
    upstream = _authority_upstream()
    first_authority = await _register_authority(sqlite_session)
    second_authority = await _register_authority(
        sqlite_session,
        source_commit_sha="d" * 40,
        build_artifact_hash="e" * 64,
    )
    results = []
    for authority in (first_authority, second_authority):
        results.append(
            await execute_core_forecast_run(
                sqlite_session,
                request=ExecuteCoreForecastRunRequest(
                    curve_request=_request(),
                    retention_policy=_policy(),
                    code_authority_id=authority.authority_id,
                ),
                upstream_repository=upstream,
            )
        )
    assert all(result.status == "COMPLETED" for result in results)
    assert results[0].run is not None and results[1].run is not None
    assert results[0].run.forecast_input_hash != results[1].run.forecast_input_hash
    assert results[0].run.result_hash != results[1].run.result_hash


@pytest.mark.unit
async def test_missing_rerun_parent_blocks_without_writes(sqlite_session: AsyncSession) -> None:
    result = await recalculate_core_forecast_run(
        sqlite_session,
        source_run_id=999999,
        curve_request=_request(),
        retention_policy=_policy(),
        upstream_repository=MissingUpstream(),
    )
    assert result.status == "BLOCKED"
    assert result.blockers[0].code == "CORE_FORECAST_PARENT_RUN_NOT_FOUND"
    assert await sqlite_session.scalar(select(func.count(CoreForecastRunModel.id))) == 0


@pytest.mark.unit
async def test_completed_run_is_reused_and_explicit_rerun_has_parent(
    sqlite_session: AsyncSession,
) -> None:
    request = ExecuteCoreForecastRunRequest(
        curve_request=_request(),
        retention_policy=_policy(),
    )
    upstream = _authority_upstream()
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
    upstream = _authority_upstream()

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


@pytest.mark.unit
async def test_rerun_scope_mismatch_blocks_without_writing_child(
    sqlite_session: AsyncSession,
) -> None:
    request = ExecuteCoreForecastRunRequest(
        curve_request=_request(),
        retention_policy=_policy(),
    )
    upstream = FixtureRepository(*_sources())
    parent = await execute_core_forecast_run(
        sqlite_session,
        request=request,
        upstream_repository=upstream,
    )
    assert parent.status == "COMPLETED"
    assert parent.run is not None
    mismatched_request = _request().model_copy(update={"destination_factory_id": 9102})
    result = await recalculate_core_forecast_run(
        sqlite_session,
        source_run_id=parent.run.run_id,
        curve_request=mismatched_request,
        retention_policy=_policy(),
        upstream_repository=upstream,
    )
    assert result.status == "BLOCKED"
    assert result.blockers[0].code == "CORE_FORECAST_RERUN_SCOPE_MISMATCH"
    assert await sqlite_session.scalar(select(func.count(CoreForecastRunModel.id))) == 1
