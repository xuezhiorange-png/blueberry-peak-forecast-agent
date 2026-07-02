from __future__ import annotations

import json
from dataclasses import asdict
from decimal import Decimal
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


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _manifest_rows(result: MaturityModelExecutionResult) -> list[dict[str, Any]]:
    rows = result.input_snapshot.get("manifest_rows", [])
    return rows if isinstance(rows, list) else []


def _holiday_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    included = [
        row
        for row in rows
        if row.get("status") == "included" and isinstance(row.get("holiday_summary"), dict)
    ]
    reason_breakdown: dict[str, int] = {}
    for row in included:
        breakdown = row["holiday_summary"].get("reason_code_breakdown", {})
        if isinstance(breakdown, dict):
            for key, value in breakdown.items():
                reason_breakdown[str(key)] = reason_breakdown.get(str(key), 0) + int(value)
    return {
        "raw_day_count": sum(
            int(row["holiday_summary"].get("raw_day_count", 0)) for row in included
        ),
        "used_day_count": sum(
            int(row["holiday_summary"].get("used_day_count", 0)) for row in included
        ),
        "downweighted_day_count": sum(
            int(row["holiday_summary"].get("downweighted_day_count", 0)) for row in included
        ),
        "excluded_day_count": sum(
            int(row["holiday_summary"].get("excluded_day_count", 0)) for row in included
        ),
        "raw_proxy_weight": sum(
            (Decimal(str(row["holiday_summary"].get("raw_proxy_weight", "0"))) for row in included),
            Decimal("0"),
        ),
        "effective_training_weight": sum(
            (
                Decimal(str(row["holiday_summary"].get("effective_training_weight", "0")))
                for row in included
            ),
            Decimal("0"),
        ),
        "reason_code_breakdown": reason_breakdown,
    }


def _manifest_audit(result: MaturityModelExecutionResult) -> dict[str, Any]:
    rows = _manifest_rows(result)
    included = [row for row in rows if row.get("status") == "included"]
    excluded = [row for row in rows if row.get("status") != "included"]
    return {
        "input_row_count": len(rows),
        "included_row_count": len(included),
        "excluded_row_count": len(excluded),
        "include_false_rows": [row for row in rows if row.get("include") is False],
        "excluded_rows": excluded,
        "holiday_audit": _holiday_summary(rows),
        "season_breakdown": {
            season_code: {
                "row_count": sum(1 for row in rows if row.get("season_code") == season_code),
                "included_row_count": sum(
                    1 for row in included if row.get("season_code") == season_code
                ),
            }
            for season_code in sorted(
                {str(row.get("season_code")) for row in rows if row.get("season_code") is not None}
            )
        },
    }


def _hierarchy_payload(result: MaturityModelExecutionResult) -> dict[str, Any]:
    group_models = cast(dict[str, dict[str, Any]], result.artifact.get("group_models", {}))
    group_audit = cast(dict[str, dict[str, Any]], result.artifact.get("group_audit", {}))
    levels: dict[str, list[dict[str, Any]]] = {
        "climate_zone_variety": [],
        "province_variety": [],
        "variety_global": [],
    }
    rows = group_audit or group_models
    for key, row in sorted(rows.items()):
        level = str(row.get("level"))
        entry = {
            "group_key": key,
            "level": level,
            "parent_group_key": row.get("parent_group_key"),
            "sample_count": row.get("sample_count"),
            "distinct_season_count": row.get("distinct_season_count"),
            "distinct_farm_count": row.get("distinct_farm_count"),
            "distinct_subfarm_count": row.get("distinct_subfarm_count"),
            "shrinkage": row.get("shrinkage"),
            "peak_day": row.get("peak_day"),
            "fallback_reason": row.get("fallback_reason"),
            "available": row.get("available", True),
            "support_range": {
                "min_day": result.artifact.get("support_days", [None])[0],
                "max_day": result.artifact.get("support_days", [None])[-1],
            },
            "warnings": row.get("warnings", []),
        }
        if level in levels:
            levels[level].append(entry)
    return levels


