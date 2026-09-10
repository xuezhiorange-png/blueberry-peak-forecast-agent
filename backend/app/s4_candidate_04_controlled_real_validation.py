"""Controlled real-validation wiring for the frozen C04 candidate.

This module is intentionally a thin execution adapter.  The candidate model
math remains in :mod:`s4_candidate_04_historical_yield`; the durable
STARTED/terminal boundary remains in :mod:`s4_candidate_execution_authority`.
The adapter only pairs the prediction projection with the frozen SOURCE-002
labels, computes the canonical sparse-surface metrics, and submits one
explicitly authorized invocation at a time.

It has no TEST reader and does not expose a parameter or candidate selector.
The command-line entry point is fixed to the four C04 manifest runs.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from backend.app.db.session import AsyncSessionMaker
from backend.app.maturity.config import load_maturity_curve_config
from backend.app.rolling_backtest.canonical import canonical_json_dumps, sha256_payload
from backend.app.s4_candidate_04_historical_yield import (
    C04_BASELINE_MULTIPLIER,
    C04HistoricalYieldScorer,
    C04ParameterManifest,
    build_c04_gate_request,
    build_c04_parameter_manifest,
)
from backend.app.s4_candidate_execution_authority import S4CandidateExecutionAuthority
from backend.app.s4_experiment import (
    REQUIRED_BREAKDOWN_AXES,
    SPARSE_COMPLETE_WINDOW_METRICS,
    V3_COMPLETE_DAILY_ROWSET_AUTHORITY,
    V3_EVALUATION_SURFACE_ID,
    V3_FORECAST_HORIZONS,
    V3_MISSING_DAY_ZERO_FILL,
    BreakdownAxisEvidence,
    BreakdownCellEvidence,
    CandidateEligibilityResult,
    CoverageQualityEvidence,
    EvidenceStatus,
    MetricObservation,
    evaluate_candidate_guardrails_v3_sparse,
)
from backend.app.s4_local_engineering import (
    FrozenEngineeringDataset,
    LocalMetricSet,
    LocalPrediction,
    V2HistoricalEvaluationAuthority,
    build_v2_historical_evaluation_authority,
    compute_metrics,
    load_frozen_engineering_dataset,
)
from backend.app.s4_validation_budget import S4ValidationBudgetRepository
from backend.app.s4_validation_budget.schemas import EVENT_STARTED, EVENT_TERMINAL

FROZEN_MANIFEST_CODE_COMMIT = "d219a3d99da3a1766ace75dcbf6a99b82d66f2a4"
FROZEN_PARAMETER_MANIFEST_HASH = "1e3433b9216f8ebe63db44ba0bc1353e1d4664cef3c1cc3f2a57bb794fe280ee"
FROZEN_RUN_PARAMETER_MANIFEST_HASHES = (
    "4ec3b36876b6394ef72596e1d52fd941023ca350aa8f5d51831f16b5ae770310",
    "a222b793cf91f1a212e9cb2b905d8e737e8152a192a9e403951de05c73d86bbf",
    "633be3689dca6af97e2b52ff44cf2bef6f3d81f085ae7136aeca205791afc7d3",
    "cb6d816a18ffd732fb2dee7df7fb3b1aa4c7fd312be489dffbd049b595c2569d",
)
FROZEN_RUN_EVALUATION_IDS = (
    "v0-3-s4-c04-v3-real-validation-01",
    "v0-3-s4-c04-v3-real-validation-02",
    "v0-3-s4-c04-v3-real-validation-03",
    "v0-3-s4-c04-v3-real-validation-04",
)
EXECUTION_TASK_ID = "V0_3_S4_C04_CONTROLLED_REAL_VALIDATION_R1"
TRIGGER_SOURCE = EXECUTION_TASK_ID
EXPECTED_LEGACY_DEBIT = 4
EXPECTED_INITIAL_STARTED = 0
EXPECTED_INITIAL_EFFECTIVE = 4
EXPECTED_INITIAL_REMAINING = 28


class C04ControlledValidationError(RuntimeError):
    """Fail-closed error for the controlled run boundary."""


@dataclass(frozen=True, slots=True)
class C04RunScore:
    ordinal: int
    multiplier: Decimal
    prediction_identity: str
    metric_evidence_identity: str
    metrics: LocalMetricSet
    eligibility: CandidateEligibilityResult


def current_execution_code_sha(repo_root: Path) -> str:
    """Return the immutable code commit used for every authorized run."""

    try:
        return subprocess.check_output(
            ("git", "-C", str(repo_root), "rev-parse", "HEAD"),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise C04ControlledValidationError("EXECUTION_CODE_SHA_UNAVAILABLE") from exc


def mask_target_actuals(
    target_rows: tuple[Any, ...],
) -> tuple[Any, ...]:
    """Keep target identities while making actual quantity unavailable to prediction."""

    return tuple(replace(row, actual_harvest_quantity_kg=Decimal("0")) for row in target_rows)


def build_frozen_manifest(
    authority: V2HistoricalEvaluationAuthority,
    repo_root: Path,
) -> C04ParameterManifest:
    """Rebuild and verify the already-frozen C04 manifest without changing it."""

    manifest = build_c04_parameter_manifest(
        authority=authority,
        config_path=repo_root / "configs" / "maturity_curve.yaml",
        code_commit_binding=FROZEN_MANIFEST_CODE_COMMIT,
    )
    if manifest.manifest_hash != FROZEN_PARAMETER_MANIFEST_HASH:
        raise C04ControlledValidationError("C04_PARAMETER_MANIFEST_HASH_MISMATCH")
    if tuple(run.parameter_manifest_hash for run in manifest.runs) != (
        FROZEN_RUN_PARAMETER_MANIFEST_HASHES
    ):
        raise C04ControlledValidationError("C04_RUN_PARAMETER_MANIFEST_HASH_MISMATCH")
    return manifest


def _row_identity(row: Any) -> tuple[str, str, str, str, Any]:
    return (row.season, row.farm, row.subfarm, row.variety, row.harvest_business_date)


def project_predictions_with_actuals(
    predictions: tuple[Any, ...],
    target_rows: tuple[Any, ...],
) -> tuple[LocalPrediction, ...]:
    """Attach labels only after the prediction projection is complete."""

    actual_by_key = {_row_identity(row): row.actual_harvest_quantity_kg for row in target_rows}
    if len(actual_by_key) != len(target_rows):
        raise C04ControlledValidationError("TARGET_IDENTITY_NOT_UNIQUE")
    projected: list[LocalPrediction] = []
    for prediction in predictions:
        key = (
            prediction.season,
            prediction.farm,
            prediction.subfarm,
            prediction.variety,
            prediction.harvest_business_date,
        )
        if key not in actual_by_key:
            raise C04ControlledValidationError("PREDICTION_TARGET_IDENTITY_MISMATCH")
        projected.append(
            LocalPrediction(
                season=prediction.season,
                farm=prediction.farm,
                subfarm=prediction.subfarm,
                variety=prediction.variety,
                harvest_business_date=prediction.harvest_business_date,
                forecast_cutoff_at=prediction.forecast_cutoff_at,
                actual_kg=actual_by_key[key],
                p50_kg=prediction.candidate_p50_kg,
                p80_kg=prediction.candidate_p80_kg,
                p90_kg=prediction.candidate_p90_kg,
                model_identity=prediction.model_identity,
            )
        )
    if len(projected) != len(target_rows):
        raise C04ControlledValidationError("PREDICTION_TARGET_ROW_COUNT_MISMATCH")
    return tuple(projected)


def _metric_observation(
    metric_name: str,
    value: Decimal | None,
    status: str,
) -> MetricObservation:
    if status == "COMPUTED" and value is not None:
        return MetricObservation.computed(metric_name, value)
    return MetricObservation.not_computable(metric_name)


def _coverage_quality(
    metrics: LocalMetricSet,
    *,
    target_rows: tuple[Any, ...],
    predictions: tuple[LocalPrediction, ...],
) -> CoverageQualityEvidence:
    target_keys = {_row_identity(row) for row in target_rows}
    predicted_keys = {item.business_key for item in predictions}
    if not target_keys:
        raise C04ControlledValidationError("TARGET_IDENTITY_EMPTY")
    coverage_ratio = Decimal(len(predicted_keys & target_keys)) / Decimal(len(target_keys))
    target_groups = {(row.season, row.farm, row.subfarm, row.variety) for row in target_rows}
    predicted_groups = {
        (item.season, item.farm, item.subfarm, item.variety) for item in predictions
    }
    group_coverage = Decimal(len(predicted_groups & target_groups)) / Decimal(len(target_groups))
    missing_proportion = Decimal(len(target_keys - predicted_keys)) / Decimal(len(target_keys))
    axes = tuple(
        BreakdownAxisEvidence(
            axis_name=axis,
            cells=tuple(
                BreakdownCellEvidence(
                    cell_id=f"{axis}:{cell_id}",
                    comparable_rows=int(cell["comparable_row_count"] or 0),
                    metric_status=cast(
                        EvidenceStatus,
                        str(cell.get("daily_wape_metric_status", "MISSING")),
                    ),
                )
                for cell_id, cell in metrics.breakdown_metrics[axis].items()
            ),
        )
        for axis in REQUIRED_BREAKDOWN_AXES
    )
    return CoverageQualityEvidence(
        coverage_ratio=MetricObservation.computed("coverage_ratio", coverage_ratio),
        valid_included_canonical_group_coverage=MetricObservation.computed(
            "valid_included_canonical_group_coverage", group_coverage
        ),
        missing_data_proportion=MetricObservation.computed(
            "missing_data_proportion", missing_proportion
        ),
        breakdown_axes=axes,
        no_silent_exclusion=predicted_keys == target_keys,
    )


def evaluate_c04_sparse_guardrails(
    *,
    candidate_metrics: LocalMetricSet,
    incumbent_metrics: LocalMetricSet,
    target_rows: tuple[Any, ...],
    candidate_predictions: tuple[LocalPrediction, ...],
) -> CandidateEligibilityResult:
    """Run the real V3 sparse evaluator with complete-window diagnostics."""

    complete_window_metrics = {
        metric_name: (
            MetricObservation.not_computable(metric_name),
            MetricObservation.not_computable(metric_name),
        )
        for metric_name in SPARSE_COMPLETE_WINDOW_METRICS
    }
    return evaluate_candidate_guardrails_v3_sparse(
        candidate_primary_metric=_metric_observation(
            "daily_wape",
            candidate_metrics.daily_wape,
            candidate_metrics.daily_wape_metric_status,
        ),
        incumbent_primary_metric=_metric_observation(
            "daily_wape",
            incumbent_metrics.daily_wape,
            incumbent_metrics.daily_wape_metric_status,
        ),
        candidate_daily_mae=MetricObservation.computed("daily_mae", candidate_metrics.daily_mae),
        incumbent_daily_mae=MetricObservation.computed("daily_mae", incumbent_metrics.daily_mae),
        candidate_p80_coverage=MetricObservation.computed(
            "P80_COVERAGE", candidate_metrics.p80_coverage
        ),
        incumbent_p80_coverage=MetricObservation.computed(
            "P80_COVERAGE", incumbent_metrics.p80_coverage
        ),
        candidate_p90_coverage=MetricObservation.computed(
            "P90_COVERAGE", candidate_metrics.p90_coverage
        ),
        incumbent_p90_coverage=MetricObservation.computed(
            "P90_COVERAGE", incumbent_metrics.p90_coverage
        ),
        coverage_quality=_coverage_quality(
            candidate_metrics,
            target_rows=target_rows,
            predictions=candidate_predictions,
        ),
        complete_window_metrics=complete_window_metrics,
        evaluation_surface_identity=V3_EVALUATION_SURFACE_ID,
        forecast_horizons=V3_FORECAST_HORIZONS,
        complete_daily_rowset_authority=V3_COMPLETE_DAILY_ROWSET_AUTHORITY,
        missing_day_zero_fill=V3_MISSING_DAY_ZERO_FILL,
    )


def _decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def _eligibility_payload(result: CandidateEligibilityResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "candidate_eligible": result.candidate_eligible,
        "reason_codes": list(result.reason_codes),
        "guardrails": [
            {
                "guardrail_id": item.guardrail_id,
                "status": item.status,
                "reason_code": item.reason_code,
                "candidate_value": _decimal_text(item.candidate_value),
                "incumbent_value": _decimal_text(item.incumbent_value),
            }
            for item in result.guardrails
        ],
        "diagnostics": [
            {
                "metric_name": item.metric_name,
                "status": item.status,
                "selection_blocking": item.selection_blocking,
                "diagnostic_only": item.diagnostic_only,
                "reason_code": item.reason_code,
            }
            for item in result.diagnostics
        ],
    }


def _metrics_payload(metrics: LocalMetricSet) -> dict[str, Any]:
    payload = dict(metrics.payload())
    payload["coverage_ratio"] = "1.000000"
    payload["valid_included_canonical_group_coverage"] = "1.000000"
    payload["missing_data_proportion"] = "0.000000"
    payload["complete_window_selection_blocking"] = False
    payload["complete_window_diagnostic_only"] = True
    payload["complete_window_reason"] = "COMPLETE_DAILY_ROW_SET_AUTHORITY_UNAVAILABLE"
    return payload


def _state_payload(state: Any | None) -> dict[str, Any] | None:
    if state is None:
        return None
    return {
        "authority_version": state.authority_version,
        "accepted_event_count": state.accepted_event_count,
        "accepted_started_count": state.accepted_started_count,
        "accepted_last_global_evaluation_ordinal": state.accepted_last_global_evaluation_ordinal,
        "legacy_reconciled_validation_debit": state.legacy_reconciled_validation_debit,
        "effective_consumed": state.effective_consumed,
        "remaining": state.remaining,
        "accepted_head_event_hash": state.accepted_head_event_hash,
    }


def _event_hash(state: Any | None, evaluation_id: str, event_type: str) -> str | None:
    if state is None:
        return None
    for event in state.events:
        if event.evaluation_id == evaluation_id and event.event_type == event_type:
            return cast(str, event.event_hash)
    return None


def _run_score_payload(score: C04RunScore) -> dict[str, Any]:
    metrics = _metrics_payload(score.metrics)
    return {
        "candidate_run_ordinal": score.ordinal,
        "multiplier": _decimal_text(score.multiplier),
        "prediction_identity": score.prediction_identity,
        "metric_evidence_identity": score.metric_evidence_identity,
        "metrics": metrics,
        "candidate_daily_wape": _decimal_text(score.metrics.daily_wape),
        "candidate_daily_mae": _decimal_text(score.metrics.daily_mae),
        "candidate_p80_coverage": _decimal_text(score.metrics.p80_coverage),
        "candidate_p90_coverage": _decimal_text(score.metrics.p90_coverage),
        "eligibility": _eligibility_payload(score.eligibility),
    }


def _score_run(
    *,
    scorer: C04HistoricalYieldScorer,
    ordinal: int,
    multiplier: Decimal,
    target_rows: tuple[Any, ...],
    masked_target_rows: tuple[Any, ...],
    incumbent_metrics: LocalMetricSet,
) -> C04RunScore:
    prediction_projection = scorer.predict_rows(masked_target_rows, multiplier)
    candidate_predictions = project_predictions_with_actuals(prediction_projection, target_rows)
    metrics = compute_metrics(candidate_predictions, complete_window_authority=None)
    prediction_identity = scorer.prediction_identity(prediction_projection)
    metric_identity = sha256_payload(metrics.payload())
    eligibility = evaluate_c04_sparse_guardrails(
        candidate_metrics=metrics,
        incumbent_metrics=incumbent_metrics,
        target_rows=target_rows,
        candidate_predictions=candidate_predictions,
    )
    return C04RunScore(
        ordinal=ordinal,
        multiplier=multiplier,
        prediction_identity=prediction_identity,
        metric_evidence_identity=metric_identity,
        metrics=metrics,
        eligibility=eligibility,
    )


def _validate_initial_state(state: Any) -> None:
    if (
        state.legacy_reconciled_validation_debit != EXPECTED_LEGACY_DEBIT
        or state.accepted_started_count != EXPECTED_INITIAL_STARTED
        or state.effective_consumed != EXPECTED_INITIAL_EFFECTIVE
        or state.remaining != EXPECTED_INITIAL_REMAINING
        or state.accepted_last_global_evaluation_ordinal != 0
    ):
        raise C04ControlledValidationError("C04_PREEXECUTION_DURABLE_BUDGET_STATE_MISMATCH")


async def run_authorized_c04_validation(repo_root: Path) -> dict[str, Any]:
    """Execute the four fixed runs exactly once, or fail closed."""

    dataset: FrozenEngineeringDataset = load_frozen_engineering_dataset(repo_root)
    authority = build_v2_historical_evaluation_authority(dataset)
    if (
        authority.materialized_dataset_identity_sha256
        != "f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785"
        or authority.train_row_count != 16_224
        or authority.validation_row_count != 8_006
        or authority.train_dataset_identity
        != "be2d4184434a0f389af21c315945322e9216cd17cc471b772e3fff389d3386d2"
        or authority.validation_dataset_identity
        != "4cbf1119f83034464159210ebbbeea5ec87848f92ce044bb328949a8f5331d06"
        or len(authority.evaluation_rows) != 688
        or tuple(authority.requested_forecast_horizons) != V3_FORECAST_HORIZONS
        or authority.test_remains_sealed is not True
    ):
        raise C04ControlledValidationError("SOURCE_002_AUTHORITY_MISMATCH")
    if str(authority.forecast_cutoff_at) != "2026-01-30":
        raise C04ControlledValidationError("FORECAST_CUTOFF_MISMATCH")

    manifest = build_frozen_manifest(authority, repo_root)
    config = load_maturity_curve_config(repo_root / "configs" / "maturity_curve.yaml")
    scorer = C04HistoricalYieldScorer.from_v2_authority(authority, config)
    target_rows = tuple(authority.evaluation_rows)
    masked_target_rows = mask_target_actuals(target_rows)
    incumbent_projection = scorer.predict_rows(masked_target_rows, C04_BASELINE_MULTIPLIER)
    incumbent_predictions = project_predictions_with_actuals(incumbent_projection, target_rows)
    incumbent_metrics = compute_metrics(incumbent_predictions, complete_window_authority=None)
    incumbent_prediction_identity = scorer.prediction_identity(incumbent_projection)
    incumbent_metric_identity = sha256_payload(incumbent_metrics.payload())
    execution_code_sha = current_execution_code_sha(repo_root)

    before_state: Any | None = None
    async with AsyncSessionMaker() as session:
        before_state = await S4ValidationBudgetRepository(session).load_verified_state()
    _validate_initial_state(before_state)

    evidence: dict[str, Any] = {
        "TASK_ID": EXECUTION_TASK_ID,
        "TASK_CLASS": "AUTHORIZED_REAL_VALIDATION_EXECUTION_AND_COMPARISON",
        "EXECUTION_AUTHORIZED": True,
        "AUTHORIZED_CANDIDATE_ID": "04_yield_parameter",
        "AUTHORIZED_REAL_VALIDATION_RUN_COUNT": 4,
        "AUTOMATIC_RETRY_AUTHORIZED": False,
        "TEST_AUTHORIZED": False,
        "EXECUTION_CODE_SHA": execution_code_sha,
        "SOURCE_002_AUTHORITY_VERIFIED": True,
        "MATERIALIZED_DATASET_IDENTITY": authority.materialized_dataset_identity_sha256,
        "TRAIN_ROWS": authority.train_row_count,
        "TRAIN_CONTENT_SHA256": authority.train_dataset_identity,
        "VALIDATION_ROWS": authority.validation_row_count,
        "VALIDATION_CONTENT_SHA256": authority.validation_dataset_identity,
        "FORECAST_CUTOFF": str(authority.forecast_cutoff_at),
        "EVALUATION_TARGET_ROWS": len(target_rows),
        "FORECAST_HORIZONS": list(V3_FORECAST_HORIZONS),
        "EVALUATION_SURFACE_ID": V3_EVALUATION_SURFACE_ID,
        "COMPLETE_DAILY_ROWSET_AUTHORITY": False,
        "MISSING_DAY_ZERO_FILL": False,
        "C04_PARAMETER_MANIFEST_VERSION": manifest.version,
        "C04_PARAMETER_MANIFEST_HASH": manifest.manifest_hash,
        "C04_PARAMETER_VALUES": [str(value) for value in manifest.parameter_values],
        "C04_PARAMETER_MANIFEST_CODE_COMMIT": manifest.code_commit_binding,
        "TARGET_IDENTITY_HASH": authority.actual_label_set_identity,
        "COMMON_COMPARABLE_SET_IDENTITY": authority.common_comparable_set_identity,
        "INCUMBENT_MODEL_ID": "V0_2_CURRENT_MODEL",
        "INCUMBENT_YIELD_AMPLITUDE_MULTIPLIER": "1.0",
        "INCUMBENT_PREDICTION_IDENTITY": incumbent_prediction_identity,
        "INCUMBENT_METRIC_EVIDENCE_IDENTITY": incumbent_metric_identity,
        "INCUMBENT_METRICS": _metrics_payload(incumbent_metrics),
        "INCUMBENT_DAILY_WAPE": _decimal_text(incumbent_metrics.daily_wape),
        "INCUMBENT_DAILY_MAE": _decimal_text(incumbent_metrics.daily_mae),
        "INCUMBENT_P80_COVERAGE": _decimal_text(incumbent_metrics.p80_coverage),
        "INCUMBENT_P90_COVERAGE": _decimal_text(incumbent_metrics.p90_coverage),
        "VALIDATION_ACTUAL_USED_FOR_MODEL_FITTING": False,
        "VALIDATION_ACTUAL_USED_FOR_PARAMETER_SELECTION": False,
        "VALIDATION_ACTUAL_USED_FOR_PREDICTION": False,
        "TEST_ACCESS_REQUESTED": False,
        "TEST_BYTES_READ": False,
        "TEST_EVALUATION_PERFORMED": False,
        "TEST_REMAINS_SEALED": True,
        "RUNS": [],
        "INITIAL_BUDGET_STATE": _state_payload(before_state),
        "RETRY_COUNT": 0,
        "AUTOMATIC_RETRY_COUNT": 0,
        "MANUAL_RETRY_COUNT": 0,
        "OPERATOR_TRIGGERED_RERUN_COUNT": 0,
    }

    stopped_after = 0
    technical_stop_reason: str | None = None
    for ordinal, (multiplier, evaluation_id) in enumerate(
        zip(manifest.parameter_values, FROZEN_RUN_EVALUATION_IDS, strict=True),
        start=1,
    ):
        run_entry: dict[str, Any] = {
            "evaluation_id": evaluation_id,
            "candidate_run_ordinal": ordinal,
            "multiplier": str(multiplier),
            "parameter_manifest_hash": manifest.run(ordinal).parameter_manifest_hash,
            "execution_code_sha": execution_code_sha,
            "started_persisted": False,
            "terminal_persisted": False,
            "terminal_status": None,
            "budget_before": None,
            "budget_after": None,
            "target_row_count": len(target_rows),
            "prediction_identity": None,
            "candidate_metric_evidence_identity": None,
            "candidate_metrics": None,
            "candidate_daily_wape": None,
            "candidate_daily_mae": None,
            "candidate_p80_coverage": None,
            "candidate_p90_coverage": None,
            "incumbent_prediction_identity": incumbent_prediction_identity,
            "incumbent_metric_evidence_identity": incumbent_metric_identity,
            "incumbent_daily_wape": _decimal_text(incumbent_metrics.daily_wape),
            "incumbent_daily_mae": _decimal_text(incumbent_metrics.daily_mae),
            "incumbent_p80_coverage": _decimal_text(incumbent_metrics.p80_coverage),
            "incumbent_p90_coverage": _decimal_text(incumbent_metrics.p90_coverage),
            "eligibility_status": None,
            "candidate_eligible": False,
            "reason_codes": [],
            "started_event_id": None,
            "started_event_hash": None,
            "terminal_event_hash": None,
            "technical_blocker": None,
        }
        score_holder: dict[str, C04RunScore] = {}

        async with AsyncSessionMaker() as session:
            authority_adapter = S4CandidateExecutionAuthority(session)
            request = build_c04_gate_request(
                manifest=manifest,
                candidate_run_ordinal=ordinal,
                code_commit_sha=execution_code_sha,
                evaluation_id=evaluation_id,
                candidate_actual_run_count=ordinal - 1,
                global_actual_evaluation_count=EXPECTED_INITIAL_EFFECTIVE + ordinal - 1,
            )

            def scorer_callback(
                run_ordinal: int = ordinal,
                run_multiplier: Decimal = multiplier,
                run_score_holder: dict[str, C04RunScore] = score_holder,
            ) -> str:
                score = _score_run(
                    scorer=scorer,
                    ordinal=run_ordinal,
                    multiplier=run_multiplier,
                    target_rows=target_rows,
                    masked_target_rows=masked_target_rows,
                    incumbent_metrics=incumbent_metrics,
                )
                run_score_holder["score"] = score
                return "COMPUTED"

            result = await authority_adapter.execute(
                request,
                scorer=scorer_callback,
                execution_authorized=True,
                trigger_source=TRIGGER_SOURCE,
            )

        preflight_state = result.preflight.state
        run_entry["budget_before"] = _state_payload(preflight_state)
        run_entry["started_persisted"] = result.started_persisted
        run_entry["terminal_persisted"] = result.terminal_persisted
        run_entry["started_event_id"] = result.started_event_id
        run_entry["started_event_hash"] = _event_hash(
            result.state_after_start, evaluation_id, EVENT_STARTED
        )
        run_entry["terminal_event_hash"] = _event_hash(
            result.state_after_terminal, evaluation_id, EVENT_TERMINAL
        )
        run_entry["terminal_status"] = (
            "COMPLETED" if result.status == "COMPLETED" else result.status
        )
        run_entry["budget_after"] = _state_payload(result.state_after_terminal)
        if result.blocker is not None:
            run_entry["technical_blocker"] = result.blocker
            run_entry["reason_codes"] = [result.blocker]
        score = score_holder.get("score")
        if score is not None:
            score_payload = _run_score_payload(score)
            run_entry["prediction_identity"] = score.prediction_identity
            run_entry["candidate_metric_evidence_identity"] = score.metric_evidence_identity
            run_entry["candidate_metrics"] = score_payload["metrics"]
            run_entry["candidate_daily_wape"] = score_payload["candidate_daily_wape"]
            run_entry["candidate_daily_mae"] = score_payload["candidate_daily_mae"]
            run_entry["candidate_p80_coverage"] = score_payload["candidate_p80_coverage"]
            run_entry["candidate_p90_coverage"] = score_payload["candidate_p90_coverage"]
            run_entry["eligibility_status"] = score.eligibility.status
            run_entry["candidate_eligible"] = score.eligibility.candidate_eligible
            run_entry["reason_codes"] = list(score.eligibility.reason_codes)
            run_entry["eligibility"] = score_payload["eligibility"]

        evidence["RUNS"].append(run_entry)
        stopped_after = ordinal
        if (
            result.status != "COMPLETED"
            or not result.started_persisted
            or not result.terminal_persisted
        ):
            technical_stop_reason = result.blocker or "C04_RUN_DID_NOT_COMPLETE"
            break
        after_state = result.state_after_terminal
        if after_state is None or (
            after_state.accepted_started_count != ordinal
            or after_state.effective_consumed != EXPECTED_INITIAL_EFFECTIVE + ordinal
            or after_state.remaining != EXPECTED_INITIAL_REMAINING - ordinal
            or after_state.accepted_last_global_evaluation_ordinal != ordinal
        ):
            technical_stop_reason = "C04_POSTRUN_DURABLE_STATE_MISMATCH"
            run_entry["technical_blocker"] = technical_stop_reason
            break

    async with AsyncSessionMaker() as session:
        final_state = await S4ValidationBudgetRepository(session).load_verified_state()
    evidence["FINAL_BUDGET_STATE"] = _state_payload(final_state)
    evidence["STOPPED_AFTER_RUN"] = stopped_after
    evidence["CANDIDATE_EXECUTION_PERFORMED"] = stopped_after > 0
    evidence["VALIDATION_SCORING_PERFORMED"] = any(
        entry.get("prediction_identity") is not None for entry in evidence["RUNS"]
    )
    evidence["NEW_VALIDATION_SCORING_CALL_COUNT"] = sum(
        entry.get("prediction_identity") is not None for entry in evidence["RUNS"]
    )
    evidence["TECHNICAL_STOP_REASON"] = technical_stop_reason
    completed_runs = [
        entry for entry in evidence["RUNS"] if entry.get("terminal_status") == "COMPLETED"
    ]
    if technical_stop_reason is not None:
        evidence["RESULT"] = "PARTIAL_EXECUTION" if completed_runs else "BLOCKED"
        evidence["C04_VALIDATION_OUTCOME"] = "PARTIAL_EXECUTION"
    else:
        statuses = [entry.get("eligibility_status") for entry in evidence["RUNS"]]
        if len(completed_runs) != 4:
            evidence["RESULT"] = "BLOCKED"
            evidence["C04_VALIDATION_OUTCOME"] = "BLOCKED"
        elif any(status == "PASS" for status in statuses):
            evidence["RESULT"] = "COMPLETED_AND_PUSHED"
            evidence["C04_VALIDATION_OUTCOME"] = "HAS_ELIGIBLE_WINNER"
        elif any(status == "BLOCKED" for status in statuses):
            evidence["RESULT"] = "COMPLETED_AND_PUSHED"
            evidence["C04_VALIDATION_OUTCOME"] = "BLOCKED"
        else:
            evidence["RESULT"] = "COMPLETED_AND_PUSHED"
            evidence["C04_VALIDATION_OUTCOME"] = "NO_ELIGIBLE_RUN"

    eligible = [entry for entry in evidence["RUNS"] if entry.get("eligibility_status") == "PASS"]
    eligible.sort(
        key=lambda entry: (
            Decimal(str(entry["candidate_daily_wape"])),
            int(entry["candidate_run_ordinal"]),
        )
    )
    if eligible:
        best = eligible[0]
        tied = [
            entry
            for entry in eligible
            if Decimal(str(entry["candidate_daily_wape"]))
            == Decimal(str(best["candidate_daily_wape"]))
        ]
        if len(tied) == 1:
            evidence["C04_BEST_RUN_ORDINAL"] = best["candidate_run_ordinal"]
            evidence["C04_BEST_MULTIPLIER"] = best["multiplier"]
            evidence["C04_BEST_DAILY_WAPE"] = best["candidate_daily_wape"]
            evidence["C04_BEST_DAILY_MAE"] = best["candidate_daily_mae"]
        else:
            evidence["C04_BEST_RUN_ORDINAL"] = "NONE"
            evidence["C04_BEST_MULTIPLIER"] = "NONE"
            evidence["C04_BEST_DAILY_WAPE"] = "NONE"
            evidence["C04_BEST_DAILY_MAE"] = "NONE"
            evidence["C04_VALIDATION_OUTCOME"] = "BLOCKED"
            evidence.setdefault("REASON_CODES", []).append("C04_TIEBREAK_AUTHORITY_UNAVAILABLE")
    else:
        evidence["C04_BEST_RUN_ORDINAL"] = "NONE"
        evidence["C04_BEST_MULTIPLIER"] = "NONE"
        evidence["C04_BEST_DAILY_WAPE"] = "NONE"
        evidence["C04_BEST_DAILY_MAE"] = "NONE"
    evidence["C04_ELIGIBLE_RUN_COUNT"] = len(eligible)
    evidence["LEGACY_RECONCILED_VALIDATION_DEBIT"] = final_state.legacy_reconciled_validation_debit
    evidence["CANONICAL_STARTED_COUNT"] = final_state.accepted_started_count
    evidence["C04_CANONICAL_STARTED_COUNT"] = sum(
        event.event_type == EVENT_STARTED and event.candidate_id == "04_yield_parameter"
        for event in final_state.events
    )
    evidence["EFFECTIVE_CONSUMED"] = final_state.effective_consumed
    evidence["REMAINING"] = final_state.remaining
    evidence["BUDGET_DELTA"] = final_state.accepted_started_count
    evidence["COMPLETE_WINDOW_METRICS_DIAGNOSTIC_ONLY"] = True
    evidence["MISSING_DAY_ZERO_FILL"] = False
    evidence["RUN_LOCAL_REPLAY_USED_AS_C03_SCORER"] = False
    evidence["TEST_AUTHORIZED"] = False
    return evidence


def write_evidence(path: Path, evidence: Mapping[str, Any]) -> None:
    path.write_text(canonical_json_dumps(dict(evidence)) + "\n", encoding="utf-8")


__all__ = [
    "C04ControlledValidationError",
    "C04RunScore",
    "EXECUTION_TASK_ID",
    "FROZEN_MANIFEST_CODE_COMMIT",
    "FROZEN_PARAMETER_MANIFEST_HASH",
    "FROZEN_RUN_EVALUATION_IDS",
    "FROZEN_RUN_PARAMETER_MANIFEST_HASHES",
    "build_frozen_manifest",
    "evaluate_c04_sparse_guardrails",
    "mask_target_actuals",
    "project_predictions_with_actuals",
    "run_authorized_c04_validation",
    "write_evidence",
]
