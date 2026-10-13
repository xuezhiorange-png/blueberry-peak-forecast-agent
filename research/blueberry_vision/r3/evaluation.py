"""Frozen R2 pixel inference and source-separated R3 box/count evaluation.

The image adapter is separate from R2's synthetic data contract. Neither pixel
detector receives annotations, and unknown reference counts stay unknown. The
research seal is an integrity log, not independent custody or authentication.
"""

from __future__ import annotations

import contextlib
import importlib
import io
import math
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from ..classical import CLASSICAL_VERSION, detect_rgb
from ..evaluator import bbox_iou, match_boxes
from ..r2_common import (
    JSONDict,
    canonical_hash,
    file_hash,
    read_json,
    seal,
    verify_seal,
    write_json_new,
)
from ..trainable import MODEL_VERSION, detect_trained_rgb, load_model

CANDIDATE_LABEL = "CANDIDATE_VISIBLE_BLUEBERRY"
EVALUATOR_VERSION = "blueberry-vision-external-box-count/3.0.0"
R2_ROOT = Path(__file__).resolve().parents[1]
R2_EVIDENCE = R2_ROOT / "evidence/r2"
PURPOSES = {"PUBLIC_EXTERNAL_BENCHMARK", "AUTHORIZED_ORCHARD_PILOT", "SYNTHETIC_ENGINEERING"}


def default_adapter_config() -> JSONDict:
    """Pre-registered CPU input bound, without inference-driven resize selection."""
    return {
        "version": "rgb-external-resize/3.0.0",
        "maximum_edge": 1280,
        "resampling": "PILLOW_LANCZOS",
        "upscale": False,
        "bbox_frame": "ORIGINAL_EXIF_NORMALIZED_RGB_HALF_OPEN_XYXY",
        "class_mapping": {"SYNTHETIC_BLUEBERRY_VISIBLE": CANDIDATE_LABEL},
        "label_approval": "CANDIDATE_RESEARCH_ADAPTATION_NOT_BUSINESS_APPROVED",
    }


def evaluation_protocol() -> JSONDict:
    return {
        "version": EVALUATOR_VERSION,
        "iou_threshold": 0.5,
        "RESEARCH_AP50": "VOC_ALL_POINTS_PRECISION_ENVELOPE_NO_MAXDETS_CAP",
        "count_policy": "RAW_OUTPUT_BOX_COUNT_INCLUDING_IGNORED_PREDICTIONS",
        "ignore_overlap_threshold": 0.5,
        "count_unit": "visible_fruit_per_image",
        "missing_gt": "NOT_EVALUABLE_NULL_NEVER_ZERO",
        "public_gt_exposure": "EXPOSED_PUBLIC_BENCHMARK",
        "coco_evaluator": "OPTIONAL_PYCOCOTOOLS_2.0.11_MAXDETS_1_10_100",
    }


def _r2_configs() -> JSONDict:
    result = {}
    for key, name in (("A", "classical_config.json"), ("B", "trained_inference_config.json")):
        wrapper = read_json(R2_EVIDENCE / name)
        if wrapper.get("config_hash") != canonical_hash(wrapper.get("config")):
            raise ValueError("R2_CONFIG_ARTIFACT_HASH_MISMATCH")
        result[key] = wrapper["config"]
    return result


