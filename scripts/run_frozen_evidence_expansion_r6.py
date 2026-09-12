"""Append-only qualify -> load/predict -> evaluate; no training entry point.

Current intake reuses the reviewed R3 source aggregation. New XLS intake requires
an explicitly authorized hash and full-export declaration; never auto-discovers data.
"""

import argparse
import json
from collections import defaultdict
from dataclasses import asdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.app.area_yield import confirmed_shape_r3a as shape
from backend.app.area_yield import total_evaluation_r4 as total_metrics
from backend.app.area_yield.censor_r3c import evaluation_status
from backend.app.area_yield.composite_r5 import best, compose
from backend.app.area_yield.composite_r5 import evaluate as composite_metrics
from backend.app.area_yield.data import digest
from backend.app.area_yield.evidence_expansion_r6 import build_qualifications, prior_prediction
from backend.app.area_yield.experiment import file_hash, read_csv, read_json, write_csv, write_json
from backend.app.area_yield.prior_shape_r3b import aggregate, conditional_metrics
from backend.app.area_yield.shape_r3 import is_summary, parse_source, season_calendar
from backend.app.area_yield.total_yield_r4 import Area, emit, positive, predict_total

COMPONENTS = {
    "total": "total-yield-r4-confirmed/model_global_median.json",
    "prior_total": "total-yield-r4-confirmed/model_same_farm_prior.json",
    "shape": "shape-r3a-confirmed/models.json",
}
COMPOSITES = {
    "A1": ("global", "ridge"),
    "A2": ("global", "prior"),
    "B1": ("prior", "ridge"),
    "B2": ("prior", "prior"),
}


def checked(path: Path, expected: str) -> Path:
    if file_hash(path) != expected:
        raise ValueError(f"hash mismatch: {path.name}")
    return path


def seal(out: Path, name: str) -> None:
    write_json(out / name, {p.name: file_hash(p) for p in sorted(out.iterdir()) if p.is_file()})


def load_seal(out: Path, name: str, filename: str) -> Any:
    hashes = read_json(out / name)
    return read_json(checked(out / filename, hashes[filename]))


def intake(root: Path, spec: dict[str, Any]) -> tuple[list[dict[str, str]], dict[str, Any]]:
    if spec["mode"] == "accepted_r3":
        manifest = read_json(root / "shape-r3/artifact_manifest.json")["files"]
        authority = read_json(
            checked(root / "shape-r3/input_manifest.json", manifest["input_manifest.json"])
        )
        source = next(s for s in authority["sources"][:2] if s["sha256"] == spec["source_hash"])
        if (source["date_min"], source["date_max"]) != (
            spec["coverage_start"],
            spec["coverage_end"],
        ):
            raise ValueError("source coverage drift")
        rows = read_csv(
            checked(
                root / "shape-r3/canonical_daily_shape.csv", manifest["canonical_daily_shape.csv"]
            )
        )
        # Empty rows here are old explicitly marked UNKNOWN calendar placeholders,
        # not null observed receipts. R3 source defects/disposition remain immutable.
        return [
            r for r in rows if r["season_id"] == spec["season"] and r["daily_harvest_kg"] != ""
        ], source
    if (
        spec["mode"] != "authorized_xls"
        or not spec.get("authorization_reference")
        or spec.get("legacy_sealed_test") is not False
    ):
        raise ValueError("explicit nonsealed source authorization required")
    parsed = parse_source(Path(spec["path"]), spec["source_hash"])
    profile = parsed["profile"]
    defects = (
        "invalid_date_count",
        "null_quantity_row_count",
        "negative_quantity_row_count",
        "duplicate_row_count",
    )
    if any(profile[k] for k in defects):
        raise ValueError("new source has unresolved null/negative/date/duplicate records")
    if (profile["date_min"], profile["date_max"]) != (spec["coverage_start"], spec["coverage_end"]):
        raise ValueError("coverage must match source")
    daily: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    for r in parsed["rows"]:
        if not r["farm"] or is_summary(r["farm"]) or is_summary(r["subfarm"]):
            raise ValueError("unresolved identity or summary/detail overlap")
        daily[r["farm"], str(r["date"])] += r["quantity"]
    return [
        {"canonical_farm_id": f, "date": d, "daily_harvest_kg": str(v)}
        for (f, d), v in sorted(daily.items())
    ], profile


