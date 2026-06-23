from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
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
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class FarmSeasonVarietyPlan(Base):
    __tablename__ = "farm_season_variety_plan"
    __table_args__ = (
        CheckConstraint(
            "planted_area_mu >= 0",
            name="ck_farm_season_variety_plan_planted_area_non_negative",
        ),
        CheckConstraint(
            "expected_yield_kg_per_mu >= 0",
            name="ck_farm_season_variety_plan_expected_yield_non_negative",
        ),
        CheckConstraint(
            "marketable_rate >= 0 and marketable_rate <= 1",
            name="ck_farm_season_variety_plan_marketable_rate_range",
        ),
        CheckConstraint(
            "expected_total_marketable_kg is null or expected_total_marketable_kg >= 0",
            name="ck_farm_season_variety_plan_expected_total_non_negative",
        ),
        CheckConstraint(
            "tree_age_years is null or tree_age_years >= 0",
            name="ck_farm_season_variety_plan_tree_age_non_negative",
        ),
        CheckConstraint(
            "version > 0",
            name="ck_farm_season_variety_plan_version_positive",
        ),
        CheckConstraint(
            "effective_to is null or effective_to > effective_from",
            name="ck_farm_season_variety_plan_effective_range",
        ),
        CheckConstraint(
            "flowering_start_date is null or flowering_peak_date is null "
            "or flowering_start_date <= flowering_peak_date",
            name="ck_farm_season_variety_plan_flowering_start_peak",
        ),
        CheckConstraint(
            "flowering_peak_date is null or flowering_end_date is null "
            "or flowering_peak_date <= flowering_end_date",
            name="ck_farm_season_variety_plan_flowering_peak_end",
        ),
        UniqueConstraint(
            "row_hash",
            name="uq_farm_season_variety_plan_row_hash",
        ),
        Index(
            "uq_farm_season_variety_plan_version_null_subfarm",
            "farm_id",
            "season_id",
            "variety_id",
            "version",
            unique=True,
            postgresql_where=text("subfarm_id is null"),
            sqlite_where=text("subfarm_id is null"),
        ),
        Index(
            "uq_farm_season_variety_plan_version_with_subfarm",
            "farm_id",
            "subfarm_id",
            "season_id",
            "variety_id",
            "version",
            unique=True,
            postgresql_where=text("subfarm_id is not null"),
            sqlite_where=text("subfarm_id is not null"),
        ),
        Index(
            "ix_farm_season_variety_plan_business_key",
            "farm_id",
            "season_id",
            "variety_id",
        ),
        Index(
            "ix_farm_season_variety_plan_subfarm_id",
            "subfarm_id",
        ),
        Index(
            "ix_farm_season_variety_plan_effective_from",
            "effective_from",
        ),
        Index(
            "ix_farm_season_variety_plan_effective_to",
            "effective_to",
        ),
        Index(
            "ix_farm_season_variety_plan_available_at",
            "available_at",
        ),
        Index(
            "ix_farm_season_variety_plan_row_hash",
            "row_hash",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    farm_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("dim_farm.id", name="fk_farm_plan_farm_id_dim_farm", ondelete="RESTRICT"),
        nullable=False,
    )
    subfarm_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "dim_subfarm.id",
            name="fk_farm_plan_subfarm_id_dim_subfarm",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    season_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("dim_season.id", name="fk_farm_plan_season_id_dim_season", ondelete="RESTRICT"),
        nullable=False,
    )
    variety_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "dim_variety.id",
            name="fk_farm_plan_variety_id_dim_variety",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    planted_area_mu: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    expected_yield_kg_per_mu: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    marketable_rate: Mapped[Decimal] = mapped_column(Numeric(12, 10), nullable=False)
    tree_age_years: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    pruning_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    flowering_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    flowering_peak_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    flowering_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    first_pick_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_total_marketable_kg: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6),
        nullable=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    available_at: Mapped[date] = mapped_column(Date, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    row_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        server_onupdate=func.now(),
    )


class ProductionPlanImportRun(Base):
    __tablename__ = "production_plan_import_run"
    __table_args__ = (
        CheckConstraint(
            "status in ('running', 'completed', 'failed')",
            name="ck_production_plan_import_run_status",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    file_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    source_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    row_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    inserted_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    skipped_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    rejected_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    duplicate_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    unknown_farm_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    unknown_subfarm_count: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default="0",
    )
    unknown_season_count: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default="0",
    )
    unknown_variety_count: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default="0",
    )
    invalid_date_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    invalid_numeric_count: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default="0",
    )
    overlap_conflict_count: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default="0",
    )
    version_conflict_count: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default="0",
    )
    report_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
