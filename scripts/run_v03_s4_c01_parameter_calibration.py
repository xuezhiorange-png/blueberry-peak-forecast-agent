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
import asyncio
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.s4_candidate_execution import (  # noqa: E402
    Candidate01ContractError,
    Candidate01PreflightResult,
    build_candidate_01_manifest,
    json_payload,
)
from backend.app.s4_candidate_execution_authority import (  # noqa: E402
    CANDIDATE_01_ID,
    S4CandidateExecutionAuthority,
)
from backend.app.s4_experiment import (  # noqa: E402
    EXPERIMENT_PLAN_VERSION,
    FROZEN_CANDIDATE_REGISTRY,
    GUARDRAIL_POLICY_HASH,
    GUARDRAIL_POLICY_VERSION,
    MAX_VALIDATION_EVALUATIONS,  # noqa: E402
    METRIC_CONTRACT_IDENTITY,
    METRIC_CONTRACT_VERSION,
    S4_A_EXPERIMENT_PLAN_HASH_BOUND,
    CandidateExecutionGateRequest,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the S4-C01 parameter-calibration preflight")
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs/maturity_curve.yaml",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="Isolated PostgreSQL URL for verified durable preflight state",
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
    canonical_ledger_started_evaluation_count: int = 0,
    legacy_reconciled_validation_debit: int = 0,
    effective_validation_evaluation_count: int = 0,
    remaining_validation_budget: int = MAX_VALIDATION_EVALUATIONS,
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
        "CANONICAL_LEDGER_ROW_COUNT": ledger_row_count,
        "CANONICAL_LEDGER_STARTED_EVALUATION_COUNT": canonical_ledger_started_evaluation_count,
        "LEGACY_RECONCILED_VALIDATION_DEBIT": legacy_reconciled_validation_debit,
        "LEGACY_UNLEDGERED_C01_STARTED_EVALUATION_COUNT": legacy_reconciled_validation_debit,
        "ACTUAL_VALIDATION_EVALUATION_COUNT": effective_validation_evaluation_count,
        "EFFECTIVE_VALIDATION_EVALUATIONS_CONSUMED": effective_validation_evaluation_count,
        "REMAINING_GLOBAL_VALIDATION_BUDGET": remaining_validation_budget,
        "REMAINING_EFFECTIVE_VALIDATION_BUDGET": remaining_validation_budget,
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
    reconciliation = result.budget_reconciliation
    canonical_started = (
        reconciliation.canonical_started_evaluation_count if reconciliation is not None else 0
    )
    legacy_debit = (
        reconciliation.legacy_unledgered_c01_started_evaluation_count
        if reconciliation is not None
        else 0
    )
    remaining_budget = (
        reconciliation.remaining_effective_validation_budget
        if reconciliation is not None
        else MAX_VALIDATION_EVALUATIONS - result.actual_validation_evaluation_count
    )
    if result.status == "BLOCKED":
        return _blocked_payload(
            blocker=result.blocker or "CANDIDATE_01_EXECUTION_PREFLIGHT_BLOCKED",
            reason_code=result.reason_code or "CANDIDATE_01_EXECUTION_PREFLIGHT_BLOCKED",
            first_non_derivable_authority=result.first_non_derivable_authority,
            manifest_hash=result.manifest_hash,
            ledger_row_count=result.current_ledger_row_count,
            canonical_ledger_started_evaluation_count=canonical_started,
            legacy_reconciled_validation_debit=legacy_debit,
            effective_validation_evaluation_count=result.actual_validation_evaluation_count,
            remaining_validation_budget=remaining_budget,
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
        "CANONICAL_LEDGER_ROW_COUNT": result.current_ledger_row_count,
        "CANONICAL_LEDGER_STARTED_EVALUATION_COUNT": canonical_started,
        "LEGACY_RECONCILED_VALIDATION_DEBIT": legacy_debit,
        "LEGACY_UNLEDGERED_C01_STARTED_EVALUATION_COUNT": legacy_debit,
        "ACTUAL_VALIDATION_EVALUATION_COUNT": result.actual_validation_evaluation_count,
        "EFFECTIVE_VALIDATION_EVALUATIONS_CONSUMED": result.actual_validation_evaluation_count,
        "REMAINING_GLOBAL_VALIDATION_BUDGET": remaining_budget,
        "REMAINING_EFFECTIVE_VALIDATION_BUDGET": remaining_budget,
        "CURRENT_LEDGER_ROW_COUNT": result.current_ledger_row_count,
        "TEST_EVALUATION_AUTHORIZED": False,
        "TEST_REMAINS_SEALED": True,
    }


def _durable_c01_request(manifest: Any) -> CandidateExecutionGateRequest:
    """Build a control-plane request; all live counts come from PostgreSQL."""

    return CandidateExecutionGateRequest(
        experiment_plan_version=EXPERIMENT_PLAN_VERSION,
        experiment_plan_hash=S4_A_EXPERIMENT_PLAN_HASH_BOUND,
        guardrail_policy_version=GUARDRAIL_POLICY_VERSION,
        guardrail_policy_hash=GUARDRAIL_POLICY_HASH,
        candidate_id=CANDIDATE_01_ID,
        candidate_run_ordinal=1,
        candidate_planned_run_count=4,
        candidate_actual_run_count=0,
        global_actual_evaluation_count=0,
        train_dataset_identity="0" * 64,
        validation_dataset_identity="0" * 64,
        actual_label_set_identity=None,
        exclusion_policy_identity=None,
        cutoff_policy_identity=None,
        forecast_horizon_set_identity=None,
        metric_contract_identity=METRIC_CONTRACT_IDENTITY,
        business_grain_set_identity=None,
        common_comparable_set_identity=None,
        metric_contract_version=METRIC_CONTRACT_VERSION,
        test_access_requested=False,
        test_sealed=True,
        parameter_manifest_hash=manifest.manifest_hash,
        code_commit_sha=None,
        random_seed=manifest.run(1).random_seed,
        evaluation_id="c01-preflight-only",
        candidate_execution_manifest_frozen=True,
        candidate_registry=FROZEN_CANDIDATE_REGISTRY,
        invocation_type="NORMAL_RUN",
    )


async def _run_durable_c01_preflight(
    *,
    database_url: str | None,
    manifest: Any,
) -> dict[str, Any]:
    if not database_url:
        return {
            "EXECUTION_STATUS": "BLOCKED",
            "CANDIDATE_ID": CANDIDATE_01_ID,
            "CANDIDATE_01_EXECUTION_PREFLIGHT": "BLOCKED",
            "BLOCKER": "POSTGRES_AUTHORITY_UNAVAILABLE",
            "REASON_CODE": "POSTGRES_AUTHORITY_UNAVAILABLE",
            "CANDIDATE_01_EXECUTION_AUTHORIZED": False,
            "CANDIDATE_01_EXECUTION_REACHED": False,
            "JSONL_LIVE_BUDGET_AUTHORITY": False,
            "RECONCILIATION_ARTIFACT_LIVE_BUDGET_AUTHORITY": False,
            "TEST_EVALUATION_AUTHORIZED": False,
            "TEST_REMAINS_SEALED": True,
        }
    try:
        engine = create_async_engine(database_url, pool_pre_ping=True)
    except Exception:
        return {
            "EXECUTION_STATUS": "BLOCKED",
            "CANDIDATE_ID": CANDIDATE_01_ID,
            "CANDIDATE_01_EXECUTION_PREFLIGHT": "BLOCKED",
            "BLOCKER": "POSTGRES_AUTHORITY_UNAVAILABLE",
            "REASON_CODE": "POSTGRES_AUTHORITY_UNAVAILABLE",
            "CANDIDATE_01_EXECUTION_AUTHORIZED": False,
            "CANDIDATE_01_EXECUTION_REACHED": False,
            "JSONL_LIVE_BUDGET_AUTHORITY": False,
            "RECONCILIATION_ARTIFACT_LIVE_BUDGET_AUTHORITY": False,
            "TEST_EVALUATION_AUTHORIZED": False,
            "TEST_REMAINS_SEALED": True,
        }
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            result = await S4CandidateExecutionAuthority(session).preflight(
                _durable_c01_request(manifest)
            )
            state = result.state
            if state is None:
                return {
                    "EXECUTION_STATUS": "BLOCKED",
                    "CANDIDATE_ID": CANDIDATE_01_ID,
                    "CANDIDATE_01_EXECUTION_PREFLIGHT": "BLOCKED",
                    "BLOCKER": result.blocker,
                    "REASON_CODE": result.reason_code,
                    "CANDIDATE_01_EXECUTION_AUTHORIZED": False,
                    "CANDIDATE_01_EXECUTION_REACHED": False,
                    "JSONL_LIVE_BUDGET_AUTHORITY": False,
                    "RECONCILIATION_ARTIFACT_LIVE_BUDGET_AUTHORITY": False,
                    "TEST_EVALUATION_AUTHORIZED": False,
                    "TEST_REMAINS_SEALED": True,
                }
            return {
                "EXECUTION_STATUS": "BLOCKED",
                "CANDIDATE_ID": CANDIDATE_01_ID,
                "CANDIDATE_01_EXECUTION_PREFLIGHT": "BLOCKED",
                "BLOCKER": result.blocker,
                "REASON_CODE": result.reason_code,
                "CANDIDATE_01_EXECUTION_AUTHORIZED": False,
                "CANDIDATE_01_EXECUTION_REACHED": False,
                "CANDIDATE_01_RUN_COUNT": result.candidate_actual_run_count,
                "CANONICAL_LEDGER_ROW_COUNT": state.accepted_event_count,
                "CANONICAL_LEDGER_STARTED_EVALUATION_COUNT": state.accepted_started_count,
                "LEGACY_RECONCILED_VALIDATION_DEBIT": state.legacy_reconciled_validation_debit,
                "EFFECTIVE_VALIDATION_EVALUATIONS_CONSUMED": state.effective_consumed,
                "REMAINING_EFFECTIVE_VALIDATION_BUDGET": state.remaining,
                "GLOBAL_GATE_COUNT_SOURCE": "POSTGRES_EFFECTIVE_CONSUMED",
                "CANDIDATE_GATE_COUNT_SOURCE": "POSTGRES_CANONICAL_STARTED",
                "PRIOR_EVALUATION_IDS_SOURCE": "POSTGRES_CANONICAL_STARTED",
                "JSONL_LIVE_BUDGET_AUTHORITY": False,
                "RECONCILIATION_ARTIFACT_LIVE_BUDGET_AUTHORITY": False,
                "TEST_EVALUATION_AUTHORIZED": False,
                "TEST_REMAINS_SEALED": True,
            }
    finally:
        await engine.dispose()


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

    try:
        payload = asyncio.run(
            _run_durable_c01_preflight(
                database_url=args.database_url,
                manifest=manifest,
            )
        )
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
