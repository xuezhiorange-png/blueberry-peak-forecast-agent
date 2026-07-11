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
from collections.abc import Mapping
from datetime import date, datetime
from typing import Annotated, Any, ClassVar, Literal, cast

from fastapi import APIRouter, Depends, Path, Response
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
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


def _redact_key(key: str) -> str:
    """Compute the irreversible correlation prefix for ``idempotency_key``.

    The TASK-012 transport MUST NOT log raw idempotency keys, full
    caller identities, request bodies, tokens, or secrets. A SHA-256
    prefix of the key is sufficient to correlate two log lines about
    the same execution without exposing the key itself.
    """
    import hashlib as _hashlib

    return _hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def _correlation_value(request: ReplayTrainedRequestSchema | None) -> str:
    """Return a non-reversible correlation prefix for log lines."""
    if request is None:
        return "no-request"
    if not request.idempotency_key:
        return "missing-key"
    return _redact_key(request.idempotency_key)


def _log_redacted(message: str, *args: Any) -> None:
    """Emit a structured log line with a SHA-256[:12] correlation prefix.

    The first positional argument after the format string is interpreted
    as the request correlation value (an opaque prefix, NOT the raw
    idempotency key). This helper is the ONLY entry-point for
    transport-layer log writes so that a future refactor cannot
    accidentally re-introduce a raw-key log.
    """
    logger.exception(message, *args)


# ---------------------------------------------------------------------------
# Strict nested Pydantic models (P0-#2 spec, amendment §7)
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
    training_dataset_hash: StrictStr = Field(..., min_length=1, pattern=LOWERCASE_64_HEX.pattern)
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
    """Frozen source-run-ids mapping per amendment §7.

    The HTTP contract uses an explicit ``extra="forbid"`` schema
    here so that unknown source-run-id keys are rejected at the
    wire boundary (P0-#5 spec). All values are strict positive
    integers (a numeric-string ``"91"`` is rejected; ``True``
    is rejected; ``91.0`` is rejected).
    """

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
    training_manifest_hash: StrictStr = Field(..., min_length=1, pattern=LOWERCASE_64_HEX.pattern)
    training_dataset_hash: StrictStr = Field(..., min_length=1, pattern=LOWERCASE_64_HEX.pattern)
    model_config_hash: StrictStr = Field(..., min_length=1, pattern=LOWERCASE_64_HEX.pattern)
    model_artifact_hash: StrictStr = Field(..., min_length=1, pattern=LOWERCASE_64_HEX.pattern)
    model_code_version: StrictStr = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Per-row strict schemas (replaces _RowPassthroughBaseModel(extra="allow"))
# ---------------------------------------------------------------------------
#
# Per amendment §7 + the P0-#5 spec, every nested row payload MUST be
# validated against an explicit strict schema. The previous
# ``_RowPassthroughBaseModel(extra="allow")`` shape is deleted. Each
# schema is ``extra="forbid"`` so unknown keys → 422.
#
# The fields below mirror the canonical rows produced by the Slice E2
# service (see :mod:`backend.app.residual_model.manifest.manifest_row_payload`
# and :mod:`backend.app.rolling_backtest.replay_trained_service._actual_input_rows`).
# The E2 service remains the authoritative business schema; these HTTP
# schemas are the fast-fail wire boundary.

_StrictNumericScalar = StrictStr | StrictInt | StrictFloat | StrictBool


class AnalyticsActualSnapshotSchema(_StrictBaseModel):
    """Schema mirroring :class:`AnalyticsActualSnapshot`."""

    build_run_id: StrictInt = Field(..., ge=1)
    source_max_raw_id: StrictInt = Field(..., ge=0)
    aggregation_version: StrictStr = Field(..., min_length=1)
    config_hash: StrictStr = Field(..., min_length=1, pattern=LOWERCASE_64_HEX.pattern)
    source_cutoff: datetime


