from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import get_settings
from backend.app.db.session import AsyncSessionMaker
from backend.app.etl.history.config import file_sha256
from backend.app.etl.history.parser import HeaderError, parse_workbook
from backend.app.etl.history.quality import decimal_json, process_rows
from backend.app.etl.history.schemas import (
    FileReport,
    ImportConfig,
    ImportResult,
    ProcessedRow,
    SourceSpec,
)
from backend.app.models.historical_import import FactReceiptRaw, IngestFile
from backend.app.models.master_data import Factory, Grade, Season, Variety

BUSINESS_FINGERPRINT_QUERY_BATCH_SIZE = 5000


class ImportFatalError(RuntimeError):
    def __init__(self, message: str, *, report: FileReport | None = None) -> None:
        super().__init__(message)
        self.report = report


@dataclass(frozen=True)
class PreparedImport:
    path: Path
    file_sha256: str
    season_id: int | None
    rows: list[ProcessedRow]
    report: FileReport


@dataclass(frozen=True)
class IngestAcquisition:
    ingest: IngestFile
    action: str


def _now() -> datetime:
    return datetime.now(UTC)


def _sanitize_error_message(message: str) -> str:
    settings = get_settings()
    sanitized = message.replace(settings.async_database_url, "<redacted-db-url>")
    sanitized = sanitized.replace(
        settings.postgres_password.get_secret_value(),
        "<redacted-password>",
    )
    sanitized = re.sub(r"postgresql(\+\w+)?://\S+", "<redacted-db-url>", sanitized)
    sanitized = sanitized.replace("\n", " ").replace("\r", " ").strip()
    return sanitized[:500]


def _source_path(source: SourceSpec, base_dir: Path) -> Path:
    return source.path if source.path.is_absolute() else base_dir / source.path


def _empty_report(source: SourceSpec, path: Path, digest: str) -> FileReport:
    return FileReport(
        source_path=str(source.path),
        file_name=path.name,
        file_sha256=digest,
        source_name=source.source_name,
        season_code=source.season_code,
    )


def _failed_result(
    source: SourceSpec,
    digest: str,
    report: FileReport,
    message: str,
) -> ImportResult:
    sanitized = _sanitize_error_message(message)
    if sanitized not in report.errors:
        report.errors.append(sanitized)
    report.inserted_row_count = 0
    return ImportResult(
        source_path=str(source.path),
        file_sha256=digest,
        status="failed",
        inserted_row_count=0,
        report=report,
    )


def _warning_result(
    source: SourceSpec,
    digest: str,
    status: str,
    report: FileReport,
) -> ImportResult:
    report.inserted_row_count = 0
    return ImportResult(
        source_path=str(source.path),
        file_sha256=digest,
        status=status,
        inserted_row_count=0,
        report=report,
    )


def _report_has_fatal_errors(report: FileReport) -> bool:
    return bool(report.errors)


def _evaluate_fatal_quality_thresholds(report: FileReport, config: ImportConfig) -> None:
    thresholds = config.rules.fatal_quality_thresholds
    total_rows = max(report.row_count, 1)
    invalid_date_count = sum(
        sheet.empty_date_count + sheet.invalid_date_count for sheet in report.sheet_reports
    )
    invalid_weight_count = sum(
        sheet.empty_weight_count + sheet.invalid_weight_count for sheet in report.sheet_reports
    )
    if (
        thresholds.max_invalid_date_count is not None
        and invalid_date_count > thresholds.max_invalid_date_count
    ):
        report.errors.append(
            f"invalid_date_count={invalid_date_count} exceeds "
            f"max_invalid_date_count={thresholds.max_invalid_date_count}"
        )
    if (
        thresholds.max_invalid_date_ratio is not None
        and (Decimal(invalid_date_count) / Decimal(total_rows)) > thresholds.max_invalid_date_ratio
    ):
        report.errors.append(
            f"invalid_date_ratio={invalid_date_count}/{total_rows} exceeds "
            f"max_invalid_date_ratio={thresholds.max_invalid_date_ratio}"
        )
    if (
        thresholds.max_invalid_weight_count is not None
        and invalid_weight_count > thresholds.max_invalid_weight_count
    ):
        report.errors.append(
            f"invalid_weight_count={invalid_weight_count} exceeds "
            f"max_invalid_weight_count={thresholds.max_invalid_weight_count}"
        )
    if (
        thresholds.max_invalid_weight_ratio is not None
        and (Decimal(invalid_weight_count) / Decimal(total_rows))
        > thresholds.max_invalid_weight_ratio
    ):
        report.errors.append(
            f"invalid_weight_ratio={invalid_weight_count}/{total_rows} exceeds "
            f"max_invalid_weight_ratio={thresholds.max_invalid_weight_ratio}"
        )


