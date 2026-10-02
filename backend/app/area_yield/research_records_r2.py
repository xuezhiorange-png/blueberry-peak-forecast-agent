"""R2 file protocol: locked metrics, verified lineage and atomic TEST_ONLY records.

R1 functions remain historical replay utilities, not R2 issuance authorities.
Local operator records and hashes are not external trusted timestamps/signatures.
"""

from __future__ import annotations

import fcntl
import inspect
import json
import os
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.app.area_yield import m0_baseline
from backend.app.area_yield import research_records as legacy
from backend.app.area_yield.base_product import AreaForecastProductRequest
from backend.app.area_yield.data import calendar, digest
from backend.app.area_yield.evaluation import summaries

Record = dict[str, Any]
read = legacy.read
file_hash = legacy.file_hash
SCHEMA = "V0_11_RESEARCH_FILE_RECORD_R2"
CONTRACT = "V0_11_M0_FULL_WINDOW_LOCKED_METRICS_R2"
DEFAULT_CONTRACT = CONTRACT
SPEC: Record = {
    "version": CONTRACT,
    "quantity_precision_kg": "0.000001",
    "quantity_rule": "EXACT_MICROKG_STRING_NO_ROUNDING",
    "coverage": "FULL_CONTIGUOUS_NO_MISSING",
    "peak": "EARLIEST_CANONICAL_TIE_COMPLETE_7_CALENDAR_DAYS",
    "metrics": "R1_CANONICAL_POINT_METRICS_UNCHANGED_ON_MICROKG_INPUTS",
    "window": "FROZEN_BUSINESS_WINDOW_TOTAL_KG",
}


def implementation_identity() -> str:
    """Bind actual metric code/dependencies, not the CLI's default version string."""
    from backend.app.area_yield import data as quantities
    from backend.app.area_yield import evaluation
    from backend.app.core_forecast import canonical, metrics, schemas
    from backend.app.harvest_state import canonical as harvest_canonical
    from backend.app.rolling_backtest import canonical as rolling_canonical

    return digest(
        {
            "score_curve": inspect.getsource(legacy.score_curve),
            "mass_date": inspect.getsource(legacy._mass_date),
            "evaluation": file_hash(Path(evaluation.__file__)),
            "peak_metrics": file_hash(Path(metrics.__file__)),
            "quantity_contract": file_hash(Path(quantities.__file__)),
            "metric_schemas": file_hash(Path(schemas.__file__)),
            "core_canonical": file_hash(Path(canonical.__file__)),
            "rolling_canonical": file_hash(Path(rolling_canonical.__file__)),
            "harvest_canonical": file_hash(Path(harvest_canonical.__file__)),
        }
    )


def metric_binding() -> Record:
    return {
        "version": CONTRACT,
        "specification_hash": digest(SPEC),
        "implementation_hash": implementation_identity(),
        "rule_version": "CANONICAL_R1_METRICS_WITH_R2_EXACT_MICROKG_INPUT",
    }


def require_contract(binding: Record, requested: str) -> None:
    if binding != metric_binding() or requested != binding["version"]:
        raise ValueError("SEALED_METRIC_SPEC_OR_IMPLEMENTATION_MISMATCH")


def sha256(value: Any) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-fA-F]{64}", value) is None:
        raise ValueError("SHA256_HEXADECIMAL_REQUIRED")
    return value.lower()


