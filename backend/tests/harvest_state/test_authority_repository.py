"""Pure unit tests for Task 9 authority repository (no database).

Tests cover:
  1. Advisory lock key determinism and collision avoidance
  2. Lifecycle transition matrix (allowed and forbidden transitions)
  3. Scope extraction for each authority family
  4. Error classification (all error codes are instantiated correctly)
  5. Result types construction
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from backend.app.harvest_state.authority_repository import (
    _ALLOWED_TRANSITIONS,
    _advisory_lock_key,
    _extract_scope,
)
from backend.app.harvest_state.authority_repository_errors import (
    AuthorityConsumabilityIntervalConflictError,
    AuthorityConsumabilityIntervalInvalidError,
    AuthorityConsumabilityIntervalOverlapError,
    AuthorityHashConflictError,
    AuthorityNotFoundError,
    AuthorityStillReferencedByActivePackageError,
    AuthoritySupersessionScopeConflictError,
    AuthorityVersionConflictError,
    CapacityPoolGrainInvalidError,
    CapacityPoolMembershipConflictError,
    DependencyNotFoundError,
    HolidayCalendarHashMismatchError,
    InitialInventoryCohortMismatchError,
    LifecycleTransitionInvalidError,
    RunParameterDependencyStatusConflictError,
    RunParameterDependencyTimezoneConflictError,
    WeatherRuleConfigHashMismatchError,
)
from backend.app.harvest_state.authority_repository_types import (
    AuthorityBundleCreateResult,
    AuthorityBundleLoadResult,
    AuthorityCreateResult,
    AuthorityLoadResult,
    LifecycleTransitionResult,
    SupersessionResult,
)
from backend.app.harvest_state.enums import AuthorityFamily, AuthorityStatus

# ── Constants ──────────────────────────────────────────────────────────

BIGINT_MIN = -(2**63)
BIGINT_MAX = 2**63 - 1

# ═══════════════════════════════════════════════════════════════════════
# 1. Advisory lock key
# ═══════════════════════════════════════════════════════════════════════


def test_advisory_lock_key_deterministic():
    """Same inputs always produce same lock key."""
    args = ("capacity_pool_definition", "pool:2026:F1:BLUE", "v1", 1)
    result_a = _advisory_lock_key(*args)
    result_b = _advisory_lock_key(*args)
    assert result_a == result_b
    # Call a third time to be sure
    assert _advisory_lock_key(*args) == result_a


def test_advisory_lock_key_different_family():
    """Different family -> different lock key."""
    base_args = ("capacity_pool_definition", "pool:2026:F1:BLUE", "v1", 1)
    other_args = ("daily_capacity", "pool:2026:F1:BLUE", "v1", 1)
    assert _advisory_lock_key(*base_args) != _advisory_lock_key(*other_args)


def test_advisory_lock_key_different_version():
    """Different version -> different lock key."""
    args_v1 = ("capacity_pool_definition", "pool:2026:F1:BLUE", "v1", 1)
    args_v2 = ("capacity_pool_definition", "pool:2026:F1:BLUE", "v2", 1)
    assert _advisory_lock_key(*args_v1) != _advisory_lock_key(*args_v2)


def test_advisory_lock_key_different_revision():
    """Different revision -> different lock key."""
    args_r1 = ("capacity_pool_definition", "pool:2026:F1:BLUE", "v1", 1)
    args_r2 = ("capacity_pool_definition", "pool:2026:F1:BLUE", "v1", 2)
    assert _advisory_lock_key(*args_r1) != _advisory_lock_key(*args_r2)


def test_advisory_lock_key_is_signed_bigint():
    """Lock key fits in PostgreSQL bigint (signed 64-bit)."""
    # Test a handful of inputs to ensure the range is respected.
    samples = [
        ("capacity_pool_definition", "pool:2026:F1:BLUE", "v1", 1),
        ("daily_capacity", "dc:2026:F2:STRAW:2026-06-01", "v3", 42),
        ("holiday_calendar_version", "cal:2026:CN", "v1", 1),
        ("weather_rule_config_version", "wr:HEAT", "v2", 7),
        ("run_parameter_package", "rp:2026:F1:farm-a", "v1", 1),
        ("initial_inventory_snapshot", "inv:2026:F1:2026-01-01", "v1", 1),
        ("mature_inventory_loss_authority", "ml:2026:F1:BLUE:2026-06-15:P50", "v1", 1),
    ]
    for args in samples:
        key = _advisory_lock_key(*args)
        assert isinstance(key, int), f"Key is not int: {key!r}"
        assert BIGINT_MIN <= key <= BIGINT_MAX, (
            f"Key {key} outside signed 64-bit range for {args}"
        )


# ═══════════════════════════════════════════════════════════════════════
# 2. Lifecycle transition matrix
# ═══════════════════════════════════════════════════════════════════════


def test_allowed_transitions_draft():
    """draft -> {active, cancelled}; no others."""
    allowed = _ALLOWED_TRANSITIONS[AuthorityStatus.DRAFT]
    assert allowed == {AuthorityStatus.ACTIVE, AuthorityStatus.CANCELLED}
    # Ensure terminal states are NOT reachable from draft
    assert AuthorityStatus.SUPERSEDED not in allowed
    assert AuthorityStatus.RETIRED not in allowed
    assert AuthorityStatus.DRAFT not in allowed  # no self-loop


def test_allowed_transitions_active():
    """active -> {superseded, retired}; no others."""
    allowed = _ALLOWED_TRANSITIONS[AuthorityStatus.ACTIVE]
    assert allowed == {AuthorityStatus.SUPERSEDED, AuthorityStatus.RETIRED}
    assert AuthorityStatus.DRAFT not in allowed
    assert AuthorityStatus.CANCELLED not in allowed
    assert AuthorityStatus.ACTIVE not in allowed  # no self-loop


def test_allowed_transitions_terminal():
    """superseded, retired, cancelled -> no outgoing."""
    for terminal in (
        AuthorityStatus.SUPERSEDED,
        AuthorityStatus.RETIRED,
        AuthorityStatus.CANCELLED,
    ):
        allowed = _ALLOWED_TRANSITIONS[terminal]
        assert allowed == set(), f"Terminal status {terminal} has outgoing: {allowed}"


def test_unknown_transition_rejected():
    """Unknown status has no outgoing transitions."""
    # Simulate an unknown status string that is NOT in the matrix.
    fake_status = "bogus_status"
    assert fake_status not in _ALLOWED_TRANSITIONS


def test_transition_matrix_is_exhaustive():
    """Every declared AuthorityStatus has an entry in the matrix."""
    for status in AuthorityStatus:
        assert status in _ALLOWED_TRANSITIONS, f"Missing status: {status}"


# ═══════════════════════════════════════════════════════════════════════
# 3. Scope extraction
# ═══════════════════════════════════════════════════════════════════════


class TestExtractScope:
    """Scope extraction produces expected keys for each authority family."""

    def test_capacity_pool(self):
        row = SimpleNamespace(
            season_id=2026,
            destination_factory_id=10,
            capacity_pool_code="BLUE",
        )
        scope = _extract_scope(AuthorityFamily.CAPACITY_POOL_DEFINITION, row)
        assert scope == {
            "season_id": 2026,
            "destination_factory_id": 10,
            "capacity_pool_code": "BLUE",
        }

    def test_daily_capacity(self):
        row = SimpleNamespace(
            capacity_pool_definition_id=99,
            capacity_date=date(2026, 6, 15),
        )
        scope = _extract_scope(AuthorityFamily.DAILY_CAPACITY, row)
        assert scope == {
            "capacity_pool_definition_id": 99,
            "capacity_date": date(2026, 6, 15),
        }

    def test_holiday(self):
        row = SimpleNamespace(
            season_id=2026,
            calendar_code="CN",
            lifecycle_timezone_name="Asia/Shanghai",
        )
        scope = _extract_scope(AuthorityFamily.HOLIDAY_CALENDAR_VERSION, row)
        assert scope == {
            "season_id": 2026,
            "calendar_code": "CN",
            "lifecycle_timezone_name": "Asia/Shanghai",
        }

    def test_weather(self):
        row = SimpleNamespace(
            rule_code="HEAT",
            lifecycle_timezone_name="Asia/Shanghai",
        )
        scope = _extract_scope(AuthorityFamily.WEATHER_RULE_CONFIG_VERSION, row)
        assert scope == {
            "rule_code": "HEAT",
            "lifecycle_timezone_name": "Asia/Shanghai",
        }

    def test_run_package(self):
        row = SimpleNamespace(
            season_id=2026,
            destination_factory_id=10,
            farm_scope_key="farm-a",
        )
        scope = _extract_scope(AuthorityFamily.RUN_PARAMETER_PACKAGE, row)
        assert scope == {
            "season_id": 2026,
            "destination_factory_id": 10,
            "farm_scope_key": "farm-a",
        }

    def test_initial_inventory(self):
        row = SimpleNamespace(
            season_id=2026,
            destination_factory_id=10,
            opening_state_date=date(2026, 1, 1),
        )
        scope = _extract_scope(AuthorityFamily.INITIAL_INVENTORY_SNAPSHOT, row)
        assert scope == {
            "season_id": 2026,
            "destination_factory_id": 10,
            "opening_state_date": date(2026, 1, 1),
        }

    def test_mature_loss(self):
        row = SimpleNamespace(
            season_id=2026,
            destination_factory_id=10,
            capacity_pool_code="BLUE",
            state_date=date(2026, 6, 15),
            forecast_quantile="P50",
        )
        scope = _extract_scope(
            AuthorityFamily.MATURE_INVENTORY_LOSS_AUTHORITY, row
        )
        assert scope == {
            "season_id": 2026,
            "destination_factory_id": 10,
            "capacity_pool_code": "BLUE",
            "state_date": date(2026, 6, 15),
            "forecast_quantile": "P50",
        }

    def test_same_scope_equality(self):
        """Same business key components produce equal scope dicts."""
        row_a = SimpleNamespace(
            season_id=2026,
            destination_factory_id=10,
            capacity_pool_code="BLUE",
        )
        row_b = SimpleNamespace(
            season_id=2026,
            destination_factory_id=10,
            capacity_pool_code="BLUE",
        )
        scope_a = _extract_scope(AuthorityFamily.CAPACITY_POOL_DEFINITION, row_a)
        scope_b = _extract_scope(AuthorityFamily.CAPACITY_POOL_DEFINITION, row_b)
        assert scope_a == scope_b
        assert scope_a is not scope_b  # distinct objects

    def test_different_scope_inequality(self):
        """Different business key components produce different scope dicts."""
        row_a = SimpleNamespace(
            season_id=2026,
            destination_factory_id=10,
            capacity_pool_code="BLUE",
        )
        row_b = SimpleNamespace(
            season_id=2026,
            destination_factory_id=10,
            capacity_pool_code="STRAW",
        )
        scope_a = _extract_scope(AuthorityFamily.CAPACITY_POOL_DEFINITION, row_a)
        scope_b = _extract_scope(AuthorityFamily.CAPACITY_POOL_DEFINITION, row_b)
        assert scope_a != scope_b


# ═══════════════════════════════════════════════════════════════════════
# 4. Error classification
# ═══════════════════════════════════════════════════════════════════════


class TestErrorCodes:
    """Every repository error carries the correct stable code and details."""

    def test_error_hash_conflict(self):
        """AuthorityHashConflictError has correct code and details."""
        err = AuthorityHashConflictError(
            expected_hash="aaa111",
            actual_hash="bbb222",
        )
        assert err.code == "AUTHORITY_HASH_CONFLICT"
        assert err.details == {"expected_hash": "aaa111", "actual_hash": "bbb222"}
        assert err.authority_family is None
        assert err.authority_stable_key is None

    def test_error_hash_conflict_with_family(self):
        err = AuthorityHashConflictError(
            authority_family=AuthorityFamily.DAILY_CAPACITY,
            authority_stable_key="dc:1",
            expected_hash="aaa",
            actual_hash="bbb",
        )
        assert err.authority_family == AuthorityFamily.DAILY_CAPACITY
        assert err.authority_stable_key == "dc:1"

    def test_error_version_conflict(self):
        """AuthorityVersionConflictError has correct code."""
        err = AuthorityVersionConflictError(
            existing_hash="old_hash",
            submitted_hash="new_hash",
        )
        assert err.code == "AUTHORITY_VERSION_CONFLICT"
        assert err.details == {
            "existing_hash": "old_hash",
            "submitted_hash": "new_hash",
        }

    def test_error_supersession_scope(self):
        err = AuthoritySupersessionScopeConflictError(
            authority_family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
            details={"old_scope": {"a": 1}, "new_scope": {"a": 2}},
        )
        assert err.code == "AUTHORITY_SUPERSESSION_SCOPE_CONFLICT"
        assert err.authority_family == AuthorityFamily.CAPACITY_POOL_DEFINITION
        assert "old_scope" in err.details
        assert "new_scope" in err.details

    def test_error_consumability_interval_invalid(self):
        err = AuthorityConsumabilityIntervalInvalidError(
            details={"reason": "from > to"}
        )
        assert err.code == "AUTHORITY_CONSUMABILITY_INTERVAL_INVALID"
        assert err.details["reason"] == "from > to"

    def test_error_consumability_interval_overlap(self):
        err = AuthorityConsumabilityIntervalOverlapError(
            details={"interval_a": "2026-01-01..2026-06-30"}
        )
        assert err.code == "AUTHORITY_CONSUMABILITY_INTERVAL_OVERLAP"
        assert "interval_a" in err.details

    def test_error_consumability_interval_conflict(self):
        err = AuthorityConsumabilityIntervalConflictError()
        assert err.code == "AUTHORITY_CONSUMABILITY_INTERVAL_CONFLICT"
        assert err.details == {}

    def test_error_cohort_mismatch(self):
        err = InitialInventoryCohortMismatchError(
            expected_total="100.00",
            actual_total="99.50",
            cohort_count=5,
        )
        assert err.code == "INITIAL_INVENTORY_COHORT_MISMATCH"
        assert err.details == {
            "expected_total": "100.00",
            "actual_total": "99.50",
            "cohort_count": 5,
        }

    def test_error_pool_grain_invalid(self):
        err = CapacityPoolGrainInvalidError(
            details={"grain": "UNKNOWN"}
        )
        assert err.code == "CAPACITY_POOL_GRAIN_INVALID"
        assert err.details["grain"] == "UNKNOWN"

    def test_error_pool_membership_conflict(self):
        err = CapacityPoolMembershipConflictError()
        assert err.code == "CAPACITY_POOL_MEMBERSHIP_CONFLICT"
        assert err.details == {}

    def test_error_timezone_conflict(self):
        err = RunParameterDependencyTimezoneConflictError(
            details={"package_tz": "UTC", "holiday_tz": "Asia/Shanghai"}
        )
        assert err.code == "RUN_PARAMETER_DEPENDENCY_TIMEZONE_CONFLICT"
        assert "package_tz" in err.details
        assert "holiday_tz" in err.details

    def test_error_dependency_status_conflict(self):
        err = RunParameterDependencyStatusConflictError(
            details={"dependency_status": "retired"}
        )
        assert err.code == "RUN_PARAMETER_DEPENDENCY_STATUS_CONFLICT"
        assert err.details["dependency_status"] == "retired"

    def test_error_still_referenced(self):
        err = AuthorityStillReferencedByActivePackageError(
            authority_family=AuthorityFamily.HOLIDAY_CALENDAR_VERSION,
            authority_stable_key="cal:2026:CN",
            referencing_package_ids=[101, 202, 303],
        )
        assert err.code == "AUTHORITY_STILL_REFERENCED_BY_ACTIVE_PACKAGE"
        assert err.authority_family == AuthorityFamily.HOLIDAY_CALENDAR_VERSION
        assert err.authority_stable_key == "cal:2026:CN"
        assert err.details["referencing_package_ids"] == [101, 202, 303]

    def test_error_holiday_hash_mismatch(self):
        err = HolidayCalendarHashMismatchError(
            expected_hash="hash_a",
            actual_hash="hash_b",
        )
        assert err.code == "HOLIDAY_CALENDAR_HASH_MISMATCH"
        assert err.details == {"expected_hash": "hash_a", "actual_hash": "hash_b"}

    def test_error_weather_hash_mismatch(self):
        err = WeatherRuleConfigHashMismatchError(
            expected_hash="whash_a",
            actual_hash="whash_b",
        )
        assert err.code == "WEATHER_RULE_CONFIG_HASH_MISMATCH"
        assert err.details == {"expected_hash": "whash_a", "actual_hash": "whash_b"}

    def test_error_lifecycle_transition_invalid(self):
        err = LifecycleTransitionInvalidError(
            authority_family=AuthorityFamily.DAILY_CAPACITY,
            authority_stable_key="dc:1",
            current_status="active",
            target_status="draft",
        )
        assert err.code == "LIFECYCLE_TRANSITION_INVALID"
        assert err.authority_family == AuthorityFamily.DAILY_CAPACITY
        assert err.authority_stable_key == "dc:1"
        assert err.details == {
            "current_status": "active",
            "target_status": "draft",
        }

    def test_error_dependency_not_found(self):
        err = DependencyNotFoundError(
            authority_family=AuthorityFamily.RUN_PARAMETER_PACKAGE,
            authority_stable_key="rp:1",
        )
        assert err.code == "DEPENDENCY_NOT_FOUND"
        assert err.authority_family == AuthorityFamily.RUN_PARAMETER_PACKAGE
        assert err.authority_stable_key == "rp:1"
        assert err.details == {}

    def test_error_authority_not_found(self):
        err = AuthorityNotFoundError(
            authority_family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
            lookup_key="pool:2026:F1:BLUE:v1:1",
        )
        assert err.code == "AUTHORITY_NOT_FOUND"
        assert err.authority_family == AuthorityFamily.CAPACITY_POOL_DEFINITION
        assert err.details == {"lookup_key": "pool:2026:F1:BLUE:v1:1"}

    def test_all_errors_inherit_base(self):
        """All concrete errors are instances of the base Exception."""
        from backend.app.harvest_state.authority_repository_errors import (
            Task9AuthorityRepositoryError,
        )

        error_classes = [
            AuthorityHashConflictError,
            AuthorityVersionConflictError,
            AuthoritySupersessionScopeConflictError,
            AuthorityConsumabilityIntervalInvalidError,
            AuthorityConsumabilityIntervalOverlapError,
            AuthorityConsumabilityIntervalConflictError,
            InitialInventoryCohortMismatchError,
            CapacityPoolGrainInvalidError,
            CapacityPoolMembershipConflictError,
            RunParameterDependencyTimezoneConflictError,
            RunParameterDependencyStatusConflictError,
            AuthorityStillReferencedByActivePackageError,
            HolidayCalendarHashMismatchError,
            WeatherRuleConfigHashMismatchError,
            LifecycleTransitionInvalidError,
            DependencyNotFoundError,
            AuthorityNotFoundError,
        ]
        for cls in error_classes:
            assert issubclass(cls, Task9AuthorityRepositoryError), (
                f"{cls.__name__} does not inherit from Task9AuthorityRepositoryError"
            )

    def test_all_error_codes_are_distinct(self):
        """Every error class produces a unique code string."""
        # Instantiate each with minimal valid args
        instances = [
            AuthorityHashConflictError(expected_hash="a", actual_hash="b"),
            AuthorityVersionConflictError(existing_hash="a", submitted_hash="b"),
            AuthoritySupersessionScopeConflictError(),
            AuthorityConsumabilityIntervalInvalidError(),
            AuthorityConsumabilityIntervalOverlapError(),
            AuthorityConsumabilityIntervalConflictError(),
            InitialInventoryCohortMismatchError(
                expected_total="0", actual_total="0", cohort_count=0
            ),
            CapacityPoolGrainInvalidError(),
            CapacityPoolMembershipConflictError(),
            RunParameterDependencyTimezoneConflictError(),
            RunParameterDependencyStatusConflictError(),
            AuthorityStillReferencedByActivePackageError(referencing_package_ids=[]),
            HolidayCalendarHashMismatchError(expected_hash="a", actual_hash="b"),
            WeatherRuleConfigHashMismatchError(expected_hash="a", actual_hash="b"),
            LifecycleTransitionInvalidError(
                current_status="draft", target_status="active"
            ),
            DependencyNotFoundError(),
            AuthorityNotFoundError(lookup_key="k"),
        ]
        codes = [e.code for e in instances]
        assert len(codes) == len(set(codes)), f"Duplicate codes found: {codes}"


# ═══════════════════════════════════════════════════════════════════════
# 5. Result types
# ═══════════════════════════════════════════════════════════════════════


class TestResultTypes:
    """Result dataclasses are frozen and carry correct field values."""

    def test_create_result_frozen(self):
        """AuthorityCreateResult is frozen (immutable)."""
        result = AuthorityCreateResult(
            authority_id=42,
            row_hash="abc123",
            created=True,
            lifecycle_event_id=7,
        )
        assert result.authority_id == 42
        assert result.row_hash == "abc123"
        assert result.created is True
        assert result.lifecycle_event_id == 7
        with pytest.raises(AttributeError):
            result.authority_id = 99  # type: ignore[misc]

    def test_create_result_no_lifecycle_event(self):
        result = AuthorityCreateResult(
            authority_id=1,
            row_hash="h",
            created=False,
            lifecycle_event_id=None,
        )
        assert result.lifecycle_event_id is None
        assert result.created is False

    def test_bundle_create_result_parent_and_children(self):
        """Bundle result carries parent and child_ids."""
        parent = AuthorityCreateResult(
            authority_id=10,
            row_hash="parent_hash",
            created=True,
            lifecycle_event_id=5,
        )
        bundle = AuthorityBundleCreateResult(
            parent=parent,
            child_ids=[11, 12, 13],
        )
        assert bundle.parent is parent
        assert bundle.parent.authority_id == 10
        assert bundle.child_ids == [11, 12, 13]
        assert len(bundle.child_ids) == 3

    def test_bundle_create_result_frozen(self):
        parent = AuthorityCreateResult(
            authority_id=1, row_hash="h", created=True, lifecycle_event_id=None
        )
        bundle = AuthorityBundleCreateResult(parent=parent, child_ids=[2])
        with pytest.raises(AttributeError):
            bundle.child_ids = [3]  # type: ignore[misc]

    def test_load_result_fields(self):
        """AuthorityLoadResult has all expected fields."""
        result = AuthorityLoadResult(
            authority_id=55,
            row_hash="load_hash",
            status="active",
            consumable_from_local_date=date(2026, 1, 1),
            consumable_to_local_date=date(2026, 12, 31),
            superseded_by_id=None,
        )
        assert result.authority_id == 55
        assert result.row_hash == "load_hash"
        assert result.status == "active"
        assert result.consumable_from_local_date == date(2026, 1, 1)
        assert result.consumable_to_local_date == date(2026, 12, 31)
        assert result.superseded_by_id is None

    def test_load_result_superseded(self):
        result = AuthorityLoadResult(
            authority_id=56,
            row_hash="old_hash",
            status="superseded",
            consumable_from_local_date=date(2026, 1, 1),
            consumable_to_local_date=date(2026, 6, 30),
            superseded_by_id=57,
        )
        assert result.superseded_by_id == 57
        assert result.status == "superseded"

    def test_load_result_frozen(self):
        result = AuthorityLoadResult(
            authority_id=1,
            row_hash="h",
            status="draft",
            consumable_from_local_date=None,
            consumable_to_local_date=None,
            superseded_by_id=None,
        )
        with pytest.raises(AttributeError):
            result.status = "active"  # type: ignore[misc]

    def test_lifecycle_transition_result_fields(self):
        """LifecycleTransitionResult has all expected fields."""
        result = LifecycleTransitionResult(
            authority_id=42,
            new_status="active",
            lifecycle_event_id=100,
            new_consumable_from=date(2026, 1, 1),
            new_consumable_to=date(2026, 12, 31),
        )
        assert result.authority_id == 42
        assert result.new_status == "active"
        assert result.lifecycle_event_id == 100
        assert result.new_consumable_from == date(2026, 1, 1)
        assert result.new_consumable_to == date(2026, 12, 31)

    def test_lifecycle_transition_result_frozen(self):
        result = LifecycleTransitionResult(
            authority_id=1,
            new_status="draft",
            lifecycle_event_id=1,
            new_consumable_from=None,
            new_consumable_to=None,
        )
        with pytest.raises(AttributeError):
            result.new_status = "active"  # type: ignore[misc]

    def test_supersession_result_fields(self):
        """SupersessionResult has all expected fields."""
        old_transition = LifecycleTransitionResult(
            authority_id=10,
            new_status="superseded",
            lifecycle_event_id=50,
            new_consumable_from=date(2026, 1, 1),
            new_consumable_to=date(2026, 6, 30),
        )
        new_create = AuthorityCreateResult(
            authority_id=11,
            row_hash="new_hash",
            created=True,
            lifecycle_event_id=51,
        )
        new_activation = LifecycleTransitionResult(
            authority_id=11,
            new_status="active",
            lifecycle_event_id=52,
            new_consumable_from=date(2026, 7, 1),
            new_consumable_to=date(2026, 12, 31),
        )
        result = SupersessionResult(
            old=old_transition,
            new=new_create,
            new_activation=new_activation,
        )
        assert result.old.authority_id == 10
        assert result.old.new_status == "superseded"
        assert result.new.authority_id == 11
        assert result.new.row_hash == "new_hash"
        assert result.new_activation.authority_id == 11
        assert result.new_activation.new_status == "active"
        assert result.new_activation.new_consumable_from == date(2026, 7, 1)

    def test_supersession_result_frozen(self):
        old = LifecycleTransitionResult(
            authority_id=1, new_status="superseded", lifecycle_event_id=1,
            new_consumable_from=None, new_consumable_to=None,
        )
        new = AuthorityCreateResult(
            authority_id=2, row_hash="h", created=True, lifecycle_event_id=2,
        )
        result = SupersessionResult(old=old, new=new, new_activation=old)
        with pytest.raises(AttributeError):
            result.old = new  # type: ignore[misc]

    def test_bundle_load_result_fields(self):
        """AuthorityBundleLoadResult has all expected fields."""
        parent = AuthorityLoadResult(
            authority_id=20,
            row_hash="parent_h",
            status="active",
            consumable_from_local_date=date(2026, 1, 1),
            consumable_to_local_date=date(2026, 12, 31),
            superseded_by_id=None,
        )
        bundle = AuthorityBundleLoadResult(
            parent=parent,
            child_hashes=["ch1", "ch2"],
        )
        assert bundle.parent is parent
        assert bundle.parent.authority_id == 20
        assert bundle.child_hashes == ["ch1", "ch2"]

    def test_bundle_load_result_frozen(self):
        parent = AuthorityLoadResult(
            authority_id=1, row_hash="h", status="draft",
            consumable_from_local_date=None, consumable_to_local_date=None,
            superseded_by_id=None,
        )
        bundle = AuthorityBundleLoadResult(parent=parent, child_hashes=[])
        with pytest.raises(AttributeError):
            bundle.child_hashes = ["x"]  # type: ignore[misc]
