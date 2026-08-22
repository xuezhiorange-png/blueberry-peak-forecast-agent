"""Lane C PIT visibility and revision-winner ORM persistence."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import sqlalchemy as sa
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
from backend.app.s2_materialized_dataset.lane_c.revision_winner import (
    idfl_null_timestamps,
    resolve_idfl_revision_winner_for_source_row,
)
from backend.app.s2_materialized_dataset.lane_c.schemas import (
    PitVisibilityBlockReason,
    PitVisibilityDecision,
    RevisionWinnerBlockReason,
    RevisionWinnerDecision,
    RevisionWinnerMode,
    SourceRowIdentity,
)

logger = logging.getLogger(__name__)

PIT_CUTOFF_NOT_APPLICABLE_FOR_IDFL_NO_FABRICATION = (
    "PIT_CUTOFF_NOT_APPLICABLE_FOR_IDFL_NO_FABRICATION"
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
    if cutoff is None:
        raise ValueError("persist_revision_winner_decision requires replay cutoff context")
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


@dataclass(frozen=True)
class IdflLabelSidePitStatus:
    pit_rows_persisted: int
    pit_eligible: int
    pit_status: str
    e4_blocked_reason: str | None


@dataclass(frozen=True)
class Source002E4Result:
    ingest_replay_row_count: int
    canonical_non_excluded_row_count: int
    kg_sum_equal: bool
    winner_mode: str
    winner_rows_resolved: int
    winner_rows_sql_persisted: int
    winner_blocked: int
    pit_rows_persisted: int
    pit_eligible: int
    pit_status: str
    e4_status: str
    e4_blocked_reason: str | None
    revision_winner_content_hashes: tuple[str, ...]
    replay_identity_match: bool
    replay_content_match: bool


def resolve_idfl_label_side_pit_status() -> IdflLabelSidePitStatus:
    return IdflLabelSidePitStatus(
        pit_rows_persisted=0,
        pit_eligible=0,
        pit_status="NOT_APPLICABLE_NOT_PERSISTED",
        e4_blocked_reason=PIT_CUTOFF_NOT_APPLICABLE_FOR_IDFL_NO_FABRICATION,
    )


def _column_is_non_nullable(session: Session, *, table_name: str, column_name: str) -> bool:
    bind = session.get_bind()
    inspector = sa.inspect(bind)
    column = next(item for item in inspector.get_columns(table_name) if item["name"] == column_name)
    return column.get("nullable", True) is False


def pit_sql_persist_blocked_without_forecast_cutoff(session: Session) -> bool:
    return _column_is_non_nullable(
        session,
        table_name="s2_pit_visibility_decision",
        column_name="forecast_cutoff_at",
    )


def revision_winner_sql_persist_blocked_without_forecast_cutoff(session: Session) -> bool:
    return _column_is_non_nullable(
        session,
        table_name="s2_revision_winner_decision",
        column_name="forecast_cutoff_at",
    )


def lane_c_source_row_identity_from_lane_a(row: Any) -> SourceRowIdentity:
    return SourceRowIdentity(
        source_row_identity_hash=row.source_row_identity_hash,
        source_system=row.source_system,
        external_logical_record_id=row.external_logical_record_id,
        external_revision_id=row.external_revision_id,
        revision_number=row.revision_number,
        raw_source_artifact_identity_hash=row.raw_source_artifact_identity_hash,
        raw_import_batch_identity_hash=row.raw_import_batch_identity_hash,
    )


def persist_idfl_revision_winner_decision(
    session: Session,
    decision: RevisionWinnerDecision,
) -> S2RevisionWinnerDecisionModel | None:
    if decision.mode is not RevisionWinnerMode.IDFL_LABEL_SIDE:
        raise ValueError("persist_idfl_revision_winner_decision requires IDFL_LABEL_SIDE mode")
    if revision_winner_sql_persist_blocked_without_forecast_cutoff(session):
        return None
    if decision.cutoff_context is None:
        return None
    return persist_revision_winner_decision(session, decision)


def count_revision_winner_sql_rows(session: Session) -> int:
    return int(
        session.scalar(
            sa.select(sa.func.count()).select_from(S2RevisionWinnerDecisionModel)
        )
        or 0
    )


def _emit_source_002_e4_report(result: Source002E4Result) -> None:
    report = (
        "SOURCE_002_E4_REPORT "
        f"e2_replay={result.ingest_replay_row_count} "
        f"e3_grains={result.canonical_non_excluded_row_count} "
        f"e3_kg_equal={'true' if result.kg_sum_equal else 'false'} "
        f"winner_mode={result.winner_mode} "
        f"winner_rows_resolved={result.winner_rows_resolved} "
        f"winner_rows_sql_persisted={result.winner_rows_sql_persisted} "
        f"winner_blocked={result.winner_blocked} "
        f"pit_rows_persisted={result.pit_rows_persisted} "
        f"pit_eligible={result.pit_eligible} "
        f"pit_status={result.pit_status} "
        f"e4_status={result.e4_status}"
    )
    if result.e4_blocked_reason is not None:
        report = f"{report} e4_blocked_reason={result.e4_blocked_reason}"
    report = f"{report} replay_content_match={'true' if result.replay_content_match else 'false'}"
    logger.info(report)
    print(report, flush=True)


def controlled_persist_source_002_idfl_from_environment(
    session: Session,
    *,
    search_roots: tuple[Path, ...] = (),
    persist: bool = True,
    previous_result: Source002E4Result | None = None,
) -> Source002E4Result:
    from sqlalchemy import select

    from backend.app.s2_materialized_dataset.lane_a.persistence import S2SourceRowLineageModel
    from backend.app.s2_materialized_dataset.lane_b.cleaning import (
        controlled_clean_source_002_from_environment,
    )

    e3_result = controlled_clean_source_002_from_environment(
        session,
        search_roots=search_roots,
        persist=persist,
    )
    pit_status = resolve_idfl_label_side_pit_status()
    if pit_status.e4_blocked_reason is not None:
        print(f"E4_BLOCKED_REASON={pit_status.e4_blocked_reason}", flush=True)

    batch_hashes = e3_result.cleaning.version.raw_import_batch_identity_hashes
    if len(batch_hashes) != 1:
        raise ValueError(
            "SOURCE_002 E4 IDFL requires exactly one raw import batch identity hash"
        )
    batch_hash = batch_hashes[0]
    lane_a_rows = session.scalars(
        select(S2SourceRowLineageModel)
        .where(S2SourceRowLineageModel.raw_import_batch_identity_hash == batch_hash)
        .order_by(S2SourceRowLineageModel.source_row_identity_hash)
    ).all()
    lane_a_by_identity_hash = {
        row.source_row_identity_hash: row for row in lane_a_rows
    }

    content_hashes: list[str] = []
    winner_blocked = 0
    winner_rows_resolved = 0

    for identity_hash in e3_result.cleaning.version.source_row_identity_hashes:
        lane_a_row = lane_a_by_identity_hash.get(identity_hash)
        if lane_a_row is None:
            raise ValueError(f"Lane A source row missing for identity hash {identity_hash}")
        lane_c_identity = lane_c_source_row_identity_from_lane_a(lane_a_row)
        decision = resolve_idfl_revision_winner_for_source_row(
            source_row_identity=lane_c_identity,
        )
        winner_rows_resolved += 1
        if decision.blocked:
            winner_blocked += 1
        content_hashes.append(decision.content_sha256)
        if persist:
            persist_idfl_revision_winner_decision(session, decision)

    winner_rows_sql_persisted = (
        count_revision_winner_sql_rows(session) if persist else 0
    )

    content_hashes_tuple = tuple(content_hashes)
    replay_identity_match = (
        True
        if previous_result is None
        else previous_result.revision_winner_content_hashes == content_hashes_tuple
    )
    replay_content_match = replay_identity_match
    kg_sum_equal = (
        e3_result.kg_sum_source_rows is not None
        and e3_result.kg_sum_cleaned_grains is not None
        and e3_result.kg_sum_source_rows == e3_result.kg_sum_cleaned_grains
    )
    result = Source002E4Result(
        ingest_replay_row_count=e3_result.ingest_replay_row_count,
        canonical_non_excluded_row_count=e3_result.canonical_source_row_count,
        kg_sum_equal=kg_sum_equal,
        winner_mode=RevisionWinnerMode.IDFL_LABEL_SIDE.value,
        winner_rows_resolved=winner_rows_resolved,
        winner_rows_sql_persisted=winner_rows_sql_persisted,
        winner_blocked=winner_blocked,
        pit_rows_persisted=pit_status.pit_rows_persisted,
        pit_eligible=pit_status.pit_eligible,
        pit_status=pit_status.pit_status,
        e4_status="RESOLVED_NOT_SQL_PERSISTED",
        e4_blocked_reason=pit_status.e4_blocked_reason,
        revision_winner_content_hashes=content_hashes_tuple,
        replay_identity_match=replay_identity_match,
        replay_content_match=replay_content_match,
    )
    _emit_source_002_e4_report(result)
    return result


__all__ = [
    "IdflLabelSidePitStatus",
    "LaneCPersistenceStore",
    "PIT_CUTOFF_NOT_APPLICABLE_FOR_IDFL_NO_FABRICATION",
    "S2PitVisibilityDecisionModel",
    "S2RevisionWinnerDecisionModel",
    "Source002E4Result",
    "controlled_persist_source_002_idfl_from_environment",
    "count_revision_winner_sql_rows",
    "idfl_null_timestamps",
    "lane_c_source_row_identity_from_lane_a",
    "persist_idfl_revision_winner_decision",
    "persist_pit_visibility_decision",
    "persist_revision_winner_decision",
    "pit_sql_persist_blocked_without_forecast_cutoff",
    "resolve_idfl_label_side_pit_status",
    "revision_winner_sql_persist_blocked_without_forecast_cutoff",
]
