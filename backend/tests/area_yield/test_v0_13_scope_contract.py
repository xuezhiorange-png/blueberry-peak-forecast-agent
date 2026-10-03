"""Public contract assertions only: no training, scoring, private data or features."""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCOPE = ROOT / "docs/v0-13/evidence/v0.13.0-version-plan-and-scope-freeze.json"
PLAN = ROOT / "docs/v0-13/v0.13.0-version-plan-and-scope-freeze.md"
S3 = ROOT / "docs/v0-7/evidence/s3-weather-aware-model-training-and-oot-backtest.json"
S2 = ROOT / "docs/v0-7/evidence/s2-weather-dataset-and-leakage-safe-feature-freeze.json"
pytestmark = pytest.mark.contract


def contract() -> dict[str, Any]:
    value = json.loads(SCOPE.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_identity_prior_version_and_namespace() -> None:
    c = contract()
    assert c["VERSION"] == "0.13.0"
    assert c["VERSION_NAME"] == "WEATHER_AND_GDD_INCREMENTAL_VALUE_RESEARCH"
    assert c["VERSION_NAME_CN"] == "天气与积温增量价值研究版"
    assert c["RELEASE_CLASS"] == "RESEARCH_VERSION"
    assert c["BASE_SHA"] == "2759b184b09440d35c9872a8241519a8e8a26f2b"
    assert c["V0_13_SCOPE_FROZEN"] is True
    assert c["V0_13_NAMESPACE_CLEAR"] is True
    assert c["V0_13_IS_V0_12_CONTINUATION"] is False
    assert c["V0_12_REOPEN_AUTHORIZED"] is False
    assert c["V0_12_R1_ARTIFACT_UNCHANGED"] is True
    assert c["V0_12_R1_MODEL_ROLE"] == "RESEARCH_CANDIDATE"


def test_four_model_attribution_and_algorithm() -> None:
    c = contract()
    assert c["models"] == [
        {"id": "V0_13_M0_BASE", "features": ["BASE_FEATURES"]},
        {"id": "V0_13_M1_WEATHER", "features": ["BASE_FEATURES", "WEATHER"]},
        {"id": "V0_13_M2_GDD", "features": ["BASE_FEATURES", "GDD"]},
        {"id": "V0_13_M3_WEATHER_GDD", "features": ["BASE_FEATURES", "WEATHER", "GDD"]},
    ]
    assert c["MODEL_ROLE"] == "FEATURE_VALUE_EXPERIMENT_MODELS"
    assert c["MODEL_FAMILY"] == "RIDGE_LEAST_SQUARES"
    assert c["ALPHA"] == "10.000000"
    assert c["INTERCEPT_UNPENALIZED"] is True
    assert c["NONNEGATIVE_OUTPUT_CLIP"] is True
    assert c["SOLVER"] == "numpy.linalg.solve"
    assert c["STANDARDIZATION"] == "TRAIN_ONLY_STANDARD_SCALER_POPULATION_STD"
    assert c["ZERO_STD_POLICY"] == "SCALE_1"
    assert c["ONLY_EXPERIMENTAL_DIFFERENCE"] == "FEATURE_SET"
    assert len(c["base_features"]) == 10
    assert set(c["invariants"]) == {
        "target_rows",
        "training_labels",
        "validation_labels",
        "folds",
        "forecast_origins",
        "target_horizons",
        "algorithm_family",
        "regularization",
        "standardization_policy",
        "nonnegative_clipping",
        "scoring",
    }


def test_weather_family_and_event_time_are_frozen_authority() -> None:
    c = contract()["weather"]
    s2 = json.loads(S2.read_text(encoding="utf-8"))
    assert c["WINDOWS"] == s2["feature_policy"]["windows_days"] == [7, 14, 30]
    assert c["WEATHER_FEATURE_COUNT"] == s2["feature_policy"]["feature_count"] == 18
    assert c["VARIABLES"] == [
        "mean_temperature",
        "mean_tmin",
        "mean_tmax",
        "precipitation_sum",
        "solar_radiation_mean",
        "wind_speed_mean",
    ]
    assert c["WEATHER_BASE_COUNT"] == 38
    assert c["WEATHER_SEASON_COUNT"] == 3
    assert c["ERA5_ROLE"] == "HISTORICAL_REALIZED_OBSERVATION"
    assert c["WEATHER_LANE_A"] == "PAST_OBSERVED_WEATHER"
    assert c["FORECAST_ORIGIN_POLICY"] == "ROLLING_DAILY_LOCAL_DAY_START"
    assert c["FORECAST_ORIGIN_TIMEZONE"] == "Asia/Shanghai"
    assert c["MAX_REALIZED_WEATHER_SOURCE_DATE"] == "FORECAST_ORIGIN_LOCAL_DATE_MINUS_1"
    assert c["MAX_SOURCE_OBSERVATION_TIME"] == "STRICTLY_BEFORE_FORECAST_ORIGIN"
    assert c["FUTURE_REALIZED_WEATHER_ALLOWED"] is False
    assert c["FUTURE_FORECAST_FEATURES_IN_LANE_A"] is False
    assert c["AS_ISSUED_KNOWN_AT_STATUS"] == "NOT_ESTABLISHED"
    assert c["PRODUCTION_LIKE_PIT_ELIGIBLE"] is False


def test_fold_row_and_base_identities_match_public_s3() -> None:
    c = contract()
    s3 = json.loads(S3.read_text(encoding="utf-8"))
    assert c["actual_label_authorities"] == s3["authorities"]
    folds = c["cohort"]["folds"]
    assert len(folds) == 2
    for frozen, source in zip(folds, s3["folds"].values(), strict=True):
        for field in (
            "fold_id",
            "train_seasons",
            "validation_season",
            "training_row_count",
            "training_row_keys_hash",
            "validation_base_count",
            "validation_prediction_row_count",
            "validation_scored_row_count",
            "validation_unscored_row_count",
        ):
            assert frozen[field] == source[field]
        assert frozen["eligible_base_ids"] == sorted(
            source["validation_dataset_meta"]["incomplete_origin_count_by_base"]
        )
        assert frozen["business_boundary"] == source["prediction_manifest"]["business_boundary"]
        assert (
            frozen["validation_row_keys_hash"]
            == (source["prediction_manifest"]["validation_target_row_keys_hash"])
        )
    assert folds[0]["train_seasons"] == ["2023-2024"]
    assert folds[0]["validation_season"] == "2024-2025"
    assert folds[1]["train_seasons"] == ["2023-2024", "2024-2025"]
    assert folds[1]["validation_season"] == "2025-2026"
    assert [len(f["eligible_base_ids"]) for f in folds] == [13, 29]


def test_common_comparable_cohort_and_labels_fail_closed() -> None:
    c = contract()["cohort"]
    assert c["V0_13_REUSES_V0_7_S3_COHORT"] is True
    assert c["COMMON_COMPARABLE_COHORT_REQUIRED"] is True
    assert c["NO_MODEL_SPECIFIC_COHORT"] is True
    assert c["MISSING_IS_ZERO"] is False
    assert c["RANDOM_SPLIT_ALLOWED"] is False
    assert c["VALIDATION_LABELS_AFTER_PREDICTION_SEAL"] is True
    assert c["TRAIN_TARGET_ROWS_DEDUPLICATED"] is True
    assert c["FUTURE_LABELS_FOR_PREPROCESSING"] is False
    assert c["NEW_INDEPENDENT_VALIDATION_CLAIM"] is False


def test_gdd_definition_not_chosen_and_s1_process_preregistered() -> None:
    c = contract()["gdd"]
    assert c["GDD_DEFINITION_SELECTED"] is False
    assert c["GDD_BASE_TEMPERATURE_C"] is None
    assert c["GDD_SWEEP_AUTHORIZED"] is False
    assert c["SEASON_TO_DATE_ENABLED"] is None
    assert c["HISTORICAL_PHENOLOGY_AUTHORITY_AVAILABLE"] is False
    assert c["FLOWERING_TO_HARVEST_CLAIM_ALLOWED"] is False
    assert c["PHENOLOGY_ANCHORED_GDD_IN_SCOPE"] is False
    assert c["required_family"] == ["GDD_W7", "GDD_W14", "GDD_W30"]
    assert c["optional_family"] == ["GDD_SEASON_TO_DATE"]
    assert c["forbidden_windows"] == [3, 5, 10, 21, 45, 60]
    assert c["OPTIONAL_FAMILY_DECIDED_BEFORE_RESULTS"] is True
    assert c["MAX_GDD_SOURCE_DATE"] == "FORECAST_ORIGIN_LOCAL_DATE_MINUS_1"
    assert c["definition_process"] == [
        "LITERATURE_OR_BUSINESS_AGRONOMIC_EVIDENCE",
        "ONE_PREDECLARED_DEFINITION",
        "FREEZE_BEFORE_SCORE_VISIBILITY",
        "FEATURE_GENERATION_ONLY_AFTER_AUTHORIZATION",
    ]
    assert c["S1_REQUIRED_FIELDS"] == [
        "GDD_BASE_TEMPERATURE_C",
        "DAILY_TEMPERATURE_FORMULA",
        "LOWER_CLIP_POLICY",
        "UPPER_CLIP_POLICY",
        "MISSING_DAY_POLICY",
        "LOCAL_DAY_TIMEZONE",
        "ACCUMULATION_START_POLICY",
        "PRECISION_AND_ROUNDING",
        "SOURCE_TEMPERATURE_FIELDS",
    ]
    assert c["AMBIGUOUS_DEFINITION_ACTION"] == "BLOCKED_OR_INCONCLUSIVE_DEFINITION_NO_SWEEP"


def test_daily_and_cumulative_metrics_are_not_interchangeable() -> None:
    c = contract()
    targets = c["targets"]
    assert targets["TARGET_ROW_IDENTITY"] == "base_id+forecast_origin+target_date"
    assert targets["TARGET_LABEL"] == "ACTUAL_DAILY_HARVEST_KG"
    assert targets["PRIMARY_HORIZONS"] == ["H7", "H15"]
    assert targets["SECONDARY_HORIZON"] == "H1"
    assert targets["horizons"] == {"H1": 1, "H7": 7, "H15": 15}
    metrics = c["metrics"]
    assert metrics["daily"] == ["DAILY_WAPE", "DAILY_MAE_KG", "BIAS_KG"]
    assert metrics["cumulative"] == ["H7_CUMULATIVE_WAPE", "H15_CUMULATIVE_WAPE"]
    assert metrics["distribution"] == ["MEDIAN_ABS_ERROR", "P75_ABS_ERROR", "P90_ABS_ERROR"]
    assert c["support_rule"]["metric"] == (
        "DAILY_WAPE_IN_COMPLETE_H7_AND_H15_VIEWS_NOT_CUMULATIVE_WAPE"
    )


def test_peak_shape_authority_and_complete_same_origin_calendar() -> None:
    c = contract()["metrics"]
    assert c["temporal"] == [
        "SINGLE_DAY_PEAK_DATE_MAE_DAYS",
        "SINGLE_DAY_PEAK_QUANTITY_MAE_KG",
        "ROLLING_7DAY_PEAK_START_DATE_MAE_DAYS",
        "ROLLING_7DAY_PEAK_QUANTITY_MAE_KG",
        "CURVE_SHAPE_ERROR",
    ]
    assert c["PEAK_EVALUATION_UNIT"] == (
        "COMPLETE_AUTHORITATIVE_H15_BASE_ORIGIN_WINDOW_SAME_ORIGIN_NO_ROLLING_ORIGIN_STITCHING"
    )
    assert c["PEAK_METRIC_STATUS_IF_INCOMPLETE"] == "NOT_COMPUTABLE"
    assert c["SEASON_WIDE_PEAK_CLAIM"] is False
    assert c["PEAK_TIE_RULE"] == "EARLIEST_DATE"
    assert c["ROLLING7_RULE"] == "MAX_CUMULATIVE_COMPLETE_7_CONSECUTIVE_CALENDAR_DAYS"
    assert c["CURVE_SHAPE_DEFINITION_STATUS"] == "REUSED_FROZEN_NORMALIZED_TOTAL_SHAPE_MICRO_WAPE"
    assert c["CURVE_SHAPE_AUTHORITY"] == "backend/app/area_yield/research_records.py:score_curve"
    assert c["CURVE_SHAPE_FORMULA"] == (
        "Q=sum(a),P=sum(p),E=sum(abs(p*Q/P-a)); pooled CURVE_SHAPE_ERROR=sum(E)/sum(Q), "
        "Q>0 and P>0; same complete H15 windows as peak metrics"
    )


def test_five_comparisons_breadth_and_predeclared_contributors() -> None:
    c = contract()
    assert [(r["new"], r["reference"]) for r in c["comparisons"]] == [
        ("V0_13_M1_WEATHER", "V0_13_M0_BASE"),
        ("V0_13_M2_GDD", "V0_13_M0_BASE"),
        ("V0_13_M3_WEATHER_GDD", "V0_13_M0_BASE"),
        ("V0_13_M3_WEATHER_GDD", "V0_13_M1_WEATHER"),
        ("V0_13_M3_WEATHER_GDD", "V0_13_M2_GDD"),
    ]
    assert c["deltas"]["absolute"] == "new_error-reference_error"
    assert c["deltas"]["relative"] == "(new_error-reference_error)/reference_error"
    assert c["deltas"]["NEGATIVE_DELTA"] == "IMPROVEMENT"
    assert c["breadth"] == [
        "COMPARABLE_BASE_COUNT",
        "IMPROVED_BASE_COUNT",
        "DEGRADED_BASE_COUNT",
        "UNCHANGED_BASE_COUNT",
        "IMPROVED_BASE_SHARE",
        "DEGRADED_BASE_SHARE",
        "IMPROVED_ACTUAL_KG_SHARE",
        "DEGRADED_ACTUAL_KG_SHARE",
    ]
    r = c["robustness"]
    assert r["required"] == ["LEAVE_TOP1", "LEAVE_TOP2"]
    assert r["horizons"] == ["H1", "H7", "H15"]
    assert r["primary_gate_horizons"] == ["H7", "H15"]
    assert r["contributor_definition"] == (
        "POSITIVE_ABSOLUTE_ERROR_REDUCTION_KG_REFERENCE_MINUS_NEW_ON_COMPLETE_HORIZON_DAILY_ROWS"
    )
    assert r["sort"] == "DESCENDING_POSITIVE_REDUCTION_THEN_BASE_ID_ASCENDING"


def test_support_requires_all_conditions_not_just_pooled_gain() -> None:
    c = contract()
    r = c["support_rule"]
    assert r["conditions"] == [
        "H7_COMBINED_DELTA_LT_0",
        "H15_COMBINED_DELTA_LT_0",
        "H7_EVERY_PREDECLARED_FOLD_DELTA_LT_0",
        "H15_EVERY_PREDECLARED_FOLD_DELTA_LT_0",
        "H7_COMBINED_LEAVE_TOP2_DELTA_LT_0",
        "H15_COMBINED_LEAVE_TOP2_DELTA_LT_0",
        "H7_EVERY_FOLD_IMPROVED_ACTUAL_KG_SHARE_GT_0_50",
        "H15_EVERY_FOLD_IMPROVED_ACTUAL_KG_SHARE_GT_0_50",
        "NO_CONTRACT_VIOLATION",
        "NO_LEAKAGE",
        "NO_POST_RESULT_TUNING",
    ]
    assert r["SUPPORTED"] == "ALL_CONDITIONS_REQUIRED"
    assert r["H1_CAN_ESTABLISH_SUPPORT"] is False
    assert (
        r["INVALID_EXPERIMENT"] == "BLOCKED_CONTRACT_VIOLATION_NOT_A_FEATURE_VALUE_CLASSIFICATION"
    )
    assert "M3 vs M1 and M3 vs M2 each SUPPORTED" in r["JOINT_INCREMENTAL_CLAIM"]
    assert c["decision_labels"] == ["SUPPORTED", "INCONCLUSIVE", "NOT_SUPPORTED"]
    assert c["BUSINESS_ACCURACY_THRESHOLD_STATUS"] == "NOT_ESTABLISHED"
    assert c["MINIMUM_PERCENT_IMPROVEMENT_THRESHOLD"] is None


def test_peak_timing_is_not_peak_amplitude_or_family_cherry_picking() -> None:
    r = contract()["peak_timing_rule"]
    assert r["SUPPORTED_ALL"] == [
        "BOTH_DATE_MAE_COMBINED_DELTAS_LT_0",
        "BOTH_DATE_MAE_DELTAS_LT_0_EVERY_EVALUABLE_PREDECLARED_FOLD",
        "CURVE_SHAPE_COMBINED_DELTA_LE_0",
        "NO_CONTRACT_VIOLATION_LEAKAGE_OR_TUNING",
    ]
    assert r["reference"] == "V0_13_M0_BASE"
    assert r["AMPLITUDE_ONLY_SUPPORTS_TIMING"] is False
    assert r["per_family_reporting_required"] is True
    assert (
        "no evaluable windows in any predeclared fold forbids SUPPORTED"
        in (r["INSUFFICIENT_COMPLETE_AUTHORITY"])
    )


def test_oracle_is_not_primary_or_deployable() -> None:
    assert contract()["oracle"] == {
        "LANE_C": "FUTURE_REALIZED_ORACLE",
        "RESEARCH_ONLY": True,
        "DEPLOYABLE": False,
        "PROSPECTIVE_EQUIVALENT": False,
        "PRIMARY_LANE_RANKING_ALLOWED": False,
        "CANDIDATE_PROMOTION_ALLOWED": False,
        "EXECUTION_AUTHORIZED": False,
    }


def test_old_weather_conclusion_remains_inconclusive() -> None:
    c = contract()["v0_7_history"]
    assert c["V0_7_WEATHER_EXPERIMENT_COMPLETED"] is True
    assert c["relative_improvement_percent_approx"] == {"H1": "1.26", "H7": "3.39", "H15": "3.45"}
    assert c["V0_7_WEATHER_INCREMENTAL_VALUE"] == "INCONCLUSIVE"
    assert c["H1_LEAVE_TOP2_DIRECTION_REVERSED"] is True
    assert c["HISTORICAL_EVIDENCE_REMAINS_CONSUMED"] is True
    assert c["NEW_BLIND_VALIDATION"] is False


@pytest.mark.parametrize(
    "field",
    [
        "V0_13_S1_AUTHORIZED",
        "V0_13_S2_AUTHORIZED",
        "V0_13_S3_AUTHORIZED",
        "V0_13_S4_AUTHORIZED",
        "V0_13_S5_AUTHORIZED",
        "MODEL_TRAINING_EXECUTED",
        "BACKTEST_EXECUTED",
        "SCORING_EXECUTED",
        "GDD_FEATURE_GENERATION_EXECUTED",
        "WEATHER_FEATURE_REGENERATION_EXECUTED",
        "PRIVATE_WEATHER_DATA_READ",
        "PRIVATE_HARVEST_ROW_READ",
        "NEW_MODEL_ARTIFACT",
        "NEW_PREDICTION",
        "HYPERPARAMETER_SEARCH",
        "FEATURE_SEARCH",
        "PROSPECTIVE_ACCURACY_VALIDATED",
        "PRODUCTION_USE_APPROVED",
        "REAL_PROSPECTIVE_ENABLED",
        "V0_13_VERSION_COMPLETE",
        "READY_AUTHORIZED",
        "MERGE_AUTHORIZED",
        "AUTO_MERGE",
        "TAG_CREATED",
        "RELEASE_CREATED",
        "DECISIONS_EXECUTED",
    ],
)
def test_no_future_slice_execution_or_promotion(field: str) -> None:
    assert contract()[field] is False


def test_public_authority_hashes_and_no_absolute_path() -> None:
    c = contract()
    for source in c["sources"]:
        path = Path(source["path"])
        assert not path.is_absolute() and ".." not in path.parts
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == source["sha256"]
    for text in (SCOPE.read_text(encoding="utf-8"), PLAN.read_text(encoding="utf-8")):
        assert "/Users/" not in text
        assert "file://" not in text
    assert c["FINAL_HEAD_SHA"] is None


def test_research_questions_and_slice_closeout_are_explicit() -> None:
    c = contract()
    assert set(c["research_questions"]) == {"RQ1", "RQ2", "RQ3", "RQ4"}
    assert len(c["slices"]) == 6
    assert c["closeout_options"] == [
        "RESEARCH_CLOSEOUT_FEATURE_SUPPORTED",
        "RESEARCH_CLOSEOUT_FEATURE_INCONCLUSIVE",
        "RESEARCH_CLOSEOUT_FEATURE_NOT_SUPPORTED",
    ]
    plan = PLAN.read_text(encoding="utf-8")
    for token in (
        "V0.13-S0",
        "V0.13-S1",
        "V0.13-S2",
        "V0.13-S3",
        "V0.13-S4",
        "V0.13-S5",
        "INCONCLUSIVE_DEFINITION",
        "COMMON_COMPARABLE_COHORT",
        "S0 不产生这些结论",
        "FLOWERING_TO_HARVEST_GDD",
        "H7_CUMULATIVE_WAPE",
        "NOT_COMPUTABLE",
    ):
        assert token in plan
