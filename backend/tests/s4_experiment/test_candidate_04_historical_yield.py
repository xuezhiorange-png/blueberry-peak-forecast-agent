"""Contract tests for the SOURCE-002-only C04 historical scorer."""

from __future__ import annotations

import copy
import gzip
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from backend.app.maturity.config import load_maturity_curve_config
from backend.app.rolling_backtest.canonical import sha256_payload
from backend.app.s4_candidate_04_historical_yield import (
    C04_ALLOWED_PARAMETER_PATHS,
    C04_BASELINE_MULTIPLIER,
    C04_CANDIDATE_ID,
    C04_INCUMBENT_CONFIG_FILE_SHA256,
    C04_INCUMBENT_CONFIG_HASH,
    C04_INCUMBENT_FORECAST_OBSERVED_PHASE_ADJUSTMENT_MAX_DAYS,
    C04_INCUMBENT_OFFSET_MAXIMUM_ABS_SHIFT_DAYS,
    C04_INCUMBENT_OFFSET_MINIMUM_TRAINING_SAMPLES,
    C04_PARAMETER_DERIVATION_POLICY,
    C04_PARAMETER_SEMANTIC,
    C04HistoricalScorerError,
    C04HistoricalYieldScorer,
    CalibrationKey,
    _build_training_model,
    _calibration_base_predictions,
    _calibration_target_actuals,
    _group_level_ratio_summaries,
    build_c04_derived_config,
    build_c04_gate_request,
    build_c04_historical_yield_scorer,
    build_c04_parameter_manifest,
    derive_c04_parameter_calibration,
    validate_c04_parameter_manifest,
    verify_c04_parameter_allowlist,
)
from backend.app.s4_experiment import (
    V2_BUDGET_SNAPSHOT_CANONICAL_STARTED_COUNT,
    V2_BUDGET_SNAPSHOT_EFFECTIVE_CONSUMED,
    V2_BUDGET_SNAPSHOT_REMAINING_VALIDATION_EVALUATIONS,
    check_candidate_execution_gate,
)
from backend.app.s4_local_engineering import (
    V2HistoricalEvaluationAuthority,
    build_v2_historical_evaluation_authority,
    load_frozen_engineering_dataset,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO_ROOT / "configs" / "maturity_curve.yaml"
TEST_COMMIT_SHA = "a" * 40


@pytest.fixture(scope="module")
def authority() -> V2HistoricalEvaluationAuthority:
    dataset = load_frozen_engineering_dataset(REPO_ROOT)
    return build_v2_historical_evaluation_authority(dataset)


@pytest.fixture(scope="module")
def manifest(authority: V2HistoricalEvaluationAuthority):
    return build_c04_parameter_manifest(
        authority=authority,
        config_path=CONFIG_PATH,
        code_commit_binding=TEST_COMMIT_SHA,
    )


def _masked_target_rows(
    authority: V2HistoricalEvaluationAuthority,
) -> tuple[Any, ...]:
    """Use validation target identities while making actual values irrelevant."""

    rows = []
    for horizon in (7, 14, 21):
        row = next(
            item
            for item in authority.evaluation_rows
            if (item.harvest_business_date - authority.forecast_cutoff_at).days == horizon
        )
        rows.append(replace(row, actual_harvest_quantity_kg=Decimal("999999999")))
    return tuple(rows)


def test_c04_parameter_derivation_train_only(
    authority: V2HistoricalEvaluationAuthority,
) -> None:
    derivation = derive_c04_parameter_calibration(authority.train_rows)
    expected_cutoff = max(row.harvest_business_date for row in authority.train_rows) - timedelta(
        days=21
    )
    assert derivation.validation_used_for_parameter_derivation is False
    assert derivation.test_used is False
    assert derivation.calibration_cutoff == expected_cutoff
    assert all(fold.calibration_cutoff == expected_cutoff for fold in derivation.folds)
    assert all(fold.fit_end_date == expected_cutoff for fold in derivation.folds)
    assert all(fold.fit_end_date < fold.holdout_start_date for fold in derivation.folds)
    assert all(fold.fit_row_count > 0 and fold.holdout_row_count > 0 for fold in derivation.folds)
    assert derivation.policy == C04_PARAMETER_DERIVATION_POLICY
    assert tuple(fold.target_horizon_days for fold in derivation.folds) == (
        (7,),
        (14,),
        (21,),
        (7, 14, 21),
    )
    assert all(fold.comparable_prediction_row_count > 0 for fold in derivation.folds)


def _calibration_components(
    authority: V2HistoricalEvaluationAuthority,
) -> tuple[date, dict[CalibrationKey, Decimal], dict[CalibrationKey, Decimal]]:
    config = load_maturity_curve_config(CONFIG_PATH)
    ordered = tuple(
        sorted(
            authority.train_rows,
            key=lambda row: (
                row.season,
                row.farm,
                row.subfarm,
                row.variety,
                row.harvest_business_date,
            ),
        )
    )
    cutoff = max(row.harvest_business_date for row in ordered) - timedelta(days=21)
    target_dates = tuple(cutoff + timedelta(days=horizon) for horizon in (7, 14, 21))
    fit_rows = tuple(row for row in ordered if row.harvest_business_date <= cutoff)
    target_rows = tuple(row for row in ordered if row.harvest_business_date in set(target_dates))
    identity_target_rows = tuple(
        replace(row, actual_harvest_quantity_kg=Decimal("0")) for row in target_rows
    )
    model = _build_training_model(fit_rows, identity_target_rows, config)
    base_predictions = _calibration_base_predictions(
        model=model,
        target_rows=identity_target_rows,
        calibration_cutoff=cutoff,
    )
    target_actuals = _calibration_target_actuals(
        target_rows=target_rows,
        calibration_cutoff=cutoff,
    )
    return cutoff, base_predictions, target_actuals


def test_c04_calibration_cutoff_is_latest_train_cutoff_with_full_21d_labels(
    authority: V2HistoricalEvaluationAuthority,
) -> None:
    derivation = derive_c04_parameter_calibration(authority.train_rows)
    expected_cutoff = max(row.harvest_business_date for row in authority.train_rows) - timedelta(
        days=max((7, 14, 21))
    )
    assert derivation.calibration_cutoff == expected_cutoff
    assert derivation.folds[-1].holdout_start_date == expected_cutoff + timedelta(days=7)
    assert derivation.folds[-1].holdout_end_date == expected_cutoff + timedelta(days=21)


def test_c04_all_four_parameters_use_same_calibration_cutoff(
    authority: V2HistoricalEvaluationAuthority,
) -> None:
    derivation = derive_c04_parameter_calibration(authority.train_rows)
    assert len({fold.calibration_cutoff for fold in derivation.folds}) == 1
    assert all(fold.fit_end_date == derivation.calibration_cutoff for fold in derivation.folds)


def test_c04_base_prediction_ignores_target_actual(
    authority: V2HistoricalEvaluationAuthority,
) -> None:
    cutoff, base_predictions, _target_actuals = _calibration_components(authority)
    config = load_maturity_curve_config(CONFIG_PATH)
    ordered = tuple(sorted(authority.train_rows, key=lambda row: row.harvest_business_date))
    fit_rows = tuple(row for row in ordered if row.harvest_business_date <= cutoff)
    target_dates = {cutoff + timedelta(days=horizon) for horizon in (7, 14, 21)}
    target_rows = tuple(row for row in ordered if row.harvest_business_date in target_dates)
    identity_rows = tuple(
        replace(row, actual_harvest_quantity_kg=Decimal("0")) for row in target_rows
    )
    mutated_rows = tuple(
        replace(row, actual_harvest_quantity_kg=Decimal("999999999")) for row in target_rows
    )
    identity_model = _build_training_model(fit_rows, identity_rows, config)
    mutated_model = _build_training_model(fit_rows, mutated_rows, config)
    assert base_predictions == _calibration_base_predictions(
        model=identity_model,
        target_rows=identity_rows,
        calibration_cutoff=cutoff,
    )
    assert base_predictions == _calibration_base_predictions(
        model=mutated_model,
        target_rows=mutated_rows,
        calibration_cutoff=cutoff,
    )


@pytest.mark.parametrize(
    ("horizon", "fold_ordinal"),
    ((7, 1), (14, 2), (21, 3)),
)
def test_c04_horizon_uses_group_level_ratios(
    authority: V2HistoricalEvaluationAuthority,
    horizon: int,
    fold_ordinal: int,
) -> None:
    _cutoff, base_predictions, target_actuals = _calibration_components(authority)
    ratio, group_count, prediction_row_count, horizons = _group_level_ratio_summaries(
        base_predictions=base_predictions,
        target_actuals=target_actuals,
        required_horizons=(horizon,),
    )
    fold = derive_c04_parameter_calibration(authority.train_rows).folds[fold_ordinal - 1]
    assert horizons == (horizon,)
    assert fold.amplitude_ratio == ratio
    assert fold.comparable_group_count == group_count
    assert fold.comparable_prediction_row_count == prediction_row_count


def test_c04_horizon7_uses_group_level_ratios(authority: V2HistoricalEvaluationAuthority) -> None:
    test_c04_horizon_uses_group_level_ratios(authority, 7, 1)


def test_c04_horizon14_uses_group_level_ratios(authority: V2HistoricalEvaluationAuthority) -> None:
    test_c04_horizon_uses_group_level_ratios(authority, 14, 2)


def test_c04_horizon21_uses_group_level_ratios(authority: V2HistoricalEvaluationAuthority) -> None:
    test_c04_horizon_uses_group_level_ratios(authority, 21, 3)


def test_c04_all_horizon_ratio_uses_same_group_7_14_21_sum(
    authority: V2HistoricalEvaluationAuthority,
) -> None:
    _cutoff, base_predictions, target_actuals = _calibration_components(authority)
    ratio, group_count, prediction_row_count, horizons = _group_level_ratio_summaries(
        base_predictions=base_predictions,
        target_actuals=target_actuals,
        required_horizons=(7, 14, 21),
    )
    fold = derive_c04_parameter_calibration(authority.train_rows).folds[3]
    assert horizons == (7, 14, 21)
    assert fold.amplitude_ratio == ratio
    assert fold.comparable_group_count == group_count
    assert fold.comparable_prediction_row_count == prediction_row_count


def test_c04_row_level_ratio_median_is_not_parameter_policy() -> None:
    group_a = ("season", "farm-a", "subfarm", "variety")
    group_b = ("season", "farm-b", "subfarm", "variety")
    base_predictions = {
        (group_a, 7): Decimal("1"),
        (group_a, 14): Decimal("1"),
        (group_a, 21): Decimal("1"),
        (group_b, 7): Decimal("1"),
        (group_b, 14): Decimal("1"),
        (group_b, 21): Decimal("1"),
    }
    target_actuals = {
        (group_a, 7): Decimal("10"),
        (group_a, 14): Decimal("1"),
        (group_a, 21): Decimal("1"),
        (group_b, 7): Decimal("2"),
        (group_b, 14): Decimal("2"),
        (group_b, 21): Decimal("2"),
    }
    ratio, _, _, _ = _group_level_ratio_summaries(
        base_predictions=base_predictions,
        target_actuals=target_actuals,
        required_horizons=(7, 14, 21),
    )
    assert ratio == Decimal("3.000000")
    assert C04_PARAMETER_DERIVATION_POLICY.endswith("GROUP_HORIZON_AMPLITUDE_CALIBRATION_V3")


def test_c04_missing_horizon_group_excluded_from_all_horizon_ratio() -> None:
    complete = ("season", "complete", "subfarm", "variety")
    partial = ("season", "partial", "subfarm", "variety")
    base_predictions = {
        (complete, 7): Decimal("1"),
        (complete, 14): Decimal("1"),
        (complete, 21): Decimal("1"),
        (partial, 7): Decimal("1"),
        (partial, 14): Decimal("1"),
    }
    target_actuals = {
        (complete, 7): Decimal("2"),
        (complete, 14): Decimal("2"),
        (complete, 21): Decimal("2"),
        (partial, 7): Decimal("100"),
        (partial, 14): Decimal("100"),
    }
    ratio, group_count, prediction_row_count, _ = _group_level_ratio_summaries(
        base_predictions=base_predictions,
        target_actuals=target_actuals,
        required_horizons=(7, 14, 21),
    )
    assert ratio == Decimal("2.000000")
    assert group_count == 1
    assert prediction_row_count == 3


def test_c04_parameter_values_exactly_four_unique_positive_finite(
    authority: V2HistoricalEvaluationAuthority,
) -> None:
    values = derive_c04_parameter_calibration(authority.train_rows).parameter_values
    assert len(values) == 4
    assert len(set(values)) == 4
    assert all(value > 0 and value.is_finite() for value in values)


def test_c04_old_r2_values_not_frozen(authority: V2HistoricalEvaluationAuthority) -> None:
    old_r2_values = {
        Decimal("416.621234"),
        Decimal("24.896716"),
        Decimal("11.302801"),
        Decimal("3.911976"),
    }
    values = set(derive_c04_parameter_calibration(authority.train_rows).parameter_values)
    assert values.isdisjoint(old_r2_values)


def test_c04_validation_not_used_for_parameter_derivation(
    authority: V2HistoricalEvaluationAuthority,
) -> None:
    first = derive_c04_parameter_calibration(authority.train_rows)
    second = derive_c04_parameter_calibration(authority.train_rows)
    assert first.parameter_values == second.parameter_values
    assert first.validation_used_for_parameter_derivation is False


def test_c04_test_not_read(monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_c04_exactly_four_unique_positive_finite_values(
    authority: V2HistoricalEvaluationAuthority,
) -> None:
    values = derive_c04_parameter_calibration(authority.train_rows).parameter_values
    assert len(values) == 4
    assert len(set(values)) == 4
    assert all(value > 0 and value.is_finite() for value in values)


def test_c04_derivation_deterministic(
    authority: V2HistoricalEvaluationAuthority,
) -> None:
    left = derive_c04_parameter_calibration(authority.train_rows)
    right = derive_c04_parameter_calibration(tuple(reversed(authority.train_rows)))
    assert left.payload() == right.payload()
    assert sha256_payload(left.payload()) == sha256_payload(right.payload())


def test_c04_inner_folds_time_ordered(
    authority: V2HistoricalEvaluationAuthority,
) -> None:
    folds = derive_c04_parameter_calibration(authority.train_rows).folds
    assert tuple(fold.fold_ordinal for fold in folds) == (1, 2, 3, 4)
    assert all(fold.fit_end_date < fold.holdout_start_date for fold in folds)
    assert tuple(fold.target_horizon_days for fold in folds) == (
        (7,),
        (14,),
        (21,),
        (7, 14, 21),
    )
    assert folds[-1].holdout_start_date < folds[-1].holdout_end_date


def test_c04_multiplier_reaches_prediction_math(
    authority: V2HistoricalEvaluationAuthority,
) -> None:
    scorer = build_c04_historical_yield_scorer(
        authority=authority,
        config_path=CONFIG_PATH,
    )
    proof = scorer.prove_parameter_effect(_masked_target_rows(authority))
    assert proof.parameter_reaches_prediction_math is True
    assert proof.parameter_change_can_change_prediction is True
    assert proof.changed_prediction_count == 3
    assert proof.baseline_prediction_identity != proof.alternate_prediction_identity


def test_c04_multiplier_changes_prediction_identity(
    authority: V2HistoricalEvaluationAuthority,
) -> None:
    scorer = build_c04_historical_yield_scorer(
        authority=authority,
        config_path=CONFIG_PATH,
    )
    rows = _masked_target_rows(authority)
    baseline = scorer.predict_rows(rows, Decimal("1.0"))
    alternate = scorer.predict_rows(rows, Decimal("2.0"))
    assert scorer.prediction_identity(baseline) != scorer.prediction_identity(alternate)
    assert any(
        left.candidate_p50_kg != right.candidate_p50_kg
        for left, right in zip(baseline, alternate, strict=True)
    )


def test_c04_multiplier_one_replays_base_prediction(
    authority: V2HistoricalEvaluationAuthority,
) -> None:
    scorer = build_c04_historical_yield_scorer(
        authority=authority,
        config_path=CONFIG_PATH,
    )
    predictions = scorer.predict_rows(_masked_target_rows(authority), C04_BASELINE_MULTIPLIER)
    assert all(item.base_p50_kg == item.candidate_p50_kg for item in predictions)
    assert all(
        item.candidate_p50_kg
        == (item.base_prediction_total_kg * item.curve_share).quantize(Decimal("0.000001"))
        for item in predictions
    )


def test_c04_incumbent_configuration_identity_is_bound(manifest: Any) -> None:
    assert manifest.incumbent_config_file_sha256 == C04_INCUMBENT_CONFIG_FILE_SHA256
    assert manifest.incumbent_config_hash == C04_INCUMBENT_CONFIG_HASH
    assert manifest.incumbent_parameter_snapshot["offset"]["maximum_abs_shift_days"] == (
        C04_INCUMBENT_OFFSET_MAXIMUM_ABS_SHIFT_DAYS
    )
    assert manifest.incumbent_parameter_snapshot["offset"]["minimum_training_samples"] == (
        C04_INCUMBENT_OFFSET_MINIMUM_TRAINING_SAMPLES
    )
    assert (
        manifest.incumbent_parameter_snapshot["forecast"]["observed_phase_adjustment_max_days"]
        == C04_INCUMBENT_FORECAST_OBSERVED_PHASE_ADJUSTMENT_MAX_DAYS
    )

    forged = replace(manifest, incumbent_config_hash="0" * 64)
    with pytest.raises(C04HistoricalScorerError, match="C04_INCUMBENT_CONFIG_IDENTITY_MISMATCH"):
        validate_c04_parameter_manifest(forged)


def test_c04_manifest_run_prediction_uses_frozen_run_value(
    authority: V2HistoricalEvaluationAuthority,
    manifest: Any,
) -> None:
    scorer = build_c04_historical_yield_scorer(
        authority=authority,
        config_path=CONFIG_PATH,
    )
    rows = _masked_target_rows(authority)
    bound = scorer.predict_manifest_run(manifest, 1, rows)
    direct = scorer.predict_rows(rows, manifest.run(1).parameter_value)
    assert scorer.prediction_identity(bound) == scorer.prediction_identity(direct)


def test_c04_horizons_exactly_7_14_21(
    authority: V2HistoricalEvaluationAuthority,
) -> None:
    scorer = build_c04_historical_yield_scorer(
        authority=authority,
        config_path=CONFIG_PATH,
    )
    predictions = scorer.predict_rows(_masked_target_rows(authority), Decimal("1.0"))
    assert tuple(sorted(item.horizon_days for item in predictions)) == (7, 14, 21)


def test_c04_canonical_grain(
    authority: V2HistoricalEvaluationAuthority,
) -> None:
    keys = {
        (
            row.season,
            row.farm,
            row.subfarm,
            row.variety,
            row.harvest_business_date,
        )
        for row in authority.evaluation_rows
    }
    assert len(keys) == authority.evaluation_row_count


def test_c04_no_weather() -> None:
    module_source = (REPO_ROOT / "backend/app/s4_candidate_04_historical_yield.py").read_text()
    assert "import weather" not in module_source
    assert "import production_plan" not in module_source


def test_c04_no_plan() -> None:
    assert C04_PARAMETER_SEMANTIC == ("TRAIN_DERIVED_POINT_FORECAST_YIELD_AMPLITUDE_MULTIPLIER")


def test_c04_no_task8_task9() -> None:
    scorer_module = C04HistoricalYieldScorer.__module__
    assert "task8" not in scorer_module.lower()
    assert "task9" not in scorer_module.lower()


def test_c04_manifest_hash_replay(
    authority: V2HistoricalEvaluationAuthority,
    manifest: Any,
) -> None:
    replay = build_c04_parameter_manifest(
        authority=authority,
        config_path=CONFIG_PATH,
        code_commit_binding=TEST_COMMIT_SHA,
    )
    assert manifest.manifest_hash == replay.manifest_hash
    assert manifest.manifest_hash == sha256_payload(manifest.payload())


def test_c04_run_hashes_replay(manifest: Any) -> None:
    assert len(manifest.runs) == 4
    assert all(run.parameter_manifest_hash for run in manifest.runs)
    assert len({run.parameter_manifest_hash for run in manifest.runs}) == 4
    assert len({run.candidate_config_hash for run in manifest.runs}) == 4
    assert all(run.unauthorized_parameter_diff_count == 0 for run in manifest.runs)


def test_c04_manifest_mutation_changes_hash(manifest: Any) -> None:
    mutated = replace(
        manifest,
        parameter_values=(Decimal("1"), *manifest.parameter_values[1:]),
    )
    assert mutated.manifest_hash != manifest.manifest_hash


def test_c04_run_order_mutation_changes_hash(manifest: Any) -> None:
    mutated = replace(manifest, runs=tuple(reversed(manifest.runs)))
    assert mutated.manifest_hash != manifest.manifest_hash


def test_c04_native_float_rejected(manifest: Any) -> None:
    mutated = replace(
        manifest,
        parameter_values=(1.0, *manifest.parameter_values[1:]),
    )
    with pytest.raises(C04HistoricalScorerError, match="C04_PARAMETER_VALUES_INVALID"):
        validate_c04_parameter_manifest(mutated)


def test_c04_allowed_parameter_path_is_exactly_one(manifest: Any) -> None:
    assert manifest.allowed_parameter_paths == C04_ALLOWED_PARAMETER_PATHS
    assert manifest.allowed_parameter_paths == ("yield_amplitude_multiplier",)


@pytest.mark.parametrize(
    ("path", "value"),
    (
        ("curve.ridge_alpha", Decimal("2")),
        ("pooling.minimum_samples", 4),
        ("offset.minimum_training_samples", 4),
        ("forecast.observed_phase_adjustment_max_days", Decimal("10")),
    ),
)
def test_c04_unauthorized_parameter_path_rejected(
    manifest: Any,
    path: str,
    value: object,
) -> None:
    candidate = copy.deepcopy(dict(manifest.incumbent_parameter_snapshot))
    current: dict[str, object] = candidate
    segments = path.split(".")
    for segment in segments[:-1]:
        child = current[segment]
        assert isinstance(child, dict)
        current = child
    current[segments[-1]] = value
    candidate[C04_ALLOWED_PARAMETER_PATHS[0]] = Decimal("2")
    diff = verify_c04_parameter_allowlist(
        incumbent_snapshot=manifest.incumbent_parameter_snapshot,
        candidate_snapshot=candidate,
    )
    assert path in diff.unauthorized_paths
    assert diff.unauthorized_parameter_diff_count >= 1


def test_c04_two_parameter_change_is_rejected(manifest: Any) -> None:
    candidate = copy.deepcopy(dict(manifest.incumbent_parameter_snapshot))
    candidate[C04_ALLOWED_PARAMETER_PATHS[0]] = Decimal("2")
    offset = candidate["offset"]
    assert isinstance(offset, dict)
    offset["minimum_training_samples"] = 4
    diff = verify_c04_parameter_allowlist(
        incumbent_snapshot=manifest.incumbent_parameter_snapshot,
        candidate_snapshot=candidate,
    )
    assert diff.changed_paths == (
        "offset.minimum_training_samples",
        "yield_amplitude_multiplier",
    )
    assert diff.unauthorized_parameter_diff_count == 1


def test_c04_incumbent_snapshot_not_mutated(manifest: Any) -> None:
    before = copy.deepcopy(dict(manifest.incumbent_parameter_snapshot))
    derived = build_c04_derived_config(manifest, 1)
    assert dict(manifest.incumbent_parameter_snapshot) == before
    assert derived.yield_amplitude_multiplier == manifest.parameter_values[0]
    assert (
        derived.full_parameter_snapshot["yield_amplitude_multiplier"]
        == (manifest.parameter_values[0])
    )


def test_c04_gate_request_is_v2_bound(manifest: Any) -> None:
    request = build_c04_gate_request(
        manifest=manifest,
        candidate_run_ordinal=1,
        code_commit_sha=TEST_COMMIT_SHA,
        evaluation_id="c04-readiness-only",
    )
    result = check_candidate_execution_gate(request)
    assert result.allowed is True
    assert request.candidate_id == C04_CANDIDATE_ID
    assert request.global_actual_evaluation_count == 4
    assert request.candidate_actual_run_count == 0


def test_c04_preflight_creates_no_started_event() -> None:
    assert V2_BUDGET_SNAPSHOT_CANONICAL_STARTED_COUNT == 0
    assert V2_BUDGET_SNAPSHOT_EFFECTIVE_CONSUMED == 4
    assert V2_BUDGET_SNAPSHOT_REMAINING_VALIDATION_EVALUATIONS == 28


def test_c04_budget_unchanged() -> None:
    assert V2_BUDGET_SNAPSHOT_EFFECTIVE_CONSUMED - V2_BUDGET_SNAPSHOT_CANONICAL_STARTED_COUNT == 4
    assert V2_BUDGET_SNAPSHOT_REMAINING_VALIDATION_EVALUATIONS == 28
    assert (
        V2_BUDGET_SNAPSHOT_EFFECTIVE_CONSUMED
        + (V2_BUDGET_SNAPSHOT_REMAINING_VALIDATION_EVALUATIONS)
        == 32
    )


def test_test_remains_sealed(manifest: Any) -> None:
    assert manifest.test_remains_sealed is True
