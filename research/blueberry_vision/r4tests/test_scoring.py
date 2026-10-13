from pathlib import Path
from typing import Any

import pytest

from research.blueberry_vision.r2_common import file_hash, read_json, seal, write_json_new
from research.blueberry_vision.r3.evaluation import compact_metrics, match_reference, research_ap50
from research.blueberry_vision.r4.recovery import recover_predictions
from research.blueberry_vision.r4.scoring import evaluate_qualified

ROOT = Path(__file__).resolve().parents[1]


def test_recover_exact_historical_predictions_and_serialized_bytes(tmp_path: Any) -> None:
    restored = recover_predictions()
    receipts = read_json(ROOT / "evidence/r3/model_inference.json")
    for receipt in receipts["model_runs"]:
        key = receipt["model_key"]
        output = tmp_path / (key + ".json")
        write_json_new(output, restored[key])
        assert restored[key]["prediction_hash"] == receipt["prediction_hash"]
        assert file_hash(output) == receipt["prediction_file_sha256"]


def test_real_images_without_gt_never_score() -> None:
    dataset = read_json(ROOT / "evidence/r3/pilot_dataset_manifest.json")
    package = read_json(ROOT / "evidence/r4/human_annotation_package.json")
    lock = read_json(ROOT / "evidence/r4/prediction_freeze.json")
    report = evaluate_qualified(dataset, package, lock, recover_predictions(), run_coco=True)
    assert report["status"] == "NOT_EVALUABLE"
    assert report["qualified_gt_images"] == 0
    assert report["qualified_gt_objects"] == 0
    assert report["unscorable_images"] == 8
    for model in report["models"]:
        assert model["metrics"]["count_mae"] is None
        assert model["metrics"]["precision"] is None
        assert model["metrics"]["tp"] is None
        assert model["coco"]["status"] == "NOT_RUN"
        assert all(row["reference_count"] is None for row in model["per_image"])


def test_altered_freeze_cannot_score() -> None:
    dataset = read_json(ROOT / "evidence/r3/pilot_dataset_manifest.json")
    package = read_json(ROOT / "evidence/r4/human_annotation_package.json")
    lock = read_json(ROOT / "evidence/r4/prediction_freeze.json")
    lock["config_hash"] = "0" * 64
    with pytest.raises(ValueError, match="SCORE_LOCK_NOT_ORIGINAL"):
        evaluate_qualified(dataset, package, seal(lock, "lock_hash"), recover_predictions())


def test_detection_hand_golden_duplicates_and_missed_gt() -> None:
    gt = [
        {"class_label": "berry", "bbox_xyxy": [0, 0, 10, 10]},
        {"class_label": "berry", "bbox_xyxy": [20, 20, 30, 30]},
    ]
    pred = [
        {"class_label": "berry", "bbox_xyxy": [0, 0, 10, 10], "score": 0.9},
        {"class_label": "berry", "bbox_xyxy": [0, 0, 10, 10], "score": 0.8},
    ]
    match = match_reference(gt, pred)
    assert (match["tp"], match["fp"], match["fn"]) == (1, 1, 1)
    assert match["matches"][0]["iou"] == 1
    assert research_ap50({"x": gt}, {"x": pred}) == pytest.approx(0.5)


def test_count_hand_golden_and_missing_excluded() -> None:
    rows: list[dict[str, Any]] = [
        {
            "status": "EVALUATED",
            "tp": 1,
            "fp": 2,
            "fn": 0,
            "predicted_count": 3,
            "reference_count": 1,
            "signed_count_error": 2,
            "absolute_count_error": 2,
        },
        {
            "status": "EVALUATED",
            "tp": 1,
            "fp": 0,
            "fn": 1,
            "predicted_count": 1,
            "reference_count": 2,
            "signed_count_error": -1,
            "absolute_count_error": 1,
        },
        {"status": "NOT_EVALUABLE", "reason_codes": ["GT_MISSING"]},
    ]
    metrics = compact_metrics(rows)
    assert metrics["count_mae"] == 1.5
    assert metrics["count_bias"] == 0.5
    assert metrics["total_overcount"] == 2
    assert metrics["total_undercount"] == 1
    assert metrics["precision"] == 0.5
    assert metrics["recall"] == pytest.approx(2 / 3)
    assert metrics["evaluated_count"] == 2
    assert metrics["excluded_count"] == 1
