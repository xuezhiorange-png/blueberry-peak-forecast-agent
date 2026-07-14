"""Deterministic Slice C explanation and recommendation engines."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from copy import deepcopy
from typing import Any, cast, get_args

from backend.app.agent.canonical import canonical_json_dumps, sha256_payload
from backend.app.agent.enums import (
    BlockerCode,
    ExplanationSectionCode,
    MissingDataImpactCode,
    RecommendationCategory,
)
from backend.app.agent.schemas import (
    Blocker,
    Citation,
    CitationAuthorityEntry,
    ConditionEvaluation,
    ExplainForecastOutput,
    ExplainParagraph,
    ExplainSection,
    ExplanationRulePolicy,
    GenerateRecommendationsOutput,
    NonAction,
    RecommendationDecision,
    RecommendationEvidence,
    RecommendationRulePolicy,
)
from backend.app.agent.slice_c.json_pointer import (
    JsonPointerResolutionError,
    resolve_json_pointer,
)

EXPLANATION_POLICY_VERSION = "explanation-rule-policy-v1"
EXPLANATION_TEMPLATE_CATALOG_VERSION = "explanation-template-catalog-v1"
RECOMMENDATION_POLICY_VERSION = "recommendation-rule-policy-v1"
RECOMMENDATION_RULE_CATALOG_VERSION = "recommendation-rule-catalog-v1"
FIELD_PATH_POLICY_VERSION = "slice-c-json-pointer-policy-v1"

SECTION_ORDER = cast(tuple[ExplanationSectionCode, ...], get_args(ExplanationSectionCode))
CATEGORY_ORDER = cast(tuple[RecommendationCategory, ...], get_args(RecommendationCategory))
OPERATIONAL_CATEGORIES = CATEGORY_ORDER[:6]

_CATEGORY_NON_ACTION = {
    "SUSTAINED_PROCESSING_CAPACITY": "NO_AUTOMATIC_PROCESSING_CAPACITY_CHANGE",
    "RECEIVING_PEAK_CAPACITY": "NO_AUTOMATIC_RECEIVING_CAPACITY_CHANGE",
    "SHIFT_STAFFING": "NO_AUTOMATIC_SHIFT_STAFFING_ACTION",
    "SPRING_FESTIVAL_STAFFING": "NO_AUTOMATIC_SPRING_FESTIVAL_STAFFING_ACTION",
    "VARIETY_STAGGER": "NO_AUTOMATIC_VARIETY_STAGGER_ACTION",
    "CROSS_PLANT_DISPATCH": "NO_AUTOMATIC_CROSS_PLANT_DISPATCH",
    "MISSING_DATA_IMPACT": "NO_AUTOMATIC_DATA_COLLECTION_ACTION",
}

_IMPACT_LEVEL = {
    "REQUIRED_AUTHORITY_MISSING": 0,
    "REQUIRED_CITATION_MISSING": 0,
    "REQUIRED_PROVENANCE_MISSING": 0,
    "PARAMETER_SAMPLE_COVERAGE_INSUFFICIENT": 1,
    "PARAMETER_SEASON_COVERAGE_INSUFFICIENT": 1,
    "PARAMETER_FARM_COVERAGE_INSUFFICIENT": 1,
    "HISTORICAL_ERROR_EVIDENCE_MISSING": 1,
    "STAFFING_PRODUCTIVITY_SOURCE_MISSING": 1,
    "PROCESSOR_CAPACITY_SOURCE_MISSING": 1,
    "BACKTEST_EVIDENCE_MISSING": 1,
    "LOCATION_EVIDENCE_INCOMPLETE": 2,
    "WEATHER_EVIDENCE_MISSING": 2,
    "PHENOLOGY_EVIDENCE_MISSING": 2,
}

_MISSING_DATA_TAXONOMY = tuple(_IMPACT_LEVEL)

_EXPLANATION_CONFIG = {
    "policy_version": EXPLANATION_POLICY_VERSION,
    "field_path_policy_version": FIELD_PATH_POLICY_VERSION,
    "section_order": list(SECTION_ORDER),
    "paragraph_kind_rank": {
        "AUTHORITATIVE_VALUE": 1,
        "DETERMINISTIC_EXPLANATION": 2,
    },
    "paragraph_order": ["paragraph_kind_rank", "template_id", "first_evidence_path"],
}
_TEMPLATE_CATALOG = [
    {
        "template_id": "request-context-v1",
        "section": "REQUEST_AND_RESOLVED_CONTEXT",
        "paragraph_kind": "DETERMINISTIC_EXPLANATION",
        "paragraph_kind_rank": 2,
        "required_evidence_path": "/normalized_request/canonical_request_hash",
        "text_template": "The request context is normalized and hash-bound.",
    },
    {
        "template_id": "parameter-value-v1",
        "section": "PARAMETER_PROVENANCE",
        "paragraph_kind": "AUTHORITATIVE_VALUE",
        "paragraph_kind_rank": 1,
        "required_evidence_path_pattern": "/parameters/{index}/p50",
        "text_template": "{parameter_name} for variety {variety_id} has p50={p50}.",
    },
    {
        "template_id": "daily-curve-value-v1",
        "section": "DAILY_CURVE_SUMMARY",
        "paragraph_kind": "AUTHORITATIVE_VALUE",
        "paragraph_kind_rank": 1,
        "required_evidence_path": "/daily_curve/0/final_corrected_arrival_quantity_kg/p50",
        "text_template": "The first daily p50 arrival quantity is {p50} kg.",
    },
    {
        "template_id": "single-day-peak-v1",
        "section": "PEAK_ANALYSIS",
        "paragraph_kind": "AUTHORITATIVE_VALUE",
        "paragraph_kind_rank": 1,
        "required_evidence_path": "/peak/single_day_peak/P50/volume_kg",
        "text_template": "The P50 single-day peak is {volume_kg} kg.",
    },
    {
        "template_id": "peak-formation-v1",
        "section": "PEAK_FORMATION",
        "paragraph_kind": "DETERMINISTIC_EXPLANATION",
        "paragraph_kind_rank": 2,
        "required_evidence_path": (
            "/peak/sustained_3day_peak/P50/rolling_daily_average_kg_per_day"
        ),
        "text_template": ("Peak formation is disclosed by the cited sustained P50 statistic."),
    },
    {
        "template_id": "confidence-v1",
        "section": "CONFIDENCE_AND_UNCERTAINTY",
        "paragraph_kind": "DETERMINISTIC_EXPLANATION",
        "paragraph_kind_rank": 2,
        "required_evidence_path": "/confidence/level",
        "text_template": "Aggregate confidence is {confidence_level}.",
    },
    {
        "template_id": "authority-evidence-v1",
        "section": "MODEL_AND_AUTHORITY_EVIDENCE",
        "paragraph_kind": "DETERMINISTIC_EXPLANATION",
        "paragraph_kind_rank": 2,
        "required_evidence_path_pattern": "/provenance/task{number}_authority",
        "text_template": "The forecast is bound to typed persisted authority evidence.",
    },
    {
        "template_id": "blocker-gap-v1",
        "section": "BLOCKERS_AND_DATA_GAPS",
        "paragraph_kind": "DETERMINISTIC_EXPLANATION",
        "paragraph_kind_rank": 2,
        "required_evidence_path": "/blockers/0/code",
        "text_template": (
            "The output retains typed blockers and data gaps from upstream processing."
        ),
    },
]
_RECOMMENDATION_CONFIG = {
    "policy_version": RECOMMENDATION_POLICY_VERSION,
    "field_path_policy_version": FIELD_PATH_POLICY_VERSION,
    "category_order": list(CATEGORY_ORDER),
    "rule_order": ["category_rank", "priority_rank", "rule_id"],
    "rule_selection": {
        "winner": "first_fully_true_rule",
        "missing_required_evidence": "BLOCKED",
        "all_false": "NOT_APPLICABLE",
    },
    "blocker_order": [
        "code",
        "canonical_details_json",
        "canonical_citation_json",
        "retry_hint",
        "message",
    ],
    "missing_data_taxonomy": list(_MISSING_DATA_TAXONOMY),
    "missing_data_impact_level": _IMPACT_LEVEL,
    "missing_data_order": [
        "impact_level",
        "affected_field_count_descending",
        "code",
        "first_evidence_path",
    ],
}
_RULE_CATALOG = [
    {
        "category": category,
        "priority_rank": index + 1,
        "rule_id": (
            "missing-data-impact-v1"
            if category == "MISSING_DATA_IMPACT"
            else f"c1-blocked-{category.lower()}"
        ),
        "c2_source_required": category != "MISSING_DATA_IMPACT",
        "status": "BLOCKED" if category != "MISSING_DATA_IMPACT" else "EVALUATED",
        "reason_code": (
            "REQUIRED_THRESHOLD_MISSING" if category != "MISSING_DATA_IMPACT" else "RULE_DEPENDENT"
        ),
        "advisory_text": None if category != "MISSING_DATA_IMPACT" else "TEMPLATE_BOUND",
        "advisory_template": (
            None
            if category != "MISSING_DATA_IMPACT"
            else (
                "Review the cited missing evidence before relying on affected forecast dimensions."
            )
        ),
        "universal_non_action": "ADVISORY_ONLY_NO_AUTOMATIC_EXECUTION",
        "category_non_action": _CATEGORY_NON_ACTION[category],
    }
    for index, category in enumerate(CATEGORY_ORDER)
]


def explanation_policy() -> ExplanationRulePolicy:
    return ExplanationRulePolicy(
        policy_version=EXPLANATION_POLICY_VERSION,
        policy_config_hash=sha256_payload(_EXPLANATION_CONFIG),
        template_catalog_version=EXPLANATION_TEMPLATE_CATALOG_VERSION,
        template_catalog_hash=sha256_payload(_TEMPLATE_CATALOG),
    )


def explanation_policy_payload() -> dict[str, Any]:
    return deepcopy(_EXPLANATION_CONFIG)


def explanation_template_catalog() -> list[dict[str, Any]]:
    return deepcopy(_TEMPLATE_CATALOG)


def recommendation_policy() -> RecommendationRulePolicy:
    return RecommendationRulePolicy(
        policy_version=RECOMMENDATION_POLICY_VERSION,
        policy_config_hash=sha256_payload(_RECOMMENDATION_CONFIG),
        rule_catalog_version=RECOMMENDATION_RULE_CATALOG_VERSION,
        rule_catalog_hash=sha256_payload(_RULE_CATALOG),
    )


def recommendation_policy_payload() -> dict[str, Any]:
    return deepcopy(_RECOMMENDATION_CONFIG)


def recommendation_rule_catalog() -> list[dict[str, Any]]:
    return deepcopy(_RULE_CATALOG)


def _render_template(template_id: str, **values: object) -> str:
    template = next(
        row["text_template"] for row in _TEMPLATE_CATALOG if row["template_id"] == template_id
    )
    return str(template).format(**values)


def _recommendation_advisory(rule_id: str) -> str:
    template = next(row["advisory_template"] for row in _RULE_CATALOG if row["rule_id"] == rule_id)
    if not isinstance(template, str):
        raise ValueError("RECOMMENDATION_RULE_MISSING: advisory template is unavailable")
    return template


def canonical_blockers(blockers: list[Blocker]) -> list[Blocker]:
    unique: dict[str, Blocker] = {}
    for blocker in blockers:
        payload = blocker.model_dump(mode="json")
        unique.setdefault(canonical_json_dumps(payload), blocker)
    return sorted(
        unique.values(),
        key=lambda item: (
            item.code.value,
            canonical_json_dumps(item.details),
            canonical_json_dumps(item.citation),
            item.retry_hint,
            item.message,
        ),
    )


def _hashes(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            if (
                isinstance(key, str)
                and key.endswith("hash")
                and isinstance(child, str)
                and len(child) == 64
            ):
                found.add(child)
            found.update(_hashes(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_hashes(child))
    return found


def validate_citation(
    source_payload: Mapping[str, Any],
    citation: Citation,
    *,
    expected_value: object | None = None,
) -> object:
    try:
        resolved = resolve_json_pointer(source_payload, citation.field_path)
    except JsonPointerResolutionError as exc:
        raise ValueError(f"EVIDENCE_FIELD_PATH_INVALID: {exc}") from exc
    if expected_value is not None and canonical_json_dumps(resolved) != canonical_json_dumps(
        expected_value
    ):
        raise ValueError("EVIDENCE_HASH_MISMATCH: resolved value differs from rule input")
    if citation.agent_artifact_hash is not None and citation.agent_artifact_hash not in _hashes(
        source_payload
    ):
        raise ValueError("EVIDENCE_HASH_MISMATCH: citation artifact hash is not in source")
    return resolved


def _authority_entries(source: Mapping[str, Any]) -> list[CitationAuthorityEntry]:
    provenance = source.get("provenance")
    if not isinstance(provenance, Mapping):
        return []
    entries: list[CitationAuthorityEntry] = []
    for number in (8, 9, 10, 11, 12):
        authority = provenance.get(f"task{number}_authority")
        if authority is None:
            continue
        entries.append(
            CitationAuthorityEntry.model_validate(
                {"authority_type": f"TASK_{number}_AUTHORITY", "authority": authority}
            )
        )
    return entries


def _citation(
    source: Mapping[str, Any],
    *,
    pointer: str,
    source_tool: str,
    artifact_hash: str | None = None,
) -> Citation:
    authorities = _authority_entries(source)
    tasks = [
        {
            "TASK_8_AUTHORITY": "TASK_008",
            "TASK_9_AUTHORITY": "TASK_009",
            "TASK_10_AUTHORITY": "TASK_010",
            "TASK_11_AUTHORITY": "TASK_011",
            "TASK_12_AUTHORITY": "TASK_012",
        }[entry.authority_type]
        for entry in authorities
    ]
    normalized = source.get("normalized_request")
    as_of = normalized.get("effective_as_of_date") if isinstance(normalized, Mapping) else None
    citation = Citation.model_validate(
        {
            "source_tasks": tasks or ["TASK_013"],
            "source_tool": source_tool,
            "authorities": [entry.model_dump(mode="python") for entry in authorities],
            "agent_artifact_hash": artifact_hash,
            "field_path": pointer,
            "effective_as_of_date": as_of,
            "confidence_evidence": None,
            "tags": [],
            "override_refs": [],
        }
    )
    validate_citation(source, citation)
    return citation


def _paragraph_key(paragraph: ExplainParagraph) -> tuple[int, str, str]:
    kind_rank = 1 if paragraph.kind == "AUTHORITATIVE_VALUE" else 2
    return kind_rank, paragraph.template_id, sorted(paragraph.evidence_field_paths)[0]


def _dedupe_paragraphs(paragraphs: list[ExplainParagraph]) -> list[ExplainParagraph]:
    unique: dict[str, ExplainParagraph] = {}
    for paragraph in paragraphs:
        unique.setdefault(canonical_json_dumps(paragraph.model_dump(mode="json")), paragraph)
    return sorted(unique.values(), key=_paragraph_key)


def _authoritative_paragraph(
    source: Mapping[str, Any],
    *,
    pointer: str,
    template_id: str,
    text: str,
    source_tool: str,
    artifact_hash: str | None = None,
) -> ExplainParagraph:
    citation = _citation(
        source,
        pointer=pointer,
        source_tool=source_tool,
        artifact_hash=artifact_hash,
    )
    return ExplainParagraph(
        kind="AUTHORITATIVE_VALUE",
        text=text,
        template_id=template_id,
        evidence_field_paths=[pointer],
        citation=citation,
    )


def build_explanation(source: Mapping[str, Any]) -> ExplainForecastOutput:
    paragraphs: dict[str, list[ExplainParagraph]] = {section: [] for section in SECTION_ORDER}
    normalized = source.get("normalized_request")
    if isinstance(normalized, Mapping) and normalized.get("canonical_request_hash") is not None:
        pointer = "/normalized_request/canonical_request_hash"
        paragraphs["REQUEST_AND_RESOLVED_CONTEXT"].append(
            ExplainParagraph(
                kind="DETERMINISTIC_EXPLANATION",
                text=_render_template("request-context-v1"),
                template_id="request-context-v1",
                evidence_field_paths=[pointer],
            )
        )

    parameters = source.get("parameters")
    if isinstance(parameters, list):
        for index, parameter in enumerate(parameters):
            if not isinstance(parameter, Mapping) or parameter.get("p50") is None:
                continue
            pointer = f"/parameters/{index}/p50"
            paragraphs["PARAMETER_PROVENANCE"].append(
                _authoritative_paragraph(
                    source,
                    pointer=pointer,
                    template_id="parameter-value-v1",
                    text=_render_template(
                        "parameter-value-v1",
                        parameter_name=parameter.get("parameter_name"),
                        variety_id=parameter.get("variety_id"),
                        p50=parameter.get("p50"),
                    ),
                    source_tool="INFER_PARAMETERS",
                )
            )

    daily = source.get("daily_curve")
    if isinstance(daily, list) and daily:
        pointer = "/daily_curve/0/final_corrected_arrival_quantity_kg/p50"
        first = daily[0]
        artifact = first.get("agent_daily_row_hash") if isinstance(first, Mapping) else None
        paragraphs["DAILY_CURVE_SUMMARY"].append(
            _authoritative_paragraph(
                source,
                pointer=pointer,
                template_id="daily-curve-value-v1",
                text=_render_template(
                    "daily-curve-value-v1",
                    p50=resolve_json_pointer(source, pointer),
                ),
                source_tool="FORECAST_DAILY_CURVE",
                artifact_hash=artifact if isinstance(artifact, str) else None,
            )
        )

    peak = source.get("peak")
    if isinstance(peak, Mapping) and peak.get("single_day_peak"):
        artifact = peak.get("agent_peak_hash")
        pointer = "/peak/single_day_peak/P50/volume_kg"
        paragraphs["PEAK_ANALYSIS"].append(
            _authoritative_paragraph(
                source,
                pointer=pointer,
                template_id="single-day-peak-v1",
                text=_render_template(
                    "single-day-peak-v1",
                    volume_kg=resolve_json_pointer(source, pointer),
                ),
                source_tool="FORECAST_PEAK",
                artifact_hash=artifact if isinstance(artifact, str) else None,
            )
        )
    if isinstance(peak, Mapping) and peak.get("sustained_3day_peak"):
        pointer = "/peak/sustained_3day_peak/P50/rolling_daily_average_kg_per_day"
        paragraphs["PEAK_FORMATION"].append(
            ExplainParagraph(
                kind="DETERMINISTIC_EXPLANATION",
                text=_render_template("peak-formation-v1"),
                template_id="peak-formation-v1",
                evidence_field_paths=[pointer],
            )
        )

    confidence = source.get("confidence")
    if isinstance(confidence, Mapping) and confidence.get("level") is not None:
        pointer = "/confidence/level"
        paragraphs["CONFIDENCE_AND_UNCERTAINTY"].append(
            ExplainParagraph(
                kind="DETERMINISTIC_EXPLANATION",
                text=_render_template(
                    "confidence-v1",
                    confidence_level=confidence.get("level"),
                ),
                template_id="confidence-v1",
                evidence_field_paths=[pointer],
            )
        )

    provenance = source.get("provenance")
    if isinstance(provenance, Mapping):
        for key in ("task10_authority", "task9_authority", "task8_authority"):
            if provenance.get(key) is not None:
                pointer = f"/provenance/{key}"
                paragraphs["MODEL_AND_AUTHORITY_EVIDENCE"].append(
                    ExplainParagraph(
                        kind="DETERMINISTIC_EXPLANATION",
                        text=_render_template("authority-evidence-v1"),
                        template_id="authority-evidence-v1",
                        evidence_field_paths=[pointer],
                    )
                )
                break

    blockers = source.get("blockers")
    if isinstance(blockers, list) and blockers:
        paragraphs["BLOCKERS_AND_DATA_GAPS"].append(
            ExplainParagraph(
                kind="DETERMINISTIC_EXPLANATION",
                text=_render_template("blocker-gap-v1"),
                template_id="blocker-gap-v1",
                evidence_field_paths=["/blockers/0/code"],
            )
        )

    sections = [
        ExplainSection(section=section, paragraphs=_dedupe_paragraphs(paragraphs[section]))
        for section in SECTION_ORDER
    ]
    policy = explanation_policy()
    output = ExplainForecastOutput(
        explanation_rule_policy_version=policy.policy_version,
        explanation_rule_policy_config_hash=policy.policy_config_hash,
        template_catalog_version=policy.template_catalog_version,
        template_catalog_hash=policy.template_catalog_hash,
        structured_payload=sections,
        agent_explanation_hash="0" * 64,
        blockers=canonical_blockers(
            [Blocker.model_validate(item) for item in blockers]
            if isinstance(blockers, list)
            else []
        ),
    )
    return output.model_copy(
        update={
            "agent_explanation_hash": sha256_payload(
                output.model_dump(mode="python", exclude={"agent_explanation_hash"})
            )
        }
    )


def _operational_decision(category: RecommendationCategory, rank: int) -> RecommendationDecision:
    blocker = Blocker(
        code=BlockerCode.RECOMMENDATION_THRESHOLD_MISSING,
        message="C2 business source package is unavailable",
        details={"category": category, "phase": "C1"},
        retry_hint="CONTACT_OPS",
    )
    return RecommendationDecision(
        category=category,
        kind="OPERATIONAL",
        status="BLOCKED",
        reason_code="REQUIRED_THRESHOLD_MISSING",
        reason_details={"source_package": f"C2-B{rank:02d}"},
        priority_rank=rank,
        rule_id=f"c1-blocked-{category.lower()}",
        template_id="operational-source-required-v1",
        advisory_text=None,
        applicability_conditions=[],
        evidence=[],
        risk_codes=[],
        confidence=None,
        confidence_boundary=None,
        blocker_dependencies=[blocker],
        non_action=NonAction(category_specific_code=_CATEGORY_NON_ACTION[category]),
    )


def _missing_items(source: Mapping[str, Any]) -> dict[MissingDataImpactCode, list[str]]:
    items: dict[MissingDataImpactCode, list[str]] = defaultdict(list)
    parameters = source.get("parameters")
    if isinstance(parameters, list):
        for index, parameter in enumerate(parameters):
            if not isinstance(parameter, Mapping):
                continue
            for field, code in (
                ("sample_count", "PARAMETER_SAMPLE_COVERAGE_INSUFFICIENT"),
                ("season_count", "PARAMETER_SEASON_COVERAGE_INSUFFICIENT"),
                ("farm_count", "PARAMETER_FARM_COVERAGE_INSUFFICIENT"),
            ):
                if parameter.get(field) == 0:
                    items[cast(MissingDataImpactCode, code)].append(f"/parameters/{index}/{field}")
            missing = parameter.get("missing_evidence")
            if isinstance(missing, list):
                for missing_index, value in enumerate(missing):
                    if isinstance(value, str) and "maturity" in value.lower():
                        items["PHENOLOGY_EVIDENCE_MISSING"].append(
                            f"/parameters/{index}/missing_evidence/{missing_index}"
                        )
            if parameter.get("citation") is None:
                items["REQUIRED_CITATION_MISSING"].append(f"/parameters/{index}/citation")

    blockers = source.get("blockers")
    if isinstance(blockers, list):
        for index, blocker in enumerate(blockers):
            if not isinstance(blocker, Mapping):
                continue
            code = str(blocker.get("code", ""))
            pointer = f"/blockers/{index}/code"
            if "AUTHORITY" in code:
                items["REQUIRED_AUTHORITY_MISSING"].append(pointer)
            elif "CITATION" in code:
                items["REQUIRED_CITATION_MISSING"].append(pointer)
            elif code in {"INSUFFICIENT_HISTORY", "NO_PERSISTED_PRIOR_SOURCE"}:
                items["HISTORICAL_ERROR_EVIDENCE_MISSING"].append(pointer)
            elif "POLICY_MISSING" in code:
                items["REQUIRED_PROVENANCE_MISSING"].append(pointer)
    return {code: sorted(set(paths)) for code, paths in items.items()}


def _missing_data_decision(source: Mapping[str, Any]) -> RecommendationDecision:
    items = _missing_items(source)
    if not items:
        return RecommendationDecision(
            category="MISSING_DATA_IMPACT",
            kind="DATA_QUALITY",
            status="NOT_APPLICABLE",
            reason_code="CONDITIONS_NOT_MET",
            reason_details={"missing_item_count": 0},
            priority_rank=7,
            rule_id="missing-data-impact-v1",
            template_id="missing-data-impact-template-v1",
            advisory_text=None,
            applicability_conditions=[],
            evidence=[],
            risk_codes=[],
            confidence=None,
            confidence_boundary=None,
            blocker_dependencies=[],
            non_action=NonAction(
                category_specific_code=_CATEGORY_NON_ACTION["MISSING_DATA_IMPACT"]
            ),
        )

    ordered = sorted(
        items.items(),
        key=lambda item: (_IMPACT_LEVEL[item[0]], -len(item[1]), item[0], item[1][0]),
    )
    conditions: list[ConditionEvaluation] = []
    evidence: list[RecommendationEvidence] = []
    for code, paths in ordered:
        for pointer in paths:
            observed = resolve_json_pointer(source, pointer)
            citation = _citation(
                source,
                pointer=pointer,
                source_tool="GENERATE_RECOMMENDATIONS",
            )
            conditions.append(
                ConditionEvaluation(
                    field_path=pointer,
                    operator="MISSING_EVIDENCE_PRESENT",
                    observed_value=(observed if isinstance(observed, (str, int, bool)) else None),
                    threshold_value=None,
                    unit=None,
                    result="TRUE",
                    citation=citation,
                )
            )
            evidence.append(
                RecommendationEvidence(
                    citation=citation,
                    affected_field_paths=[pointer],
                    missing_data_code=code,
                    threshold=None,
                )
            )

    return RecommendationDecision(
        category="MISSING_DATA_IMPACT",
        kind="DATA_QUALITY",
        status="APPLICABLE",
        reason_code="RULE_APPLICABLE",
        reason_details={"missing_item_count": len(conditions)},
        priority_rank=7,
        rule_id="missing-data-impact-v1",
        template_id="missing-data-impact-template-v1",
        advisory_text=_recommendation_advisory("missing-data-impact-v1"),
        applicability_conditions=conditions,
        evidence=evidence,
        risk_codes=[code for code, _ in ordered],
        confidence="LOW",
        confidence_boundary={"claim": "No forecast improvement is guaranteed."},
        blocker_dependencies=[],
        non_action=NonAction(category_specific_code=_CATEGORY_NON_ACTION["MISSING_DATA_IMPACT"]),
    )


def build_recommendations(source: Mapping[str, Any]) -> GenerateRecommendationsOutput:
    decisions = [
        _operational_decision(category, rank)
        for rank, category in enumerate(OPERATIONAL_CATEGORIES, start=1)
    ]
    decisions.append(_missing_data_decision(source))
    policy = recommendation_policy()
    upstream = source.get("blockers")
    blockers = canonical_blockers(
        ([Blocker.model_validate(item) for item in upstream] if isinstance(upstream, list) else [])
        + [blocker for decision in decisions for blocker in decision.blocker_dependencies]
    )
    output = GenerateRecommendationsOutput(
        recommendation_rule_policy_version=policy.policy_version,
        recommendation_rule_policy_config_hash=policy.policy_config_hash,
        rule_catalog_version=policy.rule_catalog_version,
        rule_catalog_hash=policy.rule_catalog_hash,
        decisions=decisions,
        agent_recommendations_hash="0" * 64,
        blockers=blockers,
    )
    return output.model_copy(
        update={
            "agent_recommendations_hash": sha256_payload(
                output.model_dump(mode="python", exclude={"agent_recommendations_hash"})
            )
        }
    )


def build_slice_c_outputs(
    source: Mapping[str, Any],
) -> tuple[ExplainForecastOutput, GenerateRecommendationsOutput]:
    """Build sibling outputs from the same immutable Slice B payload."""

    return build_explanation(source), build_recommendations(source)


__all__ = [
    "EXPLANATION_POLICY_VERSION",
    "EXPLANATION_TEMPLATE_CATALOG_VERSION",
    "FIELD_PATH_POLICY_VERSION",
    "RECOMMENDATION_POLICY_VERSION",
    "RECOMMENDATION_RULE_CATALOG_VERSION",
    "build_explanation",
    "build_recommendations",
    "build_slice_c_outputs",
    "canonical_blockers",
    "explanation_policy",
    "explanation_policy_payload",
    "explanation_template_catalog",
    "recommendation_policy",
    "recommendation_policy_payload",
    "recommendation_rule_catalog",
    "validate_citation",
]
