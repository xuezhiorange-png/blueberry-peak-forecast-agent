"""Offline historical quantities times predeclared SYNTHETIC costs. No production IO."""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.app.area_yield.v015_research_cohort import digest
from backend.app.forecast_intelligence import business_loss as loss
from backend.app.forecast_intelligence import forecast_ops as ops
from backend.app.forecast_intelligence.uncertainty import (
    MODEL_ID,
    CalibrationTargetRow,
    calibrate,
    evaluate,
)
from scripts import run_v0_16_s2_uncertainty_calibration as s2
from scripts import run_v0_16_s4_forecastops_monitoring as s4

REPOSITORY = Path(__file__).resolve().parents[1]
BASE = "0084981e92869b24cad90dd1a066a125e73a8ba3"
TASK = "V0_16_S5_BUSINESS_LOSS_CONTRACT_R1"
S4_ROOT = "docs/v0-16/evidence/forecastops-monitoring-r1"
S4_POLICY_HASH = "6dfe2c1ac684844af636d936b5797d301e80f015c9e3dd880a102127a169ac1c"
OUTPUT_NAMES = ("private-business-loss-inputs.json", "historical-synthetic-loss-summary.json")
load, sha, save = s4.load, s4.sha, s4.save
sources, label_access, output_guard = s4.sources, s4.label_access, s4.output_guard


def public_authority() -> dict[str, str]:
    bound = s4.public_authority()
    contract = load(REPOSITORY / S4_ROOT / "monitoring-policy-r1.json")
    if (
        contract["policy_hash"] != S4_POLICY_HASH
        or digest(contract["policy"]) != S4_POLICY_HASH
        or digest(s4.policy()) != S4_POLICY_HASH
    ):
        raise ValueError("UPSTREAM_AUTHORITY_DRIFT")
    manifest = load(REPOSITORY / S4_ROOT / "manifest-r1.json")
    if manifest["policy_hash"] != S4_POLICY_HASH:
        raise ValueError("UPSTREAM_AUTHORITY_DRIFT")
    for name, expected in manifest["files"].items():
        path = REPOSITORY / S4_ROOT / name
        if sha(path.read_bytes()) != expected:
            raise ValueError("UPSTREAM_AUTHORITY_DRIFT")
        bound[f"{S4_ROOT}/{name}"] = expected
    bound[f"{S4_ROOT}/manifest-r1.json"] = sha(
        (REPOSITORY / S4_ROOT / "manifest-r1.json").read_bytes()
    )
    for name in (
        "backend/app/forecast_intelligence/business_loss.py",
        "scripts/run_v0_16_s5_business_loss_contract.py",
    ):
        bound[name] = sha((REPOSITORY / name).read_bytes())
    return bound


def cost_contracts() -> list[dict[str, Any]]:
    return [c.payload() | {"contract_hash": c.contract_hash} for c in loss.synthetic_contracts()]


def policy() -> dict[str, Any]:
    return {
        "business_loss_policy_version": loss.BUSINESS_LOSS_POLICY_VERSION,
        "cost_contract_policy_version": loss.COST_CONTRACT_POLICY_VERSION,
        "forecast_comparison_policy_version": loss.FORECAST_COMPARISON_POLICY_VERSION,
        "formula": loss.FORMULA,
        "underforecast_definition": "max(actual_kg - forecast_kg, 0)",
        "overforecast_definition": "max(forecast_kg - actual_kg, 0)",
        "cost_authority_types": list(loss.AUTHORITY_TYPES),
        "hidden_cost_default_allowed": False,
        "decimal_only": True,
        "decimal_precision": 50,
        "inexact_authoritative_arithmetic": "FAIL_CLOSED",
        "native_float_authoritative_input_allowed": False,
        "display_quantization": False,
        "canonical_company_cost_established": False,
        "real_roi_validated": False,
        "same_cost_contract_comparison_required": True,
        "same_comparable_rowset_required": True,
        "comparison_semantics": "DESCRIPTIVE_SYNTHETIC_COST_COMPARISON",
        "comparison_selection": "COMPLETE_COMMON_ORIGIN_PREFIX_ALL_THREE_CANDIDATES_AND_ACTUAL",
        "missing_actual_is_zero": False,
        "missing_candidate_is_zero": False,
        "partial_is_complete": False,
        "horizons": list(loss.HORIZONS),
        "target_semantics": loss.TARGET_SEMANTICS,
        "candidates": list(loss.CANDIDATES),
        "synthetic_cost_contracts": cost_contracts(),
        "economic_evidence_class": "REAL_HISTORICAL_QUANTITY_TIMES_SYNTHETIC_COST_WEIGHTS",
        "source_model_id": MODEL_ID,
        "source_split": "EXPOSED_OOT",
        "source_bindings": dict(s2.PINS) | {"common_rowset_hash": s4.COMMON},
        "s2_policy_hash": s4.S2_POLICY,
        "s2_coverage_summary_hash": s4.S2_COVERAGE,
        "s2_lead_day_summary_hash": s4.S2_LEADS,
        "s4_forecastops_policy_hash": S4_POLICY_HASH,
        "actual_matching": ops.ACTUAL_MATCH_POLICY_VERSION,
        "current_season_actual_read": False,
        "strict_pit": False,
        "historical_actual_available_at_proven": False,
        "retrospective_authority_used": True,
        "point_forecast_is_proven_p50": False,
        "upper_planning_bound_is_quantile": False,
        "new_forecast_model_allowed": False,
        "model_training_allowed": False,
        "model_refit_allowed": False,
        "model_tuning_allowed": False,
        "privacy_policy": "PRIVATE_ROWS_PUBLIC_AGGREGATES_HASHES_ONLY",
        "source_evidence_sha256": public_authority(),
    }


