"""Pure, missing-safe retrospective ForecastOps. No IO, production thresholds or actions."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal, localcontext
from typing import Any
from zoneinfo import ZoneInfo

from backend.app.area_yield.v015_research_cohort import digest

POLICY_VERSION = "V0_16_FORECASTOPS_MONITORING_R1"
SCORING_POLICY_VERSION = "V0_16_FORECASTOPS_HORIZON_SCORING_R1"
ACTUAL_MATCH_POLICY_VERSION = "V0_16_EXACT_BASE_DATE_ACTUAL_MATCH_R1"
ISSUANCE_COVERAGE_POLICY_VERSION = "V0_16_FORECASTOPS_ISSUANCE_COVERAGE_R1"
QUALITY_TREND_POLICY_VERSION = "V0_16_FORECASTOPS_DESCRIPTIVE_TREND_R1"
HORIZONS = (1, 3, 7, 15)
SHANGHAI = ZoneInfo("Asia/Shanghai")
ZERO = Decimal(0)
SOURCE_FIELDS = {
    "model_id",
    "policy_version",
    "schema_version",
    "source_split",
    "prediction_hash",
    "model_artifact_hash",
    "model_config_hash",
}


@dataclass(frozen=True)
class DailyForecast:
    lead_day: int
    target_date: date
    predicted_kg: Decimal


@dataclass(frozen=True)
class ForecastOrigin:
    base_id: str
    season: str
    forecast_origin: datetime
    daily: tuple[DailyForecast, ...]
    source_identity: dict[str, str]
    is_rerun: bool = False


@dataclass(frozen=True)
class ActualPoint:
    base_id: str
    season: str
    target_date: date
    quantity_kg: Decimal


@dataclass(frozen=True)
class IntervalPoint:
    semantic_slot: tuple[str, str, str]
    lead_day: int
    level: int
    lower_kg: Decimal | None
    upper_kg: Decimal | None
    upper_planning_bound_kg: Decimal | None = None


@dataclass(frozen=True)
class IssuanceEvent:
    semantic_slot_id: str
    forecast_id: str
    scheduled_at: datetime
    started_at: datetime
    completed_at: datetime
    terminal_status: str
    model_id: str
    policy_version: str
    source_hash: str
    result_hash: str
    is_rerun: bool = False


def aware(value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("TIMEZONE_REQUIRED")


def slot(row: ForecastOrigin) -> tuple[str, str, str]:
    aware(row.forecast_origin)
    return row.base_id, row.season, row.forecast_origin.astimezone(SHANGHAI).isoformat()


def numeric(value: Any) -> bool:
    return isinstance(value, Decimal) and value.is_finite() and value >= 0


def ratio(n: int | Decimal, d: int | Decimal) -> str | None:
    return str(Decimal(n) / Decimal(d)) if d else None


def median(values: list[Decimal]) -> str | None:
    if not values:
        return None
    v = sorted(values)
    n = len(v)
    return str(v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2)


def metrics(cells: list[list[tuple[Decimal, Decimal]]], readiness: str) -> dict[str, Any]:
    pairs = [p for c in cells for p in c]
    actual = sum((a for _, a in pairs), ZERO)
    forecast = sum((p for p, _ in pairs), ZERO)
    ae = sum((abs(p - a) for p, a in pairs), ZERO)
    signed = sum((p - a for p, a in pairs), ZERO)
    ce = sum((abs(sum((p - a for p, a in c), ZERO)) for c in cells), ZERO)
    return {
        "scoring_readiness": readiness,
        "scorable_origin_count": len(cells),
        "daily_row_count": len(pairs),
        "daily_wape": ratio(ae, actual) if pairs else None,
        "daily_mae_kg": ratio(ae, len(pairs)),
        "daily_bias_kg": ratio(signed, len(pairs)),
        "absolute_daily_bias_kg": ratio(abs(signed), len(pairs)),
        "total_signed_bias_kg": str(signed) if pairs else None,
        "cumulative_wape": ratio(ce, actual) if pairs else None,
        "actual_sum_kg": str(actual),
        "forecast_sum_kg": str(forecast),
        "absolute_error_sum_kg": str(ae),
        "wape_status": "COMPUTABLE"
        if pairs and actual
        else "NOT_COMPUTABLE_ZERO_ACTUAL_DENOMINATOR"
        if pairs
        else "NOT_SCORABLE",
    }


def trend(current: list[Decimal], previous: list[Decimal]) -> str:
    if current == previous:
        return "UNCHANGED"
    if all(c <= p for c, p in zip(current, previous, strict=True)):
        return "IMPROVED"
    if all(c >= p for c, p in zip(current, previous, strict=True)):
        return "OBSERVED_DEGRADATION"
    return "MIXED"


def interval_summary(
    rows: list[tuple[Decimal, Decimal, IntervalPoint | None]], kind: str
) -> dict[str, Any]:
    covered = 0
    widths: list[Decimal] = []
    for point, actual, item in rows:
        if item is None:
            continue
        if kind == "PI" and item.lower_kg is not None and item.upper_kg is not None:
            covered += item.lower_kg <= actual <= item.upper_kg
            widths.append(item.upper_kg - item.lower_kg)
        elif kind == "UPPER" and item.upper_planning_bound_kg is not None:
            covered += actual <= item.upper_planning_bound_kg
            widths.append(item.upper_planning_bound_kg - point)
    field = "width" if kind == "PI" else "expansion"
    return {
        "candidate_row_count": len(rows),
        "computable_row_count": len(widths),
        "not_computable_row_count": len(rows) - len(widths),
        "covered_row_count": covered,
        "empirical_coverage": ratio(covered, len(widths)),
        f"mean_{field}_kg": ratio(sum(widths, ZERO), len(widths)),
        f"median_{field}_kg": median(widths),
        f"min_{field}_kg": str(min(widths)) if widths else None,
        f"max_{field}_kg": str(max(widths)) if widths else None,
    }


def runtime_observability(
    events: list[IssuanceEvent],
    evaluation_as_of: datetime,
    expected_slot_ids: list[str] | None = None,
) -> dict[str, Any]:
    aware(evaluation_as_of)
    rows = []
    for e in sorted(events, key=lambda x: (x.semantic_slot_id, x.forecast_id)):
        for t in (e.scheduled_at, e.started_at, e.completed_at):
            aware(t)
        if not e.scheduled_at <= e.started_at <= e.completed_at <= evaluation_as_of:
            raise ValueError("RUNTIME_TIMESTAMP_ORDER_INVALID")
        if any(not re.fullmatch("[0-9a-f]{64}", h) for h in (e.source_hash, e.result_hash)):
            raise ValueError("SOURCE_DRIFT")

        def seconds(delta: timedelta) -> str:
            return str(
                Decimal(delta.days * 86400 + delta.seconds) + Decimal(delta.microseconds) / 1000000
            )

        rows.append(
            {
                "semantic_slot_id": e.semantic_slot_id,
                "forecast_id": e.forecast_id,
                "start_delay_seconds": seconds(e.started_at - e.scheduled_at),
                "execution_latency_seconds": seconds(e.completed_at - e.started_at),
                "completion_delay_seconds": seconds(e.completed_at - e.scheduled_at),
            }
        )
    latest = max((e.completed_at for e in events), default=None)
    delta = evaluation_as_of - latest if latest else None
    present = {e.semantic_slot_id for e in events}
    return {
        "events": rows,
        "terminal_event_count": len(events),
        "successful_issuance_count": sum(e.terminal_status == "SUCCESS" for e in events),
        "failed_terminal_count": sum(e.terminal_status != "SUCCESS" for e in events),
        "expected_slot_present_count": len(present & set(expected_slot_ids))
        if expected_slot_ids is not None
        else None,
        "expected_slot_missing_count": len(set(expected_slot_ids) - present)
        if expected_slot_ids is not None
        else None,
        "latest_completed_at": latest.isoformat() if latest else None,
        "age_seconds": str(
            Decimal(delta.days * 86400 + delta.seconds) + Decimal(delta.microseconds) / 1000000
        )
        if delta
        else "0"
        if latest
        else None,
        "latency_status": "OBSERVED" if events else "NOT_COMPUTABLE_NO_RUNTIME_TIMESTAMP_AUTHORITY",
        "freshness_status": "OBSERVED_AGE_ONLY"
        if events
        else "NOT_COMPUTABLE_NO_RUNTIME_SCHEDULE_AUTHORITY",
    }


def monitor(
    forecasts: list[ForecastOrigin],
    actuals: list[ActualPoint],
    *,
    expected_slots: list[tuple[str, str, str]],
    source_identity: dict[str, str],
    evaluation_as_of: datetime,
    intervals: list[IntervalPoint] | None = None,
    interval_policy_hash: str | None = None,
    scope: str = "BASE_COHORT_AGGREGATE",
    reference: dict[str, Any] | None = None,
) -> dict[str, Any]:
    aware(evaluation_as_of)
    # Reject before matching/filtering: no current-season data can disappear silently.
    if any(a.season == "2026-2027" for a in actuals) or any(
        s[1] == "2026-2027" for s in expected_slots
    ):
        raise ValueError("FAIL_CURRENT_SEASON_ACTUAL_PRESENT")
    if len(set(expected_slots)) != len(expected_slots):
        raise ValueError("EXPECTED_SLOT_DUPLICATE")
    with localcontext() as ctx:
        ctx.prec = 50
        return _monitor(
            forecasts,
            actuals,
            expected_slots,
            source_identity,
            evaluation_as_of,
            intervals or [],
            interval_policy_hash,
            scope,
            reference,
        )


def _monitor(
    forecasts: list[ForecastOrigin],
    actuals: list[ActualPoint],
    expected_slots: list[tuple[str, str, str]],
    identity: dict[str, str],
    as_of: datetime,
    intervals: list[IntervalPoint],
    interval_hash: str | None,
    scope: str,
    reference: dict[str, Any] | None,
) -> dict[str, Any]:
    status = "PASS"
    hash_valid = (
        set(identity) == SOURCE_FIELDS
        and all(identity.values())
        and all(re.fullmatch("[0-9a-f]{64}", v) for k, v in identity.items() if k.endswith("hash"))
    )
    if not hash_valid or (
        interval_hash is not None and not re.fullmatch("[0-9a-f]{64}", interval_hash)
    ):
        status = "SOURCE_DRIFT"
    expected = set(expected_slots)
    grouped: dict[tuple[str, str, str], list[ForecastOrigin]] = {}
    for f in forecasts:
        key = slot(f)
        if f.season == "2026-2027":
            raise ValueError("FAIL_CURRENT_SEASON_ACTUAL_PRESENT")
        if f.source_identity != identity or key not in expected:
            status = "SOURCE_DRIFT"
        grouped.setdefault(key, []).append(f)
    duplicates = sum(max(0, sum(not f.is_rerun for f in fs) - 1) for fs in grouped.values())
    if duplicates and status == "PASS":
        status = "DUPLICATE_ISSUANCE"
    admitted: dict[tuple[str, str, str], ForecastOrigin] = {}
    daily: dict[tuple[str, str, str], dict[int, DailyForecast]] = {}
    duplicate_targets = 0
    for key, fs in sorted(grouped.items()):
        originals = [f for f in fs if not f.is_rerun]
        # A rerun never replaces an original or chooses a winner. Only exact replay is admitted.
        if len(originals) != 1 or any(
            sorted(f.daily, key=lambda d: d.lead_day)
            != sorted(originals[0].daily, key=lambda d: d.lead_day)
            for f in fs
        ):
            if status == "PASS":
                status = "DUPLICATE_ISSUANCE"
            continue
        f = originals[0]
        if key in expected and f.source_identity == identity:
            admitted[key] = f
        leads = [d.lead_day for d in f.daily]
        dates = [d.target_date for d in f.daily]
        duplicate_targets += max(len(leads) - len(set(leads)), len(dates) - len(set(dates)))
        valid = {
            d.lead_day: d
            for d in f.daily
            if type(d.lead_day) is int
            and 1 <= d.lead_day <= 15
            and numeric(d.predicted_kg)
            and d.target_date
            == f.forecast_origin.astimezone(SHANGHAI).date() + timedelta(days=d.lead_day)
        }
        daily[key] = valid
        if (len(valid) != 15 or len(f.daily) != 15) and status == "PASS":
            status = "SCHEMA_DRIFT"
    if duplicate_targets and status in ("PASS", "SCHEMA_DRIFT"):
        status = "ROWSET_INTEGRITY_FAILED"
    by_actual: dict[tuple[str, date], ActualPoint] = {}
    for a in actuals:
        key_a = a.base_id, a.target_date
        if key_a in by_actual:
            raise ValueError("ACTUAL_DUPLICATE_CONFLICT")
        if not numeric(a.quantity_kg):
            raise ValueError("SOURCE_NUMERIC_INVALID")
        by_actual[key_a] = a
    by_interval: dict[tuple[tuple[str, str, str], int, int], IntervalPoint] = {}
    for i in intervals:
        key_i = i.semantic_slot, i.lead_day, i.level
        if key_i in by_interval:
            status = "ROWSET_INTEGRITY_FAILED"
        bounds_ok = (i.lower_kg is None and i.upper_kg is None) or (
            i.lower_kg is not None
            and i.upper_kg is not None
            and numeric(i.lower_kg)
            and numeric(i.upper_kg)
            and i.lower_kg <= i.upper_kg
        )
        point = daily.get(i.semantic_slot, {}).get(i.lead_day)
        if (
            not bounds_ok
            or i.level not in (80, 90)
            or point is None
            or interval_hash is None
            or (
                i.upper_planning_bound_kg is not None
                and (
                    not numeric(i.upper_planning_bound_kg)
                    or i.upper_planning_bound_kg < point.predicted_kg
                )
            )
        ):
            status = "SCHEMA_DRIFT" if status == "PASS" else status
        by_interval[key_i] = i
    gates, complete, point_summaries, interval_summaries, lead_summaries = [], {}, {}, {}, {}
    for h in HORIZONS:
        cells: list[list[tuple[Decimal, Decimal]]] = []
        interval_rows: dict[int, list[tuple[Decimal, Decimal, IntervalPoint | None]]] = {
            80: [],
            90: [],
        }
        matured = present_a = present_f = ac = ap = ae = fc = 0
        for key in sorted(expected):
            origin_date = datetime.fromisoformat(key[2]).astimezone(SHANGHAI).date()
            mature = as_of.astimezone(SHANGHAI).date() > origin_date + timedelta(days=h)
            ds = daily.get(key, {})
            forecast_complete = all(d in ds for d in range(1, h + 1)) and key in admitted
            fc += forecast_complete
            present_f += sum(d in ds for d in range(1, h + 1)) if key in admitted else 0
            aa = [by_actual.get((key[0], origin_date + timedelta(days=d))) for d in range(1, h + 1)]
            aa = [a if a is not None and a.season == key[1] else None for a in aa]
            n = sum(a is not None for a in aa) if mature else 0
            state = (
                "NOT_MATURED"
                if not mature
                else "COMPLETE"
                if n == h
                else "PARTIAL"
                if n
                else "EMPTY"
            )
            matured += mature
            present_a += n
            ac += state == "COMPLETE"
            ap += state == "PARTIAL"
            ae += state == "EMPTY"
            scorable = mature and forecast_complete and state == "COMPLETE" and status == "PASS"
            gates.append(
                {
                    "semantic_slot": list(key),
                    "horizon": h,
                    "maturity_status": "MATURED" if mature else "NOT_MATURED",
                    "actual_completeness": state,
                    "forecast_completeness": "COMPLETE" if forecast_complete else "PARTIAL",
                    "scorable": scorable,
                }
            )
            if scorable:
                cell = [
                    (ds[d].predicted_kg, actual.quantity_kg)
                    for d, actual in enumerate(aa, 1)
                    if actual is not None
                ]
                cells.append(cell)
                gates[-1]["point_metrics"] = metrics([cell], "SCORABLE")
                for level in (80, 90):
                    interval_rows[level].extend(
                        (p, a, by_interval.get((key, d, level))) for d, (p, a) in enumerate(cell, 1)
                    )
        readiness = (
            "NOT_SCORABLE"
            if status != "PASS"
            else "INSUFFICIENT_DATA"
            if not matured
            else "SCORABLE"
            if cells
            else "NOT_SCORABLE"
        )
        point_summaries[f"H{h}"] = metrics(cells, readiness)
        complete[f"H{h}"] = {
            "expected_origin_count": len(expected),
            "issued_origin_count": len(admitted),
            "matured_origin_count": matured,
            "not_matured_origin_count": len(expected) - matured,
            "forecast_complete_origin_count": fc,
            "forecast_partial_origin_count": len(expected) - fc,
            "actual_complete_origin_count": ac,
            "actual_partial_origin_count": ap,
            "actual_empty_origin_count": ae,
            "scorable_origin_count": len(cells),
            "not_scorable_origin_count": len(expected) - len(cells),
            "origin_scoring_coverage": ratio(len(cells), matured),
            "expected_target_row_count": len(expected) * h,
            "present_forecast_target_row_count": present_f,
            "present_actual_target_row_count": present_a,
            "forecast_target_coverage": ratio(present_f, len(expected) * h),
            "actual_target_completeness": ratio(present_a, matured * h),
        }
        interval_summaries[f"H{h}"] = {
            f"{kind}{level}": interval_summary(interval_rows[level], kind)
            for kind in ("PI", "UPPER")
            for level in (80, 90)
        }
        lead_pairs = []
        if status == "PASS":
            for key in sorted(admitted):
                row = daily[key].get(h)
                lead_actual = by_actual.get((key[0], row.target_date)) if row else None
                if (
                    row
                    and lead_actual
                    and lead_actual.season == key[1]
                    and as_of.astimezone(SHANGHAI).date() > row.target_date
                ):
                    lead_pairs.append([(row.predicted_kg, lead_actual.quantity_kg)])
        lead_summaries[f"D{h}"] = metrics(lead_pairs, "SCORABLE" if lead_pairs else "NOT_SCORABLE")
    valid_targets = sum(len(daily.get(k, {})) for k in admitted)
    result: dict[str, Any] = {
        "forecastops_policy_version": POLICY_VERSION,
        "scoring_policy_version": SCORING_POLICY_VERSION,
        "actual_match_policy_version": ACTUAL_MATCH_POLICY_VERSION,
        "issuance_coverage_policy_version": ISSUANCE_COVERAGE_POLICY_VERSION,
        "quality_trend_policy_version": QUALITY_TREND_POLICY_VERSION,
        "scope": scope,
        "source_identity_hash": digest(identity),
        "expected_issuance_set_hash": digest(sorted(expected)),
        "forecast_rowset_hash": digest(
            [
                _payload(replace(f, daily=tuple(sorted(f.daily, key=lambda d: d.lead_day))))
                for f in sorted(forecasts, key=lambda x: (slot(x), x.is_rerun))
            ]
        ),
        "actual_rowset_hash": digest(
            [_payload(a) for a in sorted(actuals, key=lambda x: (x.base_id, x.target_date))]
        ),
        "interval_rowset_hash": digest(
            [
                _payload(i)
                for i in sorted(intervals, key=lambda x: (x.semantic_slot, x.lead_day, x.level))
            ]
        ),
        "interval_policy_hash": interval_hash,
        "evaluation_as_of": as_of.astimezone(SHANGHAI).isoformat(),
        "horizons": list(HORIZONS),
        "integrity_status": status,
        "schema_integrity_status": "PASS"
        if status in ("PASS", "SOURCE_DRIFT", "DUPLICATE_ISSUANCE")
        else status,
        "duplicate_issuance_count": duplicates,
        "duplicate_target_row_count": duplicate_targets,
        "duplicate_actual_conflict_count": 0,
        "source_hash_match": status != "SOURCE_DRIFT",
        "issuance": {
            "expected_issuance_origin_count": len(expected),
            "valid_issuance_origin_count": len(admitted),
            "issuance_coverage": ratio(len(admitted), len(expected)),
            "expected_forecast_target_row_count": len(expected) * 15,
            "valid_forecast_target_row_count": valid_targets,
            "forecast_target_coverage": ratio(valid_targets, len(expected) * 15),
        },
        "completeness": complete,
        "point_quality": point_summaries,
        "lead_quality": lead_summaries,
        "interval_quality": interval_summaries,
        "quality_trend": "NO_REFERENCE",
        "production_alert_status": "NOT_CONFIGURED_NO_PRODUCTION_THRESHOLDS",
        "production_alert_thresholds_established": False,
        "minimum_production_sample_count": None,
    }
    comparison_fields = (
        "scope",
        "scoring_policy_version",
        "source_identity_hash",
        "expected_issuance_set_hash",
        "horizons",
    )
    if (
        reference
        and all(result[k] == reference.get(k) for k in comparison_fields)
        and status == "PASS"
    ):
        names = ("daily_wape", "daily_mae_kg", "absolute_daily_bias_kg", "cumulative_wape")
        current = [point_summaries[f"H{h}"][k] for h in HORIZONS for k in names]
        previous = [
            reference.get("point_quality", {}).get(f"H{h}", {}).get(k)
            for h in HORIZONS
            for k in names
        ]
        if all(v is not None for v in current + previous):
            result["quality_trend"] = trend(
                [Decimal(v) for v in current], [Decimal(v) for v in previous]
            )
    result["horizon_gates_hash"] = digest(gates)
    result["result_hash"] = digest(result)
    result["private_gates"] = gates
    return result


def _payload(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return _payload(asdict(value))
    if isinstance(value, dict):
        return {k: _payload(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_payload(v) for v in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value
