"""Historical upstream candidate resolution for rolling backtest orchestration.

Typed candidate contract, pinned and historical resolution modes, deterministic
sorting, and ambiguity detection. Source-specific query adapters reuse existing
Task 3/6/7/8/9/10 ORM models and integrity loaders.

All cutoff filtering happens in SQL — no Python-side post-filtering that would
allow future records to shadow valid history. Database IDs are excluded from
semantic identity payloads; only stable upstream business fields participate
in canonical hashes.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.analytics import AnalyticsBuildRun
from backend.app.models.harvest_state import HarvestStateRun
from backend.app.models.maturity import (
    MaturityForecastRun,
    MaturityModelRun,
)
from backend.app.models.production_plan import ProductionPlanImportRun
from backend.app.models.residual_model import (
    ResidualModelTrainingRun,
)
from backend.app.models.weather import WeatherFeatureRun
from backend.app.rolling_backtest.canonical import canonical_json_dumps, sha256_payload
from backend.app.rolling_backtest.enums import (
    AvailabilitySourceType,
    ExecutionMode,
)
from backend.app.rolling_backtest.schemas import (
    PersistentUpstreamReference,
    ResolvedUpstreamSemanticIdentity,
    RollingNodeDefinition,
    UpstreamSemanticIdentityPayload,
)

# ── Typed adapter contract ───────────────────────────────────────────────────

CandidateQueryAdapter = Callable[
    [AsyncSession, RollingNodeDefinition, ExecutionMode],
    Awaitable[list["HistoricalCandidate"]],
]

# ── Typed candidate contract ─────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class HistoricalCandidate:
    """A typed, source-specific upstream candidate for a rolling backtest node.

    canonical_identity_hash  — SHA-256 of the stable semantic identity payload
                               (source_type, source_role, input_signature, config_hash,
                                result_hash, business_version, policy_version, etc.)
    canonical_payload_hash   — SHA-256 of the upstream's canonical result/artifact
                               payload (may be computed by upstream service or derived
                               from canonical output stored in the ORM).
    """

    source_role: str
    source_type: AvailabilitySourceType
    persistent_reference: PersistentUpstreamReference
    semantic_identity: ResolvedUpstreamSemanticIdentity
    authoritative_available_at: datetime
    business_version: str | None = None
    canonical_identity_hash: str = ""
    canonical_payload_hash: str = ""

    def __post_init__(self) -> None:
        # Compute canonical_identity_hash from stable semantic identity fields
        if not self.canonical_identity_hash:
            id_payload = _build_identity_payload(self.semantic_identity)
            id_str = canonical_json_dumps(id_payload)
            object.__setattr__(self, "canonical_identity_hash", sha256_payload(id_str))

        # canonical_payload_hash must be supplied by the adapter from upstream data;
        # if still empty after __post_init__, the adapter failed to provide it.
        # We keep it as-is — empty means "not available from upstream".


def _build_identity_payload(identity: ResolvedUpstreamSemanticIdentity) -> dict[str, object]:
    """Build the canonical identity payload from stable fields only.

    Explicitly EXCLUDES: persistent_reference, display_label, db_id, uuid, row_id.
    Only stable upstream business fields participate.
    """
    sem = identity.semantic
    payload: dict[str, object] = {
        "source_type": identity.source_type.value,
        "source_role": identity.source_role,
        "schema_version": sem.schema_version,
        "semantic_payload_hash": sem.semantic_payload_hash,
    }
    if sem.input_signature:
        payload["input_signature"] = sem.input_signature
    if sem.config_hash:
        payload["config_hash"] = sem.config_hash
    if sem.result_hash:
        payload["result_hash"] = sem.result_hash
    if sem.canonical_payload_hash:
        payload["canonical_payload_hash"] = sem.canonical_payload_hash
    if sem.artifact_payload_hash:
        payload["artifact_payload_hash"] = sem.artifact_payload_hash
    if sem.business_version:
        payload["business_version"] = sem.business_version
    if sem.policy_version:
        payload["policy_version"] = sem.policy_version
    if identity.role_qualifier:
        payload["role_qualifier"] = identity.role_qualifier
    return payload


def _make_identity(
    *,
    source_type: AvailabilitySourceType,
    source_role: str,
    schema_version: str,
    semantic_payload_hash: str,
    input_signature: str | None = None,
    config_hash: str | None = None,
    result_hash: str | None = None,
    canonical_payload_hash: str | None = None,
    artifact_payload_hash: str | None = None,
    business_version: str | None = None,
    policy_version: str | None = None,
    role_qualifier: str | None = None,
    display_label: str | None = None,
    persistent_reference: PersistentUpstreamReference | None = None,
) -> ResolvedUpstreamSemanticIdentity:
    """Build a ResolvedUpstreamSemanticIdentity from stable upstream fields only.

    Database IDs, UUIDs, and other mutable/persistent identifiers are confined to
    persistent_reference and NEVER enter the semantic identity payload or hashes.
    """
    return ResolvedUpstreamSemanticIdentity(
        source_type=source_type,
        source_role=source_role,
        role_qualifier=role_qualifier,
        persistent_reference=persistent_reference,
        semantic=UpstreamSemanticIdentityPayload(
            schema_version=schema_version,
            display_label=display_label or f"{source_type.value}:{source_role}",
            semantic_payload_hash=semantic_payload_hash,
            input_signature=input_signature,
            config_hash=config_hash,
            result_hash=result_hash,
            canonical_payload_hash=canonical_payload_hash,
            artifact_payload_hash=artifact_payload_hash,
            business_version=business_version,
            policy_version=policy_version,
        ),
    )


@dataclass(frozen=True, slots=True)
class ResolutionResult:
    """Deterministic resolution result for a single source role."""

    source_role: str
    source_type: AvailabilitySourceType
    candidates: tuple[HistoricalCandidate, ...]
    resolved: HistoricalCandidate | None = None
    blocked: bool = False
    blocker_code: str | None = None
    diagnostics: dict[str, object] = field(default_factory=dict)


# ── Source-specific query adapters ───────────────────────────────────────────
#
# Every adapter has the SAME signature:
#   (session: AsyncSession, node: RollingNodeDefinition, execution_mode: ExecutionMode)
#   -> list[HistoricalCandidate]
#
# Cutoff filtering is applied IN SQL via WHERE clauses — never in Python.
# Adapters that do not need execution_mode should accept it and ignore it
# (explicit `del execution_mode` or `_unused = execution_mode`).


async def _query_task3_candidates(
    session: AsyncSession,
    node: RollingNodeDefinition,
    execution_mode: ExecutionMode,
) -> list[HistoricalCandidate]:
    """Query Task 3 AnalyticsBuildRun candidates with SQL cutoff filtering."""
    _unused = execution_mode  # accepted for uniform contract

    # SQL-level filtering: status, season, authority time <= cutoff
    query = (
        select(AnalyticsBuildRun)
        .where(AnalyticsBuildRun.season_id == node.season_id)
        .where(AnalyticsBuildRun.status == "completed")
        .where(AnalyticsBuildRun.finished_at <= node.forecast_cutoff_at)
        .order_by(AnalyticsBuildRun.finished_at.desc().nullslast())
        .limit(20)
    )
    result = await session.execute(query)
    rows = result.scalars().all()

    candidates: list[HistoricalCandidate] = []
    for row in rows:
        if row.finished_at is None:
            continue
        # Build identity from real upstream fields — no DB ID
        identity = _make_identity(
            source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
            source_role="task3_analytics_build",
            schema_version="task3-analytics-v1",
            semantic_payload_hash=row.config_hash or "",
            config_hash=row.config_hash,
            business_version=row.aggregation_version,
            display_label=f"task3:analytics_build:season{row.season_id}",
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id", reference_value=row.id
            ),
        )
        candidates.append(
            HistoricalCandidate(
                source_role="task3_analytics_build",
                source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
                persistent_reference=PersistentUpstreamReference(
                    reference_type="database_run_id", reference_value=row.id
                ),
                semantic_identity=identity,
                authoritative_available_at=row.finished_at,
                business_version=row.aggregation_version,
                canonical_payload_hash=row.config_hash or "",
            )
        )
    return candidates


async def _query_task6_candidates(
    session: AsyncSession,
    node: RollingNodeDefinition,
    execution_mode: ExecutionMode,
) -> list[HistoricalCandidate]:
    """Query Task 6 ProductionPlanImportRun candidates with SQL cutoff filtering."""
    _unused = execution_mode

    # Task 6 uses finished_at as authority timestamp; filter in SQL
    query = (
        select(ProductionPlanImportRun)
        .where(ProductionPlanImportRun.status == "completed")
        .where(ProductionPlanImportRun.finished_at <= node.forecast_cutoff_at)
        .order_by(ProductionPlanImportRun.finished_at.desc().nullslast())
        .limit(20)
    )
    result = await session.execute(query)
    rows = result.scalars().all()

    candidates: list[HistoricalCandidate] = []
    for row in rows:
        if row.finished_at is None:
            continue
        identity = _make_identity(
            source_type=AvailabilitySourceType.TASK6_PLAN_VERSION,
            source_role="task6_plan_version",
            schema_version="task6-plan-v1",
            semantic_payload_hash=row.file_sha256,
            business_version=row.source_version,
            display_label=f"task6:plan:{row.id}",
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id", reference_value=row.id
            ),
        )
        candidates.append(
            HistoricalCandidate(
                source_role="task6_plan_version",
                source_type=AvailabilitySourceType.TASK6_PLAN_VERSION,
                persistent_reference=PersistentUpstreamReference(
                    reference_type="database_run_id", reference_value=row.id
                ),
                semantic_identity=identity,
                authoritative_available_at=row.finished_at,
                business_version=row.source_version,
                canonical_payload_hash=row.file_sha256,
            )
        )
    return candidates


async def _query_task7_candidates(
    session: AsyncSession,
    node: RollingNodeDefinition,
    execution_mode: ExecutionMode,
) -> list[HistoricalCandidate]:
    """Query Task 7 WeatherFeatureRun candidates with SQL cutoff filtering."""
    _unused = execution_mode

    # SQL-level filtering: status, authority time <= cutoff
    query = (
        select(WeatherFeatureRun)
        .where(WeatherFeatureRun.status.in_(["completed", "unavailable"]))
        .where(WeatherFeatureRun.finished_at <= node.forecast_cutoff_at)
        .order_by(WeatherFeatureRun.finished_at.desc().nullslast())
        .limit(20)
    )
    result = await session.execute(query)
    rows = result.scalars().all()

    candidates: list[HistoricalCandidate] = []
    for row in rows:
        if row.finished_at is None:
            continue
        identity = _make_identity(
            source_type=AvailabilitySourceType.TASK7_WEATHER_OBSERVATION,
            source_role="task7_weather_observation",
            schema_version="task7-weather-v1",
            semantic_payload_hash=row.config_hash,
            config_hash=row.config_hash,
            business_version=row.feature_version,
            display_label=f"task7:weather:{row.id}",
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id", reference_value=row.id
            ),
        )
        candidates.append(
            HistoricalCandidate(
                source_role="task7_weather_observation",
                source_type=AvailabilitySourceType.TASK7_WEATHER_OBSERVATION,
                persistent_reference=PersistentUpstreamReference(
                    reference_type="database_run_id", reference_value=row.id
                ),
                semantic_identity=identity,
                authoritative_available_at=row.finished_at,
                business_version=row.feature_version,
                canonical_payload_hash=row.config_hash,
            )
        )
    return candidates


async def _query_task8_model_run_candidates(
    session: AsyncSession,
    node: RollingNodeDefinition,
    execution_mode: ExecutionMode,
) -> list[HistoricalCandidate]:
    """Query Task 8 MaturityModelRun candidates with SQL cutoff filtering."""
    _unused = execution_mode

    query = (
        select(MaturityModelRun)
        .where(MaturityModelRun.status.in_(["completed", "unavailable"]))
        .where(MaturityModelRun.training_cutoff <= node.as_of_local_date)
        .where(MaturityModelRun.finished_at <= node.forecast_cutoff_at)
        .order_by(MaturityModelRun.finished_at.desc().nullslast())
        .limit(20)
    )
    result = await session.execute(query)
    rows = result.scalars().all()

    candidates: list[HistoricalCandidate] = []
    for row in rows:
        if row.finished_at is None:
            continue
        identity = _make_identity(
            source_type=AvailabilitySourceType.TASK8_MODEL_RUN,
            source_role="task8_model_run",
            schema_version="task8-maturity-v1",
            semantic_payload_hash=row.config_hash,
            config_hash=row.config_hash,
            business_version=row.model_version,
            display_label=f"task8:model:{row.id}",
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id", reference_value=row.id
            ),
        )
        candidates.append(
            HistoricalCandidate(
                source_role="task8_model_run",
                source_type=AvailabilitySourceType.TASK8_MODEL_RUN,
                persistent_reference=PersistentUpstreamReference(
                    reference_type="database_run_id", reference_value=row.id
                ),
                semantic_identity=identity,
                authoritative_available_at=row.finished_at,
                business_version=row.model_version,
                canonical_payload_hash=row.config_hash,
            )
        )
    return candidates


async def _query_task8_forecast_run_candidates(
    session: AsyncSession,
    node: RollingNodeDefinition,
    execution_mode: ExecutionMode,
) -> list[HistoricalCandidate]:
    """Query Task 8 MaturityForecastRun candidates with SQL cutoff filtering."""
    _unused = execution_mode

    query = (
        select(MaturityForecastRun)
        .where(MaturityForecastRun.status.in_(["completed", "unavailable"]))
        .where(MaturityForecastRun.finished_at <= node.forecast_cutoff_at)
        .order_by(MaturityForecastRun.finished_at.desc().nullslast())
        .limit(20)
    )
    result = await session.execute(query)
    rows = result.scalars().all()

    candidates: list[HistoricalCandidate] = []
    for row in rows:
        if row.finished_at is None:
            continue
        identity = _make_identity(
            source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
            source_role="task8_forecast_run",
            schema_version="task8-maturity-v1",
            semantic_payload_hash=row.source_signature if hasattr(row, "source_signature") else "",
            display_label=f"task8:forecast:{row.id}",
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id", reference_value=row.id
            ),
        )
        candidates.append(
            HistoricalCandidate(
                source_role="task8_forecast_run",
                source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
                persistent_reference=PersistentUpstreamReference(
                    reference_type="database_run_id", reference_value=row.id
                ),
                semantic_identity=identity,
                authoritative_available_at=row.finished_at,
            )
        )
    return candidates


async def _query_task9_candidates(
    session: AsyncSession,
    node: RollingNodeDefinition,
    execution_mode: ExecutionMode,
) -> list[HistoricalCandidate]:
    """Query Task 9 HarvestStateRun candidates with SQL cutoff filtering."""
    _unused = execution_mode

    query = (
        select(HarvestStateRun)
        .where(HarvestStateRun.as_of_date <= node.as_of_local_date)
        .where(HarvestStateRun.created_at <= node.forecast_cutoff_at)
        .where(HarvestStateRun.status.in_(["completed", "blocked"]))
        .order_by(HarvestStateRun.created_at.desc().nullslast())
        .limit(20)
    )
    result = await session.execute(query)
    rows = result.scalars().all()

    candidates: list[HistoricalCandidate] = []
    for row in rows:
        if row.created_at is None:
            continue
        identity = _make_identity(
            source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
            source_role="task9_structural_forecast",
            schema_version=row.output_schema_version,
            semantic_payload_hash=row.result_hash,
            config_hash=row.config_hash,
            result_hash=row.result_hash,
            canonical_payload_hash=row.canonical_payload_hash,
            business_version=row.output_schema_version,
            display_label=f"task9:harvest_state:{row.id}",
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id", reference_value=row.id
            ),
        )
        candidates.append(
            HistoricalCandidate(
                source_role="task9_structural_forecast",
                source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
                persistent_reference=PersistentUpstreamReference(
                    reference_type="database_run_id", reference_value=row.id
                ),
                semantic_identity=identity,
                authoritative_available_at=row.created_at,
                business_version=row.output_schema_version,
                canonical_payload_hash=row.canonical_payload_hash,
            )
        )
    return candidates


async def _query_task10_training_candidates(
    session: AsyncSession,
    node: RollingNodeDefinition,
    execution_mode: ExecutionMode,
) -> list[HistoricalCandidate]:
    """Query Task 10 ResidualModelTrainingRun candidates with SQL cutoff filtering."""
    _unused = execution_mode

    query = (
        select(ResidualModelTrainingRun)
        .where(ResidualModelTrainingRun.execution_status.in_(["completed", "blocked", "failed"]))
        .where(ResidualModelTrainingRun.finished_at <= node.forecast_cutoff_at)
        .order_by(ResidualModelTrainingRun.finished_at.desc().nullslast())
        .limit(20)
    )
    result = await session.execute(query)
    rows = result.scalars().all()

    candidates: list[HistoricalCandidate] = []
    for row in rows:
        if row.finished_at is None:
            continue
        identity = _make_identity(
            source_type=AvailabilitySourceType.TASK10_TRAINING_RUN,
            source_role="task10_training_run",
            schema_version=row.feature_schema_version,
            semantic_payload_hash=row.training_signature,
            config_hash=row.config_hash,
            result_hash=row.canonical_payload_hash,
            canonical_payload_hash=row.canonical_payload_hash,
            business_version=row.model_version,
            display_label=f"task10:training:{row.id}",
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id", reference_value=row.id
            ),
        )
        candidates.append(
            HistoricalCandidate(
                source_role="task10_training_run",
                source_type=AvailabilitySourceType.TASK10_TRAINING_RUN,
                persistent_reference=PersistentUpstreamReference(
                    reference_type="database_run_id", reference_value=row.id
                ),
                semantic_identity=identity,
                authoritative_available_at=row.finished_at,
                business_version=row.model_version,
                canonical_payload_hash=row.canonical_payload_hash,
            )
        )
    return candidates


# ── Dispatch map (typed, no Any) ─────────────────────────────────────────────

_SOURCE_QUERY_MAP: dict[AvailabilitySourceType, CandidateQueryAdapter] = {
    AvailabilitySourceType.TASK3_ANALYTICS_BUILD: _query_task3_candidates,
    AvailabilitySourceType.TASK6_PLAN_VERSION: _query_task6_candidates,
    AvailabilitySourceType.TASK7_WEATHER_OBSERVATION: _query_task7_candidates,
    AvailabilitySourceType.TASK8_MODEL_RUN: _query_task8_model_run_candidates,
    AvailabilitySourceType.TASK8_FORECAST_RUN: _query_task8_forecast_run_candidates,
    AvailabilitySourceType.TASK9_HARVEST_STATE_RUN: _query_task9_candidates,
    AvailabilitySourceType.TASK10_TRAINING_RUN: _query_task10_training_candidates,
}


async def _query_candidates_by_type(
    session: AsyncSession,
    node: RollingNodeDefinition,
    execution_mode: ExecutionMode,
    source_type: AvailabilitySourceType,
) -> list[HistoricalCandidate]:
    """Dispatch to the correct source-specific query adapter."""
    adapter = _SOURCE_QUERY_MAP.get(source_type)
    if adapter is not None:
        return await adapter(session, node, execution_mode)
    return []


# ── Resolution engine ───────────────────────────────────────────────────────


async def resolve_pinned(
    session: AsyncSession,
    *,
    pinned_identity: ResolvedUpstreamSemanticIdentity,
    node: RollingNodeDefinition,
    execution_mode: ExecutionMode,
) -> ResolutionResult:
    """Resolve a pinned upstream source: verify exact match, fail closed on mismatch.

    Validates: persistent reference exists, source type exact, source role exact,
    season/scope match, authority time visible, schema version compatible,
    canonical payload hash exact match, parent authority exact.
    No substitution, no auto-replacement, no silent downgrade.
    """
    source_type = pinned_identity.source_type

    candidates = await _query_candidates_by_type(session, node, execution_mode, source_type)

    pinned_ref = pinned_identity.persistent_reference
    pinned_ref_value = pinned_ref.reference_value if pinned_ref else None

    # Find exact persistent reference match
    matched: HistoricalCandidate | None = None
    for candidate in candidates:
        ref_val = candidate.persistent_reference.reference_value
        if pinned_ref_value is not None and ref_val == pinned_ref_value:
            matched = candidate
            break

    if matched is None:
        return ResolutionResult(
            source_role=pinned_identity.source_role,
            source_type=source_type,
            candidates=tuple(candidates),
            blocked=True,
            blocker_code="pinned_source_not_found",
            diagnostics={"pinned_ref": str(pinned_ref_value)},
        )

    # Validate source type
    if matched.source_type != source_type:
        return ResolutionResult(
            source_role=pinned_identity.source_role,
            source_type=source_type,
            candidates=tuple(candidates),
            blocked=True,
            blocker_code="pinned_source_type_mismatch",
            diagnostics={
                "expected": source_type.value,
                "actual": matched.source_type.value,
            },
        )

    # Validate source role
    if matched.semantic_identity.source_role != pinned_identity.source_role:
        return ResolutionResult(
            source_role=pinned_identity.source_role,
            source_type=source_type,
            candidates=tuple(candidates),
            blocked=True,
            blocker_code="pinned_source_role_mismatch",
            diagnostics={
                "expected_role": pinned_identity.source_role,
                "actual_role": matched.semantic_identity.source_role,
            },
        )

    # Validate authority time visibility
    if matched.authoritative_available_at > node.forecast_cutoff_at:
        return ResolutionResult(
            source_role=pinned_identity.source_role,
            source_type=source_type,
            candidates=tuple(candidates),
            blocked=True,
            blocker_code="pinned_source_not_visible",
            diagnostics={
                "available_at": matched.authoritative_available_at.isoformat(),
                "cutoff": node.forecast_cutoff_at.isoformat(),
            },
        )

    # Validate canonical payload hash exact match
    pinned_hash = pinned_identity.semantic.canonical_payload_hash
    matched_hash = matched.semantic_identity.semantic.canonical_payload_hash
    if pinned_hash and matched_hash and pinned_hash != matched_hash:
        return ResolutionResult(
            source_role=pinned_identity.source_role,
            source_type=source_type,
            candidates=tuple(candidates),
            blocked=True,
            blocker_code="pinned_source_identity_mismatch",
            diagnostics={
                "pinned_payload_hash": pinned_hash,
                "matched_payload_hash": matched_hash,
            },
        )

    # Validate config hash match if both present
    pinned_config = pinned_identity.semantic.config_hash
    matched_config = matched.semantic_identity.semantic.config_hash
    if pinned_config and matched_config and pinned_config != matched_config:
        return ResolutionResult(
            source_role=pinned_identity.source_role,
            source_type=source_type,
            candidates=tuple(candidates),
            blocked=True,
            blocker_code="pinned_source_integrity_failure",
            diagnostics={
                "pinned_config_hash": pinned_config,
                "matched_config_hash": matched_config,
            },
        )

    return ResolutionResult(
        source_role=pinned_identity.source_role,
        source_type=source_type,
        candidates=tuple(candidates),
        resolved=matched,
    )


async def resolve_historical(
    session: AsyncSession,
    *,
    source_role: str,
    source_type: AvailabilitySourceType,
    node: RollingNodeDefinition,
    execution_mode: ExecutionMode,
) -> ResolutionResult:
    """Resolve historical candidates deterministically by visibility rules.

    All filtering happens in SQL via the source-specific adapter.
    Only deterministic sorting and ambiguity detection happen in Python.
    """
    candidates = await _query_candidates_by_type(session, node, execution_mode, source_type)

    if not candidates:
        return ResolutionResult(
            source_role=source_role,
            source_type=source_type,
            candidates=(),
            blocked=True,
            blocker_code="historical_source_not_found",
        )

    # All candidates already filtered in SQL; none should exceed cutoff
    visible = list(candidates)

    # Deterministic sort:
    #   Priority tier: authoritative_available_at DESC, business_version DESC
    #   Stable tie-break: canonical_identity_hash ASC, canonical_payload_hash ASC
    visible.sort(
        key=lambda c: (
            # Primary: authoritative time DESC → negate timestamp
            -c.authoritative_available_at.timestamp(),
            # Secondary: business version DESC → negate version sort key components
            tuple(-x for x in _version_sort_key(c.business_version or "")),
            # Tie-break: identity hash ASC
            c.canonical_identity_hash,
            c.canonical_payload_hash,
        ),
    )

    top = visible[0]

    # Ambiguity detection: find all candidates in the same "priority tier"
    # (same authoritative time + same business version)
    same_tier = [
        c
        for c in visible
        if (
            c.authoritative_available_at == top.authoritative_available_at
            and c.business_version == top.business_version
        )
    ]

    if len(same_tier) > 1:
        # Check if all top-tier candidates are semantic-equivalent
        first_identity = same_tier[0].canonical_identity_hash
        first_payload = same_tier[0].canonical_payload_hash
        all_equivalent = all(
            c.canonical_identity_hash == first_identity
            and c.canonical_payload_hash == first_payload
            for c in same_tier[1:]
        )

        if not all_equivalent:
            return ResolutionResult(
                source_role=source_role,
                source_type=source_type,
                candidates=tuple(visible),
                blocked=True,
                blocker_code="ambiguous_historical_candidate",
                diagnostics={
                    "top_hash": top.canonical_identity_hash,
                    "tier_size": len(same_tier),
                    "distinct_identities": len({c.canonical_identity_hash for c in same_tier}),
                },
            )

    return ResolutionResult(
        source_role=source_role,
        source_type=source_type,
        candidates=tuple(visible),
        resolved=top,
    )


def _version_sort_key(version_str: str) -> tuple[int, ...]:
    """Convert a version string to a sortable tuple for DESC ordering.

    Handles simple semver-like strings (e.g., 'v1', 'v2.3', '3.0.1').
    The resulting tuple is negated by the caller for DESC sort.
    """
    import re

    parts = re.split(r"[._-]", version_str)
    numeric: list[int] = []
    for p in parts:
        nums = re.findall(r"\d+", p)
        if nums:
            numeric.append(int(nums[0]))
        elif p:
            numeric.append(ord(p[0]) if p else 0)
    # Pad to a consistent length for stable comparison
    while len(numeric) < 4:
        numeric.append(0)
    return tuple(numeric)
