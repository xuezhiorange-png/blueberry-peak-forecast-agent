from datetime import datetime
from pathlib import Path

import pytest
import xlwt
from sqlalchemy import select

from backend.app.db.session import AsyncSessionMaker
from backend.app.etl.history.config import file_sha256, load_import_config
from backend.app.etl.history.importer import (
    count_ingest_files,
    count_raw_rows,
    dry_run_source,
    import_source,
)
from backend.app.models.historical_import import FactReceiptRaw, IngestFile
from backend.app.models.master_data import Factory, Grade, Season, Variety

pytestmark = pytest.mark.integration


def _require_postgres() -> None:
    import os

    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("set RUN_POSTGRES_INTEGRATION=1 when PostgreSQL is available")


def _write_xls(
    path: Path,
    *,
    duplicate_across_files: bool = False,
    link_name: str = "链路A",
) -> None:
    workbook = xlwt.Workbook()
    date_style = xlwt.easyxf(num_format_str="YYYY-MM-DD")
    sheet1 = workbook.add_sheet("SheetA")
    sheet2 = workbook.add_sheet("SheetB")
    headers = ["时间", "链路", "农场", "分场", "品种", "果径", "入库公斤数", "加工厂"]
    rows = [
        [datetime(2026, 1, 2), link_name, "农场A", "分场A", "蓝莓原果Dx", "优果", 10, "工厂A"],
        ["2026-05-01", "链路B", "农场B", "分场B", "品种B", "普鲜", 5, "巴松加工厂"],
        ["坏日期", "链路C", "农场C", "分场C", "未知品种", "优果", -1, "未知厂"],
    ]
    if duplicate_across_files:
        rows = [
            [datetime(2026, 1, 2), link_name, "农场A", "分场A", "蓝莓原果Dx", "优果", 10, "工厂A"],
        ]
    for sheet in [sheet1, sheet2]:
        for col, header in enumerate(headers):
            sheet.write(0, col, header)
        for row_index, row in enumerate(rows, start=1):
            for col, value in enumerate(row):
                if isinstance(value, datetime):
                    sheet.write(row_index, col, value, date_style)
                else:
                    sheet.write(row_index, col, value)
    workbook.save(str(path))


def _write_invalid_header_xls(path: Path) -> None:
    workbook = xlwt.Workbook()
    sheet = workbook.add_sheet("SheetA")
    headers = ["时间", "链路", "农场", "分场", "品种", "果径", "错误列", "加工厂"]
    for col, header in enumerate(headers):
        sheet.write(0, col, header)
    sheet.write(1, 0, "2026-01-01")
    workbook.save(str(path))


async def _seed_master_data(*, with_season: bool = True) -> None:
    async with AsyncSessionMaker() as session:
        rows = [
            Factory(code="factory-a", name="工厂A", active=True),
            Factory(code="bashong", name="巴松加工厂", active=True),
            Variety(code="DX", name="Dx"),
            Grade(code="优果", is_analysis_eligible_default=True),
            Grade(code="普鲜", is_analysis_eligible_default=False),
        ]
        if with_season:
            rows.insert(
                0,
                Season(
                    code="2025-2026",
                    start_date=datetime(2026, 1, 1),
                    end_date=datetime(2026, 4, 30),
                ),
            )
        session.add_all(rows)
        await session.commit()


