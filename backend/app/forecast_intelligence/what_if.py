"""Pure saved-forecast scenario evaluation. No inference, optimization or execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Context, Decimal, Inexact, Rounded, localcontext
from typing import Any

from backend.app.area_yield.v015_research_cohort import digest
from backend.app.forecast_intelligence.business_loss import (
    BusinessCostContract,
    decimal_text,
    hash_shape,
    row_loss,
)

POLICY_VERSION = "V0_16_WHAT_IF_DECISION_SIMULATOR_R1"
CAPACITY_POLICY_VERSION = "V0_16_EXPLICIT_DAILY_HANDLING_CAPACITY_R1"
BACKLOG_POLICY_VERSION = "V0_16_DETERMINISTIC_BACKLOG_BALANCE_R1"
LOSS_MAPPING_POLICY_VERSION = "V0_16_PLANNING_DEMAND_VS_CAPACITY_LOSS_R1"
COMPARISON_POLICY_VERSION = "V0_16_SAME_FORECAST_PLANNING_LEVEL_COST_CONTRACT_R1"
RANKING_POLICY_VERSION = "V0_16_CONDITIONAL_SCENARIO_RANKING_R1"
UTILIZATION_POLICY_VERSION = "V0_16_EXACT_RATIO_WITH_DECIMAL50_HALF_EVEN_R1"
AMENDMENT_ID = "V0_16_S6_CAPACITY_UTILIZATION_RATIONAL_DECIMAL_EXCEPTION_R1"
PLANNING_LEVELS = ("POINT", "UPPER_PLANNING_BOUND_80", "UPPER_PLANNING_BOUND_90")
HIERARCHY_LEVELS = ("BASE", "REGION", "COMPANY")
ZERO = Decimal(0)


def numeric(value: Any) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise ValueError("SOURCE_NUMERIC_INVALID")


def nonempty(value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("SCENARIO_SCHEMA_INVALID")


def day_valid(value: Any) -> None:
    if type(value) is not date:
        raise ValueError("DATE_SCHEMA_INVALID")


def utilization(n: Decimal, d: Decimal, prefix: str) -> dict[str, Any]:
    """Exact quantity pair; ONLY this division has the Owner's Inexact exception."""
    numeric(n)
    numeric(d)
    if n > d or prefix not in ("capacity_utilization", "aggregate_capacity_utilization"):
        raise ValueError("UTILIZATION_AUTHORITY_INVALID")
    value, rounded = None, False
    if d > 0:
        with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)) as ctx:
            ctx.clear_flags()
            value = decimal_text(n / d)
            rounded = ctx.flags[Inexact] or ctx.flags[Rounded]
    return {
        f"{prefix}_numerator_kg": decimal_text(n),
        f"{prefix}_denominator_kg": decimal_text(d),
        f"{prefix}_decimal": value,
        f"{prefix}_precision": 50,
        f"{prefix}_rounding_mode": "ROUND_HALF_EVEN",
        f"{prefix}_rounding_applied": rounded,
        f"{prefix}_status": "COMPUTABLE" if d > 0 else "NOT_COMPUTABLE_ZERO_CAPACITY",
    }


