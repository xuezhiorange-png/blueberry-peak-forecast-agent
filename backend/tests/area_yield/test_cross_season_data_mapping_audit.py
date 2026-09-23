from datetime import date
from decimal import Decimal
from hashlib import sha256
from typing import Any

import pytest

from scripts import audit_cross_season_data_mapping as audit


def _source_row(
    *, season: str, row_number: int, farm: str, subfarm: str, quantity: str, day: date
) -> audit.SourceRow:
    values = {
        "season": season,
        "row_number": row_number,
        "farm": farm,
        "subfarm": subfarm,
        "quantity": quantity,
        "day": day.isoformat(),
    }
    return audit.SourceRow(
        season=season,
        sheet="fixture",
        row_number=row_number,
        event_date=day,
        company="Organization A",
        farm=farm,
        subfarm=subfarm,
        cultivar="Cultivar A",
        fruit_size="Size A",
        quantity_kg=Decimal(quantity),
        raw_record_hash=sha256(audit._canonical_bytes(values)).hexdigest(),
    )


def _fixture(*, cross_season_assignment_change: bool = False) -> dict[str, Any]:
    base_ids = [f"base-{index:02}" for index in range(39)]
    base_names = {base_id: f"Base {index:02}" for index, base_id in enumerate(base_ids)}
    source_rows = [
        _source_row(
            season="2023-2024",
            row_number=1,
            farm="Mapped A",
            subfarm="Sub A1",
            quantity="2",
            day=date(2024, 3, 1),
        ),
        _source_row(
            season="2023-2024",
            row_number=2,
            farm="Mapped A",
            subfarm="Sub A2",
            quantity="3",
            day=date(2024, 3, 2),
        ),
        _source_row(
            season="2023-2024",
            row_number=3,
            farm="Candidate U",
            subfarm="",
            quantity="13",
            day=date(2024, 3, 3),
        ),
        _source_row(
            season="2024-2025",
            row_number=4,
            farm="Mapped A",
            subfarm="Sub A1",
            quantity="7",
            day=date(2025, 3, 1),
        ),
        _source_row(
            season="2025-2026",
            row_number=5,
            farm="Mapped A",
            subfarm="Sub A1",
            quantity="11",
            day=date(2026, 3, 1),
        ),
        _source_row(
            season="2025-2026",
            row_number=6,
            farm="Mapped A",
            subfarm="Sub A1",
            quantity="1",
            day=date(2026, 4, 16),
        ),
    ]
    first_season_target = "base-01" if cross_season_assignment_change else "base-00"
    second_season_target = "base-00" if cross_season_assignment_change else "base-00"
    historical_rows = [
        {
            "season": season,
            "source_farm_label": "Mapped A",
            "candidate_base_id": target,
            "candidate_base": base_names[target],
            "match_type": "EXACT",
            "decision": "ACCEPTED",
            "evidence": "fixture authority row",
        }
        for season, target in (
            ("2023-2024", first_season_target),
            ("2024-2025", second_season_target),
        )
    ]
    historical_rows.append(
        {
            "season": "2023-2024",
            "source_farm_label": "Candidate U",
            "candidate_base_id": "base-01;base-02",
            "candidate_base": "Base 01;Base 02",
            "match_type": "UNRESOLVED",
            "decision": "REQUIRES_BUSINESS_CONFIRMATION",
            "evidence": "ambiguous fixture candidate only",
        }
    )
    matrix_rows = []
    mapped_totals = {"2023-2024": Decimal("5"), "2024-2025": Decimal("7")}
    for season in ("2023-2024", "2024-2025"):
        target = first_season_target if season == "2023-2024" else second_season_target
        for base_id in base_ids:
            accepted_labels = ["Mapped A"] if base_id == target else []
            ambiguous_labels = (
                ["Candidate U"]
                if season == "2023-2024" and base_id in {"base-01", "base-02"}
                else []
            )
            matrix_rows.append(
                {
                    "season": season,
                    "base_id": base_id,
                    "accepted_source_labels": ";".join(accepted_labels),
                    "accepted_mapped_kg": str(
                        mapped_totals[season] if accepted_labels else Decimal(0)
                    ),
                    "proposed_source_labels": "",
                    "ambiguous_proposed_source_labels": ";".join(ambiguous_labels),
                    "quantity_eligibility": "NOT_STRICT_COMPLETE_SEASON",
                    "identity_mapping_status": "ACCEPTED_OR_NO_ACCEPTED_LABEL",
                }
            )
    members = [
        {
            "historical_farm_identity": "Candidate U",
            "matched_base_id": "base-01;base-02",
            "canonical_base_name": "Base 01;Base 02",
            "match_status": "UNRESOLVED",
            "match_method": "CANDIDATE_ONLY",
            "evidence": "fixture candidate only",
        }
    ]
    if not cross_season_assignment_change:
        members.append(
            {
                "historical_farm_identity": "Mapped A",
                "matched_base_id": "base-00",
                "canonical_base_name": "Base 00",
                "match_status": "EXACT",
                "match_method": "EXACT",
                "evidence": "fixture current authority row",
            }
        )
    season_source_totals = {"2023-2024": Decimal("18"), "2024-2025": Decimal("7")}
    coverage = {
        "coverage_by_season": [
            {
                "season": season,
                "source_total_kg": str(season_source_totals[season]),
                "mapped_kg": str(mapped_totals[season]),
            }
            for season in season_source_totals
        ],
        "area_authority_adjudication": {"history_rows": []},
    }
    registry = {
        "bases": [
            {
                "base_id": base_id,
                "canonical_base_name": base_names[base_id],
                "productive_area_mu": "100",
            }
            for base_id in base_ids
        ]
    }
    return {
        "source_rows": source_rows,
        "historical_rows": historical_rows,
        "matrix_rows": matrix_rows,
        "coverage": coverage,
        "members": members,
        "registry": registry,
        "source_hashes": dict(audit.EXPECTED_SOURCE_HASHES),
        "authority_hashes": dict(audit.EXPECTED_AUTHORITY_HASHES),
    }


