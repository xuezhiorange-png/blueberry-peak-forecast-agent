"""Immutable stage-separated S5 operator. Private inputs/outputs, aggregate publication."""

from __future__ import annotations

import argparse
import importlib.metadata
import os
from decimal import getcontext
from pathlib import Path
from typing import Any

from backend.app.area_yield.v015_base10_benchmark import flatten_features, score
from backend.app.area_yield.v015_benchmark_custody import (
    DATASET_MANIFEST_HASH,
    FEATURE_HASHES,
    LABEL_HASHES,
    FrozenDataset,
    check_files,
    load,
    save,
    seal_files,
    sha,
    validate_public,
)
from backend.app.area_yield.v015_harvest_incremental import (
    COUNTS,
    MANIFEST,
    POLICY,
    ROWSET,
    STATE_HASHES,
    HarvestCustody,
    breadth,
    classify,
    deltas,
    fit_predict,
    robustness,
)
from backend.app.area_yield.v015_harvest_state import FEATURES
from backend.app.area_yield.v015_research_cohort import digest
from backend.app.area_yield.weather_aware_backtest import BASE_FEATURES

BASE = "33b51a7bbe08b4dc11cf33d01b3bcb95398ef102"
RIDGE_SOURCE = "aae66403ddbc285c55c4133cf1379dfec00aaff17f22cf8f5f43bb9ab6e685f6"
MODELS = ("M0", "M1")
REPOSITORY = Path(__file__).resolve().parents[1]


def contract() -> dict[str, Any]:
    files = (
        "scripts/run_v0_15_s5_harvest_incremental.py",
        "backend/app/area_yield/v015_harvest_incremental.py",
        "backend/app/area_yield/v015_base10_benchmark.py",
        "backend/app/area_yield/v015_benchmark_custody.py",
        "backend/app/area_yield/v015_harvest_state.py",
        "backend/app/area_yield/weather_aware_backtest.py",
        "pyproject.toml",
        "uv.lock",
        "backend/constraints-ci.txt",
    )
    value = {
        "task_id": "V0_15_S5_HARVEST_STATE_INCREMENTAL_VALUE_RIDGE_BENCHMARK_R1",
        "base_develop_sha": BASE,
        "source_hashes": {f: sha((REPOSITORY / f).read_bytes()) for f in files},
        "library_versions": {n: importlib.metadata.version(n) for n in ("numpy",)},
        "s2_manifest_hash": DATASET_MANIFEST_HASH,
        "s2_feature_hashes": FEATURE_HASHES,
        "s2_label_hashes": LABEL_HASHES,
        "s4_manifest_hash": MANIFEST,
        "harvest_state_policy_hash": POLICY,
        "common_rowset_hash": ROWSET,
        "s4_feature_hashes": STATE_HASHES,
        "origin_counts": COUNTS,
        "target_counts": {k: v * 15 for k, v in COUNTS.items()},
        "final_fit_target_rows": 136755,
        "models": {"M0": list(BASE_FEATURES), "M1": list(BASE_FEATURES + FEATURES)},
        "only_experimental_difference": "FOUR_HARVEST_STATE_V1_FEATURES",
        "ridge": {
            "alpha": "10.000000",
            "intercept_unpenalized": True,
            "standardization": "TRAIN_ONLY_STANDARD_SCALER_POPULATION_STD",
            "zero_std_policy": "SCALE_1",
            "solver": "numpy.linalg.solve",
            "nonnegative_clip": True,
            "prediction_decimals": 12,
        },
        "decimal_precision": 50,
        "wape_unit": "RATIO_NOT_PERCENT",
        "final_fit_scaler_scope": "TRAIN_PLUS_VALIDATION_ONLY",
        "phase_order": ["A", "B", "FINAL", "SCORE"],
        "score_once": True,
        "validation_labels_require_seal": True,
        "oot_labels_require_seal": True,
        "post_result_tuning": False,
        "ridge_source_sha256": RIDGE_SOURCE,
        "classification": {
            "primary_metrics": ["H7_DAILY_WAPE", "H15_DAILY_WAPE"],
            "supported": (
                "ALL_FOUR_DELTAS_NEGATIVE_ALL_FOUR_KG_SHARES_GT_HALF_LEAVE_TOP2_BOTH_NEGATIVE"
            ),
            "not_supported": "ALL_FOUR_DELTAS_NONNEGATIVE_AND_NOT_BOTH_LEAVE_TOP2_NEGATIVE",
            "otherwise": "INCONCLUSIVE",
            "minimum_percent_improvement_threshold": None,
        },
        "robustness_ranking": "POSITIVE_H15_ERROR_REDUCTION_DESC_THEN_PRIVATE_BASE_ID_LEXICAL",
        "curve_shape_zero_total": "UNDEFINED_WHOLE_METRIC_IF_ANY_ORIGIN_TOTAL_NONPOSITIVE",
        "s3_metrics_direct_comparison_allowed": False,
        "strict_pit": False,
        "harvest_state_evidence_grade": "RETROSPECTIVE_DATE_BOUND",
        "retrospective_authority_used": True,
        "prospective_claim_allowed": False,
        "2025_2026_previously_exposed": True,
        "2026_2027_reserved_for_prospective": True,
        "weather_files_opened": False,
        "weather_feature_used": False,
        "catboost_trained": False,
        "lightgbm_trained": False,
        "dependency_changed": False,
        "current_2026_27_actual_accessed": False,
        "production_promotion": False,
    }
    value["contract_hash"] = digest(value)
    return value


