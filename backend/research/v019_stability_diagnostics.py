"""Exact error accounting for S5; no model selection or causal season claims."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Context, Decimal, localcontext
from typing import Any, cast

from backend.research import v019_real_training_cli as s4
from backend.research import v019_research_execution as engine
from backend.research import v019_stability as stable

METHODS = (*s4.METHODS, stable.METHOD)


def serial(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(k): serial(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serial(v) for v in value]
    return value


def expand(compacted: dict[str, Any]) -> dict[str, Any]:
    def visit(obj: Any) -> Any:
        if isinstance(obj, list):
            return [visit(v) for v in obj]
        if not isinstance(obj, dict):
            return obj
        out = {}
        for key, value in obj.items():
            if key == "common_member_ids_ref":
                out["common_member_ids"] = compacted["cohort_member_sets"][value]
            elif key == "exclusions_ref":
                out["exclusions"] = compacted["exclusion_ledgers"][value]
            else:
                out[key] = visit(value)
        return out

    return cast(dict[str, Any], visit(compacted))


def five_model_evaluation(
    old: dict[str, Any],
    new: dict[str, Any],
    labels: dict[str, Any],
    reference: dict[str, Any],
    label_ids: dict[str, str],
) -> dict[str, Any]:
    result = {}
    for e in ("A", "B"):
        previous, candidate = old["experiments"][e], new["experiments"][e]
        if candidate["members"] != previous["members"]:
            raise ValueError("C0_MEMBER_DRIFT")
        curves = {
            m: {b: engine.curve_rows(rr) for b, rr in cc.items()}
            for m, cc in previous["curves"].items()
        }
        if set(curves) != set(s4.METHODS):
            raise ValueError("OLD_FOUR_MODEL_SET_CHANGED")
        curves[stable.METHOD] = {b: engine.curve_rows(rr) for b, rr in candidate["curves"].items()}
        scored = s4.evaluate(
            curves, labels[e], previous["members"], previous["training_bases"], label_ids[e]
        )
        complete = scored["comparison_status"] == "COMPLETE_FOUR_MODEL_COMMON_COHORT"
        scored["comparison_status"] = (
            "COMPLETE_FIVE_MODEL_COMMON_COHORT"
            if complete
            else "BLOCKED_INCOMPLETE_COMPARISON_NO_OVERALL_WINNER"
        )
        if complete:
            pairs = [(scored["groups"], reference["experiments"][e]["groups"])]
            for category in ("per_base", "seen_unseen"):
                if set(scored[category]) != set(reference["experiments"][e][category]):
                    raise ValueError("OLD_COHORT_GROUP_DRIFT")
                pairs += [
                    (v["groups"], reference["experiments"][e][category][key]["groups"])
                    for key, v in scored[category].items()
                ]
            for current, frozen in pairs:
                for window in current:
                    for model in s4.METHODS:
                        if current[window][model] != frozen[window][model]:
                            raise ValueError("FROZEN_FOUR_MODEL_METRIC_DRIFT")
        scored["old_four_metric_parity"] = complete
        result[e] = scored
    return {
        "experiments": result,
        "research_status": "EXPLORATORY",
        "strict_pit": False,
        "production_eligible": False,
    }


def _training_totals(rows: list[dict[str, Any]]) -> dict[str, list[Decimal]]:
    out: dict[str, list[Decimal]] = {}
    for row in rows:
        area = Decimal(row["area_mu"])
        p = sum(map(Decimal, row["baseline"]), Decimal(0))
        a = sum(map(Decimal, row["actual"]), Decimal(0))
        totals = out.setdefault(row["base_id"], [Decimal(0), Decimal(0), Decimal(0)])
        totals[0] += p / area
        totals[1] += a / area
        totals[2] += 1
    return out


def _global_ratio(rows: list[dict[str, Any]]) -> dict[str, Any]:
    totals = _training_totals(rows)
    p = sum((v[0] for v in totals.values()), Decimal(0))
    a = sum((v[1] for v in totals.values()), Decimal(0))
    return {
        "sum_baseline_kg_per_mu": p,
        "sum_actual_kg_per_mu": a,
        "factor": a / p if p else None,
        "training_bins": len(rows),
        "base_count": len(totals),
    }


def factor_diagnostics(
    training: dict[str, Any], fitted: dict[str, Any], new: dict[str, Any]
) -> dict[str, Any]:
    with localcontext(Context(prec=50)):
        experiments = {}
        inventory = training["admission"]["inventory"]
        for e in ("A", "B"):
            fit = fitted["experiments"][e]
            totals = _training_totals(fit["normalized_training_rows"])
            records = {}
            g = Decimal(fit["fitted"]["global_factor"])
            for bid, (p, a, n) in totals.items():
                raw = a / p if p else None
                # Match the frozen estimator's operation order at precision 50.
                final = (n * a / p + 4 * g) / (n + 4) if p else g
                if final != Decimal(fit["fitted"]["base_factors"][bid]):
                    raise ValueError("ORIGINAL_SHRINKAGE_RECONSTRUCTION_DRIFT")
                members = [
                    {
                        "season": r["season"],
                        "area_mu": r["area_mu"],
                        "source_member_count": len(r["members"]),
                        "source_members": r["members"],
                        "full_authorized_days": r["daily_count"],
                    }
                    for r in inventory
                    if r["status"] == "ADMIT"
                    and r["base_id"] == bid
                    and r["season"] in fit["training_seasons"]
                ]
                records[bid] = {
                    "complete_training_bins": int(n),
                    "raw_pooled_factor": raw,
                    "original_shrunk_factor": final,
                    "global_shrinkage_weight": 4 / (n + 4),
                    "complete_bin_actual_kg_per_mu": a,
                    "complete_bin_baseline_kg_per_mu": p,
                    "training_members": members,
                    "consensus": new["experiments"][e]["fitted"]["base_records"][bid],
                }
            ratio = _global_ratio(fit["normalized_training_rows"])
            if ratio["factor"] != g:
                raise ValueError("ORIGINAL_GLOBAL_FACTOR_DRIFT")
            experiments[e] = {
                "global_factor": g,
                "original_fit_sha256": fit["sha256"],
                "original_parameter_sha256": fit["fitted"]["sha256"],
                "training_seasons": fit["training_seasons"],
                "profile_file_sha256": new["experiments"][e]["fitted"]["profile_sha256"],
                "base_factors": records,
                "full_season_summaries": new["experiments"][e]["fitted"]["season_summaries"],
                "full_season_factors_include_short_tail": True,
                "original_fit_uses_complete_bins_only": True,
            }
        a_rows = fitted["experiments"]["A"]["normalized_training_rows"]
        b_rows = fitted["experiments"]["B"]["normalized_training_rows"]
        b23 = [r for r in b_rows if r["season_start"] == "2023-07-01"]

        def identity(r: dict[str, Any]) -> tuple[Any, ...]:
            return r["base_id"], r["start"], r["area_mu"], tuple(r["actual"])

        if sorted(map(identity, a_rows)) != sorted(map(identity, b23)):
            raise ValueError("CONTROLLED_TRAINING_ROWS_DIFFER")
        decomposition = {
            "status": "POST_HOC_TRAINING_SUM_AUDIT_NOT_VALIDATION",
            "same_2023_rows_fold_A": _global_ratio(a_rows),
            "same_2023_rows_fold_B": _global_ratio(b23),
            "both_seasons_fold_B": _global_ratio(b_rows),
            "warning": "Fold B includes the later season; no Fold B validation on 2024-2025.",
        }
    return cast(
        dict[str, Any],
        serial(
            {
                "experiments": experiments,
                "global_ratio_decomposition": decomposition,
                "two_season_bases": new["two_season_identity_intersection"],
                "training_identity_sets": new["training_identity_sets"],
                "physical_basis_equivalence": "NOT_PROVEN",
                "historical_area_known_at": "NOT_PROVEN",
            }
        ),
    )


def _empty() -> dict[str, Any]:
    return {
        "actual_kg": Decimal(0),
        "day_occurrences": 0,
        "models": {
            m: {
                "predicted_kg": Decimal(0),
                "absolute_error_kg": Decimal(0),
                "overprediction_error_kg": Decimal(0),
                "underprediction_error_kg": Decimal(0),
            }
            for m in METHODS
        },
    }


def _add(acc: dict[str, Any], actual: Decimal, pp: dict[str, Decimal], weight: int) -> None:
    acc["actual_kg"] += weight * actual
    acc["day_occurrences"] += weight
    for model, p in pp.items():
        a = acc["models"][model]
        a["predicted_kg"] += weight * p
        a["absolute_error_kg"] += weight * abs(p - actual)
        a["overprediction_error_kg"] += weight * max(p - actual, Decimal(0))
        a["underprediction_error_kg"] += weight * max(actual - p, Decimal(0))


def _finish(acc: dict[str, Any]) -> dict[str, Any]:
    for v in acc["models"].values():
        v["signed_bias_kg"] = v["predicted_kg"] - acc["actual_kg"]
        v["WAPE"] = v["absolute_error_kg"] / acc["actual_kg"] if acc["actual_kg"] else None
    return acc


def _equal_wape(per_base: dict[str, Any], window: str) -> dict[str, Any]:
    out = {}
    for model in METHODS:
        values, missing = [], []
        for bid, r in per_base.items():
            v = r["groups"][window][model]["metrics"]["DAILY_WAPE"]["candidate"]["value"]
            if v is None:
                missing.append({"base_id": bid, "reason": "ZERO_ACTUAL_DENOMINATOR"})
            else:
                values.append(Decimal(v))
        out[model] = {
            "base_equal_WAPE": sum(values, Decimal(0)) / len(values) if values else None,
            "computed_base_count": len(values),
            "not_computable": missing,
        }
    return out


def analyze(
    old: dict[str, Any],
    new: dict[str, Any],
    labels: dict[str, Any],
    comparison: dict[str, Any],
    factors: dict[str, Any],
) -> dict[str, Any]:
    """S1 repeated-window accounting AND separate non-overlapping calendar accounting."""
    with localcontext(Context(prec=50)):
        return _analyze(old, new, labels, comparison, factors)


def _analyze(
    old: dict[str, Any],
    new: dict[str, Any],
    labels: dict[str, Any],
    comparison: dict[str, Any],
    factors: dict[str, Any],
) -> dict[str, Any]:
    results = {}
    for e in ("A", "B"):
        ex = old["experiments"][e]
        scored = comparison["experiments"][e]
        if scored["comparison_status"] != "COMPLETE_FIVE_MODEL_COMMON_COHORT":
            raise ValueError("INCOMPLETE_COMPARISON_NO_DIAGNOSTIC_WINNER")
        curves = {
            m: {
                b: {date.fromisoformat(r["date"]): Decimal(r["kg"]) for r in rr}
                for b, rr in cc.items()
            }
            for m, cc in ex["curves"].items()
        }
        curves[stable.METHOD] = {
            b: {date.fromisoformat(r["date"]): Decimal(r["kg"]) for r in rr}
            for b, rr in new["experiments"][e]["curves"].items()
        }
        actual = {b: {r.day: r.kg for r in rr} for b, rr in labels[e].items()}
        weights: dict[str, dict[str, Counter[date]]] = {
            w: defaultdict(Counter) for w in ("H7_PREFIX", "H15_LOCAL")
        }
        for m in ex["members"]:
            start, window_days = (
                date.fromisoformat(m["target_start"]),
                7 if m["window"] == "H7_PREFIX" else 15,
            )
            weights[m["window"]][m["base_id"]].update(
                start + timedelta(days=i) for i in range(window_days)
            )
        unique: dict[str, Any] = {}
        monthly: dict[str, Any] = {}
        bins: dict[int, Any] = {}
        start = date.fromisoformat(new["experiments"][e]["fitted"]["evaluation_start"])
        for bid in sorted({m["base_id"] for m in ex["members"]}):
            unique_dates = sorted(set(weights["H7_PREFIX"][bid]) | set(weights["H15_LOCAL"][bid]))
            acc = _empty()
            for day in unique_dates:
                aa = actual[bid][day]
                pp = {m: cc[bid][day] for m, cc in curves.items()}
                _add(acc, aa, pp, 1)
                _add(monthly.setdefault(str(day)[:7], _empty()), aa, pp, 1)
                key = (day - start).days // 7
                _add(bins.setdefault(key, _empty()), aa, pp, 1)
            unique[bid] = {
                "base_id": bid,
                "season_start": str(start),
                "seen_in_original_fit": bid in ex["training_bases"],
                "training": factors["experiments"][e]["base_factors"].get(bid),
                "consensus": new["experiments"][e]["fitted"]["base_records"][bid],
                **_finish(acc),
            }
        by_window = {}
        for window, bases in weights.items():
            per_base: dict[str, Any] = {}
            aggregate = _empty()
            by_month: dict[str, Any] = {}
            by_bin: dict[int, Any] = {}
            transitions: dict[str, dict[str, Any]] = {
                k: {
                    "improved_error_kg": Decimal(0),
                    "degraded_error_kg": Decimal(0),
                    "day_occurrences": 0,
                }
                for k in ("BASELINE_OVER", "BASELINE_UNDER", "BASELINE_EXACT")
            }
            for bid, date_weights in sorted(bases.items()):
                acc = _empty()
                for day, n in sorted(date_weights.items()):
                    aa, pp = actual[bid][day], {m: cc[bid][day] for m, cc in curves.items()}
                    _add(acc, aa, pp, n)
                    _add(aggregate, aa, pp, n)
                    _add(by_month.setdefault(str(day)[:7], _empty()), aa, pp, n)
                    _add(by_bin.setdefault((day - start).days // 7, _empty()), aa, pp, n)
                    kind = (
                        "BASELINE_OVER"
                        if pp["baseline"] > aa
                        else "BASELINE_UNDER"
                        if pp["baseline"] < aa
                        else "BASELINE_EXACT"
                    )
                    delta = n * (abs(pp["VOLUME_CALIBRATION_V1"] - aa) - abs(pp["baseline"] - aa))
                    transitions[kind]["improved_error_kg"] += max(-delta, Decimal(0))
                    transitions[kind]["degraded_error_kg"] += max(delta, Decimal(0))
                    transitions[kind]["day_occurrences"] += n
                per_base[bid] = _finish(acc)
            aggregate = _finish(aggregate)
            denominator = aggregate["actual_kg"]
            contributions = {}
            for bid, acc in per_base.items():
                base_error = acc["models"]["baseline"]["absolute_error_kg"]
                contributions[bid] = {
                    "actual_kg": acc["actual_kg"],
                    "actual_weight": acc["actual_kg"] / denominator if denominator else None,
                    "models": {
                        m: {
                            "predicted_kg": v["predicted_kg"],
                            "absolute_error_kg": v["absolute_error_kg"],
                            "error_change_vs_baseline_kg": v["absolute_error_kg"] - base_error,
                            "WAPE_contribution_change_pp": (v["absolute_error_kg"] - base_error)
                            * 100
                            / denominator
                            if denominator
                            else None,
                        }
                        for m, v in acc["models"].items()
                    },
                }
            for m in METHODS:
                official = scored["groups"][window][m]["metrics"]
                if aggregate["models"][m]["absolute_error_kg"] != Decimal(
                    official["DAILY_MAE"]["candidate"]["numerator"]
                ) or denominator != Decimal(official["DAILY_WAPE"]["candidate"]["denominator"]):
                    raise ValueError("OFFICIAL_NUMERATOR_OR_DENOMINATOR_ACCOUNTING_DRIFT")
            harm = {}
            for m in METHODS:
                deltas = [
                    v["models"][m]["error_change_vs_baseline_kg"] for v in contributions.values()
                ]
                positive, negative = (
                    sum((max(d, Decimal(0)) for d in deltas), Decimal(0)),
                    sum((max(-d, Decimal(0)) for d in deltas), Decimal(0)),
                )
                harm[m] = {
                    "gross_harm_kg": positive,
                    "gross_gain_kg": negative,
                    "gross_harm_pp": positive * 100 / denominator if denominator else None,
                    "gross_gain_pp": negative * 100 / denominator if denominator else None,
                    "improved_bases": sum(d < 0 for d in deltas),
                    "degraded_bases": sum(d > 0 for d in deltas),
                    "tied_bases": sum(d == 0 for d in deltas),
                }
            harm["volume_to_stable_tradeoff"] = {
                "harm_avoided_kg": harm["VOLUME_CALIBRATION_V1"]["gross_harm_kg"]
                - harm[stable.METHOD]["gross_harm_kg"],
                "gain_forgone_kg": harm["VOLUME_CALIBRATION_V1"]["gross_gain_kg"]
                - harm[stable.METHOD]["gross_gain_kg"],
            }
            by_window[window] = {
                "aggregate": aggregate,
                "base_equal_WAPE": _equal_wape(scored["per_base"], window),
                "per_base": per_base,
                "base_contributions": contributions,
                "by_month": {k: _finish(v) for k, v in sorted(by_month.items())},
                "by_season_7day_bin": {k: _finish(v) for k, v in sorted(by_bin.items())},
                "volume_change_by_baseline_direction": transitions,
                "observed_harm_gain": harm,
            }
        results[e] = {
            "unique_base_days": unique,
            "unique_months": {k: _finish(v) for k, v in sorted(monthly.items())},
            "unique_7day_bins": {k: _finish(v) for k, v in sorted(bins.items())},
            "official_repeated_window_accounting": by_window,
            "fallback_base_count": sum(
                v["consensus"]["mode"] == "BASELINE_FALLBACK" for v in unique.values()
            ),
            "candidate_count": len(ex["members"]),
            "evaluation_base_count": len(unique),
        }
    common = sorted(set(results["A"]["unique_base_days"]) & set(results["B"]["unique_base_days"]))
    membership_audit = {}
    for window, audit in results["B"]["official_repeated_window_accounting"].items():
        groups = {}
        for name, include in (("COMMON_A_B_BASES", True), ("ADDITIONAL_B_BASES", False)):
            selected = {
                bid: r for bid, r in audit["per_base"].items() if (bid in common) == include
            }
            amount = sum((r["actual_kg"] for r in selected.values()), Decimal(0))
            error = {
                m: sum((r["models"][m]["absolute_error_kg"] for r in selected.values()), Decimal(0))
                for m in METHODS
            }
            groups[name] = {
                "base_ids": sorted(selected),
                "actual_kg": amount,
                "actual_weight": amount / audit["aggregate"]["actual_kg"]
                if audit["aggregate"]["actual_kg"]
                else None,
                "WAPE": {m: n / amount if amount else None for m, n in error.items()},
                "absolute_errors": error,
            }
        membership_audit[window] = groups
    return cast(
        dict[str, Any],
        serial(
            {
                "experiments": results,
                "common_evaluation_base_ids": common,
                "B_common_vs_additional_identity_audit": membership_audit,
                "confounders": [
                    "training_data",
                    "reference_profile",
                    "fit_parameters",
                    "evaluation_members",
                    "actual_weights",
                    "physical_basis",
                ],
                "causal_season_effect_identified": False,
                "generalization_established": False,
                "observed_harm_is_not_future_risk_probability": True,
                "research_status": "EXPLORATORY",
            }
        ),
    )