def qualify(root: Path, out: Path, config_path: Path) -> dict[str, Any]:
    config = read_json(config_path)
    if len(config["sources"]) != 2 or config["train_season"] >= config["validation_season"]:
        raise ValueError("one historical and one later evaluation source required")
    if [s["season"] for s in config["sources"]] != [
        config["train_season"],
        config["validation_season"],
    ]:
        raise ValueError("source season order mismatch")
    areas = {}
    binding_rows = []
    for b in config["bindings"]:
        a = Area(**b)
        a.validate(a.farm)
        if a.farm in areas:
            raise ValueError("duplicate farm area")
        areas[a.farm] = a
    for spec in config["sources"]:
        if not spec.get("authorization_reference") or spec.get("legacy_sealed_test") is not False:
            raise ValueError("explicit source authorization required")
    for folder in config["preserve_directories"]:
        if not (root / folder).is_dir():
            raise ValueError("missing immutable artifact directory")
    loaded = [intake(root, s) for s in config["sources"]]
    farms = [{r["canonical_farm_id"] for r in rows} for rows, _ in loaded]
    matched = farms[0] & farms[1]  # exact only, no fuzzy or normalization merge
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    old = {
        str(p.relative_to(root)): file_hash(p)
        for folder in config["preserve_directories"]
        for p in sorted((root / folder).rglob("*"))
        if p.is_file()
    }
    for k, name in COMPONENTS.items():
        checked(root / name, config["component_hashes"][k])
    matrices, all_curves, calendars = [], [], []
    for spec, (rows, _) in zip(config["sources"], loaded, strict=True):
        qualifications, curves, calendar = build_qualifications(
            rows,
            spec["season"],
            spec["source_hash"],
            date.fromisoformat(spec["coverage_start"]),
            date.fromisoformat(spec["coverage_end"]),
            spec["complete_export"] is True,
            spec["ledger_zero_semantics_authorized"] is True,
            matched,
            areas,
        )
        matrices.append({r.canonical_farm: asdict(r) for r in qualifications})
        all_curves.append(curves)
        calendars.append(calendar)
        write_csv(out / f"source_active_calendar_{spec['season']}.csv", calendar)
    train, validation = matrices
    paired = sorted(
        f for f in matched if train[f]["shape_evaluable"] and validation[f]["shape_evaluable"]
    )
    total = [f for f in paired if f in areas]
    missing = []
    # All farms retained, including non-pairs and area-only blockers.
    for farm in sorted(farms[0] | farms[1]):
        binding = areas.get(farm)
        binding_rows.append(
            {
                "canonical_farm": farm,
                "productive_area_mu": binding.value if binding else "",
                "area_basis": binding.basis if binding else "MISSING",
                "area_bound": binding is not None,
            }
        )
        for table in matrices:
            if farm in table:
                q = table[farm]
                for reason in q["exclusion_reasons"]:
                    missing.append(
                        {
                            "farm": farm,
                            "season": q["season"],
                            "reason": reason,
                            "unknown_dates": ";".join(q["active_span_global_unknown_days"]),
                        }
                    )
    write_json(out / "source_manifest.json", {"sources": [s for _, s in loaded], "config": config})
    write_json(
        out / "qualification.json",
        {"train": train, "validation": validation, "paired": paired, "total": total},
    )
    write_csv(out / "qualification_matrix.csv", [q for m in matrices for q in m.values()])
    write_csv(out / "area_binding_status.csv", binding_rows)
    for name, fs in (("eligible_total_farms", total), ("eligible_shape_farms", paired)):
        write_csv(
            out / f"{name}.csv",
            [{"farm": f, "status": "ELIGIBLE"} for f in fs]
            or [{"farm": "", "status": "NONE_ELIGIBLE"}],
        )
    write_csv(
        out / "missing_evidence.csv",
        missing or [{"farm": "", "season": "", "reason": "NONE", "unknown_dates": ""}],
    )
    write_json(out / "history.json", {f: all_curves[0][f] for f in paired})
    write_json(out / "validation_labels.json", {f: all_curves[1][f] for f in paired})
    write_json(out / "old_artifact_hashes.json", old)
    write_json(
        out / "implementation_hashes.json",
        {
            p: file_hash(Path(p))
            for p in (
                "scripts/run_frozen_evidence_expansion_r6.py",
                "backend/app/area_yield/evidence_expansion_r6.py",
                "backend/app/area_yield/composite_r5.py",
                "backend/app/area_yield/confirmed_shape_r3a.py",
                "backend/app/area_yield/total_yield_r4.py",
            )
        },
    )
    summary = {
        "total_farms": total,
        "shape_paired_farms": paired,
        "huaxing_total_unlock_status": "READY" if "保山华兴农场" in total else "AREA_REQUIRED",
        "model_fit_count": 0,
        "new_source_supplied": any(s["mode"] != "accepted_r3" for s in config["sources"]),
    }
    write_json(out / "qualification_summary.json", summary)
    seal(out, "qualification_freeze.json")
    return summary


