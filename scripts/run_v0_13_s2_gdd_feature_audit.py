"""S2 operator-only feature/identity audit. Never loads harvest or runs a model."""

from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from backend.app.area_yield import gdd_features as g
from backend.app.area_yield.data import digest

BASE_SHA = "4f0caedaf7a4f9942371f1fd92dc5132c3c671b5"
SOURCE_HEAD = "817bbed30e296bc01fb2af9560e66c272ec27247"
WEATHER_SHA = "5ad49f11895c76e6aadd01d240ada3ba93d599d25138a2609887e527e58dad3b"
PUBLIC_S3_SHA = "cc3e81003463377dd4fe8d0adc792dc453e68c5391c8fcf98a9ceb038a4d121b"
STANDARDIZATION = "TRAIN_ONLY_STANDARD_SCALER_POPULATION_STD"
MODEL_ID = "AREA_DAILY_RIDGE_V1_ROLLING_OOT_NO_WEATHER"
SERIALIZED_FIELDS = {
    "model_id",
    "fold_id",
    "feature_names",
    "alpha",
    "intercept_unpenalized",
    "nonnegative_output_clip",
    "solver",
    "feature_means",
    "feature_scales",
    "coefficients",
    "intercept",
    "training_row_keys",
    "training_label_hash",
    "training_input_hash",
    "artifact_hash",
}
FROZEN = {
    "FOLD_A": {
        "artifact_hash": "3b6704a639501b097a1104d5f92b03ded8dc242230615544d48e1929b310f9ee",
        "training_input_hash": "6a72ac9f9afb8ee6b2fca292f2d35d296153ab1412a6ee2f59055e8d9d1903b5",
        "training_label_hash": "f18a290ec7888126d630d6426002fd8592d01b294bf46bc367889acf44db4e43",
        "count": 17460,
        "keys_hash": "90e9fdf84b45eeb7cfb819bd9384f776eaf5e94ca541eef99cded43904e1d036",
        "validation_count": 49140,
        "validation_hash": "85654a3b60c05c7e028825d9fa96f67681a0985bd991c86e4bbdb73652108788",
    },
    "FOLD_B": {
        "artifact_hash": "361eb893e6b0aaed89044df5163b6ebeb48a7459c1addcaac8414986aa64114d",
        "training_input_hash": "be8188eb257924038dd40dbf403d4a8e2c2baa60d4e003dac86628f8a20e0e20",
        "training_label_hash": "97169c277b1ae737ab6b01a202defedf36c0f87dc69e2535b33afab146699eac",
        "count": 59471,
        "keys_hash": "5ee82a037b7c8a0d1cc396ad69ffb92421e44b40d57d8a89c87567b8027a97d4",
        "validation_count": 109620,
        "validation_hash": "e4568d3f61c1368f059c46b2240af8c4f455cce8731a4409a0bc43b3fd071869",
    },
}


