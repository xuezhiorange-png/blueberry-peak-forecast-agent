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


class ExpectedSheetsError(HeaderError):
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


def _find_header_row(
    sheet: xlrd.sheet.Sheet,
    configured_header_row: int | None,
    header_aliases: dict[str, str] | None = None,
) -> int:
    if configured_header_row is not None:
        return configured_header_row
    expected = set(EXPECTED_HEADERS)
    for row_index in range(sheet.nrows):
        values = {
            _apply_header_alias(sheet.cell_value(row_index, col_index), header_aliases or {})
            for col_index in range(sheet.ncols)
        }
        if expected.issubset(values):
            return row_index
    raise HeaderError(f"Header row not found in sheet {sheet.name}")


def _apply_header_alias(raw_header: Any, aliases: dict[str, str]) -> str | None:
    normalized = normalize_text(raw_header)
    if normalized is None and "<blank>" in aliases:
        return aliases["<blank>"]
    if normalized is None:
        return None
    return aliases.get(normalized, normalized)


def _header_map(
    sheet: xlrd.sheet.Sheet,
    header_row: int,
    file_name: str,
    header_aliases: dict[str, str] | None = None,
) -> dict[str, int]:
    aliases = header_aliases or {}
    values = [
        _apply_header_alias(sheet.cell_value(header_row, col_index), aliases)
        for col_index in range(sheet.ncols)
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


def _validate_expected_sheets(
    workbook: xlrd.book.Book, expected_sheets: list[str], behavior: str
) -> dict[str, Any]:
    actual_sheets = [sheet.name for sheet in workbook.sheets()]
    missing = [sheet for sheet in expected_sheets if sheet not in actual_sheets]
    unexpected = [sheet for sheet in actual_sheets if sheet not in expected_sheets]
    warnings: list[str] = []
    if expected_sheets and (missing or unexpected):
        message = (
            f"Unexpected sheets in workbook; actual={actual_sheets}; "
            f"missing={missing}; unexpected={unexpected}"
        )
        if behavior == "fatal":
            raise ExpectedSheetsError(message)
        warnings.append(message)
    return {
        "actual_sheets": actual_sheets,
        "missing_expected_sheets": missing,
        "unexpected_sheets": unexpected,
        "warnings": warnings,
    }


def parse_workbook(
    path: Path,
    rules: ImportRules,
    header_row: int | None = None,
    expected_sheets: list[str] | None = None,
    expected_sheets_behavior: str = "warning",
    header_aliases: dict[str, str] | None = None,
) -> tuple[list[ParsedRow], dict[str, Any]]:
    workbook = xlrd.open_workbook(path)
    parsed_rows: list[ParsedRow] = []
    sheet_check = _validate_expected_sheets(
        workbook,
        expected_sheets=expected_sheets or [],
        behavior=expected_sheets_behavior,
    )
    stats: dict[str, Any] = {
        "sheet_count": len(workbook.sheets()),
        "actual_sheets": sheet_check["actual_sheets"],
        "missing_expected_sheets": sheet_check["missing_expected_sheets"],
        "unexpected_sheets": sheet_check["unexpected_sheets"],
        "warnings": sheet_check["warnings"],
        "sheet_stats": [],
    }
    for sheet in workbook.sheets():
        header_index = _find_header_row(sheet, header_row, header_aliases)
        columns = _header_map(sheet, header_index, path.name, header_aliases)
        sheet_physical_row_count = 0
        sheet_blank_row_count = 0
        for row_index in range(header_index + 1, sheet.nrows):
            sheet_physical_row_count += 1
            row_values = [
                _cell_raw_value(sheet.cell(row_index, columns[header]), workbook.datemode)
                for header in EXPECTED_HEADERS
            ]
            if _is_blank_row(row_values, rules):
                sheet_blank_row_count += 1
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
        stats["sheet_stats"].append(
            {
                "sheet_name": sheet.name,
                "physical_row_count": sheet_physical_row_count,
                "blank_row_count": sheet_blank_row_count,
                "data_row_count": sheet_physical_row_count - sheet_blank_row_count,
            }
        )
    return parsed_rows, stats