@dataclass(frozen=True)
class SavedForecastDay:
    date: date
    point_forecast_kg: Decimal
    upper_planning_bound_80_kg: Decimal | None
    upper_planning_bound_90_kg: Decimal | None

    def __post_init__(self) -> None:
        day_valid(self.date)
        numeric(self.point_forecast_kg)
        for value in (self.upper_planning_bound_80_kg, self.upper_planning_bound_90_kg):
            if value is not None:
                numeric(value)
                if value < self.point_forecast_kg:
                    raise ValueError("PLANNING_BOUND_SCHEMA_INVALID")
        if (
            self.upper_planning_bound_80_kg is not None
            and self.upper_planning_bound_90_kg is not None
            and self.upper_planning_bound_90_kg < self.upper_planning_bound_80_kg
        ):
            raise ValueError("PLANNING_BOUND_SCHEMA_INVALID")

    def selected(self, level: str) -> Decimal:
        if level not in PLANNING_LEVELS:
            raise ValueError("PLANNING_LEVEL_INVALID")
        value = {
            "POINT": self.point_forecast_kg,
            "UPPER_PLANNING_BOUND_80": self.upper_planning_bound_80_kg,
            "UPPER_PLANNING_BOUND_90": self.upper_planning_bound_90_kg,
        }[level]
        if value is None:
            raise ValueError("BLOCKED_INCOMPLETE_PLANNING_CURVE")
        return value

    def payload(self) -> dict[str, Any]:
        return {
            "date": self.date.isoformat(),
            "point_forecast_kg": decimal_text(self.point_forecast_kg),
            "upper_planning_bound_80_kg": decimal_text(self.upper_planning_bound_80_kg)
            if self.upper_planning_bound_80_kg is not None
            else None,
            "upper_planning_bound_90_kg": decimal_text(self.upper_planning_bound_90_kg)
            if self.upper_planning_bound_90_kg is not None
            else None,
        }


@dataclass(frozen=True)
class SavedForecastCurve:
    forecast_source_id: str
    forecast_source_hash: str
    forecast_origin: datetime
    hierarchy_level: str
    hierarchy_entity_id: str
    hierarchy_authority_hash: str
    daily_rows: tuple[SavedForecastDay, ...]
    point_is_proven_p50: bool = False
    upper_planning_bound_is_quantile: bool = False

    def __post_init__(self) -> None:
        nonempty(self.forecast_source_id)
        nonempty(self.hierarchy_entity_id)
        hash_shape(self.forecast_source_hash)
        hash_shape(self.hierarchy_authority_hash)
        if (
            not isinstance(self.forecast_origin, datetime)
            or self.forecast_origin.tzinfo is None
            or self.forecast_origin.utcoffset() is None
            or self.hierarchy_level not in HIERARCHY_LEVELS
            or self.point_is_proven_p50 is not False
            or self.upper_planning_bound_is_quantile is not False
            or not isinstance(self.daily_rows, tuple)
            or not self.daily_rows
            or any(not isinstance(r, SavedForecastDay) for r in self.daily_rows)
        ):
            raise ValueError("SAVED_FORECAST_SCHEMA_INVALID")
        ordered = tuple(sorted(self.daily_rows, key=lambda r: r.date))
        if any(
            b.date != a.date + timedelta(days=1) for a, b in zip(ordered, ordered[1:], strict=False)
        ):
            raise ValueError("FORECAST_DATE_CONTINUITY_FAILED")
        object.__setattr__(self, "daily_rows", ordered)

    @property
    def forecast_curve_hash(self) -> str:
        return digest([r.payload() for r in self.daily_rows])

    def payload(self) -> dict[str, Any]:
        return {
            "forecast_source_id": self.forecast_source_id,
            "forecast_source_hash": self.forecast_source_hash,
            "forecast_origin": self.forecast_origin.astimezone(UTC).isoformat(),
            "hierarchy_level": self.hierarchy_level,
            "hierarchy_entity_id": self.hierarchy_entity_id,
            "hierarchy_authority_hash": self.hierarchy_authority_hash,
            "forecast_curve_hash": self.forecast_curve_hash,
            "point_is_proven_p50": False,
            "upper_planning_bound_is_quantile": False,
            "daily_rows": [r.payload() for r in self.daily_rows],
        }

    @property
    def saved_forecast_hash(self) -> str:
        return digest(self.payload())


def verify_saved_forecast(curve: SavedForecastCurve, expected_hash: str) -> None:
    hash_shape(expected_hash)
    if curve.saved_forecast_hash != expected_hash:
        raise ValueError("SOURCE_FORECAST_DRIFT")


