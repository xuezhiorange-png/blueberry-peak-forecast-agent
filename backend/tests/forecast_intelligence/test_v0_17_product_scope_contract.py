"""Offline product-scope contracts only; no business engine or UI execution."""

import ast
import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCOPE_PATH = "docs/v0-17/evidence/v0.17.0-version-plan-and-product-scope-freeze-r1.json"
DOC_PATH = "docs/v0-17/v0.17.0-version-plan-and-product-scope-freeze.md"
TEST_PATH = "backend/tests/forecast_intelligence/test_v0_17_product_scope_contract.py"
STAGES = [
    "PRODUCTIZATION_AND_DASHBOARD_SCOPE_FREEZE",
    "FORECAST_INTELLIGENCE_SERVICE_AND_READ_API",
    "DECISION_SUPPORT_API",
    "MCP_PRODUCTIZATION",
    "DASHBOARD_UX_AND_DESIGN_SYSTEM_FREEZE",
    "DASHBOARD_IMPLEMENTATION",
    "CROSS_SURFACE_E2E_PRODUCT_ACCEPTANCE",
]
PAGES = ["OVERVIEW", "FORECAST", "ATTRIBUTION", "CAPACITY_SIMULATOR", "QUALITY"]
CAPABILITIES = [
    "GET_FORECAST_OVERVIEW",
    "GET_FORECAST_CURVE",
    "GET_HIERARCHICAL_FORECAST",
    "GET_FORECAST_UNCERTAINTY",
    "GET_FORECAST_ATTRIBUTION",
    "GET_FORECAST_QUALITY",
    "SIMULATE_CAPACITY",
    "COMPARE_CAPACITY_SCENARIOS",
]
POLICY_HASHES = {
    "S2": "f35f2700011f440569c9a0140dc9deb482281d60190e8a601b5a503c79013efd",
    "S3": "950d7d4885c4a96b43bba5ad6b586ee7a424ae86482618a8be22ed272039a422",
    "S4": "6dfe2c1ac684844af636d936b5797d301e80f015c9e3dd880a102127a169ac1c",
    "S5": "740c0a48506b524ea822b88ad9c5b3443cf3356969026e02cff4a6e1a3c446b7",
    "S6": "c1712c6596a813816eefbcb8d51c7088304549cfcc1899a637dff1b150be6463",
}


def scope():
    return json.loads((ROOT / SCOPE_PATH).read_bytes())


def test_identity_fresh_baseline_and_new_roadmap_authority():
    data = scope()
    assert data["TASK_ID"] == "V0_17_S0_PRODUCTIZATION_AND_DASHBOARD_SCOPE_FREEZE_R1"
    assert data["VERSION"] == "0.17.0"
    assert data["VERSION_NAME"] == "FORECAST_INTELLIGENCE_PRODUCTIZATION_AND_DASHBOARD"
    assert data["VERSION_NAME_CN"] == "蓝莓预测智能产品化与决策看板版"
    assert data["RELEASE_CLASS"] == "PRODUCTIZATION_AND_ENGINEERING_VERSION"
    assert data["BASE_MAIN_SHA"] == "2eb88a198fa2247ce813f8dac7bf7b41b8fdee32"
    assert data["LATEST_FORMAL_RELEASE"] == "v0.16.0"
    assert (
        data["PRIMARY_GOAL"]
        == "PRODUCTIZE_EXISTING_V0_16_FORECAST_INTELLIGENCE_AND_DECISION_SUPPORT"
    )
    assert data["V0_17_IS_PRODUCTIZATION_VERSION"] is True
    assert data["HISTORICAL_RECOMMENDATION_REWRITTEN"] is False
    assert data["ROADMAP_AUTHORITY"] == "OWNER_V0_17_S0_EXPLICIT_PRODUCTIZATION_AUTHORIZATION"
    audit = data["BASELINE_AUDIT"]
    assert audit["RELEASE_TAG_TARGET_SHA"] == data["BASE_MAIN_SHA"]
    assert audit["RELEASE_DRAFT"] is audit["RELEASE_PRERELEASE"] is False
    assert audit["PREEXISTING_V0_17_BRANCH_COUNT"] == audit["PREEXISTING_V0_17_PR_COUNT"] == 0
    assert audit["WORKTREE_CLEAN"] is True


