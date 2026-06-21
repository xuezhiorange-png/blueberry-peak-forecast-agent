from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base
from backend.app.models.master_data import Factory, Season


class BaselineBacktestRun(Base):
    __tablename__ = "baseline_backtest_run"
    __table_args__ = (
        CheckConstraint(
            "status in ('running', 'completed', 'failed')",
            name="ck_baseline_backtest_run_status",
        ),
        Index("ix_baseline_backtest_run_status", "status"),
        Index("ix_baseline_backtest_run_evaluation_scheme", "evaluation_scheme"),
        Index(
            "ux_baseline_backtest_run_active_or_completed",
            "model_version",
            "config_hash",
            "source_signature",
            "evaluation_scheme",
            unique=True,
            postgresql_where=text("status in ('running', 'completed')"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    model_version: Mapped[str] = mapped_column(Text, nullable=False)
    config_hash: Mapped[str] = mapped_column(Text, nullable=False)
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_signature: Mapped[str] = mapped_column(Text, nullable=False)
    source_build_runs: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    evaluation_scheme: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    random_seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    result_row_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    results: Mapped[list["BaselineBacktestResult"]] = relationship(
        back_populates="run",
        lazy="raise",
    )


class BaselineBacktestResult(Base):
    __tablename__ = "baseline_backtest_result"
    __table_args__ = (
        CheckConstraint(
            "baseline_name in ("
            "'previous_season_peak',"
            "'volume_previous_concentration',"
            "'ridge_structure',"
            "'ridge_structure_factory_holdout'"
            ")",
            name="ck_baseline_backtest_result_baseline_name",
        ),
        CheckConstraint(
            "status in ('evaluated', 'excluded')",
            name="ck_baseline_backtest_result_status",
        ),
        UniqueConstraint(
            "run_id",
            "baseline_name",
            "target_season_id",
            "factory_id",
            "fold_key",
            name="uq_baseline_backtest_result_run_model_target_factory_fold",
        ),
        Index("ix_baseline_backtest_result_run_id", "run_id"),
        Index("ix_baseline_backtest_result_baseline_name", "baseline_name"),
        Index("ix_baseline_backtest_result_target_season_id", "target_season_id"),
        Index("ix_baseline_backtest_result_factory_id", "factory_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "baseline_backtest_run.id",
            name="fk_baseline_backtest_result_run_id_baseline_backtest_run",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    baseline_name: Mapped[str] = mapped_column(Text, nullable=False)
    target_season_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "dim_season.id",
            name="fk_baseline_backtest_result_target_season_id_dim_season",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    factory_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "dim_factory.id",
            name="fk_baseline_backtest_result_factory_id_dim_factory",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    previous_season_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "dim_season.id",
            name="fk_baseline_backtest_result_previous_season_id_dim_season",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    fold_key: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    actual_stable_peak_kg: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    predicted_stable_peak_kg: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    absolute_error_kg: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    signed_error_kg: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    ape: Mapped[Decimal | None] = mapped_column(Numeric(12, 10), nullable=True)
    input_features: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    training_season_codes: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    model_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    exclusion_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    run: Mapped[BaselineBacktestRun] = relationship(back_populates="results", lazy="raise")
    target_season: Mapped[Season] = relationship(
        foreign_keys=[target_season_id],
        lazy="raise",
    )
    previous_season: Mapped[Season | None] = relationship(
        foreign_keys=[previous_season_id],
        lazy="raise",
    )
    factory: Mapped[Factory] = relationship(lazy="raise")
