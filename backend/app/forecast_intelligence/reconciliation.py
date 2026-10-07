"""Pure exact-Decimal aggregation of already validated saved Base curves."""

from datetime import date, timedelta
from decimal import Decimal, localcontext
from typing import Any

from backend.app.area_yield.data import digest
from backend.app.forecast_intelligence.errors import HierarchicalForecastError
from backend.app.forecast_intelligence.hierarchy import (
    COMPANY_ID,
    CONTRACT_VERSION,
    validate_hierarchy,
)
from backend.app.forecast_intelligence.schemas import CreateHierarchicalRun
from backend.app.forecast_quality.operational_peak import summarize_window

POLICY_VERSION = "HIERARCHICAL_BOTTOM_UP_EXACT_SUM_R1"
FORECAST_FAMILY = "OPERATIONAL_PEAK_FORECAST_RUN_V1"
COMPATIBILITY_FIELDS = (
    "policy_version",
    "baseline_id",
    "target_season",
    "origin_date",
    "business_season_start",
    "business_season_end",
    "weather_used",
)


def _quantity(value: Any) -> Decimal:
    if isinstance(value, (float, bool)):
        raise HierarchicalForecastError("SOURCE_FORECAST_INTEGRITY_FAILED")
    try:
        number = Decimal(value)
        if not number.is_finite() or number < 0:
            raise ValueError
        return number
    except (ValueError, TypeError, ArithmeticError) as exc:
        raise HierarchicalForecastError("SOURCE_FORECAST_INTEGRITY_FAILED") from exc


def _text(value: Decimal) -> str:
    return format(value, "f")


