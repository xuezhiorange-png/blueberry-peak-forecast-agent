from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

import backend.app.harvest_state.authority_repository as authority_repository
from backend.app.harvest_state.authority_repository import (
    _build_initial_lifecycle_events,
    _verify_lifecycle_chain,
    authority_lock_key,
)
from backend.app.harvest_state.authority_repository_errors import (
    AuthorityConsumabilityIntervalConflictError,
    AuthorityHashConflictError,
    LifecycleTransitionInvalidError,
)
from backend.app.harvest_state.enums import AuthorityFamily, AuthorityStatus
from backend.app.models import Task9AuthorityLifecycleEvent, Task9CapacityPoolDefinition


def test_authority_lock_key_is_deterministic_and_signed_bigint() -> None:
    expected = 5720769477307131196
    result = authority_lock_key(
        family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
        stable_key="x",
        business_version="v1",
        revision=1,
    )
    assert result == expected
    assert (
        authority_lock_key(
            family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
            stable_key="x",
            business_version="v1",
            revision=1,
        )
        == expected
    )
    assert (
        authority_lock_key(
            family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
            stable_key="x",
            business_version="v2",
            revision=1,
        )
        != expected
    )


def test_initial_lifecycle_events_for_active_row_build_null_draft_then_activation() -> None:
    changed_at = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
    events = _build_initial_lifecycle_events(
        family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
        stable_key="capacity-pool:1:2:POOL-A",
        business_version="v1",
        revision=1,
        row_hash="a" * 64,
        status=AuthorityStatus.ACTIVE,
        consumable_from_local_date=date(2026, 1, 2),
        consumable_to_local_date=None,
        status_changed_at=changed_at,
        source_system="task9_historical_authority",
        source_record_key="capacity-pool:1:2:POOL-A:v1:1",
    )
    assert [item.transition_sequence for item in events] == [1, 2]
    assert events[0].old_status is None
    assert events[0].new_status is AuthorityStatus.DRAFT
    assert events[1].old_status is AuthorityStatus.DRAFT
    assert events[1].new_status is AuthorityStatus.ACTIVE
    assert events[1].new_consumable_from_local_date == date(2026, 1, 2)


def _pool_row(*, status: AuthorityStatus = AuthorityStatus.ACTIVE) -> Task9CapacityPoolDefinition:
    return Task9CapacityPoolDefinition(
        id=11,
        season_id=1,
        destination_factory_id=2,
        capacity_pool_code="POOL-A",
        capacity_pool_version="v1",
        revision=1,
        capacity_pool_grain="FARM",
        capacity_input_mode="LABOR_DERIVED",
        effective_from=date(2026, 1, 1),
        effective_to=None,
        available_at_local_date=date(2026, 1, 1),
        consumable_from_local_date=(
            None if status is not AuthorityStatus.ACTIVE else date(2026, 1, 2)
        ),
        consumable_to_local_date=None,
        status=status.value,
        status_changed_at=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        source_system="task9_historical_authority",
        source_record_key="capacity-pool:1:2:POOL-A:v1:1",
        source_version="src-v1",
        row_hash="a" * 64,
        superseded_by_id=None,
    )


def _event(
    *,
    sequence: int,
    old_status: AuthorityStatus | None,
    new_status: AuthorityStatus,
    old_from: date | None,
    old_to: date | None,
    new_from: date | None,
    new_to: date | None,
    business_row_hash: str = "a" * 64,
    replacement_stable_key: str | None = None,
    replacement_version: str | None = None,
    replacement_revision: int | None = None,
) -> Task9AuthorityLifecycleEvent:
    semantic = authority_repository.Task9LifecycleEventSemanticInput(
        authority_family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
        authority_stable_key="capacity-pool:1:2:POOL-A",
        authority_business_version="v1",
        authority_revision=1,
        business_row_hash=business_row_hash,
        transition_sequence=sequence,
        old_status=old_status,
        new_status=new_status,
        old_consumable_from_local_date=old_from,
        old_consumable_to_local_date=old_to,
        new_consumable_from_local_date=new_from,
        new_consumable_to_local_date=new_to,
        superseded_by_authority_stable_key=replacement_stable_key,
        superseded_by_authority_business_version=replacement_version,
        superseded_by_authority_revision=replacement_revision,
        transitioned_at=datetime(2026, 1, sequence, 9, 0, tzinfo=UTC),
        source_system="task9_historical_authority",
        source_record_key=f"event:{sequence}",
    )
    return Task9AuthorityLifecycleEvent(
        authority_family=semantic.authority_family.value,
        authority_stable_key=semantic.authority_stable_key,
        authority_business_version=semantic.authority_business_version,
        authority_revision=semantic.authority_revision,
        business_row_hash=semantic.business_row_hash,
        transition_sequence=semantic.transition_sequence,
        old_status=None if semantic.old_status is None else semantic.old_status.value,
        new_status=semantic.new_status.value,
        old_consumable_from_local_date=semantic.old_consumable_from_local_date,
        old_consumable_to_local_date=semantic.old_consumable_to_local_date,
        new_consumable_from_local_date=semantic.new_consumable_from_local_date,
        new_consumable_to_local_date=semantic.new_consumable_to_local_date,
        superseded_by_authority_stable_key=semantic.superseded_by_authority_stable_key,
        superseded_by_authority_business_version=semantic.superseded_by_authority_business_version,
        superseded_by_authority_revision=semantic.superseded_by_authority_revision,
        transitioned_at=semantic.transitioned_at,
        source_system=semantic.source_system,
        source_record_key=semantic.source_record_key,
        lifecycle_event_hash=authority_repository.make_lifecycle_event_hash(semantic),
    )


