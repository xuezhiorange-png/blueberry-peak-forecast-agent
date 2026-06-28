from __future__ import annotations

from datetime import date, datetime, time
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
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base

_JSON_VARIANT = JSONB(astext_type=Text())


def _sha256_check_sql(column_name: str) -> str:
    stripped = column_name
    for char in "0123456789abcdef":
        stripped = f"replace({stripped}, '{char}', '')"
    return (
        f"length({column_name}) = 64 and lower({column_name}) = {column_name} and {stripped} = ''"
    )


def _nullable_sha256_check_sql(column_name: str) -> str:
    stripped = column_name
    for char in "0123456789abcdef":
        stripped = f"replace({stripped}, '{char}', '')"
    return (
        f"({column_name} IS NULL) OR "
        f"(length({column_name}) = 64 "
        f"and lower({column_name}) = {column_name} "
        f"and {stripped} = '')"
    )


class RollingBacktestRun(Base):
    __tablename__ = "rolling_backtest_run"
    __table_args__ = (
        UniqueConstraint("run_signature", name="uq_rolling_backtest_run_signature"),
        CheckConstraint(
            _sha256_check_sql("run_signature"),
            name="ck_rolling_backtest_run_signature_sha256",
        ),
        CheckConstraint(
            _sha256_check_sql("config_hash"),
            name="ck_rolling_backtest_run_config_hash_sha256",
        ),
        CheckConstraint(
            _sha256_check_sql("canonical_payload_hash"),
            name="ck_rolling_backtest_run_canonical_payload_hash_sha256",
        ),
        CheckConstraint(
            "execution_mode in ('historical_observed', 'retrospective_replay')",
            name="ck_rolling_backtest_run_execution_mode",
        ),
        CheckConstraint(
            "status in ('pending', 'running', 'forecast_completed', "
            "'partially_completed', 'completed', 'blocked', 'failed')",
            name="ck_rolling_backtest_run_status",
        ),
        CheckConstraint(
            "expected_node_count >= 1",
            name="ck_rolling_backtest_run_expected_node_count",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_signature: Mapped[str] = mapped_column(Text, nullable=False)
    config_hash: Mapped[str] = mapped_column(Text, nullable=False)
    execution_mode: Mapped[str] = mapped_column(Text, nullable=False)
    rolling_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_serialization_version: Mapped[str] = mapped_column(Text, nullable=False)
    availability_registry_version: Mapped[str] = mapped_column(Text, nullable=False)
    node_calendar_version: Mapped[str] = mapped_column(Text, nullable=False)
    forecast_horizon_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    upstream_selection_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    metric_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    calendar_phase_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    cutoff_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    cutoff_timezone: Mapped[str] = mapped_column(Text, nullable=False)
    cutoff_local_time: Mapped[time] = mapped_column(Time, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    expected_node_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    canonical_payload: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)
    canonical_payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class RollingBacktestNode(Base):
    __tablename__ = "rolling_backtest_node"
    __table_args__ = (
        UniqueConstraint(
            "rolling_run_id",
            "season_id",
            "node_key",
            name="uq_rolling_backtest_node_business_key",
        ),
        UniqueConstraint(
            "rolling_run_id",
            "node_signature",
            name="uq_rolling_backtest_node_signature",
        ),
        CheckConstraint(
            _sha256_check_sql("node_signature"),
            name="ck_rolling_backtest_node_signature_sha256",
        ),
        CheckConstraint(
            _sha256_check_sql("canonical_payload_hash"),
            name="ck_rolling_backtest_node_canonical_payload_hash_sha256",
        ),
        CheckConstraint(
            "execution_mode in ('historical_observed', 'retrospective_replay')",
            name="ck_rolling_backtest_node_execution_mode",
        ),
        CheckConstraint(
            "upstream_selection_mode in ('pinned', 'historical_resolution')",
            name="ck_rolling_backtest_node_upstream_selection_mode",
        ),
        CheckConstraint(
            "forecast_end_local_date >= forecast_start_local_date",
            name="ck_rolling_backtest_node_forecast_date_range",
        ),
        CheckConstraint("season_id > 0", name="ck_rolling_backtest_node_season_positive"),
        CheckConstraint(
            "expected_resolved_input_count >= 0",
            name="ck_rolling_backtest_node_expected_input_count_non_negative",
        ),
        CheckConstraint(
            "expected_availability_audit_count >= 0",
            name="ck_rolling_backtest_node_expected_audit_count_non_negative",
        ),
        Index("ix_rolling_backtest_node_run_id", "rolling_run_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rolling_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "rolling_backtest_run.id",
            name="fk_rolling_backtest_node_run_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    season_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    node_key: Mapped[str] = mapped_column(Text, nullable=False)
    node_signature: Mapped[str] = mapped_column(Text, nullable=False)
    as_of_local_date: Mapped[date] = mapped_column(Date, nullable=False)
    forecast_cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    forecast_start_local_date: Mapped[date] = mapped_column(Date, nullable=False)
    forecast_end_local_date: Mapped[date] = mapped_column(Date, nullable=False)
    execution_mode: Mapped[str] = mapped_column(Text, nullable=False)
    upstream_selection_mode: Mapped[str] = mapped_column(Text, nullable=False)
    task10_model_policy: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)
    canonical_payload: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)
    canonical_payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    expected_resolved_input_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expected_availability_audit_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RollingBacktestAttempt(Base):
    __tablename__ = "rolling_backtest_attempt"
    __table_args__ = (
        UniqueConstraint(
            "rolling_run_id",
            "attempt_number",
            name="uq_rolling_backtest_attempt_number",
        ),
        CheckConstraint(
            "status in ('pending', 'running', 'forecast_completed', "
            "'partially_completed', 'completed', 'blocked', 'failed')",
            name="ck_rolling_backtest_attempt_status",
        ),
        CheckConstraint(
            "attempt_number >= 1",
            name="ck_rolling_backtest_attempt_number_positive",
        ),
        CheckConstraint(
            "(status in ('pending', 'running')) = (finished_at IS NULL)",
            name="ck_rolling_backtest_attempt_terminal_time",
        ),
        Index("ix_rolling_backtest_attempt_run_id", "rolling_run_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rolling_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "rolling_backtest_run.id",
            name="fk_rolling_backtest_attempt_run_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    prior_attempt_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "rolling_backtest_attempt.id",
            name="fk_rolling_backtest_attempt_prior_id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    current_stage: Mapped[str] = mapped_column(Text, nullable=False)
    structured_error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    sanitized_diagnostics: Mapped[dict[str, Any] | None] = mapped_column(
        _JSON_VARIANT, nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    runtime_environment_identity: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RollingBacktestResolvedInput(Base):
    __tablename__ = "rolling_backtest_resolved_input"
    __table_args__ = (
        UniqueConstraint(
            "rolling_node_id",
            "source_role",
            name="uq_rolling_backtest_resolved_input_source_role",
        ),
        CheckConstraint(
            _sha256_check_sql("audit_hash"),
            name="ck_rolling_backtest_resolved_input_audit_hash_sha256",
        ),
        CheckConstraint(
            _nullable_sha256_check_sql("semantic_input_signature"),
            name="ck_rolling_backtest_resolved_input_semantic_sig_sha256",
        ),
        CheckConstraint(
            _nullable_sha256_check_sql("result_hash"),
            name="ck_rolling_backtest_resolved_input_result_hash_sha256",
        ),
        CheckConstraint(
            _nullable_sha256_check_sql("canonical_payload_hash"),
            name="ck_rolling_backtest_resolved_input_canonical_hash_sha256",
        ),
        CheckConstraint(
            "(persistent_reference_type IS NULL) = (persistent_reference_value IS NULL)",
            name="ck_rolling_backtest_resolved_input_persistent_ref_pairing",
        ),
        Index("ix_rolling_backtest_resolved_input_node_id", "rolling_node_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rolling_node_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "rolling_backtest_node.id",
            name="fk_rolling_backtest_resolved_input_node_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    source_role: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    semantic_input_signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_payload_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    policy_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    persistent_reference_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    persistent_reference_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_payload: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)
    audit_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RollingBacktestAvailabilityAudit(Base):
    __tablename__ = "rolling_backtest_availability_audit"
    __table_args__ = (
        UniqueConstraint(
            "rolling_node_id",
            "source_role",
            name="uq_rolling_backtest_availability_audit_source_role",
        ),
        CheckConstraint(
            _sha256_check_sql("audit_hash"),
            name="ck_rolling_backtest_availability_audit_hash_sha256",
        ),
        CheckConstraint(
            "(allowed = true AND blocker_code IS NULL) OR "
            "(allowed = false AND blocker_code IS NOT NULL)",
            name="ck_rolling_backtest_audit_consistency",
        ),
        Index("ix_rolling_backtest_availability_audit_node_id", "rolling_node_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rolling_node_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "rolling_backtest_node.id",
            name="fk_rolling_backtest_availability_audit_node_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    source_role: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    blocker_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_payload: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)
    audit_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RollingBacktestDagSnapshot(Base):
    __tablename__ = "rolling_backtest_dag_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "rolling_node_id",
            name="uq_rolling_backtest_dag_snapshot_node_id",
        ),
        CheckConstraint(
            _sha256_check_sql("canonical_payload_hash"),
            name="ck_rolling_backtest_dag_snapshot_payload_hash_sha256",
        ),
        CheckConstraint(
            "expected_node_count >= 0",
            name="ck_rolling_backtest_dag_snapshot_node_count_non_negative",
        ),
        CheckConstraint(
            "expected_edge_count >= 0",
            name="ck_rolling_backtest_dag_snapshot_edge_count_non_negative",
        ),
        Index("ix_rolling_backtest_dag_snapshot_node_id", "rolling_node_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rolling_node_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "rolling_backtest_node.id",
            name="fk_rolling_backtest_dag_snapshot_node_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    dag_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    dag_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_payload: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False)
    canonical_payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    expected_node_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expected_edge_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
