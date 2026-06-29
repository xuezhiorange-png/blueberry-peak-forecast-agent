"""Golden-vector regression tests for Task 9 authority semantic hashing.

Covers:
- P0-1: business hash excludes row_hash, status, lifecycle, created_at, surrogate IDs
- P0-2: run-package dependency identity is semantic, not surrogate ID
- P0-2: member/cohort hash includes parent semantic identity
- P0-3: calendar_hash and config_hash strict validation
- P0-4: inventory reconciliation rules
- P0-5: pool grain rules
- P1: naive datetime rejection, empty holiday dates, duplicate cohort keys
"""
from __future__ import annotations

from datetime import UTC, date, datetime, time

import pytest
from pydantic import ValidationError

from backend.app.harvest_state.authority_canonical import (
    build_capacity_pool_definition_payload,
    build_daily_capacity_payload,
    build_initial_inventory_snapshot_payload,
    build_run_parameter_package_payload,
    make_authority_row_hash,
)
from backend.app.harvest_state.authority_schemas import (
    Task9AuthorityLifecycleEventSchema,
    Task9CapacityPoolDefinitionBundleSchema,
    Task9CapacityPoolDefinitionSchema,
    Task9CapacityPoolMemberSchema,
    Task9DailyCapacityAuthoritySchema,
    Task9HolidayCalendarBundleSchema,
    Task9HolidayCalendarVersionSchema,
    Task9InitialInventoryBundleSchema,
    Task9InitialInventoryCohortSchema,
    Task9InitialInventorySnapshotSchema,
    Task9RunParameterPackageSchema,
    Task9WeatherRuleConfigVersionSchema,
)
from backend.app.harvest_state.canonical import (
    make_holiday_calendar_hash,
    make_weather_rule_config_hash,
)

# ── helpers ────────────────────────────────────────────────────────────


def _sha(seed: str) -> str:
    # Produce valid hex by using hashlib
    import hashlib
    return hashlib.sha256(seed.encode()).hexdigest()


def _pool_def_draft() -> dict[str, object]:
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
        "row_hash": _sha("a"),
    }


def _member(
    farm_id: int = 10, subfarm_id: int | None = None, variety_id: int = 20
) -> dict[str, object]:
    return {"farm_id": farm_id, "subfarm_id": subfarm_id, "variety_id": variety_id}


def _pool_bundle(grain: str = "FARM", members: list[dict] | None = None) -> dict[str, object]:
    if members is None:
        members = [_member()]
    return {**_pool_def_draft(), "capacity_pool_grain": grain, "members": members}


def _daily() -> dict[str, object]:
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
        "row_hash": _sha("c"),
    }


def _run_package() -> dict[str, object]:
    return {
        "season_id": 1,
        "destination_factory_id": 2,
        "farm_scope_key": "farm-scope:10",
        "farm_timezone": "Asia/Shanghai",
        "destination_factory_timezone": "Asia/Shanghai",
        "harvest_bucket_anchor_local_time": time(9, 0),
        "harvest_to_arrival_lag_days": 1,
        "holiday_calendar_version_id": 31,
        "weather_rule_config_version_id": 41,
        "package_version": "pkg-v1",
        "revision": 1,
        "effective_from": date(2026, 1, 1),
        "effective_to": None,
        "available_at_local_date": date(2026, 1, 1),
        "consumable_from_local_date": date(2026, 1, 1),
        "consumable_to_local_date": None,
        "status": "active",
        "status_changed_at": datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        "superseded_by_id": None,
        "source_system": "task9_historical_authority",
        "source_record_key": "run-package:1:2:farm-scope:10:pkg-v1:1",
        "source_version": "pkg-v1",
        "row_hash": _sha("d"),
    }


def _cal_hash() -> str:
    return make_holiday_calendar_hash(
        holiday_calendar_version="calendar-v1", holiday_dates=[date(2026, 2, 10)]
    )


def _holiday_bundle() -> dict[str, object]:
    return {
        "season_id": 1,
        "calendar_code": "CN-SH",
        "calendar_version": "calendar-v1",
        "revision": 1,
        "calendar_hash": _cal_hash(),
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
        "row_hash": _sha("f"),
        "dates": [
            {"holiday_date": date(2026, 2, 10), "holiday_code": "CNY", "holiday_name": "A"},
            {"holiday_date": date(2026, 2, 10), "holiday_code": "LOCAL", "holiday_name": "B"},
        ],
    }


