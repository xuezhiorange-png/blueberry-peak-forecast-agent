from decimal import Decimal

import pytest

from backend.app.area_yield.total_evaluation_r4 import aggregate, compare
from backend.app.area_yield.total_yield_r4 import Area, fit, sample


def test_business_confirmed_area_is_supported_without_changing_proxy():
    area = Area("A", "393.4", "BUSINESS_CONFIRMED", "user confirmation", "a" * 64, "FARM", True)
    row = sample(area, "A", "2023-2024", "3934", "STRICT_ELIGIBLE")
    assert row["yield_kg_per_mu"] == "10.000000"
    with pytest.raises(ValueError):
        Area("A", "393.4", "PREVIOUS_SEASON_PROXY", "old", "a" * 64, "FARM", True).validate("A")


def test_global_median_order_determinism():
    rows = [
        sample(
            Area(f, "100", "BUSINESS_REPORTED", "fixture", "a" * 64, "FARM", True),
            f,
            "2023-2024",
            total,
            "COMPLETE",
        )
        for f, total in (("A", "1000"), ("B", "3000"))
    ]
    assert fit(rows) == fit(list(reversed(rows)))
    assert Decimal(fit(rows)["global_yield"]) == 20


def test_equal_farm_metrics_and_separate_kg_weighting():
    rows = []
    for farm, actual, predicted in (("A", "10", "20"), ("B", "100", "100")):
        rows.append(
            compare(
                {"farm": farm, "area_mu": "1", "yield_kg_per_mu": actual, "total_kg": actual},
                {"predicted_yield_kg_per_mu": predicted, "predicted_season_total_kg": predicted},
            )
        )
    macro = aggregate(rows)
    assert macro["yield_mae"] == "5.000000"
    assert macro["yield_mape"] == "0.500000"
    assert macro["total_rel_p90"] == "0.900000"
    assert macro["kg_weighted_wape_diagnostic"] == "0.090909"
