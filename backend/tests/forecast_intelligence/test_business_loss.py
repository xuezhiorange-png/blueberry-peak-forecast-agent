"""Synthetic-only asymmetric loss and fair-comparison contracts."""

from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta
from decimal import Decimal as D

import pytest

from backend.app.forecast_intelligence import business_loss as loss


def targets(n=15):
    origin = datetime.fromisoformat("2025-11-01T17:00:00+08:00")
    return [
        loss.LossTarget(
            f"SYNTHETIC#D{d:02}",
            "SYNTHETIC",
            "2025-2026",
            origin,
            d,
            origin.date() + timedelta(days=d),
        )
        for d in range(1, n + 1)
    ]


def fixture():
    rows = targets()
    actuals = [loss.ActualObservation(t, D(100)) for t in rows]
    candidates = [
        loss.ForecastCandidate(
            name, char * 64, tuple(loss.CandidateValue(t, D(value)) for t in rows)
        )
        for name, char, value in (
            (loss.POINT, "a", 80),
            (loss.UP80, "b", 110),
            (loss.UP90, "c", 120),
        )
    ]
    return rows, actuals, candidates


@pytest.mark.parametrize(
    "actual,forecast,expected",
    [
        (100, 80, (20, 0, 80, 0, 80)),
        (80, 100, (0, 20, 0, 20, 20)),
        (100, 100, (0, 0, 0, 0, 0)),
        (0, 20, (0, 20, 0, 20, 20)),
    ],
)
def test_manual_loss(actual, forecast, expected):
    r = loss.row_loss(D(actual), D(forecast), loss.synthetic_contracts()[1])
    assert tuple(r.values()) == tuple(map(D, expected))
    assert D(actual) - D(forecast) == r["underforecast_kg"] - r["overforecast_kg"]


@pytest.mark.parametrize("value", [D(-1), D("NaN"), D("Infinity"), D("-Infinity"), 1.5, 1, None])
def test_numeric_rejection(value):
    c = loss.synthetic_contracts()[0]
    for kwargs in ({"c_under_per_kg": value}, {"c_over_per_kg": value}):
        with pytest.raises(ValueError):
            replace(c, **kwargs)
    with pytest.raises(ValueError):
        loss.row_loss(value, D(1), c)
    with pytest.raises(ValueError):
        loss.row_loss(D(1), value, c)


@pytest.mark.parametrize(
    "changes",
    [
        {"authority_type": "FAKE"},
        {"authority_reference": ""},
        {"loss_unit": ""},
        {"loss_unit": "CNY"},
        {"synthetic": False},
        {"canonical_company_cost": True},
        {"contract_id": ""},
        {"policy_version": "DRIFT"},
        {"contract_version": ""},
    ],
)
def test_cost_authority(changes):
    with pytest.raises(ValueError):
        replace(loss.synthetic_contracts()[0], **changes)


def test_contract_identity_immutable_and_sensitivity():
    balanced, under, over = loss.synthetic_contracts()
    assert len({c.contract_hash for c in (balanced, under, over)}) == 3
    assert replace(balanced, c_under_per_kg=D("1.00")).contract_hash == balanced.contract_hash
    with pytest.raises(FrozenInstanceError):
        balanced.synthetic = False
    with pytest.raises(TypeError):
        loss.BusinessCostContract(contract_id="MISSING")
    for actual, point in ((100, 80), (80, 100)):
        a, b, c = [
            loss.row_loss(D(actual), D(point), contract) for contract in (balanced, under, over)
        ]
        assert a["underforecast_kg"] == b["underforecast_kg"] == c["underforecast_kg"]
        assert a["overforecast_kg"] == b["overforecast_kg"] == c["overforecast_kg"]
        assert b["underforecast_loss"] == 4 * a["underforecast_loss"]
        assert b["overforecast_loss"] == a["overforecast_loss"]
        assert c["overforecast_loss"] == 4 * a["overforecast_loss"]
        assert c["underforecast_loss"] == a["underforecast_loss"]


def evaluate(rows, actuals, candidates, cost=None):
    return loss.evaluate_comparison(
        cost or loss.synthetic_contracts()[0],
        rows,
        actuals,
        candidates,
        actual_authority_hash="d" * 64,
    )


def test_fair_aggregation_and_order():
    rows, actuals, candidates = fixture()
    result = evaluate(rows, actuals, candidates)
    assert result == evaluate(
        rows[::-1], actuals[::-1], [replace(c, rows=c.rows[::-1]) for c in candidates[::-1]]
    )
    for h in (1, 3, 7, 15):
        group = result[f"H{h}"]
        assert group["common_comparable_row_count"] == h
        assert group["scorable_origin_count"] == 1
        assert group["candidates"][loss.POINT]["total_business_loss"] == str(20 * h)
        assert group["candidates"][loss.UP80]["loss_delta_vs_point"] == str(-10 * h)
        assert group["comparison_status"] == "COMPARABLE"


