"""Revocable sessions and CSRF; all checks use authentication metadata only."""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.core.config import AppSettings
from backend.app.local_auth.models import AuthAccount, AuthSession

COOKIE = "__Host-blueberry-session"


class AuthError(Exception):
    def __init__(self, code: str, status: int = 403):
        self.code, self.status = code, status
        super().__init__(code)


def now() -> datetime:
    return datetime.now(UTC)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def envelope(data: Any, status: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "schema_version": "V0_18_LOCAL_AUTH_R1",
            "request_id": None,
            "status": "READY",
            "data": data,
        },
        headers={"Cache-Control": "no-store"},
    )


def error(exc: AuthError) -> JSONResponse:
    response = JSONResponse(
        status_code=exc.status,
        content={
            "schema_version": "V0_18_LOCAL_AUTH_R1",
            "status": "ERROR",
            "code": exc.code,
            "data": None,
        },
        headers={"Cache-Control": "no-store"},
    )
    if exc.status == 401:
        response.delete_cookie(COOKIE, secure=True, httponly=True, samesite="lax")
    return response


def cookie(response: JSONResponse, token: str) -> None:
    response.set_cookie(COOKIE, token, secure=True, httponly=True, samesite="lax", path="/")


@dataclass(frozen=True)
class Principal:
    account_id: str
    principal_id: str
    session_id: str
    role: str
    must_change_password: bool
    auth_revision: int
    grant_revision: int


class Sessions:
    def __init__(self, factory: async_sessionmaker[AsyncSession], settings: AppSettings):
        self.factory, self.settings = factory, settings

    def transport(self, request: Request, *, modifying: bool = False) -> None:
        origin = self.settings.local_auth_origin
        parsed = urlsplit(origin)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.path
            or not self.settings.local_auth_login_bucket_secret.get_secret_value()
        ):
            raise AuthError("AUTHORIZATION_UNAVAILABLE", 503)
        if request.url.scheme != "https" or request.headers.get("host") != parsed.netloc:
            raise AuthError("FORBIDDEN")
        for header in ("host", "origin", "x-csrf-token"):
            if len(request.headers.getlist(header)) > 1:
                raise AuthError("FORBIDDEN")
        if any(header in request.headers for header in ("x-actor", "x-principal-id", "x-role")):
            raise AuthError("FORBIDDEN")
        incoming = request.headers.get("origin")
        if incoming is not None and incoming != origin:
            raise AuthError("FORBIDDEN")
        if modifying:
            if incoming != origin:
                raise AuthError("FORBIDDEN")
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                raise AuthError("UNSUPPORTED_MEDIA_TYPE", 415)

    def token(self, request: Request) -> str:
        cookies = request.headers.getlist("cookie")
        combined = ";".join(cookies)
        values = [
            p.strip().partition("=")[2]
            for p in combined.split(";")
            if p.strip().partition("=")[0] == COOKIE
        ]
        if len(values) != 1 or not 40 <= len(values[0]) <= 128:
            raise AuthError("UNAUTHENTICATED", 401)
        return values[0]

    async def load(
        self,
        db: AsyncSession,
        request: Request,
        *,
        preauth: bool = False,
        csrf: bool = False,
        shared_lock: bool = False,
    ) -> tuple[AuthSession, AuthAccount | None]:
        session = await db.scalar(
            select(AuthSession)
            .where(AuthSession.token_digest == digest(self.token(request)))
            .execution_options(populate_existing=True)
        )
        stamp = now()
        if (
            session is None
            or session.revoked_at is not None
            or stamp >= session.idle_expires_at
            or stamp >= session.absolute_expires_at
        ):
            raise AuthError("UNAUTHENTICATED", 401)
        if preauth != (session.kind == "PREAUTH"):
            raise AuthError("UNAUTHENTICATED", 401)
        account = None
        if session.account_id is not None:
            statement = select(AuthAccount).where(AuthAccount.account_id == session.account_id)
            if shared_lock:
                statement = statement.with_for_update(read=True)
            account = await db.scalar(statement.execution_options(populate_existing=True))
            if (
                account is None
                or account.status != "ACTIVE"
                or session.auth_revision != account.auth_revision
                or session.grant_revision != account.grant_revision
            ):
                raise AuthError("UNAUTHENTICATED", 401)
            # Re-read session AFTER the account lock: logout/revocation uses the same lock.
            if shared_lock:
                await db.refresh(session)
                if (
                    session.revoked_at is not None
                    or now() >= session.idle_expires_at
                    or now() >= session.absolute_expires_at
                    or session.auth_revision != account.auth_revision
                    or session.grant_revision != account.grant_revision
                ):
                    raise AuthError("UNAUTHENTICATED", 401)
        if csrf:
            token = request.headers.get("x-csrf-token", "")
            if not token or not hmac.compare_digest(digest(token), session.csrf_token_digest):
                raise AuthError("FORBIDDEN")
        return session, account

    async def authenticate(self, request: Request, *, csrf: bool = False) -> Principal:
        self.transport(request, modifying=csrf)
        async with self.factory() as db, db.begin():
            session, account = await self.load(db, request, csrf=csrf)
            assert account is not None
            session.last_seen_at = now()
            session.idle_expires_at = min(now() + timedelta(hours=8), session.absolute_expires_at)
            return Principal(
                account.account_id,
                account.principal_id,
                session.session_id,
                account.role,
                account.must_change_password,
                account.auth_revision,
                account.grant_revision,
            )

    async def issue(self, db: AsyncSession, account: AuthAccount | None) -> tuple[str, str]:
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        stamp = now()
        absolute = stamp + (timedelta(hours=24) if account else timedelta(seconds=300))
        db.add(
            AuthSession(
                token_digest=digest(token),
                csrf_token_digest=digest(csrf),
                kind="END_USER" if account else "PREAUTH",
                account_id=account.account_id if account else None,
                auth_revision=account.auth_revision if account else None,
                grant_revision=account.grant_revision if account else None,
                issued_at=stamp,
                last_seen_at=stamp,
                absolute_expires_at=absolute,
                idle_expires_at=min(stamp + timedelta(hours=8), absolute),
            )
        )
        await db.flush()
        return token, csrf

    async def revoke_all(self, db: AsyncSession, account: AuthAccount, reason: str) -> None:
        await db.execute(
            update(AuthSession)
            .where(AuthSession.account_id == account.account_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=now(), revoke_reason=reason)
        )
