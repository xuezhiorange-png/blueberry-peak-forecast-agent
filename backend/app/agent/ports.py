"""TASK-013 Slice A — Protocol ports for dependency injection.

Adapters MUST receive explicit typed dependencies through these Protocol
interfaces rather than importing global mutable state or instantiating
upstream services directly.  Tests may substitute deterministic fakes; one
SQLite-backed integration test per adapter is required (per §15).

No port touches the network, the shell, or any secret store.  All ports are
read-only with respect to side effects unless the underlying upstream service
itself has a write semantics that the agent uses for read-through (e.g.
TASK-012 GET-only path).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agent.schemas import (
    AdvancedOverrides,
    ForecastDailyRow,
    NormalizedAgentRequest,
    ResolvedLocation,
    Task8Authority,
    Task9Authority,
    Task10Authority,
    Task11Authority,
    Task12Authority,
)

if TYPE_CHECKING:
    from backend.app.agent.adapters.parameters import ParameterPrior


# --- §13 resolve_location -------------------------------------------------

class LocationResolverPort(Protocol):
    """Adapter to ``backend.app.planning.location.resolve_location_input``."""

    async def resolve(
        self,
        *,
        session: AsyncSession,
        location: dict[str, Any],
        as_of_date: date,
    ) -> ResolvedLocation:
        ...


# --- §14 infer_parameters -------------------------------------------------

class ParameterPriorPort(Protocol):
    """Adapter that runs the parameter inference pipeline per variety."""

    async def resolve_parameter(
        self,
        *,
        session: AsyncSession,
        variety_id: int,
        parameter_name: str,
        resolved_location: ResolvedLocation,
        effective_as_of_date: date,
        widening_factor: Decimal,
        monotonic_step: int,
    ) -> "ParameterPrior":
        ...


# --- §15 forecast_daily_curve composition --------------------------------

class Task8ForecastPort(Protocol):
    """Adapter that loads a TASK-008 forecast persisted row by id."""

    async def load_by_id(
        self,
        *,
        session: AsyncSession,
        forecast_run_id: int,
    ) -> Task8Authority | None:
        ...


class Task9HarvestStatePort(Protocol):
    """Adapter that loads a TASK-009 harvest-state persisted run by id."""

    async def load_by_id(
        self,
        *,
        session: AsyncSession,
        harvest_state_run_id: int,
    ) -> Task9Authority | None:
        ...


class Task10PredictionPort(Protocol):
    """Adapter that loads a TASK-010 residual prediction by id."""

    async def load_by_id(
        self,
        *,
        session: AsyncSession,
        prediction_run_id: int,
    ) -> Task10Authority | None:
        ...


class Task11BacktestPort(Protocol):
    """Adapter that loads a TASK-011 rolling-backtest run by id."""

    async def load_by_id(
        self,
        *,
        session: AsyncSession,
        rolling_backtest_run_id: int,
    ) -> Task11Authority | None:
        ...


class Task12PredictionPort(Protocol):
    """Adapter that loads a TASK-012 replay-trained prediction by id.

    Only reachable when an explicit ``TASK12_PREDICTION_RUN`` authority
    override is supplied (§22.1).  The adapter MUST fail closed with
    ``None`` (not a fabricated value) when the row is absent.
    """

    async def load_by_id(
        self,
        *,
        session: AsyncSession,
        prediction_run_id: int,
    ) -> Task12Authority | None:
        ...


# --- §17 simulate_scenario helpers ---------------------------------------

class ScenarioBaselinePort(Protocol):
    """Adapter that produces the deterministic baseline curve + peak."""

    async def compute_baseline(
        self,
        *,
        session: AsyncSession,
        normalized_request: NormalizedAgentRequest,
        resolved_location: ResolvedLocation,
        parameters: list[Any],
        advanced_overrides: AdvancedOverrides | None,
    ) -> tuple[list[ForecastDailyRow], Any]:
        ...


__all__ = [
    "LocationResolverPort",
    "ParameterPriorPort",
    "Task8ForecastPort",
    "Task9HarvestStatePort",
    "Task10PredictionPort",
    "Task11BacktestPort",
    "Task12PredictionPort",
    "ScenarioBaselinePort",
]
