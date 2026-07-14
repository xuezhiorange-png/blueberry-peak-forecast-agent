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
2. Distinguish a discriminated set of outcomes via
   :class:`AuthoritySelectionResult` (candidates XOR blockers — never
   both, never bare-empty).  Each failure mode maps to a typed
   ``BlockerCode``:
   * :data:`BlockerCode.TASK9_AUTHORITY_NOT_FOUND` — no row matches the
     base scope (status / destination / date coverage).
   * :data:`BlockerCode.AUTHORITY_SCOPE_MISMATCH` — candidate rows
     exist but fail scope (no persisted season identity, season
     mismatch, date coverage, destination, variety-scope mismatch).
   * :data:`BlockerCode.AUTHORITY_HASH_MALFORMED` — ``result_hash`` /
     ``config_hash`` / ``prediction_hash`` / etc. malformed.
   * :data:`BlockerCode.AUTHORITY_IDENTITY_MALFORMED` — required
     identity column missing or wrong type.
   * :data:`BlockerCode.AUTHORITY_LINEAGE_MISMATCH` — TASK-010 lineage
     does not bind to the selected TASK-009 run.
   * :data:`BlockerCode.UPSTREAM_READ_FAILURE` — ORM query raised an
     unexpected exception (fail-closed; not silently NOT_FOUND).
   * :data:`BlockerCode.AUTHORITY_CONFLICT` — multiple fully-valid
     candidates; disclose every candidate ID + hash; do NOT auto
     tie-break.
3. The destination_factory_id passed to the selector MUST appear in the
   WHERE clause; if the upstream query is unable to apply the filter, the
   loader fails closed with :data:`BlockerCode.AUTHORITY_IDENTITY_MALFORMED`.

**TASK-009 season identity (P0-1 review 4680340321)**

The legacy ``HarvestStateRun.as_of_date.year`` derivation is FORBIDDEN —
it is a date-guess, not a persisted identity.  Real TASK-009 rows
written by ``_sorted_request_snapshot()`` do NOT carry
``input_snapshot["forecast_season"]``.  When the request asks for an
explicit season and the candidate row has no persisted season binding,
the selector MUST return an ``AUTHORITY_SCOPE_MISMATCH`` blocker with
``reason=PERSISTED_FORECAST_SEASON_IDENTITY_UNAVAILABLE`` — NOT a
silent ``TASK9_AUTHORITY_NOT_FOUND`` collapse.

**Per-variety contribution (P0-4 / P0-5 review 4680340321)**

Per-variety contribution is read from
:class:`~backend.app.models.harvest_state.HarvestStateDailyMemberRowModel`
and composed in three strict phases:

* **Phase 1 (matrix prevalidation):** for every requested variety ×
  P50/P80/P90 × target date, verify a real member row exists BEFORE
  creating any :class:`VarietyContribution`.  A later variety missing
  P90 MUST NOT silently drop the earlier variety's contribution.
* **Phase 2 (denominator scope):** the persisted member-variety set
  for the selected TASK-009 run MUST equal the requested variety set
  (exact).  An extra persisted variety with non-zero volume is a scope
  mismatch (no mixed-semantic denominator / requested-only output
  truncation).
* **Phase 3 (compute + reconcile):** build contributions, validate
  per-quantile sum-of-member-volume = pool-arrival total, sum-of-rate
  = 1 (pool > 0) or all-zero (pool = 0).  Any reconciliation failure
  returns ``[]`` + typed blockers — never partial contribution.

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

from sqlalchemy import func, or_, select
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
from backend.app.residual_model.canonical import canonical_json_dumps


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


@dataclass(frozen=True)
class AuthoritySelectionResult:
    """Discriminated selector result (review 4680340321 P0-2 / P0-3).

    Selectors MUST return this type instead of a bare
    ``list[dict[str, Any]]``.  Either ``candidates`` is non-empty and
    ``blockers`` is empty, OR ``blockers`` is non-empty and
    ``candidates`` is empty.  Empty-empty or both-non-empty is a
    programming error.
    """

    candidates: tuple[dict[str, Any], ...] = ()
    blockers: tuple[Blocker, ...] = ()

    def __post_init__(self) -> None:
        if bool(self.candidates) == bool(self.blockers):
            raise ValueError(
                "AuthoritySelectionResult: candidates and blockers are "
                "mutually exclusive; exactly one must be non-empty "
                f"(candidates={len(self.candidates)}, "
                f"blockers={len(self.blockers)})."
            )

    @property
    def is_empty(self) -> bool:
        return not self.candidates and not self.blockers

    @property
    def first_blocker(self) -> Blocker | None:
        return self.blockers[0] if self.blockers else None


# --- Identity-mismatch reason codes (round 8 / review 4680340321) --------
#
# TASK-009 / TASK-010 selectors surface a typed ``reason`` value
# inside ``AUTHORITY_SCOPE_MISMATCH`` ``Blocker.details`` so callers
# can disambiguate root-cause classes without inventing a new
# ``BlockerCode`` per case (per the round 8 directive: "use existing
# blocker taxonomy; do not add a parallel duplicate taxonomy").

SEASON_BINDING_UNAVAILABLE = "PERSISTED_FORECAST_SEASON_IDENTITY_UNAVAILABLE"
TASK9_SEASON_SCHEMA_UNSUPPORTED = "TASK9_SEASON_IDENTITY_SCHEMA_UNSUPPORTED"
SEASON_IDENTITY_MALFORMED = "PERSISTED_FORECAST_SEASON_IDENTITY_MALFORMED"
SEASON_IDENTITY_CONFLICT = "PERSISTED_FORECAST_SEASON_IDENTITY_CONFLICT"
SEASON_REGISTRY_DRIFT = "PERSISTED_FORECAST_SEASON_REGISTRY_DRIFT"
FORECAST_SEASON_ID_MISMATCH = "FORECAST_SEASON_ID_MISMATCH"
FALLBACK_RUN_NOT_AUTHORITATIVE = "FALLBACK_RUN_NOT_AUTHORITATIVE"
MEMBER_VARIETY_SET_MISMATCH = "TASK9_MEMBER_VARIETY_SET_MISMATCH"
EXECUTION_STATUS_NOT_COMPLETED = "EXECUTION_STATUS_NOT_COMPLETED"
DESTINATION_MISMATCH = "DESTINATION_MISMATCH"
DATE_COVERAGE_MISMATCH = "DATE_COVERAGE_MISMATCH"


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
                        "effective_forecast_season_id": (
                            normalized_request.effective_forecast_season_id
                        ),
                        "calendar_policy_version": None,
                        "calendar_config_hash": None,
                    },
                    retry_hint="PROVIDE_OVERRIDE",
                )
            )

        # ---- TASK-009 selector (strict scope, no latest) --------------
        # P0-2 / P0-3 (review 4680340321): the selector returns a
        # discriminated :class:`AuthoritySelectionResult`; consumers
        # dispatch on ``.candidates`` / ``.blockers`` and never
        # collapse distinct failure modes into a single NOT_FOUND
        # blob.
        task9_run_id_override = _select_authority_run_id(
            advanced_overrides, "TASK9_HARVEST_STATE_RUN"
        )
        requested_variety_codes = tuple(str(v.variety_id) for v in normalized_request.varieties)
        task9_selection = await _select_harvest_state_run_candidates(
            session,
            as_of=normalized_request.effective_as_of_date,
            run_id_override=task9_run_id_override,
            destination_factory_id=getattr(resolved_location, "location_reference_id", None),
            requested_variety_codes=requested_variety_codes,
            effective_forecast_season_id=normalized_request.effective_forecast_season_id,
        )
        if task9_selection.blockers:
            blockers.extend(task9_selection.blockers)
            # The TASK-010 lineage is bound to TASK-009; if the
            # TASK-009 selection did not produce a candidate, emit a
            # TASK-010_AUTHORITY_NOT_FOUND to disclose the downstream
            # gap, while preserving the upstream typed blockers.
            # Only add it when the TASK-009 failure was
            # "not found" / "scope mismatch" / "upstream read
            # failure" (i.e. the lineage is not just contested);
            # when the upstream returned a conflicting but
            # "complete" set, the downstream TASK-010 is
            # intentionally not surfaced (the conflict is the
            # actionable signal).
            task9_codes = {b.code for b in task9_selection.blockers}
            task9_precludes_lineage = bool(
                task9_codes
                & {
                    BlockerCode.TASK9_AUTHORITY_NOT_FOUND,
                    BlockerCode.AUTHORITY_SCOPE_MISMATCH,
                    BlockerCode.UPSTREAM_READ_FAILURE,
                    BlockerCode.AUTHORITY_IDENTITY_MALFORMED,
                    BlockerCode.AUTHORITY_HASH_MALFORMED,
                }
            )
            if task9_precludes_lineage and not any(
                b.code == BlockerCode.TASK10_AUTHORITY_NOT_FOUND for b in blockers
            ):
                blockers.append(
                    Blocker(
                        code=BlockerCode.TASK10_AUTHORITY_NOT_FOUND,
                        message=(
                            "No TASK-010 residual prediction run available: "
                            "the TASK-009 lineage required to bind TASK-010 "
                            "is missing or invalid."
                        ),
                        retry_hint="WAIT_FOR_DATA",
                    )
                )
            return BaselineCompositionResult(rows=[], blockers=blockers)
        task9_candidates = list(task9_selection.candidates)
        if not task9_candidates:
            # Defensive: should be unreachable (selector invariant
            # is candidates XOR blockers, never both empty).
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
        # P0-3 (review 4680340321): the selector returns
        # :class:`AuthoritySelectionResult`; failures are preserved
        # with their typed discriminator (not collapsed to
        # TASK10_AUTHORITY_NOT_FOUND).
        task10_run_id_override = _select_authority_run_id(
            advanced_overrides, "TASK10_PREDICTION_RUN"
        )
        task10_selection = await _select_residual_prediction_run_candidates(
            session,
            task9_run_id=task9_run_id,
            task9_result_hash=task9_result_hash,
            prediction_run_id_override=task10_run_id_override,
        )
        if task10_selection.blockers:
            blockers.extend(task10_selection.blockers)
            return BaselineCompositionResult(rows=[], blockers=blockers)
        task10_candidates = list(task10_selection.candidates)
        if not task10_candidates:
            # Defensive: should be unreachable.
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

        # P0-3 (review 4680340321): lineage integrity is enforced
        # inside the selector's shared validator
        # :func:`_evaluate_task10_row_against_scope`; no duplicate
        # post-hoc re-check is needed here.

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