def test_stage_sequence_and_capability_boundaries():
    data = scope()
    assert data["STAGE_ORDER"] == ["S0", "S1", "S2", "S3", "S4", "S5", "S6", "VERSION_CLOSEOUT"]
    assert list(data["STAGES"]) == [f"S{i}" for i in range(7)]
    for i, name in enumerate(STAGES):
        assert data["STAGES"][f"S{i}"]["TASK"] == name
    assert data["STAGES"]["S1"]["READ_CAPABILITIES"] == CAPABILITIES[:6]
    assert data["STAGES"]["S1"]["SCENARIO_WRITES"] is False
    assert data["STAGES"]["S2"]["NO_PERSISTENT_BUSINESS_ACTION"] is True
    assert data["STAGES"]["S2"]["NO_AUTOMATIC_EXECUTION"] is True
    assert data["STAGES"]["S3"]["REUSE_S1_S2_SERVICE"] is True
    assert data["STAGES"]["S4"]["FULL_PRODUCTION_UI_IMPLEMENTATION"] is False
    assert data["STAGES"]["S5"]["PAGES"] == PAGES
    assert data["STAGES"]["S6"]["CROSS_SURFACE_PARITY_REQUIRED"] is True


def test_users_business_information_flow_and_exact_navigation():
    data = scope()
    assert data["PRIMARY_USERS"] == [
        "MANAGEMENT_AND_OPERATIONS",
        "FORECAST_AND_PROCESS_ENGINEERING",
        "AI_ASSISTANT_CONSUMER",
    ]
    assert data["PRODUCT_INFORMATION_FLOW"] == ["FORECAST", "RISK", "WHY", "WHAT_IF"]
    assert data["TOP_LEVEL_PAGES"] == PAGES
    assert data["TOP_LEVEL_PAGE_LABELS"] == ["总览", "预测", "影响因素", "产能模拟", "预测质量"]
    assert data["TOP_LEVEL_PAGE_COUNT"] == 5
    assert data["BUSINESS_FIRST"] is True
    assert data["NON_TECHNICAL_READABLE"] is True
    assert data["ADVANCED_DETAILS_AVAILABLE_SECONDARY"] is True
    assert set(data["FORBIDDEN_TOP_LEVEL_NAVIGATION"]) >= {
        "MODEL_MANAGEMENT",
        "ALGORITHM_MANAGEMENT",
        "SYSTEM_MANAGEMENT",
        "USER_MANAGEMENT",
        "DATA_MANAGEMENT",
        "MCP_MANAGEMENT",
        "API_MANAGEMENT",
        "LOG_CENTER",
        "ALERT_CENTER",
        "CONFIGURATION_CENTER",
    }


def test_hierarchy_and_overview_contract():
    data = scope()
    assert data["SUPPORTED_HIERARCHY"] == ["COMPANY", "REGION", "BASE"]
    assert data["FARM_HIERARCHY_ADMITTED"] is data["FACTORY_HIERARCHY_ADMITTED"] is False
    page = data["PAGES"]["OVERVIEW"]
    assert page["PRIMARY_KPIS"] == [
        "FORECAST_7D_TOTAL",
        "FORECAST_15D_TOTAL",
        "PEAK_DATE",
        "PEAK_DAILY_QUANTITY",
    ]
    assert page["MAX_PRIMARY_KPI_COUNT"] == 6
    assert page["CONTEXT"] == ["HIERARCHY_SELECTOR", "FORECAST_ORIGIN_OR_LATEST_RUN"]
    assert page["CURVE_SERIES"] == [
        "POINT_FORECAST",
        "UPPER_PLANNING_BOUND_80",
        "UPPER_PLANNING_BOUND_90",
    ]
    assert page["HIGH_LOAD_DATE_FIELDS"] == [
        "date",
        "forecast_quantity",
        "planning_bound",
        "relative_status",
    ]
    assert page["CONTRIBUTION_SOURCE"] == "SAME_AUTHORITATIVE_FORECAST_CURVE_AND_V0_16_S1_HIERARCHY"
    assert page["PRODUCTION_ALARM_SEMANTICS_ALLOWED"] is False
    assert data["PAGES"]["FORECAST"]["HORIZONS"] == ["H1", "H3", "H7", "H15"]
    assert data["PAGES"]["FORECAST"]["DAILY_TABLE"] == [
        "date",
        "point_forecast",
        "upper_planning_bound_80",
        "upper_planning_bound_90",
    ]


