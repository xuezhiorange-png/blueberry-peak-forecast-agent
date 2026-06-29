from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from backend.app.rolling_backtest.canonical import canonical_json_value, sha256_payload
from backend.app.rolling_backtest.enums import (
    AVAILABILITY_REGISTRY_VERSION,
    AvailabilityBlockerCode,
    AvailabilityRuleKind,
    AvailabilitySourceType,
    ExecutionMode,
)
from backend.app.rolling_backtest.schemas import (
    AvailabilityAuthorityEvaluationResult,
    AvailabilityAuthoritySpec,
    AvailabilitySnapshot,
    ParentAuthorityIdentity,
    Task3AnalyticsBuildAvailabilitySnapshot,
    Task6PlanVersionAvailabilitySnapshot,
    Task7WeatherObservationAvailabilitySnapshot,
    Task8DailyPredictionAvailabilitySnapshot,
    Task8ForecastRunAvailabilitySnapshot,
    Task8ModelArtifactAvailabilitySnapshot,
    Task8ModelRunAvailabilitySnapshot,
    Task9HarvestStateRunAvailabilitySnapshot,
    Task10ModelArtifactAvailabilitySnapshot,
    Task10PredictionRunAvailabilitySnapshot,
    Task10TrainingRunAvailabilitySnapshot,
)

_LOCAL_AVAILABLE_DATE_POLICY_VERSION = "task11-local-date-visibility-v1"
_TASK3_SOURCE_VISIBILITY_POLICY_VERSION = "task11-task3-source-visibility-v1"


