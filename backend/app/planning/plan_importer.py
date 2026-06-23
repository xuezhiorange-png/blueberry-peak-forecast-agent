from __future__ import annotations

import csv
import hashlib
from dataclasses import asdict
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.planning.json_types import canonical_json_value
from backend.app.planning.normalization import normalize_location_name
from backend.app.planning.plan_config import ProductionPlanConfig
from backend.app.planning.plan_repository import (
    create_import_run,
    get_farm_by_name,
    get_season_by_code,
    get_subfarm_by_name,
    get_variety_by_code,
    list_plan_versions_by_key,
    mark_import_run_completed,
    mark_import_run_failed,
)
from backend.app.planning.plan_schemas import (
    ProductionPlanImportErrorRow,
    ProductionPlanImportExecutionResult,
    ProductionPlanIntervalConflictError,
    ProductionPlanValidationError,
    ProductionPlanVersionConflictError,
)
from backend.app.planning.plan_service import _prepare_plan_inputs, create_plan_version


def _now() -> datetime:
    return datetime.now(UTC)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_date(value: str | None, *, field: str) -> date | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ProductionPlanValidationError(f"{field} must be an ISO date") from exc


def _parse_decimal(value: str | None, *, field: str, required: bool) -> Decimal | None:
    if value is None:
        if required:
            raise ProductionPlanValidationError(f"{field} is required")
        return None
    text = value.strip()
    if not text:
        if required:
            raise ProductionPlanValidationError(f"{field} is required")
        return None
    try:
        parsed = Decimal(text)
    except InvalidOperation as exc:
        raise ProductionPlanValidationError(f"{field} must be a valid decimal") from exc
    if not parsed.is_finite():
        raise ProductionPlanValidationError(f"{field} must be finite")
    return parsed


def _parse_int(value: str | None, *, field: str) -> int:
    if value is None or not value.strip():
        raise ProductionPlanValidationError(f"{field} is required")
    try:
        return int(value.strip())
    except ValueError as exc:
        raise ProductionPlanValidationError(f"{field} must be an integer") from exc


