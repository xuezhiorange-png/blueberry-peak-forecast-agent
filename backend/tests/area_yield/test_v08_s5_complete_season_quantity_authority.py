from __future__ import annotations

import copy
import json
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest

from backend.app.area_yield.v08_s5_quantity_completeness import (
    SEASONS,
    QuantityAuthorityError,
    SeasonBoundary,
    build_quantity_authority_outputs,
)

_STARTS = {
    "2023-2024": date(2023, 7, 1),
    "2024-2025": date(2024, 7, 1),
    "2025-2026": date(2025, 7, 22),
}


def _inputs(
    *,
    base_ids: tuple[str, ...] = ("base-a",),
    day_overrides: dict[tuple[str, str], list[tuple[str, str, str | None]]] | None = None,
    business_totals: dict[tuple[str, str], str] | None = None,
    identity_overrides: dict[tuple[str, str], tuple[str, list[str]]] | None = None,
) -> dict[str, Any]:
    day_overrides = day_overrides or {}
    business_totals = business_totals or {}
    identity_overrides = identity_overrides or {}
    boundaries = {
        season: SeasonBoundary(
            season=season,
            start=start,
            end=start + timedelta(days=2),
            authority_id=f"FROZEN_TEST_BOUNDARY_{season}",
            authority_sha256="a" * 64,
        )
        for season, start in _STARTS.items()
    }
    daily_rows: list[dict[str, str]] = []
    quality_rows: list[dict[str, str]] = []
    area_rows: list[dict[str, str]] = []
    sums_by_season: dict[str, Decimal] = defaultdict(Decimal)

    for base_id in base_ids:
        for season in SEASONS:
            specs = day_overrides.get(
                (base_id, season),
                [
                    ("KNOWN_MAPPED_SUBTOTAL", "COMPLETE_MAPPED_MEMBERS", "10"),
                    ("KNOWN_MAPPED_SUBTOTAL", "COMPLETE_MAPPED_MEMBERS", "10"),
                    ("KNOWN_MAPPED_SUBTOTAL", "COMPLETE_MAPPED_MEMBERS", "10"),
                ],
            )
            daily_sum = Decimal(0)
            for offset, (status, completeness, quantity) in enumerate(specs):
                day = boundaries[season].start + timedelta(days=offset)
                if status == "KNOWN_MAPPED_SUBTOTAL":
                    daily_sum += Decimal(quantity or "0")
                daily_rows.append(
                    {
                        "base_id": base_id,
                        "season": season,
                        "date": day.isoformat(),
                        "quantity_status": status,
                        "quantity_completeness_status": completeness,
                        "mapped_observed_subtotal_kg": quantity or "",
                        "source_row_count": "1",
                        "contributing_source_label_count": (
                            "1" if completeness == "COMPLETE_MAPPED_MEMBERS" else "0"
                        ),
                        "source_sha256": "b" * 64,
                        "identity_authority_id": "CROSS_SEASON_BASE_IDENTITY_AUTHORITY_R1",
                        "identity_authority_sha256": "c" * 64,
                    }
                )
            sums_by_season[season] += daily_sum
            identity_status, unresolved_labels = identity_overrides.get(
                (base_id, season), ("IDENTITY_CONFIRMED", [])
            )
            has_business_total = (base_id, season) in business_totals
            quality_rows.append(
                {
                    "base_id": base_id,
                    "canonical_base_name": base_id,
                    "season": season,
                    "business_window_calendar_day_count": "3",
                    "business_window_mapped_quantity_kg": business_totals.get(
                        (base_id, season), str(daily_sum)
                    ),
                    "accepted_source_label_count": "1",
                    "accepted_source_labels": '["member-a"]',
                    "unresolved_candidate_source_labels": json.dumps(
                        unresolved_labels, separators=(",", ":")
                    ),
                    "source_identity_status": identity_status,
                    "business_total_coverage_status": (
                        "BUSINESS_TOTAL_AUTHORITY_ELIGIBLE"
                        if has_business_total
                        else "NOT_ESTABLISHED_NO_FROZEN_TOTAL_AUTHORITY"
                    ),
                    "season_total_complete": str(has_business_total).lower(),
                }
            )
            area_rows.append(
                {
                    "base_id": base_id,
                    "season": season,
                    "historical_actual_area_mu": "100.00",
                    "area_status": "BUSINESS_CONFIRMED_HISTORICAL_ACTUAL",
                    "authority_eligible": "true",
                    "identity_authority_id": "CROSS_SEASON_BASE_IDENTITY_AUTHORITY_R1",
                }
            )

    season_totals = {
        season: {
            "raw_source_kg": str(sums_by_season[season]),
            "mapped_kg": str(sums_by_season[season]),
            "unresolved_kg": "0",
            "explicitly_excluded_kg": "0",
            "business_window_mapped_kg": str(sums_by_season[season]),
        }
        for season in SEASONS
    }
    return {
        "daily_rows": daily_rows,
        "quality_rows": quality_rows,
        "area_rows": area_rows,
        "boundaries": boundaries,
        "season_totals": season_totals,
        "unresolved_identity_rows": [],
    }


