"""Deterministic V0.7-S4 comparison of the frozen S3 Model A and Model B.

This module is deliberately inference-only.  It consumes the sealed S3
prediction rows and their post-seal scores; it never fits a model, reads a
training source, or changes the S3 row scope.  All aggregations use the S3
complete-horizon denominator policy and Decimal arithmetic so the conclusion
can be replayed from the controlled row-level artifact.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from backend.app.area_yield.data import digest
from backend.app.area_yield.formal_multi_season_validation import (
    BusinessBoundary,
    business_boundary,
)
from backend.app.area_yield.weather_aware_backtest import (
    HORIZONS,
    MODEL_A_S3,
    MODEL_B1,
    _complete_horizon_rows,
)

ALLOWED_WEATHER_INCREMENTAL_VALUE = frozenset(
    {
        "SUPPORTED_BY_HISTORICAL_OOT_EVIDENCE",
        "NOT_DEMONSTRATED",
        "UNSTABLE_ACROSS_SEASONS",
        "INCONCLUSIVE",
    }
)

# These are the S3 R2 primary WAPE values accepted by PR #647.  Keeping the
# reference in the comparison boundary prevents a changed artifact from being
# silently treated as the same experiment.
S3_PRIMARY_WAPE_REFERENCE: dict[str, dict[str, tuple[str, str]]] = {
    "fold_a": {
        "H1": ("0.5735007172166231354939150247", "0.5712674368698074356303994552"),
        "H7": ("0.5740635012743079200397000277", "0.5598280551919795726817188018"),
        "H15": ("0.5766585085673582207236496244", "0.5668383352648546388586439127"),
    },
    "fold_b": {
        "H1": ("0.5353785100212518009093563999", "0.5270941105936877811007125420"),
        "H7": ("0.5228899179358368129482200790", "0.5035973330809727732919925954"),
        "H15": ("0.5242647222257295327448299625", "0.5032230970616741330430591370"),
    },
    "combined": {
        "H1": ("0.5444649243638447728953130494", "0.5376228069878489890305679374"),
        "H7": ("0.5347506341910098593067011251", "0.5166301636211149439149827418"),
        "H15": ("0.5361813512430062990109994014", "0.5176919729808530068973419994"),
    },
}


class WeatherValueConclusionError(ValueError):
    """Raised when frozen S3 evidence cannot support an S4 comparison."""


def _decimal(value: Any) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite():
        raise WeatherValueConclusionError("NONFINITE_NUMERIC_VALUE")
    return result


def _text(value: Decimal) -> str:
    if not value.is_finite():
        raise WeatherValueConclusionError("NONFINITE_NUMERIC_VALUE")
    return format(value, "f")


def _boundary_for_score(score: Mapping[str, Any]) -> BusinessBoundary:
    boundary = score.get("boundary")
    if not isinstance(boundary, Mapping):
        raise WeatherValueConclusionError("S3_BOUNDARY_MISSING")
    season = str(boundary.get("season", ""))
    resolved = business_boundary(season)
    expected = resolved.payload()
    actual = {str(key): str(value) for key, value in boundary.items()}
    if actual != expected:
        raise WeatherValueConclusionError("S3_BOUNDARY_AUTHORITY_MISMATCH")
    return resolved


def complete_horizon_views(
    rows: Sequence[Mapping[str, Any]], *, boundary: BusinessBoundary
) -> dict[str, list[dict[str, Any]]]:
    """Use exactly S3's complete-origin view policy for H1/H7/H15."""

    return {
        horizon: _complete_horizon_rows(
            [row for row in rows if int(row["lead_day"]) < horizon_days],
            horizon_days=horizon_days,
            boundary=boundary,
        )
        for horizon, horizon_days in HORIZONS.items()
    }


def _error_distribution(values: Sequence[Decimal]) -> dict[str, str | None]:
    if not values:
        return {"median": None, "p75": None, "p90": None, "max": None}
    ordered = sorted(values)

    def percentile(fraction: Decimal) -> Decimal:
        position = fraction * Decimal(len(ordered) - 1)
        low = int(position)
        high = min(low + 1, len(ordered) - 1)
        return ordered[low] + (position - Decimal(low)) * (ordered[high] - ordered[low])

    return {
        "median": _text(percentile(Decimal("0.5"))),
        "p75": _text(percentile(Decimal("0.75"))),
        "p90": _text(percentile(Decimal("0.9"))),
        "max": _text(max(ordered)),
    }


