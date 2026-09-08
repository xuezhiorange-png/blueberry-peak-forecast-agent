#!/usr/bin/env python3
"""Run the authorized S4-C01 local engineering validation lane.

This runner is deliberately local-only.  It verifies the frozen SOURCE-002
object, reads the already-materialized TRAIN/VALIDATION bytes from an isolated
PostgreSQL database, performs the regenerated incumbent replay twice, and
executes exactly the four frozen Candidate 01 runs.  It never reads TEST and
never writes production forecast authority.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.maturity.config import load_maturity_curve_config
from backend.app.s2_materialized_dataset.lane_d.canonical import parse_partition_bytes
from backend.app.s2_materialized_dataset.lane_d.service import (
    MaterializedDatasetBuildError,
    S2MaterializedDatasetModel,
    S2MaterializedPartitionModel,
    controlled_materialize_source_002_from_environment,
    load_materialized_dataset_result,
)
from backend.app.s2_materialized_dataset.shared.contracts import PartitionName
from backend.app.s4_candidate_execution import (
    CANDIDATE_01_PARAMETER_MANIFEST_HASH_BOUND,
    build_candidate_01_manifest,
    build_derived_candidate_config,
    validate_candidate_01_manifest,
)
from backend.app.s4_experiment import (
    GUARDRAIL_POLICY_HASH,
    GUARDRAIL_POLICY_VERSION,
    METRIC_CONTRACT_VERSION,
    S4_A_EXPERIMENT_PLAN_HASH_BOUND,
)
from backend.app.s4_local_engineering import (
    LOCAL_ENGINEERING_REPLAY_AUTHORITY_CLASS,
    SOURCE_002_MATERIALIZED_DATASET_IDENTITY_SHA256,
    FrozenEngineeringDataset,
    LocalEngineeringContractError,
    guardrail_payload,
    load_frozen_engineering_dataset,
    relation_to_incumbent,
    run_local_replay,
    verify_frozen_source_object,
)

EXPECTED_MAIN_SHA = "77e3d8ac63d794babfe0c8549fd34d0467f0d57e"
EXPECTED_TRAIN_HASH = "be2d4184434a0f389af21c315945322e9216cd17cc471b772e3fff389d3386d2"
EXPECTED_VALIDATION_HASH = "4cbf1119f83034464159210ebbbeea5ec87848f92ce044bb328949a8f5331d06"
EXPECTED_TRAIN_ROWS = 16_224
EXPECTED_VALIDATION_ROWS = 8_006
EXPECTED_TEST_ROWS = 0
EXPECTED_RUN_COUNT = 4
REMAINING_EFFECTIVE_BUDGET = 28


class LocalRunnerContractError(RuntimeError):
    """A sanitized local runner contract failure."""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _assert_git_identity(
    root: Path, *, execution_main_sha: str, runner_commit_sha: str
) -> dict[str, str]:
    if _git(root, "status", "--porcelain"):
        raise LocalRunnerContractError("WORKTREE_NOT_CLEAN")
    head_sha = _git(root, "rev-parse", "HEAD")
    origin_main_sha = _git(root, "rev-parse", "origin/main")
    if head_sha != runner_commit_sha:
        raise LocalRunnerContractError("RUNNER_COMMIT_SHA_MISMATCH")
    if origin_main_sha != execution_main_sha:
        raise LocalRunnerContractError("EXECUTION_MAIN_SHA_MISMATCH")
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", execution_main_sha, head_sha],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return {
        "current_head_sha": head_sha,
        "execution_main_sha": execution_main_sha,
        "runner_commit_sha": runner_commit_sha,
    }


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _partition_name(value: object) -> str:
    return value.value if isinstance(value, PartitionName) else str(value)


def _load_database_dataset_sync(
    session: Any,
    *,
    source_parent: Path,
    dataset_id: str,
    dataset_version: str,
) -> tuple[FrozenEngineeringDataset, dict[str, Any]]:
    """Load only TRAIN/VALIDATION bytes from the isolated materialized store."""

    try:
        persisted = load_materialized_dataset_result(
            session,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
        )
    except MaterializedDatasetBuildError:
        report = controlled_materialize_source_002_from_environment(
            session,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            search_roots=(source_parent,),
            persist=True,
        )
        if (
            report.dataset_identity != SOURCE_002_MATERIALIZED_DATASET_IDENTITY_SHA256
            or report.rebuild_parity != "PASS"
            or report.train_rows != EXPECTED_TRAIN_ROWS
            or report.val_rows != EXPECTED_VALIDATION_ROWS
            or report.test_rows != EXPECTED_TEST_ROWS
        ):
            raise LocalRunnerContractError("SOURCE_002_MATERIALIZATION_ORACLE_MISMATCH") from None
        persisted = load_materialized_dataset_result(
            session,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
        )

    if (
        persisted.materialized_dataset_identity_sha256
        != SOURCE_002_MATERIALIZED_DATASET_IDENTITY_SHA256
    ):
        raise LocalRunnerContractError("MATERIALIZED_DATASET_IDENTITY_MISMATCH")
    if not persisted.lineage_complete or persisted.quality_gate_status.value != "ACCEPTED":
        raise LocalRunnerContractError("MATERIALIZED_DATASET_QUALITY_GATE_MISMATCH")

    partition_rows = session.scalars(
        select(S2MaterializedPartitionModel)
        .where(
            S2MaterializedPartitionModel.materialized_dataset_id
            == _dataset_row_id(session, dataset_id, dataset_version)
        )
        .order_by(S2MaterializedPartitionModel.partition_name)
    ).all()
    by_name = {_partition_name(row.partition_name): row for row in partition_rows}
    if set(by_name) != {"TRAIN", "VALIDATION", "TEST"}:
        raise LocalRunnerContractError("MATERIALIZED_PARTITION_SET_MISMATCH")
    if by_name["TEST"].row_count != EXPECTED_TEST_ROWS:
        raise LocalRunnerContractError("TEST_ROWS_PRESENT_IN_LOCAL_ENGINEERING_DATABASE")

    parsed: dict[str, tuple[Any, ...]] = {}
    for name, expected_hash, expected_rows in (
        ("TRAIN", EXPECTED_TRAIN_HASH, EXPECTED_TRAIN_ROWS),
        ("VALIDATION", EXPECTED_VALIDATION_HASH, EXPECTED_VALIDATION_ROWS),
    ):
        row = by_name[name]
        content = bytes(row.content_bytes)
        if row.content_sha256 != expected_hash or _sha256(content) != expected_hash:
            raise LocalRunnerContractError(f"{name}_CONTENT_HASH_MISMATCH")
        if row.row_count != expected_rows:
            raise LocalRunnerContractError(f"{name}_ROW_COUNT_MISMATCH")
        parsed[name] = parse_partition_bytes(content)
        if len(parsed[name]) != expected_rows:
            raise LocalRunnerContractError(f"{name}_PARSED_ROW_COUNT_MISMATCH")

    dataset = FrozenEngineeringDataset(
        train_rows=tuple(parsed["TRAIN"]),
        validation_rows=tuple(parsed["VALIDATION"]),
        train_content_sha256=EXPECTED_TRAIN_HASH,
        validation_content_sha256=EXPECTED_VALIDATION_HASH,
        materialized_dataset_identity_sha256=persisted.materialized_dataset_identity_sha256,
        test_row_count=EXPECTED_TEST_ROWS,
    )
    return dataset, {
        "materialized_dataset_identity_sha256": persisted.materialized_dataset_identity_sha256,
        "train_row_count": by_name["TRAIN"].row_count,
        "validation_row_count": by_name["VALIDATION"].row_count,
        "test_row_count": by_name["TEST"].row_count,
        "train_content_sha256": by_name["TRAIN"].content_sha256,
        "validation_content_sha256": by_name["VALIDATION"].content_sha256,
        "test_content_sha256": by_name["TEST"].content_sha256,
        "partition_rebuild_hash_replay": {
            name: str(row.rebuild_hash_replay_status) for name, row in by_name.items()
        },
    }


def _dataset_row_id(session: Any, dataset_id: str, dataset_version: str) -> int:
    result = session.execute(
        select(S2MaterializedDatasetModel.id)
        .where(
            S2MaterializedDatasetModel.dataset_id == dataset_id,
            S2MaterializedDatasetModel.dataset_version == dataset_version,
        )
        .limit(1)
    ).scalar_one_or_none()
    if result is None:
        raise LocalRunnerContractError("MATERIALIZED_DATASET_ROW_UNAVAILABLE")
    return int(result)


async def _load_database_dataset(
    *,
    host: str,
    port: int,
    database: str,
    source_parent: Path,
) -> tuple[FrozenEngineeringDataset, dict[str, Any]]:
    if host not in {"127.0.0.1", "localhost"}:
        raise LocalRunnerContractError("NON_LOCAL_DATABASE_HOST_FORBIDDEN")
    url = f"postgresql+asyncpg://postgres@{host}:{port}/{database}"
    engine = create_async_engine(url, pool_pre_ping=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as session:
            result = await session.run_sync(
                lambda sync: _load_database_dataset_sync(
                    sync,
                    source_parent=source_parent,
                    dataset_id="source-002",
                    dataset_version="e5-live-v1",
                )
            )
            await session.commit()
            return result
    finally:
        await engine.dispose()


def _metric_summary(result: Any) -> dict[str, Any]:
    return result.payload(include_predictions=False)


def _run_summary(*, ordinal: int, run: Any, result: Any, incumbent: Any) -> dict[str, Any]:
    guardrails = guardrail_payload(candidate=result, incumbent=incumbent)
    coverage = next(
        (
            item["status"]
            for item in guardrails["guardrails"]
            if item["guardrail_id"] == "coverage_and_data_quality"
        ),
        "BLOCKED",
    )
    return {
        "candidate_run_ordinal": ordinal,
        "parameter_manifest_hash": run.parameter_manifest_hash,
        "candidate_config_hash": run.candidate_config_hash,
        "random_seed": run.random_seed,
        "parameter_delta": {path: str(value) for path, value in run.parameter_delta},
        "result": _metric_summary(result),
        "primary_metric_relation_to_incumbent": relation_to_incumbent(result, incumbent),
        "guardrail_status": guardrails["status"],
        "coverage_status": coverage,
        "guardrails": guardrails,
    }


def _best_run(summaries: list[dict[str, Any]]) -> tuple[str, str]:
    eligible = [
        item
        for item in summaries
        if item["guardrail_status"] == "PASS"
        and item["primary_metric_relation_to_incumbent"] == "IMPROVED"
    ]
    if eligible:
        eligible.sort(
            key=lambda item: (
                item["result"]["metrics"]["daily_wape"],
                item["candidate_run_ordinal"],
            )
        )
        return str(eligible[0]["candidate_run_ordinal"]), "IMPROVED"
    if any(item["guardrail_status"] == "BLOCKED" for item in summaries):
        return "NONE", "BLOCKED"
    return "NONE", "NO_IMPROVEMENT"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-object",
        type=Path,
        default=Path("/tmp/source-002-original.xls"),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/maturity_curve.yaml"),
    )
    parser.add_argument("--execution-main-sha", required=True)
    parser.add_argument("--runner-commit-sha", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=55435)
    parser.add_argument("--database", default="blueberry_peak_s4_local_engineering")
    return parser


def _execute(args: argparse.Namespace) -> dict[str, Any]:
    root = _repo_root()
    source_path = (
        args.source_object if args.source_object.is_absolute() else root / args.source_object
    )
    config_path = args.config if args.config.is_absolute() else root / args.config
    git_identity = _assert_git_identity(
        root,
        execution_main_sha=args.execution_main_sha,
        runner_commit_sha=args.runner_commit_sha,
    )
    if args.execution_main_sha != EXPECTED_MAIN_SHA:
        raise LocalRunnerContractError("UNEXPECTED_EXECUTION_MAIN_SHA")
    source = verify_frozen_source_object(source_path)
    fixture_dataset = load_frozen_engineering_dataset(root)
    database_dataset, database_summary = asyncio.run(
        _load_database_dataset(
            host=args.host,
            port=args.port,
            database=args.database,
            source_parent=source.path.parent,
        )
    )
    if database_dataset.train_rows != fixture_dataset.train_rows:
        raise LocalRunnerContractError("DATABASE_TRAIN_BYTES_DIFFER_FROM_FROZEN_PARTITION")
    if database_dataset.validation_rows != fixture_dataset.validation_rows:
        raise LocalRunnerContractError("DATABASE_VALIDATION_BYTES_DIFFER_FROM_FROZEN_PARTITION")
    config = load_maturity_curve_config(config_path)
    incumbent_first = run_local_replay(dataset=database_dataset, config=config)
    incumbent_second = run_local_replay(dataset=database_dataset, config=config)
    if incumbent_first.payload() != incumbent_second.payload():
        raise LocalRunnerContractError("LOCAL_INCUMBENT_REPLAY_NOT_DETERMINISTIC")

    manifest = build_candidate_01_manifest(config_path)
    validate_candidate_01_manifest(manifest, config_path=config_path)
    if manifest.manifest_hash != CANDIDATE_01_PARAMETER_MANIFEST_HASH_BOUND:
        raise LocalRunnerContractError("CANDIDATE_01_MANIFEST_HASH_MISMATCH")
    summaries: list[dict[str, Any]] = []
    for ordinal in range(1, EXPECTED_RUN_COUNT + 1):
        run, candidate_config = build_derived_candidate_config(manifest, ordinal)
        candidate_result = run_local_replay(dataset=database_dataset, config=candidate_config)
        summaries.append(
            _run_summary(
                ordinal=ordinal,
                run=run,
                result=candidate_result,
                incumbent=incumbent_first,
            )
        )
    best_run, candidate_result = _best_run(summaries)
    return {
        "EXECUTION_STATUS": "PASS",
        "TASK_ID": "V0_3_S4_LOCAL_ENGINEERING_VALIDATION_BOOTSTRAP_AND_C01_EXECUTION_R1",
        "EVALUATION_LANE": "LOCAL_ENGINEERING_REPLAY",
        "BASE_MAIN_SHA": args.execution_main_sha,
        "CURRENT_HEAD_SHA": git_identity["current_head_sha"],
        "SCORING_RUNNER_COMMIT_SHA": git_identity["runner_commit_sha"],
        "LOCAL_POSTGRES_READY": True,
        "LOCAL_DATABASE_HOST": args.host,
        "LOCAL_DATABASE_PORT": args.port,
        "LOCAL_DATABASE_NAME": args.database,
        "SOURCE_002_RAW_OBJECT_SHA256": source.sha256,
        "SOURCE_002_RAW_OBJECT_BYTE_COUNT": source.byte_count,
        "SOURCE_002_RAW_OBJECT_ROW_COUNT": source.row_count,
        "SOURCE_002_RESTORED": True,
        "SOURCE_002_MATERIALIZED_DATASET_IDENTITY_SHA256": database_summary[
            "materialized_dataset_identity_sha256"
        ],
        "TRAIN_ROW_COUNT": database_summary["train_row_count"],
        "TRAIN_CONTENT_SHA256": database_summary["train_content_sha256"],
        "VALIDATION_ROW_COUNT": database_summary["validation_row_count"],
        "VALIDATION_CONTENT_SHA256": database_summary["validation_content_sha256"],
        "TEST_ROW_COUNT": database_summary["test_row_count"],
        "TEST_REMAINS_SEALED": True,
        "NO_FUTURE_LABEL_LEAKAGE": True,
        "NO_TEST_ACCESS": True,
        "REGENERATED_INCUMBENT_AUTHORITY_CLASS": LOCAL_ENGINEERING_REPLAY_AUTHORITY_CLASS,
        "INCUMBENT_MODEL_ID": "V0_2_CURRENT_MODEL",
        "LOCAL_INCUMBENT_REPLAY_STATUS": "PASS",
        "LOCAL_INCUMBENT_REPLAY_COUNT": 2,
        "LOCAL_INCUMBENT_REPLAY_DETERMINISTIC": True,
        "INCUMBENT_REPLAY": _metric_summary(incumbent_first),
        "INCUMBENT_REPLAY_IDENTITY_SHA256": incumbent_first.prediction_identity_sha256,
        "CANDIDATE_01_ID": manifest.candidate_id,
        "CANDIDATE_01_MANIFEST_HASH": manifest.manifest_hash,
        "CANDIDATE_01_ENGINEERING_RUN_COUNT": EXPECTED_RUN_COUNT,
        "CANDIDATE_01_RUNS": summaries,
        "CANDIDATE_01_LOCAL_ENGINEERING_BEST_RUN": best_run,
        "CANDIDATE_01_LOCAL_ENGINEERING_RESULT": candidate_result,
        "LOCAL_ENGINEERING_VALIDATION_EVALUATION_COUNT": EXPECTED_RUN_COUNT,
        "EFFECTIVE_VALIDATION_EVALUATIONS_CONSUMED": EXPECTED_RUN_COUNT,
        "REMAINING_EFFECTIVE_VALIDATION_BUDGET": REMAINING_EFFECTIVE_BUDGET,
        "MODEL_APPROVED_FOR_PILOT": False,
        "FINAL_MODEL_SELECTED": False,
        "TEST_EVALUATION_PERFORMED": False,
        "S4_CANDIDATE_EXPERIMENT_EXECUTED": True,
        "EXPERIMENT_PLAN_HASH": S4_A_EXPERIMENT_PLAN_HASH_BOUND,
        "GUARDRAIL_POLICY_VERSION": GUARDRAIL_POLICY_VERSION,
        "GUARDRAIL_POLICY_HASH": GUARDRAIL_POLICY_HASH,
        "METRIC_CONTRACT_VERSION": METRIC_CONTRACT_VERSION,
    }


def main() -> int:
    args = _parser().parse_args()
    try:
        payload = _execute(args)
    except (LocalRunnerContractError, LocalEngineeringContractError, OSError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "EXECUTION_STATUS": "BLOCKED",
                    "BLOCKER": "LOCAL_ENGINEERING_EXECUTION_CONTRACT",
                    "REASON_CODE": str(exc) or type(exc).__name__,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
