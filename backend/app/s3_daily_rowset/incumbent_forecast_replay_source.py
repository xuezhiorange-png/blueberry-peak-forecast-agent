"""S3-A2 incumbent forecast replay source."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from backend.app.s3_daily_rowset.catalog_artifact import IncumbentForecastArtifactEntry
from backend.app.s3_daily_rowset.incumbent_forecast_artifact_content import (
    project_incumbent_forecast_artifact_entries,
)

HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF = True


def _empty_v0_2_postgres_obtain() -> tuple[IncumbentForecastArtifactEntry, ...]:
    from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_live_postgres_read import (
        read_bindable_replay_identity_rows,
    )
    from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_sql_table_authority import (
        bindable_table_names,
    )

    if not bindable_table_names():
        return ()
    return read_bindable_replay_identity_rows()


@dataclass
class IncumbentForecastReplaySource:
    replay_rows: tuple[IncumbentForecastArtifactEntry, ...] = ()
    uses_harvest_date_as_forecast_cutoff: bool = False
    v0_2_postgres_obtain: Callable[[], tuple[IncumbentForecastArtifactEntry, ...]] = (
        _empty_v0_2_postgres_obtain
    )

    def obtain(self) -> tuple[IncumbentForecastArtifactEntry, ...]:
        if self.uses_harvest_date_as_forecast_cutoff:
            return ()
        if self.replay_rows:
            return project_incumbent_forecast_artifact_entries(self.replay_rows)
        postgres_rows = self.v0_2_postgres_obtain()
        if not postgres_rows:
            return ()
        return project_incumbent_forecast_artifact_entries(postgres_rows)