def _run(inputs: dict[str, Any], *, expected_base_count: int = 1) -> dict[str, Any]:
    return build_quantity_authority_outputs(
        **inputs, expected_season_base_count=expected_base_count
    )


def _season_row(outputs: dict[str, Any], season: str = "2023-2024") -> dict[str, str]:
    return next(row for row in outputs["completeness_rows"] if row["season"] == season)


@pytest.mark.parametrize("zero_status", ["AUTHORIZED_ZERO", "COMPLETE_SOURCE_ROWS_ZERO"])
def test_complete_daily_window_and_authorized_zero_establish_season_total(
    zero_status: str,
) -> None:
    inputs = _inputs(
        day_overrides={
            ("base-a", "2023-2024"): [
                ("KNOWN_MAPPED_SUBTOTAL", "COMPLETE_MAPPED_MEMBERS", "10"),
                ("CONFIRMED_ZERO", zero_status, "0"),
                ("KNOWN_MAPPED_SUBTOTAL", "COMPLETE_MAPPED_MEMBERS", "5"),
            ]
        }
    )

    row = _season_row(_run(inputs))

    assert row["daily_curve_evaluation_eligible"] == "true"
    assert row["season_total_training_eligible"] == "true"
    assert row["complete_season_total_quantity_kg"] == "15"
    assert row["confirmed_zero_day_count"] == 1


def test_partial_day_blocks_daily_and_derived_season_total() -> None:
    inputs = _inputs(
        day_overrides={
            ("base-a", "2023-2024"): [
                ("KNOWN_MAPPED_SUBTOTAL", "COMPLETE_MAPPED_MEMBERS", "10"),
                ("KNOWN_MAPPED_SUBTOTAL", "PARTIAL_KNOWN_SUBTOTAL", "50"),
                ("KNOWN_MAPPED_SUBTOTAL", "COMPLETE_MAPPED_MEMBERS", "10"),
            ]
        }
    )

    row = _season_row(_run(inputs))

    assert row["daily_curve_evaluation_eligible"] == "false"
    assert row["season_total_training_eligible"] == "false"
    assert row["partial_known_subtotal_day_count"] == 1
    assert row["partial_known_quantity_kg"] == "50"
    assert row["complete_season_total_quantity_kg"] == ""


def test_business_total_can_be_eligible_while_daily_coverage_is_incomplete() -> None:
    inputs = _inputs(
        day_overrides={
            ("base-a", "2023-2024"): [
                ("KNOWN_MAPPED_SUBTOTAL", "COMPLETE_MAPPED_MEMBERS", "10"),
                ("KNOWN_MAPPED_SUBTOTAL", "PARTIAL_KNOWN_SUBTOTAL", "5"),
                ("UNKNOWN", "UNKNOWN_NOT_ZERO_FILLED", None),
            ]
        },
        business_totals={("base-a", "2023-2024"): "500"},
    )

    row = _season_row(_run(inputs))

    assert row["daily_curve_evaluation_eligible"] == "false"
    assert row["season_total_training_eligible"] == "true"
    assert row["quantity_authority_status"] == (
        "BUSINESS_TOTAL_AUTHORITY_PRESENT_DAILY_COVERAGE_INCOMPLETE"
    )
    assert row["complete_season_total_quantity_kg"] == "500"
    assert row["unknown_quantity_kg_or_null"] == "null"


def test_unknown_quantity_remains_null_and_blocks_daily_derived_total() -> None:
    inputs = _inputs(
        day_overrides={
            ("base-a", "2023-2024"): [
                ("KNOWN_MAPPED_SUBTOTAL", "COMPLETE_MAPPED_MEMBERS", "10"),
                ("UNKNOWN", "UNKNOWN_NOT_ZERO_FILLED", None),
                ("KNOWN_MAPPED_SUBTOTAL", "COMPLETE_MAPPED_MEMBERS", "10"),
            ]
        }
    )

    outputs = _run(inputs)
    row = _season_row(outputs)
    unknown_gap = next(gap for gap in outputs["gap_rows"] if gap["date"] == "2023-07-02")

    assert row["unknown_day_count"] == 1
    assert row["unknown_quantity_kg_or_null"] == "null"
    assert row["season_total_training_eligible"] == "false"
    assert unknown_gap["known_quantity_kg_or_null"] == "null"
    assert "UNKNOWN_DAYS_PRESENT" in row["blocker_codes"]


