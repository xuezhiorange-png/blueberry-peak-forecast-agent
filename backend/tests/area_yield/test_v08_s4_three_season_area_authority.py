from __future__ import annotations

from decimal import Decimal

import pytest

from backend.app.area_yield.v08_s4_three_season_area_authority import (
    AREA_AUTHORITY_ID,
    BASE_COUNT,
    BUSINESS_CONFIRMATION_ID,
    SEASONS,
    TRAINING_SEASONS,
    build_area_authority_rows,
    build_quantity_eligibility_rows,
    reconcile_legacy_area_evidence,
    serialize_csv_rows,
    validate_area_snapshot,
)

AREA_SOURCE_SHA256 = "73329a1f7315f81ce7cf24d59dc7b3a49507520cd179a205b7267a5b430db7d7"
IDENTITY_SHA256 = "7054c4168fac8342022527ab3ba017eb8e0b2c57409eb0e6dba166e6f181c61b"
BUSINESS_CONFIRMATION = {
    "confirmation_record_id": BUSINESS_CONFIRMATION_ID,
    "decision": "USE_RECOVERED_39_BASE_41335_MU_FOR_ALL_THREE_SEASONS",
    "base_count": 39,
    "total_area_mu": "41335",
    "seasons": list(SEASONS),
    "area_values_same_across_seasons": True,
    "decision_type": "EXPLICIT_BUSINESS_CONFIRMATION",
    "area_estimation": False,
    "cross_season_inference": False,
}


def _source_rows() -> list[dict[str, str]]:
    areas = [Decimal("394"), Decimal("922")] + [Decimal("1000")] * 36 + [Decimal("4019")]
    assert len(areas) == BASE_COUNT
    rows: list[dict[str, str]] = []
    for index, area in enumerate(areas):
        rows.append(
            {
                "source_record_id": f"source-record-{index:02d}",
                "base_id": f"base-{index:02d}",
                "base_name": f"Canonical Base {index:02d}",
                "area_mu": str(area),
                "source_sha256": AREA_SOURCE_SHA256,
                "original_season_scope": "CURRENT/UNSPECIFIED",
                "source_row": str(index + 2),
            }
        )
    return rows


