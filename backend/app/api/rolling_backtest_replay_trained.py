"""TASK-012 Slice E3 — replay-trained HTTP API surface.

Implements the additive FastAPI adapter for the frozen
``docs/task-012-slice-e-api-cli-amendment.md`` §7 contract.

This module is a THIN adapter between the HTTP transport and the Slice E2
application service in ``backend.app.rolling_backtest.replay_trained_service``.
It MUST NOT:

* implement business logic (cutoff filtering, Task 9 authority, manifest
  rebuilding, artifact integrity verification, training, prediction,
  idempotency, advisory locking, conflict determination, persistence);
* fabricate ORM rows, sessions, or persisted identity;
* expose tracebacks, SQL text, driver errors, local paths, environment
  variables, model binary bytes, or secrets to the HTTP client;
* infer current / latest / most-recent / wall-clock selection.

The adapter delegates to the existing Slice E2 service for ALL
business and persistence behaviour. The only additive helpers it
introduces are pure HTTP transport mappings plus a public read-only
pre-check that consults the same idempotency key / canonical request
hash that the service uses, so the adapter can return the frozen
``201`` vs ``200`` status code.

Frozen endpoints (amendment §7.2):

* ``POST /api/v1/rolling-backtest/replay-trained-predictions``
  - 201 first successful execution;
  - 200 exact idempotent replay;
  - 404 explicitly named replay / Task 8 / Task 9 / training / artifact /
    prediction identity missing;
  - 409 idempotency / hash / identity / cross-run substitution conflict;
  - 422 invalid request schema, cutoff, policy, or visibility contract;
  - 500 integrity failure with stable non-leaking envelope.

* ``GET /api/v1/rolling-backtest/replay-trained-predictions/{prediction_run_id}``
  - 200 persisted prediction identity (exact retrieval only);
  - 404 not found;
  - 500 integrity failure.

The adapter MUST NOT accept or expose any ``latest`` / ``current`` /
``most_recent`` / ``now()`` selection. Path parameters and the
``prediction_run_id`` are the ONLY retrieval selectors.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Path, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import get_db_session
from backend.app.models.residual_model import ResidualModelPredictionRun
from backend.app.repositories.residual_model import get_residual_prediction_run
from backend.app.residual_model.config import load_residual_model_config_from_snapshot
from backend.app.rolling_backtest.canonical import sha256_payload
from backend.app.rolling_backtest.replay_trained_service import (
    ReplayTrainedExecutionRequest,
    ReplayTrainedExecutionResult,
    ReplayTrainedServiceBlockerError,
    ReplayTrainedServiceConflictError,
    ReplayTrainedServiceError,
    ReplayTrainedServiceInputError,
    _validate_request,
    execute_replay_trained_prediction,
)

logger = logging.getLogger(__name__)

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
PredictionRunIdPath = Annotated[int, Path(..., ge=1)]


# ---------------------------------------------------------------------------
# Stable error payloads (amendment §7.3, §7.4)
# ---------------------------------------------------------------------------


def _not_found_payload(prediction_run_id: int | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "code": "TASK012_REPLAY_TRAINED_NOT_FOUND",
        "message": "The requested replay-trained prediction authority was not found.",
        "blocker": None,
        "identity": {},
    }
    if prediction_run_id is not None:
        body["identity"] = {"prediction_run_id": prediction_run_id}
    return {"error": body}


def _input_invalid_payload(message: str | None = None) -> dict[str, Any]:
    return {
        "error": {
            "code": "TASK012_REPLAY_TRAINED_INPUT_INVALID",
            "message": message or "Replay-trained request is invalid.",
            "blocker": None,
            "identity": {},
        }
    }


def _conflict_payload(message: str, mismatched_fields: tuple[str, ...]) -> dict[str, Any]:
    return {
        "error": {
            "code": "TASK012_REPLAY_TRAINED_CONFLICT",
            "message": message,
            "blocker": None,
            "identity": {"mismatched_fields": list(mismatched_fields)},
        }
    }


def _blocked_payload(
    blocker_code: str | None,
    message: str,
    mismatched_fields: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "error": {
            "code": "TASK012_REPLAY_TRAINED_BLOCKED",
            "message": message,
            "blocker": blocker_code,
            "identity": {"mismatched_fields": list(mismatched_fields)},
        }
    }


def _integrity_error_payload() -> dict[str, Any]:
    return {
        "error": {
            "code": "TASK012_REPLAY_TRAINED_INTEGRITY_ERROR",
            "message": "TASK-012 replay-trained prediction integrity check failed.",
            "blocker": None,
            "identity": {},
        }
    }


def _json_error_response(payload: dict[str, Any], status_code: int) -> Response:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return Response(
        content=body,
        media_type="application/json",
        status_code=status_code,
    )


# ---------------------------------------------------------------------------
# Transport validation (request shape, amendment §7.2 / §4.3)
# ---------------------------------------------------------------------------


def _ensure_request_object(request_body: Any) -> dict[str, Any] | Response:
    if not isinstance(request_body, dict):
        return _json_error_response(
            _input_invalid_payload("request body must be a JSON object"),
            status_code=422,
        )
    return request_body


def _ensure_required_idempotency_key(
    request_body: dict[str, Any],
) -> str | Response:
    idempotency_key_raw = request_body.get("idempotency_key")
    if not isinstance(idempotency_key_raw, str) or not idempotency_key_raw:
        return _json_error_response(
            _input_invalid_payload("idempotency_key is required and must be a non-empty string"),
            status_code=422,
        )
    return idempotency_key_raw


def _build_request(request_body: dict[str, Any]) -> ReplayTrainedExecutionRequest | Response:
    """Translate the JSON body into a frozen E2 request, or 422.

    The service-level schema in ``ReplayTrainedExecutionRequest.from_payload``
    is the single source of truth for required identity fields; the HTTP
    layer does NOT replicate that schema. We only catch the service
    input error and re-emit the stable 422 envelope. The internal
    exception message is intentionally NOT echoed to the client; the
    stable public message is emitted instead.
    """
    try:
        return ReplayTrainedExecutionRequest.from_payload(cast(dict[str, object], request_body))
    except ReplayTrainedServiceInputError:
        return _json_error_response(
            _input_invalid_payload(),
            status_code=422,
        )


# ---------------------------------------------------------------------------
# Idempotency pre-check (amendment §8): the E2 service re-uses a prior
# persisted prediction when the same idempotency_key AND canonical request
# hash exist. The HTTP layer must distinguish first execution (201) from
# exact replay (200). The E2 service exposes ``_existing_prediction_for_idempotency``
# as a module-private helper; we wrap it in a thin public read-only helper
# here purely so the HTTP layer does not duplicate the
# idempotency-key / canonical-hash business rule.
# ---------------------------------------------------------------------------


async def _request_payload_hash_for(request: ReplayTrainedExecutionRequest) -> str:
    config = load_residual_model_config_from_snapshot(request.task10_config_snapshot)
    return sha256_payload(request.canonical_identity_payload(task10_config_hash=config.config_hash))


async def _find_existing_replay_prediction(
    session: AsyncSession,
    *,
    idempotency_key: str,
    request_payload_hash: str,
) -> ResidualModelPredictionRun | None:
    """Return the persisted prediction matching the same idempotency key
    and canonical request payload hash, or ``None`` if no such prediction
    exists. If a prediction exists with the same idempotency key but a
    different canonical request hash, raise the service conflict error so
    the HTTP layer can surface a stable 409 envelope.
    """
    rows = (await session.scalars(select(ResidualModelPredictionRun))).all()
    for row in rows:
        context = row.input_snapshot.get("task12_replay")
        if not isinstance(context, dict):
            continue
        if context.get("idempotency_key") != idempotency_key:
            continue
        existing_hash = context.get("request_payload_hash")
        if existing_hash == request_payload_hash:
            return row
        raise ReplayTrainedServiceConflictError(
            "idempotency_key_payload_mismatch: idempotency key is already bound "
            "to a different canonical request",
            mismatched_fields=("idempotency_key_payload_mismatch",),
        )
    return None


# ---------------------------------------------------------------------------
# Response envelope (amendment §7.3, §9)
# ---------------------------------------------------------------------------


def _response_envelope(result: ReplayTrainedExecutionResult) -> dict[str, Any]:
    """Return the stable public response body. The E2 service is the
    single source of truth for canonical identity fields; the HTTP layer
    only repackages the canonical payload as a stable envelope. No ORM
    row, session, or exception context is exposed.
    """
    payload = result.to_payload()
    return {
        "prediction_run_id": result.prediction_run_id,
        "prediction_hash": result.prediction_hash,
        "request_payload_hash": result.request_payload_hash,
        "model_policy": payload.get("model_policy"),
        "task12_policy_version": payload.get("task12_policy_version"),
        "replay_attempt_id": payload.get("replay_attempt_id"),
        "replay_node_id": payload.get("replay_node_id"),
        "scenario_id": payload.get("scenario_id"),
        "training_manifest_hash": result.training_manifest_hash,
        "training_dataset_hash": payload.get("training_dataset_hash"),
        "model_config_hash": result.model_config_hash,
        "model_artifact_hash": result.model_artifact_hash,
        "model_code_version": payload.get("model_code_version"),
        "forecast_cutoff_at": payload.get("forecast_cutoff_at"),
        "training_cutoff_at": payload.get("training_cutoff_at"),
        "task9_run_id": result.task9_run_id,
        "task9_result_hash": result.task9_result_hash,
        "task10_training_run_id": payload.get("task10_training_run_id"),
        "task10_training_signature": payload.get("task10_training_signature"),
        "task10_manifest_hash": payload.get("task10_manifest_hash"),
        "task10_config_hash": payload.get("task10_config_hash"),
        "task10_artifact_hashes": payload.get("task10_artifact_hashes"),
        "filtered_training_row_count": result.filtered_training_row_count,
        "filtered_label_row_count": result.filtered_label_row_count,
        "training_execution_status": result.training_execution_status,
        "training_eligibility_status": result.training_eligibility_status,
        "prediction_execution_status": result.prediction_execution_status,
        "prediction_mode": result.prediction_mode,
        "idempotency_key": payload.get("idempotency_key"),
        "caller_identity": payload.get("caller_identity"),
        "no_implicit_selection": payload.get("no_implicit_selection", True),
        "no_cross_run_substitution": payload.get("no_cross_run_substitution", True),
        "audit_identity": result.audit_identity,
        "service_version": payload.get("service_version"),
    }


# ---------------------------------------------------------------------------
# GET endpoint (amendment §7.2)
# ---------------------------------------------------------------------------


def _prediction_identity_envelope(
    *,
    prediction_run_id: int,
    row: ResidualModelPredictionRun,
    context: dict[str, object],
    typed_audit: dict[str, object],
) -> dict[str, Any]:
    """Build the GET response from the persisted ORM row.

    The adapter reconstructs the response strictly from the persisted
    ``input_snapshot.task12_replay`` context. No service re-execution
    and no SQL emission to the client.
    """

    def _str(key: str, default: str = "") -> str:
        value = context.get(key, default)
        return str(value) if value is not None else default

    def _int(key: str) -> int:
        value = context.get(key)
        if isinstance(value, bool):  # pragma: no cover - defensive
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:  # pragma: no cover - defensive
                return 0
        return 0

    def _str_list(key: str) -> list[str]:
        value = context.get(key, [])
        if not isinstance(value, list):
            return []
        return [str(item) for item in value]

    return {
        "prediction_run_id": prediction_run_id,
        "prediction_hash": _str("prediction_hash") or str(row.canonical_payload_hash),
        "request_payload_hash": _str("request_payload_hash"),
        "model_policy": _str("model_policy"),
        "task12_policy_version": _str("task12_policy_version"),
        "replay_attempt_id": _str("replay_attempt_id"),
        "replay_node_id": _str("replay_node_id"),
        "scenario_id": _str("scenario_id"),
        "training_manifest_hash": _str("training_manifest_hash"),
        "training_dataset_hash": _str("training_dataset_hash"),
        "model_config_hash": _str("model_config_hash"),
        "model_artifact_hash": _str("model_artifact_hash"),
        "model_code_version": _str("model_code_version"),
        "forecast_cutoff_at": _str("forecast_cutoff_at"),
        "training_cutoff_at": _str("training_cutoff_at"),
        "task9_run_id": _int("task9_run_id"),
        "task9_result_hash": _str("task9_result_hash"),
        "task10_training_run_id": _int("task10_training_run_id"),
        "task10_training_signature": _str("task10_training_signature"),
        "task10_manifest_hash": _str("task10_manifest_hash"),
        "task10_config_hash": _str("task10_config_hash"),
        "task10_artifact_hashes": _str_list("task10_artifact_hashes"),
        "filtered_training_row_count": _int("filtered_training_row_count"),
        "filtered_label_row_count": _int("filtered_label_row_count"),
        "training_execution_status": _str("training_execution_status"),
        "training_eligibility_status": _str("training_eligibility_status"),
        "prediction_execution_status": _str("prediction_execution_status"),
        "prediction_mode": _str("prediction_mode"),
        "idempotency_key": _str("idempotency_key"),
        "caller_identity": _str("caller_identity"),
        "audit_identity": str(typed_audit.get("audit_identity", "")),
        "service_version": _str("service_version"),
    }


@router.get(
    "/replay-trained-predictions/{prediction_run_id}",
    summary="Retrieve an exact persisted replay-trained prediction.",
)
async def get_replay_trained_prediction(
    prediction_run_id: PredictionRunIdPath,
    session: SessionDep,
) -> Response:
    """Return the persisted TASK-012 replay-trained prediction identity.

    The path parameter is the ONLY selector. The endpoint MUST NOT
    accept ``latest`` / ``current`` / ``most_recent`` / ``now()``
    shortcuts and MUST NOT re-execute the Slice E2 service. It reads
    the existing persisted ORM row and projects the stable TASK-012
    identity fields.
    """
    try:
        row = await get_residual_prediction_run(session, run_id=prediction_run_id)
        if row is None:
            return _json_error_response(
                _not_found_payload(prediction_run_id),
                status_code=404,
            )
        context = row.input_snapshot.get("task12_replay")
        if not isinstance(context, dict):
            return _json_error_response(
                _integrity_error_payload(),
                status_code=500,
            )
        typed_attempt = row.typed_attempt or {}
        typed_audit = typed_attempt.get("task12_replay", {})
        if not isinstance(typed_audit, dict):
            return _json_error_response(
                _integrity_error_payload(),
                status_code=500,
            )
        envelope = _prediction_identity_envelope(
            prediction_run_id=prediction_run_id,
            row=row,
            context=context,
            typed_audit=typed_audit,
        )
    except Exception:
        logger.exception(
            "replay_trained_api.get_unexpected_error prediction_run_id=%r",
            prediction_run_id,
        )
        return _json_error_response(
            _integrity_error_payload(),
            status_code=500,
        )
    return _json_error_response(envelope, status_code=200)


# ---------------------------------------------------------------------------
# POST endpoint (amendment §7.2)
# ---------------------------------------------------------------------------


@router.post(
    "/replay-trained-predictions",
    status_code=201,
    summary="Execute an explicit replay-trained prediction request.",
)
async def post_replay_trained_prediction(
    request_body: dict[str, Any],
    session: SessionDep,
) -> Response:
    """Translate the JSON request into the frozen E2 contract and
    delegate to the Slice E2 application service. The HTTP layer does
    NOT implement any business / persistence / idempotency logic; the
    service is the single source of truth. The HTTP layer only maps
    service errors to the stable transport envelope and distinguishes
    first execution (201) from exact idempotent replay (200).
    """
    # ---- 1. Transport validation ----
    object_or_error = _ensure_request_object(request_body)
    if not isinstance(object_or_error, dict):
        return object_or_error
    request_body = object_or_error
    idempotency_key_or_error = _ensure_required_idempotency_key(request_body)
    if not isinstance(idempotency_key_or_error, str):
        return idempotency_key_or_error
    idempotency_key = idempotency_key_or_error

    # ---- 2. Build the frozen E2 request ----
    built = _build_request(request_body)
    if not isinstance(built, ReplayTrainedExecutionRequest):
        return built
    request = built

    # ---- 3. Idempotency pre-check (amendment §8) ----
    try:
        _validate_request(request)
        canonical_hash = await _request_payload_hash_for(request)
        existing = await _find_existing_replay_prediction(
            session,
            idempotency_key=idempotency_key,
            request_payload_hash=canonical_hash,
        )
        if existing is not None:
            # The E2 service can re-load this prediction identically; defer
            # the actual response to it so the canonical payload is the
            # single source of truth.
            result = await execute_replay_trained_prediction(session, request=request)
            return _json_error_response(
                _response_envelope(result),
                status_code=200,
            )
    except ReplayTrainedServiceInputError:
        return _json_error_response(
            _input_invalid_payload(),
            status_code=422,
        )
    except ReplayTrainedServiceConflictError as exc:
        return _json_error_response(
            _conflict_payload("idempotency_key_payload_mismatch", exc.mismatched_fields),
            status_code=409,
        )
    except ReplayTrainedServiceBlockerError as exc:
        return _json_error_response(
            _blocked_payload(
                exc.blocker_code,
                "Replay-trained request is blocked by a TASK-012 deterministic blocker.",
                exc.mismatched_fields,
            ),
            status_code=409,
        )

    # ---- 4. Delegate to the Slice E2 application service ----
    try:
        result = await execute_replay_trained_prediction(session, request=request)
    except ReplayTrainedServiceInputError:
        return _json_error_response(
            _input_invalid_payload(),
            status_code=422,
        )
    except ReplayTrainedServiceConflictError as exc:
        return _json_error_response(
            _conflict_payload("idempotency_key_payload_mismatch", exc.mismatched_fields),
            status_code=409,
        )
    except ReplayTrainedServiceBlockerError as exc:
        return _json_error_response(
            _blocked_payload(
                exc.blocker_code,
                "Replay-trained request is blocked by a TASK-012 deterministic blocker.",
                exc.mismatched_fields,
            ),
            status_code=409,
        )
    except ReplayTrainedServiceError:
        logger.exception(
            "replay_trained_api.post_service_error idempotency_key=%r",
            idempotency_key,
        )
        return _json_error_response(
            _integrity_error_payload(),
            status_code=500,
        )
    except Exception:
        logger.exception(
            "replay_trained_api.post_unexpected_error idempotency_key=%r",
            idempotency_key,
        )
        return _json_error_response(
            _integrity_error_payload(),
            status_code=500,
        )

    return _json_error_response(
        _response_envelope(result),
        status_code=201,
    )
