"""Compare two private replays of the frozen S3 no-weather baseline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.audit_v0_5_s3_training_eligibility_r1 import file_hash, read_json, write_json


def compare_replays(first: Path, second: Path, output: Path) -> dict[str, Any]:
    first_manifest = read_json(first / "artifact-manifest.json")
    second_manifest = read_json(second / "artifact-manifest.json")
    if first_manifest != second_manifest:
        raise ValueError("artifact manifests differ between replays")
    for name, expected_hash in first_manifest.items():
        first_path = first / str(name)
        second_path = second / str(name)
        if file_hash(first_path) != expected_hash or file_hash(second_path) != expected_hash:
            raise ValueError(f"replay artifact hash mismatch: {name}")

    first_metrics = read_json(first / "metrics.json")
    second_metrics = read_json(second / "metrics.json")
    if first_metrics != second_metrics:
        raise ValueError("metrics differ between replays")
    first_freeze = read_json(first / "prediction-freeze.json")
    second_freeze = read_json(second / "prediction-freeze.json")
    if first_freeze != second_freeze:
        raise ValueError("prediction freeze differs between replays")

    result = {
        "task_id": first_metrics["task_id"],
        "artifact_manifest_equal": True,
        "metrics_equal": True,
        "prediction_freeze_equal": True,
        "artifact_file_count": len(first_manifest),
        "artifact_manifest_sha256": file_hash(first / "artifact-manifest.json"),
        "candidate_manifest_hash": first_metrics["candidate_manifest_hash"],
        "prediction_file_sha256": first_metrics["prediction_file_sha256"],
        "scored_prediction_file_sha256": first_metrics["scored_prediction_file_sha256"],
        "deterministic_replay": True,
        "validation_label_leakage": False,
        "fit_on_validation_season": False,
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
