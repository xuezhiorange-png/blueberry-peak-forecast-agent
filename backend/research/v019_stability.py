"""One fixed exploratory consensus shrinker; no IO, labels or production registration."""

from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from typing import Any

from backend.research import v019_accuracy_models as original
from backend.research.v019_daily_curve import DailyKg, _kg, _micro
from backend.research.v019_synthetic_validation import digest

METHOD = "TWO_SEASON_CONSENSUS_SHRINK_V1"
SEASONS = ("2023-2024", "2024-2025")
CONFIG = {
    "method": METHOD,
    "season_factor": "FULL_AUTHORIZED_SEASON_ACTUAL_PER_MU_OVER_SAME_PROFILE_BASELINE_PER_MU",
    "spread": "ABS_F1_MINUS_F2",
    "weight": "ONE_OVER_ONE_PLUS_SPREAD",
    "stable_factor": "ONE_PLUS_WEIGHT_TIMES_ORIGINAL_MINUS_ONE",
    "fallback": "BASELINE_FACTOR_ONE",
    "precision": 50,
    "allocation": "HALF_EVEN_MICRO_LARGEST_REMAINDER_EARLIEST",
    "parameter_search": False,
    "research_status": "EXPLORATORY",
    "strict_pit": False,
    "production_eligible": False,
}


def _hash(value: str) -> None:
    if re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("SOURCE_IDENTITY")


def _positive(value: Decimal, *, zero: bool = True) -> None:
    if not value.is_finite() or value < 0 or (not zero and value == 0):
        raise ValueError("INVALID_FINITE_NONNEGATIVE_VALUE")


def summarize_season(
    base_id: str,
    season: str,
    area_mu: Decimal,
    actual: tuple[DailyKg, ...],
    baseline: tuple[DailyKg, ...],
    *,
    source_sha256: str,
    members_sha256: str,
    profile_sha256: str,
) -> dict[str, Any]:
    """Full authorized daily calendar, not the S4 complete-bin fitting subset."""
    if season not in SEASONS or not base_id:
        raise ValueError("TRAINING_SEASON_OR_BASE_IDENTITY")
    _positive(area_mu, zero=False)
    for value in (source_sha256, members_sha256, profile_sha256):
        _hash(value)
    year = int(season[:4])
    start, end = date(year, 7, 1), date(year + 1, 4, 15)
    expected = tuple(start + timedelta(days=i) for i in range((end - start).days + 1))
    aa, pp = sorted(actual, key=lambda r: r.day), sorted(baseline, key=lambda r: r.day)
    if tuple(r.day for r in aa) != expected or tuple(r.day for r in pp) != expected:
        raise ValueError("COMPLETE_AUTHORIZED_SEASON_REQUIRED")
    for r in (*aa, *pp):
        _micro(r.kg)
    with localcontext(Context(prec=50)):
        a, p = sum((r.kg for r in aa), Decimal(0)), sum((r.kg for r in pp), Decimal(0))
        body = {
            "base_id": base_id,
            "season": season,
            "start": str(start),
            "end": str(end),
            "days": len(expected),
            "area_mu": str(area_mu),
            "actual_kg": str(a),
            "baseline_kg": str(p),
            "actual_kg_per_mu": str(a / area_mu),
            "baseline_kg_per_mu": str(p / area_mu),
            "factor": str((a / area_mu) / (p / area_mu)) if p else None,
            "source_sha256": source_sha256,
            "members_sha256": members_sha256,
            "profile_sha256": profile_sha256,
            "daily_sha256": digest(
                [
                    {"date": str(x.day), "actual": str(x.kg), "baseline": str(y.kg)}
                    for x, y in zip(aa, pp, strict=True)
                ]
            ),
        }
    return {**body, "sha256": digest(body)}


