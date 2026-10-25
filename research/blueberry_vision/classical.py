"""Deterministic RGB color regions, connected-component boxes, and visible counts.

This intentionally simple research baseline merges touching fruit and misses some
synthetic color appearances. A connected color region is a prediction candidate,
never evidence of hidden fruit or a claim of real blueberry accuracy.
"""

from __future__ import annotations

import math
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from research.blueberry_vision.r2_common import (
    CLASS_LABEL,
    JSONDict,
    canonical_hash,
    dataset_split_hash,
    seal,
    verify_seal,
)

CLASSICAL_VERSION = "rgb-connected-components/2.0.0"
PREDICTION_SCHEMA = "blueberry-vision-predictions/2.0.0"


def default_classical_config() -> JSONDict:
    """Pre-registered settings; these defaults do not come from test results."""
    return {
        "name": "classical_rgb_components",
        "version": CLASSICAL_VERSION,
        "minimum_color_difference": 18.0,
        "minimum_blue_over_green": 12.0,
        "minimum_saturation": 0.20,
        "minimum_value": 0.12,
        "minimum_component_area": 12,
        "minimum_fill_ratio": 0.12,
        "maximum_component_area_fraction": 0.90,
        "maximum_input_pixels": 4_000_000,
        "connectivity": 4,
        "score_type": "non_probability_color_shape_score",
    }


def validate_rgb(rgb: NDArray[Any], maximum_pixels: int = 4_000_000) -> None:
    if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != np.uint8:
        raise ValueError("RGB_UINT8_HWC_REQUIRED")
    if rgb.shape[0] == 0 or rgb.shape[1] == 0:
        raise ValueError("RGB_EMPTY_IMAGE")
    if rgb.shape[0] * rgb.shape[1] > maximum_pixels:
        raise ValueError("RGB_PIXEL_LIMIT")


def _finite_number(config: JSONDict, key: str, low: float, high: float) -> float:
    value = config.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"INVALID_CONFIG_{key.upper()}")
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"INVALID_CONFIG_{key.upper()}")
    return float(value)


def _positive_integer(config: JSONDict, key: str) -> int:
    value = config.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"INVALID_CONFIG_{key.upper()}")
    return value


def validate_component_config(config: JSONDict) -> None:
    _positive_integer(config, "minimum_component_area")
    _positive_integer(config, "maximum_input_pixels")
    _finite_number(config, "minimum_fill_ratio", 0.0, 1.0)
    _finite_number(config, "maximum_component_area_fraction", 0.0, 1.0)
    if config.get("connectivity") != 4:
        raise ValueError("INVALID_CONFIG_CONNECTIVITY")


def extract_components(
    mask: NDArray[np.bool_],
    config: JSONDict,
    scores: NDArray[np.float64] | None = None,
    *,
    score_type: str = "non_probability_color_shape_score",
) -> list[JSONDict]:
    """Four-connected candidates with half-open boxes and deterministic scan order.

    No instance-separation oracle is used. In particular, a joined region yields
    one box; the evaluator keeps the resulting under-count rather than repairing
    it using a reference count. The score is explicitly uncalibrated.
    """
    validate_component_config(config)
    if mask.ndim != 2 or mask.dtype != np.bool_ or not mask.size:
        raise ValueError("BINARY_MASK_REQUIRED")
    if mask.size > config["maximum_input_pixels"]:
        raise ValueError("RGB_PIXEL_LIMIT")
    if scores is not None and (scores.shape != mask.shape or not np.isfinite(scores).all()):
        raise ValueError("INVALID_PIXEL_SCORES")
    height, width = mask.shape
    visited = np.zeros_like(mask)
    components: list[JSONDict] = []
    minimum_area = config["minimum_component_area"]
    maximum_area = mask.size * config["maximum_component_area_fraction"]
    for row_value, column_value in np.argwhere(mask):
        row, column = int(row_value), int(column_value)
        if visited[row, column]:
            continue
        queue: deque[tuple[int, int]] = deque([(row, column)])
        visited[row, column] = True
        x_min = x_max = column
        y_min = y_max = row
        area = 0
        score_sum = 0.0
        while queue:
            y, x = queue.popleft()
            area += 1
            x_min, x_max = min(x_min, x), max(x_max, x)
            y_min, y_max = min(y_min, y), max(y_max, y)
            if scores is not None:
                score_sum += float(scores[y, x])
            for next_y, next_x in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if (
                    0 <= next_y < height
                    and 0 <= next_x < width
                    and mask[next_y, next_x]
                    and not visited[next_y, next_x]
                ):
                    visited[next_y, next_x] = True
                    queue.append((next_y, next_x))
        box_area = (x_max + 1 - x_min) * (y_max + 1 - y_min)
        fill_ratio = area / box_area
        if area < minimum_area or area > maximum_area or fill_ratio < config["minimum_fill_ratio"]:
            continue
        # A color/shape score provides ordering, but is not a probability of fruit.
        score = (score_sum / area if scores is not None else 0.5) * 0.8 + fill_ratio * 0.2
        components.append(
            {
                "object_id": f"prediction-{len(components) + 1:05d}",
                "bbox_xyxy": [float(x_min), float(y_min), float(x_max + 1), float(y_max + 1)],
                "class_label": CLASS_LABEL,
                "score": float(round(min(1.0, max(0.0, score)), 10)),
                "score_type": score_type,
                "component_pixel_area": area,
            }
        )
    return components


