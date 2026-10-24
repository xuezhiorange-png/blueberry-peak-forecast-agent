"""Authenticated research-shadow ingress; disabled without explicit server policy."""

import asyncio
import json
from datetime import date
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import Field
from sqlalchemy.exc import SQLAlchemyError
from starlette.types import Receive, Scope, Send

from backend.app.api.local_auth import service
from backend.app.local_auth.authorization import read_admission
from backend.app.local_auth.sessions import AuthError, Principal, error
from backend.app.rolling_forecast import application
from backend.app.rolling_forecast.evaluation import options, review
from backend.app.rolling_forecast.model_artifacts import ModelArtifactError
from backend.app.rolling_forecast.policy import Catalog, load_catalog
from backend.app.rolling_forecast.schemas import Contract, Issue

router = APIRouter()


class Filters(Contract):
    base_id: str | None = Field(default=None, min_length=1, max_length=200)
    target_season: str | None = Field(default=None, pattern=r"^\d{4}-\d{4}$")
    origin_date: date | None = None
    offset: int = Field(default=0, ge=0, le=10000)
    limit: int = Field(default=20, ge=1, le=100)


class Comparison(Contract):
    left_run_id: int = Field(gt=0)
    right_run_id: int = Field(gt=0)


class Review(Contract):
    label_snapshot_reference: str = Field(min_length=1, max_length=200)


def catalog(request: Request) -> Catalog:
    auth = service(request)
    try:
        organizations = json.loads(auth.settings.local_auth_organization_ids_json)
        if not isinstance(organizations, list) or any(
            not isinstance(s, str) for s in organizations
        ):
            raise ValueError("ORGANIZATION_AUTHORITY_MISSING")
        return load_catalog(auth.settings.rolling_forecast_catalog_path, organizations)
    except ValueError:
        raise AuthError("ROLLING_FORECAST_UNAVAILABLE", 503) from None


class ReleasedResponse(JSONResponse):
    def __init__(
        self,
        data: dict[str, Any],
        request: Request,
        principal: Principal,
        policy: Catalog,
        operation: str,
    ):
        super().__init__(
            {"schema_version": "ROLLING_SHADOW_V1", "status": "READY", "data": data},
            headers={"Cache-Control": "no-store"},
        )
        self.request, self.principal, self.policy, self.operation = (
            request,
            principal,
            policy,
            operation,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        started = False

        async def release(message: Any) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            auth = service(self.request)
            async with auth.factory() as db, read_admission(auth, db, self.request, self.principal):
                current = catalog(self.request)
                if current.fingerprint != self.policy.fingerprint:
                    raise AuthError("AUTHORITY_MISMATCH", 409)
                application.contexts(current, self.principal, self.operation)
                # Recheck time-based session validity immediately before bytes.
                await auth.load(db, self.request, shared_lock=True)
                await super().__call__(scope, receive, release)
        except (AuthError, SQLAlchemyError, TimeoutError, OSError) as exc:
            if started:
                raise RuntimeError("Rolling protected response interrupted") from None
            await error(
                exc
                if isinstance(exc, AuthError)
                else AuthError("ROLLING_FORECAST_UNAVAILABLE", 503)
            )(scope, receive, send)


async def handle(request: Request, operation: str, run_id: int | None = None) -> JSONResponse:
    try:
        auth = service(request)
        principal = await auth.authenticate(request, csrf=operation in {"issue", "evaluate"})
        if len(request.scope.get("query_string", b"")) > 8192 or len(
            request.query_params.multi_items()
        ) != len(request.query_params):
            raise AuthError("INVALID_REQUEST", 422)
        params = dict(request.query_params)
        body: Issue | Review | None = None
        if operation in {"issue", "evaluate"}:
            if params:
                raise AuthError("INVALID_REQUEST", 422)
            payload = bytearray()
            async with asyncio.timeout(5):
                async for chunk in request.stream():
                    if len(payload) + len(chunk) > 131072:
                        raise AuthError("REQUEST_BODY_TOO_LARGE", 413)
                    payload.extend(chunk)
            body = (
                Issue.model_validate_json(bytes(payload))
                if operation == "issue"
                else Review.model_validate_json(bytes(payload))
            )
        policy = catalog(request)
        async with auth.factory() as db, read_admission(auth, db, request, principal):
            # A fresh account/session lock precedes model, observation and saved
            # quantity reads. ADMIN has no implicit capability here either.
            if operation == "issue":
                assert isinstance(body, Issue)
                data = await application.issue(db, policy, principal, body)
            elif operation == "evaluate":
                assert isinstance(body, Review) and run_id is not None
                data = await review(db, policy, principal, run_id, body.label_snapshot_reference)
            elif operation == "review_options":
                if params or run_id is None:
                    raise AuthError("INVALID_REQUEST", 422)
                data = await options(db, policy, principal, run_id)
            elif operation == "compare":
                pair = Comparison.model_validate(params)
                left = await application.get(db, policy, principal, pair.left_run_id, "compare")
                right = await application.get(db, policy, principal, pair.right_run_id, "compare")
                data = application.compare(left, right)
            elif operation == "read" and run_id is None:
                filters = Filters.model_validate(params)
                data = await application.history(db, policy, principal, filters.model_dump())
            else:
                if params or run_id is None:
                    raise AuthError("INVALID_REQUEST", 422)
                data = await application.get(db, policy, principal, run_id)
                if operation == "daily":
                    data = {
                        k: data[k]
                        for k in (
                            "run_id",
                            "base_id",
                            "target_season",
                            "origin_date",
                            "input_hash",
                            "result_hash",
                            "result",
                        )
                    }
            return ReleasedResponse(
                data,
                request,
                principal,
                policy,
                "evaluate"
                if operation == "review_options"
                else "read"
                if operation == "daily"
                else operation,
            )
    except AuthError as exc:
        return error(exc)
    except ModelArtifactError as exc:
        return error(AuthError(str(exc), 503 if "UNAVAILABLE" in str(exc) else 409))
    except (ValueError, UnicodeError) as exc:
        # No values, file paths or SQL from an exception reach the caller.
        code = str(exc) if str(exc).isupper() and len(str(exc)) < 100 else "INVALID_REQUEST"
        return error(AuthError(code, 409 if "MISMATCH" in code or "CONFLICT" in code else 422))
    except (SQLAlchemyError, OSError, TimeoutError):
        return error(AuthError("ROLLING_FORECAST_UNAVAILABLE", 503))


@router.post("")
async def issue(request: Request) -> JSONResponse:
    return await handle(request, "issue")


@router.get("")
async def history(request: Request) -> JSONResponse:
    return await handle(request, "read")


@router.get("/compare")
async def compare(request: Request) -> JSONResponse:
    return await handle(request, "compare")


@router.get("/{run_id:int}")
async def detail(request: Request, run_id: int) -> JSONResponse:
    return await handle(request, "read", run_id)


@router.get("/{run_id:int}/daily")
async def daily(request: Request, run_id: int) -> JSONResponse:
    return await handle(request, "daily", run_id)


@router.post("/{run_id:int}/review")
async def evaluate(request: Request, run_id: int) -> JSONResponse:
    return await handle(request, "evaluate", run_id)


@router.get("/{run_id:int}/review")
async def review_options(request: Request, run_id: int) -> JSONResponse:
    return await handle(request, "review_options", run_id)