def freeze_r2_baselines(
    output_path: Path | None = None,
    *,
    adapter_config: JSONDict | None = None,
) -> JSONDict:
    """Freeze existing artifacts and adapter before any real test scoring.

    No fitting, threshold tuning, annotation reads, timestamps, hostnames, or
    output paths enter this immutable identity. The original model is not copied
    into a new production registry, and its synthetic training scope is retained.
    """
    adapter = default_adapter_config() if adapter_config is None else adapter_config
    if adapter != default_adapter_config():
        raise ValueError("ADAPTER_CONFIG_NOT_PREREGISTERED")
    configs = _r2_configs()
    original_freeze = read_json(R2_EVIDENCE / "algorithm_config.json")
    for key, name in (("A", "classical"), ("B", "inference")):
        if configs[key] != original_freeze[name]:
            raise ValueError("R2_BASELINE_CONFIG_CHANGED")
    original_hashes = original_freeze["source_code_sha256"]
    for name in ("classical.py", "trainable.py", "evaluator.py"):
        if file_hash(R2_ROOT / name) != original_hashes[name]:
            raise ValueError("R2_BASELINE_SOURCE_CHANGED")
    model = load_model(R2_EVIDENCE / "model.json")
    model_manifest = read_json(R2_EVIDENCE / "model_manifest.json")
    if (
        not verify_seal(model_manifest, "model_manifest_hash")
        or model_manifest["model_hash"] != model["model_hash"]
        or model_manifest["model_artifact_sha256"] != file_hash(R2_EVIDENCE / "model.json")
        or model["training_config"]["iterations"] != 80
    ):
        raise ValueError("R2_MODEL_PROVENANCE_MISMATCH")
    models = {
        "A": {
            "model_name": "RGB_threshold_and_4_connected_components_v2",
            "model_version": CLASSICAL_VERSION,
            "model_hash": canonical_hash(
                {"detector_version": CLASSICAL_VERSION, "config": configs["A"]}
            ),
            "training_scope": "NO_TRAINING_DETERMINISTIC_R2_FROZEN_CONFIG",
        },
        "B": {
            "model_name": "CPU_NumPy_logistic_pixel_classifier_v2",
            "model_version": MODEL_VERSION,
            "model_hash": model["model_hash"],
            "model_artifact_sha256": model_manifest["model_artifact_sha256"],
            "training_scope": "R2_SYNTHETIC_TRAIN_ONLY_NO_R3_REFIT",
            "training_data_hash": model_manifest["training_data_hash"],
            "training_dataset_manifest_hash": read_json(R2_EVIDENCE / "dataset_manifest.json")[
                "manifest_hash"
            ],
        },
    }
    protocol = evaluation_protocol()
    result = seal(
        {
            "schema_version": "blueberry-vision-r3-baseline-freeze/3.0.0",
            "models": models,
            "model_hash": canonical_hash(models),
            "frozen_configs": configs,
            "adapter_config": adapter,
            "config_hash": canonical_hash({"configs": configs, "adapter": adapter}),
            "training_data_hash": model_manifest["training_data_hash"],
            "training_image_ids": model_manifest["train_image_ids"],
            "training_dataset_manifest_hash": read_json(R2_EVIDENCE / "dataset_manifest.json")[
                "manifest_hash"
            ],
            "dependencies": {"Pillow": version("Pillow"), "numpy": version("numpy")},
            "evaluation_protocol": protocol,
            "evaluation_protocol_hash": canonical_hash(protocol),
            "source_code_sha256": {
                **original_hashes,
                "r3/evaluation.py": file_hash(Path(__file__)),
                **{
                    f"r3/{name}": file_hash(R2_ROOT / "r3" / name)
                    for name in ("ingestion.py", "contracts.py", "annotations.py", "splits.py")
                },
            },
            "selection_policy": "R2_ARTIFACTS_UNCHANGED_ADAPTER_PREREGISTERED_NO_REAL_GT_SELECTION",
            "independent_access_control": False,
        },
        "freeze_hash",
    )
    if output_path is not None:
        write_json_new(output_path, result)
    return result


def validate_freeze(freeze: JSONDict) -> None:
    if not verify_seal(freeze, "freeze_hash"):
        raise ValueError("FREEZE_HASH_MISMATCH")
    if freeze.get("frozen_configs") != _r2_configs():
        raise ValueError("R2_BASELINE_CONFIG_CHANGED")
    if freeze.get("adapter_config") != default_adapter_config():
        raise ValueError("ADAPTER_CONFIG_NOT_PREREGISTERED")
    if freeze != freeze_r2_baselines():
        raise ValueError("FROZEN_SOURCE_OR_MODEL_CHANGED")


def resize_for_inference(
    rgb: NDArray[np.uint8],
    adapter_config: JSONDict,
) -> tuple[NDArray[np.uint8], JSONDict]:
    if adapter_config != default_adapter_config():
        raise ValueError("ADAPTER_CONFIG_NOT_PREREGISTERED")
    if rgb.ndim != 3 or rgb.dtype != np.uint8 or rgb.shape[2] != 3 or not rgb.size:
        raise ValueError("RGB_UINT8_HWC_REQUIRED")
    height, width = rgb.shape[:2]
    ratio = min(1.0, adapter_config["maximum_edge"] / max(width, height))
    resized_width = max(1, round(width * ratio))
    resized_height = max(1, round(height * ratio))
    resized = resized_width != width or resized_height != height
    output = (
        np.asarray(
            Image.fromarray(rgb).resize((resized_width, resized_height), Image.Resampling.LANCZOS),
            dtype=np.uint8,
        ).copy()
        if resized
        else rgb.copy()
    )
    metadata = {
        "version": adapter_config["version"],
        "resized": resized,
        "input_width": width,
        "input_height": height,
        "inference_width": resized_width,
        "inference_height": resized_height,
        "scale_x_to_original": width / resized_width,
        "scale_y_to_original": height / resized_height,
        "resampling": adapter_config["resampling"],
        "adapter_hash": canonical_hash(adapter_config),
    }
    return output, metadata


