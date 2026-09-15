"""Replay S3 eligibility using the corrected S1 R2 alias authority.

This is an evidence rebind only.  It intentionally calls the existing S3
qualification functions and never trains a model or creates weather features.
The old R1/R2 private artifacts remain append-only historical evidence; each
invocation writes to a new R3 replay directory.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from scripts.audit_v0_5_s3_training_eligibility_r1 import (
    build_outputs,
    canonical_value_hash,
    file_hash,
    load_inputs,
    read_json,
    write_json,
)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def reconcile_scope_sets(known_ids: set[str], yunnan_ids: set[str]) -> dict[str, Any]:
    intersection = sorted(known_ids & yunnan_ids)
    known_only = sorted(known_ids - yunnan_ids)
    weather_only = sorted(yunnan_ids - known_ids)
    return {
        "active_registry_base_count": None,
        "known_support_base_count": len(known_ids),
        "known_support_ids_hash": canonical_value_hash(sorted(known_ids)),
        "yunnan_core_base_count": len(yunnan_ids),
        "yunnan_core_ids_hash": canonical_value_hash(sorted(yunnan_ids)),
        "known_support_weather_intersection_count": len(intersection),
        "known_support_weather_intersection_ids_hash": canonical_value_hash(intersection),
        "known_support_only_count": len(known_only),
        "known_support_only_ids": known_only,
        "weather_only_count": len(weather_only),
        "weather_only_ids": weather_only,
        "known_support_weather_set_equal": known_ids == yunnan_ids,
    }


def _verify_dehong_authority(
    config: dict[str, Any], inputs: dict[str, Any], registry_root: Path
) -> dict[str, Any]:
    mapping = inputs.get("mapping_authority")
    required = config["mapping_authority"]
    if not isinstance(mapping, dict):
        raise ValueError("S1 R2 mapping authority was not loaded")
    source = required["required_alias"]["source"]
    target = required["required_alias"]["target"]
    base_id = required["required_alias"]["canonical_base_id"]
    aliases = mapping.get("aliases", {})
    if not isinstance(aliases, dict) or source not in aliases or target not in aliases[source]:
        raise ValueError("required Dehong alias is absent from mapping authority")

    member_rows = read_csv_rows(registry_root / "member-farm-mapping.csv")
    alias_rows = [
        row
        for row in member_rows
        if row.get("historical_farm_identity") == source
        and row.get("normalized_identity") == target
        and row.get("matched_base_id") == base_id
        and row.get("match_method") == "AUTHORIZED_ALIAS"
        and row.get("match_status") == "AUTHORIZED_ALIAS"
    ]
    if len(alias_rows) != 1:
        raise ValueError("required Dehong alias row is not uniquely authorized")

    season_rows = read_csv_rows(registry_root / "business-season-boundary-audit.csv")
    dehong = next(
        (
            row
            for row in season_rows
            if row.get("base_id") == base_id and row.get("season") == "2025-2026"
        ),
        None,
    )
    if dehong is None:
        raise ValueError("2025-2026 Dehong qualification row is missing")
    if dehong.get("unresolved_member_farm_count") != "0":
        raise ValueError("Dehong still has unresolved members in S1 R2 authority")
    if dehong.get("pre_cutoff_total_kg") != "392895.468000":
        raise ValueError("Dehong pre-cutoff total does not match S1 R2 authority")
    return {
        "base_id": base_id,
        "base_name": required["required_alias"]["canonical_base_name"],
        "season": "2025-2026",
        "unresolved_member_farm_count": int(dehong["unresolved_member_farm_count"]),
        "pre_cutoff_total_kg": dehong["pre_cutoff_total_kg"],
        "authorized_alias_source": source,
        "authorized_alias_target": target,
        "mapping_authority_version": mapping["version"],
        "mapping_authority_payload_hash": mapping["hash"],
        "mapping_authority_file_sha256": inputs["files"]["mapping_authority"],
        "alias_row_evidence": alias_rows[0].get("evidence", ""),
    }


def _scope_from_output(output: Path, registry_root: Path) -> dict[str, Any]:
    registry = read_json(registry_root / "base-registry-v1.json")
    registry_ids = {str(base["base_id"]) for base in registry["bases"]}
    yunnan_ids = {
        str(base["base_id"])
        for base in registry["bases"]
        if base.get("region_scope") == "YUNNAN_CORE"
    }
    daily_rows = read_csv_rows(output / "daily-label-eligibility.csv")
    known_ids = {row["base_id"] for row in daily_rows if row["label_known"] == "True"}
    result = reconcile_scope_sets(known_ids, yunnan_ids)
    result["active_registry_base_count"] = len(registry_ids)
    result["active_registry_ids_hash"] = canonical_value_hash(sorted(registry_ids))
    return result


def _refresh_manifest(output: Path) -> dict[str, str]:
    manifest = {
        path.name: file_hash(path)
        for path in sorted(output.iterdir())
        if path.is_file() and path.name != "artifact-manifest.json"
    }
    write_json(output / "artifact-manifest.json", manifest)
    return manifest


def run_rebind(
    config_path: Path,
    registry_root: Path,
    weather_root: Path,
    output: Path,
) -> dict[str, Any]:
    if output.exists():
        raise ValueError("R3 replay output must be new and append-only")
    config = read_json(config_path)
    if config.get("task_id") != "V0_5_S3_ELIGIBILITY_AUTHORITY_REBIND_R3":
        raise ValueError("wrong S3 R3 rebind configuration")
    inputs = load_inputs(config, registry_root, weather_root)
    authority_proof = _verify_dehong_authority(config, inputs, registry_root)
    summary = build_outputs(config, inputs, output)
    scope = _scope_from_output(output, registry_root)
    support_counts = read_json(output / "support-counts-by-season.json")
    forward_folds = read_json(output / "forward-fold-support.json")

    summary.update(
        {
            "authority_rebind_status": "S1_R2_ALIAS_CORRECTED_AUTHORITY_LOADED",
            "mapping_authority_version": config["mapping_authority"]["version"],
            "mapping_authority_payload_hash": config["mapping_authority"]["payload_hash"],
            "mapping_authority_file_sha256": inputs["files"]["mapping_authority"],
            "supersedes_s3_evidence": "R1_AND_R2_SUPPORT_EVIDENCE",
            "previous_s3_evidence_status": "SUPERSEDED_BY_AUTHORITY_REBIND_R3",
            "known_support_scope": scope,
            "full_season_complete_count": summary["full_season_complete_count"],
            "full_season_partial_count": summary["full_season_partial_count"],
            "full_season_blocked_count": summary["full_season_blocked_count"],
            "model_training": False,
            "weather_features_generated": False,
            "s4_weather_ablation_authorized": False,
        }
    )
    write_json(output / "summary.json", summary)
    write_json(
        output / "r3-authority-rebind.json",
        {
            "task_id": config["task_id"],
            "base_r2_head": "a1d3025402f5d6252c91df7419b48fb00179fbf9",
            "authority": authority_proof,
            "input_hashes": inputs["files"],
            "mapping_authority_version": config["mapping_authority"]["version"],
            "mapping_authority_payload_hash": config["mapping_authority"]["payload_hash"],
            "old_r1_r2_evidence_preserved": True,
            "model_training": False,
        },
    )
    write_json(
        output / "r3-scope-reconciliation.json",
        {
            "task_id": config["task_id"],
            "scope": scope,
            "support_counts_by_season": support_counts["by_season"],
            "forward_folds": forward_folds["folds"],
            "full_season_status": {
                "complete": summary["full_season_complete_count"],
                "partial": summary["full_season_partial_count"],
                "blocked": summary["full_season_blocked_count"],
            },
            "full_season_model_authorized": False,
        },
    )
    manifest = _refresh_manifest(output)
    return {
        "summary": summary,
        "authority": authority_proof,
        "scope": scope,
        "support_counts": support_counts,
        "forward_folds": forward_folds,
        "artifact_manifest": manifest,
        "artifact_manifest_sha256": file_hash(output / "artifact-manifest.json"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/v0_5_s3_eligibility_authority_rebind_r3.json"),
    )
    parser.add_argument("--registry-root", type=Path, required=True)
    parser.add_argument("--weather-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_rebind(args.config, args.registry_root, args.weather_root, args.output)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
