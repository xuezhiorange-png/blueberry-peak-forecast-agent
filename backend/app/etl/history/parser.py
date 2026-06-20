from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import xlrd
from xlrd.sheet import Cell

from backend.app.etl.history.normalizer import normalize_text
from backend.app.etl.history.schemas import EXPECTED_HEADERS, ImportRules, ParsedRow


class HeaderError(ValueError):
    pass


def _cell_raw_value(cell: Cell, datemode: int) -> Any:
    if cell.ctype == xlrd.XL_CELL_DATE:
        try:
            return xlrd.xldate_as_datetime(cell.value, datemode).date().isoformat()
        except (ValueError, OverflowError):
            return cell.value
    if isinstance(cell.value, float) and cell.value.is_integer():
        return int(cell.value)
    return cell.value


def _raw_to_text(value: Any) -> str | None:
    normalized = normalize_text(value)
    return normalized


def parse_date_value(
    value: Any, cell: Cell | None, datemode: int, rules: ImportRules
) -> tuple[date | None, list[str]]:
    if cell is not None and cell.ctype == xlrd.XL_CELL_DATE:
        try:
            return xlrd.xldate_as_datetime(cell.value, datemode).date(), []
        except (ValueError, OverflowError):
            return None, ["invalid_date"]
    if value is None or normalize_text(value) in rules.empty_strings:
        return None, ["empty_date"]
    if isinstance(value, datetime):
        return value.date(), []
    if isinstance(value, date):
        return value, []
    if isinstance(value, int | float):
        try:
            return xlrd.xldate_as_datetime(float(value), datemode).date(), []
        except (ValueError, OverflowError):
            return None, ["invalid_date"]
    text = normalize_text(value)
    if text is None or text in rules.empty_strings:
        return None, ["empty_date"]
    for fmt in rules.date_formats:
        try:
            return datetime.strptime(text, fmt).date(), []
        except ValueError:
            continue
    return None, ["invalid_date"]


def parse_weight_value(value: Any, rules: ImportRules) -> tuple[Decimal | None, list[str]]:
    if value is None or normalize_text(value) in rules.empty_strings:
        return None, ["empty_weight"]
    if isinstance(value, Decimal):
        return value, []
    text = normalize_text(value)
    if text is None or text in rules.empty_strings:
        return None, ["empty_weight"]
    try:
        return Decimal(text.replace(",", "")), []
    except (InvalidOperation, ValueError):
        return None, ["invalid_weight"]


def _is_blank_row(values: list[Any], rules: ImportRules) -> bool:
    for value in values:
        text = normalize_text(value)
        if text is not None and text not in rules.empty_strings:
            return False
    return True


def _find_header_row(sheet: xlrd.sheet.Sheet, configured_header_row: int | None) -> int:
    if configured_header_row is not None:
        return configured_header_row
    expected = set(EXPECTED_HEADERS)
    for row_index in range(sheet.nrows):
        values = {
            normalize_text(sheet.cell_value(row_index, col_index))
            for col_index in range(sheet.ncols)
        }
        if expected.issubset(values):
            return row_index
    raise HeaderError(f"Header row not found in sheet {sheet.name}")


def _header_map(sheet: xlrd.sheet.Sheet, header_row: int, file_name: str) -> dict[str, int]:
    values = [
        normalize_text(sheet.cell_value(header_row, col_index)) for col_index in range(sheet.ncols)
    ]
    duplicates = sorted(
        {value for value in values if value is not None and values.count(value) > 1}
    )
    missing = [header for header in EXPECTED_HEADERS if header not in values]
    if duplicates or missing:
        raise HeaderError(
            f"Invalid header in file={file_name} sheet={sheet.name}; missing={missing}; "
            f"duplicates={duplicates}; actual={values}"
        )
    return {header: values.index(header) for header in EXPECTED_HEADERS}


def parse_workbook(
    path: Path, rules: ImportRules, header_row: int | None = None
) -> tuple[list[ParsedRow], dict[str, int]]:
    workbook = xlrd.open_workbook(path)
    parsed_rows: list[ParsedRow] = []
    stats = {"sheet_count": len(workbook.sheets()), "physical_row_count": 0, "blank_row_count": 0}
    for sheet in workbook.sheets():
        header_index = _find_header_row(sheet, header_row)
        columns = _header_map(sheet, header_index, path.name)
        for row_index in range(header_index + 1, sheet.nrows):
            stats["physical_row_count"] += 1
            row_values = [
                _cell_raw_value(sheet.cell(row_index, columns[header]), workbook.datemode)
                for header in EXPECTED_HEADERS
            ]
            if _is_blank_row(row_values, rules):
                stats["blank_row_count"] += 1
                continue
            raw_payload = dict(zip(EXPECTED_HEADERS, row_values, strict=True))
            receipt_cell = sheet.cell(row_index, columns["时间"])
            receipt_date, date_errors = parse_date_value(
                raw_payload["时间"], receipt_cell, workbook.datemode, rules
            )
            weight_kg, weight_errors = parse_weight_value(raw_payload["入库公斤数"], rules)
            parsed_rows.append(
                ParsedRow(
                    source_sheet=sheet.name,
                    source_row_number=row_index + 1,
                    raw_payload=raw_payload,
                    receipt_date_raw=_raw_to_text(raw_payload["时间"]),
                    link_name_raw=_raw_to_text(raw_payload["链路"]),
                    farm_raw=_raw_to_text(raw_payload["农场"]),
                    subfarm_raw=_raw_to_text(raw_payload["分场"]),
                    variety_raw=_raw_to_text(raw_payload["品种"]),
                    grade_raw=_raw_to_text(raw_payload["果径"]),
                    weight_kg_raw=_raw_to_text(raw_payload["入库公斤数"]),
                    factory_raw=_raw_to_text(raw_payload["加工厂"]),
                    receipt_date=receipt_date,
                    weight_kg=weight_kg,
                    parse_errors=[*date_errors, *weight_errors],
                )
            )
    return parsed_rows, stats
