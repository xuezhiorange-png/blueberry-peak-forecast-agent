"""Pixel-based detector acceptance; expected values are hand-made images, not GT lookups."""

from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

from research.blueberry_vision.classical import (
    default_classical_config,
    detect_rgb,
    predict_classical,
)
from research.blueberry_vision.r2_common import CLASS_LABEL, dataset_split_hash, seal


def image_with_squares() -> np.ndarray:
    image = np.full((36, 44, 3), (36, 82, 32), dtype=np.uint8)
    image[4:12, 3:11] = (62, 72, 159)
    image[20:30, 29:39] = (64, 80, 172)
    return image


def test_pixel_detector_finds_two_independent_targets() -> None:
    result = detect_rgb(image_with_squares(), default_classical_config())
    assert [obj["bbox_xyxy"] for obj in result] == [
        [3.0, 4.0, 11.0, 12.0],
        [29.0, 20.0, 39.0, 30.0],
    ]
    assert all(obj["class_label"] == CLASS_LABEL for obj in result)
    assert all(obj["score_type"] == "non_probability_color_shape_score" for obj in result)
    assert all(0.0 <= obj["score"] <= 1.0 for obj in result)


def test_true_empty_image_and_red_interference() -> None:
    rgb = np.full((20, 30, 3), (30, 70, 30), dtype=np.uint8)
    rgb[4:13, 4:13] = (170, 50, 30)
    assert detect_rgb(rgb, default_classical_config()) == []


def test_touching_regions_merge_instead_of_claiming_hidden_instances() -> None:
    rgb = np.zeros((30, 40, 3), dtype=np.uint8)
    rgb[5:16, 4:15] = (55, 60, 150)
    rgb[5:16, 15:26] = (55, 60, 150)
    result = detect_rgb(rgb, default_classical_config())
    assert len(result) == 1
    assert result[0]["bbox_xyxy"] == [4.0, 5.0, 26.0, 16.0]


def test_cropped_edge_targets_are_valid_half_open_boxes() -> None:
    rgb = np.zeros((16, 18, 3), dtype=np.uint8)
    rgb[0:8, 0:7] = (50, 60, 170)
    assert detect_rgb(rgb, default_classical_config())[0]["bbox_xyxy"] == [0.0, 0.0, 7.0, 8.0]


def test_pixels_and_parameters_really_change_predictions() -> None:
    rgb = image_with_squares()
    config = default_classical_config()
    frozen_input = rgb.copy()
    frozen_config = copy.deepcopy(config)
    assert len(detect_rgb(rgb, config)) == 2
    changed_config = {**config, "minimum_component_area": 80}
    assert len(detect_rgb(rgb, changed_config)) == 1
    rgb[4:12, 3:11] = (36, 82, 32)
    assert len(detect_rgb(rgb, config)) == 1
    assert np.array_equal(frozen_input[20:30, 29:39], rgb[20:30, 29:39])
    assert config == frozen_config


def test_small_noise_is_filtered() -> None:
    rgb = np.zeros((20, 20, 3), dtype=np.uint8)
    rgb[3, 3] = (40, 40, 170)
    assert detect_rgb(rgb, default_classical_config()) == []


@pytest.mark.parametrize(
    "rgb",
    [
        np.zeros((20, 20), dtype=np.uint8),
        np.zeros((20, 20, 4), dtype=np.uint8),
        np.zeros((0, 20, 3), dtype=np.uint8),
        np.zeros((20, 20, 3), dtype=np.float64),
    ],
)
def test_invalid_rgb_shape_and_type_rejected(rgb: np.ndarray) -> None:
    with pytest.raises(ValueError, match="RGB"):
        detect_rgb(rgb, default_classical_config())


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("minimum_component_area", 0),
        ("minimum_component_area", True),
        ("minimum_color_difference", float("nan")),
        ("minimum_saturation", 1.1),
    ],
)
def test_invalid_frozen_config_rejected(key: str, value: object) -> None:
    config = {**default_classical_config(), key: value}
    with pytest.raises(ValueError, match="CONFIG"):
        detect_rgb(image_with_squares(), config)


def test_deterministic_order_no_external_identifiers() -> None:
    rgb = image_with_squares()
    assert detect_rgb(rgb, default_classical_config()) == detect_rgb(
        rgb, default_classical_config()
    )
    assert [obj["object_id"] for obj in detect_rgb(rgb, default_classical_config())] == [
        "prediction-00001",
        "prediction-00002",
    ]


def test_wrapper_real_asset_binding_gt_independence_and_failed_image(tmp_path: Path) -> None:
    images: list[dict[str, Any]] = []
    for index, split in enumerate(("train", "test", "test")):
        image_path = tmp_path / f"image-{index}.png"
        Image.fromarray(image_with_squares()).save(image_path)
        images.append(
            {
                "image_id": f"asset-{index}",
                "SYNTHETIC": True,
                "split": split,
                "original_asset_ref": image_path.name,
                "asset_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
                "image_width": 44,
                "image_height": 36,
                "capture_session_id": f"session-{index}",
                "sampling_unit_id": f"unit-{index}",
                "template_group_id": f"template-{index}",
                "near_duplicate_group_id": f"duplicates-{index}",
                "generation_seed": index,
                "source_authority": {
                    "permission_status": "synthetic_only",
                    "allowed_uses": ["metadata_validation", split],
                },
                "visible_count": 9000,
                "objects": [{"pretend_gt": "never-read"}],
            }
        )
    manifest = seal(
        {"SYNTHETIC": True, "images": images, "split_hash": dataset_split_hash(images)},
        "manifest_hash",
    )
    first = predict_classical(manifest, tmp_path, "test", default_classical_config())
    assert first["dataset_manifest_hash"] == manifest["manifest_hash"]
    assert first["split_hash"] == manifest["split_hash"]
    assert first["prediction_scope_hash"] != manifest["split_hash"]
    assert first["images"][0]["predicted_visible_fruit_count"] == 2
    changed = copy.deepcopy(manifest)
    changed["images"][1]["objects"] = []
    changed["images"][1]["visible_count"] = 0
    changed = seal(changed, "manifest_hash")
    second = predict_classical(changed, tmp_path, "test", default_classical_config())
    assert first["images"] == second["images"]
    (tmp_path / "image-2.png").write_bytes(b"corrupt")
    failed = predict_classical(manifest, tmp_path, "test", default_classical_config())["images"][1]
    assert failed["status"] == "failed"
    assert failed["predicted_visible_fruit_count"] is None
    assert failed["detected_objects"] is None
    assert failed["reason_code"] is not None


def test_wrapper_rejects_unsealed_manifest_before_loading(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="MANIFEST_HASH"):
        predict_classical(
            {"SYNTHETIC": True, "images": []}, tmp_path, "test", default_classical_config()
        )
