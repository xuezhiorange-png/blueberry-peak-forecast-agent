"""Append-only qualify -> apply frozen business window -> evaluate; never fit."""

import argparse
from dataclasses import asdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.app.area_yield import confirmed_shape_r3a as shape
from backend.app.area_yield import total_evaluation_r4 as total_metrics
from backend.app.area_yield.business_boundary_r7b import (
    END,
    POLICY,
    START,
    apply_window,
    qualify_window,
    window_rows,
)
from backend.app.area_yield.censor_r3c import evaluation_status
from backend.app.area_yield.composite_r5 import best, compose
from backend.app.area_yield.composite_r5 import evaluate as composite_metrics
from backend.app.area_yield.data import digest
from backend.app.area_yield.experiment import file_hash, read_json, write_csv, write_json
from backend.app.area_yield.prior_shape_r3b import aggregate, conditional_metrics
from backend.app.area_yield.rolling_comparison_r7 import origin_one_parity
from backend.app.area_yield.total_yield_r4 import emit, positive
from scripts.run_frozen_evidence_expansion_r6 import COMPOSITES, checked, load_seal, seal

R7_MANIFEST_HASH = "44d9ff2f7fa88dd9c326aaa2c7ed3e736b9b4637df3633c3db69392625596581"


def implementation() -> dict[str, str]:
    paths = sorted(Path("backend/app/area_yield").glob("*.py")) + [
        Path(__file__),
        Path("scripts/run_frozen_evidence_expansion_r6.py"),
    ]
    return {str(p): file_hash(p) for p in paths}


def qualify(root: Path, out: Path) -> dict[str, Any]:
    old = root / "three-season-r7"
    manifest = read_json(checked(old / "artifact_manifest.json", R7_MANIFEST_HASH))
    for name, h in manifest.items():
        checked(old / name, h)
    frozen = read_json(old / "origin_2_predictions_before_scoring.json")
    if digest(frozen["predictions"]) != frozen["prediction_hash"]:
        raise ValueError("R7 prediction identity mismatch")
    q = read_json(old / "qualification.json")
    labels = read_json(old / "validation_labels.json")
    qualified = {
        f: asdict(qualify_window(q["validation"][f], rows, q["train"][f]["shape_evaluable"]))
        for f, rows in labels.items()
    }
    out.mkdir(parents=True, mode=0o700, exist_ok=False)
    old_hashes = read_json(old / "old_artifact_hashes.json")
    old_hashes.update(
        {str(p.relative_to(root)): file_hash(p) for p in sorted(old.rglob("*")) if p.is_file()}
    )
    write_json(out / "old_artifact_hashes.json", old_hashes)
    write_json(
        out / "boundary_authority.json",
        {
            "policy": POLICY,
            "business_start": str(START),
            "business_end": str(END),
            "authority": "USER_CONFIRMED",
            "source_right_truncated": False,
            "business_season_complete": True,
            "post_window_class": "TAIL_FRUIT_OUT_OF_SCOPE",
            "previous_seasons_changed": False,
            "no_fit": True,
            "r7_manifest_hash": R7_MANIFEST_HASH,
            "r7_prediction_hash": frozen["prediction_hash"],
            "r7_partial_status_cause": "INCORRECT_SEASON_BOUNDARY_INTERPRETATION",
            "unknown_within_window_unchanged": True,
            "qualification_rule": "R6_ACTIVE_SPAN_UNKNOWN_WITH_USER_CONFIRMED_BUSINESS_BOUNDARIES",
            "selection_rule": "R5_UNIQUE_PARETO_DOMINANCE_OTHERWISE_NO_CLEAR_WINNER",
            "direction_rule": "PRIOR_TOTAL_AND_PRIOR_SHAPE_BOTH_IMPROVE_ON_SAME_TWO_FARMS",
            "validation_blindness": "NOT_BLIND_POST_R7_USER_BOUNDARY_CORRECTION",
        },
    )
    write_json(out / "qualification.json", qualified)
    write_csv(out / "qualification_r7b.csv", list(qualified.values()))
    write_json(out / "raw_predictions.json", frozen)
    write_json(out / "business_labels.json", {f: window_rows(rows) for f, rows in labels.items()})
    write_json(
        out / "tail_exclusion_audit.json",
        {
            f: {
                "tail_recorded_kg": emit(
                    sum(
                        (
                            Decimal(r["quantity"])
                            for r in rows
                            if r["date"] > str(END) and r["quantity"] != ""
                        ),
                        Decimal(0),
                    )
                ),
                "data_class": "TAIL_FRUIT_OUT_OF_SCOPE",
                "included_in_metrics": False,
                "in_window_unknown_days": sum(r["quantity"] == "" for r in window_rows(rows)),
            }
            for f, rows in labels.items()
        },
    )
    write_json(out / "origin_1_reference.json", read_json(old / "origin_1_reference.json"))
    write_json(out / "implementation_hashes.json", implementation())
    seal(out, "qualification_freeze.json")
    return {
        "shape_eligible": sum(v["shape_evaluable"] for v in qualified.values()),
        "total_eligible": sum(v["total_evaluable"] for v in qualified.values()),
    }


