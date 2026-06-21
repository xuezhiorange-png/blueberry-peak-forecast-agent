from __future__ import annotations

import csv
import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import cast

from backend.app.baseline.schemas import BaselineBacktestExecutionResult
from backend.app.etl.history.quality import decimal_json


def _run_label(result: BaselineBacktestExecutionResult) -> str:
    if result.run_id is None:
        return "unknown"
    return str(result.run_id)


def _json_payload(result: BaselineBacktestExecutionResult) -> dict[str, object]:
    return cast(dict[str, object], decimal_json(asdict(result)))


def _markdown_report(result: BaselineBacktestExecutionResult) -> str:
    lines = [
        "# Baseline Backtest Report",
        "",
        f"- run_id: {_run_label(result)}",
        f"- status: {result.status}",
        f"- model_version: {result.model_version}",
        f"- benchmark_mode: {result.benchmark_mode}",
        f"- production_eligible: {str(result.production_eligible).lower()}",
        f"- evaluation_scheme: {result.evaluation_scheme}",
        f"- source_signature: {result.source_signature}",
        f"- result_row_count: {result.result_row_count}",
    ]
    if result.error_message:
        lines.append(f"- error_message: {result.error_message}")
    lines.extend(["", "## Model Summaries", ""])
    for summary in result.model_summaries:
        lines.extend(
            [
                f"### {summary['baseline_name']}",
                f"- evaluated_row_count: {summary['evaluated_row_count']}",
                f"- excluded_row_count: {summary['excluded_row_count']}",
                f"- mape: {summary['mape']}",
                f"- mdape: {summary['mdape']}",
                f"- wmape: {summary['wmape']}",
                f"- mae_kg: {summary['mae_kg']}",
                f"- mean_bias_kg: {summary['mean_bias_kg']}",
                "",
            ]
        )
    lines.extend(["## Limitations", ""])
    for limitation in result.limitations:
        lines.append(f"- {limitation}")
    lines.extend(["", "## Leakage Audit", ""])
    for check in result.leakage_audit:
        lines.append(f"- {check.name}: {'pass' if check.passed else 'fail'} ({check.evidence})")
    return "\n".join(lines).rstrip() + "\n"


def _write_factory_error_csv(
    result: BaselineBacktestExecutionResult,
    path: Path,
) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "model",
                "target_season",
                "factory",
                "previous_season",
                "status",
                "actual_peak_kg",
                "predicted_peak_kg",
                "actual_peak_tonne",
                "predicted_peak_tonne",
                "absolute_error_kg",
                "APE",
                "training_seasons",
                "exclusion_reason",
                "build_run_id",
                "model_version",
            ],
        )
        writer.writeheader()
        for row in result.results:
            writer.writerow(
                {
                    "model": row.baseline_name,
                    "target_season": row.target_season_code,
                    "factory": row.factory_name,
                    "previous_season": row.previous_season_code or "",
                    "status": row.status,
                    "actual_peak_kg": row.actual_stable_peak_kg,
                    "predicted_peak_kg": row.predicted_stable_peak_kg,
                    "actual_peak_tonne": (
                        None
                        if row.actual_stable_peak_kg is None
                        else row.actual_stable_peak_kg / 1000
                    ),
                    "predicted_peak_tonne": (
                        None
                        if row.predicted_stable_peak_kg is None
                        else row.predicted_stable_peak_kg / 1000
                    ),
                    "absolute_error_kg": row.absolute_error_kg,
                    "APE": row.ape,
                    "training_seasons": ",".join(row.training_season_codes),
                    "exclusion_reason": row.exclusion_reason or "",
                    "build_run_id": _run_label(result),
                    "model_version": result.model_version,
                }
            )


def write_execution_reports(
    result: BaselineBacktestExecutionResult,
    *,
    output_dir: Path,
) -> BaselineBacktestExecutionResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_label = _run_label(result)
    json_path = output_dir / f"baseline_backtest_{run_label}.json"
    markdown_path = output_dir / f"baseline_backtest_{run_label}.md"
    csv_path = output_dir / f"baseline_factory_errors_{run_label}.csv"
    json_path.write_text(
        json.dumps(_json_payload(result), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    markdown_path.write_text(_markdown_report(result), encoding="utf-8")
    _write_factory_error_csv(result, csv_path)
    return replace(
        result,
        report_paths=(str(json_path), str(markdown_path), str(csv_path)),
        report_generation_failed=False,
    )
