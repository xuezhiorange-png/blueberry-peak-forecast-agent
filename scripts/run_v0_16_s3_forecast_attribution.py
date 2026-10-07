"""Offline frozen attribution custody. No labels, fitting, issuance or database."""

from __future__ import annotations

import argparse
import ast
import builtins
import hashlib
import io
import json
import os
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

from backend.app.area_yield.v015_benchmark_custody import FrozenDataset
from backend.app.area_yield.v015_harvest_incremental import HarvestCustody, target_rows
from backend.app.area_yield.v015_research_cohort import canonical, digest
from backend.app.forecast_intelligence import attribution as a

REPOSITORY = Path(__file__).resolve().parents[1]
BASE = "fa3958fa19e01676030f1f1f2d5451d8c9a8754a"
TASK = "V0_16_S3_FORECAST_ATTRIBUTION_R1"
EVIDENCE = "docs/v0-15/evidence/harvest-state-incremental-value-r1"
HISTORICAL_COMMIT = "139ef01733100847a8c44d2f127d05eadd78b96c"
RIDGE_SOURCE = "backend/app/area_yield/weather_aware_backtest.py"
PINS = {
    "model_artifact_hash": a.LEGACY_FILE_HASH,
    "model_config_hash": "1c3d731bd3b56af929ccf0fdd932b14ebb6f7f3b107df8da57f012d89db21173",
    "prediction_hash": "74e1add1e552245b968dca2b0770c97e0ca99abda24545c743162a08e908559b",
    "prediction_seal_hash": "a97f6a6a794e16215a2758bad55f2711c08fe935cbac7d3338c692e948b3a2df",
    "common_rowset_hash": "dbd37e02e19d1fc37942e0accae7d76198bc499d58d66e01104f6833c899445e",
    "target_rowset_hash": "476f4e00e985408c09512dc9bac5c5daa74a253f50bcb605bb48f8e5aadcc188",
    "base10_feature_hash": "90fa6756bf27f57c7effdf47f0f51d474d6379ab1816c0f9f236bf93b6ad725e",
    "harvest_state_feature_hash": (
        "9d81338d2e17108b089f580a575a407387237d007815a1a83d056f1754e4488a"
    ),
}
ORIGINS = 8775
TARGETS = 131625
PREDICTIONS = "exposed-oot-M1-predictions.json"
OUTPUTS = (
    "private-target-attribution.json",
    "private-horizon-attribution.json",
    "feature-summary.json",
    "family-group-summary.json",
    "semantic-group-summary.json",
    "horizon-summary.json",
    "reconstruction-summary.json",
)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@contextmanager
def no_labels() -> Iterator[None]:
    """Also guards transitive frozen feature-reader IO; no label file can open."""
    original_io, original_builtin = io.open, builtins.open

    def guard(original: Any, file: Any, *args: Any, **kwargs: Any) -> Any:
        if isinstance(file, (str, os.PathLike)) and "label_zone" in Path(file).resolve().parts:
            raise ValueError("LABEL_ACCESS_FORBIDDEN")
        return original(file, *args, **kwargs)

    with (
        patch("io.open", lambda f, *x, **k: guard(original_io, f, *x, **k)),
        patch("builtins.open", lambda f, *x, **k: guard(original_builtin, f, *x, **k)),
    ):
        yield


def load(path: Path) -> Any:
    with no_labels():
        return json.loads(path.read_bytes())


def save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("xb") as stream:
        os.chmod(path, 0o600)
        stream.write(canonical(value))


