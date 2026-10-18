"""Transactional account administration. No forecast repository access here."""

import asyncio
import hashlib
import hmac
import json
from datetime import timedelta
from typing import Any

from fastapi import Request
from sqlalchemy import cast, func, or_, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.local_auth.models import (
    AuthAccount,
    AuthAuditEvent,
    AuthResourceGrant,
    AuthSession,
)
from backend.app.local_auth.passwords import HASHER, hash_password, verify_password
from backend.app.local_auth.schemas import (
    CreateAccount,
    ForecastGrant,
    Login,
    PublisherBoundary,
    QualityGrantRequest,
    SimpleAdminCatalog,
)
from backend.app.local_auth.sessions import AuthError, Principal, Sessions, digest, now


def summary(account: AuthAccount) -> dict[str, Any]:
    return {
        name: getattr(account, name)
        for name in (
            "account_id",
            "principal_id",
            "role",
            "status",
            "must_change_password",
            "auth_revision",
            "grant_revision",
        )
    }


def audit(
    db: AsyncSession,
    action: str,
    *,
    actor: str | None = None,
    target: str | None = None,
    grant: str | None = None,
    organization: str | None = None,
    bucket: str | None = None,
    code: str = "SUCCESS",
    before: int | None = None,
    after: int | None = None,
    reason: str | None = None,
) -> None:
    db.add(
        AuthAuditEvent(
            occurred_at=now(),
            actor_principal_id=actor,
            target_account_id=target,
            target_grant_id=grant,
            action=action,
            result_code=code,
            revision_before=before,
            revision_after=after,
            organization_id=organization,
            login_bucket_digest=bucket,
            reason_code=reason if reason is not None else action,
        )
    )


