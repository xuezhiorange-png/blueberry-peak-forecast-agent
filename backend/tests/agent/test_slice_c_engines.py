from __future__ import annotations

from copy import deepcopy

import pytest

from backend.app.agent.canonical import canonical_json_dumps, sha256_payload
from backend.app.agent.enums import BlockerCode
from backend.app.agent.schemas import Blocker
from backend.app.agent.slice_c.engine import (
    EXPLANATION_POLICY_VERSION,
    EXPLANATION_TEMPLATE_CATALOG_VERSION,
    FIELD_PATH_POLICY_VERSION,
    RECOMMENDATION_POLICY_VERSION,
    RECOMMENDATION_RULE_CATALOG_VERSION,
    build_slice_c_outputs,
    canonical_blockers,
    explanation_policy,
    explanation_policy_payload,
    explanation_template_catalog,
    recommendation_policy,
    recommendation_policy_payload,
    recommendation_rule_catalog,
    validate_citation,
)

OPERATIONAL = (
    "SUSTAINED_PROCESSING_CAPACITY",
    "RECEIVING_PEAK_CAPACITY",
    "SHIFT_STAFFING",
    "SPRING_FESTIVAL_STAFFING",
    "VARIETY_STAGGER",
    "CROSS_PLANT_DISPATCH",
)


def _source_payload() -> dict:
    return {
        "request_id": "req-c1",
        "request_status": "BLOCKED",
        "normalized_request": {
            "request_id": "req-c1",
            "effective_as_of_date": "2026-03-01",
            "canonical_request_hash": "1" * 64,
        },
        "resolved_location": {
            "status": "resolved",
            "location_reference_id": 601,
            "matched_location_method": "REFERENCE_ID",
        },
        "parameters": [
            {
                "parameter_name": "maturity_curve",
                "variety_id": "101",
                "p50": "12.0",
                "sample_count": 0,
                "season_count": 0,
                "farm_count": 0,
                "source_level": 5,
                "confidence": "LOW",
                "citation": None,
                "missing_evidence": ["maturity_curve_component_missing:maturity_width_days"],
            }
        ],
        "daily_curve": [
            {
                "date": "2026-03-01",
                "final_corrected_arrival_quantity_kg": {
                    "p50": "100.0",
                    "p80": "120.0",
                    "p90": "140.0",
                },
                "agent_daily_row_hash": "2" * 64,
            }
        ],
        "peak": {
            "single_day_peak": {"P50": {"date": "2026-03-01", "volume_kg": "100.0"}},
            "sustained_3day_peak": {
                "P50": {
                    "start_date": "2026-03-01",
                    "end_date": "2026-03-03",
                    "rolling_daily_average_kg_per_day": "90.0",
                    "cumulative_quantity_kg": "270.0",
                }
            },
            "agent_peak_hash": "3" * 64,
        },
        "confidence": {"level": "LOW", "evidence": {"key_missing_items": ["x"]}},
        "provenance": {
            "task8_authority": None,
            "task9_authority": None,
            "task10_authority": None,
            "agent_daily_curve_hash": "4" * 64,
            "agent_peak_hash": "3" * 64,
        },
        "blockers": [
            {
                "code": "INSUFFICIENT_HISTORY",
                "message": "history unavailable",
                "details": {"variety_id": "101"},
                "citation": None,
                "retry_hint": "WAIT_FOR_DATA",
            }
        ],
        "warnings": [],
    }


def test_builds_eight_sections_and_seven_decisions_deterministically() -> None:
    source = _source_payload()
    explanation, recommendations = build_slice_c_outputs(source)
    repeated = build_slice_c_outputs(dict(reversed(list(source.items()))))
    assert len(explanation.structured_payload) == 8
    assert all(section.paragraphs is not None for section in explanation.structured_payload)
    assert len(recommendations.decisions) == 7
    assert explanation.model_dump_json() == repeated[0].model_dump_json()
    assert recommendations.model_dump_json() == repeated[1].model_dump_json()
    assert explanation.agent_explanation_hash == sha256_payload(
        explanation.model_dump(mode="python", exclude={"agent_explanation_hash"})
    )
    assert recommendations.agent_recommendations_hash == sha256_payload(
        recommendations.model_dump(mode="python", exclude={"agent_recommendations_hash"})
    )