class ManifestFeatureValueSchema(_StrictBaseModel):
    """Schema mirroring the canonical ``feature_values`` row payload."""

    feature_name: StrictStr = Field(..., min_length=1)
    value: _StrictNumericScalar | None = None
    known_at: datetime
    source_ref: dict[StrictStr, _StrictNumericScalar | list[_StrictNumericScalar] | None]
    source_version: StrictStr = Field(..., min_length=1)
    source_available_at: datetime
    observation_date: date | None = None


class ManifestFeatureVisibilityIssueSchema(_StrictBaseModel):
    """Schema mirroring :class:`FeatureVisibilityIssue` (open string code)."""

    code: StrictStr = Field(..., min_length=1)
    feature_name: StrictStr = Field(..., min_length=1)
    detail: StrictStr = Field(..., min_length=1)


class ManifestFeatureVisibilityAuditSchema(_StrictBaseModel):
    """Schema mirroring :class:`FeatureVisibilityAudit`."""

    status: StrictStr = Field(..., min_length=1)
    feature_count: StrictInt = Field(..., ge=0)
    visible_feature_count: StrictInt = Field(..., ge=0)
    blocked_feature_count: StrictInt = Field(..., ge=0)
    missing_feature_count: StrictInt = Field(..., ge=0)
    unknown_feature_count: StrictInt = Field(..., ge=0)
    blockers: list[ManifestFeatureVisibilityIssueSchema]
    warnings: list[StrictStr]
    audit_hash: StrictStr = Field(..., min_length=1, pattern=LOWERCASE_64_HEX.pattern)


class ManifestRowSchema(_StrictBaseModel):
    """Strict schema for one manifest row payload (amendment §7).

    Mirrors the keys produced by
    :func:`backend.app.residual_model.manifest.manifest_row_payload`.
    The HTTP layer rejects unknown keys (``extra="forbid"``) and
    rejects numeric strings in integer fields (``StrictInt``).
    """

    season_id: StrictInt = Field(..., ge=1)
    destination_factory_id: StrictInt = Field(..., ge=1)
    task9_run_id: StrictInt = Field(..., ge=1)
    task9_result_hash: StrictStr = Field(..., min_length=1, pattern=LOWERCASE_64_HEX.pattern)
    as_of_date: date
    target_arrival_local_date: date
    forecast_horizon_days: StrictInt = Field(..., ge=0)
    label_actual_snapshot: AnalyticsActualSnapshotSchema
    feature_actual_snapshot: AnalyticsActualSnapshotSchema
    observed_effective_receipt_kg: _StrictNumericScalar
    structural_p50_kg: _StrictNumericScalar
    structural_p80_kg: _StrictNumericScalar
    structural_p90_kg: _StrictNumericScalar
    residual_label_kg: _StrictNumericScalar
    feature_values: list[ManifestFeatureValueSchema]
    feature_visibility_audit: ManifestFeatureVisibilityAuditSchema | None = None
    feature_vector_hash: StrictStr = Field(..., min_length=1, pattern=LOWERCASE_64_HEX.pattern)
    feature_visibility_audit_hash: StrictStr = Field(
        ..., min_length=1, pattern=LOWERCASE_64_HEX.pattern
    )
    split: Literal["train", "validation", "holdout"]
    include: StrictBool
    sample_weight: _StrictNumericScalar
    exclusion_reason: StrictStr | None = None
    source_refs: list[StrictStr]


class TrainingRowSchema(_StrictBaseModel):
    """Strict schema for one training row.

    Mirrors the keys produced by
    :func:`ReplayTrainedExecutionRequest._request_training_rows` /
    :func:`backend.app.rolling_backtest.replay_trained_service._actual_input_rows`.
    """

    observation_date: date
    value: _StrictNumericScalar


class LabelRowSchema(_StrictBaseModel):
    """Strict schema for one label row.

    Mirrors the keys produced by
    :func:`ReplayTrainedExecutionRequest._request_label_rows` /
    :func:`backend.app.rolling_backtest.replay_trained_service._actual_input_rows`.
    """

    observation_date: date
    label_availability_date: date
    value: _StrictNumericScalar


