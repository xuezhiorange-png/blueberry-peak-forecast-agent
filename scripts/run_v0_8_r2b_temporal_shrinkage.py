#!/usr/bin/env python3
"""Run the frozen 2023-24 -> 2024-25 temporal shrinkage identifiability experiment."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import stat
from collections.abc import Mapping, Sequence
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

from backend.app.area_yield.v08_r2b_temporal_shrinkage import (
    ALLOWED_LAMBDAS,
    EXPECTED_DATASET_SHA256,
    R2BExperimentError,
    build_candidate_predictions,
    candidate_metrics,
    decimal_text,
    decimal_value,
    history_diagnostics,
    project_rows_before_freeze,
    select_candidate,
    validate_dataset_hash,
    validate_support_zero_parity,
    validate_temporal_cohorts,
    win_loss_counts,
)

TASK_ID = "V0_8_R2B_TEMPORAL_FORWARD_SHRINKAGE_IDENTIFIABILITY_R1"
BASE_MAIN_SHA = "5c66d8d8565eb87e1434e61de2939dcce4d7df75"
FORBIDDEN_SEASON = "2025-2026"
GLOBAL_YIELD_POLICY = "AREA_WEIGHTED_POOLED_SUM_QUANTITY_DIVIDED_BY_SUM_AREA_TRAIN_2023_2024_ONLY"
PREDICTION_FIELDS = (
    "base_id",
    "canonical_base_name",
    "season",
    "support_group",
    "support_count",
    "validation_area_mu",
    "global_yield",
    "global_predicted_total",
    "base_historical_yield",
    "base_specific_predicted_yield",
    "base_specific_predicted_total",
    *(
        field
        for lam in ALLOWED_LAMBDAS
        for field in (
            f"lambda_{str(lam).replace('.', '_')}_weight",
            f"lambda_{str(lam).replace('.', '_')}_yield",
            f"lambda_{str(lam).replace('.', '_')}_predicted_total",
        )
    ),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_bytes_exclusive(path: Path, payload: bytes, mode: int = 0o600) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise
    os.chmod(path, mode)


def write_json(path: Path, value: Any) -> None:
    payload = (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )
    _write_bytes_exclusive(path, payload)


def write_csv(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    from io import StringIO

    buffer = StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=list(fields),
        extrasaction="ignore",
        lineterminator="\n",
        quoting=csv.QUOTE_MINIMAL,
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({field: str(row.get(field, "")) for field in fields})
    _write_bytes_exclusive(path, buffer.getvalue().encode("utf-8"))


def read_pre_freeze_projected_rows(path: Path) -> list[dict[str, str]]:
    """Read only train labels and validation covariates from the canonical CSV.

    CSV target cells for 2024-2025 are intentionally not indexed or copied until
    after the prediction freeze. The forbidden 2025-2026 gate is checked using
    the season cell before any target cell is touched.
    """
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        try:
            headers = next(reader)
        except StopIteration as exc:
            raise R2BExperimentError("CANONICAL_DATASET_HEADER_MISSING") from exc
        if not headers:
            raise R2BExperimentError("CANONICAL_DATASET_HEADER_MISSING")
        required = {
            "base_id",
            "canonical_base_name",
            "season",
            "area_mu",
            "season_total_quantity_kg",
            "strict_training_eligible",
        }
        if not required.issubset(headers):
            raise R2BExperimentError("CANONICAL_DATASET_SCHEMA_MISMATCH")
        index = {name: headers.index(name) for name in headers}
        projected_rows: list[dict[str, str]] = []
        for cells in reader:
            if len(cells) != len(headers):
                raise R2BExperimentError("CANONICAL_DATASET_ROW_WIDTH_MISMATCH")
            season = cells[index["season"]]
            if season == FORBIDDEN_SEASON:
                raise R2BExperimentError("BLOCKED_2025_2026_ACCESS")
            if season not in {"2023-2024", "2024-2025"}:
                raise R2BExperimentError("BLOCKED_UNAUTHORIZED_SEASON")
            allowed = [
                "base_id",
                "canonical_base_name",
                "season",
                "area_mu",
                "strict_training_eligible",
                "area_authority_id",
                "area_authority_sha256",
                "quantity_authority_id",
                "quantity_authority_sha256",
                "identity_authority_id",
                "identity_authority_sha256",
                "source_signature",
                "eligibility_signature",
            ]
            if season == "2023-2024":
                allowed.append("season_total_quantity_kg")
            projected_rows.append(
                {field: cells[index[field]] for field in allowed if field in index}
            )
        return projected_rows


def _read_validation_actuals_after_freeze(
    source_path: Path,
    output_dir: Path,
    expected_source_sha256: str,
    expected_prediction_sha256: str,
    expected_keys: set[str],
) -> list[dict[str, str]]:
    manifest_path = output_dir / "prediction-freeze-manifest-r1.json"
    predictions_path = output_dir / "temporal-validation-predictions-r1.csv"
    if not manifest_path.is_file() or not predictions_path.is_file():
        raise R2BExperimentError("PREDICTIONS_NOT_FROZEN_BEFORE_SCORING")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        sha256_file(source_path) != expected_source_sha256
        or manifest.get("canonical_training_dataset_sha256") != expected_source_sha256
    ):
        raise R2BExperimentError("BLOCKED_TRAINING_DATASET_DRIFT_AFTER_FREEZE")
    actual_prediction_hash = sha256_file(predictions_path)
    if (
        manifest.get("predictions_frozen") is not True
        or manifest.get("validation_actual_accessed_before_freeze") is not False
        or manifest.get("predictions_sha256") != expected_prediction_sha256
        or actual_prediction_hash != expected_prediction_sha256
    ):
        raise R2BExperimentError("PREDICTION_FREEZE_INTEGRITY_FAILURE")

    actual_rows: list[dict[str, str]] = []
    seen: set[str] = set()
    with source_path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        try:
            headers = next(reader)
        except StopIteration as exc:
            raise R2BExperimentError("CANONICAL_DATASET_HEADER_MISSING") from exc
        columns = {name: headers.index(name) for name in headers}
        for cells in reader:
            season = cells[columns["season"]]
            if season == FORBIDDEN_SEASON:
                raise R2BExperimentError("BLOCKED_2025_2026_ACCESS")
            if season != "2024-2025":
                continue
            base_id = cells[columns["base_id"]]
            if base_id in seen:
                raise R2BExperimentError("DUPLICATE_VALIDATION_ACTUAL")
            seen.add(base_id)
            # Validation targets are first indexed only after the prediction hash gate above.
            quantity = decimal_value(
                cells[columns["season_total_quantity_kg"]], "validation_actual_total"
            )
            area = decimal_value(cells[columns["area_mu"]], "validation_actual_area")
            if quantity <= 0 or area <= 0:
                raise R2BExperimentError("NONPOSITIVE_VALIDATION_TRUTH")
            with localcontext() as context:
                context.prec = 60
                yield_value = quantity / area
            actual_rows.append(
                {
                    "base_id": base_id,
                    "season": season,
                    "area_mu": decimal_text(area),
                    "actual_total_kg": decimal_text(quantity),
                    "actual_yield_kg_per_mu": decimal_text(yield_value),
                }
            )
    if seen != expected_keys or len(actual_rows) != 22:
        raise R2BExperimentError("BLOCKED_TEMPORAL_COHORT_MISMATCH:VALIDATION_TRUTH_KEYS")
    actual_rows.sort(key=lambda row: row["base_id"])
    return actual_rows


def _candidate_definitions() -> list[dict[str, str]]:
    result = [
        {"candidate": "GLOBAL_POOLED_YIELD", "lambda": "NONE", "complexity_rank": "0"},
        {"candidate": "BASE_SPECIFIC_NO_SHRINKAGE", "lambda": "NONE", "complexity_rank": "1"},
    ]
    result.extend(
        {
            "candidate": "SHRINKAGE_BASE_YIELD",
            "lambda": decimal_text(lam),
            "complexity_rank": "2",
        }
        for lam in ALLOWED_LAMBDAS
    )
    return result


def _build_support_ledger(
    train: Sequence[Mapping[str, str]], validation: Sequence[Mapping[str, str]]
) -> list[dict[str, str]]:
    train_by_base = {str(row["base_id"]): row for row in train}
    result: list[dict[str, str]] = []
    for row in validation:
        base = str(row["base_id"])
        source = train_by_base.get(base)
        result.append(
            {
                "base_id": base,
                "base_name": str(row["canonical_base_name"]),
                "has_2023_2024_training_sample": "true" if source else "false",
                "support_count": "1" if source else "0",
                "train_area_mu": "" if source is None else source["area_mu"],
                "train_quantity_kg": "" if source is None else source["season_total_quantity_kg"],
                "train_yield_kg_per_mu": "" if source is None else source["yield_kg_per_mu"],
                "validation_area_mu": str(row["area_mu"]),
                "support_group": "SUPPORT_1" if source else "SUPPORT_0",
            }
        )
    return result


def _build_candidate_summaries(
    predictions: Sequence[Mapping[str, str]], actuals: Mapping[str, Decimal]
) -> tuple[list[dict[str, str | int]], list[dict[str, str | int]]]:
    specs: list[tuple[str, str, str]] = [("GLOBAL_POOLED_YIELD", "NONE", "global_predicted_total")]
    specs.append(("BASE_SPECIFIC_NO_SHRINKAGE", "NONE", "base_specific_predicted_total"))
    specs.extend(
        (
            "SHRINKAGE_BASE_YIELD",
            decimal_text(lam),
            f"lambda_{str(lam).replace('.', '_')}_predicted_total",
        )
        for lam in ALLOWED_LAMBDAS
    )
    by_support1: list[dict[str, str | int]] = []
    by_all: list[dict[str, str | int]] = []
    for candidate, lam, field in specs:
        for support_group, destination in (("SUPPORT_1", by_support1), (None, by_all)):
            metrics = candidate_metrics(
                predictions,
                actuals,
                field,
                support_group=support_group,
            )
            destination.append(
                {
                    "candidate": candidate,
                    "lambda": lam,
                    "cohort": "SUPPORT_1" if support_group else "ALL_22",
                    **metrics,
                }
            )
    return by_support1, by_all


def _build_scoring_rows(
    predictions: Sequence[Mapping[str, str]], actual_rows: Sequence[Mapping[str, str]]
) -> list[dict[str, str]]:
    actual_by_base = {str(row["base_id"]): row for row in actual_rows}
    if set(actual_by_base) != {str(row["base_id"]) for row in predictions}:
        raise R2BExperimentError("SCORING_COHORT_KEY_MISMATCH")
    result: list[dict[str, str]] = []
    candidates = [
        ("global", "global_predicted_total"),
        ("base_specific", "base_specific_predicted_total"),
        *[
            (
                f"lambda_{str(lam).replace('.', '_')}",
                f"lambda_{str(lam).replace('.', '_')}_predicted_total",
            )
            for lam in ALLOWED_LAMBDAS
        ],
    ]
    for prediction in predictions:
        actual = actual_by_base[str(prediction["base_id"])]
        actual_total = decimal_value(actual["actual_total_kg"], "actual_total")
        row = {
            "base_id": str(prediction["base_id"]),
            "base_name": str(prediction["canonical_base_name"]),
            "season": "2024-2025",
            "support_group": str(prediction["support_group"]),
            "validation_area_mu": str(prediction["validation_area_mu"]),
            "actual_total_kg": decimal_text(actual_total),
            "actual_yield_kg_per_mu": str(actual["actual_yield_kg_per_mu"]),
        }
        for candidate, prediction_field in candidates:
            predicted = decimal_value(prediction[prediction_field], prediction_field)
            signed_error = predicted - actual_total
            with localcontext() as context:
                context.prec = 60
                ape = abs(signed_error) / actual_total
            row[f"{candidate}_predicted_total_kg"] = decimal_text(predicted)
            row[f"{candidate}_abs_error_kg"] = decimal_text(abs(signed_error))
            row[f"{candidate}_ape"] = decimal_text(ape)
            row[f"{candidate}_signed_error_kg"] = decimal_text(signed_error)
        result.append(row)
    return result


def _history_diagnosis_rows(
    predictions: Sequence[Mapping[str, str]], actual_rows: Sequence[Mapping[str, str]]
) -> list[dict[str, str]]:
    actual_by_base = {row["base_id"]: row for row in actual_rows}
    result: list[dict[str, str]] = []
    for row in predictions:
        if row["support_group"] != "SUPPORT_1":
            continue
        actual = actual_by_base[row["base_id"]]
        hist = decimal_value(row["base_historical_yield"], "historical_yield")
        actual_yield = decimal_value(actual["actual_yield_kg_per_mu"], "actual_yield")
        global_yield = decimal_value(row["global_yield"], "global_yield")
        hist_dev = hist - global_yield
        actual_dev = actual_yield - global_yield
        if hist_dev == 0 or actual_dev == 0:
            persisted = False
        else:
            persisted = (hist_dev > 0) == (actual_dev > 0)
        history_distance = abs(actual_yield - hist)
        global_distance = abs(actual_yield - global_yield)
        closer = (
            "BASE_HISTORY_CLOSER"
            if history_distance < global_distance
            else "GLOBAL_YIELD_CLOSER"
            if history_distance > global_distance
            else "TIE"
        )
        result.append(
            {
                "base_id": row["base_id"],
                "base_name": row["canonical_base_name"],
                "yield_2023_2024": decimal_text(hist),
                "yield_2024_2025": decimal_text(actual_yield),
                "global_yield_2023_2024": decimal_text(global_yield),
                "historical_deviation_direction": "ABOVE"
                if hist_dev > 0
                else "BELOW"
                if hist_dev < 0
                else "AT_GLOBAL",
                "validation_deviation_direction": "ABOVE"
                if actual_dev > 0
                else "BELOW"
                if actual_dev < 0
                else "AT_GLOBAL",
                "direction_persisted": "true" if persisted else "false",
                "closer_estimate": closer,
                "absolute_history_yield_error": decimal_text(history_distance),
                "absolute_global_yield_error": decimal_text(global_distance),
            }
        )
    return result


def _candidate_field(candidate: str, lam: str = "NONE") -> str:
    if candidate == "GLOBAL_POOLED_YIELD":
        return "global_predicted_total"
    if candidate == "BASE_SPECIFIC_NO_SHRINKAGE":
        return "base_specific_predicted_total"
    if candidate == "SHRINKAGE_BASE_YIELD":
        return f"lambda_{lam.replace('.', '_')}_predicted_total"
    raise R2BExperimentError("UNAUTHORIZED_CANDIDATE_FIELD")


def run_replay(source_path: Path, replay_dir: Path, source_hash: str) -> dict[str, Any]:
    replay_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
    os.chmod(replay_dir, 0o700)
    source_rows = read_pre_freeze_projected_rows(source_path)
    train, validation = project_rows_before_freeze(source_rows)
    cohort_counts = validate_temporal_cohorts(train, validation)
    support_ledger = _build_support_ledger(train, validation)
    predictions = build_candidate_predictions(train, validation)
    support_zero_count = validate_support_zero_parity(predictions)

    train_fields = [
        "base_id",
        "canonical_base_name",
        "season",
        "area_mu",
        "season_total_quantity_kg",
        "yield_kg_per_mu",
        "area_authority_id",
        "area_authority_sha256",
        "quantity_authority_id",
        "quantity_authority_sha256",
        "identity_authority_id",
        "identity_authority_sha256",
        "source_signature",
        "eligibility_signature",
    ]
    train_fields = [field for field in train_fields if any(field in row for row in train)]
    write_csv(replay_dir / "temporal-train-2023-2024-r1.csv", train_fields, train)
    write_csv(
        replay_dir / "temporal-validation-support-ledger-r1.csv",
        [
            "base_id",
            "base_name",
            "has_2023_2024_training_sample",
            "support_count",
            "train_area_mu",
            "train_quantity_kg",
            "train_yield_kg_per_mu",
            "validation_area_mu",
            "support_group",
        ],
        support_ledger,
    )
    write_csv(replay_dir / "temporal-validation-predictions-r1.csv", PREDICTION_FIELDS, predictions)
    prediction_hash = sha256_file(replay_dir / "temporal-validation-predictions-r1.csv")
    candidate_spec = {
        "task_id": TASK_ID,
        "global_candidate": "GLOBAL_POOLED_YIELD",
        "base_candidate": "BASE_SPECIFIC_NO_SHRINKAGE",
        "shrinkage_candidate": "SHRINKAGE_BASE_YIELD",
        "lambda_grid": [decimal_text(lam) for lam in ALLOWED_LAMBDAS],
        "shrinkage_weight": "n/(n+lambda)",
        "global_yield_aggregation": "SUM_2023_2024_QUANTITY_DIVIDED_BY_SUM_2023_2024_AREA",
        "primary_cohort": "SUPPORT_1_ONLY",
        "primary_metric": "POOLED_SEASON_TOTAL_WAPE",
        "all_22_role": "AUXILIARY_ONLY",
        "tie_break": [
            "EXACT_PRIMARY_WAPE",
            "SIMPLER_MODEL",
            "LOWER_ABSOLUTE_SIGNED_BIAS",
            "STRONGER_SHRINKAGE",
        ],
        "validation_actual_accessed": False,
        "forbidden_season": FORBIDDEN_SEASON,
        "stage_b_executed": False,
    }
    write_json(replay_dir / "candidate-specification-r1.json", candidate_spec)
    candidate_spec_hash = sha256_file(replay_dir / "candidate-specification-r1.json")
    freeze_manifest = {
        "task_id": TASK_ID,
        "canonical_training_dataset_sha256": source_hash,
        "prediction_file": "temporal-validation-predictions-r1.csv",
        "predictions_sha256": prediction_hash,
        "candidate_specification_sha256": candidate_spec_hash,
        "predictions_frozen": True,
        "validation_actual_accessed_before_freeze": False,
        "validation_actual_scoring_gate": "AFTER_PREDICTION_FILE_AND_SPEC_HASHED",
        "season_access_allowlist": ["2023-2024", "2024-2025"],
        "2025_2026_accessed": False,
    }
    write_json(replay_dir / "prediction-freeze-manifest-r1.json", freeze_manifest)

    expected_validation_keys = {str(row["base_id"]) for row in validation}
    actual_rows = _read_validation_actuals_after_freeze(
        source_path,
        replay_dir,
        source_hash,
        prediction_hash,
        expected_validation_keys,
    )
    actuals = {row["base_id"]: Decimal(row["actual_total_kg"]) for row in actual_rows}
    validation_fields = [
        "base_id",
        "season",
        "area_mu",
        "actual_total_kg",
        "actual_yield_kg_per_mu",
    ]
    write_csv(replay_dir / "temporal-validation-2024-2025-r1.csv", validation_fields, actual_rows)
    scoring_rows = _build_scoring_rows(predictions, actual_rows)
    scoring_fields = list(scoring_rows[0])
    write_csv(replay_dir / "temporal-validation-scoring-r1.csv", scoring_fields, scoring_rows)
    support1_summary, all22_summary = _build_candidate_summaries(predictions, actuals)
    summary_fields = [
        "candidate",
        "lambda",
        "cohort",
        "row_count",
        "actual_denominator_kg",
        "wape",
        "mae_kg",
        "median_ape",
        "bias_kg",
        "bias_ratio",
    ]
    write_csv(replay_dir / "candidate-support1-summary-r1.csv", summary_fields, support1_summary)
    write_csv(replay_dir / "candidate-all22-summary-r1.csv", summary_fields, all22_summary)
    history_rows = _history_diagnosis_rows(predictions, actual_rows)
    write_csv(
        replay_dir / "base-history-vs-global-diagnosis-r1.csv",
        [
            "base_id",
            "base_name",
            "yield_2023_2024",
            "yield_2024_2025",
            "global_yield_2023_2024",
            "historical_deviation_direction",
            "validation_deviation_direction",
            "direction_persisted",
            "closer_estimate",
            "absolute_history_yield_error",
            "absolute_global_yield_error",
        ],
        history_rows,
    )
    direction_count = sum(row["direction_persisted"] == "true" for row in history_rows)
    history_closer = sum(row["closer_estimate"] == "BASE_HISTORY_CLOSER" for row in history_rows)
    global_closer = sum(row["closer_estimate"] == "GLOBAL_YIELD_CLOSER" for row in history_rows)
    closer_ties = sum(row["closer_estimate"] == "TIE" for row in history_rows)
    write_csv(
        replay_dir / "yield-direction-persistence-r1.csv",
        [
            "base_id",
            "base_name",
            "historical_deviation_direction",
            "validation_deviation_direction",
            "direction_persisted",
        ],
        history_rows,
    )
    correlation = history_diagnostics(predictions, actuals)
    write_json(
        replay_dir / "yield-cross-season-correlation-r1.json",
        {
            "n": correlation["correlation_n"],
            "pearson": correlation["pearson"],
            "spearman": correlation["spearman"],
            "interpretation": "SMALL_SAMPLE_DESCRIPTIVE_ONLY",
        },
    )

    global_support1 = next(
        row for row in support1_summary if row["candidate"] == "GLOBAL_POOLED_YIELD"
    )
    base_support1 = next(
        row for row in support1_summary if row["candidate"] == "BASE_SPECIFIC_NO_SHRINKAGE"
    )
    shrink_summaries = [
        row for row in support1_summary if row["candidate"] == "SHRINKAGE_BASE_YIELD"
    ]
    best_shrinkage = select_candidate(shrink_summaries)
    selected = select_candidate(support1_summary)
    shrink_signal = Decimal(str(best_shrinkage["wape"])) < Decimal(str(global_support1["wape"]))
    base_history_signal = Decimal(str(base_support1["wape"])) < Decimal(
        str(global_support1["wape"])
    )
    best_lambda = str(best_shrinkage["lambda"])
    best_lambda_field = _candidate_field("SHRINKAGE_BASE_YIELD", best_lambda)
    best_win_loss = win_loss_counts(
        predictions, actuals, best_lambda_field, "global_predicted_total"
    )
    base_win_loss = win_loss_counts(
        predictions, actuals, "base_specific_predicted_total", "global_predicted_total"
    )
    global_yield = Decimal(predictions[0]["global_yield"])
    result = (
        "PASS_SHRINKAGE_SIGNAL_IDENTIFIED"
        if shrink_signal
        else "PASS_NO_SHRINKAGE_SIGNAL_IDENTIFIED"
    )
    summary: dict[str, Any] = {
        "task_id": TASK_ID,
        "result": result,
        "base_main_sha": BASE_MAIN_SHA,
        "canonical_training_dataset_sha256": source_hash,
        "canonical_dataset_matches_s8": source_hash == EXPECTED_DATASET_SHA256,
        "cohort_counts": cohort_counts,
        "global_yield_aggregation_policy": GLOBAL_YIELD_POLICY,
        "global_yield_2023_2024_only_kg_per_mu": decimal_text(global_yield),
        "s8_global_yield_reused": False,
        "support0_candidate_prediction_parity": "PASS" if support_zero_count == 11 else "FAIL",
        "support1_primary_candidate_summaries": support1_summary,
        "all22_auxiliary_candidate_summaries": all22_summary,
        "best_shrinkage_lambda": best_lambda,
        "best_shrinkage_support1_wape": best_shrinkage["wape"],
        "shrinkage_signal_identified": shrink_signal,
        "base_history_signal_identified": base_history_signal,
        "selected_model": selected["candidate"],
        "selected_lambda": selected["lambda"]
        if selected["candidate"] == "SHRINKAGE_BASE_YIELD"
        else "NONE",
        "best_shrinkage_vs_global_support1_win_loss": best_win_loss,
        "base_specific_vs_global_support1_win_loss": base_win_loss,
        "history_diagnostics": {
            "history_closer_count": history_closer,
            "global_closer_count": global_closer,
            "tie_count": closer_ties,
            "direction_persistence_count": direction_count,
            "direction_persistence_rate": correlation["direction_persistence_rate"],
            "pearson": correlation["pearson"],
            "spearman": correlation["spearman"],
            "correlation_n": correlation["correlation_n"],
            "note": "SMALL_SAMPLE_DESCRIPTIVE_ONLY",
        },
        "predictions_frozen_before_validation_scoring": True,
        "used_2025_2026": False,
        "model_selection_used_2025_2026": False,
        "hyperparameter_selection_used_2025_2026": False,
        "stage_b_executed": False,
        "daily_prediction_executed": False,
        "peak_metric_executed": False,
        "rolling7_metric_executed": False,
        "model_production_ready": False,
        "validation_role": "TEMPORAL_MODEL_SELECTION_VALIDATION_NOT_INDEPENDENT_TEST",
    }
    write_json(replay_dir / "experiment-summary-r1.json", summary)
    artifact_files = sorted(
        path.name
        for path in replay_dir.iterdir()
        if path.is_file() and path.name != "artifact-manifest.json"
    )
    artifact_manifest = {
        "task_id": TASK_ID,
        "private_artifacts": {name: sha256_file(replay_dir / name) for name in artifact_files},
        "canonical_training_dataset_sha256": source_hash,
        "row_level_data_privacy": "PRIVATE_LOCAL_ONLY",
        "directory_mode_octal": "0700",
        "file_mode_octal": "0600",
    }
    write_json(replay_dir / "artifact-manifest.json", artifact_manifest)
    _verify_private_modes(replay_dir)
    return {
        "summary": summary,
        "artifact_manifest": artifact_manifest,
        "prediction_sha256": prediction_hash,
        "scoring_sha256": sha256_file(replay_dir / "temporal-validation-scoring-r1.csv"),
        "summary_sha256": sha256_file(replay_dir / "experiment-summary-r1.json"),
        "manifest_sha256": sha256_file(replay_dir / "artifact-manifest.json"),
        "files": artifact_files + ["artifact-manifest.json"],
    }


def _verify_private_modes(directory: Path) -> None:
    if stat.S_IMODE(directory.stat().st_mode) != 0o700:
        raise R2BExperimentError("PRIVATE_DIRECTORY_MODE_MISMATCH")
    for path in directory.iterdir():
        if path.is_file() and stat.S_IMODE(path.stat().st_mode) != 0o600:
            raise R2BExperimentError("PRIVATE_FILE_MODE_MISMATCH")


def run_two_replays(source_path: Path, output_root: Path) -> tuple[dict[str, Any], bool]:
    if output_root.exists():
        raise R2BExperimentError("OUTPUT_DIRECTORY_ALREADY_EXISTS_REFUSING_OVERWRITE")
    if not source_path.is_file():
        raise R2BExperimentError("CANONICAL_TRAINING_DATASET_NOT_FOUND")
    source_hash = validate_dataset_hash(source_path.read_bytes())
    output_root.mkdir(mode=0o700, parents=False, exist_ok=False)
    os.chmod(output_root, 0o700)
    first = run_replay(source_path, output_root / "replay-1", source_hash)
    second = run_replay(source_path, output_root / "replay-2", source_hash)
    first_dir = output_root / "replay-1"
    second_dir = output_root / "replay-2"
    same_files = first["files"] == second["files"]
    same_bytes = same_files and all(
        (first_dir / name).read_bytes() == (second_dir / name).read_bytes()
        for name in first["files"]
    )
    if not same_bytes:
        raise R2BExperimentError("BLOCKED_NONDETERMINISTIC_REPLAY")
    return first, same_bytes


def public_evidence(private_result: Mapping[str, Any]) -> dict[str, Any]:
    summary = private_result["summary"]
    support1 = summary["support1_primary_candidate_summaries"]
    all22 = summary["all22_auxiliary_candidate_summaries"]
    diagnostics = summary["history_diagnostics"]
    return {
        "task_id": TASK_ID,
        "result": summary["result"],
        "base_main_sha": BASE_MAIN_SHA,
        "branch_scope": "LOCAL_ONLY_NO_COMMIT_NO_PR",
        "canonical_training_dataset_sha256": summary["canonical_training_dataset_sha256"],
        "canonical_dataset_matches_s8": summary["canonical_dataset_matches_s8"],
        "train_season": "2023-2024",
        "train_row_count": summary["cohort_counts"]["train_count"],
        "validation_season": "2024-2025",
        "validation_row_count": summary["cohort_counts"]["validation_count"],
        "unique_base_count_across_two_seasons": summary["cohort_counts"]["unique_base_count"],
        "support1_validation_base_count": summary["cohort_counts"]["support_1_count"],
        "support0_validation_base_count": summary["cohort_counts"]["support_0_count"],
        "global_yield_aggregation_policy": summary["global_yield_aggregation_policy"],
        "global_yield_2023_2024_only_kg_per_mu": summary["global_yield_2023_2024_only_kg_per_mu"],
        "s8_global_yield_reused": False,
        "primary_validation_cohort": "SUPPORT_1",
        "primary_validation_count": summary["cohort_counts"]["support_1_count"],
        "support1_candidate_metrics": support1,
        "all22_auxiliary_candidate_metrics": all22,
        "best_shrinkage_lambda": summary["best_shrinkage_lambda"],
        "best_shrinkage_support1_wape": summary["best_shrinkage_support1_wape"],
        "shrinkage_signal_identified": summary["shrinkage_signal_identified"],
        "base_history_signal_identified": summary["base_history_signal_identified"],
        "selected_model": summary["selected_model"],
        "selected_lambda": summary["selected_lambda"],
        "best_shrinkage_vs_global_support1_win_loss": summary[
            "best_shrinkage_vs_global_support1_win_loss"
        ],
        "base_specific_vs_global_support1_win_loss": summary[
            "base_specific_vs_global_support1_win_loss"
        ],
        "history_diagnostics": diagnostics,
        "support0_candidate_prediction_parity": summary["support0_candidate_prediction_parity"],
        "predictions_frozen_before_validation_scoring": True,
        "used_2025_2026": False,
        "model_selection_used_2025_2026": False,
        "hyperparameter_selection_used_2025_2026": False,
        "validation_role": summary["validation_role"],
        "stage_b_executed": False,
        "daily_prediction_executed": False,
        "peak_metric_executed": False,
        "rolling7_metric_executed": False,
        "model_production_ready": False,
        "deterministic_replay": "PASS",
        "prediction_freeze_sha256": private_result["prediction_sha256"],
        "scoring_sha256": private_result["scoring_sha256"],
        "experiment_summary_sha256": private_result["summary_sha256"],
        "private_artifact_manifest_sha256": private_result["manifest_sha256"],
        "private_artifact_filenames": private_result["files"],
    }


def _write_public_evidence(repo_root: Path, evidence: Mapping[str, Any]) -> None:
    evidence_path = (
        repo_root / "docs/v0-8/evidence/r2b-temporal-forward-shrinkage-identifiability-r1.json"
    )
    markdown_path = repo_root / "docs/v0-8/r2b/temporal-forward-shrinkage-identifiability-r1.md"
    evidence_path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    markdown_path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    if evidence_path.exists() or markdown_path.exists():
        raise R2BExperimentError("PUBLIC_EVIDENCE_ALREADY_EXISTS_REFUSING_OVERWRITE")
    evidence_bytes = (
        json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode(
            "utf-8"
        )
        + b"\n"
    )
    _write_bytes_exclusive(evidence_path, evidence_bytes, mode=0o644)
    support1 = evidence["support1_candidate_metrics"]
    lines = [
        "# V0.8-R2B Temporal-Forward Shrinkage Identifiability",
        "",
        f"Task: `{TASK_ID}`  ",
        f"Result: `{evidence['result']}`  ",
        "Validation is 2024–25 temporal model-selection validation, not an independent test.",
        "",
        "## Direct result",
        "",
        f"- Train: 2023–24, {evidence['train_row_count']} Base-season rows.",
        f"- Validation: 2024–25, {evidence['validation_row_count']} Base-season rows.",
        f"  Support=1: {evidence['support1_validation_base_count']}; "
        f"support=0: {evidence['support0_validation_base_count']}.",
        "- 2023–24-only area-weighted pooled yield: "
        f"{evidence['global_yield_2023_2024_only_kg_per_mu']} kg/mu.",
        f"- Best shrinkage lambda: {evidence['best_shrinkage_lambda']}.",
        f"  Support=1 WAPE: {evidence['best_shrinkage_support1_wape']}.",
        "- Shrinkage signal: "
        f"`{str(evidence['shrinkage_signal_identified']).lower()}`; "
        "base-history signal: "
        f"`{str(evidence['base_history_signal_identified']).lower()}`.",
        "",
        "## Support=1 primary results",
        "",
        "| Candidate | Lambda | WAPE | MAE (kg) | Median APE | Bias (kg) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in support1:
        lines.append(
            f"| {row['candidate']} | {row['lambda']} | {row['wape']} | "
            f"{row['mae_kg']} | {row['median_ape']} | {row['bias_kg']} |"
        )
    lines.extend(
        [
            "",
            "Support=1 pooled WAPE is the sole selection metric.",
            "All-22 is auxiliary because support=0 predictions are identical.",
            "",
            "## Guardrails and interpretation",
            "",
            "- Predictions were hashed before validation labels were loaded for scoring.",
            "- The canonical input SHA is pinned to S8's 37-row dataset.",
            "  Global yield was recalculated only from the 15 2023–24 rows.",
            "- 2025–26 actuals, predictions, and metrics were not accessed.",
            "  No Stage B, daily, peak, or rolling-7 analysis was run.",
            "- Correlations are descriptive only (n=11); this is not production evidence.",
            "- Row-level artifacts remain private; only aggregate metrics and hashes are recorded.",
            "",
            "Machine evidence is recorded in the R2B evidence JSON.",
        ]
    )
    _write_bytes_exclusive(
        markdown_path,
        ("\n".join(lines) + "\n").encode("utf-8"),
        mode=0o644,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-dataset", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    source_hash = validate_dataset_hash(args.training_dataset.read_bytes())
    result, deterministic = run_two_replays(args.training_dataset, args.output_root)
    if not deterministic:
        raise R2BExperimentError("BLOCKED_NONDETERMINISTIC_REPLAY")
    evidence = public_evidence(result)
    _write_public_evidence(args.repo_root, evidence)
    print(
        json.dumps(
            {
                "result": result["summary"]["result"],
                "dataset_sha256": source_hash,
                **{
                    key: result[key]
                    for key in (
                        "prediction_sha256",
                        "scoring_sha256",
                        "summary_sha256",
                        "manifest_sha256",
                    )
                },
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
