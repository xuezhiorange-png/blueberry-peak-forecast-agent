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
from backend.app.area_yield.product_errors import (
    AreaForecastAuthorityError,
    AreaForecastRequestError,
)


def load_authority() -> dict[str, Any]:
    path = os.environ.get("AREA_YIELD_AUTHORITY_PATH")
    expected = os.environ.get("AREA_YIELD_AUTHORITY_SHA256")
    if not path or not expected:
        raise AreaForecastAuthorityError("AUTHORITY_NOT_CONFIGURED")
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise AreaForecastAuthorityError("AUTHORITY_FILE_UNREADABLE") from exc
    if hashlib.sha256(raw).hexdigest() != expected:
        raise AreaForecastAuthorityError("AUTHORITY_FILE_HASH_MISMATCH")
    try:
        value: dict[str, Any] = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("object required")
    except (ValueError, UnicodeError) as exc:
        raise AreaForecastAuthorityError("AUTHORITY_PAYLOAD_INVALID") from exc
    check_hash(value)
    return value


def forecast_area_product(request: AreaDrivenForecastRequest) -> AreaDrivenForecastResult:
    try:
        return forecast_by_area(request, load_authority())
    except (AreaForecastRequestError, AreaForecastAuthorityError):
        raise
    except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
        raise AreaForecastAuthorityError("AUTHORITY_PAYLOAD_INVALID") from exc
