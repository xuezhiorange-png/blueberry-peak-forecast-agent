from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from backend.app.harvest_state.canonical import canonical_json_value
from backend.app.harvest_state.service import run_harvest_state_model
from backend.tests.harvest_state.conftest import (
    make_capacity_input,
    make_initial_cohort,
    make_loss_input,
    make_pool,
    make_request,
    make_stable_cohort_key,
    make_task8_source_ref,
    make_task8_verification_snapshot,
)

_GOLDEN_DIR = Path(__file__).with_name("golden")


def _load_golden(name: str) -> dict[str, object]:
    return json.loads((_GOLDEN_DIR / name).read_text())


def _canonical_output(result: object) -> dict[str, object]:
    return canonical_json_value(result)  # type: ignore[return-value]


def test_single_day_direct_capacity_golden_fixture() -> None:
    source_ref = make_task8_source_ref(
        prediction_date=date(2026, 3, 1),
        forecast_quantile="P50",
        source_quantity_kg=Decimal("10"),
    )
    verification_snapshot = make_task8_verification_snapshot(
        prediction_date=date(2026, 3, 1),
        forecast_quantile="P50",
        source_quantity_kg=Decimal("10"),
        variety_id=101,
    )
    verification_snapshot["p50_kg"] = Decimal("10")
    verification_snapshot["p80_kg"] = Decimal("0")
    verification_snapshot["p90_kg"] = Decimal("0")
    payload = {
        **make_request(),
        "forecast_start_date": date(2026, 3, 1),
        "forecast_end_date": date(2026, 3, 1),
        "capacity_pools": [
            make_pool(
                grain="SUBFARM_VARIETY",
                members=[{"farm_id": 1, "subfarm_id": 11, "variety_id": 101}],
            )
        ],
        "task8_daily_predictions": [
            {
                "prediction_date": date(2026, 3, 1),
                "farm_id": 1,
                "subfarm_id": 11,
                "variety_id": 101,
                "source_ref": source_ref,
                "verification_snapshot": verification_snapshot,
            },
            {
                "prediction_date": date(2026, 3, 1),
                "farm_id": 1,
                "subfarm_id": 11,
                "variety_id": 101,
                "source_ref": make_task8_source_ref(
                    prediction_date=date(2026, 3, 1),
                    forecast_quantile="P80",
                    source_quantity_kg=Decimal("0"),
                ),
                "verification_snapshot": {
                    **make_task8_verification_snapshot(
                        prediction_date=date(2026, 3, 1),
                        forecast_quantile="P80",
                        source_quantity_kg=Decimal("0"),
                        variety_id=101,
                    ),
                    "p50_kg": Decimal("10"),
                    "p80_kg": Decimal("0"),
                    "p90_kg": Decimal("0"),
                },
            },
            {
                "prediction_date": date(2026, 3, 1),
                "farm_id": 1,
                "subfarm_id": 11,
                "variety_id": 101,
                "source_ref": make_task8_source_ref(
                    prediction_date=date(2026, 3, 1),
                    forecast_quantile="P90",
                    source_quantity_kg=Decimal("0"),
                ),
                "verification_snapshot": {
                    **make_task8_verification_snapshot(
                        prediction_date=date(2026, 3, 1),
                        forecast_quantile="P90",
                        source_quantity_kg=Decimal("0"),
                        variety_id=101,
                    ),
                    "p50_kg": Decimal("10"),
                    "p80_kg": Decimal("0"),
                    "p90_kg": Decimal("0"),
                },
            },
        ],
        "initial_inventory_cohorts": [],
        "initial_opening_mature_inventory_kg": Decimal("0"),
        "daily_capacity_inputs": [
            make_capacity_input(
                capacity_date=date(2026, 3, 1),
                mode="DIRECT_CAPACITY",
                planned_picker_count=None,
                productivity=None,
                direct_capacity=Decimal("7"),
            )
        ],
        "mature_inventory_loss_inputs": [
            make_loss_input(
                state_date=date(2026, 3, 1),
                pool_id="pool-a",
                quantile="P50",
                quantity=Decimal("1"),
            ),
            make_loss_input(
                state_date=date(2026, 3, 1),
                pool_id="pool-a",
                quantile="P80",
                quantity=Decimal("0"),
            ),
            make_loss_input(
                state_date=date(2026, 3, 1),
                pool_id="pool-a",
                quantile="P90",
                quantity=Decimal("0"),
            ),
        ],
    }
    payload["initial_inventory_cohorts"] = [
        make_initial_cohort(
            quantile="P50",
            quantity=Decimal("2"),
            variety_id=101,
            capacity_pool_membership_hash=make_stable_cohort_key(
                {
                    "capacity_pool_grain": "SUBFARM_VARIETY",
                    "members": [{"farm_id": 1, "subfarm_id": 11, "variety_id": 101}],
                }
            ),
        )
    ]
    payload["initial_opening_mature_inventory_kg"] = Decimal("2")

    result = run_harvest_state_model(payload)

    assert _canonical_output(result.model_dump(mode="python")) == _load_golden(
        "single_day_direct_capacity.json"
    )


def test_multi_day_shared_pool_golden_fixture() -> None:
    result = run_harvest_state_model(make_request())

    assert _canonical_output(result.model_dump(mode="python")) == _load_golden(
        "multi_day_shared_pool.json"
    )


def test_arrival_lag_golden_fixture() -> None:
    payload = make_request()
    payload["harvest_to_arrival_lag_days"] = 5

    result = run_harvest_state_model(payload)

    assert _canonical_output(result.model_dump(mode="python")) == _load_golden("arrival_lag.json")
