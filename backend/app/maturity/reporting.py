from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from backend.app.maturity.schemas import (
    MaturityForecastExecutionResult,
    MaturityModelExecutionResult,
)
from backend.app.planning.json_types import canonical_json_value


def _run_label(run_id: int | None, source_signature: str) -> str:
    if run_id is not None:
        return str(run_id)
    return source_signature[:12] or "preview"


def _json_payload(
    result: MaturityModelExecutionResult | MaturityForecastExecutionResult,
) -> dict[str, Any]:
    return cast(dict[str, Any], canonical_json_value(asdict(result)))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _model_markdown(result: MaturityModelExecutionResult) -> str:
    lines = [
        "# Maturity Model Report",
        "",
        f"- run_id: {result.run_id if result.run_id is not None else '(dry-run)'}",
        f"- status: {result.status}",
        f"- model_version: {result.model_version}",
        f"- model_family: {result.model_family}",
        f"- source_signature: {result.source_signature}",
        f"- sample_count: {result.sample_count}",
        f"- distinct_season_count: {result.distinct_season_count}",
        f"- distinct_farm_count: {result.distinct_farm_count}",
        f"- distinct_subfarm_count: {result.distinct_subfarm_count}",
        "",
        "## Warnings",
        "",
    ]
    if result.warnings:
        lines.extend(f"- {item}" for item in result.warnings)
    else:
        lines.append("- (none)")
    lines.extend(["", "## Blockers", ""])
    if result.blockers:
        lines.extend(f"- {item}" for item in result.blockers)
    else:
        lines.append("- (none)")
    return "\n".join(lines).rstrip() + "\n"


def _forecast_markdown(result: MaturityForecastExecutionResult) -> str:
    lines = [
        "# Natural Maturity Forecast Report",
        "",
        f"- run_id: {result.run_id if result.run_id is not None else '(dry-run)'}",
        f"- status: {result.status}",
        f"- model_run_id: {result.model_run_id}",
        f"- model_version: {result.model_version}",
        f"- source_signature: {result.source_signature}",
        f"- axis_mode: {result.axis_mode}",
        f"- expected_marketable_total_kg: {result.expected_marketable_total_kg}",
        f"- expected_total_source: {result.expected_total_source}",
        f"- daily_row_count: {len(result.daily_predictions)}",
        "",
        "## Warnings",
        "",
    ]
    if result.warnings:
        lines.extend(f"- {item}" for item in result.warnings)
    else:
        lines.append("- (none)")
    lines.extend(["", "## Blockers", ""])
    if result.blockers:
        lines.extend(f"- {item}" for item in result.blockers)
    else:
        lines.append("- (none)")
    return "\n".join(lines).rstrip() + "\n"


def write_model_reports(
    result: MaturityModelExecutionResult,
    *,
    output_dir: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_label = _run_label(result.run_id, result.source_signature)
    json_path = output_dir / f"{run_label}.json"
    markdown_path = output_dir / f"{run_label}.md"
    _write_json(json_path, _json_payload(result))
    markdown_path.write_text(_model_markdown(result), encoding="utf-8")
    return json_path, markdown_path


def write_forecast_reports(
    result: MaturityForecastExecutionResult,
    *,
    output_dir: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_label = _run_label(result.run_id, result.source_signature)
    json_path = output_dir / f"{run_label}.json"
    markdown_path = output_dir / f"{run_label}.md"
    _write_json(json_path, _json_payload(result))
    markdown_path.write_text(_forecast_markdown(result), encoding="utf-8")
    return json_path, markdown_path
