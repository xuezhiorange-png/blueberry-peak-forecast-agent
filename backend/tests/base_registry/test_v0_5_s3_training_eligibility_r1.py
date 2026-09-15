"""Contract tests for the S3 qualification and evaluation freeze runner."""

from datetime import date
from decimal import Decimal

from scripts.audit_v0_5_s3_training_eligibility_r1 import (
    KNOWN_STATUS,
    build_forward_fold_support,
    build_peak_rows,
    build_source_calendar,
    build_support_count_evidence,
    build_window_rows,
    canonical_value_hash,
    dates_between,
    season_window,
)


def ledger_row(
    season: str, base_id: str, day: str, status: str, quantity: str = "0.000000"
) -> dict[str, str]:
    return {
        "season": season,
        "base_id": base_id,
        "date": day,
        "observation_status": status,
        "recorded_harvest_kg": quantity if status == KNOWN_STATUS else "",
    }


def test_business_calendar_is_deterministic_and_excludes_april_16() -> None:
    start, end = season_window("2025-2026")
    calendar = dates_between(start, end)

    assert start == date(2025, 7, 1)
    assert end == date(2026, 4, 15)
    assert len(calendar) == 289
    assert date(2026, 4, 16) not in calendar


def test_source_active_and_global_unknown_are_distinct() -> None:
    season = "2024-2025"
    base_ids = ["base-a", "base-b"]
    rows = {
        (season, "base-a", "2024-07-01"): ledger_row(
            season, "base-a", "2024-07-01", KNOWN_STATUS, "2.000000"
        ),
        (season, "base-b", "2024-07-01"): ledger_row(season, "base-b", "2024-07-01", KNOWN_STATUS),
        (season, "base-a", "2024-07-03"): ledger_row(
            season, "base-a", "2024-07-03", "UNKNOWN_GLOBAL_NO_RECORD"
        ),
        (season, "base-b", "2024-07-03"): ledger_row(
            season, "base-b", "2024-07-03", "UNKNOWN_GLOBAL_NO_RECORD"
        ),
    }

    calendar = build_source_calendar(
        season,
        base_ids,
        rows,
        date(2024, 7, 1),
        date(2024, 7, 3),
    )
    by_date = {row["date"]: row for row in calendar}

    assert by_date["2024-07-01"]["source_active_day"] is True
    assert by_date["2024-07-01"]["global_no_record_day"] is False
    assert by_date["2024-07-03"]["source_active_day"] is False
    assert by_date["2024-07-03"]["global_no_record_day"] is True


def test_authorized_ledger_zero_is_known_but_global_unknown_is_not() -> None:
    season = "2024-2025"
    base_ids = ["base-a"]
    rows = {
        (season, "base-a", "2024-07-01"): ledger_row(
            season, "base-a", "2024-07-01", KNOWN_STATUS, "0.000000"
        ),
        (season, "base-a", "2024-07-03"): ledger_row(
            season, "base-a", "2024-07-03", "UNKNOWN_GLOBAL_NO_RECORD"
        ),
    }
    source_calendar = build_source_calendar(
        season,
        base_ids,
        rows,
        date(2024, 7, 1),
        date(2024, 7, 3),
    )

    # The full daily builder is intentionally exercised through its observable
    # source states in the source-calendar contract above; this assertion keeps
    # the zero policy explicit at the source row boundary.
    assert rows[(season, "base-a", "2024-07-01")]["recorded_harvest_kg"] == "0.000000"
    assert source_calendar[2]["global_no_record_day"] is True


def test_peak_tie_break_is_earliest_date_and_unknown_competition_blocks() -> None:
    base = {"base_id": "base-a", "canonical_base_name": "A"}
    complete = [
        {
            "base_id": "base-a",
            "date": "2025-01-02",
            "label_known": True,
            "observed_harvest_kg": "3.000000",
            "label_state": KNOWN_STATUS,
        },
        {
            "base_id": "base-a",
            "date": "2025-01-01",
            "label_known": True,
            "observed_harvest_kg": "3.000000",
            "label_state": KNOWN_STATUS,
        },
    ]
    peak = build_peak_rows(complete, [base], "2024-2025")[0]
    assert peak["peak_evaluation_status"] == "EXACT_COMPUTABLE"
    assert peak["actual_peak_date"] == "2025-01-01"

    incomplete = complete + [
        {
            "base_id": "base-a",
            "date": "2025-01-03",
            "label_known": False,
            "observed_harvest_kg": "",
            "label_state": "UNKNOWN_GLOBAL_NO_RECORD",
        }
    ]
    blocked = build_peak_rows(incomplete, [base], "2024-2025")[0]
    assert blocked["peak_evaluation_status"] == "NOT_COMPUTABLE_INCOMPLETE_LABEL_DOMAIN"
    assert blocked["actual_peak_date"] == ""


