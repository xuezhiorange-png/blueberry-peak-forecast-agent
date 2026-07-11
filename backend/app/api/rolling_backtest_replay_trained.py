"""TASK-012 Slice E3 — replay-trained HTTP API surface.

This module is a THIN HTTP transport adapter for the frozen
``docs/task-012-slice-e-api-cli-amendment.md`` §7 contract. It delegates
ALL business / persistence / idempotency / conflict determination to
the Slice E2 application service in
``backend.app.rolling_backtest.replay_trained_service``.

Hard prohibitions (enforced by tests in
``backend/tests/rolling_backtest/test_replay_trained_model_slice_e3.py``):

* NO business logic (no cutoff filtering, no Task 9 authority
  verification, no manifest / dataset rebuilding, no artifact
  integrity verification, no training, no prediction, no
  idempotency, no advisory locking, no conflict determination, no
  persistence business logic).
* NO ORM row fabrication, no in-memory cache of identity, no
  request-body backfill into persisted identity.
* NO echo of internal exception text, SQL text, driver errors,
  local paths, environment variables, model binary bytes, or
  secrets to the HTTP client.
* NO implicit ``latest`` / ``current`` / ``most_recent`` /
  ``now()`` / wall-clock selection. The path parameter
  ``prediction_run_id`` is the ONLY retrieval selector.
* NO duplicate of validation, idempotency, or hash logic that the
  E2 service already performs. The HTTP layer uses a strict
  Pydantic request schema and forwards the parsed payload to the
  E2 service, which is the single source of truth.

Frozen endpoints (amendment §7.2):

* ``POST /api/v1/rolling-backtest/replay-trained-predictions``
    - 201 first successful execution (service ``result.created == True``);
    - 200 exact idempotent replay (service ``result.created == False``);
    - 404 explicitly named replay / Task 8 / Task 9 / training /
      artifact / prediction authority missing (frozen blocker
      ``TASK12_***_NOT_FOUND``-class envelope);
    - 409 idempotency / canonical-hash mismatch (service
      ``ReplayTrainedServiceConflictError``);
    - 409 structured TASK-012 blocker with stable ``blocker_code``
      field (service ``ReplayTrainedServiceBlockerError``);
    - 422 request schema, cutoff, policy, or visibility contract
      violation (request schema validation OR service
      ``ReplayTrainedServiceInputError``);
    - 500 unexpected internal failure with stable non-leaking
      envelope.

* ``GET /api/v1/rolling-backtest/replay-trained-predictions/{prediction_run_id}``
    - 200 persisted prediction identity (exact retrieval only);
    - 404 not found;
    - 500 integrity failure.

The HTTP layer reads the service's ``result.created`` boolean
disposition to choose between 201 and 200, and reads the service's
canonical payload (via ``result.to_payload()``) to build the
response envelope. It MUST NOT pre-check, recompute, or
re-classify the disposition.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Annotated, Any, ClassVar, cast

from fastapi import APIRouter, Depends, Path, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import get_db_session
from backend.app.models.residual_model import ResidualModelPredictionRun
from backend.app.repositories.residual_model import get_residual_prediction_run
from backend.app.rolling_backtest.replay_trained_service import (
    ReplayTrainedExecutionRequest,
    ReplayTrainedExecutionResult,
    ReplayTrainedServiceBlockerError,
    ReplayTrainedServiceConflictError,
    ReplayTrainedServiceError,
    ReplayTrainedServiceInputError,
    execute_replay_trained_prediction,
)

logger = logging.getLogger(__name__)

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
PredictionRunIdPath = Annotated[int, Path(..., ge=1)]

#: Lowercase 64-character hex hash. Used for prediction_hash, request_payload_hash,
#: task9_result_hash, model_config_hash, model_artifact_hash, training_manifest_hash,
#: training_dataset_hash, task10_manifest_hash, task10_config_hash.
LOWERCASE_64_HEX = re.compile(r"^[0-9a-f]{64}$")
#: Lowercase 32-character hex hash. Used for config_hash.
LOWERCASE_32_HEX = re.compile(r"^[0-9a-f]{32}$")


# ---------------------------------------------------------------------------
# Strict request schema (amendment §7.1, §4.3, §6, §8)
# ---------------------------------------------------------------------------
#
# The schema mirrors the canonical request identity at the wire boundary.
# The E2 service (``ReplayTrainedExecutionRequest.from_payload``) is the
# single source of truth for the full business contract; the HTTP layer's
# strict schema exists ONLY to (a) reject malformed / hostile request
# bodies with a stable 422 envelope BEFORE the E2 service is invoked and
# (b) reject unknown fields. The E2 service still re-validates every
# field. Any divergence between this schema and the E2 schema is a bug
# in this layer.
class ReplayTrainedRequestSchema(BaseModel):
    """Strict Pydantic request schema mirroring the frozen E2 contract.

    All fields are required (no defaults). ``extra="forbid"`` rejects
    unknown fields. Datetime fields are parsed by Pydantic v2 and
    MUST be timezone-aware (naive datetimes raise a 422).
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    # NOTE: the JSON field name is ``model_config`` (frozen at the wire
    # boundary by amendment §7.1) but the Python attribute name is
    # ``model_config_payload`` to avoid colliding with Pydantic's
    # ``model_config`` class variable.
    model_config_payload: dict[str, object] = Field(
        ...,
        validation_alias="model_config",
        serialization_alias="model_config",
    )
    model_policy: str = Field(..., min_length=1)
    task12_policy_version: str = Field(..., min_length=1)
    replay_attempt_id: str = Field(..., min_length=1)
    replay_node_id: str = Field(..., min_length=1)
    scenario_id: str = Field(..., min_length=1)
    forecast_cutoff_at: datetime
    training_cutoff_at: datetime
    allowed_training_season_ids: tuple[int, ...] = Field(..., min_length=1)
    training_manifest: dict[str, object]
    model_code_version: str = Field(..., min_length=1)
    replay_code_version: str = Field(..., min_length=1)
    task9_run_id: int = Field(..., ge=1)
    task9_result_hash: str = Field(..., min_length=1)
    is_replay: bool
    task10_config_snapshot: dict[str, object]
    manifest_rows_payload: list[dict[str, object]] = Field(..., min_length=1)
    training_rows: list[dict[str, object]] = Field(..., min_length=1)
    label_rows: list[dict[str, object]]
    source_run_ids: dict[str, int]
    artifact_identity_json: dict[str, object]
    artifact_identity_manifest: dict[str, object]
    feature_actual_snapshot: dict[str, object] | None
    idempotency_key: str = Field(..., min_length=1)
    caller_identity: str = Field(..., min_length=1)
    training_samples: list[dict[str, object]] = Field(..., min_length=1)
    supplemental_feature_values: list[dict[str, object]]

    @field_validator("task9_result_hash")
    @classmethod
    def _validate_hash_fields(cls, value: str) -> str:
        if not LOWERCASE_64_HEX.match(value):
            raise ValueError("task9_result_hash must be a lowercase 64-character hex hash")
        return value

    @field_validator("forecast_cutoff_at", "training_cutoff_at")
    @classmethod
    def _validate_tz_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime fields must be timezone-aware")
        return value


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


