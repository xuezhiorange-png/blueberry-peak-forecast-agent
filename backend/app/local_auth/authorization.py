"""Exact grants before business reads, then locked ASGI response release."""

import hashlib
import json
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from starlette.types import Receive, Scope, Send

from backend.app.forecast_intelligence.decision_schemas import CostSelection, DecisionSelection
from backend.app.forecast_intelligence.decision_service import DecisionSupportService
from backend.app.forecast_intelligence.read_schemas import ForecastReadQuery, QualityReadQuery
from backend.app.forecast_intelligence.read_service import (
    PUBLIC_EVIDENCE_HASHES,
    ForecastIntelligenceReadService,
)
from backend.app.local_auth.models import AuthResourceGrant
from backend.app.local_auth.service import AuthService
from backend.app.local_auth.sessions import AuthError, Principal, now


def binding_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()


def active(grant: AuthResourceGrant) -> bool:
    return grant.revoked_at is None and grant.valid_from <= now() < grant.valid_until


def grant_snapshot(grant: AuthResourceGrant) -> dict[str, Any]:
    return {
        "grant_id": grant.grant_id,
        "principal_id": grant.principal_id,
        "resource_kind": grant.resource_kind,
        "capability": grant.capability,
        "organization_id": grant.organization_id,
        "grant_revision": grant.grant_revision,
        "forecast_binding": grant.forecast_binding,
        "quality_binding": grant.quality_binding,
    }


async def authorize(
    service: AuthService,
    principal: Principal,
    query: ForecastReadQuery | QualityReadQuery | None,
) -> tuple[dict[str, Any], ForecastReadQuery | QualityReadQuery | None]:
    if principal.must_change_password:
        raise AuthError("PASSWORD_CHANGE_REQUIRED")
    try:
        organizations = json.loads(service.settings.local_auth_organization_ids_json)
        if (
            not isinstance(organizations, list)
            or not organizations
            or any(not isinstance(v, str) or not v or "*" in v for v in organizations)
        ):
            raise ValueError("Invalid organization authority")
    except (ValueError, TypeError):
        raise AuthError("AUTHORIZATION_UNAVAILABLE", 503) from None
    quality = isinstance(query, QualityReadQuery)
    capability = "may_read_quality" if quality else "may_read_forecast"
    async with service.factory() as db:
        grants = (
            await db.scalars(
                select(AuthResourceGrant).where(
                    AuthResourceGrant.principal_id == principal.principal_id,
                    AuthResourceGrant.capability == capability,
                    AuthResourceGrant.organization_id.in_(organizations),
                    AuthResourceGrant.revoked_at.is_(None),
                )
            )
        ).all()
        for grant in grants:
            if not active(grant):
                continue
            if isinstance(query, ForecastReadQuery):
                binding = grant.forecast_binding
                if binding is None or binding.get("identity") != query.model_dump(
                    mode="json", exclude={"expected_source_result_hash"}
                ):
                    continue
                expected = binding["expected_source_result_hash"]
                if query.expected_source_result_hash not in (None, expected):
                    raise AuthError("FORBIDDEN")
                return grant_snapshot(grant), query.model_copy(
                    update={"expected_source_result_hash": expected}
                )
            if isinstance(query, QualityReadQuery):
                binding = grant.quality_binding
                if binding is None or binding.get("query") != query.model_dump(mode="json"):
                    continue
                if (
                    binding["evidence_hashes"] != PUBLIC_EVIDENCE_HASHES
                    or binding_digest(PUBLIC_EVIDENCE_HASHES) != binding["evidence_set_digest"]
                ):
                    raise AuthError("AUTHORITY_MISMATCH", 409)
                return grant_snapshot(grant), query
            if query is None:
                return grant_snapshot(grant), None
    raise AuthError("FORBIDDEN")


