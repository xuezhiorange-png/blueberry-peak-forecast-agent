"""Unified, CPU-only synthetic research pipeline. Never accesses production services."""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

from research.blueberry_vision.r2_common import (
    JSONDict,
    canonical_hash,
    dataset_split_hash,
    file_hash,
    read_json,
    seal,
    verify_seal,
    write_json_new,
)

SPLITS = ("train", "validation", "test", "out_of_domain")


def _splits(values: list[str]) -> list[str]:
    if (
        not values
        or len(set(values)) != len(values)
        or any(value not in SPLITS for value in values)
    ):
        raise ValueError("INVALID_SPLITS")
    return values


def merge_prediction_bundles(manifest: JSONDict, bundles: list[JSONDict]) -> JSONDict:
    """Join actual per-split outputs while preserving their source seals and scope."""
    if not bundles:
        raise ValueError("PREDICTION_BUNDLES_REQUIRED")
    first = bundles[0]
    fields = ("model_name", "model_hash", "config_hash", "detector_version")
    records: list[JSONDict] = []
    seen: set[str] = set()
    for bundle in bundles:
        if not verify_seal(bundle, "prediction_hash"):
            raise ValueError("PREDICTION_HASH_MISMATCH")
        if bundle["dataset_manifest_hash"] != manifest["manifest_hash"]:
            raise ValueError("PREDICTION_DATASET_MISMATCH")
        if bundle["split_hash"] != manifest["split_hash"]:
            raise ValueError("PREDICTION_SPLIT_HASH_MISMATCH")
        if any(bundle[key] != first[key] for key in fields):
            raise ValueError("PREDICTION_MODEL_CONFIG_MISMATCH")
        for record in bundle["images"]:
            if record["image_id"] in seen:
                raise ValueError("DUPLICATE_PREDICTION_IMAGE")
            seen.add(record["image_id"])
            records.append(record)
    scope = [record for record in manifest["images"] if record["image_id"] in seen]
    return seal(
        {
            "schema_version": "blueberry-vision-predictions/2.0.0",
            "SYNTHETIC": True,
            "count_unit": "visible_fruit_per_image",
            "dataset_manifest_hash": manifest["manifest_hash"],
            "split_hash": manifest["split_hash"],
            "prediction_scope_hash": dataset_split_hash(scope),
            **{key: first[key] for key in fields},
            "source_prediction_hashes": [bundle["prediction_hash"] for bundle in bundles],
            "splits": [bundle["split"] for bundle in bundles],
            "images": sorted(records, key=lambda record: record["image_id"]),
        },
        "prediction_hash",
    )


def _classical(
    manifest: JSONDict, data_root: Path, splits: list[str], config: JSONDict
) -> JSONDict:
    from research.blueberry_vision.classical import predict_classical

    return merge_prediction_bundles(
        manifest,
        [predict_classical(manifest, data_root, split, config) for split in _splits(splits)],
    )


def _trained(
    manifest: JSONDict,
    data_root: Path,
    splits: list[str],
    model: JSONDict,
    config: JSONDict | None = None,
) -> JSONDict:
    from research.blueberry_vision.trainable import predict_trained

    return merge_prediction_bundles(
        manifest,
        [predict_trained(manifest, data_root, split, model, config) for split in _splits(splits)],
    )


def create_artifact_manifest(run_dir: Path, run_id: str) -> JSONDict:
    files: list[JSONDict] = []
    for path in sorted(run_dir.rglob("*")):
        if path.is_file() and path.name != "artifact_manifest.json":
            files.append(
                {
                    "path": path.relative_to(run_dir).as_posix(),
                    "size_bytes": path.stat().st_size,
                    "sha256": file_hash(path),
                }
            )
    result = seal(
        {
            "schema_version": "blueberry-vision-artifacts/2.0.0",
            "SYNTHETIC": True,
            "run_id": run_id,
            "files": files,
        },
        "artifact_hash",
    )
    write_json_new(run_dir / "artifact_manifest.json", result)
    return result


