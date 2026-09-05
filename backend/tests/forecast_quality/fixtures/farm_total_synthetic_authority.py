"""Synthetic authority fixtures for Farm-total baseline data plane tests."""

from __future__ import annotations

from decimal import Decimal

from backend.app.forecast_quality.farm_total_area_authority import (
    build_area_authority_package,
    build_area_authority_row,
)
from backend.app.forecast_quality.farm_total_data_plane import FarmTotalAuthorityBundle
from backend.app.forecast_quality.farm_total_group_mapping import (
    build_mapping_package,
    build_mapping_row,
)
from backend.app.forecast_quality.farm_total_policy import (
    AREA_AUTHORITY_CLASS_PREVIOUS_SEASON_PROXY,
    EXCLUSION_REASON_TEMPORAL_CONFLICT,
    FARM_TOTAL_MAPPING_POLICY_VERSION,
    FARM_TOTAL_PRIOR_AREA_SOURCE_SEASON,
)


def build_synthetic_authority_bundle() -> FarmTotalAuthorityBundle:
    """Minimal 3-group bundle: one-to-one, many-to-one, and one excluded conflict."""

    mapping_rows = (
        build_mapping_row(
            baseline_farm_group_key="alpha",
            source_farm_business_keys=("farm-alpha",),
            mapping_relationship_type="ONE_TO_ONE",
            exclusion_status="ELIGIBLE",
            exclusion_reason=None,
        ),
        build_mapping_row(
            baseline_farm_group_key="beta",
            source_farm_business_keys=("farm-beta-a", "farm-beta-b"),
            mapping_relationship_type="MANY_SOURCE_FARMS_TO_ONE_BASELINE_FARM",
            exclusion_status="ELIGIBLE",
            exclusion_reason=None,
        ),
        build_mapping_row(
            baseline_farm_group_key="新哨",
            source_farm_business_keys=("farm-conflict",),
            mapping_relationship_type="ONE_TO_ONE",
            exclusion_status="EXCLUDED_CONFLICT",
            exclusion_reason=EXCLUSION_REASON_TEMPORAL_CONFLICT,
        ),
    )
    mapping_package = build_mapping_package(rows=mapping_rows)

    area_rows = (
        build_area_authority_row(
            baseline_farm_group_key="alpha",
            source_farm_business_keys=("farm-alpha",),
            area_mu=Decimal("100.0"),
            area_authority_class=AREA_AUTHORITY_CLASS_PREVIOUS_SEASON_PROXY,
            area_source_season=FARM_TOTAL_PRIOR_AREA_SOURCE_SEASON,
            area_source_identity="synthetic-prior-area",
            area_source_hash="a" * 64,
            mapping_policy_version=FARM_TOTAL_MAPPING_POLICY_VERSION,
            mapping_identity_hash=mapping_package.mapping_set_sha256,
            source_row_refs=("synthetic:alpha",),
        ),
        build_area_authority_row(
            baseline_farm_group_key="beta",
            source_farm_business_keys=("farm-beta-a", "farm-beta-b"),
            area_mu=Decimal("200.0"),
            area_authority_class=AREA_AUTHORITY_CLASS_PREVIOUS_SEASON_PROXY,
            area_source_season=FARM_TOTAL_PRIOR_AREA_SOURCE_SEASON,
            area_source_identity="synthetic-prior-area",
            area_source_hash="b" * 64,
            mapping_policy_version=FARM_TOTAL_MAPPING_POLICY_VERSION,
            mapping_identity_hash=mapping_package.mapping_set_sha256,
            source_row_refs=("synthetic:beta",),
        ),
    )
    area_package = build_area_authority_package(
        rows=area_rows,
        source_file_hashes=(("synthetic_fixture", "c" * 64),),
        mapping_policy_version=FARM_TOTAL_MAPPING_POLICY_VERSION,
        mapping_identity_hash=mapping_package.mapping_set_sha256,
    )
    return FarmTotalAuthorityBundle(
        mapping_package=mapping_package,
        area_package=area_package,
    )
