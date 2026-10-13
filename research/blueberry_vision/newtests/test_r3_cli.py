"""Real CLI execution and independent artifact tamper/symlink rejection."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from research.blueberry_vision.r2_common import read_json, seal, write_json_new
from research.blueberry_vision.r3.acceptance import (
    create_artifact_manifest,
    run_acceptance,
    verify_artifacts,
)
from research.blueberry_vision.r3.cli import build_parser, main


def test_acceptance_executes_pixels_review_seal_both_models_and_report(tmp_path: Path) -> None:
    result = run_acceptance(tmp_path / "run", run_tests=False)
    assert result["status"] == "PASS"
    assert result["purpose"] == "SYNTHETIC_ENGINEERING"
    assert result["REAL_IMAGE_ACCURACY_VALIDATED"] is False
    assert result["regression_tests"]["status"] == "NOT_RUN_EXPLICIT_PIPELINE_ONLY"
    assert result["checks"]["artifact_verification"] is True
    assert result["checks"]["duplicate_candidates_found"] is True
    assert result["checks"]["cross_split_leakage_rejected"] is True
    assert result["checks"]["coco_round_trip"] is True
    assert result["checks"]["frozen_model_reloaded"] is True
    a = read_json(tmp_path / "run/evaluation_A.json")
    assert a["metrics"]["tp"] == 2
    assert a["metrics"]["fp"] == a["metrics"]["fn"] == 0
    assert a["metrics"]["count_mae"] == 0
    predictions = read_json(tmp_path / "run/predictions_A.json")
    assert [row["predicted_visible_fruit_count"] for row in predictions["images"]] == [1, 1, 0]
    assert (tmp_path / "run/review/report.html").is_file()
    assert verify_artifacts(tmp_path / "run/artifact_manifest.json")["valid"] is True
    with pytest.raises(ValueError, match="OUTPUT_ALREADY_EXISTS"):
        run_acceptance(tmp_path / "run", run_tests=False)


def test_acceptance_prediction_hash_is_path_and_clock_independent(tmp_path: Path) -> None:
    run_acceptance(tmp_path / "one", run_tests=False)
    run_acceptance(tmp_path / "two", run_tests=False)
    for name in ("predictions_A.json", "predictions_B.json", "dataset/dataset_manifest.json"):
        assert read_json(tmp_path / "one" / name) == read_json(tmp_path / "two" / name)


def test_artifacts_do_not_claim_real_files_are_synthetic(tmp_path: Path) -> None:
    (tmp_path / "real_manifest.json").write_text('{"SYNTHETIC": false}')
    manifest = create_artifact_manifest(tmp_path)
    assert manifest["purpose"] == "ENGINEERING_ARTIFACT_INDEX"
    assert "SYNTHETIC" not in manifest
    assert manifest["artifacts"][0]["path"] == "real_manifest.json"
    assert verify_artifacts(tmp_path / "artifact_manifest.json")["verified_count"] == 1


def test_artifact_changed_bytes_rejected(tmp_path: Path) -> None:
    (tmp_path / "file.txt").write_text("original")
    create_artifact_manifest(tmp_path)
    (tmp_path / "file.txt").write_text("modified")
    result = verify_artifacts(tmp_path / "artifact_manifest.json")
    assert result["valid"] is False
    assert result["failures"][0]["reason_code"] == "ARTIFACT_SHA256_MISMATCH"


@pytest.mark.parametrize("ref", ["../secret", "/etc/passwd", "a/../file", "a//file", "."])
def test_resealed_artifact_directory_traversal_rejected(tmp_path: Path, ref: str) -> None:
    (tmp_path / "file.txt").write_text("fixture")
    manifest = create_artifact_manifest(tmp_path)
    manifest["artifacts"][0]["path"] = ref
    rewritten = tmp_path / "invalid.json"
    write_json_new(rewritten, seal(manifest, "artifact_manifest_hash"))
    with pytest.raises(ValueError, match="ARTIFACT_PATH_UNSAFE"):
        verify_artifacts(rewritten)


@pytest.mark.parametrize("kind", ["file", "directory", "root", "ancestor", "manifest"])
def test_artifact_symlinks_rejected(tmp_path: Path, kind: str) -> None:
    root = tmp_path / "run"
    root.mkdir()
    (root / "file.txt").write_text("fixture")
    if kind in {"file", "directory"}:
        (root / "alias").symlink_to(root / "file.txt" if kind == "file" else root)
        with pytest.raises(ValueError, match="ARTIFACT_SYMLINK_FORBIDDEN"):
            create_artifact_manifest(root)
        return
    create_artifact_manifest(root)
    if kind == "manifest":
        (root / "alias.json").symlink_to(root / "artifact_manifest.json")
        target = root / "alias.json"
    elif kind == "root":
        (tmp_path / "alias").symlink_to(root, target_is_directory=True)
        target = tmp_path / "alias/artifact_manifest.json"
    else:
        (tmp_path / "alias").symlink_to(tmp_path, target_is_directory=True)
        target = tmp_path / "alias/run/artifact_manifest.json"
    with pytest.raises(ValueError, match="ARTIFACT_SYMLINK_FORBIDDEN"):
        verify_artifacts(target)


def test_artifact_duplicate_entries_and_size_limit_rejected(tmp_path: Path) -> None:
    (tmp_path / "file.txt").write_text("fixture")
    with pytest.raises(ValueError, match="ARTIFACT_RESOURCE_LIMIT"):
        create_artifact_manifest(tmp_path, max_total_bytes=1)
    manifest = create_artifact_manifest(tmp_path)
    manifest["artifacts"].append(dict(manifest["artifacts"][0]))
    rewritten = tmp_path / "invalid.json"
    write_json_new(rewritten, seal(manifest, "artifact_manifest_hash"))
    with pytest.raises(ValueError, match="ARTIFACT_PATH_DUPLICATE"):
        verify_artifacts(rewritten)


def test_artifact_named_pipe_is_rejected_without_blocking(tmp_path: Path) -> None:
    os.mkfifo(tmp_path / "pipe")
    with pytest.raises(ValueError, match="ARTIFACT_NOT_REGULAR_FILE"):
        create_artifact_manifest(tmp_path)


def test_artifact_manifest_uses_strict_bounded_json_reader(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"schema_version":"x", "schema_version":"y"}')
    with pytest.raises(ValueError, match="DUPLICATE_JSON_KEY"):
        verify_artifacts(manifest)
    manifest.write_text('{"number": NaN}')
    with pytest.raises(ValueError, match="NONFINITE_JSON_NUMBER"):
        verify_artifacts(manifest)


def test_all_required_commands_have_actual_handlers() -> None:
    parser = build_parser()
    commands = {
        "discover-sources",
        "import-images",
        "audit-images",
        "find-near-duplicates",
        "import-annotations",
        "review-annotations",
        "build-split",
        "seal-test",
        "run-real-inference",
        "evaluate-real",
        "render-real-report",
        "verify-artifacts",
        "run-r3-acceptance",
    }
    assert all(command in parser.format_help() for command in commands)


def test_individual_cli_commands_execute_the_same_actual_adapters(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run = tmp_path / "fixture"
    run_acceptance(run, run_tests=False)
    data_root = run / "assets"
    imported = tmp_path / "cli-import"
    assert (
        main(
            [
                "import-images",
                "--data-root",
                str(data_root),
                "--source-index",
                str(run / "source_index.json"),
                "--registry",
                str(run / "source_registry.json"),
                "--output-dir",
                str(imported),
            ]
        )
        == 0
    )
    manifest = imported / "dataset_manifest.json"
    for command in ("audit-images", "find-near-duplicates"):
        assert (
            main(
                [
                    command,
                    "--manifest",
                    str(manifest),
                    "--data-root",
                    str(data_root),
                    "--output",
                    str(tmp_path / f"{command}.json"),
                ]
            )
            == 0
        )
    annotations = tmp_path / "cli-annotations.json"
    assert (
        main(
            [
                "import-annotations",
                "--manifest",
                str(manifest),
                "--coco",
                str(run / "annotations_coco.json"),
                "--output",
                str(annotations),
            ]
        )
        == 0
    )
    assert (
        read_json(annotations)["annotations_hash"]
        == read_json(run / "annotations.json")["annotations_hash"]
    )
    assignments = tmp_path / "assignments.json"
    write_json_new(assignments, {"a-fruit": "TEST", "b-reencoded": "TEST", "c-empty": "TEST"})
    split = tmp_path / "cli-split.json"
    assert (
        main(
            [
                "build-split",
                "--manifest",
                str(manifest),
                "--assignments",
                str(assignments),
                "--duplicates",
                str(tmp_path / "find-near-duplicates.json"),
                "--output",
                str(split),
            ]
        )
        == 0
    )
    frozen = tmp_path / "cli-freeze.json"
    assert main(["freeze-baselines", "--output", str(frozen)]) == 0
    ledger = tmp_path / "cli-ledger"
    predictions = tmp_path / "cli-predictions.json"
    assert (
        main(
            [
                "run-real-inference",
                "--manifest",
                str(manifest),
                "--data-root",
                str(data_root),
                "--freeze",
                str(frozen),
                "--ledger",
                str(ledger),
                "--output",
                str(predictions),
            ]
        )
        == 0
    )
    test_seal = tmp_path / "cli-seal.json"
    assert (
        main(
            [
                "seal-test",
                "--manifest",
                str(manifest),
                "--split",
                str(split),
                "--annotations",
                str(annotations),
                "--freeze",
                str(frozen),
                "--ledger",
                str(ledger),
                "--output",
                str(test_seal),
            ]
        )
        == 0
    )
    evaluated = tmp_path / "cli-evaluated.json"
    assert (
        main(
            [
                "evaluate-real",
                "--manifest",
                str(manifest),
                "--predictions",
                str(predictions),
                "--annotations",
                str(annotations),
                "--split",
                str(split),
                "--test-seal",
                str(test_seal),
                "--freeze",
                str(frozen),
                "--ledger",
                str(ledger),
                "--output",
                str(evaluated),
            ]
        )
        == 0
    )
    assert read_json(evaluated)["metrics"]["tp"] == 2
    assert (
        main(
            [
                "render-real-report",
                "--manifest",
                str(manifest),
                "--data-root",
                str(data_root),
                "--predictions",
                str(predictions),
                "--evaluations",
                str(evaluated),
                "--annotations",
                str(annotations),
                "--output-dir",
                str(tmp_path / "cli-review"),
            ]
        )
        == 0
    )
    assert (tmp_path / "cli-review/report.html").is_file()
    draft = tmp_path / "draft.json"
    assert (
        main(
            [
                "review-annotations",
                "--action",
                "create",
                "--manifest",
                str(manifest),
                "--image-id",
                "c-empty",
                "--annotation-version",
                "cli-new-draft",
                "--actor",
                "simulated-cli-user",
                "--workflow-mode",
                "SIMULATED_ENGINEERING",
                "--output",
                str(draft),
            ]
        )
        == 0
    )
    assert read_json(draft)["visible_count"] is None
    # Unannotated is not a reviewed zero: submission must be rejected.
    assert (
        main(
            [
                "review-annotations",
                "--action",
                "transition",
                "--snapshot",
                str(draft),
                "--state",
                "SUBMITTED",
                "--actor",
                "simulated-cli-user",
                "--output",
                str(tmp_path / "must-not-submit.json"),
            ]
        )
        == 2
    )
    zero_objects = tmp_path / "zero-objects.json"
    write_json_new(zero_objects, {"objects": []})
    zero_draft = tmp_path / "zero-draft.json"
    assert (
        main(
            [
                "review-annotations",
                "--action",
                "create",
                "--manifest",
                str(manifest),
                "--image-id",
                "c-empty",
                "--objects",
                str(zero_objects),
                "--annotation-version",
                "explicit-reviewed-zero-candidate",
                "--actor",
                "simulated-cli-user",
                "--workflow-mode",
                "SIMULATED_ENGINEERING",
                "--output",
                str(zero_draft),
            ]
        )
        == 0
    )
    assert read_json(zero_draft)["visible_count"] == 0
    assert (
        main(
            [
                "review-annotations",
                "--action",
                "transition",
                "--snapshot",
                str(zero_draft),
                "--state",
                "SUBMITTED",
                "--actor",
                "simulated-cli-user",
                "--output",
                str(tmp_path / "submitted.json"),
            ]
        )
        == 0
    )
    assert read_json(tmp_path / "submitted.json")["review_status"] == "SUBMITTED"
    assert (
        main(
            [
                "review-annotations",
                "--action",
                "export-coco",
                "--snapshot",
                str(annotations),
                "--actor",
                "self-asserted-exporter",
                "--output",
                str(tmp_path / "exported.json"),
            ]
        )
        == 0
    )
    assert len(read_json(tmp_path / "exported.json")["annotations"]) == 2
    capsys.readouterr()


def test_cli_persisted_source_discovery_and_no_silent_overwrite(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "registry.json"
    assert main(["discover-sources", "--output", str(path)]) == 0
    registry = read_json(path)
    assert registry["fresh_network_verification"] is False
    assert len(registry["sources"]) >= 4
    assert main(["discover-sources", "--output", str(path)]) == 2
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["status"] == "ERROR"


def test_cli_quality_download_is_explicit_and_metadata_cannot_claim_gt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from research.blueberry_vision.r3 import cli

    calls = []

    def bounded_download(output_dir: Path, *, image_count: int) -> dict[str, object]:
        calls.append((output_dir, image_count))
        return {
            "image_count": 4,
            "index_hash": "c" * 64,
            "reference_status": "PUB_REFERENCE_PENDING_QUALITY_NOT_EVALUABLE",
        }

    monkeypatch.setattr(cli, "download_blueberry_quality_sample", bounded_download)
    output = tmp_path / "review.json"
    assert (
        main(
            [
                "discover-sources",
                "--download-quality",
                str(tmp_path / "data"),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert calls == [(tmp_path / "data", 4)]
    sample = read_json(output)["explicit_public_sample_acquisition"]
    assert sample["accuracy_status"] == "NOT_EVALUABLE_GT_QUALITY_PENDING"


def test_cli_commons_acquisition_has_explicit_scope_without_accuracy_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from research.blueberry_vision.r3 import cli

    calls = []

    def controlled_download(
        registry: dict[str, object], output_dir: Path, source_ids: list[str]
    ) -> dict[str, object]:
        calls.append((output_dir, source_ids))
        return {
            "image_count": 4,
            "index_hash": "b" * 64,
            "reference_status": "NO_HUMAN_REFERENCE_LABELS",
        }

    monkeypatch.setattr(cli, "download_public_pilot", controlled_download)
    output = tmp_path / "review.json"
    assert (
        main(
            [
                "discover-sources",
                "--download-commons",
                str(tmp_path / "images"),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert len(calls[0][1]) == 4
    assert all(source_id.startswith("commons-") for source_id in calls[0][1])
    assert (
        read_json(output)["explicit_commons_sample_acquisition"]["accuracy_status"]
        == "NOT_EVALUABLE_GT_MISSING"
    )


def test_cli_acceptance_and_verifier_exit_codes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "run"
    assert main(["run-r3-acceptance", "--output-dir", str(output), "--skip-regression"]) == 0
    assert main(["verify-artifacts", "--manifest", str(output / "artifact_manifest.json")]) == 0
    (output / "predictions_A.json").write_text("{}")
    assert main(["verify-artifacts", "--manifest", str(output / "artifact_manifest.json")]) == 1
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["valid"] is False