def reconcile(
    hierarchy: dict[str, Any], request: CreateHierarchicalRun, sources: list[dict[str, Any]]
) -> dict[str, Any]:
    validate_hierarchy(hierarchy)
    bases = {b["base_id"]: b for b in hierarchy["bases"]}
    regions = {r["region_id"]: r for r in hierarchy["regions"]}
    if request.target_entity_type == "COMPANY":
        if request.target_entity_id != COMPANY_ID:
            raise HierarchicalForecastError("TARGET_ENTITY_NOT_FOUND")
        expected = sorted(b for b, value in bases.items() if value["active"])
        label = hierarchy["company"]["entity_label"]
    else:
        if request.target_entity_id not in regions:
            raise HierarchicalForecastError("TARGET_ENTITY_NOT_FOUND")
        expected = regions[request.target_entity_id]["active_child_base_ids"]
        label = regions[request.target_entity_id]["region_name"]
    ordered = sorted(sources, key=lambda s: s["run_id"])
    if [s["run_id"] for s in ordered] != request.source_run_ids:
        raise HierarchicalForecastError("SOURCE_FORECAST_INTEGRITY_FAILED")
    included: set[str] = set()
    source_authority = hierarchy["source_operational_peak_authority_hash"]
    first = ordered[0]["result"]
    compatibility = {key: first[key] for key in COMPATIBILITY_FIELDS}
    dates = [r["date"] for r in first["daily_forecast"]]
    origin = date.fromisoformat(first["origin_date"])
    end = date.fromisoformat(first["business_season_end"])
    required_dates = [
        (origin + timedelta(days=n)).isoformat() for n in range(1, min(15, (end - origin).days) + 1)
    ]
    if not dates or dates != required_dates:
        raise HierarchicalForecastError("SOURCE_DAILY_WINDOW_MISMATCH")
    for source in ordered:
        base = source["base_id"]
        if base not in bases:
            raise HierarchicalForecastError("SOURCE_BASE_NOT_IN_HIERARCHY")
        if not bases[base]["active"]:
            raise HierarchicalForecastError("INACTIVE_SOURCE_BASE")
        if base not in expected:
            raise HierarchicalForecastError("SOURCE_BASE_OUTSIDE_TARGET")
        if base in included:
            raise HierarchicalForecastError("DUPLICATE_BASE_FORECAST")
        included.add(base)
        result = source["result"]
        if source["authority_hash"] != source_authority:
            raise HierarchicalForecastError("HIERARCHY_SOURCE_AUTHORITY_MISMATCH")
        if {key: result[key] for key in COMPATIBILITY_FIELDS} != compatibility:
            raise HierarchicalForecastError("INCOMPATIBLE_SOURCE_FORECASTS")
        if [r["date"] for r in result["daily_forecast"]] != dates:
            raise HierarchicalForecastError("SOURCE_DAILY_WINDOW_MISMATCH")
        for row in result["daily_forecast"]:
            _quantity(row["predicted_kg"])
    source_ids = [s["run_id"] for s in ordered]
    source_hashes = [
        {
            "run_id": s["run_id"],
            "result_hash": s["result_hash"],
            "execution_hash": s["execution_hash"],
        }
        for s in ordered
    ]
    key = {
        "forecast_family": FORECAST_FAMILY,
        **compatibility,
        "authority_hash": source_authority,
        "daily_dates": dates,
        "quantile_or_point_label": "POINT",
        "scenario_id": "BASELINE",
    }
    execution = {
        "schema_version": CONTRACT_VERSION,
        "target_entity_type": request.target_entity_type,
        "target_entity_id": request.target_entity_id,
        "hierarchy_authority_hash": hierarchy["hierarchy_authority_hash"],
        "source_run_ids": source_ids,
        "source_result_hashes": source_hashes,
        "compatibility_key": key,
        "reconciliation_policy_version": POLICY_VERSION,
    }
    missing = sorted(set(expected) - included)
    value: dict[str, Any] = {
        **execution,
        "execution_hash": digest(execution),
        "forecast_family": FORECAST_FAMILY,
        "hierarchy_contract_version": CONTRACT_VERSION,
        "source_authority_hash": source_authority,
        "target_entity_label": label,
        "target_season": first["target_season"],
        "origin_date": first["origin_date"],
        "business_season_start": first["business_season_start"],
        "business_season_end": first["business_season_end"],
        "baseline_id": first["baseline_id"],
        "source_policy_version": first["policy_version"],
        "weather_used": first["weather_used"],
        "quantile_or_point_label": "POINT",
        "scenario_id": "BASELINE",
        "child_expected_count": len(expected),
        "child_included_count": len(included),
        "child_base_ids": sorted(included),
        "child_base_ids_hash": digest(sorted(included)),
        "missing_base_ids": missing,
        "missing_base_ids_hash": digest(missing),
        "source_run_ids_hash": digest(source_ids),
        "source_result_hashes_hash": digest(source_hashes),
        "status": "INCOMPLETE_CHILD_COVERAGE" if missing else "COMPLETE",
        "daily_forecast": [],
        "official_aggregate_kg": None,
        "aggregate_total_kg": None,
        "forecast_7d": None,
        "forecast_15d": None,
        "single_day_peak": None,
        "rolling_7day_peak": None,
        "season_total_kg": None,
        "season_total_status": "NOT_APPLICABLE_SOURCE_HORIZON",
        "company_path_parity": None,
        "region_breakdown": [],
        "region_breakdown_hash": digest([]),
        "limitations": [
            "POINT_FORECAST_ONLY",
            "TECHNICAL_ROOT_NOT_LEGAL_COMPANY",
            "REGION_SCOPE_EXACT_REGISTRY_LABEL_NOT_GEOGRAPHIC_CERTIFICATION",
            "SOURCE_HORIZON_AT_MOST_15_DAYS",
        ],
    }
    if not missing:
        # Canonical source quantities are six decimal places. Dynamic precision prevents
        # Decimal context rounding even for arbitrarily large admitted source values.
        quantities = [
            _quantity(r["predicted_kg"]) for s in ordered for r in s["result"]["daily_forecast"]
        ]
        precision = max(
            len(q.as_tuple().digits) + abs(int(q.as_tuple().exponent)) for q in quantities
        )
        with localcontext() as context:
            context.prec = max(50, precision + len(str(len(quantities))) + 12)
            daily = [
                {
                    "date": day,
                    "predicted_kg": _text(
                        sum(
                            (
                                _quantity(s["result"]["daily_forecast"][i]["predicted_kg"])
                                for s in ordered
                            ),
                            Decimal(0),
                        )
                    ),
                }
                for i, day in enumerate(dates)
            ]
            value["daily_forecast"] = daily
            total = _text(sum((_quantity(r["predicted_kg"]) for r in daily), Decimal(0)))
            value.update(official_aggregate_kg=total, aggregate_total_kg=total)
            for days in (7, 15):
                value[f"forecast_{days}d"] = summarize_window(
                    daily,
                    origin_date=origin,
                    window_days=days,
                    business_start=date.fromisoformat(first["business_season_start"]),
                    business_end=end,
                ).to_mapping()
            peak = min(daily, key=lambda r: (-Decimal(r["predicted_kg"]), r["date"]))
            value["single_day_peak"] = dict(peak)
            windows = [
                {
                    "start_date": daily[i]["date"],
                    "end_date": daily[i + 6]["date"],
                    "total_kg": _text(
                        sum((Decimal(r["predicted_kg"]) for r in daily[i : i + 7]), Decimal(0))
                    ),
                }
                for i in range(len(daily) - 6)
            ]
            value["rolling_7day_peak"] = (
                min(windows, key=lambda w: (-Decimal(w["total_kg"]), w["start_date"]))
                if windows
                else None
            )
            if request.target_entity_type == "COMPANY":
                breakdown = [
                    {
                        "region_id": r,
                        "daily_forecast": [
                            {
                                "date": day,
                                "predicted_kg": _text(
                                    sum(
                                        (
                                            Decimal(
                                                s["result"]["daily_forecast"][i]["predicted_kg"]
                                            )
                                            for s in ordered
                                            if bases[s["base_id"]]["region_id"] == r
                                        ),
                                        Decimal(0),
                                    )
                                ),
                            }
                            for i, day in enumerate(dates)
                        ],
                    }
                    for r in sorted(regions)
                ]
                parity = all(
                    Decimal(row["predicted_kg"])
                    == sum(
                        (Decimal(r["daily_forecast"][i]["predicted_kg"]) for r in breakdown),
                        Decimal(0),
                    )
                    for i, row in enumerate(daily)
                )
                if not parity:
                    raise HierarchicalForecastError("COMPANY_PATH_PARITY_FAILED")
                value.update(
                    company_path_parity=True,
                    region_breakdown=breakdown,
                    region_breakdown_hash=digest(breakdown),
                )
    return {**value, "result_hash": digest(value)}
