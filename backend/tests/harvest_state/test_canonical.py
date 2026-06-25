from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.tests.harvest_state.conftest import make_initial_cohort, make_request


def test_membership_hash_is_order_invariant() -> None:
    from backend.app.harvest_state.schemas import Task9ARequest
    from backend.app.harvest_state.service import _validated_request

    payload = make_request()
    reversed_payload = make_request()
    reversed_payload["capacity_pools"][0]["members"] = list(
        reversed(reversed_payload["capacity_pools"][0]["members"])
    )

    request_a = Task9ARequest.model_validate(payload)
    request_b = Task9ARequest.model_validate(reversed_payload)
    validated_a = _validated_request(request_a)
    validated_b = _validated_request(request_b)

    assert (
        validated_a.pool_membership_hash_by_pool["pool-a"]
        == validated_b.pool_membership_hash_by_pool["pool-a"]
    )


def test_stable_cohort_key_ignores_mutable_quantity() -> None:
    from backend.app.harvest_state.schemas import Task9ARequest
    from backend.app.harvest_state.service import _validated_request

    payload = make_request()
    payload["initial_inventory_cohorts"][0]["remaining_quantity_kg"] = Decimal("5")
    request_a = Task9ARequest.model_validate(payload)
    key_a = _validated_request(request_a).initial_cohort_keys[0]

    payload["initial_inventory_cohorts"][0]["remaining_quantity_kg"] = Decimal("7")
    request_b = Task9ARequest.model_validate(payload)
    key_b = _validated_request(request_b).initial_cohort_keys[0]

    assert key_a == key_b


def test_result_hash_excludes_itself_and_is_order_invariant() -> None:
    from backend.app.harvest_state.schemas import Task9ARequest
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    reversed_payload = make_request()
    reversed_payload["task8_daily_predictions"] = list(
        reversed(reversed_payload["task8_daily_predictions"])
    )
    reversed_payload["mature_inventory_loss_inputs"] = list(
        reversed(reversed_payload["mature_inventory_loss_inputs"])
    )

    result_a = run_harvest_state_model(Task9ARequest.model_validate(payload))
    result_b = run_harvest_state_model(Task9ARequest.model_validate(reversed_payload))

    assert result_a.result_hash == result_b.result_hash
    payload = result_a.model_dump(mode="python")
    payload.pop("result_hash")
    assert result_a.result_hash == __import__(
        "backend.app.harvest_state.canonical",
        fromlist=["make_result_hash"],
    ).make_result_hash(payload)


def test_input_position_does_not_change_initial_inventory_cohort_key() -> None:
    from backend.app.harvest_state.schemas import Task9ARequest
    from backend.app.harvest_state.service import _validated_request

    payload = make_request()
    payload["initial_inventory_cohorts"] = [
        make_initial_cohort(quantile="P50", quantity=Decimal("3"), cohort_date=date(2026, 2, 27)),
        make_initial_cohort(quantile="P50", quantity=Decimal("4"), cohort_date=date(2026, 2, 28)),
    ]
    request_a = Task9ARequest.model_validate(payload)
    keys_a = _validated_request(request_a).initial_cohort_keys

    payload["initial_inventory_cohorts"] = list(reversed(payload["initial_inventory_cohorts"]))
    request_b = Task9ARequest.model_validate(payload)
    keys_b = _validated_request(request_b).initial_cohort_keys

    assert sorted(keys_a) == sorted(keys_b)
