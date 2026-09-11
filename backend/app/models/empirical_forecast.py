from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class EmpiricalMaturityAuthority(Base):
    __tablename__ = "empirical_maturity_authority"
    authority_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EmpiricalForecastRun(Base):
    __tablename__ = "empirical_forecast_run"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    authority_hash: Mapped[str] = mapped_column(
        ForeignKey("empirical_maturity_authority.authority_hash"), nullable=False
    )
    task9_run_id: Mapped[int] = mapped_column(ForeignKey("harvest_state_run.id"), nullable=False)
    result_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
