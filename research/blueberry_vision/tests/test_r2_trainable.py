"""True synthetic-only CPU fitting, serialization, isolation, and pixel inference."""

from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

from research.blueberry_vision.r2_common import canonical_hash, dataset_split_hash, read_json, seal
from research.blueberry_vision.trainable import (
    default_training_config,
    detect_trained_rgb,
    load_model,
    predict_trained,
    train_model,
)


def _make_dataset(tmp_path: Path) -> dict[str, Any]:
    images: list[dict[str, Any]] = []
    for index, split in enumerate(("train", "train", "validation", "test")):
        rgb = np.full((32, 40, 3), (30, 85, 35), dtype=np.uint8)
        mask = np.zeros((32, 40), dtype=np.uint8)
        rgb[3:11, 4:12] = (50 + index, 70, 170)
        rgb[18:29, 25:36] = (54, 76 + index, 159)
        mask[3:11, 4:12] = 255
        mask[18:29, 25:36] = 255
        mask[0:2, :] = 128
        image_path = tmp_path / f"image-{index}.png"
        mask_path = tmp_path / f"mask-{index}.png"
        Image.fromarray(rgb).save(image_path)
        Image.fromarray(mask).save(mask_path)
        images.append(
            {
                "image_id": f"hand-synthetic-{index}",
                "SYNTHETIC": True,
                "split": split,
                "asset_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
                "image_width": 40,
                "image_height": 32,
                "original_asset_ref": image_path.name,
                "training_mask_ref": mask_path.name,
                "training_mask_sha256": hashlib.sha256(mask_path.read_bytes()).hexdigest(),
                "capture_session_id": f"session-{index}",
                "sampling_unit_id": f"unit-{index}",
                "template_group_id": f"template-{index}",
                "near_duplicate_group_id": f"frame-group-{index}",
                "generation_seed": 100 + index,
                "source_authority": {
                    "permission_status": "synthetic_only",
                    "allowed_uses": ["metadata_validation", split],
                },
            }
        )
    return seal(
        {"SYNTHETIC": True, "images": images, "split_hash": dataset_split_hash(images)},
        "manifest_hash",
    )


def test_real_fit_loss_reduction_save_reload_and_unseen_pixel_inference(tmp_path: Path) -> None:
    dataset = _make_dataset(tmp_path)
    config = {**default_training_config(), "iterations": 45, "samples_per_image": 300}
    model = train_model(dataset, tmp_path, tmp_path / "model", config)
    reloaded = load_model(tmp_path / "model/model.json")
    assert model == reloaded
    assert any(abs(value) > 0.01 for value in model["coefficients"])
    log = read_json(tmp_path / "model/training_log.json")
    assert log["loss_history"][-1] < log["loss_history"][0]
    assert log["used_image_ids"] == ["hand-synthetic-0", "hand-synthetic-1"]
    assert log["ignored_pixels"] == 160
    prediction = predict_trained(dataset, tmp_path, "test", reloaded)
    assert prediction["images"][0]["status"] == "ok"
    assert prediction["images"][0]["predicted_visible_fruit_count"] == 2
    assert prediction["images"][0]["detected_objects"][0]["bbox_xyxy"] == [4.0, 3.0, 12.0, 11.0]


def test_training_parameters_change_actual_coefficients(tmp_path: Path) -> None:
    dataset = _make_dataset(tmp_path)
    config = {**default_training_config(), "iterations": 8, "samples_per_image": 200}
    first = train_model(dataset, tmp_path, tmp_path / "first", config)
    second = train_model(dataset, tmp_path, tmp_path / "second", {**config, "learning_rate": 0.01})
    assert first["coefficients"] != second["coefficients"]
    assert first["model_hash"] != second["model_hash"]


