"""Bounded Owner S6 features -> fit/predict -> independent verify -> score/report."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from backend.app.area_yield import v015_harvest_state, weather_aware_backtest
from backend.research import v019_origin_evaluation as evaluation
from backend.research import v019_origin_features as features
from backend.research import v019_origin_models as models
from backend.research import v019_origin_reference as reference
from backend.research import v019_origin_report as report
from backend.research import v019_origin_sources as sources
from backend.research import v019_owner_replay as owner
from backend.research import v019_real_training as training
from backend.research import v019_real_training_cli as s4
from backend.research import v019_stability_cli as previous
from backend.research.v019_daily_curve import DailyKg, canonical_bytes
from backend.research.v019_synthetic_validation import digest

TASK = "V0_19_S6_ORIGIN_AWARE_HARVEST_FORECAST_R1"


def code_identity() -> str:
    modules = (
        sys.modules[__name__],
        features,
        models,
        sources,
        reference,
        evaluation,
        report,
        v015_harvest_state,
        weather_aware_backtest,
        training,
        s4,
    )
    return digest(
        {
            Path(str(m.__file__)).name: hashlib.sha256(
                Path(str(m.__file__)).read_bytes()
            ).hexdigest()
            for m in modules
        }
    )


def prepare(root: Path) -> dict[str, bytes]:
    source = sources.load(root)
    projected, labels = sources.materialize(source)
    diag = reference.audit(source["bundle"], source["profile_trace"])
    return {
        "origin-feature-manifest.json": canonical_bytes(
            s4.seal(
                {
                    **projected,
                    "code_identity": code_identity(),
                    "source_kind": "EXACT_FROZEN_REAL_SOURCES",
                    "task_id": TASK,
                }
            )
        ),
        "training-labels.json": canonical_bytes(s4.seal(labels)),
        "reference-profile-diagnostics.json": canonical_bytes(diag),
    }


def read(path: Path, name: str) -> dict[str, Any]:
    m = json.loads((path / "manifest.json").read_bytes())
    return cast(dict[str, Any], json.loads(owner.read_bytes(path / name, m["file_sha256"][name])))


def prepared(path: Path) -> tuple[dict[str, Any], dict[str, Any], str]:
    raw = read(path, "origin-feature-manifest.json")
    p = s4.unseal(raw)
    sources.validate_members(p["members"])
    labels = s4.unseal(read(path, "training-labels.json"))
    if (
        p["code_identity"] != code_identity()
        or p["task_id"] != TASK
        or p["source_kind"] != "EXACT_FROZEN_REAL_SOURCES"
        or p["input_pins"] != training.PINS
        or labels["input_pins"] != training.PINS
    ):
        raise ValueError("SOURCE_PROJECTION_IDENTITY")
    if (
        len(p["members"]["B"]) != 19032
        or len({m["base_id"] for m in p["members"]["B"]}) != 39
        or labels["evaluation_2025_2026_labels_included"] is not False
    ):
        raise ValueError("BOUNDED_SCOPE_OR_LABEL_ISOLATION")
    for row in p["records"].values():
        features.validate(row)
    return p, labels, raw["sha256"]


def calculate(
    p: dict[str, Any], labels: dict[str, Any], source_sha256: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Pure numerical workflow; tests use synthetic inputs, no source-file access."""
    fits = {}
    predictions = {}
    for e, year in [("A", 2024), ("B", 2025)]:
        seasons = ("2023-2024",) if e == "A" else ("2023-2024", "2024-2025")
        fit = models.fit_pair(
            list(p["records"].values()),
            labels["daily"],
            allowed_seasons=seasons,
            evaluation_start=date(year, 7, 1),
        )
        keys = {evaluation.origin_key(m, f"{year}-{year + 1}") for m in p["members"][e]}
        origins = {}
        predictor = models.compile_pair(fit)
        for key in sorted(keys):
            if key not in p["records"]:
                raise ValueError("MISSING_C0_ORIGIN_SNAPSHOT")
            origins[key] = predictor.predict(p["records"][key])
        predictions[e] = {
            "origins": origins,
            "members": p["members"][e],
            "members_sha256": digest(p["members"][e]),
            "training_bases": fit["training_bases"],
            "fit_sha256": fit["sha256"],
        }
        fits[e] = fit
    return s4.seal(
        {
            "experiments": fits,
            "source_projection_sha256": source_sha256,
            "code_identity": code_identity(),
            "config": models.CONFIG,
        }
    ), s4.seal(
        {
            "experiments": predictions,
            "source_projection_sha256": source_sha256,
            "code_identity": code_identity(),
            "config": models.CONFIG,
            "target_2025_label_file_read_by_predictor": False,
            "feature_materializer_previous_full_source_exposure_disclosed": True,
            "strict_pit": False,
        }
    )


def predict(path: Path) -> dict[str, bytes]:
    p, ll, h = prepared(path)
    fit, pred = calculate(p, ll, h)
    return {
        "dynamic-model-fits.json": canonical_bytes(fit),
        "dynamic-predictions.json": canonical_bytes(pred),
    }


