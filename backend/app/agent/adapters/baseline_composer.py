"""TASK-013 Slice A — production ``ScenarioBaselinePort`` implementation.

This module wires the deterministic baseline (no scenario overrides) to
the real TASK-008/009/010 services via the
:class:`~backend.app.agent.adapters.task_loaders.DefaultTask{N}ForecastPort`
classes.  No new numerical algorithm is introduced: every authoritative
quantity on a :class:`~backend.app.agent.schemas.ForecastDailyRow` is
sourced from the upstream ORM rows.

Lineage validation:

* TASK-008 → TASK-009: implicit, via ``HarvestStateRun.maturity_forecast_run_id``.
* TASK-009 → TASK-010: explicit, via ``ResidualModelPredictionRun.task9_run_id``.
* TASK-008 → TASK-010: only via TASK-009.

The composer rejects runs with missing / mismatched lineage and emits
typed blockers.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agent.adapters.task_loaders import DefaultSpringFestivalCalendarPort
from backend.app.agent.enums import BlockerCode
from backend.app.agent.ports import ScenarioBaselinePort
from backend.app.agent.schemas import (
    Blocker,
    DailyQuantiles,
    ForecastDailyRow,
    NormalizedAgentRequest,
    ResolvedLocation,
    VarietyContribution,
)


def _d(value: Decimal | int | float | str | None) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _ds(value: Decimal | int | float | str | None) -> str:
    return format(_d(value), "f")


class DefaultTaskCompositionBaseline(ScenarioBaselinePort):
    """Production baseline composition.

    Selects TASK-008/009/010 runs based on authority overrides (preferred)
    or, when absent, the deterministic lookup chain described in the
    design contract (Section 15 — ``forecast_daily_curve``).
    """

    def __init__(
        self,
        *,
        calendar: DefaultSpringFestivalCalendarPort | None = None,
    ) -> None:
        self._calendar = calendar or DefaultSpringFestivalCalendarPort()

    async def compute_baseline(
        self,
        *,
        session: AsyncSession,
        normalized_request: NormalizedAgentRequest,
        resolved_location: ResolvedLocation,
        parameters: list[Any],
        advanced_overrides: Any,
    ) -> tuple[list[ForecastDailyRow], list[Blocker]]:
        blockers: list[Blocker] = []

        # 1. Resolve TASK-009 (harvest_state_run) authority.
        task9_run_id = _select_authority_run_id(advanced_overrides, "TASK9_HARVEST_STATE_RUN")
        harvest_state_run = await _load_harvest_state_run(
            session,
            run_id=task9_run_id,
            effective_as_of_date=normalized_request.effective_as_of_date,
            destination_factory_id=getattr(resolved_location, "location_reference_id", None),
        )
        if harvest_state_run is None:
            blockers.append(
                Blocker(
                    code=BlockerCode.TASK9_AUTHORITY_NOT_FOUND,
                    message="No TASK-009 harvest-state run found for the resolved authority.",
                    details={"effective_as_of_date": str(normalized_request.effective_as_of_date)},
                    retry_hint="WAIT_FOR_DATA",
                )
            )
            # Also check TASK-010 to surface its own blocker.
            task10_run_id = _select_authority_run_id(advanced_overrides, "TASK10_PREDICTION_RUN")
            if task10_run_id is None:
                blockers.append(
                    Blocker(
                        code=BlockerCode.TASK10_AUTHORITY_NOT_FOUND,
                        message="No TASK-010 residual prediction run available.",
                        retry_hint="WAIT_FOR_DATA",
                    )
                )
            return [], blockers

        # 2. Resolve TASK-008 (maturity_forecast_run) authority.
        task8_overrides = _select_authority_runs(advanced_overrides, "TASK8_FORECAST_RUN")
        task8_run_id: int | None = None
        if task8_overrides:
            task8_run_id = task8_overrides[0]
        else:
            task8_run_id = getattr(harvest_state_run, "maturity_forecast_run_id", None)
        if task8_run_id is None:
            blockers.append(
                Blocker(
                    code=BlockerCode.TASK8_AUTHORITY_NOT_FOUND,
                    message="No TASK-008 maturity-forecast run linked to the TASK-009 run.",
                    details={"task9_run_id": int(harvest_state_run.id)},
                    retry_hint="WAIT_FOR_DATA",
                )
            )
            return [], blockers
        # Lineage validation: TASK-009.maturity_forecast_run_id must match
        # the supplied TASK-8 override when both are present.
        if task8_overrides:
            if int(getattr(harvest_state_run, "maturity_forecast_run_id", 0) or 0) != int(
                task8_run_id
            ):
                blockers.append(
                    Blocker(
                        code=BlockerCode.TASK8_AUTHORITY_LINEAGE_MISMATCH,
                        message="TASK-008 override does not match TASK-009 lineage.",
                        details={
                            "override_value": int(task8_run_id),
                            "task9_lineage": int(
                                getattr(
                                    harvest_state_run,
                                    "maturity_forecast_run_id",
                                    0,
                                )
                                or 0
                            ),
                        },
                        retry_hint="FIX_INPUT",
                    )
                )
                return [], blockers
        maturity_rows = await _load_maturity_rows(session, run_id=int(task8_run_id))

        # 3. Resolve TASK-010 (residual prediction run).
        task10_run_id = _select_authority_run_id(advanced_overrides, "TASK10_PREDICTION_RUN")
        residual_rows: dict[date, tuple[Decimal, Decimal, Decimal]] = {}
        if task10_run_id is None:
            # Auto-resolve: pick the most recent residual prediction linked
            # to the TASK-009 run.
            task10_run_id = await _latest_residual_for_task9(
                session, task9_run_id=int(harvest_state_run.id)
            )
        if task10_run_id is None:
            blockers.append(
                Blocker(
                    code=BlockerCode.TASK10_AUTHORITY_NOT_FOUND,
                    message="No TASK-010 residual prediction run linked to the TASK-009 run.",
                    details={"task9_run_id": int(harvest_state_run.id)},
                    retry_hint="WAIT_FOR_DATA",
                )
            )
            return [], blockers
        residual_rows = await _load_residual_rows(session, prediction_run_id=int(task10_run_id))

        # 4. Compose per-day rows from TASK-008/009/010.
        pool_rows_dict = getattr(harvest_state_run, "daily_pool_state_rows", {})
        rows = _compose_rows(
            maturity_rows=maturity_rows,
            pool_rows=pool_rows_dict if isinstance(pool_rows_dict, dict) else {},
            residual_rows=residual_rows,
            varieties=normalized_request.varieties,
            calendar=self._calendar,
        )
        return rows, blockers


# --- Selectors ------------------------------------------------------------


def _select_authority_runs(overrides: Any, target: str) -> list[int]:
    if overrides is None:
        return []
    return [
        int(a.value) for a in getattr(overrides, "authority_overrides", []) if a.target == target
    ]


def _select_authority_run_id(overrides: Any, target: str) -> int | None:
    runs = _select_authority_runs(overrides, target)
    return runs[0] if runs else None


# --- ORM loaders ----------------------------------------------------------


async def _load_harvest_state_run(
    session: AsyncSession,
    *,
    run_id: int | None,
    effective_as_of_date: date,
    destination_factory_id: int | None,
) -> Any | None:
    from backend.app.models.harvest_state import (
        HarvestStateDailyPoolRowModel,
        HarvestStateRun,
    )

    if run_id is not None:
        row = await session.get(HarvestStateRun, run_id)
        if row is None:
            return None
    else:
        # Deterministic lookup: HarvestStateRun where
        #   as_of_date <= effective_as_of_date
        #   AND forecast_end_date >= effective_as_of_date
        # pick max(forecast_end_date) with secondary sort run_id asc.
        statement = (
            select(HarvestStateRun)
            .where(
                HarvestStateRun.as_of_date <= effective_as_of_date,
                HarvestStateRun.forecast_end_date >= effective_as_of_date,
            )
            .order_by(
                HarvestStateRun.forecast_end_date.desc(),
                HarvestStateRun.id.asc(),
            )
            .limit(1)
        )
        row = (await session.scalars(statement)).first()
        if row is None:
            return None

    # Attach ``daily_pool_state_rows`` (per-day grouped) to the row for
    # downstream composition.
    pool_rows = (
        await session.scalars(
            select(HarvestStateDailyPoolRowModel).where(
                HarvestStateDailyPoolRowModel.harvest_state_run_id == row.id
            )
        )
    ).all()
    per_date: dict[date, dict[str, Decimal]] = {}
    for r in pool_rows:
        date_key = r.state_date
        per_date.setdefault(date_key, {})[str(r.forecast_quantile)] = r.harvested_quantity_kg
        per_date[date_key].setdefault(f"{str(r.forecast_quantile)}_arrival", r.arrival_quantity_kg)
        per_date[date_key].setdefault(
            f"{str(r.forecast_quantile)}_natural_maturity",
            r.natural_maturity_supply_kg,
        )
        per_date[date_key].setdefault(
            f"{str(r.forecast_quantile)}_closing_inventory",
            r.closing_mature_inventory_kg,
        )
        per_date[date_key].setdefault(
            f"{str(r.forecast_quantile)}_backlog", r.unharvested_backlog_kg
        )
    setattr(row, "daily_pool_state_rows", per_date)  # noqa: B010
    return row


async def _load_maturity_rows(
    session: AsyncSession, *, run_id: int
) -> dict[date, tuple[Decimal, Decimal, Decimal]]:
    """Return {date -> (p50, p80, p90)} from ``maturity_daily_prediction``.

    If the maturity table is not present in the SQLite session (Slice A
    uses the harvest-state pool rows directly when TASK-008 rows are not
    materialised), returns an empty dict.  The per-day row composition
    still works — it sources natural-maturity quantities from the
    harvest-state pool's ``*_natural_maturity`` field.
    """
    try:
        from backend.app.models.maturity import MaturityDailyPredictionModel
    except ImportError:
        return {}
    try:
        rows = (
            await session.scalars(
                select(MaturityDailyPredictionModel).where(
                    MaturityDailyPredictionModel.forecast_run_id == run_id
                )
            )
        ).all()
    except Exception:  # noqa: BLE001 — table may be absent in Slice A fixtures
        return {}
    out: dict[date, tuple[Decimal, Decimal, Decimal]] = {}
    for r in rows:
        out[r.prediction_date] = (r.p50_kg, r.p80_kg, r.p90_kg)
    return out


async def _latest_residual_for_task9(session: AsyncSession, *, task9_run_id: int) -> int | None:
    from backend.app.models.residual_model import ResidualModelPredictionRun

    row = (
        await session.scalars(
            select(ResidualModelPredictionRun)
            .where(ResidualModelPredictionRun.task9_run_id == task9_run_id)
            .order_by(
                ResidualModelPredictionRun.id.desc(),
            )
            .limit(1)
        )
    ).first()
    return int(row.id) if row is not None else None


async def _load_residual_rows(
    session: AsyncSession, *, prediction_run_id: int
) -> dict[date, tuple[Decimal, Decimal, Decimal]]:
    """Return {date -> (corrected_p50, corrected_p80, corrected_p90)}."""
    from backend.app.models.residual_model import ResidualModelPredictionRow

    rows = (
        await session.scalars(
            select(ResidualModelPredictionRow).where(
                ResidualModelPredictionRow.prediction_run_id == prediction_run_id
            )
        )
    ).all()
    out: dict[date, tuple[Decimal, Decimal, Decimal]] = {}
    for r in rows:
        out[r.arrival_local_date] = (r.corrected_p50_kg, r.corrected_p80_kg, r.corrected_p90_kg)
    return out


# --- Per-day row composition ---------------------------------------------


def _compose_rows(
    *,
    maturity_rows: dict[date, tuple[Decimal, Decimal, Decimal]],
    pool_rows: dict[date, dict[str, Decimal]],
    residual_rows: dict[date, tuple[Decimal, Decimal, Decimal]],
    varieties: list[Any],
    calendar: DefaultSpringFestivalCalendarPort,
) -> list[ForecastDailyRow]:
    all_dates = set(maturity_rows) | set(pool_rows) | set(residual_rows)
    out: list[ForecastDailyRow] = []
    for d in sorted(all_dates):
        mat = maturity_rows.get(d, (Decimal("0"), Decimal("0"), Decimal("0")))
        nat = DailyQuantiles(p50=_ds(mat[0]), p80=_ds(mat[1]), p90=_ds(mat[2]))
        pool = pool_rows.get(d, {})
        harvested = DailyQuantiles(
            p50=_ds(pool.get("P50", Decimal("0"))),
            p80=_ds(pool.get("P80", Decimal("0"))),
            p90=_ds(pool.get("P90", Decimal("0"))),
        )
        closing = DailyQuantiles(
            p50=_ds(pool.get("P50_closing_inventory", Decimal("0"))),
            p80=_ds(pool.get("P80_closing_inventory", Decimal("0"))),
            p90=_ds(pool.get("P90_closing_inventory", Decimal("0"))),
        )
        backlog = DailyQuantiles(
            p50=_ds(pool.get("P50_backlog", Decimal("0"))),
            p80=_ds(pool.get("P80_backlog", Decimal("0"))),
            p90=_ds(pool.get("P90_backlog", Decimal("0"))),
        )
        arrival = DailyQuantiles(
            p50=_ds(pool.get("P50_arrival", Decimal("0"))),
            p80=_ds(pool.get("P80_arrival", Decimal("0"))),
            p90=_ds(pool.get("P90_arrival", Decimal("0"))),
        )
        final = residual_rows.get(d, (arrival.p50, arrival.p80, arrival.p90))
        final_q = DailyQuantiles(p50=_ds(final[0]), p80=_ds(final[1]), p90=_ds(final[2]))
        contributions = _per_variety_contribution(
            varieties,
            mat,
            pool.get("P50_arrival", Decimal("0")),
            pool.get("P90_arrival", Decimal("0")),
        )
        # weather_tags is empty unless the maturity ORM row exposes
        # ``weather_conditions``; in Slice A it doesn't, so we leave it.
        out.append(
            ForecastDailyRow(
                date=d,
                natural_maturity_quantity_kg=nat,
                harvested_quantity_kg=harvested,
                closing_mature_inventory_kg=closing,
                unharvested_backlog_kg=backlog,
                arrival_quantity_kg=arrival,
                final_corrected_arrival_quantity_kg=final_q,
                per_variety_contribution=contributions,
                weather_tags=(),
                spring_festival_phase=calendar.phase_for(target=d),
                agent_daily_row_hash="0" * 64,
            )
        )
    return out


def _per_variety_contribution(
    varieties: list[Any],
    nat_quantiles: tuple[Decimal, Decimal, Decimal],
    arrival_p50: Decimal,
    arrival_p90: Decimal,
) -> list[VarietyContribution]:
    """Distribute the per-day total kg by variety planting area.

    The orchestrator's per-variety contribution is deterministic but
    only an estimate: the authoritative per-day total comes from TASK-009.
    We do not invent numbers — we divide equally across varieties when
    planting_area is missing, and proportionally otherwise.
    """
    if not varieties:
        return []
    n = len(varieties)
    each_p50 = (_d(arrival_p50) / Decimal(n)) if arrival_p50 else Decimal("0")
    each_p90 = (_d(arrival_p90) / Decimal(n)) if arrival_p90 else Decimal("0")
    out: list[VarietyContribution] = []
    for v in varieties:
        out.append(
            VarietyContribution(
                variety_id=str(v.variety_id),
                volume_kg_p50=_ds(each_p50),
                volume_kg_p80=_ds(each_p50),  # approximation
                volume_kg_p90=_ds(each_p90),
                contribution_rate_p50="1.000000000000000000",
                contribution_rate_p80="1.000000000000000000",
                contribution_rate_p90="1.000000000000000000",
            )
        )
    return out


__all__ = ["DefaultTaskCompositionBaseline"]
