from __future__ import annotations

from datetime import date
from typing import Any

from backend.app.harvest_state.authority_schemas import (
    Task9AuthorityLifecycleEventSchema,
    Task9CapacityPoolDefinitionBundleSchema,
    Task9CapacityPoolDefinitionSchema,
    Task9CapacityPoolMemberSchema,
    Task9DailyCapacityAuthoritySchema,
    Task9HolidayCalendarBundleSchema,
    Task9HolidayCalendarDateSchema,
    Task9HolidayCalendarVersionSchema,
    Task9InitialInventoryBundleSchema,
    Task9InitialInventoryCohortSchema,
    Task9InitialInventorySnapshotSchema,
    Task9MatureInventoryLossAuthoritySchema,
    Task9RunParameterPackageSchema,
    Task9WeatherRuleConfigVersionSchema,
)
from backend.app.harvest_state.canonical import (
    canonical_decimal_string,
    canonical_json_dumps,
    canonical_json_value,
    make_holiday_calendar_hash,
    make_weather_rule_config_hash,
    sha256_hex,
)

TASK9_AUTHORITY_LIFECYCLE_EVENT_SCHEMA_VERSION = "task9-authority-lifecycle-event-v1"


# ── sort keys ──────────────────────────────────────────────────────────


def _canonical_member_sort_key(member: Task9CapacityPoolMemberSchema) -> tuple[int, int, int]:
    return (
        member.farm_id,
        -1 if member.subfarm_id is None else member.subfarm_id,
        member.variety_id,
    )


def _canonical_holiday_sort_key(item: Task9HolidayCalendarDateSchema) -> tuple[date, str]:
    return (item.holiday_date, item.holiday_code)


def _canonical_cohort_sort_key(item: Task9InitialInventoryCohortSchema) -> str:
    return item.stable_cohort_key


def _weather_band_payload(band: Any) -> dict[str, object]:
    return {
        "lower_bound": canonical_decimal_string(band.lower_bound),
        "lower_inclusive": band.lower_inclusive,
        "upper_bound": canonical_decimal_string(band.upper_bound),
        "upper_inclusive": band.upper_inclusive,
        "multiplier": canonical_decimal_string(band.multiplier),
    }


# ── stable keys ────────────────────────────────────────────────────────


def build_capacity_pool_definition_stable_key(
    definition: Task9CapacityPoolDefinitionSchema,
) -> str:
    return (
        f"capacity-pool:{definition.season_id}:{definition.destination_factory_id}:"
        f"{definition.capacity_pool_code}"
    )


def build_daily_capacity_stable_key(row: Task9DailyCapacityAuthoritySchema) -> str:
    return (
        f"daily-capacity:{row.season_id}:{row.destination_factory_id}:"
        f"{row.capacity_pool_code}:{row.capacity_pool_version}:{row.capacity_pool_revision}:"
        f"{row.capacity_date.isoformat()}"
    )


def build_run_parameter_package_stable_key(row: Task9RunParameterPackageSchema) -> str:
    return f"run-package:{row.season_id}:{row.destination_factory_id}:{row.farm_scope_key}"


def build_holiday_calendar_stable_key(row: Task9HolidayCalendarVersionSchema) -> str:
    return f"holiday-calendar:{row.season_id}:{row.calendar_code}:{row.lifecycle_timezone_name}"


def build_weather_rule_stable_key(row: Task9WeatherRuleConfigVersionSchema) -> str:
    return f"weather-rule:{row.rule_code}:{row.lifecycle_timezone_name}"


def build_initial_inventory_stable_key(row: Task9InitialInventorySnapshotSchema) -> str:
    return (
        f"initial-inventory:{row.season_id}:{row.destination_factory_id}:"
        f"{row.opening_state_date.isoformat()}"
    )


def build_mature_inventory_loss_stable_key(
    row: Task9MatureInventoryLossAuthoritySchema,
) -> str:
    return (
        f"mature-loss:{row.season_id}:{row.destination_factory_id}:{row.capacity_pool_code}:"
        f"{row.state_date.isoformat()}:{row.forecast_quantile.value}"
    )


# ── parent semantic identity helpers ───────────────────────────────────


