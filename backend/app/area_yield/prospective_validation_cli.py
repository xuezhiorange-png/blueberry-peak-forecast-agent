"""Thin E1 operations registered in the existing app CLI, TEST_ONLY only."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import TextIO

from backend.app.area_yield import prospective_validation as e1
from backend.app.area_yield.research_records import file_hash, read
from backend.app.core_forecast.cli import CoreForecastCliError


def register_e1_parser(parsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    resource = parsers.add_parser("v0-12-research", help="E1 TEST_ONLY; real issuance disabled")
    operations = resource.add_subparsers(dest="command", required=True)
    registration = operations.add_parser(
        "register-artifacts", help="E2 frozen R1 read-only verification"
    )
    registration.add_argument("--candidate", required=True)
    registration.add_argument("--baseline", required=True)
    registration.add_argument("--public-evidence", required=True)
    registration.add_argument("--output", required=True)
    for operation in ("pack-recovery", "verify-bundle", "restore-bundle", "audit-export"):
        recovery = operations.add_parser(operation, help="E3 local custody; never real issuance")
        if operation == "pack-recovery":
            for argument in (
                "candidate",
                "baseline",
                "receipt",
                "seal",
                "execution-contract",
                "public-evidence",
                "output",
            ):
                recovery.add_argument(f"--{argument}", required=True)
        else:
            recovery.add_argument("--bundle", required=True)
            if operation == "restore-bundle":
                recovery.add_argument("--output", required=True)
            if operation == "audit-export":
                for argument in ("restored", "registry", "drill-result", "store", "output"):
                    recovery.add_argument(f"--{argument}", required=True)
    for name in (
        "issue",
        "verify-seal",
        "import-actuals",
        "create-snapshot",
        "evaluate",
        "show-run",
    ):
        command = operations.add_parser(name)
        command.add_argument("--store", required=True)
        if name != "issue":
            command.add_argument("--forecast-id", required=True)
        if name in {"issue", "import-actuals"}:
            command.add_argument("--input", required=True)
            command.add_argument("--source", required=True)
        if name == "issue":
            command.add_argument("--registry", required=True)
            command.add_argument("--registry-hash", required=True)
            command.add_argument("--authorization", required=True)
        if name == "create-snapshot":
            command.add_argument("--revision-id", required=True)
        if name == "evaluate":
            command.add_argument("--snapshot-id", required=True)
            command.add_argument("--metric-contract", required=True)
        if name not in {"verify-seal", "show-run"}:
            command.add_argument(
                "--test-clock", required=True, help="Explicit TEST_NOT_PROSPECTIVE clock"
            )


def dispatch_e1(args: argparse.Namespace, stdout: TextIO) -> None:
    if args.command in {"pack-recovery", "verify-bundle", "restore-bundle", "audit-export"}:
        from backend.app.area_yield import recovery_bundle as recovery

        try:
            if args.command == "pack-recovery":
                result = recovery.pack(
                    Path(args.candidate),
                    Path(args.baseline),
                    Path(args.receipt),
                    Path(args.seal),
                    Path(args.execution_contract),
                    Path(args.public_evidence),
                    Path(args.output),
                )
            elif args.command == "verify-bundle":
                result = recovery.verify(Path(args.bundle))
            elif args.command == "restore-bundle":
                result = recovery.restore(Path(args.bundle), Path(args.output))
            else:
                result = recovery.audit_export(
                    Path(args.bundle),
                    Path(args.restored),
                    Path(args.registry),
                    Path(args.drill_result),
                    Path(args.store),
                    Path(args.output),
                )
            stdout.write(json.dumps(result, sort_keys=True) + "\n")
            return
        except (ValueError, KeyError, OSError, TypeError) as exc:
            raise CoreForecastCliError("V0_12_E3_REJECTED", str(exc), exit_code=2) from exc
    if args.command == "register-artifacts":
        from backend.app.area_yield.artifact_registration import register_pair

        try:
            result = register_pair(
                Path(args.candidate),
                Path(args.baseline),
                Path(args.public_evidence),
                Path(args.output),
            )
            stdout.write(json.dumps(result, sort_keys=True) + "\n")
            return
        except (ValueError, KeyError, OSError) as exc:
            raise CoreForecastCliError("V0_12_E2_REJECTED", str(exc), exit_code=2) from exc
    root = Path(args.store)
    clock = datetime.fromisoformat(args.test_clock) if getattr(args, "test_clock", None) else None
    try:
        if args.command == "issue":
            record = e1.create_research_forecast(
                root,
                Path(args.registry),
                args.registry_hash,
                read(Path(args.input)),
                Path(args.source),
                Path(args.authorization),
                clock=clock,
            )
        elif args.command == "import-actuals":
            record = e1.import_actuals(
                root, args.forecast_id, read(Path(args.input)), Path(args.source), clock=clock
            )
        elif args.command == "create-snapshot":
            record = e1.create_actual_snapshot(
                root, args.forecast_id, [args.revision_id], clock=clock
            )
        elif args.command == "evaluate":
            record = e1.evaluate_locked_forecast(
                root, args.forecast_id, args.snapshot_id, args.metric_contract, clock=clock
            )
        else:
            record = e1.verify_research_forecast(root, args.forecast_id)
        stdout.write(
            json.dumps(
                {
                    "id": record["id"],
                    "kind": record["kind"],
                    "seal_hash": record["record_hash"],
                    "test_only": True,
                    "record": record,
                },
                sort_keys=True,
            )
            + "\n"
        )
    except (ValueError, KeyError, OSError) as exc:
        raise CoreForecastCliError("V0_12_E1_REJECTED", str(exc), exit_code=2) from exc


def registry_hash(path: Path) -> str:
    return file_hash(path)


def main() -> None:
    # V0.11 pins the bytes of its launcher in a public replay manifest. Extend
    # its actual parser in memory rather than rewriting the historical launcher.
    from backend.app import cli as existing

    parser = existing._parser()
    subparsers = [
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    ]
    if len(subparsers) != 1:
        raise ValueError("EXISTING_CLI_EXTENSION_SEAM_CHANGED")
    register_e1_parser(subparsers[0])
    args = parser.parse_args()
    if args.resource != "v0-12-research":
        raise SystemExit(existing.run_cli())
    try:
        dispatch_e1(args, sys.stdout)
    except CoreForecastCliError as exc:
        sys.stderr.write(str(exc) + "\n")
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
