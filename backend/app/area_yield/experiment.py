"""Private append-only experiment phases; final evaluation cannot be silently rerun.

Preparation handles authorized labels for deterministic splitting. Training never opens
the final label file. Final predictions are persisted before that file is read.
"""

import csv
import hashlib
import json
import os
import platform
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.app.area_yield.data import AreaAuthority, Receipt, calendar, digest, materialize
from backend.app.area_yield.evaluation import compare, summaries
from backend.app.area_yield.model import fit_model, predict


def write_json(path: Path, value: Any) -> None:
    # Exclusive creation: no historical artifact or final result can be overwritten.
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
    path.chmod(0o600)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError("empty artifact")
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    path.chmod(0o600)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def prepare(
    root: Path, config: dict[str, Any], receipts: list[Receipt], code_sha: str
) -> dict[str, Any]:
    validate_config(config)
    if root.exists():
        raise ValueError("new private experiment directory required")
    root.mkdir(parents=True, mode=0o700)
    root.chmod(0o700)
    write_json(root / "experiment_config.json", config)
    authority = AreaAuthority(
        config["scope_id"],
        config["season_id"],
        date.fromisoformat(config["coverage_start"]),
        date.fromisoformat(config["coverage_end"]),
        Decimal(config["area_mu"]),
        config["area_basis"],
        config["area_source"],
        config["complete_ledger_authority"],
    )
    rows = materialize(receipts, authority)
    partitions: dict[str, list[dict[str, str]]] = {"train": [], "development": [], "final": []}
    for row in rows:
        split = (
            "train"
            if row["date"] <= config["train_end"]
            else ("development" if row["date"] <= config["development_end"] else "final")
        )
        row.update(
            {
                "split_assignment": split,
                "source_id": config["source_path"],
                "source_hash": config["source_hash"],
            }
        )
        partitions[split].append(row)
    for name, subset in partitions.items():
        if not subset:
            raise ValueError(f"empty {name} partition")
        write_csv(root / f"{name}.csv", subset)
    write_csv(root / "dataset.csv", rows)
    # This identity-only file can be opened by final prediction without final labels.
    write_csv(
        root / "final_targets.csv",
        [
            {k: r[k] for k in ("scope_id", "season_id", "date", "area_mu")}
            for r in partitions["final"]
        ],
    )
    write_csv(
        root / "area_mapping_audit.csv",
        [
            {
                "scope": config["scope_id"],
                "source": config["source_path"],
                "decision": "INCLUDED",
                "basis": config["area_basis"],
                "reason": "EXACT_OLD_BANNA_DX_ACCEPTANCE_ONLY_NOT_MEASURED_WHOLE_FARM",
                "area_mu": config["area_mu"],
            },
            {
                "scope": "OTHER_SCOPES_IN_2024_2025",
                "source": config["source_path"],
                "decision": "EXCLUDED",
                "basis": "NOT_PROVEN",
                "reason": "NO_MATCHED_AUTHORIZED_AREA_SOURCE_IN_CURRENT_PROJECT_PATHS",
                "area_mu": "",
            },
            {
                "scope": "ALL_2025_2026",
                "source": "data/raw/2025_2026_receipts.xls",
                "decision": "NOT_OPENED",
                "basis": "NOT_PROVEN",
                "reason": "LEGACY_SEALED_BOUNDARY_AND_NO_MATCHED_AREA_NONSEALED_SLICE",
                "area_mu": "",
            },
        ],
    )
    splits = {
        name: {
            "row_count": len(subset),
            "first": subset[0]["date"],
            "last": subset[-1]["date"],
            "file_sha256": file_hash(root / f"{name}.csv"),
        }
        for name, subset in partitions.items()
    }
    write_json(root / "split_manifest.json", splits)
    manifest = {
        "experiment_id": config["experiment_id"],
        "code_sha": code_sha,
        "config_hash": digest(config),
        "source_hash": config["source_hash"],
        "source_path": config["source_path"],
        "scope_count": 1,
        "season_count": 1,
        "receipt_count": len(receipts),
        "daily_count": len(rows),
        "observed_days": sum(r["observation_status"] == "OBSERVED" for r in rows),
        "authorized_zero_days": sum(
            r["observation_status"] == "AUTHORIZED_LEDGER_ZERO" for r in rows
        ),
        "dataset_sha256": file_hash(root / "dataset.csv"),
        "final_targets_sha256": file_hash(root / "final_targets.csv"),
        "splits": splits,
        "area_basis": config["area_basis"],
        "source_availability": "RETROSPECTIVE_NOT_HISTORICAL_PIT",
        "legacy_test_bytes_read": False,
        "python_version": platform.python_version(),
        "training_runs": 0,
        "backtest_runs": 0,
    }
    write_json(root / "data_manifest.json", manifest)
    return manifest


