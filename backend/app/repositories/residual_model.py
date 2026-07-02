from __future__ import annotations

from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.residual_model import (
    ResidualModelArtifact,
    ResidualModelExecutionAttempt,
    ResidualModelManifestRow,
    ResidualModelPredictionRow,
    ResidualModelPredictionRun,
    ResidualModelTrainingRun,
)


async def get_residual_training_run(
    session: AsyncSession,
    *,
    run_id: int,
) -> ResidualModelTrainingRun | None:
    return cast(
        ResidualModelTrainingRun | None,
        await session.scalar(
            select(ResidualModelTrainingRun)
            .where(ResidualModelTrainingRun.id == run_id)
            .execution_options(populate_existing=True)
        ),
    )


async def get_residual_training_run_by_signature(
    session: AsyncSession,
    *,
    training_signature: str,
) -> ResidualModelTrainingRun | None:
    return cast(
        ResidualModelTrainingRun | None,
        await session.scalar(
            select(ResidualModelTrainingRun)
            .where(ResidualModelTrainingRun.training_signature == training_signature)
            .execution_options(populate_existing=True)
        ),
    )


async def list_residual_manifest_rows(
    session: AsyncSession,
    *,
    training_run_id: int,
) -> list[ResidualModelManifestRow]:
    return list(
        (
            await session.scalars(
                select(ResidualModelManifestRow)
                .where(ResidualModelManifestRow.training_run_id == training_run_id)
                .order_by(ResidualModelManifestRow.row_index.asc())
            )
        ).all()
    )


async def list_residual_artifacts(
    session: AsyncSession,
    *,
    training_run_id: int,
) -> list[ResidualModelArtifact]:
    return list(
        (
            await session.scalars(
                select(ResidualModelArtifact)
                .where(ResidualModelArtifact.training_run_id == training_run_id)
                .order_by(ResidualModelArtifact.quantile_label.asc())
            )
        ).all()
    )


async def get_residual_prediction_run(
    session: AsyncSession,
    *,
    run_id: int,
) -> ResidualModelPredictionRun | None:
    return cast(
        ResidualModelPredictionRun | None,
        await session.scalar(
            select(ResidualModelPredictionRun)
            .where(ResidualModelPredictionRun.id == run_id)
            .execution_options(populate_existing=True)
        ),
    )


async def get_residual_prediction_run_by_input_signature(
    session: AsyncSession,
    *,
    prediction_input_signature: str,
) -> ResidualModelPredictionRun | None:
    return cast(
        ResidualModelPredictionRun | None,
        await session.scalar(
            select(ResidualModelPredictionRun)
            .where(
                ResidualModelPredictionRun.prediction_input_signature == prediction_input_signature
            )
            .execution_options(populate_existing=True)
        ),
    )


async def list_residual_prediction_rows(
    session: AsyncSession,
    *,
    prediction_run_id: int,
) -> list[ResidualModelPredictionRow]:
    return list(
        (
            await session.scalars(
                select(ResidualModelPredictionRow)
                .where(ResidualModelPredictionRow.prediction_run_id == prediction_run_id)
                .order_by(
                    ResidualModelPredictionRow.destination_factory_id.asc(),
                    ResidualModelPredictionRow.arrival_local_date.asc(),
                )
            )
        ).all()
    )


async def get_residual_execution_attempt(
    session: AsyncSession,
    *,
    attempt_id: int,
) -> ResidualModelExecutionAttempt | None:
    return cast(
        ResidualModelExecutionAttempt | None,
        await session.scalar(
            select(ResidualModelExecutionAttempt)
            .where(ResidualModelExecutionAttempt.id == attempt_id)
            .execution_options(populate_existing=True)
        ),
    )


async def create_residual_execution_attempt(
    session: AsyncSession,
    *,
    attempt_type: str,
    execution_status: str,
    current_stage: str,
    requested_inputs: dict[str, object],
    config_identity: dict[str, object],
    upstream_requested_ids: dict[str, object],
    blockers: list[str] | None = None,
    sanitized_error: str | None = None,
) -> ResidualModelExecutionAttempt:
    attempt = ResidualModelExecutionAttempt(
        attempt_type=attempt_type,
        execution_status=execution_status,
        current_stage=current_stage,
        requested_inputs=requested_inputs,
        config_identity=config_identity,
        upstream_requested_ids=upstream_requested_ids,
        blockers=blockers or [],
        sanitized_error=sanitized_error,
        started_at=func.now(),
    )
    session.add(attempt)
    await session.flush()
    return attempt


async def update_residual_execution_attempt_stage(
    session: AsyncSession,
    *,
    attempt_id: int,
    current_stage: str,
) -> None:
    attempt = await get_residual_execution_attempt(session, attempt_id=attempt_id)
    if attempt is not None:
        attempt.current_stage = current_stage
        await session.flush()


async def complete_residual_execution_attempt(
    session: AsyncSession,
    *,
    attempt_id: int,
    linked_training_run_id: int | None = None,
    linked_prediction_run_id: int | None = None,
) -> None:
    attempt = await get_residual_execution_attempt(session, attempt_id=attempt_id)
    if attempt is not None:
        attempt.execution_status = "completed"
        attempt.current_stage = "completed"
        attempt.finished_at = func.now()
        if linked_training_run_id is not None:
            attempt.linked_training_run_id = linked_training_run_id
        if linked_prediction_run_id is not None:
            attempt.linked_prediction_run_id = linked_prediction_run_id
        await session.flush()


async def fail_residual_execution_attempt(
    session: AsyncSession,
    *,
    attempt_id: int,
    sanitized_error: str,
) -> None:
    attempt = await get_residual_execution_attempt(session, attempt_id=attempt_id)
    if attempt is not None:
        attempt.execution_status = "failed"
        attempt.sanitized_error = sanitized_error
        attempt.finished_at = func.now()
        await session.flush()


async def link_residual_execution_attempt_to_run(
    session: AsyncSession,
    *,
    attempt_id: int,
    linked_training_run_id: int | None = None,
    linked_prediction_run_id: int | None = None,
) -> None:
    attempt = await get_residual_execution_attempt(session, attempt_id=attempt_id)
    if attempt is not None:
        if linked_training_run_id is not None:
            attempt.linked_training_run_id = linked_training_run_id
        if linked_prediction_run_id is not None:
            attempt.linked_prediction_run_id = linked_prediction_run_id
        await session.flush()