def test_point_and_bound_semantics_and_missing_authority():
    semantic = scope()["PRODUCT_SEMANTICS"]
    assert semantic["POINT_FORECAST_IS_PROVEN_P50"] is False
    assert semantic["UPPER_PLANNING_BOUND_IS_QUANTILE"] is False
    assert semantic["FORMAL_QUANTILE_UI_ALIASES_ALLOWED"] is False
    assert semantic["FORBIDDEN_FORMAL_UI_LABELS"] == ["P50", "P80", "P90"]
    assert semantic["BOUND_TOOLTIP_REQUIREMENTS"] == [
        "POINT_NOT_PROVEN_P50",
        "BOUND_NOT_PROVEN_QUANTILE",
        "HISTORICAL_COVERAGE_UNDER_NOMINAL",
        "NO_FUTURE_COVERAGE_GUARANTEE",
    ]
    availability = scope()["AUTHORITY_AVAILABILITY"]
    assert availability["REGION_COMPANY_INTERVAL_CALIBRATION_ESTABLISHED"] is False
    assert availability["SUM_BASE_BOUNDS_FOR_AGGREGATE_COVERAGE_ALLOWED"] is False
    assert availability["MISSING_BOUND_FALLBACK_ALLOWED"] is False
    assert availability["ATTRIBUTION_FOR_UNBOUND_MODEL_ALLOWED"] is False
    assert availability["NO_AUTHORITY_STATUS"] == "NOT_AVAILABLE"
    assert availability["MISMATCH_STATUS"] == "AUTHORITY_MISMATCH"


def test_attribution_is_model_contribution_not_causality():
    page = scope()["PAGES"]["ATTRIBUTION"]
    assert page["TITLE"] == "影响因素"
    assert page["MODEL_ATTRIBUTION_ONLY"] is True
    assert page["ATTRIBUTION_IS_CAUSAL"] is False
    assert page["GROUPS"] == ["HARVEST_STATE", "BASE10", "INDIVIDUAL_TERMS"]
    assert page["ADVANCED_DETAILS"] == [
        "INTERCEPT",
        "RAW_CONTRIBUTION",
        "CLIP_ADJUSTMENT",
        "SERIALIZATION_ADJUSTMENT",
    ]
    assert page["RECOMMENDED_COPY"] == "模型中对本次预测贡献较大"
    assert page["FORBIDDEN_CAUSAL_COPY"] == ["导致", "原因就是", "造成产量变化"]
    assert page["RAW_MODEL_PARAMETERS_PUBLIC"] is False


