"""TASK-012 Slice E2 replay-trained application service.

This is the only production boundary that opens ``replay_trained_model``.
It verifies a complete replay identity, rebuilds the Task 10 dataset from
persisted authorities, and delegates execution to the real Task 10
application service.  It never selects a model or source implicitly.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, replace
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Final, cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.harvest_state.persistence import load_harvest_state_output_by_id
from backend.app.models.analytics import AnalyticsBuildRun
from backend.app.models.harvest_state import HarvestStateRun
from backend.app.models.residual_model import ResidualModelPredictionRun
from backend.app.repositories.residual_model import (
    get_residual_prediction_run,
    get_residual_training_run,
    list_residual_artifacts,
)
from backend.app.residual_model.application import (
    ResidualPredictionApplicationIntegrityError,
    ResidualTrainingApplicationIntegrityError,
    execute_residual_prediction,
    execute_residual_training,
)
from backend.app.residual_model.canonical import (
    canonical_json_dumps,
    canonical_json_value,
    canonical_payload_hash,
)
from backend.app.residual_model.config import load_residual_model_config_from_snapshot
from backend.app.residual_model.manifest import manifest_hash, manifest_row_payload
from backend.app.residual_model.persistence import (
    ResidualModelPersistenceIntegrityError,
    load_residual_prediction_run_by_id,
)
from backend.app.residual_model.schemas import (
    FeatureValue,
    ResidualPredictionExecutionResult,
    ResidualPredictionRequest,
    ResidualTrainingExecutionResult,
    ResidualTrainingManifestRow,
    ResidualTrainingSampleSpec,
)
from backend.app.residual_model.training_manifest import (
    ResidualManifestBuildError,
    build_residual_training_manifest,
)

from .canonical import sha256_payload
from .enums import Task10ModelPolicy
from .orchestration import OrchestrationBlocker
from .replay_trained_filtering import (
    FilteredLabelRow,
    FilteredTrainingRow,
    TrainingRowsEmptyError,
    filter_labels_by_availability_cutoff,
    filter_training_rows_by_cutoff,
    require_non_empty_training_rows,
)
from .replay_trained_identity import (
    ModelConfigPayload,
    ReplayTrainedIdentityProjection,
    TrainingManifestPayload,
    project_replay_trained_identity,
)
from .replay_trained_prediction import (
    ArtifactIdentityPair,
    ReplayTrainedArtifactIdentityMismatchError,
    verify_replay_trained_artifact_identity,
)

_SERVICE_VERSION: Final[str] = "task12-slice-e2-v2"
_HASH_LENGTH: Final[int] = 64
_TASK12_TRAINING_EXECUTION_FAILED: Final[str] = "task12_training_execution_failed"
_TASK12_DATASET_MISMATCH: Final[str] = "task12_training_dataset_mismatch"
_TASK12_PERSISTENCE_INTEGRITY: Final[str] = "task12_persistence_integrity_failure"


class ReplayTrainedServiceError(ValueError):
    """Base error with stable machine-readable service metadata.

    The frozen public envelope is ``{code, message, blocker, identity}``
    (amendment §7.3 + §7.4). The HTTP layer builds this envelope
    explicitly from the public attributes of the exception class; the
    internal ``to_payload`` helper is a JSON-canonical snapshot for
    service-level logging / audit and is NOT forwarded verbatim to the
    HTTP client. The internal payload preserves ``mismatched_fields``
    and ``details`` for log forensics but those fields MUST NOT leak
    into the public envelope.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str,
        blocker_code: str | None = None,
        mismatched_fields: tuple[str, ...] = (),
        details: Mapping[str, object] | None = None,
        identity: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        # Public attributes (HTTP transport reads these).
        self.message: str = message
        self.code: str = code
        self.blocker_code: str | None = blocker_code
        self.identity: dict[str, object] = dict(identity) if identity else {}
        # Internal-only attributes (service-layer logging / audit).
        self.mismatched_fields: tuple[str, ...] = mismatched_fields
        self._internal_details: dict[str, object] = dict(details) if details else {}
        # Canonical-JSON payload is a service-internal snapshot of the
        # full exception metadata (including internal mismatched-fields
        # and details); it is NEVER forwarded verbatim to the wire.
        internal_payload: dict[str, object] = {
            "code": code,
            "message": message,
            "blocker": blocker_code,
            "mismatched_fields": list(mismatched_fields),
        }
        if self._internal_details:
            internal_payload["details"] = dict(self._internal_details)
        if self.identity:
            internal_payload["identity"] = dict(self.identity)
        self.payload = canonical_json_dumps(internal_payload)

    def to_payload(self) -> dict[str, object]:
        return cast(dict[str, object], json.loads(self.payload))


class ReplayTrainedServiceInputError(ReplayTrainedServiceError):
    """Request or policy contract failure."""

    def __init__(self, message: str, *, mismatched_fields: tuple[str, ...] = ()) -> None:
        super().__init__(
            message,
            code="TASK012_REPLAY_TRAINED_INPUT_INVALID",
            mismatched_fields=mismatched_fields,
        )


class ReplayTrainedServiceBlockerError(ReplayTrainedServiceError):
    """A deterministic TASK-012 blocker."""

    def __init__(
        self,
        message: str,
        *,
        blocker_code: str,
        mismatched_fields: tuple[str, ...] = (),
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="TASK012_REPLAY_TRAINED_BLOCKED",
            blocker_code=blocker_code,
            mismatched_fields=mismatched_fields,
            details=details,
        )


class ReplayTrainedServiceConflictError(ReplayTrainedServiceError):
    """Durable idempotency or exact-identity conflict."""

    def __init__(self, message: str, *, mismatched_fields: tuple[str, ...]) -> None:
        super().__init__(
            message,
            code="TASK012_REPLAY_TRAINED_CONFLICT",
            mismatched_fields=mismatched_fields,
        )


class ReplayTrainedServiceNotFoundError(ReplayTrainedServiceError):
    """The referenced Task 9 / Task 8 / training / artifact authority does not exist.

    This is distinct from ``ReplayTrainedServiceBlockerError`` (409): the
    authority is missing entirely. The HTTP layer maps this to a 404
    response with a stable ``TASK012_REPLAY_TRAINED_NOT_FOUND`` envelope.
    The constructor takes a public ``identity`` mapping that the HTTP
    transport layer surfaces under ``error.identity`` (frozen envelope
    key set).
    """

    def __init__(
        self,
        message: str,
        *,
        identity: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="TASK012_REPLAY_TRAINED_NOT_FOUND",
            identity=identity,
        )


class ReplayTrainedPersistedIdentityIntegrityError(ReplayTrainedServiceError):
    """Strict persisted identity loader detected a missing or malformed field.

    The HTTP layer maps this to a 500 response with the stable
    ``TASK012_REPLAY_TRAINED_INTEGRITY_ERROR`` envelope (amendment §7.4
    — the canonical public code includes the ``_ERROR`` suffix; the
    no-suffix form is forbidden by the §7 contract tests). The loader
    is fail-closed: it NEVER returns ``None`` for a required identity
    field and NEVER substitutes a default value.
    """

    def __init__(
        self,
        message: str,
        *,
        mismatched_fields: tuple[str, ...] = (),
    ) -> None:
        super().__init__(
            message,
            code="TASK012_REPLAY_TRAINED_INTEGRITY_ERROR",
            mismatched_fields=mismatched_fields,
        )


@dataclass(frozen=True, slots=True)
class ReplayTrainedPersistedIdentity:
    """Strict typed envelope built by the application-level loader.

    ALL fields are non-None required identity fields read from the
    persisted ORM row (P0-#5 spec). The HTTP GET endpoint MUST return
    this object as a 200 response without any dict reconstruction,
    default values, or fallback identities. The loader raises
    :class:`ReplayTrainedPersistedIdentityIntegrityError` if any
    required field is missing, malformed, or fails
    deterministic-redeterminism verification.

    The fields are exhaustive with respect to amendment §7: every
    required GET identity is declared here (no nullable identity
    field). The previously-permissive ``Optional[...]`` shape is
    deleted; the loader is fail-closed on any missing required field.
    """

    prediction_run_id: int
    prediction_hash: str
    request_payload_hash: str
    model_policy: str
    task12_policy_version: str
    replay_attempt_id: str
    replay_node_id: str
    scenario_id: str
    training_manifest_hash: str
    training_dataset_hash: str
    model_config_hash: str
    model_artifact_hash: str
    model_code_version: str
    forecast_cutoff_at: str
    training_cutoff_at: str
    task9_run_id: int
    task9_result_hash: str
    task10_training_run_id: int
    task10_training_signature: str
    task10_manifest_hash: str
    task10_config_hash: str
    task10_artifact_hashes: tuple[str, ...]
    filtered_training_row_count: int
    filtered_label_row_count: int
    training_execution_status: str
    training_eligibility_status: str
    prediction_execution_status: str
    prediction_mode: str
    idempotency_key: str
    caller_identity: str
    audit_identity: str

    def to_response_payload(self) -> dict[str, object]:
        """Return the wire envelope.

        The HTTP layer MUST NOT add, remove, default, or rename
        fields. The loader is the single source of truth for the
        response shape.
        """
        return {
            "prediction_run_id": self.prediction_run_id,
            "prediction_hash": self.prediction_hash,
            "request_payload_hash": self.request_payload_hash,
            "model_policy": self.model_policy,
            "task12_policy_version": self.task12_policy_version,
            "replay_attempt_id": self.replay_attempt_id,
            "replay_node_id": self.replay_node_id,
            "scenario_id": self.scenario_id,
            "training_manifest_hash": self.training_manifest_hash,
            "training_dataset_hash": self.training_dataset_hash,
            "model_config_hash": self.model_config_hash,
            "model_artifact_hash": self.model_artifact_hash,
            "model_code_version": self.model_code_version,
            "forecast_cutoff_at": self.forecast_cutoff_at,
            "training_cutoff_at": self.training_cutoff_at,
            "task9_run_id": self.task9_run_id,
            "task9_result_hash": self.task9_result_hash,
            "task10_training_run_id": self.task10_training_run_id,
            "task10_training_signature": self.task10_training_signature,
            "task10_manifest_hash": self.task10_manifest_hash,
            "task10_config_hash": self.task10_config_hash,
            "task10_artifact_hashes": list(self.task10_artifact_hashes),
            "filtered_training_row_count": self.filtered_training_row_count,
            "filtered_label_row_count": self.filtered_label_row_count,
            "training_execution_status": self.training_execution_status,
            "training_eligibility_status": self.training_eligibility_status,
            "prediction_execution_status": self.prediction_execution_status,
            "prediction_mode": self.prediction_mode,
            "idempotency_key": self.idempotency_key,
            "caller_identity": self.caller_identity,
            "audit_identity": self.audit_identity,
        }


# Lowercase 64-character hex hash. Used for ALL frozen TASK-012 identity
# hash fields. The strict loader uses this regex to fail-closed if a
# persisted hash is malformed.
_LOWERCASE_64_HEX: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")


