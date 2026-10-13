"""Actual pixel imports and fail-closed external authority contracts."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
from PIL import Image, ImageDraw

from research.blueberry_vision.assets import AssetPolicy
from research.blueberry_vision.r2_common import file_hash, seal
from research.blueberry_vision.r3.contracts import DatasetError, validate_manifest
from research.blueberry_vision.r3.ingestion import (
    audit_images,
    import_images,
    load_manifest,
    secure_load_asset,
)


@pytest.fixture
def pilot(tmp_path: Path) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    root = tmp_path / "images"
    root.mkdir()
    Image.new("RGB", (24, 16), (20, 50, 120)).save(root / "fruit.png")
    source = {
        "source_id": "public-one",
        "purpose": "PUBLIC_EXTERNAL_BENCHMARK",
        "SYNTHETIC": False,
        "license_id": "CC0-1.0",
        "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
        "license_status": "LICENSE_VERIFIED",
        "research_use": True,
        "commercial_use": False,
        "model_training": False,
        "redistribution": False,
        "attribution_required": False,
        "official_url": "https://example.org/source",
        "license_evidence": {"metadata_sha256": "a" * 64},
    }
    index = {
        "dataset_id": "test-public-pilot",
        "dataset_version": "1.0.0",
        "purpose": "PUBLIC_EXTERNAL_BENCHMARK",
        "SYNTHETIC": False,
        "images": [
            {
                "source_id": "public-one",
                "image_id": "one",
                "asset_ref": "fruit.png",
                "asset_sha256": file_hash(root / "fruit.png"),
            }
        ],
    }
    return root, index, {"sources": [source]}


def imported(pilot: tuple[Path, dict[str, Any], dict[str, Any]], output: Path) -> dict[str, Any]:
    return import_images(*pilot, output)


def test_actual_import_preserves_unknown_time_identity_and_permissions(
    pilot: tuple[Path, dict[str, Any], dict[str, Any]], tmp_path: Path
) -> None:
    data = imported(pilot, tmp_path / "run")
    row = data["images"][0]
    assert row["observed_at"] is None and row["capture_time_status"].startswith("UNKNOWN")
    assert row["base_identity"]["status"] == "UNRESOLVED"
    assert row["image_width"] == 24 and row["image_height"] == 16
    assert row["license_status"] == "LICENSE_VERIFIED"
    assert data["sources"][0]["redistribution"] is False
    assert data["sources"][0]["model_training"] is False
    assert "objects" not in row and "visible_count" not in row
    assert load_manifest(tmp_path / "run/dataset_manifest.json") == data


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("license_status", "LICENSE_UNVERIFIED", "SOURCE_LICENSE_NOT_VERIFIED"),
        ("research_use", False, "SOURCE_RESEARCH_USE_NOT_ALLOWED"),
        ("SYNTHETIC", True, "SOURCE_PURPOSE_MISMATCH"),
        ("license_url", None, "SOURCE_LICENSE_REFERENCE_MISSING"),
    ],
)
def test_license_and_domain_fail_closed(
    pilot: tuple[Path, dict[str, Any], dict[str, Any]],
    tmp_path: Path,
    field: str,
    value: object,
    code: str,
) -> None:
    pilot[2]["sources"][0][field] = value
    with pytest.raises(DatasetError, match=code):
        imported(pilot, tmp_path / "run")


def test_manifest_reseal_cannot_upgrade_source_permission(
    pilot: tuple[Path, dict[str, Any], dict[str, Any]], tmp_path: Path
) -> None:
    data = imported(pilot, tmp_path / "run")
    data["images"][0]["license_status"] = "LICENSE_UNVERIFIED"
    data["images"][0] = seal(data["images"][0], "record_hash")
    with pytest.raises(DatasetError, match="IMAGE_SOURCE_LICENSE_MISMATCH"):
        validate_manifest(seal(data, "manifest_hash"))


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("asset_sha256", "b" * 64, "ASSET_HASH_MISMATCH"),
        ("image_width", 900, "IMAGE_SIZE_MISMATCH"),
        ("observed_at", "2001-01-01", "CAPTURE_TIME_INVALID"),
        ("observed_at", "2001-01-01T00:00:00", "CAPTURE_TIME_INVALID"),
    ],
)
def test_bad_bindings_and_guessed_dates_rejected(
    pilot: tuple[Path, dict[str, Any], dict[str, Any]],
    tmp_path: Path,
    field: str,
    value: object,
    code: str,
) -> None:
    pilot[1]["images"][0][field] = value
    with pytest.raises(DatasetError, match=code):
        imported(pilot, tmp_path / "run")


@pytest.mark.parametrize(
    "kind", ["root", "ancestor", "file", "traversal", "absolute", "invalid_format", "corrupt"]
)
def test_unsafe_assets_rejected(
    pilot: tuple[Path, dict[str, Any], dict[str, Any]], tmp_path: Path, kind: str
) -> None:
    root, index, registry = pilot
    if kind == "root":
        link = tmp_path / "link"
        link.symlink_to(root, target_is_directory=True)
        root = link
    elif kind == "ancestor":
        link = tmp_path / "link"
        link.symlink_to(tmp_path, target_is_directory=True)
        root = link / "images"
    elif kind == "file":
        (root / "alias.png").symlink_to(root / "fruit.png")
        index["images"][0]["asset_ref"] = "alias.png"
    elif kind == "traversal":
        index["images"][0]["asset_ref"] = "../fruit.png"
    elif kind == "absolute":
        index["images"][0]["asset_ref"] = str(root / "fruit.png")
    elif kind == "invalid_format":
        Image.new("RGB", (5, 5)).save(root / "fruit.gif")
        index["images"][0].update(asset_ref="fruit.gif", asset_sha256=file_hash(root / "fruit.gif"))
    else:
        (root / "fruit.png").write_bytes(b"not an image")
        index["images"][0]["asset_sha256"] = file_hash(root / "fruit.png")
    with pytest.raises(DatasetError):
        import_images(root, index, registry, tmp_path / "run")


@pytest.mark.parametrize(
    "max_images,max_bytes,code",
    [
        (0, 500_000_000, "IMPORT_LIMIT_INVALID"),
        (101, 500_000_000, "IMPORT_LIMIT_INVALID"),
        (100, 500_000_001, "IMPORT_LIMIT_INVALID"),
        (100, 10, "IMPORT_BYTES_LIMIT"),
    ],
)
def test_pilot_resource_bounds(
    pilot: tuple[Path, dict[str, Any], dict[str, Any]],
    tmp_path: Path,
    max_images: int,
    max_bytes: int,
    code: str,
) -> None:
    with pytest.raises(DatasetError, match=code):
        import_images(*pilot, tmp_path / "run", max_images=max_images, max_total_bytes=max_bytes)


def test_folder_import_requires_explicit_source_and_generates_no_dates(
    pilot: tuple[Path, dict[str, Any], dict[str, Any]], tmp_path: Path
) -> None:
    root, index, registry = pilot
    index["images"] = None
    index["source_id"] = "public-one"
    data = import_images(root, index, registry, tmp_path / "run")
    assert len(data["images"]) == 1 and data["images"][0]["observed_at"] is None


def test_duplicate_ids_and_unknown_source_rejected(
    pilot: tuple[Path, dict[str, Any], dict[str, Any]], tmp_path: Path
) -> None:
    pilot[1]["images"].append(copy.deepcopy(pilot[1]["images"][0]))
    with pytest.raises(DatasetError, match="IMAGE_ID_DUPLICATE"):
        imported(pilot, tmp_path / "run")
    pilot[1]["images"] = pilot[1]["images"][:1]
    pilot[1]["images"][0]["source_id"] = "not-authorized"
    with pytest.raises(DatasetError, match="SOURCE_ID_UNKNOWN"):
        imported(pilot, tmp_path / "run")


def test_image_quality_is_auxiliary_and_not_gt(
    pilot: tuple[Path, dict[str, Any], dict[str, Any]], tmp_path: Path
) -> None:
    data = imported(pilot, tmp_path / "run")
    quality = audit_images(data, pilot[0])
    row = quality["images"][0]
    assert row["status"] == "VALID" and row["laplacian_variance"] == 0.0
    assert row["brightness"] > 0 and row["contrast"] >= 0
    assert quality["annotation_coverage"] == 0 and quality["per_fruit_label_count"] is None
    assert quality["summary"]["quality_metrics_are_auxiliary"] is True
    (pilot[0] / "fruit.png").write_bytes(b"broken")
    quality = audit_images(data, pilot[0])
    assert quality["summary"]["failed_count"] == 1
    assert quality["images"][0]["reason_code"] == "ASSET_HASH_MISMATCH"


def test_import_is_reproducible_and_no_overwrite(
    pilot: tuple[Path, dict[str, Any], dict[str, Any]], tmp_path: Path
) -> None:
    one = imported(pilot, tmp_path / "one")
    two = imported(pilot, tmp_path / "two")
    assert one["manifest_hash"] == two["manifest_hash"]
    with pytest.raises((FileExistsError, DatasetError)):
        imported(pilot, tmp_path / "one")


def test_secure_loader_reuses_original_pixel_binding(
    pilot: tuple[Path, dict[str, Any], dict[str, Any]],
) -> None:
    loaded = secure_load_asset(pilot[0], "fruit.png")
    assert loaded.rgb.shape == (16, 24, 3)


def test_coco_identity_linkage_and_missing_gt_remain_separate(
    pilot: tuple[Path, dict[str, Any], dict[str, Any]], tmp_path: Path
) -> None:
    coco: dict[str, Any] = {
        "images": [{"id": 7, "file_name": "fruit.png", "width": 24, "height": 16}],
        "annotations": [{"id": 1, "image_id": 7, "category_id": 1, "bbox": [1, 1, 5, 5]}],
        "categories": [{"id": 1, "name": "blueberry"}],
    }
    data = import_images(*pilot, tmp_path / "run", coco=coco)
    assert data["annotation_index"]["images"][0]["image_id"] == "one"
    assert data["annotation_index"]["status"] == "INDEXED_NOT_GT_QUALITY_APPROVED"
    assert "objects" not in data["images"][0]
    coco["annotations"][0]["image_id"] = 99
    with pytest.raises(DatasetError, match="COCO_ANNOTATION_IMAGE_UNMATCHED"):
        import_images(*pilot, tmp_path / "other", coco=coco)


@pytest.mark.parametrize(
    "coco,code",
    [
        ({"images": [], "annotations": []}, "COCO_IMAGE_COVERAGE_MISMATCH"),
        ({"images": [{"id": True}], "annotations": []}, "COCO_IMAGE_ID_INVALID"),
        (
            {"images": [{"id": 7, "file_name": "wrong.png"}], "annotations": []},
            "COCO_IMAGE_ASSET_UNMATCHED",
        ),
        (
            {
                "images": [{"id": 7, "file_name": "fruit.png", "width": 24, "height": 15}],
                "annotations": [],
            },
            "COCO_IMAGE_SIZE_MISMATCH",
        ),
    ],
)
def test_coco_bad_image_bindings_rejected(
    pilot: tuple[Path, dict[str, Any], dict[str, Any]],
    tmp_path: Path,
    coco: dict[str, Any],
    code: str,
) -> None:
    with pytest.raises(DatasetError, match=code):
        import_images(*pilot, tmp_path / "run", coco=coco)


def test_input_license_disagreement_and_unresolved_canonical_id_rejected(
    pilot: tuple[Path, dict[str, Any], dict[str, Any]], tmp_path: Path
) -> None:
    pilot[1]["images"][0]["license_id"] = "UNKNOWN"
    with pytest.raises(DatasetError, match="IMAGE_SOURCE_LICENSE_MISMATCH"):
        imported(pilot, tmp_path / "run")
    del pilot[1]["images"][0]["license_id"]
    pilot[1]["images"][0]["base_identity"] = {"status": "UNRESOLVED", "base_id": "guessed-farm"}
    with pytest.raises(DatasetError, match="UNRESOLVED_IDENTITY_HAS_CANONICAL_ID"):
        imported(pilot, tmp_path / "run")


def test_import_cannot_loosen_r2_memory_policy(
    pilot: tuple[Path, dict[str, Any], dict[str, Any]], tmp_path: Path
) -> None:
    with pytest.raises(DatasetError, match="IMPORT_ASSET_POLICY_EXCEEDS_LIMIT"):
        import_images(*pilot, tmp_path / "run", policy=AssetPolicy(max_pixels=100_000_000))


def test_manifest_rejects_gt_and_prediction_fields(
    pilot: tuple[Path, dict[str, Any], dict[str, Any]], tmp_path: Path
) -> None:
    data = imported(pilot, tmp_path / "run")
    data["images"][0]["objects"] = []
    data["images"][0] = seal(data["images"][0], "record_hash")
    with pytest.raises(DatasetError, match="DATASET_SCHEMA_INVALID"):
        validate_manifest(seal(data, "manifest_hash"))


def test_registry_hash_and_root_dotdot_cannot_mask_symlink(
    pilot: tuple[Path, dict[str, Any], dict[str, Any]], tmp_path: Path
) -> None:
    pilot[2]["registry_hash"] = "0" * 64
    with pytest.raises(DatasetError, match="SOURCE_REGISTRY_HASH_MISMATCH"):
        imported(pilot, tmp_path / "run")
    del pilot[2]["registry_hash"]
    with pytest.raises(DatasetError, match="DATA_ROOT_PATH_UNSAFE"):
        import_images(pilot[0] / "../images", pilot[1], pilot[2], tmp_path / "run")


def test_known_capture_needs_source_status_and_no_future_availability(
    pilot: tuple[Path, dict[str, Any], dict[str, Any]], tmp_path: Path
) -> None:
    row = pilot[1]["images"][0]
    row.update(observed_at="2020-01-01T00:00:00Z", capture_time_status="SOURCE_VERIFIED")
    data = imported(pilot, tmp_path / "one")
    assert data["images"][0]["observed_at"] == row["observed_at"]
    row["asset_available_at"] = "2019-01-01T00:00:00Z"
    with pytest.raises(DatasetError, match="ASSET_AVAILABLE_BEFORE_CAPTURE"):
        imported(pilot, tmp_path / "two")


def test_schema_fixture_matches_model_and_rejects_mixed_domain(
    pilot: tuple[Path, dict[str, Any], dict[str, Any]], tmp_path: Path
) -> None:
    from research.blueberry_vision.r2_common import read_json
    from research.blueberry_vision.r3.contracts import R3Dataset

    schema = read_json(Path(__file__).parents[1] / "r3/schema.json")
    assert schema == R3Dataset.model_json_schema()
    data = imported(pilot, tmp_path / "run")
    data["SYNTHETIC"] = True
    with pytest.raises(DatasetError, match="DATASET_PURPOSE_MISMATCH"):
        validate_manifest(seal(data, "manifest_hash"))


@pytest.mark.parametrize("orientation", [2, 8])
def test_exif_geometry_is_actual_and_raw_coco_is_rejected(
    pilot: tuple[Path, dict[str, Any], dict[str, Any]], tmp_path: Path, orientation: int
) -> None:
    image = Image.new("RGB", (64, 48), (160, 100, 30))
    ImageDraw.Draw(image).rectangle((10, 20, 19, 29), fill=(10, 20, 160))
    exif = Image.Exif()
    exif[274] = orientation
    image.save(pilot[0] / "oriented.jpg", exif=exif, quality=100, subsampling=0)
    row = pilot[1]["images"][0]
    row.update(asset_ref="oriented.jpg", asset_sha256=file_hash(pilot[0] / "oriented.jpg"))
    data = imported(pilot, tmp_path / "run")
    imported_row = data["images"][0]
    assert imported_row["original_width"] == 64 and imported_row["original_height"] == 48
    assert imported_row["exif_orientation"] == orientation
    assert imported_row["image_coordinate_frame"] == "EXIF_NORMALIZED_RGB_HALF_OPEN_XYXY"
    expected_size = (64, 48) if orientation == 2 else (48, 64)
    assert (imported_row["image_width"], imported_row["image_height"]) == expected_size
    if orientation == 2:
        normalized = secure_load_asset(pilot[0], "oriented.jpg").rgb
        assert normalized[25, 48, 2] > normalized[25, 48, 0]
        assert normalized[25, 15, 2] < normalized[25, 15, 0]
    coco: dict[str, Any] = {
        "images": [
            {
                "id": 1,
                "file_name": "oriented.jpg",
                "width": expected_size[0],
                "height": expected_size[1],
            }
        ],
        "annotations": [{"id": 1, "image_id": 1, "category_id": 1, "bbox": [10, 20, 10, 10]}],
    }
    with pytest.raises(DatasetError, match="COCO_COORDINATE_FRAME_UNVERIFIED"):
        import_images(*pilot, tmp_path / "raw-coco", coco=coco)
    coco.update(
        coordinate_frame="EXIF_NORMALIZED_RGB_HALF_OPEN_XYXY", coordinate_frame_status="VERIFIED"
    )
    with pytest.raises(DatasetError, match="COCO_COORDINATE_FRAME_UNVERIFIED"):
        import_images(*pilot, tmp_path / "no-evidence", coco=coco)
    coco["coordinate_frame_evidence_ref"] = "manual-reviewed-transform-v1"
    normalized_dataset = import_images(*pilot, tmp_path / "normalized", coco=coco)
    assert normalized_dataset["annotation_index"]["coordinate_frame"] == coco["coordinate_frame"]


def test_secure_metadata_reads_are_bounded_and_bind_same_bytes(
    pilot: tuple[Path, dict[str, Any], dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    from research.blueberry_vision.r3 import ingestion

    loaded = secure_load_asset(pilot[0], "fruit.png")
    assert loaded.metadata["exif_orientation"] == 1
    assert loaded.metadata["original_width"] == 24
    monkeypatch.setattr(ingestion, "_read_authorized", lambda *_args: b"changed after pixel decode")
    with pytest.raises(DatasetError, match="IMAGE_METADATA_ASSET_CHANGED"):
        secure_load_asset(pilot[0], "fruit.png")


def test_old_unannotated_m2_manifest_remains_valid(
    pilot: tuple[Path, dict[str, Any], dict[str, Any]], tmp_path: Path
) -> None:
    data = imported(pilot, tmp_path / "run")
    for key in ("original_width", "original_height", "exif_orientation", "image_coordinate_frame"):
        data["images"][0].pop(key)
    data["images"][0] = seal(data["images"][0], "record_hash")
    assert (
        validate_manifest(seal(data, "manifest_hash"))["images"][0].get("exif_orientation") is None
    )


def test_quality_audit_rejects_resealed_false_exif_orientation(
    pilot: tuple[Path, dict[str, Any], dict[str, Any]], tmp_path: Path
) -> None:
    data = imported(pilot, tmp_path / "run")
    data["images"][0]["exif_orientation"] = 2
    data["images"][0] = seal(data["images"][0], "record_hash")
    report = audit_images(seal(data, "manifest_hash"), pilot[0])
    assert report["images"][0]["reason_code"] == "IMAGE_COORDINATE_METADATA_MISMATCH"


def test_explicit_original_lineage_is_preserved_without_guessed_parent(
    pilot: tuple[Path, dict[str, Any], dict[str, Any]], tmp_path: Path
) -> None:
    pilot[1]["images"][0].update(
        original_asset_sha256="d" * 64, original_asset_ref="originals/source-photo.jpg"
    )
    data = imported(pilot, tmp_path / "derived")
    row = data["images"][0]
    assert row["original_asset_sha256"] == "d" * 64
    assert row["original_asset_ref"] == "originals/source-photo.jpg"
    assert row["parent_image_id"] is None
    del pilot[1]["images"][0]["original_asset_sha256"]
    del pilot[1]["images"][0]["original_asset_ref"]
    original = imported(pilot, tmp_path / "original")
    assert original["images"][0]["original_asset_sha256"] is None
    assert original["images"][0]["original_asset_ref"] is None


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("original_asset_sha256", "not-a-hash", "DATASET_SCHEMA_INVALID"),
        ("original_asset_ref", "../unapproved.jpg", "ORIGINAL_ASSET_REF_INVALID"),
        ("original_asset_ref", "https://example.org/image.jpg", "ORIGINAL_ASSET_REF_INVALID"),
    ],
)
def test_bad_original_lineage_rejected(
    pilot: tuple[Path, dict[str, Any], dict[str, Any]],
    tmp_path: Path,
    field: str,
    value: str,
    code: str,
) -> None:
    pilot[1]["images"][0][field] = value
    with pytest.raises(DatasetError, match=code):
        imported(pilot, tmp_path / "run")
