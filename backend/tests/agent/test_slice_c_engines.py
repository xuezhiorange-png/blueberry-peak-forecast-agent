from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from backend.app.agent.adapters.parameters import ALL_LOGICAL_PARAMETERS, LOGICAL_TO_UPSTREAM
from backend.app.agent.canonical import canonical_json_dumps, sha256_payload
from backend.app.agent.enums import BlockerCode
from backend.app.agent.schemas import Blocker, Citation, CitationAuthorityEntry, SliceCSourcePayload
from backend.app.agent.slice_c.engine import (
    EXPLANATION_POLICY_VERSION,
    EXPLANATION_TEMPLATE_CATALOG_VERSION,
    FIELD_PATH_POLICY_VERSION,
    RECOMMENDATION_POLICY_VERSION,
    RECOMMENDATION_RULE_CATALOG_VERSION,
    build_explanation,
    build_recommendations,
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
    source = json.loads(
        (Path(__file__).parent / "golden" / "slice_b_ordinary_user.json").read_text()
    )
    source.pop("explanation")
    source.pop("recommendations")
    for field in (
        "uncertainty_widening_policy_version",
        "uncertainty_widening_policy_config_hash",
        "peak_metric_policy_version",
        "peak_metric_policy_config_hash",
    ):
        source.pop(field)
    source["blockers"] = [
        {
            "code": "INSUFFICIENT_HISTORY",
            "message": "history unavailable",
            "details": {"variety_id": "101"},
            "citation": None,
            "retry_hint": "WAIT_FOR_DATA",
        }
    ]
    entries = _authority_entries(source)
    source["citations"] = [
        _citation(
            source,
            entries=entries,
            pointer="/daily_curve/0/final_corrected_arrival_quantity_kg/p50",
            tool="FORECAST_DAILY_CURVE",
            artifact_hash=source["daily_curve"][0]["agent_daily_row_hash"],
        ).model_dump(mode="json"),
        _citation(
            source,
            entries=entries,
            pointer="/peak/single_day_peak/P50/volume_kg",
            tool="FORECAST_PEAK",
            artifact_hash=source["peak"]["agent_peak_hash"],
        ).model_dump(mode="json"),
        _citation(
            source,
            entries=[entries[1]],
            pointer="/provenance/task9_authority",
            tool="EXPLAIN_FORECAST",
            artifact_hash=None,
        ).model_dump(mode="json"),
        _citation(
            source,
            entries=entries,
            pointer="/peak/sustained_3day_peak/P50/rolling_daily_average_kg_per_day",
            tool="FORECAST_PEAK",
            artifact_hash=source["peak"]["agent_peak_hash"],
        ).model_dump(mode="json"),
        Citation.model_validate(
            {
                "source_tasks": ["TASK_013"],
                "source_tool": "GENERATE_RECOMMENDATIONS",
                "authorities": [],
                "agent_artifact_hash": None,
                "field_path": "/blockers/0/code",
                "effective_as_of_date": source["normalized_request"]["effective_as_of_date"],
                "confidence_evidence": None,
                "tags": [],
                "override_refs": [],
            }
        ).model_dump(mode="json"),
    ]
    return source


def _authority_entries(source: dict) -> list[CitationAuthorityEntry]:
    return [
        CitationAuthorityEntry.model_validate(
            {"authority_type": f"TASK_{number}_AUTHORITY", "authority": authority}
        )
        for number in (8, 9, 10)
        if (authority := source["provenance"].get(f"task{number}_authority")) is not None
    ]


def _citation(
    source: dict,
    *,
    entries: list[CitationAuthorityEntry],
    pointer: str,
    tool: str,
    artifact_hash: str | None,
) -> Citation:
    return Citation.model_validate(
        {
            "source_tasks": [
                f"TASK_{int(entry.authority_type.split('_')[1]):03d}" for entry in entries
            ],
            "source_tool": tool,
            "authorities": [entry.model_dump(mode="json") for entry in entries],
            "agent_artifact_hash": artifact_hash,
            "field_path": pointer,
            "effective_as_of_date": source["normalized_request"]["effective_as_of_date"],
            "confidence_evidence": None,
            "tags": [],
            "override_refs": [],
        }
    )


def _source_with_parameter() -> dict:
    source = _source_payload()
    entry = _authority_entries(source)[:1]
    citation = _citation(
        source,
        entries=entry,
        pointer="/parameters/0/p50",
        tool="INFER_PARAMETERS",
        artifact_hash=source["provenance"]["task8_authority"]["maturity_model_artifact_hash"],
    )
    source["parameters"] = [
        {
            "parameter_name": "maturity_curve",
            "variety_id": "101",
            "p50": "12.0",
            "p80_lower": None,
            "p80_upper": None,
            "source_level": 5,
            "confidence": "LOW",
            "confidence_score": None,
            "sample_count": 0,
            "season_count": 0,
            "farm_count": 0,
            "source_observation_ids": [],
            "fallback_below_minimum": True,
            "missing_evidence": ["maturity_curve_component_missing:maturity_width_days"],
            "prior_version": None,
            "distribution_kind": "POINT",
            "citation": citation.model_dump(mode="json"),
        }
    ]
    return source


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


def test_missing_data_impact_applicable_with_cited_blocker_metadata() -> None:
    _, recommendations = build_slice_c_outputs(_source_payload())
    decision = recommendations.decisions[-1]
    assert decision.category == "MISSING_DATA_IMPACT"
    assert decision.status == "APPLICABLE"
    assert decision.reason_code == "RULE_APPLICABLE"
    assert decision.advisory_text is not None
    assert decision.evidence[0].citation.source_tasks == ["TASK_013"]
    assert decision.evidence[0].citation.authorities == []
    assert "%" not in decision.advisory_text


def test_explanation_does_not_consume_recommendation_owned_blocker_citation() -> None:
    source = _source_payload()
    explanation, recommendations = build_slice_c_outputs(source)
    blocker_section = next(
        section
        for section in explanation.structured_payload
        if section.section == "BLOCKERS_AND_DATA_GAPS"
    )
    assert blocker_section.paragraphs
    assert blocker_section.paragraphs[0].evidence_field_paths == ["/blockers/0/code"]
    assert blocker_section.paragraphs[0].citation is None
    assert all(
        paragraph.citation is None or paragraph.citation.source_tool != "GENERATE_RECOMMENDATIONS"
        for section in explanation.structured_payload
        for paragraph in section.paragraphs
    )
    missing_data = recommendations.decisions[-1]
    assert missing_data.evidence
    assert all(
        evidence.citation.source_tool == "GENERATE_RECOMMENDATIONS"
        for evidence in missing_data.evidence
    )


def test_slice_c_sibling_outputs_are_order_independent() -> None:
    source = SliceCSourcePayload.model_validate(_source_payload())
    explanation_first = build_explanation(source)
    recommendations_second = build_recommendations(source)
    recommendations_first = build_recommendations(source)
    explanation_second = build_explanation(source)

    assert explanation_first.model_dump_json() == explanation_second.model_dump_json()
    assert recommendations_first.model_dump_json() == recommendations_second.model_dump_json()
    assert "agent_recommendations_hash" not in explanation_first.model_dump_json()
    assert "agent_explanation_hash" not in recommendations_first.model_dump_json()


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


def _replace_citation(source: dict, replacement: Citation) -> None:
    source["citations"] = [
        replacement.model_dump(mode="json")
        if item["field_path"] == replacement.field_path
        else item
        for item in source["citations"]
    ]


def test_missing_authority_blocks_authoritative_paragraph() -> None:
    source = _source_payload()
    citation = Citation.model_validate(source["citations"][0]).model_copy(
        update={"source_tasks": ["TASK_013"], "authorities": []}
    )
    _replace_citation(source, citation)
    explanation, _ = build_slice_c_outputs(source)
    daily = next(
        section
        for section in explanation.structured_payload
        if section.section == "DAILY_CURVE_SUMMARY"
    )
    assert daily.paragraphs == []
    assert BlockerCode.REQUIRED_AUTHORITY_MISSING in {item.code for item in explanation.blockers}


def test_missing_citation_blocks_authoritative_paragraph() -> None:
    source = _source_payload()
    source["citations"] = [
        item
        for item in source["citations"]
        if item["field_path"] != "/daily_curve/0/final_corrected_arrival_quantity_kg/p50"
    ]
    explanation, _ = build_slice_c_outputs(source)
    assert BlockerCode.REQUIRED_CITATION_MISSING in {item.code for item in explanation.blockers}


def test_task013_is_never_used_as_numerical_authority_fallback() -> None:
    source = _source_payload()
    source["provenance"]["task8_authority"] = None
    source["provenance"]["task9_authority"] = None
    source["provenance"]["task10_authority"] = None
    source["citations"] = []
    explanation, _ = build_slice_c_outputs(source)
    assert all(
        "TASK_013" not in paragraph.citation.source_tasks
        for section in explanation.structured_payload
        for paragraph in section.paragraphs
        if paragraph.citation is not None
    )
    assert BlockerCode.REQUIRED_CITATION_MISSING in {item.code for item in explanation.blockers}


def test_parameter_citation_is_not_rewritten_by_slice_c() -> None:
    source = _source_with_parameter()
    original = deepcopy(source["parameters"][0]["citation"])
    explanation, _ = build_slice_c_outputs(source)
    assert source["parameters"][0]["citation"] == original
    assert all(
        paragraph.template_id != "parameter-value-v1"
        for section in explanation.structured_payload
        for paragraph in section.paragraphs
    )
    assert BlockerCode.EVIDENCE_HASH_MISMATCH in {item.code for item in explanation.blockers}


def test_expected_yield_is_not_bound_to_task8_maturity_authority() -> None:
    source = _source_with_parameter()
    source["parameters"][0]["parameter_name"] = "expected_per_mu_yield"
    explanation, _ = build_slice_c_outputs(source)
    assert all(
        paragraph.template_id != "parameter-value-v1"
        for section in explanation.structured_payload
        for paragraph in section.paragraphs
    )
    assert all(item["field_path"] != "/parameters/0/p50" for item in source["citations"])


def test_wrong_task8_parameter_binding_is_rejected() -> None:
    source = _source_with_parameter()
    citation = Citation.model_validate(source["parameters"][0]["citation"])
    with pytest.raises(ValueError, match="EVIDENCE_HASH_MISMATCH"):
        validate_citation(source, citation, expected_value=source["parameters"][0]["p50"])


def test_override_tags_and_refs_are_preserved() -> None:
    source = _source_payload()
    payload = Citation.model_validate(source["citations"][0]).model_dump(mode="json")
    payload.update(
        {
            "tags": ["OVERRIDE_APPLIED"],
            "override_refs": [
                {
                    "override_ref_id": "a" * 64,
                    "override_kind": "AS_OF_OVERRIDE",
                    "target": None,
                    "source_attestation": "operator-confirmed",
                    "source_ref": {"ticket": "OPS-1"},
                }
            ],
        }
    )
    citation = Citation.model_validate(payload)
    _replace_citation(source, citation)
    explanation, _ = build_slice_c_outputs(source)
    paragraph = next(
        paragraph
        for section in explanation.structured_payload
        for paragraph in section.paragraphs
        if paragraph.template_id == "daily-curve-value-v1"
    )
    assert paragraph.citation is not None
    assert paragraph.citation.tags == citation.tags
    assert paragraph.citation.override_refs == citation.override_refs


@pytest.mark.parametrize(
    ("pointer", "wrong_hash"),
    [
        (
            "/daily_curve/0/final_corrected_arrival_quantity_kg/p50",
            "peak",
        ),
        ("/peak/single_day_peak/P50/volume_kg", "daily"),
    ],
)
def test_cross_artifact_substitution_is_rejected(pointer: str, wrong_hash: str) -> None:
    source = _source_payload()
    canonical = next(item for item in source["citations"] if item["field_path"] == pointer)
    artifact = (
        source["peak"]["agent_peak_hash"]
        if wrong_hash == "peak"
        else source["daily_curve"][0]["agent_daily_row_hash"]
    )
    malicious = Citation.model_validate(canonical).model_copy(
        update={"agent_artifact_hash": artifact}
    )
    with pytest.raises(ValueError, match="EVIDENCE_HASH_MISMATCH"):
        validate_citation(source, malicious)


def test_daily_row_rejects_other_row_hash() -> None:
    source = _source_payload()
    source["daily_curve"].append(deepcopy(source["daily_curve"][0]))
    source["daily_curve"][1]["date"] = "2026-03-04"
    source["daily_curve"][1]["agent_daily_row_hash"] = "f" * 64
    citation = Citation.model_validate(source["citations"][0]).model_copy(
        update={"agent_artifact_hash": "f" * 64}
    )
    with pytest.raises(ValueError, match="EVIDENCE_HASH_MISMATCH"):
        validate_citation(source, citation)


def test_parameter_field_rejects_other_parameter_citation() -> None:
    source = _source_with_parameter()
    second = deepcopy(source["parameters"][0])
    second["variety_id"] = "102"
    second["p50"] = "2.50"
    second_citation = Citation.model_validate(second["citation"]).model_copy(
        update={"field_path": "/parameters/1/p50"}
    )
    second["citation"] = second_citation.model_dump(mode="json")
    source["parameters"].append(second)
    source["citations"].append(second_citation.model_dump(mode="json"))
    with pytest.raises(ValueError, match="EVIDENCE_HASH_MISMATCH"):
        validate_citation(
            source,
            second_citation,
            expected_value=source["parameters"][0]["p50"],
        )


def test_cross_authority_substitution_is_rejected() -> None:
    source = _source_payload()
    canonical = Citation.model_validate(source["citations"][0])
    task10 = [
        entry for entry in canonical.authorities if entry.authority_type == "TASK_10_AUTHORITY"
    ]
    malicious = canonical.model_copy(update={"source_tasks": ["TASK_010"], "authorities": task10})
    _replace_citation(source, malicious)
    with pytest.raises(ValueError, match="EVIDENCE_HASH_MISMATCH"):
        validate_citation(source, malicious)


def test_task9_field_rejects_task10_only_authority() -> None:
    source = _source_payload()
    canonical = Citation.model_validate(
        next(
            item
            for item in source["citations"]
            if item["field_path"] == "/provenance/task9_authority"
        )
    )
    task10 = _authority_entries(source)[2]
    malicious = canonical.model_copy(update={"source_tasks": ["TASK_010"], "authorities": [task10]})
    with pytest.raises(ValueError, match="EVIDENCE_HASH_MISMATCH"):
        validate_citation(source, malicious)


def test_empty_source_is_fail_closed() -> None:
    explanation, recommendations = build_slice_c_outputs({})
    assert len(explanation.structured_payload) == 8
    assert {item.code for item in explanation.blockers} >= {
        BlockerCode.REQUIRED_CITATION_MISSING,
        BlockerCode.REQUIRED_PROVENANCE_MISSING,
        BlockerCode.EVIDENCE_FIELD_PATH_INVALID,
    }
    assert recommendations.decisions[-1].status == "BLOCKED"
    assert recommendations.decisions[-1].reason_code == "REQUIRED_EVIDENCE_MISSING"


def test_missing_citations_maps_only_citation_blocker() -> None:
    source = _source_payload()
    del source["citations"]
    explanation, _ = build_slice_c_outputs(source)
    assert {item.code for item in explanation.blockers} == {BlockerCode.REQUIRED_CITATION_MISSING}


def test_malformed_provenance_maps_only_supported_blockers() -> None:
    source = _source_payload()
    source["provenance"]["task8_authority"] = {"bad": "shape"}
    explanation, _ = build_slice_c_outputs(source)
    assert {item.code for item in explanation.blockers} == {BlockerCode.REQUIRED_AUTHORITY_MISSING}
    assert all(
        item.details and item.details["validation_location"] for item in explanation.blockers
    )


def test_bad_pointer_does_not_report_unrelated_authority_gap() -> None:
    source = _source_payload()
    citation = Citation.model_validate(source["citations"][0]).model_copy(
        update={"field_path": "daily_curve[0].p50"}
    )
    with pytest.raises(ValueError, match="EVIDENCE_FIELD_PATH_INVALID") as captured:
        validate_citation(source, citation)
    assert "REQUIRED_AUTHORITY_MISSING" not in str(captured.value)


def test_unknown_source_field_maps_to_exact_location() -> None:
    source = _source_payload()
    source["provenance"]["misspelled_authority"] = "invalid"
    explanation, _ = build_slice_c_outputs(source)
    assert {item.code for item in explanation.blockers} == {BlockerCode.EVIDENCE_FIELD_PATH_INVALID}
    assert explanation.blockers[0].details == {
        "validation_location": ["provenance", "misspelled_authority"],
        "validation_type": "extra_forbidden",
        "input_field": "misspelled_authority",
    }


def test_missing_data_impact_not_applicable_engine_contract_only() -> None:
    source = _source_payload()
    source["blockers"] = []
    source["citations"] = [
        item for item in source["citations"] if not item["field_path"].startswith("/blockers/")
    ]
    _, recommendations = build_slice_c_outputs(source)
    decision = recommendations.decisions[-1]
    assert decision.status == "NOT_APPLICABLE"
    assert decision.reason_code == "CONDITIONS_NOT_MET"


def test_not_applicable_production_reachability_is_blocked_by_frozen_sources() -> None:
    unsupported = {
        "spring_festival_harvest_rate",
        "weather_adjustment",
        "post_spring_festival_backlog_release_intensity",
        "historical_anomaly_peak_probability",
    }
    assert unsupported <= set(ALL_LOGICAL_PARAMETERS)
    assert {name for name, source in LOGICAL_TO_UPSTREAM.items() if source is None} == unsupported


def test_missing_data_impact_blocked_when_metadata_citation_missing() -> None:
    source = _source_payload()
    source["citations"] = [
        item for item in source["citations"] if item["field_path"] != "/blockers/0/code"
    ]
    _, recommendations = build_slice_c_outputs(source)
    decision = recommendations.decisions[-1]
    assert decision.status == "BLOCKED"
    assert decision.reason_code == "REQUIRED_EVIDENCE_MISSING"


def test_task013_metadata_citation_cannot_validate_numerical_path() -> None:
    source = _source_payload()
    metadata = next(item for item in source["citations"] if item["source_tasks"] == ["TASK_013"])
    malicious = Citation.model_validate(metadata).model_copy(
        update={"field_path": "/daily_curve/0/final_corrected_arrival_quantity_kg/p50"}
    )
    _replace_citation(source, malicious)
    with pytest.raises(ValueError, match="REQUIRED_AUTHORITY_MISSING|EVIDENCE_HASH_MISMATCH"):
        validate_citation(source, malicious)


def test_incomplete_provenance_is_fail_closed() -> None:
    source = _source_payload()
    source["provenance"] = {}
    explanation, recommendations = build_slice_c_outputs(source)
    assert BlockerCode.REQUIRED_PROVENANCE_MISSING in {item.code for item in explanation.blockers}
    assert recommendations.decisions[-1].status == "BLOCKED"


def test_domain_resolution_errors_become_typed_blockers() -> None:
    source = _source_payload()
    del source["daily_curve"][0]["final_corrected_arrival_quantity_kg"]["p50"]
    explanation, recommendations = build_slice_c_outputs(source)
    assert BlockerCode.EVIDENCE_FIELD_PATH_INVALID in {item.code for item in explanation.blockers}
    assert recommendations.decisions[-1].status == "BLOCKED"
    assert recommendations.decisions[-1].reason_code == "REQUIRED_EVIDENCE_MISSING"


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
    source = _source_with_parameter()
    second = deepcopy(source["parameters"][0])
    second["variety_id"] = "102"
    second_citation = Citation.model_validate(second["citation"]).model_copy(
        update={"field_path": "/parameters/1/p50"}
    )
    second["citation"] = second_citation.model_dump(mode="json")
    source["parameters"].append(second)
    source["citations"].append(second_citation.model_dump(mode="json"))
    _, recommendations = build_slice_c_outputs(source)
    decision = recommendations.decisions[-1]
    assert decision.status == "BLOCKED"
    assert decision.reason_code == "REQUIRED_EVIDENCE_MISSING"
    assert decision.risk_codes == sorted(decision.risk_codes)


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
                assert pointer.startswith("/")
            if paragraph.citation is not None:
                validate_citation(source, paragraph.citation)
    for decision in recommendations.decisions:
        for evidence in decision.evidence:
            validate_citation(source, evidence.citation)
