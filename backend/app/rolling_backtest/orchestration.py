"""Rolling backtest orchestration: Foundation contract definitions.

Phase 3 Foundation contracts — stage enums, blocker codes, DAG topology,
outcome dataclasses, date/time authority helpers, and diagnostics utilities.
No executable orchestration; execution surface removed in TASK-011 cleanup.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.actual_harvest_labels.models import (
    ActualHarvestLabelSnapshotLabelModel,
    ActualHarvestLabelSnapshotModel,
    ActualHarvestLabelSnapshotWinnerModel,
)
from backend.app.models.core_forecast import CoreForecastDailyRowModel, CoreForecastRunModel
from backend.app.models.harvest_state import HarvestStateRun
from backend.app.rolling_backtest.canonical import canonical_json_value, sha256_payload
from backend.app.rolling_backtest.enums import (
    AvailabilitySourceType,
)
from backend.app.rolling_backtest.persisted_forecast_authority import (
    PersistedForecastAuthorityRefs,
    task9_member_identity_hash as _task9_member_identity_hash,
    validate_persisted_forecast_authority_chain,
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
    S2ActualLabelAuthority,
    S2HistoricalBacktestRequest,
    S2HistoricalBindingCandidate,
    S2HistoricalBindingRow,
    s2_business_grain_hash,
)
from backend.app.rolling_backtest.signatures import (
    s2_binding_key_hash,
    s2_binding_row_hash,
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
    "resolve_s2_persisted_authorities",
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
class _PinnedTask10PredictionInput:
    """Minimum typed projection consumed by the existing replay binding adapter."""

    persistent_reference: PersistentUpstreamReference


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

    normalized: list[S2HistoricalBindingCandidate] = []
    for candidate in candidates:
        if candidate.authority_verification == "UNVERIFIED":
            raise ValueError(
                "caller-supplied authority is not accepted without persisted verification"
            )
        if candidate.horizon_days not in request.requested_horizons_days:
            raise ValueError("candidate horizon is outside the requested horizon set")
        if not (
            candidate.season_business_key in request.season_business_keys
            and candidate.farm_business_key in request.farm_business_keys
            and candidate.subfarm_business_key in request.subfarm_business_keys
            and candidate.variety_business_key in request.variety_business_keys
        ):
            raise ValueError("candidate business grain is outside request scope")
        if candidate.forecast_cutoff_at > request.forecast_cutoff_at:
            raise ValueError("forecast authority is visible after the request cutoff")
        if candidate.forecast_authority.available_at > request.forecast_cutoff_at:
            raise ValueError("forecast authority availability violates forecast cutoff")
        if candidate.forecast_authority.task10_model_available_at > request.forecast_cutoff_at:
            raise ValueError("Task 10 model authority availability violates forecast cutoff")
        if candidate.forecast_authority.historical_code_available_at > request.forecast_cutoff_at:
            raise ValueError("historical code authority is visible after the forecast cutoff")
        normalized.append(candidate)

    rows: list[S2HistoricalBindingRow] = []
    for candidate in normalized:
        actual = candidate.actual_label
        reason_code: str | None = None
        row_status = "COMPARABLE"
        alignment = "VERIFIED"
        if actual is None:
            row_status = "EXCLUDED"
            reason_code = "NO_APPROVED_REAL_DATA"
            alignment = "UNVERIFIED"
        elif actual.label_resolution_status == "PROVEN_ABSENT":
            row_status = "EXCLUDED"
            reason_code = "NO_VISIBLE_LABEL_AT_CUTOFF"
            alignment = "UNVERIFIED"
        elif actual.visibility_timestamp is None:
            raise ValueError("actual label authority is missing visibility timestamp")
        elif (
            request.label_visibility_mode == "AS_OF_EVALUATION"
            and actual.visibility_timestamp > request.label_observation_cutoff_at  # type: ignore[operator]
        ):
            raise ValueError("label authority is visible after the label cutoff")
        elif (
            candidate.authority_verification == "PERSISTED"
            and actual.physical_alignment_status == "VERIFIED"
        ):
            raise ValueError(
                "production physical equivalence authority is unavailable; "
                "synthetic alignment cannot be promoted"
            )
        elif actual.physical_alignment_status != "VERIFIED":
            row_status = "NOT_COMPUTABLE"
            reason_code = "BLOCKED_BY_PHYSICAL_TARGET_GAP"
            alignment = "UNVERIFIED"

        if actual is not None:
            if actual.target_date != candidate.target_date:
                raise ValueError("actual label target date does not match binding target date")
            if (
                actual.label_row_identity_hash is not None
                and actual.label_row_identity_hash == actual.label_snapshot_identity_hash
            ):
                raise ValueError("snapshot identity cannot substitute for exact label row identity")
            actual_keys = {
                actual.season_business_key,
                actual.farm_business_key,
                actual.subfarm_business_key,
                actual.variety_business_key,
            }
            if None in actual_keys:
                raise ValueError("actual label business grain is incomplete")
            if not (
                actual.season_business_key in request.season_business_keys
                and actual.farm_business_key in request.farm_business_keys
                and actual.subfarm_business_key in request.subfarm_business_keys
                and actual.variety_business_key in request.variety_business_keys
            ):
                raise ValueError("actual label business grain is outside request scope")
            if actual.business_grain_hash != s2_business_grain_hash(
                season_business_key=actual.season_business_key,
                farm_business_key=actual.farm_business_key,
                subfarm_business_key=actual.subfarm_business_key,
                variety_business_key=actual.variety_business_key,
                target_date=actual.target_date,
            ):
                raise ValueError("actual label business grain hash is not canonical")
            if (
                actual.season_business_key != candidate.season_business_key
                or actual.farm_business_key != candidate.farm_business_key
                or actual.subfarm_business_key != candidate.subfarm_business_key
                or actual.variety_business_key != candidate.variety_business_key
            ):
                raise ValueError("actual label grain does not match forecast binding grain")

        row_payload: dict[str, object] = {
            "season_id": candidate.season_id,
            "season_business_key": candidate.season_business_key,
            "farm_business_key": candidate.farm_business_key,
            "subfarm_business_key": candidate.subfarm_business_key,
            "variety_business_key": candidate.variety_business_key,
            "forecast_quantile": candidate.forecast_quantile,
            "horizon_days": candidate.horizon_days,
            "target_date": candidate.target_date,
            "forecast_cutoff_at": request.forecast_cutoff_at,
            "label_observation_cutoff_at": request.label_observation_cutoff_at,
            "label_visibility_mode": request.label_visibility_mode,
            "forecast_value_kg": candidate.forecast_value_kg,
            "actual_value_kg": (
                actual.observed_weight_kg
                if actual is not None and actual.label_resolution_status == "EXACT_LABEL"
                else None
            ),
            "forecast_authority": candidate.forecast_authority,
            "actual_label": actual,
            "physical_alignment_status": alignment,
            "row_status": row_status,
            "reason_code": reason_code,
            "authority_verification": candidate.authority_verification,
            "binding_key_hash": "0" * 64,
        }
        provisional = S2HistoricalBindingRow(
            **row_payload,
            row_hash="0" * 64,
        )
        row_payload["binding_key_hash"] = s2_binding_key_hash(request, provisional)
        with_binding_key = S2HistoricalBindingRow(**row_payload, row_hash="0" * 64)
        row_hash = s2_binding_row_hash(with_binding_key)
        rows.append(S2HistoricalBindingRow(**row_payload, row_hash=row_hash))
    binding_keys = [row.binding_key_hash for row in rows]
    if len(binding_keys) != len(set(binding_keys)):
        raise ValueError("duplicate canonical S2 binding key is a structural failure")
    coverage: dict[tuple[object, ...], set[int]] = {}
    for row in rows:
        grain = (
            row.season_id,
            row.season_business_key,
            row.farm_business_key,
            row.subfarm_business_key,
            row.variety_business_key,
            row.forecast_quantile,
            row.forecast_authority.forecast_run_identity_hash,
        )
        coverage.setdefault(grain, set()).add(row.horizon_days)
    required_horizons = set(request.requested_horizons_days)
    if any(horizons != required_horizons for horizons in coverage.values()):
        raise ValueError("each S2 business grain requires complete requested horizon coverage")
    return tuple(sorted(rows, key=lambda row: row.binding_key_hash))


async def run_s2_historical_binding(
    session: Any,
    *,
    request: S2HistoricalBacktestRequest,
    candidates: tuple[S2HistoricalBindingCandidate, ...],
    season_id: int | None = None,
) -> Any:
    """Persist supplied authority evidence using a caller-owned transaction.

    The function does not open a business database, discover latest rows, or
    run an operational backtest. It accepts evidence from a separately
    audited adapter and persists only comparison-ready binding evidence.
    """

    from backend.app.rolling_backtest.persistence import persist_s2_historical_binding

    if not candidates:
        raise ValueError("S2 runner requires at least one persisted authority candidate")
    verification_modes = {candidate.authority_verification for candidate in candidates}
    if verification_modes != {"PERSISTED"}:
        raise ValueError("production S2 runner requires exact persisted authority")
    if any(candidate.persisted_authority_references is None for candidate in candidates):
        raise ValueError("persisted authority candidates require lookup references")
    candidates = await resolve_s2_persisted_authorities(
        session,
        request=request,
        candidates=candidates,
    )
    resolved_season_ids = {candidate.season_id for candidate in candidates}
    if season_id is not None and resolved_season_ids != {season_id}:
        raise ValueError("caller season_id does not match persisted season authority")
    rows = build_s2_binding_rows(request, candidates)
    return await persist_s2_historical_binding(
        session,
        request=request,
        rows=rows,
    )


async def resolve_s2_persisted_authorities(
    session: AsyncSession,
    *,
    request: S2HistoricalBacktestRequest,
    candidates: tuple[S2HistoricalBindingCandidate, ...],
) -> tuple[S2HistoricalBindingCandidate, ...]:
    """Load and verify exact persisted authority rows before binding.

    This adapter is deliberately reference-driven. It never searches for the
    latest run or snapshot; every relationship is checked against the caller's
    expected identity and cutoff before a verified candidate is returned.
    """

    from backend.app.actual_harvest_labels.hashes import (
        compute_exclusion_manifest_hash,
        compute_label_row_set_hash,
        compute_label_snapshot_hash,
        compute_snapshot_instance_identity_hash,
        compute_snapshot_request_identity_hash,
        compute_winner_manifest_hash,
    )
    from backend.app.actual_harvest_labels.persistence import (
        exclusion_row_hash_for,
        exclusion_row_to_value_object,
        label_row_hash_for,
        label_row_to_value_object,
        load_exclusion_rows_for_snapshot,
        load_label_rows_for_snapshot,
        load_winners_for_snapshot,
        winner_row_hash_for,
        winner_to_value_object,
    )

    resolved: list[S2HistoricalBindingCandidate] = []
    exact_row_references: set[tuple[int, int, int | None]] = set()
    for candidate in candidates:
        refs = candidate.persisted_authority_references
        if refs is None:
            raise ValueError("persisted authority references are required")
        reference_key = (
            refs.core_forecast_daily_row_id,
            refs.task10_prediction_run_id,
            refs.label_row_id,
        )
        if reference_key in exact_row_references:
            raise ValueError("ambiguous persisted authority reference reused across bindings")
        exact_row_references.add(reference_key)

        core_run = await session.get(CoreForecastRunModel, refs.core_forecast_run_id)
        core_row = await session.get(CoreForecastDailyRowModel, refs.core_forecast_daily_row_id)
        task9 = await session.get(HarvestStateRun, refs.task9_run_id)
        snapshot = await session.get(ActualHarvestLabelSnapshotModel, refs.label_snapshot_id)
        label = (
            None
            if refs.label_row_id is None
            else await session.get(
                ActualHarvestLabelSnapshotLabelModel,
                refs.label_row_id,
            )
        )
        winner = (
            None
            if refs.label_winner_id is None
            else await session.get(
                ActualHarvestLabelSnapshotWinnerModel,
                refs.label_winner_id,
            )
        )
        if any(item is None for item in (core_run, core_row, task9, snapshot)):
            raise ValueError("required persisted S2 authority is missing")
        assert core_run is not None
        assert core_row is not None
        assert task9 is not None
        assert snapshot is not None

        if (
            candidate.season_id != core_run.forecast_season_id
            or candidate.season_business_key != core_run.forecast_season_code
            or candidate.forecast_quantile != core_row.forecast_quantile
        ):
            raise ValueError("candidate season/quantile does not match persisted core forecast")

        await validate_persisted_forecast_authority_chain(
            session,
            refs=PersistedForecastAuthorityRefs(
                core_forecast_run_id=refs.core_forecast_run_id,
                core_forecast_daily_row_id=refs.core_forecast_daily_row_id,
                task9_run_id=refs.task9_run_id,
                task10_prediction_run_id=refs.task10_prediction_run_id,
            ),
            forecast_cutoff_at=request.forecast_cutoff_at,
            target_date=candidate.target_date,
            horizon_days=candidate.horizon_days,
            expected_forecast_authority=candidate.forecast_authority,
        )

        persisted_labels = await load_label_rows_for_snapshot(session, snapshot.id)
        persisted_winners = await load_winners_for_snapshot(session, snapshot.id)
        persisted_exclusions = await load_exclusion_rows_for_snapshot(session, snapshot.id)
        winner_values = tuple(winner_to_value_object(item) for item in persisted_winners)
        label_values = tuple(label_row_to_value_object(item) for item in persisted_labels)
        exclusion_values = tuple(
            exclusion_row_to_value_object(item) for item in persisted_exclusions
        )
        if any(
            winner_row_hash_for(item.model_dump(mode="python")) != item.winner_row_hash
            for item in winner_values
        ):
            raise ValueError("persisted I7 winner canonical hash does not round-trip")
        if any(
            label_row_hash_for(item.model_dump(mode="python")) != item.label_row_hash
            for item in label_values
        ):
            raise ValueError("persisted I7 label canonical hash does not round-trip")
        if any(
            exclusion_row_hash_for(item.model_dump(mode="python")) != item.exclusion_row_hash
            for item in exclusion_values
        ):
            raise ValueError("persisted I7 exclusion canonical hash does not round-trip")
        try:
            raw_season_business_keys = json.loads(snapshot.season_business_keys)
            raw_farm_business_keys = json.loads(snapshot.farm_business_keys_or_empty_for_all)
            raw_variety_business_keys = json.loads(snapshot.variety_business_keys_or_empty_for_all)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("persisted I7 snapshot scope is not canonical JSON") from exc
        raw_scopes = (
            raw_season_business_keys,
            raw_farm_business_keys,
            raw_variety_business_keys,
        )
        if any(not isinstance(scope, list) for scope in raw_scopes) or any(
            not isinstance(item, str) for scope in raw_scopes for item in scope
        ):
            raise ValueError("persisted I7 snapshot scope is malformed")
        season_business_keys = tuple(raw_season_business_keys)
        farm_business_keys = tuple(raw_farm_business_keys)
        variety_business_keys = tuple(raw_variety_business_keys)
        snapshot_request_hash = compute_snapshot_request_identity_hash(
            snapshot_idempotency_key=snapshot.snapshot_idempotency_key,
            source_system=snapshot.source_system,
            visibility_mode=snapshot.visibility_mode,
            label_observation_cutoff_at_or_null=(snapshot.label_observation_cutoff_at_or_null),
            harvest_date_start=snapshot.harvest_date_start,
            harvest_date_end=snapshot.harvest_date_end,
            season_business_keys=season_business_keys,
            farm_business_keys_or_empty_for_all=farm_business_keys,
            variety_business_keys_or_empty_for_all=variety_business_keys,
            snapshot_policy_version=snapshot.snapshot_policy_version,
            winner_policy_version=snapshot.winner_policy_version,
            aggregation_policy_version=snapshot.aggregation_policy_version,
        )
        snapshot_instance_hash = compute_snapshot_instance_identity_hash(
            request_identity_hash=snapshot_request_hash,
            source_commit_manifest_set_hash=snapshot.source_commit_manifest_set_hash,
        )
        winner_manifest_hash = compute_winner_manifest_hash(
            item.model_dump(mode="python") for item in winner_values
        )
        label_row_set_hash = compute_label_row_set_hash(
            item.model_dump(mode="python") for item in label_values
        )
        exclusion_manifest_hash = compute_exclusion_manifest_hash(
            item.model_dump(mode="python") for item in exclusion_values
        )
        label_snapshot_hash = compute_label_snapshot_hash(
            instance_identity_hash=snapshot_instance_hash,
            winner_manifest_hash=winner_manifest_hash,
            label_row_set_hash=label_row_set_hash,
            exclusion_manifest_hash=exclusion_manifest_hash,
            winner_count=len(winner_values),
            label_row_count=len(label_values),
            exclusion_row_count=len(exclusion_values),
            snapshot_policy_version=snapshot.snapshot_policy_version,
            winner_policy_version=snapshot.winner_policy_version,
            aggregation_policy_version=snapshot.aggregation_policy_version,
        )
        if (
            snapshot.snapshot_request_identity_hash != snapshot_request_hash
            or snapshot.snapshot_instance_identity_hash != snapshot_instance_hash
            or snapshot.winner_manifest_hash != winner_manifest_hash
            or snapshot.label_row_set_hash != label_row_set_hash
            or snapshot.exclusion_manifest_hash != exclusion_manifest_hash
            or snapshot.label_snapshot_hash != label_snapshot_hash
            or snapshot.winner_count != len(winner_values)
            or snapshot.label_row_count != len(label_values)
            or snapshot.exclusion_row_count != len(exclusion_values)
        ):
            raise ValueError("persisted I7 snapshot canonical identity does not round-trip")
        winner_commit_manifest_hashes = {item.commit_manifest_hash for item in winner_values}
        if snapshot.source_manifest_count <= 0 or snapshot.source_manifest_count < len(
            winner_commit_manifest_hashes
        ):
            raise ValueError("persisted I7 actual-source manifest evidence is incomplete")
        if (
            not set(request.season_business_keys).issubset(season_business_keys)
            or (
                farm_business_keys
                and not set(request.farm_business_keys).issubset(farm_business_keys)
            )
            or (
                variety_business_keys
                and not set(request.variety_business_keys).issubset(variety_business_keys)
            )
        ):
            raise ValueError("persisted I7 snapshot scope does not cover the request")
        if request.label_observation_cutoff_at is not None and any(
            (
                item.source_recorded_at_or_null is not None
                and item.source_recorded_at_or_null > request.label_observation_cutoff_at
            )
            or (
                item.finalized_at_or_null is not None
                and item.finalized_at_or_null > request.label_observation_cutoff_at
            )
            for item in persisted_winners
        ):
            raise ValueError("future I7 winner revision is visible after the label cutoff")
        if snapshot.visibility_mode != request.label_visibility_mode or not (
            snapshot.harvest_date_start <= candidate.target_date <= snapshot.harvest_date_end
        ):
            raise ValueError("I7 snapshot does not cover the requested date/visibility mode")
        if request.label_observation_cutoff_at is not None:
            if snapshot.label_observation_cutoff_at_or_null != request.label_observation_cutoff_at:
                raise ValueError("I7 snapshot label cutoff mismatch")
            if snapshot.snapshot_executed_at > request.label_observation_cutoff_at:
                raise ValueError("I7 snapshot is visible after the label cutoff")
        elif snapshot.label_observation_cutoff_at_or_null is not None:
            raise ValueError("final-adjudicated snapshot unexpectedly carries an as-of cutoff")

        matching_labels = tuple(
            item
            for item in persisted_labels
            if (
                item.season_business_key == candidate.season_business_key
                and item.farm_business_key == candidate.farm_business_key
                and item.subfarm_business_key == candidate.subfarm_business_key
                and item.variety_business_key == candidate.variety_business_key
                and item.harvest_business_date == candidate.target_date
            )
        )
        if len(matching_labels) > 1:
            raise ValueError("ambiguous persisted I7 label rows for exact search grain")
        if label is None and matching_labels:
            raise ValueError("persisted I7 label exists but exact label reference was omitted")
        if label is not None and (len(matching_labels) != 1 or matching_labels[0].id != label.id):
            raise ValueError("exact I7 label reference does not match the searched snapshot row")
        if label is not None and label.id not in {item.id for item in persisted_labels}:
            raise ValueError("exact I7 label row is not owned by the requested snapshot")
        if winner is not None and winner.id not in {item.id for item in persisted_winners}:
            raise ValueError("exact I7 winner is not owned by the requested snapshot")

        business_grain_hash = s2_business_grain_hash(
            season_business_key=candidate.season_business_key,
            farm_business_key=candidate.farm_business_key,
            subfarm_business_key=candidate.subfarm_business_key,
            variety_business_key=candidate.variety_business_key,
            target_date=candidate.target_date,
        )
        physical_alignment_policy_version = "v0.2-s2-q2c-business-attestation-required-v1"
        physical_alignment_payload = canonical_json_value(
            {
                "forecast_physical_event": "MODEL_HARVESTED_MARKETABLE_QUANTITY",
                "actual_physical_event": "FARM_PICK",
                "forecast_quantity_basis": "MODEL_MARKETABLE_QUANTITY",
                "actual_quantity_basis": "OBSERVED_PICK_WEIGHT",
                "unit": "kg",
                "loss_boundary_policy_version": "q2c-business-attestation-missing",
                "physical_alignment_policy_version": physical_alignment_policy_version,
                "equivalence_attested": False,
            }
        )
        physical_alignment_evidence_hash = sha256_payload(physical_alignment_payload)

        if label is None:
            if winner is not None:
                raise ValueError("winner reference cannot exist without an exact I7 label row")
            label_winner_set_identity_hash = sha256_payload(
                canonical_json_value({"winner_row_hashes": ()})
            )
            absence_evidence = canonical_json_value(
                {
                    "label_snapshot_identity_hash": snapshot.label_snapshot_hash,
                    "label_row_set_hash": snapshot.label_row_set_hash,
                    "exclusion_manifest_hash": snapshot.exclusion_manifest_hash,
                    "source_commit_manifest_set_hash": snapshot.source_commit_manifest_set_hash,
                    "label_observation_cutoff_at": snapshot.label_observation_cutoff_at_or_null,
                    "search_grain": {
                        "season_business_key": candidate.season_business_key,
                        "farm_business_key": candidate.farm_business_key,
                        "subfarm_business_key": candidate.subfarm_business_key,
                        "variety_business_key": candidate.variety_business_key,
                        "target_date": candidate.target_date,
                    },
                    "matching_label_row_count": 0,
                }
            )
            absence_evidence_hash = sha256_payload(absence_evidence)
            actual_source_identity_hash = sha256_payload(
                canonical_json_value(
                    {
                        "source_commit_manifest_set_hash": (
                            snapshot.source_commit_manifest_set_hash
                        ),
                        "label_row_set_hash": snapshot.label_row_set_hash,
                        "exclusion_manifest_hash": snapshot.exclusion_manifest_hash,
                    }
                )
            )
            actual = S2ActualLabelAuthority(
                label_snapshot_identity_hash=snapshot.label_snapshot_hash,
                label_resolution_status="PROVEN_ABSENT",
                label_winner_set_identity_hash=label_winner_set_identity_hash,
                source_identity_hash=snapshot.source_commit_manifest_set_hash,
                actual_source_identity_hash=actual_source_identity_hash,
                target_date=candidate.target_date,
                season_business_key=candidate.season_business_key,
                farm_business_key=candidate.farm_business_key,
                subfarm_business_key=candidate.subfarm_business_key,
                variety_business_key=candidate.variety_business_key,
                business_grain_hash=business_grain_hash,
                revision_or_winner_evidence={"persisted_absence_search": absence_evidence},
                absence_evidence_hash=absence_evidence_hash,
                visibility_timestamp=snapshot.snapshot_executed_at,
                forecast_physical_event="MODEL_HARVESTED_MARKETABLE_QUANTITY",
                actual_physical_event="FARM_PICK",
                forecast_quantity_basis="MODEL_MARKETABLE_QUANTITY",
                actual_quantity_basis="OBSERVED_PICK_WEIGHT",
                unit="kg",
                loss_boundary_policy_version="q2c-business-attestation-missing",
                physical_alignment_policy_version=physical_alignment_policy_version,
                physical_alignment_evidence_hash=physical_alignment_evidence_hash,
                physical_alignment_status="UNVERIFIED",
            )
        else:
            if winner is None:
                raise ValueError("exact I7 label row requires an exact winner reference")
            if (
                label.snapshot_id != snapshot.id
                or label.harvest_business_date != candidate.target_date
                or not (
                    label.season_business_key == candidate.season_business_key
                    and label.farm_business_key == candidate.farm_business_key
                    and label.subfarm_business_key == candidate.subfarm_business_key
                    and label.variety_business_key == candidate.variety_business_key
                )
            ):
                raise ValueError("I7 label row is not bound to the requested snapshot/grain")
            try:
                contributing_winner_hashes_raw = json.loads(label.contributing_winner_hashes)
            except (TypeError, json.JSONDecodeError) as exc:
                raise ValueError("I7 label winner evidence is not canonical JSON") from exc
            if not isinstance(contributing_winner_hashes_raw, list) or any(
                not isinstance(item, str) or len(item) != 64
                for item in contributing_winner_hashes_raw
            ):
                raise ValueError("I7 label winner evidence is malformed")
            contributing_winner_hashes = tuple(contributing_winner_hashes_raw)
            if contributing_winner_hashes != tuple(
                sorted(set(contributing_winner_hashes))
            ) or label.contributing_winner_count != len(contributing_winner_hashes):
                raise ValueError("I7 label winner evidence is ambiguous or count-drifted")
            matching_winners = tuple(
                item
                for item in persisted_winners
                if item.winner_row_hash in contributing_winner_hashes
            )
            if (
                len(matching_winners) != len(contributing_winner_hashes)
                or winner.winner_row_hash not in contributing_winner_hashes
            ):
                raise ValueError("I7 winner set does not exactly bind the requested label row")
            if (
                sum(
                    (item.actual_harvest_quantity_kg for item in matching_winners),
                    start=Decimal("0"),
                )
                != label.exact_decimal_quantity_sum_kg
            ):
                raise ValueError("I7 label exact Decimal sum does not match its winner set")
            expected_label_row_hash = label_row_hash_for(
                {
                    "season_business_key": label.season_business_key,
                    "farm_business_key": label.farm_business_key,
                    "subfarm_business_key": label.subfarm_business_key,
                    "variety_business_key": label.variety_business_key,
                    "harvest_business_date": label.harvest_business_date,
                    "exact_decimal_quantity_sum_kg": label.exact_decimal_quantity_sum_kg,
                    "contributing_winner_hashes": contributing_winner_hashes,
                }
            )
            if expected_label_row_hash != label.label_row_hash:
                raise ValueError("I7 label row canonical hash does not round-trip")
            for selected_winner in matching_winners:
                if (
                    selected_winner.snapshot_id != snapshot.id
                    or selected_winner.season_business_key != label.season_business_key
                    or selected_winner.farm_business_key != label.farm_business_key
                    or selected_winner.subfarm_business_key != label.subfarm_business_key
                    or selected_winner.variety_business_key != label.variety_business_key
                    or selected_winner.harvest_business_date != label.harvest_business_date
                ):
                    raise ValueError("I7 winner is not an exact contributor to the label row")
                if (
                    selected_winner.resolved_identity_snapshot_hash
                    != request.resolved_identity_snapshot_hash
                    or selected_winner.mapping_policy_version != request.mapping_policy_version
                    or selected_winner.season_resolver_version
                    != request.master_identity_resolver_version
                ):
                    raise ValueError("I7 resolver/mapping identity does not match request")
                if any(
                    value is None
                    for value in (
                        selected_winner.season_id,
                        selected_winner.farm_id,
                        selected_winner.subfarm_id,
                        selected_winner.variety_id,
                    )
                ):
                    raise ValueError("I7 winner is missing resolved numeric identity references")
                if (
                    selected_winner.season_id != core_run.forecast_season_id
                    or selected_winner.farm_id != core_row.farm_id
                    or selected_winner.subfarm_id != core_row.subfarm_id
                    or selected_winner.variety_id != core_row.variety_id
                ):
                    raise ValueError("forecast row identity does not match persisted I7 grain")
                if request.label_observation_cutoff_at is not None and (
                    (
                        selected_winner.source_recorded_at_or_null is not None
                        and selected_winner.source_recorded_at_or_null
                        > request.label_observation_cutoff_at
                    )
                    or (
                        selected_winner.finalized_at_or_null is not None
                        and selected_winner.finalized_at_or_null
                        > request.label_observation_cutoff_at
                    )
                ):
                    raise ValueError("future I7 winner revision is visible after the label cutoff")
            label_winner_set_identity_hash = sha256_payload(
                canonical_json_value({"winner_row_hashes": contributing_winner_hashes})
            )
            actual_source_identity_hash = sha256_payload(
                canonical_json_value(
                    {
                        "source_commit_manifest_set_hash": (
                            snapshot.source_commit_manifest_set_hash
                        ),
                        "winner_commit_manifest_hashes": tuple(
                            sorted({item.commit_manifest_hash for item in matching_winners})
                        ),
                    }
                )
            )
            actual = S2ActualLabelAuthority(
                label_snapshot_identity_hash=snapshot.label_snapshot_hash,
                label_resolution_status="EXACT_LABEL",
                label_row_identity_hash=label.label_row_hash,
                label_winner_identity_hash=winner.winner_row_hash,
                label_winner_set_identity_hash=label_winner_set_identity_hash,
                source_identity_hash=snapshot.source_commit_manifest_set_hash,
                actual_source_identity_hash=actual_source_identity_hash,
                target_date=label.harvest_business_date,
                season_business_key=label.season_business_key,
                farm_business_key=label.farm_business_key,
                subfarm_business_key=label.subfarm_business_key,
                variety_business_key=label.variety_business_key,
                business_grain_hash=business_grain_hash,
                revision_or_winner_evidence={
                    "winner_rows": tuple(
                        {
                            "external_logical_record_id": item.external_logical_record_id,
                            "external_revision_id": item.external_revision_id,
                            "revision_number": item.revision_number,
                            "winner_row_hash": item.winner_row_hash,
                            "source_recorded_at": item.source_recorded_at_or_null,
                        }
                        for item in sorted(
                            matching_winners,
                            key=lambda item: item.winner_row_hash,
                        )
                    )
                },
                observed_weight_kg=label.exact_decimal_quantity_sum_kg,
                visibility_timestamp=snapshot.snapshot_executed_at,
                forecast_physical_event="MODEL_HARVESTED_MARKETABLE_QUANTITY",
                actual_physical_event="FARM_PICK",
                forecast_quantity_basis="MODEL_MARKETABLE_QUANTITY",
                actual_quantity_basis="OBSERVED_PICK_WEIGHT",
                unit="kg",
                loss_boundary_policy_version="q2c-business-attestation-missing",
                physical_alignment_policy_version=physical_alignment_policy_version,
                physical_alignment_evidence_hash=physical_alignment_evidence_hash,
                physical_alignment_status="UNVERIFIED",
            )
        if candidate.actual_label is not None and (
            candidate.actual_label.label_snapshot_identity_hash
            != actual.label_snapshot_identity_hash
            or candidate.actual_label.label_resolution_status != actual.label_resolution_status
            or candidate.actual_label.label_row_identity_hash != actual.label_row_identity_hash
            or candidate.actual_label.label_winner_identity_hash
            != actual.label_winner_identity_hash
            or candidate.actual_label.business_grain_hash != actual.business_grain_hash
        ):
            raise ValueError("persisted I7 identity does not match request")
        if candidate.forecast_authority is None:
            raise ValueError("persisted forecast authority is required")
        forecast = candidate.forecast_authority
        resolved.append(
            candidate.model_copy(
                update={
                    "season_id": core_run.forecast_season_id,
                    "season_business_key": core_run.forecast_season_code,
                    "forecast_quantile": core_row.forecast_quantile,
                    "forecast_value_kg": core_row.model_harvested_marketable_quantity_kg,
                    "forecast_authority": forecast,
                    "actual_label": actual,
                    "authority_verification": "PERSISTED",
                }
            )
        )
    return tuple(resolved)
