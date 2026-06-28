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
    AvailabilityAuthoritySnapshot,
    Task3SourceVisibilityIdentity,
)


def _golden_path(name: str) -> Path:
    return Path(__file__).parent / "golden" / name


def _evaluate(snapshot: AvailabilityAuthoritySnapshot, *, mode: ExecutionMode) -> object:
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


def test_availability_registry_matches_golden() -> None:
    payload = json.loads(_golden_path("availability_registry.json").read_text(encoding="utf-8"))
    registry = build_availability_authority_registry()
    assert [item.model_dump(mode="json") for item in registry] == payload


def test_authority_registry_is_complete_and_unique() -> None:
    registry = build_availability_authority_registry()
    assert {item.source_type for item in registry} == set(AvailabilitySourceType)
    assert len(registry) == len(set(item.source_type for item in registry))


def test_task3_historical_observed_requires_finished_at() -> None:
    snapshot = AvailabilityAuthoritySnapshot(
        source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
        status="completed",
        authoritative_timestamp=datetime(2026, 2, 28, 15, 0, tzinfo=UTC),
    )
    result = _evaluate(snapshot, mode=ExecutionMode.HISTORICAL_OBSERVED)
    assert result.allowed is True


def test_replay_execution_after_cutoff_is_allowed_with_typed_task3_visibility() -> None:
    snapshot = AvailabilityAuthoritySnapshot(
        source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
        status="completed",
        authoritative_timestamp=datetime(2026, 3, 20, 8, 0, tzinfo=UTC),
        task3_source_visibility=_task3_visibility(),
    )
    result = _evaluate(snapshot, mode=ExecutionMode.RETROSPECTIVE_REPLAY)
    assert result.allowed is True
    assert result.blocker_code is None


def test_task10_prediction_source_cutoff_cannot_bypass_missing_completed_at() -> None:
    snapshot = AvailabilityAuthoritySnapshot(
        source_type=AvailabilitySourceType.TASK10_PREDICTION_RUN,
        status="completed",
        source_cutoff_at=datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
    )
    result = _evaluate(snapshot, mode=ExecutionMode.RETROSPECTIVE_REPLAY)
    assert result.allowed is False
    assert result.blocker_code == "FORBIDDEN_FIELD_PRESENT"


def test_task8_artifact_requires_explicit_parent_authority() -> None:
    snapshot = AvailabilityAuthoritySnapshot(
        source_type=AvailabilitySourceType.TASK8_MODEL_ARTIFACT,
        status="completed",
        authoritative_timestamp=datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
        parent_authority_valid=None,
    )
    result = _evaluate(snapshot, mode=ExecutionMode.HISTORICAL_OBSERVED)
    assert result.allowed is False
    assert result.blocker_code == "PARENT_AUTHORITY_REQUIRED"


def test_required_observation_date_missing_is_blocked() -> None:
    snapshot = AvailabilityAuthoritySnapshot(
        source_type=AvailabilitySourceType.TASK7_WEATHER_OBSERVATION,
        status="completed",
        available_on_local_date=date(2026, 2, 28),
    )
    result = _evaluate(snapshot, mode=ExecutionMode.RETROSPECTIVE_REPLAY)
    assert result.allowed is False
    assert result.blocker_code == "REQUIRED_FIELD_MISSING"


def test_task3_required_source_visibility_missing_is_blocked() -> None:
    snapshot = AvailabilityAuthoritySnapshot(
        source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
        status="completed",
        authoritative_timestamp=datetime(2026, 3, 20, 8, 0, tzinfo=UTC),
    )
    result = _evaluate(snapshot, mode=ExecutionMode.RETROSPECTIVE_REPLAY)
    assert result.allowed is False
    assert result.blocker_code == "SOURCE_VISIBILITY_MISSING"


def test_source_cutoff_is_rejected_for_non_source_cutoff_rule() -> None:
    snapshot = AvailabilityAuthoritySnapshot(
        source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
        status="completed",
        authoritative_timestamp=datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
        source_cutoff_at=datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
    )
    result = _evaluate(snapshot, mode=ExecutionMode.HISTORICAL_OBSERVED)
    assert result.allowed is False
    assert result.blocker_code == "FORBIDDEN_FIELD_PRESENT"


def test_plan_available_date_uses_explicit_local_date_policy() -> None:
    spec = get_availability_authority_spec(AvailabilitySourceType.TASK6_PLAN_VERSION)
    assert spec.rule_kind == AvailabilityRuleKind.LOCAL_AVAILABLE_DATE
    assert spec.local_date_policy_version == "task11-local-date-visibility-v1"

    snapshot = AvailabilityAuthoritySnapshot(
        source_type=AvailabilitySourceType.TASK6_PLAN_VERSION,
        status="completed",
        available_on_local_date=date(2026, 3, 1),
    )
    result = _evaluate(snapshot, mode=ExecutionMode.HISTORICAL_OBSERVED)
    assert result.allowed is False
    assert result.blocker_code == "AVAILABLE_ON_LOCAL_DATE_AFTER_AS_OF"


def test_weather_requires_observation_and_available_date() -> None:
    snapshot = AvailabilityAuthoritySnapshot(
        source_type=AvailabilitySourceType.TASK7_WEATHER_OBSERVATION,
        status="completed",
        available_on_local_date=date(2026, 2, 28),
        observation_date=date(2026, 3, 1),
    )
    result = _evaluate(snapshot, mode=ExecutionMode.RETROSPECTIVE_REPLAY)
    assert result.allowed is False
    assert result.blocker_code == "OBSERVATION_DATE_AFTER_CUTOFF"


def test_task10_prediction_completed_at_missing_is_rejected() -> None:
    snapshot = AvailabilityAuthoritySnapshot(
        source_type=AvailabilitySourceType.TASK10_PREDICTION_RUN,
        status="completed",
    )
    result = _evaluate(snapshot, mode=ExecutionMode.HISTORICAL_OBSERVED)
    assert result.allowed is False
    assert result.blocker_code == "MISSING_AUTHORITATIVE_TIMESTAMP"
