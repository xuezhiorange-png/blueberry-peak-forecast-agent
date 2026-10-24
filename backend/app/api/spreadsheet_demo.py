"""No upload endpoint: fixed SYNTHETIC assets, existing scoped application service."""

import asyncio
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from backend.app.api.local_auth import service
from backend.app.api.rolling_forecast import ReleasedResponse, catalog
from backend.app.local_auth.authorization import read_admission
from backend.app.local_auth.sessions import AuthError, error
from backend.app.rolling_forecast import application
from backend.app.rolling_forecast import spreadsheet_demo as demo

router = APIRouter()


async def handle(
    request: Request, action: str, scenario: demo.SCENARIOS = "complete", kind: str = "xlsx"
) -> JSONResponse:
    try:
        auth = service(request)
        principal = await auth.authenticate(request, csrf=action != "download")
        if action != "download" and request.query_params:
            raise AuthError("INVALID_REQUEST", 422)
        body = None
        if action != "download":
            payload = bytearray()
            async with asyncio.timeout(5):
                async for chunk in request.stream():
                    if len(payload) + len(chunk) > 8192:
                        raise AuthError("REQUEST_BODY_TOO_LARGE", 413)
                    payload.extend(chunk)
            body = demo.Binding.model_validate_json(bytes(payload))
            scenario, kind = body.scenario, body.format
        operation = "issue" if action == "issue" else "read"
        policy = catalog(request)
        async with auth.factory() as db, read_admission(auth, db, request, principal):
            selected, context, source = demo.resolve(
                auth.settings, policy, principal, scenario, operation
            )
            if action == "download":
                data = demo.download(selected, kind)
            else:
                assert body is not None
                data = demo.validate_binding(selected, context, source, body)
                if action == "issue":
                    if data["readiness"]["m1_feature_readiness"] != "COMPUTABLE":
                        raise AuthError("SYNTHETIC_SOURCE_NOT_READY", 422)
                    data = await application.issue(
                        db, policy, principal, demo.issue_request(context, selected, body)
                    )
            return ReleasedResponse(data, request, principal, policy, operation)
    except AuthError as exc:
        return error(exc)
    except (ValueError, UnicodeError) as exc:
        code = str(exc) if str(exc).isupper() and len(str(exc)) < 100 else "INVALID_REQUEST"
        return error(AuthError(code, 409 if "MISMATCH" in code else 422))
    except (OSError, TimeoutError, SQLAlchemyError):
        return error(AuthError("SYNTHETIC_DEMO_UNAVAILABLE", 503))


@router.get("")
async def download(
    request: Request, scenario: demo.SCENARIOS = "complete", format: Literal["csv", "xlsx"] = "xlsx"
) -> JSONResponse:
    if len(request.query_params.multi_items()) != len(request.query_params) or set(
        request.query_params
    ) - {"scenario", "format"}:
        return error(AuthError("INVALID_REQUEST", 422))
    return await handle(request, "download", scenario, format)


@router.post("/verify")
async def verify(request: Request) -> JSONResponse:
    return await handle(request, "verify")


@router.post("/issue")
async def issue(request: Request) -> JSONResponse:
    return await handle(request, "issue")