@dataclass(frozen=True)
class CapacityDay:
    date: date
    capacity_mode: str
    daily_handling_capacity_kg: Decimal | None
    workforce_count: int | None
    productivity_kg_per_person_day: Decimal | None
    buffer_supplied: bool
    buffer_handling_capacity_kg: Decimal

    def __post_init__(self) -> None:
        day_valid(self.date)
        numeric(self.buffer_handling_capacity_kg)
        if type(self.buffer_supplied) is not bool or (
            not self.buffer_supplied and self.buffer_handling_capacity_kg != 0
        ):
            raise ValueError("BUFFER_CONTRACT_INVALID")
        if self.capacity_mode == "DIRECT":
            numeric(self.daily_handling_capacity_kg)
            if self.workforce_count is not None or self.productivity_kg_per_person_day is not None:
                raise ValueError("CAPACITY_MODE_CONFLICT")
        elif self.capacity_mode == "WORKFORCE_DERIVED":
            if (
                self.daily_handling_capacity_kg is not None
                or type(self.workforce_count) is not int
                or self.workforce_count < 0
            ):
                raise ValueError("CAPACITY_MODE_CONFLICT")
            numeric(self.productivity_kg_per_person_day)
        else:
            raise ValueError("CAPACITY_MODE_INVALID")

    def handling(self) -> Decimal:
        if self.capacity_mode == "DIRECT":
            assert self.daily_handling_capacity_kg is not None
            return self.daily_handling_capacity_kg
        assert self.workforce_count is not None and self.productivity_kg_per_person_day is not None
        try:
            with localcontext(Context(prec=50)) as ctx:
                ctx.traps[Inexact] = True
                return Decimal(self.workforce_count) * self.productivity_kg_per_person_day
        except Inexact:
            raise ValueError("AUTHORITATIVE_PRECISION_EXCEEDED") from None

    def payload(self) -> dict[str, Any]:
        return {
            "date": self.date.isoformat(),
            "capacity_mode": self.capacity_mode,
            "daily_handling_capacity_kg": decimal_text(self.daily_handling_capacity_kg)
            if self.daily_handling_capacity_kg is not None
            else None,
            "workforce_count": self.workforce_count,
            "productivity_kg_per_person_day": decimal_text(self.productivity_kg_per_person_day)
            if self.productivity_kg_per_person_day is not None
            else None,
            "buffer_supplied": self.buffer_supplied,
            "buffer_handling_capacity_kg": decimal_text(self.buffer_handling_capacity_kg),
        }


@dataclass(frozen=True)
class DecisionScenario:
    scenario_id: str
    scenario_version: str
    saved_forecast: SavedForecastCurve
    planning_level: str
    cost: BusinessCostContract
    capacity_rows: tuple[CapacityDay, ...]

    def __post_init__(self) -> None:
        nonempty(self.scenario_id)
        nonempty(self.scenario_version)
        if (
            not isinstance(self.saved_forecast, SavedForecastCurve)
            or not isinstance(self.cost, BusinessCostContract)
            or self.planning_level not in PLANNING_LEVELS
            or not isinstance(self.capacity_rows, tuple)
            or any(not isinstance(c, CapacityDay) for c in self.capacity_rows)
        ):
            raise ValueError("SCENARIO_SCHEMA_INVALID")
        ordered = tuple(sorted(self.capacity_rows, key=lambda c: c.date))
        if [c.date for c in ordered] != [r.date for r in self.saved_forecast.daily_rows]:
            raise ValueError("CAPACITY_DATE_COVERAGE_MISMATCH")
        object.__setattr__(self, "capacity_rows", ordered)

    def authority(self) -> dict[str, Any]:
        f = self.saved_forecast
        return {
            "saved_forecast_hash": f.saved_forecast_hash,
            "forecast_curve_hash": f.forecast_curve_hash,
            "forecast_source_hash": f.forecast_source_hash,
            "forecast_origin": f.payload()["forecast_origin"],
            "hierarchy_level": f.hierarchy_level,
            "hierarchy_entity_id": f.hierarchy_entity_id,
            "hierarchy_authority_hash": f.hierarchy_authority_hash,
            "planning_level": self.planning_level,
            "cost_contract_hash": self.cost.contract_hash,
            "loss_unit": self.cost.loss_unit,
            "dates": [r.date.isoformat() for r in f.daily_rows],
            "initial_backlog_kg": "0",
            "backlog_policy_version": BACKLOG_POLICY_VERSION,
        }

    def payload(self) -> dict[str, Any]:
        return self.authority() | {
            "scenario_id": self.scenario_id,
            "scenario_version": self.scenario_version,
            "policy_version": POLICY_VERSION,
            "capacity_policy_version": CAPACITY_POLICY_VERSION,
            "decision_loss_mapping_policy_version": LOSS_MAPPING_POLICY_VERSION,
            "capacity_rows": [c.payload() for c in self.capacity_rows],
        }

    @property
    def scenario_hash(self) -> str:
        return digest(self.payload())


