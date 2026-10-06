"""Four explicitly separated S3 stages; private numerical outputs, public aggregates."""

from __future__ import annotations

import argparse
import importlib.metadata
import os
from datetime import UTC, datetime
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any

from backend.app.area_yield.v015_base10_benchmark import (
    CANDIDATES,
    EXPECTED_COUNTS,
    SEED,
    complexity,
    direction,
    fit_model,
    flatten_features,
    score,
    select_candidate,
)
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
from backend.app.area_yield.v015_research_cohort import digest
from backend.app.area_yield.weather_aware_backtest import BASE_FEATURES

BASE_SHA = "52d152fd9113395d62eaf007745592672adb5185"
RIDGE_SOURCE_SHA = "aae66403ddbc285c55c4133cf1379dfec00aaff17f22cf8f5f43bb9ab6e685f6"
LIBRARIES = {"catboost": "1.2.10", "lightgbm": "4.7.0"}
FAMILIES = ("RIDGE", "CATBOOST", "LIGHTGBM")


def contract() -> dict[str, Any]:
    repository = Path(__file__).resolve().parents[1]
    source_files = (
        "scripts/run_v0_15_s3_base10_benchmark.py",
        "backend/app/area_yield/v015_base10_benchmark.py",
        "backend/app/area_yield/v015_benchmark_custody.py",
        "pyproject.toml",
        "uv.lock",
        "backend/constraints-ci.txt",
    )
    value = {
        "task_id": "V0_15_S3_BASE10_RIDGE_CATBOOST_LIGHTGBM_BENCHMARK_R1",
        "base_sha": BASE_SHA,
        "execution_source_hashes": {
            name: sha((repository / name).read_bytes()) for name in source_files
        },
        "dataset_manifest_hash": DATASET_MANIFEST_HASH,
        "feature_hashes": FEATURE_HASHES,
        "label_hashes": LABEL_HASHES,
        "features": list(BASE_FEATURES),
        "origin_counts": EXPECTED_COUNTS,
        "target_rows": {k: n * 15 for k, n in EXPECTED_COUNTS.items()},
        "final_fit_target_rows": 152295,
        "candidates": CANDIDATES,
        "model_versions": LIBRARIES,
        "ridge_authority_source_sha256": RIDGE_SOURCE_SHA,
        "seed": SEED,
        "cpu_only": True,
        "threads": 1,
        "prediction_format": "NONNEGATIVE_CLIP_THEN_12DP",
        "validation_selection": [
            "H15_DAILY_WAPE",
            "H7_DAILY_WAPE",
            "DAILY_MAE_KG",
            "LOWER_COMPLEXITY",
            "LEXICAL_CANDIDATE_ID",
        ],
        "complexity_order": {
            name: list(complexity(name)) for name in CANDIDATES if name != "RIDGE"
        },
        "research_family_simplicity_order": list(FAMILIES),
        "dynamic_rowset": False,
        "origin_reweighting": False,
        "target_deduplication": False,
        "decimal_precision": 50,
        "wape_unit": "RATIO_NOT_PERCENT",
        "curve_shape_error": (
            "SUM_ABS_PRED_SCALED_TO_ORIGIN_ACTUAL_TOTAL_MINUS_ACTUAL_DIV_SUM_ACTUAL"
        ),
        "curve_shape_zero_total": "UNDEFINED_WHOLE_METRIC_IF_ANY_ORIGIN_TOTAL_NONPOSITIVE",
        "peak_ties": "EARLIEST",
        "rolling7_windows": 9,
        "strict_pit": False,
        "retrospective_authority_used": True,
        "2025_2026_previously_exposed": True,
        "2026_2027_reserved_for_prospective": True,
        "prospective_claim_allowed": False,
        "production_promotion": False,
        "weather_feature_used": False,
        "harvest_state_feature_used": False,
        "binary_hash_determinism_required": False,
        "prediction_hash_deterministic": True,
        "label_hash_verification": "ACTUAL_BYTES_ONLY_AT_AUTHORIZED_POST_SEAL_UNLOCK",
    }
    value["contract_hash"] = digest(value)
    return value


