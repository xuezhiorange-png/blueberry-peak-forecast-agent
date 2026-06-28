from __future__ import annotations

from backend.app.rolling_backtest.config import rolling_backtest_config_hash
from backend.app.rolling_backtest.enums import EvaluationStatus, ForecastStatus, RunDerivedStatus
from backend.app.rolling_backtest.schemas import NodeStateSnapshot, RollingBacktestConfig
from backend.app.rolling_backtest.state import derive_run_status


def test_run_level_state_matrix_failed_wins() -> None:
    result = derive_run_status(
        (
            NodeStateSnapshot(
                forecast_status=ForecastStatus.COMPLETED,
                evaluation_status=EvaluationStatus.COMPLETED,
            ),
            NodeStateSnapshot(
                forecast_status=ForecastStatus.FAILED,
                evaluation_status=EvaluationStatus.FAILED,
            ),
        )
    )
    assert result == RunDerivedStatus.FAILED


def test_run_level_state_matrix_blocked_and_completed_is_partially_completed() -> None:
    result = derive_run_status(
        (
            NodeStateSnapshot(
                forecast_status=ForecastStatus.COMPLETED,
                evaluation_status=EvaluationStatus.NOT_READY,
            ),
            NodeStateSnapshot(
                forecast_status=ForecastStatus.BLOCKED,
                evaluation_status=EvaluationStatus.BLOCKED,
            ),
        )
    )
    assert result == RunDerivedStatus.PARTIALLY_COMPLETED


def test_run_level_state_matrix_all_blocked_is_blocked() -> None:
    result = derive_run_status(
        (
            NodeStateSnapshot(
                forecast_status=ForecastStatus.BLOCKED,
                evaluation_status=EvaluationStatus.BLOCKED,
            ),
            NodeStateSnapshot(
                forecast_status=ForecastStatus.BLOCKED,
                evaluation_status=EvaluationStatus.BLOCKED,
            ),
        )
    )
    assert result == RunDerivedStatus.BLOCKED


def test_run_level_state_matrix_forecast_completed_when_evaluation_not_ready() -> None:
    result = derive_run_status(
        (
            NodeStateSnapshot(
                forecast_status=ForecastStatus.COMPLETED,
                evaluation_status=EvaluationStatus.NOT_READY,
            ),
            NodeStateSnapshot(
                forecast_status=ForecastStatus.COMPLETED,
                evaluation_status=EvaluationStatus.PENDING,
            ),
        )
    )
    assert result == RunDerivedStatus.FORECAST_COMPLETED


def test_run_level_state_matrix_completed_when_all_complete() -> None:
    result = derive_run_status(
        (
            NodeStateSnapshot(
                forecast_status=ForecastStatus.COMPLETED,
                evaluation_status=EvaluationStatus.COMPLETED,
            ),
            NodeStateSnapshot(
                forecast_status=ForecastStatus.COMPLETED,
                evaluation_status=EvaluationStatus.COMPLETED,
            ),
        )
    )
    assert result == RunDerivedStatus.COMPLETED


def test_run_level_state_matrix_running_and_pending() -> None:
    running = derive_run_status(
        (
            NodeStateSnapshot(
                forecast_status=ForecastStatus.RUNNING,
                evaluation_status=EvaluationStatus.PENDING,
            ),
        )
    )
    pending = derive_run_status(
        (
            NodeStateSnapshot(
                forecast_status=ForecastStatus.PENDING,
                evaluation_status=EvaluationStatus.NOT_READY,
            ),
        )
    )
    assert running == RunDerivedStatus.RUNNING
    assert pending == RunDerivedStatus.PENDING


def test_config_hash_is_order_independent_for_nodes() -> None:
    left = RollingBacktestConfig.model_validate(
        {
            "rolling_schema_version": "task11-rolling-v1",
            "canonical_serialization_version": "task11-canonical-v1",
            "availability_registry_version": "task11-availability-v1",
            "node_calendar_version": "task11-calendar-v1",
            "forecast_horizon_policy_version": "task11-horizon-v1",
            "upstream_selection_policy_version": "task11-selection-v1",
            "metric_policy_version": "task11-metrics-v1",
            "task10_model_policy": "historically_available_model",
            "calendar_phase_policy_version": "task11-calendar-phase-v1",
            "cutoff_timezone": "Asia/Shanghai",
            "cutoff_local_time": "12:00:00",
            "nodes": [
                {
                    "season_id": 2026,
                    "node_key": "march_31",
                    "as_of_local_date": "2026-03-31",
                    "forecast_cutoff_at": "2026-03-31T12:00:00Z",
                    "forecast_start_local_date": "2026-04-01",
                    "forecast_end_local_date": "2026-04-07",
                    "destination_factory_ids": [202, 101],
                    "execution_mode": "historical_observed",
                    "upstream_selection_mode": "historical_resolution",
                    "forecast_horizon_policy_version": "task11-horizon-v1",
                    "timezone": "Asia/Shanghai",
                },
                {
                    "season_id": 2026,
                    "node_key": "march_15",
                    "as_of_local_date": "2026-03-15",
                    "forecast_cutoff_at": "2026-03-15T12:00:00Z",
                    "forecast_start_local_date": "2026-03-16",
                    "forecast_end_local_date": "2026-03-31",
                    "destination_factory_ids": [101],
                    "execution_mode": "historical_observed",
                    "upstream_selection_mode": "historical_resolution",
                    "forecast_horizon_policy_version": "task11-horizon-v1",
                    "timezone": "Asia/Shanghai",
                },
            ],
        }
    )
    right = RollingBacktestConfig.model_validate(
        {
            **left.model_dump(mode="json"),
            "nodes": list(reversed(left.model_dump(mode="json")["nodes"])),
        }
    )
    assert rolling_backtest_config_hash(left) == rolling_backtest_config_hash(right)
