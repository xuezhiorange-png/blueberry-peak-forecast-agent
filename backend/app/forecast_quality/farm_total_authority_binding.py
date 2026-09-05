"""Cross-package mapping ↔ area authority binding validation."""

from __future__ import annotations

from enum import StrEnum

from backend.app.forecast_quality.farm_total_area_authority import FarmTotalAreaAuthorityPackage
from backend.app.forecast_quality.farm_total_group_mapping import (
    FarmGroupMappingPackage,
    eligible_mapping_rows,
)


class FarmTotalAuthorityBindingBlocker(StrEnum):
    NONE = "NONE"
    AUTHORITY_GROUP_SET_MISMATCH = "AUTHORITY_GROUP_SET_MISMATCH"
    AUTHORITY_SOURCE_MEMBER_SET_MISMATCH = "AUTHORITY_SOURCE_MEMBER_SET_MISMATCH"
    MAPPING_IDENTITY_HASH_MISMATCH = "MAPPING_IDENTITY_HASH_MISMATCH"
    AUTHORITY_SEASON_MISMATCH = "AUTHORITY_SEASON_MISMATCH"
    MAPPING_POLICY_VERSION_MISMATCH = "MAPPING_POLICY_VERSION_MISMATCH"


def validate_mapping_area_authority_binding(
    *,
    mapping_package: FarmGroupMappingPackage,
    area_package: FarmTotalAreaAuthorityPackage,
) -> FarmTotalAuthorityBindingBlocker:
    if mapping_package.mapping_policy_version != area_package.mapping_policy_version:
        return FarmTotalAuthorityBindingBlocker.MAPPING_POLICY_VERSION_MISMATCH
    if mapping_package.target_season != area_package.target_season:
        return FarmTotalAuthorityBindingBlocker.AUTHORITY_SEASON_MISMATCH

    eligible_mapping = {
        row.baseline_farm_group_key: row for row in eligible_mapping_rows(mapping_package)
    }
    area_by_group = {row.baseline_farm_group_key: row for row in area_package.rows}

    if set(eligible_mapping) != set(area_by_group):
        return FarmTotalAuthorityBindingBlocker.AUTHORITY_GROUP_SET_MISMATCH

    expected_mapping_hash = mapping_package.mapping_set_sha256
    mapping_hashes = {row.mapping_identity_hash for row in area_package.rows}
    if len(mapping_hashes) != 1:
        return FarmTotalAuthorityBindingBlocker.MAPPING_IDENTITY_HASH_MISMATCH
    mapping_identity_hash = next(iter(mapping_hashes))
    if not mapping_identity_hash or mapping_identity_hash != expected_mapping_hash:
        return FarmTotalAuthorityBindingBlocker.MAPPING_IDENTITY_HASH_MISMATCH

    for group_key, mapping_row in eligible_mapping.items():
        area_row = area_by_group[group_key]
        if tuple(mapping_row.source_farm_business_keys) != area_row.source_farm_business_keys:
            return FarmTotalAuthorityBindingBlocker.AUTHORITY_SOURCE_MEMBER_SET_MISMATCH
        if area_row.mapping_identity_hash != expected_mapping_hash:
            return FarmTotalAuthorityBindingBlocker.MAPPING_IDENTITY_HASH_MISMATCH

    return FarmTotalAuthorityBindingBlocker.NONE
