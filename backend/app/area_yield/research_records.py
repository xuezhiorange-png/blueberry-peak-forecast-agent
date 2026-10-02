"""File-mode adapter for frozen M0 research issuance and later locked scoring.

Reuses the existing request, inference, decimal/calendar and point-metric contracts.
No training, model selection, actual imputation or production default is implemented.
Local hashes detect alteration; they are not an external trusted timestamp or WORM store.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from backend.app.area_yield import m0_baseline
from backend.app.area_yield.base_product import AreaForecastProductRequest
from backend.app.area_yield.data import calendar, digest, fixed
from backend.app.area_yield.evaluation import compare, summaries

CONTRACT = "V0_11_M0_FULL_WINDOW_LOCKED_METRICS_R1"
TIMEZONE = ZoneInfo("Asia/Shanghai")
Record = dict[str, Any]


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> Record:
    payload: Record = json.loads(path.read_text())
    return payload


def _now(test_clock: datetime | None) -> datetime:
    value = test_clock if test_clock is not None else datetime.now(UTC)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("AWARE_CLOCK_REQUIRED")
    return value.astimezone(UTC)


def _seal(payload: Record) -> Record:
    if "record_hash" in payload:
        raise ValueError("PRESEALED_PAYLOAD_REJECTED")
    return {**payload, "record_hash": digest(payload)}


def verify(payload: Record) -> None:
    if payload.get("record_hash") != digest(
        {k: v for k, v in payload.items() if k != "record_hash"}
    ):
        raise ValueError("RECORD_HASH_MISMATCH")


def _save(root: Path, kind: str, payload: Record) -> Path:
    directory = root / kind / str(payload["id"])
    directory.mkdir(parents=True, exist_ok=False)
    target = directory / "record.json"
    with target.open("x") as stream:
        json.dump(payload, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
    return target


def _load(root: Path, kind: str, identity: str) -> Record:
    if Path(identity).name != identity or not identity or identity in {".", ".."}:
        raise ValueError("INVALID_RECORD_ID")
    payload = read(root / kind / identity / "record.json")
    verify(payload)
    if payload["id"] != identity or payload["kind"] != kind:
        raise ValueError("RECORD_IDENTITY_MISMATCH")
    return payload


def _registered_model(
    registry_path: Path, registry_sha256: str, model_path: Path, model_id: str
) -> tuple[Record, Record]:
    if file_hash(registry_path) != registry_sha256:
        raise ValueError("REGISTRY_HASH_MISMATCH")
    registry = read(registry_path)
    if registry["default_research_model_id"] != model_id:
        raise ValueError("EXPLICIT_M0_REFERENCE_REQUIRED")
    entries = [entry for entry in registry["models"] if entry["model_id"] == model_id]
    if len(entries) != 1:
        raise ValueError("MODEL_ID_NOT_UNIQUE")
    entry = entries[0]
    if (
        entry["model_role"] != "REFERENCE_BASELINE"
        or entry["model_family"] != m0_baseline.MODEL_ID
        or entry["approval_status"] != "RESEARCH_ONLY"
        or file_hash(model_path) != entry["artifact_file_sha256"]
    ):
        raise ValueError("MODEL_ROLE_OR_ARTIFACT_MISMATCH")
    model = m0_baseline.load_model(model_path)
    if any(
        model[key] != entry[key]
        for key in ("artifact_hash", "training_manifest_sha256", "training_cutoff")
    ):
        raise ValueError("MODEL_LINEAGE_MISMATCH")
    return model, entry


def issue(
    root: Path,
    registry_path: Path,
    registry_sha256: str,
    model_path: Path,
    model_id: str,
    request_payload: Record,
    authorization: Record,
    *,
    parent_id: str | None = None,
    test_clock: datetime | None = None,
) -> Path:
    """No caller-issued_at parameter. Explicit test clock always taints the record."""
    request = AreaForecastProductRequest.model_validate(request_payload)
    if request.base_id is None:
        raise ValueError("ANONYMOUS_STABLE_BASE_ID_REQUIRED")
    model, entry = _registered_model(registry_path, registry_sha256, model_path, model_id)
    now = _now(test_clock)
    if now.date() <= date.fromisoformat(model["training_cutoff"]):
        raise ValueError("TRAINING_CUTOFF_AFTER_ISSUANCE")
    year = int(request.target_season[:4])
    support = [date(year, 7, 1), date(year + 1, 4, 15)]
    if [request.forecast_start_date, request.forecast_end_date] != support:
        raise ValueError("FULL_TOTAL_CANNOT_BE_REASSIGNED_TO_SUBWINDOW")
    if entry["supported_request_window"] != "JULY_01_THROUGH_APRIL_15_INCLUSIVE":
        raise ValueError("MODEL_SUPPORT_CONTRACT_MISMATCH")
    if now >= datetime.combine(support[0], time.min, TIMEZONE):
        raise ValueError("PRESEASON_WINDOW_ALREADY_STARTED")
    snapshot = request.model_dump(mode="json")
    expected_authority = "TEST_ONLY" if test_clock is not None else "OWNER_AUTHORIZED"
    if (
        set(authorization)
        != {
            "status",
            "request_snapshot_hash",
            "source_version",
            "source_sha256",
            "target_actuals_used",
        }
        or authorization.get("status") != expected_authority
        or authorization.get("request_snapshot_hash") != digest(snapshot)
        or not authorization.get("source_version")
        or len(str(authorization.get("source_sha256", ""))) != 64
        or authorization.get("target_actuals_used") is not False
    ):
        raise ValueError("EXACT_REQUEST_AUTHORITY_REQUIRED")
    if parent_id:
        parent = _load(root, "predictions", parent_id)
        if parent["request_snapshot"]["base_id"] != request.base_id:
            raise ValueError("REISSUE_BASE_MISMATCH")
    # Only model coefficients/learned representation and request enter inference.
    prediction = m0_baseline.predict(model, request)
    dates = [date.fromisoformat(row["date"]) for row in prediction["daily_curve"]]
    values = [Decimal(row["predicted_quantity_kg"]) for row in prediction["daily_curve"]]
    metrics = summaries(dates, values)
    payload = _seal(
        {
            "id": str(uuid4()),
            "kind": "predictions",
            "schema": "V0_11_RESEARCH_FILE_RECORD_R1",
            "model_id": model_id,
            "model_family": m0_baseline.MODEL_ID,
            "model_artifact_hash": model["artifact_hash"],
            "model_file_sha256": file_hash(model_path),
            "registry_sha256": registry_sha256,
            "training_manifest_hash": model["training_manifest_sha256"],
            "training_cutoff": model["training_cutoff"],
            "request_snapshot": snapshot,
            "request_snapshot_hash": digest(snapshot),
            "input_sources_and_versions": authorization,
            "model_support_window": [d.isoformat() for d in support],
            "requested_target_window": [d.isoformat() for d in support],
            "target_definition": "FROZEN_BUSINESS_WINDOW_TOTAL_KG",
            "issued_at": now.isoformat(),
            "issued_at_source": "EXPLICIT_TEST_CLOCK" if test_clock else "EXECUTION_UTC_CLOCK",
            "business_timezone": "Asia/Shanghai",
            "prediction": prediction,
            "daily_prediction_hash": digest(prediction["daily_curve"]),
            "metrics": metrics,
            "metrics_hash": digest(metrics),
            "research_role": "REFERENCE_BASELINE",
            "prospective_class": "TEST_NOT_PROSPECTIVE"
            if test_clock
            else "FULL_WINDOW_PRESEASON_RESEARCH",
            "test_only": test_clock is not None,
            "parent_id": parent_id,
            "metric_contract_version": CONTRACT,
            "known_limitations": [
                "LOCAL_HASH_NOT_EXTERNAL_TRUSTED_TIMESTAMP",
                "PRODUCTION_ACCURACY_NOT_APPROVED",
                "LEGACY_RUNNER_IDENTITY_INCOMPLETE",
                "RAW_WORKBOOK_NOT_INDEPENDENTLY_REVIEWED",
                "OLD_6_INNER_1_OUTER_NUMERICAL_GAPS_REMAIN",
            ],
        }
    )
    return _save(root, "predictions", payload)


def load_prediction(root: Path, seal_id: str, model_path: Path) -> Record:
    payload = _load(root, "predictions", seal_id)
    model = m0_baseline.load_model(model_path)
    if (
        file_hash(model_path) != payload["model_file_sha256"]
        or model["artifact_hash"] != payload["model_artifact_hash"]
        or digest(payload["request_snapshot"]) != payload["request_snapshot_hash"]
        or digest(payload["prediction"]["daily_curve"]) != payload["daily_prediction_hash"]
        or digest(payload["metrics"]) != payload["metrics_hash"]
    ):
        raise ValueError("SEALED_COMPONENT_MISMATCH")
    return payload


def import_actuals(
    root: Path, seal_id: str, source: Record, *, test_clock: datetime | None = None
) -> Path:
    prediction = _load(root, "predictions", seal_id)
    if prediction["test_only"] != (test_clock is not None):
        raise ValueError("TEST_REAL_MODE_MISMATCH")
    allowed = {
        "base_id",
        "target_season",
        "unit",
        "source_version",
        "source_sha256",
        "rows",
        "supersedes",
        "revision_reason",
    }
    if set(source) - allowed:
        raise ValueError("ACTUAL_SOURCE_SCHEMA_INVALID")
    request = prediction["request_snapshot"]
    if source["unit"] != "kg" or any(
        source[key] != request[key] for key in ("base_id", "target_season")
    ):
        raise ValueError("ACTUAL_BASE_SEASON_UNIT_MISMATCH")
    if not source["source_version"] or len(source["source_sha256"]) != 64:
        raise ValueError("ACTUAL_SOURCE_IDENTITY_REQUIRED")
    now = _now(test_clock)
    seen: set[str] = set()
    for row in source["rows"]:
        if set(row) != {"date", "new_quantity_kg", "status"}:
            raise ValueError("ACTUAL_ROW_SCHEMA_INVALID")
        day = date.fromisoformat(row["date"])
        if (
            row["date"] in seen
            or not prediction["requested_target_window"][0]
            <= row["date"]
            <= prediction["requested_target_window"][1]
        ):
            raise ValueError("ACTUAL_DUPLICATE_OR_WINDOW_MISMATCH")
        seen.add(row["date"])
        if day > now.astimezone(TIMEZONE).date():
            raise ValueError("FUTURE_ACTUAL_OBSERVATION_REJECTED")
        if row["status"] not in {"OBSERVED", "CONFIRMED_ZERO", "MISSING"}:
            raise ValueError("ACTUAL_COVERAGE_STATUS_INVALID")
        if row["status"] == "MISSING":
            if row["new_quantity_kg"] is not None:
                raise ValueError("MISSING_IS_NOT_ZERO")
        else:
            value = Decimal(row["new_quantity_kg"])
            if not value.is_finite() or value < 0:
                raise ValueError("ACTUAL_QUANTITY_INVALID")
            if row["status"] == "CONFIRMED_ZERO" and value != 0:
                raise ValueError("CONFIRMED_ZERO_NOT_ZERO")
    supersedes = source.get("supersedes")
    if supersedes:
        prior = _load(root, "actuals", supersedes)
        if prior["prediction_seal_id"] != seal_id or not source.get("revision_reason"):
            raise ValueError("ACTUAL_REVISION_LINEAGE_INVALID")
    return _save(
        root,
        "actuals",
        _seal(
            {
                "id": str(uuid4()),
                "kind": "actuals",
                "prediction_seal_id": seal_id,
                "prediction_seal_hash": prediction["record_hash"],
                "source": source,
                "source_snapshot_hash": digest(source),
                "first_ingested_at": now.isoformat(),
                "test_only": prediction["test_only"],
                "quantity_field": "new_quantity_kg",
                "label_assumption": "ARRIVAL_EQUALS_HARVEST_EQUALS_MATURITY_PROXY",
            }
        ),
    )


def _mass_date(dates: list[date], values: list[Decimal], fraction: Decimal) -> str | None:
    total = sum(values, Decimal(0))
    if total <= 0:
        return None
    cumulative = Decimal(0)
    for day, value in zip(dates, values, strict=True):
        cumulative += value
        if cumulative >= fraction * total:
            return day.isoformat()
    raise ValueError("CDF_MASS_INCONSISTENT")


def score_curve(rows: list[Record], prediction: Record) -> Record:
    dates = [date.fromisoformat(row["date"]) for row in rows]
    actual = [Decimal(row["new_quantity_kg"]) for row in rows]
    predicted = [Decimal(row["predicted_quantity_kg"]) for row in prediction["daily_curve"]]
    result = compare(
        [{"date": r["date"], "actual_kg": r["new_quantity_kg"]} for r in rows], predicted
    )
    q, qhat = sum(actual, Decimal(0)), sum(predicted, Decimal(0))
    absolute = sum((abs(a - p) for a, p in zip(actual, predicted, strict=True)), Decimal(0))
    shape_error = (
        sum((abs(p * q / qhat - a) for a, p in zip(actual, predicted, strict=True)), Decimal(0))
        if qhat > 0 and q > 0
        else None
    )
    result.update(
        {
            "actual_total_kg": fixed(q),
            "total_absolute_error_kg": fixed(abs(qhat - q)),
            "daily_absolute_error_kg": fixed(absolute),
            "shape_absolute_error_kg": fixed(shape_error) if shape_error is not None else None,
            "timing_shape_micro_wape": fixed(shape_error / q) if shape_error is not None else None,
            "window_total_wape": fixed(abs(qhat - q) / q) if q > 0 else None,
            "total_signed_bias_kg": fixed(qhat - q),
            "total_underestimated": qhat < q,
            "total_overestimated": qhat > q,
        }
    )
    for name, fraction in (("P10", Decimal(".1")), ("P50", Decimal(".5")), ("P90", Decimal(".9"))):
        a, p = _mass_date(dates, actual, fraction), _mass_date(dates, predicted, fraction)
        signed = (date.fromisoformat(p) - date.fromisoformat(a)).days if a and p else None
        result[name] = {
            "actual": a,
            "predicted": p,
            "signed_days": signed,
            "absolute_days": abs(signed) if signed is not None else None,
        }
    for name, field, dayfield in (
        ("single_day_peak", "quantity_kg", "date"),
        ("rolling_7day_peak", "cumulative_quantity_kg", "start_date"),
    ):
        a, p = result["actual"][name], result["predicted"][name]
        bias = Decimal(p[field]) - Decimal(a[field])
        result[name + "_bias"] = {
            "quantity_kg": fixed(bias),
            "underestimated": bias < 0,
            "overestimated": bias > 0,
            "signed_days": (date.fromisoformat(p[dayfield]) - date.fromisoformat(a[dayfield])).days,
        }
    return result


def evaluate(
    root: Path,
    seal_id: str,
    actual_id: str,
    metric_contract_version: str,
    model_path: Path,
    *,
    test_clock: datetime | None = None,
    parent_id: str | None = None,
) -> Path:
    if metric_contract_version != CONTRACT:
        raise ValueError("LOCKED_METRIC_CONTRACT_REQUIRED")
    prediction = load_prediction(root, seal_id, model_path)
    actual = _load(root, "actuals", actual_id)
    if (
        prediction["test_only"] != (test_clock is not None)
        or actual["test_only"] != prediction["test_only"]
    ):
        raise ValueError("TEST_REAL_MODE_MISMATCH")
    if (
        actual["prediction_seal_id"] != seal_id
        or actual["prediction_seal_hash"] != prediction["record_hash"]
    ):
        raise ValueError("ACTUAL_PREDICTION_IDENTITY_MISMATCH")
    now = _now(test_clock)
    if now <= datetime.fromisoformat(actual["first_ingested_at"]):
        raise ValueError("EVALUATION_BEFORE_ACTUAL_INGESTION")
    end = date.fromisoformat(prediction["requested_target_window"][1])
    if now.astimezone(TIMEZONE).date() <= end:
        raise ValueError("FULL_WINDOW_NOT_ENDED")
    start = date.fromisoformat(prediction["requested_target_window"][0])
    rows = sorted(actual["source"]["rows"], key=lambda r: r["date"])
    if [r["date"] for r in rows] != [d.isoformat() for d in calendar(start, end)] or any(
        r["status"] == "MISSING" for r in rows
    ):
        raise ValueError("FULL_ACTUAL_COVERAGE_REQUIRED_NO_IMPUTATION")
    if parent_id:
        parent = _load(root, "evaluations", parent_id)
        if parent["prediction_seal_id"] != seal_id:
            raise ValueError("REEVALUATION_LINEAGE_MISMATCH")
    metrics = score_curve(rows, prediction["prediction"])
    return _save(
        root,
        "evaluations",
        _seal(
            {
                "id": str(uuid4()),
                "kind": "evaluations",
                "prediction_seal_id": seal_id,
                "prediction_seal_hash": prediction["record_hash"],
                "actual_snapshot_id": actual_id,
                "actual_snapshot_hash": actual["record_hash"],
                "metric_contract_version": CONTRACT,
                "evaluated_at": now.isoformat(),
                "metrics": metrics,
                "metrics_hash": digest(metrics),
                "test_only": prediction["test_only"],
                "parent_id": parent_id,
                "prospective_accuracy_validated": False,
            }
        ),
    )


def aggregate(metrics: list[Record]) -> Record:
    """Same-cohort micro WAPE adds numerators/denominators, not Base percentages."""
    denominator = sum((Decimal(m["actual_total_kg"]) for m in metrics), Decimal(0))
    result: Record = {"cohort_count": len(metrics), "actual_total_kg": fixed(denominator)}
    for field, name in (
        ("total_absolute_error_kg", "window_total_wape"),
        ("daily_absolute_error_kg", "full_daily_wape"),
        ("shape_absolute_error_kg", "timing_shape_micro_wape"),
    ):
        if any(m[field] is None for m in metrics):
            result[name] = None
        else:
            numerator = sum((Decimal(m[field]) for m in metrics), Decimal(0))
            result[name] = fixed(numerator / denominator) if denominator > 0 else None
    result["total_signed_bias_kg"] = fixed(
        sum((Decimal(m["total_signed_bias_kg"]) for m in metrics), Decimal(0))
    )
    for direction in ("underestimated", "overestimated"):
        result["total_" + direction + "_count"] = sum(m["total_" + direction] for m in metrics)
    for quantile in ("P10", "P50", "P90"):
        values = [m[quantile]["absolute_days"] for m in metrics]
        result[quantile + "_timing_mae_days"] = (
            sum(values) / len(values) if values and all(v is not None for v in values) else None
        )
    for name, quantity, timing in (
        ("single_day_peak", "single_day_peak_absolute_error_kg", "single_day_peak_date_error_days"),
        (
            "rolling_7day_peak",
            "rolling_7day_peak_absolute_error_kg",
            "rolling_7day_window_shift_days",
        ),
    ):
        result[name + "_quantity_mae_kg"] = (
            fixed(sum((Decimal(m[quantity]) for m in metrics), Decimal(0)) / len(metrics))
            if metrics
            else None
        )
        result[name + "_timing_mae_days"] = (
            sum(m[timing] for m in metrics) / len(metrics) if metrics else None
        )
        result[name + "_signed_bias_kg"] = fixed(
            sum((Decimal(m[name + "_bias"]["quantity_kg"]) for m in metrics), Decimal(0))
        )
        for direction in ("underestimated", "overestimated"):
            result[name + "_" + direction + "_count"] = sum(
                m[name + "_bias"][direction] for m in metrics
            )
    return result
