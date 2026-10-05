"""Metadata-only intersection audit; no label, database or server capability."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from scripts.audit_v0_15_s0_existing_assets import validate_public

TASK = "V0_15_S0_STRICT_PIT_REPLAY_COHORT_CLOSURE_R1"
PARENT = "fe6b1310e39505c835f06ec6b1302b3eadcad533"
BUSINESS = "docs/v0-15/evidence/business-data-closure-r1"
WEATHER = "docs/v0-15/evidence/precipitation-packing-policy-closure-r1"
POLICY = {
    "id": "V0_15_S0_EVIDENCE_BOUND_REPLAY_INTERSECTION_R1",
    "candidate_scope": "ONLY_PARENT_39_FULL_WEATHER_BASE_SEASONS",
    "area": "A direct contemporaneous evidence or B separately supported frozen assumption",
    "identity": "STRICT contemporaneous binding or separately supported frozen ASSUMED binding",
    "labels": "All required business-window days VALID_OBSERVED or authorized REAL_ZERO",
    "tier_b_area_or_identity_assumption_instantiated": False,
    "weather_grade": "TIER_B_PUBLICATION_PLUS_INDEX_COMPLETE_PLUS_REAL_TP_ENDPOINTS",
    "all_eight_numeric_features_reconstructed": False,
    "new_blind_test": "Previously consumed benchmark does not become pristine by resealing",
    "target_lead_offset_selected": False,
    "s1_authorized": False,
}


def encoded(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def classify_label(row: dict[str, Any]) -> str:
    counts = [
        row[k]
        for k in (
            "unknown_count",
            "partial_subtotal_count",
            "missing_count",
            "conflict_count",
            "invalid_count",
        )
    ]
    if any(not isinstance(n, int) or isinstance(n, bool) or n < 0 for n in counts):
        raise ValueError("INVALID_STATE_COUNT")
    expected = (
        date.fromisoformat(row["target_end_date"]) - date.fromisoformat(row["target_start_date"])
    ).days + 1
    if expected <= 0 or row["logical_record_count"] > expected or counts[3] or counts[4]:
        return "LABEL_UNUSABLE_FOR_PEAK_SCORING"
    if any(counts) or row["logical_record_count"] != expected:
        return "LABEL_PARTIAL"
    return "LABEL_COMPLETE"


def intersect(area: str, identity: str, label: str) -> tuple[bool, list[str]]:
    reasons = []
    if area not in {"A", "B"}:
        reasons.append("AREA_PIT_UNPROVEN")
    if identity not in {"STRICT", "ASSUMED_FROZEN"}:
        reasons.append("IDENTITY_PIT_UNPROVEN")
    if label != "LABEL_COMPLETE":
        reasons.append("LABEL_WINDOW_INCOMPLETE")
    return not reasons, reasons


def generate(repo: Path, output: Path) -> None:
    if output.exists() and any(output.iterdir()):
        raise ValueError("IMMUTABLE_OUTPUT_EXISTS")
    source_receipts: dict[str, Any] = {}

    def source(path: str) -> bytes:
        data = (repo / path).read_bytes()
        original = subprocess.check_output(["git", "show", f"{PARENT}:{path}"], cwd=repo)
        if data != original:
            raise ValueError("PINNED_SOURCE_CHANGED")
        source_receipts[path] = {"sha256": sha(data), "size": len(data)}
        return data

    def load(path: str) -> Any:
        return json.loads(source(path))

    business_manifest = load(f"{BUSINESS}/report-manifest.json")
    for name, expected in business_manifest["files"].items():
        if sha(source(f"{BUSINESS}/{name}")) != expected:
            raise ValueError("BUSINESS_MANIFEST_DRIFT")
    weather_manifest = load(f"{WEATHER}/manifest.json")
    for member in weather_manifest["members"]:
        if sha(source(f"{WEATHER}/{member['name']}")) != member["sha256"]:
            raise ValueError("WEATHER_MANIFEST_DRIFT")
    weather = load(f"{WEATHER}/pit-weather-coverage-finalization.json")
    full = sorted(
        [r for r in weather["base_season_rows"] if r["status"] == "FULL_WEATHER_COVERAGE"],
        key=lambda r: (r["base_id"], r["season"]),
    )
    keys = {(r["base_id"], r["season"]) for r in full}
    if len(full) != 39 or len(keys) != 39 or any(s != "2025-2026" for _, s in keys):
        raise ValueError("FROZEN_39_UNIVERSE_CHANGED")
    prior_matrix = load(f"{BUSINESS}/base-season-training-readiness-matrix.json")
    business_rows = {(r["base_id"], r["season"]): r for r in prior_matrix["rows"]}
    area_rows = {
        (r["base_id"], r["season"]): r
        for r in load(f"{BUSINESS}/area-pit-evidence-reclassification.json")["rows"]
    }
    identities = load(f"{BUSINESS}/identity-authority-closure-report.json")["rows"]
    load(f"{BUSINESS}/execution-verification-receipt.json")
    # Inspect fixed historical Git lineage, not wall-clock mtime or moving main.
    historical_sources = [
        "configs/v0_5_base_reference_registry_v1.json",
        "configs/v0_5_area_forecast_experimental_prior_history_v1.json",
        "configs/v0_8_s4_three_season_area_authority_r1.json",
        "docs/v0-8/evidence/s1-cross-season-identity-authority-application-and-canonical-dataset-rebuild-r1.json",
        "docs/v0-8/evidence/s4-user-confirmed-three-season-area-authority-application-r1.json",
        "docs/v0-8/s7/training-season-source-identity-closure-r1.md",
        "docs/v0-8/r2c/frozen-shrinkage-model-and-2025-2026-benchmark-replay-r1.md",
    ]
    git_lineage = []
    for path in historical_sources:
        source(path)
        history = subprocess.check_output(
            ["git", "log", PARENT, "--reverse", "--format=%H %aI %cI", "--", path],
            cwd=repo,
            text=True,
        ).splitlines()
        git_lineage.append(
            {"source": path, "history": history, "commit_time_is_historical_available_at": False}
        )
    origin_rows = load(f"{WEATHER}/historical-base-season-origin-weather-pit-matrix.json")["rows"]
    result_rows, gaps, area_audit, identity_audit, label_audit = [], [], [], [], []
    for candidate in full:
        key = candidate["base_id"], candidate["season"]
        business_row, area = business_rows[key], area_rows[key]
        if (
            any(
                area.get(field) is not None
                for field in (
                    "historical_available_at",
                    "created_at",
                    "updated_at",
                    "historical_ingested_at",
                    "revision_time",
                )
            )
            or area["tier"] != "PIT_EVIDENCE_TIER_C_RETROSPECTIVE"
        ):
            raise ValueError("NEW_AREA_TEMPORAL_EVIDENCE_REQUIRES_REVIEW")
        bound = [r for r in identities if (r["base_id"], r["season"]) == key]
        if not bound or any(r["strict_pit_authority"] or r["assumed_pit_authority"] for r in bound):
            raise ValueError("NEW_OR_MISSING_IDENTITY_EVIDENCE_REQUIRES_REVIEW")
        identity = (
            "ACCEPTED_RETROSPECTIVE_PIT_UNPROVEN"
            if all(r["closure_status"] == "ACCEPTED_RETROSPECTIVE" for r in bound)
            else "UNRESOLVED_BINDING"
        )
        origins = [r for r in origin_rows if (r["base_id"], r["season"]) == key]
        if (
            len(origins) != candidate["required_origin_count"]
            or not all(r["weather8_coverage_complete"] for r in origins)
            or len({r["forecast_origin"] for r in origins}) != len(origins)
        ):
            raise ValueError("FULL_WEATHER_ORIGIN_DRIFT")
        label = classify_label(business_row)
        ready, reasons = intersect("C", identity, label)
        item = {
            "base_id": key[0],
            "season": key[1],
            "weather_pit_status": POLICY["weather_grade"],
            "area_pit_tier": "C",
            "identity_status": identity,
            "label_completeness": label,
            "strict_replay_ready": ready,
            "blocking_reason": reasons,
            "required_origin_count": len(origins),
            "fresh_blind_test_eligible": False,
            "blind_test_blocking_reason": "PREVIOUSLY_CONSUMED_2025_2026_BENCHMARK",
        }
        result_rows.append(item)
        area_audit.append(
            {
                **area,
                "recovery_result": "NO_NEW_CONTEMPORANEOUS_EVIDENCE_FOUND_IN_SCANNED_SOURCES",
                "tier_changed": False,
            }
        )
        identity_audit.append(
            {
                "base_id": key[0],
                "season": key[1],
                "status": identity,
                "source_bindings": bound,
                "binding_usable_retrospectively": identity.startswith("ACCEPTED"),
                "new_binding_applied": False,
            }
        )
        end = date.fromisoformat(business_row["target_end_date"])
        # Diagnose both offsets; DO NOT choose a dataset target convention in S0.
        horizon_counts = {}
        for offset in (0, 1):
            horizon_counts[f"lead_offset_{offset}_full_h15_origins"] = sum(
                date.fromisoformat(r["forecast_origin"][:10]) + timedelta(days=offset + 14) <= end
                for r in origins
            )
        label_audit.append(
            {
                "base_id": key[0],
                "season": key[1],
                "status": label,
                **{
                    k: business_row[k]
                    for k in (
                        "target_start_date",
                        "target_end_date",
                        "logical_record_count",
                        "unknown_count",
                        "partial_subtotal_count",
                        "missing_count",
                        "conflict_count",
                        "invalid_count",
                    )
                },
                **horizon_counts,
                "label_quantities_read": False,
                "evidence_grade": "REUSED_HASH_BOUND_UNIQUE_BASE_DAY_STATE_AUDIT",
            }
        )
        for reason in reasons:
            gaps.append(
                {
                    "base_id": key[0],
                    "season": key[1],
                    "blocking_reason": reason,
                    "existing_evidence": area["source_hash"]
                    if reason.startswith("AREA")
                    else "EXACT_RETROSPECTIVE_SOURCE_BINDINGS",
                    "minimum_required_evidence": (
                        "Payload-bound contemporaneous receipt before each cutoff; "
                        "otherwise separately justified frozen Tier B policy"
                    ),
                    "requested_action": "LOCATE_RECEIPT_OR_CONFIRM_ABSENCE_NO_BULK_REUPLOAD",
                }
            )
    label_counts = Counter(r["label_completeness"] for r in result_rows)
    cohort: dict[str, Any] = {
        "schema": "V0_15_S0_STRICT_REPLAY_COHORT_V1",
        "policy": POLICY,
        "parent_head": PARENT,
        "rows": result_rows,
        "eligible_members": [r for r in result_rows if r["strict_replay_ready"]],
        "cohort_frozen": True,
        "empty_cohort_is_not_dataset_ready": True,
    }
    summary = {
        "task_id": TASK,
        "result": "PASS",
        "pass_definition": "ALL_39_AUDITED_EMPTY_INTERSECTION_FROZEN_NOT_BLIND_DATASET_READY",
        "full_weather_base_season_count": len(full),
        "area_tier_a_count": 0,
        "area_tier_b_count": 0,
        "area_tier_c_count": len(full),
        "identity_strict_count": 0,
        "identity_assumed_count": 0,
        "identity_unresolved_count": len(full),
        "identity_unresolved_definition": "TEMPORAL_PIT_UNPROVEN_NOT_UNRESOLVED_SOURCE_MAPPING",
        "retrospective_identity_usable_count": sum(
            r["identity_status"].startswith("ACCEPTED") for r in result_rows
        ),
        "label_complete_base_season_count": label_counts["LABEL_COMPLETE"],
        "label_partial_base_season_count": label_counts["LABEL_PARTIAL"],
        "label_unusable_for_peak_scoring_count": label_counts["LABEL_UNUSABLE_FOR_PEAK_SCORING"],
        "strict_replay_ready_base_season_count": len(cohort["eligible_members"]),
        "strict_replay_blocked_base_season_count": len(full) - len(cohort["eligible_members"]),
        "strict_replay_cohort_frozen": True,
        "fresh_blind_test_eligible_count": 0,
        "s0_final_ready": False,
        "s1_ready": False,
        "s1_authorized": False,
        "fresh_database_or_server_access": False,
        "label_quantities_accessed": False,
        "model_training_executed": False,
        "scoring_executed": False,
        "current_2026_27_actual_accessed": False,
        "v0_14_changed": False,
        "cold_storage_changed": False,
        "production_db_changed": False,
        "ready_authorized": False,
        "merge_authorized": False,
        "stop": True,
    }
    reports = {
        "intersection-policy.json": POLICY,
        "historical-authority-recovery-source-report.json": {
            "sources": source_receipts,
            "git_lineage": git_lineage,
            "search_limit": (
                "Pinned repository history plus existing hash-bound readonly database audit; "
                "no fresh DB or unknown external receipt search"
            ),
            "tier_b_assumption_instantiated": False,
        },
        "scoped-area-pit-recovery-report.json": {"rows": area_audit},
        "scoped-identity-pit-recovery-report.json": {"rows": identity_audit},
        "scoped-label-completeness-report.json": {
            "rows": label_audit,
            "blind_labels_unlocked": False,
        },
        "strict-replay-cohort.json": cohort,
        "scoped-owner-gap-package.json": {
            "rows": gaps,
            "fresh_blind_test_gap": (
                "Existing consumed 2025-2026 history cannot be restored to pristine test status"
            ),
        },
        "s0-strict-replay-readiness.json": summary,
    }
    output.mkdir(parents=True, exist_ok=True)
    members = []
    for name, value in sorted(reports.items()):
        validate_public(value)
        data = encoded(value)
        (output / name).write_bytes(data)
        members.append({"name": name, "sha256": sha(data), "size": len(data)})
    manifest: dict[str, Any] = {
        "schema": "V0_15_S0_REPLAY_INTERSECTION_MANIFEST_V1",
        "members": members,
        "parent_head": PARENT,
        "serialization": "SORTED_COMPACT_UTF8_JSON_LF_HASH_INCLUDES_LF",
    }
    manifest["manifest_hash"] = sha(encoded(manifest))
    (output / "manifest.json").write_bytes(encoded(manifest))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    generate(args.repo.resolve(), args.output)


if __name__ == "__main__":
    main()
