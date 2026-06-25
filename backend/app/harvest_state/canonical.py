from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, time
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext
from enum import Enum
from typing import Any, cast

from backend.app.harvest_state.enums import RESULT_HASH_SCHEMA_VERSION

type JsonScalar = None | str | bool | int | float
type JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]

_CANONICAL_DECIMAL_RE = re.compile(r"^(0|[-]?[1-9][0-9]*)(\.[0-9]+)?$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def parse_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("non-finite Decimal is not allowed")
        return value
    if isinstance(value, bool):
        raise ValueError("bool is not a valid Decimal input")
    if isinstance(value, float):
        raise ValueError("native float business input is forbidden")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        text = value.strip()
        if text == "":
            raise ValueError("empty Decimal string is not allowed")
        if not _CANONICAL_DECIMAL_RE.fullmatch(text):
            raise ValueError(f"non-canonical Decimal string: {value!r}")
        if text.startswith("-0"):
            raise ValueError("negative zero is not allowed")
        try:
            parsed = Decimal(text)
        except InvalidOperation as exc:  # pragma: no cover - defensive
            raise ValueError(f"invalid Decimal string: {value!r}") from exc
        if not parsed.is_finite():
            raise ValueError("non-finite Decimal is not allowed")
        return parsed
    raise ValueError(f"unsupported Decimal input type: {type(value).__name__}")


def canonical_decimal_string(value: Decimal) -> str:
    if value == 0:
        return "0"
    normalized = value.normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def quantize_quantity(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def quantize_ratio(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def business_localcontext() -> Any:
    ctx = localcontext()
    context = ctx.__enter__()
    context.prec = 28
    context.rounding = ROUND_HALF_UP
    return ctx


def canonical_json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, (str, bool, int, float)):
        return cast(JsonValue, value)
    if isinstance(value, Decimal):
        return canonical_decimal_string(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    if isinstance(value, Enum):
        return canonical_json_value(value.value)
    if isinstance(value, list | tuple):
        return [canonical_json_value(item) for item in value]
    if isinstance(value, dict):
        return {
            key: canonical_json_value(item)
            for key, item in sorted(value.items(), key=lambda item: item[0])
        }
    raise TypeError(f"unsupported canonical JSON value type: {type(value).__name__}")


def canonical_json_dumps(value: object) -> str:
    return json.dumps(
        canonical_json_value(value),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def sha256_hex(value: object) -> str:
    payload = value if isinstance(value, str) else canonical_json_dumps(value)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def make_membership_hash(capacity_pool_grain: str, members: list[dict[str, int | None]]) -> str:
    return sha256_hex(
        {
            "capacity_pool_grain": capacity_pool_grain,
            "members": members,
        }
    )


def make_source_ref_hash(payload: dict[str, Any]) -> str:
    return sha256_hex(payload)


def make_stable_cohort_key(payload: dict[str, Any]) -> str:
    return sha256_hex(payload)


def make_weather_rule_config_hash(payload: dict[str, Any]) -> str:
    return sha256_hex(payload)


def make_holiday_calendar_hash(
    *,
    holiday_calendar_version: str,
    holiday_dates: list[date],
) -> str:
    return sha256_hex(
        {
            "holiday_calendar_version": holiday_calendar_version,
            "holiday_dates": sorted(holiday_dates),
        }
    )


def make_task9a_config_hash(
    *,
    weather_rule_version: str,
    weather_rule_config_hash: str,
    holiday_calendar_version: str,
    holiday_calendar_hash: str,
    source_ref_schema_version: str,
    stable_cohort_key_schema_version: str,
    resolved_parameter_snapshot_schema_version: str,
    output_schema_version: str,
) -> str:
    return sha256_hex(
        {
            "weather_rule_version": weather_rule_version,
            "weather_rule_config_hash": weather_rule_config_hash,
            "holiday_calendar_version": holiday_calendar_version,
            "holiday_calendar_hash": holiday_calendar_hash,
            "source_ref_schema_version": source_ref_schema_version,
            "stable_cohort_key_schema_version": stable_cohort_key_schema_version,
            "resolved_parameter_snapshot_schema_version": (
                resolved_parameter_snapshot_schema_version
            ),
            "output_schema_version": output_schema_version,
        }
    )


def make_result_hash(payload: dict[str, Any]) -> str:
    filtered = {key: value for key, value in payload.items() if key != "result_hash"}
    filtered["result_hash_schema_version"] = RESULT_HASH_SCHEMA_VERSION
    return sha256_hex(filtered)


def is_sha256_hex(value: str) -> bool:
    return bool(_SHA256_RE.fullmatch(value))
