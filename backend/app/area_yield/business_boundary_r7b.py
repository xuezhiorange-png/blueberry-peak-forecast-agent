"""Explicit 2526 business boundary, applied to frozen R7 predictions only.

This is a user-authorized reporting/prediction-window policy, not a learned rule.
R6 active-span UNKNOWN checks remain; the boundary-buffer heuristic is superseded
only for this explicitly complete business season. No historical label is imputed.
"""

import math
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from backend.app.area_yield.evidence_expansion_r6 import FarmSeasonQualification
from backend.app.area_yield.shape_r3 import normalize, season_calendar

START = date(2025, 7, 22)
END = date(2026, 4, 15)
POLICY = "USER_CONFIRMED_2526_BUSINESS_WINDOW_R7B"


def window_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    if [r["date"] for r in rows] != [str(d) for d in season_calendar("2025-2026")]:
        raise ValueError("frozen full-calendar label identity required")
    if len({r["farm"] for r in rows}) != 1:
        raise ValueError("mixed farm identity")
    kept = [dict(r) for r in rows if str(START) <= r["date"] <= str(END)]
    for r in kept:
        if r["quantity"] != "":
            value = Decimal(r["quantity"])
            if not value.is_finite() or value < 0:
                raise ValueError("invalid in-window label")
    return kept


def qualify_window(
    original: dict[str, Any], rows: list[dict[str, str]], training_eligible: bool
) -> FarmSeasonQualification:
    q = FarmSeasonQualification(**original)
    if q.season != "2025-2026":
        raise ValueError("R7B is not authority to change past seasons")
    kept = window_rows(rows)
    if any(r["farm"] != q.canonical_farm for r in kept):
        raise ValueError("farm mismatch")
    positives = [r["date"] for r in kept if r["quantity"] != "" and Decimal(r["quantity"]) > 0]
    unknown = tuple(
        r["date"]
        for r in kept
        if r["quantity"] == "" and positives and positives[0] <= r["date"] <= positives[-1]
    )
    reasons = []
    if not q.source_complete or not q.ledger_zero_semantics_authorized:
        reasons.append("SOURCE_INCOMPLETE")
    if not q.coverage_start <= str(START) <= str(END) <= q.coverage_end:
        reasons.append("BUSINESS_WINDOW_SOURCE_COVERAGE_INCOMPLETE")
    if "UNRESOLVED_DATA_CONFLICT" in q.exclusion_reasons:
        reasons.append("UNRESOLVED_DATA_CONFLICT")
    if not training_eligible:
        reasons.append("PRIOR_SEASON_NOT_STRICT_ELIGIBLE")
    if not positives:
        reasons.append("NONPOSITIVE_BUSINESS_TOTAL")
    if unknown:
        reasons.append("GLOBAL_UNKNOWN_BLOCKED")
    strict = not reasons
    if not q.area_bound:
        reasons.append("AREA_MISSING")
    return replace(
        q,
        coverage_start=str(START),
        coverage_end=str(END),
        active_span_global_unknown_days=unknown,
        season_completeness_status="STRICT_ELIGIBLE"
        if strict
        else ("GLOBAL_UNKNOWN_BLOCKED" if unknown else "NOT_ELIGIBLE_OTHER"),
        shape_evaluable=strict,
        total_evaluable=strict and q.area_bound,
        exclusion_reasons=tuple(reasons),
        peak_evaluation_status="NOT_COMPUTABLE_OTHER",
        seven_day_evaluation_status="NOT_COMPUTABLE_OTHER",
    )


def apply_window(raw: list[float]) -> dict[str, Any]:
    days = season_calendar("2025-2026")
    if len(raw) != len(days) or any(not math.isfinite(v) or v < 0 for v in raw):
        raise ValueError("invalid raw frozen shares")
    if abs(sum(raw) - 1) > 1e-12:
        raise ValueError("raw full-calendar shares not normalized")
    kept = [v for d, v in zip(days, raw, strict=True) if START <= d <= END]
    return {
        "policy": POLICY,
        "dates": [str(START + timedelta(days=i)) for i in range(len(kept))],
        "shares": normalize(kept),
        "raw_window_mass": sum(kept),
        "pre_window_mass": sum(v for d, v in zip(days, raw, strict=True) if d < START),
        "post_window_mass": sum(v for d, v in zip(days, raw, strict=True) if d > END),
        "post_window_class": "TAIL_FRUIT_OUT_OF_SCOPE",
        "raw_prediction_changed": False,
        "validation_quantity_used": False,
    }
