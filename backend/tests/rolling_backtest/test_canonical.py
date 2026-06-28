from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import BaseModel

from backend.app.rolling_backtest.canonical import (
    canonical_json_dumps,
    canonical_json_value,
    sha256_payload,
)
from backend.app.rolling_backtest.enums import ExecutionMode


class _Payload(BaseModel):
    value: str


def test_canonical_dict_ordering_is_stable() -> None:
    left = canonical_json_dumps({"b": 2, "a": 1})
    right = canonical_json_dumps({"a": 1, "b": 2})
    assert left == right == '{"a":1,"b":2}'


def test_decimal_stability_avoids_scientific_notation() -> None:
    payload = canonical_json_value({"value": Decimal("1000.5000")})
    assert payload == {"value": "1000.5"}


def test_timezone_aware_datetime_is_converted_to_utc_z() -> None:
    value = datetime(2026, 3, 15, 12, 30, tzinfo=timezone(timedelta(hours=8)))
    assert canonical_json_value(value) == "2026-03-15T04:30:00Z"


def test_dst_boundary_is_normalized_to_utc() -> None:
    value = datetime(2026, 3, 8, 3, 30, tzinfo=timezone(timedelta(hours=-4)))
    assert canonical_json_value(value) == "2026-03-08T07:30:00Z"


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        canonical_json_value(datetime(2026, 3, 15, 12, 0))


def test_nan_and_infinity_are_rejected() -> None:
    with pytest.raises(ValueError):
        canonical_json_value(Decimal("NaN"))
    with pytest.raises(ValueError):
        canonical_json_value(Decimal("Infinity"))
    with pytest.raises(ValueError):
        canonical_json_value(Decimal("-Infinity"))


def test_enum_and_pydantic_models_are_canonicalized() -> None:
    payload = canonical_json_value(
        {
            "mode": ExecutionMode.HISTORICAL_OBSERVED,
            "model": _Payload(value="x"),
            "ts": datetime(2026, 3, 15, 12, 0, tzinfo=UTC),
        }
    )
    assert payload == {
        "mode": "historical_observed",
        "model": {"value": "x"},
        "ts": "2026-03-15T12:00:00Z",
    }


def test_sha256_payload_is_deterministic() -> None:
    assert sha256_payload({"a": 1, "b": 2}) == sha256_payload({"b": 2, "a": 1})
