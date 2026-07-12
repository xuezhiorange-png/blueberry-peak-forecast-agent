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

Slice A does not implement any new maturity, inventory, backlog, arrival,
residual, or weather formula.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

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
    AuthorityOverride,
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


def _zero_quantiles() -> dict[ForecastQuantile, Decimal]:
    return {q: Decimal("0") for q in QUANTILES}


def _select_authority_overrides(
    overrides: AdvancedOverrides | None,
    target: str,
) -> list[AuthorityOverride]:
    if overrides is None:
        return []
    return [o for o in overrides.authority_overrides if o.target == target]


# --- Default upstream ports -----------------------------------------------


class _NoopTaskPort:
    """Default task port: no row exists, returns ``None`` (no fabricated identity)."""

    async def load_by_id(self, *, session: AsyncSession, **kwargs: Any) -> None:
        return None


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
        self._task8 = task8 or _NoopTaskPort()
        self._task9 = task9 or _NoopTaskPort()
        self._task10 = task10 or _NoopTaskPort()
        self._task11 = task11 or _NoopTaskPort()
        self._task12 = task12 or _NoopTaskPort()
        self._baseline = baseline or _NoopScenarioBaseline()

    async def execute(
        self,
        session: AsyncSession,
        *,
        input: ForecastDailyCurveInput,
    ) -> ForecastDailyCurveOutput:
        nr = input.normalized_request
        overrides = input.advanced_overrides or nr.advanced_overrides
        blockers: list[Blocker] = []

        # --- TASK-008 --------------------------------------------------------
        task8_authority = None
        task8_overrides = _select_authority_overrides(overrides, "TASK8_FORECAST_RUN")
        if task8_overrides:
            task8_authority = await self._task8.load_by_id(
                session=session,
                forecast_run_id=int(task8_overrides[0].value),
            )
            if task8_authority is None or int(task8_authority.maturity_forecast_run_id) != int(
                task8_overrides[0].value
            ):
                blockers.append(
                    Blocker(
                        code=BlockerCode.CITATION_HASH_MISMATCH,
                        message=(
                            "TASK-008 authority override supplied but the loaded envelope "
                            "maturity_forecast_run_id does not match the override value."
                        ),
                        details={"override_value": int(task8_overrides[0].value)},
                        retry_hint="FIX_INPUT",
                    )
                )

        # --- TASK-009 --------------------------------------------------------
        task9_authority = None
        task9_overrides = _select_authority_overrides(overrides, "TASK9_HARVEST_STATE_RUN")
        if task9_overrides:
            task9_authority = await self._task9.load_by_id(
                session=session,
                harvest_state_run_id=int(task9_overrides[0].value),
            )
            if task9_authority is None or int(task9_authority.harvest_state_run_id) != int(
                task9_overrides[0].value
            ):
                blockers.append(
                    Blocker(
                        code=BlockerCode.CITATION_HASH_MISMATCH,
                        message=(
                            "TASK-009 authority override supplied but the loaded envelope "
                            "harvest_state_run_id does not match the override value."
                        ),
                        details={"override_value": int(task9_overrides[0].value)},
                        retry_hint="FIX_INPUT",
                    )
                )

        # --- TASK-010 --------------------------------------------------------
        task10_authority = None
        task10_overrides = _select_authority_overrides(overrides, "TASK10_PREDICTION_RUN")
        if task10_overrides:
            task10_authority = await self._task10.load_by_id(
                session=session,
                prediction_run_id=int(task10_overrides[0].value),
            )
            if task10_authority is None or int(task10_authority.prediction_run_id) != int(
                task10_overrides[0].value
            ):
                blockers.append(
                    Blocker(
                        code=BlockerCode.CITATION_HASH_MISMATCH,
                        message=(
                            "TASK-010 authority override supplied but the loaded envelope "
                            "prediction_run_id does not match the override value."
                        ),
                        details={"override_value": int(task10_overrides[0].value)},
                        retry_hint="FIX_INPUT",
                    )
                )

        # --- TASK-011 --------------------------------------------------------
        task11_authority = None
        task11_overrides = _select_authority_overrides(overrides, "TASK11_BACKTEST_RUN")
        if task11_overrides:
            task11_authority = await self._task11.load_by_id(
                session=session,
                rolling_backtest_run_id=int(task11_overrides[0].value),
            )
            if task11_authority is None or int(task11_authority.rolling_backtest_run_id) != int(
                task11_overrides[0].value
            ):
                blockers.append(
                    Blocker(
                        code=BlockerCode.CITATION_HASH_MISMATCH,
                        message=(
                            "TASK-011 authority override supplied but the loaded envelope "
                            "rolling_backtest_run_id does not match the override value."
                        ),
                        details={"override_value": int(task11_overrides[0].value)},
                        retry_hint="FIX_INPUT",
                    )
                )

        # --- TASK-012 (only via explicit override, §22.1) --------------------
        task12_authority = None
        task12_overrides = _select_authority_overrides(overrides, "TASK12_PREDICTION_RUN")
        if task12_overrides:
            task12_authority = await self._task12.load_by_id(
                session=session,
                prediction_run_id=int(task12_overrides[0].value),
            )
            if task12_authority is None or int(task12_authority.prediction_run_id) != int(
                task12_overrides[0].value
            ):
                blockers.append(
                    Blocker(
                        code=BlockerCode.CITATION_HASH_MISMATCH,
                        message=(
                            "TASK-012 authority override supplied but the loaded envelope "
                            "prediction_run_id does not match the override value."
                        ),
                        details={"override_value": int(task12_overrides[0].value)},
                        retry_hint="FIX_INPUT",
                    )
                )
        else:
            # Per §22.1 / §15.8, no TASK-012 default path.  Block if any
            # downstream code expects a TASK-012 authority; here we simply
            # leave ``task12_authority = None`` which downstream consumers
            # must handle.
            pass

        # --- Compose per-day rows -------------------------------------------
        # In Slice A we use the injected baseline port to obtain the
        # authoritative per-day rows.  The baseline is itself a deterministic
        # composition of TASK-008/009/010 services and is supplied by the
        # production adapter (or by a test fake).  If no rows are available,
        # we return an empty curve with a ``PEAK_POLICY_MISSING``-style note
        # recorded as a blocker for traceability.
        per_day, baseline_blockers = await self._baseline.compute_baseline(
            session=session,
            normalized_request=nr,
            resolved_location=input.resolved_location,
            parameters=input.parameters,
            advanced_overrides=overrides,
        )
        blockers.extend(baseline_blockers)

        # Recompute per-row agent_daily_row_hash; compute curve hash over rows.
        rows: list[ForecastDailyRow] = []
        for row in per_day:
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
    }
    return sha256_payload(payload)


class _NoopScenarioBaseline:
    """Default baseline: empty curve + a single ``INTERNAL_FAILURE`` blocker.

    The production wiring replaces this with a deterministic composition
    adapter that reads TASK-008/009/010 outputs.  Slice A tests inject
    deterministic fakes per the design.
    """

    async def compute_baseline(
        self,
        *,
        session: AsyncSession,
        normalized_request: Any,
        resolved_location: Any,
        parameters: list[Any],
        advanced_overrides: AdvancedOverrides | None,
    ) -> tuple[list[ForecastDailyRow], list[Blocker]]:
        return (
            [],
            [
                Blocker(
                    code=BlockerCode.INTERNAL_FAILURE,
                    message=(
                        "No baseline composition adapter wired.  Inject a "
                        "ScenarioBaselinePort implementation in production."
                    ),
                    retry_hint="CONTACT_OPS",
                )
            ],
        )


__all__ = ["DefaultDailyCurveAdapter"]