def run_real_inference(
    dataset: JSONDict,
    data_root: Path,
    freeze: JSONDict,
    *,
    model_key: str = "A",
    image_ids: list[str] | None = None,
    output_path: Path | None = None,
    ledger_dir: Path | None = None,
) -> JSONDict:
    """Asset-only R3 inference: no annotations, counts, seed, or GT parameter.

    The strict R3 asset contract forbids GT fields. Pure R2 pixel functions are
    called directly, preserving real/synthetic provenance instead of feeding a
    fake synthetic manifest into R2's synthetic-only evaluator.
    """
    from .contracts import validate_manifest
    from .ingestion import secure_load_asset, verify_coordinate_metadata

    validate_manifest(dataset)
    validate_freeze(freeze)
    if model_key not in {"A", "B"}:
        raise ValueError("MODEL_KEY_UNKNOWN")
    records = dataset["images"]
    scope = {image["image_id"] for image in records}
    if image_ids is not None:
        if len(set(image_ids)) != len(image_ids) or not set(image_ids) <= scope:
            raise ValueError("INFERENCE_IMAGE_SCOPE_INVALID")
        records = [image for image in records if image["image_id"] in image_ids]
    model = load_model(R2_EVIDENCE / "model.json") if model_key == "B" else None
    config = freeze["frozen_configs"][model_key]
    predictions: list[JSONDict] = []
    for image in records:
        row: JSONDict = {
            "image_id": image["image_id"],
            "source_asset_hash": image["asset_sha256"],
            "source_id": image["source_id"],
            "purpose": dataset["purpose"],
            "SYNTHETIC": dataset["SYNTHETIC"],
            "status": "failed",
            "reason_code": None,
            "detected_objects": None,
            "predicted_visible_fruit_count": None,
            "preprocessing": None,
        }
        try:
            loaded = secure_load_asset(
                data_root,
                image["asset_ref"],
                expected_hash=image["asset_sha256"],
                expected_size=(image["image_width"], image["image_height"]),
            )
            verify_coordinate_metadata(image, loaded)
            if loaded.metadata["preprocessing_hash"] != image["preprocessing_hash"]:
                raise ValueError("PREPROCESSING_HASH_MISMATCH")
            pixels, preprocessing = resize_for_inference(loaded.rgb, freeze["adapter_config"])
            objects = (
                detect_rgb(pixels, config)
                if model_key == "A"
                else detect_trained_rgb(pixels, model if model is not None else {}, config)
            )
            mapped: list[JSONDict] = []
            for candidate in objects:
                if candidate["class_label"] != "SYNTHETIC_BLUEBERRY_VISIBLE":
                    raise ValueError("R2_CANDIDATE_LABEL_UNEXPECTED")
                x1, y1, x2, y2 = candidate["bbox_xyxy"]
                original = [
                    x1 * preprocessing["scale_x_to_original"],
                    y1 * preprocessing["scale_y_to_original"],
                    x2 * preprocessing["scale_x_to_original"],
                    y2 * preprocessing["scale_y_to_original"],
                ]
                mapped.append(
                    {
                        **candidate,
                        "class_label": CANDIDATE_LABEL,
                        "original_detector_class_label": candidate["class_label"],
                        "label_approval": "CANDIDATE_RESEARCH_ADAPTATION_NOT_BUSINESS_APPROVED",
                        "bbox_xyxy": original,
                        "bbox_normalized": [
                            original[0] / image["image_width"],
                            original[1] / image["image_height"],
                            original[2] / image["image_width"],
                            original[3] / image["image_height"],
                        ],
                    }
                )
            row.update(
                status="ok",
                detected_objects=mapped,
                predicted_visible_fruit_count=len(mapped),
                preprocessing=preprocessing,
            )
        except (OSError, ValueError) as exc:
            row["reason_code"] = (
                str(exc).split(":", 1)[0] if isinstance(exc, ValueError) else "ASSET_IO_ERROR"
            )
        predictions.append(seal(row, "prediction_hash"))
    result = seal(
        {
            "schema_version": "blueberry-vision-r3-predictions/3.0.0",
            "purpose": dataset["purpose"],
            "SYNTHETIC": dataset["SYNTHETIC"],
            "dataset_manifest_hash": dataset["manifest_hash"],
            "freeze_hash": freeze["freeze_hash"],
            "model_key": model_key,
            "model_name": freeze["models"][model_key]["model_name"],
            "model_hash": freeze["model_hash"],
            "selected_model_hash": freeze["models"][model_key]["model_hash"],
            "config_hash": freeze["config_hash"],
            "training_data_hash": freeze["training_data_hash"],
            "prediction_scope_hash": canonical_hash(sorted(image["image_id"] for image in records)),
            "images": predictions,
            "count_unit": "visible_fruit_per_image",
            "gt_consumed": False,
        },
        "prediction_hash",
    )
    if output_path is not None:
        write_json_new(output_path, result)
    if ledger_dir is not None:
        if output_path is None:
            raise ValueError("PREDICTION_ARTIFACT_REQUIRED_FOR_LEDGER")
        from .splits import append_exposure_event

        append_exposure_event(
            ledger_dir,
            "PREDICTIONS_FIXED",
            {
                "freeze_hash": freeze["freeze_hash"],
                "prediction_hash": result["prediction_hash"],
                "artifact_sha256": file_hash(output_path),
            },
        )
    return result


