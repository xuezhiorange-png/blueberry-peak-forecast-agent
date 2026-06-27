from __future__ import annotations

from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.residual_model import (
    ResidualModelArtifact,
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
                ResidualModelPredictionRun.prediction_input_signature
                == prediction_input_signature
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