def historical_source() -> dict[str, Any]:
    result = subprocess.run(
        ["git", "show", f"{HISTORICAL_COMMIT}:{RIDGE_SOURCE}"],
        cwd=REPOSITORY,
        capture_output=True,
        check=False,
    )
    if result.returncode or sha(result.stdout) != a.LEGACY_SOURCE_HASH:
        raise ValueError("HISTORICAL_RIDGE_AUTHORITY_UNAVAILABLE")
    tree = ast.parse(result.stdout)
    fit = next(
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "fit_ridge_artifact"
    )
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "RidgeArtifact")
    serializer = next(
        n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "payload_without_hash"
    )
    dicts = [n for n in ast.walk(fit) if isinstance(n, ast.Dict)]
    included = any(
        any(
            isinstance(k, ast.Constant)
            and k.value == "standardization"
            and isinstance(v, ast.Constant)
            and v.value == a.STANDARDIZATION
            for k, v in zip(d.keys, d.values, strict=True)
        )
        for d in dicts
    )
    omitted = all(
        not (isinstance(n, ast.Constant) and n.value == "standardization")
        for n in ast.walk(serializer)
    )
    if not included or not omitted:
        raise ValueError("HISTORICAL_RIDGE_SCHEMA_NOT_PROVEN")
    return {
        "historical_commit": HISTORICAL_COMMIT,
        "source_sha256": sha(result.stdout),
        "schema_proven": True,
    }


def public_authority() -> dict[str, Any]:
    contract = load(REPOSITORY / EVIDENCE / "s5-experiment-contract.json")
    config = load(REPOSITORY / EVIDENCE / "model-config-freeze.json")
    fit = load(REPOSITORY / EVIDENCE / "final-fit-manifest.json")
    seal = load(REPOSITORY / EVIDENCE / "exposed-oot-prediction-seal.json")
    if (
        contract["ridge"]["standardization"] != a.STANDARDIZATION
        or config["ridge"]["standardization"] != a.STANDARDIZATION
        or contract["ridge_source_sha256"] != a.LEGACY_SOURCE_HASH
    ):
        raise ValueError("BLOCKED_STANDARDIZATION_AUTHORITY_CONFLICT")
    if (
        any(
            fit["M1"][k] != PINS[k]
            for k in ("model_artifact_hash", "model_config_hash", "prediction_hash")
        )
        or seal["seal_hash"] != PINS["prediction_seal_hash"]
        or seal["rowset_hash"] != PINS["target_rowset_hash"]
        or contract["common_rowset_hash"] != PINS["common_rowset_hash"]
        or contract["s2_feature_hashes"]["EXPOSED_OOT"] != PINS["base10_feature_hash"]
        or contract["s4_feature_hashes"]["EXPOSED_OOT"] != PINS["harvest_state_feature_hash"]
    ):
        raise ValueError("PUBLIC_AUTHORITY_DRIFT")
    files = [
        f"{EVIDENCE}/{n}.json"
        for n in (
            "s5-experiment-contract",
            "model-config-freeze",
            "final-fit-manifest",
            "exposed-oot-prediction-seal",
            "common-rowset-binding-report",
        )
    ]
    files += [
        "docs/v0-16/v0.16.0-version-plan-and-scope-freeze.md",
        "docs/v0-16/evidence/v0.16.0-version-plan-and-scope-freeze-r1.json",
        "docs/v0-16/v0.16-s1-hierarchical-forecast-reconciliation-r1.md",
        "docs/v0-16/evidence/v0.16-s1-hierarchical-forecast-reconciliation-r1.json",
        "backend/app/forecast_intelligence/uncertainty.py",
        "scripts/run_v0_16_s2_uncertainty_calibration.py",
    ]
    s2 = REPOSITORY / "docs/v0-16/evidence/uncertainty-conformal-calibration-r1"
    files += [str(p.relative_to(REPOSITORY)) for p in sorted(s2.glob("*.json"))]
    s2_policy = load(s2 / "conformal-policy-r1.json")
    if (
        s2_policy["policy_hash"]
        != "f35f2700011f440569c9a0140dc9deb482281d60190e8a601b5a503c79013efd"
    ):
        raise ValueError("S2_AUTHORITY_DRIFT")
    files += [
        "backend/app/forecast_intelligence/attribution.py",
        "scripts/run_v0_16_s3_forecast_attribution.py",
    ]
    return {
        "historical_source": historical_source(),
        "source_evidence_sha256": {f: sha((REPOSITORY / f).read_bytes()) for f in files},
    }