def validate_config(config: dict[str, Any]) -> None:
    if not (
        config["coverage_start"]
        <= config["train_end"]
        < config["development_end"]
        < config["final_end"]
        == config["coverage_end"]
    ):
        raise ValueError("invalid chronological partitions")
    if (
        config["ridge_alpha"] != 10.0
        or config["ridge_solver"] != "svd"
        or config["random_seed"] != 0
        or config["selection"] != "DEVELOPMENT_WAPE_STRICTLY_LOWER_AND_MAE_NOT_HIGHER_ELSE_BASELINE"
        or type(config["complete_ledger_authority"]) is not bool
        or not config["zero_policy"]
    ):
        raise ValueError("configuration does not match fixed R1 implementation")


def context(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    config, manifest = (
        read_json(root / "experiment_config.json"),
        read_json(root / "data_manifest.json"),
    )
    validate_config(config)
    if digest(config) != manifest["config_hash"]:
        raise ValueError("config drift")
    return config, manifest


def partition(root: Path, manifest: dict[str, Any], name: str) -> list[dict[str, str]]:
    path = root / f"{name}.csv"
    if file_hash(path) != manifest["splits"][name]["file_sha256"]:
        raise ValueError("partition drift")
    return read_csv(path)


def prediction_rows(
    rows: list[dict[str, str]], model: dict[str, Any], config: dict[str, Any]
) -> list[Decimal]:
    if any(r["area_mu"] != config["area_mu"] for r in rows):
        raise ValueError("projection area mismatch")
    return predict(
        model,
        [date.fromisoformat(r["date"]) for r in rows],
        Decimal(config["area_mu"]),
        config["scope_id"],
    )


def table_rows(
    rows: list[dict[str, str]],
    models: dict[str, Any],
    predictions: dict[str, list[Decimal]],
    split: str,
) -> list[dict[str, Any]]:
    return [
        {
            "scope_id": row["scope_id"],
            "season_id": row["season_id"],
            "cutoff": models[kind]["training_cutoff"],
            "target_date": row["date"],
            "lead_days": (
                date.fromisoformat(row["date"])
                - date.fromisoformat(models[kind]["training_cutoff"])
            ).days,
            "area_mu": row["area_mu"],
            "actual_kg": row["actual_kg"],
            "baseline_prediction_kg": str(predictions["baseline"][i]),
            "model_prediction_kg": str(predictions[kind][i]),
            "split_id": split,
            "model_kind": kind,
            "model_version": models[kind]["model_version"],
            "observation_status": row["observation_status"],
        }
        for kind in ("baseline", "ridge")
        for i, row in enumerate(rows)
    ]


def lead_metrics(
    rows: list[dict[str, str]],
    predictions: dict[str, list[Decimal]],
    cutoff: date,
    config: dict[str, Any],
) -> dict[str, Any]:
    result = {}
    for lower, upper in config["lead_time_reporting_bands_days"]:
        indices = [
            i
            for i, row in enumerate(rows)
            if lower <= (date.fromisoformat(row["date"]) - cutoff).days <= upper
        ]
        if indices:
            result[f"{lower}_{upper}"] = {
                kind: compare([rows[i] for i in indices], [values[i] for i in indices])
                for kind, values in predictions.items()
            }
    return result


def train(root: Path) -> dict[str, Any]:
    config, manifest = context(root)
    # Created before any fit: repeats cannot become unrecorded adaptive searches.
    write_json(root / "training_started.json", {"config_hash": manifest["config_hash"]})
    training = partition(root, manifest, "train")
    development = partition(root, manifest, "development")
    models = {
        kind: fit_model(training, kind, date.fromisoformat(config["train_end"]), config["scope_id"])
        for kind in ("baseline", "ridge")
    }
    # Prediction interface receives dates/area, not the actual field.
    predictions = {
        kind: prediction_rows(development, model, config) for kind, model in models.items()
    }
    metrics = {kind: compare(development, values) for kind, values in predictions.items()}
    write_json(root / "development_metrics.json", metrics)
    write_json(
        root / "development_lead_metrics.json",
        lead_metrics(development, predictions, date.fromisoformat(config["train_end"]), config),
    )
    write_csv(
        root / "development_predictions.csv",
        table_rows(development, models, predictions, "development"),
    )
    baseline, candidate = metrics["baseline"], metrics["ridge"]
    selected = "baseline"
    if baseline["daily_wape"] is not None and candidate["daily_wape"] is not None:
        if Decimal(candidate["daily_wape"]) < Decimal(baseline["daily_wape"]) and Decimal(
            candidate["daily_mae_kg"]
        ) <= Decimal(baseline["daily_mae_kg"]):
            selected = "ridge"
    # Candidate definitions and hyperparameters do not change after development.
    final_models = {
        kind: fit_model(
            training + development,
            kind,
            date.fromisoformat(config["development_end"]),
            config["scope_id"],
        )
        for kind in ("baseline", "ridge")
    }
    for kind, model in final_models.items():
        write_json(root / f"model_{kind}.json", model)
    write_json(root / "selected_model.json", final_models[selected])
    freeze = {
        "selected": selected,
        "selection_rule": config["selection"],
        "model_hashes": {kind: file_hash(root / f"model_{kind}.json") for kind in final_models},
        "selected_model_sha256": file_hash(root / "selected_model.json"),
        "config_hash": manifest["config_hash"],
        "training_fit_count": 4,
        "baseline_fit_count": 2,
        "candidate_fit_count": 2,
        "development_backtest_count": 2,
        "final_labels_opened_by_training": False,
    }
    write_json(root / "selection_freeze.json", freeze)
    return freeze


def final_evaluate(root: Path) -> dict[str, Any]:
    config, manifest = context(root)
    freeze = read_json(root / "selection_freeze.json")
    if freeze["config_hash"] != manifest["config_hash"]:
        raise ValueError("selection/config drift")
    if file_hash(root / "final_targets.csv") != manifest["final_targets_sha256"]:
        raise ValueError("target identity drift")
    models = {}
    for kind, expected in freeze["model_hashes"].items():
        if file_hash(root / f"model_{kind}.json") != expected:
            raise ValueError("frozen model drift")
        models[kind] = read_json(root / f"model_{kind}.json")
    write_json(
        root / "final_phase_started.json",
        {"selection_freeze_sha256": file_hash(root / "selection_freeze.json")},
    )
    targets = read_csv(root / "final_targets.csv")
    predictions = {kind: prediction_rows(targets, model, config) for kind, model in models.items()}
    write_json(
        root / "final_predictions_before_labels.json",
        {kind: [str(v) for v in values] for kind, values in predictions.items()},
    )
    final = partition(root, manifest, "final")
    if [{k: r[k] for k in targets[0]} for r in final] != targets:
        raise ValueError("label/target identity mismatch")
    metrics = {kind: compare(final, values) for kind, values in predictions.items()}
    all_metrics = {
        "development": read_json(root / "development_metrics.json"),
        "final": metrics,
        "selected_before_final": freeze["selected"],
        "final_phase_count": 1,
        "new_training_fit_count": 4,
        "new_backtest_model_window_count": 4,
        "full_season_backtest_available": False,
        "independent_time_evidence": "IN_SEASON_RETROSPECTIVE_ONLY",
        "business_usability": "NOT_ESTABLISHED",
        "aggregate_scope_weight": "1.000000",
        "lead_time_breakdowns": {
            "development": read_json(root / "development_lead_metrics.json"),
            "final": lead_metrics(
                final, predictions, date.fromisoformat(config["development_end"]), config
            ),
        },
    }
    write_json(root / "metrics.json", all_metrics)
    records: list[dict[str, Any]] = list(read_csv(root / "development_predictions.csv"))
    records += table_rows(final, models, predictions, "final")
    write_csv(root / "backtest_predictions.csv", records)
    return all_metrics


def forecast(
    root: Path, area: Decimal, season_start_year: int, cutoff: date, scope_id: str
) -> dict[str, Any]:
    config, _ = context(root)
    freeze = read_json(root / "selection_freeze.json")
    if file_hash(root / "selected_model.json") != freeze["selected_model_sha256"]:
        raise ValueError("selected model drift")
    model = read_json(root / "selected_model.json")
    start = date(season_start_year, 10, 1)
    end = date(season_start_year + 1, 10, 1) - timedelta(days=1)
    if not date.fromisoformat(model["training_cutoff"]) <= cutoff < start:
        raise ValueError("season forecast cutoff invalid")
    dates = calendar(start, end)
    values = predict(model, dates, area, scope_id)
    write_csv(
        root / "forecast_example.csv",
        [
            {
                "date": day.isoformat(),
                "harvest_quantity_kg": str(value),
                "arrival_quantity_kg": str(value),
                "prediction_area_mu": str(area),
                "reference_scope": scope_id,
                "model_version": model["model_version"],
            }
            for day, value in zip(dates, values, strict=True)
        ],
    )
    result = {
        **summaries(dates, values),
        "area_mu": str(area),
        "scope_id": scope_id,
        "forecast_start": start.isoformat(),
        "forecast_end": end.isoformat(),
        "forecast_cutoff": cutoff.isoformat(),
        "daily_count": len(dates),
        "model_version": model["model_version"],
        "training_cutoff": model["training_cutoff"],
        "selected_kind": model["kind"],
        "process_id": os.getpid(),
        "refit_performed": False,
        "area_basis": config["area_basis"],
        "area_extrapolation": str(area.quantize(Decimal("0.000001")))
        not in model["known_training_areas_mu"],
        "season_position_extrapolation": True,
        "limitations": [
            "ONE_CALIBRATION_DENOMINATOR_NOT_MEASURED_AREA",
            "NO_PRESEASON_FULL_SEASON_HOLDOUT",
            "UNSEEN_SEASON_POSITIONS",
            "NO_CALIBRATED_PROBABILITIES",
            "NOT_GLOBAL_BLIND_OR_STRICT_HISTORICAL_PIT",
        ],
    }
    write_json(root / "forecast_example_summary.json", result)
    return result