def prepare(s5: Path, dataset: Path, harvest: Path, output: Path) -> None:
    output_guard(output, [s5, dataset, harvest])
    if output.exists():
        raise ValueError("OUTPUT_ALREADY_EXISTS")
    with label_access(None):
        frozen_policy = policy()
        *_, binding = sources(s5, dataset, harvest)
    contract = {
        "task_id": TASK,
        "base_main_sha": BASE,
        "policy": frozen_policy,
        "policy_hash": digest(frozen_policy),
    }
    contract["contract_hash"] = digest(contract)
    save(output / "contract.json", contract)
    save(
        output / "source-binding-prelabel.json",
        {
            "source_hashes": binding,
            "contract_hash": contract["contract_hash"],
            "label_bytes_read": False,
        },
    )


def verify_contract(output: Path) -> dict[str, Any]:
    c = load(output / "contract.json")
    if (
        c.get("task_id") != TASK
        or c.get("base_main_sha") != BASE
        or c.get("policy") != policy()
        or c.get("policy_hash") != digest(c["policy"])
        or digest({k: v for k, v in c.items() if k != "contract_hash"}) != c.get("contract_hash")
    ):
        raise ValueError("BUSINESS_LOSS_CONTRACT_DRIFT")
    return dict(c)


def historical_rows(
    frozen: Any,
    full: list[dict[str, Any]],
    common: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    label_path: Path,
) -> list[CalibrationTargetRow]:
    """Consume the original S5 sealed LabelPermit, not an independent actual source."""
    with label_access(label_path):
        raw = label_path.read_bytes()
        # Inspect season metadata before parsing any quantity or selecting a subset.
        if re.search(rb'"season"\s*:\s*"2026-2027"', raw):
            raise ValueError("FAIL_CURRENT_SEASON_ACTUAL_PRESENT")
        if sha(raw) != s2.PINS["full_label_file_hash"]:
            raise ValueError("BLOCKED_LABELSET_DRIFT")
        envelope = json.loads(raw, parse_float=s2.reject_float, parse_constant=s2.reject_float)
        if any(r["season"] == "2026-2027" for r in envelope):
            raise ValueError("FAIL_CURRENT_SEASON_ACTUAL_PRESENT")
        if len({r["row_key"] for r in envelope}) != len(envelope):
            raise ValueError("ACTUAL_DUPLICATE_CONFLICT")
        labels = frozen.labels("EXPOSED_OOT", full)
    label_map = {r["row_key"]: values for r, values in zip(full, labels, strict=True)}
    common = sorted(common, key=lambda r: r["row_key"])
    if digest([label_map[r["row_key"]] for r in common]) != s2.PINS["filtered_labelset_hash"]:
        raise ValueError("BLOCKED_LABELSET_DRIFT")
    pred = {r["row_key"]: r["predictions"] for r in predictions}
    if len(pred) != len(predictions) or set(pred) != {r["row_key"] for r in common}:
        raise ValueError("ROWSET_ACCOUNTING_FAILED")
    targets = []
    for r in common:
        for lead, (target, p, a) in enumerate(
            zip(r["target_dates"], pred[r["row_key"]], label_map[r["row_key"]], strict=True), 1
        ):
            row = CalibrationTargetRow(
                f"{r['row_key']}#D{lead:02}",
                r["base_id"],
                r["season"],
                datetime.fromisoformat(r["forecast_origin"]),
                lead,
                date.fromisoformat(target),
                s2.numeric(p),
                s2.numeric(a),
            )
            row.validate()
            targets.append(row)
    if len(common) != s2.ORIGINS or len(targets) != s2.TARGETS:
        raise ValueError("ROWSET_ACCOUNTING_FAILED")
    return targets


