from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import cast

from pydantic import BaseModel

from backend.app.harvest_state.canonical import canonical_decimal_string

type JsonScalar = None | bool | int | str
type JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


def _canonical_datetime_string(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone-aware datetime is required")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _canonical_decimal(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("non-finite Decimal is not allowed")
    return canonical_decimal_string(value)


def canonical_json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, (bool, int, str)):
        return cast(JsonValue, value)
    if isinstance(value, float):
        raise TypeError("native float is not supported in canonical payloads")
    if isinstance(value, Decimal):
        return _canonical_decimal(value)
    if isinstance(value, datetime):
        return _canonical_datetime_string(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    if isinstance(value, Enum):
        return canonical_json_value(value.value)
    if isinstance(value, BaseModel):
        return canonical_json_value(value.model_dump(mode="python"))
    if isinstance(value, tuple | list):
        return [canonical_json_value(item) for item in value]
    if isinstance(value, set):
        raise TypeError("set is not supported in canonical payloads")
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("canonical payload dict keys must be strings")
        return {key: canonical_json_value(value[key]) for key in sorted(value.keys())}
    raise TypeError(f"unsupported canonical JSON value type: {type(value).__name__}")


def canonical_json_dumps(value: object) -> str:
    return json.dumps(
        canonical_json_value(value),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def sha256_payload(value: object) -> str:
    payload = value if isinstance(value, str) else canonical_json_dumps(value)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
