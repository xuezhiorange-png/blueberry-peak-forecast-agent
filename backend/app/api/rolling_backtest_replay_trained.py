"""TASK-012 Slice E3 — replay-trained HTTP API surface.

This module is a THIN HTTP transport adapter for the frozen
``docs/task-012-slice-e-api-cli-amendment.md`` §7 contract. It delegates
ALL business / persistence / idempotency / conflict determination to
the Slice E2 application service in
``backend.app.rolling_backtest.replay_trained_service``.

Hard prohibitions (enforced by tests in
``backend/tests/rolling_backtest/test_replay_trained_model_slice_e3.py``
and the E3 PG contracts):

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
  Pydantic request schema (``extra="forbid"`` +
  ``StrictBool``/``StrictInt``/``Literal``) and forwards the
  parsed payload to the E2 service, which is the single source
  of truth.

Frozen endpoints (amendment §7.2):

* ``POST /api/v1/rolling-backtest/replay-trained-predictions``
    - 201 first successful execution (service ``result.created == True``);
    - 200 exact idempotent replay (service ``result.created == False``);
    - 404 explicitly named replay / Task 8 / Task 9 / training /
      artifact / prediction authority missing (frozen
      ``TASK012_REPLAY_TRAINED_NOT_FOUND`` envelope via
      :class:`ReplayTrainedServiceNotFoundError`);
    - 409 idempotency / canonical-hash mismatch (service
      :class:`ReplayTrainedServiceConflictError`);
    - 409 structured TASK-012 blocker with stable ``blocker_code``
      field (service :class:`ReplayTrainedServiceBlockerError`);
    - 422 request schema, cutoff, policy, or visibility contract
      violation (request schema validation OR service
      :class:`ReplayTrainedServiceInputError`);
    - 500 unexpected internal failure with stable non-leaking
      envelope.

* ``GET /api/v1/rolling-backtest/replay-trained-predictions/{prediction_run_id}``
    - 200 persisted prediction identity (exact retrieval only);
    - 404 not found (via :class:`ReplayTrainedServiceNotFoundError`);
    - 500 strict persisted identity loader detected a missing or
      malformed required field (via
      :class:`ReplayTrainedPersistedIdentityIntegrityError`).

The strict Pydantic request schema (per P0-#2 spec) rejects:

* unknown top-level field and unknown nested field (→ 422);
* ``is_replay`` set to a string ``"false"`` or integer ``1``
  (StrictBool → 422);
* integer fields receiving bool, float, or numeric string
  (StrictInt → 422);
* string fields receiving number / bool auto-conversion
  (StrictStr → 422);
* naive datetimes in datetime fields (custom validator → 422);
* non-lowercase / wrong-length hash fields (pattern regex → 422).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Annotated, Any, ClassVar, Literal, cast

from fastapi import APIRouter, Depends, Path, Response
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    field_validator,
)
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import get_db_session
from backend.app.rolling_backtest.replay_trained_service import (
    ReplayTrainedExecutionRequest,
    ReplayTrainedExecutionResult,
    ReplayTrainedPersistedIdentity,
    ReplayTrainedPersistedIdentityIntegrityError,
    ReplayTrainedServiceBlockerError,
    ReplayTrainedServiceConflictError,
    ReplayTrainedServiceError,
    ReplayTrainedServiceInputError,
    ReplayTrainedServiceNotFoundError,
    execute_replay_trained_prediction,
    load_replay_trained_prediction,
)

logger = logging.getLogger(__name__)

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
PredictionRunIdPath = Annotated[int, Path(..., ge=1)]

#: Lowercase 64-character hex hash. Used for prediction_hash, request_payload_hash,
#: task9_result_hash, model_config_hash, model_artifact_hash, training_manifest_hash,
#: training_dataset_hash, task10_manifest_hash, task10_config_hash.
LOWERCASE_64_HEX = re.compile(r"^[0-9a-f]{64}$")


# ---------------------------------------------------------------------------
# Strict nested Pydantic models (P0-#2 spec)
# ---------------------------------------------------------------------------
#
# Every nested model is built with
# ``ConfigDict(extra="forbid", populate_by_name=True)``. Combined with
# the field-level ``StrictBool`` / ``StrictInt`` / ``StrictStr`` and
# ``Literal`` types, the schema rejects:
#
#   - unknown top-level and unknown nested fields (→ 422);
#   - bool / float / numeric string in integer fields (StrictInt);
#   - number / bool auto-conversion in string fields (StrictStr);
#   - naive datetimes in datetime fields (custom validator);
#   - non-lowercase / wrong-length hash fields (pattern regex).
#
# The schema mirrors the canonical request identity at the wire
# boundary. The E2 service
# (``ReplayTrainedExecutionRequest.from_payload``) is the single
# source of truth for the full business contract; this layer's
# strict schema exists ONLY as a fast-fail barrier BEFORE the E2
# service is invoked. The E2 service still re-validates every field.


class _StrictBaseModel(BaseModel):
    """Base for every strict nested model.

    Rejects unknown fields (via ``extra="forbid"``) and accepts
    either the JSON field name OR the Python attribute name
    (via ``populate_by_name=True``). Datetime / list / tuple /
    nested-dict fields still parse from JSON strings/lists via
    Pydantic v2's standard validation; the field-level
    ``StrictBool``/``StrictInt``/``StrictStr`` types enforce the
    no-auto-coerce rule on the scalar fields the spec requires.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
        populate_by_name=True,
    )


