from decimal import Decimal
from typing import cast

import pytest

from backend.app.forecast_quality.canonical import emit_s3_decimal
from backend.app.forecast_quality.exceptions import S3DecimalAssertionError


def test_fixed_six_half_even_decimal_emission() -> None:
    assert emit_s3_decimal(Decimal("1")) == "1.000000"
    assert emit_s3_decimal(Decimal("1.2")) == "1.200000"
    assert emit_s3_decimal(Decimal("0.000001")) == "0.000001"
    assert emit_s3_decimal(Decimal("0.0000005")) == "0.000000"
    assert emit_s3_decimal(Decimal("0.0000015")) == "0.000002"


def test_non_decimal_and_non_finite_values_are_rejected() -> None:
    for value in (1.0, float("nan"), float("inf"), Decimal("NaN"), Decimal("Infinity")):
        with pytest.raises(S3DecimalAssertionError):
            emit_s3_decimal(cast(Decimal, value))
