"""Owner-authorized offline historical ForecastOps. Never connected to production."""

from __future__ import annotations

import argparse
import builtins
import io
import json
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import patch

from backend.app.area_yield.v015_benchmark_custody import FrozenDataset, check_files
from backend.app.area_yield.v015_harvest_incremental import HarvestCustody
from backend.app.area_yield.v015_research_cohort import digest
from backend.app.forecast_intelligence import forecast_ops as ops
from backend.app.forecast_intelligence.uncertainty import (
    MODEL_ID,
    CalibrationTargetRow,
    calibrate,
    evaluate,
)
from scripts import run_v0_16_s2_uncertainty_calibration as s2

REPOSITORY = Path(__file__).resolve().parents[1]
BASE = "0d14913bcff599a24491c71e9d99ef88021e68db"
TASK = "V0_16_S4_FORECASTOPS_MONITORING_R1"
S2_ROOT = "docs/v0-16/evidence/uncertainty-conformal-calibration-r1"
S3_ROOT = "docs/v0-16/evidence/forecast-attribution-r1"
S2_POLICY = "f35f2700011f440569c9a0140dc9deb482281d60190e8a601b5a503c79013efd"
S3_POLICY = "950d7d4885c4a96b43bba5ad6b586ee7a424ae86482618a8be22ed272039a422"
S2_COVERAGE = "1586144b596e315ef627ee1874a1104229337bae96a86fd4e26d066c55dadd17"
S2_LEADS = "5dd0b3418bc0e8549644a6730f7aef9e42d3b2457424472ec0abdb87d3e28f30"
COMMON = "dbd37e02e19d1fc37942e0accae7d76198bc499d58d66e01104f6833c899445e"
OUTPUT_NAMES = (
    "forecastops-origin-binding.json",
    "forecastops-daily-binding.json",
    "forecastops-horizon-gates.json",
    "forecastops-point-scoring-detail.json",
    "forecastops-interval-detail.json",
    "monitoring-snapshot.json",
    "s2-coverage-summary.json",
    "s2-lead-summary.json",
)
load, sha, save = s2.load, s2.sha, s2.save


@contextmanager
def label_access(allowed: Path | None) -> Iterator[None]:
    original_io, original_builtin = io.open, builtins.open

    def checked(path: Any) -> None:
        if isinstance(path, (str, os.PathLike)):
            p = Path(path).resolve()
            if "label_zone" in p.parts and (allowed is None or p != allowed.resolve()):
                raise ValueError("LABEL_ACCESS_FORBIDDEN")

    def io_open(file: Any, *args: Any, **kwargs: Any) -> Any:
        checked(file)
        return original_io(file, *args, **kwargs)

    def builtin_open(file: Any, *args: Any, **kwargs: Any) -> Any:
        checked(file)
        return original_builtin(file, *args, **kwargs)

    with patch("io.open", io_open), patch("builtins.open", builtin_open):
        yield


def public_authority() -> dict[str, str]:
    verified = s2.verify_public()
    frozen_s2 = load(REPOSITORY / S2_ROOT / "conformal-policy-r1.json")
    frozen_s3 = load(REPOSITORY / S3_ROOT / "attribution-policy-r1.json")
    if (
        digest(s2.policy()) != S2_POLICY
        or frozen_s2["policy_hash"] != S2_POLICY
        or digest(frozen_s2["policy"]) != S2_POLICY
        or frozen_s3["policy_hash"] != S3_POLICY
        or digest(frozen_s3["policy"]) != S3_POLICY
    ):
        raise ValueError("UPSTREAM_POLICY_DRIFT")
    if verified != frozen_s2["policy"]["source_evidence_sha256"]:
        raise ValueError("UPSTREAM_SOURCE_DRIFT")
    for root in (S2_ROOT, S3_ROOT):
        manifest = load(REPOSITORY / root / "manifest-r1.json")
        for name, expected in manifest["files"].items():
            path = REPOSITORY / root / name
            if sha(path.read_bytes()) != expected:
                raise ValueError("UPSTREAM_EVIDENCE_DRIFT")
            verified[str(path.relative_to(REPOSITORY))] = expected
        verified[f"{root}/manifest-r1.json"] = sha(
            (REPOSITORY / root / "manifest-r1.json").read_bytes()
        )
    if (
        sha((REPOSITORY / S2_ROOT / "coverage-summary-r1.json").read_bytes()) != S2_COVERAGE
        or sha((REPOSITORY / S2_ROOT / "lead-day-coverage-r1.json").read_bytes()) != S2_LEADS
    ):
        raise ValueError("S2_INTERVAL_REPLAY_PARITY_FAILED")
    for name in (
        "backend/app/forecast_intelligence/forecast_ops.py",
        "scripts/run_v0_16_s4_forecastops_monitoring.py",
    ):
        verified[name] = sha((REPOSITORY / name).read_bytes())
    return verified