def build_availability_authority_registry() -> tuple[AvailabilityAuthoritySpec, ...]:
    registry = (
        AvailabilityAuthoritySpec(
            source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
            rule_kind=AvailabilityRuleKind.TASK3_SOURCE_VISIBILITY,
            required_statuses=("completed",),
            authoritative_timestamp_field="finished_at",
            task3_source_visibility_field="task3_source_visibility",
            parent_authority_required=False,
            source_visibility_policy_version=_TASK3_SOURCE_VISIBILITY_POLICY_VERSION,
        ),
        AvailabilityAuthoritySpec(
            source_type=AvailabilitySourceType.TASK6_PLAN_VERSION,
            rule_kind=AvailabilityRuleKind.LOCAL_AVAILABLE_DATE,
            required_statuses=(),
            available_on_local_date_field="available_at",
            parent_authority_required=False,
            local_date_policy_version=_LOCAL_AVAILABLE_DATE_POLICY_VERSION,
        ),
        AvailabilityAuthoritySpec(
            source_type=AvailabilitySourceType.TASK7_WEATHER_OBSERVATION,
            rule_kind=AvailabilityRuleKind.LOCAL_AVAILABLE_DATE_WITH_OBSERVATION_DATE,
            required_statuses=(),
            available_on_local_date_field="available_at",
            observation_date_field="observation_date",
            parent_authority_required=False,
            local_date_policy_version=_LOCAL_AVAILABLE_DATE_POLICY_VERSION,
        ),
        AvailabilityAuthoritySpec(
            source_type=AvailabilitySourceType.TASK7_WEATHER_FEATURE_RUN,
            rule_kind=AvailabilityRuleKind.AUTHORITATIVE_TIMESTAMP,
            required_statuses=("completed", "unavailable"),
            authoritative_timestamp_field="finished_at",
            parent_authority_required=False,
        ),
        AvailabilityAuthoritySpec(
            source_type=AvailabilitySourceType.TASK7_LOCATION_WEATHER_MAPPING,
            rule_kind=AvailabilityRuleKind.LOCAL_AVAILABLE_DATE,
            required_statuses=(),
            available_on_local_date_field="available_at",
            parent_authority_required=False,
            local_date_policy_version=_LOCAL_AVAILABLE_DATE_POLICY_VERSION,
        ),
        AvailabilityAuthoritySpec(
            source_type=AvailabilitySourceType.TASK8_MODEL_RUN,
            rule_kind=AvailabilityRuleKind.AUTHORITATIVE_TIMESTAMP,
            required_statuses=("completed", "unavailable"),
            authoritative_timestamp_field="finished_at",
            parent_authority_required=False,
        ),
        AvailabilityAuthoritySpec(
            source_type=AvailabilitySourceType.TASK8_MODEL_ARTIFACT,
            rule_kind=AvailabilityRuleKind.AUTHORITATIVE_TIMESTAMP,
            required_statuses=(),
            authoritative_timestamp_field="created_at",
            parent_authority_required=True,
        ),
        AvailabilityAuthoritySpec(
            source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
            rule_kind=AvailabilityRuleKind.AUTHORITATIVE_TIMESTAMP,
            required_statuses=("completed", "unavailable"),
            authoritative_timestamp_field="finished_at",
            parent_authority_required=False,
        ),
        AvailabilityAuthoritySpec(
            source_type=AvailabilitySourceType.TASK8_DAILY_PREDICTION,
            rule_kind=AvailabilityRuleKind.AUTHORITATIVE_WITH_OBSERVATION_DATE,
            required_statuses=(),
            authoritative_timestamp_field="created_at",
            observation_date_field="prediction_date",
            parent_authority_required=True,
        ),
        AvailabilityAuthoritySpec(
            source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
            rule_kind=AvailabilityRuleKind.AUTHORITATIVE_TIMESTAMP,
            required_statuses=("completed", "blocked"),
            authoritative_timestamp_field="created_at",
            parent_authority_required=False,
        ),
        AvailabilityAuthoritySpec(
            source_type=AvailabilitySourceType.TASK10_TRAINING_RUN,
            rule_kind=AvailabilityRuleKind.AUTHORITATIVE_TIMESTAMP,
            required_statuses=("completed", "blocked", "failed"),
            authoritative_timestamp_field="finished_at",
            parent_authority_required=False,
        ),
        AvailabilityAuthoritySpec(
            source_type=AvailabilitySourceType.TASK10_MODEL_ARTIFACT,
            rule_kind=AvailabilityRuleKind.AUTHORITATIVE_TIMESTAMP,
            required_statuses=(),
            authoritative_timestamp_field="created_at",
            parent_authority_required=True,
        ),
        AvailabilityAuthoritySpec(
            source_type=AvailabilitySourceType.TASK10_PREDICTION_RUN,
            rule_kind=AvailabilityRuleKind.AUTHORITATIVE_TIMESTAMP,
            required_statuses=("completed", "blocked", "failed"),
            authoritative_timestamp_field="completed_at",
            parent_authority_required=False,
        ),
    )
    _validate_registry(registry)
    return registry


def _validate_registry(registry: tuple[AvailabilityAuthoritySpec, ...]) -> None:
    source_types = [item.source_type for item in registry]
    if len(set(source_types)) != len(source_types):
        raise ValueError("availability registry contains duplicate source types")
    if set(source_types) != set(AvailabilitySourceType):
        raise ValueError("availability registry is incomplete")

    for item in registry:
        if item.rule_kind == AvailabilityRuleKind.AUTHORITATIVE_TIMESTAMP:
            if item.authoritative_timestamp_field is None:
                raise ValueError("authoritative rule requires authoritative timestamp field")
            if any(
                (
                    item.available_on_local_date_field,
                    item.observation_date_field,
                    item.task3_source_visibility_field,
                )
            ):
                raise ValueError("authoritative rule has unreachable field requirements")
        elif item.rule_kind == AvailabilityRuleKind.AUTHORITATIVE_WITH_OBSERVATION_DATE:
            if item.authoritative_timestamp_field is None or item.observation_date_field is None:
                raise ValueError(
                    "authoritative observation rule requires authoritative and observation fields"
                )
        elif item.rule_kind == AvailabilityRuleKind.LOCAL_AVAILABLE_DATE:
            if item.available_on_local_date_field is None:
                raise ValueError("local available date rule requires local date field")
            if item.local_date_policy_version is None:
                raise ValueError("local available date rule requires policy version")
        elif item.rule_kind == AvailabilityRuleKind.LOCAL_AVAILABLE_DATE_WITH_OBSERVATION_DATE:
            if item.available_on_local_date_field is None or item.observation_date_field is None:
                raise ValueError(
                    "local available date observation rule requires local date and observation"
                )
            if item.local_date_policy_version is None:
                raise ValueError("local available date observation rule requires policy version")
        elif item.rule_kind == AvailabilityRuleKind.TASK3_SOURCE_VISIBILITY:
            if (
                item.authoritative_timestamp_field is None
                or item.task3_source_visibility_field is None
            ):
                raise ValueError("task3 source visibility rule requires authority and visibility")
            if item.source_visibility_policy_version is None:
                raise ValueError("task3 source visibility rule requires policy version")
        else:
            raise ValueError(f"unsupported availability rule kind: {item.rule_kind.value}")


