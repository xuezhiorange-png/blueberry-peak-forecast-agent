"""Contract hardening tests for V0.3 Farm-total baseline data plane R2."""

from __future__ import annotations

import ast
import inspect
import subprocess
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app.forecast_quality.canonical import emit_s3_area_mu
from backend.app.forecast_quality.farm_total_area_authority import (
    FarmTotalAreaAuthorityBlocker,
    area_authority_package_to_payload,
    build_area_authority_row,
    validate_area_authority_package_payload,
)
from backend.app.forecast_quality.farm_total_authority_binding import (
    FarmTotalAuthorityBindingBlocker,
    validate_mapping_area_authority_binding,
)
from backend.app.forecast_quality.farm_total_data_plane import (
    FarmTotalAuthorityBundle,
    materialize_farm_total_baseline_data_plane,
)
from backend.app.forecast_quality.farm_total_dataset import (
    FarmTotalDatasetBlocker,
    _percentile,
    build_farm_total_data_plane,
    build_partition_dataset,
    compute_partition_diagnostics,
)
from backend.app.forecast_quality.farm_total_group_mapping import (
    FarmGroupMappingBlocker,
    mapping_package_to_payload,
    validate_mapping_package_payload,
)
from backend.app.forecast_quality.farm_total_policy import (
    AREA_AUTHORITY_CLASS_PREVIOUS_SEASON_PROXY,
    FARM_TOTAL_MAPPING_POLICY_VERSION,
    FARM_TOTAL_PRIOR_AREA_SOURCE_SEASON,
    FARM_TOTAL_TARGET_SEASON,
)
from backend.app.s2_materialized_dataset.lane_d.canonical import build_partition_bytes
from backend.app.s2_materialized_dataset.shared.contracts import MaterializableRow
from backend.app.s3_daily_rowset.schemas import (
    EXPECTED_DATASET_ID,
    EXPECTED_DATASET_VERSION,
    EXPECTED_MATERIALIZED_DATASET_IDENTITY_SHA256,
)
from backend.tests.forecast_quality.fixtures.farm_total_synthetic_authority import (
    build_synthetic_authority_bundle,
)

SEASON = "2025~2026"
REPO_ROOT = Path(__file__).resolve().parents[3]
GENERATE_SCRIPT = REPO_ROOT / "scripts" / "generate_v03_farm_total_authority_packages.py"
VERIFICATION_SCRIPT = REPO_ROOT / "scripts" / "run_v03_farm_total_data_plane_verification.py"


def _row(
    *,
    farm: str,
    harvest_date: date,
    quantity: str = "10.0",
) -> MaterializableRow:
    return MaterializableRow(
        season=SEASON,
        farm=farm,
        subfarm="sf-1",
        variety="v1",
        harvest_business_date=harvest_date,
        actual_harvest_quantity_kg=Decimal(quantity),
        source_row_identity=f"src-{farm}-{harvest_date.isoformat()}",
        cleaned_row_identity=f"cln-{farm}-{harvest_date.isoformat()}",
        pit_visibility_identity=f"pit-{farm}-{harvest_date.isoformat()}",
        revision_winner_identity=f"rev-{farm}-{harvest_date.isoformat()}",
    )


def _valid_train_val_bytes(bundle: FarmTotalAuthorityBundle) -> tuple[bytes, bytes]:
    train = build_partition_bytes(
        (
            _row(farm="farm-alpha", harvest_date=date(2025, 9, 1)),
            _row(farm="farm-beta-a", harvest_date=date(2025, 9, 2)),
        )
    )
    val = build_partition_bytes((_row(farm="farm-beta-a", harvest_date=date(2026, 2, 1)),))
    return train, val