def quantity(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("QUANTITY_DECIMAL_STRING_REQUIRED")
    try:
        number = Decimal(value)
        if (
            not number.is_finite()
            or number < 0
            or number * 1000000 != (number * 1000000).to_integral_value()
        ):
            raise ValueError("EXACT_NONNEGATIVE_MICROKG_REQUIRED")
        return format(number.quantize(Decimal("0.000001")), "f")
    except InvalidOperation as exc:
        raise ValueError("EXACT_NONNEGATIVE_MICROKG_REQUIRED") from exc


def normalize_rows(rows: list[Record]) -> list[Record]:
    result = []
    for row in rows:
        if set(row) != {"date", "status", "new_quantity_kg"}:
            raise ValueError("ACTUAL_ROW_SCHEMA_INVALID")
        if row["status"] not in {"OBSERVED", "CONFIRMED_ZERO", "MISSING"}:
            raise ValueError("ACTUAL_COVERAGE_STATUS_INVALID")
        value = row["new_quantity_kg"]
        if row["status"] == "MISSING":
            if value is not None:
                raise ValueError("MISSING_IS_NOT_ZERO")
        else:
            value = quantity(value)
            if row["status"] == "CONFIRMED_ZERO" and Decimal(value) != 0:
                raise ValueError("CONFIRMED_ZERO_NOT_ZERO")
        result.append({**row, "new_quantity_kg": value})
    return sorted(result, key=lambda row: row["date"])


class TestClock:
    """Explicit controlled clock; never establishes a prospective issuance."""

    def __init__(self, clock: Callable[[], datetime]):
        self.clock = clock

    def now(self) -> datetime:
        return legacy._now(self.clock())


Clock = datetime | TestClock | None


def now(clock: Clock) -> datetime:
    return clock.now() if isinstance(clock, TestClock) else legacy._now(clock)


@contextmanager
def locked(root: Path, *, exclusive: bool) -> Iterator[None]:
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".record-lock").open("a+") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def _write(path: Path, payload: Record) -> None:
    with path.open("x") as stream:
        json.dump(payload, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _cutoff(stamp: datetime, payload: Record) -> None:
    start = date.fromisoformat(payload["identity"]["window"][0])
    if stamp >= datetime.combine(start, time.min, legacy.TIMEZONE):
        raise ValueError("COMPLETION_CROSSED_PRESEASON_CUTOFF_NOT_ISSUED")


def _save(root: Path, payload: Record, clock: Clock, *, forecast: bool = False) -> Path:
    """Caller holds exclusive lock. Readers hold shared lock until post-publish check.

    Private durable stage -> completion time -> final durable record -> atomic rename
    -> post-publication cutoff check. Failed/new-only writes are quarantined, never
    visible as valid records to cooperating readers. Old records are never changed.
    """
    identity = str(payload["id"])
    stage = root / ".staging" / identity
    stage.mkdir(parents=True, exist_ok=False)
    destination = root / str(payload["kind"]) / identity
    try:
        _write(stage / "not-final.json", {"status": "PUBLICATION_NOT_FINAL"})
        _write(stage / "pending.json", payload)
        stamp = now(clock)
        if stamp < datetime.fromisoformat(payload["occurred_at"]):
            raise ValueError("TIME_REVERSAL_REJECTED")
        if forecast:
            _cutoff(stamp, payload)
            payload.update(sealed_at=stamp.isoformat(), issued_at=stamp.isoformat())
        payload["committed_at"] = stamp.isoformat()
        sealed = legacy._seal(payload)
        _write(stage / "record.json", sealed)
        destination.parent.mkdir(parents=True, exist_ok=True)
        stage.rename(destination)
        descriptor = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        completed = now(clock)
        if completed < stamp:
            raise ValueError("TIME_REVERSAL_REJECTED")
        if forecast:
            _cutoff(completed, payload)
        # A crash after rename but before this marker must not make a valid seal.
        _write(
            destination / "completion.json",
            legacy._seal(
                {
                    "sealed_record_hash": sealed["record_hash"],
                    "completed_at": completed.isoformat(),
                    "status": "COMPLETED",
                }
            ),
        )
        final = now(clock)
        if final < completed:
            raise ValueError("TIME_REVERSAL_REJECTED")
        if forecast:
            _cutoff(final, payload)
        (destination / "not-final.json").unlink()
        return destination / "record.json"
    except BaseException:
        abandoned = destination if destination.exists() else stage
        aborted = root / "ABORTED_NOT_ISSUED" / identity
        aborted.parent.mkdir(parents=True, exist_ok=True)
        if abandoned.exists():
            abandoned.rename(aborted)
        raise


def _load(root: Path, kind: str, identity: str, seen: set[str] | None = None) -> Record:
    record = legacy._load(root, kind, identity)
    if record.get("schema") != SCHEMA:
        raise ValueError("LEGACY_RECORD_REQUIRES_EXPLICIT_HISTORICAL_REPLAY")
    seen = set() if seen is None else seen.copy()
    if identity in seen:
        raise ValueError("LINEAGE_CYCLE_REJECTED")
    seen.add(identity)
    if record["test_only"] is not True:
        raise ValueError("REAL_ISSUANCE_NOT_AUTHORIZED_IN_R2_TASK")
    if record["prospective_class"] != "TEST_NOT_PROSPECTIVE":
        raise ValueError("TEST_REAL_TAINT_MISMATCH")
    event = datetime.fromisoformat(record["occurred_at"])
    if datetime.fromisoformat(record["committed_at"]) < event:
        raise ValueError("TIME_REVERSAL_REJECTED")
    if kind == "predictions":
        stamps = [
            datetime.fromisoformat(record[key])
            for key in ("started_at", "prediction_generated_at", "sealed_at")
        ]
        if stamps != sorted(stamps) or record["issued_at"] != record["sealed_at"]:
            raise ValueError("FORECAST_TIME_ORDER_INVALID")
        _cutoff(stamps[-1], record)
        require_contract(record["metric_binding"], record["metric_contract_version"])
    _completion(root, record)
    if kind != "predictions":
        seal = _load(root, "predictions", record["prediction_seal_id"], seen)
        if seal["record_hash"] != record["prediction_seal_hash"]:
            raise ValueError("PREDICTION_HASH_LINEAGE_MISMATCH")
        relation(record, _published(root, seal), same_kind=False)
        if kind == "evaluations":
            actual = _load(root, "actuals", record["actual_snapshot_id"], seen)
            if actual["record_hash"] != record["actual_snapshot_hash"]:
                raise ValueError("ACTUAL_HASH_LINEAGE_MISMATCH")
            relation(record, _published(root, actual), same_kind=False)
            require_contract(record["metric_binding"], record["metric_contract_version"])
    parent_id = record.get("parent_id")
    if parent_id:
        parent = _load(root, kind, parent_id, seen)
        if record["parent_hash"] != parent["record_hash"]:
            raise ValueError("PARENT_HASH_MISMATCH")
        if record["parent_completion_hash"] != file_hash(
            root / kind / parent_id / "completion.json"
        ):
            raise ValueError("PARENT_COMPLETION_HASH_MISMATCH")
        relation(record, _published(root, parent))
    return record


def _completion(root: Path, record: Record) -> Record:
    if (root / str(record["kind"]) / str(record["id"]) / "not-final.json").exists():
        raise ValueError("PUBLICATION_COMPLETION_MARKER_NOT_FINAL_NOT_ISSUED")
    path = root / str(record["kind"]) / str(record["id"]) / "completion.json"
    if not path.is_file():
        raise ValueError("PUBLICATION_COMPLETION_MARKER_REQUIRED_NOT_ISSUED")
    completion = read(path)
    legacy.verify(completion)
    if (
        completion.get("sealed_record_hash") != record["record_hash"]
        or completion.get("status") != "COMPLETED"
    ):
        raise ValueError("PUBLICATION_COMPLETION_IDENTITY_MISMATCH")
    stamp = datetime.fromisoformat(completion["completed_at"])
    if stamp < datetime.fromisoformat(record["committed_at"]):
        raise ValueError("TIME_REVERSAL_REJECTED")
    if record["kind"] == "predictions":
        _cutoff(stamp, record)
    return completion


def _published(root: Path, record: Record) -> Record:
    return {**record, "committed_at": _completion(root, record)["completed_at"]}


def relation(child: Record, parent: Record, *, same_kind: bool = True) -> None:
    if same_kind and child["kind"] != parent["kind"]:
        raise ValueError("PARENT_RECORD_TYPE_MISMATCH")
    if child["identity"] != parent["identity"]:
        raise ValueError("BASE_SEASON_WINDOW_TARGET_LINEAGE_MISMATCH")
    if (
        child["test_only"] != parent["test_only"]
        or child["prospective_class"] != parent["prospective_class"]
    ):
        raise ValueError("TEST_REAL_LINEAGE_MISMATCH")
    if datetime.fromisoformat(child["occurred_at"]) < datetime.fromisoformat(
        parent["committed_at"]
    ):
        raise ValueError("TIME_REVERSAL_REJECTED")
    if same_kind:
        if not child.get("revision_reason"):
            raise ValueError("REVISION_REASON_REQUIRED")
        if (
            child["kind"] != "predictions"
            and child["prediction_seal_id"] != parent["prediction_seal_id"]
        ):
            raise ValueError("REVISION_PREDICTION_SEAL_MISMATCH")
        if (
            child["kind"] == "evaluations"
            and child["actual_snapshot_id"] != parent["actual_snapshot_id"]
        ):
            if child.get("actual_supersedes") != parent["actual_snapshot_id"]:
                raise ValueError("EVALUATION_ACTUAL_REVISION_MISMATCH")


def source_identity(source: Record, canonical: Any, *, authorization: bool = False) -> Record:
    required = {
        "source_id",
        "source_version",
        "raw_source_hash",
        "canonical_payload_hash",
        "normalization_version",
        "raw_source_path",
    }
    if set(source) != required or any(
        not source[key] for key in ("source_id", "source_version", "normalization_version")
    ):
        raise ValueError("SOURCE_IDENTITY_SCHEMA_INVALID")
    result = dict(source)
    for key in ("raw_source_hash", "canonical_payload_hash"):
        result[key] = sha256(source[key])
    if result["canonical_payload_hash"] != digest(canonical):
        raise ValueError("CANONICAL_PAYLOAD_HASH_MISMATCH")
    path = source["raw_source_path"]
    result["verification"] = "DECLARED_NOT_CONTENT_VERIFIED"
    if path is not None:
        raw = Path(path)
        if file_hash(raw) != result["raw_source_hash"]:
            raise ValueError("RAW_SOURCE_CONTENT_HASH_MISMATCH")
        content = json.loads(raw.read_text())
        if authorization:
            if content != canonical:
                raise ValueError("LOCAL_AUTHORIZATION_CONTENT_MISMATCH")
        elif (
            source["normalization_version"] != "IDENTITY_JSON_MICROKG_R2"
            or normalize_rows(content) != canonical
        ):
            raise ValueError("SOURCE_NORMALIZATION_CONTENT_MISMATCH")
        result["verification"] = "CONTENT_HASH_AND_DECLARED_TRANSFORM_VERIFIED"
    if authorization and (
        path is None or source["normalization_version"] != "EXACT_REQUEST_AUTH_R2"
    ):
        raise ValueError("VERIFIABLE_LOCAL_AUTHORIZATION_REQUIRED")
    return result


def _base(kind: str, seal: Record, stamp: datetime) -> Record:
    return {
        "id": str(uuid4()),
        "kind": kind,
        "schema": SCHEMA,
        "identity": seal["identity"],
        "test_only": seal["test_only"],
        "prospective_class": seal["prospective_class"],
        "occurred_at": stamp.isoformat(),
        "prediction_seal_id": seal["id"],
        "prediction_seal_hash": seal["record_hash"],
        "parent_id": None,
    }


def _parent(root: Path, record: Record, parent_id: str | None) -> None:
    if parent_id:
        prior = _load(root, record["kind"], parent_id)
        relation(record, _published(root, prior))
        record.update(
            parent_id=parent_id,
            parent_hash=prior["record_hash"],
            parent_completion_hash=file_hash(root / record["kind"] / parent_id / "completion.json"),
        )


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
    test_clock: Clock = None,
) -> Path:
    if test_clock is None:
        raise ValueError("REAL_RESEARCH_ISSUANCE_NOT_AUTHORIZED")
    request = AreaForecastProductRequest.model_validate(request_payload)
    if request.base_id is None:
        raise ValueError("ANONYMOUS_STABLE_BASE_ID_REQUIRED")
    model, entry = legacy._registered_model(
        registry_path, sha256(registry_sha256), model_path, model_id
    )
    started = now(test_clock)
    year = int(request.target_season[:4])
    support = [date(year, 7, 1), date(year + 1, 4, 15)]
    if [request.forecast_start_date, request.forecast_end_date] != support or entry[
        "supported_request_window"
    ] != "JULY_01_THROUGH_APRIL_15_INCLUSIVE":
        raise ValueError("FULL_TOTAL_CANNOT_BE_REASSIGNED_TO_SUBWINDOW")
    if started.date() <= date.fromisoformat(model["training_cutoff"]):
        raise ValueError("TRAINING_CUTOFF_AFTER_ISSUANCE")
    snapshot = request.model_dump(mode="json")
    local = authorization["local_record"]
    if set(authorization) != {"local_record", "source"} or set(local) != {
        "status",
        "operator",
        "request_snapshot_hash",
        "target_actuals_used",
        "revision_reason",
    }:
        raise ValueError("EXACT_REQUEST_AUTHORITY_REQUIRED")
    if (
        local["status"] != "TEST_ONLY"
        or not local["operator"]
        or local["request_snapshot_hash"] != digest(snapshot)
        or local["target_actuals_used"] is not False
    ):
        raise ValueError("EXACT_REQUEST_AUTHORITY_REQUIRED")
    authority = source_identity(authorization["source"], local, authorization=True)
    payload: Record = {
        "id": str(uuid4()),
        "kind": "predictions",
        "schema": SCHEMA,
        "identity": {
            "base_id": request.base_id,
            "target_season": request.target_season,
            "window": [d.isoformat() for d in support],
            "target_definition": "FROZEN_BUSINESS_WINDOW_TOTAL_KG",
            "unit": "kg",
        },
        "test_only": True,
        "prospective_class": "TEST_NOT_PROSPECTIVE",
        "started_at": started.isoformat(),
        "occurred_at": started.isoformat(),
        "parent_id": None,
        "revision_reason": local["revision_reason"],
        "model_id": model_id,
        "model_family": m0_baseline.MODEL_FAMILY,
        "model_artifact_hash": model["artifact_hash"],
        "model_file_sha256": file_hash(model_path),
        "registry_sha256": registry_sha256,
        "training_manifest_hash": model["training_manifest_sha256"],
        "training_cutoff": model["training_cutoff"],
        "request_snapshot": snapshot,
        "request_snapshot_hash": digest(snapshot),
        "model_support_window": [d.isoformat() for d in support],
        "requested_target_window": [d.isoformat() for d in support],
        "target_definition": "FROZEN_BUSINESS_WINDOW_TOTAL_KG",
        "input_sources_and_versions": authority,
        "request_authorization": local,
        "metric_contract_version": CONTRACT,
        "metric_binding": metric_binding(),
        "issued_at_source": "EXPLICIT_TEST_CLOCK",
        "business_timezone": "Asia/Shanghai",
        "research_role": "REFERENCE_BASELINE",
        "known_limitations": [
            "LOCAL_HASH_NOT_EXTERNAL_TRUSTED_TIMESTAMP",
            "LOCAL_OPERATOR_NOT_INDEPENDENT_BUSINESS_VERIFICATION",
            "LEGACY_RUNNER_AND_WORKBOOK_LIMITATIONS_REMAIN",
            "OLD_6_INNER_1_OUTER_NUMERICAL_GAPS_REMAIN",
        ],
    }
    _cutoff(started, payload)
    with locked(root, exclusive=True):
        _parent(root, payload, parent_id)
        prediction = m0_baseline.predict(model, request)
        metrics = summaries(
            [date.fromisoformat(r["date"]) for r in prediction["daily_curve"]],
            [Decimal(quantity(r["predicted_quantity_kg"])) for r in prediction["daily_curve"]],
        )
        generated = now(test_clock)
        if generated < started:
            raise ValueError("TIME_REVERSAL_REJECTED")
        _cutoff(generated, payload)
        payload.update(
            prediction_generated_at=generated.isoformat(),
            occurred_at=generated.isoformat(),
            prediction=prediction,
            daily_prediction_hash=digest(prediction["daily_curve"]),
            metrics=metrics,
            metrics_hash=digest(metrics),
        )
        return _save(root, payload, test_clock, forecast=True)