def metric(rows: Sequence[Mapping[str, Any]], prediction_key: str) -> dict[str, Any]:
    """Return pooled WAPE plus the frozen daily error summaries."""

    if not rows:
        return {"status": "NOT_COMPUTABLE_NO_COMPARABLE_ROWS", "sample_count": 0}
    actual = [_decimal(row["actual_daily_kg"]) for row in rows]
    predicted = [_decimal(row[prediction_key]) for row in rows]
    signed = [left - right for left, right in zip(predicted, actual, strict=True)]
    absolute = [abs(value) for value in signed]
    actual_total = sum(actual, Decimal(0))
    absolute_total = sum(absolute, Decimal(0))
    if actual_total <= 0:
        return {
            "status": "NOT_COMPUTABLE_ZERO_ACTUAL_DENOMINATOR",
            "sample_count": len(rows),
            "pooled_actual_kg": _text(actual_total),
        }
    return {
        "status": "COMPUTABLE",
        "sample_count": len(rows),
        "mae_kg": _text(absolute_total / Decimal(len(rows))),
        "pooled_wape": _text(absolute_total / actual_total),
        "bias_kg": _text(sum(signed, Decimal(0)) / Decimal(len(rows))),
        "bias_definition": "MEAN_PREDICTED_MINUS_ACTUAL; POSITIVE_OVERPREDICTION",
        "pooled_actual_kg": _text(actual_total),
        "pooled_absolute_error_kg": _text(absolute_total),
        "error_distribution_abs_kg": _error_distribution(absolute),
    }


def _subtract(left: Any, right: Any) -> str | None:
    if not isinstance(left, str) or not isinstance(right, str):
        return None
    if left.startswith("NOT_COMPUTABLE") or right.startswith("NOT_COMPUTABLE"):
        return None
    return _text(_decimal(right) - _decimal(left))


def _relative_improvement(a_wape: Any, b_wape: Any) -> str | None:
    if not isinstance(a_wape, str) or not isinstance(b_wape, str):
        return None
    a_value = _decimal(a_wape)
    if a_value == 0:
        return None
    return _text((a_value - _decimal(b_wape)) / a_value)