async def _season_id(session: AsyncSession, season_code: str) -> int | None:
    season = await session.scalar(select(Season).where(Season.code == season_code))
    if season is None:
        return None
    return season.id


async def _master_maps(
    session: AsyncSession,
) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    factories = (await session.scalars(select(Factory))).all()
    varieties = (await session.scalars(select(Variety))).all()
    grades = (await session.scalars(select(Grade))).all()
    factory_map: dict[str, int] = {}
    for factory in factories:
        factory_map[factory.name] = factory.id
        if factory.code:
            factory_map[factory.code] = factory.id
    variety_map: dict[str, int] = {}
    for variety in varieties:
        variety_map[variety.name] = variety.id
        variety_map[variety.code] = variety.id
    grade_map = {grade.code: grade.id for grade in grades}
    return factory_map, variety_map, grade_map


async def _existing_business_rows(
    session: AsyncSession,
    business_fingerprints: set[str],
) -> dict[str, list[dict[str, Any]]]:
    if not business_fingerprints:
        return {}
    result: dict[str, list[dict[str, Any]]] = {}
    ordered_fingerprints = sorted(business_fingerprints)
    for start in range(0, len(ordered_fingerprints), BUSINESS_FINGERPRINT_QUERY_BATCH_SIZE):
        batch = ordered_fingerprints[start : start + BUSINESS_FINGERPRINT_QUERY_BATCH_SIZE]
        rows = await session.execute(
            select(
                FactReceiptRaw.business_fingerprint,
                FactReceiptRaw.ingest_file_id,
                FactReceiptRaw.source_sheet,
                FactReceiptRaw.source_row_number,
            ).where(FactReceiptRaw.business_fingerprint.in_(batch))
        )
        for fingerprint, ingest_file_id, source_sheet, source_row_number in rows:
            result.setdefault(fingerprint, []).append(
                {
                    "ingest_file_id": ingest_file_id,
                    "source_sheet": source_sheet,
                    "source_row_number": source_row_number,
                }
            )
    return result


async def _ingest_by_sha(session: AsyncSession, file_sha256: str) -> IngestFile | None:
    return cast(
        IngestFile | None,
        await session.scalar(select(IngestFile).where(IngestFile.file_sha256 == file_sha256)),
    )