def load_prediction(root: Path, seal_id: str, model_path: Path) -> Record:
    with locked(root, exclusive=False):
        record = _load(root, "predictions", seal_id)
        model = m0_baseline.load_model(model_path)
        if (
            file_hash(model_path) != record["model_file_sha256"]
            or model["artifact_hash"] != record["model_artifact_hash"]
            or digest(record["request_snapshot"]) != record["request_snapshot_hash"]
            or digest(record["prediction"]["daily_curve"]) != record["daily_prediction_hash"]
            or digest(record["metrics"]) != record["metrics_hash"]
        ):
            raise ValueError("SEALED_COMPONENT_MISMATCH")
        return record


def import_actuals(root: Path, seal_id: str, source: Record, *, test_clock: Clock = None) -> Path:
    with locked(root, exclusive=True):
        seal = _load(root, "predictions", seal_id)
        if test_clock is None:
            raise ValueError("TEST_REAL_MODE_MISMATCH")
        if set(source) != {
            "base_id",
            "target_season",
            "unit",
            "rows",
            "source_identity",
            "supersedes",
            "revision_reason",
        }:
            raise ValueError("ACTUAL_SOURCE_SCHEMA_INVALID")
        if any(
            source[key] != seal["identity"][key] for key in ("base_id", "target_season", "unit")
        ):
            raise ValueError("ACTUAL_BASE_SEASON_UNIT_MISMATCH")
        stamp = now(test_clock)
        rows = normalize_rows(source["rows"])
        seen: set[str] = set()
        for row in rows:
            day = date.fromisoformat(row["date"])
            if (
                row["date"] in seen
                or not seal["identity"]["window"][0] <= row["date"] <= seal["identity"]["window"][1]
            ):
                raise ValueError("ACTUAL_DUPLICATE_OR_WINDOW_MISMATCH")
            if day > stamp.astimezone(legacy.TIMEZONE).date():
                raise ValueError("FUTURE_ACTUAL_OBSERVATION_REJECTED")
            seen.add(row["date"])
        origin = source_identity(source["source_identity"], rows)
        record = _base("actuals", seal, stamp)
        record.update(
            source={**source, "rows": rows},
            source_identity=origin,
            revision_reason=source["revision_reason"],
            first_ingested_at=stamp.isoformat(),
            quantity_field="new_quantity_kg",
            label_assumption="ARRIVAL_EQUALS_HARVEST_EQUALS_MATURITY_PROXY",
        )
        relation(record, _published(root, seal), same_kind=False)
        _parent(root, record, source["supersedes"])
        known_version = False
        known_source = False
        duplicate: Path | None = None
        for path in sorted((root / "actuals").glob("*/record.json")):
            prior = _load(root, "actuals", path.parent.name)
            old = prior["source_identity"]
            if old["source_id"] != origin["source_id"]:
                continue
            known_source = True
            if prior["identity"] != record["identity"]:
                raise ValueError("SOURCE_IDENTITY_TARGET_CONFLICT")
            same_version = (old["source_version"], old["normalization_version"]) == (
                origin["source_version"],
                origin["normalization_version"],
            )
            if same_version:
                known_version = True
                if (
                    old["raw_source_hash"] != origin["raw_source_hash"]
                    or old["canonical_payload_hash"] != origin["canonical_payload_hash"]
                ):
                    raise ValueError("SAME_SOURCE_VERSION_PAYLOAD_CONFLICT")
                if prior["prediction_seal_id"] == seal_id and not source["supersedes"]:
                    duplicate = path
        if known_source and not known_version:
            if not source["supersedes"] or not source["revision_reason"]:
                raise ValueError("SOURCE_VERSION_CHANGE_REQUIRES_REVISION")
            prior = _load(root, "actuals", source["supersedes"])
            if prior["source_identity"]["source_id"] != origin["source_id"]:
                raise ValueError("SOURCE_REVISION_IDENTITY_MISMATCH")
        if duplicate is not None:
            return duplicate
        return _save(root, record, test_clock)


