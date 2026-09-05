#!/usr/bin/env python3
"""Run V0.3 Farm-total data plane against accepted SOURCE-002 TRAIN+VALIDATION."""

from __future__ import annotations

import asyncio
import json
import sys
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.app.db.session import AsyncSessionMaker, dispose_db_engine  # noqa: E402
from backend.app.forecast_quality.farm_total_data_plane import (  # noqa: E402
    load_authority_bundle_from_paths,
    materialize_farm_total_baseline_data_plane,
)
from backend.app.forecast_quality.farm_total_policy import (  # noqa: E402
    REVIEWED_ELIGIBLE_PROXY_AREA_MU,
    REVIEWED_ELIGIBLE_PROXY_GROUP_COUNT,
    REVIEWED_ELIGIBLE_PROXY_HISTORICAL_HARVEST_KG,
)
from backend.app.s3_daily_rowset import (  # noqa: E402
    accepted_s2_train_val_source_002_row_level_read_live_obtain as source_002_live,
)


async def _load_partitions() -> tuple[bytes, bytes]:
    try:
        async with AsyncSessionMaker() as session:
            obtain = await session.run_sync(source_002_live._obtain_from_session)
            if not obtain.obtained:
                raise RuntimeError(f"SOURCE-002 obtain failed: {obtain.reason_code}")
            return obtain.train_content_bytes, obtain.validation_content_bytes
    finally:
        await dispose_db_engine()


def main() -> None:
    authority_dir = (
        Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/v03-farm-total-authority")
    )
    bundle = load_authority_bundle_from_paths(
        mapping_package_path=authority_dir / "farm_total_group_mapping_package.json",
        area_authority_package_path=authority_dir / "farm_total_area_authority_package.json",
    )
    train_bytes, validation_bytes = asyncio.run(_load_partitions())
    blocker, result = materialize_farm_total_baseline_data_plane(
        train_content_bytes=train_bytes,
        validation_content_bytes=validation_bytes,
        authority_bundle=bundle,
        verify_official_hashes=True,
    )
    if blocker.value != "NONE" or result is None:
        raise SystemExit(f"data plane failed: {blocker}")

    eligible_count = len(bundle.area_package.rows)
    authorized_area = sum((row.area_mu for row in bundle.area_package.rows), Decimal("0"))
    if eligible_count != REVIEWED_ELIGIBLE_PROXY_GROUP_COUNT:
        raise SystemExit(
            f"eligible count mismatch: {eligible_count} != {REVIEWED_ELIGIBLE_PROXY_GROUP_COUNT}"
        )
    reviewed_area = Decimal(REVIEWED_ELIGIBLE_PROXY_AREA_MU)
    if authorized_area != reviewed_area:
        raise SystemExit(f"area mismatch: {authorized_area} != {reviewed_area}")

    train_groups = {r.baseline_farm_group_key for r in result.train_dataset.partition_dataset.rows}
    val_groups = {
        r.baseline_farm_group_key for r in result.validation_dataset.partition_dataset.rows
    }
    all_groups = train_groups | val_groups
    if len(all_groups) != eligible_count:
        raise SystemExit(f"projected group count {len(all_groups)} != {eligible_count}")

    total_kg = Decimal(result.audit_union_diagnostics.total_actual_harvest_kg)
    reviewed_kg = Decimal(REVIEWED_ELIGIBLE_PROXY_HISTORICAL_HARVEST_KG)
    if total_kg.quantize(Decimal("0.000001")) != reviewed_kg.quantize(Decimal("0.000001")):
        raise SystemExit(f"harvest mismatch: {total_kg} != {reviewed_kg}")

    print(f"FARM_GROUP_MAPPING_SET_SHA256={result.mapping_set_sha256}")
    print(f"FARM_AREA_AUTHORITY_SET_SHA256={result.area_authority_set_sha256}")
    print(f"ELIGIBLE_FARM_GROUP_COUNT={eligible_count}")
    print(f"AUTHORIZED_AREA_MU={authorized_area}")
    print(f"TRAIN_FARM_TOTAL_ROW_COUNT={len(result.train_dataset.partition_dataset.rows)}")
    print(
        f"VALIDATION_FARM_TOTAL_ROW_COUNT={len(result.validation_dataset.partition_dataset.rows)}"
    )
    print(f"TRAIN_FARM_GROUP_COUNT={result.train_dataset.diagnostics.farm_group_count}")
    print(f"VALIDATION_FARM_GROUP_COUNT={result.validation_dataset.diagnostics.farm_group_count}")
    print(
        f"TRAIN_TOTAL_ACTUAL_HARVEST_KG={result.train_dataset.diagnostics.total_actual_harvest_kg}"
    )
    print(
        f"VALIDATION_TOTAL_ACTUAL_HARVEST_KG={result.validation_dataset.diagnostics.total_actual_harvest_kg}"
    )
    print(
        f"TRAIN_FARM_TOTAL_DATASET_SHA256={result.train_dataset.partition_dataset.dataset_sha256}"
    )
    print(
        f"VALIDATION_FARM_TOTAL_DATASET_SHA256={result.validation_dataset.partition_dataset.dataset_sha256}"
    )
    print(f"AREA_DOUBLE_COUNT_COUNT={result.area_double_count_count}")
    print(f"SOURCE_FARM_DOUBLE_MAP_COUNT={result.source_farm_double_map_count}")
    print(f"SOURCE_ACTUAL_DOUBLE_COUNT={result.source_actual_double_count}")
    print(f"VALIDATION_USED_AS_TRAINING_INPUT={result.validation_used_as_training_input}")
    train_diag = result.train_dataset.diagnostics
    val_diag = result.validation_dataset.diagnostics
    print(
        "AUDIT_DIAGNOSTICS="
        + json.dumps(
            {
                "train": {
                    "partition": train_diag.partition,
                    "farm_group_count": train_diag.farm_group_count,
                    "row_count": train_diag.row_count,
                    "total_actual_harvest_kg": train_diag.total_actual_harvest_kg,
                },
                "validation": {
                    "partition": val_diag.partition,
                    "farm_group_count": val_diag.farm_group_count,
                    "row_count": val_diag.row_count,
                    "total_actual_harvest_kg": val_diag.total_actual_harvest_kg,
                },
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
