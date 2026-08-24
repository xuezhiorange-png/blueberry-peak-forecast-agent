"""S3-A2 incumbent forecast artifact live adapter."""

from __future__ import annotations

from dataclasses import dataclass

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

    def has_versioned_artifact(self) -> bool:
        if self.artifact is None:
            return False
        if self.artifact.uses_harvest_date_as_forecast_cutoff:
            return True
        return bool(_accepted_rows(self.artifact.rows))

    def catalog_source_kind(self) -> CatalogSourceKind:
        if self.artifact is None:
            return CatalogSourceKind.UNBOUND
        if self.artifact.uses_harvest_date_as_forecast_cutoff:
            return self.artifact.catalog_source_kind
        if not _accepted_rows(self.artifact.rows):
            return CatalogSourceKind.UNBOUND
        return self.artifact.catalog_source_kind

    def entries(self) -> tuple[IncumbentForecastArtifactEntry, ...]:
        if self.artifact is None or self.artifact.uses_harvest_date_as_forecast_cutoff:
            return ()
        return _accepted_rows(self.artifact.rows)

    def uses_harvest_date_as_forecast_cutoff(self) -> bool:
        if self.artifact is None:
            return False
        return self.artifact.uses_harvest_date_as_forecast_cutoff
