from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.harvest_state.canonical import (
    is_sha256_hex,
    make_holiday_calendar_hash,
    make_weather_rule_config_hash,
)
from backend.app.harvest_state.enums import (
    AuthorityFamily,
    AuthorityStatus,
    CapacityInputMode,
    CapacityPoolGrain,
    ForecastQuantile,
    WeatherCombinationMethod,
)
from backend.app.harvest_state.schemas import (
    NonNegativeBusinessDecimal,
    RatioDecimal,
    WeatherFeatureBand,
    WeatherFeatureRule,
)

Task9AuthorityStatus = AuthorityStatus
Task9AuthorityFamily = AuthorityFamily


class _AuthorityBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _require_non_blank(value: str, field_name: str) -> str:
    if value.strip() == "":
        raise ValueError(f"{field_name} must not be blank")
    return value


def _validate_sha256(value: str, field_name: str) -> str:
    if not is_sha256_hex(value):
        raise ValueError(f"{field_name} must be a lower-case SHA-256 hex digest")
    return value


def _validate_timezone_name(value: str) -> str:
    _require_non_blank(value, "timezone")
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("TIMEZONE_AUTHORITY_INVALID") from exc
    return value


class _AuthorityRowBase(_AuthorityBase):
    source_system: str = Field(min_length=1)
    source_record_key: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    row_hash: str = Field(min_length=64, max_length=64)

    @field_validator("source_system", "source_record_key", "source_version")
    @classmethod
    def _validate_non_blank(cls, value: str) -> str:
        return _require_non_blank(value, "text field")

    @field_validator("row_hash")
    @classmethod
    def _validate_row_hash(cls, value: str) -> str:
        return _validate_sha256(value, "row_hash")


