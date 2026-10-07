"""Synthetic-only missing-safe ForecastOps contract tests."""

from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from backend.app.forecast_intelligence import forecast_ops as ops

D = Decimal
ORIGIN = datetime.fromisoformat("2025-11-01T17:00:00+08:00")
AS_OF = ORIGIN + timedelta(days=17)
IDENTITY = {
    "model_id": "SYNTHETIC",
    "policy_version": "FIXTURE",
    "schema_version": "1",
    "source_split": "SYNTHETIC",
    "prediction_hash": "a" * 64,
    "model_artifact_hash": "b" * 64,
    "model_config_hash": "c" * 64,
}


def fixture(count=1):
    forecasts, actuals = [], []
    for b in range(count):
        daily = tuple(
            ops.DailyForecast(d, ORIGIN.date() + timedelta(days=d), D(10)) for d in range(1, 16)
        )
        forecasts.append(ops.ForecastOrigin(str(b), "SYNTHETIC", ORIGIN, daily, dict(IDENTITY)))
        actuals.extend(ops.ActualPoint(str(b), "SYNTHETIC", r.target_date, D(5)) for r in daily)
    return forecasts, actuals


def monitor(forecasts=None, actuals=None, **kwargs):
    f, a = fixture()
    f = f if forecasts is None else forecasts
    a = a if actuals is None else actuals
    return ops.monitor(
        f,
        a,
        expected_slots=[ops.slot(x) for x in fixture()[0]],
        source_identity=IDENTITY,
        evaluation_as_of=AS_OF,
        **kwargs,
    )


def test_prefix_and_exact_lead_metrics():
    r = monitor()
    for h in (1, 3, 7, 15):
        m = r["point_quality"][f"H{h}"]
        assert m["daily_row_count"] == h
        assert D(m["daily_wape"]) == 1
        assert D(m["daily_mae_kg"]) == D(m["daily_bias_kg"]) == 5
        assert D(m["cumulative_wape"]) == 1
    assert r["lead_quality"]["D7"]["daily_row_count"] == 1


def test_missing_not_zero_and_partial_explicit():
    f, a = fixture(2)
    a = [
        x
        for x in a
        if not (x.base_id == "1" and x.target_date == ORIGIN.date() + timedelta(days=2))
    ]
    r = ops.monitor(
        f,
        a,
        expected_slots=[ops.slot(x) for x in f],
        source_identity=IDENTITY,
        evaluation_as_of=AS_OF,
    )
    c = r["completeness"]["H3"]
    assert (
        c["matured_origin_count"],
        c["actual_partial_origin_count"],
        c["scorable_origin_count"],
    ) == (2, 1, 1)
    assert c["origin_scoring_coverage"] == "0.5"
    assert r["point_quality"]["H3"]["daily_row_count"] == 3
    assert any(x["actual_completeness"] == "PARTIAL" for x in r["private_gates"])


def test_zero_complete_but_wape_undefined():
    f, a = fixture()
    r = monitor(f, [replace(x, quantity_kg=D(0)) for x in a])
    m = r["point_quality"]["H3"]
    assert m["daily_wape"] is None and m["cumulative_wape"] is None
    assert m["wape_status"] == "NOT_COMPUTABLE_ZERO_ACTUAL_DENOMINATOR"
    assert m["daily_mae_kg"] == "10" and m["daily_bias_kg"] == "10"
    assert r["completeness"]["H3"]["actual_complete_origin_count"] == 1


def test_maturity_empty_and_no_mature_data():
    f, a = fixture()
    r = ops.monitor(
        f,
        a,
        expected_slots=[ops.slot(x) for x in f],
        source_identity=IDENTITY,
        evaluation_as_of=ORIGIN + timedelta(days=3),
    )
    assert r["point_quality"]["H3"]["scoring_readiness"] == "INSUFFICIENT_DATA"
    assert r["completeness"]["H3"]["actual_partial_origin_count"] == 0
    assert monitor(f, [])["point_quality"]["H15"]["scoring_readiness"] == "NOT_SCORABLE"