def evaluate_authority_visibility(
    *,
    snapshot: AvailabilitySnapshot,
    execution_mode: ExecutionMode,
    forecast_cutoff_at: datetime,
    as_of_local_date: date,
    business_timezone: str,
) -> AvailabilityAuthorityEvaluationResult:
    ZoneInfo(business_timezone)
    spec = get_availability_authority_spec(snapshot.source_type)

    return _dispatch_evaluator(
        snapshot=snapshot,
        spec=spec,
        execution_mode=execution_mode,
        forecast_cutoff_at=forecast_cutoff_at,
        as_of_local_date=as_of_local_date,
    )


def _dispatch_evaluator(
    *,
    snapshot: AvailabilitySnapshot,
    spec: AvailabilityAuthoritySpec,
    execution_mode: ExecutionMode,
    forecast_cutoff_at: datetime,
    as_of_local_date: date,
) -> AvailabilityAuthorityEvaluationResult:

    if isinstance(snapshot, Task3AnalyticsBuildAvailabilitySnapshot):
        return _evaluate_task3(
            snapshot=snapshot,
            spec=spec,
            execution_mode=execution_mode,
            forecast_cutoff_at=forecast_cutoff_at,
        )
    if isinstance(snapshot, Task6PlanVersionAvailabilitySnapshot):
        return _evaluate_local_date(
            available_on_local_date=snapshot.available_at,
            as_of_local_date=as_of_local_date,
        )
    if isinstance(snapshot, Task7WeatherObservationAvailabilitySnapshot):
        return _evaluate_local_date_observation(
            available_on_local_date=snapshot.available_at,
            observation_date=snapshot.observation_date,
            as_of_local_date=as_of_local_date,
        )
    if isinstance(
        snapshot, (Task8ModelRunAvailabilitySnapshot, Task8ForecastRunAvailabilitySnapshot)
    ):
        return _evaluate_run(
            status=snapshot.status,
            required_statuses=spec.required_statuses,
            authoritative_timestamp=snapshot.authoritative_timestamp,
            forecast_cutoff_at=forecast_cutoff_at,
        )
    if isinstance(snapshot, Task8ModelArtifactAvailabilitySnapshot):
        return _evaluate_artifact(
            created_at=snapshot.created_at,
            parent_authority_timestamp=snapshot.parent_authority.authority_timestamp,
            parent_authority_status=snapshot.parent_authority.authority_status,
            forecast_cutoff_at=forecast_cutoff_at,
        )
    if isinstance(snapshot, Task8DailyPredictionAvailabilitySnapshot):
        return _evaluate_daily_prediction(
            created_at=snapshot.created_at,
            prediction_date=snapshot.prediction_date,
            parent_authority_timestamp=snapshot.parent_authority.authority_timestamp,
            parent_authority_status=snapshot.parent_authority.authority_status,
            forecast_cutoff_at=forecast_cutoff_at,
            as_of_local_date=as_of_local_date,
        )
    if isinstance(snapshot, Task9HarvestStateRunAvailabilitySnapshot):
        return _evaluate_run(
            status=snapshot.status,
            required_statuses=spec.required_statuses,
            authoritative_timestamp=snapshot.authoritative_timestamp,
            forecast_cutoff_at=forecast_cutoff_at,
        )
    if isinstance(
        snapshot, (Task10TrainingRunAvailabilitySnapshot, Task10PredictionRunAvailabilitySnapshot)
    ):
        return _evaluate_run(
            status=snapshot.status,
            required_statuses=spec.required_statuses,
            authoritative_timestamp=snapshot.authoritative_timestamp,
            forecast_cutoff_at=forecast_cutoff_at,
        )
    if isinstance(snapshot, Task10ModelArtifactAvailabilitySnapshot):
        return _evaluate_artifact(
            created_at=snapshot.created_at,
            parent_authority_timestamp=snapshot.parent_authority.authority_timestamp,
            parent_authority_status=snapshot.parent_authority.authority_status,
            forecast_cutoff_at=forecast_cutoff_at,
        )

    raise TypeError(f"unsupported availability snapshot type: {type(snapshot).__name__}")


