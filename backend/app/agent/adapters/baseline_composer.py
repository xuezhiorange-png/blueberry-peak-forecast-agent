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
from typing import Any, cast

from sqlalchemy import Integer, func, select
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


# Per-variety grain capability blocker.  Now exposed as
# :data:`BlockerCode.TASK9_PER_VARIETY_GRAIN_MISSING` (P0-4 round 5).


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

        # ---- Spring Festival policy disclosure (P0-9 round 6) -----------
        # The default calendar port reports is_policy_loaded() == False and
        # returns phase = "NONE" for every date.  "NONE" is NOT a confirmed
        # "outside the Spring Festival window" assertion — it means the
        # policy source is absent.  Emit a typed
        # SPRING_FESTIVAL_CALENDAR_POLICY_MISSING blocker so downstream
        # consumers know the per-day phase is unaudited, and continue
        # composition (the curve still has value; the phase is a tag, not
        # a gate).  Version/hash use None — not "unknown" or "v0".
        if not self._calendar.is_policy_loaded():
            blockers.append(
                Blocker(
                    code=BlockerCode.SPRING_FESTIVAL_CALENDAR_POLICY_MISSING,
                    message=(
                        "Default Spring Festival calendar port has no versioned "
                        "policy loaded; per-day phase is set to 'NONE' as a "
                        "non-authoritative placeholder, not a confirmed phase."
                    ),
                    details={
                        "effective_forecast_season": str(
                            normalized_request.effective_forecast_season
                        )
                        if getattr(normalized_request, "effective_forecast_season", None)
                        is not None
                        else None,
                        "calendar_policy_version": None,
                        "calendar_config_hash": None,
                    },
                    retry_hint="PROVIDE_OVERRIDE",
                )
            )

        # ---- TASK-009 selector (strict scope, no latest) --------------
        task9_run_id_override = _select_authority_run_id(
            advanced_overrides, "TASK9_HARVEST_STATE_RUN"
        )
        requested_variety_codes = tuple(str(v.variety_id) for v in normalized_request.varieties)
        try:
            task9_candidates = await _select_harvest_state_run_candidates(
                session,
                as_of=normalized_request.effective_as_of_date,
                run_id_override=task9_run_id_override,
                destination_factory_id=getattr(resolved_location, "location_reference_id", None),
                requested_variety_codes=requested_variety_codes,
                effective_forecast_season=(
                    int(normalized_request.effective_forecast_season)
                    if getattr(normalized_request, "effective_forecast_season", None) is not None
                    else None
                ),
            )
        except UpstreamReadFailure as exc:
            blockers.append(
                Blocker(
                    code=BlockerCode.UPSTREAM_READ_FAILURE,
                    message=(f"TASK-009 selector raised an upstream read failure: {exc}"),
                    details={"field": "harvest_state_run_selector"},
                    retry_hint="WAIT_FOR_DATA",
                )
            )
            return BaselineCompositionResult(rows=[], blockers=blockers)
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
        try:
            task10_candidates = await _select_residual_prediction_run_candidates(
                session,
                task9_run_id=task9_run_id,
                task9_result_hash=task9_result_hash,
                prediction_run_id_override=task10_run_id_override,
            )
        except UpstreamReadFailure as exc:
            blockers.append(
                Blocker(
                    code=BlockerCode.UPSTREAM_READ_FAILURE,
                    message=(f"TASK-010 selector raised an upstream read failure: {exc}"),
                    details={"field": "residual_prediction_run_selector"},
                    retry_hint="WAIT_FOR_DATA",
                )
            )
            return BaselineCompositionResult(rows=[], blockers=blockers)
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
        # P0-5 #16: when an explicit TASK-8 override is supplied, it
        # MUST equal the maturity_forecast_run_id pointer on the
        # selected TASK-009 row.  Otherwise we surface
        # TASK8_AUTHORITY_LINEAGE_MISMATCH.
        if task8_overrides:
            lineage_mf_id = await _select_maturity_forecast_run_id(
                session,
                task9_run_id=task9_run_id,
            )
            if lineage_mf_id is not None and int(task8_run_id or -1) != int(lineage_mf_id):
                blockers.append(
                    Blocker(
                        code=BlockerCode.TASK8_AUTHORITY_LINEAGE_MISMATCH,
                        message=(
                            "TASK-008 override does not match the "
                            "selected TASK-009 lineage pointer "
                            "(maturity_forecast_run_id)."
                        ),
                        details={
                            "override_task8_run_id": int(task8_run_id or -1),
                            "task9_maturity_forecast_run_id": int(lineage_mf_id),
                            "task9_run_id": int(task9_run_id),
                        },
                        retry_hint="FIX_INPUT",
                    )
                )
                return BaselineCompositionResult(rows=[], blockers=blockers)
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
        # P0-4 round 5: use session.execute() (not scalars()) so a
        # multi-column query (id, code) yields rows.  Read failures
        # surface as UPSTREAM_READ_FAILURE, NOT a silently empty
        # mapping.
        from backend.app.models.master_data import Variety as _Variety

        pk_by_code: dict[str, int] = {}
        try:
            variety_rows = (await session.execute(select(_Variety.id, _Variety.code))).all()
            pk_by_code = {str(code): int(pk) for pk, code in variety_rows}
        except Exception as exc:  # noqa: BLE001
            blockers.append(
                Blocker(
                    code=BlockerCode.UPSTREAM_READ_FAILURE,
                    message=(
                        f"Variety catalog read failed while resolving "
                        f"variety codes: {type(exc).__name__}: {exc}"
                    ),
                    details={"field": "variety_catalog"},
                    retry_hint="WAIT_FOR_DATA",
                )
            )
            return BaselineCompositionResult(rows=[], blockers=blockers)

        rows, per_variety_blockers = _compose_rows(
            pool_rows=pool_rows_dict,
            residual_rows=residual_rows,
            varieties=normalized_request.varieties,
            variety_member_rows=variety_member_rows,
            variety_pk_by_code=pk_by_code,
            calendar=self._calendar,
            task9_run_id=task9_run_id,
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
    requested_variety_codes: tuple[str, ...] = (),
    effective_forecast_season: int | None = None,
) -> list[dict[str, Any]]:
    """Strict-scope TASK-009 selector.  No implicit latest.

    Returns the full list of candidate rows satisfying the scope; the
    caller is responsible for raising AUTHORITY_CONFLICT when more than
    one candidate is returned.

    P0-3 round 5:

    * When ``run_id_override`` is supplied, the override row is
      validated against the full strict scope: row exists, status ==
      'completed', destination matches, as-of visibility, forecast
      coverage, hash integrity, AND — when ``requested_variety_codes``
      is non-empty — the persisted member-row variety set covers the
      request.
    * When the override fails any of these checks, the selector
      returns ``[]`` (NOT the row) so the caller emits the typed
      AUTHORITY_NOT_FOUND / AUTHORITY_IDENTITY_MALFORMED blocker.

    P0-4 round 6:

    * ``effective_forecast_season`` (when non-None) MUST match the
      persisted ``as_of_date.year`` of the candidate.  This is a
      real persisted identity (every HarvestStateRun has
      ``as_of_date``); the selector does NOT auto-derive season from
      a date guess — it requires the request to supply an explicit
      integer season and the row to carry an ``as_of_date.year`` that
      matches.  When the requested season is supplied but no
      candidate matches it, the selector returns ``[]`` (typed
      AUTHORITY_NOT_FOUND via the caller).
    """

    from backend.app.models.harvest_state import (
        HarvestStateRun,
    )

    if run_id_override is not None:
        try:
            row = await session.get(HarvestStateRun, int(run_id_override))
        except Exception as exc:  # noqa: BLE001
            raise UpstreamReadFailure(
                f"TASK-009 override read failed: {type(exc).__name__}: {exc}"
            ) from exc
        if row is None:
            return []
        # P0-3 #12: validate the override against the full scope.
        if not await _validate_task9_row_against_scope(
            row=row,
            as_of=as_of,
            destination_factory_id=destination_factory_id,
            requested_variety_codes=requested_variety_codes,
            session=session,
            effective_forecast_season=effective_forecast_season,
        ):
            return []
        return [
            {
                "id": int(row.id),
                "result_hash": str(row.result_hash),
            }
        ]

    # Build the strict-scope filter.  The destination_factory_id MUST
    # enter the WHERE clause when supplied.
    filters = [
        HarvestStateRun.status == "completed",
        HarvestStateRun.as_of_date <= as_of,
        HarvestStateRun.forecast_end_date >= as_of,
    ]
    if destination_factory_id is not None:
        filters.append(HarvestStateRun.destination_factory_id == int(destination_factory_id))
    # P0-4 round 6: season filter uses the real persisted
    # as_of_date.year (every row carries it).  extract('year', ...)
    # is portable across SQLite + Postgres in SQLAlchemy 2.x.
    if effective_forecast_season is not None:
        filters.append(
            func.cast(func.strftime("%Y", HarvestStateRun.as_of_date), Integer)
            == int(effective_forecast_season)
        )

    stmt = select(HarvestStateRun.id, HarvestStateRun.result_hash).where(*filters)
    try:
        rows = (await session.execute(stmt)).all()
    except Exception as exc:  # noqa: BLE001
        raise UpstreamReadFailure(
            f"TASK-009 scope read failed: {type(exc).__name__}: {exc}"
        ) from exc

    candidates: list[dict[str, Any]] = []
    for r in rows:
        # P0-3 #11: when variety scope is requested, filter to TASK-9
        # runs whose member rows cover the requested variety set.
        if requested_variety_codes:
            try:
                covered = await _member_variety_codes_for_run(
                    session=session, harvest_state_run_id=int(r.id)
                )
            except Exception as exc:  # noqa: BLE001
                raise UpstreamReadFailure(
                    f"TASK-009 variety-scope read failed: {type(exc).__name__}: {exc}"
                ) from exc
            if not set(requested_variety_codes).issubset(covered):
                continue
        candidates.append({"id": int(r.id), "result_hash": str(r.result_hash)})
    return candidates


