"""S2 deterministic numeric materialization. No fit, prediction, SQL or network.

Feature construction accepts origin metadata and area only. Label construction
is a separate application path. Retrospective grades are never upgraded.
"""

import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

from backend.app.area_yield.formal_multi_season_validation import business_boundary
from backend.app.area_yield.v014_future_weather_features import (
    FEATURE_NAMES,
    REQUIRED_FIELDS,
    aggregate_ifs,
)
from backend.app.area_yield.v015_research_cohort import (
    COMPLETE_STATES,
    SEASONS,
    digest,
    origin_time,
    target_dates,
)
from backend.app.area_yield.weather_aware_backtest import BASE_FEATURES, _base_feature_values
from scripts.audit_v0_15_ecmwf_semantics import availability
from scripts.audit_v0_15_precip_packing_policy import window_precip

POLICY_ID = "V0_15_S2_RESEARCH_NUMERIC_MATERIALIZATION_R1"


def read_feature_artifact(path: Path, *, expected_file_sha256: str) -> list[dict[str, Any]]:
    """The feature-reader path cannot point at a label artifact, including symlinks."""
    resolved = path.resolve(strict=True)
    if resolved.parent.name != "feature_zone":
        raise ValueError("LABEL_ZONE_DENIED")
    raw = resolved.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_file_sha256:
        raise ValueError("FEATURE_ARTIFACT_HASH_DRIFT")
    rows: list[dict[str, Any]] = json.loads(raw)
    if not isinstance(rows, list):
        raise ValueError("FEATURE_ARTIFACT_REQUIRED")
    for row in rows:
        if {"labels", "daily", "h7_total", "h15_total", "quantity_kg"}.intersection(row):
            raise ValueError("LABEL_ZONE_DENIED")
        if not ({"base10", "weather8"} & row.keys()):
            raise ValueError("FEATURE_ARTIFACT_REQUIRED")
        vectors = row.get("base10", [row.get("weather8")])
        expected = set(BASE_FEATURES if "base10" in row else FEATURE_NAMES)
        if any(set(v) != expected for v in vectors):
            raise ValueError("FEATURE_COLUMNS_CHANGED")
    # Target hashes belong to lineage/audit, not to the predictor's input.
    return [
        {k: v for k, v in row.items() if k in {"row_key", "base10", "weather8", "feature_hash"}}
        for row in rows
    ]


def validate_weather_cache(cache: dict[str, Any], row: dict[str, Any]) -> None:
    if cache["provider"] != "ECMWF_IFS_OPEN_DATA" or cache["status"] != "COMPLETE":
        raise ValueError("WEATHER_NOT_AS_ISSUED_OR_INCOMPLETE")
    if (
        cache["run_id"] != row["selected_run_id"]
        or digest({k: v for k, v in cache.items() if k != "cache_hash"}) != cache["cache_hash"]
    ):
        raise ValueError("WEATHER_CACHE_IDENTITY_INVALID")
    validate_weather_origin(cache["run_id"], row)
    if cache["location_authority_sha256"] != (
        "502c73fecdf68e91e4aa35982a2207d224204390597eaf59420ebd1101539904"
    ):
        raise ValueError("LOCATION_AUTHORITY_CHANGED")
    receipts = cache["raw_receipts"]
    if len(receipts) != 256 or {(r["step"], r["parameter"]) for r in receipts} != set(
        REQUIRED_FIELDS
    ):
        raise ValueError("RAW_PROVENANCE_INCOMPLETE")
    for r in receipts:
        m = r["metadata"]
        if (
            m["dataDate"] != int(cache["run_id"][:8])
            or m["dataTime"] != int(cache["run_id"][8:10]) * 100
            or m["shortName"] != r["parameter"]
            or m["endStep"] != r["step"]
            or (m["marsClass"], m["marsStream"], m["marsType"]) != ("od", "oper", "fc")
            or len(r["raw_sha256"]) != 64
            or r["raw_size"] <= 0
        ):
            raise ValueError("RAW_RUN_PROVENANCE_INVALID")