def policy() -> dict[str, Any]:
    return {
        "policy_version": a.POLICY_VERSION,
        "model_id": a.MODEL_ID,
        "model_role": "RETROSPECTIVE_RESEARCH_POINT_FORECAST_NOT_PRODUCTION",
        "source_bindings": PINS,
        "features": list(a.FEATURES),
        "family_grouping": a.FAMILY,
        "semantic_grouping": a.SEMANTIC,
        "grouping_axes_are_independent": True,
        "standardization": a.STANDARDIZATION,
        "numeric_semantics": "MODEL_FAITHFUL_IEEE754_BINARY64_R1",
        "contribution_serialization": ".17g",
        "prediction_serialization": ".12f",
        "reconstruction_tolerance_kg": "0",
        "reconstruction_comparison": "EXACT_SEALED_PREDICTION_STRING_EQUALITY_12DP",
        "nonnegative_clip": True,
        "clip_adjustment_is_feature_contribution": False,
        "serialization_adjustment_is_feature_contribution": False,
        "intercept_is_business_baseline": False,
        "attribution_is_causal_explanation": False,
        "shap_used": False,
        "label_bytes_read": False,
        "source_split": "EXPOSED_OOT",
        "origin_count": ORIGINS,
        "target_row_count": TARGETS,
        "privacy_policy": "PRIVATE_ROWS_PARAMETERS_IDENTITIES_PUBLIC_AGGREGATES_ONLY",
        "legacy_compatibility_rule_id": a.LEGACY_RULE,
        **public_authority(),
    }


def source_paths(s5: Path, dataset: Path, harvest: Path) -> dict[str, Path]:
    return {
        "model": s5 / "models/exposed-oot-M1.json",
        "predictions": s5 / PREDICTIONS,
        "fit": s5 / "exposed-oot-fit-manifest.json",
        "seal": s5 / "exposed-oot-prediction-seal.json",
        "s5_contract": s5 / "contract.json",
        "dataset_manifest": dataset / "manifest.json",
        "base10": dataset / "feature_zone/exposed_oot-base10.json",
        "harvest_manifest": harvest / "manifest.json",
        "common": harvest / "audit/harvest-state-common-rowset.json",
        "harvest": harvest / "feature_zone/harvest-state-v1-exposed-oot.json",
    }


def sources(
    s5: Path, dataset: Path, harvest: Path
) -> tuple[dict[str, Any], list[Any], dict[str, str], dict[str, Any], dict[str, str]]:
    with no_labels():
        paths = source_paths(s5, dataset, harvest)
        hashes = {k: sha(p.read_bytes()) for k, p in paths.items()}
        for key, pin in [
            ("model", "model_artifact_hash"),
            ("predictions", "prediction_hash"),
            ("base10", "base10_feature_hash"),
            ("harvest", "harvest_state_feature_hash"),
            ("common", "common_rowset_hash"),
        ]:
            if hashes[key] != PINS[pin]:
                raise ValueError("SOURCE_BINDING_DRIFT")
        fit, seal, old = (load(paths[k]) for k in ("fit", "seal", "s5_contract"))
        if any(
            fit["M1"][k] != PINS[k]
            for k in ("model_artifact_hash", "model_config_hash", "prediction_hash")
        ):
            raise ValueError("MODEL_IDENTITY_MISMATCH")
        if (
            seal["seal_hash"] != PINS["prediction_seal_hash"]
            or digest({k: v for k, v in seal.items() if k != "seal_hash"}) != seal["seal_hash"]
            or seal["labels_read"] is not False
            or seal["phase"] != "FINAL"
            or seal["label_scope"] != "EXPOSED_OOT"
            or seal["rowset_hash"] != PINS["target_rowset_hash"]
            or seal["predictions"][PREDICTIONS] != PINS["prediction_hash"]
            or old["contract_hash"] != seal["contract_hash"]
            or digest({k: v for k, v in old.items() if k != "contract_hash"})
            != old["contract_hash"]
            or digest(old["models"]["M1"]) != PINS["model_config_hash"]
        ):
            raise ValueError("SEALED_SOURCE_DRIFT")
        authority = public_authority()
        model = load(paths["model"])
        compat = a.validate_legacy_m1_artifact(
            model,
            file_hash=hashes["model"],
            contract_standardization=old["ridge"]["standardization"],
            config_standardization=load(REPOSITORY / EVIDENCE / "model-config-freeze.json")[
                "ridge"
            ]["standardization"],
            historical_source_hash=authority["historical_source"]["source_sha256"],
            historical_schema_proven=authority["historical_source"]["schema_proven"],
        )
        a.validate_model(model, compatibility=compat)
        full = FrozenDataset(dataset, "FINAL").features("EXPOSED_OOT")
        rows, states = HarvestCustody(harvest).bind("EXPOSED_OOT", full)
        targets = target_rows(rows, states, "M1")
        predictions = load(paths["predictions"])
        by_key: dict[str, str] = {}
        for r in predictions:
            if set(r) != {"row_key", "predictions"} or len(r["predictions"]) != 15:
                raise ValueError("ATTRIBUTION_ROWSET_ACCOUNTING_FAILED")
            for i, p in enumerate(r["predictions"], 1):
                key = f"{r['row_key']}#D{i:02}"
                if key in by_key or not isinstance(p, str):
                    raise ValueError("ATTRIBUTION_ROWSET_ACCOUNTING_FAILED")
                by_key[key] = p
        keys = [r.key for r in targets]
        if (
            len(rows) != ORIGINS
            or len(targets) != TARGETS
            or len(predictions) != ORIGINS
            or len(set(keys)) != TARGETS
            or set(keys) != set(by_key)
            or digest(sorted(keys)) != PINS["target_rowset_hash"]
        ):
            raise ValueError("ATTRIBUTION_ROWSET_ACCOUNTING_FAILED")
        return model, targets, by_key, compat, hashes