def _calibration_payload(result: MaturityModelExecutionResult) -> dict[str, Any]:
    payload = dict(result.calibration_metrics)
    payload["interval_semantics"] = payload.get("interval_semantics", "pointwise_marginal")
    payload["p50_mass_conserving"] = True
    payload["p80_p90_sum_mass_conserving"] = False
    return payload


def _reproducibility_payload(result: MaturityModelExecutionResult) -> dict[str, Any]:
    return {
        "run_id": result.run_id,
        "source_signature": result.source_signature,
        "config_hash": result.config_hash,
        "model_version": result.model_version,
        "artifact_hash": result.input_snapshot.get("artifact_hash"),
        "training_cutoff": result.input_snapshot.get("training_cutoff"),
        "config_snapshot": result.input_snapshot.get("config_snapshot", {}),
        "random_seed": result.input_snapshot.get("random_seed"),
        "code_version": result.input_snapshot.get("code_version"),
        "leakage_checks": result.input_snapshot.get("leakage_checks", {}),
        "manifest_rows": result.input_snapshot.get("manifest_rows", []),
        "base_temperature_context": result.input_snapshot.get("base_temperature_context", {}),
    }


def _leakage_checks_payload(result: MaturityModelExecutionResult) -> dict[str, Any]:
    return cast(dict[str, Any], result.input_snapshot.get("leakage_checks", {}))


def _model_json_payload(result: MaturityModelExecutionResult) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        canonical_json_value(
            {
                "run_id": result.run_id,
                "status": result.status,
                "model_version": result.model_version,
                "model_family": result.model_family,
                "source_signature": result.source_signature,
                "config_hash": result.config_hash,
                "training_cutoff": result.input_snapshot.get("training_cutoff"),
                "code_version": result.input_snapshot.get("code_version"),
                "random_seed": result.input_snapshot.get("random_seed"),
                "artifact_hash": result.input_snapshot.get("artifact_hash"),
                "label_proxy": {
                    "name": "smoothed_arrival_proxy_for_natural_maturity",
                    "description": (
                        "Smoothed arrival proxy derived from fact_receipt_daily "
                        "rather than direct physiological maturity observations."
                    ),
                },
                "manifest_audit": _manifest_audit(result),
                "hierarchy": _hierarchy_payload(result),
                "training_metrics": result.training_metrics,
                "calibration": _calibration_payload(result),
                "shift_model": result.artifact.get("shift_model", {}),
                "spline_partial_pooling": {
                    "support_days": result.artifact.get("support_days", []),
                    "reference_phase_rates": result.artifact.get("reference_phase_rates", {}),
                    "phase_adjustment_bounds_days": result.artifact.get(
                        "phase_adjustment_bounds_days",
                        [],
                    ),
                },
                "artifact": result.artifact,
                "reproducibility": _reproducibility_payload(result),
                "leakage_checks": _leakage_checks_payload(result),
                "warnings": list(result.warnings),
                "blockers": list(result.blockers),
                "raw_result": asdict(result),
            }
        ),
    )


def _forecast_json_payload(result: MaturityForecastExecutionResult) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        canonical_json_value(
            {
                "run_id": result.run_id,
                "status": result.status,
                "model_run_id": result.model_run_id,
                "source_signature": result.source_signature,
                "config_hash": result.config_hash,
                "model_version": result.model_version,
                "axis_mode": result.axis_mode,
                "expected_marketable_total_kg": result.expected_marketable_total_kg,
                "expected_total_source": result.expected_total_source,
                "warnings": list(result.warnings),
                "blockers": list(result.blockers),
                "input_snapshot": result.input_snapshot,
                "daily_predictions": [asdict(item) for item in result.daily_predictions],
            }
        ),
    )