def evaluate(
    root: Path,
    seal_id: str,
    actual_id: str,
    metric_contract_version: str,
    model_path: Path,
    *,
    test_clock: Clock = None,
    parent_id: str | None = None,
    revision_reason: str | None = None,
) -> Path:
    # Verify model outside write lock to avoid recursive flock deadlocks.
    load_prediction(root, seal_id, model_path)
    with locked(root, exclusive=True):
        seal = _load(root, "predictions", seal_id)
        actual = _load(root, "actuals", actual_id)
        require_contract(seal["metric_binding"], metric_contract_version)
        if test_clock is None:
            raise ValueError("TEST_REAL_MODE_MISMATCH")
        stamp = now(test_clock)
        record = _base("evaluations", seal, stamp)
        relation(record, _published(root, actual), same_kind=False)
        if actual["prediction_seal_id"] != seal_id:
            raise ValueError("ACTUAL_PREDICTION_IDENTITY_MISMATCH")
        start, end = [date.fromisoformat(day) for day in seal["identity"]["window"]]
        if stamp.astimezone(legacy.TIMEZONE).date() <= end:
            raise ValueError("FULL_WINDOW_NOT_ENDED")
        rows = actual["source"]["rows"]
        if [r["date"] for r in rows] != [d.isoformat() for d in calendar(start, end)] or any(
            r["status"] == "MISSING" for r in rows
        ):
            raise ValueError("FULL_ACTUAL_COVERAGE_REQUIRED_NO_IMPUTATION")
        record.update(
            actual_snapshot_id=actual_id,
            actual_snapshot_hash=actual["record_hash"],
            actual_supersedes=actual["parent_id"],
            metric_contract_version=metric_contract_version,
            metric_binding=seal["metric_binding"],
            evaluated_at=stamp.isoformat(),
            revision_reason=revision_reason,
            prospective_accuracy_validated=False,
        )
        _parent(root, record, parent_id)
        metrics = legacy.score_curve(rows, seal["prediction"])
        record.update(metrics=metrics, metrics_hash=digest(metrics))
        return _save(root, record, test_clock)