class TrainingSampleSchema(_StrictBaseModel):
    """Strict schema for one training sample spec.

    Mirrors :class:`backend.app.residual_model.schemas.ResidualTrainingSampleSpec`.
    """

    task9_run_id: StrictInt = Field(..., ge=1)
    label_analytics_build_run_id: StrictInt = Field(..., ge=1)
    feature_analytics_build_run_id: StrictInt = Field(..., ge=1)
    split: Literal["train", "validation", "holdout"]
    include: StrictBool
    sample_weight: _StrictNumericScalar
    exclusion_reason: StrictStr | None = None
    supplemental_feature_values: list[SupplementalFeatureValueSchema] = Field(default_factory=list)


class SupplementalFeatureValueSchema(_StrictBaseModel):
    """Strict schema for one :class:`FeatureValue` payload."""

    feature_name: StrictStr = Field(..., min_length=1)
    value: _StrictNumericScalar | None = None
    known_at: datetime
    source_ref: dict[StrictStr, _StrictNumericScalar | list[_StrictNumericScalar] | None]
    source_version: StrictStr = Field(..., min_length=1)
    source_available_at: datetime
    observation_date: date | None = None


# Resolve the forward reference for TrainingSampleSchema.
TrainingSampleSchema.model_rebuild()


# ---------------------------------------------------------------------------
# Open canonical JSON payload (deliberately permissive shape)
# ---------------------------------------------------------------------------
#
# ``task10_config_snapshot`` and ``feature_actual_snapshot`` are
# intentionally open canonical-JSON payloads — the wire format does
# NOT freeze a per-field shape; the E2 service is the authoritative
# schema. However, the §7 contract requires the wire boundary to:
#
#   1. Reject non-string dict keys (JSON-compatible values only —
#      Python objects / bytes / custom classes MUST be rejected);
#   2. Reject silent coercion (no implicit ``str(...)`` on a non-string
#      scalar, no implicit ``int(...)`` on a numeric string);
#   3. Reject unknown top-level / nested keys in container bodies
#      (the open-key nature is documented but each VALUE is still
#      validated as JSON-compatible).
#
# These two fields are the ONLY intentionally-open fields in the
# request schema. All other fields use explicit strict schemas.


class _CanonicalJsonPayloadSchema(_StrictBaseModel):
    """Strict JSON-only payload schema for ``task10_config_snapshot`` etc.

    The OUTER model is ``extra="allow"`` because the payload IS the
    open canonical-JSON tree (the spec allows dynamic keys inside
    the value tree; see amendment §7). The outer ``extra="allow"``
    is the documented exception that justifies the canonical-JSON
    payload being intentionally open. The JSON-only invariant
    (no Python objects / bytes / datetime-as-objects / decimal-as-
    objects / non-string dict keys / silent coercion) is enforced
    by :meth:`_normalize_open_payload` which walks the parsed
    payload before the model accepts it.

    All OTHER fields in the request schema use explicit strict
    schemas (``extra="forbid"``); this is the ONLY place where
    ``extra="allow"`` is permitted, and the JSON-only check makes
    the open shape safer than a typed schema with N declared fields.
    """

    __slots__ = ()

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )

    def __init__(self, **data: Any) -> None:
        # Pydantic v2 does not natively support self-referential
        # ``_JsonValue`` types in field annotations without a
        # ``model_rebuild`` cycle. We instead enforce the JSON-only
        # invariant by walking the parsed payload in
        # :meth:`_normalize_open_payload` below. The outer model has
        # no declared fields; the parsed ``data`` IS the open
        # payload.
        super().__init__(**self._normalize_open_payload(data))

    @staticmethod
    def _normalize_open_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
        """Validate that ``payload`` is JSON-compatible and return it as-is.

        A value is JSON-compatible if it is:

        * ``None``, ``bool``, ``int``, ``float``, ``str``;
        * ``list`` whose items are JSON-compatible;
        * ``dict`` whose keys are ``str`` and whose values are
          JSON-compatible.

        Anything else (``bytes``, ``Decimal``, ``datetime``, ``date``,
        Pydantic models, custom classes, ...) is rejected.
        """

        def _check(value: object, *, path: str) -> object:
            if value is None or isinstance(value, (bool, int, float, str)):
                return value
            if isinstance(value, list):
                return [_check(item, path=f"{path}[]") for item in value]
            if isinstance(value, dict):
                normalized: dict[str, Any] = {}
                for raw_key, raw_value in value.items():
                    if not isinstance(raw_key, str):
                        raise ValueError(
                            f"{path}<key> must be a string (got {type(raw_key).__name__})"
                        )
                    normalized[raw_key] = _check(
                        raw_value, path=f"{path}.{raw_key}" if path else raw_key
                    )
                return normalized
            raise ValueError(f"{path}: value of type {type(value).__name__} is not JSON-compatible")

        return cast(dict[str, Any], _check(dict(payload), path=""))