def match_reference(
    targets: list[JSONDict],
    predictions: list[JSONDict],
    ignore_regions: list[list[float]] | None = None,
) -> JSONDict:
    """Reuse R2's independently tested same-class one-to-one matcher."""
    return match_boxes(targets, predictions, 0.5, ignore_regions)


def research_ap50(
    truths: dict[str, list[JSONDict]],
    predictions: dict[str, list[JSONDict]],
    ignored: dict[str, set[int]] | None = None,
) -> float | None:
    """One-class VOC all-points envelope. Deliberately not official COCO mAP."""
    if set(truths) != set(predictions):
        raise ValueError("AP_SCOPE_MISMATCH")
    support = sum(len(boxes) for boxes in truths.values())
    if not support:
        return None
    unused = {image_id: set(range(len(boxes))) for image_id, boxes in truths.items()}
    ranked = sorted(
        [
            (-float(box["score"]), image_id, index, box)
            for image_id in sorted(predictions)
            for index, box in enumerate(predictions[image_id])
        ],
        key=lambda row: row[:3],
    )
    tp = fp = 0
    points: list[tuple[float, float]] = []
    for _, image_id, index, prediction in ranked:
        if ignored and index in ignored.get(image_id, set()):
            continue
        candidates = [
            (bbox_iou(truths[image_id][gt_index]["bbox_xyxy"], prediction["bbox_xyxy"]), gt_index)
            for gt_index in sorted(unused[image_id])
            if truths[image_id][gt_index]["class_label"] == prediction["class_label"]
        ]
        overlap, matched = max(candidates, key=lambda row: (row[0], -row[1]), default=(0, -1))
        if matched >= 0 and overlap >= 0.5:
            unused[image_id].remove(matched)
            tp += 1
        else:
            fp += 1
        points.append((tp / support, tp / (tp + fp)))
    recalls = [0.0, *(point[0] for point in points), 1.0]
    precision = [0.0, *(point[1] for point in points), 0.0]
    for index in range(len(precision) - 2, -1, -1):
        precision[index] = max(precision[index], precision[index + 1])
    return sum(
        (recalls[index] - recalls[index - 1]) * precision[index] for index in range(1, len(recalls))
    )


def compact_metrics(rows: list[JSONDict]) -> JSONDict:
    evaluated = [row for row in rows if row["status"] == "EVALUATED"]
    count = len(evaluated)
    tp = sum(row["tp"] for row in evaluated)
    fp = sum(row["fp"] for row in evaluated)
    fn = sum(row["fn"] for row in evaluated)
    missing = sum("GT_MISSING" in row.get("reason_codes", []) for row in rows)
    failed = sum("PREDICTION_FAILED" in row.get("reason_codes", []) for row in rows)
    return {
        "status": "EVALUATED" if count else "NOT_EVALUABLE",
        "reason_code": None if count else "NO_QUALIFIED_REFERENCE_IMAGES",
        "evaluated_count": count,
        "excluded_count": len(rows) - count,
        "missing_count": missing,
        "missing_prediction_count": sum(
            "PREDICTION_MISSING" in row.get("reason_codes", []) for row in rows
        ),
        "failed_count": failed,
        "tp": tp if count else None,
        "fp": fp if count else None,
        "fn": fn if count else None,
        "precision": tp / (tp + fp) if count and tp + fp else None,
        "recall": tp / (tp + fn) if count and tp + fn else None,
        "f1": 2 * tp / (2 * tp + fp + fn) if count and 2 * tp + fp + fn else None,
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
        "empty_image_false_positives": sum(
            row["predicted_count"] for row in evaluated if row["reference_count"] == 0
        )
        if count
        else None,
        "count_unit": "visible_fruit_per_image",
    }


def _snapshot_index(annotations: JSONDict | None) -> dict[str, JSONDict]:
    if annotations is None:
        return {}
    if not verify_seal(annotations, "annotations_hash"):
        raise ValueError("ANNOTATIONS_HASH_MISMATCH")
    snapshots = annotations.get("snapshots")
    if not isinstance(snapshots, list):
        raise ValueError("ANNOTATION_SNAPSHOTS_REQUIRED")
    result = {}
    from .annotations import validate_snapshot

    for snapshot in snapshots:
        if not isinstance(snapshot, dict) or not verify_seal(snapshot, "snapshot_hash"):
            raise ValueError("ANNOTATION_SNAPSHOT_HASH_MISMATCH")
        if snapshot.get("image_id") in result:
            raise ValueError("MULTIPLE_REFERENCE_VERSIONS_FOR_IMAGE")
        validate_snapshot(snapshot)
        result[snapshot["image_id"]] = snapshot
    return result


