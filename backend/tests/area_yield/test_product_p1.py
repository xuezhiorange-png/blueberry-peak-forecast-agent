"""Product policy tests use synthetic fixtures, never research labels."""

from copy import deepcopy
from decimal import Decimal

import pytest

from backend.app.area_yield.data import digest
from backend.app.area_yield.product import AreaDrivenForecastRequest, forecast_by_area


def bundle():
    shape = {
        "kind": "ridge",
        "alpha": 10.0,
        "training_season": "2024-2025",
        "mean": [0.0] * 4,
        "scale": [1.0] * 4,
        "coefficients": [0.1, 0.2, 0.0, 0.0],
        "intercept": 1.0,
        "calendar": "JULY_01_THROUGH_JUNE_30",
    }
    shape["hash"] = digest(shape)
    value = {
        "model_version": "area-yield-b1-fixture-v1",
        "shape": shape,
        "shape_available_on": "2025-07-01",
        "aliases": {"alias": "known"},
        "history": [
            {
                "farm": farm,
                "season": "2025-2026",
                "end": "2026-04-15",
                "available_on": "2026-04-16",
                "yield_kg_per_mu": amount,
                "completeness": "STRICT_ELIGIBLE",
                "area_basis": "BUSINESS_CONFIRMED",
                "source_hash": "a" * 64,
            }
            for farm, amount in [("known", "100"), ("other", "200")]
        ],
    }
    value["hash"] = digest(value)
    return value


def request(farm="known", area="100", **kwargs):
    return AreaDrivenForecastRequest(
        farm=farm, productive_area_mu=area, target_season="2026-2027", **kwargs
    )


def test_known_prior_and_requested_area():
    r = forecast_by_area(request(), bundle())
    assert r.predicted_total_kg == "10000.000000"
    assert not r.fallback_used
    assert r.mass_balance["pass"]
    assert r.total_model_source_season == "2025-2026"


def test_unknown_explicit_fallback():
    r = forecast_by_area(request("new"), bundle())
    assert r.fallback_used and r.fallback_reason == "NO_PRIOR_SEASON"
    assert r.predicted_yield_kg_per_mu == "150.000000"
    assert r.total_model == "GLOBAL_MEDIAN_YIELD_PER_MU"


def test_alias_only_authorized_and_determinism():
    assert forecast_by_area(request("alias"), bundle()).canonical_farm == "known"
    assert forecast_by_area(request(), bundle()) == forecast_by_area(request(), bundle())
    assert forecast_by_area(request("know"), bundle()).fallback_used


@pytest.mark.parametrize("area", ["0", "-1", "NaN", "Infinity"])
def test_invalid_area(area):
    with pytest.raises(ValueError):
        request(area=area)


def test_area_scale_shape_dates_and_mass():
    results = [forecast_by_area(request(area=a), bundle()) for a in ["100", "500", "1000"]]
    for r, ratio in zip(results, [1, 5, 10], strict=True):
        assert Decimal(r.predicted_total_kg) == Decimal(results[0].predicted_total_kg) * ratio
        assert r.single_day_peak["date"] == results[0].single_day_peak["date"]
        assert [d.share for d in r.daily_forecast] == [d.share for d in results[0].daily_forecast]
        assert abs(
            Decimal(r.single_day_peak["kg"]) - Decimal(results[0].single_day_peak["kg"]) * ratio
        ) < Decimal("0.00001")
        assert abs(
            Decimal(r.rolling_7day_peak["total_kg"])
            - Decimal(results[0].rolling_7day_peak["total_kg"]) * ratio
        ) < Decimal("0.00007")
        assert r.mass_balance["pass"]


def test_hash_and_future_guard():
    b = bundle()
    b["history"][0]["yield_kg_per_mu"] = "999"
    with pytest.raises(ValueError, match="hash"):
        forecast_by_area(request(), b)
    b = bundle()
    for row in b["history"]:
        row["available_on"] = "2027-01-01"
    b["hash"] = digest({k: v for k, v in b.items() if k != "hash"})
    with pytest.raises(ValueError, match="history"):
        forecast_by_area(request(), b)


def test_frozen_shape_no_prior_production():
    b = deepcopy(bundle())
    b["shape"]["alpha"] = 1
    b["shape"]["hash"] = digest({k: v for k, v in b["shape"].items() if k != "hash"})
    b["hash"] = digest({k: v for k, v in b.items() if k != "hash"})
    with pytest.raises(ValueError, match="shape"):
        forecast_by_area(request(), b)


def test_window_and_peaks_from_final_rows():
    r = forecast_by_area(request(season_start="2026-10-15", season_end="2027-05-09"), bundle())
    assert len(r.daily_forecast) == 207
    assert r.season_window_status == "CALLER_SPECIFIED"
    values = [Decimal(d.predicted_kg) for d in r.daily_forecast]
    assert Decimal(r.single_day_peak["kg"]) == max(values)
    assert Decimal(r.rolling_7day_peak["total_kg"]) == max(
        sum(values[i : i + 7]) for i in range(len(values) - 6)
    )
    assert abs(sum(Decimal(d.share) for d in r.daily_forecast) - 1) < Decimal("1e-12")


def test_no_fit_or_prior_shape_invocation(monkeypatch):
    from sklearn.linear_model import Ridge

    from backend.app.area_yield import prior_shape_r3b

    def forbidden(*args, **kwargs):
        raise AssertionError("research operation invoked")

    monkeypatch.setattr(Ridge, "fit", forbidden)
    # The product imports only Global predict; no carry-forward path is dispatched.
    monkeypatch.setattr(prior_shape_r3b, "predict", forbidden, raising=False)
    assert forecast_by_area(request(), bundle()).shape_model == "GLOBAL_RIDGE_TWO_ANNUAL_HARMONICS"


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("completeness", "RIGHT_CENSORED", "PRIOR_SEASON_INCOMPLETE"),
        ("area_basis", "PREVIOUS_SEASON_PROXY", "NO_VALID_AREA_HISTORY"),
    ],
)
def test_ineligible_own_history_fallback(field, value, reason):
    b = bundle()
    b["history"][0][field] = value
    b["hash"] = digest({k: v for k, v in b.items() if k != "hash"})
    r = forecast_by_area(request(), b)
    assert r.fallback_reason == reason
    assert r.predicted_yield_kg_per_mu == "200.000000"


def test_asof_target_and_short_window_rejected():
    for kwargs in [
        dict(as_of="2026-07-01"),
        dict(season_start="2026-08-01"),
        dict(season_start="2026-08-01", season_end="2026-08-06"),
    ]:
        with pytest.raises(ValueError):
            forecast_by_area(request(**kwargs), bundle())


def test_default_calendar_leap_year_and_latest_eligible_history():
    b = bundle()
    b["history"].append(
        {
            **b["history"][0],
            "season": "2024-2025",
            "end": "2025-05-27",
            "available_on": "2025-06-01",
            "yield_kg_per_mu": "999",
        }
    )
    b["hash"] = digest({k: v for k, v in b.items() if k != "hash"})
    r = forecast_by_area(
        AreaDrivenForecastRequest(
            farm="known", productive_area_mu="100", target_season="2027-2028"
        ),
        b,
    )
    assert len(r.daily_forecast) == 366
    assert r.season_window_status == "FORECAST_ASSUMPTION"
    assert r.predicted_yield_kg_per_mu == "100.000000"
