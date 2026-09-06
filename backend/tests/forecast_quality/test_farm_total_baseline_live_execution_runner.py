"""Synthetic tests for the Farm-total baseline live execution runner."""

from __future__ import annotations

import dataclasses
import importlib.util
import json
import re
import types
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, cast
from unittest.mock import patch

import pytest

from backend.app.forecast_quality.farm_total_area_authority import (
    FarmTotalAreaAuthorityLoadError,
)
from backend.app.forecast_quality.farm_total_baseline_evaluation_package import (
    FARM_TOTAL_BASELINE_EVALUATION_PACKAGE_SCHEMA_VERSION,
    build_farm_total_baseline_evaluation_package,
)
from backend.app.forecast_quality.farm_total_data_plane import (
    FarmTotalAuthorityBundle,
    FarmTotalDataPlaneResult,
    FarmTotalDatasetBlocker,
    authority_bundle_payloads,
)
from backend.app.forecast_quality.farm_total_dataset import (
    FarmTotalDatasetDiagnostics,
    FarmTotalDatasetRow,
    FarmTotalPartitionDataset,
    FarmTotalTrainingDataset,
    FarmTotalValidationDataset,
    compute_partition_dataset_sha256,
)
from backend.app.forecast_quality.farm_total_policy import (
    AREA_AUTHORITY_CLASS_PREVIOUS_SEASON_PROXY,
)
from backend.app.s3_daily_rowset import (
    accepted_s2_train_val_source_002_row_level_read_live_obtain as source_002_live_obtain,
)
from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read import (
    OFFICIAL_TRAIN_CONTENT_SHA256,
    OFFICIAL_VALIDATION_CONTENT_SHA256,
)
from backend.tests.forecast_quality.fixtures.farm_total_synthetic_authority import (
    build_synthetic_authority_bundle,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNER_PATH = REPO_ROOT / "scripts" / "run_v03_farm_total_baseline_evaluation_package.py"
SHA256_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SEASON = "2025~2026"

LiveObtainEnvelope = source_002_live_obtain.AcceptedS2TrainValLiveObtainEnvelope


def _load_runner_module() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("farm_total_baseline_live_runner", RUNNER_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


RUNNER = _load_runner_module()


def _write_authority_dir(tmp_path: Path) -> Path:
    bundle = build_synthetic_authority_bundle()
    mapping_payload, area_payload = authority_bundle_payloads(bundle)
    authority_dir = tmp_path / "authority"
    authority_dir.mkdir(exist_ok=True)
    (authority_dir / "farm_total_group_mapping_package.json").write_text(
        json.dumps(mapping_payload),
        encoding="utf-8",
    )
    (authority_dir / "farm_total_area_authority_package.json").write_text(
        json.dumps(area_payload),
        encoding="utf-8",
    )
    return authority_dir


def _synthetic_row(
    *,
    group: str,
    harvest_date: date,
    quantity_kg: Decimal,
    partition: Literal["TRAIN", "VALIDATION"],
) -> FarmTotalDatasetRow:
    return FarmTotalDatasetRow(
        season_business_key=SEASON,
        baseline_farm_group_key=group,
        harvest_business_date=harvest_date,
        partition=partition,
        area_mu=Decimal("100.0"),
        area_authority_class=AREA_AUTHORITY_CLASS_PREVIOUS_SEASON_PROXY,
        actual_harvest_quantity_kg=quantity_kg,
        actual_harvest_kg_per_mu=quantity_kg / Decimal("100.0"),
        source_actual_row_count=1,
        source_farm_business_keys=(f"farm-{group}",),
        area_authority_row_hash=f"area-hash-{group}",
        actual_projection_hash=f"proj-{group}-{harvest_date.isoformat()}",
        row_hash=f"row-{group}-{harvest_date.isoformat()}-{partition}",
    )


def _synthetic_data_plane_result() -> FarmTotalDataPlaneResult:
    train_rows = tuple(
        _synthetic_row(
            group="alpha",
            harvest_date=date(2025, 9, index + 1),
            quantity_kg=Decimal(str((index + 1) * 10)),
            partition="TRAIN",
        )
        for index in range(5)
    )
    validation_rows = (
        _synthetic_row(
            group="alpha",
            harvest_date=date(2025, 9, 1),
            quantity_kg=Decimal("1"),
            partition="VALIDATION",
        ),
    )
    bundle = build_synthetic_authority_bundle()
    train_dataset = FarmTotalTrainingDataset(
        partition_dataset=FarmTotalPartitionDataset(
            partition="TRAIN",
            schema_version="test-schema",
            rows=train_rows,
            dataset_sha256=compute_partition_dataset_sha256(train_rows),
        ),
        diagnostics=FarmTotalDatasetDiagnostics(
            partition="TRAIN",
            farm_group_count=1,
            date_count=5,
            row_count=5,
            total_area_mu="100.0",
            total_actual_harvest_kg="0",
            kg_per_mu_min=None,
            kg_per_mu_p25=None,
            kg_per_mu_median=None,
            kg_per_mu_p75=None,
            kg_per_mu_max=None,
        ),
    )
    validation_dataset = FarmTotalValidationDataset(
        partition_dataset=FarmTotalPartitionDataset(
            partition="VALIDATION",
            schema_version="test-schema",
            rows=validation_rows,
            dataset_sha256=compute_partition_dataset_sha256(validation_rows),
        ),
        diagnostics=FarmTotalDatasetDiagnostics(
            partition="VALIDATION",
            farm_group_count=1,
            date_count=1,
            row_count=1,
            total_area_mu="100.0",
            total_actual_harvest_kg="0",
            kg_per_mu_min=None,
            kg_per_mu_p25=None,
            kg_per_mu_median=None,
            kg_per_mu_p75=None,
            kg_per_mu_max=None,
        ),
    )
    return FarmTotalDataPlaneResult(
        train_dataset=train_dataset,
        validation_dataset=validation_dataset,
        audit_union_diagnostics=train_dataset.diagnostics,
        mapping_set_sha256=bundle.mapping_package.mapping_set_sha256,
        area_authority_set_sha256=bundle.area_package.area_authority_set_sha256,
        area_double_count_count=0,
        source_farm_double_map_count=0,
        source_actual_double_count=0,
        validation_used_as_training_input=False,
    )


def _successful_obtain() -> LiveObtainEnvelope:
    return LiveObtainEnvelope(
        obtained=True,
        source_002_row_level_read=False,
        official_hashes_attested_from_a_live_read=False,
        reason_code=source_002_live_obtain.LiveObtainReasonCode.OBTAINED,
        dataset_id="source-002",
        dataset_version="v1",
        materialized_dataset_identity_sha256="a" * 64,
        train_content_bytes=b"train-bytes",
        validation_content_bytes=b"validation-bytes",
        train_row_count=10,
        train_byte_count=10,
        validation_row_count=5,
        validation_byte_count=11,
        test_row_count=0,
        test_remains_sealed=True,
    )


def _run_synthetic(
    tmp_path: Path,
    *,
    obtain_fn: Callable[[], LiveObtainEnvelope] | None = None,
    authority_loader_fn: Callable[[Path], FarmTotalAuthorityBundle] | None = None,
    data_plane_fn: Callable[..., tuple[FarmTotalDatasetBlocker, FarmTotalDataPlaneResult | None]]
    | None = None,
    package_builder_fn: Callable[..., Any] | None = None,
    authority_dir: Path | None = None,
) -> dict[str, Any]:
    resolved_authority_dir = authority_dir or _write_authority_dir(tmp_path)
    data_plane_result = _synthetic_data_plane_result()
    package = build_farm_total_baseline_evaluation_package(
        train_dataset=data_plane_result.train_dataset,
        validation_dataset=data_plane_result.validation_dataset,
    )
    return cast(
        dict[str, Any],
        RUNNER.run_farm_total_baseline_live_execution(
            authority_dir=resolved_authority_dir,
            execution_main_sha="main-sha",
            runner_commit_sha="runner-sha",
            obtain_fn=obtain_fn or (lambda: _successful_obtain()),
            authority_loader_fn=authority_loader_fn,
            data_plane_fn=data_plane_fn
            or (lambda **_kwargs: (FarmTotalDatasetBlocker.NONE, data_plane_result)),
            package_builder_fn=package_builder_fn or (lambda **kwargs: package),
            verify_repository=False,
        ),
    )


def test_successful_synthetic_orchestration(tmp_path: Path) -> None:
    data_plane_result = _synthetic_data_plane_result()
    package = build_farm_total_baseline_evaluation_package(
        train_dataset=data_plane_result.train_dataset,
        validation_dataset=data_plane_result.validation_dataset,
    )

    def data_plane_fn(
        **_kwargs: object,
    ) -> tuple[FarmTotalDatasetBlocker, FarmTotalDataPlaneResult]:
        return FarmTotalDatasetBlocker.NONE, data_plane_result

    payload = _run_synthetic(
        tmp_path,
        data_plane_fn=data_plane_fn,
        package_builder_fn=lambda **kwargs: package,
    )
    assert payload["EXECUTION_STATUS"] == "PASS"
    assert payload["TARGET_COUNT"] == package.target_count
    assert payload["PACKAGE_SHA256"] == package.package_sha256


def test_authority_dir_required_by_cli() -> None:
    with pytest.raises(SystemExit):
        RUNNER.parse_args([])


def test_missing_mapping_file_fail_closed(tmp_path: Path) -> None:
    authority_dir = tmp_path / "authority"
    authority_dir.mkdir()
    (authority_dir / "farm_total_area_authority_package.json").write_text("{}", encoding="utf-8")
    payload = _run_synthetic(tmp_path, authority_dir=authority_dir)
    assert payload["EXECUTION_STATUS"] == "BLOCKED"
    assert payload["BLOCKER"] == "LIVE_AUTHORITY_PACKAGE_FILES_UNAVAILABLE"


def test_missing_area_file_fail_closed(tmp_path: Path) -> None:
    authority_dir = tmp_path / "authority"
    authority_dir.mkdir()
    (authority_dir / "farm_total_group_mapping_package.json").write_text("{}", encoding="utf-8")
    payload = _run_synthetic(tmp_path, authority_dir=authority_dir)
    assert payload["EXECUTION_STATUS"] == "BLOCKED"
    assert payload["BLOCKER"] == "LIVE_AUTHORITY_PACKAGE_FILES_UNAVAILABLE"


def test_invalid_authority_bundle_fail_closed(tmp_path: Path) -> None:
    def broken_loader(_authority_dir: Path) -> FarmTotalAuthorityBundle:
        raise FarmTotalAreaAuthorityLoadError("invalid")

    payload = _run_synthetic(tmp_path, authority_loader_fn=broken_loader)
    assert payload["EXECUTION_STATUS"] == "BLOCKED"
    assert payload["BLOCKER"] == "LIVE_AUTHORITY_PACKAGE_INVALID"


def test_source_002_obtain_failure_fail_closed(tmp_path: Path) -> None:
    def failed_obtain() -> LiveObtainEnvelope:
        return LiveObtainEnvelope(
            obtained=False,
            source_002_row_level_read=False,
            official_hashes_attested_from_a_live_read=False,
            reason_code=source_002_live_obtain.LiveObtainReasonCode.FAIL_CLOSED_NO_ACCEPTED_DATASET,
            test_remains_sealed=True,
        )

    payload = _run_synthetic(tmp_path, obtain_fn=failed_obtain)
    assert payload["EXECUTION_STATUS"] == "BLOCKED"
    assert payload["BLOCKER"] == "SOURCE_002_OBTAIN_FAILED"


def test_missing_train_bytes_fail_closed(tmp_path: Path) -> None:
    def missing_train() -> LiveObtainEnvelope:
        envelope = _successful_obtain()
        return envelope.model_copy(update={"train_content_bytes": b""})

    payload = _run_synthetic(tmp_path, obtain_fn=missing_train)
    assert payload["BLOCKER"] == "SOURCE_002_BYTES_MISSING"


def test_missing_validation_bytes_fail_closed(tmp_path: Path) -> None:
    def missing_validation() -> LiveObtainEnvelope:
        envelope = _successful_obtain()
        return envelope.model_copy(update={"validation_content_bytes": None})

    payload = _run_synthetic(tmp_path, obtain_fn=missing_validation)
    assert payload["BLOCKER"] == "SOURCE_002_BYTES_MISSING"


def test_test_remains_sealed_false_rejected(tmp_path: Path) -> None:
    def unsealed() -> LiveObtainEnvelope:
        envelope = _successful_obtain()
        return envelope.model_copy(update={"test_remains_sealed": False})

    payload = _run_synthetic(tmp_path, obtain_fn=unsealed)
    assert payload["BLOCKER"] == "TEST_CUSTODY_NOT_SEALED"


def test_data_plane_blocker_rejected(tmp_path: Path) -> None:
    def blocked_plane(**_kwargs: object) -> tuple[FarmTotalDatasetBlocker, None]:
        return FarmTotalDatasetBlocker.OFFICIAL_HASH_MISMATCH, None

    payload = _run_synthetic(tmp_path, data_plane_fn=blocked_plane)
    assert payload["BLOCKER"] == "FARM_TOTAL_DATA_PLANE_BLOCKED"


def test_data_plane_none_result_rejected(tmp_path: Path) -> None:
    def none_plane(**_kwargs: object) -> tuple[FarmTotalDatasetBlocker, None]:
        return FarmTotalDatasetBlocker.NONE, None

    payload = _run_synthetic(tmp_path, data_plane_fn=none_plane)
    assert payload["BLOCKER"] == "FARM_TOTAL_DATA_PLANE_BLOCKED"


def test_validation_used_as_training_input_rejected(tmp_path: Path) -> None:
    data_plane_result = _synthetic_data_plane_result()
    violated = FarmTotalDataPlaneResult(
        train_dataset=data_plane_result.train_dataset,
        validation_dataset=data_plane_result.validation_dataset,
        audit_union_diagnostics=data_plane_result.audit_union_diagnostics,
        mapping_set_sha256=data_plane_result.mapping_set_sha256,
        area_authority_set_sha256=data_plane_result.area_authority_set_sha256,
        area_double_count_count=0,
        source_farm_double_map_count=0,
        source_actual_double_count=0,
        validation_used_as_training_input=True,
    )

    payload = _run_synthetic(
        tmp_path,
        data_plane_fn=lambda **_kwargs: (FarmTotalDatasetBlocker.NONE, violated),
    )
    assert payload["BLOCKER"] == "FARM_TOTAL_DATA_PLANE_INVARIANT_VIOLATION"


def test_area_double_count_rejected(tmp_path: Path) -> None:
    data_plane_result = _synthetic_data_plane_result()
    violated = dataclasses.replace(data_plane_result, area_double_count_count=1)
    payload = _run_synthetic(
        tmp_path,
        data_plane_fn=lambda **_kwargs: (FarmTotalDatasetBlocker.NONE, violated),
    )
    assert payload["BLOCKER"] == "FARM_TOTAL_DATA_PLANE_INVARIANT_VIOLATION"


def test_source_farm_double_map_count_rejected(tmp_path: Path) -> None:
    data_plane_result = _synthetic_data_plane_result()
    violated = dataclasses.replace(data_plane_result, source_farm_double_map_count=1)
    payload = _run_synthetic(
        tmp_path,
        data_plane_fn=lambda **_kwargs: (FarmTotalDatasetBlocker.NONE, violated),
    )
    assert payload["BLOCKER"] == "FARM_TOTAL_DATA_PLANE_INVARIANT_VIOLATION"


def test_source_actual_double_count_rejected(tmp_path: Path) -> None:
    data_plane_result = _synthetic_data_plane_result()
    violated = dataclasses.replace(data_plane_result, source_actual_double_count=1)
    payload = _run_synthetic(
        tmp_path,
        data_plane_fn=lambda **_kwargs: (FarmTotalDatasetBlocker.NONE, violated),
    )
    assert payload["BLOCKER"] == "FARM_TOTAL_DATA_PLANE_INVARIANT_VIOLATION"


def test_package_builder_called_only_after_data_plane_success(tmp_path: Path) -> None:
    called = {"package": False}

    def blocked_plane(**_kwargs: object) -> tuple[FarmTotalDatasetBlocker, None]:
        return FarmTotalDatasetBlocker.MALFORMED_PARTITION_BYTES, None

    def package_builder(**_kwargs: object) -> None:
        called["package"] = True
        raise AssertionError("package builder should not run")

    payload = _run_synthetic(
        tmp_path,
        data_plane_fn=blocked_plane,
        package_builder_fn=package_builder,
    )
    assert payload["EXECUTION_STATUS"] == "BLOCKED"
    assert called["package"] is False


def test_successful_package_exposes_six_hashes(tmp_path: Path) -> None:
    data_plane_result = _synthetic_data_plane_result()
    package = build_farm_total_baseline_evaluation_package(
        train_dataset=data_plane_result.train_dataset,
        validation_dataset=data_plane_result.validation_dataset,
    )
    payload = _run_synthetic(
        tmp_path,
        data_plane_fn=lambda **_kwargs: (FarmTotalDatasetBlocker.NONE, data_plane_result),
        package_builder_fn=lambda **kwargs: package,
    )
    for field in (
        "ESTIMATOR_STATE_SHA256",
        "TARGET_IDENTITY_SET_SHA256",
        "BASELINE_POINT_SET_SHA256",
        "TARGET_OUTCOME_SET_SHA256",
        "PREDICTION_IDENTITY_SHA256",
        "PACKAGE_SHA256",
    ):
        assert SHA256_HEX_PATTERN.match(payload[field])


def test_success_output_includes_required_diagnostics_counts(tmp_path: Path) -> None:
    data_plane_result = _synthetic_data_plane_result()
    package = build_farm_total_baseline_evaluation_package(
        train_dataset=data_plane_result.train_dataset,
        validation_dataset=data_plane_result.validation_dataset,
    )
    payload = _run_synthetic(
        tmp_path,
        data_plane_fn=lambda **_kwargs: (FarmTotalDatasetBlocker.NONE, data_plane_result),
        package_builder_fn=lambda **kwargs: package,
    )
    for field in (
        "TARGET_COUNT",
        "EMITTED_POINT_COUNT",
        "BLOCKED_TARGET_COUNT",
        "READY_TARGET_COUNT",
        "INSUFFICIENT_TRAIN_SUPPORT_TARGET_COUNT",
        "UNSEEN_GROUP_TARGET_COUNT",
    ):
        assert field in payload


def test_output_contains_no_target_level_actuals(tmp_path: Path) -> None:
    payload = _run_synthetic(tmp_path)
    serialized = json.dumps(payload)
    assert "actual_harvest_quantity_kg" not in serialized
    assert "actual_harvest_kg_per_mu" not in serialized


def test_output_contains_no_target_level_baseline_values(tmp_path: Path) -> None:
    payload = _run_synthetic(tmp_path)
    serialized = json.dumps(payload)
    assert "baseline_harvest_quantity_kg" not in serialized


def test_output_contains_no_test_payload(tmp_path: Path) -> None:
    payload = _run_synthetic(tmp_path)
    serialized = json.dumps(payload)
    assert "test_content_bytes" not in serialized
    assert "TEST_BYTES" not in serialized


def test_output_contains_no_scoring_or_metric_fields(tmp_path: Path) -> None:
    payload = _run_synthetic(tmp_path)
    serialized = json.dumps(payload).lower()
    for token in ("mae", "wape", "smape", "mape", "bias", "metric_result", "score"):
        assert token not in serialized


def test_output_contains_no_p80_p90_fields(tmp_path: Path) -> None:
    payload = _run_synthetic(tmp_path)
    serialized = json.dumps(payload).lower()
    assert "p80" not in serialized
    assert "p90" not in serialized


def test_deterministic_json_payload_for_identical_synthetic_input(tmp_path: Path) -> None:
    data_plane_result = _synthetic_data_plane_result()
    package = build_farm_total_baseline_evaluation_package(
        train_dataset=data_plane_result.train_dataset,
        validation_dataset=data_plane_result.validation_dataset,
    )
    authority_dir = _write_authority_dir(tmp_path)
    payload_a = _run_synthetic(
        tmp_path,
        authority_dir=authority_dir,
        data_plane_fn=lambda **_kwargs: (FarmTotalDatasetBlocker.NONE, data_plane_result),
        package_builder_fn=lambda **kwargs: package,
    )
    payload_b = _run_synthetic(
        tmp_path,
        authority_dir=authority_dir,
        data_plane_fn=lambda **_kwargs: (FarmTotalDatasetBlocker.NONE, data_plane_result),
        package_builder_fn=lambda **kwargs: package,
    )
    assert payload_a == payload_b


def test_fail_closed_json_is_deterministic(tmp_path: Path) -> None:
    payload_a = _run_synthetic(
        tmp_path,
        obtain_fn=lambda: LiveObtainEnvelope(
            obtained=False,
            source_002_row_level_read=False,
            official_hashes_attested_from_a_live_read=False,
            reason_code=source_002_live_obtain.LiveObtainReasonCode.FAIL_CLOSED_NO_ACCEPTED_DATASET,
            test_remains_sealed=True,
        ),
    )
    payload_b = _run_synthetic(
        tmp_path,
        obtain_fn=lambda: LiveObtainEnvelope(
            obtained=False,
            source_002_row_level_read=False,
            official_hashes_attested_from_a_live_read=False,
            reason_code=source_002_live_obtain.LiveObtainReasonCode.FAIL_CLOSED_NO_ACCEPTED_DATASET,
            test_remains_sealed=True,
        ),
    )
    assert payload_a == payload_b


def test_fail_closed_exit_nonzero_at_cli_seam(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authority_dir = _write_authority_dir(tmp_path)
    monkeypatch.setattr(
        RUNNER,
        "run_farm_total_baseline_live_execution",
        lambda **kwargs: {
            "EXECUTION_STATUS": "BLOCKED",
            "BLOCKER": "SOURCE_002_OBTAIN_FAILED",
            "REASON_CODE": "FAIL_CLOSED_NO_ACCEPTED_DATASET",
        },
    )
    exit_code = RUNNER.main(
        [
            "--authority-dir",
            str(authority_dir),
            "--execution-main-sha",
            "main-sha",
            "--runner-commit-sha",
            "runner-sha",
        ]
    )
    assert exit_code == 1


def test_repository_identity_mismatch_blocked(tmp_path: Path) -> None:
    authority_dir = _write_authority_dir(tmp_path)
    with patch.object(RUNNER, "_git_rev_parse", side_effect=["wrong-runner", "expected-main"]):
        payload = RUNNER.run_farm_total_baseline_live_execution(
            authority_dir=authority_dir,
            execution_main_sha="expected-main",
            runner_commit_sha="expected-runner",
            obtain_fn=lambda: _successful_obtain(),
            verify_repository=True,
        )
    assert payload["BLOCKER"] == "REPOSITORY_IDENTITY_MISMATCH"


def test_official_hash_constants_reported_as_identity(tmp_path: Path) -> None:
    payload = _run_synthetic(tmp_path)
    assert payload["OFFICIAL_TRAIN_CONTENT_SHA256"] == OFFICIAL_TRAIN_CONTENT_SHA256
    assert payload["OFFICIAL_VALIDATION_CONTENT_SHA256"] == OFFICIAL_VALIDATION_CONTENT_SHA256


def test_authority_semantic_hashes_come_from_data_plane_result(tmp_path: Path) -> None:
    data_plane_result = _synthetic_data_plane_result()
    payload = _run_synthetic(
        tmp_path,
        data_plane_fn=lambda **_kwargs: (FarmTotalDatasetBlocker.NONE, data_plane_result),
    )
    assert payload["FARM_GROUP_MAPPING_SET_SHA256"] == data_plane_result.mapping_set_sha256
    assert payload["FARM_AREA_AUTHORITY_SET_SHA256"] == data_plane_result.area_authority_set_sha256


def test_no_raw_train_or_validation_contents_in_serialized_output(tmp_path: Path) -> None:
    payload = _run_synthetic(tmp_path)
    serialized = json.dumps(payload)
    assert "train-bytes" not in serialized
    assert "validation-bytes" not in serialized
    assert "TRAIN_TOTAL_ACTUAL_HARVEST_KG" not in serialized
    assert "VALIDATION_TOTAL_ACTUAL_HARVEST_KG" not in serialized


def test_evaluation_package_build_failure_blocked(tmp_path: Path) -> None:
    data_plane_result = _synthetic_data_plane_result()

    def broken_builder(**_kwargs: object) -> None:
        raise RuntimeError("package failed")

    payload = _run_synthetic(
        tmp_path,
        data_plane_fn=lambda **_kwargs: (FarmTotalDatasetBlocker.NONE, data_plane_result),
        package_builder_fn=broken_builder,
    )
    assert payload["BLOCKER"] == "EVALUATION_PACKAGE_BUILD_FAILED"


def test_cli_success_exit_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    authority_dir = _write_authority_dir(tmp_path)
    monkeypatch.setattr(
        RUNNER,
        "run_farm_total_baseline_live_execution",
        lambda **kwargs: {"EXECUTION_STATUS": "PASS"},
    )
    assert (
        RUNNER.main(
            [
                "--authority-dir",
                str(authority_dir),
                "--execution-main-sha",
                "main-sha",
                "--runner-commit-sha",
                "runner-sha",
            ]
        )
        == 0
    )


def test_package_schema_version_in_success_output(tmp_path: Path) -> None:
    payload = _run_synthetic(tmp_path)
    assert (
        payload["PACKAGE_SCHEMA_VERSION"] == FARM_TOTAL_BASELINE_EVALUATION_PACKAGE_SCHEMA_VERSION
    )


def test_test_remains_sealed_true_in_success_output(tmp_path: Path) -> None:
    payload = _run_synthetic(tmp_path)
    assert payload["TEST_REMAINS_SEALED"] is True


def test_validation_used_as_training_input_false_in_success_output(tmp_path: Path) -> None:
    payload = _run_synthetic(tmp_path)
    assert payload["VALIDATION_USED_AS_TRAINING_INPUT"] is False
