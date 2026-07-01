from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class AuthorityCreateResult:
    """Returned by create-or-load operations."""
    authority_id: int
    row_hash: str
    created: bool
    lifecycle_event_id: int | None


@dataclass(frozen=True, slots=True)
class AuthorityLoadResult:
    """Returned by exact load operations."""
    authority_id: int
    row_hash: str
    status: str
    consumable_from_local_date: date | None
    consumable_to_local_date: date | None
    superseded_by_id: int | None


@dataclass(frozen=True, slots=True)
class AuthorityBundleCreateResult:
    """Returned by bundle create-or-load operations."""
    parent: AuthorityCreateResult
    child_ids: list[int]


@dataclass(frozen=True, slots=True)
class AuthorityBundleLoadResult:
    """Returned by bundle load operations."""
    parent: AuthorityLoadResult
    child_hashes: list[str]


@dataclass(frozen=True, slots=True)
class LifecycleTransitionResult:
    """Returned by lifecycle transition operations."""
    authority_id: int
    new_status: str
    lifecycle_event_id: int
    new_consumable_from: date | None
    new_consumable_to: date | None


@dataclass(frozen=True, slots=True)
class SupersessionResult:
    """Returned by supersession operations."""
    old: LifecycleTransitionResult
    new: AuthorityCreateResult
    new_activation: LifecycleTransitionResult
