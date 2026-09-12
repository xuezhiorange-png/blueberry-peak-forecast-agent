"""Freeze predictions first; separately evaluate once. Never changes R3A artifacts."""

import argparse
import json
from pathlib import Path

from backend.app.area_yield.confirmed_shape_r3a import labels
from backend.app.area_yield.data import digest
from backend.app.area_yield.experiment import file_hash, read_json, write_csv, write_json
from backend.app.area_yield.prior_shape_r3b import (
    aggregate,
    carry_forward,
    conditional_metrics,
    select,
)
from backend.app.area_yield.shape_r3 import season_calendar


def verify(source: Path, hashes: dict) -> None:
    if any(file_hash(source / name) != value for name, value in hashes.items()):
        raise ValueError("R3A artifact changed")


def prepare(source: Path, output: Path) -> dict:
    hashes = read_json(source / "artifact_manifest.json")
    verify(source, hashes)
    config = read_json(Path("configs/shape_r3b.json"))
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    write_json(output / "experiment_config.json", config)
    write_json(output / "source_hashes.json", hashes)
    curves = read_json(source / "train_curves.json")
    global_predictions = read_json(source / "predictions_before_scoring.json")
    manifest = read_json(source / "prediction_manifest.json")
    if digest(global_predictions) != manifest["prediction_hash"]:
        raise ValueError("global prediction identity mismatch")
    predictions = {
        farm: {**global_predictions, "prior": carry_forward(farm, curves[farm])}
        for farm in config["farms"]
    }
    write_json(output / "predictions.json", predictions)
    freeze = {
        "config_hash": digest(config),
        "prediction_hash": digest(predictions),
        "validation_labels_read_for_prediction": False,
        "global_models_refitted": False,
        "implementation_hashes": {
            name: file_hash(Path(name))
            for name in (
                "scripts/run_prior_shape_r3b.py",
                "backend/app/area_yield/prior_shape_r3b.py",
                "backend/app/area_yield/confirmed_shape_r3a.py",
            )
        },
    }
    write_json(output / "prediction_freeze.json", freeze)
    return freeze


def evaluate(source: Path, output: Path) -> dict:
    verify(source, read_json(output / "source_hashes.json"))
    freeze = read_json(output / "prediction_freeze.json")
    verify(Path("."), freeze["implementation_hashes"])
    config = read_json(output / "experiment_config.json")
    predictions = read_json(output / "predictions.json")
    if digest(config) != freeze["config_hash"] or digest(predictions) != freeze["prediction_hash"]:
        raise ValueError("frozen identity mismatch")
    write_json(output / "evaluation_started.json", {"count": 1, "retry": False})
    curves = read_json(source / "validation_labels.json")
    days = season_calendar("2024-2025")
    rows, daily = [], []
    for farm in config["farms"]:
        actual = labels(curves[farm])
        if [r["date"] for r in curves[farm]] != [str(d) for d in days]:
            raise ValueError("calendar mismatch")
        for kind in config["models"]:
            prediction = predictions[farm][kind]
            rows.append(
                {"farm": farm, "model": kind, **conditional_metrics(days, actual, prediction)}
            )
            for i, d in enumerate(days):
                daily.append(
                    {
                        "farm": farm,
                        "model": kind,
                        "date": str(d),
                        "actual_share": actual[i] if actual[i] is not None else "",
                        "prediction_share": prediction[i],
                    }
                )
    macros = {k: aggregate([r for r in rows if r["model"] == k]) for k in config["models"]}
    result = {
        "result": select(macros, len(config["farms"])),
        "macro": macros,
        "per_farm": rows,
        "validation_blindness": "NOT_BLIND",
        "prediction_hash": freeze["prediction_hash"],
        "config_hash": freeze["config_hash"],
        "r3a_artifact_changed": False,
    }
    write_json(output / "metrics.json", result)
    write_csv(output / "per_farm_metrics.csv", rows)
    write_csv(output / "daily_predictions.csv", daily)
    verify(source, read_json(output / "source_hashes.json"))
    write_json(
        output / "artifact_manifest.json",
        {f.name: file_hash(f) for f in sorted(output.iterdir()) if f.is_file()},
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("prepare", "evaluate"))
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = (prepare if args.phase == "prepare" else evaluate)(args.source, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
