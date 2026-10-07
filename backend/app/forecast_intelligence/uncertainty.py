"""Pure Decimal rolling date-bound conformal research; no IO or point-model execution."""

from __future__ import annotations

from bisect import insort
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, localcontext
from typing import Any
from zoneinfo import ZoneInfo

from backend.app.area_yield.v015_research_cohort import digest

MODEL_ID = "V0_15_S5_M1_RIDGE"
POLICY_VERSION = "V0_16_ROLLING_DATE_BOUND_CONFORMAL_R1"
NOT_COMPUTABLE = "NOT_COMPUTABLE_INSUFFICIENT_CALIBRATION"
SHANGHAI = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class CalibrationTargetRow:
    row_key: str
    base_id: str
    season: str
    forecast_origin: datetime
    lead_day: int
    target_date: date
    point_prediction_kg: Decimal
    actual_kg: Decimal
    point_model_id: str = MODEL_ID
    split: str = "EXPOSED_OOT"

    def validate(self) -> None:
        if self.season == "2026-2027":
            raise ValueError("FAIL_CURRENT_SEASON_ACTUAL_PRESENT")
        if self.season != "2025-2026" or self.split != "EXPOSED_OOT":
            raise ValueError("SOURCE_SPLIT_INVALID")
        if self.point_model_id != MODEL_ID:
            raise ValueError("POINT_MODEL_IDENTITY_MISMATCH")
        origin = self.forecast_origin
        if origin.tzinfo is None or origin.utcoffset() != timedelta(hours=8):
            raise ValueError("SOURCE_ORIGIN_SEMANTICS_DRIFT")
        local = origin.astimezone(SHANGHAI)
        if (local.hour, local.minute, local.second, local.microsecond) != (17, 0, 0, 0):
            raise ValueError("SOURCE_ORIGIN_SEMANTICS_DRIFT")
        if (
            type(self.lead_day) is not int
            or not 1 <= self.lead_day <= 15
            or self.target_date != local.date() + timedelta(days=self.lead_day)
            or not self.row_key
            or not self.base_id
        ):
            raise ValueError("ROWSET_ACCOUNTING_FAILED")
        for value in (self.actual_kg, self.point_prediction_kg):
            if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
                raise ValueError("SOURCE_NUMERIC_INVALID")


def order_statistic(scores: list[Decimal], level: int) -> Decimal | None:
    """Uninterpolated 1-based ceil((n+1)c); mathematical minimum only."""
    if level not in (80, 90):
        raise ValueError("COVERAGE_LEVEL_INVALID")
    if any(not isinstance(s, Decimal) or not s.is_finite() or s < 0 for s in scores):
        raise ValueError("SOURCE_NUMERIC_INVALID")
    ordered = sorted(scores)
    k = ((len(ordered) + 1) * level + 99) // 100
    return ordered[k - 1] if 1 <= k <= len(ordered) else None


def interval(point: Decimal, q_abs: Decimal, q_upper: Decimal) -> dict[str, str]:
    if any(
        not isinstance(v, Decimal) or not v.is_finite() or v < 0 for v in (point, q_abs, q_upper)
    ):
        raise ValueError("SOURCE_NUMERIC_INVALID")
    with localcontext() as ctx:
        ctx.prec = 50
        return {
            "lower_kg": str(max(Decimal(0), point - q_abs)),
            "upper_kg": str(point + q_abs),
            "upper_planning_bound_kg": str(point + q_upper),
        }


def _quantile_sorted(scores: list[Decimal], level: int) -> Decimal | None:
    k = ((len(scores) + 1) * level + 99) // 100
    return scores[k - 1] if k <= len(scores) else None


