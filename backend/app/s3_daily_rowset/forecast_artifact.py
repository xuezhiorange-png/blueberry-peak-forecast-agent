"""S3-A2 incumbent forecast artifact live adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from backend.app.s3_daily_rowset.actuals import (
    is_evaluation_partition_allowed,
    window_contains_test_partition,
)
from backend.app.s3_daily_rowset.catalog_artifact import (
    IncumbentForecastArtifactEntry,
    IncumbentForecastArtifactPort,
)
from backend.app.s3_daily_rowset.registry import (
    FORBIDDEN_CATALOG_SOURCE_KINDS,
    HORIZON_H7_SUCCESS_FIXTURE_HASH,
    CatalogSourceKind,
)
from backend.app.s3_daily_rowset.schemas import HORIZON_DAYS
from backend.app.s3_daily_rowset.window import cutoff_business_date, horizon_window_dates

if TYPE_CHECKING:
    from backend.app.s3_daily_rowset.incumbent_forecast_artifact_content import (
        IncumbentForecastArtifactContentProducer,
    )


def _default_content_producer() -> IncumbentForecastArtifactContentProducer:
    from backend.app.s3_daily_rowset.incumbent_forecast_artifact_content import (
        IncumbentForecastArtifactContentProducer,
    )

    return IncumbentForecastArtifactContentProducer()


def _try_live_origin_construction_forecast_artifact() -> VersionedIncumbentForecastArtifact | None:
    try:
        from backend.app.s3_daily_rowset.s3_a2_default_catalog_live_origin_construction import (
            live_origin_forecast_artifact_for_default_construction,
        )
    except ImportError:
        return None
    return live_origin_forecast_artifact_for_default_construction()


FORBIDDEN_EMPTY_FORECAST_ARTIFACT_HASHES = frozenset(
    {
        "",
        "0" * 64,
    }
)


class ForbiddenForecastArtifactError(ValueError):
    """Raised when a forecast artifact identity or source is forbidden."""


def _validate_forecast_artifact_identity(content_identity_sha256: str) -> None:
    if content_identity_sha256 in FORBIDDEN_EMPTY_FORECAST_ARTIFACT_HASHES:
        raise ForbiddenForecastArtifactError("empty forecast artifact hash sentinel is forbidden")
    if content_identity_sha256 == HORIZON_H7_SUCCESS_FIXTURE_HASH:
        raise ForbiddenForecastArtifactError(
            "H=7 fixture hash cannot be used as forecast artifact identity"
        )


def _entry_intersects_test_partition(entry: IncumbentForecastArtifactEntry) -> bool:
    cutoff_date = cutoff_business_date(entry.forecast_cutoff_at)
    if not is_evaluation_partition_allowed(cutoff_date):
        return True
    for horizon_days in sorted(HORIZON_DAYS):
        window_dates = horizon_window_dates(entry.forecast_cutoff_at, horizon_days)
        if window_contains_test_partition(window_dates):
            return True
    return False


def _accepted_rows(
    rows: tuple[IncumbentForecastArtifactEntry, ...],
) -> tuple[IncumbentForecastArtifactEntry, ...]:
    return tuple(row for row in rows if not _entry_intersects_test_partition(row))


@dataclass(frozen=True, slots=True)
class VersionedIncumbentForecastArtifact:
    content_identity_sha256: str
    rows: tuple[IncumbentForecastArtifactEntry, ...]
    catalog_source_kind: CatalogSourceKind = CatalogSourceKind.BOUND_FIXTURE
    uses_harvest_date_as_forecast_cutoff: bool = False
    model_identity_metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _validate_forecast_artifact_identity(self.content_identity_sha256)
        if self.catalog_source_kind in FORBIDDEN_CATALOG_SOURCE_KINDS:
            raise ForbiddenForecastArtifactError(
                f"forbidden forecast artifact source kind: {self.catalog_source_kind}"
            )


@dataclass
class IncumbentForecastArtifactAdapter(IncumbentForecastArtifactPort):
    artifact: VersionedIncumbentForecastArtifact | None = None
    producer: IncumbentForecastArtifactContentProducer = field(
        default_factory=_default_content_producer
    )

    def _resolved_artifact(self) -> VersionedIncumbentForecastArtifact | None:
        if self.artifact is not None:
            return self.artifact
        produced = self.producer.produce()
        if produced is not None:
            return produced
        return _try_live_origin_construction_forecast_artifact()

    def has_versioned_artifact(self) -> bool:
        artifact = self._resolved_artifact()
        if artifact is None:
            return False
        if artifact.uses_harvest_date_as_forecast_cutoff:
            return True
        return bool(_accepted_rows(artifact.rows))

    def catalog_source_kind(self) -> CatalogSourceKind:
        artifact = self._resolved_artifact()
        if artifact is None:
            return CatalogSourceKind.UNBOUND
        if artifact.uses_harvest_date_as_forecast_cutoff:
            return artifact.catalog_source_kind
        if not _accepted_rows(artifact.rows):
            return CatalogSourceKind.UNBOUND
        return artifact.catalog_source_kind

    def entries(self) -> tuple[IncumbentForecastArtifactEntry, ...]:
        artifact = self._resolved_artifact()
        if artifact is None or artifact.uses_harvest_date_as_forecast_cutoff:
            return ()
        return _accepted_rows(artifact.rows)

    def uses_harvest_date_as_forecast_cutoff(self) -> bool:
        artifact = self._resolved_artifact()
        if artifact is None:
            return False
        return artifact.uses_harvest_date_as_forecast_cutoff
