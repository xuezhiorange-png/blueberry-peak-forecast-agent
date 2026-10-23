"""S7 numerical/runtime contracts use synthetic inputs, not current-season actuals."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from backend.app.rolling_forecast.engine import forecast, harvest_features
from backend.app.rolling_forecast.schemas import Area, Calendar, Observation


def inputs():
    calendar = Calendar(
        reference="SYNTHETIC-CALENDAR",
        season="2026-2027",
        start=date(2026, 7, 1),
        end=date(2027, 4, 15),
        source_hash="a" * 64,
        known_at=datetime(2026, 6, 1, tzinfo=UTC),
    )
    area = Area(
        reference="SYNTHETIC-AREA",
        base_id="SYNTHETIC_BASE",
        season=calendar.season,
        area_mu=Decimal(100),
        source_hash="b" * 64,
        known_at=calendar.known_at,
        effective_from=calendar.start,
        effective_until=calendar.end,
    )
    origin = date(2026, 8, 5)
    cutoff = datetime(2026, 8, 5, 9, tzinfo=UTC)
    rows = [
        Observation(
            base_id=area.base_id,
            season=area.season,
            business_date=calendar.start + timedelta(days=i),
            quantity_kg=Decimal(2),
            record_state="VALID_OBSERVED",
            quantity_basis="INBOUND_NET_WEIGHT",
            source_system="SYNTHETIC",
            source_identity=str(i),
            source_hash="c" * 64,
            source_recorded_at=datetime(2026, 7, 1, tzinfo=UTC) + timedelta(days=i),
            server_ingested_at=datetime(2026, 7, 1, 1, tzinfo=UTC) + timedelta(days=i),
            available_at_authority="TRUSTED_SOURCE_TIMESTAMP",
            observation_completeness="COMPLETE",
        )
        for i in range(50)
    ]
    return calendar, area, origin, cutoff, rows


def test_future_season_uses_explicit_authority_and_prior_days_only():
    from backend.tests.rolling_forecast.training_fixture import frozen_pair

    calendar, area, origin, cutoff, rows = inputs()
    pair = frozen_pair()
    prediction = forecast(calendar, area, origin, cutoff, rows, pair, "RESEARCH_SHADOW")
    first = harvest_features(calendar, area, origin, cutoff, rows, "RESEARCH_SHADOW")
    assert first["complete"]
    assert list(first["values"].values()) == ["14", "28", "56", "70"]
    changed = [
        r.model_copy(update={"quantity_kg": Decimal(999)}) if r.business_date >= origin else r
        for r in rows
    ]
    assert harvest_features(calendar, area, origin, cutoff, changed, "RESEARCH_SHADOW") == first
    assert forecast(calendar, area, origin, cutoff, changed, pair, "RESEARCH_SHADOW") == prediction
    changed = [
        r.model_copy(update={"quantity_kg": Decimal(5)})
        if r.business_date == origin - timedelta(days=1)
        else r
        for r in rows
    ]
    after = harvest_features(calendar, area, origin, cutoff, changed, "RESEARCH_SHADOW")
    assert all(Decimal(after["values"][k]) - Decimal(v) == 3 for k, v in first["values"].items())
    updated = forecast(calendar, area, origin, cutoff, changed, pair, "RESEARCH_SHADOW")
    assert updated["models"]["M0"] == prediction["models"]["M0"]
    assert (
        updated["models"]["M1"]["daily_forecast_kg"]
        != prediction["models"]["M1"]["daily_forecast_kg"]
    )


@pytest.mark.parametrize("distance", [1, 10, 20])
def test_each_prior_window_requires_observations_but_accepts_authoritative_zero(distance):
    calendar, area, origin, cutoff, rows = inputs()
    target = origin - timedelta(days=distance)
    missing = [r for r in rows if r.business_date != target]
    assert not harvest_features(calendar, area, origin, cutoff, missing, "RESEARCH_SHADOW")[
        "complete"
    ]
    zero = [
        r.model_copy(update={"record_state": "CONFIRMED_ZERO", "quantity_kg": Decimal(0)})
        if r.business_date == target
        else r
        for r in rows
    ]
    result = harvest_features(calendar, area, origin, cutoff, zero, "RESEARCH_SHADOW")
    assert result["complete"]
    assert Decimal(result["values"]["past_28d_harvest_kg"]) == 54


@pytest.mark.parametrize("field", ["source_recorded_at", "server_ingested_at"])
def test_late_revision_or_ingestion_never_enters_cutoff(field):
    calendar, area, origin, cutoff, rows = inputs()
    rows[34] = rows[34].model_copy(update={field: cutoff + timedelta(seconds=1)})
    r = harvest_features(calendar, area, origin, cutoff, rows, "RESEARCH_SHADOW")
    assert not r["complete"] and r["values"]["past_7d_harvest_kg"] is None


@pytest.mark.parametrize("state", ["UNKNOWN", "PARTIAL", "MISSING", "CONFLICTING"])
def test_missing_progress_is_not_zero_filled(state):
    calendar, area, origin, cutoff, rows = inputs()
    rows[34] = rows[34].model_copy(update={"record_state": state, "quantity_kg": None})
    assert not harvest_features(calendar, area, origin, cutoff, rows, "RESEARCH_SHADOW")["complete"]


def test_past_dates_do_not_establish_historical_available_at():
    calendar, area, origin, cutoff, rows = inputs()
    rows = [
        r.model_copy(update={"source_recorded_at": None, "available_at_authority": "MISSING"})
        for r in rows
    ]
    assert not harvest_features(calendar, area, origin, cutoff, rows, "RESEARCH_SHADOW")["complete"]
    r = harvest_features(calendar, area, origin, cutoff, rows, "RETROSPECTIVE_DATE_BOUND")
    assert r["complete"] and r["visibility"] == "RETROSPECTIVE_DATE_BOUND" and not r["strict_pit"]


def test_m0_can_remain_a_control_when_m1_is_incomplete():
    from backend.tests.rolling_forecast.training_fixture import frozen_pair

    calendar, area, origin, cutoff, rows = inputs()
    pair = frozen_pair()
    r = forecast(calendar, area, origin, cutoff, rows[:-20], pair, "RESEARCH_SHADOW")
    assert r["models"]["M0"]["status"] == "COMPUTED"
    assert r["models"]["M1"]["status"] == "NOT_COMPUTABLE"
    assert r["models"]["M1"]["daily_forecast_kg"] == []
    complete = forecast(calendar, area, origin, cutoff, rows, pair, "RESEARCH_SHADOW")
    assert complete == forecast(calendar, area, origin, cutoff, rows, pair, "RESEARCH_SHADOW")
    for rr in complete["models"].values():
        daily = rr["daily_forecast_kg"]
        assert len(daily) == 15 and daily[0]["date"] == "2026-08-06"
        assert daily[-1]["date"] == "2026-08-20"
        assert Decimal(rr["H7"]["forecast_total_kg"]) == sum(Decimal(x["kg"]) for x in daily[:7])
        assert all(Decimal(x["kg"]) >= 0 and len(x["kg"].split(".")[1]) == 6 for x in daily)
        assert rr["H15"]["rolling_7day_peak_end"] <= "2026-08-20"
