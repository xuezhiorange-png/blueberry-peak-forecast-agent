#!/usr/bin/env python3
"""Run V0.3 Farm-total baseline evaluation package against official SOURCE-002."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.forecast_quality.farm_total_area_authority import (  # noqa: E402
    FarmTotalAreaAuthorityLoadError,
)
from backend.app.forecast_quality.farm_total_baseline_evaluation_package import (  # noqa: E402
    FARM_TOTAL_BASELINE_EVALUATION_PACKAGE_SCHEMA_VERSION,
    FarmTotalBaselineEvaluationPackage,
    build_farm_total_baseline_evaluation_package,
)
from backend.app.forecast_quality.farm_total_data_plane import (  # noqa: E402
    FarmTotalAuthorityBundle,
    FarmTotalDataPlaneResult,
    FarmTotalDatasetBlocker,
    load_authority_bundle_from_paths,
    materialize_farm_total_baseline_data_plane,
)
from backend.app.s3_daily_rowset import (  # noqa: E402
    accepted_s2_train_val_source_002_row_level_read_live_obtain as source_002_live_obtain,
)
from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read import (  # noqa: E402
    OFFICIAL_TRAIN_CONTENT_SHA256,
    OFFICIAL_VALIDATION_CONTENT_SHA256,
)

MAPPING_PACKAGE_NAME = "farm_total_group_mapping_package.json"
AREA_PACKAGE_NAME = "farm_total_area_authority_package.json"

LiveObtainEnvelope = source_002_live_obtain.AcceptedS2TrainValLiveObtainEnvelope
LiveObtainReasonCode = source_002_live_obtain.LiveObtainReasonCode


class LiveExecutionBlocker(StrEnum):
    REPOSITORY_IDENTITY_MISMATCH = "REPOSITORY_IDENTITY_MISMATCH"
    LIVE_AUTHORITY_PACKAGE_FILES_UNAVAILABLE = "LIVE_AUTHORITY_PACKAGE_FILES_UNAVAILABLE"
    LIVE_AUTHORITY_PACKAGE_INVALID = "LIVE_AUTHORITY_PACKAGE_INVALID"
    SOURCE_002_OBTAIN_FAILED = "SOURCE_002_OBTAIN_FAILED"
    SOURCE_002_BYTES_MISSING = "SOURCE_002_BYTES_MISSING"
    TEST_CUSTODY_NOT_SEALED = "TEST_CUSTODY_NOT_SEALED"
    FARM_TOTAL_DATA_PLANE_BLOCKED = "FARM_TOTAL_DATA_PLANE_BLOCKED"
    FARM_TOTAL_DATA_PLANE_INVARIANT_VIOLATION = "FARM_TOTAL_DATA_PLANE_INVARIANT_VIOLATION"
    EVALUATION_PACKAGE_BUILD_FAILED = "EVALUATION_PACKAGE_BUILD_FAILED"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_rev_parse(ref: str) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", ref],
        cwd=REPO_ROOT,
        text=True,
    ).strip()


def _git_status_porcelain() -> str:
    return subprocess.check_output(
        ["git", "status", "--porcelain"],
        cwd=REPO_ROOT,
        text=True,
    )


def verify_repository_identity(
    *,
    execution_main_sha: str,
    runner_commit_sha: str,
) -> LiveExecutionBlocker | None:
    if _git_rev_parse("HEAD") != runner_commit_sha:
        return LiveExecutionBlocker.REPOSITORY_IDENTITY_MISMATCH
    if _git_rev_parse("origin/main") != execution_main_sha:
        return LiveExecutionBlocker.REPOSITORY_IDENTITY_MISMATCH
    if _git_status_porcelain().strip():
        return LiveExecutionBlocker.REPOSITORY_IDENTITY_MISMATCH
    return None


def verify_authority_package_files(authority_dir: Path) -> LiveExecutionBlocker | None:
    mapping_path = authority_dir / MAPPING_PACKAGE_NAME
    area_path = authority_dir / AREA_PACKAGE_NAME
    if not mapping_path.is_file() or not area_path.is_file():
        return LiveExecutionBlocker.LIVE_AUTHORITY_PACKAGE_FILES_UNAVAILABLE
    return None


def load_authority_bundle_from_directory(authority_dir: Path) -> FarmTotalAuthorityBundle:
    return load_authority_bundle_from_paths(
        mapping_package_path=authority_dir / MAPPING_PACKAGE_NAME,
        area_authority_package_path=authority_dir / AREA_PACKAGE_NAME,
    )


def validate_source_002_obtain(
    obtain: LiveObtainEnvelope,
) -> LiveExecutionBlocker | None:
    if not obtain.obtained or obtain.reason_code != LiveObtainReasonCode.OBTAINED:
        return LiveExecutionBlocker.SOURCE_002_OBTAIN_FAILED
    if obtain.train_content_bytes is None or not obtain.train_content_bytes:
        return LiveExecutionBlocker.SOURCE_002_BYTES_MISSING
    if obtain.validation_content_bytes is None or not obtain.validation_content_bytes:
        return LiveExecutionBlocker.SOURCE_002_BYTES_MISSING
    if not obtain.test_remains_sealed:
        return LiveExecutionBlocker.TEST_CUSTODY_NOT_SEALED
    if obtain.dataset_id is None or obtain.dataset_version is None:
        return LiveExecutionBlocker.SOURCE_002_OBTAIN_FAILED
    if obtain.materialized_dataset_identity_sha256 is None:
        return LiveExecutionBlocker.SOURCE_002_OBTAIN_FAILED
    if obtain.train_row_count is None or obtain.validation_row_count is None:
        return LiveExecutionBlocker.SOURCE_002_OBTAIN_FAILED
    return None


def validate_data_plane_result(
    blocker: FarmTotalDatasetBlocker,
    result: FarmTotalDataPlaneResult | None,
) -> LiveExecutionBlocker | None:
    if blocker != FarmTotalDatasetBlocker.NONE or result is None:
        return LiveExecutionBlocker.FARM_TOTAL_DATA_PLANE_BLOCKED
    if result.validation_used_as_training_input:
        return LiveExecutionBlocker.FARM_TOTAL_DATA_PLANE_INVARIANT_VIOLATION
    if result.area_double_count_count != 0:
        return LiveExecutionBlocker.FARM_TOTAL_DATA_PLANE_INVARIANT_VIOLATION
    if result.source_farm_double_map_count != 0:
        return LiveExecutionBlocker.FARM_TOTAL_DATA_PLANE_INVARIANT_VIOLATION
    if result.source_actual_double_count != 0:
        return LiveExecutionBlocker.FARM_TOTAL_DATA_PLANE_INVARIANT_VIOLATION
    return None


def build_success_payload(
    *,
    execution_main_sha: str,
    runner_commit_sha: str,
    obtain: LiveObtainEnvelope,
    data_plane_result: FarmTotalDataPlaneResult,
    package: FarmTotalBaselineEvaluationPackage,
    authority_dir: Path,
) -> dict[str, Any]:
    mapping_path = authority_dir / MAPPING_PACKAGE_NAME
    area_path = authority_dir / AREA_PACKAGE_NAME
    train_dataset = data_plane_result.train_dataset
    validation_dataset = data_plane_result.validation_dataset
    diagnostics = package.diagnostics
    return {
        "EXECUTION_STATUS": "PASS",
        "EXECUTION_MAIN_SHA": execution_main_sha,
        "RUNNER_COMMIT_SHA": runner_commit_sha,
        "SOURCE_002_DATASET_ID": obtain.dataset_id,
        "SOURCE_002_DATASET_VERSION": obtain.dataset_version,
        "SOURCE_002_MATERIALIZED_DATASET_IDENTITY_SHA256": (
            obtain.materialized_dataset_identity_sha256
        ),
        "OFFICIAL_TRAIN_CONTENT_SHA256": OFFICIAL_TRAIN_CONTENT_SHA256,
        "OFFICIAL_VALIDATION_CONTENT_SHA256": OFFICIAL_VALIDATION_CONTENT_SHA256,
        "TRAIN_SOURCE_ROW_COUNT": obtain.train_row_count,
        "VALIDATION_SOURCE_ROW_COUNT": obtain.validation_row_count,
        "TEST_REMAINS_SEALED": obtain.test_remains_sealed,
        "FARM_GROUP_MAPPING_SET_SHA256": data_plane_result.mapping_set_sha256,
        "FARM_AREA_AUTHORITY_SET_SHA256": data_plane_result.area_authority_set_sha256,
        "AUTHORITY_MAPPING_PACKAGE_FILE_SHA256": sha256_file(mapping_path),
        "AUTHORITY_AREA_PACKAGE_FILE_SHA256": sha256_file(area_path),
        "TRAIN_FARM_TOTAL_ROW_COUNT": len(train_dataset.partition_dataset.rows),
        "VALIDATION_FARM_TOTAL_ROW_COUNT": len(validation_dataset.partition_dataset.rows),
        "TRAIN_FARM_GROUP_COUNT": train_dataset.diagnostics.farm_group_count,
        "VALIDATION_FARM_GROUP_COUNT": validation_dataset.diagnostics.farm_group_count,
        "TRAIN_FARM_TOTAL_DATASET_SHA256": train_dataset.partition_dataset.dataset_sha256,
        "VALIDATION_FARM_TOTAL_DATASET_SHA256": (
            validation_dataset.partition_dataset.dataset_sha256
        ),
        "AREA_DOUBLE_COUNT_COUNT": data_plane_result.area_double_count_count,
        "SOURCE_FARM_DOUBLE_MAP_COUNT": data_plane_result.source_farm_double_map_count,
        "SOURCE_ACTUAL_DOUBLE_COUNT": data_plane_result.source_actual_double_count,
        "VALIDATION_USED_AS_TRAINING_INPUT": data_plane_result.validation_used_as_training_input,
        "PACKAGE_SCHEMA_VERSION": FARM_TOTAL_BASELINE_EVALUATION_PACKAGE_SCHEMA_VERSION,
        "TARGET_COUNT": diagnostics.target_count,
        "EMITTED_POINT_COUNT": diagnostics.emitted_point_count,
        "BLOCKED_TARGET_COUNT": diagnostics.blocked_target_count,
        "READY_TARGET_COUNT": diagnostics.ready_target_count,
        "INSUFFICIENT_TRAIN_SUPPORT_TARGET_COUNT": (
            diagnostics.insufficient_train_support_target_count
        ),
        "UNSEEN_GROUP_TARGET_COUNT": diagnostics.unseen_group_target_count,
        "ESTIMATOR_STATE_SHA256": package.estimator_state_sha256,
        "TARGET_IDENTITY_SET_SHA256": package.target_identity_set_sha256,
        "BASELINE_POINT_SET_SHA256": package.baseline_point_set_sha256,
        "TARGET_OUTCOME_SET_SHA256": package.target_outcome_set_sha256,
        "PREDICTION_IDENTITY_SHA256": package.prediction_identity_sha256,
        "PACKAGE_SHA256": package.package_sha256,
    }


def build_blocked_payload(
    *,
    blocker: LiveExecutionBlocker,
    reason_code: str,
) -> dict[str, str]:
    return {
        "EXECUTION_STATUS": "BLOCKED",
        "BLOCKER": blocker.value,
        "REASON_CODE": reason_code,
    }


def run_farm_total_baseline_live_execution(
    *,
    authority_dir: Path,
    execution_main_sha: str,
    runner_commit_sha: str,
    obtain_fn: Callable[[], LiveObtainEnvelope] | None = None,
    authority_loader_fn: Callable[[Path], FarmTotalAuthorityBundle] | None = None,
    data_plane_fn: Callable[..., tuple[FarmTotalDatasetBlocker, FarmTotalDataPlaneResult | None]]
    | None = None,
    package_builder_fn: Callable[..., FarmTotalBaselineEvaluationPackage] | None = None,
    verify_repository: bool = True,
) -> dict[str, Any]:
    obtain = (
        obtain_fn
        or source_002_live_obtain.obtain_accepted_s2_train_val_content_bytes_from_bound_live_session
    )
    authority_loader = authority_loader_fn or load_authority_bundle_from_directory
    data_plane = data_plane_fn or materialize_farm_total_baseline_data_plane
    package_builder = package_builder_fn or build_farm_total_baseline_evaluation_package

    if verify_repository:
        repo_blocker = verify_repository_identity(
            execution_main_sha=execution_main_sha,
            runner_commit_sha=runner_commit_sha,
        )
        if repo_blocker is not None:
            return build_blocked_payload(
                blocker=repo_blocker,
                reason_code=repo_blocker.value,
            )

    files_blocker = verify_authority_package_files(authority_dir)
    if files_blocker is not None:
        return build_blocked_payload(
            blocker=files_blocker,
            reason_code=files_blocker.value,
        )

    try:
        authority_bundle = authority_loader(authority_dir)
    except (FarmTotalAreaAuthorityLoadError, OSError, ValueError, json.JSONDecodeError):
        return build_blocked_payload(
            blocker=LiveExecutionBlocker.LIVE_AUTHORITY_PACKAGE_INVALID,
            reason_code=LiveExecutionBlocker.LIVE_AUTHORITY_PACKAGE_INVALID.value,
        )

    obtain_envelope = obtain()
    obtain_blocker = validate_source_002_obtain(obtain_envelope)
    if obtain_blocker is not None:
        reason = (
            obtain_envelope.reason_code.value
            if obtain_envelope.reason_code is not None
            else obtain_blocker.value
        )
        return build_blocked_payload(blocker=obtain_blocker, reason_code=reason)

    train_bytes = obtain_envelope.train_content_bytes
    validation_bytes = obtain_envelope.validation_content_bytes
    assert train_bytes is not None
    assert validation_bytes is not None

    blocker, data_plane_result = data_plane(
        train_content_bytes=train_bytes,
        validation_content_bytes=validation_bytes,
        authority_bundle=authority_bundle,
        verify_official_hashes=True,
    )
    data_plane_blocker = validate_data_plane_result(blocker, data_plane_result)
    if data_plane_blocker is not None:
        if blocker != FarmTotalDatasetBlocker.NONE:
            reason = blocker.value
        else:
            reason = data_plane_blocker.value
        return build_blocked_payload(blocker=data_plane_blocker, reason_code=reason)

    assert data_plane_result is not None
    try:
        package = package_builder(
            train_dataset=data_plane_result.train_dataset,
            validation_dataset=data_plane_result.validation_dataset,
        )
    except Exception:
        return build_blocked_payload(
            blocker=LiveExecutionBlocker.EVALUATION_PACKAGE_BUILD_FAILED,
            reason_code=LiveExecutionBlocker.EVALUATION_PACKAGE_BUILD_FAILED.value,
        )

    return build_success_payload(
        execution_main_sha=execution_main_sha,
        runner_commit_sha=runner_commit_sha,
        obtain=obtain_envelope,
        data_plane_result=data_plane_result,
        package=package,
        authority_dir=authority_dir,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run V0.3 Farm-total baseline evaluation package live execution.",
    )
    parser.add_argument(
        "--authority-dir",
        required=True,
        type=Path,
        help="Directory containing reviewed farm-total authority package JSON files.",
    )
    parser.add_argument(
        "--execution-main-sha",
        required=True,
        help="Expected origin/main SHA for this controlled execution.",
    )
    parser.add_argument(
        "--runner-commit-sha",
        required=True,
        help="Expected local commit SHA containing the finalized runner.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = run_farm_total_baseline_live_execution(
        authority_dir=args.authority_dir,
        execution_main_sha=args.execution_main_sha,
        runner_commit_sha=args.runner_commit_sha,
    )
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0 if payload.get("EXECUTION_STATUS") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
