from __future__ import annotations

from backend.app.rolling_backtest.enums import (
    EvaluationStatus,
    ForecastStatus,
    RunDerivedStatus,
)
from backend.app.rolling_backtest.schemas import NodeStateSnapshot


def derive_run_status(nodes: tuple[NodeStateSnapshot, ...]) -> RunDerivedStatus:
    if any(node.forecast_status == ForecastStatus.FAILED for node in nodes):
        return RunDerivedStatus.FAILED

    completed_forecasts = sum(
        1 for node in nodes if node.forecast_status == ForecastStatus.COMPLETED
    )
    blocked_forecasts = sum(1 for node in nodes if node.forecast_status == ForecastStatus.BLOCKED)
    running_forecasts = sum(1 for node in nodes if node.forecast_status == ForecastStatus.RUNNING)

    if blocked_forecasts and completed_forecasts:
        return RunDerivedStatus.PARTIALLY_COMPLETED
    if blocked_forecasts and not completed_forecasts:
        return RunDerivedStatus.BLOCKED
    if running_forecasts:
        return RunDerivedStatus.RUNNING
    if all(node.forecast_status == ForecastStatus.PENDING for node in nodes):
        return RunDerivedStatus.PENDING
    if all(node.forecast_status == ForecastStatus.COMPLETED for node in nodes):
        if all(node.evaluation_status == EvaluationStatus.COMPLETED for node in nodes):
            return RunDerivedStatus.COMPLETED
        return RunDerivedStatus.FORECAST_COMPLETED
    return RunDerivedStatus.PENDING
