"""Verify frozen R2 inputs, adjudicate K5 offline, write new private evidence only."""

import argparse
import json
import socket
from collections import Counter
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np
from threadpoolctl import threadpool_limits

from scripts.climate_authority_r3 import FEATURES, diagnose
from scripts.climate_source_r2 import digest, file_hash, inspect_source, write_json
from scripts.run_climate_study_r2 import csv_file

REGISTRY_HASH = "d942f78e33495739319753c3f4d184fd0d4ee98a23888c8e710cc17e474cd293"
SOURCE_HASH = "ddb4e9beb6a68927de882186cd3cbb7efa6b3238d56fb4f20bb2d36b8655ac70"
R2_HASH = "e71c4279131f810dfb94118f8dabb25584aeee403cfcaff6831c09f4c2091357"
LABELS = [
    "滇中南偏暖偏干型",
    "滇西高海拔凉湿型",
    "滇南低海拔暖湿型",
    "滇东/滇东南高原型",
    "滇中北高原较干高辐射型",
]


def zone_id(zone: int) -> str:
    return f"YN_CLIMATE_ZONE_{zone + 1:02}"


def verify_bundle(root: Path, expected: dict[str, Any]) -> None:
    manifest = json.loads((root / "artifact-manifest.json").read_text())
    if (
        manifest != expected
        or digest({k: v for k, v in manifest.items() if k != "hash"}) != R2_HASH
    ):
        raise ValueError("BLOCKED_R2_AUTHORITY_INPUT_MISMATCH: manifest")
    for name, sha in manifest["file_hashes"].items():
        if file_hash(root / name) != sha:
            raise ValueError("BLOCKED_R2_AUTHORITY_INPUT_MISMATCH: file")


def verify_inputs(source: Path, r2: Path, replay: Path) -> dict[str, Any]:
    expected: dict[str, Any] = json.loads(
        Path("docs/v0-5/s1/climate-zone-evidence.json").read_text()
    )["artifact_manifest"]
    if (
        expected["hash"] != R2_HASH
        or expected["registry_hash"] != REGISTRY_HASH
        or expected["source_hash"] != SOURCE_HASH
    ):
        raise ValueError("BLOCKED_R2_AUTHORITY_INPUT_MISMATCH: identities")
    verify_bundle(r2, expected)
    verify_bundle(replay, expected)
    actual, ds = inspect_source(source)
    ds.close()
    if (
        actual != json.loads((r2 / "climate-source-snapshot-manifest.json").read_text())
        or actual["hash"] != SOURCE_HASH
    ):
        raise ValueError("BLOCKED_R2_AUTHORITY_INPUT_MISMATCH: source")
    profiles = json.loads((r2 / "base-climate-profile-v1.json").read_text())
    for profile in profiles:
        if (
            digest({k: v for k, v in profile.items() if k != "profile_hash"})
            != profile["profile_hash"]
        ):
            raise ValueError("BLOCKED_R2_AUTHORITY_INPUT_MISMATCH: profile")
    return expected


def payload_hash(payload: dict[str, Any]) -> dict[str, Any]:
    return payload | {"hash": digest(payload)}