def simulate(scenario: DecisionScenario) -> dict[str, Any]:
    """Forward queue balance over exactly the supplied scenario, never search."""
    if not isinstance(scenario, DecisionScenario):
        raise ValueError("SCENARIO_REQUIRED")
    daily = []
    opening = ZERO
    try:
        with localcontext(Context(prec=50)) as ctx:
            ctx.traps[Inexact] = True
            for demand_row, capacity in zip(
                scenario.saved_forecast.daily_rows, scenario.capacity_rows, strict=True
            ):
                demand = demand_row.selected(scenario.planning_level)
                handling = capacity.handling()
                effective = handling + capacity.buffer_handling_capacity_kg
                workload = opening + demand
                processed = min(workload, effective)
                closing = workload - processed
                # The frozen S5 kernel is the sole asymmetric loss implementation.
                mapped = row_loss(demand, effective, scenario.cost)
                if opening + demand != processed + closing or processed > effective:
                    raise ValueError("BACKLOG_MASS_BALANCE_FAILED")
                row = (
                    capacity.payload()
                    | {
                        "planning_level": scenario.planning_level,
                        "planning_demand_kg": decimal_text(demand),
                        "daily_handling_capacity_kg": decimal_text(handling),
                        "effective_capacity_kg": decimal_text(effective),
                        "opening_backlog_kg": decimal_text(opening),
                        "workload_kg": decimal_text(workload),
                        "processed_kg": decimal_text(processed),
                        "closing_backlog_kg": decimal_text(closing),
                        "daily_overload_kg": decimal_text(mapped["underforecast_kg"]),
                        "daily_over_capacity_kg": decimal_text(mapped["overforecast_kg"]),
                        "under_capacity_kg": decimal_text(mapped["underforecast_kg"]),
                        "over_capacity_kg": decimal_text(mapped["overforecast_kg"]),
                        "under_capacity_loss": decimal_text(mapped["underforecast_loss"]),
                        "over_capacity_loss": decimal_text(mapped["overforecast_loss"]),
                        "scenario_business_loss": decimal_text(mapped["total_business_loss"]),
                    }
                    | utilization(processed, effective, "capacity_utilization")
                )
                row["row_hash"] = digest(row)
                daily.append(row)
                opening = closing
            totals = {
                out: sum((Decimal(r[field]) for r in daily), ZERO)
                for out, field in (
                    ("total_planning_demand_kg", "planning_demand_kg"),
                    ("total_base_handling_capacity_kg", "daily_handling_capacity_kg"),
                    ("total_buffer_capacity_kg", "buffer_handling_capacity_kg"),
                    ("total_effective_capacity_kg", "effective_capacity_kg"),
                    ("total_processed_kg", "processed_kg"),
                    ("under_capacity_kg", "under_capacity_kg"),
                    ("over_capacity_kg", "over_capacity_kg"),
                    ("under_capacity_loss", "under_capacity_loss"),
                    ("over_capacity_loss", "over_capacity_loss"),
                    ("total_business_loss", "scenario_business_loss"),
                )
            }
            if (
                totals["total_planning_demand_kg"] != totals["total_processed_kg"] + opening
                or totals["total_business_loss"]
                != totals["under_capacity_loss"] + totals["over_capacity_loss"]
            ):
                raise ValueError("AGGREGATE_BALANCE_FAILED")
            result = (
                scenario.authority()
                | {
                    "scenario_id": scenario.scenario_id,
                    "scenario_hash": scenario.scenario_hash,
                    "scenario_status": "COMPLETE",
                    "loss_semantics": "ASYMMETRIC_PLANNING_GAP_LOSS",
                    "decision_evidence_class": "SYNTHETIC_DECISION_LOSS"
                    if scenario.cost.synthetic
                    else "EXPLICIT_COST_DECISION_SUPPORT_NOT_PRODUCTION_APPROVAL",
                    "forecast_start_date": daily[0]["date"],
                    "forecast_end_date": daily[-1]["date"],
                    "day_count": len(daily),
                    "overload_dates": [
                        r["date"] for r in daily if Decimal(r["daily_overload_kg"]) > 0
                    ],
                    "backlog_dates": [
                        r["date"] for r in daily if Decimal(r["closing_backlog_kg"]) > 0
                    ],
                    "cumulative_shortfall_kg": decimal_text(totals["under_capacity_kg"]),
                    "max_backlog_kg": decimal_text(
                        max(Decimal(r["closing_backlog_kg"]) for r in daily)
                    ),
                    "ending_backlog_kg": decimal_text(opening),
                    "daily_rows": daily,
                }
                | {k: decimal_text(v) for k, v in totals.items()}
            )
            result["overload_day_count"] = len(result["overload_dates"])
            result["backlog_day_count"] = len(result["backlog_dates"])
            result |= utilization(
                totals["total_processed_kg"],
                totals["total_effective_capacity_kg"],
                "aggregate_capacity_utilization",
            )
            result["result_hash"] = digest(result)
            return result
    except Inexact:
        raise ValueError("AUTHORITATIVE_PRECISION_EXCEEDED") from None


