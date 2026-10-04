"""Sealed prospective pair issuance boundary; no fitting or actual scoring."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from backend.app.area_yield.data import digest
from backend.app.area_yield.formal_multi_season_validation import BusinessBoundary
from backend.app.area_yield.v014_future_weather_features import (
    FEATURE_NAMES,
    POLICY,
    require,
    validate_policy,
    verify_artifact,
    verify_pair,
)
from backend.app.area_yield.weather_aware_backtest import (
    BASE_FEATURES,
    _base_feature_values,
    target_row_key,
)
from backend.app.pit.canonical import hash_payload
from backend.app.pit.schemas import AreaRevisionInput

TZ = ZoneInfo("Asia/Shanghai")
BASE_ID = "base_a96b297b126a8cab67c4755f"
BASE_NAME = "保山杨柳基地"
AREA_HASH = "213c4aa66b7a102ec0561508b7b604bbf8ae9cc30c37bdeb0008df2460fc4274"
AREA_FILE_SHA = "9fbd36297b03700f33f25656976713feffddefe0304430c75199ac7222948d49"
AREA_MANIFEST_HASH = "907e3e07cad968eda9612058e8623d20867912ce09593c6d3d2c510784cb5ab9"
BUNDLE_HASH = "18f22af283a0f6f548afebba8136f3a0ae4a35c166c6c8b20388d188f2fe00df"
MODEL_HASHES = {
    "c0": "787c95168f3ac106b50d5e78f3c84201e744ad4264708de9f6ea852a6f6d6059",
    "w1": "4a5a56cd8c896290ffdd0cdc9e347cd754d076520006ed56d990d711710cb923",
}
COHORT_ID = "V0_14_AS_ISSUED_WEATHER_PROSPECTIVE_COHORT_R1"
METRIC_ID = "V0_14_PROSPECTIVE_H7_H15_LOCKED_METRICS_R1"
SEAL_SCHEMA = "V0_14_PROSPECTIVE_PREDICTION_SEAL_V1"


def read_json(path: Path) -> Any:
    require(not path.is_symlink(), "UNSAFE_INPUT_SYMLINK")
    return json.loads(path.read_bytes())


def json_bytes(body: Any) -> bytes:
    return (
        json.dumps(body, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode()


def write_immutable(path: Path, body: Any) -> None:
    require(not path.is_symlink(), "IMMUTABLE_CONFLICT")
    raw = json_bytes(body)
    if path.exists():
        require(path.read_bytes() == raw, "DUPLICATE_PROSPECTIVE_REQUEST_CONFLICT")
        return
    with path.open("xb") as stream:
        stream.write(raw)


def operation_gate(operation: str) -> None:
    require(
        operation in {"scope", "bundle", "capture", "predict", "seal", "replay"},
        "FORBIDDEN_EXECUTION",
    )


def recover_area(root: Path, store: Path) -> AreaRevisionInput:
    raw = (root / "area-revision.json").read_bytes()
    require(hashlib.sha256(raw).hexdigest() == AREA_FILE_SHA, "S3A_ARTIFACT_MISMATCH")
    area = AreaRevisionInput.model_validate_json(raw)
    manifest = read_json(root / "authority-manifest.json")
    require(
        hash_payload({k: v for k, v in manifest.items() if k != "manifest_hash"})
        == manifest.get("manifest_hash")
        == AREA_MANIFEST_HASH,
        "S3A_MANIFEST_MISMATCH",
    )
    require(
        manifest["artifact_sha256"] == AREA_FILE_SHA and manifest["payload_hash"] == AREA_HASH,
        "S3A_MANIFEST_MISMATCH",
    )
    revisions = [
        AreaRevisionInput.model_validate_json(p.read_bytes())
        for p in sorted(store.rglob("area-revision.json"))
    ]
    verify_scope(area, revisions)
    return area


def verify_scope(area: AreaRevisionInput, revisions: list[AreaRevisionInput]) -> None:
    require(area.payload_hash == area.computed_payload_hash() == AREA_HASH, "S3A_PAYLOAD_MISMATCH")
    require(
        (area.base_id, area.season, area.area_type) == (BASE_ID, "2026-2027", "REFERENCE_AREA"),
        "S3A_SCOPE_MISMATCH",
    )
    relevant = [r for r in revisions if r.base_id == BASE_ID and r.season == "2026-2027"]
    for r in relevant:
        require(r.payload_hash == r.computed_payload_hash(), "INVALID_REVISION_HASH")
        require(
            all(
                x.payload_hash == r.payload_hash
                for x in relevant
                if x.area_revision_id == r.area_revision_id
            ),
            "CONFLICTING_REVISION_ID",
        )
    superseded = {r.supersedes_revision_id for r in relevant if r.supersedes_revision_id}
    terminal = {r.area_revision_id: r for r in relevant if r.area_revision_id not in superseded}
    require(
        len(terminal) == 1
        and area.area_revision_id in terminal
        and terminal[area.area_revision_id].payload_hash == AREA_HASH,
        "CURRENT_SEASON_AREA_AUTHORITY_CONFLICT",
    )


def verify_area_time(area: AreaRevisionInput, created: datetime, origin: datetime) -> None:
    require(
        area.recorded_at <= area.known_at <= created
        and area.effective_from <= origin
        and (area.effective_to is None or origin < area.effective_to),
        "AREA_PIT_INVALID",
    )


def recover_bundle(root: Path) -> dict[str, Any]:
    manifest = read_json(root / "bundle-manifest.json")
    require(
        digest(manifest["files"]) == manifest["bundle_hash"] == BUNDLE_HASH, "S2_BUNDLE_MISMATCH"
    )
    names = {
        "feature-policy.json",
        "training-cohort-manifest.json",
        "c0-artifact.json",
        "w1-artifact.json",
        "historical-proxy-manifest.json",
        "live-feature-surface-manifest.json",
    }
    require({e["name"] for e in manifest["files"]} == names, "BUNDLE_MEMBER_MISMATCH")
    for entry in manifest["files"]:
        name = Path(entry["name"])
        require(len(name.parts) == 1 and not name.is_absolute(), "UNSAFE_BUNDLE_PATH")
        raw = (root / name).read_bytes()
        require(
            hashlib.sha256(raw).hexdigest() == entry["sha256"] and len(raw) == entry["size"],
            "BUNDLE_MEMBER_MISMATCH",
        )
    validate_policy(read_json(root / "feature-policy.json"))
    models = {role: read_json(root / f"{role}-artifact.json") for role in MODEL_HASHES}
    for role, artifact in models.items():
        verify_artifact(artifact)
        require(artifact["artifact_hash"] == MODEL_HASHES[role], "FROZEN_MODEL_HASH_MISMATCH")
    verify_pair(models["c0"], models["w1"])
    return models


def model_origin(created: datetime) -> datetime:
    require(created.tzinfo is not None, "NAIVE_TIMESTAMP")
    earliest = (created + timedelta(hours=6)).astimezone(TZ)
    candidate = datetime.combine(earliest.date(), time.min, tzinfo=TZ)
    return candidate if candidate >= earliest else candidate + timedelta(days=1)


def verify_timing(created: datetime, origin: datetime, sealed: datetime) -> None:
    require(all(t.tzinfo is not None for t in (created, origin, sealed)), "NAIVE_TIMESTAMP")
    require(
        origin.astimezone(TZ).time() == time.min and origin == model_origin(created),
        "MODEL_ORIGIN_POLICY_MISMATCH",
    )
    require(
        origin - created >= timedelta(hours=6) and created < sealed < origin,
        "ISSUANCE_CROSSED_MODEL_ORIGIN_BOUNDARY",
    )


def verify_weather_receipt(surface: dict[str, Any], created: datetime) -> None:
    issued = datetime.fromisoformat(surface["issued_at"])
    receipt = surface["acquisition_receipt"]
    require(
        issued.tzinfo is not None
        and issued.hour in {0, 12}
        and issued.minute == issued.second == issued.microsecond == 0
        and surface["run_id"] == issued.strftime("%Y%m%d%H%M%S"),
        "INVALID_PROVIDER_RUN",
    )
    require(
        issued
        <= datetime.fromisoformat(receipt["fetched_at"])
        <= datetime.fromisoformat(receipt["known_at"])
        <= created,
        "WEATHER_PIT_INVALID",
    )
    require(receipt["manifest_sha256"] == surface["raw_manifest_sha256"], "WEATHER_MANIFEST_DRIFT")


def target_rows(
    area: AreaRevisionInput, origin: datetime, weather: dict[str, str]
) -> list[dict[str, Any]]:
    require(set(weather) == set(FEATURE_NAMES), "SELECTED_SCOPE_W1_FEATURE_SURFACE_INCOMPLETE")
    boundary = BusinessBoundary(
        "2026-2027",
        date(2026, 7, 1),
        date(2027, 4, 15),
        "OWNER_S3_R2_BUSINESS_BOUNDARY",
        digest(["2026-07-01", "2027-04-15"]),
        "FROZEN_S3_R2",
    )
    result = []
    for lead in range(15):
        target = origin.astimezone(TZ).date() + timedelta(days=lead)
        require(
            boundary.start <= target <= boundary.end,
            "FULL_H15_TARGET_WINDOW_OUTSIDE_BUSINESS_BOUNDARY",
        )
        base = _base_feature_values(
            reference_area_mu=area.area_mu, target_date=target, boundary=boundary
        )
        result.append(
            {
                "key": target_row_key(
                    base_id=area.base_id, forecast_origin=origin, target_date=target
                ),
                "base_id": area.base_id,
                "season": area.season,
                "forecast_origin": origin.isoformat(),
                "target_date": target.isoformat(),
                "lead_day": lead,
                "features": {**base, **weather},
                "weather_source": "ECMWF_IFS_OPEN_DATA",
                "weather_lane": "AS_ISSUED_FUTURE_FORECAST",
                "feature_policy_version": POLICY["feature_policy_id"],
            }
        )
    verify_rows(result)
    return result


def verify_rows(rows: list[dict[str, Any]]) -> None:
    require(len(rows) == 15 and len({r["key"] for r in rows}) == 15, "TARGET_ROW_UNIVERSE_MISMATCH")
    for lead, row in enumerate(rows):
        origin = datetime.fromisoformat(row["forecast_origin"])
        target = date.fromisoformat(row["target_date"])
        require(
            row["base_id"] == BASE_ID
            and row["season"] == "2026-2027"
            and row["lead_day"] == lead
            and target == origin.astimezone(TZ).date() + timedelta(days=lead)
            and row["key"]
            == target_row_key(base_id=BASE_ID, forecast_origin=origin, target_date=target),
            "TARGET_ROW_IDENTITY_MISMATCH",
        )
        require(
            row["weather_source"] == "ECMWF_IFS_OPEN_DATA"
            and row["weather_lane"] == "AS_ISSUED_FUTURE_FORECAST"
            and row["feature_policy_version"] == POLICY["feature_policy_id"],
            "WRONG_WEATHER_LANE",
        )
        require(
            set(row["features"]) == set(BASE_FEATURES + FEATURE_NAMES)
            and all(math.isfinite(float(v)) for v in row["features"].values()),
            "INVALID_FEATURE_MATRIX",
        )


def predict_pair(models: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, list[list[str]]]:
    operation_gate("predict")
    verify_rows(rows)
    verify_pair(models["c0"], models["w1"])
    result = {}
    for role, artifact in models.items():
        verify_artifact(artifact)
        require(
            artifact["feature_names"]
            == list(BASE_FEATURES + (FEATURE_NAMES if role == "w1" else ())),
            "C0_WEATHER_CONSUMPTION",
        )
        predictions = []
        for row in rows:
            value = float(artifact["intercept"]) + sum(
                float(coefficient) * ((float(row["features"][name]) - float(mean)) / float(scale))
                for name, mean, scale, coefficient in zip(
                    artifact["feature_names"],
                    artifact["feature_means"],
                    artifact["feature_scales"],
                    artifact["coefficients"],
                    strict=True,
                )
            )
            require(math.isfinite(value), "NONFINITE_PREDICTION")
            predictions.append([row["key"], format(max(0.0, value), ".12f")])
        result[role] = predictions
    require([r[0] for r in result["c0"]] == [r[0] for r in result["w1"]], "PAIR_TARGET_MISMATCH")
    return result


def metric_contract() -> dict[str, Any]:
    return {
        "id": METRIC_ID,
        "actual_target": "BASE_DAILY_HARVEST_KG",
        "actual_grain": "BASE_ID_X_HARVEST_BUSINESS_DATE",
        "actual_unit": "KG",
        "business_timezone": "Asia/Shanghai",
        "missing_is_zero": False,
        "statuses": {
            "OBSERVED": "quantity required >=0",
            "AUTHORIZED_ZERO": "quantity exactly 0",
            "MISSING": "quantity null",
        },
        "horizons": {"H7": list(range(7)), "H15": list(range(15))},
        "completeness": "ALL_LEADS_OBSERVED_OR_AUTHORIZED_ZERO;NO_PARTIAL_DENOMINATOR",
        "incomplete": "NOT_COMPUTABLE_INCOMPLETE_ACTUAL",
        "zero_denominator": "NOT_COMPUTABLE_ZERO_ACTUAL_DENOMINATOR",
        "primary": ["H7_DAILY_WAPE", "H15_DAILY_WAPE"],
        "wape": "sum(abs(pred-actual))/sum(actual)",
        "mae": "mean(abs(pred-actual))",
        "bias": "mean(pred-actual)",
        "single_peak": "H15_COMPLETE_VECTOR_MAX_DAILY_EARLIEST_DATE_TIE",
        "rolling7_peak": "H15_COMPLETE_VECTOR_MAX_9_CONSECUTIVE_7_DAY_SUMS_EARLIEST_START_TIE",
        "shape": (
            "Q=sum(actual);P=sum(pred);Q<=0 or P<=0 => NOT_COMPUTABLE;"
            "else sum(abs(pred_i*Q/P-actual_i))/Q;NO_EPSILON"
        ),
        "pair_fairness": "SAME_ACTUAL_SNAPSHOT_TARGET_ROWS_DENOMINATOR_COMPLETENESS",
        "business_promotion_threshold": None,
    }


def self_seal(body: dict[str, Any]) -> dict[str, Any]:
    return {**body, "seal_hash": digest(body)}


def verify_seal(seal: dict[str, Any]) -> None:
    require(
        seal["seal_hash"] == digest({k: v for k, v in seal.items() if k != "seal_hash"}),
        "SEAL_HASH_TAMPER",
    )


def validate_public(value: Any) -> None:
    forbidden = {
        "predicted_daily_kg",
        "predictions",
        "h7_total_kg",
        "h15_total_kg",
        "peak_kg",
        "features",
        "coordinates",
        "latitude",
        "longitude",
        "coefficients",
        "actual_daily_kg",
        "feature_values",
    }
    if isinstance(value, dict):
        require(not forbidden.intersection(value), "PRIVATE_PUBLIC_DISCLOSURE")
        for item in value.values():
            validate_public(item)
    elif isinstance(value, list):
        for item in value:
            validate_public(item)
    elif isinstance(value, str):
        require(
            not any(p in value for p in ("/Users/", "/private/", "/tmp/")),
            "PRIVATE_PATH_DISCLOSURE",
        )
