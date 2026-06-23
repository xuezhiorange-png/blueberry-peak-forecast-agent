from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.app.planning.plan_hashing import plan_row_hash


def test_plan_row_hash_is_stable_for_same_business_payload() -> None:
    payload = {
        "farm_id": 1,
        "subfarm_id": None,
        "season_id": 2,
        "variety_id": 3,
        "planted_area_mu": Decimal("100"),
        "expected_yield_kg_per_mu": Decimal("1000.000000"),
        "marketable_rate": Decimal("0.7000000000"),
        "tree_age_years": Decimal("3"),
        "pruning_date": date(2026, 1, 1),
        "flowering_start_date": date(2026, 2, 1),
        "flowering_peak_date": date(2026, 2, 10),
        "flowering_end_date": date(2026, 2, 20),
        "first_pick_date": date(2026, 3, 1),
        "expected_total_marketable_kg": Decimal("70000"),
        "version": 1,
        "effective_from": date(2026, 1, 1),
        "effective_to": None,
        "available_at": date(2025, 12, 1),
        "source_type": "manual",
        "source_name": "planner",
        "source_version": "v1",
        "notes": "same",
    }
    reordered = dict(reversed(list(payload.items())))

    assert plan_row_hash(payload) == plan_row_hash(reordered)


def test_plan_row_hash_changes_when_plan_content_changes() -> None:
    payload = {
        "farm_id": 1,
        "subfarm_id": None,
        "season_id": 2,
        "variety_id": 3,
        "planted_area_mu": Decimal("100"),
        "expected_yield_kg_per_mu": Decimal("1000"),
        "marketable_rate": Decimal("0.7"),
        "tree_age_years": None,
        "pruning_date": None,
        "flowering_start_date": None,
        "flowering_peak_date": None,
        "flowering_end_date": None,
        "first_pick_date": None,
        "expected_total_marketable_kg": None,
        "version": 1,
        "effective_from": date(2026, 1, 1),
        "effective_to": None,
        "available_at": date(2025, 12, 1),
        "source_type": "manual",
        "source_name": None,
        "source_version": None,
        "notes": None,
    }
    changed = dict(payload)
    changed["marketable_rate"] = Decimal("0.8")

    assert plan_row_hash(payload) != plan_row_hash(changed)
