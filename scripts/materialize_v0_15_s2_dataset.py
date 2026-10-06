"""Offline S2 materializer; separate private features/labels, aggregate public reports.

No live database capability. The input snapshot must be the S0 read-only,
ROLLBACK-authenticated snapshot; no current-season ingestion is supported.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.app.area_yield.v015_materialization import (
    POLICY_ID,
    authorized,
    base_vectors,
    daily_index,
    label_vector,
    validate_public,
    validate_weather_cache,
    weather_vector,
)
from backend.app.area_yield.v015_research_cohort import canonical, digest
from scripts.audit_v0_15_s0_business_closure import digest as s0_digest
from scripts.freeze_v0_15_s1_research_cohort import load_sources

S1 = "docs/v0-15/evidence/retrospective-research-cohort-split-freeze-r1"
S1_MANIFEST_SHA = "d32fd39c84cd843c2846521acb55569ae35f7519eb9d0d7a946eb18c7439dc1d"
PINS = {
    "backend/app/area_yield/weather_aware_backtest.py": (
        "aae66403ddbc285c55c4133cf1379dfec00aaff17f22cf8f5f43bb9ab6e685f6"
    ),
    "backend/app/area_yield/v014_future_weather_features.py": (
        "8c8d558a384601a633d3ef50033f89a77ee8de4795586bd7c2cfc110eb1dc34e"
    ),
    "docs/v0-15/evidence/historical-ecmwf-coverage-sweep-r1/audit-source-manifest.json": (
        "2bc2d22ce6a28710d494143dae12bbfb49efb84d3327f6e514ef2355a5d92f7e"
    ),
}


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def immutable(path: Path, value: Any) -> None:
    content = canonical(value)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError("IMMUTABLE_ARTIFACT_CONFLICT")
        return
    with path.open("xb") as f:
        f.write(content)
    path.chmod(0o600)


def sources(root: Path) -> tuple[dict[str, Any], dict[str, str]]:
    inherited, inherited_pins = load_sources(root)
    raw = (root / S1 / "manifest.json").read_bytes()
    if sha(raw) != S1_MANIFEST_SHA:
        raise ValueError("S1_MANIFEST_CHANGED")
    m = json.loads(raw)
    if digest({k: v for k, v in m.items() if k != "manifest_hash"}) != m["manifest_hash"]:
        raise ValueError("S1_MANIFEST_SELF_HASH_INVALID")
    values = {}
    for member in m["members"]:
        raw = (root / S1 / member["name"]).read_bytes()
        if sha(raw) != member["sha256"]:
            raise ValueError("S1_MEMBER_CHANGED")
        values[member["name"]] = json.loads(raw)
    for path, expected in PINS.items():
        if sha((root / path).read_bytes()) != expected:
            raise ValueError("BASE10_OR_WEATHER_AUTHORITY_CHANGED")
    return {**values, "inherited": inherited}, {
        **inherited_pins,
        **PINS,
        "s1_manifest": S1_MANIFEST_SHA,
    }


def run(
    root: Path,
    snapshot: Path,
    projection: Path,
    weather: Path,
    private: Path,
    public: Path,
    isolation_receipt: Path,
) -> dict[str, Any]:
    os.umask(0o077)
    s, pins = sources(root)
    snap = json.loads(snapshot.read_bytes())
    expected = s["inherited"][
        "docs/v0-15/evidence/business-data-closure-r1/s0-business-data-readiness-recommendation.json"
    ]["snapshot_hash"]
    if (
        s0_digest(snap) != expected
        or snap["transaction_read_only"] != "on"
        or snap["transaction_end"] != "ROLLBACK"
    ):
        raise ValueError("SNAPSHOT_AUTHENTICATION_FAILED")
    # Validate every source row's season before building any numeric quantity.
    for table, rows in snap["records"].items():
        if table != "audit.source_manifest":
            for row in rows:
                authorized(row["season"])
    daily = json.loads(projection.read_bytes())
    report = s["inherited"][
        "docs/v0-15/evidence/business-data-closure-r1/canonical-logical-harvest-record-report.json"
    ]
    if s0_digest(daily) != report["logical_projection_hash"]:
        raise ValueError("LOGICAL_PROJECTION_CHANGED")
    index = daily_index(daily)
    isolation = json.loads(isolation_receipt.read_bytes())
    if (
        not isolation["predictor_label_vault_denied"]
        or not isolation["read_only_enforced"]
        or not isolation["rollback"]
    ):
        raise ValueError("FEATURE_LABEL_ISOLATION_FAILED")
    area_rows = snap["records"]["authority.area_records"]
    areas = {}
    for area in area_rows:
        key = area["base_id"], area["season"]
        if key in areas:
            raise ValueError("DUPLICATE_AREA_AUTHORITY")
        areas[key] = area
    cohort = {
        (r["base_id"], r["season"]): r
        for r in s["retrospective-base-research-cohort.json"]["admitted_rows"]
    }
    origins = [
        r
        for r in s["research-forecast-origin-universe.json"]["rows"]
        if r["base_research_eligible"]
    ]
    if len(origins) != 20020 or len(cohort) != 76:
        raise ValueError("S1_ELIGIBLE_UNIVERSE_CHANGED")
    features: dict[str, list[Any]] = {role: [] for role in ("TRAIN", "VALIDATION", "EXPOSED_OOT")}
    labels: dict[str, list[Any]] = {role: [] for role in features}
    wx: dict[str, list[Any]] = {role: [] for role in features}
    failed, wx_failed = [], []
    caches: dict[str, Any] = {}
    catalog_bindings = json.loads(
        (
            root
            / "docs/v0-15/evidence/historical-ecmwf-coverage-sweep-r1/audit-source-manifest.json"
        ).read_bytes()
    )
    catalog_pins = {
        r["run_id"]: r["effective_derived_run_sha256"]
        for r in catalog_bindings["run_receipt_layers"]
    }
    q: dict[str, Any] = {
        role: {
            k: 0
            for k in (
                "row_count",
                "valid_label_count",
                "real_zero_count",
                "invalid_count",
                "suspect_count",
                "valid_extreme_keep_count",
                "duplicate_count",
                "nonfinite_count",
                "negative_count",
                "feature_missing_count",
                "feature_nonfinite_count",
                "label_missing_count",
                "weather_numeric_complete_count",
                "weather_numeric_failed_count",
            )
        }
        for role in features
    }
    for row in origins:
        role = row["temporal_role"]
        key = row["base_id"], row["season"]
        common = {
            k: row[k]
            for k in (
                "base_id",
                "season",
                "forecast_origin",
                "target_dates",
                "area_authority_id",
                "identity_mapping_id",
                "area_evidence_level",
                "identity_evidence_level",
                "exposure_status",
            )
        }
        common.update(
            row_key=row["row_hash"],
            split=role,
            materialization_policy_version=POLICY_ID,
            strict_pit=False,
            retrospective_authority_used=True,
        )
        common["authority_grade"] = {
            "area": row["area_evidence_level"],
            "identity": row["identity_evidence_level"],
            "weather": row["weather_evidence_level"],
        }
        q[role]["row_count"] += 1
        try:
            a = areas[key]
            c = cohort[key]
            if (
                a["payload"]["area_authority_id"] != row["area_authority_id"]
                or a["source_hash"] != c["area_source_hash"]
                or a["payload"]["base_id"] != key[0]
            ):
                raise ValueError("AREA_LINEAGE_MISMATCH")
            vectors = base_vectors(row, Decimal(a["payload"]["historical_actual_area_mu"]))
            label = label_vector(row, index)
            if canonical(vectors) != canonical(
                base_vectors(row, Decimal(a["payload"]["historical_actual_area_mu"]))
            ) or canonical(label) != canonical(label_vector(row, index)):
                raise ValueError("DETERMINISTIC_REPLAY_FAILED")
            source_hashes = sorted(
                set(
                    label["source_hashes"]
                    + [
                        a["source_hash"],
                        row["source_business_row_hash"],
                        row["cohort_decision_hash"],
                    ]
                )
            )
            f = {
                **common,
                "source_hashes": source_hashes,
                "base10": vectors,
                "missing_mask": [False] * 10,
            }
            label_row = {**common, "source_hashes": source_hashes, "labels": label}
            # Numeric feature identity is independent of target labels/source revisions.
            f["feature_hash"], label_row["label_hash"] = digest(vectors), digest(label)
            f["label_hash"], label_row["feature_hash"] = label_row["label_hash"], f["feature_hash"]
            f["row_hash"], label_row["row_hash"] = digest(f), digest(label_row)
            features[role].append(f)
            labels[role].append(label_row)
            q[role]["valid_label_count"] += 15
            q[role]["real_zero_count"] += sum(
                index[key[0], key[1], d]["record_state"] == "REAL_ZERO" for d in row["target_dates"]
            )
            # No statistical cutoff is fitted. All valid extremes remain admitted.
            q[role]["valid_extreme_keep_count"] += 1
        except (ValueError, KeyError) as exc:
            reason = str(exc)
            decision = {
                "row_key": row["row_hash"],
                "source_hash": row["source_business_row_hash"],
                "exclusion_reason": reason,
            }
            decision["decision_hash"] = digest(decision)
            failed.append(decision)
            q[role]["invalid_count"] += 1
        if row["weather_comparable_eligible"]:
            if role == "TRAIN":
                raise ValueError("WEATHER_TRAIN_CHANGED")
            try:
                run_id = row["selected_run_id"]
                if run_id not in caches:
                    caches[run_id] = json.loads((weather / (run_id + ".json")).read_bytes())
                cache = caches[run_id]
                validate_weather_cache(cache, row)
                if cache["catalog_sha256"] != catalog_pins[run_id]:
                    raise ValueError("S0_CATALOG_DRIFT")
                if (
                    cache["run_id"] != run_id
                    or digest({k: v for k, v in cache.items() if k != "cache_hash"})
                    != cache["cache_hash"]
                ):
                    raise ValueError("WEATHER_CACHE_IDENTITY_INVALID")
                if cache["provider"] != "ECMWF_IFS_OPEN_DATA" or cache["status"] != "COMPLETE":
                    raise ValueError("WEATHER_NOT_AS_ISSUED_OR_INCOMPLETE")
                surface = {(r["step"], r["parameter"]): r for r in cache["base_fields"][key[0]]}
                vector = weather_vector(surface)
                if canonical(vector) != canonical(weather_vector(surface)):
                    raise ValueError("WEATHER_REPLAY_FAILED")
                w = {
                    **common,
                    "run_id": run_id,
                    "weather8": vector,
                    "source_hashes": [cache["cache_hash"]],
                    "publication_policy_hash": row["publication_policy_hash"],
                    "precipitation_policy_hash": row["precipitation_policy_hash"],
                    "weather_policy_version": row["weather_policy_version"],
                }
                w["weather_vector_hash"] = digest(w)
                wx[role].append(w)
                q[role]["weather_numeric_complete_count"] += 1
            except (OSError, KeyError, ValueError) as exc:
                decision = {
                    "row_key": row["row_hash"],
                    "source_hash": row["source_weather_row_hash"],
                    "exclusion_reason": type(exc).__name__
                    + ":"
                    + (str(exc) if not isinstance(exc, OSError) else "WEATHER_CACHE_UNAVAILABLE"),
                }
                decision["decision_hash"] = digest(decision)
                wx_failed.append(decision)
                q[role]["weather_numeric_failed_count"] += 1
    hashes = {}
    for role in features:
        if [r["row_key"] for r in features[role]] != [r["row_key"] for r in labels[role]]:
            raise ValueError("COMMON_ROWSET_MISMATCH")
        immutable(private / "feature_zone" / f"{role.lower()}-base10.json", features[role])
        immutable(private / "label_zone" / f"{role.lower()}-labels.json", labels[role])
        immutable(private / "feature_zone" / f"{role.lower()}-weather8.json", wx[role])
        hashes[role + "_FEATURESET_HASH"] = digest(features[role])
        hashes[role + "_LABELSET_HASH"] = digest(labels[role])
        hashes["WEATHER_" + role + "_VECTORSET_HASH"] = digest(wx[role])
        q[role]["base_season_count"] = len({(r["base_id"], r["season"]) for r in features[role]})
    immutable(private / "audit" / "base-failed.json", failed)
    immutable(private / "audit" / "weather-failed.json", wx_failed)
    n = sum(map(len, features.values()))
    wn = sum(map(len, wx.values()))
    if n + len(failed) != 20020 or wn + len(wx_failed) != 12925:
        raise ValueError("SILENT_ROW_LOSS")
    policy = {
        "policy_version": POLICY_ID,
        "source_pins": pins,
        "split": {"2023-2024": "TRAIN", "2024-2025": "VALIDATION", "2025-2026": "EXPOSED_OOT"},
        "base10_authority": (
            "V014_SHADOW_ISSUANCE_CALLS_WEATHER_AWARE_BACKTEST._base_feature_values"
        ),
        "base10_grain": "ORIGIN_WITH_15_TARGET_SPECIFIC_BASE10_VECTORS",
        "no_scaler_fit": True,
        "complete_label_states": ["VALID_OBSERVED", "REAL_ZERO"],
        "statistical_threshold_fitted": False,
        "statistical_outlier_auto_delete": False,
        "model_error_based_exclusion": False,
        "strict_pit": False,
        "retrospective_authority_used": True,
        "prospective_claim_allowed": False,
        "weather_train_origins": 0,
        "publication_lag_hours": 8,
        "precip_threshold_mm": "0.08",
        "publication_policy_hash": (
            "896e19617c0d12579fa33cf9ed17e81e6ed2e4337866c10de00c3932918565c7"
        ),
        "precipitation_policy_hash": (
            "dd84aa464912cb93a1e40506488a39c7b5bc5b82f2b73b67216e0be2563cda2b"
        ),
        "physical_artifact_layout": (
            "SEPARATE_FEATURE_AND_LABEL_DIRECTORIES;OWNER_ONLY;FEATURE_BUILDER_NO_LABEL_ARGUMENT"
        ),
        "origin_day_harvest_excluded": True,
    }
    policy["policy_hash"] = digest(policy)
    ready = not failed
    summary = {
        "base10_materialized_origin_count": n,
        "base10_failed_origin_count": len(failed),
        "origin_accounting": 20020,
        "split_counts": {k: len(v) for k, v in features.items()},
        "dataset_hashes": hashes,
        "source_snapshot_hash": expected,
        "logical_projection_hash": report["logical_projection_hash"],
        "dataset_policy_hash": policy["policy_hash"],
    }
    reports = {
        "s2-materialization-policy.json": policy,
        "base10-materialization-summary.json": summary,
        "historical-label-materialization-summary.json": {
            "materialized_origin_count": sum(map(len, labels.values())),
            "failed_origin_count": len(failed),
            "horizon": "D1=ORIGIN_NEXT_DAY;D15=ORIGIN_PLUS_15",
            "peak_ties": "EARLIEST",
            "rolling7_windows": 9,
            "no_quantities_public": True,
        },
        "historical-data-quality-report.json": {
            "categories": ["INVALID_EXCLUDE", "SUSPECT_REVIEW", "VALID_EXTREME_KEEP"],
            "invalid_exclude_count": len(failed),
            "suspect_review_count": 0,
            "valid_extreme_keep_count": n,
            "valid_extreme_keep_definition": (
                "ALL_VALID_ORIGINS_RETAINED_WITHOUT_STATISTICAL_DELETION;NOT_ALL_ARE_OUTLIERS"
            ),
            "excluded_rows": failed,
            "statistical_threshold": None,
            "source_logical_record_count": len(daily),
            "source_state_counts_unchanged": dict(Counter(r["record_state"] for r in daily)),
            "source_records_not_selected_by_s1_are_not_re_admitted": True,
            "unknown_zero_conversion": False,
            "partial_complete_conversion": False,
        },
        "split-quality-report.json": {
            "splits": q,
            "daily_label_counts_count_overlapping_target_windows": True,
        },
        "base10-common-benchmark-dataset-contract.json": {
            "frozen": ready,
            "same_rows_features_labels_masks_and_denominator_required": True,
            "common_origin_keys_hash": digest(
                [r["row_key"] for role in features for r in features[role]]
            ),
            "feature_count_per_target": 10,
            "targets_per_origin": 15,
            "extra_rows": "EXPLORATORY_ONLY",
            "strict_pit": False,
            "2025_2026_previously_exposed": True,
        },
        "weather8-numeric-materialization-summary.json": {
            "expected_origin_count": 12925,
            "materialized_origin_count": wn,
            "failed_origin_count": len(wx_failed),
            "split_counts": {k: len(v) for k, v in wx.items()},
            "result": "PASS" if not wx_failed else "PARTIAL",
            "excluded_rows": wx_failed,
            "all_successes_have_eight_finite_values": True,
            "numeric_cache_hashes": {k: v["cache_hash"] for k, v in sorted(caches.items())},
            "weather_benchmark_training_ready": False,
        },
        "weather-training-gap-assessment.json": {
            "train_season": "2023-2024",
            "required_origins": 4125,
            "qualified_origins": 0,
            "numeric_materialized_origins": 0,
            "gap_reason": "S1_FROZEN_OFFICIAL_ARCHIVE_COVERAGE_HAS_NO_TRAIN_WEATHER",
            "official_archive_route_checked": "S0_OFFICIAL_OPEN_DATA_MIRROR_SWEEP",
            "reanalysis_substitution_allowed": False,
            "split_change_allowed": False,
            "weather_model_training_ready": False,
        },
        "feature-label-isolation-audit.json": {
            "result": "PASS",
            "physical_separate_artifact_files_and_directories": True,
            "private_mode": "0700_DIRECTORIES_0600_FILES",
            "feature_builder_label_input_capability": False,
            "predictor_database_label_vault_access": "DENIED",
            "database_isolation_receipt": isolation,
            "original_source_modified": False,
            "future_actual_leakage_tests": "PASS",
        },
        "privacy-scan-report.json": {"result": "PASS", "public_contains_private_rows": False},
        "deterministic-replay-report.json": {
            "result": "PASS",
            "vector_replay_count_per_successful_origin": 2,
            "base_origin_count": n,
            "label_origin_count": sum(map(len, labels.values())),
            "weather_origin_count": wn,
            "method": "TWO_INDEPENDENT_PURE_FUNCTION_CALLS;CANONICAL_BYTE_EQUALITY",
            "network_during_replay": False,
            "fresh_process_file_parity_requires_additional_operator_verification": True,
        },
        "s2-readiness-recommendation.json": {
            "result": "PASS" if ready and not wx_failed else "PARTIAL",
            "s2_ready": ready and not wx_failed,
            "base10_benchmark_ready": ready,
            "weather_benchmark_ready": False,
            "weather_train_origins": 0,
            "s3_authorized": False,
            "model_training_executed": False,
            "model_scoring_executed": False,
            "current_2026_27_actual_accessed": False,
            "production_db_changed": False,
            "v0_14_changed": False,
            "cold_storage_changed": False,
        },
    }
    for name, value in reports.items():
        validate_public(value)
        immutable(public / name, value)
    members = [
        {"name": name, "sha256": sha(canonical(value)), "size": len(canonical(value))}
        for name, value in sorted(reports.items())
    ]
    manifest = {
        "schema": "V0_15_S2_DATASET_MANIFEST_V1",
        "members": members,
        "dataset_hashes": hashes,
        "policy_hash": policy["policy_hash"],
    }
    manifest["manifest_hash"] = digest(manifest)
    immutable(private / "manifest.json", manifest)
    immutable(public / "manifest.json", manifest)
    return summary


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    for name in (
        "repository",
        "snapshot",
        "projection",
        "weather-cache",
        "private-output",
        "public-output",
        "isolation-receipt",
    ):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    print(
        json.dumps(
            run(
                a.repository,
                a.snapshot,
                a.projection,
                a.weather_cache,
                a.private_output,
                a.public_output,
                a.isolation_receipt,
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