def compare_and_rank(scenarios: tuple[DecisionScenario, ...]) -> dict[str, Any]:
    if not scenarios or len({s.scenario_id for s in scenarios}) != len(scenarios):
        raise ValueError("SCENARIO_DUPLICATE_OR_EMPTY")
    # Same declared source identity cannot silently acquire different saved bytes.
    seen: dict[str, str] = {}
    for s in scenarios:
        f = s.saved_forecast
        if f.forecast_source_id in seen and seen[f.forecast_source_id] != f.saved_forecast_hash:
            raise ValueError("SOURCE_FORECAST_DRIFT")
        seen[f.forecast_source_id] = f.saved_forecast_hash
    authority = scenarios[0].authority()
    if any(s.authority() != authority for s in scenarios):
        return {"scenario_comparison_status": "NOT_COMPARABLE_AUTHORITY_MISMATCH", "rankings": []}
    results = [simulate(s) for s in scenarios]
    ordered = sorted(
        results,
        key=lambda r: (
            Decimal(r["total_business_loss"]),
            Decimal(r["max_backlog_kg"]),
            Decimal(r["cumulative_shortfall_kg"]),
            Decimal(r["ending_backlog_kg"]),
            r["scenario_id"],
        ),
    )
    result = {
        "scenario_comparison_status": "COMPARABLE",
        "comparison_authority_hash": digest(authority),
        "ranking_semantics": "DESCRIPTIVE_ORDER_UNDER_GIVEN_INPUTS_AND_COST_CONTRACT",
        "rankings": [
            {
                "scenario_id": r["scenario_id"],
                "scenario_hash": r["scenario_hash"],
                "result_hash": r["result_hash"],
                "scenario_rank": rank,
            }
            for rank, r in enumerate(ordered, 1)
        ],
    }
    result["comparison_hash"] = digest(result)
    return result
