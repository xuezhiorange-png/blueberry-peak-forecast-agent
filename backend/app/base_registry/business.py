"""Deterministic base ledger and April-15 preparation. Never trains or predicts."""

import re
from collections import defaultdict
from datetime import date
from decimal import Decimal, localcontext
from typing import Any

from backend.app.area_yield.data import calendar, fixed


def business_cutoff(season: str) -> date:
    if not re.fullmatch(r"\d{4}-\d{4}", season):
        raise ValueError("invalid season")
    start, end = map(int, season.split("-"))
    if end != start + 1:
        raise ValueError("nonconsecutive season")
    return date(end, 4, 15)


def map_farms(
    registry: dict[str, Any], identities: set[str], aliases: dict[str, tuple[str, str]]
) -> list[dict[str, Any]]:
    members: dict[str, set[str]] = defaultdict(set)
    names = {}
    for b in registry["bases"]:
        names[b["base_id"]] = b["canonical_base_name"]
        for f in b["covered_farms"]:
            members[f].add(b["base_id"])
    result = []
    for farm in sorted(identities):
        key, method, evidence = farm, "EXACT", registry["source_hash"]
        if farm not in members and farm in aliases:
            key, evidence = aliases[farm]
            if not evidence:
                raise ValueError("alias evidence required")
            method = "AUTHORIZED_ALIAS"
        targets = members.get(key, set())
        status = method if len(targets) == 1 else "AMBIGUOUS" if targets else "UNRESOLVED"
        selected = next(iter(targets)) if len(targets) == 1 else None
        result.append(
            {
                "historical_farm_identity": farm,
                "normalized_identity": key,
                "matched_base_id": selected,
                "canonical_base_name": names.get(selected),
                "match_method": method,
                "match_status": status,
                "evidence": evidence,
            }
        )
    return result


def audit_season(
    registry: dict[str, Any], source: dict[str, Any], aliases: dict[str, tuple[str, str]]
) -> dict[str, Any]:
    with localcontext() as ctx:
        ctx.prec = 50
        return _audit(registry, source, aliases)


