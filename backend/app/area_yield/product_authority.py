"""Operator-configured private product authority; callers cannot supply model paths."""

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from backend.app.area_yield.product import (
    AreaDrivenForecastRequest,
    AreaDrivenForecastResult,
    check_hash,
    forecast_by_area,
)


def load_authority() -> dict[str, Any]:
    path = os.environ.get("AREA_YIELD_AUTHORITY_PATH")
    expected = os.environ.get("AREA_YIELD_AUTHORITY_SHA256")
    if not path or not expected:
        raise ValueError("AREA_YIELD_AUTHORITY_NOT_CONFIGURED")
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("AREA_YIELD_AUTHORITY_HASH_MISMATCH")
    value: dict[str, Any] = json.loads(raw)
    check_hash(value)
    return value


def forecast_area_product(request: AreaDrivenForecastRequest) -> AreaDrivenForecastResult:
    return forecast_by_area(request, load_authority())