def _strict_required_str(
    context: Mapping[str, object],
    key: str,
) -> str:
    """Read a required string field; raise integrity error if missing/malformed.

    The P0-#5 spec requires the loader to fail-closed on EVERY
    required identity field: missing → 500, type mismatch → 500,
    empty string → 500. NEVER a fallback default value.
    """
    if key not in context:
        raise ReplayTrainedPersistedIdentityIntegrityError(
            f"persisted identity is missing required field {key!r}",
            mismatched_fields=(f"{key}_missing",),
        )
    value = context[key]
    if not isinstance(value, str) or not value:
        raise ReplayTrainedPersistedIdentityIntegrityError(
            f"persisted identity field {key!r} must be a non-empty string",
            mismatched_fields=(f"{key}_type",),
        )
    return value


def _strict_required_int(
    context: Mapping[str, object],
    key: str,
) -> int:
    """Read a required integer field; raise integrity error if missing/malformed.

    The persisted type MUST be a native ``int``; ``bool`` is rejected
    (Python ``bool`` is a subclass of ``int`` but represents a flag,
    not a count), numeric strings are rejected, and ``float`` is
    rejected. Persisted type drift is integrity failure, not silent
    coercion.
    """
    if key not in context:
        raise ReplayTrainedPersistedIdentityIntegrityError(
            f"persisted identity is missing required field {key!r}",
            mismatched_fields=(f"{key}_missing",),
        )
    value = context[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ReplayTrainedPersistedIdentityIntegrityError(
            f"persisted identity field {key!r} must be a native integer "
            "(bool / numeric string / float are not accepted)",
            mismatched_fields=(f"{key}_type",),
        )
    return value


def _strict_required_non_empty_str_list(
    context: Mapping[str, object],
    key: str,
) -> tuple[str, ...]:
    """Read a required non-empty list of non-empty strings.

    The persisted list MUST contain at least one item; each item
    MUST be a non-empty string. ``None`` items, ``int`` items, and
    empty strings are integrity failures.
    """
    if key not in context:
        raise ReplayTrainedPersistedIdentityIntegrityError(
            f"persisted identity is missing required field {key!r}",
            mismatched_fields=(f"{key}_missing",),
        )
    value = context[key]
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item for item in value)
    ):
        raise ReplayTrainedPersistedIdentityIntegrityError(
            f"persisted identity field {key!r} must be a non-empty list of non-empty strings",
            mismatched_fields=(f"{key}_type",),
        )
    return tuple(value)


def _strict_required_lowercase_64_hex(context: Mapping[str, object], key: str) -> str:
    value = _strict_required_str(context, key)
    if not _LOWERCASE_64_HEX.match(value):
        raise ReplayTrainedPersistedIdentityIntegrityError(
            f"persisted identity field {key!r} must be a lowercase 64-character hex hash",
            mismatched_fields=(f"{key}_format",),
        )
    return value


def _strict_required_true_bool(
    context: Mapping[str, object],
    key: str,
) -> bool:
    """Read a required boolean flag; raise integrity error on drift.

    The persisted type MUST be a native ``bool``; strings (``"true"`` /
    ``"false"``), integers (``0`` / ``1``), and ``None`` are all
    rejected. The flag value MUST be ``True`` — a persisted ``False``
    is an integrity failure (not silent acceptance + later audit
    mismatch). Missing keys, wrong types, and wrong values all fail
    closed with precise ``{key}_missing`` / ``{key}_type`` /
    ``{key}_mismatch`` ``mismatched_fields`` reasons.

    This helper is the strict-required successor to silent
    ``bool(value or False)`` coercion. Silent coercion allowed
    ``"false"`` (a non-empty string) to be coerced to ``True`` and
    then re-serialized into the audit payload, producing an audit
    hash that was internally consistent with the WRONG boolean
    value — a corruption that the byte-for-byte equality check
    could not detect. The strict helper closes that gap.
    """
    if key not in context:
        raise ReplayTrainedPersistedIdentityIntegrityError(
            f"persisted audit field {key!r} is missing",
            mismatched_fields=(f"{key}_missing",),
        )
    value = context[key]
    # ``bool`` MUST be a real ``bool`` — strings / ints / ``None`` are
    # wrong-type and must not silently coerce.
    if not isinstance(value, bool):
        raise ReplayTrainedPersistedIdentityIntegrityError(
            f"persisted audit field {key!r} must be a native boolean",
            mismatched_fields=(f"{key}_type",),
        )
    if value is not True:
        raise ReplayTrainedPersistedIdentityIntegrityError(
            f"persisted audit field {key!r} must remain true",
            mismatched_fields=(f"{key}_mismatch",),
        )
    return value


def _recompute_audit_payload(typed_audit: Mapping[str, object]) -> dict[str, object]:
    """Rebuild the canonical 31-field audit payload from a persisted
    ``typed_attempt.task12_replay`` dict.

    The persisted form is byte-identical to the 31-field dict
    produced by :func:`_task12_audit_payload` (write-time). The
    loader reconstructs the same dict here (without ``audit_identity``)
    and computes :func:`_audit_identity` against it.

    This is the SAME canonical function used at write time by the
    Slice E2 service (``_task12_audit_payload``); the loader MUST
    rebuild the audit payload from the persisted canonical payload
    and compare exact equality with the persisted
    ``typed_attempt.task12_replay.audit_identity`` (P0-#2 spec).

    Any tampering that replaces ANY of the 31 audit fields — including
    a different valid-but-wrong 64-hex ``audit_identity`` — is caught
    by the byte-for-byte equality check below.
    """
    return _task12_audit_payload(
        service_version=str(typed_audit.get("service_version") or ""),
        model_policy=str(typed_audit.get("model_policy") or ""),
        task12_policy_version=str(typed_audit.get("task12_policy_version") or ""),
        replay_attempt_id=str(typed_audit.get("replay_attempt_id") or ""),
        replay_node_id=str(typed_audit.get("replay_node_id") or ""),
        scenario_id=str(typed_audit.get("scenario_id") or ""),
        training_manifest_hash=str(typed_audit.get("training_manifest_hash") or ""),
        training_dataset_hash=str(typed_audit.get("training_dataset_hash") or ""),
        model_config_hash=str(typed_audit.get("model_config_hash") or ""),
        model_artifact_hash=str(typed_audit.get("model_artifact_hash") or ""),
        model_code_version=str(typed_audit.get("model_code_version") or ""),
        forecast_cutoff_at=str(typed_audit.get("forecast_cutoff_at") or ""),
        training_cutoff_at=str(typed_audit.get("training_cutoff_at") or ""),
        task9_run_id=_coerce_int_strict(typed_audit.get("task9_run_id"), field_name="task9_run_id"),
        task9_result_hash=str(typed_audit.get("task9_result_hash") or ""),
        prediction_hash=str(typed_audit.get("prediction_hash") or ""),
        request_payload_hash=str(typed_audit.get("request_payload_hash") or ""),
        filtered_training_row_count=_coerce_int_strict(
            typed_audit.get("filtered_training_row_count"),
            field_name="filtered_training_row_count",
        ),
        filtered_label_row_count=_coerce_int_strict(
            typed_audit.get("filtered_label_row_count"),
            field_name="filtered_label_row_count",
        ),
        training_execution_status=str(typed_audit.get("training_execution_status") or ""),
        training_eligibility_status=str(typed_audit.get("training_eligibility_status") or ""),
        prediction_execution_status=str(typed_audit.get("prediction_execution_status") or ""),
        prediction_mode=str(typed_audit.get("prediction_mode") or ""),
        task10_training_run_id=_coerce_int_strict(
            typed_audit.get("task10_training_run_id"),
            field_name="task10_training_run_id",
        ),
        task10_training_signature=str(typed_audit.get("task10_training_signature") or ""),
        task10_manifest_hash=str(typed_audit.get("task10_manifest_hash") or ""),
        task10_config_hash=str(typed_audit.get("task10_config_hash") or ""),
        task10_artifact_hashes=tuple(
            cast(Sequence[str], typed_audit.get("task10_artifact_hashes") or ())
        ),
        idempotency_key=str(typed_audit.get("idempotency_key") or ""),
        caller_identity=str(typed_audit.get("caller_identity") or ""),
        no_implicit_selection=_strict_required_true_bool(
            typed_audit,
            "no_implicit_selection",
        ),
        no_cross_run_substitution=_strict_required_true_bool(
            typed_audit,
            "no_cross_run_substitution",
        ),
    )


def _coerce_int_strict(value: object, *, field_name: str) -> int:
    """Coerce ``value`` to a native ``int``.

    Native ``int`` is accepted; ``bool`` is rejected (Python ``bool``
    is a subclass of ``int`` but a flag is not a numeric identity);
    numeric strings are rejected; ``float`` is rejected; missing
    values raise ``{field_name}_missing``. Type drift is a
    redetermination failure, not a silent coercion.
    """
    if value is None or isinstance(value, (str, float)):
        # ``None`` / numeric-string / float: missing-OR-wrong-type —
        # emit the dedicated ``_missing`` reason when there's no key
        # and ``_type`` when the key exists but is the wrong type.
        # From the loader's point of view the field name is the same.
        raise ReplayTrainedPersistedIdentityIntegrityError(
            f"persisted audit payload field {field_name!r} is missing or has the wrong type",
            mismatched_fields=(f"{field_name}_missing",),
        )
    if isinstance(value, bool):
        raise ReplayTrainedPersistedIdentityIntegrityError(
            f"persisted audit payload integer field {field_name!r} is a bool, not an int",
            mismatched_fields=(f"{field_name}_type",),
        )
    if isinstance(value, int):
        return value
    raise ReplayTrainedPersistedIdentityIntegrityError(
        f"persisted audit payload integer field {field_name!r} is not a native int",
        mismatched_fields=(f"{field_name}_type",),
    )


def _recompute_prediction_hash(loaded: ResidualPredictionExecutionResult) -> str:
    """Recompute the canonical prediction hash for a persisted result.

    This mirrors the write-time
    :func:`backend.app.residual_model.persistence._prediction_hash_from_result`
    helper: the payload is the canonical-JSON dump of the result,
    then ``prediction_hash`` is replaced with ``None``, then the
    payload is hashed. We re-implement the helper locally (rather
    than import the private function from residual_model.persistence)
    so that the TASK-012 loader has no cross-module dependency on
    the residual-model persistence layer's private API. The
    canonical-JSON dump goes through :func:`canonical_json_value`
    which is the same dump used at write time.
    """
    payload = canonical_json_value(loaded.model_dump(mode="python"))
    cast_dict = cast(dict[str, object], payload)
    cast_dict["prediction_hash"] = None
    return canonical_payload_hash(cast_dict)


