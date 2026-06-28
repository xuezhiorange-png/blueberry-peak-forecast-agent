from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

from backend.app.rolling_backtest.availability import (
    build_availability_authority_registry,
    evaluate_authority_visibility,
    get_availability_authority_spec,
)
from backend.app.rolling_backtest.enums import (
    AvailabilityRuleKind,
    AvailabilitySourceType,
    ExecutionMode,
)
from backend.app.rolling_backtest.schemas import (
    AvailabilityAuthorityEvaluationResult,
    AvailabilitySnapshot,
    ParentAuthorityIdentity,
    Task3AnalyticsBuildAvailabilitySnapshot,
    Task3SourceVisibilityIdentity,
    Task6PlanVersionAvailabilitySnapshot,
    Task7WeatherObservationAvailabilitySnapshot,
    Task8DailyPredictionAvailabilitySnapshot,
    Task8ModelArtifactAvailabilitySnapshot,
    Task8ModelRunAvailabilitySnapshot,
    Task9HarvestStateRunAvailabilitySnapshot,
    Task10PredictionRunAvailabilitySnapshot,
)


def _golden_path(name: str) -> Path:
    return Path(__file__).parent / "golden" / name


def _evaluate(
    snapshot: AvailabilitySnapshot, *, mode: ExecutionMode
) -> AvailabilityAuthorityEvaluationResult:
    return evaluate_authority_visibility(
        snapshot=snapshot,
        execution_mode=mode,
        forecast_cutoff_at=datetime(2026, 2, 28, 15, 59, 59, tzinfo=UTC),
        as_of_local_date=date(2026, 2, 28),
        business_timezone="Asia/Shanghai",
    )


def _task3_visibility(
    *,
    visible_through_at: datetime = datetime(2026, 2, 28, 15, 0, tzinfo=UTC),
) -> Task3SourceVisibilityIdentity:
    return Task3SourceVisibilityIdentity(
        visibility_policy_version="task11-task3-source-visibility-v1",
        source_max_raw_id=123,
        aggregation_version="task3-v1",
        config_hash="1" * 64,
        visibility_manifest_hash="2" * 64,
        visible_through_at=visible_through_at,
    )


def _parent_run(
    *,
    source_type: AvailabilitySourceType = AvailabilitySourceType.TASK8_MODEL_RUN,
    timestamp: datetime = datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
    status: str = "completed",
) -> ParentAuthorityIdentity:
    return ParentAuthorityIdentity(
        source_type=source_type,
        authority_timestamp=timestamp,
        authority_status=status,
    )


def test_availability_registry_matches_golden() -> None:
    payload = json.loads(_golden_path("availability_registry.json").read_text(encoding="utf-8"))
    registry = build_availability_authority_registry()
    assert [item.model_dump(mode="json") for item in registry] == payload


def test_authority_registry_is_complete_and_unique() -> None:
    registry = build_availability_authority_registry()
    assert {item.source_type for item in registry} == set(AvailabilitySourceType)
    assert len(registry) == len(set(item.source_type for item in registry))


# ── Task 3 tests ────────────────────────────────────────────────────────────


def test_task3_historical_observed_requires_finished_at() -> None:
    snapshot = Task3AnalyticsBuildAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
        status="completed",
        authoritative_timestamp=datetime(2026, 2, 28, 15, 0, tzinfo=UTC),
        task3_source_visibility=_task3_visibility(),
    )
    result = _evaluate(snapshot, mode=ExecutionMode.HISTORICAL_OBSERVED)
    assert result.allowed is True


def test_task3_historical_requires_source_visibility() -> None:
    snapshot = Task3AnalyticsBuildAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
        status="completed",
        authoritative_timestamp=datetime(2026, 2, 28, 15, 0, tzinfo=UTC),
    )
    result = _evaluate(snapshot, mode=ExecutionMode.HISTORICAL_OBSERVED)
    assert result.allowed is False
    assert result.blocker_code == "SOURCE_VISIBILITY_MISSING"


def test_task3_historical_visibility_after_cutoff_is_blocked() -> None:
    snapshot = Task3AnalyticsBuildAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
        status="completed",
        authoritative_timestamp=datetime(2026, 2, 28, 15, 0, tzinfo=UTC),
        task3_source_visibility=_task3_visibility(
            visible_through_at=datetime(2026, 6, 1, 0, 0, tzinfo=UTC),
        ),
    )
    result = _evaluate(snapshot, mode=ExecutionMode.HISTORICAL_OBSERVED)
    assert result.allowed is False
    assert result.blocker_code == "SOURCE_CUTOFF_AFTER_FORECAST_CUTOFF"


