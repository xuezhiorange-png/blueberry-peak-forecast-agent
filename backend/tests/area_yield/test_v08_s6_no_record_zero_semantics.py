from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal

import pytest

from backend.app.area_yield.v08_s5_quantity_completeness import (
    SeasonBoundary,
    build_quantity_authority_outputs,
)
from backend.app.area_yield.v08_s6_no_record_zero import (
    NoRecordZeroSemanticsError,
    apply_no_record_zero_semantics,
    apply_s6_season_total_authority,
)

SEASON = "2025-2026"
SOURCE_HASH = "a" * 64
BOUNDARY = {SEASON: (date(2025, 7, 22), date(2025, 7, 24))}
HASHES = {SEASON: SOURCE_HASH}


def _quality(
    *,
    identity_status: str = "IDENTITY_CONFIRMED",
    accepted_labels: tuple[str, ...] = ("member-a", "member-b"),
    unresolved_labels: tuple[str, ...] = (),
) -> dict[str, str]:
    return {
        "base_id": "base-1",
        "canonical_base_name": "Base One",
        "season": SEASON,
        "source_identity_status": identity_status,
        "accepted_source_label_count": str(len(accepted_labels)),
        "accepted_source_labels": json.dumps(accepted_labels),
        "unresolved_candidate_source_labels": json.dumps(unresolved_labels),
    }


def _daily(
    day: str,
    *,
    status: str = "UNKNOWN",
    completeness: str = "UNKNOWN_NOT_ZERO_FILLED",
    quantity: str = "",
    source_rows: int = 0,
    contributing_labels: int = 0,
    unknown_possible: bool = True,
) -> dict[str, str]:
    return {
        "base_id": "base-1",
        "canonical_base_name": "Base One",
        "season": SEASON,
        "source_sha256": SOURCE_HASH,
        "date": day,
        "scope": "BUSINESS_WINDOW",
        "quantity_status": status,
        "mapped_observed_subtotal_kg": quantity,
        "quantity_completeness_status": completeness,
        "unknown_component_possible": str(unknown_possible).lower(),
        "source_row_count": str(source_rows),
        "contributing_source_label_count": str(contributing_labels),
        "confirmed_zero_basis": "",
        "identity_authority_id": "CROSS_SEASON_BASE_IDENTITY_AUTHORITY_R1",
        "identity_authority_sha256": "b" * 64,
    }


def _apply(
    daily_rows: list[dict[str, str]],
    *,
    quality: dict[str, str] | None = None,
) -> dict[str, object]:
    return apply_no_record_zero_semantics(
        daily_rows=daily_rows,
        quality_rows=[quality or _quality()],
        boundaries=BOUNDARY,
        source_hashes=HASHES,
        expected_base_count=1,
    )


def test_expected_identity_confirmed_day_without_rows_becomes_authorized_zero() -> None:
    result = _apply([_daily("2025-07-22"), _daily("2025-07-23"), _daily("2025-07-24")])
    converted = [row for row in result["overlay_rows"] if row["zero_applied"] == "true"]
    assert len(converted) == 3
    assert {row["new_quantity_status"] for row in converted} == {"CONFIRMED_ZERO"}
    assert {row["new_completeness_status"] for row in converted} == {"AUTHORIZED_ZERO"}
    assert {row["zero_basis"] for row in converted} == {
        "EXPLICIT_BUSINESS_RULE_NO_HARVEST_RECORD_MEANS_ZERO"
    }


def test_unresolved_source_identity_prevents_zero_conversion() -> None:
    quality = _quality(
        identity_status="IDENTITY_CONFIRMED_WITH_UNRESOLVED_CANDIDATES",
        unresolved_labels=("unresolved-label",),
    )
    result = _apply([_daily("2025-07-22")], quality=quality)
    row = result["overlay_rows"][0]
    assert row["new_quantity_status"] == "UNKNOWN"
    assert row["zero_applied"] == "false"
    assert result["unknown_decomposition_rows"][0]["unknown_reason_before"] == (
        "UNRESOLVED_SOURCE_IDENTITY_MAY_CONFLICT_WITH_BASE_DAY"
    )


def test_missing_known_members_are_zero_and_partial_day_becomes_complete() -> None:
    daily = _daily(
        "2025-07-22",
        status="KNOWN_MAPPED_SUBTOTAL",
        completeness="PARTIAL_KNOWN_SUBTOTAL",
        quantity="100.000",
        source_rows=1,
        contributing_labels=1,
    )
    result = _apply([daily])
    row = result["overlay_rows"][0]
    assert row["new_quantity_kg"] == "100.000"
    assert row["new_completeness_status"] == "COMPLETE_MAPPED_MEMBERS"
    assert row["partial_resolved"] == "true"
    assert result["counts"]["partial_resolved_by_zero_count"] == 1


