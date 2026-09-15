"""Verify and compare two frozen V0.5-S4 experiment replays."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.audit_v0_5_s3_training_eligibility_r1 import file_hash, read_json, write_json


def _verify_replay(root: Path) -> tuple[dict[str, str], str]:
    manifest_path = root / "artifact-manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"missing artifact manifest: {root}")
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict) or not manifest:
        raise ValueError("S4 artifact manifest must be a non-empty object")
    normalized = {str(name): str(expected) for name, expected in manifest.items()}
    for name, expected in normalized.items():
        path = root / name
        if not path.is_file() or file_hash(path) != expected:
            raise ValueError(f"S4 replay artifact hash mismatch: {name}")
    return normalized, file_hash(manifest_path)


def _assert_boolean_contract(metrics: Any, freeze: Any) -> None:
    if not isinstance(metrics, dict) or not isinstance(freeze, dict):
        raise ValueError("S4 replay metadata must be objects")
    for key in (
        "future_actual_weather_used",
        "validation_labels_used_for_fit",
        "validation_labels_used_for_candidate_selection",
    ):
        if metrics.get(key) is not False:
            raise ValueError(f"S4 replay contract drift: {key}")
    if freeze.get("validation_label_values_used_for_prediction") is not False:
        raise ValueError("S4 prediction freeze contains validation labels")
    if freeze.get("future_actual_weather_used") is not False:
        raise ValueError("S4 prediction freeze contains future weather")


def compare_replays(first: Path, second: Path, output: Path) -> dict[str, Any]:
    first_manifest, first_manifest_hash = _verify_replay(first)
    second_manifest, second_manifest_hash = _verify_replay(second)
    if first_manifest != second_manifest:
        raise ValueError("S4 artifact manifests differ between replays")

    comparable_json = (
        "candidate-manifest.json",
        "input-manifest.json",
        "origin-filter-manifest.json",
        "feature-manifest.json",
        "prediction-freeze.json",
        "training-manifest.json",
        "evaluation-manifest.json",
        "metrics.json",
    )
    for name in comparable_json:
        if read_json(first / name) != read_json(second / name):
            raise ValueError(f"S4 replay JSON differs: {name}")
    metrics = read_json(first / "metrics.json")
    freeze = read_json(first / "prediction-freeze.json")
    _assert_boolean_contract(metrics, freeze)
    result = {
        "task_id": metrics["task_id"],
        "replay_1": str(first),
        "replay_2": str(second),
        "artifact_file_count": len(first_manifest),
        "artifact_manifest_equal": True,
        "artifact_manifest_sha256": first_manifest_hash,
        "second_artifact_manifest_sha256": second_manifest_hash,
        "candidate_manifest_hash": metrics["candidate_manifest_hash"],
        "prediction_file_sha256": metrics["prediction_file_sha256"],
        "scored_prediction_file_sha256": metrics["scored_prediction_file_sha256"],
        "metrics_equal": True,
        "prediction_freeze_equal": True,
        "validation_label_leakage": False,
        "fit_on_validation_season": False,
        "control_prediction_hash_equal": True,
        "weather_prediction_hash_equal": True,
        "deterministic_replay": True,
    }
    write_json(output, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare_replays(args.first, args.second, args.output)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
