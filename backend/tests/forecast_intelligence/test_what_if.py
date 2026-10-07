"""S6 pure contracts: exact quantities, derived utilization, no optimizer."""

from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta
from decimal import Decimal, Inexact, Rounded, localcontext

import pytest

from backend.app.forecast_intelligence import what_if as w
from backend.app.forecast_intelligence.business_loss import synthetic_contracts

D = Decimal


def scenario(demands=("200", "50", "50"), capacities=("100", "120", "100"), sid="A"):
    days = tuple(date(2025, 1, 1) + timedelta(days=i) for i in range(len(demands)))
    curve = w.SavedForecastCurve(
        "SYNTHETIC",
        "a" * 64,
        datetime.fromisoformat("2024-12-31T17:00:00+08:00"),
        "COMPANY",
        "SYNTHETIC_COMPANY",
        "b" * 64,
        tuple(
            w.SavedForecastDay(d, D(v), D(v) + D(20), D(v) + D(40))
            for d, v in zip(days, demands, strict=True)
        ),
    )
    return w.DecisionScenario(
        sid,
        "R1",
        curve,
        "POINT",
        synthetic_contracts()[0],
        tuple(
            w.CapacityDay(d, "DIRECT", D(v), None, None, True, D(0))
            for d, v in zip(days, capacities, strict=True)
        ),
    )


@pytest.mark.parametrize(
    "n,d,text,rounded",
    [("80", "140", "0." + "571428" * 8 + "57", True), ("50", "100", "0.5", False)],
)
def test_utilization_exception(n, d, text, rounded):
    result = w.utilization(Decimal(n), Decimal(d), "capacity_utilization")
    assert result["capacity_utilization_decimal"] == text
    assert result["capacity_utilization_rounding_applied"] is rounded
    assert result["capacity_utilization_numerator_kg"] == n
    assert result["capacity_utilization_denominator_kg"] == d
    with localcontext() as ctx:
        ctx.prec = 2
        assert result == w.utilization(Decimal(n), Decimal(d), "capacity_utilization")


def test_zero_capacity():
    result = w.utilization(Decimal(0), Decimal(0), "capacity_utilization")
    assert result["capacity_utilization_decimal"] is None
    assert result["capacity_utilization_status"] == "NOT_COMPUTABLE_ZERO_CAPACITY"
    assert result["capacity_utilization_rounding_applied"] is False


def test_aggregate_utilization_and_context():
    expected = w.utilization(D(240), D(420), "aggregate_capacity_utilization")
    assert expected["aggregate_capacity_utilization_numerator_kg"] == "240"
    assert expected["aggregate_capacity_utilization_denominator_kg"] == "420"
    assert expected["aggregate_capacity_utilization_decimal"] == "0." + "571428" * 8 + "57"
    with localcontext() as ctx:
        ctx.prec = 2
        ctx.traps[Inexact] = True
        ctx.traps[Rounded] = True
        assert expected == w.utilization(D(240), D(420), "aggregate_capacity_utilization")


def test_backlog_growth_recovery_balance():
    s = scenario()
    r = w.simulate(s)
    assert [row["closing_backlog_kg"] for row in r["daily_rows"]] == ["100", "30", "0"]
    assert r["cumulative_shortfall_kg"] == "100"
    assert r["max_backlog_kg"] == "100"
    assert r["ending_backlog_kg"] == "0"
    assert r["overload_dates"] == ["2025-01-01"]
    assert r["backlog_dates"] == ["2025-01-01", "2025-01-02"]
    assert r["daily_rows"][1]["daily_overload_kg"] == "0"
    previous = D(0)
    for row in r["daily_rows"]:
        assert D(row["opening_backlog_kg"]) == previous
        assert previous + D(row["planning_demand_kg"]) == D(row["processed_kg"]) + D(
            row["closing_backlog_kg"]
        )
        assert D(row["processed_kg"]) <= D(row["effective_capacity_kg"])
        assert row["under_capacity_kg"] == row["daily_overload_kg"]
        previous = D(row["closing_backlog_kg"])
    assert r["total_business_loss"] == "220"
    assert w.digest({k: v for k, v in r.items() if k != "result_hash"}) == r["result_hash"]


