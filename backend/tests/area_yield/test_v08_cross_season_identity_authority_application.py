"""Contracts for applying frozen cross-season business identity decisions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import apply_v0_8_cross_season_identity_authority as authority


def _proposal_row(**overrides: str) -> dict[str, str]:
    row = {
        "season": "2024-2025",
        "source_farm_label": "Farm A",
        "source_subfarm_label": "Subfarm A",
        "old_status": "UNRESOLVED",
        "old_base_id": "",
        "proposed_status": "UNRESOLVED",
        "proposed_base_id": "",
        "proposed_base_name": "",
        "decision_question": "",
        "business_decision": "",
        "change_type": "NO_CHANGE",
        "quantity_kg": "10.25",
        "business_window_quantity_kg": "9.75",
    }
    row.update(overrides)
    return row


def _decision_rows() -> list[dict[str, str]]:
    rows = []
    for question in ("Q07", "Q10", "Q14", "Q17", "Q26"):
        rows.append(
            {
                "question_number": question,
                "decision_2023_2024": "",
                "decision_2024_2025": "",
                "decision_2025_2026": "",
                "split_rule": "",
                "future_effective_rule": "",
            }
        )
    by_question = {row["question_number"]: row for row in rows}
    by_question["Q14"].update(decision_2024_2025="NO_CANDIDATE", decision_2025_2026="YES_CANDIDATE")
    by_question["Q17"].update(
        decision_2024_2025="SPLIT_RULE",
        decision_2025_2026="SPLIT_RULE",
        split_rule='{"2024-2025":{"Farm B":"Base B"}}',
    )
    by_question["Q26"].update(
        decision_2024_2025="CORRECT_BASE:Base C",
        future_effective_rule="SEASON_SCOPED_ONLY",
    )
    return rows


def _valid_decision_application() -> tuple[list[dict[str, str]], dict[str, int]]:
    rows = [
        _proposal_row(
            season="2024-2025",
            source_farm_label="Q14 prior",
            source_subfarm_label="Sub 14",
            old_candidate_base_id="BASE-OLD",
            decision_question="Q14",
            business_decision="Q14:NO_CANDIDATE",
            change_type="REJECT_CANDIDATE_KEEP_UNRESOLVED",
        ),
        _proposal_row(
            season="2025-2026",
            source_farm_label="Q14 target",
            source_subfarm_label="Sub 14",
            proposed_status="PROPOSED_MAPPED_NON_AUTHORITY",
            proposed_base_id="BASE-14",
            decision_question="Q14",
            business_decision="Q14:YES_CANDIDATE",
            change_type="RESOLVE_UNRESOLVED",
        ),
        _proposal_row(
            source_farm_label="Q17 listed",
            proposed_status="PROPOSED_MAPPED_NON_AUTHORITY",
            proposed_base_id="BASE-17",
            decision_question="Q17",
            business_decision="Q17:SPLIT_RULE",
            change_type="SPLIT_RELATION",
        ),
        _proposal_row(
            source_farm_label="Q17 unlisted",
            decision_question="Q17",
            business_decision="Q17:SPLIT_RULE",
            change_type="NO_CHANGE",
        ),
        _proposal_row(
            season="2025-2026",
            source_farm_label="Parent correction",
            old_status="AUTHORIZED_ALIAS",
            old_base_id="BASE-P",
            proposed_status="AUTHORIZED_ALIAS",
            proposed_base_id="BASE-P",
            decision_question="Q07",
            business_decision="Q07:CORRECT_PARENT",
            change_type="PARENT_CORRECTION",
        ),
        _proposal_row(
            source_farm_label="Q26 mapped",
            proposed_status="PROPOSED_MAPPED_NON_AUTHORITY",
            proposed_base_id="BASE-C",
            proposed_base_name="Base C",
            decision_question="Q26",
            business_decision="Q26:CORRECT_BASE:Base C",
            change_type="RESOLVE_UNRESOLVED",
        ),
    ]
    build_info = {
        "q17_target_row_count": 1,
        "q17_unhandled_source_label_keys": [("2024-2025", "Q17 unlisted")],
        "parent_correction_row_count": 1,
    }
    audit_rows = [
        {
            "season": row["season"],
            "source_farm_label": row["source_farm_label"],
            "source_subfarm_label": row["source_subfarm_label"],
            "quantity_kg": row["quantity_kg"],
            "business_window_quantity_kg": row["business_window_quantity_kg"],
        }
        for row in rows
    ]
    return rows, build_info, audit_rows


def test_quantity_status_preserves_missing_zero_and_partial_semantics() -> None:
    assert (
        authority.daily_quantity_status(
            source_rows_present=False,
            mapped_quantity=authority.Decimal(0),
            all_mapped_members_observed=False,
            unresolved_candidate=False,
            prior_confirmed_zero=False,
            r7b_confirmed_zero=False,
        )[0]
        == "UNKNOWN"
    )
    assert (
        authority.daily_quantity_status(
            source_rows_present=True,
            mapped_quantity=authority.Decimal(0),
            all_mapped_members_observed=True,
            unresolved_candidate=False,
            prior_confirmed_zero=False,
            r7b_confirmed_zero=False,
        )[0]
        == "CONFIRMED_ZERO"
    )
    partial = authority.daily_quantity_status(
        source_rows_present=True,
        mapped_quantity=authority.Decimal("4.5"),
        all_mapped_members_observed=False,
        unresolved_candidate=False,
        prior_confirmed_zero=False,
        r7b_confirmed_zero=False,
    )
    assert partial == (
        "KNOWN_MAPPED_SUBTOTAL",
        "PARTIAL_KNOWN_SUBTOTAL",
        True,
        "RAW_SOURCE_MAPPED_ROWS",
    )


def test_authorized_prior_zero_requires_unchanged_membership_at_callsite() -> None:
    assert authority.daily_quantity_status(
        source_rows_present=False,
        mapped_quantity=authority.Decimal(0),
        all_mapped_members_observed=False,
        unresolved_candidate=False,
        prior_confirmed_zero=True,
        r7b_confirmed_zero=False,
    ) == ("CONFIRMED_ZERO", "AUTHORIZED_ZERO", False, "REUSED_UNCHANGED_MEMBERSHIP_ZERO")


def test_quantity_reconciliation_fails_closed() -> None:
    assert authority.validate_conservation(
        authority.Decimal("100"),
        authority.Decimal("60"),
        authority.Decimal("30"),
        authority.Decimal("10"),
    ) == authority.Decimal(0)
    with pytest.raises(ValueError, match="QUANTITY_RECONCILIATION_FAILED"):
        authority.validate_conservation(
            authority.Decimal("100"),
            authority.Decimal("61"),
            authority.Decimal("30"),
            authority.Decimal("10"),
        )


def test_season_scoped_decisions_and_parent_correction_are_preserved() -> None:
    proposals, build_info, audit_rows = _valid_decision_application()
    result = authority._validate_business_decision_application(
        _decision_rows(), proposals, build_info, audit_rows
    )
    assert result["q14_prior_no_candidate_rows_remain_unresolved"] == 1
    assert result["q14_target_season_rows_with_candidate"] == 1
    assert result["q17_split_relation_rows"] == 1
    assert result["q07_q10_parent_corrections_reallocate_quantity"] is False
    assert result["q26_decisions_are_season_scoped"] is True


def test_q14_prior_no_candidate_cannot_fall_back_to_another_base() -> None:
    proposals, build_info, audit_rows = _valid_decision_application()
    proposals[0]["proposed_status"] = "PROPOSED_MAPPED_NON_AUTHORITY"
    proposals[0]["proposed_base_id"] = "BASE-FALLBACK"
    with pytest.raises(ValueError, match="Q14_SEASON_SCOPED_DECISION_APPLICATION_INVALID"):
        authority._validate_business_decision_application(
            _decision_rows(), proposals, build_info, audit_rows
        )


def test_q17_unlisted_label_and_q26_unapproved_season_fail_closed() -> None:
    proposals, build_info, audit_rows = _valid_decision_application()
    proposals[3]["proposed_base_id"] = "BASE-UNLISTED"
    with pytest.raises(ValueError, match="Q17_UNLISTED_SOURCE_LABEL_WAS_MAPPED"):
        authority._validate_business_decision_application(
            _decision_rows(), proposals, build_info, audit_rows
        )

    proposals, build_info, audit_rows = _valid_decision_application()
    proposals[-1]["season"] = "2025-2026"
    audit_rows[-1]["season"] = "2025-2026"
    with pytest.raises(ValueError, match="Q26_RULE_PROPAGATED_OUTSIDE_EXPLICIT_SEASON"):
        authority._validate_business_decision_application(
            _decision_rows(), proposals, build_info, audit_rows
        )


def test_parent_correction_cannot_reassign_base_or_change_source_quantity() -> None:
    proposals, build_info, audit_rows = _valid_decision_application()
    proposals[4]["proposed_base_id"] = "BASE-OTHER"
    with pytest.raises(ValueError, match="PARENT_CORRECTION_CHANGED_QUANTITY_ASSIGNMENT"):
        authority._validate_business_decision_application(
            _decision_rows(), proposals, build_info, audit_rows
        )

    proposals, build_info, audit_rows = _valid_decision_application()
    audit_rows[0]["quantity_kg"] = "99"
    with pytest.raises(ValueError, match="BUSINESS_DECISION_CHANGED_SOURCE_QUANTITY"):
        authority._validate_business_decision_application(
            _decision_rows(), proposals, build_info, audit_rows
        )


def test_same_farm_label_cannot_map_to_multiple_bases_in_one_season() -> None:
    common = {
        "season": "2024-2025",
        "source_farm_label": "Same farm",
        "old_status": "UNRESOLVED",
        "old_base_id": "",
        "proposed_status": "PROPOSED_MAPPED_NON_AUTHORITY",
        "old_candidate_base_id": "",
        "decision_question": "Q01",
        "business_decision": "Q01:CORRECT_BASE",
    }
    proposals = [
        {**common, "source_subfarm_label": "Sub 1", "proposed_base_id": "BASE-1"},
        {**common, "source_subfarm_label": "Sub 2", "proposed_base_id": "BASE-2"},
    ]
    audit = [
        {
            "season": row["season"],
            "source_farm_label": row["source_farm_label"],
            "source_subfarm_label": row["source_subfarm_label"],
        }
        for row in proposals
    ]
    with pytest.raises(ValueError, match="SAME_SEASON_FARM_LABEL_HAS_MULTIPLE_APPLIED_BASES"):
        authority._mapping_rows(proposals, audit)


def test_flat_hash_manifest_verifies_every_artifact_and_fails_on_change(tmp_path: Path) -> None:
    artifact = tmp_path / "frozen.bin"
    artifact.write_bytes(b"frozen payload")
    manifest = tmp_path / "artifact_manifest.json"
    manifest.write_text(
        json.dumps({"frozen.bin": authority.sha256_file(artifact)}), encoding="utf-8"
    )
    manifest_hash = authority.sha256_file(manifest)
    assert authority._verify_flat_hash_manifest(tmp_path, manifest.name, manifest_hash) == {
        "frozen.bin": authority.sha256_file(artifact)
    }

    artifact.write_bytes(b"changed payload")
    with pytest.raises(ValueError, match="HASH_MANIFEST_ARTIFACT_MISMATCH"):
        authority._verify_flat_hash_manifest(tmp_path, manifest.name, manifest_hash)


def test_business_season_windows_are_fixed_and_2025_start_is_r7b() -> None:
    assert authority.SEASON_WINDOWS["2023-2024"] == (
        authority.date(2023, 7, 1),
        authority.date(2024, 4, 15),
    )
    assert authority.SEASON_WINDOWS["2024-2025"] == (
        authority.date(2024, 7, 1),
        authority.date(2025, 4, 15),
    )
    assert authority.SEASON_WINDOWS["2025-2026"] == (
        authority.date(2025, 7, 22),
        authority.date(2026, 4, 15),
    )


def test_r7b_coverage_authority_cannot_propagate_to_other_seasons() -> None:
    r7b = {"Repeated farm label": {"season": "2025-2026", "total_evaluable": "True"}}
    assert authority._r7b_rows_for_base_season("2023-2024", ["Repeated farm label"], r7b) == []
    assert authority._r7b_rows_for_base_season("2024-2025", ["Repeated farm label"], r7b) == []
    assert authority._r7b_rows_for_base_season("2025-2026", ["Repeated farm label"], r7b) == [
        r7b["Repeated farm label"]
    ]