def loss_inputs(
    targets: list[CalibrationTargetRow], intervals: list[dict[str, Any]]
) -> tuple[
    list[loss.LossTarget],
    list[loss.ActualObservation],
    list[loss.ForecastCandidate],
    list[dict[str, Any]],
]:
    interval_map = {r["row_key"]: r for r in intervals}
    if len(interval_map) != len(intervals) or set(interval_map) != {r.row_key for r in targets}:
        raise ValueError("INTERVAL_ROWSET_DRIFT")
    expected, actuals, private = [], [], []
    values: dict[str, list[loss.CandidateValue]] = {c: [] for c in loss.CANDIDATES}
    for r in sorted(targets, key=lambda r: (r.forecast_origin, r.base_id, r.lead_day, r.row_key)):
        t = loss.LossTarget(
            r.row_key, r.base_id, r.season, r.forecast_origin, r.lead_day, r.target_date
        )
        t.validate()
        ir = interval_map[r.row_key]
        if (
            ir["base_id"] != r.base_id
            or ir["season"] != r.season
            or ir["forecast_origin"] != r.forecast_origin.isoformat()
            or ir["lead_day"] != r.lead_day
            or ir["target_date"] != r.target_date.isoformat()
            or Decimal(ir["point_forecast_kg"]) != r.point_prediction_kg
            or Decimal(ir["actual_kg"]) != r.actual_kg
        ):
            raise ValueError("INTERVAL_ROWSET_DRIFT")
        quantities: dict[str, Decimal | None] = {loss.POINT: r.point_prediction_kg}
        for cid, level in ((loss.UP80, 80), (loss.UP90, 90)):
            value = ir[f"upper_planning_bound_{level}"]
            quantities[cid] = s2.numeric(value) if value is not None else None
        expected.append(t)
        actuals.append(loss.ActualObservation(t, r.actual_kg))
        for cid in loss.CANDIDATES:
            values[cid].append(loss.CandidateValue(t, quantities[cid]))
        private.append(
            {
                "target": t.payload(),
                "actual_kg": loss.decimal_text(r.actual_kg),
                "candidate_values": {
                    k: loss.decimal_text(v) if v is not None else None
                    for k, v in quantities.items()
                },
            }
        )
    interval_hash = digest(intervals)
    candidates = [
        loss.ForecastCandidate(
            cid,
            s2.PINS["prediction_hash"]
            if cid == loss.POINT
            else digest(
                {
                    "candidate_id": cid,
                    "s2_policy_hash": s4.S2_POLICY,
                    "interval_rows_hash": interval_hash,
                    "point_prediction_hash": s2.PINS["prediction_hash"],
                    "actual_authority_hash": s2.PINS["filtered_labelset_hash"],
                }
            ),
            tuple(values[cid]),
        )
        for cid in loss.CANDIDATES
    ]
    return expected, actuals, candidates, private