class GuardedResponse(JSONResponse):
    """Hold the shared subject lock through ASGI send; no bytes before recheck.

    Revokers take the same subject row's exclusive lock and commit. A revocation
    committed before this gate wins. Already sent bytes are not retractable.
    """

    def __init__(
        self,
        data: Any,
        service: AuthService,
        request: Request,
        principal: Principal,
        snapshot: dict[str, Any],
    ):
        super().__init__(data, headers={"Cache-Control": "no-store"})
        self.service, self.request = service, request
        self.principal, self.snapshot = principal, snapshot

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        started = False

        async def release(message: Any) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            async with self.service.factory() as db, db.begin():
                _, account = await self.service.load(db, self.request, shared_lock=True)
                assert account is not None
                if (
                    account.principal_id != self.principal.principal_id
                    or account.auth_revision != self.principal.auth_revision
                    or account.grant_revision != self.principal.grant_revision
                    or account.must_change_password
                ):
                    raise AuthError("FORBIDDEN")
                grant = await db.scalar(
                    select(AuthResourceGrant)
                    .where(AuthResourceGrant.grant_id == self.snapshot["grant_id"])
                    .execution_options(populate_existing=True)
                )
                if grant is None or not active(grant) or grant_snapshot(grant) != self.snapshot:
                    raise AuthError("FORBIDDEN")
                # ORM snapshots are fresh in an independent READ COMMITTED tx.
                await super().__call__(scope, receive, release)
        except AuthError as exc:
            if started:
                raise RuntimeError("Response release unavailable") from None
            await protected_error(self.request, exc)(scope, receive, send)
        except (SQLAlchemyError, OSError, TimeoutError):
            if started:
                raise RuntimeError("Response release unavailable") from None
            await protected_error(self.request, AuthError("AUTHORIZATION_UNAVAILABLE", 503))(
                scope, receive, send
            )


def protected_error(request: Request, exc: AuthError) -> JSONResponse:
    if request.url.path.startswith("/api/v1/decision-support/"):
        from backend.app.api.forecast_intelligence_decision import decision_error

        response = decision_error(exc.code, exc.status)
    else:
        from backend.app.api.forecast_intelligence_read import _error

        response = _error(exc.code, exc.status)
    response.headers["Cache-Control"] = "no-store"
    return response


async def protected_transport(request: Request, *, decision: bool = False) -> JSONResponse:
    """Direct shared-service projection; no forecast math or Trial identity bridge."""
    from pydantic import BaseModel, ValidationError

    from backend.app.forecast_intelligence.read_schemas import ReadError

    service: AuthService | None = getattr(request.app.state, "local_auth", None)
    if service is None:
        return protected_error(request, AuthError("AUTHORIZATION_UNAVAILABLE", 503))
    try:
        principal = await service.authenticate(request, csrf=request.method == "POST")
        operation = request.url.path.rsplit("/", 1)[-1]
        query: ForecastReadQuery | QualityReadQuery | None
        payload: dict[str, Any] | None = None
        if decision and request.method == "POST":
            payload = await request.json()
            # Existing S2 uses two-phase selection then scenario validation.
            selection = DecisionSelection.model_validate(
                {k: payload[k] for k in DecisionSelection.model_fields if k in payload}
            )
            query = ForecastReadQuery.model_validate(
                {
                    **selection.forecast_selection.model_dump(mode="json"),
                    "expected_source_result_hash": selection.expected_source_result_hash,
                }
            )
        elif decision:
            query = None
        elif operation == "quality":
            query = QualityReadQuery.model_validate(dict(request.query_params))
        else:
            query = ForecastReadQuery.model_validate(dict(request.query_params))
        snapshot, query = await authorize(service, principal, query)
        result: BaseModel
        async with service.factory() as db:
            with db.no_autoflush:
                reader = ForecastIntelligenceReadService(db)
                if decision:
                    engine = DecisionSupportService(reader)
                    if payload is None:
                        result = engine.business_loss(
                            CostSelection.model_validate(dict(request.query_params))
                        )
                    elif operation == "simulate-capacity":
                        result = await engine.simulate(payload)
                    elif operation == "compare-capacity-scenarios":
                        result = await engine.compare(payload)
                    else:
                        raise AuthError("NOT_FOUND", 404)
                else:
                    if operation not in {
                        "overview",
                        "curve",
                        "hierarchy",
                        "uncertainty",
                        "attribution",
                        "quality",
                    }:
                        raise AuthError("NOT_FOUND", 404)
                    result = await getattr(reader, operation)(query)
                content = result.model_dump(mode="json")
        if isinstance(query, ForecastReadQuery):
            if (
                content.get("forecast_identity")
                != query.model_dump(mode="json", exclude={"expected_source_result_hash"})
                or content.get("source_result_hash") != query.expected_source_result_hash
            ):
                raise AuthError("AUTHORITY_MISMATCH", 409)
        return GuardedResponse(content, service, request, principal, snapshot)
    except AuthError as exc:
        return protected_error(request, exc)
    except ReadError as exc:
        return protected_error(request, AuthError(exc.code, exc.status_code))
    except (ValidationError, ValueError, TypeError, KeyError):
        return protected_error(request, AuthError("INVALID_REQUEST", 422))
    except (SQLAlchemyError, OSError, TimeoutError):
        return protected_error(request, AuthError("PERSISTENCE_UNAVAILABLE", 503))