@pytest.mark.parametrize(
    "d,c,over,under,processed",
    [("0", "100", "100", "0", "0"), ("100", "0", "0", "100", "0"), ("100", "100", "0", "0", "100")],
)
def test_zero_exact_capacity(d, c, over, under, processed):
    r = w.simulate(scenario((d,), (c,)))
    row = r["daily_rows"][0]
    assert row["over_capacity_kg"] == over
    assert row["under_capacity_kg"] == under
    assert row["processed_kg"] == processed
    if c == "0":
        assert row["capacity_utilization_decimal"] is None
        assert r["aggregate_capacity_utilization_decimal"] is None


def test_buffer_additive_no_carry_and_workforce_parity():
    s = scenario(("0", "150"), ("120", "120"))
    capacities = tuple(
        w.CapacityDay(c.date, "WORKFORCE_DERIVED", None, 10, D(10), True, D(20))
        for c in s.capacity_rows
    )
    other = replace(s, scenario_id="B", capacity_rows=capacities)
    a, b = w.simulate(s), w.simulate(other)
    assert a["ending_backlog_kg"] == b["ending_backlog_kg"] == "30"
    assert a["total_business_loss"] == b["total_business_loss"]
    assert [r["effective_capacity_kg"] for r in b["daily_rows"]] == ["120", "120"]
    assert b["daily_rows"][0]["daily_handling_capacity_kg"] == "100"


@pytest.mark.parametrize(
    "field,value",
    [
        ("workforce_count", -1),
        ("workforce_count", 1.5),
        ("workforce_count", True),
        ("workforce_count", None),
        ("productivity_kg_per_person_day", None),
        ("productivity_kg_per_person_day", 1.5),
        ("productivity_kg_per_person_day", D(-1)),
        ("productivity_kg_per_person_day", D("NaN")),
        ("productivity_kg_per_person_day", D("Infinity")),
        ("daily_handling_capacity_kg", D(1)),
    ],
)
def test_workforce_reject(field, value):
    c = w.CapacityDay(date(2025, 1, 1), "WORKFORCE_DERIVED", None, 10, D(12), True, D(0))
    assert c.handling() == D(120)
    with pytest.raises(ValueError):
        replace(c, **{field: value})


@pytest.mark.parametrize(
    "field,value",
    [
        ("workforce_count", 1),
        ("productivity_kg_per_person_day", D(1)),
        ("daily_handling_capacity_kg", None),
        ("daily_handling_capacity_kg", 1.5),
        ("daily_handling_capacity_kg", D(-1)),
        ("daily_handling_capacity_kg", D("NaN")),
        ("buffer_handling_capacity_kg", 1.5),
        ("buffer_handling_capacity_kg", D(-1)),
        ("buffer_handling_capacity_kg", D("Infinity")),
        ("capacity_mode", "UNKNOWN"),
    ],
)
def test_direct_and_buffer_reject(field, value):
    with pytest.raises(ValueError):
        replace(scenario().capacity_rows[0], **{field: value})


def test_explicit_absent_buffer():
    c = replace(scenario().capacity_rows[0], buffer_supplied=False)
    assert c.buffer_handling_capacity_kg == 0
    with pytest.raises(ValueError, match="BUFFER_CONTRACT_INVALID"):
        replace(c, buffer_handling_capacity_kg=D(1))


@pytest.mark.parametrize(
    "level,expected",
    [("POINT", "100"), ("UPPER_PLANNING_BOUND_80", "120"), ("UPPER_PLANNING_BOUND_90", "140")],
)
def test_planning_selection(level, expected):
    r = w.simulate(replace(scenario(("100",), ("100",)), planning_level=level))
    assert r["total_planning_demand_kg"] == expected


@pytest.mark.parametrize("level", ["P50", "P80", "P90", "UNKNOWN"])
def test_legacy_alias_forbidden(level):
    with pytest.raises(ValueError, match="SCENARIO_SCHEMA_INVALID"):
        replace(scenario(), planning_level=level)


def test_missing_selected_bound_no_fallback():
    s = scenario(("100",), ("100",))
    curve = replace(
        s.saved_forecast,
        daily_rows=(replace(s.saved_forecast.daily_rows[0], upper_planning_bound_80_kg=None),),
    )
    assert w.simulate(replace(s, saved_forecast=curve))["total_planning_demand_kg"] == "100"
    with pytest.raises(ValueError, match="BLOCKED_INCOMPLETE_PLANNING_CURVE"):
        w.simulate(replace(s, saved_forecast=curve, planning_level="UPPER_PLANNING_BOUND_80"))


