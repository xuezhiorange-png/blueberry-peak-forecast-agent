"""Upstream registration and lineage completeness checks for Lane D."""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.s2_materialized_dataset.shared.contracts import (
    SOURCE_COHORT_MANIFEST_SHA256,
    LaneAUpstreamPort,
    LaneBUpstreamPort,
    LaneCUpstreamPort,
    UpstreamBundlePort,
)


@dataclass(frozen=True, slots=True)
class RegisteredUpstream:
    lane_a: LaneAUpstreamPort
    lane_b: LaneBUpstreamPort
    lane_c: LaneCUpstreamPort


def register_upstream(
    *,
    lane_a: LaneAUpstreamPort,
    lane_b: LaneBUpstreamPort,
    lane_c: LaneCUpstreamPort,
) -> RegisteredUpstream:
    """Register upstream lane ports for Lane D consumption."""
    return RegisteredUpstream(lane_a=lane_a, lane_b=lane_b, lane_c=lane_c)


def upstream_bundle_from_registered(registered: RegisteredUpstream) -> UpstreamBundlePort:
    return _RegisteredBundle(registered)


@dataclass(frozen=True, slots=True)
class _RegisteredBundle:
    registered: RegisteredUpstream

    @property
    def lane_a(self) -> LaneAUpstreamPort:
        return self.registered.lane_a

    @property
    def lane_b(self) -> LaneBUpstreamPort:
        return self.registered.lane_b

    @property
    def lane_c(self) -> LaneCUpstreamPort:
        return self.registered.lane_c


def lineage_complete(registered: RegisteredUpstream) -> bool:
    """True only when every upstream lane reports a complete lineage identity."""
    lane_a = registered.lane_a
    lane_b = registered.lane_b
    lane_c = registered.lane_c
    if not (
        lane_a.lineage_identity_present()
        and lane_b.lineage_identity_present()
        and lane_c.lineage_identity_present()
    ):
        return False
    if lane_a.source_cohort_manifest_sha256 != SOURCE_COHORT_MANIFEST_SHA256:
        return False
    for row in lane_b.iter_materializable_rows():
        if not (
            row.source_row_identity
            and row.cleaned_row_identity
            and row.pit_visibility_identity
            and row.revision_winner_identity
        ):
            return False
    return True