def test_cumulative_cancellation_and_negative_bias():
    f, a = fixture()
    a = [
        replace(x, quantity_kg=D(20) if i == 0 else D(0) if i == 1 else D(10))
        for i, x in enumerate(a)
    ]
    r = monitor(f, a)
    assert D(r["point_quality"]["H3"]["daily_wape"]) > 0
    assert D(r["point_quality"]["H3"]["cumulative_wape"]) == 0
    assert D(r["point_quality"]["H1"]["daily_bias_kg"]) < 0


def test_issuance_target_coverage_and_rerun():
    f, a = fixture(100)
    r = ops.monitor(
        f[:90],
        a,
        expected_slots=[ops.slot(x) for x in f],
        source_identity=IDENTITY,
        evaluation_as_of=AS_OF,
    )
    assert r["issuance"]["issuance_coverage"] == "0.9"
    assert D(r["issuance"]["forecast_target_coverage"]) == D("0.9")
    f, a = fixture()
    assert (
        monitor(f + [replace(f[0], is_rerun=True)], a)["issuance"]["valid_issuance_origin_count"]
        == 1
    )
    r = monitor([replace(f[0], daily=f[0].daily[:-1])], a)
    assert r["integrity_status"] == "SCHEMA_DRIFT"
    assert r["issuance"]["valid_forecast_target_row_count"] == 14
    assert r["point_quality"]["H1"]["daily_wape"] is None


def test_duplicate_issuance_target_and_actual():
    f, a = fixture()
    assert monitor(f + f, a)["integrity_status"] == "DUPLICATE_ISSUANCE"
    assert (
        monitor([replace(f[0], daily=f[0].daily + (f[0].daily[0],))], a)["integrity_status"]
        == "ROWSET_INTEGRITY_FAILED"
    )
    with pytest.raises(ValueError, match="ACTUAL_DUPLICATE_CONFLICT"):
        monitor(f, a + a[:1])


@pytest.mark.parametrize("key", list(IDENTITY))
def test_source_drift_no_quality(key):
    f, a = fixture()
    changed = dict(IDENTITY) | {key: "drift"}
    r = monitor([replace(f[0], source_identity=changed)], a)
    assert r["integrity_status"] == "SOURCE_DRIFT"
    assert r["point_quality"]["H15"]["scoring_readiness"] == "NOT_SCORABLE"


@pytest.mark.parametrize("value", [D(-1), D("NaN"), D("Infinity"), 1.0])
def test_numeric_schema_drift(value):
    f, a = fixture()
    r = monitor(
        [replace(f[0], daily=(replace(f[0].daily[0], predicted_kg=value),) + f[0].daily[1:])], a
    )
    assert r["integrity_status"] == "SCHEMA_DRIFT"


def test_interval_inclusive_width_and_not_computable():
    f, a = fixture()
    intervals = [ops.IntervalPoint(ops.slot(f[0]), d, 80, D(5), D(7), D(12)) for d in range(1, 16)]
    intervals += [ops.IntervalPoint(ops.slot(f[0]), d, 90, None, None, None) for d in range(1, 16)]
    r = monitor(f, a, intervals=intervals, interval_policy_hash="d" * 64)
    assert r["interval_quality"]["H3"]["PI80"]["empirical_coverage"] == "1"
    assert r["interval_quality"]["H3"]["PI80"]["mean_width_kg"] == "2"
    assert r["interval_quality"]["H3"]["PI90"]["not_computable_row_count"] == 3
    bad = [replace(intervals[0], lower_kg=D(8))]
    assert (
        monitor(f, a, intervals=bad, interval_policy_hash="d" * 64)["integrity_status"]
        == "SCHEMA_DRIFT"
    )