def test_six_operational_categories_are_fail_closed_without_action_numbers() -> None:
    _, recommendations = build_slice_c_outputs(_source_payload())
    for decision in recommendations.decisions[:6]:
        assert decision.category in OPERATIONAL
        assert decision.status == "BLOCKED"
        assert decision.reason_code == "REQUIRED_THRESHOLD_MISSING"
        assert decision.advisory_text is None
        assert decision.applicability_conditions == []
        assert decision.blocker_dependencies
        dumped = decision.model_dump_json()
        assert "threshold_value" not in dumped
        assert "dispatch now" not in dumped


def test_missing_data_impact_uses_real_parameter_evidence_without_improvement_claim() -> None:
    _, recommendations = build_slice_c_outputs(_source_payload())
    decision = recommendations.decisions[-1]
    assert decision.category == "MISSING_DATA_IMPACT"
    assert decision.status == "APPLICABLE"
    assert decision.reason_code == "RULE_APPLICABLE"
    assert decision.evidence
    assert decision.applicability_conditions
    assert all(item.field_path.startswith("/") for item in decision.applicability_conditions)
    text = decision.advisory_text or ""
    assert "%" not in text
    assert "MAPE" not in text
    assert "will improve" not in text


def test_citation_value_and_artifact_mismatch_fail_closed() -> None:
    source = _source_payload()
    explanation, _ = build_slice_c_outputs(source)
    paragraph = next(
        paragraph
        for section in explanation.structured_payload
        for paragraph in section.paragraphs
        if paragraph.kind == "AUTHORITATIVE_VALUE"
    )
    assert paragraph.citation is not None
    validate_citation(source, paragraph.citation)
    malicious = paragraph.citation.model_copy(update={"agent_artifact_hash": "f" * 64})
    try:
        validate_citation(source, malicious)
    except ValueError as exc:
        assert "EVIDENCE_HASH_MISMATCH" in str(exc)
    else:
        raise AssertionError("mismatched artifact hash was accepted")


def test_completely_identical_source_repeats_byte_identically() -> None:
    source = _source_payload()
    before = deepcopy(source)
    first = build_slice_c_outputs(source)
    second = build_slice_c_outputs(deepcopy(source))
    assert source == before
    assert first[0].model_dump_json() == second[0].model_dump_json()
    assert first[1].model_dump_json() == second[1].model_dump_json()


def test_policy_and_catalog_identities_are_canonical_and_independently_recomputable() -> None:
    explanation = explanation_policy()
    recommendation = recommendation_policy()
    assert explanation.policy_version == EXPLANATION_POLICY_VERSION
    assert explanation.template_catalog_version == EXPLANATION_TEMPLATE_CATALOG_VERSION
    assert recommendation.policy_version == RECOMMENDATION_POLICY_VERSION
    assert recommendation.rule_catalog_version == RECOMMENDATION_RULE_CATALOG_VERSION
    assert FIELD_PATH_POLICY_VERSION == "slice-c-json-pointer-policy-v1"
    assert explanation.policy_config_hash == sha256_payload(explanation_policy_payload())
    assert explanation.template_catalog_hash == sha256_payload(explanation_template_catalog())
    assert recommendation.policy_config_hash == sha256_payload(recommendation_policy_payload())
    assert recommendation.rule_catalog_hash == sha256_payload(recommendation_rule_catalog())
    changed_templates = explanation_template_catalog()
    changed_templates[0]["text_template"] = "changed"
    assert sha256_payload(changed_templates) != explanation.template_catalog_hash

    explanation_output, recommendation_output = build_slice_c_outputs(_source_payload())
    template_ids = {row["template_id"] for row in explanation_template_catalog()}
    rule_ids = {row["rule_id"] for row in recommendation_rule_catalog()}
    assert {
        paragraph.template_id
        for section in explanation_output.structured_payload
        for paragraph in section.paragraphs
    } <= template_ids
    assert {decision.rule_id for decision in recommendation_output.decisions} == rule_ids


