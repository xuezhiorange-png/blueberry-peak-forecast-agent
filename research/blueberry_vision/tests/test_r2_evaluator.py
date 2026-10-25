"""Hand-computable independent Golden cases, written before the evaluator."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from research.blueberry_vision.evaluator import (
    bbox_iou,
    compare_reports,
    default_evaluation_config,
    evaluate_predictions,
    match_boxes,
)
from research.blueberry_vision.r2_common import (
    CLASS_LABEL,
    canonical_hash,
    dataset_split_hash,
    seal,
)

JSONDict = dict[str, Any]


def box(x: float, score: float | None = None, *, label: str = CLASS_LABEL) -> JSONDict:
    result: JSONDict = {"bbox_xyxy": [x, 0.0, x + 10.0, 10.0], "class_label": label}
    if score is None:
        result["object_id"] = f"gt-{x}"
    else:
        result["score"] = score
    return result


def data_pair(
    refs: list[list[JSONDict] | None],
    outputs: list[list[JSONDict] | None],
) -> tuple[JSONDict, JSONDict]:
    images: list[JSONDict] = []
    predictions: list[JSONDict] = []
    for index, (gt, pred) in enumerate(zip(refs, outputs, strict=True)):
        image_id = f"image-{index}"
        asset_hash = canonical_hash(image_id)
        images.append(
            {
                "image_id": image_id,
                "SYNTHETIC": True,
                "asset_sha256": asset_hash,
                "split": "test",
                "capture_session_id": f"session-{index}",
                "sampling_unit_id": f"unit-{index}",
                "template_group_id": f"template-{index}",
                "near_duplicate_group_id": f"duplicate-{index}",
                "generation_seed": index,
                "image_width": 100,
                "image_height": 100,
                "gt_status": "missing" if gt is None else "complete",
                "annotation_quality_status": "synthetic_reference",
                "source_authority": {
                    "authority_id": "independent-hand-computed-golden",
                    "source_ref": "test-r2-evaluator/golden-1",
                    "permission_status": "synthetic_only",
                    "allowed_uses": ["test"],
                },
                "objects": gt,
                "visible_count": None if gt is None else len(gt),
                "ignore_regions": [],
                "scene_metadata": {
                    "density": "sparse",
                    "occlusion": "none",
                    "lighting": "normal",
                    "size": "small",
                    "domain": "regular",
                    "empty": gt == [],
                    "scene_type": "golden",
                },
            }
        )
        predictions.append(
            seal(
                {
                    "image_id": image_id,
                    "source_asset_hash": asset_hash,
                    "status": "failed" if pred is None else "ok",
                    "reason_code": "GOLDEN_FAILURE" if pred is None else None,
                    "detected_objects": pred,
                    "predicted_visible_fruit_count": None if pred is None else len(pred),
                },
                "prediction_hash",
            )
        )
    split_hash = dataset_split_hash(images)
    manifest = seal(
        {"SYNTHETIC": True, "images": images, "split_hash": split_hash}, "manifest_hash"
    )
    bundle = seal(
        {
            "schema_version": "blueberry-vision-predictions/2.0.0",
            "SYNTHETIC": True,
            "dataset_manifest_hash": manifest["manifest_hash"],
            "split_hash": split_hash,
            "model_name": "golden-pixel-detector",
            "model_hash": canonical_hash("golden-model"),
            "config_hash": canonical_hash("golden-config"),
            "detector_version": "golden/1.0",
            "images": predictions,
        },
        "prediction_hash",
    )
    return manifest, bundle


def test_iou_independently_computable_overlap_one_third() -> None:
    assert bbox_iou([0, 0, 10, 10], [5, 0, 15, 10]) == pytest.approx(1 / 3)
    assert bbox_iou([0, 0, 10, 10], [10, 0, 20, 10]) == 0
    assert bbox_iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1


@pytest.mark.parametrize("coords", [[0, 0, 0, 2], [2, 0, 1, 2], [0, 0, float("nan"), 2], [0, 0, 1]])
def test_invalid_geometry_fails_closed(coords: list[float]) -> None:
    with pytest.raises(ValueError, match="BBOX"):
        bbox_iou(coords, [0, 0, 2, 2])


def test_matching_confidence_one_to_one_and_duplicate_false_positive() -> None:
    result = match_boxes([box(0), box(20)], [box(0, 0.9), box(0, 0.8), box(20, 0.7)])
    assert (result["tp"], result["fp"], result["fn"]) == (2, 1, 0)
    assert [match["iou"] for match in result["matches"]] == [1, 1]
    assert result["false_positive_indices"] == [1]


def test_wrong_class_does_not_match_and_wrong_image_is_rejected() -> None:
    result = match_boxes([box(0)], [box(0, 0.9, label="DISTRACTOR")])
    assert (result["tp"], result["fp"], result["fn"]) == (0, 1, 1)
    with pytest.raises(ValueError, match="IMAGE_SCOPE"):
        match_boxes([{**box(0), "image_id": "one"}], [{**box(0, 0.9), "image_id": "two"}])


def test_research_ap_ranked_curve_golden_five_sixths() -> None:
    manifest, pred = data_pair([[box(0), box(20)]], [[box(0, 0.9), box(0, 0.8), box(20, 0.7)]])
    report = evaluate_predictions(manifest, pred)
    metric = report["metrics"]
    assert metric["precision"] == pytest.approx(2 / 3)
    assert metric["recall"] == 1
    assert metric["f1"] == pytest.approx(0.8)
    assert metric["bbox_ap50_research_all_points"] == pytest.approx(5 / 6)
    assert "coco_map" not in metric


def test_count_golden_mae_one_bias_zero_with_missing_and_failed_coverage() -> None:
    manifest, pred = data_pair(
        [[box(0), box(20), box(40)], [], None, [box(0)]],
        [[box(0, 0.9), box(20, 0.8)], [box(0, 0.9)], [], None],
    )
    report = evaluate_predictions(manifest, pred)
    assert report["evaluated_count"] == 2
    assert report["excluded_count"] == 2
    assert report["missing_count"] == 1
    assert report["failed_count"] == 1
    assert report["metrics"]["count_mae"] == 1
    assert report["metrics"]["count_bias"] == 0
    assert report["metrics"]["total_overcount"] == 1
    assert report["metrics"]["total_undercount"] == 1
    assert report["metrics"]["empty_false_positive_count"] == 1
    assert report["metrics"]["count_unit"] == "visible_fruit_per_image"
    assert len(report["failure_cases"]) == 4
    assert report["subgroup_metrics"]["empty"]["true"]["count_mae"] == 1
    assert report["subgroup_metrics"]["density"]["dense"]["count_mae"] is None


def test_empty_images_and_no_predictions_have_explicit_null_semantics() -> None:
    manifest, pred = data_pair([[]], [[]])
    report = evaluate_predictions(manifest, pred)
    assert report["metrics"]["count_mae"] == 0
    assert report["metrics"]["precision"] is None
    assert report["metrics"]["recall"] is None
    assert report["metrics"]["bbox_ap50_research_all_points"] is None
    manifest, pred = data_pair([[box(0)]], [[]])
    metric = evaluate_predictions(manifest, pred)["metrics"]
    assert metric["precision"] is None
    assert metric["recall"] == 0
    assert metric["bbox_ap50_research_all_points"] == 0


def test_no_evaluable_gt_is_not_zero_error() -> None:
    manifest, pred = data_pair([None], [[]])
    metric = evaluate_predictions(manifest, pred)["metrics"]
    assert metric["status"] == "NOT_EVALUABLE"
    assert metric["reason_code"] == "NO_EVALUABLE_IMAGES"
    assert metric["count_mae"] is None
    assert metric["count_bias"] is None


def test_ignore_only_prediction_not_detection_fp_still_raw_count_error() -> None:
    manifest, pred = data_pair([[]], [[box(0, 0.9)]])
    manifest["images"][0]["ignore_regions"] = [[0, 0, 10, 10]]
    manifest = seal(manifest, "manifest_hash")
    pred["dataset_manifest_hash"] = manifest["manifest_hash"]
    pred = seal(pred, "prediction_hash")
    report = evaluate_predictions(manifest, pred)
    assert report["metrics"]["fp"] == 0
    assert report["metrics"]["count_mae"] == 1
    assert report["per_image_results"][0]["ignored_prediction_indices"] == [0]


def test_more_than_one_hundred_targets_are_not_truncated() -> None:
    gt = [box(float(index * 20)) for index in range(101)]
    manifest, pred = data_pair([gt], [[box(float(i * 20), 0.9) for i in range(101)]])
    manifest["images"][0]["image_width"] = 2020
    manifest = seal(manifest, "manifest_hash")
    pred["dataset_manifest_hash"] = manifest["manifest_hash"]
    pred = seal(pred, "prediction_hash")
    report = evaluate_predictions(manifest, pred)
    assert report["metrics"]["tp"] == 101
    assert report["metrics"]["bbox_ap50_research_all_points"] == 1
    assert report["evaluator_config"]["max_detections"] is None


@pytest.mark.parametrize("mutate", ["hash", "asset", "count", "duplicate_id", "extra_id"])
def test_binding_and_record_integrity_rejects_manipulation(mutate: str) -> None:
    manifest, pred = data_pair([[box(0)]], [[box(0, 0.9)]])
    if mutate == "hash":
        pred["images"][0]["detected_objects"][0]["score"] = 0.2
    elif mutate == "asset":
        pred["images"][0]["source_asset_hash"] = canonical_hash("different")
    elif mutate == "count":
        pred["images"][0]["predicted_visible_fruit_count"] = 0
    elif mutate == "duplicate_id":
        pred["images"].append(deepcopy(pred["images"][0]))
    else:
        pred["images"][0]["image_id"] = "unknown-image"
    if mutate != "hash":
        pred["images"] = [seal(image, "prediction_hash") for image in pred["images"]]
        pred = seal(pred, "prediction_hash")
    with pytest.raises(ValueError):
        evaluate_predictions(manifest, pred)


def test_hashes_deterministic_and_configuration_changes_evaluator_hash() -> None:
    manifest, pred = data_pair([[box(0)]], [[box(0, 0.9)]])
    first = evaluate_predictions(manifest, pred)
    assert first["report_hash"] == evaluate_predictions(manifest, pred)["report_hash"]
    config = default_evaluation_config()
    config["iou_threshold"] = 0.75
    assert (
        first["evaluator_config_hash"]
        != evaluate_predictions(manifest, pred, config=config)["evaluator_config_hash"]
    )


def test_comparison_uses_common_reference_rows_and_reports_negative_delta() -> None:
    manifest, first = data_pair([[box(0)]], [[box(0, 0.9)]])
    _, second = data_pair([[box(0)]], [[]])
    a = evaluate_predictions(manifest, first)
    b = evaluate_predictions(manifest, second)
    comparison = compare_reports(a, b)
    assert comparison["common_evaluated_count"] == 1
    assert comparison["paired_count_mae_delta_candidate_minus_baseline"] == 1
    b["per_image_results"][0]["status"] = "MISSING_PREDICTION"
    b["per_image_results"][0]["signed_count_error"] = None
    b["per_image_results"][0]["absolute_count_error"] = None
    b = seal(b, "report_hash")
    coverage = compare_reports(a, b)
    assert coverage["common_evaluated_count"] == 0
    assert coverage["paired_count_mae_delta_candidate_minus_baseline"] is None
    assert coverage["baseline_available_candidate_missing"] == ["image-0"]


@pytest.mark.parametrize("invalid", [["sparse"], {"value": "sparse"}, 12, None])
def test_malformed_scene_dimension_has_stable_reason(invalid: object) -> None:
    manifest, pred = data_pair([[box(0)]], [[box(0, 0.9)]])
    manifest["images"][0]["scene_metadata"]["density"] = invalid
    manifest = seal(manifest, "manifest_hash")
    pred["dataset_manifest_hash"] = manifest["manifest_hash"]
    pred = seal(pred, "prediction_hash")
    with pytest.raises(ValueError, match="SCENE_METADATA_DIMENSION_INVALID"):
        evaluate_predictions(manifest, pred)


def test_prediction_image_scope_and_declared_scope_hash_are_validated() -> None:
    manifest, pred = data_pair([[box(0)]], [[box(0, 0.9)]])
    pred["images"][0]["detected_objects"][0]["image_id"] = "unrelated"
    pred["images"][0] = seal(pred["images"][0], "prediction_hash")
    pred = seal(pred, "prediction_hash")
    with pytest.raises(ValueError, match="BOX_IMAGE_SCOPE_MISMATCH"):
        evaluate_predictions(manifest, pred)
    manifest, pred = data_pair([[box(0)]], [[box(0, 0.9)]])
    pred["prediction_scope_hash"] = canonical_hash("wrong-scope")
    pred = seal(pred, "prediction_hash")
    with pytest.raises(ValueError, match="PREDICTION_SCOPE_HASH_MISMATCH"):
        evaluate_predictions(manifest, pred)


@pytest.mark.parametrize("score", [float("nan"), float("inf"), True, "0.9", -0.1, 1.1])
def test_invalid_detection_scores_rejected(score: object) -> None:
    gt = box(0)
    pred = box(0, 0.9)
    pred["score"] = score
    with pytest.raises(ValueError, match="PREDICTION_SCORE_INVALID"):
        match_boxes([gt], [pred])


def test_inference_failure_and_missing_gt_both_coverage_flags_preserved() -> None:
    manifest, pred = data_pair([None], [None])
    report = evaluate_predictions(manifest, pred)
    assert report["evaluated_count"] == 0
    assert report["excluded_count"] == 1
    assert report["missing_count"] == 1
    assert report["failed_count"] == 1
    row = report["per_image_results"][0]
    assert row["inference_status"] == "failed"
    assert row["inference_reason_code"] == "GOLDEN_FAILURE"


def test_subgroups_retain_missing_coverage_and_count_errors() -> None:
    manifest, pred = data_pair([[box(0)], []], [[], [box(0, 0.9), box(20, 0.8)]])
    manifest["images"][1]["scene_metadata"].update(density="dense", occlusion="high")
    manifest = seal(manifest, "manifest_hash")
    pred["dataset_manifest_hash"] = manifest["manifest_hash"]
    pred = seal(pred, "prediction_hash")
    report = evaluate_predictions(manifest, pred)
    assert report["metrics"]["count_mae"] == 1.5
    assert report["metrics"]["count_bias"] == 0.5
    assert report["subgroup_metrics"]["density"]["sparse"]["count_mae"] == 1
    assert report["subgroup_metrics"]["density"]["dense"]["count_mae"] == 2
    assert report["subgroup_metrics"]["occlusion"]["high"]["count_bias"] == 2


def test_ap_global_ranking_does_not_match_gt_from_another_image() -> None:
    manifest, pred = data_pair([[box(0)], [box(20)]], [[box(20, 0.9)], [box(20, 0.8), box(0, 0.7)]])
    metric = evaluate_predictions(manifest, pred)["metrics"]
    assert (metric["tp"], metric["fp"], metric["fn"]) == (1, 2, 1)
    assert metric["bbox_ap50_research_all_points"] == pytest.approx(0.25)


@pytest.mark.parametrize("mutation", ["real", "pred_as_gt", "unlicensed", "wrong_use"])
def test_reference_provenance_cannot_be_upgraded_by_manifest_hash(mutation: str) -> None:
    manifest, pred = data_pair([[box(0)]], [[box(0, 0.9)]])
    record = manifest["images"][0]
    if mutation == "real":
        record["SYNTHETIC"] = False
    elif mutation == "pred_as_gt":
        record["annotation_quality_status"] = "model_prediction"
    elif mutation == "unlicensed":
        record["source_authority"]["permission_status"] = "unknown"
    else:
        record["source_authority"]["allowed_uses"] = ["train"]
    manifest = seal(manifest, "manifest_hash")
    pred["dataset_manifest_hash"] = manifest["manifest_hash"]
    pred = seal(pred, "prediction_hash")
    with pytest.raises(ValueError, match="SYNTHETIC_REFERENCE|REFERENCE_SOURCE"):
        evaluate_predictions(manifest, pred)
