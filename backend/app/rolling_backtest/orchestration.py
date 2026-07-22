"""Rolling backtest orchestration: Foundation contract definitions.

Phase 3 Foundation contracts — stage enums, blocker codes, DAG topology,
outcome dataclasses, date/time authority helpers, and diagnostics utilities.
No executable orchestration; execution surface removed in TASK-011 cleanup.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo

from backend.app.rolling_backtest.canonical import canonical_json_value, sha256_payload
from backend.app.rolling_backtest.enums import (
    AvailabilitySourceType,
)
from backend.app.rolling_backtest.persistence import (
    DagPersistenceCommand,
)
from backend.app.rolling_backtest.resolution import (
    HistoricalCandidate,
    ResolutionResult,
)
from backend.app.rolling_backtest.schemas import (
    PersistentUpstreamReference,
    ResolvedUpstreamSemanticIdentity,
    S2HistoricalBacktestRequest,
    S2HistoricalBindingCandidate,
    S2HistoricalBindingRow,
)

# ── Orchestration stage enum ─────────────────────────────────────────────────


class OrchestrationStage(StrEnum):
    RESOLVE_HISTORICAL_INPUTS = "resolve_historical_inputs"
    VALIDATE_VISIBILITY = "validate_visibility"
    VALIDATE_AUTHORITY_CHAIN = "validate_authority_chain"
    RESOLVE_OR_REPLAY_TASK8 = "resolve_or_replay_task8"
    RESOLVE_OR_REPLAY_TASK9 = "resolve_or_replay_task9"
    RESOLVE_OR_TRAIN_TASK10 = "resolve_or_train_task10"
    EXECUTE_TASK10_PREDICTION = "execute_task10_prediction"
    FINALIZE_ORCHESTRATION_SNAPSHOT = "finalize_orchestration_snapshot"


class OrchestrationBlocker(StrEnum):
    HISTORICAL_SOURCE_NOT_FOUND = "historical_source_not_found"
    HISTORICAL_SOURCE_NOT_VISIBLE = "historical_source_not_visible"
    HISTORICAL_SOURCE_INTEGRITY_FAILURE = "historical_source_integrity_failure"
    AMBIGUOUS_HISTORICAL_CANDIDATE = "ambiguous_historical_candidate"
    PINNED_SOURCE_NOT_FOUND = "pinned_source_not_found"
    PINNED_SOURCE_TYPE_MISMATCH = "pinned_source_type_mismatch"
    PINNED_SOURCE_ROLE_MISMATCH = "pinned_source_role_mismatch"
    PINNED_SOURCE_NOT_VISIBLE = "pinned_source_not_visible"
    PINNED_SOURCE_IDENTITY_MISMATCH = "pinned_source_identity_mismatch"
    PINNED_SOURCE_INTEGRITY_FAILURE = "pinned_source_integrity_failure"
    TASK8_PARENT_AUTHORITY_MISMATCH = "task8_parent_authority_mismatch"
    TASK8_MISSING_ARTIFACT = "task8_missing_artifact"
    TASK8_MISSING_DAILY_PREDICTIONS = "task8_missing_daily_predictions"
    TASK9_TASK8_AUTHORITY_MISMATCH = "task9_task8_authority_mismatch"
    TASK9_REPLAY_INPUT_INCOMPLETE = "task9_replay_input_incomplete"
    TASK9_EXECUTION_BLOCKED = "task9_execution_blocked"
    TASK10_MODEL_NOT_AVAILABLE = "task10_model_not_available"
    TASK10_TASK9_BINDING_MISMATCH = "task10_task9_binding_mismatch"
    TASK10_PREDICTION_BLOCKED = "task10_prediction_blocked"
    TASK10_PREDICTION_SERVICE_FAILURE = "task10_prediction_service_failure"
    FUTURE_SOURCE_LEAKAGE_DETECTED = "future_source_leakage_detected"
    NO_SESSION_CONFIGURED = "no_session_configured"
    PERSISTENCE_FAILURE = "persistence_failure"
    INTEGRITY_RELOAD_FAILED = "rolling_orchestration_integrity_reload_failed"
    TASK9_REUSE_INTEGRITY_FAILED = "task9_reuse_integrity_failed"

    # ── Phase 3.1 replay blocker taxonomy (frozen amendment §7) ────────────
    # The 9 values below were frozen by
    # ``docs/task-11-phase3-retrospective-replay-amendment.md`` §7 (Decision 5).
    # ``TASK9_REPLAY_INPUT_INCOMPLETE`` above is the umbrella code carried over
    # from Phase 2 closeout; the 9 below are the more-specific replay taxonomy.
    # Stability rule: each value is a stable, machine-readable
    # lower_snake_case string literal that MUST NOT be inferred from log
    # message text. Code values MUST NOT be reused across taxonomies.
    REPLAY_RUNTIME_IDENTITY_MISSING = "replay_runtime_identity_missing"
    REPLAY_AUDIT_INCOMPLETE = "replay_audit_incomplete"
    MISSING_TASK8_REPLAY_SOURCE = "missing_task8_replay_source"
    CUTOFF_INVISIBLE_TASK9_INPUT = "cutoff_invisible_task9_input"
    AMBIGUOUS_REPLAY_INPUT = "ambiguous_replay_input"
    AUTHORITY_CHAIN_INCOMPATIBLE = "authority_chain_incompatible"
    REPLAY_METADATA_INVALID = "replay_metadata_invalid"
    TASK9_REPLAY_FAILED = "task9_replay_failed"
    TASK10_REPLAY_BINDING_INVALID = "task10_replay_binding_invalid"
    # ── TASK-012 Slice B additions (§9 blocker taxonomy) ─────────────────
    # These blocker codes cover the §9 categories that Slice B produces
    # as part of its manifest/identity/hash pipeline. Slice C / D may
    # raise additional §9 categories that are not yet implemented.
    TASK12_TRAINING_DATASET_EMPTY = "task12_training_dataset_empty"
    TASK12_MODEL_ARTIFACT_HASH_MISMATCH = "task12_model_artifact_hash_mismatch"
    TASK12_MANIFEST_MISMATCH = "task12_manifest_mismatch"
    TASK12_CROSS_RUN_SUBSTITUTION = "task12_cross_run_substitution"
    # ── TASK-012 Slice C additions (§11 #3 / #4 / #5) ────────────────────
    # These blocker codes cover the §11 #3 (execution portion — cutoff
    # filtering), §11 #4 (label-availability cutoff filtering), and
    # §11 #5 (structured empty-training-set blocker) obligations.
    TASK12_TRAINING_ROWS_EMPTY = "task12_training_rows_empty"
    TASK12_CUTOFF_FILTERED_ROW = "task12_cutoff_filtered_row"
    # ── TASK-012 Slice D additions (§11 #10 / #11) ───────────────────────
    # These blocker codes cover the §11 #10 (artifact identity mismatch
    # — JSON-side vs manifest-side disagreement on the canonical §6
    # identity fields) and §11 #11 (prediction binding mismatch —
    # exact Task 9 replay binding not satisfied) obligations. §11 #12
    # reuses the existing TASK12_CROSS_RUN_SUBSTITUTION code (§9
    # taxonomy). Slice E (API / CLI) is out of scope.
    TASK12_ARTIFACT_IDENTITY_MISMATCH = "task12_artifact_identity_mismatch"
    TASK12_PREDICTION_BINDING_MISMATCH = "task12_prediction_binding_mismatch"


# ── Date/time authority helpers ───────────────────────────────────────────────


def cutoff_local_date(forecast_cutoff_at: datetime, timezone_name: str) -> date:
    """Convert a UTC-aware forecast_cutoff_at to a local date in the given timezone.

    Raises:
        TypeError: If forecast_cutoff_at is not a datetime instance.
        ValueError: If forecast_cutoff_at is naive (no tzinfo).
        ZoneInfoNotFoundError: If timezone_name is invalid.
    """
    if not isinstance(forecast_cutoff_at, datetime):
        raise TypeError(
            f"forecast_cutoff_at must be a datetime, got {type(forecast_cutoff_at).__name__}"
        )
    if forecast_cutoff_at.tzinfo is None:
        raise ValueError("forecast_cutoff_at must be timezone-aware (UTC)")
    tz = ZoneInfo(timezone_name)
    return forecast_cutoff_at.astimezone(tz).date()


def assert_date_authority_visible(
    available_on: date,
    *,
    forecast_cutoff_at: datetime,
    timezone_name: str,
) -> None:
    """Raise ValueError if the date authority is not yet visible at cutoff.

    A date authority is visible iff its available_on date is <= the local
    calendar date derived from forecast_cutoff_at in the node's timezone.
    """
    cutoff_date = cutoff_local_date(forecast_cutoff_at, timezone_name)
    if available_on > cutoff_date:
        raise ValueError(
            f"Date authority not visible: "
            f"available_on={available_on.isoformat()} "
            f"> cutoff_local_date={cutoff_date.isoformat()} "
            f"(forecast_cutoff_at={forecast_cutoff_at.isoformat()}, "
            f"timezone={timezone_name})"
        )


__all__ = [
    "HistoricalCandidate",
    "ResolutionResult",
    "ResolvedInputOutcome",
    "Task9AuthorityOutcome",
    "Task10AuthorityOutcome",
    "NodeOrchestrationOutcome",
    "AvailabilityAuditOutcome",
    "NodeExecutionContext",
    "OrchestrationStage",
    "OrchestrationBlocker",
    "cutoff_local_date",
    "assert_date_authority_visible",
    "_sanitize_diagnostics",
    "_build_frozen_dag",
    "build_s2_binding_rows",
    "run_s2_historical_binding",
]


# ── Frozen DAG ───────────────────────────────────────────────────────────────

_FROZEN_DAG_STAGES = (
    OrchestrationStage.RESOLVE_HISTORICAL_INPUTS.value,
    OrchestrationStage.VALIDATE_VISIBILITY.value,
    OrchestrationStage.VALIDATE_AUTHORITY_CHAIN.value,
    OrchestrationStage.RESOLVE_OR_REPLAY_TASK8.value,
    OrchestrationStage.RESOLVE_OR_REPLAY_TASK9.value,
    OrchestrationStage.RESOLVE_OR_TRAIN_TASK10.value,
    OrchestrationStage.EXECUTE_TASK10_PREDICTION.value,
    OrchestrationStage.FINALIZE_ORCHESTRATION_SNAPSHOT.value,
)

_FROZEN_DAG_EDGES = tuple(
    (_FROZEN_DAG_STAGES[i], _FROZEN_DAG_STAGES[i + 1]) for i in range(len(_FROZEN_DAG_STAGES) - 1)
)

_FROZEN_DAG_SCHEMA_VERSION = "task11-phase3-v1"
_FROZEN_DAG_POLICY_VERSION = "v1"


def _build_frozen_dag(*, owner_node_signature: str) -> DagPersistenceCommand:
    return DagPersistenceCommand(
        dag_schema_version=_FROZEN_DAG_SCHEMA_VERSION,
        dag_policy_version=_FROZEN_DAG_POLICY_VERSION,
        dag_dict={
            "nodes": list(_FROZEN_DAG_STAGES),
            "edges": [list(e) for e in _FROZEN_DAG_EDGES],
        },
        expected_node_count=len(_FROZEN_DAG_STAGES),
        expected_edge_count=len(_FROZEN_DAG_EDGES),
    )


# ── Node execution context ──────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class NodeExecutionContext:
    """Typed execution context carrying real persisted run/node identity."""

    rolling_run_id: int
    rolling_node_id: int
    run_signature: str
    node_signature: str


# ── Outcome dataclasses ──────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ResolvedInputOutcome:
    source_role: str
    source_type: AvailabilitySourceType
    semantic_identity: ResolvedUpstreamSemanticIdentity
    persistent_reference: PersistentUpstreamReference
    authoritative_available_at: datetime
    canonical_identity_hash: str
    canonical_payload_hash: str
    business_version: str | None = None


@dataclass(frozen=True, slots=True)
class AvailabilityAuditOutcome:
    source_role: str
    source_type: str
    allowed: bool
    blocker_code: str | None = None
    authoritative_available_at: str = ""
    forecast_cutoff_at: str = ""
    audit_hash: str = ""
    parent_authority: str | None = None


@dataclass(frozen=True, slots=True)
class Task9AuthorityOutcome:
    run_reference: PersistentUpstreamReference | None = None
    semantic_input_signature: str | None = None
    result_hash: str | None = None
    canonical_payload_hash: str | None = None
    source_catalog_hash: str | None = None
    verification_snapshot_hash: str | None = None
    mode: str = "unresolved"


@dataclass(frozen=True, slots=True)
class Task10AuthorityOutcome:
    training_reference: PersistentUpstreamReference | None = None
    artifact_reference: PersistentUpstreamReference | None = None
    prediction_reference: PersistentUpstreamReference | None = None
    feature_reference: PersistentUpstreamReference | None = None
    task9_run_reference: PersistentUpstreamReference | None = None
    task9_result_hash: str | None = None
    input_signature: str | None = None
    prediction_hash: str | None = None
    mode: str = "unresolved"


@dataclass(frozen=True, slots=True)
class NodeOrchestrationOutcome:
    rolling_run_signature: str
    node_signature: str
    attempt_number: int
    status: str
    stage: str
    resolved_inputs: tuple[ResolvedInputOutcome, ...] = ()
    availability_audits: tuple[AvailabilityAuditOutcome, ...] = ()
    task9_authority: Task9AuthorityOutcome | None = None
    task10_authority: Task10AuthorityOutcome | None = None
    fallback_mode: str | None = None
    blocker_code: str | None = None
    diagnostics: dict[str, object] = field(default_factory=dict)
    canonical_payload_hash: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None


# ── Diagnostics helpers ──────────────────────────────────────────────────────


def _sanitize_diagnostics(raw: dict[str, object]) -> dict[str, object]:
    SENSITIVE_KEYS = {"password", "secret", "token", "connection_url", "dsn"}
    SENSITIVE_KEY_SUBSTRINGS = ("dsn", "connection", "password", "secret", "token")
    SENSITIVE_SUBSTRINGS = ("postgres", "sql", "psycopg", "asyncpg")

    def _sanitize_value(value: object) -> object:
        if isinstance(value, dict):
            result: dict[str, object] = {}
            for k, v in value.items():
                k_lower = k.lower()
                if k_lower in SENSITIVE_KEYS or any(
                    sub in k_lower for sub in SENSITIVE_KEY_SUBSTRINGS
                ):
                    result[k] = "[REDACTED]"
                else:
                    result[k] = _sanitize_value(v)
            return result
        if isinstance(value, (list, tuple)):
            return [_sanitize_value(item) for item in value]
        if isinstance(value, str):
            for substr in SENSITIVE_SUBSTRINGS:
                if substr in value.lower():
                    return "[REDACTED]"
            if len(value) > 500:
                return value[:500] + "..."
        return value

    return _sanitize_value(raw)  # type: ignore[return-value]


def build_s2_binding_rows(
    request: S2HistoricalBacktestRequest,
    candidates: tuple[S2HistoricalBindingCandidate, ...],
) -> tuple[S2HistoricalBindingRow, ...]:
    """Build deterministic comparison-ready rows from frozen authorities.

    This function does not query live data and does not compute quality
    metrics. Missing labels remain unknown and become explicit exclusions;
    they are never represented as zero. Forecast and label cutoffs are
    checked independently before a row can be comparable.
    """

    by_horizon: dict[int, S2HistoricalBindingCandidate] = {}
    for candidate in candidates:
        if candidate.horizon_days in by_horizon:
            raise ValueError("duplicate S2 horizon candidate is a structural failure")
        if candidate.forecast_cutoff_at > request.forecast_cutoff_at:
            raise ValueError("forecast authority is visible after the request cutoff")
        if candidate.forecast_authority.available_at > request.forecast_cutoff_at:
            raise ValueError("forecast authority availability violates forecast cutoff")
        by_horizon[candidate.horizon_days] = candidate

    missing = set(request.requested_horizons_days) - by_horizon.keys()
    if missing:
        raise ValueError(
            "missing forecast authority for requested horizon(s): "
            + ",".join(str(item) for item in sorted(missing))
        )

    rows: list[S2HistoricalBindingRow] = []
    for horizon in request.requested_horizons_days:
        candidate = by_horizon[horizon]
        actual = candidate.actual_label
        reason_code: str | None = None
        row_status = "COMPARABLE"
        alignment = "VERIFIED"
        if actual is None:
            row_status = "EXCLUDED"
            reason_code = "NO_APPROVED_REAL_DATA"
            alignment = "UNVERIFIED"
        elif actual.visibility_timestamp is None:
            raise ValueError("actual label authority is missing visibility timestamp")
        elif (
            request.label_visibility_mode == "AS_OF_EVALUATION"
            and actual.visibility_timestamp > request.label_observation_cutoff_at  # type: ignore[operator]
        ):
            raise ValueError("label authority is visible after the label cutoff")
        elif actual.physical_alignment_status != "VERIFIED":
            row_status = "EXCLUDED"
            reason_code = "PHYSICAL_TARGET_ALIGNMENT_UNVERIFIED"
            alignment = actual.physical_alignment_status

        row_payload: dict[str, object] = {
            "horizon_days": candidate.horizon_days,
            "target_date": candidate.target_date,
            "forecast_cutoff_at": request.forecast_cutoff_at,
            "label_observation_cutoff_at": request.label_observation_cutoff_at,
            "label_visibility_mode": request.label_visibility_mode,
            "forecast_value_kg": candidate.forecast_value_kg,
            "actual_value_kg": actual.observed_weight_kg if actual is not None else None,
            "forecast_authority": candidate.forecast_authority,
            "actual_label": actual,
            "physical_alignment_status": alignment,
            "row_status": row_status,
            "reason_code": reason_code,
        }
        row_hash = sha256_payload(canonical_json_value(row_payload))
        rows.append(S2HistoricalBindingRow(**row_payload, row_hash=row_hash))
    return tuple(rows)


async def run_s2_historical_binding(
    session: Any,
    *,
    request: S2HistoricalBacktestRequest,
    candidates: tuple[S2HistoricalBindingCandidate, ...],
    season_id: int,
) -> Any:
    """Persist supplied authority evidence using a caller-owned transaction.

    The function does not open a business database, discover latest rows, or
    run an operational backtest. It accepts evidence from a separately
    audited adapter and persists only comparison-ready binding evidence.
    """

    from backend.app.rolling_backtest.persistence import persist_s2_historical_binding

    rows = build_s2_binding_rows(request, candidates)
    return await persist_s2_historical_binding(
        session,
        request=request,
        rows=rows,
        season_id=season_id,
    )
