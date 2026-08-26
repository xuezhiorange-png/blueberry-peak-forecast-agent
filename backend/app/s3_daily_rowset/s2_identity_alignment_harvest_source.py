"""S3-A2 S2 identity alignment harvest source."""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.s2_materialized_dataset.shared.contracts import MaterializableRow

HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF = True


def _materializable_row_sort_key(row: MaterializableRow) -> tuple[str, ...]:
    return (
        row.harvest_business_date.isoformat(),
        row.season.strip(),
        row.farm.strip(),
        row.subfarm.strip(),
        row.variety.strip(),
    )


@dataclass
class S2IdentityAlignmentHarvestSource:
    harvest_rows: tuple[MaterializableRow, ...] = ()

    def obtain(self) -> tuple[MaterializableRow, ...]:
        if not self.harvest_rows:
            return ()
        from backend.app.s3_daily_rowset.accepted_s2_identity_alignment_evidence import (
            project_accepted_s2_identity_evidence_rows,
        )

        accepted = project_accepted_s2_identity_evidence_rows(self.harvest_rows)
        if not accepted:
            return ()
        accepted_keys = {
            (row.season, row.farm, row.subfarm, row.variety, row.harvest_business_date)
            for row in accepted
        }
        deduped: dict[tuple[str, str, str, str, object], MaterializableRow] = {}
        for row in self.harvest_rows:
            key = (
                row.season.strip(),
                row.farm.strip(),
                row.subfarm.strip(),
                row.variety.strip(),
                row.harvest_business_date,
            )
            if key in accepted_keys:
                deduped[key] = row
        return tuple(sorted(deduped.values(), key=_materializable_row_sort_key))
