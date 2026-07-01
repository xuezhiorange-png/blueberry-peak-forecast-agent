from __future__ import annotations

from datetime import date

from backend.app.harvest_state.authority_repository_errors import (
    Task9AuthorityRepositoryError,
)
from backend.app.harvest_state.enums import AuthorityFamily


class HistoricalAuthorityNotFoundError(Task9AuthorityRepositoryError):
    def __init__(
        self,
        *,
        authority_family: AuthorityFamily,
        as_of_local_date: date,
        business_key: str,
        details: dict[str, object] | None = None,
    ) -> None:
        payload: dict[str, object] = {
            "reason": "historical_authority_not_found",
            "as_of_local_date": as_of_local_date.isoformat(),
            "business_key": business_key,
        }
        if details:
            payload.update(details)
        super().__init__(
            code="HISTORICAL_AUTHORITY_NOT_FOUND",
            authority_family=authority_family,
            authority_stable_key=business_key,
            details=payload,
        )


class AmbiguousHistoricalAuthorityError(Task9AuthorityRepositoryError):
    def __init__(
        self,
        *,
        authority_family: AuthorityFamily,
        as_of_local_date: date,
        business_key: str,
        details: dict[str, object] | None = None,
    ) -> None:
        payload: dict[str, object] = {
            "reason": "ambiguous_historical_authority",
            "as_of_local_date": as_of_local_date.isoformat(),
            "business_key": business_key,
        }
        if details:
            payload.update(details)
        super().__init__(
            code="AMBIGUOUS_HISTORICAL_AUTHORITY",
            authority_family=authority_family,
            authority_stable_key=business_key,
            details=payload,
        )


class AuthorityNotConsumableAtCutoffError(Task9AuthorityRepositoryError):
    def __init__(
        self,
        *,
        authority_family: AuthorityFamily,
        authority_stable_key: str,
        as_of_local_date: date,
        details: dict[str, object] | None = None,
    ) -> None:
        payload: dict[str, object] = {
            "reason": "authority_not_consumable_at_cutoff",
            "as_of_local_date": as_of_local_date.isoformat(),
        }
        if details:
            payload.update(details)
        super().__init__(
            code="AUTHORITY_NOT_CONSUMABLE_AT_CUTOFF",
            authority_family=authority_family,
            authority_stable_key=authority_stable_key,
            details=payload,
        )


class AuthorityEffectiveIntervalMismatchError(Task9AuthorityRepositoryError):
    def __init__(
        self,
        *,
        authority_family: AuthorityFamily,
        authority_stable_key: str,
        target_local_date: date,
        details: dict[str, object] | None = None,
    ) -> None:
        payload: dict[str, object] = {
            "reason": "authority_effective_interval_mismatch",
            "target_local_date": target_local_date.isoformat(),
        }
        if details:
            payload.update(details)
        super().__init__(
            code="AUTHORITY_EFFECTIVE_INTERVAL_MISMATCH",
            authority_family=authority_family,
            authority_stable_key=authority_stable_key,
            details=payload,
        )


class AuthorityScopeMismatchError(Task9AuthorityRepositoryError):
    def __init__(
        self,
        *,
        authority_family: AuthorityFamily,
        authority_stable_key: str,
        details: dict[str, object] | None = None,
    ) -> None:
        payload: dict[str, object] = {"reason": "authority_scope_mismatch"}
        if details:
            payload.update(details)
        super().__init__(
            code="AUTHORITY_SCOPE_MISMATCH",
            authority_family=authority_family,
            authority_stable_key=authority_stable_key,
            details=payload,
        )


class AuthorityDependencyMismatchError(Task9AuthorityRepositoryError):
    def __init__(
        self,
        *,
        authority_family: AuthorityFamily,
        authority_stable_key: str,
        details: dict[str, object] | None = None,
    ) -> None:
        payload: dict[str, object] = {"reason": "authority_dependency_mismatch"}
        if details:
            payload.update(details)
        super().__init__(
            code="AUTHORITY_DEPENDENCY_MISMATCH",
            authority_family=authority_family,
            authority_stable_key=authority_stable_key,
            details=payload,
        )


class AuthorityParentChildMismatchError(Task9AuthorityRepositoryError):
    def __init__(
        self,
        *,
        authority_family: AuthorityFamily,
        authority_stable_key: str,
        details: dict[str, object] | None = None,
    ) -> None:
        payload: dict[str, object] = {"reason": "authority_parent_child_mismatch"}
        if details:
            payload.update(details)
        super().__init__(
            code="AUTHORITY_PARENT_CHILD_MISMATCH",
            authority_family=authority_family,
            authority_stable_key=authority_stable_key,
            details=payload,
        )


class AuthorityExactReferenceMismatchError(Task9AuthorityRepositoryError):
    def __init__(
        self,
        *,
        authority_family: AuthorityFamily,
        authority_stable_key: str,
        details: dict[str, object] | None = None,
    ) -> None:
        payload: dict[str, object] = {"reason": "authority_exact_reference_mismatch"}
        if details:
            payload.update(details)
        super().__init__(
            code="AUTHORITY_EXACT_REFERENCE_MISMATCH",
            authority_family=authority_family,
            authority_stable_key=authority_stable_key,
            details=payload,
        )


class TimezoneAuthorityInvalidError(Task9AuthorityRepositoryError):
    def __init__(self, *, timezone_name: str) -> None:
        super().__init__(
            code="TIMEZONE_AUTHORITY_INVALID",
            authority_family=None,
            authority_stable_key=None,
            details={
                "reason": "timezone_authority_invalid",
                "timezone_name": timezone_name,
            },
        )