def _geometry(objects: list[JSONDict], image: JSONDict, *, predictions: bool) -> None:
    seen: set[str] = set()
    for box in objects:
        if not isinstance(box, dict):
            raise ValueError("OBJECT_RECORD_REQUIRED")
        object_id = box.get("object_id")
        if not isinstance(object_id, str) or object_id in seen:
            raise ValueError("OBJECT_ID_INVALID_OR_DUPLICATE")
        seen.add(object_id)
        coords = box.get("bbox_xyxy")
        if not isinstance(coords, list) or len(coords) != 4:
            raise ValueError("BBOX_FOUR_COORDINATES_REQUIRED")
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in coords):
            raise ValueError("BBOX_NONFINITE_OR_NONNUMERIC")
        if (
            not 0 <= coords[0] < coords[2] <= image["image_width"]
            or not 0 <= coords[1] < coords[3] <= image["image_height"]
        ):
            raise ValueError("BBOX_IMAGE_BOUNDARY")
        if (predictions or box.get("disposition") == "TARGET") and box.get(
            "class_label"
        ) != CANDIDATE_LABEL:
            raise ValueError("CANDIDATE_LABEL_MISMATCH")
        if predictions:
            score = box.get("score")
            if (
                isinstance(score, bool)
                or not isinstance(score, (int, float))
                or not math.isfinite(score)
                or not 0 <= score <= 1
            ):
                raise ValueError("PREDICTION_SCORE_INVALID")


