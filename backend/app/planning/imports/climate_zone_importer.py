from __future__ import annotations

import csv
import hashlib
import json
import unicodedata
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.planning.imports.climate_zone_repository import (
    create_climate_zone_import_run,
    insert_climate_zones,
    load_existing_climate_zones,
    mark_climate_zone_import_run_completed,
    mark_climate_zone_import_run_failed,
)
from backend.app.planning.schemas import (
    ClimateZoneImportErrorRow,
    ClimateZoneImportExecutionResult,
)

_REQUIRED_FIELDS = (
    "code",
    "name",
    "country",
    "centroid_latitude",
    "centroid_longitude",
    "zone_version",
    "valid_from",
    "source_name",
    "source_version",
)

_EXPECTED_HEADERS = (
    "code",
    "name",
    "country",
    "province",
    "prefecture",
    "county",
    "centroid_latitude",
    "centroid_longitude",
    "min_altitude_m",
    "max_altitude_m",
    "zone_version",
    "valid_from",
    "valid_to",
    "source_name",
    "source_version",
)


class ClimateZoneImportConflictError(ValueError):
    pass


@dataclass(frozen=True)
class ClimateZoneImportRow:
    row_number: int
    code: str
    name: str
    country: str
    province: str | None
    prefecture: str | None
    county: str | None
    centroid_latitude: Decimal
    centroid_longitude: Decimal
    min_altitude_m: Decimal | None
    max_altitude_m: Decimal | None
    zone_version: str
    valid_from: date
    valid_to: date | None
    source_name: str
    source_version: str
    source_row_hash: str


@dataclass(frozen=True)
class ClimateZoneImportPrepared:
    file_sha256: str
    zone_version: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    skipped_rows: int
    rows_to_insert_count: int
    rows: tuple[ClimateZoneImportRow, ...]
    error_rows: tuple[ClimateZoneImportErrorRow, ...]
    warnings: tuple[str, ...] = ()

    def to_report_payload(self) -> dict[str, Any]:
        return {
            "file_sha256": self.file_sha256,
            "zone_version": self.zone_version,
            "total_rows": self.total_rows,
            "valid_rows": self.valid_rows,
            "invalid_rows": self.invalid_rows,
            "skipped_rows": self.skipped_rows,
            "rows_to_insert_count": self.rows_to_insert_count,
            "rows": [_json_ready(asdict(row)) for row in self.rows],
            "error_rows": [_json_ready(asdict(row)) for row in self.error_rows],
            "warnings": list(self.warnings),
        }


def _json_ready(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple | list):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    return value


def _sanitize_error_message(message: str) -> str:
    return " ".join(message.replace("\n", " ").replace("\r", " ").split())[:500]


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = unicodedata.normalize("NFKC", value)
    normalized = " ".join(normalized.split()).strip()
    return normalized or None