def _conflict_candidate_id(candidate: dict[str, Any]) -> int:
    """Extract the deterministic identity of an AUTHORITY_CONFLICT candidate.

    Conflict candidates arrive from the upstream selectors in
    field shapes that differ between TASK-009 and TASK-010:

    * TASK-009 callers use ``{"harvest_state_run_id": ..., "result_hash": ...}``.
    * TASK-010 callers use ``{"prediction_run_id": ..., ...}``.

    A conflict candidate MUST carry exactly one supported identity
    field.  Empty, ambiguous or unsupported payloads fail-closed
    via :class:`ValueError` (no silent ``0`` fallback).  The set of
    supported identity keys is fixed and explicit:

    * ``id``  — generic selection (kept for backward compatibility)
    * ``harvest_state_run_id``  — TASK-009 conflict
    * ``prediction_run_id``  — TASK-010 conflict
    """

    supported = (
        "id",
        "harvest_state_run_id",
        "prediction_run_id",
    )
    present = [candidate[key] for key in supported if candidate.get(key) is not None]
    if len(present) != 1:
        raise ValueError(
            "conflict candidate must contain exactly one supported identity "
            f"(id, harvest_state_run_id, prediction_run_id); got {len(present)}"
        )
    return int(present[0])


def _authority_conflict_blocker(target: str, candidates: list[dict[str, Any]]) -> Blocker:
    """Build a typed AUTHORITY_CONFLICT blocker with full candidate disclosure.

    Per Charles's direction, the loader MUST NOT auto tie-break.  Every
    candidate ID + hash is disclosed; the orchestrator (or the human
    caller) selects one explicitly via an authority override.

    The candidate list is sorted by the real identity field
    (``harvest_state_run_id`` for TASK-009 conflicts, ``prediction_run_id``
    for TASK-010 conflicts) ascending (Round 11 review 4680976947) so
    the disclosure has a stable total order across cross-DB
    (SQLite / PostgreSQL) execution and across opposite insertion
    order on equivalent content.
    """

    sorted_candidates = sorted(candidates, key=_conflict_candidate_id)
    return Blocker(
        code=BlockerCode.AUTHORITY_CONFLICT,
        message=(
            f"Multiple {target} candidates satisfy the strict scope filter. "
            "Caller MUST disambiguate via an explicit authority override."
        ),
        details={
            "target": target,
            "candidate_count": len(sorted_candidates),
            "candidates": sorted_candidates,
        },
        retry_hint="PROVIDE_OVERRIDE",
    )


def _blocker_sort_key(blocker: Blocker) -> tuple[str, str, str, str]:
    """Strict total-order key for :class:`Blocker` (Round 11 review 4680976947).

    The Round 10 key ``(code, reason, field)`` was content-based but
    not a strict total order: two blockers with the same
    ``(code, reason, field)`` but different ``row_id`` / ``message`` /
    ``details`` produced identical keys, so their order was a
    function of the input list order (NOT of the public payload
    content).  That allowed reverse-order inputs to produce
    different public payloads.

    Round 11 appends the full canonical public payload
    (:func:`canonical_json_dumps` of
    :meth:`Blocker.model_dump(mode="json")`) as the final tie-break.
    Two blockers with distinct public content now produce
    distinct sort keys; the resulting order is a strict total order
    over the public surface and is byte-identical across reverse
    input orders and across SQLite / PostgreSQL execution.
    """

    details = blocker.details or {}
    public_payload = canonical_json_dumps(blocker.model_dump(mode="json"))
    return (
        str(getattr(blocker.code, "value", str(blocker.code))),
        str(details.get("reason", "") or ""),
        str(details.get("field", "") or ""),
        public_payload,
    )


def _sort_blockers_deterministically(blockers: list[Blocker]) -> list[Blocker]:
    """Sort blockers by the stable total-order key.

    Python-level sort (P0-2 review 4680912426) is preferred over
    SQL ``ORDER BY`` because the latter cannot guarantee a
    cross-database (SQLite / PostgreSQL) tie-break for the same
    semantic content.  Sorting here is a *display* decision; it
    does NOT auto-select any single authority.
    """
    return sorted(blockers, key=_blocker_sort_key)


# --- Strict-scope ORM selectors -----------------------------------------


