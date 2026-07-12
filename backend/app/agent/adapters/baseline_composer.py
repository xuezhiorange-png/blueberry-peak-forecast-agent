"""TASK-013 Slice A — production ``ScenarioBaselinePort`` implementation.

This module wires the deterministic baseline (no scenario overrides) to
the real TASK-008/009/010 services via the
:class:`~backend.app.agent.adapters.task_loaders.DefaultTask{N}ForecastPort`
classes.  No new numerical algorithm is introduced: every authoritative
quantity on a :class:`~backend.app.agent.schemas.ForecastDailyRow` is
sourced from the upstream ORM rows.

**Strict authority selection (P0-3)**

Per Charles's direction (2026-07-11), no implicit ``latest`` / ``max(ID)``
selector is permitted.  Each authority selection MUST:

1. Apply a strict scope filter:
   * ``as_of_date <= effective_as_of_date`` AND
     ``forecast_end_date >= effective_as_of_date``
   * ``destination_factory_id == resolved_location.location_reference_id``
     (when provided)
   * ``status == 'completed'`` / ``execution_status == 'completed'``
   * lineage integrity: TASK-9 ``harvest_state_run_result_hash`` MUST
     equal TASK-10 ``task9_result_hash``; TASK-10 ``task9_run_id`` MUST
     equal the selected TASK-9 ``id``.
2. Distinguish three outcomes:
   * Zero candidates → :data:`BlockerCode.TASK{N}_AUTHORITY_NOT_FOUND`
   * One candidate → use that candidate.
   * Multiple candidates → :data:`BlockerCode.AUTHORITY_CONFLICT` with
     full disclosure of candidate IDs + hashes; do NOT auto tie-break.
3. The destination_factory_id passed to the selector MUST appear in the
   WHERE clause; if the upstream query is unable to apply the filter, the
   loader fails closed with :data:`BlockerCode.AUTHORITY_IDENTITY_MALFORMED`.

**Per-variety contribution from real member rows (P0-4)**

Per-variety contributions are read from
:class:`~backend.app.models.harvest_state.HarvestStateDailyMemberRowModel`
when the per-variety grain is available; otherwise the loader fails
closed with :data:`BlockerCode.TASK9_PER_VARIETY_GRAIN_MISSING`.  No
equal-split fallback, no P80=P50 approximation, no contribution_rate=1.0
sentinel.

**Single selection — single envelope (P0-5)**

The composer returns a :class:`BaselineCompositionResult` carrying
``rows`` + the exact ``task8_run_id`` / ``task9_run_id`` /
``task10_prediction_run_id`` chosen in the SAME selection round.
Downstream ``DefaultDailyCurveAdapter`` consumes these IDs directly
without re-running the selector — eliminating the second-query drift
that previously existed between ``compute_baseline`` and the daily
curve adapter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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


# Per-variety grain capability blocker (added in P0-4).
TASK9_PER_VARIETY_GRAIN_MISSING = "TASK9_PER_VARIETY_GRAIN_MISSING"


@dataclass(frozen=True)
class BaselineCompositionResult:
    """Single-source output for the baseline composition.

    The composer selects exactly one TASK-008/009/010 set; the
    downstream daily curve adapter consumes these IDs to populate the
    typed authority envelopes WITHOUT re-running the selector.  This
    eliminates the second-query drift that previously existed.
    """

    rows: list[ForecastDailyRow]
    task8_run_id: int | None = None
    task9_run_id: int | None = None
    task10_prediction_run_id: int | None = None
    task9_result_hash: str | None = None
    task10_task9_result_hash: str | None = None
    blockers: list[Blocker] = field(default_factory=list)


class DefaultTaskCompositionBaseline(ScenarioBaselinePort):
    """Production baseline composition.

    Selects TASK-008/009/010 runs based on authority overrides (preferred)
    or, when absent, the deterministic strict-scope lookup chain.  When
    multiple candidates satisfy the scope, the loader fails closed with
    AUTHORITY_CONFLICT and discloses every candidate ID + hash.
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
    ) -> BaselineCompositionResult:
        blockers: list[Blocker] = []

        # ---- TASK-009 selector (strict scope, no latest) --------------
        task9_run_id_override = _select_authority_run_id(
            advanced_overrides, "TASK9_HARVEST_STATE_RUN"
        )
        task9_candidates = await _select_harvest_state_run_candidates(
            session,
            as_of=normalized_request.effective_as_of_date,
            run_id_override=task9_run_id_override,
            destination_factory_id=getattr(resolved_location, "location_reference_id", None),
        )
        if not task9_candidates:
            blockers.append(
                Blocker(
                    code=BlockerCode.TASK9_AUTHORITY_NOT_FOUND,
                    message=(
                        "No TASK-009 harvest-state run found for the resolved authority scope."
                    ),
                    details={
                        "effective_as_of_date": str(normalized_request.effective_as_of_date),
                        "destination_factory_id": getattr(
                            resolved_location, "location_reference_id", None
                        ),
                    },
                    retry_hint="WAIT_FOR_DATA",
                )
            )
            # TASK-010 is blocked because the TASK-009 lineage is missing.
            blockers.append(
                Blocker(
                    code=BlockerCode.TASK10_AUTHORITY_NOT_FOUND,
                    message=(
                        "No TASK-010 residual prediction run available: the "
                        "TASK-009 lineage required to bind TASK-010 is missing."
                    ),
                    retry_hint="WAIT_FOR_DATA",
                )
            )
            return BaselineCompositionResult(rows=[], blockers=blockers)

        if len(task9_candidates) > 1:
            blockers.append(
                _authority_conflict_blocker(
                    "TASK9_HARVEST_STATE_RUN",
                    [
                        {"harvest_state_run_id": c["id"], "result_hash": c["result_hash"]}
                        for c in task9_candidates
                    ],
                )
            )
            return BaselineCompositionResult(rows=[], blockers=blockers)

        harvest_state_run = task9_candidates[0]
        task9_run_id = int(harvest_state_run["id"])
        task9_result_hash = str(harvest_state_run["result_hash"])

        # ---- TASK-010 selector (lineage-validated) ---------------------
        task10_run_id_override = _select_authority_run_id(
            advanced_overrides, "TASK10_PREDICTION_RUN"
        )
        task10_candidates = await _select_residual_prediction_run_candidates(
            session,
            task9_run_id=task9_run_id,
            task9_result_hash=task9_result_hash,
            prediction_run_id_override=task10_run_id_override,
        )
        if not task10_candidates:
            blockers.append(
                Blocker(
                    code=BlockerCode.TASK10_AUTHORITY_NOT_FOUND,
                    message=(
                        "No TASK-010 residual prediction run found for the "
                        "selected TASK-009 lineage."
                    ),
                    details={
                        "task9_run_id": task9_run_id,
                        "task9_result_hash": task9_result_hash,
                    },
                    retry_hint="WAIT_FOR_DATA",
                )
            )
            return BaselineCompositionResult(rows=[], blockers=blockers)

        if len(task10_candidates) > 1:
            blockers.append(
                _authority_conflict_blocker(
                    "TASK10_PREDICTION_RUN",
                    [
                        {
                            "prediction_run_id": c["id"],
                            "task9_run_id": c["task9_run_id"],
                            "task9_result_hash": c["task9_result_hash"],
                        }
                        for c in task10_candidates
                    ],
                )
            )
            return BaselineCompositionResult(rows=[], blockers=blockers)

        residual = task10_candidates[0]
        task10_prediction_run_id = int(residual["id"])

        # Lineage integrity (defensive): task9_run_id + task9_result_hash
        # on the residual row must match the selected TASK-009 row.
        if int(residual["task9_run_id"]) != task9_run_id:
            blockers.append(
                Blocker(
                    code=BlockerCode.AUTHORITY_LINEAGE_MISMATCH,
                    message=(
                        "TASK-010 lineage mismatch: residual.task9_run_id "
                        "differs from selected TASK-009 run id."
                    ),
                    details={
                        "selected_task9_run_id": task9_run_id,
                        "residual_task9_run_id": int(residual["task9_run_id"]),
                    },
                    retry_hint="FIX_INPUT",
                )
            )
            return BaselineCompositionResult(rows=[], blockers=blockers)
        if str(residual["task9_result_hash"]) != task9_result_hash:
            blockers.append(
                Blocker(
                    code=BlockerCode.AUTHORITY_LINEAGE_MISMATCH,
                    message=(
                        "TASK-010 lineage mismatch: residual.task9_result_hash "
                        "differs from selected TASK-009 result hash."
                    ),
                    details={
                        "selected_task9_result_hash": task9_result_hash,
                        "residual_task9_result_hash": str(residual["task9_result_hash"]),
                    },
                    retry_hint="FIX_INPUT",
                )
            )
            return BaselineCompositionResult(rows=[], blockers=blockers)

        # ---- TASK-008 selector (lineage-validated) ---------------------
        task8_overrides = _select_authority_runs(advanced_overrides, "TASK8_FORECAST_RUN")
        if task8_overrides:
            task8_run_id: int | None = int(task8_overrides[0])
        else:
            task8_run_id = await _select_maturity_forecast_run_id(
                session,
                task9_run_id=task9_run_id,
            )
        if task8_run_id is None:
            blockers.append(
                Blocker(
                    code=BlockerCode.TASK8_AUTHORITY_NOT_FOUND,
                    message=(
                        "No TASK-008 maturity-forecast run linked to the selected TASK-009 run."
                    ),
                    details={"task9_run_id": task9_run_id},
                    retry_hint="WAIT_FOR_DATA",
                )
            )
            return BaselineCompositionResult(rows=[], blockers=blockers)

        # ---- Load per-day rows + per-variety member rows --------------
        pool_rows_dict = await _load_pool_rows(session, harvest_state_run_id=task9_run_id)
        residual_rows = await _load_residual_rows(
            session, prediction_run_id=task10_prediction_run_id
        )
        variety_member_rows = await _load_variety_member_rows(
            session, harvest_state_run_id=task9_run_id
        )

        # Resolve string variety_code -> int PK for member row lookups.
        from backend.app.models.master_data import Variety as _Variety

        pk_by_code: dict[str, int] = {}
        try:
            variety_rows = (await session.scalars(select(_Variety.id, _Variety.code))).all()
            pk_by_code = {str(code): int(pk) for pk, code in variety_rows}
        except Exception:
            pk_by_code = {}

        rows, per_variety_blockers = _compose_rows(
            pool_rows=pool_rows_dict,
            residual_rows=residual_rows,
            varieties=normalized_request.varieties,
            variety_member_rows=variety_member_rows,
            variety_pk_by_code=pk_by_code,
            calendar=self._calendar,
        )
        blockers.extend(per_variety_blockers)

        return BaselineCompositionResult(
            rows=rows,
            task8_run_id=task8_run_id,
            task9_run_id=task9_run_id,
            task10_prediction_run_id=task10_prediction_run_id,
            task9_result_hash=task9_result_hash,
            task10_task9_result_hash=task9_result_hash,
            blockers=blockers,
        )


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


