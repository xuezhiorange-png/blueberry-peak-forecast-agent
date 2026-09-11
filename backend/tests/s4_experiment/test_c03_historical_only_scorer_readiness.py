"""Fail-closed C03 canonical shift-model equivalence tests."""

from __future__ import annotations

import hashlib
import inspect
from dataclasses import replace
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

import backend.app.s4_candidate_03_historical_phenology as c03
from backend.app.s4_experiment import (
    EXPERIMENT_PLAN_V2_HASH,
    EXPERIMENT_PLAN_V2_VERSION,
    V2_GUARDRAIL_POLICY_HASH,
    V2_GUARDRAIL_POLICY_VERSION,
)
from backend.app.s4_v2_historical_only_execution import (
    V2_CANDIDATE_03_ID,
    V2_CANDIDATE_04_ID,
    V2CandidateCompatibility,
    build_v2_candidate_compatibility_audit,
    build_v2_historical_only_readiness,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO_ROOT / "configs/maturity_curve.yaml"


def _identity(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _authority() -> SimpleNamespace:
    return SimpleNamespace(
        source_id="SOURCE_002",
        materialized_dataset_identity_sha256=c03.C03_MATERIALIZED_DATASET_IDENTITY,
        train_dataset_identity=c03.C03_TRAIN_DATASET_IDENTITY,
        validation_dataset_identity=c03.C03_VALIDATION_DATASET_IDENTITY,
        actual_label_set_identity=_identity("source-002-labels"),
        cutoff_policy_identity=_identity("source-002-cutoff"),
        forecast_horizon_set_identity=_identity("source-002-horizons"),
        business_grain_set_identity=_identity("source-002-grain"),
        common_comparable_set_identity=_identity("source-002-comparable"),
        forecast_cutoff_at=date(2026, 1, 30),
        requested_forecast_horizons=c03.C03_FORECAST_HORIZONS,
        observed_forecast_horizons=c03.C03_FORECAST_HORIZONS,
        train_row_count=c03.C03_TRAIN_ROWS,
        validation_row_count=c03.C03_VALIDATION_ROWS,
        evaluation_row_count=688,
        test_remains_sealed=True,
    )


def _manifest() -> c03.C03HistoricalParameterManifest:
    return c03.build_c03_historical_only_manifest(
        authority=_authority(),
        config_path=CONFIG_PATH,
        code_commit_binding="a" * 40,
    )


def _audit_by_id() -> dict[str, V2CandidateCompatibility]:
    return {item.candidate_id: item for item in build_v2_candidate_compatibility_audit()}


def test_c03_owner_semantic_preserved() -> None:
    manifest = _manifest()
    assert manifest.semantic_authority_decision_id == c03.C03_OWNER_DECISION_ID
    assert manifest.semantic_authority == "TRAINING_TIME_LEARNED_SHIFT_MODEL_BOUND"
    assert manifest.allowed_parameter_paths == ("offset.maximum_abs_shift_days",)
    assert manifest.explicitly_excluded_parameter_paths == (
        "forecast.observed_phase_adjustment_max_days",
    )


def test_c03_canonical_shift_trainer_identity_is_shared_with_production() -> None:
    audit = c03.audit_c03_canonical_training_inputs()
    assert audit.production_training_path == "backend.app.maturity.service.train_maturity_curve"
    assert audit.production_shift_builder_path == "backend.app.maturity.service._build_shift_model"
    assert (
        audit.production_shift_predictor_path == "backend.app.maturity.service._predict_shift_days"
    )
    assert audit.production_forecast_path == (
        "backend.app.maturity.service.forecast_natural_maturity"
    )
    builder_source = (REPO_ROOT / "backend/app/maturity/service.py").read_text(encoding="utf-8")
    assert "observed_peak" in builder_source
    assert "parent_artifact.peak_day" in builder_source


def test_c03_canonical_training_required_features_are_audited() -> None:
    audit = c03.audit_c03_canonical_training_inputs()
    assert audit.required_training_features == (
        "altitude_m",
        "tree_age_years",
        "pruning_offset_days",
        "flowering_peak_offset_days",
        "first_pick_offset_days",
        "facility_type",
    )
    assert audit.shift_target_definition == "observed_peak_day - parent_curve_artifact.peak_day"
    assert audit.forward_looking_authority_domains == (
        "analytics_build_run",
        "production_plan",
        "location_reference",
        "base_temperature_search",
        "weather_mapping_and_observations",
    )


def test_c03_source002_missing_canonical_inputs_blocks() -> None:
    audit = c03.audit_c03_canonical_training_inputs()
    assert audit.source002_can_supply_canonical_inputs is False
    assert audit.separable_from_forward_looking_authority is False
    assert audit.reason_code == c03.C03_CANONICAL_SHIFT_MODEL_BLOCKER
    assert set(audit.missing_source002_inputs) == set(audit.required_training_inputs)
    assert "actual_harvest_quantity_kg" in audit.source002_materializable_fields
    assert "parent_curve_artifact.peak_day" not in audit.source002_materializable_fields


def test_c03_production_training_sample_resolves_forward_authorities() -> None:
    source = (REPO_ROOT / "backend/app/maturity/service.py").read_text(encoding="utf-8")
    for token in (
        "load_production_plan_config",
        "FarmSeasonVarietyPlan",
        "resolve_weather_mapping",
        "location_reference",
        "base_temperature",
        "feature_values",
    ):
        assert token in source


def test_c03_does_not_replace_production_ridge_shift_with_group_peak_delta() -> None:
    assert c03.C03_NON_CANONICAL_PROTOTYPE_STATUS == "NON_CANONICAL_EXPERIMENTAL_PROTOTYPE"
    assert c03.C03_NON_CANONICAL_PROTOTYPE_IS_EXECUTION_AUTHORITY is False
    assert c03.C03_NON_CANONICAL_PROTOTYPE_PATH.endswith(
        "C03HistoricalPhenologyScorer.predict_rows"
    )
    with pytest.raises(
        c03.C03HistoricalPhenologyError,
        match=c03.C03_CANONICAL_SHIFT_MODEL_BLOCKER,
    ):
        c03.build_c03_historical_phenology_scorer(
            authority=_authority(),
            config_path=CONFIG_PATH,
        )


def test_c03_authority_bound_prototype_constructor_fails_closed() -> None:
    with pytest.raises(
        c03.C03HistoricalPhenologyError,
        match=c03.C03_CANONICAL_SHIFT_MODEL_BLOCKER,
    ):
        c03.C03HistoricalPhenologyScorer.from_v2_authority(
            _authority(),
            object(),  # type: ignore[arg-type]
        )


def test_c03_manifest_is_prepared_but_not_an_execution_authority() -> None:
    manifest = _manifest()
    assert manifest.version == "v0.3-s4-c03-phenology-offset-manifest-v2-historical-only"
    assert manifest.manifest_hash == _manifest().manifest_hash
    assert c03.C03_HISTORICAL_ONLY_SCORING_PATH_EXISTS is False
    assert c03.C03_PARAMETER_REACHES_PREDICTION_MATH is False
    assert c03.C03_PARAMETER_CHANGE_CAN_CHANGE_PREDICTION is False
    assert c03.C03_CANONICAL_PARAMETER_CHANGE_STATUS == "NOT_PROVEN"


def test_c03_v2_manifest_does_not_reuse_v1() -> None:
    forged = replace(_manifest(), version="v0.3-s4-c03-phenology-offset-manifest-v1")
    with pytest.raises(c03.C03HistoricalPhenologyError, match="C03_V1_MANIFEST"):
        c03.validate_c03_historical_only_manifest(forged)


def test_c03_v4_gate_is_identity_checked_then_fail_closed() -> None:
    request = c03.build_c03_v4_gate_request(
        manifest=_manifest(),
        candidate_run_ordinal=1,
        code_commit_sha="b" * 40,
        evaluation_id="c03-canonical-audit-r2",
    )
    result = c03.check_c03_v4_gate(request)
    assert result.allowed is False
    assert result.reason_codes == (c03.C03_CANONICAL_SHIFT_MODEL_BLOCKER,)
    assert request.experiment_plan_version == EXPERIMENT_PLAN_V2_VERSION
    assert request.experiment_plan_hash == EXPERIMENT_PLAN_V2_HASH
    assert request.guardrail_policy_version == c03.V4_GUARDRAIL_POLICY_VERSION
    assert request.guardrail_policy_hash == c03.V4_GUARDRAIL_POLICY_HASH


def test_c03_plan_eligibility_is_distinct_from_current_runnability() -> None:
    item = _audit_by_id()[V2_CANDIDATE_03_ID]
    assert item.current_v0_3_execution_eligible is True
    assert item.v2_historical_only_scoring_path_exists is False
    assert item.historical_only_execution_compatible is False
    assert item.currently_runnable_under_v4 is False
    assert item.reason_code == c03.C03_CANONICAL_SHIFT_MODEL_BLOCKER
    assert item.parameter_reaches_prediction_math is False
    assert item.parameter_change_can_change_prediction is False
    assert item.uses_weather is True
    assert item.uses_production_plan is True
    assert item.uses_other_forward_looking_authority is True


def test_c04_plan_eligibility_remains_true_separately() -> None:
    item = _audit_by_id()[V2_CANDIDATE_04_ID]
    assert item.current_v0_3_execution_eligible is True
    assert item.historical_only_execution_compatible is True
    assert item.currently_runnable_under_v4 is False
    assert item.reason_code == "C04_EXHAUSTED_EVIDENCE_INSUFFICIENT"


def test_v2_readiness_has_no_current_executable_candidate() -> None:
    readiness = build_v2_historical_only_readiness()
    assert readiness.next_executable_candidate == "NONE"
    assert readiness.started_event_created is False
    assert readiness.validation_scoring_performed is False
    assert readiness.test_accessed is False


def test_c03_readiness_has_no_durable_execution_path() -> None:
    source = inspect.getsource(c03)
    assert "S4CandidateExecutionAuthority" not in source
    assert ".execute(" not in source
    assert "s4_validation_budget" not in source


def test_c03_budget_facts_remain_8_24() -> None:
    readiness = build_v2_historical_only_readiness()
    assert readiness.budget_snapshot_canonical_started_count == 0
    assert readiness.budget_snapshot_effective_consumed == 4
    assert readiness.budget_snapshot_remaining == 28


def test_c03_test_remains_sealed() -> None:
    assert c03.C03_TEST_REMAINS_SEALED is True
    assert c03.C03_USES_PROSPECTIVE_CAPTURE is False
    assert c03.C03_USES_WALL_CLOCK_WAIT is False


def test_frozen_v2_plan_and_candidate_eligibility_are_not_rewritten() -> None:
    audit = _audit_by_id()
    eligible = {
        item.candidate_id for item in audit.values() if item.current_v0_3_execution_eligible
    }
    assert eligible == {
        "01_parameter_calibration",
        "02_quantile_calibration",
        "03_phenology_offset",
        "04_yield_parameter",
        "05_marketable_rate",
        "07_harvest_efficiency",
    }
    assert V2_GUARDRAIL_POLICY_VERSION == "v0.3-s4-guardrail-policy-v2"
    assert V2_GUARDRAIL_POLICY_HASH == (
        "65ad056b3085b7ff41d25e1a7a86b990ac0f837270d62f6fd84ce5938843c793"
    )
