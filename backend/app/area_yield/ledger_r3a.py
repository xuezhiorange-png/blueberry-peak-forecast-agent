"""Source-active ledger qualification, independent of area and model accuracy."""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any


def qualify(
    rows: list[dict[str, str]],
    season: str,
    start: date,
    end: date,
    completeness: bool,
    matched: set[str],
    conflicts: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    calendar = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    by_farm: dict[str, dict[date, Decimal]] = defaultdict(dict)
    source: dict[date, Decimal] = defaultdict(Decimal)
    bad = set(conflicts or ())
    for row in rows:
        farm, day = row["canonical_farm_id"], date.fromisoformat(row["date"])
        if not start <= day <= end:
            continue
        by_farm[farm]
        if row["daily_harvest_kg"] == "":
            continue
        value = Decimal(row["daily_harvest_kg"])
        if not value.is_finite() or value < 0 or day in by_farm[farm]:
            bad.add(farm)
            continue
        by_farm[farm][day] = value
        source[day] += value
    global_unknown = set(calendar) - source.keys()
    source_calendar = [
        {
            "date": str(d),
            "source_active_day": d in source,
            "status": "SOURCE_ACTIVE_DAY" if d in source else "UNKNOWN_GLOBAL_NO_RECORD",
            "recorded_harvest_kg": str(source[d]) if d in source else "",
        }
        for d in calendar
    ]
    matrix = []
    for farm, daily in sorted(by_farm.items()):
        positive = sorted(d for d, value in daily.items() if value > 0)
        first, last = (positive[0], positive[-1]) if positive else (None, None)
        before, after = (first - start).days if first else None, (end - last).days if last else None
        contained = before is not None and after is not None and before >= 14 and after >= 14
        span_unknown = sum(first <= d <= last for d in global_unknown) if first and last else 0
        absence = len(source.keys() - daily.keys())
        reasons = []
        if farm not in matched:
            reasons.append("NO_EXACT_CROSS_SEASON_IDENTITY")
        if not positive:
            reasons.append("NONPOSITIVE_TOTAL")
        if not contained:
            reasons.append("BOUNDARY_BUFFER_LT_14")
        if farm in bad:
            reasons.append("UNRESOLVED_DATA_CONFLICT")
        if span_unknown:
            reasons.append("ACTIVE_SPAN_GLOBAL_UNKNOWN")
        potential = not reasons
        if not completeness:
            reasons.append("SOURCE_EXPORT_COMPLETENESS_NOT_ESTABLISHED")
        matrix.append(
            {
                "farm": farm,
                "season": season,
                "file_start": str(start),
                "file_end": str(end),
                "first_positive_date": str(first) if first else "",
                "last_positive_date": str(last) if last else "",
                "days_from_file_start": before,
                "days_to_file_end": after,
                "observed_positive_days": len(positive),
                "source_active_absence_days": absence,
                "source_active_zero_days": absence if completeness else 0,
                "global_unknown_days": len(global_unknown),
                "active_span_global_unknown_days": span_unknown,
                "season_total_kg": str(sum(daily.values(), Decimal(0))),
                "total_semantics": "RECORDED_EXPORT_TOTAL_NOT_BIOLOGICAL_TOTAL",
                "boundary_contained": contained,
                "source_completeness": "ESTABLISHED" if completeness else "NOT_ESTABLISHED",
                "strict_eligible": not reasons,
                "diagnostic_only": bool(reasons),
                "eligible_if_source_confirmed": potential,
                "zero_semantics": "RECORDED_LEDGER_ZERO_NOT_BIOLOGICAL_ZERO",
                "exclusion_reason": ";".join(reasons),
            }
        )
    return matrix, source_calendar
