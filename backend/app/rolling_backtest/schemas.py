from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Annotated, Final, Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.rolling_backtest.enums import (
    AvailabilityRuleKind,
    AvailabilitySourceType,
    DefaultNodeKey,
    EvaluationStatus,
    ExecutionMode,
    ForecastStatus,
    ScopeMode,
    Task10ModelPolicy,
    UpstreamSelectionMode,
)


class _BaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DefaultRollingNodeDate(_BaseModel):
    node_key: DefaultNodeKey
    as_of_local_date: date
    forecast_start_local_date: date


class ScopeSelector(_BaseModel):
    mode: ScopeMode
    ids: tuple[int, ...] = ()

    @field_validator("ids")
    @classmethod
    def _normalize_ids(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if any(item <= 0 for item in value):
            raise ValueError("scope ids must contain positive integers")
        if len(set(value)) != len(value):
            raise ValueError("scope ids must not contain duplicates")
        return tuple(sorted(value))

    @model_validator(mode="after")
    def _validate_mode(self) -> Self:
        if self.mode == ScopeMode.ALL and self.ids:
            raise ValueError("scope ids must be empty when mode=all")
        if self.mode == ScopeMode.INCLUDE_IDS and not self.ids:
            raise ValueError("scope ids must be non-empty when mode=include_ids")
        return self


class RollingNodeScope(_BaseModel):
    destination_factory_ids: ScopeSelector
    farm_ids: ScopeSelector = Field(default_factory=lambda: ScopeSelector(mode=ScopeMode.ALL))
    subfarm_ids: ScopeSelector = Field(default_factory=lambda: ScopeSelector(mode=ScopeMode.ALL))
    variety_ids: ScopeSelector = Field(default_factory=lambda: ScopeSelector(mode=ScopeMode.ALL))

    @model_validator(mode="after")
    def _validate_destination_scope(self) -> Self:
        if self.destination_factory_ids.mode != ScopeMode.INCLUDE_IDS:
            raise ValueError("destination_factory_ids must use mode=include_ids")
        return self


class PersistentUpstreamReference(_BaseModel):
    reference_type: Literal["database_run_id", "database_artifact_id", "database_row_id", "uuid"]
    reference_value: int | str

    @field_validator("reference_value")
    @classmethod
    def _validate_reference_value(cls, value: int | str) -> int | str:
        if isinstance(value, int):
            if value <= 0:
                raise ValueError("persistent reference id must be positive")
            return value
        if not value:
            raise ValueError("persistent reference value must be non-empty")
        return value


class UpstreamSemanticIdentityPayload(_BaseModel):
    schema_version: str = Field(min_length=1)
    display_label: str = Field(min_length=1)
    semantic_payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_signature: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    config_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    result_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    canonical_payload_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    artifact_payload_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    business_version: str | None = Field(default=None, min_length=1)
    policy_version: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _require_stable_identity(self) -> Self:
        if not any(
            (
                self.input_signature,
                self.config_hash,
                self.result_hash,
                self.canonical_payload_hash,
                self.artifact_payload_hash,
            )
        ):
            raise ValueError("semantic identity payload must include at least one stable hash")
        return self


class ResolvedUpstreamSemanticIdentity(_BaseModel):
    source_type: AvailabilitySourceType
    source_role: str = Field(min_length=1)
    role_qualifier: str | None = Field(default=None, min_length=1)
    semantic: UpstreamSemanticIdentityPayload
    persistent_reference: PersistentUpstreamReference | None = None


class HistoricalAvailableModelIdentity(_BaseModel):
    policy: Literal[Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL]
    training_run_semantic_identity: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_semantic_identities: tuple[str, ...] = Field(min_length=1)
    authority_visibility_identity: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("artifact_semantic_identities")
    @classmethod
    def _normalize_artifact_semantic_identities(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        if any(not item or len(item) != 64 for item in value):
            raise ValueError("artifact semantic identities must be 64-char hashes")
        if len(set(value)) != len(value):
            raise ValueError("artifact semantic identities must not contain duplicates")
        return tuple(sorted(value))


class ReplayTrainedModelIdentity(_BaseModel):
    policy: Literal[Task10ModelPolicy.REPLAY_TRAINED_MODEL]
    training_cutoff_at: datetime
    allowed_training_season_ids: tuple[int, ...]
    validation_policy_version: str = Field(min_length=1)
    label_visibility_policy_version: str = Field(min_length=1)
    feature_visibility_policy_version: str = Field(min_length=1)
    artifact_visibility_policy_version: str = Field(min_length=1)
    training_manifest_semantic_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    # ── TASK-012 Slice B additions (§6 identity model) ────────────────────
    # The two hash fields below are required for canonical replay-trained
    # identity per design §6 line 132-133. They default to ``None`` so
    # existing Slice A contract-test call sites (which only construct
    # the schema-level identity without populating Slice B hashes)
    # continue to work; :meth:`is_canonical` enforces that the canonical
    # projection (per §6 line 141) requires non-empty hashes, and
    # :meth:`_validate_slice_b_hash` rejects malformed non-empty values.
    model_config_hash: str | None = Field(default=None)
    model_artifact_hash: str | None = Field(default=None)
    model_code_version: str = Field(default="", min_length=0)
    task12_policy_version: str = Field(default="", min_length=0)

    @field_validator("training_cutoff_at")
    @classmethod
    def _validate_training_cutoff(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("training_cutoff_at must be timezone-aware")
        return value

    @field_validator("allowed_training_season_ids")
    @classmethod
    def _normalize_training_season_ids(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if not value:
            raise ValueError("allowed_training_season_ids must be non-empty")
        if any(item <= 0 for item in value):
            raise ValueError("allowed_training_season_ids must contain positive integers")
        if len(set(value)) != len(value):
            raise ValueError("allowed_training_season_ids must not contain duplicates")
        return tuple(sorted(value))

    @field_validator("model_config_hash", "model_artifact_hash")
    @classmethod
    def _validate_slice_b_hash(cls, value: str | None) -> str | None:
        # Slice B adds these as Optional fields; existing Slice A callers
        # leave them None. A non-None value MUST be a 64-char lowercase
        # hex string per design §6 line 132-133. Empty string is rejected
        # here (callers wanting "absent" must pass None).
        if value is None:
            return None
        if len(value) != 64 or not all(c in "0123456789abcdef" for c in value):
            raise ValueError(
                "Slice B hash must be a 64-char lowercase hex string (design §6 line 132-133)"
            )
        return value

    def is_canonical(self) -> bool:
        """Design §6 line 141: "not canonical unless all identity fields
        are present and all hash fields are non-empty".

        Returns True iff every Slice B hash field is a non-empty 64-hex
        string AND every Slice B identity string is non-empty.
        """
        hash_fields = (
            self.training_manifest_semantic_hash,
            self.model_config_hash,
            self.model_artifact_hash,
        )
        if any(not h or len(h) != 64 for h in hash_fields):
            return False
        identity_fields = (self.model_code_version, self.task12_policy_version)
        return all(bool(v) for v in identity_fields)


ResolvedTask10ModelPolicy = Annotated[
    HistoricalAvailableModelIdentity | ReplayTrainedModelIdentity,
    Field(discriminator="policy"),
]


class RollingNodeDefinition(_BaseModel):
    season_id: int = Field(gt=0)
    node_key: DefaultNodeKey
    as_of_local_date: date
    forecast_cutoff_at: datetime
    forecast_start_local_date: date
    forecast_end_local_date: date
    scope: RollingNodeScope
    upstream_selection_mode: UpstreamSelectionMode
    forecast_horizon_policy_version: str = Field(min_length=1)
    timezone: str = Field(min_length=1)
    task10_model_policy: ResolvedTask10ModelPolicy
    resolved_upstream_semantic_identities: tuple[ResolvedUpstreamSemanticIdentity, ...] = ()

    @field_validator("forecast_cutoff_at")
    @classmethod
    def _validate_cutoff(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("forecast_cutoff_at must be timezone-aware")
        return value

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
    def _sort_and_validate_semantic_identities(
        cls,
        value: tuple[ResolvedUpstreamSemanticIdentity, ...],
    ) -> tuple[ResolvedUpstreamSemanticIdentity, ...]:
        exact_keys: set[tuple[object, ...]] = set()
        role_keys: dict[tuple[str, str | None], ResolvedUpstreamSemanticIdentity] = {}
        semantic_keys: dict[
            tuple[AvailabilitySourceType, str, str | None, str],
            ResolvedUpstreamSemanticIdentity,
        ] = {}

        for item in value:
            role_key = (item.source_role, item.role_qualifier)
            role_owner = role_keys.get(role_key)
            if role_owner is not None:
                if role_owner == item:
                    raise ValueError("exact duplicate semantic identity is not allowed")
                if role_owner.semantic.display_label == item.semantic.display_label:
                    raise ValueError("conflicting semantic identity is not allowed")
                raise ValueError("duplicate source role is not allowed")
            role_keys[role_key] = item

            semantic_key = (
                item.source_type,
                item.source_role,
                item.role_qualifier,
                item.semantic.display_label,
            )
            semantic_owner = semantic_keys.get(semantic_key)
            if semantic_owner is not None and semantic_owner.semantic != item.semantic:
                raise ValueError("conflicting semantic identity is not allowed")
            semantic_keys[semantic_key] = item

            exact_key = (
                item.source_type.value,
                item.source_role,
                item.role_qualifier,
                item.semantic.model_dump_json(),
                item.persistent_reference.model_dump_json()
                if item.persistent_reference is not None
                else None,
            )
            if exact_key in exact_keys:
                raise ValueError("exact duplicate semantic identity is not allowed")
            exact_keys.add(exact_key)

        return tuple(
            sorted(
                value,
                key=lambda item: (
                    item.source_role,
                    item.role_qualifier or "",
                    item.source_type.value,
                    item.semantic.display_label,
                    item.semantic.semantic_payload_hash,
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
        expected_day = {
            DefaultNodeKey.FEBRUARY_END: (date(self.season_id, 3, 1) - timedelta(days=1)),
            DefaultNodeKey.MARCH_15: date(self.season_id, 3, 15),
            DefaultNodeKey.MARCH_31: date(self.season_id, 3, 31),
            DefaultNodeKey.APRIL_07: date(self.season_id, 4, 7),
        }[self.node_key]
        if self.as_of_local_date != expected_day:
            raise ValueError("node_key must match season_id and as_of_local_date")
        return self

    @model_validator(mode="after")
    def _validate_task10_policy_cutoff(self) -> Self:
        if self.task10_model_policy.policy == Task10ModelPolicy.REPLAY_TRAINED_MODEL:
            from backend.app.rolling_backtest.schemas import ReplayTrainedModelIdentity

            if not isinstance(self.task10_model_policy, ReplayTrainedModelIdentity):
                raise ValueError("replay_trained_model policy expected ReplayTrainedModelIdentity")
            if self.task10_model_policy.training_cutoff_at > self.forecast_cutoff_at:
                raise ValueError(
                    "replay training_cutoff_at must not be after node forecast_cutoff_at"
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
    execution_mode: ExecutionMode
    calendar_phase_policy_version: str = Field(min_length=1)
    cutoff_policy_version: str = Field(min_length=1)
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
                    item.season_id,
                    item.as_of_local_date,
                    item.node_key.value,
                    item.forecast_end_local_date,
                ),
            )
        )
        node_keys = [(item.season_id, item.node_key.value) for item in ordered]
        if len(set(node_keys)) != len(node_keys):
            raise ValueError("duplicate (season_id, node_key) is not allowed")
        node_dates = [(item.season_id, item.as_of_local_date) for item in ordered]
        if len(set(node_dates)) != len(node_dates):
            raise ValueError("duplicate resolved node date is not allowed within a season")
        return ordered

    @model_validator(mode="after")
    def _validate_nodes_against_run_policy(self) -> Self:
        for node in self.nodes:
            if node.forecast_horizon_policy_version != self.forecast_horizon_policy_version:
                raise ValueError(
                    "node forecast_horizon_policy_version must match run policy version"
                )
            if node.timezone != self.cutoff_timezone:
                raise ValueError("node timezone must match run cutoff timezone")
            local_cutoff = node.forecast_cutoff_at.astimezone(ZoneInfo(self.cutoff_timezone))
            if local_cutoff.date() != node.as_of_local_date:
                raise ValueError("forecast_cutoff_at local date must match as_of_local_date")
            if local_cutoff.timetz().replace(tzinfo=None) != self.cutoff_local_time:
                raise ValueError("forecast_cutoff_at local time must match cutoff_local_time")
            if (
                self.execution_mode == ExecutionMode.HISTORICAL_OBSERVED
                and node.task10_model_policy.policy
                != Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL
            ):
                raise ValueError("historical_observed nodes must use historically_available_model")
        return self


# V0.2-S2 historical binding contract.  These models intentionally carry
# business-key scope and immutable authority identities, not database lookup
# ids.  They are the input boundary for the runner; no S3 metric is part of
# this contract.
S2_CONTRACT_VERSION: Final = "v0.2-s2-historical-binding-v1"
S2_ALLOWED_HORIZONS_DAYS = (7, 14, 21)
S2_LABEL_VISIBILITY_MODES = ("AS_OF_EVALUATION", "FINAL_ADJUDICATED")


class S2HistoricalBacktestRequest(_BaseModel):
    s2_contract_version: Literal["v0.2-s2-historical-binding-v1"] = S2_CONTRACT_VERSION
    season_business_keys: tuple[str, ...] = Field(min_length=1)
    farm_business_keys: tuple[str, ...] = Field(min_length=1)
    subfarm_business_keys: tuple[str, ...] = Field(min_length=1)
    variety_business_keys: tuple[str, ...] = Field(min_length=1)
    master_identity_resolver_version: str = Field(min_length=1)
    mapping_policy_version: str = Field(min_length=1)
    resolved_identity_snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_selection_policy_version: str = Field(min_length=1)
    single_node_identity_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    forecast_cutoff_at: datetime
    label_observation_cutoff_at: datetime | None = None
    label_visibility_mode: Literal["AS_OF_EVALUATION", "FINAL_ADJUDICATED"]
    requested_horizons_days: tuple[int, ...] = Field(min_length=1)

    @field_validator(
        "season_business_keys",
        "farm_business_keys",
        "subfarm_business_keys",
        "variety_business_keys",
        mode="before",
    )
    @classmethod
    def _canonicalize_business_keys(cls, value: object) -> tuple[str, ...]:
        if not isinstance(value, (tuple, list)):
            raise ValueError("business-key scope must be a list or tuple")
        normalized = tuple(sorted(str(item).strip() for item in value))
        if not normalized or any(not item for item in normalized):
            raise ValueError("business-key scope must contain non-empty values")
        if len(set(normalized)) != len(normalized):
            raise ValueError("business-key scope must not contain duplicates")
        return normalized

    @field_validator("forecast_cutoff_at", "label_observation_cutoff_at")
    @classmethod
    def _require_aware_cutoff(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("cutoff timestamps must be timezone-aware")
        return value

    @field_validator("requested_horizons_days", mode="before")
    @classmethod
    def _normalize_horizons(cls, value: object) -> tuple[int, ...]:
        if not isinstance(value, (tuple, list)):
            raise ValueError("requested_horizons_days must be a list or tuple")
        horizons = tuple(int(item) for item in value)
        if not horizons:
            raise ValueError("requested_horizons_days must not be empty")
        if len(set(horizons)) != len(horizons):
            raise ValueError("requested_horizons_days must not contain duplicates")
        if any(item not in S2_ALLOWED_HORIZONS_DAYS for item in horizons):
            raise ValueError("requested_horizons_days must be a subset of 7, 14, 21")
        return tuple(sorted(horizons))

    @model_validator(mode="after")
    def _validate_visibility_cutoff(self) -> Self:
        if self.label_visibility_mode == "AS_OF_EVALUATION":
            if self.label_observation_cutoff_at is None:
                raise ValueError("AS_OF_EVALUATION requires label_observation_cutoff_at")
        elif self.label_observation_cutoff_at is not None:
            raise ValueError("FINAL_ADJUDICATED requires null label_observation_cutoff_at")
        return self


class S2ForecastAuthorityBundle(_BaseModel):
    forecast_run_identity_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    daily_row_identity_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    task9_authority_identity_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    task10_authority_identity_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    forecast_code_identity: str = Field(min_length=1)
    model_identity: str = Field(min_length=1)
    parameter_identity: str = Field(min_length=1)
    data_identity: str = Field(min_length=1)
    available_at: datetime

    @field_validator("available_at")
    @classmethod
    def _require_aware_availability(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("forecast authority available_at must be timezone-aware")
        return value


class S2ActualLabelAuthority(_BaseModel):
    label_snapshot_identity_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_identity_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    observed_weight_kg: Decimal = Field(ge=Decimal("0"))
    visibility_timestamp: datetime | None = None
    physical_alignment_status: Literal["VERIFIED", "UNVERIFIED"]

    @field_validator("visibility_timestamp")
    @classmethod
    def _require_aware_visibility(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("label visibility_timestamp must be timezone-aware")
        return value


class S2HistoricalBindingCandidate(_BaseModel):
    horizon_days: int
    target_date: date
    forecast_cutoff_at: datetime
    forecast_value_kg: Decimal = Field(ge=Decimal("0"))
    forecast_authority: S2ForecastAuthorityBundle
    actual_label: S2ActualLabelAuthority | None = None

    @field_validator("horizon_days")
    @classmethod
    def _validate_horizon(cls, value: int) -> int:
        if value not in S2_ALLOWED_HORIZONS_DAYS:
            raise ValueError("horizon_days must be one of 7, 14, 21")
        return value

    @field_validator("forecast_cutoff_at")
    @classmethod
    def _require_aware_forecast_cutoff(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("candidate forecast_cutoff_at must be timezone-aware")
        return value


class S2HistoricalBindingRow(_BaseModel):
    horizon_days: int
    target_date: date
    forecast_cutoff_at: datetime
    label_observation_cutoff_at: datetime | None
    label_visibility_mode: Literal["AS_OF_EVALUATION", "FINAL_ADJUDICATED"]
    forecast_value_kg: Decimal = Field(ge=Decimal("0"))
    actual_value_kg: Decimal | None = Field(default=None, ge=Decimal("0"))
    forecast_authority: S2ForecastAuthorityBundle
    actual_label: S2ActualLabelAuthority | None = None
    physical_alignment_status: str
    row_status: Literal["COMPARABLE", "EXCLUDED", "NOT_COMPUTABLE"]
    reason_code: str | None = None
    row_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("horizon_days")
    @classmethod
    def _validate_row_horizon(cls, value: int) -> int:
        if value not in S2_ALLOWED_HORIZONS_DAYS:
            raise ValueError("binding horizon must be one of 7, 14, 21")
        return value

    @model_validator(mode="after")
    def _validate_row_semantics(self) -> Self:
        if self.row_status == "COMPARABLE":
            if self.actual_label is None or self.actual_value_kg is None:
                raise ValueError("comparable row requires an actual label")
            if self.physical_alignment_status != "VERIFIED":
                raise ValueError("comparable row requires verified physical alignment")
            if self.reason_code is not None:
                raise ValueError("comparable row cannot have an exclusion reason")
        elif self.reason_code is None:
            raise ValueError("excluded or not-computable row requires a reason code")
        if (
            self.actual_label is not None
            and self.actual_value_kg != self.actual_label.observed_weight_kg
        ):
            raise ValueError("actual_value_kg must equal the persisted label authority value")
        return self


class Task3SourceVisibilityIdentity(_BaseModel):
    visibility_policy_version: str = Field(min_length=1)
    source_max_raw_id: int = Field(gt=0)
    aggregation_version: str = Field(min_length=1)
    config_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    visibility_manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    visible_through_at: datetime

    @field_validator("visible_through_at")
    @classmethod
    def _validate_visible_through_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("visible_through_at must be timezone-aware")
        return value


class AvailabilityAuthoritySpec(_BaseModel):
    source_type: AvailabilitySourceType
    rule_kind: AvailabilityRuleKind
    required_statuses: tuple[str, ...]
    authoritative_timestamp_field: str | None = Field(default=None, min_length=1)
    available_on_local_date_field: str | None = Field(default=None, min_length=1)
    observation_date_field: str | None = Field(default=None, min_length=1)
    task3_source_visibility_field: str | None = Field(default=None, min_length=1)
    parent_authority_required: bool
    local_date_policy_version: str | None = Field(default=None, min_length=1)
    source_visibility_policy_version: str | None = Field(default=None, min_length=1)


class ParentAuthorityIdentity(_BaseModel):
    """Typed parent-run authority with stable semantic binding.

    Status and timestamp alone are insufficient — the child must bind to a
    stable, auditable parent semantic identity.
    """

    source_type: AvailabilitySourceType
    authority_schema_version: str = Field(min_length=1)
    authority_policy_version: str = Field(min_length=1)
    authority_timestamp: datetime
    authority_status: str
    semantic_input_signature: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    result_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    canonical_payload_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    persistent_reference: PersistentUpstreamReference | None = None

    @field_validator("authority_timestamp")
    @classmethod
    def _validate_authority_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("authority_timestamp must be timezone-aware")
        return value

    @model_validator(mode="after")
    def _require_stable_parent_identity(self) -> Self:
        if not any(
            (
                self.semantic_input_signature,
                self.result_hash,
                self.canonical_payload_hash,
            )
        ):
            raise ValueError("parent authority identity must include at least one stable hash")
        return self


class _BaseAvailabilitySnapshot(_BaseModel):
    """Base for all source-specific availability snapshots."""


class Task3AnalyticsBuildAvailabilitySnapshot(_BaseAvailabilitySnapshot):
    source_type: Literal[AvailabilitySourceType.TASK3_ANALYTICS_BUILD]
    status: str
    authoritative_timestamp: datetime
    task3_source_visibility: Task3SourceVisibilityIdentity | None = None

    @field_validator("authoritative_timestamp")
    @classmethod
    def _validate_authoritative_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("authoritative_timestamp must be timezone-aware")
        return value


class Task6PlanVersionAvailabilitySnapshot(_BaseAvailabilitySnapshot):
    source_type: Literal[AvailabilitySourceType.TASK6_PLAN_VERSION]
    available_at: date
    effective_interval_version: str = Field(min_length=1)


class Task7WeatherObservationAvailabilitySnapshot(_BaseAvailabilitySnapshot):
    source_type: Literal[AvailabilitySourceType.TASK7_WEATHER_OBSERVATION]
    available_at: date
    observation_date: date


class Task8ModelRunAvailabilitySnapshot(_BaseAvailabilitySnapshot):
    source_type: Literal[AvailabilitySourceType.TASK8_MODEL_RUN]
    status: str
    authoritative_timestamp: datetime

    @field_validator("authoritative_timestamp")
    @classmethod
    def _validate_authoritative_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("authoritative_timestamp must be timezone-aware")
        return value


class Task8ModelArtifactAvailabilitySnapshot(_BaseAvailabilitySnapshot):
    source_type: Literal[AvailabilitySourceType.TASK8_MODEL_ARTIFACT]
    created_at: datetime
    parent_authority: ParentAuthorityIdentity

    @field_validator("created_at")
    @classmethod
    def _validate_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value

    @field_validator("parent_authority")
    @classmethod
    def _validate_parent_type(cls, value: ParentAuthorityIdentity) -> ParentAuthorityIdentity:
        if value.source_type != AvailabilitySourceType.TASK8_MODEL_RUN:
            raise ValueError("Task 8 model artifact parent must be a Task 8 model run authority")
        return value


class Task8ForecastRunAvailabilitySnapshot(_BaseAvailabilitySnapshot):
    source_type: Literal[AvailabilitySourceType.TASK8_FORECAST_RUN]
    status: str
    authoritative_timestamp: datetime

    @field_validator("authoritative_timestamp")
    @classmethod
    def _validate_authoritative_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("authoritative_timestamp must be timezone-aware")
        return value


class Task8DailyPredictionAvailabilitySnapshot(_BaseAvailabilitySnapshot):
    source_type: Literal[AvailabilitySourceType.TASK8_DAILY_PREDICTION]
    prediction_date: date
    created_at: datetime
    parent_authority: ParentAuthorityIdentity

    @field_validator("created_at")
    @classmethod
    def _validate_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value

    @field_validator("parent_authority")
    @classmethod
    def _validate_parent_type(cls, value: ParentAuthorityIdentity) -> ParentAuthorityIdentity:
        if value.source_type != AvailabilitySourceType.TASK8_FORECAST_RUN:
            raise ValueError(
                "Task 8 daily prediction parent must be a Task 8 forecast run authority"
            )
        return value


class Task9HarvestStateRunAvailabilitySnapshot(_BaseAvailabilitySnapshot):
    source_type: Literal[AvailabilitySourceType.TASK9_HARVEST_STATE_RUN]
    status: str
    authoritative_timestamp: datetime

    @field_validator("authoritative_timestamp")
    @classmethod
    def _validate_authoritative_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("authoritative_timestamp must be timezone-aware")
        return value


class Task10TrainingRunAvailabilitySnapshot(_BaseAvailabilitySnapshot):
    source_type: Literal[AvailabilitySourceType.TASK10_TRAINING_RUN]
    status: str
    authoritative_timestamp: datetime

    @field_validator("authoritative_timestamp")
    @classmethod
    def _validate_authoritative_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("authoritative_timestamp must be timezone-aware")
        return value


class Task10ModelArtifactAvailabilitySnapshot(_BaseAvailabilitySnapshot):
    source_type: Literal[AvailabilitySourceType.TASK10_MODEL_ARTIFACT]
    created_at: datetime
    parent_authority: ParentAuthorityIdentity

    @field_validator("created_at")
    @classmethod
    def _validate_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value

    @field_validator("parent_authority")
    @classmethod
    def _validate_parent_type(cls, value: ParentAuthorityIdentity) -> ParentAuthorityIdentity:
        if value.source_type != AvailabilitySourceType.TASK10_TRAINING_RUN:
            raise ValueError(
                "Task 10 model artifact parent must be a Task 10 training run authority"
            )
        return value


class Task10PredictionRunAvailabilitySnapshot(_BaseAvailabilitySnapshot):
    source_type: Literal[AvailabilitySourceType.TASK10_PREDICTION_RUN]
    status: str
    authoritative_timestamp: datetime

    @field_validator("authoritative_timestamp")
    @classmethod
    def _validate_authoritative_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("authoritative_timestamp must be timezone-aware")
        return value


AvailabilitySnapshot = Annotated[
    Task3AnalyticsBuildAvailabilitySnapshot
    | Task6PlanVersionAvailabilitySnapshot
    | Task7WeatherObservationAvailabilitySnapshot
    | Task8ModelRunAvailabilitySnapshot
    | Task8ModelArtifactAvailabilitySnapshot
    | Task8ForecastRunAvailabilitySnapshot
    | Task8DailyPredictionAvailabilitySnapshot
    | Task9HarvestStateRunAvailabilitySnapshot
    | Task10TrainingRunAvailabilitySnapshot
    | Task10ModelArtifactAvailabilitySnapshot
    | Task10PredictionRunAvailabilitySnapshot,
    Field(discriminator="source_type"),
]


class AvailabilityAuthorityEvaluationResult(_BaseModel):
    allowed: bool
    blocker_code: str | None = None


class NodeStateSnapshot(_BaseModel):
    forecast_status: ForecastStatus
    evaluation_status: EvaluationStatus