def verify_contract(output: Path, repository: Path) -> dict[str, Any]:
    current = contract()
    if load(output / "contract.json") != current:
        raise ValueError("CONTRACT_CONFIG_DRIFT")
    if (
        sha((repository / "backend/app/area_yield/weather_aware_backtest.py").read_bytes())
        != RIDGE_SOURCE_SHA
    ):
        raise ValueError("RIDGE_AUTHORITY_DRIFT")
    for name, version in LIBRARIES.items():
        if importlib.metadata.version(name) != version:
            raise ValueError("MODEL_DEPENDENCY_DRIFT")
    if (output / "invalidated.json").exists():
        raise ValueError("RUN_INVALIDATED_OWNER_REAUTHORIZATION_REQUIRED")
    return current


def prediction_name(stage: str, candidate: str) -> str:
    return f"{stage}-{candidate}-predictions.json"


def matrix_labels(vectors: list[list[str]]) -> list[str]:
    return [v for row in vectors for v in row]


def train_predict(
    candidate: str,
    train: list[dict[str, Any]],
    labels: list[list[str]],
    predict_rows: list[dict[str, Any]],
    output: Path,
    stage: str,
) -> dict[str, Any]:
    model = fit_model(candidate, train, matrix_labels(labels))
    predictions = model.predict(predict_rows)
    if len(predictions) != len(predict_rows) * 15:
        raise ValueError("MODEL_OUTPUT_INVALID")
    records = [
        {"row_key": row["row_key"], "predictions": predictions[i * 15 : (i + 1) * 15]}
        for i, row in enumerate(sorted(predict_rows, key=lambda r: r["row_key"]))
    ]
    name = prediction_name(stage, candidate)
    save(output / name, records)
    models = output / "models"
    models.mkdir(exist_ok=True, mode=0o700)
    suffix = "json" if candidate == "RIDGE" else ("cbm" if candidate.startswith("CB") else "txt")
    path = models / f"{stage}-{candidate}.{suffix}"
    if path.exists():
        raise ValueError("MODEL_ARTIFACT_ALREADY_EXISTS")
    if candidate == "RIDGE":
        save(path, model.artifact.payload())
    elif candidate.startswith("CB"):
        model.artifact.save_model(str(path))
    else:
        model.artifact.booster_.save_model(str(path))
    path.chmod(0o600)
    _, keys = flatten_features(train)
    return {
        "candidate": candidate,
        "model_library": "numpy"
        if candidate == "RIDGE"
        else ("catboost" if candidate.startswith("CB") else "lightgbm"),
        "model_library_version": importlib.metadata.version(
            "numpy"
            if candidate == "RIDGE"
            else ("catboost" if candidate.startswith("CB") else "lightgbm")
        ),
        "config_hash": digest(CANDIDATES[candidate]),
        "train_input_hash": digest(train),
        "train_rowset_hash": digest(keys),
        "train_label_hash": digest(labels),
        "train_target_row_count": len(keys),
        "model_artifact_hash": sha(path.read_bytes()),
        "prediction_hash": sha((output / name).read_bytes()),
        "prediction_target_row_count": len(predictions),
        "binary_hash_determinism_required": False,
        "prediction_hash_deterministic": True,
    }


def read_predictions(
    output: Path, stage: str, candidate: str, features: list[dict[str, Any]]
) -> list[list[str]]:
    records = load(output / prediction_name(stage, candidate))
    if [r["row_key"] for r in records] != [r["row_key"] for r in features]:
        raise ValueError("COMMON_ROWSET")
    return [r["predictions"] for r in records]


def verify_common_training(manifests: dict[str, Any]) -> None:
    for field in (
        "train_input_hash",
        "train_label_hash",
        "train_rowset_hash",
        "train_target_row_count",
    ):
        if len({m[field] for m in manifests.values()}) != 1:
            raise ValueError("MODEL_SPECIFIC_ROWSET")


