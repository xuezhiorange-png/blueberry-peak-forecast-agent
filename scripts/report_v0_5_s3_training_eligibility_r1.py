"""Verify S3 eligibility artifacts and compare two deterministic audit replays."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.audit_v0_5_s3_training_eligibility_r1 import file_hash


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_artifact(root: Path) -> dict[str, str]:
    manifest = read_json(root / "artifact-manifest.json")
    if not isinstance(manifest, dict):
        raise ValueError("artifact manifest must be an object")
    for name, expected in manifest.items():
        path = root / str(name)
        if not path.is_file() or file_hash(path) != expected:
            raise ValueError(f"artifact hash mismatch: {name}")
    return {str(name): str(value) for name, value in manifest.items()}


def compare(first: Path, second: Path) -> dict[str, Any]:
    first_manifest = verify_artifact(first)
    second_manifest = verify_artifact(second)
    if first_manifest != second_manifest:
        raise ValueError("replay artifact manifests differ")
    first_summary = read_json(first / "summary.json")
    second_summary = read_json(second / "summary.json")
    if first_summary != second_summary:
        raise ValueError("replay summaries differ")
    return {
        "replay_1": str(first),
        "replay_2": str(second),
        "artifact_file_count": len(first_manifest),
        "artifact_manifest_equal": True,
        "summary_equal": True,
        "deterministic_replay": True,
        "artifact_manifest_hash": file_hash(first / "artifact-manifest.json"),
        "summary_hash": file_hash(first / "summary.json"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare(args.first, args.second)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    args.output.chmod(0o600)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
