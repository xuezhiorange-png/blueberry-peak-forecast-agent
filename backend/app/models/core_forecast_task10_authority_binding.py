"""Immutable persisted Task 10 authority binding for a Core forecast run."""

from __future__ import annotations

from datetime import datetime

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

_BIGINT_VARIANT = BigInteger().with_variant(Integer(), "sqlite")


def _sha256_check(name: str, column: str) -> tuple[CheckConstraint, CheckConstraint]:
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


class CoreForecastTask10AuthorityBindingModel(Base):
    """Authority evidence binding one Core forecast run to one Task 10 prediction run."""

    __tablename__ = "core_forecast_task10_authority_binding"
    __table_args__ = (
        UniqueConstraint(
            "core_forecast_run_id",
            name="uq_core_forecast_task10_authority_binding_core_run",
        ),
        *_sha256_check(
            "ck_core_forecast_task10_authority_binding_task9_result_hash",
            "task9_result_hash",
        ),
        *_sha256_check(
            "ck_core_forecast_task10_authority_binding_identity_hash",
            "binding_identity_hash",
        ),
        CheckConstraint("core_forecast_run_id > 0", name="ck_core_forecast_task10_binding_core"),
        CheckConstraint("task9_run_id > 0", name="ck_core_forecast_task10_binding_task9"),
        CheckConstraint(
            "task10_prediction_run_id > 0",
            name="ck_core_forecast_task10_binding_task10",
        ),
        Index(
            "ix_core_forecast_task10_authority_binding_task10_prediction_run_id",
            "task10_prediction_run_id",
        ),
    )

    id: Mapped[int] = mapped_column(_BIGINT_VARIANT, primary_key=True, autoincrement=True)
    core_forecast_run_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey(
            "core_forecast_run.id",
            name="fk_core_forecast_task10_authority_binding_core_run_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    task9_run_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey(
            "harvest_state_run.id",
            name="fk_core_forecast_task10_authority_binding_task9_run_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    task9_result_hash: Mapped[str] = mapped_column(Text, nullable=False)
    task10_prediction_run_id: Mapped[int] = mapped_column(
        _BIGINT_VARIANT,
        ForeignKey(
            "residual_model_prediction_run.id",
            name="fk_core_forecast_task10_authority_binding_task10_run_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    binding_identity_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
