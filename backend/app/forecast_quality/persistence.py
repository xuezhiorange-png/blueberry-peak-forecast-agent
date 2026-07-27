"""Caller-owned persistence for the V0.2-S3 Round B evidence set."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.forecast_quality.canonical import canonical_json_bytes
from backend.app.forecast_quality.enums import MetricStatus, ReasonCode
from backend.app.forecast_quality.schemas import (
    BaselineRequest,
    BaselineResult,
    BaselineSourceSnapshot,
    DailyMetricResult,
    S3EvaluationInput,
)
from backend.app.models.forecast_quality import (
    PERSISTENCE_SCHEMA_VERSION,
    ModelBaselineComparisonModel,
    NaiveBaselineRunModel,
    QualityBreakdownResultModel,
    QualityEvaluationManifestModel,
    QualityEvaluationRunModel,
    QualityMetricResultModel,
)

COMPARISON_RESULT_SET_PAYLOAD = {
    "records": [],
    "schema_version": "v0.2-s3-comparison-result-set-v1",
}
COMPARISON_RESULT_SET_HASH = hashlib.sha256(
    canonical_json_bytes(COMPARISON_RESULT_SET_PAYLOAD)
).hexdigest()

_EXPECTED_METRIC_NAMES = frozenset(
    {
        "daily_mae",
        "daily_wape",
        "daily_smape",
        "daily_mape",
        "daily_bias_kg",
        "daily_relative_bias",
        "daily_absolute_error_sum_kg",
    }
)

_COVERAGE_QUANTUM = Decimal("0.000001")


class ForecastQualityPersistenceError(RuntimeError):
    """Base error for fail-closed Round B persistence failures."""


class ForecastQualityContractError(ForecastQualityPersistenceError):
    """Input or canonical contract validation failed before a write."""


class ForecastQualityConflictError(ForecastQualityPersistenceError):
    """A semantic identity already exists with different evidence."""


class ForecastQualityPartialResultError(ForecastQualityPersistenceError):
    """An existing result is incomplete or internally inconsistent."""


@dataclass(frozen=True)
class BaselinePersistenceRecord:
    request: BaselineRequest
    snapshot: BaselineSourceSnapshot
    result: BaselineResult


@dataclass(frozen=True)
class PersistedQualityEvaluation:
    run_id: int
    manifest_id: int
    evaluation_request_hash: str
    evaluation_instance_hash: str
    new_write_count: int
    replayed: bool


@dataclass(frozen=True)
class _MetricEvidence:
    key_hash: str
    canonical_hash: str
    payload: dict[str, Any]
    breakdown_identity: dict[str, Any]
    metric_name: str
    metric_status: str
    reason_code: str
    metric_value: Any
    numerator: Any
    denominator: Any


@dataclass(frozen=True)
class _BreakdownEvidence:
    key_hash: str
    canonical_hash: str
    payload: dict[str, Any]
    identity: dict[str, Any]
    metric_status: str
    reason_code: str
    comparable_count: int
    excluded_count: int
    not_computable_count: int
    coverage_ratio: Decimal | None
    metric_values: dict[str, Any]


@dataclass(frozen=True)
class _BaselineEvidence:
    request_hash: str
    result_hash: str
    canonical_hash: str
    payload: dict[str, Any]
    source_identity: str
    source_hash: str
    source_row_set_hash: str
    visibility_manifest_hash: str
    baseline_policy_version: str
    metric_status: str
    reason_code: str


@dataclass(frozen=True)
class _EvidenceSet:
    evaluation_request_hash: str
    run_payload: dict[str, Any]
    run_hash: str
    metrics: tuple[_MetricEvidence, ...]
    breakdowns: tuple[_BreakdownEvidence, ...]
    baselines: tuple[_BaselineEvidence, ...]
    metric_set_hash: str
    breakdown_set_hash: str
    baseline_set_hash: str
    evaluation_instance_hash: str
    manifest_payload: dict[str, Any]
    manifest_hash: str


def _hash(payload: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _json_ready(payload: Any) -> dict[str, Any]:
    value = json.loads(canonical_json_bytes(payload).decode("utf-8"))
    if not isinstance(value, dict):
        raise ForecastQualityContractError("canonical payload must be an object")
    return value


def _nonempty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ForecastQualityContractError(f"{field} must be a non-empty string")
    return value


def _require_hash(value: Any, field: str) -> str:
    validated = _nonempty(value, field)
    if (
        len(validated) != 64
        or validated.lower() != validated
        or any(char not in "0123456789abcdef" for char in validated)
    ):
        raise ForecastQualityContractError(f"{field} must be lowercase SHA-256")
    return validated


def _hash_set(values: Sequence[str]) -> str:
    return _hash({"hashes": sorted(values)})


def _object_hash_with_blank_canonical_hash(value: Any) -> str:
    payload = dataclasses.asdict(value)
    payload["canonical_hash"] = ""
    return _hash(payload)


def _validate_evaluation_input(value: S3EvaluationInput) -> tuple[dict[str, Any], str, str]:
    for field in (
        "s2_run_identity",
        "s2_manifest_identity",
        "s2_binding_row_set_hash",
    ):
        _nonempty(getattr(value, field), field)
    for field in ("metric_policy_version", "baseline_policy_version"):
        _nonempty(getattr(value, field).value, field)
    request_payload = {
        "schema_version": PERSISTENCE_SCHEMA_VERSION,
        "s2_run_identity": value.s2_run_identity,
        "s2_manifest_identity": value.s2_manifest_identity,
        "s2_binding_row_set_hash": value.s2_binding_row_set_hash,
        "metric_policy_version": value.metric_policy_version,
        "baseline_policy_version": value.baseline_policy_version,
    }
    return request_payload, _hash(request_payload), _hash(request_payload)


def _metric_evidence(result: DailyMetricResult) -> tuple[_MetricEvidence, ...]:
    expected_hash = _object_hash_with_blank_canonical_hash(result)
    actual_hash = _require_hash(result.canonical_hash, "metric_result.canonical_hash")
    if actual_hash != expected_hash:
        raise ForecastQualityContractError("DailyMetricResult canonical hash replay failed")
    result_payload = dataclasses.asdict(result)
    result_payload = _json_ready(result_payload)
    breakdown_identity = _json_ready(result.breakdown_identity)
    evidence: list[_MetricEvidence] = []
    for cell in result.metric_cells:
        cell_payload = _json_ready(dataclasses.asdict(cell))
        key_payload = {
            "s2_binding_row_set_hash": result.s2_binding_row_set_hash,
            "metric_input_quantile": result.metric_input_quantile,
            "breakdown_identity": breakdown_identity,
            "metric_name": cell.metric_name,
        }
        key_hash = _hash(key_payload)
        canonical_payload = {
            "schema_version": PERSISTENCE_SCHEMA_VERSION,
            "daily_metric_result": result_payload,
            "daily_metric_result_canonical_hash": actual_hash,
            "metric_cell": cell_payload,
        }
        evidence.append(
            _MetricEvidence(
                key_hash=key_hash,
                canonical_hash=_hash(canonical_payload),
                payload=_json_ready(canonical_payload),
                breakdown_identity=breakdown_identity,
                metric_name=cell.metric_name,
                metric_status=str(cell.metric_status.value),
                reason_code=str(cell.reason_code.value),
                metric_value=cell.metric_value,
                numerator=cell.numerator,
                denominator=cell.denominator,
            )
        )
    if len({item.key_hash for item in evidence}) != len(evidence):
        raise ForecastQualityContractError("duplicate metric result semantic identity")
    if {item.metric_name for item in evidence} != _EXPECTED_METRIC_NAMES:
        raise ForecastQualityContractError("complete seven-metric result set is required")
    return tuple(evidence)


def _breakdown_evidence(value: Mapping[str, Any]) -> _BreakdownEvidence:
    payload = _json_ready(dict(value))
    identity = payload.get("cell_identity", payload.get("breakdown_identity"))
    if not isinstance(identity, dict) or set(identity) != {
        "forecast_horizon_days",
        "farm_business_key",
        "subfarm_business_key",
        "variety_business_key",
        "season_business_key",
        "model_identity",
    }:
        raise ForecastQualityContractError("breakdown identity must contain exactly six axes")
    for field in identity:
        if identity[field] in (None, ""):
            raise ForecastQualityContractError(f"breakdown identity field is empty: {field}")
    key_hash = _hash(identity)
    try:
        total = int(payload["s2_total_binding_row_count"])
        comparable = int(payload["s2_comparable_row_count"])
        excluded = int(payload["s2_excluded_row_count"])
        not_computable = int(payload["s2_not_computable_row_count"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ForecastQualityContractError("breakdown counters are required") from exc
    if min(total, comparable, excluded, not_computable) < 0:
        raise ForecastQualityContractError("breakdown counters cannot be negative")
    if total != comparable + excluded + not_computable:
        raise ForecastQualityContractError("breakdown counters do not close")
    if (
        "cell_identity_hash" in payload
        and _require_hash(payload["cell_identity_hash"], "cell_identity_hash") != key_hash
    ):
        raise ForecastQualityContractError("breakdown identity hash mismatch")
    metric_status = str(payload.get("metric_status", ""))
    reason_code = str(payload.get("reason_code", ""))
    try:
        normalized_status = MetricStatus(metric_status)
        normalized_reason = ReasonCode(reason_code)
    except ValueError as exc:
        raise ForecastQualityContractError(
            "breakdown status or reason is outside Round A vocabulary"
        ) from exc
    coverage_ratio = payload.get("coverage_ratio")
    if total == 0:
        if coverage_ratio is not None:
            raise ForecastQualityContractError("zero-row breakdown coverage must be null")
        normalized_coverage: Decimal | None = None
    else:
        if coverage_ratio is None:
            raise ForecastQualityContractError("breakdown coverage does not match counters")
        expected_coverage = (Decimal(comparable) / Decimal(total)).quantize(
            _COVERAGE_QUANTUM,
            rounding=ROUND_HALF_EVEN,
        )
        try:
            actual_coverage = Decimal(str(coverage_ratio))
        except (InvalidOperation, ValueError) as exc:
            raise ForecastQualityContractError(
                "breakdown coverage does not match counters"
            ) from exc
        if actual_coverage != expected_coverage:
            raise ForecastQualityContractError("breakdown coverage does not match counters")
        normalized_coverage = expected_coverage
    payload["metric_status"] = normalized_status.value
    payload["reason_code"] = normalized_reason.value
    payload["coverage_ratio"] = (
        None if normalized_coverage is None else format(normalized_coverage, "f")
    )
    canonical_hash = _hash(payload)
    return _BreakdownEvidence(
        key_hash=key_hash,
        canonical_hash=canonical_hash,
        payload=payload,
        identity=identity,
        metric_status=normalized_status.value,
        reason_code=normalized_reason.value,
        comparable_count=comparable,
        excluded_count=excluded,
        not_computable_count=not_computable,
        coverage_ratio=normalized_coverage,
        metric_values=payload.get("metric_values", {}),
    )


def _baseline_evidence(record: BaselinePersistenceRecord) -> _BaselineEvidence:
    request = record.request
    snapshot = record.snapshot
    result = record.result
    if request.requested_quantile != result.baseline_quantile:
        raise ForecastQualityContractError("baseline request/result quantile mismatch")
    pairs = (
        (
            "source_snapshot_identity",
            snapshot.source_snapshot_identity,
            result.source_snapshot_identity,
        ),
        ("source_snapshot_hash", snapshot.source_snapshot_hash, result.source_snapshot_hash),
        ("source_row_set_hash", snapshot.source_row_set_hash, result.source_row_set_hash),
        (
            "visibility_manifest_hash",
            snapshot.visibility_manifest_hash,
            result.visibility_manifest_hash,
        ),
    )
    for field, snapshot_value, result_value in pairs:
        if snapshot_value != result_value:
            raise ForecastQualityContractError(f"baseline {field} mismatch")
    result_hash = _require_hash(result.canonical_hash, "baseline.result.canonical_hash")
    if _object_hash_with_blank_canonical_hash(result) != result_hash:
        raise ForecastQualityContractError("BaselineResult canonical hash replay failed")
    request_payload = _json_ready(dataclasses.asdict(request))
    snapshot_payload = _json_ready(dataclasses.asdict(snapshot))
    result_payload = _json_ready(dataclasses.asdict(result))
    canonical_payload = {
        "schema_version": PERSISTENCE_SCHEMA_VERSION,
        "request": request_payload,
        "snapshot": snapshot_payload,
        "result": result_payload,
        "result_canonical_hash": result_hash,
    }
    return _BaselineEvidence(
        request_hash=_hash(request_payload),
        result_hash=result_hash,
        canonical_hash=_hash(canonical_payload),
        payload=_json_ready(canonical_payload),
        source_identity=_nonempty(snapshot.source_snapshot_identity, "source_snapshot_identity"),
        source_hash=_require_hash(snapshot.source_snapshot_hash, "source_snapshot_hash"),
        source_row_set_hash=_require_hash(snapshot.source_row_set_hash, "source_row_set_hash"),
        visibility_manifest_hash=_require_hash(
            snapshot.visibility_manifest_hash, "visibility_manifest_hash"
        ),
        baseline_policy_version=request_payload["baseline_policy_version"],
        metric_status=str(result.metric_status.value),
        reason_code=str(result.reason_code.value),
    )


def _build_evidence(
    *,
    evaluation_input: S3EvaluationInput,
    metric_results: Sequence[DailyMetricResult],
    breakdown_results: Sequence[Mapping[str, object]],
    baseline_records: Sequence[BaselinePersistenceRecord],
    manifest_payload: Mapping[str, object],
) -> _EvidenceSet:
    run_payload, evaluation_request_hash, run_hash = _validate_evaluation_input(evaluation_input)
    metrics = tuple(item for result in metric_results for item in _metric_evidence(result))
    if len({item.key_hash for item in metrics}) != len(metrics):
        raise ForecastQualityContractError("duplicate metric child identity")
    breakdowns = tuple(_breakdown_evidence(item) for item in breakdown_results)
    if len({item.key_hash for item in breakdowns}) != len(breakdowns):
        raise ForecastQualityContractError("duplicate breakdown child identity")
    baselines = tuple(_baseline_evidence(item) for item in baseline_records)
    if len({item.request_hash for item in baselines}) != len(baselines):
        raise ForecastQualityContractError("duplicate baseline request identity")

    metric_set_hash = _hash_set([item.canonical_hash for item in metrics])
    breakdown_set_hash = _hash_set([item.canonical_hash for item in breakdowns])
    baseline_set_hash = _hash_set([item.canonical_hash for item in baselines])
    instance_payload = {
        "schema_version": PERSISTENCE_SCHEMA_VERSION,
        "evaluation_request_hash": evaluation_request_hash,
        "metric_result_set_hash": metric_set_hash,
        "breakdown_result_set_hash": breakdown_set_hash,
        "baseline_result_set_hash": baseline_set_hash,
        "comparison_result_set_hash": COMPARISON_RESULT_SET_HASH,
    }
    instance_hash = _hash(instance_payload)
    final_manifest_payload = {
        **instance_payload,
        "evaluation_instance_hash": instance_hash,
        "child_counts": {
            "metric_results": len(metrics),
            "breakdown_results": len(breakdowns),
            "baseline_results": len(baselines),
            "comparison_results": 0,
        },
    }
    supplied = _json_ready(dict(manifest_payload))
    unknown = set(supplied) - set(final_manifest_payload)
    if unknown:
        raise ForecastQualityContractError(
            f"manifest assertion contains unknown fields: {sorted(unknown)}"
        )
    for field, expected in supplied.items():
        if canonical_json_bytes(expected) != canonical_json_bytes(final_manifest_payload[field]):
            raise ForecastQualityContractError(f"manifest assertion drift: {field}")
    return _EvidenceSet(
        evaluation_request_hash=evaluation_request_hash,
        run_payload=_json_ready(run_payload),
        run_hash=run_hash,
        metrics=metrics,
        breakdowns=breakdowns,
        baselines=baselines,
        metric_set_hash=metric_set_hash,
        breakdown_set_hash=breakdown_set_hash,
        baseline_set_hash=baseline_set_hash,
        evaluation_instance_hash=instance_hash,
        manifest_payload=final_manifest_payload,
        manifest_hash=_hash(final_manifest_payload),
    )


def _stored_hash(payload: Any) -> str:
    return _hash(payload)


def _stored_canonical_hash(row: Any, field: str = "canonical_hash") -> str:
    try:
        stored = _require_hash(getattr(row, field), field)
    except ForecastQualityContractError as exc:
        raise ForecastQualityPartialResultError(
            f"PARTIAL_METRIC_PERSISTENCE_FORBIDDEN: stored {field} is invalid"
        ) from exc
    if _stored_hash(row.canonical_payload) != stored:
        raise ForecastQualityPartialResultError(
            f"PARTIAL_METRIC_PERSISTENCE_FORBIDDEN: stored {field} payload hash mismatch"
        )
    return stored


def _require_stored_hash(value: Any, field: str) -> str:
    try:
        return _require_hash(value, field)
    except ForecastQualityContractError as exc:
        raise ForecastQualityPartialResultError(
            f"PARTIAL_METRIC_PERSISTENCE_FORBIDDEN: stored {field} is invalid"
        ) from exc


def _require_projection(actual: Any, expected: Any, field: str) -> None:
    if canonical_json_bytes(actual) != canonical_json_bytes(expected):
        raise ForecastQualityPartialResultError(
            f"PARTIAL_METRIC_PERSISTENCE_FORBIDDEN: {field} projection mismatch"
        )


def _stored_metric_projection(row: QualityMetricResultModel) -> tuple[str, str]:
    canonical_hash = _stored_canonical_hash(row)
    try:
        payload = row.canonical_payload
        daily_result = payload["daily_metric_result"]
        metric_cell = payload["metric_cell"]
        identity = daily_result["breakdown_identity"]
        expected_key = _hash(
            {
                "s2_binding_row_set_hash": daily_result["s2_binding_row_set_hash"],
                "metric_input_quantile": daily_result["metric_input_quantile"],
                "breakdown_identity": identity,
                "metric_name": metric_cell["metric_name"],
            }
        )
    except (KeyError, TypeError, AttributeError) as exc:
        raise ForecastQualityPartialResultError(
            "PARTIAL_METRIC_PERSISTENCE_FORBIDDEN: metric semantic projection is malformed"
        ) from exc
    key_hash = _require_stored_hash(row.metric_result_key_hash, "metric_result_key_hash")
    if key_hash != expected_key:
        raise ForecastQualityPartialResultError(
            "PARTIAL_METRIC_PERSISTENCE_FORBIDDEN: metric key projection mismatch"
        )
    for column, expected in (
        ("metric_name", metric_cell.get("metric_name")),
        ("metric_status", metric_cell.get("metric_status")),
        ("reason_code", metric_cell.get("reason_code")),
        ("metric_value", metric_cell.get("metric_value")),
        ("numerator", metric_cell.get("numerator")),
        ("denominator", metric_cell.get("denominator")),
        ("breakdown_identity", identity),
    ):
        _require_projection(getattr(row, column), expected, f"metric {column}")
    return key_hash, canonical_hash


def _stored_breakdown_projection(row: QualityBreakdownResultModel) -> tuple[str, str]:
    canonical_hash = _stored_canonical_hash(row)
    try:
        payload = row.canonical_payload
        identity = payload.get("cell_identity", payload.get("breakdown_identity"))
        expected_key = _hash(identity)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ForecastQualityPartialResultError(
            "PARTIAL_METRIC_PERSISTENCE_FORBIDDEN: breakdown semantic projection is malformed"
        ) from exc
    key_hash = _require_stored_hash(row.breakdown_key_hash, "breakdown_key_hash")
    if key_hash != expected_key:
        raise ForecastQualityPartialResultError(
            "PARTIAL_METRIC_PERSISTENCE_FORBIDDEN: breakdown key projection mismatch"
        )
    for column, expected in (
        ("breakdown_identity", identity),
        ("metric_status", payload.get("metric_status")),
        ("reason_code", payload.get("reason_code")),
        ("s2_comparable_row_count", payload.get("s2_comparable_row_count")),
        ("s2_excluded_row_count", payload.get("s2_excluded_row_count")),
        ("s2_not_computable_row_count", payload.get("s2_not_computable_row_count")),
        ("coverage_ratio", payload.get("coverage_ratio")),
        ("metric_values", payload.get("metric_values", {})),
    ):
        _require_projection(getattr(row, column), expected, f"breakdown {column}")
    return key_hash, canonical_hash


def _stored_baseline_projection(row: NaiveBaselineRunModel) -> tuple[tuple[str, str], str]:
    canonical_hash = _stored_canonical_hash(row)
    try:
        payload = row.canonical_payload
        request_payload = payload["request"]
        result_payload = payload["result"]
        expected_request_hash = _hash(request_payload)
        expected_result_hash = _require_stored_hash(
            result_payload["canonical_hash"], "baseline.result.canonical_hash"
        )
        payload_result_hash = _require_stored_hash(
            payload["result_canonical_hash"], "baseline.result_canonical_hash"
        )
    except (KeyError, TypeError, AttributeError) as exc:
        raise ForecastQualityPartialResultError(
            "PARTIAL_METRIC_PERSISTENCE_FORBIDDEN: baseline semantic projection is malformed"
        ) from exc
    if payload_result_hash != expected_result_hash:
        raise ForecastQualityPartialResultError(
            "PARTIAL_METRIC_PERSISTENCE_FORBIDDEN: baseline result projection mismatch"
        )
    request_hash = _require_stored_hash(row.baseline_request_hash, "baseline_request_hash")
    result_hash = _require_stored_hash(row.baseline_result_hash, "baseline_result_hash")
    if request_hash != expected_request_hash or result_hash != expected_result_hash:
        raise ForecastQualityPartialResultError(
            "PARTIAL_METRIC_PERSISTENCE_FORBIDDEN: baseline key projection mismatch"
        )
    for column, expected in (
        ("baseline_source_snapshot_identity", result_payload.get("source_snapshot_identity")),
        ("baseline_source_snapshot_hash", result_payload.get("source_snapshot_hash")),
        ("baseline_source_row_set_hash", result_payload.get("source_row_set_hash")),
        ("visibility_manifest_hash", result_payload.get("visibility_manifest_hash")),
        ("baseline_policy_version", request_payload.get("baseline_policy_version")),
        ("metric_status", result_payload.get("metric_status")),
        ("reason_code", result_payload.get("reason_code")),
    ):
        _require_projection(getattr(row, column), expected, f"baseline {column}")
    return (request_hash, result_hash), canonical_hash


def _compare_projection_mapping(
    *,
    label: str,
    stored: Sequence[tuple[Any, str]],
    expected: Sequence[tuple[Any, str]],
) -> None:
    stored_map = dict(stored)
    expected_map = dict(expected)
    if len(stored) != len(stored_map) or set(stored_map) != set(expected_map):
        raise ForecastQualityPartialResultError(
            f"PARTIAL_METRIC_PERSISTENCE_FORBIDDEN: {label} child set mismatch"
        )
    for key, stored_hash in stored_map.items():
        if stored_hash != expected_map[key]:
            raise ForecastQualityConflictError(
                f"CONFLICTING_REPLAY_REJECTED: {label} evidence drift"
            )


def _classify_existing(
    session: Session, run: QualityEvaluationRunModel, evidence: _EvidenceSet
) -> PersistedQualityEvaluation:
    if _stored_hash(run.canonical_payload) != run.canonical_hash:
        raise ForecastQualityPartialResultError(
            "PARTIAL_METRIC_PERSISTENCE_FORBIDDEN: stored run payload hash mismatch"
        )
    if run.canonical_hash != evidence.run_hash:
        raise ForecastQualityConflictError("CONFLICTING_REPLAY_REJECTED: run evidence drift")
    metrics = list(
        session.scalars(
            select(QualityMetricResultModel).where(
                QualityMetricResultModel.quality_evaluation_run_id == run.id
            )
        )
    )
    breakdowns = list(
        session.scalars(
            select(QualityBreakdownResultModel).where(
                QualityBreakdownResultModel.quality_evaluation_run_id == run.id
            )
        )
    )
    baselines = list(
        session.scalars(
            select(NaiveBaselineRunModel).where(
                NaiveBaselineRunModel.quality_evaluation_run_id == run.id
            )
        )
    )
    comparisons = list(
        session.scalars(
            select(ModelBaselineComparisonModel).where(
                ModelBaselineComparisonModel.quality_evaluation_run_id == run.id
            )
        )
    )
    manifest = session.scalar(
        select(QualityEvaluationManifestModel).where(
            QualityEvaluationManifestModel.quality_evaluation_run_id == run.id
        )
    )
    if comparisons:
        raise ForecastQualityPartialResultError("comparison rows are forbidden in Round B")
    if manifest is None:
        raise ForecastQualityPartialResultError("PARTIAL_METRIC_PERSISTENCE_FORBIDDEN: no manifest")
    _compare_projection_mapping(
        label="metric",
        stored=[_stored_metric_projection(row) for row in metrics],
        expected=[(item.key_hash, item.canonical_hash) for item in evidence.metrics],
    )
    _compare_projection_mapping(
        label="breakdown",
        stored=[_stored_breakdown_projection(row) for row in breakdowns],
        expected=[(item.key_hash, item.canonical_hash) for item in evidence.breakdowns],
    )
    _compare_projection_mapping(
        label="baseline",
        stored=[_stored_baseline_projection(row) for row in baselines],
        expected=[
            ((item.request_hash, item.result_hash), item.canonical_hash)
            for item in evidence.baselines
        ],
    )
    if _stored_hash(manifest.manifest_payload) != manifest.manifest_hash:
        raise ForecastQualityPartialResultError(
            "PARTIAL_METRIC_PERSISTENCE_FORBIDDEN: stored manifest payload hash mismatch"
        )
    if manifest.manifest_hash != evidence.manifest_hash:
        raise ForecastQualityConflictError("CONFLICTING_REPLAY_REJECTED: manifest evidence drift")
    for field, expected in (
        ("evaluation_request_hash", evidence.evaluation_request_hash),
        ("evaluation_instance_hash", evidence.evaluation_instance_hash),
        ("metric_result_set_hash", evidence.metric_set_hash),
        ("breakdown_result_set_hash", evidence.breakdown_set_hash),
        ("baseline_result_set_hash", evidence.baseline_set_hash),
        ("comparison_result_set_hash", COMPARISON_RESULT_SET_HASH),
    ):
        _require_projection(getattr(manifest, field), expected, f"manifest {field}")
    return PersistedQualityEvaluation(
        run_id=run.id,
        manifest_id=manifest.id,
        evaluation_request_hash=evidence.evaluation_request_hash,
        evaluation_instance_hash=evidence.evaluation_instance_hash,
        new_write_count=0,
        replayed=True,
    )


def _make_run(evidence: _EvidenceSet, now: datetime) -> QualityEvaluationRunModel:
    return QualityEvaluationRunModel(
        schema_version=PERSISTENCE_SCHEMA_VERSION,
        evaluation_request_hash=evidence.evaluation_request_hash,
        s2_run_identity=evidence.run_payload["s2_run_identity"],
        s2_manifest_identity=evidence.run_payload["s2_manifest_identity"],
        s2_binding_row_set_hash=evidence.run_payload["s2_binding_row_set_hash"],
        metric_policy_version=evidence.run_payload["metric_policy_version"],
        baseline_policy_version=evidence.run_payload["baseline_policy_version"],
        status="COMPLETE",
        canonical_payload=evidence.run_payload,
        canonical_hash=evidence.run_hash,
        created_at=now,
        completed_at=now,
    )


def _persist_new(session: Session, evidence: _EvidenceSet) -> PersistedQualityEvaluation:
    now = datetime.now(UTC)
    run = _make_run(evidence, now)
    try:
        with session.begin_nested():
            session.add(run)
            session.flush()
    except IntegrityError as exc:
        existing = session.scalar(
            select(QualityEvaluationRunModel).where(
                QualityEvaluationRunModel.evaluation_request_hash
                == evidence.evaluation_request_hash
            )
        )
        if existing is None:
            raise ForecastQualityPersistenceError("failed to create evaluation run") from exc
        return _classify_existing(session, existing, evidence)

    if run.id is None:
        raise ForecastQualityPersistenceError("database did not assign evaluation run id")
    metric_rows = [
        QualityMetricResultModel(
            quality_evaluation_run_id=run.id,
            schema_version=PERSISTENCE_SCHEMA_VERSION,
            metric_result_key_hash=item.key_hash,
            metric_name=item.metric_name,
            metric_status=item.metric_status,
            reason_code=item.reason_code,
            metric_value=item.metric_value,
            numerator=item.numerator,
            denominator=item.denominator,
            breakdown_identity=item.breakdown_identity,
            canonical_payload=item.payload,
            canonical_hash=item.canonical_hash,
            created_at=now,
            completed_at=now,
        )
        for item in evidence.metrics
    ]
    breakdown_rows = [
        QualityBreakdownResultModel(
            quality_evaluation_run_id=run.id,
            schema_version=PERSISTENCE_SCHEMA_VERSION,
            breakdown_key_hash=item.key_hash,
            breakdown_identity=item.identity,
            metric_status=item.metric_status,
            reason_code=item.reason_code,
            s2_comparable_row_count=item.comparable_count,
            s2_excluded_row_count=item.excluded_count,
            s2_not_computable_row_count=item.not_computable_count,
            coverage_ratio=item.coverage_ratio,
            metric_values=item.metric_values,
            canonical_payload=item.payload,
            canonical_hash=item.canonical_hash,
            created_at=now,
            completed_at=now,
        )
        for item in evidence.breakdowns
    ]
    baseline_rows = [
        NaiveBaselineRunModel(
            quality_evaluation_run_id=run.id,
            schema_version=PERSISTENCE_SCHEMA_VERSION,
            baseline_request_hash=item.request_hash,
            baseline_result_hash=item.result_hash,
            baseline_source_snapshot_identity=item.source_identity,
            baseline_source_snapshot_hash=item.source_hash,
            baseline_source_row_set_hash=item.source_row_set_hash,
            visibility_manifest_hash=item.visibility_manifest_hash,
            baseline_policy_version=item.baseline_policy_version,
            metric_status=item.metric_status,
            reason_code=item.reason_code,
            canonical_payload=item.payload,
            canonical_hash=item.canonical_hash,
            created_at=now,
            completed_at=now,
        )
        for item in evidence.baselines
    ]
    session.add_all([*metric_rows, *breakdown_rows, *baseline_rows])
    session.flush()
    manifest = QualityEvaluationManifestModel(
        quality_evaluation_run_id=run.id,
        schema_version=PERSISTENCE_SCHEMA_VERSION,
        evaluation_request_hash=evidence.evaluation_request_hash,
        evaluation_instance_hash=evidence.evaluation_instance_hash,
        metric_result_set_hash=evidence.metric_set_hash,
        breakdown_result_set_hash=evidence.breakdown_set_hash,
        baseline_result_set_hash=evidence.baseline_set_hash,
        comparison_result_set_hash=COMPARISON_RESULT_SET_HASH,
        manifest_payload=evidence.manifest_payload,
        manifest_hash=evidence.manifest_hash,
        created_at=now,
        completed_at=now,
        sealed_at=now,
    )
    session.add(manifest)
    session.flush()
    return PersistedQualityEvaluation(
        run_id=run.id,
        manifest_id=manifest.id,
        evaluation_request_hash=evidence.evaluation_request_hash,
        evaluation_instance_hash=evidence.evaluation_instance_hash,
        new_write_count=1 + len(metric_rows) + len(breakdown_rows) + len(baseline_rows) + 1,
        replayed=False,
    )


def persist_quality_evaluation(
    session: Session,
    *,
    evaluation_input: S3EvaluationInput,
    metric_results: Sequence[DailyMetricResult],
    breakdown_results: Sequence[Mapping[str, object]],
    baseline_records: Sequence[BaselinePersistenceRecord],
    comparison_records: Sequence[Mapping[str, object]],
    manifest_payload: Mapping[str, object],
) -> PersistedQualityEvaluation:
    """Persist one complete result without taking transaction ownership."""
    if comparison_records:
        raise ForecastQualityContractError(
            "NONEMPTY_COMPARISON_RECORDS_FAIL_CLOSED: comparison rows are not authorized"
        )
    if not isinstance(session, Session):
        raise TypeError("persist_quality_evaluation requires a synchronous SQLAlchemy Session")
    if not isinstance(manifest_payload, Mapping):
        raise ForecastQualityContractError("manifest_payload must be a mapping")
    evidence = _build_evidence(
        evaluation_input=evaluation_input,
        metric_results=metric_results,
        breakdown_results=breakdown_results,
        baseline_records=baseline_records,
        manifest_payload=manifest_payload,
    )
    existing = cast(
        QualityEvaluationRunModel | None,
        session.scalar(
            select(QualityEvaluationRunModel).where(
                QualityEvaluationRunModel.evaluation_request_hash
                == evidence.evaluation_request_hash
            )
        ),
    )
    if existing is not None:
        return _classify_existing(session, existing, evidence)
    return _persist_new(session, evidence)


__all__ = [
    "BaselinePersistenceRecord",
    "COMPARISON_RESULT_SET_HASH",
    "ForecastQualityConflictError",
    "ForecastQualityContractError",
    "ForecastQualityPartialResultError",
    "ForecastQualityPersistenceError",
    "PersistedQualityEvaluation",
    "persist_quality_evaluation",
]
