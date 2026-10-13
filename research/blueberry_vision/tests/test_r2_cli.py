"""CPU CLI acceptance consumes generated pixels, fitted weights and independent metrics."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from research.blueberry_vision.cli import create_artifact_manifest, run_demo, verify_artifacts
from research.blueberry_vision.r2_common import read_json, seal, write_json_new


def test_small_complete_demo_actually_runs_every_stage(tmp_path: Path) -> None:
    output = tmp_path / "run"
    summary = run_demo(output, seed=91, images_per_split=2)
    assert summary["status"] == "PASS"
    assert summary["synthetic_image_count"] == 8
    assert summary["evaluation_scope"] == "SYNTHETIC_ONLY"
    assert summary["model_training_completed"] is True
    model = read_json(output / "model/model.json")
    assert any(abs(value) > 0.0001 for value in model["coefficients"])
    log = read_json(output / "model/training_log.json")
    assert len(log["used_image_ids"]) == 2
    baseline = read_json(output / "baseline_metrics.json")
    candidate = read_json(output / "trained_candidate_metrics.json")
    assert "ap_per_class" in baseline["metrics"]
    assert "ap_per_class" not in summary["baseline_metrics"]
    assert "ap_per_class" not in summary["candidate_metrics"]
    assert (
        summary["baseline_metrics"]["bbox_ap50_research_all_points"]
        == baseline["metrics"]["bbox_ap50_research_all_points"]
    )
    assert all(
        not isinstance(value, (dict, list)) for value in summary["baseline_metrics"].values()
    )
    assert baseline["evaluated_count"] == candidate["evaluated_count"] == 4
    assert baseline["prediction_hash"] != candidate["prediction_hash"]
    for report in [baseline, candidate]:
        errors = [row["signed_count_error"] for row in report["per_image_results"]]
        assert report["metrics"]["count_mae"] == sum(abs(error) for error in errors) / 4
        assert report["metrics"]["count_bias"] == sum(errors) / 4
    assert (output / "report/report.html").is_file()
    assert verify_artifacts(output / "artifact_manifest.json")["valid"] is True
    artifacts = read_json(output / "artifact_manifest.json")
    for entry in artifacts["files"]:
        path = output / entry["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
    with pytest.raises(FileExistsError):
        run_demo(output, seed=91, images_per_split=2)


def test_cli_generates_and_checks_actual_images(tmp_path: Path) -> None:
    output = tmp_path / "dataset"
    prefix = [sys.executable, "-m", "research.blueberry_vision.cli"]
    result = subprocess.run(
        [
            *prefix,
            "generate-demo",
            "--output",
            str(output),
            "--seed",
            "13",
            "--images-per-split",
            "1",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert len(list((output / "images").rglob("*.png"))) == 4
    checked = subprocess.run(
        [
            *prefix,
            "validate-assets",
            "--dataset",
            str(output / "dataset_manifest.json"),
            "--data-root",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert checked.returncode == 0
    assert json.loads(checked.stdout)["summary"]["validated_count"] == 4


def test_hash_verification_detects_tampering_and_path_escape(tmp_path: Path) -> None:
    from research.blueberry_vision.r2_common import seal, write_json_new

    asset = tmp_path / "example.txt"
    asset.write_text("synthetic artifact")
    manifest = seal(
        {
            "schema_version": "blueberry-vision-artifacts/2.0.0",
            "SYNTHETIC": True,
            "run_id": "hand-synthetic-golden",
            "files": [
                {
                    "path": "example.txt",
                    "size_bytes": asset.stat().st_size,
                    "sha256": hashlib.sha256(asset.read_bytes()).hexdigest(),
                }
            ],
        },
        "artifact_hash",
    )
    path = tmp_path / "artifact_manifest.json"
    write_json_new(path, manifest)
    assert verify_artifacts(path)["valid"] is True
    asset.write_text("tampered artifact")
    assert verify_artifacts(path)["valid"] is False
    escaped = seal(
        {
            "schema_version": "blueberry-vision-artifacts/2.0.0",
            "SYNTHETIC": True,
            "run_id": "hand-synthetic-golden",
            "files": [{"path": "../escape.txt", "size_bytes": 1, "sha256": "a" * 64}],
        },
        "artifact_hash",
    )
    escape_path = tmp_path / "bad.json"
    write_json_new(escape_path, escaped)
    with pytest.raises(ValueError, match="ARTIFACT_PATH_UNSAFE"):
        verify_artifacts(escape_path)


def artifact_golden(path: Path, ref: str, content: bytes) -> None:
    write_json_new(
        path,
        seal(
            {
                "schema_version": "blueberry-vision-artifacts/2.0.0",
                "SYNTHETIC": True,
                "run_id": "hand-synthetic-golden",
                "files": [
                    {
                        "path": ref,
                        "size_bytes": len(content),
                        "sha256": hashlib.sha256(content).hexdigest(),
                    }
                ],
            },
            "artifact_hash",
        ),
    )


@pytest.mark.parametrize("kind", ["file", "directory"])
def test_artifact_creation_rejects_symlink_before_hashing(tmp_path: Path, kind: str) -> None:
    run = tmp_path / "run"
    run.mkdir()
    outside = tmp_path / "synthetic-outside"
    outside.mkdir()
    (outside / "generated.txt").write_text("self-generated synthetic sentinel")
    if kind == "file":
        (run / "linked.txt").symlink_to(outside / "generated.txt")
    else:
        (run / "linked").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="ARTIFACT_PATH_UNSAFE"):
        create_artifact_manifest(run, "synthetic-review")
    assert not (run / "artifact_manifest.json").exists()


@pytest.mark.parametrize("kind", ["file", "directory", "manifest"])
def test_artifact_verification_rejects_symlink_inputs(tmp_path: Path, kind: str) -> None:
    run = tmp_path / "run"
    run.mkdir()
    outside = tmp_path / "synthetic-outside"
    outside.mkdir()
    content = b"self-generated synthetic sentinel"
    (outside / "generated.txt").write_bytes(content)
    if kind == "manifest":
        artifact_golden(outside / "generated-manifest.json", "generated.txt", content)
        (run / "artifact_manifest.json").symlink_to(outside / "generated-manifest.json")
    else:
        ref = "linked.txt" if kind == "file" else "linked/generated.txt"
        if kind == "file":
            (run / ref).symlink_to(outside / "generated.txt")
        else:
            (run / "linked").symlink_to(outside, target_is_directory=True)
        artifact_golden(run / "artifact_manifest.json", ref, content)
    with pytest.raises(ValueError, match="ARTIFACT_PATH_UNSAFE"):
        verify_artifacts(run / "artifact_manifest.json")


def test_artifact_hashing_streams_bounded_chunks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = b"synthetic streaming golden\n" * 50_000
    (tmp_path / "large.txt").write_bytes(content)
    original_read = os.read
    reads: list[int] = []

    def bounded_read(descriptor: int, count: int) -> bytes:
        assert count <= 65_536
        reads.append(count)
        return original_read(descriptor, count)

    def no_read_bytes(_path: Path) -> bytes:
        raise AssertionError("unbounded Path.read_bytes must not be used")

    monkeypatch.setattr(os, "read", bounded_read)
    monkeypatch.setattr(Path, "read_bytes", no_read_bytes)
    manifest = create_artifact_manifest(tmp_path, "synthetic-stream")
    assert manifest["files"][0]["sha256"] == hashlib.sha256(content).hexdigest()
    assert verify_artifacts(tmp_path / "artifact_manifest.json")["valid"]
    assert len(reads) > 4


def test_artifact_file_change_during_hash_is_retained_as_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = b"synthetic artifact"
    target = tmp_path / "generated.txt"
    target.write_bytes(content)
    inode = target.stat().st_ino
    artifact_golden(tmp_path / "artifact_manifest.json", target.name, content)
    original_read = os.read
    changed = False

    def append_during_read(descriptor: int, count: int) -> bytes:
        nonlocal changed
        if os.fstat(descriptor).st_ino == inode and not changed:
            with target.open("ab") as stream:
                stream.write(b"-concurrent-synthetic-edit")
            changed = True
        return original_read(descriptor, count)

    monkeypatch.setattr(os, "read", append_during_read)
    report = verify_artifacts(tmp_path / "artifact_manifest.json")
    assert report["valid"] is False and report["verified_count"] == 0
    assert report["failures"][0]["reason_code"] == "ARTIFACT_CHANGED_DURING_READ"


def test_artifact_sparse_resource_limit_and_fifo_rejected(tmp_path: Path) -> None:
    import research.blueberry_vision.cli as cli

    with (tmp_path / "large.bin").open("wb") as stream:
        stream.truncate(cli.MAX_ARTIFACT_BYTES + 1)
    with pytest.raises(ValueError, match="ARTIFACT_BYTES_LIMIT"):
        create_artifact_manifest(tmp_path, "synthetic-resource-limit")
    (tmp_path / "large.bin").unlink()
    os.mkfifo(tmp_path / "pipe.txt")
    with pytest.raises(ValueError, match="ARTIFACT_NOT_REGULAR_FILE"):
        create_artifact_manifest(tmp_path, "synthetic-fifo")


@pytest.mark.parametrize(
    "field,value", [("size_bytes", True), ("sha256", "bad"), ("path", "a//b.txt")]
)
def test_artifact_declarations_strict_and_duplicates_rejected(
    tmp_path: Path, field: str, value: Any
) -> None:
    (tmp_path / "example.txt").write_bytes(b"a")
    artifact_golden(tmp_path / "original.json", "example.txt", b"a")
    data = read_json(tmp_path / "original.json")
    data["files"][0][field] = value
    write_json_new(tmp_path / "invalid.json", seal(data, "artifact_hash"))
    with pytest.raises(ValueError, match="ARTIFACT_(ENTRY_INVALID|PATH_UNSAFE)"):
        verify_artifacts(tmp_path / "invalid.json")
    data = read_json(tmp_path / "original.json")
    data["files"].append(dict(data["files"][0]))
    write_json_new(tmp_path / "duplicate.json", seal(data, "artifact_hash"))
    with pytest.raises(ValueError, match="DUPLICATE_ARTIFACT_PATH"):
        verify_artifacts(tmp_path / "duplicate.json")


def test_artifact_missing_and_nested_manifests_are_not_silently_ignored(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "artifact_manifest.json").write_text('{"SYNTHETIC":true}')
    manifest = create_artifact_manifest(tmp_path, "synthetic-nested-artifact")
    assert [entry["path"] for entry in manifest["files"]] == ["nested/artifact_manifest.json"]
    (nested / "artifact_manifest.json").unlink()
    report = verify_artifacts(tmp_path / "artifact_manifest.json")
    assert report["valid"] is False
    assert report["failures"] == [
        {"path": "nested/artifact_manifest.json", "reason_code": "ARTIFACT_MISSING"}
    ]


@pytest.mark.parametrize("command", ["run-baseline", "train-synthetic", "predict-synthetic"])
def test_standalone_pixel_commands_reject_cross_split_rgb_duplicate(
    tmp_path: Path, command: str
) -> None:
    from PIL import Image, PngImagePlugin

    from research.blueberry_vision.assets import load_asset, validate_assets
    from research.blueberry_vision.contracts import canonical_record_hash
    from research.blueberry_vision.synthetic import generate_dataset

    data_root = tmp_path / "dataset"
    manifest = generate_dataset(data_root, seed=9131, images_per_split=1)
    train, test = manifest["images"][0], manifest["images"][2]
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("comment", "self-generated alternate synthetic PNG encoding")
    with Image.open(data_root / train["original_asset_ref"]) as pixels:
        pixels.save(data_root / test["original_asset_ref"], pnginfo=metadata)
    binding = load_asset(data_root, test["original_asset_ref"]).metadata
    test.update(
        asset_sha256=binding["asset_sha256"], preprocessing_hash=binding["preprocessing_hash"]
    )
    test["record_hash"] = canonical_record_hash(test)
    altered = data_root / "altered_manifest.json"
    write_json_new(altered, seal(manifest, "manifest_hash"))
    assert not validate_assets(altered, data_root)["valid"]
    output = tmp_path / "output"
    arguments = [
        sys.executable,
        "-m",
        "research.blueberry_vision.cli",
        command,
        "--dataset",
        str(altered),
        "--data-root",
        str(data_root),
        "--output",
        str(output),
    ]
    if command == "predict-synthetic":
        arguments.extend(["--model", str(tmp_path / "must-not-be-read.json")])
    result = subprocess.run(arguments, capture_output=True, text=True, check=False)
    assert result.returncode == 2
    assert json.loads(result.stdout)["reason_code"] == "DATASET_ASSETS_REJECTED"
    assert not output.exists()
