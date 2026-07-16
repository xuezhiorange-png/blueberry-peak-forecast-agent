from __future__ import annotations

import pytest

from backend.app.core_forecast.canonical import (
    compute_core_forecast_input_hash,
    compute_core_forecast_request_hash,
    compute_core_forecast_result_hash,
    compute_retention_policy_snapshot_hash,
)
from backend.tests.core_forecast.s4_test_helpers import fixture_request_and_outputs
from backend.tests.core_forecast.test_complete_daily_curve_service import _policy, _request


@pytest.mark.unit
def test_scope_order_does_not_change_forecast_input_hash() -> None:
    request = _request()
    reversed_request = request.model_copy(update={"scopes": tuple(reversed(request.scopes))})
    policy = _policy()
    assert compute_core_forecast_input_hash(request, policy) == compute_core_forecast_input_hash(
        reversed_request, policy
    )


@pytest.mark.unit
def test_policy_order_does_not_change_snapshot_or_input_hash() -> None:
    request = _request()
    policy = _policy()
    reversed_policy = policy.model_copy(update={"entries": tuple(reversed(policy.entries))})
    assert compute_retention_policy_snapshot_hash(policy) == compute_retention_policy_snapshot_hash(
        reversed_policy
    )
    assert compute_core_forecast_input_hash(request, policy) == compute_core_forecast_input_hash(
        request, reversed_policy
    )


@pytest.mark.unit
def test_business_field_change_changes_forecast_input_hash() -> None:
    request = _request()
    changed = request.model_copy(update={"destination_factory_id": 9102})
    policy = _policy()
    assert compute_core_forecast_input_hash(request, policy) != compute_core_forecast_input_hash(
        changed, policy
    )


@pytest.mark.unit
def test_rerun_parent_changes_request_hash_not_forecast_input_hash() -> None:
    request = _request()
    policy = _policy()
    input_hash = compute_core_forecast_input_hash(request, policy)
    assert compute_core_forecast_request_hash(
        input_hash, None
    ) != compute_core_forecast_request_hash(input_hash, 123)


@pytest.mark.unit
def test_result_hash_excludes_database_identity_and_clock() -> None:
    request = _request()
    policy = _policy()
    input_hash = compute_core_forecast_input_hash(request, policy)
    request_hash = compute_core_forecast_request_hash(input_hash, None)
    kwargs = {
        "request_hash": request_hash,
        "forecast_input_hash": input_hash,
        "curve_hash": "a" * 64,
        "metrics_hash": "b" * 64,
        "daily_row_count": 1080,
        "metric_row_count": 3,
    }
    assert compute_core_forecast_result_hash(**kwargs) == compute_core_forecast_result_hash(
        **kwargs
    )


@pytest.mark.unit
async def test_fixture_hashes_are_stable_for_s4_input() -> None:
    (
        request,
        curve,
        metrics,
        policy_hash,
        input_hash,
        request_hash,
        result_hash,
    ) = await fixture_request_and_outputs()
    assert request.rerun_of_run_id is None
    assert len(curve.rows) == 1080
    assert len(metrics.metrics) == 3
    assert len(policy_hash) == len(input_hash) == len(request_hash) == len(result_hash) == 64
