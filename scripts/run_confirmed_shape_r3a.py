"""Local-first phases: qualify/train, fresh-process predict, once-only evaluate."""

import argparse
import json
from datetime import date
from pathlib import Path

from backend.app.area_yield import confirmed_shape_r3a as model
from backend.app.area_yield.data import digest
from backend.app.area_yield.experiment import file_hash, read_csv, read_json, write_csv, write_json
from backend.app.area_yield.ledger_r3a import qualify
from backend.app.area_yield.shape_r3 import season_calendar


def train(root: Path, r3: Path) -> dict:
    config = read_json(Path("configs/shape_r3a_confirmed.json"))
    authority = read_json(r3 / "input_manifest.json")
    inventory_hashes = read_json(r3 / "artifact_manifest.json")["files"]
    for name in ("input_manifest.json", "canonical_daily_shape.csv", "paired_farm_seasons.csv"):
        if file_hash(r3 / name) != inventory_hashes[name]:
            raise ValueError("source artifact hash mismatch")
    if [s["sha256"] for s in authority["sources"][:2]] != config["source_hashes"]:
        raise ValueError("confirmation not bound to sources")
    if not (
        config["complete_export"]
        and config["source_active_farm_absence_is_recorded_zero"]
        and config["global_no_record_is_unknown"]
    ):
        raise ValueError("missing user confirmation")
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    write_json(root / "experiment_config.json", config)
    write_json(
        root / "implementation_hashes.json",
        {
            p: file_hash(Path(p))
            for p in (
                "scripts/run_confirmed_shape_r3a.py",
                "backend/app/area_yield/confirmed_shape_r3a.py",
                "backend/app/area_yield/ledger_r3a.py",
                "configs/shape_r3a_confirmed.json",
            )
        },
    )
    rows = read_csv(r3 / "canonical_daily_shape.csv")
    pairs = read_csv(r3 / "paired_farm_seasons.csv")
    matched = {
        p["canonical_farm"]
        for p in pairs
        if p["season_23_24_available"] == "True" and p["season_24_25_available"] == "True"
    }
    matrices, active_sets, source_calendars = [], [], []
    for i, season in enumerate(("2023-2024", "2024-2025")):
        src = authority["sources"][i]
        matrix, calendar = qualify(
            [r for r in rows if r["season_id"] == season],
            season,
            date.fromisoformat(src["date_min"]),
            date.fromisoformat(src["date_max"]),
            True,
            matched,
        )
        matrices.append(matrix)
        source_calendars.append(calendar)
        active_sets.append({r["date"] for r in calendar if r["source_active_day"]})
        write_csv(root / f"source_active_calendar_{season}.csv", calendar)
    write_csv(root / "farm_season_qualification.csv", matrices[0] + matrices[1])
    eligible = [{r["farm"] for r in m if r["strict_eligible"]} for m in matrices]
    paired = eligible[0] & eligible[1]
    write_csv(
        root / "paired_qualification.csv",
        [
            {
                "farm": f,
                "strict_train": f in eligible[0],
                "strict_validation": f in eligible[1],
                "eligible_cross_season": f in paired,
            }
            for f in sorted(matched)
        ],
    )
    if not paired:
        raise ValueError("no strict paired scope")
    all_curves = {}
    for i, season in enumerate(("2023-2024", "2024-2025")):
        farms = eligible[0] if i == 0 else paired
        curves = {}
        for f in sorted(farms):
            part = [r for r in rows if r["season_id"] == season and r["canonical_farm_id"] == f]
            curves[f] = [
                {
                    "farm": f,
                    "date": r["date"],
                    "quantity": r["daily_harvest_kg"]
                    if r["daily_harvest_kg"]
                    else "0"
                    if r["date"] in active_sets[i]
                    else "",
                    "status": "OBSERVED"
                    if r["daily_harvest_kg"]
                    else "SOURCE_ACTIVE_LEDGER_ZERO"
                    if r["date"] in active_sets[i]
                    else "UNKNOWN_GLOBAL_OR_OUTSIDE_SOURCE_COVERAGE",
                }
                for r in part
            ]
        all_curves[season] = curves
    write_json(root / "train_curves.json", all_curves["2023-2024"])
    write_json(root / "validation_labels.json", all_curves["2024-2025"])
    trained = {
        kind: model.fit(all_curves["2023-2024"], "2023-2024", kind) for kind in config["models"]
    }
    write_json(root / "models.json", trained)
    result = {
        "train_farm_count": len(eligible[0]),
        "validation_strict_farm_count": len(eligible[1]),
        "paired_farm_count": len(paired),
        "paired_farms": sorted(paired),
        "model_fit_count": 2,
        "model_kinds": config["models"],
        "config_hash": digest(config),
        "global_unknown_day_counts": [
            sum(not r["source_active_day"] for r in c) for c in source_calendars
        ],
        "training_season": "2023-2024",
        "training_cutoff": "2024-06-30",
        "validation_used_in_fit": False,
        "source_audit_repeated": False,
        "models_file_sha256": file_hash(root / "models.json"),
        "train_curves_sha256": file_hash(root / "train_curves.json"),
        "validation_labels_sha256": file_hash(root / "validation_labels.json"),
    }
    write_json(root / "training_manifest.json", result)
    return result


