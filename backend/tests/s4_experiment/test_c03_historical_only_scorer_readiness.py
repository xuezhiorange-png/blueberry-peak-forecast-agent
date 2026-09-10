from __future__ import annotations

import copy
import hashlib
import inspect
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

import backend.app.s4_candidate_03_historical_phenology as c03
from backend.app.maturity.config import load_maturity_curve_config
from backend.app.maturity.schemas import ShiftModelArtifact
from backend.app.s2_materialized_dataset.shared.contracts import MaterializableRow
from backend.app.s4_experiment import (
    BreakdownAxisEvidence,
    BreakdownCellEvidence,
    CoverageQualityEvidence,
    MetricObservation,
    SelectionEvidenceProvenanceError,
    build_coverage_quality_evidence_payload,
    parse_coverage_quality_evidence_payload,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO_ROOT / "configs/maturity_curve.yaml"
GROUP = ("season-1", "farm-1", "subfarm-1", "variety-1")
CUTOFF = date(2026, 1, 30)


def _identity(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _row(
    *,
    horizon: int,
    actual: str = "10",
    group: tuple[str, str, str, str] = GROUP,
    base_date: date = CUTOFF,
) -> MaterializableRow:
    return MaterializableRow(
        season=group[0],
        farm=group[1],
        subfarm=group[2],
        variety=group[3],
        harvest_business_date=base_date + timedelta(days=horizon),
        actual_harvest_quantity_kg=Decimal(actual),
        source_row_identity=_identity(f"source-{group}-{horizon}"),
        cleaned_row_identity=_identity(f"cleaned-{group}-{horizon}"),
        pit_visibility_identity=_identity(f"pit-{group}-{horizon}"),
        revision_winner_identity=_identity(f"winner-{group}-{horizon}"),
    )


def _authority(
    *,
    train_rows: tuple[MaterializableRow, ...] = (),
    evaluation_rows: tuple[MaterializableRow, ...] = (),
) -> SimpleNamespace:
    return SimpleNamespace(
        source_id="SOURCE_002",
        materialized_dataset_identity_sha256=c03.C03_MATERIALIZED_DATASET_IDENTITY,
        train_dataset_identity=c03.C03_TRAIN_DATASET_IDENTITY,
        validation_dataset_identity=c03.C03_VALIDATION_DATASET_IDENTITY,
        actual_label_set_identity=_identity("source-002-evaluation-labels"),
        cutoff_policy_identity=_identity("source-002-cutoff-policy"),
        forecast_horizon_set_identity=_identity("source-002-horizons-7-14-21"),
        business_grain_set_identity=_identity("source-002-business-grain"),
        common_comparable_set_identity=_identity("source-002-comparable-set"),
        forecast_cutoff_at=CUTOFF,
        requested_forecast_horizons=c03.C03_FORECAST_HORIZONS,
        observed_forecast_horizons=c03.C03_FORECAST_HORIZONS,
        train_row_count=c03.C03_TRAIN_ROWS,
        validation_row_count=c03.C03_VALIDATION_ROWS,
        evaluation_row_count=688,
        train_rows=train_rows,
        validation_rows=evaluation_rows,
        evaluation_rows=evaluation_rows,
        complete_window_authority=None,
        test_remains_sealed=True,
    )


def _manifest():
    return c03.build_c03_historical_only_manifest(
        authority=_authority(),
        config_path=CONFIG_PATH,
        code_commit_binding="a" * 40,
    )


def _synthetic_model() -> c03._C03TrainingModel:
    support_days = tuple(range(-30, 91))
    density = tuple(Decimal(1 + max(0, 100 - abs(day - 20))) for day in support_days)
    artifact = ShiftModelArtifact(
        enabled=True,
        intercept_days=Decimal("30"),
        coefficients={},
        category_vocabulary={"group": ("|".join(GROUP),)},
        reference_categories={"group": "unknown"},
        unknown_categories={"group": "unknown"},
        unknown_handling_rules={"group": "map_unseen_to_intercept"},
        feature_order=(),
        scaler_center={},
        scaler_scale={},
        feature_units={"group": "canonical_business_grain"},
        missing_value_rules={"group": "intercept"},
        bounds=(Decimal("-21"), Decimal("21")),
        warnings=(),
    )
    return c03._C03TrainingModel(
        support_days=support_days,
        group_anchors={GROUP: CUTOFF},
        variety_anchors={GROUP[3]: CUTOFF},
        group_totals={GROUP: Decimal("1000")},
        variety_total_medians={GROUP[3]: Decimal("1000")},
        group_curves={GROUP: density},
        variety_curves={GROUP[3]: density},
        shift_model=c03.C03HistoricalShiftModel(
            artifact=artifact,
            group_shift_days={GROUP: Decimal("30")},
            variety_shift_days={GROUP[3]: Decimal("30")},
            default_shift_days=Decimal("30"),
        ),
    )


def _scorer() -> c03.C03HistoricalPhenologyScorer:
    return c03.C03HistoricalPhenologyScorer(
        train_rows=(),
        forecast_cutoff_at=CUTOFF,
        train_dataset_identity=c03.C03_TRAIN_DATASET_IDENTITY,
        config=load_maturity_curve_config(CONFIG_PATH),
        _model=_synthetic_model(),
    )


def _target_rows() -> tuple[MaterializableRow, ...]:
    return tuple(_row(horizon=horizon, actual=str(horizon)) for horizon in (7, 14, 21))


def test_c03_owner_semantic_preserved() -> None:
    manifest = _manifest()
    assert manifest.semantic_authority_decision_id == c03.C03_OWNER_DECISION_ID
    assert manifest.semantic_authority == "TRAINING_TIME_LEARNED_SHIFT_MODEL_BOUND"


def test_c03_allowed_parameter_is_maximum_abs_shift_days() -> None:
    assert c03.C03_ALLOWED_PARAMETER_PATHS == ("offset.maximum_abs_shift_days",)


def test_c03_forecast_phase_parameter_remains_excluded() -> None:
    assert c03.C03_EXCLUDED_PARAMETER_PATHS == ("forecast.observed_phase_adjustment_max_days",)


def test_c03_v1_manifest_not_used_for_v4_execution() -> None:
    forged = replace(_manifest(), version="v0.3-s4-c03-phenology-offset-manifest-v1")
    with pytest.raises(c03.C03HistoricalPhenologyError, match="C03_V1_MANIFEST"):
        c03.validate_c03_historical_only_manifest(forged)


def test_c03_v2_manifest_hash_deterministic() -> None:
    assert _manifest().manifest_hash == _manifest().manifest_hash


def test_c03_manifest_binds_v4_policy() -> None:
    manifest = _manifest()
    assert manifest.guardrail_policy_version == (
        "v0.3-s4-guardrail-policy-v4-breakdown-reporting-floor"
    )
    assert manifest.guardrail_policy_hash == c03.V4_GUARDRAIL_POLICY_HASH


def test_c03_manifest_binds_sparse_surface() -> None:
    manifest = _manifest()
    assert manifest.evaluation_surface_identity == c03.C03_EVALUATION_SURFACE_ID
    assert manifest.forecast_horizons == (7, 14, 21)
    assert manifest.complete_daily_rowset_authority is False
    assert manifest.missing_day_zero_fill is False


def test_c03_run_values_remain_14_18_24_28() -> None:
    assert tuple(run.parameter_value for run in _manifest().runs) == (
        Decimal("14"),
        Decimal("18"),
        Decimal("24"),
        Decimal("28"),
    )


def test_c03_incumbent_value_remains_21() -> None:
    assert c03.C03_INCUMBENT_VALUE == Decimal("21")


def test_c03_scorer_reads_source002_train() -> None:
    audit_source = inspect.getsource(c03.C03HistoricalPhenologyScorer.from_v2_authority)
    assert "v2_training_rows(authority)" in audit_source
    assert c03.C03_SOURCE_ID == "SOURCE_002"


def test_c03_scorer_uses_no_weather() -> None:
    assert c03.C03_USES_WEATHER is False
    assert "backend.app.maturity.service" not in inspect.getsource(c03)


def test_c03_scorer_uses_no_production_plan() -> None:
    assert c03.C03_USES_PRODUCTION_PLAN is False
    assert "forecast_natural_maturity" not in inspect.getsource(c03)


def test_c03_scorer_uses_no_task8() -> None:
    assert c03.C03_USES_TASK8 is False


def test_c03_scorer_uses_no_task9() -> None:
    assert c03.C03_USES_TASK9 is False


def test_c03_validation_actual_not_used_for_fit(monkeypatch: pytest.MonkeyPatch) -> None:
    target_rows = _target_rows()
    captured: dict[str, object] = {}

    def fake_builder(train_rows, projection_rows, config):
        captured["train_rows"] = train_rows
        captured["projection_rows"] = projection_rows
        captured["config"] = config
        return _synthetic_model()

    monkeypatch.setattr(c03, "_build_training_model", fake_builder)
    authority = _authority(
        train_rows=(_row(horizon=-1, actual="100"),),
        evaluation_rows=target_rows,
    )
    scorer = c03.C03HistoricalPhenologyScorer.from_v2_authority(
        authority,
        load_maturity_curve_config(CONFIG_PATH),
    )
    assert scorer.train_rows == authority.train_rows
    assert captured["train_rows"] == authority.train_rows
    projection_rows = captured["projection_rows"]
    assert isinstance(projection_rows, tuple)
    assert tuple(row.actual_harvest_quantity_kg for row in projection_rows) == (
        Decimal("0"),
        Decimal("0"),
        Decimal("0"),
    )


def test_c03_test_remains_sealed() -> None:
    assert c03.C03_TEST_REMAINS_SEALED is True
    assert c03.C03_USES_PROSPECTIVE_CAPTURE is False
    assert c03.C03_USES_WALL_CLOCK_WAIT is False


def test_c03_parameter_reaches_training_shift_math() -> None:
    proof = _scorer().prove_parameter_effect(_target_rows())
    assert proof.changed_prediction_count > 0
    assert proof.baseline_prediction_identity != proof.alternate_prediction_identity


@pytest.mark.parametrize("value", (Decimal("14"), Decimal("18"), Decimal("24"), Decimal("28")))
def test_c03_each_frozen_value_changes_candidate_configuration(value: Decimal) -> None:
    effects = _scorer().prove_frozen_parameter_effects(_target_rows())
    assert effects[value] is True


def test_c03_prediction_identity_is_deterministic() -> None:
    scorer = _scorer()
    rows = _target_rows()
    first = scorer.predict_rows(rows, Decimal("14"))
    second = scorer.predict_rows(rows, Decimal("14"))
    assert scorer.prediction_identity(first) == scorer.prediction_identity(second)


def test_c03_v4_gate_request_allowed_in_pure_preflight() -> None:
    manifest = _manifest()
    request = c03.build_c03_v4_gate_request(
        manifest=manifest,
        candidate_run_ordinal=1,
        code_commit_sha="b" * 40,
        evaluation_id="c03-readiness-r1-1",
    )
    result = c03.check_c03_v4_gate(request)
    assert result.allowed is True
    assert request.guardrail_policy_version == c03.V4_GUARDRAIL_POLICY_VERSION
    assert request.experiment_plan_hash == c03.EXPERIMENT_PLAN_V2_HASH
    assert request.global_actual_evaluation_count == 8
    assert request.test_access_requested is False


def test_c03_future_evidence_uses_cell_reason_code() -> None:
    axes = tuple(
        BreakdownAxisEvidence(
            axis_name=axis_name,
            cells=(
                BreakdownCellEvidence(
                    cell_id=f"{axis_name}:cell-1",
                    comparable_rows=12,
                    metric_status="COMPUTED",
                    reason_code="RAW_METRIC_COMPUTED",
                ),
            ),
        )
        for axis_name in (
            "forecast_horizon_days",
            "farm_business_key",
            "subfarm_business_key",
            "variety_business_key",
            "season_business_key",
            "model_identity",
        )
    )
    payload = build_coverage_quality_evidence_payload(
        CoverageQualityEvidence(
            coverage_ratio=MetricObservation.computed("coverage_ratio", Decimal("1")),
            valid_included_canonical_group_coverage=MetricObservation.computed(
                "valid_included_canonical_group_coverage", Decimal("1")
            ),
            missing_data_proportion=MetricObservation.computed(
                "missing_data_proportion", Decimal("0")
            ),
            breakdown_axes=axes,
            no_silent_exclusion=True,
        )
    )
    assert payload["breakdown_axes"]["farm_business_key"]["cells"][0]["reason_code"] == (
        "RAW_METRIC_COMPUTED"
    )


def test_c03_future_evidence_round_trip_passes() -> None:
    axes = tuple(
        BreakdownAxisEvidence(
            axis_name=axis_name,
            cells=(
                BreakdownCellEvidence(
                    cell_id=f"{axis_name}:cell-1",
                    comparable_rows=3,
                    metric_status="INSUFFICIENT_SAMPLE",
                    reason_code="RAW_CELL_SAMPLE_BELOW_REPORTING_FLOOR",
                ),
            ),
        )
        for axis_name in (
            "forecast_horizon_days",
            "farm_business_key",
            "subfarm_business_key",
            "variety_business_key",
            "season_business_key",
            "model_identity",
        )
    )
    original = CoverageQualityEvidence(
        coverage_ratio=MetricObservation.computed("coverage_ratio", Decimal("1")),
        valid_included_canonical_group_coverage=MetricObservation.computed(
            "valid_included_canonical_group_coverage", Decimal("1")
        ),
        missing_data_proportion=MetricObservation.computed("missing_data_proportion", Decimal("0")),
        breakdown_axes=axes,
        no_silent_exclusion=True,
    )
    payload = build_coverage_quality_evidence_payload(original)
    parsed = parse_coverage_quality_evidence_payload(payload)
    assert build_coverage_quality_evidence_payload(parsed) == payload
    assert parsed.breakdown_axes[0].cells[0].reason_code == (
        "RAW_CELL_SAMPLE_BELOW_REPORTING_FLOOR"
    )


def test_c03_readiness_creates_no_started_event() -> None:
    assert c03.C03_HISTORICAL_ONLY_SCORING_PATH_EXISTS is True
    source = inspect.getsource(c03)
    assert "S4CandidateExecutionAuthority" not in source
    assert ".execute(" not in source


def test_c03_readiness_budget_remains_8_24() -> None:
    # This is a read-only contract assertion; the durable PostgreSQL ledger is
    # intentionally not imported or mutated by the readiness adapter.
    assert c03.C03_HISTORICAL_ONLY_SCORING_PATH_EXISTS is True
    assert c03.C03_TEST_REMAINS_SEALED is True
    assert "s4_validation_budget" not in inspect.getsource(c03)


def test_c03_missing_reason_code_is_rejected_by_future_evidence_contract() -> None:
    axes = tuple(
        BreakdownAxisEvidence(
            axis_name=axis_name,
            cells=(BreakdownCellEvidence(cell_id=f"{axis_name}:1", comparable_rows=12),),
        )
        for axis_name in (
            "forecast_horizon_days",
            "farm_business_key",
            "subfarm_business_key",
            "variety_business_key",
            "season_business_key",
            "model_identity",
        )
    )
    evidence = CoverageQualityEvidence(
        coverage_ratio=MetricObservation.computed("coverage_ratio", Decimal("1")),
        valid_included_canonical_group_coverage=MetricObservation.computed(
            "valid_included_canonical_group_coverage", Decimal("1")
        ),
        missing_data_proportion=MetricObservation.computed("missing_data_proportion", Decimal("0")),
        breakdown_axes=axes,
    )
    with pytest.raises(SelectionEvidenceProvenanceError):
        build_coverage_quality_evidence_payload(evidence)


def test_c03_incumbent_replay_uses_same_prediction_identity() -> None:
    scorer = _scorer()
    rows = _target_rows()
    first = scorer.predict_rows(rows, c03.C03_INCUMBENT_VALUE)
    second = scorer.predict_rows(copy.deepcopy(rows), c03.C03_INCUMBENT_VALUE)
    assert scorer.prediction_identity(first) == scorer.prediction_identity(second)
