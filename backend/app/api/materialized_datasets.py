"""Lane D materialized dataset manifest and hash API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import get_db_session
from backend.app.s2_materialized_dataset.lane_d.schemas import MaterializedDatasetApiResponse
from backend.app.s2_materialized_dataset.lane_d.service import load_materialized_dataset_result
from backend.app.s2_materialized_dataset.shared.contracts import (
    MATERIALIZED_DATASET_API_POLICY_VERSION,
)

router = APIRouter()


@router.get(
    "/{dataset_id}/versions/{dataset_version}",
    response_model=MaterializedDatasetApiResponse,
)
async def get_materialized_dataset_manifest(
    dataset_id: str,
    dataset_version: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MaterializedDatasetApiResponse:
    """Return persisted partition manifests and hashes without partition byte payloads."""
    from backend.app.s2_materialized_dataset.lane_d.builder import MaterializedDatasetBuildError

    def _load(sync_session):
        return load_materialized_dataset_result(
            sync_session,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
        )

    try:
        result = await session.run_sync(_load)
    except MaterializedDatasetBuildError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="materialized dataset not found",
        ) from exc
    return MaterializedDatasetApiResponse.from_result(
        result,
        api_policy_version=MATERIALIZED_DATASET_API_POLICY_VERSION,
    )
