from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

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


class ImportFatalError(RuntimeError):
    pass


async def _season_id(session: AsyncSession, season_code: str) -> int:
    season = await session.scalar(select(Season).where(Season.code == season_code))
    if season is None:
        raise ImportFatalError(f"Missing season code: {season_code}")
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
) -> tuple[str, int, list[ProcessedRow], FileReport]:
    path = source.path if source.path.is_absolute() else base_dir / source.path
    if not path.exists():
        raise ImportFatalError(f"Source file not found: {source.path}")
    digest = file_sha256(path)
    season_id = await _season_id(session, source.season_code)
    factory_map, variety_map, grade_map = await _master_maps(session)
    try:
        parsed_rows, parser_stats = parse_workbook(path, config.rules, source.header_row)
    except HeaderError as exc:
        raise ImportFatalError(str(exc)) from exc
    rows, report = process_rows(
        rows=parsed_rows,
        source=source,
        file_sha256=digest,
        config=config,
        season_id=season_id,
        factory_ids_by_name=factory_map,
        variety_ids_by_name=variety_map,
        grade_ids_by_code=grade_map,
    )
    report.sheet_count = int(parser_stats["sheet_count"])
    for sheet_report in report.sheet_reports:
        sheet_report.physical_row_count = parser_stats["physical_row_count"]
        sheet_report.blank_row_count = parser_stats["blank_row_count"]
    return digest, season_id, rows, report


async def dry_run_source(
    session: AsyncSession,
    source: SourceSpec,
    config: ImportConfig,
    base_dir: Path,
) -> ImportResult:
    digest, _season_id_value, rows, report = await _prepare_file(session, source, config, base_dir)
    return ImportResult(
        source_path=str(source.path),
        file_sha256=digest,
        status="dry_run",
        inserted_row_count=0,
        report=replace(report, inserted_row_count=0, row_count=len(rows)),
    )


async def import_source(
    session: AsyncSession,
    source: SourceSpec,
    config: ImportConfig,
    base_dir: Path,
) -> ImportResult:
    digest, season_id, rows, report = await _prepare_file(session, source, config, base_dir)
    existing = await session.scalar(select(IngestFile).where(IngestFile.file_sha256 == digest))
    if existing is not None and existing.status == "completed":
        return ImportResult(
            source_path=str(source.path),
            file_sha256=digest,
            status="skipped",
            inserted_row_count=0,
            report=replace(report, inserted_row_count=0, row_count=len(rows)),
        )

    ingest = IngestFile(
        file_name=source.path.name,
        source_path=str(source.path),
        file_sha256=digest,
        season_id=season_id,
        status="running",
        sheet_count=report.sheet_count,
        row_count=len(rows),
        inserted_row_count=0,
        suspected_duplicate_count=report.suspected_duplicate_count,
        config_hash=config.config_hash,
        config_snapshot=decimal_json(config.snapshot),
        quality_report={},
    )
    session.add(ingest)
    try:
        await session.flush()
        session.add_all([_row_to_model(row, ingest.id, season_id) for row in rows])
        ingest.status = "completed"
        ingest.inserted_row_count = len(rows)
        ingest.quality_report = decimal_json(
            replace(report, inserted_row_count=len(rows), row_count=len(rows))
        )
        ingest.finished_at = await session.scalar(select(func.now()))
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ImportFatalError(
            f"Import failed because of a database uniqueness conflict for {source.path}"
        ) from exc
    except Exception:
        await session.rollback()
        raise
    return ImportResult(
        source_path=str(source.path),
        file_sha256=digest,
        status="completed",
        inserted_row_count=len(rows),
        report=replace(report, inserted_row_count=len(rows), row_count=len(rows)),
    )


async def count_raw_rows(session: AsyncSession) -> int:
    return int(
        (await session.execute(select(func.count()).select_from(FactReceiptRaw))).scalar_one()
    )


async def count_ingest_files(session: AsyncSession) -> int:
    return int((await session.execute(select(func.count()).select_from(IngestFile))).scalar_one())