def phase_a(dataset: Path, output: Path, repository: Path) -> None:
    if output.exists():
        raise ValueError("RUN_ALREADY_STARTED_NO_HIDDEN_RETRY")
    output.mkdir(parents=True, mode=0o700)
    save(output / "contract.json", contract())  # Frozen before TRAIN/VALIDATION labels.
    c = verify_contract(output, repository)
    data = FrozenDataset(dataset, "A")
    train, validation = data.features("TRAIN"), data.features("VALIDATION")
    labels = data.labels("TRAIN", train)
    manifests = {
        name: train_predict(name, train, labels, validation, output, "validation")
        for name in CANDIDATES
    }
    verify_common_training(manifests)
    save(output / "phase-a-model-manifest.json", manifests)
    _, keys = flatten_features(validation)
    seal = seal_files(
        output,
        phase="A",
        names=[prediction_name("validation", k) for k in CANDIDATES],
        rowset_hash=digest(keys),
        contract_hash=c["contract_hash"],
    )
    save(output / "validation-prediction-seal.json", seal)
    save(
        output / "phase-a-custody.json",
        {
            "label_reads": data.label_reads,
            "validation_labels_read": False,
            "oot_labels_read": False,
        },
    )


def validation_permit(output: Path, c: dict[str, Any]) -> Any:
    return check_files(
        output,
        load(output / "validation-prediction-seal.json"),
        expected_names=[prediction_name("validation", k) for k in CANDIDATES],
        contract_hash=c["contract_hash"],
        phase="A",
    )


def phase_b(dataset: Path, output: Path, repository: Path) -> None:
    c = verify_contract(output, repository)
    permit = validation_permit(output, c)
    if (output / "selection.json").exists():
        raise ValueError("VALIDATION_ALREADY_CONSUMED")
    data = FrozenDataset(dataset, "B", label_gate=permit)
    rows = data.features("VALIDATION")
    if (
        digest(flatten_features(rows)[1])
        != load(output / "validation-prediction-seal.json")["rowset_hash"]
    ):
        raise ValueError("COMMON_ROWSET")
    try:
        labels = data.labels("VALIDATION", rows)
        metrics, details = {}, {}
        for name in CANDIDATES:
            metrics[name], details[name] = score(
                rows, read_predictions(output, "validation", name, rows), labels
            )
        save(output / "validation-metrics.json", metrics)
        save(output / "validation-base-details.json", details)
        selected = {
            "RIDGE": "RIDGE",
            "CATBOOST": select_candidate({k: metrics[k] for k in CANDIDATES if k.startswith("CB")}),
            "LIGHTGBM": select_candidate(
                {k: metrics[k] for k in CANDIDATES if k.startswith("LGB")}
            ),
        }
        selection = {
            "selected": selected,
            "source": "VALIDATION_ONLY",
            "validation_metrics_hash": digest(metrics),
            "contract_hash": c["contract_hash"],
            "validation_seal_hash": permit.seal_hash,
        }
        selection["selection_hash"] = digest(selection)
        save(output / "selection.json", selection)
        save(
            output / "phase-b-custody.json",
            {
                "label_reads": data.label_reads,
                "label_opened_at": datetime.now(UTC).isoformat(),
                "verified_seal_hash": permit.seal_hash,
            },
        )
    except Exception:
        save(output / "invalidated.json", {"phase": "B", "owner_reauthorization_required": True})
        raise


