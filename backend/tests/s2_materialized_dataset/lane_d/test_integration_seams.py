"""Lane D integration seam tests against shared contracts."""

from __future__ import annotations

from backend.app.s2_materialized_dataset.lane_d.builder import build_materialized_dataset
from backend.app.s2_materialized_dataset.shared.registration import (
    register_upstream,
    upstream_bundle_from_registered,
)
from backend.tests.s2_materialized_dataset.lane_d.conftest import complete_upstream


def test_builder_consumes_registered_upstream_bundle() -> None:
    upstream = complete_upstream()
    registered = register_upstream(
        lane_a=upstream.lane_a,
        lane_b=upstream.lane_b,
        lane_c=upstream.lane_c,
    )
    bundle = upstream_bundle_from_registered(registered)
    result = build_materialized_dataset(
        dataset_id="materialized-ds-1",
        dataset_version="v1",
        upstream=bundle,
        timestamps=None,
    )
    assert len(result.partitions) == 3
    for manifest in result.partitions:
        assert manifest.row_count >= 0
        assert manifest.byte_count >= 0
        assert len(manifest.content_sha256) == 64
        assert len(manifest.partition_identity_sha256) == 64
        assert len(manifest.manifest_sha256) == 64
    assert len(result.materialized_dataset_identity_sha256) == 64
