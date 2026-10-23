"""S6 bounded adapter around the frozen V0.15 feature kernels, not new sums."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from backend.app.area_yield import v015_harvest_state as harvest
from backend.app.area_yield.formal_multi_season_validation import business_boundary
from backend.app.area_yield.weather_aware_backtest import _base_feature_values
from backend.research.v019_synthetic_validation import digest

SEASONS = ("2023-2024", "2024-2025", "2025-2026")
STATES = {"VALID_OBSERVED", "CONFIRMED_ZERO", "UNKNOWN", "PARTIAL", "MISSING", "CONFLICTING"}
FEATURES = harvest.FEATURES
VERSION = "V0_19_ORIGIN_HARVEST_ADAPTER_V1"
SNAPSHOT_FIELDS = frozenset(
    {
        "row_key",
        "base_id",
        "season",
        "origin",
        "cutoff",
        "timezone",
        "target_dates",
        "area_mu",
        "season_start",
        "season_end",
        "feature_ranges",
        "values",
        "complete",
        "reasons",
        "audit",
        "past_state_counts",
        "source_identity",
        "unit",
        "physical_basis",
        "historical_available_at_status",
        "authority_grade",
        "strict_pit",
        "kernel_policy_sha256",
        "version",
        "sha256",
    }
)


def validate_cutoff(origin: date, value: str) -> None:
    """Preserve both frozen end-of-day precisions without changing C0 bytes."""
    clock = datetime.fromisoformat(value)
    if (
        clock.utcoffset() != timedelta(hours=8)
        or clock.date() != origin
        or (clock.hour, clock.minute, clock.second) != (23, 59, 59)
        or clock.microsecond not in (0, 999999)
    ):
        raise ValueError("ORIGIN_RESEARCH_SEMANTICS_CHANGED")


def snapshot(
    base_id: str,
    season: str,
    origin: date,
    area_mu: Decimal,
    history: list[dict[str, Any]],
    days: int,
    *,
    cutoff: str | None = None,
) -> dict[str, Any]:
    if season not in SEASONS or any(r["season"] not in SEASONS for r in history):
        raise ValueError("UNAUTHORIZED_SEASON")
    if not base_id or not area_mu.is_finite() or area_mu <= 0:
        raise ValueError("BASE_OR_AREA_IDENTITY")
    boundary = business_boundary(season)
    cutoff = cutoff or str(origin) + "T23:59:59.999999+08:00"
    validate_cutoff(origin, cutoff)
    if days not in (7, 15) or origin + timedelta(days=days) > boundary.end:
        raise ValueError("TARGET_WINDOW_OUTSIDE_SEASON")
    # Select date/identity BEFORE accessing any quantity or quantity lineage.
    selected = [
        r
        for r in history
        if r["base_id"] == base_id
        and r["season"] == season
        and boundary.start <= date.fromisoformat(r["date"]) < origin
    ]
    normalized = []
    for r in selected:
        if r["state"] not in STATES:
            raise ValueError("UNKNOWN_STATE_ENUM")
        normalized.append(
            {
                "base_id": base_id,
                "season": season,
                "date": r["date"],
                "quantity_kg": r["kg"],
                "record_state": {"CONFIRMED_ZERO": "REAL_ZERO", "PARTIAL": "PARTIAL_SUBTOTAL"}.get(
                    r["state"], r["state"]
                ),
                "logical_record_id": r["authority_sha256"],
                "source_hashes": [r["source_sha256"]],
                "conflict_status": ["CONFLICT"] if r["state"] == "CONFLICTING" else ["NONE"],
            }
        )
    index = harvest.history_index(normalized)
    row_key = digest({"base": base_id, "season": season, "origin": str(origin)})
    # build_row's public contract fixes 17:00 but its date predicate is <D.
    # Bridge only the kernel clock, never claim this as issuance/availability.
    request = {
        "row_key": row_key,
        "base_id": base_id,
        "season": season,
        "forecast_origin": str(origin) + "T17:00:00+08:00",
        "split": dict(zip(SEASONS, ("TRAIN", "VALIDATION", "EXPOSED_OOT"), strict=True))[season],
    }
    if boundary.start <= origin <= boundary.end:
        kernel = harvest.build_row(request, index)
        values, complete, reasons, audit = (
            kernel["harvest_state_v1"],
            kernel["harvest_state_complete"],
            kernel["exclusion_reasons"],
            kernel["audit"],
        )
        lineage = kernel["source_hashes"]
    else:
        values, complete, reasons, audit = (
            dict.fromkeys(FEATURES),
            False,
            ["ORIGIN_OUTSIDE_SEASON"],
            {},
        )
        lineage = []
    body = {
        "row_key": row_key,
        "base_id": base_id,
        "season": season,
        "origin": str(origin),
        "cutoff": cutoff,
        "timezone": "Asia/Shanghai",
        "target_dates": [str(origin + timedelta(days=i)) for i in range(1, days + 1)],
        "area_mu": str(area_mu),
        "season_start": str(boundary.start),
        "season_end": str(boundary.end),
        "feature_ranges": {
            f: [
                str(origin - timedelta(days=n)) if n else str(boundary.start),
                str(origin - timedelta(days=1)),
            ]
            for f, n in zip(FEATURES, (7, 14, 28, 0), strict=True)
        },
        "values": values,
        "complete": complete,
        "reasons": reasons,
        "audit": audit,
        "past_state_counts": dict(sorted(Counter(r["state"] for r in selected).items())),
        "source_identity": lineage,
        "unit": "kg",
        "physical_basis": "RECORDED_INBOUND_NET_WEIGHT"
        if season == "2025-2026"
        else "RECORDED_INBOUND_WEIGHT",
        "historical_available_at_status": "NOT_PROVEN",
        "authority_grade": "RETROSPECTIVE_DATE_BOUND",
        "strict_pit": False,
        "kernel_policy_sha256": digest(harvest.policy()),
        "version": VERSION,
    }
    return {**body, "sha256": digest(body)}


def validate(row: dict[str, Any]) -> None:
    if set(row) != SNAPSHOT_FIELDS:
        raise ValueError("FEATURE_SCHEMA_EXTRA_OR_MISSING_FIELD")
    if row.get("sha256") != digest({k: v for k, v in row.items() if k != "sha256"}):
        raise ValueError("FEATURE_SNAPSHOT_HASH")
    if row["version"] != VERSION or row["kernel_policy_sha256"] != digest(harvest.policy()):
        raise ValueError("FEATURE_POLICY_CHANGED")
    if row["season"] not in SEASONS or set(row["values"]) != set(FEATURES):
        raise ValueError("FEATURE_SCHEMA")
    boundary = business_boundary(row["season"])
    origin = date.fromisoformat(row["origin"])
    validate_cutoff(origin, row["cutoff"])
    if (
        row["row_key"]
        != digest({"base": row["base_id"], "season": row["season"], "origin": str(origin)})
        or row["timezone"] != "Asia/Shanghai"
        or row["unit"] != "kg"
        or row["strict_pit"] is not False
    ):
        raise ValueError("FEATURE_ORIGIN_UNIT_OR_TIME_CHANGED")
    if row["season_start"] != str(boundary.start) or row["season_end"] != str(boundary.end):
        raise ValueError("FEATURE_BOUNDARY_CHANGED")
    if (
        row["target_dates"]
        != [str(origin + timedelta(days=i)) for i in range(1, len(row["target_dates"]) + 1)]
        or len(row["target_dates"]) not in (7, 15)
        or row["target_dates"][-1] > str(boundary.end)
    ):
        raise ValueError("TARGET_WINDOW_CHANGED")
    if row["complete"] and any(
        v is None or not Decimal(v).is_finite() or Decimal(v) < 0 for v in row["values"].values()
    ):
        raise ValueError("INVALID_COMPLETE_FEATURE")


def base10(row: dict[str, Any]) -> list[dict[str, str]]:
    validate(row)
    return [
        _base_feature_values(
            reference_area_mu=Decimal(row["area_mu"]),
            target_date=date.fromisoformat(d),
            boundary=business_boundary(row["season"]),
        )
        for d in row["target_dates"]
    ]
