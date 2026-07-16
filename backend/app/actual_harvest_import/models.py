from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    Text,
    TypeDecorator,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.actual_harvest_import.enums import (
    ActualHarvestBatchSealStatus,
    ActualHarvestImportBatchStatus,
    ActualHarvestImportChannel,
    ActualHarvestMissingRecordSemantics,
    ActualHarvestPhysicalEvent,
    ActualHarvestQuantityBasis,
    ActualHarvestQuantityUnit,
    ActualHarvestRecordStatus,
    SourceRecordedAtAuthorityStatus,
)
from backend.app.db.base import Base


def _sqlite_bigint() -> Any:
    return BigInteger().with_variant(Integer(), "sqlite")


def _quoted_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _enum_check(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({_quoted_values(values)})"


def _sha256_hex_check(column: str, *, nullable: bool) -> str:
    expression = column
    for character in "0123456789abcdef":
        expression = f"replace({expression}, '{character}', '')"
    valid = f"length({column}) = 64 AND lower({column}) = {column} AND length({expression}) = 0"
    return f"{column} IS NULL OR ({valid})" if nullable else valid


class UTCDateTime(TypeDecorator[datetime]):
    """Preserve timezone-aware instants on SQLite as well as PostgreSQL."""

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


_BATCH_STATUS_VALUES = tuple(item.value for item in ActualHarvestImportBatchStatus)
_BATCH_SEAL_VALUES = tuple(item.value for item in ActualHarvestBatchSealStatus)
_CHANNEL_VALUES = tuple(item.value for item in ActualHarvestImportChannel)
_RECORD_STATUS_VALUES = tuple(item.value for item in ActualHarvestRecordStatus)
_SOURCE_TIME_STATUS_VALUES = tuple(item.value for item in SourceRecordedAtAuthorityStatus)
_PHYSICAL_EVENT_VALUES = tuple(item.value for item in ActualHarvestPhysicalEvent)
_QUANTITY_BASIS_VALUES = tuple(item.value for item in ActualHarvestQuantityBasis)
_QUANTITY_UNIT_VALUES = tuple(item.value for item in ActualHarvestQuantityUnit)
_MISSING_RECORD_VALUES = tuple(item.value for item in ActualHarvestMissingRecordSemantics)


class ActualHarvestImportBatchModel(Base):
    __tablename__ = "actual_harvest_import_batch"

    id: Mapped[int] = mapped_column(_sqlite_bigint(), primary_key=True, autoincrement=True)
    import_id: Mapped[str] = mapped_column(Text, nullable=False)
    import_channel: Mapped[str] = mapped_column(Text, nullable=False)
    source_system: Mapped[str] = mapped_column(Text, nullable=False)
    source_dataset: Mapped[str] = mapped_column(Text, nullable=False)
    source_version: Mapped[str] = mapped_column(Text, nullable=False)
    external_batch_id: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    import_received_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    submitted_by_identity: Mapped[str] = mapped_column(Text, nullable=False)
    expected_record_count_or_null: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uploaded_record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    sealed_record_count_or_null: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sealed_at_or_null: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    sealed_by_identity_or_null: Mapped[str | None] = mapped_column(Text, nullable=True)
    seal_status: Mapped[str] = mapped_column(Text, nullable=False)
    server_raw_payload_hash_or_null: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_batch_hash_or_null: Mapped[str | None] = mapped_column(Text, nullable=True)
    seal_manifest_hash_or_null: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_file_name_or_null: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_file_hash_or_null: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    mapping_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    validation_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    source_semantics_attestation_version: Mapped[str] = mapped_column(Text, nullable=False)
    source_semantics_physical_event: Mapped[str] = mapped_column(Text, nullable=False)
    source_semantics_quantity_basis: Mapped[str] = mapped_column(Text, nullable=False)
    source_semantics_quantity_unit: Mapped[str] = mapped_column(Text, nullable=False)
    source_semantics_missing_record_semantics: Mapped[str] = mapped_column(Text, nullable=False)
    source_semantics_attestation_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    invalid_record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    committed_record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=func.now()
    )
    validated_at_or_null: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    committed_at_or_null: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    records: Mapped[list[ActualHarvestImportRecordModel]] = relationship(
        back_populates="batch",
        foreign_keys="ActualHarvestImportRecordModel.batch_id",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint("import_id", name="uq_actual_harvest_import_batch_import_id"),
        UniqueConstraint(
            "source_system",
            "external_batch_id",
            name="uq_actual_harvest_import_batch_source_external",
        ),
        UniqueConstraint(
            "source_system",
            "idempotency_key",
            name="uq_actual_harvest_import_batch_source_idempotency",
        ),
        UniqueConstraint(
            "id",
            "source_system",
            "external_batch_id",
            name="uq_actual_harvest_import_batch_composite_parent",
        ),
        CheckConstraint(
            "length(trim(import_id)) > 0",
            name="ck_actual_harvest_batch_import_id_nonempty",
        ),
        CheckConstraint(
            _enum_check("import_channel", _CHANNEL_VALUES),
            name="ck_actual_harvest_batch_import_channel",
        ),
        CheckConstraint(
            _enum_check("seal_status", _BATCH_SEAL_VALUES),
            name="ck_actual_harvest_batch_seal_status",
        ),
        CheckConstraint(
            _enum_check("status", _BATCH_STATUS_VALUES),
            name="ck_actual_harvest_batch_status",
        ),
        CheckConstraint(
            "(expected_record_count_or_null IS NULL OR expected_record_count_or_null >= 0) "
            "AND uploaded_record_count >= 0 "
            "AND (sealed_record_count_or_null IS NULL OR sealed_record_count_or_null >= 0) "
            "AND record_count >= 0 AND valid_record_count >= 0 "
            "AND invalid_record_count >= 0 AND committed_record_count >= 0",
            name="ck_actual_harvest_batch_counts_nonnegative",
        ),
        CheckConstraint(
            _sha256_hex_check("server_raw_payload_hash_or_null", nullable=True),
            name="ck_actual_harvest_batch_server_raw_hash",
        ),
        CheckConstraint(
            _sha256_hex_check("canonical_batch_hash_or_null", nullable=True),
            name="ck_actual_harvest_batch_canonical_hash",
        ),
        CheckConstraint(
            _sha256_hex_check("seal_manifest_hash_or_null", nullable=True),
            name="ck_actual_harvest_batch_seal_manifest_hash",
        ),
        CheckConstraint(
            _sha256_hex_check("source_file_hash_or_null", nullable=True),
            name="ck_actual_harvest_batch_source_file_hash",
        ),
        CheckConstraint(
            _sha256_hex_check("raw_payload_hash", nullable=False),
            name="ck_actual_harvest_batch_raw_payload_hash",
        ),
        CheckConstraint(
            _sha256_hex_check("source_semantics_attestation_hash", nullable=False),
            name="ck_actual_harvest_batch_attestation_hash",
        ),
        CheckConstraint(
            _enum_check("source_semantics_physical_event", _PHYSICAL_EVENT_VALUES),
            name="ck_actual_harvest_batch_physical_event",
        ),
        CheckConstraint(
            _enum_check("source_semantics_quantity_basis", _QUANTITY_BASIS_VALUES),
            name="ck_actual_harvest_batch_quantity_basis",
        ),
        CheckConstraint(
            _enum_check("source_semantics_quantity_unit", _QUANTITY_UNIT_VALUES),
            name="ck_actual_harvest_batch_quantity_unit",
        ),
        CheckConstraint(
            _enum_check(
                "source_semantics_missing_record_semantics",
                _MISSING_RECORD_VALUES,
            ),
            name="ck_actual_harvest_batch_missing_record_semantics",
        ),
        Index("ix_actual_harvest_import_batch_idempotency", "source_system", "idempotency_key"),
    )


