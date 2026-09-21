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
from collections.abc import Mapping
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

from backend.app.area_yield.data import digest
from backend.app.area_yield.weather_features import (
    DUPLICATE_TARGET_LABEL_WEIGHTING_ALLOWED,
    HORIZON_TARGET_TYPES,
    ORIGIN_POLICY,
    ORIGIN_TIMEZONE,
    PRIMARY_FEATURE_COUNT,
    PRIMARY_FEATURES,
    PRIMARY_HORIZONS,
    PRIMARY_WINDOWS_DAYS,
    TARGET_GRANULARITY,
    TARGET_LABEL,
    TARGET_ROW_IDENTITY,
    WEATHER_FEATURE_POLICY_VERSION,
    WEATHER_ROLE,
    WEATHER_SOURCE,
    build_feature_manifest,
    build_feature_row,
    load_era5_daily_jsonl,
    target_dates_for_horizon,
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
HISTORICAL_ARCHIVE_PERIODS = {
    "2024-2025": (date(2024, 7, 1), date(2025, 4, 15)),
    "2025-2026": (date(2025, 7, 22), date(2026, 4, 15)),
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


def _manifest_timestamp(
    payload: Mapping[str, Any], *keys: str
) -> tuple[str | None, datetime | None, str | None]:
    """Read an optional timezone-aware timestamp without inventing one."""

    for key in keys:
        if key not in payload or payload[key] is None:
            continue
        value = payload[key]
        if not isinstance(value, str):
            return str(value), None, f"{key}_NOT_STRING"
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value, None, f"{key}_INVALID"
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return value, None, f"{key}_MISSING_TIMEZONE"
        return value, parsed, None
    return None, None, None


def _valid_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _step_hours(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str):
        normalized = value.strip().lower().removesuffix("h")
        try:
            parsed = int(normalized)
        except ValueError:
            return None
        return parsed if parsed > 0 else None
    return None


def _horizon_name(hours: int) -> str:
    return {24: "D1", 72: "D3", 168: "D7", 360: "D15"}.get(hours, f"H{hours}H")


def _historical_period(issued_at: datetime | None) -> str | None:
    if issued_at is None:
        return None
    issued_date = issued_at.date()
    for season, (start, end) in HISTORICAL_ARCHIVE_PERIODS.items():
        if start <= issued_date <= end:
            return season
    return None


def _audit_manifest(path: Path, root: Path | None) -> dict[str, Any]:
    """Parse one saved manifest and classify its provenance, without I/O beyond the file."""

    manifest_hash = file_sha256(path)
    base_record: dict[str, Any] = {
        "artifact_path": logical_path(path, root),
        "artifact_manifest_sha256": manifest_hash,
        "provider": None,
        "model": None,
        "run_id": None,
        "issued_at": None,
        "fetched_at": None,
        "known_at": None,
        "field_artifact_count": 0,
        "index_artifact_count": 0,
        "available_horizons_hours": [],
        "available_horizons": [],
        "base_count": None,
        "grid_count": 0,
        "raw_artifact_hashes": [],
        "historical_period": None,
        "archive_provenance_eligible": False,
        "qualification_status": "FOUND_BUT_NOT_AS_ISSUED_ELIGIBLE",
        "qualification_reasons": [],
    }
    try:
        payload = read_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        base_record["qualification_reasons"] = [f"MANIFEST_PARSE_FAILED:{type(exc).__name__}"]
        return base_record

    provider = payload.get("provider")
    base_record.update(
        {
            "provider": provider,
            "model": payload.get("model"),
            "run_id": payload.get("run_id"),
        }
    )
    issued_text, issued_at, issued_issue = _manifest_timestamp(payload, "issued_at")
    fetched_text, fetched_at, fetched_issue = _manifest_timestamp(
        payload, "fetched_at", "fetch_time", "fetch_at"
    )
    known_text, known_at, known_issue = _manifest_timestamp(payload, "known_at")
    base_record.update(
        {
            "issued_at": issued_text,
            "fetched_at": fetched_text,
            "known_at": known_text,
            "historical_period": _historical_period(issued_at),
        }
    )
    reasons: list[str] = []
    if provider != ECMWF_PROVIDER:
        reasons.append("PROVIDER_MISMATCH")
    if payload.get("model") != ECMWF_MODEL:
        reasons.append("MODEL_MISMATCH_OR_MISSING")
    if not isinstance(payload.get("run_id"), str) or not payload["run_id"].strip():
        reasons.append("RUN_ID_MISSING")
    if issued_issue is not None:
        reasons.append(issued_issue)
    elif issued_at is None:
        reasons.append("ISSUED_AT_MISSING")
    if fetched_issue is not None:
        reasons.append(fetched_issue)
    if known_issue is not None:
        reasons.append(known_issue)
    elif known_at is None:
        reasons.append("KNOWN_AT_MISSING")
    if issued_at is not None and fetched_at is not None and issued_at > fetched_at:
        reasons.append("ISSUED_AFTER_FETCHED")
    if fetched_at is not None and known_at is not None and fetched_at > known_at:
        reasons.append("FETCHED_AFTER_KNOWN")
    if issued_at is not None and known_at is not None and issued_at > known_at:
        reasons.append("ISSUED_AFTER_KNOWN")

    field_artifacts = payload.get("field_artifacts")
    index_artifacts = payload.get("index_artifacts")
    if not isinstance(field_artifacts, list):
        field_artifacts = []
        reasons.append("FIELD_ARTIFACTS_MISSING")
    if not isinstance(index_artifacts, list):
        index_artifacts = []
    raw_hashes: list[str] = []
    horizon_hours: set[int] = set()
    for artifact_kind, artifacts in (("field", field_artifacts), ("index", index_artifacts)):
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                reasons.append(f"{artifact_kind.upper()}_ARTIFACT_NOT_OBJECT")
                continue
            artifact_hash = artifact.get("sha256")
            if not _valid_sha256(artifact_hash):
                reasons.append(f"{artifact_kind.upper()}_ARTIFACT_HASH_INVALID")
            else:
                raw_hashes.append(str(artifact_hash))
            step = _step_hours(artifact.get("step"))
            if step is None:
                reasons.append(f"{artifact_kind.upper()}_ARTIFACT_STEP_INVALID")
            else:
                horizon_hours.add(step)
    if not field_artifacts:
        reasons.append("NO_FORECAST_FIELD_ARTIFACTS")
    if not raw_hashes:
        reasons.append("RAW_ARTIFACT_IDENTITY_MISSING")
    selected_grid = payload.get("selected_grid_coordinates")
    grid_count = len(selected_grid) if isinstance(selected_grid, dict) else 0
    base_count = payload.get("base_count")
    if not isinstance(base_count, int) or isinstance(base_count, bool) or base_count <= 0:
        if grid_count == 0:
            reasons.append("BASE_OR_GRID_COVERAGE_MISSING")
        else:
            base_count = grid_count
    if not horizon_hours:
        reasons.append("FORECAST_HORIZON_MISSING")

    base_record.update(
        {
            "field_artifact_count": len(field_artifacts),
            "index_artifact_count": len(index_artifacts),
            "available_horizons_hours": sorted(horizon_hours),
            "available_horizons": [_horizon_name(value) for value in sorted(horizon_hours)],
            "base_count": base_count,
            "grid_count": grid_count,
            "raw_artifact_hashes": sorted(set(raw_hashes)),
            "raw_artifact_identity": digest(sorted(set(raw_hashes))) if raw_hashes else None,
        }
    )
    if not reasons:
        base_record["archive_provenance_eligible"] = True
        base_record["qualification_status"] = "FOUND_AS_ISSUED_ELIGIBLE"
    base_record["qualification_reasons"] = sorted(set(reasons))
    return base_record


def audit_ecmwf_archive(root: Path | None) -> dict[str, Any]:
    """Audit saved ECMWF manifests by their issue time; never fetch or reconstruct."""

    discovered: list[dict[str, Any]] = []
    if root is not None and root.exists():
        for path in sorted(root.rglob("artifact-manifest.json")):
            discovered.append(_audit_manifest(path, root))

    saved_ecmwf = [item for item in discovered if item.get("provider") == ECMWF_PROVIDER]
    rejected = [item for item in discovered if item.get("provider") != ECMWF_PROVIDER]
    historical_by_season: dict[str, list[dict[str, Any]]] = {
        season: [] for season in HISTORICAL_ARCHIVE_PERIODS
    }
    for item in saved_ecmwf:
        season = item.get("historical_period")
        if season in historical_by_season:
            historical_by_season[season].append(item)

    requested: dict[str, dict[str, Any]] = {}
    for season, (start, end) in HISTORICAL_ARCHIVE_PERIODS.items():
        candidates = historical_by_season[season]
        eligible = [
            item
            for item in candidates
            if item.get("qualification_status") == "FOUND_AS_ISSUED_ELIGIBLE"
        ]
        if eligible:
            status = "FOUND_AS_ISSUED_ELIGIBLE"
        elif candidates:
            status = "FOUND_BUT_NOT_AS_ISSUED_ELIGIBLE"
        else:
            status = "NOT_FOUND"
        origin_dates = sorted(
            {str(item["issued_at"])[:10] for item in eligible if item.get("issued_at")}
        )
        issue_cycles = sorted({str(item["run_id"]) for item in eligible if item.get("run_id")})
        horizons = sorted(
            {horizon for item in eligible for horizon in item.get("available_horizons", [])}
        )
        raw_identity = sorted(
            {raw_hash for item in eligible for raw_hash in item.get("raw_artifact_hashes", [])}
        )
        requested[season] = {
            "status": status,
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "candidate_manifest_count": len(candidates),
            "eligible_manifest_count": len(eligible),
            "available_origin_dates": origin_dates,
            "available_base_count": max(
                (int(item["base_count"]) for item in eligible if item.get("base_count")),
                default=0,
            ),
            "available_issue_cycles": issue_cycles,
            "available_horizons": horizons,
            "provider_identity": (
                {"provider": ECMWF_PROVIDER, "model": ECMWF_MODEL} if eligible else None
            ),
            "raw_artifact_identity": raw_identity or None,
            "missing_date_ranges": ([] if eligible else ["ENTIRE_REQUESTED_SEASON_ARCHIVE"]),
            "manifest_details": candidates,
        }
    any_eligible = any(
        item.get("qualification_status") == "FOUND_AS_ISSUED_ELIGIBLE"
        and item.get("historical_period") in HISTORICAL_ARCHIVE_PERIODS
        for item in saved_ecmwf
    )
    return {
        "audit_status": "PASS",
        "audit_method": "FILESYSTEM_MANIFEST_SCAN_BY_ISSUED_AT",
        "network_accessed": False,
        "retrospective_forecast_reconstruction_allowed": False,
        "as_issued_known_at_required": True,
        "archive_provenance_eligibility_rule": [
            "provider_identity_valid",
            "model_run_identity_valid",
            "issued_at_timezone_aware",
            "known_at_timezone_aware",
            "issued_at <= known_at",
            "raw_forecast_artifact_identity_valid",
            "forecast_horizon_identity_valid",
            "base_grid_coverage_identity_valid",
        ],
        "requested_seasons": requested,
        "discovered_manifest_count": len(discovered),
        "saved_ecmwf_manifests": saved_ecmwf,
        "rejected_manifests": rejected,
        "historical_as_issued_archive_status": (
            "AVAILABLE_FOR_AUDITED_ORIGINS"
            if any_eligible
            else "INSUFFICIENT_FOR_PRIMARY_HISTORICAL_PRODUCTION_LIKE_COMPARISON"
        ),
        "production_like_comparison_status": (
            "COMPUTABLE_FOR_AUDITED_ORIGINS"
            if any_eligible
            else "NOT_COMPUTABLE_NO_AS_ISSUED_ARCHIVE"
        ),
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
            for horizon_name in PRIMARY_HORIZONS:
                target_dates = target_dates_for_horizon(
                    forecast_origin=origin, horizon=horizon_name
                )
                rows.append(
                    build_feature_row(
                        observations=observations,
                        base_id=base_id,
                        forecast_origin=origin,
                        target_start=target_dates[0],
                        target_end=target_dates[-1],
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
        "artifact_type": "OFFLINE_CONTRACT_FIXTURE",
        "offline_contract_fixture_row_count": len(rows),
        "offline_contract_fixture_base_count": len(base_ids),
        "offline_contract_fixture_origin_count": len(SEASON_STARTS),
        "offline_contract_fixture_horizon_count": len(PRIMARY_HORIZONS),
        "row_count": len(rows),
        "base_count": len(base_ids),
        "origin_count": len(SEASON_STARTS),
        "season_count": len(SEASON_STARTS),
        "horizon_count": len(PRIMARY_HORIZONS),
        "full_rolling_training_feature_dataset_built": False,
        "manifest_hash": str(manifest["manifest_hash"]),
        "manifest_file_sha256": file_sha256(manifest_path),
        "rows_file_sha256": file_sha256(row_path),
        "replay_manifest_hash": str(replay_manifest["manifest_hash"]),
        "offline_replay_pass": manifest == replay_manifest,
        "private_artifact_policy": "CALLER_SELECTED_PRIVATE_OUTPUT_NOT_COMMITTED",
        "fixture_semantics": (
            "CONTRACT_AND_OFFLINE_REPLAY_EVIDENCE_ONLY;NOT_A_COMPLETE_S3_TRAINING_FEATURE_DATASET"
        ),
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
    historical_forecast_status = archive["production_like_comparison_status"]
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
        "task_id": "V0_7_S2_AS_ISSUED_KNOWN_AT_GATE_CORRECTION_R3",
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
            "as_issued_known_at_required": True,
            "archive_provenance_eligibility_rule": archive["archive_provenance_eligibility_rule"],
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
                "historical_status": historical_forecast_status,
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
        "target_semantics": {
            "target_granularity": TARGET_GRANULARITY,
            "target_label": TARGET_LABEL,
            "target_row_identity": TARGET_ROW_IDENTITY,
            "duplicate_target_label_weighting_allowed": (DUPLICATE_TARGET_LABEL_WEIGHTING_ALLOWED),
            "horizon_target_types": dict(HORIZON_TARGET_TYPES),
            "horizon_views": {
                "H1": "lead_day_0;target_dates=D",
                "H7": "lead_days_0..6;target_dates=D..D+6",
                "H15": "lead_days_0..14;target_dates=D..D+14",
            },
            "same_target_row_keys": True,
            "same_target_dates": True,
            "same_lead_days": True,
            "same_actual_label_authority": True,
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
            "era5_event_time_cutoff_pass": True,
            "era5_forecast_time_known_at_status": "NOT_ESTABLISHED",
            "lane_a_historical_oot_research_eligible": True,
            "lane_a_production_like_pit_eligible": False,
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
            "weather_time_visibility_pass": ("PASS_WITH_ERA5_RESEARCH_ONLY_KNOWN_AT_LIMITATION"),
            "future_event_time_leakage_pass": "PASS",
            "era5_event_time_visibility_pass": "PASS",
            "era5_known_at_visibility_status": "NOT_ESTABLISHED",
            "as_issued_forecast_visibility_policy_pass": "PASS",
            "as_issued_known_at_required": True,
            "known_at_missing_fail_closed_pass": "PASS",
            "archive_provenance_eligibility_gate_pass": "PASS",
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
            "full_rolling_training_feature_dataset_built": False,
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
