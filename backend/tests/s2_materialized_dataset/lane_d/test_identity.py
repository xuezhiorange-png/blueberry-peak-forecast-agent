"""Lane D §4.11 dataset identity tests."""

from __future__ import annotations

from datetime import UTC, datetime

from backend.app.s2_materialized_dataset.lane_d.builder import (
    BuildTimestamps,
    build_materialized_dataset,
)
from backend.app.s2_materialized_dataset.lane_d.identity import (
    materialized_dataset_identity_sha256,
)
from backend.tests.s2_materialized_dataset.lane_d.conftest import complete_upstream


def test_dataset_identity_is_deterministic() -> None:
    upstream = complete_upstream()
    timestamps = BuildTimestamps(
        started_at=datetime(2026, 4, 1, tzinfo=UTC),
        completed_at=datetime(2026, 4, 1, tzinfo=UTC),
    )
    first = build_materialized_dataset(
        dataset_id="materialized-ds-1",
        dataset_version="v1",
        upstream=upstream,
        timestamps=timestamps,
    )
    second = build_materialized_dataset(
        dataset_id="materialized-ds-1",
        dataset_version="v1",
        upstream=upstream,
        timestamps=timestamps,
    )
    assert first.materialized_dataset_identity_sha256 == second.materialized_dataset_identity_sha256
    assert len(first.materialized_dataset_identity_sha256) == 64


def test_dataset_identity_binds_partition_identities_and_content_hashes() -> None:
    upstream = complete_upstream()
    result = build_materialized_dataset(
        dataset_id="materialized-ds-1",
        dataset_version="v1",
        upstream=upstream,
        timestamps=BuildTimestamps(
            started_at=datetime(2026, 4, 1, tzinfo=UTC),
            completed_at=datetime(2026, 4, 1, tzinfo=UTC),
        ),
    )
    recomputed = materialized_dataset_identity_sha256(
        dataset_id=result.dataset_id,
        dataset_version=result.dataset_version,
        raw_policy_version=upstream.lane_a.raw_policy_version,
        cleaning_policy_version=upstream.lane_b.cleaning_policy_version,
        correction_policy_version=upstream.lane_b.correction_policy_version,
        exclusion_policy_version=upstream.lane_b.exclusion_policy_version,
        visibility_policy_version=upstream.lane_c.visibility_policy_version,
        revision_winner_policy_version=upstream.lane_c.revision_winner_policy_version,
        ordered_partition_identities=tuple(
            manifest.partition_identity_sha256 for manifest in result.partitions
        ),
        ordered_partition_content_hashes=tuple(
            manifest.content_sha256 for manifest in result.partitions
        ),
    )
    assert recomputed == result.materialized_dataset_identity_sha256
