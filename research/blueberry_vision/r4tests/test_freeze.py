import copy
from pathlib import Path
from typing import Any

import pytest

from research.blueberry_vision.r2_common import read_json, seal
from research.blueberry_vision.r3.evaluation import run_real_inference
from research.blueberry_vision.r4.freeze import lock_predictions
from research.blueberry_vision.r4.package import build_package


@pytest.fixture
def frozen_public_inference(public_preview: Any) -> Any:
    dataset, root = public_preview
    freeze = read_json(Path(__file__).resolve().parents[1] / "evidence/r3/config_freeze.json")
    predictions = {
        key: run_real_inference(dataset, root, freeze, model_key=key) for key in ("A", "B")
    }
    # Pre-modification receipt of genuine pixel inference for tamper/control tests;
    # this is NOT an independent algorithm accuracy assertion or human reference.
    evidence = seal(
        {
            "model_runs": [
                {key: value for key, value in pred.items() if key != "images"}
                for pred in predictions.values()
            ]
        },
        "evidence_hash",
    )
    return dataset, freeze, predictions, evidence


def test_genuine_pixel_output_freeze(frozen_public_inference: Any) -> None:
    d, f, preds, receipt = frozen_public_inference
    lock = lock_predictions(d, build_package(d), f, preds, receipt)
    assert lock["verified"]
    assert lock["scope"] == "EXPOSED_EXTERNAL_EVALUATION_FULL_FRAMES"
    assert lock["gt_consumed"] is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("gt_consumed", True),
        ("selected_model_hash", "0" * 64),
        ("config_hash", "0" * 64),
        ("freeze_hash", "0" * 64),
        ("dataset_manifest_hash", "0" * 64),
    ],
)
def test_resealed_prediction_tampering(
    frozen_public_inference: Any, field: Any, value: Any
) -> None:
    d, f, preds, receipt = frozen_public_inference
    preds = copy.deepcopy(preds)
    preds["A"][field] = value
    preds["A"] = seal(preds["A"], "prediction_hash")
    with pytest.raises(ValueError):
        lock_predictions(d, build_package(d), f, preds, receipt)


def test_one_image_scope_missing(frozen_public_inference: Any) -> None:
    d, f, preds, receipt = frozen_public_inference
    preds["B"]["images"] = []
    preds["B"] = seal(preds["B"], "prediction_hash")
    with pytest.raises(ValueError):
        lock_predictions(d, build_package(d), f, preds, receipt)


def test_config_cannot_change_even_if_rehashed(frozen_public_inference: Any) -> None:
    d, f, preds, receipt = frozen_public_inference
    f = copy.deepcopy(f)
    f["adapter_config"]["maximum_edge"] = 640
    with pytest.raises(ValueError):
        lock_predictions(d, build_package(d), seal(f, "freeze_hash"), preds, receipt)
