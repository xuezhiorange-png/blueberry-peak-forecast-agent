"""Two append-only shadow forecast tables; not a production model registry."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.actual_harvest_import.models import UTCDateTime
from backend.app.db.base import Base
from backend.app.db.types import ExactDecimal


class RollingRun(Base):
    __tablename__ = "rolling_forecast_run"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    principal_id: Mapped[str] = mapped_column(String(200))
    context_reference: Mapped[str] = mapped_column(String(200))
    base_id: Mapped[str] = mapped_column(String(200))
    target_season: Mapped[str] = mapped_column(String(9))
    origin_date: Mapped[date] = mapped_column(Date)
    origin_cutoff_at: Mapped[datetime] = mapped_column(UTCDateTime())
    input_hash: Mapped[str] = mapped_column(String(64))
    result_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
    issued_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    rerun_of_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("rolling_forecast_run.id", ondelete="RESTRICT"), nullable=True
    )
    __table_args__ = (
        UniqueConstraint("principal_id", "input_hash", name="uq_rolling_run_idempotency"),
        CheckConstraint("status IN ('COMPUTED','PARTIAL','BLOCKED')", name="ck_rolling_run_status"),
        Index(
            "ix_rolling_run_discovery", "principal_id", "base_id", "target_season", "origin_date"
        ),
    )


class RollingDaily(Base):
    __tablename__ = "rolling_forecast_daily"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("rolling_forecast_run.id", ondelete="RESTRICT"))
    model: Mapped[str] = mapped_column(String(2))
    target_date: Mapped[date] = mapped_column(Date)
    quantity_kg: Mapped[Decimal] = mapped_column(ExactDecimal())
    __table_args__ = (
        UniqueConstraint("run_id", "model", "target_date", name="uq_rolling_daily_target"),
        CheckConstraint("model IN ('M0','M1')", name="ck_rolling_daily_model"),
        CheckConstraint("quantity_kg >= 0", name="ck_rolling_daily_nonnegative"),
    )