def predict(root: Path, out: Path, config_path: Path) -> dict[str, Any]:
    # Intentionally never opens validation_labels, raw source, or old label hashes.
    config = load_seal(out, "qualification_freeze.json", "source_manifest.json")["config"]
    if read_json(config_path) != config:
        raise ValueError("config drift")
    q = load_seal(out, "qualification_freeze.json", "qualification.json")
    for p, h in load_seal(out, "qualification_freeze.json", "implementation_hashes.json").items():
        checked(Path(p), h)
    history = load_seal(out, "qualification_freeze.json", "history.json")
    if not q["paired"]:
        raise ValueError("no qualified pairs; prediction not executed")
    total = read_json(checked(root / COMPONENTS["total"], config["component_hashes"]["total"]))[
        "model"
    ]
    prior_total = read_json(
        checked(root / COMPONENTS["prior_total"], config["component_hashes"]["prior_total"])
    )["model"]
    if total != prior_total:
        raise ValueError("R4 global/prior authority disagreement")
    if digest({k: v for k, v in total.items() if k != "hash"}) != total["hash"]:
        raise ValueError("total model integrity mismatch")
    ridge = read_json(checked(root / COMPONENTS["shape"], config["component_hashes"]["shape"]))[
        "ridge"
    ]
    # Both global coefficients remain unchanged; prior lookup extends only source facts.
    ridge_shares = shape.predict(ridge, config["validation_season"])
    rows = []
    for farm in q["paired"]:
        area = q["train"][farm]["productive_area_mu"]
        shares, prior_yield = prior_prediction(
            history[farm], config["train_season"], config["validation_season"], area
        )
        totals = {}
        if farm in q["total"]:
            if prior_yield is None:
                raise ValueError("qualified total requires area")
            totals["global"] = predict_total(total, area, farm, "global")
            # Same-farm lookup uses the frozen R4 rule; not a new global estimate.
            if farm in total["farm_yields"] and config["train_season"] == total["training_season"]:
                if prior_yield != total["farm_yields"][farm]:
                    raise ValueError("frozen prior source drift")
                totals["prior"] = predict_total(total, area, farm, "prior")
            else:
                totals["prior"] = {
                    "predicted_yield_kg_per_mu": prior_yield,
                    "predicted_season_total_kg": emit(positive(prior_yield) * positive(area)),
                    "model_basis": "FROZEN_PRIOR_LOOKUP_RULE_NEW_AUTHORIZED_HISTORY",
                }
        shapes = {"ridge": ridge_shares, "prior": shares}
        composites = (
            {
                c: {
                    "total": totals[t],
                    "shares": shapes[s],
                    "daily_kg": [
                        str(v) for v in compose(totals[t]["predicted_season_total_kg"], shapes[s])
                    ],
                }
                for c, (t, s) in COMPOSITES.items()
            }
            if totals
            else {}
        )
        rows.append({"farm": farm, "totals": totals, "shapes": shapes, "composites": composites})
    manifest = {
        "predictions": rows,
        "prediction_hash": digest(rows),
        "fit_called": False,
        "validation_labels_read": False,
        "component_hashes": config["component_hashes"],
        "qualification_freeze_hash": file_hash(out / "qualification_freeze.json"),
    }
    write_json(out / "frozen_prediction_manifest.json", manifest)
    write_json(
        out / "prediction_freeze.json",
        {"frozen_prediction_manifest.json": file_hash(out / "frozen_prediction_manifest.json")},
    )
    return {k: v for k, v in manifest.items() if k != "predictions"}


