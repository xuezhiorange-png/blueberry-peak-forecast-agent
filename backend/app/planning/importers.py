from __future__ import annotations

import csv
import hashlib
from datetime import date
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.planning import (
    AgroClimateZone,
    LocationReference,
    ParameterLibraryVersion,
    ParameterObservation,
)
from backend.app.planning.imports.climate_zone_importer import (
    normalize_climate_zone_code,
)
from backend.app.planning.normalization import normalize_address_text, normalize_location_name
from backend.app.planning.repository import (
    get_farm_by_name,
    get_library_version_by_code,
    get_season_by_code,
    get_variety_by_lookup,
)
from backend.app.planning.schemas import ImportExecutionResult


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _row_hash(row: dict[str, str], *, source_version: str) -> str:
    payload = {key: row.get(key, "") for key in sorted(row)}
    payload["source_version"] = source_version
    return hashlib.sha256(repr(payload).encode("utf-8")).hexdigest()


def _parse_date(value: str) -> date | None:
    text = value.strip()
    if not text:
        return None
    return date.fromisoformat(text)


def _parse_optional_int(value: str | None) -> int | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    return int(text)


def normalized_location_reference_address(row: dict[str, str]) -> str:
    address_raw = normalize_location_name(row.get("address_raw"))
    if address_raw is not None:
        return normalize_address_text(address_raw)
    return normalize_address_text(
        " ".join(
            part
            for part in (
                row.get("province", ""),
                row.get("prefecture", ""),
                row.get("county", ""),
                row.get("township", ""),
                row.get("village", ""),
            )
            if part
        )
    )


def _optional_climate_zone_code(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return normalize_climate_zone_code(value)


async def _get_zone(
    session: AsyncSession,
    *,
    climate_zone_code: str | None,
    as_of_date: date,
) -> AgroClimateZone | None:
    normalized_code = _optional_climate_zone_code(climate_zone_code)
    if normalized_code is None:
        return None
    matches = (
        await session.scalars(
            select(AgroClimateZone)
            .where(
                AgroClimateZone.code == normalized_code,
                AgroClimateZone.valid_from <= as_of_date,
                (AgroClimateZone.valid_to.is_(None) | (AgroClimateZone.valid_to >= as_of_date)),
            )
            .order_by(AgroClimateZone.zone_version.asc(), AgroClimateZone.id.asc())
        )
    ).all()
    if len(matches) > 1:
        raise ValueError(f"climate zone conflict for code: {normalized_code}")
    return matches[0] if matches else None


async def import_location_references_csv(
    session: AsyncSession,
    *,
    file_path: Path,
    source_version: str,
    dry_run: bool,
) -> ImportExecutionResult:
    file_sha = _file_sha256(file_path)
    inserted = 0
    skipped = 0
    with file_path.open("r", encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))

    for row in rows:
        row_hash = _row_hash(row, source_version=source_version)
        existing = await session.scalar(
            select(LocationReference).where(
                LocationReference.source_version == source_version,
                LocationReference.source_row_hash == row_hash,
            )
        )
        if existing is not None:
            skipped += 1
            continue
        if dry_run:
            inserted += 1
            continue

        valid_from = _parse_date(row["valid_from"]) or date(1970, 1, 1)
        zone = await _get_zone(
            session,
            climate_zone_code=row.get("climate_zone_code"),
            as_of_date=valid_from,
        )
        farm_name = normalize_location_name(row.get("farm_name"))
        farm = (
            await get_farm_by_name(session, farm_name=farm_name) if farm_name is not None else None
        )
        session.add(
            LocationReference(
                farm_id=farm.id if farm is not None else None,
                subfarm_id=None,
                farm_code=normalize_location_name(row.get("farm_code")),
                farm_name=farm_name,
                subfarm_name=normalize_location_name(row.get("subfarm_name")),
                address_raw=normalize_location_name(row.get("address_raw")),
                address_normalized=normalized_location_reference_address(row),
                province=normalize_location_name(row.get("province")),
                prefecture=normalize_location_name(row.get("prefecture")),
                county=normalize_location_name(row.get("county")),
                township=normalize_location_name(row.get("township")),
                village=normalize_location_name(row.get("village")),
                latitude=row["latitude"],
                longitude=row["longitude"],
                altitude_m=row["altitude_m"] or None,
                climate_zone_id=zone.id if zone is not None else None,
                location_source=row.get("location_source") or "csv",
                source_version=source_version,
                valid_from=valid_from,
                valid_to=_parse_date(row.get("valid_to", "")),
                source_row_hash=row_hash,
            )
        )
        inserted += 1

    if dry_run:
        return ImportExecutionResult(
            status="dry_run",
            inserted_row_count=inserted,
            skipped_row_count=skipped,
            file_sha256=file_sha,
        )
    await session.commit()
    return ImportExecutionResult(
        status="draft",
        inserted_row_count=inserted,
        skipped_row_count=skipped,
        file_sha256=file_sha,
    )


