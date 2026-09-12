"""Load frozen components, freeze composite predictions, then evaluate once."""

import argparse
import json
from decimal import Decimal
from pathlib import Path

from backend.app.area_yield.composite_r5 import best, compose, evaluate
from backend.app.area_yield.data import digest
from backend.app.area_yield.evaluation import summaries
from backend.app.area_yield.experiment import file_hash, read_csv, read_json, write_csv, write_json
from backend.app.area_yield.shape_r3 import season_calendar
from backend.app.area_yield.total_yield_r4 import emit, predict_total
from scripts.run_prior_shape_r3b import verify


def prepare(root: Path, out: Path) -> dict:
    config = read_json(Path("configs/composite_r5.json"))
    sources = {
        n: read_json(root / n / "artifact_manifest.json")
        for n in ("shape-r3a-confirmed", "shape-r3b", "shape-r3c", "total-yield-r4-confirmed")
    }
    for name, hashes in sources.items():
        verify(root / name, hashes)
    shape = read_json(root / "shape-r3b/predictions.json")
    ridge = read_json(root / "shape-r3a-confirmed/predictions_before_scoring.json")["ridge"]
    models = {
        k: read_json(root / "total-yield-r4-confirmed" / f)["model"]
        for k, f in (
            ("global", "model_global_median.json"),
            ("prior", "model_same_farm_prior.json"),
        )
    }
    predictions = []
    for farm, area in config["farms"].items():
        if shape[farm]["ridge"] != ridge:
            raise ValueError("global shape drift")
        for identity, (total_kind, shape_kind) in config["composites"].items():
            total = predict_total(models[total_kind], area, farm, total_kind)
            daily = compose(total["predicted_season_total_kg"], shape[farm][shape_kind])
            predictions.append(
                {
                    "farm": farm,
                    "composite": identity,
                    "total_model": total_kind,
                    "shape_model": shape_kind,
                    **total,
                    "shares": shape[farm][shape_kind],
                    "daily_kg": [str(v) for v in daily],
                }
            )
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    manifest = {
        "config": config,
        "config_hash": digest(config),
        "source_artifact_hashes": sources,
        "prediction_hash": digest(predictions),
        "fresh_process_load": True,
        "fit_called": False,
        "validation_labels_parsed": False,
        "shape_basis": "FROZEN_R3A_R3B_NORMALIZED_PREDICTION_ARTIFACTS",
        "implementation_hashes": {
            p: file_hash(Path(p))
            for p in ("scripts/run_composite_r5.py", "backend/app/area_yield/composite_r5.py")
        },
    }
    write_json(out / "component_manifest.json", manifest)
    write_json(out / "predictions_before_scoring.json", predictions)
    return {k: v for k, v in manifest.items() if k != "source_artifact_hashes"}


def verify_load(root: Path, out: Path) -> tuple[dict, list]:
    manifest = read_json(out / "component_manifest.json")
    for name, hashes in manifest["source_artifact_hashes"].items():
        verify(root / name, hashes)
    verify(Path("."), manifest["implementation_hashes"])
    predictions = read_json(out / "predictions_before_scoring.json")
    if (
        digest(predictions) != manifest["prediction_hash"]
        or digest(manifest["config"]) != manifest["config_hash"]
    ):
        raise ValueError("frozen payload drift")
    return manifest, predictions


