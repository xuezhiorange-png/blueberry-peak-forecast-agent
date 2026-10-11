"""Additive authentication metadata; no forecasting or actual-data columns."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from backend.app.db.base import Base


class UTCDateTime(TypeDecorator[datetime]):
    """Reject naive writes; PostgreSQL timestamptz and SQLite UTC round trips."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        del dialect
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Timezone-aware datetime required")
        return value.astimezone(UTC) if value else None

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        del dialect
        if value is not None:
            return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return None


DOCUMENT = JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")


def identifier() -> str:
    return str(uuid4())


class AuthAccount(Base):
    __tablename__ = "auth_account"
    __table_args__ = (
        CheckConstraint("role IN ('ADMIN','BUSINESS_USER')", name="ck_auth_role"),
        CheckConstraint("status IN ('ACTIVE','DISABLED')", name="ck_auth_status"),
        CheckConstraint("auth_revision > 0 AND grant_revision > 0", name="ck_auth_revision"),
    )
    account_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    principal_id: Mapped[str] = mapped_column(String(36), unique=True, default=identifier)
    username_normalized: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(10), default="ACTIVE")
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    auth_revision: Mapped[int] = mapped_column(BigInteger, default=1)
    grant_revision: Mapped[int] = mapped_column(BigInteger, default=1)
    managed_organization_ids: Mapped[list[str]] = mapped_column(DOCUMENT, default=list)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime())
    disabled_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class AuthSession(Base):
    __tablename__ = "auth_session"
    __table_args__ = (
        CheckConstraint(
            "(kind='PREAUTH' AND account_id IS NULL AND auth_revision IS NULL "
            "AND grant_revision IS NULL) OR (kind='END_USER' AND account_id IS NOT NULL "
            "AND auth_revision > 0 AND grant_revision > 0)",
            name="ck_auth_session_kind",
        ),
        CheckConstraint("absolute_expires_at > issued_at", name="ck_auth_session_expiry"),
        Index("ix_auth_session_account", "account_id", "revoked_at"),
    )
    session_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    token_digest: Mapped[str] = mapped_column(String(64), unique=True)
    kind: Mapped[str] = mapped_column(String(10))
    account_id: Mapped[str | None] = mapped_column(
        ForeignKey("auth_account.account_id", ondelete="RESTRICT")
    )
    csrf_token_digest: Mapped[str] = mapped_column(String(64))
    issued_at: Mapped[datetime] = mapped_column(UTCDateTime())
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime())
    idle_expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    absolute_expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    auth_revision: Mapped[int | None] = mapped_column(BigInteger)
    grant_revision: Mapped[int | None] = mapped_column(BigInteger)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    revoke_reason: Mapped[str | None] = mapped_column(String(64))


class AuthResourceGrant(Base):
    __tablename__ = "auth_resource_grant"
    __table_args__ = (
        CheckConstraint("valid_until > valid_from", name="ck_auth_grant_expiry"),
        CheckConstraint("grant_revision > 0", name="ck_auth_grant_revision"),
        CheckConstraint(
            "(resource_kind='FORECAST' AND capability='may_read_forecast' "
            "AND forecast_binding IS NOT NULL AND quality_binding IS NULL) OR "
            "(resource_kind='QUALITY' AND capability='may_read_quality' "
            "AND quality_binding IS NOT NULL AND forecast_binding IS NULL)",
            name="ck_auth_grant_binding",
        ),
        Index("ix_auth_grant_principal", "principal_id", "capability", "revoked_at"),
    )
    grant_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    principal_id: Mapped[str] = mapped_column(
        ForeignKey("auth_account.principal_id", ondelete="RESTRICT")
    )
    resource_kind: Mapped[str] = mapped_column(String(10))
    capability: Mapped[str] = mapped_column(String(40))
    organization_id: Mapped[str] = mapped_column(String(200))
    approved_by_principal: Mapped[str] = mapped_column(String(36))
    approval_reference: Mapped[str] = mapped_column(String(200))
    reason: Mapped[str] = mapped_column(String(500))
    grant_revision: Mapped[int] = mapped_column(BigInteger)
    forecast_binding: Mapped[dict[str, Any] | None] = mapped_column(DOCUMENT, nullable=True)
    quality_binding: Mapped[dict[str, Any] | None] = mapped_column(DOCUMENT, nullable=True)
    valid_from: Mapped[datetime] = mapped_column(UTCDateTime())
    valid_until: Mapped[datetime] = mapped_column(UTCDateTime())
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())


class AuthAuditEvent(Base):
    __tablename__ = "auth_audit_event"
    __table_args__ = (
        Index("ix_auth_audit_bucket", "login_bucket_digest", "occurred_at"),
        Index("ix_auth_audit_org_time", "organization_id", "occurred_at"),
    )
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime())
    actor_principal_id: Mapped[str | None] = mapped_column(String(36))
    target_account_id: Mapped[str | None] = mapped_column(String(36))
    target_grant_id: Mapped[str | None] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(64))
    result_code: Mapped[str] = mapped_column(String(64))
    revision_before: Mapped[int | None] = mapped_column(BigInteger)
    revision_after: Mapped[int | None] = mapped_column(BigInteger)
    correlation_id: Mapped[str] = mapped_column(String(36), default=identifier)
    organization_id: Mapped[str | None] = mapped_column(String(200))
    login_bucket_digest: Mapped[str | None] = mapped_column(String(64))
    reason_code: Mapped[str] = mapped_column(String(64))
