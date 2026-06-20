import hashlib
from datetime import date
from decimal import ROUND_HALF_UP, Decimal


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def source_row_fingerprint(file_sha256: str, sheet_name: str, source_row_number: int) -> str:
    return _sha256_text(f"{file_sha256}|{sheet_name}|{source_row_number}")


def normalize_decimal_for_fingerprint(value: Decimal | None) -> str:
    if value is None:
        return ""
    return str(value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def business_fingerprint(
    *,
    season_code: str,
    receipt_date: date | None,
    factory_name: str | None,
    farm_name: str | None,
    subfarm_name: str | None,
    variety_name: str | None,
    grade_code: str | None,
    weight_kg: Decimal | None,
) -> str:
    payload = "|".join(
        [
            season_code,
            receipt_date.isoformat() if receipt_date else "",
            factory_name or "",
            farm_name or "",
            subfarm_name or "",
            variety_name or "",
            grade_code or "",
            normalize_decimal_for_fingerprint(weight_kg),
        ]
    )
    return _sha256_text(payload)
