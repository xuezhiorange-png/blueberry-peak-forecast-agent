from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base
from backend.app.models.master_data import Factory, Season, Variety


class AnalyticsBuildRun(Base):
    __tablename__ = "analytics_build_run"
    __table_args__ = (
        CheckConstraint(
            "status in ('running', 'completed', 'failed')",
            name="ck_analytics_build_run_status",
        ),
        Index("ix_analytics_build_run_season_id", "season_id"),
        Index("ix_analytics_build_run_status", "status"),
        Index("ix_analytics_build_run_source_max_raw_id", "source_max_raw_id"),
        Index(
            "ux_analytics_build_run_active_or_completed",
            "season_id",
            "aggregation_version",
            "source_max_raw_id",
            "config_hash",
            unique=True,
            postgresql_where=text("status in ('running', 'completed')"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    season_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "dim_season.id",
            name="fk_analytics_build_run_season_id_dim_season",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    aggregation_version: Mapped[str] = mapped_column(Text, nullable=False)
    source_max_raw_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    config_hash: Mapped[str] = mapped_column(Text, nullable=False)
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    source_eligible_row_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    source_eligible_weight_kg: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, server_default="0"
    )
    daily_fact_row_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    season: Mapped[Season] = relationship(lazy="raise")
    daily_facts: Mapped[list["FactReceiptDaily"]] = relationship(
        back_populates="build_run",
        lazy="raise",
    )
    peak_metrics: Mapped[list["FactorySeasonPeakMetric"]] = relationship(
        back_populates="build_run",
        lazy="raise",
    )


class FactReceiptDaily(Base):
    __tablename__ = "fact_receipt_daily"
    __table_args__ = (
        UniqueConstraint(
            "build_run_id",
            "season_id",
            "receipt_date",
            "factory_id",
            "farm_key",
            "subfarm_key",
            "variety_id",
            name="uq_fact_receipt_daily_build_grain",
        ),
        CheckConstraint("weight_kg > 0", name="ck_fact_receipt_daily_weight_positive"),
        CheckConstraint(
            "source_row_count > 0",
            name="ck_fact_receipt_daily_source_row_count_positive",
        ),
        Index("ix_fact_receipt_daily_build_run_id", "build_run_id"),
        Index("ix_fact_receipt_daily_season_id", "season_id"),
        Index("ix_fact_receipt_daily_factory_id", "factory_id"),
        Index("ix_fact_receipt_daily_receipt_date", "receipt_date"),
        Index(
            "ix_fact_receipt_daily_season_factory_date",
            "season_id",
            "factory_id",
            "receipt_date",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    build_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "analytics_build_run.id",
            name="fk_fact_receipt_daily_build_run_id_analytics_build_run",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    season_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "dim_season.id",
            name="fk_fact_receipt_daily_season_id_dim_season",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    receipt_date: Mapped[date] = mapped_column(Date, nullable=False)
    factory_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "dim_factory.id",
            name="fk_fact_receipt_daily_factory_id_dim_factory",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    farm_key: Mapped[str] = mapped_column(Text, nullable=False)
    subfarm_key: Mapped[str] = mapped_column(Text, nullable=False)
    variety_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "dim_variety.id",
            name="fk_fact_receipt_daily_variety_id_dim_variety",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    source_row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    holiday_codes: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    is_spring_festival: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    build_run: Mapped[AnalyticsBuildRun] = relationship(back_populates="daily_facts", lazy="raise")
    season: Mapped[Season] = relationship(lazy="raise")
    factory: Mapped[Factory] = relationship(lazy="raise")
    variety: Mapped[Variety] = relationship(lazy="raise")


class FactorySeasonPeakMetric(Base):
    __tablename__ = "factory_season_peak_metric"
    __table_args__ = (
        UniqueConstraint(
            "build_run_id",
            "factory_id",
            name="uq_factory_season_peak_metric_build_run_id_factory_id",
        ),
        CheckConstraint("total_weight_kg > 0", name="ck_factory_peak_total_weight_positive"),
        CheckConstraint(
            "calendar_day_count >= observed_day_count and observed_day_count >= 0",
            name="ck_factory_peak_observed_day_count",
        ),
        CheckConstraint(
            "peak_concentration >= 0 and peak_concentration <= 1",
            name="ck_factory_peak_peak_concentration_range",
        ),
        CheckConstraint(
            "variety_hhi >= 0 and variety_hhi <= 1",
            name="ck_factory_peak_variety_hhi_range",
        ),
        CheckConstraint(
            "farm_hhi >= 0 and farm_hhi <= 1",
            name="ck_factory_peak_farm_hhi_range",
        ),
        CheckConstraint(
            "subfarm_hhi >= 0 and subfarm_hhi <= 1",
            name="ck_factory_peak_subfarm_hhi_range",
        ),
        CheckConstraint(
            "unknown_farm_weight_share >= 0 and unknown_farm_weight_share <= 1",
            name="ck_factory_peak_unknown_farm_share_range",
        ),
        CheckConstraint(
            "unknown_subfarm_weight_share >= 0 and unknown_subfarm_weight_share <= 1",
            name="ck_factory_peak_unknown_subfarm_share_range",
        ),
        Index("ix_factory_season_peak_metric_build_run_id", "build_run_id"),
        Index("ix_factory_season_peak_metric_season_id", "season_id"),
        Index("ix_factory_season_peak_metric_factory_id", "factory_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    build_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "analytics_build_run.id",
            name="fk_factory_season_peak_metric_build_run_id_analytics_build_run",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    season_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "dim_season.id",
            name="fk_factory_season_peak_metric_season_id_dim_season",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    factory_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "dim_factory.id",
            name="fk_factory_season_peak_metric_factory_id_dim_factory",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    analysis_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    analysis_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    calendar_day_count: Mapped[int] = mapped_column(Integer, nullable=False)
    observed_day_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_weight_kg: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    single_day_peak_kg: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    single_day_peak_date: Mapped[date] = mapped_column(Date, nullable=False)
    stable_median_3d_peak_kg: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    stable_median_3d_peak_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    mean_3d_peak_kg: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    mean_3d_peak_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    peak_concentration: Mapped[Decimal] = mapped_column(Numeric(12, 10), nullable=False)
    variety_hhi: Mapped[Decimal] = mapped_column(Numeric(12, 10), nullable=False)
    farm_hhi: Mapped[Decimal] = mapped_column(Numeric(12, 10), nullable=False)
    subfarm_hhi: Mapped[Decimal] = mapped_column(Numeric(12, 10), nullable=False)
    unknown_farm_weight_share: Mapped[Decimal] = mapped_column(Numeric(12, 10), nullable=False)
    unknown_subfarm_weight_share: Mapped[Decimal] = mapped_column(Numeric(12, 10), nullable=False)
    spring_festival_day_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    build_run: Mapped[AnalyticsBuildRun] = relationship(
        back_populates="peak_metrics",
        lazy="raise",
    )
    season: Mapped[Season] = relationship(lazy="raise")
    factory: Mapped[Factory] = relationship(lazy="raise")
