"""Node-level orchestration service for Task 11 rolling backtest.

Executes a single rolling node through the eight-stage DAG.
Supports execution_mode=historical_observed + upstream_selection_mode=pinned.

Stages:
1. resolve_historical_inputs
2. validate_visibility
3. validate_authority_chain
4. resolve_or_replay_task8
5. resolve_or_replay_task9
6. resolve_or_train_task10
7. execute_task10_prediction
8. finalize_orchestration_snapshot

For historical_observed + pinned: stages 4-7 perform reuse, exact load,
integrity reload, and authority binding verification only.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any, cast
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.harvest_state.application import get_harvest_state_run_by_id
from backend.app.harvest_state.canonical import parse_decimal
from backend.app.maturity.service import (
    load_maturity_forecast_result,
    load_maturity_model_result,
)
from backend.app.models.analytics import AnalyticsBuildRun
from backend.app.models.harvest_state import HarvestStateRun
from backend.app.models.maturity import (
    MaturityDailyPredictionModel,
    MaturityForecastRun,
    MaturityModelArtifact,
    MaturityModelRun,
)
from backend.app.models.production_plan import FarmSeasonVarietyPlan, ProductionPlanImportRun
from backend.app.models.residual_model import (
    ResidualModelArtifact,
    ResidualModelPredictionRun,
    ResidualModelTrainingRun,
)
from backend.app.models.rolling_backtest import (
    RollingBacktestAttempt,
    RollingBacktestAvailabilityAudit,
    RollingBacktestNode,
    RollingBacktestOrchestrationSnapshot,
    RollingBacktestRun,
)
from backend.app.models.weather import (
    LocationWeatherMapping,
    WeatherDailyObservation,
    WeatherFeatureRun,
)
from backend.app.residual_model.persistence import (
    load_and_validate_trusted_residual_artifacts,
    load_residual_prediction_run_by_id,
    load_residual_training_run_by_id,
)
from backend.app.rolling_backtest.availability import (
    availability_snapshot_audit_hash,
    evaluate_authority_visibility,
)
from backend.app.rolling_backtest.canonical import canonical_json_dumps, sha256_payload
from backend.app.rolling_backtest.enums import (
    AvailabilitySourceType,
    ExecutionMode,
    UpstreamSelectionMode,
)
from backend.app.rolling_backtest.errors import (
    RollingBacktestAttemptConflictError,
    RollingBacktestAuthorityBindingError,
    RollingBacktestIntegrityError,
    RollingBacktestPersistenceError,
)
from backend.app.rolling_backtest.orchestration import (
    AvailabilityAuditOutcome,
    NodeOrchestrationOutcome,
    OrchestrationStage,
    ResolvedInputOutcome,
    Task9AuthorityOutcome,
    Task10AuthorityOutcome,
    _build_frozen_dag,
    _sanitize_diagnostics,
)
from backend.app.rolling_backtest.persistence import (
    _finalize_attempt_status_in_session,
    _resolved_input_canonical_payload,
    create_execution_attempt,
    finalize_attempt_status,  # noqa: F401 – used by unit test mocks
    finalize_attempt_with_snapshot,
    load_logical_run_with_integrity,
    load_node_resolved_identities_with_references,
    persist_orchestration_snapshot,
    persist_stage_event,
    update_run_status_from_attempts,
)
from backend.app.rolling_backtest.replay_metadata import ReplayRunIdentity
from backend.app.rolling_backtest.replay_pipeline import (
    ReplayPipelineOutcome,
    orchestrate_replay_node,
)
from backend.app.rolling_backtest.resolution import (
    HistoricalCandidate,
    _build_identity_payload,
    _make_identity,
    _task8_daily_prediction_payload_hash,
    resolve_historical,
)
from backend.app.rolling_backtest.schemas import (
    AvailabilitySnapshot,
    ParentAuthorityIdentity,
    PersistentUpstreamReference,
    ResolvedUpstreamSemanticIdentity,
    RollingBacktestConfig,
    RollingNodeDefinition,
    Task3AnalyticsBuildAvailabilitySnapshot,
    Task3SourceVisibilityIdentity,
    Task8DailyPredictionAvailabilitySnapshot,
    Task8ForecastRunAvailabilitySnapshot,
    Task8ModelArtifactAvailabilitySnapshot,
    Task8ModelRunAvailabilitySnapshot,
    Task9HarvestStateRunAvailabilitySnapshot,
    Task10ModelArtifactAvailabilitySnapshot,
    Task10PredictionRunAvailabilitySnapshot,
    Task10TrainingRunAvailabilitySnapshot,
)

if TYPE_CHECKING:  # pragma: no cover — import-only for type checkers
    from backend.app.harvest_state.schemas import Task9ARequest

# ── Error types ──────────────────────────────────────────────────────────────


class NodeOrchestrationError(RollingBacktestPersistenceError):
    """Base error for node orchestration failures."""

    code = "NODE_ORCHESTRATION_ERROR"


class UnsupportedExecutionModeError(NodeOrchestrationError):
    """Execution mode is not supported in this phase."""

    code = "UNSUPPORTED_EXECUTION_MODE"


class UnsupportedSelectionModeError(NodeOrchestrationError):
    """Selection mode is not supported in this phase."""

    code = "UNSUPPORTED_SELECTION_MODE"


class NodeAlreadyFinalizedError(NodeOrchestrationError):
    """Cannot overwrite a successfully completed node."""

    code = "NODE_ALREADY_FINALIZED"


class NodeIntegrityReloadFailedError(NodeOrchestrationError):
    """Integrity reload failed after snapshot persistence."""

    code = "INTEGRITY_RELOAD_FAILED"


class PinnedSourceNotFoundError(NodeOrchestrationError):
    """Pinned source not found in database."""

    code = "PINNED_SOURCE_NOT_FOUND"


class PinnedSourceIdentityMismatchError(NodeOrchestrationError):
    """Pinned source identity does not match database."""

    code = "PINNED_SOURCE_IDENTITY_MISMATCH"


class PinnedSourceNotVisibleError(NodeOrchestrationError):
    """Pinned source is not visible at forecast cutoff."""

    code = "PINNED_SOURCE_NOT_VISIBLE"


class PinnedSourceScopeMismatchError(NodeOrchestrationError):
    """Pinned source database scope does not match the rolling node scope."""

    code = "PINNED_SOURCE_SCOPE_MISMATCH"


class HistoricalSourceNotFoundError(NodeOrchestrationError):
    """No valid historical candidate exists for the requested source role/type."""

    code = "historical_source_not_found"


class HistoricalSourceNotVisibleError(NodeOrchestrationError):
    """Historical candidate(s) exist but none are visible at the forecast cutoff."""

    code = "historical_source_not_visible"


class AmbiguousHistoricalCandidateError(NodeOrchestrationError):
    """Same-priority historical candidates disagree semantically or by payload."""

    code = "ambiguous_historical_candidate"


class Task8ParentAuthorityMismatchError(NodeOrchestrationError):
    """Task 8 parent authority chain mismatch."""

    code = "TASK8_PARENT_AUTHORITY_MISMATCH"


class Task9Task8AuthorityMismatchError(NodeOrchestrationError):
    """Task 9 frozen Task 8 identity does not match resolved Task 8."""

    code = "TASK9_TASK8_AUTHORITY_MISMATCH"


class Task10Task9BindingMismatchError(NodeOrchestrationError):
    """Task 10 binding does not match Task 9 identity."""

    code = "TASK10_TASK9_BINDING_MISMATCH"


class Task10PredictionNotCompletedError(NodeOrchestrationError):
    """Task 10 prediction run is not completed or completed_at missing."""

    code = "TASK10_PREDICTION_NOT_COMPLETED"


class Task10PredictionAfterCutoffError(NodeOrchestrationError):
    """Task 10 prediction completed_at is after forecast_cutoff_at."""

    code = "TASK10_PREDICTION_AFTER_CUTOFF"


# ── Stage execution context ─────────────────────────────────────────────────


@dataclass
class _StageContext:
    """Mutable context accumulated during stage execution."""

    attempt_id: int
    node_id: int
    run_id: int
    resolved_inputs: dict[str, ResolvedInputOutcome]
    availability_audits: dict[str, AvailabilityAuditOutcome]
    attempt_number: int | None = None
    prior_attempt_id: int | None = None
    task9_authority: Task9AuthorityOutcome | None = None
    task10_authority: Task10AuthorityOutcome | None = None
    fallback_mode: str | None = None
    blocker_code: str | None = None
    active_stage: str | None = None
    last_completed_stage: str | None = None
    terminal_stage: str | None = None
    diagnostics: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.diagnostics is None:
            self.diagnostics = {}


# ── Pinned source verification ───────────────────────────────────────────────


async def _verify_pinned_source(
    session: AsyncSession,
    *,
    identity: ResolvedUpstreamSemanticIdentity,
    persistent_ref: PersistentUpstreamReference,
    audit_row: Any,
    forecast_cutoff_at: datetime,
    node_timezone: str,
    as_of_local_date: Any,
    execution_mode: ExecutionMode,
) -> ResolvedInputOutcome:
    """Verify a pinned source's database existence and integrity.

    §5.4 dispatch lift: the per-call ``execution_mode`` parameter
    replaces the previously-hardcoded
    ``ExecutionMode.HISTORICAL_OBSERVED`` literal. The caller
    (downstream replay-pipeline paths) supplies the explicit
    ``ExecutionMode`` so context tracks ``RollingBacktestConfig``.
    Note this helper is currently dead code (no callers in this
    module — kept for completeness); the parameter is required so
    that future replay-mode dispatch that does resurrect pinned paths
    is forced to pass the explicit mode rather than inheriting a
    hidden default.
    """
    from backend.app.rolling_backtest.schemas import AvailabilitySnapshot

    snapshot_adapter = __import__("pydantic").TypeAdapter(AvailabilitySnapshot)
    if audit_row is None:
        raise PinnedSourceNotFoundError(
            f"no availability audit for pinned source role={identity.source_role}"
        )

    snapshot = snapshot_adapter.validate_python(audit_row.canonical_payload)
    eval_result = evaluate_authority_visibility(
        snapshot=snapshot,
        execution_mode=execution_mode,
        forecast_cutoff_at=forecast_cutoff_at,
        as_of_local_date=as_of_local_date,
        business_timezone=node_timezone,
    )
    if not eval_result.allowed:
        raise PinnedSourceNotVisibleError(
            f"pinned source role={identity.source_role} blocked by {eval_result.blocker_code}"
        )

    available_at = _extract_authoritative_available_at(snapshot)

    return ResolvedInputOutcome(
        source_role=identity.source_role,
        source_type=identity.source_type,
        semantic_identity=identity,
        persistent_reference=persistent_ref,
        authoritative_available_at=available_at,
        canonical_identity_hash=sha256_payload(
            canonical_json_dumps(_resolved_input_canonical_payload(identity))
        ),
        canonical_payload_hash=identity.semantic.canonical_payload_hash or "",
    )


def _extract_authoritative_available_at(
    snapshot: AvailabilitySnapshot,
) -> datetime:
    """Extract the authoritative available_at timestamp from an availability snapshot."""
    if hasattr(snapshot, "authoritative_timestamp"):
        return snapshot.authoritative_timestamp
    if hasattr(snapshot, "available_at"):
        from datetime import datetime as _dt

        avail_date = snapshot.available_at
        if isinstance(avail_date, datetime):
            return avail_date
        return _dt(
            avail_date.year,
            avail_date.month,
            avail_date.day,
            tzinfo=UTC,
        )
    if hasattr(snapshot, "created_at"):
        return snapshot.created_at
    raise PinnedSourceIdentityMismatchError(
        "availability snapshot missing authoritative timestamp fields"
    )


def _task3_source_visibility_snapshot(
    build_run: AnalyticsBuildRun,
) -> Task3SourceVisibilityIdentity:
    assert build_run.finished_at is not None
    visible_through_at = build_run.finished_at
    visibility_manifest_hash = sha256_payload(
        {
            "visibility_policy_version": "task11-task3-source-visibility-v1",
            "source_max_raw_id": build_run.source_max_raw_id,
            "aggregation_version": build_run.aggregation_version,
            "config_hash": build_run.config_hash,
            "visible_through_at": visible_through_at,
        }
    )
    return Task3SourceVisibilityIdentity(
        visibility_policy_version="task11-task3-source-visibility-v1",
        source_max_raw_id=build_run.source_max_raw_id,
        aggregation_version=build_run.aggregation_version,
        config_hash=build_run.config_hash,
        visibility_manifest_hash=visibility_manifest_hash,
        visible_through_at=visible_through_at,
    )


def _require_database_ref(
    identity: ResolvedUpstreamSemanticIdentity,
    *,
    allowed_types: tuple[str, ...],
) -> int:
    ref = identity.persistent_reference
    if ref is None or ref.reference_type not in allowed_types:
        allowed = ",".join(allowed_types)
        raise PinnedSourceIdentityMismatchError(
            f"pinned source role={identity.source_role} must use persistent reference "
            f"type in {{{allowed}}}"
        )
    if not isinstance(ref.reference_value, int):
        raise PinnedSourceIdentityMismatchError(
            f"pinned source role={identity.source_role} must use integer persistent reference"
        )
    return ref.reference_value


def _coerce_persisted_date(value: Any, *, field_name: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise Task9Task8AuthorityMismatchError(
                f"Task 9 verification snapshot {field_name} is not a valid ISO date"
            ) from exc
    raise Task9Task8AuthorityMismatchError(
        f"Task 9 verification snapshot {field_name} is not a persisted date"
    )


def _local_midnight(value: Any, timezone_name: str) -> datetime:
    if not hasattr(value, "year") or not hasattr(value, "month") or not hasattr(value, "day"):
        raise PinnedSourceIdentityMismatchError(
            f"cannot derive authoritative local datetime for timezone={timezone_name}"
        )
    return datetime(value.year, value.month, value.day, tzinfo=ZoneInfo(timezone_name))


def _task9_source_catalog_hash(envelope: Any) -> str | None:
    source_ref_catalog = getattr(getattr(envelope, "output", None), "source_ref_catalog", None)
    if source_ref_catalog is None:
        return None
    normalized = [
        item.model_dump(mode="python") if hasattr(item, "model_dump") else item
        for item in source_ref_catalog
    ]
    return sha256_payload(normalized)


def _task9_verification_snapshot_hash(envelope: Any) -> str | None:
    input_snapshot = getattr(getattr(envelope, "output", None), "input_snapshot", None)
    if not isinstance(input_snapshot, dict):
        return None
    predictions = input_snapshot.get("task8_daily_predictions")
    if not isinstance(predictions, list):
        return None
    normalized: list[dict[str, Any]] = []
    for item in predictions:
        if not isinstance(item, dict):
            continue
        verification_snapshot = item.get("verification_snapshot")
        if verification_snapshot is None:
            continue
        normalized.append(
            {
                "source_ref_hash": item.get("source_ref_hash"),
                "verification_snapshot": verification_snapshot,
                "verification_snapshot_hash": item.get("verification_snapshot_hash"),
            }
        )
    normalized.sort(
        key=lambda item: (
            str(item.get("source_ref_hash") or ""),
            canonical_json_dumps(item.get("verification_snapshot")),
        )
    )
    return sha256_payload(normalized) if normalized else None


async def _load_task8_plan_for_scope(
    session: AsyncSession,
    *,
    forecast_row: MaturityForecastRun,
    node_season_id: int,
) -> FarmSeasonVarietyPlan:
    plan_row = cast(
        FarmSeasonVarietyPlan | None,
        await session.get(FarmSeasonVarietyPlan, forecast_row.plan_id),
    )
    if plan_row is None:
        raise Task8ParentAuthorityMismatchError(
            f"Task 8 forecast run {forecast_row.id} plan {forecast_row.plan_id} was not found"
        )
    if plan_row.season_id != node_season_id:
        raise PinnedSourceScopeMismatchError(
            f"Task 8 forecast run {forecast_row.id} plan season {plan_row.season_id} "
            f"does not match node season {node_season_id}"
        )
    return plan_row


@dataclass(frozen=True)
class _Task8DailyExactSet:
    target_dates: tuple[date, ...]
    db_daily_ids: frozenset[int]
    pinned_daily_ids: frozenset[int]
    task9_daily_ids: frozenset[int]
    db_date_to_id: dict[date, int]
    pinned_date_to_id: dict[date, int]
    task9_date_to_id: dict[date, int]
    db_rows_by_date: dict[date, MaturityDailyPredictionModel]


def _task8_daily_role_date(source_role: str) -> date:
    prefix = "task8_daily_prediction:"
    if not source_role.startswith(prefix):
        raise Task9Task8AuthorityMismatchError(
            f"Task 8 daily source role {source_role!r} is malformed"
        )
    try:
        return date.fromisoformat(source_role.removeprefix(prefix))
    except ValueError as exc:
        raise Task9Task8AuthorityMismatchError(
            f"Task 8 daily source role {source_role!r} does not carry an ISO date"
        ) from exc


async def _verify_task8_daily_exact_set(
    session: AsyncSession,
    *,
    forecast_run_id: int,
    pinned_daily_inputs: tuple[ResolvedInputOutcome, ...],
    task9_snapshot_rows: list[dict[str, Any]],
    source_ref_payload_by_hash: dict[str, dict[str, Any]],
) -> _Task8DailyExactSet:
    task9_rows_by_date: dict[date, list[dict[str, Any]]] = {}
    task9_date_to_id: dict[date, int] = {}
    task9_daily_ids: set[int] = set()

    for item in task9_snapshot_rows:
        if not isinstance(item, dict):
            raise Task9Task8AuthorityMismatchError(
                "Task 9 persisted envelope contains malformed Task 8 verification rows"
            )
        verification = item.get("verification_snapshot")
        if not isinstance(verification, dict):
            raise Task9Task8AuthorityMismatchError(
                "Task 9 persisted envelope contains malformed Task 8 verification snapshot"
            )
        prediction_date = _coerce_persisted_date(
            verification.get("prediction_date"),
            field_name="prediction_date",
        )
        daily_id = verification.get("maturity_daily_prediction_id")
        if not isinstance(daily_id, int):
            raise Task9Task8AuthorityMismatchError(
                "Task 9 verification snapshot daily prediction id must be an integer"
            )
        verification_forecast_run_id = verification.get("maturity_daily_prediction_forecast_run_id")
        if verification_forecast_run_id is None:
            verification_forecast_run_id = verification.get("maturity_forecast_run_id")
        if verification_forecast_run_id != forecast_run_id:
            raise Task9Task8AuthorityMismatchError(
                "Task 9 verification snapshot daily prediction forecast parent "
                "does not match pinned Task 8 forecast run"
            )
        forecast_quantile = verification.get("forecast_quantile")
        if forecast_quantile is None:
            source_ref_hash = item.get("source_ref_hash")
            if not isinstance(source_ref_hash, str) or not source_ref_hash:
                raise Task9Task8AuthorityMismatchError(
                    "Task 9 verification snapshot forecast quantile is missing "
                    "and source_ref_hash is absent"
                )
            source_ref_payload = source_ref_payload_by_hash.get(source_ref_hash)
            if not isinstance(source_ref_payload, dict):
                raise Task9Task8AuthorityMismatchError(
                    "Task 9 source_ref_hash is missing from source_ref_catalog"
                )
            forecast_quantile = source_ref_payload.get("forecast_quantile")
        if forecast_quantile not in {"P50", "P80", "P90"}:
            raise Task9Task8AuthorityMismatchError(
                "Task 9 verification snapshot forecast quantile is invalid"
            )
        task9_rows_by_date.setdefault(prediction_date, []).append(
            {
                "verification_snapshot": verification,
                "forecast_quantile": forecast_quantile,
                "daily_id": daily_id,
            }
        )
        task9_daily_ids.add(daily_id)

    for prediction_date, rows in task9_rows_by_date.items():
        quantiles = {cast(str, row["forecast_quantile"]) for row in rows}
        if quantiles != {"P50", "P80", "P90"} or len(rows) != 3:
            raise Task9Task8AuthorityMismatchError(
                "Task 9 verification snapshot does not carry exactly P50/P80/P90 per date"
            )
        daily_ids_for_date = {cast(int, row["daily_id"]) for row in rows}
        if len(daily_ids_for_date) != 1:
            raise Task9Task8AuthorityMismatchError(
                "Task 9 verification snapshot uses multiple daily ids for one date"
            )
        task9_date_to_id[prediction_date] = next(iter(daily_ids_for_date))

    target_dates = tuple(sorted(task9_rows_by_date))
    pinned_date_to_id: dict[date, int] = {}
    pinned_daily_ids: set[int] = set()
    for outcome in pinned_daily_inputs:
        prediction_date = _task8_daily_role_date(outcome.source_role)
        daily_id = _require_database_ref(
            outcome.semantic_identity,
            allowed_types=("database_row_id",),
        )
        if prediction_date in pinned_date_to_id:
            raise Task9Task8AuthorityMismatchError(
                "Pinned Task 8 daily predictions contain duplicate dates"
            )
        if daily_id in pinned_daily_ids:
            raise Task9Task8AuthorityMismatchError(
                "Pinned Task 8 daily predictions contain duplicate persistent references"
            )
        pinned_date_to_id[prediction_date] = daily_id
        pinned_daily_ids.add(daily_id)

    if set(pinned_date_to_id) != set(target_dates):
        raise Task9Task8AuthorityMismatchError(
            "Pinned Task 8 daily prediction date set does not match Task 9 verification dates"
        )

    result = await session.execute(
        select(MaturityDailyPredictionModel).where(
            MaturityDailyPredictionModel.forecast_run_id == forecast_run_id,
            MaturityDailyPredictionModel.prediction_date.in_(target_dates),
        )
    )
    db_rows = result.scalars().all()
    db_rows_by_date: dict[date, MaturityDailyPredictionModel] = {}
    db_daily_ids: set[int] = set()
    for row in db_rows:
        if row.prediction_date in db_rows_by_date:
            raise Task9Task8AuthorityMismatchError(
                "Task 8 forecast run contains duplicate daily rows for one date"
            )
        if row.forecast_run_id != forecast_run_id:
            raise Task9Task8AuthorityMismatchError(
                "Task 8 daily prediction database row has unexpected parent forecast run"
            )
        db_rows_by_date[row.prediction_date] = row
        db_daily_ids.add(row.id)

    if set(db_rows_by_date) != set(target_dates):
        raise Task9Task8AuthorityMismatchError(
            "Task 8 daily prediction database date set does not match Task 9 verification dates"
        )

    db_date_to_id = {prediction_date: row.id for prediction_date, row in db_rows_by_date.items()}
    if db_date_to_id != task9_date_to_id:
        raise Task9Task8AuthorityMismatchError(
            "Task 9 verification snapshot date-to-daily mapping does not match database rows"
        )
    if db_date_to_id != pinned_date_to_id:
        raise Task9Task8AuthorityMismatchError(
            "Pinned Task 8 daily prediction date-to-daily mapping does not match database rows"
        )

    return _Task8DailyExactSet(
        target_dates=target_dates,
        db_daily_ids=frozenset(db_daily_ids),
        pinned_daily_ids=frozenset(pinned_daily_ids),
        task9_daily_ids=frozenset(task9_daily_ids),
        db_date_to_id=db_date_to_id,
        pinned_date_to_id=pinned_date_to_id,
        task9_date_to_id=task9_date_to_id,
        db_rows_by_date=db_rows_by_date,
    )


async def _load_exact_pinned_candidate(
    session: AsyncSession,
    node: RollingNodeDefinition,
    identity: ResolvedUpstreamSemanticIdentity,
) -> HistoricalCandidate:
    source_type = identity.source_type

    if source_type == AvailabilitySourceType.TASK3_ANALYTICS_BUILD:
        run_id = _require_database_ref(identity, allowed_types=("database_run_id",))
        build_run = cast(AnalyticsBuildRun | None, await session.get(AnalyticsBuildRun, run_id))
        if build_run is None or build_run.finished_at is None:
            raise PinnedSourceNotFoundError(
                f"pinned source role={identity.source_role} ref={run_id} was not found"
            )
        if build_run.season_id != node.season_id:
            raise PinnedSourceScopeMismatchError(
                f"Task 3 analytics build season {build_run.season_id} "
                f"does not match node season {node.season_id}"
            )
        exact_identity = _make_identity(
            source_type=source_type,
            source_role="task3_analytics_build",
            schema_version="task3-analytics-v1",
            semantic_payload_hash=build_run.config_hash or "",
            config_hash=build_run.config_hash,
            business_version=build_run.aggregation_version,
            display_label=f"task3:analytics_build:season{build_run.season_id}",
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=build_run.id,
            ),
        )
        return HistoricalCandidate(
            source_role="task3_analytics_build",
            source_type=source_type,
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=build_run.id,
            ),
            semantic_identity=exact_identity,
            authoritative_available_at=build_run.finished_at,
            business_version=build_run.aggregation_version,
            canonical_payload_hash=build_run.config_hash or "",
        )

    if source_type == AvailabilitySourceType.TASK6_PLAN_VERSION:
        run_id = _require_database_ref(identity, allowed_types=("database_run_id",))
        plan_run = cast(
            ProductionPlanImportRun | None,
            await session.get(ProductionPlanImportRun, run_id),
        )
        if plan_run is None or plan_run.finished_at is None:
            raise PinnedSourceNotFoundError(
                f"pinned source role={identity.source_role} ref={run_id} was not found"
            )
        exact_identity = _make_identity(
            source_type=source_type,
            source_role="task6_plan_version",
            schema_version="task6-plan-v1",
            semantic_payload_hash=plan_run.file_sha256,
            canonical_payload_hash=plan_run.file_sha256,
            business_version=plan_run.source_version,
            display_label="task6:plan_version",
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=plan_run.id,
            ),
        )
        return HistoricalCandidate(
            source_role="task6_plan_version",
            source_type=source_type,
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=plan_run.id,
            ),
            semantic_identity=exact_identity,
            authoritative_available_at=plan_run.finished_at,
            business_version=plan_run.source_version,
            canonical_payload_hash=plan_run.file_sha256,
        )

    if source_type == AvailabilitySourceType.TASK7_WEATHER_FEATURE_RUN:
        run_id = _require_database_ref(identity, allowed_types=("database_run_id",))
        feature_run = cast(WeatherFeatureRun | None, await session.get(WeatherFeatureRun, run_id))
        if feature_run is None or feature_run.finished_at is None:
            raise PinnedSourceNotFoundError(
                f"pinned source role={identity.source_role} ref={run_id} was not found"
            )
        exact_identity = _make_identity(
            source_type=source_type,
            source_role="task7_weather_feature_run",
            schema_version="task7-weather-v1",
            semantic_payload_hash=feature_run.source_signature,
            config_hash=feature_run.config_hash,
            business_version=feature_run.feature_version,
            display_label="task7:weather_feature_run",
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=feature_run.id,
            ),
        )
        return HistoricalCandidate(
            source_role="task7_weather_feature_run",
            source_type=source_type,
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=feature_run.id,
            ),
            semantic_identity=exact_identity,
            authoritative_available_at=feature_run.finished_at,
            business_version=feature_run.feature_version,
            canonical_payload_hash=feature_run.source_signature,
        )

    if source_type == AvailabilitySourceType.TASK7_LOCATION_WEATHER_MAPPING:
        row_id = _require_database_ref(identity, allowed_types=("database_run_id",))
        mapping_row = cast(
            LocationWeatherMapping | None,
            await session.get(LocationWeatherMapping, row_id),
        )
        if mapping_row is None:
            raise PinnedSourceNotFoundError(
                f"pinned source role={identity.source_role} ref={row_id} was not found"
            )
        exact_identity = _make_identity(
            source_type=source_type,
            source_role="task7_location_weather_mapping",
            schema_version="task7-weather-v1",
            semantic_payload_hash=mapping_row.row_hash,
            config_hash=mapping_row.config_hash,
            business_version=mapping_row.mapping_version,
            display_label="task7:location_weather_mapping",
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=mapping_row.id,
            ),
        )
        return HistoricalCandidate(
            source_role="task7_location_weather_mapping",
            source_type=source_type,
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=mapping_row.id,
            ),
            semantic_identity=exact_identity,
            authoritative_available_at=_local_midnight(mapping_row.available_at, node.timezone),
            business_version=mapping_row.mapping_version,
            canonical_payload_hash=mapping_row.row_hash,
        )

    if source_type == AvailabilitySourceType.TASK7_WEATHER_OBSERVATION:
        row_id = _require_database_ref(identity, allowed_types=("database_run_id",))
        observation_row = cast(
            WeatherDailyObservation | None,
            await session.get(WeatherDailyObservation, row_id),
        )
        if observation_row is None:
            raise PinnedSourceNotFoundError(
                f"pinned source role={identity.source_role} ref={row_id} was not found"
            )
        exact_identity = _make_identity(
            source_type=source_type,
            source_role="task7_weather_observation",
            schema_version="task7-weather-v1",
            semantic_payload_hash=observation_row.row_hash,
            canonical_payload_hash=observation_row.row_hash,
            business_version=observation_row.source_version,
            display_label="task7:weather_observation",
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=observation_row.id,
            ),
        )
        return HistoricalCandidate(
            source_role="task7_weather_observation",
            source_type=source_type,
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=observation_row.id,
            ),
            semantic_identity=exact_identity,
            authoritative_available_at=_local_midnight(observation_row.available_at, node.timezone),
            business_version=observation_row.source_version,
            canonical_payload_hash=observation_row.row_hash,
        )

    if source_type == AvailabilitySourceType.TASK8_MODEL_RUN:
        run_id = _require_database_ref(identity, allowed_types=("database_run_id",))
        model_run_row = cast(MaturityModelRun | None, await session.get(MaturityModelRun, run_id))
        if model_run_row is None or model_run_row.finished_at is None:
            raise PinnedSourceNotFoundError(
                f"pinned source role={identity.source_role} ref={run_id} was not found"
            )
        await load_maturity_model_result(session, run_id=run_id)
        exact_identity = _make_identity(
            source_type=source_type,
            source_role="task8_model_run",
            schema_version="task8-maturity-v1",
            semantic_payload_hash=model_run_row.config_hash,
            config_hash=model_run_row.config_hash,
            business_version=model_run_row.model_version,
            display_label="task8:model_run",
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=model_run_row.id,
            ),
        )
        return HistoricalCandidate(
            source_role="task8_model_run",
            source_type=source_type,
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=model_run_row.id,
            ),
            semantic_identity=exact_identity,
            authoritative_available_at=model_run_row.finished_at,
            business_version=model_run_row.model_version,
            canonical_payload_hash=model_run_row.config_hash,
        )

    if source_type == AvailabilitySourceType.TASK8_MODEL_ARTIFACT:
        artifact_id = _require_database_ref(
            identity,
            allowed_types=("database_artifact_id",),
        )
        model_artifact_row = cast(
            MaturityModelArtifact | None,
            await session.get(MaturityModelArtifact, artifact_id),
        )
        if model_artifact_row is None:
            raise PinnedSourceNotFoundError(
                f"pinned source role={identity.source_role} ref={artifact_id} was not found"
            )
        parent_model_run = cast(
            MaturityModelRun | None,
            await session.get(MaturityModelRun, model_artifact_row.run_id),
        )
        if parent_model_run is None:
            raise Task8ParentAuthorityMismatchError(
                f"Task 8 model artifact {artifact_id} parent model run was not found"
            )
        await load_maturity_model_result(session, run_id=parent_model_run.id)
        exact_identity = _make_identity(
            source_type=source_type,
            source_role="task8_model_artifact",
            schema_version="task8-maturity-v1",
            semantic_payload_hash=model_artifact_row.artifact_hash,
            config_hash=parent_model_run.config_hash,
            business_version=parent_model_run.model_version,
            display_label="task8:model_artifact",
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_artifact_id",
                reference_value=model_artifact_row.id,
            ),
        )
        return HistoricalCandidate(
            source_role="task8_model_artifact",
            source_type=source_type,
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_artifact_id",
                reference_value=model_artifact_row.id,
            ),
            semantic_identity=exact_identity,
            authoritative_available_at=model_artifact_row.created_at,
            business_version=parent_model_run.model_version,
            canonical_payload_hash=model_artifact_row.artifact_hash,
        )

    if source_type == AvailabilitySourceType.TASK8_FORECAST_RUN:
        run_id = _require_database_ref(identity, allowed_types=("database_run_id",))
        forecast_run_row = cast(
            MaturityForecastRun | None,
            await session.get(MaturityForecastRun, run_id),
        )
        if forecast_run_row is None or forecast_run_row.finished_at is None:
            raise PinnedSourceNotFoundError(
                f"pinned source role={identity.source_role} ref={run_id} was not found"
            )
        await load_maturity_forecast_result(session, run_id=run_id)
        await _load_task8_plan_for_scope(
            session,
            forecast_row=forecast_run_row,
            node_season_id=node.season_id,
        )
        exact_identity = _make_identity(
            source_type=source_type,
            source_role="task8_forecast_run",
            schema_version="task8-maturity-v1",
            semantic_payload_hash=forecast_run_row.source_signature,
            input_signature=forecast_run_row.source_signature,
            display_label="task8:forecast_run",
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=forecast_run_row.id,
            ),
        )
        return HistoricalCandidate(
            source_role="task8_forecast_run",
            source_type=source_type,
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=forecast_run_row.id,
            ),
            semantic_identity=exact_identity,
            authoritative_available_at=forecast_run_row.finished_at,
        )

    if source_type == AvailabilitySourceType.TASK8_DAILY_PREDICTION:
        row_id = _require_database_ref(identity, allowed_types=("database_row_id",))
        daily_prediction_row = cast(
            MaturityDailyPredictionModel | None,
            await session.get(MaturityDailyPredictionModel, row_id),
        )
        if daily_prediction_row is None:
            raise PinnedSourceNotFoundError(
                f"pinned source role={identity.source_role} ref={row_id} was not found"
            )
        parent_forecast_run = cast(
            MaturityForecastRun | None,
            await session.get(MaturityForecastRun, daily_prediction_row.forecast_run_id),
        )
        if parent_forecast_run is None:
            raise Task8ParentAuthorityMismatchError(
                f"Task 8 daily prediction {row_id} parent forecast run was not found"
            )
        await load_maturity_forecast_result(session, run_id=parent_forecast_run.id)
        await _load_task8_plan_for_scope(
            session,
            forecast_row=parent_forecast_run,
            node_season_id=node.season_id,
        )
        daily_payload_hash = _task8_daily_prediction_payload_hash(
            daily_prediction_row,
            forecast_source_signature=parent_forecast_run.source_signature,
        )
        exact_identity = _make_identity(
            source_type=source_type,
            source_role=identity.source_role,
            role_qualifier=identity.role_qualifier,
            schema_version="task8-maturity-v1",
            semantic_payload_hash=daily_payload_hash,
            input_signature=parent_forecast_run.source_signature,
            canonical_payload_hash=daily_payload_hash,
            business_version=identity.semantic.business_version,
            policy_version=identity.semantic.policy_version,
            display_label="task8:daily_prediction",
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_row_id",
                reference_value=daily_prediction_row.id,
            ),
        )
        return HistoricalCandidate(
            source_role=identity.source_role,
            source_type=source_type,
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_row_id",
                reference_value=daily_prediction_row.id,
            ),
            semantic_identity=exact_identity,
            authoritative_available_at=daily_prediction_row.created_at,
        )

    if source_type == AvailabilitySourceType.TASK9_HARVEST_STATE_RUN:
        run_id = _require_database_ref(identity, allowed_types=("database_run_id",))
        harvest_run_row = cast(HarvestStateRun | None, await session.get(HarvestStateRun, run_id))
        if harvest_run_row is None:
            raise PinnedSourceNotFoundError(
                f"pinned source role={identity.source_role} ref={run_id} was not found"
            )
        envelope = await get_harvest_state_run_by_id(session, run_id=run_id)
        exact_identity = _make_identity(
            source_type=source_type,
            source_role="task9_structural_forecast",
            schema_version=harvest_run_row.output_schema_version,
            semantic_payload_hash=harvest_run_row.result_hash,
            config_hash=harvest_run_row.config_hash,
            result_hash=harvest_run_row.result_hash,
            canonical_payload_hash=harvest_run_row.canonical_payload_hash,
            business_version=harvest_run_row.output_schema_version,
            display_label="task9:harvest_state",
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=harvest_run_row.id,
            ),
        )
        return HistoricalCandidate(
            source_role="task9_structural_forecast",
            source_type=source_type,
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=harvest_run_row.id,
            ),
            semantic_identity=exact_identity,
            authoritative_available_at=envelope.created_at,
            business_version=harvest_run_row.output_schema_version,
            canonical_payload_hash=harvest_run_row.canonical_payload_hash,
        )

    if source_type == AvailabilitySourceType.TASK10_TRAINING_RUN:
        run_id = _require_database_ref(identity, allowed_types=("database_run_id",))
        training_run_row = cast(
            ResidualModelTrainingRun | None,
            await session.get(ResidualModelTrainingRun, run_id),
        )
        loaded_training = await load_residual_training_run_by_id(session, run_id=run_id)
        if (
            training_run_row is None
            or training_run_row.finished_at is None
            or loaded_training is None
        ):
            raise PinnedSourceNotFoundError(
                f"pinned source role={identity.source_role} ref={run_id} was not found"
            )
        exact_identity = _make_identity(
            source_type=source_type,
            source_role="task10_training_run",
            schema_version=training_run_row.feature_schema_version,
            semantic_payload_hash=training_run_row.training_signature,
            config_hash=training_run_row.config_hash,
            result_hash=training_run_row.canonical_payload_hash,
            canonical_payload_hash=training_run_row.canonical_payload_hash,
            business_version=training_run_row.model_version,
            display_label="task10:training_run",
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=training_run_row.id,
            ),
        )
        return HistoricalCandidate(
            source_role="task10_training_run",
            source_type=source_type,
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=training_run_row.id,
            ),
            semantic_identity=exact_identity,
            authoritative_available_at=training_run_row.finished_at,
            business_version=training_run_row.model_version,
            canonical_payload_hash=training_run_row.canonical_payload_hash,
        )

    if source_type == AvailabilitySourceType.TASK10_MODEL_ARTIFACT:
        artifact_id = _require_database_ref(
            identity,
            allowed_types=("database_artifact_id",),
        )
        residual_artifact_row = cast(
            ResidualModelArtifact | None,
            await session.get(ResidualModelArtifact, artifact_id),
        )
        if residual_artifact_row is None:
            raise PinnedSourceNotFoundError(
                f"pinned source role={identity.source_role} ref={artifact_id} was not found"
            )
        trusted_artifacts = await load_and_validate_trusted_residual_artifacts(
            session,
            run_id=residual_artifact_row.training_run_id,
        )
        if not any(
            item.metadata.binary_sha256 == residual_artifact_row.artifact_sha256
            for item in trusted_artifacts
        ):
            raise Task10Task9BindingMismatchError(
                f"Task 10 artifact {artifact_id} failed trusted artifact validation"
            )
        exact_identity = _make_identity(
            source_type=source_type,
            source_role="task10_model_artifact",
            schema_version=residual_artifact_row.feature_schema_version,
            semantic_payload_hash=residual_artifact_row.artifact_sha256,
            config_hash=residual_artifact_row.config_hash,
            artifact_payload_hash=residual_artifact_row.artifact_sha256,
            business_version=residual_artifact_row.artifact_schema_version,
            display_label="task10:model_artifact",
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_artifact_id",
                reference_value=residual_artifact_row.id,
            ),
        )
        return HistoricalCandidate(
            source_role="task10_model_artifact",
            source_type=source_type,
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_artifact_id",
                reference_value=residual_artifact_row.id,
            ),
            semantic_identity=exact_identity,
            authoritative_available_at=residual_artifact_row.created_at,
            business_version=residual_artifact_row.artifact_schema_version,
            canonical_payload_hash=residual_artifact_row.artifact_sha256,
        )

    if source_type == AvailabilitySourceType.TASK10_PREDICTION_RUN:
        run_id = _require_database_ref(identity, allowed_types=("database_run_id",))
        prediction_run_row = cast(
            ResidualModelPredictionRun | None,
            await session.get(ResidualModelPredictionRun, run_id),
        )
        loaded_prediction = await load_residual_prediction_run_by_id(session, run_id=run_id)
        if (
            prediction_run_row is None
            or prediction_run_row.completed_at is None
            or loaded_prediction is None
        ):
            raise PinnedSourceNotFoundError(
                f"pinned source role={identity.source_role} ref={run_id} was not found"
            )
        exact_identity = _make_identity(
            source_type=source_type,
            source_role="task10_prediction_run",
            schema_version=prediction_run_row.feature_schema_version,
            semantic_payload_hash=prediction_run_row.prediction_hash,
            config_hash=prediction_run_row.config_hash,
            result_hash=prediction_run_row.prediction_hash,
            canonical_payload_hash=prediction_run_row.prediction_hash,
            input_signature=prediction_run_row.prediction_input_signature,
            business_version=prediction_run_row.feature_schema_version,
            display_label="task10:prediction_run",
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=prediction_run_row.id,
            ),
        )
        return HistoricalCandidate(
            source_role="task10_prediction_run",
            source_type=source_type,
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=prediction_run_row.id,
            ),
            semantic_identity=exact_identity,
            authoritative_available_at=prediction_run_row.completed_at,
            business_version=prediction_run_row.feature_schema_version,
            canonical_payload_hash=prediction_run_row.prediction_hash,
        )

    raise PinnedSourceNotFoundError(
        f"exact pinned loader is not implemented for source type {source_type.value}"
    )


# ── Task 8 reuse (stage 4) ──────────────────────────────────────────────────


async def _resolve_task8_reuse(
    session: AsyncSession,
    ctx: _StageContext,
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
    *,
    resolved_inputs: dict[str, ResolvedInputOutcome],
) -> None:
    """Stage 4: Reuse persisted Task 8 authorities.

    For historical_observed + pinned: exact-load Task 8 model run, artifact,
    forecast run, and daily predictions. Verify integrity.
    """
    # Find Task 8 related inputs
    task8_inputs = {
        role: outcome
        for role, outcome in resolved_inputs.items()
        if outcome.source_type.value.startswith("task8_")
    }
    if not task8_inputs:
        return  # No Task 8 inputs required

    model_run = next(
        (
            outcome
            for outcome in task8_inputs.values()
            if outcome.source_type == AvailabilitySourceType.TASK8_MODEL_RUN
        ),
        None,
    )
    model_artifact = next(
        (
            outcome
            for outcome in task8_inputs.values()
            if outcome.source_type == AvailabilitySourceType.TASK8_MODEL_ARTIFACT
        ),
        None,
    )
    forecast_run = next(
        (
            outcome
            for outcome in task8_inputs.values()
            if outcome.source_type == AvailabilitySourceType.TASK8_FORECAST_RUN
        ),
        None,
    )

    if model_run is not None:
        model_run_id = _require_database_ref(
            model_run.semantic_identity,
            allowed_types=("database_run_id",),
        )
        loaded_model = await load_maturity_model_result(session, run_id=model_run_id)
        if loaded_model.status != "completed":
            raise Task8ParentAuthorityMismatchError(
                f"Task 8 model run {model_run_id} must be completed"
            )

    if model_artifact is not None:
        artifact_id = _require_database_ref(
            model_artifact.semantic_identity,
            allowed_types=("database_artifact_id",),
        )
        artifact_row = await session.get(MaturityModelArtifact, artifact_id)
        if artifact_row is None:
            raise Task8ParentAuthorityMismatchError(
                f"Task 8 model artifact {artifact_id} was not found"
            )
        if model_run is None:
            raise Task8ParentAuthorityMismatchError(
                "Task 8 model artifact has no parent model run in resolved inputs"
            )
        model_run_id = _require_database_ref(
            model_run.semantic_identity,
            allowed_types=("database_run_id",),
        )
        if artifact_row.run_id != model_run_id:
            raise Task8ParentAuthorityMismatchError(
                f"Task 8 model artifact {artifact_id} parent mismatch"
            )

    if forecast_run is not None:
        forecast_run_id = _require_database_ref(
            forecast_run.semantic_identity,
            allowed_types=("database_run_id",),
        )
        loaded_forecast = await load_maturity_forecast_result(session, run_id=forecast_run_id)
        forecast_row = await session.get(MaturityForecastRun, forecast_run_id)
        if forecast_row is None:
            raise Task8ParentAuthorityMismatchError(
                f"Task 8 forecast run {forecast_run_id} was not found"
            )
        if loaded_forecast.status != "completed":
            raise Task8ParentAuthorityMismatchError(
                f"Task 8 forecast run {forecast_run_id} must be completed"
            )
        if model_run is not None:
            model_run_id = _require_database_ref(
                model_run.semantic_identity,
                allowed_types=("database_run_id",),
            )
            if forecast_row.model_run_id != model_run_id:
                raise Task8ParentAuthorityMismatchError(
                    f"Task 8 forecast run {forecast_run_id} model parent mismatch"
                )
        if model_artifact is not None:
            artifact_id = _require_database_ref(
                model_artifact.semantic_identity,
                allowed_types=("database_artifact_id",),
            )
            if forecast_row.artifact_id != artifact_id:
                raise Task8ParentAuthorityMismatchError(
                    f"Task 8 forecast run {forecast_run_id} artifact parent mismatch"
                )

    for outcome in task8_inputs.values():
        if outcome.source_type != AvailabilitySourceType.TASK8_DAILY_PREDICTION:
            continue
        daily_id = _require_database_ref(
            outcome.semantic_identity,
            allowed_types=("database_row_id",),
        )
        daily_row = await session.get(MaturityDailyPredictionModel, daily_id)
        if daily_row is None:
            raise Task8ParentAuthorityMismatchError(
                f"Task 8 daily prediction {daily_id} was not found"
            )
        if forecast_run is None:
            raise Task8ParentAuthorityMismatchError(
                "Task 8 daily prediction has no parent forecast run in resolved inputs"
            )
        forecast_run_id = _require_database_ref(
            forecast_run.semantic_identity,
            allowed_types=("database_run_id",),
        )
        if daily_row.forecast_run_id != forecast_run_id:
            raise Task8ParentAuthorityMismatchError(
                f"Task 8 daily prediction {daily_id} parent forecast mismatch"
            )


# ── Task 9 reuse (stage 5) ──────────────────────────────────────────────────


async def _resolve_task9_reuse(
    ctx: _StageContext,
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
    *,
    session: AsyncSession,
    resolved_inputs: dict[str, ResolvedInputOutcome],
) -> None:
    """Stage 5: Reuse persisted Task 9 harvest state.

    Verify: status == completed, result_hash, config_hash,
    frozen Task 8 identities match.
    """
    task9_inputs = {
        role: outcome
        for role, outcome in resolved_inputs.items()
        if outcome.source_type.value == "task9_harvest_state_run"
    }
    if not task9_inputs:
        return

    task9_outcome = next(iter(task9_inputs.values()))
    ref = task9_outcome.persistent_reference
    if ref.reference_type != "database_run_id" or not isinstance(ref.reference_value, int):
        raise PinnedSourceIdentityMismatchError("Task 9 pinned reference must be database_run_id")
    envelope = await get_harvest_state_run_by_id(session, run_id=ref.reference_value)
    if envelope.status != "completed":
        raise Task9Task8AuthorityMismatchError("Task 9 persisted envelope must be completed")

    source_ref_catalog = (
        getattr(getattr(envelope, "output", None), "source_ref_catalog", None) or []
    )
    source_ref_payload_by_hash: dict[str, dict[str, Any]] = {
        entry.source_ref_hash: dict(entry.source_ref_payload)
        for entry in source_ref_catalog
        if isinstance(getattr(entry, "source_ref_hash", None), str)
        and isinstance(getattr(entry, "source_ref_payload", None), dict)
    }

    task8_inputs = {
        outcome.source_type: outcome
        for outcome in resolved_inputs.values()
        if outcome.source_type.value.startswith("task8_")
    }
    task8_snapshot_rows = envelope.output.input_snapshot.get("task8_daily_predictions", [])
    if task8_inputs and not isinstance(task8_snapshot_rows, list):
        raise Task9Task8AuthorityMismatchError(
            "Task 9 persisted envelope is missing Task 8 verification snapshots"
        )

    model_run = task8_inputs.get(AvailabilitySourceType.TASK8_MODEL_RUN)
    model_run_row: MaturityModelRun | None = None
    if model_run is not None:
        model_run_id = _require_database_ref(
            model_run.semantic_identity,
            allowed_types=("database_run_id",),
        )
        model_run_row = cast(
            MaturityModelRun | None,
            await session.get(MaturityModelRun, model_run_id),
        )
        if model_run_row is None:
            raise PinnedSourceNotFoundError(f"Task 8 model run {model_run_id} was not found")

    model_artifact = task8_inputs.get(AvailabilitySourceType.TASK8_MODEL_ARTIFACT)
    model_artifact_row: MaturityModelArtifact | None = None
    if model_artifact is not None:
        artifact_ref_id = _require_database_ref(
            model_artifact.semantic_identity,
            allowed_types=("database_artifact_id",),
        )
        model_artifact_row = cast(
            MaturityModelArtifact | None,
            await session.get(MaturityModelArtifact, artifact_ref_id),
        )
        if model_artifact_row is None:
            raise PinnedSourceNotFoundError(
                f"Task 8 model artifact {artifact_ref_id} was not found"
            )

    forecast_run = task8_inputs.get(AvailabilitySourceType.TASK8_FORECAST_RUN)
    forecast_run_id: int | None = None
    forecast_row: MaturityForecastRun | None = None
    plan_row: FarmSeasonVarietyPlan | None = None
    if forecast_run is not None:
        forecast_run_id = _require_database_ref(
            forecast_run.semantic_identity,
            allowed_types=("database_run_id",),
        )
        forecast_row = cast(
            MaturityForecastRun | None,
            await session.get(MaturityForecastRun, forecast_run_id),
        )
        if forecast_row is None:
            raise PinnedSourceNotFoundError(f"Task 8 forecast run {forecast_run_id} was not found")
        plan_row = await _load_task8_plan_for_scope(
            session,
            forecast_row=forecast_row,
            node_season_id=node.season_id,
        )

    for item in task8_snapshot_rows:
        if not isinstance(item, dict):
            raise Task9Task8AuthorityMismatchError(
                "Task 9 persisted envelope contains malformed Task 8 verification rows"
            )
        verification = item.get("verification_snapshot")
        if not isinstance(verification, dict):
            raise Task9Task8AuthorityMismatchError(
                "Task 9 persisted envelope contains malformed Task 8 verification snapshot"
            )
        prediction_date = _coerce_persisted_date(
            verification.get("prediction_date"),
            field_name="prediction_date",
        )
        forecast_as_of_date = _coerce_persisted_date(
            verification.get("maturity_forecast_as_of_date"),
            field_name="maturity_forecast_as_of_date",
        )
        forecast_start_date = _coerce_persisted_date(
            verification.get("maturity_forecast_prediction_start_date"),
            field_name="maturity_forecast_prediction_start_date",
        )
        forecast_end_date = _coerce_persisted_date(
            verification.get("maturity_forecast_prediction_end_date"),
            field_name="maturity_forecast_prediction_end_date",
        )
        verification_model_run_id = (
            _require_database_ref(
                model_run.semantic_identity,
                allowed_types=("database_run_id",),
            )
            if model_run is not None
            else None
        )
        if (
            model_run is not None
            and verification.get("maturity_model_run_id") != verification_model_run_id
        ):
            raise Task9Task8AuthorityMismatchError(
                "Task 9 verification snapshot model_run_id does not match pinned Task 8 model run"
            )
        if model_artifact is not None:
            artifact_ref_id = _require_database_ref(
                model_artifact.semantic_identity,
                allowed_types=("database_artifact_id",),
            )
            if verification.get("maturity_model_artifact_id") != artifact_ref_id:
                raise Task9Task8AuthorityMismatchError(
                    "Task 9 verification snapshot artifact_id does not match pinned Task 8 artifact"
                )
            expected_artifact_hash = model_artifact.canonical_payload_hash
            if (
                expected_artifact_hash
                and verification.get("maturity_model_artifact_hash") != expected_artifact_hash
            ):
                raise Task9Task8AuthorityMismatchError(
                    "Task 9 verification snapshot artifact_hash "
                    "does not match pinned Task 8 artifact"
                )
        if (
            forecast_run is not None
            and verification.get("maturity_forecast_run_id") != forecast_run_id
        ):
            raise Task9Task8AuthorityMismatchError(
                "Task 9 verification snapshot forecast_run_id "
                "does not match pinned Task 8 forecast run"
            )
        if forecast_row is not None:
            if verification.get("maturity_forecast_run_status") not in {
                None,
                forecast_row.status,
            }:
                raise Task9Task8AuthorityMismatchError(
                    "Task 9 verification snapshot forecast run status "
                    "does not match pinned Task 8 forecast"
                )
            if verification.get("maturity_forecast_model_run_id") != forecast_row.model_run_id:
                raise Task9Task8AuthorityMismatchError(
                    "Task 9 verification snapshot forecast model parent "
                    "does not match pinned Task 8 forecast"
                )
            if verification.get("maturity_forecast_artifact_id") != forecast_row.artifact_id:
                raise Task9Task8AuthorityMismatchError(
                    "Task 9 verification snapshot forecast artifact parent "
                    "does not match pinned Task 8 forecast"
                )
            if (
                verification.get("maturity_forecast_source_signature")
                != forecast_row.source_signature
            ):
                raise Task9Task8AuthorityMismatchError(
                    "Task 9 verification snapshot forecast source signature "
                    "does not match pinned Task 8 forecast"
                )
            if forecast_as_of_date != forecast_row.as_of_date:
                raise Task9Task8AuthorityMismatchError(
                    "Task 9 verification snapshot forecast as-of date "
                    "does not match pinned Task 8 forecast"
                )
            if forecast_start_date != forecast_row.prediction_start_date:
                raise Task9Task8AuthorityMismatchError(
                    "Task 9 verification snapshot forecast prediction start "
                    "does not match pinned Task 8 forecast"
                )
            if forecast_end_date != forecast_row.prediction_end_date:
                raise Task9Task8AuthorityMismatchError(
                    "Task 9 verification snapshot forecast prediction end "
                    "does not match pinned Task 8 forecast"
                )
            if verification.get("location_reference_id") != forecast_row.location_reference_id:
                raise Task9Task8AuthorityMismatchError(
                    "Task 9 verification snapshot location reference "
                    "does not match pinned Task 8 forecast"
                )
            if verification.get("weather_mapping_id") not in {
                None,
                forecast_row.weather_mapping_id,
            }:
                raise Task9Task8AuthorityMismatchError(
                    "Task 9 verification snapshot weather mapping "
                    "does not match pinned Task 8 forecast"
                )
            if verification.get("base_temperature_search_run_id") not in {
                None,
                forecast_row.base_temperature_search_run_id,
            }:
                raise Task9Task8AuthorityMismatchError(
                    "Task 9 verification snapshot base temperature search run "
                    "does not match pinned Task 8 forecast"
                )
        if model_run_row is not None:
            if verification.get("maturity_model_version") not in {
                None,
                model_run_row.model_version,
            }:
                raise Task9Task8AuthorityMismatchError(
                    "Task 9 verification snapshot model version "
                    "does not match pinned Task 8 model run"
                )
            if (
                verification.get("maturity_model_config_hash") is not None
                and verification.get("maturity_model_config_hash") != model_run_row.config_hash
            ):
                raise Task9Task8AuthorityMismatchError(
                    "Task 9 verification snapshot model config hash "
                    "does not match pinned Task 8 model run"
                )
            if (
                verification.get("maturity_model_source_signature") is not None
                and verification.get("maturity_model_source_signature")
                != model_run_row.source_signature
            ):
                raise Task9Task8AuthorityMismatchError(
                    "Task 9 verification snapshot model source signature "
                    "does not match pinned Task 8 model run"
                )
        if model_artifact_row is not None and verification.get(
            "maturity_model_artifact_run_id"
        ) not in {
            None,
            model_artifact_row.run_id,
        }:
            raise Task9Task8AuthorityMismatchError(
                "Task 9 verification snapshot model artifact parent run "
                "does not match pinned Task 8 artifact"
            )
        if plan_row is not None:
            if verification.get("plan_id") != plan_row.id:
                raise Task9Task8AuthorityMismatchError(
                    "Task 9 verification snapshot plan id does not match pinned Task 8 plan"
                )
            if verification.get("farm_id") != plan_row.farm_id:
                raise Task9Task8AuthorityMismatchError(
                    "Task 9 verification snapshot farm id does not match pinned Task 8 plan"
                )
            if verification.get("subfarm_id") != plan_row.subfarm_id:
                raise Task9Task8AuthorityMismatchError(
                    "Task 9 verification snapshot subfarm id does not match pinned Task 8 plan"
                )
            if verification.get("variety_id") != plan_row.variety_id:
                raise Task9Task8AuthorityMismatchError(
                    "Task 9 verification snapshot variety id does not match pinned Task 8 plan"
                )

    pinned_daily_inputs = tuple(
        outcome
        for outcome in resolved_inputs.values()
        if outcome.source_type == AvailabilitySourceType.TASK8_DAILY_PREDICTION
    )
    if forecast_run_id is not None and pinned_daily_inputs:
        exact_daily_set = await _verify_task8_daily_exact_set(
            session,
            forecast_run_id=forecast_run_id,
            pinned_daily_inputs=pinned_daily_inputs,
            task9_snapshot_rows=task8_snapshot_rows,
            source_ref_payload_by_hash=source_ref_payload_by_hash,
        )
        if not (
            exact_daily_set.db_daily_ids
            == exact_daily_set.pinned_daily_ids
            == exact_daily_set.task9_daily_ids
        ):
            raise Task9Task8AuthorityMismatchError(
                "Task 9 verification snapshot daily prediction set "
                "does not match pinned Task 8 rows"
            )
        for item in task8_snapshot_rows:
            if not isinstance(item, dict):
                continue
            verification = item.get("verification_snapshot")
            if not isinstance(verification, dict):
                continue
            source_ref_hash = item.get("source_ref_hash")
            if not isinstance(source_ref_hash, str) or not source_ref_hash:
                raise Task9Task8AuthorityMismatchError(
                    "Task 9 verification snapshot source_ref_hash is missing"
                )
            source_ref_payload = source_ref_payload_by_hash.get(source_ref_hash)
            if not isinstance(source_ref_payload, dict):
                raise Task9Task8AuthorityMismatchError(
                    "Task 9 source_ref_hash is missing from source_ref_catalog"
                )
            prediction_date = _coerce_persisted_date(
                verification.get("prediction_date"),
                field_name="prediction_date",
            )
            db_row = exact_daily_set.db_rows_by_date[prediction_date]
            forecast_quantile = source_ref_payload.get("forecast_quantile")
            if forecast_quantile not in {"P50", "P80", "P90"}:
                raise Task9Task8AuthorityMismatchError(
                    "Task 9 source_ref forecast quantile is invalid"
                )
            expected_quantity = {
                "P50": db_row.p50_kg,
                "P80": db_row.p80_kg,
                "P90": db_row.p90_kg,
            }[forecast_quantile]
            actual_source_quantity = parse_decimal(source_ref_payload.get("source_quantity_kg"))
            if actual_source_quantity != expected_quantity:
                raise Task9Task8AuthorityMismatchError(
                    "Task 9 source_ref quantity does not match pinned Task 8 daily prediction"
                )
            verification_quantile_quantity = parse_decimal(
                verification.get(f"{forecast_quantile.lower()}_kg")
            )
            if verification_quantile_quantity != expected_quantity:
                raise Task9Task8AuthorityMismatchError(
                    "Task 9 verification snapshot quantile quantity "
                    "does not match pinned Task 8 daily prediction"
                )

    ctx.task9_authority = Task9AuthorityOutcome(
        run_reference=task9_outcome.persistent_reference,
        semantic_input_signature=task9_outcome.semantic_identity.semantic.input_signature,
        result_hash=envelope.result_hash,
        canonical_payload_hash=task9_outcome.semantic_identity.semantic.canonical_payload_hash,
        source_catalog_hash=(
            getattr(envelope.output, "source_catalog_hash", None)
            or _task9_source_catalog_hash(envelope)
        ),
        verification_snapshot_hash=(
            getattr(envelope.output, "verification_snapshot_hash", None)
            or _task9_verification_snapshot_hash(envelope)
        ),
        mode="reuse",
    )


# ── Task 10 reuse (stage 6) ─────────────────────────────────────────────────


async def _resolve_task10_reuse(
    session: AsyncSession,
    ctx: _StageContext,
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
    *,
    resolved_inputs: dict[str, ResolvedInputOutcome],
) -> None:
    """Stage 6: Reuse persisted Task 10 training and prediction.

    Verify: training run completed, artifact belongs to training run,
    prediction run completed, completed_at <= forecast_cutoff_at.
    """
    task10_inputs = {
        role: outcome
        for role, outcome in resolved_inputs.items()
        if outcome.source_type.value.startswith("task10_")
    }
    if not task10_inputs:
        return

    training = next(
        (o for t, o in task10_inputs.items() if "training" in t),
        None,
    )
    prediction = next(
        (o for t, o in task10_inputs.items() if "prediction" in t),
        None,
    )
    artifact = next(
        (o for t, o in task10_inputs.items() if "artifact" in t),
        None,
    )
    analytics_build = next(
        (
            outcome
            for outcome in resolved_inputs.values()
            if outcome.source_type == AvailabilitySourceType.TASK3_ANALYTICS_BUILD
        ),
        None,
    )

    if training is not None:
        training_run_id = _require_database_ref(
            training.semantic_identity,
            allowed_types=("database_run_id",),
        )
        training_result = await load_residual_training_run_by_id(session, run_id=training_run_id)
        if training_result is None or training_result.execution_status != "completed":
            raise Task10Task9BindingMismatchError(
                f"Task 10 training run {training_run_id} must be completed"
            )

    if artifact is not None:
        artifact_id = _require_database_ref(
            artifact.semantic_identity,
            allowed_types=("database_artifact_id",),
        )
        artifact_row = await session.get(ResidualModelArtifact, artifact_id)
        if artifact_row is None:
            raise Task10Task9BindingMismatchError(f"Task 10 artifact {artifact_id} was not found")
        trusted_artifacts = await load_and_validate_trusted_residual_artifacts(
            session,
            run_id=artifact_row.training_run_id,
        )
        if not any(
            item.metadata.binary_sha256 == artifact_row.artifact_sha256
            for item in trusted_artifacts
        ):
            raise Task10Task9BindingMismatchError(
                f"Task 10 artifact {artifact_id} did not pass trusted-artifact validation"
            )
        if training is not None:
            training_run_id = _require_database_ref(
                training.semantic_identity,
                allowed_types=("database_run_id",),
            )
            if artifact_row.training_run_id != training_run_id:
                raise Task10Task9BindingMismatchError(
                    f"Task 10 artifact {artifact_id} does not belong to pinned training run"
                )

    if prediction is not None:
        prediction_run_id = _require_database_ref(
            prediction.semantic_identity,
            allowed_types=("database_run_id",),
        )
        prediction_row = await session.get(ResidualModelPredictionRun, prediction_run_id)
        prediction_result = await load_residual_prediction_run_by_id(
            session,
            run_id=prediction_run_id,
        )
        if prediction_row is None or prediction_result is None:
            raise Task10PredictionNotCompletedError(
                f"Task 10 prediction run {prediction_run_id} was not found"
            )
        if prediction_result.execution_status != "completed" or prediction_row.completed_at is None:
            raise Task10PredictionNotCompletedError(
                f"Task 10 prediction run {prediction_run_id} must be completed"
            )
        if prediction_row.completed_at > node.forecast_cutoff_at:
            raise Task10PredictionAfterCutoffError(
                f"Task 10 prediction run {prediction_run_id} completed after cutoff"
            )
        if training is not None:
            training_run_id = _require_database_ref(
                training.semantic_identity,
                allowed_types=("database_run_id",),
            )
            if prediction_row.training_run_id != training_run_id:
                raise Task10Task9BindingMismatchError(
                    f"Task 10 prediction run {prediction_run_id} "
                    "does not belong to pinned training run"
                )
        if ctx.task9_authority is None or ctx.task9_authority.run_reference is None:
            raise Task10Task9BindingMismatchError(
                "Task 10 prediction run requires pinned Task 9 authority"
            )
        if prediction_result.task9_run_id != ctx.task9_authority.run_reference.reference_value:
            raise Task10Task9BindingMismatchError(
                f"Task 10 prediction run {prediction_run_id} Task 9 run mismatch"
            )
        if prediction_result.task9_result_hash != ctx.task9_authority.result_hash:
            raise Task10Task9BindingMismatchError(
                f"Task 10 prediction run {prediction_run_id} Task 9 result hash mismatch"
            )
        if analytics_build is not None:
            build_run_id = _require_database_ref(
                analytics_build.semantic_identity,
                allowed_types=("database_run_id",),
            )
            feature_snapshot = prediction_result.input_snapshot.get("feature_actual_snapshot")
            if not isinstance(feature_snapshot, dict):
                raise Task10Task9BindingMismatchError(
                    f"Task 10 prediction run {prediction_run_id} is missing feature_actual_snapshot"
                )
            if feature_snapshot.get("build_run_id") != build_run_id:
                raise Task10Task9BindingMismatchError(
                    f"Task 10 prediction run {prediction_run_id} feature build mismatch"
                )
            if (
                analytics_build.business_version is not None
                and feature_snapshot.get("aggregation_version") != analytics_build.business_version
            ):
                raise Task10Task9BindingMismatchError(
                    f"Task 10 prediction run {prediction_run_id} feature version mismatch"
                )
            expected_config_hash = analytics_build.semantic_identity.semantic.config_hash
            if (
                expected_config_hash is not None
                and feature_snapshot.get("config_hash") != expected_config_hash
            ):
                raise Task10Task9BindingMismatchError(
                    f"Task 10 prediction run {prediction_run_id} feature config mismatch"
                )

    ctx.task10_authority = Task10AuthorityOutcome(
        training_reference=training.persistent_reference if training else None,
        artifact_reference=artifact.persistent_reference if artifact else None,
        prediction_reference=prediction.persistent_reference if prediction else None,
        feature_reference=analytics_build.persistent_reference if analytics_build else None,
        task9_run_reference=ctx.task9_authority.run_reference if ctx.task9_authority else None,
        task9_result_hash=ctx.task9_authority.result_hash if ctx.task9_authority else None,
        input_signature=(
            prediction.semantic_identity.semantic.input_signature if prediction else None
        ),
        prediction_hash=prediction.semantic_identity.semantic.result_hash if prediction else None,
        mode="reuse",
    )


# ── Stage 7: Task 10 prediction (reuse only) ────────────────────────────────


async def _execute_task10_prediction_reuse(
    session: AsyncSession,
    ctx: _StageContext,
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
) -> None:
    """Stage 7: Verify persisted Task 10 prediction integrity.

    For historical_observed: no new prediction execution.
    Verify existing prediction hash matches.
    """
    if ctx.task10_authority is None:
        return
    if ctx.task10_authority.prediction_hash is None:
        return
    if ctx.task10_authority.prediction_reference is None:
        raise Task10PredictionNotCompletedError(
            "Task 10 reuse is missing pinned prediction reference"
        )
    prediction_run_id = ctx.task10_authority.prediction_reference.reference_value
    if not isinstance(prediction_run_id, int):
        raise Task10PredictionNotCompletedError(
            "Task 10 prediction reference must be a database_run_id"
        )
    prediction_result = await load_residual_prediction_run_by_id(session, run_id=prediction_run_id)
    prediction_row = await session.get(ResidualModelPredictionRun, prediction_run_id)
    if prediction_result is None or prediction_row is None or prediction_row.completed_at is None:
        raise Task10PredictionNotCompletedError(
            f"Task 10 prediction run {prediction_run_id} was not found"
        )
    if prediction_result.execution_status != "completed":
        raise Task10PredictionNotCompletedError(
            f"Task 10 prediction run {prediction_run_id} must be completed"
        )
    if prediction_row.completed_at > node.forecast_cutoff_at:
        raise Task10PredictionAfterCutoffError(
            f"Task 10 prediction run {prediction_run_id} completed after cutoff"
        )
    if prediction_result.prediction_hash != ctx.task10_authority.prediction_hash:
        raise Task10Task9BindingMismatchError(
            f"Task 10 prediction run {prediction_run_id} prediction hash mismatch"
        )
    if prediction_result.prediction_input_signature != ctx.task10_authority.input_signature:
        raise Task10Task9BindingMismatchError(
            f"Task 10 prediction run {prediction_run_id} input signature mismatch"
        )
    if ctx.task9_authority is None or ctx.task9_authority.run_reference is None:
        raise Task10Task9BindingMismatchError(
            "Task 10 prediction run requires resolved Task 9 authority"
        )
    if prediction_result.task9_run_id != ctx.task9_authority.run_reference.reference_value:
        raise Task10Task9BindingMismatchError(
            f"Task 10 prediction run {prediction_run_id} Task 9 run mismatch"
        )
    if prediction_result.task9_result_hash != ctx.task9_authority.result_hash:
        raise Task10Task9BindingMismatchError(
            f"Task 10 prediction run {prediction_run_id} Task 9 result hash mismatch"
        )
    if ctx.task10_authority.feature_reference is not None:
        feature_snapshot = prediction_result.input_snapshot.get("feature_actual_snapshot")
        expected_build_run_id = ctx.task10_authority.feature_reference.reference_value
        if (
            not isinstance(feature_snapshot, dict)
            or feature_snapshot.get("build_run_id") != expected_build_run_id
        ):
            raise Task10Task9BindingMismatchError(
                f"Task 10 prediction run {prediction_run_id} feature build mismatch"
            )


# ── Snapshot builder ────────────────────────────────────────────────────────


def _build_orchestration_snapshot_payload(
    ctx: _StageContext,
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
    *,
    run_signature: str,
    node_signature: str,
) -> dict[str, Any]:
    """Build the canonical orchestration snapshot payload."""
    task8_authorities = {
        role: {
            "source_role": outcome.source_role,
            "source_type": outcome.source_type.value,
            "persistent_reference": outcome.persistent_reference.model_dump(mode="python"),
            "business_version": outcome.business_version,
            "canonical_identity_hash": outcome.canonical_identity_hash,
            "canonical_payload_hash": outcome.canonical_payload_hash,
        }
        for role, outcome in ctx.resolved_inputs.items()
        if outcome.source_type.value.startswith("task8_")
    }
    resolved_inputs_dict = {
        role: {
            "source_role": outcome.source_role,
            "source_type": outcome.source_type.value,
            "persistent_reference": outcome.persistent_reference.model_dump(mode="python"),
            "authoritative_available_at": outcome.authoritative_available_at.isoformat(),
            "business_version": outcome.business_version,
            "canonical_identity_hash": outcome.canonical_identity_hash,
            "canonical_payload_hash": outcome.canonical_payload_hash,
        }
        for role, outcome in ctx.resolved_inputs.items()
    }
    audits_dict = {
        role: {
            "source_role": audit.source_role,
            "source_type": audit.source_type,
            "allowed": audit.allowed,
            "blocker_code": audit.blocker_code,
            "authoritative_available_at": audit.authoritative_available_at,
            "forecast_cutoff_at": audit.forecast_cutoff_at,
            "audit_hash": audit.audit_hash,
            "parent_authority": audit.parent_authority,
        }
        for role, audit in ctx.availability_audits.items()
    }
    dag = _build_frozen_dag(owner_node_signature=node_signature)
    dag_payload = {
        "dag_schema_version": dag.dag_schema_version,
        "dag_policy_version": dag.dag_policy_version,
        "nodes": dag.dag_dict["nodes"],
        "edges": dag.dag_dict["edges"],
    }
    snapshot: dict[str, Any] = {
        "run_signature": run_signature,
        "node_signature": node_signature,
        "attempt": {
            "attempt_id": ctx.attempt_id,
            "attempt_number": ctx.attempt_number,
            "prior_attempt_id": ctx.prior_attempt_id,
        },
        "execution_mode": config.execution_mode.value,
        "upstream_selection_mode": node.upstream_selection_mode.value,
        "forecast_cutoff_at": node.forecast_cutoff_at.isoformat(),
        "dag": dag_payload,
        "dag_hash": sha256_payload(dag_payload),
        "resolved_inputs": resolved_inputs_dict,
        "availability_audits": audits_dict,
    }
    if task8_authorities:
        snapshot["task8_authorities"] = task8_authorities
    if ctx.task9_authority:
        snapshot["task9_authority"] = {
            "run_reference": (
                ctx.task9_authority.run_reference.model_dump(mode="python")
                if ctx.task9_authority.run_reference
                else None
            ),
            "semantic_input_signature": ctx.task9_authority.semantic_input_signature,
            "result_hash": ctx.task9_authority.result_hash,
            "canonical_payload_hash": ctx.task9_authority.canonical_payload_hash,
            "source_catalog_hash": ctx.task9_authority.source_catalog_hash,
            "verification_snapshot_hash": ctx.task9_authority.verification_snapshot_hash,
            "mode": ctx.task9_authority.mode,
        }
    if ctx.task10_authority:
        snapshot["task10_authority"] = {
            "training_reference": (
                ctx.task10_authority.training_reference.model_dump(mode="python")
                if ctx.task10_authority.training_reference
                else None
            ),
            "prediction_reference": (
                ctx.task10_authority.prediction_reference.model_dump(mode="python")
                if ctx.task10_authority.prediction_reference
                else None
            ),
            "artifact_reference": (
                ctx.task10_authority.artifact_reference.model_dump(mode="python")
                if ctx.task10_authority.artifact_reference
                else None
            ),
            "feature_reference": (
                ctx.task10_authority.feature_reference.model_dump(mode="python")
                if ctx.task10_authority.feature_reference
                else None
            ),
            "task9_run_reference": (
                ctx.task10_authority.task9_run_reference.model_dump(mode="python")
                if ctx.task10_authority.task9_run_reference
                else None
            ),
            "task9_result_hash": ctx.task10_authority.task9_result_hash,
            "input_signature": ctx.task10_authority.input_signature,
            "prediction_hash": ctx.task10_authority.prediction_hash,
            "mode": ctx.task10_authority.mode,
        }
    if ctx.fallback_mode:
        snapshot["fallback_mode"] = ctx.fallback_mode
    return snapshot


# ── Main orchestration entry point ───────────────────────────────────────────


async def orchestrate_node(
    session: AsyncSession,
    *,
    rolling_run_id: int,
    rolling_node_id: int,
    _before_stage_hook: Any = None,
    _replay_runtime_identity: ReplayRunIdentity | None = None,
    replay_dispatch_task9a_request: Mapping[str, object] | Task9ARequest | None = None,
) -> NodeOrchestrationOutcome:
    """Execute a single rolling node through the eight-stage DAG.

    This is the formal typed service for node orchestration.
    All state changes go through the persistence layer.

    §5 dispatch lift (bucket #5):
        * ``_replay_runtime_identity`` (a ``ReplayRunIdentity``
          populated by the dispatch caller) is required when
          ``config.execution_mode == RETROSPECTIVE_REPLAY``. The
          orchestrator routes replay-mode dispatch into
          :func:`replay_pipeline.orchestrate_replay_node` instead of
          running the historical 8-stage DAG.
        * ``replay_dispatch_task9a_request`` is the §3 canonical
          ``Task9ARequest`` (or a mapping accepted by
          :func:`execute_harvest_state_run`) the replay pipeline
          must pass through. It is required when replay-mode is
          dispatched and is forwarded unchanged to the bucket-#5
          pipeline entry point.
        * Historical-mode callers who do NOT supply these kwargs get
          the unchanged historical 8-stage DAG.
    """
    # ── Load and validate ─────────────────────────────────────────────────
    run_result = await session.execute(
        select(RollingBacktestRun).where(RollingBacktestRun.id == rolling_run_id)
    )
    run = run_result.scalar_one_or_none()
    if run is None:
        raise RollingBacktestIntegrityError(f"rolling run {rolling_run_id} not found")

    node_result = await session.execute(
        select(RollingBacktestNode).where(RollingBacktestNode.id == rolling_node_id)
    )
    node = node_result.scalar_one_or_none()
    if node is None:
        raise RollingBacktestIntegrityError(f"rolling node {rolling_node_id} not found")
    if node.rolling_run_id != rolling_run_id:
        raise RollingBacktestAuthorityBindingError(
            f"node {rolling_node_id} does not belong to run {rolling_run_id}"
        )

    config = _config_from_payload(run.canonical_payload)
    node_def = _node_def_from_payload(node.canonical_payload, config)

    ctx = _StageContext(
        attempt_id=0,
        node_id=rolling_node_id,
        run_id=rolling_run_id,
        resolved_inputs={},
        availability_audits={},
    )
    attempt = None

    # ── Check for existing finalized result (P0-1: idempotent reload) ──────
    latest_attempt_result = await session.execute(
        select(RollingBacktestAttempt)
        .where(
            RollingBacktestAttempt.rolling_node_id == rolling_node_id,
            RollingBacktestAttempt.rolling_run_id == rolling_run_id,
        )
        .order_by(RollingBacktestAttempt.attempt_number.desc())
        .limit(1)
    )
    latest_attempt = latest_attempt_result.scalar_one_or_none()
    if latest_attempt is not None and latest_attempt.status == "completed":
        # Load persisted orchestration snapshot
        snap_result = await session.execute(
            select(RollingBacktestOrchestrationSnapshot).where(
                RollingBacktestOrchestrationSnapshot.attempt_id == latest_attempt.id
            )
        )
        snapshot = snap_result.scalar_one_or_none()

        # Hard integrity reload — fail closed
        await load_logical_run_with_integrity(session, run)

        # Build completed outcome from persisted data (no new attempt, no mutation)
        terminal_stage = (
            snapshot.terminal_stage
            if snapshot
            else OrchestrationStage.FINALIZE_ORCHESTRATION_SNAPSHOT.value
        )
        return NodeOrchestrationOutcome(
            rolling_run_signature=run.run_signature,
            node_signature=(node_def.node_signature if hasattr(node_def, "node_signature") else ""),
            attempt_number=latest_attempt.attempt_number,
            status="completed",
            stage=terminal_stage,
            started_at=latest_attempt.started_at,
            finished_at=latest_attempt.finished_at,
            diagnostics={"idempotent_reload": True},
        )

    persisted_identities = await load_node_resolved_identities_with_references(
        session,
        rolling_node_id=node.id,
    )
    expected_resolved_input_count = getattr(
        node,
        "expected_resolved_input_count",
        len(node_def.resolved_upstream_semantic_identities),
    )
    if not isinstance(expected_resolved_input_count, int):
        expected_resolved_input_count = len(node_def.resolved_upstream_semantic_identities)
    if len(persisted_identities) != expected_resolved_input_count:
        raise RollingBacktestIntegrityError(
            "persisted resolved input count does not match node expected_resolved_input_count"
        )

    if node_def.upstream_selection_mode == UpstreamSelectionMode.PINNED:
        for identity in persisted_identities:
            if identity.persistent_reference is None:
                raise PinnedSourceNotFoundError(
                    f"pinned source role={identity.source_role} is missing persistent reference"
                )

    node_def = node_def.model_copy(
        update={"resolved_upstream_semantic_identities": persisted_identities}
    )

    try:
        # P0-2: Mode validation moved into Stage 1 (after attempt creation)
        # ── Create execution attempt ────────────────────────────────────────
        attempt = await create_execution_attempt(
            rolling_run_id,
            rolling_node_id,
            status="running",
            current_stage=OrchestrationStage.RESOLVE_HISTORICAL_INPUTS.value,
            session=session,
        )
        ctx.attempt_id = attempt.id
        ctx.attempt_number = attempt.attempt_number
        ctx.prior_attempt_id = getattr(attempt, "prior_attempt_id", None)

        # ── §5 dispatch lift (bucket #5): RETROSPECTIVE_REPLAY mode routes
        # through ``replay_pipeline.orchestrate_replay_node`` instead of the
        # historical 8-stage DAG. The replay pipeline "composes around
        # (does not replace)" the existing Task 8 / Task 9 / Task 10 paths
        # (§5.5 / §3); it calls bucket #3 audit writer, the §3 canonical
        # Task 9 entry point ``execute_harvest_state_run``, and bucket #4
        # metadata writer. The historical 8-stage DAG does NOT run for
        # replay mode here; replay has its own closed pipeline.
        #
        # The dispatch branch lives INSIDE the existing ``try`` block,
        # AFTER ``create_execution_attempt`` so the Phase 2 contract
        # ``attempt_count == 1`` for unsupported-mode blocked outcomes
        # is preserved (Phase 2 integration tests pin this).
        if config.execution_mode == ExecutionMode.RETROSPECTIVE_REPLAY:
            if _replay_runtime_identity is None:
                # §4.3 / §4.4 hard rule: replay dispatch must be supplied
                # with explicit runtime identity (code_version +
                # replay_correlation_id). Without it the pipeline cannot
                # proceed; raise the typed error so the except-block
                # below builds a blocked outcome carrying
                # ``UNSUPPORTED_EXECUTION_MODE``.
                raise UnsupportedExecutionModeError(
                    "RETROSPECTIVE_REPLAY dispatch requires explicit "
                    "_replay_runtime_identity (ReplayRunIdentity); "
                    "see §4.3 + §4.4."
                )
            return await _run_replay_pipeline_via_dispatch(
                session=session,
                config=config,
                node_def=node_def,
                replay_runtime_identity=_replay_runtime_identity,
                replay_dispatch_task9a_request=replay_dispatch_task9a_request,
            )

        # ── Stage 1: resolve_historical_inputs ───────────────────────────
        ctx = await _run_stage(
            session,
            ctx,
            OrchestrationStage.RESOLVE_HISTORICAL_INPUTS,
            config,
            node_def,
            _stage_resolve_historical_inputs,
            _before_stage_hook,
        )

        # ── Stage 2: validate_visibility ─────────────────────────────────
        ctx = await _run_stage(
            session,
            ctx,
            OrchestrationStage.VALIDATE_VISIBILITY,
            config,
            node_def,
            _stage_validate_visibility,
            _before_stage_hook,
        )

        # ── Stage 3: validate_authority_chain ────────────────────────────
        ctx = await _run_stage(
            session,
            ctx,
            OrchestrationStage.VALIDATE_AUTHORITY_CHAIN,
            config,
            node_def,
            _stage_validate_authority_chain,
            _before_stage_hook,
        )

        # ── Stage 4: resolve_or_replay_task8 ────────────────────────────
        ctx = await _run_stage(
            session,
            ctx,
            OrchestrationStage.RESOLVE_OR_REPLAY_TASK8,
            config,
            node_def,
            _stage_resolve_task8,
            _before_stage_hook,
        )

        # ── Stage 5: resolve_or_replay_task9 ────────────────────────────
        ctx = await _run_stage(
            session,
            ctx,
            OrchestrationStage.RESOLVE_OR_REPLAY_TASK9,
            config,
            node_def,
            _stage_resolve_task9,
            _before_stage_hook,
        )

        # ── Stage 6: resolve_or_train_task10 ────────────────────────────
        ctx = await _run_stage(
            session,
            ctx,
            OrchestrationStage.RESOLVE_OR_TRAIN_TASK10,
            config,
            node_def,
            _stage_resolve_task10,
            _before_stage_hook,
        )

        # ── Stage 7: execute_task10_prediction ───────────────────────────
        ctx = await _run_stage(
            session,
            ctx,
            OrchestrationStage.EXECUTE_TASK10_PREDICTION,
            config,
            node_def,
            _stage_execute_task10_prediction,
            _before_stage_hook,
        )

        # ── Stage 8: finalize_orchestration_snapshot ─────────────────────
        ctx = await _run_stage(
            session,
            ctx,
            OrchestrationStage.FINALIZE_ORCHESTRATION_SNAPSHOT,
            config,
            node_def,
            _stage_finalize_snapshot,
            _before_stage_hook,
        )

        # ── P0-3: Finalize attempt THEN integrity reload (fail closed) ───
        # Finalize in caller's session so rollback can undo everything
        # if integrity check fails.
        await _finalize_attempt_status_in_session(
            session,
            attempt.id,
            status="completed",
            current_stage=OrchestrationStage.FINALIZE_ORCHESTRATION_SNAPSHOT.value,
        )

        await update_run_status_from_attempts(session, rolling_run_id)
        await session.flush()

        # Hard integrity reload — fail closed, no swallowing.
        # Verifies: run canonical parity, node canonical parity,
        # attempt chain, stage continuity, snapshot consistency.
        #
        # P0-4: Freeze primitive values BEFORE the reload so that after
        # rollback (which expires ORM objects) we can construct the outcome
        # without touching expired ORM attributes or triggering MissingGreenlet.
        frozen_run_signature = run.run_signature
        frozen_node_signature = (
            node_def.node_signature if hasattr(node_def, "node_signature") else ""
        )
        frozen_attempt_number = attempt.attempt_number
        frozen_started_at = attempt.started_at
        frozen_resolved_inputs = tuple(ctx.resolved_inputs.values())
        frozen_availability_audits = tuple(ctx.availability_audits.values())
        frozen_task9_authority = ctx.task9_authority
        frozen_task10_authority = ctx.task10_authority
        frozen_fallback_mode = ctx.fallback_mode

        try:
            await load_logical_run_with_integrity(session, run)
        except Exception as reload_exc:
            # Integrity reload failed — rollback the entire execution so
            # no completed attempt, snapshot, or run-status mutation survives.
            await session.rollback()
            return NodeOrchestrationOutcome(
                rolling_run_signature=frozen_run_signature,
                node_signature=frozen_node_signature,
                attempt_number=frozen_attempt_number,
                status="blocked",
                stage=OrchestrationStage.FINALIZE_ORCHESTRATION_SNAPSHOT.value,
                resolved_inputs=frozen_resolved_inputs,
                availability_audits=frozen_availability_audits,
                task9_authority=frozen_task9_authority,
                task10_authority=frozen_task10_authority,
                fallback_mode=frozen_fallback_mode,
                blocker_code="ROLLING_ORCHESTRATION_INTEGRITY_RELOAD_FAILED",
                diagnostics={"error": str(reload_exc)},
                started_at=frozen_started_at,
            )

        return _build_outcome(
            ctx=ctx,
            config=config,
            node=node_def,
            run=run,
            attempt=attempt,
            status="completed",
            stage=OrchestrationStage.FINALIZE_ORCHESTRATION_SNAPSHOT.value,
        )

    except (
        UnsupportedExecutionModeError,
        UnsupportedSelectionModeError,
        NodeAlreadyFinalizedError,
        RollingBacktestAttemptConflictError,
        HistoricalSourceNotFoundError,
        HistoricalSourceNotVisibleError,
        AmbiguousHistoricalCandidateError,
        PinnedSourceNotFoundError,
        PinnedSourceIdentityMismatchError,
        PinnedSourceScopeMismatchError,
        PinnedSourceNotVisibleError,
        Task8ParentAuthorityMismatchError,
        Task9Task8AuthorityMismatchError,
        Task10Task9BindingMismatchError,
        Task10PredictionNotCompletedError,
        Task10PredictionAfterCutoffError,
    ) as exc:
        # Known typed errors → blocked
        blocker_code = getattr(exc, "code", "PERSISTENCE_FAILURE")
        if attempt is not None:
            await _finalize_blocked(
                session,
                ctx,
                config,
                node_def,
                run,
                attempt,
                blocker_code=blocker_code,
                error=exc,
            )
        return _build_outcome(
            ctx=ctx,
            config=config,
            node=node_def,
            run=run,
            attempt=attempt,
            status="blocked",
            stage=_blocked_terminal_stage(ctx),
            blocker_code=blocker_code,
            diagnostics={
                "error": str(exc),
                "last_completed_stage": ctx.last_completed_stage,
                "terminal_stage": _blocked_terminal_stage(ctx),
            },
        )

    except Exception as exc:
        # Unexpected errors → failed
        if attempt is not None:
            await _finalize_blocked(
                session,
                ctx,
                config,
                node_def,
                run,
                attempt,
                blocker_code="PERSISTENCE_FAILURE",
                error=exc,
            )
        return _build_outcome(
            ctx=ctx,
            config=config,
            node=node_def,
            run=run,
            attempt=attempt,
            status="failed",
            stage=_blocked_terminal_stage(ctx),
            blocker_code="PERSISTENCE_FAILURE",
            diagnostics={
                "error": str(exc),
                "last_completed_stage": ctx.last_completed_stage,
                "terminal_stage": _blocked_terminal_stage(ctx),
            },
        )


# ── Stage runner ─────────────────────────────────────────────────────────────


async def _run_stage(
    session: AsyncSession,
    ctx: _StageContext,
    stage: OrchestrationStage,
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
    stage_fn: Any,
    before_hook: Any = None,
) -> _StageContext:
    """Run a single stage: enter → execute → exit."""
    if before_hook is not None:
        hook_result = before_hook(stage.value)
        if hasattr(hook_result, "__await__"):
            await hook_result

    # Enter stage (running)
    ctx.active_stage = stage.value
    await persist_stage_event(
        ctx.attempt_id,
        ctx.node_id,
        stage=stage.value,
        status="running",
        session=session,
    )

    try:
        ctx = await stage_fn(session, ctx, config, node)
        # Complete stage
        await persist_stage_event(
            ctx.attempt_id,
            ctx.node_id,
            stage=stage.value,
            status="completed",
            session=session,
        )
        ctx.last_completed_stage = stage.value
        ctx.active_stage = None
        ctx.diagnostics["last_completed_stage"] = stage.value
        return ctx

    except Exception as exc:
        # P0-4: Preserve typed error code instead of degrading to STAGE_FAILED
        ctx.terminal_stage = stage.value
        code = getattr(exc, "code", "STAGE_FAILED")
        await persist_stage_event(
            ctx.attempt_id,
            ctx.node_id,
            stage=stage.value,
            status="blocked",
            structured_error_code=code,
            session=session,
        )
        raise


def _blocked_terminal_stage(ctx: _StageContext) -> str:
    return (
        ctx.terminal_stage
        or ctx.active_stage
        or ctx.last_completed_stage
        or OrchestrationStage.RESOLVE_HISTORICAL_INPUTS.value
    )


# ── Individual stage implementations ─────────────────────────────────────────


async def _stage_resolve_historical_inputs(
    session: AsyncSession,
    ctx: _StageContext,
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
) -> _StageContext:
    """Stage 1: Resolve historical inputs from persisted source requests."""
    # Preserve the stage-1 blocker contract: unsupported mode/selection must
    # fail closed before any availability lookup or exact-load attempt.
    #
    # §5.1 dispatch lift: the gate accepts BOTH ExecutionMode.HISTORICAL_OBSERVED
    # AND ExecutionMode.RETROSPECTIVE_REPLAY. Replay-mode dispatch reaches the
    # bucket-#5 ``replay_pipeline.orchestrate_replay_node`` entry point before
    # this stage runs (see ``orchestrate_node`` above); this gate accepts replay
    # mode defensively so the historical 8-stage DAG can be exercised by future
    # bucket-6+ code that wires replay into stage 1 directly without the
    # pipeline wrapper.
    if config.execution_mode not in (
        ExecutionMode.HISTORICAL_OBSERVED,
        ExecutionMode.RETROSPECTIVE_REPLAY,
    ):
        raise UnsupportedExecutionModeError(
            f"execution_mode={config.execution_mode.value} is not supported"
        )
    if node.upstream_selection_mode == UpstreamSelectionMode.PINNED:
        for identity in node.resolved_upstream_semantic_identities:
            if identity.persistent_reference is None:
                raise PinnedSourceNotFoundError(
                    f"pinned source role={identity.source_role} is missing persistent reference"
                )
            exact = await _load_exact_pinned_candidate(session, node, identity)
            if exact.semantic_identity.source_role != identity.source_role:
                raise PinnedSourceIdentityMismatchError(
                    f"pinned source role mismatch: expected {identity.source_role} "
                    f"got {exact.semantic_identity.source_role}"
                )
            if _build_identity_payload(exact.semantic_identity) != _build_identity_payload(
                identity
            ):
                raise PinnedSourceIdentityMismatchError(
                    f"pinned source semantic mismatch for role={identity.source_role}"
                )
            outcome = ResolvedInputOutcome(
                source_role=identity.source_role,
                source_type=identity.source_type,
                semantic_identity=identity,
                persistent_reference=exact.persistent_reference,
                authoritative_available_at=exact.authoritative_available_at,
                canonical_identity_hash=exact.canonical_identity_hash,
                canonical_payload_hash=exact.canonical_payload_hash,
                business_version=exact.business_version,
            )
            ctx.resolved_inputs[identity.source_role] = outcome
        return ctx

    if node.upstream_selection_mode == UpstreamSelectionMode.HISTORICAL_RESOLUTION:
        for request_identity in node.resolved_upstream_semantic_identities:
            resolution = await resolve_historical(
                session,
                source_role=request_identity.source_role,
                source_type=request_identity.source_type,
                node=node,
                execution_mode=config.execution_mode,
            )
            if resolution.blocked or resolution.resolved is None:
                blocker_code = resolution.blocker_code or HistoricalSourceNotFoundError.code
                if blocker_code == HistoricalSourceNotFoundError.code:
                    if await _has_historical_candidates_outside_cutoff(
                        session,
                        source_type=request_identity.source_type,
                        node=node,
                    ):
                        role = request_identity.source_role
                        raise HistoricalSourceNotVisibleError(
                            f"no cutoff-visible historical candidate for role={role}"
                        )
                    raise HistoricalSourceNotFoundError(
                        f"no valid historical candidate for role={request_identity.source_role}"
                    )
                if blocker_code == HistoricalSourceNotVisibleError.code:
                    role = request_identity.source_role
                    raise HistoricalSourceNotVisibleError(
                        f"no cutoff-visible historical candidate for role={role}"
                    )
                if blocker_code == AmbiguousHistoricalCandidateError.code:
                    raise AmbiguousHistoricalCandidateError(
                        f"ambiguous historical candidates for role={request_identity.source_role}"
                    )
                raise NodeOrchestrationError(
                    f"historical resolution blocked for role={request_identity.source_role}",
                    code=blocker_code,
                )

            resolved = resolution.resolved
            ctx.resolved_inputs[request_identity.source_role] = ResolvedInputOutcome(
                source_role=request_identity.source_role,
                source_type=resolved.source_type,
                semantic_identity=resolved.semantic_identity,
                persistent_reference=resolved.persistent_reference,
                authoritative_available_at=resolved.authoritative_available_at,
                canonical_identity_hash=resolved.canonical_identity_hash,
                canonical_payload_hash=resolved.canonical_payload_hash,
                business_version=resolved.business_version,
            )
        return ctx

    raise UnsupportedSelectionModeError(
        f"upstream_selection_mode={node.upstream_selection_mode} not supported"
    )
def _parent_authority_identity(
    *,
    source_type: AvailabilitySourceType,
    authority_status: str,
    authority_timestamp: datetime,
    persistent_reference: PersistentUpstreamReference,
    semantic_input_signature: str | None = None,
    result_hash: str | None = None,
    canonical_payload_hash: str | None = None,
) -> ParentAuthorityIdentity:
    return ParentAuthorityIdentity(
        source_type=source_type,
        authority_schema_version="task11-upstream-v1",
        authority_policy_version="task11-upstream-v1",
        authority_timestamp=authority_timestamp,
        authority_status=authority_status,
        semantic_input_signature=semantic_input_signature,
        result_hash=result_hash,
        canonical_payload_hash=canonical_payload_hash,
        persistent_reference=persistent_reference,
    )


async def _has_historical_candidates_outside_cutoff(
    session: AsyncSession,
    *,
    source_type: AvailabilitySourceType,
    node: RollingNodeDefinition,
) -> bool:
    if source_type == AvailabilitySourceType.TASK3_ANALYTICS_BUILD:
        row = (
            await session.execute(
                select(AnalyticsBuildRun.id)
                .where(AnalyticsBuildRun.season_id == node.season_id)
                .where(AnalyticsBuildRun.status == "completed")
                .limit(1)
            )
        ).first()
        return row is not None
    if source_type == AvailabilitySourceType.TASK8_MODEL_RUN:
        row = (
            await session.execute(
                select(MaturityModelRun.id)
                .where(MaturityModelRun.status.in_(["completed", "unavailable"]))
                .where(MaturityModelRun.training_cutoff <= node.as_of_local_date)
                .limit(1)
            )
        ).first()
        return row is not None
    if source_type == AvailabilitySourceType.TASK8_MODEL_ARTIFACT:
        row = (
            await session.execute(
                select(MaturityModelArtifact.id)
                .join(MaturityModelRun, MaturityModelArtifact.run_id == MaturityModelRun.id)
                .where(MaturityModelRun.status.in_(["completed", "unavailable"]))
                .where(MaturityModelRun.training_cutoff <= node.as_of_local_date)
                .limit(1)
            )
        ).first()
        return row is not None
    if source_type == AvailabilitySourceType.TASK8_FORECAST_RUN:
        row = (
            await session.execute(
                select(MaturityForecastRun.id)
                .where(MaturityForecastRun.status.in_(["completed", "unavailable"]))
                .limit(1)
            )
        ).first()
        return row is not None
    if source_type == AvailabilitySourceType.TASK8_DAILY_PREDICTION:
        row = (
            await session.execute(
                select(MaturityDailyPredictionModel.id)
                .join(
                    MaturityForecastRun,
                    MaturityDailyPredictionModel.forecast_run_id == MaturityForecastRun.id,
                )
                .where(MaturityForecastRun.status.in_(["completed", "unavailable"]))
                .where(
                    MaturityDailyPredictionModel.prediction_date >= node.forecast_start_local_date
                )
                .where(MaturityDailyPredictionModel.prediction_date <= node.forecast_end_local_date)
                .limit(1)
            )
        ).first()
        return row is not None
    if source_type == AvailabilitySourceType.TASK9_HARVEST_STATE_RUN:
        row = (
            await session.execute(
                select(HarvestStateRun.id)
                .where(HarvestStateRun.as_of_date <= node.as_of_local_date)
                .where(HarvestStateRun.status.in_(["completed", "blocked"]))
                .limit(1)
            )
        ).first()
        return row is not None
    if source_type == AvailabilitySourceType.TASK10_TRAINING_RUN:
        row = (
            await session.execute(
                select(ResidualModelTrainingRun.id)
                .where(
                    ResidualModelTrainingRun.execution_status.in_(
                        ["completed", "blocked", "failed"]
                    )
                )
                .limit(1)
            )
        ).first()
        return row is not None
    if source_type == AvailabilitySourceType.TASK10_MODEL_ARTIFACT:
        row = (
            await session.execute(
                select(ResidualModelArtifact.id)
                .join(
                    ResidualModelTrainingRun,
                    ResidualModelArtifact.training_run_id == ResidualModelTrainingRun.id,
                )
                .where(ResidualModelTrainingRun.execution_status == "completed")
                .limit(1)
            )
        ).first()
        return row is not None
    if source_type == AvailabilitySourceType.TASK10_PREDICTION_RUN:
        row = (
            await session.execute(
                select(ResidualModelPredictionRun.id)
                .where(ResidualModelPredictionRun.execution_status == "completed")
                .limit(1)
            )
        ).first()
        return row is not None
    return False


async def _build_availability_snapshot_for_resolved_input(
    session: AsyncSession,
    *,
    outcome: ResolvedInputOutcome,
) -> AvailabilitySnapshot:
    source_type = outcome.source_type

    if source_type == AvailabilitySourceType.TASK3_ANALYTICS_BUILD:
        build_run_id = _require_database_ref(
            outcome.semantic_identity,
            allowed_types=("database_run_id",),
        )
        build_run = cast(
            AnalyticsBuildRun | None, await session.get(AnalyticsBuildRun, build_run_id)
        )
        if build_run is None or build_run.finished_at is None:
            raise HistoricalSourceNotFoundError(
                f"Task 3 analytics build {build_run_id} was not found"
            )
        return Task3AnalyticsBuildAvailabilitySnapshot(
            source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
            status=build_run.status,
            authoritative_timestamp=build_run.finished_at,
            task3_source_visibility=_task3_source_visibility_snapshot(build_run),
        )

    if source_type == AvailabilitySourceType.TASK8_MODEL_RUN:
        run_id = _require_database_ref(
            outcome.semantic_identity, allowed_types=("database_run_id",)
        )
        model_run = cast(MaturityModelRun | None, await session.get(MaturityModelRun, run_id))
        if model_run is None or model_run.finished_at is None:
            raise HistoricalSourceNotFoundError(f"Task 8 model run {run_id} was not found")
        return Task8ModelRunAvailabilitySnapshot(
            source_type=AvailabilitySourceType.TASK8_MODEL_RUN,
            status=model_run.status,
            authoritative_timestamp=model_run.finished_at,
        )

    if source_type == AvailabilitySourceType.TASK8_MODEL_ARTIFACT:
        artifact_id = _require_database_ref(
            outcome.semantic_identity,
            allowed_types=("database_artifact_id",),
        )
        artifact_row = cast(
            MaturityModelArtifact | None, await session.get(MaturityModelArtifact, artifact_id)
        )
        parent_run = (
            None
            if artifact_row is None
            else cast(
                MaturityModelRun | None, await session.get(MaturityModelRun, artifact_row.run_id)
            )
        )
        if artifact_row is None or parent_run is None or parent_run.finished_at is None:
            raise HistoricalSourceNotFoundError(
                f"Task 8 model artifact {artifact_id} was not found"
            )
        return Task8ModelArtifactAvailabilitySnapshot(
            source_type=AvailabilitySourceType.TASK8_MODEL_ARTIFACT,
            created_at=artifact_row.created_at,
            parent_authority=_parent_authority_identity(
                source_type=AvailabilitySourceType.TASK8_MODEL_RUN,
                authority_status=parent_run.status,
                authority_timestamp=parent_run.finished_at,
                persistent_reference=PersistentUpstreamReference(
                    reference_type="database_run_id",
                    reference_value=parent_run.id,
                ),
                canonical_payload_hash=parent_run.config_hash,
            ),
        )

    if source_type == AvailabilitySourceType.TASK8_FORECAST_RUN:
        run_id = _require_database_ref(
            outcome.semantic_identity, allowed_types=("database_run_id",)
        )
        forecast_run = cast(
            MaturityForecastRun | None, await session.get(MaturityForecastRun, run_id)
        )
        if forecast_run is None or forecast_run.finished_at is None:
            raise HistoricalSourceNotFoundError(f"Task 8 forecast run {run_id} was not found")
        return Task8ForecastRunAvailabilitySnapshot(
            source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
            status=forecast_run.status,
            authoritative_timestamp=forecast_run.finished_at,
        )

    if source_type == AvailabilitySourceType.TASK8_DAILY_PREDICTION:
        row_id = _require_database_ref(
            outcome.semantic_identity, allowed_types=("database_row_id",)
        )
        daily_prediction = cast(
            MaturityDailyPredictionModel | None,
            await session.get(MaturityDailyPredictionModel, row_id),
        )
        parent_forecast = (
            None
            if daily_prediction is None
            else cast(
                MaturityForecastRun | None,
                await session.get(MaturityForecastRun, daily_prediction.forecast_run_id),
            )
        )
        if (
            daily_prediction is None
            or parent_forecast is None
            or parent_forecast.finished_at is None
        ):
            raise HistoricalSourceNotFoundError(f"Task 8 daily prediction {row_id} was not found")
        return Task8DailyPredictionAvailabilitySnapshot(
            source_type=AvailabilitySourceType.TASK8_DAILY_PREDICTION,
            prediction_date=daily_prediction.prediction_date,
            created_at=daily_prediction.created_at,
            parent_authority=_parent_authority_identity(
                source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
                authority_status=parent_forecast.status,
                authority_timestamp=parent_forecast.finished_at,
                persistent_reference=PersistentUpstreamReference(
                    reference_type="database_run_id",
                    reference_value=parent_forecast.id,
                ),
                semantic_input_signature=parent_forecast.source_signature,
                canonical_payload_hash=parent_forecast.source_signature,
            ),
        )

    if source_type == AvailabilitySourceType.TASK9_HARVEST_STATE_RUN:
        run_id = _require_database_ref(
            outcome.semantic_identity, allowed_types=("database_run_id",)
        )
        harvest_run = cast(HarvestStateRun | None, await session.get(HarvestStateRun, run_id))
        if harvest_run is None or harvest_run.created_at is None:
            raise HistoricalSourceNotFoundError(f"Task 9 run {run_id} was not found")
        return Task9HarvestStateRunAvailabilitySnapshot(
            source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
            status=harvest_run.status,
            authoritative_timestamp=harvest_run.created_at,
        )

    if source_type == AvailabilitySourceType.TASK10_TRAINING_RUN:
        run_id = _require_database_ref(
            outcome.semantic_identity, allowed_types=("database_run_id",)
        )
        training_run = cast(
            ResidualModelTrainingRun | None, await session.get(ResidualModelTrainingRun, run_id)
        )
        if training_run is None or training_run.finished_at is None:
            raise HistoricalSourceNotFoundError(f"Task 10 training run {run_id} was not found")
        return Task10TrainingRunAvailabilitySnapshot(
            source_type=AvailabilitySourceType.TASK10_TRAINING_RUN,
            status=training_run.execution_status,
            authoritative_timestamp=training_run.finished_at,
        )

    if source_type == AvailabilitySourceType.TASK10_MODEL_ARTIFACT:
        artifact_id = _require_database_ref(
            outcome.semantic_identity,
            allowed_types=("database_artifact_id",),
        )
        residual_artifact = cast(
            ResidualModelArtifact | None, await session.get(ResidualModelArtifact, artifact_id)
        )
        artifact_training_run = (
            None
            if residual_artifact is None
            else cast(
                ResidualModelTrainingRun | None,
                await session.get(ResidualModelTrainingRun, residual_artifact.training_run_id),
            )
        )
        if (
            residual_artifact is None
            or artifact_training_run is None
            or artifact_training_run.finished_at is None
        ):
            raise HistoricalSourceNotFoundError(f"Task 10 artifact {artifact_id} was not found")
        return Task10ModelArtifactAvailabilitySnapshot(
            source_type=AvailabilitySourceType.TASK10_MODEL_ARTIFACT,
            created_at=residual_artifact.created_at,
            parent_authority=_parent_authority_identity(
                source_type=AvailabilitySourceType.TASK10_TRAINING_RUN,
                authority_status=artifact_training_run.execution_status,
                authority_timestamp=artifact_training_run.finished_at,
                persistent_reference=PersistentUpstreamReference(
                    reference_type="database_run_id",
                    reference_value=artifact_training_run.id,
                ),
                semantic_input_signature=artifact_training_run.training_signature,
                result_hash=artifact_training_run.canonical_payload_hash,
                canonical_payload_hash=artifact_training_run.canonical_payload_hash,
            ),
        )

    if source_type == AvailabilitySourceType.TASK10_PREDICTION_RUN:
        run_id = _require_database_ref(
            outcome.semantic_identity, allowed_types=("database_run_id",)
        )
        prediction_run = cast(
            ResidualModelPredictionRun | None, await session.get(ResidualModelPredictionRun, run_id)
        )
        if prediction_run is None or prediction_run.completed_at is None:
            raise HistoricalSourceNotFoundError(f"Task 10 prediction run {run_id} was not found")
        return Task10PredictionRunAvailabilitySnapshot(
            source_type=AvailabilitySourceType.TASK10_PREDICTION_RUN,
            status=prediction_run.execution_status,
            authoritative_timestamp=prediction_run.completed_at,
        )

    raise UnsupportedSelectionModeError(
        f"availability snapshot builder is not implemented for source_type={source_type.value}"
    )


async def _stage_validate_visibility(
    session: AsyncSession,
    ctx: _StageContext,
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
) -> _StageContext:
    """Stage 2: Validate availability visibility for all resolved inputs."""
    from backend.app.rolling_backtest.schemas import AvailabilitySnapshot

    snapshot_adapter = __import__("pydantic").TypeAdapter(AvailabilitySnapshot)

    # Load persisted availability audits
    audit_result = await session.execute(
        select(RollingBacktestAvailabilityAudit).where(
            RollingBacktestAvailabilityAudit.rolling_node_id == ctx.node_id
        )
    )
    audit_rows = audit_result.scalars().all()
    audit_by_role = {a.source_role: a for a in audit_rows}

    for role, outcome in ctx.resolved_inputs.items():
        audit_row = audit_by_role.get(role)
        if audit_row is None:
            if node.upstream_selection_mode != UpstreamSelectionMode.HISTORICAL_RESOLUTION:
                raise RollingBacktestAuthorityBindingError(
                    f"no availability audit for resolved input role={role}"
                )
            snapshot = await _build_availability_snapshot_for_resolved_input(
                session,
                outcome=outcome,
            )
        else:
            snapshot = snapshot_adapter.validate_python(audit_row.canonical_payload)
        eval_result = evaluate_authority_visibility(
            snapshot=snapshot,
            execution_mode=config.execution_mode,
            forecast_cutoff_at=node.forecast_cutoff_at,
            as_of_local_date=node.as_of_local_date,
            business_timezone=config.cutoff_timezone,
        )
        available_at = _extract_authoritative_available_at(snapshot)
        ctx.availability_audits[role] = AvailabilityAuditOutcome(
            source_role=role,
            source_type=outcome.source_type.value,
            allowed=eval_result.allowed,
            blocker_code=eval_result.blocker_code,
            authoritative_available_at=available_at.isoformat(),
            forecast_cutoff_at=node.forecast_cutoff_at.isoformat(),
            audit_hash=availability_snapshot_audit_hash(snapshot),
            parent_authority=None,
        )
        if not eval_result.allowed:
            if node.upstream_selection_mode == UpstreamSelectionMode.HISTORICAL_RESOLUTION:
                raise HistoricalSourceNotVisibleError(
                    f"historical source role={role} blocked by {eval_result.blocker_code}"
                )
            raise PinnedSourceNotVisibleError(
                f"pinned source role={role} blocked by {eval_result.blocker_code}"
            )
    return ctx


async def _stage_validate_authority_chain(  # noqa: ARG001
    session: AsyncSession,
    ctx: _StageContext,
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
) -> _StageContext:
    """Stage 3: Validate authority chains for all resolved inputs."""
    # For pinned mode, the authority chain is validated by the
    # availability audits (stage 2) and the integrity reload
    # that follows the orchestration snapshot.
    # Here we verify that all resolved inputs have valid hashes.
    for role, outcome in ctx.resolved_inputs.items():
        if outcome.semantic_identity.semantic.semantic_payload_hash == "":
            raise RollingBacktestAuthorityBindingError(
                f"resolved input role={role} has empty semantic_payload_hash"
            )
    return ctx


async def _stage_resolve_task8(  # noqa: ARG001
    session: AsyncSession,
    ctx: _StageContext,
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
) -> _StageContext:
    """Stage 4: Resolve or replay Task 8.

    For historical_observed + pinned: reuse persisted Task 8.
    Verify parent authority chain.
    """
    await _resolve_task8_reuse(
        session,
        ctx,
        config,
        node,
        resolved_inputs=ctx.resolved_inputs,
    )
    return ctx


async def _stage_resolve_task9(  # noqa: ARG001
    session: AsyncSession,
    ctx: _StageContext,
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
) -> _StageContext:
    """Stage 5: Resolve or replay Task 9.

    For historical_observed + pinned: reuse persisted Task 9.
    Verify frozen Task 8 identity matches.
    """
    await _resolve_task9_reuse(
        ctx,
        config,
        node,
        session=session,
        resolved_inputs=ctx.resolved_inputs,
    )
    return ctx


async def _stage_resolve_task10(  # noqa: ARG001
    session: AsyncSession,
    ctx: _StageContext,
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
) -> _StageContext:
    """Stage 6: Resolve or train Task 10.

    For historical_observed + pinned: reuse persisted Task 10.
    Verify training run completed, prediction run completed.
    """
    await _resolve_task10_reuse(
        session,
        ctx,
        config,
        node,
        resolved_inputs=ctx.resolved_inputs,
    )
    return ctx


async def _stage_execute_task10_prediction(  # noqa: ARG001
    session: AsyncSession,
    ctx: _StageContext,
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
) -> _StageContext:
    """Stage 7: Execute Task 10 prediction.

    For historical_observed: reuse persisted prediction only.
    """
    await _execute_task10_prediction_reuse(session, ctx, config, node)
    return ctx


async def _stage_finalize_snapshot(
    session: AsyncSession,
    ctx: _StageContext,
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
) -> _StageContext:
    """Stage 8: Finalize orchestration snapshot.

    Atomic persistence of immutable snapshot.
    """
    from backend.app.rolling_backtest.signatures import (
        node_signature_hash,
        run_signature_hash,
    )

    run_sig = run_signature_hash(config)
    node_sig = node_signature_hash(config, node)

    snapshot_payload = _build_orchestration_snapshot_payload(
        ctx,
        config,
        node,
        run_signature=run_sig,
        node_signature=node_sig,
    )

    await persist_orchestration_snapshot(
        ctx.attempt_id,
        ctx.node_id,
        status="completed",
        terminal_stage=OrchestrationStage.FINALIZE_ORCHESTRATION_SNAPSHOT.value,
        canonical_payload=snapshot_payload,
        session=session,
    )
    return ctx


# ── Blocked/finalize helper ─────────────────────────────────────────────────


async def _finalize_blocked(
    session: AsyncSession,
    ctx: _StageContext,
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
    run: RollingBacktestRun,
    attempt: RollingBacktestAttempt,
    *,
    blocker_code: str,
    error: Exception,
) -> None:
    """Finalize attempt and snapshot as blocked."""
    terminal_stage = _blocked_terminal_stage(ctx)
    diagnostics = _sanitize_diagnostics(
        {
            "error": str(error),
            "error_type": type(error).__name__,
            "blocker_code": blocker_code,
            "last_completed_stage": ctx.last_completed_stage,
            "terminal_stage": terminal_stage,
        }
    )

    await finalize_attempt_with_snapshot(
        attempt.id,
        node_id=ctx.node_id,
        status="blocked",
        current_stage=terminal_stage,
        snapshot_status="blocked",
        terminal_stage=terminal_stage,
        blocker_code=blocker_code,
        structured_error_code=blocker_code,
        sanitized_diagnostics=diagnostics,
        canonical_payload={"blocker_code": blocker_code},
        session=session,
    )

    await update_run_status_from_attempts(session, ctx.run_id)


# ── Outcome builder ──────────────────────────────────────────────────────────


def _build_outcome(
    *,
    ctx: _StageContext,
    config: RollingBacktestConfig,
    node: RollingNodeDefinition,
    run: RollingBacktestRun,
    attempt: RollingBacktestAttempt | None,
    status: str,
    stage: str,
    blocker_code: str | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> NodeOrchestrationOutcome:
    """Build the final orchestration outcome."""

    return NodeOrchestrationOutcome(
        rolling_run_signature=run.run_signature,
        node_signature=node.node_signature if hasattr(node, "node_signature") else "",
        attempt_number=attempt.attempt_number if attempt is not None else 0,
        status=status,
        stage=stage,
        resolved_inputs=tuple(ctx.resolved_inputs.values()),
        availability_audits=tuple(ctx.availability_audits.values()),
        task9_authority=ctx.task9_authority,
        task10_authority=ctx.task10_authority,
        fallback_mode=ctx.fallback_mode,
        blocker_code=blocker_code,
        diagnostics=diagnostics or {},
        started_at=attempt.started_at if attempt is not None else None,
        finished_at=attempt.finished_at if attempt is not None else None,
    )


# ── Helpers ──────────────────────────────────────────────────────────────────


def _config_from_payload(payload: dict[str, Any]) -> RollingBacktestConfig:
    """Reconstruct config from canonical payload."""
    from copy import deepcopy

    from pydantic import TypeAdapter

    # Canonical payloads strip display_label — restore it for validation
    normalized = deepcopy(payload)
    for node in normalized.get("nodes", []):
        for ident in node.get("resolved_upstream_semantic_identities", []):
            sem = ident.get("semantic")
            if isinstance(sem, dict) and "display_label" not in sem:
                sem["display_label"] = "__canonical__"
    adapter = TypeAdapter(RollingBacktestConfig)
    return adapter.validate_python(normalized)
    return adapter.validate_python(payload)


def _node_def_from_payload(
    payload: dict[str, Any],
    config: RollingBacktestConfig,
) -> RollingNodeDefinition:
    """Reconstruct node definition from canonical payload.

    IMPORTANT: Uses deepcopy to avoid mutating the original payload dict.
    Without this, ``sem["display_label"] = "__canonical__"`` would modify
    the shared reference inside the SQLAlchemy model's canonical_payload,
    corrupting it and causing integrity check failures.
    """
    from copy import deepcopy

    from pydantic import TypeAdapter

    # Node canonical payload may include run-level fields that
    # RollingNodeDefinition rejects (extra="forbid"). Strip them.
    _NODE_STRIP_KEYS = {"execution_mode", "cutoff_policy_version"}
    cleaned = {k: deepcopy(v) for k, v in payload.items() if k not in _NODE_STRIP_KEYS}
    # Restore display_label for semantic identities
    for ident in cleaned.get("resolved_upstream_semantic_identities", []):
        sem = ident.get("semantic") if isinstance(ident, dict) else None
        if isinstance(sem, dict) and "display_label" not in sem:
            sem["display_label"] = "__canonical__"
    adapter = TypeAdapter(RollingNodeDefinition)
    node_def = adapter.validate_python(cleaned)
    # Populate resolved identities from config's node matching
    for cfg_node in config.nodes:
        if cfg_node.season_id == node_def.season_id and cfg_node.node_key == node_def.node_key:
            return cfg_node
    return node_def


# ── §5 dispatch lift (bucket #5): replay-mode branch helper ────────────────────


def _replay_task9a_request_marker(
    replay_runtime_identity: ReplayRunIdentity,
) -> Mapping[str, object]:
    """§3 / §5 — assemble a marker ``Task9ARequest`` mapping for replay dispatch.

    The historical 8-stage DAG builds its ``Task9ARequest`` from the
    resolved inputs + canonical season / pool / capacity state. Replay
    mode re-uses that SAME §3 canonical entry point
    :func:`execute_harvest_state_run` (bucket #5 must not call
    :func:`run_harvest_state_model` or any other Task 9 lower-level
    internals).

    Bucket #5 ships the **dispatch scaffolding** only; the full
    mapping construction (season / pool / capacity state) is a
    bucket-6+ concern that requires Task 8 / Task 10 replay binding
    semantics. The marker here is the **minimum contract** the
    replay-pipeline expects: a non-empty mapping carrying an explicit
    replay-correlation-id anchor so
    :func:`execute_harvest_state_run` can produce a fresh
    ``HarvestStateRun`` row whose ``replay_run_correlation_id`` (set
    by the bucket-#4 metadata writer) ties the run back to the
    dispatch.

    A future bucket that builds the canonical Task9ARequest from
    replay-prepared state replaces this marker while keeping the
    replay-pipeline entry point unchanged.
    """
    return {
        "_bucket5_replay_marker": True,
        "replay_correlation_id": replay_runtime_identity.run_correlation_id,
        "replay_code_version": replay_runtime_identity.code_version,
    }


async def _run_replay_pipeline_via_dispatch(
    *,
    session: AsyncSession,
    config: RollingBacktestConfig,
    node_def: RollingNodeDefinition,
    replay_runtime_identity: ReplayRunIdentity,
    replay_dispatch_task9a_request: Mapping[str, object] | Task9ARequest | None = None,
) -> NodeOrchestrationOutcome:
    """§5 dispatch lift (bucket #5) — replay-mode routing into replay_pipeline.

    For ``ExecutionMode.RETROSPECTIVE_REPLAY`` runs the
    :func:`orchestrate_replay_node` entry point with the dispatcher-
    supplied :class:`ReplayRunIdentity`. Returns a
    :class:`NodeOrchestrationOutcome` that satisfies the historical
    8-stage DAG's typed signature so dispatch callers stay
    mode-agnostic.

    The replay pipeline does **not** run the historical 8-stage DAG
    stages 1-7 (those are historical-only). It composes around them
    per §5.5 "composes around (not replaces)"; the historical DAG
    remains a separate code path triggered only by
    ``ExecutionMode.HISTORICAL_OBSERVED``.

    If ``replay_dispatch_task9a_request`` is supplied by the dispatch
    caller, it is forwarded unchanged to :func:`execute_harvest_state_run`;
    otherwise the bucket-#5 marker :func:`_replay_task9a_request_marker`
    is used. Bucket-6+ replaces the marker with a fully-built canonical
    ``Task9ARequest`` derived from the replay-bound Task 8 / Task 9
    state.
    """
    from backend.app.harvest_state.schemas import Task9ARequest as _Task9ARequest
    if replay_dispatch_task9a_request is None:
        task9a_request: Mapping[str, object] | _Task9ARequest = (
            _replay_task9a_request_marker(replay_runtime_identity)
        )
    else:
        task9a_request = replay_dispatch_task9a_request
    replay_outcome: ReplayPipelineOutcome = await orchestrate_replay_node(
        session=session,
        config=config,
        node=node_def,
        task9a_request=task9a_request,
        code_version=replay_runtime_identity.code_version,
        replay_correlation_id=replay_runtime_identity.run_correlation_id,
    )

    now_iso = replay_outcome.replay_executed_at.isoformat()
    diagnostics: dict[str, object] = {
        "bucket": "5",
        "mode": "retrospective_replay",
        "task9_run_id": replay_outcome.task9_run_id,
        "audit_row_count": replay_outcome.audit_row_count,
        "replay_correlation_id": replay_outcome.replay_correlation_id,
        "replay_code_version": replay_outcome.code_version,
        "replay_executed_at": now_iso,
        "dispatch_marker": True,
    }

    # Replay pipeline returns before the historical 8-stage DAG completes,
    # so node-level fields (attempt_number, started_at, finished_at) are
    # the replay-pipeline boundary timestamps.
    _node_signature = (
        node_def.node_signature if hasattr(node_def, "node_signature") else ""
    )
    return NodeOrchestrationOutcome(
        rolling_run_signature=_node_signature,
        node_signature=_node_signature,
        attempt_number=0,
        status="completed",
        stage=OrchestrationStage.FINALIZE_ORCHESTRATION_SNAPSHOT.value,
        resolved_inputs=(),
        availability_audits=(),
        task9_authority=None,
        task10_authority=None,
        fallback_mode="replay_pipeline",
        blocker_code=None,
        diagnostics=diagnostics,
        canonical_payload_hash="",
        started_at=replay_outcome.replay_executed_at,
        finished_at=replay_outcome.replay_executed_at,
    )
