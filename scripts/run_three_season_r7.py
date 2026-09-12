"""R7 rolling past-data refit with R6 qualification and sealed phase boundaries."""

import argparse
from dataclasses import asdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.app.area_yield import confirmed_shape_r3a as shape
from backend.app.area_yield import total_evaluation_r4 as tm
from backend.app.area_yield import total_yield_r4 as total
from backend.app.area_yield.censor_r3c import evaluation_status
from backend.app.area_yield.composite_r5 import best, compose
from backend.app.area_yield.composite_r5 import evaluate as composite_metrics
from backend.app.area_yield.data import digest
from backend.app.area_yield.evidence_expansion_r6 import build_qualifications, prior_prediction
from backend.app.area_yield.experiment import file_hash, read_json, write_csv, write_json
from backend.app.area_yield.prior_shape_r3b import aggregate, conditional_metrics
from backend.app.area_yield.rolling_comparison_r7 import compare_origins, origin_one_parity
from backend.app.area_yield.shape_r3 import parse_source, season_calendar
from scripts.run_frozen_evidence_expansion_r6 import COMPOSITES, checked, intake, load_seal, seal

TRAIN = "2024-2025"
TARGET = "2025-2026"


def code_hashes() -> dict[str, str]:
    paths = sorted(Path("backend/app/area_yield").glob("*.py")) + [
        Path("scripts/run_frozen_evidence_expansion_r6.py"),
        Path(__file__),
    ]
    return {str(p): file_hash(p) for p in paths}


def qualify(root: Path, out: Path, config_path: Path, source: Path) -> dict[str, Any]:
    config = read_json(config_path)
    old_config = read_json(Path("configs/frozen_evidence_expansion_r6.json"))
    spec = {**config["source"], "path": str(source)}
    observed, profile = intake(root, spec)
    raw = parse_source(source, spec["source_hash"])
    profile.update(
        original_filename="原果入库汇总表.xls",
        farm_labels=sorted({r["farm"] for r in raw["rows"]}),
        subfarm_labels=sorted({r["subfarm"] for r in raw["rows"]}),
        variety_labels=sorted({r["variety"] for r in raw["rows"]}),
        byte_size=source.stat().st_size,
    )
    history, previous_profile = intake(root, old_config["sources"][1])
    # Existing explicit user identity authority, not a new fuzzy-name decision.
    alias = {"建水南庄农场": "建水南庄基地"}
    raw_farms = {r["canonical_farm_id"] for r in observed}
    if any(a in raw_farms and b in raw_farms for a, b in alias.items()):
        raise ValueError("both alias labels present; duplicate-scope review required")
    observed = [
        {**r, "canonical_farm_id": alias.get(r["canonical_farm_id"], r["canonical_farm_id"])}
        for r in observed
    ]
    areas = {b["farm"]: total.Area(**b) for b in old_config["bindings"]}
    farms = {r["canonical_farm_id"] for r in observed}
    previous_farms = {r["canonical_farm_id"] for r in history}
    matched = farms & previous_farms
    # Global models consume ALL qualified past farms, independent of target labels.
    tq, tc, _ = build_qualifications(
        history,
        TRAIN,
        previous_profile["sha256"],
        date.fromisoformat(previous_profile["date_min"]),
        date.fromisoformat(previous_profile["date_max"]),
        True,
        True,
        previous_farms,
        areas,
    )
    vq, vc, calendar = build_qualifications(
        observed,
        TARGET,
        profile["sha256"],
        date.fromisoformat(profile["date_min"]),
        date.fromisoformat(profile["date_max"]),
        spec["complete_export"],
        spec["ledger_zero_semantics_authorized"],
        matched,
        areas,
    )
    train, validation = [{q.canonical_farm: asdict(q) for q in qs} for qs in (tq, vq)]
    training_farms = sorted(f for f in train if train[f]["shape_evaluable"])
    prediction_farms = sorted(matched & set(training_farms))
    strict = [f for f in prediction_farms if validation[f]["shape_evaluable"]]
    total_farms = [f for f in strict if validation[f]["total_evaluable"]]
    out.mkdir(parents=True, mode=0o700, exist_ok=False)
    preserved = old_config["preserve_directories"] + ["evidence-expansion-r6"]
    old = {
        str(p.relative_to(root)): file_hash(p)
        for folder in preserved
        for p in sorted((root / folder).rglob("*"))
        if p.is_file()
    }
    if any(not (root / folder).is_dir() for folder in preserved):
        raise ValueError("missing immutable evidence")
    reference = read_json(root / "evidence-expansion-r6/evaluation_manifest.json")
    r5 = read_json(root / "end-to-end-r5/composite_metrics.json")
    for folder, manifest_name, file_name in (
        ("end-to-end-r5", "artifact_manifest.json", "composite_metrics.json"),
        ("evidence-expansion-r6", "artifact_manifest.json", "evaluation_manifest.json"),
    ):
        checked(root / folder / file_name, read_json(root / folder / manifest_name)[file_name])
    if not origin_one_parity(r5, reference):
        raise ValueError("R5_ORIGIN_1_PARITY_FAIL")
    write_json(
        out / "origin_1_reference.json",
        {
            "r6": reference,
            "r5": r5,
            "reference_only_no_refit": True,
            "r5_file_hash": file_hash(root / "end-to-end-r5/composite_metrics.json"),
        },
    )
    write_json(
        out / "source_25_26_manifest.json",
        {
            "config": config,
            "source": spec,
            "original_filename": "原果入库汇总表.xls",
            "converted": False,
        },
    )
    write_json(out / "source_25_26_audit.json", profile)
    write_json(
        out / "canonical_mapping.json",
        {
            "aliases": alias,
            "authority": "USER_R4_CONTINUE_EXPLICIT_NANZHUANG_IDENTITY_EQUIVALENCE",
            "source_labels_unchanged": True,
        },
    )
    write_csv(out / "source_active_calendar_25_26.csv", calendar)
    write_csv(out / "qualification_25_26.csv", list(validation.values()))
    write_json(
        out / "qualification.json",
        {
            "train": train,
            "validation": validation,
            "matched_count": len(matched),
            "training_farms": training_farms,
            "prediction_farms": prediction_farms,
            "strict": strict,
            "total": total_farms,
        },
    )
    write_json(out / "origin_2_training_input.json", {f: tc[f] for f in training_farms})
    write_json(out / "validation_labels.json", {f: vc[f] for f in prediction_farms})
    write_json(out / "old_artifact_hashes.json", old)
    write_json(out / "implementation_hashes.json", code_hashes())
    seal(out, "qualification_freeze.json")
    return {
        "matched": len(matched),
        "training_farms": training_farms,
        "prediction_farms": prediction_farms,
        "strict": strict,
        "total": total_farms,
    }


