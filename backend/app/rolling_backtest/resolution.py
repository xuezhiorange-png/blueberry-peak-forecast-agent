"""Historical upstream candidate resolution for rolling backtest orchestration.

Typed candidate contract, pinned and historical resolution modes, deterministic
sorting, and ambiguity detection. Source-specific query adapters reuse existing
Task 3/6/7/8/9/10 ORM models and integrity loaders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

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

# ── Typed candidate contract ─────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class HistoricalCandidate:
    """A typed, source-specific upstream candidate for a rolling backtest node."""

    source_role: str
    source_type: AvailabilitySourceType
    persistent_reference: PersistentUpstreamReference
    semantic_identity: ResolvedUpstreamSemanticIdentity
    authoritative_available_at: datetime
    business_version: str | None = None
    canonical_identity_hash: str = ""
    canonical_payload_hash: str = ""

    def __post_init__(self) -> None:
        if not self.canonical_identity_hash:
            payload = self.semantic_identity.semantic.model_dump(
                mode="python", exclude={"display_label"}
            )
            payload_str = canonical_json_dumps(payload)
            object.__setattr__(self, "canonical_identity_hash", sha256_payload(payload_str))
            object.__setattr__(self, "canonical_payload_hash", sha256_payload(payload_str))


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


async def _query_task3_candidates(
    session: AsyncSession,
    node: RollingNodeDefinition,
    execution_mode: ExecutionMode,
) -> list[HistoricalCandidate]:
    """Query Task 3 AnalyticsBuildRun candidates."""
    query = (
        select(AnalyticsBuildRun)
        .where(AnalyticsBuildRun.season_id == node.season_id)
        .where(AnalyticsBuildRun.status == "completed")
        .order_by(AnalyticsBuildRun.finished_at.desc().nullslast())
    )
    result = await session.execute(query)
    rows = result.scalars().all()

    candidates: list[HistoricalCandidate] = []
    for row in rows:
        if row.finished_at is None:
            continue
        if execution_mode == ExecutionMode.HISTORICAL_OBSERVED:
            if row.finished_at > node.forecast_cutoff_at:
                continue

        identity = _build_identity(
            source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
            source_role="task3_analytics_build",
            row_id=row.id,
            version_str=row.aggregation_version,
            config_hash=row.config_hash,
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
            )
        )
    return candidates


async def _query_task6_candidates(
    session: AsyncSession,
    node: RollingNodeDefinition,
) -> list[HistoricalCandidate]:
    """Query Task 6 plan/version candidates from ProductionPlanImportRun."""
    query = (
        select(ProductionPlanImportRun)
        .where(ProductionPlanImportRun.status == "completed")
        .order_by(ProductionPlanImportRun.finished_at.desc().nullslast())
        .limit(10)
    )
    result = await session.execute(query)
    rows = result.scalars().all()

    candidates: list[HistoricalCandidate] = []
    for row in rows:
        if row.finished_at is None:
            continue
        if row.finished_at > node.forecast_cutoff_at:
            continue

        identity = _build_identity(
            source_type=AvailabilitySourceType.TASK6_PLAN_VERSION,
            source_role="task6_plan_version",
            row_id=row.id,
            version_str=row.source_version,
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
            )
        )
    return candidates


async def _query_task7_candidates(
    session: AsyncSession,
    node: RollingNodeDefinition,
) -> list[HistoricalCandidate]:
    """Query Task 7 weather feature run candidates."""
    query = (
        select(WeatherFeatureRun)
        .where(WeatherFeatureRun.status == "completed")
        .order_by(WeatherFeatureRun.finished_at.desc().nullslast())
        .limit(10)
    )
    result = await session.execute(query)
    rows = result.scalars().all()

    candidates: list[HistoricalCandidate] = []
    for row in rows:
        if row.finished_at is None:
            continue
        if row.finished_at > node.forecast_cutoff_at:
            continue

        identity = _build_identity(
            source_type=AvailabilitySourceType.TASK7_WEATHER_OBSERVATION,
            source_role="task7_weather_observation",
            row_id=row.id,
            version_str=row.feature_version,
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
            )
        )
    return candidates


async def _query_task8_model_run_candidates(
    session: AsyncSession,
    node: RollingNodeDefinition,
) -> list[HistoricalCandidate]:
    """Query Task 8 maturity model run candidates."""
    query = (
        select(MaturityModelRun)
        .where(MaturityModelRun.status.in_(["completed", "unavailable"]))
        .where(MaturityModelRun.training_cutoff <= node.as_of_local_date)
        .order_by(MaturityModelRun.finished_at.desc().nullslast())
        .limit(10)
    )
    result = await session.execute(query)
    rows = result.scalars().all()

    candidates: list[HistoricalCandidate] = []
    for row in rows:
        if row.finished_at is None:
            continue
        if row.finished_at > node.forecast_cutoff_at:
            continue

        identity = _build_identity(
            source_type=AvailabilitySourceType.TASK8_MODEL_RUN,
            source_role="task8_model_run",
            row_id=row.id,
            version_str=row.model_version,
            config_hash=row.config_hash,
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
            )
        )
    return candidates


async def _query_task8_forecast_run_candidates(
    session: AsyncSession,
    node: RollingNodeDefinition,
) -> list[HistoricalCandidate]:
    """Query Task 8 maturity forecast run candidates."""
    query = (
        select(MaturityForecastRun)
        .where(MaturityForecastRun.status.in_(["completed", "unavailable"]))
        .order_by(MaturityForecastRun.finished_at.desc().nullslast())
        .limit(10)
    )
    result = await session.execute(query)
    rows = result.scalars().all()

    candidates: list[HistoricalCandidate] = []
    for row in rows:
        if row.finished_at is None:
            continue
        if row.finished_at > node.forecast_cutoff_at:
            continue

        identity = _build_identity(
            source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
            source_role="task8_forecast_run",
            row_id=row.id,
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
) -> list[HistoricalCandidate]:
    """Query Task 9 harvest state run candidates."""
    query = (
        select(HarvestStateRun)
        .where(HarvestStateRun.as_of_date <= node.as_of_local_date)
        .where(HarvestStateRun.status.in_(["completed", "blocked"]))
        .order_by(HarvestStateRun.created_at.desc().nullslast())
        .limit(10)
    )
    result = await session.execute(query)
    rows = result.scalars().all()

    candidates: list[HistoricalCandidate] = []
    for row in rows:
        if row.created_at is None:
            continue
        if row.created_at > node.forecast_cutoff_at:
            continue

        identity = _build_identity(
            source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
            source_role="task9_structural_forecast",
            row_id=row.id,
            version_str=row.output_schema_version,
            config_hash=row.config_hash,
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
            )
        )
    return candidates


async def _query_task10_training_candidates(
    session: AsyncSession,
    node: RollingNodeDefinition,
) -> list[HistoricalCandidate]:
    """Query Task 10 residual model training run candidates."""
    query = (
        select(ResidualModelTrainingRun)
        .where(ResidualModelTrainingRun.execution_status.in_(["completed", "blocked", "failed"]))
        .order_by(ResidualModelTrainingRun.finished_at.desc().nullslast())
        .limit(10)
    )
    result = await session.execute(query)
    rows = result.scalars().all()

    candidates: list[HistoricalCandidate] = []
    for row in rows:
        if row.finished_at is None:
            continue
        if row.finished_at > node.forecast_cutoff_at:
            continue

        identity = _build_identity(
            source_type=AvailabilitySourceType.TASK10_TRAINING_RUN,
            source_role="task10_training_run",
            row_id=row.id,
            version_str=row.model_version,
            config_hash=row.config_hash,
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
            )
        )
    return candidates


# ── Internal helpers ─────────────────────────────────────────────────────────


def _build_identity(
    *,
    source_type: AvailabilitySourceType,
    source_role: str,
    row_id: int,
    version_str: str | None = None,
    config_hash: str | None = None,
) -> ResolvedUpstreamSemanticIdentity:
    """Build a semantic identity payload from an ORM row's stable fields."""
    payload = {
        "source_type": source_type.value,
        "source_role": source_role,
        "db_id": row_id,
        "version": version_str or "unknown",
        "config_hash": config_hash or "",
    }
    payload_str = canonical_json_dumps(payload)
    payload_hash = sha256_payload(payload_str)

    return ResolvedUpstreamSemanticIdentity(
        source_type=source_type,
        source_role=source_role,
        semantic=UpstreamSemanticIdentityPayload(
            schema_version="task11-resolution-v1",
            display_label=f"{source_type.value}:{row_id}",
            semantic_payload_hash=payload_hash,
            canonical_payload_hash=payload_hash,
            business_version=version_str,
        ),
    )


