from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class AuthorityRepositoryError(RuntimeError):
    code: str
    authority_family: str | None = None
    authority_stable_key: str | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        RuntimeError.__init__(self, self.detail or self.code)


class AuthorityNotFoundError(AuthorityRepositoryError):
    def __init__(
        self,
        *,
        authority_family: str | None = None,
        authority_stable_key: str | None = None,
        detail: str | None = None,
    ) -> None:
        super().__init__(
            code="AUTHORITY_NOT_FOUND",
            authority_family=authority_family,
            authority_stable_key=authority_stable_key,
            detail=detail,
        )


class AuthorityVersionConflictError(AuthorityRepositoryError):
    def __init__(
        self,
        *,
        authority_family: str,
        authority_stable_key: str,
        existing_hash: str | None = None,
        submitted_hash: str | None = None,
        detail: str | None = None,
    ) -> None:
        suffix = ""
        if existing_hash is not None and submitted_hash is not None:
            suffix = f" existing_hash={existing_hash} submitted_hash={submitted_hash}"
        super().__init__(
            code="AUTHORITY_VERSION_CONFLICT",
            authority_family=authority_family,
            authority_stable_key=authority_stable_key,
            detail=detail or f"authority version conflict{suffix}",
        )


class AuthorityHashConflictError(AuthorityRepositoryError):
    def __init__(
        self,
        *,
        authority_family: str,
        authority_stable_key: str,
        expected_hash: str | None = None,
        actual_hash: str | None = None,
        detail: str | None = None,
    ) -> None:
        suffix = ""
        if expected_hash is not None and actual_hash is not None:
            suffix = f" expected_hash={expected_hash} actual_hash={actual_hash}"
        super().__init__(
            code="AUTHORITY_HASH_CONFLICT",
            authority_family=authority_family,
            authority_stable_key=authority_stable_key,
            detail=detail or f"authority hash conflict{suffix}",
        )


class LifecycleTransitionInvalidError(AuthorityRepositoryError):
    def __init__(
        self,
        *,
        authority_family: str,
        authority_stable_key: str,
        detail: str | None = None,
    ) -> None:
        super().__init__(
            code="LIFECYCLE_TRANSITION_INVALID",
            authority_family=authority_family,
            authority_stable_key=authority_stable_key,
            detail=detail,
        )


class AuthorityConsumabilityIntervalInvalidError(AuthorityRepositoryError):
    def __init__(
        self,
        *,
        authority_family: str,
        authority_stable_key: str,
        detail: str | None = None,
    ) -> None:
        super().__init__(
            code="AUTHORITY_CONSUMABILITY_INTERVAL_INVALID",
            authority_family=authority_family,
            authority_stable_key=authority_stable_key,
            detail=detail,
        )


class AuthorityConsumabilityIntervalConflictError(AuthorityRepositoryError):
    def __init__(
        self,
        *,
        authority_family: str,
        authority_stable_key: str,
        detail: str | None = None,
    ) -> None:
        super().__init__(
            code="AUTHORITY_CONSUMABILITY_INTERVAL_CONFLICT",
            authority_family=authority_family,
            authority_stable_key=authority_stable_key,
            detail=detail,
        )


class AuthorityConsumabilityIntervalOverlapError(AuthorityRepositoryError):
    def __init__(
        self,
        *,
        authority_family: str,
        authority_stable_key: str,
        detail: str | None = None,
    ) -> None:
        super().__init__(
            code="AUTHORITY_CONSUMABILITY_INTERVAL_OVERLAP",
            authority_family=authority_family,
            authority_stable_key=authority_stable_key,
            detail=detail,
        )


class AuthorityDependencyConflictError(AuthorityRepositoryError):
    def __init__(
        self,
        *,
        authority_family: str,
        authority_stable_key: str,
        detail: str | None = None,
    ) -> None:
        super().__init__(
            code="AUTHORITY_DEPENDENCY_CONFLICT",
            authority_family=authority_family,
            authority_stable_key=authority_stable_key,
            detail=detail,
        )
