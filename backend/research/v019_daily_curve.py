"""One SYNTHETIC-stage research candidate; no IO or production registration.

Decimal quantities are represented exactly in integer micro-kg. Linear weights
use integer numerators/denominators, so neither interpolation nor largest-
remainder ordering depends on rounded Decimal division or ambient precision.
"""

from __future__ import annotations

import hashlib
import json
import re
from bisect import bisect_right
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from math import lcm

BASELINE_POLICY = "AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1"
MICRO_PER_KG = 1_000_000


def method_config() -> dict[str, str | int | bool]:
    """Fresh copy of the sole frozen configuration, not tunable parameters."""
    return {
        "anchor": "MEAN_BASELINE_DAILY_MICRO_KG_AT_MIDPOINT_OF_ACTUAL_BIN_SUPPORT",
        "baseline_policy": BASELINE_POLICY,
        "bin_days": 7,
        "boundary": "CLAMP_ENDPOINT_ANCHOR_INSIDE_DECLARED_SUPPORT_NO_EXTRAPOLATION",
        "candidate_count": 1,
        "candidate_id": "BIN_CENTER_LINEAR_PER_BIN_MASS_V1",
        "input_precision": "EXACT_NONNEGATIVE_INTEGER_MICRO_KG_NO_INPUT_ROUNDING",
        "interpolation": "BIN_CENTER_LINEAR_INTERPOLATION",
        "method_selection": "OWNER_SPECIFIED_STRUCTURE_ONLY_BEFORE_LABEL_ACCESS",
        "normalization": "PER_BIN_MASS_CONSERVING_NORMALIZATION",
        "numeric_arithmetic": "DECIMAL_INPUT_OUTPUT_EXACT_INTEGER_RATIONAL_INTERMEDIATES_NO_FLOAT",
        "output_kg_places": 6,
        "parameter_search": False,
        "partial_bins": "ACTUAL_DECLARED_SUPPORT_DAYS_ONLY_PRESERVE_SEASON_ANCHOR",
        "quantization": "LARGEST_EXACT_REMAINDER_THEN_EARLIEST_DATE",
        "query": "SLICE_PRECOMPUTED_SUPPORT_NO_RENORMALIZATION",
        "timezone": "Asia/Shanghai",
        "zero_mass_bin": "ALL_ZERO",
    }


@dataclass(frozen=True)
class DailyKg:
    day: date
    kg: Decimal


@dataclass(frozen=True)
class CurveInput:
    season_start: date
    support_start: date
    support_end: date
    baseline: tuple[DailyKg, ...]
    baseline_source_sha256: str
    baseline_policy: str
    timezone: str


@dataclass(frozen=True)
class BinMass:
    bin_id: int
    baseline_micro_kg: int
    candidate_micro_kg: int


@dataclass(frozen=True)
class CandidateResult:
    rows: tuple[DailyKg, ...]
    bins: tuple[BinMass, ...]
    input_sha256: str
    config_sha256: str
    canonical_bytes: bytes
    result_sha256: str


def canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")


def _micro(value: Decimal) -> int:
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise ValueError("INVALID_NONNEGATIVE_DECIMAL")
    numerator, denominator = value.as_integer_ratio()
    whole, remainder = divmod(numerator * MICRO_PER_KG, denominator)
    if remainder:
        raise ValueError("INPUT_NOT_EXACT_MICRO_KG")
    return whole


def _kg(value: int) -> Decimal:
    whole, fraction = divmod(value, MICRO_PER_KG)
    return Decimal(f"{whole}.{fraction:06d}")


def _validate(request: CurveInput) -> list[int]:
    if any(
        type(day) is not date
        for day in (request.season_start, request.support_start, request.support_end)
    ):
        raise ValueError("LOCAL_BUSINESS_DATE_REQUIRED")
    if (
        request.baseline_policy != BASELINE_POLICY
        or request.timezone != "Asia/Shanghai"
        or re.fullmatch(r"[0-9a-f]{64}", request.baseline_source_sha256) is None
    ):
        raise ValueError("INVALID_BASELINE_IDENTITY")
    days = (request.support_end - request.support_start).days + 1
    if request.support_start < request.season_start or days <= 0 or len(request.baseline) != days:
        raise ValueError("INCOMPLETE_DECLARED_SUPPORT")
    values: list[int] = []
    for index, row in enumerate(request.baseline):
        if type(row.day) is not date or row.day != request.support_start + timedelta(days=index):
            raise ValueError("INVALID_CONTINUOUS_CALENDAR")
        values.append(_micro(row.kg))
    return values