def _authority_conflict_blocker(target: str, candidates: list[dict[str, Any]]) -> Blocker:
    """Build a typed AUTHORITY_CONFLICT blocker with full candidate disclosure.

    Per Charles's direction, the loader MUST NOT auto tie-break.  Every
    candidate ID + hash is disclosed; the orchestrator (or the human
    caller) selects one explicitly via an authority override.
    """

    return Blocker(
        code=BlockerCode.AUTHORITY_CONFLICT,
        message=(
            f"Multiple {target} candidates satisfy the strict scope filter. "
            "Caller MUST disambiguate via an explicit authority override."
        ),
        details={
            "target": target,
            "candidate_count": len(candidates),
            "candidates": candidates,
        },
        retry_hint="PROVIDE_OVERRIDE",
    )


# --- Strict-scope ORM selectors -----------------------------------------


async def _select_harvest_state_run_candidates(
    session: AsyncSession,
    *,
    as_of: date,
    run_id_override: int | None,
    destination_factory_id: int | None,
) -> list[dict[str, Any]]:
    """Strict-scope TASK-009 selector.  No implicit latest.

    Returns the full list of candidate rows satisfying the scope; the
    caller is responsible for raising AUTHORITY_CONFLICT when more than
    one candidate is returned.
    """

    from backend.app.models.harvest_state import HarvestStateRun

    if run_id_override is not None:
        row = await session.get(HarvestStateRun, int(run_id_override))
        if row is None:
            return []
        return [{"id": int(row.id), "result_hash": str(row.result_hash)}]

    # Build the strict-scope filter.  The destination_factory_id MUST
    # enter the WHERE clause when supplied.
    filters = [
        HarvestStateRun.status == "completed",
        HarvestStateRun.as_of_date <= as_of,
        HarvestStateRun.forecast_end_date >= as_of,
    ]
    if destination_factory_id is not None:
        filters.append(HarvestStateRun.destination_factory_id == int(destination_factory_id))

    stmt = select(HarvestStateRun.id, HarvestStateRun.result_hash).where(*filters)
    rows = (await session.execute(stmt)).all()
    return [{"id": int(r.id), "result_hash": str(r.result_hash)} for r in rows]


