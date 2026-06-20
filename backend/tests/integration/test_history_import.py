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


def _write_xls(path: Path) -> None:
    workbook = xlwt.Workbook()
    date_style = xlwt.easyxf(num_format_str="YYYY-MM-DD")
    sheet1 = workbook.add_sheet("SheetA")
    sheet2 = workbook.add_sheet("SheetB")
    headers = ["时间", "链路", "农场", "分场", "品种", "果径", "入库公斤数", "加工厂"]
    rows = [
        [datetime(2026, 1, 2), "链路A", "农场A", "分场A", "蓝莓原果Dx", "优果", 10, "工厂A"],
        ["2026-05-01", "链路B", "农场B", "分场B", "品种B", "普鲜", 5, "巴松加工厂"],
        ["坏日期", "链路C", "农场C", "分场C", "未知品种", "优果", -1, "未知厂"],
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


async def _seed_master_data() -> None:
    async with AsyncSessionMaker() as session:
        session.add_all(
            [
                Season(
                    code="2025-2026",
                    start_date=datetime(2026, 1, 1),
                    end_date=datetime(2026, 4, 30),
                ),
                Factory(code="factory-a", name="工厂A", active=True),
                Factory(code="bashong", name="巴松加工厂", active=True),
                Variety(code="DX", name="Dx"),
                Grade(code="优果", is_analysis_eligible_default=True),
                Grade(code="普鲜", is_analysis_eligible_default=False),
            ]
        )
        await session.commit()


def _write_config_files(base: Path, xls_path: Path) -> tuple[Path, Path, Path, Path]:
    configs = base / "configs"
    configs.mkdir()
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
    header_row: null
    description: "synthetic fixture"
""",
        encoding="utf-8",
    )
    rules.write_text(
        """
version: test
valid_months: [1, 2, 3, 4]
excluded_grades: ["普鲜", "普青", "普冻", "废果"]
excluded_factories: ["巴松加工厂"]
deduplicate_suspected_business_rows_in_curated: true
date_formats: ["%Y-%m-%d", "%Y/%m/%d"]
variety_prefixes_to_remove: ["蓝莓原果"]
empty_values:
  strings: ["", "-"]
report:
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


async def _load_config(base: Path, xls_path: Path):
    manifest, rules, factory_aliases, variety_aliases = _write_config_files(base, xls_path)
    return load_import_config(manifest, rules, factory_aliases, variety_aliases)


@pytest.mark.asyncio
async def test_dry_run_does_not_write_and_preserves_source_sha(tmp_path: Path) -> None:
    _require_postgres()
    await _seed_master_data()
    xls_path = tmp_path / "synthetic.xls"
    _write_xls(xls_path)
    before_sha = file_sha256(xls_path)
    config = await _load_config(tmp_path, xls_path)

    async with AsyncSessionMaker() as session:
        before_raw = await count_raw_rows(session)
        before_ingest = await count_ingest_files(session)
        result = await dry_run_source(session, config.sources[0], config, tmp_path)
        after_raw = await count_raw_rows(session)
        after_ingest = await count_ingest_files(session)

    assert result.status == "dry_run"
    assert before_raw == after_raw == 0
    assert before_ingest == after_ingest == 0
    assert file_sha256(xls_path) == before_sha


@pytest.mark.asyncio
async def test_formal_import_is_idempotent_and_raw_keeps_invalid_rows(tmp_path: Path) -> None:
    _require_postgres()
    await _seed_master_data()
    xls_path = tmp_path / "synthetic.xls"
    _write_xls(xls_path)
    config = await _load_config(tmp_path, xls_path)

    async with AsyncSessionMaker() as session:
        first = await import_source(session, config.sources[0], config, tmp_path)
        raw_count_after_first = await count_raw_rows(session)
        second = await import_source(session, config.sources[0], config, tmp_path)
        raw_count_after_second = await count_raw_rows(session)
        ingest = await session.scalar(
            select(IngestFile).where(IngestFile.file_sha256 == first.file_sha256)
        )
        rows = (await session.scalars(select(FactReceiptRaw))).all()

    assert first.status == "completed"
    assert first.inserted_row_count == 6
    assert second.status == "skipped"
    assert second.inserted_row_count == 0
    assert raw_count_after_first == raw_count_after_second == 6
    assert ingest is not None
    assert ingest.quality_report["row_count"] == 6
    assert any(row.weight_kg is not None and row.weight_kg < 0 for row in rows)
    assert any("invalid_date" in row.parse_errors for row in rows)
    assert any(not row.is_factory_known for row in rows)
    assert any(not row.is_variety_known for row in rows)


@pytest.mark.asyncio
async def test_missing_season_fails_without_writing_rows(tmp_path: Path) -> None:
    _require_postgres()
    xls_path = tmp_path / "synthetic.xls"
    _write_xls(xls_path)
    config = await _load_config(tmp_path, xls_path)

    async with AsyncSessionMaker() as session:
        with pytest.raises(Exception, match="Missing season code"):
            await import_source(session, config.sources[0], config, tmp_path)
        assert await count_raw_rows(session) == 0
        assert await count_ingest_files(session) == 0