def test_capacity_scenarios_reuse_frozen_mathematics_and_cost_semantics():
    page = scope()["PAGES"]["CAPACITY_SIMULATOR"]
    assert page["PLANNING_LEVELS"] == [
        "POINT",
        "UPPER_PLANNING_BOUND_80",
        "UPPER_PLANNING_BOUND_90",
    ]
    assert page["CAPACITY_MODES"] == ["DIRECT", "WORKFORCE_DERIVED"]
    assert page["WORKFORCE_INPUTS"] == ["workforce_count", "productivity_kg_per_person_day"]
    assert page["HIDDEN_PRODUCTIVITY_DEFAULT_ALLOWED"] is False
    assert page["BUFFER_SEMANTICS"] == "SAME_DAY_ADDITIVE_HANDLING_CAPACITY"
    assert page["INITIAL_BACKLOG_KG"] == "0"
    assert page["RANKING_LABEL"] == "条件情景排序"
    assert page["USER_EXPLICIT_SCENARIOS_ONLY"] is True
    assert page["COMPARISON_AUTHORITY"] == [
        "SAME_FORECAST",
        "SAME_HIERARCHY",
        "SAME_PLANNING_LEVEL",
        "SAME_DATE_SET",
        "SAME_COST_CONTRACT",
    ]
    assert page["UTILIZATION_EXACT_AUTHORITY"] == "NUMERATOR_DENOMINATOR_PAIR"
    assert page["ROUNDED_UTILIZATION_USED_FOR_RANKING"] is False
    assert set(page["OUTPUTS"]) >= {
        "OVERLOAD_DAY_COUNT",
        "CUMULATIVE_SHORTFALL_KG",
        "MAX_BACKLOG_KG",
        "ENDING_BACKLOG_KG",
        "AGGREGATE_CAPACITY_UTILIZATION",
        "BUSINESS_LOSS",
    }
    assert page["CHARTS"] == ["DEMAND_VS_CAPACITY", "BACKLOG"]
    cost = scope()["BUSINESS_LOSS_PRESENTATION"]
    assert cost["SHOW_COST_AUTHORITY"] is True
    assert cost["SYNTHETIC_BADGE"] == "SYNTHETIC_COST"
    assert cost["SYNTHETIC_LOSS_UNIT"] == "SYNTHETIC_LOSS_UNIT"
    assert cost["CANONICAL_COMPANY_COST_ESTABLISHED"] is cost["REAL_ROI_VALIDATED"] is False
    assert cost["SYNTHETIC_CURRENCY_DISPLAY_ALLOWED"] is False


def test_quality_preserves_negative_evidence_and_current_actual_empty_state():
    data = scope()
    page = data["PAGES"]["QUALITY"]
    assert page["DEFAULT_MODE"] == "HISTORICAL_VALIDATION"
    assert page["EVIDENCE_LABEL"] == "RETROSPECTIVE_OBSERVATION"
    assert page["HORIZONS"] == ["H1", "H3", "H7", "H15"]
    assert page["METRICS"] == ["WAPE", "MAE", "Bias", "Cumulative WAPE", "INTERVAL_COVERAGE"]
    assert page["SHOW_UNDER_NOMINAL_COVERAGE"] is True
    assert page["HISTORICAL_IS_CURRENT_PRODUCTION_ACCURACY"] is False
    assert page["CURRENT_ACTUAL_EMPTY_STATE"] == "当前产季暂无可用于正式评分的实际采收数据。"
    coverage = json.loads((ROOT / page["COVERAGE_EVIDENCE_PATH"]).read_bytes())
    assert page["FROZEN_COVERAGE_OBSERVATIONS"] == coverage
    for horizon in coverage.values():
        assert all(row["observation"] == "UNDER_NOMINAL" for row in horizon.values())
    for name in (
        "AVAILABLE",
        "REQUIRED",
        "READ_AUTHORIZED",
        "IMPORT_AUTHORIZED",
        "SCORING_AUTHORIZED",
    ):
        assert data[f"CURRENT_SEASON_ACTUAL_{name}"] is False


def test_single_service_and_cross_surface_authority_parity():
    data = scope()
    assert data["ONE_SERVICE_LAYER"] is True
    assert data["ARCHITECTURE"]["FLOW"] == [
        "V0_16_FROZEN_ENGINES",
        "FORECAST_INTELLIGENCE_SERVICE_LAYER",
        "HTTP_API_MCP_DASHBOARD",
    ]
    assert data["API_CAPABILITIES"] == CAPABILITIES
    assert data["MCP_CAPABILITIES"] == [name.lower() for name in CAPABILITIES]
    assert data["API_URL_PATHS_FROZEN_IN_S0"] is False
    assert data["ARCHITECTURE"]["DUPLICATED_SURFACE_FORMULAS_ALLOWED"] is False
    parity = data["CROSS_SURFACE_PARITY"]
    assert parity["SURFACES"] == ["DASHBOARD", "HTTP_API", "MCP"]
    assert parity["SAME_INPUTS"] == [
        "FORECAST_RUN",
        "ENTITY",
        "PLANNING_LEVEL",
        "SCENARIO_INPUTS",
        "AUTHORITY",
    ]
    assert parity["SAME_OUTPUTS"] == ["AUTHORITATIVE_QUANTITY", "RESULT_HASH", "SEMANTIC_STATUS"]
    assert parity["PRESENTATION_FORMATTING_DIFFERENCE_ALLOWED"] is True
    assert parity["NUMERIC_RESULT_DIFFERENCE_ALLOWED"] is False


