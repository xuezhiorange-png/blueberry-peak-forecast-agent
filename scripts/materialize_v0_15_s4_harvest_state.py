"""Offline S4 materializer. Reads frozen historical sources, never target labels.

Outputs are immutable, private, owner-only. Public reports contain only counts,
contracts and hashes. No database, network, model fit or scoring capability.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.app.area_yield.formal_multi_season_validation import business_boundary
from backend.app.area_yield.v015_benchmark_custody import (
    DATASET_MANIFEST_HASH,
    FEATURE_HASHES,
    FrozenDataset,
    save,
    sha,
    validate_public,
)
from backend.app.area_yield.v015_harvest_state import (
    FEATURES,
    build_row,
    history_index,
    policy,
    read_artifact,
)
from backend.app.area_yield.v015_research_cohort import canonical, digest, origin_time
from scripts.audit_v0_15_s0_business_closure import digest as s0_digest

BASE_SHA = "6cf7555ce55ce0d163f5de7e306b36f21b73555d"
PROJECTION_HASH = "52df1531f95e933d91def40d490e5de6dfcb98c5bb42375d3a25bb0653c6363b"
COUNTS = {"TRAIN": 4125, "VALIDATION": 6028, "EXPOSED_OOT": 9867}
STRUCTURAL = {"TRAIN": 3705, "VALIDATION": 5412, "EXPOSED_OOT": 8775}


def common_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = [r["row_key"] for r in rows]
    if len(set(keys)) != len(keys):
        raise ValueError("DUPLICATE_ORIGIN_KEY")
    return [
        {"row_key": r["row_key"], "split": r["split"], "target_rows": 15}
        for r in sorted(rows, key=lambda r: r["row_key"])
        if r["harvest_state_complete"]
    ]


def mutation_checks(
    origin: dict[str, Any], index: dict[tuple[str, str, str], dict[str, Any]]
) -> dict[str, Any]:
    before = build_row(origin, index)
    if not before["harvest_state_complete"]:
        raise ValueError("MUTATION_PROOF_REQUIRES_COMPLETE_ORIGIN")
    cutoff = origin_time(origin["forecast_origin"]).date()
    end = business_boundary(origin["season"]).end
    results = {}
    for name, day in [
        ("ORIGIN_DAY", cutoff),
        ("D_PLUS_1", cutoff + timedelta(days=1)),
        ("D_PLUS_7", cutoff + timedelta(days=7)),
        ("D_PLUS_15", cutoff + timedelta(days=15)),
        ("SEASON_FINAL", end),
        ("FUTURE_SOURCE_HASH", cutoff + timedelta(days=1)),
        ("D_MINUS_1", cutoff - timedelta(days=1)),
    ]:
        key = origin["base_id"], origin["season"], day.isoformat()
        source = index[key]
        changed = dict(index)
        changed[key] = {**source, "quantity_kg": str(Decimal(source["quantity_kg"]) + 1)}
        if name == "FUTURE_SOURCE_HASH":
            changed[key] = {**source, "source_hashes": ["f" * 64]}
        if name == "D_MINUS_1":
            changed[key]["record_state"] = "VALID_OBSERVED"
        after = build_row(origin, changed)
        same = {
            "vector_hash_unchanged": before["harvest_state_feature_hash"]
            == after["harvest_state_feature_hash"],
            "row_hash_unchanged": before["row_hash"] == after["row_hash"],
            "artifact_bytes_unchanged": canonical([before]) == canonical([after]),
        }
        if name == "D_MINUS_1":
            if any(same.values()) or not all(
                Decimal(after["harvest_state_v1"][f]) == Decimal(before["harvest_state_v1"][f]) + 1
                for f in FEATURES
            ):
                raise ValueError("PAST_ACTUAL_POSITIVE_SENSITIVITY_FAILED")
            results[name] = {"all_four_values_changed": True, "hashes_and_bytes_changed": True}
        else:
            if not all(same.values()):
                raise ValueError("FUTURE_ACTUAL_LEAKAGE")
            results[name] = same
    return results


def run(dataset: Path, projection: Path, private: Path, public: Path) -> dict[str, Any]:
    os.umask(0o077)
    if private.resolve() == dataset.resolve() or dataset.resolve() in private.resolve().parents:
        raise ValueError("S2_ARTIFACT_WRITE_DENIED")
    repository = Path(__file__).resolve().parents[1]
    if repository in private.resolve().parents or private.resolve() == repository:
        raise ValueError("PRIVATE_OUTPUT_IN_PUBLIC_REPOSITORY_DENIED")
    daily = json.loads(projection.read_bytes())
    index = history_index(daily)  # Reject entire current-season envelope before quantity access.
    if s0_digest(daily) != PROJECTION_HASH or len(daily) != 33033:
        raise ValueError("HISTORICAL_SOURCE_DRIFT")
    del daily
    frozen = FrozenDataset(dataset, "FINAL")
    rows: dict[str, list[dict[str, Any]]] = {}
    exclusions: list[dict[str, Any]] = []
    lineage: list[dict[str, Any]] = []
    common: list[dict[str, Any]] = []
    split_reports: dict[str, Any] = {}
    mutation_reports: dict[str, Any] = {}
    private_members: dict[str, Any] = {}
    for split, expected in COUNTS.items():
        features = frozen.features(split)  # Feature files only; no labels/Weather8 are opened.
        rows[split] = [build_row(r, index) for r in features]
        if len(rows[split]) != expected:
            raise ValueError("BASE10_ORIGIN_ACCOUNTING_DRIFT")
        rows[split].sort(key=lambda r: r["row_key"])
        selected = common_rows(rows[split])
        common.extend(selected)
        split_reports[split] = {
            "base10_origin_count": expected,
            "base_season_count": len({(r["base_id"], r["season"]) for r in features}),
            "harvest_state_complete_origin_count": len(selected),
            "harvest_state_excluded_origin_count": expected - len(selected),
            "complete_target_row_count": len(selected) * 15,
            "incomplete_window_origin_counts": {
                f: sum(
                    r["audit"][f.replace("_harvest_kg", "_missing_count")] > 0 for r in rows[split]
                )
                for f in FEATURES
            },
            "expected_structural_count": STRUCTURAL[split],
            "structural_counts_match": len(selected) == STRUCTURAL[split],
        }
        sample = next(r for r in rows[split] if r["harvest_state_complete"])
        mutation_reports[split] = mutation_checks(sample, index)
        for row in rows[split]:
            lineage.append({"row_key": row["row_key"], "source_hashes": row["source_hashes"]})
            if not row["harvest_state_complete"]:
                exclusions.append(
                    {
                        "row_key": row["row_key"],
                        "split": split,
                        "reason_codes": row["exclusion_reasons"],
                        "audit": row["audit"],
                        "decision_hash": digest(row),
                    }
                )
        name = "feature_zone/harvest-state-v1-" + split.lower().replace("_", "-") + ".json"
        save(private / name, rows[split])
        file_hash = sha((private / name).read_bytes())
        read_artifact(private / name, file_hash)
        private_members[name] = {"sha256": file_hash, "row_count": len(rows[split])}
        del features
    common.sort(key=lambda r: (r["split"], r["row_key"]))
    for name, value in {
        "audit/harvest-state-exclusions.json": exclusions,
        "audit/harvest-state-source-lineage.json": lineage,
        "audit/harvest-state-common-rowset.json": common,
    }.items():
        save(private / name, value)
        private_members[name] = {
            "sha256": sha((private / name).read_bytes()),
            "row_count": len(value),
        }
    total = sum(r["harvest_state_complete_origin_count"] for r in split_reports.values())
    summary = {
        "base10_total_origin_count": sum(COUNTS.values()),
        "harvest_state_complete_origin_count": total,
        "harvest_state_excluded_origin_count": len(exclusions),
        "origin_accounting": total + len(exclusions),
        "structural_counts_match": all(
            r["structural_counts_match"] for r in split_reports.values()
        ),
        "incomplete_window_origin_counts": {
            f: sum(r["incomplete_window_origin_counts"][f] for r in split_reports.values())
            for f in FEATURES
        },
        "featureset_hashes": {
            k: v["sha256"] for k, v in private_members.items() if k.startswith("feature_zone/")
        },
        "common_rowset_hash": digest(common),
        "policy_hash": digest(policy()),
    }
    source = {
        "base_develop_sha": BASE_SHA,
        "s2_manifest_hash": DATASET_MANIFEST_HASH,
        "s2_feature_file_hashes": FEATURE_HASHES,
        "logical_projection_hash": PROJECTION_HASH,
        "historical_logical_record_count": 33033,
        "seasons": ["2023-2024", "2024-2025", "2025-2026"],
        "frozen_business_boundaries": {
            season: {
                "start": business_boundary(season).start.isoformat(),
                "end": business_boundary(season).end.isoformat(),
                "authority_hash": business_boundary(season).authority_hash,
            }
            for season in ("2023-2024", "2024-2025", "2025-2026")
        },
        "source_files_unchanged": True,
        "execution_source_sha256": {
            name: sha((repository / name).read_bytes())
            for name in (
                "scripts/materialize_v0_15_s4_harvest_state.py",
                "backend/app/area_yield/v015_harvest_state.py",
                "backend/app/area_yield/formal_multi_season_validation.py",
            )
        },
        "strict_pit": False,
        "historical_available_at_proven": False,
    }
    rowset = {
        "common_rowset_hash": digest(common),
        "split_counts": {
            k: v["harvest_state_complete_origin_count"] for k, v in split_reports.items()
        },
        "target_rows_per_origin": 15,
        "base10_origins_preserved": 20020,
        "same_keys_labels_horizon_denominator_required": True,
        "only_model_input_difference": "FOUR_HARVEST_STATE_V1_FEATURES",
        "s3_metrics_direct_comparison_allowed": False,
        "base10_comparator_refit_on_common_rows_required": True,
        "model_family_selected": False,
    }
    readiness = {
        "s4_materialization_complete": True,
        "harvest_state_benchmark_ready": all(
            r["harvest_state_complete_origin_count"] > 0 for r in split_reports.values()
        ),
        "fresh_process_replay_required_for_pass": True,
        "model_training_executed": False,
        "model_scoring_executed": False,
        "s5_authorized": False,
        "strict_pit": False,
        "authority_grade": "RETROSPECTIVE_DATE_BOUND",
        "prospective_claim_allowed": False,
    }
    reports = {
        "harvest-state-definition-contract.json": policy(),
        "harvest-state-source-authority.json": source,
        "harvest-state-coverage-summary.json": summary,
        "harvest-state-split-coverage.json": split_reports,
        "harvest-state-exclusion-reasons.json": {
            "excluded_origins": len(exclusions),
            "reason_counts": dict(
                sorted(
                    Counter(reason for row in exclusions for reason in row["reason_codes"]).items()
                )
            ),
            "invalid_base10_rows": 0,
            "base10_dataset_modified": False,
        },
        "harvest-state-common-rowset-contract.json": rowset,
        "harvest-state-leakage-test-report.json": {
            "test_kind": "REAL_HISTORICAL_ORIGIN_MUTATION_ONE_COMPLETE_ORIGIN_PER_SPLIT",
            "split_cases": {
                k: {n: v for n, v in r.items() if n != "D_MINUS_1"}
                for k, r in mutation_reports.items()
            },
            "result": "PASS",
        },
        "harvest-state-positive-sensitivity-report.json": {
            "split_cases": {k: r["D_MINUS_1"] for k, r in mutation_reports.items()},
            "result": "PASS",
        },
        "harvest-state-feature-label-isolation-audit.json": {
            "feature_schema_reader_validation": "PASS",
            "label_artifacts_opened": False,
            "feature_zone_has_daily_details": False,
            "feature_zone_has_target_hashes": False,
            "historical_source_is_authorized_materializer_input_not_predictor_artifact": True,
            "feature_zone_has_only_four_model_values_and_past_lineage": True,
            "database_privileges_changed": False,
        },
        "privacy-scan-report.json": {
            "public_reports_scan": "PASS",
            "private_feature_rows_committed": False,
        },
        "s4-readiness-recommendation.json": readiness,
    }
    for name, report_value in reports.items():
        validate_public(report_value)
        save(public / name, report_value)
    members = {name: sha(canonical(value)) for name, value in sorted(reports.items())}
    manifest = {
        "schema": "V0_15_S4_HARVEST_STATE_MANIFEST_V1",
        "policy_hash": digest(policy()),
        "source": source,
        "public_members": members,
        "private_members": private_members,
    }
    manifest["manifest_hash"] = digest(manifest)
    validate_public(manifest)
    save(private / "manifest.json", manifest)
    save(public / "manifest.json", manifest)
    return summary


def replay(first: Path, second: Path, public: Path) -> None:
    a = {str(p.relative_to(first)): sha(p.read_bytes()) for p in first.rglob("*.json")}
    b = {str(p.relative_to(second)): sha(p.read_bytes()) for p in second.rglob("*.json")}
    if a != b or not a:
        raise ValueError("FRESH_PROCESS_REPLAY_FAILED")
    value = {
        "result": "PASS",
        "independent_process_count": 2,
        "private_member_count": len(a),
        "same_rows_exclusions_order_bytes_hashes": True,
        "file_hash_manifest_hash": digest(a),
    }
    validate_public(value)
    save(public / "deterministic-replay-report.json", value)
    manifest = json.loads((public / "manifest.json").read_bytes())
    # Original materialization manifest remains immutable. Supplement binds it.
    save(
        public / "verification-manifest.json",
        {
            "materialization_manifest_hash": manifest["manifest_hash"],
            "replay_report_sha256": sha(canonical(value)),
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    materialize = sub.add_parser("materialize")
    for name in ("dataset", "projection", "private", "public"):
        materialize.add_argument("--" + name, type=Path, required=True)
    verify = sub.add_parser("verify-replay")
    for name in ("first", "second", "public"):
        verify.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if args.command == "materialize":
        print(
            json.dumps(
                run(args.dataset, args.projection, args.private, args.public), sort_keys=True
            )
        )
    else:
        replay(args.first, args.second, args.public)
        print("FRESH_PROCESS_REPLAY=PASS")


if __name__ == "__main__":
    main()
