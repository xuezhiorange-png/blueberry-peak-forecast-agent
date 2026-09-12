"""Separate real training, prediction freeze, evaluation and fresh-load examples."""

import argparse
import json
from decimal import Decimal
from pathlib import Path

from backend.app.area_yield.data import digest
from backend.app.area_yield.experiment import file_hash, read_csv, read_json, write_csv, write_json
from backend.app.area_yield.total_evaluation_r4 import aggregate, compare
from backend.app.area_yield.total_yield_r4 import Area, fit, predict_total, sample
from scripts.run_prior_shape_r3b import verify


def inputs(source: Path, config: dict) -> list[dict[str, str]]:
    verify(source, read_json(source / "artifact_manifest.json"))
    matrix = read_csv(source / "farm_season_qualification.csv")
    rows = []
    for binding in config["bindings"]:
        area = Area(
            binding["farm"],
            binding["productive_area_mu"],
            binding["area_basis"],
            binding["source_reference"],
            digest(binding),
            "FARM",
            True,
        )
        for season in ("2023-2024", "2024-2025"):
            matches = [r for r in matrix if r["farm"] == area.farm and r["season"] == season]
            if len(matches) != 1 or matches[0]["strict_eligible"] != "True":
                raise ValueError("BLOCKED_INCOMPLETE_SEASON_TOTAL")
            row = matches[0]
            if (
                row["active_span_global_unknown_days"] != "0"
                or row["source_completeness"] != "ESTABLISHED"
            ):
                raise ValueError("incomplete source")
            rows.append(sample(area, area.farm, season, row["season_total_kg"], "STRICT_ELIGIBLE"))
    return rows


def train(source: Path, output: Path) -> dict:
    config = read_json(Path("configs/confirmed_total_r4.json"))
    old_area = Path("docs/v0-3/s3/authority/farm_total_area_authority_package.json")
    if file_hash(old_area) != config["source_area_package_hash"]:
        raise ValueError("old area authority drift")
    rows = inputs(source, config)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    write_json(output / "confirmed_area_bindings_r4.json", config)
    write_csv(output / "farm_season_yield_r4.csv", rows)
    training = [r for r in rows if r["season"] == "2023-2024"]
    model = fit(training)
    write_json(output / "model_global_median.json", {"kind": "global", "model": model})
    write_json(output / "model_same_farm_prior.json", {"kind": "prior", "model": model})
    manifest = {
        "config_hash": digest(config),
        "training_rows": training,
        "training_row_count": len(training),
        "training_season": "2023-2024",
        "validation_used_in_fit": False,
        "training_called": True,
        "model_hash": model["hash"],
        "source_qualification_hash": file_hash(source / "farm_season_qualification.csv"),
        "model_files": {
            n: file_hash(output / n)
            for n in ("model_global_median.json", "model_same_farm_prior.json")
        },
        "implementation_hashes": {
            p: file_hash(Path(p))
            for p in (
                "scripts/run_confirmed_total_r4.py",
                "backend/app/area_yield/total_yield_r4.py",
                "backend/app/area_yield/total_evaluation_r4.py",
            )
        },
    }
    write_json(output / "training_manifest_r4.json", manifest)
    return manifest


def load(output: Path) -> tuple[dict, dict]:
    manifest = read_json(output / "training_manifest_r4.json")
    verify(output, manifest["model_files"])
    verify(Path("."), manifest["implementation_hashes"])
    config = read_json(output / "confirmed_area_bindings_r4.json")
    if digest(config) != manifest["config_hash"]:
        raise ValueError("config drift")
    return config, read_json(output / "model_global_median.json")["model"]


def prediction(output: Path) -> dict:
    config, model = load(output)
    rows = [
        {
            "farm": b["farm"],
            "kind": kind,
            **predict_total(model, b["productive_area_mu"], b["farm"], kind),
        }
        for b in config["bindings"]
        for kind in config["models"]
    ]
    result = {
        "prediction_hash": digest(rows),
        "rows": rows,
        "fresh_process_load": True,
        "validation_labels_read": False,
        "fit_called": False,
    }
    write_json(output / "predictions_before_scoring.json", result)
    return result


def evaluate(source: Path, output: Path) -> dict:
    config, model = load(output)
    frozen = read_json(output / "predictions_before_scoring.json")
    if digest(frozen["rows"]) != frozen["prediction_hash"]:
        raise ValueError("prediction drift")
    manifest = read_json(output / "training_manifest_r4.json")
    if file_hash(source / "farm_season_qualification.csv") != manifest["source_qualification_hash"]:
        raise ValueError("source drift")
    write_json(output / "evaluation_started.json", {"evaluation_count": 1, "retry": False})
    validation = {r["farm"]: r for r in inputs(source, config) if r["season"] == "2024-2025"}
    rows = [{"kind": p["kind"], **compare(validation[p["farm"]], p)} for p in frozen["rows"]]
    metrics = {k: aggregate([r for r in rows if r["kind"] == k]) for k in config["models"]}
    prior = all(
        Decimal(metrics["prior"][k]) < Decimal(metrics["global"][k])
        for k in ("yield_mae", "yield_mape", "total_rel_mean")
    )
    selected = "prior" if prior else "global"
    result = {
        "result": "SAME_FARM_PRIOR_YIELD_BEST" if prior else "GLOBAL_YIELD_BASELINE_BEST",
        "selected_kind": selected,
        "macro": metrics,
        "per_farm": rows,
        "evidence_strength": "LIMITED_TWO_FARM_CROSS_SEASON",
        "validation_type": "CROSS_SEASON_OUT_OF_TIME_RETROSPECTIVE",
        "validation_blindness": "NOT_BLIND",
    }
    write_json(output / "cross_season_total_metrics.json", result)
    write_csv(output / "cross_season_total_predictions.csv", rows)
    write_json(output / "selected_total_model.json", {"kind": selected, "model": model})
    return result


def examples(output: Path) -> dict:
    config, model = load(output)
    selected = read_json(output / "selected_total_model.json")
    if selected["model"] != model:
        raise ValueError("selected model mismatch")
    kind = selected["kind"]
    rows = [
        {"farm": b["farm"], **predict_total(model, b["productive_area_mu"], b["farm"], kind)}
        for b in config["bindings"]
    ]
    tests = [
        predict_total(model, a, config["bindings"][0]["farm"], kind) for a in ("100", "500", "1000")
    ]
    values = [Decimal(r["predicted_season_total_kg"]) for r in tests]
    if abs(values[1] - 5 * values[0]) > Decimal("0.000005") or abs(
        values[2] - 2 * values[1]
    ) > Decimal("0.000002"):
        raise ValueError("scaling failure")
    result = {
        "examples": rows,
        "scaling_examples": tests,
        "scaling_pass": True,
        "fresh_process_load": True,
        "fit_called": False,
        "composite_example": False,
    }
    write_json(output / "total_prediction_examples.json", result)
    write_json(
        output / "artifact_manifest.json", {f.name: file_hash(f) for f in sorted(output.iterdir())}
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("train", "predict", "evaluate", "examples"))
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.phase == "train":
        result = train(args.source, args.output)
    elif args.phase == "predict":
        result = prediction(args.output)
    elif args.phase == "evaluate":
        result = evaluate(args.source, args.output)
    else:
        result = examples(args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