def test_task3_historical_wrong_visibility_policy_is_blocked() -> None:
    visibility = _task3_visibility()
    visibility.visibility_policy_version = "wrong-version"
    snapshot = Task3AnalyticsBuildAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
        status="completed",
        authoritative_timestamp=datetime(2026, 2, 28, 15, 0, tzinfo=UTC),
        task3_source_visibility=visibility,
    )
    result = _evaluate(snapshot, mode=ExecutionMode.HISTORICAL_OBSERVED)
    assert result.allowed is False
    assert result.blocker_code == "SOURCE_VISIBILITY_MISSING"


def test_replay_execution_after_cutoff_is_allowed_with_typed_task3_visibility() -> None:
    snapshot = Task3AnalyticsBuildAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
        status="completed",
        authoritative_timestamp=datetime(2026, 3, 20, 8, 0, tzinfo=UTC),
        task3_source_visibility=_task3_visibility(),
    )
    result = _evaluate(snapshot, mode=ExecutionMode.RETROSPECTIVE_REPLAY)
    assert result.allowed is True
    assert result.blocker_code is None


def test_task3_replay_missing_visibility_is_blocked() -> None:
    snapshot = Task3AnalyticsBuildAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
        status="completed",
        authoritative_timestamp=datetime(2026, 3, 20, 8, 0, tzinfo=UTC),
    )
    result = _evaluate(snapshot, mode=ExecutionMode.RETROSPECTIVE_REPLAY)
    assert result.allowed is False
    assert result.blocker_code == "SOURCE_VISIBILITY_MISSING"


def test_task3_replay_visibility_after_cutoff_is_blocked() -> None:
    snapshot = Task3AnalyticsBuildAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
        status="completed",
        authoritative_timestamp=datetime(2026, 3, 20, 8, 0, tzinfo=UTC),
        task3_source_visibility=_task3_visibility(
            visible_through_at=datetime(2026, 6, 1, 0, 0, tzinfo=UTC),
        ),
    )
    result = _evaluate(snapshot, mode=ExecutionMode.RETROSPECTIVE_REPLAY)
    assert result.allowed is False
    assert result.blocker_code == "SOURCE_CUTOFF_AFTER_FORECAST_CUTOFF"


def test_task3_replay_wrong_visibility_policy_is_blocked() -> None:
    visibility = _task3_visibility()
    visibility.visibility_policy_version = "wrong-version"
    snapshot = Task3AnalyticsBuildAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
        status="completed",
        authoritative_timestamp=datetime(2026, 3, 20, 8, 0, tzinfo=UTC),
        task3_source_visibility=visibility,
    )
    result = _evaluate(snapshot, mode=ExecutionMode.RETROSPECTIVE_REPLAY)
    assert result.allowed is False
    assert result.blocker_code == "SOURCE_VISIBILITY_MISSING"


def test_task3_replay_execution_after_cutoff_is_allowed_when_source_visible() -> None:
    snapshot = Task3AnalyticsBuildAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
        status="completed",
        authoritative_timestamp=datetime(2026, 3, 20, 8, 0, tzinfo=UTC),
        task3_source_visibility=_task3_visibility(
            visible_through_at=datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
        ),
    )
    result = _evaluate(snapshot, mode=ExecutionMode.RETROSPECTIVE_REPLAY)
    assert result.allowed is True


# ── P0-2: Typed snapshot tests ──────────────────────────────────────────────


def test_plan_snapshot_rejects_status() -> None:
    """Task 6 plan has no status field."""
    snapshot = Task6PlanVersionAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK6_PLAN_VERSION,
        available_at=date(2026, 2, 28),
        effective_interval_version="plan-interval-v1",
    )
    result = _evaluate(snapshot, mode=ExecutionMode.HISTORICAL_OBSERVED)
    assert result.allowed is True


def test_weather_snapshot_rejects_status() -> None:
    """Task 7 weather has no status field."""
    snapshot = Task7WeatherObservationAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK7_WEATHER_OBSERVATION,
        available_at=date(2026, 2, 28),
        observation_date=date(2026, 2, 28),
    )
    result = _evaluate(snapshot, mode=ExecutionMode.HISTORICAL_OBSERVED)
    assert result.allowed is True


