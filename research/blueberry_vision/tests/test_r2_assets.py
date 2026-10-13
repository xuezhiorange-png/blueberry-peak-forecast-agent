"""M1 asset security and independent R2 synthetic data contract tests."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import struct
import zlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from research.blueberry_vision.assets import (
    AssetError,
    AssetPolicy,
    load_asset,
    load_dataset,
    validate_assets,
)
from research.blueberry_vision.contracts import canonical_record_hash
from research.blueberry_vision.r2_common import CLASS_LABEL, seal
from research.blueberry_vision.r2_contracts import R2Dataset, compute_split_hash


def reseal(data: dict[str, Any]) -> dict[str, Any]:
    for record in data["images"]:
        record["record_hash"] = canonical_record_hash(record)
    data["split_hash"] = compute_split_hash(data["images"])
    return seal(data, "manifest_hash")


@pytest.fixture
def dataset(tmp_path: Path) -> dict[str, Any]:
    images = []
    for index, split in enumerate(("train", "validation", "test", "out_of_domain")):
        ref = f"images/{split}.png"
        (tmp_path / "images").mkdir(exist_ok=True)
        Image.new("RGB", (12, 8), (index * 30, 40, 90)).save(tmp_path / ref)
        metadata = load_asset(tmp_path, ref).metadata
        images.append(
            {
                "image_id": f"synthetic-{index}",
                "original_asset_ref": ref,
                "asset_sha256": metadata["asset_sha256"],
                "image_width": 12,
                "image_height": 8,
                "observed_at": "2021-01-01T00:00:00Z",
                "asset_available_at": "2021-01-01T00:00:01Z",
                "available_at": "2021-01-01T00:00:02Z",
                "capture_session_id": f"session-{index}",
                "sampling_unit_id": f"unit-{index}",
                "base_identity": {
                    "status": "unresolved",
                    "base_id": None,
                    "authority_ref": None,
                    "unresolved_reason": "synthetic_has_no_canonical_business_identity",
                },
                "source_authority": {
                    "authority_id": "synthetic-generator",
                    "source_ref": "test-generated-pixels",
                    "permission_status": "synthetic_only",
                    "evidence_ref": None,
                    "allowed_uses": ["metadata_validation", split],
                    "granted_at": None,
                    "expires_at": None,
                },
                "SYNTHETIC": True,
                "split": split,
                "generation_seed": index,
                "template_group_id": f"template-{index}",
                "near_duplicate_group_id": f"duplicate-{index}",
                "preprocessing_version": metadata["preprocessing_version"],
                "preprocessing_hash": metadata["preprocessing_hash"],
                "label_definition_version": "synthetic-visible-fruit/2.0.0",
                "annotation_version": "synthetic-render-reference/2.0.0",
                "annotation_quality_status": "synthetic_reference",
                "gt_status": "complete",
                "visible_count": 1,
                "objects": [
                    {
                        "object_id": f"object-{index}",
                        "class_label": CLASS_LABEL,
                        "bbox_xyxy": [1.0, 1.0, 5.0, 5.0],
                    }
                ],
                "ignore_regions": [],
                "drawn_object_count": 1,
                "hidden_object_count": 0,
                "ignored_object_count": 0,
                "scene_metadata": {"scene": "sparse"},
                "training_mask_ref": None,
                "training_mask_sha256": None,
                "record_hash": "0" * 64,
            }
        )
    return reseal(
        {
            "schema_version": "blueberry-vision-dataset/2.0.0",
            "SYNTHETIC": True,
            "image_files_present": True,
            "generator_version": "synthetic-generator/2.0.0",
            "generation_config": {"seed": 0},
            "label_definition_version": "synthetic-visible-fruit/2.0.0",
            "annotation_version": "synthetic-render-reference/2.0.0",
            "images": images,
            "manifest_hash": "0" * 64,
            "split_hash": "0" * 64,
        }
    )


def write_manifest(tmp_path: Path, data: dict[str, Any]) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data))
    return path


@pytest.mark.parametrize("extension", ["png", "jpg", "jpeg"])
def test_actual_bytes_rgb_size_and_original_unchanged(tmp_path: Path, extension: str) -> None:
    path = tmp_path / f"image.{extension}"
    Image.new("RGB", (13, 7), (40, 50, 100)).save(path)
    before = path.read_bytes()
    loaded = load_asset(tmp_path, path.name, hashlib.sha256(before).hexdigest(), (13, 7))
    assert loaded.rgb.dtype == np.uint8
    assert loaded.rgb.shape == (7, 13, 3)
    assert loaded.metadata["image_width"] == 13
    assert loaded.metadata["original_height"] == 7
    assert path.read_bytes() == before
    assert loaded.metadata == load_asset(tmp_path, path.name).metadata


def test_exif_orientation_and_white_alpha_composite(tmp_path: Path) -> None:
    image = Image.new("RGB", (8, 3), (50, 90, 120))
    exif = image.getexif()
    exif[274] = 6
    image.save(tmp_path / "oriented.jpg", exif=exif)
    oriented = load_asset(tmp_path, "oriented.jpg", expected_size=(3, 8))
    assert oriented.rgb.shape == (8, 3, 3)
    assert oriented.metadata["original_width"] == 8
    Image.new("RGBA", (2, 2), (0, 0, 0, 0)).save(tmp_path / "alpha.png")
    assert np.all(load_asset(tmp_path, "alpha.png").rgb == 255)


@pytest.mark.parametrize(
    "ref",
    [
        "../image.png",
        "/tmp/image.png",
        "https://example.com/x.png",
        "a/../x.png",
        "a\\x.png",
        "a//x.png",
        "./x.png",
    ],
)
def test_path_traversal_and_nonlocal_references_rejected(tmp_path: Path, ref: str) -> None:
    with pytest.raises(AssetError, match="ASSET_REF_INVALID"):
        load_asset(tmp_path, ref)


def test_symlink_directory_and_file_are_rejected(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    Image.new("RGB", (2, 2)).save(outside / "image.png")
    (tmp_path / "linked.png").symlink_to(outside / "image.png")
    (tmp_path / "linked-dir").symlink_to(outside, target_is_directory=True)
    for ref in ("linked.png", "linked-dir/image.png"):
        with pytest.raises(AssetError, match="ASSET_PATH_UNSAFE"):
            load_asset(tmp_path, ref)


@pytest.mark.parametrize("contents", [b"not a picture", b"\x89PNG\r\n\x1a\n"])
def test_corrupted_image_rejected(tmp_path: Path, contents: bytes) -> None:
    (tmp_path / "bad.png").write_bytes(contents)
    with pytest.raises(AssetError, match="IMAGE_DECODE_FAILED"):
        load_asset(tmp_path, "bad.png")


def test_truncated_jpeg_and_forged_decompression_bomb_rejected(tmp_path: Path) -> None:
    path = tmp_path / "broken.jpg"
    Image.new("RGB", (20, 20), (40, 80, 120)).save(path)
    path.write_bytes(path.read_bytes()[:-12])
    with pytest.raises(AssetError, match="IMAGE_DECODE_FAILED"):
        load_asset(tmp_path, path.name)

    def chunk(kind: bytes, payload: bytes) -> bytes:
        checksum = zlib.crc32(kind + payload)
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)

    # Valid PNG header declaring an extreme decode; rejection happens before load.
    header = struct.pack(">IIBBBBB", 100_000, 100_000, 8, 2, 0, 0, 0)
    bomb = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(b""))
        + chunk(b"IEND", b"")
    )
    (tmp_path / "bomb.png").write_bytes(bomb)
    with pytest.raises(AssetError, match="IMAGE_DECOMPRESSION_BOMB"):
        load_asset(tmp_path, "bomb.png")


def test_nonregular_file_and_unsupported_format_rejected(tmp_path: Path) -> None:
    os.mkfifo(tmp_path / "pipe.png")
    with pytest.raises(AssetError, match="ASSET_NOT_REGULAR_FILE"):
        load_asset(tmp_path, "pipe.png")
    Image.new("RGB", (2, 2)).save(tmp_path / "disguised.png", format="GIF")
    with pytest.raises(AssetError, match="IMAGE_FORMAT_UNSUPPORTED"):
        load_asset(tmp_path, "disguised.png")


def test_invalid_asset_policy_rejected() -> None:
    with pytest.raises(AssetError, match="ASSET_POLICY_INVALID"):
        AssetPolicy(max_bytes=0)


def test_resource_guards_hash_and_dimension_checks(tmp_path: Path) -> None:
    Image.new("RGB", (20, 20)).save(tmp_path / "large.png")
    for kwargs, code in (
        ({"policy": AssetPolicy(max_bytes=10)}, "ASSET_BYTES_LIMIT"),
        ({"policy": AssetPolicy(max_pixels=399)}, "IMAGE_PIXELS_LIMIT"),
        ({"policy": AssetPolicy(max_dimension=19)}, "IMAGE_DIMENSION_LIMIT"),
        ({"expected_hash": "0" * 64}, "ASSET_HASH_MISMATCH"),
        ({"expected_size": (1, 1)}, "IMAGE_SIZE_MISMATCH"),
    ):
        with pytest.raises(AssetError, match=code):
            load_asset(tmp_path, "large.png", **kwargs)


def test_dataset_schema_asset_validation_and_r1_are_independent(
    tmp_path: Path, dataset: dict[str, Any]
) -> None:
    path = write_manifest(tmp_path, dataset)
    assert load_dataset(path) == dataset
    report = validate_assets(path, tmp_path)
    assert report["valid"] is True
    assert report["summary"]["validated_count"] == 4
    assert report["summary"]["SYNTHETIC"] is True
    from research.blueberry_vision.validate_manifest import validate_data

    assert validate_data(dataset, mode="experiment")["valid"] is False


@pytest.mark.parametrize(
    "field", ["visible_count", "record_hash", "base_identity", "training_mask_ref"]
)
def test_nullable_contract_fields_are_required(
    tmp_path: Path, dataset: dict[str, Any], field: str
) -> None:
    del dataset["images"][0][field]
    if field != "record_hash":
        dataset = reseal(dataset)
    with pytest.raises(AssetError, match="DATASET_SCHEMA_INVALID"):
        load_dataset(write_manifest(tmp_path, dataset))


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("asset_available_at", "2020-12-31T23:59:59Z", "ASSET_BEFORE_CAPTURE"),
        ("available_at", "2020-12-31T23:59:59Z", "RECORD_BEFORE_ASSET"),
        ("visible_count", 2, "COUNT_OBJECTS_MISMATCH"),
        ("annotation_version", "unknown", "ANNOTATION_VERSION_MISMATCH"),
        ("SYNTHETIC", False, "DATASET_SCHEMA_INVALID"),
        ("visible_count", True, "DATASET_SCHEMA_INVALID"),
    ],
)
def test_dataset_semantics_reject_invalid_values(
    tmp_path: Path, dataset: dict[str, Any], field: str, value: object, code: str
) -> None:
    dataset["images"][0][field] = value
    with pytest.raises(AssetError, match=code):
        load_dataset(write_manifest(tmp_path, reseal(dataset)))


def test_missing_gt_is_preserved_and_cannot_be_empty_truth(
    tmp_path: Path, dataset: dict[str, Any]
) -> None:
    record = dataset["images"][0]
    record.update(gt_status="missing", visible_count=None, objects=None)
    assert (
        load_dataset(write_manifest(tmp_path, reseal(dataset)))["images"][0]["visible_count"]
        is None
    )
    record["visible_count"] = 0
    with pytest.raises(AssetError, match="MISSING_GT_HAS_LABELS"):
        load_dataset(write_manifest(tmp_path, reseal(dataset)))


@pytest.mark.parametrize(
    "field",
    [
        "generation_seed",
        "template_group_id",
        "near_duplicate_group_id",
        "capture_session_id",
        "sampling_unit_id",
    ],
)
def test_split_isolation_for_all_simulated_groups(
    tmp_path: Path, dataset: dict[str, Any], field: str
) -> None:
    dataset["images"][1][field] = dataset["images"][0][field]
    with pytest.raises(AssetError, match="SPLIT_LEAKAGE"):
        load_dataset(write_manifest(tmp_path, reseal(dataset)))


@pytest.mark.parametrize("field", ["image_id", "asset_sha256", "original_asset_ref"])
def test_duplicate_identity_or_bytes_rejected(
    tmp_path: Path, dataset: dict[str, Any], field: str
) -> None:
    dataset["images"][1][field] = dataset["images"][0][field]
    with pytest.raises(AssetError, match="DUPLICATE"):
        load_dataset(write_manifest(tmp_path, reseal(dataset)))


def test_bbox_identity_permission_and_preprocessing_guards(
    tmp_path: Path, dataset: dict[str, Any]
) -> None:
    modifiers: list[tuple[Callable[[dict[str, Any]], None], str]] = [
        (lambda r: r["objects"][0].update(bbox_xyxy=[0.0, 0.0, 13.0, 4.0]), "BBOX_OUT_OF_BOUNDS"),
        (lambda r: r["base_identity"].update(base_id="guessed"), "IDENTITY_UNRESOLVED_HAS_BASE"),
        (
            lambda r: r["source_authority"].update(permission_status="approved"),
            "SYNTHETIC_SOURCE_PERMISSION_REQUIRED",
        ),
        (
            lambda r: r["source_authority"].update(allowed_uses=["metadata_validation"]),
            "SOURCE_USE_NOT_ALLOWED",
        ),
    ]
    for modifier, code in modifiers:
        changed = copy.deepcopy(dataset)
        modifier(changed["images"][0])
        with pytest.raises(AssetError, match=code):
            load_dataset(write_manifest(tmp_path, reseal(changed)))
    dataset["images"][0]["preprocessing_hash"] = "0" * 64
    report = validate_assets(write_manifest(tmp_path, reseal(dataset)), tmp_path)
    assert report["valid"] is False
    assert report["images"][0]["reason_code"] == "PREPROCESSING_HASH_MISMATCH"


def test_manifest_and_record_hash_tampering(tmp_path: Path, dataset: dict[str, Any]) -> None:
    dataset["generation_config"]["seed"] = 5
    with pytest.raises(AssetError, match="MANIFEST_HASH_MISMATCH"):
        load_dataset(write_manifest(tmp_path, dataset))
    dataset = seal(dataset, "manifest_hash")
    dataset["images"][0]["scene_metadata"]["scene"] = "dense"
    dataset = seal(dataset, "manifest_hash")
    with pytest.raises(AssetError, match="RECORD_HASH_MISMATCH"):
        load_dataset(write_manifest(tmp_path, dataset))


@pytest.mark.parametrize("same_split", [False, True])
def test_same_normalized_pixels_different_png_bytes_are_rejected(
    tmp_path: Path, dataset: dict[str, Any], same_split: bool
) -> None:
    first, second = dataset["images"][:2]
    info = PngInfo()
    info.add_text("synthetic_encoding_variant", "different PNG bytes, identical RGB")
    with Image.open(tmp_path / first["original_asset_ref"]) as original:
        original.save(tmp_path / second["original_asset_ref"], pnginfo=info, compress_level=0)
    loaded = load_asset(tmp_path, second["original_asset_ref"])
    assert loaded.metadata["asset_sha256"] != first["asset_sha256"]
    assert (
        loaded.metadata["rgb_sha256"]
        == load_asset(tmp_path, first["original_asset_ref"]).metadata["rgb_sha256"]
    )
    second.update(
        asset_sha256=loaded.metadata["asset_sha256"],
        preprocessing_hash=loaded.metadata["preprocessing_hash"],
    )
    if same_split:
        second["split"] = first["split"]
        second["source_authority"]["allowed_uses"] = ["metadata_validation", "train"]
    dataset = reseal(dataset)
    path = write_manifest(tmp_path, dataset)
    assert load_dataset(path) == dataset
    report = validate_assets(path, tmp_path)
    assert report["valid"] is False
    assert report["images"][1]["reason_code"] == "DUPLICATE_NORMALIZED_RGB"
    assert report["summary"]["normalized_rgb_exact_duplicate_analysis_performed"] is True
    assert report["summary"]["visual_near_duplicate_analysis_performed"] is False


def test_committed_r2_schema_matches_model() -> None:
    path = Path(__file__).resolve().parents[1] / "schemas/r2_dataset.schema.json"
    assert json.loads(path.read_text()) == R2Dataset.model_json_schema()
