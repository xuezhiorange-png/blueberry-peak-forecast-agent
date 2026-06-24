from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import get_db_session
from backend.app.maturity.config import MaturityCurveConfig, load_maturity_curve_config
from backend.app.maturity.schemas import MaturityManifestRow
from backend.app.maturity.service import (
    _forecast_payload,
    _model_payload,
    forecast_natural_maturity,
    load_maturity_forecast_result,
    load_maturity_model_result,
    train_maturity_curve,
)
from backend.app.schemas.maturity import (
    MaturityForecastRequest,
    MaturityModelTrainRequest,
    MaturityTaskResponse,
)

router = APIRouter()
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]


def _config_path() -> Path:
    return Path("configs/maturity_curve.yaml")


def _config() -> MaturityCurveConfig:
    return load_maturity_curve_config(_config_path())


def _manifest_rows(payload: MaturityModelTrainRequest) -> list[MaturityManifestRow]:
    return [MaturityManifestRow(**item.model_dump()) for item in payload.manifest_rows]


def _map_error(exc: Exception) -> HTTPException:
    detail = " ".join(str(exc).split())[:500]
    if isinstance(exc, ValueError):
        if "not found" in detail.lower():
            return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="internal error")


@router.post("/maturity/models/train", response_model=MaturityTaskResponse)
async def train_model(
    payload: MaturityModelTrainRequest,
    session: SessionDep,
) -> MaturityTaskResponse:
    try:
        result = await train_maturity_curve(
            session,
            training_cutoff=payload.training_cutoff,
            manifest_rows=_manifest_rows(payload),
            config=_config(),
            dry_run=payload.dry_run,
        )
    except Exception as exc:  # noqa: BLE001
        raise _map_error(exc) from exc
    return MaturityTaskResponse.model_validate(_model_payload(result))


@router.get("/maturity/models/{run_id}", response_model=MaturityTaskResponse)
async def get_model(run_id: int, session: SessionDep) -> MaturityTaskResponse:
    try:
        result = await load_maturity_model_result(session, run_id=run_id)
    except Exception as exc:  # noqa: BLE001
        raise _map_error(exc) from exc
    return MaturityTaskResponse.model_validate(_model_payload(result))


@router.post("/maturity/forecasts", response_model=MaturityTaskResponse)
async def forecast_model(
    payload: MaturityForecastRequest,
    session: SessionDep,
) -> MaturityTaskResponse:
    try:
        result = await forecast_natural_maturity(
            session,
            model_run_id=payload.model_run_id,
            farm_id=payload.farm_id,
            subfarm_id=payload.subfarm_id,
            season_id=payload.season_id,
            variety_id=payload.variety_id,
            as_of_date=payload.as_of_date,
            prediction_start_date=payload.prediction_start_date,
            prediction_end_date=payload.prediction_end_date,
            expected_marketable_total_kg=payload.expected_marketable_total_kg,
            facility_type=payload.facility_type,
            config=_config(),
            dry_run=payload.dry_run,
        )
    except Exception as exc:  # noqa: BLE001
        raise _map_error(exc) from exc
    return MaturityTaskResponse.model_validate(_forecast_payload(result))


@router.get("/maturity/forecasts/{run_id}", response_model=MaturityTaskResponse)
async def get_forecast(run_id: int, session: SessionDep) -> MaturityTaskResponse:
    try:
        result = await load_maturity_forecast_result(session, run_id=run_id)
    except Exception as exc:  # noqa: BLE001
        raise _map_error(exc) from exc
    return MaturityTaskResponse.model_validate(_forecast_payload(result))