def calibrate(source: list[CalibrationTargetRow]) -> list[dict[str, Any]]:
    """Insert mature rows before each origin; same-origin rows cannot enter any pool."""
    for row in source:
        row.validate()
    keys = {(r.base_id, r.forecast_origin, r.lead_day) for r in source}
    if len(keys) != len(source) or len({r.row_key for r in source}) != len(source):
        raise ValueError("ROWSET_ACCOUNTING_FAILED")
    ordered = sorted(source, key=lambda r: (r.forecast_origin, r.base_id, r.lead_day, r.row_key))
    mature = sorted(source, key=lambda r: (r.target_date, r.forecast_origin, r.row_key))
    abs_pools: dict[int, list[Decimal]] = {d: [] for d in range(1, 16)}
    upper_pools: dict[int, list[Decimal]] = {d: [] for d in range(1, 16)}
    max_origins: dict[int, datetime] = {}
    max_targets: dict[int, date] = {}
    index = 0
    result = []
    with localcontext() as ctx:
        ctx.prec = 50
        for row in ordered:
            local_date = row.forecast_origin.astimezone(SHANGHAI).date()
            while index < len(mature) and mature[index].target_date < local_date:
                candidate = mature[index]
                # Redundant with positive lead validation, retained as an explicit custody guard.
                if candidate.forecast_origin >= row.forecast_origin:
                    raise ValueError("FUTURE_RESIDUAL_LEAKAGE")
                d = candidate.lead_day
                residual = candidate.actual_kg - candidate.point_prediction_kg
                insort(abs_pools[d], abs(residual))
                insort(upper_pools[d], max(residual, Decimal(0)))
                max_origins[d] = max(
                    max_origins.get(d, candidate.forecast_origin), candidate.forecast_origin
                )
                max_targets[d] = max(
                    max_targets.get(d, candidate.target_date), candidate.target_date
                )
                index += 1
            d = row.lead_day
            p, actual = row.point_prediction_kg, row.actual_kg
            output: dict[str, Any] = {
                "row_key": row.row_key,
                "base_id": row.base_id,
                "season": row.season,
                "forecast_origin": row.forecast_origin.isoformat(),
                "origin_local_date": local_date.isoformat(),
                "lead_day": d,
                "target_date": row.target_date.isoformat(),
                "point_forecast_kg": str(p),
                "actual_kg": str(actual),
                "split": row.split,
                "calibration_n": len(abs_pools[d]),
                "calibration_pool_max_origin": max_origins[d].isoformat()
                if d in max_origins
                else None,
                "calibration_pool_max_target_date": max_targets[d].isoformat()
                if d in max_targets
                else None,
                "policy_version": POLICY_VERSION,
                "point_model_id": MODEL_ID,
            }
            for level in (80, 90):
                qa = _quantile_sorted(abs_pools[d], level)
                qu = _quantile_sorted(upper_pools[d], level)
                bounds = interval(p, qa, qu) if qa is not None and qu is not None else None
                output[f"calibration_n_{level}"] = len(abs_pools[d])
                output[f"abs_score_q{level}_kg"] = str(qa) if qa is not None else None
                output[f"upper_score_q{level}_kg"] = str(qu) if qu is not None else None
                output[f"prediction_interval_{level}"] = (
                    {k: bounds[k] for k in ("lower_kg", "upper_kg")} if bounds else None
                )
                output[f"upper_planning_bound_{level}"] = (
                    bounds["upper_planning_bound_kg"] if bounds else None
                )
                output[f"interval_{level}_status"] = "COMPUTABLE" if bounds else NOT_COMPUTABLE
                output[f"interval_{level}_covered"] = (
                    Decimal(bounds["lower_kg"]) <= actual <= Decimal(bounds["upper_kg"])
                    if bounds
                    else None
                )
                output[f"upper_{level}_covered"] = (
                    actual <= Decimal(bounds["upper_planning_bound_kg"]) if bounds else None
                )
            if output["prediction_interval_90"] is not None:
                b80, b90 = output["prediction_interval_80"], output["prediction_interval_90"]
                if not (
                    Decimal(b90["lower_kg"]) <= Decimal(b80["lower_kg"])
                    and Decimal(b90["upper_kg"]) >= Decimal(b80["upper_kg"])
                    and Decimal(output["upper_planning_bound_90"])
                    >= Decimal(output["upper_planning_bound_80"])
                    >= p
                ):
                    raise ValueError("CONFORMAL_MONOTONICITY_FAILED")
            output["row_hash"] = digest(output)
            result.append(output)
    return result


