from __future__ import annotations

import csv
import io
from datetime import datetime

import openpyxl
from openpyxl.workbook.properties import CalcProperties

from backend.app.actual_harvest_import.spreadsheet_parser import canonical_spreadsheet_headers
from backend.app.actual_harvest_import.spreadsheet_policy import (
    DEFAULT_SPREADSHEET_POLICY,
    SpreadsheetParserPolicy,
)


def generate_csv_template(
    *,
    policy: SpreadsheetParserPolicy = DEFAULT_SPREADSHEET_POLICY,
) -> bytes:
    del policy
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(canonical_spreadsheet_headers())
    return output.getvalue().encode("utf-8")


def generate_xlsx_template(
    *,
    policy: SpreadsheetParserPolicy = DEFAULT_SPREADSHEET_POLICY,
) -> bytes:
    del policy
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = "actual_harvest"
    for column, header in enumerate(canonical_spreadsheet_headers(), start=1):
        worksheet.cell(row=1, column=column, value=header)
    workbook.properties.creator = ""
    workbook.properties.lastModifiedBy = ""
    workbook.properties.created = datetime(2000, 1, 1)
    workbook.properties.modified = datetime(2000, 1, 1)
    workbook.calculation = CalcProperties(
        calcMode="manual", fullCalcOnLoad=False, forceFullCalc=False
    )
    output = io.BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()