def detect_rgb(rgb: NDArray[np.uint8], config: JSONDict) -> list[JSONDict]:
    """Only image pixels plus frozen configuration enter the detector."""
    validate_component_config(config)
    validate_rgb(rgb, config["maximum_input_pixels"])
    if (
        config.get("name") != "classical_rgb_components"
        or config.get("version") != CLASSICAL_VERSION
    ):
        raise ValueError("INVALID_CONFIG_CLASSICAL_VERSION")
    difference = _finite_number(config, "minimum_color_difference", 0.0, 255.0)
    green_difference = _finite_number(config, "minimum_blue_over_green", 0.0, 255.0)
    saturation_threshold = _finite_number(config, "minimum_saturation", 0.0, 1.0)
    value_threshold = _finite_number(config, "minimum_value", 0.0, 1.0)
    channels = rgb.astype(np.float64)
    red, green, blue = channels[:, :, 0], channels[:, :, 1], channels[:, :, 2]
    maximum = channels.max(axis=2)
    minimum = channels.min(axis=2)
    saturation = (maximum - minimum) / np.maximum(maximum, 1.0)
    mask = (
        (blue - red >= difference)
        & (blue - green >= green_difference)
        & (saturation >= saturation_threshold)
        & (maximum / 255.0 >= value_threshold)
    )
    color_score = np.clip((blue - np.maximum(red, green)) / 128.0, 0.0, 1.0)
    return extract_components(mask, config, color_score)


def _research_images(manifest: JSONDict, split: str) -> list[JSONDict]:
    if manifest.get("SYNTHETIC") is not True:
        raise ValueError("SYNTHETIC_DATA_REQUIRED")
    if not verify_seal(manifest, "manifest_hash"):
        raise ValueError("MANIFEST_HASH_MISMATCH")
    if split not in {"train", "validation", "test", "out_of_domain"}:
        raise ValueError("INVALID_RESEARCH_SPLIT")
    images = manifest.get("images")
    if not isinstance(images, list):
        raise ValueError("MANIFEST_IMAGES_REQUIRED")
    selected: list[JSONDict] = []
    for image in images:
        if not isinstance(image, dict):
            raise ValueError("MANIFEST_IMAGE_OBJECT_REQUIRED")
        if image.get("SYNTHETIC") is not True:
            raise ValueError("SYNTHETIC_IMAGE_REQUIRED")
        authority = image.get("source_authority", {})
        if authority.get("permission_status") != "synthetic_only" or image.get(
            "split"
        ) not in authority.get("allowed_uses", []):
            raise ValueError("SYNTHETIC_SOURCE_PERMISSION_REQUIRED")
        if image.get("split") == split:
            selected.append(image)
    if not selected:
        raise ValueError("EMPTY_RESEARCH_SPLIT")
    return selected


def prediction_bundle(
    manifest: JSONDict,
    images: list[JSONDict],
    split: str,
    predictions: list[JSONDict],
    *,
    model_name: str,
    model_hash: str,
    config: JSONDict,
    detector_version: str,
) -> JSONDict:
    return seal(
        {
            "schema_version": PREDICTION_SCHEMA,
            "SYNTHETIC": True,
            "count_unit": "visible_fruit_per_image",
            "dataset_manifest_hash": manifest["manifest_hash"],
            "split": split,
            "split_hash": manifest["split_hash"],
            "prediction_scope_hash": dataset_split_hash(images),
            "model_name": model_name,
            "model_hash": model_hash,
            "config_hash": canonical_hash(config),
            "detector_version": detector_version,
            "images": predictions,
        },
        "prediction_hash",
    )


def predict_classical(
    manifest: JSONDict, data_root: Path, split: str, config: JSONDict
) -> JSONDict:
    """Read authorized synthetic files; retain failed images with missing counts."""
    from research.blueberry_vision.assets import load_asset

    validate_component_config(config)
    selected = _research_images(manifest, split)
    predictions: list[JSONDict] = []
    for image in selected:
        prediction: JSONDict = {
            "image_id": image["image_id"],
            "source_asset_hash": image["asset_sha256"],
            "status": "failed",
            "reason_code": None,
            "predicted_visible_fruit_count": None,
            "detected_objects": None,
        }
        try:
            asset = load_asset(
                data_root,
                image["original_asset_ref"],
                expected_hash=image["asset_sha256"],
                expected_size=(image["image_width"], image["image_height"]),
            )
            objects = detect_rgb(asset.rgb, config)
            prediction.update(
                status="ok", predicted_visible_fruit_count=len(objects), detected_objects=objects
            )
        except ValueError as error:
            prediction["reason_code"] = str(error).split(":", 1)[0]
        except OSError:
            prediction["reason_code"] = "ASSET_IO_ERROR"
        predictions.append(seal(prediction, "prediction_hash"))
    return prediction_bundle(
        manifest,
        selected,
        split,
        predictions,
        model_name="Baseline A: deterministic RGB connected components",
        model_hash=canonical_hash({"detector_version": CLASSICAL_VERSION, "config": config}),
        config=config,
        detector_version=CLASSICAL_VERSION,
    )
