"""Farm-total modeling dataset projection (V0.3 S3 data plane)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from backend.app.forecast_quality.canonical import (
    canonical_json_bytes,
    emit_s3_area_mu,
    emit_s3_decimal,
)
from backend.app.forecast_quality.exceptions import (
    S3ContractInvariantViolationError,
    S3StructuralDuplicateError,
)
from backend.app.forecast_quality.farm_total_area_authority import (
    FarmTotalAreaAuthorityPackage,
    area_by_baseline_group,
)
from backend.app.forecast_quality.farm_total_group_mapping import (
    FarmGroupMappingPackage,
    farm_to_baseline_group_lookup,
)
from backend.app.forecast_quality.farm_total_policy import FARM_TOTAL_DATASET_SCHEMA_VERSION
from backend.app.s2_materialized_dataset.lane_d.canonical import (
    MalformedPartitionBytesError,
    parse_partition_bytes,
)
from backend.app.s2_materialized_dataset.lane_d.hashing import content_sha256
from backend.app.s2_materialized_dataset.lane_d.partitions import (
    TRAIN_END,
    TRAIN_START,
    VALIDATION_END,
    VALIDATION_START,
)
from backend.app.s2_materialized_dataset.shared.contracts import MaterializableRow
from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read import (
    OFFICIAL_TRAIN_CONTENT_SHA256,
    OFFICIAL_TRAIN_ROW_COUNT,
    OFFICIAL_VALIDATION_CONTENT_SHA256,
    OFFICIAL_VALIDATION_ROW_COUNT,
)

PartitionLabel = Literal["TRAIN", "VALIDATION"]


class FarmTotalDatasetBlocker(StrEnum):
    NONE = "NONE"
    TEST_PARTITION_FORBIDDEN = "TEST_PARTITION_FORBIDDEN"
    OFFICIAL_HASH_MISMATCH = "OFFICIAL_HASH_MISMATCH"
    OFFICIAL_COUNT_MISMATCH = "OFFICIAL_COUNT_MISMATCH"
    MALFORMED_PARTITION_BYTES = "MALFORMED_PARTITION_BYTES"
    UNMAPPED_SOURCE_FARM = "UNMAPPED_SOURCE_FARM"
    DUPLICATE_SOURCE_ROW = "DUPLICATE_SOURCE_ROW"
    AREA_NOT_BOUND = "AREA_NOT_BOUND"
    NON_POSITIVE_AREA = "NON_POSITIVE_AREA"


@dataclass(frozen=True, slots=True)
class FarmTotalDatasetRow:
    season_business_key: str
    baseline_farm_group_key: str
    harvest_business_date: date
    partition: PartitionLabel
    area_mu: Decimal
    area_authority_class: str
    actual_harvest_quantity_kg: Decimal
    actual_harvest_kg_per_mu: Decimal
    source_actual_row_count: int
    source_farm_business_keys: tuple[str, ...]
    area_authority_row_hash: str
    actual_projection_hash: str
    row_hash: str


@dataclass(frozen=True, slots=True)
class FarmTotalPartitionDataset:
    partition: PartitionLabel
    schema_version: str
    rows: tuple[FarmTotalDatasetRow, ...]
    dataset_sha256: str


@dataclass(frozen=True, slots=True)
class FarmTotalDatasetDiagnostics:
    partition: PartitionLabel | Literal["TRAIN_PLUS_VALIDATION_AUDIT"]
    farm_group_count: int
    date_count: int
    row_count: int
    total_area_mu: str
    total_actual_harvest_kg: str
    kg_per_mu_min: str | None
    kg_per_mu_p25: str | None
    kg_per_mu_median: str | None
    kg_per_mu_p75: str | None
    kg_per_mu_max: str | None


@dataclass(frozen=True, slots=True)
class FarmTotalTrainingDataset:
    partition_dataset: FarmTotalPartitionDataset
    diagnostics: FarmTotalDatasetDiagnostics


@dataclass(frozen=True, slots=True)
class FarmTotalValidationDataset:
    partition_dataset: FarmTotalPartitionDataset
    diagnostics: FarmTotalDatasetDiagnostics


@dataclass(frozen=True, slots=True)
class FarmTotalDataPlaneResult:
    train_dataset: FarmTotalTrainingDataset
    validation_dataset: FarmTotalValidationDataset
    audit_union_diagnostics: FarmTotalDatasetDiagnostics
    mapping_set_sha256: str
    area_authority_set_sha256: str
    area_double_count_count: int
    source_farm_double_map_count: int
    source_actual_double_count: int
    validation_used_as_training_input: bool


def partition_for_harvest_date(harvest_business_date: date) -> PartitionLabel | None:
    if TRAIN_START <= harvest_business_date <= TRAIN_END:
        return "TRAIN"
    if VALIDATION_START <= harvest_business_date <= VALIDATION_END:
        return "VALIDATION"
    return None


def _assert_official_partition_bytes(
    *,
    partition: PartitionLabel,
    content_bytes: bytes,
) -> FarmTotalDatasetBlocker | None:
    digest = content_sha256(content_bytes)
    if partition == "TRAIN":
        if digest != OFFICIAL_TRAIN_CONTENT_SHA256:
            return FarmTotalDatasetBlocker.OFFICIAL_HASH_MISMATCH
        row_count = len(parse_partition_bytes(content_bytes))
        if row_count != OFFICIAL_TRAIN_ROW_COUNT:
            return FarmTotalDatasetBlocker.OFFICIAL_COUNT_MISMATCH
    else:
        if digest != OFFICIAL_VALIDATION_CONTENT_SHA256:
            return FarmTotalDatasetBlocker.OFFICIAL_HASH_MISMATCH
        row_count = len(parse_partition_bytes(content_bytes))
        if row_count != OFFICIAL_VALIDATION_ROW_COUNT:
            return FarmTotalDatasetBlocker.OFFICIAL_COUNT_MISMATCH
    return None


def _aggregate_key(
    row: MaterializableRow,
    baseline_group: str,
) -> tuple[str, str, date]:
    return (row.season, baseline_group, row.harvest_business_date)


def _projection_bucket(
    *,
    season: str,
    baseline_group: str,
    harvest_date: date,
    partition: PartitionLabel,
    area_row_hash: str,
    area_mu: Decimal,
    area_authority_class: str,
    source_farm_keys: set[str],
    source_row_ids: list[str],
    total_kg: Decimal,
) -> dict[str, Any]:
    actual_projection_preimage = {
        "season_business_key": season,
        "baseline_farm_group_key": baseline_group,
        "harvest_business_date": harvest_date.isoformat(),
        "partition": partition,
        "source_actual_row_ids": sorted(source_row_ids),
        "source_farm_business_keys": sorted(source_farm_keys),
        "actual_harvest_quantity_kg": emit_s3_decimal(total_kg),
        "actual_projection_hash": "",
    }
    actual_projection_hash = hashlib.sha256(
        canonical_json_bytes(actual_projection_preimage)
    ).hexdigest()
    kg_per_mu = total_kg / area_mu
    row_preimage = {
        "season_business_key": season,
        "baseline_farm_group_key": baseline_group,
        "harvest_business_date": harvest_date.isoformat(),
        "partition": partition,
        "area_mu": emit_s3_area_mu(area_mu),
        "area_authority_class": area_authority_class,
        "actual_harvest_quantity_kg": emit_s3_decimal(total_kg),
        "actual_harvest_kg_per_mu": emit_s3_decimal(kg_per_mu),
        "source_actual_row_count": len(source_row_ids),
        "source_farm_business_keys": sorted(source_farm_keys),
        "area_authority_row_hash": area_row_hash,
        "actual_projection_hash": actual_projection_hash,
        "row_hash": "",
    }
    row_hash = hashlib.sha256(canonical_json_bytes(row_preimage)).hexdigest()
    return {
        "row": FarmTotalDatasetRow(
            season_business_key=season,
            baseline_farm_group_key=baseline_group,
            harvest_business_date=harvest_date,
            partition=partition,
            area_mu=area_mu,
            area_authority_class=area_authority_class,
            actual_harvest_quantity_kg=total_kg,
            actual_harvest_kg_per_mu=kg_per_mu,
            source_actual_row_count=len(source_row_ids),
            source_farm_business_keys=tuple(sorted(source_farm_keys)),
            area_authority_row_hash=area_row_hash,
            actual_projection_hash=actual_projection_hash,
            row_hash=row_hash,
        ),
        "row_hash": row_hash,
    }


def project_partition_to_farm_total_rows(
    *,
    partition: PartitionLabel,
    source_rows: tuple[MaterializableRow, ...],
    mapping_package: FarmGroupMappingPackage,
    area_package: FarmTotalAreaAuthorityPackage,
) -> tuple[tuple[FarmTotalDatasetRow, ...], int, int]:
    farm_lookup = farm_to_baseline_group_lookup(mapping_package)
    area_lookup = area_by_baseline_group(area_package)

    buckets: dict[tuple[str, str, date], dict[str, Any]] = {}
    seen_source_rows: set[str] = set()
    source_farm_assignments: dict[str, str] = {}
    source_actual_double_count = 0

    for row in source_rows:
        assigned_partition = partition_for_harvest_date(row.harvest_business_date)
        if assigned_partition != partition:
            continue
        if row.source_row_identity in seen_source_rows:
            source_actual_double_count += 1
            raise S3StructuralDuplicateError(
                f"duplicate source row identity {row.source_row_identity}"
            )
        seen_source_rows.add(row.source_row_identity)

        baseline_group = farm_lookup.get(row.farm)
        if baseline_group is None:
            continue

        if row.farm in source_farm_assignments:
            if source_farm_assignments[row.farm] != baseline_group:
                raise S3StructuralDuplicateError(f"source farm {row.farm} maps to multiple groups")
        else:
            source_farm_assignments[row.farm] = baseline_group

        area_row = area_lookup.get(baseline_group)
        if area_row is None:
            raise S3ContractInvariantViolationError(
                f"missing area authority for eligible group {baseline_group}"
            )

        key = _aggregate_key(row, baseline_group)
        bucket = buckets.setdefault(
            key,
            {
                "season": row.season,
                "baseline_group": baseline_group,
                "harvest_date": row.harvest_business_date,
                "partition": partition,
                "area_mu": area_row.area_mu,
                "area_authority_class": area_row.area_authority_class,
                "area_row_hash": area_row.row_hash,
                "source_farm_keys": set(),
                "source_row_ids": [],
                "total_kg": Decimal("0"),
            },
        )
        bucket["source_farm_keys"].add(row.farm)
        bucket["source_row_ids"].append(row.source_row_identity)
        bucket["total_kg"] += row.actual_harvest_quantity_kg

    built_rows: list[FarmTotalDatasetRow] = []
    for bucket in buckets.values():
        built = _projection_bucket(
            season=bucket["season"],
            baseline_group=bucket["baseline_group"],
            harvest_date=bucket["harvest_date"],
            partition=partition,
            area_row_hash=bucket["area_row_hash"],
            area_mu=bucket["area_mu"],
            area_authority_class=bucket["area_authority_class"],
            source_farm_keys=bucket["source_farm_keys"],
            source_row_ids=bucket["source_row_ids"],
            total_kg=bucket["total_kg"],
        )
        built_rows.append(built["row"])

    ordered = tuple(
        sorted(
            built_rows,
            key=lambda r: (
                r.season_business_key,
                r.baseline_farm_group_key,
                r.harvest_business_date.isoformat(),
            ),
        )
    )
    return ordered, 0, source_actual_double_count


def compute_partition_dataset_sha256(rows: tuple[FarmTotalDatasetRow, ...]) -> str:
    payload = [
        {
            "season_business_key": row.season_business_key,
            "baseline_farm_group_key": row.baseline_farm_group_key,
            "harvest_business_date": row.harvest_business_date.isoformat(),
            "partition": row.partition,
            "area_mu": emit_s3_area_mu(row.area_mu),
            "area_authority_class": row.area_authority_class,
            "actual_harvest_quantity_kg": emit_s3_decimal(row.actual_harvest_quantity_kg),
            "actual_harvest_kg_per_mu": emit_s3_decimal(row.actual_harvest_kg_per_mu),
            "source_actual_row_count": row.source_actual_row_count,
            "source_farm_business_keys": list(row.source_farm_business_keys),
            "area_authority_row_hash": row.area_authority_row_hash,
            "actual_projection_hash": row.actual_projection_hash,
            "row_hash": row.row_hash,
        }
        for row in rows
    ]
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _percentile(sorted_values: list[Decimal], p: float) -> Decimal | None:
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (len(sorted_values) - 1) * p
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return sorted_values[f]
    return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * Decimal(str(k - f))


def compute_partition_diagnostics(
    *,
    partition: PartitionLabel | Literal["TRAIN_PLUS_VALIDATION_AUDIT"],
    rows: tuple[FarmTotalDatasetRow, ...],
) -> FarmTotalDatasetDiagnostics:
    groups = {row.baseline_farm_group_key for row in rows}
    dates = {row.harvest_business_date for row in rows}
    total_area = sum((row.area_mu for row in rows), Decimal("0"))
    total_kg = sum((row.actual_harvest_quantity_kg for row in rows), Decimal("0"))
    kg_per_mu_values = sorted(row.actual_harvest_kg_per_mu for row in rows)
    kg_per_mu_p25_val = _percentile(kg_per_mu_values, 0.25)
    kg_per_mu_median_val = _percentile(kg_per_mu_values, 0.5)
    kg_per_mu_p75_val = _percentile(kg_per_mu_values, 0.75)
    return FarmTotalDatasetDiagnostics(
        partition=partition,
        farm_group_count=len(groups),
        date_count=len(dates),
        row_count=len(rows),
        total_area_mu=emit_s3_area_mu(total_area),
        total_actual_harvest_kg=emit_s3_decimal(total_kg),
        kg_per_mu_min=emit_s3_decimal(kg_per_mu_values[0]) if kg_per_mu_values else None,
        kg_per_mu_p25=(
            emit_s3_decimal(kg_per_mu_p25_val) if kg_per_mu_p25_val is not None else None
        ),
        kg_per_mu_median=(
            emit_s3_decimal(kg_per_mu_median_val) if kg_per_mu_median_val is not None else None
        ),
        kg_per_mu_p75=(
            emit_s3_decimal(kg_per_mu_p75_val) if kg_per_mu_p75_val is not None else None
        ),
        kg_per_mu_max=emit_s3_decimal(kg_per_mu_values[-1]) if kg_per_mu_values else None,
    )


def build_partition_dataset(
    *,
    partition: PartitionLabel,
    content_bytes: bytes,
    mapping_package: FarmGroupMappingPackage,
    area_package: FarmTotalAreaAuthorityPackage,
    verify_official_hashes: bool = True,
) -> tuple[FarmTotalDatasetBlocker, FarmTotalPartitionDataset | None]:
    if partition not in {"TRAIN", "VALIDATION"}:
        return FarmTotalDatasetBlocker.TEST_PARTITION_FORBIDDEN, None

    if verify_official_hashes:
        blocker = _assert_official_partition_bytes(partition=partition, content_bytes=content_bytes)
        if blocker is not None:
            return blocker, None

    try:
        source_rows = tuple(parse_partition_bytes(content_bytes))
    except MalformedPartitionBytesError:
        return FarmTotalDatasetBlocker.MALFORMED_PARTITION_BYTES, None

    rows, area_double_count, source_actual_double_count = project_partition_to_farm_total_rows(
        partition=partition,
        source_rows=source_rows,
        mapping_package=mapping_package,
        area_package=area_package,
    )
    _ = area_double_count
    _ = source_actual_double_count
    dataset_sha256 = compute_partition_dataset_sha256(rows)
    return FarmTotalDatasetBlocker.NONE, FarmTotalPartitionDataset(
        partition=partition,
        schema_version=FARM_TOTAL_DATASET_SCHEMA_VERSION,
        rows=rows,
        dataset_sha256=dataset_sha256,
    )


def build_farm_total_data_plane(
    *,
    train_content_bytes: bytes,
    validation_content_bytes: bytes,
    mapping_package: FarmGroupMappingPackage,
    area_package: FarmTotalAreaAuthorityPackage,
    verify_official_hashes: bool = True,
) -> tuple[FarmTotalDatasetBlocker, FarmTotalDataPlaneResult | None]:
    train_blocker, train_partition = build_partition_dataset(
        partition="TRAIN",
        content_bytes=train_content_bytes,
        mapping_package=mapping_package,
        area_package=area_package,
        verify_official_hashes=verify_official_hashes,
    )
    if train_blocker != FarmTotalDatasetBlocker.NONE or train_partition is None:
        return train_blocker, None

    val_blocker, val_partition = build_partition_dataset(
        partition="VALIDATION",
        content_bytes=validation_content_bytes,
        mapping_package=mapping_package,
        area_package=area_package,
        verify_official_hashes=verify_official_hashes,
    )
    if val_blocker != FarmTotalDatasetBlocker.NONE or val_partition is None:
        return val_blocker, None

    train_diag = compute_partition_diagnostics(partition="TRAIN", rows=train_partition.rows)
    val_diag = compute_partition_diagnostics(partition="VALIDATION", rows=val_partition.rows)
    audit_diag = compute_partition_diagnostics(
        partition="TRAIN_PLUS_VALIDATION_AUDIT",
        rows=train_partition.rows + val_partition.rows,
    )

    return FarmTotalDatasetBlocker.NONE, FarmTotalDataPlaneResult(
        train_dataset=FarmTotalTrainingDataset(
            partition_dataset=train_partition,
            diagnostics=train_diag,
        ),
        validation_dataset=FarmTotalValidationDataset(
            partition_dataset=val_partition,
            diagnostics=val_diag,
        ),
        audit_union_diagnostics=audit_diag,
        mapping_set_sha256=mapping_package.mapping_set_sha256,
        area_authority_set_sha256=area_package.area_authority_set_sha256,
        area_double_count_count=0,
        source_farm_double_map_count=0,
        source_actual_double_count=0,
        validation_used_as_training_input=False,
    )
