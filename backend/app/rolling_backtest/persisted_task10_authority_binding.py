"""Persisted Core forecast ↔ Task 10 authority binding (reference evidence only)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.app.models.core_forecast import CoreForecastRunModel
from backend.app.models.core_forecast_task10_authority_binding import (
    CoreForecastTask10AuthorityBindingModel,
)
from backend.app.models.residual_model import ResidualModelPredictionRun
from backend.app.rolling_backtest.canonical import canonical_json_value, sha256_payload


class PersistedTask10AuthorityBindingError(ValueError):
    """Base error for persisted Task 10 authority binding failures."""


class PersistedTask10AuthorityBindingLineageError(PersistedTask10AuthorityBindingError):
    """Raised when the pinned Task 10 run does not match the Core/Task 9 lineage."""


class PersistedTask10AuthorityBindingConflictError(PersistedTask10AuthorityBindingError):
    """Raised when a Core forecast run already has a different Task 10 binding."""


class PersistedTask10AuthorityBindingWriteOutcome(StrEnum):
    """Typed result for rolling-node Task 10 authority relation population."""

    BOUND = "BOUND"
    CORE_AUTHORITY_NOT_FOUND = "CORE_AUTHORITY_NOT_FOUND"
    CORE_AUTHORITY_AMBIGUOUS = "CORE_AUTHORITY_AMBIGUOUS"
    TASK10_AUTHORITY_NOT_PINNED = "TASK10_AUTHORITY_NOT_PINNED"
    TASK9_AUTHORITY_NOT_PINNED = "TASK9_AUTHORITY_NOT_PINNED"
    TASK8_LINEAGE_NOT_FOUND = "TASK8_LINEAGE_NOT_FOUND"


@dataclass(frozen=True, slots=True)
class PersistedTask10AuthorityBindingWriteResult:
    outcome: PersistedTask10AuthorityBindingWriteOutcome
    core_forecast_run_id: int | None = None
    task10_prediction_run_id: int | None = None
    binding_id: int | None = None


def compute_binding_identity_hash(
    *,
    core_forecast_run_id: int,
    core_forecast_result_hash: str,
    task9_run_id: int,
    task9_result_hash: str,
    task10_prediction_run_id: int,
    task10_prediction_hash: str,
) -> str:
    return sha256_payload(
        canonical_json_value(
            {
                "core_forecast_run_id": core_forecast_run_id,
                "core_forecast_result_hash": core_forecast_result_hash,
                "task9_run_id": task9_run_id,
                "task9_result_hash": task9_result_hash,
                "task10_prediction_run_id": task10_prediction_run_id,
                "task10_prediction_hash": task10_prediction_hash,
            }
        )
    )


def _validate_lineage(
    *,
    core_run: CoreForecastRunModel,
    prediction_run: ResidualModelPredictionRun,
) -> None:
    if core_run.status != "completed":
        raise PersistedTask10AuthorityBindingLineageError(
            "core forecast run must be completed before Task 10 binding"
        )
    if prediction_run.execution_status != "completed":
        raise PersistedTask10AuthorityBindingLineageError(
            "Task 10 prediction run must be completed before binding"
        )
    if prediction_run.task9_run_id != core_run.task9_harvest_state_run_id:
        raise PersistedTask10AuthorityBindingLineageError(
            "Task 10 prediction run is not bound to the core forecast Task 9 run"
        )
    if prediction_run.task9_result_hash != core_run.task9_result_hash:
        raise PersistedTask10AuthorityBindingLineageError(
            "Task 10 prediction run Task 9 result hash does not match core forecast"
        )
    if core_run.task9_result_hash != prediction_run.task9_result_hash:
        raise PersistedTask10AuthorityBindingLineageError(
            "persisted forecast authority chain is inconsistent"
        )


async def register_persisted_task10_authority_binding(
    session: AsyncSession,
    *,
    core_forecast_run_id: int,
    task10_prediction_run_id: int,
) -> CoreForecastTask10AuthorityBindingModel:
    """Persist one immutable Task 10 authority binding for an exact Core forecast run.

    The caller must already possess the exact ``task10_prediction_run_id``. This
    function never scans or selects among Task 10 prediction runs.
    """
    core_run = await session.get(CoreForecastRunModel, core_forecast_run_id)
    if core_run is None:
        raise PersistedTask10AuthorityBindingLineageError(
            "core forecast run is missing for Task 10 authority binding"
        )
    prediction_run = await session.get(ResidualModelPredictionRun, task10_prediction_run_id)
    if prediction_run is None:
        raise PersistedTask10AuthorityBindingLineageError(
            "Task 10 prediction run is missing for authority binding"
        )
    _validate_lineage(core_run=core_run, prediction_run=prediction_run)

    existing = await session.scalar(
        select(CoreForecastTask10AuthorityBindingModel).where(
            CoreForecastTask10AuthorityBindingModel.core_forecast_run_id == core_forecast_run_id
        )
    )
    if existing is not None:
        if existing.task10_prediction_run_id != task10_prediction_run_id:
            raise PersistedTask10AuthorityBindingConflictError(
                "core forecast run already has a conflicting Task 10 authority binding"
            )
        return existing

    binding_identity_hash = compute_binding_identity_hash(
        core_forecast_run_id=core_run.id,
        core_forecast_result_hash=core_run.result_hash,
        task9_run_id=core_run.task9_harvest_state_run_id,
        task9_result_hash=core_run.task9_result_hash,
        task10_prediction_run_id=prediction_run.id,
        task10_prediction_hash=prediction_run.prediction_hash,
    )
    row = CoreForecastTask10AuthorityBindingModel(
        core_forecast_run_id=core_run.id,
        task9_run_id=core_run.task9_harvest_state_run_id,
        task9_result_hash=core_run.task9_result_hash,
        task10_prediction_run_id=prediction_run.id,
        binding_identity_hash=binding_identity_hash,
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as error:
        raise PersistedTask10AuthorityBindingConflictError(
            "core forecast run already has a conflicting Task 10 authority binding"
        ) from error
    return row


async def resolve_exact_core_forecast_run_ids(
    session: AsyncSession,
    *,
    task8_forecast_run_id: int,
    task9_harvest_state_run_id: int,
    task9_result_hash: str,
    forecast_effective_cutoff_at: datetime,
) -> list[int]:
    """Resolve authority-bound Core forecast runs by exact lineage identity only."""
    rows = list(
        await session.scalars(
            select(CoreForecastRunModel.id).where(
                CoreForecastRunModel.status == "completed",
                CoreForecastRunModel.task8_forecast_run_id == task8_forecast_run_id,
                CoreForecastRunModel.task9_harvest_state_run_id == task9_harvest_state_run_id,
                CoreForecastRunModel.task9_result_hash == task9_result_hash,
                CoreForecastRunModel.forecast_effective_cutoff_at == forecast_effective_cutoff_at,
                CoreForecastRunModel.code_authority_id.is_not(None),
                CoreForecastRunModel.code_authority_hash.is_not(None),
            )
        )
    )
    return [int(row) for row in rows]


async def write_persisted_task10_authority_binding_from_pinned_lineage(
    session: AsyncSession,
    *,
    task10_prediction_run_id: int,
    task8_forecast_run_id: int,
    task9_harvest_state_run_id: int,
    task9_result_hash: str,
    forecast_effective_cutoff_at: datetime,
) -> PersistedTask10AuthorityBindingWriteResult:
    """Persist one Task 10 authority binding after exact Core lineage resolution."""
    core_ids = await resolve_exact_core_forecast_run_ids(
        session,
        task8_forecast_run_id=task8_forecast_run_id,
        task9_harvest_state_run_id=task9_harvest_state_run_id,
        task9_result_hash=task9_result_hash,
        forecast_effective_cutoff_at=forecast_effective_cutoff_at,
    )
    if not core_ids:
        return PersistedTask10AuthorityBindingWriteResult(
            outcome=PersistedTask10AuthorityBindingWriteOutcome.CORE_AUTHORITY_NOT_FOUND,
            task10_prediction_run_id=task10_prediction_run_id,
        )
    if len(core_ids) > 1:
        return PersistedTask10AuthorityBindingWriteResult(
            outcome=PersistedTask10AuthorityBindingWriteOutcome.CORE_AUTHORITY_AMBIGUOUS,
            task10_prediction_run_id=task10_prediction_run_id,
        )
    core_forecast_run_id = core_ids[0]
    binding = await register_persisted_task10_authority_binding(
        session,
        core_forecast_run_id=core_forecast_run_id,
        task10_prediction_run_id=task10_prediction_run_id,
    )
    return PersistedTask10AuthorityBindingWriteResult(
        outcome=PersistedTask10AuthorityBindingWriteOutcome.BOUND,
        core_forecast_run_id=core_forecast_run_id,
        task10_prediction_run_id=task10_prediction_run_id,
        binding_id=binding.id,
    )


def lookup_task10_prediction_run_id_sync(
    session: Session,
    *,
    core_forecast_run_id: int,
) -> int | None:
    """Return the pinned Task 10 prediction run id for a Core forecast run, if bound."""
    rows = list(
        session.scalars(
            select(CoreForecastTask10AuthorityBindingModel.task10_prediction_run_id).where(
                CoreForecastTask10AuthorityBindingModel.core_forecast_run_id == core_forecast_run_id
            )
        ).all()
    )
    if not rows:
        return None
    if len(rows) != 1:
        raise PersistedTask10AuthorityBindingConflictError(
            "ambiguous persisted Task 10 authority binding for core forecast run"
        )
    return int(rows[0])


async def lookup_task10_prediction_run_id(
    session: AsyncSession,
    *,
    core_forecast_run_id: int,
) -> int | None:
    rows = list(
        await session.scalars(
            select(CoreForecastTask10AuthorityBindingModel.task10_prediction_run_id).where(
                CoreForecastTask10AuthorityBindingModel.core_forecast_run_id == core_forecast_run_id
            )
        )
    )
    if not rows:
        return None
    if len(rows) != 1:
        raise PersistedTask10AuthorityBindingConflictError(
            "ambiguous persisted Task 10 authority binding for core forecast run"
        )
    return int(rows[0])