def policy() -> dict[str, Any]:
    return {
        "policy_version": ops.POLICY_VERSION,
        "scoring_policy_version": ops.SCORING_POLICY_VERSION,
        "actual_match_policy_version": ops.ACTUAL_MATCH_POLICY_VERSION,
        "issuance_coverage_policy_version": ops.ISSUANCE_COVERAGE_POLICY_VERSION,
        "quality_trend_policy_version": ops.QUALITY_TREND_POLICY_VERSION,
        "source_bindings": dict(s2.PINS) | {"common_rowset_hash": COMMON},
        "s2_policy_hash": S2_POLICY,
        "s3_policy_hash": S3_POLICY,
        "s2_coverage_summary_hash": S2_COVERAGE,
        "s2_lead_day_summary_hash": S2_LEADS,
        "expected_issuance_authority": "V0_15_S5_COMMON_ROWSET",
        "issuance_semantics": "RETROSPECTIVE_EVIDENCE_ISSUANCE_COVERAGE_NOT_PRODUCTION_SLA",
        "horizons": list(ops.HORIZONS),
        "horizon_semantics": "PREFIX_D1_THROUGH_DH",
        "lead_metrics": [1, 3, 7, 15],
        "actual_match": "EXACT_BASE_ID_TARGET_DATE",
        "actual_projection_authority": (
            "FROZEN_LABELS_VERIFIED_EQUAL_OVERLAPPING_REFERENCES_COLLAPSE_ONCE_CONFLICT_REJECTED"
        ),
        "actual_states": ["CONFIRMED_QUANTITY", "CONFIRMED_ZERO", "MISSING"],
        "missing_actual_is_zero": False,
        "partial_is_complete": False,
        "maturity": "EVALUATION_LOCAL_DATE_STRICTLY_AFTER_HORIZON_END",
        "evaluation_as_of_derivation": "MAX_FROZEN_TARGET_DATE_PLUS_ONE_DAY",
        "error_sign": "FORECAST_MINUS_ACTUAL",
        "decimal_precision": 50,
        "display_quantization": False,
        "daily_wape": "SUM_ABS_DAILY_ERROR_DIV_SUM_ACTUAL",
        "daily_mae_kg": "SUM_ABS_DAILY_ERROR_DIV_ROW_COUNT",
        "daily_bias_kg": "SUM_SIGNED_DAILY_ERROR_DIV_ROW_COUNT",
        "cumulative_wape": "SUM_ABS_PER_ORIGIN_HORIZON_TOTAL_ERROR_DIV_SUM_ACTUAL",
        "zero_denominator": "NOT_COMPUTABLE_ZERO_ACTUAL_DENOMINATOR",
        "trend_metrics": [
            "daily_wape",
            "daily_mae_kg",
            "absolute_daily_bias_kg",
            "cumulative_wape",
        ],
        "trend_rule": "ALL_EQUAL_UNCHANGED_ALL_LE_IMPROVED_ALL_GE_DEGRADATION_ELSE_MIXED",
        "production_alert_thresholds_established": False,
        "minimum_production_sample_count": None,
        "strict_pit": False,
        "historical_actual_available_at_proven": False,
        "retrospective_authority_used": True,
        "current_season_actual_read": False,
        "point_forecast_reexecuted": False,
        "model_training_executed": False,
        "point_forecast_is_proven_p50": False,
        "true_quantile_semantics_established": False,
        "no_automatic_action": True,
        "production_use_approved": False,
        "privacy_policy": "PRIVATE_ROWS_PUBLIC_AGGREGATES_HASHES_ONLY",
        "source_evidence_sha256": public_authority(),
    }


