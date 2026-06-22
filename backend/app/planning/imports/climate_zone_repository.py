from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.baseline.json_types import canonical_json_value
from backend.app.models.planning import AgroClimateZone, ClimateZoneImportRun

if TYPE_CHECKING:
    from backend.app.planning.imports.climate_zone_importer import ClimateZoneImportRow


def _now() -> datetime:
    return datetime.now(UTC)


async def load_existing_climate_zones(
    session: AsyncSession,
    *,
    business_keys: list[tuple[str, str]],
) -> list[AgroClimateZone]:
    if not business_keys:
        return []
    statement = select(AgroClimateZone).where(
        tuple_(AgroClimateZone.code, AgroClimateZone.zone_version).in_(business_keys)
    )
    return list((await session.scalars(statement)).all())


async def create_climate_zone_import_run(
    session: AsyncSession,
    *,
    file_name: str,
    file_sha256: str,
    zone_version: str | None,
    source_name: str | None,
    source_version: str | None,
    status: str,
    row_count: int,
    valid_row_count: int,
    invalid_row_count: int,
    inserted_count: int,
    skipped_count: int,
    conflict_count: int,
    report_json: dict[str, Any],
    error_message: str | None,
) -> ClimateZoneImportRun:
    run = ClimateZoneImportRun(
        file_name=file_name,
        file_sha256=file_sha256,
        zone_version=zone_version,
        source_name=source_name,
        source_version=source_version,
        status=status,
        row_count=row_count,
        valid_row_count=valid_row_count,
        invalid_row_count=invalid_row_count,
        inserted_count=inserted_count,
        skipped_count=skipped_count,
        conflict_count=conflict_count,
        report_json=cast(dict[str, Any], canonical_json_value(report_json)),
        error_message=error_message,
        finished_at=_now() if status != "running" else None,
    )
    session.add(run)
    await session.commit()
    return run


async def mark_climate_zone_import_run_completed(
    session: AsyncSession,
    *,
    run_id: int,
    inserted_count: int,
    skipped_count: int,
    conflict_count: int,
    report_json: dict[str, Any],
) -> None:
    await session.execute(
        update(ClimateZoneImportRun)
        .where(ClimateZoneImportRun.id == run_id)
        .values(
            status="completed",
            inserted_count=inserted_count,
            skipped_count=skipped_count,
            conflict_count=conflict_count,
            report_json=cast(dict[str, Any], canonical_json_value(report_json)),
            error_message=None,
            finished_at=_now(),
        )
    )
    await session.commit()


async def mark_climate_zone_import_run_failed(
    session: AsyncSession,
    *,
    run_id: int,
    conflict_count: int,
    report_json: dict[str, Any],
    error_message: str,
) -> None:
    await session.execute(
        update(ClimateZoneImportRun)
        .where(ClimateZoneImportRun.id == run_id)
        .values(
            status="failed",
            conflict_count=conflict_count,
            report_json=cast(dict[str, Any], canonical_json_value(report_json)),
            error_message=error_message,
            finished_at=_now(),
        )
    )
    await session.commit()


async def insert_climate_zones(
    session: AsyncSession,
    *,
    rows: Sequence[ClimateZoneImportRow],
) -> None:
    session.add_all(
        [
            AgroClimateZone(
                code=row.code,
                name=row.name,
                country=row.country,
                province=row.province or row.country,
                prefecture=row.prefecture,
                county=row.county,
                centroid_latitude=row.centroid_latitude,
                centroid_longitude=row.centroid_longitude,
                min_altitude_m=row.min_altitude_m,
                max_altitude_m=row.max_altitude_m,
                zone_version=row.zone_version,
                valid_from=row.valid_from,
                valid_to=row.valid_to,
                source_name=row.source_name,
                source_version=row.source_version,
            )
            for row in rows
        ]
    )
