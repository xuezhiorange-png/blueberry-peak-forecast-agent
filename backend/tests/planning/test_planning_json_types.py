from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from backend.app.planning.json_types import (
    canonical_decimal_string,
    canonical_json_value,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("1000.00000000"), "1000"),
        (Decimal("1000.000000"), "1000"),
        (Decimal("1000"), "1000"),
        (Decimal("0.70"), "0.7"),
        (Decimal("0.7000000000"), "0.7"),
        (Decimal("2.000000"), "2"),
        (Decimal("0.1000000000"), "0.1"),
        (Decimal("0.000000"), "0"),
        (Decimal("-0.000"), "0"),
        (Decimal("0E-10"), "0"),
        (Decimal("0.00000100"), "0.000001"),
    ],
)
def test_canonical_decimal_string_normalizes_equivalent_values(
    value: Decimal,
    expected: str,
) -> None:
    assert canonical_decimal_string(value) == expected


def test_canonical_json_value_normalizes_nested_decimal_structures() -> None:
    payload = {
        "weight": Decimal("1000.00000000"),
        "rate": Decimal("0.7000000000"),
        "items": (
            Decimal("2.000000"),
            {
                "zero": Decimal("-0.000"),
                "small": Decimal("0.00000100"),
            },
        ),
        "day": date(2026, 6, 22),
        "timestamp": datetime(2026, 6, 22, 9, 30, 15),
    }

    assert canonical_json_value(payload) == {
        "weight": "1000",
        "rate": "0.7",
        "items": ["2", {"zero": "0", "small": "0.000001"}],
        "day": "2026-06-22",
        "timestamp": "2026-06-22T09:30:15",
    }


def test_canonical_json_value_preserves_json_primitives() -> None:
    assert canonical_json_value(None) is None
    assert canonical_json_value(True) is True
    assert canonical_json_value("x") == "x"
    assert canonical_json_value(3) == 3
    assert canonical_json_value(1.5) == 1.5


def test_canonical_json_value_rejects_unknown_types() -> None:
    class Unsupported:
        pass

    with pytest.raises(TypeError, match="Unsupported JSON value type"):
        canonical_json_value(Unsupported())
