"""Stage-separated private conformal operator. No model execution, SQL or network."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.app.area_yield.v015_research_cohort import canonical, digest
from backend.app.forecast_intelligence.uncertainty import (
    MODEL_ID,
    POLICY_VERSION,
    CalibrationTargetRow,
    calibrate,
    evaluate,
)

REPOSITORY = Path(__file__).resolve().parents[1]
EVIDENCE = "docs/v0-15/evidence/harvest-state-incremental-value-r1"
BASE = "b1ae3f06f982999af68ac4bdb0b2f0b94a845f24"
PINS = {
    "model_artifact_hash": "b382312d33e834ed1b0ec1b98bbb84dcba3ea0f37a31ae846c0a91387f415161",
    "model_config_hash": "1c3d731bd3b56af929ccf0fdd932b14ebb6f7f3b107df8da57f012d89db21173",
    "prediction_hash": "74e1add1e552245b968dca2b0770c97e0ca99abda24545c743162a08e908559b",
    "seal_hash": "a97f6a6a794e16215a2758bad55f2711c08fe935cbac7d3338c692e948b3a2df",
    "rowset_hash": "476f4e00e985408c09512dc9bac5c5daa74a253f50bcb605bb48f8e5aadcc188",
    "filtered_labelset_hash": "4b4d9fe78f887065688f4b115bc87ab46583cc45f224474bc591067c10095b59",
    "dataset_manifest_hash": "7f76d97c34679c31824271ca817835a9ed953504261abf2a249b896713e2e178",
    "full_label_file_hash": "710ca7427d37f5a9f80b0b310d369a97990a8707d976cbb1744f5edcf7529262",
}
ORIGINS = 8775
TARGETS = 131625
PREDICTION_FILE = "exposed-oot-M1-predictions.json"
OUTPUT_NAMES = (
    "private-target-rows.json",
    "private-interval-rows.json",
    "private-base-coverage.json",
    "coverage-summary.json",
    "lead-day-coverage.json",
    "base-breadth-summary.json",
)
PROTECTED = (
    "docs/v0-16/v0.16.0-version-plan-and-scope-freeze.md",
    "docs/v0-16/evidence/v0.16.0-version-plan-and-scope-freeze-r1.json",
    "docs/v0-16/v0.16-s1-hierarchical-forecast-reconciliation-r1.md",
    "docs/v0-16/evidence/v0.16-s1-hierarchical-forecast-reconciliation-r1.json",
    "docs/v0-3/s3/s3-quantile-semantics-contract.md",
    "docs/v0-3/s3/s3-quantile-semantics-remediation-contract.md",
)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def reject_float(value: str) -> Any:
    raise ValueError("SOURCE_NUMERIC_INVALID")


def load(path: Path) -> Any:
    return json.loads(path.read_bytes(), parse_float=reject_float, parse_constant=reject_float)


def save(path: Path, value: Any) -> None:
    raw = canonical(value)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Derived private files are append-only too; conflicting output never overwrites.
    with path.open("xb") as stream:
        os.chmod(path, 0o600)
        stream.write(raw)


def verify_public() -> dict[str, str]:
    files = [
        f"{EVIDENCE}/{n}.json"
        for n in (
            "exposed-oot-prediction-seal",
            "final-fit-manifest",
            "feature-label-custody-audit",
            "common-rowset-binding-report",
            "deterministic-replay-report",
            "exposed-oot-metrics",
        )
    ]
    fit, seal = load(REPOSITORY / files[1]), load(REPOSITORY / files[0])
    audit = load(REPOSITORY / files[2])
    common, replay, metrics = (load(REPOSITORY / f) for f in files[3:])
    if (
        any(
            fit["M1"][k] != PINS[k]
            for k in ("model_artifact_hash", "model_config_hash", "prediction_hash")
        )
        or seal["seal_hash"] != PINS["seal_hash"]
        or seal["rowset_hash"] != PINS["rowset_hash"]
        or seal["predictions"][PREDICTION_FILE] != PINS["prediction_hash"]
        or audit["score_custody"]["exposed-oot"]["labelset_hash"] != PINS["filtered_labelset_hash"]
        or common["origin_counts"]["EXPOSED_OOT"] != ORIGINS
        or common["target_counts"]["EXPOSED_OOT"] != TARGETS
        or replay["artifact_hashes"][PREDICTION_FILE] != PINS["prediction_hash"]
        or metrics["M1"]["origin_count"] != ORIGINS
        or metrics["M1"]["target_row_count"] != TARGETS
    ):
        raise ValueError("BLOCKED_PUBLIC_AUTHORITY_DRIFT")
    implementation = (
        "backend/app/forecast_intelligence/uncertainty.py",
        "scripts/run_v0_16_s2_uncertainty_calibration.py",
    )
    return {f: sha((REPOSITORY / f).read_bytes()) for f in (*files, *PROTECTED, *implementation)}


def policy() -> dict[str, Any]:
    return {
        "policy_version": POLICY_VERSION,
        "point_model_id": MODEL_ID,
        "point_model_role": "RETROSPECTIVE_RESEARCH_POINT_FORECAST_NOT_PRODUCTION",
        "source_bindings": dict(PINS),
        "source_split": "EXPOSED_OOT",
        "origin_count": ORIGINS,
        "target_row_count": TARGETS,
        "calibration_grain": "BASE_TARGET_ROW",
        "pooling_policy": "GLOBAL_BASE_POOL_WITHIN_SAME_LEAD_DAY",
        "eligibility": (
            "SAME_MODEL_SAME_LEAD_AND_C_ORIGIN_LT_E_ORIGIN_AND_C_TARGET_DATE_LT_E_LOCAL_DATE"
        ),
        "origin_time": "17:00 Asia/Shanghai",
        "score_two_sided": "ABSOLUTE_ERROR_KG",
        "score_upper": "UNDERPREDICTION_ERROR_KG",
        "coverage_levels": ["0.80", "0.90"],
        "quantile_rule": "ONE_BASED_CEIL_N_PLUS_ONE_TIMES_LEVEL_NO_INTERPOLATION",
        "minimum_n": {"80": 4, "90": 9},
        "extra_heuristic_min_sample_size": False,
        "lower_bound_zero_clip": True,
        "upper_cap": False,
        "calibration_weighting": "UNWEIGHTED",
        "residual_normalization": "NONE",
        "outlier_removal": False,
        "score_winsorization": False,
        "score_clipping": False,
        "train_residuals_used": False,
        "validation_residuals_used": False,
        "retrospective_date_bound": True,
        "strict_pit": False,
        "exact_historical_available_at_proven": False,
        "retrospective_authority_used": True,
        "point_forecast_is_proven_p50": False,
        "true_quantile_semantics_established": False,
        "upper_bound_semantics": "ONE_SIDED_CONFORMAL_UPPER_COVERAGE_BOUND",
        "horizon_coverage_semantics": "DAILY_TARGET_ROW_COVERAGE_NOT_CUMULATIVE_TOTAL",
        "cumulative_total_conformal_interval_implemented": False,
        "interval_bound_summation_allowed": False,
        "region_interval_calibration": False,
        "company_interval_calibration": False,
        "prospective_interval_coverage_validated": False,
        "production_interval_approval": False,
        "coverage_result_is_pass_gate": False,
        "post_result_retuning": False,
        "privacy_policy": "PRIVATE_ROWS_PUBLIC_AGGREGATES_ONLY_NO_PATHS_OR_IDENTITIES",
        "source_evidence_sha256": verify_public(),
    }


def numeric(value: Any) -> Decimal:
    if not isinstance(value, str):
        raise ValueError("SOURCE_NUMERIC_INVALID")
    try:
        number = Decimal(value)
    except Exception:
        raise ValueError("SOURCE_NUMERIC_INVALID") from None
    if not number.is_finite() or number < 0:
        raise ValueError("SOURCE_NUMERIC_INVALID")
    return number


def sources(s5: Path, dataset: Path) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Pre-label source binding. Does not open/stat/hash any label artifact."""
    fit = load(s5 / "exposed-oot-fit-manifest.json")
    if any(fit["M1"][k] != PINS[k] for k in ("model_artifact_hash", "model_config_hash")):
        raise ValueError("POINT_MODEL_IDENTITY_MISMATCH")
    raw = (s5 / PREDICTION_FILE).read_bytes()
    if (
        sha(raw) != PINS["prediction_hash"]
        or fit["M1"]["prediction_hash"] != PINS["prediction_hash"]
    ):
        raise ValueError("BLOCKED_POINT_PREDICTION_DRIFT")
    predictions = json.loads(raw, parse_float=reject_float, parse_constant=reject_float)
    if not isinstance(predictions, list) or len(predictions) != ORIGINS:
        raise ValueError("ROWSET_ACCOUNTING_FAILED")
    keys = []
    for row in sorted(predictions, key=lambda r: r["row_key"]):
        if set(row) != {"row_key", "predictions"} or len(row["predictions"]) != 15:
            raise ValueError("ROWSET_ACCOUNTING_FAILED")
        for lead, value in enumerate(row["predictions"], 1):
            numeric(value)
            keys.append(f"{row['row_key']}#D{lead:02}")
    if len(keys) != TARGETS or len(set(keys)) != TARGETS or digest(keys) != PINS["rowset_hash"]:
        raise ValueError("ROWSET_ACCOUNTING_FAILED")
    seal = load(s5 / "exposed-oot-prediction-seal.json")
    if (
        seal["seal_hash"] != PINS["seal_hash"]
        or digest({k: v for k, v in seal.items() if k != "seal_hash"}) != PINS["seal_hash"]
        or seal["phase"] != "FINAL"
        or seal["label_scope"] != "EXPOSED_OOT"
        or seal["labels_read"] is not False
        or seal["rowset_hash"] != PINS["rowset_hash"]
        or seal["predictions"][PREDICTION_FILE] != PINS["prediction_hash"]
    ):
        raise ValueError("BLOCKED_PREDICTION_SEAL_DRIFT")
    old_contract = load(s5 / "contract.json")
    if (
        old_contract["contract_hash"] != seal["contract_hash"]
        or digest({k: v for k, v in old_contract.items() if k != "contract_hash"})
        != seal["contract_hash"]
        or digest(old_contract["models"]["M1"]) != PINS["model_config_hash"]
    ):
        raise ValueError("POINT_MODEL_IDENTITY_MISMATCH")
    model = s5 / "models" / "exposed-oot-M1.json"
    if sha(model.read_bytes()) != PINS["model_artifact_hash"]:
        raise ValueError("POINT_MODEL_IDENTITY_MISMATCH")
    manifest = load(dataset / "manifest.json")
    if (
        manifest["manifest_hash"] != PINS["dataset_manifest_hash"]
        or digest({k: v for k, v in manifest.items() if k != "manifest_hash"})
        != PINS["dataset_manifest_hash"]
        or manifest["dataset_hashes"]["EXPOSED_OOT_LABELSET_HASH"] != PINS["full_label_file_hash"]
    ):
        raise ValueError("BLOCKED_DATASET_MANIFEST_DRIFT")
    bindings = {
        "prediction_file": sha(raw),
        "prediction_seal": sha((s5 / "exposed-oot-prediction-seal.json").read_bytes()),
        "fit_manifest": sha((s5 / "exposed-oot-fit-manifest.json").read_bytes()),
        "s5_contract": sha((s5 / "contract.json").read_bytes()),
        "model_artifact": sha(model.read_bytes()),
        "dataset_manifest": sha((dataset / "manifest.json").read_bytes()),
    }
    return predictions, bindings


