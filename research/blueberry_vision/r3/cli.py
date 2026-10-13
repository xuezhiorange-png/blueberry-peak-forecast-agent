"""Actual offline R3 ingestion, annotation, integrity and evaluation commands."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from research.blueberry_vision.r2_common import JSONDict, read_json, seal, write_json_new

from .acceptance import run_acceptance, verify_artifacts
from .annotations import (
    adjudicate_annotations,
    compare_annotations,
    create_draft,
    export_coco,
    import_annotations,
    transition_review,
)
from .contracts import load_manifest
from .dedup import find_near_duplicates
from .evaluation import evaluate_real, freeze_r2_baselines, run_real_inference, validate_freeze
from .ingestion import audit_images, import_images
from .report import render_report
from .sources import discover_sources, download_blueberry_quality_sample, download_public_pilot
from .splits import append_exposure_event, build_split, load_exposure_ledger, seal_test


def _optional(path: Path | None) -> JSONDict | None:
    return None if path is None else read_json(path)


def _mapping(path: Path | None) -> dict[int, str] | None:
    if path is None:
        return None
    value = read_json(path)
    if any(not key.isdecimal() or not isinstance(label, str) for key, label in value.items()):
        raise ValueError("ANNOTATION_MAPPING_INVALID")
    result = {int(key): label for key, label in value.items()}
    if len(result) != len(value):
        raise ValueError("ANNOTATION_MAPPING_DUPLICATE")
    return result


def _objects(path: Path | None) -> list[JSONDict] | None:
    if path is None:
        return None
    rows = read_json(path).get("objects")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("ANNOTATION_OBJECTS_REQUIRED")
    return rows


def _review(args: argparse.Namespace) -> JSONDict:
    action = args.action
    if action == "create":
        if args.manifest is None or args.image_id is None or args.annotation_version is None:
            raise ValueError("ANNOTATION_CREATE_ARGUMENTS_REQUIRED")
        dataset = load_manifest(args.manifest)
        images = {row["image_id"]: row for row in dataset["images"]}
        if args.image_id not in images:
            raise ValueError("ANNOTATION_IMAGE_UNKNOWN")
        return create_draft(
            images[args.image_id],
            annotation_version=args.annotation_version,
            annotator_id=args.actor,
            objects=_objects(args.objects),
            workflow_mode=args.workflow_mode,
            provenance=_optional(args.provenance),
        )
    if args.snapshot is None:
        raise ValueError("ANNOTATION_SNAPSHOT_REQUIRED")
    snapshot = read_json(args.snapshot)
    if action == "transition":
        if args.state is None:
            raise ValueError("ANNOTATION_TARGET_STATE_REQUIRED")
        return transition_review(snapshot, args.state, actor_id=args.actor)
    if action == "export-coco":
        return export_coco(snapshot if "snapshots" in snapshot else [snapshot])
    if args.other is None:
        raise ValueError("ANNOTATION_SECOND_SNAPSHOT_REQUIRED")
    other = read_json(args.other)
    if action == "compare":
        return compare_annotations(snapshot, other, iou_threshold=args.iou_threshold)
    objects = _objects(args.objects)
    if objects is None or args.annotation_version is None:
        raise ValueError("ADJUDICATION_OBJECTS_AND_VERSION_REQUIRED")
    return adjudicate_annotations(
        snapshot,
        other,
        objects,
        adjudicator_id=args.actor,
        annotation_version=args.annotation_version,
        provenance=_optional(args.provenance),
    )


def _execute(args: argparse.Namespace) -> JSONDict:
    command = args.command
    if command == "discover-sources":
        registry = discover_sources(online=args.online)
        if args.download_commons is not None:
            source_ids = sorted(
                row["source_id"]
                for row in registry["sources"]
                if row["source_id"].startswith("commons-")
            )
            selected = download_public_pilot(registry, args.download_commons, source_ids)
            registry = seal(
                {
                    **registry,
                    "explicit_commons_sample_acquisition": {
                        "image_count": selected["image_count"],
                        "source_index_hash": selected["index_hash"],
                        "reference_status": selected["reference_status"],
                        "accuracy_status": "NOT_EVALUABLE_GT_MISSING",
                    },
                },
                "registry_hash",
            )
        if args.download_quality is not None:
            selected = download_blueberry_quality_sample(args.download_quality, image_count=4)
            registry = seal(
                {
                    **registry,
                    "explicit_public_sample_acquisition": {
                        "source_id": "zenodo-22148787",
                        "image_count": selected["image_count"],
                        "source_index_hash": selected["index_hash"],
                        "reference_status": selected["reference_status"],
                        "accuracy_status": "NOT_EVALUABLE_GT_QUALITY_PENDING",
                        "selected_archive_members_only": True,
                    },
                },
                "registry_hash",
            )
        return registry
    if command == "import-images":
        return import_images(
            args.data_root,
            args.source_index,
            args.registry,
            args.output_dir,
            max_images=args.max_images,
            max_total_bytes=args.max_total_bytes,
            coco=args.coco,
        )
    if command == "prepare-public-pilot":
        from .public_pilot import prepare_public_pilot

        return prepare_public_pilot(
            args.commons_root,
            args.quality_root,
            args.registry,
            args.supplement,
            args.output_dir,
            max_images=args.max_images,
            max_total_bytes=args.max_total_bytes,
        )
    if command == "audit-images":
        return audit_images(load_manifest(args.manifest), args.data_root)
    if command == "find-near-duplicates":
        return find_near_duplicates(load_manifest(args.manifest), args.data_root, args.threshold)
    if command == "import-annotations":
        return import_annotations(
            load_manifest(args.manifest),
            read_json(args.coco),
            annotation_version=args.annotation_version,
            category_mapping=_mapping(args.category_map),
            image_mapping=_mapping(args.image_map),
            provenance=_optional(args.provenance),
            annotator_id=args.actor,
            workflow_mode=args.workflow_mode,
        )
    if command == "review-annotations":
        return _review(args)
    if command == "build-split":
        return build_split(
            load_manifest(args.manifest),
            read_json(args.assignments),
            _optional(args.duplicates),
            split_version=args.split_version,
        )
    if command == "freeze-baselines":
        return freeze_r2_baselines()
    if command == "seal-test":
        return seal_test(
            load_manifest(args.manifest),
            read_json(args.split),
            _optional(args.annotations),
            read_json(args.freeze),
            ledger=args.ledger,
        )
    if command == "run-real-inference":
        frozen = read_json(args.freeze)
        validate_freeze(frozen)
        if args.ledger is not None and not load_exposure_ledger(args.ledger)["events"]:
            append_exposure_event(
                args.ledger,
                "CONFIG_FROZEN",
                {"freeze_hash": frozen["freeze_hash"]},
                artifact_path=args.freeze,
            )
        return run_real_inference(
            load_manifest(args.manifest),
            args.data_root,
            frozen,
            model_key=args.model,
            output_path=args.output,
            ledger_dir=args.ledger,
        )
    if command == "evaluate-real":
        return evaluate_real(
            load_manifest(args.manifest),
            read_json(args.predictions),
            _optional(args.annotations),
            _optional(args.split),
            _optional(args.test_seal),
            freeze=read_json(args.freeze),
            ledger=args.ledger,
            run_coco=args.coco,
        )
    if command == "render-real-report":
        return render_report(
            load_manifest(args.manifest),
            args.data_root,
            [read_json(path) for path in args.predictions],
            [read_json(path) for path in args.evaluations],
            _optional(args.annotations),
            args.output_dir,
            public_export=args.public_export,
            max_images=args.max_images,
        )
    if command == "verify-artifacts":
        return verify_artifacts(args.manifest, root=args.root)
    if command == "run-r3-acceptance":
        return run_acceptance(
            args.output_dir, run_tests=not args.skip_regression, run_coco=args.coco
        )
    raise ValueError("COMMAND_NOT_IMPLEMENTED")


def _arg(parser: argparse.ArgumentParser, name: str, *, required: bool = True) -> None:
    parser.add_argument(name, type=Path, required=required)


def _manifest(parser: argparse.ArgumentParser) -> None:
    _arg(parser, "--manifest")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Offline blueberry R3 research; no production services."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    discover = commands.add_parser(
        "discover-sources",
        help="Read persisted official-source review; --online explicitly refreshes metadata.",
    )
    discover.add_argument("--online", action="store_true")
    _arg(discover, "--download-commons", required=False)
    _arg(discover, "--download-quality", required=False)
    _arg(discover, "--output")
    importer = commands.add_parser(
        "import-images", help="Bind licensed PNG/JPEG bytes to external manifest."
    )
    for name in ("--data-root", "--source-index", "--registry", "--output-dir"):
        _arg(importer, name)
    _arg(importer, "--coco", required=False)
    importer.add_argument("--max-images", type=int, default=100)
    importer.add_argument("--max-total-bytes", type=int, default=500_000_000)
    pilot = commands.add_parser(
        "prepare-public-pilot",
        help="Merge licensed Commons/Quality pixel assets; keep candidate annotations separate.",
    )
    for name in ("--commons-root", "--quality-root", "--registry", "--supplement"):
        _arg(pilot, name)
    pilot.add_argument("--output", "--output-dir", dest="output_dir", type=Path, required=True)
    pilot.add_argument("--max-images", type=int, default=100)
    pilot.add_argument("--max-total-bytes", type=int, default=500_000_000)
    for name in ("audit-images", "find-near-duplicates"):
        sub = commands.add_parser(name)
        _manifest(sub)
        _arg(sub, "--data-root")
        _arg(sub, "--output")
        if name == "find-near-duplicates":
            sub.add_argument("--threshold", type=int, default=6)
    annotations = commands.add_parser(
        "import-annotations",
        help="Import COCO with provenance and mappings; controlled roundtrips retain originals.",
    )
    _manifest(annotations)
    _arg(annotations, "--coco")
    _arg(annotations, "--output")
    for name in ("--provenance", "--category-map", "--image-map"):
        _arg(annotations, name, required=False)
    annotations.add_argument("--annotation-version")
    annotations.add_argument("--actor", default="external-import")
    annotations.add_argument(
        "--workflow-mode",
        choices=("OFFLINE_SELF_ASSERTED", "SIMULATED_ENGINEERING"),
        default="OFFLINE_SELF_ASSERTED",
    )
    review = commands.add_parser(
        "review-annotations",
        help="Create, compare, transition, adjudicate or export drafts; no authenticated approval.",
    )
    review.add_argument(
        "--action",
        choices=("create", "transition", "compare", "adjudicate", "export-coco"),
        required=True,
    )
    for name in ("--snapshot", "--other", "--manifest", "--objects", "--provenance"):
        _arg(review, name, required=False)
    _arg(review, "--output")
    review.add_argument("--actor", required=True)
    review.add_argument("--image-id")
    review.add_argument("--annotation-version")
    review.add_argument("--state", choices=("SUBMITTED", "REVIEW_PENDING", "SEALED"))
    review.add_argument(
        "--workflow-mode",
        choices=("OFFLINE_SELF_ASSERTED", "SIMULATED_ENGINEERING"),
        default="OFFLINE_SELF_ASSERTED",
    )
    review.add_argument("--iou-threshold", type=float, default=0.5)
    splitter = commands.add_parser("build-split")
    _manifest(splitter)
    _arg(splitter, "--assignments")
    _arg(splitter, "--duplicates", required=False)
    _arg(splitter, "--output")
    splitter.add_argument("--split-version", default="1")
    frozen = commands.add_parser(
        "freeze-baselines", help="Freeze immutable R2 models plus preregistered R3 pixel adapter."
    )
    _arg(frozen, "--output")
    seal_parser = commands.add_parser("seal-test")
    _manifest(seal_parser)
    for name in ("--split", "--freeze", "--output"):
        _arg(seal_parser, name)
    _arg(seal_parser, "--annotations", required=False)
    _arg(seal_parser, "--ledger", required=False)
    infer = commands.add_parser(
        "run-real-inference",
        help="Pixels only; no GT argument. Predictions are saved before the exposure event.",
    )
    _manifest(infer)
    for name in ("--data-root", "--freeze", "--output"):
        _arg(infer, name)
    _arg(infer, "--ledger", required=False)
    infer.add_argument("--model", choices=("A", "B"), default="A")
    evaluate = commands.add_parser(
        "evaluate-real",
        help="Qualified GT + seal + exposure ledger required; otherwise NOT_EVALUABLE.",
    )
    _manifest(evaluate)
    for name in ("--predictions", "--freeze", "--output"):
        _arg(evaluate, name)
    for name in ("--annotations", "--split", "--test-seal", "--ledger"):
        _arg(evaluate, name, required=False)
    evaluate.add_argument(
        "--coco",
        action="store_true",
        help="Actually run optional official pycocotools; no renamed research AP.",
    )
    report = commands.add_parser("render-real-report")
    _manifest(report)
    for name in ("--data-root", "--output-dir"):
        _arg(report, name)
    report.add_argument("--predictions", nargs="+", type=Path, required=True)
    report.add_argument("--evaluations", nargs="+", type=Path, required=True)
    _arg(report, "--annotations", required=False)
    report.add_argument("--public-export", action="store_true")
    report.add_argument("--max-images", type=int, default=50)
    verifier = commands.add_parser("verify-artifacts")
    _manifest(verifier)
    _arg(verifier, "--root", required=False)
    acceptance = commands.add_parser(
        "run-r3-acceptance",
        help="Synthetic-only engineering; default runs R1/R2/R3 tests. No downloads.",
    )
    acceptance.add_argument("--output", "--output-dir", dest="output_dir", type=Path, required=True)
    acceptance.add_argument(
        "--skip-tests",
        "--skip-regression",
        dest="skip_regression",
        action="store_true",
        help="Record pipeline-only mode when tests were executed separately.",
    )
    acceptance.add_argument("--coco", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        output = getattr(args, "output", None)
        if output is not None and (output.exists() or output.is_symlink()):
            raise ValueError("OUTPUT_ALREADY_EXISTS")
        result = _execute(args)
        if output is not None and args.command != "run-real-inference":
            write_json_new(output, result)
        # Compact receipt; full indexed outputs stay in explicit files.
        if args.command == "verify-artifacts":
            print(json.dumps(result, sort_keys=True, allow_nan=False))
            return 0 if result["valid"] else 1
        if args.command == "run-r3-acceptance":
            print(json.dumps(result, sort_keys=True, allow_nan=False))
            return 0 if result["status"] == "PASS" else 1
        receipt: dict[str, Any] = {"status": "COMPLETE", "command": args.command}
        for key in (
            "purpose",
            "SYNTHETIC",
            "manifest_hash",
            "registry_hash",
            "annotations_hash",
            "split_hash",
            "freeze_hash",
            "test_seal_hash",
            "prediction_hash",
            "report_hash",
        ):
            if key in result:
                receipt[key] = result[key]
        if result.get("status") == "NOT_EVALUABLE":
            receipt["evaluation_status"] = "NOT_EVALUABLE"
            receipt["reason_codes"] = result.get("reason_codes", [])
        print(json.dumps(receipt, sort_keys=True, allow_nan=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError, subprocess.TimeoutExpired) as exc:
        code = getattr(exc, "code", None)
        if code is None:
            code = "OUTPUT_ALREADY_EXISTS" if isinstance(exc, FileExistsError) else str(exc)
        print(
            json.dumps(
                {"status": "ERROR", "command": args.command, "reason_code": code}, sort_keys=True
            )
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
