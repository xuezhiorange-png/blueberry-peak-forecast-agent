from __future__ import annotations

import json

from backend.app.area_yield.v08_s7_training_source_identity_closure import (
    ACCEPTED_RESOLUTION_BY_MAPPING_STATUS,
    build_target_base_seasons,
    resolve_source_identity,
    validate_eligibility_preservation,
)


def _identity(
    *,
    status: str = "UNRESOLVED",
    base_id: str = "",
    questions: str = "",
    decisions: str = "",
) -> dict[str, str]:
    return {
        "season": "2023-2024",
        "source_farm_label": "Source Farm",
        "mapping_status": status,
        "canonical_base_id": base_id,
        "decision_questions": questions,
        "business_decisions": decisions,
        "identity_revision_id": "revision-current",
    }


def _decision(
    *,
    answer: str = "",
    correct_base: str = "",
    split_rule: str = "",
) -> dict[str, str]:
    return {
        "question_number": "Q01",
        "decision_2023_2024": answer,
        "correct_base": correct_base,
        "split_rule": split_rule,
        "decision_source": "USER_BUSINESS_CONFIRMATION_2026_09_23",
    }


def _group(*, scoped: bool = True, candidate_ids: list[str] | None = None) -> dict[str, str]:
    keys = [{"season": "2023-2024", "source_farm_label": "Source Farm"}] if scoped else []
    return {
        "question_number": "Q01",
        "owned_label_keys": json.dumps(keys),
        "unresolved_label_keys": json.dumps(keys),
        "reference_label_keys": "[]",
        "candidate_base_ids": json.dumps(candidate_ids or ["base-a"]),
    }


def test_exact_current_identity_is_reused_only_for_exact_season_key() -> None:
    result = resolve_source_identity(
        season="2023-2024",
        source_farm_label="Source Farm",
        candidate_base_ids=["base-a"],
        current_identity=_identity(status="AUTHORIZED_ALIAS", base_id="base-a"),
    )
    assert result.status == "ACCEPTED_AUTHORIZED_ALIAS"
    assert result.base_id == "base-a"
    assert result.basis == "EXACT_SEASON_AND_SOURCE_FARM_LABEL_ONLY"


def test_historically_proven_alias_reapplies_only_when_current_key_is_absent() -> None:
    result = resolve_source_identity(
        season="2023-2024",
        source_farm_label="Source Farm",
        candidate_base_ids=["base-a"],
        historical_identity={
            "season": "2023-2024",
            "source_farm_label": "Source Farm",
            "mapping_status": "ACCEPTED_FROZEN_IDENTITY_MAPPING",
            "decision": "ACCEPTED",
            "match_type": "HISTORICALLY_PROVEN_ALIAS",
            "candidate_base_id": "base-a",
        },
    )
    assert result.status == "ACCEPTED_HISTORICALLY_PROVEN_ALIAS"
    assert result.base_id == "base-a"


def test_current_unresolved_and_historical_acceptance_is_a_conflict() -> None:
    result = resolve_source_identity(
        season="2023-2024",
        source_farm_label="Source Farm",
        candidate_base_ids=["base-a"],
        current_identity=_identity(),
        historical_identity={
            "season": "2023-2024",
            "source_farm_label": "Source Farm",
            "mapping_status": "ACCEPTED_FROZEN_IDENTITY_MAPPING",
            "decision": "ACCEPTED",
            "match_type": "EXACT",
            "candidate_base_id": "base-a",
        },
    )
    assert result.status == "CONFLICTING_EVIDENCE"
    assert result.base_id == ""


def test_multiple_candidate_bases_remain_unresolved() -> None:
    result = resolve_source_identity(
        season="2023-2024",
        source_farm_label="Source Farm",
        candidate_base_ids=["base-a", "base-b"],
        current_identity=_identity(),
    )
    assert result.status == "UNRESOLVED_MULTIPLE_BASES"
    assert result.base_id == ""


def test_yes_all_does_not_resolve_without_explicit_target() -> None:
    result = resolve_source_identity(
        season="2023-2024",
        source_farm_label="Source Farm",
        candidate_base_ids=["base-a"],
        current_identity=_identity(questions="Q01", decisions="Q01:YES_ALL"),
        decision_rows={"Q01": _decision(answer="YES_ALL")},
        decision_groups={"Q01": _group()},
        base_name_to_id={"Candidate Base": "base-a"},
    )
    assert result.status == "UNRESOLVED_NO_EVIDENCE"
    assert result.base_id == ""
    assert result.basis == "BUSINESS_DECISION_YES_ALL_HAS_NO_EXPLICIT_TARGET"


