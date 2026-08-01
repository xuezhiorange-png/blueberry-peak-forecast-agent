"""Persisted authority and public Trial resource ownership bindings."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.actual_harvest_import.models import UTCDateTime
from backend.app.db.base import Base

_BIGINT_VARIANT = BigInteger().with_variant(Integer(), "sqlite")
_JSON_VARIANT = JSON().with_variant(JSONB(), "postgresql")
TRIAL_FORECAST_EVIDENCE_SCHEMA_VERSION = "v0.2-trial-forecast-evidence-v1"


def _sha256_checks(column: str, name: str) -> tuple[CheckConstraint, CheckConstraint]:
    return (
        CheckConstraint(
            f"length({column}) = 64 AND {column} NOT GLOB '*[^0-9a-f]*'",
            name=name,
        ).ddl_if(dialect="sqlite"),
        CheckConstraint(
            f"{column} ~ '^[0-9a-f]{{64}}$'",
            name=name,
        ).ddl_if(dialect="postgresql"),
    )


def _non_empty(column: str, name: str) -> CheckConstraint:
    return CheckConstraint(f"length(trim({column})) > 0", name=name)


class CoreForecastMarketablePolicyModel(Base):
    """A point-in-time marketable-retention policy header."""

    __tablename__ = "core_forecast_marketable_policy"
    __table_args__ = (
        *_sha256_checks("public_policy_hash", "ck_core_forecast_policy_public_hash"),
        *_sha256_checks("row_set_hash", "ck_core_forecast_policy_row_set_hash"),
        CheckConstraint("id > 0", name="ck_core_forecast_policy_id_positive"),
        _non_empty("policy_version", "ck_core_forecast_policy_version_nonempty"),
        _non_empty("source_system", "ck_core_forecast_policy_source_nonempty"),
        _non_empty("source_record_key", "ck_core_forecast_policy_record_key_nonempty"),
        CheckConstraint("season_id > 0", name="ck_core_forecast_policy_season_positive"),
        CheckConstraint("factory_id > 0", name="ck_core_forecast_policy_factory_positive"),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_core_forecast_policy_date_range",
        ),
        CheckConstraint("status IN ('ACTIVE', 'RETIRED')", name="ck_core_forecast_policy_status"),
        UniqueConstraint("public_policy_hash", name="uq_core_forecast_policy_public_hash"),
        Index(
            "ix_core_forecast_policy_season_factory_status",
            "season_id",
            "factory_id",
            "status",
        ),
        Index("ix_core_forecast_policy_available_at", "available_at"),
        Index(
            "ix_core_forecast_policy_effective_range",
            "effective_from",
            "effective_to",
        ),
    )

    id: Mapped[int] = mapped_column(_BIGINT_VARIANT, primary_key=True, autoincrement=True)
    public_policy_hash: Mapped[str] = mapped_column(Text, nullable=False)
    policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    season_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey("dim_season.id", name="fk_core_forecast_policy_season", ondelete="RESTRICT"),
        nullable=False,
    )
    factory_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey("dim_factory.id", name="fk_core_forecast_policy_factory", ondelete="RESTRICT"),
        nullable=False,
    )
    source_system: Mapped[str] = mapped_column(Text, nullable=False)
    source_record_key: Mapped[str] = mapped_column(Text, nullable=False)
    available_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    row_set_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=func.now()
    )


class CoreForecastMarketablePolicyEntryModel(Base):
    """One farm/subfarm/variety row in a persisted policy snapshot."""

    __tablename__ = "core_forecast_marketable_policy_entry"
    __table_args__ = (
        *_sha256_checks("row_hash", "ck_core_forecast_policy_entry_row_hash"),
        CheckConstraint("id > 0", name="ck_core_forecast_policy_entry_id_positive"),
        _non_empty("source_version", "ck_core_forecast_policy_entry_source_version"),
        CheckConstraint("policy_id > 0", name="ck_core_forecast_policy_entry_policy_positive"),
        CheckConstraint("farm_id > 0", name="ck_core_forecast_policy_entry_farm_positive"),
        CheckConstraint("subfarm_id > 0", name="ck_core_forecast_policy_entry_subfarm_positive"),
        CheckConstraint("variety_id > 0", name="ck_core_forecast_policy_entry_variety_positive"),
        CheckConstraint(
            "sorting_retention_rate >= 0 AND sorting_retention_rate <= 1",
            name="ck_core_forecast_policy_entry_sorting_rate",
        ),
        CheckConstraint(
            "postharvest_retention_rate >= 0 AND postharvest_retention_rate <= 1",
            name="ck_core_forecast_policy_entry_postharvest_rate",
        ),
        UniqueConstraint(
            "policy_id",
            "farm_id",
            "subfarm_id",
            "variety_id",
            name="uq_core_forecast_policy_entry_scope",
        ),
        UniqueConstraint("row_hash", name="uq_core_forecast_policy_entry_row_hash"),
        Index("ix_core_forecast_policy_entry_policy_id", "policy_id"),
        Index("ix_core_forecast_policy_entry_scope", "farm_id", "subfarm_id", "variety_id"),
    )

    id: Mapped[int] = mapped_column(_BIGINT_VARIANT, primary_key=True, autoincrement=True)
    policy_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey(
            "core_forecast_marketable_policy.id",
            name="fk_core_forecast_policy_entry_policy",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    farm_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey("dim_farm.id", name="fk_core_forecast_policy_entry_farm", ondelete="RESTRICT"),
        nullable=False,
    )
    subfarm_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey(
            "dim_subfarm.id", name="fk_core_forecast_policy_entry_subfarm", ondelete="RESTRICT"
        ),
        nullable=False,
    )
    variety_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey(
            "dim_variety.id", name="fk_core_forecast_policy_entry_variety", ondelete="RESTRICT"
        ),
        nullable=False,
    )
    sorting_retention_rate: Mapped[Decimal] = mapped_column(Numeric(24, 6), nullable=False)
    postharvest_retention_rate: Mapped[Decimal] = mapped_column(Numeric(24, 6), nullable=False)
    source_version: Mapped[str] = mapped_column(Text, nullable=False)
    row_hash: Mapped[str] = mapped_column(Text, nullable=False)


class TrialResourceBindingModel(Base):
    """Immutable public ownership and lineage binding for a Trial resource."""

    __tablename__ = "trial_resource_binding"
    __table_args__ = (
        *_sha256_checks("public_resource_id", "ck_trial_binding_public_resource_id"),
        *_sha256_checks("business_scope_hash", "ck_trial_binding_scope_hash"),
        *_sha256_checks("parent_forecast_public_id", "ck_trial_binding_parent_forecast_id"),
        CheckConstraint("id > 0", name="ck_trial_binding_id_positive"),
        CheckConstraint(
            "resource_kind IN ('FORECAST', 'QUALITY_REPORT')",
            name="ck_trial_binding_resource_kind",
        ),
        _non_empty("owner_identity", "ck_trial_binding_owner_nonempty"),
        CheckConstraint(
            "parent_import_id IS NULL OR length(trim(parent_import_id)) > 0",
            name="ck_trial_binding_parent_import_nonempty",
        ),
        CheckConstraint(
            "(resource_kind = 'FORECAST' AND parent_forecast_public_id IS NULL "
            "AND parent_import_id IS NULL) OR "
            "(resource_kind = 'QUALITY_REPORT' AND parent_forecast_public_id IS NOT NULL "
            "AND parent_import_id IS NOT NULL)",
            name="ck_trial_binding_parent_coupling",
        ),
        UniqueConstraint(
            "resource_kind",
            "public_resource_id",
            name="uq_trial_binding_resource_identity",
        ),
        Index(
            "ix_trial_binding_scoped_resource",
            "resource_kind",
            "public_resource_id",
            "owner_identity",
        ),
        Index("ix_trial_binding_owner_kind", "owner_identity", "resource_kind"),
        Index("ix_trial_binding_parent_forecast", "parent_forecast_public_id"),
        Index("ix_trial_binding_parent_import", "parent_import_id"),
    )

    id: Mapped[int] = mapped_column(_BIGINT_VARIANT, primary_key=True, autoincrement=True)
    resource_kind: Mapped[str] = mapped_column(Text, nullable=False)
    public_resource_id: Mapped[str] = mapped_column(Text, nullable=False)
    owner_identity: Mapped[str] = mapped_column(Text, nullable=False)
    business_scope_hash: Mapped[str] = mapped_column(Text, nullable=False)
    parent_forecast_public_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_import_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey(
            "actual_harvest_import_batch.import_id",
            name="fk_trial_binding_parent_import",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=func.now()
    )


class TrialForecastEvidenceModel(Base):
    """Immutable creation-time evidence for one public Core Forecast request."""

    __tablename__ = "trial_forecast_evidence"
    __table_args__ = (
        *_sha256_checks("public_forecast_id", "ck_trial_forecast_evidence_public_id"),
        *_sha256_checks(
            "forecast_input_authority_hash",
            "ck_trial_forecast_evidence_authority_hash",
        ),
        *_sha256_checks("plan_row_hash", "ck_trial_forecast_evidence_plan_row_hash"),
        *_sha256_checks("business_scope_hash", "ck_trial_forecast_evidence_scope_hash"),
        *_sha256_checks(
            "forecast_evidence_hash",
            "ck_trial_forecast_evidence_evidence_hash",
        ),
        CheckConstraint(
            f"evidence_schema_version = '{TRIAL_FORECAST_EVIDENCE_SCHEMA_VERSION}'",
            name="ck_trial_forecast_evidence_schema_version",
        ),
        CheckConstraint("id > 0", name="ck_trial_forecast_evidence_id_positive"),
        _non_empty("farm_business_key", "ck_trial_forecast_evidence_farm_nonempty"),
        CheckConstraint(
            "subfarm_business_key_or_null IS NULL OR "
            "length(trim(subfarm_business_key_or_null)) > 0",
            name="ck_trial_forecast_evidence_subfarm_nonempty",
        ),
        _non_empty("season_business_key", "ck_trial_forecast_evidence_season_nonempty"),
        _non_empty("variety_business_key", "ck_trial_forecast_evidence_variety_nonempty"),
        _non_empty(
            "destination_factory_business_key",
            "ck_trial_forecast_evidence_factory_nonempty",
        ),
        _non_empty("plan_version", "ck_trial_forecast_evidence_plan_version_nonempty"),
        CheckConstraint(
            "planting_area_mu >= 0",
            name="ck_trial_forecast_evidence_planting_area_nonnegative",
        ),
        UniqueConstraint(
            "public_forecast_id",
            name="uq_trial_forecast_evidence_public_forecast_id",
        ),
        UniqueConstraint(
            "forecast_evidence_hash",
            name="uq_trial_forecast_evidence_evidence_hash",
        ),
        Index(
            "ix_trial_forecast_evidence_business_scope_hash",
            "business_scope_hash",
        ),
        Index(
            "ix_trial_forecast_evidence_authority_hash",
            "forecast_input_authority_hash",
        ),
        Index("ix_trial_forecast_evidence_plan_row_hash", "plan_row_hash"),
    )

    id: Mapped[int] = mapped_column(_BIGINT_VARIANT, primary_key=True, autoincrement=True)
    evidence_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    public_forecast_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "core_forecast_run.request_hash",
            name="fk_trial_forecast_evidence_public_forecast",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    forecast_input_authority_hash: Mapped[str] = mapped_column(Text, nullable=False)
    authority_available_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    farm_business_key: Mapped[str] = mapped_column(Text, nullable=False)
    subfarm_business_key_or_null: Mapped[str | None] = mapped_column(Text, nullable=True)
    season_business_key: Mapped[str] = mapped_column(Text, nullable=False)
    variety_business_key: Mapped[str] = mapped_column(Text, nullable=False)
    destination_factory_business_key: Mapped[str] = mapped_column(Text, nullable=False)
    plan_version: Mapped[str] = mapped_column(Text, nullable=False)
    plan_row_hash: Mapped[str] = mapped_column(Text, nullable=False)
    planting_area_mu: Mapped[Decimal] = mapped_column(Numeric(24, 6), nullable=False)
    business_scope_hash: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_payload: Mapped[dict[str, object]] = mapped_column(
        _JSON_VARIANT,
        nullable=False,
    )
    forecast_evidence_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=func.now()
    )
