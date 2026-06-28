from __future__ import annotations

from datetime import datetime

from backend.app.rolling_backtest.enums import (
    AVAILABILITY_REGISTRY_VERSION,
    AvailabilityBlockerCode,
    AvailabilitySourceType,
    ExecutionMode,
)
from backend.app.rolling_backtest.schemas import (
    AvailabilityAuthorityEvaluationResult,
    AvailabilityAuthoritySnapshot,
    AvailabilityAuthoritySpec,
)


def build_availability_authority_registry() -> tuple[AvailabilityAuthoritySpec, ...]:
    return (
        AvailabilityAuthoritySpec(
            source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
            required_statuses=("completed",),
            authoritative_timestamp_field="finished_at",
            parent_authority_required=False,
            observation_date_field=None,
            source_cutoff_field="source_cutoff_at",
            historical_observed_rule="authoritative_timestamp_lte_forecast_cutoff",
            retrospective_replay_rule="source_cutoff_lte_forecast_cutoff",
        ),
        AvailabilityAuthoritySpec(
            source_type=AvailabilitySourceType.TASK6_PLAN_VERSION,
            required_statuses=("completed",),
            authoritative_timestamp_field="available_at",
            parent_authority_required=False,
            observation_date_field=None,
            source_cutoff_field=None,
            historical_observed_rule="authoritative_timestamp_lte_forecast_cutoff",
            retrospective_replay_rule="authoritative_timestamp_lte_forecast_cutoff",
        ),
        AvailabilityAuthoritySpec(
            source_type=AvailabilitySourceType.TASK7_WEATHER_OBSERVATION,
            required_statuses=("completed",),
            authoritative_timestamp_field="available_at",
            parent_authority_required=False,
            observation_date_field="observation_date",
            source_cutoff_field=None,
            historical_observed_rule="authoritative_timestamp_lte_forecast_cutoff",
            retrospective_replay_rule=("observation_date_and_authority_lte_forecast_cutoff"),
        ),
        AvailabilityAuthoritySpec(
            source_type=AvailabilitySourceType.TASK8_MODEL_RUN,
            required_statuses=("completed", "unavailable"),
            authoritative_timestamp_field="finished_at",
            parent_authority_required=False,
            observation_date_field=None,
            source_cutoff_field=None,
            historical_observed_rule="authoritative_timestamp_lte_forecast_cutoff",
            retrospective_replay_rule="authoritative_timestamp_lte_forecast_cutoff",
        ),
        AvailabilityAuthoritySpec(
            source_type=AvailabilitySourceType.TASK8_MODEL_ARTIFACT,
            required_statuses=("completed",),
            authoritative_timestamp_field="created_at",
            parent_authority_required=True,
            observation_date_field=None,
            source_cutoff_field=None,
            historical_observed_rule="authoritative_timestamp_lte_forecast_cutoff",
            retrospective_replay_rule="authoritative_timestamp_lte_forecast_cutoff",
        ),
        AvailabilityAuthoritySpec(
            source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
            required_statuses=("completed", "unavailable"),
            authoritative_timestamp_field="finished_at",
            parent_authority_required=False,
            observation_date_field=None,
            source_cutoff_field=None,
            historical_observed_rule="authoritative_timestamp_lte_forecast_cutoff",
            retrospective_replay_rule="authoritative_timestamp_lte_forecast_cutoff",
        ),
        AvailabilityAuthoritySpec(
            source_type=AvailabilitySourceType.TASK8_DAILY_PREDICTION,
            required_statuses=("completed",),
            authoritative_timestamp_field="created_at",
            parent_authority_required=True,
            observation_date_field="prediction_date",
            source_cutoff_field=None,
            historical_observed_rule="authoritative_timestamp_lte_forecast_cutoff",
            retrospective_replay_rule="authoritative_timestamp_lte_forecast_cutoff",
        ),
        AvailabilityAuthoritySpec(
            source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
            required_statuses=("completed", "blocked"),
            authoritative_timestamp_field="created_at",
            parent_authority_required=False,
            observation_date_field=None,
            source_cutoff_field=None,
            historical_observed_rule="authoritative_timestamp_lte_forecast_cutoff",
            retrospective_replay_rule="authoritative_timestamp_lte_forecast_cutoff",
        ),
        AvailabilityAuthoritySpec(
            source_type=AvailabilitySourceType.TASK10_TRAINING_RUN,
            required_statuses=("completed", "blocked", "failed"),
            authoritative_timestamp_field="finished_at",
            parent_authority_required=False,
            observation_date_field=None,
            source_cutoff_field=None,
            historical_observed_rule="authoritative_timestamp_lte_forecast_cutoff",
            retrospective_replay_rule="authoritative_timestamp_lte_forecast_cutoff",
        ),
        AvailabilityAuthoritySpec(
            source_type=AvailabilitySourceType.TASK10_MODEL_ARTIFACT,
            required_statuses=("completed",),
            authoritative_timestamp_field="created_at",
            parent_authority_required=True,
            observation_date_field=None,
            source_cutoff_field=None,
            historical_observed_rule="authoritative_timestamp_lte_forecast_cutoff",
            retrospective_replay_rule="authoritative_timestamp_lte_forecast_cutoff",
        ),
        AvailabilityAuthoritySpec(
            source_type=AvailabilitySourceType.TASK10_PREDICTION_RUN,
            required_statuses=("completed", "blocked", "failed"),
            authoritative_timestamp_field="completed_at",
            parent_authority_required=False,
            observation_date_field=None,
            source_cutoff_field=None,
            historical_observed_rule="authoritative_timestamp_lte_forecast_cutoff",
            retrospective_replay_rule=(
                "authoritative_timestamp_or_source_visibility_lte_forecast_cutoff"
            ),
        ),
    )