class TestPartitionFailClosed:
    def test_test_date_row_returns_test_partition_forbidden(self) -> None:
        bundle = build_synthetic_authority_bundle()
        test_bytes = build_partition_bytes(
            (_row(farm="farm-alpha", harvest_date=date(2026, 3, 15)),)
        )
        blocker, dataset = build_partition_dataset(
            partition="TRAIN",
            content_bytes=test_bytes,
            mapping_package=bundle.mapping_package,
            area_package=bundle.area_package,
            verify_official_hashes=False,
        )
        assert blocker == FarmTotalDatasetBlocker.TEST_PARTITION_FORBIDDEN
        assert dataset is None

    def test_validation_row_in_train_returns_partition_membership_mismatch(self) -> None:
        bundle = build_synthetic_authority_bundle()
        val_in_train = build_partition_bytes(
            (_row(farm="farm-alpha", harvest_date=date(2026, 2, 1)),)
        )
        blocker, dataset = build_partition_dataset(
            partition="TRAIN",
            content_bytes=val_in_train,
            mapping_package=bundle.mapping_package,
            area_package=bundle.area_package,
            verify_official_hashes=False,
        )
        assert blocker == FarmTotalDatasetBlocker.PARTITION_MEMBERSHIP_MISMATCH
        assert dataset is None

    def test_train_row_in_validation_returns_partition_membership_mismatch(self) -> None:
        bundle = build_synthetic_authority_bundle()
        train_in_val = build_partition_bytes(
            (_row(farm="farm-alpha", harvest_date=date(2025, 9, 1)),)
        )
        blocker, dataset = build_partition_dataset(
            partition="VALIDATION",
            content_bytes=train_in_val,
            mapping_package=bundle.mapping_package,
            area_package=bundle.area_package,
            verify_official_hashes=False,
        )
        assert blocker == FarmTotalDatasetBlocker.PARTITION_MEMBERSHIP_MISMATCH
        assert dataset is None


class TestMappingFrozenIdentityValidation:
    @pytest.fixture()
    def mapping_payload(self) -> dict:
        bundle = build_synthetic_authority_bundle()
        return mapping_package_to_payload(bundle.mapping_package)

    def test_mapping_source_dataset_id_tamper_rejected(self, mapping_payload: dict) -> None:
        mapping_payload["source_dataset_id"] = "tampered"
        blocker, package = validate_mapping_package_payload(mapping_payload)
        assert blocker == FarmGroupMappingBlocker.MAPPING_SOURCE_DATASET_ID_MISMATCH
        assert package is None

    def test_mapping_source_dataset_version_tamper_rejected(self, mapping_payload: dict) -> None:
        mapping_payload["source_dataset_version"] = "tampered"
        blocker, package = validate_mapping_package_payload(mapping_payload)
        assert blocker == FarmGroupMappingBlocker.MAPPING_SOURCE_DATASET_VERSION_MISMATCH
        assert package is None

    def test_materialized_dataset_identity_tamper_rejected(self, mapping_payload: dict) -> None:
        mapping_payload["materialized_dataset_identity_sha256"] = "0" * 64
        blocker, package = validate_mapping_package_payload(mapping_payload)
        assert blocker == FarmGroupMappingBlocker.MAPPING_MATERIALIZED_IDENTITY_MISMATCH
        assert package is None

    def test_mapping_policy_tamper_rejected(self, mapping_payload: dict) -> None:
        mapping_payload["mapping_policy_version"] = "tampered"
        blocker, package = validate_mapping_package_payload(mapping_payload)
        assert blocker == FarmGroupMappingBlocker.MAPPING_POLICY_VERSION_MISMATCH
        assert package is None

    def test_target_season_tamper_rejected(self, mapping_payload: dict) -> None:
        mapping_payload["target_season"] = "tampered"
        blocker, package = validate_mapping_package_payload(mapping_payload)
        assert blocker == FarmGroupMappingBlocker.MAPPING_TARGET_SEASON_MISMATCH
        assert package is None

    def test_frozen_identity_fields_match_expected(self, mapping_payload: dict) -> None:
        assert mapping_payload["mapping_policy_version"] == FARM_TOTAL_MAPPING_POLICY_VERSION
        assert mapping_payload["target_season"] == FARM_TOTAL_TARGET_SEASON
        assert mapping_payload["source_dataset_id"] == EXPECTED_DATASET_ID
        assert mapping_payload["source_dataset_version"] == EXPECTED_DATASET_VERSION
        assert (
            mapping_payload["materialized_dataset_identity_sha256"]
            == EXPECTED_MATERIALIZED_DATASET_IDENTITY_SHA256
        )


