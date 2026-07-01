from __future__ import annotations

from datetime import UTC, date, datetime

from backend.app.harvest_state.canonical import make_holiday_calendar_hash


def _daily_capacity_payload() -> dict[str, object]:
    return {
        "capacity_pool_definition_id": 11,
        "season_id": 1,
        "destination_factory_id": 2,
        "capacity_pool_code": "POOL-A",
        "capacity_pool_version": "v1",
        "capacity_pool_revision": 1,
        "capacity_date": date(2026, 2, 1),
        "daily_capacity_revision": 1,
        "capacity_input_mode": "LABOR_DERIVED",
        "planned_picker_count": "10",
        "kg_per_person_per_day": "20",
        "direct_nominal_capacity_kg_per_day": None,
        "labor_availability_ratio": "0.8",
        "operational_efficiency_ratio": "0.9",
        "available_at_local_date": date(2026, 1, 31),
        "consumable_from_local_date": date(2026, 1, 31),
        "consumable_to_local_date": None,
        "status": "active",
        "status_changed_at": datetime(2026, 1, 31, 8, 0, tzinfo=UTC),
        "superseded_by_id": None,
        "source_system": "task9_historical_authority",
        "source_record_key": "daily-capacity:1:2:POOL-A:v1:1:2026-02-01:1",
        "source_version": "v1",
        "row_hash": "c" * 64,
    }


def _pool_bundle_payload() -> dict[str, object]:
    return {
        "season_id": 1,
        "destination_factory_id": 2,
        "capacity_pool_code": "POOL-A",
        "capacity_pool_grain": "FARM",
        "capacity_input_mode": "LABOR_DERIVED",
        "capacity_pool_version": "v1",
        "revision": 1,
        "effective_from": date(2026, 1, 1),
        "effective_to": None,
        "available_at_local_date": date(2026, 1, 1),
        "consumable_from_local_date": None,
        "consumable_to_local_date": None,
        "status": "draft",
        "status_changed_at": datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        "source_system": "task9_historical_authority",
        "source_record_key": "capacity-pool:1:2:POOL-A:v1:1",
        "source_version": "v1",
        "row_hash": "a" * 64,
        "members": [
            {
                "farm_id": 11,
                "subfarm_id": 5,
                "variety_id": 20,
            },
            {
                "farm_id": 11,
                "subfarm_id": None,
                "variety_id": 10,
            },
        ],
    }


def _holiday_payload() -> dict[str, object]:
    _cal_hash = make_holiday_calendar_hash(
        holiday_calendar_version="calendar-v1", holiday_dates=[date(2026, 2, 10)]
    )
    return {
        "season_id": 1,
        "calendar_code": "CN-SH",
        "calendar_version": "calendar-v1",
        "revision": 1,
        "calendar_hash": _cal_hash,
        "region_scope": "CN-SH",
        "lifecycle_timezone_name": "Asia/Shanghai",
        "available_at_local_date": date(2026, 1, 1),
        "consumable_from_local_date": date(2026, 1, 1),
        "consumable_to_local_date": None,
        "status": "active",
        "status_changed_at": datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        "superseded_by_id": None,
        "source_system": "task9_historical_authority",
        "source_record_key": "holiday-calendar:1:CN-SH:Asia/Shanghai:calendar-v1:1",
        "source_version": "calendar-v1",
        "row_hash": "f" * 64,
        "dates": [
            {
                "holiday_date": date(2026, 2, 10),
                "holiday_code": "LOCAL",
                "holiday_name": "B",
            },
            {
                "holiday_date": date(2026, 2, 10),
                "holiday_code": "CNY",
                "holiday_name": "A",
            },
        ],
    }


def _inventory_payload() -> dict[str, object]:
    return {
        "season_id": 1,
        "destination_factory_id": 2,
        "opening_state_date": date(2026, 2, 1),
        "snapshot_version": "snap-v1",
        "revision": 1,
        "initial_opening_mature_inventory_kg": "30",
        "available_at_local_date": date(2026, 1, 31),
        "consumable_from_local_date": date(2026, 1, 31),
        "consumable_to_local_date": None,
        "status": "active",
        "status_changed_at": datetime(2026, 1, 31, 9, 0, tzinfo=UTC),
        "superseded_by_id": None,
        "source_system": "task9_historical_authority",
        "source_record_key": "initial-inventory:1:2:2026-02-01:snap-v1:1",
        "source_version": "snap-v1",
        "row_hash": "3" * 64,
        "cohorts": [
            {
                "stable_cohort_key": "c3",
                "forecast_quantile": "P90",
                "cohort_date": date(2026, 1, 31),
                "farm_id": 10,
                "subfarm_id": None,
                "variety_id": 20,
                "remaining_quantity_kg": "10",
            },
            {
                "stable_cohort_key": "c1",
                "forecast_quantile": "P50",
                "cohort_date": date(2026, 1, 29),
                "farm_id": 10,
                "subfarm_id": None,
                "variety_id": 20,
                "remaining_quantity_kg": "10",
            },
            {
                "stable_cohort_key": "c2",
                "forecast_quantile": "P80",
                "cohort_date": date(2026, 1, 30),
                "farm_id": 10,
                "subfarm_id": None,
                "variety_id": 20,
                "remaining_quantity_kg": "10",
            },
        ],
    }


