from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from backend.app.agent.enums import BlockerCode
from backend.app.agent.schemas import (
    Blocker,
    ConditionEvaluation,
    GenerateRecommendationsOutput,
    NonAction,
    RecommendationDecision,
)

CATEGORIES = (
    "SUSTAINED_PROCESSING_CAPACITY",
    "RECEIVING_PEAK_CAPACITY",
    "SHIFT_STAFFING",
    "SPRING_FESTIVAL_STAFFING",
    "VARIETY_STAGGER",
    "CROSS_PLANT_DISPATCH",
    "MISSING_DATA_IMPACT",
)


def _decision(
    category: str,
    *,
    status: str = "BLOCKED",
    reason: str = "REQUIRED_THRESHOLD_MISSING",
    advisory_text: str | None = None,
) -> RecommendationDecision:
    blocker = Blocker(
        code=BlockerCode.RECOMMENDATION_THRESHOLD_MISSING,
        message="C2 source package is unavailable",
        details={"category": category},
        retry_hint="CONTACT_OPS",
    )
    return RecommendationDecision(
        category=category,
        kind="DATA_QUALITY" if category == "MISSING_DATA_IMPACT" else "OPERATIONAL",
        status=status,
        reason_code=reason,
        reason_details=None,
        priority_rank=CATEGORIES.index(category) + 1,
        rule_id=f"rule-{category.lower()}",
        template_id=f"template-{category.lower()}",
        advisory_text=advisory_text,
        applicability_conditions=[],
        evidence=[],
        risk_codes=[],
        confidence=None,
        confidence_boundary=None,
        blocker_dependencies=[blocker] if status == "BLOCKED" else [],
        non_action=NonAction(
            category_specific_code=f"NO_AUTOMATIC_{category}_ACTION",
        ),
    )


def _output(decisions: list[RecommendationDecision]) -> GenerateRecommendationsOutput:
    return GenerateRecommendationsOutput(
        recommendation_rule_policy_version="recommendation-rule-policy-v1",
        recommendation_rule_policy_config_hash="a" * 64,
        rule_catalog_version="recommendation-rule-catalog-v1",
        rule_catalog_hash="b" * 64,
        decisions=decisions,
        agent_recommendations_hash="c" * 64,
        blockers=[],
    )


def test_recommendation_output_requires_exact_category_order() -> None:
    decisions = [_decision(category) for category in CATEGORIES]
    assert [item.category for item in _output(decisions).decisions] == list(CATEGORIES)
    with pytest.raises(ValidationError):
        _output(list(reversed(decisions)))
    with pytest.raises(ValidationError):
        _output(decisions[:-1])


@pytest.mark.parametrize(
    ("status", "reason", "advisory"),
    [
        ("APPLICABLE", "RULE_APPLICABLE", "Review the cited missing evidence."),
        ("NOT_APPLICABLE", "CONDITIONS_NOT_MET", None),
        ("NOT_APPLICABLE", "OUTSIDE_AUTHORIZED_SCOPE", None),
        ("BLOCKED", "REQUIRED_THRESHOLD_MISSING", None),
        ("BLOCKED", "REQUIRED_EVIDENCE_MISSING", None),
        ("BLOCKED", "UPSTREAM_BLOCKED", None),
        ("BLOCKED", "POLICY_UNAVAILABLE", None),
    ],
)
def test_recommendation_status_reason_contract(
    status: str, reason: str, advisory: str | None
) -> None:
    decision = _decision(
        "MISSING_DATA_IMPACT", status=status, reason=reason, advisory_text=advisory
    )
    assert decision.reason_code == reason


@pytest.mark.parametrize(
    ("status", "reason", "advisory"),
    [
        ("APPLICABLE", "CONDITIONS_NOT_MET", "x"),
        ("NOT_APPLICABLE", "RULE_APPLICABLE", None),
        ("BLOCKED", "RULE_APPLICABLE", None),
        ("BLOCKED", "REQUIRED_THRESHOLD_MISSING", "x"),
    ],
)
def test_recommendation_rejects_invalid_status_reason_combinations(
    status: str, reason: str, advisory: str | None
) -> None:
    with pytest.raises(ValidationError):
        _decision("MISSING_DATA_IMPACT", status=status, reason=reason, advisory_text=advisory)


def test_slice_c_models_are_strict_and_frozen() -> None:
    with pytest.raises(ValidationError):
        ConditionEvaluation(
            field_path="/parameters/0/p50",
            operator="EXISTS",
            observed_value="1",
            threshold_value=None,
            unit=None,
            result="TRUE",
            citation=None,
            unexpected=True,
        )
    decision = _decision("SUSTAINED_PROCESSING_CAPACITY")
    with pytest.raises(ValidationError):
        decision.priority_rank = 99  # type: ignore[misc]


def test_hash_fields_reject_non_lowercase_sha256() -> None:
    decisions = [_decision(category) for category in CATEGORIES]
    payload: dict[str, Any] = {
        "recommendation_rule_policy_version": "recommendation-rule-policy-v1",
        "recommendation_rule_policy_config_hash": "A" * 64,
        "rule_catalog_version": "recommendation-rule-catalog-v1",
        "rule_catalog_hash": "b" * 64,
        "decisions": decisions,
        "agent_recommendations_hash": "c" * 64,
        "blockers": [],
    }
    with pytest.raises(ValidationError):
        GenerateRecommendationsOutput.model_validate(payload)


def test_slice_c_blocker_taxonomy_is_frozen() -> None:
    expected = {
        "EXPLANATION_POLICY_MISSING",
        "EXPLANATION_TEMPLATE_MISSING",
        "RECOMMENDATION_POLICY_MISSING",
        "RECOMMENDATION_RULE_MISSING",
        "RECOMMENDATION_THRESHOLD_MISSING",
        "REQUIRED_CITATION_MISSING",
        "REQUIRED_AUTHORITY_MISSING",
        "REQUIRED_PROVENANCE_MISSING",
        "EVIDENCE_FIELD_PATH_INVALID",
        "EVIDENCE_HASH_MISMATCH",
    }
    assert expected <= {item.value for item in BlockerCode}


def test_slice_c_package_has_no_database_or_external_client_imports() -> None:
    package = Path(__file__).parents[2] / "app" / "agent" / "slice_c"
    forbidden = {"sqlalchemy", "requests", "httpx", "openai", "anthropic", "smtplib"}
    imported: set[str] = set()
    for path in package.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", 1)[0])
    assert imported.isdisjoint(forbidden)
