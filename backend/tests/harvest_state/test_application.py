from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.harvest_state.application import (
    HarvestStateDeliveryConflictError,
    HarvestStateRunNotFoundError,
    execute_harvest_state_run,
    get_harvest_state_run_by_id,
    get_harvest_state_run_by_result_hash,
)
from backend.app.harvest_state.persistence import HarvestStateHashConflictError
from backend.tests.harvest_state.conftest import make_request


@pytest.mark.asyncio
async def test_execute_completed_run_persists_and_returns_output(
    sqlite_session: AsyncSession,
) -> None:
    envelope = await execute_harvest_state_run(sqlite_session, request=make_request())

    assert envelope.status == "completed"
    assert envelope.run_id > 0
    assert envelope.output.status == "completed"
    assert envelope.result_hash == envelope.output.result_hash
    assert envelope.config_hash == envelope.output.config_hash


@pytest.mark.asyncio
async def test_execute_blocked_run_persists_and_returns_output(
    sqlite_session: AsyncSession,
) -> None:
    payload = make_request()
    payload["farm_timezone"] = "Bad/Timezone"

    envelope = await execute_harvest_state_run(sqlite_session, request=payload)

    assert envelope.status == "blocked"
    assert envelope.output.status == "blocked"
    assert envelope.output.blockers == ["INVALID_TIMEZONE"]


@pytest.mark.asyncio
async def test_execute_repeated_request_reuses_existing_run(
    sqlite_session: AsyncSession,
) -> None:
    first = await execute_harvest_state_run(sqlite_session, request=make_request())
    second = await execute_harvest_state_run(sqlite_session, request=make_request())

    assert second.run_id == first.run_id
    assert second.result_hash == first.result_hash


@pytest.mark.asyncio
async def test_get_run_by_id_and_hash(sqlite_session: AsyncSession) -> None:
    envelope = await execute_harvest_state_run(sqlite_session, request=make_request())

    by_id = await get_harvest_state_run_by_id(sqlite_session, run_id=envelope.run_id)
    by_hash = await get_harvest_state_run_by_result_hash(
        sqlite_session,
        result_hash=envelope.result_hash,
    )

    assert by_id.model_dump(mode="python") == envelope.model_dump(mode="python")
    assert by_hash.model_dump(mode="python") == envelope.model_dump(mode="python")


@pytest.mark.asyncio
async def test_get_missing_run_raises_not_found(sqlite_session: AsyncSession) -> None:
    with pytest.raises(HarvestStateRunNotFoundError):
        await get_harvest_state_run_by_id(sqlite_session, run_id=999)


@pytest.mark.asyncio
async def test_persistence_conflict_is_mapped(
    sqlite_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _raise_conflict(*args: object, **kwargs: object) -> object:
        raise HarvestStateHashConflictError("conflict")

    monkeypatch.setattr(
        "backend.app.harvest_state.application.save_harvest_state_output",
        _raise_conflict,
    )

    with pytest.raises(HarvestStateDeliveryConflictError):
        await execute_harvest_state_run(sqlite_session, request=make_request())