def _pool_definition_semantic_identity(
    definition: Task9CapacityPoolDefinitionSchema,
) -> dict[str, object]:
    """Semantic identity of a capacity pool definition (no metadata)."""
    return {
        "season_id": definition.season_id,
        "destination_factory_id": definition.destination_factory_id,
        "capacity_pool_code": definition.capacity_pool_code,
        "capacity_pool_grain": definition.capacity_pool_grain.value,
        "capacity_input_mode": definition.capacity_input_mode.value,
        "capacity_pool_version": definition.capacity_pool_version,
        "revision": definition.revision,
        "effective_from": definition.effective_from.isoformat(),
        "effective_to": (
            None if definition.effective_to is None else definition.effective_to.isoformat()
        ),
        "available_at_local_date": definition.available_at_local_date.isoformat(),
        "source_system": definition.source_system,
        "source_record_key": definition.source_record_key,
        "source_version": definition.source_version,
    }


def _snapshot_semantic_identity(
    snapshot: Task9InitialInventorySnapshotSchema,
) -> dict[str, object]:
    """Semantic identity of an initial inventory snapshot (no metadata)."""
    return {
        "season_id": snapshot.season_id,
        "destination_factory_id": snapshot.destination_factory_id,
        "opening_state_date": snapshot.opening_state_date.isoformat(),
        "snapshot_version": snapshot.snapshot_version,
        "revision": snapshot.revision,
        "initial_opening_mature_inventory_kg": canonical_decimal_string(
            snapshot.initial_opening_mature_inventory_kg
        ),
        "available_at_local_date": snapshot.available_at_local_date.isoformat(),
        "source_system": snapshot.source_system,
        "source_record_key": snapshot.source_record_key,
        "source_version": snapshot.source_version,
    }


def _holiday_semantic_identity(
    header: Task9HolidayCalendarVersionSchema,
) -> dict[str, object]:
    """Semantic identity of a holiday calendar version (no metadata)."""
    return {
        "season_id": header.season_id,
        "calendar_code": header.calendar_code,
        "calendar_version": header.calendar_version,
        "revision": header.revision,
        "lifecycle_timezone_name": header.lifecycle_timezone_name,
    }


def _weather_semantic_identity(
    row: Task9WeatherRuleConfigVersionSchema,
) -> dict[str, object]:
    """Semantic identity of a weather rule config version (no metadata)."""
    return {
        "rule_code": row.rule_code,
        "rule_version": row.rule_version,
        "revision": row.revision,
        "lifecycle_timezone_name": row.lifecycle_timezone_name,
    }


# ── payload builders (P0-1: exclude row_hash, status, lifecycle, surrogate IDs) ──


def build_capacity_pool_member_payload(
    member: Task9CapacityPoolMemberSchema,
    parent_definition: Task9CapacityPoolDefinitionSchema,
) -> dict[str, object]:
    """Member payload includes parent pool semantic identity."""
    return {
        "parent_pool_identity": _pool_definition_semantic_identity(parent_definition),
        "farm_id": member.farm_id,
        "subfarm_id": member.subfarm_id,
        "variety_id": member.variety_id,
    }


def build_capacity_pool_definition_payload(
    definition: Task9CapacityPoolDefinitionSchema,
    members: list[Task9CapacityPoolMemberSchema],
) -> dict[str, object]:
    return {
        "season_id": definition.season_id,
        "destination_factory_id": definition.destination_factory_id,
        "capacity_pool_code": definition.capacity_pool_code,
        "capacity_pool_grain": definition.capacity_pool_grain.value,
        "capacity_input_mode": definition.capacity_input_mode.value,
        "capacity_pool_version": definition.capacity_pool_version,
        "revision": definition.revision,
        "effective_from": definition.effective_from.isoformat(),
        "effective_to": (
            None if definition.effective_to is None else definition.effective_to.isoformat()
        ),
        "available_at_local_date": definition.available_at_local_date.isoformat(),
        "source_system": definition.source_system,
        "source_record_key": definition.source_record_key,
        "source_version": definition.source_version,
        "members": [
            build_capacity_pool_member_payload(item, definition)
            for item in sorted(members, key=_canonical_member_sort_key)
        ],
    }