async def _select_harvest_state_run_candidates(
    session: AsyncSession,
    *,
    as_of: date,
    run_id_override: int | None,
    destination_factory_id: int | None,
    requested_variety_codes: tuple[str, ...] = (),
    effective_forecast_season_id: int | None = None,
) -> AuthoritySelectionResult:
    """Strict-scope TASK-009 selector.  No implicit latest.

    Returns a discriminated :class:`AuthoritySelectionResult`:

    * ``candidates`` non-empty → one or more fully-valid TASK-009 rows
      pass the strict scope; caller disambiguates ``len > 1`` via
      :data:`BlockerCode.AUTHORITY_CONFLICT`.
    * ``blockers`` non-empty → zero fully-valid candidates; the
      blocker tuple is exhaustive (each entry carries a typed reason).

    P0-3 (review 4680340321): the default path now performs the SAME
    identity / hash / datetime / season-scope validation as the
    override path.  Override and default share
    :func:`_evaluate_task9_row_against_scope` so a row that fails any
    check in one path also fails in the other.

    The sole season selector authority is the v2
    ``HarvestStateRun.forecast_season_id`` FK and its validated
    canonical mirror. Legacy input-snapshot season values and date-year
    derivation are never consulted.

    Failure mode taxonomy (P0-2):

    * no base-scope row at all (status / destination / date coverage)
      → :data:`BlockerCode.TASK9_AUTHORITY_NOT_FOUND`
    * candidate row exists but ``result_hash`` / ``config_hash`` is
      not 64-char lowercase hex → :data:`BlockerCode.AUTHORITY_HASH_MALFORMED`
    * candidate row exists but required identity field is missing
      or wrong type → :data:`BlockerCode.AUTHORITY_IDENTITY_MALFORMED`
    * candidate row exists but no persisted season binding matches
      the requested season → :data:`BlockerCode.AUTHORITY_SCOPE_MISMATCH`
    * member-variety ORM query raised an unexpected exception →
      :data:`BlockerCode.UPSTREAM_READ_FAILURE`
    * multiple fully-valid candidates → caller emits
      :data:`BlockerCode.AUTHORITY_CONFLICT` (not this function).
    """

    from backend.app.models.harvest_state import HarvestStateRun

    candidate_dicts: list[dict[str, Any]] = []
    collected_blockers: list[Blocker] = []

    # ---- Override path: validate the explicit run id -----------------
    if run_id_override is not None:
        try:
            row = await session.get(HarvestStateRun, int(run_id_override))
        except Exception as exc:  # noqa: BLE001
            return AuthoritySelectionResult(
                blockers=(
                    Blocker(
                        code=BlockerCode.UPSTREAM_READ_FAILURE,
                        message=(f"TASK-009 override read failed: {type(exc).__name__}: {exc}"),
                        details={
                            "field": "harvest_state_run_override_read",
                            "run_id_override": int(run_id_override),
                        },
                        retry_hint="WAIT_FOR_DATA",
                    ),
                )
            )
        if row is None:
            return AuthoritySelectionResult(
                blockers=(
                    Blocker(
                        code=BlockerCode.TASK9_AUTHORITY_NOT_FOUND,
                        message=(
                            f"TASK-009 override run id {int(run_id_override)} does not exist."
                        ),
                        details={"run_id_override": int(run_id_override)},
                        retry_hint="WAIT_FOR_DATA",
                    ),
                )
            )
        outcome = await _evaluate_task9_row_against_scope(
            row=row,
            as_of=as_of,
            destination_factory_id=destination_factory_id,
            requested_variety_codes=requested_variety_codes,
            session=session,
            effective_forecast_season_id=effective_forecast_season_id,
        )
        if outcome.candidates:
            return outcome
        # Override path returns the row's typed failure blockers.
        return outcome

    # ---- Default path: two-stage related-candidate query ----------
    # P0-1 (review 4680528194): the previous default path applied
    # ``status='completed'``, ``destination_factory_id``, and the
    # full date-coverage window in the SQL ``WHERE`` clause.  Out-of-
    # scope rows therefore disappeared before the shared validator
    # could surface them, collapsing to
    # :data:`BlockerCode.TASK9_AUTHORITY_NOT_FOUND` instead of a
    # typed :data:`BlockerCode.AUTHORITY_SCOPE_MISMATCH`.
    #
    # Stage A (related-candidate query): load any row that is
    # *diagnostically relevant* to the request — i.e. overlaps the
    # requested date window (``as_of_date <= as_of <= forecast_end_date``)
    # OR the requested ``destination_factory_id``.  This is the
    # minimal relation surface that lets the shared validator classify
    # a row's status, destination, date coverage, hash, season, and
    # variety scope uniformly.
    #
    # Stage B (shared validator): every related row is fed through
    # :func:`_evaluate_task9_row_against_scope`.  Rows that pass are
    # returned as candidates; rows that fail surface their typed
    # blockers.  The selector returns ``TASK9_AUTHORITY_NOT_FOUND``
    # ONLY when no related row exists at all.
    #
    # Determinism: no ``ORDER BY`` / ``LIMIT`` / implicit-latest
    # selection.  The composer's downstream ``len > 1`` dispatch
    # surfaces :data:`BlockerCode.AUTHORITY_CONFLICT` when more than
    # one row passes the validator.

    # Stage A related-candidate query (P0-1 review 4680912426):
    # the global as-of visibility cutoff is enforced AS A TOP-LEVEL
    # AND before any destination broadening.  A future TASK-009
    # row (row.as_of_date > request.as_of) MUST be completely
    # invisible to the default path: no candidate, no scope
    # mismatch, no blocker message/details, no conflict
    # disclosure.  The destination broadening is a SCOPE-widening
    # diagnostic helper (it surfaces destination-mismatched
    # visible rows) — it is NOT a permission to bypass the as-of
    # visibility cutoff.
    #
    # Semantic equivalent:
    #     HarvestStateRun.as_of_date <= request_as_of
    #     AND (
    #         HarvestStateRun.forecast_end_date >= request_as_of
    #         OR HarvestStateRun.destination_factory_id == requested_destination
    #     )
    # When ``destination_factory_id is None`` the destination
    # broadening is omitted; only the date-window clause is used.
    visibility_clause = HarvestStateRun.as_of_date <= as_of
    scope_clauses: list[Any] = [HarvestStateRun.forecast_end_date >= as_of]
    if destination_factory_id is not None:
        scope_clauses.append(HarvestStateRun.destination_factory_id == int(destination_factory_id))
    related_stmt = select(
        HarvestStateRun.id,
        HarvestStateRun.status,
        HarvestStateRun.destination_factory_id,
        HarvestStateRun.as_of_date,
        HarvestStateRun.forecast_end_date,
        HarvestStateRun.result_hash,
        HarvestStateRun.config_hash,
        HarvestStateRun.output_schema_version,
        HarvestStateRun.result_hash_schema_version,
        HarvestStateRun.forecast_season_id,
        HarvestStateRun.input_snapshot,
    ).where(visibility_clause, or_(*scope_clauses))
    try:
        rows = (await session.execute(related_stmt)).all()
    except Exception as exc:  # noqa: BLE001
        return AuthoritySelectionResult(
            blockers=(
                Blocker(
                    code=BlockerCode.UPSTREAM_READ_FAILURE,
                    message=(
                        f"TASK-009 related-candidate read failed: {type(exc).__name__}: {exc}"
                    ),
                    details={"field": "harvest_state_run_related_scope"},
                    retry_hint="WAIT_FOR_DATA",
                ),
            )
        )

    if not rows:
        # No related row exists at all → this is the ONLY case that
        # legitimately emits :data:`BlockerCode.TASK9_AUTHORITY_NOT_FOUND`.
        return AuthoritySelectionResult(
            blockers=(
                Blocker(
                    code=BlockerCode.TASK9_AUTHORITY_NOT_FOUND,
                    message=(
                        "No TASK-009 harvest-state run is related to the "
                        "request's date window or destination; cannot "
                        "classify scope / status / identity without a "
                        "candidate row to validate."
                    ),
                    details={
                        "effective_as_of_date": as_of.isoformat(),
                        "destination_factory_id": (
                            int(destination_factory_id)
                            if destination_factory_id is not None
                            else None
                        ),
                    },
                    retry_hint="WAIT_FOR_DATA",
                ),
            )
        )

    # P0-1 / P0-2: every base-scope row must be evaluated through the
    # same validator (hashes, identity, season, variety scope).  Rows
    # that fail validation are EXCLUDED with typed blockers; rows
    # that pass are appended as candidates.
    for r in rows:
        outcome = await _evaluate_task9_row_against_scope(
            row=r,
            as_of=as_of,
            destination_factory_id=destination_factory_id,
            requested_variety_codes=requested_variety_codes,
            session=session,
            effective_forecast_season_id=effective_forecast_season_id,
        )
        if outcome.candidates:
            candidate_dicts.extend(outcome.candidates)
        elif outcome.blockers:
            # Collect typed-failure blockers (e.g. season-scope,
            # hash-malformed, identity-malformed, upstream-read
            # failure).  We do NOT collapse them to a single
            # TASK9_AUTHORITY_NOT_FOUND; each one is preserved with
            # its discriminator.
            collected_blockers.extend(outcome.blockers)

    # P0-2 (review 4680912426): sort candidates by ``id`` ascending
    # so the public ``candidates`` tuple has a stable total order
    # across cross-DB (SQLite / PostgreSQL) execution and across
    # opposite insertion order on equivalent content.  This is a
    # DISPLAY decision, not an authority auto-selection.
    candidate_dicts.sort(key=lambda c: int(c.get("id", 0) or 0))

    if candidate_dicts:
        return AuthoritySelectionResult(candidates=tuple(candidate_dicts))
    if collected_blockers:
        # Stable-sort blockers by (code, row_id, reason, field) so
        # the public blocker surface is deterministic.
        return AuthoritySelectionResult(
            blockers=tuple(_sort_blockers_deterministically(collected_blockers))
        )
    # Defensive: rows existed but every one was excluded for a reason
    # not yet wired (should be unreachable).  Return a typed
    # AUTHORITY_SCOPE_MISMATCH so the failure is never silent.
    return AuthoritySelectionResult(
        blockers=(
            Blocker(
                code=BlockerCode.AUTHORITY_SCOPE_MISMATCH,
                message=(
                    "TASK-009 base-scope rows existed but all were "
                    "excluded by scope/identity checks; see aggregated "
                    "blockers for details."
                ),
                details={"effective_as_of_date": as_of.isoformat()},
                retry_hint="FIX_INPUT",
            ),
        )
    )


