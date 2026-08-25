"""S3-A2 incumbent forecast replay source."""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.s3_daily_rowset.catalog_artifact import IncumbentForecastArtifactEntry
from backend.app.s3_daily_rowset.incumbent_forecast_artifact_content import (
    project_incumbent_forecast_artifact_entries,
)

HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF = True


@dataclass
class IncumbentForecastReplaySource:
    replay_rows: tuple[IncumbentForecastArtifactEntry, ...] = ()
    uses_harvest_date_as_forecast_cutoff: bool = False

    def obtain(self) -> tuple[IncumbentForecastArtifactEntry, ...]:
        if self.uses_harvest_date_as_forecast_cutoff:
            return ()
        if not self.replay_rows:
            return ()
        return project_incumbent_forecast_artifact_entries(self.replay_rows)