def test_frontend_direction_states_accessibility_and_design_stage_separation():
    data = scope()
    frontend = data["FRONTEND_DIRECTION"]
    assert frontend["STACK"] == ["React", "Vite", "TypeScript"]
    assert frontend["EXISTING_PAGES"] == ["ForecastPage", "QualityPage"]
    assert frontend["DESKTOP_PRIMARY"] is frontend["MOBILE_RESPONSIVE"] is True
    assert frontend["MOBILE_BASIC_SCENARIO_INPUT_REQUIRED"] is True
    assert frontend["DESIGN_SYSTEM_FREEZE_STAGE"] == "S4"
    assert frontend["S0_VISUAL_DESIGN_EXECUTED"] is False
    assert data["CORE_PAGE_STATES"] == [
        "LOADING",
        "READY",
        "EMPTY",
        "PARTIAL",
        "NOT_AVAILABLE",
        "ERROR",
        "AUTHORITY_MISMATCH",
        "NO_CURRENT_ACTUAL",
    ]
    assert data["ACCESSIBILITY_REQUIREMENTS"] == [
        "KEYBOARD_NAVIGATION",
        "SEMANTIC_HTML",
        "VISIBLE_FOCUS",
        "CONTRAST",
        "CHART_TEXT_ALTERNATIVE_OR_DATA_TABLE",
    ]


@pytest.mark.parametrize("stage", range(1, 7))
def test_no_follow_on_implementation_authorized(stage):
    data = scope()
    assert data[f"S{stage}_AUTHORIZED"] is False
    assert data["STAGES"][f"S{stage}"]["IMPLEMENTATION_AUTHORIZED"] is False


@pytest.mark.parametrize(
    "field",
    [
        "V0_17_IS_MODEL_DEVELOPMENT_VERSION",
        "V0_17_IS_PROSPECTIVE_VALIDATION_VERSION",
        "MODEL_DEVELOPMENT",
        "MODEL_TRAINING",
        "MODEL_REFIT",
        "MODEL_TUNING",
        "VISION_IN_SCOPE",
        "PROSPECTIVE_VALIDATION_IN_SCOPE",
        "PROSPECTIVE_ACCURACY_VALIDATED",
        "PRODUCTION_USE_APPROVED",
        "REAL_ROI_VALIDATED",
        "READY_AUTHORIZED",
        "MERGE_AUTHORIZED",
        "VERSION_CLOSEOUT_AUTHORIZED",
        "TAG_AUTHORIZED",
        "RELEASE_AUTHORIZED",
        "V0_17_VERSION_COMPLETE",
    ],
)
def test_non_goals_and_governance_closed(field):
    assert scope()[field] is False


def test_out_of_scope_and_future_recommendations_are_not_authorization():
    data = scope()
    assert set(data["OUT_OF_SCOPE"]) == {
        "VISION",
        "BLUEBERRY_IMAGE_MODEL",
        "WEATHER_RESEARCH",
        "NEW_MODEL",
        "MODEL_TRAINING",
        "MODEL_REFIT",
        "MODEL_TUNING",
        "NEW_HARVEST_STATE",
        "PROSPECTIVE_VALIDATION",
        "CURRENT_SEASON_SCORING",
        "TRUE_PRODUCTION_ALERTING",
        "REAL_ROI",
        "CANONICAL_COMPANY_COST",
        "WORKFORCE_SCHEDULING",
        "CAPACITY_OPTIMIZATION",
        "MULTI_FACTORY_ROUTING",
        "AUTOMATIC_EXECUTION",
        "USER_MANAGEMENT",
        "COMPLEX_ADMIN",
        "MODEL_MANAGEMENT_UI",
        "DATABASE_ADMIN_UI",
    }
    assert data["S0_AUTHORIZED"] is True
    assert data["S0_FORMAL_COMPLETE"] is False
    assert data["STOP"] is True
    for future in data["FUTURE_CANDIDATES"].values():
        assert future["AUTHORIZED"] is future["STARTED"] is False
    assert data["V0_18_AUTHORIZED"] is data["V0_18_STARTED"] is False