def test_unresolved_candidate_keeps_partial_subtotal_partial() -> None:
    quality = _quality(
        identity_status="IDENTITY_CONFIRMED_WITH_UNRESOLVED_CANDIDATES",
        unresolved_labels=("unresolved-label",),
    )
    daily = _daily(
        "2025-07-22",
        status="KNOWN_MAPPED_SUBTOTAL",
        completeness="PARTIAL_KNOWN_SUBTOTAL",
        quantity="100",
        source_rows=1,
        contributing_labels=1,
    )
    result = _apply([daily], quality=quality)
    assert result["overlay_rows"][0]["new_completeness_status"] == "PARTIAL_KNOWN_SUBTOTAL"
    assert result["overlay_rows"][0]["partial_resolved"] == "false"


def test_missing_canonical_daily_row_is_not_reclassified_as_zero() -> None:
    result = _apply([_daily("2025-07-22")])
    row = next(row for row in result["overlay_rows"] if row["date"] == "2025-07-23")
    assert row["old_quantity_status"] == "NO_CANONICAL_DAILY_ROW"
    assert row["new_quantity_status"] == "UNKNOWN"
    assert row["zero_applied"] == "false"


def test_existing_authorized_zero_remains_scoreable() -> None:
    zero = _daily(
        "2025-07-22",
        status="CONFIRMED_ZERO",
        completeness="AUTHORIZED_ZERO",
        quantity="0",
        unknown_possible=False,
    )
    result = _apply([zero])
    assert result["overlay_rows"][0]["authority_eligible_daily"] == "true"
    assert result["overlay_rows"][0]["zero_applied"] == "false"


def test_unknown_with_a_source_row_is_not_zeroed() -> None:
    row = _daily("2025-07-22", source_rows=1, contributing_labels=1)
    result = _apply([row])
    assert result["overlay_rows"][0]["new_quantity_status"] == "UNKNOWN"
    assert result["unknown_decomposition_rows"][0]["unknown_reason_before"] == (
        "UNKNOWN_WITH_SOURCE_ROWS"
    )


def test_source_hash_mismatch_fails_closed() -> None:
    row = _daily("2025-07-22")
    row["source_sha256"] = "c" * 64
    with pytest.raises(NoRecordZeroSemanticsError, match="DAILY_SOURCE_HASH_MISMATCH"):
        _apply([row])


def test_unaccepted_source_identity_stays_unknown() -> None:
    quality = _quality(
        identity_status="NO_ACCEPTED_SOURCE_ROWS",
        accepted_labels=(),
    )
    result = _apply([_daily("2025-07-22")], quality=quality)
    assert result["overlay_rows"][0]["new_quantity_status"] == "UNKNOWN"
    assert result["unknown_decomposition_rows"][0]["unknown_reason_before"] == (
        "NO_ACCEPTED_SOURCE_IDENTITY_FOR_BASE_SEASON"
    )


def test_source_row_counts_cannot_claim_more_members_than_frozen_universe() -> None:
    row = _daily(
        "2025-07-22",
        status="KNOWN_MAPPED_SUBTOTAL",
        completeness="COMPLETE_MAPPED_MEMBERS",
        quantity="10",
        source_rows=3,
        contributing_labels=3,
    )
    with pytest.raises(NoRecordZeroSemanticsError, match="DAILY_MEMBER_ROW_COUNTS_INCONSISTENT"):
        _apply([row])


def test_zero_conversion_never_changes_nonzero_harvest_mass() -> None:
    rows = [
        _daily(
            "2025-07-22",
            status="KNOWN_MAPPED_SUBTOTAL",
            completeness="COMPLETE_MAPPED_MEMBERS",
            quantity="12.345",
            source_rows=2,
            contributing_labels=2,
            unknown_possible=False,
        ),
        _daily("2025-07-23"),
        _daily("2025-07-24"),
    ]
    result = _apply(rows)
    before = sum(
        (
            Decimal(row["mapped_observed_subtotal_kg"])
            for row in rows
            if row["quantity_status"] == "KNOWN_MAPPED_SUBTOTAL"
        ),
        Decimal(0),
    )
    after = sum(
        (
            Decimal(row["mapped_observed_subtotal_kg"])
            for row in result["transformed_daily_rows"]
            if row["quantity_status"] == "KNOWN_MAPPED_SUBTOTAL"
        ),
        Decimal(0),
    )
    assert before == after == Decimal("12.345")


