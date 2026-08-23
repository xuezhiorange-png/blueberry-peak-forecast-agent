"""Contract registration and lineage completeness tests."""

from __future__ import annotations

from backend.app.s2_materialized_dataset.shared.contracts import (
    SOURCE_002_CONTROLLED_SQL_MATERIALIZATION_ENABLED,
    SOURCE_002_EXPECTED_IDFL_SQL_ROW_COUNT,
    SOURCE_002_EXPECTED_NON_EXCLUDED_GRAIN_COUNT,
    SOURCE_002_ROW_LEVEL_READ,
    SOURCE_COHORT_MANIFEST_SHA256,
    LaneAUpstreamPort,
    LaneBUpstreamPort,
    LaneCUpstreamPort,
)
from backend.app.s2_materialized_dataset.shared.registration import (
    lineage_complete,
    register_upstream,
    upstream_bundle_from_registered,
)
from backend.tests.s2_materialized_dataset.lane_d.conftest import (
    FakeLaneA,
    FakeLaneB,
    FakeLaneC,
    complete_upstream,
    make_row,
)


def test_source_002_controlled_sql_flag_enabled() -> None:
    assert SOURCE_002_CONTROLLED_SQL_MATERIALIZATION_ENABLED is True
    assert SOURCE_002_ROW_LEVEL_READ is False
    assert SOURCE_002_EXPECTED_IDFL_SQL_ROW_COUNT == 233171
    assert SOURCE_002_EXPECTED_NON_EXCLUDED_GRAIN_COUNT == 33894


def test_register_upstream_exposes_bundle_ports() -> None:
    upstream = complete_upstream()
    registered = register_upstream(
        lane_a=upstream.lane_a,
        lane_b=upstream.lane_b,
        lane_c=upstream.lane_c,
    )
    bundle = upstream_bundle_from_registered(registered)
    assert isinstance(bundle.lane_a, LaneAUpstreamPort)
    assert isinstance(bundle.lane_b, LaneBUpstreamPort)
    assert isinstance(bundle.lane_c, LaneCUpstreamPort)
    assert bundle.lane_a.source_cohort_manifest_sha256 == SOURCE_COHORT_MANIFEST_SHA256


def test_lineage_complete_true_for_complete_upstream() -> None:
    upstream = complete_upstream()
    registered = register_upstream(
        lane_a=upstream.lane_a,
        lane_b=upstream.lane_b,
        lane_c=upstream.lane_c,
    )
    assert lineage_complete(registered) is True


def test_lineage_complete_false_when_lane_a_missing() -> None:
    upstream = complete_upstream()
    registered = register_upstream(
        lane_a=FakeLaneA(lineage_present=False),
        lane_b=upstream.lane_b,
        lane_c=upstream.lane_c,
    )
    assert lineage_complete(registered) is False


def test_lineage_complete_false_when_lane_b_missing() -> None:
    upstream = complete_upstream()
    registered = register_upstream(
        lane_a=upstream.lane_a,
        lane_b=FakeLaneB(lineage_present=False),
        lane_c=upstream.lane_c,
    )
    assert lineage_complete(registered) is False


def test_lineage_complete_false_when_lane_c_missing() -> None:
    upstream = complete_upstream()
    registered = register_upstream(
        lane_a=upstream.lane_a,
        lane_b=upstream.lane_b,
        lane_c=FakeLaneC(lineage_present=False),
    )
    assert lineage_complete(registered) is False


def test_lineage_complete_false_when_cohort_manifest_mismatch() -> None:
    upstream = complete_upstream()
    registered = register_upstream(
        lane_a=FakeLaneA(source_cohort_manifest_sha256="bad"),
        lane_b=upstream.lane_b,
        lane_c=upstream.lane_c,
    )
    assert lineage_complete(registered) is False


def test_lineage_complete_false_when_row_identity_missing() -> None:
    upstream = complete_upstream(
        rows=(make_row(source_row_identity=""),),
    )
    registered = register_upstream(
        lane_a=upstream.lane_a,
        lane_b=upstream.lane_b,
        lane_c=upstream.lane_c,
    )
    assert lineage_complete(registered) is False