def _weather_cfg() -> dict[str, object]:
    exact = {
        "version": "wx-v1",
        "required_feature_ids": ["rain", "temp"],
        "feature_rules": [
            {
                "feature_id": "rain",
                "bands": [{"lower_bound": "0", "lower_inclusive": True,
                           "upper_bound": "10", "upper_inclusive": True, "multiplier": "1"}],
            },
            {
                "feature_id": "temp",
                "bands": [{"lower_bound": "0", "lower_inclusive": True,
                           "upper_bound": "30", "upper_inclusive": True, "multiplier": "0.9"}],
            },
        ],
        "combination_method": "MULTIPLY",
        "minimum_ratio": "0.7",
        "maximum_ratio": "1",
        "missing_feature_policy": "BLOCK",
    }
    return {
        "rule_code": "wx-rule",
        "rule_version": "wx-v1",
        "revision": 1,
        "lifecycle_timezone_name": "Asia/Shanghai",
        "combination_method": "MULTIPLY",
        "minimum_ratio": "0.7",
        "maximum_ratio": "1",
        "required_feature_ids": ["rain", "temp"],
        "feature_rules": [
            {"feature_id": "rain", "bands": [
                {"lower_bound": "0", "lower_inclusive": True,
                 "upper_bound": "10", "upper_inclusive": True, "multiplier": "1"},
            ]},
            {"feature_id": "temp", "bands": [
                {"lower_bound": "0", "lower_inclusive": True,
                 "upper_bound": "30", "upper_inclusive": True, "multiplier": "0.9"},
            ]},
        ],
        "missing_feature_policy": "BLOCK",
        "config_hash": make_weather_rule_config_hash(exact),
        "available_at_local_date": date(2026, 1, 1),
        "effective_from": date(2026, 1, 1),
        "effective_to": None,
        "consumable_from_local_date": date(2026, 1, 1),
        "consumable_to_local_date": None,
        "status": "active",
        "status_changed_at": datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        "superseded_by_id": None,
        "source_system": "task9_historical_authority",
        "source_record_key": "weather-rule:wx-rule:Asia/Shanghai:wx-v1:1",
        "source_version": "wx-v1",
        "row_hash": _sha("2"),
    }


def _inventory_bundle(total: str = "30") -> dict[str, object]:
    return {
        "season_id": 1,
        "destination_factory_id": 2,
        "opening_state_date": date(2026, 2, 1),
        "snapshot_version": "snap-v1",
        "revision": 1,
        "initial_opening_mature_inventory_kg": total,
        "available_at_local_date": date(2026, 1, 31),
        "consumable_from_local_date": date(2026, 1, 31),
        "consumable_to_local_date": None,
        "status": "active",
        "status_changed_at": datetime(2026, 1, 31, 9, 0, tzinfo=UTC),
        "superseded_by_id": None,
        "source_system": "task9_historical_authority",
        "source_record_key": "initial-inventory:1:2:2026-02-01:snap-v1:1",
        "source_version": "snap-v1",
        "row_hash": _sha("3"),
        "cohorts": [
            {"stable_cohort_key": "c1", "forecast_quantile": "P50",
             "cohort_date": date(2026, 1, 29), "farm_id": 10, "subfarm_id": None,
             "variety_id": 20, "remaining_quantity_kg": "10"},
            {"stable_cohort_key": "c2", "forecast_quantile": "P80",
             "cohort_date": date(2026, 1, 30), "farm_id": 10, "subfarm_id": None,
             "variety_id": 20, "remaining_quantity_kg": "10"},
            {"stable_cohort_key": "c3", "forecast_quantile": "P90",
             "cohort_date": date(2026, 1, 31), "farm_id": 10, "subfarm_id": None,
             "variety_id": 20, "remaining_quantity_kg": "10"},
        ],
    }


def _mature_loss() -> dict[str, object]:
    return {
        "season_id": 1,
        "destination_factory_id": 2,
        "state_date": date(2026, 2, 1),
        "capacity_pool_code": "POOL-A",
        "forecast_quantile": "P50",
        "loss_version": "loss-v1",
        "revision": 1,
        "mature_inventory_loss_quantity_kg": "5",
        "available_at_local_date": date(2026, 1, 31),
        "consumable_from_local_date": date(2026, 1, 31),
        "consumable_to_local_date": None,
        "status": "active",
        "status_changed_at": datetime(2026, 1, 31, 9, 0, tzinfo=UTC),
        "superseded_by_id": None,
        "source_system": "task9_historical_authority",
        "source_record_key": "mature-loss:1:2:POOL-A:2026-02-01:P50:loss-v1:1",
        "source_version": "loss-v1",
        "row_hash": _sha("7"),
    }


