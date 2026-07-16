from __future__ import annotations

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core_forecast.canonical import (
    compute_core_forecast_input_hash,
    compute_core_forecast_request_hash,
    compute_core_forecast_result_hash,
    compute_retention_policy_snapshot_hash,
)
from backend.app.core_forecast.metrics import compute_core_forecast_metrics
from backend.app.core_forecast.persistence import (
    CoreForecastPersistenceConflictError,
    CoreForecastPersistenceIntegrityError,
    CoreForecastRunRepository,
    CoreForecastWriteFailure,
)
from backend.app.core_forecast.repository import (
    CoreForecastRepository,
    SqlAlchemyCoreForecastRepository,
)
from backend.app.core_forecast.schemas import (
    CompleteDailyMarketableCurveRequest,
    CoreForecastBlockerCode,
    CoreForecastExecutionResult,
    ExecuteCoreForecastRunRequest,
    MarketableRetentionPolicySnapshot,
    PersistedCoreForecastRun,
)
from backend.app.core_forecast.service import compose_complete_daily_marketable_curve


def _blocked(code: CoreForecastBlockerCode, message: str) -> CoreForecastExecutionResult:
    from backend.app.core_forecast.schemas import CoreForecastBlocker

    return CoreForecastExecutionResult(
        status="BLOCKED",
        run=None,
        daily_curve=None,
        metrics=None,
        reused_existing_run=False,
        blockers=(CoreForecastBlocker(code=code, message=message),),
    )


def _completed(
    persisted: PersistedCoreForecastRun,
    *,
    reused_existing_run: bool,
) -> CoreForecastExecutionResult:
    return CoreForecastExecutionResult(
        status="COMPLETED",
        run=persisted.run,
        daily_curve=persisted.daily_curve,
        metrics=persisted.metrics,
        reused_existing_run=reused_existing_run,
        blockers=(),
    )


def _same_rerun_scope(
    parent: ExecuteCoreForecastRunRequest,
    current: ExecuteCoreForecastRunRequest,
) -> bool:
    left = parent.curve_request
    right = current.curve_request
    return (
        left.forecast_season_id == right.forecast_season_id
        and left.forecast_season_code == right.forecast_season_code
        and left.forecast_start_date == right.forecast_start_date
        and left.forecast_end_date == right.forecast_end_date
        and left.destination_factory_id == right.destination_factory_id
        and {(scope.farm_id, scope.subfarm_id, scope.variety_id) for scope in left.scopes}
        == {(scope.farm_id, scope.subfarm_id, scope.variety_id) for scope in right.scopes}
    )


