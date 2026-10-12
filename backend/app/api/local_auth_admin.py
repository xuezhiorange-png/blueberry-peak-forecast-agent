"""Bounded management endpoints; trusted publisher scope precedes object reads."""

import asyncio
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.app.api.local_auth import body, service
from backend.app.local_auth.models import AuthAccount, AuthAuditEvent, AuthResourceGrant
from backend.app.local_auth.passwords import hash_password
from backend.app.local_auth.schemas import (
    CreateAccount,
    ForecastGrant,
    QualityGrantRequest,
    ResetPassword,
    RevokeGrant,
    RoleChange,
    StatusChange,
)
from backend.app.local_auth.service import audit, summary
from backend.app.local_auth.sessions import AuthError, envelope, error, now

router = APIRouter()


def page(request: Request, allowed: set[str]) -> tuple[int, str | None]:
    if set(request.query_params) - allowed:
        raise AuthError("INVALID_REQUEST", 422)
    value = request.query_params.get("page_size", "20")
    if not value.isascii() or not value.isdecimal() or not 1 <= int(value) <= 100:
        raise AuthError("INVALID_REQUEST", 422)
    after = next((request.query_params.get(v) for v in allowed if v.startswith("after_")), None)
    if after is not None:
        try:
            after = str(UUID(after))
        except ValueError:
            raise AuthError("INVALID_REQUEST", 422) from None
    return int(value), after


