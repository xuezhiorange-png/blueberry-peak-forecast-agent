from __future__ import annotations

from backend.app.core_forecast.canonical import (
    compute_core_forecast_input_hash,
    compute_core_forecast_request_hash,
    compute_core_forecast_result_hash,
    compute_retention_policy_snapshot_hash,
)
from backend.app.core_forecast.metrics import compute_core_forecast_metrics
from backend.app.core_forecast.schemas import ExecuteCoreForecastRunRequest
from backend.tests.core_forecast.test_complete_daily_curve_service import (
    _policy,
    _request,
    _run,
)


async def fixture_request_and_outputs():
    curve_request = _request()
    retention_policy = _policy()
    curve = await _run()
    metrics = compute_core_forecast_metrics(daily_curve=curve)
    request = ExecuteCoreForecastRunRequest(
        curve_request=curve_request,
        retention_policy=retention_policy,
    )
    policy_hash = compute_retention_policy_snapshot_hash(retention_policy)
    input_hash = compute_core_forecast_input_hash(curve_request, retention_policy)
    request_hash = compute_core_forecast_request_hash(input_hash, None)
    assert curve.curve_hash is not None
    assert metrics.metrics_hash is not None
    result_hash = compute_core_forecast_result_hash(
        request_hash=request_hash,
        forecast_input_hash=input_hash,
        curve_hash=curve.curve_hash,
        metrics_hash=metrics.metrics_hash,
        daily_row_count=len(curve.rows),
        metric_row_count=len(metrics.metrics),
    )
    return request, curve, metrics, policy_hash, input_hash, request_hash, result_hash