class TrainingManifestSchema(_StrictBaseModel):
    replay_attempt_id: StrictStr = Field(..., min_length=1)
    replay_node_id: StrictStr = Field(..., min_length=1)
    scenario_id: StrictStr = Field(..., min_length=1)
    forecast_cutoff_at: datetime
    training_cutoff_at: datetime
    allowed_training_season_ids: list[StrictInt] = Field(..., min_length=1)
    feature_visibility_policy_version: StrictStr = Field(..., min_length=1)
    label_visibility_policy_version: StrictStr = Field(..., min_length=1)
    artifact_visibility_policy_version: StrictStr = Field(..., min_length=1)
    validation_policy_version: StrictStr = Field(..., min_length=1)
    training_dataset_hash: StrictStr = Field(
        ..., min_length=1, pattern=LOWERCASE_64_HEX.pattern
    )
    task8_curve_identity: StrictStr | None = None
    task9_replay_binding_identity: StrictStr | None = None
    row_count: StrictInt = Field(..., ge=0)
    excluded_row_count: StrictInt = Field(..., ge=0)


class ModelConfigSchema(_StrictBaseModel):
    algorithm_family: StrictStr = Field(..., min_length=1)
    hyperparameters: dict[StrictStr, StrictStr | StrictInt | StrictBool]
    random_seed: StrictInt = Field(..., ge=0)
    deterministic_serialization_version: StrictStr = Field(..., min_length=1)


class SourceRunIdsSchema(_StrictBaseModel):
    task9a_run_id: StrictInt = Field(..., ge=1)
    task9b_run_id: StrictInt | None = Field(default=None, ge=1)
    task10_training_run_id: StrictInt | None = Field(default=None, ge=1)


class ArtifactIdentitySchema(_StrictBaseModel):
    model_policy: Literal["replay_trained_model"]
    task12_policy_version: StrictStr = Field(..., min_length=1)
    replay_attempt_id: StrictStr = Field(..., min_length=1)
    replay_node_id: StrictStr = Field(..., min_length=1)
    forecast_cutoff_at: datetime
    training_cutoff_at: datetime
    training_manifest_hash: StrictStr = Field(
        ..., min_length=1, pattern=LOWERCASE_64_HEX.pattern
    )
    training_dataset_hash: StrictStr = Field(
        ..., min_length=1, pattern=LOWERCASE_64_HEX.pattern
    )
    model_config_hash: StrictStr = Field(
        ..., min_length=1, pattern=LOWERCASE_64_HEX.pattern
    )
    model_artifact_hash: StrictStr = Field(
        ..., min_length=1, pattern=LOWERCASE_64_HEX.pattern
    )
    model_code_version: StrictStr = Field(..., min_length=1)