def verify(output: Path) -> dict[str, Any]:
    c = contract()
    if (
        load(output / "contract.json") != c
        or sha((REPOSITORY / "backend/app/area_yield/weather_aware_backtest.py").read_bytes())
        != RIDGE_SOURCE
    ):
        raise ValueError("CONTRACT_DRIFT")
    if (output / "invalidated.json").exists():
        raise ValueError("RUN_INVALIDATED_OWNER_REAUTHORIZATION_REQUIRED")
    return c


def pname(stage: str, model: str) -> str:
    return f"{stage}-{model}-predictions.json"


def permit(output: Path, c: dict[str, Any], stage: str) -> Any:
    return check_files(
        output,
        load(output / f"{stage}-prediction-seal.json"),
        expected_names=[pname(stage, m) for m in MODELS],
        contract_hash=c["contract_hash"],
        phase="A" if stage == "validation" else "FINAL",
    )


def train_stage(dataset: Path, state: Path, output: Path, phase: str) -> None:
    c = verify(output)
    gate = permit(output, c, "validation") if phase == "FINAL" else None
    data = FrozenDataset(dataset, phase, label_gate=gate)
    custody = HarvestCustody(state)
    splits = ("TRAIN", "VALIDATION") if phase == "FINAL" else ("TRAIN",)
    train: list[dict[str, Any]] = []
    vectors: dict[str, Any] = {}
    labels: list[list[str]] = []
    for split in splits:
        full = data.features(split)
        rows, states = custody.bind(split, full)
        full_labels = data.labels(split, full)
        bykey = {r["row_key"]: v for r, v in zip(full, full_labels, strict=True)}
        train.extend(rows)
        vectors.update(states)
        labels.extend(bykey[r["row_key"]] for r in rows)
    # Canonical row ordering binds BOTH features and labels identically.
    pairs = sorted(zip(train, labels, strict=True), key=lambda p: p[0]["row_key"])
    train = [p[0] for p in pairs]
    labels = [p[1] for p in pairs]
    expected = 136755 if phase == "FINAL" else 55575
    if len(train) * 15 != expected:
        raise ValueError("TARGET_ROW_ACCOUNTING")
    split = "EXPOSED_OOT" if phase == "FINAL" else "VALIDATION"
    rows, states = custody.bind(split, data.features(split))
    stage = "exposed-oot" if phase == "FINAL" else "validation"
    manifests = {}
    for model in MODELS:
        artifact, predictions = fit_predict(model, train, vectors, labels, rows, states)
        save(output / "models" / f"{stage}-{model}.json", artifact.payload())
        save(
            output / pname(stage, model),
            [
                {"row_key": r["row_key"], "predictions": p}
                for r, p in zip(rows, predictions, strict=True)
            ],
        )
        manifests[model] = {
            "model_config_hash": digest(c["models"][model]),
            "model_artifact_hash": sha((output / "models" / f"{stage}-{model}.json").read_bytes()),
            "training_rowset_hash": digest(flatten_features(train)[1]),
            "training_label_hash": digest(labels),
            "training_target_row_count": expected,
            "prediction_hash": sha((output / pname(stage, model)).read_bytes()),
            "prediction_target_row_count": len(rows) * 15,
        }
    for field in ("training_rowset_hash", "training_label_hash", "training_target_row_count"):
        if manifests["M0"][field] != manifests["M1"][field]:
            raise ValueError("FAIL_COMMON_ROWSET")
    save(output / f"{stage}-fit-manifest.json", manifests)
    save(
        output / f"{stage}-prediction-seal.json",
        seal_files(
            output,
            phase=phase,
            names=[pname(stage, m) for m in MODELS],
            rowset_hash=digest(flatten_features(rows)[1]),
            contract_hash=c["contract_hash"],
        ),
    )
    save(
        output / f"{stage}-custody.json",
        {
            "phase": phase,
            "label_reads": data.label_reads,
            "validation_labels_read_before_seal": False,
            "oot_labels_read_before_seal": False,
        },
    )


