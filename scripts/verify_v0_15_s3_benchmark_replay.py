"""Compare immutable completed S3 runs without refitting or changing scores."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from backend.app.area_yield.v015_base10_benchmark import CANDIDATES
from backend.app.area_yield.v015_benchmark_custody import load, save, sha, validate_public
from backend.app.area_yield.v015_research_cohort import digest


def replay_report(first: Path, second: Path) -> dict[str, Any]:
    selection = load(first / "selection.json")["selected"]
    if selection != load(second / "selection.json")["selected"]:
        raise ValueError("SELECTED_CONFIG_REPLAY_FAILED")
    if load(first / "contract.json") != load(second / "contract.json"):
        raise ValueError("CONTRACT_REPLAY_FAILED")
    names = [f"validation-{candidate}-predictions.json" for candidate in CANDIDATES]
    names += [f"oot-{candidate}-predictions.json" for candidate in selection.values()]
    names += ["validation-metrics.json", "oot-metrics.json"]
    hashes = {}
    for name in names:
        original, replayed = (first / name).read_bytes(), (second / name).read_bytes()
        if original != replayed:
            raise ValueError("PREDICTION_OR_METRIC_BYTE_REPLAY_FAILED")
        hashes[name] = sha(original)
    custody = []
    for root in (first, second):
        a = load(root / "phase-a-custody.json")
        b = load(root / "phase-b-custody.json")
        final = load(root / "final-custody.json")
        oot = load(root / "oot-custody.json")
        if (
            a["label_reads"] != ["TRAIN"]
            or b["label_reads"] != ["VALIDATION"]
            or final["label_reads"] != ["TRAIN", "VALIDATION"]
            or oot["label_reads"] != ["EXPOSED_OOT"]
            or a["validation_labels_read"] is not False
            or a["oot_labels_read"] is not False
            or final["oot_labels_read"] is not False
        ):
            raise ValueError("LABEL_CUSTODY_REPLAY_FAILED")
        custody.append(
            {
                "validation_seal_hash": b["verified_seal_hash"],
                "oot_seal_hash": oot["verified_seal_hash"],
                "phase_label_reads": [
                    a["label_reads"],
                    b["label_reads"],
                    final["label_reads"],
                    oot["label_reads"],
                ],
            }
        )
    return {
        "result": "PASS",
        "independent_complete_process_runs": 2,
        "same_selected_configs": True,
        "same_canonical_prediction_bytes": True,
        "same_canonical_metric_bytes": True,
        "RIDGE_REPLAY": "PASS",
        "CATBOOST_REPLAY": "PASS",
        "LIGHTGBM_REPLAY": "PASS",
        "artifact_hashes": hashes,
        "custody": custody,
        "binary_hash_determinism_required": False,
        "timestamps_excluded_from_numeric_replay": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--public-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = replay_report(args.first, args.second)
    members = []
    for path in sorted(args.public_source.glob("*.json")):
        if path.name == "manifest.json":
            continue
        value = load(path)
        validate_public(value)
        save(args.output / path.name, value)
        raw = (args.output / path.name).read_bytes()
        members.append({"name": path.name, "sha256": sha(raw), "size": len(raw)})
    validate_public(report)
    save(args.output / "deterministic-replay-report.json", report)
    raw = (args.output / "deterministic-replay-report.json").read_bytes()
    members.append(
        {"name": "deterministic-replay-report.json", "sha256": sha(raw), "size": len(raw)}
    )
    manifest = {
        "schema": "V0_15_S3_BENCHMARK_MANIFEST_V1",
        "members": sorted(members, key=lambda m: m["name"]),
        "dataset_manifest_hash": load(args.first / "contract.json")["dataset_manifest_hash"],
        "source_public_manifest_hash": load(args.public_source / "manifest.json")["manifest_hash"],
    }
    manifest["manifest_hash"] = digest(manifest)
    save(args.output / "manifest.json", manifest)
    print("DETERMINISTIC_REPLAY=PASS")


if __name__ == "__main__":
    main()