def _evaluate_task3(
    *,
    snapshot: Task3AnalyticsBuildAvailabilitySnapshot,
    spec: AvailabilityAuthoritySpec,
    execution_mode: ExecutionMode,
    forecast_cutoff_at: datetime,
) -> AvailabilityAuthorityEvaluationResult:
    if snapshot.status not in spec.required_statuses:
        return _blocked(AvailabilityBlockerCode.STATUS_NOT_ALLOWED)

    expected_policy = spec.source_visibility_policy_version
    if expected_policy is None:
        raise ValueError("task3 source visibility rule requires policy version in registry spec")

    if execution_mode == ExecutionMode.HISTORICAL_OBSERVED:
        if snapshot.authoritative_timestamp > forecast_cutoff_at:
            return _blocked(AvailabilityBlockerCode.AUTHORITATIVE_TIMESTAMP_AFTER_CUTOFF)
        if snapshot.task3_source_visibility is None:
            return _blocked(AvailabilityBlockerCode.SOURCE_VISIBILITY_MISSING)
        if snapshot.task3_source_visibility.visible_through_at > forecast_cutoff_at:
            return _blocked(AvailabilityBlockerCode.SOURCE_CUTOFF_AFTER_FORECAST_CUTOFF)
        if snapshot.task3_source_visibility.visibility_policy_version != expected_policy:
            return _blocked(AvailabilityBlockerCode.SOURCE_VISIBILITY_POLICY_MISMATCH)
        return AvailabilityAuthorityEvaluationResult(allowed=True, blocker_code=None)

    if execution_mode == ExecutionMode.RETROSPECTIVE_REPLAY:
        if snapshot.task3_source_visibility is None:
            return _blocked(AvailabilityBlockerCode.SOURCE_VISIBILITY_MISSING)
        if snapshot.task3_source_visibility.visible_through_at > forecast_cutoff_at:
            return _blocked(AvailabilityBlockerCode.SOURCE_CUTOFF_AFTER_FORECAST_CUTOFF)
        if snapshot.task3_source_visibility.visibility_policy_version != expected_policy:
            return _blocked(AvailabilityBlockerCode.SOURCE_VISIBILITY_POLICY_MISMATCH)
        return AvailabilityAuthorityEvaluationResult(allowed=True, blocker_code=None)

    raise ValueError(f"unsupported execution mode: {execution_mode.value}")


def _evaluate_local_date(
    *,
    available_on_local_date: date,
    as_of_local_date: date,
) -> AvailabilityAuthorityEvaluationResult:
    if available_on_local_date > as_of_local_date:
        return _blocked(AvailabilityBlockerCode.AVAILABLE_ON_LOCAL_DATE_AFTER_AS_OF)
    return AvailabilityAuthorityEvaluationResult(allowed=True, blocker_code=None)


