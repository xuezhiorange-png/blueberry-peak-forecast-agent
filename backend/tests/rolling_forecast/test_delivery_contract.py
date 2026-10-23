"""S7 sample arithmetic is executable; snapshots never bind future worktrees."""

import json
from decimal import Decimal
from pathlib import Path


def test_documented_example_closes_and_never_claims_production_accuracy():
    root = Path(__file__).resolve().parents[3]
    value = json.loads((root / "docs/v0-19/evidence/v0.19-s7-rolling-shadow-r1.json").read_bytes())
    example = value["business_example"]
    assert example["data_class"] == "SYNTHETIC_TEST_FIXTURE"
    days = [Decimal(v) for v in example["origin_1_daily_kg"]]
    assert len(days) == 15 and all(d >= 0 for d in days)
    assert sum(days[:7]) == Decimal(example["origin_1_h7_total_kg"])
    assert sum(days) == Decimal(example["origin_1_h15_total_kg"])
    for n in (7, 15):
        assert Decimal(example[f"origin_2_h{n}_total_kg"]) - Decimal(
            example[f"origin_1_h{n}_total_kg"]
        ) == Decimal(example[f"different_window_h{n}_delta_kg"])
    for field in (
        "current_2026_2027_actuals_read",
        "current_2026_2027_actuals_scored",
        "strict_pit_validated",
        "prospective_accuracy_validated",
        "production_model_promoted",
        "deployed",
        "ready_authorized",
        "merge_authorized",
        "model_training_executed",
    ):
        assert value[field] is False
    assert value["exact_head_ci"] == "EXTERNAL_POST_COMMIT_RECEIPT_REQUIRED"