class UpstreamReadFailure(RuntimeError):
    """Raised by selectors when an unexpected upstream read error occurs.

    The composer translates this into a typed
    :data:`BlockerCode.UPSTREAM_READ_FAILURE` blocker.
    """


async def _evaluate_task9_row_against_scope(
    *,
    row: Any,
    as_of: date,
    destination_factory_id: int | None,
    requested_variety_codes: tuple[str, ...],
    session: AsyncSession,
    effective_forecast_season_id: int | None = None,
) -> AuthoritySelectionResult:
    """Validate a TASK-009 candidate row against the strict scope.

    Returns a discriminated :class:`AuthoritySelectionResult`.  On
    success the row appears as a single-element ``candidates`` tuple.
    On failure the result carries ONE typed blocker describing the
    root cause (hash-malformed, identity-malformed, season-scope,
    date-coverage, destination, upstream-read-failure).  Multiple
    blockers are NOT combined — the FIRST failure is reported so the
    caller can disambiguate deterministically.

    The season identity check uses only the validated Task 9 v2 FK and
    canonical mirror. Missing request identity and every v1/NULL
    authority fail closed with
    ``reason=PERSISTED_FORECAST_SEASON_IDENTITY_UNAVAILABLE``.
    """

    from backend.app.agent.adapters.task_loaders import _SHA256_HEX_RE

    row_id = int(getattr(row, "id", 0) or 0)

    def _hash_malformed(field: str, value: Any) -> Blocker:
        return Blocker(
            code=BlockerCode.AUTHORITY_HASH_MALFORMED,
            message=(
                f"TASK-009 candidate row {row_id} has malformed "
                f"{field}: not a 64-char lowercase hex string"
            ),
            details={
                "field": field,
                "row_id": row_id,
                "value_kind": type(value).__name__,
            },
            retry_hint="WAIT_FOR_DATA",
        )

    def _identity_malformed(field: str, reason: str) -> Blocker:
        return Blocker(
            code=BlockerCode.AUTHORITY_IDENTITY_MALFORMED,
            message=(
                f"TASK-009 candidate row {row_id} is missing or has "
                f"a wrong-type identity field {field!r}: {reason}"
            ),
            details={"field": field, "row_id": row_id, "reason": reason},
            retry_hint="WAIT_FOR_DATA",
        )

    def _scope_mismatch(reason: str, extra: dict[str, Any] | None = None) -> Blocker:
        details: dict[str, Any] = {
            "authority": "TASK9_HARVEST_STATE_RUN",
            "row_id": row_id,
            "requested_effective_forecast_season_id": (
                int(effective_forecast_season_id)
                if effective_forecast_season_id is not None
                else None
            ),
            "persisted_season_identity": None,
            "reason": reason,
        }
        if extra:
            details.update(extra)
        return Blocker(
            code=BlockerCode.AUTHORITY_SCOPE_MISMATCH,
            message=(f"TASK-009 candidate row {row_id} fails scope check: {reason}"),
            details=details,
            retry_hint="FIX_INPUT",
        )

    # --- status ---
    # P0-1 (review 4680528194): ``status`` is a SCOPE property, NOT
    # an identity property.  A row with ``status != 'completed'``
    # (e.g. ``status='failed'``) is a scope/status mismatch, not
    # a malformed identity.  Classification changed from
    # :data:`BlockerCode.AUTHORITY_IDENTITY_MALFORMED` to
    # :data:`BlockerCode.AUTHORITY_SCOPE_MISMATCH` with
    # ``reason=EXECUTION_STATUS_NOT_COMPLETED``.  Identity-misformed
    # is reserved for "field is missing or has a wrong type" (see
    # the type-check below).
    status_value = getattr(row, "status", None)
    if status_value is None or not isinstance(status_value, str):
        return AuthoritySelectionResult(
            blockers=(_identity_malformed("status", "expected non-empty string"),)
        )
    if status_value != "completed":
        return AuthoritySelectionResult(
            blockers=(
                _scope_mismatch(
                    EXECUTION_STATUS_NOT_COMPLETED,
                    extra={
                        "row_status": str(status_value),
                        "expected_status": "completed",
                    },
                ),
            )
        )

    # --- destination_factory_id ---
    if destination_factory_id is not None:
        row_dest = getattr(row, "destination_factory_id", None)
        if row_dest is None or int(row_dest) != int(destination_factory_id):
            return AuthoritySelectionResult(
                blockers=(
                    _scope_mismatch(
                        DESTINATION_MISMATCH,
                        extra={
                            "row_destination_factory_id": (
                                int(row_dest) if row_dest is not None else None
                            ),
                            "requested_destination_factory_id": int(destination_factory_id),
                        },
                    ),
                )
            )

    # --- date coverage ---
    row_as_of = getattr(row, "as_of_date", None)
    row_end = getattr(row, "forecast_end_date", None)
    if not isinstance(row_as_of, date) or not isinstance(row_end, date):
        return AuthoritySelectionResult(
            blockers=(
                _identity_malformed(
                    "as_of_date" if not isinstance(row_as_of, date) else "forecast_end_date",
                    "expected datetime.date",
                ),
            )
        )
    if not (row_as_of <= as_of <= row_end):
        return AuthoritySelectionResult(
            blockers=(
                _scope_mismatch(
                    DATE_COVERAGE_MISMATCH,
                    extra={
                        "row_as_of_date": row_as_of.isoformat(),
                        "row_forecast_end_date": row_end.isoformat(),
                        "requested_as_of_date": as_of.isoformat(),
                    },
                ),
            )
        )

    # --- result_hash / config_hash ---
    result_hash = getattr(row, "result_hash", None)
    if not isinstance(result_hash, str) or not _SHA256_HEX_RE.match(result_hash):
        return AuthoritySelectionResult(blockers=(_hash_malformed("result_hash", result_hash),))
    config_hash = getattr(row, "config_hash", None)
    if not isinstance(config_hash, str) or not _SHA256_HEX_RE.match(config_hash):
        return AuthoritySelectionResult(blockers=(_hash_malformed("config_hash", config_hash),))

    # --- persisted v2 season identity ---
    persisted_season_id = getattr(row, "forecast_season_id", None)
    if effective_forecast_season_id is None:
        return AuthoritySelectionResult(
            blockers=(
                _scope_mismatch(
                    SEASON_BINDING_UNAVAILABLE,
                    extra={"persisted_forecast_season_id": persisted_season_id},
                ),
            )
        )
    season_blocker, persisted_season_id = await _validate_task9_v2_season_identity(
        session=session,
        row=row,
        row_id=row_id,
        requested_season_id=effective_forecast_season_id,
        scope_mismatch=_scope_mismatch,
        identity_malformed=_identity_malformed,
    )
    if season_blocker is not None:
        return AuthoritySelectionResult(blockers=(season_blocker,))

    # --- variety coverage ---
    if requested_variety_codes:
        try:
            covered = await _member_variety_codes_for_run(
                session=session, harvest_state_run_id=row_id
            )
        except Exception as exc:  # noqa: BLE001
            return AuthoritySelectionResult(
                blockers=(
                    Blocker(
                        code=BlockerCode.UPSTREAM_READ_FAILURE,
                        message=(
                            f"TASK-009 member-variety ORM query raised "
                            f"for row {row_id}: "
                            f"{type(exc).__name__}: {exc}"
                        ),
                        details={
                            "field": "member_variety_scope",
                            "row_id": row_id,
                        },
                        retry_hint="WAIT_FOR_DATA",
                    ),
                )
            )
        if not set(requested_variety_codes).issubset(covered):
            return AuthoritySelectionResult(
                blockers=(
                    Blocker(
                        code=BlockerCode.AUTHORITY_SCOPE_MISMATCH,
                        message=(
                            f"TASK-009 candidate row {row_id} member-row "
                            f"variety set does not cover the requested "
                            f"variety set."
                        ),
                        details={
                            "field": "member_variety_scope",
                            "row_id": row_id,
                            "requested_variety_codes": list(requested_variety_codes),
                            "persisted_variety_codes": sorted(covered),
                            "reason": MEMBER_VARIETY_SET_MISMATCH,
                        },
                        retry_hint="FIX_INPUT",
                    ),
                )
            )

    return AuthoritySelectionResult(
        candidates=(
            {
                "id": row_id,
                "result_hash": str(result_hash),
                "forecast_season_id": persisted_season_id,
            },
        )
    )