def compare_metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Compare A and B on one exactly defined row set."""

    a = metric(rows, "model_a_predicted_daily_kg")
    b = metric(rows, "model_b_predicted_daily_kg")
    wape_delta = _subtract(a.get("pooled_wape"), b.get("pooled_wape"))
    return {
        "sample_count": len(rows),
        "model_a": a,
        "model_b": b,
        "absolute_delta": {
            "daily_wape_b_minus_a": wape_delta,
            "daily_mae_b_minus_a": _subtract(a.get("mae_kg"), b.get("mae_kg")),
            "bias_b_minus_a": _subtract(a.get("bias_kg"), b.get("bias_kg")),
        },
        "relative_improvement": {
            "daily_wape": _relative_improvement(a.get("pooled_wape"), b.get("pooled_wape"))
        },
        "bias_magnitude_delta": _subtract(
            _text(abs(_decimal(a["bias_kg"]))) if "bias_kg" in a else None,
            _text(abs(_decimal(b["bias_kg"]))) if "bias_kg" in b else None,
        ),
        "delta_definition": "MODEL_B_MINUS_MODEL_A",
        "relative_improvement_definition": "(MODEL_A-MODEL_B)/MODEL_A",
    }


def cumulative_compare(rows: Sequence[Mapping[str, Any]], *, horizon_days: int) -> dict[str, Any]:
    """Compare sums over each complete origin window, without zero-fill."""

    grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[
            (
                str(row.get("season", "")),
                str(row["base_id"]),
                str(row["forecast_origin"]),
            )
        ].append(row)
    windows: list[dict[str, Decimal]] = []
    for key in sorted(grouped):
        window = sorted(grouped[key], key=lambda row: int(row["lead_day"]))
        if len(window) != horizon_days or {int(row["lead_day"]) for row in window} != set(
            range(horizon_days)
        ):
            continue
        windows.append(
            {
                "actual": sum((_decimal(row["actual_daily_kg"]) for row in window), Decimal(0)),
                "model_a": sum(
                    (_decimal(row["model_a_predicted_daily_kg"]) for row in window), Decimal(0)
                ),
                "model_b": sum(
                    (_decimal(row["model_b_predicted_daily_kg"]) for row in window), Decimal(0)
                ),
            }
        )
    if not windows:
        return {
            "status": "NOT_COMPUTABLE_INCOMPLETE_TARGET_WINDOW",
            "complete_view_count": 0,
        }
    actual_total = sum((window["actual"] for window in windows), Decimal(0))
    a_error = sum((abs(window["model_a"] - window["actual"]) for window in windows), Decimal(0))
    b_error = sum((abs(window["model_b"] - window["actual"]) for window in windows), Decimal(0))
    if actual_total <= 0:
        return {
            "status": "NOT_COMPUTABLE_ZERO_ACTUAL_DENOMINATOR",
            "complete_view_count": len(windows),
        }
    a_wape = a_error / actual_total
    b_wape = b_error / actual_total
    return {
        "status": "COMPUTABLE",
        "complete_view_count": len(windows),
        "model_a_pooled_wape": _text(a_wape),
        "model_b_pooled_wape": _text(b_wape),
        "absolute_delta_wape_b_minus_a": _text(b_wape - a_wape),
        "model_a_pooled_absolute_error_kg": _text(a_error),
        "model_b_pooled_absolute_error_kg": _text(b_error),
        "pooled_actual_kg": _text(actual_total),
    }


def _direction(delta: str | None) -> str:
    if delta is None:
        return "NOT_COMPUTABLE"
    value = _decimal(delta)
    if value < 0:
        return "IMPROVED"
    if value > 0:
        return "DEGRADED"
    return "UNCHANGED"


def _leave_direction(delta: str | None) -> str:
    if delta is None:
        return "NOT_COMPUTABLE"
    value = _decimal(delta)
    if value < 0:
        return "IMPROVES"
    if value > 0:
        return "DEGRADES"
    return "UNCHANGED"


def _base_ids(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    return sorted({str(row["base_id"]) for row in rows})


def _base_name(rows: Sequence[Mapping[str, Any]], base_id: str) -> str:
    names = sorted(
        {str(row.get("base_name", base_id)) for row in rows if str(row["base_id"]) == base_id}
    )
    return names[0] if names else base_id


def _base_metric_entry(
    *, base_id: str, base_name: str, rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    comparison = compare_metrics(rows)
    a = comparison["model_a"]
    b = comparison["model_b"]
    delta = comparison["absolute_delta"]["daily_wape_b_minus_a"]
    if delta is None:
        status = "NOT_COMPUTABLE"
        reduction = None
    else:
        status = _direction(delta)
        reduction = _text(
            _decimal(a["pooled_absolute_error_kg"]) - _decimal(b["pooled_absolute_error_kg"])
        )
    return {
        "base_id": base_id,
        "canonical_base_name": base_name,
        "status": status,
        "complete_horizon_row_count": len(rows),
        "model_a_wape": a.get("pooled_wape"),
        "model_b_wape": b.get("pooled_wape"),
        "wape_delta_b_minus_a": delta,
        "model_a_bias_kg": a.get("bias_kg"),
        "model_b_bias_kg": b.get("bias_kg"),
        "actual_denominator_kg": a.get("pooled_actual_kg"),
        "model_a_absolute_error_kg": a.get("pooled_absolute_error_kg"),
        "model_b_absolute_error_kg": b.get("pooled_absolute_error_kg"),
        "absolute_error_reduction_kg": reduction,
    }


def _distribution(values: Sequence[int]) -> dict[str, int | None]:
    if not values:
        return {"min": None, "median": None, "p75": None, "max": None}
    ordered = sorted(values)

    def nearest_rank(fraction: Decimal) -> int:
        position = int((fraction * Decimal(len(ordered) - 1)).to_integral_value())
        return ordered[position]

    return {
        "min": ordered[0],
        "median": nearest_rank(Decimal("0.5")),
        "p75": nearest_rank(Decimal("0.75")),
        "max": ordered[-1],
    }


def _breadth(entries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    comparable = [
        entry for entry in entries if entry["status"] in {"IMPROVED", "DEGRADED", "UNCHANGED"}
    ]
    improved = [entry for entry in comparable if entry["status"] == "IMPROVED"]
    degraded = [entry for entry in comparable if entry["status"] == "DEGRADED"]
    actual_total = sum(
        (_decimal(entry["actual_denominator_kg"]) for entry in comparable), Decimal(0)
    )

    def share(count: int, denominator: int) -> str | None:
        return _text(Decimal(count) / Decimal(denominator)) if denominator else None

    def actual_share(group: Sequence[Mapping[str, Any]]) -> str | None:
        return (
            _text(
                sum((_decimal(entry["actual_denominator_kg"]) for entry in group), Decimal(0))
                / actual_total
            )
            if actual_total > 0
            else None
        )

    return {
        "comparable_base_count": len(comparable),
        "improved_base_count": len(improved),
        "degraded_base_count": len(degraded),
        "unchanged_base_count": sum(entry["status"] == "UNCHANGED" for entry in comparable),
        "not_computable_base_count": sum(entry["status"] == "NOT_COMPUTABLE" for entry in entries),
        "improved_base_count_share": share(len(improved), len(comparable)),
        "degraded_base_count_share": share(len(degraded), len(comparable)),
        "improved_base_actual_kg_share": actual_share(improved),
        "degraded_base_actual_kg_share": actual_share(degraded),
        "comparable_actual_denominator_kg": _text(actual_total),
    }


def _contributions(
    *,
    entries: Sequence[Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]],
    comparison: Mapping[str, Any],
) -> dict[str, Any]:
    comparable = [entry for entry in entries if entry["absolute_error_reduction_kg"] is not None]
    reductions = [
        (_decimal(entry["absolute_error_reduction_kg"]), str(entry["base_id"]))
        for entry in comparable
    ]
    net = sum((value for value, _ in reductions), Decimal(0))
    positive = sorted(
        [(value, base_id) for value, base_id in reductions if value > 0],
        key=lambda item: (-item[0], item[1]),
    )
    positive_total = sum((value for value, _ in positive), Decimal(0))
    aggregate_reduction = _decimal(comparison["model_a"]["pooled_absolute_error_kg"]) - _decimal(
        comparison["model_b"]["pooled_absolute_error_kg"]
    )
    decomposition_pass = net == aggregate_reduction

    def contributor(index: int) -> dict[str, Any] | None:
        if len(positive) < index:
            return None
        value, base_id = positive[index - 1]
        return {
            "base_id": base_id,
            "canonical_base_name": next(
                (
                    str(entry["canonical_base_name"])
                    for entry in entries
                    if str(entry["base_id"]) == base_id
                ),
                base_id,
            ),
            "error_reduction_kg": _text(value),
            "positive_contribution_share": (
                _text(value / positive_total) if positive_total > 0 else None
            ),
            "net_improvement_share": _text(value / net) if net != 0 else None,
        }

    result: dict[str, Any] = {
        "aggregate_error_reduction_kg": _text(aggregate_reduction),
        "sum_base_error_reduction_kg": _text(net),
        "error_reduction_decomposition_pass": decomposition_pass,
        "positive_contribution_denominator_kg": _text(positive_total),
        "top1_positive_contributor": contributor(1),
        "top2_positive_contributors": [item for item in (contributor(1), contributor(2)) if item],
        "top1_positive_contribution_share": (
            _text(positive[0][0] / positive_total) if positive and positive_total > 0 else None
        ),
        "top2_positive_contribution_share": (
            _text(sum((item[0] for item in positive[:2]), Decimal(0)) / positive_total)
            if positive and positive_total > 0
            else None
        ),
    }

    for count, label in ((1, "top1"), (2, "top2")):
        removed = {base_id for _, base_id in positive[:count]}
        if not removed:
            result[f"leave_{label}"] = {
                "removed_base_ids": [],
                "delta": None,
                "direction": "NOT_COMPUTABLE_NO_POSITIVE_CONTRIBUTOR",
            }
            continue
        remaining = [row for row in rows if str(row["base_id"]) not in removed]
        leave = compare_metrics(remaining)
        delta = leave["absolute_delta"]["daily_wape_b_minus_a"]
        result[f"leave_{label}"] = {
            "removed_base_ids": sorted(removed),
            "model_a_wape": leave["model_a"].get("pooled_wape"),
            "model_b_wape": leave["model_b"].get("pooled_wape"),
            "delta": delta,
            "direction": _leave_direction(delta),
            "refit": False,
        }
    return result


def _per_base_comparison(
    *,
    all_rows: Sequence[Mapping[str, Any]],
    view_rows: Sequence[Mapping[str, Any]],
    comparison: Mapping[str, Any],
) -> dict[str, Any]:
    ids = _base_ids(all_rows)
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in view_rows:
        grouped[str(row["base_id"])].append(row)
    entries = [
        _base_metric_entry(
            base_id=base_id,
            base_name=_base_name(all_rows, base_id),
            rows=grouped.get(base_id, []),
        )
        for base_id in ids
    ]
    contributions = _contributions(entries=entries, rows=view_rows, comparison=comparison)
    return {
        "entries": entries,
        "breadth": _breadth(entries),
        "contributions": contributions,
        "complete_horizon_row_count_distribution": _distribution(
            [int(entry["complete_horizon_row_count"]) for entry in entries]
        ),
    }


def _lead_day_comparison(h15_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for lead_day in range(15):
        rows = [row for row in h15_rows if int(row["lead_day"]) == lead_day]
        result[str(lead_day)] = compare_metrics(rows)
    return {
        "basis": "H15_COMPLETE_HORIZON_VIEWS",
        "lead_days": result,
    }


def _scope_summary(
    *,
    all_rows: Sequence[Mapping[str, Any]],
    views: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    horizons: dict[str, Any] = {}
    for horizon, rows in views.items():
        comparison = compare_metrics(rows)
        horizons[horizon] = {
            "comparison": comparison,
            "cumulative": cumulative_compare(rows, horizon_days=HORIZONS[horizon]),
            "per_base": _per_base_comparison(
                all_rows=all_rows,
                view_rows=rows,
                comparison=comparison,
            ),
        }
    return {
        "candidate_scored_base_count": len(_base_ids(all_rows)),
        "scored_row_count": len(all_rows),
        "horizons": horizons,
        "lead_day": _lead_day_comparison(views["H15"]),
    }


def _exact_match(actual: Any, expected: str) -> bool:
    return isinstance(actual, str) and actual == expected


def validate_s3_primary_parity(
    *,
    fold_scores: Mapping[str, Mapping[str, Any]],
    public_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify public and controlled score artifacts retain S3's exact WAPEs."""

    checks: dict[str, bool] = {}
    for scope in ("fold_a", "fold_b"):
        score_models = fold_scores[scope]["models"]
        public_fold = public_evidence["folds"][scope]
        for horizon in HORIZONS:
            for model_id, position in ((MODEL_A_S3, 0), (MODEL_B1, 1)):
                private_value = score_models[model_id]["horizons"][horizon]["pooled_wape"]
                public_value = public_fold["score"]["models"][model_id]["horizons"][horizon][
                    "pooled_wape"
                ]
                expected = S3_PRIMARY_WAPE_REFERENCE[scope][horizon][position]
                checks[f"{scope}.{horizon}.{model_id}.private"] = _exact_match(
                    private_value, expected
                )
                checks[f"{scope}.{horizon}.{model_id}.public"] = _exact_match(
                    public_value, expected
                )
                checks[f"{scope}.{horizon}.{model_id}.private_public"] = (
                    private_value == public_value
                )

    combined = public_evidence["combined"]
    for horizon in HORIZONS:
        for model_id, position in ((MODEL_A_S3, 0), (MODEL_B1, 1)):
            actual = combined["models"][model_id]["horizons"][horizon]["pooled_wape"]
            expected = S3_PRIMARY_WAPE_REFERENCE["combined"][horizon][position]
            checks[f"combined.{horizon}.{model_id}"] = _exact_match(actual, expected)
    return {"pass": all(checks.values()), "checks": checks}


