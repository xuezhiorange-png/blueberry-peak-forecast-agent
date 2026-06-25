from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.tests.harvest_state.conftest import make_request


def test_request_accepts_decimal_int_and_canonical_string_inputs() -> None:
    from backend.app.harvest_state.schemas import Task9ARequest

    payload = make_request()
    payload["harvest_to_arrival_lag_days"] = 1
    payload["daily_capacity_inputs"][0]["planned_picker_count"] = 10
    payload["daily_capacity_inputs"][0]["kg_per_person_per_day"] = "20"

    request = Task9ARequest.model_validate(payload)

    assert request.daily_capacity_inputs[0].planned_picker_count == Decimal("10")
    assert request.daily_capacity_inputs[0].kg_per_person_per_day == Decimal("20")


def test_request_rejects_native_float_business_inputs() -> None:
    from backend.app.harvest_state.schemas import Task9ARequest

    payload = make_request()
    payload["daily_capacity_inputs"][0]["kg_per_person_per_day"] = 20.5

    with pytest.raises(ValidationError):
        Task9ARequest.model_validate(payload)


def test_capacity_pool_grain_rejects_undefined_value() -> None:
    from backend.app.harvest_state.schemas import Task9ARequest

    payload = make_request()
    payload["capacity_pools"][0]["capacity_pool_grain"] = "REGION"

    with pytest.raises(ValidationError):
        Task9ARequest.model_validate(payload)


def test_forecast_quantiles_must_be_canonical_sorted_triplet() -> None:
    from backend.app.harvest_state.schemas import Task9ARequest

    payload = make_request()
    payload["forecast_quantiles"] = ["P80", "P50", "P90"]

    with pytest.raises(ValidationError):
        Task9ARequest.model_validate(payload)
