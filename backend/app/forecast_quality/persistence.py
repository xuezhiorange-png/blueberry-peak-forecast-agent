"""Caller-owned persistence for the V0.2-S3 Round B and Round C evidence sets."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.forecast_quality.canonical import canonical_json_bytes
from backend.app.forecast_quality.comparison import (
    COMPARISON_POLICY_VERSION,
    COMPARISON_RESULT_SCHEMA_VERSION,
    COMPARISON_RESULT_SET_SCHEMA_VERSION,
    ComparisonName,
    ComparisonResult,
    build_comparison_result_set_payload,
    compute_comparison_result_set_hash,
)
from backend.app.forecast_quality.enums import ComparisonAvailability, MetricStatus, ReasonCode
from backend.app.forecast_quality.schemas import (
    BaselineRequest,
    BaselineResult,
    BaselineSourceSnapshot,
    DailyMetricResult,
    S3EvaluationInput,
)
from backend.app.models.forecast_quality import (
    PERSISTENCE_SCHEMA_VERSION,
    ROUND_C_PERSISTENCE_SCHEMA_VERSION,
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
class PersistedQualityEvaluationReadModel:
    """Immutable, verified Quality evidence returned by the read adapter."""

    run_id: int
    manifest_id: int
    evaluation_request_hash: str
    evaluation_instance_hash: str
    run_payload: Mapping[str, object]
    manifest_payload: Mapping[str, object]
    metrics: tuple[Mapping[str, object], ...]
    breakdowns: tuple[Mapping[str, object], ...]
    baselines: tuple[Mapping[str, object], ...]
    comparisons: tuple[Mapping[str, object], ...]


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
class _ComparisonEvidence:
    key_hash: str
    canonical_hash: str
    payload: dict[str, Any]
    result: ComparisonResult


@dataclass(frozen=True)
class _EvidenceSet:
    evaluation_request_hash: str
    run_payload: dict[str, Any]
    run_hash: str
    metrics: tuple[_MetricEvidence, ...]
    breakdowns: tuple[_BreakdownEvidence, ...]
    baselines: tuple[_BaselineEvidence, ...]
    comparisons: tuple[_ComparisonEvidence, ...]
    persistence_schema_version: str
    comparison_policy_version: str | None
    comparison_result_schema_version: str | None
    comparison_result_set_schema_version: str
    comparison_result_set_hash: str
    comparison_cell_count: int
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


def _validate_evaluation_input(
    value: S3EvaluationInput,
    *,
    round_c: bool = False,
    request_identity_payload: Mapping[str, object] | None = None,
) -> tuple[dict[str, Any], str, str]:
    for field in (
        "s2_run_identity",
        "s2_manifest_identity",
        "s2_binding_row_set_hash",
    ):
        _nonempty(getattr(value, field), field)
    for field in ("metric_policy_version", "baseline_policy_version"):
        _nonempty(getattr(value, field).value, field)
    request_payload: dict[str, Any] = {
        "schema_version": ROUND_C_PERSISTENCE_SCHEMA_VERSION
        if round_c
        else PERSISTENCE_SCHEMA_VERSION,
        "s2_run_identity": value.s2_run_identity,
        "s2_manifest_identity": value.s2_manifest_identity,
        "s2_binding_row_set_hash": value.s2_binding_row_set_hash,
        "metric_policy_version": value.metric_policy_version,
        "baseline_policy_version": value.baseline_policy_version,
    }
    if request_identity_payload is not None:
        identity = _json_ready(dict(request_identity_payload))
        actor_identity = identity.get("actor_identity")
        idempotency_key = identity.get("request_idempotency_key")
        canonical_request = identity.get("canonical_request")
        if not isinstance(actor_identity, str) or not actor_identity.strip():
            raise ForecastQualityContractError("actor_identity is required")
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise ForecastQualityContractError("request_idempotency_key is required")
        if not isinstance(canonical_request, Mapping):
            raise ForecastQualityContractError("canonical_request is required")
        request_payload["trial_request_identity"] = identity
        request_identity_hash = _hash(
            {
                "schema_version": request_payload["schema_version"],
                "actor_identity": actor_identity,
                "request_idempotency_key": idempotency_key,
            }
        )
    else:
        request_identity_hash = _hash(request_payload)
    if round_c:
        request_payload.update(
            {
                "persistence_schema_version": ROUND_C_PERSISTENCE_SCHEMA_VERSION,
                "comparison_policy_version": COMPARISON_POLICY_VERSION,
                "comparison_result_schema_version": COMPARISON_RESULT_SCHEMA_VERSION,
                "comparison_contract_enabled": True,
            }
        )
    return request_payload, request_identity_hash, _hash(request_payload)


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
    try:
        normalized_status = MetricStatus(result.metric_status)
        normalized_reason = ReasonCode(result.reason_code)
    except ValueError as exc:
        raise ForecastQualityContractError(
            "baseline status or reason is outside Round A vocabulary"
        ) from exc
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
        metric_status=normalized_status.value,
        reason_code=normalized_reason.value,
    )


def _comparison_evidence(value: ComparisonResult | Mapping[str, object]) -> _ComparisonEvidence:
    if isinstance(value, ComparisonResult):
        result = value
    else:
        raise ForecastQualityContractError(
            "comparison_records must contain ComparisonResult instances"
        )
    if result.schema_version != COMPARISON_RESULT_SCHEMA_VERSION:
        raise ForecastQualityContractError("comparison result schema version mismatch")
    if result.comparison_policy_version != COMPARISON_POLICY_VERSION:
        raise ForecastQualityContractError("comparison policy version mismatch")
    try:
        normalized_availability = ComparisonAvailability(result.comparison_availability)
        normalized_status = MetricStatus(result.metric_status)
        normalized_reason = ReasonCode(result.reason_code)
    except ValueError as exc:
        raise ForecastQualityContractError(
            "comparison status, availability, or reason is outside Round C vocabulary"
        ) from exc
    payload = _json_ready(result.canonical_payload)
    canonical_hash = _require_hash(result.canonical_hash, "comparison.canonical_hash")
    if _hash(payload) != canonical_hash:
        raise ForecastQualityContractError("comparison canonical hash replay failed")
    member_set = result.baseline_member_identity_set
    if not isinstance(member_set, list) or not member_set:
        raise ForecastQualityContractError("comparison baseline member set must be nonempty")
    member_keys = {
        "comparison_daily_key",
        "baseline_request_hash",
        "baseline_result_hash",
        "baseline_source_snapshot_identity",
        "baseline_source_snapshot_hash",
        "baseline_source_row_set_hash",
        "visibility_manifest_hash",
        "baseline_policy_version",
    }
    daily_keys = {
        "current_target_date",
        "current_forecast_cutoff_at",
        "farm_business_key",
        "subfarm_business_key",
        "variety_business_key",
        "metric_policy_version",
        "baseline_policy_version",
    }
    normalized_members: list[dict[str, Any]] = []
    for member in member_set:
        if not isinstance(member, Mapping) or set(member) != member_keys:
            raise ForecastQualityContractError("comparison baseline member shape mismatch")
        daily_key = member.get("comparison_daily_key")
        if not isinstance(daily_key, Mapping) or set(daily_key) != daily_keys:
            raise ForecastQualityContractError("comparison daily key shape mismatch")
        for field in member_keys - {"comparison_daily_key"}:
            _nonempty(member[field], f"comparison member {field}")
        for field in (
            "baseline_request_hash",
            "baseline_result_hash",
            "baseline_source_snapshot_hash",
            "baseline_source_row_set_hash",
            "visibility_manifest_hash",
        ):
            _require_hash(member[field], f"comparison member {field}")
        normalized_members.append(_json_ready(dict(member)))
    normalized_members.sort(key=lambda item: canonical_json_bytes(item["comparison_daily_key"]))
    if normalized_members != member_set:
        raise ForecastQualityContractError("comparison baseline member order is not canonical")
    member_set_payload = {
        "members": normalized_members,
        "schema_version": "v0.2-s3-comparison-baseline-member-set-v1",
    }
    if result.baseline_member_set_hash != _hash(member_set_payload):
        raise ForecastQualityContractError("comparison baseline member set hash mismatch")
    name = result.comparison_name
    if not isinstance(name, ComparisonName):
        try:
            name = ComparisonName(name)
        except ValueError as exc:
            raise ForecastQualityContractError(
                "comparison name is outside Round C vocabulary"
            ) from exc
    if set(result.normalized_breakdown_identity) != {
        "forecast_horizon_days",
        "farm_business_key",
        "subfarm_business_key",
        "variety_business_key",
        "season_business_key",
        "model_identity",
    }:
        raise ForecastQualityContractError("comparison breakdown identity must contain six axes")
    if result.model_identity != result.normalized_breakdown_identity["model_identity"]:
        raise ForecastQualityContractError("comparison model identity projection mismatch")
    if (
        result.forecast_horizon_days
        != result.normalized_breakdown_identity["forecast_horizon_days"]
    ):
        raise ForecastQualityContractError("comparison horizon projection mismatch")
    expected_key = _hash(
        {
            "comparison_result_schema_version": COMPARISON_RESULT_SCHEMA_VERSION,
            "comparison_policy_version": COMPARISON_POLICY_VERSION,
            "comparison_name": name.value,
            "baseline_member_set_hash": result.baseline_member_set_hash,
            "normalized_breakdown_identity": result.normalized_breakdown_identity,
        }
    )
    if result.comparison_key_hash != expected_key:
        raise ForecastQualityContractError("comparison key projection mismatch")
    if normalized_status is MetricStatus.NOT_COMPUTABLE:
        if any(
            value is not None
            for value in (result.model_value, result.baseline_value, result.delta_value)
        ):
            raise ForecastQualityContractError("not-computable comparison values must be null")
        if normalized_reason is ReasonCode.NONE:
            raise ForecastQualityContractError("not-computable comparison reason is required")
    elif any(
        value is None for value in (result.model_value, result.baseline_value, result.delta_value)
    ):
        raise ForecastQualityContractError("computable comparison values are required")
    if normalized_availability is ComparisonAvailability.AVAILABLE and (
        result.external_blocker is not None or result.frozen_limitation is not None
    ):
        raise ForecastQualityContractError("daily comparison limitation fields must be null")
    if normalized_availability is ComparisonAvailability.BLOCKED and (
        result.external_blocker is not None or result.frozen_limitation != normalized_reason.value
    ):
        raise ForecastQualityContractError("blocked comparison limitation projection mismatch")
    return _ComparisonEvidence(
        key_hash=expected_key,
        canonical_hash=canonical_hash,
        payload=payload,
        result=dataclasses.replace(
            result,
            comparison_name=name,
            comparison_availability=normalized_availability,
            metric_status=normalized_status,
            reason_code=normalized_reason,
            baseline_member_identity_set=normalized_members,
        ),
    )


def _build_evidence(
    *,
    evaluation_input: S3EvaluationInput,
    metric_results: Sequence[DailyMetricResult],
    breakdown_results: Sequence[Mapping[str, object]],
    baseline_records: Sequence[BaselinePersistenceRecord],
    comparison_records: Sequence[ComparisonResult | Mapping[str, object]],
    manifest_payload: Mapping[str, object],
    comparison_contract_enabled: bool = False,
    request_identity_payload: Mapping[str, object] | None = None,
) -> _EvidenceSet:
    """Build a pre-SQL graph evidence set with explicit V1/V2 mode selection.

    The caller MUST declare whether Round C comparison contract is enabled
    via ``comparison_contract_enabled``.  Round C no longer infers the mode
    from ``bool(comparisons)``.  V1 callers (``False``) must not supply any
    comparison records; V2 callers (``True``) may supply zero cells (full
    V2 schema) or full ten-record cells.
    """
    comparisons = tuple(_comparison_evidence(item) for item in comparison_records)
    if not comparison_contract_enabled:
        if comparisons:
            raise ForecastQualityContractError(
                "comparison records supplied without comparison_contract_enabled=True"
            )
    # V2 zero-cell branch must still publish V2 request identity, result-set
    # schema, and empty-set hash — never silently fall back to V1.  This is
    # achieved by keying ``comparison_contract_enabled`` through every schema
    # selector below (instead of ``bool(comparisons)``).
    run_payload, evaluation_request_hash, run_hash = _validate_evaluation_input(
        evaluation_input,
        round_c=comparison_contract_enabled,
        request_identity_payload=request_identity_payload,
    )
    metrics = tuple(item for result in metric_results for item in _metric_evidence(result))
    if len({item.key_hash for item in metrics}) != len(metrics):
        raise ForecastQualityContractError("duplicate metric child identity")
    breakdowns = tuple(_breakdown_evidence(item) for item in breakdown_results)
    if len({item.key_hash for item in breakdowns}) != len(breakdowns):
        raise ForecastQualityContractError("duplicate breakdown child identity")
    baselines = tuple(_baseline_evidence(item) for item in baseline_records)
    if len({item.request_hash for item in baselines}) != len(baselines):
        raise ForecastQualityContractError("duplicate baseline request identity")
    # baseline supplied set: hash of request identities that were supplied.
    supplied_baseline_result_hashes = {item.result_hash for item in baselines}
    supplied_baseline_request_hashes = {item.request_hash for item in baselines}
    names_by_cell: dict[bytes, set[str]] = {}
    if comparisons:
        keys = [item.key_hash for item in comparisons]
        if len(set(keys)) != len(keys):
            raise ForecastQualityContractError("duplicate comparison semantic identity")
        for item in comparisons:
            cell_key = canonical_json_bytes(item.result.normalized_breakdown_identity)
            names_by_cell.setdefault(cell_key, set()).add(item.result.comparison_name.value)
        expected_names = {name.value for name in ComparisonName}
        if any(names != expected_names for names in names_by_cell.values()):
            raise ForecastQualityContractError("each comparison cell must contain ten records")
        # baseline referenced member set: every comparison must reference a
        # member of the supplied baseline set (by baseline_result_hash) and
        # all members referenced across all comparisons must coincide (no
        # comparison references a baseline that the caller did not supply).
        referenced_baseline_result_hashes: set[str] = set()
        referenced_baseline_request_hashes: set[str] = set()
        for item in comparisons:
            for member in item.result.baseline_member_identity_set:
                result_hash = member["baseline_result_hash"]
                request_hash = member["baseline_request_hash"]
                if result_hash not in supplied_baseline_result_hashes:
                    raise ForecastQualityContractError(
                        f"comparison references baseline_result_hash={result_hash[:12]}... "
                        "not present in supplied baseline set"
                    )
                if request_hash not in supplied_baseline_request_hashes:
                    raise ForecastQualityContractError(
                        f"comparison references baseline_request_hash={request_hash[:12]}... "
                        "not present in supplied baseline set"
                    )
                referenced_baseline_result_hashes.add(result_hash)
                referenced_baseline_request_hashes.add(request_hash)
        if referenced_baseline_result_hashes != supplied_baseline_result_hashes:
            missing = supplied_baseline_result_hashes - referenced_baseline_result_hashes
            if missing:
                raise ForecastQualityContractError(
                    f"supplied baseline set has members never referenced by any comparison: "
                    f"{sorted(hash[:12] for hash in missing)}"
                )
        # Comparison cell identity: every comparison inside one cell must
        # share the same baseline_member_set_hash.  Already implicit through
        # the canonical payload replay, but we make it explicit here.
        cell_member_set_hashes: dict[bytes, str] = {}
        for item in comparisons:
            cell_key = canonical_json_bytes(item.result.normalized_breakdown_identity)
            existing = cell_member_set_hashes.get(cell_key)
            if existing is None:
                cell_member_set_hashes[cell_key] = item.result.baseline_member_set_hash
            elif existing != item.result.baseline_member_set_hash:
                raise ForecastQualityContractError(
                    "comparison cell has inconsistent baseline_member_set_hash"
                )
        # canonical payload truth table: every ComparisonResult stored
        # field must agree with its derivation from the calculator cells.
        # (Per-cell baseline_member_set_hash and comparison_key_hash are
        # verified inside _comparison_evidence.)
    if comparison_contract_enabled:
        # V2: comparison_result_set_schema_version, comparison_policy_version,
        # and persistence_schema_version always published (zero cells included).
        comparison_result_set_schema_version = COMPARISON_RESULT_SET_SCHEMA_VERSION
        comparison_result_schema_version = COMPARISON_RESULT_SCHEMA_VERSION
        comparison_policy_version: str | None = COMPARISON_POLICY_VERSION
        persistence_schema_version = ROUND_C_PERSISTENCE_SCHEMA_VERSION
    else:
        # V1: V1 persistence only, no comparison children expected.
        comparison_result_set_schema_version = "v0.2-s3-comparison-result-set-v1"
        comparison_result_schema_version = None
        comparison_policy_version = None
        persistence_schema_version = PERSISTENCE_SCHEMA_VERSION

    metric_set_hash = _hash_set([item.canonical_hash for item in metrics])
    breakdown_set_hash = _hash_set([item.canonical_hash for item in breakdowns])
    baseline_set_hash = _hash_set([item.canonical_hash for item in baselines])
    comparison_hashes = [item.canonical_hash for item in comparisons]
    comparison_result_set_payload = (
        build_comparison_result_set_payload(comparison_hashes)
        if comparison_contract_enabled
        else COMPARISON_RESULT_SET_PAYLOAD
    )
    comparison_result_set_hash = (
        compute_comparison_result_set_hash(comparison_hashes)
        if comparison_contract_enabled
        else COMPARISON_RESULT_SET_HASH
    )
    instance_payload = {
        "schema_version": persistence_schema_version,
        "evaluation_request_hash": evaluation_request_hash,
        "metric_result_set_hash": metric_set_hash,
        "breakdown_result_set_hash": breakdown_set_hash,
        "baseline_result_set_hash": baseline_set_hash,
        "comparison_result_set_hash": comparison_result_set_hash,
    }
    instance_hash = _hash(instance_payload)
    final_manifest_payload = {
        **instance_payload,
        "evaluation_instance_hash": instance_hash,
        "child_counts": {
            "metric_results": len(metrics),
            "breakdown_results": len(breakdowns),
            "baseline_results": len(baselines),
            "comparison_results": len(comparisons),
        },
        "comparison_result_set_payload": comparison_result_set_payload,
        "comparison_cell_count": len(names_by_cell) if comparisons else 0,
        "comparison_result_count": len(comparisons),
        "comparison_policy_version": comparison_policy_version,
        "comparison_result_schema_version": comparison_result_schema_version,
        "comparison_result_set_schema_version": comparison_result_set_schema_version,
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
        comparisons=comparisons,
        persistence_schema_version=persistence_schema_version,
        comparison_policy_version=comparison_policy_version,
        comparison_result_schema_version=comparison_result_schema_version,
        comparison_result_set_schema_version=comparison_result_set_schema_version,
        comparison_result_set_hash=comparison_result_set_hash,
        comparison_cell_count=len(names_by_cell) if comparisons else 0,
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


def _stored_comparison_projection(row: ModelBaselineComparisonModel) -> tuple[str, str]:
    canonical_hash = _stored_canonical_hash(row)
    payload = row.canonical_payload
    key_hash = _require_stored_hash(row.comparison_key_hash, "comparison_key_hash")
    if payload.get("comparison_key_hash") != key_hash:
        raise ForecastQualityPartialResultError(
            "PARTIAL_METRIC_PERSISTENCE_FORBIDDEN: comparison key projection mismatch"
        )
    if payload.get("comparison_name") != row.comparison_name:
        raise ForecastQualityPartialResultError(
            "PARTIAL_METRIC_PERSISTENCE_FORBIDDEN: comparison name projection mismatch"
        )
    for column in (
        "comparison_policy_version",
        "comparison_availability",
        "metric_status",
        "reason_code",
        "external_blocker",
        "frozen_limitation",
        "model_identity",
        "baseline_member_identity_set",
        "baseline_member_set_hash",
        "normalized_breakdown_identity",
        "forecast_horizon_days",
        "model_value",
        "baseline_value",
        "delta_value",
        "model_input_row_count",
        "baseline_input_row_count",
        "common_comparable_row_count",
        "model_only_row_count",
        "baseline_only_row_count",
        "excluded_row_count",
        "not_computable_row_count",
    ):
        _require_projection(getattr(row, column), payload.get(column), f"comparison {column}")
    return key_hash, canonical_hash


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
    _compare_projection_mapping(
        label="comparison",
        stored=[_stored_comparison_projection(row) for row in comparisons],
        expected=[(item.key_hash, item.canonical_hash) for item in evidence.comparisons],
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
        ("comparison_result_set_hash", evidence.comparison_result_set_hash),
        ("comparison_policy_version", evidence.comparison_policy_version),
        ("comparison_result_schema_version", evidence.comparison_result_schema_version),
        (
            "comparison_result_set_schema_version",
            evidence.comparison_result_set_schema_version,
        ),
        ("comparison_cell_count", evidence.comparison_cell_count),
        ("comparison_result_count", len(evidence.comparisons)),
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


def load_quality_evaluation_by_instance_hash(
    session: Session,
    *,
    evaluation_instance_hash: str,
) -> PersistedQualityEvaluationReadModel:
    """Load one complete Quality result from immutable persisted evidence.

    The Trial layer receives this value object rather than an ORM graph.  The
    loader deliberately performs the same projection and hash checks used by
    the replay path, so missing children and normalized-column drift fail
    closed before any public DTO is produced.
    """

    if not isinstance(session, Session):
        raise TypeError("load_quality_evaluation_by_instance_hash requires a synchronous Session")
    if (
        not isinstance(evaluation_instance_hash, str)
        or re.fullmatch(r"[0-9a-f]{64}", evaluation_instance_hash) is None
    ):
        raise ForecastQualityContractError("evaluation_instance_hash must be lowercase SHA-256")
    manifest = session.scalar(
        select(QualityEvaluationManifestModel).where(
            QualityEvaluationManifestModel.evaluation_instance_hash == evaluation_instance_hash
        )
    )
    if manifest is None:
        raise ForecastQualityPartialResultError("PARTIAL_METRIC_PERSISTENCE_FORBIDDEN: no manifest")
    run = session.get(QualityEvaluationRunModel, manifest.quality_evaluation_run_id)
    if run is None or run.status != "COMPLETE":
        raise ForecastQualityPartialResultError(
            "PARTIAL_METRIC_PERSISTENCE_FORBIDDEN: complete run is missing"
        )
    if run.schema_version not in {
        PERSISTENCE_SCHEMA_VERSION,
        ROUND_C_PERSISTENCE_SCHEMA_VERSION,
    } or manifest.schema_version != run.schema_version or manifest.sealed_at is None:
        raise ForecastQualityPartialResultError(
            "PARTIAL_METRIC_PERSISTENCE_FORBIDDEN: sealed schema identity is invalid"
        )
    if _stored_hash(run.canonical_payload) != run.canonical_hash:
        raise ForecastQualityPartialResultError(
            "PARTIAL_METRIC_PERSISTENCE_FORBIDDEN: stored run payload hash mismatch"
        )
    if run.canonical_payload.get("evaluation_request_hash") != run.evaluation_request_hash:
        raise ForecastQualityPartialResultError(
            "PARTIAL_METRIC_PERSISTENCE_FORBIDDEN: run request identity projection mismatch"
        )
    request_identity = run.canonical_payload.get("trial_request_identity")
    if not isinstance(request_identity, Mapping):
        raise ForecastQualityPartialResultError(
            "PARTIAL_METRIC_PERSISTENCE_FORBIDDEN: trial request identity is missing"
        )
    actor_identity = request_identity.get("actor_identity")
    idempotency_key = request_identity.get("request_idempotency_key")
    canonical_request = request_identity.get("canonical_request")
    if (
        not isinstance(actor_identity, str)
        or not actor_identity.strip()
        or not isinstance(idempotency_key, str)
        or not idempotency_key.strip()
        or not isinstance(canonical_request, Mapping)
    ):
        raise ForecastQualityPartialResultError(
            "PARTIAL_METRIC_PERSISTENCE_FORBIDDEN: trial request identity is invalid"
        )
    expected_request_hash = _hash(
        {
            "schema_version": run.schema_version,
            "actor_identity": actor_identity,
            "request_idempotency_key": idempotency_key,
        }
    )
    if expected_request_hash != run.evaluation_request_hash:
        raise ForecastQualityPartialResultError(
            "PARTIAL_METRIC_PERSISTENCE_FORBIDDEN: evaluation request hash drift"
        )
    if _stored_hash(manifest.manifest_payload) != manifest.manifest_hash:
        raise ForecastQualityPartialResultError(
            "PARTIAL_METRIC_PERSISTENCE_FORBIDDEN: stored manifest payload hash mismatch"
        )
    if (
        manifest.evaluation_request_hash != run.evaluation_request_hash
        or manifest.evaluation_instance_hash != evaluation_instance_hash
        or manifest.manifest_payload.get("evaluation_instance_hash") != evaluation_instance_hash
        or run.canonical_payload.get("schema_version") != run.schema_version
        or manifest.manifest_payload.get("schema_version") != manifest.schema_version
    ):
        raise ForecastQualityPartialResultError(
            "PARTIAL_METRIC_PERSISTENCE_FORBIDDEN: manifest identity projection mismatch"
        )

    metrics = tuple(
        session.scalars(
            select(QualityMetricResultModel)
            .where(QualityMetricResultModel.quality_evaluation_run_id == run.id)
            .order_by(QualityMetricResultModel.metric_result_key_hash)
        )
    )
    breakdowns = tuple(
        session.scalars(
            select(QualityBreakdownResultModel)
            .where(QualityBreakdownResultModel.quality_evaluation_run_id == run.id)
            .order_by(QualityBreakdownResultModel.breakdown_key_hash)
        )
    )
    baselines = tuple(
        session.scalars(
            select(NaiveBaselineRunModel)
            .where(NaiveBaselineRunModel.quality_evaluation_run_id == run.id)
            .order_by(NaiveBaselineRunModel.baseline_request_hash)
        )
    )
    comparisons = tuple(
        session.scalars(
            select(ModelBaselineComparisonModel)
            .where(ModelBaselineComparisonModel.quality_evaluation_run_id == run.id)
            .order_by(ModelBaselineComparisonModel.comparison_key_hash)
        )
    )
    expected_counts = manifest.manifest_payload.get("child_counts")
    if not isinstance(expected_counts, Mapping):
        raise ForecastQualityPartialResultError(
            "PARTIAL_METRIC_PERSISTENCE_FORBIDDEN: child counts are missing"
        )
    actual_counts = {
        "metric_results": len(metrics),
        "breakdown_results": len(breakdowns),
        "baseline_results": len(baselines),
        "comparison_results": len(comparisons),
    }
    if dict(expected_counts) != actual_counts:
        raise ForecastQualityPartialResultError(
            "PARTIAL_METRIC_PERSISTENCE_FORBIDDEN: child count mismatch"
        )

    metric_projections = tuple(_stored_metric_projection(row) for row in metrics)
    breakdown_projections = tuple(_stored_breakdown_projection(row) for row in breakdowns)
    baseline_projections = tuple(_stored_baseline_projection(row) for row in baselines)
    comparison_projections = tuple(_stored_comparison_projection(row) for row in comparisons)
    if manifest.metric_result_set_hash != _hash_set([item[1] for item in metric_projections]):
        raise ForecastQualityPartialResultError("metric result-set hash drift")
    if manifest.breakdown_result_set_hash != _hash_set([item[1] for item in breakdown_projections]):
        raise ForecastQualityPartialResultError("breakdown result-set hash drift")
    if manifest.baseline_result_set_hash != _hash_set([item[1] for item in baseline_projections]):
        raise ForecastQualityPartialResultError("baseline result-set hash drift")
    if manifest.schema_version == ROUND_C_PERSISTENCE_SCHEMA_VERSION:
        comparison_hash = compute_comparison_result_set_hash(
            [item[1] for item in comparison_projections]
        )
    else:
        comparison_hash = COMPARISON_RESULT_SET_HASH
    if manifest.comparison_result_set_hash != comparison_hash:
        raise ForecastQualityPartialResultError("comparison result-set hash drift")
    if manifest.comparison_result_count != len(comparisons):
        raise ForecastQualityPartialResultError("comparison result count drift")
    if manifest.comparison_cell_count != int(
        manifest.manifest_payload.get("comparison_cell_count", -1)
    ):
        raise ForecastQualityPartialResultError("comparison cell count drift")
    expected_instance_hash = _hash(
        {
            "schema_version": run.schema_version,
            "evaluation_request_hash": run.evaluation_request_hash,
            "metric_result_set_hash": manifest.metric_result_set_hash,
            "breakdown_result_set_hash": manifest.breakdown_result_set_hash,
            "baseline_result_set_hash": manifest.baseline_result_set_hash,
            "comparison_result_set_hash": manifest.comparison_result_set_hash,
        }
    )
    if expected_instance_hash != evaluation_instance_hash:
        raise ForecastQualityPartialResultError(
            "PARTIAL_METRIC_PERSISTENCE_FORBIDDEN: evaluation instance hash drift"
        )

    return PersistedQualityEvaluationReadModel(
        run_id=run.id,
        manifest_id=manifest.id,
        evaluation_request_hash=run.evaluation_request_hash,
        evaluation_instance_hash=evaluation_instance_hash,
        run_payload=dict(run.canonical_payload),
        manifest_payload=dict(manifest.manifest_payload),
        metrics=tuple(dict(row.canonical_payload) for row in metrics),
        breakdowns=tuple(dict(row.canonical_payload) for row in breakdowns),
        baselines=tuple(dict(row.canonical_payload) for row in baselines),
        comparisons=tuple(dict(row.canonical_payload) for row in comparisons),
    )


def _make_run(evidence: _EvidenceSet, now: datetime) -> QualityEvaluationRunModel:
    return QualityEvaluationRunModel(
        schema_version=evidence.persistence_schema_version,
        evaluation_request_hash=evidence.evaluation_request_hash,
        s2_run_identity=evidence.run_payload["s2_run_identity"],
        s2_manifest_identity=evidence.run_payload["s2_manifest_identity"],
        s2_binding_row_set_hash=evidence.run_payload["s2_binding_row_set_hash"],
        metric_policy_version=evidence.run_payload["metric_policy_version"],
        baseline_policy_version=evidence.run_payload["baseline_policy_version"],
        comparison_policy_version=evidence.comparison_policy_version,
        status="COMPLETE",
        canonical_payload=evidence.run_payload,
        canonical_hash=evidence.run_hash,
        created_at=now,
        completed_at=now,
    )


def _persist_new(session: Session, evidence: _EvidenceSet) -> PersistedQualityEvaluation:
    now = datetime.now(UTC)
    run = _make_run(evidence, now)
    # Brief §12/§13 — run UNIQUE race classification.
    # A concurrent writer may have committed the run row for this
    # evaluation_request_hash between our SELECT (above) and our
    # INSERT (below).  The DB rejects our INSERT with
    # SQLSTATE=23505 + constraint_name=uq_quality_evaluation_run_request.
    # We classify that specific failure by re-reading
    # evaluation_request_hash and routing through
    # ``_classify_existing``.  Any other SQLSTATE or constraint
    # propagates verbatim so we never silently turn a contract
    # failure into a replay.
    try:
        with session.begin_nested():
            session.add(run)
            session.flush()
    except IntegrityError as exc:
        # Brief §5.3 — extract sqlstate and constraint_name in
        # this order.  If the adapter does not expose
        # ``sqlstate`` (asyncpg ``RaiseError``) we must still
        # not guess — the text fallback below is bounded to the
        # exact ``duplicate key value violates unique constraint
        # "<name>"`` shape; anything else is fail-closed.
        orig = getattr(exc, "orig", None)
        sqlstate: str | None = None
        if orig is not None and hasattr(orig, "sqlstate"):
            sqlstate = getattr(orig, "sqlstate", None)
        constraint_name: str | None = None
        if orig is not None and hasattr(orig, "constraint_name"):
            constraint_name = getattr(orig, "constraint_name", None)
        if sqlstate is None or constraint_name is None:
            msg = str(exc)
            import re

            sql_match = re.search(r"SQLSTATE (\d{5})", msg)
            if sqlstate is None and sql_match is not None:
                sqlstate = sql_match.group(1)
            cstr_match = re.search(
                r'duplicate key value violates unique constraint "([^"]+)"',
                msg,
            )
            if constraint_name is None and cstr_match is not None:
                constraint_name = cstr_match.group(1)
        if sqlstate is None or constraint_name is None:
            # Brief §5.3 — unknown adapter exception shape must
            # propagate verbatim, never get coerced to a replay.
            raise
        if sqlstate != "23505" or constraint_name not in ("uq_quality_evaluation_run_request",):
            # Brief §5.2 — run INSERT may ONLY classify the
            # ``uq_quality_evaluation_run_request`` UNIQUE race.
            # All other SQLSTATEs, all other constraints
            # (including ``uq_quality_manifest_run``), and any
            # unknown adapter shape must propagate verbatim so we
            # never silently turn a contract failure into a
            # replay.
            raise
        # Brief §3 mandates caller-owned transaction.  When the
        # asyncpg connection is in "transaction aborted" state, a
        # fresh SAVEPOINT cannot succeed.  The post-failure
        # SAVEPOINT rollback, however, places the connection back
        # at the outer transaction's snapshot — a subsequent
        # plain ``SELECT`` issued without an explicit SAVEPOINT
        # wrapper succeeds because PostgreSQL's MVCC snapshot is
        # already restored to its pre-failure state.  We therefore
        # route the classification read through the caller-owned
        # session WITHOUT wrapping it in ``begin_nested``.
        # When even the bare SELECT fails (the SAVEPOINT itself
        # left the connection in error state), we surface a
        # structured ``ForecastQualityPersistenceError`` so the
        # brief §3 caller-owned-transaction contract holds and
        # we never silently turn a contract failure into a
        # replay.
        try:
            existing = session.scalar(
                select(QualityEvaluationRunModel).where(
                    QualityEvaluationRunModel.evaluation_request_hash
                    == evidence.evaluation_request_hash
                )
            )
        except IntegrityError:
            existing = None
        if existing is None:
            raise ForecastQualityPersistenceError(
                "run UNIQUE race lost but no owning run found"
            ) from exc
        return _classify_existing(session, existing, evidence)

    if run.id is None:
        raise ForecastQualityPersistenceError("database did not assign evaluation run id")
    metric_rows = [
        QualityMetricResultModel(
            quality_evaluation_run_id=run.id,
            schema_version=evidence.persistence_schema_version,
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
            schema_version=evidence.persistence_schema_version,
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
            schema_version=evidence.persistence_schema_version,
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
    comparison_rows = [
        ModelBaselineComparisonModel(
            quality_evaluation_run_id=run.id,
            schema_version=evidence.persistence_schema_version,
            comparison_key_hash=item.key_hash,
            comparison_policy_version=evidence.comparison_policy_version,
            comparison_name=item.result.comparison_name.value,
            comparison_availability=item.result.comparison_availability.value,
            metric_status=item.result.metric_status.value,
            reason_code=item.result.reason_code.value,
            external_blocker=item.result.external_blocker,
            frozen_limitation=item.result.frozen_limitation,
            model_identity=item.result.model_identity,
            baseline_member_identity_set=item.result.baseline_member_identity_set,
            baseline_member_set_hash=item.result.baseline_member_set_hash,
            normalized_breakdown_identity=item.result.normalized_breakdown_identity,
            forecast_horizon_days=item.result.forecast_horizon_days,
            model_value=item.result.model_value,
            baseline_value=item.result.baseline_value,
            delta_value=item.result.delta_value,
            model_input_row_count=item.result.model_input_row_count,
            baseline_input_row_count=item.result.baseline_input_row_count,
            common_comparable_row_count=item.result.common_comparable_row_count,
            model_only_row_count=item.result.model_only_row_count,
            baseline_only_row_count=item.result.baseline_only_row_count,
            excluded_row_count=item.result.excluded_row_count,
            not_computable_row_count=item.result.not_computable_row_count,
            canonical_payload=item.payload,
            canonical_hash=item.canonical_hash,
            created_at=now,
            completed_at=now,
        )
        for item in evidence.comparisons
    ]
    session.add_all([*metric_rows, *breakdown_rows, *baseline_rows])
    # The PostgreSQL comparison trigger validates every baseline member
    # against its owning run.  Make the dependency visible inside the same
    # caller-owned transaction before inserting comparison children.
    session.flush()
    session.add_all(comparison_rows)
    session.flush()
    manifest = QualityEvaluationManifestModel(
        quality_evaluation_run_id=run.id,
        schema_version=evidence.persistence_schema_version,
        evaluation_request_hash=evidence.evaluation_request_hash,
        evaluation_instance_hash=evidence.evaluation_instance_hash,
        metric_result_set_hash=evidence.metric_set_hash,
        breakdown_result_set_hash=evidence.breakdown_set_hash,
        baseline_result_set_hash=evidence.baseline_set_hash,
        comparison_result_set_hash=evidence.comparison_result_set_hash,
        comparison_policy_version=evidence.comparison_policy_version,
        comparison_result_schema_version=evidence.comparison_result_schema_version,
        comparison_result_set_schema_version=evidence.comparison_result_set_schema_version,
        comparison_cell_count=evidence.comparison_cell_count,
        comparison_result_count=len(comparison_rows),
        manifest_payload=evidence.manifest_payload,
        manifest_hash=evidence.manifest_hash,
        created_at=now,
        completed_at=now,
        sealed_at=now,
    )
    # Brief §12/§13 — manifest UNIQUE race classification.
    # Wrap the manifest INSERT in a SAVEPOINT so we can roll back only
    # this statement if the DB rejects it with SQLSTATE=23505 +
    # constraint_name=uq_quality_manifest_run.  A concurrent writer
    # may have committed a manifest for the same run between our
    # run SELECT and our manifest INSERT.  Any other SQLSTATE or
    # constraint_name propagates verbatim — we never translate a
    # contract failure into a replay.
    try:
        with session.begin_nested():
            session.add(manifest)
            session.flush()
    except IntegrityError as exc:
        # Brief §5.3 — same fail-closed extraction as the run
        # INSERT path.  Unknown adapter shape or missing
        # sqlstate/constraint_name propagates verbatim.
        orig = getattr(exc, "orig", None)
        manifest_sqlstate: str | None = None
        if orig is not None and hasattr(orig, "sqlstate"):
            manifest_sqlstate = getattr(orig, "sqlstate", None)
        manifest_constraint_name: str | None = None
        if orig is not None and hasattr(orig, "constraint_name"):
            manifest_constraint_name = getattr(orig, "constraint_name", None)
        if manifest_sqlstate is None or manifest_constraint_name is None:
            msg = str(exc)
            import re

            sql_match = re.search(r"SQLSTATE (\d{5})", msg)
            if manifest_sqlstate is None and sql_match is not None:
                manifest_sqlstate = sql_match.group(1)
            cstr_match = re.search(
                r'duplicate key value violates unique constraint "([^"]+)"',
                msg,
            )
            if manifest_constraint_name is None and cstr_match is not None:
                manifest_constraint_name = cstr_match.group(1)
        if manifest_sqlstate is None or manifest_constraint_name is None:
            raise
        if manifest_sqlstate != "23505" or manifest_constraint_name != "uq_quality_manifest_run":
            # Brief §5.2 — manifest INSERT may ONLY classify
            # ``uq_quality_manifest_run``.  All other SQLSTATEs
            # (including other UNIQUE constraints, CHECK, FK,
            # trigger) propagate verbatim — we never translate
            # a contract failure into a replay.
            raise
        # Concurrent winner already sealed the manifest.
        # Brief §3 mandates caller-owned transaction; we look up
        # the existing run via the caller-owned session WITHOUT
        # wrapping the read in ``begin_nested`` (asyncpg leaves
        # the connection in error state, but a plain ``SELECT``
        # after SAVEPOINT rollback operates on the outer
        # transaction's restored snapshot).
        try:
            existing = session.scalar(
                select(QualityEvaluationRunModel).where(
                    QualityEvaluationRunModel.evaluation_request_hash
                    == evidence.evaluation_request_hash
                )
            )
        except IntegrityError:
            existing = None
        if existing is None:
            raise ForecastQualityPersistenceError(
                "manifest UNIQUE race lost but no owning run found"
            ) from exc
        return _classify_existing(session, existing, evidence)
    session.flush()
    return PersistedQualityEvaluation(
        run_id=run.id,
        manifest_id=manifest.id,
        evaluation_request_hash=evidence.evaluation_request_hash,
        evaluation_instance_hash=evidence.evaluation_instance_hash,
        new_write_count=1
        + len(metric_rows)
        + len(breakdown_rows)
        + len(baseline_rows)
        + len(comparison_rows)
        + 1,
        replayed=False,
    )


def persist_quality_evaluation(
    session: Session,
    *,
    evaluation_input: S3EvaluationInput,
    metric_results: Sequence[DailyMetricResult],
    breakdown_results: Sequence[Mapping[str, object]],
    baseline_records: Sequence[BaselinePersistenceRecord],
    comparison_records: Sequence[ComparisonResult | Mapping[str, object]] = (),
    manifest_payload: Mapping[str, object],
    comparison_contract_enabled: bool = False,
    request_identity_payload: Mapping[str, object] | None = None,
) -> PersistedQualityEvaluation:
    """Persist one complete result without taking transaction ownership.

    ``comparison_contract_enabled`` declares whether the caller is using V2
    (Round C) persistence.  ``False`` selects V1 persistence and rejects any
    comparison records that may have been passed in by mistake.  ``True``
    selects V2 persistence regardless of whether comparison_records is
    empty (V2 zero-cell branch) or populated with full ten-record cells.
    """
    if not isinstance(session, Session):
        raise TypeError("persist_quality_evaluation requires a synchronous SQLAlchemy Session")
    if not isinstance(manifest_payload, Mapping):
        raise ForecastQualityContractError("manifest_payload must be a mapping")
    evidence = _build_evidence(
        evaluation_input=evaluation_input,
        metric_results=metric_results,
        breakdown_results=breakdown_results,
        baseline_records=baseline_records,
        comparison_records=comparison_records,
        manifest_payload=manifest_payload,
        comparison_contract_enabled=comparison_contract_enabled,
        request_identity_payload=request_identity_payload,
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
    "COMPARISON_POLICY_VERSION",
    "COMPARISON_RESULT_SCHEMA_VERSION",
    "COMPARISON_RESULT_SET_SCHEMA_VERSION",
    "COMPARISON_RESULT_SET_HASH",
    "ComparisonResult",
    "ForecastQualityConflictError",
    "ForecastQualityContractError",
    "ForecastQualityPartialResultError",
    "ForecastQualityPersistenceError",
    "PersistedQualityEvaluation",
    "PersistedQualityEvaluationReadModel",
    "ROUND_C_PERSISTENCE_SCHEMA_VERSION",
    "load_quality_evaluation_by_instance_hash",
    "persist_quality_evaluation",
]