def test_trend_comparability_and_rules():
    r = monitor()
    assert r["quality_trend"] == "NO_REFERENCE"
    assert monitor(reference=r)["quality_trend"] == "UNCHANGED"
    f, a = fixture()
    assert (
        monitor(f, [replace(x, quantity_kg=D(9)) for x in a], reference=r)["quality_trend"]
        == "IMPROVED"
    )
    assert (
        monitor(f, [replace(x, quantity_kg=D(2)) for x in a], reference=r)["quality_trend"]
        == "OBSERVED_DEGRADATION"
    )
    assert ops.trend([D(1), D(3)], [D(2), D(2)]) == "MIXED"
    assert monitor(reference=dict(r, scope="OTHER"))["quality_trend"] == "NO_REFERENCE"


def test_current_season_rejected_before_filter_and_naive_time():
    f, a = fixture()
    with pytest.raises(ValueError, match="FAIL_CURRENT_SEASON_ACTUAL_PRESENT"):
        monitor(f, a + [replace(a[0], season="2026-2027")])
    with pytest.raises(ValueError, match="TIMEZONE_REQUIRED"):
        ops.runtime_observability([], datetime(2025, 1, 1))


def test_runtime_latency_no_invented_freshness():
    event = ops.IssuanceEvent(
        "slot",
        "id",
        ORIGIN,
        ORIGIN + timedelta(seconds=2),
        ORIGIN + timedelta(seconds=7),
        "SUCCESS",
        "m",
        "p",
        "a" * 64,
        "b" * 64,
    )
    r = ops.runtime_observability([event], ORIGIN + timedelta(seconds=10), ["slot", "absent"])
    assert r["events"][0]["start_delay_seconds"] == "2"
    assert r["events"][0]["execution_latency_seconds"] == "5"
    assert r["events"][0]["completion_delay_seconds"] == "7"
    assert r["age_seconds"] == "3" and r["expected_slot_missing_count"] == 1
    assert "STALE" not in str(r)
    assert (
        ops.runtime_observability([], AS_OF)["latency_status"]
        == "NOT_COMPUTABLE_NO_RUNTIME_TIMESTAMP_AUTHORITY"
    )


def test_input_order_and_context_determinism():
    f, a = fixture()
    r = monitor(f, a)
    shuffled = monitor([replace(f[0], daily=tuple(reversed(f[0].daily)))], list(reversed(a)))
    assert r == shuffled
    assert r["production_alert_status"] == "NOT_CONFIGURED_NO_PRODUCTION_THRESHOLDS"
    assert r["result_hash"]


def test_exact_date_matching_no_nearest_fill():
    f, a = fixture()
    # A neighbouring day is never a replacement for the missing exact date.
    a = [x for x in a if x.target_date != ORIGIN.date() + timedelta(days=3)]
    r = monitor(f, a)
    assert r["completeness"]["H3"]["actual_partial_origin_count"] == 1
    assert r["point_quality"]["H3"]["daily_wape"] is None


def test_interval_upper_endpoint_and_input_order():
    f, a = fixture()
    a = [replace(x, quantity_kg=D(7)) for x in a]
    intervals = [
        ops.IntervalPoint(ops.slot(f[0]), d, level, D(5), D(7), D(12))
        for d in range(1, 16)
        for level in (80, 90)
    ]
    r = monitor(f, a, intervals=intervals, interval_policy_hash="a" * 64)
    assert r["interval_quality"]["H15"]["PI90"]["covered_row_count"] == 15
    assert (
        monitor(
            f, list(reversed(a)), intervals=list(reversed(intervals)), interval_policy_hash="a" * 64
        )
        == r
    )


def test_source_hash_shape_and_bad_calendar():
    f, a = fixture()
    bad = dict(IDENTITY, prediction_hash="A" * 64)
    r = ops.monitor(
        [replace(f[0], source_identity=bad)],
        a,
        expected_slots=[ops.slot(f[0])],
        source_identity=bad,
        evaluation_as_of=AS_OF,
    )
    assert r["integrity_status"] == "SOURCE_DRIFT"
    daily = (replace(f[0].daily[0], target_date=date(2025, 1, 1)),) + f[0].daily[1:]
    assert monitor([replace(f[0], daily=daily)], a)["integrity_status"] == "SCHEMA_DRIFT"
