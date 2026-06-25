from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.harvest_state.canonical import canonical_json_dumps, is_sha256_hex
from backend.app.harvest_state.persistence import (
    HarvestStateHashConflictError,
    HarvestStatePersistenceError,
    HarvestStatePersistenceIntegrityError,
    HarvestStateResultHashMismatchError,
    load_harvest_state_output_by_id,
    load_harvest_state_output_by_result_hash,
    save_harvest_state_output,
)
from backend.app.harvest_state.schemas import (
    Task9ABlockedOutput,
    Task9ACompletedOutput,
    Task9ARequest,
)
from backend.app.harvest_state.service import run_harvest_state_model
from backend.app.repositories.harvest_state import (
    get_harvest_state_run,
)
from backend.app.repositories.harvest_state import (
    get_harvest_state_run_by_result_hash as get_persisted_harvest_state_run_by_result_hash,
)
from backend.app.schemas.harvest_state import HarvestStateRunEnvelope


class HarvestStateDeliveryError(RuntimeError):
    code = "HARVEST_STATE_DELIVERY_ERROR"
    message = "Harvest-state delivery failed."

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.message)


class HarvestStateRunNotFoundError(HarvestStateDeliveryError):
    code = "HARVEST_STATE_RUN_NOT_FOUND"
    message = "Harvest-state run was not found."


class HarvestStateDeliveryConflictError(HarvestStateDeliveryError):
    code = "HARVEST_STATE_DELIVERY_CONFLICT"
    message = "Harvest-state delivery detected a result-hash conflict."


class HarvestStateDeliveryIntegrityError(HarvestStateDeliveryError):
    code = "HARVEST_STATE_DELIVERY_INTEGRITY_ERROR"
    message = "Harvest-state delivery failed an integrity check."


class HarvestStateDeliveryInputError(HarvestStateDeliveryError):
    code = "HARVEST_STATE_DELIVERY_INPUT_ERROR"
    message = "Harvest-state request is invalid."


def _canonical_output_json(output: Task9ACompletedOutput | Task9ABlockedOutput) -> str:
    return canonical_json_dumps(output.model_dump(mode="python"))


def _build_envelope(
    *,
    run_id: int,
    created_at: Any,
    output: Task9ACompletedOutput | Task9ABlockedOutput,
) -> HarvestStateRunEnvelope:
    return HarvestStateRunEnvelope(
        run_id=run_id,
        status=output.status,
        result_hash=output.result_hash,
        config_hash=output.config_hash,
        created_at=created_at,
        output=output,
    )


def _normalize_request(payload: Task9ARequest | Mapping[str, object]) -> Task9ARequest:
    if isinstance(payload, Task9ARequest):
        return payload
    try:
        return Task9ARequest.model_validate(payload)
    except ValidationError as exc:
        raise HarvestStateDeliveryInputError("Harvest-state request failed validation.") from exc


def _map_persistence_error(exc: HarvestStatePersistenceError) -> HarvestStateDeliveryError:
    if isinstance(exc, HarvestStateHashConflictError):
        return HarvestStateDeliveryConflictError()
    if isinstance(
        exc,
        (
            HarvestStatePersistenceIntegrityError,
            HarvestStateResultHashMismatchError,
        ),
    ):
        return HarvestStateDeliveryIntegrityError()
    return HarvestStateDeliveryIntegrityError()


async def execute_harvest_state_run(
    session: AsyncSession,
    *,
    request: Task9ARequest | Mapping[str, object],
) -> HarvestStateRunEnvelope:
    normalized_request = _normalize_request(request)
    output = run_harvest_state_model(normalized_request)

    try:
        run = await save_harvest_state_output(session, output=output)
        loaded = await load_harvest_state_output_by_id(session, run_id=run.id)
    except HarvestStatePersistenceError as exc:
        raise _map_persistence_error(exc) from exc

    if loaded is None:
        raise HarvestStateDeliveryIntegrityError("Saved harvest-state run could not be reloaded.")
    if _canonical_output_json(loaded) != _canonical_output_json(output):
        raise HarvestStateDeliveryIntegrityError(
            "Persisted harvest-state output does not match computed output."
        )
    return _build_envelope(run_id=run.id, created_at=run.created_at, output=loaded)


async def get_harvest_state_run_by_id(
    session: AsyncSession,
    *,
    run_id: int,
) -> HarvestStateRunEnvelope:
    run = await get_harvest_state_run(session, run_id=run_id)
    if run is None:
        raise HarvestStateRunNotFoundError()
    try:
        output = await load_harvest_state_output_by_id(session, run_id=run_id)
    except HarvestStatePersistenceError as exc:
        raise _map_persistence_error(exc) from exc
    if output is None:
        raise HarvestStateRunNotFoundError()
    return _build_envelope(run_id=run.id, created_at=run.created_at, output=output)


async def get_harvest_state_run_by_result_hash(
    session: AsyncSession,
    *,
    result_hash: str,
) -> HarvestStateRunEnvelope:
    if not is_sha256_hex(result_hash):
        raise HarvestStateDeliveryInputError(
            "result_hash must be a 64-character lowercase SHA-256."
        )
    run = await get_persisted_harvest_state_run_by_result_hash(session, result_hash=result_hash)
    if run is None:
        raise HarvestStateRunNotFoundError()
    try:
        output = await load_harvest_state_output_by_result_hash(session, result_hash=result_hash)
    except HarvestStatePersistenceError as exc:
        raise _map_persistence_error(exc) from exc
    if output is None:
        raise HarvestStateRunNotFoundError()
    return _build_envelope(run_id=run.id, created_at=run.created_at, output=output)
