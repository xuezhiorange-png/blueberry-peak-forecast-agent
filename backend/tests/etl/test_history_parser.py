from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
import xlwt

from backend.app.etl.history.parser import HeaderError, parse_workbook
from backend.app.etl.history.schemas import EXPECTED_HEADERS, ImportRules


def rules() -> ImportRules:
    return ImportRules(
        version="test",
        valid_months={1, 2, 3, 4},
        excluded_grades={"普鲜", "普青", "普冻", "废果"},
        excluded_factories={"巴松加工厂"},
        deduplicate_suspected_business_rows_in_curated=True,
        date_formats=["%Y-%m-%d", "%Y/%m/%d"],
        variety_prefixes_to_remove=["蓝莓原果"],
        empty_strings={"", "-"},
        max_issue_examples=50,
    )


def write_xls(path: Path, *, missing_header: bool = False) -> None:
    workbook = xlwt.Workbook()
    date_style = xlwt.easyxf(num_format_str="YYYY-MM-DD")
    for sheet_name in ["一月", "二月"]:
        sheet = workbook.add_sheet(sheet_name)
        headers = list(EXPECTED_HEADERS)
        if missing_header:
            headers.remove("加工厂")
        for col, header in enumerate(headers):
            sheet.write(0, col, header)
        rows = [
            [
                datetime(2026, 1, 2),
                "链路A",
                " 农场 A ",
                "分场A",
                "蓝莓原果 Dx ",
                "优果",
                12.5,
                " 工厂A ",
            ],
            ["2026/05/01", "链路B", "农场B", "分场B", "品种B", "普鲜", "0", "巴松加工厂"],
            ["", "", "", "", "", "", "", ""],
            ["坏日期", "链路C", "农场C", "分场C", "品种C", "优果", "-3.25", "未知厂"],
        ]
        for row_index, row in enumerate(rows, start=1):
            for col, value in enumerate(row):
                if isinstance(value, datetime):
                    sheet.write(row_index, col, value, date_style)
                else:
                    sheet.write(row_index, col, value)
    workbook.save(str(path))


def test_parse_legacy_xls_multiple_sheets_dates_weights_and_blank_rows(tmp_path: Path) -> None:
    path = tmp_path / "fixture.xls"
    write_xls(path)

    rows, stats = parse_workbook(path, rules())

    assert stats["sheet_count"] == 2
    assert stats["blank_row_count"] == 2
    assert len(rows) == 6
    assert rows[0].receipt_date == date(2026, 1, 2)
    assert rows[0].weight_kg == Decimal("12.5")
    assert rows[1].receipt_date == date(2026, 5, 1)
    assert rows[1].weight_kg == Decimal("0")
    assert "invalid_date" in rows[2].parse_errors
    assert rows[2].weight_kg == Decimal("-3.25")


def test_parse_legacy_xls_rejects_missing_header(tmp_path: Path) -> None:
    path = tmp_path / "bad-header.xls"
    write_xls(path, missing_header=True)

    with pytest.raises(HeaderError):
        parse_workbook(path, rules())