def verify_v0_7_s3_legacy_model_a_artifact(
    artifact: dict[str, Any], public: dict[str, Any], fold_id: str
) -> dict[str, Any]:
    """Only the exact two frozen Model A identities can use this compatibility rule.

    No corrected artifact is created. Public coefficient parity is identity
    verification, never inference or scientific interpretation.
    """
    if (
        fold_id not in FROZEN
        or artifact.get("model_id") != MODEL_ID
        or artifact.get("fold_id") != fold_id
    ):
        raise g.GDDError("LEGACY_MODEL_OR_FOLD_MISMATCH")
    if set(artifact) != SERIALIZED_FIELDS:
        raise g.GDDError("LEGACY_SERIALIZER_FIELD_MISMATCH")
    frozen = FROZEN[fold_id]
    for key in ("artifact_hash", "training_input_hash", "training_label_hash"):
        if artifact[key] != frozen[key]:
            raise g.GDDError("LEGACY_FROZEN_IDENTITY_MISMATCH")
    keys = artifact["training_row_keys"]
    if (
        not isinstance(keys, list)
        or len(keys) != frozen["count"]
        or digest(keys) != frozen["keys_hash"]
    ):
        raise g.GDDError("LEGACY_TRAINING_ROW_KEYS_MISMATCH")
    if keys != sorted(set(keys)):
        raise g.GDDError("LEGACY_TRAINING_ROW_KEYS_ORDER")
    for key in keys:
        g.parse_row_key(key)
    for key, value in public.items():
        if key == "training_row_key_count":
            if len(keys) != value:
                raise g.GDDError("LEGACY_PUBLIC_EVIDENCE_MISMATCH")
        elif key not in artifact or artifact[key] != value:
            raise g.GDDError("LEGACY_PUBLIC_EVIDENCE_MISMATCH")
    if set(public) != (SERIALIZED_FIELDS - {"training_row_keys"}) | {"training_row_key_count"}:
        raise g.GDDError("LEGACY_PUBLIC_EVIDENCE_FIELDS_MISMATCH")
    payload = {k: v for k, v in artifact.items() if k != "artifact_hash"}
    direct = digest(payload)
    compatibility = digest({**payload, "standardization": STANDARDIZATION})
    if compatibility != artifact["artifact_hash"]:
        raise g.GDDError("LEGACY_COMPATIBILITY_HASH_MISMATCH")
    if direct == artifact["artifact_hash"]:
        raise g.GDDError("LEGACY_GAP_NOT_PRESENT")
    return {
        "direct_self_hash_valid": False,
        "direct_self_hash": direct,
        "legacy_compatibility_hash": compatibility,
        "legacy_compatibility_hash_valid": True,
        "public_evidence_parity": "PASS",
        "training_input_hash_match": True,
        "training_label_hash_match": True,
        "training_row_keys_hash_match": True,
    }


def file_identity(p: Path) -> dict[str, Any]:
    s = p.stat()
    return {"sha256": g.sha256(p), "size_bytes": s.st_size, "mtime_ns": s.st_mtime_ns}


def reconstruct_validation(fold: dict[str, Any], daily: list[dict[str, Any]]) -> list[str]:
    """Calendar + public scope + accepted weather presence, no actual authority."""
    season = fold["validation_season"]
    year = int(season[:4])
    start, end = date(year, 7, 1), date(year + 1, 4, 15)
    bases = sorted(fold["validation_dataset_meta"]["incomplete_origin_count_by_base"])
    if len(bases) != fold["validation_base_count"]:
        raise g.GDDError("VALIDATION_SCOPE_MISMATCH")
    present = {(r["base_id"], date.fromisoformat(r["local_date"])) for r in daily}
    keys: list[str] = []
    for base in bases:
        origin = start
        while origin <= end:
            if all((base, origin - timedelta(days=i)) in present for i in range(1, 31)):
                for lead in range(15):
                    target = origin + timedelta(days=lead)
                    if target <= end:
                        keys.append(f"{base}+{origin}T00:00:00+08:00+{target}")
            origin += timedelta(days=1)
    return sorted(keys)


def write_json(path: Path, payload: Any) -> None:
    with path.open("x", encoding="utf-8") as f:
        f.write(
            json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False)
            + "\n"
        )


