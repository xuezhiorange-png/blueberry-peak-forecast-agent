"""Independent synthetic-only box/count evaluator; this is not COCO mAP."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from research.blueberry_vision.r2_common import (
    CLASS_LABEL,
    JSONDict,
    canonical_hash,
    dataset_split_hash,
    file_hash,
    seal,
    verify_seal,
)

EVALUATOR_VERSION = "blueberry-vision-box-count-evaluator/2.0.0"
AP_NAME = "bbox_ap50_research_all_points"
STRATA: dict[str, tuple[Any, ...]] = {
    "density": ("sparse", "dense", "pressure"),
    "occlusion": ("none", "partial", "high"),
    "lighting": ("normal", "shadow", "glare"),
    "size": ("small", "large", "mixed"),
    "domain": ("regular", "ood"),
    "empty": (True, False),
}


def default_evaluation_config() -> JSONDict:
    """Operating-point IoU is independent of fixed AP50 curve integration."""
    return {
        "schema_version": "blueberry-vision-evaluator-config/2.0.0",
        "iou_threshold": 0.5,
        "ap_iou_threshold": 0.5,
        "ap_method": "VOC_ALL_POINTS_PRECISION_ENVELOPE",
        "max_detections": None,
        "ignore_rule": "UNMATCHED_PREDICTION_INTERSECTION_OVER_PREDICTION_AREA_GE_THRESHOLD",
        "ignore_overlap_threshold": 0.5,
        "count_policy": "RAW_OUTPUT_BOX_COUNT_INCLUDING_IGNORED_PREDICTIONS",
        "count_unit": "visible_fruit_per_image",
    }


def _number(value: object, reason: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(reason)
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(reason)
    return number


def _bbox(coords: object) -> list[float]:
    if not isinstance(coords, list) or len(coords) != 4:
        raise ValueError("BBOX_FOUR_COORDINATES_REQUIRED")
    box = [_number(value, "BBOX_NONFINITE_OR_NONNUMERIC") for value in coords]
    if box[0] < 0 or box[1] < 0 or box[2] <= box[0] or box[3] <= box[1]:
        raise ValueError("BBOX_INVALID_HALF_OPEN_GEOMETRY")
    return box


def _intersection(a: list[float], b: list[float]) -> float:
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def _area(a: list[float]) -> float:
    return (a[2] - a[0]) * (a[3] - a[1])


def bbox_iou(a: list[float], b: list[float]) -> float:
    """Continuous half-open XYXY; edge-touching boxes have zero intersection."""
    first, second = _bbox(a), _bbox(b)
    overlap = _intersection(first, second)
    union = _area(first) + _area(second) - overlap
    if not math.isfinite(overlap) or not math.isfinite(union):
        raise ValueError("BBOX_ARITHMETIC_OVERFLOW")
    return overlap / union


def _score(prediction: JSONDict) -> float:
    score = _number(prediction.get("score"), "PREDICTION_SCORE_INVALID")
    if not 0 <= score <= 1:
        raise ValueError("PREDICTION_SCORE_INVALID")
    return score


def _validate_boxes(boxes: list[JSONDict], *, predictions: bool) -> None:
    for box in boxes:
        if not isinstance(box, dict):
            raise ValueError("BOX_OBJECT_REQUIRED")
        _bbox(box.get("bbox_xyxy"))
        if not isinstance(box.get("class_label"), str) or not box["class_label"]:
            raise ValueError("CLASS_LABEL_REQUIRED")
        if predictions:
            _score(box)


def _ignored(box: JSONDict, regions: list[list[float]], threshold: float) -> bool:
    coords = _bbox(box["bbox_xyxy"])
    return any(_intersection(coords, region) / _area(coords) >= threshold for region in regions)


def _match(
    gt: list[JSONDict],
    pred: list[JSONDict],
    iou_threshold: float,
    regions: list[list[float]],
    ignore_threshold: float,
) -> JSONDict:
    available = set(range(len(gt)))
    matches: list[JSONDict] = []
    false_positives: list[int] = []
    ignored_indices: list[int] = []
    # Python's sort is stable: equal-score predictions retain their input order.
    ranked = sorted(range(len(pred)), key=lambda index: -_score(pred[index]))
    for prediction_index in ranked:
        prediction = pred[prediction_index]
        candidates = [
            (bbox_iou(gt[index]["bbox_xyxy"], prediction["bbox_xyxy"]), index)
            for index in sorted(available)
            if gt[index]["class_label"] == prediction["class_label"]
        ]
        best_iou, best_index = max(
            candidates, key=lambda item: (item[0], -item[1]), default=(0, -1)
        )
        if best_index >= 0 and best_iou >= iou_threshold:
            available.remove(best_index)
            matches.append(
                {"gt_index": best_index, "prediction_index": prediction_index, "iou": best_iou}
            )
        elif _ignored(prediction, regions, ignore_threshold):
            ignored_indices.append(prediction_index)
        else:
            false_positives.append(prediction_index)
    return {
        "tp": len(matches),
        "fp": len(false_positives),
        "fn": len(available),
        "matches": matches,
        "false_positive_indices": false_positives,
        "false_negative_indices": sorted(available),
        "ignored_prediction_indices": ignored_indices,
    }


def match_boxes(
    gt: list[JSONDict],
    pred: list[JSONDict],
    iou_threshold: float = 0.5,
    ignore_regions: list[list[float]] | None = None,
) -> JSONDict:
    """Same-image/same-class greedy confidence-ordered one-to-one matching."""
    threshold = _number(iou_threshold, "IOU_THRESHOLD_INVALID")
    if not 0 < threshold <= 1:
        raise ValueError("IOU_THRESHOLD_INVALID")
    _validate_boxes(gt, predictions=False)
    _validate_boxes(pred, predictions=True)
    scope = {box["image_id"] for box in [*gt, *pred] if "image_id" in box}
    if len(scope) > 1:
        raise ValueError("IMAGE_SCOPE_MISMATCH")
    regions = [_bbox(region) for region in (ignore_regions or [])]
    return _match(gt, pred, threshold, regions, 0.5)


def _average_precision(
    rows: list[JSONDict], references: dict[str, JSONDict], predictions: dict[str, JSONDict]
) -> JSONDict:
    """Re-match globally confidence-ranked outputs independently for every class."""
    evaluated = [row for row in rows if row["status"] == "EVALUATED"]
    classes = {CLASS_LABEL}
    for row in evaluated:
        image_id = row["image_id"]
        classes.update(box["class_label"] for box in references[image_id]["objects"])
        classes.update(box["class_label"] for box in predictions[image_id]["detected_objects"])
    per_class: JSONDict = {}
    supported_ap: list[float] = []
    for label in sorted(classes):
        truths: dict[str, list[JSONDict]] = {}
        ranked: list[tuple[float, int, int, str, JSONDict]] = []
        for image_index, row in enumerate(evaluated):
            image_id = row["image_id"]
            truths[image_id] = [
                box for box in references[image_id]["objects"] if box["class_label"] == label
            ]
            for pred_index, box in enumerate(predictions[image_id]["detected_objects"]):
                if box["class_label"] == label:
                    ranked.append((-_score(box), image_index, pred_index, image_id, box))
        support = sum(len(boxes) for boxes in truths.values())
        if support == 0:
            per_class[label] = {
                "gt_support": 0,
                "ap": None,
                "reason_code": "NO_GT_CLASS_SUPPORT",
                "curve": [],
            }
            continue
        available = {image_id: set(range(len(boxes))) for image_id, boxes in truths.items()}
        cumulative_tp = cumulative_fp = 0
        curve: list[JSONDict] = []
        for negative_score, _, pred_index, image_id, box in sorted(ranked, key=lambda x: x[:3]):
            candidates = [
                (bbox_iou(truths[image_id][index]["bbox_xyxy"], box["bbox_xyxy"]), index)
                for index in sorted(available[image_id])
            ]
            best_iou, best_index = max(
                candidates, key=lambda item: (item[0], -item[1]), default=(0, -1)
            )
            if best_index >= 0 and best_iou >= 0.5:
                available[image_id].remove(best_index)
                cumulative_tp += 1
            elif pred_index in next(
                row["ap_ignored_prediction_indices"]
                for row in evaluated
                if row["image_id"] == image_id
            ):
                continue
            else:
                cumulative_fp += 1
            curve.append(
                {
                    "image_id": image_id,
                    "prediction_index": pred_index,
                    "score": -negative_score,
                    "tp_cumulative": cumulative_tp,
                    "fp_cumulative": cumulative_fp,
                    "precision": cumulative_tp / (cumulative_tp + cumulative_fp),
                    "recall": cumulative_tp / support,
                }
            )
        recalls = [0.0, *(point["recall"] for point in curve), 1.0]
        envelope = [0.0, *(point["precision"] for point in curve), 0.0]
        for index in range(len(envelope) - 2, -1, -1):
            envelope[index] = max(envelope[index], envelope[index + 1])
        ap = sum(
            (recalls[index] - recalls[index - 1]) * envelope[index]
            for index in range(1, len(recalls))
            if recalls[index] != recalls[index - 1]
        )
        supported_ap.append(ap)
        per_class[label] = {"gt_support": support, "ap": ap, "reason_code": None, "curve": curve}
    return {
        AP_NAME: sum(supported_ap) / len(supported_ap) if supported_ap else None,
        "ap_per_class": per_class,
        "ap_supported_classes": [
            label for label, entry in per_class.items() if entry["ap"] is not None
        ],
        "ap_unsupported_classes": [
            label for label, entry in per_class.items() if entry["ap"] is None
        ],
    }


def _metrics(
    rows: list[JSONDict], references: dict[str, JSONDict], predictions: dict[str, JSONDict]
) -> JSONDict:
    evaluated = [row for row in rows if row["status"] == "EVALUATED"]
    count = len(evaluated)
    tp = sum(row["tp"] for row in evaluated)
    fp = sum(row["fp"] for row in evaluated)
    fn = sum(row["fn"] for row in evaluated)
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
    return {
        "status": "EVALUATED" if count else "NOT_EVALUABLE",
        "reason_code": None if count else "NO_EVALUABLE_IMAGES",
        "image_count": len(rows),
        "evaluated_count": count,
        "excluded_count": len(rows) - count,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision_reason_code": None if precision is not None else "NO_NONIGNORED_PREDICTIONS",
        "recall_reason_code": None if recall is not None else "NO_EVALUABLE_GT_OBJECTS",
        "count_mae": sum(row["absolute_count_error"] for row in evaluated) / count
        if count
        else None,
        "count_bias": sum(row["signed_count_error"] for row in evaluated) / count
        if count
        else None,
        "total_overcount": sum(max(row["signed_count_error"], 0) for row in evaluated)
        if count
        else None,
        "total_undercount": sum(max(-row["signed_count_error"], 0) for row in evaluated)
        if count
        else None,
        "empty_false_positive_count": sum(
            row["pred_count"] for row in evaluated if row["gt_count"] == 0
        )
        if count
        else None,
        "count_unit": "visible_fruit_per_image",
        **_average_precision(rows, references, predictions),
    }


def _config(config: JSONDict | None) -> JSONDict:
    result = dict(default_evaluation_config() if config is None else config)
    if set(result) != set(default_evaluation_config()):
        raise ValueError("EVALUATOR_CONFIG_KEYS_INVALID")
    defaults = default_evaluation_config()
    for key in defaults:
        if (
            key not in {"iou_threshold", "ignore_overlap_threshold"}
            and result[key] != defaults[key]
        ):
            raise ValueError("EVALUATOR_CONFIG_UNSUPPORTED")
    for key in ("iou_threshold", "ignore_overlap_threshold"):
        value = _number(result[key], "EVALUATOR_THRESHOLD_INVALID")
        if not 0 < value <= 1:
            raise ValueError("EVALUATOR_THRESHOLD_INVALID")
    return result


def _hash(value: object, reason: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise ValueError(reason)
    return value


def _index(records: object, reason: str) -> dict[str, JSONDict]:
    if not isinstance(records, list):
        raise ValueError(reason)
    result: dict[str, JSONDict] = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError(reason)
        image_id = record.get("image_id")
        if not isinstance(image_id, str) or not image_id or image_id in result:
            raise ValueError("IMAGE_ID_MISSING_OR_DUPLICATE")
        result[image_id] = record
    return result


def _in_bounds(boxes: list[JSONDict], width: int, height: int) -> None:
    for box in boxes:
        coords = _bbox(box["bbox_xyxy"])
        if coords[2] > width or coords[3] > height:
            raise ValueError("BBOX_OUTSIDE_IMAGE")


def _validate_reference(record: JSONDict) -> None:
    if record.get("SYNTHETIC") is not True:
        raise ValueError("SYNTHETIC_REFERENCE_REQUIRED")
    authority = record.get("source_authority")
    if (
        not isinstance(authority, dict)
        or authority.get("permission_status") != "synthetic_only"
        or not isinstance(authority.get("allowed_uses"), list)
        or record.get("split") not in authority["allowed_uses"]
        or not isinstance(authority.get("authority_id"), str)
        or not authority["authority_id"]
        or not isinstance(authority.get("source_ref"), str)
        or not authority["source_ref"]
    ):
        raise ValueError("REFERENCE_SOURCE_AUTHORITY_REQUIRED")
    width, height = record.get("image_width"), record.get("image_height")
    if (
        isinstance(width, bool)
        or not isinstance(width, int)
        or width < 1
        or isinstance(height, bool)
        or not isinstance(height, int)
        or height < 1
    ):
        raise ValueError("IMAGE_DIMENSIONS_INVALID")
    _hash(record.get("asset_sha256"), "ASSET_HASH_INVALID")
    if record.get("gt_status") == "missing":
        if record.get("visible_count") is not None or record.get("objects") not in (None, []):
            raise ValueError("MISSING_GT_CANNOT_BECOME_ZERO_OR_OBJECTS")
    elif record.get("gt_status") == "complete":
        if record.get("annotation_quality_status") != "synthetic_reference":
            raise ValueError("SYNTHETIC_REFERENCE_PROVENANCE_REQUIRED")
        boxes = record.get("objects")
        if not isinstance(boxes, list):
            raise ValueError("REFERENCE_OBJECTS_REQUIRED")
        _validate_boxes(boxes, predictions=False)
        _in_bounds(boxes, width, height)
        _validate_box_scope(boxes, record["image_id"])
        count = record.get("visible_count")
        if isinstance(count, bool) or not isinstance(count, int) or count != len(boxes):
            raise ValueError("REFERENCE_COUNT_BOX_MISMATCH")
        ids = [box.get("object_id") for box in boxes]
        if any(not isinstance(value, str) or not value for value in ids) or len(set(ids)) != len(
            ids
        ):
            raise ValueError("REFERENCE_OBJECT_ID_MISSING_OR_DUPLICATE")
    else:
        raise ValueError("GT_STATUS_INVALID")
    regions = record.get("ignore_regions", [])
    if not isinstance(regions, list):
        raise ValueError("IGNORE_REGIONS_LIST_REQUIRED")
    for region in regions:
        _in_bounds([{"bbox_xyxy": _bbox(region)}], width, height)
    metadata = record.get("scene_metadata")
    if not isinstance(metadata, dict):
        raise ValueError("SCENE_METADATA_REQUIRED")
    for dimension in (*STRATA, "scene_type"):
        if dimension not in metadata:
            continue
        value = metadata[dimension]
        if dimension == "empty":
            valid = isinstance(value, bool)
        else:
            valid = isinstance(value, str) and bool(value)
        if not valid:
            raise ValueError("SCENE_METADATA_DIMENSION_INVALID")


def _validate_box_scope(boxes: list[JSONDict], image_id: str) -> None:
    for box in boxes:
        if "image_id" in box and box["image_id"] != image_id:
            raise ValueError("BOX_IMAGE_SCOPE_MISMATCH")


def _validate_prediction(prediction: JSONDict, record: JSONDict) -> None:
    if not verify_seal(prediction, "prediction_hash"):
        raise ValueError("PER_IMAGE_PREDICTION_HASH_MISMATCH")
    if prediction.get("source_asset_hash") != record["asset_sha256"]:
        raise ValueError("PREDICTION_ASSET_BINDING_MISMATCH")
    if prediction.get("status") == "failed":
        if (
            prediction.get("predicted_visible_fruit_count") is not None
            or prediction.get("detected_objects") is not None
        ):
            raise ValueError("FAILED_PREDICTION_CANNOT_BECOME_ZERO")
        if not isinstance(prediction.get("reason_code"), str) or not prediction["reason_code"]:
            raise ValueError("FAILED_PREDICTION_REASON_REQUIRED")
    elif prediction.get("status") == "ok":
        boxes = prediction.get("detected_objects")
        if not isinstance(boxes, list):
            raise ValueError("PREDICTED_OBJECTS_REQUIRED")
        _validate_boxes(boxes, predictions=True)
        _in_bounds(boxes, record["image_width"], record["image_height"])
        _validate_box_scope(boxes, record["image_id"])
        count = prediction.get("predicted_visible_fruit_count")
        if isinstance(count, bool) or not isinstance(count, int) or count != len(boxes):
            raise ValueError("PREDICTION_COUNT_BOX_MISMATCH")
    else:
        raise ValueError("PREDICTION_STATUS_INVALID")


def evaluate_predictions(
    manifest: JSONDict,
    predictions: JSONDict,
    splits: list[str] | None = None,
    config: JSONDict | None = None,
) -> JSONDict:
    """Evaluate sealed synthetic artifacts; missing or failed inputs retain coverage."""
    settings = _config(config)
    if manifest.get("SYNTHETIC") is not True or predictions.get("SYNTHETIC") is not True:
        raise ValueError("SYNTHETIC_ONLY_EVALUATOR")
    if not verify_seal(manifest, "manifest_hash"):
        raise ValueError("DATASET_MANIFEST_HASH_MISMATCH")
    if not verify_seal(predictions, "prediction_hash"):
        raise ValueError("PREDICTION_BUNDLE_HASH_MISMATCH")
    if predictions.get("schema_version") != "blueberry-vision-predictions/2.0.0":
        raise ValueError("PREDICTION_SCHEMA_UNSUPPORTED")
    references = _index(manifest.get("images"), "MANIFEST_IMAGES_REQUIRED")
    predicted = _index(predictions.get("images"), "PREDICTION_IMAGES_REQUIRED")
    if set(predicted) - set(references):
        raise ValueError("PREDICTION_IMAGE_OUTSIDE_MANIFEST")
    split_hash = dataset_split_hash(list(references.values()))
    if manifest.get("split_hash") != split_hash or predictions.get("split_hash") != split_hash:
        raise ValueError("SPLIT_HASH_MISMATCH")
    if predictions.get("dataset_manifest_hash") != manifest["manifest_hash"]:
        raise ValueError("PREDICTION_DATASET_BINDING_MISMATCH")
    if "prediction_scope_hash" in predictions:
        declared_scope = dataset_split_hash([references[key] for key in sorted(predicted)])
        if predictions["prediction_scope_hash"] != declared_scope:
            raise ValueError("PREDICTION_SCOPE_HASH_MISMATCH")
    for key in ("model_hash", "config_hash"):
        _hash(predictions.get(key), f"{key.upper()}_INVALID")
    chosen = ["test", "out_of_domain"] if splits is None else list(splits)
    if (
        not chosen
        or len(set(chosen)) != len(chosen)
        or any(split not in {"train", "validation", "test", "out_of_domain"} for split in chosen)
    ):
        raise ValueError("EVALUATION_SPLITS_INVALID")
    rows: list[JSONDict] = []
    for image_id, record in sorted(references.items()):
        _validate_reference(record)
        if image_id in predicted:
            _validate_prediction(predicted[image_id], record)
        if record.get("split") not in chosen:
            continue
        prediction = predicted.get(image_id)
        row: JSONDict = {
            "image_id": image_id,
            "split": record["split"],
            "source_asset_hash": record["asset_sha256"],
            "reference_hash": canonical_hash(
                {
                    key: record.get(key)
                    for key in ("gt_status", "objects", "visible_count", "ignore_regions")
                }
            ),
            "prediction_hash": prediction["prediction_hash"] if prediction else None,
            "inference_status": prediction["status"] if prediction else "missing",
            "inference_reason_code": prediction.get("reason_code") if prediction else None,
            "scene_metadata": record["scene_metadata"],
            "gt_count": record.get("visible_count"),
            "pred_count": prediction.get("predicted_visible_fruit_count") if prediction else None,
            "signed_count_error": None,
            "absolute_count_error": None,
            "tp": None,
            "fp": None,
            "fn": None,
            "matches": [],
            "ignored_prediction_indices": [],
            "ap_ignored_prediction_indices": [],
        }
        if record["gt_status"] == "missing":
            row.update(status="MISSING_GT", reason_code="REFERENCE_ANNOTATION_MISSING")
        elif prediction is None:
            row.update(status="MISSING_PREDICTION", reason_code="PREDICTION_RECORD_MISSING")
        elif prediction["status"] == "failed":
            row.update(status="FAILED_INFERENCE", reason_code=prediction["reason_code"])
        else:
            regions = [_bbox(region) for region in record.get("ignore_regions", [])]
            matches = _match(
                record["objects"],
                prediction["detected_objects"],
                settings["iou_threshold"],
                regions,
                settings["ignore_overlap_threshold"],
            )
            ap_matches = _match(
                record["objects"],
                prediction["detected_objects"],
                0.5,
                regions,
                settings["ignore_overlap_threshold"],
            )
            signed = row["pred_count"] - row["gt_count"]
            row.update(
                status="EVALUATED",
                reason_code=None,
                signed_count_error=signed,
                absolute_count_error=abs(signed),
                **matches,
                ap_ignored_prediction_indices=ap_matches["ignored_prediction_indices"],
            )
        rows.append(row)
    subgroup_metrics: JSONDict = {}
    for dimension, expected in {**STRATA, "scene_type": ()}.items():
        values = set(expected) | {row["scene_metadata"].get(dimension, "unknown") for row in rows}
        subgroup_metrics[dimension] = {}
        for value in sorted(values, key=str):
            key = str(value).lower() if isinstance(value, bool) else str(value)
            subgroup_metrics[dimension][key] = _metrics(
                [row for row in rows if row["scene_metadata"].get(dimension, "unknown") == value],
                references,
                predicted,
            )
    evaluated_count = sum(row["status"] == "EVALUATED" for row in rows)
    return seal(
        {
            "schema_version": "blueberry-vision-evaluation/2.0.0",
            "SYNTHETIC": True,
            "evaluation_scope": "SYNTHETIC_ONLY",
            "dataset_manifest_hash": manifest["manifest_hash"],
            "split_hash": split_hash,
            "evaluation_splits": sorted(chosen),
            "scope_hash": canonical_hash([row["image_id"] for row in rows]),
            "model_name": predictions.get("model_name"),
            "model_hash": predictions["model_hash"],
            "config_hash": predictions["config_hash"],
            "evaluator_version": EVALUATOR_VERSION,
            "evaluator_hash": file_hash(Path(__file__)),
            "evaluator_config": settings,
            "evaluator_config_hash": canonical_hash(settings),
            "prediction_hash": predictions["prediction_hash"],
            "evaluated_count": evaluated_count,
            "excluded_count": len(rows) - evaluated_count,
            "missing_count": sum(
                row["status"] in {"MISSING_GT", "MISSING_PREDICTION"} for row in rows
            ),
            "failed_count": sum(row["inference_status"] == "failed" for row in rows),
            "metrics": _metrics(rows, references, predicted),
            "subgroup_metrics": subgroup_metrics,
            "per_image_results": rows,
            "failure_cases": [
                row
                for row in rows
                if row["status"] != "EVALUATED"
                or row["fp"]
                or row["fn"]
                or row["absolute_count_error"]
            ],
            "limitations": [
                "SYNTHETIC DEMONSTRATION — NOT REAL BLUEBERRY ACCURACY",
                "Research AP50 uses VOC all-points precision envelope; not COCO mAP.",
                "No maxDets truncation; all outputs, including >100-object scenes, are evaluated.",
                "Ignored unmatched predictions do not count as detection FP "
                "but remain raw count errors.",
                "No confidence intervals or independent real-world generalization claim.",
                "Visible fruit count is not kg or a business maturity grade.",
                "Hash binding verifies artifact integrity, "
                "not upstream pixel inference or source authority.",
            ],
        },
        "report_hash",
    )


def compare_reports(baseline: JSONDict, candidate: JSONDict) -> JSONDict:
    """Paired errors on identical references; report every coverage difference."""
    if not verify_seal(baseline, "report_hash") or not verify_seal(candidate, "report_hash"):
        raise ValueError("COMPARISON_REPORT_HASH_MISMATCH")
    for key in ("dataset_manifest_hash", "split_hash", "scope_hash", "evaluator_config_hash"):
        if baseline.get(key) != candidate.get(key):
            raise ValueError("COMPARISON_SCOPE_OR_EVALUATOR_MISMATCH")
    first = _index(baseline.get("per_image_results"), "COMPARISON_ROWS_REQUIRED")
    second = _index(candidate.get("per_image_results"), "COMPARISON_ROWS_REQUIRED")
    if set(first) != set(second) or any(
        first[key]["reference_hash"] != second[key]["reference_hash"] for key in first
    ):
        raise ValueError("COMPARISON_REFERENCE_ROWSET_MISMATCH")
    paired: list[JSONDict] = []
    first_missing: list[str] = []
    second_missing: list[str] = []
    for image_id in sorted(first):
        a, b = first[image_id], second[image_id]
        if a["status"] == b["status"] == "EVALUATED":
            paired.append(
                {
                    "image_id": image_id,
                    "baseline_absolute_error": a["absolute_count_error"],
                    "candidate_absolute_error": b["absolute_count_error"],
                    "absolute_error_delta_candidate_minus_baseline": b["absolute_count_error"]
                    - a["absolute_count_error"],
                    "signed_error_delta_candidate_minus_baseline": b["signed_count_error"]
                    - a["signed_count_error"],
                }
            )
        elif a["status"] == "EVALUATED":
            second_missing.append(image_id)
        elif b["status"] == "EVALUATED":
            first_missing.append(image_id)
    count = len(paired)
    return seal(
        {
            "schema_version": "blueberry-vision-comparison/2.0.0",
            "SYNTHETIC": True,
            "dataset_manifest_hash": baseline["dataset_manifest_hash"],
            "split_hash": baseline["split_hash"],
            "scope_hash": baseline["scope_hash"],
            "baseline_report_hash": baseline["report_hash"],
            "candidate_report_hash": candidate["report_hash"],
            "status": "EVALUATED" if count else "NOT_EVALUABLE",
            "common_evaluated_count": count,
            "paired_count_mae_delta_candidate_minus_baseline": sum(
                row["absolute_error_delta_candidate_minus_baseline"] for row in paired
            )
            / count
            if count
            else None,
            "paired_count_bias_delta_candidate_minus_baseline": sum(
                row["signed_error_delta_candidate_minus_baseline"] for row in paired
            )
            / count
            if count
            else None,
            "baseline_available_candidate_missing": second_missing,
            "candidate_available_baseline_missing": first_missing,
            "paired_results": paired,
            "count_unit": "visible_fruit_per_image",
            "limitations": [
                "Synthetic paired engineering comparison only; no production superiority claim."
            ],
        },
        "comparison_hash",
    )
