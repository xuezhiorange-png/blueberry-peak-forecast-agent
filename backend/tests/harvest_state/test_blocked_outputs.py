from __future__ import annotations

from decimal import Decimal

from backend.tests.harvest_state.conftest import make_request


def test_blocked_output_has_empty_state_arrays() -> None:
    from backend.app.harvest_state.schemas import Task9ARequest
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["daily_capacity_inputs"] = []
    result = run_harvest_state_model(Task9ARequest.model_validate(payload))

    assert result.status == "blocked"
    assert result.daily_pool_state_rows == []
    assert result.daily_member_state_rows == []
    assert result.cohort_transition_rows == []
    assert result.future_arrival_schedule == []


def test_missing_initial_cohorts_differs_from_explicit_empty() -> None:
    from backend.app.harvest_state.schemas import Task9ARequest
    from backend.app.harvest_state.service import run_harvest_state_model

    payload_missing = make_request()
    del payload_missing["initial_inventory_cohorts"]
    blocked = run_harvest_state_model(Task9ARequest.model_validate(payload_missing))
    assert blocked.status == "blocked"

    payload_empty = make_request()
    payload_empty["initial_inventory_cohorts"] = []
    payload_empty["initial_opening_mature_inventory_kg"] = Decimal("0")
    completed = run_harvest_state_model(Task9ARequest.model_validate(payload_empty))
    assert completed.status == "completed"
