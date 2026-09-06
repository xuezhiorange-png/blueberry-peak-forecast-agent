#!/usr/bin/env python3
"""Run the authorized Farm-total baseline VALIDATION scorer against SOURCE-002."""

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
from backend.app.forecast_quality.farm_total_baseline_validation_scoring import (  # noqa: E402
    FarmTotalBaselineValidationMetricCell,
    FarmTotalBaselineValidationScorePackage,
    FarmTotalBaselineValidationScoringError,
    score_farm_total_baseline_validation,
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
    OFFICIAL_DATASET_ID,
    OFFICIAL_DATASET_VERSION,
    OFFICIAL_MATERIALIZED_DATASET_IDENTITY_SHA256,
    OFFICIAL_TRAIN_CONTENT_SHA256,
    OFFICIAL_VALIDATION_CONTENT_SHA256,
)

MAPPING_PACKAGE_NAME = "farm_total_group_mapping_package.json"
AREA_PACKAGE_NAME = "farm_total_area_authority_package.json"
R4_AUTHORITY_LINEAGE = "R4_REISSUED_DURABLE"
R4_AUTHORITY_RECOVERY_MODE = "R4_REISSUANCE"
R4_CANONICAL_AUTHORITY_DIR = REPO_ROOT / "docs" / "v0-3" / "s3" / "authority"

LiveObtainEnvelope = source_002_live_obtain.AcceptedS2TrainValLiveObtainEnvelope
LiveObtainReasonCode = source_002_live_obtain.LiveObtainReasonCode


class LiveExecutionBlocker(StrEnum):
    REPOSITORY_IDENTITY_MISMATCH = "REPOSITORY_IDENTITY_MISMATCH"
    LIVE_AUTHORITY_PACKAGE_FILES_UNAVAILABLE = "LIVE_AUTHORITY_PACKAGE_FILES_UNAVAILABLE"
    LIVE_AUTHORITY_PACKAGE_INVALID = "LIVE_AUTHORITY_PACKAGE_INVALID"
    R4_AUTHORITY_PATH_MISMATCH = "R4_AUTHORITY_PATH_MISMATCH"
    R4_AUTHORITY_LINEAGE_MISMATCH = "R4_AUTHORITY_LINEAGE_MISMATCH"
    R4_AUTHORITY_NOT_DURABLY_COMMITTED = "R4_AUTHORITY_NOT_DURABLY_COMMITTED"
    SOURCE_002_OBTAIN_FAILED = "SOURCE_002_OBTAIN_FAILED"
    SOURCE_002_BYTES_MISSING = "SOURCE_002_BYTES_MISSING"
    SOURCE_002_IDENTITY_MISMATCH = "SOURCE_002_IDENTITY_MISMATCH"
    TEST_CUSTODY_NOT_SEALED = "TEST_CUSTODY_NOT_SEALED"
    FARM_TOTAL_DATA_PLANE_BLOCKED = "FARM_TOTAL_DATA_PLANE_BLOCKED"
    FARM_TOTAL_DATA_PLANE_INVARIANT_VIOLATION = "FARM_TOTAL_DATA_PLANE_INVARIANT_VIOLATION"
    FARM_TOTAL_DATA_PLANE_IDENTITY_MISMATCH = "FARM_TOTAL_DATA_PLANE_IDENTITY_MISMATCH"
    EVALUATION_PACKAGE_BUILD_FAILED = "EVALUATION_PACKAGE_BUILD_FAILED"
    EVALUATION_PACKAGE_IDENTITY_MISMATCH = "EVALUATION_PACKAGE_IDENTITY_MISMATCH"
    SCORING_DIAGNOSTIC_MISMATCH = "SCORING_DIAGNOSTIC_MISMATCH"
    SCORING_INTERNAL_ERROR = "SCORING_INTERNAL_ERROR"