def fit_consensus(
    summaries: tuple[dict[str, Any], ...],
    original_fitted: dict[str, Any],
    *,
    evaluation_start: date,
    profile_sha256: str,
    base_ids: tuple[str, ...],
) -> dict[str, Any]:
    """Use only the sealed original fit's legal seasons; target labels are absent."""
    _hash(profile_sha256)
    if (
        digest({k: v for k, v in original_fitted.items() if k != "sha256"})
        != original_fitted.get("sha256")
        or original_fitted.get("config") != original.CONFIG
    ):
        raise ValueError("ORIGINAL_FIT_SEAL")
    if (
        original_fitted["evaluation_start"] != str(evaluation_start)
        or date.fromisoformat(original_fitted["training_last_date"]) >= evaluation_start
    ):
        raise ValueError("TEMPORAL_BOUNDARY")
    if not base_ids or len(set(base_ids)) != len(base_ids) or any(not b for b in base_ids):
        raise ValueError("EVALUATION_BASE_IDENTITY")
    for value in (original_fitted["global_factor"], *original_fitted["base_factors"].values()):
        _positive(Decimal(value))
    allowed = {str(date.fromisoformat(s).year) for s in original_fitted["training_seasons"]}
    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    for s in summaries:
        if digest({k: v for k, v in s.items() if k != "sha256"}) != s.get("sha256"):
            raise ValueError("SEASON_SUMMARY_SEAL")
        if s["season"] not in SEASONS or s["season"][:4] not in allowed:
            raise ValueError("TEMPORAL_TRAINING_SEASON")
        if date.fromisoformat(s["end"]) >= evaluation_start:
            raise ValueError("TEMPORAL_TARGET_LABEL_LEAKAGE")
        if s["profile_sha256"] != profile_sha256:
            raise ValueError("PROFILE_IDENTITY_MISMATCH")
        if s["season"] in grouped.setdefault(s["base_id"], {}):
            raise ValueError("DUPLICATE_BASE_SEASON")
        for key in ("actual_kg", "baseline_kg", "actual_kg_per_mu", "baseline_kg_per_mu"):
            _positive(Decimal(s[key]))
        _positive(Decimal(s["area_mu"]), zero=False)
        grouped[s["base_id"]][s["season"]] = s
    records = {}
    with localcontext(Context(prec=50)):
        for bid in sorted(set(base_ids) | set(grouped)):
            ss = grouped.get(bid, {})
            before = Decimal(
                original_fitted["base_factors"].get(bid, original_fitted["global_factor"])
            )
            _positive(before)
            reasons = "MISSING_TWO_COMPLETE_TRAINING_SEASONS" if set(ss) != set(SEASONS) else None
            if not reasons and any(Decimal(s["baseline_kg_per_mu"]) == 0 for s in ss.values()):
                reasons = "ZERO_BASELINE_DENOMINATOR"
            factors = {
                season: Decimal(s["actual_kg_per_mu"]) / Decimal(s["baseline_kg_per_mu"])
                if Decimal(s["baseline_kg_per_mu"])
                else None
                for season, s in sorted(ss.items())
            }
            f1, f2 = factors.get(SEASONS[0]), factors.get(SEASONS[1])
            spread = abs(f1 - f2) if not reasons and f1 is not None and f2 is not None else None
            weight = Decimal(1) / (1 + spread) if spread is not None else None
            value = 1 + weight * (before - 1) if weight is not None else Decimal(1)
            _positive(value)
            records[bid] = {
                "F1": str(factors[SEASONS[0]]) if factors.get(SEASONS[0]) is not None else None,
                "F2": str(factors[SEASONS[1]]) if factors.get(SEASONS[1]) is not None else None,
                "original_factor": str(before),
                "spread": str(spread) if spread is not None else None,
                "weight": str(weight) if weight is not None else None,
                "stable_factor": str(value),
                "mode": "BASELINE_FALLBACK" if reasons else "TWO_SEASON_CONSENSUS",
                "reason": reasons,
                "training_seasons": sorted(ss),
                "season_summary_sha256": {k: v["sha256"] for k, v in sorted(ss.items())},
            }
    body = {
        "method": METHOD,
        "config": CONFIG,
        "original_fitted_sha256": original_fitted["sha256"],
        "evaluation_start": str(evaluation_start),
        "profile_sha256": profile_sha256,
        "evaluation_bases": sorted(base_ids),
        "season_summaries": sorted(summaries, key=lambda s: (s["base_id"], s["season"])),
        "base_records": records,
        "two_season_bases": sorted(b for b, ss in grouped.items() if set(ss) == set(SEASONS)),
        "research_status": "EXPLORATORY",
    }
    return {**body, "sha256": digest(body)}


def predict(
    fitted: dict[str, Any], base_id: str, season_start: date, baseline: tuple[DailyKg, ...]
) -> tuple[DailyKg, ...]:
    if (
        digest({k: v for k, v in fitted.items() if k != "sha256"}) != fitted.get("sha256")
        or fitted.get("config") != CONFIG
    ):
        raise ValueError("CONSENSUS_FIT_SEAL")
    if base_id not in fitted["evaluation_bases"]:
        raise ValueError("BASE_NOT_IN_FROZEN_COHORT")
    if (
        str(season_start) != fitted["evaluation_start"]
        or not baseline
        or baseline[0].day != season_start
    ):
        raise ValueError("PREDICTION_TIME_BOUNDARY")
    result = list(baseline)
    with localcontext(Context(prec=50)):
        factor = Decimal(fitted["base_records"][base_id]["stable_factor"])
        _positive(factor)
        for i, row in enumerate(baseline):
            if row.day != season_start + timedelta(days=i):
                raise ValueError("INCOMPLETE_CALENDAR")
            _micro(row.kg)
        for i in range(0, len(baseline), 7):
            rows = baseline[i : i + 7]
            target = int(
                (sum(_micro(r.kg) for r in rows) * factor).to_integral_value(
                    rounding=ROUND_HALF_EVEN
                )
            )
            amounts = original.allocate(target, tuple(r.kg for r in rows))
            for j, amount in enumerate(amounts):
                result[i + j] = DailyKg(rows[j].day, _kg(amount))
    return tuple(result)
