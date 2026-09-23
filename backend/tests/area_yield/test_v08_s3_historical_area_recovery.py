from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.recover_v0_8_historical_area_authority import (
    RecoveryError,
    _direct_area_bindings,
    _identity_index,
    build_artifacts,
    build_candidate_authority,
    build_conflict_ledger,
    build_source_recovery_ledger,
)


def _fixture_inputs() -> dict:
    quality = []
    for season in ("2023-2024", "2024-2025", "2025-2026"):
        for index in range(39):
            base_id = f"base-{index:02d}"
            quality.append(
                {
                    "base_id": base_id,
                    "canonical_base_name": f"基地{index:02d}",
                    "season": season,
                    "historical_actual_productive_area_mu": "",
                    "historical_actual_productive_area_status": "NOT_ESTABLISHED",
                    "business_total_coverage_status": "NOT_COMPUTABLE",
                    "season_total_complete": "false",
                }
            )
    quality[2 * 39]["business_total_coverage_status"] = "BUSINESS_TOTAL_AUTHORITY_ELIGIBLE"
    quality[2 * 39]["season_total_complete"] = "true"
    identities = [
        {
            "season": "2025-2026",
            "source_farm_label": "农场甲",
            "mapping_status": "EXACT",
            "canonical_base_id": "base-00",
            "canonical_base_name": "基地00",
            "identity_revision_id": "revision-1",
        },
        {
            "season": "2025-2026",
            "source_farm_label": "农场甲旧名",
            "mapping_status": "AUTHORIZED_ALIAS",
            "canonical_base_id": "base-00",
            "canonical_base_name": "基地00",
            "identity_revision_id": "revision-2",
        },
    ]
    source_records = [
        {
            "record_id": "area-1",
            "source_kind": "AREA_YIELD_AUTHORITY",
            "source_file": "/private/authority.json",
            "source_hash": "area-authority-hash",
            "season": "2025-2026",
            "source_original_name": "农场甲",
            "farm_identity": "农场甲",
            "area_mu": "12.5",
            "area_semantics": "ACTUAL_PRODUCTIVE_AREA",
            "area_basis": "BUSINESS_CONFIRMED",
            "mapped_base_id": "base-00",
            "mapped_base": "基地00",
            "authority_eligibility": "DIRECT_CURRENT_SEASON_AUTHORITY_ONLY",
            "decision": "DIRECT_AUTHORITY_CANDIDATE",
            "sheet": "history",
            "source_row": "1",
        }
    ]
    return {
        "source_records": source_records,
        "identity_rows": identities,
        "quality_rows": quality,
        "area_authority": {
            "aliases": {"农场甲旧名": "农场甲"},
            "history": [
                {
                    "farm": "农场甲",
                    "season": "2025-2026",
                    "area_basis": "BUSINESS_CONFIRMED",
                    "historical_area_mu": "12.5",
                    "source_hash": "harvest-source-hash",
                }
            ],
        },
        "qualification_rows": [
            {
                "canonical_farm": "农场甲",
                "season": "2025-2026",
                "source_hash": "harvest-source-hash",
                "area_basis": "BUSINESS_CONFIRMED",
                "productive_area_mu": "12.5",
                "area_bound": "True",
            }
        ],
        "area_confirmation_2023": [],
        "area_confirmation_2024": [],
        "hashes": {
            "source_inventory": "source-inventory-hash",
            "source_manifest": "source-manifest-hash",
            "identity": "identity-authority-hash",
            "quality": "quality-ledger-hash",
            "area_authority": "area-authority-hash",
            "r7b_manifest": "r7b-manifest-hash",
            "r7b_qualification": "r7b-qualification-hash",
        },
        "verified_source_file_count": 1,
    }


def _direct_bindings(inputs: dict) -> list[dict]:
    return _direct_area_bindings(
        area_authority=inputs["area_authority"],
        qualification_rows=inputs["qualification_rows"],
        identity_index=_identity_index(inputs["identity_rows"]),
        source_records=inputs["source_records"],
        area_authority_sha256=inputs["hashes"]["area_authority"],
        identity_authority_sha256=inputs["hashes"]["identity"],
    )


def test_business_confirmed_area_rebinds_through_current_accepted_alias_only() -> None:
    inputs = _fixture_inputs()
    bindings = _direct_bindings(inputs)

    assert len(bindings) == 1
    assert bindings[0]["base_id"] == "base-00"
    assert bindings[0]["season"] == "2025-2026"
    assert bindings[0]["area_mu"] == "12.5"
    assert bindings[0]["identity_authority_sha256"] == "identity-authority-hash"


def test_missing_current_canonical_identity_fails_closed() -> None:
    inputs = _fixture_inputs()
    inputs["identity_rows"] = []

    with pytest.raises(RecoveryError, match="AREA_IDENTITY_REBIND_NOT_UNIQUE"):
        _direct_bindings(inputs)


def test_season_specific_area_is_not_propagated_to_other_seasons() -> None:
    inputs = _fixture_inputs()
    bindings = _direct_bindings(inputs)
    source_ledger = build_source_recovery_ledger(
        source_records=inputs["source_records"],
        identity_rows=inputs["identity_rows"],
        direct_bindings=bindings,
        area_authority_sha256=inputs["hashes"]["area_authority"],
    )
    candidates = build_candidate_authority(
        quality_rows=inputs["quality_rows"],
        source_ledger=source_ledger,
        direct_bindings=bindings,
        area_conflicts=[],
    )
    base_rows = [row for row in candidates if row["base_id"] == "base-00"]

    assert [(row["season"], row["historical_actual_productive_area_mu"]) for row in base_rows] == [
        ("2023-2024", ""),
        ("2024-2025", ""),
        ("2025-2026", "12.5"),
    ]
    assert sum(row["training_area_eligible"] for row in base_rows) == 0


