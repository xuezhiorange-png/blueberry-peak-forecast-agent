from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from backend.app.harvest_state.canonical import (
    canonical_decimal_string,
    canonical_json_dumps,
    canonical_json_value,
    parse_decimal,
    quantize_quantity,
    quantize_ratio,
    sha256_hex,
)

JsonValue = (
    None
    | str
    | bool
    | int
    | float
    | list["JsonValue"]
    | dict[str, "JsonValue"]
)


def canonical_payload_hash(payload: object) -> str:
    return sha256_hex(payload)


def canonical_iso_date(value: date) -> str:
    return value.isoformat()


def canonical_iso_datetime(value: datetime) -> str:
    return value.isoformat()


__all__ = [
    "JsonValue",
    "canonical_decimal_string",
    "canonical_iso_date",
    "canonical_iso_datetime",
    "canonical_json_dumps",
    "canonical_json_value",
    "canonical_payload_hash",
    "parse_decimal",
    "quantize_quantity",
    "quantize_ratio",
    "sha256_hex",
    "Decimal",
    "Any",
]

