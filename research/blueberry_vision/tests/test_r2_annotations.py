"""Hand-created geometry/provenance goldens for controlled detection adapters."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from research.blueberry_vision.annotations import (
    AnnotationError,
    export_coco,
    export_r1_coco,
    import_coco,
)
from research.blueberry_vision.r2_common import canonical_hash, seal


def research_manifest() -> dict[str, Any]:
    records = []
    for name, status, count, objects in [
        (
            "fruit",
            "complete",
            1,
            [{"object_id": "berry-1", "class_label": "candidate", "bbox_xyxy": [2, 3, 8, 11]}],
        ),
        ("empty", "complete", 0, []),
        ("missing", "missing", None, None),
    ]:
        records.append(
            seal(
                {
                    "image_id": name,
                    "image_width": 20,
                    "image_height": 15,
                    "original_asset_ref": f"images/{name}.png",
                    "asset_sha256": "a" * 64,
                    "gt_status": status,
                    "visible_count": count,
                    "objects": objects,
                    "ignore_regions": [],
                    "annotation_version": "synthetic-1",
                    "label_definition_version": "candidate-1",
                    "SYNTHETIC": True,
                    "source_authority": {
                        "authority_id": "generator",
                        "permission_status": "synthetic_only",
                    },
                    "scene_metadata": {"occlusion": "none"},
                },
                "record_hash",
            )
        )
    return seal({"SYNTHETIC": True, "images": records}, "dataset_manifest_hash")


def test_coco_round_trip_hand_calculated_geometry_and_empty_missing() -> None:
    manifest = research_manifest()
    coco = export_coco(manifest)
    assert coco["annotations"][0]["bbox"] == [2, 3, 6, 8]
    assert coco["annotations"][0]["area"] == 48
    recovered = import_coco(coco)
    assert recovered["schema_version"] == "blueberry-vision-reference-adapter/2.0.0"
    assert recovered["is_validated_dataset"] is False
    for original, actual in zip(manifest["images"], recovered["images"], strict=True):
        for key in [
            "image_id",
            "objects",
            "visible_count",
            "gt_status",
            "source_authority",
            "annotation_version",
            "label_definition_version",
            "record_hash",
        ]:
            assert actual[key] == original[key]
    assert recovered["images"][1]["objects"] == []
    assert recovered["images"][2]["objects"] is None
    assert coco["research_provenance"]["label_approval_status"] == "candidate"


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("bounds", "BBOX_OUT_OF_BOUNDS"),
        ("nan", "INVALID_BBOX"),
        ("mask", "SEGMENTATION_NOT_SUPPORTED"),
        ("prediction", "PREDICTION_IS_NOT_GT"),
        ("source", "SOURCE_AUTHORITY_REQUIRED"),
        ("duplicate", "DUPLICATE_IMAGE_ID"),
        ("count", "REFERENCE_COUNT_MISMATCH"),
    ],
)
def test_coco_export_rejects_invalid_reference(mutation: str, code: str) -> None:
    manifest = research_manifest()
    image = manifest["images"][0]
    if mutation == "bounds":
        image["objects"][0]["bbox_xyxy"][2] = 22
    elif mutation == "nan":
        image["objects"][0]["bbox_xyxy"][0] = float("nan")
    elif mutation == "mask":
        image["objects"][0]["mask_polygon"] = [[1, 1], [2, 2], [3, 1]]
    elif mutation == "prediction":
        image["record_kind"] = "model_prediction"
    elif mutation == "source":
        del image["source_authority"]
    elif mutation == "duplicate":
        manifest["images"][1]["image_id"] = "fruit"
    elif mutation == "count":
        image["visible_count"] = 9
    with pytest.raises(AnnotationError) as error:
        export_coco(manifest)
    assert error.value.code == code


def test_import_requires_provenance_and_unknown_category_is_rejected() -> None:
    coco = export_coco(research_manifest())
    bare = copy.deepcopy(coco)
    del bare["research_provenance"]
    with pytest.raises(AnnotationError, match="PROVENANCE_REQUIRED"):
        import_coco(bare)
    coco["annotations"][0]["category_id"] = 999
    with pytest.raises(AnnotationError, match="UNKNOWN_CATEGORY"):
        import_coco(coco)


def test_changed_import_creates_candidate_revision_not_fake_review() -> None:
    original = research_manifest()
    coco = export_coco(original)
    coco["annotations"][0]["bbox"] = [1, 2, 7, 8]
    actual = import_coco(coco)["images"][0]
    assert actual["objects"][0]["bbox_xyxy"] == [1, 2, 8, 10]
    assert actual["annotation_quality_status"] == "draft"
    assert actual["annotation_version"].startswith("candidate-import/")
    assert actual["original_record_hash"] == original["images"][0]["record_hash"]
    assert actual["record_hash"] != original["images"][0]["record_hash"]
    assert "reviewer" not in actual


def test_r1_adapter_retains_no_asset_descriptor_semantics() -> None:
    from pathlib import Path

    from research.blueberry_vision.r2_common import read_json

    fixture = read_json(Path("research/blueberry_vision/fixtures/synthetic_manifest.json"))
    coco = export_r1_coco(fixture)
    assert coco["research_provenance"]["image_files_present"] is False
    assert coco["research_provenance"]["asset_hash_basis"] == "synthetic_descriptor_sha256"
    assert coco["research_provenance"]["original_manifest_hash"] == canonical_hash(fixture)
    assert all(image["research_record"]["SYNTHETIC"] for image in coco["images"])
    assert coco["research_provenance"]["label_approval_status"] == "candidate"


@pytest.mark.parametrize("key", ["image_id", "category_id", "id"])
@pytest.mark.parametrize("value", [True, 1.0, "1", None])
def test_coco_ids_are_strict_integers(key: str, value: object) -> None:
    coco = export_coco(research_manifest())
    coco["annotations"][0][key] = value
    with pytest.raises(AnnotationError):
        import_coco(coco)


@pytest.mark.parametrize("key", ["images", "annotations", "categories"])
@pytest.mark.parametrize("value", [[None], {}, None, [1]])
def test_coco_malformed_arrays_fail_with_controlled_reason(key: str, value: object) -> None:
    coco = export_coco(research_manifest())
    coco[key] = value
    with pytest.raises(AnnotationError):
        import_coco(coco)
