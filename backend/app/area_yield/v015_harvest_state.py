"""Four date-bound retrospective features. No SQL, labels, model or weather access.

The input envelope is checked for unauthorized seasons before any quantity is
inspected. For each origin, only prior in-season days can affect bytes or hashes.
This is not evidence of historical ingestion/availability at the exact cutoff.
"""

import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Any

from backend.app.area_yield.formal_multi_season_validation import business_boundary
from backend.app.area_yield.v015_research_cohort import (
    COMPLETE_STATES,
    SEASONS,
    digest,
    origin_time,
)

POLICY_ID = "V0_15_HARVEST_STATE_V1_DATE_BOUND_R1"
FEATURES = (
    "past_7d_harvest_kg",
    "past_14d_harvest_kg",
    "past_28d_harvest_kg",
    "season_to_date_harvest_kg",
)
SPLITS = dict(zip(SEASONS, ("TRAIN", "VALIDATION", "EXPOSED_OOT"), strict=True))
GRADE = "RETROSPECTIVE_DATE_BOUND"
ROW_FIELDS = frozenset(
    {
        "row_key",
        "base_id",
        "season",
        "forecast_origin",
        "split",
        "harvest_state_v1",
        "audit",
        "harvest_state_complete",
        "feature_policy_version",
        "feature_policy_hash",
        "authority_grade",
        "source_hashes",
        "harvest_state_feature_hash",
        "row_hash",
        "exclusion_reasons",
        "retrospective_authority_used",
        "strict_pit",
        "prospective_claim_allowed",
    }
)


def policy() -> dict[str, Any]:
    return {
        "policy_id": POLICY_ID,
        "features": list(FEATURES),
        "model_feature_count": 4,
        "future_combined_feature_count": 14,
        "timezone": "Asia/Shanghai",
        "origin_local_time": "17:00:00",
        "date_predicate": "BUSINESS_DATE_STRICTLY_LESS_THAN_ORIGIN_LOCAL_DATE",
        "windows": [7, 14, 28, "FROZEN_BUSINESS_SEASON_START_TO_ORIGIN_MINUS_ONE"],
        "allowed_daily_states": sorted(COMPLETE_STATES),
        "decimal_precision": 50,
        "missing_window_value": None,
        "preseason_zero_allowed": False,
        "missing_counts_model_features": False,
        "fill_allowed": False,
        "statistical_outliers_auto_deleted": False,
        "origin_level_vector": True,
        "same_vector_for_d1_d15": True,
        "strict_pit": False,
        "authority_grade": GRADE,
        "historical_available_at_proven": False,
        "retrospective_authority_used": True,
        "prospective_claim_allowed": False,
        "s3_metrics_direct_comparison_allowed": False,
        "s5_requires_refit_base10_comparator_on_common_rowset": True,
        "model_training_executed": False,
        "model_scoring_executed": False,
        "weather_feature_used": False,
        "feature_lineage": "ONLY_PRIOR_DAY_SOURCE_HASHES_AND_PRIOR_DAY_CANONICAL_RECORD_HASHES",
        "origin_row_identity": "FROZEN_S2_ROW_KEY_NOT_REDERIVED_FROM_LABELS",
    }


