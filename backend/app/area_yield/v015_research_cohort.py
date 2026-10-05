"""Offline retrospective admission and time boundaries, not a training pipeline."""

import hashlib
import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

SEASONS = ("2023-2024", "2024-2025", "2025-2026")
SHANGHAI = ZoneInfo("Asia/Shanghai")
COMPLETE_STATES = frozenset({"VALID_OBSERVED", "REAL_ZERO"})


def canonical(value: Any) -> bytes:
    return (
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        )
        + "\n"
    ).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def admit_base(row: dict[str, Any]) -> tuple[bool, list[str]]:
    if row["season"] not in SEASONS:
        raise ValueError("UNAUTHORIZED_SEASON")
    reasons = []
    if row["identity_status"] != "ACCEPTED_RETROSPECTIVE":
        reasons.append("IDENTITY_UNRESOLVED")
    if row["area_pit_tier"] not in {
        "PIT_EVIDENCE_TIER_A_STRICT",
        "PIT_EVIDENCE_TIER_B_ASSUMED",
        "PIT_EVIDENCE_TIER_C_RETROSPECTIVE",
    }:
        reasons.append("AREA_AUTHORITY_MISSING")
    if row["season_status"] != "FROZEN_BUSINESS_WINDOW_NOT_FULL_YEAR":
        reasons.append("SEASON_AUTHORITY_UNKNOWN")
    days = (
        date.fromisoformat(row["target_end_date"]) - date.fromisoformat(row["target_start_date"])
    ).days + 1
    if days <= 0 or row["logical_record_count"] != days:
        reasons.append("DAILY_LABEL_COVERAGE_INCOMPLETE")
    for field in (
        "unknown_count",
        "partial_subtotal_count",
        "missing_count",
        "conflict_count",
        "invalid_count",
    ):
        if row[field] != 0:
            reasons.append(field.upper())
    return not reasons, reasons


def split_roles(seasons: list[str]) -> dict[str, str]:
    ordered = sorted(set(seasons))
    if any(s not in SEASONS for s in ordered):
        raise ValueError("UNAUTHORIZED_SEASON")
    if len(ordered) != 3:
        raise ValueError("THREE_SEASONS_REQUIRED")
    return dict(zip(ordered, ("TRAIN", "VALIDATION", "EXPOSED_OOT"), strict=True))


def origin_time(origin: str) -> datetime:
    parsed = datetime.fromisoformat(origin)
    if parsed.tzinfo is None:
        raise ValueError("TIMEZONE_REQUIRED")
    local = parsed.astimezone(SHANGHAI)
    if (local.hour, local.minute, local.second, local.microsecond) != (17, 0, 0, 0):
        raise ValueError("FROZEN_1700_CUTOFF_REQUIRED")
    return local


def target_dates(origin: str, end: str) -> list[str]:
    day = origin_time(origin).date()
    targets = [(day + timedelta(days=i)).isoformat() for i in range(1, 16)]
    return targets if targets[-1] <= end else []


def past_features(
    records: list[dict[str, Any]], origin: str, base: str, season: str, start: str
) -> dict[str, Any]:
    """Boundary reference implementation. Synthetic tests only; no database capability.

    Future rows are filtered using keys and dates BEFORE reading quantities. An entire
    origin-day total is also future information at 17:00 and is excluded.
    """
    if season not in SEASONS:
        raise ValueError("UNAUTHORIZED_SEASON")
    cutoff = origin_time(origin).date()
    first = date.fromisoformat(start)
    values: dict[date, Decimal | None] = {}
    for row in records:
        if row["base_id"] != base or row["season"] != season:
            continue
        day = date.fromisoformat(row["business_date"])
        if not first <= day < cutoff:
            continue
        if row["zone"] != "FEATURE_ZONE":
            raise ValueError("LABEL_ZONE_DENIED")
        if day in values:
            raise ValueError("DUPLICATE_PAST_DAY")
        value = None
        if row["state"] in COMPLETE_STATES:
            value = Decimal(str(row["quantity_kg"]))
            if not value.is_finite() or value < 0 or (row["state"] == "REAL_ZERO" and value != 0):
                raise ValueError("INVALID_COMPLETE_QUANTITY")
        values[day] = value
    result: dict[str, Any] = {}
    for label, days in [(f"past_{n}d", n) for n in (7, 14, 28)] + [
        ("season_to_date", (cutoff - first).days)
    ]:
        expected = [cutoff - timedelta(days=i) for i in range(1, days + 1)]
        window = [values.get(day) for day in expected]
        missing = sum(value is None for value in window)
        result[f"{label}_missing_count"] = missing
        result[f"{label}_kg"] = (
            None if missing else str(sum((v for v in window if v is not None), Decimal(0)))
        )
    return result


def assert_same_rowset(rowsets: dict[str, list[str]]) -> None:
    expected = next(iter(rowsets.values()), [])
    for rows in rowsets.values():
        if len(rows) != len(set(rows)):
            raise ValueError("DUPLICATE_COMPARISON_ROW")
        if rows != expected:
            raise ValueError("COMMON_ROWSET_MISMATCH")