def test_training_labels_change_weights_and_predictions(tmp_path: Path) -> None:
    dataset = _make_dataset(tmp_path)
    config = {**default_training_config(), "iterations": 40, "samples_per_image": 300}
    first = train_model(dataset, tmp_path, tmp_path / "first", config)
    changed = copy.deepcopy(dataset)
    for image in changed["images"][:2]:
        mask_path = tmp_path / image["training_mask_ref"]
        labels = np.asarray(Image.open(mask_path)).copy()
        labels[labels == 128] = 0
        labels = 255 - labels
        alternative_path = tmp_path / ("alternative-" + mask_path.name)
        Image.fromarray(labels.astype(np.uint8)).save(alternative_path)
        image["training_mask_ref"] = alternative_path.name
        image["training_mask_sha256"] = hashlib.sha256(alternative_path.read_bytes()).hexdigest()
    changed = seal(changed, "manifest_hash")
    second = train_model(changed, tmp_path, tmp_path / "second", config)
    test_rgb = np.asarray(Image.open(tmp_path / "image-3.png"))
    assert first["coefficients"] != second["coefficients"]
    assert detect_trained_rgb(test_rgb, first) != detect_trained_rgb(test_rgb, second)


def test_test_labels_and_masks_never_enter_training_or_inference(tmp_path: Path) -> None:
    dataset = _make_dataset(tmp_path)
    config = {**default_training_config(), "iterations": 12, "samples_per_image": 100}
    # Test references are deliberately missing: train and pixel inference must not open them.
    dataset["images"][3]["training_mask_ref"] = "not-present-test-mask.png"
    dataset["images"][3]["reference_objects"] = [{"answer": "malformed-should-never-be-read"}]
    dataset = seal(dataset, "manifest_hash")
    model = train_model(dataset, tmp_path, tmp_path / "model", config)
    first = predict_trained(dataset, tmp_path, "test", model)
    changed = copy.deepcopy(dataset)
    changed["images"][3]["reference_objects"] = []
    changed["images"][3]["reference_visible_count"] = 9999
    changed["images"][3]["scene_metadata"] = {"pretend_count": -1}
    changed = seal(changed, "manifest_hash")
    second = predict_trained(changed, tmp_path, "test", model)
    assert first["images"] == second["images"]


def test_fit_deterministic_across_output_directories(tmp_path: Path) -> None:
    dataset = _make_dataset(tmp_path)
    config = {**default_training_config(), "iterations": 8, "samples_per_image": 200}
    first = train_model(dataset, tmp_path, tmp_path / "a", config)
    second = train_model(dataset, tmp_path, tmp_path / "b", config)
    assert first == second
    assert canonical_hash(first) == canonical_hash(second)
    with pytest.raises(FileExistsError):
        train_model(dataset, tmp_path, tmp_path / "a", config)


def test_missing_or_single_class_training_targets_are_not_fake_success(tmp_path: Path) -> None:
    dataset = _make_dataset(tmp_path)
    for image in dataset["images"][:2]:
        mask_path = tmp_path / image["training_mask_ref"]
        Image.fromarray(np.zeros((32, 40), dtype=np.uint8)).save(mask_path)
        image["training_mask_sha256"] = hashlib.sha256(mask_path.read_bytes()).hexdigest()
    dataset = seal(dataset, "manifest_hash")
    with pytest.raises(ValueError, match="TWO_TRAINING_CLASSES_REQUIRED"):
        train_model(dataset, tmp_path, tmp_path / "model", default_training_config())


def test_non_synthetic_training_rejected_before_assets_read(tmp_path: Path) -> None:
    dataset = {"SYNTHETIC": False, "images": []}
    with pytest.raises(ValueError, match="SYNTHETIC"):
        train_model(dataset, tmp_path, tmp_path / "model", default_training_config())


def test_model_hash_and_nonfinite_parameter_validation(tmp_path: Path) -> None:
    dataset = _make_dataset(tmp_path)
    model = train_model(
        dataset, tmp_path, tmp_path / "model", {**default_training_config(), "iterations": 4}
    )
    model["coefficients"][0] += 1.0
    with pytest.raises(ValueError, match="MODEL_HASH"):
        detect_trained_rgb(np.zeros((10, 10, 3), dtype=np.uint8), model)
    model["coefficients"][0] = float("inf")
    with pytest.raises(ValueError):
        detect_trained_rgb(np.zeros((10, 10, 3), dtype=np.uint8), model)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("iterations", 0),
        ("seed", True),
        ("learning_rate", float("nan")),
        ("samples_per_image", -2),
        ("l2_penalty", -1.0),
    ],
)
def test_invalid_training_config_rejected(tmp_path: Path, field: str, value: object) -> None:
    with pytest.raises(ValueError, match="CONFIG"):
        train_model(
            {"SYNTHETIC": True, "images": []},
            tmp_path,
            tmp_path / "model",
            {**default_training_config(), field: value},
        )