def _audit(
    registry: dict[str, Any], source: dict[str, Any], aliases: dict[str, tuple[str, str]]
) -> dict[str, Any]:
    cutoff = business_cutoff(source["season"])
    start, end = (date.fromisoformat(source[k]) for k in ("coverage_start", "coverage_end"))
    season_start, season_end = date(cutoff.year - 1, 7, 1), date(cutoff.year, 6, 30)
    if not season_start <= start <= end <= season_end:
        raise ValueError("source outside season")
    known: dict[tuple[str, date], Decimal] = {}
    active: set[date] = set()
    for r in source["rows"]:
        farm, day = r["canonical_farm_id"], date.fromisoformat(r["date"])
        value = Decimal(r["daily_harvest_kg"])
        if (farm, day) in known:
            raise ValueError("duplicate farm-day")
        if not farm or not start <= day <= end or not value.is_finite() or value < 0:
            raise ValueError("invalid observed farm-day")
        known[farm, day] = value
        active.add(day)
    identities = {f for f, _ in known}
    mapping = map_farms(registry, identities, aliases)
    mapped = {r["historical_farm_identity"]: r for r in mapping}
    totals: dict[tuple[str, date], Decimal] = defaultdict(Decimal)
    excluded = Decimal(0)
    for (farm, day), value in known.items():
        target = mapped[farm]["matched_base_id"]
        if target:
            totals[target, day] += value
        else:
            excluded += value
    audits, all_daily = [], []
    # Do not fill unobserved source margins, including post-cutoff days.
    days = calendar(start, max(end, cutoff))
    for b in registry["bases"]:
        bid = b["base_id"]
        resolved = {r["normalized_identity"] for r in mapping if r["matched_base_id"] == bid}
        unresolved = set(b["covered_farms"]) - resolved
        positive = sorted(d for (base, d), v in totals.items() if base == bid and v > 0)
        business_positive = [d for d in positive if d <= cutoff]
        unknown = set(calendar(start, min(end, cutoff))) - active
        reasons = []
        if not source["complete_export"] or not source["ledger_zero_semantics_authorized"]:
            reasons.append("SOURCE_NOT_QUALIFIED")
        if unresolved:
            reasons.append("UNRESOLVED_MEMBER_FARMS")
        if not b["productive_area_mu"]:
            reasons.append("AREA_INVALID")
        farm_set = {r["historical_farm_identity"] for r in mapping if r["matched_base_id"] == bid}
        if farm_set & set(source.get("conflicted_farms", [])):
            reasons.append("SOURCE_GRAIN_CONFLICT")
        if end < cutoff:
            reasons.append("SOURCE_END_BEFORE_CUTOFF")
        # Conservative full-window gate. No activity-based interpolation or
        # zero extrapolation before file coverage. July-1 is existing calendar.
        if start > season_start:
            reasons.append("SOURCE_START_AFTER_SEASON_START")
        if unknown:
            reasons.append("GLOBAL_UNKNOWN_IN_BUSINESS_WINDOW")
        if not business_positive:
            reasons.append("NO_POSITIVE_BUSINESS_LABELS")
        for d in days:
            partial = totals.get((bid, d), Decimal(0))
            known_day = (
                d in active
                and source["complete_export"]
                and source["ledger_zero_semantics_authorized"]
                and not unresolved
            )
            if d > cutoff:
                # Tail audit contains actual recorded subtotals only.
                if (bid, d) not in totals:
                    continue
                known_day = not unresolved
            all_daily.append(
                {
                    "base_id": bid,
                    "canonical_base_name": b["canonical_base_name"],
                    "season": source["season"],
                    "source_hash": source["source_hash"],
                    "date": str(d),
                    "scope": "BUSINESS_SCOPE"
                    if d <= cutoff
                    else "OUT_OF_BUSINESS_SCOPE_TAIL_FRUIT",
                    "mapped_observed_subtotal_kg": fixed(partial),
                    "recorded_harvest_kg": fixed(partial) if known_day else None,
                    "observation_status": "OBSERVED_OR_AUTHORIZED_LEDGER_ZERO"
                    if known_day
                    else "UNKNOWN_MEMBER_COVERAGE"
                    if d in active
                    else "UNKNOWN_GLOBAL_NO_RECORD",
                }
            )
        pre = [(d, totals[bid, d]) for d in positive if d <= cutoff]
        post = [(d, totals[bid, d]) for d in positive if d > cutoff]
        pre_total = sum((v for _, v in pre), Decimal(0))
        post_total = sum((v for _, v in post), Decimal(0))
        pre_peak = max(pre, key=lambda x: x[1]) if pre else None
        post_peak = max(post, key=lambda x: x[1]) if post else None
        audits.append(
            {
                "base_id": bid,
                "canonical_base_name": b["canonical_base_name"],
                "season": source["season"],
                "raw_first_harvest_date": str(positive[0]) if positive else None,
                "raw_last_harvest_date": str(positive[-1]) if positive else None,
                "business_cutoff_date": str(cutoff),
                "pre_cutoff_total_kg": fixed(pre_total),
                "post_cutoff_total_kg": fixed(post_total),
                "post_cutoff_ratio": fixed(post_total / (pre_total + post_total))
                if pre_total + post_total
                else None,
                "ratio_status": "COMPUTABLE" if pre_total + post_total else "NOT_COMPUTABLE",
                "pre_cutoff_peak_date": str(pre_peak[0]) if pre_peak else None,
                "pre_cutoff_peak_kg": fixed(pre_peak[1]) if pre_peak else None,
                "post_cutoff_peak_date": str(post_peak[0]) if post_peak else None,
                "post_cutoff_peak_kg": fixed(post_peak[1]) if post_peak else None,
                "post_cutoff_peak_exceeds_business_peak": bool(
                    post_peak and (not pre_peak or post_peak[1] > pre_peak[1])
                ),
                "business_day_count": sum(d <= cutoff for d in days),
                "post_cutoff_day_count": sum(d > cutoff for d in days),
                "member_farm_count": len(b["covered_farms"]),
                "resolved_member_farm_count": len(resolved),
                "unresolved_member_farm_count": len(unresolved),
                "unresolved_members": sorted(unresolved),
                "coverage_status": "COMPLETE"
                if not reasons
                else "PARTIAL"
                if positive
                else "BLOCKED",
                "total_semantics": "MAPPED_RECORDED_SUBTOTAL"
                if reasons
                else "COMPLETE_BUSINESS_TOTAL",
                "exclusion_reasons": reasons,
                "productive_area_mu": b["productive_area_mu"],
                "yield_kg_per_mu": fixed(pre_total / Decimal(b["productive_area_mu"]))
                if not reasons
                else None,
                "yield_eligible": not reasons,
            }
        )
    return {
        "audit": audits,
        "daily": all_daily,
        "mapping": mapping,
        "excluded_total_kg": fixed(excluded),
        "source_recorded_total_kg": fixed(sum(known.values(), Decimal(0))),
    }