def test_conflicting_candidate_values_are_retained_not_averaged() -> None:
    inputs = _fixture_inputs()
    source_ledger = [
        {
            "current_canonical_base_id": "base-00",
            "season_raw": "2024-2025",
            "source_record_id": "candidate-1",
            "area_mu_raw": "100",
            "source_sha256": "hash-1",
        },
        {
            "current_canonical_base_id": "base-00",
            "season_raw": "2024-2025",
            "source_record_id": "candidate-2",
            "area_mu_raw": "120",
            "source_sha256": "hash-2",
        },
    ]
    conflict_rows = [
        {
            "base_id": "base-00",
            "base_name": "基地00",
            "season_id": "2024-2025",
            "current_decision": "CONFLICTING_EVIDENCE",
            "analysis_report_candidate_areas_mu": "100;120",
            "candidate_difference_mu": "20",
        }
    ]
    conflicts = build_conflict_ledger(conflict_rows, source_ledger)
    candidates = build_candidate_authority(
        quality_rows=inputs["quality_rows"],
        source_ledger=source_ledger,
        direct_bindings=[],
        area_conflicts=conflict_rows,
    )
    row = next(r for r in candidates if r["base_id"] == "base-00" and r["season"] == "2024-2025")

    assert len(conflicts) == 1
    assert row["area_status"] == "CONFLICTING_EVIDENCE"
    assert row["historical_actual_productive_area_mu"] == ""
    assert row["candidate_area_values_mu"] == ["100", "120"]


def test_confirmation_required_is_not_misclassified_as_conflict() -> None:
    inputs = _fixture_inputs()
    source_ledger = [
        {
            "current_canonical_base_id": "base-00",
            "season_raw": "2024-2025",
            "source_record_id": "proxy-1",
            "area_mu_raw": "968",
            "source_sha256": "proxy-hash",
        }
    ]
    review_rows = [
        {
            "base_id": "base-00",
            "base_name": "基地00",
            "season_id": "2024-2025",
            "current_decision": "BUSINESS_CONFIRMATION_REQUIRED",
            "previous_season_proxy_area_mu": "968",
        }
    ]

    candidates = build_candidate_authority(
        quality_rows=inputs["quality_rows"],
        source_ledger=source_ledger,
        direct_bindings=[],
        area_conflicts=review_rows,
    )
    row = next(r for r in candidates if r["base_id"] == "base-00" and r["season"] == "2024-2025")

    assert row["area_status"] == "REFERENCE_AREA_ONLY"
    assert row["conflict_status"] == "NONE"
    assert row["historical_actual_productive_area_mu"] == ""


def test_reference_and_unseasoned_sources_do_not_become_historical_area() -> None:
    inputs = _fixture_inputs()
    inputs["source_records"].append(
        {
            "record_id": "current-area",
            "source_kind": "BASE_REGISTRY_JSON",
            "source_file": "/private/registry.json",
            "source_hash": "registry-hash",
            "season": "CURRENT/UNSPECIFIED",
            "source_original_name": "基地00",
            "farm_identity": "农场甲",
            "area_mu": "999",
            "area_semantics": "CURRENT_AREA",
            "area_basis": "USER_AUTHORIZED_PRODUCTIVE_AREA",
            "mapped_base_id": "base-00",
            "authority_eligibility": "CURRENT_BASE_REGISTRY_ONLY_NOT_HISTORICAL_BACKFILL",
            "decision": "BUSINESS_CONFIRMATION_REQUIRED",
            "sheet": "bases",
            "source_row": "1",
        }
    )
    ledger = build_source_recovery_ledger(
        source_records=inputs["source_records"],
        identity_rows=inputs["identity_rows"],
        direct_bindings=_direct_bindings(inputs),
        area_authority_sha256=inputs["hashes"]["area_authority"],
    )

    assert ledger[-1]["season_binding_status"] == "SEASON_NOT_ESTABLISHED"
    candidates = build_candidate_authority(
        quality_rows=inputs["quality_rows"],
        source_ledger=ledger,
        direct_bindings=[],
        area_conflicts=[],
    )
    historical = [r for r in candidates if r["base_id"] == "base-00"]
    assert all(r["historical_actual_productive_area_mu"] == "" for r in historical)


def test_complete_candidate_matrix_and_manifest_bytes_are_deterministic() -> None:
    first, second = _fixture_inputs(), _fixture_inputs()

    artifacts_a = build_artifacts(first)
    artifacts_b = build_artifacts(second)

    assert artifacts_a == artifacts_b
    assert len(artifacts_a["canonical-historical-area-authority-r1.csv"].splitlines()) == 118


def test_duplicate_area_values_for_same_base_season_do_not_silently_select() -> None:
    inputs = _fixture_inputs()
    bindings = _direct_bindings(inputs)
    conflicting = deepcopy(bindings[0])
    conflicting["area_mu"] = "13.5"
    conflicting["source_record_id"] = "area-2"
    rows = build_candidate_authority(
        quality_rows=inputs["quality_rows"],
        source_ledger=[],
        direct_bindings=[*bindings, conflicting],
        area_conflicts=[],
    )
    row = next(r for r in rows if r["base_id"] == "base-00" and r["season"] == "2025-2026")

    assert row["area_status"] == "CONFLICTING_EVIDENCE"
    assert row["historical_actual_productive_area_mu"] == ""
