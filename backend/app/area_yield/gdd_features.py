"""V0.13-S2 fixed past-temperature representation; no model/label dependency."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Any

from backend.app.area_yield.data import digest

POLICY_VERSION = "V0_13_S2_GDD_7C_ROLLING_V1"
DEFINITION_ID = "V0_13_GDD_7C_SIMPLE_MEAN_R1"
POLICY: dict[str, Any] = {
    "version": POLICY_VERSION,
    "definition_id": DEFINITION_ID,
    "tbase_c": "7.0",
    "formula": "(TMAX+TMIN)/2",
    "lower_clip": "FINAL_GDD_ZERO_CLIP",
    "upper_clip": "NONE",
    "tmin_preclip": False,
    "windows": [7, 14, 30],
    "timezone": "Asia/Shanghai",
    "precision": 50,
    "decimal_places": 12,
    "rounding": "ROUND_HALF_EVEN",
    "early_daily_rounding": False,
    "season_to_date": False,
}
FEATURE_IDS = ["GDD_W7", "GDD_W14", "GDD_W30"]


class GDDError(ValueError):
    """Stable failure reason, never row data or local paths."""


def validate_policy(policy: Mapping[str, Any]) -> None:
    if dict(policy) != POLICY:
        raise GDDError("GDD_POLICY_MISMATCH")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def daily_gdd(tmax: Any, tmin: Any) -> Decimal:
    if tmin is None or tmin == "":
        raise GDDError("MISSING_TMIN")
    if tmax is None or tmax == "":
        raise GDDError("MISSING_TMAX")
    try:
        hi, lo = Decimal(str(tmax)), Decimal(str(tmin))
    except (InvalidOperation, ValueError) as exc:
        raise GDDError("NONFINITE") from exc
    if not hi.is_finite() or not lo.is_finite():
        raise GDDError("NONFINITE")
    # Explicit Celsius plausibility gate rejects silently supplied Kelvin.
    if not (-100 <= lo <= 100 and -100 <= hi <= 100):
        raise GDDError("WRONG_UNIT")
    if hi < lo:
        raise GDDError("TMAX_LT_TMIN")
    with localcontext() as ctx:
        ctx.prec = max(50, len(hi.as_tuple().digits) + len(lo.as_tuple().digits) + 10)
        return max(Decimal(0), (hi + lo) / 2 - Decimal("7.0"))


def origin_day(origin: str) -> date:
    try:
        dt = datetime.fromisoformat(origin)
    except ValueError as exc:
        raise GDDError("INVALID_ORIGIN") from exc
    if dt.utcoffset() != timedelta(hours=8) or dt.time() != time.min:
        raise GDDError("WRONG_TIMEZONE")
    if dt.isoformat() != origin:
        raise GDDError("INVALID_ORIGIN")
    return dt.date()


def parse_row_key(key: str) -> tuple[str, str, date]:
    base, sep, tail = key.partition("+")
    origin, sep2, target = tail.rpartition("+")
    if not base or not sep or not sep2:
        raise GDDError("INVALID_ROW_KEY")
    day = origin_day(origin)
    try:
        target_day = date.fromisoformat(target)
    except ValueError as exc:
        raise GDDError("INVALID_ROW_KEY") from exc
    if not 0 <= (target_day - day).days <= 14:
        raise GDDError("INVALID_ROW_LEAD")
    return base, origin, target_day


def index_daily(rows: Iterable[Mapping[str, Any]]) -> dict[tuple[str, date], Decimal | str]:
    result: dict[tuple[str, date], Decimal | str] = {}
    for row in rows:
        base = row.get("base_id")
        try:
            day = date.fromisoformat(str(row.get("local_date")))
        except ValueError as exc:
            raise GDDError("DATE_MISMATCH") from exc
        if not isinstance(base, str) or not base:
            raise GDDError("DATE_MISMATCH")
        key = base, day
        if key in result:
            result[key] = "DUPLICATE_DAY"
            continue
        try:
            if (
                row.get("processing_version") != "BASE_WEATHER_DAILY_V1"
                or row.get("hourly_sample_count") != 24
            ):
                raise GDDError("DATE_MISMATCH")
            if row.get("timezone", "Asia/Shanghai") != "Asia/Shanghai":
                raise GDDError("WRONG_TIMEZONE")
            if row.get("temperature_unit", "degrees_C") != "degrees_C":
                raise GDDError("WRONG_UNIT")
            result[key] = daily_gdd(
                row.get("sampled_local_day_tmax_c"), row.get("sampled_local_day_tmin_c")
            )
        except GDDError as exc:
            result[key] = str(exc)
    return result


def load_daily(path: Path, expected_sha256: str) -> list[dict[str, Any]]:
    if sha256(path) != expected_sha256:
        raise GDDError("WEATHER_ARTIFACT_HASH_MISMATCH")
    # The pinned accepted daily layer supplies Celsius/local-day semantics
    # omitted as explicit fields in its original schema. No alternate source.
    with path.open(encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    if not all(isinstance(row, dict) for row in rows):
        raise GDDError("DAILY_ROW_NOT_OBJECT")
    return rows


def build_gdd_context(
    index: Mapping[tuple[str, date], Decimal | str],
    base_id: str,
    forecast_origin: str,
    source_hash: str,
    *,
    policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    validate_policy(POLICY if policy is None else policy)
    if len(source_hash) != 64 or any(c not in "0123456789abcdef" for c in source_hash):
        raise GDDError("SOURCE_IDENTITY_INVALID")
    day = origin_day(forecast_origin)
    payload: dict[str, Any] = {
        "base_id": base_id,
        "forecast_origin": forecast_origin,
        "source_window_start": (day - timedelta(days=30)).isoformat(),
        "source_window_end": (day - timedelta(days=1)).isoformat(),
        "max_source_date": (day - timedelta(days=1)).isoformat(),
        "source_dataset_hash": source_hash,
        "gdd_policy_version": POLICY_VERSION,
        "eligible": True,
    }
    values: list[Decimal] = []
    for offset in range(1, 31):
        value = index.get((base_id, day - timedelta(days=offset)), "MISSING_REQUIRED_LOCAL_DAY")
        if isinstance(value, str):
            return {**payload, "eligible": False, "reason": value}
        values.append(value)
    with localcontext() as ctx:
        ctx.prec = max(50, max(len(v.as_tuple().digits) for v in values) + 10)
        for window in (7, 14, 30):
            total = sum(values[:window], Decimal(0))
            payload[f"gdd_w{window}"] = format(
                total.quantize(Decimal("1e-12"), rounding=ROUND_HALF_EVEN), "f"
            )
    payload["feature_hash"] = digest(payload)
    verify_context(payload)
    return payload


def verify_context(c: Mapping[str, Any]) -> None:
    day = origin_day(c["forecast_origin"])
    if c.get("source_window_end") != (day - timedelta(days=1)).isoformat() or c.get(
        "max_source_date"
    ) != c.get("source_window_end"):
        raise GDDError("EVENT_TIME_LEAKAGE")
    if (
        c.get("source_window_start") != (day - timedelta(days=30)).isoformat()
        or c.get("gdd_policy_version") != POLICY_VERSION
    ):
        raise GDDError("GDD_POLICY_MISMATCH")
    if c.get("feature_hash") != digest({k: v for k, v in c.items() if k != "feature_hash"}):
        raise GDDError("CONTEXT_HASH_MISMATCH")
    if not (Decimal(c["gdd_w30"]) >= Decimal(c["gdd_w14"]) >= Decimal(c["gdd_w7"]) >= 0):
        raise GDDError("NESTED_WINDOW_SANITY_FAILURE")


def build_gdd_manifest(contexts: Iterable[dict[str, Any]], source_hash: str) -> dict[str, Any]:
    rows = sorted(contexts, key=lambda c: (c["base_id"], c["forecast_origin"]))
    eligible = [c for c in rows if c["eligible"]]
    for c in eligible:
        verify_context(c)
        if c["source_dataset_hash"] != source_hash:
            raise GDDError("SOURCE_IDENTITY_MISMATCH")
    identities = [[c["base_id"], c["forecast_origin"]] for c in eligible]
    if len(identities) != len({tuple(x) for x in identities}):
        raise GDDError("DUPLICATE_CONTEXT")
    m: dict[str, Any] = {
        "schema": "V0_13_GDD_CONTEXT_MANIFEST_V1",
        "policy_version": POLICY_VERSION,
        "source_dataset_hash": source_hash,
        "source_artifact_sha256": source_hash,
        "gdd_definition_id": DEFINITION_ID,
        "tbase_c": "7.0",
        "formula": POLICY["formula"],
        "upper_clip": "NONE",
        "rounding": "ROUND_HALF_EVEN",
        "context_count": len(eligible),
        "candidate_context_count": len(rows),
        "ineligible_context_count": len(rows) - len(eligible),
        "ineligible_reason_counts": dict(
            sorted(Counter(c["reason"] for c in rows if not c["eligible"]).items())
        ),
        "base_count": len({c["base_id"] for c in eligible}),
        "origin_count": len({c["forecast_origin"] for c in eligible}),
        "feature_ids": FEATURE_IDS,
        "context_identity_hash": digest(identities),
        "feature_value_hash": digest(
            [
                {k: c[k] for k in ("base_id", "forecast_origin", "gdd_w7", "gdd_w14", "gdd_w30")}
                for c in eligible
            ]
        ),
    }
    return {**m, "manifest_hash": digest(m)}


def require_common_models(model_rows: Mapping[str, list[str]]) -> None:
    if (
        set(model_rows) != {"M0", "M1", "M2", "M3"}
        or len({digest(keys) for keys in model_rows.values()}) != 1
    ):
        raise GDDError("MODEL_SPECIFIC_COHORT")


def project_rows(
    keys: list[str], contexts: Mapping[tuple[str, str], dict[str, Any]]
) -> dict[str, Any]:
    if keys != sorted(set(keys)):
        raise GDDError("ROW_IDENTITY_ORDER_OR_DUPLICATE")
    common: list[str] = []
    projection: list[list[str]] = []
    coverage: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    views: dict[tuple[str, str], set[int]] = defaultdict(set)
    for key in keys:
        base, origin, target = parse_row_key(key)
        c = contexts.get((base, origin))
        if c is None or (c["base_id"], c["forecast_origin"]) != (base, origin):
            raise GDDError("CONTEXT_PROJECTION_IDENTITY_MISMATCH")
        season_year = target.year if target.month >= 7 else target.year - 1
        tally = coverage[base, f"{season_year}-{season_year + 1}"]
        tally["candidate"] += 1
        if not c["eligible"]:
            tally[c["reason"]] += 1
            continue
        verify_context(c)
        common.append(key)
        projection.append([key, c["feature_hash"]])
        tally["eligible"] += 1
        views[base, origin].add((target - origin_day(origin)).days)
    require_common_models({m: common for m in ("M0", "M1", "M2", "M3")})
    result: dict[str, Any] = {
        "original_row_count": len(keys),
        "original_row_keys_hash": digest(keys),
        "common_row_count": len(common),
        "common_row_keys_hash": digest(common),
        "projected_target_row_count": len(projection),
        "projected_target_row_keys_hash": digest(common),
        "gdd_projection_hash": digest(projection),
        "coverage": [
            {"base_id": b, "season": s, **dict(v)} for (b, s), v in sorted(coverage.items())
        ],
        "views": {},
    }
    for horizon, length in (("H1", 1), ("H7", 7), ("H15", 15)):
        identities = [
            [b, o] for (b, o), leads in sorted(views.items()) if set(range(length)) <= leads
        ]
        result["views"][horizon] = {"count": len(identities), "identity_hash": digest(identities)}
    result["structural_h15_not_actual_authority"] = True
    return result