def build_daily_capacity_payload(row: Task9DailyCapacityAuthoritySchema) -> dict[str, object]:
    return {
        "season_id": row.season_id,
        "destination_factory_id": row.destination_factory_id,
        "capacity_pool_code": row.capacity_pool_code,
        "capacity_pool_version": row.capacity_pool_version,
        "capacity_pool_revision": row.capacity_pool_revision,
        "capacity_date": row.capacity_date.isoformat(),
        "daily_capacity_revision": row.daily_capacity_revision,
        "capacity_input_mode": row.capacity_input_mode.value,
        "planned_picker_count": (
            None
            if row.planned_picker_count is None
            else canonical_decimal_string(row.planned_picker_count)
        ),
        "kg_per_person_per_day": (
            None
            if row.kg_per_person_per_day is None
            else canonical_decimal_string(row.kg_per_person_per_day)
        ),
        "direct_nominal_capacity_kg_per_day": (
            None
            if row.direct_nominal_capacity_kg_per_day is None
            else canonical_decimal_string(row.direct_nominal_capacity_kg_per_day)
        ),
        "labor_availability_ratio": canonical_decimal_string(row.labor_availability_ratio),
        "operational_efficiency_ratio": canonical_decimal_string(row.operational_efficiency_ratio),
        "available_at_local_date": row.available_at_local_date.isoformat(),
        "source_system": row.source_system,
        "source_record_key": row.source_record_key,
        "source_version": row.source_version,
    }


def build_run_parameter_package_payload(
    row: Task9RunParameterPackageSchema,
    holiday_header: Task9HolidayCalendarVersionSchema | None = None,
    weather_rule: Task9WeatherRuleConfigVersionSchema | None = None,
) -> dict[str, object]:
    """Run-package payload. P0-2: dependency IDs replaced with expanded semantic identity."""
    payload: dict[str, object] = {
        "season_id": row.season_id,
        "destination_factory_id": row.destination_factory_id,
        "farm_scope_key": row.farm_scope_key,
        "farm_timezone": row.farm_timezone,
        "destination_factory_timezone": row.destination_factory_timezone,
        "harvest_bucket_anchor_local_time": row.harvest_bucket_anchor_local_time.isoformat(),
        "harvest_to_arrival_lag_days": row.harvest_to_arrival_lag_days,
        "package_version": row.package_version,
        "revision": row.revision,
        "effective_from": row.effective_from.isoformat(),
        "effective_to": None if row.effective_to is None else row.effective_to.isoformat(),
        "available_at_local_date": row.available_at_local_date.isoformat(),
        "source_system": row.source_system,
        "source_record_key": row.source_record_key,
        "source_version": row.source_version,
    }
    # P0-2: expand dependency semantic identity instead of surrogate IDs
    if holiday_header is not None:
        payload["holiday_calendar"] = _holiday_semantic_identity(holiday_header)
    if weather_rule is not None:
        payload["weather_rule"] = _weather_semantic_identity(weather_rule)
    return payload


def build_holiday_calendar_payload(
    header: Task9HolidayCalendarVersionSchema,
    dates: list[Task9HolidayCalendarDateSchema],
) -> dict[str, object]:
    unique_holiday_dates = sorted({item.holiday_date for item in dates})
    return {
        "season_id": header.season_id,
        "calendar_code": header.calendar_code,
        "calendar_version": header.calendar_version,
        "revision": header.revision,
        "calendar_hash": make_holiday_calendar_hash(
            holiday_calendar_version=header.calendar_version,
            holiday_dates=unique_holiday_dates,
        ),
        "region_scope": header.region_scope,
        "lifecycle_timezone_name": header.lifecycle_timezone_name,
        "available_at_local_date": header.available_at_local_date.isoformat(),
        "source_system": header.source_system,
        "source_record_key": header.source_record_key,
        "source_version": header.source_version,
        "dates": [
            {
                "holiday_date": item.holiday_date.isoformat(),
                "holiday_code": item.holiday_code,
                "holiday_name": item.holiday_name,
            }
            for item in sorted(dates, key=_canonical_holiday_sort_key)
        ],
    }