def verify_artifacts(manifest_path: Path) -> JSONDict:
    artifacts = read_json(manifest_path)
    if not verify_seal(artifacts, "artifact_hash"):
        raise ValueError("ARTIFACT_MANIFEST_HASH_MISMATCH")
    root = manifest_path.parent.resolve()
    failures: list[JSONDict] = []
    for entry in artifacts["files"]:
        ref = Path(entry["path"])
        path = (root / ref).resolve()
        if ref.is_absolute() or ".." in ref.parts or not path.is_relative_to(root):
            raise ValueError("ARTIFACT_PATH_UNSAFE")
        if not path.is_file():
            failures.append({"path": ref.as_posix(), "reason_code": "ARTIFACT_MISSING"})
        elif path.stat().st_size != entry["size_bytes"] or file_hash(path) != entry["sha256"]:
            failures.append({"path": ref.as_posix(), "reason_code": "ARTIFACT_BYTES_MISMATCH"})
    return {
        "valid": not failures,
        "verified_count": len(artifacts["files"]) - len(failures),
        "failures": failures,
        "artifact_hash": artifacts["artifact_hash"],
    }


def run_demo(output_dir: Path, seed: int = 20261013, images_per_split: int = 14) -> JSONDict:
    """Execute every algorithm afresh in a new directory; never serve cached answers."""
    from research.blueberry_vision.annotations import export_coco, import_coco
    from research.blueberry_vision.assets import load_dataset, validate_assets
    from research.blueberry_vision.classical import default_classical_config
    from research.blueberry_vision.evaluator import (
        compare_reports,
        default_evaluation_config,
        evaluate_predictions,
    )
    from research.blueberry_vision.report import render_report
    from research.blueberry_vision.synthetic import generate_dataset
    from research.blueberry_vision.trainable import (
        default_trained_inference_config,
        default_training_config,
        load_model,
        train_model,
    )

    if output_dir.exists():
        raise FileExistsError("OUTPUT_ALREADY_EXISTS")
    output_dir.mkdir(parents=True)
    dataset_dir = output_dir / "dataset"
    generate_dataset(dataset_dir, seed=seed, images_per_split=images_per_split)
    manifest = load_dataset(dataset_dir / "dataset_manifest.json")
    validation = validate_assets(dataset_dir / "dataset_manifest.json", dataset_dir)
    write_json_new(output_dir / "asset_validation.json", validation)
    if not validation["valid"]:
        raise ValueError("DATASET_ASSETS_REJECTED")
    classical_config = default_classical_config()
    training_config = {**default_training_config(), "seed": seed}
    inference_config = default_trained_inference_config()
    evaluation_config = default_evaluation_config()
    # Lock defaults before any official test inference. No test-driven threshold search.
    freeze = seal(
        {
            "classical": classical_config,
            "training": training_config,
            "inference": inference_config,
            "evaluation": evaluation_config,
            "selection_policy": "PRE_REGISTERED_DEFAULTS_NO_TEST_TUNING",
            "test_used_for_model_selection": False,
            "source_code_sha256": {
                name: file_hash(Path(__file__).parent / name)
                for name in ("classical.py", "trainable.py", "evaluator.py")
            },
        },
        "config_hash",
    )
    write_json_new(output_dir / "algorithm_config.json", freeze)
    model = train_model(manifest, dataset_dir, output_dir / "model", training_config)
    reloaded = load_model(output_dir / "model/model.json")
    if model != reloaded:
        raise ValueError("MODEL_RELOAD_MISMATCH")
    validation_predictions = _trained(
        manifest, dataset_dir, ["validation"], reloaded, inference_config
    )
    validation_report = evaluate_predictions(
        manifest,
        validation_predictions,
        ["validation"],
        evaluation_config,
    )
    write_json_new(output_dir / "validation_predictions.json", validation_predictions)
    write_json_new(output_dir / "validation_metrics.json", validation_report)
    chosen = ["test", "out_of_domain"]
    baseline_predictions = _classical(manifest, dataset_dir, chosen, classical_config)
    trained_predictions = _trained(manifest, dataset_dir, chosen, reloaded, inference_config)
    write_json_new(output_dir / "baseline_predictions.json", baseline_predictions)
    write_json_new(output_dir / "trained_candidate_predictions.json", trained_predictions)
    # Predictions are serialized before evaluator reads test references.
    baseline_report = evaluate_predictions(
        manifest, baseline_predictions, chosen, evaluation_config
    )
    trained_report = evaluate_predictions(manifest, trained_predictions, chosen, evaluation_config)
    write_json_new(output_dir / "baseline_metrics.json", baseline_report)
    write_json_new(output_dir / "trained_candidate_metrics.json", trained_report)
    comparison = compare_reports(baseline_report, trained_report)
    write_json_new(output_dir / "comparison.json", comparison)
    coco = export_coco(manifest)
    write_json_new(output_dir / "coco_detection.json", coco)
    write_json_new(output_dir / "coco_roundtrip.json", import_coco(coco))
    render_report(
        manifest,
        dataset_dir,
        [baseline_predictions, trained_predictions],
        [baseline_report, trained_report],
        output_dir / "report",
    )
    run_id = (
        "r2-"
        + canonical_hash(
            {
                "dataset_manifest_hash": manifest["manifest_hash"],
                "config_hash": freeze["config_hash"],
                "model_hash": model["model_hash"],
            }
        )[:20]
    )
    summary = seal(
        {
            "status": "PASS"
            if (
                baseline_report["evaluated_count"]
                == trained_report["evaluated_count"]
                == sum(record["split"] in chosen for record in manifest["images"])
                and baseline_report["failed_count"] == trained_report["failed_count"] == 0
            )
            else "PARTIAL",
            "run_id": run_id,
            "SYNTHETIC": True,
            "synthetic_image_count": len(manifest["images"]),
            "evaluation_scope": "SYNTHETIC_ONLY",
            "model_training_completed": True,
            "model_hash": model["model_hash"],
            "model_artifact_sha256": file_hash(output_dir / "model/model.json"),
            "dataset_manifest_hash": manifest["manifest_hash"],
            "baseline_metrics": baseline_report["metrics"],
            "candidate_metrics": trained_report["metrics"],
            "real_accuracy_validated": False,
            "visual_count_to_kg_validated": False,
            "production_forecast_changed": False,
            "report_path": "report/report.html",
        },
        "summary_hash",
    )
    write_json_new(output_dir / "run_summary.json", summary)
    create_artifact_manifest(output_dir, run_id)
    if not verify_artifacts(output_dir / "artifact_manifest.json")["valid"]:
        raise ValueError("ARTIFACT_VERIFICATION_FAILED")
    return summary