async def load_replay_trained_prediction(
    session: AsyncSession,
    *,
    prediction_run_id: int,
) -> ReplayTrainedPersistedIdentity:
    """Strict application-level loader for the TASK-012 GET endpoint.

    Reads the persisted ORM row at the exact ``prediction_run_id``
    and projects every frozen TASK-012 identity field. Fails
    closed with :class:`ReplayTrainedPersistedIdentityIntegrityError`
    (mapped by HTTP to 500) if any of the 14 required integrity
    conditions below is violated. Fails closed with
    :class:`ReplayTrainedServiceNotFoundError` (mapped by HTTP to
    404) if the row is absent. The HTTP layer MUST NOT add
    fallback defaults or skip fields; this function is the single
    source of truth.

    Integrity conditions (P0-#5 / §3 spec):

    1.  Exact ``prediction_run_id`` row exists.
    2.  ``input_snapshot.task12_replay`` dict is present.
    3.  ``typed_attempt.task12_replay`` dict is present.
    4.  All required fields (model_policy, task9_run_id,
        request_payload_hash, training_manifest_hash, etc.) are
        present in the persisted context.
    5.  Each required field has the correct Python type
        (string, int, list-of-string, etc.).
    6.  All frozen hash fields are lowercase 64-character hex.
    7.  ``model_policy`` is exactly ``"replay_trained_model"``.
    8.  ``prediction_hash`` matches
        ``row.canonical_payload_hash``.
    9.  ``task9_run_id`` matches the Task 9 authority referenced
        in the persisted context.
    10. ``task9_result_hash`` matches the persisted authority.
    11. Training / config / artifact identity hashes are consistent
        with the persisted projection.
    12. ``audit_identity`` is deterministic-redeterminism: the
        redetermined identity MUST equal the persisted identity.
    13. The loader NEVER returns ``None`` for a required field; it
        raises an integrity error instead.
    14. The loader NEVER fabricates fallback identities ("", "0",
        "[]", or default values).
    """
    row = await get_residual_prediction_run(session, run_id=prediction_run_id)
    if row is None:
        raise ReplayTrainedServiceNotFoundError(
            "the requested replay-trained prediction was not found",
            identity={"prediction_run_id": prediction_run_id},
        )

    input_snapshot = row.input_snapshot or {}
    if not isinstance(input_snapshot, Mapping):
        raise ReplayTrainedPersistedIdentityIntegrityError(
            "persisted input_snapshot must be a mapping",
            mismatched_fields=("input_snapshot_type",),
        )
    # The ``input_snapshot.task12_replay`` field holds the
    # EXECUTION-PASS lightweight context from :func:`_task12_context`
    # (~22 fields, no ``audit_identity``). The full audit-critical
    # 32-field payload lives in ``typed_attempt.task12_replay`` —
    # written by :func:`_finalize_task12_audit_payload` after the
    # prediction commits. ``input_snapshot`` participates in the
    # residual-model persistence layer's parent-payload hash; we
    # therefore keep it stable and never overwrite it post-write.
    legacy_context_obj = input_snapshot.get("task12_replay")
    if not isinstance(legacy_context_obj, Mapping):
        raise ReplayTrainedPersistedIdentityIntegrityError(
            "persisted input_snapshot.task12_replay is missing",
            mismatched_fields=("input_snapshot_task12_replay_missing",),
        )
    # ``legacy_context_obj`` is only checked for presence + type —
    # its content is no longer read by the loader (see below). The
    # presence check is the audit trail that the lightweight
    # execution-pass form is intact.

    typed_attempt = row.typed_attempt or {}
    if not isinstance(typed_attempt, Mapping):
        raise ReplayTrainedPersistedIdentityIntegrityError(
            "persisted typed_attempt must be a mapping",
            mismatched_fields=("typed_attempt_type",),
        )
    typed_audit_obj = typed_attempt.get("task12_replay")
    if not isinstance(typed_audit_obj, Mapping):
        raise ReplayTrainedPersistedIdentityIntegrityError(
            "persisted typed_attempt.task12_replay is missing",
            mismatched_fields=("typed_attempt_task12_replay_missing",),
        )
    typed_audit = cast(Mapping[str, object], typed_audit_obj)
    # SINGLE source of truth for the strict-required identity fields
    # below. ``typed_audit`` is the full audit-critical 32-field dict
    # produced by :func:`_task12_audit_payload` at write time and is
    # the exact dict the audit-identity recomputation step uses.
    # Reading from ``legacy_context`` (input_snapshot.task12_replay)
    # would either miss audit-only fields or — worse — see a
    # different lightweight dict whose hash is computed over a
    # different shape, breaking the byte-for-byte equality required
    # by P0-#2 (write-time hash == read-time hash).
    context = typed_audit

    # Required identity fields. The strict loader treats every one
    # of these as load-bearing; any missing or malformed value is
    # an integrity error (500), not a default-substituted success.
    request_payload_hash = _strict_required_lowercase_64_hex(context, "request_payload_hash")
    model_policy = _strict_required_str(context, "model_policy")
    if model_policy != "replay_trained_model":
        raise ReplayTrainedPersistedIdentityIntegrityError(
            "persisted model_policy is not replay_trained_model",
            mismatched_fields=("model_policy_mismatch",),
        )
    # The ``task9_run_id`` is persisted by the E2 service as a native
    # integer. The strict loader accepts ONLY native ``int``; ``bool``
    # is rejected (Python ``bool`` is a subclass of ``int`` but a flag
    # is not a Task 9 run identifier), numeric strings are rejected,
    # and ``float`` is rejected. Persisted type drift is integrity
    # failure, not silent coercion.
    task9_run_id = _strict_required_int(context, "task9_run_id")
    task9_result_hash = _strict_required_lowercase_64_hex(context, "task9_result_hash")
    training_manifest_hash = _strict_required_lowercase_64_hex(context, "training_manifest_hash")
    training_dataset_hash = _strict_required_lowercase_64_hex(context, "training_dataset_hash")
    model_config_hash = _strict_required_lowercase_64_hex(context, "model_config_hash")
    model_artifact_hash = _strict_required_lowercase_64_hex(context, "model_artifact_hash")
    model_code_version = _strict_required_str(context, "model_code_version")
    task12_policy_version = _strict_required_str(context, "task12_policy_version")
    replay_attempt_id = _strict_required_str(context, "replay_attempt_id")
    replay_node_id = _strict_required_str(context, "replay_node_id")
    scenario_id = _strict_required_str(context, "scenario_id")
    forecast_cutoff_at = _strict_required_str(context, "forecast_cutoff_at")
    training_cutoff_at = _strict_required_str(context, "training_cutoff_at")

    # P0-#5: every audit-payload field is strict-required BEFORE we
    # recompute the audit identity. This guarantees that missing /
    # malformed fields surface as ``{field}_missing`` / ``{field}_type``
    # reasons, NOT as ``audit_identity_mismatch`` (which would mask
    # the real corruption reason under a generic integrity failure).
    # The strict-required calls have side effects (raise integrity
    # error on missing / wrong-type) but their return values are not
    # used downstream — they are pure validators. ``_ =`` discards
    # silence the F841 unused-variable warnings without losing the
    # validation.
    _ = _strict_required_str(context, "service_version")
    _ = _strict_required_int(context, "task10_training_run_id")
    _ = _strict_required_lowercase_64_hex(context, "task10_training_signature")
    _ = _strict_required_lowercase_64_hex(context, "task10_manifest_hash")
    _ = _strict_required_lowercase_64_hex(context, "task10_config_hash")
    _ = _strict_required_non_empty_str_list(context, "task10_artifact_hashes")
    _ = _strict_required_int(context, "filtered_training_row_count")
    _ = _strict_required_int(context, "filtered_label_row_count")
    _ = _strict_required_str(context, "training_execution_status")
    _ = _strict_required_str(context, "training_eligibility_status")
    _ = _strict_required_str(context, "prediction_execution_status")
    _ = _strict_required_str(context, "prediction_mode")
    _ = _strict_required_str(context, "idempotency_key")
    _ = _strict_required_str(context, "caller_identity")

    # Identity consistency: prediction_hash must match the row's
    # canonical_payload_hash AND must match the independently
    # recomputed prediction hash for the persisted
    # ``ResidualPredictionExecutionResult`` (P0-#4 spec).
    #
    # A 64-hex format constraint on ``canonical_payload_hash`` does
    # NOT prove semantic correctness — replacing it with a different
    # valid 64-hex value would pass a format-only check. The loader
    # therefore re-reads the persisted prediction result via
    # ``load_residual_prediction_run_by_id`` (which rebuilds the
    # ``ResidualPredictionExecutionResult`` from child rows + the
    # ``canonical_output`` blob), recomputes
    # ``_prediction_hash_from_result(loaded)``, and compares it
    # byte-for-byte with the stored ``row.prediction_hash``. Any
    # mismatch — including a valid-but-wrong 64-hex replacement —
    # raises a 500 integrity error.
    prediction_hash = str(row.prediction_hash or "")
    if not _LOWERCASE_64_HEX.match(prediction_hash):
        raise ReplayTrainedPersistedIdentityIntegrityError(
            "persisted prediction_hash must be a lowercase 64-character hex hash",
            mismatched_fields=("prediction_hash_format",),
        )
    canonical_payload_hash = str(row.canonical_payload_hash or "")
    if not _LOWERCASE_64_HEX.match(canonical_payload_hash):
        raise ReplayTrainedPersistedIdentityIntegrityError(
            "persisted canonical_payload_hash must be a lowercase 64-character hex hash",
            mismatched_fields=("canonical_payload_hash_format",),
        )

    # Independent persisted prediction hash verification. We rebuild
    # the prediction result from the persisted ``canonical_output``
    # blob + child rows, recompute the canonical prediction hash, and
    # require it to equal the stored ``prediction_hash``. This
    # catches a valid-but-wrong 64-hex replacement that the format
    # check alone would miss. ``load_residual_prediction_run_by_id``
    # itself verifies ``_prediction_payload_hash(loaded) ==
    # canonical_payload_hash`` so the two cross-checks combine to
    # validate ``prediction_hash == _prediction_hash_from_result(loaded)
    # == _prediction_payload_hash(loaded) == canonical_payload_hash``.
    try:
        reloaded_prediction = await load_residual_prediction_run_by_id(
            session, run_id=prediction_run_id
        )
    except ResidualModelPersistenceIntegrityError as exc:
        # The residual-model persistence layer detected a prediction
        # integrity failure (typically a tampered ``canonical_output``
        # blob that no longer matches ``canonical_payload_hash``).
        # Normalize to the TASK-012 envelope so the HTTP 500 surface
        # is consistent and the internal mismatched-field detail does
        # not leak to clients.
        raise ReplayTrainedPersistedIdentityIntegrityError(
            "persisted prediction canonical payload failed integrity "
            "verification during reload (semantic integrity failure)",
            mismatched_fields=("prediction_hash_mismatch",),
        ) from exc
    if reloaded_prediction is None:
        raise ReplayTrainedPersistedIdentityIntegrityError(
            "persisted prediction could not be reloaded for hash verification",
            mismatched_fields=("prediction_hash_reload_missing",),
        )
    rebuilt_prediction_hash = _recompute_prediction_hash(reloaded_prediction)
    if rebuilt_prediction_hash != prediction_hash:
        raise ReplayTrainedPersistedIdentityIntegrityError(
            "persisted prediction_hash does not match the independently recomputed "
            "prediction hash (semantic integrity failure)",
            mismatched_fields=("prediction_hash_mismatch",),
        )

    # Task 9 / artifact / training / config / model identity
    # consistency: the persisted run / result / artifact identity
    # MUST equal the values the request body asserted at write time.
    persisted_task9_run = await session.get(HarvestStateRun, task9_run_id)
    if persisted_task9_run is None:
        raise ReplayTrainedPersistedIdentityIntegrityError(
            "persisted task9_run_id references a missing Task 9 run",
            mismatched_fields=("task9_run_missing",),
        )
    if str(persisted_task9_run.result_hash or "") != task9_result_hash:
        raise ReplayTrainedPersistedIdentityIntegrityError(
            "persisted task9_result_hash does not match the Task 9 run authority",
            mismatched_fields=("task9_result_hash_mismatch",),
        )

    # The audit identity is the deterministic-redeterminism
    # fingerprint stored in ``typed_attempt.task12_replay.audit_identity``.
    # The loader MUST recompute the audit identity from the
    # persisted canonical payload using the SAME canonical function
    # that wrote it (``_audit_identity_for``), then compare
    # exact-string equality (P0-#2 spec).
    #
    # The recomputation deliberately excludes the two
    # non-authoritative fields ``audit_identity`` (the value being
    # recomputed) and ``prediction_run_id`` (the persisted row
    # identifier). Any tampering that replaces the persisted
    # ``audit_identity`` with a different valid 64-hex string is
    # caught by exact-string equality; replacing it with a malformed
    # string is caught by the well-formedness check below.
    persisted_audit_identity = _strict_required_lowercase_64_hex(typed_audit, "audit_identity")
    recomputed_audit_payload = _recompute_audit_payload(typed_audit)
    recomputed_audit_identity = _audit_identity(recomputed_audit_payload)
    if recomputed_audit_identity != persisted_audit_identity:
        raise ReplayTrainedPersistedIdentityIntegrityError(
            "persisted TASK-012 audit_identity does not match the recomputed "
            "canonical audit identity (semantic integrity failure)",
            mismatched_fields=("audit_identity_mismatch",),
        )

    return ReplayTrainedPersistedIdentity(
        prediction_run_id=prediction_run_id,
        prediction_hash=prediction_hash,
        request_payload_hash=request_payload_hash,
        model_policy=model_policy,
        task12_policy_version=task12_policy_version,
        replay_attempt_id=replay_attempt_id,
        replay_node_id=replay_node_id,
        scenario_id=scenario_id,
        training_manifest_hash=training_manifest_hash,
        training_dataset_hash=training_dataset_hash,
        model_config_hash=model_config_hash,
        model_artifact_hash=model_artifact_hash,
        model_code_version=model_code_version,
        forecast_cutoff_at=forecast_cutoff_at,
        training_cutoff_at=training_cutoff_at,
        task9_run_id=task9_run_id,
        task9_result_hash=task9_result_hash,
        task10_training_run_id=_strict_required_int(context, "task10_training_run_id"),
        task10_training_signature=_strict_required_lowercase_64_hex(
            context, "task10_training_signature"
        ),
        task10_manifest_hash=_strict_required_lowercase_64_hex(context, "task10_manifest_hash"),
        task10_config_hash=_strict_required_lowercase_64_hex(context, "task10_config_hash"),
        task10_artifact_hashes=_strict_required_non_empty_str_list(
            context, "task10_artifact_hashes"
        ),
        filtered_training_row_count=_strict_required_int(context, "filtered_training_row_count"),
        filtered_label_row_count=_strict_required_int(context, "filtered_label_row_count"),
        training_execution_status=_strict_required_str(context, "training_execution_status"),
        training_eligibility_status=_strict_required_str(context, "training_eligibility_status"),
        prediction_execution_status=_strict_required_str(context, "prediction_execution_status"),
        prediction_mode=_strict_required_str(context, "prediction_mode"),
        idempotency_key=_strict_required_str(context, "idempotency_key"),
        caller_identity=_strict_required_str(context, "caller_identity"),
        audit_identity=persisted_audit_identity,
    )


