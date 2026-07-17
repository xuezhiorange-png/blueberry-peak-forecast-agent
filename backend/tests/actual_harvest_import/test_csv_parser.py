from __future__ import annotations

import csv
import io
from decimal import Decimal

import pytest

from backend.app.actual_harvest_import.enums import ActualHarvestValidationErrorCode
from backend.app.actual_harvest_import.errors import ActualHarvestValidationError
from backend.app.actual_harvest_import.spreadsheet_parser import (
    canonical_spreadsheet_headers,
    parse_csv,
)

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def _row(**overrides: str) -> dict[str, str]:
    values = {
        "external_logical_record_id": "logical-1",
        "external_revision_id": "revision-1",
        "source_system": "farm-picking-system",
        "external_batch_id": "batch-1",
        "harvest_business_date": "2026-03-01",
        "farm_code": "FARM-1",
        "subfarm_or_plot_code": "SUBFARM-1",
        "variety_code": "VARIETY-1",
        "actual_harvest_quantity_kg": "12.345678",
        "source_recorded_at": "",
        "source_recorded_at_authority_status": "MISSING",
        "source_recorded_at_authority_reference_or_null": "",
        "revision_number": "1",
        "record_status": "ACTIVE",
        "supersedes_external_revision_id": "",
        "season_code": "2026",
        "farm_timezone": "Asia/Shanghai",
        "revised_at": "",
        "finalized_at": "",
        "source_note": "蓝莓采摘记录",
    }
    values.update(overrides)
    return values


def _csv_bytes(rows: list[dict[str, str]], headers: list[str] | None = None) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    selected_headers = headers or list(canonical_spreadsheet_headers())
    writer.writerow(selected_headers)
    for row in rows:
        writer.writerow([row.get(header, "") for header in selected_headers])
    return output.getvalue().encode("utf-8")


def _assert_code(payload: bytes, code: ActualHarvestValidationErrorCode) -> None:
    with pytest.raises(ActualHarvestValidationError) as captured:
        parse_csv(payload)
    assert captured.value.code == code
    assert captured.value.details is not None
    assert "raw_row" not in captured.value.details


def test_valid_utf8_csv_normalizes_exact_decimal_and_provenance() -> None:
    result = parse_csv(_csv_bytes([_row()]))

    assert len(result.records) == 1
    record = result.records[0]
    assert record.actual_harvest_quantity_kg == Decimal("12.345678")
    assert record.source_row_number == 2
    assert record.source_sheet_name is None
    assert result.diagnostics == ()


def test_empty_rows_are_ignored_with_deterministic_diagnostic() -> None:
    payload = _csv_bytes([_row()]) + b",,,,,,,,,,,,,,,,,,,\n"

    result = parse_csv(payload)

    assert len(result.records) == 1
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].code == "CSV_EMPTY_ROW_IGNORED"
    assert result.diagnostics[0].source_row_number == 3


@pytest.mark.parametrize(
    ("headers", "code"),
    [
        (
            list(canonical_spreadsheet_headers())[1:],
            ActualHarvestValidationErrorCode.REQUIRED_FIELD_MISSING,
        ),
        (
            list(canonical_spreadsheet_headers()) + ["unknown_column"],
            ActualHarvestValidationErrorCode.UNKNOWN_FIELD,
        ),
        (
            [
                *canonical_spreadsheet_headers()[:2],
                canonical_spreadsheet_headers()[1],
                *canonical_spreadsheet_headers()[2:],
            ],
            ActualHarvestValidationErrorCode.CANONICAL_HEADER_DUPLICATE,
        ),
        (
            ["SOURCE_SYSTEM", *canonical_spreadsheet_headers()],
            ActualHarvestValidationErrorCode.CANONICAL_HEADER_COLLISION,
        ),
    ],
)
def test_header_policy_rejects_missing_unknown_duplicate_and_collision(
    headers: list[str], code: ActualHarvestValidationErrorCode
) -> None:
    _assert_code(_csv_bytes([_row()], headers=headers), code)


def test_server_generated_fields_cannot_be_supplied() -> None:
    headers = [*canonical_spreadsheet_headers(), "import_received_at"]
    _assert_code(
        _csv_bytes([_row(import_received_at="2026-01-01T00:00:00Z")], headers),
        ActualHarvestValidationErrorCode.SERVER_GENERATED_FIELD_SUPPLIED,
    )


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("actual_harvest_quantity_kg", "", ActualHarvestValidationErrorCode.REQUIRED_FIELD_MISSING),
        (
            "actual_harvest_quantity_kg",
            "-1.000000",
            ActualHarvestValidationErrorCode.NEGATIVE_QUANTITY,
        ),
        (
            "actual_harvest_quantity_kg",
            "1.0000001",
            ActualHarvestValidationErrorCode.INVALID_DECIMAL,
        ),
        (
            "actual_harvest_quantity_kg",
            "1234567890123.000000",
            ActualHarvestValidationErrorCode.INVALID_DECIMAL,
        ),
        ("actual_harvest_quantity_kg", "NaN", ActualHarvestValidationErrorCode.INVALID_DECIMAL),
        (
            "actual_harvest_quantity_kg",
            "Infinity",
            ActualHarvestValidationErrorCode.INVALID_DECIMAL,
        ),
        ("actual_harvest_quantity_kg", "1e2", ActualHarvestValidationErrorCode.INVALID_DECIMAL),
        ("harvest_business_date", "03/01/2026", ActualHarvestValidationErrorCode.INVALID_DATE),
    ],
)
def test_invalid_rows_fail_closed(
    field: str, value: str, code: ActualHarvestValidationErrorCode
) -> None:
    _assert_code(_csv_bytes([_row(**{field: value})]), code)


def test_explicit_zero_is_not_missing_and_missing_is_not_zero() -> None:
    result = parse_csv(_csv_bytes([_row(actual_harvest_quantity_kg="0")]))
    assert result.records[0].actual_harvest_quantity_kg == Decimal("0")
    _assert_code(
        _csv_bytes([_row(actual_harvest_quantity_kg="")]),
        ActualHarvestValidationErrorCode.REQUIRED_FIELD_MISSING,
    )


def test_output_order_is_canonical_not_hash_or_filesystem_order() -> None:
    result = parse_csv(
        _csv_bytes(
            [
                _row(external_logical_record_id="logical-2", external_revision_id="revision-2"),
                _row(external_logical_record_id="logical-1", external_revision_id="revision-1"),
            ]
        )
    )
    assert [record.external_logical_record_id for record in result.records] == [
        "logical-1",
        "logical-2",
    ]


def test_invalid_utf8_and_malformed_csv_are_rejected() -> None:
    _assert_code(b"\xff\xfe", ActualHarvestValidationErrorCode.CSV_ENCODING_INVALID)
    _assert_code(
        _csv_bytes([_row()]) + b'"unterminated',
        ActualHarvestValidationErrorCode.CSV_STRUCTURE_INVALID,
    )
