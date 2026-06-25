from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.harvest_state.application import (
    HarvestStateDeliveryConflictError,
    HarvestStateDeliveryIntegrityError,
    HarvestStateRunNotFoundError,
    execute_harvest_state_run,
    get_harvest_state_run_by_id,
    get_harvest_state_run_by_result_hash,
)
from backend.app.harvest_state.persistence import (
    HarvestStateHashConflictError,
    HarvestStatePersistenceIntegrityError,
    HarvestStateResultHashMismatchError,
)
from backend.app.models.harvest_state import HarvestStateRun
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


@pytest.mark.asyncio
async def test_persistence_integrity_error_is_mapped(
    sqlite_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _raise_integrity(*args: object, **kwargs: object) -> object:
        raise HarvestStatePersistenceIntegrityError("broken")

    monkeypatch.setattr(
        "backend.app.harvest_state.application.save_harvest_state_output",
        _raise_integrity,
    )

    with pytest.raises(HarvestStateDeliveryIntegrityError):
        await execute_harvest_state_run(sqlite_session, request=make_request())


@pytest.mark.asyncio
async def test_result_hash_mismatch_is_mapped_to_integrity_error(
    sqlite_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _raise_mismatch(*args: object, **kwargs: object) -> object:
        raise HarvestStateResultHashMismatchError("mismatch")

    monkeypatch.setattr(
        "backend.app.harvest_state.application.save_harvest_state_output",
        _raise_mismatch,
    )

    with pytest.raises(HarvestStateDeliveryIntegrityError):
        await execute_harvest_state_run(sqlite_session, request=make_request())


@pytest.mark.asyncio
async def test_reload_missing_after_save_raises_integrity_error(
    sqlite_session: AsyncSession,
    completed_harvest_state_output: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _SavedRun:
        id = 1
        created_at = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)

    async def _save(*args: object, **kwargs: object) -> object:
        return _SavedRun()

    async def _load(*args: object, **kwargs: object) -> object:
        return None

    monkeypatch.setattr(
        "backend.app.harvest_state.application.save_harvest_state_output",
        _save,
    )
    monkeypatch.setattr(
        "backend.app.harvest_state.application.load_harvest_state_output_by_id",
        _load,
    )

    with pytest.raises(HarvestStateDeliveryIntegrityError):
        await execute_harvest_state_run(sqlite_session, request=make_request())


@pytest.mark.asyncio
async def test_reload_payload_mismatch_raises_integrity_error(
    sqlite_session: AsyncSession,
    completed_harvest_state_output: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _SavedRun:
        id = 1
        created_at = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)

    async def _save(*args: object, **kwargs: object) -> object:
        return _SavedRun()

    async def _load(*args: object, **kwargs: object) -> object:
        return completed_harvest_state_output.model_copy(update={"warnings": ["mismatch"]})

    monkeypatch.setattr(
        "backend.app.harvest_state.application.save_harvest_state_output",
        _save,
    )
    monkeypatch.setattr(
        "backend.app.harvest_state.application.load_harvest_state_output_by_id",
        _load,
    )

    with pytest.raises(HarvestStateDeliveryIntegrityError):
        await execute_harvest_state_run(sqlite_session, request=make_request())


@pytest.mark.asyncio
async def test_failed_save_does_not_return_envelope(
    sqlite_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _raise_integrity(*args: object, **kwargs: object) -> object:
        raise HarvestStatePersistenceIntegrityError("broken")

    monkeypatch.setattr(
        "backend.app.harvest_state.application.save_harvest_state_output",
        _raise_integrity,
    )

    with pytest.raises(HarvestStateDeliveryIntegrityError):
        await execute_harvest_state_run(sqlite_session, request=make_request())


@pytest.mark.asyncio
async def test_failed_save_leaves_no_partial_run(
    sqlite_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _raise_integrity(*args: object, **kwargs: object) -> object:
        raise HarvestStatePersistenceIntegrityError("broken")

    monkeypatch.setattr(
        "backend.app.harvest_state.application.save_harvest_state_output",
        _raise_integrity,
    )

    with pytest.raises(HarvestStateDeliveryIntegrityError):
        await execute_harvest_state_run(sqlite_session, request=make_request())

    assert await sqlite_session.scalar(select(func.count()).select_from(HarvestStateRun)) == 0
