from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

from backend.app.rolling_backtest.availability import (
    build_availability_authority_registry,
    evaluate_authority_visibility,
    get_availability_authority_spec,
)
from backend.app.rolling_backtest.enums import AvailabilitySourceType, ExecutionMode
from backend.app.rolling_backtest.schemas import AvailabilityAuthoritySnapshot


def _golden_path(name: str) -> Path:
    return Path(__file__).parent / "golden" / name


def test_availability_registry_matches_golden() -> None:
    payload = json.loads(_golden_path("availability_registry.json").read_text(encoding="utf-8"))
    registry = build_availability_authority_registry()
    assert [item.model_dump(mode="json") for item in registry] == payload


def test_authority_registry_is_complete() -> None:
    expected = {
        "task3_analytics_build",
        "task6_plan_version",
        "task7_weather_observation",
        "task8_model_run",
        "task8_model_artifact",
        "task8_forecast_run",
        "task8_daily_prediction",
        "task9_harvest_state_run",
        "task10_training_run",
        "task10_model_artifact",
        "task10_prediction_run",
    }
    assert {item.source_type.value for item in build_availability_authority_registry()} == expected


def test_historical_observed_cutoff_passes() -> None:
    snapshot = AvailabilityAuthoritySnapshot(
        source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
        status="completed",
        authoritative_timestamp=datetime(2026, 3, 15, 11, 0, tzinfo=UTC),
    )
    result = evaluate_authority_visibility(
        snapshot=snapshot,
        execution_mode=ExecutionMode.HISTORICAL_OBSERVED,
        forecast_cutoff_at=datetime(2026, 3, 15, 12, 0, tzinfo=UTC),
    )
    assert result.allowed is True
    assert result.blocker_code is None


def test_historical_observed_cutoff_failure_is_blocked() -> None:
    snapshot = AvailabilityAuthoritySnapshot(
        source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
        status="completed",
        authoritative_timestamp=datetime(2026, 3, 15, 13, 0, tzinfo=UTC),
    )
    result = evaluate_authority_visibility(
        snapshot=snapshot,
        execution_mode=ExecutionMode.HISTORICAL_OBSERVED,
        forecast_cutoff_at=datetime(2026, 3, 15, 12, 0, tzinfo=UTC),
    )
    assert result.allowed is False
    assert result.blocker_code == "AUTHORITATIVE_TIMESTAMP_AFTER_CUTOFF"


def test_replay_execution_after_cutoff_is_allowed_when_source_cutoff_is_visible() -> None:
    snapshot = AvailabilityAuthoritySnapshot(
        source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
        status="completed",
        authoritative_timestamp=datetime(2026, 3, 20, 8, 0, tzinfo=UTC),
        source_cutoff_at=datetime(2026, 2, 28, 23, 0, tzinfo=UTC),
    )
    result = evaluate_authority_visibility(
        snapshot=snapshot,
        execution_mode=ExecutionMode.RETROSPECTIVE_REPLAY,
        forecast_cutoff_at=datetime(2026, 2, 28, 23, 59, tzinfo=UTC),
    )
    assert result.allowed is True
    assert result.blocker_code is None


def test_task10_prediction_completed_at_missing_is_rejected() -> None:
    snapshot = AvailabilityAuthoritySnapshot(
        source_type=AvailabilitySourceType.TASK10_PREDICTION_RUN,
        status="completed",
        authoritative_timestamp=None,
    )
    result = evaluate_authority_visibility(
        snapshot=snapshot,
        execution_mode=ExecutionMode.HISTORICAL_OBSERVED,
        forecast_cutoff_at=datetime(2026, 3, 15, 12, 0, tzinfo=UTC),
    )
    assert result.allowed is False
    assert result.blocker_code == "MISSING_AUTHORITATIVE_TIMESTAMP"


def test_parent_authority_is_required() -> None:
    spec = get_availability_authority_spec(AvailabilitySourceType.TASK8_MODEL_ARTIFACT)
    assert spec.parent_authority_required is True


def test_observation_date_after_cutoff_is_rejected() -> None:
    snapshot = AvailabilityAuthoritySnapshot(
        source_type=AvailabilitySourceType.TASK7_WEATHER_OBSERVATION,
        status="completed",
        authoritative_timestamp=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
        observation_date=date(2026, 3, 1),
    )
    result = evaluate_authority_visibility(
        snapshot=snapshot,
        execution_mode=ExecutionMode.RETROSPECTIVE_REPLAY,
        forecast_cutoff_at=datetime(2026, 2, 28, 23, 59, tzinfo=UTC),
    )
    assert result.allowed is False
    assert result.blocker_code == "OBSERVATION_DATE_AFTER_CUTOFF"
