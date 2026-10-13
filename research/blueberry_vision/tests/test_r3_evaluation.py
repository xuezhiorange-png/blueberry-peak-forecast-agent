"""Independent hand-computable metric goldens and frozen R2 adapter contracts."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image, ImageDraw

from research.blueberry_vision.r2_common import canonical_hash, seal, verify_seal
from research.blueberry_vision.r3.evaluation import (
    CANDIDATE_LABEL,
    _coco_metrics,
    compact_metrics,
    default_adapter_config,
    evaluate_real,
    freeze_r2_baselines,
    match_reference,
    research_ap50,
    resize_for_inference,
    run_real_inference,
    validate_freeze,
)
from research.blueberry_vision.r3.ingestion import import_images
from research.blueberry_vision.r3.splits import append_exposure_event, build_split, seal_test


def box(coords: list[float], score: float = 1.0) -> dict[str, object]:
    return {"bbox_xyxy": coords, "class_label": CANDIDATE_LABEL, "score": score}


def test_one_to_one_duplicate_prediction_golden() -> None:
    gt = [box([0, 0, 10, 10])]
    pred = [box([0, 0, 10, 10], 0.9), box([0, 0, 10, 10], 0.8)]
    result = match_reference(gt, pred)
    assert (result["tp"], result["fp"], result["fn"]) == (1, 1, 0)
    assert result["matches"][0]["iou"] == 1.0


def test_ap_tp_fp_tp_is_five_sixths() -> None:
    truths = {"x": [box([0, 0, 10, 10]), box([20, 0, 30, 10])]}
    predictions = {
        "x": [box([0, 0, 10, 10], 0.9), box([40, 0, 50, 10], 0.8), box([20, 0, 30, 10], 0.7)]
    }
    assert research_ap50(truths, predictions) == pytest.approx(5 / 6)


def test_ap_cannot_match_another_image() -> None:
    truths = {"a": [box([0, 0, 10, 10])], "b": []}
    predictions = {"a": [], "b": [box([0, 0, 10, 10])]}
    assert research_ap50(truths, predictions) == 0.0


def test_ap_missing_support_is_null() -> None:
    assert research_ap50({"a": []}, {"a": [box([0, 0, 10, 10])]}) is None
    assert research_ap50({}, {}) is None


def test_count_mae_bias_hand_golden() -> None:
    rows = []
    for index, (reference, predicted) in enumerate(((3, 1), (2, 5), (2, 1))):
        error = predicted - reference
        rows.append(
            {
                "image_id": str(index),
                "status": "EVALUATED",
                "reference_count": reference,
                "predicted_count": predicted,
                "signed_count_error": error,
                "absolute_count_error": abs(error),
                "tp": min(reference, predicted),
                "fp": max(error, 0),
                "fn": max(-error, 0),
            }
        )
    result = compact_metrics(rows)
    assert result["count_mae"] == 2
    assert result["count_bias"] == 0
    assert result["total_overcount"] == result["total_undercount"] == 3
    assert result["precision"] == pytest.approx(4 / 7)
    assert result["recall"] == pytest.approx(4 / 7)


def test_missing_gt_remains_null_not_zero() -> None:
    result = compact_metrics(
        [{"image_id": "missing", "status": "NOT_EVALUABLE", "reason_codes": ["GT_MISSING"]}]
    )
    for key in ("tp", "fp", "fn", "count_mae", "count_bias", "precision", "recall", "f1"):
        assert result[key] is None
    assert result["evaluated_count"] == 0
    assert result["missing_count"] == 1
    assert result["status"] == "NOT_EVALUABLE"


def test_true_zero_with_false_prediction_is_evaluable() -> None:
    metrics = compact_metrics(
        [
            {
                "status": "EVALUATED",
                "reference_count": 0,
                "predicted_count": 2,
                "signed_count_error": 2,
                "absolute_count_error": 2,
                "tp": 0,
                "fp": 2,
                "fn": 0,
            }
        ]
    )
    assert metrics["count_mae"] == metrics["count_bias"] == 2
    assert metrics["precision"] == 0
    assert metrics["recall"] is None
    assert metrics["empty_image_false_positives"] == 2


def test_ignore_region_does_not_remove_raw_predicted_count() -> None:
    matched = match_reference([], [box([0, 0, 10, 10])], [[0, 0, 10, 10]])
    assert matched["fp"] == 0
    assert matched["ignored_prediction_indices"] == [0]


def test_resize_registered_and_original_geometry() -> None:
    rgb = np.zeros((2301, 2043, 3), dtype=np.uint8)
    resized, metadata = resize_for_inference(rgb, default_adapter_config())
    assert resized.shape == (1280, 1136, 3)
    assert metadata["scale_x_to_original"] == pytest.approx(2043 / 1136)
    assert metadata["scale_y_to_original"] == pytest.approx(2301 / 1280)
    assert metadata["resized"] is True


def test_small_images_never_upscaled() -> None:
    rgb = np.zeros((10, 20, 3), dtype=np.uint8)
    output, metadata = resize_for_inference(rgb, default_adapter_config())
    assert np.array_equal(rgb, output)
    assert metadata["resized"] is False


def test_freeze_stable_independent_of_output_path(tmp_path: Path) -> None:
    first = freeze_r2_baselines(tmp_path / "a.json")
    second = freeze_r2_baselines(tmp_path / "b.json")
    assert first == second
    assert verify_seal(first, "freeze_hash")
    assert first["models"]["B"]["model_artifact_sha256"] == (
        "b685ff32fac8542e3f50bbbb5f5a1b09d2319114ce14af17078de06ac9482b10"
    )
    assert first["training_data_hash"] == (
        "a92c8c9a9f8228ccd4273ccbd249fc68ce4e8d48eeed5783bca510ae57ec4edb"
    )
    validate_freeze(first)


def test_resealed_parameter_tampering_rejected() -> None:
    frozen = deepcopy(freeze_r2_baselines())
    frozen["frozen_configs"]["A"]["minimum_color_difference"] = 0
    frozen["config_hash"] = canonical_hash(
        {"configs": frozen["frozen_configs"], "adapter": frozen["adapter_config"]}
    )
    frozen = seal(frozen, "freeze_hash")
    with pytest.raises(ValueError, match="R2_BASELINE_CONFIG_CHANGED"):
        validate_freeze(frozen)


def test_test_tunable_resize_adapter_rejected() -> None:
    config = default_adapter_config()
    config["maximum_edge"] = 640
    with pytest.raises(ValueError, match="ADAPTER_CONFIG_NOT_PREREGISTERED"):
        freeze_r2_baselines(adapter_config=config)


@pytest.fixture
def fixture_dataset(tmp_path: Path) -> tuple[dict[str, Any], Path]:
    """Synthetic engineering pixels, never a real-photo accuracy fixture."""
    root = tmp_path / "assets"
    root.mkdir()
    pixels = Image.new("RGB", (64, 48), (50, 100, 40))
    ImageDraw.Draw(pixels).rectangle((10, 12, 19, 23), fill=(30, 50, 180))
    pixels.save(root / "pixel_fixture.png")
    from research.blueberry_vision.r2_common import file_hash

    source = {
        "source_id": "local-engineering-fixture",
        "purpose": "SYNTHETIC_ENGINEERING",
        "SYNTHETIC": True,
        "license_id": "LOCAL_SYNTHETIC_FIXTURE",
        "license_url": "https://example.invalid/synthetic-fixture-only",
        "license_status": "SYNTHETIC_AUTHORITY",
        "research_use": True,
        "model_training": False,
        "redistribution": True,
    }
    index = {
        "dataset_id": "synthetic-adapter-fixture",
        "dataset_version": "1",
        "purpose": "SYNTHETIC_ENGINEERING",
        "SYNTHETIC": True,
        "images": [
            {
                "image_id": "pixel-one",
                "source_id": source["source_id"],
                "asset_ref": "pixel_fixture.png",
                "asset_sha256": file_hash(root / "pixel_fixture.png"),
            }
        ],
    }
    return import_images(root, index, {"sources": [source]}, tmp_path / "imported"), root


def test_real_adapter_inference_is_pixels_not_gt(
    fixture_dataset: tuple[dict[str, Any], Path],
) -> None:
    dataset, root = fixture_dataset
    result = run_real_inference(dataset, root, freeze_r2_baselines())
    row = result["images"][0]
    assert row["status"] == "ok"
    assert row["predicted_visible_fruit_count"] == 1
    assert row["detected_objects"][0]["bbox_xyxy"] == [10, 12, 20, 24]
    assert row["detected_objects"][0]["class_label"] == CANDIDATE_LABEL
    assert (
        row["detected_objects"][0]["original_detector_class_label"] == "SYNTHETIC_BLUEBERRY_VISIBLE"
    )
    assert result["gt_consumed"] is False
    assert result["purpose"] == "SYNTHETIC_ENGINEERING" and result["SYNTHETIC"] is True


def test_unchanged_trained_r2_model_reads_fixture_bytes(
    fixture_dataset: tuple[dict[str, Any], Path],
) -> None:
    dataset, root = fixture_dataset
    freeze = freeze_r2_baselines()
    result = run_real_inference(dataset, root, freeze, model_key="B")
    assert result["images"][0]["status"] == "ok"
    assert result["selected_model_hash"] == freeze["models"]["B"]["model_hash"]
    assert result["training_data_hash"] == freeze["training_data_hash"]
    assert result["images"][0]["detected_objects"]


def test_actual_pixel_change_changes_prediction(
    fixture_dataset: tuple[dict[str, Any], Path], tmp_path: Path
) -> None:
    dataset, root = fixture_dataset
    first = run_real_inference(dataset, root, freeze_r2_baselines())
    Image.new("RGB", (64, 48), (100, 100, 100)).save(root / "blank.png")
    from research.blueberry_vision.r2_common import file_hash

    source = dataset["sources"][0]
    index = {
        "dataset_id": "blank",
        "dataset_version": "1",
        "purpose": "SYNTHETIC_ENGINEERING",
        "SYNTHETIC": True,
        "images": [
            {
                "image_id": "blank",
                "source_id": source["source_id"],
                "asset_ref": "blank.png",
                "asset_sha256": file_hash(root / "blank.png"),
            }
        ],
    }
    blank = import_images(root, index, {"sources": [source]}, tmp_path / "blank-import")
    second = run_real_inference(blank, root, freeze_r2_baselines())
    assert first["images"][0]["predicted_visible_fruit_count"] == 1
    assert second["images"][0]["predicted_visible_fruit_count"] == 0


def test_missing_gt_reports_no_real_accuracy(fixture_dataset: tuple[dict[str, Any], Path]) -> None:
    dataset, root = fixture_dataset
    freeze = freeze_r2_baselines()
    predictions = run_real_inference(dataset, root, freeze)
    report = evaluate_real(
        dataset,
        predictions,
        None,
        build_split(dataset, {"pixel-one": "TEST"}),
        freeze=freeze,
        run_coco=True,
    )
    assert report["status"] == "NOT_EVALUABLE"
    assert "GT_MISSING" in report["reason_codes"]
    assert report["per_image_results"][0]["reference_count"] is None
    assert report["per_image_results"][0]["predicted_count"] == 1
    assert report["metrics"]["count_mae"] is None
    assert report["metrics"]["RESEARCH_AP50"] is None
    assert report["coco"]["status"] == "NOT_EVALUABLE"
    assert report["COCO_MAP50"] is report["COCO_MAP50_95"] is None


def test_inference_no_ground_truth_argument() -> None:
    import inspect

    assert not {"gt", "annotations", "objects", "reference_count"} & set(
        inspect.signature(run_real_inference).parameters
    )


def test_model_and_source_identity_tampering_rejected(
    fixture_dataset: tuple[dict[str, Any], Path],
) -> None:
    dataset, root = fixture_dataset
    freeze = freeze_r2_baselines()
    predictions = run_real_inference(dataset, root, freeze)
    predictions["selected_model_hash"] = "f" * 64
    predictions = seal(predictions, "prediction_hash")
    with pytest.raises(ValueError, match="PREDICTION_FROZEN_IDENTITY_MISMATCH"):
        evaluate_real(dataset, predictions, None, freeze=freeze)


def test_source_domains_cannot_be_aggregated(fixture_dataset: tuple[dict[str, Any], Path]) -> None:
    dataset, root = fixture_dataset
    freeze = freeze_r2_baselines()
    predictions = run_real_inference(dataset, root, freeze)
    predictions["purpose"] = "PUBLIC_EXTERNAL_BENCHMARK"
    predictions["SYNTHETIC"] = False
    predictions = seal(predictions, "prediction_hash")
    with pytest.raises(ValueError, match="PREDICTION_DATASET_OR_PURPOSE_MISMATCH"):
        evaluate_real(dataset, predictions, None, freeze=freeze)


def test_missing_gt_cannot_enter_legacy_r2_evaluator(
    fixture_dataset: tuple[dict[str, Any], Path],
) -> None:
    dataset, root = fixture_dataset
    result = run_real_inference(dataset, root, freeze_r2_baselines())
    assert result["schema_version"] == "blueberry-vision-r3-predictions/3.0.0"
    assert "SYNTHETIC_BLUEBERRY_VISIBLE" not in [
        b["class_label"] for b in result["images"][0]["detected_objects"]
    ]


def test_optional_official_coco_perfect_golden() -> None:
    pytest.importorskip("pycocotools")
    truth = {"a": [box([0, 0, 10, 10]), box([20, 0, 30, 10])]}
    images = {"a": {"image_width": 64, "image_height": 48}}
    snapshots = {"a": {"objects": [{**target, "disposition": "TARGET"} for target in truth["a"]]}}
    result = _coco_metrics(images, truth, truth, snapshots)
    assert result["status"] == "EVALUATED"
    assert result["COCO_MAP50"] == pytest.approx(1)
    assert result["COCO_MAP50_95"] == pytest.approx(1)
    assert result["maxDets"] == [1, 10, 100]


def test_optional_official_coco_all_missed_golden() -> None:
    pytest.importorskip("pycocotools")
    truth = {"a": [box([0, 0, 10, 10])]}
    images = {"a": {"image_width": 64, "image_height": 48}}
    snapshots = {"a": {"objects": [{**target, "disposition": "TARGET"} for target in truth["a"]]}}
    result = _coco_metrics(images, truth, {"a": []}, snapshots)
    assert result["COCO_MAP50"] == result["COCO_MAP50_95"] == 0


def test_official_coco_unsupported_ignore_semantics_not_silently_scored() -> None:
    pytest.importorskip("pycocotools")
    truth = {"a": [box([0, 0, 10, 10])]}
    result = _coco_metrics({"a": {}}, truth, truth, {"a": {"objects": [{"disposition": "IGNORE"}]}})
    assert result["status"] == "NOT_RUN"
    assert result["COCO_MAP50"] is None
    assert result["reason_code"] == "COCO_IGNORE_GT_POLICY_UNSUPPORTED"


def simulated_reference(dataset: dict[str, Any], image_id: str | None = None) -> dict[str, Any]:
    """A fully labelled simulated workbench flow for engineering-only acceptance."""
    from research.blueberry_vision.r3.annotations import (
        adjudicate_annotations,
        annotation_bundle,
        create_draft,
        transition_review,
    )

    image = next(
        (row for row in dataset["images"] if row["image_id"] == image_id), dataset["images"][0]
    )
    # Manual fixed rectangle equals the painted raster's half-open boundary.
    # This is an independent known geometry, never boxes copied from inference.
    targets: list[dict[str, Any]] = [
        {
            "object_id": "fixture-target",
            "class_label": CANDIDATE_LABEL,
            "bbox_xyxy": [10, 12, 20, 24],
            "disposition": "TARGET",
        }
    ]
    versions: list[dict[str, Any]] = []
    for name in ("operator-a", "operator-b"):
        snapshot = create_draft(
            image,
            annotation_version=f"draft-{name}",
            annotator_id=name,
            objects=targets,
            workflow_mode="SIMULATED_ENGINEERING",
        )
        snapshot = transition_review(snapshot, "SUBMITTED", actor_id=name)
        versions.append(transition_review(snapshot, "REVIEW_PENDING", actor_id=name))
    adjudicated = adjudicate_annotations(
        versions[0],
        versions[1],
        targets,
        adjudicator_id="simulated-arbiter",
        annotation_version="simulated-reference-v1",
    )
    sealed = transition_review(adjudicated, "SEALED", actor_id="simulated-arbiter")
    return annotation_bundle(dataset, [sealed])


def test_full_sealed_engineering_eval_with_ledger_and_independent_geometry(
    fixture_dataset: tuple[dict[str, Any], Path],
    tmp_path: Path,
) -> None:
    dataset, root = fixture_dataset
    frozen = freeze_r2_baselines(tmp_path / "freeze.json")
    ledger = tmp_path / "ledger"
    append_exposure_event(ledger, "CONFIG_FROZEN", {"freeze_hash": frozen["freeze_hash"]})
    predictions = run_real_inference(
        dataset, root, frozen, output_path=tmp_path / "predictions.json", ledger_dir=ledger
    )
    annotations = simulated_reference(dataset)
    split = build_split(dataset, {"pixel-one": "TEST"})
    sealed = seal_test(dataset, split, annotations, frozen, ledger=ledger)
    assert sealed["status"] == "SEALED_RESEARCH_INTEGRITY"
    report = evaluate_real(
        dataset,
        predictions,
        annotations,
        split,
        sealed,
        freeze=frozen,
        ledger=ledger,
        run_coco=True,
    )
    assert report["status"] == "EVALUATED", report["reason_codes"]
    assert report["metrics"]["tp"] == 1
    assert report["metrics"]["fp"] == report["metrics"]["fn"] == 0
    assert report["metrics"]["precision"] == report["metrics"]["recall"] == 1
    assert report["metrics"]["count_mae"] == report["metrics"]["count_bias"] == 0
    assert report["metrics"]["RESEARCH_AP50"] == 1
    from importlib.util import find_spec

    if find_spec("pycocotools") is not None:
        assert report["COCO_MAP50"] == pytest.approx(1)
    else:
        assert report["coco"]["status"] == "NOT_RUN"
        assert report["coco"]["reason_code"] == "PYCOCOTOOLS_NOT_INSTALLED"
        assert report["COCO_MAP50"] is None
    assert report["SYNTHETIC"] is True
    assert report["evaluation_scope"] == "SYNTHETIC_ENGINEERING"


def test_no_ledger_no_seal_cannot_claim_accuracy(
    fixture_dataset: tuple[dict[str, Any], Path],
) -> None:
    dataset, root = fixture_dataset
    frozen = freeze_r2_baselines()
    predictions = run_real_inference(dataset, root, frozen)
    annotations = simulated_reference(dataset)
    report = evaluate_real(
        dataset,
        predictions,
        annotations,
        build_split(dataset, {"pixel-one": "TEST"}),
        freeze=frozen,
    )
    assert report["status"] == "NOT_EVALUABLE"
    assert "TEST_SEAL_REQUIRED" in report["reason_codes"]
    assert "EXPOSURE_LEDGER_REQUIRED" in report["reason_codes"]
    assert report["metrics"]["precision"] is None


def test_rescaled_reference_boxes_never_used_to_predict(
    fixture_dataset: tuple[dict[str, Any], Path],
) -> None:
    dataset, root = fixture_dataset
    first = run_real_inference(dataset, root, freeze_r2_baselines())
    # A separate candidate snapshot with wrong geometry cannot enter the asset
    # contract or change the already fixed pixel-only prediction.
    annotations = simulated_reference(dataset)
    annotations["snapshots"][0]["objects"][0]["bbox_xyxy"] = [0, 0, 5, 5]
    second = run_real_inference(dataset, root, freeze_r2_baselines())
    assert first["prediction_hash"] == second["prediction_hash"]


@pytest.mark.parametrize(
    "field,value", [("predicted_visible_fruit_count", -1), ("detected_objects", [])]
)
def test_prediction_count_invalid_even_without_gt(
    fixture_dataset: tuple[dict[str, Any], Path],
    field: str,
    value: object,
) -> None:
    dataset, root = fixture_dataset
    frozen = freeze_r2_baselines()
    predictions = run_real_inference(dataset, root, frozen)
    predictions["images"][0][field] = value
    predictions["images"][0] = seal(predictions["images"][0], "prediction_hash")
    predictions = seal(predictions, "prediction_hash")
    with pytest.raises(ValueError, match="PREDICTION_COUNT_OR_OBJECTS_INVALID"):
        evaluate_real(dataset, predictions, None, freeze=frozen)


def test_prediction_out_of_bounds_invalid_without_gt(
    fixture_dataset: tuple[dict[str, Any], Path],
) -> None:
    dataset, root = fixture_dataset
    frozen = freeze_r2_baselines()
    predictions = run_real_inference(dataset, root, frozen)
    predictions["images"][0]["detected_objects"][0]["bbox_xyxy"] = [0, 0, 1000, 1000]
    predictions["images"][0] = seal(predictions["images"][0], "prediction_hash")
    predictions = seal(predictions, "prediction_hash")
    with pytest.raises(ValueError, match="BBOX_IMAGE_BOUNDARY"):
        evaluate_real(dataset, predictions, None, freeze=frozen)


def test_decoding_failure_does_not_become_zero(
    fixture_dataset: tuple[dict[str, Any], Path],
) -> None:
    dataset, root = fixture_dataset
    frozen = freeze_r2_baselines()
    (root / "pixel_fixture.png").write_bytes(b"corrupt authorized fixture bytes")
    predictions = run_real_inference(dataset, root, frozen)
    row = predictions["images"][0]
    assert row["status"] == "failed" and row["reason_code"] == "ASSET_HASH_MISMATCH"
    assert row["predicted_visible_fruit_count"] is None
    report = evaluate_real(dataset, predictions, None, freeze=frozen)
    assert report["metrics"]["failed_count"] == 1
    assert report["metrics"]["count_mae"] is None


def test_absent_strata_are_not_fabricated_zero_errors(
    fixture_dataset: tuple[dict[str, Any], Path],
) -> None:
    dataset, root = fixture_dataset
    frozen = freeze_r2_baselines()
    report = evaluate_real(dataset, run_real_inference(dataset, root, frozen), None, freeze=frozen)
    for dimension, value in (("density", "dense"), ("occlusion", "high"), ("lighting", "glare")):
        metrics = report["subgroup_metrics"][dimension][value]
        assert metrics["status"] == "NOT_EVALUABLE"
        assert metrics["count_mae"] is None
        assert metrics["evaluated_count"] == 0


def test_wrong_gt_source_id_does_not_pass_via_resealed_hash(
    fixture_dataset: tuple[dict[str, Any], Path],
) -> None:
    dataset, root = fixture_dataset
    annotations = simulated_reference(dataset)
    annotations["snapshots"][0]["source_id"] = "wrong-source"
    annotations["snapshots"][0] = seal(annotations["snapshots"][0], "snapshot_hash")
    annotations = seal(annotations, "annotations_hash")
    frozen = freeze_r2_baselines()
    with pytest.raises(ValueError, match="IMAGE_ASSET_MISMATCH"):
        evaluate_real(
            dataset, run_real_inference(dataset, root, frozen), annotations, freeze=frozen
        )


def test_train_validation_cannot_be_scored_under_a_test_seal(
    fixture_dataset: tuple[dict[str, Any], Path],
    tmp_path: Path,
) -> None:
    from research.blueberry_vision.r2_common import file_hash
    from research.blueberry_vision.r3.annotations import annotation_bundle

    original, root = fixture_dataset
    source = original["sources"][0]
    index: dict[str, Any] = {
        "dataset_id": "mixed-scope-fixture",
        "dataset_version": "1",
        "purpose": "SYNTHETIC_ENGINEERING",
        "SYNTHETIC": True,
        "images": [],
    }
    # All three are distinct pixel drawings; no identical-image leakage is waived.
    for number, name in enumerate(("train", "validation", "test")):
        pixels = Image.new("RGB", (64, 48), (50 + number, 100, 40))
        ImageDraw.Draw(pixels).rectangle((10, 12, 19, 23), fill=(30, 50, 180))
        pixels.save(root / f"{name}.png")
        index["images"].append(
            {
                "image_id": name,
                "source_id": source["source_id"],
                "asset_ref": f"{name}.png",
                "asset_sha256": file_hash(root / f"{name}.png"),
            }
        )
    dataset = import_images(root, index, {"sources": [source]}, tmp_path / "mixed-import")
    frozen = freeze_r2_baselines()
    ledger = tmp_path / "scope-ledger"
    append_exposure_event(ledger, "CONFIG_FROZEN", {"freeze_hash": frozen["freeze_hash"]})
    predictions = run_real_inference(
        dataset, root, frozen, output_path=tmp_path / "scope-predictions.json", ledger_dir=ledger
    )
    snapshots = [
        simulated_reference(dataset, name)["snapshots"][0]
        for name in ("train", "validation", "test")
    ]
    annotations = annotation_bundle(dataset, snapshots)
    split = build_split(dataset, {"train": "TRAIN", "validation": "VALIDATION", "test": "TEST"})
    sealed = seal_test(dataset, split, annotations, frozen, ledger=ledger)
    report = evaluate_real(
        dataset, predictions, annotations, split, sealed, freeze=frozen, ledger=ledger
    )
    rows = {row["image_id"]: row for row in report["per_image_results"]}
    assert rows["test"]["status"] == "EVALUATED"
    for name in ("train", "validation"):
        assert rows[name]["status"] == "NOT_EVALUABLE"
        assert rows[name]["reference_count"] is None
        assert "NOT_IN_EVALUATION_SPLIT" in rows[name]["reason_codes"]
        assert rows[name]["tp"] is None
    assert report["metrics"]["evaluated_count"] == 1
    assert report["metrics"]["excluded_count"] == 2
    assert report["evaluation_image_ids"] == ["test"]


def test_unstructured_scene_metadata_remains_unknown(
    fixture_dataset: tuple[dict[str, Any], Path],
) -> None:
    dataset, root = fixture_dataset
    dataset["images"][0]["scene_metadata"] = {
        "density": ["not-a-confirmed-stratum"],
        "occlusion": {"unknown": True},
    }
    dataset["images"][0] = seal(dataset["images"][0], "record_hash")
    dataset = seal(dataset, "manifest_hash")
    frozen = freeze_r2_baselines()
    report = evaluate_real(dataset, run_real_inference(dataset, root, frozen), None, freeze=frozen)
    assert report["subgroup_metrics"]["density"]["UNKNOWN"]["excluded_count"] == 1
    assert report["subgroup_metrics"]["occlusion"]["UNKNOWN"]["excluded_count"] == 1


def test_omitted_sealed_test_prediction_is_visible_not_silently_dropped(
    fixture_dataset: tuple[dict[str, Any], Path],
    tmp_path: Path,
) -> None:
    from research.blueberry_vision.r2_common import file_hash
    from research.blueberry_vision.r3.annotations import annotation_bundle

    original, root = fixture_dataset
    source = original["sources"][0]
    pixels = Image.new("RGB", (64, 48), (80, 110, 40))
    ImageDraw.Draw(pixels).rectangle((10, 12, 19, 23), fill=(30, 50, 180))
    pixels.save(root / "second.png")
    index = {
        "dataset_id": "two-tests",
        "dataset_version": "1",
        "purpose": "SYNTHETIC_ENGINEERING",
        "SYNTHETIC": True,
        "images": [
            {
                "image_id": "pixel-one",
                "source_id": source["source_id"],
                "asset_ref": "pixel_fixture.png",
                "asset_sha256": file_hash(root / "pixel_fixture.png"),
            },
            {
                "image_id": "pixel-two",
                "source_id": source["source_id"],
                "asset_ref": "second.png",
                "asset_sha256": file_hash(root / "second.png"),
            },
        ],
    }
    dataset = import_images(root, index, {"sources": [source]}, tmp_path / "two-tests-import")
    frozen = freeze_r2_baselines()
    ledger = tmp_path / "missing-ledger"
    append_exposure_event(ledger, "CONFIG_FROZEN", {"freeze_hash": frozen["freeze_hash"]})
    predictions = run_real_inference(
        dataset,
        root,
        frozen,
        image_ids=["pixel-one"],
        output_path=tmp_path / "missing-pred.json",
        ledger_dir=ledger,
    )
    annotations = annotation_bundle(
        dataset,
        [simulated_reference(dataset, name)["snapshots"][0] for name in ("pixel-one", "pixel-two")],
    )
    split = build_split(dataset, {"pixel-one": "TEST", "pixel-two": "OUT_OF_DOMAIN"})
    sealed = seal_test(dataset, split, annotations, frozen, ledger=ledger)
    report = evaluate_real(
        dataset, predictions, annotations, split, sealed, freeze=frozen, ledger=ledger
    )
    rows = {row["image_id"]: row for row in report["per_image_results"]}
    assert set(rows) == {"pixel-one", "pixel-two"}
    assert rows["pixel-two"]["predicted_count"] is None
    assert "PREDICTION_MISSING" in rows["pixel-two"]["reason_codes"]
    assert {row["image_id"] for row in report["failure_cases"]} == {"pixel-one", "pixel-two"}
    assert report["status"] == "NOT_EVALUABLE"
    assert report["metrics"]["precision"] is None
    assert report["metrics"]["missing_prediction_count"] == 1
    assert report["metrics"]["excluded_count"] == 2
    assert report["coverage"]["predicted_image_count"] == 1
    assert report["coverage"]["evaluation_scope_image_count"] == 2


@pytest.mark.parametrize("field,value", [("exif_orientation", 2), ("original_width", 48)])
def test_resealed_coordinate_metadata_cannot_override_decoded_pixels(
    fixture_dataset: tuple[dict[str, Any], Path],
    field: str,
    value: object,
) -> None:
    dataset, root = fixture_dataset
    dataset["images"][0][field] = value
    if field == "original_width":
        # Internally consistent declared 90-degree frame, but not the source's
        # actual EXIF/original dimensions. Schema validation alone cannot prove it.
        dataset["images"][0]["original_height"] = 64
        dataset["images"][0]["exif_orientation"] = 6
    dataset["images"][0] = seal(dataset["images"][0], "record_hash")
    dataset = seal(dataset, "manifest_hash")
    result = run_real_inference(dataset, root, freeze_r2_baselines())
    assert result["images"][0]["status"] == "failed"
    assert result["images"][0]["reason_code"] == "IMAGE_COORDINATE_METADATA_MISMATCH"
    assert result["images"][0]["predicted_visible_fruit_count"] is None


def test_noncanonical_coordinate_frame_rejected_before_inference(
    fixture_dataset: tuple[dict[str, Any], Path],
) -> None:
    dataset, root = fixture_dataset
    dataset["images"][0]["image_coordinate_frame"] = "ENCODED_ORIGINAL_UNTRANSPOSED"
    dataset["images"][0] = seal(dataset["images"][0], "record_hash")
    dataset = seal(dataset, "manifest_hash")
    with pytest.raises(ValueError, match="DATASET_SCHEMA_INVALID"):
        run_real_inference(dataset, root, freeze_r2_baselines())


def test_freeze_binds_coordinate_and_gt_admission_helpers() -> None:
    frozen = freeze_r2_baselines()
    assert {"r3/ingestion.py", "r3/contracts.py", "r3/annotations.py", "r3/splits.py"} <= set(
        frozen["source_code_sha256"]
    )