def test_policy_hashes_reject_unordered_set_values() -> None:
    with pytest.raises(TypeError, match="set is not supported"):
        canonical_json_dumps({"forbidden": {"unordered"}})


def test_upstream_blockers_are_preserved_and_only_exact_duplicates_are_removed() -> None:
    first = Blocker(
        code=BlockerCode.INSUFFICIENT_HISTORY,
        message="history unavailable",
        details={"variety_id": "101"},
        retry_hint="WAIT_FOR_DATA",
    )
    second = first.model_copy(update={"details": {"variety_id": "102"}})
    ordered = canonical_blockers([second, first, first])
    assert len(ordered) == 2
    assert {item.details["variety_id"] for item in ordered} == {"101", "102"}

    source = _source_payload()
    source["blockers"] = [
        first.model_dump(mode="json"),
        second.model_dump(mode="json"),
        first.model_dump(mode="json"),
    ]
    explanation, recommendations = build_slice_c_outputs(source)
    for output_blockers in (explanation.blockers, recommendations.blockers):
        history = [
            blocker
            for blocker in output_blockers
            if blocker.code == BlockerCode.INSUFFICIENT_HISTORY
        ]
        assert len(history) == 2
        assert {item.details["variety_id"] for item in history} == {"101", "102"}


def test_non_actions_are_universal_and_category_specific() -> None:
    _, recommendations = build_slice_c_outputs(_source_payload())
    for decision in recommendations.decisions:
        assert decision.non_action.required is True
        assert decision.non_action.code == "ADVISORY_ONLY_NO_AUTOMATIC_EXECUTION"
        assert (
            decision.non_action.text
            == "This output is advisory only and does not trigger any external action."
        )
        assert decision.non_action.category_specific_code.startswith("NO_AUTOMATIC_")


def test_missing_data_impact_tie_break_uses_affected_count_then_code() -> None:
    source = _source_payload()
    second = deepcopy(source["parameters"][0])
    second["variety_id"] = "102"
    source["parameters"].append(second)
    _, recommendations = build_slice_c_outputs(source)
    decision = recommendations.decisions[-1]
    assert decision.risk_codes == [
        "REQUIRED_CITATION_MISSING",
        "PARAMETER_FARM_COVERAGE_INSUFFICIENT",
        "PARAMETER_SAMPLE_COVERAGE_INSUFFICIENT",
        "PARAMETER_SEASON_COVERAGE_INSUFFICIENT",
        "HISTORICAL_ERROR_EVIDENCE_MISSING",
        "PHENOLOGY_EVIDENCE_MISSING",
    ]


def test_all_evidence_pointers_resolve_and_paragraph_order_is_frozen() -> None:
    source = _source_payload()
    explanation, recommendations = build_slice_c_outputs(source)
    kind_rank = {"AUTHORITATIVE_VALUE": 1, "DETERMINISTIC_EXPLANATION": 2}
    for section in explanation.structured_payload:
        keys = [
            (
                kind_rank[paragraph.kind],
                paragraph.template_id,
                sorted(paragraph.evidence_field_paths)[0],
            )
            for paragraph in section.paragraphs
        ]
        assert keys == sorted(keys)
        for paragraph in section.paragraphs:
            for pointer in paragraph.evidence_field_paths:
                validate_citation(
                    source,
                    paragraph.citation
                    if paragraph.citation is not None
                    else _citation_for_pointer(source, pointer),
                )
    for decision in recommendations.decisions:
        for evidence in decision.evidence:
            validate_citation(source, evidence.citation)


def _citation_for_pointer(source: dict, pointer: str):
    from backend.app.agent.schemas import Citation

    normalized = source["normalized_request"]
    return Citation(
        source_tasks=["TASK_013"],
        source_tool="EXPLAIN_FORECAST",
        authorities=[],
        field_path=pointer,
        effective_as_of_date=normalized["effective_as_of_date"],
        tags=[],
        override_refs=[],
    )