def output_guard(output: Path, *roots: Path) -> None:
    resolved = output.resolve()
    if any(
        resolved == p.resolve()
        or resolved.is_relative_to(p.resolve())
        or p.resolve().is_relative_to(resolved)
        for p in (*roots, REPOSITORY)
    ):
        raise ValueError("PRIVATE_OUTPUT_LOCATION_INVALID")


def prepare(s5: Path, dataset: Path, harvest: Path, output: Path) -> None:
    output_guard(output, s5, dataset, harvest)
    if output.exists():
        raise ValueError("OUTPUT_ALREADY_EXISTS")
    frozen = policy()
    _, _, _, compat, hashes = sources(s5, dataset, harvest)
    contract = {
        "task_id": TASK,
        "base_main_sha": BASE,
        "policy": frozen,
        "policy_hash": digest(frozen),
    }
    contract["contract_hash"] = digest(contract)
    save(output / "contract.json", contract)
    save(
        output / "source-binding.json",
        {
            "source_hashes": hashes,
            "legacy_compatibility": compat,
            "label_bytes_read": False,
            "model_training_executed": False,
        },
    )


def verify_contract(output: Path) -> dict[str, Any]:
    c: dict[str, Any] = load(output / "contract.json")
    frozen = policy()
    if (
        c["task_id"] != TASK
        or c["base_main_sha"] != BASE
        or c["policy"] != json.loads(canonical(frozen))
        or c["policy_hash"] != digest(frozen)
        or c["contract_hash"] != digest({k: v for k, v in c.items() if k != "contract_hash"})
    ):
        raise ValueError("CONTRACT_DRIFT")
    return c


