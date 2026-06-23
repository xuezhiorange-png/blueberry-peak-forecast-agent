from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import get_db_session
from backend.app.planning.plan_config import load_production_plan_config
from backend.app.schemas.weather import (
    BaseTemperatureSearchRequest,
    WeatherFeatureBuildRequest,
    WeatherHistoryRequest,
    WeatherMappingResolveRequest,
    WeatherTaskResponse,
)
from backend.app.weather.config import WeatherFeatureConfig, load_weather_feature_config
from backend.app.weather.schemas import BaseTemperatureTrainingSample
from backend.app.weather.service import (
    BaseTemperatureSearchUnavailableError,
    WeatherDataVersionConflictError,
    WeatherMappingConflictError,
    WeatherMappingUnavailableError,
    _base_temperature_payload,
    _weather_feature_payload,
    build_phenology_timeline,
    compute_weather_window_features,
    get_weather_history,
    list_weather_source_locations,
    load_base_temperature_search_result,
    load_weather_feature_result,
    resolve_weather_mapping,
    search_base_temperature,
)

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_db_session)]


def _weather_config_path() -> Path:
    return Path("configs/weather_features.yaml")


def _production_plan_config_path() -> Path:
    return Path("configs/production_plan.yaml")


def _response(status_value: str, payload: dict[str, object]) -> WeatherTaskResponse:
    return WeatherTaskResponse.model_validate(
        {
            "status": status_value,
            "run_id": payload.get("run_id"),
            "source_signature": payload.get("source_signature", ""),
            "config_hash": payload.get("config_hash", ""),
            "feature_version": payload.get("feature_version"),
            "payload": payload,
        }
    )


def _weather_config() -> WeatherFeatureConfig:
    return load_weather_feature_config(_weather_config_path())


def _map_error(exc: Exception) -> HTTPException:
    detail = " ".join(str(exc).split())[:500]
    if isinstance(exc, (WeatherDataVersionConflictError, WeatherMappingConflictError)):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    if isinstance(exc, (WeatherMappingUnavailableError, BaseTemperatureSearchUnavailableError)):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)
    if isinstance(exc, ValueError):
        if "not found" in detail.lower():
            return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="internal error")


@router.post("/weather/mappings/resolve", response_model=WeatherTaskResponse)
async def resolve_mapping(
    payload: WeatherMappingResolveRequest,
    session: SessionDep,
) -> WeatherTaskResponse:
    config = _weather_config()
    try:
        result = await resolve_weather_mapping(
            session,
            location_reference_id=payload.location_reference_id,
            as_of_date=payload.as_of_date,
            config=config,
            persist=False,
        )
    except Exception as exc:  # noqa: BLE001
        raise _map_error(exc) from exc
    return _response(
        result.status,
        {
            "status": result.status,
            "run_id": None,
            "source_signature": "",
            "config_hash": config.config_hash,
            "feature_version": config.rules.features.version,
            "mapping": result.reproducibility_snapshot | {"status": result.status},
        },
    )


@router.get("/weather/source-locations", response_model=WeatherTaskResponse)
async def weather_source_locations(
    as_of_date: str,
    session: SessionDep,
    provider_code: str | None = None,
) -> WeatherTaskResponse:
    from datetime import date

    try:
        result = await list_weather_source_locations(
            session,
            as_of_date=date.fromisoformat(as_of_date),
            provider_code=provider_code,
        )
    except Exception as exc:  # noqa: BLE001
        raise _map_error(exc) from exc
    return _response("completed", {"status": "completed", "payload": result})


@router.post("/weather/history", response_model=WeatherTaskResponse)
async def weather_history(
    payload: WeatherHistoryRequest,
    session: SessionDep,
) -> WeatherTaskResponse:
    config = _weather_config()
    try:
        result = await get_weather_history(
            session,
            location_reference_id=payload.location_reference_id,
            as_of_date=payload.as_of_date,
            start_date=payload.start_date,
            end_date=payload.end_date,
            config=config,
        )
    except Exception as exc:  # noqa: BLE001
        raise _map_error(exc) from exc
    return _response("completed", {"status": "completed", "payload": result})