def _lifecycle_payload() -> dict[str, object]:
    return {
        "authority_family": "daily_capacity",
        "authority_stable_key": "daily-capacity:1:2:POOL-A:v1:1:2026-02-01",
        "authority_business_version": "v1",
        "authority_revision": 1,
        "business_row_hash": "8" * 64,
        "transition_sequence": 1,
        "old_status": None,
        "new_status": "draft",
        "old_consumable_from_local_date": None,
        "old_consumable_to_local_date": None,
        "new_consumable_from_local_date": None,
        "new_consumable_to_local_date": None,
        "superseded_by_authority_stable_key": None,
        "superseded_by_authority_business_version": None,
        "superseded_by_authority_revision": None,
        "transitioned_at": datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        "source_system": "task9_historical_authority",
        "source_record_key": "lifecycle:daily-capacity:1",
        "lifecycle_event_hash": "9" * 64,
    }


def test_daily_stable_key_and_revision_contract() -> None:
    from backend.app.harvest_state.authority_canonical import (
        build_daily_capacity_payload,
        build_daily_capacity_stable_key,
    )
    from backend.app.harvest_state.authority_schemas import Task9DailyCapacityAuthoritySchema

    row = Task9DailyCapacityAuthoritySchema.model_validate(_daily_capacity_payload())
    assert build_daily_capacity_stable_key(row) == ("daily-capacity:1:2:POOL-A:v1:1:2026-02-01")
    payload = build_daily_capacity_payload(row)
    assert payload["daily_capacity_revision"] == "1" or payload["daily_capacity_revision"] == 1


def test_daily_parent_revision_changes_stable_key_but_child_revision_does_not() -> None:
    from backend.app.harvest_state.authority_canonical import build_daily_capacity_stable_key
    from backend.app.harvest_state.authority_schemas import Task9DailyCapacityAuthoritySchema

    base = Task9DailyCapacityAuthoritySchema.model_validate(_daily_capacity_payload())
    changed_parent = Task9DailyCapacityAuthoritySchema.model_validate(
        {**_daily_capacity_payload(), "capacity_pool_revision": 2}
    )
    changed_child = Task9DailyCapacityAuthoritySchema.model_validate(
        {**_daily_capacity_payload(), "daily_capacity_revision": 2}
    )

    assert build_daily_capacity_stable_key(base) != build_daily_capacity_stable_key(changed_parent)
    assert build_daily_capacity_stable_key(base) == build_daily_capacity_stable_key(changed_child)


def test_business_row_hash_excludes_status_and_consumability_but_not_business_fields() -> None:
    from backend.app.harvest_state.authority_canonical import make_authority_row_hash
    from backend.app.harvest_state.authority_schemas import Task9DailyCapacityAuthoritySchema

    base = Task9DailyCapacityAuthoritySchema.model_validate(_daily_capacity_payload())
    changed_status = Task9DailyCapacityAuthoritySchema.model_validate(
        {
            **_daily_capacity_payload(),
            "status": "superseded",
            "consumable_to_local_date": date(2026, 2, 2),
            "superseded_by_id": 99,
        }
    )
    changed_business = Task9DailyCapacityAuthoritySchema.model_validate(
        {**_daily_capacity_payload(), "planned_picker_count": "11"}
    )
    assert make_authority_row_hash(base) == make_authority_row_hash(changed_status)
    assert make_authority_row_hash(base) != make_authority_row_hash(changed_business)


def test_pool_holiday_and_inventory_payloads_are_order_deterministic() -> None:
    from backend.app.harvest_state.authority_canonical import (
        build_capacity_pool_definition_payload,
        build_holiday_calendar_payload,
        build_initial_inventory_snapshot_payload,
        make_authority_row_hash,
    )
    from backend.app.harvest_state.authority_schemas import (
        Task9CapacityPoolDefinitionBundleSchema,
        Task9HolidayCalendarBundleSchema,
        Task9InitialInventoryBundleSchema,
    )

    pool = Task9CapacityPoolDefinitionBundleSchema.model_validate(_pool_bundle_payload())
    holiday = Task9HolidayCalendarBundleSchema.model_validate(_holiday_payload())
    inventory = Task9InitialInventoryBundleSchema.model_validate(_inventory_payload())

    pool_payload = build_capacity_pool_definition_payload(pool.definition, pool.members)
    assert [m["variety_id"] for m in pool_payload["members"]] == [10, 20]

    holiday_payload = build_holiday_calendar_payload(holiday.header, holiday.dates)
    assert [d["holiday_code"] for d in holiday_payload["dates"]] == ["CNY", "LOCAL"]

    inventory_payload = build_initial_inventory_snapshot_payload(
        inventory.snapshot, inventory.cohorts
    )
    assert [c["stable_cohort_key"] for c in inventory_payload["cohorts"]] == ["c1", "c2", "c3"]

    assert make_authority_row_hash(pool) == make_authority_row_hash(
        Task9CapacityPoolDefinitionBundleSchema.model_validate(_pool_bundle_payload())
    )


def test_lifecycle_event_hash_changes_only_when_event_fields_change() -> None:
    from backend.app.harvest_state.authority_canonical import make_lifecycle_event_hash
    from backend.app.harvest_state.authority_schemas import Task9AuthorityLifecycleEventSchema

    event = Task9AuthorityLifecycleEventSchema.model_validate(_lifecycle_payload())
    changed = Task9AuthorityLifecycleEventSchema.model_validate(
        {
            **_lifecycle_payload(),
            "new_status": "active",
            "new_consumable_from_local_date": date(2026, 1, 1),
        }
    )
    assert make_lifecycle_event_hash(event) != make_lifecycle_event_hash(changed)

    same_semantics = Task9AuthorityLifecycleEventSchema.model_validate(
        {**_lifecycle_payload(), "lifecycle_event_hash": "a" * 64}
    )
    assert make_lifecycle_event_hash(event) == make_lifecycle_event_hash(same_semantics)