class TestAreaFrozenIdentityValidation:
    @pytest.fixture()
    def area_payload(self) -> dict:
        bundle = build_synthetic_authority_bundle()
        return area_authority_package_to_payload(bundle.area_package)

    def test_area_source_season_tamper_rejected(self, area_payload: dict) -> None:
        area_payload["source_season"] = "tampered"
        blocker, package = validate_area_authority_package_payload(area_payload)
        assert blocker == FarmTotalAreaAuthorityBlocker.AREA_SOURCE_SEASON_MISMATCH
        assert package is None

    def test_area_target_season_tamper_rejected(self, area_payload: dict) -> None:
        area_payload["target_season"] = "tampered"
        blocker, package = validate_area_authority_package_payload(area_payload)
        assert blocker == FarmTotalAreaAuthorityBlocker.AREA_TARGET_SEASON_MISMATCH
        assert package is None

    def test_area_mapping_policy_tamper_rejected(self, area_payload: dict) -> None:
        area_payload["mapping_policy_version"] = "tampered"
        blocker, package = validate_area_authority_package_payload(area_payload)
        assert blocker == FarmTotalAreaAuthorityBlocker.AREA_MAPPING_POLICY_VERSION_MISMATCH
        assert package is None

    def test_area_mapping_identity_hash_mismatch_rejected(self) -> None:
        bundle = build_synthetic_authority_bundle()
        alpha_row = bundle.area_package.rows[0]
        beta_row = bundle.area_package.rows[1]
        inconsistent_alpha = build_area_authority_row(
            baseline_farm_group_key=alpha_row.baseline_farm_group_key,
            source_farm_business_keys=alpha_row.source_farm_business_keys,
            area_mu=alpha_row.area_mu,
            area_authority_class=alpha_row.area_authority_class,
            area_source_season=alpha_row.area_source_season,
            area_source_identity=alpha_row.area_source_identity,
            area_source_hash=alpha_row.area_source_hash,
            mapping_policy_version=alpha_row.mapping_policy_version,
            mapping_identity_hash="a" * 64,
            source_row_refs=alpha_row.source_row_refs,
        )
        inconsistent_beta = build_area_authority_row(
            baseline_farm_group_key=beta_row.baseline_farm_group_key,
            source_farm_business_keys=beta_row.source_farm_business_keys,
            area_mu=beta_row.area_mu,
            area_authority_class=beta_row.area_authority_class,
            area_source_season=beta_row.area_source_season,
            area_source_identity=beta_row.area_source_identity,
            area_source_hash=beta_row.area_source_hash,
            mapping_policy_version=beta_row.mapping_policy_version,
            mapping_identity_hash="b" * 64,
            source_row_refs=beta_row.source_row_refs,
        )
        from backend.app.forecast_quality.farm_total_area_authority import (
            build_area_authority_package,
        )

        tampered = build_area_authority_package(
            rows=(inconsistent_alpha, inconsistent_beta),
            source_file_hashes=bundle.area_package.source_file_hashes,
            mapping_policy_version=FARM_TOTAL_MAPPING_POLICY_VERSION,
            mapping_identity_hash="a" * 64,
        )
        payload = area_authority_package_to_payload(tampered)
        blocker, package = validate_area_authority_package_payload(payload)
        assert blocker == FarmTotalAreaAuthorityBlocker.AREA_MAPPING_IDENTITY_HASH_INCONSISTENT
        assert package is None

    def test_frozen_identity_fields_match_expected(self, area_payload: dict) -> None:
        assert area_payload["source_season"] == FARM_TOTAL_PRIOR_AREA_SOURCE_SEASON
        assert area_payload["target_season"] == FARM_TOTAL_TARGET_SEASON
        assert area_payload["mapping_policy_version"] == FARM_TOTAL_MAPPING_POLICY_VERSION
        hashes = {row["mapping_identity_hash"] for row in area_payload["rows"]}
        assert len(hashes) == 1
        assert hashes.pop()