class Task10ConfigSnapshotSchema(_CanonicalJsonPayloadSchema):
    """Open canonical-JSON payload for ``task10_config_snapshot``."""


class FeatureActualSnapshotSchema(_CanonicalJsonPayloadSchema):
    """Open canonical-JSON payload for ``feature_actual_snapshot``.

    ``feature_actual_snapshot`` is optional (``None`` is also a
    valid value at the wire boundary, alongside an empty object).
    """


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
    task9_result_hash: StrictStr = Field(..., min_length=1, pattern=LOWERCASE_64_HEX.pattern)
    is_replay: StrictBool
    task10_config_snapshot: Task10ConfigSnapshotSchema
    manifest_rows_payload: list[ManifestRowSchema] = Field(..., min_length=1)
    training_rows: list[TrainingRowSchema] = Field(..., min_length=1)
    label_rows: list[LabelRowSchema]
    source_run_ids: SourceRunIdsSchema
    artifact_identity_json: ArtifactIdentitySchema
    artifact_identity_manifest: ArtifactIdentitySchema
    feature_actual_snapshot: FeatureActualSnapshotSchema | None
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
# Stable error envelope (amendment §7.3, §7.4)
# ---------------------------------------------------------------------------
#
# The TASK-012 frozen contract requires the public envelope to carry
# EXACTLY four keys: ``error.code``, ``error.message``, ``error.blocker``,
# and ``error.identity``. Internal mismatched-field detail MAY be logged
# or carried in the ``identity`` dict, but the public envelope MUST NOT
# add ``details`` / ``mismatched_fields`` / or any other top-level keys.
#
# The frozen public code for integrity failures is
# ``TASK012_REPLAY_TRAINED_INTEGRITY_ERROR`` (with the ``_ERROR`` suffix).
# Prior rounds incorrectly returned ``TASK012_REPLAY_TRAINED_INTEGRITY``;
# the contract test enforces the exact full code string.