def output_guard(output: Path, sources: list[Path]) -> None:
    p = output.resolve()
    if any(
        p == x.resolve() or p.is_relative_to(x.resolve()) or x.resolve().is_relative_to(p)
        for x in [REPOSITORY, *sources]
    ):
        raise ValueError("PRIVATE_OUTPUT_LOCATION_INVALID")


def sources(s5: Path, dataset: Path, harvest: Path) -> tuple[Any, Any, Any, Any, dict[str, str]]:
    predictions, binding = s2.sources(s5, dataset)
    seal = load(s5 / "exposed-oot-prediction-seal.json")
    permit = check_files(
        s5,
        seal,
        expected_names=["exposed-oot-M0-predictions.json", "exposed-oot-M1-predictions.json"],
        contract_hash=load(s5 / "contract.json")["contract_hash"],
        phase="FINAL",
    )
    frozen = FrozenDataset(dataset, "SCORE", label_gate=permit)
    full = frozen.features("EXPOSED_OOT")
    common, _ = HarvestCustody(harvest).bind("EXPOSED_OOT", full)
    if len(common) != s2.ORIGINS or {r["row_key"] for r in common} != {
        r["row_key"] for r in predictions
    }:
        raise ValueError("ROWSET_ACCOUNTING_FAILED")
    for name, path in {
        "m0_seal_member": s5 / "exposed-oot-M0-predictions.json",
        "base10_features": dataset / "feature_zone/exposed_oot-base10.json",
        "common_rowset": harvest / "audit/harvest-state-common-rowset.json",
        "harvest_manifest": harvest / "manifest.json",
        "harvest_features": harvest / "feature_zone/harvest-state-v1-exposed-oot.json",
    }.items():
        binding[name] = sha(path.read_bytes())
    return frozen, full, common, predictions, binding


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
        or c["policy"] != policy()
        or c["policy_hash"] != digest(c["policy"])
        or digest({k: v for k, v in c.items() if k != "contract_hash"}) != c["contract_hash"]
    ):
        raise ValueError("FORECASTOPS_CONTRACT_DRIFT")
    return dict(c)


def point_parity(snapshot: dict[str, Any]) -> None:
    expected = load(REPOSITORY / s2.EVIDENCE / "exposed-oot-metrics.json")["M1"]
    for h, key in (
        (7, "H7_DAILY_WAPE"),
        (15, "H15_DAILY_WAPE"),
        (7, "H7_CUMULATIVE_WAPE"),
        (15, "H15_CUMULATIVE_WAPE"),
    ):
        name = "daily_wape" if "DAILY" in key else "cumulative_wape"
        if snapshot["point_quality"][f"H{h}"][name] != expected[key]:
            raise ValueError("LOCKED_SCORING_PARITY_FAILED")
    for name, key in (("daily_mae_kg", "DAILY_MAE_KG"), ("daily_bias_kg", "BIAS_KG")):
        if snapshot["point_quality"]["H15"][name] != expected[key]:
            raise ValueError("LOCKED_SCORING_PARITY_FAILED")