def test_date_missing_duplicate_and_immutability():
    s = scenario()
    for rows in (
        (s.saved_forecast.daily_rows[0],) * 2,
        (s.saved_forecast.daily_rows[0], s.saved_forecast.daily_rows[2]),
    ):
        with pytest.raises(ValueError, match="FORECAST_DATE_CONTINUITY_FAILED"):
            replace(s.saved_forecast, daily_rows=rows)
    for rows in (s.capacity_rows[:-1], s.capacity_rows + (s.capacity_rows[0],)):
        with pytest.raises(ValueError, match="CAPACITY_DATE_COVERAGE_MISMATCH"):
            replace(s, capacity_rows=rows)
    with pytest.raises(FrozenInstanceError):
        s.scenario_id = "other"
    reverse = replace(
        s,
        saved_forecast=replace(s.saved_forecast, daily_rows=s.saved_forecast.daily_rows[::-1]),
        capacity_rows=s.capacity_rows[::-1],
    )
    assert s.scenario_hash == reverse.scenario_hash
    assert w.simulate(s) == w.simulate(reverse)


@pytest.mark.parametrize(
    "field,value",
    [
        ("hierarchy_level", "FARM"),
        ("hierarchy_level", "FACTORY"),
        ("forecast_source_hash", "X" * 64),
        ("hierarchy_authority_hash", "a" * 63),
        ("forecast_origin", datetime(2025, 1, 1)),
        ("point_is_proven_p50", True),
        ("upper_planning_bound_is_quantile", True),
    ],
)
def test_saved_forecast_contract_reject(field, value):
    with pytest.raises(ValueError):
        replace(scenario().saved_forecast, **{field: value})


def test_source_identity_changed_payload_reject():
    s = scenario()
    f = replace(s.saved_forecast, hierarchy_authority_hash="c" * 64)
    with pytest.raises(ValueError, match="SOURCE_FORECAST_DRIFT"):
        w.verify_saved_forecast(f, s.saved_forecast.saved_forecast_hash)
    with pytest.raises(ValueError, match="SOURCE_FORECAST_DRIFT"):
        w.compare_and_rank((s, replace(s, scenario_id="B", saved_forecast=f)))


@pytest.mark.parametrize(
    "change",
    [
        "source",
        "curve",
        "origin",
        "level",
        "entity",
        "hierarchy",
        "planning",
        "dates",
        "cost",
        "unit",
    ],
)
def test_comparison_authority_mismatch(change):
    s = scenario()
    f = replace(s.saved_forecast, forecast_source_id="OTHER_SYNTHETIC")
    b = replace(s, scenario_id="B", saved_forecast=f)
    if change == "source":
        b = replace(b, saved_forecast=replace(f, forecast_source_hash="c" * 64))
    elif change == "curve":
        b = replace(
            b,
            saved_forecast=replace(
                f, daily_rows=(replace(f.daily_rows[0], point_forecast_kg=D(1)), *f.daily_rows[1:])
            ),
        )
    elif change == "origin":
        b = replace(
            b, saved_forecast=replace(f, forecast_origin=f.forecast_origin + timedelta(hours=1))
        )
    elif change == "level":
        b = replace(b, saved_forecast=replace(f, hierarchy_level="REGION"))
    elif change == "entity":
        b = replace(b, saved_forecast=replace(f, hierarchy_entity_id="OTHER"))
    elif change == "hierarchy":
        b = replace(b, saved_forecast=replace(f, hierarchy_authority_hash="c" * 64))
    elif change == "planning":
        b = replace(b, planning_level="UPPER_PLANNING_BOUND_80")
    elif change == "dates":
        b = replace(
            b,
            saved_forecast=replace(f, daily_rows=f.daily_rows[:-1]),
            capacity_rows=b.capacity_rows[:-1],
        )
    elif change == "cost":
        b = replace(b, cost=synthetic_contracts()[1])
    else:
        b = replace(
            b,
            cost=replace(
                b.cost,
                authority_type="OWNER_BUSINESS_SUPPLIED",
                synthetic=False,
                loss_unit="EXPLICIT_TEST_UNIT",
            ),
        )
    result = w.compare_and_rank((s, b))
    assert result["scenario_comparison_status"] == "NOT_COMPARABLE_AUTHORITY_MISMATCH"
    assert result["rankings"] == []


