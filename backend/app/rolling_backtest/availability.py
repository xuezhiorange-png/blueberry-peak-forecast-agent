from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from backend.app.rolling_backtest.enums import (
    AVAILABILITY_REGISTRY_VERSION,
    AvailabilityBlockerCode,
    AvailabilityRuleKind,
    AvailabilitySourceType,
    ExecutionMode,
)
from backend.app.rolling_backtest.schemas import (
    AvailabilityAuthorityEvaluationResult,
    AvailabilityAuthoritySnapshot,
    AvailabilityAuthoritySpec,
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
            required_statuses=("completed",),
            available_on_local_date_field="available_at",
            parent_authority_required=False,
            local_date_policy_version=_LOCAL_AVAILABLE_DATE_POLICY_VERSION,
        ),
        AvailabilityAuthoritySpec(
            source_type=AvailabilitySourceType.TASK7_WEATHER_OBSERVATION,
            rule_kind=AvailabilityRuleKind.LOCAL_AVAILABLE_DATE_WITH_OBSERVATION_DATE,
            required_statuses=("completed",),
            available_on_local_date_field="available_at",
            observation_date_field="observation_date",
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
            required_statuses=("completed",),
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
            required_statuses=("completed",),
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
            required_statuses=("completed",),
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


def _validate_parent_authority(
    *,
    snapshot: AvailabilityAuthoritySnapshot,
    spec: AvailabilityAuthoritySpec,
) -> AvailabilityAuthorityEvaluationResult | None:
    if spec.parent_authority_required:
        if snapshot.parent_authority_valid is not True:
            return _blocked(AvailabilityBlockerCode.PARENT_AUTHORITY_REQUIRED)
    elif snapshot.parent_authority_valid is not None:
        return _blocked(AvailabilityBlockerCode.FORBIDDEN_FIELD_PRESENT)
    return None


def _validate_forbidden_fields(
    *,
    snapshot: AvailabilityAuthoritySnapshot,
    spec: AvailabilityAuthoritySpec,
) -> AvailabilityAuthorityEvaluationResult | None:
    if snapshot.source_cutoff_at is not None:
        return _blocked(AvailabilityBlockerCode.FORBIDDEN_FIELD_PRESENT)
    if (
        spec.rule_kind != AvailabilityRuleKind.TASK3_SOURCE_VISIBILITY
        and snapshot.task3_source_visibility is not None
    ):
        return _blocked(AvailabilityBlockerCode.FORBIDDEN_FIELD_PRESENT)
    if spec.available_on_local_date_field is None and snapshot.available_on_local_date is not None:
        return _blocked(AvailabilityBlockerCode.FORBIDDEN_FIELD_PRESENT)
    if spec.observation_date_field is None and snapshot.observation_date is not None:
        return _blocked(AvailabilityBlockerCode.FORBIDDEN_FIELD_PRESENT)
    if spec.authoritative_timestamp_field is None and snapshot.authoritative_timestamp is not None:
        return _blocked(AvailabilityBlockerCode.FORBIDDEN_FIELD_PRESENT)
    return None


def _validate_observation_date(
    observation_date: date | None,
    *,
    as_of_local_date: date,
) -> AvailabilityAuthorityEvaluationResult | None:
    if observation_date is None:
        return _blocked(AvailabilityBlockerCode.REQUIRED_FIELD_MISSING)
    if observation_date > as_of_local_date:
        return _blocked(AvailabilityBlockerCode.OBSERVATION_DATE_AFTER_CUTOFF)
    return None


def _validate_local_available_date(
    available_on_local_date: date | None,
    *,
    as_of_local_date: date,
) -> AvailabilityAuthorityEvaluationResult | None:
    if available_on_local_date is None:
        return _blocked(AvailabilityBlockerCode.REQUIRED_FIELD_MISSING)
    if available_on_local_date > as_of_local_date:
        return _blocked(AvailabilityBlockerCode.AVAILABLE_ON_LOCAL_DATE_AFTER_AS_OF)
    return None


def _validate_authoritative_timestamp(
    authoritative_timestamp: datetime | None,
    *,
    forecast_cutoff_at: datetime,
) -> AvailabilityAuthorityEvaluationResult | None:
    if authoritative_timestamp is None:
        return _blocked(AvailabilityBlockerCode.MISSING_AUTHORITATIVE_TIMESTAMP)
    if authoritative_timestamp > forecast_cutoff_at:
        return _blocked(AvailabilityBlockerCode.AUTHORITATIVE_TIMESTAMP_AFTER_CUTOFF)
    return None


def evaluate_authority_visibility(
    *,
    snapshot: AvailabilityAuthoritySnapshot,
    execution_mode: ExecutionMode,
    forecast_cutoff_at: datetime,
    as_of_local_date: date,
    business_timezone: str,
) -> AvailabilityAuthorityEvaluationResult:
    ZoneInfo(business_timezone)
    spec = get_availability_authority_spec(snapshot.source_type)
    if snapshot.status not in spec.required_statuses:
        return _blocked(AvailabilityBlockerCode.STATUS_NOT_ALLOWED)

    parent_error = _validate_parent_authority(snapshot=snapshot, spec=spec)
    if parent_error is not None:
        return parent_error

    forbidden_error = _validate_forbidden_fields(snapshot=snapshot, spec=spec)
    if forbidden_error is not None:
        return forbidden_error

    if spec.rule_kind == AvailabilityRuleKind.AUTHORITATIVE_TIMESTAMP:
        result = _validate_authoritative_timestamp(
            snapshot.authoritative_timestamp,
            forecast_cutoff_at=forecast_cutoff_at,
        )
        return result or AvailabilityAuthorityEvaluationResult(allowed=True, blocker_code=None)

    if spec.rule_kind == AvailabilityRuleKind.AUTHORITATIVE_WITH_OBSERVATION_DATE:
        observation_error = _validate_observation_date(
            snapshot.observation_date,
            as_of_local_date=as_of_local_date,
        )
        if observation_error is not None:
            return observation_error
        result = _validate_authoritative_timestamp(
            snapshot.authoritative_timestamp,
            forecast_cutoff_at=forecast_cutoff_at,
        )
        return result or AvailabilityAuthorityEvaluationResult(allowed=True, blocker_code=None)

    if spec.rule_kind == AvailabilityRuleKind.LOCAL_AVAILABLE_DATE:
        result = _validate_local_available_date(
            snapshot.available_on_local_date,
            as_of_local_date=as_of_local_date,
        )
        return result or AvailabilityAuthorityEvaluationResult(allowed=True, blocker_code=None)

    if spec.rule_kind == AvailabilityRuleKind.LOCAL_AVAILABLE_DATE_WITH_OBSERVATION_DATE:
        available_error = _validate_local_available_date(
            snapshot.available_on_local_date,
            as_of_local_date=as_of_local_date,
        )
        if available_error is not None:
            return available_error
        observation_error = _validate_observation_date(
            snapshot.observation_date,
            as_of_local_date=as_of_local_date,
        )
        return observation_error or AvailabilityAuthorityEvaluationResult(
            allowed=True,
            blocker_code=None,
        )

    if spec.rule_kind == AvailabilityRuleKind.TASK3_SOURCE_VISIBILITY:
        if execution_mode == ExecutionMode.HISTORICAL_OBSERVED:
            result = _validate_authoritative_timestamp(
                snapshot.authoritative_timestamp,
                forecast_cutoff_at=forecast_cutoff_at,
            )
            return result or AvailabilityAuthorityEvaluationResult(allowed=True, blocker_code=None)

        if snapshot.task3_source_visibility is None:
            return _blocked(AvailabilityBlockerCode.SOURCE_VISIBILITY_MISSING)
        if snapshot.task3_source_visibility.visible_through_at > forecast_cutoff_at:
            return _blocked(AvailabilityBlockerCode.SOURCE_CUTOFF_AFTER_FORECAST_CUTOFF)
        return AvailabilityAuthorityEvaluationResult(allowed=True, blocker_code=None)

    raise ValueError(f"unsupported availability rule kind: {spec.rule_kind.value}")


_REGISTRY = {item.source_type: item for item in build_availability_authority_registry()}


def get_availability_authority_spec(
    source_type: AvailabilitySourceType,
) -> AvailabilityAuthoritySpec:
    return _REGISTRY[source_type]


def _blocked(code: AvailabilityBlockerCode) -> AvailabilityAuthorityEvaluationResult:
    return AvailabilityAuthorityEvaluationResult(allowed=False, blocker_code=code.value)


__all__ = [
    "AVAILABILITY_REGISTRY_VERSION",
    "build_availability_authority_registry",
    "evaluate_authority_visibility",
    "get_availability_authority_spec",
]
