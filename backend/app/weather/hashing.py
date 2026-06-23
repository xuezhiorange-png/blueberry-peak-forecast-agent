from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any


def _canonical_json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        return [_canonical_json(item) for item in value]
    if isinstance(value, tuple):
        return [_canonical_json(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _canonical_json(value[key]) for key in sorted(value)}
    return value


def stable_json(value: Any) -> str:
    return json.dumps(
        _canonical_json(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def sha256_payload(payload: dict[str, Any]) -> str:
    return hashlib.sha256(stable_json(payload).encode("utf-8")).hexdigest()