def score(root: Path, out: Path) -> dict:
    manifest, predictions = verify_load(root, out)
    config = manifest["config"]
    write_json(out / "evaluation_started.json", {"count": 1, "retry": False})
    labels = read_json(root / "shape-r3a-confirmed/validation_labels.json")
    qualification = read_csv(root / "shape-r3a-confirmed/farm_season_qualification.csv")
    days = season_calendar(config["validation_season"])
    rows, daily = [], []
    for p in predictions:
        farm = p["farm"]
        q = [
            r
            for r in qualification
            if r["farm"] == farm and r["season"] == config["validation_season"]
        ]
        if len(q) != 1 or q[0]["strict_eligible"] != "True":
            raise ValueError("invalid total qualification")
        if [r["date"] for r in labels[farm]] != [str(d) for d in days]:
            raise ValueError("date drift")
        metrics = evaluate(
            labels[farm],
            p["predicted_season_total_kg"],
            p["shares"],
            q[0]["file_start"],
            q[0]["file_end"],
        )
        if Decimal(metrics["actual_total_kg"]) != Decimal(q[0]["season_total_kg"]):
            raise ValueError("actual total disagreement")
        if [str(v) for v in compose(p["predicted_season_total_kg"], p["shares"])] != p["daily_kg"]:
            raise ValueError("daily prediction drift")
        row = {
            k: p[k]
            for k in (
                "farm",
                "composite",
                "total_model",
                "shape_model",
                "requested_area_mu",
                "predicted_yield_kg_per_mu",
            )
        }
        rows.append({**row, **metrics})
        daily.extend(
            {
                "farm": farm,
                "composite": p["composite"],
                "date": str(d),
                "actual_kg": labels[farm][i]["quantity"],
                "predicted_daily_kg": p["daily_kg"][i],
                "prediction_share": p["shares"][i],
            }
            for i, d in enumerate(days)
        )
    bykey = {(r["farm"], r["composite"]): r for r in rows}
    effects = []
    keys = (
        "total_rel_error",
        "daily_mae_kg",
        "daily_wape",
        "peak_date_error_days",
        "seven_day_shift_days",
    )
    for farm in config["farms"]:
        for kind, first, second in (
            ("TOTAL_AT_GLOBAL_SHAPE", "A1", "B1"),
            ("TOTAL_AT_PRIOR_SHAPE", "A2", "B2"),
            ("SHAPE_AT_GLOBAL_TOTAL", "A1", "A2"),
            ("SHAPE_AT_PRIOR_TOTAL", "B1", "B2"),
        ):
            a, b = bykey[farm, first], bykey[farm, second]
            if kind.startswith("SHAPE") and a["total_rel_error"] != b["total_rel_error"]:
                raise ValueError("shape changed total error")
            if kind.startswith("TOTAL") and (
                a["predicted_peak_date"] != b["predicted_peak_date"]
                or a["predicted_7day_start"] != b["predicted_7day_start"]
            ):
                raise ValueError("total changed peak timing")
            effects.append(
                {
                    "farm": farm,
                    "effect": kind,
                    "from": first,
                    "to": second,
                    "delta_to_minus_from": {
                        k: emit(Decimal(str(b[k])) - Decimal(str(a[k])))
                        if a[k] is not None and b[k] is not None
                        else None
                        for k in keys
                    },
                }
            )
    macros = []
    for c in config["composites"]:
        part = [r for r in rows if r["composite"] == c]
        macros.append(
            {
                "composite": c,
                "farm_count": len(part),
                **{
                    k: emit(sum((Decimal(str(r[k])) for r in part), Decimal(0)) / len(part))
                    if all(r[k] is not None for r in part)
                    else None
                    for k in (
                        *keys,
                        "known_support_wape",
                        "unknown_prediction_mass",
                        "peak_quantity_abs_error_kg",
                        "seven_day_quantity_abs_error_kg",
                    )
                },
            }
        )
    farm_best = {f: best([r for r in rows if r["farm"] == f]) for f in config["farms"]}
    result = {
        "per_farm": rows,
        "macro": macros,
        "farm_best": farm_best,
        "macro_best": best(macros),
        "farm_heterogeneity_observed": len(set(farm_best.values())) > 1,
        "mass_balance_pass": True,
        "evidence_strength": "LIMITED_TWO_FARM_CROSS_SEASON",
        "full_unobserved_biological_total_proven": False,
    }
    write_csv(out / "composite_predictions.csv", daily)
    write_csv(out / "per_farm_comparison.csv", rows)
    write_json(out / "composite_metrics.json", result)
    write_json(out / "component_effects.json", effects)
    write_json(
        out / "selected_limited_composite.json",
        {
            "status": "CURRENT_BEST_LIMITED_EVIDENCE_COMPOSITE",
            "macro_best": result["macro_best"],
            "farm_best": farm_best,
            "production_approved": False,
        },
    )
    return result


def example(root: Path, out: Path) -> dict:
    manifest, predictions = verify_load(root, out)
    config = manifest["config"]
    p = next(
        p
        for p in predictions
        if p["farm"] == next(iter(config["farms"]))
        and p["composite"] == config["example_composite"]
    )
    days = season_calendar(config["example_season"])
    if len(days) != len(p["daily_kg"]):
        raise ValueError("example calendar needs explicit mapping")
    quantities = [Decimal(v) for v in p["daily_kg"]]
    result = {
        "farm": p["farm"],
        "requested_area_mu": p["requested_area_mu"],
        "predicted_yield_kg_per_mu": p["predicted_yield_kg_per_mu"],
        "composite": p["composite"],
        "forecast_start": str(days[0]),
        "forecast_end": str(days[-1]),
        "forecast_example_only": True,
        "accuracy_evidence": False,
        **summaries(days, quantities),
    }
    write_csv(
        out / "forecast_example.csv",
        [
            {"date": str(d), "predicted_daily_kg": str(v)}
            for d, v in zip(days, quantities, strict=True)
        ],
    )
    write_json(out / "forecast_example_summary.json", result)
    write_json(
        out / "artifact_manifest.json", {f.name: file_hash(f) for f in sorted(out.iterdir())}
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("prepare", "score", "example"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    operation = {"prepare": prepare, "score": score, "example": example}[args.phase]
    print(json.dumps(operation(args.root, args.output), ensure_ascii=False, indent=2))
