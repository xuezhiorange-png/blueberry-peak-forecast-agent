"""S1 commit-manifest ORM model.

Frozen contract:
- Execution model: SYNCHRONOUS_SINGLE_TRANSACTION
- No commit attempt ledger / lease / heartbeat / stale reclaim / fencing /
  generation / background worker
- One table: actual_harvest_commit_manifest
- 19 fields, all NOT NULL, all 64-char hex TEXT for hash fields
- UNIQUE(batch_id), UNIQUE(validation_run_id), UNIQUE(commit_manifest_hash)
- PostgreSQL immutability trigger rejects UPDATE and DELETE
- commit_policy_version is a fixed string constant
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.actual_harvest_import.enums import ActualHarvestImportBatchStatus
from backend.app.db.base import Base

COMMIT_POLICY_VERSION = "actual-harvest-commit-policy-v1"


def _sqlite_bigint() -> Any:
    return BigInteger().with_variant(Integer(), "sqlite")


def _enum_check(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


def _sha_check(column: str, *, nullable: bool = False) -> str:
    expression = column
    for character in "0123456789abcdef":
        expression = f"replace({expression}, '{character}', '')"
    valid = f"length({column}) = 64 AND lower({column}) = {column} AND length({expression}) = 0"
    return f"{column} IS NULL OR ({valid})" if nullable else valid


class ActualHarvestCommitManifestModel(Base):
    """Immutable, append-only atomic commit manifest.

    Frozen S1 contract. The lifecycle of one row:

    1. batch is VALIDATED, request validation_run_instance_identity_hash matches
       the current VALIDATED validation run
    2. caller-owned transaction inserts one row, sets batch.status=COMMITTED,
       batch.committed_record_count=record_count, batch.committed_at_or_null=now
    3. caller commits; any prior session-level error rolls back both the row
       and the batch update
    4. PostgreSQL trigger ``trg_actual_harvest_commit_manifest_immutable``
       rejects UPDATE and DELETE; SQLite triggers do the same
    5. The row is the canonical proof that the batch became COMMITTED. Its
       ``commit_manifest_hash`` is deterministic from canonical JSON of
       policy_version + import_id + validation_run_instance_identity_hash +
       all 9 evidence hashes + ordered_records payload. It does NOT include
       committed_at or committed_by_identity (those are provenance, not
       identity).
    """

    __tablename__ = "actual_harvest_commit_manifest"

    id: Mapped[int] = mapped_column(_sqlite_bigint(), primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        _sqlite_bigint(),
        ForeignKey(
            "actual_harvest_import_batch.id",
            name="fk_actual_harvest_commit_manifest_batch",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    validation_run_id: Mapped[int] = mapped_column(
        _sqlite_bigint(),
        ForeignKey(
            "actual_harvest_validation_run.id",
            name="fk_actual_harvest_commit_manifest_validation_run",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    commit_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    validation_run_instance_identity_hash: Mapped[str] = mapped_column(Text, nullable=False)
    commit_manifest_hash: Mapped[str] = mapped_column(Text, nullable=False)
    seal_manifest_hash: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_batch_hash: Mapped[str] = mapped_column(Text, nullable=False)
    record_manifest_hash: Mapped[str] = mapped_column(Text, nullable=False)
    validation_result_hash: Mapped[str] = mapped_column(Text, nullable=False)
    mapping_snapshot_hash: Mapped[str] = mapped_column(Text, nullable=False)
    resolved_identity_snapshot_hash: Mapped[str] = mapped_column(Text, nullable=False)
    lineage_graph_hash: Mapped[str] = mapped_column(Text, nullable=False)
    committed_lineage_basis_hash: Mapped[str] = mapped_column(Text, nullable=False)
    registry_content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    source_semantics_attestation_hash: Mapped[str] = mapped_column(Text, nullable=False)
    committed_record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    committed_by_identity: Mapped[str] = mapped_column(Text, nullable=False)
    committed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("batch_id", name="uq_actual_harvest_commit_manifest_batch"),
        UniqueConstraint(
            "validation_run_id",
            name="uq_actual_harvest_commit_manifest_validation_run",
        ),
        UniqueConstraint(
            "commit_manifest_hash",
            name="uq_actual_harvest_commit_manifest_hash",
        ),
        CheckConstraint(
            "committed_record_count >= 0",
            name="ck_actual_harvest_commit_manifest_count_nonneg",
        ),
        CheckConstraint(
            _sha_check("validation_run_instance_identity_hash"),
            name="ck_actual_harvest_commit_manifest_instance_hash",
        ),
        CheckConstraint(
            _sha_check("commit_manifest_hash"),
            name="ck_actual_harvest_commit_manifest_hash",
        ),
        CheckConstraint(
            _sha_check("seal_manifest_hash"),
            name="ck_actual_harvest_commit_manifest_seal_hash",
        ),
        CheckConstraint(
            _sha_check("canonical_batch_hash"),
            name="ck_actual_harvest_commit_manifest_canonical_batch_hash",
        ),
        CheckConstraint(
            _sha_check("record_manifest_hash"),
            name="ck_actual_harvest_commit_manifest_record_manifest_hash",
        ),
        CheckConstraint(
            _sha_check("validation_result_hash"),
            name="ck_actual_harvest_commit_manifest_validation_result_hash",
        ),
        CheckConstraint(
            _sha_check("mapping_snapshot_hash"),
            name="ck_actual_harvest_commit_manifest_mapping_snapshot_hash",
        ),
        CheckConstraint(
            _sha_check("resolved_identity_snapshot_hash"),
            name="ck_actual_harvest_commit_manifest_resolved_identity_hash",
        ),
        CheckConstraint(
            _sha_check("lineage_graph_hash"),
            name="ck_actual_harvest_commit_manifest_lineage_graph_hash",
        ),
        CheckConstraint(
            _sha_check("committed_lineage_basis_hash"),
            name="ck_actual_harvest_commit_manifest_lineage_basis_hash",
        ),
        CheckConstraint(
            _sha_check("registry_content_hash"),
            name="ck_actual_harvest_commit_manifest_registry_hash",
        ),
        CheckConstraint(
            _sha_check("source_semantics_attestation_hash"),
            name="ck_actual_harvest_commit_manifest_attestation_hash",
        ),
    )


__all__ = [
    "ActualHarvestCommitManifestModel",
    "COMMIT_POLICY_VERSION",
]


# Re-export the status enum value used by the commit service
COMMITTED_STATUS = ActualHarvestImportBatchStatus.COMMITTED.value
