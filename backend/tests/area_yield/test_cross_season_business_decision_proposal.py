"""Regression tests for private business-decision capture and proposal simulation."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from scripts.propose_cross_season_identity_authority import (
    ACCEPTED_STATUSES,
    DECISION_SOURCE,
    PROPOSAL_FIELDS,
    build_proposal,
    build_public_evidence,
    simulate_mapping,
    verify_decisions,
)


def _priority_row(question: int, **updates: str) -> dict[str, str]:
    row = {
        "group_id": f"GROUP-{question:02d}",
        "question_number": f"Q{question:02d}",
        "relation_type": "CROSS_SEASON_MEMBERSHIP_CHANGE",
        "owned_label_keys": "[]",
        "reference_label_keys": "[]",
        "subfarm_labels": "[]",
        "candidate_base_ids": "",
    }
    row.update(updates)
    return row


def _decision_row(question: int, **updates: str) -> dict[str, str]:
    row = {
        "group_id": f"GROUP-{question:02d}",
        "question_number": f"Q{question:02d}",
        "decision_2023_2024": "",
        "decision_2024_2025": "",
        "decision_2025_2026": "",
        "correct_base": "",
        "split_rule": "",
        "future_effective_rule": "",
        "business_comment": "",
        "confirmed_by": "",
        "confirmation_date": "2026-09-23",
        "decision_source": DECISION_SOURCE,
        "confirmed_by_status": "NOT_CAPTURED",
    }
    row.update(updates)
    return row


def _fixture() -> tuple[
    list[dict[str, str]], list[dict[str, str]], list[dict[str, str]], dict[str, str]
]:
    priority = [_priority_row(number) for number in range(1, 41)]
    decisions = [_decision_row(number) for number in range(1, 41)]
    by_priority = {row["question_number"]: row for row in priority}
    by_decision = {row["question_number"]: row for row in decisions}

    def scope(question: str, keys: list[tuple[str, str]], *, relation: str | None = None) -> None:
        row = by_priority[question]
        row["reference_label_keys"] = json.dumps(
            [{"season": season, "source_farm_label": farm} for season, farm in keys]
        )
        if relation:
            row["relation_type"] = relation

    scope("Q06", [("2023-2024", "Qiu Base"), ("2024-2025", "Qiu Farm")])
    scope("Q09", [("2023-2024", "Qiu Base"), ("2024-2025", "Qiu Farm")])
    scope("Q18", [("2023-2024", "Qiu Base"), ("2024-2025", "Qiu Base")])
    for question in ("Q06", "Q09"):
        by_decision[question]["decision_2023_2024"] = "CORRECT_BASE:Base One"
        by_decision[question]["decision_2024_2025"] = "CORRECT_BASE:Base One"
        by_decision[question]["correct_base"] = "Base One"
    by_decision["Q18"]["decision_2023_2024"] = "CORRECT_BASE:Base One"
    by_decision["Q18"]["decision_2024_2025"] = "CORRECT_BASE:Base One"

    scope(
        "Q07",
        [("2025-2026", "Wrong Parent"), ("2025-2026", "Correct Parent")],
        relation="REUSED_SUBFARM_PARENT_REVIEW",
    )
    by_priority["Q07"]["subfarm_labels"] = '["Shared Subfarm One"]'
    by_decision["Q07"]["decision_2025_2026"] = "CORRECT_PARENT:Correct Parent"
    by_decision["Q07"]["split_rule"] = json.dumps(
        {
            "2025-2026": {
                "old_parent_source_farm_label": "Wrong Parent",
                "correct_parent_source_farm_label": "Correct Parent",
                "source_subfarm_label": "Shared Subfarm One",
            }
        }
    )

    scope(
        "Q10",
        [("2025-2026", "Other Wrong Parent"), ("2025-2026", "Correct Parent")],
        relation="REUSED_SUBFARM_PARENT_REVIEW",
    )
    by_priority["Q10"]["subfarm_labels"] = '["Shared Subfarm Two"]'
    by_decision["Q10"]["decision_2025_2026"] = "CORRECT_PARENT:Correct Parent"
    by_decision["Q10"]["split_rule"] = json.dumps(
        {
            "2025-2026": {
                "old_parent_source_farm_label": "Other Wrong Parent",
                "correct_parent_source_farm_label": "Correct Parent",
                "source_subfarm_label": "Shared Subfarm Two",
            }
        }
    )

    scope("Q12", [("2024-2025", "Candidate Farm")])
    by_priority["Q12"]["candidate_base_ids"] = '["base-candidate"]'
    by_decision["Q12"]["decision_2024_2025"] = "YES_CANDIDATE"

    scope("Q14", [("2024-2025", "Seasonal Farm"), ("2025-2026", "Seasonal Farm")])
    by_priority["Q14"]["candidate_base_ids"] = '["base-seasonal"]'
    by_decision["Q14"]["decision_2024_2025"] = "NO_CANDIDATE"
    by_decision["Q14"]["decision_2025_2026"] = "YES_CANDIDATE"

    q17_keys = [
        ("2024-2025", "Farm Two"),
        ("2024-2025", "Farm Three"),
        ("2024-2025", "Farm Four"),
        ("2024-2025", "Generic Farm"),
        ("2025-2026", "Farm Two"),
        ("2025-2026", "Farm Three"),
        ("2025-2026", "Farm Four"),
        ("2025-2026", "Generic Farm"),
    ]
    scope("Q17", q17_keys)
    q17_split = {
        "2024-2025": {
            "Farm Two": "Base Two",
            "Farm Three": "Base Two",
            "Farm Four": "Base Two",
            "Generic Farm": "Base One",
        },
        "2025-2026": {
            "Farm Two": "Base Two",
            "Farm Three": "Base Two",
            "Farm Four": "Base Two",
            "Generic Farm": "Base One",
        },
    }
    by_decision["Q17"]["decision_2024_2025"] = "SPLIT_RULE"
    by_decision["Q17"]["decision_2025_2026"] = "SPLIT_RULE"
    by_decision["Q17"]["split_rule"] = json.dumps(q17_split)

    scope("Q26", [("2024-2025", "Old Region Farm"), ("2025-2026", "Current Region Farm")])
    by_decision["Q26"]["decision_2024_2025"] = "CORRECT_BASE:Base Quishi"
    by_decision["Q26"]["decision_2025_2026"] = "CORRECT_BASE:Base Zhonghe"
    by_decision["Q26"]["correct_base"] = "Base Zhonghe"
    by_decision["Q26"]["future_effective_rule"] = "2025-2026 onward: Base Zhonghe region"

    rows: list[dict[str, str]] = []

    def add(
        season: str,
        farm: str,
        subfarm: str = "",
        *,
        status: str = "EXCLUDED",
        base_id: str = "",
        base_name: str = "",
        candidate_ids: str = "",
        candidate_names: str = "",
        quantity: str = "1",
    ) -> None:
        rows.append(
            {
                "season": season,
                "source_farm_label": farm,
                "source_subfarm_label": subfarm,
                "current_mapping_status": status,
                "current_match_type": status,
                "current_candidate_base_id": candidate_ids or base_id,
                "current_canonical_base_name": candidate_names or base_name,
                "quantity_kg": quantity,
                "business_window_quantity_kg": quantity,
            }
        )

    add(
        "2023-2024",
        "Qiu Base",
        status="UNRESOLVED",
        candidate_ids="base-two;base-one",
        candidate_names="Base Two;Base One",
        quantity="11",
    )
    add(
        "2024-2025",
        "Qiu Farm",
        status="UNRESOLVED",
        candidate_ids="base-two;base-one",
        candidate_names="Base Two;Base One",
        quantity="13",
    )
    add(
        "2024-2025",
        "Qiu Base",
        status="UNRESOLVED",
        candidate_ids="base-two;base-one",
        candidate_names="Base Two;Base One",
        quantity="17",
    )

    add(
        "2025-2026",
        "Wrong Parent",
        "Shared Subfarm One",
        status="EXACT",
        base_id="base-lancang",
        base_name="Base Lancang",
        quantity="2",
    )
    add(
        "2025-2026",
        "Correct Parent",
        "Shared Subfarm One",
        status="EXACT",
        base_id="base-lancang",
        base_name="Base Lancang",
        quantity="7",
    )
    add(
        "2025-2026",
        "Other Wrong Parent",
        "Shared Subfarm Two",
        status="EXACT",
        base_id="base-lancang",
        base_name="Base Lancang",
        quantity="3",
    )
    add(
        "2025-2026",
        "Correct Parent",
        "Shared Subfarm Two",
        status="EXACT",
        base_id="base-lancang",
        base_name="Base Lancang",
        quantity="9",
    )

    add(
        "2024-2025",
        "Candidate Farm",
        status="UNRESOLVED",
        candidate_ids="base-candidate",
        candidate_names="Candidate Base",
        quantity="19",
    )
    add(
        "2024-2025",
        "Seasonal Farm",
        status="UNRESOLVED",
        candidate_ids="base-seasonal",
        candidate_names="Seasonal Base",
        quantity="23",
    )
    add(
        "2025-2026",
        "Seasonal Farm",
        status="EXACT",
        base_id="base-seasonal",
        base_name="Seasonal Base",
        quantity="29",
    )

    for season, mapping in q17_split.items():
        for farm, target in mapping.items():
            if target == "Base Two":
                add(
                    season,
                    farm,
                    status="EXACT",
                    base_id="base-two",
                    base_name="Base Two",
                    quantity="31",
                )
            elif season == "2025-2026":
                add(season, farm, status="UNRESOLVED", quantity="37")
            else:
                add(
                    season,
                    farm,
                    status="UNRESOLVED",
                    candidate_ids="base-one;base-two",
                    candidate_names="Base One;Base Two",
                    quantity="41",
                )

    add(
        "2024-2025",
        "Old Region Farm",
        status="UNRESOLVED",
        candidate_ids="base-zhonghe",
        candidate_names="Base Zhonghe",
        quantity="43",
    )
    add(
        "2025-2026",
        "Current Region Farm",
        status="EXACT",
        base_id="base-zhonghe",
        base_name="Base Zhonghe",
        quantity="47",
    )

    add(
        "2024-2025",
        "Yes All Unresolved",
        status="UNRESOLVED",
        candidate_ids="base-candidate",
        candidate_names="Candidate Base",
        quantity="53",
    )
    scope("Q01", [("2024-2025", "Yes All Unresolved")])
    by_decision["Q01"]["decision_2024_2025"] = "YES_ALL"

    while len(rows) < 466:
        index = len(rows)
        season = ("2023-2024", "2024-2025", "2025-2026")[index % 3]
        add(season, f"Filler-{index:03d}", quantity="1")
    base_names = {
        "base-one": "Base One",
        "base-two": "Base Two",
        "base-seasonal": "Seasonal Base",
        "base-candidate": "Candidate Base",
        "base-lancang": "Base Lancang",
        "base-zhonghe": "Base Zhonghe",
        "base-quishi": "Base Quishi",
    }
    assert (
        len({(r["season"], r["source_farm_label"], r["source_subfarm_label"]) for r in rows}) == 466
    )
    return rows, priority, decisions, base_names


def _find(
    proposal: list[dict[str, str]], season: str, farm: str, subfarm: str = ""
) -> dict[str, str]:
    return next(
        row
        for row in proposal
        if (row["season"], row["source_farm_label"], row["source_subfarm_label"])
        == (season, farm, subfarm)
    )


def test_all_40_decisions_are_bound_to_exact_question_and_group() -> None:
    _, priority, decisions, _ = _fixture()
    assert len(verify_decisions(decisions, priority)) == 40
    decisions[0]["confirmed_by"] = "not-authorized"
    with pytest.raises(ValueError, match="UNAUTHORIZED_CONFIRMED_BY_VALUE"):
        verify_decisions(decisions, priority)


def test_q14_season_specific_decision_does_not_flow_between_seasons() -> None:
    identity, priority, decisions, base_names = _fixture()
    proposal, _ = build_proposal(identity, priority, decisions, base_names)
    q14_prior = _find(proposal, "2024-2025", "Seasonal Farm")
    q14_current = _find(proposal, "2025-2026", "Seasonal Farm")
    assert q14_prior["proposed_status"] == "UNRESOLVED"
    assert q14_prior["proposed_base_id"] == ""
    assert q14_prior["change_type"] == "OUT_OF_SCOPE"
    assert q14_current["proposed_base_id"] == "base-seasonal"
    assert q14_current["proposed_status"] == "EXACT"


def test_q17_exact_split_and_unlisted_label_fail_closed() -> None:
    identity, priority, decisions, base_names = _fixture()
    proposal, info = build_proposal(identity, priority, decisions, base_names)
    assert _find(proposal, "2024-2025", "Farm Two")["proposed_base_id"] == "base-two"
    assert _find(proposal, "2024-2025", "Generic Farm")["proposed_base_id"] == "base-one"
    assert _find(proposal, "2025-2026", "Generic Farm")["proposed_base_id"] == "base-one"
    assert info["q17_unhandled_source_label_keys"] == []

    q17 = next(row for row in priority if row["question_number"] == "Q17")
    q17_keys = json.loads(q17["reference_label_keys"])
    q17_keys.append({"season": "2025-2026", "source_farm_label": "Unlisted Qiu Label"})
    q17["reference_label_keys"] = json.dumps(q17_keys)
    identity.pop(0)
    identity.append(
        {
            "season": "2025-2026",
            "source_farm_label": "Unlisted Qiu Label",
            "source_subfarm_label": "",
            "current_mapping_status": "UNRESOLVED",
            "current_match_type": "UNRESOLVED",
            "current_candidate_base_id": "",
            "current_canonical_base_name": "",
            "quantity_kg": "59",
            "business_window_quantity_kg": "59",
        }
    )
    proposal, info = build_proposal(identity, priority, decisions, base_names)
    assert info["q17_unhandled_source_label_keys"] == [
        {"season": "2025-2026", "source_farm_label": "Unlisted Qiu Label"}
    ]
    unknown = _find(proposal, "2025-2026", "Unlisted Qiu Label")
    assert unknown["proposed_status"] == "UNRESOLVED"
    assert unknown["proposed_base_id"] == ""


def test_q26_time_versioned_assignment_does_not_back_propagate() -> None:
    identity, priority, decisions, base_names = _fixture()
    proposal, _ = build_proposal(identity, priority, decisions, base_names)
    old_season = _find(proposal, "2024-2025", "Old Region Farm")
    current_season = _find(proposal, "2025-2026", "Current Region Farm")
    assert old_season["proposed_base_id"] == "base-quishi"
    assert old_season["change_type"] == "RESOLVE_UNRESOLVED"
    assert current_season["proposed_base_id"] == "base-zhonghe"
    assert "2025-2026 onward" in current_season["future_effective_rule"]


def test_explicit_business_correction_can_propose_reassignment_without_applying_authority() -> None:
    identity, priority, decisions, base_names = _fixture()
    existing = next(row for row in identity if row["source_farm_label"] == "Old Region Farm")
    existing.update(
        current_mapping_status="EXACT",
        current_match_type="EXACT",
        current_candidate_base_id="base-zhonghe",
        current_canonical_base_name="Base Zhonghe",
    )

    proposal, _ = build_proposal(identity, priority, decisions, base_names)

    corrected = _find(proposal, "2024-2025", "Old Region Farm")
    assert corrected["old_base_id"] == "base-zhonghe"
    assert corrected["proposed_base_id"] == "base-quishi"
    assert corrected["proposed_status"] == "PROPOSED_MAPPED_NON_AUTHORITY"
    assert corrected["change_type"] == "REASSIGN_EXISTING"
    assert corrected["proposal_authority_status"] == "NON_AUTHORITATIVE_PROPOSAL_ONLY"


@pytest.mark.parametrize(
    ("question", "wrong_parent", "subfarm"),
    [
        ("Q07", "Wrong Parent", "Shared Subfarm One"),
        ("Q10", "Other Wrong Parent", "Shared Subfarm Two"),
    ],
)
def test_parent_correction_changes_relation_not_quantity_or_base(
    question: str, wrong_parent: str, subfarm: str
) -> None:
    identity, priority, decisions, base_names = _fixture()
    proposal, _ = build_proposal(identity, priority, decisions, base_names)
    corrected = _find(proposal, "2025-2026", wrong_parent, subfarm)
    assert corrected["change_type"] == "PARENT_CORRECTION"
    assert corrected["proposed_parent_source_farm_label"] == "Correct Parent"
    assert corrected["old_base_id"] == corrected["proposed_base_id"] == "base-lancang"
    assert corrected["quantity_kg"] in {"2", "3"}
    assert corrected["business_decision"].startswith(f"{question}:")


def test_yes_all_never_resolves_unresolved_label_without_explicit_target() -> None:
    identity, priority, decisions, base_names = _fixture()
    proposal, _ = build_proposal(identity, priority, decisions, base_names)
    row = _find(proposal, "2024-2025", "Yes All Unresolved")
    assert row["proposed_status"] == "UNRESOLVED"
    assert row["proposed_base_id"] == ""


def test_duplicate_question_scopes_de_duplicate_kg_and_conserve_all_seasons() -> None:
    identity, priority, decisions, base_names = _fixture()
    proposal, _ = build_proposal(identity, priority, decisions, base_names)
    reconciliation = simulate_mapping(identity, proposal)
    combined = _find(proposal, "2023-2024", "Qiu Base")
    assert combined["decision_question"] == "Q06;Q09;Q18"
    assert combined["quantity_kg"] == "11"
    for season in ("2023-2024", "2024-2025", "2025-2026"):
        current = reconciliation["current"][season]
        proposed = reconciliation["proposed"][season]
        assert current["raw"] == proposed["raw"]
        assert proposed["reconciliation_delta"] == Decimal(0)
        assert proposed["business_reconciliation_delta"] == Decimal(0)
    assert len(proposal) == 466
    assert all(
        row["proposal_authority_status"] == "NON_AUTHORITATIVE_PROPOSAL_ONLY" for row in proposal
    )


def test_unique_yes_candidate_resolves_only_under_confirmed_candidate() -> None:
    identity, priority, decisions, base_names = _fixture()
    proposal, _ = build_proposal(identity, priority, decisions, base_names)
    row = _find(proposal, "2024-2025", "Candidate Farm")
    assert row["proposed_status"] == "PROPOSED_MAPPED_NON_AUTHORITY"
    assert row["proposed_base_id"] == "base-candidate"
    assert row["change_type"] == "RESOLVE_UNRESOLVED"


def test_public_evidence_contains_aggregates_and_hashes_not_private_labels() -> None:
    identity, priority, decisions, base_names = _fixture()
    proposal, info = build_proposal(identity, priority, decisions, base_names)
    reconciliation = simulate_mapping(identity, proposal)
    evidence = build_public_evidence(
        base_sha="base-sha",
        source_hashes={
            season: f"hash-{index}"
            for index, season in enumerate(("2023-2024", "2024-2025", "2025-2026"))
        },
        authority_hashes={"identity": "hash"},
        package_manifest_hash="package-hash",
        decisions_hash="decisions-hash",
        proposal_rows=proposal,
        decision_rows=decisions,
        build_info=info,
        reconciliation=reconciliation,
        s1_evidence={"folds": {}},
        s1_evidence_sha256="s1-hash",
        s3_evidence={
            "per_base": [
                {"fold_id": "FOLD_A", "season": "2024-2025", "base_id": "base-one"},
                {"fold_id": "FOLD_B", "season": "2025-2026", "base_id": "base-two"},
            ]
        },
        s3_evidence_sha256="s3-hash",
    )
    text = json.dumps(evidence, ensure_ascii=False)
    assert evidence["business_decision_count"] == 40
    assert evidence["all_40_business_questions_captured"] is True
    assert evidence["no_business_decision_inferred"] is True
    assert evidence["question_specific_rules"]["q06_q09_exact_identity_deduplication"] is True
    assert evidence["question_specific_rules"]["q14_season_specific_rule_preserved"] is True
    assert evidence["question_specific_rules"]["q07_parent_correction_preserved"] is True
    assert evidence["question_specific_rules"]["q10_parent_correction_preserved"] is True
    assert "Qiu Base" not in text
    assert "Correct Parent" not in text
    assert "Candidate Base" not in text
    assert "base-lancang" not in text
    assert evidence["impact_analysis"]["s3_source_label_lineage_proven"] is False


def test_proposal_schema_keeps_non_authoritative_contract() -> None:
    assert "proposal_authority_status" in PROPOSAL_FIELDS
    assert "decision_question" in PROPOSAL_FIELDS
    assert ACCEPTED_STATUSES == {"EXACT", "AUTHORIZED_ALIAS", "HISTORICALLY_PROVEN_ALIAS"}


def test_checked_in_evidence_is_sanitized_and_non_authoritative() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    evidence_path = repository_root / (
        "docs/data-audit/evidence/"
        "cross-season-business-identity-decisions-and-authority-correction-proposal-r1.json"
    )
    report_path = repository_root / (
        "docs/data-audit/"
        "cross-season-business-identity-decisions-and-authority-correction-proposal-r1.md"
    )
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    public_text = evidence_path.read_text(encoding="utf-8") + report_path.read_text(
        encoding="utf-8"
    )

    assert evidence["business_decision_count"] == 40
    assert evidence["private_proposal_row_count"] == 466
    assert evidence["quantity_reconciliation_pass"] is True
    assert evidence["question_specific_rules"]["q14_season_specific_rule_preserved"] is True
    assert evidence["question_specific_rules"]["q17_split_mapping_rule_preserved"] is True
    assert evidence["question_specific_rules"]["q26_effective_season_rule_preserved"] is True
    assert evidence["mapping_authority_applied"] is False
    assert evidence["model_changed"] is False
    assert evidence["model_retrained"] is False
    assert evidence["backtest_executed"] is False
    assert evidence["v07_changed"] is False
    assert len(evidence["private_output_manifest_sha256"]) == 64
    assert "source_farm_label" not in public_text
    assert "source_subfarm_label" not in public_text