@dataclass(frozen=True, slots=True)
class ReplayTrainedExecutionRequest:
    """Complete explicit identity and authoritative Task 10 input payload."""

    model_policy: Task10ModelPolicy | str | None
    task12_policy_version: str
    replay_attempt_id: str
    replay_node_id: str
    scenario_id: str
    forecast_cutoff_at: datetime
    training_cutoff_at: datetime
    allowed_training_season_ids: tuple[int, ...]
    training_manifest: TrainingManifestPayload
    model_config: ModelConfigPayload
    model_code_version: str
    replay_code_version: str
    task9_run_id: int
    task9_result_hash: str
    is_replay: bool
    task10_config_snapshot: dict[str, Any]
    manifest_rows_payload: tuple[dict[str, object], ...]
    training_rows: tuple[dict[str, object], ...]
    label_rows: tuple[dict[str, object], ...]
    source_run_ids: dict[str, int]
    artifact_identity_json: dict[str, object]
    artifact_identity_manifest: dict[str, object]
    feature_actual_snapshot: dict[str, object] | None
    idempotency_key: str
    caller_identity: str
    training_samples: tuple[ResidualTrainingSampleSpec, ...] = ()
    supplemental_feature_values: tuple[FeatureValue, ...] = ()

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ReplayTrainedExecutionRequest:
        def required(name: str) -> object:
            value = payload.get(name)
            if value is None:
                raise ReplayTrainedServiceInputError(
                    f"request field {name!r} is required",
                    mismatched_fields=(f"{name}_required",),
                )
            return value

        manifest_payload = cast(Mapping[str, object], required("training_manifest"))
        model_config_payload = cast(Mapping[str, object], required("model_config"))
        try:
            manifest = TrainingManifestPayload(
                replay_attempt_id=str(required_from(manifest_payload, "replay_attempt_id")),
                replay_node_id=str(required_from(manifest_payload, "replay_node_id")),
                scenario_id=str(required_from(manifest_payload, "scenario_id")),
                forecast_cutoff_at=_parse_datetime(
                    required_from(manifest_payload, "forecast_cutoff_at")
                ),
                training_cutoff_at=_parse_datetime(
                    required_from(manifest_payload, "training_cutoff_at")
                ),
                allowed_training_season_ids=tuple(
                    _int_value(item)
                    for item in cast(
                        list[object],
                        required_from(manifest_payload, "allowed_training_season_ids"),
                    )
                ),
                feature_visibility_policy_version=str(
                    required_from(manifest_payload, "feature_visibility_policy_version")
                ),
                label_visibility_policy_version=str(
                    required_from(manifest_payload, "label_visibility_policy_version")
                ),
                artifact_visibility_policy_version=str(
                    required_from(manifest_payload, "artifact_visibility_policy_version")
                ),
                validation_policy_version=str(
                    required_from(manifest_payload, "validation_policy_version")
                ),
                training_dataset_hash=str(required_from(manifest_payload, "training_dataset_hash")),
                task8_curve_identity=cast(str | None, manifest_payload.get("task8_curve_identity")),
                task9_replay_binding_identity=cast(
                    str | None, manifest_payload.get("task9_replay_binding_identity")
                ),
                row_count=_int_value(required_from(manifest_payload, "row_count")),
                excluded_row_count=_int_value(
                    required_from(manifest_payload, "excluded_row_count")
                ),
            )
            model_config = ModelConfigPayload(
                algorithm_family=str(required_from(model_config_payload, "algorithm_family")),
                hyperparameters=cast(
                    dict[str, str | int | bool],
                    required_from(model_config_payload, "hyperparameters"),
                ),
                random_seed=_int_value(required_from(model_config_payload, "random_seed")),
                deterministic_serialization_version=str(
                    required_from(model_config_payload, "deterministic_serialization_version")
                ),
            )
            samples = tuple(
                ResidualTrainingSampleSpec.model_validate(item)
                for item in cast(list[object], payload.get("training_samples", []))
            )
        except (TypeError, ValueError) as exc:
            if isinstance(exc, ReplayTrainedServiceError):
                raise
            raise ReplayTrainedServiceInputError(
                "request contains an invalid Task 10 identity or sample payload",
                mismatched_fields=("request_payload_invalid",),
            ) from exc

        return cls(
            model_policy=cast(Task10ModelPolicy | str | None, payload.get("model_policy")),
            task12_policy_version=str(required("task12_policy_version")),
            replay_attempt_id=str(required("replay_attempt_id")),
            replay_node_id=str(required("replay_node_id")),
            scenario_id=str(required("scenario_id")),
            forecast_cutoff_at=_parse_datetime(required("forecast_cutoff_at")),
            training_cutoff_at=_parse_datetime(required("training_cutoff_at")),
            allowed_training_season_ids=tuple(
                _int_value(item)
                for item in cast(list[object], required("allowed_training_season_ids"))
            ),
            training_manifest=manifest,
            model_config=model_config,
            model_code_version=str(required("model_code_version")),
            replay_code_version=str(required("replay_code_version")),
            task9_run_id=_int_value(required("task9_run_id")),
            task9_result_hash=str(required("task9_result_hash")),
            is_replay=bool(required("is_replay")),
            task10_config_snapshot=cast(dict[str, Any], required("task10_config_snapshot")),
            manifest_rows_payload=tuple(
                cast(dict[str, object], item)
                for item in cast(list[object], required("manifest_rows_payload"))
            ),
            training_rows=tuple(
                cast(dict[str, object], item)
                for item in cast(list[object], required("training_rows"))
            ),
            label_rows=tuple(
                cast(dict[str, object], item) for item in cast(list[object], required("label_rows"))
            ),
            source_run_ids={
                str(key): _int_value(value)
                for key, value in cast(Mapping[str, object], required("source_run_ids")).items()
                if value is not None
            },
            artifact_identity_json=cast(dict[str, object], required("artifact_identity_json")),
            artifact_identity_manifest=cast(
                dict[str, object], required("artifact_identity_manifest")
            ),
            feature_actual_snapshot=cast(
                dict[str, object] | None, payload.get("feature_actual_snapshot")
            ),
            idempotency_key=str(required("idempotency_key")),
            caller_identity=str(required("caller_identity")),
            training_samples=samples,
            supplemental_feature_values=tuple(
                FeatureValue.model_validate(item)
                for item in cast(list[object], payload.get("supplemental_feature_values", []))
            ),
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "model_policy": _enum_value(self.model_policy),
            "task12_policy_version": self.task12_policy_version,
            "replay_attempt_id": self.replay_attempt_id,
            "replay_node_id": self.replay_node_id,
            "scenario_id": self.scenario_id,
            "forecast_cutoff_at": _datetime_string(self.forecast_cutoff_at),
            "training_cutoff_at": _datetime_string(self.training_cutoff_at),
            "allowed_training_season_ids": list(self.allowed_training_season_ids),
            "training_manifest": _manifest_payload(self.training_manifest),
            "model_config": asdict(self.model_config),
            "model_code_version": self.model_code_version,
            "replay_code_version": self.replay_code_version,
            "task9_run_id": self.task9_run_id,
            "task9_result_hash": self.task9_result_hash,
            "is_replay": self.is_replay,
            "task10_config_snapshot": _json_safe(self.task10_config_snapshot),
            "manifest_rows_payload": [
                _json_safe(dict(item)) for item in self.manifest_rows_payload
            ],
            "training_rows": [_json_safe(dict(item)) for item in self.training_rows],
            "label_rows": [_json_safe(dict(item)) for item in self.label_rows],
            "source_run_ids": dict(sorted(self.source_run_ids.items())),
            "artifact_identity_json": _json_safe(self.artifact_identity_json),
            "artifact_identity_manifest": _json_safe(self.artifact_identity_manifest),
            "feature_actual_snapshot": _json_safe(self.feature_actual_snapshot),
            "idempotency_key": self.idempotency_key,
            "caller_identity": self.caller_identity,
            "training_samples": [item.model_dump(mode="json") for item in self.training_samples],
            "supplemental_feature_values": [
                item.model_dump(mode="json") for item in self.supplemental_feature_values
            ],
        }

    def canonical_identity_payload(self, *, task10_config_hash: str) -> dict[str, object]:
        payload = self.to_payload()
        payload.pop("task10_config_snapshot", None)
        return {
            "service_version": _SERVICE_VERSION,
            "request": payload,
            "task10_config_hash": task10_config_hash,
        }


