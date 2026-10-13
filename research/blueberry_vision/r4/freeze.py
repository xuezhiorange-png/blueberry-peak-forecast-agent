"""Bind original R3 prediction hashes to unmodified R2 models and full-frame scope."""

from __future__ import annotations

from ..r2_common import JSONDict, canonical_hash, seal, verify_seal
from ..r3.evaluation import evaluation_protocol, validate_freeze
from .package import validate_package


def lock_predictions(
    dataset: JSONDict,
    package: JSONDict,
    freeze: JSONDict,
    predictions: dict[str, JSONDict],
    expected_receipt: JSONDict,
    *,
    file_hashes: dict[str, str] | None = None,
) -> JSONDict:
    validate_package(package, dataset)
    validate_freeze(freeze)
    if set(predictions) != {"A", "B"}:
        raise ValueError("BOTH_ORIGINAL_BASELINES_REQUIRED")
    if not verify_seal(expected_receipt, "evidence_hash"):
        raise ValueError("TRUSTED_R3_RECEIPT_HASH_INVALID")
    expected = {row["model_key"]: row for row in expected_receipt["model_runs"]}
    records = {row["image_id"]: row for row in dataset["images"]}
    checks = []
    for key, prediction in predictions.items():
        if not verify_seal(prediction, "prediction_hash"):
            raise ValueError("PREDICTION_HASH_INVALID")
        if prediction["prediction_hash"] != expected[key]["prediction_hash"]:
            raise ValueError("ORIGINAL_R3_PREDICTION_CHANGED")
        bindings = {
            "model_key": key,
            "model_name": freeze["models"][key]["model_name"],
            "selected_model_hash": freeze["models"][key]["model_hash"],
            "model_hash": freeze["model_hash"],
            "config_hash": freeze["config_hash"],
            "freeze_hash": freeze["freeze_hash"],
            "gt_consumed": False,
            "dataset_manifest_hash": dataset["manifest_hash"],
            "SYNTHETIC": False,
            "purpose": dataset["purpose"],
            "count_unit": "visible_fruit_per_image",
        }
        if any(prediction.get(field) != value for field, value in bindings.items()):
            raise ValueError("PREDICTION_MODEL_CONFIG_OR_SCOPE_MISMATCH")
        rows = prediction.get("images", [])
        if len(rows) != len(records) or {row["image_id"] for row in rows} != set(records):
            raise ValueError("PREDICTION_IMAGE_SCOPE_MISMATCH")
        for row in rows:
            if (
                not verify_seal(row, "prediction_hash")
                or row["source_asset_hash"] != records[row["image_id"]]["asset_sha256"]
            ):
                raise ValueError("PREDICTION_IMAGE_HASH_MISMATCH")
        raw_verified = None
        if file_hashes is not None:
            raw_verified = file_hashes[key] == expected[key]["prediction_file_sha256"]
            if not raw_verified:
                raise ValueError("ORIGINAL_R3_PREDICTION_FILE_CHANGED")
        checks.append(
            {
                "model_key": key,
                "model_name": prediction["model_name"],
                "model_hash": prediction["selected_model_hash"],
                "prediction_hash": prediction["prediction_hash"],
                "raw_file_hash_verified": raw_verified,
                "image_count": len(rows),
            }
        )
    protocol = {
        **evaluation_protocol(),
        "reference_admission": "R4_OWNER_VERIFIED_HUMAN_REFERENCE_REQUIRED",
        "scope": "ALL_8_ADMITTED_FULL_FRAMES_NOT_MODEL_ERROR_SELECTED",
        "partial_roi": "NOT_USED; separate prior registration required",
        "unresolved_fruit_count": "NOT_EVALUABLE",
        "exposure": "EXPOSED_EXTERNAL_EVALUATION_NOT_BLIND",
    }
    return seal(
        {
            "version": "r4-frozen-reference-evaluation/1.0.0",
            "verified": True,
            "package_hash": package["package_hash"],
            "scope_hash": package["scope_hash"],
            "dataset_manifest_hash": dataset["manifest_hash"],
            "r3_freeze_hash": freeze["freeze_hash"],
            "models": checks,
            "config_hash": freeze["config_hash"],
            "training_data_hash": freeze["training_data_hash"],
            "evaluation_protocol": protocol,
            "evaluation_protocol_hash": canonical_hash(protocol),
            "gt_consumed": False,
            "model_retrained": False,
            "thresholds_changed": False,
            "scope": "EXPOSED_EXTERNAL_EVALUATION_FULL_FRAMES",
            "gt_qualified_by_prediction_freeze": False,
        },
        "lock_hash",
    )
