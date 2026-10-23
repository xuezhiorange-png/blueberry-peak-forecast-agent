"""Owner's bounded S5 predict -> independent verify -> diagnose/score workflow."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Context, Decimal, localcontext
from pathlib import Path
from typing import Any, cast

from backend.app.forecast_quality.operational_peak import _daily_row, load_frozen_reference_profile
from backend.research import v019_accuracy_models as models
from backend.research import v019_accuracy_study as study
from backend.research import v019_owner_replay as owner
from backend.research import v019_real_training as training
from backend.research import v019_real_training_cli as s4
from backend.research import v019_research_execution as engine
from backend.research import v019_stability as stable
from backend.research import v019_stability_diagnostics as diagnostics
from backend.research import v019_stability_report as report
from backend.research.v019_daily_curve import DailyKg, canonical_bytes
from backend.research.v019_synthetic_validation import digest

TASK = "V0_19_S5_CROSS_SEASON_STABILITY_R1"
S4_RUN = "v0-19-s4-real-training-final-shPL7z"
S4_CODE_SHA = "cc281c0650b2fb676ad3f3cb081a3affb4ce3b28"
PINS = {
    "a/training-manifest.json": "ea3e3fa270c1de750473dca0934cc744efea3bb5dc9d132c06a06a02b904c98b",
    "a/fitted-models.json": "98859e98d0a012376f162e1b8cdf4ddff3e4fae03b75b0f9605a19fb0bc3e497",
    "a/predictions.json": "a1f06c48d102e1838ef044e1820de18a10d92b63eac73af7eb2948b84801af8c",
    "verification/verification.json": (
        "187c08c7a1577a05f06d9ef5f7768c53bd9f86ccd0467fa3a3f24ff0f9e9a26c"
    ),
    "b/comparison.json": "56d15f87b0311e2f20117882f6d649ff02e6f3340451099ed7e60bc0e22640fe",
    "b/report.md": "e25319cd024b6670eba4971a41cdc7842d86f8ddc7cebf27f2fa58019d4ab5ba",
    "b/report.html": "e3277369793ed3294d7da4bdb66ea69cf907a8fb3e0a855ec06ffcc8c8aaf28c",
}


def code_identity() -> str:
    return digest(
        {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (
                Path(__file__),
                Path(stable.__file__),
                Path(diagnostics.__file__),
                Path(report.__file__),
            )
        }
    )


def historical_s4_source_identity() -> str:
    """Old predictions bind old Git bytes, never a future mutable worktree."""
    names = (
        "v019_real_training_cli.py",
        "v019_real_training.py",
        "v019_accuracy_models.py",
        "v019_accuracy_study.py",
    )
    try:
        return digest(
            {
                n: hashlib.sha256(
                    subprocess.check_output(
                        ["git", "show", f"{S4_CODE_SHA}:backend/research/{n}"],
                        stderr=subprocess.DEVNULL,
                    )
                ).hexdigest()
                for n in names
            }
        )
    except subprocess.CalledProcessError as exc:
        raise ValueError("S4_HISTORICAL_SOURCE_UNAVAILABLE") from exc


def load_old(root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """No evaluation report access in this function."""
    values = [
        json.loads(owner.read_bytes(root / S4_RUN / n, PINS[n]))
        for n in ("a/training-manifest.json", "a/fitted-models.json", "a/predictions.json")
    ]
    old_source = historical_s4_source_identity()
    for value in values:
        s4.unseal(value)
        if value["payload"]["code_identity"] != old_source:
            raise ValueError("FROZEN_S4_IMPLEMENTATION_CHANGED")
    t, f, p = values
    receipt = json.loads(
        owner.read_bytes(
            root / S4_RUN / "verification/verification.json", PINS["verification/verification.json"]
        )
    )
    if (
        not receipt["verified"]
        or receipt["prediction_sha256"] != p["sha256"]
        or receipt["code_identity"] != p["payload"]["code_identity"]
        or p["payload"]["training_manifest_sha256"] != t["sha256"]
        or p["payload"]["fitted_models_sha256"] != f["sha256"]
    ):
        raise ValueError("FROZEN_S4_LINK_OR_VERIFICATION")
    return t, f, p


def season_summaries(
    bundle: dict[str, Any], fitted: dict[str, Any], experiment: str
) -> tuple[dict[str, Any], ...]:
    """Select legal seasons BEFORE computing any candidate factor."""
    with localcontext(Context(prec=50)):
        return _season_summaries(bundle, fitted, experiment)


def _season_summaries(
    bundle: dict[str, Any], fitted: dict[str, Any], experiment: str
) -> tuple[dict[str, Any], ...]:
    profile = bundle["profiles"][experiment]
    reference = load_frozen_reference_profile(profile)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in bundle["admission"]["daily"]:
        if r["season"] in fitted["training_seasons"]:
            grouped[r["base_id"], r["season"]].append(r)
    summaries = []
    for (bid, season), rr in sorted(grouped.items()):
        rr.sort(key=lambda r: r["date"])
        if len({(r["area_mu"], r["members_sha256"], r["raw_source_sha256"]) for r in rr}) != 1:
            raise ValueError("TRAINING_MEMBER_AREA_OR_SOURCE_CHANGED")
        start, area = date(int(season[:4]), 7, 1), Decimal(rr[0]["area_mu"])
        actual = tuple(DailyKg(date.fromisoformat(r["date"]), Decimal(r["kg"])) for r in rr)
        baseline = tuple(
            DailyKg(r.day, _daily_row(r.day, start, area, reference).predicted_kg) for r in actual
        )
        summaries.append(
            stable.summarize_season(
                bid,
                season,
                area,
                actual,
                baseline,
                source_sha256=rr[0]["raw_source_sha256"],
                members_sha256=rr[0]["members_sha256"],
                profile_sha256=training.PINS[f"{training.PROFILE_DIR}/reference-{experiment}.json"],
            )
        )
    return tuple(summaries)


def predict_run(root: Path) -> dict[str, Any]:
    t, f, p = load_old(root)
    bundle = training.load_training(root)
    if bundle["admission"] != t["payload"]["admission"]:
        raise ValueError("S4_TRAINING_ADMISSION_DRIFT")
    sets = {
        season: {
            r["base_id"]
            for r in bundle["admission"]["inventory"]
            if r["season"] == season and r["status"] == "ADMIT"
        }
        for season in stable.SEASONS
    }
    experiments = {}
    for e in ("A", "B"):
        previous = p["payload"]["experiments"][e]
        old_fit = f["payload"]["experiments"][e]
        for v in (old_fit, old_fit["fitted"]):
            if digest({k: x for k, x in v.items() if k != "sha256"}) != v["sha256"]:
                raise ValueError("S4_FIT_SEAL")
        summaries = season_summaries(bundle, old_fit, e)
        bases = tuple(sorted(previous["curves"]["baseline"]))
        start = date.fromisoformat(old_fit["fitted"]["evaluation_start"])
        fitted = stable.fit_consensus(
            summaries,
            old_fit["fitted"],
            evaluation_start=start,
            profile_sha256=training.PINS[f"{training.PROFILE_DIR}/reference-{e}.json"],
            base_ids=bases,
        )
        curves, failures = {}, []
        for bid in bases:
            try:
                rows = engine.curve_rows(previous["curves"]["baseline"][bid])
                curves[bid] = engine._serialize(stable.predict(fitted, bid, start, rows))
            except (ValueError, ArithmeticError) as exc:
                failures.append({"base_id": bid, "reason": str(exc)})
        inventory = []
        for member in previous["members"]:
            try:
                rr = models.window(
                    engine.curve_rows(curves.get(member["base_id"], [])),
                    date.fromisoformat(member["target_start"]),
                    7 if member["window"] == "H7_PREFIX" else 15,
                )
                record = {"status": "COMPLETED", "window_sha256": digest(engine._serialize(rr))}
            except ValueError as exc:
                record = {"status": "FAILED", "reason": str(exc)}
            inventory.append({"candidate_id": member["candidate_id"], **record})
        experiments[e] = {
            "fitted": fitted,
            "curves": curves,
            "members": previous["members"],
            "members_sha256": digest(previous["members"]),
            "inventory": inventory,
            "failures": failures,
            "original_fit_sha256": old_fit["sha256"],
            "training_bases": previous["training_bases"],
        }
    if len(sets[stable.SEASONS[0]]) != 15 or len(sets[stable.SEASONS[1]]) != 22:
        raise ValueError("TRAINING_IDENTITY_COUNTS_CHANGED")
    return s4.seal(
        {
            "task_id": TASK,
            "method_config": stable.CONFIG,
            "code_identity": code_identity(),
            "frozen_s4_a_files": {k: v for k, v in PINS.items() if not k.startswith("b/")},
            "training_input_pins": training.PINS,
            "historical_s4_code_sha": S4_CODE_SHA,
            "two_season_identity_intersection": sorted(
                sets[stable.SEASONS[0]] & sets[stable.SEASONS[1]]
            ),
            "training_identity_sets": {k: sorted(v) for k, v in sets.items()},
            "experiments": experiments,
            "labels_2025_2026_read": False,
            "research_status": "EXPLORATORY",
            "strict_pit": False,
            "production_eligible": False,
        }
    )


def load_new(path: Path) -> dict[str, Any]:
    manifest = json.loads((path / "manifest.json").read_bytes())
    p = json.loads(
        owner.read_bytes(
            path / "stability-predictions.json",
            manifest["file_sha256"]["stability-predictions.json"],
        )
    )
    s4.unseal(p)
    if p["payload"]["code_identity"] != code_identity():
        raise ValueError("NEW_CODE_IDENTITY_CHANGED")
    return cast(dict[str, Any], p)


def verify_run(root: Path, path: Path) -> dict[str, Any]:
    p = load_new(path)
    if p != predict_run(root):
        raise ValueError("CONSENSUS_RECOMPUTATION_MISMATCH")
    return {
        "verified": True,
        "prediction_sha256": p["sha256"],
        "code_identity": code_identity(),
        "target_labels_read": False,
    }


def score_run(root: Path, path: Path, verification: Path) -> dict[str, Any]:
    p = load_new(path)
    manifest = json.loads((verification / "manifest.json").read_bytes())
    receipt = json.loads(
        owner.read_bytes(
            verification / "verification.json", manifest["file_sha256"]["verification.json"]
        )
    )
    if (
        not receipt.get("verified")
        or receipt.get("prediction_sha256") != p["sha256"]
        or receipt.get("code_identity") != code_identity()
    ):
        raise ValueError("INDEPENDENT_VERIFICATION_REQUIRED")
    verify_run(root, path)  # Recompute before any target report/label read.
    if any(
        ex["failures"] or any(r["status"] != "COMPLETED" for r in ex["inventory"])
        for ex in p["payload"]["experiments"].values()
    ):
        raise ValueError("INCOMPLETE_C0_PREDICTIONS_NO_LABEL_READ")
    t, f, old_p = load_old(root)
    for name in ("b/report.md", "b/report.html"):
        owner.read_bytes(root / S4_RUN / name, PINS[name])
    previous = json.loads(
        owner.read_bytes(root / S4_RUN / "b/comparison.json", PINS["b/comparison.json"])
    )
    actual: dict[str, dict[str, list[DailyKg]]] = {"A": {}, "B": {}}
    for r in t["payload"]["admission"]["daily"]:
        if r["season"] == "2024-2025":
            actual["A"].setdefault(r["base_id"], []).append(
                DailyKg(date.fromisoformat(r["date"]), Decimal(r["kg"]))
            )
    for r in previous["actual_daily"]:
        actual["B"].setdefault(r["base_id"], []).append(
            DailyKg(date.fromisoformat(r["date"]), Decimal(r["kg"]))
        )
    labels = {
        e: {b: tuple(sorted(rr, key=lambda r: r.day)) for b, rr in aa.items()}
        for e, aa in actual.items()
    }
    comparison = diagnostics.five_model_evaluation(
        old_p["payload"],
        p["payload"],
        labels,
        diagnostics.expand(previous),
        {"A": t["payload"]["admission"]["daily_sha256"], "B": study.S3_PINS["b/report.json"]},
    )
    factors = diagnostics.factor_diagnostics(t["payload"], f["payload"], p["payload"])
    analysis = diagnostics.analyze(old_p["payload"], p["payload"], labels, comparison, factors)
    return {
        "comparison": comparison,
        "factors": factors,
        "analysis": analysis,
        "names": old_p["payload"]["base_names"],
        "old": old_p["payload"],
        "new": p["payload"],
        "labels": labels,
        "execution_kind": "REAL_FIXED_SOURCE_OWNER_COMMAND",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("predict", "verify", "score"))
    parser.add_argument("--owner-task", required=True, choices=(TASK,))
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--a", type=Path)
    parser.add_argument("--verification", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if subprocess.check_output(["git", "status", "--porcelain"], text=True).strip():
        raise ValueError("COMMITTED_CLEAN_SOURCE_REQUIRED")
    metadata = {
        "task_id": TASK,
        "mode": "OWNER_CONTROLLED_RETROSPECTIVE",
        "actual_execution_time": datetime.now(UTC).isoformat(),
        "pid": os.getpid(),
        "code_git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "code_identity": code_identity(),
        "command": sys.argv,
        "authorization_source": "DIRECT_OWNER_TASK_CURRENT_SCOPE",
        "production_eligible": False,
    }
    if args.phase == "predict":
        files = {"stability-predictions.json": canonical_bytes(predict_run(args.artifact_root))}
    elif args.phase == "verify":
        if args.a is None:
            parser.error("--a required")
        files = {"verification.json": canonical_bytes(verify_run(args.artifact_root, args.a))}
    else:
        if args.a is None or args.verification is None:
            parser.error("--a and --verification required")
        files = report.report_files(score_run(args.artifact_root, args.a, args.verification))
    metadata["completed_at"] = datetime.now(UTC).isoformat()
    owner.write_bundle(args.output, files, metadata)
    print(json.dumps({"phase": args.phase, "output": str(args.output), "files": list(files)}))


if __name__ == "__main__":
    main()