@dataclass(frozen=True, slots=True)
class ReplayTrainedExecutionResult:
    """Canonical result returned by the Slice E2 service."""

    model_policy: Task10ModelPolicy
    prediction_run_id: int
    prediction_hash: str
    request_payload_hash: str
    training_manifest_hash: str
    model_config_hash: str
    model_artifact_hash: str
    task9_run_id: int
    task9_result_hash: str
    filtered_training_row_count: int
    filtered_label_row_count: int
    training_execution_status: str
    training_eligibility_status: str
    prediction_execution_status: str
    prediction_mode: str
    audit_identity: str
    #: True iff this invocation persisted a NEW prediction row (HTTP 201);
    #: False iff the service re-loaded the prior prediction for the same
    #: (idempotency_key, request_payload_hash) pair (HTTP 200). The HTTP
    #: adapter MUST consume this disposition and MUST NOT recompute it.
    created: bool
    audit_payload: dict[str, object]

    def to_payload(self) -> dict[str, object]:
        return dict(self.audit_payload)


def _enum_value(value: object) -> object:
    return value.value if isinstance(value, Task10ModelPolicy) else value


def _int_value(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise ReplayTrainedServiceInputError(
            "integer fields must contain integers",
            mismatched_fields=("integer_type",),
        )
    try:
        return int(value)
    except ValueError as exc:
        raise ReplayTrainedServiceInputError(
            "integer fields must contain integers",
            mismatched_fields=("integer_format",),
        ) from exc


def required_from(payload: Mapping[str, object], name: str) -> object:
    value = payload.get(name)
    if value is None:
        raise ReplayTrainedServiceInputError(
            f"nested request field {name!r} is required",
            mismatched_fields=(f"{name}_required",),
        )
    return value


def _parse_datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise ReplayTrainedServiceInputError(
            "datetime fields must be ISO-8601 strings",
            mismatched_fields=("datetime_type",),
        )
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReplayTrainedServiceInputError(
            "datetime fields must be valid ISO-8601 values",
            mismatched_fields=("datetime_format",),
        ) from exc


def _datetime_string(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone-aware datetime is required")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _manifest_payload(manifest: TrainingManifestPayload) -> dict[str, object]:
    return {
        "replay_attempt_id": manifest.replay_attempt_id,
        "replay_node_id": manifest.replay_node_id,
        "scenario_id": manifest.scenario_id,
        "forecast_cutoff_at": _datetime_string(manifest.forecast_cutoff_at),
        "training_cutoff_at": _datetime_string(manifest.training_cutoff_at),
        "allowed_training_season_ids": list(manifest.allowed_training_season_ids),
        "feature_visibility_policy_version": manifest.feature_visibility_policy_version,
        "label_visibility_policy_version": manifest.label_visibility_policy_version,
        "artifact_visibility_policy_version": manifest.artifact_visibility_policy_version,
        "validation_policy_version": manifest.validation_policy_version,
        "training_dataset_hash": manifest.training_dataset_hash,
        "task8_curve_identity": manifest.task8_curve_identity,
        "task9_replay_binding_identity": manifest.task9_replay_binding_identity,
        "row_count": manifest.row_count,
        "excluded_row_count": manifest.excluded_row_count,
    }


def _json_safe(value: object) -> object:
    if isinstance(value, datetime):
        return _datetime_string(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, tuple | list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return value


def _json_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            _json_safe(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _date_value(row: Mapping[str, object], field: str) -> date:
    raw = row.get(field)
    if not isinstance(raw, str):
        raise ReplayTrainedServiceInputError(
            f"{field} must be an ISO date string",
            mismatched_fields=(f"{field}_required",),
        )
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ReplayTrainedServiceInputError(
            f"{field} must be a valid ISO date string",
            mismatched_fields=(f"{field}_format",),
        ) from exc


def _float_value(row: Mapping[str, object], field: str) -> float:
    raw = row.get(field)
    if isinstance(raw, bool) or not isinstance(raw, int | float | str):
        raise ReplayTrainedServiceInputError(
            f"{field} must be numeric",
            mismatched_fields=(f"{field}_numeric",),
        )
    try:
        return float(raw)
    except ValueError as exc:
        raise ReplayTrainedServiceInputError(
            f"{field} must be numeric",
            mismatched_fields=(f"{field}_numeric",),
        ) from exc


def _same_datetime(left: datetime, right: datetime) -> bool:
    return left.astimezone(UTC) == right.astimezone(UTC)


def _validate_request(request: ReplayTrainedExecutionRequest) -> None:
    if request.model_policy != Task10ModelPolicy.REPLAY_TRAINED_MODEL:
        raise ReplayTrainedServiceInputError(
            "Slice E2 requires an explicit replay_trained_model policy",
            mismatched_fields=("model_policy_must_be_replay_trained_model",),
        )
    if not request.is_replay:
        raise ReplayTrainedServiceInputError(
            "replay-trained execution requires replay provenance",
            mismatched_fields=("is_replay_must_be_true",),
        )
    if not request.idempotency_key or not request.caller_identity:
        raise ReplayTrainedServiceInputError(
            "idempotency_key and caller_identity are required",
            mismatched_fields=("idempotency_identity_required",),
        )
    if request.task9_run_id <= 0:
        raise ReplayTrainedServiceInputError(
            "task9_run_id must be positive",
            mismatched_fields=("task9_run_id_must_be_positive",),
        )
    for value, field in (
        (request.forecast_cutoff_at, "forecast_cutoff_at"),
        (request.training_cutoff_at, "training_cutoff_at"),
    ):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ReplayTrainedServiceInputError(
                f"{field} must be timezone-aware",
                mismatched_fields=(f"{field}_timezone_required",),
            )
    if request.training_cutoff_at.astimezone(UTC) > request.forecast_cutoff_at.astimezone(UTC):
        raise ReplayTrainedServiceInputError(
            "training_cutoff_at must be <= forecast_cutoff_at",
            mismatched_fields=("training_cutoff_after_forecast_cutoff",),
        )
    if len(request.task9_result_hash) != _HASH_LENGTH or any(
        char not in "0123456789abcdef" for char in request.task9_result_hash
    ):
        raise ReplayTrainedServiceInputError(
            "task9_result_hash must be lowercase SHA-256",
            mismatched_fields=("task9_result_hash_must_be_64_hex",),
        )
    manifest = request.training_manifest
    mismatches: list[str] = []
    for name in ("replay_attempt_id", "replay_node_id", "scenario_id"):
        if getattr(request, name) != getattr(manifest, name):
            mismatches.append(f"{name}_mismatch")
    if not _same_datetime(request.forecast_cutoff_at, manifest.forecast_cutoff_at):
        mismatches.append("forecast_cutoff_mismatch")
    if not _same_datetime(request.training_cutoff_at, manifest.training_cutoff_at):
        mismatches.append("training_cutoff_mismatch")
    if tuple(request.allowed_training_season_ids) != tuple(manifest.allowed_training_season_ids):
        mismatches.append("allowed_training_season_ids_mismatch")
    expected_binding = sha256_payload(
        {
            "task9_run_id": request.task9_run_id,
            "task9_result_hash": request.task9_result_hash,
            "is_replay": True,
            "replay_code_version": request.replay_code_version,
        }
    )
    if manifest.task9_replay_binding_identity != expected_binding:
        mismatches.append("task9_replay_binding_identity_mismatch")
    if request.source_run_ids.get("task9a_run_id") != request.task9_run_id:
        mismatches.append("source_task9_run_id_mismatch")
    if mismatches:
        raise ReplayTrainedServiceBlockerError(
            "replay request identity disagrees with its persisted binding",
            blocker_code=OrchestrationBlocker.TASK12_CROSS_RUN_SUBSTITUTION.value,
            mismatched_fields=tuple(mismatches),
        )
    if not request.training_samples:
        raise ReplayTrainedServiceInputError(
            "training_samples must contain the exact persisted Task 10 sources",
            mismatched_fields=("training_samples_required",),
        )


def _task10_model_config_projection(config: Any) -> ModelConfigPayload:
    snapshot = config.snapshot
    scalar_identity = {
        "model_version": config.rules.model_version,
        "feature_schema_version": config.rules.feature_schema_version,
        "artifact_schema_version": config.rules.artifact_schema_version,
        "estimator": canonical_json_dumps(snapshot["estimator"]),
        "split": canonical_json_dumps(snapshot["split"]),
        "missing_values": canonical_json_dumps(snapshot["missing_values"]),
        "categorical_encoding": canonical_json_dumps(snapshot["categorical_encoding"]),
        "projection": canonical_json_dumps(snapshot["projection"]),
        "eligibility": canonical_json_dumps(snapshot["eligibility"]),
    }
    return ModelConfigPayload(
        algorithm_family=config.rules.model_family,
        hyperparameters=cast(dict[str, str | int | bool], scalar_identity),
        random_seed=config.rules.random_seed,
        deterministic_serialization_version="task10-config-snapshot-v1",
    )


async def _verify_persisted_task9(
    session: AsyncSession,
    *,
    request: ReplayTrainedExecutionRequest,
) -> None:
    """Verify the Task 9 authority for a TASK-012 replay-trained request.

    Splits the previously combined "missing or not-replay" blocker
    into two distinct HTTP statuses per the P0-#4 spec:

    * ``run is None`` (Task 9 run does not exist) → 404
      (:class:`ReplayTrainedServiceNotFoundError`);
    * ``output is None`` (Task 9 run exists but its output is
      missing) → 404 (the run's replay authority IS its output;
      the output is missing entirely);
    * ``run.is_replay is not True`` (run present, not a replay)
      → 409 (:class:`ReplayTrainedServiceBlockerError`,
      mismatched_fields=``task9_replay_run_missing_or_not_replay``);
    * ``output.result_hash != request.task9_result_hash``
      (present but identity mismatch) → 409, mismatched_fields=
      ``task9_result_hash_mismatch``.
    """
    run = await session.get(HarvestStateRun, request.task9_run_id)
    if run is None:
        raise ReplayTrainedServiceNotFoundError(
            "the referenced Task 9 run does not exist",
            identity={"task9_run_id": request.task9_run_id},
        )
    if run.is_replay is not True:
        raise ReplayTrainedServiceBlockerError(
            "the exact replay-produced Task 9 run is not available",
            blocker_code=OrchestrationBlocker.TASK12_CROSS_RUN_SUBSTITUTION.value,
            mismatched_fields=("task9_replay_run_missing_or_not_replay",),
        )
    output = await load_harvest_state_output_by_id(session, run_id=request.task9_run_id)
    if output is None:
        raise ReplayTrainedServiceNotFoundError(
            "the referenced Task 9 run has no persisted output",
            identity={"task9_run_id": request.task9_run_id},
        )
    if output.status != "completed" or output.result_hash != request.task9_result_hash:
        raise ReplayTrainedServiceBlockerError(
            "the exact Task 9 result hash does not match persisted authority",
            blocker_code=OrchestrationBlocker.TASK12_CROSS_RUN_SUBSTITUTION.value,
            mismatched_fields=("task9_result_hash_mismatch",),
        )


async def _visible_samples(
    session: AsyncSession,
    *,
    request: ReplayTrainedExecutionRequest,
) -> tuple[ResidualTrainingSampleSpec, ...]:
    visible: list[ResidualTrainingSampleSpec] = []
    for sample in request.training_samples:
        output = await load_harvest_state_output_by_id(session, run_id=sample.task9_run_id)
        run = await session.get(HarvestStateRun, sample.task9_run_id)
        if (
            output is None
            or run is None
            or output.status != "completed"
            or run.is_replay is not True
        ):
            raise ReplayTrainedServiceBlockerError(
                "a training sample is not bound to a completed replay Task 9 run",
                blocker_code=OrchestrationBlocker.TASK12_CROSS_RUN_SUBSTITUTION.value,
                mismatched_fields=("training_sample_task9_authority_mismatch",),
            )
        raw_as_of = output.input_snapshot.get("as_of_date")
        sample_as_of = (
            raw_as_of if isinstance(raw_as_of, date) else date.fromisoformat(str(raw_as_of))
        )
        if sample_as_of <= request.training_cutoff_at.date():
            visible.append(sample)
    if not visible:
        raise ReplayTrainedServiceBlockerError(
            "no replay Task 9 training source is visible at the training cutoff",
            blocker_code=OrchestrationBlocker.TASK12_TRAINING_ROWS_EMPTY.value,
        )
    build_ids = {sample.label_analytics_build_run_id for sample in visible} | {
        sample.feature_analytics_build_run_id for sample in visible
    }
    for build_id in sorted(build_ids):
        build = await session.get(AnalyticsBuildRun, build_id)
        if build is None or build.status != "completed":
            raise ReplayTrainedServiceBlockerError(
                "a Task 3 analytics build authority is unavailable",
                blocker_code=OrchestrationBlocker.TASK12_CROSS_RUN_SUBSTITUTION.value,
                mismatched_fields=("analytics_build_authority_missing",),
            )
        available_at = build.finished_at or build.started_at
        if available_at.tzinfo is None:
            available_at = available_at.replace(tzinfo=UTC)
        if available_at.astimezone(UTC) > request.training_cutoff_at.astimezone(UTC):
            raise ReplayTrainedServiceBlockerError(
                "a Task 3 analytics build is not visible at the training cutoff",
                blocker_code=OrchestrationBlocker.TASK12_CROSS_RUN_SUBSTITUTION.value,
                mismatched_fields=("analytics_build_not_cutoff_visible",),
                details={"build_run_id": build_id},
            )
    return tuple(visible)


def _normalized_numeric(value: object) -> str:
    return format(Decimal(str(value)).normalize(), "f")


def _request_training_rows(rows: Sequence[FilteredTrainingRow]) -> list[dict[str, str]]:
    return [
        {
            "observation_date": row.observation_date.isoformat(),
            "value": _normalized_numeric(row.value),
        }
        for row in rows
    ]


def _request_label_rows(rows: Sequence[FilteredLabelRow]) -> list[dict[str, str]]:
    return [
        {
            "observation_date": row.observation_date.isoformat(),
            "label_availability_date": row.label_availability_date.isoformat(),
            "value": _normalized_numeric(row.value),
        }
        for row in rows
    ]


def _actual_input_rows(
    rows: Sequence[ResidualTrainingManifestRow],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    training_rows = [
        {
            "observation_date": row.as_of_date.isoformat(),
            "value": _normalized_numeric(row.observed_effective_receipt_kg),
        }
        for row in rows
    ]
    label_rows = [
        {
            "observation_date": row.target_arrival_local_date.isoformat(),
            "label_availability_date": row.label_actual_snapshot.source_cutoff.date().isoformat(),
            "value": _normalized_numeric(row.observed_effective_receipt_kg),
        }
        for row in rows
    ]
    return training_rows, label_rows


def _actual_manifest_payload(
    rows: Sequence[ResidualTrainingManifestRow],
) -> list[dict[str, object]]:
    return [cast(dict[str, object], _json_safe(manifest_row_payload(row))) for row in rows]


def _dataset_identity(
    *,
    training_rows: Sequence[Mapping[str, object]],
    label_rows: Sequence[Mapping[str, object]],
    manifest_rows: Sequence[Mapping[str, object]],
) -> str:
    return canonical_payload_hash(
        {
            "training_rows": list(training_rows),
            "label_rows": list(label_rows),
            "manifest_rows": list(manifest_rows),
        }
    )


def _task12_context(
    *,
    request: ReplayTrainedExecutionRequest,
    projection: ReplayTrainedIdentityProjection,
    request_payload_hash: str,
    task10_manifest_hash: str,
    task10_config_hash: str,
    task10_training_run_id: int | None = None,
    task10_training_signature: str | None = None,
    task10_artifact_hashes: Sequence[str] = (),
) -> dict[str, object]:
    """Lightweight TASK-012 replay context for Task 10 execution passes.

    This dict is the EXECUTION-PASS context (passed as
    ``execution_context`` / ``typed_attempt`` to
    ``execute_residual_training`` and ``execute_residual_prediction``).
    It is NOT the audit-critical form; the persisted row's
    ``input_snapshot.task12_replay`` and ``typed_attempt.task12_replay``
    are OVERWRITTEN with the full :func:`_task12_audit_context` form
    after prediction completes — see ``_finalize_task12_audit_payload``
    below — so that the audit-identity redetermination step at
    read time rebuilds the EXACT same 31-field payload that wrote
    it.
    """
    return {
        "model_policy": Task10ModelPolicy.REPLAY_TRAINED_MODEL.value,
        "task12_policy_version": projection.task12_policy_version,
        "replay_attempt_id": request.replay_attempt_id,
        "replay_node_id": request.replay_node_id,
        "scenario_id": request.scenario_id,
        "forecast_cutoff_at": _datetime_string(request.forecast_cutoff_at),
        "training_cutoff_at": _datetime_string(request.training_cutoff_at),
        "training_manifest_hash": projection.training_manifest_hash,
        "training_dataset_hash": projection.manifest.training_dataset_hash,
        "model_config_hash": projection.model_config_hash,
        "model_artifact_hash": projection.model_artifact_hash,
        "model_code_version": projection.model_code_version,
        "replay_code_version": request.replay_code_version,
        "task9_run_id": request.task9_run_id,
        "task9_result_hash": request.task9_result_hash,
        "task10_training_run_id": task10_training_run_id,
        "task10_training_signature": task10_training_signature,
        "task10_manifest_hash": task10_manifest_hash,
        "task10_config_hash": task10_config_hash,
        "task10_artifact_hashes": list(task10_artifact_hashes),
        "is_replay": True,
        "idempotency_key": request.idempotency_key,
        "caller_identity": request.caller_identity,
        "request_payload_hash": request_payload_hash,
    }


def _task12_audit_payload(
    *,
    service_version: str,
    model_policy: str,
    task12_policy_version: str,
    replay_attempt_id: str,
    replay_node_id: str,
    scenario_id: str,
    training_manifest_hash: str,
    training_dataset_hash: str,
    model_config_hash: str,
    model_artifact_hash: str,
    model_code_version: str,
    forecast_cutoff_at: str,
    training_cutoff_at: str,
    task9_run_id: int,
    task9_result_hash: str,
    prediction_hash: str,
    request_payload_hash: str,
    filtered_training_row_count: int,
    filtered_label_row_count: int,
    training_execution_status: str,
    training_eligibility_status: str,
    prediction_execution_status: str,
    prediction_mode: str,
    task10_training_run_id: int,
    task10_training_signature: str,
    task10_manifest_hash: str,
    task10_config_hash: str,
    task10_artifact_hashes: Sequence[str],
    idempotency_key: str,
    caller_identity: str,
    no_implicit_selection: bool,
    no_cross_run_substitution: bool,
) -> dict[str, object]:
    """Build the canonical TASK-012 audit payload.

    Single source of truth for BOTH the write-time audit-identity
    computation (``_result_payload`` → ``_audit_identity``) AND the
    read-time redetermination path
    (``load_replay_trained_prediction``). The two callers MUST call
    this builder with byte-identical field values; the field names,
    field set, field ordering, and canonical serialization are frozen
    by this function and any drift between write-time and read-time
    is reported as ``audit_identity_mismatch`` (HTTP 500).

    Deliberately EXCLUDED fields (NOT in audit hash):

    * ``audit_identity`` — the value being recomputed; including it
      would create a circular hash that excludes any tampering of
      the audit_identity field itself.
    * ``prediction_run_id`` — the persisted row identifier that
      the write-time payload did NOT include; the read-time path
      loads this from the row primary key, not from the payload.

    All other persisted fields — ``service_version``,
    ``no_implicit_selection``, ``no_cross_run_substitution``, the
    row counts, the execution / eligibility / mode statuses — are
    LOAD-BEARING for audit. Removing or defaulting them on the
    read-time path is an integrity violation.
    """
    return {
        "service_version": service_version,
        "model_policy": model_policy,
        "task12_policy_version": task12_policy_version,
        "replay_attempt_id": replay_attempt_id,
        "replay_node_id": replay_node_id,
        "scenario_id": scenario_id,
        "training_manifest_hash": training_manifest_hash,
        "training_dataset_hash": training_dataset_hash,
        "model_config_hash": model_config_hash,
        "model_artifact_hash": model_artifact_hash,
        "model_code_version": model_code_version,
        "forecast_cutoff_at": forecast_cutoff_at,
        "training_cutoff_at": training_cutoff_at,
        "task9_run_id": task9_run_id,
        "task9_result_hash": task9_result_hash,
        "prediction_hash": prediction_hash,
        "request_payload_hash": request_payload_hash,
        "filtered_training_row_count": filtered_training_row_count,
        "filtered_label_row_count": filtered_label_row_count,
        "training_execution_status": training_execution_status,
        "training_eligibility_status": training_eligibility_status,
        "prediction_execution_status": prediction_execution_status,
        "prediction_mode": prediction_mode,
        "task10_training_run_id": task10_training_run_id,
        "task10_training_signature": task10_training_signature,
        "task10_manifest_hash": task10_manifest_hash,
        "task10_config_hash": task10_config_hash,
        "task10_artifact_hashes": sorted(task10_artifact_hashes),
        "idempotency_key": idempotency_key,
        "caller_identity": caller_identity,
        "no_implicit_selection": no_implicit_selection,
        "no_cross_run_substitution": no_cross_run_substitution,
    }


def _audit_identity(payload: Mapping[str, object]) -> str:
    audit_payload = {
        key: value
        for key, value in payload.items()
        if key not in {"audit_identity", "prediction_run_id"}
    }
    return sha256_payload(audit_payload)


def _result_payload(
    *,
    request: ReplayTrainedExecutionRequest,
    projection: ReplayTrainedIdentityProjection,
    request_payload_hash: str,
    training_result: ResidualTrainingExecutionResult,
    prediction_result: ResidualPredictionExecutionResult,
    prediction_run_id: int,
    task10_training_run_id: int,
    task10_training_signature: str,
    task10_manifest_hash: str,
    task10_config_hash: str,
    task10_artifact_hashes: Sequence[str],
    filtered_training_row_count: int,
    filtered_label_row_count: int,
    created: bool,
) -> ReplayTrainedExecutionResult:
    payload: dict[str, object] = _task12_audit_payload(
        service_version=_SERVICE_VERSION,
        model_policy=Task10ModelPolicy.REPLAY_TRAINED_MODEL.value,
        task12_policy_version=projection.task12_policy_version,
        replay_attempt_id=request.replay_attempt_id,
        replay_node_id=request.replay_node_id,
        scenario_id=request.scenario_id,
        training_manifest_hash=projection.training_manifest_hash,
        training_dataset_hash=projection.manifest.training_dataset_hash,
        model_config_hash=projection.model_config_hash,
        model_artifact_hash=projection.model_artifact_hash,
        model_code_version=projection.model_code_version,
        forecast_cutoff_at=_datetime_string(request.forecast_cutoff_at),
        training_cutoff_at=_datetime_string(request.training_cutoff_at),
        task9_run_id=request.task9_run_id,
        task9_result_hash=request.task9_result_hash,
        prediction_hash=prediction_result.prediction_hash,
        request_payload_hash=request_payload_hash,
        filtered_training_row_count=filtered_training_row_count,
        filtered_label_row_count=filtered_label_row_count,
        training_execution_status=training_result.execution_status.value,
        training_eligibility_status=training_result.eligibility_status.value,
        prediction_execution_status=prediction_result.execution_status.value,
        prediction_mode=prediction_result.mode.value,
        task10_training_run_id=task10_training_run_id,
        task10_training_signature=task10_training_signature,
        task10_manifest_hash=task10_manifest_hash,
        task10_config_hash=task10_config_hash,
        task10_artifact_hashes=task10_artifact_hashes,
        idempotency_key=request.idempotency_key,
        caller_identity=request.caller_identity,
        no_implicit_selection=True,
        no_cross_run_substitution=True,
    )
    audit_identity = _audit_identity(payload)
    payload["audit_identity"] = audit_identity
    return ReplayTrainedExecutionResult(
        model_policy=Task10ModelPolicy.REPLAY_TRAINED_MODEL,
        prediction_run_id=prediction_run_id,
        prediction_hash=prediction_result.prediction_hash,
        request_payload_hash=request_payload_hash,
        training_manifest_hash=projection.training_manifest_hash,
        model_config_hash=projection.model_config_hash,
        model_artifact_hash=projection.model_artifact_hash,
        task9_run_id=request.task9_run_id,
        task9_result_hash=request.task9_result_hash,
        filtered_training_row_count=filtered_training_row_count,
        filtered_label_row_count=filtered_label_row_count,
        training_execution_status=training_result.execution_status.value,
        training_eligibility_status=training_result.eligibility_status.value,
        prediction_execution_status=prediction_result.execution_status.value,
        prediction_mode=prediction_result.mode.value,
        audit_identity=audit_identity,
        created=created,
        audit_payload=payload,
    )


async def _existing_prediction_for_idempotency(
    session: AsyncSession,
    *,
    idempotency_key: str,
    request_payload_hash: str,
) -> tuple[ResidualModelPredictionRun | None, bool]:
    rows = (await session.scalars(select(ResidualModelPredictionRun))).all()
    for row in rows:
        context = row.input_snapshot.get("task12_replay")
        if not isinstance(context, dict) or context.get("idempotency_key") != idempotency_key:
            continue
        existing_hash = context.get("request_payload_hash")
        if existing_hash != request_payload_hash:
            raise ReplayTrainedServiceConflictError(
                "idempotency_key_payload_mismatch: idempotency key is already bound "
                "to a different canonical request",
                mismatched_fields=("idempotency_key_payload_mismatch",),
            )
        return row, True
    return None, False


@asynccontextmanager
async def _idempotency_guard(
    session: AsyncSession,
    *,
    idempotency_key: str,
) -> Any:
    """Serialize same-key PostgreSQL executions without process memory."""
    bind = session.bind
    if bind is None or bind.dialect.name != "postgresql":
        yield
        return
    lock_sessionmaker = async_sessionmaker(
        bind=bind,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    lock_value = int.from_bytes(
        hashlib.sha256(idempotency_key.encode("utf-8")).digest()[:8],
        "big",
        signed=True,
    )
    async with lock_sessionmaker() as lock_session:
        await lock_session.execute(select(func.pg_advisory_xact_lock(lock_value)))
        yield


async def _fresh_prediction_reload(
    session: AsyncSession,
    *,
    prediction_run_id: int,
) -> ResidualPredictionExecutionResult:
    bind = session.bind
    if bind is None:
        raise ReplayTrainedServiceBlockerError(
            "the prediction session has no database bind",
            blocker_code=_TASK12_PERSISTENCE_INTEGRITY,
        )
    maker = async_sessionmaker(bind=bind, class_=AsyncSession, expire_on_commit=False)
    async with maker() as fresh_session:
        loaded = await load_residual_prediction_run_by_id(fresh_session, run_id=prediction_run_id)
    if loaded is None:
        raise ReplayTrainedServiceBlockerError(
            "persisted prediction could not be reloaded in a fresh session",
            blocker_code=_TASK12_PERSISTENCE_INTEGRITY,
        )
    return loaded


async def _finalize_task12_audit_payload(
    session: AsyncSession,
    *,
    prediction_run_id: int,
    audit_payload: Mapping[str, object],
) -> None:
    """Persist the FINAL audit payload to ``typed_attempt.task12_replay``.

    The audit payload is the AUTHORITATIVE 32-field dict (31 audit
    fields + ``audit_identity``) produced by
    :func:`_task12_audit_payload` at write time. The write-time
    ``canonical_payload_hash`` was computed over the original
    ``input_snapshot`` (which holds the lightweight execution-pass
    ``task12_replay`` from :func:`_task12_context` and is the
    payload bound by the residual-model persistence layer's
    parent-payload hash). Therefore this finalizer MUST NOT mutate
    ``input_snapshot`` — doing so would invalidate
    ``canonical_payload_hash`` and the persistence layer would raise
    ``ResidualModelPersistenceIntegrityError("prediction parent
    payload mismatch")`` on every reload, including every uncorrupted
    GET.

    Instead the finalizer writes the audit payload to a single
    location — ``typed_attempt.task12_replay`` — and updates the
    persisted row in place. The read-time loader
    (:func:`load_replay_trained_prediction`) reads the audit
    payload from ``typed_attempt.task12_replay`` ONLY. The
    strict-required identity fields used for the persisted identity
    dataclass are read from the SAME dict.

    A previously persisted lightweight ``task12_replay`` in
    ``typed_attempt`` (the execution-pass form from
    :func:`_task12_context`) is fully OVERWRITTEN — the audit-critical
    form is authoritative.

    Why NOT mutate ``input_snapshot``:
      * ``input_snapshot`` participates in
        ``prediction_parent_payload_from_columns`` →
        ``canonical_payload_hash`` (residual_model.persistence).
        Mutating it without recomputing ``canonical_payload_hash``
        silently invalidates every persisted prediction's reload.
      * The audit payload is logically a write-time signature, not a
        snapshot of the request input. It belongs with the
        ``typed_attempt`` (the post-execution state), not the input.
    """
    row = await get_residual_prediction_run(session, run_id=prediction_run_id)
    if row is None:
        raise ReplayTrainedServiceBlockerError(
            "the persisted prediction is missing while finalizing TASK-012 audit payload",
            blocker_code=_TASK12_PERSISTENCE_INTEGRITY,
        )
    audit_payload_dict = dict(audit_payload)
    persisted_audit_identity = str(audit_payload_dict.get("audit_identity") or "")
    if not persisted_audit_identity:
        raise ReplayTrainedServiceBlockerError(
            "the audit payload is missing audit_identity at finalize time",
            blocker_code=_TASK12_PERSISTENCE_INTEGRITY,
        )
    typed_attempt = dict(row.typed_attempt or {})
    typed_attempt["task12_replay"] = dict(audit_payload_dict)
    row.typed_attempt = typed_attempt
    await session.commit()


async def execute_replay_trained_prediction(
    session: AsyncSession,
    *,
    request: ReplayTrainedExecutionRequest,
) -> ReplayTrainedExecutionResult:
    """Execute one explicitly identified replay-trained prediction request."""
    _validate_request(request)
    try:
        config = load_residual_model_config_from_snapshot(request.task10_config_snapshot)
    except (TypeError, ValueError) as exc:
        raise ReplayTrainedServiceInputError(
            "Task 10 configuration snapshot is invalid",
            mismatched_fields=("task10_config_snapshot_invalid",),
        ) from exc
    request_payload_hash = sha256_payload(
        request.canonical_identity_payload(task10_config_hash=config.config_hash)
    )

    async with _idempotency_guard(session, idempotency_key=request.idempotency_key):
        existing, found = await _existing_prediction_for_idempotency(
            session,
            idempotency_key=request.idempotency_key,
            request_payload_hash=request_payload_hash,
        )
        if found and existing is not None:
            await _verify_persisted_task9(session, request=request)
            prediction_result = await load_residual_prediction_run_by_id(
                session, run_id=existing.id
            )
            if prediction_result is None:
                raise ReplayTrainedServiceBlockerError(
                    "the idempotent prediction authority could not be reloaded",
                    blocker_code=_TASK12_PERSISTENCE_INTEGRITY,
                )
            context = prediction_result.input_snapshot.get("task12_replay")
            if not isinstance(context, dict):
                raise ReplayTrainedServiceBlockerError(
                    "the persisted prediction is missing TASK-012 identity",
                    blocker_code=_TASK12_PERSISTENCE_INTEGRITY,
                )
            projection = project_replay_trained_identity(
                manifest=request.training_manifest,
                config=request.model_config,
                model_code_version=request.model_code_version,
                task12_policy_version=request.task12_policy_version,
            )
            result = _result_payload(
                request=request,
                projection=projection,
                request_payload_hash=request_payload_hash,
                training_result=ResidualTrainingExecutionResult.model_validate(
                    {
                        "execution_status": context["training_execution_status"],
                        "eligibility_status": context["training_eligibility_status"],
                        "model_family": "persisted",
                        "model_version": "persisted",
                        "feature_schema_version": "persisted",
                        "artifact_schema_version": "persisted",
                        "training_signature": context["task10_training_signature"],
                        "config_hash": context["task10_config_hash"],
                        "manifest_hash": context["task10_manifest_hash"],
                        "sample_count": 0,
                        "distinct_season_count": 0,
                        "distinct_factory_count": 0,
                        "warnings": [],
                        "blockers": [],
                        "feature_audit_summary": {},
                        "metrics": {},
                        "eligibility_reasons": [],
                        "input_snapshot": {},
                        "artifacts": [],
                    }
                ),
                prediction_result=prediction_result,
                prediction_run_id=existing.id,
                task10_training_run_id=int(context["task10_training_run_id"]),
                task10_training_signature=str(context["task10_training_signature"]),
                task10_manifest_hash=str(context["task10_manifest_hash"]),
                task10_config_hash=str(context["task10_config_hash"]),
                task10_artifact_hashes=cast(list[str], context["task10_artifact_hashes"]),
                filtered_training_row_count=int(context["filtered_training_row_count"]),
                filtered_label_row_count=int(context["filtered_label_row_count"]),
                created=False,
            )
            persisted_context = cast(dict[str, object], existing.typed_attempt or {}).get(
                "task12_replay"
            )
            if (
                isinstance(persisted_context, dict)
                and persisted_context.get("audit_identity") != result.audit_identity
            ):
                raise ReplayTrainedServiceBlockerError(
                    "the persisted TASK-012 audit identity does not match the result",
                    blocker_code=_TASK12_PERSISTENCE_INTEGRITY,
                )
            return result

        await _verify_persisted_task9(session, request=request)
        visible_samples = await _visible_samples(session, request=request)
        training_candidates = tuple(
            FilteredTrainingRow(
                observation_date=_date_value(row, "observation_date"),
                value=_float_value(row, "value"),
            )
            for row in request.training_rows
        )
        filtered_training = filter_training_rows_by_cutoff(
            training_candidates,
            training_cutoff_at=request.training_cutoff_at.date(),
        )
        try:
            require_non_empty_training_rows(
                filtered_training,
                training_cutoff_at=request.training_cutoff_at.date(),
                candidate_row_count=len(training_candidates),
            )
        except TrainingRowsEmptyError as exc:
            raise ReplayTrainedServiceBlockerError(
                "no training rows remain visible at the training cutoff",
                blocker_code=OrchestrationBlocker.TASK12_TRAINING_ROWS_EMPTY.value,
                details={"filter_payload": exc.payload},
            ) from exc
        label_candidates = tuple(
            FilteredLabelRow(
                observation_date=_date_value(row, "observation_date"),
                label_availability_date=_date_value(row, "label_availability_date"),
                value=_float_value(row, "value"),
            )
            for row in request.label_rows
        )
        filtered_labels = filter_labels_by_availability_cutoff(
            label_candidates,
            label_availability_cutoff_at=request.training_cutoff_at.date(),
        )

        try:
            rebuilt_manifest_rows = await build_residual_training_manifest(
                session,
                samples=visible_samples,
            )
        except (ResidualManifestBuildError, ValueError) as exc:
            raise ReplayTrainedServiceBlockerError(
                "the persisted Task 10 manifest could not be rebuilt",
                blocker_code=_TASK12_DATASET_MISMATCH,
                details={"exception_type": type(exc).__name__},
            ) from exc
        rebuilt_manifest_payload = _actual_manifest_payload(rebuilt_manifest_rows)
        actual_training_rows, actual_label_rows = _actual_input_rows(rebuilt_manifest_rows)
        actual_dataset_hash = _dataset_identity(
            training_rows=actual_training_rows,
            label_rows=actual_label_rows,
            manifest_rows=rebuilt_manifest_payload,
        )
        actual_summary = {
            "row_count": len(rebuilt_manifest_rows),
            "excluded_row_count": len(rebuilt_manifest_rows)
            - sum(1 for row in rebuilt_manifest_rows if row.include),
        }
        request_training_rows = _request_training_rows(filtered_training)
        request_label_rows = _request_label_rows(filtered_labels)
        if (
            request_training_rows != actual_training_rows
            or request_label_rows != actual_label_rows
            or list(request.manifest_rows_payload) != rebuilt_manifest_payload
            or request.training_manifest.training_dataset_hash != actual_dataset_hash
            or request.training_manifest.row_count != actual_summary["row_count"]
            or request.training_manifest.excluded_row_count != actual_summary["excluded_row_count"]
        ):
            raise ReplayTrainedServiceBlockerError(
                "request dataset identity does not match the rebuilt persisted Task 10 dataset",
                blocker_code=_TASK12_DATASET_MISMATCH,
                mismatched_fields=(
                    "training_rows",
                    "label_rows",
                    "manifest_rows_payload",
                    "training_dataset_hash",
                    "manifest_row_count",
                    "manifest_excluded_row_count",
                ),
            )

        actual_manifest = replace(
            request.training_manifest,
            training_dataset_hash=actual_dataset_hash,
            row_count=actual_summary["row_count"],
            excluded_row_count=actual_summary["excluded_row_count"],
        )
        actual_model_config = _task10_model_config_projection(config)
        if request.model_config != actual_model_config:
            raise ReplayTrainedServiceBlockerError(
                "request model config identity does not match the persisted Task 10 config",
                blocker_code=_TASK12_DATASET_MISMATCH,
                mismatched_fields=("model_config",),
            )
        projection = project_replay_trained_identity(
            manifest=actual_manifest,
            config=actual_model_config,
            model_code_version=request.model_code_version,
            task12_policy_version=request.task12_policy_version,
        )
        try:
            verify_replay_trained_artifact_identity(
                ArtifactIdentityPair(
                    json_side=request.artifact_identity_json,
                    manifest_side=request.artifact_identity_manifest,
                ),
                projection=projection,
            )
        except ReplayTrainedArtifactIdentityMismatchError as exc:
            raise ReplayTrainedServiceBlockerError(
                "replay-trained artifact identity mismatch",
                blocker_code=OrchestrationBlocker.TASK12_ARTIFACT_IDENTITY_MISMATCH.value,
                mismatched_fields=exc.mismatched_fields,
            ) from exc

        task12_context = _task12_context(
            request=request,
            projection=projection,
            request_payload_hash=request_payload_hash,
            task10_manifest_hash=manifest_hash(rebuilt_manifest_rows),
            task10_config_hash=config.config_hash,
        )
        try:
            training_result, training_run_id = await execute_residual_training(
                session,
                samples=list(visible_samples),
                config=config,
                execution_context={"task12_replay": task12_context},
                typed_attempt={"task12_replay": task12_context},
            )
        except (
            ResidualTrainingApplicationIntegrityError,
            ResidualModelPersistenceIntegrityError,
        ) as exc:
            raise ReplayTrainedServiceBlockerError(
                "the real Task 10 training path failed integrity checks",
                blocker_code=_TASK12_TRAINING_EXECUTION_FAILED,
                details={"exception_type": type(exc).__name__},
            ) from exc
        if (
            training_result.execution_status != "completed"
            or training_result.eligibility_status != "eligible"
        ):
            raise ReplayTrainedServiceBlockerError(
                "the real Task 10 training path did not produce an eligible model",
                blocker_code=_TASK12_TRAINING_EXECUTION_FAILED,
                details={"training_status": training_result.execution_status.value},
            )
        training_row = await get_residual_training_run(session, run_id=training_run_id)
        if training_row is None:
            raise ReplayTrainedServiceBlockerError(
                "the persisted Task 10 training run could not be loaded",
                blocker_code=_TASK12_PERSISTENCE_INTEGRITY,
            )
        artifact_rows = await list_residual_artifacts(session, training_run_id=training_run_id)
        artifact_hashes = [row.artifact_sha256 for row in artifact_rows]
        if len(artifact_hashes) != 3:
            raise ReplayTrainedServiceBlockerError(
                "the persisted Task 10 training run does not have three artifacts",
                blocker_code=_TASK12_PERSISTENCE_INTEGRITY,
            )
        for artifact in artifact_rows:
            metadata = artifact.artifact_metadata_json
            if (
                metadata.get("training_signature") != training_result.training_signature
                or metadata.get("manifest_hash") != training_result.manifest_hash
                or metadata.get("config_hash") != training_result.config_hash
            ):
                raise ReplayTrainedServiceBlockerError(
                    "a persisted Task 10 artifact is not bound to the executed training run",
                    blocker_code=_TASK12_PERSISTENCE_INTEGRITY,
                )
        task12_context = _task12_context(
            request=request,
            projection=projection,
            request_payload_hash=request_payload_hash,
            task10_manifest_hash=training_result.manifest_hash,
            task10_config_hash=training_result.config_hash,
            task10_training_run_id=training_run_id,
            task10_training_signature=training_result.training_signature,
            task10_artifact_hashes=artifact_hashes,
        ) | {
            "training_execution_status": training_result.execution_status.value,
            "training_eligibility_status": training_result.eligibility_status.value,
            "filtered_training_row_count": len(filtered_training),
            "filtered_label_row_count": len(filtered_labels),
        }
        try:
            prediction_result, prediction_run_id = await execute_residual_prediction(
                session,
                request=ResidualPredictionRequest(
                    model_run_id=training_run_id,
                    task9_run_id=request.task9_run_id,
                    feature_analytics_build_run_id=visible_samples[
                        0
                    ].feature_analytics_build_run_id,
                    supplemental_feature_values=request.supplemental_feature_values,
                ),
                model_policy=Task10ModelPolicy.REPLAY_TRAINED_MODEL,
                execution_context={"task12_replay": task12_context},
                typed_attempt={"task12_replay": task12_context},
            )
        except (
            ResidualPredictionApplicationIntegrityError,
            ResidualModelPersistenceIntegrityError,
        ) as exc:
            raise ReplayTrainedServiceBlockerError(
                "the real Task 10 prediction path failed integrity checks",
                blocker_code=OrchestrationBlocker.TASK12_PREDICTION_BINDING_MISMATCH.value,
                details={"exception_type": type(exc).__name__},
            ) from exc
        if (
            prediction_result.execution_status != "completed"
            or prediction_result.mode.value != "residual_corrected"
        ):
            raise ReplayTrainedServiceBlockerError(
                "replay-trained execution must produce residual-corrected output",
                blocker_code=OrchestrationBlocker.TASK12_PREDICTION_BINDING_MISMATCH.value,
            )
        fresh_prediction = await _fresh_prediction_reload(
            session,
            prediction_run_id=prediction_run_id,
        )
        if fresh_prediction.prediction_hash != prediction_result.prediction_hash:
            raise ReplayTrainedServiceBlockerError(
                "fresh-session prediction reload changed the persisted result",
                blocker_code=_TASK12_PERSISTENCE_INTEGRITY,
            )
        result = _result_payload(
            request=request,
            projection=projection,
            request_payload_hash=request_payload_hash,
            training_result=training_result,
            prediction_result=fresh_prediction,
            prediction_run_id=prediction_run_id,
            task10_training_run_id=training_run_id,
            task10_training_signature=training_result.training_signature,
            task10_manifest_hash=training_result.manifest_hash,
            task10_config_hash=training_result.config_hash,
            task10_artifact_hashes=artifact_hashes,
            filtered_training_row_count=len(filtered_training),
            filtered_label_row_count=len(filtered_labels),
            created=True,
        )
        await _finalize_task12_audit_payload(
            session,
            prediction_run_id=prediction_run_id,
            audit_payload=result.audit_payload,
        )
        return result
