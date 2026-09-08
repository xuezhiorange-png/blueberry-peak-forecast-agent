"""Candidate 01 manifest, preflight, and append-only validation ledger.

This module owns the small amount of S4-C01 control-plane machinery that is
safe to run before a candidate has a lawful paired validation authority.  It
does not read TEST, derive labels, synthesize forecasts, or silently turn a
missing historical incumbent authority into an executable comparison.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, Literal, cast

from backend.app.maturity.config import (
    CurveRules,
    ForecastRules,
    HolidayRules,
    IntervalRules,
    MaturityCurveConfig,
    MaturityCurveRules,
    OffsetRules,
    PoolingRules,
    load_maturity_curve_config,
)
from backend.app.rolling_backtest.canonical import canonical_json_dumps, sha256_payload
from backend.app.s4_experiment import (
    EXPERIMENT_PLAN_VERSION,
    FROZEN_CANDIDATE_REGISTRY,
    GUARDRAIL_POLICY_HASH,
    GUARDRAIL_POLICY_VERSION,
    METRIC_CONTRACT_VERSION,
    S4_A_EXPERIMENT_PLAN_HASH_BOUND,
    CandidateExecutionGateRequest,
    check_candidate_execution_gate,
)

CANDIDATE_01_ID: Final[str] = "01_parameter_calibration"
CANDIDATE_01_FAMILY: Final[str] = "PARAMETER_CALIBRATION"
CANDIDATE_01_PARENT_MODEL_ID: Final[str] = "V0_2_CURRENT_MODEL"
CANDIDATE_01_HYPOTHESIS: Final[str] = (
    "parameter_calibration_reduces_primary_metric_without_guardrail_regression"
)
CANDIDATE_01_PARAMETER_MANIFEST_VERSION: Final[str] = (
    "v0.3-s4-c01-parameter-manifest-v1"
)
CANDIDATE_01_ALLOWED_PARAMETER_PATHS: Final[tuple[str, ...]] = (
    "curve.spline_knot_count",
    "curve.ridge_alpha",
)
CANDIDATE_01_RANDOM_SEED: Final[int] = 20260624
CANDIDATE_01_PLANNED_RUN_COUNT: Final[int] = 4
INCUMBENT_CONFIG_PATH: Final[str] = "configs/maturity_curve.yaml"
VALIDATION_LEDGER_SCHEMA_VERSION: Final[str] = "v0.3-s4-validation-ledger-v1"
VALIDATION_EVENT_SCHEMA_VERSION: Final[str] = "v0.3-s4-validation-event-v1"
HISTORICAL_INCUMBENT_AUTHORITY_REASON: Final[str] = (
    "HISTORICAL_INCUMBENT_DAILY_FORECAST_AUTHORITY_NOT_DURABLY_RETAINED"
)
NO_VERSIONED_FORECAST_AUTHORITY_REASON: Final[str] = (
    "NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT"
)

_SHA256_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
_LEDGER_EVENT_TYPES: Final[frozenset[str]] = frozenset(
    {"EVALUATION_STARTED", "EVALUATION_TERMINAL"}
)
_TERMINAL_EXECUTION_STATUSES: Final[frozenset[str]] = frozenset(
    {"COMPLETED", "FAILED", "ABORTED", "CANCELLED", "TIMEOUT", "BLOCKED"}
)
_LEDGER_FIELDS: Final[tuple[str, ...]] = (
    "evaluation_id",
    "experiment_plan_version",
    "candidate_id",
    "candidate_run_ordinal",
    "global_evaluation_ordinal",
    "invocation_type",
    "trigger_source",
    "started_at",
    "finished_at",
    "execution_status",
    "metric_result_status",
    "dataset_hash",
    "validation_split_hash",
    "code_commit_sha",
    "parameter_manifest_hash",
    "random_seed",
    "retry_of_evaluation_id",
    "counted_toward_budget",
    "budget_count_reason",
)


class Candidate01ContractError(ValueError):
    """Sanitized S4-C01 contract failure."""

    reason_code = "CANDIDATE_01_CONTRACT_ERROR"


class Candidate01PreflightBlocked(Candidate01ContractError):
    """Raised when no lawful candidate evaluation may be started."""

    reason_code = "CANDIDATE_01_EXECUTION_PREFLIGHT_BLOCKED"


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _decimalize(value: object) -> object:
    """Convert YAML float scalars to Decimal without admitting native floats."""

    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise Candidate01ContractError("non-finite configuration value")
        return value
    if isinstance(value, Mapping):
        return {str(key): _decimalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decimalize(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_decimalize(item) for item in value)
    return value


def _contains_native_float(value: object) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, Mapping):
        return any(_contains_native_float(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_native_float(item) for item in value)
    return False


def _path_value(payload: Mapping[str, Any], dotted_path: str) -> object:
    current: object = payload
    for segment in dotted_path.split("."):
        if not isinstance(current, Mapping) or segment not in current:
            raise Candidate01ContractError("parameter path is missing")
        current = current[segment]
    return current


def _set_path(payload: dict[str, Any], dotted_path: str, value: object) -> None:
    segments = dotted_path.split(".")
    current = payload
    for segment in segments[:-1]:
        child = current.get(segment)
        if not isinstance(child, dict):
            raise Candidate01ContractError("parameter path is not an object")
        current = child
    current[segments[-1]] = value


def _flatten_paths(value: object, prefix: str = "") -> dict[str, object]:
    if isinstance(value, Mapping):
        flattened: dict[str, object] = {}
        for key in sorted(value):
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            flattened.update(_flatten_paths(value[key], child_prefix))
        return flattened
    return {prefix: value}


@dataclass(frozen=True, slots=True)
class ParameterDiffResult:
    changed_paths: tuple[str, ...]
    unauthorized_paths: tuple[str, ...]
    native_float_present: bool

    @property
    def unauthorized_parameter_diff_count(self) -> int:
        return len(self.unauthorized_paths)


def verify_parameter_allowlist(
    *,
    incumbent_snapshot: Mapping[str, Any],
    candidate_snapshot: Mapping[str, Any],
    allowed_paths: tuple[str, ...] = CANDIDATE_01_ALLOWED_PARAMETER_PATHS,
) -> ParameterDiffResult:
    """Verify that a candidate config changes only the approved paths."""

    incumbent = _decimalize(incumbent_snapshot)
    candidate = _decimalize(candidate_snapshot)
    if not isinstance(incumbent, Mapping) or not isinstance(candidate, Mapping):
        raise Candidate01ContractError("configuration snapshots must be mappings")
    incumbent_flat = _flatten_paths(incumbent)
    candidate_flat = _flatten_paths(candidate)
    all_paths = sorted(set(incumbent_flat) | set(candidate_flat))
    changed = tuple(
        path
        for path in all_paths
        if incumbent_flat.get(path) != candidate_flat.get(path)
    )
    allowed = set(allowed_paths)
    unauthorized = tuple(path for path in changed if path not in allowed)
    return ParameterDiffResult(
        changed_paths=changed,
        unauthorized_paths=unauthorized,
        native_float_present=_contains_native_float(incumbent_snapshot)
        or _contains_native_float(candidate_snapshot),
    )


@dataclass(frozen=True, slots=True)
class CandidateRunDefinition:
    candidate_run_ordinal: int
    parameter_delta: tuple[tuple[str, object], ...]
    full_parameter_snapshot: Mapping[str, Any]
    authorized_parameter_delta: Mapping[str, Any]
    parameter_manifest_hash: str
    candidate_config_hash: str
    incumbent_config_hash: str
    random_seed: int
    unauthorized_parameter_diff_count: int

    def payload(self) -> dict[str, Any]:
        return {
            "candidate_id": CANDIDATE_01_ID,
            "candidate_run_ordinal": self.candidate_run_ordinal,
            "parent_model_id": CANDIDATE_01_PARENT_MODEL_ID,
            "full_parameter_snapshot": copy.deepcopy(dict(self.full_parameter_snapshot)),
            "authorized_parameter_delta": copy.deepcopy(dict(self.authorized_parameter_delta)),
            "parameter_manifest_hash": self.parameter_manifest_hash,
            "candidate_config_hash": self.candidate_config_hash,
            "incumbent_config_hash": self.incumbent_config_hash,
            "random_seed": self.random_seed,
            "unauthorized_parameter_diff_count": self.unauthorized_parameter_diff_count,
        }


@dataclass(frozen=True, slots=True)
class Candidate01ParameterManifest:
    version: str
    candidate_id: str
    candidate_family: str
    parent_model_id: str
    hypothesis: str
    allowed_parameter_paths: tuple[str, ...]
    incumbent_config_path: str
    incumbent_config_file_sha256: str
    incumbent_config_hash: str
    incumbent_parameter_snapshot: Mapping[str, Any]
    random_seed_policy: str
    planned_run_count: int
    runs: tuple[CandidateRunDefinition, ...]

    def payload(self) -> dict[str, Any]:
        return {
            "candidate_01_parameter_manifest_version": self.version,
            "candidate_id": self.candidate_id,
            "candidate_family": self.candidate_family,
            "parent_model_id": self.parent_model_id,
            "hypothesis": self.hypothesis,
            "allowed_parameter_paths": list(self.allowed_parameter_paths),
            "incumbent_config_path": self.incumbent_config_path,
            "incumbent_config_file_sha256": self.incumbent_config_file_sha256,
            "incumbent_config_hash": self.incumbent_config_hash,
            "incumbent_parameter_snapshot": copy.deepcopy(
                dict(self.incumbent_parameter_snapshot)
            ),
            "random_seed_policy": self.random_seed_policy,
            "planned_run_count": self.planned_run_count,
            "runs": [run.payload() for run in self.runs],
            "native_float_allowed": False,
            "adaptive_search_allowed": False,
            "post_validation_parameter_substitution_allowed": False,
            "candidate_01_only": True,
        }

    @property
    def manifest_hash(self) -> str:
        return sha256_payload(self.payload())

    def run(self, ordinal: int) -> CandidateRunDefinition:
        for run in self.runs:
            if run.candidate_run_ordinal == ordinal:
                return run
        raise Candidate01ContractError("candidate run ordinal is not in the frozen manifest")


def _validate_incumbent_values(config: MaturityCurveConfig) -> None:
    expected: tuple[tuple[str, object], ...] = (
        ("model_family", "shared_spline_partial_pooling"),
        ("random_seed", CANDIDATE_01_RANDOM_SEED),
        ("curve.spline_degree", 3),
        ("curve.spline_knot_count", 6),
        ("curve.ridge_alpha", Decimal("0.10")),
        ("pooling.full_pooling_sample_target", 4),
    )
    snapshot = _decimalize(config.snapshot)
    if not isinstance(snapshot, Mapping):
        raise Candidate01ContractError("incumbent config snapshot is not a mapping")
    for path, expected_value in expected:
        if _path_value(snapshot, path) != expected_value:
            raise Candidate01ContractError("incumbent config authority mismatch")


def _candidate_config_hash(snapshot: Mapping[str, Any]) -> str:
    return sha256_payload(_decimalize(snapshot))


def _run_manifest_hash(
    *,
    ordinal: int,
    parameter_delta: Mapping[str, Any],
    full_snapshot: Mapping[str, Any],
    incumbent_config_hash: str,
) -> str:
    return sha256_payload(
        {
            "manifest_version": CANDIDATE_01_PARAMETER_MANIFEST_VERSION,
            "candidate_id": CANDIDATE_01_ID,
            "candidate_run_ordinal": ordinal,
            "parent_model_id": CANDIDATE_01_PARENT_MODEL_ID,
            "full_parameter_snapshot": full_snapshot,
            "authorized_parameter_delta": parameter_delta,
            "incumbent_config_hash": incumbent_config_hash,
            "random_seed": CANDIDATE_01_RANDOM_SEED,
        }
    )


def build_candidate_01_manifest(
    config_path: Path,
) -> Candidate01ParameterManifest:
    """Load current incumbent config and freeze the exact four-run neighborhood."""

    if not config_path.is_file():
        raise Candidate01ContractError("incumbent config file is unavailable")
    config = load_maturity_curve_config(config_path)
    _validate_incumbent_values(config)
    snapshot = _decimalize(config.snapshot)
    if not isinstance(snapshot, Mapping):
        raise Candidate01ContractError("incumbent config snapshot is invalid")
    incumbent_snapshot = cast(dict[str, Any], copy.deepcopy(dict(snapshot)))
    run_deltas: tuple[tuple[tuple[str, object], ...], ...] = (
        (("curve.spline_knot_count", 5), ("curve.ridge_alpha", Decimal("0.10"))),
        (("curve.spline_knot_count", 7), ("curve.ridge_alpha", Decimal("0.10"))),
        (("curve.spline_knot_count", 6), ("curve.ridge_alpha", Decimal("0.05"))),
        (("curve.spline_knot_count", 6), ("curve.ridge_alpha", Decimal("0.20"))),
    )
    runs: list[CandidateRunDefinition] = []
    for ordinal, delta_items in enumerate(run_deltas, start=1):
        candidate_snapshot = copy.deepcopy(incumbent_snapshot)
        parameter_delta = dict(delta_items)
        for path, value in delta_items:
            _set_path(candidate_snapshot, path, value)
        diff = verify_parameter_allowlist(
            incumbent_snapshot=incumbent_snapshot,
            candidate_snapshot=candidate_snapshot,
        )
        if diff.native_float_present or diff.unauthorized_parameter_diff_count:
            raise Candidate01ContractError("candidate config violates parameter allowlist")
        candidate_hash = _candidate_config_hash(candidate_snapshot)
        run_hash = _run_manifest_hash(
            ordinal=ordinal,
            parameter_delta=parameter_delta,
            full_snapshot=candidate_snapshot,
            incumbent_config_hash=config.config_hash,
        )
        runs.append(
            CandidateRunDefinition(
                candidate_run_ordinal=ordinal,
                parameter_delta=tuple(delta_items),
                full_parameter_snapshot=candidate_snapshot,
                authorized_parameter_delta=parameter_delta,
                parameter_manifest_hash=run_hash,
                candidate_config_hash=candidate_hash,
                incumbent_config_hash=config.config_hash,
                random_seed=CANDIDATE_01_RANDOM_SEED,
                unauthorized_parameter_diff_count=diff.unauthorized_parameter_diff_count,
            )
        )
    manifest = Candidate01ParameterManifest(
        version=CANDIDATE_01_PARAMETER_MANIFEST_VERSION,
        candidate_id=CANDIDATE_01_ID,
        candidate_family=CANDIDATE_01_FAMILY,
        parent_model_id=CANDIDATE_01_PARENT_MODEL_ID,
        hypothesis=CANDIDATE_01_HYPOTHESIS,
        allowed_parameter_paths=CANDIDATE_01_ALLOWED_PARAMETER_PATHS,
        incumbent_config_path=INCUMBENT_CONFIG_PATH,
        incumbent_config_file_sha256=_file_sha256(config_path),
        incumbent_config_hash=config.config_hash,
        incumbent_parameter_snapshot=incumbent_snapshot,
        random_seed_policy="FIXED_AND_RECORDED_PER_RUN",
        planned_run_count=CANDIDATE_01_PLANNED_RUN_COUNT,
        runs=tuple(runs),
    )
    validate_candidate_01_manifest(manifest)
    return manifest


def validate_candidate_01_manifest(manifest: Candidate01ParameterManifest) -> None:
    """Reject post-freeze insertion, reordering, or unauthorized run drift."""

    if manifest.version != CANDIDATE_01_PARAMETER_MANIFEST_VERSION:
        raise Candidate01ContractError("candidate manifest version mismatch")
    if manifest.candidate_id != CANDIDATE_01_ID:
        raise Candidate01ContractError("candidate manifest candidate mismatch")
    if manifest.candidate_family != CANDIDATE_01_FAMILY:
        raise Candidate01ContractError("candidate manifest family mismatch")
    if manifest.parent_model_id != CANDIDATE_01_PARENT_MODEL_ID:
        raise Candidate01ContractError("candidate manifest parent mismatch")
    if manifest.allowed_parameter_paths != CANDIDATE_01_ALLOWED_PARAMETER_PATHS:
        raise Candidate01ContractError("candidate allowlist mismatch")
    if manifest.planned_run_count != CANDIDATE_01_PLANNED_RUN_COUNT:
        raise Candidate01ContractError("candidate planned run count mismatch")
    ordinals = tuple(run.candidate_run_ordinal for run in manifest.runs)
    if ordinals != (1, 2, 3, 4):
        raise Candidate01ContractError("candidate run order is not frozen")
    for run in manifest.runs:
        diff = verify_parameter_allowlist(
            incumbent_snapshot=manifest.incumbent_parameter_snapshot,
            candidate_snapshot=run.full_parameter_snapshot,
        )
        if diff.native_float_present or diff.unauthorized_parameter_diff_count != 0:
            raise Candidate01ContractError("candidate config violates parameter allowlist")
        if run.unauthorized_parameter_diff_count != 0:
            raise Candidate01ContractError("candidate run contains unauthorized diff")


def _config_from_snapshot(
    snapshot: Mapping[str, Any],
    *,
    config_hash: str,
) -> MaturityCurveConfig:
    """Build a validated Task 8 config object without changing the repo YAML."""

    def value(path: str) -> object:
        return _path_value(snapshot, path)

    def integer(path: str) -> int:
        raw = value(path)
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise Candidate01ContractError("integer configuration value is invalid")
        return raw

    return MaturityCurveConfig(
        rules=MaturityCurveRules(
            curve=CurveRules(
                version=cast(str, value("curve.version")),
                support_min_day=integer("curve.support_min_day"),
                support_max_day=integer("curve.support_max_day"),
                spline_degree=integer("curve.spline_degree"),
                spline_knot_count=integer("curve.spline_knot_count"),
                ridge_alpha=cast(Decimal, value("curve.ridge_alpha")),
            ),
            pooling=PoolingRules(
                minimum_samples=integer("pooling.minimum_samples"),
                minimum_seasons=integer("pooling.minimum_seasons"),
                minimum_farms=integer("pooling.minimum_farms"),
                minimum_subfarms=integer("pooling.minimum_subfarms"),
                full_pooling_sample_target=integer("pooling.full_pooling_sample_target"),
            ),
            offset=OffsetRules(
                maximum_abs_shift_days=cast(Decimal, value("offset.maximum_abs_shift_days")),
                minimum_training_samples=integer("offset.minimum_training_samples"),
            ),
            holidays=HolidayRules(
                spring_festival_codes=tuple(
                    cast(list[str], value("holidays.spring_festival_codes"))
                ),
                disturbance_weight=cast(Decimal, value("holidays.disturbance_weight")),
                exclude_from_loss=bool(value("holidays.exclude_from_loss")),
            ),
            intervals=IntervalRules(
                p80_quantile=cast(Decimal, value("intervals.p80_quantile")),
                p90_quantile=cast(Decimal, value("intervals.p90_quantile")),
                calendar_proxy_widening_factor=cast(
                    Decimal, value("intervals.calendar_proxy_widening_factor")
                ),
                uncalibrated_widening_factor=cast(
                    Decimal, value("intervals.uncalibrated_widening_factor")
                ),
            ),
            forecast=ForecastRules(
                p50_mass_tolerance_kg=cast(Decimal, value("forecast.p50_mass_tolerance_kg")),
                observed_phase_adjustment_max_days=cast(
                    Decimal, value("forecast.observed_phase_adjustment_max_days")
                ),
                minimum_observed_axis_coverage_ratio=cast(
                    Decimal, value("forecast.minimum_observed_axis_coverage_ratio")
                ),
            ),
            random_seed=integer("random_seed"),
            model_family=cast(Literal["shared_spline_partial_pooling"], value("model_family")),
        ),
        config_hash=config_hash,
        snapshot=copy.deepcopy(dict(snapshot)),
    )


def build_derived_candidate_config(
    manifest: Candidate01ParameterManifest,
    candidate_run_ordinal: int,
) -> tuple[CandidateRunDefinition, MaturityCurveConfig]:
    run = manifest.run(candidate_run_ordinal)
    diff = verify_parameter_allowlist(
        incumbent_snapshot=manifest.incumbent_parameter_snapshot,
        candidate_snapshot=run.full_parameter_snapshot,
    )
    if diff.native_float_present or diff.unauthorized_parameter_diff_count != 0:
        raise Candidate01ContractError("candidate config drift detected")
    if run.unauthorized_parameter_diff_count != 0:
        raise Candidate01ContractError("candidate manifest contains unauthorized diff")
    return run, _config_from_snapshot(
        run.full_parameter_snapshot,
        config_hash=run.candidate_config_hash,
    )


@dataclass(frozen=True, slots=True)
class PairingIdentityBinding:
    name: str
    identity: str
    source_path: str


@dataclass(frozen=True, slots=True)
class PairingAuthorityResolution:
    status: Literal["RESOLVED", "BLOCKED"]
    bindings: tuple[PairingIdentityBinding, ...]
    blocker: str | None
    reason_code: str | None
    first_non_derivable_authority: str | None

    @property
    def resolved(self) -> bool:
        return self.status == "RESOLVED"


_REQUIRED_PAIRING_IDENTITY_NAMES: Final[tuple[str, ...]] = (
    "train_dataset_identity",
    "validation_dataset_identity",
    "actual_label_set_identity",
    "exclusion_policy_identity",
    "cutoff_policy_identity",
    "forecast_horizon_set_identity",
    "metric_contract_identity",
    "business_grain_set_identity",
    "common_comparable_set_identity",
)


def resolve_pairing_authority(repo_root: Path) -> PairingAuthorityResolution:
    """Resolve only durable authorities; never manufacture an identity hash."""

    closeout_path = repo_root / (
        "docs/v0-3/s3/evidence/"
        "s3-final-closeout-and-s4-entry-authorization-r1.json"
    )
    if not closeout_path.is_file():
        return PairingAuthorityResolution(
            "BLOCKED",
            (),
            "S3_CLOSEOUT_AUTHORITY_UNAVAILABLE",
            "S3_CLOSEOUT_AUTHORITY_UNAVAILABLE",
            "S3_FINAL_CLOSEOUT_EVIDENCE",
        )
    try:
        closeout = json.loads(closeout_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return PairingAuthorityResolution(
            "BLOCKED",
            (),
            "S3_CLOSEOUT_AUTHORITY_INVALID",
            "S3_CLOSEOUT_AUTHORITY_INVALID",
            "S3_FINAL_CLOSEOUT_EVIDENCE",
        )
    historical = closeout.get("HISTORICAL_S3_EVALUATION", {})
    historical_available = historical.get(
        "HISTORICAL_INCUMBENT_FORECAST_DAILY_AUTHORITY_AVAILABLE"
    )
    if historical_available is False:
        return PairingAuthorityResolution(
            "BLOCKED",
            (),
            HISTORICAL_INCUMBENT_AUTHORITY_REASON,
            HISTORICAL_INCUMBENT_AUTHORITY_REASON,
            "HISTORICAL_INCUMBENT_DAILY_FORECAST_AUTHORITY",
        )
    if closeout.get("HISTORICAL_PIT_NOT_COMPUTABLE") is True:
        return PairingAuthorityResolution(
            "BLOCKED",
            (),
            HISTORICAL_INCUMBENT_AUTHORITY_REASON,
            HISTORICAL_INCUMBENT_AUTHORITY_REASON,
            "HISTORICAL_INCUMBENT_DAILY_FORECAST_AUTHORITY",
        )
    return PairingAuthorityResolution(
        "BLOCKED",
        (),
        NO_VERSIONED_FORECAST_AUTHORITY_REASON,
        NO_VERSIONED_FORECAST_AUTHORITY_REASON,
        "VERSIONED_INCUMBENT_FORECAST_ARTIFACT",
    )


@dataclass(frozen=True, slots=True)
class LedgerEvent:
    event_type: str
    event_payload: Mapping[str, Any]
    event_hash: str

    def record(self) -> dict[str, Any]:
        return {
            "schema_version": VALIDATION_EVENT_SCHEMA_VERSION,
            "event_type": self.event_type,
            "event_payload": copy.deepcopy(dict(self.event_payload)),
            "event_hash": self.event_hash,
        }


def _event_hash(event_type: str, payload: Mapping[str, Any]) -> str:
    return sha256_payload({"event_type": event_type, "event_payload": payload})


def _validate_ledger_payload(payload: Mapping[str, Any]) -> None:
    if set(payload) != set(_LEDGER_FIELDS):
        raise Candidate01ContractError("ledger payload fields do not match frozen schema")
    if not isinstance(payload["evaluation_id"], str) or not payload["evaluation_id"]:
        raise Candidate01ContractError("evaluation identity is missing")
    if payload["invocation_type"] != "NORMAL_RUN":
        raise Candidate01ContractError("retry invocation is not authorized for Candidate 01")
    if payload["counted_toward_budget"] is not True:
        raise Candidate01ContractError("started invocation must count toward budget")
    if payload["budget_count_reason"] != "STARTED_INVOCATION":
        raise Candidate01ContractError("started invocation budget reason is invalid")
    try:
        canonical_json_dumps(payload)
    except (TypeError, ValueError) as exc:
        raise Candidate01ContractError("ledger payload is not canonical") from exc


class AppendOnlyValidationJournal:
    """Append-only JSONL event journal with deterministic materialization."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def _read_events(self) -> list[LedgerEvent]:
        if not self.path.exists():
            return []
        events: list[LedgerEvent] = []
        seen_event_keys: set[tuple[str, str]] = set()
        for raw_line in self.path.read_text(encoding="utf-8").splitlines():
            if not raw_line.strip():
                continue
            try:
                record = json.loads(raw_line)
                if record.get("schema_version") != VALIDATION_EVENT_SCHEMA_VERSION:
                    raise Candidate01ContractError("ledger event schema mismatch")
                event_type = record["event_type"]
                payload = record["event_payload"]
                event_hash = record["event_hash"]
                if event_type not in _LEDGER_EVENT_TYPES or not isinstance(payload, dict):
                    raise Candidate01ContractError("ledger event shape is invalid")
                if event_hash != _event_hash(event_type, payload):
                    raise Candidate01ContractError("ledger event hash mismatch")
                evaluation_id = payload.get("evaluation_id")
                if not isinstance(evaluation_id, str):
                    raise Candidate01ContractError("duplicate ledger event")
                key = (event_type, evaluation_id)
                if key in seen_event_keys:
                    raise Candidate01ContractError("duplicate ledger event")
                seen_event_keys.add(key)
                events.append(LedgerEvent(event_type, payload, event_hash))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                if isinstance(exc, Candidate01ContractError):
                    raise
                raise Candidate01ContractError("ledger event is invalid") from exc
        return events

    def _append(self, event_type: str, payload: Mapping[str, Any]) -> LedgerEvent:
        if event_type not in _LEDGER_EVENT_TYPES:
            raise Candidate01ContractError("unsupported ledger event type")
        canonical_payload = cast(
            dict[str, Any], json.loads(canonical_json_dumps(dict(payload)))
        )
        event = LedgerEvent(
            event_type,
            canonical_payload,
            _event_hash(event_type, canonical_payload),
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(canonical_json_dumps({
                "schema_version": VALIDATION_EVENT_SCHEMA_VERSION,
                "event_type": event.event_type,
                "event_payload": event.event_payload,
                "event_hash": event.event_hash,
            }))
            file.write("\n")
        return event

    def append_started(self, payload: Mapping[str, Any]) -> LedgerEvent:
        _validate_ledger_payload(payload)
        events = self._read_events()
        evaluation_id = cast(str, payload["evaluation_id"])
        if any(
            event.event_payload.get("evaluation_id") == evaluation_id
            for event in events
        ):
            raise Candidate01ContractError("evaluation identity reuse is forbidden")
        return self._append("EVALUATION_STARTED", payload)

    def append_terminal(
        self,
        *,
        evaluation_id: str,
        finished_at: str,
        execution_status: str,
        metric_result_status: str,
    ) -> LedgerEvent:
        events = self._read_events()
        started = [
            event for event in events
            if event.event_type == "EVALUATION_STARTED"
            and event.event_payload.get("evaluation_id") == evaluation_id
        ]
        if len(started) != 1:
            raise Candidate01ContractError("terminal event has no unique started event")
        if any(
            event.event_type == "EVALUATION_TERMINAL"
            and event.event_payload.get("evaluation_id") == evaluation_id
            for event in events
        ):
            raise Candidate01ContractError("terminal event already exists")
        if execution_status not in _TERMINAL_EXECUTION_STATUSES:
            raise Candidate01ContractError("invalid terminal execution status")
        payload = {
            "evaluation_id": evaluation_id,
            "finished_at": finished_at,
            "execution_status": execution_status,
            "metric_result_status": metric_result_status,
        }
        return self._append("EVALUATION_TERMINAL", payload)

    def materialize(self) -> tuple[dict[str, Any], ...]:
        events = self._read_events()
        starts: dict[str, dict[str, Any]] = {}
        terminals: dict[str, Mapping[str, Any]] = {}
        for event in events:
            evaluation_id = cast(str, event.event_payload["evaluation_id"])
            if event.event_type == "EVALUATION_STARTED":
                if evaluation_id in starts:
                    raise Candidate01ContractError("duplicate started event")
                payload = dict(event.event_payload)
                _validate_ledger_payload(payload)
                starts[evaluation_id] = payload
            else:
                if evaluation_id in terminals:
                    raise Candidate01ContractError("duplicate terminal event")
                terminals[evaluation_id] = event.event_payload
        rows: list[dict[str, Any]] = []
        for evaluation_id, started in starts.items():
            row = dict(started)
            terminal = terminals.get(evaluation_id)
            if terminal is not None:
                row["finished_at"] = terminal["finished_at"]
                row["execution_status"] = terminal["execution_status"]
                row["metric_result_status"] = terminal["metric_result_status"]
            rows.append(row)
        rows.sort(key=lambda row: (int(row["global_evaluation_ordinal"]), row["evaluation_id"]))
        return tuple(rows)


@dataclass(frozen=True, slots=True)
class Candidate01PreflightResult:
    status: Literal["PASS", "BLOCKED"]
    blocker: str | None
    reason_code: str | None
    first_non_derivable_authority: str | None
    manifest_hash: str
    current_ledger_row_count: int
    actual_validation_evaluation_count: int


def candidate_01_execution_preflight(
    *,
    repo_root: Path,
    manifest: Candidate01ParameterManifest,
    journal: AppendOnlyValidationJournal,
) -> Candidate01PreflightResult:
    rows = journal.materialize()
    count = len(rows)
    if count > 0:
        return Candidate01PreflightResult(
            "BLOCKED",
            "CANDIDATE_01_ALREADY_STARTED",
            "CANDIDATE_01_ALREADY_STARTED",
            "CANDIDATE_01_LEDGER_ALREADY_CONSUMED",
            manifest.manifest_hash,
            count,
            count,
        )
    pairing = resolve_pairing_authority(repo_root)
    if not pairing.resolved:
        return Candidate01PreflightResult(
            "BLOCKED",
            pairing.blocker,
            pairing.reason_code,
            pairing.first_non_derivable_authority,
            manifest.manifest_hash,
            0,
            0,
        )
    raise Candidate01PreflightBlocked("candidate execution adapter must be explicit")


def build_candidate_gate_request(
    *,
    manifest: Candidate01ParameterManifest,
    run: CandidateRunDefinition,
    pairing_bindings: Mapping[str, str],
    candidate_actual_run_count: int,
    global_actual_evaluation_count: int,
    code_commit_sha: str,
    evaluation_id: str,
) -> CandidateExecutionGateRequest:
    missing = [
        name for name in _REQUIRED_PAIRING_IDENTITY_NAMES if name not in pairing_bindings
    ]
    if missing:
        raise Candidate01PreflightBlocked("paired identity is missing")
    registration = next(
        item for item in FROZEN_CANDIDATE_REGISTRY if item.candidate_id == CANDIDATE_01_ID
    )
    request = CandidateExecutionGateRequest(
        experiment_plan_version=EXPERIMENT_PLAN_VERSION,
        experiment_plan_hash=S4_A_EXPERIMENT_PLAN_HASH_BOUND,
        guardrail_policy_version=GUARDRAIL_POLICY_VERSION,
        guardrail_policy_hash=GUARDRAIL_POLICY_HASH,
        candidate_id=CANDIDATE_01_ID,
        candidate_run_ordinal=run.candidate_run_ordinal,
        candidate_planned_run_count=registration.planned_run_count,
        candidate_actual_run_count=candidate_actual_run_count,
        global_actual_evaluation_count=global_actual_evaluation_count,
        train_dataset_identity=pairing_bindings["train_dataset_identity"],
        validation_dataset_identity=pairing_bindings["validation_dataset_identity"],
        actual_label_set_identity=pairing_bindings["actual_label_set_identity"],
        exclusion_policy_identity=pairing_bindings["exclusion_policy_identity"],
        cutoff_policy_identity=pairing_bindings["cutoff_policy_identity"],
        forecast_horizon_set_identity=pairing_bindings["forecast_horizon_set_identity"],
        metric_contract_identity=pairing_bindings["metric_contract_identity"],
        business_grain_set_identity=pairing_bindings["business_grain_set_identity"],
        common_comparable_set_identity=pairing_bindings["common_comparable_set_identity"],
        metric_contract_version=METRIC_CONTRACT_VERSION,
        test_access_requested=False,
        test_sealed=True,
        parameter_manifest_hash=run.parameter_manifest_hash,
        code_commit_sha=code_commit_sha,
        random_seed=run.random_seed,
        evaluation_id=evaluation_id,
        candidate_execution_manifest_frozen=True,
        candidate_registry=FROZEN_CANDIDATE_REGISTRY,
        policy_payload={
            "candidate_id": CANDIDATE_01_ID,
            "manifest_hash": manifest.manifest_hash,
            "candidate_config_hash": run.candidate_config_hash,
        },
    )
    result = check_candidate_execution_gate(request)
    if not result.allowed:
        raise Candidate01PreflightBlocked(result.reason_codes[0])
    return request


def json_payload(value: object) -> str:
    """Expose canonical JSON for docs/tests without admitting native floats."""

    return canonical_json_dumps(value)


__all__ = [
    "AppendOnlyValidationJournal",
    "CANDIDATE_01_ALLOWED_PARAMETER_PATHS",
    "CANDIDATE_01_FAMILY",
    "CANDIDATE_01_HYPOTHESIS",
    "CANDIDATE_01_ID",
    "CANDIDATE_01_PARAMETER_MANIFEST_VERSION",
    "CANDIDATE_01_PARENT_MODEL_ID",
    "CANDIDATE_01_PLANNED_RUN_COUNT",
    "CANDIDATE_01_RANDOM_SEED",
    "Candidate01ContractError",
    "Candidate01ParameterManifest",
    "Candidate01PreflightBlocked",
    "Candidate01PreflightResult",
    "CandidateRunDefinition",
    "LedgerEvent",
    "NO_VERSIONED_FORECAST_AUTHORITY_REASON",
    "HISTORICAL_INCUMBENT_AUTHORITY_REASON",
    "PairingAuthorityResolution",
    "PairingIdentityBinding",
    "ParameterDiffResult",
    "VALIDATION_EVENT_SCHEMA_VERSION",
    "VALIDATION_LEDGER_SCHEMA_VERSION",
    "build_candidate_01_manifest",
    "build_candidate_gate_request",
    "build_derived_candidate_config",
    "candidate_01_execution_preflight",
    "json_payload",
    "resolve_pairing_authority",
    "validate_candidate_01_manifest",
    "verify_parameter_allowlist",
]