def test_explicit_yes_candidate_requires_exact_group_scope_and_unique_candidate() -> None:
    accepted = resolve_source_identity(
        season="2023-2024",
        source_farm_label="Source Farm",
        candidate_base_ids=["base-a"],
        current_identity=_identity(questions="Q01"),
        decision_rows={"Q01": _decision(answer="YES_CANDIDATE")},
        decision_groups={"Q01": _group()},
        base_name_to_id={"Candidate Base": "base-a"},
    )
    out_of_scope = resolve_source_identity(
        season="2023-2024",
        source_farm_label="Other Farm",
        candidate_base_ids=["base-a"],
        current_identity=_identity(questions="Q01"),
        decision_rows={"Q01": _decision(answer="YES_CANDIDATE")},
        decision_groups={"Q01": _group()},
        base_name_to_id={"Candidate Base": "base-a"},
    )
    ambiguous = resolve_source_identity(
        season="2023-2024",
        source_farm_label="Source Farm",
        candidate_base_ids=["base-a", "base-b"],
        current_identity=_identity(questions="Q01"),
        decision_rows={"Q01": _decision(answer="YES_CANDIDATE")},
        decision_groups={"Q01": _group(candidate_ids=["base-a", "base-b"])},
        base_name_to_id={"Candidate Base": "base-a"},
    )
    assert accepted.status == "ACCEPTED_BUSINESS_CONFIRMED_MAPPING"
    assert accepted.base_id == "base-a"
    assert out_of_scope.status == "UNRESOLVED_NO_EVIDENCE"
    assert ambiguous.status == "UNRESOLVED_MULTIPLE_BASES"


def test_correct_base_decision_is_explicit_but_fuzzy_name_is_not() -> None:
    accepted = resolve_source_identity(
        season="2023-2024",
        source_farm_label="Source Farm",
        candidate_base_ids=["base-a"],
        current_identity=_identity(questions="Q01"),
        decision_rows={"Q01": _decision(answer="CORRECT_BASE:Canonical Base")},
        decision_groups={"Q01": _group()},
        base_name_to_id={"Canonical Base": "base-a"},
    )
    no_match = resolve_source_identity(
        season="2023-2024",
        source_farm_label="Source Farm",
        candidate_base_ids=["base-a"],
        current_identity=_identity(questions="Q01"),
        decision_rows={"Q01": _decision(answer="CORRECT_BASE:Almost Canonical Base")},
        decision_groups={"Q01": _group()},
        base_name_to_id={"Canonical Base": "base-a"},
    )
    assert accepted.status == "ACCEPTED_BUSINESS_CONFIRMED_MAPPING"
    assert accepted.base_id == "base-a"
    assert no_match.status == "UNRESOLVED_NO_EVIDENCE"


def test_no_cross_season_propagation() -> None:
    result = resolve_source_identity(
        season="2024-2025",
        source_farm_label="Source Farm",
        candidate_base_ids=["base-a"],
        current_identity={**_identity(status="EXACT", base_id="base-a"), "season": "2023-2024"},
    )
    assert result.status == "UNRESOLVED_NO_EVIDENCE"
    assert result.base_id == ""


def test_parent_relationship_without_explicit_quantity_base_assignment_is_not_identity() -> None:
    result = resolve_source_identity(
        season="2023-2024",
        source_farm_label="Source Farm",
        source_subfarm_label="Subfarm",
        candidate_base_ids=["base-a"],
        current_identity=_identity(),
        parent_relation={
            "season": "2023-2024",
            "source_farm_label": "Source Farm",
            "source_subfarm_label": "Subfarm",
            "parent_relation_status": "SOURCE_REPORTED_PARENT",
            "canonical_base_id_from_farm_identity": "",
            "quantity_assignment_base_id": "",
        },
    )
    assert result.status == "UNRESOLVED_NO_EVIDENCE"


def test_explicit_parent_mapping_is_accepted_only_when_base_assignments_agree() -> None:
    authorized_relation = {
        "season": "2023-2024",
        "source_farm_label": "Source Farm",
        "source_subfarm_label": "Subfarm",
        "parent_relation_status": "BUSINESS_CONFIRMED_PARENT_MAPPING",
        "canonical_base_id_from_farm_identity": "base-a",
        "quantity_assignment_base_id": "base-a",
        "relation_revision_id": "parent-revision-1",
    }
    accepted = resolve_source_identity(
        season="2023-2024",
        source_farm_label="Source Farm",
        source_subfarm_label="Subfarm",
        candidate_base_ids=["base-a"],
        parent_relation=authorized_relation,
    )
    conflicting = resolve_source_identity(
        season="2023-2024",
        source_farm_label="Source Farm",
        source_subfarm_label="Subfarm",
        candidate_base_ids=["base-a", "base-b"],
        parent_relation={
            **authorized_relation,
            "quantity_assignment_base_id": "base-b",
        },
    )
    assert accepted.status == "ACCEPTED_MEMBER_TO_BASE_MAPPING"
    assert accepted.base_id == "base-a"
    assert accepted.evidence_ids == ("parent-revision-1",)
    assert conflicting.status == "UNRESOLVED_MULTIPLE_BASES"
    assert conflicting.base_id == ""


