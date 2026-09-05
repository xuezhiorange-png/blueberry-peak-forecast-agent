"""V0.3 Farm-total baseline data plane orchestrator."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.app.forecast_quality.farm_total_area_authority import (
    FarmTotalAreaAuthorityPackage,
    area_authority_package_to_payload,
    load_area_authority_package,
)
from backend.app.forecast_quality.farm_total_dataset import (
    FarmTotalDataPlaneResult,
    FarmTotalDatasetBlocker,
    build_farm_total_data_plane,
)
from backend.app.forecast_quality.farm_total_group_mapping import (
    FarmGroupMappingPackage,
    load_mapping_package,
    mapping_package_to_payload,
)
from backend.app.forecast_quality.farm_total_policy import (
    FARM_TOTAL_TARGET_SEASON,
    V0_3_BASELINE_ENTITY,
    V0_3_BASELINE_TARGET,
)


@dataclass(frozen=True, slots=True)
class FarmTotalAuthorityBundle:
    mapping_package: FarmGroupMappingPackage
    area_package: FarmTotalAreaAuthorityPackage


def load_authority_bundle_from_paths(
    *,
    mapping_package_path: Path,
    area_authority_package_path: Path,
) -> FarmTotalAuthorityBundle:
    mapping_payload = json.loads(mapping_package_path.read_text(encoding="utf-8"))
    area_payload = json.loads(area_authority_package_path.read_text(encoding="utf-8"))
    return FarmTotalAuthorityBundle(
        mapping_package=load_mapping_package(mapping_payload),
        area_package=load_area_authority_package(area_payload),
    )


def load_authority_bundle_from_payloads(
    *,
    mapping_payload: dict[str, Any],
    area_payload: dict[str, Any],
) -> FarmTotalAuthorityBundle:
    return FarmTotalAuthorityBundle(
        mapping_package=load_mapping_package(mapping_payload),
        area_package=load_area_authority_package(area_payload),
    )


def materialize_farm_total_baseline_data_plane(
    *,
    train_content_bytes: bytes,
    validation_content_bytes: bytes,
    authority_bundle: FarmTotalAuthorityBundle,
    verify_official_hashes: bool = True,
) -> tuple[FarmTotalDatasetBlocker, FarmTotalDataPlaneResult | None]:
    """Build TRAIN and VALIDATION Farm-total datasets from accepted SOURCE-002 bytes."""

    if authority_bundle.mapping_package.target_season != FARM_TOTAL_TARGET_SEASON:
        return FarmTotalDatasetBlocker.OFFICIAL_HASH_MISMATCH, None

    return build_farm_total_data_plane(
        train_content_bytes=train_content_bytes,
        validation_content_bytes=validation_content_bytes,
        mapping_package=authority_bundle.mapping_package,
        area_package=authority_bundle.area_package,
        verify_official_hashes=verify_official_hashes,
    )


def authority_bundle_payloads(
    bundle: FarmTotalAuthorityBundle,
) -> tuple[dict[str, Any], dict[str, Any]]:
    return (
        mapping_package_to_payload(bundle.mapping_package),
        area_authority_package_to_payload(bundle.area_package),
    )


__all__ = [
    "FarmTotalAuthorityBundle",
    "FarmTotalDataPlaneResult",
    "FarmTotalDatasetBlocker",
    "V0_3_BASELINE_ENTITY",
    "V0_3_BASELINE_TARGET",
    "authority_bundle_payloads",
    "load_authority_bundle_from_paths",
    "load_authority_bundle_from_payloads",
    "materialize_farm_total_baseline_data_plane",
]
