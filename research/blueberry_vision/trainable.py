"""A real CPU-trained, synthetic-only logistic-regression pixel baseline.

The learned pixel foreground is converted to four-connected boxes using the same
visible-count definition as the classical baseline. No bounding boxes, scene
identifiers, masks, or reference counts are inputs to pixel inference.
"""

from __future__ import annotations

import math
from importlib.metadata import metadata
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import __version__ as pillow_version

from research.blueberry_vision.assets import load_asset
from research.blueberry_vision.classical import (
    _finite_number,
    _positive_integer,
    _research_images,
    extract_components,
    prediction_bundle,
    validate_component_config,
    validate_rgb,
)
from research.blueberry_vision.r2_common import (
    CLASS_LABEL,
    JSONDict,
    canonical_hash,
    file_hash,
    read_json,
    seal,
    verify_seal,
    write_json_new,
)

MODEL_VERSION = "numpy-logistic-pixel/2.0.0"
MODEL_SCHEMA = "blueberry-vision-pixel-model/2.0.0"
FEATURE_VERSION = "normalized-rgb-polynomial/2.0.0"
FEATURE_NAMES = [
    "red",
    "green",
    "blue",
    "red_minus_green",
    "blue_minus_green",
    "blue_minus_red",
    "red_times_green",
    "green_times_blue",
    "red_times_blue",
    "channel_range",
]


def default_training_config() -> JSONDict:
    """Fixed before evaluation; no test-driven parameter selection is performed."""
    return {
        "version": MODEL_VERSION,
        "feature_version": FEATURE_VERSION,
        "seed": 7123,
        "samples_per_image": 1200,
        "iterations": 80,
        "learning_rate": 0.15,
        "l2_penalty": 0.001,
        "maximum_input_pixels": 4_000_000,
        "maximum_training_samples": 250_000,
        "source_scope": "synthetic_train_only",
        "sampling": "balanced_per_image_without_replacement",
    }


def default_trained_inference_config() -> JSONDict:
    return {
        "version": MODEL_VERSION,
        "probability_threshold": 0.5,
        "minimum_component_area": 12,
        "minimum_fill_ratio": 0.12,
        "maximum_component_area_fraction": 0.90,
        "maximum_input_pixels": 4_000_000,
        "connectivity": 4,
        "score_type": "uncalibrated_pixel_probability_shape_score",
    }


def _validate_training_config(config: JSONDict) -> None:
    if (
        config.get("version") != MODEL_VERSION
        or config.get("feature_version") != FEATURE_VERSION
        or config.get("source_scope") != "synthetic_train_only"
        or config.get("sampling") != "balanced_per_image_without_replacement"
    ):
        raise ValueError("INVALID_CONFIG_TRAINING_VERSION")
    seed = config.get("seed")
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise ValueError("INVALID_CONFIG_SEED")
    for field, maximum in (
        ("iterations", 1000),
        ("samples_per_image", 5000),
        ("maximum_training_samples", 250_000),
        ("maximum_input_pixels", 4_000_000),
    ):
        if _positive_integer(config, field) > maximum:
            raise ValueError(f"INVALID_CONFIG_{field.upper()}_LIMIT")
    _finite_number(config, "learning_rate", 0.000001, 1.0)
    _finite_number(config, "l2_penalty", 0.0, 10.0)


def _color_features(pixels: NDArray[np.uint8]) -> NDArray[np.float64]:
    # No learned preprocessing is applied until the train-only scaler below.
    normalized = pixels.astype(np.float64) / 255.0
    red, green, blue = normalized[:, 0], normalized[:, 1], normalized[:, 2]
    return np.column_stack(
        (
            red,
            green,
            blue,
            red - green,
            blue - green,
            blue - red,
            red * green,
            green * blue,
            red * blue,
            normalized.max(axis=1) - normalized.min(axis=1),
        )
    )


def _sigmoid(logits: NDArray[np.float64]) -> NDArray[np.float64]:
    return 1.0 / (1.0 + np.exp(-np.clip(logits, -40.0, 40.0)))