async def execute_core_forecast_run(
    session: AsyncSession,
    *,
    request: ExecuteCoreForecastRunRequest,
    upstream_repository: CoreForecastRepository | None = None,
    persistence_repository: CoreForecastRunRepository | None = None,
) -> CoreForecastExecutionResult:
    """Execute S2 and S3 once, then persist one immutable completed run."""

    try:
        canonical_request = ExecuteCoreForecastRunRequest.model_validate(
            request.model_dump(mode="python")
        )
        policy_hash = compute_retention_policy_snapshot_hash(canonical_request.retention_policy)
        input_hash = compute_core_forecast_input_hash(
            canonical_request.curve_request,
            canonical_request.retention_policy,
        )
        request_hash = compute_core_forecast_request_hash(
            input_hash,
            canonical_request.rerun_of_run_id,
        )
    except (ValidationError, ValueError, TypeError):
        return _blocked("CORE_FORECAST_PERSISTENCE_INTEGRITY_FAILED", "request validation failed")

    persistence = persistence_repository or CoreForecastRunRepository(session)
    upstream = upstream_repository or SqlAlchemyCoreForecastRepository(session)

    if canonical_request.rerun_of_run_id is not None:
        try:
            parent = await persistence.get_run_by_id(canonical_request.rerun_of_run_id)
        except CoreForecastPersistenceIntegrityError:
            return _blocked(
                "CORE_FORECAST_PERSISTENCE_INTEGRITY_FAILED",
                "rerun parent failed integrity validation",
            )
        if parent is None:
            return _blocked(
                "CORE_FORECAST_PARENT_RUN_NOT_FOUND",
                "rerun parent run was not found",
            )
        if not _same_rerun_scope(parent.request, canonical_request):
            return _blocked(
                "CORE_FORECAST_RERUN_SCOPE_MISMATCH",
                "rerun scope must match the immutable parent scope",
            )
        if input_hash == parent.run.forecast_input_hash:
            return _blocked(
                "CORE_FORECAST_RERUN_INPUT_UNCHANGED",
                "rerun requires a complete changed forecast input",
            )

    try:
        existing = await persistence.get_run_by_request_hash(request_hash)
    except CoreForecastPersistenceIntegrityError:
        return _blocked(
            "CORE_FORECAST_PERSISTENCE_INTEGRITY_FAILED",
            "existing run failed integrity validation",
        )
    if existing is not None:
        if existing.request != canonical_request:
            return _blocked(
                "CORE_FORECAST_PERSISTENCE_CONFLICT",
                "request hash exists with a different request snapshot",
            )
        return _completed(existing, reused_existing_run=True)

    curve = await compose_complete_daily_marketable_curve(
        session,
        request=canonical_request.curve_request,
        retention_policy=canonical_request.retention_policy,
        repository=upstream,
    )
    if curve.status != "COMPLETED":
        return CoreForecastExecutionResult(
            status="BLOCKED",
            run=None,
            daily_curve=None,
            metrics=None,
            reused_existing_run=False,
            blockers=curve.blockers,
        )

    metrics = compute_core_forecast_metrics(daily_curve=curve)
    if metrics.status != "COMPLETED":
        return CoreForecastExecutionResult(
            status="BLOCKED",
            run=None,
            daily_curve=None,
            metrics=None,
            reused_existing_run=False,
            blockers=metrics.blockers,
        )

    assert curve.curve_hash is not None
    assert metrics.metrics_hash is not None
    result_hash = compute_core_forecast_result_hash(
        request_hash=request_hash,
        forecast_input_hash=input_hash,
        curve_hash=curve.curve_hash,
        metrics_hash=metrics.metrics_hash,
        daily_row_count=len(curve.rows),
        metric_row_count=len(metrics.metrics),
    )
    try:
        persisted = await persistence.save_completed_run(
            request=canonical_request,
            forecast_input_hash=input_hash,
            request_hash=request_hash,
            result_hash=result_hash,
            retention_policy_snapshot_hash=policy_hash,
            curve=curve,
            metrics=metrics,
            rerun_of_run_id=canonical_request.rerun_of_run_id,
        )
    except CoreForecastPersistenceConflictError:
        return _blocked(
            "CORE_FORECAST_PERSISTENCE_CONFLICT",
            "canonical persistence identity conflict",
        )
    except CoreForecastPersistenceIntegrityError:
        return _blocked(
            "CORE_FORECAST_PERSISTENCE_INTEGRITY_FAILED",
            "saved run failed canonical reload validation",
        )
    except CoreForecastWriteFailure:
        return _blocked("CORE_FORECAST_WRITE_FAILURE", "core forecast write failed")
    return _completed(persisted, reused_existing_run=False)


async def recalculate_core_forecast_run(
    session: AsyncSession,
    *,
    source_run_id: int,
    curve_request: CompleteDailyMarketableCurveRequest,
    retention_policy: MarketableRetentionPolicySnapshot,
    upstream_repository: CoreForecastRepository | None = None,
    persistence_repository: CoreForecastRunRepository | None = None,
) -> CoreForecastExecutionResult:
    request = ExecuteCoreForecastRunRequest(
        curve_request=curve_request,
        retention_policy=retention_policy,
        rerun_of_run_id=source_run_id,
    )
    return await execute_core_forecast_run(
        session,
        request=request,
        upstream_repository=upstream_repository,
        persistence_repository=persistence_repository,
    )