def _write_config_files(
    base: Path,
    xls_path: Path,
    *,
    invalid_date_limit: int | None = None,
    deduplicate_in_curated: bool = True,
) -> tuple[Path, Path, Path, Path]:
    configs = base / "configs"
    configs.mkdir(parents=True)
    manifest = configs / "source_manifest.yaml"
    rules = configs / "import_rules.yaml"
    factory_aliases = configs / "factory_aliases.yaml"
    variety_aliases = configs / "variety_aliases.yaml"
    manifest.write_text(
        f"""
version: test
sources:
  - path: "{xls_path.name}"
    source_name: "synthetic"
    season_code: "2025-2026"
    enabled: true
    expected_sheets: []
    expected_sheets_behavior: "warning"
    header_row: null
    description: "synthetic fixture"
""",
        encoding="utf-8",
    )
    invalid_date_threshold = (
        f"  max_invalid_date_count: {invalid_date_limit}\n"
        if invalid_date_limit is not None
        else "  max_invalid_date_count: 999999\n"
    )
    rules.write_text(
        f"""
version: test
valid_months: [1, 2, 3, 4]
excluded_grades: ["普鲜", "普青", "普冻", "废果"]
excluded_factories: ["巴松加工厂"]
deduplicate_suspected_business_rows_in_curated: {"true" if deduplicate_in_curated else "false"}
date_formats: ["%Y-%m-%d", "%Y/%m/%d"]
variety_prefixes_to_remove: ["蓝莓原果"]
allow_unknown_factory_in_analysis: false
allow_unknown_variety_in_analysis: false
allow_empty_factory_in_analysis: false
allow_empty_variety_in_analysis: false
empty_values:
  strings: ["", "-"]
fatal_quality_thresholds:
{invalid_date_threshold}report:
  max_issue_examples: 50
""",
        encoding="utf-8",
    )
    factory_aliases.write_text(
        """
version: test
aliases:
  工厂A: 工厂A
  巴松加工厂: 巴松加工厂
""",
        encoding="utf-8",
    )
    variety_aliases.write_text(
        """
version: test
remove_prefixes: ["蓝莓原果"]
aliases:
  Dx: Dx
""",
        encoding="utf-8",
    )
    return manifest, rules, factory_aliases, variety_aliases


def _load_config(
    base: Path,
    xls_path: Path,
    *,
    invalid_date_limit: int | None = None,
    deduplicate_in_curated: bool = True,
):
    manifest, rules, factory_aliases, variety_aliases = _write_config_files(
        base,
        xls_path,
        invalid_date_limit=invalid_date_limit,
        deduplicate_in_curated=deduplicate_in_curated,
    )
    return load_import_config(manifest, rules, factory_aliases, variety_aliases)


@pytest.mark.asyncio
async def test_dry_run_does_not_write_and_preserves_source_sha(tmp_path: Path) -> None:
    _require_postgres()
    await _seed_master_data()
    xls_path = tmp_path / "synthetic.xls"
    _write_xls(xls_path)
    before_sha = file_sha256(xls_path)
    config = _load_config(tmp_path, xls_path)

    async with AsyncSessionMaker() as session:
        before_raw = await count_raw_rows(session)
        before_ingest = await count_ingest_files(session)
        result = await dry_run_source(session, config.sources[0], config, tmp_path)
        after_raw = await count_raw_rows(session)
        after_ingest = await count_ingest_files(session)

    assert result.status == "dry_run"
    assert result.report.sheet_reports[0].physical_row_count == 3
    assert result.report.sheet_reports[1].physical_row_count == 3
    assert before_raw == after_raw == 0
    assert before_ingest == after_ingest == 0
    assert file_sha256(xls_path) == before_sha


@pytest.mark.asyncio
async def test_failed_import_is_recorded_and_can_retry_successfully(tmp_path: Path) -> None:
    _require_postgres()
    xls_path = tmp_path / "synthetic.xls"
    _write_xls(xls_path)
    config = _load_config(tmp_path, xls_path)

    async with AsyncSessionMaker() as session:
        failed = await import_source(session, config.sources[0], config, tmp_path)
        assert failed.status == "failed"
        assert await count_raw_rows(session) == 0
        assert await count_ingest_files(session) == 1
        ingest = await session.scalar(
            select(IngestFile).where(IngestFile.file_sha256 == failed.file_sha256)
        )
        assert ingest is not None
        assert ingest.status == "failed"
        assert ingest.error_message

    await _seed_master_data(with_season=True)

    async with AsyncSessionMaker() as session:
        retried = await import_source(session, config.sources[0], config, tmp_path)
        ingest = await session.scalar(
            select(IngestFile).where(IngestFile.file_sha256 == retried.file_sha256)
        )
        assert retried.status == "completed"
        assert retried.inserted_row_count == 6
        assert await count_raw_rows(session) == 6
        assert await count_ingest_files(session) == 1
        assert ingest is not None
        assert ingest.status == "completed"


