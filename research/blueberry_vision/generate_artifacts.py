"""Deterministic schema and fabricated metadata generation; no image bytes are created."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from research.blueberry_vision.contracts import (
    MANIFEST_SCHEMA_VERSION,
    OBSERVATION_SCHEMA_VERSION,
    VisionManifest,
    VisionObservation,
    canonical_record_hash,
)


def build_synthetic_manifest() -> dict[str, Any]:
    observations: list[dict[str, Any]] = []
    for index, split in enumerate(["train", "validation", "test", "out_of_domain", "unassigned"]):
        day = 1 + index * 2
        missing = split == "unassigned"
        identity: dict[str, Any] = {
            "status": "resolved",
            "base_id": "SYNTHETIC_BASE_A" if index < 2 else f"SYNTHETIC_BASE_{index}",
            "authority_ref": "synthetic-identity-map-v1",
            "unresolved_reason": None,
        }
        if missing:
            identity = {
                "status": "unresolved",
                "base_id": None,
                "authority_ref": None,
                "unresolved_reason": "synthetic-example-awaiting-authoritative-identity",
            }
        descriptor = f"SYNTHETIC metadata descriptor; NO IMAGE BYTES; image-{split}-001"
        record: dict[str, Any] = {
            "schema_version": OBSERVATION_SCHEMA_VERSION,
            "observation_id": f"synthetic-observation-{split}-001",
            "image_id": f"synthetic-image-{split}-001",
            "asset_hash": hashlib.sha256(descriptor.encode("utf-8")).hexdigest(),
            "capture_session_id": f"synthetic-session-{split}",
            "near_duplicate_group_id": f"synthetic-near-duplicate-{split}",
            "observed_at": f"2021-01-{day:02d}T12:00:00Z",
            "asset_available_at": f"2021-01-{day:02d}T12:01:00Z",
            "available_at": f"2021-01-{day:02d}T12:02:00Z",
            "base_identity": identity,
            "season_id": "SYNTHETIC_SEASON_2020_2021",
            "sampling_unit_id": f"SYNTHETIC_UNIT_{split}",
            "variety_id": "SYNTHETIC_VARIETY_A" if index < 3 else None,
            "occlusion": ["none", "partial", "heavy", "unknown", "unknown"][index],
            "device": {
                "device_id": f"synthetic-device-{index % 2}",
                "camera_model": "SYNTHETIC_CAMERA_NOT_REAL",
                "view_angle_degrees": 15.0 if not missing else None,
                "capture_distance_m": 0.5 if not missing else None,
                "lighting": ["diffuse", "shade", "direct_sun", "mixed", "unknown"][index],
                "metadata_ref": "synthetic-camera-metadata-v1",
            },
            "image_dimensions": {"width_px": 640, "height_px": 480},
            "record_kind": "synthetic_observation",
            "SYNTHETIC": True,
            "split": split,
            "task_kind": "detection",
            "annotation_version": None if missing else "synthetic-annotation-v1",
            "label_definition_version": None if missing else "synthetic-candidate-labels-v1",
            "annotation_quality_status": "not_annotated" if missing else "reviewed",
            "annotation_available_at": None if missing else f"2021-01-{day:02d}T12:02:00Z",
            "object_count": None if missing else 2,
            "count_unit": "fruit_count",
            "missing_count_reason": "synthetic-intentionally-not-annotated" if missing else None,
            "class_labels": None if missing else ["SYNTHETIC_candidate_fruit"] * 2,
            "objects": None
            if missing
            else [
                {
                    "object_id": f"synthetic-object-{n}",
                    "class_label": "SYNTHETIC_candidate_fruit",
                    "bbox_xyxy": [20.0 + 100 * n, 30.0, 45.0 + 100 * n, 55.0],
                    "mask_polygon": None,
                }
                for n in range(2)
            ],
            "source_authority": {
                "authority_id": "synthetic-fixture-generator",
                "source_ref": "research/blueberry_vision/generate_artifacts.py",
                "permission_status": "synthetic_only",
                "evidence_ref": "fabricated-metadata-only-no-real-assets",
                "allowed_uses": [
                    "metadata_validation",
                    "train",
                    "validation",
                    "test",
                    "out_of_domain",
                ],
                "granted_at": None,
                "expires_at": None,
            },
            "model_provenance": None,
        }
        record["record_hash"] = canonical_record_hash(record)
        observations.append(record)
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "manifest_id": "SYNTHETIC_BLUEBERRY_VISION_R1_METADATA_ONLY",
        "SYNTHETIC": True,
        "purpose": "offline_synthetic_validation",
        "image_files_present": False,
        "asset_hash_basis": "synthetic_descriptor_sha256",
        "as_of_cutoff": "2021-02-01T00:00:00Z",
        "split_cutoffs": None,
        "label_definitions": [
            {
                "version": "synthetic-candidate-labels-v1",
                "task_kinds": [
                    "detection",
                    "instance_segmentation",
                    "maturity_classification",
                    "yield_proxy",
                ],
                "class_names": ["SYNTHETIC_candidate_fruit"],
                "approval_status": "candidate",
                "source_ref": "fabricated-example-not-a-business-label-standard",
            }
        ],
        "annotation_versions": [
            {
                "version": "synthetic-annotation-v1",
                "label_definition_version": "synthetic-candidate-labels-v1",
                "guideline_ref": "fabricated-example-no-annotated-image-assets",
            }
        ],
        "near_duplicate_review": {
            "status": "completed",
            "method": "synthetic-group-declaration-only",
            "evidence_ref": "generated-distinct-descriptors-no-image-similarity-analysis",
            "completed_at": "2021-01-10T00:00:00Z",
            "scope": "entire_manifest",
            "basis": "synthetic_declared",
        },
        "observations": observations,
    }


def main() -> None:
    root = Path(__file__).resolve().parent
    for model, filename in (
        (VisionObservation, "vision_observation.schema.json"),
        (VisionManifest, "vision_manifest.schema.json"),
    ):
        (root / "schemas" / filename).write_text(
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    (root / "fixtures" / "synthetic_manifest.json").write_text(
        json.dumps(build_synthetic_manifest(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
