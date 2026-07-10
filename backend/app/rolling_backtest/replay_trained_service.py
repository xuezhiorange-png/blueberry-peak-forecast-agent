"""TASK-012 Slice E2 replay-trained application service.

This module is the explicit boundary for ``replay_trained_model`` execution.
It validates the complete replay identity before delegating to the existing
Task 10 contract-payload services. It does not change Task 8, Task 9, or
Task 10 algorithms, and it does not infer state from the database.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from typing import Any, Final, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.harvest_state.persistence import load_harvest_state_output_by_id
from backend.app.models.harvest_state import HarvestStateRun
from backend.app.residual_model.config import load_residual_model_config_from_snapshot
from backend.app.residual_model.service import (
    predict_residual_model_from_contract_payload,
    train_residual_model_from_contract_payload,
)

from .canonical import canonical_json_dumps, sha256_payload
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
    ReplayTrainedBindingInput,
    bind_replay_trained_prediction,
    verify_replay_trained_artifact_identity,
)

_SERVICE_VERSION: Final[str] = "task12-slice-e2-v1"
_TASK12_TRAINING_EXECUTION_FAILED: Final[str] = "task12_training_execution_failed"
_HASH_LENGTH: Final[int] = 64


class ReplayTrainedServiceError(ValueError):
    """Base error with stable machine-readable service metadata."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        blocker_code: str | None = None,
        mismatched_fields: tuple[str, ...] = (),
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.blocker_code = blocker_code
        self.mismatched_fields = mismatched_fields
        payload: dict[str, object] = {
            "code": code,
            "blocker": blocker_code,
            "mismatched_fields": list(mismatched_fields),
        }
        if details:
            payload["details"] = dict(details)
        self.payload = canonical_json_dumps(payload)

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
    """Idempotency or exact-identity conflict."""

    def __init__(self, message: str, *, mismatched_fields: tuple[str, ...]) -> None:
        super().__init__(
            message,
            code="TASK012_REPLAY_TRAINED_CONFLICT",
            mismatched_fields=mismatched_fields,
        )


