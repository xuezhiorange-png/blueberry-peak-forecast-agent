"""S4 trial page API routes.

Handlers are intentionally limited to validation, authorization, delegation,
and public response mapping. Domain calculations remain outside this module.
"""

from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.actual_harvest_import.api_errors import ActualHarvestApiError
from backend.app.actual_harvest_import.api_schemas import (
    ActualHarvestApiCommitRequest,
    ActualHarvestApiCreateImportRequest,
)
from backend.app.db.session import get_db_session
from backend.app.trial import (
    TrialActorDep,
    TrialActualHarvestCommitResponse,
    TrialActualHarvestImportCreateResponse,
    TrialActualHarvestImportStatusResponse,
    TrialApiError,
    TrialErrorResponse,
    TrialForecastCreateRequest,
    TrialForecastDailyCurveResponse,
    TrialForecastSummaryResponse,
    TrialQualityComparisonResponse,
    TrialQualityReportCreateRequest,
    TrialQualityReportResponse,
    TrialServiceDep,
    map_actual_harvest_error,
    map_unhandled_error,
)

router = APIRouter()
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]


def _request_id(request: Request) -> str:
    candidate = request.headers.get("x-request-id")
    if candidate and len(candidate) <= 128 and candidate.isascii() and candidate.isprintable():
        return candidate
    return uuid4().hex


def _error_response(request_id: str, error: TrialApiError) -> JSONResponse:
    body = TrialErrorResponse(
        request_id=request_id,
        code=error.code.value,
        message_template_id=error.code.value,
        retryable=error.retryable,
        details=error.details,
    )
    return JSONResponse(status_code=error.status_code, content=body.model_dump(mode="json"))


@router.post(
    "/forecasts",
    response_model=TrialForecastSummaryResponse,
    operation_id="createTrialForecast",
)
async def create_trial_forecast(
    request: Request,
    body: TrialForecastCreateRequest,
    session: SessionDep,
    actor: TrialActorDep,
    service: TrialServiceDep,
) -> TrialForecastSummaryResponse | JSONResponse:
    request_id = _request_id(request)
    try:
        return await service.create_forecast(session, body, actor)
    except TrialApiError as error:
        return _error_response(request_id, error)
    except ActualHarvestApiError as error:
        return _error_response(request_id, map_actual_harvest_error(error))
    except Exception as error:
        return _error_response(request_id, map_unhandled_error(error))


@router.get(
    "/forecasts/{run_id}",
    response_model=TrialForecastSummaryResponse,
    operation_id="getTrialForecast",
)
async def get_trial_forecast(
    run_id: str,
    request: Request,
    session: SessionDep,
    actor: TrialActorDep,
    service: TrialServiceDep,
) -> TrialForecastSummaryResponse | JSONResponse:
    request_id = _request_id(request)
    try:
        return await service.get_forecast(session, run_id, actor)
    except TrialApiError as error:
        return _error_response(request_id, error)
    except ActualHarvestApiError as error:
        return _error_response(request_id, map_actual_harvest_error(error))
    except Exception as error:
        return _error_response(request_id, map_unhandled_error(error))


@router.get(
    "/forecasts/{run_id}/daily-curve",
    response_model=TrialForecastDailyCurveResponse,
    operation_id="getTrialForecastDailyCurve",
)
async def get_trial_forecast_daily_curve(
    run_id: str,
    request: Request,
    session: SessionDep,
    actor: TrialActorDep,
    service: TrialServiceDep,
) -> TrialForecastDailyCurveResponse | JSONResponse:
    request_id = _request_id(request)
    try:
        return await service.get_daily_curve(session, run_id, actor)
    except TrialApiError as error:
        return _error_response(request_id, error)
    except ActualHarvestApiError as error:
        return _error_response(request_id, map_actual_harvest_error(error))
    except Exception as error:
        return _error_response(request_id, map_unhandled_error(error))


@router.get(
    "/forecasts/{run_id}/export.csv",
    response_model=None,
    operation_id="exportTrialForecastCsv",
)
async def export_trial_forecast_csv(
    run_id: str,
    request: Request,
    session: SessionDep,
    actor: TrialActorDep,
    service: TrialServiceDep,
) -> Response | JSONResponse:
    request_id = _request_id(request)
    try:
        document = await service.export_forecast(session, run_id, actor)
        return Response(
            content=document.content,
            media_type="text/csv",
            headers={
                "content-disposition": f'attachment; filename="{document.filename}"',
                "x-request-id": request_id,
            },
        )
    except TrialApiError as error:
        return _error_response(request_id, error)
    except ActualHarvestApiError as error:
        return _error_response(request_id, map_actual_harvest_error(error))
    except Exception as error:
        return _error_response(request_id, map_unhandled_error(error))