@pytest.mark.asyncio
async def test_formal_import_is_idempotent_and_keeps_first_duplicate_row(tmp_path: Path) -> None:
    _require_postgres()
    await _seed_master_data()
    xls_path = tmp_path / "synthetic.xls"
    _write_xls(xls_path)
    config = _load_config(tmp_path, xls_path)

    async with AsyncSessionMaker() as session:
        first = await import_source(session, config.sources[0], config, tmp_path)
        raw_count_after_first = await count_raw_rows(session)
        second = await import_source(session, config.sources[0], config, tmp_path)
        raw_count_after_second = await count_raw_rows(session)
        rows = (await session.scalars(select(FactReceiptRaw).order_by(FactReceiptRaw.id))).all()
        ingest = await session.scalar(
            select(IngestFile).where(IngestFile.file_sha256 == first.file_sha256)
        )

    assert first.status == "completed"
    assert first.report.cross_sheet_duplicate_count == 3
    assert second.status == "skipped"
    assert second.inserted_row_count == 0
    assert raw_count_after_first == raw_count_after_second == 6
    assert ingest is not None
    assert ingest.quality_report["row_count"] == 6
    assert rows[0].is_suspected_duplicate is False
    assert rows[0].is_analysis_eligible is True
    duplicate_rows = [row for row in rows if row.is_suspected_duplicate]
    assert duplicate_rows
    assert all("suspected_duplicate" in row.exclusion_reasons for row in duplicate_rows)
    assert any(not row.is_factory_known and not row.is_analysis_eligible for row in rows)
    assert any(not row.is_variety_known and not row.is_analysis_eligible for row in rows)


@pytest.mark.asyncio
async def test_cross_file_duplicates_are_counted_against_prior_imports(tmp_path: Path) -> None:
    _require_postgres()
    await _seed_master_data()
    first_xls = tmp_path / "synthetic-a.xls"
    second_xls = tmp_path / "synthetic-b.xls"
    _write_xls(first_xls, duplicate_across_files=True, link_name="链路A")
    _write_xls(second_xls, duplicate_across_files=True, link_name="链路B")
    first_config = _load_config(tmp_path / "cfg-a", first_xls)
    second_config = _load_config(tmp_path / "cfg-b", second_xls)

    async with AsyncSessionMaker() as session:
        first = await import_source(
            session,
            first_config.sources[0],
            first_config,
            first_xls.parent,
        )
        second = await import_source(
            session,
            second_config.sources[0],
            second_config,
            second_xls.parent,
        )
        second_rows = (
            await session.scalars(
                select(FactReceiptRaw)
                .join(IngestFile, FactReceiptRaw.ingest_file_id == IngestFile.id)
                .where(IngestFile.file_sha256 == second.file_sha256)
                .order_by(FactReceiptRaw.id)
            )
        ).all()

    assert first.status == "completed"
    assert second.status == "completed"
    assert second.report.cross_file_duplicate_count == 2
    assert second.report.cross_file_duplicate_examples
    assert second_rows
    assert all(row.is_suspected_duplicate for row in second_rows)
    assert all("suspected_duplicate" in row.exclusion_reasons for row in second_rows)
    assert all(row.is_analysis_eligible is False for row in second_rows)