def verify(path: Path, predicted: Path) -> dict[str, Any]:
    p, ll, h = prepared(path)
    expected = calculate(p, ll, h)
    actual = read(predicted, "dynamic-model-fits.json"), read(predicted, "dynamic-predictions.json")
    if expected != actual:
        raise ValueError("INDEPENDENT_DYNAMIC_RECOMPUTATION_MISMATCH")
    return {
        "verified": True,
        "fit_sha256": actual[0]["sha256"],
        "prediction_sha256": actual[1]["sha256"],
        "feature_sha256": h,
        "code_identity": code_identity(),
        "target_2025_labels_read": False,
    }


def score(root: Path, path: Path, predicted: Path, verification: Path) -> dict[str, Any]:
    pred = read(predicted, "dynamic-predictions.json")
    fits = read(predicted, "dynamic-model-fits.json")
    receipt = read(verification, "verification.json")
    if (
        not receipt.get("verified")
        or receipt.get("prediction_sha256") != pred["sha256"]
        or receipt.get("fit_sha256") != fits["sha256"]
        or receipt.get("code_identity") != code_identity()
    ):
        raise ValueError("INDEPENDENT_VERIFICATION_REQUIRED")
    verify(path, predicted)  # No target report/label access before this completes.
    p, _, h = prepared(path)
    # Only the already authorized fixed inputs; score never discovers a source.
    bundle = training.load_training(root)
    _, _, old = previous.load_old(root)
    target = json.loads(
        owner.read_bytes(
            root / previous.S4_RUN / "b/comparison.json", previous.PINS["b/comparison.json"]
        )
    )
    actual: dict[str, dict[str, list[DailyKg]]] = {"A": {}, "B": {}}
    for r in bundle["admission"]["daily"]:
        if r["season"] == "2024-2025":
            actual["A"].setdefault(r["base_id"], []).append(
                DailyKg(date.fromisoformat(r["date"]), Decimal(r["kg"]))
            )
    for r in target["actual_daily"]:
        actual["B"].setdefault(r["base_id"], []).append(
            DailyKg(date.fromisoformat(r["date"]), Decimal(r["kg"]))
        )
    result = {}
    for e in ("A", "B"):
        if p["members"][e] != old["payload"]["experiments"][e]["members"]:
            raise ValueError("ORIGINAL_C0_CHANGED")
        aa = {b: tuple(sorted(rr, key=lambda r: r.day)) for b, rr in actual[e].items()}
        static = {
            b: evaluation.curve(rr)
            for b, rr in old["payload"]["experiments"][e]["curves"]["baseline"].items()
        }
        result[e] = evaluation.evaluate(
            pred["payload"]["experiments"][e],
            p["members"][e],
            aa,
            static,
            "2024-2025" if e == "A" else "2025-2026",
        )
    return {
        "comparison": {
            "experiments": result,
            "feature_sha256": h,
            "prediction_sha256": pred["sha256"],
            "code_identity": code_identity(),
            "strict_pit": False,
            "production_accuracy_validated": False,
        },
        "features": p,
        "fits": fits["payload"],
        "predictions": pred["payload"],
        "actual": actual,
        "reference": read(path, "reference-profile-diagnostics.json"),
        "names": old["payload"]["base_names"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("features", "predict", "verify", "score"))
    parser.add_argument("--owner-task", choices=(TASK,), required=True)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--features", type=Path)
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--verification", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    a = parser.parse_args()
    if subprocess.check_output(["git", "status", "--porcelain"], text=True).strip():
        raise ValueError("COMMITTED_CLEAN_CODE_REQUIRED")
    if any(
        os.environ.get(n) != "1"
        for n in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")
    ):
        raise ValueError("FROZEN_SINGLE_THREAD_ENVIRONMENT_REQUIRED")
    meta = {
        "task_id": TASK,
        "phase": a.phase,
        "mode": "OWNER_CONTROLLED_RETROSPECTIVE",
        "authorization_source": "DIRECT_OWNER_CURRENT_TASK",
        "command": sys.argv,
        "pid": os.getpid(),
        "started_at": datetime.now(UTC).isoformat(),
        "code_identity": code_identity(),
        "code_git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "strict_pit": False,
        "production_eligible": False,
    }
    if a.phase == "features":
        if a.artifact_root is None:
            parser.error("--artifact-root required")
        out = prepare(a.artifact_root)
    elif a.phase == "predict":
        if a.features is None or a.artifact_root is not None:
            parser.error("predict requires --features and refuses --artifact-root")
        out = predict(a.features)
    elif a.phase == "verify":
        if a.features is None or a.predictions is None or a.artifact_root is not None:
            parser.error("verify requires --features/--predictions; no source root")
        out = {"verification.json": canonical_bytes(verify(a.features, a.predictions))}
    else:
        if any(x is None for x in (a.artifact_root, a.features, a.predictions, a.verification)):
            parser.error("score requires root/features/predictions/verification")
        out = report.files(score(a.artifact_root, a.features, a.predictions, a.verification))
    meta["completed_at"] = datetime.now(UTC).isoformat()
    owner.write_bundle(a.output, out, meta)
    print(json.dumps({"phase": a.phase, "output": str(a.output), "files": list(out)}))


if __name__ == "__main__":
    main()
