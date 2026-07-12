"""TASK-013 Slice A — ``simulate_scenario`` deterministic adapter.

This adapter wraps the existing TASK-008/009/010 services via injected ports
and computes a deterministic baseline + scenario curve pair, then emits the
quantile-preserving delta summary required by §17.

Hard rules enforced (P0-6):

* The baseline preserves the input ``parameter_overrides`` /
  ``authority_overrides`` / ``as_of_overrides`` / ``execution_overrides`` —
  it only clears ``scenario_overrides``.
* The scenario preserves the same non-scenario override families and
  applies the current ``scenario_overrides``.
* Both baseline and scenario use the SAME TASK-008/009/010 authority
  set.  Any drift between the two returns
  :data:`BlockerCode.SCENARIO_INCOMPATIBLE_WITH_BASE` and the delta is
  NOT computed.
* Scenario overrides have no upstream execution capability in Slice A.
  When a scenario override is supplied, the adapter emits
  :data:`BlockerCode.SCENARIO_OVERRIDE_EXECUTION_NOT_AVAILABLE` and
  does NOT return a fabricated scenario curve.
* Accepts the typed :class:`~backend.app.agent.schemas.ScenarioOverride`
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
    AdvancedOverrides,
    Blocker,
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


def _single_day_peak_volume(rows: list[Any]) -> dict[ForecastQuantile, Decimal]:
    out: dict[ForecastQuantile, Decimal] = {}
    for q in ("P50", "P80", "P90"):
        field = {"P50": "p50", "P80": "p80", "P90": "p90"}[q]
        out[q] = max(
            (_to_decimal(getattr(r.final_corrected_arrival_quantity_kg, field)) for r in rows),
            default=Decimal("0"),
        )
    return out


def _authority_identities_match(baseline_curve: Any, scenario_curve: Any) -> bool:
    """Compare TASK-008/009/010 authority envelope IDs across the two curves."""

    pairs = (
        ("task8_authority", "maturity_forecast_run_id"),
        ("task9_authority", "harvest_state_run_id"),
        ("task10_authority", "prediction_run_id"),
    )
    for attr, id_field in pairs:
        b_env = getattr(baseline_curve, attr, None)
        s_env = getattr(scenario_curve, attr, None)
        if b_env is None and s_env is None:
            continue
        if b_env is None or s_env is None:
            return False
        if getattr(b_env, id_field) != getattr(s_env, id_field):
            return False
    return True


def _baseline_and_scenario_overrides(
    *,
    input: SimulateScenarioInput,
) -> tuple[AdvancedOverrides, AdvancedOverrides]:
    """Build baseline + scenario ``AdvancedOverrides`` preserving provenance.

    Baseline: keep input non-scenario overrides; clear scenario_overrides.
    Scenario: keep input non-scenario overrides; apply input scenario_overrides.
    """

    input_overrides = input.advanced_overrides or AdvancedOverrides()
    baseline_overrides = AdvancedOverrides(
        parameter_overrides=list(input_overrides.parameter_overrides),
        authority_overrides=list(input_overrides.authority_overrides),
        as_of_overrides=list(input_overrides.as_of_overrides),
        execution_overrides=list(input_overrides.execution_overrides),
        scenario_overrides=[],
    )
    scenario_overrides = AdvancedOverrides(
        parameter_overrides=list(input_overrides.parameter_overrides),
        authority_overrides=list(input_overrides.authority_overrides),
        as_of_overrides=list(input_overrides.as_of_overrides),
        execution_overrides=list(input_overrides.execution_overrides),
        scenario_overrides=list(input.scenario_overrides),
    )
    return baseline_overrides, scenario_overrides


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
        validation_blockers = _validate_overrides(input.scenario_overrides)
        if validation_blockers:
            raise ValueError(
                "scenario overrides failed validation: "
                + "; ".join(b.code.value for b in validation_blockers)
            )

        scenario_id, scenario_config_hash = _scenario_id_and_hash(input.scenario_overrides)

        # P0-6: scenario overrides have no real upstream execution
        # capability in Slice A.  When ANY scenario override is supplied,
        # surface SCENARIO_OVERRIDE_EXECUTION_NOT_AVAILABLE rather than
        # emitting a fabricated scenario curve.
        if input.scenario_overrides:
            # Still compute the baseline to preserve the contract, but
            # emit a typed capability blocker for the scenario.
            baseline_overrides, _ = _baseline_and_scenario_overrides(input=input)
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
            capability_blocker = Blocker(
                code=BlockerCode.SCENARIO_OVERRIDE_EXECUTION_NOT_AVAILABLE,
                message=(
                    "scenario override execution is not available in Slice A; "
                    "no upstream scenario-capable service exists to apply the "
                    "supplied scenario override."
                ),
                details={
                    "scenario_override_count": len(input.scenario_overrides),
                    "scenario_override_targets": sorted(
                        {ov.target for ov in input.scenario_overrides}
                    ),
                },
                retry_hint="WAIT_FOR_DATA",
            )
            baseline_curve.blockers.append(capability_blocker)
            baseline_peak = self._peak.execute(
                input=ForecastPeakInput(
                    normalized_request=input.normalized_request,
                    daily_curve=baseline_curve,
                    peak_metric_policy=input.peak_metric_policy,
                )
            )
            zero_delta = SimulateScenarioDelta(
                single_day_peak_volume_delta_kg=ScenarioDeltaQuantiles(p50="0", p80="0", p90="0"),
                sustained_3day_daily_average_delta_kg_per_day=ScenarioDeltaQuantiles(
                    p50="0", p80="0", p90="0"
                ),
                sustained_3day_cumulative_delta_kg=ScenarioDeltaQuantiles(
                    p50="0", p80="0", p90="0"
                ),
            )
            # P0-6 round 5: the scenario result is discriminated —
            # ``status="BLOCKED"`` is a TOP-LEVEL field.  No fabricated
            # scenario curve / peak / delta is attached.  The baseline
            # curve is still emitted so callers can see what the
            # baseline WOULD have been, but the scenario status is
            # BLOCKED at the top level (the contract explicitly
            # forbids nested ``forecast_daily_curve.blockers`` only
            # signaling the blocker).
            return SimulateScenarioOutput(
                scenario_id=scenario_id,
                scenario_config_hash=scenario_config_hash,
                status="BLOCKED",
                forecast_daily_curve=baseline_curve,
                forecast_peak=baseline_peak,
                delta_vs_baseline=zero_delta,
                blockers=[capability_blocker],
            )

        baseline_overrides, scenario_overrides = _baseline_and_scenario_overrides(input=input)

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

        scenario_curve = await self._daily_curve.execute(
            session,
            input=__import__(
                "backend.app.agent.schemas", fromlist=["ForecastDailyCurveInput"]
            ).ForecastDailyCurveInput(
                normalized_request=input.normalized_request,
                resolved_location=input.resolved_location,
                parameters=input.parameters,
                advanced_overrides=scenario_overrides,
                uncertainty_widening_policy=input.uncertainty_widening_policy,
            ),
        )

        # Authority compatibility: baseline and scenario MUST share the
        # same TASK-008/009/010 authority set.  Any drift returns
        # SCENARIO_INCOMPATIBLE_WITH_BASE and we do not compute the delta.
        if not _authority_identities_match(baseline_curve, scenario_curve):
            incompatible_blocker = Blocker(
                code=BlockerCode.SCENARIO_INCOMPATIBLE_WITH_BASE,
                message=(
                    "scenario curve's TASK-008/009/010 authority identities "
                    "differ from baseline; cannot compute a meaningful delta."
                ),
                details={
                    "baseline_task8_run_id": (
                        getattr(baseline_curve.task8_authority, "maturity_forecast_run_id", None)
                    ),
                    "scenario_task8_run_id": (
                        getattr(scenario_curve.task8_authority, "maturity_forecast_run_id", None)
                    ),
                    "baseline_task9_run_id": (
                        getattr(baseline_curve.task9_authority, "harvest_state_run_id", None)
                    ),
                    "scenario_task9_run_id": (
                        getattr(scenario_curve.task9_authority, "harvest_state_run_id", None)
                    ),
                    "baseline_task10_run_id": (
                        getattr(baseline_curve.task10_authority, "prediction_run_id", None)
                    ),
                    "scenario_task10_run_id": (
                        getattr(scenario_curve.task10_authority, "prediction_run_id", None)
                    ),
                },
                retry_hint="FIX_INPUT",
            )
            scenario_curve.blockers.append(incompatible_blocker)
            scenario_peak = self._peak.execute(
                input=ForecastPeakInput(
                    normalized_request=input.normalized_request,
                    daily_curve=scenario_curve,
                    peak_metric_policy=input.peak_metric_policy,
                )
            )
            zero_delta = SimulateScenarioDelta(
                single_day_peak_volume_delta_kg=ScenarioDeltaQuantiles(p50="0", p80="0", p90="0"),
                sustained_3day_daily_average_delta_kg_per_day=ScenarioDeltaQuantiles(
                    p50="0", p80="0", p90="0"
                ),
                sustained_3day_cumulative_delta_kg=ScenarioDeltaQuantiles(
                    p50="0", p80="0", p90="0"
                ),
            )
            return SimulateScenarioOutput(
                scenario_id=scenario_id,
                scenario_config_hash=scenario_config_hash,
                status="BLOCKED",
                forecast_daily_curve=scenario_curve,
                forecast_peak=scenario_peak,
                delta_vs_baseline=zero_delta,
                blockers=[incompatible_blocker],
            )

        scenario_peak = self._peak.execute(
            input=ForecastPeakInput(
                normalized_request=input.normalized_request,
                daily_curve=scenario_curve,
                peak_metric_policy=input.peak_metric_policy,
            )
        )

        def _single_day_value(peak_output: Any, q: str) -> Decimal:
            if q not in peak_output.single_day_peak:
                return Decimal("0")
            return _to_decimal(peak_output.single_day_peak[cast(ForecastQuantile, q)].volume_kg)

        baseline_peak_volume: dict[str, Decimal] = {
            q: _single_day_value(baseline_peak, q) for q in ("P50", "P80", "P90")
        }
        scenario_peak_volume: dict[str, Decimal] = {
            q: _single_day_value(scenario_peak, q) for q in ("P50", "P80", "P90")
        }

        def _sustained_value(peak_output: Any, q: str, attr: str) -> Decimal:
            sus = peak_output.sustained_3day_peak
            if q not in sus:
                return Decimal("0")
            return _to_decimal(getattr(sus[q], attr))

        baseline_sustained_avg: dict[str, Decimal] = {
            q: _sustained_value(baseline_peak, q, "rolling_daily_average_kg_per_day")
            for q in ("P50", "P80", "P90")
        }
        scenario_sustained_avg: dict[str, Decimal] = {
            q: _sustained_value(scenario_peak, q, "rolling_daily_average_kg_per_day")
            for q in ("P50", "P80", "P90")
        }
        baseline_sustained_cum: dict[str, Decimal] = {
            q: _sustained_value(baseline_peak, q, "cumulative_quantity_kg")
            for q in ("P50", "P80", "P90")
        }
        scenario_sustained_cum: dict[str, Decimal] = {
            q: _sustained_value(scenario_peak, q, "cumulative_quantity_kg")
            for q in ("P50", "P80", "P90")
        }

        return SimulateScenarioOutput(
            scenario_id=scenario_id,
            scenario_config_hash=scenario_config_hash,
            status="SUCCESS",
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
            blockers=[],
        )


__all__ = ["DefaultScenarioAdapter"]