def _input_invalid_payload() -> dict[str, Any]:
    return {
        "error": {
            "code": "TASK012_REPLAY_TRAINED_INPUT_INVALID",
            "message": "Replay-trained request is invalid.",
            "blocker": None,
            "identity": {},
        }
    }


def _conflict_payload(mismatched_fields: tuple[str, ...]) -> dict[str, Any]:
    return {
        "error": {
            "code": "TASK012_REPLAY_TRAINED_CONFLICT",
            "message": "Replay-trained request conflicts with a prior persisted prediction.",
            "blocker": None,
            "identity": {"mismatched_fields": list(mismatched_fields)},
        }
    }


def _blocked_payload(
    blocker_code: str | None,
    mismatched_fields: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "error": {
            "code": "TASK012_REPLAY_TRAINED_BLOCKED",
            "message": "Replay-trained request is blocked by a TASK-012 deterministic blocker.",
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
# Response envelope (amendment §7.3, §9)
# ---------------------------------------------------------------------------


def _response_envelope(result: ReplayTrainedExecutionResult) -> dict[str, Any]:
    """Return the stable public response body.

    The E2 service is the single source of truth for the canonical
    payload (``result.to_payload()``) and the 201/200 disposition
    (``result.created``). The HTTP layer does NOT recompute either;
    it only re-packages the canonical payload and exposes the
    disposition as ``disposition`` so clients can introspect.
    """
    payload = result.to_payload()
    return {
        "disposition": "created" if result.created else "idempotent_replay",
        "prediction_run_id": result.prediction_run_id,
        "prediction_hash": result.prediction_hash,
        "request_payload_hash": result.request_payload_hash,
        "model_policy": payload["model_policy"],
        "task12_policy_version": payload["task12_policy_version"],
        "replay_attempt_id": payload["replay_attempt_id"],
        "replay_node_id": payload["replay_node_id"],
        "scenario_id": payload["scenario_id"],
        "training_manifest_hash": result.training_manifest_hash,
        "training_dataset_hash": payload["training_dataset_hash"],
        "model_config_hash": result.model_config_hash,
        "model_artifact_hash": result.model_artifact_hash,
        "model_code_version": payload["model_code_version"],
        "forecast_cutoff_at": payload["forecast_cutoff_at"],
        "training_cutoff_at": payload["training_cutoff_at"],
        "task9_run_id": result.task9_run_id,
        "task9_result_hash": result.task9_result_hash,
        "task10_training_run_id": payload["task10_training_run_id"],
        "task10_training_signature": payload["task10_training_signature"],
        "task10_manifest_hash": payload["task10_manifest_hash"],
        "task10_config_hash": payload["task10_config_hash"],
        "task10_artifact_hashes": payload["task10_artifact_hashes"],
        "filtered_training_row_count": result.filtered_training_row_count,
        "filtered_label_row_count": result.filtered_label_row_count,
        "training_execution_status": result.training_execution_status,
        "training_eligibility_status": result.training_eligibility_status,
        "prediction_execution_status": result.prediction_execution_status,
        "prediction_mode": result.prediction_mode,
        "idempotency_key": payload["idempotency_key"],
        "caller_identity": payload["caller_identity"],
        "no_implicit_selection": payload["no_implicit_selection"],
        "no_cross_run_substitution": payload["no_cross_run_substitution"],
        "audit_identity": result.audit_identity,
        "service_version": payload["service_version"],
    }


# ---------------------------------------------------------------------------
# GET endpoint (amendment §7.2) — strict persisted identity loader
# ---------------------------------------------------------------------------


def _prediction_identity_envelope(
    *,
    prediction_run_id: int,
    row: ResidualModelPredictionRun,
) -> dict[str, Any]:
    """Build the GET response strictly from the persisted ORM row.

    The adapter does NOT recompute, default, or fabricate any
    identity field. Every field that IS in the response is read
    from the persisted ``input_snapshot.task12_replay`` context
    (or ``typed_attempt.task12_replay`` for the audit identity)
    and the ORM row. A field that is absent in the persisted
    context is returned as ``None`` rather than fabricated with
    a default value; the adapter MUST NOT silently backfill. The
    persisted ``audit_identity`` (in ``typed_attempt.task12_replay``)
    is the only field treated as integrity-required; if it is
    missing the row has not been TASK-012-finalised and the
    endpoint emits the stable 500 integrity envelope (fail-closed).
    """

    def _strict_str(context: dict[str, object], key: str) -> str | None:
        if key not in context:
            return None
        value = context[key]
        if not isinstance(value, str) or not value:
            return None
        return value

    def _strict_int(context: dict[str, object], key: str) -> int | None:
        if key not in context:
            return None
        value = context[key]
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        return value

    def _strict_str_list(context: dict[str, object], key: str) -> list[str] | None:
        if key not in context:
            return None
        value = context[key]
        if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
            return None
        return cast(list[str], value)

    input_snapshot = row.input_snapshot or {}
    context_obj = input_snapshot.get("task12_replay")
    if not isinstance(context_obj, dict):
        raise KeyError("task12_replay context")
    context = cast(dict[str, object], context_obj)

    typed_attempt = row.typed_attempt or {}
    typed_audit_obj = typed_attempt.get("task12_replay")
    typed_audit = (
        cast(dict[str, object], typed_audit_obj) if isinstance(typed_audit_obj, dict) else {}
    )

    prediction_hash = str(row.canonical_payload_hash)
    audit_identity = _strict_str(typed_audit, "audit_identity")
    if audit_identity is None:
        raise KeyError("audit_identity")
    return {
        "prediction_run_id": prediction_run_id,
        "prediction_hash": prediction_hash,
        "request_payload_hash": _strict_str(context, "request_payload_hash"),
        "model_policy": _strict_str(context, "model_policy"),
        "task12_policy_version": _strict_str(context, "task12_policy_version"),
        "replay_attempt_id": _strict_str(context, "replay_attempt_id"),
        "replay_node_id": _strict_str(context, "replay_node_id"),
        "scenario_id": _strict_str(context, "scenario_id"),
        "training_manifest_hash": _strict_str(context, "training_manifest_hash"),
        "training_dataset_hash": _strict_str(context, "training_dataset_hash"),
        "model_config_hash": _strict_str(context, "model_config_hash"),
        "model_artifact_hash": _strict_str(context, "model_artifact_hash"),
        "model_code_version": _strict_str(context, "model_code_version"),
        "forecast_cutoff_at": _strict_str(context, "forecast_cutoff_at"),
        "training_cutoff_at": _strict_str(context, "training_cutoff_at"),
        "task9_run_id": _strict_int(context, "task9_run_id"),
        "task9_result_hash": _strict_str(context, "task9_result_hash"),
        "task10_training_run_id": _strict_int(context, "task10_training_run_id"),
        "task10_training_signature": _strict_str(context, "task10_training_signature"),
        "task10_manifest_hash": _strict_str(context, "task10_manifest_hash"),
        "task10_config_hash": _strict_str(context, "task10_config_hash"),
        "task10_artifact_hashes": _strict_str_list(context, "task10_artifact_hashes"),
        "filtered_training_row_count": _strict_int(context, "filtered_training_row_count"),
        "filtered_label_row_count": _strict_int(context, "filtered_label_row_count"),
        "training_execution_status": _strict_str(context, "training_execution_status"),
        "training_eligibility_status": _strict_str(context, "training_eligibility_status"),
        "prediction_execution_status": _strict_str(context, "prediction_execution_status"),
        "prediction_mode": _strict_str(context, "prediction_mode"),
        "idempotency_key": _strict_str(context, "idempotency_key"),
        "caller_identity": _strict_str(context, "caller_identity"),
        "audit_identity": audit_identity,
        "service_version": _strict_str(context, "service_version"),
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
    shortcuts and MUST NOT re-execute the Slice E2 service. It
    reads the existing persisted ORM row and projects the strict
    TASK-012 identity fields. Any missing required field fails
    closed with the stable 500 integrity envelope.
    """
    try:
        row = await get_residual_prediction_run(session, run_id=prediction_run_id)
        if row is None:
            return _json_error_response(
                _not_found_payload(prediction_run_id),
                status_code=404,
            )
        envelope = _prediction_identity_envelope(
            prediction_run_id=prediction_run_id,
            row=row,
        )
    except KeyError as exc:
        logger.error(
            "replay_trained_api.get_integrity_missing_field prediction_run_id=%r missing_key=%r",
            prediction_run_id,
            exc.args[0] if exc.args else "<unknown>",
        )
        return _json_error_response(
            _integrity_error_payload(),
            status_code=500,
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
# POST endpoint (amendment §7.2) — strict transport, 201/200 from service
# ---------------------------------------------------------------------------


@router.post(
    "/replay-trained-predictions",
    summary="Execute an explicit replay-trained prediction request.",
)
async def post_replay_trained_prediction(
    request: ReplayTrainedRequestSchema,
    session: SessionDep,
) -> Response:
    """Translate the JSON request into the frozen E2 contract and
    delegate to the Slice E2 application service.

    The HTTP layer does NOT implement any business / persistence /
    idempotency logic; the service is the single source of truth.
    The HTTP layer only:

    1. Enforces a strict Pydantic schema at the wire boundary
       (Pydantic raises before this function returns if the body
       is malformed; the route's RequestValidationError is
       converted to a stable 422 envelope by the main-app
       exception handler).
    2. Re-validates with the E2 service's ``from_payload`` (the
       service is the authoritative schema; this layer is a
       fast-fail barrier).
    3. Calls ``execute_replay_trained_prediction`` exactly once.
    4. Reads the service's ``result.created`` boolean to choose
       between 201 (first execution) and 200 (exact idempotent
       replay). The HTTP layer does NOT pre-check or recompute
       the disposition.
    5. Maps service errors to the stable transport envelope.
    """
    try:
        payload_for_service = cast(
            dict[str, object], request.model_dump(by_alias=True, mode="json")
        )
        e2_request = ReplayTrainedExecutionRequest.from_payload(payload_for_service)
    except ReplayTrainedServiceInputError:
        return _json_error_response(
            _input_invalid_payload(),
            status_code=422,
        )

    try:
        result = await execute_replay_trained_prediction(session, request=e2_request)
    except ReplayTrainedServiceInputError:
        return _json_error_response(
            _input_invalid_payload(),
            status_code=422,
        )
    except ReplayTrainedServiceConflictError as exc:
        return _json_error_response(
            _conflict_payload(exc.mismatched_fields),
            status_code=409,
        )
    except ReplayTrainedServiceBlockerError as exc:
        return _json_error_response(
            _blocked_payload(exc.blocker_code, exc.mismatched_fields),
            status_code=409,
        )
    except ReplayTrainedServiceError:
        logger.exception(
            "replay_trained_api.post_service_error idempotency_key=%r",
            request.idempotency_key,
        )
        return _json_error_response(
            _integrity_error_payload(),
            status_code=500,
        )
    except Exception:
        logger.exception(
            "replay_trained_api.post_unexpected_error idempotency_key=%r",
            request.idempotency_key,
        )
        return _json_error_response(
            _integrity_error_payload(),
            status_code=500,
        )

    status_code = 201 if result.created else 200
    return _json_error_response(
        _response_envelope(result),
        status_code=status_code,
    )
