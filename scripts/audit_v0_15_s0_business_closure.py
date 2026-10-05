"""Read-only source snapshot -> private label projection + sanitized S0 reports.

This offline audit does not connect to a database, train, score, or reconstruct
authorities. A separately authorized read-only acquisition supplies the snapshot.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from scripts.audit_v0_15_s0_existing_assets import validate_public

TASK = "V0_15_S0_HISTORICAL_AUTHORITY_IDENTITY_AND_HARVEST_CLOSURE_R1"
SEASONS = ("2023-2024", "2024-2025", "2025-2026")
STATES = (
    "VALID_OBSERVED",
    "REAL_ZERO",
    "MISSING",
    "UNKNOWN",
    "PARTIAL_SUBTOTAL",
    "CONFLICTING",
    "INVALID",
)
ACCEPTED = {"EXACT", "BUSINESS_CONFIRMED_MAPPING", "AUTHORIZED_ALIAS"}
PINS = {
    "canonical_daily": "be948dee9a7789e90ee60fc42277e8e978ecdc897c519686f3cc36d798d5bd75",
    "zero_overlay": "d0f94ea143cc44c555cc3299a8ea0b3073ab96173fa7927b53104a45c904a8e0",
    "season_area": "40a0e1e6a96cb9d612c51fe7790c03bf9bf7ffe9f865f96d710e4d8c2e96d4d9",
    "identity": "7054c4168fac8342022527ab3ba017eb8e0b2c57409eb0e6dba166e6f181c61b",
    "subfarm_parent": "ca5e949301f981c92c3e9d95375e5f0bef58627854c2ff054527cc5a57308f49",
}
POLICY = {
    "id": "V0_15_S0_LOGICAL_HARVEST_AND_AUTHORITY_AUDIT_R1",
    "logical_key": ["base_id", "season", "date"],
    "grain": "BASE_BUSINESS_DAY; subfarm_id/variety not present at this source grain",
    "overlay": "PINNED_V0_8_S6_EXPLICIT_SUPERSESSION_WITH_OLD_FIELDS_VERIFIED",
    "missing_is_zero": False,
    "partial_is_complete": False,
    "unknown_quantity": None,
    "identity": "EXPLICIT_EXACT_SEASON_BINDING_ONLY; no candidate/fuzzy propagation",
    "tier_b_instantiated": False,
    "training_candidate": "COMPLETE_RETROSPECTIVE_BUSINESS_WINDOW_ONLY; not PIT admission",
    "s1_ready": "Audited business inputs ready for independently authorized authority work",
    "raw_preserved": True,
    "source_pins": PINS,
}


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def validate_season(season: str) -> None:
    if season not in SEASONS:
        raise ValueError("UNAUTHORIZED_SEASON")


def quantity(value: Any) -> Decimal | None:
    if value is None or str(value).strip().lower() in {"", "null"}:
        return None
    parsed = Decimal(str(value))
    if not parsed.is_finite():
        raise ValueError("NONFINITE_QUANTITY")
    return parsed


def classify_quantity(status: str, completeness: str, value: Any) -> tuple[str, str | None]:
    try:
        number = quantity(value)
    except (InvalidOperation, ValueError):
        return "INVALID", None
    if status == "UNKNOWN":
        return (
            ("UNKNOWN", None)
            if (number is None and completeness == "UNKNOWN_NOT_ZERO_FILLED")
            else ("INVALID", None)
        )
    if number is None or number < 0:
        return "INVALID", None
    if status == "CONFIRMED_ZERO" and completeness == "AUTHORIZED_ZERO" and number == 0:
        return "REAL_ZERO", str(number)
    if status == "KNOWN_MAPPED_SUBTOTAL":
        if completeness == "PARTIAL_KNOWN_SUBTOTAL":
            return "PARTIAL_SUBTOTAL", str(number)
        if completeness == "COMPLETE_MAPPED_MEMBERS":
            return ("REAL_ZERO" if number == 0 else "VALID_OBSERVED"), str(number)
    return "INVALID", None


def project_pair(
    original: dict[str, Any] | None,
    overlay: dict[str, Any] | None,
    evidence_ids: list[str],
    hashes: list[str],
) -> dict[str, Any]:
    seed = original or overlay
    if seed is None:
        raise ValueError("NO_EVIDENCE")
    validate_season(seed["season"])
    key = {k: seed[k] for k in ("base_id", "season", "date")}
    day = date.fromisoformat(key["date"])
    start_year = int(key["season"][:4])
    if not date(start_year, 7, 1) <= day <= date(start_year + 1, 6, 30):
        raise ValueError("DATE_SEASON_MISMATCH")
    conflicts = []
    state, value = "MISSING", None
    if original is not None and overlay is not None:
        if any(original[k] != overlay[k] for k in key):
            conflicts.append("EVIDENCE_KEY_MISMATCH")
        if original["quantity_status"] != overlay["old_quantity_status"]:
            conflicts.append("OLD_STATUS_MISMATCH")
        if original["quantity_completeness_status"] != overlay["old_completeness_status"]:
            conflicts.append("OLD_COMPLETENESS_MISMATCH")
        try:
            old = quantity(original["mapped_observed_subtotal_kg"])
            if old != quantity(overlay["old_quantity_kg"]):
                conflicts.append("OLD_QUANTITY_MISMATCH")
            new = quantity(overlay["new_quantity_kg"])
            changed = (
                original["quantity_status"] != overlay["new_quantity_status"]
                or original["quantity_completeness_status"] != overlay["new_completeness_status"]
                or old != new
            )
            permitted_zero = (
                original["quantity_status"] == "UNKNOWN"
                and old is None
                and new == 0
                and overlay.get("zero_applied") == "true"
                and overlay.get("resolution_reason")
                == "VERIFIED_SEASON_SOURCE_HAS_NO_BASE_DAY_HARVEST_ROW"
                and overlay["new_quantity_status"] == "CONFIRMED_ZERO"
                and overlay["new_completeness_status"] == "AUTHORIZED_ZERO"
            )
            permitted_partial = (
                original["quantity_status"]
                == overlay["new_quantity_status"]
                == "KNOWN_MAPPED_SUBTOTAL"
                and old == new
                and original["quantity_completeness_status"] == "PARTIAL_KNOWN_SUBTOTAL"
                and overlay["new_completeness_status"] == "COMPLETE_MAPPED_MEMBERS"
                and overlay.get("partial_resolved") == "true"
                and overlay.get("resolution_reason") == "KNOWN_MISSING_MEMBERS_HAVE_NO_HARVEST_ROWS"
            )
            if changed and not (permitted_zero or permitted_partial):
                conflicts.append("UNAUTHORIZED_TRANSITION")
        except (InvalidOperation, ValueError):
            conflicts.append("INVALID_LINEAGE_QUANTITY")
        state, value = classify_quantity(
            overlay["new_quantity_status"],
            overlay["new_completeness_status"],
            overlay["new_quantity_kg"],
        )
    if conflicts:
        state, value = "CONFLICTING", None
    return {
        "logical_record_id": "harvest_" + digest(key)[:24],
        **key,
        "subfarm_id": None,
        "variety": None,
        "quantity_kg": value,
        "record_state": state,
        "source_evidence_ids": sorted(evidence_ids),
        "source_hashes": sorted(hashes),
        "conflict_status": conflicts or ["NONE"],
        "reason": overlay.get("resolution_reason") if overlay else "MISSING_EVIDENCE_VERSION",
        "grain": "BASE_BUSINESS_DAY",
        "source_grain_limitation": "NO_SUBFARM_OR_VARIETY_DETAIL",
    }


def close_identity(
    row: dict[str, Any],
    historical: list[dict[str, Any]],
    parents: list[dict[str, Any]],
    resolutions: list[dict[str, Any]],
) -> dict[str, Any]:
    validate_season(row["season"])

    def exact(r: dict[str, Any]) -> bool:
        return bool(
            r.get("season") == row["season"]
            and r.get("source_farm_label", r.get("source_label")) == row["source_farm_label"]
        )

    matches = [r for r in historical if exact(r)]
    parent_matches = [r for r in parents if exact(r)]
    resolution_matches = [r for r in resolutions if exact(r)]
    if row["mapping_status"] == "UNRESOLVED" and any(
        r.get("proposed_base_id")
        and r.get("proposed_resolution_status") != "UNRESOLVED_NO_EVIDENCE"
        for r in resolution_matches
    ):
        raise ValueError("NEW_EXPLICIT_IDENTITY_EVIDENCE_REQUIRES_REVIEW")
    # A prior proposal or source-reported parent is not an exact accepted Base binding.
    accepted = row["mapping_status"] in ACCEPTED and bool(row.get("canonical_base_id"))
    return {
        "season": row["season"],
        "source_farm_label": row["source_farm_label"],
        "base_id": row.get("canonical_base_id") or None,
        "mapping_status": row["mapping_status"],
        "closure_status": "ACCEPTED_RETROSPECTIVE" if accepted else row["mapping_status"],
        "strict_pit_authority": False,
        "assumed_pit_authority": False,
        "historical_exact_label_matches": len(matches),
        "parent_exact_label_matches": len(parent_matches),
        "explicit_terminal_base_parent_matches": sum(
            bool(r.get("canonical_base_id_from_farm_identity")) for r in parent_matches
        ),
        "prior_resolution_matches": len(resolution_matches),
        "prior_resolution_statuses": sorted(
            {r.get("proposed_resolution_status", "UNKNOWN") for r in resolution_matches}
        ),
        "reason": "No newer explicit exact-season accepted authority found"
        if row["mapping_status"] == "UNRESOLVED"
        else "Frozen business mapping retained",
        "candidate_is_authority": False,
        "automatic_mapping_applied": False,
    }


def build_reports(
    snapshot: dict[str, Any],
    supplementary: dict[str, Any],
    baseline: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if snapshot["transaction_read_only"] != "on" or snapshot["transaction_end"] != "ROLLBACK":
        raise ValueError("READ_ONLY_PROOF_MISSING")
    if supplementary.get("db_local_source_payload_parity") is not True:
        raise ValueError("LOCAL_DB_PAYLOAD_PARITY_REQUIRED")
    if (
        supplementary["s6_policy"]["input_authorities"]["s1_daily_ledger_sha256"]
        != PINS["canonical_daily"]
    ):
        raise ValueError("S6_SUPERSESSION_LINEAGE_MISMATCH")
    if supplementary["supplementary_sources"]["closure_overlay"]["row_count"] != 0:
        raise ValueError("NEW_IDENTITY_OVERLAY_REQUIRES_REVIEW")
    records = snapshot["records"]
    manifests = {r["source"]: r for r in records["audit.source_manifest"]}
    if {k: v["source_hash"] for k, v in manifests.items()} != PINS:
        raise ValueError("SOURCE_IDENTITY_MISMATCH")
    groups: dict[tuple[str, str, str], dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in records["label_vault.harvest_records"]:
        validate_season(row["season"])
        if row["source_hash"] != PINS.get(row["source"]):
            raise ValueError("HARVEST_SOURCE_HASH_MISMATCH")
        p = row["payload"]
        if row["season"] != p["season"] or row["base_id"] != p["base_id"]:
            raise ValueError("ENVELOPE_IDENTITY_MISMATCH")
        groups[(p["base_id"], p["season"], p["date"])][row["source"]].append(row)
    logical = []
    for harvest_key in sorted(groups):
        group = groups[harvest_key]
        evidence = [r for rows in group.values() for r in rows]
        a, b = group.get("canonical_daily", []), group.get("zero_overlay", [])
        row = project_pair(
            a[0]["payload"] if a else None,
            b[0]["payload"] if b else None,
            [r["source_hash"] + ":" + str(r["source_row_number"]) for r in evidence],
            sorted({r["source_hash"] for r in evidence}),
        )
        if len(a) > 1 or len(b) > 1:
            row.update(
                record_state="CONFLICTING",
                quantity_kg=None,
                conflict_status=["DUPLICATE_EVIDENCE_VERSION"],
            )
        logical.append(row)
    state_counts = {s: sum(r["record_state"] == s for r in logical) for s in STATES}
    areas = []
    for row in records["authority.area_records"]:
        validate_season(row["season"])
        p = row["payload"]
        prior = supplementary["area_metadata"][(row["base_id"] + ":" + row["season"])]
        if prior.get("available_at") is not None or prior.get("historical_known_at") is not None:
            raise ValueError("NEW_TEMPORAL_EVIDENCE_REQUIRES_REVIEW")
        areas.append(
            {
                "base_id": row["base_id"],
                "season": row["season"],
                "area_authority_id": p["area_authority_id"],
                "source_hash": row["source_hash"],
                "source_revision": p["business_confirmation_id"],
                "original_source_hash": p["original_area_source_sha256"],
                "confirmation_hash": p["business_confirmation_sha256"],
                "historical_available_at": None,
                "created_at": None,
                "updated_at": None,
                "historical_ingested_at": None,
                "revision_time": None,
                "bootstrap_imported_at": row["imported_at"],
                "immutable_public_snapshot": supplementary["area_commit"],
                "artifact_timestamp_is_available_at": False,
                "mtime_used_as_available_at": False,
                "assumption_policy_instantiated": False,
                "tier": "PIT_EVIDENCE_TIER_C_RETROSPECTIVE",
                "reason": (
                    "Retrospective confirmation; no contemporaneous payload-bound availability"
                ),
                "searched_source_ids": supplementary["area_search_source_ids"],
            }
        )
    identities = [
        close_identity(
            r["payload"],
            supplementary["historical_mapping"],
            [r["payload"] for r in records["authority.subfarm_parent_records"]],
            supplementary["identity_resolutions"],
        )
        for r in records["authority.identity_records"]
    ]
    unresolved = [r for r in identities if r["closure_status"] == "UNRESOLVED"]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in logical:
        grouped[(row["base_id"], row["season"])].append(row)
    matrix, gaps = [], []
    for area in sorted(areas, key=lambda r: (r["base_id"], r["season"])):
        key = (area["base_id"], area["season"])
        rows = grouped.get(key, [])
        counts = Counter(r["record_state"] for r in rows)
        accepted = [
            r
            for r in identities
            if r["base_id"] == key[0]
            and r["season"] == key[1]
            and r["closure_status"] == "ACCEPTED_RETROSPECTIVE"
        ]
        problems = [s for s in STATES if s not in {"VALID_OBSERVED", "REAL_ZERO"} and counts[s]]
        candidate = bool(rows and accepted and not problems)
        item = {
            "base_id": key[0],
            "season": key[1],
            "entity_kind": "CANONICAL_BASE",
            "harvest_status": "AVAILABLE_VALID" if candidate else "AVAILABLE_PARTIAL",
            "area_pit_tier": area["tier"],
            "identity_status": "ACCEPTED_RETROSPECTIVE" if accepted else "UNRESOLVED",
            "season_status": "FROZEN_BUSINESS_WINDOW_NOT_FULL_YEAR",
            "target_start_date": min(r["date"] for r in rows) if rows else None,
            "target_end_date": max(r["date"] for r in rows) if rows else None,
            "logical_record_count": len(rows),
            "unknown_count": counts["UNKNOWN"],
            "partial_subtotal_count": counts["PARTIAL_SUBTOTAL"],
            "conflict_count": counts["CONFLICTING"],
            "invalid_count": counts["INVALID"],
            "missing_count": counts["MISSING"],
            "strict_pit_ready": False,
            "training_candidate": candidate,
            "training_candidate_class": "RETROSPECTIVE_ONLY",
            "blocking_reason": ["HISTORICAL_AREA_AVAILABLE_AT_NOT_ESTABLISHED"] + problems,
            "training_cohort_selected": False,
            "fresh_blind_test_eligible": False,
        }
        matrix.append(item)

        def gap(
            item_name: str,
            evidence: Any,
            why: str,
            minimum: str,
            blocking: bool = True,
            bound_key: tuple[str, str] = key,
        ) -> dict[str, Any]:
            return {
                "base": bound_key[0],
                "season": bound_key[1],
                "missing_or_unresolved_item": item_name,
                "existing_evidence": evidence,
                "why_existing_data_is_insufficient": why,
                "blocking_or_optional": "BLOCKING" if blocking else "OPTIONAL",
                "minimum_owner_input_required": minimum,
                "true_new_data_required": False,
                "requested_action": "LOCATE_EXISTING_AUTHORITY_OR_CONFIRM_ABSENCE",
            }

        gaps.append(
            gap(
                "historical_area_available_at",
                area["source_hash"],
                area["reason"],
                "Exact Base-season area revision + immutable availability receipt before cutoff",
            )
        )
        if problems or not accepted:
            gaps.append(
                gap(
                    "daily_harvest_identity_or_completeness",
                    {s: counts[s] for s in problems},
                    "Unknown/partial evidence cannot establish complete daily actual",
                    "Exact historical label-to-Base/member binding and day coverage evidence; "
                    "no blanket zero confirmation; affected IDs in private projection",
                )
            )
        gaps.append(
            gap(
                "subfarm_and_variety_detail",
                "Source grain is Base-day",
                "Aggregated ledger cannot recover missing finer-grain identity",
                "Original member/variety IDs if fine-grain analysis is desired",
                False,
            )
        )
    for row in unresolved:
        gaps.append(
            {
                "base": None,
                "source_farm_label": row["source_farm_label"],
                "season": row["season"],
                "missing_or_unresolved_item": "identity_binding",
                "existing_evidence": row,
                "why_existing_data_is_insufficient": row["reason"],
                "blocking_or_optional": "BLOCKING",
                "minimum_owner_input_required": "Explicit historical Base ID/alias or "
                "canonical parent-child authority for this exact season and source label",
                "true_new_data_required": False,
                "requested_action": "LOCATE_EXISTING_AUTHORITY_OR_CONFIRM_ABSENCE",
            }
        )
    # Retain the wider S0 inventory: source labels are not automatically company Bases.
    canonical_lookup = {(r["base_id"], r["season"]): r for r in matrix}
    inventory_matrix = []
    for row in baseline:
        matched = canonical_lookup.get((row["entity_id"], row["season_id"]))
        if matched is not None:
            inventory_matrix.append({**row, **matched, "closure_db_access": "VERIFIED_READ_ONLY"})
        else:
            inventory_matrix.append(
                {
                    **row,
                    "harvest_status": "UNKNOWN_REQUIRES_REVIEW",
                    "area_pit_tier": "UNCLASSIFIED_NO_BOUND_AUTHORITY",
                    "identity_status": "UNBOUND_SOURCE_ENTITY",
                    "season_status": row["season"],
                    "unknown_count": None,
                    "partial_subtotal_count": None,
                    "conflict_count": None,
                    "strict_pit_ready": False,
                    "training_candidate": False,
                    "blocking_reason": ["UNBOUND_ENTITY_NOT_A_BASE_AUTHORITY"],
                    "closure_db_access": "NO_BOUND_RECORD_IN_AUDITED_DB",
                }
            )
    unknown = [r for r in logical if r["record_state"] == "UNKNOWN"]
    partial = [r for r in logical if r["record_state"] == "PARTIAL_SUBTOTAL"]

    def reason_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
        per_base: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for r in rows:
            per_base[(r["base_id"], r["season"])].append(r)
        return {
            "count": len(rows),
            "reason_counts": dict(sorted(Counter(str(r["reason"]) for r in rows).items())),
            "base_season_rows": [
                {
                    "base_id": b,
                    "season": s,
                    "count": len(v),
                    "start_date": min(r["date"] for r in v),
                    "end_date": max(r["date"] for r in v),
                    "logical_record_ids_hash": digest([r["logical_record_id"] for r in v]),
                }
                for (b, s), v in sorted(per_base.items())
            ],
        }

    reports = {
        "canonical-logical-harvest-record-report": {
            "raw_evidence_row_count": len(records["label_vault.harvest_records"]),
            "logical_harvest_record_count": len(logical),
            "key": POLICY["logical_key"],
            "paired_version_count": sum(
                len(v.get("canonical_daily", [])) == 1 and len(v.get("zero_overlay", [])) == 1
                for v in groups.values()
            ),
            "logical_projection_hash": digest(logical),
            "raw_evidence_preserved": True,
            "source_pins": PINS,
            "policy_hash": digest(POLICY),
            "raw_quantities_public": False,
            "projection_in_predictor_zone": False,
        },
        "harvest-record-state-classification": {
            "counts": state_counts,
            "policy": POLICY,
            "policy_hash": digest(POLICY),
            "real_zero_origin_counts": {
                "explicit_authorized_zero": sum(
                    r["payload"]["new_completeness_status"] == "AUTHORIZED_ZERO"
                    for r in records["label_vault.harvest_records"]
                    if r["source"] == "zero_overlay"
                ),
                "complete_observed_zero": sum(
                    r["payload"]["new_completeness_status"] == "COMPLETE_MAPPED_MEMBERS"
                    and quantity(r["payload"]["new_quantity_kg"]) == 0
                    for r in records["label_vault.harvest_records"]
                    if r["source"] == "zero_overlay"
                ),
            },
        },
        "area-pit-evidence-reclassification": {
            "rows": areas,
            "tier_a_count": 0,
            "tier_b_count": 0,
            "tier_c_count": len(areas),
        },
        "identity-authority-closure-report": {
            "rows": identities,
            "strict_count": 0,
            "assumed_count": 0,
            "unresolved_count": len(unresolved),
            "accepted_retrospective_count": sum(
                r["closure_status"] == "ACCEPTED_RETROSPECTIVE" for r in identities
            ),
            "excluded_count": sum(r["closure_status"] == "EXCLUDED" for r in identities),
            "newly_resolved_count": 0,
            "strict_definition": "CONTEMPORANEOUS_PIT_AUTHORITY",
            "searched_source_hashes": supplementary["identity_search_source_hashes"],
        },
        "unknown-record-analysis": {**reason_report(unknown), "quantity_coerced_to_zero": False},
        "partial-subtotal-analysis": {**reason_report(partial), "treated_as_complete": False},
        "base-season-training-readiness-matrix": {
            "rows": matrix,
            "base_season_count": len(matrix),
            "inventory_entity_season_rows": inventory_matrix,
            "inventory_entity_season_count": len(inventory_matrix),
            "strict_pit_ready_count": 0,
            "training_candidate_count": sum(r["training_candidate"] for r in matrix),
            "candidate_is_cohort_selection": False,
        },
        "revised-owner-data-supplement-package": {
            "package_id": "OWNER_DATA_SUPPLEMENT_PACKAGE_R3",
            "rows": gaps,
            "blocking_count": sum(r["blocking_or_optional"] == "BLOCKING" for r in gaps),
            "optional_count": sum(r["blocking_or_optional"] == "OPTIONAL" for r in gaps),
            "true_new_data_required_count": 0,
            "new_upload_required": False,
            "ecmwf_scope": "SEPARATE_ACCESS_GATE_NOT_A_BUSINESS_AUDIT_BLOCKER",
        },
        "s0-business-data-readiness-recommendation": {
            "task_id": TASK,
            "result": "PASS",
            "s0_business_data_ready": True,
            "s0_ready_definition": "EVIDENCE_BOUND_AUDIT_COMPLETED_NOT_TRAINING_READY",
            "s1_ready": True,
            "s1_authorized": False,
            "strict_pit_training_ready": False,
            "current_2026_27_actual_accessed": False,
            "model_training_executed": False,
            "scoring_executed": False,
            "v0_14_changed": False,
            "cold_storage_changed": False,
            "production_db_changed": False,
            "historical_database_changed": False,
            "database_read_only": True,
            "database_rollback": True,
            "snapshot_hash": digest(snapshot),
            "supplementary_evidence_hash": digest(supplementary),
            "policy_hash": digest(POLICY),
            "ready_authorized": False,
            "merge_authorized": False,
        },
    }
    return reports, logical


def validate_business_public(value: Any) -> None:
    validate_public(value)
    if isinstance(value, dict):
        if {"quantity_kg", "actual_quantity_kg", "mapped_observed_subtotal_kg"} & set(value):
            raise ValueError("PUBLIC_HARVEST_QUANTITY")
        for child in value.values():
            validate_business_public(child)
    elif isinstance(value, list):
        for child in value:
            validate_business_public(child)


def write_reports(
    output: Path, reports: dict[str, Any], logical: list[dict[str, Any]] | None
) -> None:
    if output.exists():
        raise ValueError("OUTPUT_EXISTS_IMMUTABLE")
    output.mkdir(parents=True, mode=0o700)
    for name, value in reports.items():
        (output / (name + ".json")).write_text(canonical(value) + "\n", encoding="utf-8")
    rows = reports["base-season-training-readiness-matrix"]["rows"]
    with (output / "base-season-training-readiness-matrix.csv").open(
        "w", encoding="utf-8", newline=""
    ) as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(
            {k: canonical(v) if isinstance(v, list) else v for k, v in r.items()} for r in rows
        )
    if logical is not None:
        (output / "canonical-logical-harvest-records.private.json").write_text(
            canonical(logical) + "\n", encoding="utf-8"
        )
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir())}
    (output / "report-manifest.json").write_text(
        canonical(
            {
                "files": hashes,
                "bundle_hash": digest(hashes),
                "serialization": "SORTED_JSON_UTF8_LF",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    for path in output.iterdir():
        path.chmod(0o600)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--supplementary", type=Path, required=True)
    parser.add_argument("--baseline-matrix", type=Path, required=True)
    parser.add_argument("--public-output", type=Path, required=True)
    parser.add_argument("--private-output", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    snapshot = json.loads(args.snapshot.read_text())
    supplementary = json.loads(args.supplementary.read_text())
    reports, logical = build_reports(
        snapshot, supplementary, json.loads(args.baseline_matrix.read_text())["rows"]
    )
    validate_business_public(reports)
    write_reports(args.public_output, reports, None)
    write_reports(args.private_output, reports, logical)
    print(
        canonical(
            {
                "task_id": TASK,
                "result": "PASS",
                "logical_count": len(logical),
                "projection_hash": digest(logical),
            }
        )
    )


if __name__ == "__main__":
    main()