class TestCrossPackageBinding:
    def test_area_group_missing_rejected(self) -> None:
        bundle = build_synthetic_authority_bundle()
        area_rows = tuple(
            row for row in bundle.area_package.rows if row.baseline_farm_group_key != "alpha"
        )
        from backend.app.forecast_quality.farm_total_area_authority import (
            build_area_authority_package,
        )

        tampered_area = build_area_authority_package(
            rows=area_rows,
            source_file_hashes=bundle.area_package.source_file_hashes,
            mapping_policy_version=FARM_TOTAL_MAPPING_POLICY_VERSION,
            mapping_identity_hash=bundle.mapping_package.mapping_set_sha256,
        )
        blocker = validate_mapping_area_authority_binding(
            mapping_package=bundle.mapping_package,
            area_package=tampered_area,
        )
        assert blocker == FarmTotalAuthorityBindingBlocker.AUTHORITY_GROUP_SET_MISMATCH

    def test_extra_area_group_rejected(self) -> None:
        bundle = build_synthetic_authority_bundle()
        extra_row = build_area_authority_row(
            baseline_farm_group_key="extra",
            source_farm_business_keys=("farm-extra",),
            area_mu=Decimal("50.0"),
            area_authority_class=AREA_AUTHORITY_CLASS_PREVIOUS_SEASON_PROXY,
            area_source_season=FARM_TOTAL_PRIOR_AREA_SOURCE_SEASON,
            area_source_identity="synthetic",
            area_source_hash="d" * 64,
            mapping_policy_version=FARM_TOTAL_MAPPING_POLICY_VERSION,
            mapping_identity_hash=bundle.mapping_package.mapping_set_sha256,
            source_row_refs=("synthetic:extra",),
        )
        from backend.app.forecast_quality.farm_total_area_authority import (
            build_area_authority_package,
        )

        tampered_area = build_area_authority_package(
            rows=(*bundle.area_package.rows, extra_row),
            source_file_hashes=bundle.area_package.source_file_hashes,
            mapping_policy_version=FARM_TOTAL_MAPPING_POLICY_VERSION,
            mapping_identity_hash=bundle.mapping_package.mapping_set_sha256,
        )
        blocker = validate_mapping_area_authority_binding(
            mapping_package=bundle.mapping_package,
            area_package=tampered_area,
        )
        assert blocker == FarmTotalAuthorityBindingBlocker.AUTHORITY_GROUP_SET_MISMATCH

    def test_source_farm_member_set_mismatch_rejected(self) -> None:
        bundle = build_synthetic_authority_bundle()
        alpha_row = next(
            row for row in bundle.area_package.rows if row.baseline_farm_group_key == "alpha"
        )
        tampered_alpha = build_area_authority_row(
            baseline_farm_group_key=alpha_row.baseline_farm_group_key,
            source_farm_business_keys=("farm-alpha", "farm-tampered"),
            area_mu=alpha_row.area_mu,
            area_authority_class=alpha_row.area_authority_class,
            area_source_season=alpha_row.area_source_season,
            area_source_identity=alpha_row.area_source_identity,
            area_source_hash=alpha_row.area_source_hash,
            mapping_policy_version=alpha_row.mapping_policy_version,
            mapping_identity_hash=alpha_row.mapping_identity_hash,
            source_row_refs=alpha_row.source_row_refs,
        )
        from backend.app.forecast_quality.farm_total_area_authority import (
            build_area_authority_package,
        )

        tampered_area = build_area_authority_package(
            rows=(tampered_alpha, bundle.area_package.rows[1]),
            source_file_hashes=bundle.area_package.source_file_hashes,
            mapping_policy_version=FARM_TOTAL_MAPPING_POLICY_VERSION,
            mapping_identity_hash=bundle.mapping_package.mapping_set_sha256,
        )
        blocker = validate_mapping_area_authority_binding(
            mapping_package=bundle.mapping_package,
            area_package=tampered_area,
        )
        assert blocker == FarmTotalAuthorityBindingBlocker.AUTHORITY_SOURCE_MEMBER_SET_MISMATCH

    def test_materialize_rejects_binding_mismatch(self) -> None:
        bundle = build_synthetic_authority_bundle()
        train_bytes, val_bytes = _valid_train_val_bytes(bundle)
        alpha_row = next(
            row for row in bundle.area_package.rows if row.baseline_farm_group_key == "alpha"
        )
        tampered_alpha = build_area_authority_row(
            baseline_farm_group_key=alpha_row.baseline_farm_group_key,
            source_farm_business_keys=("farm-alpha", "farm-tampered"),
            area_mu=alpha_row.area_mu,
            area_authority_class=alpha_row.area_authority_class,
            area_source_season=alpha_row.area_source_season,
            area_source_identity=alpha_row.area_source_identity,
            area_source_hash=alpha_row.area_source_hash,
            mapping_policy_version=alpha_row.mapping_policy_version,
            mapping_identity_hash=alpha_row.mapping_identity_hash,
            source_row_refs=alpha_row.source_row_refs,
        )
        from backend.app.forecast_quality.farm_total_area_authority import (
            FarmTotalAreaAuthorityPackage,
        )

        tampered_bundle = FarmTotalAuthorityBundle(
            mapping_package=bundle.mapping_package,
            area_package=FarmTotalAreaAuthorityPackage(
                schema_version=bundle.area_package.schema_version,
                policy_version=bundle.area_package.policy_version,
                source_season=bundle.area_package.source_season,
                target_season=bundle.area_package.target_season,
                mapping_policy_version=bundle.area_package.mapping_policy_version,
                source_file_hashes=bundle.area_package.source_file_hashes,
                rows=(tampered_alpha, bundle.area_package.rows[1]),
                area_authority_set_sha256=bundle.area_package.area_authority_set_sha256,
                canonical_hash=bundle.area_package.canonical_hash,
            ),
        )
        blocker, result = materialize_farm_total_baseline_data_plane(
            train_content_bytes=train_bytes,
            validation_content_bytes=val_bytes,
            authority_bundle=tampered_bundle,
            verify_official_hashes=False,
        )
        assert blocker == FarmTotalDatasetBlocker.AUTHORITY_SOURCE_MEMBER_SET_MISMATCH
        assert result is None