def run(s5: Path, dataset: Path, harvest: Path, output: Path) -> None:
    output_guard(output, s5, dataset, harvest)
    c = verify_contract(output)
    binding = load(output / "source-binding.json")
    model, targets, predictions, compat, hashes = sources(s5, dataset, harvest)
    if binding != {
        "source_hashes": hashes,
        "legacy_compatibility": compat,
        "label_bytes_read": False,
        "model_training_executed": False,
    }:
        raise ValueError("SOURCE_BINDING_DRIFT")
    save(output / "run-started.json", {"process_id": os.getpid()})
    attributed: list[dict[str, Any]] = []
    origins: dict[str, list[dict[str, Any]]] = {}
    for r in sorted(targets, key=lambda r: (r.forecast_origin, r.base_id, r.lead_day, r.key)):
        if r.season != "2025-2026" or tuple(n for n, _ in r.feature_values) != a.FEATURES:
            raise ValueError("FEATURE_SCHEMA_DRIFT")
        value = {
            "target_row_key": r.key,
            "base_id": r.base_id,
            "season": r.season,
            "forecast_origin": r.forecast_origin,
            "lead_day": r.lead_day,
            "target_date": r.target_date.isoformat(),
            "point_model_id": a.MODEL_ID,
            **a.attribute(model, r.features, predictions[r.key]),
            "model_artifact_file_hash": PINS["model_artifact_hash"],
            "attribution_policy_version": a.POLICY_VERSION,
        }
        value["row_hash"] = digest(value)
        attributed.append(value)
        origins.setdefault(r.key.rsplit("#D", 1)[0], []).append(value)
    horizon_rows = [
        {"row_key": key, **{f"H{h}": a.horizon(values, h) for h in (7, 15)}}
        for key, values in sorted(origins.items())
    ]
    artifacts = {
        "private-target-attribution.json": attributed,
        "private-horizon-attribution.json": horizon_rows,
        **a.summaries(attributed, horizon_rows),
    }
    if any(sha(p.read_bytes()) != hashes[k] for k, p in source_paths(s5, dataset, harvest).items()):
        raise ValueError("SOURCE_ARTIFACT_MUTATION")
    for name, value in artifacts.items():
        save(output / name, value)
    save(
        output / "execution-receipt.json",
        {
            "contract_hash": c["contract_hash"],
            "source_binding_hash": sha((output / "source-binding.json").read_bytes()),
            "artifact_hashes": {n: sha((output / n).read_bytes()) for n in OUTPUTS},
            "label_bytes_read": False,
            "source_artifact_mutation": False,
            "result": "PASS",
        },
    )


