"""Run the frozen V0.8-R2 Stage-A experiment.

`run` performs grouped training-only CV, freezes a final model, then replays the
already-seen 2025-2026 benchmark. `finalize` verifies two independent runs and
publishes aggregate-only repository evidence. S8 private rows never enter Git.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from pathlib import Path
from typing import Any

for _thread_env in (
    "OPENBLAS_NUM_THREADS",
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
):
    os.environ[_thread_env] = "1"

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.area_yield.v08_r2_stage_a import (  # noqa: E402
    R2ExperimentError,
    build_final_stage_a_model,
    canonical_json_bytes,
    decimal_text,
    decimal_value,
    predict_yield,
    run_grouped_cv,
    select_cv_candidate,
    sha256_bytes,
    stage_b_shape_hash,
    validate_peak_date_invariance,
    validate_training_dataset_hash,
    validate_training_rows,
)
from backend.app.area_yield.v08_s8_training_backtest import (  # noqa: E402
    OOT_SEASON,
    compose_daily_curve,
    csv_bytes,
    derive_peaks,
    numeric_distribution,
    read_csv,
    score_model_daily,
    score_season_totals,
    sha256_file,
    verify_model_artifact,
    write_private_bytes,
    write_private_json,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "configs/v0_8_r2_stage_a_experiment_r1.json"
S8_EVIDENCE_PATH = (
    REPO_ROOT / "docs/v0-8/evidence/s8-canonical-training-and-independent-oot-backtest-r1.json"
)
S8_CONFIG_PATH = REPO_ROOT / "configs/v0_8_s8_training_backtest_r1.json"
S9_EVIDENCE_PATH = (
    REPO_ROOT / "docs/v0-8/evidence/s9-scale-shape-error-decomposition-and-model-diagnosis-r1.json"
)
DEFAULT_ARTIFACT_ROOT = Path.home() / "Documents/blueberry-area-yield-artifacts"
TRAIN_FIELDS = [
    "base_id",
    "canonical_base_name",
    "season",
    "area_mu",
    "season_total_quantity_kg",
    "strict_training_eligible",
    "yield_kg_per_mu",
    "daily_curve_available",
    "daily_curve_source_signature",
    "area_authority_id",
    "area_authority_sha256",
    "quantity_authority_id",
    "quantity_authority_sha256",
    "identity_authority_id",
    "identity_authority_sha256",
    "source_signature",
    "eligibility_signature",
]
SEASON_PRED_FIELDS = [
    "model_id",
    "base_id",
    "canonical_base_name",
    "season",
    "target_area_mu",
    "predicted_season_total_kg",
    "predicted_yield_kg_per_mu",
    "training_season_support_count",
    "prediction_basis",
    "model_artifact_sha256",
]
DAILY_PRED_FIELDS = [
    "model_id",
    "base_id",
    "canonical_base_name",
    "season",
    "date",
    "target_area_mu",
    "predicted_season_total_kg",
    "predicted_daily_quantity_kg",
    "predicted_share",
    "model_artifact_sha256",
]
FOLD_FIELDS = ["fold_id", "base_id", "season", "role"]
CV_FIELDS = [
    "model_candidate",
    "hyperparameter",
    "fold_id",
    "validation_base_count",
    "validation_row_count",
    "wape",
    "mae_kg",
    "bias_kg",
    "median_ape",
]
CV_SUMMARY_FIELDS = [
    "model_candidate",
    "hyperparameter",
    "cv_primary_metric",
    "cv_wape",
    "mae_kg",
    "bias_kg",
    "absolute_bias_kg",
    "median_ape",
    "fold_count",
    "validation_row_count",
    "complexity_rank",
]
MODEL_ID = "V0_8_R2_SELECTED_STAGE_A_AND_SHARED_DAILY_SHAPE_R1"
MODEL_IDS = {
    "baseline": "AREA_PROPORTIONAL_POOLED_TRAINING_YIELD_R1",
    "r1": "V0_8_AREA_SCALED_BASE_YIELD_AND_SHARED_DAILY_SHAPE_R1",
    "r2": MODEL_ID,
    "v07": "V0_7_PRODUCTION_MODEL",
}
EXPECTED_BASELINE_WAPE = Decimal("0.3429935582924604063039679242")
EXPECTED_R1_WAPE = Decimal("0.3925893218351959883557945280")
EXPECTED_R1_DAILY_WAPE = Decimal("0.6292132974633544144280801218")
QUANTUM = Decimal("0.000001")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise R2ExperimentError(f"JSON_ROOT_NOT_OBJECT:{path.name}")
    return value


def _write_json(path: Path, value: Any) -> None:
    write_private_json(path, value)


def _write_csv(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> str:
    payload = csv_bytes(fields, rows)
    write_private_bytes(path, payload)
    return sha256_bytes(payload)


def _load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    value = _read_json(path)
    if value.get("task_id") != "V0_8_R2_STAGE_A_SHRINKAGE_MODEL_EXPERIMENT_R1":
        raise R2ExperimentError("R2_CONFIG_TASK_ID_MISMATCH")
    return value


def _safe_manifest_file(root: Path, relative: str) -> Path:
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts:
        raise R2ExperimentError("UNSAFE_PINNED_ARTIFACT_PATH")
    path = root / rel
    if path.is_symlink() or not path.is_file():
        raise R2ExperimentError(f"PINNED_S8_ARTIFACT_MISSING_OR_SYMLINK:{relative}")
    return path


def verify_frozen_inputs(
    config: Mapping[str, Any], artifact_root: Path
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    s8 = config["s8"]
    s8_root = artifact_root / str(s8["private_directory"])
    if sha256_file(S8_EVIDENCE_PATH) != s8["repository_evidence_sha256"]:
        raise R2ExperimentError("BLOCKED_S8_ARTIFACT_DRIFT:REPOSITORY_EVIDENCE")
    if sha256_file(S8_CONFIG_PATH) != s8["repository_config_sha256"]:
        raise R2ExperimentError("BLOCKED_S8_ARTIFACT_DRIFT:REPOSITORY_CONFIG")
    s8_manifest_path = _safe_manifest_file(s8_root, "artifact-manifest.json")
    if sha256_file(s8_manifest_path) != s8["private_manifest_sha256"]:
        raise R2ExperimentError("BLOCKED_S8_ARTIFACT_DRIFT:PRIVATE_MANIFEST")
    s8_manifest = _read_json(s8_manifest_path)
    manifest_artifacts = s8_manifest.get("artifacts")
    if not isinstance(manifest_artifacts, dict) or len(manifest_artifacts) != 59:
        raise R2ExperimentError("BLOCKED_S8_ARTIFACT_DRIFT:MANIFEST_SCHEMA_OR_COUNT")
    mismatches: list[str] = []
    for relative, expected_hash in sorted(manifest_artifacts.items()):
        path = _safe_manifest_file(s8_root, str(relative))
        if sha256_file(path) != expected_hash:
            mismatches.append(str(relative))
    if mismatches:
        raise R2ExperimentError("BLOCKED_S8_ARTIFACT_DRIFT:" + ",".join(mismatches[:5]))
    for relative, expected_hash in s8["frozen_artifacts"].items():
        if manifest_artifacts.get(relative) != expected_hash:
            raise R2ExperimentError(f"BLOCKED_S8_ARTIFACT_DRIFT:PIN_MISMATCH:{relative}")

    s9_evidence = _read_json(S9_EVIDENCE_PATH)
    if sha256_file(S9_EVIDENCE_PATH) != s8["s9_evidence_sha256"]:
        raise R2ExperimentError("BLOCKED_S8_ARTIFACT_DRIFT:S9_EVIDENCE")
    if (
        s9_evidence.get("full39_diagnosis", {})
        .get("baseline_v08_shape_hash_parity", {})
        .get("v08_sha256")
        != s8["stage_b_shape_sha256"]
    ):
        raise R2ExperimentError("BLOCKED_STAGE_B_DRIFT:S9_SHAPE_PIN")
    s9_private = s9_evidence.get("private_artifacts", {})
    if s9_private.get("artifact_manifest_sha256") != s8["s9_private_manifest_sha256"]:
        raise R2ExperimentError("BLOCKED_S8_ARTIFACT_DRIFT:S9_PRIVATE_MANIFEST_PIN")
    s9_root = Path(str(s9_private["primary_directory"]))
    s9_manifest_path = _safe_manifest_file(s9_root, "artifact-manifest.json")
    if sha256_file(s9_manifest_path) != s8["s9_private_manifest_sha256"]:
        raise R2ExperimentError("BLOCKED_S8_ARTIFACT_DRIFT:S9_PRIVATE_MANIFEST")
    s9_manifest = _read_json(s9_manifest_path)
    s9_artifacts = s9_manifest.get("artifacts")
    if not isinstance(s9_artifacts, dict):
        raise R2ExperimentError("BLOCKED_S8_ARTIFACT_DRIFT:S9_MANIFEST_SCHEMA")
    for relative, expected_hash in sorted(s9_artifacts.items()):
        if sha256_file(_safe_manifest_file(s9_root, str(relative))) != expected_hash:
            raise R2ExperimentError(f"BLOCKED_S8_ARTIFACT_DRIFT:S9:{relative}")

    r1_path = _safe_manifest_file(
        s8_root, "model-artifact/training-replay-1/v0-8-model-artifact-r1.json"
    )
    r1_model = _read_json(r1_path)
    if sha256_file(r1_path) != s8["r1_model_artifact_sha256"]:
        raise R2ExperimentError("BLOCKED_S8_ARTIFACT_DRIFT:R1_MODEL_HASH")
    verify_model_artifact(r1_model)
    return s8_root, r1_model, s9_evidence


def _training_code_hash() -> str:
    module_path = REPO_ROOT / "backend/app/area_yield/v08_r2_stage_a.py"
    s8_module_path = REPO_ROOT / "backend/app/area_yield/v08_s8_training_backtest.py"
    values = {
        "r2_module_sha256": sha256_file(module_path),
        "r2_runner_sha256": sha256_file(Path(__file__).resolve()),
        "s8_scoring_module_sha256": sha256_file(s8_module_path),
    }
    return sha256_bytes(canonical_json_bytes(values))


def _pooled_yield(rows: Sequence[Mapping[str, Any]]) -> Decimal:
    ordered = sorted(rows, key=lambda row: (str(row["season"]), str(row["base_id"])))
    total = Decimal(0)
    area = Decimal(0)
    for row in ordered:
        total += decimal_value(row["season_total_quantity_kg"], "season_total")
        area += decimal_value(row["area_mu"], "area")
    with localcontext() as context:
        context.prec = 40
        return total / area


def _base_support(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = Counter(str(row["base_id"]) for row in rows)
    return dict(sorted(counts.items()))


def _make_final_artifact(
    *,
    training_rows: Sequence[Mapping[str, Any]],
    selected: Mapping[str, Any],
    r1_model: Mapping[str, Any],
    training_sha: str,
    training_daily_sha: str,
    config_sha: str,
    cv_summary_sha: str,
) -> dict[str, Any]:
    candidate = str(selected["model_candidate"])
    hyper = str(selected["hyperparameter"])
    parameter = None if hyper == "NONE" else decimal_value(hyper, "selected_hyperparameter")
    stage_a_fit = build_final_stage_a_model(training_rows, candidate, parameter)
    pooled = _pooled_yield(training_rows)
    source_pooled = decimal_value(
        r1_model["stage_a"]["pooled_training_yield_kg_per_mu"], "r1_pooled_training_yield"
    )
    if pooled != source_pooled:
        raise R2ExperimentError("S8_FROZEN_TRAINING_POOLED_YIELD_MISMATCH")
    if (
        candidate == "GLOBAL_POOLED_YIELD"
        and decimal_value(stage_a_fit["global_yield_kg_per_mu"], "global_yield") != source_pooled
    ):
        raise R2ExperimentError("FROZEN_GLOBAL_YIELD_MISMATCH")
    stage_a = {
        **stage_a_fit,
        "model_family": candidate,
        "prediction": "TARGET_AREA_MU_TIMES_ESTIMATED_YIELD_KG_PER_MU",
        "pooled_training_yield_kg_per_mu": decimal_text(pooled),
        "training_row_count": len(training_rows),
        "selection_cv_wape": str(selected["cv_wape"]),
        "selection_metric": "GROUPED_CV_SEASON_TOTAL_WAPE",
        "nonnegative_yield_required": True,
    }
    payload: dict[str, Any] = {
        "model_id": MODEL_ID,
        "model_family": candidate,
        "architecture": "REPLACED_STAGE_A_WITH_EXACT_FROZEN_R1_STAGE_B",
        "training_seasons": ["2023-2024", "2024-2025"],
        "training_row_count": len(training_rows),
        "training_row_keys": [
            f"{row['base_id']}+{row['season']}"
            for row in sorted(
                training_rows, key=lambda row: (str(row["season"]), str(row["base_id"]))
            )
        ],
        "training_dataset_sha256": training_sha,
        "training_daily_curve_sha256": training_daily_sha,
        "configuration_sha256": config_sha,
        "training_cv_summary_sha256": cv_summary_sha,
        "training_code_sha256": _training_code_hash(),
        "source_r1_model_artifact_sha256": str(r1_model["artifact_hash"]),
        "stage_a": stage_a,
        "stage_b": copy.deepcopy(r1_model["stage_b"]),
        "randomness": "NONE;NUMPY_BLAS_THREADS=1",
        "benchmark_actuals_used": False,
        "oot_labels_used": False,
        "model_production_ready": False,
        "artifact_hash": "",
    }
    payload.pop("artifact_hash")
    payload["artifact_hash"] = sha256_bytes(canonical_json_bytes(payload))
    verify_model_artifact(payload)
    return payload


def _predict_model_total(
    model: Mapping[str, Any], base_id: str, area: Decimal
) -> tuple[Decimal, Decimal]:
    stage_a = model["stage_a"]
    yield_value = predict_yield(stage_a, base_id)
    if yield_value <= 0:
        raise R2ExperimentError("NONPOSITIVE_PREDICTED_YIELD")
    total = (area * yield_value).quantize(QUANTUM, rounding=ROUND_HALF_EVEN)
    return total, yield_value


def _private_file_map(root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "artifact-manifest.json":
            relative = path.relative_to(root).as_posix()
            result[relative] = {"sha256": sha256_file(path), "size_bytes": path.stat().st_size}
    return result


def _build_shrinkage_diagnostics(
    rows: Sequence[Mapping[str, Any]],
    cv_summary: Sequence[Mapping[str, Any]],
    selected: Mapping[str, Any],
) -> list[dict[str, str]]:
    options = [row for row in cv_summary if row["model_candidate"] == "SHRINKAGE_BASE_YIELD"]
    best = min(
        options,
        key=lambda row: (
            decimal_value(row["cv_wape"], "cv_wape"),
            -decimal_value(row["hyperparameter"], "lambda"),
        ),
    )
    lam = decimal_value(best["hyperparameter"], "lambda")
    global_yield = _pooled_yield(rows)
    yields: dict[str, list[Decimal]] = {}
    for row in rows:
        base = str(row["base_id"])
        yields.setdefault(base, []).append(
            decimal_value(row["season_total_quantity_kg"], "season_total")
            / decimal_value(row["area_mu"], "area")
        )
    output: list[dict[str, str]] = []
    for base, values in sorted(yields.items()):
        n = len(values)
        mean = sum(values, Decimal(0)) / Decimal(n)
        weight = Decimal(n) / (Decimal(n) + lam)
        estimate = weight * mean + (Decimal(1) - weight) * global_yield
        output.append(
            {
                "base_id": base,
                "n_history": str(n),
                "base_mean_yield_kg_per_mu": decimal_text(mean),
                "global_yield_kg_per_mu": decimal_text(global_yield),
                "lambda_cv_diagnostic_only": decimal_text(lam),
                "shrinkage_weight": decimal_text(weight),
                "shrunk_yield_kg_per_mu": decimal_text(estimate),
                "selected_stage_a_candidate": str(selected["model_candidate"]),
                "selected_for_r2": str(
                    selected["model_candidate"] == "SHRINKAGE_BASE_YIELD"
                ).lower(),
                "benchmark_values_used": "false",
            }
        )
    return output


def _make_fold_assignment(
    rows: Sequence[Mapping[str, Any]], fold_rows: Sequence[Mapping[str, str]]
) -> list[dict[str, str]]:
    # The CV helper returns a long-form table with every row assigned a role in every fold.
    return [dict(row) for row in fold_rows]


def _run_training_and_freeze(
    *, config: Mapping[str, Any], s8_root: Path, r1_model: Mapping[str, Any], output_root: Path
) -> dict[str, Any]:
    training_path = _safe_manifest_file(s8_root, "v0-8-canonical-training-dataset-r1.csv")
    training_daily_path = _safe_manifest_file(s8_root, "training-daily-curves-r1.csv")
    training_bytes = training_path.read_bytes()
    training_sha = validate_training_dataset_hash(
        training_bytes, str(config["training"]["expected_sha256"])
    )
    training_daily_sha = sha256_file(training_daily_path)
    training_rows = read_csv(training_path)
    training_daily_rows = read_csv(training_daily_path)
    validate_training_rows(training_rows)
    if len(training_rows) != 37:
        raise R2ExperimentError("BLOCKED_TRAINING_DATASET_DRIFT:ROW_COUNT")
    if any(row["season"] == OOT_SEASON for row in training_daily_rows):
        raise R2ExperimentError("OOT_LABELS_FOUND_IN_TRAINING_DAILY_INPUT")

    candidate_specs = config["candidate_specs"]
    fold_rows, cv_rows, cv_summary = run_grouped_cv(training_rows, candidate_specs)
    selection = select_cv_candidate(
        cv_summary,
        tie_tolerance=decimal_value(config["selection_policy"]["tie_tolerance"], "tie_tolerance"),
    )

    output_root.mkdir(parents=True, mode=0o700, exist_ok=False)
    output_root.chmod(0o700)
    write_private_bytes(output_root / "r2-training-dataset-r1.csv", training_bytes)
    write_private_bytes(
        output_root / "r2-training-daily-curves-r1.csv", training_daily_path.read_bytes()
    )
    _write_json(
        output_root / "r2-training-manifest-r1.json",
        {
            "row_count": len(training_rows),
            "unique_base_season_count": len(
                {(row["base_id"], row["season"]) for row in training_rows}
            ),
            "season_counts": {
                season: sum(row["season"] == season for row in training_rows)
                for season in ("2023-2024", "2024-2025")
            },
            "dataset_sha256": training_sha,
            "daily_curves_sha256": training_daily_sha,
            "blocked_rows_included": 0,
            "oot_season_rows_included": 0,
        },
    )
    _write_json(output_root / "stage-a-candidate-specs-r1.json", {"candidates": candidate_specs})
    _write_csv(
        output_root / "stage-a-training-cv-folds-r1.csv",
        FOLD_FIELDS,
        _make_fold_assignment(training_rows, fold_rows),
    )
    _write_csv(output_root / "stage-a-training-cv-results-r1.csv", CV_FIELDS, cv_rows)
    _write_csv(output_root / "stage-a-candidate-cv-summary-r1.csv", CV_SUMMARY_FIELDS, cv_summary)

    selected_config = {
        "model_id": MODEL_ID,
        "selected_candidate": selection["model_candidate"],
        "selected_hyperparameter": selection["hyperparameter"],
        "selection_metric": "GROUPED_CV_SEASON_TOTAL_WAPE",
        "selection_cv_wape": selection["cv_wape"],
        "selection_cv_mae_kg": selection["mae_kg"],
        "selection_cv_bias_kg": selection["bias_kg"],
        "cv_strategy": "DETERMINISTIC_LEAVE_ONE_BASE_OUT;ALL_SEASONS_OF_BASE_HELD_OUT_TOGETHER",
        "cv_fold_count": len({row["fold_id"] for row in fold_rows}),
        "training_dataset_sha256": training_sha,
        "stage_b_source_model_artifact_sha256": r1_model["artifact_hash"],
        "stage_b_profile_copied_exactly": True,
        "benchmark_selection_or_tuning_used": False,
        "candidate_specs_sha256": sha256_file(output_root / "stage-a-candidate-specs-r1.json"),
        "tie_break_applied": "SIMPLER_MODEL_THEN_LOWER_ABSOLUTE_BIAS_THEN_STABLE_ORDER",
    }
    _write_json(output_root / "selected-stage-a-model-config-r1.json", selected_config)
    selected_config_sha = sha256_file(output_root / "selected-stage-a-model-config-r1.json")
    cv_summary_sha = sha256_file(output_root / "stage-a-candidate-cv-summary-r1.csv")
    model = _make_final_artifact(
        training_rows=training_rows,
        selected=selection,
        r1_model=r1_model,
        training_sha=training_sha,
        training_daily_sha=training_daily_sha,
        config_sha=selected_config_sha,
        cv_summary_sha=cv_summary_sha,
    )
    model_payload = canonical_json_bytes(model) + b"\n"
    model_path = output_root / "selected-stage-a-model-artifact-r1.json"
    write_private_bytes(model_path, model_payload)
    model_file_sha = sha256_bytes(model_payload)
    if model_file_sha != sha256_file(model_path):
        raise R2ExperimentError("FINAL_MODEL_ARTIFACT_WRITE_HASH_MISMATCH")
    _write_csv(
        output_root / "stage-a-shrinkage-by-base-r1.csv",
        [
            "base_id",
            "n_history",
            "base_mean_yield_kg_per_mu",
            "global_yield_kg_per_mu",
            "lambda_cv_diagnostic_only",
            "shrinkage_weight",
            "shrunk_yield_kg_per_mu",
            "selected_stage_a_candidate",
            "selected_for_r2",
            "benchmark_values_used",
        ],
        _build_shrinkage_diagnostics(training_rows, cv_summary, selection),
    )
    frozen_marker = {
        "model_artifact_sha256": model_file_sha,
        "model_internal_hash": model["artifact_hash"],
        "training_dataset_sha256": training_sha,
        "selected_config_sha256": selected_config_sha,
        "model_artifact_created_before_benchmark_replay": True,
        "benchmark_labels_read": False,
    }
    _write_json(output_root / "model-frozen-before-benchmark-r1.json", frozen_marker)
    return {
        "model": model,
        "model_file_sha256": model_file_sha,
        "training_rows": training_rows,
        "training_sha256": training_sha,
        "training_daily_sha256": training_daily_sha,
        "cv_rows": cv_rows,
        "cv_summary": cv_summary,
        "selection": selection,
        "selected_config_sha256": selected_config_sha,
        "frozen_marker": frozen_marker,
    }


def _read_model_predictions(path: Path) -> dict[str, dict[str, str]]:
    rows = read_csv(path)
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        base_id = row["base_id"]
        if base_id in result:
            raise R2ExperimentError(f"DUPLICATE_FROZEN_SEASON_PREDICTION:{path.name}")
        result[base_id] = row
    return result


def _model_daily_rows(path: Path, model_id: str | None = None) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in read_csv(path):
        if model_id is not None and row.get("model_id") != model_id:
            continue
        grouped.setdefault(row["base_id"], []).append(row)
    for rows in grouped.values():
        rows.sort(key=lambda row: row["date"])
    return grouped


def _as_scoring_predictions(
    grouped: Mapping[str, Sequence[Mapping[str, str]]],
    base_ids: Sequence[str],
    field: str,
) -> list[dict[str, str]]:
    return [
        {
            "base_id": base_id,
            "date": row["date"],
            "predicted_daily_quantity_kg": row[field],
        }
        for base_id in sorted(base_ids)
        for row in grouped[base_id]
    ]


def _write_r2_predictions(
    *, s8_root: Path, output_root: Path, model: Mapping[str, Any], model_file_sha: str
) -> dict[str, Any]:
    area_rows = read_csv(_safe_manifest_file(s8_root, "oot-area-input-r1.csv"))
    if len(area_rows) != 39 or len({row["base_id"] for row in area_rows}) != 39:
        raise R2ExperimentError("BLOCKED_OOT_COHORT_NOT_39_AREAS")
    if any(row["season"] != OOT_SEASON for row in area_rows):
        raise R2ExperimentError("NON_FROZEN_BENCHMARK_SEASON_IN_AREA_INPUT")
    training_support: dict[str, int] = model["stage_a"].get("base_support", {})
    season_predictions: list[dict[str, str]] = []
    daily_predictions: list[dict[str, str]] = []
    peak_by_base: dict[str, dict[str, str]] = {}
    for row in sorted(area_rows, key=lambda item: item["base_id"]):
        base_id = row["base_id"]
        area = decimal_value(row.get("actual_area_mu", row.get("area_mu")), "oot_area")
        if area <= 0:
            raise R2ExperimentError("NONPOSITIVE_FROZEN_BENCHMARK_AREA")
        total, yield_value = _predict_model_total(model, base_id, area)
        daily = compose_daily_curve(model=model, predicted_total_kg=total, season=OOT_SEASON)
        if (
            sum(
                (decimal_value(item["predicted_daily_quantity_kg"], "daily") for item in daily),
                Decimal(0),
            )
            != total
        ):
            raise R2ExperimentError("R2_PREDICTED_DAILY_SUM_MISMATCH")
        season_predictions.append(
            {
                "model_id": MODEL_ID,
                "base_id": base_id,
                "canonical_base_name": row["canonical_base_name"],
                "season": OOT_SEASON,
                "target_area_mu": decimal_text(area),
                "predicted_season_total_kg": decimal_text(total),
                "predicted_yield_kg_per_mu": decimal_text(yield_value),
                "training_season_support_count": str(training_support.get(base_id, 0)),
                "prediction_basis": str(model["stage_a"]["candidate"]),
                "model_artifact_sha256": model_file_sha,
            }
        )
        for day in daily:
            daily_predictions.append(
                {
                    "model_id": MODEL_ID,
                    "base_id": base_id,
                    "canonical_base_name": row["canonical_base_name"],
                    "season": OOT_SEASON,
                    "date": day["date"],
                    "target_area_mu": decimal_text(area),
                    "predicted_season_total_kg": decimal_text(total),
                    "predicted_daily_quantity_kg": day["predicted_daily_quantity_kg"],
                    "predicted_share": day["predicted_share"],
                    "model_artifact_sha256": model_file_sha,
                }
            )
        peak_by_base[base_id] = derive_peaks(daily)
    if len(daily_predictions) != 39 * 268:
        raise R2ExperimentError("R2_DAILY_PREDICTION_COUNT_MISMATCH")
    season_predictions.sort(key=lambda row: row["base_id"])
    daily_predictions.sort(key=lambda row: (row["base_id"], row["date"]))
    season_sha = _write_csv(
        output_root / "r2-frozen-benchmark-season-total-r1.csv",
        SEASON_PRED_FIELDS,
        season_predictions,
    )
    daily_sha = _write_csv(
        output_root / "r2-frozen-benchmark-daily-r1.csv", DAILY_PRED_FIELDS, daily_predictions
    )
    shape_sha = stage_b_shape_hash(daily_predictions)
    if shape_sha != "7ae53f5888947053057071f9b097e38b03bb8112a41de972b8e2d51fd311cb2e":
        raise R2ExperimentError("BLOCKED_STAGE_B_DRIFT:R2_EFFECTIVE_SHAPE_HASH")
    seal = {
        "model_artifact_sha256": model_file_sha,
        "training_dataset_sha256": model["training_dataset_sha256"],
        "benchmark_season": OOT_SEASON,
        "benchmark_row_count": len(season_predictions),
        "benchmark_actuals_read_before_prediction_seal": False,
        "stage_b_shape_sha256": shape_sha,
        "season_prediction_sha256": season_sha,
        "daily_prediction_sha256": daily_sha,
    }
    _write_json(output_root / "r2-benchmark-prediction-seal-r1.json", seal)
    if sha256_file(output_root / "selected-stage-a-model-artifact-r1.json") != model_file_sha:
        raise R2ExperimentError("MODEL_ARTIFACT_CHANGED_AFTER_FREEZE")
    return {
        "season_predictions": season_predictions,
        "daily_predictions": daily_predictions,
        "peak_by_base": peak_by_base,
        "seal": seal,
    }


def _sum_bias(
    actual: Mapping[str, Decimal], predicted: Mapping[str, Decimal]
) -> tuple[Decimal, Decimal]:
    signed = sum((predicted[key] - actual[key] for key in actual), Decimal(0))
    actual_sum = sum(actual.values(), Decimal(0))
    return signed, signed / actual_sum


def _metric_by_support(
    *,
    actual: Mapping[str, Decimal],
    predictions: Mapping[str, Mapping[str, Decimal]],
    support: Mapping[str, int],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    groups: tuple[tuple[str, Callable[[int], bool]], ...] = (
        ("support_0", lambda value: value == 0),
        ("support_1", lambda value: value == 1),
        ("support_2plus", lambda value: value >= 2),
    )
    for group_name, predicate in groups:
        bases = sorted(base for base in actual if predicate(support.get(base, 0)))
        if not bases:
            raise R2ExperimentError(f"EMPTY_TRAIN_SUPPORT_STRATUM:{group_name}")
        models = {name: {base: predictions[name][base] for base in bases} for name in predictions}
        metrics = score_season_totals({base: actual[base] for base in bases}, models)
        for model_id, model_metric in sorted(metrics.items()):
            rows.append(
                {
                    "support_stratum": group_name,
                    "base_count": str(len(bases)),
                    "model_id": model_id,
                    "season_total_wape": str(model_metric["wape"]),
                    "season_total_mae_kg": str(model_metric["mae"]),
                    "season_total_bias_kg": str(model_metric["bias_sum_predicted_minus_actual"]),
                }
            )
    return rows


def _distribution_for_yields(
    *,
    actual: Mapping[str, Decimal],
    areas: Mapping[str, Decimal],
    predictions: Mapping[str, Mapping[str, Decimal]],
    baseline_yield: Decimal,
) -> dict[str, Any]:
    ids = sorted(actual)
    return {
        "baseline_pooled_yield_kg_per_mu": decimal_text(baseline_yield),
        "baseline_yield_distribution": numeric_distribution([baseline_yield for _ in ids]),
        "r1_predicted_yield_distribution": numeric_distribution(
            [predictions["r1"][base] / areas[base] for base in ids]
        ),
        "r2_predicted_yield_distribution": numeric_distribution(
            [predictions["r2"][base] / areas[base] for base in ids]
        ),
        "actual_benchmark_yield_distribution": numeric_distribution(
            [actual[base] / areas[base] for base in ids]
        ),
        "oot_actual_yield_used_for_fit_or_selection": False,
    }


def _base_comparison_rows(
    *,
    base_ids: Sequence[str],
    actual: Mapping[str, Decimal],
    totals: Mapping[str, Mapping[str, Decimal]],
    daily_metrics: Mapping[str, Any],
    support: Mapping[str, int],
    areas: Mapping[str, Decimal],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    metric_peaks = daily_metrics
    for base in sorted(base_ids):
        row: dict[str, str] = {
            "base_id": base,
            "actual_total_kg": decimal_text(actual[base]),
            "area_mu": decimal_text(areas[base]),
            "training_season_support_count": str(support.get(base, 0)),
        }
        for label, model in (("baseline", "baseline"), ("r1", "r1"), ("r2", "r2")):
            predicted = totals[model][base]
            row[f"{label}_predicted_total_kg"] = decimal_text(predicted)
            row[f"{label}_absolute_error_kg"] = decimal_text(abs(predicted - actual[base]))
        for label, model_id in (
            ("baseline", MODEL_IDS["baseline"]),
            ("r1", MODEL_IDS["r1"]),
            ("r2", MODEL_IDS["r2"]),
        ):
            per_base = metric_peaks[model_id]["per_base_daily"][base]
            peaks = metric_peaks[model_id]["per_base_peak_truth_and_predictions"][base]
            row[f"{label}_daily_wape"] = str(per_base["wape"])
            row[f"{label}_single_day_peak_date_error_days"] = str(
                abs(
                    (
                        date.fromisoformat(peaks["predicted_peak_date"])
                        - date.fromisoformat(peaks["actual_peak_date"])
                    ).days
                )
            )
            row[f"{label}_rolling7_start_date_error_days"] = str(
                abs(
                    (
                        date.fromisoformat(peaks["predicted_rolling7_start_date"])
                        - date.fromisoformat(peaks["actual_rolling7_start_date"])
                    ).days
                )
            )
            row[f"{label}_single_day_peak_quantity_abs_error_kg"] = str(
                abs(
                    decimal_value(peaks["predicted_peak_quantity_kg"], "pred_peak")
                    - decimal_value(peaks["actual_peak_quantity_kg"], "actual_peak")
                )
            )
            row[f"{label}_rolling7_quantity_abs_error_kg"] = str(
                abs(
                    decimal_value(peaks["predicted_rolling7_peak_quantity_kg"], "pred_roll7")
                    - decimal_value(peaks["actual_rolling7_peak_quantity_kg"], "actual_roll7")
                )
            )
        rows.append(row)
    return rows


def _score_frozen_benchmark(
    *, config: Mapping[str, Any], s8_root: Path, output_root: Path, trained: Mapping[str, Any]
) -> dict[str, Any]:
    model = trained["model"]
    model_file_sha = str(trained["model_file_sha256"])
    if not trained["frozen_marker"].get("model_artifact_created_before_benchmark_replay"):
        raise R2ExperimentError("BENCHMARK_OPENED_BEFORE_MODEL_FREEZE")
    pred = _write_r2_predictions(
        s8_root=s8_root, output_root=output_root, model=model, model_file_sha=model_file_sha
    )

    # Benchmark truth is first parsed only after the frozen R2 prediction seal exists.
    oot_truth_rows = read_csv(_safe_manifest_file(s8_root, "v0-8-canonical-oot-dataset-r1.csv"))
    actual_total_rows = {row["base_id"]: row for row in oot_truth_rows}
    if len(actual_total_rows) != 39 or any(row["season"] != OOT_SEASON for row in oot_truth_rows):
        raise R2ExperimentError("FROZEN_BENCHMARK_TRUTH_COHORT_NOT_39")
    actual_daily_source = read_csv(
        _safe_manifest_file(s8_root, "v0-8-oot-daily-predictions-r1.csv")
    )
    actual_daily_by_base: dict[str, list[dict[str, str]]] = {}
    r1_daily_by_base: dict[str, list[dict[str, str]]] = {}
    for row in actual_daily_source:
        if row.get("model_id") != MODEL_IDS["r1"]:
            continue
        actual_daily_by_base.setdefault(row["base_id"], []).append(row)
        r1_daily_by_base.setdefault(row["base_id"], []).append(row)
    for grouped in (actual_daily_by_base, r1_daily_by_base):
        for rows in grouped.values():
            rows.sort(key=lambda row: row["date"])
    if set(actual_daily_by_base) != set(actual_total_rows) or any(
        len(rows) != 268 for rows in actual_daily_by_base.values()
    ):
        raise R2ExperimentError("FROZEN_BENCHMARK_DAILY_TRUTH_COHORT_MISMATCH")

    # S8 frozen predictions are opened only now, after R2 model and predictions are sealed.
    baseline_total_rows = _read_model_predictions(
        _safe_manifest_file(s8_root, "baseline-oot-predictions-r1.csv")
    )
    r1_total_rows = _read_model_predictions(
        _safe_manifest_file(s8_root, "v0-8-oot-season-total-predictions-r1.csv")
    )
    v07_total_rows = _read_model_predictions(
        _safe_manifest_file(s8_root, "v0-7-oot-predictions-r1.csv")
    )
    baseline_daily = _model_daily_rows(
        _safe_manifest_file(s8_root, "baseline-oot-daily-predictions-r1.csv"), MODEL_IDS["baseline"]
    )
    v07_daily = _model_daily_rows(
        _safe_manifest_file(s8_root, "v0-7-oot-daily-predictions-r1.csv"), MODEL_IDS["v07"]
    )
    r2_daily: dict[str, list[dict[str, str]]] = {}
    for row in pred["daily_predictions"]:
        r2_daily.setdefault(row["base_id"], []).append(row)
    r2_totals_rows = {row["base_id"]: row for row in pred["season_predictions"]}

    actual = {
        base: decimal_value(row["actual_season_total_quantity_kg"], "actual_total")
        for base, row in actual_total_rows.items()
    }
    actual_by_base: dict[str, list[dict[str, str]]] = {}
    areas: dict[str, Decimal] = {}
    names: dict[str, str] = {}
    for base, rows in actual_daily_by_base.items():
        actual_by_base[base] = [
            {
                "date": row["date"],
                "actual_quantity_kg": row["actual_quantity_kg"],
                "actual_completeness_status": row.get(
                    "actual_completeness_status", "AUTHORIZED_ZERO"
                ),
            }
            for row in rows
        ]
        daily_sum = sum(
            (decimal_value(row["actual_quantity_kg"], "actual_daily") for row in rows), Decimal(0)
        )
        if daily_sum != actual[base]:
            raise R2ExperimentError(f"FROZEN_BENCHMARK_DAILY_TOTAL_MISMATCH:{base}")
        areas[base] = decimal_value(actual_total_rows[base]["area_mu"], "actual_area")
        names[base] = actual_total_rows[base]["canonical_base_name"]

    full_bases = sorted(actual)
    common_bases = sorted(set(v07_total_rows))
    if len(common_bases) != 30 or not set(common_bases) <= set(full_bases):
        raise R2ExperimentError("COMMON_COMPARATOR_COHORT_NOT_30")
    baseline_totals = {
        base: decimal_value(row["predicted_season_total_kg"], "baseline_total")
        for base, row in baseline_total_rows.items()
    }
    r1_totals = {
        base: decimal_value(row["predicted_season_total_kg"], "r1_total")
        for base, row in r1_total_rows.items()
    }
    v07_totals = {
        base: decimal_value(row["predicted_season_total_kg"], "v07_total")
        for base, row in v07_total_rows.items()
    }
    r2_totals = {
        base: decimal_value(row["predicted_season_total_kg"], "r2_total")
        for base, row in r2_totals_rows.items()
    }
    if any(set(items) != set(full_bases) for items in (baseline_totals, r1_totals, r2_totals)):
        raise R2ExperimentError("FULL_39_TOTAL_PREDICTION_COHORT_MISMATCH")
    if set(baseline_daily) != set(full_bases) or set(r2_daily) != set(full_bases):
        raise R2ExperimentError("FULL_39_DAILY_PREDICTION_COHORT_MISMATCH")
    if set(v07_daily) != set(common_bases):
        raise R2ExperimentError("V07_COMMON_30_DAILY_COHORT_MISMATCH")

    baseline_id = MODEL_IDS["baseline"]
    r1_id = MODEL_IDS["r1"]
    r2_id = MODEL_IDS["r2"]
    v07_id = MODEL_IDS["v07"]
    full_total_metrics = score_season_totals(
        actual,
        {baseline_id: baseline_totals, r1_id: r1_totals, r2_id: r2_totals},
    )
    common_actual = {base: actual[base] for base in common_bases}
    common_total_metrics = score_season_totals(
        common_actual,
        {
            baseline_id: {base: baseline_totals[base] for base in common_bases},
            r1_id: {base: r1_totals[base] for base in common_bases},
            r2_id: {base: r2_totals[base] for base in common_bases},
            v07_id: {base: v07_totals[base] for base in common_bases},
        },
    )
    full_daily_metrics = {
        model_id: score_model_daily(
            _as_scoring_predictions(rows, full_bases, "predicted_daily_quantity_kg"),
            actual_by_base,
        )
        for model_id, rows in (
            (baseline_id, baseline_daily),
            (r1_id, r1_daily_by_base),
            (r2_id, r2_daily),
        )
    }
    common_daily_metrics = {
        model_id: score_model_daily(
            _as_scoring_predictions(grouped, common_bases, "predicted_daily_quantity_kg"),
            {base: actual_by_base[base] for base in common_bases},
        )
        for model_id, grouped in (
            (baseline_id, baseline_daily),
            (r1_id, r1_daily_by_base),
            (r2_id, r2_daily),
            (v07_id, v07_daily),
        )
    }

    frozen_baseline_wape = decimal_value(full_total_metrics[baseline_id]["wape"], "baseline_wape")
    frozen_r1_wape = decimal_value(full_total_metrics[r1_id]["wape"], "r1_wape")
    frozen_r1_daily_wape = decimal_value(
        full_daily_metrics[r1_id]["daily"]["wape"], "r1_daily_wape"
    )
    if (frozen_baseline_wape, frozen_r1_wape, frozen_r1_daily_wape) != (
        EXPECTED_BASELINE_WAPE,
        EXPECTED_R1_WAPE,
        EXPECTED_R1_DAILY_WAPE,
    ):
        raise R2ExperimentError("S8_FROZEN_PRIMARY_METRIC_PARITY_FAILED")

    r1_effective_shape = stage_b_shape_hash(
        [row for rows in r1_daily_by_base.values() for row in rows]
    )
    r2_effective_shape = stage_b_shape_hash(pred["daily_predictions"])
    expected_shape_hash = str(config["s8"]["stage_b_shape_sha256"])
    if r1_effective_shape != expected_shape_hash or r2_effective_shape != expected_shape_hash:
        raise R2ExperimentError("BLOCKED_STAGE_B_DRIFT:EFFECTIVE_SHAPE_HASH")
    r1_peaks = {base: derive_peaks(rows) for base, rows in r1_daily_by_base.items()}
    r2_peaks = {base: derive_peaks(rows) for base, rows in r2_daily.items()}
    single_changed, rolling_changed = validate_peak_date_invariance(r1_peaks, r2_peaks)
    if single_changed != 0 or rolling_changed != 0:
        raise R2ExperimentError("BLOCKED_STAGE_B_PEAK_DATE_CHANGED")

    support = _base_support(trained["training_rows"])
    support_by_oot = {base: support.get(base, 0) for base in full_bases}
    total_prediction_maps = {
        "baseline": baseline_totals,
        "r1": r1_totals,
        "r2": r2_totals,
    }
    if {row["base_id"] for row in pred["season_predictions"]} != set(full_bases):
        raise R2ExperimentError("R2_BENCHMARK_PREDICTION_COHORT_CHANGED")
    support_rows = _metric_by_support(
        actual=actual, predictions=total_prediction_maps, support=support_by_oot
    )
    full_base_rows = _base_comparison_rows(
        base_ids=full_bases,
        actual=actual,
        totals=total_prediction_maps,
        daily_metrics=full_daily_metrics,
        support=support_by_oot,
        areas=areas,
    )
    common_base_rows = _base_comparison_rows(
        base_ids=common_bases,
        actual=actual,
        totals={
            "baseline": baseline_totals,
            "r1": r1_totals,
            "r2": r2_totals,
        },
        daily_metrics=common_daily_metrics,
        support=support_by_oot,
        areas=areas,
    )
    # Add V0.7 total diagnostics to the common-30 artifact without changing the full-39 cohort.
    for row in common_base_rows:
        base = row["base_id"]
        row["v07_predicted_total_kg"] = decimal_text(v07_totals[base])
        row["v07_absolute_error_kg"] = decimal_text(abs(v07_totals[base] - actual[base]))

    win_summary: dict[str, dict[str, int]] = {}
    for comparator, comparator_map in (("baseline", baseline_totals), ("r1", r1_totals)):
        counts: Counter[str] = Counter()
        for base in full_bases:
            r2_error = abs(r2_totals[base] - actual[base])
            comparator_error = abs(comparator_map[base] - actual[base])
            if r2_error < comparator_error:
                counts["r2_lower_abs_error"] += 1
            elif r2_error > comparator_error:
                counts["comparator_lower_abs_error"] += 1
            else:
                counts["tie"] += 1
        win_summary[comparator] = {
            "r2_lower_abs_error_base_count": counts["r2_lower_abs_error"],
            f"{comparator}_lower_abs_error_base_count": counts["comparator_lower_abs_error"],
            "tie_base_count": counts["tie"],
        }

    baseline_yield = decimal_value(
        model["stage_a"]["pooled_training_yield_kg_per_mu"], "baseline_yield"
    )
    yield_distribution = _distribution_for_yields(
        actual=actual,
        areas=areas,
        predictions=total_prediction_maps,
        baseline_yield=baseline_yield,
    )
    r2_bias, r2_bias_ratio = _sum_bias(actual, r2_totals)
    r1_bias, _ = _sum_bias(actual, r1_totals)
    r2_baseline_delta = (
        decimal_value(full_total_metrics[r2_id]["wape"], "r2_wape") - frozen_baseline_wape
    )
    r2_r1_delta = decimal_value(full_total_metrics[r2_id]["wape"], "r2_wape") - frozen_r1_wape
    if r2_baseline_delta < 0:
        readiness = "R2_BENCHMARK_IMPROVED_FUTURE_VALIDATION_REQUIRED"
        result = "PASS_R2_STAGE_A_EXPERIMENT_COMPLETED"
    elif r2_baseline_delta == 0:
        readiness = "R2_NO_MATERIAL_BENCHMARK_IMPROVEMENT"
        result = "PASS_EXPERIMENT_COMPLETED_NO_STAGE_A_IMPROVEMENT"
    else:
        readiness = "R2_BENCHMARK_WORSE"
        result = "PASS_EXPERIMENT_COMPLETED_NO_STAGE_A_IMPROVEMENT"

    summary = {
        "task_id": config["task_id"],
        "result": result,
        "baseline_main_sha": config["baseline_main_sha"],
        "training_dataset_sha256": trained["training_sha256"],
        "training_dataset_matches_s8": True,
        "training_dataset_row_count": 37,
        "frozen_benchmark_row_count": 39,
        "frozen_benchmark_season": OOT_SEASON,
        "common_comparator_count": 30,
        "selected_stage_a_model": trained["selection"]["model_candidate"],
        "selected_hyperparameter": trained["selection"]["hyperparameter"],
        "selected_model_cv_wape": trained["selection"]["cv_wape"],
        "cv_strategy": "GROUPED_LEAVE_ONE_BASE_OUT_26_FOLDS",
        "cv_base_leakage": False,
        "model_artifact_sha256": trained["model_file_sha256"],
        "model_artifact_internal_sha256": model["artifact_hash"],
        "model_artifact_created_before_benchmark_replay": True,
        "model_selection_used_2025_2026": False,
        "hyperparameter_tuning_used_2025_2026": False,
        "stage_b_shape_hash_r1": r1_effective_shape,
        "stage_b_shape_hash_r2": r2_effective_shape,
        "stage_b_shape_unchanged": True,
        "r1_r2_single_day_peak_date_changed_count": single_changed,
        "r1_r2_rolling7_start_date_changed_count": rolling_changed,
        "full39_season_total_metrics": full_total_metrics,
        "common30_season_total_metrics": common_total_metrics,
        "full39_daily_metrics": full_daily_metrics,
        "common30_daily_metrics": common_daily_metrics,
        "support_strata": support_rows,
        "training_support_counts": {"support_0": 13, "support_1": 15, "support_2plus": 11},
        "r2_vs_baseline_season_total_wape_delta": decimal_text(r2_baseline_delta),
        "r2_vs_r1_season_total_wape_delta": decimal_text(r2_r1_delta),
        "r1_total_bias_kg": decimal_text(r1_bias),
        "r2_total_bias_kg": decimal_text(r2_bias),
        "r2_total_bias_ratio": decimal_text(r2_bias_ratio),
        "per_base_error_win_counts": win_summary,
        "yield_distribution": yield_distribution,
        "stage_b_daily_sum_reconciliation": "PASS",
        "benchmark_scope": "FROZEN_BENCHMARK_REPLAY",
        "pristine_future_validation_pending": True,
        "model_production_ready": False,
        "model_readiness_status": readiness,
        "business_acceptance_threshold": "NOT_DEFINED",
        "stage_a_cv_results_sha256": sha256_file(
            output_root / "stage-a-training-cv-results-r1.csv"
        ),
        "stage_a_cv_summary_sha256": sha256_file(
            output_root / "stage-a-candidate-cv-summary-r1.csv"
        ),
        "r2_season_prediction_sha256": pred["seal"]["season_prediction_sha256"],
        "r2_daily_prediction_sha256": pred["seal"]["daily_prediction_sha256"],
        "r2_prediction_seal": pred["seal"],
        "oot_actuals_used_for_fit_or_selection": False,
    }
    _write_csv(
        output_root / "r1-vs-r2-vs-baseline-full39-r1.csv", list(full_base_rows[0]), full_base_rows
    )
    _write_csv(
        output_root / "v07-vs-r1-vs-r2-common30-r1.csv", list(common_base_rows[0]), common_base_rows
    )
    _write_csv(
        output_root / "training-support-strata-comparison-r1.csv",
        [
            "support_stratum",
            "base_count",
            "model_id",
            "season_total_wape",
            "season_total_mae_kg",
            "season_total_bias_kg",
        ],
        support_rows,
    )
    bias_rows = []
    for model_name, model_map in (
        ("baseline", baseline_totals),
        ("r1", r1_totals),
        ("r2", r2_totals),
    ):
        bias, ratio = _sum_bias(actual, model_map)
        bias_rows.append(
            {
                "model": model_name,
                "signed_bias_kg_predicted_minus_actual": decimal_text(bias),
                "bias_ratio": decimal_text(ratio),
                "overpredict_base_count": str(
                    sum(model_map[base] > actual[base] for base in full_bases)
                ),
                "underpredict_base_count": str(
                    sum(model_map[base] < actual[base] for base in full_bases)
                ),
                "tie_base_count": str(sum(model_map[base] == actual[base] for base in full_bases)),
            }
        )
    _write_csv(
        output_root / "benchmark-bias-diagnosis-r1.csv",
        [
            "model",
            "signed_bias_kg_predicted_minus_actual",
            "bias_ratio",
            "overpredict_base_count",
            "underpredict_base_count",
            "tie_base_count",
        ],
        bias_rows,
    )
    _write_json(output_root / "benchmark-yield-distribution-r1.json", yield_distribution)
    _write_json(output_root / "experiment-summary-r1.json", summary)
    return summary


def run_experiment(config_path: Path, artifact_root: Path, output_root: Path) -> dict[str, Any]:
    config = _load_config(config_path)
    if not output_root.is_absolute():
        output_root = output_root.resolve()
    if output_root.exists():
        raise R2ExperimentError("PRIVATE_OUTPUT_DIRECTORY_ALREADY_EXISTS_NO_OVERWRITE")
    s8_root, r1_model, _s9_evidence = verify_frozen_inputs(config, artifact_root)
    if sha256_file(CONFIG_PATH) != sha256_file(config_path):
        raise R2ExperimentError("R2_CONFIG_CHANGED_DURING_RUN")
    training_daily_path = _safe_manifest_file(s8_root, "training-daily-curves-r1.csv")
    training_path = _safe_manifest_file(s8_root, "v0-8-canonical-training-dataset-r1.csv")
    oot_path = _safe_manifest_file(s8_root, "v0-8-canonical-oot-dataset-r1.csv")
    if sha256_file(training_path) != config["training"]["expected_sha256"]:
        raise R2ExperimentError("BLOCKED_TRAINING_DATASET_DRIFT")
    # Hash-only pin verification above does not parse the benchmark. All model
    # selection calls below receive training rows only.
    training_daily_sha = sha256_file(training_daily_path)
    trained = _run_training_and_freeze(
        config=config,
        s8_root=s8_root,
        r1_model=r1_model,
        output_root=output_root,
    )
    # Ensure benchmark row bytes remain exactly the pinned S8 artifact at the
    # boundary between model freeze and benchmark replay.
    if sha256_file(oot_path) != config["s8"]["oot_dataset_sha256"]:
        raise R2ExperimentError("BLOCKED_S8_ARTIFACT_DRIFT:BENCHMARK_BEFORE_REPLAY")
    summary = _score_frozen_benchmark(
        config=config, s8_root=s8_root, output_root=output_root, trained=trained
    )
    if training_daily_sha != trained["training_daily_sha256"]:
        raise R2ExperimentError("TRAINING_DAILY_INPUT_CHANGED_DURING_RUN")
    files = _private_file_map(output_root)
    manifest = {
        "task_id": config["task_id"],
        "artifact_schema": "V0_8_R2_STAGE_A_SHRINKAGE_EXPERIMENT_R1",
        "artifact_count": len(files),
        "artifacts": files,
    }
    _write_json(output_root / "artifact-manifest.json", manifest)
    return summary


def _public_evidence(
    *, config: Mapping[str, Any], summary: Mapping[str, Any], run1: Path, run2: Path
) -> dict[str, Any]:
    full_metrics = summary["full39_season_total_metrics"]
    full_daily = summary["full39_daily_metrics"]
    common_total = summary["common30_season_total_metrics"]
    common_daily = summary["common30_daily_metrics"]
    baseline_id, r1_id, r2_id, v07_id = (
        MODEL_IDS["baseline"],
        MODEL_IDS["r1"],
        MODEL_IDS["r2"],
        MODEL_IDS["v07"],
    )

    def season_total_diagnostics(metric: Mapping[str, Any]) -> dict[str, Any]:
        per_base = list(metric["per_base"].values())
        return {
            "n": metric["n"],
            "wape": metric["wape"],
            "mae_kg": metric["mae"],
            "median_ape": metric["median_ape"],
            "bias_sum_predicted_minus_actual_kg": metric["bias_sum_predicted_minus_actual"],
            "predicted_sum_kg": metric["predicted_sum"],
            "actual_sum_kg": metric["actual_sum"],
            "overpredict_base_count": sum(
                decimal_value(row["predicted_total_kg"], "predicted_total")
                > decimal_value(row["actual_total_kg"], "actual_total")
                for row in per_base
            ),
            "underpredict_base_count": sum(
                decimal_value(row["predicted_total_kg"], "predicted_total")
                < decimal_value(row["actual_total_kg"], "actual_total")
                for row in per_base
            ),
            "tie_base_count": sum(
                decimal_value(row["predicted_total_kg"], "predicted_total")
                == decimal_value(row["actual_total_kg"], "actual_total")
                for row in per_base
            ),
            "absolute_error_distribution_kg": metric["absolute_error_distribution"],
            "per_base_absolute_percentage_error_distribution": metric[
                "per_base_absolute_percentage_error_distribution"
            ],
        }

    def delta(left: Any, right: Any, field: str, label: str) -> str:
        return decimal_text(
            decimal_value(left[field], f"{label}_left")
            - decimal_value(right[field], f"{label}_right")
        )

    return {
        "task_id": config["task_id"],
        "result": summary["result"],
        "base_main_sha": config["baseline_main_sha"],
        "head_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip(),
        "branch": subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=REPO_ROOT, text=True
        ).strip(),
        "scope": {
            "training_dataset_row_count": 37,
            "training_dataset_sha256": summary["training_dataset_sha256"],
            "training_dataset_matches_s8": True,
            "blocked_training_rows_included": 0,
            "frozen_benchmark_row_count": 39,
            "benchmark_season": OOT_SEASON,
            "benchmark_role": "FROZEN_BENCHMARK_REPLAY",
            "pristine_future_validation_pending": True,
            "common_comparator_count": 30,
        },
        "s8_pins": {
            "private_manifest_sha256": config["s8"]["private_manifest_sha256"],
            "all_manifest_artifact_hashes_verified": True,
            "artifact_count": 59,
            "training_dataset_sha256": config["s8"]["training_dataset_sha256"],
            "oot_dataset_sha256": config["s8"]["oot_dataset_sha256"],
            "r1_model_artifact_sha256": config["s8"]["r1_model_artifact_sha256"],
            "repository_evidence_sha256": config["s8"]["repository_evidence_sha256"],
            "repository_config_sha256": config["s8"]["repository_config_sha256"],
            "stage_b_shape_sha256": config["s8"]["stage_b_shape_sha256"],
            "s9_evidence_sha256": config["s8"]["s9_evidence_sha256"],
            "s9_private_manifest_sha256": config["s8"]["s9_private_manifest_sha256"],
        },
        "selection": {
            "candidate_count": 3,
            "candidates": [
                "GLOBAL_POOLED_YIELD",
                "SHRINKAGE_BASE_YIELD",
                "REGULARIZED_BASE_EFFECT",
            ],
            "cv_strategy": summary["cv_strategy"],
            "cv_primary_metric": "GROUPED_CV_SEASON_TOTAL_WAPE",
            "selected_stage_a_model": summary["selected_stage_a_model"],
            "selected_hyperparameter": summary["selected_hyperparameter"],
            "selected_model_cv_wape": summary["selected_model_cv_wape"],
            "model_selection_used_2025_2026": False,
            "hyperparameter_tuning_used_2025_2026": False,
            "training_only_selection": True,
        },
        "stage_b": {
            "shape_hash_r1": summary["stage_b_shape_hash_r1"],
            "shape_hash_r2": summary["stage_b_shape_hash_r2"],
            "unchanged": summary["stage_b_shape_unchanged"],
            "single_day_peak_date_changed_count": summary[
                "r1_r2_single_day_peak_date_changed_count"
            ],
            "rolling7_start_date_changed_count": summary["r1_r2_rolling7_start_date_changed_count"],
        },
        "metrics": {
            "full39_season_total_wape": {
                "baseline": full_metrics[baseline_id]["wape"],
                "v08_r1": full_metrics[r1_id]["wape"],
                "v08_r2": full_metrics[r2_id]["wape"],
            },
            "full39_season_total_mae_kg": {
                "baseline": full_metrics[baseline_id]["mae"],
                "v08_r1": full_metrics[r1_id]["mae"],
                "v08_r2": full_metrics[r2_id]["mae"],
            },
            "full39_daily_wape": {
                "baseline": full_daily[baseline_id]["daily"]["wape"],
                "v08_r1": full_daily[r1_id]["daily"]["wape"],
                "v08_r2": full_daily[r2_id]["daily"]["wape"],
            },
            "full39_daily_mae_kg": {
                "baseline": full_daily[baseline_id]["daily"]["mae"],
                "v08_r1": full_daily[r1_id]["daily"]["mae"],
                "v08_r2": full_daily[r2_id]["daily"]["mae"],
            },
            "full39_single_day_peak_quantity_wape": {
                "baseline": full_daily[baseline_id]["single_day_peak"]["wape"],
                "v08_r1": full_daily[r1_id]["single_day_peak"]["wape"],
                "v08_r2": full_daily[r2_id]["single_day_peak"]["wape"],
            },
            "full39_single_day_peak_date_mae_days": {
                "baseline": full_daily[baseline_id]["single_day_peak"]["date_mae_days"],
                "v08_r1": full_daily[r1_id]["single_day_peak"]["date_mae_days"],
                "v08_r2": full_daily[r2_id]["single_day_peak"]["date_mae_days"],
            },
            "full39_rolling7_quantity_wape": {
                "baseline": full_daily[baseline_id]["rolling7_peak"]["wape"],
                "v08_r1": full_daily[r1_id]["rolling7_peak"]["wape"],
                "v08_r2": full_daily[r2_id]["rolling7_peak"]["wape"],
            },
            "full39_rolling7_start_date_mae_days": {
                "baseline": full_daily[baseline_id]["rolling7_peak"]["start_date_mae_days"],
                "v08_r1": full_daily[r1_id]["rolling7_peak"]["start_date_mae_days"],
                "v08_r2": full_daily[r2_id]["rolling7_peak"]["start_date_mae_days"],
            },
            "common30_season_total_wape": {
                "v07": common_total[v07_id]["wape"],
                "baseline": common_total[baseline_id]["wape"],
                "v08_r1": common_total[r1_id]["wape"],
                "v08_r2": common_total[r2_id]["wape"],
            },
            "common30_daily_wape": {
                model_key: common_daily[model_id]["daily"]["wape"]
                for model_key, model_id in (
                    ("v07", v07_id),
                    ("baseline", baseline_id),
                    ("v08_r1", r1_id),
                    ("v08_r2", r2_id),
                )
            },
            "common30_daily_mae_kg": {
                model_key: common_daily[model_id]["daily"]["mae"]
                for model_key, model_id in (
                    ("v07", v07_id),
                    ("baseline", baseline_id),
                    ("v08_r1", r1_id),
                    ("v08_r2", r2_id),
                )
            },
            "common30_single_day_peak_quantity_wape": {
                model_key: common_daily[model_id]["single_day_peak"]["wape"]
                for model_key, model_id in (
                    ("v07", v07_id),
                    ("baseline", baseline_id),
                    ("v08_r1", r1_id),
                    ("v08_r2", r2_id),
                )
            },
            "common30_single_day_peak_date_mae_days": {
                model_key: common_daily[model_id]["single_day_peak"]["date_mae_days"]
                for model_key, model_id in (
                    ("v07", v07_id),
                    ("baseline", baseline_id),
                    ("v08_r1", r1_id),
                    ("v08_r2", r2_id),
                )
            },
            "common30_rolling7_quantity_wape": {
                model_key: common_daily[model_id]["rolling7_peak"]["wape"]
                for model_key, model_id in (
                    ("v07", v07_id),
                    ("baseline", baseline_id),
                    ("v08_r1", r1_id),
                    ("v08_r2", r2_id),
                )
            },
            "common30_rolling7_start_date_mae_days": {
                model_key: common_daily[model_id]["rolling7_peak"]["start_date_mae_days"]
                for model_key, model_id in (
                    ("v07", v07_id),
                    ("baseline", baseline_id),
                    ("v08_r1", r1_id),
                    ("v08_r2", r2_id),
                )
            },
        },
        "season_total_diagnostics": {
            "full39": {
                "baseline": season_total_diagnostics(full_metrics[baseline_id]),
                "v08_r1": season_total_diagnostics(full_metrics[r1_id]),
                "v08_r2": season_total_diagnostics(full_metrics[r2_id]),
            },
            "common30": {
                "v07": season_total_diagnostics(common_total[v07_id]),
                "baseline": season_total_diagnostics(common_total[baseline_id]),
                "v08_r1": season_total_diagnostics(common_total[r1_id]),
                "v08_r2": season_total_diagnostics(common_total[r2_id]),
            },
        },
        "metric_deltas": {
            "full39_r2_minus_baseline_season_total_wape": decimal_text(
                decimal_value(full_metrics[r2_id]["wape"], "r2_wape")
                - decimal_value(full_metrics[baseline_id]["wape"], "baseline_wape")
            ),
            "full39_r2_minus_r1_season_total_wape": decimal_text(
                decimal_value(full_metrics[r2_id]["wape"], "r2_wape")
                - decimal_value(full_metrics[r1_id]["wape"], "r1_wape")
            ),
            "full39_r2_minus_r1_daily_wape": decimal_text(
                decimal_value(full_daily[r2_id]["daily"]["wape"], "r2_daily_wape")
                - decimal_value(full_daily[r1_id]["daily"]["wape"], "r1_daily_wape")
            ),
            "common30_r2_minus_v07_season_total_wape": decimal_text(
                decimal_value(common_total[r2_id]["wape"], "r2_wape")
                - decimal_value(common_total[v07_id]["wape"], "v07_wape")
            ),
            "common30_r2_minus_r1_season_total_wape": decimal_text(
                decimal_value(common_total[r2_id]["wape"], "r2_wape")
                - decimal_value(common_total[r1_id]["wape"], "r1_wape")
            ),
            "common30_r2_minus_baseline_season_total_wape": decimal_text(
                decimal_value(common_total[r2_id]["wape"], "r2_wape")
                - decimal_value(common_total[baseline_id]["wape"], "baseline_wape")
            ),
            "common30_r2_minus_v07_daily_wape": decimal_text(
                decimal_value(common_daily[r2_id]["daily"]["wape"], "r2_daily_wape")
                - decimal_value(common_daily[v07_id]["daily"]["wape"], "v07_daily_wape")
            ),
            "common30_r2_minus_r1_daily_wape": decimal_text(
                decimal_value(common_daily[r2_id]["daily"]["wape"], "r2_daily_wape")
                - decimal_value(common_daily[r1_id]["daily"]["wape"], "r1_daily_wape")
            ),
            "full39_r2_minus_r1_season_total_mae_kg": delta(
                full_metrics[r2_id], full_metrics[r1_id], "mae", "full39_total_mae"
            ),
            "full39_r2_minus_r1_daily_mae_kg": delta(
                full_daily[r2_id]["daily"], full_daily[r1_id]["daily"], "mae", "full39_daily_mae"
            ),
            "full39_r2_minus_baseline_single_day_peak_quantity_wape": delta(
                full_daily[r2_id]["single_day_peak"],
                full_daily[baseline_id]["single_day_peak"],
                "wape",
                "full39_peak_wape",
            ),
            "full39_r2_minus_r1_single_day_peak_quantity_wape": delta(
                full_daily[r2_id]["single_day_peak"],
                full_daily[r1_id]["single_day_peak"],
                "wape",
                "full39_peak_wape",
            ),
            "full39_r2_minus_baseline_rolling7_quantity_wape": delta(
                full_daily[r2_id]["rolling7_peak"],
                full_daily[baseline_id]["rolling7_peak"],
                "wape",
                "full39_rolling7_wape",
            ),
            "full39_r2_minus_r1_rolling7_quantity_wape": delta(
                full_daily[r2_id]["rolling7_peak"],
                full_daily[r1_id]["rolling7_peak"],
                "wape",
                "full39_rolling7_wape",
            ),
            "common30_r2_minus_v07_single_day_peak_quantity_wape": delta(
                common_daily[r2_id]["single_day_peak"],
                common_daily[v07_id]["single_day_peak"],
                "wape",
                "common30_peak_wape",
            ),
            "common30_r2_minus_v07_rolling7_quantity_wape": delta(
                common_daily[r2_id]["rolling7_peak"],
                common_daily[v07_id]["rolling7_peak"],
                "wape",
                "common30_rolling7_wape",
            ),
        },
        "candidate_cv_summary": [
            {
                field: row[field]
                for field in (
                    "model_candidate",
                    "hyperparameter",
                    "cv_primary_metric",
                    "cv_wape",
                    "mae_kg",
                    "bias_kg",
                    "median_ape",
                    "fold_count",
                    "validation_row_count",
                    "complexity_rank",
                )
            }
            for row in read_csv(run1 / "stage-a-candidate-cv-summary-r1.csv")
        ],
        "support_strata": summary["support_strata"],
        "bias": {
            "r1_signed_kg": summary["r1_total_bias_kg"],
            "r2_signed_kg": summary["r2_total_bias_kg"],
            "r2_ratio": summary["r2_total_bias_ratio"],
        },
        "per_base_error_win_counts": summary["per_base_error_win_counts"],
        "yield_distribution": summary["yield_distribution"],
        "readiness": {
            "status": summary["model_readiness_status"],
            "model_production_ready": False,
            "business_acceptance_threshold": "NOT_DEFINED",
            "benchmark_scope": "FROZEN_BENCHMARK_REPLAY",
        },
        "replay": {
            "deterministic_training": "PASS",
            "model_hash_match": sha256_file(run1 / "selected-stage-a-model-artifact-r1.json")
            == sha256_file(run2 / "selected-stage-a-model-artifact-r1.json"),
            "prediction_hash_match": sha256_file(run1 / "r2-frozen-benchmark-season-total-r1.csv")
            == sha256_file(run2 / "r2-frozen-benchmark-season-total-r1.csv")
            and sha256_file(run1 / "r2-frozen-benchmark-daily-r1.csv")
            == sha256_file(run2 / "r2-frozen-benchmark-daily-r1.csv"),
            "all_private_artifacts_byte_identical": _compare_run_artifacts(run1, run2),
            "model_training_executed": True,
            "model_refit_executed": True,
            "benchmark_replay_executed": True,
            "pr_created": False,
            "ready_action_taken": False,
            "merge_action_taken": False,
        },
        "artifact_hashes": {
            "model_sha256": summary["model_artifact_sha256"],
            "cv_results_sha256": summary["stage_a_cv_results_sha256"],
            "cv_summary_sha256": summary["stage_a_cv_summary_sha256"],
            "benchmark_season_prediction_sha256": summary["r2_season_prediction_sha256"],
            "benchmark_daily_prediction_sha256": summary["r2_daily_prediction_sha256"],
            "private_manifest_sha256": sha256_file(run1 / "artifact-manifest.json"),
        },
        "non_actions": {
            "data_governance_reopened": False,
            "area_quantity_identity_authority_changed": False,
            "stage_b_changed": False,
            "2025_2026_used_for_tuning_or_selection": False,
            "production_promotion_authorized": False,
        },
    }


def _compare_run_artifacts(first: Path, second: Path) -> bool:
    first_files = _private_file_map(first)
    second_files = _private_file_map(second)
    if first_files != second_files:
        return False
    first_manifest = _read_json(first / "artifact-manifest.json")
    second_manifest = _read_json(second / "artifact-manifest.json")
    return first_manifest == second_manifest


def finalize_evidence(
    *, config_path: Path, run1: Path, run2: Path, evidence_path: Path
) -> dict[str, Any]:
    config = _load_config(config_path)
    if not run1.is_dir() or not run2.is_dir():
        raise R2ExperimentError("DETERMINISM_REPLAY_DIRECTORY_MISSING")
    if not _compare_run_artifacts(run1, run2):
        raise R2ExperimentError("BLOCKED_NON_DETERMINISTIC_R2_REPLAY")
    summary = _read_json(run1 / "experiment-summary-r1.json")
    summary2 = _read_json(run2 / "experiment-summary-r1.json")
    if summary != summary2:
        raise R2ExperimentError("BLOCKED_NON_DETERMINISTIC_R2_SUMMARY")
    evidence = _public_evidence(config=config, summary=summary, run1=run1, run2=run2)
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_bytes(canonical_json_bytes(evidence) + b"\n")
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("run", "finalize"), required=True)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--run1", type=Path)
    parser.add_argument("--run2", type=Path)
    parser.add_argument(
        "--evidence-output",
        type=Path,
        default=REPO_ROOT / "docs/v0-8/evidence/r2-stage-a-shrinkage-model-experiment-r1.json",
    )
    args = parser.parse_args()
    try:
        if args.phase == "run":
            if args.output_dir is None:
                raise R2ExperimentError("OUTPUT_DIR_REQUIRED_FOR_RUN")
            result = run_experiment(args.config, args.artifact_root, args.output_dir)
            print(
                json.dumps(
                    {
                        "result": result["result"],
                        "selected": result["selected_stage_a_model"],
                        "wape": result["full39_season_total_metrics"][MODEL_IDS["r2"]]["wape"],
                    },
                    sort_keys=True,
                )
            )
        else:
            if args.run1 is None or args.run2 is None:
                raise R2ExperimentError("BOTH_REPLAY_DIRECTORIES_REQUIRED_FOR_FINALIZE")
            result = finalize_evidence(
                config_path=args.config,
                run1=args.run1,
                run2=args.run2,
                evidence_path=args.evidence_output,
            )
            print(
                json.dumps(
                    {"result": result["result"], "evidence": str(args.evidence_output)},
                    sort_keys=True,
                )
            )
    except (R2ExperimentError, OSError, KeyError, ValueError) as exc:
        print(f"BLOCKED:{exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