def _model_markdown(result: MaturityModelExecutionResult) -> str:
    manifest_audit = _manifest_audit(result)
    hierarchy = _hierarchy_payload(result)
    calibration = _calibration_payload(result)
    reproducibility = _reproducibility_payload(result)
    leakage_checks = _leakage_checks_payload(result)
    holiday_audit = cast(dict[str, Any], manifest_audit["holiday_audit"])
    shift_model = cast(dict[str, Any], result.artifact.get("shift_model", {}))
    lines = [
        "# Maturity Model Report",
        "",
        f"- run_id: {result.run_id if result.run_id is not None else '(dry-run)'}",
        f"- status: {result.status}",
        f"- model_version: {result.model_version}",
        f"- model_family: {result.model_family}",
        f"- source_signature: {result.source_signature}",
        f"- config_hash: {result.config_hash}",
        f"- training_cutoff: {reproducibility['training_cutoff']}",
        f"- code_version: {reproducibility['code_version']}",
        f"- random_seed: {reproducibility['random_seed']}",
        f"- artifact_hash: {reproducibility['artifact_hash']}",
        "",
        "## Proxy Label",
        "",
        "- label: smoothed_arrival_proxy_for_natural_maturity",
        "- source: smoothed fact_receipt_daily arrival proxy",
        "- note: not a direct physiological maturity observation",
        "",
        "## Manifest Audit",
        "",
        f"- input_row_count: {manifest_audit['input_row_count']}",
        f"- included_row_count: {manifest_audit['included_row_count']}",
        f"- excluded_row_count: {manifest_audit['excluded_row_count']}",
        f"- raw_day_count: {holiday_audit['raw_day_count']}",
        f"- used_day_count: {holiday_audit['used_day_count']}",
        f"- downweighted_day_count: {holiday_audit['downweighted_day_count']}",
        f"- excluded_day_count: {holiday_audit['excluded_day_count']}",
        f"- raw_proxy_weight: {holiday_audit['raw_proxy_weight']}",
        f"- effective_training_weight: {holiday_audit['effective_training_weight']}",
        f"- reason_code_breakdown: {holiday_audit['reason_code_breakdown']}",
        "",
        "### Include False Rows",
        "",
    ]
    include_false_rows = cast(list[dict[str, Any]], manifest_audit["include_false_rows"])
    if include_false_rows:
        for row in include_false_rows:
            exclusion_reason = row.get("resolved_exclusion_reason") or row.get("exclusion_reason")
            lines.append(
                f"- season={row.get('season_code')}, "
                f"include={row.get('include')}, "
                f"exclusion_reason={exclusion_reason}"
            )
    else:
        lines.append("- (none)")
    lines.extend(
        [
            "",
            "### Season Breakdown",
            "",
        ]
    )
    for season_code, row in cast(dict[str, Any], manifest_audit["season_breakdown"]).items():
        lines.append(
            f"- {season_code}: "
            f"row_count={row['row_count']}, "
            f"included_row_count={row['included_row_count']}"
        )
    lines.extend(
        [
            "",
            "## Hierarchy",
            "",
        ]
    )
    for level in ("climate_zone_variety", "province_variety", "variety_global"):
        lines.append(f"### {level}")
        lines.append("")
        entries = cast(list[dict[str, Any]], hierarchy[level])
        if not entries:
            lines.append("- (none)")
            lines.append("")
            continue
        for entry in entries:
            summary = (
                f"group_key={entry['group_key']}, "
                f"parent_group={entry['parent_group_key']}, "
                f"sample_count={entry['sample_count']}, "
                f"season_count={entry['distinct_season_count']}, "
                f"farm_count={entry['distinct_farm_count']}, "
                f"subfarm_count={entry['distinct_subfarm_count']}, "
                f"shrinkage={entry['shrinkage']}, "
                f"fallback_reason={entry['fallback_reason']}, "
                f"peak_day={entry['peak_day']}, "
                f"support_range={entry['support_range']}, "
                f"warnings={entry['warnings']}, "
                f"available={entry['available']}"
            )
            lines.append(f"- {summary}")
        lines.append("")
    lines.extend(
        [
            "## Spline / Partial Pooling",
            "",
            f"- support_days: {result.artifact.get('support_days', [])}",
            f"- reference_phase_rates: {result.artifact.get('reference_phase_rates', {})}",
            "- phase_adjustment_bounds_days: "
            f"{result.artifact.get('phase_adjustment_bounds_days', [])}",
            f"- curve_config: {reproducibility['config_snapshot'].get('curve', {})}",
            f"- pooling_config: {reproducibility['config_snapshot'].get('pooling', {})}",
            "",
            "## Shift Model",
            "",
            f"- enabled: {shift_model.get('enabled')}",
            f"- intercept: {shift_model.get('intercept_days')}",
            f"- feature_order: {shift_model.get('feature_order', [])}",
            f"- coefficients: {shift_model.get('coefficients', {})}",
            f"- scaler_center: {shift_model.get('scaler_center', {})}",
            f"- scaler_scale: {shift_model.get('scaler_scale', {})}",
            f"- feature_units: {shift_model.get('feature_units', {})}",
            f"- reference_category: {shift_model.get('reference_categories', {})}",
            f"- category_vocabulary: {shift_model.get('category_vocabulary', {})}",
            f"- missing_value_rules: {shift_model.get('missing_value_rules', {})}",
            f"- bounds: {shift_model.get('bounds', [])}",
            "",
            "## Calibration",
            "",
            f"- calibration_status: {calibration.get('calibration_status')}",
            f"- fold_count: {calibration.get('fold_count')}",
            f"- held_out_seasons: {calibration.get('held_out_seasons')}",
            f"- residual_count: {calibration.get('residual_count')}",
            f"- interval_semantics: {calibration.get('interval_semantics')}",
            f"- pointwise_p80_coverage: {calibration.get('pointwise_p80_coverage')}",
            f"- pointwise_p90_coverage: {calibration.get('pointwise_p90_coverage')}",
            f"- curve_wmape: {calibration.get('curve_wmape')}",
            f"- peak_date_mae_days: {calibration.get('peak_date_mae_days')}",
            f"- cumulative_share_error: {calibration.get('cumulative_share_error')}",
            "- p50_mass_conserving: True",
            "- p80_p90_sum_mass_conserving: False",
            "",
            "## Leakage Checks",
            "",
        ]
    )
    for key, value in leakage_checks.items():
        if isinstance(value, dict):
            lines.append(
                f"- {key}: status={value.get('status')}, "
                f"checked={value.get('checked_row_count')}, "
                f"passed={value.get('passed_row_count')}, "
                f"excluded={value.get('excluded_row_count')}, "
                f"failed={value.get('failed_row_count')}, "
                f"reasons={value.get('reason_code_breakdown')}"
            )
        else:
            lines.append(f"- {key}: {value}")
    lines.extend(
        [
            "",
            "## Reproducibility",
            "",
        ]
    )
    for row in cast(list[dict[str, Any]], reproducibility["manifest_rows"]):
        if row.get("status") != "included":
            continue
        analytics = cast(dict[str, Any], row.get("analytics_provenance", {}))
        base_temperature_run = cast(dict[str, Any], row.get("base_temperature_run", {}))
        lines.append(
            f"- season={row.get('season_code')}, "
            f"source_max_raw_id={analytics.get('source_max_raw_id')}, "
            f"plan_row_hash={row.get('plan_row_hash')}, "
            f"base_temperature_run_id={base_temperature_run.get('run_id')}"
        )
    lines.extend(["", "## Warnings", ""])
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
    _write_json(json_path, _model_json_payload(result))
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
    _write_json(json_path, _forecast_json_payload(result))
    markdown_path.write_text(_forecast_markdown(result), encoding="utf-8")
    return json_path, markdown_path