def verify_code(out: Path) -> None:
    if implementation() != load_seal(
        out, "qualification_freeze.json", "implementation_hashes.json"
    ):
        raise ValueError("execution code drift")


def predict(out: Path) -> dict[str, Any]:
    """Reads frozen predictions, not validation labels or training APIs."""
    verify_code(out)
    raw = load_seal(out, "qualification_freeze.json", "raw_predictions.json")
    if digest(raw["predictions"]) != raw["prediction_hash"]:
        raise ValueError("raw prediction hash mismatch")
    result = []
    for p in raw["predictions"]:
        windows = {k: apply_window(v) for k, v in p["shapes"].items()}
        composites = (
            {
                c: {
                    "total": p["totals"][t],
                    "shares": windows[s]["shares"],
                    "daily_kg": [
                        str(v)
                        for v in compose(
                            p["totals"][t]["predicted_season_total_kg"], windows[s]["shares"]
                        )
                    ],
                }
                for c, (t, s) in COMPOSITES.items()
            }
            if p["totals"]
            else {}
        )
        result.append(
            {"farm": p["farm"], "totals": p["totals"], "windows": windows, "composites": composites}
        )
    frozen = {
        "predictions": result,
        "prediction_hash": digest(result),
        "raw_prediction_hash": raw["prediction_hash"],
        "policy": POLICY,
        "qualification_freeze_hash": file_hash(out / "qualification_freeze.json"),
        "fit_called": False,
        "validation_labels_read": False,
    }
    write_json(out / "predictions_before_scoring.json", frozen)
    seal(out, "prediction_freeze.json")
    return {k: v for k, v in frozen.items() if k != "predictions"}


