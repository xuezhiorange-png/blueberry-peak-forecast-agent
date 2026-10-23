"""Two fixed S4 research estimators; no production registration or private IO.

The public synthetic interface stays isolated. The explicit Owner research
adapter reuses the same numerical cores after validating frozen real sources.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from typing import Any

from backend.research.v019_daily_curve import DailyKg, _kg, _micro
from backend.research.v019_synthetic_validation import digest

CONFIG = {
    "volume": "VOLUME_CALIBRATION_V1",
    "timing": "VOLUME_TIMING_V1",
    "base_shrinkage_bins": 4,
    "shape_uniform_pseudobins": 1,
    "global_factor": "SUM_ACTUAL_PER_MU_OVER_SUM_BASELINE_PER_MU",
    "base_factor": "COMPLETE_BIN_COUNT_SHRINKAGE_TO_GLOBAL",
    "shape": "MEAN_NORMALIZED_COMPLETE_BIN_SHAPE_SHRUNK_TO_UNIFORM",
    "quantization": "BIN_TOTAL_HALF_EVEN_MICRO_LARGEST_REMAINDER_EARLIEST",
    "parameter_search": False,
    "strict_pit": False,
    "production_eligible": False,
}


@dataclass(frozen=True)
class TrainingBin:
    base_id: str
    season_start: date
    start: date
    area_mu: Decimal
    baseline: tuple[Decimal, ...]
    actual: tuple[Decimal, ...]
    source_sha256: str


def allocate(total: int, weights: tuple[Decimal, ...]) -> tuple[int, ...]:
    """Exact integer rational apportionment, independent of Decimal context."""
    from math import lcm

    if total < 0 or not weights or any(not w.is_finite() or w < 0 for w in weights):
        raise ValueError("INVALID_ALLOCATION")
    ratios = [w.as_integer_ratio() for w in weights]
    common = lcm(*(d for _, d in ratios))
    scaled = [n * (common // d) for n, d in ratios]
    denominator = sum(scaled)
    if denominator == 0:
        if total:
            raise ValueError("POSITIVE_MASS_WITHOUT_SHAPE")
        return (0,) * len(weights)
    qr = [divmod(total * w, denominator) for w in scaled]
    remainder = total - sum(q for q, _ in qr)
    awarded = set(sorted(range(len(weights)), key=lambda i: (-qr[i][1], i))[:remainder])
    return tuple(q + int(i in awarded) for i, (q, _) in enumerate(qr))


def fit(
    bins: tuple[TrainingBin, ...], *, evaluation_start: date, data_class: str
) -> dict[str, Any]:
    if data_class != "SYNTHETIC":
        raise PermissionError("REAL_TRAINING_SOURCE_AND_PHYSICAL_BASIS_NOT_ADMITTED")
    if any(not b.base_id.startswith("SYNTHETIC-") for b in bins):
        raise ValueError("SYNTHETIC_IDENTITY_REQUIRED")
    return _fit_bins(bins, evaluation_start=evaluation_start, data_class=data_class)


def _fit_bins(
    bins: tuple[TrainingBin, ...], *, evaluation_start: date, data_class: str
) -> dict[str, Any]:
    """Shared arithmetic; real-source admission belongs to the research adapter."""
    if not bins:
        raise ValueError("EMPTY_TRAINING")
    seen = set()
    totals: dict[str, list[Decimal]] = {}
    shape = [Decimal(0)] * 7
    shape_count = 0
    with localcontext(Context(prec=50)):
        for b in sorted(bins, key=lambda b: (b.base_id, b.start)):
            key = b.base_id, b.start
            if (
                key in seen
                or b.start < b.season_start
                or (b.start - b.season_start).days % 7
                or b.start + timedelta(days=6) >= evaluation_start
                or b.season_start.year >= evaluation_start.year
                or not b.area_mu.is_finite()
                or b.area_mu <= 0
                or len(b.baseline) != 7
                or len(b.actual) != 7
                or re.fullmatch(r"[0-9a-f]{64}", b.source_sha256) is None
            ):
                raise ValueError("TRAINING_IDENTITY_CALENDAR_OR_TEMPORAL_BOUNDARY")
            seen.add(key)
            for v in (*b.baseline, *b.actual):
                _micro(v)
            p, a = sum(b.baseline), sum(b.actual)
            t = totals.setdefault(b.base_id, [Decimal(0), Decimal(0), Decimal(0)])
            t[0] += p / b.area_mu
            t[1] += a / b.area_mu
            t[2] += 1
            if a:
                shape_count += 1
                shape = [s + v / a for s, v in zip(shape, b.actual, strict=True)]
        denominator = sum(v[0] for v in totals.values())
        if not denominator:
            raise ValueError("ZERO_TRAINING_BASELINE_DENOMINATOR")
        global_factor = sum(v[1] for v in totals.values()) / denominator
        factors = {
            b: str((n * a / p + 4 * global_factor) / (n + 4) if p else global_factor)
            for b, (p, a, n) in sorted(totals.items())
        }
        weights = [str((v + Decimal(1) / 7) / (shape_count + 1)) for v in shape]
        body = {
            "config": CONFIG.copy(),
            "data_class": data_class,
            "evaluation_start": str(evaluation_start),
            "training_last_date": str(max(b.start + timedelta(days=6) for b in bins)),
            "training_seasons": sorted({str(b.season_start) for b in bins}),
            "training_sha256": digest(
                [
                    {
                        k: str(v)
                        if isinstance(v, (date, Decimal))
                        else [str(x) for x in v]
                        if isinstance(v, tuple)
                        else v
                        for k, v in asdict(b).items()
                    }
                    for b in sorted(bins, key=lambda b: (b.base_id, b.start))
                ]
            ),
            "global_factor": str(global_factor),
            "base_factors": factors,
            "shape_weights": weights,
            "training_bin_count": len(bins),
        }
    return {**body, "sha256": digest(body)}


def predict(
    fitted: dict[str, Any], base_id: str, season_start: date, baseline: tuple[DailyKg, ...]
) -> dict[str, tuple[DailyKg, ...]]:
    if fitted.get("data_class") != "SYNTHETIC" or not base_id.startswith("SYNTHETIC-"):
        raise PermissionError("REAL_MODEL_NOT_ADMITTED")
    return _predict_curve(fitted, base_id, season_start, baseline)


def _predict_curve(
    fitted: dict[str, Any], base_id: str, season_start: date, baseline: tuple[DailyKg, ...]
) -> dict[str, tuple[DailyKg, ...]]:
    """No IO or labels; callers validate the model's source and training identity."""
    body = {k: v for k, v in fitted.items() if k != "sha256"}
    if digest(body) != fitted.get("sha256") or fitted["config"] != CONFIG:
        raise ValueError("FIT_SEAL_MISMATCH")
    if (
        not baseline
        or baseline[0].day < season_start
        or baseline[0].day < date.fromisoformat(fitted["evaluation_start"])
        or date.fromisoformat(fitted["training_last_date"]) >= baseline[0].day
    ):
        raise ValueError("PREDICTION_TIME_BOUNDARY")
    bins: dict[int, list[int]] = {}
    for i, r in enumerate(baseline):
        if r.day != baseline[0].day + timedelta(days=i):
            raise ValueError("INCOMPLETE_CALENDAR")
        _micro(r.kg)
        bins.setdefault((r.day - season_start).days // 7, []).append(i)
    volume, timing = list(baseline), list(baseline)
    with localcontext(Context(prec=50)):
        factor = Decimal(fitted["base_factors"].get(base_id, fitted["global_factor"]))
        for indexes in bins.values():
            amount = sum(_micro(baseline[i].kg) for i in indexes)
            target = int((amount * factor).to_integral_value(rounding=ROUND_HALF_EVEN))
            flat = allocate(target, tuple(baseline[i].kg for i in indexes))
            shape = tuple(
                Decimal(fitted["shape_weights"][(baseline[i].day - season_start).days % 7])
                for i in indexes
            )
            shaped = allocate(target, shape)
            for j, i in enumerate(indexes):
                volume[i] = DailyKg(baseline[i].day, _kg(flat[j]))
                timing[i] = DailyKg(baseline[i].day, _kg(shaped[j]))
    return {"VOLUME_CALIBRATION_V1": tuple(volume), "VOLUME_TIMING_V1": tuple(timing)}


def window(rows: tuple[DailyKg, ...], start: date, days: int) -> tuple[DailyKg, ...]:
    if days not in (7, 15):
        raise ValueError("H7_H15_ONLY")
    result = tuple(r for r in rows if start <= r.day < start + timedelta(days=days))
    if len(result) != days or any(r.day != start + timedelta(days=i) for i, r in enumerate(result)):
        raise ValueError("INCOMPLETE_WINDOW")
    for r in result:
        _micro(r.kg)
    return result