def privacy(value: Any) -> None:
    forbidden = {
        "base_id",
        "base_name",
        "canonical_base_name",
        "row_key",
        "target_row_key",
        "forecast_origin",
        "target_date",
        "feature_values",
        "standardized_values",
        "raw_features",
        "coefficients",
        "intercept",
        "feature_means",
        "feature_scales",
        "training_row_keys",
        "labels",
        "actual",
        "daily_prediction",
        "prediction_values",
        "source_file",
        "password",
        "token",
        "secret",
        "credentials",
        "database_url",
    }
    if isinstance(value, dict):
        if forbidden & value.keys():
            raise ValueError("PUBLIC_PRIVACY_FAILED")
        for item in value.values():
            privacy(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            privacy(item)
    elif isinstance(value, str) and any(
        x in value for x in ("/Users/", "/home/", "/root/", "/tmp/", "/private/", "postgresql://")
    ):
        raise ValueError("PUBLIC_PRIVATE_PATH")


def publish(primary: Path, replay: Path, public: Path) -> None:
    if primary.resolve() == replay.resolve() or public.exists():
        raise ValueError("REPLAY_OR_OUTPUT_INVALID")
    c = verify_contract(primary)
    if (
        c != verify_contract(replay)
        or load(primary / "run-started.json")["process_id"]
        == load(replay / "run-started.json")["process_id"]
    ):
        raise ValueError("FRESH_PROCESS_REPLAY_REQUIRED")
    receipt = load(primary / "execution-receipt.json")
    if receipt != load(replay / "execution-receipt.json") or receipt["result"] != "PASS":
        raise ValueError("REPLAY_MISMATCH")
    if any(
        sha((root / "source-binding.json").read_bytes()) != receipt["source_binding_hash"]
        for root in (primary, replay)
    ):
        raise ValueError("SOURCE_BINDING_DRIFT")
    for name in OUTPUTS:
        if (primary / name).read_bytes() != (replay / name).read_bytes() or sha(
            (primary / name).read_bytes()
        ) != receipt["artifact_hashes"][name]:
            raise ValueError("REPLAY_MISMATCH")
    evidence = {
        "attribution-policy-r1.json": c,
        "source-binding-r1.json": load(primary / "source-binding.json"),
    }
    for original, name in [
        ("feature-summary.json", "feature-contribution-summary-r1.json"),
        ("family-group-summary.json", "family-group-summary-r1.json"),
        ("semantic-group-summary.json", "business-semantic-group-summary-r1.json"),
        ("horizon-summary.json", "horizon-contribution-summary-r1.json"),
        ("reconstruction-summary.json", "reconstruction-summary-r1.json"),
    ]:
        evidence[name] = load(primary / original)
    evidence["deterministic-replay-report-r1.json"] = {
        "result": "PASS",
        "fresh_processes_verified": True,
        "artifact_hashes": receipt["artifact_hashes"],
        "policy_hash": c["policy_hash"],
    }
    evidence["privacy-scan-report-r1.json"] = {
        "result": "PASS",
        "public_private_data_leak": False,
        "private_attribution_rows_committed": False,
        "model_parameters_public": False,
    }
    evidence["v0.16-s3-forecast-attribution-r1.json"] = {
        "task_id": TASK,
        "version": "0.16.0",
        "stage": "S3",
        "base_main_sha": BASE,
        "engineering_result": "PASS",
        "policy_hash": c["policy_hash"],
        "model_id": a.MODEL_ID,
        "model_role": c["policy"]["model_role"],
        "source_bindings": PINS,
        "legacy_compatibility": evidence["source-binding-r1.json"]["legacy_compatibility"],
        "origin_count": ORIGINS,
        "target_row_count": TARGETS,
        "feature_count": 14,
        "attribution_method": "STANDARDIZED_LINEAR_TERM_DECOMPOSITION",
        "attribution_is_causal_explanation": False,
        "shap_used": False,
        "tree_shap_used": False,
        "label_bytes_read": False,
        "training_label_bytes_read": False,
        "training_feature_reconstruction": False,
        "current_season_actual_read": False,
        "current_season_actual_import": False,
        "current_season_actual_scoring": False,
        "model_inference_replay_executed": True,
        "model_training_executed": False,
        "model_refit_executed": False,
        "model_tuning_executed": False,
        "source_artifact_mutation": False,
        "db_migration_created": False,
        "http_attribution_api_implemented": False,
        "mcp_attribution_tools_implemented": False,
        "frontend_changed": False,
        "s1_changed": False,
        "s2_changed": False,
        "v0_14_changed": False,
        "v0_15_changed": False,
        "s4_started": False,
        "s5_started": False,
        "s6_started": False,
        "v0_17_started": False,
        "deterministic_replay": "PASS",
        "privacy_scan": "PASS",
        "production_use_approved": False,
        "prospective_claim_allowed": False,
        "retrospective_authority_used": True,
        "strict_pit": False,
        "external_exact_head_ci": "REQUIRED_SEPARATE_TERMINAL_PR_RECEIPT",
        "ready_authorized": False,
        "merge_authorized": False,
        "tag_authorized": False,
        "release_authorized": False,
        "stop": True,
        "summary_hashes": {n: digest(v) for n, v in evidence.items() if "summary" in n},
    }
    for value in evidence.values():
        privacy(value)
    evidence["manifest-r1.json"] = {
        "policy_hash": c["policy_hash"],
        "files": {n: digest(v) for n, v in evidence.items()},
    }
    for name, value in evidence.items():
        save(public / name, value)


def main() -> int:
    parser = argparse.ArgumentParser(description="Frozen research-only M1 attribution")
    parser.add_argument("phase", choices=("PREPARE", "RUN", "REPLAY", "PUBLISH"))
    for name in (
        "s5-output-root",
        "dataset-root",
        "harvest-state-root",
        "output",
        "replay-output",
        "public-output",
    ):
        parser.add_argument("--" + name, type=Path)
    args = parser.parse_args()
    try:
        with no_labels():
            roots = (args.s5_output_root, args.dataset_root, args.harvest_state_root)
            if args.phase == "PREPARE":
                prepare(*roots, args.output)
            elif args.phase == "RUN":
                run(*roots, args.output)
            elif args.phase == "REPLAY":
                verify_contract(args.output)
                prepare(*roots, args.replay_output)
                run(*roots, args.replay_output)
            else:
                output_guard(args.public_output, *roots, args.output, args.replay_output)
                publish(args.output, args.replay_output, args.public_output)
        print(json.dumps({"phase": args.phase, "result": "PASS", "label_bytes_read": False}))
        return 0
    except Exception as exc:
        code = (
            str(exc)
            if isinstance(exc, ValueError)
            and str(exc).replace("_", "").isalnum()
            and str(exc).isupper()
            else "ATTRIBUTION_OPERATOR_FAILED"
        )
        print(json.dumps({"phase": args.phase, "result": "FAIL", "code": code}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