def _median(values: list[Decimal]) -> str | None:
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    return str(ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2)


def coverage(rows: list[dict[str, Any]], kind: str, level: int) -> dict[str, Any]:
    key = f"{'interval' if kind == 'PI' else 'upper'}_{level}_covered"
    valid = [r for r in rows if r[key] is not None]
    covered = sum(r[key] is True for r in valid)
    nominal = Decimal(level) / 100
    empirical = Decimal(covered) / len(valid) if valid else None
    value: dict[str, Any] = {
        "candidate_row_count": len(rows),
        "computable_row_count": len(valid),
        "not_computable_row_count": len(rows) - len(valid),
        "covered_row_count": covered,
        "empirical_coverage": str(empirical) if empirical is not None else None,
        "nominal_coverage": str(nominal),
        "coverage_gap": str(empirical - nominal) if empirical is not None else None,
        "observation": ("AT_OR_ABOVE_NOMINAL" if empirical >= nominal else "UNDER_NOMINAL")
        if empirical is not None
        else "NOT_COMPUTABLE",
    }
    if kind == "PI":
        widths = [
            Decimal(r[f"prediction_interval_{level}"]["upper_kg"])
            - Decimal(r[f"prediction_interval_{level}"]["lower_kg"])
            for r in valid
        ]
        value.update(
            {
                "mean_interval_width_kg": str(sum(widths) / len(widths)) if widths else None,
                "median_interval_width_kg": _median(widths),
                "min_interval_width_kg": str(min(widths)) if widths else None,
                "max_interval_width_kg": str(max(widths)) if widths else None,
            }
        )
    else:
        expansions = [
            Decimal(r[f"upper_planning_bound_{level}"]) - Decimal(r["point_forecast_kg"])
            for r in valid
        ]
        value.update(
            {
                "mean_upper_expansion_kg": str(sum(expansions) / len(expansions))
                if expansions
                else None,
                "median_upper_expansion_kg": _median(expansions),
            }
        )
    return value


def evaluate(
    rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    def summaries(subset: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            f"{kind}{level}": coverage(subset, kind, level)
            for kind in ("PI", "UPPER")
            for level in (80, 90)
        }

    with localcontext() as ctx:
        ctx.prec = 50
        overall = {f"H{h}": summaries([r for r in rows if r["lead_day"] <= h]) for h in (7, 15)}
        leads = []
        for d in range(1, 16):
            subset = [r for r in rows if r["lead_day"] == d]
            ns = [Decimal(r["calibration_n"]) for r in subset]
            leads.append(
                {
                    "lead_day": d,
                    "metrics": summaries(subset),
                    "calibration_n_min": int(min(ns)) if ns else None,
                    "calibration_n_median": _median(ns),
                    "calibration_n_max": int(max(ns)) if ns else None,
                }
            )
        by_base: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            by_base.setdefault(r["base_id"], []).append(r)
        private = {base: summaries(subset) for base, subset in sorted(by_base.items())}
        breadth = {}
        for name in ("PI80", "PI90", "UPPER80", "UPPER90"):
            counts = [item[name] for item in private.values()]
            computable = [c for c in counts if c["computable_row_count"]]
            above = sum(
                Decimal(c["empirical_coverage"]) >= Decimal(c["nominal_coverage"])
                for c in computable
            )
            breadth[name] = {
                "comparable_base_count": len(counts),
                "computable_base_count": len(computable),
                "bases_at_or_above_nominal_coverage_count": above,
                "bases_below_nominal_coverage_count": len(computable) - above,
                "bases_with_no_computable_rows_count": len(counts) - len(computable),
            }
    return overall, leads, breadth, private
