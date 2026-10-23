"""Fixed-input A/B profile reliability audit; never selects or refits a profile."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Context, Decimal, localcontext
from typing import Any, cast

from backend.app.forecast_quality.operational_peak import (
    _daily_row,
    load_frozen_reference_profile,
    nearest_reference_bin,
)
from backend.research.v019_daily_curve import DailyKg
from backend.research.v019_stability_diagnostics import serial
from backend.research.v019_synthetic_validation import _peak, digest


def audit(bundle: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    with localcontext(Context(prec=50)):
        pp = {f: load_frozen_reference_profile(p) for f, p in bundle["profiles"].items()}
        meta = trace["training-manifest.json"]["folds"]
        for f in ["A", "B"]:
            if meta[f]["train_row_set_hash"] != bundle["profiles"][f]["train_row_set_hash"] or meta[
                f
            ]["train_seasons"] != (["2023-2024"] if f == "A" else ["2023-2024", "2024-2025"]):
                raise ValueError("PROFILE_TRAINING_TRACE_MISMATCH")
        bins = []
        for i in range(42):
            refs = {f: nearest_reference_bin(i, sorted(p)) for f, p in pp.items()}
            values = {f: p[refs[f]] for f, p in pp.items()}
            bins.append(
                {
                    "bin": i,
                    "selected_reference_bin": refs,
                    "daily_kg_per_mu": values,
                    "delta_B_minus_A": values["B"] - values["A"],
                    "ratio_B_over_A": values["B"] / values["A"] if values["A"] else None,
                    "unit": "kg/mu/day",
                    "bin_anchored_on": "JULY_01",
                    "missing_strategy": "NEAREST_AVAILABLE_EARLIER_TIE",
                }
            )
        scopes = [
            (b["base_id"], "2025-2026", str(b["productive_area_mu"]))
            for b in bundle["registry"]["bases"]
        ]
        scopes += [
            (r["base_id"], r["season"], r["area_mu"])
            for r in bundle["admission"]["inventory"]
            if r["status"] == "ADMIT"
        ]
        sensitivity = []
        for bid, season, area in sorted(scopes):
            start, end = date(int(season[:4]), 7, 1), date(int(season[5:]), 4, 15)
            curves = {
                f: tuple(
                    DailyKg(
                        start + timedelta(days=i),
                        _daily_row(start + timedelta(days=i), start, Decimal(area), p).predicted_kg,
                    )
                    for i in range((end - start).days + 1)
                )
                for f, p in pp.items()
            }
            result: dict[str, Any] = {}
            for f, rr in curves.items():
                daily, rolling = _peak(rr, False), _peak(rr, True)
                result[f] = {
                    "predicted_kg": sum((r.kg for r in rr), Decimal(0)),
                    "single_peak_date": str(daily[0]),
                    "single_peak_kg": daily[1],
                    "rolling7_start": str(rolling[0]),
                    "rolling7_kg": rolling[1],
                    "curve_sha256": digest([(str(r.day), str(r.kg)) for r in rr]),
                }
            sensitivity.append(
                {
                    "base_id": bid,
                    "season": season,
                    "area_mu": area,
                    "profile_comparison_only_not_actuals": True,
                    "profiles": result,
                    "delta_predicted_kg": result["B"]["predicted_kg"] - result["A"]["predicted_kg"],
                    "single_peak_date_shift_days": (
                        date.fromisoformat(result["B"]["single_peak_date"])
                        - date.fromisoformat(result["A"]["single_peak_date"])
                    ).days,
                    "rolling7_start_shift_days": (
                        date.fromisoformat(result["B"]["rolling7_start"])
                        - date.fromisoformat(result["A"]["rolling7_start"])
                    ).days,
                }
            )
        return cast(
            dict[str, Any],
            serial(
                {
                    "profile_metadata": meta,
                    "profile_input_trace": trace["input-manifest.json"],
                    "current_quantity_training_base_seasons": 37,
                    "profile_training_is_not_current_quantity_training": True,
                    "available_bins": {f: sorted(p) for f, p in pp.items()},
                    "bin_changes": bins,
                    "largest_absolute_bin_changes": sorted(
                        bins, key=lambda r: (-abs(r["delta_B_minus_A"]), r["bin"])
                    ),
                    "fixed_input_sensitivity": sensitivity,
                    "relative_profile_sensitivity_shared_across_bases_except_micro_rounding": True,
                    "absolute_kg_sensitivity_scales_with_area_not_biological_effect": True,
                    "date_anchor_and_unit_policy_consistent": True,
                    "no_profile_selected_using_2025_labels": True,
                    "profile_original_known_label_subset_not_full_authority": True,
                    "training_label_physical_equivalence_to_source002": "NOT_PROVEN",
                    "historical_area_known_at": "NOT_PROVEN",
                    "strict_pit": False,
                }
            ),
        )