def _canonical_bases(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [{"base_id": row["base_id"], "canonical_base_name": row["base_name"]} for row in rows]


def _area_rows(
    sources: list[dict[str, str]] | None = None,
    confirmation: dict[str, object] | None = BUSINESS_CONFIRMATION,
    canonical_bases: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    source_rows = sources or _source_rows()
    identity = canonical_bases or _canonical_bases(source_rows)
    return build_area_authority_rows(
        source_rows,
        identity,
        confirmation,
        identity_authority_id="CROSS_SEASON_BASE_IDENTITY_AUTHORITY_R1",
        identity_authority_sha256=IDENTITY_SHA256,
    )


def _quantity_rows(area_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for area in area_rows:
        complete = area["base_id"] == "base-00" and area["season"] == "2025-2026"
        rows.append(
            {
                "base_id": area["base_id"],
                "canonical_base_name": area["canonical_base_name"],
                "season": area["season"],
                "business_total_coverage_status": (
                    "BUSINESS_TOTAL_AUTHORITY_ELIGIBLE"
                    if complete
                    else "NOT_ESTABLISHED_NO_FROZEN_TOTAL_AUTHORITY"
                ),
                "season_total_complete": "true" if complete else "false",
                "business_window_mapped_quantity_kg": "484802.056" if complete else "",
            }
        )
    return rows


def test_39_bases_expand_to_117_unique_base_season_rows() -> None:
    rows = _area_rows()
    keys = {(row["base_id"], row["season"]) for row in rows}
    assert len(rows) == 117
    assert len(keys) == 117
    assert len({row["base_id"] for row in rows}) == 39
    assert {row["season"] for row in rows} == set(SEASONS)
    assert all(row["area_authority_id"] == AREA_AUTHORITY_ID for row in rows)


def test_each_season_area_total_is_exactly_41335_mu() -> None:
    rows = _area_rows()
    for season in SEASONS:
        total = sum(
            (Decimal(row["historical_actual_area_mu"]) for row in rows if row["season"] == season),
            Decimal(0),
        )
        assert total == Decimal("41335")


def test_decimal_values_are_preserved_without_float_rounding() -> None:
    rows = _area_rows()
    values = {(row["base_id"], row["season"]): row["historical_actual_area_mu"] for row in rows}
    assert values[("base-00", "2023-2024")] == "394"
    assert values[("base-01", "2024-2025")] == "922"


def test_explicit_confirmation_resolves_original_unspecified_scope() -> None:
    rows = _area_rows()
    assert all(row["original_season_scope"] == "CURRENT/UNSPECIFIED" for row in rows)
    assert all(row["resolved_season_scope"] == ";".join(SEASONS) for row in rows)
    assert all(row["season_binding_basis"] == "EXPLICIT_BUSINESS_CONFIRMATION" for row in rows)
    assert all(row["business_confirmation_id"] == BUSINESS_CONFIRMATION_ID for row in rows)


def test_missing_business_confirmation_fails_closed() -> None:
    with pytest.raises(ValueError, match="EXPLICIT_BUSINESS_CONFIRMATION_REQUIRED"):
        _area_rows(confirmation=None)


def test_duplicate_base_area_snapshot_fails_closed() -> None:
    sources = _source_rows()
    sources[-1]["base_id"] = sources[0]["base_id"]
    with pytest.raises(ValueError, match="DUPLICATE_CONFIRMED_BASE_AREA"):
        validate_area_snapshot(sources, _canonical_bases(_source_rows()))


def test_unresolved_or_mismatched_canonical_identity_fails_closed() -> None:
    sources = _source_rows()
    identities = _canonical_bases(sources[:-1])
    with pytest.raises(ValueError, match="BASE_IDENTITY_UNRESOLVED"):
        validate_area_snapshot(sources, identities)


def test_area_snapshot_sum_mismatch_fails_closed() -> None:
    sources = _source_rows()
    sources[0]["area_mu"] = "395"
    with pytest.raises(ValueError, match="CONFIRMED_AREA_TOTAL_MISMATCH"):
        validate_area_snapshot(sources, _canonical_bases(sources))


def test_member_area_is_supporting_detail_not_base_area_override() -> None:
    area_rows = _area_rows()
    base = next(
        row for row in area_rows if row["base_id"] == "base-01" and row["season"] == "2025-2026"
    )
    legacy = [
        {
            "legacy_record_id": "legacy-member",
            "base_id": "base-01",
            "base_name": base["canonical_base_name"],
            "season": "2025-2026",
            "grain": "MEMBER",
            "old_area_mu": "152.35",
            "source_id": "business-confirmation-member",
            "source_sha256": "a" * 64,
        }
    ]
    reconciled = reconcile_legacy_area_evidence(legacy, area_rows)
    assert reconciled[0]["reconciliation_status"] == "MEMBER_AREA_SUPPORTING_DETAIL"
    assert reconciled[0]["new_confirmed_base_area_mu"] == base["historical_actual_area_mu"]
    assert reconciled[0]["legacy_grain"] == "MEMBER"


def test_member_area_less_than_base_does_not_create_conflict() -> None:
    area_rows = _area_rows()
    legacy = [
        {
            "legacy_record_id": "legacy-member",
            "base_id": "base-01",
            "base_name": "Canonical Base 01",
            "season": "2025-2026",
            "grain": "MEMBER",
            "old_area_mu": "152.35",
            "source_id": "business-confirmation-member",
            "source_sha256": "a" * 64,
        }
    ]
    assert reconcile_legacy_area_evidence(legacy, area_rows)[0]["reconciliation_status"] == (
        "MEMBER_AREA_SUPPORTING_DETAIL"
    )


def test_member_area_greater_than_base_creates_consistency_blocker() -> None:
    area_rows = _area_rows()
    legacy = [
        {
            "legacy_record_id": "legacy-member",
            "base_id": "base-01",
            "base_name": "Canonical Base 01",
            "season": "2025-2026",
            "grain": "MEMBER",
            "old_area_mu": "1000",
            "source_id": "business-confirmation-member",
            "source_sha256": "a" * 64,
        }
    ]
    assert reconcile_legacy_area_evidence(legacy, area_rows)[0]["reconciliation_status"] == (
        "MEMBER_AREA_EXCEEDS_CONFIRMED_BASE_AREA_BLOCKER"
    )


def test_legacy_base_value_difference_is_explicitly_superseded() -> None:
    area_rows = _area_rows()
    legacy = [
        {
            "legacy_record_id": "legacy-base",
            "base_id": "base-00",
            "base_name": "Canonical Base 00",
            "season": "2025-2026",
            "grain": "BASE",
            "old_area_mu": "393.4",
            "source_id": "legacy-confirmed-base",
            "source_sha256": "b" * 64,
        }
    ]
    result = reconcile_legacy_area_evidence(legacy, area_rows)[0]
    assert result["reconciliation_status"] == (
        "LEGACY_AREA_EVIDENCE_SUPERSEDED_BY_EXPLICIT_BUSINESS_CONFIRMATION"
    )
    assert result["old_area_mu"] == "393.4"
    assert result["new_confirmed_base_area_mu"] == "394"


def test_all_117_area_rows_are_training_area_qualified_in_two_training_seasons() -> None:
    rows = _area_rows()
    training_count = sum(row["season"] in TRAINING_SEASONS for row in rows)
    assert training_count == 78
    assert all(row["authority_eligible"] == "true" for row in rows)


def test_all_39_oot_area_rows_are_qualified() -> None:
    rows = _area_rows()
    assert sum(row["season"] == "2025-2026" for row in rows) == 39


def test_incomplete_quantity_authority_blocks_strict_training() -> None:
    area_rows = _area_rows()
    eligibility = build_quantity_eligibility_rows(area_rows, _quantity_rows(area_rows))
    row = next(
        row for row in eligibility if row["base_id"] == "base-00" and row["season"] == "2023-2024"
    )
    assert row["area_eligible"] == "true"
    assert row["quantity_eligible"] == "false"
    assert row["strict_training_eligible"] == "false"
    assert row["exclusion_reason"] == "COMPLETE_SEASON_TOTAL_AUTHORITY_MISSING"


def test_complete_quantity_authority_intersects_with_area_for_training_and_oot() -> None:
    area_rows = _area_rows()
    quantity_rows = _quantity_rows(area_rows)
    quantity_rows[0]["business_total_coverage_status"] = "BUSINESS_TOTAL_AUTHORITY_ELIGIBLE"
    quantity_rows[0]["season_total_complete"] = "true"
    eligibility = build_quantity_eligibility_rows(area_rows, quantity_rows)
    row = next(
        row for row in eligibility if row["base_id"] == "base-00" and row["season"] == "2023-2024"
    )
    assert row["strict_training_eligible"] == "true"
    assert row["strict_oot_eligible"] == "false"
    assert row["exclusion_reason"] == "ELIGIBLE"


def test_incomplete_quantity_never_becomes_eligible_from_area_only() -> None:
    area_rows = _area_rows()
    eligibility = build_quantity_eligibility_rows(area_rows, _quantity_rows(area_rows))
    assert sum(row["area_eligible"] == "true" for row in eligibility) == 117
    assert sum(row["strict_training_eligible"] == "true" for row in eligibility) == 0


def test_expected_oot_quantity_row_is_not_mislabeled_as_training() -> None:
    area_rows = _area_rows()
    eligibility = build_quantity_eligibility_rows(area_rows, _quantity_rows(area_rows))
    row = next(
        row for row in eligibility if row["base_id"] == "base-00" and row["season"] == "2025-2026"
    )
    assert row["quantity_eligible"] == "true"
    assert row["strict_oot_eligible"] == "true"
    assert row["strict_training_eligible"] == "false"
    assert row["exclusion_reason"] == "NOT_TRAINING_SEASON"


def test_quantity_matrix_missing_or_duplicate_key_fails_closed() -> None:
    area_rows = _area_rows()
    quantity_rows = _quantity_rows(area_rows)[:-1]
    with pytest.raises(ValueError, match="QUANTITY_AUTHORITY_KEYSET_MISMATCH"):
        build_quantity_eligibility_rows(area_rows, quantity_rows)


def test_csv_serialization_is_deterministic() -> None:
    rows = _area_rows()
    fields = tuple(rows[0])
    assert serialize_csv_rows(rows, fields) == serialize_csv_rows(list(reversed(rows)), fields)