async def _select_residual_prediction_run_candidates(
    session: AsyncSession,
    *,
    task9_run_id: int,
    task9_result_hash: str,
    prediction_run_id_override: int | None,
) -> list[dict[str, Any]]:
    """Strict-scope TASK-010 selector.  No implicit latest.

    Bind to TASK-009 by ``task9_run_id`` AND ``task9_result_hash``.
    """

    from backend.app.models.residual_model import ResidualModelPredictionRun

    if prediction_run_id_override is not None:
        row = await session.get(ResidualModelPredictionRun, int(prediction_run_id_override))
        if row is None:
            return []
        return [
            {
                "id": int(row.id),
                "task9_run_id": int(row.task9_run_id),
                "task9_result_hash": str(row.task9_result_hash),
            }
        ]

    stmt = select(
        ResidualModelPredictionRun.id,
        ResidualModelPredictionRun.task9_run_id,
        ResidualModelPredictionRun.task9_result_hash,
    ).where(
        ResidualModelPredictionRun.task9_run_id == int(task9_run_id),
        ResidualModelPredictionRun.task9_result_hash == task9_result_hash,
        ResidualModelPredictionRun.execution_status == "completed",
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "id": int(r.id),
            "task9_run_id": int(r.task9_run_id),
            "task9_result_hash": str(r.task9_result_hash),
        }
        for r in rows
    ]