def selection_verified(output: Path, c: dict[str, Any]) -> dict[str, str]:
    value = load(output / "selection.json")
    if value["selection_hash"] != digest({k: v for k, v in value.items() if k != "selection_hash"}):
        raise ValueError("SELECTION_DRIFT")
    if value["contract_hash"] != c["contract_hash"] or value["source"] != "VALIDATION_ONLY":
        raise ValueError("SELECTION_DRIFT")
    if value["validation_seal_hash"] != validation_permit(output, c).seal_hash:
        raise ValueError("SELECTION_DRIFT")
    metrics = load(output / "validation-metrics.json")
    if digest(metrics) != value["validation_metrics_hash"]:
        raise ValueError("SELECTION_DRIFT")
    expected = {
        "RIDGE": "RIDGE",
        "CATBOOST": select_candidate({k: metrics[k] for k in CANDIDATES if k.startswith("CB")}),
        "LIGHTGBM": select_candidate({k: metrics[k] for k in CANDIDATES if k.startswith("LGB")}),
    }
    if value["selected"] != expected:
        raise ValueError("SELECTION_DRIFT")
    return expected


def final_fit(dataset: Path, output: Path, repository: Path) -> None:
    c = verify_contract(output, repository)
    if (output / "oot-prediction-seal.json").exists() or (output / "oot-metrics.json").exists():
        raise ValueError("FINAL_FIT_ALREADY_SEALED_OR_OOT_CONSUMED")
    permit = validation_permit(output, c)
    selected = selection_verified(output, c)
    data = FrozenDataset(dataset, "FINAL", label_gate=permit)
    train, validation, oot = [data.features(k) for k in EXPECTED_COUNTS]
    pairs = sorted(
        zip(
            train + validation,
            data.labels("TRAIN", train) + data.labels("VALIDATION", validation),
            strict=True,
        ),
        key=lambda pair: pair[0]["row_key"],
    )
    rows, labels = [p[0] for p in pairs], [p[1] for p in pairs]
    manifests = {
        family: train_predict(candidate, rows, labels, oot, output, "oot")
        for family, candidate in selected.items()
    }
    verify_common_training(manifests)
    for model_manifest in manifests.values():
        model_manifest["final_fit_input_hash"] = model_manifest["train_input_hash"]
        model_manifest["final_fit_label_hash"] = model_manifest["train_label_hash"]
    save(
        output / "final-fit-manifest.json",
        {
            "models": manifests,
            "selection_hash": load(output / "selection.json")["selection_hash"],
            "final_fit_target_row_count": len(rows) * 15,
        },
    )
    seal = seal_files(
        output,
        phase="FINAL",
        names=[prediction_name("oot", k) for k in selected.values()],
        rowset_hash=digest(flatten_features(oot)[1]),
        contract_hash=c["contract_hash"],
    )
    save(output / "oot-prediction-seal.json", seal)
    save(output / "final-custody.json", {"label_reads": data.label_reads, "oot_labels_read": False})


def breadth(tree: dict[str, Any], ridge: dict[str, Any], horizon: int) -> dict[str, Any]:
    if set(tree) != set(ridge):
        raise ValueError("COMMON_ROWSET")
    key, actual_key = f"error{horizon}", f"actual{horizon}"
    improved = [b for b in tree if Decimal(tree[b][key]) < Decimal(ridge[b][key])]
    degraded = [b for b in tree if Decimal(tree[b][key]) > Decimal(ridge[b][key])]
    total = sum((Decimal(v[actual_key]) for v in ridge.values()), Decimal(0))
    mass = sum((Decimal(ridge[b][actual_key]) for b in improved), Decimal(0))
    return {
        "improved_base_count": len(improved),
        "degraded_base_count": len(degraded),
        "unchanged_base_count": len(tree) - len(improved) - len(degraded),
        "improved_base_share": str(Decimal(len(improved)) / len(tree)),
        "improved_actual_kg_share": str(mass / total) if total > 0 else None,
    }


