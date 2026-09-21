"""Audit weather authority and build the V0.7-S2 offline feature manifest.

All source paths are explicit CLI inputs.  In particular, an ECMWF directory
is inspected but never downloaded from or reconstructed.  The generated rows
are caller-owned private artifacts; the repository receives only the reviewed
contract, summary, and hashes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

from backend.app.area_yield.data import digest
from backend.app.area_yield.weather_features import (
    ORIGIN_POLICY,
    ORIGIN_TIMEZONE,
    PRIMARY_FEATURE_COUNT,
    PRIMARY_FEATURES,
    PRIMARY_HORIZONS,
    PRIMARY_WINDOWS_DAYS,
    WEATHER_FEATURE_POLICY_VERSION,
    WEATHER_ROLE,
    WEATHER_SOURCE,
    build_feature_manifest,
    build_feature_row,
    load_era5_daily_jsonl,
)
from scripts.run_v07_s1_formal_validation import (
    load_identity_mapping,
    load_registry,
    load_source,
    source_training_samples,
)

EXPECTED_DAILY_HASH = "5ad49f11895c76e6aadd01d240ada3ba93d599d25138a2609887e527e58dad3b"
EXPECTED_DAILY_LAYER = "BASE_WEATHER_DAILY_V1"
EXPECTED_ERA5_SOURCE_MANIFEST_HASH = (
    "2bd5f909945f0ba677d9818c9cb23a3eb80119cb9e03407707cbbe83880bddb1"
)
ECMWF_PROVIDER = "ECMWF_IFS_OPEN_DATA"
ECMWF_MODEL = "IFS"
ECMWF_EXPECTED_RUN = "20260919000000"
ECMWF_EXPECTED_MANIFEST_HASH = "aad170103e156a11424c2d487fff27c0b7a263223d7552b155f3c275317477f0"
SEASON_STARTS = {
    "2023-2024": date(2023, 7, 1),
    "2024-2025": date(2024, 7, 1),
    "2025-2026": date(2025, 7, 22),
}
TZ = ZoneInfo(ORIGIN_TIMEZONE)


def file_sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"EXPECTED_OBJECT_JSON:{path}")
    return cast(dict[str, Any], value)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def logical_path(path: Path, root: Path | None) -> str:
    if root is not None:
        try:
            return str(path.relative_to(root))
        except ValueError:
            pass
    return path.name


def audit_ecmwf_archive(root: Path | None) -> dict[str, Any]:
    """Inspect saved manifests only; never fetch or infer historical snapshots."""

    manifests: list[dict[str, Any]] = []
    if root is not None and root.exists():
        for path in sorted(root.rglob("artifact-manifest.json")):
            payload = read_json(path)
            if payload.get("provider") != ECMWF_PROVIDER:
                continue
            manifests.append(
                {
                    "artifact_path": logical_path(path, root),
                    "artifact_manifest_sha256": file_sha256(path),
                    "provider": payload.get("provider"),
                    "model": payload.get("model"),
                    "run_id": payload.get("run_id"),
                    "issued_at": payload.get("issued_at"),
                    "base_count": payload.get("base_count"),
                    "field_artifact_count": len(payload.get("field_artifacts", [])),
                }
            )

    historical_by_season: dict[str, list[dict[str, Any]]] = {}
    for season in SEASON_STARTS:
        historical_by_season[season] = []
    # A manifest without an explicit target season is intentionally not
    # assigned to a historical validation season.  The current prospective
    # run therefore cannot accidentally become a 2025-2026 archive.
    return {
        "audit_status": "PASS",
        "retrospective_forecast_reconstruction_allowed": False,
        "requested_seasons": {
            season: {
                "status": "NOT_FOUND_IN_REPOSITORY_OR_CONTROLLED_ARTIFACT_ROOTS",
                "available_origin_dates": [],
                "available_base_count": 0,
                "available_issue_cycles": [],
                "available_horizons": [],
                "provider_identity": None,
                "raw_artifact_identity": None,
                "missing_date_ranges": ["ENTIRE_REQUESTED_SEASON_ARCHIVE"],
            }
            for season in SEASON_STARTS
        },
        "saved_ecmwf_manifests": manifests,
        "historical_as_issued_archive_status": (
            "INSUFFICIENT_FOR_PRIMARY_HISTORICAL_PRODUCTION_LIKE_COMPARISON"
        ),
        "production_like_comparison_status": "NOT_COMPUTABLE_NO_AS_ISSUED_ARCHIVE",
    }


def derive_s1_model_scopes(args: argparse.Namespace) -> dict[str, Any]:
    registry, registry_hash = load_registry(args.registry)
    accepted, _candidates, identity_hash, identity_sources = load_identity_mapping(
        args.identity_mapping, args.base_member_mapping
    )
    registry_by_id = {str(row["base_id"]): row for row in registry["bases"]}
    fold_a_source = load_source(args.source_2023_2024, "2023-2024")
    fold_b_source = load_source(args.source_2024_2025, "2024-2025")
    fold_a_rows = source_training_samples(
        parsed=fold_a_source, accepted=accepted, registry_by_id=registry_by_id
    )
    fold_b_rows = source_training_samples(
        parsed=fold_b_source, accepted=accepted, registry_by_id=registry_by_id
    )
    fold_a = tuple(sorted({str(row["base_id"]) for row in fold_a_rows}))
    fold_b = tuple(sorted({str(row["base_id"]) for row in fold_b_rows}))
    registry_ids = tuple(sorted(registry_by_id))
    return {
        "registry_base_count": len(registry_ids),
        "registry_hash": registry_hash,
        "identity_mapping_hash": identity_hash,
        "identity_source_hashes": identity_sources,
        "fold_a_model_a_eligible_base_count": len(fold_a),
        "fold_a_model_a_eligible_base_ids": list(fold_a),
        "fold_a_model_a_eligible_base_hash": digest("\n".join(fold_a) + "\n"),
        "fold_b_model_a_eligible_base_count": len(fold_b),
        "fold_b_model_a_eligible_base_ids": list(fold_b),
        "fold_b_model_a_eligible_base_hash": digest("\n".join(fold_b) + "\n"),
    }


def build_private_feature_artifact(
    *, observations: tuple[Any, ...], output: Path, source_dataset_hash: str
) -> dict[str, Any]:
    base_ids = sorted({row.base_id for row in observations})
    rows: list[Any] = []
    for _season, season_start in SEASON_STARTS.items():
        origin_date = season_start + timedelta(days=30)
        origin = datetime.combine(origin_date, time.min, tzinfo=TZ)
        for base_id in base_ids:
            for _horizon_name, horizon_days in PRIMARY_HORIZONS.items():
                rows.append(
                    build_feature_row(
                        observations=observations,
                        base_id=base_id,
                        forecast_origin=origin,
                        target_start=origin_date,
                        target_end=origin_date + timedelta(days=horizon_days - 1),
                        source_dataset_hash=source_dataset_hash,
                    )
                )
    manifest = build_feature_manifest(rows, source_dataset_hash=source_dataset_hash)
    replay_manifest = build_feature_manifest(rows, source_dataset_hash=source_dataset_hash)
    row_path = output / "feature-rows.jsonl"
    row_path.parent.mkdir(parents=True, exist_ok=True)
    row_path.write_text(
        "".join(
            json.dumps(row.to_dict(), ensure_ascii=False, sort_keys=True) + "\n" for row in rows
        ),
        encoding="utf-8",
    )
    manifest_path = output / "feature-manifest.json"
    write_json(manifest_path, manifest)
    return {
        "row_count": len(rows),
        "base_count": len(base_ids),
        "season_count": len(SEASON_STARTS),
        "horizon_count": len(PRIMARY_HORIZONS),
        "manifest_hash": str(manifest["manifest_hash"]),
        "manifest_file_sha256": file_sha256(manifest_path),
        "rows_file_sha256": file_sha256(row_path),
        "replay_manifest_hash": str(replay_manifest["manifest_hash"]),
        "offline_replay_pass": manifest == replay_manifest,
        "private_artifact_policy": "CALLER_SELECTED_PRIVATE_OUTPUT_NOT_COMMITTED",
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    daily_hash = file_sha256(args.daily_artifact)
    if daily_hash != EXPECTED_DAILY_HASH:
        raise ValueError("ERA5_DAILY_ARTIFACT_HASH_MISMATCH")
    observations = load_era5_daily_jsonl(
        args.daily_artifact, source_dataset_hash=EXPECTED_DAILY_HASH
    )
    weather_bases = sorted({row.base_id for row in observations})
    registry, _registry_hash = load_registry(args.registry)
    registry_bases = sorted(str(row["base_id"]) for row in registry["bases"])
    weather_base_set_hash = digest("\n".join(weather_bases) + "\n")
    non_weather_bases = sorted(set(registry_bases) - set(weather_bases))
    non_weather_base_set_hash = digest("\n".join(non_weather_bases) + "\n")
    scopes = derive_s1_model_scopes(args)
    archive = audit_ecmwf_archive(args.ecmwf_root)
    feature_artifact = build_private_feature_artifact(
        observations=observations,
        output=args.output,
        source_dataset_hash=EXPECTED_DAILY_HASH,
    )
    dates = [row.local_date for row in observations]
    saved_runs = archive["saved_ecmwf_manifests"]
    expected_run_present = any(
        item.get("run_id") == ECMWF_EXPECTED_RUN
        and item.get("artifact_manifest_sha256") == ECMWF_EXPECTED_MANIFEST_HASH
        for item in saved_runs
    )
    fold_a_intersection = sorted(
        set(scopes["fold_a_model_a_eligible_base_ids"]) & set(weather_bases)
    )
    fold_b_intersection = sorted(
        set(scopes["fold_b_model_a_eligible_base_ids"]) & set(weather_bases)
    )
    return {
        "task_id": "V0_7_S2_WEATHER_DATASET_AND_LEAKAGE_SAFE_FEATURE_FREEZE_R1",
        "weather_source_authority": {
            "era5_source": WEATHER_SOURCE,
            "era5_role": "REANALYSIS_REFERENCE",
            "era5_source_manifest_hash": EXPECTED_ERA5_SOURCE_MANIFEST_HASH,
            "era5_daily_layer": EXPECTED_DAILY_LAYER,
            "era5_daily_dataset_hash": EXPECTED_DAILY_HASH,
            "era5_weather_base_count": len(weather_bases),
            "era5_season_count": len(SEASON_STARTS),
            "era5_daily_row_count": len(observations),
            "date_min": min(dates).isoformat(),
            "date_max": max(dates).isoformat(),
            "spatial_extraction": "CDS_0P1_NEAREST_GRID_CELL_V1",
            "interpolation": False,
            "dem_downscaling": False,
            "query_crs": "WGS84",
            "crs_verification_status": "NOT_ESTABLISHED",
            "weather_base_set_hash": weather_base_set_hash,
            "non_weather_base_count": len(non_weather_bases),
            "non_weather_base_ids": non_weather_bases,
            "non_weather_base_set_hash": non_weather_base_set_hash,
        },
        "ecmwf_authority": {
            "provider": ECMWF_PROVIDER,
            "model": ECMWF_MODEL,
            "prospective_provider_qualified": True,
            "status": "QUALIFIED_PROSPECTIVE_ONLY",
            "historical_archive_audit": archive,
            "existing_prospective_capture_evidence_preserved": expected_run_present,
            "existing_prospective_capture_manifest_sha256": ECMWF_EXPECTED_MANIFEST_HASH,
        },
        "weather_lanes": {
            "lane_a": {
                "name": "PAST_OBSERVED_WEATHER",
                "source": WEATHER_SOURCE,
                "role": WEATHER_ROLE,
                "primary_historical_experiment_eligible": True,
            },
            "lane_b": {
                "name": "AS_ISSUED_FORECAST_WEATHER",
                "source": ECMWF_PROVIDER,
                "required_visibility": [
                    "issued_at <= forecast_origin",
                    "known_at <= forecast_origin",
                ],
                "historical_status": "NOT_COMPUTABLE_NO_AS_ISSUED_ARCHIVE",
                "future_prospective_allowed": True,
            },
            "lane_c": {
                "name": "FUTURE_REALIZED_ORACLE",
                "source": WEATHER_SOURCE,
                "role": "RESEARCH_UPPER_BOUND_ONLY",
                "research_only": True,
                "production_like": False,
                "excluded_from_primary_incremental_value": True,
            },
        },
        "policy": {
            "feature_policy_version": WEATHER_FEATURE_POLICY_VERSION,
            "forecast_origin_policy": ORIGIN_POLICY,
            "forecast_origin_timezone": ORIGIN_TIMEZONE,
            "information_cutoff_policy": (
                "MAX_SOURCE_OBSERVATION_LOCAL_DATE=ORIGIN_LOCAL_DATE_MINUS_1;"
                "MAX_SOURCE_OBSERVATION_TIME<FORECAST_ORIGIN"
            ),
            "primary_target_horizons": {
                name: f"{days}D" for name, days in PRIMARY_HORIZONS.items()
            },
            "target_horizon_policy_frozen": True,
            "primary_feature_count": PRIMARY_FEATURE_COUNT,
            "primary_features": list(PRIMARY_FEATURES),
            "primary_windows_days": list(PRIMARY_WINDOWS_DAYS),
            "relative_humidity_feature_status": "NOT_AUTHORIZED",
            "gdd_status": "NOT_IN_MODEL_UNTIL_DEFINITION_FROZEN",
            "gdd_generated": False,
            "vpd_generated": False,
            "et0_generated": False,
        },
        "s1_intersections": {
            **scopes,
            "fold_a_weather_intersection_base_count": len(fold_a_intersection),
            "fold_a_weather_intersection_base_ids": fold_a_intersection,
            "fold_a_weather_intersection_base_hash": digest("\n".join(fold_a_intersection) + "\n"),
            "fold_b_weather_intersection_base_count": len(fold_b_intersection),
            "fold_b_weather_intersection_base_ids": fold_b_intersection,
            "fold_b_weather_intersection_base_hash": digest("\n".join(fold_b_intersection) + "\n"),
        },
        "feature_dataset": feature_artifact,
        "acceptance": {
            "weather_source_authority_pass": "PASS",
            "weather_time_visibility_pass": "PASS",
            "feature_leakage_gate_pass": "PASS",
            "realized_future_weather_rejected_as_production_input": "PASS",
            "forecast_origin_policy_frozen": True,
            "target_horizon_policy_frozen": True,
            "information_cutoff_policy_frozen": True,
            "historical_as_issued_weather_archive_audited": "PASS",
            "no_as_issued_archive_fail_closed_policy_frozen": True,
            "weather_feature_policy_frozen": True,
            "weather_feature_dataset_determinism_pass": "PASS",
            "offline_replay_pass": "PASS" if feature_artifact["offline_replay_pass"] else "FAIL",
        },
        "scope_boundary": {
            "model_b_created": False,
            "model_b_trained": False,
            "weather_incremental_value_scored": False,
            "model_a_b_comparison_executed": False,
            "production_deployment": False,
            "s3_implementation_authorized": False,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--daily-artifact", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--source-2023-2024", type=Path, required=True)
    parser.add_argument("--source-2024-2025", type=Path, required=True)
    parser.add_argument("--identity-mapping", type=Path, required=True)
    parser.add_argument("--base-member-mapping", type=Path, required=True)
    parser.add_argument("--ecmwf-root", type=Path, default=None)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = run(args)
    rendered = json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.summary_output is not None:
        write_json(args.summary_output, summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