@router.post("/weather/features", response_model=WeatherTaskResponse)
async def build_features(
    payload: WeatherFeatureBuildRequest,
    session: SessionDep,
) -> WeatherTaskResponse:
    config = _weather_config()
    try:
        result = await compute_weather_window_features(
            session,
            farm_id=payload.farm_id,
            subfarm_id=payload.subfarm_id,
            season_id=payload.season_id,
            variety_id=payload.variety_id,
            as_of_date=payload.as_of_date,
            feature_date=payload.feature_date,
            config=config,
            production_plan_config=load_production_plan_config(_production_plan_config_path()),
            base_temperature_search_run_id=payload.base_temperature_search_run_id,
            anchor_event=payload.anchor_event,
            dry_run=payload.dry_run,
        )
    except Exception as exc:  # noqa: BLE001
        raise _map_error(exc) from exc
    return _response(result.status, _weather_feature_payload(result))


@router.post("/weather/timeline", response_model=WeatherTaskResponse)
async def timeline(
    payload: WeatherFeatureBuildRequest,
    session: SessionDep,
) -> WeatherTaskResponse:
    config = _weather_config()
    try:
        result = await build_phenology_timeline(
            session,
            farm_id=payload.farm_id,
            subfarm_id=payload.subfarm_id,
            season_id=payload.season_id,
            variety_id=payload.variety_id,
            as_of_date=payload.as_of_date,
            feature_date=payload.feature_date,
            config=config,
            production_plan_config=load_production_plan_config(_production_plan_config_path()),
            base_temperature_search_run_id=payload.base_temperature_search_run_id,
            anchor_event=payload.anchor_event,
        )
    except Exception as exc:  # noqa: BLE001
        raise _map_error(exc) from exc
    return _response(
        "completed",
        {
            "status": "completed",
            "run_id": None,
            "source_signature": "",
            "config_hash": config.config_hash,
            "feature_version": config.rules.features.version,
            "timeline": result,
        },
    )


@router.post("/weather/base-temperature-searches", response_model=WeatherTaskResponse)
async def run_base_temperature_search(
    payload: BaseTemperatureSearchRequest,
    session: SessionDep,
) -> WeatherTaskResponse:
    config = _weather_config()
    try:
        result = await search_base_temperature(
            session,
            training_cutoff=payload.training_cutoff,
            samples=[
                BaseTemperatureTrainingSample(
                    plan_id=item.plan_id,
                    anchor_event=item.anchor_event,
                    target_event=item.target_event,
                    sample_weight=item.sample_weight,
                    include=item.include,
                    exclusion_reason=item.exclusion_reason,
                )
                for item in payload.samples
            ],
            config=config,
            variety_id=payload.variety_id,
            climate_zone_id=payload.climate_zone_id,
            scope_type=payload.scope_type,
            dry_run=payload.dry_run,
        )
    except Exception as exc:  # noqa: BLE001
        raise _map_error(exc) from exc
    return _response(result.status, _base_temperature_payload(result))


@router.get("/weather/features/{run_id}", response_model=WeatherTaskResponse)
async def get_feature_run(run_id: int, session: SessionDep) -> WeatherTaskResponse:
    try:
        result = await load_weather_feature_result(session, run_id=run_id)
    except Exception as exc:  # noqa: BLE001
        raise _map_error(exc) from exc
    return _response(result.status, _weather_feature_payload(result))


@router.get("/weather/base-temperature-searches/{run_id}", response_model=WeatherTaskResponse)
async def get_base_temperature_run(run_id: int, session: SessionDep) -> WeatherTaskResponse:
    try:
        result = await load_base_temperature_search_result(session, run_id=run_id)
    except Exception as exc:  # noqa: BLE001
        raise _map_error(exc) from exc
    return _response(result.status, _base_temperature_payload(result))
