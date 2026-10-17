"""Three controlled S2 endpoints; opaque tokens never replace authentication."""

import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from backend.app.api.local_auth import service
from backend.app.business_access.response import DiscoveryResponse, failure
from backend.app.business_access.schemas import Filters, Selection
from backend.app.business_access.service import DiscoveryService
from backend.app.forecast_intelligence.read_schemas import ReadError
from backend.app.local_auth.authorization import read_admission
from backend.app.local_auth.sessions import AuthError

router = APIRouter()


async def handle(request: Request, operation: str) -> JSONResponse:
    try:
        auth = service(request)
        principal = await auth.authenticate(request, csrf=operation == "selection")
        discovery = DiscoveryService(auth)
        if len(request.scope.get("query_string", b"")) > 8192:
            raise AuthError("INVALID_REQUEST", 422)
        params = request.query_params
        if len(params.multi_items()) != len(params):
            raise AuthError("INVALID_REQUEST", 422)
        async with auth.factory() as db, read_admission(auth, db, request, principal):
            if operation == "selection":
                if params:
                    raise AuthError("INVALID_REQUEST", 422)
                payload = bytearray()
                async for chunk in request.stream():
                    if len(payload) + len(chunk) > 131072:
                        raise AuthError("REQUEST_BODY_TOO_LARGE", 413)
                    payload.extend(chunk)
                selection = Selection.model_validate_json(bytes(payload))
                data, catalog, query = await discovery.selection(db, principal, selection)
                return DiscoveryResponse(data, discovery, request, principal, catalog, query)
            if operation == "scope":
                if params:
                    raise AuthError("INVALID_REQUEST", 422)
                data, catalog = await discovery.scope(db, principal)
            else:
                data, catalog = await discovery.saved_runs(
                    db, principal, Filters.model_validate(dict(params))
                )
            return DiscoveryResponse(data, discovery, request, principal, catalog)
    except (ValidationError, ValueError, UnicodeError, json.JSONDecodeError):
        return failure(AuthError("INVALID_REQUEST", 422))
    except AuthError as exc:
        return failure(exc)
    except ReadError as exc:
        return failure(AuthError(exc.code, exc.status_code))
    except (SQLAlchemyError, OSError, TimeoutError):
        return failure(AuthError("AUTHORIZATION_UNAVAILABLE", 503))


@router.get("/scope")
async def scope(request: Request) -> JSONResponse:
    return await handle(request, "scope")


@router.get("/saved-runs")
async def saved_runs(request: Request) -> JSONResponse:
    return await handle(request, "saved-runs")


@router.post("/selection")
async def selection(request: Request) -> JSONResponse:
    return await handle(request, "selection")