async def import_parameter_library_csv(
    session: AsyncSession,
    *,
    file_path: Path,
    version_code: str,
    activate: bool,
    dry_run: bool,
) -> ImportExecutionResult:
    file_sha = _file_sha256(file_path)
    with file_path.open("r", encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))

    existing = await get_library_version_by_code(session, version_code=version_code)
    if (
        existing is not None
        and existing.source_file_sha256 == file_sha
        and existing.status in {"draft", "active"}
    ):
        if activate and existing.status != "active" and not dry_run:
            await session.execute(
                update(ParameterLibraryVersion)
                .where(ParameterLibraryVersion.status == "active")
                .values(status="retired")
            )
            await session.execute(
                update(ParameterLibraryVersion)
                .where(ParameterLibraryVersion.id == existing.id)
                .values(status="active")
            )
            await session.commit()
            return ImportExecutionResult("active", 0, len(rows), file_sha)
        return ImportExecutionResult("skipped", 0, len(rows), file_sha)

    if dry_run:
        return ImportExecutionResult("dry_run", len(rows), 0, file_sha)

    version = ParameterLibraryVersion(
        version_code=version_code,
        status="draft",
        source_name=file_path.name,
        source_file_sha256=file_sha,
        config_hash=file_sha,
        record_count=0,
        effective_from=date.today(),
    )
    session.add(version)
    await session.commit()

    inserted = 0
    try:
        for row in rows:
            row_hash = _row_hash(row, source_version=version_code)
            season = None
            if row.get("season_code"):
                season = await get_season_by_code(session, season_code=row["season_code"])
            variety = await get_variety_by_lookup(
                session,
                variety_id=None,
                variety_code=row["variety_code"],
                variety_name=None,
            )
            if variety is None:
                raise ValueError(f"unknown variety_code: {row['variety_code']}")
            farm_name = normalize_location_name(row.get("farm_name"))
            farm = (
                await get_farm_by_name(session, farm_name=farm_name)
                if farm_name is not None
                else None
            )
            location_reference_id = _parse_optional_int(row.get("location_reference_id"))
            location_reference = (
                await session.get(LocationReference, location_reference_id)
                if location_reference_id is not None
                else None
            )
            if location_reference_id is not None and location_reference is None:
                raise ValueError(f"unknown location_reference_id: {location_reference_id}")
            zone = await _get_zone(
                session,
                climate_zone_code=row.get("climate_zone_code"),
                as_of_date=_parse_date(row["valid_from"]) or date(1970, 1, 1),
            )
            session.add(
                ParameterObservation(
                    library_version_id=version.id,
                    parameter_type=row["parameter_type"],
                    variety_id=variety.id,
                    farm_id=farm.id if farm is not None else None,
                    subfarm_id=None,
                    location_reference_id=(
                        location_reference.id if location_reference is not None else None
                    ),
                    climate_zone_id=(
                        zone.id
                        if zone is not None
                        else (
                            location_reference.climate_zone_id
                            if location_reference is not None
                            else None
                        )
                    ),
                    season_id=season.id if season is not None else None,
                    province=normalize_location_name(row.get("province")),
                    prefecture=normalize_location_name(row.get("prefecture")),
                    county=normalize_location_name(row.get("county")),
                    township=normalize_location_name(row.get("township")),
                    altitude_m=row["altitude_m"] or None,
                    scalar_value=row["scalar_value"],
                    unit=row["unit"],
                    sample_weight=row["sample_weight"],
                    source_level=row["source_level"],
                    source_name=row["source_name"],
                    source_version=row["source_version"],
                    historical_mape=row["historical_mape"] or None,
                    date_mae_days=row["date_mae_days"] or None,
                    p90_coverage=row["p90_coverage"] or None,
                    available_at=(
                        _parse_date(row["available_at"]) if row.get("available_at") else None
                    ),
                    valid_from=_parse_date(row["valid_from"]) or date(1970, 1, 1),
                    valid_to=_parse_date(row.get("valid_to", "")),
                    source_row_hash=row_hash,
                )
            )
            inserted += 1

        await session.flush()
        await session.execute(
            update(ParameterLibraryVersion)
            .where(ParameterLibraryVersion.id == version.id)
            .values(record_count=inserted)
        )
        if activate:
            await session.execute(
                update(ParameterLibraryVersion)
                .where(
                    ParameterLibraryVersion.status == "active",
                    ParameterLibraryVersion.id != version.id,
                )
                .values(status="retired")
            )
            await session.execute(
                update(ParameterLibraryVersion)
                .where(ParameterLibraryVersion.id == version.id)
                .values(status="active")
            )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        await session.execute(
            update(ParameterLibraryVersion)
            .where(ParameterLibraryVersion.id == version.id)
            .values(status="failed")
        )
        await session.commit()
        return ImportExecutionResult(
            status="failed",
            inserted_row_count=inserted,
            skipped_row_count=0,
            file_sha256=file_sha,
            error_message=" ".join(str(exc).split())[:500],
        )

    return ImportExecutionResult(
        status="active" if activate else "draft",
        inserted_row_count=inserted,
        skipped_row_count=0,
        file_sha256=file_sha,
    )