def test_unknown_and_partial_reclassification_counts_conserve() -> None:
    rows = [
        _daily("2025-07-22"),
        _daily(
            "2025-07-23",
            status="KNOWN_MAPPED_SUBTOTAL",
            completeness="PARTIAL_KNOWN_SUBTOTAL",
            quantity="5",
            source_rows=1,
            contributing_labels=1,
        ),
        _daily(
            "2025-07-24",
            status="KNOWN_MAPPED_SUBTOTAL",
            completeness="PARTIAL_KNOWN_SUBTOTAL",
            quantity="6",
            source_rows=1,
            contributing_labels=1,
        ),
    ]
    result = _apply(rows)
    counts = result["counts"]
    assert (
        counts["unknown_day_count_before"]
        == counts["zero_converted_from_no_record_count"] + counts["unknown_day_count_after"]
    )
    assert (
        counts["partial_day_count_before"]
        == counts["partial_resolved_by_zero_count"] + counts["partial_day_count_after"]
    )


def test_no_record_zero_count_only_increments_confirmed_zeros() -> None:
    result = _apply([_daily("2025-07-22"), _daily("2025-07-23"), _daily("2025-07-24")])
    assert result["counts"]["confirmed_zero_day_count_before"] == 0
    assert result["counts"]["confirmed_zero_day_count_after"] == 3


def test_excluded_status_is_preserved_and_never_zeroed() -> None:
    row = _daily(
        "2025-07-22",
        status="EXCLUDED",
        completeness="EXCLUDED_BY_AUTHORITY",
        quantity="",
    )
    result = _apply([row])
    assert result["overlay_rows"][0]["new_quantity_status"] == "EXCLUDED"
    assert result["overlay_rows"][0]["zero_applied"] == "false"


def test_replay_is_byte_stable_for_overlay_payloads() -> None:
    rows = [_daily("2025-07-22"), _daily("2025-07-23"), _daily("2025-07-24")]
    first = _apply(rows)
    second = _apply(rows)
    assert first == second


@pytest.fixture(scope="module")
def full_three_season_overlay_inputs() -> dict[str, object]:
    windows = {
        "2023-2024": (
            date(2023, 7, 1),
            date(2024, 4, 15),
            "FROZEN_CROSS_SEASON_AUDIT_WINDOW_R1",
            "c" * 64,
        ),
        "2024-2025": (
            date(2024, 7, 1),
            date(2025, 4, 15),
            "FROZEN_CROSS_SEASON_AUDIT_WINDOW_R1",
            "c" * 64,
        ),
        "2025-2026": (
            date(2025, 7, 22),
            date(2026, 4, 15),
            "USER_CONFIRMED_2526_BUSINESS_WINDOW_R7B",
            "d" * 64,
        ),
    }
    date_boundaries = {
        season: (start, end) for season, (start, end, _authority, _sha) in windows.items()
    }
    boundaries = {
        season: SeasonBoundary(season, start, end, authority, source_sha)
        for season, (start, end, authority, source_sha) in windows.items()
    }
    source_hashes = {season: "e" * 64 for season in windows}
    daily_rows: list[dict[str, str]] = []
    quality_rows: list[dict[str, str]] = []
    area_rows: list[dict[str, str]] = []
    quantity_per_base = Decimal("1.25")

    for season, (start, end) in date_boundaries.items():
        day_count = (end - start).days + 1
        for base_number in range(39):
            base_id = f"base-{base_number:02d}"
            base_name = f"Base {base_number:02d}"
            member = f"member-{base_number:02d}-{season}"
            is_business_total_row = season == "2023-2024" and base_number == 0
            quality_rows.append(
                {
                    "base_id": base_id,
                    "canonical_base_name": base_name,
                    "season": season,
                    "source_identity_status": "IDENTITY_CONFIRMED",
                    "accepted_source_label_count": "1",
                    "accepted_source_labels": json.dumps([member]),
                    "unresolved_candidate_source_labels": "[]",
                    "business_window_calendar_day_count": str(day_count),
                    "business_window_mapped_quantity_kg": str(quantity_per_base),
                    "business_total_coverage_status": (
                        "BUSINESS_TOTAL_AUTHORITY_ELIGIBLE"
                        if is_business_total_row
                        else "NOT_AUTHORIZED"
                    ),
                    "season_total_complete": str(is_business_total_row).lower(),
                }
            )
            area_rows.append(
                {
                    "base_id": base_id,
                    "canonical_base_name": base_name,
                    "season": season,
                    "historical_actual_area_mu": "100",
                    "area_status": "BUSINESS_CONFIRMED_HISTORICAL_ACTUAL",
                    "authority_eligible": "true",
                    "identity_authority_id": "CROSS_SEASON_BASE_IDENTITY_AUTHORITY_R1",
                }
            )
            current_day = start
            while current_day <= end:
                has_harvest = current_day == start
                daily_rows.append(
                    {
                        "base_id": base_id,
                        "canonical_base_name": base_name,
                        "season": season,
                        "source_sha256": source_hashes[season],
                        "date": current_day.isoformat(),
                        "scope": "BUSINESS_WINDOW",
                        "quantity_status": "KNOWN_MAPPED_SUBTOTAL" if has_harvest else "UNKNOWN",
                        "mapped_observed_subtotal_kg": str(quantity_per_base)
                        if has_harvest
                        else "",
                        "quantity_completeness_status": (
                            "COMPLETE_MAPPED_MEMBERS" if has_harvest else "UNKNOWN_NOT_ZERO_FILLED"
                        ),
                        "unknown_component_possible": str(not has_harvest).lower(),
                        "source_row_count": "1" if has_harvest else "0",
                        "contributing_source_label_count": "1" if has_harvest else "0",
                        "confirmed_zero_basis": "" if has_harvest else "",
                        "identity_authority_id": "CROSS_SEASON_BASE_IDENTITY_AUTHORITY_R1",
                        "identity_authority_sha256": "f" * 64,
                    }
                )
                current_day += timedelta(days=1)

    totals = {
        season: {
            "raw_source_kg": str(quantity_per_base * 39),
            "mapped_kg": str(quantity_per_base * 39),
            "unresolved_kg": "0",
            "explicitly_excluded_kg": "0",
            "business_window_mapped_kg": str(quantity_per_base * 39),
        }
        for season in windows
    }
    return {
        "date_boundaries": date_boundaries,
        "boundaries": boundaries,
        "source_hashes": source_hashes,
        "daily_rows": daily_rows,
        "quality_rows": quality_rows,
        "area_rows": area_rows,
        "season_totals": totals,
    }


