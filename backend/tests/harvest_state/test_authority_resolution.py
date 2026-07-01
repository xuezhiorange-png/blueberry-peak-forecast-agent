from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from backend.app.harvest_state.authority_resolution import (
    AuthorityCandidateSnapshot,
    AuthorityExactReference,
    _candidate_is_consumable_at_as_of,
    _candidate_is_current_operational,
    _choose_candidate_snapshot,
    _validate_timezone_name,
)
from backend.app.harvest_state.authority_resolution_errors import (
    AmbiguousHistoricalAuthorityError,
    TimezoneAuthorityInvalidError,
)
from backend.app.harvest_state.enums import AuthorityFamily, AuthorityStatus


def _snapshot(
    *,
    authority_id: int = 1,
    status: str = AuthorityStatus.ACTIVE,
    available_at_local_date: date = date(2026, 1, 1),
    consumable_from_local_date: date | None = date(2026, 1, 1),
    consumable_to_local_date: date | None = None,
    authority_stable_key: str = "capacity-pool:1:2:POOL-A",
    business_version: str = "v1",
    revision: int = 1,
    row_hash: str = "a" * 64,
) -> AuthorityCandidateSnapshot:
    return AuthorityCandidateSnapshot(
        authority_id=authority_id,
        authority_family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
        authority_stable_key=authority_stable_key,
        business_version=business_version,
        revision=revision,
        row_hash=row_hash,
        status=status,
        available_at_local_date=available_at_local_date,
        consumable_from_local_date=consumable_from_local_date,
        consumable_to_local_date=consumable_to_local_date,
    )


def test_current_operational_predicate_requires_active_open_and_visible() -> None:
    accepted = _snapshot()
    assert _candidate_is_current_operational(accepted, as_of_local_date=date(2026, 3, 1)) is True

    assert (
        _candidate_is_current_operational(
            replace(accepted, status=AuthorityStatus.SUPERSEDED),
            as_of_local_date=date(2026, 3, 1),
        )
        is False
    )
    assert (
        _candidate_is_current_operational(
            replace(accepted, consumable_from_local_date=None),
            as_of_local_date=date(2026, 3, 1),
        )
        is False
    )
    assert (
        _candidate_is_current_operational(
            replace(accepted, consumable_to_local_date=date(2026, 3, 2)),
            as_of_local_date=date(2026, 3, 1),
        )
        is False
    )
    assert (
        _candidate_is_current_operational(
            replace(accepted, available_at_local_date=date(2026, 3, 2)),
            as_of_local_date=date(2026, 3, 1),
        )
        is False
    )


def test_historical_predicate_uses_half_open_interval_and_excludes_draft_cancelled() -> None:
    historical = _snapshot(consumable_to_local_date=date(2026, 6, 1))
    assert _candidate_is_consumable_at_as_of(historical, as_of_local_date=date(2026, 5, 31)) is True
    assert _candidate_is_consumable_at_as_of(historical, as_of_local_date=date(2026, 6, 1)) is False

    assert (
        _candidate_is_consumable_at_as_of(
            replace(historical, status=AuthorityStatus.DRAFT),
            as_of_local_date=date(2026, 5, 31),
        )
        is False
    )
    assert (
        _candidate_is_consumable_at_as_of(
            replace(historical, status=AuthorityStatus.CANCELLED),
            as_of_local_date=date(2026, 5, 31),
        )
        is False
    )


def test_choose_candidate_snapshot_ignores_database_id_for_equivalent_duplicates() -> None:
    winner = _snapshot(authority_id=10)
    duplicate = _snapshot(authority_id=999)

    chosen = _choose_candidate_snapshot(
        [duplicate, winner],
        authority_family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
        as_of_local_date=date(2026, 3, 1),
        reason="equivalent_duplicate",
    )

    assert chosen.authority_stable_key == winner.authority_stable_key
    assert chosen.business_version == winner.business_version
    assert chosen.revision == winner.revision
    assert chosen.row_hash == winner.row_hash