def prediction(root: Path) -> dict:
    manifest = read_json(root / "training_manifest.json")
    if file_hash(root / "models.json") != manifest["models_file_sha256"]:
        raise ValueError("models integrity mismatch")
    models = read_json(root / "models.json")
    predictions = {k: model.predict(v, "2024-2025") for k, v in models.items()}
    write_json(root / "predictions_before_scoring.json", predictions)
    result = {
        "fresh_process_load": True,
        "fit_called": False,
        "validation_labels_read": False,
        "prediction_hash": digest(predictions),
        "predicted_days": 365,
        "share_sums": {k: sum(v) for k, v in predictions.items()},
    }
    write_json(root / "prediction_manifest.json", result)
    return result


def evaluate(root: Path) -> dict:
    write_json(root / "evaluation_started.json", {"evaluation_count": 1, "automatic_retry": False})
    train_manifest = read_json(root / "training_manifest.json")
    if file_hash(root / "validation_labels.json") != train_manifest["validation_labels_sha256"]:
        raise ValueError("label integrity mismatch")
    predictions = read_json(root / "predictions_before_scoring.json")
    if digest(predictions) != read_json(root / "prediction_manifest.json")["prediction_hash"]:
        raise ValueError("prediction integrity mismatch")
    config = read_json(root / "experiment_config.json")
    if digest(config) != train_manifest["config_hash"]:
        raise ValueError("policy drift")
    curves = read_json(root / "validation_labels.json")
    days = season_calendar("2024-2025")
    per_farm, daily = [], []
    for farm, rows in sorted(curves.items()):
        actual = model.labels(rows)
        if [r["date"] for r in rows] != [str(d) for d in days]:
            raise ValueError("calendar identity mismatch")
        for kind, prediction in predictions.items():
            per_farm.append(
                {"farm": farm, "model": kind, **model.metrics(days, actual, prediction)}
            )
            for i, row in enumerate(rows):
                daily.append(
                    {
                        "farm": farm,
                        "date": row["date"],
                        "model": kind,
                        "actual_share": actual[i] if actual[i] is not None else "",
                        "predicted_share": prediction[i],
                        "observation_status": row["status"],
                    }
                )
    macros = {k: model.macro([r for r in per_farm if r["model"] == k]) for k in predictions}
    a, b = macros["ridge"], macros["empirical"]
    improved = (
        b["mean_peak_date_error_days"] < a["mean_peak_date_error_days"]
        and b["mean_7day_shift_days"] < a["mean_7day_shift_days"]
        and b["daily_share_mae"] <= a["daily_share_mae"]
        and b["daily_share_wape"] <= a["daily_share_wape"]
    )
    selected = "empirical" if improved else "ridge"
    write_csv(root / "cross_season_predictions.csv", daily)
    write_csv(root / "per_farm_metrics.csv", per_farm)
    result = {
        "result": "CROSS_SEASON_SHAPE_MODEL_TRAINED",
        "selected_shape_model": selected,
        "improved_over_ridge": improved,
        "macro": macros,
        "per_farm": per_farm,
        "validation_blindness": "NOT_BLIND",
        "kg_metrics_computed": False,
        "known_ledger_share_validation_only": True,
        "full_unobserved_season_truth_proven": False,
        "candidate_retuning_performed": False,
    }
    write_json(root / "cross_season_metrics.json", result)
    write_json(root / "selected_shape_model.json", read_json(root / "models.json")[selected])
    write_json(
        root / "artifact_manifest.json",
        {f.name: file_hash(f) for f in sorted(root.iterdir()) if f.is_file()},
    )
    return result


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("phase", choices=("train", "predict", "evaluate"))
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--r3", type=Path)
    args = p.parse_args()
    if args.phase == "train":
        if args.r3 is None:
            p.error("train requires --r3")
        result = train(args.output, args.r3)
    elif args.phase == "predict":
        result = prediction(args.output)
    else:
        result = evaluate(args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
