"""Compare rolling evidence without selecting or tuning a new model."""

from typing import Any


def origin_one_parity(r5: dict[str, Any], r6: dict[str, Any]) -> bool:
    keys = (
        "predicted_total_kg",
        "daily_mae_kg",
        "daily_wape",
        "total_rel_error",
        "peak_date_error_days",
        "seven_day_shift_days",
        "mass_balance_error_kg",
    )
    reference = {(r["farm"], r["composite"]): r for r in r5["per_farm"]}
    current = {(r["farm"], r["composite"]): r for r in r6["composites"]}
    return reference.keys() == current.keys() and all(
        all(reference[k][field] == current[k][field] for field in keys) for k in reference
    )


def compare_origins(
    reference: dict[str, Any],
    totals: dict[str, Any],
    shapes: dict[str, Any],
    composites: dict[str, Any],
) -> dict[str, Any]:
    # No claim of stable direction without the same farm denominator and both origins.
    same_total_farms = {r["farm"] for r in reference["r6"]["total_per_farm"]} == {
        r["farm"] for r in totals["per_farm"]
    }
    result: dict[str, Any] = {
        "origin_1_parity": "PASS"
        if origin_one_parity(reference["r5"], reference["r6"])
        else "FAIL",
        "origin_1_macro": reference["r5"]["macro"],
        "origin_2_macro": composites["macro"],
        "origin_1_macro_best": reference["r5"]["macro_best"],
        "origin_2_macro_best": composites["macro_best"],
        "b2_replicated": "NOT_COMPUTABLE",
        "cross_season_direction_stable": "NOT_COMPUTABLE",
        "farm_heterogeneity_persists": "NOT_ESTABLISHED",
        "total_research_reopen_threshold_reached": totals["farm_count"] >= 3,
        "shape_research_reopen_threshold_reached": len(shapes["common_exact_farms"]) >= 3,
        "model_search_started": False,
        "limitations": "Censored and diagnostic samples cannot prove full-season direction.",
    }
    if (
        same_total_farms
        and composites["macro"]
        and all(
            r["peak_date_error_days"] is not None and r["seven_day_shift_days"] is not None
            for r in composites["macro"]
        )
    ):
        result["b2_replicated"] = reference["r5"]["macro_best"] == composites["macro_best"] == "B2"
        result["cross_season_direction_stable"] = result["b2_replicated"]
        result["farm_heterogeneity_persists"] = (
            reference["r5"]["farm_heterogeneity_observed"]
            and len(set(composites["farm_best"].values())) > 1
        )
    return result