def history_index(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    for row in rows:
        if row.get("season") == "2026-2027":
            raise ValueError("FAIL_CURRENT_SEASON_ACTUAL_PRESENT")
        if row.get("season") not in SEASONS:
            raise ValueError("UNAUTHORIZED_SEASON")
    result = {}
    for row in rows:
        key = row["base_id"], row["season"], row["date"]
        if key in result:
            raise ValueError("DUPLICATE_BASE_SEASON_DATE")
        boundary = business_boundary(row["season"])
        if not boundary.start <= date.fromisoformat(row["date"]) <= boundary.end:
            raise ValueError("DATE_OUTSIDE_SEASON")
        result[key] = row
    return result


def valid_day(row: dict[str, Any]) -> tuple[Decimal | None, str | None]:
    if row["record_state"] not in COMPLETE_STATES:
        return None, "INCOMPLETE_DAILY_STATE_" + row["record_state"]
    try:
        value = Decimal(str(row["quantity_kg"]))
    except InvalidOperation:
        return None, "INVALID_EXCLUDE"
    if (
        not value.is_finite()
        or value < 0
        or (row["record_state"] == "REAL_ZERO" and value != 0)
        or row.get("conflict_status", ["NONE"]) != ["NONE"]
        or not row.get("logical_record_id")
        or not row.get("source_hashes")
        or any(not isinstance(h, str) or len(h) != 64 for h in row["source_hashes"])
    ):
        return None, "INVALID_EXCLUDE"
    return value, None


def build_row(
    origin: dict[str, Any], index: dict[tuple[str, str, str], dict[str, Any]]
) -> dict[str, Any]:
    season = origin["season"]
    if season not in SPLITS:
        raise ValueError("FAIL_CURRENT_SEASON_ACTUAL_PRESENT")
    if origin["split"] != SPLITS[season]:
        raise ValueError("SPLIT_CHANGED")
    cutoff = origin_time(origin["forecast_origin"]).date()
    boundary = business_boundary(season)
    if not boundary.start <= cutoff <= boundary.end:
        raise ValueError("ORIGIN_OUTSIDE_SEASON")
    prior: dict[date, Decimal | None] = {}
    hashes, reasons = set(), set()
    consumed_hashes = []
    day = boundary.start
    # Only these keys are looked up. Origin-day and future quantities/lineage are
    # never inspected, even when supplied in the same historical envelope.
    while day < cutoff:
        source = index.get((origin["base_id"], season, day.isoformat()))
        if source is None:
            prior[day] = None
            reasons.add("MISSING_BUSINESS_DAY")
        else:
            value, reason = valid_day(source)
            prior[day] = value
            if reason:
                reasons.add(reason)
            # Hash only consumed past-row fields, not the seasonal input file.
            hashes.update(source.get("source_hashes", []))
            consumed_hashes.append(
                digest(
                    {
                        k: source.get(k)
                        for k in (
                            "logical_record_id",
                            "base_id",
                            "season",
                            "date",
                            "record_state",
                            "quantity_kg",
                            "source_hashes",
                            "conflict_status",
                        )
                    }
                )
            )
        day += timedelta(days=1)
    vector, audit = {}, {}
    with localcontext() as ctx:
        ctx.prec = 50
        for feature, length in zip(FEATURES, (7, 14, 28, None), strict=True):
            first = cutoff - timedelta(days=length) if length else boundary.start
            days = [first + timedelta(days=i) for i in range((cutoff - first).days)]
            missing = sum(prior.get(d) is None for d in days)
            key = feature.replace("_harvest_kg", "_missing_count")
            audit[key] = missing
            vector[feature] = (
                None
                if missing
                else str(sum((v for d in days if (v := prior[d]) is not None), Decimal(0)))
            )
            if first < boundary.start:
                reasons.add("HARVEST_STATE_INCOMPLETE_PRIOR_WINDOW")
    hashes.add(digest(consumed_hashes))
    complete = all(n == 0 for n in audit.values())
    row = {
        **{k: origin[k] for k in ("row_key", "base_id", "season", "forecast_origin", "split")},
        "harvest_state_v1": vector,
        "audit": audit,
        "harvest_state_complete": complete,
        "feature_policy_version": POLICY_ID,
        "feature_policy_hash": digest(policy()),
        "authority_grade": GRADE,
        "strict_pit": False,
        "retrospective_authority_used": True,
        "prospective_claim_allowed": False,
        "source_hashes": sorted(hashes),
        "exclusion_reasons": sorted(reasons),
        "harvest_state_feature_hash": digest(vector),
    }
    row["row_hash"] = digest(row)
    return row


def target_vectors(row: dict[str, Any]) -> list[dict[str, str]]:
    if not row["harvest_state_complete"]:
        raise ValueError("HARVEST_STATE_BENCHMARK_EXCLUDED")
    return [dict(row["harvest_state_v1"]) for _ in range(15)]


def read_artifact(path: Path, expected_sha256: str) -> list[dict[str, Any]]:
    resolved = path.resolve(strict=True)
    if resolved.parent.name != "feature_zone":
        raise ValueError("LABEL_ZONE_DENIED")
    raw = resolved.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("FEATURE_ARTIFACT_DRIFT")
    rows: list[dict[str, Any]] = json.loads(raw)
    for row in rows:
        if set(row) != ROW_FIELDS or set(row["harvest_state_v1"]) != set(FEATURES):
            raise ValueError("FEATURE_SCHEMA_CONTAMINATION")
        if (
            row["feature_policy_hash"] != digest(policy())
            or (digest({k: v for k, v in row.items() if k != "row_hash"}) != row["row_hash"])
            or digest(row["harvest_state_v1"]) != row["harvest_state_feature_hash"]
        ):
            raise ValueError("FEATURE_HASH_DRIFT")
    return [
        {
            k: row[k]
            for k in (
                "row_key",
                "harvest_state_v1",
                "harvest_state_complete",
                "harvest_state_feature_hash",
            )
        }
        for row in rows
    ]