def run(s5: Path, dataset: Path, harvest: Path, output: Path) -> None:
    output_guard(output, [s5, dataset, harvest])
    with label_access(None):
        c = verify_contract(output)
        frozen, full, common, predictions, before = sources(s5, dataset, harvest)
        if load(output / "source-binding-prelabel.json") != {
            "source_hashes": before,
            "contract_hash": c["contract_hash"],
            "label_bytes_read": False,
        }:
            raise ValueError("SOURCE_BINDING_DRIFT")
    save(output / "run-started.json", {"contract_hash": c["contract_hash"]})
    save(output / "process-receipt.json", {"process_id": os.getpid()})
    label_path = dataset / "label_zone/exposed_oot-labels.json"
    with label_access(label_path):
        raw = label_path.read_bytes()
        if sha(raw) != s2.PINS["full_label_file_hash"]:
            raise ValueError("BLOCKED_LABELSET_DRIFT")
        envelope = json.loads(raw, parse_float=s2.reject_float, parse_constant=s2.reject_float)
        if any(r["season"] == "2026-2027" for r in envelope):
            raise ValueError("FAIL_CURRENT_SEASON_ACTUAL_PRESENT")
        if len({r["row_key"] for r in envelope}) != len(envelope):
            raise ValueError("ACTUAL_DUPLICATE_CONFLICT")
        all_labels = frozen.labels("EXPOSED_OOT", full)
    label_map = {r["row_key"]: v for r, v in zip(full, all_labels, strict=True)}
    common = sorted(common, key=lambda r: r["row_key"])
    filtered = [label_map[r["row_key"]] for r in common]
    if digest(filtered) != s2.PINS["filtered_labelset_hash"]:
        raise ValueError("BLOCKED_LABELSET_DRIFT")
    prediction_map = {r["row_key"]: r["predictions"] for r in predictions}
    identity = {
        "model_id": MODEL_ID,
        "policy_version": "S5_FIXED_RESEARCH",
        "schema_version": "SEALED_15_TARGETS_V1",
        "source_split": "EXPOSED_OOT",
        "prediction_hash": s2.PINS["prediction_hash"],
        "model_artifact_hash": s2.PINS["model_artifact_hash"],
        "model_config_hash": s2.PINS["model_config_hash"],
    }
    forecasts, targets = [], []
    actual_map: dict[tuple[str, date], ops.ActualPoint] = {}
    for r in common:
        origin = datetime.fromisoformat(r["forecast_origin"])
        daily = []
        for d, (target, p, a) in enumerate(
            zip(
                r["target_dates"],
                prediction_map[r["row_key"]],
                label_map[r["row_key"]],
                strict=True,
            ),
            1,
        ):
            target_date = date.fromisoformat(target)
            point, actual = s2.numeric(p), s2.numeric(a)
            daily.append(ops.DailyForecast(d, target_date, point))
            targets.append(
                CalibrationTargetRow(
                    f"{r['row_key']}#D{d:02}",
                    r["base_id"],
                    r["season"],
                    origin,
                    d,
                    target_date,
                    point,
                    actual,
                )
            )
            actual_point = ops.ActualPoint(r["base_id"], r["season"], target_date, actual)
            key = r["base_id"], target_date
            if key in actual_map and actual_map[key] != actual_point:
                raise ValueError("ACTUAL_DUPLICATE_CONFLICT")
            actual_map[key] = actual_point
        forecasts.append(
            ops.ForecastOrigin(r["base_id"], r["season"], origin, tuple(daily), dict(identity))
        )
    expected = [ops.slot(f) for f in forecasts]
    if len(expected) != s2.ORIGINS or len(targets) != s2.TARGETS:
        raise ValueError("ROWSET_ACCOUNTING_FAILED")
    interval_rows = calibrate(targets)
    coverage, leads, _, _ = evaluate(interval_rows)
    if digest(coverage) != S2_COVERAGE or digest(leads) != S2_LEADS:
        raise ValueError("S2_INTERVAL_REPLAY_PARITY_FAILED")
    intervals = []
    for r in interval_rows:
        interval_slot = r["base_id"], r["season"], r["forecast_origin"]
        for level in (80, 90):
            pi = r[f"prediction_interval_{level}"]
            upper = r[f"upper_planning_bound_{level}"]
            intervals.append(
                ops.IntervalPoint(
                    interval_slot,
                    r["lead_day"],
                    level,
                    Decimal(pi["lower_kg"]) if pi else None,
                    Decimal(pi["upper_kg"]) if pi else None,
                    Decimal(upper) if upper is not None else None,
                )
            )
    as_of = datetime.combine(
        max(r.target_date for r in targets) + timedelta(days=1), time(), tzinfo=ops.SHANGHAI
    )
    snapshot = ops.monitor(
        forecasts,
        list(actual_map.values()),
        expected_slots=expected,
        source_identity=identity,
        evaluation_as_of=as_of,
        intervals=intervals,
        interval_policy_hash=S2_POLICY,
    )
    point_parity(snapshot)
    if snapshot["integrity_status"] != "PASS" or any(
        v["scorable_origin_count"] != s2.ORIGINS for v in snapshot["point_quality"].values()
    ):
        raise ValueError("REAL_HISTORICAL_ACCOUNTING_FAILED")
    for h in (7, 15):
        for name, metric in coverage[f"H{h}"].items():
            if (
                snapshot["interval_quality"][f"H{h}"][name]["empirical_coverage"]
                != metric["empirical_coverage"]
            ):
                raise ValueError("S2_INTERVAL_REPLAY_PARITY_FAILED")
    gates = snapshot.pop("private_gates")
    private_daily = [
        {
            "row_key": r.row_key,
            "base_id": r.base_id,
            "season": r.season,
            "forecast_origin": r.forecast_origin.isoformat(),
            "lead_day": r.lead_day,
            "target_date": r.target_date.isoformat(),
            "point_forecast_kg": str(r.point_prediction_kg),
            "actual_kg": str(r.actual_kg),
            "actual_state": "CONFIRMED_ZERO" if r.actual_kg == 0 else "CONFIRMED_QUANTITY",
        }
        for r in sorted(targets, key=lambda r: (r.forecast_origin, r.base_id, r.lead_day))
    ]
    payloads = {
        "forecastops-origin-binding.json": sorted(
            [{"semantic_slot": list(ops.slot(f)), "source_identity": identity} for f in forecasts],
            key=lambda r: tuple(r["semantic_slot"]),
        ),
        "forecastops-daily-binding.json": private_daily,
        "forecastops-horizon-gates.json": gates,
        "forecastops-point-scoring-detail.json": snapshot["point_quality"],
        "forecastops-interval-detail.json": interval_rows,
        "monitoring-snapshot.json": snapshot,
        "s2-coverage-summary.json": coverage,
        "s2-lead-summary.json": leads,
    }
    with label_access(None):
        *_, after = sources(s5, dataset, harvest)
    with label_access(label_path):
        if before != after or sha(label_path.read_bytes()) != s2.PINS["full_label_file_hash"]:
            raise ValueError("SOURCE_ARTIFACT_MUTATION")
    for name, value in payloads.items():
        save(output / name, value)
    save(
        output / "execution-receipt.json",
        {
            "contract_hash": c["contract_hash"],
            "policy_hash": c["policy_hash"],
            "label_read_stage": "RUN_AFTER_ORIGINAL_S5_SEAL_GATE",
            "label_file_hash": s2.PINS["full_label_file_hash"],
            "filtered_common_labelset_hash": digest(filtered),
            "base_count": len({r.base_id for r in targets}),
            "origin_count": len(forecasts),
            "target_row_count": len(targets),
            "s2_replay_parity": "PASS",
            "source_artifact_mutation": False,
            "current_season_actual_read": False,
            "artifact_hashes": {name: sha((output / name).read_bytes()) for name in OUTPUT_NAMES},
        },
    )