def macro_composites(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for c in COMPOSITES:
        part = [r for r in rows if r["composite"] == c]
        if part:
            result.append(
                {
                    "composite": c,
                    "farm_count": len(part),
                    **{
                        k: emit(sum((Decimal(str(r[k])) for r in part), Decimal(0)) / len(part))
                        if all(r[k] is not None for r in part)
                        else None
                        for k in (
                            "total_rel_error",
                            "daily_mae_kg",
                            "daily_wape",
                            "known_support_wape",
                            "peak_date_error_days",
                            "seven_day_shift_days",
                        )
                    },
                }
            )
    return result


def conclusion(
    reference: dict[str, Any],
    total: dict[str, Any],
    shapes: dict[str, Any],
    composites: list[dict[str, Any]],
    farm_best: dict[str, str],
) -> dict[str, Any]:
    macro = macro_composites(composites)
    winner = best(macro) if macro else "NO_CLEAR_WINNER"
    # Component direction uses the SAME two total farms, not the larger shape denominator.
    paired = shapes["total_farm_common_macro"]
    complete = total["farm_count"] == 2 and all(
        paired[k]["farm_count"] == 2 for k in ("ridge", "prior")
    )
    stable = (
        complete
        and Decimal(total["macro"]["prior"]["total_rel_mean"])
        < Decimal(total["macro"]["global"]["total_rel_mean"])
        and all(
            paired["prior"][k]["mean"] < paired["ridge"][k]["mean"]
            for k in ("peak_date_error_days", "rolling_7day_window_shift_days")
        )
    )
    return {
        "origin_1_parity": "PASS"
        if origin_one_parity(reference["r5"], reference["r6"])
        else "FAIL",
        "origin_1_macro_best": reference["r5"]["macro_best"],
        "origin_2_macro_best": winner,
        "b2_replicated": reference["r5"]["macro_best"] == winner == "B2",
        "cross_season_direction_stable": stable,
        "direction_evidence_complete": complete,
        "farm_heterogeneity_persists": heterogeneity(farm_best),
        "macro": macro,
        "farm_best": farm_best,
        "business_windows_differ_across_origins": True,
        "model_fit_called": False,
    }


def heterogeneity(farm_best: dict[str, str]) -> bool | str:
    if len(farm_best) != 2 or any(v not in COMPOSITES for v in farm_best.values()):
        return "NOT_ESTABLISHED"
    return len(set(farm_best.values())) > 1


def evaluate(root: Path, out: Path) -> dict[str, Any]:
    verify_code(out)
    frozen = load_seal(out, "prediction_freeze.json", "predictions_before_scoring.json")
    if digest(frozen["predictions"]) != frozen["prediction_hash"] or frozen[
        "qualification_freeze_hash"
    ] != file_hash(out / "qualification_freeze.json"):
        raise ValueError("prediction freeze mismatch")
    q = load_seal(out, "qualification_freeze.json", "qualification.json")
    write_json(out / "evaluation_started.json", {"prediction_hash": frozen["prediction_hash"]})
    labels = load_seal(out, "qualification_freeze.json", "business_labels.json")
    days = [START + timedelta(days=i) for i in range((END - START).days + 1)]
    total_rows, shape_rows, composite_rows = [], [], []
    for p in frozen["predictions"]:
        f, observed = p["farm"], labels[p["farm"]]
        if [r["date"] for r in observed] != [str(d) for d in days]:
            raise ValueError("business label date mismatch")
        if not q[f]["shape_evaluable"]:
            continue
        for k, w in p["windows"].items():
            m = conditional_metrics(days, shape.labels(observed), w["shares"])
            peak, week = (
                date.fromisoformat(m["predicted_peak_date"]),
                date.fromisoformat(m["predicted_7day_start"]),
            )
            m["peak_evaluation_status"] = evaluation_status(
                peak, peak, START, END, m["predicted_peak_has_known_label"]
            )
            m["seven_day_evaluation_status"] = evaluation_status(
                week, week + timedelta(days=6), START, END, m["predicted_7day_has_complete_labels"]
            )
            shape_rows.append(
                {"farm": f, "model": k, "out_of_scope_prediction_mass": w["post_window_mass"], **m}
            )
        if not q[f]["total_evaluable"]:
            continue
        actual_total = sum(
            (Decimal(r["quantity"]) for r in observed if r["quantity"] != ""), Decimal(0)
        )
        actual = {
            "farm": f,
            "area_mu": q[f]["productive_area_mu"],
            "total_kg": emit(actual_total),
            "yield_kg_per_mu": emit(actual_total / positive(q[f]["productive_area_mu"])),
        }
        for k, prediction in p["totals"].items():
            total_rows.append({"model": k, **total_metrics.compare(actual, prediction)})
        for c, cp in p["composites"].items():
            m = composite_metrics(
                observed,
                cp["total"]["predicted_season_total_kg"],
                cp["shares"],
                str(START),
                str(END),
            )
            composite_rows.append({"farm": f, "composite": c, **m})
    common = sorted(
        f
        for f, v in q.items()
        if v["shape_evaluable"]
        and all(
            r["peak_evaluation_status"] == "EXACT_COMPUTABLE"
            and r["seven_day_evaluation_status"] == "EXACT_COMPUTABLE"
            for r in shape_rows
            if r["farm"] == f
        )
    )
    total_farms = sorted({r["farm"] for r in total_rows})
    total_result = {
        "farm_count": len(total_farms),
        "per_farm": total_rows,
        "macro": {
            k: total_metrics.aggregate([r for r in total_rows if r["model"] == k])
            for k in ("global", "prior")
        }
        if total_rows
        else {},
    }
    shapes = {
        "strict_pair_count": sum(v["shape_evaluable"] for v in q.values()),
        "common_exact_farms": common,
        "per_farm": shape_rows,
        "common_macro": {
            k: aggregate([r for r in shape_rows if r["farm"] in common and r["model"] == k])
            for k in ("ridge", "prior")
        },
        "total_farm_common_macro": {
            k: aggregate(
                [
                    r
                    for r in shape_rows
                    if r["farm"] in common and r["farm"] in total_farms and r["model"] == k
                ]
            )
            for k in ("ridge", "prior")
        },
    }
    farm_best = {f: best([r for r in composite_rows if r["farm"] == f]) for f in total_farms}
    comparison = conclusion(
        load_seal(out, "qualification_freeze.json", "origin_1_reference.json"),
        total_result,
        shapes,
        composite_rows,
        farm_best,
    )
    write_json(out / "total_metrics_r7b.json", total_result)
    write_json(out / "shape_metrics_r7b.json", shapes)
    write_json(
        out / "composite_metrics_r7b.json",
        {
            "per_farm": composite_rows,
            "farm_count": len(total_farms),
            "macro": comparison["macro"],
            "farm_best": farm_best,
            "mass_balance_pass": bool(composite_rows)
            and all(r["mass_balance_pass"] for r in composite_rows),
        },
    )
    write_json(out / "three_season_comparison_r7b.json", comparison)
    if composite_rows:
        write_csv(out / "per_farm_comparison_r7b.csv", composite_rows)
    for name, h in load_seal(out, "qualification_freeze.json", "old_artifact_hashes.json").items():
        checked(root / name, h)
    seal(out, "artifact_manifest.json")
    return {
        "total_farms": len(total_farms),
        "shape_strict": shapes["strict_pair_count"],
        "shape_exact": len(common),
        "macro_best": comparison["origin_2_macro_best"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("qualify", "predict", "evaluate"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = (
        qualify(args.root, args.output)
        if args.phase == "qualify"
        else predict(args.output)
        if args.phase == "predict"
        else evaluate(args.root, args.output)
    )
    print(result)


if __name__ == "__main__":
    main()
