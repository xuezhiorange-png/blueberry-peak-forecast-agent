"""Lane C PIT visibility and revision-winner ORM persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from backend.app.db.base import Base
from backend.app.s2_materialized_dataset.lane_c.schemas import (
    PitVisibilityBlockReason,
    PitVisibilityDecision,
    RevisionWinnerBlockReason,
    RevisionWinnerDecision,
    RevisionWinnerMode,
)

PIT_VISIBILITY_BLOCK_REASON_VALUES = tuple(reason.value for reason in PitVisibilityBlockReason)
REVISION_WINNER_BLOCK_REASON_VALUES = tuple(reason.value for reason in RevisionWinnerBlockReason)
REVISION_WINNER_MODE_VALUES = tuple(mode.value for mode in RevisionWinnerMode)


def _sqlite_bigint() -> Any:
    return BigInteger().with_variant(Integer(), "sqlite")


def _enum_check(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


def _sha_check(column: str, *, nullable: bool = False) -> str:
    expression = column
    for character in "0123456789abcdef":
        expression = f"replace({expression}, '{character}', '')"
    valid = f"length({column}) = 64 AND lower({column}) = {column} AND length({expression}) = 0"
    return f"{column} IS NULL OR ({valid})" if nullable else valid


class S2PitVisibilityDecisionModel(Base):
    __tablename__ = "s2_pit_visibility_decision"

    id: Mapped[int] = mapped_column(_sqlite_bigint(), primary_key=True, autoincrement=True)
    source_row_identity_hash: Mapped[str] = mapped_column(Text, nullable=False)
    source_system: Mapped[str] = mapped_column(Text, nullable=False)
    external_logical_record_id: Mapped[str] = mapped_column(Text, nullable=False)
    external_revision_id: Mapped[str] = mapped_column(Text, nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_source_artifact_identity_hash: Mapped[str] = mapped_column(Text, nullable=False)
    raw_import_batch_identity_hash: Mapped[str] = mapped_column(Text, nullable=False)
    source_recorded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_available_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_revised_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_finalized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    forecast_cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    visibility_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    visibility_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    forecast_cutoff_identity_version: Mapped[str] = mapped_column(Text, nullable=False)
    revision_winner_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    revision_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    eligible: Mapped[bool] = mapped_column(Boolean(), nullable=False)
    blocked: Mapped[bool] = mapped_column(Boolean(), nullable=False)
    block_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("content_sha256", name="uq_s2_pit_visibility_decision_content"),
        CheckConstraint(
            _sha_check("source_row_identity_hash"),
            name="ck_s2_pit_visibility_source_row_identity_hash",
        ),
        CheckConstraint(
            _sha_check("raw_source_artifact_identity_hash"),
            name="ck_s2_pit_visibility_raw_source_artifact_hash",
        ),
        CheckConstraint(
            _sha_check("raw_import_batch_identity_hash"),
            name="ck_s2_pit_visibility_raw_import_batch_hash",
        ),
        CheckConstraint(_sha_check("content_sha256"), name="ck_s2_pit_visibility_content_sha256"),
        CheckConstraint("revision_number >= 1", name="ck_s2_pit_visibility_revision_number"),
        CheckConstraint(
            (
                "block_reason IS NULL OR "
                f"{_enum_check('block_reason', PIT_VISIBILITY_BLOCK_REASON_VALUES)}"
            ),
            name="ck_s2_pit_visibility_block_reason",
        ),
    )


class S2RevisionWinnerDecisionModel(Base):
    __tablename__ = "s2_revision_winner_decision"

    id: Mapped[int] = mapped_column(_sqlite_bigint(), primary_key=True, autoincrement=True)
    source_system: Mapped[str] = mapped_column(Text, nullable=False)
    external_logical_record_id: Mapped[str] = mapped_column(Text, nullable=False)
    forecast_cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    visibility_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    visibility_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    forecast_cutoff_identity_version: Mapped[str] = mapped_column(Text, nullable=False)
    revision_winner_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    revision_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    revision_winner_required: Mapped[bool] = mapped_column(Boolean(), nullable=False)
    winner_manifest_required: Mapped[bool] = mapped_column(Boolean(), nullable=False)
    winner_source_row_identity_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    winner_source_system: Mapped[str | None] = mapped_column(Text, nullable=True)
    winner_external_logical_record_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    winner_external_revision_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    winner_revision_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    winner_raw_source_artifact_identity_hash: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    winner_raw_import_batch_identity_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    blocked: Mapped[bool] = mapped_column(Boolean(), nullable=False)
    no_winner_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    ordered_candidate_identities_json: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("content_sha256", name="uq_s2_revision_winner_decision_content"),
        CheckConstraint(_sha_check("content_sha256"), name="ck_s2_revision_winner_content_sha256"),
        CheckConstraint(
            _sha_check("winner_source_row_identity_hash", nullable=True),
            name="ck_s2_revision_winner_winner_identity_hash",
        ),
        CheckConstraint(
            _sha_check("winner_raw_source_artifact_identity_hash", nullable=True),
            name="ck_s2_revision_winner_winner_artifact_hash",
        ),
        CheckConstraint(
            _sha_check("winner_raw_import_batch_identity_hash", nullable=True),
            name="ck_s2_revision_winner_winner_batch_hash",
        ),
        CheckConstraint(
            _enum_check("mode", REVISION_WINNER_MODE_VALUES),
            name="ck_s2_revision_winner_mode",
        ),
        CheckConstraint(
            (
                "no_winner_reason IS NULL OR "
                f"{_enum_check('no_winner_reason', REVISION_WINNER_BLOCK_REASON_VALUES)}"
            ),
            name="ck_s2_revision_winner_no_winner_reason",
        ),
        CheckConstraint(
            (
                "(winner_source_row_identity_hash IS NULL "
                "AND winner_source_system IS NULL "
                "AND winner_external_logical_record_id IS NULL "
                "AND winner_external_revision_id IS NULL "
                "AND winner_revision_number IS NULL "
                "AND winner_raw_source_artifact_identity_hash IS NULL "
                "AND winner_raw_import_batch_identity_hash IS NULL) "
                "OR (winner_source_row_identity_hash IS NOT NULL "
                "AND winner_source_system IS NOT NULL "
                "AND winner_external_logical_record_id IS NOT NULL "
                "AND winner_external_revision_id IS NOT NULL "
                "AND winner_revision_number IS NOT NULL "
                "AND winner_raw_source_artifact_identity_hash IS NOT NULL "
                "AND winner_raw_import_batch_identity_hash IS NOT NULL "
                "AND winner_revision_number >= 1)"
            ),
            name="ck_s2_revision_winner_winner_identity_presence",
        ),
    )


@dataclass
class LaneCPersistenceStore:
    """Append-only in-memory store for deterministic replay during Draft R1."""

    pit_visibility_decisions: list[PitVisibilityDecision] = field(default_factory=list)
    revision_winner_decisions: list[RevisionWinnerDecision] = field(default_factory=list)

    def record_pit_visibility(self, decision: PitVisibilityDecision) -> None:
        self.pit_visibility_decisions.append(decision)

    def record_revision_winner(self, decision: RevisionWinnerDecision) -> None:
        self.revision_winner_decisions.append(decision)


def persist_pit_visibility_decision(
    session: Session,
    decision: PitVisibilityDecision,
) -> S2PitVisibilityDecisionModel:
    existing = (
        session.query(S2PitVisibilityDecisionModel)
        .filter_by(content_sha256=decision.content_sha256)
        .one_or_none()
    )
    if existing is not None:
        return existing

    identity = decision.source_row_identity
    cutoff = decision.cutoff_context
    timestamps = decision.timestamps
    row = S2PitVisibilityDecisionModel(
        source_row_identity_hash=identity.source_row_identity_hash,
        source_system=identity.source_system,
        external_logical_record_id=identity.external_logical_record_id,
        external_revision_id=identity.external_revision_id,
        revision_number=identity.revision_number,
        raw_source_artifact_identity_hash=identity.raw_source_artifact_identity_hash,
        raw_import_batch_identity_hash=identity.raw_import_batch_identity_hash,
        source_recorded_at=timestamps.source_recorded_at,
        source_available_at=timestamps.source_available_at,
        source_revised_at=timestamps.source_revised_at,
        source_finalized_at=timestamps.source_finalized_at,
        source_cancelled_at=timestamps.source_cancelled_at,
        forecast_cutoff_at=cutoff.forecast_cutoff_at,
        visibility_policy_version=cutoff.visibility_policy_version,
        visibility_schema_version=cutoff.visibility_schema_version,
        forecast_cutoff_identity_version=cutoff.forecast_cutoff_identity_version,
        revision_winner_policy_version=cutoff.revision_winner_policy_version,
        revision_schema_version=cutoff.revision_schema_version,
        eligible=decision.eligible,
        blocked=decision.blocked,
        block_reason=decision.block_reason.value if decision.block_reason is not None else None,
        content_sha256=decision.content_sha256,
        created_at=datetime.now(UTC),
    )
    session.add(row)
    session.flush()
    return row


def persist_revision_winner_decision(
    session: Session,
    decision: RevisionWinnerDecision,
) -> S2RevisionWinnerDecisionModel:
    existing = (
        session.query(S2RevisionWinnerDecisionModel)
        .filter_by(content_sha256=decision.content_sha256)
        .one_or_none()
    )
    if existing is not None:
        return existing

    cutoff = decision.cutoff_context
    winner = decision.winner_source_row_identity
    row = S2RevisionWinnerDecisionModel(
        source_system=decision.logical_record_key.source_system,
        external_logical_record_id=decision.logical_record_key.external_logical_record_id,
        forecast_cutoff_at=cutoff.forecast_cutoff_at,
        visibility_policy_version=cutoff.visibility_policy_version,
        visibility_schema_version=cutoff.visibility_schema_version,
        forecast_cutoff_identity_version=cutoff.forecast_cutoff_identity_version,
        revision_winner_policy_version=cutoff.revision_winner_policy_version,
        revision_schema_version=cutoff.revision_schema_version,
        mode=decision.mode.value,
        revision_winner_required=decision.revision_winner_required,
        winner_manifest_required=decision.winner_manifest_required,
        winner_source_row_identity_hash=(
            winner.source_row_identity_hash if winner is not None else None
        ),
        winner_source_system=winner.source_system if winner is not None else None,
        winner_external_logical_record_id=(
            winner.external_logical_record_id if winner is not None else None
        ),
        winner_external_revision_id=winner.external_revision_id if winner is not None else None,
        winner_revision_number=winner.revision_number if winner is not None else None,
        winner_raw_source_artifact_identity_hash=(
            winner.raw_source_artifact_identity_hash if winner is not None else None
        ),
        winner_raw_import_batch_identity_hash=(
            winner.raw_import_batch_identity_hash if winner is not None else None
        ),
        blocked=decision.blocked,
        no_winner_reason=(
            decision.no_winner_reason.value if decision.no_winner_reason is not None else None
        ),
        ordered_candidate_identities_json=json.dumps(list(decision.ordered_candidate_identities)),
        content_sha256=decision.content_sha256,
        created_at=datetime.now(UTC),
    )
    session.add(row)
    session.flush()
    return row


__all__ = [
    "LaneCPersistenceStore",
    "S2PitVisibilityDecisionModel",
    "S2RevisionWinnerDecisionModel",
    "persist_pit_visibility_decision",
    "persist_revision_winner_decision",
]
