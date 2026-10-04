"""Public-only prospective protocol freeze; never capture or execute models."""

import ast
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCOPE = ROOT / "docs/v0-14/evidence/v0.14.0-version-plan-and-prospective-protocol-freeze-r1.json"
PLAN = ROOT / "docs/v0-14/v0.14.0-version-plan-and-prospective-protocol-freeze.md"
pytestmark = pytest.mark.contract


def contract() -> dict[str, Any]:
    return json.loads(SCOPE.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def validate(c: dict[str, Any]) -> None:
    """Test-only fail-closed acceptance oracle, not a production runner."""
    assert c["VERSION"] == "0.14.0"
    assert c["VERSION_NAME"] == "AS_ISSUED_WEATHER_SHADOW_ISSUANCE_AND_PROSPECTIVE_COHORT"
    assert c["VERSION_NAME_CN"] == "真实天气影子发报与前瞻队列版"
    assert c["RELEASE_CLASS"] == "PROSPECTIVE_RESEARCH_VERSION"
    assert c["BASE_SHA"] == "837bb5cf9674ca2f5bdbb2f082dc9092e86e9ca0"
    assert c["V0_13_VERSION_COMPLETE"] is True
    assert c["V0_13_VERSION_CLOSEOUT_COMPLETE"] is True
    assert c["V0_13_FEATURE_DEVELOPMENT_FROZEN"] is True
    assert c["CURRENT_SEASON_ACTUAL_REQUIRED_FOR_V0_14"] is False
    assert c["provider"]["REQUIRED_HORIZONS"] == [24, 72, 168]
    assert c["provider"]["OPTIONAL_HORIZONS"] == [360]
    assert c["H7_PROVIDER_SURFACE_PRESENT_BY_CONTRACT"] is True
    assert c["H15_PROVIDER_SURFACE_GUARANTEED"] is False
    assert c["ENDPOINT_SNAPSHOTS_FORM_COMPLETE_FUTURE_WEATHER_WINDOW"] is False
    assert c["FUTURE_WEATHER_FEATURE_SCHEMA_FROZEN"] is False
    assert c["FUTURE_WEATHER_FEATURE_COUNT"] is None
    assert c["FUTURE_WEATHER_FEATURES_R1"] is None
    assert c["CANDIDATE_COUNT"] == 1
    assert c["CANDIDATE_ID"] == "V0_14_W1_AS_ISSUED_WEATHER_PROSPECTIVE_CANDIDATE"
    assert c["COMPARATOR_ID"] == "V0_14_C0_BASE_ONLY_PROSPECTIVE_COMPARATOR"
    assert c["models"]["C0"]["features"] == ["BASE_FEATURES"]
    assert c["models"]["W1"]["features"] == ["BASE_FEATURES", "FUTURE_WEATHER_FEATURES_R1"]
    assert c["models"]["C0"]["future_weather"] is False
    assert c["models"]["W1"]["future_weather"] is True
    expected_algorithm = {
        "MODEL_FAMILY": "RIDGE_LEAST_SQUARES",
        "ALPHA": "10.000000",
        "INTERCEPT_UNPENALIZED": True,
        "NONNEGATIVE_OUTPUT_CLIP": True,
        "STANDARDIZATION": "TRAIN_ONLY_STANDARD_SCALER_POPULATION_STD",
        "ZERO_STD_POLICY": "SCALE_1",
        "SOLVER": "numpy.linalg.solve",
    }
    assert c["algorithm"] == expected_algorithm
    assert c["models"]["C0"]["algorithm_contract"] == "algorithm"
    assert c["models"]["W1"]["algorithm_contract"] == "algorithm"
    assert all(value is True for value in c["fair_comparison"].values())
    assert c["PRIMARY_EXPERIMENTAL_DIFFERENCE"] == "AS_ISSUED_FUTURE_WEATHER_INFORMATION"
    assert c["HISTORICAL_PROXY_IS_AS_ISSUED_FORECAST"] is False
    assert c["PROXY_TO_REAL_FORECAST_DOMAIN_SHIFT_EXISTS"] is True
    assert c["FINAL_TRAINING_COHORT_AUTHORITY"] == "TO_BE_AUDITED_AND_FROZEN_BEFORE_S2_FIT"
    assert c["WEATHER_CAPTURE_AUTHORITY_EQUALS_QUANTITY_FORECAST_SCOPE_AUTHORITY"] is False
    assert c["PREVIOUS_SEASON_AREA_AS_CURRENT_SEASON_FALLBACK"] is False
    assert c["WEATHER_CAPTURE_CAN_BEGIN_WITHOUT_CURRENT_SEASON_HARVEST"] is True
    assert c["FIRST_ISSUANCE_SCOPE_AUTHORIZED"] is False
    assert c["CURRENT_SCOPE_AUTHORITY_REVALIDATED"] is False
    assert c["scope_gate"]["missing_current_season_authority"] == {
        "WEATHER_CAPTURE_ALLOWED": True,
        "SHADOW_QUANTITY_ISSUANCE": "BLOCKED",
        "V0_14_VERSION_COMPLETE": False,
    }
    assert c["capture_contract"]["pit_order"] == [
        "issued_at",
        "fetched_at",
        "known_at",
        "forecast_created_at",
    ]
    assert c["capture_contract"]["ordering_operator"] == "<="
    assert c["capture_contract"]["ordering_violation"] == "FAIL_CLOSED"
    assert c["capture_contract"]["run_selection"] == (
        "SELECT_LATEST_COMPLETE_QUALIFIED_PROVIDER_RUN_AT_OR_BEFORE_FORECAST_CREATED_AT"
    )
    assert c["capture_contract"]["same_run_different_bytes"] == "CONFLICT_FAIL_CLOSED"
    assert c["capture_contract"]["qualified_run_unavailable"] == "WEATHER_CAPTURE_UNAVAILABLE"
    assert c["capture_contract"]["newer_run_backfill_old_origin"] is False
    for field in [
        "future_provider_cycle",
        "backdated_known_at",
        "retrospective_replacement_with_newer_run",
        "H8_H15_weather_fabrication",
    ]:
        assert c["capture_contract"][field] is False
    assert c["seal_contract"]["target_actual_read_before_seal"] is False
    assert c["seal_contract"]["target_actual_score_before_seal"] is False
    assert c["future_scoring"]["execution_authorized"] is False
    assert c["training_contract"]["historical_performance_candidate_selection"] is False
    assert c["provider"]["real_surface_qualified_in_s0"] is False
    assert c["COHORT_ID"] == "V0_14_AS_ISSUED_WEATHER_PROSPECTIVE_COHORT_R1"
    assert c["future_scoring"]["primary"] == ["H7_DAILY_WAPE", "H15_DAILY_WAPE"]
    assert c["future_scoring"]["metric_contract_bound_before_issuance"] is True
    assert (
        c["future_scoring"]["changed_metric_contract"]
        == "NOT_COMPARABLE_TO_ORIGINAL_PROSPECTIVE_COHORT"
    )
    assert c["future_scoring"]["promotion_threshold"] is None
    assert c["completion"]["minimum_valid_real_shadow_seals"] == 1
    assert c["completion"]["required_slices"] == ["S0", "S1", "S2", "S3", "S4"]
    assert c["completion"]["future_actual_required"] is False
    assert c["V0_14_VERSION_COMPLETE"] is False
    assert c["NEW_PROSPECTIVE_FORECAST_COUNT"] == 0
    assert c["WEATHER_AS_ISSUED_INCREMENTAL_VALUE"] == "NOT_EVALUATED"
    assert c["FUTURE_PROSPECTIVE_SCORING_VERSION"] == "V0.15"
    assert c["LATEST_FORMAL_RELEASE"] == "v0.11.0"
    assert c["V0_14_S0_AUTHORIZED"] is True
    assert c["V0_14_S0_COMPLETE"] is True
    for field in c["forbidden_true_fields"]:
        assert c[field] is False, field
    assert set(c["forbidden_true_fields"]) >= {
        "GDD_IN_V0_14_CANDIDATE",
        "HYPERPARAMETER_SEARCH",
        "WEATHER_FEATURE_SEARCH_BY_RESULT",
        "TARGET_ACTUAL_READ_BEFORE_SEAL",
        "REAL_PROSPECTIVE_SCORING_IN_V0_14",
        "V0_14_S1_AUTHORIZED",
        "V0_14_S2_AUTHORIZED",
        "V0_14_S3_AUTHORIZED",
        "V0_14_S4_AUTHORIZED",
        "V0_15_AUTHORIZED",
        "PRODUCTION_USE_APPROVED",
        "REAL_ECMWF_CAPTURE_EXECUTED",
        "PRIVATE_HARVEST_ROW_READ",
        "PRIVATE_WEATHER_ARTIFACT_READ",
        "PRIVATE_AREA_ARTIFACT_READ",
        "MODEL_TRAINING_EXECUTED",
        "MODEL_PREDICTION_EXECUTED",
        "SCORING_EXECUTED",
        "TAG_CREATED",
        "RELEASE_CREATED",
        "READY_AUTHORIZED",
        "MERGE_AUTHORIZED",
    }


def test_frozen_protocol_acceptance() -> None:
    validate(contract())


@pytest.mark.parametrize(
    "field",
    [
        "H15_PROVIDER_SURFACE_GUARANTEED",
        "ENDPOINT_SNAPSHOTS_FORM_COMPLETE_FUTURE_WEATHER_WINDOW",
        "FUTURE_WEATHER_FEATURE_SCHEMA_FROZEN",
        "HISTORICAL_PROXY_IS_AS_ISSUED_FORECAST",
        "GDD_IN_V0_14_CANDIDATE",
        "HYPERPARAMETER_SEARCH",
        "WEATHER_FEATURE_SEARCH_BY_RESULT",
        "TARGET_ACTUAL_READ_BEFORE_SEAL",
        "PREVIOUS_SEASON_AREA_AS_CURRENT_SEASON_FALLBACK",
        "REAL_PROSPECTIVE_SCORING_IN_V0_14",
        "V0_15_AUTHORIZED",
        "PRODUCTION_USE_APPROVED",
        "V0_14_S1_AUTHORIZED",
        "V0_14_S2_AUTHORIZED",
        "V0_14_S3_AUTHORIZED",
        "V0_14_S4_AUTHORIZED",
        "FIRST_ISSUANCE_SCOPE_AUTHORIZED",
        "CURRENT_SCOPE_AUTHORITY_REVALIDATED",
        "PRIVATE_WEATHER_ARTIFACT_READ",
        "PRIVATE_AREA_ARTIFACT_READ",
        "PRIVATE_HARVEST_ROW_READ",
    ],
)
def test_forbidden_scope_mutations_fail_closed(field: str) -> None:
    c = copy.deepcopy(contract())
    c[field] = True
    with pytest.raises(AssertionError):
        validate(c)


@pytest.mark.parametrize(
    "section,field,value",
    [
        ("provider", "REQUIRED_HORIZONS", [24, 72, 168, 360]),
        ("provider", "OPTIONAL_HORIZONS", []),
        ("algorithm", "ALPHA", "1.000000"),
        ("algorithm", "STANDARDIZATION", "ALL_ROWS_SCALER"),
        ("capture_contract", "newer_run_backfill_old_origin", True),
        ("capture_contract", "ordering_violation", "WARN_ONLY"),
        ("future_scoring", "primary", ["H1_DAILY_WAPE"]),
        ("completion", "future_actual_required", True),
        ("completion", "minimum_valid_real_shadow_seals", 0),
        ("seal_contract", "target_actual_read_before_seal", True),
        ("seal_contract", "target_actual_score_before_seal", True),
        ("future_scoring", "execution_authorized", True),
        ("training_contract", "historical_performance_candidate_selection", True),
        ("provider", "real_surface_qualified_in_s0", True),
    ],
)
def test_nested_contract_mutations_fail_closed(section: str, field: str, value: Any) -> None:
    c = copy.deepcopy(contract())
    c[section][field] = value
    with pytest.raises(AssertionError):
        validate(c)


def test_public_source_pins_and_prior_version_closeout() -> None:
    c = contract()
    for source in c["public_sources"]:
        path = ROOT / source["path"]
        assert not Path(source["path"]).is_absolute()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == source["sha256"]
    prior = json.loads((ROOT / c["public_sources"][0]["path"]).read_text())
    for field in [
        "V0_13_VERSION_COMPLETE",
        "V0_13_VERSION_CLOSEOUT_COMPLETE",
        "V0_13_FEATURE_DEVELOPMENT_FROZEN",
    ]:
        assert prior[field] is True
    assert (
        prior["WEATHER_QUANTITY_INCREMENTAL_VALUE"]
        == c["V0_13_WEATHER_QUANTITY_VALUE"]
        == "SUPPORTED"
    )
    assert (
        prior["WEATHER_PEAK_TIMING_INCREMENTAL_VALUE"]
        == c["V0_13_WEATHER_TIMING_VALUE"]
        == "NOT_SUPPORTED"
    )
    assert prior["PRODUCTION_LIKE_WEATHER_VALIDATION"] is False
    lineage = c["V0_13_closeout_lineage"]
    assert lineage["pr"] == 673
    assert lineage["head"] == "2ea3ee736b8ded06269ace768d249497d70b791a"
    assert lineage["merge"] == c["BASE_SHA"]
    assert lineage["exact_head_ci_run"] == 37178547066
    assert lineage["post_merge_ci_run"] == 37180837114
    assert lineage["state"] == "MERGED"


def test_provider_constants_from_committed_source_without_instantiation() -> None:
    c = contract()["provider"]
    tree = ast.parse((ROOT / c["source_file"]).read_text())
    assignments = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id
        in {
            "PROVIDER_NAME",
            "MODEL_ID",
            "STREAM",
            "RESOLUTION",
            "REQUIRED_HORIZONS",
            "OPTIONAL_HORIZONS",
            "BASE_LOCATION_COUNT",
            "BASE_LOCATION_AUTHORITY_SHA256",
            "BASE_LOCATION_AUTHORITY_PAYLOAD_HASH",
            "PARAMETERS",
            "OPTIONAL_PARAMETERS",
        }
    }
    for name, value in assignments.items():
        assert c[name] == (list(value) if isinstance(value, tuple) else value)
    assert c["coordinate_review_status"] == "RANGE_VALID_CRS_UNCONFIRMED"
    assert c["coordinate_reference_system"] == "NOT_ESTABLISHED"
    assert c["PERMANENT_BUSINESS_COVERAGE_CLAIM"] is False


