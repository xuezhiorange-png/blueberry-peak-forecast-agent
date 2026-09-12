from datetime import date, timedelta

from backend.app.area_yield.ledger_r3a import qualify


def fixture(global_gap=False):
    start = date(2023, 8, 1)
    rows = []
    for i in range(60):
        day = str(start + timedelta(days=i))
        rows.append(
            {
                "canonical_farm_id": "B",
                "date": day,
                "daily_harvest_kg": "" if global_gap and i == 25 else "1",
            }
        )
        rows.append(
            {
                "canonical_farm_id": "A",
                "date": day,
                "daily_harvest_kg": "2" if i in (20, 30) else "",
            }
        )
    return rows, start, start + timedelta(days=59)


def test_source_active_absence_needs_completeness():
    rows, start, end = fixture()
    matrix, daily = qualify(rows, "2023-2024", start, end, False, {"A"})
    assert matrix[0]["source_active_zero_days"] == 0
    assert matrix[0]["source_active_absence_days"] == 58
    assert not matrix[0]["strict_eligible"]
    assert matrix[0]["eligible_if_source_confirmed"]
    assert all(r["source_active_day"] for r in daily)


def test_source_active_zero_never_biological_zero():
    rows, start, end = fixture()
    matrix, _ = qualify(rows, "2023-2024", start, end, True, {"A"})
    assert matrix[0]["strict_eligible"]
    assert matrix[0]["source_active_zero_days"] == 58
    assert matrix[0]["zero_semantics"] == "RECORDED_LEDGER_ZERO_NOT_BIOLOGICAL_ZERO"


def test_global_unknown_in_active_span_blocks():
    rows, start, end = fixture(True)
    matrix, daily = qualify(rows, "2023-2024", start, end, True, {"A"})
    assert matrix[0]["active_span_global_unknown_days"] == 1
    assert not matrix[0]["strict_eligible"]
    assert sum(not r["source_active_day"] for r in daily) == 1


def test_boundary_truncation_is_diagnostic_only():
    rows, start, end = fixture()
    matrix, _ = qualify(rows, "2023-2024", start, end, True, {"A", "B"})
    assert not matrix[1]["boundary_contained"]
    assert matrix[1]["diagnostic_only"]


def test_exact_identity_required():
    rows, start, end = fixture()
    matrix, _ = qualify(rows, "2023-2024", start, end, True, {"other"})
    assert not matrix[0]["strict_eligible"]


def test_global_absence_outside_harvest_span_not_zero():
    rows, start, end = fixture()
    rows[0]["daily_harvest_kg"] = ""
    matrix, daily = qualify(rows, "2023-2024", start, end, True, {"A"})
    assert matrix[0]["global_unknown_days"] == 1
    assert matrix[0]["active_span_global_unknown_days"] == 0
    assert daily[0]["status"] == "UNKNOWN_GLOBAL_NO_RECORD"
    assert daily[0]["recorded_harvest_kg"] == ""
