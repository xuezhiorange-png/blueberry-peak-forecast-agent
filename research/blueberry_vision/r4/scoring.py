"""Only score owner-qualified references, reusing the original R3 metric engine.

Unqualified images are retained as unscorable rows with nullable GT/error metrics.
Both baselines use exactly the same qualified range, original boxes and config.
"""

from pathlib import Path

from ..r2_common import JSONDict, canonical_hash, file_hash, read_json, seal, verify_seal
from ..r3.evaluation import (
    _coco_metrics,
    compact_metrics,
    match_reference,
    research_ap50,
)
from .freeze import lock_predictions
from .reference import qualify_reference

ROOT = Path(__file__).resolve().parents[1]


def evaluate_qualified(
    dataset: JSONDict,
    package: JSONDict,
    lock: JSONDict,
    predictions: dict[str, JSONDict],
    *,
    references: JSONDict | None = None,
    approvals: dict[str, JSONDict] | None = None,
    evidence_root: Path | None = None,
    run_coco: bool = False,
) -> JSONDict:
    # Verify original predictions/config before inspecting reference geometry.
    original = lock_predictions(
        dataset,
        package,
        read_json(ROOT / "evidence/r3/config_freeze.json"),
        predictions,
        read_json(ROOT / "evidence/r3/model_inference.json"),
    )
    if not verify_seal(lock, "lock_hash") or any(
        lock.get(key) != original[key]
        for key in (
            "package_hash",
            "scope_hash",
            "config_hash",
            "r3_freeze_hash",
            "dataset_manifest_hash",
            "evaluation_protocol_hash",
        )
    ):
        raise ValueError("SCORE_LOCK_NOT_ORIGINAL")
    if references is not None:
        if (
            not verify_seal(references, "annotations_hash")
            or references.get("dataset_manifest_hash") != dataset["manifest_hash"]
            or references.get("SYNTHETIC") is not False
            or references.get("purpose") != dataset["purpose"]
        ):
            raise ValueError("REFERENCE_BUNDLE_BINDING_INVALID")
    snaps = (references or {}).get("snapshots", [])
    snapshots = {row["image_id"]: row for row in snaps}
    records = {row["image_id"]: row for row in dataset["images"]}
    if len(snapshots) != len(snaps) or not set(snapshots) <= set(records):
        raise ValueError("REFERENCE_IMAGE_UNKNOWN_OR_DUPLICATE")
    qualifications = {
        key: qualify_reference(
            image,
            package,
            snapshots.get(key),
            approval=(approvals or {}).get(key),
            evidence_root=evidence_root,
        )
        for key, image in records.items()
    }
    eligible = {key for key, value in qualifications.items() if value["qualified"]}
    models = []
    for model_key in ("A", "B"):
        rows = []
        truths = {}
        candidates = {}
        ignored = {}
        images = {row["image_id"]: row for row in predictions[model_key]["images"]}
        for key, image in sorted(records.items()):
            prediction = images[key]
            reasons = list(qualifications[key]["reason_codes"])
            if prediction["status"] != "ok":
                reasons.append("PREDICTION_FAILED")
            row = {
                "image_id": key,
                "source_asset_hash": image["asset_sha256"],
                "predicted_count": prediction["predicted_visible_fruit_count"],
                "reference_count": None,
                "signed_count_error": None,
                "absolute_count_error": None,
                "status": "NOT_EVALUABLE",
                "reason_codes": reasons,
                "tp": None,
                "fp": None,
                "fn": None,
                "matches": [],
                "false_positive_indices": [],
                "false_negative_indices": [],
                "ignored_prediction_indices": [],
                "scene_metadata": image.get("scene_metadata", {}),
                "reference_hash": qualifications[key]["reference_hash"],
            }
            if not reasons:
                snapshot = snapshots[key]
                gt = [obj for obj in snapshot["objects"] if obj["disposition"] == "TARGET"]
                boxes = prediction["detected_objects"]
                regions = [
                    obj["bbox_xyxy"]
                    for obj in snapshot["objects"]
                    if obj["disposition"] == "IGNORE"
                ]
                match = match_reference(gt, boxes, regions)
                error = len(boxes) - len(gt)
                row.update(
                    status="EVALUATED",
                    reference_count=len(gt),
                    signed_count_error=error,
                    absolute_count_error=abs(error),
                    **match,
                )
                truths[key] = gt
                candidates[key] = boxes
                ignored[key] = set(match["ignored_prediction_indices"])
            rows.append(row)
        metrics = compact_metrics(rows)
        metrics["RESEARCH_AP50"] = research_ap50(truths, candidates, ignored)
        subgroups = {
            dimension: {
                value: compact_metrics(
                    [
                        row
                        for row in rows
                        if (row["scene_metadata"].get(dimension) or "UNKNOWN") == value
                    ]
                )
                for value in sorted(
                    {row["scene_metadata"].get(dimension) or "UNKNOWN" for row in rows}
                )
            }
            for dimension in ("density", "occlusion", "lighting")
        }
        coco = {
            "status": "NOT_RUN",
            "reason_code": "NO_QUALIFIED_REFERENCE_IMAGES" if not truths else "NOT_REQUESTED",
            "COCO_MAP50": None,
            "COCO_MAP50_95": None,
        }
        if run_coco and truths:
            coco = _coco_metrics(records, truths, candidates, snapshots)
        models.append(
            {
                "model_key": model_key,
                "model_hash": predictions[model_key]["selected_model_hash"],
                "prediction_hash": predictions[model_key]["prediction_hash"],
                "metrics": metrics,
                "coco": coco,
                "per_image": rows,
                "subgroup_metrics": subgroups,
                "failure_images": [
                    row["image_id"]
                    for row in rows
                    if row["status"] != "EVALUATED"
                    or row["fp"]
                    or row["fn"]
                    or row["absolute_count_error"]
                ],
            }
        )
    return seal(
        {
            "version": "r4-qualified-reference-evaluation/1.0.0",
            "status": "EVALUATED"
            if len(eligible) == len(records)
            else "PARTIAL_EVALUATED"
            if eligible
            else "NOT_EVALUABLE",
            "scope": "EXPOSED_EXTERNAL_EVALUATION_FULL_FRAMES",
            "SYNTHETIC": False,
            "dataset_manifest_hash": dataset["manifest_hash"],
            "package_hash": package["package_hash"],
            "prediction_lock_hash": lock["lock_hash"],
            "evaluation_protocol_hash": lock["evaluation_protocol_hash"],
            "evaluator_source_hash": file_hash(Path(__file__)),
            "r3_evaluator_hash": file_hash(ROOT / "r3/evaluation.py"),
            "qualified_gt_images": len(eligible),
            "qualified_gt_objects": sum(qualifications[key]["reference_count"] for key in eligible),
            "unscorable_images": len(records) - len(eligible),
            "reference_hash": canonical_hash(
                [qualifications[key]["reference_hash"] for key in sorted(eligible)]
            )
            if eligible
            else None,
            "qualifications": list(qualifications.values()),
            "models": models,
            "limitations": [
                "No real company orchard/generalization approval.",
                "External public labels/results have been exposed; not blind.",
                "Offline owner receipts require genuine external human verification.",
                "Raw count includes ignored predictions; matching ignore policy is separate.",
                "No count to kg calibration.",
            ],
        },
        "report_hash",
    )