@pytest.mark.parametrize("stage", POLICY_HASHES)
def test_upstream_math_policy_bytes_and_semantic_hashes_unchanged(stage):
    pin = scope()["FROZEN_V0_16_POLICIES"][stage]
    assert pin["POLICY_HASH"] == POLICY_HASHES[stage]
    payload = json.loads((ROOT / pin["PATH"]).read_bytes())
    assert payload["policy_hash"] == POLICY_HASHES[stage]
    raw = (
        json.dumps(payload["policy"], sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        + "\n"
    ).encode()
    assert hashlib.sha256(raw).hexdigest() == POLICY_HASHES[stage]
    assert scope()[f"V0_16_{pin['FROZEN_FLAG']}_POLICY_FROZEN"] is True


def test_public_source_binding_canonical_scope_and_three_file_allowlist():
    data = scope()
    for name, expected in data["SOURCE_EVIDENCE_SHA256"].items():
        path = Path(name)
        assert not path.is_absolute() and ".." not in path.parts
        assert path.parts[0] in {"docs", "frontend"}
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected
    assert (ROOT / SCOPE_PATH).read_bytes() == (
        json.dumps(data, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
    ).encode()
    assert data["CHANGED_FILE_ALLOWLIST"] == [DOC_PATH, SCOPE_PATH, TEST_PATH]
    assert data["S0_ALLOWED_OUTPUTS"] == [
        "DOCS",
        "MACHINE_READABLE_SCOPE_EVIDENCE",
        "CONTRACT_TESTS",
    ]
    assert data["S0_PRIVATE_DATA_READ"] is False
    assert data["V0_16_FORECAST_MATH_FROZEN"] is True
    assert data["PRODUCTIZED_EQUALS_PRODUCTION_VALIDATED"] is False
    tree = ast.parse(Path(__file__).read_text())
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module)
    assert imports == {"ast", "hashlib", "json", "pathlib", "pytest"}


def test_s1_existing_hierarchy_contract_is_not_redefined():
    evidence = json.loads(
        (
            ROOT / "docs/v0-16/evidence/v0.16-s1-hierarchical-forecast-reconciliation-r1.json"
        ).read_bytes()
    )
    assert evidence["hierarchy_contract_version"] == "V0_16_HIERARCHY_R1"
    assert evidence["reconciliation_policy_version"] == "HIERARCHICAL_BOTTOM_UP_EXACT_SUM_R1"
    assert evidence["MISSING_CHILD_AS_ZERO"] is False
    assert scope()["V0_16_HIERARCHY_POLICY_FROZEN"] is True


def test_s0_has_no_product_implementation_or_private_payload():
    data = scope()
    for field in (
        "API_IMPLEMENTED",
        "MCP_IMPLEMENTED",
        "FRONTEND_IMPLEMENTED",
        "DASHBOARD_IMPLEMENTED",
        "DESIGN_SYSTEM_IMPLEMENTED",
        "DB_MIGRATION_CREATED",
        "DEPLOYMENT_EXECUTED",
    ):
        assert data[f"S0_{field}"] is False
    for field in ("READ", "IMPORT", "SCORING"):
        assert data[f"CURRENT_SEASON_ACTUAL_{field}"] is False
    raw = (ROOT / SCOPE_PATH).read_text() + (ROOT / DOC_PATH).read_text()
    for forbidden in (
        "/Users/",
        "/private/tmp/",
        "postgresql://",
        "postgresql+asyncpg://",
        "ghp_",
        "sk-proj-",
        '"base_id":',
        '"row_key":',
        '"daily_actual":',
        '"daily_forecast":',
    ):
        assert forbidden not in raw
    assert data["SOURCE_EVIDENCE_SHA256"]
    assert all(page in data["PAGES"] for page in PAGES)
