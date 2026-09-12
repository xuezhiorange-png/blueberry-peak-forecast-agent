"""R2 rolling selection, once-only known benchmark, then one deployment-candidate refit.

No existing model is deployed/replaced. All files exclusive-created outside R1.
"""

import os
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.app.area_yield import model as r1_model
from backend.app.area_yield import spline_r2
from backend.app.area_yield.data import calendar, digest, fixed
from backend.app.area_yield.evaluation import compare, summaries
from backend.app.area_yield.experiment import file_hash, read_csv, read_json, write_csv, write_json

KINDS = ("baseline", "ridge", "spline")


def split_windows(config: dict[str, Any]) -> list[dict[str, Any]]:
    windows = []
    for origin in config["origins"]:
        cutoff = date.fromisoformat(origin)
        for days in config["window_days"]:
            end = cutoff + timedelta(days=days)
            if end > date.fromisoformat(config["development_label_end"]):
                continue
            windows.append(
                {
                    "id": f"{origin}_{days}d",
                    "cutoff": cutoff,
                    "start": cutoff + timedelta(days=1),
                    "end": end,
                    "days": days,
                }
            )
    return windows


def select_kind(results: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    keys = list(
        dict.fromkeys(config["selection_priority"] + config["development_non_regression_metrics"])
    )
    means = {
        kind: {
            key: sum((Decimal(str(r["metrics"][kind][key])) for r in results), Decimal(0))
            / len(results)
            for key in keys
        }
        for kind in KINDS
    }
    eligible = [
        kind
        for kind in KINDS
        if all(
            means[kind][key] <= means["ridge"][key]
            for key in config["development_non_regression_metrics"]
        )
    ]
    selected = min(
        eligible,
        key=lambda k: (
            *(means[k][key] for key in config["selection_priority"]),
            config["tie_order"].index(k),
        ),
    )
    return {
        "selected": selected,
        "eligible_non_regression": eligible,
        "macro_means": {
            kind: {key: fixed(v) for key, v in values.items()} for kind, values in means.items()
        },
        "selection_priority": config["selection_priority"],
        "benchmark_used_for_selection": False,
    }


def fit_kind(rows: list[dict[str, str]], kind: str, cutoff: date, scope: str) -> dict[str, Any]:
    return (
        spline_r2.fit(rows, cutoff, scope)
        if kind == "spline"
        else r1_model.fit_model(rows, kind, cutoff, scope)
    )


def predict_kind(
    model: dict[str, Any], dates: list[date], area: Decimal, scope: str
) -> list[Decimal]:
    return (
        spline_r2.predict(model, dates, area, scope)
        if model["kind"] == "spline"
        else r1_model.predict(model, dates, area, scope)
    )


def source_rows(r1: Path, name: str, config: dict[str, Any]) -> list[dict[str, str]]:
    path = r1 / f"{name}.csv"
    if file_hash(path) != config[f"r1_{name}_sha256"]:
        raise ValueError(f"R1 {name} identity drift")
    rows = read_csv(path)
    if any(
        r["scope_id"] != config["scope_id"]
        or r["area_mu"] != config["area_mu"]
        or r["area_basis"] != "AUTHORIZED_CALIBRATION"
        for r in rows
    ):
        raise ValueError("R1 scope/area mismatch")
    return rows


def snapshot(r1: Path) -> dict[str, str]:
    return {p.name: file_hash(p) for p in sorted(r1.iterdir()) if p.is_file()}


def project_table(
    rows: list[dict[str, str]],
    values: dict[str, list[Decimal]],
    models: dict[str, Any],
    window: str,
) -> list[dict[str, Any]]:
    return [
        {
            "window_id": window,
            "kind": kind,
            "scope_id": row["scope_id"],
            "season_id": row["season_id"],
            "cutoff": models[kind]["training_cutoff"],
            "target_date": row["date"],
            "area_mu": row["area_mu"],
            "actual_kg": row["actual_kg"],
            "prediction_kg": str(values[kind][i]),
            "model_version": models[kind]["model_version"],
            "observation_status": row["observation_status"],
        }
        for kind in KINDS
        for i, row in enumerate(rows)
    ]


def rolling(root: Path, r1: Path, config: dict[str, Any], code_sha: str) -> dict[str, Any]:
    if root.resolve() == r1.resolve() or root.exists():
        raise ValueError("new R2 output directory required")
    if config["spline"] != {
        "number_of_knots": 6,
        "degree": 3,
        "alpha": 10.0,
        "include_bias": False,
        "knots": "uniform",
        "extrapolation": "linear",
        "scaling": "STANDARD_SCALER_TRAIN_FOLD_ONLY",
        "solver": "svd",
        "random_state": 0,
    }:
        raise ValueError("R2 config/implementation mismatch")
    root.mkdir(parents=True, mode=0o700)
    root.chmod(0o700)
    write_json(root / "model_config_r2.json", config)
    write_json(root / "r1_artifact_snapshot.json", snapshot(r1))
    write_json(root / "rolling_started.json", {"code_sha": code_sha, "config_hash": digest(config)})
    # No final CSV parser call in rolling development selection.
    rows = source_rows(r1, "train", config) + source_rows(r1, "development", config)
    results, records = [], []
    fitted: dict[str, dict[str, Any]] = {}
    for window in split_windows(config):
        origin = window["cutoff"].isoformat()
        train = [r for r in rows if r["date"] <= origin]
        targets = [
            r for r in rows if window["start"].isoformat() <= r["date"] <= window["end"].isoformat()
        ]
        if len(targets) != window["days"] or any(not r["actual_kg"] for r in targets):
            raise ValueError("complete comparable window unavailable")
        if origin not in fitted:
            fitted[origin] = {
                kind: fit_kind(train, kind, window["cutoff"], config["scope_id"]) for kind in KINDS
            }
            write_json(root / f"rolling_models_{origin}.json", fitted[origin])
        models = fitted[origin]
        dates = [date.fromisoformat(r["date"]) for r in targets]
        predictions = {
            kind: predict_kind(model, dates, Decimal(config["area_mu"]), config["scope_id"])
            for kind, model in models.items()
        }
        write_json(
            root / f"predictions_{window['id']}.json",
            {kind: [str(v) for v in values] for kind, values in predictions.items()},
        )
        result = {
            "window_id": window["id"],
            "cutoff": origin,
            "rows": len(targets),
            "training_rows": len(train),
            "start": dates[0].isoformat(),
            "end": dates[-1].isoformat(),
            "metrics": {kind: compare(targets, values) for kind, values in predictions.items()},
        }
        results.append(result)
        records.extend(project_table(targets, predictions, models, window["id"]))
    write_json(root / "rolling_backtest_metrics.json", results)
    write_csv(root / "rolling_backtest_predictions.csv", records)
    selection = select_kind(results, config)
    selection.update(
        {
            "config_hash": digest(config),
            "rolling_window_count": len(results),
            "fit_count": len(fitted) * 3,
            "model_window_evaluations": len(results) * 3,
        }
    )
    write_json(root / "selection_freeze_r2.json", selection)
    return selection


def load_config(root: Path) -> dict[str, Any]:
    config: dict[str, Any] = read_json(root / "model_config_r2.json")
    if digest(config) != read_json(root / "selection_freeze_r2.json")["config_hash"]:
        raise ValueError("frozen config drift")
    return config


def benchmark(root: Path, r1: Path) -> dict[str, Any]:
    config = load_config(root)
    write_json(root / "benchmark_started.json", {"blind": False, "once_only": True})
    rows = source_rows(r1, "train", config) + source_rows(r1, "development", config)
    cutoff = date.fromisoformat(config["development_label_end"])
    models = {kind: fit_kind(rows, kind, cutoff, config["scope_id"]) for kind in KINDS}
    dates = calendar(
        date.fromisoformat(config["benchmark_start"]), date.fromisoformat(config["benchmark_end"])
    )
    predictions = {
        kind: predict_kind(model, dates, Decimal(config["area_mu"]), config["scope_id"])
        for kind, model in models.items()
    }
    write_json(root / "benchmark_models.json", models)
    write_json(
        root / "benchmark_predictions_before_labels.json",
        {kind: [str(v) for v in values] for kind, values in predictions.items()},
    )
    labels = source_rows(r1, "final", config)
    if [r["date"] for r in labels] != [d.isoformat() for d in dates]:
        raise ValueError("benchmark identity mismatch")
    metrics = {kind: compare(labels, values) for kind, values in predictions.items()}
    # Reference values come from immutable R1 evidence, never hand-entered replacements.
    original = read_json(r1 / "metrics.json")["final"]
    for kind in ("baseline", "ridge"):
        if metrics[kind] != original[kind]:
            raise ValueError("R1 benchmark replay differs")
    selection = read_json(root / "selection_freeze_r2.json")
    selected = selection["selected"]
    old, new = metrics["ridge"], metrics[selected]
    peak = (
        new["single_day_peak_date_error_days"] < old["single_day_peak_date_error_days"]
        and new["rolling_7day_window_shift_days"] < old["rolling_7day_window_shift_days"]
    )
    quantities = all(
        Decimal(str(new[k])) <= Decimal(str(old[k]))
        for k in config["development_non_regression_metrics"]
    )
    result = {
        "selected_before_benchmark": selected,
        "benchmark_status": config["benchmark_status"],
        "metrics": metrics,
        "peak_timing_improved": peak,
        "quantity_errors_not_worse": quantities,
        "single_season_backtest_improved": selected == "spline" and peak and quantities,
        "result": "SINGLE_SEASON_BACKTEST_IMPROVED"
        if selected == "spline" and peak and quantities
        else "BASELINE_REMAINS_BEST"
        if selected != "spline"
        else "NO_MATERIAL_IMPROVEMENT",
        "wape_improvement_pct": fixed(
            (Decimal(old["daily_wape"]) - Decimal(new["daily_wape"]))
            / Decimal(old["daily_wape"])
            * 100
        ),
        "peak_date_improvement_days": old["single_day_peak_date_error_days"]
        - new["single_day_peak_date_error_days"],
        "seven_day_improvement_days": old["rolling_7day_window_shift_days"]
        - new["rolling_7day_window_shift_days"],
        "R1_artifact_changed": snapshot(r1) != read_json(root / "r1_artifact_snapshot.json"),
    }
    if result["R1_artifact_changed"]:
        raise ValueError("R1 artifact drift")
    write_json(root / "model_comparison_r2.json", result)
    write_csv(
        root / "benchmark_predictions.csv",
        project_table(labels, predictions, models, "R1_KNOWN_BENCHMARK"),
    )
    return result


def fitted_values(model: dict[str, Any], dates: list[date], area: Decimal) -> list[Decimal]:
    """Diagnostic training reconstruction ONLY; not a public forecasting or backtest API."""
    if model["kind"] == "spline":
        return spline_r2.project(model, dates, area)
    values = []
    for day in dates:
        v = model.get("mean_kg_per_mu_day", 0.0)
        if model["kind"] == "ridge":
            v = model["intercept"] + sum(
                (x - m) / s * c
                for x, m, s, c in zip(
                    r1_model.features(day),
                    model["scaler_mean"],
                    model["scaler_scale"],
                    model["coefficients"],
                    strict=True,
                )
            )
        values.append(Decimal(fixed(Decimal(str(max(0.0, v))) * area)))
    return values


def refit(root: Path, r1: Path) -> dict[str, Any]:
    config = load_config(root)
    selection = read_json(root / "selection_freeze_r2.json")
    read_json(root / "model_comparison_r2.json")  # Must have finished the once-only comparison.
    write_json(
        root / "full_refit_started.json", {"kind": selection["selected"], "evaluation": False}
    )
    rows = source_rows(r1, "dataset", config)
    if len(rows) != 207:
        raise ValueError("full history count mismatch")
    model = fit_kind(
        rows, selection["selected"], date.fromisoformat(config["benchmark_end"]), config["scope_id"]
    )
    dates = [date.fromisoformat(r["date"]) for r in rows]
    fitted = fitted_values(model, dates, Decimal(config["area_mu"]))
    write_csv(
        root / "full_history_fit_predictions.csv",
        [
            {
                "date": row["date"],
                "actual_kg": row["actual_kg"],
                "fitted_kg": str(v),
                "status": "IN_SAMPLE_RECONSTRUCTION_NOT_INDEPENDENT_EVALUATION",
            }
            for row, v in zip(rows, fitted, strict=True)
        ],
    )
    wrapper = {
        "schema": "single-season-selected-r2",
        "predictor": model,
        "config_hash": digest(config),
        "support_min": min(map(spline_r2.position, dates)),
        "support_max": max(map(spline_r2.position, dates)),
        "area_scaling_validated": False,
    }
    wrapper["model_version"] = digest(wrapper)
    write_json(root / "selected_model_r2.json", wrapper)
    manifest = {
        "row_count": len(rows),
        "dataset_sha256": file_hash(r1 / "dataset.csv"),
        "selected_model_sha256": file_hash(root / "selected_model_r2.json"),
        "training_cutoff": config["benchmark_end"],
        "scope_count": 1,
        "season_count": 1,
        "full_history_refit_count": 1,
        "total_model_fits": 13,
        "model_window_evaluations": 30,
        "refit_evaluation_claim": False,
    }
    write_json(root / "training_manifest_r2.json", manifest)
    return manifest


def load_selected(root: Path) -> dict[str, Any]:
    wrapper: dict[str, Any] = read_json(root / "selected_model_r2.json")
    if (
        digest({k: v for k, v in wrapper.items() if k != "model_version"})
        != wrapper["model_version"]
    ):
        raise ValueError("selected model integrity mismatch")
    if (
        file_hash(root / "selected_model_r2.json")
        != read_json(root / "training_manifest_r2.json")["selected_model_sha256"]
    ):
        raise ValueError("selected model file changed")
    return wrapper


def forecast(root: Path) -> dict[str, Any]:
    config = load_config(root)
    wrapper = load_selected(root)
    year = config["forecast_season_start_year"]
    start = date.fromisoformat(f"{year}-{config['main_output_start_month_day']}")
    end = date.fromisoformat(f"{year + 1}-{config['main_output_end_month_day']}")
    dates = calendar(start, end)
    areas = [Decimal(a) for a in config["example_areas_mu"]]
    values = {
        str(area): predict_kind(wrapper["predictor"], dates, area, config["scope_id"])
        for area in areas
    }
    for a, b, c in zip(*(values[str(v)] for v in areas), strict=True):
        if abs(b - a * 2) > Decimal("0.0000015") or abs(c - b * Decimal("1.5")) > Decimal(
            "0.00000125"
        ):
            raise ValueError("linear area scaling implementation failed")
    records = [
        {
            "date": d.isoformat(),
            "area_mu": str(area),
            "harvest_kg": str(v),
            "arrival_kg": str(v),
            "position_status": "SUPPORTED"
            if wrapper["support_min"] <= spline_r2.position(d) <= wrapper["support_max"]
            else "EXTRAPOLATED",
        }
        for area in areas
        for d, v in zip(dates, values[str(area)], strict=True)
    ]
    write_csv(root / "forecast_example_r2.csv", records)
    result = {
        **summaries(dates, values[config["area_mu"]]),
        "area_mu": config["area_mu"],
        "daily_rows_per_area": len(dates),
        "forecast_start": start.isoformat(),
        "forecast_end": end.isoformat(),
        "area_scaling_software_test": "PASS",
        "area_scaling_validated": False,
        "fresh_process_pid": os.getpid(),
        "fit_called": False,
        "extrapolated_rows": sum(r["position_status"] == "EXTRAPOLATED" for r in records),
        "outside_main_window": "NOT_PREDICTED_NOT_ZERO",
        "model_kind": wrapper["predictor"]["kind"],
        "model_version": wrapper["model_version"],
    }
    write_json(root / "forecast_example_summary_r2.json", result)
    return result