def test_yangliu_is_only_a_public_scope_candidate() -> None:
    c = contract()
    source = json.loads((ROOT / c["scope_gate"]["candidate_public_source"]).read_text())
    request = source["real_acceptance"]
    candidate = c["scope_gate"]["candidate_request"]
    for field in ["farm", "productive_area_mu", "target_season", "as_of"]:
        assert candidate[field] == request[field]
    assert c["FIRST_ISSUANCE_SCOPE_CANDIDATE"] == "YANG_LIU_2026_2027"
    assert c["FIRST_ISSUANCE_SCOPE_AUTHORIZED"] is False
    assert c["scope_gate"]["candidate_is_current_scope_authority"] is False


def test_future_scoring_seal_and_lifecycle_are_complete() -> None:
    c = contract()
    assert set(c["seal_contract"]["required_fields"]) >= {
        "forecast_id",
        "request_snapshot",
        "scope_authority_hash",
        "C0_artifact_hash",
        "W1_artifact_hash",
        "weather_snapshot_ids",
        "weather_snapshot_hashes",
        "provider_manifest_hash",
        "forecast_created_at",
        "prediction_hashes",
        "metric_contract",
    }
    assert (
        c["seal_contract"]["prospective_pristine_if_target_actual_used_for_decisions"]
        == "INVALID_FOR_NEW_VALIDATION"
    )
    assert c["seal_contract"]["claims_no_actual_exists_in_external_world"] is False
    assert c["future_scoring"]["required_reporting"] == [
        "C0_VS_W1",
        "SAME_SEALED_COHORT",
        "SAME_ACTUAL_DENOMINATOR",
        "PER_SCOPE",
        "COMBINED",
        "COVERAGE",
        "COMPLETENESS",
    ]
    assert c["future_scoring"]["secondary"] == [
        "DAILY_MAE",
        "BIAS",
        "SINGLE_DAY_PEAK_DATE",
        "SINGLE_DAY_PEAK_QUANTITY",
        "ROLLING7_PEAK_DATE",
        "ROLLING7_PEAK_QUANTITY",
        "SHAPE_IF_COMPUTABLE",
    ]
    assert c["operations"]["protocol_change_requires"] == "NEW_PROTOCOL_VERSION_OR_NEW_MODEL_COHORT"
    assert (
        c["operations"]["post_closeout_accumulation_role"]
        == "DATA_ACCUMULATION_UNDER_FROZEN_PROTOCOL"
    )
    assert c["operations"]["accumulation_authorized_by_s0"] is False
    assert c["operations"]["shadow_mode"] == {
        "TEST_ONLY": False,
        "SHADOW": True,
        "PRODUCTION": False,
    }
    assert len(c["research_questions"]) == 4
    assert [s["id"] for s in c["slice_plan"]] == ["S0", "S1", "S2", "S3", "S4"]
    assert len(c["provider"]["S1_qualification_questions"]) == 10
    plan = PLAN.read_text()
    for phrase in [
        "端点",
        "393.4",
        "360h",
        "domain shift",
        "V0.15",
        "不能",
        "S1",
        "S2",
        "S3",
        "S4",
    ]:
        assert phrase in plan