@pytest.mark.asyncio
async def test_verify_lifecycle_chain_rejects_business_row_hash_tamper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _pool_row()
    events = [
        _event(
            sequence=1,
            old_status=None,
            new_status=AuthorityStatus.DRAFT,
            old_from=None,
            old_to=None,
            new_from=None,
            new_to=None,
        ),
        _event(
            sequence=2,
            old_status=AuthorityStatus.DRAFT,
            new_status=AuthorityStatus.ACTIVE,
            old_from=None,
            old_to=None,
            new_from=date(2026, 1, 2),
            new_to=None,
            business_row_hash="b" * 64,
        ),
    ]

    async def _load_events(*args: object, **kwargs: object) -> list[Task9AuthorityLifecycleEvent]:
        return events

    monkeypatch.setattr(authority_repository, "_load_lifecycle_events", _load_events)

    with pytest.raises(AuthorityHashConflictError) as excinfo:
        await _verify_lifecycle_chain(
            SimpleNamespace(),
            family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
            stable_key="capacity-pool:1:2:POOL-A",
            business_version="v1",
            revision=1,
            authority=row,
        )
    assert excinfo.value.code == "AUTHORITY_HASH_CONFLICT"


@pytest.mark.asyncio
async def test_verify_lifecycle_chain_requires_exact_null_to_draft_initial_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _pool_row()
    events = [
        _event(
            sequence=1,
            old_status=None,
            new_status=AuthorityStatus.ACTIVE,
            old_from=None,
            old_to=None,
            new_from=date(2026, 1, 2),
            new_to=None,
        )
    ]

    async def _load_events(*args: object, **kwargs: object) -> list[Task9AuthorityLifecycleEvent]:
        return events

    monkeypatch.setattr(authority_repository, "_load_lifecycle_events", _load_events)

    with pytest.raises(LifecycleTransitionInvalidError) as excinfo:
        await _verify_lifecycle_chain(
            SimpleNamespace(),
            family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
            stable_key="capacity-pool:1:2:POOL-A",
            business_version="v1",
            revision=1,
            authority=row,
        )
    assert excinfo.value.code == "LIFECYCLE_TRANSITION_INVALID"


@pytest.mark.asyncio
async def test_verify_lifecycle_chain_rejects_superseded_replacement_identity_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _pool_row(status=AuthorityStatus.SUPERSEDED)
    row.consumable_from_local_date = date(2026, 1, 2)
    row.consumable_to_local_date = date(2026, 1, 10)
    row.superseded_by_id = 99
    events = [
        _event(
            sequence=1,
            old_status=None,
            new_status=AuthorityStatus.DRAFT,
            old_from=None,
            old_to=None,
            new_from=None,
            new_to=None,
        ),
        _event(
            sequence=2,
            old_status=AuthorityStatus.DRAFT,
            new_status=AuthorityStatus.ACTIVE,
            old_from=None,
            old_to=None,
            new_from=date(2026, 1, 2),
            new_to=None,
        ),
        _event(
            sequence=3,
            old_status=AuthorityStatus.ACTIVE,
            new_status=AuthorityStatus.SUPERSEDED,
            old_from=date(2026, 1, 2),
            old_to=None,
            new_from=date(2026, 1, 2),
            new_to=date(2026, 1, 10),
            replacement_stable_key="capacity-pool:1:2:POOL-B",
            replacement_version="v2",
            replacement_revision=2,
        ),
    ]
    replacement_row = _pool_row(status=AuthorityStatus.DRAFT)
    replacement_row.id = 99
    replacement_row.capacity_pool_code = "POOL-C"
    replacement_row.capacity_pool_version = "v2"
    replacement_row.revision = 2

    async def _load_events(*args: object, **kwargs: object) -> list[Task9AuthorityLifecycleEvent]:
        return events

    monkeypatch.setattr(authority_repository, "_load_lifecycle_events", _load_events)

    class _Session:
        async def get(self, model: object, pk: int) -> Task9CapacityPoolDefinition:
            assert pk == 99
            return replacement_row

    with pytest.raises(AuthorityConsumabilityIntervalConflictError) as excinfo:
        await _verify_lifecycle_chain(
            _Session(),
            family=AuthorityFamily.CAPACITY_POOL_DEFINITION,
            stable_key="capacity-pool:1:2:POOL-A",
            business_version="v1",
            revision=1,
            authority=row,
        )
    assert excinfo.value.code == "AUTHORITY_CONSUMABILITY_INTERVAL_CONFLICT"