def verify_code(out: Path) -> None:
    if code_hashes() != load_seal(out, "qualification_freeze.json", "implementation_hashes.json"):
        raise ValueError("execution code drift")


def build(out: Path) -> dict[str, Any]:
    verify_code(out)
    q = load_seal(out, "qualification_freeze.json", "qualification.json")
    curves = load_seal(out, "qualification_freeze.json", "origin_2_training_input.json")
    model = shape.fit_rolling_r7(curves)
    samples = []
    for f, rows in curves.items():
        a = q["train"][f]
        if a["total_evaluable"]:
            samples.append(
                {
                    "farm": f,
                    "season": TRAIN,
                    "total_kg": str(
                        sum(
                            (Decimal(r["quantity"]) for r in rows if r["quantity"] != ""),
                            Decimal(0),
                        )
                    ),
                    "area_mu": a["productive_area_mu"],
                    "completeness": "STRICT_ELIGIBLE",
                }
            )
    total_model = total.fit_rolling_r7(samples) if samples else None
    write_json(out / "origin_2_global_shape_model.json", model)
    write_json(out / "origin_2_total_model.json", total_model)
    manifest = {
        "train": TRAIN,
        "validation": TARGET,
        "shape_farms": sorted(curves),
        "total_samples": samples,
        "training_input_hash": digest(curves),
        "algorithm_frozen": True,
        "fit_on_validation_season": False,
        "hyperparameters": {"alpha": 10, "annual_harmonics": 2, "solver": "svd"},
    }
    write_json(out / "origin_2_training_manifest.json", manifest)
    seal(out, "model_freeze.json")
    return manifest