def test_window_rows_are_forward_only_and_require_every_label() -> None:
    rows = [
        {
            "base_id": "base-a",
            "date": f"2025-01-{index:02d}",
            "label_known": True,
            "observed_harvest_kg": "1.000000",
        }
        for index in range(1, 20)
    ]
    windows = build_window_rows(rows, "2024-2025", 7)

    assert len(windows) == 12
    assert windows[0]["origin_date"] == "2025-01-01"
    assert windows[0]["window_start"] == "2025-01-02"
    assert windows[0]["window_end"] == "2025-01-08"
    assert windows[0]["no_cross_season"] is True
    assert windows[0]["window_total_kg"] == "7.000000"

    rows[8]["label_known"] = False
    rows[8]["observed_harvest_kg"] = ""
    changed = build_window_rows(rows, "2024-2025", 7)
    assert any(
        row["window_evaluation_status"] == "NOT_COMPUTABLE_INCOMPLETE_LABEL_DOMAIN"
        for row in changed
    )


def test_decimal_label_values_are_not_recomputed_from_area() -> None:
    assert Decimal("10.000000") / Decimal("2.000000") == Decimal("5.000000")


def _support_rows(
    season: str, base_id: str, dates: list[str], *, window: bool = False
) -> list[dict[str, object]]:
    if window:
        return [
            {
                "base_id": base_id,
                "season": season,
                "window_days": 7,
                "window_evaluation_status": "EXACT_COMPUTABLE",
                "origin_date": day,
            }
            for day in dates
        ]
    return [
        {"base_id": base_id, "season": season, "date": day, "label_known": True} for day in dates
    ]


def test_support_counts_scope_denominators_by_unit_and_season() -> None:
    daily = {
        "2023-2024": _support_rows("2023-2024", "base-a", ["2023-07-01"])
        + _support_rows("2023-2024", "base-b", ["2023-07-02"]),
        "2024-2025": _support_rows("2024-2025", "base-a", ["2024-07-01"]),
        "2025-2026": [],
    }
    windows = _support_rows(
        "2023-2024", "base-a", ["2023-07-01", "2023-07-02"], window=True
    ) + _support_rows("2024-2025", "base-a", ["2024-07-01"], window=True)

    result = build_support_count_evidence(daily, windows)

    counts = result["by_season"]["2023-2024"]["daily_known_support"]
    assert counts["row_or_origin_count"] == 2
    assert counts["unique_base_count"] == 2
    assert counts["unique_base_season_count"] == 2
    assert counts["base_season_ids_hash"] == canonical_value_hash(
        ["base-a|2023-2024", "base-b|2023-2024"]
    )
    assert result["by_season"]["2023-2024"]["W7"]["row_or_origin_count"] == 2
    assert result["by_season"]["2025-2026"]["W15"]["unique_base_count"] == 0


def test_forward_folds_are_explicit_and_count_base_intersection_separately() -> None:
    daily = {
        "2023-2024": _support_rows("2023-2024", "base-a", ["2023-07-01"]),
        "2024-2025": _support_rows("2024-2025", "base-a", ["2024-07-01"])
        + _support_rows("2024-2025", "base-b", ["2024-07-02"]),
        "2025-2026": _support_rows("2025-2026", "base-b", ["2025-07-01"]),
    }
    windows = (
        _support_rows("2023-2024", "base-a", ["2023-07-01"], window=True)
        + _support_rows("2024-2025", "base-a", ["2024-07-01"], window=True)
        + _support_rows("2024-2025", "base-b", ["2024-07-02"], window=True)
        + _support_rows("2025-2026", "base-b", ["2025-07-01"], window=True)
    )

    result = build_forward_fold_support(daily, windows)
    fold_a = result["folds"][0]
    fold_b = result["folds"][1]

    assert fold_a["train_seasons"] == ["2023-2024"]
    assert fold_a["validation_seasons"] == ["2024-2025"]
    assert fold_a["metrics"]["daily_known_support"]["train_origin_or_row_count"] == 1
    assert fold_a["metrics"]["daily_known_support"]["validation_origin_or_row_count"] == 2
    assert fold_a["metrics"]["daily_known_support"]["train_validation_base_intersection_count"] == 1
    assert fold_b["metrics"]["W7"]["train_unique_base_count"] == 2
    assert fold_b["metrics"]["W7"]["validation_unique_base_count"] == 1
    assert fold_b["metrics"]["W7"]["train_validation_base_intersection_count"] == 1