def _build_three_season_outputs(
    fixture: dict[str, object], quality_rows: list[dict[str, str]] | None = None
) -> tuple[dict[str, object], dict[str, object]]:
    transformed = apply_no_record_zero_semantics(
        daily_rows=fixture["daily_rows"],
        quality_rows=quality_rows or fixture["quality_rows"],
        boundaries=fixture["date_boundaries"],
        source_hashes=fixture["source_hashes"],
        expected_base_count=39,
    )
    outputs = build_quantity_authority_outputs(
        daily_rows=transformed["transformed_daily_rows"],
        quality_rows=quality_rows or fixture["quality_rows"],
        area_rows=fixture["area_rows"],
        boundaries=fixture["boundaries"],
        season_totals=fixture["season_totals"],
        unresolved_identity_rows=[],
        expected_season_base_count=39,
    )
    outputs = apply_s6_season_total_authority(
        quantity_outputs=outputs,
        quality_rows=quality_rows or fixture["quality_rows"],
        area_rows=fixture["area_rows"],
        training_seasons=frozenset({"2023-2024", "2024-2025"}),
        oot_season="2025-2026",
    )
    return transformed, outputs


def test_full_daily_zero_overlay_releases_expected_training_and_oot_scope(
    full_three_season_overlay_inputs: dict[str, object],
) -> None:
    transformed, outputs = _build_three_season_outputs(full_three_season_overlay_inputs)
    eligible = outputs["eligibility_rows"]
    assert len(transformed["overlay_rows"]) == 33033
    assert transformed["counts"]["partial_resolved_by_zero_count"] == 0
    assert sum(row["strict_training_eligible"] == "true" for row in eligible) == 78
    assert sum(row["strict_oot_eligible"] == "true" for row in eligible) == 39
    completeness = outputs["completeness_rows"]
    assert sum(row["season_total_training_eligible"] == "true" for row in completeness) == 117
    assert sum(row["daily_curve_evaluation_eligible"] == "true" for row in completeness) == 117
    assert outputs["business_total_reconciled_count"] == 1
    assert outputs["business_total_mismatch_count"] == 0


def test_business_total_mismatch_fails_closed_after_complete_daily_rebuild(
    full_three_season_overlay_inputs: dict[str, object],
) -> None:
    quality_rows = [dict(row) for row in full_three_season_overlay_inputs["quality_rows"]]
    target = next(
        row for row in quality_rows if row["base_id"] == "base-00" and row["season"] == "2023-2024"
    )
    target["business_window_mapped_quantity_kg"] = "2.25"
    transformed, outputs = _build_three_season_outputs(
        full_three_season_overlay_inputs, quality_rows=quality_rows
    )
    target_eligibility = next(
        row
        for row in outputs["eligibility_rows"]
        if row["base_id"] == "base-00" and row["season"] == "2023-2024"
    )
    assert outputs["business_total_mismatch_count"] == 1
    assert target_eligibility["season_total_training_eligible"] == "false"
    assert transformed["counts"]["unknown_day_count_after"] == 0
