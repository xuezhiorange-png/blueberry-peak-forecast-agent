"""PIT adapter for the existing actual-harvest import/commit chain.

V0.6-S1 deliberately does not add a second actual-harvest persistence
framework.  The existing import record already owns source revision and
receipt timestamps.  This adapter exposes the fields needed by the common PIT
policy; ``import_received_at`` is the persisted knowledge time for a record.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from backend.app.actual_harvest_import.models import ActualHarvestImportRecordModel
from backend.app.pit.visibility import record_visible_at

ACTUAL_HARVEST_REUSED = True


@dataclass(frozen=True, slots=True)
class PITActualHarvestRecord:
    farm_id: str
    base_id: str | None
    harvest_date: date
    quantity_kg: Decimal
    source: str
    revision_id: str
    observed_at: datetime
    recorded_at: datetime
    known_at: datetime
    payload_hash: str


def adapt_actual_harvest_record(
    record: ActualHarvestImportRecordModel,
    *,
    base_id: str | None,
    payload_hash: str,
) -> PITActualHarvestRecord:
    """Project one existing imported record into the shared PIT vocabulary."""

    known_at = record.import_received_at.astimezone(UTC)
    observed_at = (record.source_recorded_at or known_at).astimezone(UTC)
    return PITActualHarvestRecord(
        farm_id=record.farm_code,
        base_id=base_id,
        harvest_date=record.harvest_business_date,
        quantity_kg=Decimal(str(record.actual_harvest_quantity_kg)),
        source=record.source_system,
        revision_id=record.external_revision_id,
        observed_at=observed_at,
        recorded_at=record.ingested_at.astimezone(UTC),
        known_at=known_at,
        payload_hash=payload_hash,
    )


def actual_harvest_visible_at(
    record: ActualHarvestImportRecordModel,
    *,
    forecast_created_at: datetime,
) -> bool:
    """Apply the common PIT rule using existing import receipt knowledge time."""

    return record_visible_at(
        adapt_actual_harvest_record(record, base_id=None, payload_hash=""),
        forecast_created_at,
    )


__all__ = [
    "ACTUAL_HARVEST_REUSED",
    "PITActualHarvestRecord",
    "adapt_actual_harvest_record",
    "actual_harvest_visible_at",
]