def run(s5: Path, dataset: Path, harvest: Path, output: Path) -> None:
    output_guard(output, [s5, dataset, harvest])
    with label_access(None):
        contract = verify_contract(output)
        frozen, full, common, predictions, before = sources(s5, dataset, harvest)
        if load(output / "source-binding-prelabel.json") != {
            "source_hashes": before,
            "contract_hash": contract["contract_hash"],
            "label_bytes_read": False,
        }:
            raise ValueError("SOURCE_BINDING_DRIFT")
    save(output / "run-started.json", {"contract_hash": contract["contract_hash"]})
    save(output / "process-receipt.json", {"process_id": os.getpid()})
    label_path = dataset / "label_zone/exposed_oot-labels.json"
    targets = historical_rows(frozen, full, common, predictions, label_path)
    intervals = calibrate(targets)
    coverage, leads, _, _ = evaluate(intervals)
    if digest(coverage) != s4.S2_COVERAGE or digest(leads) != s4.S2_LEADS:
        raise ValueError("S2_INTERVAL_REPLAY_PARITY_FAILED")
    expected, actuals, candidates, private = loss_inputs(targets, intervals)
    results = {
        cost.contract_id: loss.evaluate_comparison(
            cost,
            expected,
            actuals,
            candidates,
            actual_authority_hash=s2.PINS["filtered_labelset_hash"],
            expected_candidate_hashes={c.candidate_id: c.source_hash for c in candidates},
        )
        for cost in loss.synthetic_contracts()
    }
    summary = {
        "economic_evidence_class": "SYNTHETIC_BUSINESS_LOSS_EXPERIMENT",
        "origin_count": len(common),
        "target_row_count": len(targets),
        "candidate_count": len(candidates),
        "cost_scenario_count": len(results),
        "loss_unit": "SYNTHETIC_LOSS_UNIT",
        "results": results,
    }
    summary["result_hash"] = digest(summary)
    with label_access(None):
        *_, after = sources(s5, dataset, harvest)
    with label_access(label_path):
        if before != after or sha(label_path.read_bytes()) != s2.PINS["full_label_file_hash"]:
            raise ValueError("SOURCE_ARTIFACT_MUTATION")
    save(output / OUTPUT_NAMES[0], private)
    save(output / OUTPUT_NAMES[1], summary)
    save(
        output / "execution-receipt.json",
        {
            "contract_hash": contract["contract_hash"],
            "policy_hash": contract["policy_hash"],
            "source_immutability_status": "PASS",
            "s2_replay_parity": "PASS",
            "label_read_stage": "RUN_AFTER_ORIGINAL_S5_SEAL_GATE",
            "full_label_file_hash": s2.PINS["full_label_file_hash"],
            "filtered_common_labelset_hash": s2.PINS["filtered_labelset_hash"],
            "artifact_hashes": {name: sha((output / name).read_bytes()) for name in OUTPUT_NAMES},
        },
    )


def privacy(value: Any) -> None:
    s4.privacy(value)
    if isinstance(value, dict):
        if {
            "target",
            "candidate_values",
            "actual_kg",
            "forecast_kg",
            "daily_prediction",
            "source_file",
            "password",
            "token",
        } & value.keys():
            raise ValueError("PUBLIC_PRIVATE_DATA_LEAK")
        for v in value.values():
            privacy(v)
    elif isinstance(value, list):
        for v in value:
            privacy(v)