def test_missing_prefix_not_zero():
    rows, actuals, cs = fixture()
    cs[1] = replace(
        cs[1], rows=cs[1].rows[:1] + (replace(cs[1].rows[1], value_kg=None),) + cs[1].rows[2:]
    )
    r = evaluate(rows, actuals, cs)
    assert r["H1"]["common_comparable_row_count"] == 1
    assert r["H3"]["common_comparable_row_count"] == 0
    assert r["H3"]["comparison_status"] == "NOT_COMPARABLE_INCOMPLETE_ROWSET"
    assert r["H3"]["candidates"] == {}
    assert evaluate(rows, actuals[1:], cs)["H1"]["candidates"] == {}


def test_comparison_gate():
    rows, actuals, cs = fixture()
    items = evaluate(rows, actuals, cs)["H7"]["candidates"]
    a, b = items[loss.POINT], items[loss.UP80]
    loss.compare_aggregates(a, b)
    for field in (
        "cost_contract_hash",
        "comparison_rowset_hash",
        "actual_authority_hash",
        "target_semantics",
    ):
        with pytest.raises(ValueError, match="COMPARISON_CONTRACT_MISMATCH"):
            loss.compare_aggregates(a, dict(b, **{field: "DRIFT"}))


def test_duplicate_and_source_conflicts():
    rows, actuals, cs = fixture()
    for ar, candidates in (
        (actuals + [actuals[0]], cs),
        (actuals, cs + [cs[0]]),
        (actuals, [replace(cs[0], rows=cs[0].rows + cs[0].rows[:1]), *cs[1:]]),
    ):
        with pytest.raises(ValueError):
            evaluate(rows, ar, candidates)
    with pytest.raises(ValueError, match="CANDIDATE_SOURCE_DRIFT"):
        loss.evaluate_comparison(
            loss.synthetic_contracts()[0],
            rows,
            actuals,
            cs,
            actual_authority_hash="d" * 64,
            expected_candidate_hashes={c.candidate_id: "e" * 64 for c in cs},
        )
    with pytest.raises(ValueError):
        evaluate(rows, actuals, [replace(cs[0], source_hash="bad"), *cs[1:]])


def test_current_season_before_numeric_and_schema():
    rows, actuals, cs = fixture()
    current = replace(rows[0], season="2026-2027")
    with pytest.raises(ValueError, match="FAIL_CURRENT_SEASON_ACTUAL_PRESENT"):
        evaluate(rows, [loss.ActualObservation(current, object()), *actuals], cs)
    with pytest.raises(ValueError):
        evaluate([replace(rows[0], target_date=date(2025, 1, 1)), *rows[1:]], actuals, cs)


def test_owner_contract_mechanics_only():
    owner = replace(
        loss.synthetic_contracts()[0],
        authority_type="OWNER_BUSINESS_SUPPLIED",
        authority_reference="SYNTHETIC_SCHEMA_TEST_NOT_COMPANY_AUTHORITY",
        synthetic=False,
        loss_unit="TEST_MECHANICS_UNIT",
    )
    assert owner.canonical_company_cost is False
    assert owner.contract_hash != loss.synthetic_contracts()[0].contract_hash


def test_changed_payload_same_candidate_identity():
    rows, actuals, cs = fixture()
    a = evaluate(rows, actuals, cs)["H1"]["candidates"][loss.POINT]
    with pytest.raises(ValueError, match="CANDIDATE_SOURCE_DRIFT"):
        loss.compare_aggregates(a, dict(a, candidate_payload_hash="f" * 64))
    with pytest.raises(ValueError, match="SOURCE_NUMERIC_INVALID"):
        loss.compare_aggregates(a, dict(a, total_business_loss=20.0))


def test_confirmed_zero_aggregate_and_missing_candidate_counts():
    rows, actuals, cs = fixture()
    result = evaluate(rows, [loss.ActualObservation(t, D(0)) for t in rows], cs)
    assert result["H3"]["candidates"][loss.POINT]["overforecast_kg"] == "240"
    cs[2] = replace(cs[2], rows=cs[2].rows[1:])
    result = evaluate(rows, actuals, cs)["H1"]
    assert result["candidate_source_row_count"][loss.UP90] == 0
    assert result["excluded_non_comparable_row_count"] == 1
    assert result["comparison_status"] == "NOT_COMPARABLE_INCOMPLETE_ROWSET"


def test_high_precision_not_silently_rounded_and_context_independent():
    from decimal import localcontext

    c = loss.synthetic_contracts()[0]
    with localcontext() as ctx:
        ctx.prec = 3
        assert loss.row_loss(D("100.123456789"), D("80.000000001"), c)["total_business_loss"] == D(
            "20.123456788"
        )
    with pytest.raises(ValueError, match="AUTHORITATIVE_PRECISION_EXCEEDED"):
        loss.row_loss(D("1e80"), D("1e-80"), c)


def test_conflicting_overlapping_actual_reference():
    rows, actuals, cs = fixture()
    first = rows[1]
    alternate = replace(
        first,
        row_key="SYNTHETIC_OTHER_ORIGIN",
        lead_day=1,
        forecast_origin=first.forecast_origin + timedelta(days=1),
    )
    with pytest.raises(ValueError, match="ACTUAL_DUPLICATE_CONFLICT"):
        evaluate([*rows, alternate], [*actuals, loss.ActualObservation(alternate, D(999))], cs)
