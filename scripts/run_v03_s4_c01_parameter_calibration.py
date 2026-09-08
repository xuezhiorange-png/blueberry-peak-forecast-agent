#!/usr/bin/env python3
"""Run the fail-closed Candidate 01 control-plane preflight.

The current repository deliberately has no durable historical incumbent daily
forecast artifact.  Consequently the official invocation stops before an
evaluation STARTED event.  Once a separately reviewed lawful authority exists,
the same manifest and journal interfaces are the only entry point for a
candidate runner; this script never invents a replacement authority.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.s4_candidate_execution import (  # noqa: E402
    AppendOnlyValidationJournal,
    Candidate01ContractError,
    Candidate01PreflightResult,
    build_candidate_01_manifest,
    candidate_01_execution_preflight,
    json_payload,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the S4-C01 parameter-calibration preflight")
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs/maturity_curve.yaml",
    )
    parser.add_argument(
        "--journal-path",
        type=Path,
        default=ROOT / "docs/v0-3/s4/evidence/s4-validation-evaluation-journal-v1.jsonl",
    )
    parser.add_argument("--execution-main-sha")
    parser.add_argument("--runner-commit-sha")
    parser.add_argument("--manifest-only", action="store_true")
    return parser


def _git(ref: str) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", ref],
        cwd=ROOT,
        text=True,
    ).strip()


def _repository_identity_blocker(
    *,
    execution_main_sha: str | None,
    runner_commit_sha: str | None,
) -> str | None:
    if not execution_main_sha or not runner_commit_sha:
        return "REPOSITORY_IDENTITY_ARGUMENT_MISSING"
    try:
        if _git("HEAD") != runner_commit_sha:
            return "REPOSITORY_IDENTITY_MISMATCH"
        if _git("origin/main") != execution_main_sha:
            return "REPOSITORY_IDENTITY_MISMATCH"
        if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip():
            return "REPOSITORY_NOT_CLEAN"
    except (OSError, subprocess.CalledProcessError):
        return "REPOSITORY_IDENTITY_UNAVAILABLE"
    return None


def _blocked_payload(
    *,
    blocker: str,
    reason_code: str,
    first_non_derivable_authority: str | None = None,
    manifest_hash: str | None = None,
    ledger_row_count: int = 0,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "EXECUTION_STATUS": "BLOCKED",
        "CANDIDATE_ID": "01_parameter_calibration",
        "CANDIDATE_01_EXECUTION_PREFLIGHT": "BLOCKED",
        "CANDIDATE_01_EXECUTION_BLOCK_REASON": reason_code,
        "BLOCKER": blocker,
        "REASON_CODE": reason_code,
        "FIRST_NON_DERIVABLE_AUTHORITY": first_non_derivable_authority,
        "CANDIDATE_01_PARAMETER_MANIFEST_FROZEN": manifest_hash is not None,
        "CANDIDATE_01_EXECUTION_AUTHORIZED": False,
        "CANDIDATE_01_EXECUTION_ADAPTER_USED": False,
        "CANDIDATE_01_EXECUTION_REACHED": False,
        "CANDIDATE_01_RUN_COUNT": ledger_row_count,
        "ACTUAL_VALIDATION_EVALUATION_COUNT": ledger_row_count,
        "REMAINING_GLOBAL_VALIDATION_BUDGET": 32 - ledger_row_count,
        "CURRENT_LEDGER_ROW_COUNT": ledger_row_count,
        "S4_CANDIDATE_EXPERIMENT_EXECUTED": False,
        "S4_METRIC_EXECUTION_PERFORMED": False,
        "TEST_EVALUATION_AUTHORIZED": False,
        "TEST_REMAINS_SEALED": True,
        "NO_VALIDATION_EVALUATION_STARTED": ledger_row_count == 0,
    }
    if manifest_hash is not None:
        payload["CANDIDATE_01_PARAMETER_MANIFEST_HASH"] = manifest_hash
    return payload


def _preflight_payload(result: Candidate01PreflightResult) -> dict[str, Any]:
    if result.status == "BLOCKED":
        return _blocked_payload(
            blocker=result.blocker or "CANDIDATE_01_EXECUTION_PREFLIGHT_BLOCKED",
            reason_code=result.reason_code or "CANDIDATE_01_EXECUTION_PREFLIGHT_BLOCKED",
            first_non_derivable_authority=result.first_non_derivable_authority,
            manifest_hash=result.manifest_hash,
            ledger_row_count=result.current_ledger_row_count,
        )
    return {
        "EXECUTION_STATUS": "PASS",
        "CANDIDATE_ID": "01_parameter_calibration",
        "CANDIDATE_01_EXECUTION_PREFLIGHT": "PASS",
        "CANDIDATE_01_PARAMETER_MANIFEST_FROZEN": True,
        "CANDIDATE_01_EXECUTION_AUTHORIZED": True,
        "CANDIDATE_01_EXECUTION_ADAPTER_USED": False,
        "CANDIDATE_01_EXECUTION_REACHED": False,
        "CANDIDATE_01_RUN_COUNT": result.current_ledger_row_count,
        "ACTUAL_VALIDATION_EVALUATION_COUNT": result.actual_validation_evaluation_count,
        "REMAINING_GLOBAL_VALIDATION_BUDGET": 32 - result.actual_validation_evaluation_count,
        "CURRENT_LEDGER_ROW_COUNT": result.current_ledger_row_count,
        "TEST_EVALUATION_AUTHORIZED": False,
        "TEST_REMAINS_SEALED": True,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        manifest = build_candidate_01_manifest(args.config)
    except (Candidate01ContractError, OSError, ValueError):
        print(
            json_payload(
                _blocked_payload(
                    blocker="CANDIDATE_01_MANIFEST_INVALID",
                    reason_code="CANDIDATE_01_MANIFEST_INVALID",
                )
            )
        )
        return 2

    if args.manifest_only:
        payload = manifest.payload()
        payload["CANDIDATE_01_PARAMETER_MANIFEST_HASH"] = manifest.manifest_hash
        payload["EXECUTION_STATUS"] = "MANIFEST_ONLY"
        print(json_payload(payload))
        return 0

    identity_blocker = _repository_identity_blocker(
        execution_main_sha=args.execution_main_sha,
        runner_commit_sha=args.runner_commit_sha,
    )
    if identity_blocker is not None:
        print(
            json_payload(
                _blocked_payload(
                    blocker=identity_blocker,
                    reason_code=identity_blocker,
                    manifest_hash=manifest.manifest_hash,
                )
            )
        )
        return 2

    journal = AppendOnlyValidationJournal(args.journal_path)
    try:
        result = candidate_01_execution_preflight(
            repo_root=ROOT,
            manifest=manifest,
            journal=journal,
        )
        payload = _preflight_payload(result)
    except Candidate01ContractError:
        payload = _blocked_payload(
            blocker="CANDIDATE_01_EXECUTION_PREFLIGHT_BLOCKED",
            reason_code="CANDIDATE_01_EXECUTION_PREFLIGHT_BLOCKED",
            manifest_hash=manifest.manifest_hash,
        )
        print(json_payload(payload))
        return 2
    print(json_payload(payload))
    return 0 if payload["EXECUTION_STATUS"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