def test_artifact_snapshot_requires_typed_parent_authority() -> None:
    """Task 8 model artifact must have typed parent authority — not a bare bool."""
    snapshot = Task8ModelArtifactAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK8_MODEL_ARTIFACT,
        created_at=datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
        parent_authority=_parent_run(),
    )
    result = _evaluate(snapshot, mode=ExecutionMode.HISTORICAL_OBSERVED)
    assert result.allowed is True


def test_artifact_parent_not_completed_is_blocked() -> None:
    snapshot = Task8ModelArtifactAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK8_MODEL_ARTIFACT,
        created_at=datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
        parent_authority=_parent_run(status="running"),
    )
    result = _evaluate(snapshot, mode=ExecutionMode.HISTORICAL_OBSERVED)
    assert result.allowed is False
    assert result.blocker_code == "PARENT_AUTHORITY_REQUIRED"


def test_daily_prediction_requires_parent_forecast_authority() -> None:
    """Task 8 daily prediction must have typed parent forecast-run authority."""
    snapshot = Task8DailyPredictionAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK8_DAILY_PREDICTION,
        prediction_date=date(2026, 2, 28),
        created_at=datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
        parent_authority=_parent_run(
            source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
        ),
    )
    result = _evaluate(snapshot, mode=ExecutionMode.HISTORICAL_OBSERVED)
    assert result.allowed is True


def test_run_snapshot_requires_real_execution_status() -> None:
    """Run types (Task 8 model run) require real execution status."""
    snapshot = Task8ModelRunAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK8_MODEL_RUN,
        status="completed",
        authoritative_timestamp=datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
    )
    result = _evaluate(snapshot, mode=ExecutionMode.HISTORICAL_OBSERVED)
    assert result.allowed is True


def test_source_specific_snapshot_rejects_unrelated_fields() -> None:
    """Plan snapshot cannot have a 'status' field at all — Pydantic rejects extras."""
    import pytest

    with pytest.raises(ValueError):
        Task6PlanVersionAvailabilitySnapshot(
            source_type=AvailabilitySourceType.TASK6_PLAN_VERSION,
            available_at=date(2026, 2, 28),
            effective_interval_version="plan-interval-v1",
            status="completed",  # type: ignore[call-arg]
        )


# ── Existing behavior tests updated to typed snapshots ─────────────────────


def test_task10_prediction_completed_at_missing_is_rejected() -> None:
    """Task 10 prediction run requires authoritative timestamp."""
    snapshot = Task10PredictionRunAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK10_PREDICTION_RUN,
        status="completed",
        authoritative_timestamp=datetime(2026, 3, 20, 10, 0, tzinfo=UTC),
    )
    result = _evaluate(snapshot, mode=ExecutionMode.HISTORICAL_OBSERVED)
    assert result.allowed is False
    assert result.blocker_code == "AUTHORITATIVE_TIMESTAMP_AFTER_CUTOFF"


def test_plan_available_date_uses_explicit_local_date_policy() -> None:
    spec = get_availability_authority_spec(AvailabilitySourceType.TASK6_PLAN_VERSION)
    assert spec.rule_kind == AvailabilityRuleKind.LOCAL_AVAILABLE_DATE
    assert spec.local_date_policy_version == "task11-local-date-visibility-v1"

    snapshot = Task6PlanVersionAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK6_PLAN_VERSION,
        available_at=date(2026, 3, 1),
        effective_interval_version="plan-interval-v1",
    )
    result = _evaluate(snapshot, mode=ExecutionMode.HISTORICAL_OBSERVED)
    assert result.allowed is False
    assert result.blocker_code == "AVAILABLE_ON_LOCAL_DATE_AFTER_AS_OF"


def test_weather_requires_observation_and_available_date() -> None:
    snapshot = Task7WeatherObservationAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK7_WEATHER_OBSERVATION,
        available_at=date(2026, 2, 28),
        observation_date=date(2026, 3, 1),
    )
    result = _evaluate(snapshot, mode=ExecutionMode.RETROSPECTIVE_REPLAY)
    assert result.allowed is False
    assert result.blocker_code == "OBSERVATION_DATE_AFTER_CUTOFF"


def test_task9_harvest_state_status_is_checked() -> None:
    snapshot = Task9HarvestStateRunAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
        status="running",
        authoritative_timestamp=datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
    )
    result = _evaluate(snapshot, mode=ExecutionMode.HISTORICAL_OBSERVED)
    assert result.allowed is False
    assert result.blocker_code == "STATUS_NOT_ALLOWED"
