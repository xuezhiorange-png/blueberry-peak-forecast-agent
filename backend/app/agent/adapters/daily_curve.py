"""TASK-013 Slice A — ``forecast_daily_curve`` deterministic adapter.

This adapter composes a per-day forecast row by reading from the existing
TASK-008 / TASK-009 / TASK-010 services via injected ports.  It does NOT
introduce a new numerical algorithm; every authoritative quantity on a
``ForecastDailyRow`` is sourced from upstream services.

Hard rules enforced:

* uses typed authority envelopes (per ``Task8Authority`` / ``Task9Authority``
  / ``Task10Authority`` / ``Task11Authority`` / ``Task12Authority``);
* rejects cross-run identity mismatch — if an explicit
  ``TASK8_FORECAST_RUN`` etc. override is supplied but the loaded authority
  envelope reports a different ``*_run_id``, a ``CITATION_HASH_MISMATCH``
  blocker is raised and the run is NOT substituted;
* never substitutes a different run (no silent fallback);
* preserves P50 / P80 / P90 independently via :class:`DailyQuantiles`;
* authoritative quantities are canonical decimal strings;
* units are kg;
* per-variety contributions are quantile-bearing (one
  :class:`VarietyContribution` per variety per row);
* TASK-012 is absent unless an explicit ``TASK12_PREDICTION_RUN`` override
  is supplied (§22.1);
* no TASK-012 POST path;
* produces deterministic ``agent_daily_row_hash`` (per row) and
  ``agent_daily_curve_hash`` (over all rows).

**Single-source authority envelope discipline (P0-5)**

The :class:`DefaultDailyCurveAdapter` consumes the
:class:`BaselineCompositionResult` returned by the baseline composer and
populates the typed ``task8_authority`` / ``task9_authority`` /
``task10_authority`` envelopes using the EXACT run IDs selected by the
composer.  No second-query drift: the adapter never re-runs the
selector to "discover" the run IDs.

Slice A does not implement any new maturity, inventory, backlog, arrival,
residual, or weather formula.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agent.adapters.baseline_composer import (
    DefaultTaskCompositionBaseline,
)
from backend.app.agent.adapters.task_loaders import AuthorityLoadResult
from backend.app.agent.canonical import sha256_payload
from backend.app.agent.enums import BlockerCode, ForecastQuantile
from backend.app.agent.ports import (
    ScenarioBaselinePort,
    Task8ForecastPort,
    Task9HarvestStatePort,
    Task10PredictionPort,
    Task11BacktestPort,
    Task12PredictionPort,
)
from backend.app.agent.schemas import (
    AdvancedOverrides,
    AuthorityOverrideUnion,
    Blocker,
    ForecastDailyCurveInput,
    ForecastDailyCurveOutput,
    ForecastDailyRow,
)

QUANTILES: tuple[ForecastQuantile, ...] = ("P50", "P80", "P90")
QUANTILE_FIELD: dict[ForecastQuantile, str] = {"P50": "p50", "P80": "p80", "P90": "p90"}


def _to_decimal(value: str | Decimal | int | float | None) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _to_decimal_string(value: Any) -> str:
    return format(_to_decimal(value), "f")


def _select_authority_overrides(
    overrides: AdvancedOverrides | None,
    target: str,
) -> list[AuthorityOverrideUnion]:
    if overrides is None:
        return []
    return [o for o in overrides.authority_overrides if o.target == target]


# --- Top-level adapter ----------------------------------------------------


class DefaultDailyCurveAdapter:
    """Default ``forecast_daily_curve`` deterministic adapter."""

    def __init__(
        self,
        *,
        task8: Task8ForecastPort | None = None,
        task9: Task9HarvestStatePort | None = None,
        task10: Task10PredictionPort | None = None,
        task11: Task11BacktestPort | None = None,
        task12: Task12PredictionPort | None = None,
        baseline: ScenarioBaselinePort | None = None,
    ) -> None:
        from backend.app.agent.adapters.task_loaders import (
            DefaultTask8ForecastPort,
            DefaultTask9HarvestStatePort,
            DefaultTask10PredictionPort,
            DefaultTask11BacktestPort,
            DefaultTask12PredictionPort,
        )

        self._task8 = task8 or DefaultTask8ForecastPort()
        self._task9 = task9 or DefaultTask9HarvestStatePort()
        self._task10 = task10 or DefaultTask10PredictionPort()
        self._task11 = task11 or DefaultTask11BacktestPort()
        self._task12 = task12 or DefaultTask12PredictionPort()
        self._baseline = baseline or DefaultTaskCompositionBaseline()

    async def execute(
        self,
        session: AsyncSession,
        *,
        input: ForecastDailyCurveInput,
    ) -> ForecastDailyCurveOutput:
        nr = input.normalized_request
        overrides = input.advanced_overrides or nr.advanced_overrides
        blockers: list[Blocker] = []

        # --- Baseline composition: selects TASK-008/009/010 ONCE ----------
        composition = await self._baseline.compute_baseline(
            session=session,
            normalized_request=nr,
            resolved_location=input.resolved_location,
            parameters=input.parameters,
            advanced_overrides=overrides,
        )
        blockers.extend(composition.blockers)

        # --- TASK-008 envelope: use the composer-selected run_id ------------
        # Round 6: P0-1 — must use load_typed() so that typed blockers
        # propagate.  Required authority envelope for daily curve output.
        task8_authority: Any = None
        if composition.task8_run_id is not None:
            task8_overrides = _select_authority_overrides(overrides, "TASK8_FORECAST_RUN")
            if task8_overrides:
                expected_id = int(task8_overrides[0].value)
            else:
                expected_id = int(composition.task8_run_id)
            t8_result: AuthorityLoadResult[Any] = await self._task8.load_typed(
                session=session,
                forecast_run_id=expected_id,
            )
            blockers.extend(t8_result.blockers)
            if t8_result.authority is not None:
                if int(t8_result.authority.maturity_forecast_run_id) != expected_id:
                    blockers.append(
                        Blocker(
                            code=BlockerCode.CITATION_HASH_MISMATCH,
                            message=(
                                "TASK-008 envelope forecast_run_id does not match "
                                "the composer-selected run id."
                            ),
                            details={"override_value": expected_id},
                            retry_hint="FIX_INPUT",
                        )
                    )
                else:
                    task8_authority = t8_result.authority
            # Required authority: if load failed the row MUST be cleared.
            elif composition.task8_run_id is not None and not _has_lineage_mismatch_blocker(
                t8_result.blockers
            ):
                # Composition selected a TASK-008 run but loader failed — required.
                # Blockers are already attached; the per-day rows will be
                # cleared below by the required-authority check.
                pass

        # --- TASK-009 envelope: use the composer-selected run_id ------------
        task9_authority: Any = None
        if composition.task9_run_id is not None:
            task9_overrides = _select_authority_overrides(overrides, "TASK9_HARVEST_STATE_RUN")
            expected_id = (
                int(task9_overrides[0].value) if task9_overrides else int(composition.task9_run_id)
            )
            t9_result: AuthorityLoadResult[Any] = await self._task9.load_typed(
                session=session,
                harvest_state_run_id=expected_id,
            )
            blockers.extend(t9_result.blockers)
            if t9_result.authority is not None:
                if int(t9_result.authority.harvest_state_run_id) != expected_id:
                    blockers.append(
                        Blocker(
                            code=BlockerCode.CITATION_HASH_MISMATCH,
                            message=(
                                "TASK-009 envelope harvest_state_run_id does not "
                                "match the composer-selected run id."
                            ),
                            details={"override_value": expected_id},
                            retry_hint="FIX_INPUT",
                        )
                    )
                else:
                    task9_authority = t9_result.authority

        # --- TASK-010 envelope: use the composer-selected prediction_run_id -
        task10_authority: Any = None
        if composition.task10_prediction_run_id is not None:
            task10_overrides = _select_authority_overrides(overrides, "TASK10_PREDICTION_RUN")
            expected_id = (
                int(task10_overrides[0].value)
                if task10_overrides
                else int(composition.task10_prediction_run_id)
            )
            t10_result: AuthorityLoadResult[Any] = await self._task10.load_typed(
                session=session,
                prediction_run_id=expected_id,
            )
            blockers.extend(t10_result.blockers)
            if t10_result.authority is not None:
                if int(t10_result.authority.prediction_run_id) != expected_id:
                    blockers.append(
                        Blocker(
                            code=BlockerCode.CITATION_HASH_MISMATCH,
                            message=(
                                "TASK-010 envelope prediction_run_id does not "
                                "match the composer-selected run id."
                            ),
                            details={"override_value": expected_id},
                            retry_hint="FIX_INPUT",
                        )
                    )
                else:
                    task10_authority = t10_result.authority

        # --- TASK-011 / TASK-012 envelopes: explicit override only ----------
        # Round 6: P0-1 — when override is supplied, use load_typed() so that
        # typed blockers (hash_malformed, policy_version_missing, etc.) are
        # preserved.  Required only when the override is supplied.
        task11_authority: Any = None
        task11_overrides = _select_authority_overrides(overrides, "TASK11_BACKTEST_RUN")
        if task11_overrides:
            task11_overridden_id = int(task11_overrides[0].value)
            t11_result: AuthorityLoadResult[Any] = await self._task11.load_typed(
                session=session,
                rolling_backtest_run_id=task11_overridden_id,
            )
            blockers.extend(t11_result.blockers)
            if t11_result.authority is not None:
                task11_authority = t11_result.authority
            elif not t11_result.blockers:
                blockers.append(
                    Blocker(
                        code=BlockerCode.TASK11_AUTHORITY_NOT_FOUND,
                        message=("TASK-011 override supplied but the loader returned None."),
                        details={"override_value": task11_overridden_id},
                        retry_hint="WAIT_FOR_DATA",
                    )
                )

        task12_authority: Any = None
        task12_overrides = _select_authority_overrides(overrides, "TASK12_PREDICTION_RUN")
        if task12_overrides:
            task12_overridden_id = int(task12_overrides[0].value)
            t12_result: AuthorityLoadResult[Any] = await self._task12.load_typed(
                session=session,
                prediction_run_id=task12_overridden_id,
            )
            blockers.extend(t12_result.blockers)
            if t12_result.authority is not None:
                task12_authority = t12_result.authority
            elif not t12_result.blockers:
                blockers.append(
                    Blocker(
                        code=BlockerCode.TASK12_AUTHORITY_NOT_FOUND,
                        message=("TASK-012 override supplied but the loader returned None."),
                        details={"override_value": task12_overridden_id},
                        retry_hint="WAIT_FOR_DATA",
                    )
                )

        # --- Required-authority check: clear per-day rows on any
        # TASK-008/009/010 typed failure so the curve cannot be returned
        # with a partial / orphan authority envelope set. ----------------
        required_authority_failed = (
            (composition.task8_run_id is not None and task8_authority is None)
            or (composition.task9_run_id is not None and task9_authority is None)
            or (composition.task10_prediction_run_id is not None and task10_authority is None)
        )
        if required_authority_failed:
            composition_rows: list[ForecastDailyRow] = []
        else:
            composition_rows = composition.rows

        # --- Compose per-day rows + hashes -----------------------------------
        rows: list[ForecastDailyRow] = []
        for row in composition_rows:
            row_hash = _row_hash(row)
            rows.append(row.model_copy(update={"agent_daily_row_hash": row_hash}))

        curve_hash_payload = {
            "request_id": nr.request_id,
            "effective_as_of_date": str(nr.effective_as_of_date),
            "per_day": [
                {
                    "date": str(r.date),
                    "agent_daily_row_hash": r.agent_daily_row_hash,
                    "final_corrected_arrival_quantity_kg": {
                        "p50": r.final_corrected_arrival_quantity_kg.p50,
                        "p80": r.final_corrected_arrival_quantity_kg.p80,
                        "p90": r.final_corrected_arrival_quantity_kg.p90,
                    },
                }
                for r in rows
            ],
        }
        curve_hash = sha256_payload(curve_hash_payload)

        return ForecastDailyCurveOutput(
            per_day=rows,
            task8_authority=task8_authority,
            task9_authority=task9_authority,
            task10_authority=task10_authority,
            task11_authority=task11_authority,
            task12_authority=task12_authority,
            agent_daily_curve_hash=curve_hash,
            blockers=blockers,
        )


def _has_lineage_mismatch_blocker(blockers: tuple[Any, ...]) -> bool:
    """Return True iff the loader blockers contain a lineage-mismatch marker.

    Used by the daily-curve adapter to decide whether a failed required
    authority is "expected" (an override-mismatch) or "unexpected"
    (genuine NOT_FOUND / integrity failure).  When the override id does not
    match the row, the lineage blocker is the *only* blocker; the row
    itself is intact under the composer-selected id, and we do not want
    to "fail closed" the entire daily curve on override-mismatch alone —
    the composer-selected id is the source of truth.
    """
    for b in blockers:
        code = getattr(b, "code", None)
        if code == BlockerCode.AUTHORITY_LINEAGE_MISMATCH:
            return True
    return False


def _row_hash(row: ForecastDailyRow) -> str:
    payload = {
        "date": str(row.date),
        "natural_maturity_quantity_kg": {
            "p50": row.natural_maturity_quantity_kg.p50,
            "p80": row.natural_maturity_quantity_kg.p80,
            "p90": row.natural_maturity_quantity_kg.p90,
        },
        "harvested_quantity_kg": {
            "p50": row.harvested_quantity_kg.p50,
            "p80": row.harvested_quantity_kg.p80,
            "p90": row.harvested_quantity_kg.p90,
        },
        "closing_mature_inventory_kg": {
            "p50": row.closing_mature_inventory_kg.p50,
            "p80": row.closing_mature_inventory_kg.p80,
            "p90": row.closing_mature_inventory_kg.p90,
        },
        "unharvested_backlog_kg": {
            "p50": row.unharvested_backlog_kg.p50,
            "p80": row.unharvested_backlog_kg.p80,
            "p90": row.unharvested_backlog_kg.p90,
        },
        "arrival_quantity_kg": {
            "p50": row.arrival_quantity_kg.p50,
            "p80": row.arrival_quantity_kg.p80,
            "p90": row.arrival_quantity_kg.p90,
        },
        "final_corrected_arrival_quantity_kg": {
            "p50": row.final_corrected_arrival_quantity_kg.p50,
            "p80": row.final_corrected_arrival_quantity_kg.p80,
            "p90": row.final_corrected_arrival_quantity_kg.p90,
        },
        "per_variety_contribution": [
            {
                "variety_id": c.variety_id,
                "volume_kg_p50": c.volume_kg_p50,
                "volume_kg_p80": c.volume_kg_p80,
                "volume_kg_p90": c.volume_kg_p90,
                "contribution_rate_p50": c.contribution_rate_p50,
                "contribution_rate_p80": c.contribution_rate_p80,
                "contribution_rate_p90": c.contribution_rate_p90,
            }
            for c in row.per_variety_contribution
        ],
        "weather_tags": list(row.weather_tags),
        "spring_festival_phase": row.spring_festival_phase,
    }
    return sha256_payload(payload)


__all__ = ["DefaultDailyCurveAdapter"]