# ── Dispatch ─────────────────────────────────────────────────────────────────


def _reverse_hex(hex_str: str) -> str:
    """Reverse a hex string so that ASC hex order becomes DESC with reverse=True."""
    return "".join(
        chr(ord("f") - ord(c) + ord("0"))
        if "0" <= c <= "9"
        else chr(ord("f") - ord(c) + ord("a"))
        if "a" <= c <= "f"
        else c
        for c in hex_str
    )


_SOURCE_QUERY_MAP: dict[
    AvailabilitySourceType,
    Any,
] = {
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
        result = await adapter(session, node, execution_mode)
        return result  # type: ignore[no-any-return]
    return []


# ── Resolution engine ───────────────────────────────────────────────────────


async def resolve_pinned(
    session: AsyncSession,
    *,
    pinned_identity: ResolvedUpstreamSemanticIdentity,
    node: RollingNodeDefinition,
    execution_mode: ExecutionMode,
) -> ResolutionResult:
    """Resolve a pinned upstream source: verify exact match, fail closed on mismatch."""
    source_type = pinned_identity.source_type

    candidates = await _query_candidates_by_type(session, node, execution_mode, source_type)

    pinned_ref_value = (
        pinned_identity.persistent_reference.reference_value
        if pinned_identity.persistent_reference
        else None
    )

    matched = None
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

    if matched.source_type != source_type:
        return ResolutionResult(
            source_role=pinned_identity.source_role,
            source_type=source_type,
            candidates=tuple(candidates),
            blocked=True,
            blocker_code="pinned_source_type_mismatch",
        )

    if (
        pinned_identity.semantic.canonical_payload_hash
        and matched.semantic_identity.semantic.canonical_payload_hash
        and pinned_identity.semantic.canonical_payload_hash
        != matched.semantic_identity.semantic.canonical_payload_hash
    ):
        return ResolutionResult(
            source_role=pinned_identity.source_role,
            source_type=source_type,
            candidates=tuple(candidates),
            blocked=True,
            blocker_code="pinned_source_identity_mismatch",
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
    """Resolve historical candidates deterministically by visibility rules."""
    candidates = await _query_candidates_by_type(session, node, execution_mode, source_type)

    if not candidates:
        return ResolutionResult(
            source_role=source_role,
            source_type=source_type,
            candidates=(),
            blocked=True,
            blocker_code="historical_source_not_found",
        )

    visible = [c for c in candidates if c.authoritative_available_at <= node.forecast_cutoff_at]
    if not visible:
        return ResolutionResult(
            source_role=source_role,
            source_type=source_type,
            candidates=tuple(candidates),
            blocked=True,
            blocker_code="historical_source_not_visible",
            diagnostics={"cutoff": node.forecast_cutoff_at.isoformat()},
        )

    # Deterministic sort: authoritative time DESC, version DESC,
    # identity hash ASC, payload hash ASC
    visible.sort(
        key=lambda c: (
            c.authoritative_available_at,
            c.business_version or "",
            # Reverse hash order to get ASC when combined with reverse=True below
            _reverse_hex(c.canonical_identity_hash),
            _reverse_hex(c.canonical_payload_hash),
        ),
        reverse=True,
    )

    top = visible[0]

    # Ambiguity detection
    if len(visible) > 1:
        second = visible[1]
        top_key = (
            top.authoritative_available_at,
            top.business_version,
            top.canonical_identity_hash,
            top.canonical_payload_hash,
        )
        second_key = (
            second.authoritative_available_at,
            second.business_version,
            second.canonical_identity_hash,
            second.canonical_payload_hash,
        )

        if top_key == second_key:
            if top.canonical_identity_hash != second.canonical_identity_hash:
                return ResolutionResult(
                    source_role=source_role,
                    source_type=source_type,
                    candidates=tuple(visible),
                    blocked=True,
                    blocker_code="ambiguous_historical_candidate",
                    diagnostics={
                        "top_hash": top.canonical_identity_hash,
                        "second_hash": second.canonical_identity_hash,
                    },
                )

    return ResolutionResult(
        source_role=source_role,
        source_type=source_type,
        candidates=tuple(visible),
        resolved=top,
    )
