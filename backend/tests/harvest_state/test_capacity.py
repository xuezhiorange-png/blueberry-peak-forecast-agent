from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.tests.harvest_state.conftest import make_capacity_input, make_pool, make_request


def test_subfarm_variety_pool_with_two_members_blocks() -> None:
    from backend.app.harvest_state.schemas import Task9ARequest
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["capacity_pools"][0] = make_pool(pool_id="pool-a", grain="SUBFARM_VARIETY")
    request = Task9ARequest.model_validate(payload)
    result = run_harvest_state_model(request)

    assert result.status == "blocked"


def test_same_member_in_two_pools_blocks() -> None:
    from backend.app.harvest_state.schemas import Task9ARequest
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["capacity_pools"] = [
        make_pool(pool_id="pool-a"),
        make_pool(pool_id="pool-b"),
    ]
    payload["daily_capacity_inputs"].append(
        make_capacity_input(capacity_date=date(2026, 3, 1), pool_id="pool-b")
    )
    payload["daily_capacity_inputs"].append(
        make_capacity_input(capacity_date=date(2026, 3, 2), pool_id="pool-b")
    )
    payload["daily_capacity_inputs"].append(
        make_capacity_input(capacity_date=date(2026, 3, 3), pool_id="pool-b")
    )
    request = Task9ARequest.model_validate(payload)
    result = run_harvest_state_model(request)

    assert result.status == "blocked"


def test_direct_capacity_mode_does_not_reapply_picker_productivity() -> None:
    from backend.app.harvest_state.schemas import Task9ARequest
    from backend.app.harvest_state.service import _validated_request

    payload = make_request()
    payload["daily_capacity_inputs"] = [
        make_capacity_input(
            capacity_date=date(2026, 3, 1),
            mode="DIRECT_CAPACITY",
            planned_picker_count=None,
            productivity=None,
            direct_capacity=Decimal("77"),
        ),
        make_capacity_input(
            capacity_date=date(2026, 3, 2),
            mode="DIRECT_CAPACITY",
            planned_picker_count=None,
            productivity=None,
            direct_capacity=Decimal("77"),
        ),
        make_capacity_input(
            capacity_date=date(2026, 3, 3),
            mode="DIRECT_CAPACITY",
            planned_picker_count=None,
            productivity=None,
            direct_capacity=Decimal("77"),
        ),
    ]
    request = Task9ARequest.model_validate(payload)
    validated = _validated_request(request)

    for params in validated.daily_pool_parameters.values():
        assert params.resolved_nominal_capacity_kg_per_day == Decimal("77")


def test_p50_remaining_capacity_does_not_affect_other_quantiles() -> None:
    from backend.app.harvest_state.schemas import Task9ARequest
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    result = run_harvest_state_model(Task9ARequest.model_validate(payload))

    by_quantile = {
        row.forecast_quantile: row.effective_capacity_for_day_kg
        for row in result.daily_pool_state_rows
        if row.state_date == date(2026, 3, 1)
    }

    assert by_quantile["P50"] == by_quantile["P80"] == by_quantile["P90"]