def test_base_identity_does_not_require_member_id_when_base_mapping_is_accepted() -> None:
    result = resolve_source_identity(
        season="2023-2024",
        source_farm_label="Source Farm",
        source_subfarm_label="Unresolved Member Label",
        candidate_base_ids=["base-a"],
        current_identity=_identity(status="BUSINESS_CONFIRMED_MAPPING", base_id="base-a"),
    )
    assert result.status == "ACCEPTED_BUSINESS_CONFIRMED_MAPPING"
    assert result.base_id == "base-a"


def test_historical_candidate_proposal_is_not_accepted_authority() -> None:
    result = resolve_source_identity(
        season="2023-2024",
        source_farm_label="Source Farm",
        candidate_base_ids=["base-a"],
        historical_identity={
            "season": "2023-2024",
            "source_farm_label": "Source Farm",
            "mapping_status": "PROPOSED_CANDIDATE_NOT_AUTHORIZED",
            "decision": "REQUIRES_BUSINESS_CONFIRMATION",
            "match_type": "REGISTERED_CORE_CANDIDATE",
            "candidate_base_id": "base-a",
        },
    )
    assert result.status == "UNRESOLVED_NO_EVIDENCE"
    assert result.base_id == ""


def test_resolution_is_deterministic_for_same_frozen_identity_inputs() -> None:
    kwargs = {
        "season": "2023-2024",
        "source_farm_label": "Source Farm",
        "candidate_base_ids": ["base-a", "base-b"],
        "current_identity": _identity(),
    }
    assert resolve_source_identity(**kwargs) == resolve_source_identity(**kwargs)


def test_target_population_is_exact_and_old_eligible_rows_are_not_reopened() -> None:
    eligibility = [
        {
            "base_id": "base-a",
            "base_name": "Base A",
            "season": "2023-2024",
            "strict_training_eligible": "false",
        },
        {
            "base_id": "base-b",
            "base_name": "Base B",
            "season": "2023-2024",
            "strict_training_eligible": "true",
        },
        {
            "base_id": "base-c",
            "base_name": "Base C",
            "season": "2025-2026",
            "strict_training_eligible": "false",
            "strict_oot_eligible": "true",
        },
    ]
    quality = [
        {
            "base_id": "base-a",
            "canonical_base_name": "Base A",
            "season": "2023-2024",
            "source_identity_status": "NO_ACCEPTED_SOURCE_ROWS",
            "accepted_source_labels": "[]",
            "unresolved_candidate_source_labels": "[]",
            "accepted_source_label_count": "0",
        },
        {
            "base_id": "base-b",
            "canonical_base_name": "Base B",
            "season": "2023-2024",
            "source_identity_status": "IDENTITY_CONFIRMED",
            "accepted_source_labels": '["Farm B"]',
            "unresolved_candidate_source_labels": "[]",
            "accepted_source_label_count": "1",
        },
        {
            "base_id": "base-c",
            "canonical_base_name": "Base C",
            "season": "2025-2026",
            "source_identity_status": "IDENTITY_CONFIRMED",
            "accepted_source_labels": '["Farm C"]',
            "unresolved_candidate_source_labels": "[]",
            "accepted_source_label_count": "1",
        },
    ]
    completeness = [
        {
            "base_id": "base-a",
            "season": "2023-2024",
            "partial_known_subtotal_day_count": "2",
            "unknown_day_count": "10",
            "complete_season_total_quantity_kg": "",
            "quantity_authority_status": "NO_COMPLETE_SEASON_TOTAL_AUTHORITY",
            "blocker_codes": "IDENTITY_UNRESOLVED",
        },
    ]
    targets = build_target_base_seasons(
        s6_eligibility_rows=eligibility,
        quality_rows=quality,
        completeness_rows=completeness,
        unresolved_rows=[],
        training_seasons=frozenset({"2023-2024", "2024-2025"}),
        expected_target_count=1,
    )
    assert len(targets) == 1
    assert targets[0]["base_id"] == "base-a"
    result = validate_eligibility_preservation(
        before_rows=eligibility,
        after_rows=eligibility,
        training_seasons=frozenset({"2023-2024", "2024-2025"}),
        oot_season="2025-2026",
    )
    assert result["previously_eligible_regression_count"] == 0
    assert result["oot_eligibility_regression_count"] == 0


def test_accepted_resolution_taxonomy_covers_only_authorized_statuses() -> None:
    assert ACCEPTED_RESOLUTION_BY_MAPPING_STATUS == {
        "EXACT": "ACCEPTED_EXACT",
        "AUTHORIZED_ALIAS": "ACCEPTED_AUTHORIZED_ALIAS",
        "HISTORICALLY_PROVEN_ALIAS": "ACCEPTED_HISTORICALLY_PROVEN_ALIAS",
        "BUSINESS_CONFIRMED_MAPPING": "ACCEPTED_BUSINESS_CONFIRMED_MAPPING",
        "BUSINESS_CONFIRMED_REASSIGNMENT": "ACCEPTED_BUSINESS_CONFIRMED_REASSIGNMENT",
    }