def robustness(details: dict[str, Any]) -> dict[str, Any]:
    ridge = details["RIDGE"]
    result = {}
    for family in ("CATBOOST", "LIGHTGBM"):
        tree = details[family]
        ranked = sorted(
            tree, key=lambda b: (-(Decimal(ridge[b]["error15"]) - Decimal(tree[b]["error15"])), b)
        )
        values = {}
        for n in (1, 2):
            keep = [b for b in tree if b not in ranked[:n]]
            subset = {}
            for name, source in (("RIDGE", ridge), (family, tree)):
                metrics = {}
                for h in (7, 15):
                    error = sum((Decimal(source[b][f"error{h}"]) for b in keep), Decimal(0))
                    actual = sum((Decimal(source[b][f"actual{h}"]) for b in keep), Decimal(0))
                    metrics[f"H{h}_DAILY_WAPE"] = str(error / actual) if actual > 0 else None
                subset[name] = metrics
            values[f"LEAVE_TOP{n}"] = {"removed_base_count": min(n, len(tree)), "metrics": subset}
        result[family] = values
    return result


def comparison(validation: dict[str, Any], oot: dict[str, Any]) -> dict[str, Any]:
    directions = {
        family: direction(validation[family], validation["RIDGE"], oot[family], oot["RIDGE"])
        for family in ("CATBOOST", "LIGHTGBM")
    }
    ranked = sorted(
        FAMILIES,
        key=lambda k: (
            tuple(
                Decimal(oot[k][m])
                for m in (
                    "H15_DAILY_WAPE",
                    "H7_DAILY_WAPE",
                    "H15_CUMULATIVE_WAPE",
                    "SINGLE_DAY_PEAK_DATE_MAE_DAYS",
                )
            )
            + (FAMILIES.index(k),)
        ),
    )
    leader = ranked[0]
    if leader != "RIDGE" and directions[leader] != "SUPPORTED_DIRECTION":
        leader = "NO_CLEAR_LEADER"
    if leader == "RIDGE" and any(
        all(
            Decimal(validation[t][h]) < Decimal(validation["RIDGE"][h])
            for h in ("H7_DAILY_WAPE", "H15_DAILY_WAPE")
        )
        for t in ("CATBOOST", "LIGHTGBM")
    ):
        leader = "NO_CLEAR_LEADER"
    return {
        "CATBOOST_VS_RIDGE": directions["CATBOOST"],
        "LIGHTGBM_VS_RIDGE": directions["LIGHTGBM"],
        "BASE10_RESEARCH_LEADER": leader,
        "research_leader_is_production_approved": False,
        "prospective_accuracy_validated": False,
    }


def score_oot(dataset: Path, output: Path, repository: Path, public: Path) -> None:
    c = verify_contract(output, repository)
    if (output / "oot-metrics.json").exists():
        raise ValueError("OOT_ALREADY_CONSUMED_NO_RESCORING")
    selected = selection_verified(output, c)
    permit = check_files(
        output,
        load(output / "oot-prediction-seal.json"),
        expected_names=[prediction_name("oot", k) for k in selected.values()],
        contract_hash=c["contract_hash"],
        phase="FINAL",
    )
    data = FrozenDataset(dataset, "SCORE", label_gate=permit)
    rows = data.features("EXPOSED_OOT")
    if (
        digest(flatten_features(rows)[1])
        != load(output / "oot-prediction-seal.json")["rowset_hash"]
    ):
        raise ValueError("COMMON_ROWSET")
    try:
        labels = data.labels("EXPOSED_OOT", rows)
        metrics, details = {}, {}
        for family, candidate in selected.items():
            metrics[family], details[family] = score(
                rows, read_predictions(output, "oot", candidate, rows), labels
            )
        save(output / "oot-metrics.json", metrics)
        save(output / "oot-base-details.json", details)
        save(
            output / "oot-custody.json",
            {
                "label_reads": data.label_reads,
                "label_opened_at": datetime.now(UTC).isoformat(),
                "verified_seal_hash": permit.seal_hash,
            },
        )
        publish(output, public)
    except Exception:
        save(
            output / "invalidated.json", {"phase": "SCORE", "owner_reauthorization_required": True}
        )
        raise