async def import_production_plans_csv(
    session: AsyncSession,
    *,
    file_path: Path,
    config: ProductionPlanConfig,
    dry_run: bool,
    source_version_override: str | None = None,
) -> ProductionPlanImportExecutionResult:
    file_sha = _file_sha256(file_path)
    with file_path.open("r", encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))

    report: dict[str, Any] = {
        "file_name": file_path.name,
        "file_sha256": file_sha,
        "dry_run": dry_run,
        "errors": [],
    }
    if dry_run:
        run_id = None
    else:
        run = await create_import_run(
            session,
            file_name=file_path.name,
            file_sha256=file_sha,
            source_version=source_version_override,
            status="running",
            report_json=report,
        )
        run_id = run.id

    inserted_count = 0
    skipped_count = 0
    rejected_count = 0
    duplicate_count = 0
    unknown_farm_count = 0
    unknown_subfarm_count = 0
    unknown_season_count = 0
    unknown_variety_count = 0
    invalid_date_count = 0
    invalid_numeric_count = 0
    overlap_conflict_count = 0
    version_conflict_count = 0
    error_rows: list[ProductionPlanImportErrorRow] = []

    try:
        for row_number, row in enumerate(rows, start=2):
            farm_name = normalize_location_name(row.get("farm_name"))
            season_code = normalize_location_name(row.get("season_code"))
            variety_code = normalize_location_name(row.get("variety_code"))
            subfarm_name = normalize_location_name(row.get("subfarm_name"))
            source_version = source_version_override or normalize_location_name(
                row.get("source_version")
            )
            try:
                if farm_name is None:
                    unknown_farm_count += 1
                    raise ProductionPlanValidationError("farm_name is required")
                if season_code is None:
                    unknown_season_count += 1
                    raise ProductionPlanValidationError("season_code is required")
                if variety_code is None:
                    unknown_variety_count += 1
                    raise ProductionPlanValidationError("variety_code is required")

                farm = await get_farm_by_name(session, farm_name=farm_name)
                if farm is None:
                    unknown_farm_count += 1
                    raise ProductionPlanValidationError(f"unknown farm_name: {farm_name}")
                season = await get_season_by_code(session, season_code=season_code)
                if season is None:
                    unknown_season_count += 1
                    raise ProductionPlanValidationError(f"unknown season_code: {season_code}")
                variety = await get_variety_by_code(session, variety_code=variety_code)
                if variety is None:
                    unknown_variety_count += 1
                    raise ProductionPlanValidationError(f"unknown variety_code: {variety_code}")
                subfarm_id: int | None = None
                if subfarm_name is not None:
                    subfarm = await get_subfarm_by_name(
                        session,
                        farm_id=farm.id,
                        subfarm_name=subfarm_name,
                    )
                    if subfarm is None:
                        unknown_subfarm_count += 1
                        raise ProductionPlanValidationError(
                            f"unknown subfarm_name: {subfarm_name}"
                        )
                    subfarm_id = subfarm.id

                payload = {
                    "farm_id": farm.id,
                    "subfarm_id": subfarm_id,
                    "season_id": season.id,
                    "variety_id": variety.id,
                    "planted_area_mu": _parse_decimal(
                        row.get("planted_area_mu"),
                        field="planted_area_mu",
                        required=True,
                    ),
                    "expected_yield_kg_per_mu": _parse_decimal(
                        row.get("expected_yield_kg_per_mu"),
                        field="expected_yield_kg_per_mu",
                        required=True,
                    ),
                    "marketable_rate": _parse_decimal(
                        row.get("marketable_rate"),
                        field="marketable_rate",
                        required=True,
                    ),
                    "tree_age_years": _parse_decimal(
                        row.get("tree_age_years"),
                        field="tree_age_years",
                        required=False,
                    ),
                    "pruning_date": _parse_date(row.get("pruning_date"), field="pruning_date"),
                    "flowering_start_date": _parse_date(
                        row.get("flowering_start_date"),
                        field="flowering_start_date",
                    ),
                    "flowering_peak_date": _parse_date(
                        row.get("flowering_peak_date"),
                        field="flowering_peak_date",
                    ),
                    "flowering_end_date": _parse_date(
                        row.get("flowering_end_date"),
                        field="flowering_end_date",
                    ),
                    "first_pick_date": _parse_date(
                        row.get("first_pick_date"),
                        field="first_pick_date",
                    ),
                    "expected_total_marketable_kg": _parse_decimal(
                        row.get("expected_total_marketable_kg"),
                        field="expected_total_marketable_kg",
                        required=False,
                    ),
                    "version": _parse_int(row.get("version"), field="version"),
                    "effective_from": _parse_date(
                        row.get("effective_from"),
                        field="effective_from",
                    ),
                    "effective_to": _parse_date(row.get("effective_to"), field="effective_to"),
                    "available_at": _parse_date(row.get("available_at"), field="available_at"),
                    "source_type": row.get("source_type") or "csv",
                    "source_name": (
                        normalize_location_name(row.get("source_name")) or file_path.name
                    ),
                    "source_version": source_version,
                    "notes": normalize_location_name(row.get("notes")),
                }
            except ProductionPlanValidationError as exc:
                rejected_count += 1
                message = str(exc)
                if "date" in message:
                    invalid_date_count += 1
                elif any(
                    field in message
                    for field in (
                        "planted_area_mu",
                        "expected_yield_kg_per_mu",
                        "marketable_rate",
                        "tree_age_years",
                        "expected_total_marketable_kg",
                        "version",
                    )
                ):
                    invalid_numeric_count += 1
                error_rows.append(
                    ProductionPlanImportErrorRow(
                        row_number=row_number,
                        field="row",
                        message=message,
                    )
                )
                continue

            if dry_run:
                try:
                    existing_rows = await list_plan_versions_by_key(
                        session,
                        farm_id=farm.id,
                        subfarm_id=subfarm_id,
                        season_id=season.id,
                        variety_id=variety.id,
                    )
                    preview_plan, _row_hash, _warnings, _created = await _prepare_plan_inputs(
                        session,
                        payload=payload,
                        config=config,
                        existing_rows=existing_rows,
                    )
                except ProductionPlanVersionConflictError:
                    rejected_count += 1
                    version_conflict_count += 1
                    error_rows.append(
                        ProductionPlanImportErrorRow(
                            row_number=row_number,
                            field="version",
                            message="version already exists for business key",
                        )
                    )
                except ProductionPlanIntervalConflictError:
                    rejected_count += 1
                    overlap_conflict_count += 1
                    error_rows.append(
                        ProductionPlanImportErrorRow(
                            row_number=row_number,
                            field="effective_from",
                            message="effective interval overlaps with existing version",
                        )
                    )
                except ProductionPlanValidationError as exc:
                    rejected_count += 1
                    error_rows.append(
                        ProductionPlanImportErrorRow(
                            row_number=row_number,
                            field="row",
                            message=str(exc),
                        )
                    )
                else:
                    if preview_plan is None:
                        skipped_count += 1
                        duplicate_count += 1
                    else:
                        inserted_count += 1
                continue

            try:
                # CSV import resolves master-data lookups in the same session first.
                # Those reads open an implicit transaction; clear it before the
                # version-write transaction acquires the business-key advisory lock.
                if session.in_transaction():
                    await session.rollback()
                result = await create_plan_version(session, payload=payload, config=config)
            except ProductionPlanVersionConflictError:
                rejected_count += 1
                version_conflict_count += 1
                error_rows.append(
                    ProductionPlanImportErrorRow(
                        row_number=row_number,
                        field="version",
                        message="version already exists for business key",
                    )
                )
            except ProductionPlanIntervalConflictError:
                rejected_count += 1
                overlap_conflict_count += 1
                error_rows.append(
                    ProductionPlanImportErrorRow(
                        row_number=row_number,
                        field="effective_from",
                        message="effective interval overlaps with existing version",
                    )
                )
            except ProductionPlanValidationError as exc:
                rejected_count += 1
                error_rows.append(
                    ProductionPlanImportErrorRow(
                        row_number=row_number,
                        field="row",
                        message=str(exc),
                    )
                )
            else:
                if result.created:
                    inserted_count += 1
                else:
                    skipped_count += 1
                    duplicate_count += 1

        report.update(
            {
                "row_count": len(rows),
                "inserted_count": inserted_count,
                "skipped_count": skipped_count,
                "rejected_count": rejected_count,
                "duplicate_count": duplicate_count,
                "unknown_farm_count": unknown_farm_count,
                "unknown_subfarm_count": unknown_subfarm_count,
                "unknown_season_count": unknown_season_count,
                "unknown_variety_count": unknown_variety_count,
                "invalid_date_count": invalid_date_count,
                "invalid_numeric_count": invalid_numeric_count,
                "overlap_conflict_count": overlap_conflict_count,
                "version_conflict_count": version_conflict_count,
                "errors": [asdict(item) for item in error_rows],
                "completed_at": _now().isoformat(),
            }
        )
        if run_id is not None:
            await mark_import_run_completed(
                session,
                run_id=run_id,
                row_count=len(rows),
                inserted_count=inserted_count,
                skipped_count=skipped_count,
                rejected_count=rejected_count,
                duplicate_count=duplicate_count,
                unknown_farm_count=unknown_farm_count,
                unknown_subfarm_count=unknown_subfarm_count,
                unknown_season_count=unknown_season_count,
                unknown_variety_count=unknown_variety_count,
                invalid_date_count=invalid_date_count,
                invalid_numeric_count=invalid_numeric_count,
                overlap_conflict_count=overlap_conflict_count,
                version_conflict_count=version_conflict_count,
                report_json=cast(dict[str, object], canonical_json_value(report)),
            )
        return ProductionPlanImportExecutionResult(
            status="dry_run" if dry_run else "completed",
            file_sha256=file_sha,
            row_count=len(rows),
            inserted_count=inserted_count,
            skipped_count=skipped_count,
            rejected_count=rejected_count,
            duplicate_count=duplicate_count,
            unknown_farm_count=unknown_farm_count,
            unknown_subfarm_count=unknown_subfarm_count,
            unknown_season_count=unknown_season_count,
            unknown_variety_count=unknown_variety_count,
            invalid_date_count=invalid_date_count,
            invalid_numeric_count=invalid_numeric_count,
            overlap_conflict_count=overlap_conflict_count,
            version_conflict_count=version_conflict_count,
            error_rows=tuple(error_rows),
            audit_run_id=run_id,
        )
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        report["errors"] = report.get("errors", [])
        if run_id is not None:
            await mark_import_run_failed(
                session,
                run_id=run_id,
                report_json=cast(dict[str, object], canonical_json_value(report)),
                error_message=str(exc),
            )
        return ProductionPlanImportExecutionResult(
            status="failed",
            file_sha256=file_sha,
            row_count=len(rows),
            inserted_count=inserted_count,
            skipped_count=skipped_count,
            rejected_count=rejected_count,
            duplicate_count=duplicate_count,
            unknown_farm_count=unknown_farm_count,
            unknown_subfarm_count=unknown_subfarm_count,
            unknown_season_count=unknown_season_count,
            unknown_variety_count=unknown_variety_count,
            invalid_date_count=invalid_date_count,
            invalid_numeric_count=invalid_numeric_count,
            overlap_conflict_count=overlap_conflict_count,
            version_conflict_count=version_conflict_count,
            error_rows=tuple(error_rows),
            audit_run_id=run_id,
            error_message=str(exc),
        )
