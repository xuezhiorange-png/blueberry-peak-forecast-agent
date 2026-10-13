"""Fresh authorization under the S1 shared subject lock through actual ASGI send."""

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.types import Receive, Scope, Send

from backend.app.business_access.service import Catalog, DiscoveryService
from backend.app.forecast_intelligence.read_schemas import ForecastReadQuery, ReadError
from backend.app.forecast_intelligence.read_service import ForecastIntelligenceReadService
from backend.app.local_auth.sessions import AuthError, Principal


def failure(exc: AuthError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status,
        content={
            "schema_version": "V0_18_BUSINESS_ACCESS_R1",
            "status": "ERROR",
            "code": exc.code,
            "data": None,
        },
        headers={"Cache-Control": "no-store"},
    )


class DiscoveryResponse(JSONResponse):
    def __init__(
        self,
        data: dict[str, Any],
        service: DiscoveryService,
        request: Request,
        principal: Principal,
        catalog: Catalog,
        query: ForecastReadQuery | None = None,
    ):
        super().__init__(
            {"schema_version": "V0_18_BUSINESS_ACCESS_R1", "status": "READY", "data": data},
            headers={"Cache-Control": "no-store"},
        )
        self.service, self.request, self.principal = service, request, principal
        self.catalog, self.query, self.data = catalog, query, data

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        started = False

        async def release(message: Any) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            async with self.service.auth.factory() as db, db.begin():
                session, account = await self.service.auth.load(db, self.request, shared_lock=True)
                if (
                    account is None
                    or session.session_id != self.principal.session_id
                    or account.principal_id != self.principal.principal_id
                    or account.auth_revision != self.principal.auth_revision
                    or account.grant_revision != self.principal.grant_revision
                    or account.role != self.principal.role
                    or account.must_change_password
                ):
                    raise AuthError("FORBIDDEN")
                current = await self.service.catalog(db, self.principal, self.catalog.directory)
                if current.snapshot != self.catalog.snapshot:
                    raise AuthError("AUTHORITY_MISMATCH", 409)
                if self.query is not None:
                    source = await ForecastIntelligenceReadService(db).curve(self.query)
                    if source.projection_hash != self.data["projection_hash"]:
                        raise AuthError("AUTHORITY_MISMATCH", 409)
                    self.service.signer.verify(
                        self.data["handoff_token"], "selection", self.principal
                    )
                elif self.data.get("next_cursor"):
                    self.service.signer.verify(self.data["next_cursor"], "cursor", self.principal)
                # Natural grant expiry can occur while canonical verification is
                # running; check validity again immediately before releasing bytes.
                _, _, directory = await self.service.directory(db, self.principal)
                if directory != self.catalog.directory:
                    raise AuthError("AUTHORITY_MISMATCH", 409)
                # Session idle/absolute expiry is time-based, not prevented by
                # holding a row lock while canonical verification runs.
                await self.service.auth.load(db, self.request, shared_lock=True)
                # Grant revokers acquire this same subject row exclusively. The
                # shared lock spans headers AND body; sent bytes are not retractable.
                await super().__call__(scope, receive, release)
        except (AuthError, ReadError) as exc:
            if started:
                raise RuntimeError("Protected response unavailable") from None
            status = exc.status if isinstance(exc, AuthError) else exc.status_code
            await failure(AuthError(exc.code, status))(scope, receive, send)
        except (SQLAlchemyError, OSError, TimeoutError):
            if started:
                raise RuntimeError("Protected response unavailable") from None
            await failure(AuthError("AUTHORIZATION_UNAVAILABLE", 503))(scope, receive, send)
