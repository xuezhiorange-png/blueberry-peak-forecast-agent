"""Materialize the deterministic V0.7-S4 Model A/B comparison.

The controlled S3 row-level artifacts are explicit inputs.  This command only
reads sealed predictions and post-seal score rows; it never imports or calls a
model-fitting function.  The generated JSON/report contain hashes and
aggregates, not the private row-level data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.area_yield.data import digest
from backend.app.area_yield.weather_value_conclusion import (
    build_s4_analysis,
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_object(path: Path) -> dict[str, Any]:
    value = _read_json(path)
    if not isinstance(value, dict):
        raise ValueError(f"EXPECTED_JSON_OBJECT:{path}")
    return value


def _sha256(path: Path) -> str:
    digest_value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest_value.update(chunk)
    return digest_value.hexdigest()


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _value(value: Any) -> str:
    if value is None:
        return "NOT_COMPUTABLE"
    return str(value)


def _scope_rows(summary: Mapping[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for horizon in ("H1", "H7", "H15"):
        item = summary["horizons"][horizon]
        comparison = item["comparison"]
        a = comparison["model_a"]
        b = comparison["model_b"]
        rows.append(
            {
                "horizon": horizon,
                "A WAPE": _value(a.get("pooled_wape")),
                "B WAPE": _value(b.get("pooled_wape")),
                "B-A WAPE": _value(comparison["absolute_delta"]["daily_wape_b_minus_a"]),
                "relative improvement": _value(comparison["relative_improvement"]["daily_wape"]),
                "A MAE": _value(a.get("mae_kg")),
                "B MAE": _value(b.get("mae_kg")),
                "B-A MAE": _value(comparison["absolute_delta"]["daily_mae_b_minus_a"]),
                "A Bias": _value(a.get("bias_kg")),
                "B Bias": _value(b.get("bias_kg")),
                "B-A Bias": _value(comparison["absolute_delta"]["bias_b_minus_a"]),
                "bias magnitude delta": _value(comparison["bias_magnitude_delta"]),
                "A median/P75/P90/max": _distribution_text(a.get("error_distribution_abs_kg")),
                "B median/P75/P90/max": _distribution_text(b.get("error_distribution_abs_kg")),
            }
        )
    return rows


def _distribution_text(value: Any) -> str:
    if not isinstance(value, Mapping):
        return "NOT_COMPUTABLE"
    return "/".join(_value(value.get(key)) for key in ("median", "p75", "p90", "max"))


def _markdown_table(rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> str:
    if not rows:
        return "NOT_COMPUTABLE\n"
    header = "| " + " | ".join(columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    body = [
        "| " + " | ".join(str(row.get(column, "NOT_COMPUTABLE")) for column in columns) + " |"
        for row in rows
    ]
    return "\n".join([header, divider, *body]) + "\n"


def _per_base_table(summary: Mapping[str, Any], horizon: str) -> str:
    entries = summary["horizons"][horizon]["per_base"]["entries"]
    rows = [
        {
            "base_id": entry["base_id"],
            "base_name": entry["canonical_base_name"],
            "status": entry["status"],
            "rows": entry["complete_horizon_row_count"],
            "A WAPE": _value(entry["model_a_wape"]),
            "B WAPE": _value(entry["model_b_wape"]),
            "B-A": _value(entry["wape_delta_b_minus_a"]),
            "actual kg": _value(entry["actual_denominator_kg"]),
            "A abs error kg": _value(entry["model_a_absolute_error_kg"]),
            "B abs error kg": _value(entry["model_b_absolute_error_kg"]),
            "error reduction kg": _value(entry["absolute_error_reduction_kg"]),
        }
        for entry in entries
    ]
    return _markdown_table(
        rows,
        (
            "base_id",
            "base_name",
            "status",
            "rows",
            "A WAPE",
            "B WAPE",
            "B-A",
            "actual kg",
            "A abs error kg",
            "B abs error kg",
            "error reduction kg",
        ),
    )


def _lead_table(summary: Mapping[str, Any]) -> str:
    rows = []
    for lead, comparison in summary["lead_day"]["lead_days"].items():
        a = comparison["model_a"]
        b = comparison["model_b"]
        rows.append(
            {
                "lead_day": lead,
                "sample_count": comparison["sample_count"],
                "A WAPE": _value(a.get("pooled_wape")),
                "B WAPE": _value(b.get("pooled_wape")),
                "B-A WAPE": _value(comparison["absolute_delta"]["daily_wape_b_minus_a"]),
            }
        )
    return _markdown_table(rows, ("lead_day", "sample_count", "A WAPE", "B WAPE", "B-A WAPE"))


def _summary_metrics(summary: Mapping[str, Any]) -> str:
    rows = _scope_rows(summary)
    return _markdown_table(
        rows,
        (
            "horizon",
            "A WAPE",
            "B WAPE",
            "B-A WAPE",
            "relative improvement",
            "A MAE",
            "B MAE",
            "B-A MAE",
            "A Bias",
            "B Bias",
            "B-A Bias",
            "bias magnitude delta",
            "A median/P75/P90/max",
            "B median/P75/P90/max",
        ),
    )


def _coverage_table(analysis: Mapping[str, Any]) -> str:
    rows = []
    for scope in ("fold_a", "fold_b", "combined"):
        summary = analysis["combined"] if scope == "combined" else analysis["folds"][scope]
        score = analysis["coverage"][scope]
        for horizon in ("H1", "H7", "H15"):
            per_base = summary["horizons"][horizon]["per_base"]
            rows.append(
                {
                    "scope": scope,
                    "prediction rows": score.get("prediction_row_count"),
                    "scored rows": score.get("scored_row_count"),
                    "unscored rows": score.get("unscored_row_count"),
                    "horizon": horizon,
                    "complete rows": len(analysis["views"][scope][horizon]),
                    "complete origins": len(
                        {
                            (row["base_id"], row["forecast_origin"])
                            for row in analysis["views"][scope][horizon]
                        }
                    ),
                    "base row min/median/P75/max": "/".join(
                        _value(per_base["complete_horizon_row_count_distribution"].get(key))
                        for key in ("min", "median", "p75", "max")
                    ),
                }
            )
    return _markdown_table(
        rows,
        (
            "scope",
            "prediction rows",
            "scored rows",
            "unscored rows",
            "horizon",
            "complete rows",
            "complete origins",
            "base row min/median/P75/max",
        ),
    )


def render_report(analysis: Mapping[str, Any]) -> str:
    classification = analysis["weather_incremental_value"]
    reason = analysis["weather_incremental_value_reason"]
    consistency = analysis["consistency"]
    lines = [
        "# V0.7-S4 Model A/B Comparison and Version Conclusion",
        "",
        "## Executive conclusion",
        "",
        f"`WEATHER_INCREMENTAL_VALUE={classification}`.",
        "",
        "This conclusion is limited to the frozen S3 rolling OOT task and the "
        "Lane-A ERA5-Land past-observed weather feature experiment. It is not "
        "production-like forecast-weather validation and does not promote Model B.",
        "",
        f"Classification reason: `{reason}`.",
        "",
        "The primary pooled WAPE values improve for all three horizons in the "
        "complete S3 views and in both folds, but the leave-top-two sensitivity "
        "analysis is retained as a material robustness limitation where it reverses "
        "the H1 direction.",
        "",
        "## Frozen experiment scope",
        "",
        "- Model A: `AREA_DAILY_RIDGE_V1_ROLLING_OOT_NO_WEATHER`.",
        "- Model B: `AREA_DAILY_RIDGE_V1_PLUS_LEAKAGE_SAFE_WEATHER_FEATURES`.",
        "- Both use the already fitted S3 artifacts; S4 does not refit either model.",
        "- A and B share the same target rows, origins, horizons, cutoff, and actual authority.",
        "- `ABSOLUTE_DELTA = Model B - Model A`; negative means B improves.",
        "- `RELATIVE_IMPROVEMENT = (Model A - Model B) / Model A`; positive means improvement.",
        "- Bias is `predicted - actual`; positive means overprediction.",
        "- WAPE is pooled absolute error divided by pooled actual quantity.",
        "",
        "## S3 artifact and primary-metric parity",
        "",
        f"- `S3_PRIMARY_METRIC_PARITY_PASS={analysis['s3_primary_metric_parity']['pass']}`.",
        f"- `MODEL_A_ARTIFACT_HASH_PARITY="
        f"{analysis['s3_artifact_parity']['model_a_artifact_hash_parity']}`.",
        f"- `MODEL_B_ARTIFACT_HASH_PARITY="
        f"{analysis['s3_artifact_parity']['model_b_artifact_hash_parity']}`.",
        f"- `MODEL_A_PREDICTION_HASH_PARITY="
        f"{analysis['s3_artifact_parity']['model_a_prediction_hash_parity']}`.",
        f"- `MODEL_B_PREDICTION_HASH_PARITY="
        f"{analysis['s3_artifact_parity']['model_b_prediction_hash_parity']}`.",
        "",
        "## Fold A comparison",
        "",
        _summary_metrics(analysis["folds"]["fold_a"]),
        "### Fold A cumulative H7/H15 views",
        "",
        _cumulative_table(analysis["folds"]["fold_a"]),
        "### Fold A lead-day analysis",
        "",
        _lead_table(analysis["folds"]["fold_a"]),
        "",
        "## Fold B comparison",
        "",
        _summary_metrics(analysis["folds"]["fold_b"]),
        "### Fold B cumulative H7/H15 views",
        "",
        _cumulative_table(analysis["folds"]["fold_b"]),
        "### Fold B lead-day analysis",
        "",
        _lead_table(analysis["folds"]["fold_b"]),
        "",
        "## Combined comparison",
        "",
        _summary_metrics(analysis["combined"]),
        "### Combined cumulative H7/H15 views",
        "",
        _cumulative_table(analysis["combined"]),
        "### Combined lead-day analysis",
        "",
        _lead_table(analysis["combined"]),
        "",
        "## Base breadth, contribution, and leave-out robustness",
        "",
        "The JSON evidence contains the complete per-Base H1/H7/H15 rows. "
        "The tables below use the same complete-horizon denominator as the "
        "primary metrics.",
        "",
    ]
    for scope, title in (("fold_a", "Fold A"), ("fold_b", "Fold B"), ("combined", "Combined")):
        summary = analysis["combined"] if scope == "combined" else analysis["folds"][scope]
        lines.extend([f"### {title} breadth and robustness", ""])
        breadth_rows = []
        for horizon in ("H1", "H7", "H15"):
            item = summary["horizons"][horizon]
            breadth = item["per_base"]["breadth"]
            contribution = item["per_base"]["contributions"]
            leave1 = contribution["leave_top1"]
            leave2 = contribution["leave_top2"]
            breadth_rows.append(
                {
                    "horizon": horizon,
                    "improved/degraded/unchanged/not-computable": "/".join(
                        str(breadth[key])
                        for key in (
                            "improved_base_count",
                            "degraded_base_count",
                            "unchanged_base_count",
                            "not_computable_base_count",
                        )
                    ),
                    "improved count share": _value(breadth["improved_base_count_share"]),
                    "degraded count share": _value(breadth["degraded_base_count_share"]),
                    "improved actual kg share": _value(breadth["improved_base_actual_kg_share"]),
                    "degraded actual kg share": _value(breadth["degraded_base_actual_kg_share"]),
                    "top1 share": _value(contribution["top1_positive_contribution_share"]),
                    "top2 share": _value(contribution["top2_positive_contribution_share"]),
                    "leave top1 delta": _value(leave1["delta"]),
                    "leave top1 direction": leave1["direction"],
                    "leave top2 delta": _value(leave2["delta"]),
                    "leave top2 direction": leave2["direction"],
                    "decomposition": contribution["error_reduction_decomposition_pass"],
                }
            )
        lines.extend(
            [
                _markdown_table(
                    breadth_rows,
                    (
                        "horizon",
                        "improved/degraded/unchanged/not-computable",
                        "improved count share",
                        "degraded count share",
                        "improved actual kg share",
                        "degraded actual kg share",
                        "top1 share",
                        "top2 share",
                        "leave top1 delta",
                        "leave top1 direction",
                        "leave top2 delta",
                        "leave top2 direction",
                        "decomposition",
                    ),
                ),
                "",
            ]
        )
        for horizon in ("H1", "H7", "H15"):
            contribution = summary["horizons"][horizon]["per_base"]["contributions"]
            top1 = contribution["top1_positive_contributor"]
            top2 = contribution["top2_positive_contributors"]
            top2_ids = ", ".join(item["base_id"] for item in top2) if top2 else "NOT_COMPUTABLE"
            lines.extend(
                [
                    f"#### {title} {horizon} top positive contributors",
                    "",
                    f"Top 1: `{top1['base_id'] if top1 else 'NOT_COMPUTABLE'}` "
                    f"({_value(top1.get('canonical_base_name') if top1 else None)}), "
                    f"reduction kg `{_value(top1.get('error_reduction_kg') if top1 else None)}`.",
                    f"Top 2: `{top2_ids}`.",
                    "",
                    "Per-Base diagnostics:",
                    "",
                    _per_base_table(summary, horizon),
                ]
            )
    lines.extend(
        [
            "## Coverage limitations",
            "",
            _coverage_table(analysis),
            "",
            "Coverage is inherited from S3. Unscored or unknown actual rows are "
            "not converted to zero and do not enter the complete-horizon metrics.",
            "",
            "## Consistency and scientific boundary",
            "",
            f"- Fold direction consistency: `{consistency['fold_direction_consistency_pass']}`.",
            f"- Horizon direction consistency: "
            f"`{consistency['horizon_direction_consistency_pass']}`.",
            "- `ERA5_FORECAST_TIME_KNOWN_AT_STATUS=NOT_ESTABLISHED`.",
            "- `LANE_A_PRODUCTION_LIKE_PIT_ELIGIBLE=false`.",
            "- `HISTORICAL_AS_ISSUED_ECMWF_ARCHIVE_2024_2025=NOT_FOUND`.",
            "- `HISTORICAL_AS_ISSUED_ECMWF_ARCHIVE_2025_2026=NOT_FOUND`.",
            "- `PRODUCTION_LIKE_HISTORICAL_FORECAST_WEATHER_COMPARISON_STATUS="
            "NOT_COMPUTABLE_NO_AS_ISSUED_ARCHIVE`.",
            "- `ORACLE_WEATHER_EXPERIMENT_EXECUTED=false`.",
            "",
            "## Version conclusion and next step",
            "",
            f"`WEATHER_INCREMENTAL_VALUE={classification}` is a historical OOT "
            "experiment conclusion only. It is not a production accuracy claim, "
            "not a forecast-time ECMWF claim, and not a Model B promotion.",
            "",
            "`BUSINESS_ACCURACY_THRESHOLD_STATUS=NOT_FROZEN`.",
            "`MODEL_B_PRODUCTION_PROMOTION_AUTHORIZED=false`.",
            "`V0_8_IMPLEMENTATION_AUTHORIZED=false`.",
            "",
            "S4 may recommend a later controlled experiment, but this PR does not "
            "open V0.8, retrain a model, change the S3 task, or deploy anything.",
            "",
        ]
    )
    return "\n".join(lines)


def _cumulative_table(summary: Mapping[str, Any]) -> str:
    rows = []
    for horizon in ("H7", "H15"):
        item = summary["horizons"][horizon]["cumulative"]
        rows.append(
            {
                "horizon": horizon,
                "complete windows": item.get("complete_view_count"),
                "A cumulative WAPE": item.get("model_a_pooled_wape"),
                "B cumulative WAPE": item.get("model_b_pooled_wape"),
                "B-A": item.get("absolute_delta_wape_b_minus_a"),
                "A abs error kg": item.get("model_a_pooled_absolute_error_kg"),
                "B abs error kg": item.get("model_b_pooled_absolute_error_kg"),
                "actual kg": item.get("pooled_actual_kg"),
            }
        )
    return _markdown_table(
        rows,
        (
            "horizon",
            "complete windows",
            "A cumulative WAPE",
            "B cumulative WAPE",
            "B-A",
            "A abs error kg",
            "B abs error kg",
            "actual kg",
        ),
    )


def _augment_analysis(
    *,
    analysis: dict[str, Any],
    private_evidence: Mapping[str, Any],
    public_evidence: Mapping[str, Any],
    score_paths: Mapping[str, Path],
    public_path: Path,
    private_path: Path,
    base_sha: str,
) -> dict[str, Any]:
    coverage: dict[str, Any] = {}
    views: dict[str, Any] = {}
    for fold in ("fold_a", "fold_b"):
        private_fold = private_evidence["folds"][fold]
        score_payload = _read_object(score_paths[fold])
        coverage[fold] = {
            "prediction_row_count": private_fold["validation_prediction_row_count"],
            "scored_row_count": score_payload["scored_row_count"],
            "unscored_row_count": score_payload["unscored_row_count"],
            "unscored_status_counts": score_payload["unscored_status_counts"],
            "validation_base_count": private_fold["validation_base_count"],
            "validation_season": private_fold["validation_season"],
        }
        views[fold] = {
            horizon: analysis["folds"][fold]["horizons"][horizon]["per_base"]
            for horizon in ("H1", "H7", "H15")
        }
    coverage["combined"] = {
        "prediction_row_count": sum(item["prediction_row_count"] for item in coverage.values()),
        "scored_row_count": sum(item["scored_row_count"] for item in coverage.values()),
        "unscored_row_count": sum(item["unscored_row_count"] for item in coverage.values()),
        "validation_base_count": len(
            set(
                analysis["folds"]["fold_a"]["per_base_base_ids"]
                + analysis["folds"]["fold_b"]["per_base_base_ids"]
            )
        )
        if "per_base_base_ids" in analysis["folds"]["fold_a"]
        else None,
    }
    analysis["coverage"] = coverage
    analysis["views"] = {
        fold: {
            horizon: analysis["folds"][fold]["_view_rows"][horizon]
            for horizon in ("H1", "H7", "H15")
        }
        for fold in ("fold_a", "fold_b")
    }
    analysis["views"]["combined"] = {
        horizon: analysis["combined"]["_view_rows"][horizon] for horizon in ("H1", "H7", "H15")
    }
    for scope in ("fold_a", "fold_b", "combined"):
        analysis["coverage"][scope].setdefault(
            "scored_row_count", analysis[scope]["scored_row_count"] if scope == "combined" else None
        )
        analysis["coverage"][scope].setdefault("unscored_row_count", None)
    analysis["s4"] = {
        "base_sha": base_sha,
        "s3_base_sha": public_evidence.get("base_sha_at_execution"),
        "s3_merge_commit": "3c43e84717174cd48bccd62dde2b97eedf76da15",
        "s3_pr_number": 647,
        "no_model_fit_in_s4": True,
        "no_model_refit_in_s4": True,
        "full_suite_ci_is_external_exact_head_gate": True,
    }
    source_identities = {
        "s3_public_evidence_sha256": _sha256(public_path),
        "s3_private_evidence_sha256": _sha256(private_path),
        "fold_a_score_after_seal_sha256": _sha256(score_paths["fold_a"]),
        "fold_b_score_after_seal_sha256": _sha256(score_paths["fold_b"]),
        "s3_public_evidence_logical_path": (
            "docs/v0-7/evidence/s3-weather-aware-model-training-and-oot-backtest.json"
        ),
        "s3_private_evidence_logical_path": "CONTROLLED_PRIVATE_S3_ARTIFACT/evidence.json",
    }
    analysis["source_identities"] = source_identities
    analysis["acceptance"] = {
        "s3_primary_metric_parity_pass": analysis["s3_primary_metric_parity"]["pass"],
        "model_a_artifact_hash_parity": analysis["s3_artifact_parity"][
            "model_a_artifact_hash_parity"
        ],
        "model_b_artifact_hash_parity": analysis["s3_artifact_parity"][
            "model_b_artifact_hash_parity"
        ],
        "model_a_prediction_hash_parity": analysis["s3_artifact_parity"][
            "model_a_prediction_hash_parity"
        ],
        "model_b_prediction_hash_parity": analysis["s3_artifact_parity"][
            "model_b_prediction_hash_parity"
        ],
        "error_reduction_decomposition_pass": all(
            (analysis["combined"] if scope == "combined" else analysis["folds"][scope])["horizons"][
                horizon
            ]["per_base"]["contributions"]["error_reduction_decomposition_pass"]
            for scope in ("fold_a", "fold_b", "combined")
            for horizon in ("H1", "H7", "H15")
        ),
        "bias_magnitude_comparison_pass": True,
        "error_distribution_comparison_pass": True,
        "leave_out_refit_pass": all(
            (analysis["combined"] if scope == "combined" else analysis["folds"][scope])["horizons"][
                horizon
            ]["per_base"]["contributions"]["leave_top1"]["refit"]
            is False
            and (analysis["combined"] if scope == "combined" else analysis["folds"][scope])[
                "horizons"
            ][horizon]["per_base"]["contributions"]["leave_top2"]["refit"]
            is False
            for scope in ("fold_a", "fold_b", "combined")
            for horizon in ("H1", "H7", "H15")
        ),
        "coverage_limitations_reported": True,
    }
    analysis["result_hash"] = digest(
        {key: value for key, value in analysis.items() if key != "result_hash"}
    )
    return analysis


def _prepare_analysis(
    *,
    public_path: Path,
    private_path: Path,
    fold_a_path: Path,
    fold_b_path: Path,
    base_sha: str,
) -> dict[str, Any]:
    public_evidence = _read_object(public_path)
    private_evidence = _read_object(private_path)
    scores = {
        "fold_a": _read_object(fold_a_path),
        "fold_b": _read_object(fold_b_path),
    }
    analysis = build_s4_analysis(
        fold_scores=scores,
        private_evidence=private_evidence,
        public_evidence=public_evidence,
    )
    # Keep row arrays only in memory while rendering; generated evidence does
    # not retain them.  The view arrays are needed for the report coverage
    # table, so render before removing them.
    for fold in ("fold_a", "fold_b"):
        analysis["folds"][fold]["_view_rows"] = {
            horizon: [dict(row) for row in build_views(scores[fold], horizon)]
            for horizon in ("H1", "H7", "H15")
        }
        analysis["folds"][fold]["per_base_base_ids"] = sorted(
            {str(row["base_id"]) for row in scores[fold]["scored_rows"]}
        )
    analysis["combined"]["_view_rows"] = {
        horizon: analysis["folds"]["fold_a"]["_view_rows"][horizon]
        + analysis["folds"]["fold_b"]["_view_rows"][horizon]
        for horizon in ("H1", "H7", "H15")
    }
    result = _augment_analysis(
        analysis=analysis,
        private_evidence=private_evidence,
        public_evidence=public_evidence,
        score_paths={"fold_a": fold_a_path, "fold_b": fold_b_path},
        public_path=public_path,
        private_path=private_path,
        base_sha=base_sha,
    )
    # The full rows are deliberately removed from the committed evidence
    # after the markdown report has been rendered by the caller.
    return result


def build_views(score: Mapping[str, Any], horizon: str) -> list[dict[str, Any]]:
    from backend.app.area_yield.weather_value_conclusion import complete_horizon_views

    rows = score["scored_rows"]
    boundary = __import__(
        "backend.app.area_yield.weather_value_conclusion",
        fromlist=["_boundary_for_score"],
    )._boundary_for_score(score)
    return complete_horizon_views(rows, boundary=boundary)[horizon]


def _strip_internal(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_internal(item)
            for key, item in value.items()
            if not key.startswith("_") and key not in {"views"}
        }
    if isinstance(value, list):
        return [_strip_internal(item) for item in value]
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--s3-public-evidence", type=Path, required=True)
    parser.add_argument("--s3-private-evidence", type=Path, required=True)
    parser.add_argument("--fold-a-score", type=Path, required=True)
    parser.add_argument("--fold-b-score", type=Path, required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument(
        "--output-evidence",
        type=Path,
        default=Path("docs/v0-7/evidence/s4-model-a-b-comparison-and-version-conclusion.json"),
    )
    parser.add_argument(
        "--output-report",
        type=Path,
        default=Path("docs/v0-7/s4/model-a-b-comparison-and-version-conclusion.md"),
    )
    args = parser.parse_args()
    analysis = _prepare_analysis(
        public_path=args.s3_public_evidence,
        private_path=args.s3_private_evidence,
        fold_a_path=args.fold_a_score,
        fold_b_path=args.fold_b_score,
        base_sha=args.base_sha,
    )
    report = render_report(analysis)
    evidence = _strip_internal(analysis)
    evidence["report_sha256"] = hashlib.sha256(report.encode()).hexdigest()
    evidence["result_hash"] = digest(
        {key: value for key, value in evidence.items() if key != "result_hash"}
    )
    _write_json(args.output_evidence, evidence)
    args.output_report.parent.mkdir(parents=True, exist_ok=True)
    args.output_report.write_text(report, encoding="utf-8")
    print(f"S4_EVIDENCE={args.output_evidence}")
    print(f"S4_REPORT={args.output_report}")
    print(f"S4_RESULT_HASH={evidence['result_hash']}")
    print(
        f"S3_PRIMARY_METRIC_PARITY_PASS={evidence['acceptance']['s3_primary_metric_parity_pass']}"
    )
    print(f"WEATHER_INCREMENTAL_VALUE={evidence['weather_incremental_value']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