def execute(
    *, daily_path: Path, fold_a_path: Path, fold_b_path: Path, public_path: Path, output: Path
) -> dict[str, Any]:
    if output.exists():
        raise g.GDDError("OUTPUT_ALREADY_EXISTS")
    before = {
        "era5": file_identity(daily_path),
        "fold_a": file_identity(fold_a_path),
        "fold_b": file_identity(fold_b_path),
    }
    if before["era5"]["sha256"] != WEATHER_SHA or g.sha256(public_path) != PUBLIC_S3_SHA:
        raise g.GDDError("FROZEN_AUTHORITY_HASH_MISMATCH")
    public = json.loads(public_path.read_text(encoding="utf-8"))
    folds: dict[str, Any] = {}
    row_sets: dict[str, dict[str, list[str]]] = {}
    for name, path in (("fold_a", fold_a_path), ("fold_b", fold_b_path)):
        artifact = json.loads(path.read_text(encoding="utf-8"))
        f = public["folds"][name]
        folds[name] = {
            "legacy": verify_v0_7_s3_legacy_model_a_artifact(artifact, f["model_a"], f["fold_id"])
        }
        row_sets[name] = {"train": artifact["training_row_keys"]}
    daily = g.load_daily(daily_path, WEATHER_SHA)
    dates = [r["local_date"] for r in daily]
    if (
        len(daily) != 32984
        or len({r["base_id"] for r in daily}) != 38
        or min(dates) != "2023-07-01"
        or max(dates) != "2026-04-15"
    ):
        raise g.GDDError("WEATHER_SCOPE_MISMATCH")
    for name in row_sets:
        validation = reconstruct_validation(public["folds"][name], daily)
        frozen = FROZEN[public["folds"][name]["fold_id"]]
        if (
            len(validation) != frozen["validation_count"]
            or digest(validation) != frozen["validation_hash"]
        ):
            raise g.GDDError("FROZEN_VALIDATION_ROW_KEYS_MISMATCH")
        row_sets[name]["validation"] = validation
    index = g.index_daily(daily)
    identities = sorted(
        {
            g.parse_row_key(key)[:2]
            for splits in row_sets.values()
            for keys in splits.values()
            for key in keys
        }
    )
    contexts = [
        g.build_gdd_context(index, base, origin, WEATHER_SHA) for base, origin in identities
    ]
    manifest = g.build_gdd_manifest(contexts, WEATHER_SHA)
    by_key = {(c["base_id"], c["forecast_origin"]): c for c in contexts}
    for name, splits in row_sets.items():
        for split, keys in splits.items():
            folds[name][split] = g.project_rows(keys, by_key)
            if folds[name][split]["common_row_count"] != len(keys):
                raise g.GDDError("GDD_ROW_LOSS_REQUIRES_OWNER_REVIEW")
    after = {
        "era5": file_identity(daily_path),
        "fold_a": file_identity(fold_a_path),
        "fold_b": file_identity(fold_b_path),
    }
    if before != after:
        raise g.GDDError("SOURCE_ARTIFACT_MUTATED")
    report = {
        "schema": "V0_13_S2_GDD_AUDIT_R2",
        "manifest": manifest,
        "folds": folds,
        "weather": {
            "row_count": len(daily),
            "base_count": 38,
            "date_min": min(dates),
            "date_max": max(dates),
        },
        "source_immutability": {"before": before, "after": after, "unchanged": True},
        "EVENT_TIME_LEAKAGE_GATE": "PASS",
        "GDD_INCREMENTAL_VALUE": "NOT_EVALUATED",
        "MODEL_TRAINING_EXECUTED": False,
        "SCORING_EXECUTED": False,
        "PRIVATE_HARVEST_ROW_READ": False,
        "VALIDATION_ACTUAL_LABEL_READ": False,
    }
    # Only the operator-specified private outputs contain context values/keys.
    output.mkdir(parents=True)
    with (output / "gdd-contexts.jsonl").open("x", encoding="utf-8") as f:
        for c in contexts:
            f.write(json.dumps(c, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n")
    write_json(output / "gdd-manifest.json", manifest)
    write_json(output / "common-cohort-manifest.json", folds)
    write_json(output / "coverage-audit.json", report)
    write_json(output / "frozen-row-identities.json", row_sets)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--daily", type=Path, required=True)
    parser.add_argument("--fold-a", type=Path, required=True)
    parser.add_argument("--fold-b", type=Path, required=True)
    parser.add_argument("--public-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = execute(
        daily_path=args.daily,
        fold_a_path=args.fold_a,
        fold_b_path=args.fold_b,
        public_path=args.public_evidence,
        output=args.output,
    )
    print(
        json.dumps(
            {
                "manifest": report["manifest"],
                "EVENT_TIME_LEAKAGE_GATE": "PASS",
                "scientific_execution": False,
            }
        )
    )


if __name__ == "__main__":
    main()