def _dataset_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("generate-demo", "run-demo"):
        child = commands.add_parser(command)
        child.add_argument("--output", type=Path, required=True)
        child.add_argument("--seed", type=int, default=20261013)
        child.add_argument("--images-per-split", type=int, default=14)
    assets = commands.add_parser("validate-assets")
    _dataset_arguments(assets)
    assets.add_argument("--output", type=Path)
    for command in ("run-baseline", "train-synthetic", "predict-synthetic"):
        child = commands.add_parser(command)
        _dataset_arguments(child)
        child.add_argument("--output", type=Path, required=True)
        child.add_argument("--config", type=Path)
        if command != "train-synthetic":
            child.add_argument("--splits", nargs="+", default=["test", "out_of_domain"])
        if command == "predict-synthetic":
            child.add_argument("--model", type=Path, required=True)
    evaluator = commands.add_parser("evaluate")
    evaluator.add_argument("--dataset", type=Path, required=True)
    evaluator.add_argument("--predictions", type=Path, required=True)
    evaluator.add_argument("--output", type=Path, required=True)
    evaluator.add_argument("--config", type=Path)
    evaluator.add_argument("--splits", nargs="+", default=["test", "out_of_domain"])
    report = commands.add_parser("render-report")
    _dataset_arguments(report)
    report.add_argument("--predictions", nargs="+", type=Path, required=True)
    report.add_argument("--evaluations", nargs="+", type=Path, required=True)
    report.add_argument("--output", type=Path, required=True)
    verifier = commands.add_parser("verify-artifacts")
    verifier.add_argument("--manifest", type=Path, required=True)
    for command in ("coco-export", "coco-import"):
        child = commands.add_parser(command)
        child.add_argument("--input", type=Path, required=True)
        child.add_argument("--output", type=Path, required=True)
    return parser


