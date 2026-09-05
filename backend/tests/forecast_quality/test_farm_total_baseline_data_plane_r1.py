"""Contract tests for V0.3 Farm-total baseline data plane R1."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from backend.app.forecast_quality.exceptions import S3StructuralDuplicateError
from backend.app.forecast_quality.farm_total_area_authority import (
    FarmTotalAreaAuthorityBlocker,
    FarmTotalAreaAuthorityLoadError,
    area_authority_package_to_payload,
    build_area_authority_row,
    load_area_authority_package,
    validate_area_authority_package_payload,
)
from backend.app.forecast_quality.farm_total_data_plane import (
    FarmTotalAuthorityBundle,
    materialize_farm_total_baseline_data_plane,
)
from backend.app.forecast_quality.farm_total_dataset import (
    FarmTotalDatasetBlocker,
    build_farm_total_data_plane,
    build_partition_dataset,
    compute_partition_dataset_sha256,
    project_partition_to_farm_total_rows,
)
from backend.app.forecast_quality.farm_total_group_mapping import (
    FarmGroupMappingBlocker,
    build_mapping_package,
    build_mapping_row,
    farm_to_baseline_group_lookup,
    load_mapping_package,
    mapping_package_to_payload,
    validate_mapping_package_payload,
)
from backend.app.forecast_quality.farm_total_policy import (
    AREA_AUTHORITY_CLASS_PREVIOUS_SEASON_PROXY,
    FARM_TOTAL_MAPPING_POLICY_VERSION,
    FARM_TOTAL_PRIOR_AREA_SOURCE_SEASON,
)
from backend.app.s2_materialized_dataset.lane_d.canonical import build_partition_bytes
from backend.app.s2_materialized_dataset.shared.contracts import MaterializableRow
from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read import (
    OFFICIAL_TRAIN_CONTENT_SHA256,
    OFFICIAL_VALIDATION_CONTENT_SHA256,
)
from backend.tests.forecast_quality.fixtures.farm_total_synthetic_authority import (
    build_synthetic_authority_bundle,
)

SEASON = "2025~2026"


def _row(
    *,
    farm: str,
    subfarm: str = "sf-1",
    variety: str = "v1",
    harvest_date: date,
    quantity: str,
) -> MaterializableRow:
    return MaterializableRow(
        season=SEASON,
        farm=farm,
        subfarm=subfarm,
        variety=variety,
        harvest_business_date=harvest_date,
        actual_harvest_quantity_kg=Decimal(quantity),
        source_row_identity=f"src-{farm}-{subfarm}-{variety}-{harvest_date.isoformat()}",
        cleaned_row_identity=f"cln-{farm}-{harvest_date.isoformat()}",
        pit_visibility_identity=f"pit-{farm}-{harvest_date.isoformat()}",
        revision_winner_identity=f"rev-{farm}-{harvest_date.isoformat()}",
    )


def _bundle_rows(bundle: FarmTotalAuthorityBundle) -> tuple[MaterializableRow, ...]:
    return (
        _row(
            farm="farm-alpha",
            harvest_date=date(2025, 9, 1),
            quantity="10.0",
        ),
        _row(
            farm="farm-beta-a",
            subfarm="sf-a",
            harvest_date=date(2025, 9, 2),
            quantity="20.0",
        ),
        _row(
            farm="farm-beta-b",
            subfarm="sf-b",
            variety="v2",
            harvest_date=date(2025, 9, 2),
            quantity="30.0",
        ),
        _row(
            farm="farm-beta-a",
            subfarm="sf-a",
            harvest_date=date(2026, 2, 1),
            quantity="5.0",
        ),
        _row(
            farm="farm-conflict",
            harvest_date=date(2025, 9, 3),
            quantity="999.0",
        ),
    )


class TestFarmTotalMappingAuthority:
    def test_many_source_farms_map_to_one_group(self) -> None:
        bundle = build_synthetic_authority_bundle()
        lookup = farm_to_baseline_group_lookup(bundle.mapping_package)
        assert lookup["farm-beta-a"] == "beta"
        assert lookup["farm-beta-b"] == "beta"

    def test_one_to_one_group_mapping(self) -> None:
        bundle = build_synthetic_authority_bundle()
        lookup = farm_to_baseline_group_lookup(bundle.mapping_package)
        assert lookup["farm-alpha"] == "alpha"

    def test_source_farm_cannot_map_twice(self) -> None:
        rows = (
            build_mapping_row(
                baseline_farm_group_key="g1",
                source_farm_business_keys=("dup-farm",),
                mapping_relationship_type="ONE_TO_ONE",
                exclusion_status="ELIGIBLE",
                exclusion_reason=None,
            ),
            build_mapping_row(
                baseline_farm_group_key="g2",
                source_farm_business_keys=("dup-farm",),
                mapping_relationship_type="ONE_TO_ONE",
                exclusion_status="ELIGIBLE",
                exclusion_reason=None,
            ),
        )
        package = build_mapping_package(rows=rows)
        payload = mapping_package_to_payload(package)
        blocker, _ = validate_mapping_package_payload(payload)
        assert blocker == FarmGroupMappingBlocker.DUPLICATE_SOURCE_FARM_KEY

    def test_conflict_group_excluded(self) -> None:
        bundle = build_synthetic_authority_bundle()
        lookup = farm_to_baseline_group_lookup(bundle.mapping_package)
        assert "farm-conflict" not in lookup
        excluded = [
            row for row in bundle.mapping_package.rows if row.baseline_farm_group_key == "新哨"
        ]
        assert len(excluded) == 1
        assert excluded[0].exclusion_status == "EXCLUDED_CONFLICT"


class TestFarmTotalProjection:
    def test_variety_rows_aggregate_to_farm_total(self) -> None:
        bundle = build_synthetic_authority_bundle()
        train_rows = tuple(r for r in _bundle_rows(bundle) if r.harvest_business_date.year == 2025)
        projected, _, _ = project_partition_to_farm_total_rows(
            partition="TRAIN",
            source_rows=train_rows,
            mapping_package=bundle.mapping_package,
            area_package=bundle.area_package,
        )
        beta_rows = [r for r in projected if r.baseline_farm_group_key == "beta"]
        assert len(beta_rows) == 1
        assert beta_rows[0].actual_harvest_quantity_kg == Decimal("50.0")
        assert beta_rows[0].source_actual_row_count == 2

    def test_subfarm_rows_aggregate_to_farm_total(self) -> None:
        bundle = build_synthetic_authority_bundle()
        train_rows = tuple(r for r in _bundle_rows(bundle) if r.harvest_business_date.year == 2025)
        projected, _, _ = project_partition_to_farm_total_rows(
            partition="TRAIN",
            source_rows=train_rows,
            mapping_package=bundle.mapping_package,
            area_package=bundle.area_package,
        )
        alpha_rows = [r for r in projected if r.baseline_farm_group_key == "alpha"]
        assert len(alpha_rows) == 1
        assert alpha_rows[0].actual_harvest_quantity_kg == Decimal("10.0")

    def test_conflict_farm_excluded_from_projection(self) -> None:
        bundle = build_synthetic_authority_bundle()
        train_rows = tuple(r for r in _bundle_rows(bundle) if r.harvest_business_date.year == 2025)
        projected, _, _ = project_partition_to_farm_total_rows(
            partition="TRAIN",
            source_rows=train_rows,
            mapping_package=bundle.mapping_package,
            area_package=bundle.area_package,
        )
        assert all(r.baseline_farm_group_key != "新哨" for r in projected)

    def test_area_not_duplicated_by_member_count(self) -> None:
        bundle = build_synthetic_authority_bundle()
        train_rows = tuple(r for r in _bundle_rows(bundle) if r.harvest_business_date.year == 2025)
        projected, _, _ = project_partition_to_farm_total_rows(
            partition="TRAIN",
            source_rows=train_rows,
            mapping_package=bundle.mapping_package,
            area_package=bundle.area_package,
        )
        beta_row = next(r for r in projected if r.baseline_farm_group_key == "beta")
        assert beta_row.area_mu == Decimal("200.0")
        assert beta_row.actual_harvest_kg_per_mu == Decimal("50.0") / Decimal("200.0")

    def test_actual_row_cannot_count_twice(self) -> None:
        bundle = build_synthetic_authority_bundle()
        duplicate = _row(
            farm="farm-alpha",
            harvest_date=date(2025, 9, 1),
            quantity="10.0",
        )
        duplicate = MaterializableRow(
            season=duplicate.season,
            farm=duplicate.farm,
            subfarm=duplicate.subfarm,
            variety=duplicate.variety,
            harvest_business_date=duplicate.harvest_business_date,
            actual_harvest_quantity_kg=duplicate.actual_harvest_quantity_kg,
            source_row_identity=duplicate.source_row_identity,
            cleaned_row_identity="different-cleaned",
            pit_visibility_identity=duplicate.pit_visibility_identity,
            revision_winner_identity=duplicate.revision_winner_identity,
        )
        with pytest.raises(S3StructuralDuplicateError):
            project_partition_to_farm_total_rows(
                partition="TRAIN",
                source_rows=(duplicate, duplicate),
                mapping_package=bundle.mapping_package,
                area_package=bundle.area_package,
            )

    def test_train_validation_remain_separated(self) -> None:
        bundle = build_synthetic_authority_bundle()
        all_rows = _bundle_rows(bundle)
        train_bytes = build_partition_bytes(
            tuple(r for r in all_rows if r.harvest_business_date.year == 2025)
        )
        val_bytes = build_partition_bytes(
            tuple(r for r in all_rows if r.harvest_business_date.year == 2026)
        )
        blocker, result = build_farm_total_data_plane(
            train_content_bytes=train_bytes,
            validation_content_bytes=val_bytes,
            mapping_package=bundle.mapping_package,
            area_package=bundle.area_package,
            verify_official_hashes=False,
        )
        assert blocker == FarmTotalDatasetBlocker.NONE
        assert result is not None
        assert result.train_dataset.partition_dataset.partition == "TRAIN"
        assert result.validation_dataset.partition_dataset.partition == "VALIDATION"
        assert len(result.train_dataset.partition_dataset.rows) == 2
        assert len(result.validation_dataset.partition_dataset.rows) == 1

    def test_validation_never_contributes_to_training_features(self) -> None:
        bundle = build_synthetic_authority_bundle()
        all_rows = _bundle_rows(bundle)
        train_bytes = build_partition_bytes(
            tuple(r for r in all_rows if r.harvest_business_date.year == 2025)
        )
        val_bytes = build_partition_bytes(
            tuple(r for r in all_rows if r.harvest_business_date.year == 2026)
        )
        _, result = build_farm_total_data_plane(
            train_content_bytes=train_bytes,
            validation_content_bytes=val_bytes,
            mapping_package=bundle.mapping_package,
            area_package=bundle.area_package,
            verify_official_hashes=False,
        )
        assert result is not None
        assert result.validation_used_as_training_input is False
        train_groups = {
            r.baseline_farm_group_key for r in result.train_dataset.partition_dataset.rows
        }
        assert "beta" in train_groups
        val_groups = {
            r.baseline_farm_group_key for r in result.validation_dataset.partition_dataset.rows
        }
        assert val_groups == {"beta"}

    def test_previous_season_proxy_label_retained(self) -> None:
        bundle = build_synthetic_authority_bundle()
        assert all(
            row.area_authority_class == AREA_AUTHORITY_CLASS_PREVIOUS_SEASON_PROXY
            for row in bundle.area_package.rows
        )


class TestFarmTotalAuthorityValidation:
    def test_zero_or_negative_area_rejected(self) -> None:
        bundle = build_synthetic_authority_bundle()
        with pytest.raises(FarmTotalAreaAuthorityLoadError):
            build_area_authority_row(
                baseline_farm_group_key="bad",
                source_farm_business_keys=("farm-bad",),
                area_mu=Decimal("0"),
                area_authority_class=AREA_AUTHORITY_CLASS_PREVIOUS_SEASON_PROXY,
                area_source_season=FARM_TOTAL_PRIOR_AREA_SOURCE_SEASON,
                area_source_identity="x",
                area_source_hash="d" * 64,
                mapping_policy_version=FARM_TOTAL_MAPPING_POLICY_VERSION,
                mapping_identity_hash=bundle.mapping_package.mapping_set_sha256,
                source_row_refs=("x",),
            )

    def test_native_float_rejected_in_area_package(self) -> None:
        bundle = build_synthetic_authority_bundle()
        payload = area_authority_package_to_payload(bundle.area_package)
        payload["rows"][0]["area_mu"] = 100.0
        blocker, _ = validate_area_authority_package_payload(payload)
        assert blocker == FarmTotalAreaAuthorityBlocker.NATIVE_FLOAT_REJECTED

    def test_input_order_independence(self) -> None:
        rows_a = (
            build_mapping_row(
                baseline_farm_group_key="zulu",
                source_farm_business_keys=("farm-z",),
                mapping_relationship_type="ONE_TO_ONE",
                exclusion_status="ELIGIBLE",
                exclusion_reason=None,
            ),
            build_mapping_row(
                baseline_farm_group_key="alpha",
                source_farm_business_keys=("farm-a",),
                mapping_relationship_type="ONE_TO_ONE",
                exclusion_status="ELIGIBLE",
                exclusion_reason=None,
            ),
        )
        rows_b = (rows_a[1], rows_a[0])
        pkg_a = build_mapping_package(rows=rows_a)
        pkg_b = build_mapping_package(rows=rows_b)
        assert pkg_a.mapping_set_sha256 == pkg_b.mapping_set_sha256
        assert pkg_a.canonical_hash == pkg_b.canonical_hash

    def test_canonical_hash_replay_equality(self) -> None:
        bundle = build_synthetic_authority_bundle()
        mapping_payload = mapping_package_to_payload(bundle.mapping_package)
        reloaded_mapping = load_mapping_package(mapping_payload)
        assert reloaded_mapping.canonical_hash == bundle.mapping_package.canonical_hash
        area_payload = area_authority_package_to_payload(bundle.area_package)
        reloaded_area = load_area_authority_package(area_payload)
        assert reloaded_area.canonical_hash == bundle.area_package.canonical_hash

    def test_source_content_hash_mismatch_fails_closed(self) -> None:
        bundle = build_synthetic_authority_bundle()
        tampered = b"tampered-partition-bytes\n"
        blocker, dataset = build_partition_dataset(
            partition="TRAIN",
            content_bytes=tampered,
            mapping_package=bundle.mapping_package,
            area_package=bundle.area_package,
            verify_official_hashes=True,
        )
        assert blocker == FarmTotalDatasetBlocker.OFFICIAL_HASH_MISMATCH
        assert dataset is None

    def test_dataset_hash_replay(self) -> None:
        bundle = build_synthetic_authority_bundle()
        train_bytes = build_partition_bytes(
            tuple(r for r in _bundle_rows(bundle) if r.harvest_business_date.year == 2025)
        )
        _, dataset = build_partition_dataset(
            partition="TRAIN",
            content_bytes=train_bytes,
            mapping_package=bundle.mapping_package,
            area_package=bundle.area_package,
            verify_official_hashes=False,
        )
        assert dataset is not None
        replay = compute_partition_dataset_sha256(dataset.rows)
        assert replay == dataset.dataset_sha256


class TestFarmTotalDataPlaneIntegration:
    def test_materialize_entrypoint(self) -> None:
        bundle = build_synthetic_authority_bundle()
        all_rows = _bundle_rows(bundle)
        train_bytes = build_partition_bytes(
            tuple(r for r in all_rows if r.harvest_business_date.year == 2025)
        )
        val_bytes = build_partition_bytes(
            tuple(r for r in all_rows if r.harvest_business_date.year == 2026)
        )
        blocker, result = materialize_farm_total_baseline_data_plane(
            train_content_bytes=train_bytes,
            validation_content_bytes=val_bytes,
            authority_bundle=bundle,
            verify_official_hashes=False,
        )
        assert blocker == FarmTotalDatasetBlocker.NONE
        assert result is not None
        assert result.mapping_set_sha256 == bundle.mapping_package.mapping_set_sha256
        assert result.area_authority_set_sha256 == bundle.area_package.area_authority_set_sha256

    def test_official_hash_constants_frozen(self) -> None:
        assert len(OFFICIAL_TRAIN_CONTENT_SHA256) == 64
        assert len(OFFICIAL_VALIDATION_CONTENT_SHA256) == 64

    def test_test_partition_rejected_by_policy(self) -> None:
        bundle = build_synthetic_authority_bundle()
        test_row = _row(
            farm="farm-alpha",
            harvest_date=date(2026, 3, 15),
            quantity="1.0",
        )
        test_bytes = build_partition_bytes((test_row,))
        blocker, dataset = build_partition_dataset(
            partition="TRAIN",
            content_bytes=test_bytes,
            mapping_package=bundle.mapping_package,
            area_package=bundle.area_package,
            verify_official_hashes=False,
        )
        assert blocker == FarmTotalDatasetBlocker.NONE
        assert dataset is not None
        assert len(dataset.rows) == 0