def build_weather_rule_config_payload(
    row: Task9WeatherRuleConfigVersionSchema,
) -> dict[str, object]:
    feature_rules = [
        {
            "feature_id": item.feature_id,
            "bands": [
                _weather_band_payload(band)
                for band in sorted(
                    item.bands,
                    key=lambda band: (
                        canonical_decimal_string(band.lower_bound),
                        band.lower_inclusive,
                        canonical_decimal_string(band.upper_bound),
                        band.upper_inclusive,
                        canonical_decimal_string(band.multiplier),
                    ),
                )
            ],
        }
        for item in sorted(row.feature_rules, key=lambda item: item.feature_id)
    ]
    exact_config_payload = {
        "version": row.rule_version,
        "required_feature_ids": sorted(row.required_feature_ids),
        "feature_rules": feature_rules,
        "combination_method": row.combination_method.value,
        "minimum_ratio": canonical_decimal_string(row.minimum_ratio),
        "maximum_ratio": canonical_decimal_string(row.maximum_ratio),
        "missing_feature_policy": row.missing_feature_policy,
    }
    return {
        "rule_code": row.rule_code,
        "rule_version": row.rule_version,
        "revision": row.revision,
        "lifecycle_timezone_name": row.lifecycle_timezone_name,
        "effective_from": row.effective_from.isoformat(),
        "effective_to": None if row.effective_to is None else row.effective_to.isoformat(),
        "available_at_local_date": row.available_at_local_date.isoformat(),
        "config_hash": make_weather_rule_config_hash(exact_config_payload),
        "config": exact_config_payload,
        "source_system": row.source_system,
        "source_record_key": row.source_record_key,
        "source_version": row.source_version,
    }


def build_initial_inventory_cohort_payload(
    row: Task9InitialInventoryCohortSchema,
    parent_snapshot: Task9InitialInventorySnapshotSchema,
) -> dict[str, object]:
    """Cohort payload includes parent snapshot semantic identity."""
    return {
        "parent_snapshot_identity": _snapshot_semantic_identity(parent_snapshot),
        "stable_cohort_key": row.stable_cohort_key,
        "forecast_quantile": row.forecast_quantile.value,
        "cohort_date": row.cohort_date.isoformat(),
        "farm_id": row.farm_id,
        "subfarm_id": row.subfarm_id,
        "variety_id": row.variety_id,
        "remaining_quantity_kg": canonical_decimal_string(row.remaining_quantity_kg),
    }


def build_initial_inventory_snapshot_payload(
    row: Task9InitialInventorySnapshotSchema,
    cohorts: list[Task9InitialInventoryCohortSchema],
) -> dict[str, object]:
    return {
        "season_id": row.season_id,
        "destination_factory_id": row.destination_factory_id,
        "opening_state_date": row.opening_state_date.isoformat(),
        "snapshot_version": row.snapshot_version,
        "revision": row.revision,
        "initial_opening_mature_inventory_kg": canonical_decimal_string(
            row.initial_opening_mature_inventory_kg
        ),
        "available_at_local_date": row.available_at_local_date.isoformat(),
        "source_system": row.source_system,
        "source_record_key": row.source_record_key,
        "source_version": row.source_version,
        "cohorts": [
            build_initial_inventory_cohort_payload(item, row)
            for item in sorted(cohorts, key=_canonical_cohort_sort_key)
        ],
    }


def build_mature_inventory_loss_payload(
    row: Task9MatureInventoryLossAuthoritySchema,
) -> dict[str, object]:
    return {
        "season_id": row.season_id,
        "destination_factory_id": row.destination_factory_id,
        "state_date": row.state_date.isoformat(),
        "capacity_pool_code": row.capacity_pool_code,
        "forecast_quantile": row.forecast_quantile.value,
        "loss_version": row.loss_version,
        "revision": row.revision,
        "mature_inventory_loss_quantity_kg": canonical_decimal_string(
            row.mature_inventory_loss_quantity_kg
        ),
        "available_at_local_date": row.available_at_local_date.isoformat(),
        "source_system": row.source_system,
        "source_record_key": row.source_record_key,
        "source_version": row.source_version,
    }