def _run(fixture: dict[str, Any]) -> dict[str, Any]:
    return audit.build_audit(
        fixture["source_rows"],
        fixture["historical_rows"],
        fixture["matrix_rows"],
        fixture["coverage"],
        fixture["members"],
        fixture["registry"],
        {},
        fixture["source_hashes"],
        fixture["authority_hashes"],
    )


@pytest.mark.unit
def test_ambiguous_candidates_remain_unresolved_not_conflicting() -> None:
    mapping = audit._mapping_record(
        "2023-2024",
        "Candidate U",
        {
            ("2023-2024", "Candidate U"): {
                "match_type": "UNRESOLVED",
                "decision": "REQUIRES_BUSINESS_CONFIRMATION",
                "candidate_base_id": "base-01;base-02",
                "candidate_base": "Base 01;Base 02",
            }
        },
        {},
    )

    assert mapping["status"] == "UNRESOLVED"
    assert mapping["base_id"] == ""
    assert mapping["candidate_base_id"] == "base-01;base-02"


@pytest.mark.unit
def test_conflicting_accepted_authorities_fail_closed() -> None:
    mapping = audit._mapping_record(
        "2023-2024",
        "Mapped A",
        {
            ("2023-2024", "Mapped A"): {
                "match_type": "EXACT",
                "decision": "ACCEPTED",
                "candidate_base_id": "base-00",
                "candidate_base": "Base 00",
                "evidence": "historical fixture authority",
            }
        },
        {
            "Mapped A": {
                "match_status": "EXACT",
                "matched_base_id": "base-01",
                "canonical_base_name": "Base 01",
            }
        },
    )

    assert mapping["status"] == "CONFLICTING"
    assert mapping["base_id"] == ""


@pytest.mark.unit
def test_raw_quantity_conserves_without_parent_pair_double_count_or_zero_fill() -> None:
    result = _run(_fixture())
    summary = result["summary"]

    assert summary["quantity_reconciliation_pass"] is True
    assert summary["raw_total_kg"] == "37"
    assert summary["mapped_total_kg"] == "24"
    assert summary["unresolved_total_kg"] == "13"
    assert summary["explicitly_excluded_total_kg"] == "0"
    for season, expected_total in (("2023-2024", "18"), ("2024-2025", "7")):
        row = summary["per_season"][season]
        assert row["raw_total_kg"] == expected_total
        assert row["farm_aggregate_total_kg"] == expected_total
        assert row["farm_subfarm_pair_aggregate_total_kg"] == expected_total
        assert row["exact_duplicate_raw_row_count"] == 0

    unresolved = [
        row for row in result["source_identity_ledger"] if row["source_farm_label"] == "Candidate U"
    ]
    assert len(unresolved) == 1
    assert unresolved[0]["current_mapping_status"] == "UNRESOLVED"
    assert unresolved[0]["quantity_kg"] == "13"


@pytest.mark.unit
def test_out_of_window_source_rows_are_retained_but_not_in_business_subtotal() -> None:
    result = _run(_fixture())
    season = result["summary"]["per_season"]["2025-2026"]
    quality = next(
        row
        for row in result["base_season_quality"]
        if row["base_id"] == "base-00" and row["season"] == "2025-2026"
    )

    assert season["raw_total_kg"] == "12"
    assert season["business_window"]["raw_in_window_kg"] == "11"
    assert season["business_window"]["raw_outside_window_kg"] == "1"
    assert quality["source_total_mapped_quantity_kg"] == "12"
    assert quality["business_window_mapped_quantity_kg"] == "11"


@pytest.mark.unit
def test_same_source_label_mapped_to_different_bases_is_reported_not_rewritten() -> None:
    result = _run(_fixture(cross_season_assignment_change=True))
    summary = result["summary"]

    assert summary["same_label_different_base_count"] == 1
    assert summary["same_label_different_base"][0]["source_label"] == "Mapped A"
    assert summary["same_label_different_base"][0]["classification"] == "POSSIBLE_ORG_CHANGE"
    assert summary["cross_season_mapping_status"] == "REQUIRES_BUSINESS_CONFIRMATION"


@pytest.mark.unit
def test_exact_source_row_identity_assigned_to_multiple_bases_is_detected() -> None:
    rows = [
        _source_row(
            season="2023-2024",
            row_number=9,
            farm="Mapped A",
            subfarm="",
            quantity="2",
            day=date(2024, 3, 1),
        ),
        _source_row(
            season="2023-2024",
            row_number=9,
            farm="Mapped B",
            subfarm="",
            quantity="3",
            day=date(2024, 3, 1),
        ),
    ]
    mappings = {
        ("2023-2024", farm): {"status": "EXACT", "base_id": base_id}
        for farm, base_id in (("Mapped A", "base-00"), ("Mapped B", "base-01"))
    }

    assert audit._multi_assigned_source_row_bases(rows, mappings) == {
        ("2023-2024", "fixture", 9): ["base-00", "base-01"]
    }