def test_identity_unresolved_blocks_daily_derived_total() -> None:
    inputs = _inputs(
        identity_overrides={
            ("base-a", "2023-2024"): (
                "IDENTITY_CONFIRMED_WITH_UNRESOLVED_CANDIDATES",
                ["unresolved-member"],
            )
        }
    )

    row = _season_row(_run(inputs))

    assert row["season_total_training_eligible"] == "false"
    assert row["quantity_authority_status"] == "NO_COMPLETE_SEASON_TOTAL_AUTHORITY"
    assert "IDENTITY_UNRESOLVED" in row["blocker_codes"]


def test_authoritative_business_total_mismatch_with_complete_daily_sum_fails_closed() -> None:
    inputs = _inputs(business_totals={("base-a", "2023-2024"): "31"})

    outputs = _run(inputs)

    row = _season_row(outputs)
    assert row["quantity_authority_status"] == "BUSINESS_TOTAL_DAILY_SUM_MISMATCH"
    assert row["season_total_training_eligible"] == "false"
    assert outputs["business_total_mismatch_count"] == 1


def test_unestablished_boundary_blocks_season_total() -> None:
    inputs = _inputs()
    inputs["boundaries"].pop("2023-2024")

    row = _season_row(_run(inputs))

    assert row["season_boundary_complete"] == "false"
    assert row["season_total_training_eligible"] == "false"
    assert "SEASON_BOUNDARY_NOT_ESTABLISHED" in row["blocker_codes"]


def test_78_area_qualified_training_rows_are_not_an_area_blocker() -> None:
    inputs = _inputs(base_ids=tuple(f"base-{number:02d}" for number in range(39)))
    outputs = _run(inputs, expected_base_count=39)

    training = [
        row for row in outputs["eligibility_rows"] if row["season"] in {"2023-2024", "2024-2025"}
    ]

    assert len(training) == 78
    assert sum(row["strict_training_eligible"] == "true" for row in training) == 78


def test_five_complete_quantity_rows_produce_five_strict_training_rows() -> None:
    base_ids = tuple(f"base-{number}" for number in range(1, 6))
    overrides = {
        (base_id, season): [
            ("UNKNOWN", "UNKNOWN_NOT_ZERO_FILLED", None),
            ("UNKNOWN", "UNKNOWN_NOT_ZERO_FILLED", None),
            ("UNKNOWN", "UNKNOWN_NOT_ZERO_FILLED", None),
        ]
        for base_id in base_ids
        for season in SEASONS
    }
    for base_id, season in zip(base_ids, ("2023-2024",) * 3 + ("2024-2025",) * 2, strict=True):
        overrides[(base_id, season)] = [
            ("KNOWN_MAPPED_SUBTOTAL", "COMPLETE_MAPPED_MEMBERS", "10")
        ] * 3
    inputs = _inputs(base_ids=base_ids, day_overrides=overrides)

    outputs = _run(inputs, expected_base_count=5)
    eligible = [
        row for row in outputs["eligibility_rows"] if row["strict_training_eligible"] == "true"
    ]

    assert len(eligible) == 5


def test_source_quantity_conservation_is_reported_and_not_silently_corrected() -> None:
    inputs = _inputs()
    inputs["season_totals"]["2023-2024"]["raw_source_kg"] = "31"

    outputs = _run(inputs)

    conservation = next(row for row in outputs["conservation_rows"] if row["season"] == "2023-2024")
    assert conservation["raw_conservation_delta_kg"] == "1"
    assert conservation["raw_conservation_pass"] == "false"


def test_deterministic_replay_returns_identical_authority_rows() -> None:
    inputs = _inputs()

    first = _run(inputs)
    second = _run(inputs)

    assert first == second
    assert first["quantity_overlay_rows"] == second["quantity_overlay_rows"]


def test_frozen_authority_input_rows_are_not_mutated() -> None:
    inputs = _inputs()
    before = copy.deepcopy(inputs)

    _run(inputs)

    assert inputs == before


def test_duplicate_base_season_authority_is_rejected() -> None:
    inputs = _inputs()
    inputs["area_rows"].append(dict(inputs["area_rows"][0]))

    with pytest.raises(QuantityAuthorityError, match="DUPLICATE_AREA_IDENTITY"):
        _run(inputs)