def _weight(position: int, centers: list[int], rates: list[int]) -> tuple[int, int]:
    """Exact linear micro-kg shape at doubled calendar coordinate."""
    if position <= centers[0]:
        return rates[0], 1
    if position >= centers[-1]:
        return rates[-1], 1
    right = bisect_right(centers, position)
    left = right - 1
    gap = centers[right] - centers[left]
    numerator = rates[left] * (centers[right] - position) + rates[right] * (
        position - centers[left]
    )
    return numerator, gap


def generate_candidate(request: CurveInput) -> CandidateResult:
    values = _validate(request)
    groups: dict[int, list[int]] = {}
    offset = (request.support_start - request.season_start).days
    for index in range(len(values)):
        groups.setdefault((offset + index) // 7, []).append(index)
    centers: list[int] = []
    rates: list[int] = []
    for indexes in groups.values():
        if len({values[i] for i in indexes}) != 1:
            raise ValueError("BASELINE_NOT_FLAT_WITHIN_SEASON_BIN")
        # A partial bin's center is the midpoint of its actual support, not an
        # invented seventh day. The original season-based bin ID never changes.
        centers.append(2 * offset + indexes[0] + indexes[-1])
        rates.append(values[indexes[0]])
    output = [0] * len(values)
    masses: list[BinMass] = []
    for bin_id, indexes in groups.items():
        target = sum(values[i] for i in indexes)
        if target:
            weights = [_weight(2 * (offset + i), centers, rates) for i in indexes]
            denominator = lcm(*(d for _, d in weights))
            scaled = [n * (denominator // d) for n, d in weights]
            total = sum(scaled)
            if total <= 0:
                raise ValueError("POSITIVE_BIN_HAS_NO_SHAPE")
            divided = [divmod(target * weight, total) for weight in scaled]
            remaining = target - sum(q for q, _ in divided)
            if not 0 <= remaining < len(indexes):
                raise ValueError("INVALID_QUANTIZATION_REMAINDER")
            priority = sorted(range(len(indexes)), key=lambda i: (-divided[i][1], indexes[i]))
            awarded = set(priority[:remaining])
            for local, index in enumerate(indexes):
                output[index] = divided[local][0] + int(local in awarded)
        actual = sum(output[i] for i in indexes)
        if actual != target:
            raise ValueError("BIN_MASS_MISMATCH")
        masses.append(BinMass(bin_id, target, actual))
    rows = tuple(
        DailyKg(row.day, _kg(amount)) for row, amount in zip(request.baseline, output, strict=True)
    )
    input_payload = {
        "baseline_policy": request.baseline_policy,
        "baseline_source_sha256": request.baseline_source_sha256,
        "rows": [
            {"date": row.day.isoformat(), "kg": format(_kg(v), "f")}
            for row, v in zip(request.baseline, values, strict=True)
        ],
        "season_start": request.season_start.isoformat(),
        "support_end": request.support_end.isoformat(),
        "support_start": request.support_start.isoformat(),
        "timezone": request.timezone,
    }
    config = method_config()
    input_hash = hashlib.sha256(canonical_bytes(input_payload)).hexdigest()
    config_hash = hashlib.sha256(canonical_bytes(config)).hexdigest()
    payload = {
        "bin_mass": [
            {
                "bin_id": b.bin_id,
                "baseline_micro_kg": b.baseline_micro_kg,
                "candidate_micro_kg": b.candidate_micro_kg,
            }
            for b in masses
        ],
        "candidate_id": config["candidate_id"],
        "config": config,
        "config_sha256": config_hash,
        "input": input_payload,
        "input_sha256": input_hash,
        "rows": [{"date": row.day.isoformat(), "kg": format(row.kg, "f")} for row in rows],
    }
    raw = canonical_bytes(payload)
    return CandidateResult(
        rows, tuple(masses), input_hash, config_hash, raw, hashlib.sha256(raw).hexdigest()
    )


def select_window(result: CandidateResult, *, origin: date, horizon: int) -> tuple[DailyKg, ...]:
    """D1..D7/D15 only slices an already computed support; never reconstructs it."""
    if type(origin) is not date:
        raise ValueError("LOCAL_BUSINESS_DATE_REQUIRED")
    if type(horizon) is not int or horizon not in (7, 15):
        raise ValueError("INVALID_HORIZON")
    first = origin + timedelta(days=1)
    offset = (first - result.rows[0].day).days
    if offset < 0 or offset + horizon > len(result.rows):
        raise ValueError("QUERY_OUTSIDE_SUPPORT")
    return result.rows[offset : offset + horizon]
