"""Typed repository exceptions for Task 9 authority domain.

Every exception carries a stable ``code`` string, optional ``authority_family``,
optional ``authority_stable_key``, and a structured ``details`` dict.
Downstream consumers (P0-7D resolver, API) must classify by code — never by
parsing message text or IntegrityError strings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.app.harvest_state.enums import AuthorityFamily


@dataclass(slots=True)
class Task9AuthorityRepositoryError(Exception):
    """Base repository error with stable code and structured details."""

    code: str
    authority_family: AuthorityFamily | None = None
    authority_stable_key: str | None = None
    details: dict[str, object] = field(default_factory=dict)

    def __str__(self) -> str:
        parts = [self.code]
        if self.authority_family is not None:
            parts.append(f"family={self.authority_family}")
        if self.authority_stable_key is not None:
            parts.append(f"key={self.authority_stable_key}")
        if self.details:
            parts.append(str(self.details))
        return " | ".join(parts)


# ── Error codes ────────────────────────────────────────────────────────

_AUTHORITY_HASH_CONFLICT = "AUTHORITY_HASH_CONFLICT"
_AUTHORITY_VERSION_CONFLICT = "AUTHORITY_VERSION_CONFLICT"
_AUTHORITY_SUPERSESSION_SCOPE_CONFLICT = "AUTHORITY_SUPERSESSION_SCOPE_CONFLICT"
_AUTHORITY_CONSUMABILITY_INTERVAL_INVALID = "AUTHORITY_CONSUMABILITY_INTERVAL_INVALID"
_AUTHORITY_CONSUMABILITY_INTERVAL_OVERLAP = "AUTHORITY_CONSUMABILITY_INTERVAL_OVERLAP"
_AUTHORITY_CONSUMABILITY_INTERVAL_CONFLICT = "AUTHORITY_CONSUMABILITY_INTERVAL_CONFLICT"
_INITIAL_INVENTORY_COHORT_MISMATCH = "INITIAL_INVENTORY_COHORT_MISMATCH"
_CAPACITY_POOL_GRAIN_INVALID = "CAPACITY_POOL_GRAIN_INVALID"
_CAPACITY_POOL_MEMBERSHIP_CONFLICT = "CAPACITY_POOL_MEMBERSHIP_CONFLICT"
_RUN_PARAMETER_DEPENDENCY_TIMEZONE_CONFLICT = "RUN_PARAMETER_DEPENDENCY_TIMEZONE_CONFLICT"
_RUN_PARAMETER_DEPENDENCY_STATUS_CONFLICT = "RUN_PARAMETER_DEPENDENCY_STATUS_CONFLICT"
_AUTHORITY_STILL_REFERENCED_BY_ACTIVE_PACKAGE = "AUTHORITY_STILL_REFERENCED_BY_ACTIVE_PACKAGE"
_HOLIDAY_CALENDAR_HASH_MISMATCH = "HOLIDAY_CALENDAR_HASH_MISMATCH"
_WEATHER_RULE_CONFIG_HASH_MISMATCH = "WEATHER_RULE_CONFIG_HASH_MISMATCH"
_LIFECYCLE_TRANSITION_INVALID = "LIFECYCLE_TRANSITION_INVALID"
_DEPENDENCY_NOT_FOUND = "DEPENDENCY_NOT_FOUND"
_AUTHORITY_NOT_FOUND = "AUTHORITY_NOT_FOUND"


class AuthorityHashConflictError(Task9AuthorityRepositoryError):
    """Submitted row_hash does not match recomputed canonical hash."""

    def __init__(
        self,
        *,
        authority_family: AuthorityFamily | None = None,
        authority_stable_key: str | None = None,
        expected_hash: str,
        actual_hash: str,
        details: dict[str, object] | None = None,
    ) -> None:
        payload: dict[str, object] = {
            "expected_hash": expected_hash,
            "actual_hash": actual_hash,
        }
        if details:
            payload.update(details)
        super().__init__(
            code=_AUTHORITY_HASH_CONFLICT,
            authority_family=authority_family,
            authority_stable_key=authority_stable_key,
            details=payload,
        )


class AuthorityVersionConflictError(Task9AuthorityRepositoryError):
    """Same business key but different canonical payload already persisted."""

    def __init__(
        self,
        *,
        authority_family: AuthorityFamily | None = None,
        authority_stable_key: str | None = None,
        existing_hash: str,
        submitted_hash: str,
    ) -> None:
        super().__init__(
            code=_AUTHORITY_VERSION_CONFLICT,
            authority_family=authority_family,
            authority_stable_key=authority_stable_key,
            details={"existing_hash": existing_hash, "submitted_hash": submitted_hash},
        )


class AuthoritySupersessionScopeConflictError(Task9AuthorityRepositoryError):
    """Replacement row does not match the same frozen business scope."""

    def __init__(
        self,
        *,
        authority_family: AuthorityFamily | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(
            code=_AUTHORITY_SUPERSESSION_SCOPE_CONFLICT,
            authority_family=authority_family,
            details=details or {},
        )


class AuthorityConsumabilityIntervalInvalidError(Task9AuthorityRepositoryError):
    """Consumability interval is structurally invalid."""

    def __init__(self, *, details: dict[str, object] | None = None) -> None:
        super().__init__(
            code=_AUTHORITY_CONSUMABILITY_INTERVAL_INVALID,
            details=details or {},
        )


class AuthorityConsumabilityIntervalOverlapError(Task9AuthorityRepositoryError):
    """Two authorities in the same scope have overlapping consumability intervals."""

    def __init__(self, *, details: dict[str, object] | None = None) -> None:
        super().__init__(
            code=_AUTHORITY_CONSUMABILITY_INTERVAL_OVERLAP,
            details=details or {},
        )


class AuthorityConsumabilityIntervalConflictError(Task9AuthorityRepositoryError):
    """Replacement boundary does not match old consumable_to."""

    def __init__(self, *, details: dict[str, object] | None = None) -> None:
        super().__init__(
            code=_AUTHORITY_CONSUMABILITY_INTERVAL_CONFLICT,
            details=details or {},
        )


class InitialInventoryCohortMismatchError(Task9AuthorityRepositoryError):
    """Sum of cohort quantities does not equal header total."""

    def __init__(
        self,
        *,
        expected_total: str,
        actual_total: str,
        cohort_count: int,
    ) -> None:
        super().__init__(
            code=_INITIAL_INVENTORY_COHORT_MISMATCH,
            authority_family=None,
            details={
                "expected_total": expected_total,
                "actual_total": actual_total,
                "cohort_count": cohort_count,
            },
        )


class CapacityPoolGrainInvalidError(Task9AuthorityRepositoryError):
    """Pool grain rules violated."""

    def __init__(self, *, details: dict[str, object] | None = None) -> None:
        super().__init__(
            code=_CAPACITY_POOL_GRAIN_INVALID,
            authority_family=None,
            details=details or {},
        )


class CapacityPoolMembershipConflictError(Task9AuthorityRepositoryError):
    """Duplicate or inconsistent pool membership."""

    def __init__(self, *, details: dict[str, object] | None = None) -> None:
        super().__init__(
            code=_CAPACITY_POOL_MEMBERSHIP_CONFLICT,
            authority_family=None,
            details=details or {},
        )


class RunParameterDependencyTimezoneConflictError(Task9AuthorityRepositoryError):
    """Package/holiday/weather timezone mismatch."""

    def __init__(self, *, details: dict[str, object] | None = None) -> None:
        super().__init__(
            code=_RUN_PARAMETER_DEPENDENCY_TIMEZONE_CONFLICT,
            authority_family=None,
            details=details or {},
        )


class RunParameterDependencyStatusConflictError(Task9AuthorityRepositoryError):
    """Dependency is not in a compatible status."""

    def __init__(self, *, details: dict[str, object] | None = None) -> None:
        super().__init__(
            code=_RUN_PARAMETER_DEPENDENCY_STATUS_CONFLICT,
            authority_family=None,
            details=details or {},
        )


class AuthorityStillReferencedByActivePackageError(Task9AuthorityRepositoryError):
    """Cannot transition a dependency that is still referenced by an active package."""

    def __init__(
        self,
        *,
        authority_family: AuthorityFamily | None = None,
        authority_stable_key: str | None = None,
        referencing_package_ids: list[int],
        details: dict[str, object] | None = None,
    ) -> None:
        payload: dict[str, object] = {"referencing_package_ids": referencing_package_ids}
        if details:
            payload.update(details)
        super().__init__(
            code=_AUTHORITY_STILL_REFERENCED_BY_ACTIVE_PACKAGE,
            authority_family=authority_family,
            authority_stable_key=authority_stable_key,
            details=payload,
        )


class HolidayCalendarHashMismatchError(Task9AuthorityRepositoryError):
    """Calendar hash does not match recomputed value from sorted dates."""

    def __init__(
        self,
        *,
        expected_hash: str,
        actual_hash: str,
    ) -> None:
        super().__init__(
            code=_HOLIDAY_CALENDAR_HASH_MISMATCH,
            details={"expected_hash": expected_hash, "actual_hash": actual_hash},
        )


class WeatherRuleConfigHashMismatchError(Task9AuthorityRepositoryError):
    """Config hash does not match recomputed value."""

    def __init__(
        self,
        *,
        expected_hash: str,
        actual_hash: str,
    ) -> None:
        super().__init__(
            code=_WEATHER_RULE_CONFIG_HASH_MISMATCH,
            details={"expected_hash": expected_hash, "actual_hash": actual_hash},
        )


class LifecycleTransitionInvalidError(Task9AuthorityRepositoryError):
    """Requested lifecycle transition is not allowed."""

    def __init__(
        self,
        *,
        authority_family: AuthorityFamily | None = None,
        authority_stable_key: str | None = None,
        current_status: str,
        target_status: str,
        details: dict[str, object] | None = None,
    ) -> None:
        payload: dict[str, object] = {
            "current_status": current_status,
            "target_status": target_status,
        }
        if details:
            payload.update(details)
        super().__init__(
            code=_LIFECYCLE_TRANSITION_INVALID,
            authority_family=authority_family,
            authority_stable_key=authority_stable_key,
            details=payload,
        )


class DependencyNotFoundError(Task9AuthorityRepositoryError):
    """Required dependency not found."""

    def __init__(
        self,
        *,
        authority_family: AuthorityFamily | None = None,
        authority_stable_key: str | None = None,
    ) -> None:
        super().__init__(
            code=_DEPENDENCY_NOT_FOUND,
            authority_family=authority_family,
            authority_stable_key=authority_stable_key,
        )


class AuthorityNotFoundError(Task9AuthorityRepositoryError):
    """Requested authority not found."""

    def __init__(
        self,
        *,
        authority_family: AuthorityFamily | None = None,
        lookup_key: str,
    ) -> None:
        super().__init__(
            code=_AUTHORITY_NOT_FOUND,
            authority_family=authority_family,
            details={"lookup_key": lookup_key},
        )