@pytest.mark.asyncio
async def test_cross_file_duplicates_can_be_marked_without_curated_deduplication(
    tmp_path: Path,
) -> None:
    _require_postgres()
    await _seed_master_data()
    first_xls = tmp_path / "synthetic-a.xls"
    second_xls = tmp_path / "synthetic-b.xls"
    _write_xls(first_xls, duplicate_across_files=True, link_name="链路A")
    _write_xls(second_xls, duplicate_across_files=True, link_name="链路B")
    first_config = _load_config(tmp_path / "cfg-a", first_xls)
    second_config = _load_config(
        tmp_path / "cfg-b",
        second_xls,
        deduplicate_in_curated=False,
    )

    async with AsyncSessionMaker() as session:
        first = await import_source(
            session,
            first_config.sources[0],
            first_config,
            first_xls.parent,
        )
        second = await import_source(
            session,
            second_config.sources[0],
            second_config,
            second_xls.parent,
        )
        second_rows = (
            await session.scalars(
                select(FactReceiptRaw)
                .join(IngestFile, FactReceiptRaw.ingest_file_id == IngestFile.id)
                .where(IngestFile.file_sha256 == second.file_sha256)
                .order_by(FactReceiptRaw.id)
            )
        ).all()

    assert first.status == "completed"
    assert second.status == "completed"
    assert second.report.cross_file_duplicate_count == 2
    assert second_rows
    assert all(row.is_suspected_duplicate for row in second_rows)
    assert all("suspected_duplicate" not in row.exclusion_reasons for row in second_rows)
    assert all(row.is_analysis_eligible is True for row in second_rows)


@pytest.mark.asyncio
async def test_fatal_quality_thresholds_fail_import_without_writing_raw(tmp_path: Path) -> None:
    _require_postgres()
    await _seed_master_data()
    xls_path = tmp_path / "synthetic.xls"
    _write_xls(xls_path)
    config = _load_config(tmp_path, xls_path, invalid_date_limit=0)

    async with AsyncSessionMaker() as session:
        result = await import_source(session, config.sources[0], config, tmp_path)
        ingest = await session.scalar(
            select(IngestFile).where(IngestFile.file_sha256 == result.file_sha256)
        )

    assert result.status == "failed"
    assert any("invalid_date_count" in error for error in result.report.errors)
    assert ingest is not None
    assert ingest.status == "failed"
    assert ingest.inserted_row_count == 0


@pytest.mark.asyncio
async def test_completed_file_skips_before_reparsing_workbook(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _require_postgres()
    await _seed_master_data()
    xls_path = tmp_path / "synthetic.xls"
    _write_xls(xls_path)
    config = _load_config(tmp_path, xls_path)

    call_count = 0
    original = import_source.__globals__["parse_workbook"]

    def spy_parse_workbook(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return original(*args, **kwargs)

    monkeypatch.setitem(import_source.__globals__, "parse_workbook", spy_parse_workbook)

    async with AsyncSessionMaker() as session:
        first = await import_source(session, config.sources[0], config, tmp_path)
        second = await import_source(session, config.sources[0], config, tmp_path)

    assert first.status == "completed"
    assert second.status == "skipped"
    assert call_count == 1


@pytest.mark.asyncio
async def test_header_failure_persists_quality_report_errors(tmp_path: Path) -> None:
    _require_postgres()
    await _seed_master_data()
    xls_path = tmp_path / "invalid-header.xls"
    _write_invalid_header_xls(xls_path)
    config = _load_config(tmp_path, xls_path)

    async with AsyncSessionMaker() as session:
        result = await import_source(session, config.sources[0], config, tmp_path)
        ingest = await session.scalar(
            select(IngestFile).where(IngestFile.file_sha256 == result.file_sha256)
        )

    assert result.status == "failed"
    assert ingest is not None
    assert ingest.status == "failed"
    assert ingest.quality_report["errors"]
    error = ingest.quality_report["errors"][0]
    assert "header" in error.lower()
    assert "SheetA" in error
