"""Deterministic Slice C explanation and recommendation engines."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, cast, get_args

from pydantic import ValidationError

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
    SliceCSourcePayload,
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


class SliceCEvidenceError(ValueError):
    """Stable internal evidence failure converted to a typed Slice C blocker."""

    def __init__(self, code: BlockerCode, message: str, *, field_path: str | None = None):
        super().__init__(f"{code.value}: {message}")
        self.code = code
        self.field_path = field_path


@dataclass(frozen=True)
class ArtifactBinding:
    owner_kind: str
    owner_field_path: str
    expected_artifact_hash: str | None
    authority_identity: tuple[str, ...]
    source_tasks: tuple[str, ...]
    canonical_citation: Citation


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


def _validated_source(source: SliceCSourcePayload | Mapping[str, Any]) -> SliceCSourcePayload:
    if isinstance(source, SliceCSourcePayload):
        return source
    return SliceCSourcePayload.model_validate(source)


def _source_dump(source: SliceCSourcePayload) -> dict[str, Any]:
    return source.model_dump(mode="json")


def _authority_identity(citation: Citation) -> tuple[str, ...]:
    return tuple(
        canonical_json_dumps(entry.model_dump(mode="json")) for entry in citation.authorities
    )


def _citation_owner_identity(citation: Citation) -> str:
    return canonical_json_dumps(citation.model_dump(mode="json", exclude={"field_path"}))


def _provenance_authority_entry(
    source: SliceCSourcePayload, number: int
) -> CitationAuthorityEntry | None:
    authority = getattr(source.provenance, f"task{number}_authority")
    if authority is None:
        return None
    try:
        return CitationAuthorityEntry.model_validate(
            {"authority_type": f"TASK_{number}_AUTHORITY", "authority": authority}
        )
    except ValidationError as exc:
        raise SliceCEvidenceError(
            BlockerCode.REQUIRED_PROVENANCE_MISSING,
            f"Task {number} authority provenance is malformed",
            field_path=f"/provenance/task{number}_authority",
        ) from exc


def _expected_authorities(
    source: SliceCSourcePayload, numbers: tuple[int, ...]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    entries = [
        entry
        for number in numbers
        if (entry := _provenance_authority_entry(source, number)) is not None
    ]
    return (
        tuple(canonical_json_dumps(entry.model_dump(mode="json")) for entry in entries),
        tuple(
            f"TASK_{number:03d}"
            for number in numbers
            if getattr(source.provenance, f"task{number}_authority") is not None
        ),
    )


def _citation_index(source: SliceCSourcePayload) -> dict[str, Citation]:
    indexed: dict[str, Citation] = {}
    for citation in source.citations:
        previous = indexed.get(citation.field_path)
        if previous is not None and canonical_json_dumps(
            previous.model_dump(mode="json")
        ) != canonical_json_dumps(citation.model_dump(mode="json")):
            raise SliceCEvidenceError(
                BlockerCode.EVIDENCE_HASH_MISMATCH,
                "multiple non-identical citations claim the same evidence field",
                field_path=citation.field_path,
            )
        indexed[citation.field_path] = citation
    return indexed


def _canonical_citation(source: SliceCSourcePayload, field_path: str) -> Citation:
    citation = _citation_index(source).get(field_path)
    if citation is None:
        raise SliceCEvidenceError(
            BlockerCode.REQUIRED_CITATION_MISSING,
            "required canonical upstream citation is missing",
            field_path=field_path,
        )
    return citation


def resolve_artifact_binding(
    source: SliceCSourcePayload | Mapping[str, Any],
    field_path: str,
) -> ArtifactBinding:
    """Resolve the one artifact and authority identity that owns ``field_path``."""

    validated = _validated_source(source)
    parameter_match = re.fullmatch(r"/parameters/(\d+)/(?:[^/]+(?:/[^/]+)*)", field_path)
    daily_match = re.fullmatch(r"/daily_curve/(\d+)/(?:[^/]+(?:/[^/]+)*)", field_path)
    if parameter_match:
        index = int(parameter_match.group(1))
        if index >= len(validated.parameters):
            raise SliceCEvidenceError(
                BlockerCode.EVIDENCE_FIELD_PATH_INVALID,
                "parameter evidence index is out of range",
                field_path=field_path,
            )
        parameter_citation = validated.parameters[index].citation
        if parameter_citation is None:
            raise SliceCEvidenceError(
                BlockerCode.REQUIRED_CITATION_MISSING,
                "parameter value has no upstream citation",
                field_path=field_path,
            )
        if parameter_citation.authorities or parameter_citation.agent_artifact_hash is not None:
            raise SliceCEvidenceError(
                BlockerCode.EVIDENCE_HASH_MISMATCH,
                "parameter citation claims an unsupported authority or artifact owner",
                field_path=field_path,
            )
        raise SliceCEvidenceError(
            BlockerCode.REQUIRED_AUTHORITY_MISSING,
            "parameter evidence has no supported typed parameter authority",
            field_path=field_path,
        )
    citation = _canonical_citation(validated, field_path)
    if daily_match:
        index = int(daily_match.group(1))
        if index >= len(validated.daily_curve):
            raise SliceCEvidenceError(
                BlockerCode.EVIDENCE_FIELD_PATH_INVALID,
                "daily evidence index is out of range",
                field_path=field_path,
            )
        authority_identity, source_tasks = _expected_authorities(validated, (8, 9, 10, 11, 12))
        return ArtifactBinding(
            owner_kind="DAILY_CURVE_ROW",
            owner_field_path=f"/daily_curve/{index}/agent_daily_row_hash",
            expected_artifact_hash=validated.daily_curve[index].agent_daily_row_hash,
            authority_identity=authority_identity,
            source_tasks=source_tasks,
            canonical_citation=citation,
        )
    if field_path.startswith("/peak/"):
        artifact_hash = validated.peak.agent_peak_hash
        authority_identity, source_tasks = _expected_authorities(validated, (8, 9, 10, 11, 12))
        return ArtifactBinding(
            owner_kind="PEAK_OUTPUT",
            owner_field_path="/peak/agent_peak_hash",
            expected_artifact_hash=artifact_hash,
            authority_identity=authority_identity,
            source_tasks=source_tasks,
            canonical_citation=citation,
        )
    provenance_match = re.fullmatch(r"/provenance/task(8|9|10|11|12)_authority", field_path)
    if provenance_match:
        number = int(provenance_match.group(1))
        entry = _provenance_authority_entry(validated, number)
        if entry is None:
            raise SliceCEvidenceError(
                BlockerCode.REQUIRED_AUTHORITY_MISSING,
                f"Task {number} authority provenance is missing",
                field_path=field_path,
            )
        return ArtifactBinding(
            owner_kind="PROVENANCE",
            owner_field_path=field_path,
            expected_artifact_hash=citation.agent_artifact_hash,
            authority_identity=(canonical_json_dumps(entry.model_dump(mode="json")),),
            source_tasks=(f"TASK_{number:03d}",),
            canonical_citation=citation,
        )
    if field_path.startswith("/blockers/"):
        if (
            citation.source_tasks != ["TASK_013"]
            or citation.source_tool != "GENERATE_RECOMMENDATIONS"
            or citation.authorities
            or citation.agent_artifact_hash is not None
            or citation.tags
            or citation.override_refs
        ):
            raise SliceCEvidenceError(
                BlockerCode.EVIDENCE_HASH_MISMATCH,
                "blocker metadata citation exceeds its agent-observed ownership boundary",
                field_path=field_path,
            )
        return ArtifactBinding(
            owner_kind="UPSTREAM_BLOCKER_METADATA",
            owner_field_path=field_path.rsplit("/", 1)[0],
            expected_artifact_hash=None,
            authority_identity=(),
            source_tasks=("TASK_013",),
            canonical_citation=citation,
        )
    raise SliceCEvidenceError(
        BlockerCode.EVIDENCE_FIELD_PATH_INVALID,
        "field path has no frozen artifact ownership rule",
        field_path=field_path,
    )


def validate_citation(
    source_payload: SliceCSourcePayload | Mapping[str, Any],
    citation: Citation,
    *,
    expected_value: object | None = None,
) -> object:
    source = _validated_source(source_payload)
    dumped = _source_dump(source)
    try:
        resolved = resolve_json_pointer(dumped, citation.field_path)
    except JsonPointerResolutionError as exc:
        raise SliceCEvidenceError(
            BlockerCode.EVIDENCE_FIELD_PATH_INVALID,
            str(exc),
            field_path=citation.field_path,
        ) from exc
    if expected_value is not None and canonical_json_dumps(resolved) != canonical_json_dumps(
        expected_value
    ):
        raise SliceCEvidenceError(
            BlockerCode.EVIDENCE_HASH_MISMATCH,
            "resolved value differs from the value consumed by the rule",
            field_path=citation.field_path,
        )
    binding = resolve_artifact_binding(source, citation.field_path)
    if binding.owner_kind in {"PARAMETER_ESTIMATE", "DAILY_CURVE_ROW", "PEAK_OUTPUT"}:
        if not citation.authorities:
            raise SliceCEvidenceError(
                BlockerCode.REQUIRED_AUTHORITY_MISSING,
                "numerical evidence has no upstream authority envelope",
                field_path=citation.field_path,
            )
        if "TASK_013" in citation.source_tasks:
            raise SliceCEvidenceError(
                BlockerCode.REQUIRED_AUTHORITY_MISSING,
                "TASK-013 cannot be used as numerical authority",
                field_path=citation.field_path,
            )
    if canonical_json_dumps(citation.model_dump(mode="json")) != canonical_json_dumps(
        binding.canonical_citation.model_dump(mode="json")
    ):
        raise SliceCEvidenceError(
            BlockerCode.EVIDENCE_HASH_MISMATCH,
            "citation differs from the canonical upstream citation",
            field_path=citation.field_path,
        )
    if citation.agent_artifact_hash != binding.expected_artifact_hash:
        raise SliceCEvidenceError(
            BlockerCode.EVIDENCE_HASH_MISMATCH,
            "citation artifact hash does not match the field owner",
            field_path=citation.field_path,
        )
    if _authority_identity(citation) != binding.authority_identity:
        raise SliceCEvidenceError(
            BlockerCode.EVIDENCE_HASH_MISMATCH,
            "citation authority does not match the field owner",
            field_path=citation.field_path,
        )
    if tuple(citation.source_tasks) != binding.source_tasks:
        raise SliceCEvidenceError(
            BlockerCode.EVIDENCE_HASH_MISMATCH,
            "citation source tasks do not match the field owner",
            field_path=citation.field_path,
        )
    return resolved


def _paragraph_key(paragraph: ExplainParagraph) -> tuple[int, str, str]:
    kind_rank = 1 if paragraph.kind == "AUTHORITATIVE_VALUE" else 2
    return kind_rank, paragraph.template_id, sorted(paragraph.evidence_field_paths)[0]


def _dedupe_paragraphs(paragraphs: list[ExplainParagraph]) -> list[ExplainParagraph]:
    unique: dict[str, ExplainParagraph] = {}
    for paragraph in paragraphs:
        unique.setdefault(canonical_json_dumps(paragraph.model_dump(mode="json")), paragraph)
    return sorted(unique.values(), key=_paragraph_key)


def _authoritative_paragraph(
    source: SliceCSourcePayload,
    *,
    pointer: str,
    template_id: str,
    text: str,
) -> ExplainParagraph:
    resolve_artifact_binding(source, pointer)
    citation = _canonical_citation(source, pointer)
    validate_citation(
        source,
        citation,
        expected_value=resolve_json_pointer(_source_dump(source), pointer),
    )
    return ExplainParagraph(
        kind="AUTHORITATIVE_VALUE",
        text=text,
        template_id=template_id,
        evidence_field_paths=[pointer],
        citation=citation,
    )


def _evidence_blocker(error: SliceCEvidenceError) -> Blocker:
    return Blocker(
        code=error.code,
        message=str(error),
        details={"field_path": error.field_path} if error.field_path is not None else None,
        retry_hint="PROVIDE_OVERRIDE",
    )


def build_explanation(source: SliceCSourcePayload) -> ExplainForecastOutput:
    paragraphs: dict[str, list[ExplainParagraph]] = {section: [] for section in SECTION_ORDER}
    evidence_blockers: list[Blocker] = []
    dumped = _source_dump(source)
    pointer = "/normalized_request/canonical_request_hash"
    paragraphs["REQUEST_AND_RESOLVED_CONTEXT"].append(
        ExplainParagraph(
            kind="DETERMINISTIC_EXPLANATION",
            text=_render_template("request-context-v1"),
            template_id="request-context-v1",
            evidence_field_paths=[pointer],
        )
    )

    for index, parameter in enumerate(source.parameters):
        pointer = f"/parameters/{index}/p50"
        try:
            paragraphs["PARAMETER_PROVENANCE"].append(
                _authoritative_paragraph(
                    source,
                    pointer=pointer,
                    template_id="parameter-value-v1",
                    text=_render_template(
                        "parameter-value-v1",
                        parameter_name=parameter.parameter_name,
                        variety_id=parameter.variety_id,
                        p50=parameter.p50,
                    ),
                )
            )
        except SliceCEvidenceError as exc:
            evidence_blockers.append(_evidence_blocker(exc))

    if source.daily_curve:
        pointer = "/daily_curve/0/final_corrected_arrival_quantity_kg/p50"
        try:
            paragraphs["DAILY_CURVE_SUMMARY"].append(
                _authoritative_paragraph(
                    source,
                    pointer=pointer,
                    template_id="daily-curve-value-v1",
                    text=_render_template(
                        "daily-curve-value-v1",
                        p50=resolve_json_pointer(dumped, pointer),
                    ),
                )
            )
        except SliceCEvidenceError as exc:
            evidence_blockers.append(_evidence_blocker(exc))

    if source.peak.single_day_peak:
        pointer = "/peak/single_day_peak/P50/volume_kg"
        try:
            paragraphs["PEAK_ANALYSIS"].append(
                _authoritative_paragraph(
                    source,
                    pointer=pointer,
                    template_id="single-day-peak-v1",
                    text=_render_template(
                        "single-day-peak-v1",
                        volume_kg=resolve_json_pointer(dumped, pointer),
                    ),
                )
            )
        except SliceCEvidenceError as exc:
            evidence_blockers.append(_evidence_blocker(exc))
    if source.peak.sustained_3day_peak:
        pointer = "/peak/sustained_3day_peak/P50/rolling_daily_average_kg_per_day"
        try:
            citation = _canonical_citation(source, pointer)
            validate_citation(source, citation)
            paragraphs["PEAK_FORMATION"].append(
                ExplainParagraph(
                    kind="DETERMINISTIC_EXPLANATION",
                    text=_render_template("peak-formation-v1"),
                    template_id="peak-formation-v1",
                    evidence_field_paths=[pointer],
                    citation=citation,
                )
            )
        except SliceCEvidenceError as exc:
            evidence_blockers.append(_evidence_blocker(exc))

    if source.confidence.level is not None:
        pointer = "/confidence/level"
        paragraphs["CONFIDENCE_AND_UNCERTAINTY"].append(
            ExplainParagraph(
                kind="DETERMINISTIC_EXPLANATION",
                text=_render_template(
                    "confidence-v1",
                    confidence_level=source.confidence.level,
                ),
                template_id="confidence-v1",
                evidence_field_paths=[pointer],
            )
        )

    for key in ("task10_authority", "task9_authority", "task8_authority"):
        if getattr(source.provenance, key) is not None:
            pointer = f"/provenance/{key}"
            try:
                citation = _canonical_citation(source, pointer)
                validate_citation(source, citation)
                paragraphs["MODEL_AND_AUTHORITY_EVIDENCE"].append(
                    ExplainParagraph(
                        kind="DETERMINISTIC_EXPLANATION",
                        text=_render_template("authority-evidence-v1"),
                        template_id="authority-evidence-v1",
                        evidence_field_paths=[pointer],
                        citation=citation,
                    )
                )
            except SliceCEvidenceError as exc:
                evidence_blockers.append(_evidence_blocker(exc))
            break

    if source.blockers:
        pointer = "/blockers/0/code"
        try:
            citation = _canonical_citation(source, pointer)
            validate_citation(source, citation)
            paragraphs["BLOCKERS_AND_DATA_GAPS"].append(
                ExplainParagraph(
                    kind="DETERMINISTIC_EXPLANATION",
                    text=_render_template("blocker-gap-v1"),
                    template_id="blocker-gap-v1",
                    evidence_field_paths=[pointer],
                    citation=citation,
                )
            )
        except SliceCEvidenceError as exc:
            evidence_blockers.append(_evidence_blocker(exc))

    all_blockers = canonical_blockers([*source.blockers, *evidence_blockers])

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
        blockers=all_blockers,
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


def _missing_items(source: SliceCSourcePayload) -> dict[MissingDataImpactCode, list[str]]:
    items: dict[MissingDataImpactCode, list[str]] = defaultdict(list)
    for index, blocker in enumerate(source.blockers):
        code = blocker.code.value
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


def _blocked_missing_data_decision(blockers: list[Blocker]) -> RecommendationDecision:
    return RecommendationDecision(
        category="MISSING_DATA_IMPACT",
        kind="DATA_QUALITY",
        status="BLOCKED",
        reason_code="REQUIRED_EVIDENCE_MISSING",
        reason_details={"evidence_blocker_count": len(blockers)},
        priority_rank=7,
        rule_id="missing-data-impact-v1",
        template_id="missing-data-impact-template-v1",
        advisory_text=None,
        applicability_conditions=[],
        evidence=[],
        risk_codes=sorted({blocker.code.value for blocker in blockers}),
        confidence=None,
        confidence_boundary=None,
        blocker_dependencies=canonical_blockers(blockers),
        non_action=NonAction(category_specific_code=_CATEGORY_NON_ACTION["MISSING_DATA_IMPACT"]),
    )


def _missing_data_decision(source: SliceCSourcePayload) -> RecommendationDecision:
    parameter_evidence_blockers: list[Blocker] = []
    for index, parameter in enumerate(source.parameters):
        has_missing_signal = (
            parameter.sample_count == 0
            or parameter.season_count == 0
            or parameter.farm_count == 0
            or bool(parameter.missing_evidence)
        )
        if not has_missing_signal:
            continue
        try:
            resolve_artifact_binding(source, f"/parameters/{index}/p50")
        except SliceCEvidenceError as exc:
            parameter_evidence_blockers.append(_evidence_blocker(exc))
    if parameter_evidence_blockers:
        return _blocked_missing_data_decision(parameter_evidence_blockers)

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
    evidence_blockers: list[Blocker] = []
    dumped = _source_dump(source)
    for code, paths in ordered:
        for pointer in paths:
            try:
                observed = resolve_json_pointer(dumped, pointer)
                citation = _canonical_citation(source, pointer)
                validate_citation(source, citation, expected_value=observed)
            except (JsonPointerResolutionError, SliceCEvidenceError) as exc:
                if isinstance(exc, SliceCEvidenceError):
                    evidence_blockers.append(_evidence_blocker(exc))
                else:
                    evidence_blockers.append(
                        _evidence_blocker(
                            SliceCEvidenceError(
                                BlockerCode.EVIDENCE_FIELD_PATH_INVALID,
                                str(exc),
                                field_path=pointer,
                            )
                        )
                    )
                continue
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

    if evidence_blockers:
        return _blocked_missing_data_decision(evidence_blockers)

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


def build_recommendations(source: SliceCSourcePayload) -> GenerateRecommendationsOutput:
    decisions = [
        _operational_decision(category, rank)
        for rank, category in enumerate(OPERATIONAL_CATEGORIES, start=1)
    ]
    decisions.append(_missing_data_decision(source))
    policy = recommendation_policy()
    blockers = canonical_blockers(
        source.blockers
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


def _invalid_source_outputs(
    error: ValidationError,
) -> tuple[ExplainForecastOutput, GenerateRecommendationsOutput]:
    evidence_blockers: list[Blocker] = []
    for item in error.errors(
        include_url=False,
        include_context=False,
        include_input=False,
    ):
        location = list(item["loc"])
        top = location[0] if location else None
        nested = str(location[1]) if len(location) > 1 else ""
        if top == "provenance" and re.fullmatch(r"task(?:8|9|10|11|12)_authority", nested):
            code = BlockerCode.REQUIRED_AUTHORITY_MISSING
        elif item["type"] == "extra_forbidden" or "field_path" in location:
            code = BlockerCode.EVIDENCE_FIELD_PATH_INVALID
        elif top == "citations":
            code = BlockerCode.REQUIRED_CITATION_MISSING
        elif top == "provenance":
            code = BlockerCode.REQUIRED_PROVENANCE_MISSING
        elif top == "normalized_request":
            code = BlockerCode.REQUIRED_PROVENANCE_MISSING
        else:
            code = BlockerCode.EVIDENCE_FIELD_PATH_INVALID
        evidence_blockers.append(
            Blocker(
                code=code,
                message="Slice B source contract validation failed",
                details={
                    "validation_location": location,
                    "validation_type": item["type"],
                    "input_field": str(location[-1]) if location else None,
                },
                retry_hint="FIX_INPUT",
            )
        )
    evidence_blockers = canonical_blockers(evidence_blockers)
    explanation_policy_value = explanation_policy()
    explanation = ExplainForecastOutput(
        explanation_rule_policy_version=explanation_policy_value.policy_version,
        explanation_rule_policy_config_hash=explanation_policy_value.policy_config_hash,
        template_catalog_version=explanation_policy_value.template_catalog_version,
        template_catalog_hash=explanation_policy_value.template_catalog_hash,
        structured_payload=[
            ExplainSection(section=section, paragraphs=[]) for section in SECTION_ORDER
        ],
        agent_explanation_hash="0" * 64,
        blockers=evidence_blockers,
    )
    explanation = explanation.model_copy(
        update={
            "agent_explanation_hash": sha256_payload(
                explanation.model_dump(mode="python", exclude={"agent_explanation_hash"})
            )
        }
    )
    decisions = [
        _operational_decision(category, rank)
        for rank, category in enumerate(OPERATIONAL_CATEGORIES, start=1)
    ]
    decisions.append(_blocked_missing_data_decision(evidence_blockers))
    recommendation_policy_value = recommendation_policy()
    recommendations = GenerateRecommendationsOutput(
        recommendation_rule_policy_version=recommendation_policy_value.policy_version,
        recommendation_rule_policy_config_hash=recommendation_policy_value.policy_config_hash,
        rule_catalog_version=recommendation_policy_value.rule_catalog_version,
        rule_catalog_hash=recommendation_policy_value.rule_catalog_hash,
        decisions=decisions,
        agent_recommendations_hash="0" * 64,
        blockers=canonical_blockers(
            evidence_blockers
            + [blocker for decision in decisions for blocker in decision.blocker_dependencies]
        ),
    )
    recommendations = recommendations.model_copy(
        update={
            "agent_recommendations_hash": sha256_payload(
                recommendations.model_dump(mode="python", exclude={"agent_recommendations_hash"})
            )
        }
    )
    return explanation, recommendations


def build_slice_c_outputs(
    source: SliceCSourcePayload | Mapping[str, Any],
) -> tuple[ExplainForecastOutput, GenerateRecommendationsOutput]:
    """Build sibling outputs from the same immutable Slice B payload."""

    try:
        validated = _validated_source(source)
    except ValidationError as exc:
        return _invalid_source_outputs(exc)
    return build_explanation(validated), build_recommendations(validated)


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
    "resolve_artifact_binding",
    "validate_citation",
]
