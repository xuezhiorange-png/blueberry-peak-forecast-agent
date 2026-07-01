from __future__ import annotations

from backend.app.harvest_state.authority_repository_errors import (
    Task9AuthorityRepositoryError,
)
from backend.app.harvest_state.enums import AuthorityFamily


class Task9AuthorityRequestAssemblyError(Task9AuthorityRepositoryError):
    def __init__(
        self,
        *,
        reason: str,
        authority_family: AuthorityFamily | None = None,
        authority_stable_key: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        payload: dict[str, object] = {"reason": reason}
        if details:
            payload.update(details)
        super().__init__(
            code="TASK9_AUTHORITY_REQUEST_ASSEMBLY_ERROR",
            authority_family=authority_family,
            authority_stable_key=authority_stable_key,
            details=payload,
        )


class Task9AuthorityPoolMembershipConflictError(Task9AuthorityRepositoryError):
    """A pool member is assigned to multiple pools."""

    def __init__(
        self,
        *,
        authority_family: AuthorityFamily | None = None,
        authority_stable_key: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        payload: dict[str, object] = {"reason": "authority_pool_membership_conflict"}
        if details:
            payload.update(details)
        super().__init__(
            code="TASK9_AUTHORITY_REQUEST_ASSEMBLY_ERROR",
            authority_family=authority_family,
            authority_stable_key=authority_stable_key,
            details=payload,
        )


class Task9AuthorityAssemblyCanonicalParityError(Task9AuthorityRepositoryError):
    """Assembly hash / canonical payload parity violation."""

    def __init__(
        self,
        *,
        authority_family: AuthorityFamily | None = None,
        authority_stable_key: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        payload: dict[str, object] = {
            "reason": "authority_assembly_canonical_parity_error",
        }
        if details:
            payload.update(details)
        super().__init__(
            code="TASK9_AUTHORITY_REQUEST_ASSEMBLY_ERROR",
            authority_family=authority_family,
            authority_stable_key=authority_stable_key,
            details=payload,
        )