def predict(out: Path) -> dict[str, Any]:
    """Separate process: no fit and no validation-label file access."""
    verify_code(out)
    q = load_seal(out, "qualification_freeze.json", "qualification.json")
    curves = load_seal(out, "qualification_freeze.json", "origin_2_training_input.json")
    model = load_seal(out, "model_freeze.json", "origin_2_global_shape_model.json")
    total_model = load_seal(out, "model_freeze.json", "origin_2_total_model.json")
    global_shape = shape.predict(model, TARGET)
    predictions = []
    for farm in q["prediction_farms"]:
        area = q["train"][farm]["productive_area_mu"]
        prior, _ = prior_prediction(curves[farm], TRAIN, TARGET, None)
        totals = (
            {
                kind: total.predict_total(total_model, area, farm, kind)
                for kind in ("global", "prior")
            }
            if area and total_model
            else {}
        )
        shares = {"ridge": global_shape, "prior": prior}
        composites = (
            {
                c: {
                    "total": totals[t],
                    "shares": shares[s],
                    "daily_kg": [
                        str(v) for v in compose(totals[t]["predicted_season_total_kg"], shares[s])
                    ],
                }
                for c, (t, s) in COMPOSITES.items()
            }
            if totals
            else {}
        )
        predictions.append(
            {"farm": farm, "shapes": shares, "totals": totals, "composites": composites}
        )
    manifest = {
        "predictions": predictions,
        "prediction_hash": digest(predictions),
        "training_season": TRAIN,
        "target_season": TARGET,
        "qualification_hash": file_hash(out / "qualification_freeze.json"),
        "model_freeze_hash": file_hash(out / "model_freeze.json"),
        "fresh_process_model_load": True,
        "validation_labels_read": False,
    }
    write_json(out / "origin_2_predictions_before_scoring.json", manifest)
    write_json(
        out / "origin_2_prediction_hash.json",
        {
            "prediction_hash": digest(predictions),
            "file_sha256": file_hash(out / "origin_2_predictions_before_scoring.json"),
        },
    )
    seal(out, "prediction_freeze.json")
    return {k: v for k, v in manifest.items() if k != "predictions"}


def shape_score(
    observed: list[dict[str, str]], shares: list[float], q: dict[str, Any]
) -> dict[str, Any]:
    m = conditional_metrics(season_calendar(TARGET), shape.labels(observed), shares)
    start, end = date.fromisoformat(q["coverage_start"]), date.fromisoformat(q["coverage_end"])
    peak, week = (
        date.fromisoformat(m["predicted_peak_date"]),
        date.fromisoformat(m["predicted_7day_start"]),
    )
    m["peak_evaluation_status"] = evaluation_status(
        peak, peak, start, end, m["predicted_peak_has_known_label"]
    )
    m["seven_day_evaluation_status"] = evaluation_status(
        week, week + timedelta(days=6), start, end, m["predicted_7day_has_complete_labels"]
    )
    if m["peak_evaluation_status"] != "EXACT_COMPUTABLE":
        m["peak_date_error_days"] = None
    if m["seven_day_evaluation_status"] != "EXACT_COMPUTABLE":
        m["rolling_7day_window_shift_days"] = None
    m["strict_eligible"] = q["shape_evaluable"]
    m["observed_peak_only_not_full_season_truth"] = not q["shape_evaluable"]
    return m


