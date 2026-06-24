from __future__ import annotations

from decimal import Decimal

import numpy as np


def empirical_quantile(values: list[Decimal], quantile: Decimal) -> Decimal:
    if not values:
        return Decimal("0")
    array = np.asarray([float(item) for item in values], dtype=float)
    result = float(np.quantile(array, float(quantile), method="linear"))
    return Decimal(f"{result:.6f}")


__all__ = ["empirical_quantile"]