def _evaluate_local_date_observation(
    *,
    available_on_local_date: date,
    observation_date: date,
    as_of_local_date: date,
) -> AvailabilityAuthorityEvaluationResult:
    if available_on_local_date > as_of_local_date:
        return _blocked(AvailabilityBlockerCode.AVAILABLE_ON_LOCAL_DATE_AFTER_AS_OF)
    if observation_date > as_of_local_date:
        return _blocked(AvailabilityBlockerCode.OBSERVATION_DATE_AFTER_CUTOFF)
    return AvailabilityAuthorityEvaluationResult(allowed=True, blocker_code=None)


def _evaluate_run(
    *,
    status: str,
    required_statuses: tuple[str, ...],
    authoritative_timestamp: datetime,
    forecast_cutoff_at: datetime,
) -> AvailabilityAuthorityEvaluationResult:
    if status not in required_statuses:
        return _blocked(AvailabilityBlockerCode.STATUS_NOT_ALLOWED)
    if authoritative_timestamp > forecast_cutoff_at:
        return _blocked(AvailabilityBlockerCode.AUTHORITATIVE_TIMESTAMP_AFTER_CUTOFF)
    return AvailabilityAuthorityEvaluationResult(allowed=True, blocker_code=None)


def _evaluate_artifact(
    *,
    created_at: datetime,
    parent_authority_timestamp: datetime,
    parent_authority_status: str,
    forecast_cutoff_at: datetime,
) -> AvailabilityAuthorityEvaluationResult:
    if parent_authority_status != "completed":
        return _blocked(AvailabilityBlockerCode.PARENT_AUTHORITY_REQUIRED)
    if parent_authority_timestamp > forecast_cutoff_at:
        return _blocked(AvailabilityBlockerCode.PARENT_AUTHORITY_REQUIRED)
    if created_at > forecast_cutoff_at:
        return _blocked(AvailabilityBlockerCode.AUTHORITATIVE_TIMESTAMP_AFTER_CUTOFF)
    return AvailabilityAuthorityEvaluationResult(allowed=True, blocker_code=None)


def _evaluate_daily_prediction(
    *,
    created_at: datetime,
    prediction_date: date,
    parent_authority_timestamp: datetime,
    parent_authority_status: str,
    forecast_cutoff_at: datetime,
    as_of_local_date: date,
) -> AvailabilityAuthorityEvaluationResult:
    if parent_authority_status != "completed":
        return _blocked(AvailabilityBlockerCode.PARENT_AUTHORITY_REQUIRED)
    if parent_authority_timestamp > forecast_cutoff_at:
        return _blocked(AvailabilityBlockerCode.PARENT_AUTHORITY_REQUIRED)
    if created_at > forecast_cutoff_at:
        return _blocked(AvailabilityBlockerCode.AUTHORITATIVE_TIMESTAMP_AFTER_CUTOFF)
    if prediction_date > as_of_local_date:
        return _blocked(AvailabilityBlockerCode.OBSERVATION_DATE_AFTER_CUTOFF)
    return AvailabilityAuthorityEvaluationResult(allowed=True, blocker_code=None)


_REGISTRY = {item.source_type: item for item in build_availability_authority_registry()}


def get_availability_authority_spec(
    source_type: AvailabilitySourceType,
) -> AvailabilityAuthoritySpec:
    return _REGISTRY[source_type]


def _blocked(code: AvailabilityBlockerCode) -> AvailabilityAuthorityEvaluationResult:
    return AvailabilityAuthorityEvaluationResult(allowed=False, blocker_code=code.value)


# ── Canonical audit payloads (Phase 1 contract — no persistence) ─────────────