def _execute(args: argparse.Namespace) -> JSONDict:
    from research.blueberry_vision.assets import load_dataset, validate_assets

    if args.command == "run-demo":
        return run_demo(args.output, args.seed, args.images_per_split)
    if args.command == "generate-demo":
        from research.blueberry_vision.synthetic import generate_dataset

        result = generate_dataset(args.output, args.seed, args.images_per_split)
        return {
            "manifest_hash": result["manifest_hash"],
            "SYNTHETIC": True,
            "image_count": len(result["images"]),
            "manifest": "dataset_manifest.json",
        }
    if args.command == "validate-assets":
        result = validate_assets(args.dataset, args.data_root)
        if args.output is not None:
            write_json_new(args.output, result)
        return result
    if args.command == "verify-artifacts":
        return verify_artifacts(args.manifest)
    if args.command in {"coco-export", "coco-import"}:
        from research.blueberry_vision.annotations import export_coco, import_coco

        result = (
            export_coco(read_json(args.input))
            if args.command == "coco-export"
            else import_coco(read_json(args.input))
        )
    elif args.command == "run-baseline":
        from research.blueberry_vision.classical import default_classical_config

        config = read_json(args.config) if args.config else default_classical_config()
        result = _classical(load_dataset(args.dataset), args.data_root, args.splits, config)
    elif args.command == "train-synthetic":
        from research.blueberry_vision.trainable import default_training_config, train_model

        config = read_json(args.config) if args.config else default_training_config()
        return train_model(load_dataset(args.dataset), args.data_root, args.output, config)
    elif args.command == "predict-synthetic":
        from research.blueberry_vision.trainable import load_model

        inference_settings = read_json(args.config) if args.config else None
        result = _trained(
            load_dataset(args.dataset),
            args.data_root,
            args.splits,
            load_model(args.model),
            inference_settings,
        )
    elif args.command == "evaluate":
        from research.blueberry_vision.evaluator import evaluate_predictions

        result = evaluate_predictions(
            load_dataset(args.dataset),
            read_json(args.predictions),
            args.splits,
            read_json(args.config) if args.config else None,
        )
    elif args.command == "render-report":
        from research.blueberry_vision.report import render_report

        return render_report(
            load_dataset(args.dataset),
            args.data_root,
            [read_json(path) for path in args.predictions],
            [read_json(path) for path in args.evaluations],
            args.output,
        )
    else:
        raise ValueError("UNKNOWN_RESEARCH_COMMAND")
    write_json_new(args.output, result)
    return result


def main() -> int:
    import json

    # A reproducible CPU setting; no credentials, hostnames or timestamps enter model hashes.
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    args = _parser().parse_args()
    try:
        result = _execute(args)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        if isinstance(exc, FileExistsError):
            code = "OUTPUT_ALREADY_EXISTS"
        else:
            candidate = getattr(exc, "code", str(exc))
            code = (
                candidate
                if re.fullmatch(r"[A-Z][A-Z0-9_]+", candidate)
                else "RESEARCH_INPUT_INVALID"
            )
        print(json.dumps({"valid": False, "reason_code": code}, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return 0 if result.get("valid", True) else 2


if __name__ == "__main__":
    raise SystemExit(main())
