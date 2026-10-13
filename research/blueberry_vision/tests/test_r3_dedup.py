"""Perceptual similarity is candidate evidence, never proof of fruit identity."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from research.blueberry_vision.r2_common import seal
from research.blueberry_vision.r3.contracts import DatasetError
from research.blueberry_vision.r3.dedup import dhash_rgb, find_near_duplicates, review_duplicate
from research.blueberry_vision.r3.ingestion import import_images


def fixture_dataset(tmp_path: Path) -> tuple[dict[str, Any], Path]:
    root = tmp_path / "images"
    root.mkdir()
    gradient = np.zeros((64, 64, 3), dtype=np.uint8)
    gradient[:, :, 0] = np.arange(64, dtype=np.uint8)[None, :] * 4
    gradient[:, :, 1] = np.arange(64, dtype=np.uint8)[:, None] * 4
    gradient[:, :, 2] = 90
    image = Image.fromarray(gradient)
    image.save(root / "one.png")
    meta = PngInfo()
    meta.add_text("encoder", "different metadata")
    image.save(root / "two.png", pnginfo=meta)
    image.resize((32, 32)).save(root / "resized.png")
    image.crop((8, 8, 56, 56)).save(root / "crop.png")
    index = {
        "dataset_id": "dedup",
        "dataset_version": "1",
        "purpose": "SYNTHETIC_ENGINEERING",
        "SYNTHETIC": True,
        "source_id": "renderer",
        "images": None,
    }
    registry = {
        "sources": [
            {
                "source_id": "renderer",
                "purpose": "SYNTHETIC_ENGINEERING",
                "SYNTHETIC": True,
                "license_status": "SYNTHETIC_AUTHORITY",
                "research_use": True,
                "model_training": True,
                "redistribution": True,
                "commercial_use": False,
                "license_id": "TEST-FIXTURE",
                "license_url": "local:fixture",
                "attribution_required": False,
            }
        ]
    }
    return import_images(root, index, registry, tmp_path / "import"), root


def test_dhash_stable_and_manual_golden() -> None:
    rgb = np.zeros((8, 9, 3), dtype=np.uint8)
    assert dhash_rgb(rgb) == "0000000000000000"
    rgb[:] = np.arange(9, dtype=np.uint8)[None, :, None] * 20
    assert dhash_rgb(rgb) == "0000000000000000"
    assert dhash_rgb(rgb[:, ::-1]) == "ffffffffffffffff"


def test_different_encodings_proven_pixels_but_hash_candidate_requires_review(
    tmp_path: Path,
) -> None:
    data, root = fixture_dataset(tmp_path)
    report = find_near_duplicates(data, root)
    assert report["summary"]["candidate_pair_count"] > 0
    pixel_edges = [edge for edge in report["edges"] if edge["relation"] == "NORMALIZED_RGB_EXACT"]
    assert len(pixel_edges) == 1 and pixel_edges[0]["status"] == "CONFIRMED"
    candidates = [edge for edge in report["edges"] if edge["relation"] == "PERCEPTUAL_SIMILARITY"]
    assert candidates and all(edge["status"] == "PENDING" for edge in candidates)
    assert any(edge["comparison"] == "CENTER_CROP_DHASH" for edge in candidates)
    assert all(row["image_id"] for row in report["images"])


def test_review_retains_old_report_and_identity_is_not_authenticated(tmp_path: Path) -> None:
    data, root = fixture_dataset(tmp_path)
    original = find_near_duplicates(data, root)
    edge = next(row for row in original["edges"] if row["status"] == "PENDING")
    changed = review_duplicate(
        original,
        edge["edge_id"],
        "REJECTED",
        "offline-reviewer",
        "2026-10-13T00:00:00Z",
        "different subjects",
    )
    assert original["edges"][0] is not changed["edges"][0]
    revised = next(row for row in changed["edges"] if row["edge_id"] == edge["edge_id"])
    assert revised["status"] == "REJECTED"
    assert revised["review"]["identity_authenticated"] is False
    assert changed["parent_duplicate_hash"] == original["duplicate_hash"]


@pytest.mark.parametrize("threshold", [-1, 65, True])
def test_invalid_threshold_rejected(tmp_path: Path, threshold: int) -> None:
    data, root = fixture_dataset(tmp_path)
    with pytest.raises(DatasetError, match="DEDUP_THRESHOLD_INVALID"):
        find_near_duplicates(data, root, threshold=threshold)


def test_dedup_uses_sealed_pixel_bindings_and_retains_failures(tmp_path: Path) -> None:
    data, root = fixture_dataset(tmp_path)
    (root / "one.png").write_bytes(b"bad")
    report = find_near_duplicates(data, root)
    failed = [row for row in report["images"] if row["status"] == "FAILED"]
    assert len(failed) == 1 and failed[0]["reason_code"] == "ASSET_HASH_MISMATCH"


@pytest.mark.parametrize("unknown", ["UNKNOWN", "UNRESOLVED", "N/A", "NONE", ""])
def test_unknown_metadata_is_not_a_capture_group(tmp_path: Path, unknown: str) -> None:
    data, root = fixture_dataset(tmp_path)
    for row in data["images"]:
        row["capture_session_id"] = unknown or None
        row["source_batch_id"] = unknown or None
        row["parent_image_id"] = unknown or None
        row.update(seal(row, "record_hash"))
    data = seal(data, "manifest_hash")
    report = find_near_duplicates(data, root)
    assert report["summary"]["metadata_link_count"] == 0


def test_unknown_session_dedup_to_split_allows_distinct_images(tmp_path: Path) -> None:
    from research.blueberry_vision.r3.splits import build_split

    data, root = fixture_dataset(tmp_path)
    # Replace two images with independently textured pixels whose dHash differs.
    for image_number, row in enumerate(data["images"][:2]):
        pixels = np.random.default_rng(image_number + 50).integers(
            0, 256, (32, 32, 3), dtype=np.uint8
        )
        Image.fromarray(pixels).save(root / row["asset_ref"])
    index = {
        "dataset_id": data["dataset_id"],
        "dataset_version": data["dataset_version"],
        "purpose": data["purpose"],
        "SYNTHETIC": data["SYNTHETIC"],
        "images": [
            {
                "image_id": row["image_id"],
                "source_id": row["source_id"],
                "asset_ref": row["asset_ref"],
                "capture_session_id": "UNKNOWN",
            }
            for row in data["images"][:2]
        ],
    }
    new = import_images(root, index, {"sources": data["sources"]}, tmp_path / "new")
    report = find_near_duplicates(new, root, threshold=0)
    assert report["edges"] == []
    assignments = {new["images"][0]["image_id"]: "TRAIN", new["images"][1]["image_id"]: "TEST"}
    split = build_split(new, assignments, report)
    assert len(split["groups"]) == 2
    assert split["association_edges"] == []
    assert {row["split"] for row in split["records"]} == {"TRAIN", "TEST"}