async def _validate_task9_v2_season_identity(
    *,
    session: AsyncSession,
    row: Any,
    row_id: int,
    requested_season_id: int,
    scope_mismatch: Any,
    identity_malformed: Any,
) -> tuple[Blocker | None, int | None]:
    """Validate the persisted Task 9 v2 season FK and canonical mirror."""
    from backend.app.harvest_state.enums import (
        OUTPUT_SCHEMA_VERSION_V1,
        OUTPUT_SCHEMA_VERSION_V2,
        RESULT_HASH_SCHEMA_VERSION_V1,
        RESULT_HASH_SCHEMA_VERSION_V2,
    )
    from backend.app.harvest_state.persistence import (
        HarvestStatePersistenceIntegrityError,
        HarvestStateSeasonRegistryDriftError,
        load_harvest_state_output_by_id,
    )

    output_version = getattr(row, "output_schema_version", None)
    result_version = getattr(row, "result_hash_schema_version", None)
    persisted_id = getattr(row, "forecast_season_id", None)
    if (
        output_version == OUTPUT_SCHEMA_VERSION_V1
        or result_version == RESULT_HASH_SCHEMA_VERSION_V1
        or persisted_id is None
    ):
        return (
            scope_mismatch(
                SEASON_BINDING_UNAVAILABLE,
                extra={"persisted_forecast_season_id": persisted_id},
            ),
            None,
        )
    if (
        output_version != OUTPUT_SCHEMA_VERSION_V2
        or result_version != RESULT_HASH_SCHEMA_VERSION_V2
    ):
        return (
            scope_mismatch(
                TASK9_SEASON_SCHEMA_UNSUPPORTED,
                extra={
                    "output_schema_version": output_version,
                    "result_hash_schema_version": result_version,
                },
            ),
            None,
        )
    if isinstance(persisted_id, bool) or not isinstance(persisted_id, int) or persisted_id <= 0:
        return identity_malformed("forecast_season_id", SEASON_IDENTITY_MALFORMED), None
    try:
        persisted_output = await load_harvest_state_output_by_id(session, run_id=row_id)
    except HarvestStateSeasonRegistryDriftError:
        return identity_malformed("forecast_season_id", SEASON_REGISTRY_DRIFT), None
    except HarvestStatePersistenceIntegrityError:
        return identity_malformed("forecast_season_id", SEASON_IDENTITY_CONFLICT), None
    except Exception:  # noqa: BLE001
        return (
            Blocker(
                code=BlockerCode.UPSTREAM_READ_FAILURE,
                message=f"TASK-009 integrity reload failed for row {row_id}",
                details={"field": "harvest_state_integrity_reload", "row_id": row_id},
                retry_hint="WAIT_FOR_DATA",
            ),
            None,
        )
    if persisted_output is None:
        return identity_malformed("forecast_season_id", SEASON_IDENTITY_MALFORMED), None
    nested_identity = persisted_output.input_snapshot.get("forecast_season_identity")
    nested_id = nested_identity.get("season_id") if isinstance(nested_identity, dict) else None
    if persisted_output.forecast_season_id != persisted_id or nested_id != persisted_id:
        return identity_malformed("forecast_season_id", SEASON_IDENTITY_CONFLICT), None
    if persisted_id != requested_season_id:
        return (
            scope_mismatch(
                FORECAST_SEASON_ID_MISMATCH,
                extra={
                    "persisted_forecast_season_id": persisted_id,
                    "requested_effective_forecast_season_id": requested_season_id,
                },
            ),
            None,
        )
    return None, persisted_id


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
) -> AuthoritySelectionResult:
    """Strict-scope TASK-010 selector.  No implicit latest.

    Bind to TASK-009 by ``task9_run_id`` AND ``task9_result_hash``.

    P0-3 (review 4680340321):

    * The default path now performs the SAME full identity / hash /
      execution-status / fallback / lineage validation as the
      override path.  Both paths share
      :func:`_evaluate_task10_row_against_scope` so a row that fails
      any check in one path also fails in the other.
    * When a candidate row is excluded, the typed-failure
      ``Blocker`` is returned (with ``reason=`` discriminator) — NOT
      a silent ``TASK10_AUTHORITY_NOT_FOUND`` collapse.

    Failure mode taxonomy (P0-3):

    * no base-scope row at all → :data:`BlockerCode.TASK10_AUTHORITY_NOT_FOUND`
    * row exists but ``execution_status != 'completed'`` →
      :data:`BlockerCode.AUTHORITY_SCOPE_MISMATCH`
      ``reason=EXECUTION_STATUS_NOT_COMPLETED``
    * row's ``task9_run_id`` or ``task9_result_hash`` does not bind
      to the selected TASK-009 lineage →
      :data:`BlockerCode.AUTHORITY_LINEAGE_MISMATCH`
    * any of ``prediction_hash`` / ``config_hash`` /
      ``prediction_input_signature`` / ``canonical_payload_hash`` /
      ``feature_schema_hash`` / ``artifact_hashes`` is malformed →
      :data:`BlockerCode.AUTHORITY_HASH_MALFORMED`
    * required identity column missing or wrong type →
      :data:`BlockerCode.AUTHORITY_IDENTITY_MALFORMED`
    * ``fallback_reason`` is set →
      :data:`BlockerCode.AUTHORITY_SCOPE_MISMATCH`
      ``reason=FALLBACK_RUN_NOT_AUTHORITATIVE`
    * ORM query raised an unexpected exception →
      :data:`BlockerCode.UPSTREAM_READ_FAILURE`
    * multiple fully-valid candidates → caller emits
      :data:`BlockerCode.AUTHORITY_CONFLICT` (not this function).
    """

    from backend.app.models.residual_model import ResidualModelPredictionRun

    # ---- Override path: validate the explicit run id -----------------
    if prediction_run_id_override is not None:
        try:
            row = await session.get(ResidualModelPredictionRun, int(prediction_run_id_override))
        except Exception as exc:  # noqa: BLE001
            return AuthoritySelectionResult(
                blockers=(
                    Blocker(
                        code=BlockerCode.UPSTREAM_READ_FAILURE,
                        message=(f"TASK-010 override read failed: {type(exc).__name__}: {exc}"),
                        details={
                            "field": "residual_prediction_run_override_read",
                            "prediction_run_id_override": int(prediction_run_id_override),
                        },
                        retry_hint="WAIT_FOR_DATA",
                    ),
                )
            )
        if row is None:
            return AuthoritySelectionResult(
                blockers=(
                    Blocker(
                        code=BlockerCode.TASK10_AUTHORITY_NOT_FOUND,
                        message=(
                            f"TASK-010 override run id "
                            f"{int(prediction_run_id_override)} does "
                            f"not exist."
                        ),
                        details={"prediction_run_id_override": int(prediction_run_id_override)},
                        retry_hint="WAIT_FOR_DATA",
                    ),
                )
            )
        return await _evaluate_task10_row_against_scope(
            row=row,
            task9_run_id=task9_run_id,
            task9_result_hash=task9_result_hash,
        )

    # ---- Default path: two-stage related-lineage query ----------
    # P0-2 (review 4680528194): the previous default path filtered
    # by exact ``task9_run_id == selected AND task9_result_hash ==
    # selected`` in the SQL ``WHERE`` clause.  A residual run that
    # exists but has a partial lineage mismatch (e.g. same run id
    # but different result hash, or different run id but same
    # result hash) was invisible to the shared validator and
    # collapsed to :data:`BlockerCode.TASK10_AUTHORITY_NOT_FOUND`.
    #
    # Stage A (related-lineage query): load any residual row that
    # shares AT LEAST ONE lineage component with the selected
    # TASK-009 — i.e. ``task9_run_id == selected`` OR
    # ``task9_result_hash == selected``.  This is the minimal
    # relation surface that lets the shared validator classify the
    # row's lineage (both components), execution status, hashes,
    # artifact hashes, and fallback reason uniformly.
    #
    # Stage B (shared validator): every related-lineage row is fed
    # through :func:`_evaluate_task10_row_against_scope`.  Rows
    # that pass are returned as candidates; rows that fail surface
    # their typed blockers.  The selector returns
    # ``TASK10_AUTHORITY_NOT_FOUND`` ONLY when no related-lineage
    # row exists at all.
    #
    # Determinism: no ``ORDER BY`` / ``LIMIT`` / implicit-latest
    # selection.  The composer's downstream ``len > 1`` dispatch
    # surfaces :data:`BlockerCode.AUTHORITY_CONFLICT` when more than
    # one row passes the validator.
    related_lineage_stmt = select(
        ResidualModelPredictionRun.id,
        ResidualModelPredictionRun.execution_status,
        ResidualModelPredictionRun.task9_run_id,
        ResidualModelPredictionRun.task9_result_hash,
        ResidualModelPredictionRun.prediction_hash,
        ResidualModelPredictionRun.config_hash,
        ResidualModelPredictionRun.prediction_input_signature,
        ResidualModelPredictionRun.canonical_payload_hash,
        ResidualModelPredictionRun.feature_schema_hash,
        ResidualModelPredictionRun.artifact_hashes,
        ResidualModelPredictionRun.fallback_reason,
    ).where(
        or_(
            ResidualModelPredictionRun.task9_run_id == int(task9_run_id),
            ResidualModelPredictionRun.task9_result_hash == str(task9_result_hash),
        )
    )
    try:
        rows = (await session.execute(related_lineage_stmt)).all()
    except Exception as exc:  # noqa: BLE001
        return AuthoritySelectionResult(
            blockers=(
                Blocker(
                    code=BlockerCode.UPSTREAM_READ_FAILURE,
                    message=(f"TASK-010 related-lineage read failed: {type(exc).__name__}: {exc}"),
                    details={"field": "residual_prediction_run_related_lineage"},
                    retry_hint="WAIT_FOR_DATA",
                ),
            )
        )

    if not rows:
        # No related-lineage row exists at all → this is the ONLY
        # case that legitimately emits
        # :data:`BlockerCode.TASK10_AUTHORITY_NOT_FOUND`.
        return AuthoritySelectionResult(
            blockers=(
                Blocker(
                    code=BlockerCode.TASK10_AUTHORITY_NOT_FOUND,
                    message=(
                        "No TASK-010 residual prediction run shares a "
                        "lineage component with the selected TASK-009 "
                        "run; cannot classify lineage / status / "
                        "identity without a candidate row to validate."
                    ),
                    details={
                        "task9_run_id": int(task9_run_id),
                        "task9_result_hash": str(task9_result_hash),
                    },
                    retry_hint="WAIT_FOR_DATA",
                ),
            )
        )

    candidate_dicts: list[dict[str, Any]] = []
    collected_blockers: list[Blocker] = []
    for r in rows:
        outcome = await _evaluate_task10_row_against_scope(
            row=r,
            task9_run_id=task9_run_id,
            task9_result_hash=task9_result_hash,
        )
        if outcome.candidates:
            candidate_dicts.extend(outcome.candidates)
        elif outcome.blockers:
            collected_blockers.extend(outcome.blockers)

    # P0-2 (review 4680912426): stable sort candidates and
    # blockers before returning.  Same total-order discipline as
    # the TASK-009 selector.
    candidate_dicts.sort(key=lambda c: int(c.get("id", 0) or 0))
    if candidate_dicts:
        return AuthoritySelectionResult(candidates=tuple(candidate_dicts))
    if collected_blockers:
        return AuthoritySelectionResult(
            blockers=tuple(_sort_blockers_deterministically(collected_blockers))
        )
    return AuthoritySelectionResult(
        blockers=(
            Blocker(
                code=BlockerCode.AUTHORITY_SCOPE_MISMATCH,
                message=(
                    "TASK-010 base-scope rows existed but all were "
                    "excluded by scope/identity checks; see aggregated "
                    "blockers for details."
                ),
                details={
                    "task9_run_id": int(task9_run_id),
                    "task9_result_hash": str(task9_result_hash),
                },
                retry_hint="FIX_INPUT",
            ),
        )
    )