class _RowPassthroughBaseModel(BaseModel):
    """Base for per-row passthrough schemas.

    The E2 service's :class:`ReplayTrainedExecutionRequest` accepts
    row payloads (``manifest_rows_payload``, ``training_rows``,
    ``label_rows``, ``training_samples``,
    ``supplemental_feature_values``) as ``tuple[dict[str, object], ...]``
    (generic per-row dicts). The HTTP layer mirrors this contract
    at the wire boundary: every row is required to be a JSON
    object (non-object → 422), and the inner keys are
    transparently forwarded to the E2 service which performs the
    full per-row validation.

    The per-row model deliberately uses ``extra="allow"`` and
    does NOT define explicit fields. This is the spec-compliant
    passthrough pattern: the strict nested model for the per-row
    structured payload IS the E2 service's
    :class:`ReplayTrainedExecutionRequest`. Pydantic v2 stores
    the extra fields in ``__pydantic_extra__``; the
    :meth:`model_dump` call returns them as-is.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )


class ManifestRowSchema(_RowPassthroughBaseModel):
    """See :class:`_RowPassthroughBaseModel`."""


class TrainingRowSchema(_RowPassthroughBaseModel):
    """See :class:`_RowPassthroughBaseModel`."""


class LabelRowSchema(_RowPassthroughBaseModel):
    """See :class:`_RowPassthroughBaseModel`."""


class TrainingSampleSchema(_RowPassthroughBaseModel):
    """See :class:`_RowPassthroughBaseModel`."""


class SupplementalFeatureValueSchema(_RowPassthroughBaseModel):
    """See :class:`_RowPassthroughBaseModel`."""


class ReplayTrainedRequestSchema(_StrictBaseModel):
    """Strict Pydantic request schema mirroring the frozen E2 contract.

    All fields are required unless explicitly typed ``None``-able.
    ``extra="forbid"`` rejects unknown fields. ``StrictBool``,
    ``StrictInt``, and ``StrictStr`` fields disable Pydantic's
    automatic type coercion for the specific scalar types the
    spec requires to be strict. Datetime fields are parsed by
    Pydantic v2 and MUST be timezone-aware (naive datetimes
    raise a 422).
    """

    # NOTE: the JSON field name is ``model_config`` (frozen at the wire
    # boundary by amendment §7.1) but the Python attribute name is
    # ``model_config_payload`` to avoid colliding with Pydantic's
    # ``model_config`` class variable.
    model_config_payload: ModelConfigSchema = Field(
        ...,
        validation_alias="model_config",
        serialization_alias="model_config",
    )
    model_policy: Literal["replay_trained_model"]
    task12_policy_version: StrictStr = Field(..., min_length=1)
    replay_attempt_id: StrictStr = Field(..., min_length=1)
    replay_node_id: StrictStr = Field(..., min_length=1)
    scenario_id: StrictStr = Field(..., min_length=1)
    forecast_cutoff_at: datetime
    training_cutoff_at: datetime
    allowed_training_season_ids: list[StrictInt] = Field(..., min_length=1)
    training_manifest: TrainingManifestSchema
    model_code_version: StrictStr = Field(..., min_length=1)
    replay_code_version: StrictStr = Field(..., min_length=1)
    task9_run_id: StrictInt = Field(..., ge=1)
    task9_result_hash: StrictStr = Field(
        ..., min_length=1, pattern=LOWERCASE_64_HEX.pattern
    )
    is_replay: StrictBool
    task10_config_snapshot: dict[StrictStr, object]
    manifest_rows_payload: list[ManifestRowSchema] = Field(..., min_length=1)
    training_rows: list[TrainingRowSchema] = Field(..., min_length=1)
    label_rows: list[LabelRowSchema]
    source_run_ids: dict[StrictStr, StrictInt]
    artifact_identity_json: ArtifactIdentitySchema
    artifact_identity_manifest: ArtifactIdentitySchema
    feature_actual_snapshot: dict[StrictStr, object] | None
    idempotency_key: StrictStr = Field(..., min_length=1)
    caller_identity: StrictStr = Field(..., min_length=1)
    training_samples: list[TrainingSampleSchema] = Field(..., min_length=1)
    supplemental_feature_values: list[SupplementalFeatureValueSchema]

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
            "code": "TASK012_REPLAY_TRAINED_INTEGRITY",
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
    """Return the stable public POST response body.

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
# GET endpoint (amendment §7.2) — application-level strict persisted loader
# ---------------------------------------------------------------------------


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
    delegates to the application-level
    :func:`load_replay_trained_prediction` loader which is
    fail-closed on every required identity field. The HTTP layer
    has only THREE possible outcomes:

    * typed result → 200 with the loader's response envelope;
    * :class:`ReplayTrainedServiceNotFoundError` → 404;
    * :class:`ReplayTrainedPersistedIdentityIntegrityError` →
      500 (loader detected a missing or malformed required field).
    """
    try:
        identity: ReplayTrainedPersistedIdentity = await load_replay_trained_prediction(
            session, prediction_run_id=prediction_run_id
        )
    except ReplayTrainedServiceNotFoundError as exc:
        return _json_error_response(
            {"error": exc.to_payload()}, status_code=404
        )
    except ReplayTrainedPersistedIdentityIntegrityError:
        logger.exception(
            "replay_trained_api.get_integrity_error prediction_run_id=%r",
            prediction_run_id,
        )
        return _json_error_response(
            _integrity_error_payload(),
            status_code=500,
        )
    except ReplayTrainedServiceError:
        logger.exception(
            "replay_trained_api.get_service_error prediction_run_id=%r",
            prediction_run_id,
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
    return _json_error_response(identity.to_response_payload(), status_code=200)


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
    5. Maps service errors to the stable transport envelope:

       * :class:`ReplayTrainedServiceInputError` → 422;
       * :class:`ReplayTrainedServiceConflictError` → 409;
       * :class:`ReplayTrainedServiceBlockerError` → 409;
       * :class:`ReplayTrainedServiceNotFoundError` → 404;
       * any other service / unexpected error → 500.
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
    except ReplayTrainedServiceNotFoundError as exc:
        return _json_error_response(
            {"error": exc.to_payload()}, status_code=404
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