def private_output_guard(output: Path, s5: Path, dataset: Path) -> None:
    resolved = output.resolve()
    if any(
        resolved == p.resolve()
        or resolved.is_relative_to(p.resolve())
        or p.resolve().is_relative_to(resolved)
        for p in (s5, dataset, REPOSITORY)
    ):
        raise ValueError("PRIVATE_OUTPUT_LOCATION_INVALID")


def prepare(s5: Path, dataset: Path, output: Path) -> None:
    private_output_guard(output, s5, dataset)
    if output.exists():
        raise ValueError("OUTPUT_ALREADY_EXISTS")
    frozen = policy()
    _, binding = sources(s5, dataset)
    contract = {
        "task_id": "V0_16_S2_UNCERTAINTY_AND_CONFORMAL_CALIBRATION_R1",
        "base_main_sha": BASE,
        "policy": frozen,
        "policy_hash": digest(frozen),
    }
    contract["contract_hash"] = digest(contract)
    save(output / "contract.json", contract)
    save(
        output / "source-binding-prelabel.json",
        {
            "source_hashes": binding,
            "label_bytes_read": False,
            "contract_hash": contract["contract_hash"],
        },
    )


def verify_contract(output: Path) -> dict[str, Any]:
    c = load(output / "contract.json")
    if (
        c.get("base_main_sha") != BASE
        or c.get("task_id") != "V0_16_S2_UNCERTAINTY_AND_CONFORMAL_CALIBRATION_R1"
        or set(c) != {"base_main_sha", "task_id", "policy", "policy_hash", "contract_hash"}
        or c["policy"] != policy()
        or c["policy_hash"] != digest(c["policy"])
        or digest({k: v for k, v in c.items() if k != "contract_hash"}) != c["contract_hash"]
    ):
        raise ValueError("CONFORMAL_CONTRACT_DRIFT")
    return dict(c)