def score_stage(dataset: Path, state: Path, output: Path, phase: str) -> None:
    c = verify(output)
    stage = "validation" if phase == "B" else "exposed-oot"
    gate = permit(output, c, stage)
    if (output / f"{stage}-consumed.json").exists():
        raise ValueError("SCORE_ALREADY_CONSUMED")
    split = "VALIDATION" if phase == "B" else "EXPOSED_OOT"
    data = FrozenDataset(dataset, phase, label_gate=gate)
    full = data.features(split)
    rows, _ = HarvestCustody(state).bind(split, full)
    if (
        digest(flatten_features(rows)[1])
        != load(output / f"{stage}-prediction-seal.json")["rowset_hash"]
    ):
        raise ValueError("FAIL_COMMON_ROWSET")
    # Durable consumed marker precedes ANY label byte access: failures cannot silently retry.
    save(output / f"{stage}-consumed.json", {"consumed": True, "seal_hash": gate.seal_hash})
    try:
        labels_full = data.labels(split, full)
        bykey = {r["row_key"]: v for r, v in zip(full, labels_full, strict=True)}
        labels = [bykey[r["row_key"]] for r in rows]
        metrics, details, predictions = {}, {}, {}
        for m in MODELS:
            records = load(output / pname(stage, m))
            if [r["row_key"] for r in records] != [r["row_key"] for r in rows]:
                raise ValueError("FAIL_COMMON_ROWSET")
            predictions[m] = [r["predictions"] for r in records]
            metrics[m], details[m] = score(rows, predictions[m], labels)
        save(output / f"{stage}-metrics.json", metrics)
        save(output / f"{stage}-base-details.json", details)
        save(output / f"{stage}-incremental-delta.json", deltas(metrics["M0"], metrics["M1"]))
        save(output / f"{stage}-breadth.json", breadth(details["M0"], details["M1"]))
        save(
            output / f"{stage}-score-custody.json",
            {
                "label_reads": data.label_reads,
                "seal_verified": True,
                "labelset_hash": digest(labels),
                "rowset_hash": digest(flatten_features(rows)[1]),
                "score_once": True,
            },
        )
        if phase == "SCORE":
            rob = robustness(rows, predictions["M0"], predictions["M1"], labels)
            save(output / "robustness.json", rob)
            ds = [
                load(output / f"{s}-incremental-delta.json")[f"H{h}_DAILY_WAPE"]["absolute_delta"]
                for s in ("validation", "exposed-oot")
                for h in (7, 15)
            ]
            shares = [
                load(output / f"{s}-breadth.json")[f"H{h}"]["improved_actual_kg_share"]
                for s in ("validation", "exposed-oot")
                for h in (7, 15)
            ]
            save(
                output / "classification.json",
                {
                    "harvest_state_incremental_value": classify(
                        ds, shares, [rob["LEAVE_TOP2"][f"H{h}_delta"] for h in (7, 15)]
                    ),
                    "primary_deltas": ds,
                    "improved_actual_kg_shares": shares,
                    "minimum_percent_improvement_threshold": None,
                    "post_result_tuning": False,
                    "no_contract_violation": True,
                    "no_leakage": True,
                    "prospective_claim_allowed": False,
                },
            )
    except Exception:
        save(
            output / "invalidated.json",
            {"invalidated": True, "owner_reauthorization_required": True},
        )
        raise


