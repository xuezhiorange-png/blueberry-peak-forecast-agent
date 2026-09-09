"""Contract tests for the V0.3 S4 V2 historical-only readiness adapter."""

from __future__ import annotations

import gzip
import inspect
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

import backend.app.s4_local_engineering as local_engineering
from backend.app.forecast_quality.farm_total_baseline_estimator import (
    FarmTotalBaselineGroupStatus,
    derive_farm_total_baseline_estimator,
)
from backend.app.forecast_quality.farm_total_dataset import (
    FarmTotalDatasetDiagnostics,
    FarmTotalDatasetRow,
    FarmTotalPartitionDataset,
    FarmTotalTrainingDataset,
    compute_partition_dataset_sha256,
)
from backend.app.forecast_quality.farm_total_policy import (
    AREA_AUTHORITY_CLASS_PREVIOUS_SEASON_PROXY,
)
from backend.app.rolling_backtest.canonical import sha256_payload
from backend.app.s4_experiment import (
    EXPERIMENT_PLAN_V2_HASH,
    EXPERIMENT_PLAN_V2_VERSION,
    EXPERIMENT_PLAN_VERSION,
    GUARDRAIL_POLICY_HASH,
    S4_A_EXPERIMENT_PLAN_HASH_BOUND,
    V2_CANDIDATE_01_RERUN_FORBIDDEN,
    V2_CANDIDATE_06_EXECUTION_ELIGIBLE,
    V2_CANDIDATE_08_EXECUTION_ELIGIBLE,
    V2_CANONICAL_STARTED_COUNT,
    V2_EFFECTIVE_CONSUMED,
    V2_FORECAST_HORIZONS,
    V2_GUARDRAIL_POLICY_HASH,
    V2_HISTORICAL_DATA_ONLY,
    V2_LEGACY_RECONCILED_VALIDATION_DEBIT,
    V2_REMAINING_VALIDATION_EVALUATIONS,
    V2_TEST_REMAINS_SEALED,
    canonical_guardrail_policy,
    canonical_guardrail_policy_v2,
)
from backend.app.s4_local_engineering import (
    V2_COMPLETE_WINDOW_METRICS_UNAVAILABLE,
    V2_HISTORICAL_HORIZON_SET_INCOMPLETE,
    V2_POST_CUTOFF_FEATURE_FORBIDDEN,
    V2_SOURCE_ID,
    LocalEngineeringContractError,
    build_v2_historical_evaluation_authority,
    load_frozen_engineering_dataset,
    v2_training_rows,
    validate_v2_feature_dates,
    validate_v2_forecast_horizon,
)
from backend.app.s4_v2_historical_only_execution import (
    V2_CANDIDATE_01_ID,
    V2_CANDIDATE_02_ID,
    V2_CANDIDATE_03_ID,
    V2_CANDIDATE_04_ID,
    V2_CANDIDATE_06_ID,
    V2_CANDIDATE_08_ID,
    V2_CANDIDATE_AUDIT_ORDER,
    build_v2_candidate_compatibility_audit,
    build_v2_historical_only_authority,
    build_v2_historical_only_readiness,
    v2_guardrail_metric_availability,
    v2_policy_is_self_consistent,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def authority() -> local_engineering.V2HistoricalEvaluationAuthority:
    return build_v2_historical_only_authority(REPO_ROOT)


def _audit_by_id() -> dict[str, Any]:
    return {item.candidate_id: item for item in build_v2_candidate_compatibility_audit()}


def test_v1_plan_identity_remains_replayable() -> None:
    assert EXPERIMENT_PLAN_VERSION == "v0.3-experiment-plan-v1"
    assert S4_A_EXPERIMENT_PLAN_HASH_BOUND == (
        "9e223a02a1b38c028c230a45eb1fa8323f3c2247bb85e7b439f3351e51042500"
    )
    assert sha256_payload(canonical_guardrail_policy()) == GUARDRAIL_POLICY_HASH


def test_v2_plan_identity_is_current_execution_authority() -> None:
    policy = canonical_guardrail_policy_v2()
    assert EXPERIMENT_PLAN_V2_VERSION == "v0.3-experiment-plan-v2"
    assert EXPERIMENT_PLAN_V2_HASH == (
        "c2bfab4ec38b4ca640f62d061494961c5b49afe5b52fa675326aa80fdf5f8ad9"
    )
    assert policy["experiment_plan_version"] == EXPERIMENT_PLAN_V2_VERSION
    assert policy["s4_a_experiment_plan_hash_bound"] == EXPERIMENT_PLAN_V2_HASH


def test_v2_guardrail_policy_hash_is_deterministic() -> None:
    assert sha256_payload(canonical_guardrail_policy_v2()) == V2_GUARDRAIL_POLICY_HASH
    assert v2_policy_is_self_consistent()
    assert V2_GUARDRAIL_POLICY_HASH != GUARDRAIL_POLICY_HASH


def test_v2_policy_does_not_change_v1_hash() -> None:
    v1_before = sha256_payload(canonical_guardrail_policy())
    _ = canonical_guardrail_policy_v2()
    assert sha256_payload(canonical_guardrail_policy()) == v1_before == GUARDRAIL_POLICY_HASH


def test_c01_rerun_remains_forbidden() -> None:
    item = _audit_by_id()[V2_CANDIDATE_01_ID]
    assert V2_CANDIDATE_01_RERUN_FORBIDDEN is True
    assert item.current_v0_3_execution_eligible is False
    assert item.reason_code == "CANDIDATE_01_RERUN_FORBIDDEN"
    assert item.parameter_reaches_prediction_math is True
    assert item.parameter_change_can_change_prediction is True


def test_candidate_06_v2_execution_blocked() -> None:
    readiness = build_v2_historical_only_readiness()
    assert V2_CANDIDATE_06_EXECUTION_ELIGIBLE is False
    assert readiness.candidate_06_execution_eligible is False
    assert readiness.next_executable_candidate == "NONE"
    assert V2_CANDIDATE_06_ID not in V2_CANDIDATE_AUDIT_ORDER


def test_candidate_08_v2_execution_blocked() -> None:
    readiness = build_v2_historical_only_readiness()
    assert V2_CANDIDATE_08_EXECUTION_ELIGIBLE is False
    assert readiness.candidate_08_execution_eligible is False
    assert readiness.next_executable_candidate == "NONE"
    assert V2_CANDIDATE_08_ID not in V2_CANDIDATE_AUDIT_ORDER


def test_source002_train_identity_exact(
    authority: local_engineering.V2HistoricalEvaluationAuthority,
) -> None:
    assert authority.source_id == V2_SOURCE_ID == "SOURCE_002"
    assert authority.train_dataset_identity == (
        "be2d4184434a0f389af21c315945322e9216cd17cc471b772e3fff389d3386d2"
    )
    assert authority.train_row_count == 16_224


def test_source002_validation_identity_exact(
    authority: local_engineering.V2HistoricalEvaluationAuthority,
) -> None:
    assert authority.validation_dataset_identity == (
        "4cbf1119f83034464159210ebbbeea5ec87848f92ce044bb328949a8f5331d06"
    )
    assert authority.validation_row_count == 8_006


def test_source002_partition_identity_tamper_blocks() -> None:
    dataset = load_frozen_engineering_dataset(REPO_ROOT)
    with pytest.raises(
        LocalEngineeringContractError, match="SOURCE_002_V2_PARTITION_IDENTITY_MISMATCH"
    ):
        build_v2_historical_evaluation_authority(replace(dataset, train_content_sha256="0" * 64))
    with pytest.raises(
        LocalEngineeringContractError, match="SOURCE_002_V2_PARTITION_IDENTITY_MISMATCH"
    ):
        build_v2_historical_evaluation_authority(replace(dataset, test_row_count=1))


def test_test_partition_not_read(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[str] = []
    original_open = gzip.open

    def recording_open(filename: Any, *args: Any, **kwargs: Any) -> Any:
        opened.append(Path(filename).name)
        return original_open(filename, *args, **kwargs)

    monkeypatch.setattr(gzip, "open", recording_open)
    dataset = load_frozen_engineering_dataset(REPO_ROOT)
    assert sorted(opened) == ["train.content.gz", "validation.content.gz"]
    assert dataset.test_row_count == 0
    assert "test.content.gz" not in opened


def test_historical_cutoff_is_deterministic(
    authority: local_engineering.V2HistoricalEvaluationAuthority,
) -> None:
    expected = max(row.harvest_business_date for row in authority.train_rows)
    validation_start = min(row.harvest_business_date for row in authority.validation_rows)
    assert authority.forecast_cutoff_at == expected
    assert authority.forecast_cutoff_at < validation_start
    assert authority.forecast_cutoff_at == date(2026, 1, 30)


def test_horizons_exactly_7_14_21(
    authority: local_engineering.V2HistoricalEvaluationAuthority,
) -> None:
    assert V2_FORECAST_HORIZONS == (7, 14, 21)
    assert authority.requested_forecast_horizons == (7, 14, 21)
    assert authority.observed_forecast_horizons == (7, 14, 21)
    assert {
        (row.harvest_business_date - authority.forecast_cutoff_at).days
        for row in authority.evaluation_rows
    } == {7, 14, 21}


def test_arbitrary_horizon_rejected() -> None:
    with pytest.raises(LocalEngineeringContractError, match="FORECAST_HORIZON_NOT_IN_FROZEN_SET"):
        validate_v2_forecast_horizon(38)
    with pytest.raises(LocalEngineeringContractError, match="FORECAST_HORIZON_NOT_IN_FROZEN_SET"):
        validate_v2_forecast_horizon(True)


def test_validation_target_not_used_for_fitting(
    authority: local_engineering.V2HistoricalEvaluationAuthority,
) -> None:
    training = v2_training_rows(authority)
    assert training is authority.train_rows
    assert not set(training).intersection(authority.validation_rows)
    no_validation = replace(authority, validation_rows=())
    assert v2_training_rows(no_validation) is no_validation.train_rows


def test_post_cutoff_feature_rejected(
    authority: local_engineering.V2HistoricalEvaluationAuthority,
) -> None:
    with pytest.raises(LocalEngineeringContractError, match=V2_POST_CUTOFF_FEATURE_FORBIDDEN):
        validate_v2_feature_dates(
            (date.fromordinal(authority.forecast_cutoff_at.toordinal() + 1),),
            forecast_cutoff_at=authority.forecast_cutoff_at,
        )
    validate_v2_feature_dates(
        (authority.forecast_cutoff_at,),
        forecast_cutoff_at=authority.forecast_cutoff_at,
    )


def test_candidate_parameter_must_reach_prediction_path() -> None:
    audit = _audit_by_id()
    assert audit[V2_CANDIDATE_01_ID].parameter_reaches_prediction_math is True
    assert audit[V2_CANDIDATE_01_ID].parameter_change_can_change_prediction is True
    assert audit[V2_CANDIDATE_02_ID].parameter_reaches_prediction_math is False
    assert audit[V2_CANDIDATE_02_ID].parameter_change_can_change_prediction is False
    assert audit[V2_CANDIDATE_04_ID].parameter_reaches_prediction_math is False


def test_candidate_using_weather_is_historical_only_ineligible() -> None:
    item = _audit_by_id()["03_phenology_offset"]
    assert item.uses_weather is True
    assert item.historical_only_input_compatible is False
    assert item.historical_only_execution_compatible is False


def test_candidate_using_plan_is_historical_only_ineligible() -> None:
    item = _audit_by_id()["03_phenology_offset"]
    assert item.uses_production_plan is True
    assert item.historical_only_execution_compatible is False


def test_c03_parameter_effect_path_is_proven_or_fail_closed() -> None:
    item = _audit_by_id()[V2_CANDIDATE_03_ID]
    assert item.parameter_or_feature_path == ("offset.maximum_abs_shift_days",)
    assert item.parameter_reaches_prediction_math is True
    assert item.v2_historical_only_scoring_path_exists is False
    assert item.current_v0_3_execution_eligible is False
    assert item.reason_code == "C03_NO_SOURCE_002_ONLY_SCORING_PATH"


def test_preflight_creates_no_started_event(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_called(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("V2 readiness must not invoke a scorer")

    monkeypatch.setattr(local_engineering, "run_local_replay", fail_if_called)
    readiness = build_v2_historical_only_readiness()
    assert readiness.started_event_created is False
    assert readiness.validation_scoring_performed is False
    assert readiness.test_accessed is False


def test_budget_remains_4_consumed_28_remaining() -> None:
    readiness = build_v2_historical_only_readiness()
    assert V2_LEGACY_RECONCILED_VALIDATION_DEBIT == 4
    assert V2_CANONICAL_STARTED_COUNT == 0
    assert V2_EFFECTIVE_CONSUMED == 4
    assert V2_REMAINING_VALIDATION_EVALUATIONS == 28
    assert readiness.legacy_reconciled_validation_debit == 4
    assert readiness.canonical_started_count == 0
    assert readiness.effective_consumed == 4
    assert readiness.remaining == 28


def test_v2_authority_identity_fields_are_all_sha256(
    authority: local_engineering.V2HistoricalEvaluationAuthority,
) -> None:
    identities = dict(authority.identity_values())
    identities["materialized_dataset_identity"] = authority.materialized_dataset_identity_sha256
    assert len(identities) == 8
    assert all(
        len(value) == 64
        and value == value.lower()
        and all(char in "0123456789abcdef" for char in value)
        for value in identities.values()
    )


def test_sparse_targets_not_complete_window(
    authority: local_engineering.V2HistoricalEvaluationAuthority,
) -> None:
    assert authority.evaluation_row_count == 688
    assert authority.complete_window_authority is None
    availability = v2_guardrail_metric_availability()
    assert availability["cumulative_absolute_error_kg"] == V2_COMPLETE_WINDOW_METRICS_UNAVAILABLE
    assert availability["single_day_peak_quantity_absolute_error_kg_q"] == (
        V2_COMPLETE_WINDOW_METRICS_UNAVAILABLE
    )
    assert availability["sustained_7day_quantity_absolute_error_kg_q"] == (
        V2_COMPLETE_WINDOW_METRICS_UNAVAILABLE
    )


def test_c02_quantile_path_is_metric_only() -> None:
    item = _audit_by_id()[V2_CANDIDATE_02_ID]
    assert item.actual_execution_function == (
        "backend.app.forecast_quality.quantile_coverage.compute_upper_quantile_coverage",
    )
    assert item.parameter_reaches_prediction_math is False
    assert item.v2_historical_only_scoring_path_exists is False
    assert "S3_BINDING_FORECAST_ROWS" in item.actual_data_sources_read


def test_candidate_audit_has_exact_six_entries() -> None:
    audit = build_v2_candidate_compatibility_audit()
    assert len(audit) == 6
    assert tuple(item.candidate_id for item in audit) == V2_CANDIDATE_AUDIT_ORDER
    assert {item.candidate_id for item in audit} == {
        "01_parameter_calibration",
        "02_quantile_calibration",
        "03_phenology_offset",
        "04_yield_parameter",
        "05_marketable_rate",
        "07_harvest_efficiency",
    }


def test_next_executable_candidate_is_none() -> None:
    readiness = build_v2_historical_only_readiness()
    assert readiness.next_executable_candidate == "NONE"
    assert all(item.current_v0_3_execution_eligible is False for item in readiness.candidate_audit)


def _baseline_row(index: int, quantity: str) -> FarmTotalDatasetRow:
    harvest_date = date(2025, 9, 1 + index)
    return FarmTotalDatasetRow(
        season_business_key="2025~2026",
        baseline_farm_group_key="group-a",
        harvest_business_date=harvest_date,
        partition="TRAIN",
        area_mu=Decimal("100"),
        area_authority_class=AREA_AUTHORITY_CLASS_PREVIOUS_SEASON_PROXY,
        actual_harvest_quantity_kg=Decimal(quantity),
        actual_harvest_kg_per_mu=Decimal(quantity) / Decimal("100"),
        source_actual_row_count=1,
        source_farm_business_keys=("farm-a",),
        area_authority_row_hash=f"area-{index}",
        actual_projection_hash=f"projection-{index}",
        row_hash=f"row-{index}",
    )


def test_farm_total_baseline_is_train_only_median_reference() -> None:
    rows = tuple(
        _baseline_row(index, quantity)
        for index, quantity in enumerate(("1", "2", "9", "10", "100"))
    )
    partition = FarmTotalPartitionDataset(
        partition="TRAIN",
        schema_version="test-schema",
        rows=rows,
        dataset_sha256=compute_partition_dataset_sha256(rows),
    )
    diagnostics = FarmTotalDatasetDiagnostics(
        partition="TRAIN",
        farm_group_count=1,
        date_count=5,
        row_count=5,
        total_area_mu="100",
        total_actual_harvest_kg="122",
        kg_per_mu_min=None,
        kg_per_mu_p25=None,
        kg_per_mu_median=None,
        kg_per_mu_p75=None,
        kg_per_mu_max=None,
    )
    state = derive_farm_total_baseline_estimator(
        FarmTotalTrainingDataset(partition_dataset=partition, diagnostics=diagnostics)
    )
    estimate = state.group_estimates[0]
    assert estimate.status is FarmTotalBaselineGroupStatus.READY
    assert estimate.baseline_harvest_quantity_kg == Decimal("9")


def test_v2_authority_payload_is_row_free(
    authority: local_engineering.V2HistoricalEvaluationAuthority,
) -> None:
    payload = authority.payload()
    assert "train_rows" not in payload
    assert "validation_rows" not in payload
    assert "evaluation_rows" not in payload
    assert payload["test_remains_sealed"] is True


def test_incomplete_horizon_error_is_closed() -> None:
    assert V2_HISTORICAL_HORIZON_SET_INCOMPLETE == "V2_HISTORICAL_HORIZON_SET_INCOMPLETE"
    assert "V2_HISTORICAL_HORIZON_SET_INCOMPLETE" in inspect.getsource(
        local_engineering._v2_target_rows
    )


def test_v2_flags_bind_historical_only_policy() -> None:
    readiness = build_v2_historical_only_readiness()
    assert readiness.experiment_plan_version == EXPERIMENT_PLAN_V2_VERSION
    assert readiness.experiment_plan_hash == EXPERIMENT_PLAN_V2_HASH
    assert readiness.historical_data_only is V2_HISTORICAL_DATA_ONLY is True
    assert readiness.weather_required is False
    assert readiness.production_plan_required is False
    assert readiness.task8_task9_required is False
    assert readiness.prospective_capture_required is False
    assert readiness.test_remains_sealed is V2_TEST_REMAINS_SEALED is True


def test_v2_authority_replay_is_deterministic() -> None:
    first = build_v2_historical_only_authority(REPO_ROOT)
    second = build_v2_historical_only_authority(REPO_ROOT)
    assert first.payload() == second.payload()
    assert first.identity_values() == second.identity_values()