def process_identity() -> int:
    return os.getpid()


def run(s5: Path, dataset: Path, output: Path) -> None:
    private_output_guard(output, s5, dataset)
    contract = verify_contract(output)
    if (output / "run-started.json").exists():
        raise ValueError("RUN_ALREADY_STARTED_NEW_AUTHORIZED_REPLAY_REQUIRED")
    predictions, before = sources(s5, dataset)
    binding = load(output / "source-binding-prelabel.json")
    if binding != {
        "source_hashes": before,
        "label_bytes_read": False,
        "contract_hash": contract["contract_hash"],
    }:
        raise ValueError("SOURCE_BINDING_DRIFT")
    # Durable marker precedes label bytes; a failed run cannot silently overwrite outputs.
    save(output / "run-started.json", {"contract_hash": contract["contract_hash"]})
    save(output / "process-custody-receipt.json", {"process_id": process_identity()})
    raw = (dataset / "label_zone" / "exposed_oot-labels.json").read_bytes()
    if sha(raw) != PINS["full_label_file_hash"]:
        raise ValueError("BLOCKED_LABELSET_DRIFT")
    labels = json.loads(raw, parse_float=reject_float, parse_constant=reject_float)
    if any(r["season"] == "2026-2027" for r in labels):
        raise ValueError("FAIL_CURRENT_SEASON_ACTUAL_PRESENT")
    if len({r["row_key"] for r in labels}) != len(labels) or any(
        r["split"] != "EXPOSED_OOT" or r["season"] != "2025-2026" for r in labels
    ):
        raise ValueError("ROWSET_ACCOUNTING_FAILED")
    by_key = {r["row_key"]: r for r in labels}
    targets: list[CalibrationTargetRow] = []
    filtered = []
    for prediction in sorted(predictions, key=lambda r: r["row_key"]):
        r = by_key.get(prediction["row_key"])
        if (
            r is None
            or digest({k: v for k, v in r.items() if k != "row_hash"}) != r["row_hash"]
            or digest(r["labels"]) != r["label_hash"]
        ):
            raise ValueError("BLOCKED_LABELSET_DRIFT")
        daily = r["labels"]["daily"]
        if len(daily) != 15 or len(r["target_dates"]) != 15:
            raise ValueError("ROWSET_ACCOUNTING_FAILED")
        filtered.append(daily)
        for lead, (actual, point, target) in enumerate(
            zip(daily, prediction["predictions"], r["target_dates"], strict=True), 1
        ):
            targets.append(
                CalibrationTargetRow(
                    row_key=f"{r['row_key']}#D{lead:02}",
                    base_id=r["base_id"],
                    season=r["season"],
                    forecast_origin=datetime.fromisoformat(r["forecast_origin"]),
                    lead_day=lead,
                    target_date=date.fromisoformat(target),
                    point_prediction_kg=numeric(point),
                    actual_kg=numeric(actual),
                )
            )
    if digest(filtered) != PINS["filtered_labelset_hash"]:
        raise ValueError("BLOCKED_LABELSET_DRIFT")
    if len(targets) != TARGETS or len({(r.base_id, r.forecast_origin) for r in targets}) != ORIGINS:
        raise ValueError("ROWSET_ACCOUNTING_FAILED")
    intervals = calibrate(targets)
    summary, leads, breadth, private = evaluate(intervals)
    # Re-read consumed sources, including the label file, without modifying them.
    _, after = sources(s5, dataset)
    if (
        before != after
        or sha((dataset / "label_zone" / "exposed_oot-labels.json").read_bytes())
        != PINS["full_label_file_hash"]
    ):
        raise ValueError("SOURCE_ARTIFACT_MUTATION")
    payloads = {
        "private-target-rows.json": [
            {
                k: r[k]
                for k in (
                    "row_key",
                    "base_id",
                    "season",
                    "forecast_origin",
                    "origin_local_date",
                    "lead_day",
                    "target_date",
                    "point_forecast_kg",
                    "actual_kg",
                    "split",
                    "point_model_id",
                )
            }
            | {"point_prediction_hash": PINS["prediction_hash"]}
            for r in intervals
        ],
        "private-interval-rows.json": intervals,
        "private-base-coverage.json": private,
        "coverage-summary.json": summary,
        "lead-day-coverage.json": leads,
        "base-breadth-summary.json": breadth,
    }
    for name, value in payloads.items():
        save(output / name, value)
    save(
        output / "execution-receipt.json",
        {
            "policy_hash": contract["policy_hash"],
            "contract_hash": contract["contract_hash"],
            "origin_count": ORIGINS,
            "candidate_target_rows": TARGETS,
            "label_file_hash": PINS["full_label_file_hash"],
            "filtered_labelset_hash": digest(filtered),
            "source_artifact_mutation": False,
            "current_season_actual_read": False,
            "point_prediction_reexecuted": False,
            "model_training_executed": False,
            "artifact_hashes": {name: sha((output / name).read_bytes()) for name in OUTPUT_NAMES},
        },
    )