def publish(primary: Path, replay: Path, public: Path) -> None:
    output_guard(public, [primary, replay])
    if primary.resolve() == replay.resolve() or load(primary / "process-receipt.json") == load(
        replay / "process-receipt.json"
    ):
        raise ValueError("FRESH_PROCESS_REPLAY_REQUIRED")
    contract = verify_contract(primary)
    receipt = load(primary / "execution-receipt.json")
    if verify_contract(replay) != contract or receipt != load(replay / "execution-receipt.json"):
        raise ValueError("DETERMINISTIC_REPLAY_FAILED")
    for name in ("contract.json", "source-binding-prelabel.json", *OUTPUT_NAMES):
        raw = (primary / name).read_bytes()
        if raw != (replay / name).read_bytes() or (
            name in OUTPUT_NAMES and sha(raw) != receipt["artifact_hashes"][name]
        ):
            raise ValueError("DETERMINISTIC_REPLAY_FAILED")
    summary = load(primary / OUTPUT_NAMES[1])
    if digest({k: v for k, v in summary.items() if k != "result_hash"}) != summary["result_hash"]:
        raise ValueError("BUSINESS_LOSS_RESULT_DRIFT")
    evidence = {
        "task_id": TASK,
        "version": "0.16.0",
        "stage": "S5",
        "base_main_sha": BASE,
        "s5_implementation_authorized": True,
        "engineering_result": "PASS",
        "business_loss_policy_version": loss.BUSINESS_LOSS_POLICY_VERSION,
        "cost_contract_policy_version": loss.COST_CONTRACT_POLICY_VERSION,
        "forecast_comparison_policy_version": loss.FORECAST_COMPARISON_POLICY_VERSION,
        "business_loss_policy_hash": contract["policy_hash"],
        "formula": loss.FORMULA,
        "cost_authority_types": list(loss.AUTHORITY_TYPES),
        "acceptance_cost_authority_type": "EXPLICIT_SYNTHETIC_SCENARIO",
        "canonical_company_cost_established": False,
        "real_roi_validated": False,
        "synthetic_cost_scenario_count": 3,
        "synthetic_loss_unit": True,
        "source_model_id": MODEL_ID,
        "source_split": "EXPOSED_OOT",
        "point_prediction_hash": s2.PINS["prediction_hash"],
        "common_rowset_hash": s4.COMMON,
        "target_rowset_hash": s2.PINS["rowset_hash"],
        "s2_policy_hash": s4.S2_POLICY,
        "s4_forecastops_policy_hash": S4_POLICY_HASH,
        "candidates": list(loss.CANDIDATES),
        "horizons": list(loss.HORIZONS),
        "origin_count": summary["origin_count"],
        "target_row_count": summary["target_row_count"],
        "current_season_actual_read": False,
        "current_season_actual_import": False,
        "current_season_actual_scoring": False,
        "strict_pit": False,
        "historical_actual_available_at_proven": False,
        "retrospective_authority_used": True,
        "point_forecast_is_proven_p50": False,
        "upper_planning_bound_is_quantile": False,
        "point_forecast_reexecuted": False,
        "model_training_executed": False,
        "model_refit_executed": False,
        "model_tuning_executed": False,
        "new_forecast_model_created": False,
        "new_model_artifact_created": False,
        "db_migration_created": False,
        "http_business_loss_api_implemented": False,
        "mcp_business_loss_tools_implemented": False,
        "frontend_changed": False,
        "scheduler_created": False,
        "systemd_timer_changed": False,
        "automatic_business_action_implemented": False,
        "model_artifact_file_mutation": False,
        "point_prediction_mutation": False,
        "label_file_mutation": False,
        "s2_evidence_mutation": False,
        "s4_evidence_mutation": False,
        "s0_s4_changed": False,
        "v0_14_changed": False,
        "v0_15_changed": False,
        "deterministic_replay": "PASS",
        "privacy_status": "PASS",
        "source_immutability_status": "PASS",
        "s2_replay_parity": "PASS",
        "private_rows_committed": False,
        "s5_formal_complete": False,
        "external_exact_head_ci": "REQUIRED_SEPARATE_TERMINAL_PR_RECEIPT",
        "ready_authorized": False,
        "merge_authorized": False,
        "s5_ready_authorized": False,
        "s5_merge_authorized": False,
        "s6_implementation_authorized": False,
        "s6_started": False,
        "v0_17_started": False,
        "tag_authorized": False,
        "release_authorized": False,
        "stop": True,
    }
    files = {
        "business-loss-policy-r1.json": contract,
        "synthetic-cost-contracts-r1.json": cost_contracts(),
        "historical-synthetic-loss-summary-r1.json": summary,
        "source-binding-r1.json": load(primary / "source-binding-prelabel.json") | receipt,
        "deterministic-replay-report-r1.json": {
            "result": "PASS",
            "fresh_processes_verified": True,
            "artifact_hashes": receipt["artifact_hashes"],
        },
        "privacy-scan-report-r1.json": {"result": "PASS", "public_private_data_leak": False},
        "v0.16-s5-business-loss-contract-r1.json": evidence,
    }
    if public.exists():
        raise ValueError("PUBLIC_OUTPUT_ALREADY_EXISTS")
    for value in files.values():
        privacy(value)
    for name, value in files.items():
        save(public / name, value)
    save(
        public / "manifest-r1.json",
        {
            "files": {n: sha((public / n).read_bytes()) for n in sorted(files)},
            "policy_hash": contract["policy_hash"],
            "result_hash": summary["result_hash"],
        },
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline synthetic-cost business loss")
    parser.add_argument("phase", choices=("PREPARE", "RUN", "REPLAY", "PUBLISH"))
    for name in ("s5-output-root", "dataset-root", "harvest-state-root", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--replay-output", type=Path)
    parser.add_argument("--public-output", type=Path)
    args = parser.parse_args(argv)
    roots = args.s5_output_root, args.dataset_root, args.harvest_state_root
    try:
        if args.phase == "PREPARE":
            prepare(*roots, args.output)
        elif args.phase == "RUN":
            run(*roots, args.output)
        elif args.phase == "REPLAY":
            if args.replay_output is None or not (args.output / "execution-receipt.json").is_file():
                raise ValueError("PRIMARY_AND_REPLAY_REQUIRED")
            verify_contract(args.output)
            prepare(*roots, args.replay_output)
            run(*roots, args.replay_output)
        else:
            if args.replay_output is None or args.public_output is None:
                raise ValueError("REPLAY_AND_PUBLIC_OUTPUT_REQUIRED")
            output_guard(args.public_output, [*roots, args.output, args.replay_output])
            publish(args.output, args.replay_output, args.public_output)
    except Exception as exc:
        code = (
            str(exc)
            if isinstance(exc, ValueError) and re.fullmatch("[A-Z][A-Z0-9_]+", str(exc))
            else "BUSINESS_LOSS_OPERATOR_FAILED"
        )
        print(json.dumps({"result": "FAIL", "code": code}))
        return 1
    print(
        json.dumps(
            {
                "result": "PASS",
                "phase": args.phase,
                "policy_version": loss.BUSINESS_LOSS_POLICY_VERSION,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