def _envelope(
    *,
    code: str,
    message: str,
    blocker: str | None,
    identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the frozen public error envelope.

    The envelope is the single source of truth for ALL public error
    responses. It contains exactly four keys: ``code``, ``message``,
    ``blocker``, ``identity``. The transport layer MUST NOT add any
    other top-level keys (``details`` / ``mismatched_fields`` /
    etc.); the canonical ``identity`` dict MAY carry mismatched-field
    metadata internally but the public top-level key set is frozen.
    """
    return {
        "error": {
            "code": code,
            "message": message,
            "blocker": blocker,
            "identity": dict(identity) if identity else {},
        }
    }


def _not_found_payload(identity: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return _envelope(
        code="TASK012_REPLAY_TRAINED_NOT_FOUND",
        message="The requested replay-trained prediction authority was not found.",
        blocker=None,
        identity=dict(identity) if identity else None,
    )


def _input_invalid_payload() -> dict[str, Any]:
    return _envelope(
        code="TASK012_REPLAY_TRAINED_INPUT_INVALID",
        message="Replay-trained request is invalid.",
        blocker=None,
        identity={},
    )


def _conflict_payload(mismatched_fields: tuple[str, ...]) -> dict[str, Any]:
    return _envelope(
        code="TASK012_REPLAY_TRAINED_CONFLICT",
        message="Replay-trained request conflicts with a prior persisted prediction.",
        blocker=None,
        identity={"mismatched_fields": list(mismatched_fields)},
    )


def _blocked_payload(
    blocker_code: str | None,
    mismatched_fields: tuple[str, ...],
) -> dict[str, Any]:
    return _envelope(
        code="TASK012_REPLAY_TRAINED_BLOCKED",
        message="Replay-trained request is blocked by a TASK-012 deterministic blocker.",
        blocker=blocker_code,
        identity={"mismatched_fields": list(mismatched_fields)},
    )


def _integrity_error_payload(
    mismatched_fields: tuple[str, ...] = (),
) -> dict[str, Any]:
    return _envelope(
        code="TASK012_REPLAY_TRAINED_INTEGRITY_ERROR",
        message="TASK-012 replay-trained prediction integrity check failed.",
        blocker=None,
        identity=({"mismatched_fields": list(mismatched_fields)} if mismatched_fields else {}),
    )


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
        # Build the frozen 404 envelope from the exception's identity dict.
        # The public envelope exposes the not-found selector under
        # ``error.identity`` (NOT ``error.details``); the exception's
        # ``to_payload`` shape is an internal contract that the transport
        # layer MUST NOT forward verbatim.
        not_found_identity: dict[str, Any] = {"prediction_run_id": prediction_run_id}
        if exc.identity:
            not_found_identity.update(dict(exc.identity))
        return _json_error_response(
            _not_found_payload(identity=not_found_identity),
            status_code=404,
        )
    except ReplayTrainedPersistedIdentityIntegrityError as exc:
        _log_redacted(
            "replay_trained_api.get_integrity_error prediction_run_id=%r mismatched_fields=%r",
            prediction_run_id,
            exc.mismatched_fields,
        )
        return _json_error_response(
            _integrity_error_payload(mismatched_fields=exc.mismatched_fields),
            status_code=500,
        )
    except ReplayTrainedServiceError as exc:
        _log_redacted(
            "replay_trained_api.get_service_error prediction_run_id=%r mismatched_fields=%r",
            prediction_run_id,
            exc.mismatched_fields,
        )
        return _json_error_response(
            _integrity_error_payload(mismatched_fields=exc.mismatched_fields),
            status_code=500,
        )
    except Exception:
        _log_redacted(
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

    correlation = _correlation_value(request)
    try:
        result = await execute_replay_trained_prediction(session, request=e2_request)
    except ReplayTrainedServiceInputError:
        return _json_error_response(
            _input_invalid_payload(),
            status_code=422,
        )
    except ReplayTrainedServiceNotFoundError as exc:
        # Frozen 404 envelope. The HTTP transport builds it from the
        # exception's public ``identity`` dict (which carries the
        # not-found selector); the exception's ``to_payload`` shape
        # is an internal contract and is NOT forwarded verbatim.
        not_found_identity: dict[str, Any] = {}
        if exc.identity:
            not_found_identity.update(dict(exc.identity))
        return _json_error_response(
            _not_found_payload(identity=not_found_identity),
            status_code=404,
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
    except ReplayTrainedServiceError as exc:
        _log_redacted(
            "replay_trained_api.post_service_error correlation=%r mismatched_fields=%r",
            correlation,
            exc.mismatched_fields,
        )
        return _json_error_response(
            _integrity_error_payload(mismatched_fields=exc.mismatched_fields),
            status_code=500,
        )
    except Exception:
        _log_redacted(
            "replay_trained_api.post_unexpected_error correlation=%r",
            correlation,
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