def evaluate_real(
    dataset: JSONDict,
    predictions: JSONDict,
    annotations: JSONDict | None,
    split: JSONDict | None = None,
    test_seal: JSONDict | None = None,
    *,
    freeze: JSONDict | None = None,
    ledger: Path | JSONDict | None = None,
    run_coco: bool = False,
) -> JSONDict:
    """Score only qualified reference snapshots after frozen predictions.

    Missing labels produce a complete coverage report with null accuracy. Source
    domains cannot aggregate because dataset/prediction/snapshot identities must
    match. Caller can provide an ordered immutable ledger directory; scoring read
    is logged after prior CONFIG_FROZEN/PREDICTIONS_FIXED, never before inference.
    """
    from .contracts import validate_manifest
    from .splits import build_split, check_admission

    validate_manifest(dataset)
    if not verify_seal(predictions, "prediction_hash"):
        raise ValueError("PREDICTION_HASH_MISMATCH")
    if (
        predictions.get("dataset_manifest_hash") != dataset["manifest_hash"]
        or predictions.get("purpose") != dataset["purpose"]
        or predictions.get("SYNTHETIC") is not dataset["SYNTHETIC"]
    ):
        raise ValueError("PREDICTION_DATASET_OR_PURPOSE_MISMATCH")
    if predictions.get("gt_consumed") is not False:
        raise ValueError("GT_CONSUMPTION_NOT_EXCLUDED")
    frozen = freeze_r2_baselines() if freeze is None else freeze
    validate_freeze(frozen)
    model_key = predictions.get("model_key")
    if (
        model_key not in {"A", "B"}
        or predictions.get("freeze_hash") != frozen["freeze_hash"]
        or predictions.get("model_hash") != frozen["model_hash"]
        or predictions.get("config_hash") != frozen["config_hash"]
        or predictions.get("selected_model_hash") != frozen["models"][model_key]["model_hash"]
    ):
        raise ValueError("PREDICTION_FROZEN_IDENTITY_MISMATCH")
    if (
        annotations is not None
        and annotations.get("dataset_manifest_hash") != dataset["manifest_hash"]
    ):
        raise ValueError("ANNOTATIONS_DATASET_MISMATCH")
    if annotations is not None and (
        annotations.get("purpose") != dataset["purpose"]
        or annotations.get("SYNTHETIC") is not dataset["SYNTHETIC"]
    ):
        raise ValueError("ANNOTATIONS_PURPOSE_MISMATCH")
    if split is None:
        split = build_split(dataset, {})
    ledger_snapshot: JSONDict | None
    if isinstance(ledger, Path):
        from .splits import append_exposure_event, load_exposure_ledger

        if annotations is not None:
            append_exposure_event(
                ledger,
                "GT_SCORE_READ",
                {
                    "freeze_hash": frozen["freeze_hash"],
                    "prediction_hash": predictions["prediction_hash"],
                    "annotations_hash": annotations["annotations_hash"],
                },
            )
        ledger_snapshot = load_exposure_ledger(ledger)
    else:
        ledger_snapshot = ledger
    # Geometry/reference reads follow the caller's recorded scoring exposure.
    # Passing an in-memory annotation dict does not provide independent custody.
    snapshots = _snapshot_index(annotations)
    admission = check_admission(
        dataset,
        split,
        annotations,
        freeze=frozen,
        test_seal=test_seal,
        predictions=predictions,
        ledger=ledger_snapshot,
    )
    global_reasons = admission.get("reason_codes", [])
    admission_images = {row["image_id"]: row for row in admission["images"]}
    originals = {image["image_id"]: image for image in dataset["images"]}
    if not set(snapshots) <= set(originals):
        raise ValueError("ANNOTATIONS_IMAGE_SCOPE_MISMATCH")
    from .annotations import validate_snapshot

    for image_id, bound_snapshot in snapshots.items():
        validate_snapshot(bound_snapshot, originals[image_id])
    local_reason_codes = {
        reason for item in admission_images.values() for reason in item["reason_codes"]
    }
    global_gate_reasons = [reason for reason in global_reasons if reason not in local_reason_codes]
    if global_reasons:
        global_gate_reasons.append("ADMISSION_SCOPE_BLOCKED")
    image_predictions: dict[str, JSONDict] = {}
    for prediction in predictions["images"]:
        image_id = prediction.get("image_id")
        if image_id not in originals or image_id in image_predictions:
            raise ValueError("PREDICTION_IMAGE_SCOPE_INVALID")
        if not verify_seal(prediction, "prediction_hash"):
            raise ValueError("PREDICTION_IMAGE_HASH_MISMATCH")
        if prediction.get("source_asset_hash") != originals[image_id]["asset_sha256"]:
            raise ValueError("PREDICTION_ASSET_HASH_MISMATCH")
        if (
            prediction.get("purpose") != dataset["purpose"]
            or prediction.get("SYNTHETIC") is not dataset["SYNTHETIC"]
            or prediction.get("source_id") != originals[image_id]["source_id"]
        ):
            raise ValueError("PREDICTION_IMAGE_PROVENANCE_MISMATCH")
        if prediction.get("status") not in {"ok", "failed"}:
            raise ValueError("PREDICTION_IMAGE_STATUS_INVALID")
        if prediction["status"] == "ok":
            detected = prediction.get("detected_objects")
            if (
                not isinstance(detected, list)
                or type(prediction.get("predicted_visible_fruit_count")) is not int
                or len(detected) != prediction["predicted_visible_fruit_count"]
            ):
                raise ValueError("PREDICTION_COUNT_OR_OBJECTS_INVALID")
            _geometry(detected, originals[image_id], predictions=True)
        elif (
            prediction.get("detected_objects") is not None
            or prediction.get("predicted_visible_fruit_count") is not None
        ):
            raise ValueError("FAILED_PREDICTION_MUST_REMAIN_NULL")
        image_predictions[image_id] = prediction
    if predictions.get("prediction_scope_hash") != canonical_hash(sorted(image_predictions)):
        raise ValueError("PREDICTION_SCOPE_HASH_MISMATCH")
    missing_predictions = set(admission_images) - set(image_predictions)
    if missing_predictions:
        global_gate_reasons.append("PREDICTION_SCOPE_INCOMPLETE")
    rows: list[JSONDict] = []
    truths: dict[str, list[JSONDict]] = {}
    candidates: dict[str, list[JSONDict]] = {}
    ignored: dict[str, set[int]] = {}
    for image_id in sorted(set(image_predictions) | set(admission_images)):
        image = originals[image_id]
        prediction = image_predictions.get(
            image_id, {"status": "missing", "predicted_visible_fruit_count": None}
        )
        snapshot = snapshots.get(image_id)
        reasons = list(global_gate_reasons)
        reasons.extend(admission_images.get(image_id, {}).get("reason_codes", []))
        if image_id not in admission_images:
            reasons.append("NOT_IN_EVALUATION_SPLIT")
        elif (
            snapshot is None
            or snapshot.get("objects") is None
            or snapshot.get("visible_count") is None
        ):
            reasons.append("GT_MISSING")
        elif (
            snapshot.get("source_asset_hash") != image["asset_sha256"]
            or snapshot.get("purpose") != dataset["purpose"]
        ):
            reasons.append("REFERENCE_ASSET_OR_PURPOSE_MISMATCH")
        if image_id in missing_predictions:
            reasons.append("PREDICTION_MISSING")
        elif prediction.get("status") != "ok":
            reasons.append("PREDICTION_FAILED")
        row: JSONDict = {
            "image_id": image_id,
            "source_asset_hash": image["asset_sha256"],
            "status": "NOT_EVALUABLE",
            "reason_codes": sorted(set(reasons)),
            "reference_count": None,
            "predicted_count": prediction.get("predicted_visible_fruit_count"),
            "signed_count_error": None,
            "absolute_count_error": None,
            "tp": None,
            "fp": None,
            "fn": None,
            "matches": [],
            "false_positive_indices": [],
            "false_negative_indices": [],
            "ignored_prediction_indices": [],
            "reference_hash": snapshot.get("snapshot_hash") if snapshot else None,
            "scene_metadata": image.get("scene_metadata") or {},
        }
        if not reasons and snapshot is not None:
            targets = [box for box in snapshot["objects"] if box["disposition"] == "TARGET"]
            regions = [
                box["bbox_xyxy"]
                for box in snapshot["objects"]
                if box["disposition"] in {"IGNORE", "UNCERTAIN"}
            ]
            detected = prediction.get("detected_objects")
            if (
                not isinstance(detected, list)
                or type(prediction.get("predicted_visible_fruit_count")) is not int
                or len(detected) != prediction["predicted_visible_fruit_count"]
            ):
                raise ValueError("PREDICTION_COUNT_OR_OBJECTS_INVALID")
            _geometry(snapshot["objects"], image, predictions=False)
            _geometry(detected, image, predictions=True)
            if snapshot["visible_count"] != len(targets):
                raise ValueError("REFERENCE_COUNT_MISMATCH")
            matched = match_reference(targets, detected, regions)
            reference, predicted = len(targets), len(detected)
            row.update(
                status="EVALUATED",
                reference_count=reference,
                predicted_count=predicted,
                signed_count_error=predicted - reference,
                absolute_count_error=abs(predicted - reference),
                **matched,
            )
            truths[image_id] = targets
            candidates[image_id] = detected
            ignored[image_id] = set(matched["ignored_prediction_indices"])
        rows.append(row)
    metrics = compact_metrics(rows)
    metrics["RESEARCH_AP50"] = research_ap50(truths, candidates, ignored)
    subgroup_metrics = {}
    for dimension, declared_values in {
        "density": {"sparse", "dense", "pressure"},
        "occlusion": {"none", "partial", "high"},
        "lighting": {"normal", "shadow", "glare"},
        "size": {"small", "large", "mixed"},
        "domain": {"regular", "ood"},
    }.items():
        values = {_stratum_value(row["scene_metadata"], dimension) for row in rows} | {
            "UNKNOWN",
            *declared_values,
        }
        subgroup_metrics[dimension] = {
            str(value): compact_metrics(
                [row for row in rows if _stratum_value(row["scene_metadata"], dimension) == value]
            )
            for value in sorted(values)
        }
    failures = [
        row
        for row in rows
        if row["status"] != "EVALUATED" or row["fp"] or row["fn"] or row["absolute_count_error"]
    ]
    coco = (
        _coco_metrics(originals, truths, candidates, snapshots)
        if run_coco and truths
        else {
            "status": "NOT_EVALUABLE" if not truths else "NOT_RUN",
            "reason_code": "NO_QUALIFIED_REFERENCE_IMAGES"
            if not truths
            else "OPTIONAL_EVALUATOR_NOT_REQUESTED",
            "COCO_MAP50": None,
            "COCO_MAP50_95": None,
        }
    )
    return seal(
        {
            "schema_version": "blueberry-vision-r3-evaluation/3.0.0",
            "evaluator_version": EVALUATOR_VERSION,
            "evaluator_hash": file_hash(Path(__file__)),
            "evaluation_protocol": evaluation_protocol(),
            "evaluation_protocol_hash": frozen["evaluation_protocol_hash"],
            "purpose": dataset["purpose"],
            "SYNTHETIC": dataset["SYNTHETIC"],
            "evaluation_scope": dataset["purpose"],
            "evaluation_image_ids": sorted(admission_images),
            "evaluation_scope_hash": canonical_hash(sorted(admission_images)),
            "public_test_exposure": "EXPOSED_PUBLIC_BENCHMARK"
            if dataset["purpose"] == "PUBLIC_EXTERNAL_BENCHMARK"
            else "NOT_PUBLIC_BENCHMARK",
            "dataset_manifest_hash": dataset["manifest_hash"],
            "split_hash": split.get("split_hash") if split else None,
            "test_seal_hash": test_seal.get("test_seal_hash") if test_seal else None,
            "model_hash": predictions["model_hash"],
            "selected_model_hash": predictions["selected_model_hash"],
            "config_hash": predictions["config_hash"],
            "prediction_hash": predictions["prediction_hash"],
            "annotations_hash": annotations.get("annotations_hash") if annotations else None,
            "ledger_hash": ledger_snapshot.get("ledger_hash") if ledger_snapshot else None,
            "status": metrics["status"],
            "reason_codes": sorted(
                {*global_reasons, *(reason for row in rows for reason in row["reason_codes"])}
            ),
            "metrics": metrics,
            "subgroup_metrics": subgroup_metrics,
            "per_image_results": rows,
            "failure_cases": failures,
            "failure_count": len(failures),
            "coverage": {
                "dataset_image_count": len(originals),
                "predicted_image_count": len(image_predictions),
                "evaluation_scope_image_count": len(admission_images),
                "missing_prediction_count": len(missing_predictions),
                "inference_success_count": sum(
                    pred["status"] == "ok" for pred in image_predictions.values()
                ),
                "reference_available_count": admission["qualified_reference_count"],
                "qualified_reference_count": admission["qualified_reference_count"],
                "annotation_available_count": sum(
                    image_id in snapshots and snapshots[image_id].get("objects") is not None
                    for image_id in admission_images
                ),
                "evaluated_count": metrics["evaluated_count"],
                "excluded_count": metrics["excluded_count"],
                "unpredicted_count": len(originals) - len(image_predictions),
            },
            "coco": coco,
            "COCO_MAP50": coco["COCO_MAP50"],
            "COCO_MAP50_95": coco["COCO_MAP50_95"],
            "limitations": [
                "COUNT_NOT_KG",
                "CANDIDATE_LABEL_NOT_BUSINESS_APPROVED",
                "PUBLIC_EXTERNAL_BENCHMARK_NOT_ORCHARD_ACCURACY",
                "R2_SYNTHETIC_MODEL_NOT_REAL_TRAINED",
                "RESEARCH_SEAL_NOT_INDEPENDENT_ACCESS_CONTROL",
                "UNANNOTATED_IMAGES_ARE_NOT_ZERO_FRUIT",
            ],
        },
        "report_hash",
    )