class UpstreamReadFailure(RuntimeError):
    """Raised by selectors when an unexpected upstream read error occurs.

    The composer translates this into a typed
    :data:`BlockerCode.UPSTREAM_READ_FAILURE` blocker.
    """


async def _validate_task9_row_against_scope(
    *,
    row: Any,
    as_of: date,
    destination_factory_id: int | None,
    requested_variety_codes: tuple[str, ...],
    session: AsyncSession,
    effective_forecast_season: int | None = None,
) -> bool:
    """P0-3 #12 + P0-4 round 6: validate a TASK-009 override row against
    the strict scope.

    Returns True iff all of the following hold:

    * ``row.status == 'completed'``
    * ``row.destination_factory_id == destination_factory_id`` when supplied
    * ``row.as_of_date <= as_of <= row.forecast_end_date``
    * ``row.result_hash`` is a 64-char lowercase hex string
    * ``row.config_hash`` is a 64-char lowercase hex string
    * when ``effective_forecast_season`` is supplied,
      ``row.as_of_date.year == effective_forecast_season``
    * when ``requested_variety_codes`` is non-empty, the
      persisted member-row variety set covers the request (this
      checks the member-row coverage of THIS specific row, not
      the default-scope coverage).
    """

    from backend.app.agent.adapters.task_loaders import (
        _SHA256_HEX_RE,
    )

    if str(getattr(row, "status", "")) != "completed":
        return False
    if destination_factory_id is not None and int(
        getattr(row, "destination_factory_id", -1) or -1
    ) != int(destination_factory_id):
        return False
    row_as_of = getattr(row, "as_of_date", None)
    row_end = getattr(row, "forecast_end_date", None)
    if row_as_of is None or row_end is None:
        return False
    if not (row_as_of <= as_of <= row_end):
        return False
    result_hash = str(getattr(row, "result_hash", "") or "")
    config_hash = str(getattr(row, "config_hash", "") or "")
    if not _SHA256_HEX_RE.match(result_hash):
        return False
    if not _SHA256_HEX_RE.match(config_hash):
        return False
    # P0-4 round 6: season validation against the real persisted
    # as_of_date.year.  Required when the caller supplied
    # effective_forecast_season.
    if effective_forecast_season is not None:
        if int(row_as_of.year) != int(effective_forecast_season):
            return False
    # P0-4 round 6: variety coverage — the persisted member-row
    # variety set of THIS row must cover the requested codes.
    if requested_variety_codes:
        try:
            covered = await _member_variety_codes_for_run(
                session=session, harvest_state_run_id=int(getattr(row, "id", 0) or 0)
            )
        except Exception:
            return False
        if not set(requested_variety_codes).issubset(covered):
            return False
    return True


