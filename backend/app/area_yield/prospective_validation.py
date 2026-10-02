"""V0.12 E1 TEST_ONLY adapter over existing file locks, seals and metric kernels.

No training, real issuance, imputation, model selection or database is reachable.
Hashes detect corruption, not privileged rewriting or externally trusted time.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from backend.app.area_yield import area_size_r1
from backend.app.area_yield import research_records as legacy
from backend.app.area_yield import research_records_r2 as r2
from backend.app.area_yield.data import calendar, digest, fixed
from backend.app.area_yield.evaluation import summaries

Record = dict[str, Any]
SCHEMA = "V0_12_E1_TEST_ONLY_FILE_RECORD_R1"
CONTRACT = "V0_12_E1_LOCKED_POINT_METRICS_R1"
SPEC = {
    "version": CONTRACT,
    "quantity": "EXACT_NONNEGATIVE_MICROKG_STRING",
    "window": "JULY01_APRIL15_BUSINESS_WINDOW_TOTAL_NOT_NATURAL_FULL_SEASON",
    "coverage": "FULL_CONTIGUOUS_NO_MISSING",
    "peak": "EARLIEST_TIE_COMPLETE_SEVEN_CALENDAR_DAY_CUMULATIVE",
    "smape": "MEAN_2_ABS_ERROR_OVER_ACTUAL_PLUS_PREDICTED_ZERO_PAIR_CONTRIBUTION_ZERO",
    "zero_denominator": "NULL_NOT_EPSILON",
    "decision": "NOT_EXECUTED_SYNTHETIC_ENGINEERING_ONLY",
}


class ProspectiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    request_id: str
    request_mode: Literal["TEST_ONLY", "REAL_PROSPECTIVE"]
    requested_at: str
    target_area_mu: str
    target_season: str
    base_id_or_farm_context: str
    forecast_start_date: str
    forecast_end_date: str
    candidate_model_id: str
    candidate_artifact_hash: str
    candidate_config_hash: str
    comparator_id: str
    comparator_artifact_or_policy_hash: str
    request_source_id: str
    request_source_version: str
    request_source_hash: str
    authorization_id: str
    authorization_status: Literal["TEST_ONLY", "REAL_PROSPECTIVE"]


def binding() -> Record:
    return {
        "version": CONTRACT,
        "specification_hash": digest(SPEC),
        "implementation_hash": digest(
            {
                "v012_adapter": legacy.file_hash(Path(__file__)),
                "canonical_metrics": r2.implementation_identity(),
            }
        ),
    }


def config_snapshot(model: Record) -> Record:
    return {
        key: model[key]
        for key in (
            "model_family",
            "model_version",
            "parameters",
            "curve_parameters",
            "target_definition",
            "quantity_precision",
            "features",
        )
    }


def _aware(value: str) -> datetime:
    return legacy._now(datetime.fromisoformat(value))


def _id(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value) is None:
        raise ValueError("SAFE_STABLE_ID_REQUIRED")
    return value


def request_source_payload(request: Record) -> Record:
    return {
        k: v
        for k, v in request.items()
        if k
        not in {
            "request_source_hash",
            "authorization_id",
            "authorization_status",
        }
    }


def actual_source_payload(actual: Record) -> Record:
    return {k: v for k, v in actual.items() if k != "source_hash"}


def _content(path: Path, expected_hash: str, expected_payload: Record) -> None:
    if legacy.file_hash(path) != r2.sha256(expected_hash):
        raise ValueError("SOURCE_CONTENT_HASH_MISMATCH")
    if legacy.read(path) != expected_payload:
        raise ValueError("SOURCE_CANONICAL_PAYLOAD_MISMATCH")


def validate_request(payload: Record, stamp: datetime) -> Record:
    if payload.get("request_mode") == "REAL_PROSPECTIVE":
        raise ValueError("REAL_PROSPECTIVE_NOT_AUTHORIZED")
    request = ProspectiveRequest.model_validate(payload).model_dump()
    if request["authorization_status"] != "TEST_ONLY":
        raise ValueError("REAL_PROSPECTIVE_NOT_AUTHORIZED")
    for key in (
        "request_id",
        "request_source_id",
        "request_source_version",
        "base_id_or_farm_context",
        "authorization_id",
    ):
        _id(request[key])
    for key in (
        "candidate_artifact_hash",
        "candidate_config_hash",
        "comparator_artifact_or_policy_hash",
        "request_source_hash",
    ):
        r2.sha256(request[key])
    if area_size_r1.number(request["target_area_mu"]) <= 0:
        raise ValueError("POSITIVE_AREA_MU_REQUIRED")
    match = re.fullmatch(r"(\d{4})-(\d{4})", request["target_season"])
    if not match or int(match[2]) != int(match[1]) + 1 or not 2024 <= int(match[1]) <= 9998:
        raise ValueError("TARGET_SEASON_INVALID")
    year = int(match[1])
    if [request["forecast_start_date"], request["forecast_end_date"]] != [
        f"{year}-07-01",
        f"{year + 1}-04-15",
    ]:
        raise ValueError("FULL_TOTAL_CANNOT_BE_REASSIGNED_TO_SUBWINDOW")
    if _aware(request["requested_at"]) > stamp:
        raise ValueError("REQUEST_AFTER_ISSUANCE")
    r2._cutoff(stamp, {"identity": {"window": [request["forecast_start_date"]]}})
    return request


def register_artifact(model_path: Path, metadata: Record) -> Record:
    """Resolve supplied public artifact, no discovery or training path."""
    model = legacy.read(model_path)
    legacy.verify(
        {
            "record_hash": model["artifact_hash"],
            **{k: v for k, v in model.items() if k != "artifact_hash"},
        }
    )
    required = {
        "registry_id",
        "model_role",
        "training_manifest_hash",
        "training_cutoff",
        "code_sha",
        "source_execution_id",
        "synthetic",
        "active_for_research",
    }
    if (
        set(metadata) != required
        or metadata["model_role"]
        not in {
            "RESEARCH_CANDIDATE",
            "COMPARATOR_BASELINE",
        }
        or metadata["active_for_research"] is not True
    ):
        raise ValueError("ARTIFACT_REGISTRATION_INVALID")
    r2.sha256(metadata["training_manifest_hash"])
    if metadata["training_manifest_hash"] != digest(model["training_identity"]):
        raise ValueError("ARTIFACT_TRAINING_MANIFEST_IDENTITY_MISMATCH")
    if type(metadata["synthetic"]) is not bool:
        raise ValueError("EXPLICIT_SYNTHETIC_CLASSIFICATION_REQUIRED")
    if re.fullmatch(r"[0-9a-f]{40}", metadata["code_sha"]) is None:
        raise ValueError("CODE_SHA_INVALID")
    date.fromisoformat(metadata["training_cutoff"])
    cutoff_year = max(int(season[:4]) for season in model["training_seasons"]) + 1
    if metadata["training_cutoff"] != f"{cutoff_year}-04-15":
        raise ValueError("ARTIFACT_TRAINING_CUTOFF_MISMATCH")
    if (
        "base_sha" in model["training_identity"]
        and metadata["code_sha"] != model["training_identity"]["base_sha"]
    ):
        raise ValueError("ARTIFACT_CODE_IDENTITY_MISMATCH")
    if model["target_definition"] != SPEC["window"] or model["model_version"] != "1":
        raise ValueError("ARTIFACT_MODEL_SUPPORT_MISMATCH")
    area_min, area_max = map(area_size_r1.number, model["training_area_range_mu"])
    if area_min <= 0 or area_max < area_min:
        raise ValueError("TRAINING_AREA_SUPPORT_INVALID")
    return {
        **metadata,
        "model_id": model["model_id"],
        "model_family": model["model_family"],
        "approval_status": "RESEARCH_ONLY",
        "production_approved": False,
        "artifact_hash": model["artifact_hash"],
        "artifact_file_hash": legacy.file_hash(model_path),
        "artifact_path": str(model_path.resolve()),
        "config_hash": digest(config_snapshot(model)),
        "training_seasons": model["training_seasons"],
        "training_sample_count": model["training_sample_count"],
        "training_area_min_mu": str(area_min),
        "training_area_max_mu": str(area_max),
        "created_at": model["created_at"],
        "content_verified": True,
    }


def save_registry(path: Path, entries: list[Record]) -> None:
    if len({e["registry_id"] for e in entries}) != len(entries):
        raise ValueError("DUPLICATE_REGISTRY_ID")
    r2._write(path, legacy._seal({"schema": SCHEMA, "entries": entries}))


def _resolve(registry: Record, identity: str, role: str, stamp: datetime) -> tuple[Record, Record]:
    matches = [entry for entry in registry["entries"] if entry["registry_id"] == identity]
    if len(matches) != 1:
        raise ValueError("ARTIFACT_NOT_REGISTERED")
    entry = matches[0]
    if (
        entry["model_role"] != role
        or entry["approval_status"] != "RESEARCH_ONLY"
        or entry["production_approved"] is not False
        or entry["active_for_research"] is not True
        or entry.get("content_verified") is not True
    ):
        raise ValueError("ARTIFACT_ROLE_OR_CONTENT_NOT_VERIFIED")
    path = Path(entry["artifact_path"])
    if legacy.file_hash(path) != entry["artifact_file_hash"]:
        raise ValueError("ARTIFACT_FILE_HASH_MISMATCH")
    model = legacy.read(path)
    if (
        model["model_id"] != entry["model_id"]
        or model["artifact_hash"] != entry["artifact_hash"]
        or digest(config_snapshot(model)) != entry["config_hash"]
        or entry["model_family"] != model["model_family"]
        or entry["training_seasons"] != model["training_seasons"]
        or entry["training_sample_count"] != model["training_sample_count"]
        or entry["training_manifest_hash"] != digest(model["training_identity"])
        or [entry["training_area_min_mu"], entry["training_area_max_mu"]]
        != model["training_area_range_mu"]
    ):
        raise ValueError("ARTIFACT_REGISTRATION_IDENTITY_MISMATCH")
    if stamp.date() <= date.fromisoformat(entry["training_cutoff"]):
        raise ValueError("TRAINING_CUTOFF_AFTER_ISSUANCE")
    expected_family = "candidate" if role == "RESEARCH_CANDIDATE" else "baseline"
    if model["model_family"] != expected_family:
        raise ValueError("CANDIDATE_COMPARATOR_FAMILY_MISMATCH")
    return model, entry


def curve_summary(rows: list[Record]) -> Record:
    return summaries(
        [date.fromisoformat(r["date"]) for r in rows],
        [Decimal(r2.quantity(r["predicted_daily_quantity_kg"])) for r in rows],
    )


def _prediction(model: Record, request: Record) -> Record:
    prediction = area_size_r1.predict(
        model,
        request["target_area_mu"],
        int(request["target_season"][:4]),
        request["base_id_or_farm_context"],
    )
    _check_prediction(prediction, request)
    return {**prediction, "canonical_summary": curve_summary(prediction["daily_curve"])}


def _check_prediction(prediction: Record, request: Record) -> None:
    if prediction["result_hash"] != digest(
        {k: v for k, v in prediction.items() if k not in {"result_hash", "canonical_summary"}}
    ):
        raise ValueError("PREDICTION_RESULT_HASH_MISMATCH")
    rows = prediction["daily_curve"]
    expected = [
        d.isoformat()
        for d in calendar(
            date.fromisoformat(request["forecast_start_date"]),
            date.fromisoformat(request["forecast_end_date"]),
        )
    ]
    if [r["date"] for r in rows] != expected:
        raise ValueError("DAILY_CONTIGUOUS_WINDOW_REQUIRED")
    summary = curve_summary(rows)
    if Decimal(summary["total_kg"]) != Decimal(
        r2.quantity(prediction["predicted_season_total_kg"])
    ):
        raise ValueError("PREDICTION_TOTAL_CONSERVATION_MISMATCH")
    if "canonical_summary" in prediction and prediction["canonical_summary"] != summary:
        raise ValueError("PEAK_SUMMARY_MISMATCH")


def _base(kind: str, forecast: Record, stamp: datetime) -> Record:
    return {
        "id": str(uuid4()),
        "kind": kind,
        "schema": SCHEMA,
        "identity": forecast["identity"],
        "test_only": True,
        "prospective_class": "TEST_NOT_PROSPECTIVE",
        "occurred_at": stamp.isoformat(),
        "prediction_seal_id": forecast["id"],
        "prediction_seal_hash": forecast["record_hash"],
    }


def _read_record(root: Path, kind: str, identity: str, seen: set[str] | None = None) -> Record:
    record = legacy._load(root, kind, identity)
    if (
        record["schema"] != SCHEMA
        or record["test_only"] is not True
        or record["prospective_class"] != "TEST_NOT_PROSPECTIVE"
    ):
        raise ValueError("E1_TEST_ONLY_RECORD_REQUIRED")
    seen = set() if seen is None else seen.copy()
    if identity in seen:
        raise ValueError("LINEAGE_CYCLE")
    seen.add(identity)
    r2._completion(root, record)
    if _aware(record["committed_at"]) < _aware(record["occurred_at"]):
        raise ValueError("TIME_REVERSAL")
    if kind == "predictions":
        if record["metric_binding"] != binding():
            raise ValueError("SEALED_METRIC_IMPLEMENTATION_MISMATCH")
        stamps = [_aware(record[k]) for k in ("started_at", "prediction_generated_at", "sealed_at")]
        if stamps != sorted(stamps) or record["issued_at"] != record["sealed_at"]:
            raise ValueError("FORECAST_TIME_ORDER_INVALID")
        request = validate_request(record["request_snapshot"], stamps[0])
        if record["request_hash"] != digest(request) or record["prediction_hash"] != digest(
            record["prediction"]
        ):
            raise ValueError("FORECAST_SEAL_MISMATCH")
        for name in ("candidate", "comparator"):
            model = record["artifact_snapshots"][name]
            entry = record["artifact_entries"][name]
            if model["artifact_hash"] != digest(
                {k: v for k, v in model.items() if k != "artifact_hash"}
            ):
                raise ValueError("SEALED_ARTIFACT_HASH_MISMATCH")
            if entry["artifact_hash"] != model["artifact_hash"] or entry["config_hash"] != digest(
                config_snapshot(model)
            ):
                raise ValueError("SEALED_CONFIG_MISMATCH")
            _check_prediction(record["prediction"][name], request)
        if (
            record["artifact_entries"]["candidate"]["artifact_hash"]
            != request["candidate_artifact_hash"]
            or record["artifact_entries"]["candidate"]["config_hash"]
            != request["candidate_config_hash"]
            or record["artifact_entries"]["comparator"]["artifact_hash"]
            != request["comparator_artifact_or_policy_hash"]
        ):
            raise ValueError("SEALED_REQUEST_ARTIFACT_MISMATCH")
    else:
        forecast = _read_record(root, "predictions", record["prediction_seal_id"], seen)
        if forecast["record_hash"] != record["prediction_seal_hash"]:
            raise ValueError("FORECAST_SEAL_LINEAGE_MISMATCH")
        r2.relation(record, r2._published(root, forecast), same_kind=False)
        if kind == "actual-revisions" and record.get("parent_revision_id"):
            parent = _read_record(root, kind, record["parent_revision_id"], seen)
            if parent["record_hash"] != record["parent_hash"] or not record["revision_reason"]:
                raise ValueError("ACTUAL_REVISION_LINEAGE_MISMATCH")
            r2.relation(record, r2._published(root, parent), same_kind=False)
            if parent["prediction_seal_id"] != record["prediction_seal_id"]:
                raise ValueError("ACTUAL_REVISION_FORECAST_MISMATCH")
        if kind == "snapshots":
            revision = _read_record(root, "actual-revisions", record["revision_ids"][0], seen)
            if (
                revision["record_hash"] != record["revision_hashes"][0]
                or revision["rows"] != record["rows"]
            ):
                raise ValueError("SNAPSHOT_REVISION_MISMATCH")
            if revision["prediction_seal_id"] != record["prediction_seal_id"]:
                raise ValueError("SNAPSHOT_FORECAST_MISMATCH")
        if kind == "evaluations":
            snapshot = _read_record(root, "snapshots", record["actual_snapshot_id"], seen)
            if snapshot["record_hash"] != record["actual_snapshot_hash"]:
                raise ValueError("EVALUATION_SNAPSHOT_MISMATCH")
            if (
                record["metric_binding"] != forecast["metric_binding"]
                or record["metrics_hash"] != digest(record["metrics"])
                or snapshot["prediction_seal_id"] != record["prediction_seal_id"]
            ):
                raise ValueError("LOCKED_EVALUATION_IDENTITY_MISMATCH")
    return record


def get_record(root: Path, kind: str, identity: str) -> Record:
    if kind not in {"predictions", "actual-revisions", "snapshots", "evaluations"}:
        raise ValueError("RECORD_TYPE_INVALID")
    with r2.locked(root, exclusive=False):
        return _read_record(root, kind, identity)


def get_research_forecast(root: Path, forecast_id: str) -> Record:
    return get_record(root, "predictions", forecast_id)


verify_research_forecast = get_research_forecast


def create_research_forecast(
    root: Path,
    registry_path: Path,
    registry_hash: str,
    request_payload: Record,
    source_path: Path,
    authorization_path: Path,
    *,
    clock: r2.Clock = None,
) -> Record:
    started = r2.now(clock)
    request = validate_request(request_payload, started)
    _content(source_path, request["request_source_hash"], request_source_payload(request))
    authorization = legacy.read(authorization_path)
    if (
        set(authorization) != {"authorization_id", "status", "request_hash", "operator"}
        or authorization["authorization_id"] != request["authorization_id"]
        or authorization["status"] != "TEST_ONLY"
        or not authorization["operator"]
        or authorization["request_hash"] != digest(request)
    ):
        raise ValueError("EXACT_REQUEST_AUTHORIZATION_REQUIRED")
    if legacy.file_hash(registry_path) != r2.sha256(registry_hash):
        raise ValueError("REGISTRY_HASH_MISMATCH")
    registry = legacy.read(registry_path)
    legacy.verify(registry)
    candidate, candidate_entry = _resolve(
        registry, request["candidate_model_id"], "RESEARCH_CANDIDATE", started
    )
    comparator, comparator_entry = _resolve(
        registry, request["comparator_id"], "COMPARATOR_BASELINE", started
    )
    if (
        candidate_entry["artifact_hash"] != request["candidate_artifact_hash"]
        or candidate_entry["config_hash"] != request["candidate_config_hash"]
        or comparator_entry["artifact_hash"] != request["comparator_artifact_or_policy_hash"]
    ):
        raise ValueError("REQUEST_REGISTERED_IDENTITY_MISMATCH")
    with r2.locked(root, exclusive=True):
        for path in (root / "predictions").glob("*/record.json"):
            prior = _read_record(root, "predictions", path.parent.name)
            if prior["request_snapshot"]["request_id"] == request["request_id"]:
                raise ValueError("DUPLICATE_REQUEST_ISSUANCE")
        prediction = {
            "candidate": _prediction(candidate, request),
            "comparator": _prediction(comparator, request),
        }
        generated = r2.now(clock)
        if generated < started:
            raise ValueError("TIME_REVERSAL")
        year = int(request["target_season"][:4])
        record: Record = {
            "id": str(uuid4()),
            "kind": "predictions",
            "schema": SCHEMA,
            "identity": {
                "base_id": request["base_id_or_farm_context"],
                "target_season": request["target_season"],
                "window": [f"{year}-07-01", f"{year + 1}-04-15"],
                "unit": "kg",
                "target_definition": SPEC["window"],
            },
            "test_only": True,
            "prospective_class": "TEST_NOT_PROSPECTIVE",
            "started_at": started.isoformat(),
            "prediction_generated_at": generated.isoformat(),
            "occurred_at": generated.isoformat(),
            "request_snapshot": request,
            "request_hash": digest(request),
            "prediction": prediction,
            "prediction_hash": digest(prediction),
            "metric_binding": binding(),
            "metric_contract_version": CONTRACT,
            "artifact_entries": {"candidate": candidate_entry, "comparator": comparator_entry},
            "artifact_snapshots": {"candidate": candidate, "comparator": comparator},
            "registry_hash": registry_hash,
            "authorization": authorization,
            "authorization_content_hash": legacy.file_hash(authorization_path),
            "source_verification": (
                "CONTENT_HASH_AND_EXACT_REQUEST_VERIFIED_NOT_BUSINESS_FACT_VERIFIED"
            ),
            "business_timezone": "Asia/Shanghai",
            "issued_at_source": "EXPLICIT_TEST_CLOCK"
            if clock is not None
            else "SYSTEM_CLOCK_TEST_ONLY",
            "prospective_accuracy_validated": False,
            "production_use_approved": False,
            "business_acceptance_policy_id": None,
            "area_applicability": {},
        }
        area = Decimal(request["target_area_mu"])
        low, high = (
            Decimal(candidate_entry["training_area_min_mu"]),
            Decimal(candidate_entry["training_area_max_mu"]),
        )
        record["area_applicability"] = {
            "training_area_min_mu": str(low),
            "training_area_max_mu": str(high),
            "target_area_mu": str(area),
            "area_position": "INTERPOLATION" if low <= area <= high else "EXTRAPOLATION",
            "warnings": ["INTERPOLATION_IS_NOT_ACCURACY_VALIDATION"]
            if low <= area <= high
            else ["AREA_EXTRAPOLATION_NOT_VALIDATED"],
            "real_extrapolation_policy": "NOT_AUTHORIZED_REQUIRES_S2",
        }
        r2._cutoff(generated, record)
        path = r2._save(root, record, clock, forecast=True)
        return _read_record(root, "predictions", path.parent.name)


def _normalize_actual(payload: Record, forecast: Record, stamp: datetime) -> list[Record]:
    if payload["request_mode"] != "TEST_ONLY":
        raise ValueError("REAL_BUSINESS_ACTUAL_IMPORT_NOT_AUTHORIZED")
    if (
        payload["base_id"] != forecast["identity"]["base_id"]
        or payload["season"] != forecast["identity"]["target_season"]
        or payload["forecast_id"] != forecast["id"]
        or payload["unit"] != "kg"
    ):
        raise ValueError("ACTUAL_BASE_SEASON_FORECAST_UNIT_MISMATCH")
    if (
        not _aware(forecast["sealed_at"])
        <= _aware(payload["first_seen_at"])
        <= _aware(payload["recorded_at"])
        <= stamp
    ):
        raise ValueError("ACTUAL_TIME_ORDER_INVALID")
    rows = []
    dates = set()
    for row in payload["rows"]:
        if set(row) != {"business_date", "quantity_status", "new_quantity_kg"}:
            raise ValueError("ACTUAL_ROW_SCHEMA_INVALID")
        day = date.fromisoformat(row["business_date"])
        if (
            day.isoformat() in dates
            or not forecast["identity"]["window"][0]
            <= day.isoformat()
            <= forecast["identity"]["window"][1]
        ):
            raise ValueError("ACTUAL_DUPLICATE_OR_WINDOW_MISMATCH")
        if day > _aware(payload["first_seen_at"]).astimezone(legacy.TIMEZONE).date():
            raise ValueError("FUTURE_ACTUAL_OBSERVATION")
        status = row["quantity_status"]
        if status not in {"OBSERVED", "AUTHORIZED_ZERO", "MISSING"}:
            raise ValueError("ACTUAL_STATUS_INVALID")
        value = row["new_quantity_kg"]
        if status == "MISSING":
            if value is not None:
                raise ValueError("MISSING_IS_NOT_ZERO")
        else:
            value = r2.quantity(value)
            if status == "AUTHORIZED_ZERO" and Decimal(value) != 0:
                raise ValueError("AUTHORIZED_ZERO_NOT_ZERO")
        dates.add(day.isoformat())
        rows.append({"date": day.isoformat(), "quantity_status": status, "new_quantity_kg": value})
    return sorted(rows, key=lambda row: row["date"])


def import_actuals(
    root: Path, forecast_id: str, payload: Record, source_path: Path, *, clock: r2.Clock = None
) -> Record:
    required = {
        "actual_revision_id",
        "forecast_id",
        "base_id",
        "season",
        "unit",
        "request_mode",
        "rows",
        "source_id",
        "source_version",
        "source_hash",
        "normalization_version",
        "first_seen_at",
        "recorded_at",
        "parent_revision_id",
        "supersedes_revision_id",
        "revision_reason",
    }
    if set(payload) != required:
        raise ValueError("ACTUAL_SCHEMA_INVALID")
    for key in ("source_id", "source_version"):
        _id(payload[key])
    with r2.locked(root, exclusive=True):
        forecast = _read_record(root, "predictions", forecast_id)
        stamp = r2.now(clock)
        revision_id = _id(payload["actual_revision_id"])
        if (root / "actual-revisions" / revision_id).exists():
            raise ValueError("IMMUTABLE_ACTUAL_REVISION_ID_ALREADY_EXISTS")
        rows = _normalize_actual(payload, forecast, stamp)
        _content(source_path, payload["source_hash"], actual_source_payload(payload))
        if payload["normalization_version"] != "EXACT_MICROKG_JSON_E1":
            raise ValueError("ACTUAL_NORMALIZATION_VERSION_UNAVAILABLE")
        parent_id = payload["parent_revision_id"]
        if parent_id != payload["supersedes_revision_id"]:
            raise ValueError("REVISION_RELATION_MISMATCH")
        parent = _read_record(root, "actual-revisions", parent_id) if parent_id else None
        record = _base("actual-revisions", forecast, stamp)
        record.update(
            id=_id(payload["actual_revision_id"]),
            rows=rows,
            source=payload,
            source_hash=payload["source_hash"],
            canonical_payload_hash=digest(rows),
            first_seen_at=payload["first_seen_at"],
            recorded_at=payload["recorded_at"],
            parent_revision_id=parent_id,
            supersedes_revision_id=parent_id,
            revision_reason=payload["revision_reason"],
            parent_hash=parent["record_hash"] if parent else None,
        )
        if parent:
            if parent["prediction_seal_id"] != forecast_id or not record["revision_reason"]:
                raise ValueError("ACTUAL_REVISION_FORECAST_OR_REASON_MISMATCH")
            r2.relation(record, r2._published(root, parent), same_kind=False)
        for path in (root / "actual-revisions").glob("*/record.json"):
            prior = _read_record(root, "actual-revisions", path.parent.name)
            old = prior["source"]
            if old["source_id"] != payload["source_id"]:
                continue
            if prior["prediction_seal_id"] != forecast_id:
                raise ValueError("SOURCE_TARGET_CONFLICT")
            if (old["source_version"], old["normalization_version"]) == (
                payload["source_version"],
                payload["normalization_version"],
            ):
                if (
                    prior["canonical_payload_hash"] != digest(rows)
                    or old["source_hash"] != payload["source_hash"]
                ):
                    raise ValueError("SAME_SOURCE_VERSION_PAYLOAD_CONFLICT")
            elif (
                parent is None
                or not record["revision_reason"]
                or parent["source"]["source_id"] != payload["source_id"]
            ):
                raise ValueError("NEW_SOURCE_VERSION_REQUIRES_REVISION")
        r2.relation(record, r2._published(root, forecast), same_kind=False)
        path = r2._save(root, record, clock)
        return _read_record(root, "actual-revisions", path.parent.name)


def create_actual_snapshot(
    root: Path, forecast_id: str, revision_ids: list[str], *, clock: r2.Clock = None
) -> Record:
    if len(revision_ids) != 1:
        raise ValueError("ONE_REPLACEMENT_REVISION_PER_SNAPSHOT_REQUIRED_NO_IMPLICIT_MERGE")
    with r2.locked(root, exclusive=True):
        forecast = _read_record(root, "predictions", forecast_id)
        revision = _read_record(root, "actual-revisions", revision_ids[0])
        if revision["prediction_seal_id"] != forecast_id:
            raise ValueError("SNAPSHOT_FORECAST_MISMATCH")
        stamp = r2.now(clock)
        rows = revision["rows"]
        window = forecast["identity"]["window"]
        full = [r["date"] for r in rows] == [
            d.isoformat() for d in calendar(*(date.fromisoformat(d) for d in window))
        ]
        full = full and all(row["quantity_status"] != "MISSING" for row in rows)
        ended = stamp.astimezone(legacy.TIMEZONE).date() > date.fromisoformat(window[1])
        record = _base("snapshots", forecast, stamp)
        record.update(
            revision_ids=revision_ids,
            revision_hashes=[revision["record_hash"]],
            rows=rows,
            coverage_period=window,
            coverage_status="FINAL_SCORING_SNAPSHOT" if full and ended else "INTERIM_SNAPSHOT",
            canonical_payload_hash=digest(rows),
            created_at=stamp.isoformat(),
        )
        r2.relation(record, r2._published(root, revision), same_kind=False)
        path = r2._save(root, record, clock)
        return _read_record(root, "snapshots", path.parent.name)


def get_actual_snapshot(root: Path, identity: str) -> Record:
    return get_record(root, "snapshots", identity)


def _metrics(rows: list[Record], prediction: Record) -> Record:
    old_prediction = {
        "daily_curve": [
            {"date": r["date"], "predicted_quantity_kg": r["predicted_daily_quantity_kg"]}
            for r in prediction["daily_curve"]
        ]
    }
    result = legacy.score_curve(rows, old_prediction)
    values = [
        (Decimal(r["new_quantity_kg"]), Decimal(p["predicted_daily_quantity_kg"]))
        for r, p in zip(rows, prediction["daily_curve"], strict=True)
    ]
    smape = sum(
        (2 * abs(a - p) / (a + p) if a + p else Decimal(0) for a, p in values), Decimal(0)
    ) / len(values)
    result.update(
        season_total_absolute_error=result["total_absolute_error_kg"],
        season_total_relative_error=result["window_total_relative_error"],
        season_total_wape=result["window_total_wape"],
        daily_mae=result["daily_mae_kg"],
        daily_smape=fixed(smape),
        single_day_peak_quantity_absolute_error=result["single_day_peak_absolute_error_kg"],
        rolling_7day_peak_start_date_error_days=result["rolling_7day_window_shift_days"],
        rolling_7day_peak_quantity_absolute_error=result["rolling_7day_peak_absolute_error_kg"],
    )
    for name, field in (
        ("single_day_peak", "quantity_kg"),
        ("rolling_7day_peak", "cumulative_quantity_kg"),
    ):
        a, p = Decimal(result["actual"][name][field]), Decimal(result["predicted"][name][field])
        result[name + "_quantity_relative_error"] = fixed(abs(a - p) / a) if a else None
    return result


def evaluate_locked_forecast(
    root: Path,
    forecast_id: str,
    snapshot_id: str,
    metric_contract: str,
    *,
    expected_identity: Record | None = None,
    clock: r2.Clock = None,
) -> Record:
    with r2.locked(root, exclusive=True):
        forecast = _read_record(root, "predictions", forecast_id)
        snapshot = _read_record(root, "snapshots", snapshot_id)
        if (
            metric_contract != forecast["metric_binding"]["version"]
            or forecast["metric_binding"] != binding()
        ):
            raise ValueError("SEALED_METRIC_CONTRACT_MISMATCH")
        identities = {
            "candidate_artifact_hash": forecast["artifact_entries"]["candidate"]["artifact_hash"],
            "comparator_hash": forecast["artifact_entries"]["comparator"]["artifact_hash"],
        }
        if expected_identity is not None and any(
            identities.get(k) != v for k, v in expected_identity.items()
        ):
            raise ValueError("EVALUATION_IDENTITY_SWITCH_REJECTED")
        if snapshot["prediction_seal_id"] != forecast_id:
            raise ValueError("ACTUAL_SNAPSHOT_FORECAST_MISMATCH")
        stamp = r2.now(clock)
        if stamp.astimezone(legacy.TIMEZONE).date() <= date.fromisoformat(
            forecast["identity"]["window"][1]
        ):
            raise ValueError("FULL_WINDOW_NOT_ENDED")
        if snapshot["coverage_status"] != "FINAL_SCORING_SNAPSHOT":
            raise ValueError("FULL_ACTUAL_COVERAGE_REQUIRED_NO_IMPUTATION")
        record = _base("evaluations", forecast, stamp)
        r2.relation(record, r2._published(root, snapshot), same_kind=False)
        metrics = {
            name: _metrics(snapshot["rows"], forecast["prediction"][name])
            for name in ("candidate", "comparator")
        }
        keys = [
            "season_total_absolute_error",
            "season_total_wape",
            "daily_mae",
            "daily_wape",
            "daily_smape",
            "single_day_peak_date_error_days",
            "single_day_peak_quantity_absolute_error",
            "rolling_7day_peak_start_date_error_days",
            "rolling_7day_peak_quantity_absolute_error",
        ]
        metrics["candidate_minus_comparator"] = {
            k: fixed(Decimal(str(metrics["candidate"][k])) - Decimal(str(metrics["comparator"][k])))
            if metrics["candidate"][k] is not None and metrics["comparator"][k] is not None
            else None
            for k in keys
        }
        record.update(
            actual_snapshot_id=snapshot_id,
            actual_snapshot_hash=snapshot["record_hash"],
            metric_binding=forecast["metric_binding"],
            artifact_identity=identities,
            metrics=metrics,
            metrics_hash=digest(metrics),
            stable_gain_decision="NOT_EXECUTED",
            allowed_future_decisions=[
                "IMPROVED",
                "NO_CLEAR_WINNER",
                "REGRESSED",
                "INSUFFICIENT_EVIDENCE",
            ],
            business_acceptance_policy_id=None,
            business_accuracy_threshold_status="NOT_ESTABLISHED",
            prospective_accuracy_validated=False,
            production_use_approved=False,
        )
        path = r2._save(root, record, clock)
        return _read_record(root, "evaluations", path.parent.name)
