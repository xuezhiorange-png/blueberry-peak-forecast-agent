"""Read the pinned pre-TEST historical XLS and emit aggregate calibration evidence.

No database access, forecast invocation, or parameter-library activation. The
source is deliberately fixed: no glob, alternate XLS, or sealed partition read.
"""

import hashlib
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import xlrd

from backend.app.planning.harvest_baseline_calibration import HarvestFact, build_harvest_baseline

SOURCE = Path("data/raw/2024_2025_receipts.xls")
SOURCE_HASH = "a55cbf259f52e6a20e30d646b43d2aa0f104f60786d725dbc051e46c76b390d5"


def main() -> None:
    source_bytes = SOURCE.read_bytes()
    if hashlib.sha256(source_bytes).hexdigest() != SOURCE_HASH:
        raise ValueError("historical source identity mismatch")
    workbook = xlrd.open_workbook(file_contents=source_bytes)
    facts: list[HarvestFact] = []
    for sheet in workbook.sheets():
        headers = [str(value).strip() for value in sheet.row_values(0)]
        if "农场" not in headers:
            raise ValueError("source farm header missing")
        for index in range(1, sheet.nrows):
            values = dict(zip(headers, sheet.row_values(index), strict=True))
            if values["农场"] != "版纳勐旺农场":
                continue
            if values.get("加工厂") != "勐旺加工厂":
                raise ValueError("canonical factory scope mismatch")
            if values.get("品种") != "蓝莓原果Dx":
                continue
            # This pinned source has ISO date strings. Other encodings are not
            # silently coerced into dates or quantities.
            day = date.fromisoformat(str(values["时间"]))
            facts.append(
                HarvestFact(
                    f"{sheet.name}:{index + 1}",
                    day,
                    Decimal(str(values["入库公斤数"])),
                )
            )
    result = build_harvest_baseline(
        tuple(facts),
        source_sha256=SOURCE_HASH,
        farm_name="版纳勐旺农场",
        variety_code="Dx",
        factory_name="勐旺加工厂",
        # Current acceptance source verification, not backdated visibility.
        source_visible_on=date(2026, 9, 11),
        as_of_date=date(2026, 9, 11),
    )
    daily = result.pop("daily_harvest")
    result["daily_harvest_hash"] = hashlib.sha256(
        json.dumps(daily, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    result["calibration_hash_includes_unpublished_daily_rows"] = True
    result["source_file"] = str(SOURCE)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
