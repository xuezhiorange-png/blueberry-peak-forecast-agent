import copy
from pathlib import Path

import pytest

from research.blueberry_vision.r2_common import read_json, seal
from research.blueberry_vision.r4.package import build_package, project_boxes, validate_package

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def dataset():
    return read_json(ROOT / "evidence/r3/pilot_dataset_manifest.json")


def test_all_images_full_frame_without_cherry_picking(dataset):
    package = build_package(dataset)
    assert len(package["images"]) == 8
    for row, image in zip(
        package["images"], sorted(dataset["images"], key=lambda x: x["image_id"]), strict=True
    ):
        assert row["roi_xyxy"] == [0, 0, image["image_width"], image["image_height"]]
        assert row["reference_count"] is None
    assert package["tasks"]["A"]["assigned_human_id"] is None
    assert package["tasks"]["B"]["assigned_human_id"] is None
    assert package["tasks"]["A"]["task_id"] != package["tasks"]["B"]["task_id"]
    assert "prediction" not in str(package["images"]).lower()
    validate_package(package, dataset)


@pytest.mark.parametrize("field,value", [("SYNTHETIC", True), ("purpose", "SYNTHETIC_ENGINEERING")])
def test_synthetic_cannot_be_real_package(dataset, field, value):
    dataset[field] = value
    dataset = seal(dataset, "manifest_hash")
    with pytest.raises(ValueError):
        build_package(dataset)


def test_resealed_roi_changed_after_registration_rejected(dataset):
    p = build_package(dataset)
    p["images"][0]["roi_xyxy"][0] = 10
    with pytest.raises(ValueError, match="PACKAGE_REGISTRATION_MISMATCH"):
        validate_package(seal(p, "package_hash"), dataset)


def test_license_source_unauthorized(dataset):
    dataset["sources"][0]["research_use"] = False
    with pytest.raises(ValueError):
        build_package(seal(dataset, "manifest_hash"))


def test_whole_image_projection_preserves_boxes():
    boxes = [{"bbox_xyxy": [2, 3, 8, 9], "object_id": "x"}]
    assert project_boxes(boxes, [0, 0, 10, 10]) == boxes


def test_roi_centroid_half_open_and_clipping_golden():
    boxes = [
        {"bbox_xyxy": [0, 0, 8, 8], "object_id": "in"},
        {"bbox_xyxy": [8, 0, 12, 4], "object_id": "out"},
    ]
    actual = project_boxes(boxes, [2, 2, 10, 10])
    assert actual == [{"bbox_xyxy": [0, 0, 6, 6], "object_id": "in"}]
    assert boxes[0]["bbox_xyxy"] == [0, 0, 8, 8]


@pytest.mark.parametrize("roi", [[0, 0, 0, 4], [0, 0, float("nan"), 5], [0, 0, 5], [True, 0, 5, 5]])
def test_bad_roi(roi):
    with pytest.raises(ValueError, match="ROI_INVALID"):
        project_boxes([], roi)


def test_package_hash_tampering(dataset):
    p = copy.deepcopy(build_package(dataset))
    p["images"][0]["source_asset_hash"] = "0" * 64
    with pytest.raises(ValueError, match="PACKAGE_HASH_INVALID"):
        validate_package(p, dataset)