def publish(output: Path, public: Path) -> None:
    c = load(output / "contract.json")
    selected = load(output / "selection.json")["selected"]
    vm = load(output / "validation-metrics.json")
    validation = {family: vm[candidate] for family, candidate in selected.items()}
    oot = load(output / "oot-metrics.json")
    vd = load(output / "validation-base-details.json")
    od = load(output / "oot-base-details.json")
    breadth_report = {
        "VALIDATION": {
            t: {f"H{h}": breadth(vd[selected[t]], vd["RIDGE"], h) for h in (7, 15)}
            for t in ("CATBOOST", "LIGHTGBM")
        },
        "EXPOSED_OOT": {
            t: {f"H{h}": breadth(od[t], od["RIDGE"], h) for h in (7, 15)}
            for t in ("CATBOOST", "LIGHTGBM")
        },
    }
    reports = {
        "s3-benchmark-contract.json": c,
        "model-dependency-freeze.json": {
            "libraries": LIBRARIES,
            "existing_direct_dep_version_changes": 0,
            "runtime_numpy_version": importlib.metadata.version("numpy"),
            "runtime_sklearn_version": importlib.metadata.version("scikit-learn"),
            "lockfile_used": True,
            "research_only": True,
        },
        "candidate-config-freeze.json": {
            "candidates": CANDIDATES,
            "configs_hash": digest(CANDIDATES),
        },
        "validation-prediction-seal.json": load(output / "validation-prediction-seal.json"),
        "validation-model-selection-report.json": load(output / "selection.json"),
        "final-fit-manifest.json": load(output / "final-fit-manifest.json"),
        "train-model-manifest.json": load(output / "phase-a-model-manifest.json"),
        "exposed-oot-prediction-seal.json": load(output / "oot-prediction-seal.json"),
        "validation-metrics.json": vm,
        "exposed-oot-metrics.json": oot,
        "lead-day-metrics.json": {
            "VALIDATION": {k: v["lead_day_metrics"] for k, v in vm.items()},
            "EXPOSED_OOT": {k: v["lead_day_metrics"] for k, v in oot.items()},
        },
        "base-breadth-summary.json": breadth_report,
        "robustness-leave-top1-top2.json": robustness(od),
        "model-comparison-summary.json": comparison(validation, oot),
        "privacy-scan-report.json": {
            "result": "PASS",
            "private_quantities_or_rows_committed": False,
        },
        "s3-readiness-recommendation.json": {
            "benchmark_executed": True,
            "strict_pit": False,
            "weather_benchmark_ready": False,
            "train_weather_origin_count": 0,
            "production_promotion": False,
            "s4_authorized": False,
            "ready_authorized": False,
            "merge_authorized": False,
        },
    }
    members = []
    for name, report in reports.items():
        validate_public(report)
        save(public / name, report)
        raw = (public / name).read_bytes()
        members.append({"name": name, "sha256": sha(raw), "size": len(raw)})
    manifest = {
        "schema": "V0_15_S3_BENCHMARK_MANIFEST_V1",
        "members": members,
        "dataset_manifest_hash": DATASET_MANIFEST_HASH,
    }
    manifest["manifest_hash"] = digest(manifest)
    save(public / "manifest.json", manifest)


def main() -> None:
    getcontext().prec = 50
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("phase-a", "phase-b", "final-fit-seal", "score-oot"))
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--repository", default=Path("."), type=Path)
    parser.add_argument("--public-output", type=Path)
    args = parser.parse_args()
    if any(
        os.environ.get(k, "1") != "1"
        for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
    ):
        raise ValueError("SINGLE_THREAD_ENVIRONMENT_REQUIRED")
    if args.stage == "phase-a":
        phase_a(args.dataset, args.output, args.repository)
    elif args.stage == "phase-b":
        phase_b(args.dataset, args.output, args.repository)
    elif args.stage == "final-fit-seal":
        final_fit(args.dataset, args.output, args.repository)
    elif args.public_output is None:
        parser.error("score-oot requires --public-output")
    else:
        score_oot(args.dataset, args.output, args.repository, args.public_output)
    print(f"S3_STAGE={args.stage};STATUS=COMPLETE")


if __name__ == "__main__":
    main()