def _row_to_model(row: ProcessedRow, ingest_file_id: int, season_id: int) -> FactReceiptRaw:
    parsed = row.parsed
    return FactReceiptRaw(
        ingest_file_id=ingest_file_id,
        season_id=season_id,
        source_sheet=parsed.source_sheet,
        source_row_number=parsed.source_row_number,
        raw_payload=decimal_json(parsed.raw_payload),
        receipt_date_raw=parsed.receipt_date_raw,
        link_name_raw=parsed.link_name_raw,
        farm_raw=parsed.farm_raw,
        subfarm_raw=parsed.subfarm_raw,
        variety_raw=parsed.variety_raw,
        grade_raw=parsed.grade_raw,
        weight_kg_raw=parsed.weight_kg_raw,
        factory_raw=parsed.factory_raw,
        receipt_date=parsed.receipt_date,
        weight_kg=parsed.weight_kg,
        factory_normalized=row.factory_normalized,
        variety_normalized=row.variety_normalized,
        factory_id=row.factory_id,
        variety_id=row.variety_id,
        grade_id=row.grade_id,
        is_date_valid=parsed.receipt_date is not None,
        is_weight_valid=parsed.weight_kg is not None,
        is_factory_known=row.is_factory_known,
        is_variety_known=row.is_variety_known,
        is_suspected_duplicate=row.is_suspected_duplicate,
        is_analysis_eligible=row.is_analysis_eligible,
        exclusion_reasons=row.exclusion_reasons,
        parse_errors=parsed.parse_errors,
        source_row_fingerprint=row.source_row_fingerprint,
        business_fingerprint=row.business_fingerprint,
    )


async def _prepare_file(
    session: AsyncSession,
    source: SourceSpec,
    config: ImportConfig,
    base_dir: Path,
) -> PreparedImport:
    path = _source_path(source, base_dir)
    if not path.exists():
        raise ImportFatalError(f"Source file not found: {source.path}")
    digest = file_sha256(path)
    try:
        parsed_rows, parser_stats = parse_workbook(
            path,
            config.rules,
            source.header_row,
            expected_sheets=source.expected_sheets,
            expected_sheets_behavior=source.expected_sheets_behavior,
            header_aliases=source.header_aliases,
        )
    except HeaderError as exc:
        report = _empty_report(source, path, digest)
        report.errors.append(str(exc))
        raise ImportFatalError(decimal_json(report.errors)[0], report=report) from exc

    season_id = await _season_id(session, source.season_code)
    factory_map, variety_map, grade_map = await _master_maps(session)
    rows_for_lookup, _report_for_lookup = process_rows(
        rows=parsed_rows,
        source=source,
        file_sha256=digest,
        config=config,
        factory_ids_by_name=factory_map,
        variety_ids_by_name=variety_map,
        grade_ids_by_code=grade_map,
    )
    existing_rows = await _existing_business_rows(
        session,
        {row.business_fingerprint for row in rows_for_lookup},
    )
    rows, report = process_rows(
        rows=parsed_rows,
        source=source,
        file_sha256=digest,
        config=config,
        factory_ids_by_name=factory_map,
        variety_ids_by_name=variety_map,
        grade_ids_by_code=grade_map,
        existing_business_rows=existing_rows,
    )
    report.sheet_count = int(parser_stats["sheet_count"])
    report.actual_sheets = list(parser_stats["actual_sheets"])
    report.missing_expected_sheets = list(parser_stats["missing_expected_sheets"])
    report.unexpected_sheets = list(parser_stats["unexpected_sheets"])
    report.warnings.extend(str(item) for item in parser_stats["warnings"])
    sheet_stats_by_name = {item["sheet_name"]: item for item in parser_stats["sheet_stats"]}
    for sheet_report in report.sheet_reports:
        stats = sheet_stats_by_name[sheet_report.sheet_name]
        sheet_report.physical_row_count = int(stats["physical_row_count"])
        sheet_report.blank_row_count = int(stats["blank_row_count"])
        sheet_report.data_row_count = int(stats["data_row_count"])
    if season_id is None:
        report.errors.append(f"Missing season code: {source.season_code}")
    _evaluate_fatal_quality_thresholds(report, config)
    return PreparedImport(
        path=path,
        file_sha256=digest,
        season_id=season_id,
        rows=rows,
        report=report,
    )