class TestDiagnosticAreaSemantics:
    def test_diagnostics_count_each_farm_area_once(self) -> None:
        bundle = build_synthetic_authority_bundle()
        train_bytes, val_bytes = _valid_train_val_bytes(bundle)
        _, result = build_farm_total_data_plane(
            train_content_bytes=train_bytes,
            validation_content_bytes=val_bytes,
            mapping_package=bundle.mapping_package,
            area_package=bundle.area_package,
            verify_official_hashes=False,
        )
        assert result is not None
        train_diag = result.train_dataset.diagnostics
        expected_area = emit_s3_area_mu(Decimal("100.0") + Decimal("200.0"))
        assert train_diag.total_area_mu == expected_area
        assert train_diag.farm_group_count == 2

    def test_audit_union_does_not_double_count_area(self) -> None:
        bundle = build_synthetic_authority_bundle()
        train_bytes, val_bytes = _valid_train_val_bytes(bundle)
        _, result = build_farm_total_data_plane(
            train_content_bytes=train_bytes,
            validation_content_bytes=val_bytes,
            mapping_package=bundle.mapping_package,
            area_package=bundle.area_package,
            verify_official_hashes=False,
        )
        assert result is not None
        audit_diag = result.audit_union_diagnostics
        expected_area = emit_s3_area_mu(Decimal("100.0") + Decimal("200.0"))
        assert audit_diag.total_area_mu == expected_area

    def test_conflicting_area_for_same_farm_fails_closed(self) -> None:
        from backend.app.forecast_quality.farm_total_dataset import FarmTotalDatasetRow

        row_a = FarmTotalDatasetRow(
            season_business_key=SEASON,
            baseline_farm_group_key="alpha",
            harvest_business_date=date(2025, 9, 1),
            partition="TRAIN",
            area_mu=Decimal("100.0"),
            area_authority_class=AREA_AUTHORITY_CLASS_PREVIOUS_SEASON_PROXY,
            actual_harvest_quantity_kg=Decimal("10.0"),
            actual_harvest_kg_per_mu=Decimal("0.1"),
            source_actual_row_count=1,
            source_farm_business_keys=("farm-alpha",),
            area_authority_row_hash="hash-a",
            actual_projection_hash="proj-a",
            row_hash="row-a",
        )
        row_b = FarmTotalDatasetRow(
            season_business_key=SEASON,
            baseline_farm_group_key="alpha",
            harvest_business_date=date(2025, 9, 2),
            partition="TRAIN",
            area_mu=Decimal("200.0"),
            area_authority_class=AREA_AUTHORITY_CLASS_PREVIOUS_SEASON_PROXY,
            actual_harvest_quantity_kg=Decimal("20.0"),
            actual_harvest_kg_per_mu=Decimal("0.1"),
            source_actual_row_count=1,
            source_farm_business_keys=("farm-alpha",),
            area_authority_row_hash="hash-b",
            actual_projection_hash="proj-b",
            row_hash="row-b",
        )
        diag = compute_partition_diagnostics(partition="TRAIN", rows=(row_a, row_b))
        assert diag == FarmTotalDatasetBlocker.AREA_VALUE_CONFLICT