_REGISTRY = {item.source_type: item for item in build_availability_authority_registry()}


def get_availability_authority_spec(
    source_type: AvailabilitySourceType,
) -> AvailabilityAuthoritySpec:
    return _REGISTRY[source_type]


def _blocked(code: AvailabilityBlockerCode) -> AvailabilityAuthorityEvaluationResult:
    return AvailabilityAuthorityEvaluationResult(allowed=False, blocker_code=code.value)


def _observation_date_ok(
    snapshot: AvailabilityAuthoritySnapshot,
    *,
    forecast_cutoff_at: datetime,
) -> bool:
    return (
        snapshot.observation_date is None or snapshot.observation_date <= forecast_cutoff_at.date()
    )


def evaluate_authority_visibility(
    *,
    snapshot: AvailabilityAuthoritySnapshot,
    execution_mode: ExecutionMode,
    forecast_cutoff_at: datetime,
) -> AvailabilityAuthorityEvaluationResult:
    spec = get_availability_authority_spec(snapshot.source_type)
    if snapshot.status not in spec.required_statuses:
        return _blocked(AvailabilityBlockerCode.STATUS_NOT_ALLOWED)
    if spec.parent_authority_required and not snapshot.parent_authority_valid:
        return _blocked(AvailabilityBlockerCode.PARENT_AUTHORITY_REQUIRED)
    if not _observation_date_ok(snapshot, forecast_cutoff_at=forecast_cutoff_at):
        return _blocked(AvailabilityBlockerCode.OBSERVATION_DATE_AFTER_CUTOFF)

    if execution_mode == ExecutionMode.HISTORICAL_OBSERVED:
        if snapshot.authoritative_timestamp is None:
            return _blocked(AvailabilityBlockerCode.MISSING_AUTHORITATIVE_TIMESTAMP)
        if snapshot.authoritative_timestamp > forecast_cutoff_at:
            return _blocked(AvailabilityBlockerCode.AUTHORITATIVE_TIMESTAMP_AFTER_CUTOFF)
        return AvailabilityAuthorityEvaluationResult(allowed=True, blocker_code=None)

    if snapshot.source_cutoff_at is not None:
        if snapshot.source_cutoff_at > forecast_cutoff_at:
            return _blocked(AvailabilityBlockerCode.SOURCE_CUTOFF_AFTER_FORECAST_CUTOFF)
        return AvailabilityAuthorityEvaluationResult(allowed=True, blocker_code=None)

    if snapshot.authoritative_timestamp is None:
        return _blocked(AvailabilityBlockerCode.MISSING_AUTHORITATIVE_TIMESTAMP)
    if snapshot.authoritative_timestamp > forecast_cutoff_at:
        return _blocked(AvailabilityBlockerCode.AUTHORITATIVE_TIMESTAMP_AFTER_CUTOFF)
    return AvailabilityAuthorityEvaluationResult(allowed=True, blocker_code=None)


__all__ = [
    "AVAILABILITY_REGISTRY_VERSION",
    "build_availability_authority_registry",
    "evaluate_authority_visibility",
    "get_availability_authority_spec",
]
