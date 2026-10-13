"""Operational R4 human packages, imports, frozen recovery and guarded evaluation.

No training, tuning, downloads, production connection, automatic human approval
or inferred GT is implemented. Use the already authorized R3 source download
recipe separately when original local assets must be restored.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from ..r2_common import JSONDict, read_json, write_json_new
from ..r3.acceptance import create_artifact_manifest, verify_artifacts
from .freeze import lock_predictions
from .package import build_package, clean_editor
from .recovery import recover_predictions
from .reference import import_task, qualify_reference, review_pair
from .report import business_report
from .scoring import evaluate_qualified

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]


def inputs() -> tuple[JSONDict, JSONDict, JSONDict]:
    return (
        read_json(ROOT / "evidence/r3/pilot_dataset_manifest.json"),
        read_json(ROOT / "evidence/r4/human_annotation_package.json"),
        read_json(ROOT / "evidence/r4/prediction_freeze.json"),
    )


def run_acceptance(output: Path, *, skip_tests: bool = False) -> JSONDict:
    if output.exists():
        raise ValueError("OUTPUT_ALREADY_EXISTS")
    output.mkdir(parents=True)
    dataset, package, lock = inputs()
    predictions = recover_predictions()
    recovery = []
    receipts = read_json(ROOT / "evidence/r3/model_inference.json")
    for receipt in receipts["model_runs"]:
        key = receipt["model_key"]
        sha = write_json_new(output / ("predictions-" + key + ".json"), predictions[key])
        if sha != receipt["prediction_file_sha256"]:
            raise ValueError("ORIGINAL_SERIALIZED_PREDICTION_HASH_MISMATCH")
        recovery.append(
            {
                "model": key,
                "file_sha256": sha,
                "canonical_hash": predictions[key]["prediction_hash"],
            }
        )
    evaluation = evaluate_qualified(dataset, package, lock, predictions, run_coco=True)
    if evaluation["status"] != "NOT_EVALUABLE" or evaluation["qualified_gt_images"]:
        raise ValueError("UNSUPPLIED_HUMAN_GT_MUST_NOT_SCORE")
    business_report(evaluation, output / "business-report")
    reviews = review_pair(dataset, package, None, None)
    write_json_new(output / "human_review_pending.json", reviews)
    r2 = subprocess.run(
        [
            sys.executable,
            "-m",
            "research.blueberry_vision.cli",
            "verify-artifacts",
            "--manifest",
            str(ROOT / "artifact_manifest.json"),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    r3 = verify_artifacts(ROOT / "evidence/r3/artifact_manifest.json", root=REPO)
    if r2.returncode or not r3["valid"]:
        raise ValueError("INHERITED_ARTIFACT_CHANGED")
    tests: JSONDict = {
        "status": "NOT_RUN_IN_THIS_COMMAND",
        "reason": "--skip-tests; run pytest separately",
    }
    if not skip_tests:
        command = [
            sys.executable,
            "-m",
            "pytest",
            "research/blueberry_vision/tests",
            "research/blueberry_vision/newtests",
            "research/blueberry_vision/r4tests",
            "-q",
        ]
        result = subprocess.run(command, cwd=REPO, capture_output=True, text=True)
        tests = {
            "command": command,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "status": "PASS" if result.returncode == 0 else "FAIL",
        }
        write_json_new(output / "test_results.json", tests)
        if result.returncode:
            raise ValueError("RESEARCH_TEST_FAILED_EVIDENCE_PRESERVED")
    acceptance = {
        "engineering_integrity": "PASS",
        "qualified_gt_available": False,
        "real_evaluation_complete": False,
        "task_result": "PARTIAL",
        "real_image_count": len(dataset["images"]),
        "unscorable_images": 8,
        "recovered_original_predictions": recovery,
        "r2_artifacts_exit_code": r2.returncode,
        "r3_artifacts_valid": r3["valid"],
        "tests": tests,
        "reference_hash": None,
        "real_metrics_status": "NOT_EVALUABLE",
        "human_reviews_completed": 0,
        "production_vision_approved": False,
        "company_orchard_accuracy_validated": False,
        "count_to_kg_calibrated": False,
        "current_season_actual_read": False,
    }
    write_json_new(output / "acceptance.json", acceptance)
    create_artifact_manifest(output, output_path=output / "artifact_manifest.json")
    if not verify_artifacts(output / "artifact_manifest.json")["valid"]:
        raise ValueError("ACCEPTANCE_ARTIFACT_HASH_FAILED")
    return acceptance


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    work = subs.add_parser("prepare-work")
    work.add_argument("--data-root", type=Path, required=True)
    work.add_argument("--output", type=Path, required=True)
    imp = subs.add_parser("import-human-draft")
    imp.add_argument("--bundle", type=Path, required=True)
    imp.add_argument("--role", choices=["A", "B"], required=True)
    imp.add_argument("--output", type=Path, required=True)
    pair = subs.add_parser("compare-human-drafts")
    pair.add_argument("--a", type=Path)
    pair.add_argument("--b", type=Path)
    pair.add_argument("--output", type=Path, required=True)
    ref = subs.add_parser("check-reference")
    ref.add_argument("--snapshot", type=Path, required=True)
    ref.add_argument("--approval", type=Path)
    ref.add_argument("--evidence-root", type=Path)
    ref.add_argument("--output", type=Path, required=True)
    recover = subs.add_parser("recover-predictions")
    recover.add_argument("--output", type=Path, required=True)
    score = subs.add_parser("evaluate-frozen")
    score.add_argument("--references", type=Path)
    score.add_argument("--approvals", type=Path)
    score.add_argument("--evidence-root", type=Path)
    score.add_argument("--coco", action="store_true")
    score.add_argument("--output", type=Path, required=True)
    report = subs.add_parser("render-business-report")
    report.add_argument("--evaluation", type=Path, required=True)
    report.add_argument("--output", type=Path, required=True)
    acceptance = subs.add_parser("run-r4-acceptance")
    acceptance.add_argument("--output", type=Path, required=True)
    acceptance.add_argument("--skip-tests", action="store_true")
    verify = subs.add_parser("verify-artifacts")
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--root", type=Path)
    args = parser.parse_args(argv)
    try:
        dataset, package, lock = inputs()
        if args.command == "prepare-work":
            args.output.mkdir(parents=True, exist_ok=False)
            write_json_new(args.output / "work_package.json", build_package(dataset))
            for slot in ("A", "B"):
                clean_editor(
                    package, dataset, args.data_root, args.output / (slot + ".html"), slot=slot
                )
            result: JSONDict = {
                "human_tasks_prepared": 2,
                "human_reviews_completed": 0,
                "package_hash": package["package_hash"],
            }
        elif args.command == "import-human-draft":
            result = import_task(dataset, package, read_json(args.bundle), args.role)
            write_json_new(args.output, result)
        elif args.command == "compare-human-drafts":
            result = review_pair(
                dataset,
                package,
                read_json(args.a) if args.a else None,
                read_json(args.b) if args.b else None,
            )
            write_json_new(args.output, result)
        elif args.command == "check-reference":
            snapshot = read_json(args.snapshot)
            image = next(
                row for row in dataset["images"] if row["image_id"] == snapshot["image_id"]
            )
            result = qualify_reference(
                image,
                package,
                snapshot,
                approval=read_json(args.approval) if args.approval else None,
                evidence_root=args.evidence_root,
            )
            write_json_new(args.output, result)
        elif args.command == "recover-predictions":
            args.output.mkdir(parents=True, exist_ok=False)
            result = {
                "files": {
                    key: write_json_new(args.output / (key + ".json"), value)
                    for key, value in recover_predictions().items()
                },
                "new_inference_executed": False,
            }
            write_json_new(args.output / "recovery_receipt.json", result)
        elif args.command == "evaluate-frozen":
            predictions = recover_predictions()
            # Original predictions are fixed/verified before any reference JSON is read.
            lock_predictions(
                dataset,
                package,
                read_json(ROOT / "evidence/r3/config_freeze.json"),
                predictions,
                read_json(ROOT / "evidence/r3/model_inference.json"),
            )
            result = evaluate_qualified(
                dataset,
                package,
                lock,
                predictions,
                references=read_json(args.references) if args.references else None,
                approvals=read_json(args.approvals).get("approvals") if args.approvals else None,
                evidence_root=args.evidence_root,
                run_coco=args.coco,
            )
            write_json_new(args.output, result)
        elif args.command == "render-business-report":
            business_report(read_json(args.evaluation), args.output)
            result = {"report_directory": str(args.output)}
        elif args.command == "run-r4-acceptance":
            result = run_acceptance(args.output, skip_tests=args.skip_tests)
        else:
            result = verify_artifacts(args.manifest, root=args.root)
            if not result["valid"]:
                print(json.dumps(result))
                return 1
        # Avoid printing full model outputs or GT records to the console.
        print(
            json.dumps(
                {
                    key: result[key]
                    for key in (
                        "task_result",
                        "engineering_integrity",
                        "real_metrics_status",
                        "human_tasks_prepared",
                        "status",
                        "report_hash",
                        "qc_hash",
                        "review_hash",
                        "qualified",
                        "valid",
                        "verified_count",
                        "new_inference_executed",
                        "report_directory",
                    )
                    if key in result
                },
                ensure_ascii=False,
            )
        )
        return 0
    except (ValueError, OSError, KeyError, StopIteration) as exc:
        print(json.dumps({"status": "ERROR", "reason_code": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