def validate_weather_origin(run_id: str, row: dict[str, Any]) -> None:
    """Validate the cutoff for each row, including reuse of a verified run."""
    if run_id != row["selected_run_id"]:
        raise ValueError("WEATHER_CACHE_IDENTITY_INVALID")
    issued = datetime.strptime(run_id, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    if issued.hour not in (0, 12) or not availability(issued, origin_time(row["forecast_origin"])):
        raise ValueError("PUBLICATION_CUTOFF_FAILED")


def authorized(season: str) -> None:
    if season not in SEASONS:
        raise ValueError("UNAUTHORIZED_SEASON")


def validate_origin(row: dict[str, Any]) -> None:
    authorized(row["season"])
    if (
        row["temporal_role"]
        != dict(zip(SEASONS, ("TRAIN", "VALIDATION", "EXPOSED_OOT"), strict=True))[row["season"]]
    ):
        raise ValueError("SPLIT_CHANGED")
    boundary = business_boundary(row["season"])
    if row["target_dates"] != target_dates(row["forecast_origin"], boundary.end.isoformat()):
        raise ValueError("TARGET_WINDOW_CHANGED_OR_TAIL")
    if (
        len(row["target_dates"]) != 15
        or date.fromisoformat(row["target_dates"][0]) < boundary.start
    ):
        raise ValueError("TARGET_OUTSIDE_BOUNDARY")


def base_vectors(row: dict[str, Any], area: Decimal) -> list[dict[str, str]]:
    validate_origin(row)
    if not area.is_finite() or area <= 0:
        raise ValueError("INVALID_AREA_AUTHORITY")
    boundary = business_boundary(row["season"])
    vectors = [
        _base_feature_values(
            reference_area_mu=area, target_date=date.fromisoformat(day), boundary=boundary
        )
        for day in row["target_dates"]
    ]
    if any(
        set(v) != set(BASE_FEATURES) or any(not Decimal(x).is_finite() for x in v.values())
        for v in vectors
    ):
        raise ValueError("INVALID_BASE10_VECTOR")
    return vectors


def daily_index(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    result = {}
    # Check the entire envelope before inspecting any quantity, never filter-and-continue.
    for row in rows:
        authorized(row["season"])
    for row in rows:
        key = row["base_id"], row["season"], row["date"]
        if key in result:
            raise ValueError("DUPLICATE_LOGICAL_KEY")
        result[key] = row
    return result


def source_quality(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Descriptive source audit; never changes S0 states or admits excluded rows."""
    daily_index(rows)
    result = {
        season: {
            "record_count": 0,
            "complete_state_count": 0,
            "incomplete_state_count": 0,
            "negative_count": 0,
            "nonfinite_count": 0,
            "complete_quantity_missing_count": 0,
            "real_zero_mismatch_count": 0,
            "outside_business_boundary_count": 0,
            "broken_source_lineage_count": 0,
        }
        for season in SEASONS
    }
    for row in rows:
        counts = result[row["season"]]
        counts["record_count"] += 1
        complete = row["record_state"] in COMPLETE_STATES
        counts["complete_state_count" if complete else "incomplete_state_count"] += 1
        raw = row["quantity_kg"]
        if raw is None:
            counts["complete_quantity_missing_count"] += int(complete)
        else:
            value = Decimal(str(raw))
            if not value.is_finite():
                counts["nonfinite_count"] += 1
            else:
                counts["negative_count"] += int(value < 0)
                counts["real_zero_mismatch_count"] += int(
                    row["record_state"] == "REAL_ZERO" and value != 0
                )
        boundary = business_boundary(row["season"])
        counts["outside_business_boundary_count"] += int(
            not boundary.start <= date.fromisoformat(row["date"]) <= boundary.end
        )
        counts["broken_source_lineage_count"] += int(not row["source_hashes"])
    return result


def label_vector(
    row: dict[str, Any], index: dict[tuple[str, str, str], dict[str, Any]]
) -> dict[str, Any]:
    validate_origin(row)
    days = row["target_dates"]
    values = []
    sources = set()
    for day in days:
        r = index.get((row["base_id"], row["season"], day))
        if r is None or r["record_state"] not in COMPLETE_STATES:
            raise ValueError("INCOMPLETE_LABEL")
        value = Decimal(str(r["quantity_kg"]))
        if not value.is_finite() or value < 0 or (r["record_state"] == "REAL_ZERO" and value != 0):
            raise ValueError("INVALID_QUANTITY")
        if not r["source_hashes"]:
            raise ValueError("BROKEN_SOURCE_LINEAGE")
        sources.update(r["source_hashes"])
        values.append(value)
    with localcontext() as ctx:
        ctx.prec = 50
        rolling = [sum(values[i : i + 7], Decimal(0)) for i in range(9)]
        peak, roll = values.index(max(values)), rolling.index(max(rolling))
        return {
            "daily": list(map(str, values)),
            "h7_total": str(sum(values[:7], Decimal(0))),
            "h15_total": str(sum(values, Decimal(0))),
            "single_day_peak_quantity": str(values[peak]),
            "single_day_peak_date": days[peak],
            "rolling7_peak_quantity": str(rolling[roll]),
            "rolling7_peak_start_date": days[roll],
            "source_hashes": sorted(sources),
        }


def weather_vector(fields: dict[tuple[int, str], dict[str, Any]]) -> dict[str, str]:
    if set(fields) != set(REQUIRED_FIELDS):
        raise ValueError("WEATHER_FIELDS_INCOMPLETE")
    # Owner-authorized S0 trace rule changes ONLY block-B precipitation. The
    # V0.14 authoritative aggregator still validates all units/time semantics.
    corrected = {k: dict(v) for k, v in fields.items()}
    with localcontext() as ctx:
        ctx.prec = 50
        a, b = Decimal(str(fields[168, "tp"]["value"])), Decimal(str(fields[360, "tp"]["value"]))
        delta = window_precip((b - a) * 1000, Decimal("0.08"))
        corrected[360, "tp"]["value"] = str(a + delta / 1000)
        vector = aggregate_ifs(corrected)
    if set(vector) != set(FEATURE_NAMES) or any(
        not Decimal(v).is_finite() for v in vector.values()
    ):
        raise ValueError("WEATHER_NUMERIC_MATERIALIZATION_FAILED")
    return vector


def validate_public(value: Any) -> None:
    forbidden = {
        "quantity_kg",
        "latitude",
        "longitude",
        "coordinates",
        "password",
        "token",
        "daily",
        "vectors",
        "features",
        "d1_actual",
        "source_file",
        "coefficients",
        "labels",
        "base10",
        "weather8",
        "base_fields",
        "h7_total",
        "h15_total",
        "single_day_peak_quantity",
        "single_day_peak_date",
        "rolling7_peak_quantity",
        "rolling7_peak_start_date",
        "api_key",
        "secret",
        "credentials",
        "database_url",
    }
    if isinstance(value, dict):
        if forbidden.intersection(k.lower() for k in value):
            raise ValueError("PUBLIC_PRIVACY_VIOLATION")
        for k in value:
            validate_public(k)
        for v in value.values():
            validate_public(v)
    elif isinstance(value, list):
        for v in value:
            validate_public(v)
    elif isinstance(value, str) and (
        any(
            p in value
            for p in (
                "/Users/",
                "/private/",
                "/var/",
                "/tmp/",
                "/opt/",
                "/root/",
                "/home/",
                "/etc/",
                "postgresql://",
                "postgres://",
            )
        )
        or ("postgresql+" in value and "://" in value)
    ):
        raise ValueError("PUBLIC_PRIVACY_VIOLATION")