def privacy(value: Any) -> None:
    s2.privacy(value)
    if isinstance(value, dict):
        if {
            "row_key",
            "forecast_origin",
            "target_date",
            "daily_forecast",
            "daily_actual",
            "interval_rows",
            "secret",
            "credentials",
            "database_url",
        } & value.keys():
            raise ValueError("PUBLIC_PRIVATE_DATA_LEAK")
        for item in value.values():
            privacy(item)
    elif isinstance(value, list):
        for item in value:
            privacy(item)


def publish(primary: Path, replay: Path, public: Path) -> None:
    if primary.resolve() == replay.resolve() or load(primary / "process-receipt.json") == load(
        replay / "process-receipt.json"
    ):
        raise ValueError("FRESH_PROCESS_REPLAY_REQUIRED")
    c = verify_contract(primary)
    receipt = load(primary / "execution-receipt.json")
    if verify_contract(replay) != c or receipt != load(replay / "execution-receipt.json"):
        raise ValueError("DETERMINISTIC_REPLAY_FAILED")
    for name in ("contract.json", "source-binding-prelabel.json", *OUTPUT_NAMES):
        raw = (primary / name).read_bytes()
        if raw != (replay / name).read_bytes() or (
            name in OUTPUT_NAMES and sha(raw) != receipt["artifact_hashes"][name]
        ):
            raise ValueError("DETERMINISTIC_REPLAY_FAILED")
    snapshot = load(primary / "monitoring-snapshot.json")
    if digest({k: v for k, v in snapshot.items() if k != "result_hash"}) != snapshot["result_hash"]:
        raise ValueError("MONITORING_RESULT_HASH_DRIFT")
    files = {
        "monitoring-policy-r1.json": c,
        "source-binding-r1.json": load(primary / "source-binding-prelabel.json")
        | {
            "label_read_stage": receipt["label_read_stage"],
            "label_file_hash": receipt["label_file_hash"],
            "filtered_common_labelset_hash": receipt["filtered_common_labelset_hash"],
        },
        "point-quality-summary-r1.json": {
            "horizons": snapshot["point_quality"],
            "lead_days": snapshot["lead_quality"],
        },
        "interval-quality-summary-r1.json": snapshot["interval_quality"],
        "completeness-summary-r1.json": snapshot["completeness"],
        "issuance-coverage-summary-r1.json": snapshot["issuance"],
        "integrity-summary-r1.json": {
            k: snapshot[k]
            for k in (
                "integrity_status",
                "schema_integrity_status",
                "source_hash_match",
                "duplicate_issuance_count",
                "duplicate_target_row_count",
                "duplicate_actual_conflict_count",
                "result_hash",
            )
        }
        | {"policy_hash_match": True, "rowset_hash_match": True},
        "runtime-observability-summary-r1.json": ops.runtime_observability(
            [], datetime.fromisoformat(snapshot["evaluation_as_of"])
        )
        | {
            "runtime_schedule_authority_available": False,
            "runtime_start_timestamp_authority_available": False,
            "runtime_completion_timestamp_authority_available": False,
        },
        "deterministic-replay-report-r1.json": {
            "result": "PASS",
            "fresh_processes_verified": True,
            "artifact_hashes": receipt["artifact_hashes"],
        },
        "privacy-scan-report-r1.json": {
            "result": "PASS",
            "public_private_data_leak": False,
            "private_rows_committed": False,
        },
        "v0.16-s4-forecastops-monitoring-r1.json": {
            "task_id": TASK,
            "version": "0.16.0",
            "stage": "S4",
            "base_main_sha": BASE,
            "engineering_result": "PASS",
            "forecastops_policy_hash": c["policy_hash"],
            "result_hash": snapshot["result_hash"],
            "base_count": receipt["base_count"],
            "origin_count": receipt["origin_count"],
            "target_row_count": receipt["target_row_count"],
            "s2_replay_parity": "PASS",
            "v0_15_metric_parity": "PASS",
            "quality_trend_status": "NO_REFERENCE",
            "production_alert_thresholds_established": False,
            "production_alert_status": "NOT_CONFIGURED_NO_PRODUCTION_THRESHOLDS",
            "minimum_production_sample_count": None,
            "historical_exposed_oot_label_read": True,
            "current_season_actual_read": False,
            "current_season_actual_import": False,
            "current_season_actual_scoring": False,
            "strict_pit": False,
            "historical_actual_available_at_proven": False,
            "retrospective_authority_used": True,
            "point_forecast_reexecuted": False,
            "model_training_executed": False,
            "model_refit_executed": False,
            "model_tuning_executed": False,
            "source_artifact_mutation": False,
            "db_migration_created": False,
            "http_forecastops_api_implemented": False,
            "mcp_forecastops_tools_implemented": False,
            "scheduler_created": False,
            "frontend_changed": False,
            "production_alert_delivery_implemented": False,
            "region_actual_scoring_implemented": False,
            "company_actual_scoring_implemented": False,
            "s1_changed": False,
            "s2_changed": False,
            "s3_changed": False,
            "v0_14_changed": False,
            "v0_14_runtime_touched": False,
            "v0_15_changed": False,
            "s5_started": False,
            "s6_started": False,
            "v0_17_started": False,
            "deterministic_replay": "PASS",
            "privacy_scan": "PASS",
            "s4_formal_complete": False,
            "formal_completion_requires_owner_merge_and_post_merge_main_ci": True,
            "external_exact_head_ci": "REQUIRED_SEPARATE_TERMINAL_PR_RECEIPT",
            "ready_authorized": False,
            "merge_authorized": False,
            "tag_authorized": False,
            "release_authorized": False,
            "stop": True,
        },
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
            "policy_hash": c["policy_hash"],
            "result_hash": snapshot["result_hash"],
        },
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline frozen historical ForecastOps")
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
            else "FORECASTOPS_OPERATOR_FAILED"
        )
        print(json.dumps({"result": "FAIL", "code": code}))
        return 1
    print(json.dumps({"result": "PASS", "phase": args.phase, "policy_version": ops.POLICY_VERSION}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
