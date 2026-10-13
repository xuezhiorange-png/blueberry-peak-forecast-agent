"""Offline engineering acceptance and bounded, symlink-safe artifact integrity.

Acceptance fixtures are synthetic. This module neither downloads real images nor
claims real-field accuracy. Artifact indexes describe files, not their image domain.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from PIL import Image, ImageDraw

from research.blueberry_vision.r2_common import (
    JSONDict,
    _finite_float,
    _reject_constant,
    _unique_keys,
    file_hash,
    read_json,
    seal,
    verify_seal,
    write_json_new,
)

ARTIFACT_VERSION = "blueberry-vision-r3-artifact-index/3.0.0"
ARTIFACT_MAX_FILES = 4096
ARTIFACT_MAX_BYTES = 100_000_000
ARTIFACT_MAX_SINGLE_BYTES = 50_000_000
PROJECT_ROOT = Path(__file__).resolve().parents[3]
VISION_ROOT = PROJECT_ROOT / "research/blueberry_vision"


def _safe_path(path: Path) -> Path:
    """Reject symlinks including root ancestors, rather than resolving them away."""
    if ".." in path.parts:
        raise ValueError("ARTIFACT_PATH_UNSAFE")
    absolute = path.absolute()
    for ancestor in (*reversed(absolute.parents), absolute):
        try:
            mode = ancestor.lstat().st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode):
            raise ValueError("ARTIFACT_SYMLINK_FORBIDDEN")
    return absolute


def _ref(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or value.startswith("/")
        or any(part in {"", ".", ".."} for part in value.split("/"))
        or "\x00" in value
    ):
        raise ValueError("ARTIFACT_PATH_UNSAFE")
    return value


@contextmanager
def _open_artifact(root: Path, ref: str) -> Iterator[int]:
    """Hold a regular-file descriptor opened through no-follow directory handles."""
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    directory_fd = root_fd
    opened: list[int] = []
    try:
        parts = _ref(ref).split("/")
        for part in parts[:-1]:
            directory_fd = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory_fd
            )
            opened.append(directory_fd)
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
        opened.append(fd)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("ARTIFACT_NOT_REGULAR_FILE")
        if before.st_size > ARTIFACT_MAX_SINGLE_BYTES:
            raise ValueError("ARTIFACT_RESOURCE_LIMIT")
        yield fd
    finally:
        for fd in reversed(opened):
            os.close(fd)
        os.close(root_fd)


def _digest(root: Path, ref: str) -> tuple[str, int]:
    """Read bounded regular files through no-follow directory file descriptors."""
    with _open_artifact(root, ref) as fd:
        before = os.fstat(fd)
        digest = hashlib.sha256()
        size = 0
        while chunk := os.read(fd, 65_536):
            size += len(chunk)
            if size > ARTIFACT_MAX_SINGLE_BYTES:
                raise ValueError("ARTIFACT_RESOURCE_LIMIT")
            digest.update(chunk)
        after = os.fstat(fd)
        if (
            before.st_size != size
            or after.st_size != before.st_size
            or after.st_mtime_ns != before.st_mtime_ns
            or after.st_ctime_ns != before.st_ctime_ns
        ):
            raise ValueError("ARTIFACT_CHANGED_DURING_READ")
        return digest.hexdigest(), size


def _read_artifact_json(root: Path, ref: str) -> JSONDict:
    """Reuse strict R2 JSON semantics while reading the same no-follow handle."""
    with _open_artifact(root, ref) as fd:
        before = os.fstat(fd)
        if before.st_size > 8_000_000:
            raise ValueError("JSON_SIZE_LIMIT")
        content = bytearray()
        while chunk := os.read(fd, 65_536):
            content.extend(chunk)
            if len(content) > 8_000_000:
                raise ValueError("JSON_SIZE_LIMIT")
        after = os.fstat(fd)
        if before.st_size != len(content) or (
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError("ARTIFACT_CHANGED_DURING_READ")
        value = json.loads(
            content,
            object_pairs_hook=_unique_keys,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
    if not isinstance(value, dict):
        raise ValueError("JSON_OBJECT_REQUIRED")
    return value


def create_artifact_manifest(
    root: Path,
    *,
    paths: list[str] | None = None,
    output_path: Path | None = None,
    max_total_bytes: int = ARTIFACT_MAX_BYTES,
) -> JSONDict:
    """Seal an explicit file inventory without falsely assigning an image domain.

    If paths are omitted, recursively index existing regular files; reject links.
    The output index itself is excluded to avoid a hash cycle. Later files are
    outside this declared snapshot; create a new versioned index to include them.
    """
    safe_root = _safe_path(root)
    if not safe_root.is_dir():
        raise ValueError("ARTIFACT_ROOT_NOT_DIRECTORY")
    if type(max_total_bytes) is not int or not 1 <= max_total_bytes <= ARTIFACT_MAX_BYTES:
        raise ValueError("ARTIFACT_RESOURCE_LIMIT")
    target = _safe_path(output_path or safe_root / "artifact_manifest.json")
    if not target.is_relative_to(safe_root):
        raise ValueError("ARTIFACT_OUTPUT_OUTSIDE_ROOT")
    excluded = target.relative_to(safe_root).as_posix()
    if paths is None:
        refs = []
        for directory, directories, files in os.walk(safe_root, followlinks=False):
            for name in (*directories, *files):
                item = Path(directory) / name
                if item.is_symlink():
                    raise ValueError("ARTIFACT_SYMLINK_FORBIDDEN")
            for name in files:
                ref = (Path(directory) / name).relative_to(safe_root).as_posix()
                if ref != excluded:
                    refs.append(ref)
                if len(refs) > ARTIFACT_MAX_FILES:
                    raise ValueError("ARTIFACT_RESOURCE_LIMIT")
    else:
        refs = [_ref(value) for value in paths]
    if len(refs) > ARTIFACT_MAX_FILES or len(set(refs)) != len(refs):
        raise ValueError("ARTIFACT_PATH_DUPLICATE_OR_LIMIT")
    if excluded in refs:
        raise ValueError("ARTIFACT_SELF_REFERENCE")
    rows = []
    total = 0
    for ref in sorted(refs):
        _safe_path(safe_root / _ref(ref))
        digest, size = _digest(safe_root, ref)
        total += size
        if total > max_total_bytes:
            raise ValueError("ARTIFACT_RESOURCE_LIMIT")
        rows.append({"path": ref, "sha256": digest, "size_bytes": size})
    result = seal(
        {
            "schema_version": ARTIFACT_VERSION,
            "purpose": "ENGINEERING_ARTIFACT_INDEX",
            "inventory_mode": "EXPLICIT_DECLARED_FILE_SNAPSHOT",
            "artifacts": rows,
            "artifact_count": len(rows),
            "total_bytes": total,
            "image_domain_inherited_from_each_data_contract": True,
        },
        "artifact_manifest_hash",
    )
    write_json_new(target, result)
    return result


def verify_artifacts(manifest_path: Path, *, root: Path | None = None) -> JSONDict:
    """Verify every declared entry; structural errors raise, changed files report.

    This is file integrity, not authenticated custody. Extra undeclared files do
    not become verified artifacts merely by existing next to the index.
    """
    safe_manifest = _safe_path(manifest_path)
    safe_root = _safe_path(root or manifest_path.parent)
    if not safe_root.is_dir() or not safe_manifest.is_relative_to(safe_root):
        raise ValueError("ARTIFACT_ROOT_OR_MANIFEST_INVALID")
    manifest = _read_artifact_json(safe_root, safe_manifest.relative_to(safe_root).as_posix())
    if (
        manifest.get("schema_version") != ARTIFACT_VERSION
        or manifest.get("purpose") != "ENGINEERING_ARTIFACT_INDEX"
        or "SYNTHETIC" in manifest
        or manifest.get("inventory_mode") != "EXPLICIT_DECLARED_FILE_SNAPSHOT"
        or not verify_seal(manifest, "artifact_manifest_hash")
    ):
        raise ValueError("ARTIFACT_MANIFEST_INVALID")
    rows = manifest.get("artifacts")
    if not isinstance(rows, list) or len(rows) > ARTIFACT_MAX_FILES:
        raise ValueError("ARTIFACT_RESOURCE_LIMIT")
    seen: set[str] = set()
    total = 0
    failures = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "sha256", "size_bytes"}:
            raise ValueError("ARTIFACT_ENTRY_INVALID")
        ref = _ref(row.get("path"))
        if ref in seen:
            raise ValueError("ARTIFACT_PATH_DUPLICATE")
        seen.add(ref)
        if safe_root / ref == safe_manifest:
            raise ValueError("ARTIFACT_SELF_REFERENCE")
        size = row.get("size_bytes")
        if type(size) is not int or not 0 <= size <= ARTIFACT_MAX_SINGLE_BYTES:
            raise ValueError("ARTIFACT_RESOURCE_LIMIT")
        if not isinstance(row.get("sha256"), str) or not re.fullmatch(
            r"[0-9a-f]{64}", row["sha256"]
        ):
            raise ValueError("ARTIFACT_SHA256_INVALID")
        total += size
        if total > ARTIFACT_MAX_BYTES:
            raise ValueError("ARTIFACT_RESOURCE_LIMIT")
        try:
            _safe_path(safe_root / ref)
            actual_hash, actual_size = _digest(safe_root, ref)
            if actual_hash != row["sha256"]:
                failures.append({"path": ref, "reason_code": "ARTIFACT_SHA256_MISMATCH"})
            elif actual_size != size:
                failures.append({"path": ref, "reason_code": "ARTIFACT_SIZE_MISMATCH"})
        except OSError:
            failures.append({"path": ref, "reason_code": "ARTIFACT_NOT_READABLE"})
    if manifest.get("artifact_count") != len(rows) or manifest.get("total_bytes") != total:
        raise ValueError("ARTIFACT_SUMMARY_MISMATCH")
    return {
        "valid": not failures,
        "verified_count": len(rows) - len(failures),
        "declared_count": len(rows),
        "failures": failures,
        "artifact_manifest_hash": manifest["artifact_manifest_hash"],
        "scope": "DECLARED_FILES_ONLY",
    }


def _fixture(root: Path) -> tuple[JSONDict, JSONDict, dict[str, list[JSONDict]]]:
    from .annotations import CANDIDATE_LABEL

    root.mkdir()
    fruit = Image.new("RGB", (64, 48), (50, 100, 40))
    ImageDraw.Draw(fruit).rectangle((10, 12, 19, 23), fill=(30, 50, 180))
    fruit.save(root / "fruit.png", compress_level=9)
    fruit.save(root / "fruit-reencoded.png", compress_level=1)
    Image.new("RGB", (64, 48), (50, 100, 40)).save(root / "empty.png", compress_level=9)
    source = {
        "source_id": "r3-offline-engineering-fixture",
        "purpose": "SYNTHETIC_ENGINEERING",
        "SYNTHETIC": True,
        "license_id": "LOCAL_SYNTHETIC_FIXTURE",
        "license_url": "https://example.invalid/synthetic-engineering-fixture-only",
        "license_status": "SYNTHETIC_AUTHORITY",
        "research_use": True,
        "model_training": False,
        "redistribution": True,
        "attribution_required": False,
    }
    objects = [
        {
            "object_id": "known-painted-fruit",
            "class_label": CANDIDATE_LABEL,
            "bbox_xyxy": [10, 12, 20, 24],
            "disposition": "TARGET",
        }
    ]
    records = []
    truth = {}
    for image_id, ref in (
        ("a-fruit", "fruit.png"),
        ("b-reencoded", "fruit-reencoded.png"),
        ("c-empty", "empty.png"),
    ):
        records.append(
            {
                "image_id": image_id,
                "asset_ref": ref,
                "asset_sha256": file_hash(root / ref),
                "source_id": source["source_id"],
                "scene_metadata": {"density": "sparse", "occlusion": "none", "lighting": "normal"},
            }
        )
        truth[image_id] = [] if image_id == "c-empty" else objects
    return (
        {
            "dataset_id": "r3-offline-synthetic-acceptance",
            "dataset_version": "3.0.0",
            "purpose": "SYNTHETIC_ENGINEERING",
            "SYNTHETIC": True,
            "images": records,
        },
        {"sources": [source]},
        truth,
    )


def _references(dataset: JSONDict, truth: dict[str, list[JSONDict]], history: Path) -> JSONDict:
    from .annotations import (
        adjudicate_annotations,
        annotation_bundle,
        compare_annotations,
        create_draft,
        save_snapshot,
        transition_review,
    )

    snapshots = []
    comparisons = []
    for image in dataset["images"]:
        versions = []
        for operator in ("simulated-a", "simulated-b"):
            draft = create_draft(
                image,
                annotation_version=f"{image['image_id']}-{operator}-v1",
                annotator_id=operator,
                objects=truth[image["image_id"]],
                workflow_mode="SIMULATED_ENGINEERING",
            )
            save_snapshot(history, draft)
            submitted = transition_review(draft, "SUBMITTED", actor_id=operator)
            save_snapshot(history, submitted)
            pending = transition_review(submitted, "REVIEW_PENDING", actor_id=operator)
            save_snapshot(history, pending)
            versions.append(pending)
        comparisons.append(compare_annotations(*versions))
        adjudicated = adjudicate_annotations(
            versions[0],
            versions[1],
            truth[image["image_id"]],
            adjudicator_id="simulated-arbiter",
            annotation_version=f"{image['image_id']}-simulated-reference-v1",
        )
        save_snapshot(history, adjudicated)
        snapshot = transition_review(adjudicated, "SEALED", actor_id="simulated-arbiter")
        save_snapshot(history, snapshot)
        snapshots.append(snapshot)
    write_json_new(
        history / "agreement.json",
        {
            "purpose": "SYNTHETIC_ENGINEERING",
            "human_annotation_agreement_validated": False,
            "simulated_comparisons": comparisons,
        },
    )
    return annotation_bundle(dataset, snapshots)


def _run_regressions() -> JSONDict:
    """Separate inherited regression from R3; unit acceptance never recurses here."""
    original = sorted(
        path
        for path in (VISION_ROOT / "tests").glob("test_*.py")
        if not path.name.startswith("test_r3_")
    )
    added = sorted(
        path
        for directory in (VISION_ROOT / "tests", VISION_ROOT / "newtests")
        for path in directory.glob("test_r3_*.py")
    )
    checks = []
    for name, paths in (("R1_R2_ORIGINAL", original), ("R3", added)):
        if not paths:
            raise ValueError("REGRESSION_SUITE_MISSING")
        process = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", *(str(path) for path in paths)],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        checks.append(
            {
                "suite": name,
                "exit_code": process.returncode,
                "stdout": process.stdout,
                "stderr": process.stderr,
            }
        )
    return {
        "status": "PASS" if all(row["exit_code"] == 0 for row in checks) else "FAIL",
        "checks": checks,
    }


def run_acceptance(output_dir: Path, *, run_tests: bool = True, run_coco: bool = False) -> JSONDict:
    """Execute the whole offline engineering path, with independent painted GT.

    The default reruns inherited and R3 pytest suites. ``run_tests=False`` is an
    explicitly recorded pipeline-only mode for an already-running test or CI job.
    No GT is available to inference; no training or network access occurs.
    """
    from .annotations import export_coco, import_annotations
    from .dedup import find_near_duplicates
    from .evaluation import (
        compact_metrics,
        evaluate_real,
        freeze_r2_baselines,
        match_reference,
        run_real_inference,
    )
    from .ingestion import audit_images, import_images
    from .report import render_report
    from .splits import append_exposure_event, build_split, seal_test

    _safe_path(output_dir)
    if output_dir.exists():
        raise ValueError("OUTPUT_ALREADY_EXISTS")
    regressions = _run_regressions() if run_tests else {"status": "NOT_RUN_EXPLICIT_PIPELINE_ONLY"}
    output_dir.mkdir(parents=True, exist_ok=False)
    index, registry, truth = _fixture(output_dir / "assets")
    write_json_new(output_dir / "source_index.json", index)
    write_json_new(output_dir / "source_registry.json", registry)
    dataset = import_images(output_dir / "assets", index, registry, output_dir / "dataset")
    quality = audit_images(dataset, output_dir / "assets")
    write_json_new(output_dir / "image_quality_report.json", quality)
    duplicate = find_near_duplicates(dataset, output_dir / "assets")
    write_json_new(output_dir / "duplicate_review.json", duplicate)
    leakage_rejected = False
    try:
        build_split(dataset, {"a-fruit": "TRAIN", "b-reencoded": "TEST"}, duplicate)
    except ValueError as exc:
        leakage_rejected = "CROSS_SPLIT" in str(exc) or "LEAKAGE" in str(exc)
    annotations = _references(dataset, truth, output_dir / "annotation_history")
    write_json_new(output_dir / "annotations.json", annotations)
    coco = export_coco(annotations)
    write_json_new(output_dir / "annotations_coco.json", coco)
    roundtrip = import_annotations(dataset, coco)
    split = build_split(dataset, {row["image_id"]: "TEST" for row in dataset["images"]}, duplicate)
    write_json_new(output_dir / "split_manifest.json", split)
    freeze = freeze_r2_baselines(output_dir / "baseline_freeze.json")
    predictions = []
    evaluations = []
    for model_key in ("A", "B"):
        ledger = output_dir / f"ledger_{model_key}"
        append_exposure_event(
            ledger,
            "CONFIG_FROZEN",
            {"freeze_hash": freeze["freeze_hash"]},
            artifact_path=output_dir / "baseline_freeze.json",
        )
        prediction = run_real_inference(
            dataset,
            output_dir / "assets",
            freeze,
            model_key=model_key,
            output_path=output_dir / f"predictions_{model_key}.json",
            ledger_dir=ledger,
        )
        test_seal = seal_test(
            dataset,
            split,
            annotations,
            freeze,
            ledger=ledger,
            output_path=output_dir / f"test_seal_{model_key}.json",
        )
        evaluation = evaluate_real(
            dataset,
            prediction,
            annotations,
            split,
            test_seal,
            freeze=freeze,
            ledger=ledger,
            run_coco=run_coco,
        )
        write_json_new(output_dir / f"evaluation_{model_key}.json", evaluation)
        predictions.append(prediction)
        evaluations.append(evaluation)
    review = render_report(
        dataset,
        output_dir / "assets",
        predictions,
        evaluations,
        annotations,
        output_dir / "review",
        public_export=True,
        max_preview_edge=64,
    )
    # Independent one-to-one duplicate and MAE/Bias arithmetic, not self-comparison.
    target = {
        "class_label": "CANDIDATE_VISIBLE_BLUEBERRY",
        "bbox_xyxy": [0, 0, 10, 10],
        "score": 1.0,
    }
    matched = match_reference([target], [target, {**target, "score": 0.5}])
    arithmetic = compact_metrics(
        [
            {
                "status": "EVALUATED",
                "reference_count": gt,
                "predicted_count": pred,
                "signed_count_error": pred - gt,
                "absolute_count_error": abs(pred - gt),
                "tp": min(gt, pred),
                "fp": max(pred - gt, 0),
                "fn": max(gt - pred, 0),
            }
            for gt, pred in ((3, 1), (2, 5), (2, 1))
        ]
    )
    checks: JSONDict = {
        "image_pixels_decoded": quality["summary"]["valid_count"] == 3,
        "duplicate_candidates_found": bool(duplicate["edges"]),
        "cross_split_leakage_rejected": leakage_rejected,
        "coco_round_trip": roundtrip["annotations_hash"] == annotations["annotations_hash"],
        "frozen_model_reloaded": bool(predictions[1]["images"][0]["detected_objects"])
        and predictions[1]["selected_model_hash"] == freeze["models"]["B"]["model_hash"],
        "pixel_only_inference": all(row["gt_consumed"] is False for row in predictions),
        "painted_reference_baseline_a": [
            row["predicted_visible_fruit_count"] for row in predictions[0]["images"]
        ]
        == [1, 1, 0]
        and evaluations[0]["metrics"]["tp"] == 2
        and evaluations[0]["metrics"]["count_mae"] == 0,
        "both_models_evaluated": all(row["status"] == "EVALUATED" for row in evaluations),
        "one_to_one_golden": (matched["tp"], matched["fp"], matched["fn"]) == (1, 1, 0),
        "mae_bias_golden": arithmetic["count_mae"] == 2 and arithmetic["count_bias"] == 0,
        "html_generated": (output_dir / "review/report.html").is_file()
        and read_json(output_dir / "review/report.json")["SYNTHETIC"] is True
        and review["embedded_count"] == 3,
        "production_approval_absent": all(
            snapshot["identity_authenticated"] is False and snapshot["business_approved"] is False
            for snapshot in annotations["snapshots"]
        ),
    }
    index_manifest = create_artifact_manifest(output_dir)
    verification = verify_artifacts(output_dir / "artifact_manifest.json")
    checks["artifact_verification"] = verification["valid"] is True
    result = {
        "task_id": "BLUEBERRY_VISION_R3_REAL_IMAGE_PILOT_AND_VALIDATION",
        "status": "PASS" if all(checks.values()) and regressions["status"] != "FAIL" else "FAIL",
        "purpose": "SYNTHETIC_ENGINEERING",
        "SYNTHETIC": True,
        "REAL_IMAGE_ACCURACY_VALIDATED": False,
        "REAL_ORCHARD_ACCURACY_APPROVED": False,
        "COUNT_TO_KG_CALIBRATED": False,
        "PRODUCTION_FORECAST_CHANGED": False,
        "checks": checks,
        "regression_tests": regressions,
        "artifact_manifest_hash": index_manifest["artifact_manifest_hash"],
        "artifact_scope": "Outputs existing before this administrative acceptance.json receipt",
        "evaluated_images_per_model": [row["metrics"]["evaluated_count"] for row in evaluations],
        "metrics_scope": "SYNTHETIC_ENGINEERING_ONLY_NOT_REAL_BLUEBERRY_ACCURACY",
    }
    write_json_new(output_dir / "acceptance.json", result)
    return result