def run(source: Path, r2: Path, r2_replay: Path, output: Path, config_path: Path) -> dict[str, Any]:
    def no_network(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("NETWORK_FORBIDDEN_R3_OFFLINE")

    with patch.object(socket.socket, "connect", no_network), threadpool_limits(limits=1):
        manifest = verify_inputs(source, r2, r2_replay)
        config = json.loads(config_path.read_text())
        profiles = json.loads((r2 / "base-climate-profile-v1.json").read_text())
        frozen = json.loads((r2 / "candidate-study.json").read_text())
        result = diagnose(profiles, frozen, config)
        output.mkdir(parents=True, exist_ok=False, mode=0o700)
        write_json(output / "adjudication-config.json", config)
        write_json(output / "resampling-runs-r3.json", result["resample_runs"])
        write_json(output / "lofo-runs-r3.json", result["lofo_runs"])
        bases = result["base_results"]
        csv_file(output / "base-zone-confidence-r3.csv", bases)
        for filename, fields in {
            "bootstrap-assignment-frequency-r3.csv": [
                "baseline_zone",
                "bootstrap_same_zone_count",
                "bootstrap_assignment_frequency",
                "aligned_zone_counts",
                "most_common_alternative_zone",
                "alternative_zone_frequency",
                "assignment_entropy_nats",
            ],
            "leave-one-feature-out-r3.csv": [
                "baseline_zone",
                "lofo_stable_count",
                "lofo_stability_rate",
                "features_whose_removal_changes_zone",
            ],
            "method-agreement-r3.csv": [
                "baseline_zone",
                "ward_k5_aligned_zone",
                "method_assignment_agreement",
            ],
            "coordinate-sensitivity-r3.csv": [
                "coordinate_zone_stable",
                "grid_cell_changed_under_perturbation",
                "max_feature_delta_under_coordinate_perturbation",
                "coordinate_crs_status",
            ],
        }.items():
            csv_file(
                output / filename,
                [{k: b[k] for k in ["base_id", "canonical_base_name", *fields]} for b in bases],
            )
        csv_file(output / "temporal-shift-diagnostics-r3.csv", result["temporal_diagnostics"])
        common = {
            "authority_status": "CANDIDATE_ONLY",
            "review_status": "COORDINATOR_REVIEW_REQUIRED",
            "climate_source_snapshot_hash": SOURCE_HASH,
            "base_registry_hash": REGISTRY_HASH,
            "r2_artifact_hash": R2_HASH,
            "method": "KMEANS",
            "K": 5,
            "feature_set_version": "R2_FROZEN_SEVEN_FEATURES_V1",
            "feature_names": list(FEATURES),
            "preprocessing_version": "R2_BASELINE_STANDARD_SCALER_V1",
            "scaler_mean": frozen["scaler_mean"],
            "scaler_scale": frozen["scaler_scale"],
            "adjudication_config_hash": digest(config),
            "climate_zone_profile_authority_frozen": False,
            "climate_zone_mapping_frozen": False,
        }
        zone_profiles = json.loads((r2 / "candidate-zone-profile.json").read_text())
        zones = []
        for z in range(5):
            members = [b for b in bases if b["baseline_zone"] == z]
            centroid = result["centroids"][z]
            silhouettes = [b["sample_silhouette"] for b in members]
            zones.append(
                {
                    "zone_id": zone_id(z),
                    "r2_candidate_zone": f"Z{z + 1}",
                    "descriptive_label": LABELS[z],
                    "climate_distribution_label": zone_profiles[z]["descriptive_label"],
                    "base_count": len(members),
                    "member_base_ids": [b["base_id"] for b in members],
                    "member_canonical_names": [b["canonical_base_name"] for b in members],
                    "baseline_climate_summary": zone_profiles[z]["climate"],
                    "centroid_standardized": centroid,
                    "centroid_hash": digest(centroid),
                    "class_counts": {
                        c: sum(b["assignment_class"] == c for b in members)
                        for c in ("CORE", "BOUNDARY", "UNSTABLE")
                    },
                    "silhouette": {
                        "min": min(silhouettes),
                        "median": float(np.median(silhouettes)),
                        "max": max(silhouettes),
                        "negative_silhouette_count": sum(s < 0 for s in silhouettes),
                    },
                    "review_status": "CANDIDATE_ONLY",
                }
            )
        profile_payload = payload_hash(
            common | {"schema": "CLIMATE_ZONE_PROFILE_V1_CANDIDATE", "zones": zones}
        )
        mapping_payload = payload_hash(
            common
            | {
                "schema": "BASE_CLIMATE_ZONE_MAPPING_V1_CANDIDATE",
                "mappings": [
                    b
                    | {
                        "zone_id": zone_id(b["baseline_zone"]),
                        "runner_up_zone_id": zone_id(b["runner_up_zone"]),
                        "authority_status": "CANDIDATE_ONLY",
                    }
                    for b in bases
                ],
            }
        )
        write_json(output / "climate-zone-profile-v1-candidate.json", profile_payload)
        write_json(output / "base-climate-zone-mapping-v1-candidate.json", mapping_payload)
        counts = Counter(b["assignment_class"] for b in bases)
        coordinate = sum(b["coordinate_zone_stable"] for b in bases)
        eligible = (
            counts["UNSTABLE"] == 0
            and coordinate == 38
            and min(z["base_count"] for z in zones) >= 3
        )
        recommendation = (
            "DO_NOT_FREEZE_MAPPING"
            if not eligible
            else "FREEZE_K5_ALL_CORE"
            if counts["CORE"] == 38
            else "FREEZE_K5_WITH_BOUNDARY_FLAGS"
        )
        summary = common | {
            "task_id": config["task_id"],
            "result": "AUTHORITY_ADJUDICATION_COMPLETED",
            "authority_recommendation": recommendation,
            "authority_freeze_eligible": eligible,
            "reference_base_count": 38,
            "out_of_yunnan_base_count": 1,
            "resample_count": 200,
            "lofo_feature_count": 7,
            "core_base_count": counts["CORE"],
            "boundary_base_count": counts["BOUNDARY"],
            "unstable_base_count": counts["UNSTABLE"],
            "zone_class_counts": {z["zone_id"]: z["class_counts"] for z in zones},
            "min_bootstrap_assignment_frequency": min(
                b["bootstrap_assignment_frequency"] for b in bases
            ),
            "median_bootstrap_assignment_frequency": float(
                np.median([b["bootstrap_assignment_frequency"] for b in bases])
            ),
            "min_lofo_stability_rate": min(b["lofo_stability_rate"] for b in bases),
            "median_lofo_stability_rate": float(
                np.median([b["lofo_stability_rate"] for b in bases])
            ),
            "negative_silhouette_base_count": sum(b["sample_silhouette"] < 0 for b in bases),
            "nonpositive_silhouette_bases": [
                b["canonical_base_name"] for b in bases if b["sample_silhouette"] <= 0
            ],
            "method_disagreement_base_count": sum(
                not b["method_assignment_agreement"] for b in bases
            ),
            "temporal_stable_base_count": sum(
                b["temporal_zone_stability"] == "STABLE" for b in bases
            ),
            "recent_shift_bases": [
                b for b in bases if b["temporal_zone_stability"] == "RECENT_SHIFT"
            ],
            "coordinate_zone_stable_count": coordinate,
            "grid_cell_switch_base_count": sum(
                b["grid_cell_changed_under_perturbation"] for b in bases
            ),
            "climate_zone_profile_v1_candidate_hash": profile_payload["hash"],
            "base_climate_zone_mapping_v1_candidate_hash": mapping_payload["hash"],
            "r2_input_hashes_verified": True,
            "r2_complete_offline_replay": "PASS",
            "r2_k5_mapping_exact_reproduction": "PASS",
            "yield_features_used": False,
            "harvest_features_used": False,
            "productive_area_used": False,
            "authority_activation_performed": False,
            "interpretation": (
                "RESAMPLING_ASSIGNMENT_STABILITY, not a confidence interval. "
                "Margin/silhouette/method diagnostics are not additional tuned gates."
            ),
        }
        write_json(output / "summary.json", summary)
        artifact = {
            "task_id": config["task_id"],
            "r2_artifact_hash": R2_HASH,
            "r2_dependencies": manifest["dependencies"],
            "file_hashes": {p.name: file_hash(p) for p in sorted(output.iterdir()) if p.is_file()},
        }
        write_json(output / "artifact-manifest.json", payload_hash(artifact))
        print(
            json.dumps(
                {
                    "recommendation": recommendation,
                    "counts": dict(counts),
                    "artifact_hash": digest(artifact),
                },
                ensure_ascii=False,
            )
        )
        return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "r2", "r2-replay", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--config", type=Path, default=Path("configs/climate_zone_r3.json"))
    args = parser.parse_args()
    run(args.source, args.r2, args.r2_replay, args.output, args.config)


if __name__ == "__main__":
    main()