def replay_legacy(root: Path, seal_id: str, actual_id: str, model_path: Path) -> Record:
    """Read-only R1 historical metrics, no new issuance/evaluation and no R2 claim."""
    seal = legacy.load_prediction(root, seal_id, model_path)
    actual = legacy._load(root, "actuals", actual_id)
    if (
        seal.get("schema") != "V0_11_RESEARCH_FILE_RECORD_R1"
        or seal["metric_contract_version"] != "V0_11_M0_FULL_WINDOW_LOCKED_METRICS_R1"
        or actual["prediction_seal_id"] != seal_id
        or actual["prediction_seal_hash"] != seal["record_hash"]
    ):
        raise ValueError("LEGACY_IDENTITY_OR_CONTRACT_MISMATCH")
    rows = sorted(actual["source"]["rows"], key=lambda r: r["date"])
    start, end = [date.fromisoformat(day) for day in seal["requested_target_window"]]
    if [r["date"] for r in rows] != [d.isoformat() for d in calendar(start, end)] or any(
        r["status"] == "MISSING" for r in rows
    ):
        raise ValueError("LEGACY_FULL_COVERAGE_REQUIRED")
    return {
        "scope": "R1_HISTORICAL_METRIC_REPLAY_NOT_R2_ISSUANCE",
        "missing_r2_evidence": [
            "SPEC_AND_IMPLEMENTATION_BINDING",
            "COMPLETION_TIMESTAMP",
            "VERIFIED_SOURCE_AND_CHAIN",
        ],
        "metrics": legacy.score_curve(rows, seal["prediction"]),
    }
