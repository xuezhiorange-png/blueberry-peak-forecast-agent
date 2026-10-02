"""Additive research calls in the existing application CLI; no API/database."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, TextIO

from backend.app.area_yield import m0_baseline
from backend.app.area_yield.base_product import AreaForecastProductRequest
from backend.app.core_forecast.cli import CoreForecastCliError


def register_m0_parser(parsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    root = parsers.add_parser(
        "m0-baseline", help="Research-only frozen M0; not production approval"
    )
    subs = root.add_subparsers(dest="command", required=True)
    train = subs.add_parser("train")
    train.add_argument("--training-input", required=True)
    train.add_argument("--manifest", required=True)
    train.add_argument("--output", required=True)
    predict = subs.add_parser("predict")
    predict.add_argument("--model", required=True)
    predict.add_argument("--input", required=True)
    predict.add_argument("--output", required=True)
    for name in ("issue", "import-actuals", "evaluate", "verify-seal"):
        operation = subs.add_parser(name, help="File-mode research records, never production")
        operation.add_argument("--store", required=True)
        if name in {"issue", "evaluate", "verify-seal"}:
            operation.add_argument("--model", required=True)
        if name != "issue":
            operation.add_argument("--seal-id", required=True)
        if name in {"issue", "import-actuals"}:
            operation.add_argument("--input", required=True)
        if name != "verify-seal":
            operation.add_argument("--test-clock", help="Explicit TEST_NOT_PROSPECTIVE only")
        if name == "issue":
            operation.add_argument("--registry", required=True)
            operation.add_argument("--registry-sha256", required=True)
            operation.add_argument("--model-id", required=True)
            operation.add_argument("--authorization", required=True)
        if name in {"issue", "evaluate"}:
            operation.add_argument("--parent-id")
        if name == "evaluate":
            operation.add_argument("--actual-id", required=True)
            operation.add_argument("--metric-contract", required=True)
            operation.add_argument("--revision-reason")


def _research_record_command(args: argparse.Namespace, stdout: TextIO) -> None:
    from backend.app.area_yield import research_records_r2 as records

    root = Path(args.store)
    clock = datetime.fromisoformat(args.test_clock) if getattr(args, "test_clock", None) else None
    if args.command == "issue":
        allowed = {
            Path(name).resolve()
            for name in (args.model, args.registry, args.input, args.authorization)
        }
        if args.parent_id:
            allowed.update(p.resolve() for p in (root / "predictions").glob("*/record.json"))
            allowed.update(p.resolve() for p in (root / "predictions").glob("*/completion.json"))
        authorization = records.read(Path(args.authorization))
        if authorization.get("source", {}).get("raw_source_path"):
            allowed.add(Path(authorization["source"]["raw_source_path"]).resolve())
        _inference_guard(allowed)
        path = records.issue(
            root,
            Path(args.registry),
            args.registry_sha256,
            Path(args.model),
            args.model_id,
            records.read(Path(args.input)),
            authorization,
            parent_id=args.parent_id,
            test_clock=clock,
        )
    elif args.command == "import-actuals":
        path = records.import_actuals(
            root,
            args.seal_id,
            records.read(Path(args.input)),
            test_clock=clock,
        )
    elif args.command == "evaluate":
        path = records.evaluate(
            root,
            args.seal_id,
            args.actual_id,
            args.metric_contract,
            Path(args.model),
            test_clock=clock,
            parent_id=args.parent_id,
            revision_reason=args.revision_reason,
        )
    else:
        payload = records.load_prediction(root, args.seal_id, Path(args.model))
        stdout.write(json.dumps({"status": "VERIFIED", "seal_hash": payload["record_hash"]}) + "\n")
        return
    if args.command == "issue":
        allowed.add(path.resolve())
    stdout.write(json.dumps({"record_path": str(path), "id": records.read(path)["id"]}) + "\n")


def _inference_guard(allowed: set[Path]) -> None:
    protected = Path(__file__).resolve().parents[3] / "artifacts"

    def audit(event: str, event_args: tuple[Any, ...]) -> None:
        if event != "open" or not isinstance(event_args[0], (str, bytes)):
            return
        name = event_args[0]
        path = Path(name.decode() if isinstance(name, bytes) else name).resolve()
        mode = event_args[1]
        if isinstance(mode, str) and any(v in mode for v in ("w", "a", "x")):
            return
        if path in allowed:
            return
        if path.is_dir():
            return  # Directory fsync for atomic R2 publication, not a data read.
        if path.suffix.lower() in {".csv", ".xls", ".xlsx", ".jsonl"} or path.is_relative_to(
            protected
        ):
            raise PermissionError("M0_INFERENCE_FORBIDDEN_DATA_READ")

    sys.addaudithook(audit)


def dispatch_m0(args: argparse.Namespace, stdout: TextIO) -> None:
    try:
        if args.command in {"issue", "import-actuals", "evaluate", "verify-seal"}:
            _research_record_command(args, stdout)
            return
        if args.command == "train":
            path = Path(args.training_input)
            payload = path.read_bytes()
            manifest_path = Path(args.manifest)
            manifest = json.loads(manifest_path.read_text())
            sha = hashlib.sha256(payload).hexdigest()
            if sha != manifest["training_input_sha256"]:
                raise ValueError("TRAINING_INPUT_HASH_MISMATCH")
            samples = json.loads(payload)
            for sample in samples:
                sample["dates"] = [date.fromisoformat(d) for d in sample["dates"]]
            if len(samples) != manifest["base_season_count"]:
                raise ValueError("TRAINING_COUNT_MISMATCH")
            model = m0_baseline.fit(
                samples,
                training_input_sha256=sha,
                training_manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            )
            m0_baseline.save_model(Path(args.output), model)
            stdout.write(
                json.dumps(
                    {
                        "status": "TRAINED_AND_SAVED",
                        "artifact_hash": model["artifact_hash"],
                        "count": len(samples),
                    }
                )
                + "\n"
            )
            return
        model_path, input_path = Path(args.model).resolve(), Path(args.input).resolve()
        allowed = {model_path, input_path}
        _inference_guard(allowed)
        model = m0_baseline.load_model(model_path)
        payload = json.loads(input_path.read_text())
        requests = payload if isinstance(payload, list) else [payload]
        output = [
            m0_baseline.predict(model, AreaForecastProductRequest.model_validate(p))
            for p in requests
        ]
        result = output if isinstance(payload, list) else output[0]
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        data = (
            json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2) + "\n"
        ).encode()
        with target.open("xb") as stream:
            stream.write(data)
        stdout.write(
            json.dumps(
                {
                    "status": "LOADED_AND_PREDICTED",
                    "request_count": len(requests),
                    "inference_data_read_guard_active": True,
                }
            )
            + "\n"
        )
    except (ValueError, OSError, KeyError, TypeError) as exc:
        raise CoreForecastCliError("M0_RESEARCH_BASELINE_ERROR", str(exc), exit_code=2) from exc