def test_choose_candidate_snapshot_rejects_same_priority_semantic_conflict() -> None:
    winner = _snapshot()
    conflicting = _snapshot(row_hash="b" * 64)

    with pytest.raises(AmbiguousHistoricalAuthorityError) as exc_info:
        _choose_candidate_snapshot(
            [winner, conflicting],
            authority_family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
            as_of_local_date=date(2026, 3, 1),
            reason="same_priority_conflict",
        )

    assert exc_info.value.code == "AMBIGUOUS_HISTORICAL_AUTHORITY"
    assert exc_info.value.details["reason"] == "same_priority_conflict"


def test_validate_timezone_name_rejects_invalid_name() -> None:
    with pytest.raises(TimezoneAuthorityInvalidError) as exc_info:
        _validate_timezone_name("Mars/Olympus")

    assert exc_info.value.code == "TIMEZONE_AUTHORITY_INVALID"


def test_exact_reference_is_typed() -> None:
    reference = AuthorityExactReference(
        authority_id=11,
        authority_stable_key="capacity-pool:1:2:POOL-A",
        business_version="v1",
        revision=2,
        row_hash="f" * 64,
    )
    assert reference.authority_id == 11
    assert reference.authority_stable_key.endswith("POOL-A")


# ---------------------------------------------------------------------------
# P1-1 boundary coverage & P0-7D unit tests
# ---------------------------------------------------------------------------


def test_current_operational_requires_consumable_from_before_as_of() -> None:
    """Boundary: consumable_from == as_of counts as visible; before also works; before boundary fails."""
    snap = _snapshot(
        consumable_from_local_date=date(2026, 6, 15),
        available_at_local_date=date(2026, 1, 1),
    )
    # as_of is before consumable_from → not yet consumable
    assert _candidate_is_current_operational(snap, as_of_local_date=date(2026, 6, 10)) is False
    # as_of == consumable_from → inclusive lower bound
    assert _candidate_is_current_operational(snap, as_of_local_date=date(2026, 6, 15)) is True
    # as_of is after consumable_from → clearly consumable
    assert _candidate_is_current_operational(snap, as_of_local_date=date(2026, 6, 20)) is True


def test_current_operational_rejects_future_consumable_from() -> None:
    """consumable_from in the future relative to as_of must be rejected."""
    snap = _snapshot(
        consumable_from_local_date=date(2026, 7, 1),
        available_at_local_date=date(2026, 1, 1),
    )
    assert _candidate_is_current_operational(snap, as_of_local_date=date(2026, 6, 1)) is False


def test_current_operational_rejects_draft_status() -> None:
    """Draft status must not be considered current operational."""
    snap = _snapshot(status=AuthorityStatus.DRAFT)
    assert _candidate_is_current_operational(snap, as_of_local_date=date(2026, 6, 1)) is False


def test_current_operational_rejects_consumable_to_set() -> None:
    """Setting consumable_to_local_date means the authority is no longer current operational."""
    snap = _snapshot(consumable_to_local_date=date(2099, 12, 31))
    assert _candidate_is_current_operational(snap, as_of_local_date=date(2026, 6, 1)) is False


def test_validate_timezone_name_accepts_valid_name() -> None:
    """Valid IANA timezone names must not raise."""
    assert _validate_timezone_name("Asia/Shanghai") == "Asia/Shanghai"
    assert _validate_timezone_name("UTC") == "UTC"


def test_historical_consumable_accepts_superseded() -> None:
    """Superseded status is accepted by the historical consumable predicate when in range."""
    snap = _snapshot(
        status=AuthorityStatus.SUPERSEDED,
        consumable_from_local_date=date(2026, 1, 1),
        consumable_to_local_date=date(2026, 6, 30),
        available_at_local_date=date(2026, 1, 1),
    )
    assert _candidate_is_consumable_at_as_of(snap, as_of_local_date=date(2026, 6, 15)) is True


def test_historical_consumable_rejects_draft() -> None:
    """Draft status is not consumable at any as_of date."""
    snap = _snapshot(
        status=AuthorityStatus.DRAFT,
        consumable_from_local_date=date(2026, 1, 1),
        consumable_to_local_date=date(2026, 6, 30),
        available_at_local_date=date(2026, 1, 1),
    )
    assert _candidate_is_consumable_at_as_of(snap, as_of_local_date=date(2026, 6, 15)) is False
