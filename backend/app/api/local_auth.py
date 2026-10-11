"""End-user session endpoints, never accepting Trial actor fallback."""

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from backend.app.local_auth.models import AuthAccount, AuthSession
from backend.app.local_auth.passwords import hash_password, verify_password
from backend.app.local_auth.schemas import ChangePassword, Login
from backend.app.local_auth.service import AuthService, audit
from backend.app.local_auth.sessions import COOKIE, AuthError, cookie, digest, envelope, error, now

router = APIRouter()


def service(request: Request) -> AuthService:
    value: AuthService | None = getattr(request.app.state, "local_auth", None)
    if value is None:
        raise AuthError("AUTHORIZATION_UNAVAILABLE", 503)
    return value


async def body(request: Request) -> dict[str, Any]:
    payload = bytearray()
    async for chunk in request.stream():
        if len(payload) + len(chunk) > 16384:
            raise AuthError("REQUEST_BODY_TOO_LARGE", 413)
        payload.extend(chunk)
    request._body = bytes(payload)
    try:
        data = await request.json()
    except ValueError:
        raise AuthError("INVALID_REQUEST", 422) from None
    if not isinstance(data, dict):
        raise AuthError("INVALID_REQUEST", 422)
    return data


@router.api_route("/{operation}", methods=["GET", "POST"])
async def session_operation(operation: str, request: Request) -> JSONResponse:
    try:
        auth = service(request)
        expected = {
            "csrf": "GET",
            "me": "GET",
            "login": "POST",
            "logout": "POST",
            "change-password": "POST",
        }
        if expected.get(operation) != request.method:
            raise AuthError("NOT_FOUND", 404)
        auth.transport(request, modifying=request.method == "POST")
        if operation == "csrf":
            async with auth.factory() as db, db.begin():
                if COOKIE in request.cookies:
                    # Determine session kind from trusted metadata, never a client claim.
                    current = await db.scalar(
                        select(AuthSession).where(
                            AuthSession.token_digest == digest(auth.token(request))
                        )
                    )
                    session, _ = await auth.load(
                        db, request, preauth=current is not None and current.kind == "PREAUTH"
                    )
                    import secrets

                    token = secrets.token_urlsafe(32)
                    session.csrf_token_digest = digest(token)
                    return envelope({"csrf_token": token, "expires_in": 300})
                raw, token = await auth.issue(db, None)
            response = envelope({"csrf_token": token, "expires_in": 300})
            cookie(response, raw)
            return response
        if operation == "login":
            result, raw = await auth.login(request, Login.model_validate(await body(request)))
            response = envelope(result)
            cookie(response, raw)
            return response
        principal = await auth.authenticate(request, csrf=request.method == "POST")
        if operation == "me":
            return envelope(
                {
                    "principal_id": principal.principal_id,
                    "role": principal.role,
                    "must_change_password": principal.must_change_password,
                    "auth_revision": principal.auth_revision,
                    "grant_revision": principal.grant_revision,
                }
            )
        data = await body(request)
        async with auth.factory() as db, db.begin():
            account = await db.scalar(
                select(AuthAccount)
                .where(AuthAccount.account_id == principal.account_id)
                .with_for_update()
            )
            _, fresh = await auth.load(db, request, csrf=True)
            assert account is not None and fresh is not None
            if operation == "logout":
                if data:
                    raise AuthError("INVALID_REQUEST", 422)
                session, _ = await auth.load(db, request, csrf=True)
                session.revoked_at, session.revoke_reason = now(), "LOGOUT"
                audit(db, "LOGOUT", actor=principal.principal_id)
                response = envelope({"logged_out": True})
                response.delete_cookie(COOKIE, secure=True, httponly=True, samesite="lax")
                return response
            payload = ChangePassword.model_validate(data)
            import asyncio

            if not await asyncio.to_thread(
                verify_password, account.password_hash, payload.current_password
            ):
                raise AuthError("INVALID_CREDENTIALS", 401)
            account.password_hash = await asyncio.to_thread(hash_password, payload.new_password)
            account.must_change_password = False
            await auth.changed(db, account, principal, "PASSWORD_CHANGED")
            raw, _ = await auth.issue(db, account)
        response = envelope({"password_changed": True})
        cookie(response, raw)
        return response
    except AuthError as exc:
        return error(exc)
    except ValidationError:
        return error(AuthError("INVALID_REQUEST", 422))
    except (SQLAlchemyError, OSError, TimeoutError):
        return error(AuthError("AUTHORIZATION_UNAVAILABLE", 503))
