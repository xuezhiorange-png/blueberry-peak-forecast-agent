"""S6 synthetic time/state boundaries; no private input or weather needed."""

import copy
from datetime import date, timedelta
from decimal import Decimal

import pytest

from backend.research import v019_origin_features as features


def history(year: int = 2024, n: int = 60) -> list[dict]:
    start = date(year, 7, 1)
    return [
        {
            "base_id": "SYNTHETIC-a",
            "season": f"{year}-{year + 1}",
            "date": str(start + timedelta(days=i)),
            "state": "VALID_OBSERVED",
            "kg": "2.000000",
            "source_sha256": "a" * 64,
            "authority_sha256": "b" * 64,
        }
        for i in range(n)
    ]


@pytest.mark.parametrize("area", ["0", "-1", "NaN", "Infinity"])
def test_invalid_area_is_not_inferred(area):
    with pytest.raises(ValueError, match="AREA"):
        features.snapshot(
            "SYNTHETIC-a", "2024-2025", date(2024, 8, 1), Decimal(area), history(), 15
        )


def test_future_quantities_are_not_even_converted_and_no_label_extra_fields():
    from backend.research.v019_synthetic_validation import digest

    class Poison:
        def __str__(self):
            raise AssertionError("FUTURE_VALUE_ACCESSED")

    h = history()
    before = features.snapshot("SYNTHETIC-a", "2024-2025", date(2024, 8, 1), Decimal(1), h, 15)
    for r in h:
        if r["date"] >= "2024-08-01":
            r["kg"] = Poison()
    assert (
        features.snapshot("SYNTHETIC-a", "2024-2025", date(2024, 8, 1), Decimal(1), h, 15) == before
    )
    injected = {**before, "actual_target_kg": "9000"}
    injected["sha256"] = digest({k: v for k, v in injected.items() if k != "sha256"})
    with pytest.raises(ValueError, match="SCHEMA"):
        features.validate(injected)


def test_reuses_four_frozen_sums_and_excludes_origin_and_future() -> None:
    h = history()
    origin = date(2024, 8, 1)
    r = features.snapshot("SYNTHETIC-a", "2024-2025", origin, Decimal(1), h, 15)
    assert r["complete"]
    assert list(r["values"].values()) == ["14.000000", "28.000000", "56.000000", "62.000000"]
    changed = copy.deepcopy(h)
    for d in changed:
        if date.fromisoformat(d["date"]) >= origin:
            d["kg"] = "999999"
            d["authority_sha256"] = "f" * 64
    assert features.snapshot("SYNTHETIC-a", "2024-2025", origin, Decimal(1), changed, 15) == r
    changed = copy.deepcopy(h)
    changed[30]["kg"] = "5.000000"
    after = features.snapshot("SYNTHETIC-a", "2024-2025", origin, Decimal(1), changed, 15)
    assert all(Decimal(after["values"][k]) - Decimal(r["values"][k]) == 3 for k in r["values"])
    assert after["sha256"] != r["sha256"]


@pytest.mark.parametrize("state", ["UNKNOWN", "PARTIAL", "MISSING", "CONFLICTING"])
def test_incomplete_state_not_zero_filled(state: str) -> None:
    h = history()
    h[25].update(state=state, kg=None)
    r = features.snapshot("SYNTHETIC-a", "2024-2025", date(2024, 8, 1), Decimal(1), h, 15)
    assert not r["complete"] and r["values"]["past_7d_harvest_kg"] is None


def test_absent_day_duplicate_invalid_and_early_origin() -> None:
    h = history()
    del h[25]
    assert not features.snapshot("SYNTHETIC-a", "2024-2025", date(2024, 8, 1), Decimal(1), h, 15)[
        "complete"
    ]
    with pytest.raises(ValueError, match="DUPLICATE"):
        features.snapshot(
            "SYNTHETIC-a", "2024-2025", date(2024, 8, 1), Decimal(1), history() + history()[:1], 15
        )
    for value in ["-1", "NaN", "Infinity"]:
        h = history()
        h[30]["kg"] = value
        assert not features.snapshot(
            "SYNTHETIC-a", "2024-2025", date(2024, 8, 1), Decimal(1), h, 15
        )["complete"]
    assert not features.snapshot(
        "SYNTHETIC-a", "2024-2025", date(2024, 7, 1), Decimal(1), history(), 15
    )["complete"]
    with pytest.raises(ValueError, match="UNAUTHORIZED"):
        features.snapshot("SYNTHETIC-a", "2026-2027", date(2026, 8, 1), Decimal(1), history(), 15)


def test_confirmed_zero_and_no_global_lineage_dependency() -> None:
    h = history()
    for r in h:
        r.update(kg="0.000000", state="CONFIRMED_ZERO")
    r = features.snapshot("SYNTHETIC-a", "2024-2025", date(2024, 8, 1), Decimal(1), h, 15)
    assert r["complete"] and all(Decimal(v) == 0 for v in r["values"].values())
    assert r == features.snapshot(
        "SYNTHETIC-a", "2024-2025", date(2024, 8, 1), Decimal(1), list(reversed(h)), 15
    )
    h[30]["kg"] = "1"
    assert not features.snapshot("SYNTHETIC-a", "2024-2025", date(2024, 8, 1), Decimal(1), h, 15)[
        "complete"
    ]


def test_frozen_2025_season_start_is_not_rebased_to_label_start() -> None:
    h = history(2025)
    h = [r for r in h if r["date"] >= "2025-08-05"]
    r = features.snapshot("SYNTHETIC-a", "2025-2026", date(2025, 8, 30), Decimal(1), h, 15)
    assert r["season_start"] == "2025-07-22"
    assert not r["complete"] and r["values"]["season_to_date_harvest_kg"] is None


def test_same_target_base10_is_origin_invariant_and_7day_tail_is_real() -> None:
    a = features.snapshot("SYNTHETIC-a", "2024-2025", date(2024, 8, 1), Decimal(1), history(), 15)
    b = features.snapshot("SYNTHETIC-a", "2024-2025", date(2024, 8, 2), Decimal(1), history(), 15)
    assert features.base10(a)[1] == features.base10(b)[0]
    tail = features.snapshot("SYNTHETIC-a", "2024-2025", date(2025, 4, 8), Decimal(1), history(), 7)
    assert tail["target_dates"][-1] == "2025-04-15"
    with pytest.raises(ValueError, match="TARGET"):
        features.snapshot("SYNTHETIC-a", "2024-2025", date(2025, 4, 8), Decimal(1), history(), 15)


@pytest.mark.parametrize("fraction", ["", ".999999"])
def test_frozen_cutoff_precision_preserved(fraction):
    cutoff = f"2024-08-01T23:59:59{fraction}+08:00"
    r = features.snapshot(
        "SYNTHETIC-a",
        "2024-2025",
        date(2024, 8, 1),
        Decimal(1),
        history(),
        15,
        cutoff=cutoff,
    )
    assert r["cutoff"] == cutoff
    features.validate(r)


@pytest.mark.parametrize(
    "cutoff",
    [
        "2024-08-01T23:59:59",
        "2024-08-01T23:59:59+00:00",
        "2024-08-02T23:59:59+08:00",
        "2024-08-01T12:00:00+08:00",
    ],
)
def test_cutoff_wrong_day_timezone_or_midday_rejected(cutoff):
    with pytest.raises(ValueError, match="SEMANTICS"):
        features.snapshot(
            "SYNTHETIC-a",
            "2024-2025",
            date(2024, 8, 1),
            Decimal(1),
            history(),
            15,
            cutoff=cutoff,
        )
