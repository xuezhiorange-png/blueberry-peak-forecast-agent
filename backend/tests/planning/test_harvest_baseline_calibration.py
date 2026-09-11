from datetime import date
from decimal import Decimal

import pytest

from backend.app.planning.harvest_baseline_calibration import (
    HarvestFact,
    HistoricalArea,
    build_harvest_baseline,
)


def facts() -> tuple[HarvestFact, ...]:
    return (
        HarvestFact("sheet:1", date(2025, 1, 2), Decimal("10")),
        HarvestFact("sheet:2", date(2025, 1, 2), Decimal("20")),
        HarvestFact("sheet:3", date(2025, 1, 4), Decimal("30")),
    )


def build(rows: tuple[HarvestFact, ...], area: HistoricalArea | None = None) -> dict:
    return build_harvest_baseline(
        rows,
        source_sha256="a" * 64,
        farm_name="farm",
        variety_code="Dx",
        factory_name="factory",
        source_visible_on=date(2025, 2, 1),
        as_of_date=date(2025, 2, 1),
        historical_area=area,
    )


def test_arrival_is_harvest_without_conversion() -> None:
    result = build(facts())
    assert result["historical_total_harvest_kg"] == "60.000000"
    assert result["arrival_equals_harvest"] is True
    assert result["observed_day_count"] == 2
    assert result["missing_calendar_day_count"] == 1
    assert len(result["daily_harvest"]) == 2


def test_baseline_policies_do_not_claim_observed_rates() -> None:
    parameters = build(facts())["parameters"]
    for name in ("marketable_rate", "harvest_realization_rate"):
        assert parameters[name]["value"] == "1.000000"
        assert parameters[name]["authority_type"] == "BASELINE_POLICY"


def test_current_area_is_not_implicitly_historical_area() -> None:
    result = build(facts())
    assert "yield_kg_per_mu" not in result["parameters"]
    assert result["historical_area_binding_available"] is False


def test_yield_uses_explicit_matching_historical_area() -> None:
    area = HistoricalArea(
        "farm", "Dx", date(2025, 1, 1), date(2025, 1, 31), Decimal("2"), "area-v1"
    )
    result = build(facts(), area)
    assert result["parameters"]["yield_kg_per_mu"]["value"] == "30.000000"
    assert result["parameters"]["yield_kg_per_mu"]["authority_type"] == "DERIVED_FROM_HISTORY"


@pytest.mark.parametrize(
    "farm,variety,end", [("other", "Dx", 31), ("farm", "other", 31), ("farm", "Dx", 3)]
)
def test_area_scope_and_window_must_match(farm: str, variety: str, end: int) -> None:
    area = HistoricalArea(
        farm, variety, date(2025, 1, 1), date(2025, 1, end), Decimal("2"), "area-v1"
    )
    with pytest.raises(ValueError, match="historical area"):
        build(facts(), area)


def test_same_source_same_hash_independent_of_row_order() -> None:
    assert build(facts()) == build(tuple(reversed(facts())))


def test_different_quantity_changes_hash() -> None:
    changed = (HarvestFact("sheet:1", date(2025, 1, 2), Decimal("11")), *facts()[1:])
    assert build(changed)["calibration_hash"] != build(facts())["calibration_hash"]


def test_duplicate_source_row_fails_closed() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        build(facts() + facts()[:1])


@pytest.mark.parametrize("value", [Decimal("-1"), Decimal("NaN"), Decimal("Infinity"), 1.5])
def test_invalid_quantity_fails_closed(value: Decimal) -> None:
    with pytest.raises(ValueError, match="quantity"):
        build((HarvestFact("sheet:1", date(2025, 1, 2), value),))


def test_future_fact_excluded_fail_closed() -> None:
    with pytest.raises(ValueError, match="future"):
        build((HarvestFact("sheet:1", date(2026, 1, 2), Decimal("1")),))


def test_no_invented_anchor_width_or_skewness() -> None:
    result = build(facts())
    assert set(result["parameters"]) == {"marketable_rate", "harvest_realization_rate"}
    assert result["parameter_library_ready"] is False
    assert result["first_positive_harvest_date"] == "2025-01-02"
    assert result["raw_peak_date"] == "2025-01-02"


def test_future_source_visibility_fails_closed() -> None:
    with pytest.raises(ValueError, match="future source"):
        build_harvest_baseline(
            facts(),
            source_sha256="a" * 64,
            farm_name="farm",
            variety_code="Dx",
            factory_name="factory",
            source_visible_on=date(2025, 2, 2),
            as_of_date=date(2025, 2, 1),
        )


def test_calibration_does_not_access_database_or_downstream() -> None:
    # Pure calibration has no application/session dependency; it cannot create
    # observations, activate a library, train a model or execute a forecast.
    result = build(facts())
    assert result["parameter_library_ready"] is False
    assert set(result["parameters"]) == {"marketable_rate", "harvest_realization_rate"}
