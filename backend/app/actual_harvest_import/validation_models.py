from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


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


REGISTRY_STATUS_VALUES = ("DRAFT", "SEALED")
MAPPING_TARGET_VALUES = ("SEASON", "FARM", "SUBFARM", "VARIETY")
VALIDATION_STATUS_VALUES = (
    "VALIDATING",
    "VALIDATED",
    "VALIDATION_FAILED",
)
ATTEMPT_STATUS_VALUES = ("ACTIVE", "ABANDONED", "STALE", "COMPLETED")
EVIDENCE_ORIGIN_VALUES = ("CURRENT_BATCH_REVISION", "COMMITTED_HISTORY_REVISION")


class ActualHarvestMappingPolicyRegistryModel(Base):
    __tablename__ = "actual_harvest_mapping_policy_registry"

    id: Mapped[int] = mapped_column(_sqlite_bigint(), primary_key=True, autoincrement=True)
    registry_version: Mapped[str] = mapped_column(Text, nullable=False)
    source_system: Mapped[str] = mapped_column(Text, nullable=False)
    mapping_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    entry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    registry_content_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    sealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("registry_version", name="uq_actual_harvest_mapping_registry_version"),
        UniqueConstraint(
            "mapping_policy_version",
            name="uq_actual_harvest_mapping_policy_version",
        ),
        CheckConstraint(
            _enum_check("status", REGISTRY_STATUS_VALUES),
            name="ck_actual_harvest_mapping_registry_status",
        ),
        CheckConstraint("entry_count >= 0", name="ck_actual_harvest_mapping_entry_count"),
        CheckConstraint(
            _sha_check("registry_content_hash", nullable=True),
            name="ck_actual_harvest_mapping_registry_hash",
        ),
    )


class ActualHarvestMappingRegistryEntryModel(Base):
    __tablename__ = "actual_harvest_mapping_registry_entry"

    id: Mapped[int] = mapped_column(_sqlite_bigint(), primary_key=True, autoincrement=True)
    registry_id: Mapped[int] = mapped_column(
        _sqlite_bigint(),
        ForeignKey(
            "actual_harvest_mapping_policy_registry.id",
            name="fk_actual_harvest_mapping_entry_registry",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    source_field: Mapped[str] = mapped_column(Text, nullable=False)
    source_code: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_business_key: Mapped[str] = mapped_column(Text, nullable=False)
    target_parent_business_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    farm_timezone: Mapped[str | None] = mapped_column(Text, nullable=True)
    entry_hash: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "registry_id",
            "source_field",
            "source_code",
            name="uq_actual_harvest_mapping_entry_source",
        ),
        CheckConstraint(
            _enum_check("target_type", MAPPING_TARGET_VALUES),
            name="ck_actual_harvest_mapping_entry_target_type",
        ),
        CheckConstraint(_sha_check("entry_hash"), name="ck_actual_harvest_mapping_entry_hash"),
        Index(
            "ix_actual_harvest_mapping_entry_lookup",
            "registry_id",
            "source_field",
            "source_code",
        ),
    )


class ActualHarvestMappingSnapshotModel(Base):
    __tablename__ = "actual_harvest_mapping_snapshot"

    id: Mapped[int] = mapped_column(_sqlite_bigint(), primary_key=True, autoincrement=True)
    validation_run_id: Mapped[int] = mapped_column(
        _sqlite_bigint(),
        ForeignKey(
            "actual_harvest_validation_run.id",
            name="fk_actual_harvest_mapping_snapshot_run",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    registry_version: Mapped[str] = mapped_column(Text, nullable=False)
    mapping_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    season_resolver_version: Mapped[str] = mapped_column(Text, nullable=False)
    registry_content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    mapping_snapshot_hash: Mapped[str] = mapped_column(Text, nullable=False)
    resolved_identity_snapshot_hash: Mapped[str] = mapped_column(Text, nullable=False)
    entry_count: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_payload: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "validation_run_id",
            name="uq_actual_harvest_mapping_snapshot_run",
        ),
        CheckConstraint(
            _sha_check("registry_content_hash"), name="ck_actual_harvest_snapshot_registry_hash"
        ),
        CheckConstraint(
            _sha_check("mapping_snapshot_hash"), name="ck_actual_harvest_snapshot_hash"
        ),
        CheckConstraint(
            _sha_check("resolved_identity_snapshot_hash"),
            name="ck_actual_harvest_snapshot_resolved_identity_hash",
        ),
    )


