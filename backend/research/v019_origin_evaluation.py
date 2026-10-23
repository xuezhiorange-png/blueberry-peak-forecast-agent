"""Origin-indexed adapter to unchanged S1 arithmetic. Full C0 never shrinks."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Context, Decimal, localcontext
from typing import Any

from backend.research import v019_accuracy_models as windows
from backend.research import v019_research_evaluation as scoring
from backend.research import v019_synthetic_validation as metrics
from backend.research.v019_daily_curve import DailyKg


def origin_key(member: dict[str, Any], season: str) -> str:
    return metrics.digest(
        {
            "base": member["base_id"],
            "season": season,
            "origin": str(date.fromisoformat(member["target_start"]) - timedelta(days=1)),
        }
    )


def curve(rows: list[dict[str, str]]) -> tuple[DailyKg, ...]:
    return tuple(DailyKg(date.fromisoformat(r["date"]), Decimal(r["kg"])) for r in rows)


def peaks(rows: tuple[DailyKg, ...]) -> dict[str, Any]:
    d, q = metrics._peak(rows, False)
    s, r = metrics._peak(rows, True)
    return {
        "single_day": {"date": str(d), "kg": str(q)},
        "rolling7": {"start": str(s), "end": str(s + timedelta(days=6)), "kg": str(r)},
    }


def errors(rows: tuple[DailyKg, ...], actual: tuple[DailyKg, ...], sid: str) -> dict[str, Decimal]:
    clock = datetime(2026, 10, 23, tzinfo=UTC)
    return metrics._errors(
        metrics.Forecast("S6", sid, "S6", "S6", rows),
        metrics.Labels(sid, "S6", "S6", actual, clock, clock, True),
    )


def evaluate(
    experiment: dict[str, Any],
    members: list[dict[str, Any]],
    actual: dict[str, tuple[DailyKg, ...]],
    static: dict[str, tuple[DailyKg, ...]],
    season: str,
) -> dict[str, Any]:
    with localcontext(Context(prec=50)):
        return _evaluate(experiment, members, actual, static, season)


def _evaluate(
    experiment: dict[str, Any],
    members: list[dict[str, Any]],
    actual: dict[str, tuple[DailyKg, ...]],
    static: dict[str, tuple[DailyKg, ...]],
    season: str,
) -> dict[str, Any]:
    if len({m["candidate_id"] for m in members}) != len(members):
        raise ValueError("C0_DUPLICATE")
    ws = ("H7_PREFIX", "H15_LOCAL")

    def group() -> dict[str, Any]:
        return {
            w: {k: scoring._accumulator() for k in ("paired", "static_on_common", "static_full_C0")}
            for w in ws
        }

    groups = group()
    perbase = {b: group() for b in sorted({m["base_id"] for m in members})}
    seen = {k: group() for k in ("SEEN", "UNSEEN")}
    denominator = {
        w: {
            "actual_kg": Decimal(0),
            "label_complete_members": 0,
            "candidate_members": sum(m["window"] == w for m in members),
        }
        for w in ws
    }
    ledger = []
    for m in members:
        bid, sid, w = m["base_id"], m["candidate_id"], m["window"]
        n = 7 if w == "H7_PREFIX" else 15
        start = date.fromisoformat(m["target_start"])
        record = experiment["origins"].get(origin_key(m, season))
        reason = None
        static_reason = None
        total = Decimal(0)
        err = {}
        static_err = {}
        detail = {}
        try:
            aa = windows.window(actual.get(bid, ()), start, n)
            total = sum((r.kg for r in aa), Decimal(0))
            denominator[w]["actual_kg"] += total
            denominator[w]["label_complete_members"] += 1
            ss = windows.window(static.get(bid, ()), start, n)
            static_err = errors(ss, aa, sid)
            detail = {"actual": peaks(aa), "static": peaks(ss)}
        except ValueError:
            static_reason = "INCOMPLETE_CALENDAR"
        try:
            if static_reason:
                raise ValueError(static_reason)
            if not record or record["status"] != "COMPUTED":
                raise ValueError("UNVERIFIED_AUTHORITY")
            pp = {k: windows.window(curve(v), start, n) for k, v in record["predictions"].items()}
            if set(pp) != {"M0", "M1"}:
                raise ValueError("IDENTITY_OR_SOURCE_HASH_MISMATCH")
            err = {k: errors(v, aa, sid) for k, v in pp.items()}
            detail.update({k: peaks(v) for k, v in pp.items()})
        except ValueError as exc:
            reason = str(exc)
        for dest in (
            groups,
            perbase[bid],
            seen["SEEN" if bid in experiment["training_bases"] else "UNSEEN"],
        ):
            scoring._add(
                dest[w]["paired"],
                m,
                reason,
                total,
                {"baseline": err.get("M0", {}), "candidate": err.get("M1", {})},
                total > 0,
            )
            scoring._add(
                dest[w]["static_on_common"],
                m,
                reason,
                total,
                {"baseline": static_err, "candidate": static_err},
                total > 0,
            )
            scoring._add(
                dest[w]["static_full_C0"],
                m,
                static_reason,
                total,
                {"baseline": static_err, "candidate": static_err},
                total > 0,
            )
        ledger.append(
            {
                "candidate_id": sid,
                "base_id": bid,
                "window": w,
                "origin_key": origin_key(m, season),
                "status": "NOT_COMPUTABLE" if reason else "COMPUTED",
                "reason": reason,
                "feature_reasons": record.get("reasons", []) if record else ["MISSING_ORIGIN"],
                "actual_kg": str(total),
                "errors": {k: {n: str(x) for n, x in v.items()} for k, v in err.items()},
                "peaks": detail,
            }
        )

    def finish(g: dict[str, Any]) -> dict[str, Any]:
        return {w: {k: scoring._finish(v) for k, v in mm.items()} for w, mm in g.items()}

    final = finish(groups)
    for gg in final.values():
        paired = gg["paired"]["metrics"]["DAILY_WAPE"]
        common = gg["static_on_common"]["metrics"]["DAILY_WAPE"]
        if (
            paired["common_member_ids"] != common["common_member_ids"]
            or paired["baseline"]["denominator"] != common["baseline"]["denominator"]
        ):
            raise ValueError("COMMON_COHORT_DENOMINATOR_CHANGED")
    direction = []
    peak = []
    for g in final.values():
        delta = g["paired"]["candidate_minus_baseline"]
        direction.append(delta["DAILY_WAPE"])
        peak.extend([delta["SINGLE_DAY_PEAK_DATE_MAE"], delta["ROLLING_7DAY_PEAK_START_MAE"]])
    classification = (
        "NOT_COMPARABLE"
        if any(v is None for v in direction)
        else "MIXED"
        if any(Decimal(v) < 0 for v in direction)
        and any(v is not None and Decimal(v) > 0 for v in peak)
        else "CONDITIONAL_INCREMENTAL_VALUE_ON_COMMON_COHORT"
        if all(Decimal(v) < 0 for v in direction)
        and all(v is not None and Decimal(v) <= 0 for v in peak)
        else "NO_INCREMENTAL_GAIN"
        if all(Decimal(v) >= 0 for v in direction)
        else "MIXED"
    )
    return {
        "groups": final,
        "per_base": {b: finish(g) for b, g in perbase.items()},
        "seen_unseen": {s: finish(g) for s, g in seen.items()},
        "full_C0_actual_denominators": {
            w: {k: str(v) if isinstance(v, Decimal) else v for k, v in d.items()}
            for w, d in denominator.items()
        },
        "member_ledger": ledger,
        "candidate_count": len(members),
        "common_computed_count": sum(r["status"] == "COMPUTED" for r in ledger),
        "not_computable_count": sum(r["status"] != "COMPUTED" for r in ledger),
        "classification": classification,
        "comparison_status": "CONDITIONAL_ON_COMMON_COMPUTABLE_COHORT",
        "static_different_model_family_no_fair_family_ranking": True,
        "overlapping_origins_not_independent": True,
        "strict_pit": False,
        "H7_rolling_start_zero_is_structural": True,
    }