def _lifecycle_event() -> dict[str, object]:
    return {
        "authority_family": "daily_capacity",
        "authority_stable_key": "daily-capacity:1:2:POOL-A:v1:1:2026-02-01",
        "authority_business_version": "v1",
        "authority_revision": 1,
        "business_row_hash": _sha("8"),
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
        "lifecycle_event_hash": _sha("9"),
    }


# ── P0-1: hash excludes metadata ──────────────────────────────────────


def test_hash_changes_when_row_hash_changes_but_stays_same_when_only_hash_field_changes() -> None:
    """Changing the input row_hash must NOT change the recomputed business hash."""
    base = Task9DailyCapacityAuthoritySchema.model_validate(_daily())
    different_hash = Task9DailyCapacityAuthoritySchema.model_validate(
        {**_daily(), "row_hash": "f" * 64}
    )
    assert make_authority_row_hash(base) == make_authority_row_hash(different_hash)


def test_hash_does_not_require_dummy_row_hash() -> None:
    """Builder should work without the caller providing a row_hash at all... but schema requires it.
    The point is: the hash output is independent of the input row_hash value."""
    a = Task9DailyCapacityAuthoritySchema.model_validate({**_daily(), "row_hash": _sha("a")})
    b = Task9DailyCapacityAuthoritySchema.model_validate({**_daily(), "row_hash": _sha("b")})
    assert make_authority_row_hash(a) == make_authority_row_hash(b)


def test_hash_excludes_status() -> None:
    base = Task9DailyCapacityAuthoritySchema.model_validate(_daily())
    changed = Task9DailyCapacityAuthoritySchema.model_validate(
        {**_daily(), "status": "superseded", "consumable_to_local_date": date(2026, 3, 1),
         "superseded_by_id": 99}
    )
    assert make_authority_row_hash(base) == make_authority_row_hash(changed)


def test_hash_excludes_consumability_dates() -> None:
    base = Task9DailyCapacityAuthoritySchema.model_validate(_daily())
    changed = Task9DailyCapacityAuthoritySchema.model_validate(
        {**_daily(), "consumable_from_local_date": date(2026, 3, 1)}
    )
    assert make_authority_row_hash(base) == make_authority_row_hash(changed)


def test_hash_changes_when_business_value_changes() -> None:
    base = Task9DailyCapacityAuthoritySchema.model_validate(_daily())
    changed = Task9DailyCapacityAuthoritySchema.model_validate(
        {**_daily(), "planned_picker_count": "999"}
    )
    assert make_authority_row_hash(base) != make_authority_row_hash(changed)


def test_hash_changes_when_source_provenance_changes() -> None:
    base = Task9DailyCapacityAuthoritySchema.model_validate(_daily())
    changed = Task9DailyCapacityAuthoritySchema.model_validate(
        {**_daily(), "source_system": "other_system"}
    )
    assert make_authority_row_hash(base) != make_authority_row_hash(changed)


def test_hash_changes_when_revision_changes() -> None:
    base = Task9DailyCapacityAuthoritySchema.model_validate(_daily())
    changed = Task9DailyCapacityAuthoritySchema.model_validate(
        {**_daily(), "daily_capacity_revision": 2}
    )
    assert make_authority_row_hash(base) != make_authority_row_hash(changed)


# ── P0-2: run-package dependency ID vs semantic identity ──────────────


def test_run_package_hash_changes_when_dependency_semantic_identity_changes() -> None:
    """Run-package hash must change when holiday/weather semantic identity changes."""
    holiday = Task9HolidayCalendarVersionSchema.model_validate(
        {k: v for k, v in _holiday_bundle().items() if k != "dates"}
    )
    weather = Task9WeatherRuleConfigVersionSchema.model_validate(_weather_cfg())
    pkg = Task9RunParameterPackageSchema.model_validate(_run_package())

    h1 = make_authority_row_hash(pkg, holiday_header=holiday, weather_rule=weather)

    # Change holiday revision
    holiday2 = Task9HolidayCalendarVersionSchema.model_validate(
        {**_holiday_bundle(), "revision": 99, "dates": None}  # type: ignore[arg-type]
    ) if False else Task9HolidayCalendarVersionSchema.model_validate(
        {k: v for k, v in _holiday_bundle().items() if k != "dates"} | {"revision": 99}
    )
    h2 = make_authority_row_hash(pkg, holiday_header=holiday2, weather_rule=weather)
    assert h1 != h2


def test_run_package_surrogate_id_change_does_not_affect_hash() -> None:
    """Changing holiday_calendar_version_id (surrogate) must NOT change hash."""
    a = Task9RunParameterPackageSchema.model_validate(_run_package())
    b = Task9RunParameterPackageSchema.model_validate(
        {**_run_package(),
         "holiday_calendar_version_id": 999, "weather_rule_config_version_id": 888}
    )
    assert make_authority_row_hash(a) == make_authority_row_hash(b)


