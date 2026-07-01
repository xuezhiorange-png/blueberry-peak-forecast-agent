from __future__ import annotations

from backend.app.rolling_backtest.enums import (
    EvaluationStatus,
    ExecutionMode,
    ForecastStatus,
    RunDerivedStatus,
    UpstreamSelectionMode,
)


def test_execution_mode_vocabulary() -> None:
    assert tuple(item.value for item in ExecutionMode) == (
        "historical_observed",
        "retrospective_replay",
    )


def test_forecast_status_vocabulary() -> None:
    assert tuple(item.value for item in ForecastStatus) == (
        "pending",
        "running",
        "completed",
        "blocked",
        "failed",
    )


def test_evaluation_status_vocabulary() -> None:
    assert tuple(item.value for item in EvaluationStatus) == (
        "not_ready",
        "pending",
        "running",
        "completed",
        "blocked",
        "failed",
    )


def test_run_derived_status_vocabulary() -> None:
    assert tuple(item.value for item in RunDerivedStatus) == (
        "pending",
        "running",
        "forecast_completed",
        "partially_completed",
        "completed",
        "blocked",
        "failed",
    )


def test_upstream_selection_mode_vocabulary() -> None:
    assert tuple(item.value for item in UpstreamSelectionMode) == (
        "pinned",
        "historical_resolution",
    )