def evaluate(root: Path, out: Path, config_path: Path) -> dict[str, Any]:
    config = load_seal(out, "qualification_freeze.json", "source_manifest.json")["config"]
    if read_json(config_path) != config:
        raise ValueError("config drift")
    q = load_seal(out, "qualification_freeze.json", "qualification.json")
    frozen = load_seal(out, "prediction_freeze.json", "frozen_prediction_manifest.json")
    for p, h in load_seal(out, "qualification_freeze.json", "implementation_hashes.json").items():
        checked(Path(p), h)
    if digest(frozen["predictions"]) != frozen["prediction_hash"] or frozen[
        "qualification_freeze_hash"
    ] != file_hash(out / "qualification_freeze.json"):
        raise ValueError("prediction freeze mismatch")
    write_json(
        out / "evaluation_started.json",
        {
            "retry": False,
            "prediction_file_hash": file_hash(out / "frozen_prediction_manifest.json"),
        },
    )
    labels = load_seal(out, "qualification_freeze.json", "validation_labels.json")
    days = season_calendar(config["validation_season"])
    totals, shapes, composites = [], [], []
    for p in frozen["predictions"]:
        farm, observed = p["farm"], labels[p["farm"]]
        v = q["validation"][farm]
        if [r["date"] for r in observed] != [str(d) for d in days]:
            raise ValueError("validation calendar drift")
        actual_total = sum(
            (Decimal(r["quantity"]) for r in observed if r["quantity"] != ""), Decimal(0)
        )
        for kind, prediction in p["totals"].items():
            area = v["productive_area_mu"]
            actual = {
                "farm": farm,
                "area_mu": area,
                "total_kg": str(actual_total),
                "yield_kg_per_mu": emit(actual_total / positive(area)),
            }
            totals.append({"model": kind, **total_metrics.compare(actual, prediction)})
        for kind, shares in p["shapes"].items():
            m = conditional_metrics(days, shape.labels(observed), shares)
            start, end = (
                date.fromisoformat(v["coverage_start"]),
                date.fromisoformat(v["coverage_end"]),
            )
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
            shapes.append({"farm": farm, "model": kind, **m})
        for c, cp in p["composites"].items():
            m = composite_metrics(
                observed,
                cp["total"]["predicted_season_total_kg"],
                cp["shares"],
                v["coverage_start"],
                v["coverage_end"],
            )
            composites.append({"farm": farm, "composite": c, **m})
    common = [
        f
        for f in q["paired"]
        if all(
            r["peak_evaluation_status"] == "EXACT_COMPUTABLE"
            and r["seven_day_evaluation_status"] == "EXACT_COMPUTABLE"
            for r in shapes
            if r["farm"] == f
        )
    ]
    cmacro = []
    for c in COMPOSITES:
        part = [r for r in composites if r["composite"] == c]
        if part:
            cmacro.append(
                {
                    "composite": c,
                    **{
                        k: emit(sum((Decimal(str(r[k])) for r in part), Decimal(0)) / len(part))
                        if all(r[k] is not None for r in part)
                        else None
                        for k in (
                            "total_rel_error",
                            "daily_wape",
                            "peak_date_error_days",
                            "seven_day_shift_days",
                        )
                    },
                }
            )
    farm_best = {f: best([r for r in composites if r["farm"] == f]) for f in q["total"]}
    result = {
        "total_farm_count": len(q["total"]),
        "common_exact_computable_farms": common,
        "total_macro": {
            k: total_metrics.aggregate([r for r in totals if r["model"] == k])
            for k in ("global", "prior")
        }
        if totals
        else {},
        "shape_common_macro": {
            k: aggregate([r for r in shapes if r["farm"] in common and r["model"] == k])
            for k in ("ridge", "prior")
        },
        "total_per_farm": totals,
        "shape_per_farm": shapes,
        "composites": composites,
        "composite_macro": cmacro,
        "farm_best": farm_best,
        "macro_best": best(cmacro) if cmacro else "NO_CLEAR_WINNER",
        "farm_heterogeneity": len(set(farm_best.values())) > 1,
        "total_research_reopen_ready": len(q["total"]) >= 3,
        "shape_research_reopen_ready": len(common) >= 3,
        "model_research_started": False,
        "validation_blindness": "NOT_BLIND",
        "prediction_hash": frozen["prediction_hash"],
    }
    write_json(out / "evaluation_manifest.json", result)
    evaluated_q = []
    for m in shapes:
        v = dict(q["validation"][m["farm"]])
        v.update(
            model=m["model"],
            peak_evaluation_status=m["peak_evaluation_status"],
            seven_day_evaluation_status=m["seven_day_evaluation_status"],
        )
        evaluated_q.append(v)
    write_json(out / "evaluated_qualification.json", evaluated_q)
    old = load_seal(out, "qualification_freeze.json", "old_artifact_hashes.json")
    for name, h in old.items():
        checked(root / name, h)
    seal(out, "artifact_manifest.json")
    return {
        k: v
        for k, v in result.items()
        if k not in ("total_per_farm", "shape_per_farm", "composites")
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("qualify", "predict", "evaluate"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            {"qualify": qualify, "predict": predict, "evaluate": evaluate}[args.phase](
                args.root, args.output, args.config
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