def _file_sha256(path: Path) -> str:
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
    try:
        if _git_rev_parse("HEAD") != runner_commit_sha:
            return LiveExecutionBlocker.REPOSITORY_IDENTITY_MISMATCH
        if _git_rev_parse("origin/main") != execution_main_sha:
            return LiveExecutionBlocker.REPOSITORY_IDENTITY_MISMATCH
        if _git_status_porcelain().strip():
            return LiveExecutionBlocker.REPOSITORY_IDENTITY_MISMATCH
    except (OSError, subprocess.CalledProcessError):
        return LiveExecutionBlocker.REPOSITORY_IDENTITY_MISMATCH
    return None


def verify_authority_package_files(authority_dir: Path) -> LiveExecutionBlocker | None:
    if not (authority_dir / MAPPING_PACKAGE_NAME).is_file():
        return LiveExecutionBlocker.LIVE_AUTHORITY_PACKAGE_FILES_UNAVAILABLE
    if not (authority_dir / AREA_PACKAGE_NAME).is_file():
        return LiveExecutionBlocker.LIVE_AUTHORITY_PACKAGE_FILES_UNAVAILABLE
    return None


def _load_authority_provenance(authority_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    mapping_payload = json.loads(
        (authority_dir / MAPPING_PACKAGE_NAME).read_text(encoding="utf-8")
    )
    area_payload = json.loads(
        (authority_dir / AREA_PACKAGE_NAME).read_text(encoding="utf-8")
    )
    mapping_provenance = mapping_payload.get("r4_provenance")
    area_provenance = area_payload.get("r4_provenance")
    if not isinstance(mapping_provenance, dict) or not isinstance(area_provenance, dict):
        raise ValueError("R4 authority provenance is missing")
    return mapping_provenance, area_provenance


def _git_path_is_tracked(path: Path) -> bool:
    try:
        subprocess.check_call(
            ["git", "ls-files", "--error-unmatch", "--", str(path.relative_to(REPO_ROOT))],
            cwd=REPO_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, ValueError, subprocess.CalledProcessError):
        return False
    return True


def validate_r4_authority_binding(
    *,
    authority_dir: Path,
) -> tuple[LiveExecutionBlocker | None, dict[str, Any] | None]:
    """Require the official run to use the committed R4 authority lineage."""

    try:
        resolved_dir = authority_dir.resolve()
        if resolved_dir != R4_CANONICAL_AUTHORITY_DIR.resolve():
            return LiveExecutionBlocker.R4_AUTHORITY_PATH_MISMATCH, None
        mapping_path = resolved_dir / MAPPING_PACKAGE_NAME
        area_path = resolved_dir / AREA_PACKAGE_NAME
        if not _git_path_is_tracked(mapping_path) or not _git_path_is_tracked(area_path):
            return LiveExecutionBlocker.R4_AUTHORITY_NOT_DURABLY_COMMITTED, None
        mapping_provenance, area_provenance = _load_authority_provenance(resolved_dir)
    except (OSError, ValueError, json.JSONDecodeError):
        return LiveExecutionBlocker.R4_AUTHORITY_LINEAGE_MISMATCH, None

    expected_fields = {
        "authority_lineage": R4_AUTHORITY_LINEAGE,
        "recovery_mode": R4_AUTHORITY_RECOVERY_MODE,
        "authority_byte_identical_recovery_required": False,
        "historical_authority_may_not_be_impersonated": True,
        "historical_mapping_semantic_parity": "NOT_REPRODUCED",
    }
    for provenance in (mapping_provenance, area_provenance):
        if any(provenance.get(field) != value for field, value in expected_fields.items()):
            return LiveExecutionBlocker.R4_AUTHORITY_LINEAGE_MISMATCH, None
    if mapping_provenance.get("r4_mapping_semantics_recovered_from_hash_oracle") is not False:
        return LiveExecutionBlocker.R4_AUTHORITY_LINEAGE_MISMATCH, None

    metadata: dict[str, Any] = {
        "AUTHORITY_LINEAGE": R4_AUTHORITY_LINEAGE,
        "AUTHORITY_RECOVERY_MODE": R4_AUTHORITY_RECOVERY_MODE,
        "AUTHORITY_PACKAGE_RECOVERY_PERFORMED": True,
        "AUTHORITY_PACKAGE_RECOVERY_STATUS": "PASS",
        "AUTHORITY_PACKAGE_RECOVERY_IDENTITY": "NEW_R4_NOT_BYTE_IDENTICAL",
        "AUTHORITY_PACKAGE_SEMANTIC_CHANGE": False,
        "R4_NEW_AUTHORITY_IDENTITY": True,
        "LOST_R1_AUTHORITY_FILES_RECOVERED": False,
        "AUTHORITY_MAPPING_PACKAGE_FILE_SHA256": _file_sha256(mapping_path),
        "AUTHORITY_AREA_PACKAGE_FILE_SHA256": _file_sha256(area_path),
        "HISTORICAL_MAPPING_SEMANTIC_PARITY": "NOT_REPRODUCED",
        "HISTORICAL_AUTHORITY_MAY_NOT_BE_IMPERSONATED": True,
        "R4_AUTHORITY_DURABLY_COMMITTED": True,
    }
    return None, metadata


def load_authority_bundle_from_directory(authority_dir: Path) -> FarmTotalAuthorityBundle:
    return load_authority_bundle_from_paths(
        mapping_package_path=authority_dir / MAPPING_PACKAGE_NAME,
        area_authority_package_path=authority_dir / AREA_PACKAGE_NAME,
    )


def validate_source_002_obtain(
    obtain: LiveObtainEnvelope,
) -> LiveExecutionBlocker | None:
    if not obtain.obtained or obtain.reason_code is not LiveObtainReasonCode.OBTAINED:
        return LiveExecutionBlocker.SOURCE_002_OBTAIN_FAILED
    if obtain.train_content_bytes is None or not obtain.train_content_bytes:
        return LiveExecutionBlocker.SOURCE_002_BYTES_MISSING
    if obtain.validation_content_bytes is None or not obtain.validation_content_bytes:
        return LiveExecutionBlocker.SOURCE_002_BYTES_MISSING
    if not obtain.test_remains_sealed:
        return LiveExecutionBlocker.TEST_CUSTODY_NOT_SEALED
    if (
        obtain.dataset_id != OFFICIAL_DATASET_ID
        or obtain.dataset_version != OFFICIAL_DATASET_VERSION
        or obtain.materialized_dataset_identity_sha256
        != OFFICIAL_MATERIALIZED_DATASET_IDENTITY_SHA256
    ):
        return LiveExecutionBlocker.SOURCE_002_IDENTITY_MISMATCH
    if (
        hashlib.sha256(obtain.train_content_bytes).hexdigest() != OFFICIAL_TRAIN_CONTENT_SHA256
        or hashlib.sha256(obtain.validation_content_bytes).hexdigest()
        != OFFICIAL_VALIDATION_CONTENT_SHA256
    ):
        return LiveExecutionBlocker.SOURCE_002_IDENTITY_MISMATCH
    return None


def validate_data_plane_result(
    blocker: FarmTotalDatasetBlocker,
    result: FarmTotalDataPlaneResult | None,
    authority_bundle: FarmTotalAuthorityBundle | None = None,
) -> LiveExecutionBlocker | None:
    if blocker != FarmTotalDatasetBlocker.NONE or result is None:
        return LiveExecutionBlocker.FARM_TOTAL_DATA_PLANE_BLOCKED
    if (
        result.validation_used_as_training_input
        or result.area_double_count_count != 0
        or result.source_farm_double_map_count != 0
        or result.source_actual_double_count != 0
    ):
        return LiveExecutionBlocker.FARM_TOTAL_DATA_PLANE_INVARIANT_VIOLATION
    if authority_bundle is not None and (
        result.mapping_set_sha256 != authority_bundle.mapping_package.mapping_set_sha256
        or result.area_authority_set_sha256
        != authority_bundle.area_package.area_authority_set_sha256
    ):
        return LiveExecutionBlocker.FARM_TOTAL_DATA_PLANE_IDENTITY_MISMATCH
    return None


def validate_evaluation_package(
    package: FarmTotalBaselineEvaluationPackage,
    data_plane_result: FarmTotalDataPlaneResult,
) -> LiveExecutionBlocker | None:
    diagnostics = package.diagnostics
    if (
        package.schema_version != FARM_TOTAL_BASELINE_EVALUATION_PACKAGE_SCHEMA_VERSION
        or package.train_dataset_sha256
        != data_plane_result.train_dataset.partition_dataset.dataset_sha256
        or package.validation_dataset_sha256
        != data_plane_result.validation_dataset.partition_dataset.dataset_sha256
        or diagnostics.target_count
        != diagnostics.ready_target_count + diagnostics.blocked_target_count
        or diagnostics.blocked_target_count
        != diagnostics.insufficient_train_support_target_count
        + diagnostics.unseen_group_target_count
        or diagnostics.emitted_point_count != diagnostics.ready_target_count
    ):
        return LiveExecutionBlocker.EVALUATION_PACKAGE_IDENTITY_MISMATCH
    return None


def _metric_value(cell: FarmTotalBaselineValidationMetricCell) -> str | None:
    return str(cell.metric_value) if cell.metric_value is not None else None


def _metric_status(cell: FarmTotalBaselineValidationMetricCell) -> str:
    return cell.metric_status.value


def _metric_reason(cell: FarmTotalBaselineValidationMetricCell) -> str:
    return cell.reason_code.value


def build_success_payload(
    *,
    execution_main_sha: str,
    runner_commit_sha: str,
    obtain: LiveObtainEnvelope,
    data_plane_result: FarmTotalDataPlaneResult,
    package: FarmTotalBaselineEvaluationPackage,
    score_package: FarmTotalBaselineValidationScorePackage,
    authority_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    diagnostics = score_package.diagnostics
    cells = {cell.metric_name: cell for cell in score_package.metric_cells}
    payload: dict[str, Any] = {
        "EXECUTION_STATUS": "PASS",
        "EXECUTION_MAIN_SHA": execution_main_sha,
        "SCORING_RUNNER_COMMIT_SHA": runner_commit_sha,
        "SOURCE_002_DATASET_ID": obtain.dataset_id,
        "SOURCE_002_DATASET_VERSION": obtain.dataset_version,
        "SOURCE_002_MATERIALIZED_DATASET_IDENTITY_SHA256": (
            obtain.materialized_dataset_identity_sha256
        ),
        "OFFICIAL_TRAIN_CONTENT_SHA256": OFFICIAL_TRAIN_CONTENT_SHA256,
        "OFFICIAL_VALIDATION_CONTENT_SHA256": OFFICIAL_VALIDATION_CONTENT_SHA256,
        "TEST_REMAINS_SEALED": obtain.test_remains_sealed,
        "FARM_GROUP_MAPPING_SET_SHA256": data_plane_result.mapping_set_sha256,
        "FARM_AREA_AUTHORITY_SET_SHA256": data_plane_result.area_authority_set_sha256,
        "TRAIN_FARM_TOTAL_DATASET_SHA256": (
            data_plane_result.train_dataset.partition_dataset.dataset_sha256
        ),
        "VALIDATION_FARM_TOTAL_DATASET_SHA256": (
            data_plane_result.validation_dataset.partition_dataset.dataset_sha256
        ),
        "BASELINE_EVALUATION_PACKAGE_SHA256": package.package_sha256,
        "ESTIMATOR_STATE_SHA256": package.estimator_state_sha256,
        "TARGET_IDENTITY_SET_SHA256": package.target_identity_set_sha256,
        "BASELINE_POINT_SET_SHA256": package.baseline_point_set_sha256,
        "TARGET_OUTCOME_SET_SHA256": package.target_outcome_set_sha256,
        "PREDICTION_IDENTITY_SHA256": package.prediction_identity_sha256,
        "SCORING_TARGET_ACTUAL_SET_SHA256": score_package.scoring_target_actual_set_sha256,
        "SCORING_INPUT_SHA256": score_package.scoring_input_sha256,
        "METRIC_RESULT_SET_SHA256": score_package.metric_result_set_sha256,
        "SCORE_PACKAGE_SHA256": score_package.score_package_sha256,
        "TARGET_COUNT": diagnostics.target_count,
        "COMPARABLE_TARGET_COUNT": diagnostics.comparable_target_count,
        "BLOCKED_TARGET_COUNT": diagnostics.blocked_target_count,
        "READY_TARGET_COUNT": diagnostics.ready_target_count,
        "INSUFFICIENT_TRAIN_SUPPORT_TARGET_COUNT": (
            diagnostics.insufficient_train_support_target_count
        ),
        "UNSEEN_GROUP_TARGET_COUNT": diagnostics.unseen_group_target_count,
        "NEGATIVE_VALIDATION_ACTUAL_COUNT": diagnostics.negative_validation_actual_count,
        "MAE_VALUE": _metric_value(cells["MAE"]),
        "MAE_STATUS": _metric_status(cells["MAE"]),
        "MAE_REASON_CODE": _metric_reason(cells["MAE"]),
        "WAPE_VALUE": _metric_value(cells["WAPE"]),
        "WAPE_STATUS": _metric_status(cells["WAPE"]),
        "WAPE_REASON_CODE": _metric_reason(cells["WAPE"]),
        "SMAPE_VALUE": _metric_value(cells["SMAPE"]),
        "SMAPE_STATUS": _metric_status(cells["SMAPE"]),
        "SMAPE_REASON_CODE": _metric_reason(cells["SMAPE"]),
        "VALIDATION_BASELINE_SCORED": True,
    }
    if authority_metadata is not None:
        payload.update(authority_metadata)
    return payload


def build_blocked_payload(*, blocker: str, reason_code: str) -> dict[str, str]:
    return {
        "EXECUTION_STATUS": "BLOCKED",
        "BLOCKER": blocker,
        "REASON_CODE": reason_code,
    }


def run_farm_total_baseline_validation_scoring(
    *,
    authority_dir: Path,
    execution_main_sha: str,
    runner_commit_sha: str,
    obtain_fn: Callable[[], LiveObtainEnvelope] | None = None,
    authority_loader_fn: Callable[[Path], FarmTotalAuthorityBundle] | None = None,
    data_plane_fn: Callable[..., tuple[FarmTotalDatasetBlocker, FarmTotalDataPlaneResult | None]]
    | None = None,
    package_builder_fn: Callable[..., FarmTotalBaselineEvaluationPackage] | None = None,
    scorer_fn: Callable[..., FarmTotalBaselineValidationScorePackage] | None = None,
    verify_repository: bool = True,
) -> dict[str, Any]:
    if verify_repository:
        repo_blocker = verify_repository_identity(
            execution_main_sha=execution_main_sha,
            runner_commit_sha=runner_commit_sha,
        )
        if repo_blocker is not None:
            return build_blocked_payload(
                blocker=repo_blocker.value,
                reason_code=repo_blocker.value,
            )

        authority_lineage_blocker, authority_metadata = validate_r4_authority_binding(
            authority_dir=authority_dir,
        )
        if authority_lineage_blocker is not None:
            return build_blocked_payload(
                blocker=authority_lineage_blocker.value,
                reason_code=authority_lineage_blocker.value,
            )
    else:
        authority_metadata = None

    files_blocker = verify_authority_package_files(authority_dir)
    if files_blocker is not None:
        return build_blocked_payload(
            blocker=files_blocker.value,
            reason_code=files_blocker.value,
        )

    authority_loader = authority_loader_fn or load_authority_bundle_from_directory
    try:
        authority_bundle = authority_loader(authority_dir)
    except (FarmTotalAreaAuthorityLoadError, OSError, ValueError, json.JSONDecodeError):
        return build_blocked_payload(
            blocker=LiveExecutionBlocker.LIVE_AUTHORITY_PACKAGE_INVALID.value,
            reason_code=LiveExecutionBlocker.LIVE_AUTHORITY_PACKAGE_INVALID.value,
        )

    obtain = (
        obtain_fn
        or source_002_live_obtain.obtain_accepted_s2_train_val_content_bytes_from_bound_live_session
    )()
    obtain_blocker = validate_source_002_obtain(obtain)
    if obtain_blocker is not None:
        return build_blocked_payload(
            blocker=obtain_blocker.value,
            reason_code=obtain.reason_code.value,
        )

    train_bytes = obtain.train_content_bytes
    validation_bytes = obtain.validation_content_bytes
    assert train_bytes is not None
    assert validation_bytes is not None

    data_plane = data_plane_fn or materialize_farm_total_baseline_data_plane
    blocker, data_plane_result = data_plane(
        train_content_bytes=train_bytes,
        validation_content_bytes=validation_bytes,
        authority_bundle=authority_bundle,
        verify_official_hashes=True,
    )
    data_plane_blocker = validate_data_plane_result(
        blocker,
        data_plane_result,
        authority_bundle,
    )
    if data_plane_blocker is not None:
        reason = (
            blocker.value
            if blocker != FarmTotalDatasetBlocker.NONE
            else data_plane_blocker.value
        )
        return build_blocked_payload(blocker=data_plane_blocker.value, reason_code=reason)
    assert data_plane_result is not None

    package_builder = package_builder_fn or build_farm_total_baseline_evaluation_package
    try:
        package = package_builder(
            train_dataset=data_plane_result.train_dataset,
            validation_dataset=data_plane_result.validation_dataset,
        )
    except Exception:
        return build_blocked_payload(
            blocker=LiveExecutionBlocker.EVALUATION_PACKAGE_BUILD_FAILED.value,
            reason_code=LiveExecutionBlocker.EVALUATION_PACKAGE_BUILD_FAILED.value,
        )

    package_blocker = validate_evaluation_package(package, data_plane_result)
    if package_blocker is not None:
        return build_blocked_payload(
            blocker=package_blocker.value,
            reason_code=package_blocker.value,
        )

    scorer = scorer_fn or score_farm_total_baseline_validation
    try:
        score_package = scorer(
            evaluation_package=package,
            validation_dataset=data_plane_result.validation_dataset,
        )
    except FarmTotalBaselineValidationScoringError as exc:
        return build_blocked_payload(
            blocker=exc.blocker.value,
            reason_code=exc.reason_code,
        )
    except Exception:
        return build_blocked_payload(
            blocker=LiveExecutionBlocker.SCORING_INTERNAL_ERROR.value,
            reason_code=LiveExecutionBlocker.SCORING_INTERNAL_ERROR.value,
        )

    diagnostics = score_package.diagnostics
    if (
        diagnostics.target_count
        != diagnostics.comparable_target_count + diagnostics.blocked_target_count
        or diagnostics.comparable_target_count != diagnostics.ready_target_count
        or diagnostics.blocked_target_count
        != diagnostics.insufficient_train_support_target_count
        + diagnostics.unseen_group_target_count
        or diagnostics.negative_validation_actual_count != 0
    ):
        return build_blocked_payload(
            blocker=LiveExecutionBlocker.SCORING_DIAGNOSTIC_MISMATCH.value,
            reason_code=LiveExecutionBlocker.SCORING_DIAGNOSTIC_MISMATCH.value,
        )

    return build_success_payload(
        execution_main_sha=execution_main_sha,
        runner_commit_sha=runner_commit_sha,
        obtain=obtain,
        data_plane_result=data_plane_result,
        package=package,
        score_package=score_package,
        authority_metadata=authority_metadata,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run V0.3 Farm-total baseline VALIDATION scoring against official SOURCE-002.",
    )
    parser.add_argument(
        "--authority-dir",
        default=R4_CANONICAL_AUTHORITY_DIR,
        type=Path,
        help="Directory containing the durable R4 Farm-total authority package JSON files.",
    )
    parser.add_argument(
        "--execution-main-sha",
        required=True,
        help="Expected origin/main SHA for this controlled execution.",
    )
    parser.add_argument(
        "--runner-commit-sha",
        required=True,
        help="Expected commit SHA containing the finalized scoring runner.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        payload = run_farm_total_baseline_validation_scoring(
            authority_dir=args.authority_dir,
            execution_main_sha=args.execution_main_sha,
            runner_commit_sha=args.runner_commit_sha,
        )
    except Exception:
        payload = build_blocked_payload(
            blocker=LiveExecutionBlocker.SCORING_INTERNAL_ERROR.value,
            reason_code=LiveExecutionBlocker.SCORING_INTERNAL_ERROR.value,
        )
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0 if payload.get("EXECUTION_STATUS") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