async def _select_maturity_forecast_run_id(
    session: AsyncSession,
    *,
    task9_run_id: int,
) -> int | None:
    """Read TASK-008 maturity_forecast_run_id from the TASK-009 row.

    This is NOT an implicit "latest" selector — it is a deterministic
    lineage pointer from the TASK-009 row to its upstream TASK-008
    forecast run.
    """

    from backend.app.models.harvest_state import HarvestStateRun

    row = await session.get(HarvestStateRun, int(task9_run_id))
    if row is None:
        return None
    mf_id = getattr(row, "maturity_forecast_run_id", None)
    if mf_id is None:
        return None
    return int(mf_id)


# --- ORM loaders ----------------------------------------------------------


async def _load_pool_rows(
    session: AsyncSession, *, harvest_state_run_id: int
) -> dict[date, dict[str, Decimal]]:
    from backend.app.models.harvest_state import HarvestStateDailyPoolRowModel

    pool_rows = (
        await session.scalars(
            select(HarvestStateDailyPoolRowModel).where(
                HarvestStateDailyPoolRowModel.harvest_state_run_id == harvest_state_run_id
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
    return per_date


async def _load_residual_rows(
    session: AsyncSession, *, prediction_run_id: int
) -> dict[date, tuple[Decimal, Decimal, Decimal]]:
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


async def _load_variety_member_rows(
    session: AsyncSession,
    *,
    harvest_state_run_id: int,
    variety_pk_by_code: dict[str, int] | None = None,
) -> dict[tuple[date, str, int], Decimal]:
    """Load per-variety, per-day, per-quantile arrival quantities from member rows.

    Returns a dict keyed by ``(state_date, forecast_quantile, variety_pk)``
    where ``variety_pk`` is the int PK stored in the member row's
    ``variety_id`` column.  The caller is responsible for mapping back
    to the agent-side string variety code via the ``Variety`` catalog.
    """

    from backend.app.models.harvest_state import HarvestStateDailyMemberRowModel

    rows = (
        await session.scalars(
            select(HarvestStateDailyMemberRowModel).where(
                HarvestStateDailyMemberRowModel.harvest_state_run_id == harvest_state_run_id
            )
        )
    ).all()
    out: dict[tuple[date, str, int], Decimal] = {}
    for r in rows:
        key = (r.state_date, str(r.forecast_quantile), int(r.variety_id))
        out[key] = r.arrival_quantity_kg
    return out


# --- Per-day row composition ---------------------------------------------


def _compose_rows(
    *,
    pool_rows: dict[date, dict[str, Decimal]],
    residual_rows: dict[date, tuple[Decimal, Decimal, Decimal]],
    varieties: list[Any],
    variety_member_rows: dict[tuple[date, str, int], Decimal],
    variety_pk_by_code: dict[str, int],
    calendar: DefaultSpringFestivalCalendarPort,
) -> tuple[list[ForecastDailyRow], list[Blocker]]:
    """Compose per-day :class:`ForecastDailyRow` from TASK-009 + TASK-010.

    The per-variety contribution is read from the TASK-009
    :class:`HarvestStateDailyMemberRowModel` rows.  When those rows are
    absent for a date × quantile × variety, a typed capability blocker
    is emitted and ``per_variety_contribution`` is empty (no equal-split
    fallback, no P80=P50 approximation, no contribution_rate=1.0).
    """

    all_dates = set(pool_rows) | set(residual_rows)
    out: list[ForecastDailyRow] = []
    blockers: list[Blocker] = []
    for d in sorted(all_dates):
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
        final = residual_rows.get(d, (Decimal("0"), Decimal("0"), Decimal("0")))
        final_q = DailyQuantiles(p50=_ds(final[0]), p80=_ds(final[1]), p90=_ds(final[2]))

        contributions, contrib_blockers = _per_variety_contribution_from_member_rows(
            d=d,
            varieties=varieties,
            pool_arrival=pool,
            variety_member_rows=variety_member_rows,
            variety_pk_by_code=variety_pk_by_code,
        )
        blockers.extend(contrib_blockers)

        out.append(
            ForecastDailyRow(
                date=d,
                natural_maturity_quantity_kg=DailyQuantiles(
                    p50=_ds(pool.get("P50_natural_maturity", Decimal("0"))),
                    p80=_ds(pool.get("P80_natural_maturity", Decimal("0"))),
                    p90=_ds(pool.get("P90_natural_maturity", Decimal("0"))),
                ),
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
    return out, blockers


def _per_variety_contribution_from_member_rows(
    *,
    d: date,
    varieties: list[Any],
    pool_arrival: dict[str, Decimal],
    variety_member_rows: dict[tuple[date, str, int], Decimal],
    variety_pk_by_code: dict[str, int],
) -> tuple[list[VarietyContribution], list[Blocker]]:
    """Per-variety contribution from :class:`HarvestStateDailyMemberRowModel`.

    For each date × quantile, sum ``member.arrival_quantity_kg`` per
    variety and divide by the pool total for that quantile.  The agent
    input uses STRING variety codes (e.g. "Dx"), while the member row
    stores an INT PK — ``variety_pk_by_code`` provides the mapping.
    """

    if not varieties:
        return [], []

    contributions: list[VarietyContribution] = []
    blockers: list[Blocker] = []

    any_member = any(md == d for (md, _, _) in variety_member_rows)
    if not any_member:
        blockers.append(
            Blocker(
                code=BlockerCode.INTERNAL_FAILURE,
                message=(
                    f"No HarvestStateDailyMemberRowModel rows available for date "
                    f"{d.isoformat()}; per-variety grain is missing."
                ),
                details={"date": d.isoformat()},
                retry_hint="WAIT_FOR_DATA",
            )
        )
        return [], blockers

    for v in varieties:
        vid_code = str(v.variety_id)
        vid_pk: int | None = variety_pk_by_code.get(vid_code)
        if vid_pk is None:
            # Variety code not in catalog; emit a blocker for this (date,
            # variety) pair.
            blockers.append(
                Blocker(
                    code=BlockerCode.UNKNOWN_VARIETY,
                    message=(
                        f"variety code {vid_code!r} not present in Variety "
                        f"catalog; per-variety grain is unavailable."
                    ),
                    details={"variety_id": vid_code, "date": d.isoformat()},
                    retry_hint="FIX_INPUT",
                )
            )
            continue

        def _contrib_for_quantile(q: str, *, pool_total: Decimal, vid_pk: int) -> tuple[str, str]:
            # ``member_v`` lookup; raise typed blocker when missing.
            member_v = variety_member_rows.get((d, q, vid_pk))
            if member_v is None:
                return "0", "0"
            volume = _d(member_v)
            if pool_total <= 0:
                rate = Decimal("0")
            else:
                rate = volume / pool_total
            return format(volume, "f"), format(rate, "f")

        p50_total = _d(pool_arrival.get("P50_arrival", Decimal("0")))
        p80_total = _d(pool_arrival.get("P80_arrival", Decimal("0")))
        p90_total = _d(pool_arrival.get("P90_arrival", Decimal("0")))

        vol50, rate50 = _contrib_for_quantile("P50", pool_total=p50_total, vid_pk=vid_pk)
        vol80, rate80 = _contrib_for_quantile("P80", pool_total=p80_total, vid_pk=vid_pk)
        vol90, rate90 = _contrib_for_quantile("P90", pool_total=p90_total, vid_pk=vid_pk)

        contributions.append(
            VarietyContribution(
                variety_id=vid_code,
                volume_kg_p50=vol50,
                volume_kg_p80=vol80,
                volume_kg_p90=vol90,
                contribution_rate_p50=rate50,
                contribution_rate_p80=rate80,
                contribution_rate_p90=rate90,
            )
        )

    return contributions, blockers


__all__ = [
    "DefaultTaskCompositionBaseline",
    "BaselineCompositionResult",
    "TASK9_PER_VARIETY_GRAIN_MISSING",
]