class AuthService(Sessions):
    def __init__(self, factory: Any, settings: Any):
        super().__init__(factory, settings)
        self._hash_slots = asyncio.Semaphore(4)
        self._dummy_hash = hash_password("synthetic-dummy-password-not-an-account")

    def publisher(self, principal: Principal) -> PublisherBoundary:
        if principal.role != "ADMIN" or principal.must_change_password:
            raise AuthError("FORBIDDEN")
        try:
            catalog_raw = self.settings.local_auth_simple_admin_catalog_json.get_secret_value()
            if catalog_raw:
                catalog = SimpleAdminCatalog.model_validate_json(catalog_raw).validate_scope()
                organizations = json.loads(self.settings.local_auth_organization_ids_json)
                if not isinstance(organizations, list) or not set(catalog.organization_ids) <= set(
                    organizations
                ):
                    raise ValueError("Unverified organization directory")
                if any(not isinstance(v, str) or not v or "*" in v for v in organizations):
                    raise ValueError("Invalid organization directory")
                return PublisherBoundary(
                    principal_id=principal.principal_id,
                    organization_ids=catalog.organization_ids,
                    manageable_account_ids=(principal.account_id,),
                    create_roles=("BUSINESS_USER",),
                    simple_admin=True,
                    registered_resources=catalog.resources,
                )
            entries = json.loads(
                self.settings.local_auth_publisher_boundaries_json.get_secret_value()
            )
            if not isinstance(entries, list):
                raise ValueError("Invalid boundaries")
            boundaries = [PublisherBoundary.model_validate(v).validate_scope() for v in entries]
        except (ValueError, TypeError):
            raise AuthError("AUTHORIZATION_UNAVAILABLE", 503) from None
        matches = [b for b in boundaries if str(b.principal_id) == principal.principal_id]
        if len(matches) != 1:
            raise AuthError("FORBIDDEN")
        return matches[0]

    def account_scope(self, boundary: PublisherBoundary) -> Any:
        explicit = AuthAccount.account_id.in_([str(v) for v in boundary.manageable_account_ids])
        if not boundary.simple_admin:
            return explicit
        organizations = cast(AuthAccount.managed_organization_ids, JSONB)
        return or_(
            explicit,
            (AuthAccount.role == "BUSINESS_USER")
            & (organizations != [])
            & organizations.contained_by(list(boundary.organization_ids)),
        )

    @staticmethod
    def operation_reason(boundary: PublisherBoundary, reason: str) -> str | None:
        if not boundary.simple_admin:
            return None
        if len(reason) > 64:
            raise AuthError("INVALID_REQUEST", 422)
        return reason

    async def login(self, request: Request, payload: Login) -> tuple[dict[str, Any], str]:
        self.transport(request, modifying=True)
        secret = self.settings.local_auth_login_bucket_secret.get_secret_value().encode()
        source = request.client.host if request.client else "unknown"
        buckets = [
            (hmac.new(secret, value.encode(), hashlib.sha256).hexdigest(), limit)
            for value, limit in (
                ("username:" + payload.username, 5),
                ("source:" + source, 25),
                ("global", 250),
            )
        ]
        failed = False
        result: dict[str, Any] = {}
        raw = ""
        async with self.factory() as db, db.begin():
            preauth, _ = await self.load(db, request, preauth=True, csrf=True)
            if db.bind is None or db.bind.dialect.name != "postgresql":
                raise AuthError("AUTHORIZATION_UNAVAILABLE", 503)
            await db.execute(text("SET LOCAL lock_timeout = '2s'"))
            await db.execute(text("SET LOCAL statement_timeout = '5s'"))
            # Global admission serializes the bounded hash section across workers;
            # username/source limits remain separate and audited using HMAC buckets.
            counts: dict[str, int] = {}
            for bucket, limit in sorted(buckets):
                lock = int(bucket[:16], 16) % (2**63 - 1)
                await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
                count = await db.scalar(
                    select(func.count())
                    .select_from(AuthAuditEvent)
                    .where(
                        AuthAuditEvent.login_bucket_digest == bucket,
                        AuthAuditEvent.action == "LOGIN_FAILURE",
                        AuthAuditEvent.occurred_at > now() - timedelta(minutes=15),
                    )
                )
                counts[bucket] = count or 0
                locked = await db.scalar(
                    select(AuthAuditEvent.event_id)
                    .where(
                        AuthAuditEvent.login_bucket_digest == bucket,
                        AuthAuditEvent.action == "LOGIN_LIMIT_STARTED",
                        AuthAuditEvent.occurred_at > now() - timedelta(minutes=15),
                    )
                    .limit(1)
                )
                if locked is not None or counts[bucket] >= limit:
                    raise AuthError("LOGIN_LIMITED", 429)
            account = await db.scalar(
                select(AuthAccount)
                .where(AuthAccount.username_normalized == payload.username)
                .with_for_update()
            )
            encoded = account.password_hash if account is not None else self._dummy_hash
            async with self._hash_slots:
                valid = await asyncio.to_thread(verify_password, encoded, payload.password)
            if account is None or account.status != "ACTIVE" or not valid:
                for bucket, limit in buckets:
                    audit(db, "LOGIN_FAILURE", bucket=bucket, code="INVALID_CREDENTIALS")
                    if counts[bucket] + 1 == limit:
                        audit(db, "LOGIN_LIMIT_STARTED", bucket=bucket, code="LOGIN_LIMITED")
                failed = True
            else:
                # Preserve lock order: login buckets -> account -> PREAUTH.
                # The pre-lock ORM snapshot is not permission to consume. Lock
                # the actual session row and refresh before reusing validation.
                preauth_id = preauth.session_id
                locked_preauth = await db.scalar(
                    select(AuthSession)
                    .where(
                        AuthSession.session_id == preauth_id,
                        AuthSession.token_digest == digest(self.token(request)),
                    )
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                if locked_preauth is None:
                    raise AuthError("UNAUTHENTICATED", 401)
                preauth, _ = await self.load(db, request, preauth=True, csrf=True)
                if preauth.session_id != preauth_id:
                    raise AuthError("UNAUTHENTICATED", 401)
                if HASHER.check_needs_rehash(account.password_hash):
                    account.password_hash = await asyncio.to_thread(hash_password, payload.password)
                preauth.revoked_at, preauth.revoke_reason = now(), "LOGIN_ROTATION"
                raw, _ = await self.issue(db, account)
                result = summary(account)
                audit(db, "LOGIN_SUCCESS", actor=account.principal_id, target=account.account_id)
        if failed:
            raise AuthError("INVALID_CREDENTIALS", 401)
        return result, raw

    async def administrator(
        self, db: AsyncSession, request: Request
    ) -> tuple[Principal, PublisherBoundary]:
        # Serialize administrative mutations BEFORE acquiring any subject row lock.
        # This avoids cross-admin shared/exclusive lock inversions. Reauthenticate
        # under the lock; a revocation while waiting cannot retain authority.
        session, account = await self.load(db, request, csrf=request.method != "GET")
        assert account is not None
        principal = Principal(
            account.account_id,
            account.principal_id,
            session.session_id,
            account.role,
            account.must_change_password,
            account.auth_revision,
            account.grant_revision,
        )
        self.publisher(principal)
        if db.bind is None or db.bind.dialect.name != "postgresql":
            raise AuthError("AUTHORIZATION_UNAVAILABLE", 503)
        await db.execute(text("SET LOCAL lock_timeout = '2s'"))
        await db.execute(text("SELECT pg_advisory_xact_lock(1801001)"))
        session, account = await self.load(
            db, request, csrf=request.method != "GET", shared_lock=True
        )
        assert account is not None
        principal = Principal(
            account.account_id,
            account.principal_id,
            session.session_id,
            account.role,
            account.must_change_password,
            account.auth_revision,
            account.grant_revision,
        )
        return principal, self.publisher(principal)

    async def create_account(
        self,
        db: AsyncSession,
        principal: Principal,
        boundary: PublisherBoundary,
        payload: CreateAccount,
    ) -> AuthAccount:
        if payload.role not in boundary.create_roles:
            raise AuthError("FORBIDDEN")
        if await db.scalar(
            select(AuthAccount.account_id).where(
                AuthAccount.username_normalized == payload.username
            )
        ):
            raise AuthError("REVISION_CONFLICT", 409)
        async with self._hash_slots:
            encoded = await asyncio.to_thread(hash_password, payload.initial_password)
        account = AuthAccount(
            username_normalized=payload.username,
            password_hash=encoded,
            role=payload.role,
            created_at=now(),
            updated_at=now(),
            managed_organization_ids=list(boundary.organization_ids)
            if boundary.simple_admin
            else [],
        )
        db.add(account)
        await db.flush()
        audit(
            db,
            "ACCOUNT_CREATED",
            actor=principal.principal_id,
            target=account.account_id,
            organization=boundary.organization_ids[0] if boundary.simple_admin else None,
            reason=self.operation_reason(boundary, payload.reason),
        )
        return account

    async def managed_account(
        self, db: AsyncSession, boundary: PublisherBoundary, account_id: str
    ) -> AuthAccount:
        if not boundary.simple_admin and account_id not in {
            str(v) for v in boundary.manageable_account_ids
        }:
            raise AuthError("FORBIDDEN")
        result = await db.scalar(
            select(AuthAccount)
            .where(AuthAccount.account_id == account_id, self.account_scope(boundary))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if result is None:
            if not boundary.simple_admin and account_id in {
                str(v) for v in boundary.manageable_account_ids
            }:
                raise AuthError("SAVED_ACCOUNT_NOT_FOUND", 404)
            raise AuthError("FORBIDDEN")
        return result

    async def protect_last_admin(self, db: AsyncSession, account: AuthAccount) -> None:
        # Shared protocol with bootstrap and all role/status/reset mutations.
        if db.bind is None or db.bind.dialect.name != "postgresql":
            raise AuthError("AUTHORIZATION_UNAVAILABLE", 503)
        await db.execute(text("SELECT pg_advisory_xact_lock(1801001)"))
        if (
            account.role == "ADMIN"
            and account.status == "ACTIVE"
            and not account.must_change_password
        ):
            active = await db.scalar(
                select(func.count())
                .select_from(AuthAccount)
                .where(
                    AuthAccount.role == "ADMIN",
                    AuthAccount.status == "ACTIVE",
                    AuthAccount.must_change_password.is_(False),
                )
            )
            if active is None or active <= 1:
                raise AuthError("LAST_ADMIN_PROTECTED", 409)

    async def changed(
        self,
        db: AsyncSession,
        account: AuthAccount,
        principal: Principal,
        action: str,
        reason: str | None = None,
        organization: str | None = None,
    ) -> None:
        before = account.auth_revision
        account.auth_revision += 1
        account.updated_at = now()
        await self.revoke_all(db, account, action)
        audit(
            db,
            action,
            actor=principal.principal_id,
            target=account.account_id,
            before=before,
            after=account.auth_revision,
            reason=reason,
            organization=organization,
        )

    async def create_grant(
        self,
        db: AsyncSession,
        principal: Principal,
        boundary: PublisherBoundary,
        payload: ForecastGrant | QualityGrantRequest,
    ) -> AuthResourceGrant:
        if (
            payload.organization_id not in boundary.organization_ids
            or payload.valid_until <= payload.valid_from
        ):
            raise AuthError("FORBIDDEN")
        registered = any(
            entry.organization_id == payload.organization_id
            and entry.resource_kind == payload.resource_kind
            and entry.capability == payload.capability
            and entry.binding == payload.binding
            for entry in boundary.registered_resources
        )
        if not (registered if boundary.simple_admin else payload in boundary.approved_grants):
            raise AuthError("FORBIDDEN")
        subject = await db.scalar(
            select(AuthAccount)
            .where(
                AuthAccount.principal_id == str(payload.subject_principal_id),
                self.account_scope(boundary),
            )
            .with_for_update()
        )
        if subject is None:
            raise AuthError("FORBIDDEN")
        if subject.grant_revision != payload.expected_grant_revision:
            raise AuthError("REVISION_CONFLICT", 409)
        before = subject.grant_revision
        subject.grant_revision += 1
        subject.updated_at = now()
        grant = AuthResourceGrant(
            principal_id=subject.principal_id,
            resource_kind=payload.resource_kind,
            capability=payload.capability,
            organization_id=payload.organization_id,
            approved_by_principal=principal.principal_id,
            approval_reference=payload.approval_reference,
            reason=payload.reason,
            grant_revision=subject.grant_revision,
            valid_from=payload.valid_from,
            valid_until=payload.valid_until,
            created_at=now(),
            forecast_binding=payload.binding.model_dump(mode="json")
            if payload.resource_kind == "FORECAST"
            else None,
            quality_binding=payload.binding.model_dump(mode="json")
            if payload.resource_kind == "QUALITY"
            else None,
        )
        db.add(grant)
        await db.flush()
        await self.revoke_all(db, subject, "GRANT_CHANGED")
        audit(
            db,
            "GRANT_CREATED",
            actor=principal.principal_id,
            target=subject.account_id,
            grant=grant.grant_id,
            organization=grant.organization_id,
            before=before,
            after=subject.grant_revision,
            reason=self.operation_reason(boundary, payload.reason),
        )
        return grant