def test_ranking_conditional_cost_and_lexical_tie():
    a = scenario(("80",), ("80",), "A")
    b = replace(
        a,
        scenario_id="B",
        capacity_rows=(replace(a.capacity_rows[0], daily_handling_capacity_kg=D(100)),),
    )
    c = replace(b, scenario_id="C")
    r = w.compare_and_rank((c, b, a))
    assert [v["scenario_id"] for v in r["rankings"]] == ["A", "B", "C"]
    assert r == w.compare_and_rank((a, b, c))
    with pytest.raises(ValueError, match="SCENARIO_DUPLICATE_OR_EMPTY"):
        w.compare_and_rank((a, a))
    with pytest.raises(ValueError, match="SCENARIO_DUPLICATE_OR_EMPTY"):
        w.compare_and_rank((a, replace(b, scenario_id="A")))


def test_exception_isolation_and_no_rounding_feedback():
    s = scenario(("1",), ("1",))
    precise = replace(
        s, capacity_rows=(replace(s.capacity_rows[0], buffer_handling_capacity_kg=D("1e-60")),)
    )
    with pytest.raises(ValueError, match="AUTHORITATIVE_PRECISION_EXCEEDED"):
        w.simulate(precise)
    cost = replace(s.cost, c_under_per_kg=D("1." + "2" * 49))
    with pytest.raises(ValueError, match="AUTHORITATIVE_PRECISION_EXCEEDED"):
        w.simulate(
            replace(
                s,
                cost=cost,
                capacity_rows=(replace(s.capacity_rows[0], daily_handling_capacity_kg=D("0.89")),),
            )
        )
    r = w.simulate(s)
    with localcontext() as ctx:
        ctx.prec = 2
        ctx.traps[Rounded] = True
        assert r == w.simulate(s)
    assert "utilization" not in str(s.payload())


def test_rounding_does_not_change_ranking(monkeypatch):
    a = scenario(("80",), ("140",), "A")
    b = replace(a, scenario_id="B")
    expected = [r["scenario_id"] for r in w.compare_and_rank((b, a))["rankings"]]
    original = w.utilization

    def changed(n, d, prefix):
        return original(n, d, prefix) | {f"{prefix}_decimal": "0.123"}

    monkeypatch.setattr(w, "utilization", changed)
    assert expected == [r["scenario_id"] for r in w.compare_and_rank((b, a))["rankings"]]


@pytest.mark.parametrize("index", range(4))
def test_each_ranking_key_precedes_later_keys(index, monkeypatch):
    a = scenario(sid="A")
    b = replace(a, scenario_id="B")
    fields = (
        "total_business_loss",
        "max_backlog_kg",
        "cumulative_shortfall_kg",
        "ending_backlog_kg",
    )

    def evaluated(s):
        values = ["10"] * 4
        values[index] = "1" if s.scenario_id == "B" else "2"
        for j in range(index + 1, 4):
            values[j] = "999" if s.scenario_id == "B" else "0"
        return dict(zip(fields, values, strict=True)) | {
            "scenario_id": s.scenario_id,
            "scenario_hash": s.scenario_hash,
            "result_hash": "a" * 64,
        }

    monkeypatch.setattr(w, "simulate", evaluated)
    assert w.compare_and_rank((a, b))["rankings"][0]["scenario_id"] == "B"


@pytest.mark.parametrize("value", [1.0, -1, Decimal(-1), Decimal("NaN"), Decimal("Infinity")])
def test_saved_quantity_reject(value):
    with pytest.raises(ValueError, match="SOURCE_NUMERIC_INVALID"):
        w.SavedForecastDay(date(2025, 1, 1), value, None, None)


def test_empty_contract_and_capacity_multiplication_precision():
    s = scenario()
    for field in ("scenario_id", "scenario_version"):
        with pytest.raises(ValueError, match="SCENARIO_SCHEMA_INVALID"):
            replace(s, **{field: ""})
    c = w.CapacityDay(
        date(2025, 1, 1), "WORKFORCE_DERIVED", None, 999, D("1." + "2" * 49), True, D(0)
    )
    with pytest.raises(ValueError, match="AUTHORITATIVE_PRECISION_EXCEEDED"):
        c.handling()