async def _acquire_ingest_record(
    source: SourceSpec,
    config: ImportConfig,
    prepared: PreparedImport,
) -> IngestAcquisition:
    async with AsyncSessionMaker() as session:
        existing = await session.scalar(
            select(IngestFile).where(IngestFile.file_sha256 == prepared.file_sha256)
        )
        if existing is not None:
            if existing.status == "completed":
                return IngestAcquisition(existing, "completed")
            if existing.status == "running":
                return IngestAcquisition(existing, "running")
            existing.file_name = prepared.path.name
            existing.source_path = str(source.path)
            existing.season_id = prepared.season_id
            existing.status = "running"
            existing.sheet_count = prepared.report.sheet_count
            existing.row_count = prepared.report.row_count
            existing.inserted_row_count = 0
            existing.suspected_duplicate_count = prepared.report.suspected_duplicate_count
            existing.started_at = _now()
            existing.finished_at = None
            existing.config_hash = config.config_hash
            existing.config_snapshot = decimal_json(config.snapshot)
            existing.quality_report = {}
            existing.error_message = None
            await session.commit()
            return IngestAcquisition(existing, "retry")

        ingest = IngestFile(
            file_name=prepared.path.name,
            source_path=str(source.path),
            file_sha256=prepared.file_sha256,
            season_id=prepared.season_id,
            status="running",
            sheet_count=prepared.report.sheet_count,
            row_count=prepared.report.row_count,
            inserted_row_count=0,
            suspected_duplicate_count=prepared.report.suspected_duplicate_count,
            started_at=_now(),
            config_hash=config.config_hash,
            config_snapshot=decimal_json(config.snapshot),
            quality_report={},
        )
        session.add(ingest)
        try:
            await session.commit()
            return IngestAcquisition(ingest, "created")
        except IntegrityError:
            await session.rollback()
            existing = await session.scalar(
                select(IngestFile).where(IngestFile.file_sha256 == prepared.file_sha256)
            )
            if existing is None:
                raise
            if existing.status == "completed":
                return IngestAcquisition(existing, "completed")
            if existing.status == "running":
                return IngestAcquisition(existing, "running")
            return IngestAcquisition(existing, "retry")


async def _mark_ingest_failed(
    ingest_id: int,
    prepared: PreparedImport,
    message: str,
) -> None:
    async with AsyncSessionMaker() as session:
        ingest = await session.get(IngestFile, ingest_id)
        if ingest is None:
            return
        ingest.status = "failed"
        ingest.season_id = prepared.season_id
        ingest.sheet_count = prepared.report.sheet_count
        ingest.row_count = prepared.report.row_count
        ingest.inserted_row_count = 0
        ingest.suspected_duplicate_count = prepared.report.suspected_duplicate_count
        ingest.finished_at = _now()
        ingest.quality_report = decimal_json(prepared.report)
        ingest.error_message = _sanitize_error_message(message)
        await session.commit()


async def _mark_ingest_completed(ingest_id: int, prepared: PreparedImport) -> None:
    async with AsyncSessionMaker() as session:
        ingest = await session.get(IngestFile, ingest_id)
        if ingest is None:
            raise ImportFatalError(f"Missing ingest_file id {ingest_id} after raw import")
        ingest.status = "completed"
        ingest.season_id = prepared.season_id
        ingest.sheet_count = prepared.report.sheet_count
        ingest.row_count = prepared.report.row_count
        ingest.inserted_row_count = len(prepared.rows)
        ingest.suspected_duplicate_count = prepared.report.suspected_duplicate_count
        ingest.finished_at = _now()
        ingest.quality_report = decimal_json(
            replace(prepared.report, inserted_row_count=len(prepared.rows))
        )
        ingest.error_message = None
        await session.commit()


async def dry_run_source(
    session: AsyncSession,
    source: SourceSpec,
    config: ImportConfig,
    base_dir: Path,
) -> ImportResult:
    path = _source_path(source, base_dir)
    if not path.exists():
        raise ImportFatalError(f"Source file not found: {source.path}")
    digest = file_sha256(path)
    try:
        prepared = await _prepare_file(session, source, config, base_dir)
    except ImportFatalError as exc:
        report = exc.report or _empty_report(source, path, digest)
        return _failed_result(source, digest, report, str(exc))
    report = replace(prepared.report, inserted_row_count=0, row_count=len(prepared.rows))
    status = "failed" if _report_has_fatal_errors(report) else "dry_run"
    return ImportResult(
        source_path=str(source.path),
        file_sha256=prepared.file_sha256,
        status=status,
        inserted_row_count=0,
        report=report,
    )