@router.post(
    "/actual-harvest/imports",
    response_model=TrialActualHarvestImportCreateResponse,
    operation_id="createTrialActualHarvestImport",
)
async def create_trial_actual_harvest_import(
    request: Request,
    body: ActualHarvestApiCreateImportRequest,
    session: SessionDep,
    actor: TrialActorDep,
    service: TrialServiceDep,
) -> TrialActualHarvestImportCreateResponse | JSONResponse:
    request_id = _request_id(request)
    try:
        return await service.create_import(session, body, actor)
    except TrialApiError as error:
        return _error_response(request_id, error)
    except ActualHarvestApiError as error:
        return _error_response(request_id, map_actual_harvest_error(error))
    except Exception as error:
        return _error_response(request_id, map_unhandled_error(error))


@router.get(
    "/actual-harvest/imports/{import_id}",
    response_model=TrialActualHarvestImportStatusResponse,
    operation_id="getTrialActualHarvestImport",
)
async def get_trial_actual_harvest_import(
    import_id: str,
    request: Request,
    session: SessionDep,
    actor: TrialActorDep,
    service: TrialServiceDep,
) -> TrialActualHarvestImportStatusResponse | JSONResponse:
    request_id = _request_id(request)
    try:
        return await service.get_import(session, import_id, actor)
    except TrialApiError as error:
        return _error_response(request_id, error)
    except ActualHarvestApiError as error:
        return _error_response(request_id, map_actual_harvest_error(error))
    except Exception as error:
        return _error_response(request_id, map_unhandled_error(error))


@router.post(
    "/actual-harvest/imports/{import_id}/commit",
    response_model=TrialActualHarvestCommitResponse,
    operation_id="commitTrialActualHarvestImport",
)
async def commit_trial_actual_harvest_import(
    import_id: str,
    request: Request,
    body: ActualHarvestApiCommitRequest,
    session: SessionDep,
    actor: TrialActorDep,
    service: TrialServiceDep,
) -> TrialActualHarvestCommitResponse | JSONResponse:
    request_id = _request_id(request)
    try:
        return await service.commit_import(session, import_id, body, actor)
    except TrialApiError as error:
        return _error_response(request_id, error)
    except ActualHarvestApiError as error:
        return _error_response(request_id, map_actual_harvest_error(error))
    except Exception as error:
        return _error_response(request_id, map_unhandled_error(error))


@router.post(
    "/quality-reports",
    response_model=TrialQualityReportResponse,
    operation_id="createTrialQualityReport",
)
async def create_trial_quality_report(
    request: Request,
    body: TrialQualityReportCreateRequest,
    session: SessionDep,
    actor: TrialActorDep,
    service: TrialServiceDep,
) -> TrialQualityReportResponse | JSONResponse:
    request_id = _request_id(request)
    try:
        return await service.create_quality_report(session, body, actor)
    except TrialApiError as error:
        return _error_response(request_id, error)
    except ActualHarvestApiError as error:
        return _error_response(request_id, map_actual_harvest_error(error))
    except Exception as error:
        return _error_response(request_id, map_unhandled_error(error))


@router.get(
    "/quality-reports/{report_id}",
    response_model=TrialQualityReportResponse,
    operation_id="getTrialQualityReport",
)
async def get_trial_quality_report(
    report_id: str,
    request: Request,
    session: SessionDep,
    actor: TrialActorDep,
    service: TrialServiceDep,
) -> TrialQualityReportResponse | JSONResponse:
    request_id = _request_id(request)
    try:
        return await service.get_quality_report(session, report_id, actor)
    except TrialApiError as error:
        return _error_response(request_id, error)
    except ActualHarvestApiError as error:
        return _error_response(request_id, map_actual_harvest_error(error))
    except Exception as error:
        return _error_response(request_id, map_unhandled_error(error))


@router.get(
    "/quality-reports/{report_id}/comparison",
    response_model=TrialQualityComparisonResponse,
    operation_id="getTrialQualityComparison",
)
async def get_trial_quality_comparison(
    report_id: str,
    request: Request,
    session: SessionDep,
    actor: TrialActorDep,
    service: TrialServiceDep,
) -> TrialQualityComparisonResponse | JSONResponse:
    request_id = _request_id(request)
    try:
        return await service.get_quality_comparison(session, report_id, actor)
    except TrialApiError as error:
        return _error_response(request_id, error)
    except ActualHarvestApiError as error:
        return _error_response(request_id, map_actual_harvest_error(error))
    except Exception as error:
        return _error_response(request_id, map_unhandled_error(error))


@router.get(
    "/quality-reports/{report_id}/export.csv",
    response_model=None,
    operation_id="exportTrialQualityCsv",
)
async def export_trial_quality_csv(
    report_id: str,
    request: Request,
    session: SessionDep,
    actor: TrialActorDep,
    service: TrialServiceDep,
) -> Response | JSONResponse:
    request_id = _request_id(request)
    try:
        document = await service.export_quality_report(session, report_id, actor)
        return Response(
            content=document.content,
            media_type="text/csv",
            headers={
                "content-disposition": f'attachment; filename="{document.filename}"',
                "x-request-id": request_id,
            },
        )
    except TrialApiError as error:
        return _error_response(request_id, error)
    except ActualHarvestApiError as error:
        return _error_response(request_id, map_actual_harvest_error(error))
    except Exception as error:
        return _error_response(request_id, map_unhandled_error(error))


__all__ = ["router"]
