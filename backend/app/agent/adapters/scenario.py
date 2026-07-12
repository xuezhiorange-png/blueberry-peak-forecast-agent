"""TASK-013 Slice A — ``simulate_scenario`` deterministic adapter.

This adapter wraps the existing TASK-008/009/010 services via injected ports
and computes a deterministic baseline + scenario curve pair, then emits the
quantile-preserving delta summary required by §17.

Hard rules enforced:

* accepts the typed :class:`~backend.app.agent.schemas.ScenarioOverride`
  union;
* validates staffing/capacity non-negativity;
* wraps the actual existing services — does NOT create a new numerical
  production model;
* hashes the canonical scenario configuration;
* emits :class:`SimulateScenarioOutput` with the §17.3 structured deltas:
  * ``single_day_peak_volume_delta_kg`` (p50/p80/p90 decimal strings);
  * ``sustained_3day_daily_average_delta_kg_per_day`` (p50/p80/p90);
  * ``sustained_3day_cumulative_delta_kg`` (p50/p80/p90);
* never outputs a single scalar ``sustained_3day_delta``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agent.adapters.daily_curve import DefaultDailyCurveAdapter
from backend.app.agent.adapters.peak import DefaultPeakAdapter
from backend.app.agent.canonical import sha256_payload
from backend.app.agent.enums import BlockerCode, ForecastQuantile
from backend.app.agent.schemas import (
    Blocker,
    ForecastDailyRow,
    ForecastPeakInput,
    ScenarioDeltaQuantiles,
    SimulateScenarioDelta,
    SimulateScenarioInput,
    SimulateScenarioOutput,
)


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _validate_overrides(overrides: list[Any]) -> list[Blocker]:
    """Validate scenario overrides.  Negative staffing/capacity is rejected."""

    blockers: list[Blocker] = []
    for ov in overrides:
        v = ov.value
        if ov.target in ("STAFFING", "PROCESSOR_CAPACITY"):
            numeric = getattr(v, "value", None)
            try:
                n = _to_decimal(numeric)
            except Exception:
                blockers.append(
                    Blocker(
                        code=BlockerCode.SCENARIO_INVALID,
                        message=f"non-numeric scenario override value: {numeric}",
                        retry_hint="FIX_INPUT",
                    )
                )
                continue
            if n < 0:
                blockers.append(
                    Blocker(
                        code=BlockerCode.SCENARIO_INVALID,
                        message=(f"negative value for {ov.target} override: {numeric}"),
                        retry_hint="FIX_INPUT",
                    )
                )
    return blockers


def _scenario_id_and_hash(overrides: list[Any]) -> tuple[str, str]:
    payload = {
        "scenario_overrides": [
            {
                "override_kind": ov.override_kind,
                "target": ov.target,
                "value": _value_to_json(ov.value),
                "unit": getattr(ov.value, "unit", None),
                "source_attestation": ov.source_attestation,
                "source_ref": ov.source_ref,
            }
            for ov in overrides
        ]
    }
    return sha256_payload(payload), sha256_payload(payload)


def _value_to_json(v: Any) -> Any:
    if v is None:
        return None
    if hasattr(v, "model_dump"):
        return v.model_dump(mode="json")
    return getattr(v, "__dict__", v)


def _delta_quantiles(
    baseline_values: dict[ForecastQuantile, Decimal] | dict[str, Decimal],
    scenario_values: dict[ForecastQuantile, Decimal] | dict[str, Decimal],
) -> ScenarioDeltaQuantiles:
    p50 = format(scenario_values["P50"] - baseline_values["P50"], "f")
    p80 = format(scenario_values["P80"] - baseline_values["P80"], "f")
    p90 = format(scenario_values["P90"] - baseline_values["P90"], "f")
    return ScenarioDeltaQuantiles(p50=p50, p80=p80, p90=p90)


def _single_day_peak_volume(rows: list[ForecastDailyRow]) -> dict[ForecastQuantile, Decimal]:
    out: dict[ForecastQuantile, Decimal] = {}
    for q in ("P50", "P80", "P90"):
        field = {"P50": "p50", "P80": "p80", "P90": "p90"}[q]
        out[q] = max(
            (_to_decimal(getattr(r.final_corrected_arrival_quantity_kg, field)) for r in rows),
            default=Decimal("0"),
        )
    return out


def _sustained_3day_daily_average(
    rows: list[ForecastDailyRow],
) -> dict[ForecastQuantile, Decimal]:
    out: dict[ForecastQuantile, Decimal] = {}
    if len(rows) < 3:
        for q in ("P50", "P80", "P90"):
            out[q] = Decimal("0")
        return out
    for q in ("P50", "P80", "P90"):
        field = {"P50": "p50", "P80": "p80", "P90": "p90"}[q]
        by_date = {
            r.date: _to_decimal(getattr(r.final_corrected_arrival_quantity_kg, field)) for r in rows
        }
        sorted_dates = sorted(by_date.keys())
        best = Decimal("0")
        for i in range(len(sorted_dates) - 2):
            v = (
                by_date[sorted_dates[i]]
                + by_date[sorted_dates[i + 1]]
                + by_date[sorted_dates[i + 2]]
            ) / Decimal(3)
            if v > best:
                best = v
        out[cast(ForecastQuantile, q)] = best
    return out


def _sustained_3day_cumulative(
    rows: list[ForecastDailyRow],
) -> dict[ForecastQuantile, Decimal]:
    out: dict[ForecastQuantile, Decimal] = {}
    if len(rows) < 3:
        for q in ("P50", "P80", "P90"):
            out[q] = Decimal("0")
        return out
    for q in ("P50", "P80", "P90"):
        field = {"P50": "p50", "P80": "p80", "P90": "p90"}[q]
        by_date = {
            r.date: _to_decimal(getattr(r.final_corrected_arrival_quantity_kg, field)) for r in rows
        }
        sorted_dates = sorted(by_date.keys())
        best = Decimal("0")
        for i in range(len(sorted_dates) - 2):
            v = (
                by_date[sorted_dates[i]]
                + by_date[sorted_dates[i + 1]]
                + by_date[sorted_dates[i + 2]]
            )
            if v > best:
                best = v
        out[cast(ForecastQuantile, q)] = best
    return out


# --- Top-level adapter ----------------------------------------------------


class DefaultScenarioAdapter:
    """Default ``simulate_scenario`` deterministic adapter."""

    def __init__(
        self,
        *,
        daily_curve_adapter: DefaultDailyCurveAdapter | None = None,
        peak_adapter: DefaultPeakAdapter | None = None,
    ) -> None:
        self._daily_curve = daily_curve_adapter or DefaultDailyCurveAdapter()
        self._peak = peak_adapter or DefaultPeakAdapter()

    async def execute(
        self,
        session: AsyncSession,
        *,
        input: SimulateScenarioInput,
    ) -> SimulateScenarioOutput:
        blockers = _validate_overrides(input.scenario_overrides)
        if blockers:
            raise ValueError(
                "scenario overrides failed validation: " + "; ".join(b.code.value for b in blockers)
            )

        scenario_id, scenario_config_hash = _scenario_id_and_hash(input.scenario_overrides)

        # Baseline (no scenario overrides): reuse the daily_curve adapter
        # with a no-scenario advanced_overrides.
        from backend.app.agent.schemas import AdvancedOverrides

        baseline_overrides = AdvancedOverrides(
            parameter_overrides=[],
            scenario_overrides=[],
            execution_overrides=[],
            authority_overrides=[],
            as_of_overrides=[],
        )
        baseline_curve = await self._daily_curve.execute(
            session,
            input=__import__(
                "backend.app.agent.schemas", fromlist=["ForecastDailyCurveInput"]
            ).ForecastDailyCurveInput(
                normalized_request=input.normalized_request,
                resolved_location=input.resolved_location,
                parameters=input.parameters,
                advanced_overrides=baseline_overrides,
                uncertainty_widening_policy=input.uncertainty_widening_policy,
            ),
        )

        baseline_peak = self._peak.execute(
            input=ForecastPeakInput(
                normalized_request=input.normalized_request,
                daily_curve=baseline_curve,
                peak_metric_policy=input.peak_metric_policy,
            )
        )

        # Scenario curve: same adapter, but with the scenario overrides
        # applied via the baseline port (the baseline port is responsible
        # for applying scenario-specific adjustments).
        scenario_curve = await self._daily_curve.execute(
            session,
            input=__import__(
                "backend.app.agent.schemas", fromlist=["ForecastDailyCurveInput"]
            ).ForecastDailyCurveInput(
                normalized_request=input.normalized_request,
                resolved_location=input.resolved_location,
                parameters=input.parameters,
                advanced_overrides=AdvancedOverrides(
                    parameter_overrides=[],
                    scenario_overrides=input.scenario_overrides,
                    execution_overrides=[],
                    authority_overrides=[],
                    as_of_overrides=[],
                ),
                uncertainty_widening_policy=input.uncertainty_widening_policy,
            ),
        )

        scenario_peak = self._peak.execute(
            input=ForecastPeakInput(
                normalized_request=input.normalized_request,
                daily_curve=scenario_curve,
                peak_metric_policy=input.peak_metric_policy,
            )
        )

        # Compute quantile-preserving deltas from peak entries directly
        # (these are the authoritative post-scenario single-day peak volumes).
        baseline_peak_volume: dict[str, Decimal] = {
            q: _to_decimal(baseline_peak.single_day_peak[cast(ForecastQuantile, q)].volume_kg)
            for q in ("P50", "P80", "P90")
        }
        scenario_peak_volume: dict[str, Decimal] = {
            q: _to_decimal(scenario_peak.single_day_peak[cast(ForecastQuantile, q)].volume_kg)
            for q in ("P50", "P80", "P90")
        }

        # The sustained 3-day average/cumulative come from the underlying
        # daily curves (the peak output already contains them).
        baseline_sustained_avg: dict[str, Decimal] = {
            q: _to_decimal(
                baseline_peak.sustained_3day_peak[
                    cast(ForecastQuantile, q)
                ].rolling_daily_average_kg_per_day
            )
            for q in ("P50", "P80", "P90")
        }
        scenario_sustained_avg: dict[str, Decimal] = {
            q: _to_decimal(
                scenario_peak.sustained_3day_peak[
                    cast(ForecastQuantile, q)
                ].rolling_daily_average_kg_per_day
            )
            for q in ("P50", "P80", "P90")
        }
        baseline_sustained_cum: dict[str, Decimal] = {
            q: _to_decimal(
                baseline_peak.sustained_3day_peak[cast(ForecastQuantile, q)].cumulative_quantity_kg
            )
            for q in ("P50", "P80", "P90")
        }
        scenario_sustained_cum: dict[str, Decimal] = {
            q: _to_decimal(
                scenario_peak.sustained_3day_peak[cast(ForecastQuantile, q)].cumulative_quantity_kg
            )
            for q in ("P50", "P80", "P90")
        }

        return SimulateScenarioOutput(
            scenario_id=scenario_id,
            scenario_config_hash=scenario_config_hash,
            forecast_daily_curve=scenario_curve,
            forecast_peak=scenario_peak,
            delta_vs_baseline=SimulateScenarioDelta(
                single_day_peak_volume_delta_kg=_delta_quantiles(
                    baseline_peak_volume, scenario_peak_volume
                ),
                sustained_3day_daily_average_delta_kg_per_day=_delta_quantiles(
                    baseline_sustained_avg, scenario_sustained_avg
                ),
                sustained_3day_cumulative_delta_kg=_delta_quantiles(
                    baseline_sustained_cum, scenario_sustained_cum
                ),
            ),
        )


__all__ = ["DefaultScenarioAdapter"]
