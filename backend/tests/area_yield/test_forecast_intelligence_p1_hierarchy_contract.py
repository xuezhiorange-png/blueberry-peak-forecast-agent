import json
from pathlib import Path


CONTRACT = Path(
    "docs/forecast-intelligence/evidence/p1-hierarchical-forecast-contract-r1.json"
)


def load_contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_forecast_intelligence_p1_hierarchy_scope_is_frozen() -> None:
    c = load_contract()

    assert c["TASK_ID"] == "FORECAST_INTELLIGENCE_P1_HIERARCHICAL_FORECAST_CONTRACT_R1"
    assert c["FORECAST_ATOMIC_ENTITY_TYPE"] == "BASE"
    assert c["CURRENT_HIERARCHY_LEVELS"] == ["BASE", "REGION", "COMPANY"]

    assert c["FARM_HIERARCHY_ADMITTED"] is False
    assert c["FACTORY_HIERARCHY_ADMITTED"] is False
    assert c["FACTORY_ROUTING_IN_SCOPE"] is False
    assert c["HIERARCHY_EFFECTIVE_DATING_ESTABLISHED"] is False
    assert c["HISTORICAL_HIERARCHY_RECONSTRUCTION_AUTHORIZED"] is False


def test_forecast_intelligence_p1_is_bottom_up_only() -> None:
    c = load_contract()

    assert c["RECONCILIATION_METHOD"] == "BOTTOM_UP_EXACT_SUM"
    assert c["STATISTICAL_RECONCILIATION"] is False
    assert c["MINT"] is False
    assert c["TOP_DOWN"] is False
    assert c["MIDDLE_OUT"] is False
    assert c["PARENT_MODEL_FIT"] is False
    assert c["POINT_FORECAST_ONLY"] is True
    assert c["UNCERTAINTY_RECONCILIATION_IN_SCOPE"] is False


def test_forecast_intelligence_p1_never_turns_missing_children_into_zero() -> None:
    c = load_contract()

    assert c["MISSING_CHILD_AS_ZERO"] is False
    assert c["INCOMPLETE_STATUS"] == "INCOMPLETE_CHILD_COVERAGE"
    assert c["INCOMPLETE_OFFICIAL_AGGREGATE_IS_NULL"] is True


def test_forecast_intelligence_p1_preserves_forecast_immutability() -> None:
    c = load_contract()

    assert c["SAME_INPUTS_SAME_OUTPUT_REQUIRED"] is True
    assert c["SAME_INPUTS_SAME_RESULT_HASH_REQUIRED"] is True
    assert c["SOURCE_FORECAST_MUTATION_ALLOWED"] is False
    assert c["HISTORICAL_AGGREGATE_OVERWRITE_ALLOWED"] is False
    assert c["APPEND_ONLY_RUN_HISTORY_REQUIRED"] is True


def test_forecast_intelligence_p1_peaks_are_derived_from_aggregate_curve() -> None:
    c = load_contract()

    assert c["PEAKS_RECOMPUTED_FROM_AGGREGATE_DAILY_CURVE"] is True
    assert c["PEAK_TIE_BREAK"] == "EARLIEST_DATE"


def test_forecast_intelligence_future_work_remains_out_of_scope() -> None:
    c = load_contract()

    excluded = set(c["EXPLICIT_EXCLUSIONS"])
    assert {
        "UNCERTAINTY_INTERVALS",
        "CONFORMAL_CALIBRATION",
        "FORECAST_ATTRIBUTION",
        "FORECAST_SCORING",
        "MODEL_DRIFT",
        "BUSINESS_LOSS",
        "WHAT_IF_SIMULATOR",
        "V0_16_PROSPECTIVE_VALIDATION",
        "MODEL_RETRAINING",
        "MODEL_PROMOTION",
        "PRODUCTION_DEPLOYMENT",
    } <= excluded

    assert c["P1_CONTRACT_FROZEN"] is True
    assert c["P1_RUNTIME_IMPLEMENTED"] is False
    assert c["P2_STARTED"] is False
    assert c["P3_STARTED"] is False
    assert c["P4_STARTED"] is False
    assert c["P5_STARTED"] is False
    assert c["P6_STARTED"] is False
    assert c["V0_16_STARTED"] is False
    assert c["READY_AUTHORIZED"] is False
    assert c["MERGE_AUTHORIZED"] is False
