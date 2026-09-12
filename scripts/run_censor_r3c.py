"""Read frozen R3A/R3B facts; no fitting, prediction or model search."""

import argparse
import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from backend.app.area_yield.censor_r3c import evaluation_status
from backend.app.area_yield.experiment import file_hash, read_csv, read_json, write_json
from backend.app.area_yield.prior_shape_r3b import aggregate
from scripts.run_prior_shape_r3b import verify


def run(root: Path, output: Path) -> dict:
    a, b = root / "shape-r3a-confirmed", root / "shape-r3b"
    hashes = {str(p): read_json(p / "artifact_manifest.json") for p in (a, b)}
    for p, manifest in hashes.items():
        verify(Path(p), manifest)
    matrix = read_csv(a / "farm_season_qualification.csv")
    train = {r["farm"]: r for r in matrix if r["season"] == "2023-2024"}
    validation = {
        r["farm"]: r
        for r in matrix
        if r["season"] == "2024-2025" and r["strict_eligible"] == "True"
    }
    calendar = read_csv(a / "source_active_calendar_2023-2024.csv")
    identities = []
    for farm in sorted(validation):
        old = train.get(farm)
        if old is None:
            raise ValueError("new identity requires explicit source investigation")
        unknown = [
            r["date"]
            for r in calendar
            if r["source_active_day"] == "False"
            and old["first_positive_date"] <= r["date"] <= old["last_positive_date"]
        ]
        identities.append(
            {
                "season_23_24_label": farm,
                "season_24_25_label": farm,
                "match_status": "EXACT",
                "match_evidence": "HASH_BOUND_SOURCE_LABEL_EQUALITY",
                "train_strict": old["strict_eligible"] == "True",
                "validation_strict": True,
                "train_exclusion_reason": old["exclusion_reason"],
                "training_active_span_unknown_dates": unknown,
            }
        )
    old_metrics = read_json(b / "metrics.json")
    labels = read_json(a / "validation_labels.json")
    rows = []
    for old in old_metrics["per_farm"]:
        if old["model"] not in {"ridge", "prior"}:
            continue
        row = dict(old)
        coverage = validation[row["farm"]]
        start, end = (
            date.fromisoformat(coverage["file_start"]),
            date.fromisoformat(coverage["file_end"]),
        )
        peak = date.fromisoformat(row["predicted_peak_date"])
        window = date.fromisoformat(row["predicted_7day_start"])
        row["peak_evaluation_status"] = evaluation_status(
            peak, peak, start, end, row["predicted_peak_has_known_label"]
        )
        row["rolling_7day_evaluation_status"] = evaluation_status(
            window,
            window + timedelta(days=6),
            start,
            end,
            row["predicted_7day_has_complete_labels"],
        )
        if row["peak_evaluation_status"] != "EXACT_COMPUTABLE":
            row["peak_date_error_days"] = None
        if row["rolling_7day_evaluation_status"] != "EXACT_COMPUTABLE":
            row["rolling_7day_window_shift_days"] = None
        tail = [
            r for r in labels[row["farm"]] if str(end - timedelta(days=13)) <= r["date"] <= str(end)
        ]
        known_tail = all(r["quantity"] != "" for r in tail) and len(tail) == 14
        sums = (
            [sum((Decimal(r["quantity"]) for r in tail[i : i + 7]), Decimal(0)) for i in (0, 7)]
            if known_tail
            else None
        )
        row.update(
            coverage_end_date=str(end),
            days_beyond_coverage=max(0, (peak - end).days),
            last_observed_positive_date=coverage["last_positive_date"],
            last_14d_observed_trend={
                "method": "LAST_7_SUM_MINUS_PREVIOUS_7_SUM_NO_PEAK_INFERENCE",
                "previous_7_kg": str(sums[0]) if sums else None,
                "last_7_kg": str(sums[1]) if sums else None,
                "difference_kg": str(sums[1] - sums[0]) if sums else None,
            },
            observed_max_date=row["actual_peak_date"],
            true_full_season_peak_proven=False,
        )
        rows.append(row)
    farms = sorted({r["farm"] for r in rows})
    common = [
        f
        for f in farms
        if all(
            r["peak_evaluation_status"] == "EXACT_COMPUTABLE"
            and r["rolling_7day_evaluation_status"] == "EXACT_COMPUTABLE"
            for r in rows
            if r["farm"] == f
        )
    ]
    right = [
        r
        for r in rows
        if "RIGHT_CENSORED" in (r["peak_evaluation_status"], r["rolling_7day_evaluation_status"])
    ]
    macros = {
        k: aggregate([r for r in rows if r["farm"] in common and r["model"] == k])
        for k in ("ridge", "prior")
    }
    result = {
        "result": "EVIDENCE_STILL_INSUFFICIENT",
        "identity_audit": identities,
        "strict_validation_farms": sorted(validation),
        "exact_identity_pairs_within_strict_validation": len(identities),
        "strict_paired_farm_count": len(farms),
        "authorized_alias_pair_count": 0,
        "common_exact_computable_set": common,
        "right_censored_farm_count": len({r["farm"] for r in right}),
        "right_censored_model_predictions": right,
        "common_macro": macros,
        "per_farm": rows,
        "next_evidence_need": "MORE_COMPLETE_CROSS_SEASON_FARM_PAIRS",
        "model_search_stopped": True,
        "model_fit_count": 0,
        "new_prediction_count": 0,
        "source_hashes": hashes,
        "r3b_prediction_hash": old_metrics["prediction_hash"],
    }
    if len(common) >= 3:
        timing = ("peak_date_error_days", "rolling_7day_window_shift_days")
        shape = ("known_support_mae", "known_support_wape")
        if all(macros["prior"][k]["mean"] < macros["ridge"][k]["mean"] for k in timing) and all(
            macros["prior"][k]["mean"] <= macros["ridge"][k]["mean"] for k in shape
        ):
            result["result"] = "SAME_FARM_SIGNAL_SUPPORTED"
            result["next_evidence_need"] = "COORDINATOR_REVIEW"
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    write_json(output / "results.json", result)
    write_json(
        output / "artifact_manifest.json", {"results.json": file_hash(output / "results.json")}
    )
    for p, manifest in hashes.items():
        verify(Path(p), manifest)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.root, args.output), ensure_ascii=False, indent=2))