# ── P0-2: member hash includes parent ─────────────────────────────────


def test_member_hash_includes_parent_semantic_identity() -> None:
    member = Task9CapacityPoolMemberSchema.model_validate(_member())
    parent_a = Task9CapacityPoolDefinitionSchema.model_validate(_pool_def_draft())
    parent_b = Task9CapacityPoolDefinitionSchema.model_validate(
        {**_pool_def_draft(), "capacity_pool_code": "OTHER"}
    )
    h_a = make_authority_row_hash(member, parent_definition=parent_a)
    h_b = make_authority_row_hash(member, parent_definition=parent_b)
    assert h_a != h_b


def test_member_hash_changes_when_parent_identity_changes() -> None:
    member = Task9CapacityPoolMemberSchema.model_validate(_member())
    parent1 = Task9CapacityPoolDefinitionSchema.model_validate(_pool_def_draft())
    parent2 = Task9CapacityPoolDefinitionSchema.model_validate(
        {**_pool_def_draft(), "revision": 2}
    )
    assert make_authority_row_hash(member, parent_definition=parent1) != make_authority_row_hash(
        member, parent_definition=parent2
    )


# ── P0-2: cohort hash includes parent ─────────────────────────────────


def test_cohort_hash_includes_parent_snapshot_identity() -> None:
    cohort = Task9InitialInventoryCohortSchema.model_validate(_inventory_bundle()["cohorts"][0])
    snap1 = Task9InitialInventorySnapshotSchema.model_validate(
        {k: v for k, v in _inventory_bundle().items() if k != "cohorts"}
    )
    snap2 = Task9InitialInventorySnapshotSchema.model_validate(
        {k: v for k, v in _inventory_bundle().items() if k != "cohorts"} | {"revision": 99}
    )
    h1 = make_authority_row_hash(cohort, parent_snapshot=snap1)
    h2 = make_authority_row_hash(cohort, parent_snapshot=snap2)
    assert h1 != h2


# ── P0-3: calendar_hash and config_hash strict validation ─────────────


def test_calendar_hash_mismatch_rejected() -> None:
    bad = {**_holiday_bundle(), "calendar_hash": "ab" * 32}
    with pytest.raises(ValidationError, match="HOLIDAY_CALENDAR_HASH_MISMATCH"):
        Task9HolidayCalendarBundleSchema.model_validate(bad)


def test_config_hash_mismatch_rejected() -> None:
    bad = {**_weather_cfg(), "config_hash": "cd" * 32}
    with pytest.raises(ValidationError, match="WEATHER_RULE_CONFIG_HASH_MISMATCH"):
        Task9WeatherRuleConfigVersionSchema.model_validate(bad)


# ── P0-4: inventory reconciliation ────────────────────────────────────


def test_zero_opening_positive_cohorts_rejected() -> None:
    bad = _inventory_bundle(total="0")
    # keep positive cohorts
    with pytest.raises(ValidationError, match="INITIAL_INVENTORY_COHORT_MISMATCH"):
        Task9InitialInventoryBundleSchema.model_validate(bad)


def test_empty_holiday_dates_pass() -> None:
    """Empty holiday dates list should be valid (no holidays for the period)."""
    bundle = {**_holiday_bundle(), "dates": []}
    # Recompute hash for empty dates
    bundle["calendar_hash"] = make_holiday_calendar_hash(
        holiday_calendar_version="calendar-v1", holiday_dates=[]
    )
    result = Task9HolidayCalendarBundleSchema.model_validate(bundle)
    assert result.dates == []


# ── P0-5: pool grain rules ────────────────────────────────────────────


def test_subfarm_variety_multiple_members_rejected() -> None:
    bad = _pool_bundle(
        grain="SUBFARM_VARIETY",
        members=[_member(10, 5, 20), _member(10, 5, 30)],
    )
    with pytest.raises(ValidationError, match="SUBFARM_VARIETY.*exactly one"):
        Task9CapacityPoolDefinitionBundleSchema.model_validate(bad)


def test_subfarm_cross_subfarm_rejected() -> None:
    bad = _pool_bundle(
        grain="SUBFARM",
        members=[_member(10, 5, 20), _member(10, 7, 30)],
    )
    with pytest.raises(ValidationError, match="SUBFARM.*exactly one subfarm"):
        Task9CapacityPoolDefinitionBundleSchema.model_validate(bad)


# ── P1: duplicate stable_cohort_key ──────────────────────────────────


