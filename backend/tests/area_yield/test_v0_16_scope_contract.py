"""Offline scope checks only: no model, database, weather or actual-data imports."""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCOPE = ROOT / "docs/v0-16/evidence/v0.16.0-version-plan-and-scope-freeze-r1.json"
STAGES = [
    "HIERARCHICAL_FORECAST_RECONCILIATION",
    "UNCERTAINTY_AND_CONFORMAL_CALIBRATION",
    "FORECAST_ATTRIBUTION",
    "FORECASTOPS_MONITORING",
    "BUSINESS_LOSS_CONTRACT",
    "WHAT_IF_DECISION_SIMULATOR",
]


def scope() -> dict:
    return json.loads(SCOPE.read_bytes())


def test_version_identity_and_order() -> None:
    data = scope()
    assert data["VERSION"] == "0.16.0"
    assert data["VERSION_NAME"] == "FORECAST_INTELLIGENCE_AND_DECISION_SUPPORT_FOUNDATION"
    assert data["VERSION_NAME_CN"] == "预测智能与决策支持基础版"
    assert data["RELEASE_CLASS"] == "RESEARCH_AND_ENGINEERING_VERSION"
    assert data["STAGE_ORDER"] == ["S0", "S1", "S2", "S3", "S4", "S5", "S6", "VERSION_CLOSEOUT"]
    for index, name in enumerate(STAGES, 1):
        assert data["STAGES"][f"S{index}"]["TASK_ID"] == f"V0_16_S{index}_{name}"
    assert [data["STAGES"][f"S{i}"]["OWNER_ORIGINAL_ITEM"] for i in range(1, 7)] == [
        8,
        1,
        6,
        7,
        9,
        3,
    ]


def test_hierarchy_exact_sum_missing_and_peaks() -> None:
    policy = scope()["STAGES"]["S1"]
    assert policy["HIERARCHY"] == ["BASE", "REGION", "COMPANY"]
    assert policy["FORECAST_ATOMIC_ENTITY_TYPE"] == "BASE"
    assert policy["FARM_HIERARCHY_ADMITTED"] is False
    assert policy["FACTORY_HIERARCHY_ADMITTED"] is False
    assert policy["RECONCILIATION_METHOD"] == "BOTTOM_UP_EXACT_SUM"
    assert policy["MISSING_CHILD_AS_ZERO"] is False
    assert policy["INCOMPLETE_STATUS"] == "INCOMPLETE_CHILD_COVERAGE"
    assert policy["INCOMPLETE_OFFICIAL_AGGREGATE_KG"] is None
    assert policy["SUM_CHILD_PEAKS_ALLOWED"] is False
    assert policy["PEAK_SOURCE"] == "AGGREGATED_DAILY_CURVE"
    assert policy["TIE_BREAK"] == "EARLIEST_DATE"
    assert policy["SOURCE_FORECAST_MUTATION_ALLOWED"] is False


def test_intervals_are_not_unproven_quantiles() -> None:
    policy = scope()["STAGES"]["S2"]
    assert policy["PREFERRED_METHOD"] == "CONFORMAL_PREDICTION"
    assert policy["POINT_MODEL_FROZEN"] is True
    assert policy["RETROSPECTIVE_INTERVAL_CALIBRATION"] is True
    assert policy["PROSPECTIVE_INTERVAL_COVERAGE_VALIDATED"] is False
    assert policy["POINT_FORECAST_IS_PROVEN_P50"] is False
    assert policy["INTERVAL_COVERAGE_LEVELS"] == [80, 90]
    assert policy["INTERVAL_IS_AUTOMATIC_QUANTILE"] is False


def test_attribution_is_not_causal() -> None:
    policy = scope()["STAGES"]["S3"]
    assert policy["ATTRIBUTION_IS_CAUSAL_EXPLANATION"] is False
    assert policy["PREFERRED_METHOD"] == "EXACT_LINEAR_CONTRIBUTION"
    assert policy["NEW_TREE_TRAINING_AUTHORIZED"] is False
    assert policy["RECONSTRUCTION_TOLERANCE_MUST_BE_FROZEN_BEFORE_IMPLEMENTATION"] is True
    assert policy["ABSENT_HARVEST_STATE_GROUP_FABRICATION_ALLOWED"] is False


