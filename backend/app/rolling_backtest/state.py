from __future__ import annotations

from backend.app.rolling_backtest.enums import (
    EvaluationStatus,
    ForecastStatus,
    RunDerivedStatus,
)
from backend.app.rolling_backtest.schemas import NodeStateSnapshot


def derive_run_status(nodes: tuple[NodeStateSnapshot, ...]) -> RunDerivedStatus:
    if not nodes:
        raise ValueError("nodes must be non-empty")

    if any(node.forecast_status == ForecastStatus.FAILED for node in nodes) or any(
        node.evaluation_status == EvaluationStatus.FAILED for node in nodes
    ):
        return RunDerivedStatus.FAILED

    completed_forecasts = sum(
        1 for node in nodes if node.forecast_status == ForecastStatus.COMPLETED
    )
    blocked_forecasts = sum(1 for node in nodes if node.forecast_status == ForecastStatus.BLOCKED)
    running_forecasts = sum(1 for node in nodes if node.forecast_status == ForecastStatus.RUNNING)
    pending_forecasts = sum(1 for node in nodes if node.forecast_status == ForecastStatus.PENDING)

    if blocked_forecasts and completed_forecasts:
        return RunDerivedStatus.PARTIALLY_COMPLETED
    if blocked_forecasts and not completed_forecasts:
        return RunDerivedStatus.BLOCKED
    if running_forecasts:
        return RunDerivedStatus.RUNNING
    if pending_forecasts == len(nodes):
        return RunDerivedStatus.PENDING
    if all(node.forecast_status == ForecastStatus.COMPLETED for node in nodes):
        if all(node.evaluation_status == EvaluationStatus.COMPLETED for node in nodes):
            return RunDerivedStatus.COMPLETED
        if any(node.evaluation_status == EvaluationStatus.BLOCKED for node in nodes):
            if any(node.evaluation_status == EvaluationStatus.COMPLETED for node in nodes):
                return RunDerivedStatus.PARTIALLY_COMPLETED
            return RunDerivedStatus.BLOCKED
        return RunDerivedStatus.FORECAST_COMPLETED
    return RunDerivedStatus.PENDING
