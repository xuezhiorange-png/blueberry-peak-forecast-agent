"""SQLAlchemy models for the durable S4 validation-budget authority."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base

_BIGINT_VARIANT = BigInteger().with_variant(Integer(), "sqlite")
_JSON_VARIANT = JSON().with_variant(JSONB(), "postgresql")
_GENESIS = "0" * 64


def _sha256_checks(column: str, name: str) -> tuple[CheckConstraint, CheckConstraint]:
    return (
        CheckConstraint(
            f"length({column}) = 64 AND lower({column}) = {column} "
            f"AND {column} NOT GLOB '*[^0-9a-f]*'",
            name=name,
        ).ddl_if(dialect="sqlite"),
        CheckConstraint(
            f"{column} ~ '^[0-9a-f]{{64}}$'",
            name=name,
        ).ddl_if(dialect="postgresql"),
    )


class S4ValidationBudgetAuthority(Base):
    """Monotonic accepted-head row for the S4 validation event ledger."""

    __tablename__ = "s4_validation_budget_authority"
    __table_args__ = (
        CheckConstraint(
            "authority_version >= 0",
            name="ck_s4_validation_budget_authority_version_nonnegative",
        ),
        CheckConstraint(
            "accepted_event_count >= 0",
            name="ck_s4_validation_budget_authority_event_count_nonnegative",
        ),
        CheckConstraint(
            "accepted_started_count >= 0",
            name="ck_s4_validation_budget_authority_started_count_nonnegative",
        ),
        CheckConstraint(
            "accepted_started_count <= accepted_event_count",
            name="ck_s4_validation_budget_authority_started_le_events",
        ),
        CheckConstraint(
            "accepted_last_global_evaluation_ordinal >= 0",
            name="ck_s4_validation_budget_authority_last_ordinal_nonnegative",
        ),
        CheckConstraint(
            "legacy_reconciled_validation_debit = 4",
            name="ck_s4_validation_budget_authority_legacy_debit",
        ),
        CheckConstraint(
            "legacy_reconciled_validation_debit + accepted_started_count <= 32",
            name="ck_s4_validation_budget_authority_effective_budget",
        ),
        *_sha256_checks(
            "accepted_head_event_hash",
            "ck_s4_validation_budget_authority_head_hash",
        ),
    )

    authority_key: Mapped[str] = mapped_column(Text, primary_key=True)
    authority_version: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    accepted_event_count: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    accepted_started_count: Mapped[int] = mapped_column(_BIGINT_VARIANT, nullable=False)
    accepted_head_event_hash: Mapped[str] = mapped_column(Text, nullable=False)
    accepted_last_global_evaluation_ordinal: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        nullable=False,
    )
    legacy_reconciled_validation_debit: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class S4ValidationEvent(Base):
    """Immutable canonical event row with typed projections for constraints."""

    __tablename__ = "s4_validation_event"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('EVALUATION_STARTED', 'EVALUATION_TERMINAL')",
            name="ck_s4_validation_event_type",
        ),
        CheckConstraint(
            "event_sequence > 0",
            name="ck_s4_validation_event_sequence_positive",
        ),
        CheckConstraint(
            "(event_type = 'EVALUATION_STARTED' AND "
            "candidate_run_ordinal >= 1 AND candidate_run_ordinal <= 4 AND "
            "global_evaluation_ordinal >= 1 AND invocation_type IS NOT NULL AND "
            "counted_toward_budget = true AND "
            "budget_count_reason = 'STARTED_INVOCATION') OR "
            "(event_type = 'EVALUATION_TERMINAL' AND "
            "candidate_run_ordinal IS NULL AND "
            "global_evaluation_ordinal IS NULL AND "
            "invocation_type IS NULL AND "
            "counted_toward_budget = false AND "
            "budget_count_reason IS NULL)",
            name="ck_s4_validation_event_type_specific_fields",
        ),
        *_sha256_checks("previous_event_hash", "ck_s4_validation_event_previous_hash"),
        *_sha256_checks("event_hash", "ck_s4_validation_event_hash"),
        UniqueConstraint(
            "authority_key",
            "evaluation_id",
            "event_type",
            name="uq_s4_validation_event_evaluation_type",
        ),
        UniqueConstraint(
            "authority_key",
            "event_hash",
            name="uq_s4_validation_event_hash",
        ),
        Index(
            "uq_s4_validation_event_started_global_ordinal",
            "authority_key",
            "global_evaluation_ordinal",
            unique=True,
            postgresql_where=text("event_type = 'EVALUATION_STARTED'"),
            sqlite_where=text("event_type = 'EVALUATION_STARTED'"),
        ),
        Index(
            "uq_s4_validation_event_started_candidate_run",
            "authority_key",
            "candidate_id",
            "candidate_run_ordinal",
            unique=True,
            postgresql_where=text("event_type = 'EVALUATION_STARTED'"),
            sqlite_where=text("event_type = 'EVALUATION_STARTED'"),
        ),
    )

    authority_key: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "s4_validation_budget_authority.authority_key",
            name="fk_s4_validation_event_authority",
            ondelete="RESTRICT",
        ),
        primary_key=True,
    )
    event_sequence: Mapped[int] = mapped_column(_BIGINT_VARIANT, primary_key=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    evaluation_id: Mapped[str] = mapped_column(Text, nullable=False)
    candidate_id: Mapped[str] = mapped_column(Text, nullable=False)
    candidate_run_ordinal: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    global_evaluation_ordinal: Mapped[int | None] = mapped_column(
        _BIGINT_VARIANT,
        nullable=True,
    )
    invocation_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    counted_toward_budget: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    budget_count_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    execution_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    metric_result_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_payload: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)
    previous_event_hash: Mapped[str] = mapped_column(Text, nullable=False)
    event_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


__all__ = ["S4ValidationBudgetAuthority", "S4ValidationEvent"]