class TestDecimalOnlyPercentile:
    def test_percentile_uses_decimal_only_arithmetic(self) -> None:
        values = [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4")]
        result = _percentile(values, Decimal("0.5"))
        assert isinstance(result, Decimal)
        assert result == Decimal("2.5")

    def test_percentile_implementation_contains_no_float_literals(self) -> None:
        source = inspect.getsource(_percentile)
        tree = ast.parse(source)
        float_nodes = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, float)
        ]
        assert float_nodes == []


class TestAuthorityProvenance:
    def test_real_package_requires_source_workbook_hash(self, tmp_path: Path) -> None:
        review_output = tmp_path / "review.txt"
        review_output.write_text(
            'BASELINE_FARM_GROUP_MAPPING_TABLE=[{"baseline_farm_group":"g1",'
            '"source_farm_business_keys":["f1"],"mapping_relationship_type":"ONE_TO_ONE",'
            '"farm_total_area_mu":"100.0"}]\n',
            encoding="utf-8",
        )
        out_dir = tmp_path / "out"
        result = subprocess.run(
            [
                sys.executable,
                str(GENERATE_SCRIPT),
                "--review-output",
                str(review_output),
                "--out-dir",
                str(out_dir),
            ],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        assert result.returncode != 0
        combined = result.stderr + result.stdout
        assert "prior-area-evidence-path" in combined

    def test_synthetic_generation_allows_missing_workbook_hash(self, tmp_path: Path) -> None:
        review_output = tmp_path / "review.txt"
        review_output.write_text(
            'BASELINE_FARM_GROUP_MAPPING_TABLE=[{"baseline_farm_group":"g1",'
            '"source_farm_business_keys":["f1"],"mapping_relationship_type":"ONE_TO_ONE",'
            '"farm_total_area_mu":"100.0"}]\n',
            encoding="utf-8",
        )
        out_dir = tmp_path / "out"
        result = subprocess.run(
            [
                sys.executable,
                str(GENERATE_SCRIPT),
                "--review-output",
                str(review_output),
                "--out-dir",
                str(out_dir),
                "--allow-synthetic-source-hashes",
            ],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        assert result.returncode != 0
        combined = result.stderr + result.stdout
        assert "eligible group count mismatch" in combined


class TestVerificationScriptCleanup:
    def test_verification_script_disposes_engine_in_finally(self) -> None:
        source = VERIFICATION_SCRIPT.read_text(encoding="utf-8")
        assert "finally:" in source
        assert "dispose_db_engine" in source
        load_fn_start = source.index("async def _load_partitions")
        load_fn_end = source.index("def main", load_fn_start)
        load_fn_source = source[load_fn_start:load_fn_end]
        assert "finally:" in load_fn_source
        finally_pos = load_fn_source.index("finally:")
        dispose_pos = load_fn_source.index("dispose_db_engine")
        assert dispose_pos > finally_pos