def privacy(value: Any) -> None:
    forbidden = {
        "base_id",
        "base_name",
        "canonical_base_name",
        "canonical_farm",
        "actual_kg",
        "predictions",
        "point_forecast_kg",
        "coefficients",
        "scaler",
        "password",
        "credential",
        "token",
        "latitude",
        "longitude",
    }
    if isinstance(value, dict):
        if forbidden & value.keys():
            raise ValueError("PUBLIC_PRIVATE_DATA_LEAK")
        for v in value.values():
            privacy(v)
    elif isinstance(value, list):
        for v in value:
            privacy(v)
    elif isinstance(value, str) and any(
        s in value
        for s in (
            "/Users/",
            "/home/",
            "/private/",
            "/tmp/",
            "postgresql://",
            "postgres://",
            "file://",
        )
    ):
        raise ValueError("PUBLIC_PRIVATE_DATA_LEAK")


def publish(primary: Path, replay: Path, public: Path) -> None:
    if primary.resolve() == replay.resolve():
        raise ValueError("INDEPENDENT_REPLAY_REQUIRED")
    if load(primary / "process-custody-receipt.json") == load(
        replay / "process-custody-receipt.json"
    ):
        raise ValueError("FRESH_PROCESS_REPLAY_REQUIRED")
    c = verify_contract(primary)
    if verify_contract(replay) != c:
        raise ValueError("DETERMINISTIC_REPLAY_FAILED")
    receipts = [load(root / "execution-receipt.json") for root in (primary, replay)]
    for name in OUTPUT_NAMES:
        raws = [(root / name).read_bytes() for root in (primary, replay)]
        if raws[0] != raws[1] or any(
            sha(raw) != receipt["artifact_hashes"][name]
            for raw, receipt in zip(raws, receipts, strict=True)
        ):
            raise ValueError("DETERMINISTIC_REPLAY_FAILED")
    if receipts[0] != receipts[1]:
        raise ValueError("DETERMINISTIC_REPLAY_FAILED")
    files = {
        "conformal-policy-r1.json": c,
        "source-binding-r1.json": load(primary / "source-binding-prelabel.json"),
        "coverage-summary-r1.json": load(primary / "coverage-summary.json"),
        "lead-day-coverage-r1.json": load(primary / "lead-day-coverage.json"),
        "base-breadth-summary-r1.json": load(primary / "base-breadth-summary.json"),
        "deterministic-replay-report-r1.json": {
            "result": "PASS",
            "fresh_processes_required": True,
            "fresh_processes_verified": True,
            "private_interval_bytes_equal": True,
            "artifact_hashes": receipts[0]["artifact_hashes"],
            "policy_hash": c["policy_hash"],
        },
        "privacy-scan-report-r1.json": {
            "result": "PASS",
            "public_private_data_leak": False,
            "private_rows_published": False,
        },
        "v0.16-s2-uncertainty-and-conformal-calibration-r1.json": {
            "task_id": c["task_id"],
            "version": "0.16.0",
            "stage": "S2",
            "base_main_sha": BASE,
            "engineering_result": "PASS",
            "evaluation_classification": "EMPIRICAL_COVERAGE_OBSERVED",
            "origin_count": ORIGINS,
            "target_row_count": TARGETS,
            "policy_hash": c["policy_hash"],
            "source_authority": dict(PINS),
            "source_split": "EXPOSED_OOT",
            "2025_2026_previously_exposed": True,
            "retrospective_interval_calibration_executed": True,
            "retrospective_date_bound": True,
            "strict_pit": False,
            "retrospective_authority_used": True,
            "point_forecast_is_proven_p50": False,
            "true_quantile_semantics_established": False,
            "legacy_quantile_semantics_reopened": False,
            "prospective_interval_coverage_validated": False,
            "production_interval_approval": False,
            "production_use_approved": False,
            "source_artifact_mutation": False,
            "point_prediction_reexecuted": False,
            "current_season_actual_read": False,
            "current_season_actual_import": False,
            "current_season_actual_scoring": False,
            "model_training_executed": False,
            "model_refit_executed": False,
            "model_tuning_executed": False,
            "train_residuals_used": False,
            "validation_residuals_used": False,
            "exposed_oot_residuals_used": True,
            "region_interval_calibration": False,
            "company_interval_calibration": False,
            "interval_bound_summation_allowed": False,
            "db_migration_created": False,
            "http_interval_api_implemented": False,
            "mcp_interval_tools_implemented": False,
            "s1_schema_changed": False,
            "v0_14_changed": False,
            "v0_15_changed": False,
            "s3_started": False,
            "s4_started": False,
            "s5_started": False,
            "s6_started": False,
            "v0_17_started": False,
            "deterministic_replay": "PASS",
            "privacy_scan": "PASS",
            "ready_authorized": False,
            "merge_authorized": False,
            "tag_authorized": False,
            "release_authorized": False,
            "stop": True,
            "external_exact_head_ci": "REQUIRED_SEPARATE_TERMINAL_PR_RECEIPT",
        },
    }
    for value in files.values():
        privacy(value)
    if public.exists():
        raise ValueError("PUBLIC_OUTPUT_ALREADY_EXISTS")
    for name, value in files.items():
        save(public / name, value)
    save(
        public / "manifest-r1.json",
        {
            "files": {name: sha((public / name).read_bytes()) for name in sorted(files)},
            "policy_hash": c["policy_hash"],
        },
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Private retrospective conformal calibration")
    parser.add_argument("phase", choices=("PREPARE", "RUN", "REPLAY", "PUBLISH"))
    parser.add_argument("--s5-output-root", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--replay-output", type=Path)
    parser.add_argument("--public-output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.phase == "PREPARE":
            prepare(args.s5_output_root, args.dataset_root, args.output)
        elif args.phase == "RUN":
            run(args.s5_output_root, args.dataset_root, args.output)
        elif args.phase == "REPLAY":
            if args.replay_output is None or not (args.output / "execution-receipt.json").is_file():
                raise ValueError("PRIMARY_RUN_AND_REPLAY_OUTPUT_REQUIRED")
            verify_contract(args.output)
            prepare(args.s5_output_root, args.dataset_root, args.replay_output)
            run(args.s5_output_root, args.dataset_root, args.replay_output)
        else:
            if args.replay_output is None or args.public_output is None:
                raise ValueError("REPLAY_AND_PUBLIC_OUTPUT_REQUIRED")
            publish(args.output, args.replay_output, args.public_output)
    except Exception as exc:
        code = (
            str(exc)
            if isinstance(exc, ValueError) and re.fullmatch(r"[A-Z][A-Z0-9_]+", str(exc))
            else "UNCERTAINTY_OPERATOR_FAILED"
        )
        print(json.dumps({"result": "FAIL", "code": code}))
        return 1
    print(json.dumps({"result": "PASS", "phase": args.phase, "policy_version": POLICY_VERSION}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