class _LifecycleAuthorityRowBase(_AuthorityRowBase):
    status: AuthorityStatus
    status_changed_at: datetime
    available_at_local_date: date
    consumable_from_local_date: date | None = None
    consumable_to_local_date: date | None = None
    superseded_by_id: int | None = None

    @field_validator("status_changed_at")
    @classmethod
    def _validate_aware_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("status_changed_at must be timezone-aware")
        return value

    @field_validator("superseded_by_id")
    @classmethod
    def _validate_superseded_by_id(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("superseded_by_id must be > 0 when set")
        return value

    @model_validator(mode="after")
    def _validate_lifecycle_projection(self) -> _LifecycleAuthorityRowBase:
        if (
            self.status in {AuthorityStatus.DRAFT, AuthorityStatus.CANCELLED}
            and self.consumable_from_local_date is not None
        ):
            raise ValueError("draft/cancelled rows must not expose consumability")
        if (
            self.status in {AuthorityStatus.DRAFT, AuthorityStatus.CANCELLED}
            and self.consumable_to_local_date is not None
        ):
            raise ValueError("draft/cancelled rows must not expose consumability")
        if self.status is AuthorityStatus.ACTIVE:
            if self.consumable_from_local_date is None or self.consumable_to_local_date is not None:
                raise ValueError("active rows require open consumability interval")
        if self.status in {AuthorityStatus.SUPERSEDED, AuthorityStatus.RETIRED}:
            if self.consumable_from_local_date is None or self.consumable_to_local_date is None:
                raise ValueError("terminal lifecycle rows require closed consumability interval")
        if (
            self.consumable_from_local_date is not None
            and self.consumable_from_local_date < self.available_at_local_date
        ):
            raise ValueError("consumable_from_local_date must be >= available_at_local_date")
        if (
            self.consumable_to_local_date is not None
            and self.consumable_from_local_date is not None
            and self.consumable_to_local_date <= self.consumable_from_local_date
        ):
            raise ValueError("consumable_to_local_date must be > consumable_from_local_date")
        if self.status is AuthorityStatus.SUPERSEDED and self.superseded_by_id is None:
            raise ValueError("superseded rows require superseded_by_id")
        if self.status is not AuthorityStatus.SUPERSEDED and self.superseded_by_id is not None:
            raise ValueError("replacement id is only allowed for superseded rows")
        return self


class Task9CapacityPoolMemberSchema(_AuthorityBase):
    farm_id: int = Field(gt=0)
    subfarm_id: int | None = Field(default=None, gt=0)
    variety_id: int = Field(gt=0)


class Task9CapacityPoolDefinitionSchema(_LifecycleAuthorityRowBase):
    season_id: int = Field(gt=0)
    destination_factory_id: int = Field(gt=0)
    capacity_pool_code: str = Field(min_length=1)
    capacity_pool_grain: CapacityPoolGrain
    capacity_input_mode: CapacityInputMode
    capacity_pool_version: str = Field(min_length=1)
    revision: int = Field(gt=0)
    effective_from: date
    effective_to: date | None = None

    @field_validator("capacity_pool_code", "capacity_pool_version")
    @classmethod
    def _validate_identity_text(cls, value: str) -> str:
        return _require_non_blank(value, "identity text")

    @model_validator(mode="after")
    def _validate_effective_range(self) -> Task9CapacityPoolDefinitionSchema:
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must be >= effective_from")
        return self


class Task9DailyCapacityAuthoritySchema(_LifecycleAuthorityRowBase):
    capacity_pool_definition_id: int = Field(gt=0)
    season_id: int = Field(gt=0)
    destination_factory_id: int = Field(gt=0)
    capacity_pool_code: str = Field(min_length=1)
    capacity_pool_version: str = Field(min_length=1)
    capacity_pool_revision: int = Field(gt=0)
    capacity_date: date
    daily_capacity_revision: int = Field(gt=0)
    capacity_input_mode: CapacityInputMode
    planned_picker_count: NonNegativeBusinessDecimal | None = None
    kg_per_person_per_day: NonNegativeBusinessDecimal | None = None
    direct_nominal_capacity_kg_per_day: NonNegativeBusinessDecimal | None = None
    labor_availability_ratio: RatioDecimal
    operational_efficiency_ratio: RatioDecimal

    @field_validator("capacity_pool_code", "capacity_pool_version")
    @classmethod
    def _validate_daily_identity_text(cls, value: str) -> str:
        return _require_non_blank(value, "identity text")

    @model_validator(mode="after")
    def _validate_mode_fields(self) -> Task9DailyCapacityAuthoritySchema:
        if self.capacity_input_mode is CapacityInputMode.LABOR_DERIVED:
            if (
                self.planned_picker_count is None
                or self.kg_per_person_per_day is None
                or self.direct_nominal_capacity_kg_per_day is not None
                or self.labor_availability_ratio is None
                or self.operational_efficiency_ratio is None
            ):
                raise ValueError("LABOR_DERIVED fields are incomplete")
        if self.capacity_input_mode is CapacityInputMode.DIRECT_CAPACITY:
            if (
                self.direct_nominal_capacity_kg_per_day is None
                or self.planned_picker_count is not None
                or self.kg_per_person_per_day is not None
                or self.labor_availability_ratio is None
                or self.operational_efficiency_ratio is None
            ):
                raise ValueError("DIRECT_CAPACITY fields are incomplete")
        return self


class Task9HolidayCalendarDateSchema(_AuthorityBase):
    holiday_date: date
    holiday_code: str = Field(min_length=1)
    holiday_name: str = Field(min_length=1)

    @field_validator("holiday_code", "holiday_name")
    @classmethod
    def _validate_holiday_text(cls, value: str) -> str:
        return _require_non_blank(value, "holiday text")


class Task9HolidayCalendarVersionSchema(_LifecycleAuthorityRowBase):
    season_id: int = Field(gt=0)
    calendar_code: str = Field(min_length=1)
    calendar_version: str = Field(min_length=1)
    revision: int = Field(gt=0)
    calendar_hash: str = Field(min_length=64, max_length=64)
    region_scope: str | None = None
    lifecycle_timezone_name: str = Field(min_length=1)

    @field_validator("calendar_code", "calendar_version")
    @classmethod
    def _validate_calendar_text(cls, value: str) -> str:
        return _require_non_blank(value, "calendar text")

    @field_validator("calendar_hash")
    @classmethod
    def _validate_calendar_hash(cls, value: str) -> str:
        return _validate_sha256(value, "calendar_hash")

    @field_validator("lifecycle_timezone_name")
    @classmethod
    def _validate_calendar_timezone(cls, value: str) -> str:
        return _validate_timezone_name(value)


class Task9WeatherRuleConfigVersionSchema(_LifecycleAuthorityRowBase):
    rule_code: str = Field(min_length=1)
    rule_version: str = Field(min_length=1)
    revision: int = Field(gt=0)
    lifecycle_timezone_name: str = Field(min_length=1)
    combination_method: WeatherCombinationMethod
    minimum_ratio: RatioDecimal
    maximum_ratio: RatioDecimal
    required_feature_ids: list[str]
    feature_rules: list[WeatherFeatureRule]
    missing_feature_policy: Literal["BLOCK"]
    config_hash: str = Field(min_length=64, max_length=64)
    effective_from: date
    effective_to: date | None = None

    @field_validator("rule_code", "rule_version")
    @classmethod
    def _validate_weather_text(cls, value: str) -> str:
        return _require_non_blank(value, "weather text")

    @field_validator("lifecycle_timezone_name")
    @classmethod
    def _validate_weather_timezone(cls, value: str) -> str:
        return _validate_timezone_name(value)

    @field_validator("config_hash")
    @classmethod
    def _validate_config_hash(cls, value: str) -> str:
        return _validate_sha256(value, "config_hash")

    @field_validator("required_feature_ids")
    @classmethod
    def _validate_required_features(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("required_feature_ids must not be empty")
        normalized = []
        for item in value:
            normalized.append(_require_non_blank(item, "feature id"))
        if len(set(normalized)) != len(normalized):
            raise ValueError("required_feature_ids must be unique")
        return normalized

    @model_validator(mode="after")
    def _validate_weather_payload(self) -> Task9WeatherRuleConfigVersionSchema:
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must be >= effective_from")
        if self.minimum_ratio > self.maximum_ratio:
            raise ValueError("minimum_ratio must be <= maximum_ratio")
        feature_ids = [rule.feature_id for rule in self.feature_rules]
        if sorted(feature_ids) != sorted(self.required_feature_ids):
            raise ValueError("feature_rules must exactly cover required_feature_ids")
        return self

    @model_validator(mode="after")
    def _validate_config_hash_match(self) -> Task9WeatherRuleConfigVersionSchema:
        from backend.app.harvest_state.canonical import canonical_decimal_string

        def _band_payload(band: WeatherFeatureBand) -> dict[str, object]:
            return {
                "lower_bound": canonical_decimal_string(band.lower_bound),
                "lower_inclusive": band.lower_inclusive,
                "upper_bound": canonical_decimal_string(band.upper_bound),
                "upper_inclusive": band.upper_inclusive,
                "multiplier": canonical_decimal_string(band.multiplier),
            }

        feature_rules = [
            {
                "feature_id": item.feature_id,
                "bands": [
                    _band_payload(band)
                    for band in sorted(
                        item.bands,
                        key=lambda b: (
                            canonical_decimal_string(b.lower_bound),
                            b.lower_inclusive,
                            canonical_decimal_string(b.upper_bound),
                            b.upper_inclusive,
                            canonical_decimal_string(b.multiplier),
                        ),
                    )
                ],
            }
            for item in sorted(self.feature_rules, key=lambda i: i.feature_id)
        ]
        exact_config = {
            "version": self.rule_version,
            "required_feature_ids": sorted(self.required_feature_ids),
            "feature_rules": feature_rules,
            "combination_method": self.combination_method.value,
            "minimum_ratio": canonical_decimal_string(self.minimum_ratio),
            "maximum_ratio": canonical_decimal_string(self.maximum_ratio),
            "missing_feature_policy": self.missing_feature_policy,
        }
        expected = make_weather_rule_config_hash(exact_config)
        if self.config_hash != expected:
            raise ValueError("WEATHER_RULE_CONFIG_HASH_MISMATCH")
        return self


class Task9RunParameterPackageSchema(_LifecycleAuthorityRowBase):
    season_id: int = Field(gt=0)
    destination_factory_id: int = Field(gt=0)
    farm_scope_key: str = Field(min_length=1)
    farm_timezone: str = Field(min_length=1)
    destination_factory_timezone: str = Field(min_length=1)
    harvest_bucket_anchor_local_time: time
    harvest_to_arrival_lag_days: int = Field(ge=0)
    holiday_calendar_version_id: int = Field(gt=0)
    weather_rule_config_version_id: int = Field(gt=0)
    package_version: str = Field(min_length=1)
    revision: int = Field(gt=0)
    effective_from: date
    effective_to: date | None = None

    @field_validator("farm_scope_key", "package_version")
    @classmethod
    def _validate_package_text(cls, value: str) -> str:
        return _require_non_blank(value, "package text")

    @field_validator("farm_timezone", "destination_factory_timezone")
    @classmethod
    def _validate_package_timezone(cls, value: str) -> str:
        return _validate_timezone_name(value)

    @model_validator(mode="after")
    def _validate_package_effective_range(self) -> Task9RunParameterPackageSchema:
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must be >= effective_from")
        return self


class Task9InitialInventorySnapshotSchema(_LifecycleAuthorityRowBase):
    season_id: int = Field(gt=0)
    destination_factory_id: int = Field(gt=0)
    opening_state_date: date
    snapshot_version: str = Field(min_length=1)
    revision: int = Field(gt=0)
    initial_opening_mature_inventory_kg: NonNegativeBusinessDecimal

    @field_validator("snapshot_version")
    @classmethod
    def _validate_snapshot_version(cls, value: str) -> str:
        return _require_non_blank(value, "snapshot_version")


class Task9InitialInventoryCohortSchema(_AuthorityBase):
    stable_cohort_key: str = Field(min_length=1)
    forecast_quantile: ForecastQuantile
    cohort_date: date
    farm_id: int = Field(gt=0)
    subfarm_id: int | None = Field(default=None, gt=0)
    variety_id: int = Field(gt=0)
    remaining_quantity_kg: NonNegativeBusinessDecimal

    @field_validator("stable_cohort_key")
    @classmethod
    def _validate_stable_key(cls, value: str) -> str:
        return _require_non_blank(value, "stable_cohort_key")


class Task9MatureInventoryLossAuthoritySchema(_LifecycleAuthorityRowBase):
    season_id: int = Field(gt=0)
    destination_factory_id: int = Field(gt=0)
    state_date: date
    capacity_pool_code: str = Field(min_length=1)
    forecast_quantile: ForecastQuantile
    loss_version: str = Field(min_length=1)
    revision: int = Field(gt=0)
    mature_inventory_loss_quantity_kg: NonNegativeBusinessDecimal

    @field_validator("capacity_pool_code", "loss_version")
    @classmethod
    def _validate_loss_text(cls, value: str) -> str:
        return _require_non_blank(value, "loss text")


class Task9AuthorityLifecycleEventSchema(_AuthorityBase):
    authority_family: AuthorityFamily
    authority_stable_key: str = Field(min_length=1)
    authority_business_version: str = Field(min_length=1)
    authority_revision: int = Field(gt=0)
    business_row_hash: str = Field(min_length=64, max_length=64)
    transition_sequence: int = Field(ge=1)
    old_status: AuthorityStatus | None = None
    new_status: AuthorityStatus
    old_consumable_from_local_date: date | None = None
    old_consumable_to_local_date: date | None = None
    new_consumable_from_local_date: date | None = None
    new_consumable_to_local_date: date | None = None
    superseded_by_authority_stable_key: str | None = None
    superseded_by_authority_business_version: str | None = None
    superseded_by_authority_revision: int | None = Field(default=None, gt=0)
    transitioned_at: datetime
    source_system: str = Field(min_length=1)
    source_record_key: str = Field(min_length=1)
    lifecycle_event_hash: str = Field(min_length=64, max_length=64)

    @field_validator(
        "authority_stable_key",
        "authority_business_version",
        "source_system",
        "source_record_key",
    )
    @classmethod
    def _validate_event_text(cls, value: str) -> str:
        return _require_non_blank(value, "event text")

    @field_validator("business_row_hash", "lifecycle_event_hash")
    @classmethod
    def _validate_event_hash(cls, value: str) -> str:
        return _validate_sha256(value, "event hash")

    @field_validator("transitioned_at")
    @classmethod
    def _validate_aware_transitioned_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("transitioned_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def _validate_replacement_identity(self) -> Task9AuthorityLifecycleEventSchema:
        replacement_values = (
            self.superseded_by_authority_stable_key,
            self.superseded_by_authority_business_version,
            self.superseded_by_authority_revision,
        )
        all_null = all(value is None for value in replacement_values)
        all_present = all(value is not None for value in replacement_values)
        if not (all_null or all_present):
            raise ValueError("replacement identity must be all-or-none")
        if self.new_status is AuthorityStatus.SUPERSEDED and not all_present:
            raise ValueError("superseded lifecycle event requires replacement identity")
        if self.new_status is not AuthorityStatus.SUPERSEDED and not all_null:
            raise ValueError("replacement identity is only allowed for superseded events")
        return self


class Task9CapacityPoolDefinitionBundleSchema(Task9CapacityPoolDefinitionSchema):
    members: list[Task9CapacityPoolMemberSchema]

    @field_validator("members")
    @classmethod
    def _validate_members_not_empty(
        cls, value: list[Task9CapacityPoolMemberSchema]
    ) -> list[Task9CapacityPoolMemberSchema]:
        if not value:
            raise ValueError("members must not be empty")
        return value

    @model_validator(mode="after")
    def _validate_members(self) -> Task9CapacityPoolDefinitionBundleSchema:
        member_keys = set()
        farm_ids = set()
        subfarm_ids = set()
        for member in self.members:
            key = (member.farm_id, member.subfarm_id, member.variety_id)
            if key in member_keys:
                raise ValueError("member business key must be unique")
            member_keys.add(key)
            farm_ids.add(member.farm_id)
            subfarm_ids.add(member.subfarm_id)
        if len(farm_ids) > 1:
            raise ValueError("pool must not mix farms")
        # Pool grain rules (matching existing Task 9 service semantics)
        if self.capacity_pool_grain is CapacityPoolGrain.SUBFARM_VARIETY:
            if len(self.members) != 1:
                raise ValueError("SUBFARM_VARIETY grain requires exactly one member")
        elif self.capacity_pool_grain is CapacityPoolGrain.SUBFARM:
            if len(farm_ids) != 1:
                raise ValueError("SUBFARM grain requires exactly one farm_id")
            if len(subfarm_ids) != 1:
                raise ValueError("SUBFARM grain requires exactly one subfarm_id")
        elif self.capacity_pool_grain is CapacityPoolGrain.FARM:
            if len(farm_ids) != 1:
                raise ValueError("FARM grain requires exactly one farm_id")
        return self

    @property
    def definition(self) -> Task9CapacityPoolDefinitionSchema:
        return Task9CapacityPoolDefinitionSchema.model_validate(
            self.model_dump(exclude={"members"})
        )


class Task9HolidayCalendarBundleSchema(Task9HolidayCalendarVersionSchema):
    dates: list[Task9HolidayCalendarDateSchema]

    @model_validator(mode="after")
    def _validate_dates_unique(self) -> Task9HolidayCalendarBundleSchema:
        seen = set()
        for item in self.dates:
            key = (item.holiday_date, item.holiday_code)
            if key in seen:
                raise ValueError("holiday (date, code) must be unique")
            seen.add(key)
        return self

    @model_validator(mode="after")
    def _validate_calendar_hash_match(self) -> Task9HolidayCalendarBundleSchema:
        unique_dates = sorted({item.holiday_date for item in self.dates})
        expected = make_holiday_calendar_hash(
            holiday_calendar_version=self.calendar_version,
            holiday_dates=unique_dates,
        )
        if self.calendar_hash != expected:
            raise ValueError("HOLIDAY_CALENDAR_HASH_MISMATCH")
        return self

    @property
    def header(self) -> Task9HolidayCalendarVersionSchema:
        return Task9HolidayCalendarVersionSchema.model_validate(self.model_dump(exclude={"dates"}))

    @property
    def request_holiday_dates(self) -> list[date]:
        return sorted({item.holiday_date for item in self.dates})


class Task9InitialInventoryBundleSchema(Task9InitialInventorySnapshotSchema):
    cohorts: list[Task9InitialInventoryCohortSchema]

    @model_validator(mode="after")
    def _validate_inventory_reconciliation(self) -> Task9InitialInventoryBundleSchema:
        total = sum((item.remaining_quantity_kg for item in self.cohorts), start=Decimal("0"))
        if self.initial_opening_mature_inventory_kg == 0:
            if total != 0:
                raise ValueError("INITIAL_INVENTORY_COHORT_MISMATCH")
            return self
        if not self.cohorts:
            raise ValueError("non-zero opening inventory requires cohorts")
        if total != self.initial_opening_mature_inventory_kg:
            raise ValueError("INITIAL_INVENTORY_COHORT_MISMATCH")
        return self

    @model_validator(mode="after")
    def _validate_unique_cohort_keys(self) -> Task9InitialInventoryBundleSchema:
        seen: set[str] = set()
        for item in self.cohorts:
            if item.stable_cohort_key in seen:
                raise ValueError("DUPLICATE_STABLE_COHORT_KEY")
            seen.add(item.stable_cohort_key)
        return self

    @property
    def snapshot(self) -> Task9InitialInventorySnapshotSchema:
        return Task9InitialInventorySnapshotSchema.model_validate(
            self.model_dump(exclude={"cohorts"})
        )


# ── Semantic input schemas (P0-1: no row_hash / lifecycle_event_hash) ──


class _SemanticSourceBase(_AuthorityBase):
    """Base for semantic inputs that carry source provenance but no row_hash."""
    source_system: str = Field(min_length=1)
    source_record_key: str = Field(min_length=1)
    source_version: str = Field(min_length=1)

    @field_validator("source_system", "source_record_key", "source_version")
    @classmethod
    def _validate_non_blank(cls, value: str) -> str:
        return _require_non_blank(value, "text field")


class _SemanticLifecycleBase(_SemanticSourceBase):
    """Semantic lifecycle input: source provenance + lifecycle fields, no row_hash."""
    status: AuthorityStatus
    status_changed_at: datetime
    available_at_local_date: date
    consumable_from_local_date: date | None = None
    consumable_to_local_date: date | None = None
    superseded_by_id: int | None = None

    @field_validator("status_changed_at")
    @classmethod
    def _validate_aware_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("status_changed_at must be timezone-aware")
        return value

    @field_validator("superseded_by_id")
    @classmethod
    def _validate_superseded_by_id(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("superseded_by_id must be > 0 when set")
        return value

    @model_validator(mode="after")
    def _validate_lifecycle_projection(self) -> _SemanticLifecycleBase:
        if (
            self.status in {AuthorityStatus.DRAFT, AuthorityStatus.CANCELLED}
            and self.consumable_from_local_date is not None
        ):
            raise ValueError("draft/cancelled rows must not expose consumability")
        if (
            self.status in {AuthorityStatus.DRAFT, AuthorityStatus.CANCELLED}
            and self.consumable_to_local_date is not None
        ):
            raise ValueError("draft/cancelled rows must not expose consumability")
        if self.status is AuthorityStatus.ACTIVE:
            if self.consumable_from_local_date is None or self.consumable_to_local_date is not None:
                raise ValueError("active rows require open consumability interval")
        if self.status in {AuthorityStatus.SUPERSEDED, AuthorityStatus.RETIRED}:
            if self.consumable_from_local_date is None or self.consumable_to_local_date is None:
                raise ValueError("terminal lifecycle rows require closed consumability interval")
        if (
            self.consumable_from_local_date is not None
            and self.consumable_from_local_date < self.available_at_local_date
        ):
            raise ValueError("consumable_from_local_date must be >= available_at_local_date")
        if (
            self.consumable_to_local_date is not None
            and self.consumable_from_local_date is not None
            and self.consumable_to_local_date <= self.consumable_from_local_date
        ):
            raise ValueError("consumable_to_local_date must be > consumable_from_local_date")
        if self.status is AuthorityStatus.SUPERSEDED and self.superseded_by_id is None:
            raise ValueError("superseded rows require superseded_by_id")
        if self.status is not AuthorityStatus.SUPERSEDED and self.superseded_by_id is not None:
            raise ValueError("replacement id is only allowed for superseded rows")
        return self


class Task9CapacityPoolDefinitionSemanticInput(_SemanticLifecycleBase):
    season_id: int = Field(gt=0)
    destination_factory_id: int = Field(gt=0)
    capacity_pool_code: str = Field(min_length=1)
    capacity_pool_grain: CapacityPoolGrain
    capacity_input_mode: CapacityInputMode
    capacity_pool_version: str = Field(min_length=1)
    revision: int = Field(gt=0)
    effective_from: date
    effective_to: date | None = None

    @field_validator("capacity_pool_code", "capacity_pool_version")
    @classmethod
    def _validate_identity_text(cls, value: str) -> str:
        return _require_non_blank(value, "identity text")

    @model_validator(mode="after")
    def _validate_effective_range(self) -> Task9CapacityPoolDefinitionSemanticInput:
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must be >= effective_from")
        return self


class Task9CapacityPoolDefinitionSemanticBundle(Task9CapacityPoolDefinitionSemanticInput):
    members: list[Task9CapacityPoolMemberSchema]

    @field_validator("members")
    @classmethod
    def _validate_members_not_empty(
        cls, value: list[Task9CapacityPoolMemberSchema]
    ) -> list[Task9CapacityPoolMemberSchema]:
        if not value:
            raise ValueError("members must not be empty")
        return value

    @model_validator(mode="after")
    def _validate_members(self) -> Task9CapacityPoolDefinitionSemanticBundle:
        member_keys: set[tuple[int, int | None, int]] = set()
        farm_ids: set[int] = set()
        subfarm_ids: set[int | None] = set()
        for member in self.members:
            key = (member.farm_id, member.subfarm_id, member.variety_id)
            if key in member_keys:
                raise ValueError("member business key must be unique")
            member_keys.add(key)
            farm_ids.add(member.farm_id)
            subfarm_ids.add(member.subfarm_id)
        if len(farm_ids) > 1:
            raise ValueError("pool must not mix farms")
        if self.capacity_pool_grain is CapacityPoolGrain.SUBFARM_VARIETY:
            if len(self.members) != 1:
                raise ValueError("SUBFARM_VARIETY grain requires exactly one member")
        elif self.capacity_pool_grain is CapacityPoolGrain.SUBFARM:
            if len(farm_ids) != 1:
                raise ValueError("SUBFARM grain requires exactly one farm_id")
            if len(subfarm_ids) != 1:
                raise ValueError("SUBFARM grain requires exactly one subfarm_id")
        elif self.capacity_pool_grain is CapacityPoolGrain.FARM:
            if len(farm_ids) != 1:
                raise ValueError("FARM grain requires exactly one farm_id")
        return self

    @property
    def definition(self) -> Task9CapacityPoolDefinitionSemanticInput:
        return Task9CapacityPoolDefinitionSemanticInput.model_validate(
            self.model_dump(exclude={"members"})
        )


class Task9DailyCapacitySemanticInput(_SemanticLifecycleBase):
    season_id: int = Field(gt=0)
    destination_factory_id: int = Field(gt=0)
    capacity_pool_code: str = Field(min_length=1)
    capacity_pool_version: str = Field(min_length=1)
    capacity_pool_revision: int = Field(gt=0)
    capacity_date: date
    daily_capacity_revision: int = Field(gt=0)
    capacity_input_mode: CapacityInputMode
    planned_picker_count: NonNegativeBusinessDecimal | None = None
    kg_per_person_per_day: NonNegativeBusinessDecimal | None = None
    direct_nominal_capacity_kg_per_day: NonNegativeBusinessDecimal | None = None
    labor_availability_ratio: RatioDecimal
    operational_efficiency_ratio: RatioDecimal

    @field_validator("capacity_pool_code", "capacity_pool_version")
    @classmethod
    def _validate_daily_identity_text(cls, value: str) -> str:
        return _require_non_blank(value, "identity text")

    @model_validator(mode="after")
    def _validate_mode_fields(self) -> Task9DailyCapacitySemanticInput:
        if self.capacity_input_mode is CapacityInputMode.LABOR_DERIVED:
            if (
                self.planned_picker_count is None
                or self.kg_per_person_per_day is None
                or self.direct_nominal_capacity_kg_per_day is not None
                or self.labor_availability_ratio is None
                or self.operational_efficiency_ratio is None
            ):
                raise ValueError("LABOR_DERIVED fields are incomplete")
        if self.capacity_input_mode is CapacityInputMode.DIRECT_CAPACITY:
            if (
                self.direct_nominal_capacity_kg_per_day is None
                or self.planned_picker_count is not None
                or self.kg_per_person_per_day is not None
                or self.labor_availability_ratio is None
                or self.operational_efficiency_ratio is None
            ):
                raise ValueError("DIRECT_CAPACITY fields are incomplete")
        return self


class Task9RunParameterPackageSemanticInput(_SemanticLifecycleBase):
    """Semantic input for run package. No row_hash, no surrogate FK IDs."""
    season_id: int = Field(gt=0)
    destination_factory_id: int = Field(gt=0)
    farm_scope_key: str = Field(min_length=1)
    farm_timezone: str = Field(min_length=1)
    destination_factory_timezone: str = Field(min_length=1)
    harvest_bucket_anchor_local_time: time
    harvest_to_arrival_lag_days: int = Field(ge=0)
    package_version: str = Field(min_length=1)
    revision: int = Field(gt=0)
    effective_from: date
    effective_to: date | None = None

    @field_validator("farm_scope_key", "package_version")
    @classmethod
    def _validate_package_text(cls, value: str) -> str:
        return _require_non_blank(value, "package text")

    @field_validator("farm_timezone", "destination_factory_timezone")
    @classmethod
    def _validate_package_timezone(cls, value: str) -> str:
        return _validate_timezone_name(value)

    @model_validator(mode="after")
    def _validate_package_effective_range(self) -> Task9RunParameterPackageSemanticInput:
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must be >= effective_from")
        return self


class Task9HolidayCalendarSemanticInput(_SemanticLifecycleBase):
    season_id: int = Field(gt=0)
    calendar_code: str = Field(min_length=1)
    calendar_version: str = Field(min_length=1)
    revision: int = Field(gt=0)
    calendar_hash: str = Field(min_length=64, max_length=64)
    region_scope: str | None = None
    lifecycle_timezone_name: str = Field(min_length=1)

    @field_validator("calendar_code", "calendar_version")
    @classmethod
    def _validate_calendar_text(cls, value: str) -> str:
        return _require_non_blank(value, "calendar text")

    @field_validator("calendar_hash")
    @classmethod
    def _validate_calendar_hash(cls, value: str) -> str:
        return _validate_sha256(value, "calendar_hash")

    @field_validator("lifecycle_timezone_name")
    @classmethod
    def _validate_calendar_timezone(cls, value: str) -> str:
        return _validate_timezone_name(value)


class Task9HolidayCalendarSemanticBundle(Task9HolidayCalendarSemanticInput):
    dates: list[Task9HolidayCalendarDateSchema]

    @model_validator(mode="after")
    def _validate_dates_unique(self) -> Task9HolidayCalendarSemanticBundle:
        seen: set[tuple[date, str]] = set()
        for item in self.dates:
            key = (item.holiday_date, item.holiday_code)
            if key in seen:
                raise ValueError("holiday (date, code) must be unique")
            seen.add(key)
        return self

    @model_validator(mode="after")
    def _validate_calendar_hash_match(self) -> Task9HolidayCalendarSemanticBundle:
        unique_dates = sorted({item.holiday_date for item in self.dates})
        expected = make_holiday_calendar_hash(
            holiday_calendar_version=self.calendar_version,
            holiday_dates=unique_dates,
        )
        if self.calendar_hash != expected:
            raise ValueError("HOLIDAY_CALENDAR_HASH_MISMATCH")
        return self


class Task9WeatherRuleSemanticInput(_SemanticLifecycleBase):
    rule_code: str = Field(min_length=1)
    rule_version: str = Field(min_length=1)
    revision: int = Field(gt=0)
    lifecycle_timezone_name: str = Field(min_length=1)
    combination_method: WeatherCombinationMethod
    minimum_ratio: RatioDecimal
    maximum_ratio: RatioDecimal
    required_feature_ids: list[str]
    feature_rules: list[WeatherFeatureRule]
    missing_feature_policy: Literal["BLOCK"]
    config_hash: str = Field(min_length=64, max_length=64)
    effective_from: date
    effective_to: date | None = None

    @field_validator("rule_code", "rule_version")
    @classmethod
    def _validate_weather_text(cls, value: str) -> str:
        return _require_non_blank(value, "weather text")

    @field_validator("lifecycle_timezone_name")
    @classmethod
    def _validate_weather_timezone(cls, value: str) -> str:
        return _validate_timezone_name(value)

    @field_validator("config_hash")
    @classmethod
    def _validate_config_hash(cls, value: str) -> str:
        return _validate_sha256(value, "config_hash")

    @field_validator("required_feature_ids")
    @classmethod
    def _validate_required_features(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("required_feature_ids must not be empty")
        normalized = []
        for item in value:
            normalized.append(_require_non_blank(item, "feature id"))
        if len(set(normalized)) != len(normalized):
            raise ValueError("required_feature_ids must be unique")
        return normalized

    @model_validator(mode="after")
    def _validate_weather_payload(self) -> Task9WeatherRuleSemanticInput:
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must be >= effective_from")
        if self.minimum_ratio > self.maximum_ratio:
            raise ValueError("minimum_ratio must be <= maximum_ratio")
        feature_ids = [rule.feature_id for rule in self.feature_rules]
        if sorted(feature_ids) != sorted(self.required_feature_ids):
            raise ValueError("feature_rules must exactly cover required_feature_ids")
        return self

    @model_validator(mode="after")
    def _validate_config_hash_match(self) -> Task9WeatherRuleSemanticInput:
        from backend.app.harvest_state.canonical import canonical_decimal_string as _cds

        def _band_payload(band: WeatherFeatureBand) -> dict[str, object]:
            return {
                "lower_bound": _cds(band.lower_bound),
                "lower_inclusive": band.lower_inclusive,
                "upper_bound": _cds(band.upper_bound),
                "upper_inclusive": band.upper_inclusive,
                "multiplier": _cds(band.multiplier),
            }

        feature_rules = [
            {
                "feature_id": item.feature_id,
                "bands": [
                    _band_payload(band)
                    for band in sorted(
                        item.bands,
                        key=lambda b: (
                            _cds(b.lower_bound),
                            b.lower_inclusive,
                            _cds(b.upper_bound),
                            b.upper_inclusive,
                            _cds(b.multiplier),
                        ),
                    )
                ],
            }
            for item in sorted(self.feature_rules, key=lambda i: i.feature_id)
        ]
        exact_config = {
            "version": self.rule_version,
            "required_feature_ids": sorted(self.required_feature_ids),
            "feature_rules": feature_rules,
            "combination_method": self.combination_method.value,
            "minimum_ratio": _cds(self.minimum_ratio),
            "maximum_ratio": _cds(self.maximum_ratio),
            "missing_feature_policy": self.missing_feature_policy,
        }
        expected = make_weather_rule_config_hash(exact_config)
        if self.config_hash != expected:
            raise ValueError("WEATHER_RULE_CONFIG_HASH_MISMATCH")
        return self


class Task9InitialInventorySemanticInput(_SemanticLifecycleBase):
    season_id: int = Field(gt=0)
    destination_factory_id: int = Field(gt=0)
    opening_state_date: date
    snapshot_version: str = Field(min_length=1)
    revision: int = Field(gt=0)
    initial_opening_mature_inventory_kg: NonNegativeBusinessDecimal

    @field_validator("snapshot_version")
    @classmethod
    def _validate_snapshot_version(cls, value: str) -> str:
        return _require_non_blank(value, "snapshot_version")


class Task9InitialInventorySemanticBundle(Task9InitialInventorySemanticInput):
    cohorts: list[Task9InitialInventoryCohortSchema]

    @model_validator(mode="after")
    def _validate_inventory_reconciliation(self) -> Task9InitialInventorySemanticBundle:
        total = sum((item.remaining_quantity_kg for item in self.cohorts), start=Decimal("0"))
        if self.initial_opening_mature_inventory_kg == 0:
            if total != 0:
                raise ValueError("INITIAL_INVENTORY_COHORT_MISMATCH")
            return self
        if not self.cohorts:
            raise ValueError("non-zero opening inventory requires cohorts")
        if total != self.initial_opening_mature_inventory_kg:
            raise ValueError("INITIAL_INVENTORY_COHORT_MISMATCH")
        return self

    @model_validator(mode="after")
    def _validate_unique_cohort_keys(self) -> Task9InitialInventorySemanticBundle:
        seen: set[str] = set()
        for item in self.cohorts:
            if item.stable_cohort_key in seen:
                raise ValueError("DUPLICATE_STABLE_COHORT_KEY")
            seen.add(item.stable_cohort_key)
        return self


class Task9MatureLossSemanticInput(_SemanticLifecycleBase):
    season_id: int = Field(gt=0)
    destination_factory_id: int = Field(gt=0)
    state_date: date
    capacity_pool_code: str = Field(min_length=1)
    forecast_quantile: ForecastQuantile
    loss_version: str = Field(min_length=1)
    revision: int = Field(gt=0)
    mature_inventory_loss_quantity_kg: NonNegativeBusinessDecimal

    @field_validator("capacity_pool_code", "loss_version")
    @classmethod
    def _validate_loss_text(cls, value: str) -> str:
        return _require_non_blank(value, "loss text")


class Task9LifecycleEventSemanticInput(_AuthorityBase):
    """Semantic input for lifecycle event: no lifecycle_event_hash."""
    authority_family: AuthorityFamily
    authority_stable_key: str = Field(min_length=1)
    authority_business_version: str = Field(min_length=1)
    authority_revision: int = Field(gt=0)
    business_row_hash: str = Field(min_length=64, max_length=64)
    transition_sequence: int = Field(ge=1)
    old_status: AuthorityStatus | None = None
    new_status: AuthorityStatus
    old_consumable_from_local_date: date | None = None
    old_consumable_to_local_date: date | None = None
    new_consumable_from_local_date: date | None = None
    new_consumable_to_local_date: date | None = None
    superseded_by_authority_stable_key: str | None = None
    superseded_by_authority_business_version: str | None = None
    superseded_by_authority_revision: int | None = Field(default=None, gt=0)
    transitioned_at: datetime
    source_system: str = Field(min_length=1)
    source_record_key: str = Field(min_length=1)

    @field_validator(
        "authority_stable_key",
        "authority_business_version",
        "source_system",
        "source_record_key",
    )
    @classmethod
    def _validate_event_text(cls, value: str) -> str:
        return _require_non_blank(value, "event text")

    @field_validator("business_row_hash")
    @classmethod
    def _validate_event_hash(cls, value: str) -> str:
        return _validate_sha256(value, "event hash")

    @field_validator("transitioned_at")
    @classmethod
    def _validate_aware_transitioned_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("transitioned_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def _validate_replacement_identity(self) -> Task9LifecycleEventSemanticInput:
        replacement_values = (
            self.superseded_by_authority_stable_key,
            self.superseded_by_authority_business_version,
            self.superseded_by_authority_revision,
        )
        all_null = all(value is None for value in replacement_values)
        all_present = all(value is not None for value in replacement_values)
        if not (all_null or all_present):
            raise ValueError("replacement identity must be all-or-none")
        if self.new_status is AuthorityStatus.SUPERSEDED and not all_present:
            raise ValueError("superseded lifecycle event requires replacement identity")
        if self.new_status is not AuthorityStatus.SUPERSEDED and not all_null:
            raise ValueError("replacement identity is only allowed for superseded events")
        return self


# ── P0-2: Run-package bundle with mandatory dependencies ──────────────


class Task9RunParameterPackageBundleSchema(_AuthorityBase):
    """Bundle: run package + mandatory holiday + weather dependencies."""
    package: Task9RunParameterPackageSemanticInput
    holiday_calendar: Task9HolidayCalendarSemanticInput
    weather_rule: Task9WeatherRuleSemanticInput

    @model_validator(mode="after")
    def _validate_timezone_consistency(self) -> Task9RunParameterPackageBundleSchema:
        pkg_tz = self.package.destination_factory_timezone
        holiday_tz = self.holiday_calendar.lifecycle_timezone_name
        weather_tz = self.weather_rule.lifecycle_timezone_name
        if pkg_tz != holiday_tz or pkg_tz != weather_tz:
            raise ValueError("RUN_PARAMETER_DEPENDENCY_TIMEZONE_CONFLICT")
        return self
