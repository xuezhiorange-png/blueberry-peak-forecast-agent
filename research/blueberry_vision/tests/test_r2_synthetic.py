"""Synthetic renderer tests use independent geometry and split/accounting assertions."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from research.blueberry_vision.r2_common import JSONDict, canonical_hash, file_hash, verify_seal
from research.blueberry_vision.synthetic import SCENE_TYPES, SPLITS, generate_dataset


@pytest.fixture(scope="module")
def dataset(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, JSONDict]:
    root = tmp_path_factory.mktemp("synthetic") / "dataset"
    return root, generate_dataset(root)


def test_default_covers_four_disjoint_splits_and_fourteen_scenes(
    dataset: tuple[Path, JSONDict],
) -> None:
    _, manifest = dataset
    images = manifest["images"]
    assert len(images) == 56
    assert manifest["SYNTHETIC"] is True
    assert manifest["image_files_present"] is True
    assert verify_seal(manifest, "manifest_hash")
    for split in SPLITS:
        records = [record for record in images if record["split"] == split]
        assert {record["scene_metadata"]["scene_type"] for record in records} == set(SCENE_TYPES)
        assert len(records) == 14
    for field in (
        "capture_session_id",
        "sampling_unit_id",
        "template_group_id",
        "near_duplicate_group_id",
    ):
        memberships: dict[str, set[str]] = {}
        for record in images:
            memberships.setdefault(record[field], set()).add(record["split"])
        assert all(len(splits) == 1 for splits in memberships.values())
    assert len({record["asset_sha256"] for record in images}) == 56


def test_generated_pngs_are_real_rgb_and_masks_bound_to_bytes(
    dataset: tuple[Path, JSONDict],
) -> None:
    root, manifest = dataset
    for record in manifest["images"]:
        path = root / record["original_asset_ref"]
        assert file_hash(path) == record["asset_sha256"]
        with Image.open(path) as image:
            assert image.format == "PNG"
            assert image.mode == "RGB"
            assert image.size == (record["image_width"], record["image_height"])
            assert np.asarray(image).std() > 4.0
        mask_path = root / record["training_mask_ref"]
        assert file_hash(mask_path) == record["training_mask_sha256"]
        with Image.open(mask_path) as mask:
            pixels = np.asarray(mask)
            assert mask.mode == "L"
            assert mask.size == (record["image_width"], record["image_height"])
            assert set(np.unique(pixels)) <= {0, 128, 255}
            assert (np.count_nonzero(pixels == 255) == 0) == (record["visible_count"] == 0)


def test_visible_annotation_bbox_and_accounting(dataset: tuple[Path, JSONDict]) -> None:
    _, manifest = dataset
    for record in manifest["images"]:
        assert record["visible_count"] == len(record["objects"])
        assert record["drawn_object_count"] == (
            record["visible_count"] + record["hidden_object_count"] + record["ignored_object_count"]
        )
        assert len({obj["object_id"] for obj in record["objects"]}) == record["visible_count"]
        for obj in record["objects"]:
            x1, y1, x2, y2 = obj["bbox_xyxy"]
            assert 0 <= x1 < x2 <= record["image_width"]
            assert 0 <= y1 < y2 <= record["image_height"]
        visibility = record["scene_metadata"]["rendered_object_visibility"]
        for obj in visibility:
            if obj["reference_status"] == "hidden":
                assert obj["visible_pixels"] == 0
            elif obj["reference_status"] == "ignored":
                assert obj["visible_pixels"] > 0
                assert obj["visible_fraction"] < 0.15 or obj["visible_pixels"] < 12
            else:
                assert obj["visible_fraction"] >= 0.15
                assert obj["visible_pixels"] >= 12


def test_empty_hidden_ignored_pressure_and_ood_are_explicit(dataset: tuple[Path, JSONDict]) -> None:
    _, manifest = dataset
    for split in SPLITS:
        records = {
            record["scene_metadata"]["scene_type"]: record
            for record in manifest["images"]
            if record["split"] == split
        }
        assert records["empty"]["visible_count"] == 0
        assert records["empty"]["objects"] == []
        assert records["empty"]["drawn_object_count"] == 0
        assert records["high_occlusion"]["hidden_object_count"] >= 1
        assert records["high_occlusion"]["ignored_object_count"] >= 1
        assert records["pressure"]["visible_count"] == 120
        assert records["pressure"]["drawn_object_count"] == 120
        assert records["edge_crop"]["scene_metadata"]["edge_cropped_objects"] >= 1
        assert all(
            record["scene_metadata"]["domain"] == ("ood" if split == "out_of_domain" else "regular")
            for record in records.values()
        )


def test_each_split_samples_actual_independent_template_geometry(
    dataset: tuple[Path, JSONDict],
) -> None:
    _, manifest = dataset
    for scene in SCENE_TYPES:
        records = [
            record
            for record in manifest["images"]
            if record["scene_metadata"]["scene_type"] == scene
        ]
        # IDs and seeds are deliberately excluded from this content hash.
        geometry = [record["scene_metadata"]["template_geometry_parameters"] for record in records]
        hashes = [canonical_hash(value) for value in geometry]
        assert len(set(hashes)) == 4
        assert hashes == [record["scene_metadata"]["template_geometry_hash"] for record in records]
        if scene in {"pressure", "edge_crop", "distractors", "touching"}:
            # Fruit positions and radii themselves change, not just background bytes.
            assert len({canonical_hash(value["fruit_shapes"]) for value in geometry}) == 4


def test_repeated_generation_same_seed_is_byte_and_manifest_deterministic(tmp_path: Path) -> None:
    first = generate_dataset(tmp_path / "first", seed=7, images_per_split=2)
    second = generate_dataset(tmp_path / "second", seed=7, images_per_split=2)
    assert first == second
    assert (tmp_path / "first/dataset_manifest.json").read_bytes() == (
        tmp_path / "second/dataset_manifest.json"
    ).read_bytes()
    changed = generate_dataset(tmp_path / "changed", seed=8, images_per_split=2)
    assert first["manifest_hash"] != changed["manifest_hash"]
    assert first["images"][0]["asset_sha256"] != changed["images"][0]["asset_sha256"]


def test_generator_refuses_overwrite(tmp_path: Path) -> None:
    root = tmp_path / "occupied"
    root.mkdir()
    sentinel = root / "retained.txt"
    sentinel.write_text("preserve", encoding="utf-8")
    with pytest.raises(ValueError, match="OUTPUT_DIRECTORY_NOT_EMPTY"):
        generate_dataset(root, images_per_split=1)
    assert sentinel.read_text(encoding="utf-8") == "preserve"


@pytest.mark.parametrize("count", [0, -1, True, 129])
def test_generator_rejects_invalid_dataset_size(tmp_path: Path, count: int) -> None:
    with pytest.raises(ValueError, match="IMAGES_PER_SPLIT_LIMIT"):
        generate_dataset(tmp_path / "bad", images_per_split=count)
