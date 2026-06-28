from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.rolling_backtest.enums import (
    AvailabilitySourceType,
    DefaultNodeKey,
    EvaluationStatus,
    ExecutionMode,
    ForecastStatus,
    UpstreamSelectionMode,
)


class _BaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DefaultRollingNodeDate(_BaseModel):
    node_key: DefaultNodeKey
    as_of_local_date: date
    forecast_start_local_date: date


class ResolvedUpstreamSemanticIdentity(_BaseModel):
    source_type: AvailabilitySourceType
    semantic_identity: str = Field(min_length=1)
    payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class RollingNodeDefinition(_BaseModel):
    season_id: int = Field(gt=0)
    node_key: DefaultNodeKey
    as_of_local_date: date
    forecast_cutoff_at: datetime
    forecast_start_local_date: date
    forecast_end_local_date: date
    destination_factory_ids: tuple[int, ...]
    execution_mode: ExecutionMode
    upstream_selection_mode: UpstreamSelectionMode
    forecast_horizon_policy_version: str = Field(min_length=1)
    timezone: str = Field(min_length=1)
    resolved_upstream_semantic_identities: tuple[ResolvedUpstreamSemanticIdentity, ...] = ()

    @field_validator("forecast_cutoff_at")
    @classmethod
    def _validate_cutoff(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("forecast_cutoff_at must be timezone-aware")
        return value

    @field_validator("destination_factory_ids")
    @classmethod
    def _normalize_factory_ids(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if not value:
            raise ValueError("destination_factory_ids must be non-empty")
        if any(item <= 0 for item in value):
            raise ValueError("destination_factory_ids must contain positive integers")
        if len(set(value)) != len(value):
            raise ValueError("destination_factory_ids must not contain duplicates")
        return tuple(sorted(value))

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unsupported timezone: {value}") from exc
        return value

    @field_validator("resolved_upstream_semantic_identities")
    @classmethod
    def _sort_semantic_identities(
        cls,
        value: tuple[ResolvedUpstreamSemanticIdentity, ...],
    ) -> tuple[ResolvedUpstreamSemanticIdentity, ...]:
        return tuple(
            sorted(
                value,
                key=lambda item: (
                    item.source_type.value,
                    item.semantic_identity,
                    item.payload_hash,
                ),
            )
        )

    @model_validator(mode="after")
    def _validate_dates(self) -> Self:
        expected_start = self.as_of_local_date + timedelta(days=1)
        if self.forecast_start_local_date != expected_start:
            raise ValueError("forecast_start_local_date must equal as_of_local_date + 1 day")
        if self.forecast_end_local_date < self.forecast_start_local_date:
            raise ValueError(
                "forecast_end_local_date must be on or after forecast_start_local_date"
            )
        return self


class RollingBacktestConfig(_BaseModel):
    rolling_schema_version: str = Field(min_length=1)
    canonical_serialization_version: str = Field(min_length=1)
    availability_registry_version: str = Field(min_length=1)
    node_calendar_version: str = Field(min_length=1)
    forecast_horizon_policy_version: str = Field(min_length=1)
    upstream_selection_policy_version: str = Field(min_length=1)
    metric_policy_version: str = Field(min_length=1)
    task10_model_policy: str = Field(min_length=1)
    calendar_phase_policy_version: str = Field(min_length=1)
    cutoff_timezone: str = Field(min_length=1)
    cutoff_local_time: time
    nodes: tuple[RollingNodeDefinition, ...]

    @field_validator("cutoff_timezone")
    @classmethod
    def _validate_cutoff_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unsupported timezone: {value}") from exc
        return value

    @field_validator("nodes")
    @classmethod
    def _normalize_nodes(
        cls,
        value: tuple[RollingNodeDefinition, ...],
    ) -> tuple[RollingNodeDefinition, ...]:
        if not value:
            raise ValueError("nodes must be non-empty")
        ordered = tuple(
            sorted(
                value,
                key=lambda item: (
                    item.as_of_local_date,
                    item.node_key.value,
                    item.forecast_end_local_date,
                ),
            )
        )
        node_keys = [item.node_key.value for item in ordered]
        if len(set(node_keys)) != len(node_keys):
            raise ValueError("duplicate node_key is not allowed")
        node_dates = [item.as_of_local_date for item in ordered]
        if len(set(node_dates)) != len(node_dates):
            raise ValueError("duplicate resolved node date is not allowed")
        return ordered


class AvailabilityAuthoritySpec(_BaseModel):
    source_type: AvailabilitySourceType
    required_statuses: tuple[str, ...]
    authoritative_timestamp_field: str = Field(min_length=1)
    parent_authority_required: bool
    observation_date_field: str | None = None
    source_cutoff_field: str | None = None
    historical_observed_rule: str = Field(min_length=1)
    retrospective_replay_rule: str = Field(min_length=1)


class AvailabilityAuthoritySnapshot(_BaseModel):
    source_type: AvailabilitySourceType
    status: str
    authoritative_timestamp: datetime | None = None
    observation_date: date | None = None
    source_cutoff_at: datetime | None = None
    parent_authority_valid: bool = True

    @field_validator("authoritative_timestamp", "source_cutoff_at")
    @classmethod
    def _validate_optional_aware_datetime(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timezone-aware datetime is required")
        return value


class AvailabilityAuthorityEvaluationResult(_BaseModel):
    allowed: bool
    blocker_code: str | None = None


class NodeStateSnapshot(_BaseModel):
    forecast_status: ForecastStatus
    evaluation_status: EvaluationStatus