def test_forecastops_is_not_live_scoring_authorization() -> None:
    policy = scope()["STAGES"]["S4"]
    assert policy["HORIZONS"] == ["H1", "H3", "H7", "H15"]
    assert policy["CURRENT_2026_2027_ACTUAL_REQUIRED"] is False
    assert policy["CURRENT_2026_2027_ACTUAL_READ"] is False
    assert policy["MISSING_ACTUAL_AS_ZERO"] is False
    assert policy["PARTIAL_AS_COMPLETE"] is False
    assert policy["PRODUCTION_ALERT_THRESHOLDS_ESTABLISHED"] is False


def test_business_loss_and_scenarios_are_not_real_roi_or_execution() -> None:
    loss = scope()["STAGES"]["S5"]
    assert loss["COST_AUTHORITY"] == ["OWNER_BUSINESS_SUPPLIED", "EXPLICIT_SYNTHETIC_SCENARIO"]
    assert loss["CANONICAL_COMPANY_COST_ESTABLISHED"] is False
    assert loss["REAL_ROI_VALIDATED"] is False
    simulator = scope()["STAGES"]["S6"]
    assert simulator["WHAT_IF_IS_SCENARIO_SIMULATION"] is True
    assert simulator["WHAT_IF_IS_NEW_FORECAST_MODEL"] is False
    assert simulator["HIDDEN_DEFAULT_PRODUCTIVITY_ALLOWED"] is False
    assert simulator["AUTOMATIC_EXECUTION_ALLOWED"] is False


@pytest.mark.parametrize("stage", range(1, 7))
def test_all_implementation_gates_remain_closed(stage: int) -> None:
    assert scope()[f"S{stage}_IMPLEMENTATION_AUTHORIZED"] is False


@pytest.mark.parametrize(
    "key",
    [
        "CURRENT_SEASON_ACTUAL_AVAILABLE",
        "2026_2027_ACTUAL_READ_AUTHORIZED",
        "2026_2027_ACTUAL_IMPORT_AUTHORIZED",
        "2026_2027_ACTUAL_SCORING_AUTHORIZED",
        "V0_17_AUTHORIZED",
        "V0_17_STARTED",
        "READY_AUTHORIZED",
        "MERGE_AUTHORIZED",
        "TAG_AUTHORIZED",
        "RELEASE_AUTHORIZED",
        "MODEL_TRAINING_AUTHORIZED",
        "MODEL_REFIT_AUTHORIZED",
        "PROSPECTIVE_SCORING_AUTHORIZED",
        "V0_16_VERSION_COMPLETE",
    ],
)
def test_authorization_and_completion_are_not_inferred(key: str) -> None:
    assert scope()[key] is False


def test_old_versions_and_preexisting_draft_are_immutable() -> None:
    data = scope()
    assert data["V0_14_UNCHANGED"] is True
    assert data["V0_15_UNCHANGED"] is True
    assert data["PREEXISTING_P1_DRAFT"] is True
    assert data["PREEXISTING_P1_PR"] == 690
    assert data["PREEXISTING_P1_HEAD"] == "5b5f01683e47c32e0cae45b791e9d0d41d8e66c2"
    assert data["PREEXISTING_P1_MODIFICATION_AUTHORIZED"] is False
    assert data["P1_ADMISSION_STATUS"] == "PENDING_VERSION_SCOPE_FREEZE"
    assert data["P1_NEXT_GATE"] == "S0_REVIEW_MERGE_THEN_FRESH_MAIN_AND_SEPARATE_AUTHORIZATION"
    assert data["V0_17_RECOMMENDED_DIRECTION"] == "HARVEST_STATE_PROSPECTIVE_SHADOW_VALIDATION"


def test_completion_requires_all_independent_gates() -> None:
    data = scope()
    assert data["VERSION_COMPLETE_REQUIRES_CURRENT_SEASON_ACTUAL"] is False
    assert len(data["VERSION_COMPLETE_CONDITIONS"]) == 16
    assert data["PROSPECTIVE_ACCURACY_VALIDATED"] is False
    assert data["PRODUCTION_USE_APPROVED"] is False
    assert data["REAL_ROI_VALIDATED"] is False


def test_contract_serialization_and_three_file_allowlist() -> None:
    data = scope()
    expected = (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    assert SCOPE.read_bytes() == expected
    assert data["CHANGED_FILE_ALLOWLIST"] == [
        "docs/v0-16/v0.16.0-version-plan-and-scope-freeze.md",
        "docs/v0-16/evidence/v0.16.0-version-plan-and-scope-freeze-r1.json",
        "backend/tests/area_yield/test_v0_16_scope_contract.py",
    ]