@router.api_route("/{resource}", methods=["GET", "POST"])
@router.api_route("/{resource}/{object_id}/{action}", methods=["POST", "PATCH"])
async def manage(
    request: Request, resource: str, object_id: str | None = None, action: str | None = None
) -> JSONResponse:
    try:
        auth = service(request)
        auth.transport(request, modifying=request.method != "GET")
        async with auth.factory() as db, db.begin():
            principal, boundary = await auth.administrator(db, request)
            data: Any = {}
            if resource == "users" and request.method == "POST" and action is None:
                account = await auth.create_account(
                    db, principal, boundary, CreateAccount.model_validate(await body(request))
                )
                account_summary = summary(account)
                return envelope(
                    {
                        key: account_summary[key]
                        for key in (
                            "account_id",
                            "principal_id",
                            "role",
                            "status",
                            "must_change_password",
                        )
                    },
                    201,
                )
            if resource == "users" and object_id is not None:
                try:
                    object_id = str(UUID(object_id))
                except ValueError:
                    raise AuthError("INVALID_REQUEST", 422) from None
                account = await auth.managed_account(db, boundary, object_id)
                payload: Any
                incoming = await body(request)
                if action == "status" and request.method == "PATCH":
                    payload = StatusChange.model_validate(incoming)
                elif action == "role" and request.method == "PATCH":
                    payload = RoleChange.model_validate(incoming)
                elif action == "reset-password" and request.method == "POST":
                    payload = ResetPassword.model_validate(incoming)
                else:
                    raise AuthError("NOT_FOUND", 404)
                if account.auth_revision != payload.expected_auth_revision:
                    raise AuthError("REVISION_CONFLICT", 409)
                reducing = (
                    action == "reset-password"
                    or getattr(payload, "status", "ACTIVE") == "DISABLED"
                    or getattr(payload, "role", "ADMIN") != "ADMIN"
                )
                if reducing:
                    await auth.protect_last_admin(db, account)
                if action == "status":
                    account.status = payload.status
                    account.disabled_at = now() if payload.status == "DISABLED" else None
                    if payload.status == "ACTIVE":
                        # Re-enable must not revive any previous grants.
                        grants = (
                            await db.scalars(
                                select(AuthResourceGrant).where(
                                    AuthResourceGrant.principal_id == account.principal_id,
                                    AuthResourceGrant.revoked_at.is_(None),
                                )
                            )
                        ).all()
                        for old_grant in grants:
                            old_grant.revoked_at = now()
                        account.grant_revision += 1
                elif action == "role":
                    if payload.role not in boundary.create_roles:
                        raise AuthError("FORBIDDEN")
                    account.role = payload.role
                else:
                    account.password_hash = await asyncio.to_thread(
                        hash_password, payload.new_temporary_password
                    )
                    account.must_change_password = True
                await auth.changed(
                    db,
                    account,
                    principal,
                    "ACCOUNT_" + action.upper().replace("-", "_"),
                    reason=auth.operation_reason(boundary, payload.reason),
                    organization=boundary.organization_ids[0] if boundary.simple_admin else None,
                )
                if action == "reset-password":
                    return envelope(
                        {"reset": True, "must_change_password": account.must_change_password}
                    )
                return envelope(
                    {"account_summary": summary(account), "auth_revision": account.auth_revision}
                )
            if resource == "resource-grants" and request.method == "POST" and action is None:
                payload = TypeAdapter(ForecastGrant | QualityGrantRequest).validate_python(
                    await body(request)
                )
                created_grant = await auth.create_grant(db, principal, boundary, payload)
                return envelope(
                    {
                        "grant_id": created_grant.grant_id,
                        "new_grant_revision": created_grant.grant_revision,
                        "binding_summary": {
                            "resource_kind": created_grant.resource_kind,
                            "capability": created_grant.capability,
                            "organization_id": created_grant.organization_id,
                            "binding": created_grant.forecast_binding
                            if created_grant.resource_kind == "FORECAST"
                            else created_grant.quality_binding,
                        },
                    },
                    201,
                )
            if resource == "resource-grants" and action == "revoke" and request.method == "POST":
                payload = RevokeGrant.model_validate(await body(request))
                # Only grants of approved manageable subjects/organizations are queried.
                grant = await db.scalar(
                    select(AuthResourceGrant)
                    .join(AuthAccount, AuthAccount.principal_id == AuthResourceGrant.principal_id)
                    .where(
                        AuthResourceGrant.grant_id == object_id,
                        AuthResourceGrant.organization_id.in_(boundary.organization_ids),
                        auth.account_scope(boundary),
                    )
                )
                if grant is None:
                    raise AuthError("FORBIDDEN")
                subject = await auth.managed_account(
                    db,
                    boundary,
                    str(
                        await db.scalar(
                            select(AuthAccount.account_id).where(
                                AuthAccount.principal_id == grant.principal_id
                            )
                        )
                    ),
                )
                if subject.grant_revision != payload.expected_grant_revision:
                    raise AuthError("REVISION_CONFLICT", 409)
                if grant.revoked_at is None:
                    before = subject.grant_revision
                    subject.grant_revision += 1
                    grant.revoked_at = now()
                    await auth.revoke_all(db, subject, "GRANT_REVOKED")
                    audit(
                        db,
                        "GRANT_REVOKED",
                        actor=principal.principal_id,
                        target=subject.account_id,
                        grant=grant.grant_id,
                        organization=grant.organization_id,
                        before=before,
                        after=subject.grant_revision,
                        reason=auth.operation_reason(boundary, payload.reason),
                    )
                return envelope({"revoked": True, "new_grant_revision": subject.grant_revision})
            if request.method != "GET" or action is not None:
                raise AuthError("NOT_FOUND", 404)
            if resource == "users":
                size, after = page(request, {"page_size", "after_account_id"})
                account_statement = select(AuthAccount).where(auth.account_scope(boundary))
                if after:
                    account_statement = account_statement.where(AuthAccount.account_id > after)
                account_rows = (
                    await db.scalars(
                        account_statement.order_by(AuthAccount.account_id).limit(size + 1)
                    )
                ).all()
                data = {
                    "items": [summary(v) for v in account_rows[:size]],
                    "next_account_id": account_rows[size - 1].account_id
                    if len(account_rows) > size
                    else None,
                }
            elif resource == "resource-grants":
                size, after = page(request, {"page_size", "after_grant_id", "subject_principal_id"})
                subject_id = request.query_params.get("subject_principal_id")
                grant_statement = (
                    select(AuthResourceGrant)
                    .join(AuthAccount, AuthAccount.principal_id == AuthResourceGrant.principal_id)
                    .where(
                        auth.account_scope(boundary),
                        AuthResourceGrant.organization_id.in_(boundary.organization_ids),
                    )
                )
                if subject_id:
                    grant_statement = grant_statement.where(
                        AuthResourceGrant.principal_id == str(UUID(subject_id))
                    )
                if after:
                    grant_statement = grant_statement.where(AuthResourceGrant.grant_id > after)
                grant_rows = (
                    await db.scalars(
                        grant_statement.order_by(AuthResourceGrant.grant_id).limit(size + 1)
                    )
                ).all()
                data = {
                    "items": [
                        {
                            "grant_id": v.grant_id,
                            "principal_id": v.principal_id,
                            "resource_kind": v.resource_kind,
                            "grant_revision": v.grant_revision,
                            "revoked": v.revoked_at is not None,
                        }
                        for v in grant_rows[:size]
                    ],
                    "next_grant_id": grant_rows[size - 1].grant_id
                    if len(grant_rows) > size
                    else None,
                }
            elif resource == "audit-events":
                size, after = page(
                    request, {"page_size", "after_event_id", "organization_id", "from", "to"}
                )
                organization = request.query_params.get("organization_id")
                if organization not in boundary.organization_ids:
                    raise AuthError("FORBIDDEN")
                start = datetime.fromisoformat(request.query_params.get("from", ""))
                end = datetime.fromisoformat(request.query_params.get("to", ""))
                if (
                    not start.tzinfo
                    or not end.tzinfo
                    or not 0 < (end - start).total_seconds() <= 31 * 86400
                ):
                    raise AuthError("INVALID_REQUEST", 422)
                audit_statement = select(AuthAuditEvent).where(
                    AuthAuditEvent.organization_id == organization,
                    AuthAuditEvent.occurred_at >= start,
                    AuthAuditEvent.occurred_at <= end,
                )
                if after:
                    audit_statement = audit_statement.where(AuthAuditEvent.event_id > after)
                audit_rows = (
                    await db.scalars(
                        audit_statement.order_by(AuthAuditEvent.event_id).limit(size + 1)
                    )
                ).all()
                data = {
                    "items": [
                        {"event_id": v.event_id, "action": v.action, "result_code": v.result_code}
                        for v in audit_rows[:size]
                    ],
                    "next_event_id": audit_rows[size - 1].event_id
                    if len(audit_rows) > size
                    else None,
                }
            else:
                raise AuthError("NOT_FOUND", 404)
            return envelope(data)
    except AuthError as exc:
        return error(exc)
    except (ValidationError, ValueError):
        return error(AuthError("INVALID_REQUEST", 422))
    except IntegrityError:
        return error(AuthError("REVISION_CONFLICT", 409))
    except (SQLAlchemyError, OSError, TimeoutError):
        return error(AuthError("AUTHORIZATION_UNAVAILABLE", 503))