def evaluate(root: Path, out: Path) -> dict[str, Any]:
    verify_code(out)
    q = load_seal(out, "qualification_freeze.json", "qualification.json")
    frozen = load_seal(out, "prediction_freeze.json", "origin_2_predictions_before_scoring.json")
    if digest(frozen["predictions"]) != frozen["prediction_hash"]:
        raise ValueError("prediction integrity")
    write_json(out / "evaluation_started.json", {"prediction_hash": frozen["prediction_hash"]})
    labels = load_seal(out, "qualification_freeze.json", "validation_labels.json")
    totals, shapes, composites = [], [], []
    for p in frozen["predictions"]:
        f, observed = p["farm"], labels[p["farm"]]
        v = q["validation"][f]
        for kind, shares in p["shapes"].items():
            shapes.append({"farm": f, "model": kind, **shape_score(observed, shares, v)})
        if f in q["total"]:
            actual_total = sum(
                (Decimal(r["quantity"]) for r in observed if r["quantity"] != ""), Decimal(0)
            )
            actual = {
                "farm": f,
                "area_mu": v["productive_area_mu"],
                "total_kg": str(actual_total),
                "yield_kg_per_mu": total.emit(
                    actual_total / total.positive(v["productive_area_mu"])
                ),
            }
            for kind, prediction in p["totals"].items():
                totals.append({"model": kind, **tm.compare(actual, prediction)})
        for c, cp in p["composites"].items():
            m = composite_metrics(
                observed,
                cp["total"]["predicted_season_total_kg"],
                cp["shares"],
                v["coverage_start"],
                v["coverage_end"],
            )
            if f not in q["total"]:
                m["observed_window_total_kg"] = m.pop("actual_total_kg")
                for k in ("total_abs_error_kg", "total_rel_error"):
                    m[k] = None
            composites.append({"farm": f, "composite": c, "strict_eligible": f in q["total"], **m})
    common = [
        f
        for f in q["strict"]
        if all(
            r["peak_evaluation_status"] == "EXACT_COMPUTABLE"
            and r["seven_day_evaluation_status"] == "EXACT_COMPUTABLE"
            for r in shapes
            if r["farm"] == f
        )
    ]
    cmacro = []
    for c in COMPOSITES:
        part = [r for r in composites if r["composite"] == c and r["strict_eligible"]]
        if part:
            cmacro.append(
                {
                    "composite": c,
                    "farm_count": len(part),
                    **{
                        k: total.emit(
                            sum((Decimal(str(r[k])) for r in part), Decimal(0)) / len(part)
                        )
                        if all(r.get(k) is not None for r in part)
                        else None
                        for k in (
                            "total_rel_error",
                            "daily_mae_kg",
                            "daily_wape",
                            "known_support_wape",
                            "peak_date_error_days",
                            "seven_day_shift_days",
                        )
                    },
                }
            )
    total_result = {
        "farm_count": len(q["total"]),
        "per_farm": totals,
        "macro": {
            k: tm.aggregate([r for r in totals if r["model"] == k]) for k in ("global", "prior")
        }
        if totals
        else {},
    }
    shape_result = {
        "matched_farm_count": q["matched_count"],
        "strict_pair_count": len(q["strict"]),
        "common_exact_farms": common,
        "per_farm": shapes,
        "common_macro": {
            k: aggregate([r for r in shapes if r["farm"] in common and r["model"] == k])
            for k in ("ridge", "prior")
        },
        "diagnostic_only_farms": [f for f in q["prediction_farms"] if f not in q["strict"]],
    }
    composite_result = {
        "farm_count": len(q["total"]),
        "per_farm": composites,
        "macro": cmacro,
        "macro_best": best(cmacro) if cmacro else "NO_CLEAR_WINNER",
        "farm_best": {f: best([r for r in composites if r["farm"] == f]) for f in q["total"]},
        "mass_balance_pass": all(r["mass_balance_pass"] for r in composites)
        if composites
        else None,
    }
    write_json(out / "origin_2_total_metrics.json", total_result)
    write_json(out / "origin_2_shape_metrics.json", shape_result)
    write_json(out / "origin_2_composite_metrics.json", composite_result)
    comparison = compare_origins(
        load_seal(out, "qualification_freeze.json", "origin_1_reference.json"),
        total_result,
        shape_result,
        composite_result,
    )
    write_json(out / "three_season_comparison.json", comparison)
    reference = load_seal(out, "qualification_freeze.json", "origin_1_reference.json")
    write_csv(
        out / "three_season_per_farm.csv",
        [
            {
                "origin": origin,
                "farm": r["farm"],
                "composite": r["composite"],
                "total_rel_error": r["total_rel_error"],
                "daily_wape": r["daily_wape"],
                "peak_date_error_days": r["peak_date_error_days"],
                "seven_day_shift_days": r["seven_day_shift_days"],
            }
            for origin, rows in (
                ("2324_2425", reference["r5"]["per_farm"]),
                ("2425_2526", composites),
            )
            for r in rows
        ],
    )
    write_csv(
        out / "origin_2_per_farm.csv",
        [
            {
                "farm": r["farm"],
                "model": r["model"],
                "strict": r["strict_eligible"],
                "peak_status": r["peak_evaluation_status"],
                "peak_error": r["peak_date_error_days"],
                "seven_day_shift": r["rolling_7day_window_shift_days"],
                "known_support_wape": r["known_support_wape"],
            }
            for r in shapes
        ],
    )
    for p, h in load_seal(out, "qualification_freeze.json", "old_artifact_hashes.json").items():
        checked(root / p, h)
    seal(out, "evaluation_freeze.json")
    seal(out, "artifact_manifest.json")
    return {
        "total_count": len(q["total"]),
        "shape_strict": len(q["strict"]),
        "shape_common": len(common),
        "macro_best": composite_result["macro_best"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("qualify", "build", "predict", "evaluate"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("configs/three_season_r7.json"))
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    if args.phase == "qualify":
        if args.source is None:
            parser.error("qualify requires original --source XLS")
        result = qualify(args.root, args.output, args.config, args.source)
    elif args.phase == "build":
        result = build(args.output)
    elif args.phase == "predict":
        result = predict(args.output)
    else:
        result = evaluate(args.root, args.output)
    print(result)


if __name__ == "__main__":
    main()