async def import_source(
    session: AsyncSession,
    source: SourceSpec,
    config: ImportConfig,
    base_dir: Path,
) -> ImportResult:
    path = _source_path(source, base_dir)
    if not path.exists():
        raise ImportFatalError(f"Source file not found: {source.path}")
    digest = file_sha256(path)
    existing_ingest = await _ingest_by_sha(session, digest)
    if existing_ingest is not None:
        report = _empty_report(source, path, digest)
        if existing_ingest.status == "completed":
            return _warning_result(source, digest, "skipped", report)
        if existing_ingest.status == "running":
            return _warning_result(source, digest, "running", report)
    try:
        prepared = await _prepare_file(session, source, config, base_dir)
    except ImportFatalError as exc:
        report = exc.report or _empty_report(source, path, digest)
        failed_prepared = PreparedImport(
            path=path,
            file_sha256=digest,
            season_id=None,
            rows=[],
            report=report,
        )
        ingest = await _acquire_ingest_record(
            source,
            config,
            failed_prepared,
        )
        if ingest.action not in {"completed", "running"}:
            await _mark_ingest_failed(ingest.ingest.id, failed_prepared, str(exc))
        return _failed_result(source, digest, report, str(exc))

    ingest = await _acquire_ingest_record(source, config, prepared)
    if ingest.action == "completed":
        return _warning_result(source, prepared.file_sha256, "skipped", prepared.report)
    if ingest.action == "running":
        return _warning_result(source, prepared.file_sha256, "running", prepared.report)

    if _report_has_fatal_errors(prepared.report):
        await _mark_ingest_failed(
            ingest.ingest.id,
            prepared,
            "; ".join(prepared.report.errors),
        )
        return _failed_result(
            source,
            prepared.file_sha256,
            prepared.report,
            "; ".join(prepared.report.errors),
        )

    if prepared.season_id is None:
        await _mark_ingest_failed(
            ingest.ingest.id,
            prepared,
            f"Missing season code: {source.season_code}",
        )
        return _failed_result(
            source,
            prepared.file_sha256,
            prepared.report,
            f"Missing season code: {source.season_code}",
        )

    try:
        async with AsyncSessionMaker() as write_session:
            write_session.add_all(
                [_row_to_model(row, ingest.ingest.id, prepared.season_id) for row in prepared.rows]
            )
            await write_session.commit()
    except IntegrityError:
        conflict_message = (
            f"Import failed because of a database uniqueness conflict for {source.path}"
        )
        await _mark_ingest_failed(ingest.ingest.id, prepared, conflict_message)
        return _failed_result(source, prepared.file_sha256, prepared.report, conflict_message)
    except Exception as exc:
        await _mark_ingest_failed(ingest.ingest.id, prepared, str(exc))
        raise

    await _mark_ingest_completed(ingest.ingest.id, prepared)
    return ImportResult(
        source_path=str(source.path),
        file_sha256=prepared.file_sha256,
        status="completed",
        inserted_row_count=len(prepared.rows),
        report=replace(
            prepared.report,
            inserted_row_count=len(prepared.rows),
            row_count=len(prepared.rows),
        ),
    )


async def count_raw_rows(session: AsyncSession) -> int:
    return int(
        (await session.execute(select(func.count()).select_from(FactReceiptRaw))).scalar_one()
    )


async def count_ingest_files(session: AsyncSession) -> int:
    return int((await session.execute(select(func.count()).select_from(IngestFile))).scalar_one())