class ActualHarvestValidationRunModel(Base):
    __tablename__ = "actual_harvest_validation_run"

    id: Mapped[int] = mapped_column(_sqlite_bigint(), primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        _sqlite_bigint(),
        ForeignKey(
            "actual_harvest_import_batch.id",
            name="fk_actual_harvest_validation_run_batch",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    request_identity_hash: Mapped[str] = mapped_column(Text, nullable=False)
    instance_identity_hash: Mapped[str] = mapped_column(Text, nullable=False)
    seal_manifest_hash: Mapped[str] = mapped_column(Text, nullable=False)
    mapping_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    validation_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    season_resolver_version: Mapped[str] = mapped_column(Text, nullable=False)
    committed_lineage_basis_hash: Mapped[str] = mapped_column(Text, nullable=False)
    registry_content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    record_manifest_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    is_current: Mapped[bool] = mapped_column(nullable=False, default=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active_attempt_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    active_attempt_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lineage_graph_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_result_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    mapping_snapshot_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_identity_snapshot_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    valid_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    invalid_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "batch_id",
            "instance_identity_hash",
            name="uq_actual_harvest_validation_run_instance",
        ),
        CheckConstraint(
            _enum_check("status", VALIDATION_STATUS_VALUES),
            name="ck_actual_harvest_validation_run_status",
        ),
        CheckConstraint(
            _sha_check("request_identity_hash"), name="ck_actual_harvest_validation_request_hash"
        ),
        CheckConstraint(
            _sha_check("instance_identity_hash"), name="ck_actual_harvest_validation_instance_hash"
        ),
        CheckConstraint(
            _sha_check("seal_manifest_hash"), name="ck_actual_harvest_validation_seal_hash"
        ),
        CheckConstraint(
            _sha_check("committed_lineage_basis_hash"),
            name="ck_actual_harvest_validation_basis_hash",
        ),
        CheckConstraint(
            _sha_check("registry_content_hash"), name="ck_actual_harvest_validation_registry_hash"
        ),
        CheckConstraint(
            _sha_check("record_manifest_hash"),
            name="ck_actual_harvest_validation_record_manifest_hash",
        ),
        CheckConstraint(
            _sha_check("lineage_graph_hash", nullable=True),
            name="ck_actual_harvest_validation_lineage_hash",
        ),
        CheckConstraint(
            _sha_check("validation_result_hash", nullable=True),
            name="ck_actual_harvest_validation_result_hash",
        ),
        CheckConstraint(
            _sha_check("mapping_snapshot_hash", nullable=True),
            name="ck_actual_harvest_validation_snapshot_hash",
        ),
        CheckConstraint(
            _sha_check("resolved_identity_snapshot_hash", nullable=True),
            name="ck_actual_harvest_validation_resolved_identity_hash",
        ),
        Index("ix_actual_harvest_validation_run_current", "batch_id", "is_current"),
    )


class ActualHarvestValidationAttemptModel(Base):
    __tablename__ = "actual_harvest_validation_attempt"

    id: Mapped[int] = mapped_column(_sqlite_bigint(), primary_key=True, autoincrement=True)
    validation_run_id: Mapped[int] = mapped_column(
        _sqlite_bigint(),
        ForeignKey(
            "actual_harvest_validation_run.id",
            name="fk_actual_harvest_validation_attempt_run",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    attempt_id: Mapped[str] = mapped_column(Text, nullable=False)
    attempt_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    fencing_token: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    abandoned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("attempt_id", name="uq_actual_harvest_validation_attempt_id"),
        UniqueConstraint(
            "validation_run_id",
            "attempt_generation",
            name="uq_actual_harvest_validation_attempt_generation",
        ),
        CheckConstraint(
            _enum_check("status", ATTEMPT_STATUS_VALUES),
            name="ck_actual_harvest_validation_attempt_status",
        ),
    )


class ActualHarvestValidationResultModel(Base):
    __tablename__ = "actual_harvest_validation_result"

    id: Mapped[int] = mapped_column(_sqlite_bigint(), primary_key=True, autoincrement=True)
    validation_run_id: Mapped[int] = mapped_column(
        _sqlite_bigint(),
        ForeignKey(
            "actual_harvest_validation_run.id",
            name="fk_actual_harvest_validation_result_run",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    validation_result_hash: Mapped[str] = mapped_column(Text, nullable=False)
    lineage_graph_hash: Mapped[str] = mapped_column(Text, nullable=False)
    committed_lineage_basis_hash: Mapped[str] = mapped_column(Text, nullable=False)
    mapping_snapshot_hash: Mapped[str] = mapped_column(Text, nullable=False)
    resolved_identity_snapshot_hash: Mapped[str] = mapped_column(Text, nullable=False)
    season_resolver_version: Mapped[str] = mapped_column(Text, nullable=False)
    valid_count: Mapped[int] = mapped_column(Integer, nullable=False)
    invalid_count: Mapped[int] = mapped_column(Integer, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False)
    result_payload: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("validation_run_id", name="uq_actual_harvest_validation_result_run"),
        CheckConstraint(
            _sha_check("validation_result_hash"),
            name="ck_actual_harvest_validation_result_hash_row",
        ),
        CheckConstraint(
            _sha_check("lineage_graph_hash"),
            name="ck_actual_harvest_validation_result_lineage_hash",
        ),
        CheckConstraint(
            _sha_check("committed_lineage_basis_hash"),
            name="ck_actual_harvest_validation_result_basis_hash",
        ),
        CheckConstraint(
            _sha_check("mapping_snapshot_hash"),
            name="ck_actual_harvest_validation_result_snapshot_hash",
        ),
        CheckConstraint(
            _sha_check("resolved_identity_snapshot_hash"),
            name="ck_actual_harvest_validation_result_resolved_identity_hash",
        ),
    )


class ActualHarvestValidationRecordModel(Base):
    __tablename__ = "actual_harvest_validation_record"

    id: Mapped[int] = mapped_column(_sqlite_bigint(), primary_key=True, autoincrement=True)
    validation_run_id: Mapped[int] = mapped_column(
        _sqlite_bigint(),
        ForeignKey(
            "actual_harvest_validation_run.id",
            name="fk_actual_harvest_validation_record_run",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    origin: Mapped[str] = mapped_column(Text, nullable=False)
    record_index: Mapped[int] = mapped_column(Integer, nullable=False)
    source_system: Mapped[str] = mapped_column(Text, nullable=False)
    external_logical_record_id: Mapped[str] = mapped_column(Text, nullable=False)
    external_revision_id: Mapped[str] = mapped_column(Text, nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    canonical_record_hash: Mapped[str] = mapped_column(Text, nullable=False)
    mapping_outcome: Mapped[str] = mapped_column(Text, nullable=False)
    is_valid: Mapped[bool] = mapped_column(nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint(
            "validation_run_id",
            "origin",
            "source_system",
            "external_revision_id",
            name="uq_actual_harvest_validation_record_key",
        ),
        CheckConstraint(
            _enum_check("origin", EVIDENCE_ORIGIN_VALUES),
            name="ck_actual_harvest_validation_record_origin",
        ),
        CheckConstraint(
            _sha_check("canonical_record_hash"), name="ck_actual_harvest_validation_record_hash"
        ),
        Index("ix_actual_harvest_validation_record_page", "validation_run_id", "record_index"),
    )


class ActualHarvestValidationMappingEvidenceModel(Base):
    __tablename__ = "actual_harvest_validation_mapping_evidence"

    id: Mapped[int] = mapped_column(_sqlite_bigint(), primary_key=True, autoincrement=True)
    validation_run_id: Mapped[int] = mapped_column(
        _sqlite_bigint(),
        ForeignKey(
            "actual_harvest_validation_run.id",
            name="fk_actual_harvest_validation_mapping_evidence_run",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    record_index: Mapped[int] = mapped_column(Integer, nullable=False)
    source_system: Mapped[str] = mapped_column(Text, nullable=False)
    external_logical_record_id: Mapped[str] = mapped_column(Text, nullable=False)
    external_revision_id: Mapped[str] = mapped_column(Text, nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_field: Mapped[str] = mapped_column(Text, nullable=False)
    source_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    registry_version: Mapped[str] = mapped_column(Text, nullable=False)
    mapping_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    resolver_version: Mapped[str] = mapped_column(Text, nullable=False)
    registry_entry_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_business_key: Mapped[str] = mapped_column(Text, nullable=False)
    target_parent_business_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_master_business_key: Mapped[str] = mapped_column(Text, nullable=False)
    resolved_master_parent_business_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_master_record_hash: Mapped[str] = mapped_column(Text, nullable=False)
    resolved_season_id: Mapped[int | None] = mapped_column(
        _sqlite_bigint(),
        ForeignKey(
            "dim_season.id", name="fk_actual_harvest_mapping_evidence_season", ondelete="RESTRICT"
        ),
        nullable=True,
    )
    resolved_farm_id: Mapped[int | None] = mapped_column(
        _sqlite_bigint(),
        ForeignKey(
            "dim_farm.id", name="fk_actual_harvest_mapping_evidence_farm", ondelete="RESTRICT"
        ),
        nullable=True,
    )
    resolved_subfarm_id: Mapped[int | None] = mapped_column(
        _sqlite_bigint(),
        ForeignKey(
            "dim_subfarm.id", name="fk_actual_harvest_mapping_evidence_subfarm", ondelete="RESTRICT"
        ),
        nullable=True,
    )
    resolved_variety_id: Mapped[int | None] = mapped_column(
        _sqlite_bigint(),
        ForeignKey(
            "dim_variety.id", name="fk_actual_harvest_mapping_evidence_variety", ondelete="RESTRICT"
        ),
        nullable=True,
    )
    resolution_mode: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "validation_run_id",
            "record_index",
            "source_field",
            name="uq_actual_harvest_validation_mapping_evidence_field",
        ),
        CheckConstraint(
            _sha_check("registry_entry_hash", nullable=True),
            name="ck_actual_harvest_validation_mapping_entry_hash",
        ),
        CheckConstraint(
            _sha_check("resolved_master_record_hash"),
            name="ck_actual_harvest_validation_resolved_master_hash",
        ),
        CheckConstraint(
            _enum_check("target_type", MAPPING_TARGET_VALUES),
            name="ck_actual_harvest_validation_mapping_target_type",
        ),
        CheckConstraint(
            "(target_type = 'SEASON' AND resolved_season_id IS NOT NULL "
            "AND resolved_farm_id IS NULL AND resolved_subfarm_id IS NULL "
            "AND resolved_variety_id IS NULL) OR "
            "(target_type = 'FARM' AND resolved_season_id IS NULL "
            "AND resolved_farm_id IS NOT NULL AND resolved_subfarm_id IS NULL "
            "AND resolved_variety_id IS NULL) OR "
            "(target_type = 'SUBFARM' AND resolved_season_id IS NULL "
            "AND resolved_farm_id IS NULL AND resolved_subfarm_id IS NOT NULL "
            "AND resolved_variety_id IS NULL) OR "
            "(target_type = 'VARIETY' AND resolved_season_id IS NULL "
            "AND resolved_farm_id IS NULL AND resolved_subfarm_id IS NULL "
            "AND resolved_variety_id IS NOT NULL)",
            name="ck_actual_harvest_validation_mapping_target_fk",
        ),
        Index(
            "ix_actual_harvest_validation_mapping_evidence_record",
            "validation_run_id",
            "record_index",
        ),
    )


class ActualHarvestValidationErrorModel(Base):
    __tablename__ = "actual_harvest_validation_error"

    id: Mapped[int] = mapped_column(_sqlite_bigint(), primary_key=True, autoincrement=True)
    validation_run_id: Mapped[int] = mapped_column(
        _sqlite_bigint(),
        ForeignKey(
            "actual_harvest_validation_run.id",
            name="fk_actual_harvest_validation_error_run",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    error_code: Mapped[str] = mapped_column(Text, nullable=False)
    record_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    external_logical_record_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_revision_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    field_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    message_template_id: Mapped[str] = mapped_column(Text, nullable=False)
    sanitized_details: Mapped[str] = mapped_column(Text, nullable=False)
    sort_key: Mapped[str] = mapped_column(Text, nullable=False)
    error_hash: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "validation_run_id", "error_hash", name="uq_actual_harvest_validation_error_hash"
        ),
        Index("ix_actual_harvest_validation_error_page", "validation_run_id", "sort_key"),
    )


class ActualHarvestValidationLineageNodeModel(Base):
    __tablename__ = "actual_harvest_validation_lineage_node"

    id: Mapped[int] = mapped_column(_sqlite_bigint(), primary_key=True, autoincrement=True)
    validation_run_id: Mapped[int] = mapped_column(
        _sqlite_bigint(),
        ForeignKey(
            "actual_harvest_validation_run.id",
            name="fk_actual_harvest_validation_node_run",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    origin: Mapped[str] = mapped_column(Text, nullable=False)
    source_system: Mapped[str] = mapped_column(Text, nullable=False)
    external_logical_record_id: Mapped[str] = mapped_column(Text, nullable=False)
    external_revision_id: Mapped[str] = mapped_column(Text, nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    record_status: Mapped[str] = mapped_column(Text, nullable=False)
    supersedes_external_revision_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_record_hash: Mapped[str] = mapped_column(Text, nullable=False)
    source_recorded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_recorded_at_authority_status: Mapped[str] = mapped_column(Text, nullable=False)
    node_hash: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "validation_run_id",
            "source_system",
            "external_revision_id",
            name="uq_actual_harvest_validation_node_key",
        ),
        CheckConstraint(
            _enum_check("origin", EVIDENCE_ORIGIN_VALUES),
            name="ck_actual_harvest_validation_node_origin",
        ),
        CheckConstraint(
            _sha_check("canonical_record_hash"),
            name="ck_actual_harvest_validation_node_record_hash",
        ),
        CheckConstraint(_sha_check("node_hash"), name="ck_actual_harvest_validation_node_hash"),
    )


class ActualHarvestValidationLineageEdgeModel(Base):
    __tablename__ = "actual_harvest_validation_lineage_edge"

    id: Mapped[int] = mapped_column(_sqlite_bigint(), primary_key=True, autoincrement=True)
    validation_run_id: Mapped[int] = mapped_column(
        _sqlite_bigint(),
        ForeignKey(
            "actual_harvest_validation_run.id",
            name="fk_actual_harvest_validation_edge_run",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    source_system: Mapped[str] = mapped_column(Text, nullable=False)
    predecessor_revision_id: Mapped[str] = mapped_column(Text, nullable=False)
    successor_revision_id: Mapped[str] = mapped_column(Text, nullable=False)
    edge_type: Mapped[str] = mapped_column(Text, nullable=False)
    edge_hash: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "validation_run_id",
            "source_system",
            "predecessor_revision_id",
            "successor_revision_id",
            name="uq_actual_harvest_validation_edge_key",
        ),
        CheckConstraint(_sha_check("edge_hash"), name="ck_actual_harvest_validation_edge_hash"),
    )


class ActualHarvestValidationLineageBasisModel(Base):
    __tablename__ = "actual_harvest_validation_lineage_basis"

    id: Mapped[int] = mapped_column(_sqlite_bigint(), primary_key=True, autoincrement=True)
    validation_run_id: Mapped[int] = mapped_column(
        _sqlite_bigint(),
        ForeignKey(
            "actual_harvest_validation_run.id",
            name="fk_actual_harvest_validation_basis_run",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    source_system: Mapped[str] = mapped_column(Text, nullable=False)
    authority_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    committed_lineage_basis_hash: Mapped[str] = mapped_column(Text, nullable=False)
    member_count: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("validation_run_id", name="uq_actual_harvest_validation_basis_run"),
        CheckConstraint(
            _sha_check("committed_lineage_basis_hash"),
            name="ck_actual_harvest_validation_basis_hash_row",
        ),
    )


class ActualHarvestValidationLineageBasisMemberModel(Base):
    __tablename__ = "actual_harvest_validation_lineage_basis_member"

    id: Mapped[int] = mapped_column(_sqlite_bigint(), primary_key=True, autoincrement=True)
    basis_id: Mapped[int] = mapped_column(
        _sqlite_bigint(),
        ForeignKey(
            "actual_harvest_validation_lineage_basis.id",
            name="fk_actual_harvest_validation_basis_member_basis",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    source_system: Mapped[str] = mapped_column(Text, nullable=False)
    committed_batch_ref: Mapped[str] = mapped_column(Text, nullable=False)
    external_logical_record_id: Mapped[str] = mapped_column(Text, nullable=False)
    external_revision_id: Mapped[str] = mapped_column(Text, nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    canonical_record_hash: Mapped[str] = mapped_column(Text, nullable=False)
    predecessor_revision_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    record_status: Mapped[str] = mapped_column(Text, nullable=False)
    source_recorded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_recorded_at_authority_status: Mapped[str] = mapped_column(Text, nullable=False)
    member_sort_key: Mapped[str] = mapped_column(Text, nullable=False)
    member_hash: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "basis_id",
            "source_system",
            "external_revision_id",
            name="uq_actual_harvest_validation_basis_member_key",
        ),
        CheckConstraint(
            _sha_check("canonical_record_hash"),
            name="ck_actual_harvest_validation_basis_member_record_hash",
        ),
        CheckConstraint(
            _sha_check("member_hash"), name="ck_actual_harvest_validation_basis_member_hash"
        ),
        Index("ix_actual_harvest_validation_basis_member_sort", "basis_id", "member_sort_key"),
    )


__all__ = [name for name in globals() if name.startswith("ActualHarvest")]
