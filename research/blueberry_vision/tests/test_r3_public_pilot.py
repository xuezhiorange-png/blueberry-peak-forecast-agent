"""Engineering fixtures for bounded public-pilot assembly; no real accuracy claim."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from research.blueberry_vision.r2_common import (
    file_hash,
    read_json,
    seal,
    verify_seal,
    write_json_new,
)
from research.blueberry_vision.r3.contracts import DatasetError
from research.blueberry_vision.r3.ingestion import import_images
from research.blueberry_vision.r3.public_pilot import prepare_public_pilot


@pytest.fixture
def pilot_inputs(tmp_path: Path) -> tuple[Path, Path, dict[str, Any], dict[str, Any]]:
    roots = [tmp_path / "commons-input", tmp_path / "quality-input"]
    sources = []
    for group, root, color in zip(
        ("commons", "quality"), roots, ((10, 30, 90), (30, 40, 110)), strict=True
    ):
        root.mkdir()
        Image.new("RGB", (20, 16), color).save(root / "fruit.png")
        source = {
            "source_id": group,
            "purpose": "PUBLIC_EXTERNAL_BENCHMARK",
            "SYNTHETIC": False,
            "license_id": "CC-BY-4.0",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "license_status": "LICENSE_VERIFIED",
            "research_use": True,
            "redistribution": True,
            "model_training": False,
            "commercial_use": False,
            "attribution_required": True,
            "creator": "Example fixture creator",
            "official_url": "https://example.org/engineering-fixture",
            "license_evidence": {"metadata_sha256": "a" * 64},
        }
        sources.append(source)
        row = {
            "image_id": group + "-one",
            "asset_ref": "fruit.png",
            "asset_sha256": file_hash(root / "fruit.png"),
            "image_width": 20,
            "image_height": 16,
            "source_id": group,
            "SYNTHETIC": False,
            "purpose": "PUBLIC_EXTERNAL_BENCHMARK",
            "observed_at": None,
            "reference_object_count": 7,
            "objects": [{"bbox": [1, 1, 5, 5]}],
            "annotation_sha256": "e" * 64,
            "source_provided_capture_date": "2001-04-01",
            "scene_metadata": {"reference_visible_count": 7},
        }
        if group == "quality":
            row.update(
                {
                    "original_asset_ref": "original.MPO.JPG",
                    "original_asset_sha256": "f" * 64,
                    "source_member": "publisher/data/raw/original.MPO.JPG",
                    "preprocessing": {
                        "preprocessing_version": "fixture-first-frame/1",
                        "preprocessing_hash": "d" * 64,
                        "original_asset_sha256": "f" * 64,
                        "derived_asset_sha256": row["asset_sha256"],
                        "selected_frame_index": 0,
                    },
                }
            )
        write_json_new(
            root / "source_index.json",
            {
                "dataset_id": group + "-fixture",
                "dataset_version": "1",
                "purpose": "PUBLIC_EXTERNAL_BENCHMARK",
                "SYNTHETIC": False,
                "retrieved_at": "2026-01-01T00:00:00Z",
                "images": [row],
            },
        )
    return roots[0], roots[1], {"sources": [sources[0]]}, {"sources": [sources[1]]}


def prepare(
    inputs: tuple[Path, Path, dict[str, Any], dict[str, Any]], output: Path, **kw: Any
) -> Any:
    return prepare_public_pilot(*inputs, output, **kw)


def test_copy_byte_identity_and_asset_only_index(
    pilot_inputs: tuple[Path, Path, dict[str, Any], dict[str, Any]], tmp_path: Path
) -> None:
    result = prepare(pilot_inputs, tmp_path / "result")
    index = result["source_index"]
    assert index["purpose"] == "PUBLIC_EXTERNAL_BENCHMARK" and index["SYNTHETIC"] is False
    assert result["image_count"] == 2
    assert verify_seal(index, "index_hash")
    assert verify_seal(result["source_registry"], "registry_hash")
    for row in index["images"]:
        assert row["asset_ref"].startswith(("commons/", "quality/"))
        original_root = pilot_inputs[0] if row["source_id"] == "commons" else pilot_inputs[1]
        assert (tmp_path / "result" / row["asset_ref"]).read_bytes() == (
            original_root / "fruit.png"
        ).read_bytes()
        assert row["observed_at"] is None
        assert row["base_identity"]["status"] == "UNRESOLVED"
        assert row["variety"] is None
        assert not ({"objects", "annotation_sha256", "reference_object_count"} & row.keys())
        assert "reference_visible_count" not in row["scene_metadata"]
    assert read_json(tmp_path / "result/source_index.json") == index
    assert read_json(tmp_path / "result/source_registry.json") == result["source_registry"]


def test_original_derivative_provenance_survives_real_import(
    pilot_inputs: tuple[Path, Path, dict[str, Any], dict[str, Any]], tmp_path: Path
) -> None:
    result = prepare(pilot_inputs, tmp_path / "result")
    dataset = import_images(
        tmp_path / "result",
        result["source_index"],
        result["source_registry"],
        tmp_path / "admission",
    )
    row = next(row for row in dataset["images"] if row["source_id"] == "quality")
    assert row["original_asset_sha256"] == "f" * 64
    assert row["original_asset_ref"] == "original.MPO.JPG"
    assert row["scene_metadata"]["parent_asset_sha256"] == "f" * 64
    assert row["scene_metadata"]["preprocessing"]["selected_frame_index"] == 0
    assert row["multiview_group_id"] is None
    assert row["source_batch_id"] == "public-source-batch-quality"
    assert dataset["sources"][0]["model_training"] is False
    assert not list((tmp_path / "result").rglob("*.JPG"))


def test_hash_does_not_depend_on_output_directory_or_retrieval_timestamp(
    pilot_inputs: tuple[Path, Path, dict[str, Any], dict[str, Any]], tmp_path: Path
) -> None:
    first = prepare(pilot_inputs, tmp_path / "one")
    for root in pilot_inputs[:2]:
        index = read_json(root / "source_index.json")
        index["retrieved_at"] = "2026-09-10T11:12:13Z"
        (root / "source_index.json").write_text(__import__("json").dumps(index))
    second = prepare(pilot_inputs, tmp_path / "two")
    assert first == second


@pytest.mark.parametrize(
    "which", ["root", "ancestor", "asset", "index", "output", "output_ancestor"]
)
def test_symlinks_rejected(
    pilot_inputs: tuple[Path, Path, dict[str, Any], dict[str, Any]], tmp_path: Path, which: str
) -> None:
    root, quality_root, registry, supplement = pilot_inputs
    output = tmp_path / "out"
    if which == "root":
        link = tmp_path / "alias"
        link.symlink_to(root, target_is_directory=True)
        root = link
    elif which == "ancestor":
        link = tmp_path / "alias"
        link.symlink_to(tmp_path, target_is_directory=True)
        root = link / "commons-input"
    elif which in {"asset", "index"}:
        path = root / ("fruit.png" if which == "asset" else "source_index.json")
        target = tmp_path / "relocated"
        path.rename(target)
        path.symlink_to(target)
    elif which == "output":
        output.symlink_to(root, target_is_directory=True)
    else:
        link = tmp_path / "out-parent"
        link.symlink_to(tmp_path, target_is_directory=True)
        output = link / "out"
    with pytest.raises(DatasetError):
        prepare((root, quality_root, registry, supplement), output)


@pytest.mark.parametrize(
    "bad_ref", ["../fruit.png", "/tmp/fruit.png", "fruit.gif", "nested/../fruit.png"]
)
def test_path_escape_or_format_rejected(
    pilot_inputs: tuple[Path, Path, dict[str, Any], dict[str, Any]], tmp_path: Path, bad_ref: str
) -> None:
    root = pilot_inputs[0]
    index = read_json(root / "source_index.json")
    index["images"][0]["asset_ref"] = bad_ref
    (root / "source_index.json").write_text(__import__("json").dumps(index))
    with pytest.raises(DatasetError):
        prepare(pilot_inputs, tmp_path / "out")


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("bad_hash", "ASSET_HASH_MISMATCH"),
        ("missing_hash", "IMAGE_HASH_REQUIRED"),
        ("bad_dimensions", "IMAGE_SIZE_MISMATCH"),
        ("synthetic", "IMAGE_PURPOSE_MISMATCH"),
        ("unverified", "SOURCE_LICENSE_NOT_VERIFIED"),
        ("research_denied", "SOURCE_RESEARCH_USE_NOT_ALLOWED"),
        ("conflicting", "SOURCE_AUTHORITY_CONFLICT"),
        ("invalid_registry_seal", "SOURCE_REGISTRY_HASH_MISMATCH"),
    ],
)
def test_bad_authority_bindings_fail_before_output(
    pilot_inputs: tuple[Path, Path, dict[str, Any], dict[str, Any]],
    tmp_path: Path,
    mutation: str,
    code: str,
) -> None:
    root = pilot_inputs[0]
    index = read_json(root / "source_index.json")
    if mutation == "bad_hash":
        index["images"][0]["asset_sha256"] = "b" * 64
    elif mutation == "missing_hash":
        del index["images"][0]["asset_sha256"]
    elif mutation == "bad_dimensions":
        index["images"][0]["image_width"] = 99
    elif mutation == "synthetic":
        index["images"][0]["SYNTHETIC"] = True
    elif mutation == "unverified":
        pilot_inputs[2]["sources"][0]["license_status"] = "LICENSE_UNVERIFIED"
    elif mutation == "research_denied":
        pilot_inputs[2]["sources"][0]["research_use"] = False
    elif mutation == "conflicting":
        copy_source = copy.deepcopy(pilot_inputs[2]["sources"][0])
        copy_source["redistribution"] = False
        pilot_inputs[3]["sources"].append(copy_source)
    else:
        pilot_inputs[2]["registry_hash"] = "b" * 64
    (root / "source_index.json").write_text(__import__("json").dumps(index))
    with pytest.raises(DatasetError, match=code):
        prepare(pilot_inputs, tmp_path / "out")
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("limit", ["images", "bytes"])
def test_limits_are_enforced_before_output(
    pilot_inputs: tuple[Path, Path, dict[str, Any], dict[str, Any]], tmp_path: Path, limit: str
) -> None:
    kwargs = {"max_images": 1} if limit == "images" else {"max_total_bytes": 1}
    with pytest.raises(DatasetError, match="PREPARE_IMAGES_LIMIT|PREPARE_BYTES_LIMIT"):
        prepare(pilot_inputs, tmp_path / "out", **kwargs)
    assert not (tmp_path / "out").exists()


def test_existing_output_is_not_modified(
    pilot_inputs: tuple[Path, Path, dict[str, Any], dict[str, Any]], tmp_path: Path
) -> None:
    output = tmp_path / "out"
    output.mkdir()
    (output / "previous.txt").write_text("preserve")
    with pytest.raises(DatasetError, match="OUTPUT_ALREADY_EXISTS"):
        prepare(pilot_inputs, output)
    assert (output / "previous.txt").read_text() == "preserve"


def test_timestamp_cannot_invent_verified_capture_authority(
    pilot_inputs: tuple[Path, Path, dict[str, Any], dict[str, Any]], tmp_path: Path
) -> None:
    root = pilot_inputs[0]
    index = read_json(root / "source_index.json")
    index["images"][0]["observed_at"] = "2001-04-01T00:00:00Z"
    (root / "source_index.json").write_text(__import__("json").dumps(index))
    with pytest.raises(DatasetError, match="CAPTURE_TIME_STATUS_MISMATCH"):
        prepare(pilot_inputs, tmp_path / "out")


def test_unselected_denied_source_remains_outside_output(
    pilot_inputs: tuple[Path, Path, dict[str, Any], dict[str, Any]], tmp_path: Path
) -> None:
    pilot_inputs[2]["sources"].append(
        {"source_id": "unverified-unselected", "license_status": "LICENSE_UNVERIFIED"}
    )
    registry_path = tmp_path / "registry.json"
    write_json_new(registry_path, seal(pilot_inputs[2], "registry_hash"))
    result = prepare_public_pilot(
        pilot_inputs[0], pilot_inputs[1], registry_path, pilot_inputs[3], tmp_path / "out"
    )
    assert len(result["source_registry"]["sources"]) == 2
    assert len(read_json(registry_path)["sources"]) == 2


def test_cli_prepares_actual_fixture_pixels_with_immutable_asset_index(
    pilot_inputs: tuple[Path, Path, dict[str, Any], dict[str, Any]], tmp_path: Path
) -> None:
    from research.blueberry_vision.r3.cli import main

    registry_path, supplement_path = tmp_path / "registry.json", tmp_path / "supplement.json"
    write_json_new(registry_path, seal(pilot_inputs[2], "registry_hash"))
    write_json_new(supplement_path, seal(pilot_inputs[3], "registry_hash"))
    output = tmp_path / "prepared"
    argv = [
        "prepare-public-pilot",
        "--commons-root",
        str(pilot_inputs[0]),
        "--quality-root",
        str(pilot_inputs[1]),
        "--registry",
        str(registry_path),
        "--supplement",
        str(supplement_path),
        "--output",
        str(output),
    ]
    assert main(argv) == 0
    index = read_json(output / "source_index.json")
    assert index["image_count"] == 2
    assert index["purpose"] == "PUBLIC_EXTERNAL_BENCHMARK" and index["SYNTHETIC"] is False
    assert verify_seal(index, "index_hash")
    assert (output / "commons").is_dir() and (output / "quality").is_dir()
    original_index_bytes = (output / "source_index.json").read_bytes()
    for row in index["images"]:
        assert (output / row["asset_ref"]).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        assert "reference_object_count" not in row
    assert main(argv) != 0
    assert (output / "source_index.json").read_bytes() == original_index_bytes