def parent_authority_semantic_payload(
    authority: ParentAuthorityIdentity,
) -> dict[str, object]:
    """Deterministic semantic payload for a parent-run authority.

    Explicitly includes stable identity fields and excludes persistent_reference,
    database IDs, UUIDs, and runtime diagnostics.
    """
    return {
        "source_type": authority.source_type,
        "authority_schema_version": authority.authority_schema_version,
        "authority_policy_version": authority.authority_policy_version,
        "authority_timestamp": authority.authority_timestamp,
        "authority_status": authority.authority_status,
        "semantic_input_signature": authority.semantic_input_signature,
        "result_hash": authority.result_hash,
        "canonical_payload_hash": authority.canonical_payload_hash,
    }


def parent_authority_audit_hash(authority: ParentAuthorityIdentity) -> str:
    return sha256_payload(canonical_json_value(parent_authority_semantic_payload(authority)))


def availability_snapshot_audit_payload(
    snapshot: AvailabilitySnapshot,
) -> dict[str, object]:
    """Construct a source-specific deterministic audit payload for any typed snapshot."""
    if isinstance(snapshot, Task3AnalyticsBuildAvailabilitySnapshot):
        vis = snapshot.task3_source_visibility
        return {
            "source_type": snapshot.source_type,
            "status": snapshot.status,
            "authoritative_timestamp": snapshot.authoritative_timestamp,
            "task3_source_visibility": (
                {
                    "visibility_policy_version": vis.visibility_policy_version,
                    "source_max_raw_id": vis.source_max_raw_id,
                    "aggregation_version": vis.aggregation_version,
                    "config_hash": vis.config_hash,
                    "visibility_manifest_hash": vis.visibility_manifest_hash,
                    "visible_through_at": vis.visible_through_at,
                }
                if vis is not None
                else None
            ),
        }
    if isinstance(snapshot, Task6PlanVersionAvailabilitySnapshot):
        return {
            "source_type": snapshot.source_type,
            "available_at": snapshot.available_at,
            "effective_interval_version": snapshot.effective_interval_version,
        }
    if isinstance(snapshot, Task7WeatherObservationAvailabilitySnapshot):
        return {
            "source_type": snapshot.source_type,
            "available_at": snapshot.available_at,
            "observation_date": snapshot.observation_date,
        }
    if isinstance(
        snapshot,
        (
            Task8ModelRunAvailabilitySnapshot,
            Task8ForecastRunAvailabilitySnapshot,
            Task9HarvestStateRunAvailabilitySnapshot,
            Task10TrainingRunAvailabilitySnapshot,
            Task10PredictionRunAvailabilitySnapshot,
        ),
    ):
        return {
            "source_type": snapshot.source_type,
            "status": snapshot.status,
            "authoritative_timestamp": snapshot.authoritative_timestamp,
        }
    if isinstance(snapshot, Task8ModelArtifactAvailabilitySnapshot):
        return {
            "source_type": snapshot.source_type,
            "created_at": snapshot.created_at,
            "parent_authority": parent_authority_semantic_payload(snapshot.parent_authority),
        }
    if isinstance(snapshot, Task8DailyPredictionAvailabilitySnapshot):
        return {
            "source_type": snapshot.source_type,
            "prediction_date": snapshot.prediction_date,
            "created_at": snapshot.created_at,
            "parent_authority": parent_authority_semantic_payload(snapshot.parent_authority),
        }
    if isinstance(snapshot, Task10ModelArtifactAvailabilitySnapshot):
        return {
            "source_type": snapshot.source_type,
            "created_at": snapshot.created_at,
            "parent_authority": parent_authority_semantic_payload(snapshot.parent_authority),
        }

    raise TypeError(f"unsupported availability snapshot type: {type(snapshot).__name__}")


def availability_snapshot_audit_hash(snapshot: AvailabilitySnapshot) -> str:
    return sha256_payload(canonical_json_value(availability_snapshot_audit_payload(snapshot)))


__all__ = [
    "AVAILABILITY_REGISTRY_VERSION",
    "availability_snapshot_audit_hash",
    "availability_snapshot_audit_payload",
    "build_availability_authority_registry",
    "evaluate_authority_visibility",
    "get_availability_authority_spec",
    "parent_authority_audit_hash",
    "parent_authority_semantic_payload",
]
