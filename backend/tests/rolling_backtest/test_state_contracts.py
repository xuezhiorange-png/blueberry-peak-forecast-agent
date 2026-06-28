from __future__ import annotations

import pytest

from backend.app.rolling_backtest.config import rolling_backtest_config_hash
from backend.app.rolling_backtest.enums import EvaluationStatus, ForecastStatus, RunDerivedStatus
from backend.app.rolling_backtest.schemas import NodeStateSnapshot, RollingBacktestConfig
from backend.app.rolling_backtest.state import derive_run_status


def _node_state(
    forecast_status: ForecastStatus,
    evaluation_status: EvaluationStatus,
) -> NodeStateSnapshot:
    return NodeStateSnapshot(
        forecast_status=forecast_status,
        evaluation_status=evaluation_status,
    )


def _scope_payload(destination_ids: list[int]) -> dict[str, object]:
    return {
        "destination_factory_ids": {"mode": "include_ids", "ids": destination_ids},
        "farm_ids": {"mode": "all", "ids": []},
        "subfarm_ids": {"mode": "all", "ids": []},
        "variety_ids": {"mode": "all", "ids": []},
    }


@pytest.mark.parametrize(
    ("nodes", "expected"),
    [
        (
            (
                _node_state(ForecastStatus.FAILED, EvaluationStatus.NOT_READY),
                _node_state(ForecastStatus.COMPLETED, EvaluationStatus.COMPLETED),
            ),
            RunDerivedStatus.FAILED,
        ),
        (
            (
                _node_state(ForecastStatus.COMPLETED, EvaluationStatus.FAILED),
                _node_state(ForecastStatus.COMPLETED, EvaluationStatus.COMPLETED),
            ),
            RunDerivedStatus.FAILED,
        ),
        (
            (
                _node_state(ForecastStatus.BLOCKED, EvaluationStatus.BLOCKED),
                _node_state(ForecastStatus.BLOCKED, EvaluationStatus.BLOCKED),
            ),
            RunDerivedStatus.BLOCKED,
        ),
        (
            (
                _node_state(ForecastStatus.BLOCKED, EvaluationStatus.BLOCKED),
                _node_state(ForecastStatus.COMPLETED, EvaluationStatus.NOT_READY),
            ),
            RunDerivedStatus.PARTIALLY_COMPLETED,
        ),
        (
            (
                _node_state(ForecastStatus.COMPLETED, EvaluationStatus.BLOCKED),
                _node_state(ForecastStatus.COMPLETED, EvaluationStatus.BLOCKED),
            ),
            RunDerivedStatus.BLOCKED,
        ),
        (
            (
                _node_state(ForecastStatus.COMPLETED, EvaluationStatus.RUNNING),
                _node_state(ForecastStatus.COMPLETED, EvaluationStatus.PENDING),
            ),
            RunDerivedStatus.FORECAST_COMPLETED,
        ),
        (
            (
                _node_state(ForecastStatus.COMPLETED, EvaluationStatus.PENDING),
                _node_state(ForecastStatus.COMPLETED, EvaluationStatus.NOT_READY),
            ),
            RunDerivedStatus.FORECAST_COMPLETED,
        ),
        (
            (
                _node_state(ForecastStatus.COMPLETED, EvaluationStatus.NOT_READY),
                _node_state(ForecastStatus.COMPLETED, EvaluationStatus.NOT_READY),
            ),
            RunDerivedStatus.FORECAST_COMPLETED,
        ),
        (
            (
                _node_state(ForecastStatus.COMPLETED, EvaluationStatus.COMPLETED),
                _node_state(ForecastStatus.COMPLETED, EvaluationStatus.COMPLETED),
            ),
            RunDerivedStatus.COMPLETED,
        ),
        (
            (
                _node_state(ForecastStatus.RUNNING, EvaluationStatus.PENDING),
                _node_state(ForecastStatus.PENDING, EvaluationStatus.NOT_READY),
            ),
            RunDerivedStatus.RUNNING,
        ),
        (
            (
                _node_state(ForecastStatus.PENDING, EvaluationStatus.NOT_READY),
                _node_state(ForecastStatus.PENDING, EvaluationStatus.NOT_READY),
            ),
            RunDerivedStatus.PENDING,
        ),
    ],
)
def test_run_level_state_matrix(
    nodes: tuple[NodeStateSnapshot, ...],
    expected: RunDerivedStatus,
) -> None:
    assert derive_run_status(nodes) == expected


def test_empty_nodes_are_rejected() -> None:
    with pytest.raises(ValueError, match="nodes must be non-empty"):
        derive_run_status(())


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
            "execution_mode": "historical_observed",
            "task10_model_policy": {
                "policy": "historically_available_model",
                "training_run_semantic_identity": "1" * 64,
                "artifact_semantic_identities": ["2" * 64, "3" * 64, "4" * 64],
                "authority_visibility_identity": "5" * 64,
            },
            "calendar_phase_policy_version": "task11-calendar-phase-v1",
            "cutoff_policy_version": "task11-cutoff-v1",
            "cutoff_timezone": "Asia/Shanghai",
            "cutoff_local_time": "12:00:00",
            "nodes": [
                {
                    "season_id": 2027,
                    "node_key": "march_15",
                    "as_of_local_date": "2027-03-15",
                    "forecast_cutoff_at": "2027-03-15T04:00:00Z",
                    "forecast_start_local_date": "2027-03-16",
                    "forecast_end_local_date": "2027-03-31",
                    "scope": _scope_payload([202, 101]),
                    "upstream_selection_mode": "historical_resolution",
                    "forecast_horizon_policy_version": "task11-horizon-v1",
                    "timezone": "Asia/Shanghai",
                },
                {
                    "season_id": 2026,
                    "node_key": "march_15",
                    "as_of_local_date": "2026-03-15",
                    "forecast_cutoff_at": "2026-03-15T04:00:00Z",
                    "forecast_start_local_date": "2026-03-16",
                    "forecast_end_local_date": "2026-03-31",
                    "scope": _scope_payload([101]),
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
