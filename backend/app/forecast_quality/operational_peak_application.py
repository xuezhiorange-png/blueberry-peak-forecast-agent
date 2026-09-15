"""Canonical application boundary for persisted S6 operational peak runs."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.forecast_quality.operational_peak import (
    OperationalPeakForecastRequest,
    OperationalPeakForecastResult,
    forecast_operational_peak,
)
from backend.app.forecast_quality.operational_peak_authority import (
    load_operational_peak_authority,
)
from backend.app.forecast_quality.operational_peak_persistence import (
    OperationalPeakPersistenceConflictError,
    OperationalPeakRerunScopeMismatch,
    OperationalPeakRunRepository,
    execution_hash,
    request_snapshot,
)
from backend.app.forecast_quality.operational_peak_schemas import SavedOperationalPeakRun


async def execute_operational_peak_forecast_run(
    session: AsyncSession,
    request: OperationalPeakForecastRequest,
    *,
    rerun_of_run_id: int | None = None,
) -> SavedOperationalPeakRun:
    """Execute once against one validated authority snapshot and persist immutably."""

    if not isinstance(request, OperationalPeakForecastRequest):
        raise ValueError("INVALID_REQUEST")
    authority = load_operational_peak_authority()
    snapshot = request_snapshot(request)
    execution_id = execution_hash(snapshot, authority.authority_hash, authority.policy_version)
    repository = OperationalPeakRunRepository(session)

    # An explicit parent is part of the caller's lineage contract. Validate it
    # before an existing execution can produce a successful early return.
    if rerun_of_run_id is not None:
        parent = await repository.get(rerun_of_run_id)
        if (
            parent.result.get("base_id") != request.base_id
            or parent.result.get("target_season") != request.target_season
            or parent.result.get("origin_date") != request.origin_date.isoformat()
        ):
            raise OperationalPeakRerunScopeMismatch("RERUN_SCOPE_MISMATCH")

    existing = await repository.existing(execution_id, snapshot)
    if existing is not None:
        if existing.result.get("policy_version") != authority.policy_version:
            raise OperationalPeakPersistenceConflictError("EXECUTION_POLICY_CONFLICT")
        return existing

    result: OperationalPeakForecastResult = forecast_operational_peak(
        request,
        authority.registry,
        authority.reference_profile,
    )
    return await repository.save(
        snapshot,
        result,
        execution_id,
        authority.authority_hash,
        rerun_of_run_id,
    )


__all__ = ["execute_operational_peak_forecast_run"]
