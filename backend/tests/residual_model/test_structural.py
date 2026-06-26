from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.app.harvest_state.service import run_harvest_state_model
from backend.app.residual_model.structural import aggregate_structural_arrivals
from backend.tests.harvest_state.conftest import make_request


def test_structural_arrivals_aggregate_member_rows_without_double_count() -> None:
    result = run_harvest_state_model(make_request())
    assert result.status == "completed"

    structural_rows = aggregate_structural_arrivals(result)

    assert structural_rows
    first = next(item for item in structural_rows if item["structural_p50_kg"] > 0)
    assert result.resolved_parameter_snapshot is not None
    assert (
        first["destination_factory_id"]
        == result.resolved_parameter_snapshot.run_parameters.destination_factory_id
    )
    assert first["arrival_local_date"] == date(2026, 3, 2)
    assert first["structural_p50_kg"] == Decimal("48.000")
    assert first["structural_p80_kg"] == Decimal("58.000")
    assert first["structural_p90_kg"] == Decimal("68.000")


def test_structural_arrivals_include_future_arrival_schedule_once() -> None:
    payload = make_request()
    payload["forecast_end_date"] = date(2026, 3, 2)
    result = run_harvest_state_model(payload)
    assert result.status == "completed"
    assert result.future_arrival_schedule

    structural_rows = aggregate_structural_arrivals(result)

    row = next(item for item in structural_rows if item["arrival_local_date"] > date(2026, 3, 2))
    assert row["structural_p50_kg"] > 0
    assert row["structural_p80_kg"] >= row["structural_p50_kg"]
    assert row["structural_p90_kg"] >= row["structural_p80_kg"]
