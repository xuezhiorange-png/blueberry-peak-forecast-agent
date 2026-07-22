"""I7 label-snapshot ORM models (4 logical tables).

Frozen contract:
- docs/forecast-quality/q2a-i7-label-snapshot-and-revision-winner-contract.md §17
- Migration 0021 creates these tables and the PostgreSQL + SQLite
  immutability triggers that reject UPDATE and DELETE.
- All FKs use ``ON DELETE RESTRICT``.
- All hash columns are 64-char lowercase hex TEXT (NOT NULL except
  where the contract permits NULL mapping evidence).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    TypeDecorator,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.actual_harvest_labels.enums import (
    ActualHarvestLabelVisibilityMode,
)
from backend.app.db.base import Base

HEADER_TABLE_NAME = "actual_harvest_label_snapshot"
WINNER_TABLE_NAME = "actual_harvest_label_snapshot_winner"
LABEL_TABLE_NAME = "actual_harvest_label_snapshot_label"
EXCLUSION_TABLE_NAME = "actual_harvest_label_snapshot_exclusion"

RECORD_STATUS_VALUES: tuple[str, ...] = ("ACTIVE", "CORRECTED", "VOID", "FINALIZED")
EFFECTIVE_STATUS_VALUES: tuple[str, ...] = ("ACTIVE", "FINALIZED")
SOURCE_AUTHORITY_VALUES: tuple[str, ...] = (
    "TRUSTED_SOURCE_TIMESTAMP",
    "USER_ASSERTED_UNVERIFIED",
    "MISSING",
    "CONFLICTING",
)


def _sqlite_bigint() -> Any:
    return BigInteger().with_variant(Integer(), "sqlite")


def _enum_check(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


def _sha256_hex_check(column: str, *, nullable: bool) -> str:
    expression = column
    for character in "0123456789abcdef":
        expression = f"replace({expression}, '{character}', '')"
    valid = f"length({column}) = 64 AND lower({column}) = {column} AND length({expression}) = 0"
    return f"{column} IS NULL OR ({valid})" if nullable else valid


class UTCDateTimeI7(TypeDecorator):  # type: ignore[type-arg]
    """Timezone-aware datetime for I7 snapshot tables (SQLite + PostgreSQL)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(
        self,
        value: datetime | None,
        dialect: Any,
    ) -> datetime | None:
        del dialect
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        return value.astimezone(UTC)

    def process_result_value(
        self,
        value: datetime | None,
        dialect: Any,
    ) -> datetime | None:
        del dialect
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def _utc_now() -> datetime:
    return datetime.now(UTC)


_VISIBILITY_VALUES = tuple(item.value for item in ActualHarvestLabelVisibilityMode)