def normalize_climate_zone_code(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().upper()
    if not normalized:
        raise ValueError("code")
    if any(char.isspace() for char in normalized):
        raise ValueError("code")
    return normalized


def build_climate_zone_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_climate_zone_row_hash(payload: dict[str, Any]) -> str:
    stable_payload = {
        key: _json_ready(payload.get(key))
        for key in (
            "code",
            "name",
            "country",
            "province",
            "prefecture",
            "county",
            "centroid_latitude",
            "centroid_longitude",
            "min_altitude_m",
            "max_altitude_m",
            "zone_version",
            "valid_from",
            "valid_to",
            "source_name",
            "source_version",
        )
    }
    text = json.dumps(
        stable_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _parse_decimal(value: str | None, *, field: str) -> Decimal | None:
    normalized = _normalize_text(value)
    if normalized is None:
        return None
    try:
        return Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError(field) from exc


def _parse_date(value: str | None, *, field: str) -> date | None:
    normalized = _normalize_text(value)
    if normalized is None:
        return None
    try:
        return date.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(field) from exc


def _normalize_row(
    row: dict[str, str | None],
    *,
    row_number: int,
    zone_version_override: str | None,
    source_name_override: str | None,
    source_version_override: str | None,
) -> ClimateZoneImportRow:
    def value(key: str) -> str | None:
        return _normalize_text(row.get(key))

    for field in _REQUIRED_FIELDS:
        if value(field) is None:
            raise ValueError(field)

    code = normalize_climate_zone_code(value("code") or "")
    latitude = _parse_decimal(row.get("centroid_latitude"), field="centroid_latitude")
    longitude = _parse_decimal(
        row.get("centroid_longitude"),
        field="centroid_longitude",
    )
    min_altitude = _parse_decimal(row.get("min_altitude_m"), field="min_altitude_m")
    max_altitude = _parse_decimal(row.get("max_altitude_m"), field="max_altitude_m")
    valid_from = _parse_date(row.get("valid_from"), field="valid_from")
    valid_to = _parse_date(row.get("valid_to"), field="valid_to")
    csv_zone_version = value("zone_version")
    csv_source_name = value("source_name")
    csv_source_version = value("source_version")

    if latitude is None or longitude is None or valid_from is None:
        raise ValueError("required")
    if latitude < Decimal("-90") or latitude > Decimal("90"):
        raise ValueError("centroid_latitude")
    if longitude < Decimal("-180") or longitude > Decimal("180"):
        raise ValueError("centroid_longitude")
    if (
        min_altitude is not None
        and max_altitude is not None
        and min_altitude > max_altitude
    ):
        raise ValueError("altitude_range")
    if valid_to is not None and valid_to < valid_from:
        raise ValueError("valid_to")

    if (
        zone_version_override is not None
        and csv_zone_version is not None
        and zone_version_override != csv_zone_version
    ):
        raise ValueError("zone_version_conflict")
    if (
        source_name_override is not None
        and csv_source_name is not None
        and source_name_override != csv_source_name
    ):
        raise ValueError("source_name_conflict")
    if (
        source_version_override is not None
        and csv_source_version is not None
        and source_version_override != csv_source_version
    ):
        raise ValueError("source_version_conflict")

    quantized_latitude = latitude.quantize(Decimal("0.000001"))
    quantized_longitude = longitude.quantize(Decimal("0.000001"))
    quantized_min_altitude = (
        min_altitude.quantize(Decimal("0.01"))
        if min_altitude is not None
        else None
    )
    quantized_max_altitude = (
        max_altitude.quantize(Decimal("0.01"))
        if max_altitude is not None
        else None
    )
    zone_version = zone_version_override or csv_zone_version or ""
    source_name = source_name_override or csv_source_name or ""
    source_version = source_version_override or csv_source_version or ""
    row_hash = build_climate_zone_row_hash(
        {
            "code": code,
            "name": value("name") or "",
            "country": value("country") or "",
            "province": value("province"),
            "prefecture": value("prefecture"),
            "county": value("county"),
            "centroid_latitude": quantized_latitude,
            "centroid_longitude": quantized_longitude,
            "min_altitude_m": quantized_min_altitude,
            "max_altitude_m": quantized_max_altitude,
            "zone_version": zone_version,
            "valid_from": valid_from,
            "valid_to": valid_to,
            "source_name": source_name,
            "source_version": source_version,
        }
    )
    return ClimateZoneImportRow(
        row_number=row_number,
        code=code,
        name=value("name") or "",
        country=value("country") or "",
        province=value("province"),
        prefecture=value("prefecture"),
        county=value("county"),
        centroid_latitude=quantized_latitude,
        centroid_longitude=quantized_longitude,
        min_altitude_m=quantized_min_altitude,
        max_altitude_m=quantized_max_altitude,
        zone_version=zone_version,
        valid_from=valid_from,
        valid_to=valid_to,
        source_name=source_name,
        source_version=source_version,
        source_row_hash=row_hash,
    )


def prepare_climate_zone_import(
    file_path: Path,
    *,
    zone_version_override: str | None = None,
    source_name_override: str | None = None,
    source_version_override: str | None = None,
) -> ClimateZoneImportPrepared:
    file_sha = build_climate_zone_file_sha256(file_path)
    with file_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            raise ValueError("CSV header is missing")
        missing_headers = [
            field for field in _EXPECTED_HEADERS if field not in reader.fieldnames
        ]
        if missing_headers:
            raise ValueError(f"missing headers: {', '.join(missing_headers)}")
        raw_rows = list(reader)

    valid_rows: list[ClimateZoneImportRow] = []
    error_rows: list[ClimateZoneImportErrorRow] = []
    warnings: list[str] = []

    for index, raw_row in enumerate(raw_rows, start=2):
        try:
            valid_rows.append(
                _normalize_row(
                    raw_row,
                    row_number=index,
                    zone_version_override=zone_version_override,
                    source_name_override=source_name_override,
                    source_version_override=source_version_override,
                )
            )
        except ValueError as exc:
            field = str(exc)
            error_rows.append(
                ClimateZoneImportErrorRow(
                    row_number=index,
                    field=field,
                    message=field,
                )
            )

    unique_rows: list[ClimateZoneImportRow] = []
    skipped_rows = 0
    by_business_key: dict[tuple[str, str], ClimateZoneImportRow] = {}
    seen_hashes: set[str] = set()
    for climate_row in valid_rows:
        business_key = (climate_row.code, climate_row.zone_version)
        existing_row = by_business_key.get(business_key)
        if (
            existing_row is not None
            and existing_row.source_row_hash != climate_row.source_row_hash
        ):
            raise ClimateZoneImportConflictError(
                "conflicting rows for code="
                f"{climate_row.code} zone_version={climate_row.zone_version}"
            )
        if climate_row.source_row_hash in seen_hashes:
            skipped_rows += 1
            continue
        seen_hashes.add(climate_row.source_row_hash)
        by_business_key[business_key] = climate_row
        unique_rows.append(climate_row)

    zone_versions = {row.zone_version for row in unique_rows}
    zone_version = zone_version_override or (
        sorted(zone_versions)[0] if zone_versions else ""
    )
    if len(zone_versions) > 1 and zone_version_override is None:
        warnings.append("multiple_zone_versions_present")

    return ClimateZoneImportPrepared(
        file_sha256=file_sha,
        zone_version=zone_version,
        total_rows=len(raw_rows),
        valid_rows=len(valid_rows),
        invalid_rows=len(error_rows),
        skipped_rows=skipped_rows,
        rows_to_insert_count=len(unique_rows),
        rows=tuple(unique_rows),
        error_rows=tuple(error_rows),
        warnings=tuple(warnings),
    )


def _result_from_prepared(
    prepared: ClimateZoneImportPrepared,
    *,
    status: str,
    dry_run: bool,
    inserted_rows: int,
    skipped_rows: int,
    conflict_rows: int,
    audit_run_id: int | None,
    error_message: str | None,
) -> ClimateZoneImportExecutionResult:
    return ClimateZoneImportExecutionResult(
        status=status,
        file_sha256=prepared.file_sha256,
        zone_version=prepared.zone_version or None,
        dry_run=dry_run,
        total_rows=prepared.total_rows,
        valid_rows=prepared.valid_rows,
        invalid_rows=prepared.invalid_rows,
        inserted_rows=inserted_rows,
        skipped_rows=skipped_rows,
        updated_rows=0,
        conflict_rows=conflict_rows,
        error_rows=prepared.error_rows,
        warnings=prepared.warnings,
        audit_run_id=audit_run_id,
        error_message=error_message,
    )


async def import_agro_climate_zones_csv(
    session: AsyncSession,
    *,
    file_path: Path,
    dry_run: bool,
    zone_version_override: str | None = None,
    source_name_override: str | None = None,
    source_version_override: str | None = None,
) -> ClimateZoneImportExecutionResult:
    prepared = prepare_climate_zone_import(
        file_path,
        zone_version_override=zone_version_override,
        source_name_override=source_name_override,
        source_version_override=source_version_override,
    )
    source_name = (
        prepared.rows[0].source_name if prepared.rows else source_name_override
    )
    source_version = (
        prepared.rows[0].source_version if prepared.rows else source_version_override
    )

    business_keys = [(row.code, row.zone_version) for row in prepared.rows]
    existing_rows = await load_existing_climate_zones(
        session,
        business_keys=business_keys,
    )
    existing_by_key = {(row.code, row.zone_version): row for row in existing_rows}

    rows_to_insert: list[ClimateZoneImportRow] = []
    skipped_from_db = 0
    conflict_rows = 0
    error_rows = list(prepared.error_rows)
    for row in prepared.rows:
        existing = existing_by_key.get((row.code, row.zone_version))
        if existing is None:
            rows_to_insert.append(row)
            continue
        existing_hash = build_climate_zone_row_hash(
            {
                "code": existing.code,
                "name": existing.name,
                "country": existing.country,
                "province": existing.province,
                "prefecture": existing.prefecture,
                "county": existing.county,
                "centroid_latitude": existing.centroid_latitude,
                "centroid_longitude": existing.centroid_longitude,
                "min_altitude_m": existing.min_altitude_m,
                "max_altitude_m": existing.max_altitude_m,
                "zone_version": existing.zone_version,
                "valid_from": existing.valid_from,
                "valid_to": existing.valid_to,
                "source_name": existing.source_name,
                "source_version": existing.source_version,
            }
        )
        if existing_hash == row.source_row_hash:
            skipped_from_db += 1
            continue
        conflict_rows += 1
        error_rows.append(
            ClimateZoneImportErrorRow(
                row_number=row.row_number,
                field="code+zone_version",
                message=f"conflict for {row.code}/{row.zone_version}",
            )
        )

    prepared_with_db = ClimateZoneImportPrepared(
        file_sha256=prepared.file_sha256,
        zone_version=prepared.zone_version,
        total_rows=prepared.total_rows,
        valid_rows=prepared.valid_rows,
        invalid_rows=prepared.invalid_rows,
        skipped_rows=prepared.skipped_rows + skipped_from_db,
        rows_to_insert_count=len(rows_to_insert),
        rows=tuple(rows_to_insert),
        error_rows=tuple(error_rows),
        warnings=prepared.warnings,
    )
    report_payload = prepared_with_db.to_report_payload()
    report_payload["file_name"] = file_path.name
    report_payload["source_name"] = source_name
    report_payload["source_version"] = source_version
    report_payload["conflict_count"] = conflict_rows

    if dry_run:
        status = "failed" if prepared_with_db.invalid_rows or conflict_rows else "dry_run"
        return _result_from_prepared(
            prepared_with_db,
            status=status,
            dry_run=True,
            inserted_rows=0,
            skipped_rows=prepared_with_db.skipped_rows,
            conflict_rows=conflict_rows,
            audit_run_id=None,
            error_message=("validation_failed" if status == "failed" else None),
        )

    if prepared_with_db.invalid_rows or conflict_rows:
        audit = await create_climate_zone_import_run(
            session,
            file_name=file_path.name,
            file_sha256=prepared_with_db.file_sha256,
            zone_version=prepared_with_db.zone_version or None,
            source_name=source_name,
            source_version=source_version,
            status="failed",
            row_count=prepared_with_db.total_rows,
            valid_row_count=prepared_with_db.valid_rows,
            invalid_row_count=prepared_with_db.invalid_rows,
            inserted_count=0,
            skipped_count=prepared_with_db.skipped_rows,
            conflict_count=conflict_rows,
            report_json=report_payload,
            error_message=(
                "validation_failed" if prepared_with_db.invalid_rows else "conflict"
            ),
        )
        return _result_from_prepared(
            prepared_with_db,
            status="failed",
            dry_run=False,
            inserted_rows=0,
            skipped_rows=prepared_with_db.skipped_rows,
            conflict_rows=conflict_rows,
            audit_run_id=audit.id,
            error_message=(
                "validation_failed" if prepared_with_db.invalid_rows else "conflict"
            ),
        )

    audit = await create_climate_zone_import_run(
        session,
        file_name=file_path.name,
        file_sha256=prepared_with_db.file_sha256,
        zone_version=prepared_with_db.zone_version or None,
        source_name=source_name,
        source_version=source_version,
        status="running",
        row_count=prepared_with_db.total_rows,
        valid_row_count=prepared_with_db.valid_rows,
        invalid_row_count=prepared_with_db.invalid_rows,
        inserted_count=0,
        skipped_count=prepared_with_db.skipped_rows,
        conflict_count=0,
        report_json=report_payload,
        error_message=None,
    )
    try:
        await insert_climate_zones(session, rows=list(prepared_with_db.rows))
        await session.commit()
        await mark_climate_zone_import_run_completed(
            session,
            run_id=audit.id,
            inserted_count=len(prepared_with_db.rows),
            skipped_count=prepared_with_db.skipped_rows,
            conflict_count=0,
            report_json=report_payload,
        )
    except Exception as exc:
        error_message = _sanitize_error_message(str(exc))
        await session.rollback()
        await mark_climate_zone_import_run_failed(
            session,
            run_id=audit.id,
            conflict_count=0,
            report_json=report_payload,
            error_message=error_message,
        )
        return _result_from_prepared(
            prepared_with_db,
            status="failed",
            dry_run=False,
            inserted_rows=0,
            skipped_rows=prepared_with_db.skipped_rows,
            conflict_rows=0,
            audit_run_id=audit.id,
            error_message=error_message,
        )

    return _result_from_prepared(
        prepared_with_db,
        status="completed",
        dry_run=False,
        inserted_rows=len(prepared_with_db.rows),
        skipped_rows=prepared_with_db.skipped_rows,
        conflict_rows=0,
        audit_run_id=audit.id,
        error_message=None,
    )
