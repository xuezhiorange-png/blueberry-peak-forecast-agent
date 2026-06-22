from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import cast

type JsonScalar = None | str | bool | int | float
type JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


def canonical_decimal_string(value: Decimal) -> str:
    if value == 0:
        return "0"
    normalized = value.normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in {"-0", "+0", ""}:
        return "0"
    return text


def canonical_json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, (str, bool, int, float)):
        return cast(JsonValue, value)
    if isinstance(value, Decimal):
        return canonical_decimal_string(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [canonical_json_value(item) for item in value]
    if isinstance(value, dict):
        canonical_dict: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"JSON object keys must be str, got {type(key).__name__}")
            canonical_dict[key] = canonical_json_value(item)
        return canonical_dict
    raise TypeError(f"Unsupported JSON value type: {type(value).__name__}")