def _artifact_parity(
    *,
    private_evidence: Mapping[str, Any],
    public_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    for fold in ("fold_a", "fold_b"):
        private = private_evidence["folds"][fold]
        public = public_evidence["folds"][fold]
        for key in (
            "model_a_artifact_hash",
            "model_b_artifact_hash",
            "model_a_prediction_hash",
            "model_b_prediction_hash",
            "artifact_manifest_hash",
        ):
            checks[f"{fold}.{key}"] = (
                private["prediction_manifest"][key] == public["prediction_manifest"][key]
            )
    return {
        "model_a_artifact_hash_parity": all(
            value for key, value in checks.items() if "model_a_artifact_hash" in key
        ),
        "model_b_artifact_hash_parity": all(
            value for key, value in checks.items() if "model_b_artifact_hash" in key
        ),
        "model_a_prediction_hash_parity": all(
            value for key, value in checks.items() if "model_a_prediction_hash" in key
        ),
        "model_b_prediction_hash_parity": all(
            value for key, value in checks.items() if "model_b_prediction_hash" in key
        ),
        "artifact_manifest_hash_parity": all(checks.values()),
        "checks": checks,
    }


def _fold_views(
    score: Mapping[str, Any],
) -> tuple[BusinessBoundary, dict[str, list[dict[str, Any]]]]:
    boundary = _boundary_for_score(score)
    rows = score.get("scored_rows")
    if not isinstance(rows, list):
        raise WeatherValueConclusionError("S3_SCORED_ROWS_MISSING")
    return boundary, complete_horizon_views(rows, boundary=boundary)


def classify_weather_incremental_value(
    *,
    fold_summaries: Mapping[str, Mapping[str, Any]],
    combined_summary: Mapping[str, Any],
    parity_pass: bool,
) -> tuple[str, str]:
    """Apply the frozen qualitative classification order without thresholds."""

    if not parity_pass:
        return "INCONCLUSIVE", "S3_PRIMARY_METRIC_PARITY_FAILED"

    fold_directions: dict[str, dict[str, str]] = {}
    for fold in ("fold_a", "fold_b"):
        fold_directions[fold] = {
            horizon: _direction(
                fold_summaries[fold]["horizons"][horizon]["comparison"]["absolute_delta"][
                    "daily_wape_b_minus_a"
                ]
            )
            for horizon in HORIZONS
        }
    opposite_fold = any(
        fold_directions["fold_a"][horizon] in {"IMPROVED", "DEGRADED"}
        and fold_directions["fold_b"][horizon] in {"IMPROVED", "DEGRADED"}
        and fold_directions["fold_a"][horizon] != fold_directions["fold_b"][horizon]
        for horizon in HORIZONS
    )
    combined_directions = {
        horizon: _direction(
            combined_summary["horizons"][horizon]["comparison"]["absolute_delta"][
                "daily_wape_b_minus_a"
            ]
        )
        for horizon in HORIZONS
    }
    if opposite_fold:
        return "UNSTABLE_ACROSS_SEASONS", "FOLD_DIRECTION_CONFLICT"
    if any(value != "IMPROVED" for value in combined_directions.values()) or any(
        value != "IMPROVED" for fold in fold_directions.values() for value in fold.values()
    ):
        return "NOT_DEMONSTRATED", "PRIMARY_POOLED_OR_FOLD_HORIZON_NOT_ALL_IMPROVED"

    leave_out_reversal = []
    for horizon in HORIZONS:
        leave_top2 = combined_summary["horizons"][horizon]["per_base"]["contributions"][
            "leave_top2"
        ]
        if leave_top2["direction"] != "IMPROVES":
            leave_out_reversal.append(horizon)
    if leave_out_reversal:
        return (
            "INCONCLUSIVE",
            "LEAVE_TOP2_ROBUSTNESS_REVERSES_OR_LOSES_IMPROVEMENT:" + ",".join(leave_out_reversal),
        )
    return (
        "SUPPORTED_BY_HISTORICAL_OOT_EVIDENCE",
        "ALL_FROZEN_FOLD_AND_HORIZON_POOLED_WAPES_IMPROVE_WITHOUT_LEAVE_TOP2_REVERSAL",
    )


def build_s4_analysis(
    *,
    fold_scores: Mapping[str, Mapping[str, Any]],
    private_evidence: Mapping[str, Any],
    public_evidence: Mapping[str, Any],
    source_identities: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build the complete deterministic S4 comparison evidence."""

    parity = validate_s3_primary_parity(
        fold_scores=fold_scores,
        public_evidence=public_evidence,
    )
    artifact_parity = _artifact_parity(
        private_evidence=private_evidence,
        public_evidence=public_evidence,
    )
    fold_views: dict[str, dict[str, list[dict[str, Any]]]] = {}
    boundaries: dict[str, BusinessBoundary] = {}
    for fold in ("fold_a", "fold_b"):
        boundary, views = _fold_views(fold_scores[fold])
        boundaries[fold] = boundary
        fold_views[fold] = views

    fold_summaries = {
        fold: _scope_summary(
            all_rows=list(fold_scores[fold]["scored_rows"]),
            views=fold_views[fold],
        )
        for fold in ("fold_a", "fold_b")
    }
    combined_views = {
        horizon: fold_views["fold_a"][horizon] + fold_views["fold_b"][horizon]
        for horizon in HORIZONS
    }
    combined_rows = list(fold_scores["fold_a"]["scored_rows"]) + list(
        fold_scores["fold_b"]["scored_rows"]
    )
    combined_summary = _scope_summary(all_rows=combined_rows, views=combined_views)
    classification, classification_reason = classify_weather_incremental_value(
        fold_summaries=fold_summaries,
        combined_summary=combined_summary,
        parity_pass=parity["pass"] and artifact_parity["artifact_manifest_hash_parity"],
    )
    if classification not in ALLOWED_WEATHER_INCREMENTAL_VALUE:
        raise WeatherValueConclusionError("INVALID_WEATHER_INCREMENTAL_CLASSIFICATION")

    fold_direction_consistency = {
        horizon: (
            _direction(
                fold_summaries["fold_a"]["horizons"][horizon]["comparison"]["absolute_delta"][
                    "daily_wape_b_minus_a"
                ]
            )
            == _direction(
                fold_summaries["fold_b"]["horizons"][horizon]["comparison"]["absolute_delta"][
                    "daily_wape_b_minus_a"
                ]
            )
        )
        for horizon in HORIZONS
    }
    horizon_direction_consistency = (
        len(
            {
                _direction(
                    combined_summary["horizons"][horizon]["comparison"]["absolute_delta"][
                        "daily_wape_b_minus_a"
                    ]
                )
                for horizon in HORIZONS
            }
        )
        == 1
    )
    evidence: dict[str, Any] = {
        "task_id": "V0_7_S4_MODEL_A_B_COMPARISON_AND_VERSION_CONCLUSION_R1",
        "slice": "S4",
        "status": "HISTORICAL_OOT_WEATHER_SIGNAL_EXPERIMENT",
        "models": {
            "model_a": MODEL_A_S3,
            "model_b": MODEL_B1,
            "model_retrained": False,
            "model_refit": False,
            "automatic_model_selection": False,
            "feature_search": False,
            "hyperparameter_search": False,
        },
        "s3_artifact_parity": artifact_parity,
        "s3_primary_metric_parity": parity,
        "folds": fold_summaries,
        "combined": combined_summary,
        "consistency": {
            "fold_direction_by_horizon": fold_direction_consistency,
            "fold_direction_consistency_pass": all(fold_direction_consistency.values()),
            "horizon_direction_consistency_pass": horizon_direction_consistency,
        },
        "scope": {
            "s1_baseline_reference_only": True,
            "s1_combined_daily_wape_reference": "0.7245703036857014811985535015",
            "s1_baseline_and_s3_parity_task_differ": True,
            "direct_72p46_to_51p77_weather_attribution_forbidden": True,
            "weather_evidence_scope": "HISTORICAL_OOT_WEATHER_SIGNAL_ONLY",
            "lane_b_executed": False,
            "oracle_weather_experiment_executed": False,
            "era5_forecast_time_known_at_status": "NOT_ESTABLISHED",
            "lane_a_production_like_pit_eligible": False,
            "historical_as_issued_ecmwf_archive_2024_2025": "NOT_FOUND",
            "historical_as_issued_ecmwf_archive_2025_2026": "NOT_FOUND",
            "production_like_historical_forecast_weather_comparison_status": (
                "NOT_COMPUTABLE_NO_AS_ISSUED_ARCHIVE"
            ),
        },
        "weather_incremental_value": classification,
        "weather_incremental_value_reason": classification_reason,
        "business_accuracy_threshold_status": "NOT_FROZEN",
        "production_promotion_authorized": False,
        "source_identities": dict(sorted((source_identities or {}).items())),
    }
    evidence["result_hash"] = digest(evidence)
    return evidence


__all__ = [
    "ALLOWED_WEATHER_INCREMENTAL_VALUE",
    "S3_PRIMARY_WAPE_REFERENCE",
    "WeatherValueConclusionError",
    "build_s4_analysis",
    "compare_metrics",
    "complete_horizon_views",
    "metric",
    "validate_s3_primary_parity",
]
