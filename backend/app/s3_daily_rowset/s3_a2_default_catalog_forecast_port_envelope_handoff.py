"""Deterministic bare-default forecast-port envelope handoff from landed reviewed grains.

Loads the coordinator-reviewed three-member identity set, maps members to replay
rows, and invokes frozen IncumbentForecastArtifactContentProducer semantics.
Does not install the global reviewed-set loader, does not set a session provider,
and does not call content-for-reviewed-grains classifier.
"""

from __future__ import annotations

from typing import Final

from backend.app.s3_daily_rowset.catalog_artifact import IncumbentForecastArtifactEntry
from backend.app.s3_daily_rowset.forecast_artifact import VersionedIncumbentForecastArtifact
from backend.app.s3_daily_rowset.incumbent_forecast_artifact_content import (
    IncumbentForecastArtifactContentProducer,
)
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_replay_identity_grain_row_presence import (
    ReviewedGrainIdentity,
)
from backend.app.s3_daily_rowset.registry import CatalogSourceKind
from backend.app.s3_daily_rowset.s3_a2_coordinator_reviewed_live_origin_grain_identity_set import (
    REVIEWED_GRAIN_IDENTITY_SET_IDENTITY_SHA256,
    load_coordinator_reviewed_live_origin_grain_identity_set,
)

EXPECTED_CONTENT_IDENTITY_SHA256: Final[str] = (
    "06f45beb0c42be0ecf2750dede6783ca5f9a1e363d85ef3e26b0faccf14353f5"
)


def _members_to_replay_rows(
    members: tuple[ReviewedGrainIdentity, ...],
) -> tuple[IncumbentForecastArtifactEntry, ...]:
    return tuple(
        IncumbentForecastArtifactEntry(
            model_id=member.model_id,
            forecast_cutoff_at=member.forecast_cutoff_at,
            forecast_quantile=member.forecast_quantile,
        )
        for member in members
    )


def deterministic_coordinator_reviewed_grains_forecast_artifact() -> (
    VersionedIncumbentForecastArtifact | None
):
    identity_set = load_coordinator_reviewed_live_origin_grain_identity_set()
    if not identity_set.artifact_available:
        return None
    if identity_set.artifact_id != REVIEWED_GRAIN_IDENTITY_SET_IDENTITY_SHA256:
        return None

    replay_rows = _members_to_replay_rows(identity_set.members)
    produced = IncumbentForecastArtifactContentProducer(
        replay_rows=replay_rows,
        declared_catalog_source_kind=CatalogSourceKind.V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF,
        uses_harvest_date_as_forecast_cutoff=False,
    ).produce()
    if produced is None:
        return None
    if produced.content_identity_sha256 != EXPECTED_CONTENT_IDENTITY_SHA256:
        return None
    return produced