class ActualHarvestImportRecordModel(Base):
    __tablename__ = "actual_harvest_import_record"

    id: Mapped[int] = mapped_column(_sqlite_bigint(), primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(_sqlite_bigint(), nullable=False)
    external_logical_record_id: Mapped[str] = mapped_column(Text, nullable=False)
    external_revision_id: Mapped[str] = mapped_column(Text, nullable=False)
    source_system: Mapped[str] = mapped_column(Text, nullable=False)
    external_batch_id: Mapped[str] = mapped_column(Text, nullable=False)
    harvest_business_date: Mapped[date] = mapped_column(Date, nullable=False)
    farm_code: Mapped[str] = mapped_column(Text, nullable=False)
    subfarm_or_plot_code: Mapped[str] = mapped_column(Text, nullable=False)
    variety_code: Mapped[str] = mapped_column(Text, nullable=False)
    actual_harvest_quantity_kg: Mapped[Any] = mapped_column(
        Numeric(18, 6, asdecimal=True), nullable=False
    )
    source_recorded_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    source_recorded_at_authority_status: Mapped[str] = mapped_column(Text, nullable=False)
    source_recorded_at_authority_reference_or_null: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    import_received_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    record_status: Mapped[str] = mapped_column(Text, nullable=False)
    supersedes_external_revision_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    season_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    farm_timezone: Mapped[str | None] = mapped_column(Text, nullable=True)
    revised_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    finalized_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    source_row_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_sheet_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    batch: Mapped[ActualHarvestImportBatchModel] = relationship(
        back_populates="records",
        foreign_keys=[batch_id],
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["batch_id", "source_system", "external_batch_id"],
            [
                "actual_harvest_import_batch.id",
                "actual_harvest_import_batch.source_system",
                "actual_harvest_import_batch.external_batch_id",
            ],
            name="fk_actual_harvest_record_batch_identity",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "source_system",
            "external_revision_id",
            name="uq_actual_harvest_record_source_revision",
        ),
        UniqueConstraint(
            "source_system",
            "external_logical_record_id",
            "revision_number",
            name="uq_actual_harvest_record_source_logical_revision",
        ),
        UniqueConstraint(
            "batch_id",
            "source_row_number",
            name="uq_actual_harvest_record_batch_row",
        ),
        CheckConstraint(
            "actual_harvest_quantity_kg >= 0",
            name="ck_actual_harvest_record_quantity_nonnegative",
        ),
        CheckConstraint(
            "revision_number >= 1",
            name="ck_actual_harvest_record_revision_positive",
        ),
        CheckConstraint(
            "source_row_number IS NULL OR source_row_number >= 1",
            name="ck_actual_harvest_record_source_row_positive",
        ),
        CheckConstraint(
            _enum_check(
                "source_recorded_at_authority_status",
                _SOURCE_TIME_STATUS_VALUES,
            ),
            name="ck_actual_harvest_record_source_time_status",
        ),
        CheckConstraint(
            _enum_check("record_status", _RECORD_STATUS_VALUES),
            name="ck_actual_harvest_record_status",
        ),
        Index("ix_actual_harvest_record_batch_id", "batch_id"),
        Index(
            "ix_actual_harvest_record_source_logical",
            "source_system",
            "external_logical_record_id",
            "revision_number",
        ),
    )


__all__ = [
    "ActualHarvestImportBatchModel",
    "ActualHarvestImportRecordModel",
    "UTCDateTime",
]