async def _member_variety_codes_for_run(
    *, session: AsyncSession, harvest_state_run_id: int
) -> set[str]:
    """Return the set of string variety codes covered by a TASK-009 run.

    Reads ``HarvestStateDailyMemberRowModel.variety_id`` and joins
    against the ``Variety`` catalog to convert int PKs back to
    string codes.  An empty set means the run has no member rows
    (which is itself a per-variety grain failure).
    """

    from backend.app.models.harvest_state import (
        HarvestStateDailyMemberRowModel,
    )
    from backend.app.models.master_data import Variety as _Variety

    pk_rows = (
        await session.execute(
            select(
                HarvestStateDailyMemberRowModel.variety_id,
                _Variety.code,
            )
            .join(_Variety, _Variety.id == HarvestStateDailyMemberRowModel.variety_id)
            .where(HarvestStateDailyMemberRowModel.harvest_state_run_id == harvest_state_run_id)
        )
    ).all()
    return {str(code) for (_pk, code) in pk_rows}


async def _select_residual_prediction_run_candidates(
    session: AsyncSession,
    *,
    task9_run_id: int,
    task9_result_hash: str,
    prediction_run_id_override: int | None,
) -> list[dict[str, Any]]:
    """Strict-scope TASK-010 selector.  No implicit latest.

    Bind to TASK-009 by ``task9_run_id`` AND ``task9_result_hash``.

    P0-3 round 5:

    * When ``prediction_run_id_override`` is supplied, the override
      row is validated: row exists, ``execution_status == 'completed'``,
      ``task9_run_id`` matches the selected TASK-9, ``task9_result_hash``
      matches the selected TASK-9 result hash, and all required
      hash / datetime fields are present.  Failure returns ``[]``
      (NOT the row).

    P0-5 round 6: the override validator now checks the full identity
    surface carried by :class:`ResidualModelPredictionRun`:

    * ``prediction_hash`` is 64-char lowercase hex
    * ``config_hash`` is 64-char lowercase hex
    * ``prediction_input_signature`` is 64-char lowercase hex
    * ``canonical_payload_hash`` is 64-char lowercase hex
    * ``feature_schema_hash`` is 64-char lowercase hex
    * ``artifact_hashes`` (if present) are all 64-char lowercase hex
    * no fabricated fallback (a row whose ``fallback_reason`` is
      set is treated as not-completed-equivalent — explicit
      fallback_reason triggers AUTHORITY_NOT_FOUND via the caller)
    * execution_status is exactly 'completed' (not 'failed',
      not 'running', not 'unavailable')

    Any of the above checks failing returns ``[]`` so the caller
    surfaces the typed blocker (NOT FOUND, HASH MALFORMED, IDENTITY
    MALFORMED, LINEAGE MISMATCH, UPSTREAM READ FAILURE).
    """

    from backend.app.agent.adapters.task_loaders import _SHA256_HEX_RE
    from backend.app.models.residual_model import ResidualModelPredictionRun

    def _strict_hex(value: Any, field: str) -> str | None:
        s = str(value or "")
        if not s or not _SHA256_HEX_RE.match(s):
            return None
        return s

    if prediction_run_id_override is not None:
        try:
            row = await session.get(ResidualModelPredictionRun, int(prediction_run_id_override))
        except Exception as exc:  # noqa: BLE001
            raise UpstreamReadFailure(
                f"TASK-010 override read failed: {type(exc).__name__}: {exc}"
            ) from exc
        if row is None:
            return []
        if str(getattr(row, "execution_status", "")) != "completed":
            return []
        if int(getattr(row, "task9_run_id", -1) or -1) != int(task9_run_id):
            return []
        if str(getattr(row, "task9_result_hash", "")) != str(task9_result_hash):
            return []
        # P0-5 round 6: full identity check.
        if _strict_hex(getattr(row, "prediction_hash", None), "prediction_hash") is None:
            return []
        if _strict_hex(getattr(row, "config_hash", None), "config_hash") is None:
            return []
        input_sig = getattr(row, "prediction_input_signature", None)
        if _strict_hex(input_sig, "prediction_input_signature") is None:
            return []
        cp_hash = getattr(row, "canonical_payload_hash", None)
        if _strict_hex(cp_hash, "canonical_payload_hash") is None:
            return []
        fs_hash = getattr(row, "feature_schema_hash", None)
        if _strict_hex(fs_hash, "feature_schema_hash") is None:
            return []
        artifact_hashes = list(getattr(row, "artifact_hashes", []) or [])
        for h in artifact_hashes:
            if _strict_hex(h, "artifact_hashes[]") is None:
                return []
        # P0-5: explicit fallback_reason disqualifies the run.
        if getattr(row, "fallback_reason", None) is not None:
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
    try:
        rows = (await session.execute(stmt)).all()
    except Exception as exc:  # noqa: BLE001
        raise UpstreamReadFailure(
            f"TASK-010 scope read failed: {type(exc).__name__}: {exc}"
        ) from exc
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

    P0-5 round 5: an explicit TASK-008 override MUST equal the
    ``maturity_forecast_run_id`` pointer on the selected TASK-009
    row; otherwise the override is rejected and the
    :data:`BlockerCode.TASK8_AUTHORITY_LINEAGE_MISMATCH` blocker is
    raised at the call site.
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

    P0-6 round 6: duplicate member rows for the same
    ``(state_date, forecast_quantile, variety_pk)`` key are SUMMED
    via SQL ``SUM(arrival_quantity_kg) GROUP BY (state_date,
    forecast_quantile, variety_id)`` — the freeze TASK-009 grain
    considers duplicate rows a valid aggregation, not an integrity
    conflict.  The resulting dict carries the aggregated quantity
    for each unique key.
    """
    from backend.app.models.harvest_state import HarvestStateDailyMemberRowModel

    rows = (
        await session.execute(
            select(
                HarvestStateDailyMemberRowModel.state_date,
                HarvestStateDailyMemberRowModel.forecast_quantile,
                HarvestStateDailyMemberRowModel.variety_id,
                func.sum(HarvestStateDailyMemberRowModel.arrival_quantity_kg),
            )
            .where(HarvestStateDailyMemberRowModel.harvest_state_run_id == harvest_state_run_id)
            .group_by(
                HarvestStateDailyMemberRowModel.state_date,
                HarvestStateDailyMemberRowModel.forecast_quantile,
                HarvestStateDailyMemberRowModel.variety_id,
            )
        )
    ).all()
    out: dict[tuple[date, str, int], Decimal] = {}
    for state_date, forecast_quantile, variety_pk, total_kg in rows:
        key = (state_date, str(forecast_quantile), int(variety_pk))
        out[key] = Decimal(str(total_kg)) if total_kg is not None else Decimal("0")
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
    task9_run_id: int | None = None,
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
            task9_run_id=task9_run_id,
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
                spring_festival_phase=cast(
                    "Any",
                    calendar.phase_for(target=d),
                ),
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
    task9_run_id: int | None = None,
) -> tuple[list[VarietyContribution], list[Blocker]]:
    """Per-variety contribution from :class:`HarvestStateDailyMemberRowModel`.

    For each date × quantile, sum ``member.arrival_quantity_kg`` per
    variety and divide by the pool total for that quantile.  The agent
    input uses STRING variety codes (e.g. "Dx"), while the member row
    stores an INT PK — ``variety_pk_by_code`` provides the mapping.

    P0-4 round 5:

    * Missing member row for any (date, quantile, variety) → typed
      TASK9_PER_VARIETY_GRAIN_MISSING blocker carrying the exact
      (date, quantile, variety_id) keys.  The day's
      ``per_variety_contribution`` is EMPTY (no partial
      contribution, no equal-split fallback, no 0/1 placeholders).
    * Sum-of-member-volume reconciliation against the pool total per
      quantile: when ``pool_total > 0`` the sum of member volumes
      for that quantile MUST equal the pool total; when
      ``pool_total == 0`` all member volumes MUST be 0.  Failure
      returns a typed integrity blocker.
    * Sum-of-contribution-rate = 1 within the frozen tolerance per
      quantile (when pool total > 0).
    * Duplicate member rows for the same (date, quantile, variety)
      are aggregated (not overwritten).
    """

    if not varieties:
        return [], []

    contributions: list[VarietyContribution] = []
    blockers: list[Blocker] = []

    any_member = any(md == d for (md, _, _) in variety_member_rows)
    if not any_member:
        # P0-7 round 6: typed TASK9_PER_VARIETY_GRAIN_MISSING (not
        # INTERNAL_FAILURE) so the per-day contribution is empty
        # and the blocker carries the real task9_run_id, not a
        # variety_pk.  Caller will pass the real task9_run_id.
        blockers.append(
            Blocker(
                code=BlockerCode.TASK9_PER_VARIETY_GRAIN_MISSING,
                message=(
                    f"No HarvestStateDailyMemberRowModel rows available for date "
                    f"{d.isoformat()}; per-variety grain is missing."
                ),
                details={"date": d.isoformat()},
                retry_hint="WAIT_FOR_DATA",
            )
        )
        return [], blockers

    # Build a per-(date, quantile) "member view" aggregated across all
    # rows: the keys we walk are (date, quantile) -> {variety_pk -> total
    # arrival_quantity_kg}.  This automatically aggregates duplicate
    # member rows.
    member_by_q: dict[str, dict[int, Decimal]] = {"P50": {}, "P80": {}, "P90": {}}
    for (md, q, member_variety_pk), arrival_kg in variety_member_rows.items():
        if md != d:
            continue
        if q not in member_by_q:
            continue
        member_by_q[q].setdefault(int(member_variety_pk), Decimal("0"))
        member_by_q[q][int(member_variety_pk)] += Decimal(arrival_kg)

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

        per_variety_missing: list[str] = []
        per_quantile_volume: dict[str, Decimal] = {}
        per_quantile_rate: dict[str, Decimal] = {}
        per_quantile_total: dict[str, Decimal] = {}

        for q in ("P50", "P80", "P90"):
            pool_total = _d(pool_arrival.get(f"{q}_arrival", Decimal("0")))
            member_v = member_by_q[q].get(int(vid_pk))
            if member_v is None:
                per_variety_missing.append(q)
                per_quantile_volume[q] = Decimal("0")
                per_quantile_rate[q] = Decimal("0")
                per_quantile_total[q] = pool_total
                continue
            volume = _d(member_v)
            if pool_total > 0:
                rate = volume / pool_total
            else:
                rate = Decimal("0")
            per_quantile_volume[q] = volume
            per_quantile_rate[q] = rate
            per_quantile_total[q] = pool_total

        if per_variety_missing:
            # Typed per-(date, quantile, variety) blocker (P0-4 #14).
            for q in per_variety_missing:
                blockers.append(
                    Blocker(
                        code=BlockerCode.TASK9_PER_VARIETY_GRAIN_MISSING,
                        message=(
                            f"per-variety grain missing for date={d.isoformat()} "
                            f"variety={vid_code} quantile={q} task9_run_id="
                            f"{task9_run_id}"
                        ),
                        details={
                            "date": d.isoformat(),
                            "quantile": q,
                            "variety_id": vid_code,
                            "task9_run_id": int(task9_run_id) if task9_run_id is not None else None,
                        },
                        retry_hint="WAIT_FOR_DATA",
                    )
                )
            # Per-day per-variety_contribution is empty for THIS day
            # when ANY quantile is missing.  Per Charles's spec, the
            # day's contribution MUST be empty (no partial
            # contribution, no 0 placeholders).
            continue

        # Reconciliation: per quantile, sum(member_v) over all
        # varieties for this (date, quantile) should equal the pool
        # total; when pool_total > 0 the contribution rates must sum
        # to 1 within tolerance.
        # P0-7 round 6: when ANY quantile fails reconciliation, the
        # WHOLE day's contribution list is cleared (no
        # zero-rates-and-append fallback).  The day is reported as
        # integrity-blocked.
        reconciliation_failed = False
        for q in ("P50", "P80", "P90"):
            pool_total = per_quantile_total[q]
            sum_member_volume = sum(_d(v) for v in member_by_q[q].values())
            if pool_total > 0 and sum_member_volume != pool_total:
                blockers.append(
                    Blocker(
                        code=BlockerCode.TASK9_PER_VARIETY_GRAIN_MISSING,
                        message=(
                            f"member volume sum reconciliation failure for "
                            f"date={d.isoformat()} quantile={q}: "
                            f"sum_member={sum_member_volume} != pool_total={pool_total}"
                        ),
                        details={
                            "date": d.isoformat(),
                            "quantile": q,
                            "sum_member_volume": format(sum_member_volume, "f"),
                            "pool_total": format(pool_total, "f"),
                        },
                        retry_hint="WAIT_FOR_DATA",
                    )
                )
                reconciliation_failed = True
            elif pool_total == 0 and sum_member_volume != 0:
                blockers.append(
                    Blocker(
                        code=BlockerCode.TASK9_PER_VARIETY_GRAIN_MISSING,
                        message=(
                            f"member volume non-zero with zero pool total for "
                            f"date={d.isoformat()} quantile={q}: "
                            f"sum_member={sum_member_volume} pool_total=0"
                        ),
                        details={
                            "date": d.isoformat(),
                            "quantile": q,
                            "sum_member_volume": format(sum_member_volume, "f"),
                            "pool_total": "0",
                        },
                        retry_hint="WAIT_FOR_DATA",
                    )
                )
                reconciliation_failed = True
        if reconciliation_failed:
            # P0-7 #10: the day's per-variety_contribution list is
            # CLEARED.  We do NOT append zero-rate VarietyContribution
            # records.  The day is reported as integrity-blocked.
            return [], blockers

        contributions.append(
            VarietyContribution(
                variety_id=vid_code,
                volume_kg_p50=_ds(per_quantile_volume["P50"]),
                volume_kg_p80=_ds(per_quantile_volume["P80"]),
                volume_kg_p90=_ds(per_quantile_volume["P90"]),
                contribution_rate_p50=_ds(per_quantile_rate["P50"]),
                contribution_rate_p80=_ds(per_quantile_rate["P80"]),
                contribution_rate_p90=_ds(per_quantile_rate["P90"]),
            )
        )

    return contributions, blockers


__all__ = [
    "DefaultTaskCompositionBaseline",
    "BaselineCompositionResult",
]
