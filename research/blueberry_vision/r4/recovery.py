"""Recover exact original R3 predictions without re-committing thousands of boxes.

R3's durable HTML contains box/id/score fields. R4 adds only missing component
area scalars. Restored canonical AND serialized file hashes must equal the
previously published R3 receipts. This is recovery, never new pixel inference.
"""

import json
import re
from pathlib import Path

from ..r2_common import JSONDict, canonical_hash, file_hash, read_json, seal, verify_seal
from ..r3.evaluation import validate_freeze

ROOT = Path(__file__).resolve().parents[1]


def recover_predictions(root: Path = ROOT) -> dict[str, JSONDict]:
    evidence = root / "evidence/r3"
    dataset = read_json(evidence / "pilot_dataset_manifest.json")
    freeze = read_json(evidence / "config_freeze.json")
    validate_freeze(freeze)
    receipts = read_json(evidence / "model_inference.json")
    supplement = read_json(root / "evidence/r4/prediction_recovery_supplement.json")
    html_path = root / "examples/r3/real_review.html"
    if not verify_seal(supplement, "supplement_hash") or supplement["r3_html_sha256"] != file_hash(
        html_path
    ):
        raise ValueError("R3_RECOVERY_SOURCE_HASH_MISMATCH")
    match = re.search(
        r'<script id="report-data" type="application/json">(.*?)</script>',
        html_path.read_text(),
        re.DOTALL,
    )
    if match is None:
        raise ValueError("R3_PERSISTED_BOXES_MISSING")
    payload = json.loads(match.group(1))
    rows = {row["image_id"]: row for row in payload["images"]}
    result = {}
    for index, receipt in enumerate(receipts["model_runs"]):
        key = receipt["model_key"]
        areas = next(
            row["component_areas"] for row in supplement["models"] if row["model_key"] == key
        )
        metadata = {row["image_id"]: row for row in receipt["images"]}
        restored = []
        for image in dataset["images"]:
            image_id = image["image_id"]
            boxes = rows[image_id]["models"][index]["detected_objects"]
            if len(boxes) != len(areas[image_id]):
                raise ValueError("R3_RECOVERY_OBJECT_COUNT_MISMATCH")
            objects = [
                {
                    **obj,
                    "component_pixel_area": area,
                    "bbox_normalized": [
                        obj["bbox_xyxy"][i] / image["image_width" if i % 2 == 0 else "image_height"]
                        for i in range(4)
                    ],
                    "original_detector_class_label": "SYNTHETIC_BLUEBERRY_VISIBLE",
                    "label_approval": "CANDIDATE_RESEARCH_ADAPTATION_NOT_BUSINESS_APPROVED",
                }
                for obj, area in zip(boxes, areas[image_id], strict=True)
            ]
            restored.append(
                seal(
                    {
                        "image_id": image_id,
                        "source_asset_hash": image["asset_sha256"],
                        "source_id": image["source_id"],
                        "purpose": dataset["purpose"],
                        "SYNTHETIC": False,
                        "status": metadata[image_id]["status"],
                        "reason_code": metadata[image_id]["reason_code"],
                        "detected_objects": objects,
                        "predicted_visible_fruit_count": len(objects),
                        "preprocessing": metadata[image_id]["preprocessing"],
                    },
                    "prediction_hash",
                )
            )
        prediction = seal(
            {
                "schema_version": "blueberry-vision-r3-predictions/3.0.0",
                "purpose": dataset["purpose"],
                "SYNTHETIC": False,
                "dataset_manifest_hash": dataset["manifest_hash"],
                "freeze_hash": freeze["freeze_hash"],
                "model_key": key,
                "model_name": freeze["models"][key]["model_name"],
                "model_hash": freeze["model_hash"],
                "selected_model_hash": freeze["models"][key]["model_hash"],
                "config_hash": freeze["config_hash"],
                "training_data_hash": freeze["training_data_hash"],
                "prediction_scope_hash": canonical_hash(
                    sorted(row["image_id"] for row in restored)
                ),
                "images": restored,
                "count_unit": "visible_fruit_per_image",
                "gt_consumed": False,
            },
            "prediction_hash",
        )
        if prediction["prediction_hash"] != receipt["prediction_hash"]:
            raise ValueError("ORIGINAL_R3_PREDICTION_HASH_NOT_RECOVERED")
        result[key] = prediction
    return result
