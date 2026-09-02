"""Seed official SOURCE_002 partitions for S3-A2 PostgreSQL integration tests."""

from __future__ import annotations

import asyncio
import gzip
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.s2_materialized_dataset.lane_d.partitions import TEST_END, TEST_START
from backend.app.s2_materialized_dataset.lane_d.service import (
    S2MaterializedDatasetModel,
    S2MaterializedPartitionModel,
)
from backend.app.s2_materialized_dataset.shared.contracts import SPLIT_POLICY_VERSION
from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read import (
    OFFICIAL_DATASET_ID,
    OFFICIAL_DATASET_VERSION,
    OFFICIAL_MATERIALIZED_DATASET_IDENTITY_SHA256,
    OFFICIAL_TRAIN_BYTE_COUNT,
    OFFICIAL_TRAIN_CONTENT_SHA256,
    OFFICIAL_TRAIN_ROW_COUNT,
    OFFICIAL_VALIDATION_BYTE_COUNT,
    OFFICIAL_VALIDATION_CONTENT_SHA256,
    OFFICIAL_VALIDATION_ROW_COUNT,
    SEALED_TEST_BYTE_COUNT,
    SEALED_TEST_CONTENT_SHA256,
)
from backend.app.s3_daily_rowset.incumbent_forecast_replay_identity_origin import (
    land_replay_identity_origin_into_sync_session,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "s3_a2_official_s2_partitions"


def run_asyncio_coro_isolated[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run a coroutine from pytest-asyncio when the test thread already has a loop."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


OFFICIAL_PARTITION_META = {
    "TRAIN": {
        "start": date(2025, 8, 5),
        "end": date(2026, 1, 30),
        "row_count": OFFICIAL_TRAIN_ROW_COUNT,
        "byte_count": OFFICIAL_TRAIN_BYTE_COUNT,
        "content_sha256": OFFICIAL_TRAIN_CONTENT_SHA256,
        "partition_identity_sha256": (
            "55d8e97e73568def2cd368bcf76deeb13de5089361f70b08c8101ea8f745097b"
        ),
        "manifest_sha256": "9cb126a65311904dc34a0350a5735369aa9988dfe8056138d7e1cd9d093351fd",
    },
    "VALIDATION": {
        "start": date(2026, 1, 31),
        "end": date(2026, 3, 9),
        "row_count": OFFICIAL_VALIDATION_ROW_COUNT,
        "byte_count": OFFICIAL_VALIDATION_BYTE_COUNT,
        "content_sha256": OFFICIAL_VALIDATION_CONTENT_SHA256,
        "partition_identity_sha256": (
            "006c80ff6bc88ecf7112fd082ab7e27e71655ebd2f00ff105d6110a8473244ba"
        ),
        "manifest_sha256": "2b8a69ef6579d616464525c9ceebc141f43dc018272b572b77fe4f3c21bf79d4",
    },
    "TEST": {
        "start": TEST_START,
        "end": TEST_END,
        "row_count": 0,
        "byte_count": SEALED_TEST_BYTE_COUNT,
        "content_sha256": SEALED_TEST_CONTENT_SHA256,
        "partition_identity_sha256": (
            "452ac3ea3c8083678bcc7f929d77f1cb6c2237445a072b0895f60cf6fffca8a3"
        ),
        "manifest_sha256": "1507d2bab7edb57421f258ded681955e93559b2e7393a3f784fb3577bdb6aeab",
    },
}


def _partition_bytes(partition_name: str) -> bytes:
    path = FIXTURE_ROOT / f"{partition_name.lower()}.content.gz"
    return gzip.decompress(path.read_bytes())


async def seed_official_source_002_materialized_dataset(session: AsyncSession) -> None:
    """Persist accepted SOURCE_002 partitions and landed replay identity rows."""
    now = datetime(2026, 4, 1, tzinfo=UTC)
    dataset = S2MaterializedDatasetModel(
        dataset_id=OFFICIAL_DATASET_ID,
        dataset_version=OFFICIAL_DATASET_VERSION,
        materialized_dataset_identity_sha256=OFFICIAL_MATERIALIZED_DATASET_IDENTITY_SHA256,
        source_cohort_id="source-002-s1-cohort-v1",
        source_cohort_manifest_sha256=(
            "27ddb9a77d9ce7d4b0579d0648c23b5ade7d6a090626b695e5b41827e714fcca"
        ),
        raw_policy_version="v0-3-s2-raw-policy-v1",
        cleaning_policy_version="v0-3-s2-cleaning-policy-v1",
        correction_policy_version="v0-3-s2-correction-policy-v1",
        exclusion_policy_version="v0-3-s2-exclusion-policy-v1",
        visibility_policy_version="v0-3-s2-visibility-policy-v1",
        revision_winner_policy_version="v0-3-s2-revision-winner-policy-v1",
        cleaned_dataset_version_identity="cleaned-dataset-v1",
        builder_version="v0-3-s2-lane-d-builder-r1",
        dataset_schema_version="v0-3-s2-materialized-dataset-v1",
        lineage_complete=True,
        quality_gate_status="ACCEPTED",
        build_started_at=now,
        build_completed_at=now,
        upstream_snapshot_sha256="04bc78515516cdab60e1d0904ca41fdabd1c78052090b996d47c0f076755f82f",
    )
    session.add(dataset)
    await session.flush()
    for partition_name, meta in OFFICIAL_PARTITION_META.items():
        content_bytes = _partition_bytes(partition_name)
        session.add(
            S2MaterializedPartitionModel(
                materialized_dataset_id=dataset.id,
                partition_name=partition_name,
                partition_start_date=meta["start"],
                partition_end_date=meta["end"],
                partition_date_field="HARVEST_BUSINESS_DATE",
                target_decision="OBSERVED_FARM_PICK_QUANTITY",
                canonical_grain="SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE",
                split_policy_version=SPLIT_POLICY_VERSION,
                manifest_schema_version="v0-3-s2-materialized-dataset-manifest-v1",
                materialized_partition_schema_version="v0-3-s2-materialized-partition-v1",
                row_count=meta["row_count"],
                byte_count=meta["byte_count"],
                content_sha256=meta["content_sha256"],
                partition_identity_sha256=meta["partition_identity_sha256"],
                manifest_sha256=meta["manifest_sha256"],
                content_bytes=content_bytes,
                lineage_complete=True,
                quality_gate_status="ACCEPTED",
                rebuild_hash_replay_status="PASS",
            )
        )
    await session.flush()
    await session.run_sync(land_replay_identity_origin_into_sync_session)
    await session.flush()


async def async_sessionmaker_for_transactional_session(
    session: AsyncSession,
) -> async_sessionmaker[AsyncSession]:
    """Return a real async_sessionmaker bound to the transactional test connection."""
    connection = await session.connection()
    return async_sessionmaker(
        bind=connection,
        class_=AsyncSession,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