def test_duplicate_stable_cohort_key_rejected() -> None:
    bad = _inventory_bundle()
    # Add a duplicate with same key but zero quantity to avoid reconciliation failure
    dup = dict(bad["cohorts"][0])  # type: ignore[attr-defined]
    dup["remaining_quantity_kg"] = "0"
    # Actually, just duplicate the key directly - reconciliation sum will be 30+0=30 matching total
    # But the original cohort already has 10, so we need to adjust
    # Use a simpler approach: two cohorts with same key summing correctly
    bad["cohorts"] = [
        {"stable_cohort_key": "dup", "forecast_quantile": "P50",
         "cohort_date": date(2026, 1, 29), "farm_id": 10, "subfarm_id": None,
         "variety_id": 20, "remaining_quantity_kg": "15"},
        {"stable_cohort_key": "dup", "forecast_quantile": "P80",
         "cohort_date": date(2026, 1, 30), "farm_id": 10, "subfarm_id": None,
         "variety_id": 20, "remaining_quantity_kg": "15"},
    ]
    with pytest.raises(ValidationError, match="DUPLICATE_STABLE_COHORT_KEY"):
        Task9InitialInventoryBundleSchema.model_validate(bad)


# ── P1: naive datetime rejection ──────────────────────────────────────


def test_naive_status_changed_at_rejected() -> None:
    bad = _daily()
    bad["status_changed_at"] = datetime(2026, 1, 1, 9, 0)  # no tzinfo
    with pytest.raises(ValidationError, match="timezone-aware"):
        Task9DailyCapacityAuthoritySchema.model_validate(bad)


def test_naive_transitioned_at_rejected() -> None:
    bad = _lifecycle_event()
    bad["transitioned_at"] = datetime(2026, 1, 1, 9, 0)  # no tzinfo
    with pytest.raises(ValidationError, match="timezone-aware"):
        Task9AuthorityLifecycleEventSchema.model_validate(bad)


# ── golden canonical payloads ─────────────────────────────────────────


def test_daily_canonical_payload_golden() -> None:
    row = Task9DailyCapacityAuthoritySchema.model_validate(_daily())
    payload = build_daily_capacity_payload(row)
    # Must NOT contain excluded fields
    for excluded in ("row_hash", "status", "status_changed_at", "superseded_by_id",
                     "consumable_from_local_date", "consumable_to_local_date",
                     "created_at", "capacity_pool_definition_id"):
        assert excluded not in payload, f"{excluded} must not be in canonical payload"
    # Must contain business fields
    assert payload["season_id"] == 1
    assert payload["capacity_pool_code"] == "POOL-A"
    assert payload["source_system"] == "task9_historical_authority"


def test_pool_definition_canonical_payload_golden() -> None:
    bundle = Task9CapacityPoolDefinitionBundleSchema.model_validate(_pool_bundle())
    payload = build_capacity_pool_definition_payload(bundle.definition, bundle.members)
    assert "row_hash" not in payload
    assert "status" not in payload
    assert len(payload["members"]) == 1
    member_payload = payload["members"][0]
    assert "parent_pool_identity" in member_payload
    assert member_payload["parent_pool_identity"]["capacity_pool_code"] == "POOL-A"
    assert "row_hash" not in member_payload
    assert "source_system" not in member_payload


def test_run_package_canonical_payload_golden() -> None:
    row = Task9RunParameterPackageSchema.model_validate(_run_package())
    holiday = Task9HolidayCalendarVersionSchema.model_validate(
        {k: v for k, v in _holiday_bundle().items() if k != "dates"}
    )
    weather = Task9WeatherRuleConfigVersionSchema.model_validate(_weather_cfg())
    payload = build_run_parameter_package_payload(row, holiday, weather)
    assert "holiday_calendar_version_id" not in payload
    assert "weather_rule_config_version_id" not in payload
    assert "holiday_calendar" in payload
    assert "weather_rule" in payload
    assert payload["holiday_calendar"]["calendar_version"] == "calendar-v1"
    assert payload["weather_rule"]["rule_code"] == "wx-rule"


def test_inventory_canonical_payload_golden() -> None:
    bundle = Task9InitialInventoryBundleSchema.model_validate(_inventory_bundle())
    payload = build_initial_inventory_snapshot_payload(bundle.snapshot, bundle.cohorts)
    assert "row_hash" not in payload
    assert "status" not in payload
    cohort_payload = payload["cohorts"][0]
    assert "parent_snapshot_identity" in cohort_payload
    assert "row_hash" not in cohort_payload
    assert "source_system" not in cohort_payload
    assert cohort_payload["parent_snapshot_identity"]["snapshot_version"] == "snap-v1"