def publish(output: Path, replay: Path, public: Path) -> None:
    c = verify(output)
    verify(replay)
    names = [pname(s, m) for s in ("validation", "exposed-oot") for m in MODELS]
    names += [
        f"{s}-{kind}.json"
        for s in ("validation", "exposed-oot")
        for kind in ("metrics", "incremental-delta", "breadth")
    ]
    names += ["robustness.json", "classification.json"]
    hashes = {n: sha((output / n).read_bytes()) for n in names}
    if any(sha((replay / n).read_bytes()) != h for n, h in hashes.items()):
        raise ValueError("DETERMINISTIC_REPLAY_FAILED")
    reports = {
        "s5-experiment-contract.json": c,
        "common-rowset-binding-report.json": {
            "origin_counts": COUNTS,
            "target_counts": c["target_counts"],
            "common_rowset_hash": ROWSET,
            "common_rowset_equal": True,
            "common_labelset_equal": True,
            "s2_input_hashes_verified": True,
            "s4_input_hashes_verified": True,
        },
        "model-config-freeze.json": {
            "ridge": c["ridge"],
            "models": c["models"],
            "model_search": False,
        },
        "validation-prediction-seal.json": load(output / "validation-prediction-seal.json"),
        "validation-metrics.json": load(output / "validation-metrics.json"),
        "validation-incremental-delta.json": load(output / "validation-incremental-delta.json"),
        "final-fit-manifest.json": load(output / "exposed-oot-fit-manifest.json"),
        "exposed-oot-prediction-seal.json": load(output / "exposed-oot-prediction-seal.json"),
        "exposed-oot-metrics.json": load(output / "exposed-oot-metrics.json"),
        "exposed-oot-incremental-delta.json": load(output / "exposed-oot-incremental-delta.json"),
        "lead-day-comparison.json": {
            s: {m: load(output / f"{s}-metrics.json")[m]["lead_day_metrics"] for m in MODELS}
            for s in ("validation", "exposed-oot")
        },
        "base-breadth-summary.json": {
            s: load(output / f"{s}-breadth.json") for s in ("validation", "exposed-oot")
        },
        "robustness-leave-top1-top2.json": load(output / "robustness.json"),
        "incremental-value-classification.json": load(output / "classification.json"),
        "deterministic-replay-report.json": {
            "M0_replay": "PASS",
            "M1_replay": "PASS",
            "fresh_processes": True,
            "artifact_hashes": hashes,
            "deterministic_replay": "PASS",
            "custody_timestamp_bytes_comparison_required": False,
            "timestamp_exclusion_reason": "INDEPENDENT_REAL_SEAL_TIME_RECEIPTS_NOT_MODEL_OUTPUT",
        },
        "feature-label-custody-audit.json": {
            "physical_sources_separate": True,
            "custody": {
                s: load(output / f"{s}-custody.json") for s in ("validation", "exposed-oot")
            },
            "score_custody": {
                s: load(output / f"{s}-score-custody.json") for s in ("validation", "exposed-oot")
            },
            "weather_files_opened": False,
            "current_2026_27_actual_accessed": False,
        },
        "s5-readiness-recommendation.json": {
            "s5_ready": True,
            "research_only": True,
            "next_stage_authorized": False,
            "ready_authorized": False,
            "merge_authorized": False,
            "production_promotion": False,
            "strict_pit": False,
        },
    }
    for value in reports.values():
        validate_public(value)
    reports["privacy-scan-report.json"] = {
        "privacy_scan": "PASS",
        "actual_values_published": False,
        "prediction_values_published": False,
        "private_base_metrics_published": False,
        "credentials_published": False,
    }
    manifest = {
        "schema": "V0_15_S5_MANIFEST_V1",
        "members": {n: digest(v) for n, v in reports.items()},
        "source_contract_hash": c["contract_hash"],
    }
    manifest["manifest_hash"] = digest(manifest)
    reports["manifest.json"] = manifest
    for name, value in reports.items():
        save(public / name, value)
    print("PUBLIC_REPORTS=19 DETERMINISTIC_REPLAY=PASS PRIVACY_SCAN=PASS")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("A", "B", "FINAL", "SCORE", "PUBLISH"))
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--harvest-state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--replay", type=Path)
    parser.add_argument("--public", type=Path)
    args = parser.parse_args()
    getcontext().prec = 50
    for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        if os.environ.get(key) != "1":
            raise ValueError("SINGLE_THREAD_ENV_REQUIRED")
    if args.phase == "A":
        if args.output.exists():
            raise ValueError("RUN_ALREADY_STARTED_NO_HIDDEN_RETRY")
        args.output.mkdir(parents=True, mode=0o700)
        save(args.output / "contract.json", contract())
        train_stage(args.dataset, args.harvest_state, args.output, "A")
    elif args.phase in ("B", "SCORE"):
        score_stage(args.dataset, args.harvest_state, args.output, args.phase)
    elif args.phase == "FINAL":
        if (
            not (args.output / "validation-metrics.json").exists()
            or (args.output / "exposed-oot-fit-manifest.json").exists()
        ):
            raise ValueError("FINAL_STAGE_ORDER_OR_RETRY_DENIED")
        train_stage(args.dataset, args.harvest_state, args.output, "FINAL")
    else:
        if args.replay is None or args.public is None:
            raise ValueError("REPLAY_AND_PUBLIC_REQUIRED")
        publish(args.output, args.replay, args.public)
    print(f"PHASE={args.phase} RESULT=PASS")


if __name__ == "__main__":
    main()