@dataclass(frozen=True, slots=True)
class ReplayTrainedExecutionRequest:
    """Complete explicit identity and deterministic payload for Slice E2."""

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
    prediction_run_id: int
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
            excluded_row_count=_int_value(required_from(manifest_payload, "excluded_row_count")),
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
            prediction_run_id=_int_value(required("prediction_run_id")),
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
            },
            artifact_identity_json=_parse_identity_payload(
                cast(dict[str, object], required("artifact_identity_json"))
            ),
            artifact_identity_manifest=_parse_identity_payload(
                cast(dict[str, object], required("artifact_identity_manifest"))
            ),
            feature_actual_snapshot=cast(
                dict[str, object] | None, payload.get("feature_actual_snapshot")
            ),
            idempotency_key=str(required("idempotency_key")),
            caller_identity=str(required("caller_identity")),
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
            "prediction_run_id": self.prediction_run_id,
            "is_replay": self.is_replay,
            "task10_config_snapshot": self.task10_config_snapshot,
            "manifest_rows_payload": [dict(item) for item in self.manifest_rows_payload],
            "training_rows": [dict(item) for item in self.training_rows],
            "label_rows": [dict(item) for item in self.label_rows],
            "source_run_ids": dict(sorted(self.source_run_ids.items())),
            "artifact_identity_json": _json_safe(self.artifact_identity_json),
            "artifact_identity_manifest": _json_safe(self.artifact_identity_manifest),
            "feature_actual_snapshot": self.feature_actual_snapshot,
            "idempotency_key": self.idempotency_key,
            "caller_identity": self.caller_identity,
        }

    def canonical_identity_payload(self, *, task10_config_hash: str) -> dict[str, object]:
        return {
            "service_version": _SERVICE_VERSION,
            "request": {
                key: value
                for key, value in self.to_payload().items()
                if key not in {"task10_config_snapshot"}
            },
            "task10_config_hash": task10_config_hash,
            "manifest_rows_hash": _json_hash(self.manifest_rows_payload),
            "training_rows": _canonical_temporal_rows(self.training_rows),
            "label_rows": _canonical_temporal_rows(self.label_rows),
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
    _payload: dict[str, object]

    def to_payload(self) -> dict[str, object]:
        return dict(self._payload)


_IDEMPOTENCY_RESULTS: dict[str, tuple[str, ReplayTrainedExecutionResult]] = {}


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
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReplayTrainedServiceInputError(
            "datetime fields must be valid ISO-8601 values",
            mismatched_fields=("datetime_format",),
        ) from exc
    return parsed


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
    if isinstance(value, tuple | list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return value


def _parse_identity_payload(payload: dict[str, object]) -> dict[str, object]:
    parsed = dict(payload)
    for field in ("forecast_cutoff_at", "training_cutoff_at"):
        value = parsed.get(field)
        if isinstance(value, str):
            parsed[field] = _parse_datetime(value)
    return parsed


def _json_hash(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _canonical_temporal_rows(rows: tuple[dict[str, object], ...]) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for row in rows:
        normalized.append(
            {
                key: (str(value) if isinstance(value, float) else value)
                for key, value in sorted(row.items())
            }
        )
    return normalized


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
    return float(raw)


def _same_datetime(left: datetime, right: datetime) -> bool:
    return left.astimezone(UTC) == right.astimezone(UTC)


def _request_projection(
    request: ReplayTrainedExecutionRequest,
) -> ReplayTrainedIdentityProjection:
    return project_replay_trained_identity(
        manifest=request.training_manifest,
        config=request.model_config,
        model_code_version=request.model_code_version,
        task12_policy_version=request.task12_policy_version,
    )


def _validate_request(
    request: ReplayTrainedExecutionRequest,
) -> tuple[ReplayTrainedIdentityProjection, str]:
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
    if request.prediction_run_id <= 0 or request.task9_run_id <= 0:
        raise ReplayTrainedServiceInputError(
            "prediction_run_id and task9_run_id must be positive",
            mismatched_fields=("run_id_must_be_positive",),
        )
    if (
        request.forecast_cutoff_at.tzinfo is None
        or request.forecast_cutoff_at.utcoffset() is None
        or request.training_cutoff_at.tzinfo is None
        or request.training_cutoff_at.utcoffset() is None
    ):
        raise ReplayTrainedServiceInputError(
            "forecast and training cutoffs must be timezone-aware",
            mismatched_fields=("cutoff_timezone_required",),
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
    identity_mismatches: list[str] = []
    for name in ("replay_attempt_id", "replay_node_id", "scenario_id"):
        if getattr(request, name) != getattr(manifest, name):
            identity_mismatches.append(f"{name}_mismatch")
    if not _same_datetime(request.forecast_cutoff_at, manifest.forecast_cutoff_at):
        identity_mismatches.append("forecast_cutoff_mismatch")
    if not _same_datetime(request.training_cutoff_at, manifest.training_cutoff_at):
        identity_mismatches.append("training_cutoff_mismatch")
    if tuple(request.allowed_training_season_ids) != tuple(manifest.allowed_training_season_ids):
        identity_mismatches.append("allowed_training_season_ids_mismatch")
    if identity_mismatches:
        raise ReplayTrainedServiceBlockerError(
            "replay request identity disagrees with its training manifest",
            blocker_code=OrchestrationBlocker.TASK12_CROSS_RUN_SUBSTITUTION.value,
            mismatched_fields=tuple(identity_mismatches),
        )

    expected_task9_binding = sha256_payload(
        {
            "task9_run_id": request.task9_run_id,
            "task9_result_hash": request.task9_result_hash,
            "is_replay": True,
            "replay_code_version": request.replay_code_version,
        }
    )
    if manifest.task9_replay_binding_identity != expected_task9_binding:
        raise ReplayTrainedServiceBlockerError(
            "Task 9 binding identity does not match the explicit replay request",
            blocker_code=OrchestrationBlocker.TASK12_CROSS_RUN_SUBSTITUTION.value,
            mismatched_fields=("task9_replay_binding_identity_mismatch",),
        )

    try:
        projection = _request_projection(request)
    except (TypeError, ValueError) as exc:
        raise ReplayTrainedServiceInputError(
            "replay-trained identity projection is invalid",
            mismatched_fields=("identity_projection_invalid",),
        ) from exc
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

    request_payload_hash = sha256_payload(request.canonical_identity_payload(task10_config_hash=""))
    return projection, request_payload_hash


async def _verify_persisted_task9(
    session: AsyncSession,
    *,
    request: ReplayTrainedExecutionRequest,
) -> None:
    result = await session.execute(
        select(HarvestStateRun).where(HarvestStateRun.id == request.task9_run_id)
    )
    run = result.scalar_one_or_none()
    if run is None or not bool(run.is_replay):
        raise ReplayTrainedServiceBlockerError(
            "the exact replay-produced Task 9 run is not available",
            blocker_code=OrchestrationBlocker.TASK12_CROSS_RUN_SUBSTITUTION.value,
            mismatched_fields=("task9_replay_run_missing_or_not_replay",),
        )
    output = await load_harvest_state_output_by_id(session, run_id=request.task9_run_id)
    if output is None or output.result_hash != request.task9_result_hash:
        raise ReplayTrainedServiceBlockerError(
            "the exact Task 9 result hash does not match persisted authority",
            blocker_code=OrchestrationBlocker.TASK12_CROSS_RUN_SUBSTITUTION.value,
            mismatched_fields=("task9_result_hash_mismatch",),
        )


async def execute_replay_trained_prediction(
    session: AsyncSession | None,
    *,
    request: ReplayTrainedExecutionRequest,
) -> ReplayTrainedExecutionResult:
    """Execute one explicitly identified replay-trained prediction request."""

    projection, _ = _validate_request(request)
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
    existing = _IDEMPOTENCY_RESULTS.get(request.idempotency_key)
    if existing is not None:
        existing_hash, existing_result = existing
        if existing_hash != request_payload_hash:
            raise ReplayTrainedServiceConflictError(
                "idempotency key is already bound to a different canonical request",
                mismatched_fields=("idempotency_key_payload_mismatch",),
            )
        return existing_result

    if session is not None:
        await _verify_persisted_task9(session, request=request)

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
    if len(request.manifest_rows_payload) < len(filtered_training):
        raise ReplayTrainedServiceInputError(
            "manifest_rows_payload must cover every visible training row",
            mismatched_fields=("manifest_rows_payload_incomplete",),
        )

    try:
        training_result, _ = train_residual_model_from_contract_payload(
            config=config,
            manifest_rows_payload=list(request.manifest_rows_payload[: len(filtered_training)]),
            forecast_cutoff=request.forecast_cutoff_at.date(),
            source_run_ids=request.source_run_ids,
            idempotency_key=request.idempotency_key,
        )
    except Exception as exc:
        raise ReplayTrainedServiceBlockerError(
            "the delegated Task 10 training path raised a deterministic failure",
            blocker_code=_TASK12_TRAINING_EXECUTION_FAILED,
            details={"delegate": "training", "exception_type": type(exc).__name__},
        ) from exc
    if training_result.execution_status == "failed":
        raise ReplayTrainedServiceBlockerError(
            "the delegated Task 10 training path failed",
            blocker_code=_TASK12_TRAINING_EXECUTION_FAILED,
            details={"training_status": training_result.execution_status},
        )

    try:
        prediction_result = predict_residual_model_from_contract_payload(
            config=config,
            training_run_id=None,
            task9_run_id=request.task9_run_id,
            task9_result_hash=request.task9_result_hash,
            feature_actual_snapshot=request.feature_actual_snapshot,
            supplemental_feature_payloads=[],
            prediction_mode="structural_only",
            source_run_ids=request.source_run_ids,
            idempotency_key=request.idempotency_key,
            training_signature_override=training_result.training_signature,
        )
        binding = bind_replay_trained_prediction(
            ReplayTrainedBindingInput(
                prediction_run_id=request.prediction_run_id,
                projection=projection,
                task9_run_id=request.task9_run_id,
                task9_result_hash=request.task9_result_hash,
                replay_code_version=request.replay_code_version,
                is_replay=request.is_replay,
                replay_attempt_id=request.replay_attempt_id,
                replay_node_id=request.replay_node_id,
            )
        )
    except Exception as exc:
        raise ReplayTrainedServiceBlockerError(
            "the delegated Task 10 prediction path raised a deterministic failure",
            blocker_code=OrchestrationBlocker.TASK12_PREDICTION_BINDING_MISMATCH.value,
            details={"delegate": "prediction", "exception_type": type(exc).__name__},
        ) from exc
    payload_without_audit: dict[str, object] = {
        "service_version": _SERVICE_VERSION,
        "model_policy": binding.model_policy.value,
        "task12_policy_version": projection.task12_policy_version,
        "replay_attempt_id": binding.replay_attempt_id,
        "replay_node_id": binding.replay_node_id,
        "training_manifest_hash": binding.training_manifest_hash,
        "training_dataset_hash": projection.manifest.training_dataset_hash,
        "model_config_hash": projection.model_config_hash,
        "model_artifact_hash": binding.model_artifact_hash,
        "model_code_version": projection.model_code_version,
        "forecast_cutoff_at": _datetime_string(binding.forecast_cutoff_at),
        "training_cutoff_at": _datetime_string(binding.training_cutoff_at),
        "task9_run_id": binding.task9_run_id,
        "task9_result_hash": binding.task9_result_hash,
        "prediction_run_id": binding.prediction_run_id,
        "prediction_hash": binding.prediction_hash,
        "request_payload_hash": request_payload_hash,
        "filtered_training_row_count": len(filtered_training),
        "filtered_label_row_count": len(filtered_labels),
        "training_execution_status": str(training_result.execution_status),
        "training_eligibility_status": str(training_result.eligibility_status),
        "prediction_execution_status": str(prediction_result.execution_status),
        "prediction_mode": str(prediction_result.mode),
        "idempotency_key": request.idempotency_key,
        "caller_identity": request.caller_identity,
        "no_implicit_selection": True,
        "no_cross_run_substitution": True,
    }
    audit_identity = sha256_payload(payload_without_audit)
    payload = {**payload_without_audit, "audit_identity": audit_identity}
    result = ReplayTrainedExecutionResult(
        model_policy=binding.model_policy,
        prediction_run_id=binding.prediction_run_id,
        prediction_hash=binding.prediction_hash,
        request_payload_hash=request_payload_hash,
        training_manifest_hash=binding.training_manifest_hash,
        model_config_hash=projection.model_config_hash,
        model_artifact_hash=binding.model_artifact_hash,
        task9_run_id=binding.task9_run_id,
        task9_result_hash=binding.task9_result_hash,
        filtered_training_row_count=len(filtered_training),
        filtered_label_row_count=len(filtered_labels),
        training_execution_status=str(training_result.execution_status),
        training_eligibility_status=str(training_result.eligibility_status),
        prediction_execution_status=str(prediction_result.execution_status),
        prediction_mode=str(prediction_result.mode),
        audit_identity=audit_identity,
        _payload=payload,
    )
    _IDEMPOTENCY_RESULTS[request.idempotency_key] = (request_payload_hash, result)
    return result