def _loss(
    features: NDArray[np.float64],
    labels: NDArray[np.float64],
    coefficients: NDArray[np.float64],
    intercept: float,
    l2: float,
) -> float:
    logits = features @ coefficients + intercept
    return float(
        np.mean(np.logaddexp(0.0, logits) - labels * logits) + l2 / 2 * np.sum(coefficients**2)
    )


def _training_pixels(
    images: list[JSONDict], data_root: Path, config: JSONDict
) -> tuple[NDArray[np.float64], NDArray[np.float64], JSONDict, list[JSONDict]]:
    rng = np.random.default_rng(config["seed"])
    feature_blocks: list[NDArray[np.float64]] = []
    label_blocks: list[NDArray[np.float64]] = []
    provenance: list[JSONDict] = []
    ignored_pixels = 0
    sampled_pixels = 0
    for image in images:
        rgb = load_asset(
            data_root,
            image["original_asset_ref"],
            expected_hash=image["asset_sha256"],
            expected_size=(image["image_width"], image["image_height"]),
        ).rgb
        validate_rgb(rgb, config["maximum_input_pixels"])
        if not image.get("training_mask_ref") or not image.get("training_mask_sha256"):
            raise ValueError("TRAINING_MASK_REQUIRED")
        mask_rgb = load_asset(
            data_root,
            image["training_mask_ref"],
            expected_hash=image["training_mask_sha256"],
            expected_size=(image["image_width"], image["image_height"]),
        ).rgb
        if not np.array_equal(mask_rgb[:, :, 0], mask_rgb[:, :, 1]) or not np.array_equal(
            mask_rgb[:, :, 0], mask_rgb[:, :, 2]
        ):
            raise ValueError("TRAINING_MASK_GRAYSCALE_REQUIRED")
        mask = mask_rgb[:, :, 0].reshape(-1)
        if not np.isin(mask, (0, 128, 255)).all():
            raise ValueError("TRAINING_MASK_VALUES_INVALID")
        ignored_pixels += int(np.count_nonzero(mask == 128))
        positive = np.flatnonzero(mask == 255)
        negative = np.flatnonzero(mask == 0)
        budget = config["samples_per_image"]
        positive_count = min(len(positive), budget // 2)
        negative_count = min(len(negative), budget - positive_count)
        if negative_count < budget - positive_count:
            positive_count = min(len(positive), budget - negative_count)
        indices = np.concatenate(
            (
                rng.choice(positive, size=positive_count, replace=False),
                rng.choice(negative, size=negative_count, replace=False),
            )
        )
        if not len(indices):
            raise ValueError("NO_EVALUABLE_TRAINING_PIXELS")
        sampled_pixels += len(indices)
        if sampled_pixels > config["maximum_training_samples"]:
            raise ValueError("TRAINING_SAMPLE_RESOURCE_LIMIT")
        feature_blocks.append(_color_features(rgb.reshape(-1, 3)[indices]))
        label_blocks.append((mask[indices] == 255).astype(np.float64))
        provenance.append(
            {
                "image_id": image["image_id"],
                "asset_sha256": image["asset_sha256"],
                "training_mask_sha256": image["training_mask_sha256"],
                "sample_count": len(indices),
                "foreground_sample_count": positive_count,
                "background_sample_count": negative_count,
                "selected_pixel_indices_hash": canonical_hash(indices.tolist()),
            }
        )
    features, labels = np.concatenate(feature_blocks), np.concatenate(label_blocks)
    if len(np.unique(labels)) != 2:
        raise ValueError("TWO_TRAINING_CLASSES_REQUIRED")
    summary: JSONDict = {
        "used_image_ids": [image["image_id"] for image in images],
        "training_image_count": len(images),
        "sampled_pixels": sampled_pixels,
        "foreground_samples": int(np.count_nonzero(labels == 1)),
        "background_samples": int(np.count_nonzero(labels == 0)),
        "ignored_pixels": ignored_pixels,
    }
    return features, labels, summary, provenance


def train_model(
    manifest: JSONDict, data_root: Path, output_dir: Path, config: JSONDict
) -> JSONDict:
    """Fit genuine parameters using only synthetic train files and their masks."""
    _validate_training_config(config)
    images = _research_images(manifest, "train")
    outputs = ("model.json", "training_log.json", "model_manifest.json")
    if any((output_dir / name).exists() for name in outputs):
        raise FileExistsError("MODEL_OUTPUT_ALREADY_EXISTS")
    features, labels, summary, provenance = _training_pixels(images, data_root, config)
    # The scaler is fitted only on sampled training pixels; never on validation/test.
    mean = features.mean(axis=0)
    scale = np.maximum(features.std(axis=0), 0.000001)
    standardized = (features - mean) / scale
    coefficients = np.zeros(standardized.shape[1], dtype=np.float64)
    intercept = 0.0
    learning_rate, l2 = config["learning_rate"], config["l2_penalty"]
    loss_history = [_loss(standardized, labels, coefficients, intercept, l2)]
    for _ in range(config["iterations"]):
        error = _sigmoid(standardized @ coefficients + intercept) - labels
        coefficients -= learning_rate * (standardized.T @ error / len(labels) + l2 * coefficients)
        intercept -= learning_rate * float(error.mean())
        loss_history.append(_loss(standardized, labels, coefficients, intercept, l2))
    if not np.isfinite(coefficients).all() or not math.isfinite(intercept):
        raise ValueError("NONFINITE_FITTED_PARAMETERS")
    training_data_hash = canonical_hash(provenance)
    model = seal(
        {
            "schema_version": MODEL_SCHEMA,
            "model_version": MODEL_VERSION,
            "model_type": "numpy_logistic_regression_pixel_classifier",
            "SYNTHETIC": True,
            "source_scope": "synthetic_train_only",
            "target_class": CLASS_LABEL,
            "feature_version": FEATURE_VERSION,
            "feature_names": FEATURE_NAMES,
            "training_config": config,
            "training_config_hash": canonical_hash(config),
            "training_data_hash": training_data_hash,
            "training_images": provenance,
            "scaler_mean": mean.tolist(),
            "scaler_scale": scale.tolist(),
            "coefficients": coefficients.tolist(),
            "intercept": intercept,
            "dependencies": {"numpy": np.__version__, "Pillow": pillow_version},
            "licenses": {
                "numpy": metadata("numpy").get("License-Expression", "UNKNOWN"),
                "Pillow": metadata("Pillow").get("License-Expression", "UNKNOWN"),
            },
            "limitations": [
                "SYNTHETIC_ONLY_NOT_REAL_BLUEBERRY_ACCURACY",
                "CONNECTED_PIXELS_CAN_MERGE_TOUCHING_FRUIT",
                "PIXEL_PROBABILITIES_ARE_NOT_CALIBRATED_OBJECT_CONFIDENCE",
                "VISIBLE_COUNT_IS_NOT_HARVEST_WEIGHT",
            ],
        },
        "model_hash",
    )
    training_log = seal(
        {
            **summary,
            "SYNTHETIC": True,
            "split": "train",
            "model_hash": model["model_hash"],
            "training_config_hash": model["training_config_hash"],
            "training_data_hash": training_data_hash,
            "loss_history": loss_history,
            "iterations_completed": config["iterations"],
            "validation_note": "No validation/test labels were used to fit or select parameters.",
        },
        "training_log_hash",
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json_new(output_dir / "model.json", model)
    write_json_new(output_dir / "training_log.json", training_log)
    write_json_new(
        output_dir / "model_manifest.json",
        seal(
            {
                "SYNTHETIC": True,
                "model_version": MODEL_VERSION,
                "model_hash": model["model_hash"],
                "model_artifact_ref": "model.json",
                "model_artifact_sha256": file_hash(output_dir / "model.json"),
                "training_log_ref": "training_log.json",
                "training_log_sha256": file_hash(output_dir / "training_log.json"),
                "training_config_hash": model["training_config_hash"],
                "training_data_hash": training_data_hash,
                "train_image_count": len(images),
                "train_image_ids": summary["used_image_ids"],
                "feature_names": FEATURE_NAMES,
                "dependencies": model["dependencies"],
                "licenses": model["licenses"],
            },
            "model_manifest_hash",
        ),
    )
    return model


def _numeric_vector(model: JSONDict, key: str, *, positive: bool = False) -> NDArray[np.float64]:
    values = model.get(key)
    if not isinstance(values, list) or len(values) != len(FEATURE_NAMES):
        raise ValueError("MODEL_PARAMETER_DIMENSION_INVALID")
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or (positive and value <= 0)
        for value in values
    ):
        raise ValueError("MODEL_PARAMETERS_INVALID")
    return np.asarray(values, dtype=np.float64)


def _validate_model(model: JSONDict) -> None:
    if not verify_seal(model, "model_hash"):
        raise ValueError("MODEL_HASH_MISMATCH")
    if (
        model.get("schema_version") != MODEL_SCHEMA
        or model.get("model_version") != MODEL_VERSION
        or model.get("SYNTHETIC") is not True
        or model.get("source_scope") != "synthetic_train_only"
        or model.get("target_class") != CLASS_LABEL
        or model.get("feature_version") != FEATURE_VERSION
        or model.get("feature_names") != FEATURE_NAMES
        or model.get("model_type") != "numpy_logistic_regression_pixel_classifier"
    ):
        raise ValueError("MODEL_CONTRACT_INVALID")
    _numeric_vector(model, "coefficients")
    _numeric_vector(model, "scaler_mean")
    _numeric_vector(model, "scaler_scale", positive=True)
    _finite_number(model, "intercept", -1_000_000.0, 1_000_000.0)


def load_model(path: Path) -> JSONDict:
    model = read_json(path)
    _validate_model(model)
    return model


def detect_trained_rgb(
    rgb: NDArray[np.uint8], model: JSONDict, config: JSONDict | None = None
) -> list[JSONDict]:
    """Pure pixel inference; neither training masks nor test references are inputs."""
    _validate_model(model)
    inference_config = default_trained_inference_config() if config is None else config
    validate_component_config(inference_config)
    if inference_config.get("version") != MODEL_VERSION:
        raise ValueError("INVALID_CONFIG_MODEL_VERSION")
    threshold = _finite_number(inference_config, "probability_threshold", 0.0, 1.0)
    validate_rgb(rgb, inference_config["maximum_input_pixels"])
    mean, scale = (
        _numeric_vector(model, "scaler_mean"),
        _numeric_vector(model, "scaler_scale", positive=True),
    )
    coefficients = _numeric_vector(model, "coefficients")
    pixels = rgb.reshape(-1, 3)
    probabilities = np.empty(len(pixels), dtype=np.float64)
    # Chunking bounds feature-matrix memory even for larger authorized inputs.
    for start in range(0, len(pixels), 65536):
        end = min(start + 65536, len(pixels))
        features = (_color_features(pixels[start:end]) - mean) / scale
        probabilities[start:end] = _sigmoid(features @ coefficients + model["intercept"])
    scores = probabilities.reshape(rgb.shape[:2])
    return extract_components(
        scores >= threshold,
        inference_config,
        scores,
        score_type="uncalibrated_pixel_probability_shape_score",
    )


def predict_trained(
    manifest: JSONDict,
    data_root: Path,
    split: str,
    model: JSONDict,
    config: JSONDict | None = None,
) -> JSONDict:
    _validate_model(model)
    inference_config = default_trained_inference_config() if config is None else config
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
            rgb = load_asset(
                data_root,
                image["original_asset_ref"],
                expected_hash=image["asset_sha256"],
                expected_size=(image["image_width"], image["image_height"]),
            ).rgb
            objects = detect_trained_rgb(rgb, model, inference_config)
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
        model_name="Baseline B: synthetic-trained NumPy logistic pixel classifier",
        model_hash=model["model_hash"],
        config=inference_config,
        detector_version=MODEL_VERSION,
    )
