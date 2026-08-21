"""Lane B cleaned-dataset ORM persistence (Draft-only; no Alembic migration)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from backend.app.db.base import Base
from backend.app.s2_materialized_dataset.lane_b.schemas import CleaningBuildResult


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


QUANTITY_PRESENCE_VALUES = ("KNOWN", "UNKNOWN_NOT_ZERO")
FINDING_SEVERITY_VALUES = ("ERROR", "WARNING")
FINDING_CODE_VALUES = (
    "MISSING_QUANTITY_UNKNOWN_NOT_ZERO",
    "DUPLICATE_CANONICAL_GRAIN",
)
EXCLUSION_CODE_VALUES = ("BUSINESS_EXCLUSION", "QUALITY_BLOCKED")


class S2CleanedDatasetVersionModel(Base):
    __tablename__ = "s2_cleaned_dataset_version"

    id: Mapped[int] = mapped_column(_sqlite_bigint(), primary_key=True, autoincrement=True)
    cleaned_dataset_version_identity_hash: Mapped[str] = mapped_column(Text, nullable=False)
    cleaned_dataset_version_content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    source_cohort_id: Mapped[str] = mapped_column(Text, nullable=False)
    mapping_registry_hash: Mapped[str] = mapped_column(Text, nullable=False)
    cleaning_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    quality_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    correction_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    exclusion_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    cleaned_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    quality_report_identity_hash: Mapped[str] = mapped_column(Text, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    excluded_row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    unknown_quantity_row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "cleaned_dataset_version_identity_hash",
            name="uq_s2_cleaned_dataset_version_identity",
        ),
        UniqueConstraint(
            "cleaned_dataset_version_content_hash",
            name="uq_s2_cleaned_dataset_version_content",
        ),
        CheckConstraint(
            _sha_check("cleaned_dataset_version_identity_hash"),
            name="ck_s2_cleaned_dataset_version_identity_hash",
        ),
        CheckConstraint(
            _sha_check("cleaned_dataset_version_content_hash"),
            name="ck_s2_cleaned_dataset_version_content_hash",
        ),
        CheckConstraint(
            _sha_check("mapping_registry_hash"),
            name="ck_s2_cleaned_dataset_mapping_registry_hash",
        ),
        CheckConstraint(
            _sha_check("quality_report_identity_hash"),
            name="ck_s2_cleaned_dataset_quality_report_hash",
        ),
    )


class S2CleanedRowModel(Base):
    __tablename__ = "s2_cleaned_row"

    id: Mapped[int] = mapped_column(_sqlite_bigint(), primary_key=True, autoincrement=True)
    cleaned_dataset_version_id: Mapped[int] = mapped_column(
        _sqlite_bigint(),
        ForeignKey("s2_cleaned_dataset_version.id", ondelete="RESTRICT"),
        nullable=False,
    )
    cleaned_row_identity_hash: Mapped[str] = mapped_column(Text, nullable=False)
    cleaned_row_content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    source_row_identity_hash: Mapped[str] = mapped_column(Text, nullable=False)
    season_business_key: Mapped[str] = mapped_column(Text, nullable=False)
    farm_business_key: Mapped[str] = mapped_column(Text, nullable=False)
    subfarm_business_key: Mapped[str] = mapped_column(Text, nullable=False)
    variety_business_key: Mapped[str] = mapped_column(Text, nullable=False)
    harvest_business_date: Mapped[Any] = mapped_column(Date, nullable=False)
    cleaning_projection_version: Mapped[str] = mapped_column(Text, nullable=False)
    cleaned_row_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    cleaning_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    correction_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    exclusion_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    source_actual_harvest_quantity_kg: Mapped[str | None] = mapped_column(Text, nullable=True)
    effective_actual_harvest_quantity_kg: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity_presence_status: Mapped[str] = mapped_column(Text, nullable=False)
    is_excluded: Mapped[bool] = mapped_column(nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "cleaned_dataset_version_id",
            "cleaned_row_identity_hash",
            name="uq_s2_cleaned_row_identity",
        ),
        UniqueConstraint(
            "cleaned_dataset_version_id",
            "season_business_key",
            "farm_business_key",
            "subfarm_business_key",
            "variety_business_key",
            "harvest_business_date",
            name="uq_s2_cleaned_row_grain",
        ),
        CheckConstraint(_sha_check("cleaned_row_identity_hash"), name="ck_s2_cleaned_row_identity"),
        CheckConstraint(_sha_check("cleaned_row_content_hash"), name="ck_s2_cleaned_row_content"),
        CheckConstraint(_sha_check("source_row_identity_hash"), name="ck_s2_cleaned_row_source"),
        CheckConstraint(
            _enum_check("quantity_presence_status", QUANTITY_PRESENCE_VALUES),
            name="ck_s2_cleaned_row_quantity_presence",
        ),
        CheckConstraint(
            (
                "(quantity_presence_status = 'UNKNOWN_NOT_ZERO' "
                "AND effective_actual_harvest_quantity_kg IS NULL) "
                "OR quantity_presence_status = 'KNOWN'"
            ),
            name="ck_s2_cleaned_row_unknown_not_zero",
        ),
    )


class S2QualityFindingModel(Base):
    __tablename__ = "s2_quality_finding"

    id: Mapped[int] = mapped_column(_sqlite_bigint(), primary_key=True, autoincrement=True)
    cleaned_dataset_version_id: Mapped[int] = mapped_column(
        _sqlite_bigint(),
        ForeignKey("s2_cleaned_dataset_version.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quality_finding_identity_hash: Mapped[str] = mapped_column(Text, nullable=False)
    source_row_identity_hash: Mapped[str] = mapped_column(Text, nullable=False)
    cleaned_row_identity_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    quality_rule_id: Mapped[str] = mapped_column(Text, nullable=False)
    quality_rule_version: Mapped[str] = mapped_column(Text, nullable=False)
    observed_field: Mapped[str] = mapped_column(Text, nullable=False)
    finding_code: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_observed_value_identity: Mapped[str] = mapped_column(Text, nullable=False)
    rule_definition_hash: Mapped[str] = mapped_column(Text, nullable=False)
    validation_run_identity: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "cleaned_dataset_version_id",
            "quality_finding_identity_hash",
            name="uq_s2_quality_finding_identity",
        ),
        CheckConstraint(
            _sha_check("quality_finding_identity_hash"),
            name="ck_s2_quality_finding_identity",
        ),
        CheckConstraint(
            _enum_check("severity", FINDING_SEVERITY_VALUES),
            name="ck_s2_quality_finding_severity",
        ),
        CheckConstraint(
            _enum_check("finding_code", FINDING_CODE_VALUES),
            name="ck_s2_quality_finding_code",
        ),
    )


class S2CorrectionLedgerEntryModel(Base):
    __tablename__ = "s2_correction_ledger_entry"

    id: Mapped[int] = mapped_column(_sqlite_bigint(), primary_key=True, autoincrement=True)
    cleaned_dataset_version_id: Mapped[int] = mapped_column(
        _sqlite_bigint(),
        ForeignKey("s2_cleaned_dataset_version.id", ondelete="RESTRICT"),
        nullable=False,
    )
    correction_ledger_entry_identity_hash: Mapped[str] = mapped_column(Text, nullable=False)
    source_row_identity_hash: Mapped[str] = mapped_column(Text, nullable=False)
    correction_event_id: Mapped[str] = mapped_column(Text, nullable=False)
    field_name: Mapped[str] = mapped_column(Text, nullable=False)
    correction_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    correction_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    quality_finding_identity_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_value_digest: Mapped[str] = mapped_column(Text, nullable=False)
    corrected_value_digest: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    manual_actor_or_authority_reference: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "cleaned_dataset_version_id",
            "correction_ledger_entry_identity_hash",
            name="uq_s2_correction_ledger_identity",
        ),
        UniqueConstraint(
            "cleaned_dataset_version_id",
            "correction_event_id",
            name="uq_s2_correction_ledger_event",
        ),
        CheckConstraint(
            _sha_check("correction_ledger_entry_identity_hash"),
            name="ck_s2_correction_ledger_identity",
        ),
    )


class S2ExclusionLedgerEntryModel(Base):
    __tablename__ = "s2_exclusion_ledger_entry"

    id: Mapped[int] = mapped_column(_sqlite_bigint(), primary_key=True, autoincrement=True)
    cleaned_dataset_version_id: Mapped[int] = mapped_column(
        _sqlite_bigint(),
        ForeignKey("s2_cleaned_dataset_version.id", ondelete="RESTRICT"),
        nullable=False,
    )
    exclusion_ledger_entry_identity_hash: Mapped[str] = mapped_column(Text, nullable=False)
    source_row_identity_hash: Mapped[str] = mapped_column(Text, nullable=False)
    exclusion_event_id: Mapped[str] = mapped_column(Text, nullable=False)
    exclusion_code: Mapped[str] = mapped_column(Text, nullable=False)
    exclusion_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    exclusion_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    quality_finding_identity_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    exclusion_reason_reference: Mapped[str] = mapped_column(Text, nullable=False)
    decision_authority_reference: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "cleaned_dataset_version_id",
            "exclusion_ledger_entry_identity_hash",
            name="uq_s2_exclusion_ledger_identity",
        ),
        UniqueConstraint(
            "cleaned_dataset_version_id",
            "source_row_identity_hash",
            name="uq_s2_exclusion_ledger_row",
        ),
        CheckConstraint(
            _sha_check("exclusion_ledger_entry_identity_hash"),
            name="ck_s2_exclusion_ledger_identity",
        ),
        CheckConstraint(
            _enum_check("exclusion_code", EXCLUSION_CODE_VALUES),
            name="ck_s2_exclusion_ledger_code",
        ),
    )


class CleanedDatasetVersionConflictError(ValueError):
    """Raised when a persisted version identity already exists with different content."""


def persist_cleaning_build_result(
    session: Session,
    result: CleaningBuildResult,
) -> S2CleanedDatasetVersionModel:
    existing = session.query(S2CleanedDatasetVersionModel).filter_by(
        cleaned_dataset_version_identity_hash=result.version.cleaned_dataset_version_identity_hash
    ).one_or_none()
    if existing is not None:
        if (
            existing.cleaned_dataset_version_content_hash
            != result.version.cleaned_dataset_version_content_hash
        ):
            raise CleanedDatasetVersionConflictError(
                "same dataset version identity with different content hashes"
            )
        return existing

    version_row = S2CleanedDatasetVersionModel(
        cleaned_dataset_version_identity_hash=result.version.cleaned_dataset_version_identity_hash,
        cleaned_dataset_version_content_hash=result.version.cleaned_dataset_version_content_hash,
        source_cohort_id=result.version.source_cohort_id,
        mapping_registry_hash=result.version.mapping_registry_hash,
        cleaning_policy_version=result.version.cleaning_policy_version,
        quality_policy_version=result.version.quality_policy_version,
        correction_policy_version=result.version.correction_policy_version,
        exclusion_policy_version=result.version.exclusion_policy_version,
        cleaned_schema_version=result.version.cleaned_schema_version,
        quality_report_identity_hash=result.version.quality_report_identity_hash,
        row_count=result.version.row_count,
        excluded_row_count=result.version.excluded_row_count,
        unknown_quantity_row_count=result.version.unknown_quantity_row_count,
        created_at=datetime.now(UTC),
    )
    session.add(version_row)
    session.flush()

    for row in result.cleaned_rows:
        session.add(
            S2CleanedRowModel(
                cleaned_dataset_version_id=version_row.id,
                cleaned_row_identity_hash=row.cleaned_row_identity_hash,
                cleaned_row_content_hash=row.cleaned_row_content_hash,
                source_row_identity_hash=row.source_row_identity_hash,
                season_business_key=row.canonical_grain_key.season_business_key,
                farm_business_key=row.canonical_grain_key.farm_business_key,
                subfarm_business_key=row.canonical_grain_key.subfarm_business_key,
                variety_business_key=row.canonical_grain_key.variety_business_key,
                harvest_business_date=row.canonical_grain_key.harvest_business_date,
                cleaning_projection_version=row.cleaning_projection_version,
                cleaned_row_schema_version=row.cleaned_row_schema_version,
                cleaning_policy_version=row.cleaning_policy_version,
                correction_policy_version=row.correction_policy_version,
                exclusion_policy_version=row.exclusion_policy_version,
                source_actual_harvest_quantity_kg=(
                    None
                    if row.source_actual_harvest_quantity_kg is None
                    else str(row.source_actual_harvest_quantity_kg)
                ),
                effective_actual_harvest_quantity_kg=(
                    None
                    if row.effective_actual_harvest_quantity_kg is None
                    else str(row.effective_actual_harvest_quantity_kg)
                ),
                quantity_presence_status=row.quantity_presence_status.value,
                is_excluded=row.is_excluded,
            )
        )

    for finding in result.quality_findings:
        session.add(
            S2QualityFindingModel(
                cleaned_dataset_version_id=version_row.id,
                quality_finding_identity_hash=finding.quality_finding_identity_hash,
                source_row_identity_hash=finding.source_row_identity_hash,
                cleaned_row_identity_hash=finding.cleaned_row_identity_hash,
                quality_rule_id=finding.quality_rule_id,
                quality_rule_version=finding.quality_rule_version,
                observed_field=finding.observed_field,
                finding_code=finding.finding_code.value,
                severity=finding.severity.value,
                normalized_observed_value_identity=finding.normalized_observed_value_identity,
                rule_definition_hash=finding.rule_definition_hash,
                validation_run_identity=finding.validation_run_identity,
            )
        )

    for entry in result.correction_ledger_entries:
        session.add(
            S2CorrectionLedgerEntryModel(
                cleaned_dataset_version_id=version_row.id,
                correction_ledger_entry_identity_hash=entry.correction_ledger_entry_identity_hash,
                source_row_identity_hash=entry.source_row_identity_hash,
                correction_event_id=entry.correction_event_id,
                field_name=entry.field_name,
                correction_policy_version=entry.correction_policy_version,
                correction_schema_version=entry.correction_schema_version,
                quality_finding_identity_hash=entry.quality_finding_identity_hash,
                original_value_digest=entry.original_value_digest,
                corrected_value_digest=entry.corrected_value_digest,
                reason=entry.reason,
                manual_actor_or_authority_reference=entry.manual_actor_or_authority_reference,
            )
        )

    for entry in result.exclusion_ledger_entries:
        session.add(
            S2ExclusionLedgerEntryModel(
                cleaned_dataset_version_id=version_row.id,
                exclusion_ledger_entry_identity_hash=entry.exclusion_ledger_entry_identity_hash,
                source_row_identity_hash=entry.source_row_identity_hash,
                exclusion_event_id=entry.exclusion_event_id,
                exclusion_code=entry.exclusion_code.value,
                exclusion_policy_version=entry.exclusion_policy_version,
                exclusion_schema_version=entry.exclusion_schema_version,
                quality_finding_identity_hash=entry.quality_finding_identity_hash,
                exclusion_reason_reference=entry.exclusion_reason_reference,
                decision_authority_reference=entry.decision_authority_reference,
            )
        )

    session.flush()
    return version_row
