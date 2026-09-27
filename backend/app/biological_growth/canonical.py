"""Deterministic serialization helpers; no filesystem or network access."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any, cast


def _plain(value: Any) -> Any:
    if is_dataclass(value):
        return _plain(asdict(cast(Any, value)))
    if isinstance(value, dict):
        return {str(key): _plain(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return str(value)
    if isinstance(value, float):
        if value != value or abs(value) == float("inf"):
            raise ValueError("Non-finite values are not canonical JSON")
        return 0.0 if value == 0 else value
    return value


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(_plain(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()