async def _evaluate_task10_row_against_scope(
    *,
    row: Any,
    task9_run_id: int,
    task9_result_hash: str,
) -> AuthoritySelectionResult:
    """Validate a TASK-010 candidate row against the strict scope.

    Returns a discriminated :class:`AuthoritySelectionResult`.  On
    success the row appears as a single-element ``candidates`` tuple.
    On failure the result carries ONE typed blocker describing the
    root cause.  Multiple blockers are NOT combined.

    P0-3 (review 4680340321): the default and override paths share
    this function so a row that fails any check in one path also
    fails in the other.
    """

    from backend.app.agent.adapters.task_loaders import _SHA256_HEX_RE

    row_id = int(getattr(row, "id", 0) or 0)

    def _hash_malformed(field: str, value: Any) -> Blocker:
        return Blocker(
            code=BlockerCode.AUTHORITY_HASH_MALFORMED,
            message=(
                f"TASK-010 candidate row {row_id} has malformed "
                f"{field}: not a 64-char lowercase hex string"
            ),
            details={
                "field": field,
                "row_id": row_id,
                "value_kind": type(value).__name__,
            },
            retry_hint="WAIT_FOR_DATA",
        )

    def _identity_malformed(field: str, reason: str) -> Blocker:
        return Blocker(
            code=BlockerCode.AUTHORITY_IDENTITY_MALFORMED,
            message=(
                f"TASK-010 candidate row {row_id} is missing or has "
                f"a wrong-type identity field {field!r}: {reason}"
            ),
            details={"field": field, "row_id": row_id, "reason": reason},
            retry_hint="WAIT_FOR_DATA",
        )

    # --- execution_status ---
    execution_status = getattr(row, "execution_status", None)
    if not isinstance(execution_status, str) or execution_status != "completed":
        return AuthoritySelectionResult(
            blockers=(
                Blocker(
                    code=BlockerCode.AUTHORITY_SCOPE_MISMATCH,
                    message=(
                        f"TASK-010 candidate row {row_id} has "
                        f"execution_status={execution_status!r}, "
                        f"expected 'completed'"
                    ),
                    details={
                        "field": "execution_status",
                        "row_id": row_id,
                        "value": execution_status,
                        "reason": EXECUTION_STATUS_NOT_COMPLETED,
                    },
                    retry_hint="WAIT_FOR_DATA",
                ),
            )
        )

    # --- lineage: task9_run_id / task9_result_hash ---
    row_task9_run_id = getattr(row, "task9_run_id", None)
    if row_task9_run_id is None or int(row_task9_run_id) != int(task9_run_id):
        return AuthoritySelectionResult(
            blockers=(
                Blocker(
                    code=BlockerCode.AUTHORITY_LINEAGE_MISMATCH,
                    message=(
                        f"TASK-010 candidate row {row_id} task9_run_id "
                        f"does not bind to the selected TASK-009 run."
                    ),
                    details={
                        "field": "task9_run_id",
                        "row_id": row_id,
                        "row_task9_run_id": (
                            int(row_task9_run_id) if row_task9_run_id is not None else None
                        ),
                        "selected_task9_run_id": int(task9_run_id),
                    },
                    retry_hint="FIX_INPUT",
                ),
            )
        )
    row_task9_result_hash = getattr(row, "task9_result_hash", None)
    if not isinstance(row_task9_result_hash, str) or row_task9_result_hash != str(
        task9_result_hash
    ):
        return AuthoritySelectionResult(
            blockers=(
                Blocker(
                    code=BlockerCode.AUTHORITY_LINEAGE_MISMATCH,
                    message=(
                        f"TASK-010 candidate row {row_id} "
                        f"task9_result_hash does not bind to the "
                        f"selected TASK-009 result hash."
                    ),
                    details={
                        "field": "task9_result_hash",
                        "row_id": row_id,
                        "row_task9_result_hash": row_task9_result_hash,
                        "selected_task9_result_hash": str(task9_result_hash),
                    },
                    retry_hint="FIX_INPUT",
                ),
            )
        )

    # --- full identity: prediction_hash, config_hash, etc. ---
    def _strict_hex(value: Any, field: str) -> str | None:
        if not isinstance(value, str) or not _SHA256_HEX_RE.match(value):
            return None
        return value

    for field_name in (
        "prediction_hash",
        "config_hash",
        "prediction_input_signature",
        "canonical_payload_hash",
        "feature_schema_hash",
    ):
        v = getattr(row, field_name, None)
        if _strict_hex(v, field_name) is None:
            return AuthoritySelectionResult(blockers=(_hash_malformed(field_name, v),))

    artifact_hashes = getattr(row, "artifact_hashes", None)
    if artifact_hashes is None:
        return AuthoritySelectionResult(
            blockers=(
                _identity_malformed(
                    "artifact_hashes",
                    "expected a list of 64-char lowercase hex strings",
                ),
            )
        )
    if not isinstance(artifact_hashes, (list, tuple)):
        return AuthoritySelectionResult(
            blockers=(
                _identity_malformed(
                    "artifact_hashes",
                    f"expected list/tuple, got {type(artifact_hashes).__name__}",
                ),
            )
        )
    for h in artifact_hashes:
        if not isinstance(h, str) or not _SHA256_HEX_RE.match(h):
            return AuthoritySelectionResult(blockers=(_hash_malformed("artifact_hashes[]", h),))

    # --- fallback_reason disqualifies the run ---
    fallback_reason = getattr(row, "fallback_reason", None)
    if fallback_reason is not None:
        return AuthoritySelectionResult(
            blockers=(
                Blocker(
                    code=BlockerCode.AUTHORITY_SCOPE_MISMATCH,
                    message=(
                        f"TASK-010 candidate row {row_id} carries a "
                        f"fallback_reason; not authoritative."
                    ),
                    details={
                        "field": "fallback_reason",
                        "row_id": row_id,
                        "value": str(fallback_reason),
                        "reason": FALLBACK_RUN_NOT_AUTHORITATIVE,
                    },
                    retry_hint="WAIT_FOR_DATA",
                ),
            )
        )

    return AuthoritySelectionResult(
        candidates=(
            {
                "id": row_id,
                "task9_run_id": int(task9_run_id),
                "task9_result_hash": str(task9_result_hash),
            },
        )
    )


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

    P0-4 / P0-5 (review 4680340321) — three strict phases:

    **Phase 1: matrix prevalidation.**  For every requested variety ×
    P50/P80/P90 × target date, verify a real member row exists BEFORE
    any :class:`VarietyContribution` is created.  A later variety
    missing P90 MUST NOT silently drop the earlier variety's
    contribution (the round-7 "late missing grain" defect).  The
    matrix MUST be complete before phase 2 starts.

    **Phase 2: denominator scope.**  The persisted member-variety
    set for the selected TASK-009 run MUST equal the requested
    variety set (exact).  An extra persisted variety with non-zero
    volume is a scope mismatch
    (reason=TASK9_MEMBER_VARIETY_SET_MISMATCH) — no
    mixed-semantic denominator / requested-only output truncation.

    **Phase 3: compute + reconcile.**  Build contributions, validate
    per-quantile:

    * sum(member_v) over requested varieties == pool arrival total
    * pool_total > 0 → sum(emitted rates) == 1
    * pool_total == 0 → all member volumes == 0

    Any reconciliation failure returns ``[]`` + typed blockers
    (never partial contribution).  All grain / reconciliation
    blockers carry ``task9_run_id`` + ``date`` + ``quantile`` +
    ``variety_id`` (where applicable).
    """

    if not varieties:
        return [], []

    task9_run_id_value: int | None = int(task9_run_id) if task9_run_id is not None else None

    # ----- Phase 1: matrix prevalidation -------------------------------
    # Build a per-(date, quantile) view of the persisted member rows.
    member_by_q: dict[str, dict[int, Decimal]] = {"P50": {}, "P80": {}, "P90": {}}
    for (md, q, member_variety_pk), arrival_kg in variety_member_rows.items():
        if md != d:
            continue
        if q not in member_by_q:
            continue
        member_by_q[q].setdefault(int(member_variety_pk), Decimal("0"))
        member_by_q[q][int(member_variety_pk)] += Decimal(arrival_kg)

    # Resolve string variety code -> int PK.  Emit a typed
    # UNKNOWN_VARIETY blocker (with task9_run_id) and surface the
    # whole-day fail-closed verdict (no partial contribution).
    requested_variety_pks: list[int] = []
    requested_variety_codes: list[str] = []
    unknown_blockers: list[Blocker] = []
    for v in varieties:
        vid_code = str(v.variety_id)
        vid_pk = variety_pk_by_code.get(vid_code)
        if vid_pk is None:
            unknown_blockers.append(
                Blocker(
                    code=BlockerCode.UNKNOWN_VARIETY,
                    message=(
                        f"variety code {vid_code!r} not present in Variety "
                        f"catalog; per-variety grain is unavailable."
                    ),
                    details={
                        "variety_id": vid_code,
                        "date": d.isoformat(),
                        "task9_run_id": task9_run_id_value,
                    },
                    retry_hint="FIX_INPUT",
                )
            )
            continue
        requested_variety_pks.append(int(vid_pk))
        requested_variety_codes.append(vid_code)
    if unknown_blockers:
        # Whole-day fail-closed: any unknown variety excludes ALL
        # contributions for this date.
        return [], unknown_blockers

    # Persisted member-variety set for THIS date.
    persisted_pks_for_date: set[int] = set()
    for q in ("P50", "P80", "P90"):
        persisted_pks_for_date.update(member_by_q[q].keys())

    requested_pks_set: set[int] = set(requested_variety_pks)

    # Phase 1 check 1: NO member rows at all for this date — emit
    # one blocker carrying the real task9_run_id + date.
    if not persisted_pks_for_date:
        return [], [
            Blocker(
                code=BlockerCode.TASK9_PER_VARIETY_GRAIN_MISSING,
                message=(
                    f"No HarvestStateDailyMemberRowModel rows available "
                    f"for date {d.isoformat()}; per-variety grain is missing."
                ),
                details={
                    "date": d.isoformat(),
                    "task9_run_id": task9_run_id_value,
                },
                retry_hint="WAIT_FOR_DATA",
            )
        ]

    # Phase 1 check 2: every requested variety × P50/P80/P90 must have
    # a real member row BEFORE any contribution is created.
    phase1_blockers: list[Blocker] = []
    for vid_code, vid_pk in zip(requested_variety_codes, requested_variety_pks, strict=True):
        for q in ("P50", "P80", "P90"):
            if int(vid_pk) not in member_by_q[q]:
                phase1_blockers.append(
                    Blocker(
                        code=BlockerCode.TASK9_PER_VARIETY_GRAIN_MISSING,
                        message=(
                            f"per-variety grain missing for date="
                            f"{d.isoformat()} variety={vid_code} "
                            f"quantile={q} task9_run_id={task9_run_id_value}"
                        ),
                        details={
                            "date": d.isoformat(),
                            "quantile": q,
                            "variety_id": vid_code,
                            "task9_run_id": task9_run_id_value,
                        },
                        retry_hint="WAIT_FOR_DATA",
                    )
                )
    if phase1_blockers:
        # Whole-day fail-closed: any missing-grain cell excludes ALL
        # contributions for this date (no partial Dx output).
        return [], phase1_blockers

    # ----- Phase 2: denominator scope (exact match) --------------------
    # Persisted member-variety set for this date MUST equal the
    # requested set.  An extra persisted variety (even with volume
    # zero) is a scope mismatch.  Per round 8: "do not depend on the
    # extra variety's volume being zero".
    if persisted_pks_for_date != requested_pks_set:
        return [], [
            Blocker(
                code=BlockerCode.AUTHORITY_SCOPE_MISMATCH,
                message=(
                    f"TASK-009 member-variety set for date "
                    f"{d.isoformat()} does not exactly match the "
                    f"requested variety set."
                ),
                details={
                    "task9_run_id": task9_run_id_value,
                    "date": d.isoformat(),
                    "requested_variety_ids": requested_variety_codes,
                    "persisted_variety_ids": sorted(
                        variety_pk_by_code_inv(persisted_pks_for_date, variety_pk_by_code)
                    ),
                    "reason": MEMBER_VARIETY_SET_MISMATCH,
                },
                retry_hint="FIX_INPUT",
            )
        ]

    # ----- Phase 3: compute contributions + reconcile ------------------
    contributions: list[VarietyContribution] = []
    per_variety_data: dict[str, dict[str, Decimal]] = {}

    for vid_code, vid_pk in zip(requested_variety_codes, requested_variety_pks, strict=True):
        per_quantile_volume: dict[str, Decimal] = {}
        per_quantile_rate: dict[str, Decimal] = {}
        per_quantile_total: dict[str, Decimal] = {}
        for q in ("P50", "P80", "P90"):
            pool_total = _d(pool_arrival.get(f"{q}_arrival", Decimal("0")))
            member_v = _d(member_by_q[q].get(int(vid_pk), Decimal("0")))
            if pool_total > 0:
                rate = member_v / pool_total
            else:
                rate = Decimal("0")
            per_quantile_volume[q] = member_v
            per_quantile_rate[q] = rate
            per_quantile_total[q] = pool_total
        per_variety_data[vid_code] = {
            **{f"volume_{q}": per_quantile_volume[q] for q in ("P50", "P80", "P90")},
            **{f"rate_{q}": per_quantile_rate[q] for q in ("P50", "P80", "P90")},
        }

    # Reconciliation per quantile.  pool_total > 0 → sum(emitted
    # rates) must equal 1 (Decimal, exact).  pool_total == 0 → all
    # member volumes must be 0.  Failure -> whole-day fail-closed.
    reconciliation_blockers: list[Blocker] = []
    for q in ("P50", "P80", "P90"):
        pool_total = _d(pool_arrival.get(f"{q}_arrival", Decimal("0")))
        sum_member_volume = sum(
            per_variety_data[code][f"volume_{q}"] for code in requested_variety_codes
        )
        if pool_total > 0 and sum_member_volume != pool_total:
            reconciliation_blockers.append(
                Blocker(
                    code=BlockerCode.TASK9_PER_VARIETY_GRAIN_MISSING,
                    message=(
                        f"member volume sum reconciliation failure for "
                        f"date={d.isoformat()} quantile={q}: "
                        f"sum_member={sum_member_volume} != "
                        f"pool_total={pool_total} task9_run_id="
                        f"{task9_run_id_value}"
                    ),
                    details={
                        "date": d.isoformat(),
                        "quantile": q,
                        "sum_member_volume": format(sum_member_volume, "f"),
                        "pool_total": format(pool_total, "f"),
                        "task9_run_id": task9_run_id_value,
                    },
                    retry_hint="WAIT_FOR_DATA",
                )
            )
        elif pool_total == 0 and sum_member_volume != 0:
            reconciliation_blockers.append(
                Blocker(
                    code=BlockerCode.TASK9_PER_VARIETY_GRAIN_MISSING,
                    message=(
                        f"member volume non-zero with zero pool total "
                        f"for date={d.isoformat()} quantile={q}: "
                        f"sum_member={sum_member_volume} pool_total=0 "
                        f"task9_run_id={task9_run_id_value}"
                    ),
                    details={
                        "date": d.isoformat(),
                        "quantile": q,
                        "sum_member_volume": format(sum_member_volume, "f"),
                        "pool_total": "0",
                        "task9_run_id": task9_run_id_value,
                    },
                    retry_hint="WAIT_FOR_DATA",
                )
            )
        elif pool_total > 0:
            sum_rates = sum(per_variety_data[code][f"rate_{q}"] for code in requested_variety_codes)
            if sum_rates != Decimal("1"):
                reconciliation_blockers.append(
                    Blocker(
                        code=BlockerCode.TASK9_PER_VARIETY_GRAIN_MISSING,
                        message=(
                            f"emitted contribution-rate sum != 1 for "
                            f"date={d.isoformat()} quantile={q}: "
                            f"sum_rate={sum_rates} task9_run_id="
                            f"{task9_run_id_value}"
                        ),
                        details={
                            "date": d.isoformat(),
                            "quantile": q,
                            "sum_rates": format(sum_rates, "f"),
                            "pool_total": format(pool_total, "f"),
                            "task9_run_id": task9_run_id_value,
                        },
                        retry_hint="WAIT_FOR_DATA",
                    )
                )
    if reconciliation_blockers:
        # Whole-day fail-closed.
        return [], reconciliation_blockers

    # All phases passed — emit the contributions.
    for vid_code in requested_variety_codes:
        data = per_variety_data[vid_code]
        contributions.append(
            VarietyContribution(
                variety_id=vid_code,
                volume_kg_p50=_ds(data["volume_P50"]),
                volume_kg_p80=_ds(data["volume_P80"]),
                volume_kg_p90=_ds(data["volume_P90"]),
                contribution_rate_p50=_ds(data["rate_P50"]),
                contribution_rate_p80=_ds(data["rate_P80"]),
                contribution_rate_p90=_ds(data["rate_P90"]),
            )
        )

    return contributions, []


def variety_pk_by_code_inv(
    persisted_pks: set[int],
    variety_pk_by_code: dict[str, int],
) -> list[str]:
    """Reverse map a set of variety PKs to their string codes.

    PKs that are not present in the catalog are returned as their
    string form ``"pk:<n>"`` so the blocker detail stays deterministic
    without losing information.
    """

    code_by_pk: dict[int, str] = {pk: code for code, pk in variety_pk_by_code.items()}
    out: list[str] = []
    for pk in sorted(persisted_pks):
        out.append(code_by_pk.get(int(pk), f"pk:{int(pk)}"))
    return out


__all__ = [
    "DefaultTaskCompositionBaseline",
    "BaselineCompositionResult",
    "AuthoritySelectionResult",
    "UpstreamReadFailure",
    "SEASON_BINDING_UNAVAILABLE",
    "FALLBACK_RUN_NOT_AUTHORITATIVE",
    "MEMBER_VARIETY_SET_MISMATCH",
    "EXECUTION_STATUS_NOT_COMPLETED",
    "DESTINATION_MISMATCH",
    "DATE_COVERAGE_MISMATCH",
]