def _stratum_value(scene: JSONDict, dimension: str) -> str:
    value = scene.get(dimension)
    return value if isinstance(value, str) and value.strip() else "UNKNOWN"


def _coco_metrics(
    images: dict[str, JSONDict],
    truths: dict[str, list[JSONDict]],
    predictions: dict[str, list[JSONDict]],
    snapshots: dict[str, JSONDict],
) -> JSONDict:
    """Optional official pycocotools bbox evaluator, pinned with explicit limits."""
    unavailable: JSONDict = {
        "status": "NOT_RUN",
        "reason_code": None,
        "COCO_MAP50": None,
        "COCO_MAP50_95": None,
    }
    try:
        package_version = version("pycocotools")
    except PackageNotFoundError:
        return {**unavailable, "reason_code": "PYCOCOTOOLS_NOT_INSTALLED"}
    if package_version != "2.0.11":
        return {**unavailable, "reason_code": "PYCOCOTOOLS_VERSION_NOT_PINNED"}
    if any(
        box["disposition"] != "TARGET"
        for image_id in truths
        for box in snapshots[image_id]["objects"]
    ):
        return {**unavailable, "reason_code": "COCO_IGNORE_GT_POLICY_UNSUPPORTED"}
    if not sum(len(boxes) for boxes in truths.values()):
        return {**unavailable, "reason_code": "NO_GT_CLASS_SUPPORT"}
    ids = {image_id: index + 1 for index, image_id in enumerate(sorted(truths))}
    coco_dataset: JSONDict = {
        "images": [
            {
                "id": ids[image_id],
                "width": images[image_id]["image_width"],
                "height": images[image_id]["image_height"],
            }
            for image_id in ids
        ],
        "categories": [{"id": 1, "name": CANDIDATE_LABEL}],
        "annotations": [],
        "info": {},
    }
    detections = []
    for image_id in ids:
        for target in truths[image_id]:
            x1, y1, x2, y2 = target["bbox_xyxy"]
            coco_dataset["annotations"].append(
                {
                    "id": len(coco_dataset["annotations"]) + 1,
                    "image_id": ids[image_id],
                    "category_id": 1,
                    "bbox": [x1, y1, x2 - x1, y2 - y1],
                    "area": (x2 - x1) * (y2 - y1),
                    "iscrowd": 0,
                }
            )
        for prediction in predictions[image_id]:
            x1, y1, x2, y2 = prediction["bbox_xyxy"]
            detections.append(
                {
                    "image_id": ids[image_id],
                    "category_id": 1,
                    "bbox": [x1, y1, x2 - x1, y2 - y1],
                    "score": prediction["score"],
                }
            )
    coco_module = importlib.import_module("pycocotools.coco")
    eval_module = importlib.import_module("pycocotools.cocoeval")
    with contextlib.redirect_stdout(io.StringIO()):
        ground_truth = coco_module.COCO()
        ground_truth.dataset = coco_dataset
        ground_truth.createIndex()
        if detections:
            detected = ground_truth.loadRes(detections)
        else:
            detected = coco_module.COCO()
            detected.dataset = {
                "images": coco_dataset["images"],
                "categories": coco_dataset["categories"],
                "annotations": [],
            }
            detected.createIndex()
        evaluator = eval_module.COCOeval(ground_truth, detected, "bbox")
        evaluator.params.imgIds = list(ids.values())
        evaluator.params.catIds = [1]
        evaluator.params.maxDets = [1, 10, 100]
        evaluator.evaluate()
        evaluator.accumulate()
        evaluator.summarize()
    return {
        "status": "EVALUATED",
        "reason_code": None,
        "evaluator": "pycocotools.COCOeval",
        "evaluator_version": package_version,
        "iou_type": "bbox",
        "maxDets": [1, 10, 100],
        "area_range": "all",
        "COCO_MAP50_95": float(evaluator.stats[0]),
        "COCO_MAP50": float(evaluator.stats[1]),
        "limitations": ["MAXDETS_100_CAN_TRUNCATE_DENSE_IMAGES", "CANDIDATE_SINGLE_CLASS"],
    }