class ActualHarvestLabelSnapshotModel(Base):
    __tablename__ = HEADER_TABLE_NAME

    id: Mapped[int] = mapped_column(_sqlite_bigint(), primary_key=True, autoincrement=True)
    snapshot_idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    source_system: Mapped[str] = mapped_column(Text, nullable=False)
    visibility_mode: Mapped[str] = mapped_column(Text, nullable=False)
    label_observation_cutoff_at_or_null: Mapped[datetime | None] = mapped_column(
        UTCDateTimeI7(), nullable=True
    )
    harvest_date_start: Mapped[Any] = mapped_column(Date, nullable=False)
    harvest_date_end: Mapped[Any] = mapped_column(Date, nullable=False)
    season_business_keys: Mapped[str] = mapped_column(Text, nullable=False)
    farm_business_keys_or_empty_for_all: Mapped[str] = mapped_column(Text, nullable=False)
    variety_business_keys_or_empty_for_all: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    winner_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    aggregation_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_request_identity_hash: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_instance_identity_hash: Mapped[str] = mapped_column(Text, nullable=False)
    source_commit_manifest_set_hash: Mapped[str] = mapped_column(Text, nullable=False)
    winner_manifest_hash: Mapped[str] = mapped_column(Text, nullable=False)
    label_row_set_hash: Mapped[str] = mapped_column(Text, nullable=False)
    exclusion_manifest_hash: Mapped[str] = mapped_column(Text, nullable=False)
    label_snapshot_hash: Mapped[str] = mapped_column(Text, nullable=False)
    source_manifest_count: Mapped[int] = mapped_column(Integer, nullable=False)
    winner_count: Mapped[int] = mapped_column(Integer, nullable=False)
    label_row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    exclusion_row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_executed_at: Mapped[datetime] = mapped_column(UTCDateTimeI7(), nullable=False)
    created_by_identity: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTimeI7(), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "source_system",
            "snapshot_idempotency_key",
            name="uq_actual_harvest_label_snapshot_idempotency",
        ),
        CheckConstraint(
            _enum_check("visibility_mode", _VISIBILITY_VALUES),
            name="ck_actual_harvest_label_snapshot_visibility_mode",
        ),
        CheckConstraint(
            "harvest_date_start <= harvest_date_end",
            name="ck_actual_harvest_label_snapshot_date_range",
        ),
        CheckConstraint(
            "(visibility_mode = 'AS_OF_EVALUATION' "
            "AND label_observation_cutoff_at_or_null IS NOT NULL) "
            "OR (visibility_mode = 'FINAL_ADJUDICATED' "
            "AND label_observation_cutoff_at_or_null IS NULL)",
            name="ck_actual_harvest_label_snapshot_cutoff_binding",
        ),
        CheckConstraint(
            "source_manifest_count >= 0 "
            "AND winner_count >= 0 "
            "AND label_row_count >= 0 "
            "AND exclusion_row_count >= 0",
            name="ck_actual_harvest_label_snapshot_counts_nonneg",
        ),
        CheckConstraint(
            _sha256_hex_check("snapshot_request_identity_hash", nullable=False),
            name="ck_actual_harvest_label_snapshot_request_hash",
        ),
        CheckConstraint(
            _sha256_hex_check("snapshot_instance_identity_hash", nullable=False),
            name="ck_actual_harvest_label_snapshot_instance_hash",
        ),
        CheckConstraint(
            _sha256_hex_check("source_commit_manifest_set_hash", nullable=False),
            name="ck_actual_harvest_label_snapshot_manifest_set_hash",
        ),
        CheckConstraint(
            _sha256_hex_check("winner_manifest_hash", nullable=False),
            name="ck_actual_harvest_label_snapshot_winner_hash",
        ),
        CheckConstraint(
            _sha256_hex_check("label_row_set_hash", nullable=False),
            name="ck_actual_harvest_label_snapshot_label_row_hash",
        ),
        CheckConstraint(
            _sha256_hex_check("exclusion_manifest_hash", nullable=False),
            name="ck_actual_harvest_label_snapshot_exclusion_hash",
        ),
        CheckConstraint(
            _sha256_hex_check("label_snapshot_hash", nullable=False),
            name="ck_actual_harvest_label_snapshot_hash",
        ),
        Index(
            "ix_actual_harvest_label_snapshot_idempotency",
            "source_system",
            "snapshot_idempotency_key",
        ),
        Index(
            "ix_actual_harvest_label_snapshot_executed_at",
            "snapshot_executed_at",
        ),
    )


