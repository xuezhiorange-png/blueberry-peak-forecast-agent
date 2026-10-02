"""Thin locked train/backtest or artifact-only inference entry; private outputs."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.app.area_yield.area_size_r1 import audit, fit, predict
from backend.app.area_yield.data import fixed
from backend.app.area_yield.evaluation import compare
from backend.app.area_yield.experiment import file_hash, read_csv, read_json, write_json


def score(
    predictions: dict[str, Any], test_rows: list[dict[str, str]], test_daily: list[dict[str, str]]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    by_base = {r["base_id"]: r for r in test_rows}
    if set(by_base) != set(predictions):
        raise ValueError("same cohort required")
    diagnostics = []
    for base_id, prediction in sorted(predictions.items()):
        actuals = sorted(
            (r for r in test_daily if r["base_id"] == base_id), key=lambda r: r["date"]
        )
        if [r["date"] for r in actuals] != [r["date"] for r in prediction["daily_curve"]]:
            raise ValueError("same calendar cohort required")
        quantities = [Decimal(r["predicted_daily_quantity_kg"]) for r in prediction["daily_curve"]]
        rows = [{"date": r["date"], "actual_kg": r["new_quantity_kg"]} for r in actuals]
        metric = compare(rows, quantities)
        actual_total = Decimal(by_base[base_id]["season_total_quantity_kg"])
        predicted_total = Decimal(prediction["predicted_season_total_kg"])
        metric["shape_error_numerator_kg"] = str(
            sum(
                (
                    abs(Decimal(r["actual_kg"]) / actual_total - q / predicted_total) * actual_total
                    for r, q in zip(rows, quantities, strict=True)
                ),
                Decimal(0),
            )
        )
        metric["daily_error_numerator_kg"] = str(
            sum(
                (abs(Decimal(r["actual_kg"]) - q) for r, q in zip(rows, quantities, strict=True)),
                Decimal(0),
            )
        )
        metric["actual_total_kg"] = str(actual_total)
        metric["base_id"] = base_id
        diagnostics.append(metric)
    denominator = sum((Decimal(m["actual_total_kg"]) for m in diagnostics), Decimal(0))

    def aggregate(key: str) -> Decimal:
        return sum((Decimal(str(m[key])) for m in diagnostics), Decimal(0))

    metrics = {
        "cohort_count": len(diagnostics),
        "actual_total_kg": str(denominator),
        "window_total_wape": fixed(aggregate("window_total_absolute_error_kg") / denominator),
        "window_total_mae_kg": fixed(
            aggregate("window_total_absolute_error_kg") / len(diagnostics)
        ),
        "daily_wape": fixed(aggregate("daily_error_numerator_kg") / denominator),
        "shape_micro_wape": fixed(aggregate("shape_error_numerator_kg") / denominator),
    }
    for key in (
        "single_day_peak_date_error_days",
        "single_day_peak_absolute_error_kg",
        "rolling_7day_window_shift_days",
        "rolling_7day_peak_absolute_error_kg",
    ):
        metrics[key + "_mae"] = fixed(aggregate(key) / len(diagnostics))
    return metrics, diagnostics


def run(source: Path, output: Path, config_path: Path) -> dict[str, Any]:
    config = read_json(config_path)
    if output.exists():
        raise ValueError("new private output required; no overwrite")
    input_paths = {
        "training_source": source / "v0-8-canonical-training-dataset-r1.csv",
        "daily_source": source / "training-daily-curves-r1.csv",
    }
    hashes = {key: file_hash(path) for key, path in input_paths.items()}
    if any(hashes[key] != config[key + "_sha256"] for key in hashes):
        raise ValueError("frozen training source identity mismatch")
    if (
        config["candidate_penalty"] != 1.0
        or config["search"] is not False
        or config["train_seasons"] != ["2023-2024"]
        or config["test_season"] != "2024-2025"
        or config["holdout_refitted_into_final_artifact"] is not False
    ):
        raise ValueError("configuration drift")
    output.mkdir(parents=True, mode=0o700)
    output.chmod(0o700)
    write_json(output / "execution-contract.json", config)
    rows = read_csv(input_paths["training_source"])
    daily = read_csv(input_paths["daily_source"])
    coverage = audit(rows, daily)
    coverage.update(
        {
            "EXCLUDED_SAMPLE_COUNT": 41,
            "EXCLUSION_REASONS": (
                "Existing S7 identity-blocked 41/78 training-pool samples stay excluded; "
                "counts cited from frozen S7 report, no unsafe source reread"
            ),
            "raw_receipt_row_count": "NOT_RECONSTRUCTED",
            "source_hashes": hashes,
        }
    )
    write_json(output / "data-coverage-audit.json", coverage)
    train = [r for r in rows if r["season"] == "2023-2024"]
    test = [r for r in rows if r["season"] == "2024-2025"]
    train_daily = [r for r in daily if r["season"] == "2023-2024"]
    identity = {
        **hashes,
        "configuration_hash": file_hash(config_path),
        "code_hash": file_hash(
            Path(__file__).parent.parent / "backend/app/area_yield/area_size_r1.py"
        ),
        "base_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "scope": "NONSEALED_PRIOR_TRAINING_POOL;2025_2026_NOT_OPENED",
    }
    created_at = datetime.now(UTC).isoformat()
    predictions, model_hashes = {}, {}
    for kind in ("baseline", "candidate"):
        model = fit(train, train_daily, kind=kind, identity=identity, created_at=created_at)
        if model != fit(train, train_daily, kind=kind, identity=identity, created_at=created_at):
            raise ValueError("nondeterministic training")
        write_json(output / f"{kind}-artifact.json", model)
        model_hashes[kind] = file_hash(output / f"{kind}-artifact.json")
        predictions[kind] = {
            r["base_id"]: predict(model, r["area_mu"], 2024, r["base_id"]) for r in test
        }
    write_json(output / "predictions-sealed-before-scoring.json", predictions)
    seal = {
        "prediction_file_sha256": file_hash(output / "predictions-sealed-before-scoring.json"),
        "artifact_file_hashes": model_hashes,
        "created_at": created_at,
        "train_seasons": ["2023-2024"],
        "test_season": "2024-2025",
        "train_sample_count": len(train),
        "test_sample_count": len(test),
        "DATA_LEAKAGE_CHECK": "PASS",
        "NEW_UNSEEN_VALIDATION": False,
    }
    write_json(output / "prediction-seal.json", seal)
    test_daily = [r for r in daily if r["season"] == "2024-2025"]
    metrics = {}
    for kind in predictions:
        metrics[kind], diagnostics = score(predictions[kind], test, test_daily)
        write_json(output / f"{kind}-paired-errors.json", diagnostics)
    write_json(output / "metrics.json", metrics)
    request: dict[str, Any] = {
        "area_mu": "736.000000",
        "season_start_year": 2026,
        "base_id": "TEST_ONLY_UNSEEN_BASE",
        "mode": "TEST_ONLY",
    }
    write_json(output / "example-request.json", request)
    expected = predict(
        read_json(output / "candidate-artifact.json"),
        request["area_mu"],
        request["season_start_year"],
        request["base_id"],
    )
    response_path = output / "example-response.json"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.run_next_area_size_r1",
            "predict",
            "--artifact",
            str(output / "candidate-artifact.json"),
            "--request",
            str(output / "example-request.json"),
            "--output",
            str(response_path),
        ],
        check=True,
    )
    if read_json(response_path) != expected:
        raise ValueError("fresh-process mismatch")
    if any(file_hash(path) != hashes[key] for key, path in input_paths.items()):
        raise ValueError("input changed")
    metric_keys = [
        key for key in metrics["baseline"] if key not in {"cohort_count", "actual_total_kg"}
    ]
    deltas = {
        key: {
            "absolute_delta": str(
                Decimal(metrics["candidate"][key]) - Decimal(metrics["baseline"][key])
            ),
            "relative_delta": str(
                Decimal(metrics["candidate"][key]) / Decimal(metrics["baseline"][key]) - 1
            )
            if Decimal(metrics["baseline"][key]) != 0
            else None,
        }
        for key in metric_keys
    }
    receipt = {
        "coverage": coverage,
        "fold": seal,
        "metrics": metrics,
        "example": {key: value for key, value in expected.items() if key != "daily_curve"},
        "fresh_process": "PASS",
        "deterministic_training": "PASS",
        "scientific_result": "RESEARCH_CANDIDATE_NO_STABLE_GAIN",
        "stable_gain": False,
        "stability_reason": (
            "Only one eligible nonsealed forward test season; no cross-fold consistency evidence"
        ),
        "metric_deltas_candidate_minus_baseline": deltas,
        "new_unseen_validation": False,
        "training_area_range": read_json(output / "candidate-artifact.json")[
            "training_area_range_mu"
        ],
        "test_area_range": [
            str(min(Decimal(r["area_mu"]) for r in test)),
            str(max(Decimal(r["area_mu"]) for r in test)),
        ],
    }
    write_json(output / "run-receipt.json", receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    train = commands.add_parser("train-backtest")
    train.add_argument("--source", type=Path, required=True)
    train.add_argument(
        "--config", type=Path, default=Path("configs/next_area_size_experiment_20261002_r1.json")
    )
    train.add_argument("--output", type=Path, required=True)
    inference = commands.add_parser("predict")
    inference.add_argument("--artifact", type=Path, required=True)
    inference.add_argument("--request", type=Path, required=True)
    inference.add_argument("--output", type=Path, required=True)
    replay = commands.add_parser("replay")
    replay.add_argument("--source", type=Path, required=True)
    replay.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "train-backtest":
        result = run(args.source, args.output, args.config)
        print(json.dumps({"metrics": result["metrics"], "fresh_process": result["fresh_process"]}))
    elif args.command == "replay":
        seal = read_json(args.output / "prediction-seal.json")
        config = read_json(args.output / "execution-contract.json")
        for name, key in (
            ("v0-8-canonical-training-dataset-r1.csv", "training_source_sha256"),
            ("training-daily-curves-r1.csv", "daily_source_sha256"),
        ):
            if file_hash(args.source / name) != config[key]:
                raise ValueError("input hash mismatch")
        if (
            file_hash(args.output / "predictions-sealed-before-scoring.json")
            != seal["prediction_file_sha256"]
        ):
            raise ValueError("prediction seal mismatch")
        predictions = read_json(args.output / "predictions-sealed-before-scoring.json")
        rows = [
            r
            for r in read_csv(args.source / "v0-8-canonical-training-dataset-r1.csv")
            if r["season"] == "2024-2025"
        ]
        daily = [
            r
            for r in read_csv(args.source / "training-daily-curves-r1.csv")
            if r["season"] == "2024-2025"
        ]
        saved = read_json(args.output / "metrics.json")
        for kind in ("baseline", "candidate"):
            if (
                file_hash(args.output / f"{kind}-artifact.json")
                != seal["artifact_file_hashes"][kind]
            ):
                raise ValueError("artifact file identity mismatch")
            model = read_json(args.output / f"{kind}-artifact.json")
            for row in rows:
                if (
                    predict(model, row["area_mu"], 2024, row["base_id"])
                    != predictions[kind][row["base_id"]]
                ):
                    raise ValueError("fresh artifact inference mismatch")
            if score(predictions[kind], rows, daily)[0] != saved[kind]:
                raise ValueError("metric replay mismatch")
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "loaded_requests": 44,
                    "metrics_reproduced": True,
                    "model_refit": False,
                }
            )
        )
    else:
        request = read_json(args.request)
        if request.get("mode") != "TEST_ONLY":
            raise ValueError("only TEST_ONLY inference authorized")
        write_json(
            args.output,
            predict(
                read_json(args.artifact),
                request["area_mu"],
                request["season_start_year"],
                request["base_id"],
            ),
        )


if __name__ == "__main__":
    main()