def build_lifecycle_event_payload(
    row: Task9AuthorityLifecycleEventSchema,
) -> dict[str, object]:
    """Lifecycle event hash payload. lifecycle_event_hash itself is excluded."""
    return {
        "event_schema_version": TASK9_AUTHORITY_LIFECYCLE_EVENT_SCHEMA_VERSION,
        "authority_family": row.authority_family.value,
        "authority_stable_key": row.authority_stable_key,
        "authority_business_version": row.authority_business_version,
        "authority_revision": row.authority_revision,
        "business_row_hash": row.business_row_hash,
        "transition_sequence": row.transition_sequence,
        "old_status": None if row.old_status is None else row.old_status.value,
        "new_status": row.new_status.value,
        "old_consumable_from_local_date": (
            None
            if row.old_consumable_from_local_date is None
            else row.old_consumable_from_local_date.isoformat()
        ),
        "old_consumable_to_local_date": (
            None
            if row.old_consumable_to_local_date is None
            else row.old_consumable_to_local_date.isoformat()
        ),
        "new_consumable_from_local_date": (
            None
            if row.new_consumable_from_local_date is None
            else row.new_consumable_from_local_date.isoformat()
        ),
        "new_consumable_to_local_date": (
            None
            if row.new_consumable_to_local_date is None
            else row.new_consumable_to_local_date.isoformat()
        ),
        "superseded_by_authority_stable_key": row.superseded_by_authority_stable_key,
        "superseded_by_authority_business_version": (row.superseded_by_authority_business_version),
        "superseded_by_authority_revision": row.superseded_by_authority_revision,
        "transitioned_at": canonical_json_value(row.transitioned_at),
        "source_system": row.source_system,
        "source_record_key": row.source_record_key,
    }


# ── hash entry points ─────────────────────────────────────────────────


def make_authority_row_hash(
    row: object,
    *,
    parent_definition: Task9CapacityPoolDefinitionSchema | None = None,
    parent_snapshot: Task9InitialInventorySnapshotSchema | None = None,
    holiday_header: Task9HolidayCalendarVersionSchema | None = None,
    weather_rule: Task9WeatherRuleConfigVersionSchema | None = None,
) -> str:
    if isinstance(row, Task9CapacityPoolDefinitionBundleSchema):
        return sha256_hex(build_capacity_pool_definition_payload(row.definition, row.members))
    if isinstance(row, Task9HolidayCalendarBundleSchema):
        return sha256_hex(build_holiday_calendar_payload(row.header, row.dates))
    if isinstance(row, Task9InitialInventoryBundleSchema):
        return sha256_hex(build_initial_inventory_snapshot_payload(row.snapshot, row.cohorts))
    if isinstance(row, Task9CapacityPoolDefinitionSchema):
        raise TypeError("capacity pool definition hash requires members")
    if isinstance(row, Task9HolidayCalendarVersionSchema):
        raise TypeError("holiday calendar hash requires child dates")
    if isinstance(row, Task9InitialInventorySnapshotSchema):
        raise TypeError("inventory snapshot hash requires cohorts")
    if isinstance(row, Task9DailyCapacityAuthoritySchema):
        return sha256_hex(build_daily_capacity_payload(row))
    if isinstance(row, Task9RunParameterPackageSchema):
        return sha256_hex(
            build_run_parameter_package_payload(row, holiday_header, weather_rule)
        )
    if isinstance(row, Task9WeatherRuleConfigVersionSchema):
        return sha256_hex(build_weather_rule_config_payload(row))
    if isinstance(row, Task9MatureInventoryLossAuthoritySchema):
        return sha256_hex(build_mature_inventory_loss_payload(row))
    if isinstance(row, Task9CapacityPoolMemberSchema):
        if parent_definition is None:
            raise TypeError("capacity pool member hash requires parent_definition")
        return sha256_hex(build_capacity_pool_member_payload(row, parent_definition))
    if isinstance(row, Task9InitialInventoryCohortSchema):
        if parent_snapshot is None:
            raise TypeError("initial inventory cohort hash requires parent_snapshot")
        return sha256_hex(build_initial_inventory_cohort_payload(row, parent_snapshot))
    raise TypeError(f"unsupported authority row type: {type(row).__name__}")


def make_lifecycle_event_hash(row: Task9AuthorityLifecycleEventSchema) -> str:
    return sha256_hex(build_lifecycle_event_payload(row))


def canonical_payload_json(payload: dict[str, Any]) -> str:
    return canonical_json_dumps(payload)