class ActualHarvestLabelSnapshotWinnerModel(Base):
    __tablename__ = WINNER_TABLE_NAME

    id: Mapped[int] = mapped_column(_sqlite_bigint(), primary_key=True, autoincrement=True)
    snapshot_id: Mapped[int] = mapped_column(
        _sqlite_bigint(),
        ForeignKey(
            f"{HEADER_TABLE_NAME}.id",
            name="fk_actual_harvest_label_snapshot_winner_snapshot",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    source_system: Mapped[str] = mapped_column(Text, nullable=False)
    external_logical_record_id: Mapped[str] = mapped_column(Text, nullable=False)
    external_revision_id: Mapped[str] = mapped_column(Text, nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    canonical_record_hash: Mapped[str] = mapped_column(Text, nullable=False)
    record_status: Mapped[str] = mapped_column(Text, nullable=False)
    effective_status: Mapped[str] = mapped_column(Text, nullable=False)
    finalized_at_or_null: Mapped[datetime | None] = mapped_column(UTCDateTimeI7(), nullable=True)
    source_recorded_at_or_null: Mapped[datetime | None] = mapped_column(
        UTCDateTimeI7(), nullable=True
    )
    source_recorded_at_authority_status: Mapped[str] = mapped_column(Text, nullable=False)
    harvest_business_date: Mapped[Any] = mapped_column(Date, nullable=False)
    actual_harvest_quantity_kg: Mapped[Any] = mapped_column(
        Numeric(18, 6, asdecimal=True), nullable=False
    )
    commit_manifest_hash: Mapped[str] = mapped_column(Text, nullable=False)
    season_business_key: Mapped[str] = mapped_column(Text, nullable=False)
    farm_business_key: Mapped[str] = mapped_column(Text, nullable=False)
    subfarm_business_key: Mapped[str] = mapped_column(Text, nullable=False)
    variety_business_key: Mapped[str] = mapped_column(Text, nullable=False)
    season_id: Mapped[int | None] = mapped_column(
        _sqlite_bigint(),
        ForeignKey(
            "dim_season.id",
            name="fk_actual_harvest_label_snapshot_winner_season",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    farm_id: Mapped[int | None] = mapped_column(
        _sqlite_bigint(),
        ForeignKey(
            "dim_farm.id",
            name="fk_actual_harvest_label_snapshot_winner_farm",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    subfarm_id: Mapped[int | None] = mapped_column(
        _sqlite_bigint(),
        ForeignKey(
            "dim_subfarm.id",
            name="fk_actual_harvest_label_snapshot_winner_subfarm",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    variety_id: Mapped[int | None] = mapped_column(
        _sqlite_bigint(),
        ForeignKey(
            "dim_variety.id",
            name="fk_actual_harvest_label_snapshot_winner_variety",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    mapping_registry_version: Mapped[str] = mapped_column(Text, nullable=False)
    mapping_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    season_resolver_version: Mapped[str] = mapped_column(Text, nullable=False)
    mapping_registry_entry_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_master_business_key: Mapped[str] = mapped_column(Text, nullable=False)
    resolved_master_parent_business_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_master_record_hash: Mapped[str] = mapped_column(Text, nullable=False)
    mapping_snapshot_hash: Mapped[str] = mapped_column(Text, nullable=False)
    resolved_identity_snapshot_hash: Mapped[str] = mapped_column(Text, nullable=False)
    registry_content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    winner_row_hash: Mapped[str] = mapped_column(Text, nullable=False)
    winner_sort_key: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "snapshot_id",
            "source_system",
            "external_revision_id",
            name="uq_actual_harvest_label_snapshot_winner_revision",
        ),
        CheckConstraint(
            "actual_harvest_quantity_kg >= 0",
            name="ck_actual_harvest_label_snapshot_winner_quantity_nonneg",
        ),
        CheckConstraint(
            _enum_check("record_status", RECORD_STATUS_VALUES),
            name="ck_actual_harvest_label_snapshot_winner_record_status",
        ),
        CheckConstraint(
            _enum_check("effective_status", EFFECTIVE_STATUS_VALUES),
            name="ck_actual_harvest_label_snapshot_winner_effective_status",
        ),
        CheckConstraint(
            _enum_check(
                "source_recorded_at_authority_status",
                SOURCE_AUTHORITY_VALUES,
            ),
            name="ck_actual_harvest_label_snapshot_winner_authority",
        ),
        CheckConstraint(
            _sha256_hex_check("canonical_record_hash", nullable=False),
            name="ck_actual_harvest_label_snapshot_winner_canonical_record_hash",
        ),
        CheckConstraint(
            _sha256_hex_check("commit_manifest_hash", nullable=False),
            name="ck_actual_harvest_label_snapshot_winner_commit_manifest_hash",
        ),
        CheckConstraint(
            _sha256_hex_check("mapping_registry_entry_hash", nullable=True),
            name="ck_actual_harvest_label_snapshot_winner_registry_entry_hash",
        ),
        CheckConstraint(
            _sha256_hex_check("resolved_master_record_hash", nullable=False),
            name="ck_actual_harvest_label_snapshot_winner_resolved_master_hash",
        ),
        CheckConstraint(
            _sha256_hex_check("mapping_snapshot_hash", nullable=False),
            name="ck_actual_harvest_label_snapshot_winner_mapping_snapshot_hash",
        ),
        CheckConstraint(
            _sha256_hex_check("resolved_identity_snapshot_hash", nullable=False),
            name="ck_actual_harvest_label_snapshot_winner_resolved_identity_hash",
        ),
        CheckConstraint(
            _sha256_hex_check("registry_content_hash", nullable=False),
            name="ck_actual_harvest_label_snapshot_winner_registry_content_hash",
        ),
        CheckConstraint(
            _sha256_hex_check("winner_row_hash", nullable=False),
            name="ck_actual_harvest_label_snapshot_winner_row_hash",
        ),
        Index(
            "ix_actual_harvest_label_snapshot_winner_sort",
            "snapshot_id",
            "winner_sort_key",
        ),
        Index(
            "ix_actual_harvest_label_snapshot_winner_logical",
            "snapshot_id",
            "source_system",
            "external_logical_record_id",
        ),
    )


class ActualHarvestLabelSnapshotLabelModel(Base):
    __tablename__ = LABEL_TABLE_NAME

    id: Mapped[int] = mapped_column(_sqlite_bigint(), primary_key=True, autoincrement=True)
    snapshot_id: Mapped[int] = mapped_column(
        _sqlite_bigint(),
        ForeignKey(
            f"{HEADER_TABLE_NAME}.id",
            name="fk_actual_harvest_label_snapshot_label_snapshot",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    season_business_key: Mapped[str] = mapped_column(Text, nullable=False)
    farm_business_key: Mapped[str] = mapped_column(Text, nullable=False)
    subfarm_business_key: Mapped[str] = mapped_column(Text, nullable=False)
    variety_business_key: Mapped[str] = mapped_column(Text, nullable=False)
    harvest_business_date: Mapped[Any] = mapped_column(Date, nullable=False)
    exact_decimal_quantity_sum_kg: Mapped[Any] = mapped_column(
        Numeric(18, 6, asdecimal=True), nullable=False
    )
    contributing_winner_count: Mapped[int] = mapped_column(Integer, nullable=False)
    contributing_winner_hashes: Mapped[str] = mapped_column(Text, nullable=False)
    label_row_hash: Mapped[str] = mapped_column(Text, nullable=False)
    label_sort_key: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "snapshot_id",
            "season_business_key",
            "farm_business_key",
            "subfarm_business_key",
            "variety_business_key",
            "harvest_business_date",
            name="uq_actual_harvest_label_snapshot_label_grain",
        ),
        CheckConstraint(
            "exact_decimal_quantity_sum_kg >= 0",
            name="ck_actual_harvest_label_snapshot_label_sum_nonneg",
        ),
        CheckConstraint(
            "contributing_winner_count >= 0",
            name="ck_actual_harvest_label_snapshot_label_count_nonneg",
        ),
        CheckConstraint(
            _sha256_hex_check("label_row_hash", nullable=False),
            name="ck_actual_harvest_label_snapshot_label_row_hash",
        ),
        Index(
            "ix_actual_harvest_label_snapshot_label_sort",
            "snapshot_id",
            "label_sort_key",
        ),
    )


class ActualHarvestLabelSnapshotExclusionModel(Base):
    __tablename__ = EXCLUSION_TABLE_NAME

    id: Mapped[int] = mapped_column(_sqlite_bigint(), primary_key=True, autoincrement=True)
    snapshot_id: Mapped[int] = mapped_column(
        _sqlite_bigint(),
        ForeignKey(
            f"{HEADER_TABLE_NAME}.id",
            name="fk_actual_harvest_label_snapshot_exclusion_snapshot",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    exclusion_category: Mapped[str] = mapped_column(Text, nullable=False)
    source_system: Mapped[str] = mapped_column(Text, nullable=False)
    external_logical_record_id_or_null: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_revision_id_or_null: Mapped[str | None] = mapped_column(Text, nullable=True)
    harvest_business_date_or_null: Mapped[Any | None] = mapped_column(Date, nullable=True)
    exclusion_row_hash: Mapped[str] = mapped_column(Text, nullable=False)
    exclusion_details: Mapped[str] = mapped_column(Text, nullable=False)
    exclusion_sort_key: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "snapshot_id",
            "exclusion_category",
            "source_system",
            "external_logical_record_id_or_null",
            "external_revision_id_or_null",
            "harvest_business_date_or_null",
            name="uq_actual_harvest_label_snapshot_exclusion_row",
        ),
        CheckConstraint(
            _sha256_hex_check("exclusion_row_hash", nullable=False),
            name="ck_actual_harvest_label_snapshot_exclusion_row_hash",
        ),
        Index(
            "ix_actual_harvest_label_snapshot_exclusion_sort",
            "snapshot_id",
            "exclusion_sort_key",
        ),
    )


__all__ = [
    "ActualHarvestLabelSnapshotExclusionModel",
    "ActualHarvestLabelSnapshotLabelModel",
    "ActualHarvestLabelSnapshotModel",
    "ActualHarvestLabelSnapshotWinnerModel",
    "EXCLUSION_TABLE_NAME",
    "HEADER_TABLE_NAME",
    "LABEL_TABLE_NAME",
    "WINNER_TABLE_NAME",
]
