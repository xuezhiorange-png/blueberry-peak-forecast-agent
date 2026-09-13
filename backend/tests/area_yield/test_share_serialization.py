"""Public share serialization only; float composition and legacy reload stay unchanged."""

import math
from decimal import ROUND_UP, Decimal, Inexact, localcontext

import pytest
from sqlalchemy import select

from backend.app.area_yield import product
from backend.app.area_yield.product import canonical_share_text
from backend.app.area_yield.product_authority import forecast_area_product
from backend.app.area_yield.run_application import execute_area_forecast_run
from backend.app.area_yield.run_persistence import AreaForecastRunRepository, validate_result
from backend.app.models.area_forecast import AreaForecastDailyRow
from backend.tests.area_yield.test_product_p1 import bundle
from backend.tests.area_yield.test_run_persistence import authority as authority
from backend.tests.area_yield.test_run_persistence import bounded
from backend.tests.area_yield.test_run_persistence import session as session


@pytest.mark.parametrize(
    "value", [0.000113281357, 0.0009676453321, 0.003928432123, 0.006789123456, 0.013305123456]
)
def test_representative_neighbor_ulps(value):
    # Synthetic representative values, NOT the unavailable server forensic pairs.
    expected = canonical_share_text(value)
    assert canonical_share_text(math.nextafter(value, math.inf)) == expected
    assert canonical_share_text(math.nextafter(value, -math.inf)) == expected
    assert len(expected.split(".")[1]) == 15
    assert "e" not in expected.lower()


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, -0.001])
def test_invalid_share_rejected(value):
    with pytest.raises(ValueError):
        canonical_share_text(value)


def test_exact_half_even_and_fixed_format():
    assert canonical_share_text(0.0) == "0.000000000000000"
    assert canonical_share_text(-0.0) == "0.000000000000000"
    assert canonical_share_text(1.0) == "1.000000000000000"
    # Exactly representable binary halfway values at decimal scale 15.
    assert canonical_share_text(2**-16) == "0.000015258789062"
    assert canonical_share_text(3 * 2**-16) == "0.000045776367188"
    assert canonical_share_text(math.nextafter(0.0, math.inf)) == "0.000000000000000"


def test_independent_of_callers_decimal_context():
    with localcontext() as ctx:
        ctx.prec = 2
        ctx.rounding = ROUND_UP
        ctx.traps[Inexact] = True
        assert canonical_share_text(0.12345678912345678) == "0.123456789123457"
        assert canonical_share_text(1e100).endswith(".000000000000000")
        assert ctx.prec == 2 and ctx.traps[Inexact]


def test_366_row_error_stays_below_existing_tolerance():
    assert abs(Decimal(canonical_share_text(1 / 366)) * 366 - 1) < Decimal("1e-12")


def test_only_share_text_and_hash_change_and_compose_receives_raw(monkeypatch):
    authority = bundle()
    original_compose = product.compose
    seen = []

    def capture(total, shares):
        seen.append(list(shares))
        return original_compose(total, shares)

    monkeypatch.setattr(product, "compose", capture)
    with monkeypatch.context() as legacy:
        legacy.setattr(product, "canonical_share_text", str)
        before = product.forecast_by_area(bounded(), authority).model_dump(mode="json")
    after = product.forecast_by_area(bounded(), authority).model_dump(mode="json")
    assert seen[0] == seen[1]
    assert len(before["daily_forecast"]) == 207
    for a, b in zip(before["daily_forecast"], after["daily_forecast"], strict=True):
        assert a["date"] == b["date"] and a["predicted_kg"] == b["predicted_kg"]
        a.pop("share")
        b.pop("share")
    before.pop("result_hash")
    after.pop("result_hash")
    assert before == after


def test_five_raw_ulp_perturbations_same_public_hash(monkeypatch):
    original = product.normalize
    expected = product.forecast_by_area(bounded(), bundle())

    def perturbed(values):
        shares = list(original(values))
        for i in range(5):
            shares[i] = math.nextafter(shares[i], math.inf)
        return shares

    monkeypatch.setattr(product, "normalize", perturbed)
    assert product.forecast_by_area(bounded(), bundle()) == expected


async def test_legacy_reload_preserves_original_share_and_execution_reuse(
    session, authority, monkeypatch
):
    with monkeypatch.context() as legacy:
        legacy.setattr(product, "canonical_share_text", str)
        old = await execute_area_forecast_run(session, bounded())
    new_result = forecast_area_product(bounded())
    assert new_result.result_hash != old.result.result_hash
    assert any(len(r.share.split(".")[-1]) > 15 for r in old.result.daily_forecast)
    repo = AreaForecastRunRepository(session)
    loaded = await repo.get(old.run.run_id)
    assert loaded == old
    assert loaded.result.daily_forecast == old.result.daily_forecast
    history = await repo.history()
    assert history.items[0].result_hash == old.result.result_hash
    reused = await execute_area_forecast_run(session, bounded())
    assert reused.reused_existing_run and reused.result == old.result


async def test_new_persistence_is_canonical_idempotent(session, authority):
    first = await execute_area_forecast_run(session, bounded())
    second = await execute_area_forecast_run(session, bounded())
    assert first.run.run_id == second.run.run_id and second.reused_existing_run
    rows = (
        await session.scalars(select(AreaForecastDailyRow).order_by(AreaForecastDailyRow.row_index))
    ).all()
    assert len(rows) == 207
    assert [r.share_text for r in rows] == [r.share for r in first.result.daily_forecast]
    assert all(len(r.share_text.split(".")[1]) == 15 for r in rows)
    validate_result(first.result)
