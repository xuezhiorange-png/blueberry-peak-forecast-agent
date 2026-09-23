"""Recover and rebind existing historical area evidence without promotion side effects.

The runner consumes frozen source inventories and authorities, emits detailed
rows only to a private output directory, and never edits an existing authority.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

TASK_ID = "V0_8_S3_EXISTING_HISTORICAL_AREA_RECOVERY_AND_CANONICAL_REBIND_R1"
SEASONS = ("2023-2024", "2024-2025", "2025-2026")
TRAIN_SEASONS = frozenset({"2023-2024", "2024-2025"})
OOT_SEASONS = frozenset({"2025-2026"})
ACCEPTED_IDENTITY_STATUSES = frozenset(
    {
        "EXACT",
        "AUTHORIZED_ALIAS",
        "HISTORICALLY_PROVEN_ALIAS",
        "BUSINESS_CONFIRMED_MAPPING",
        "BUSINESS_CONFIRMED_REASSIGNMENT",
    }
)

SOURCE_LEDGER_FIELDS = (
    "source_record_id",
    "source_type",
    "source_path",
    "source_sha256",
    "source_revision",
    "season_raw",
    "farm_label_raw",
    "subfarm_label_raw",
    "area_mu_raw",
    "area_unit_raw",
    "area_semantics_raw",
    "source_date",
    "business_confirmation_status",
    "original_authority_status",
    "current_canonical_base_id",
    "current_canonical_base_name",
    "identity_binding_status",
    "season_binding_status",
    "area_authority_candidate_status",
    "conflict_status",
    "conflict_detail",
    "prior_binding_failure_reason",
    "evidence",
)

AUTHORITY_FIELDS = (
    "base_id",
    "canonical_base_name",
    "season",
    "historical_actual_productive_area_mu",
    "area_status",
    "area_basis",
    "source_record_count",
    "source_ids",
    "source_hashes",
    "identity_authority_id",
    "identity_authority_sha256",
    "season_binding",
    "conflict_status",
    "candidate_area_values_mu",
    "training_area_eligible",
)


class RecoveryError(ValueError):
    """Stable fail-closed error for area evidence recovery."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def csv_bytes(rows: list[dict[str, Any]], fields: tuple[str, ...]) -> bytes:
    from io import StringIO

    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: json_cell(row.get(field, "")) for field in fields})
    return buffer.getvalue().encode("utf-8")


def json_cell(value: Any) -> str:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def verify_pinned_file(path: Path, expected_sha256: str, label: str) -> str:
    if not path.is_file():
        raise RecoveryError(f"INPUT_FILE_MISSING:{label}")
    actual = sha256_file(path)
    if actual != expected_sha256:
        raise RecoveryError(f"INPUT_HASH_MISMATCH:{label}:{actual}")
    return actual


def _identity_index(
    identity_rows: list[dict[str, str]],
) -> dict[tuple[str, str], list[dict[str, str]]]:
    result: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in identity_rows:
        result[(row.get("season", ""), row.get("source_farm_label", ""))].append(row)
    return result


def _resolve_current_identity(
    *,
    season: str,
    labels: list[str],
    identity_index: dict[tuple[str, str], list[dict[str, str]]],
) -> tuple[str, str, str]:
    matches: dict[str, dict[str, str]] = {}
    unresolved_seen = False
    for label in labels:
        if not label:
            continue
        for row in identity_index.get((season, label), []):
            status = row.get("mapping_status", "")
            if status in ACCEPTED_IDENTITY_STATUSES and row.get("canonical_base_id"):
                matches[row["canonical_base_id"]] = row
            elif status in {"UNRESOLVED", "CONFLICTING"}:
                unresolved_seen = True
    if len(matches) == 1:
        row = next(iter(matches.values()))
        return (
            row["canonical_base_id"],
            row.get("canonical_base_name", ""),
            "BOUND_CURRENT_CANONICAL_IDENTITY",
        )
    if len(matches) > 1:
        return "", "", "IDENTITY_CONFLICTING_MULTIPLE_CANONICAL_BASES"
    if unresolved_seen:
        return "", "", "AREA_SOURCE_FOUND_IDENTITY_UNRESOLVED"
    return "", "", "NOT_BOUND_BY_CURRENT_IDENTITY_AUTHORITY"


def _direct_area_bindings(
    *,
    area_authority: dict[str, Any],
    qualification_rows: list[dict[str, str]],
    identity_index: dict[tuple[str, str], list[dict[str, str]]],
    source_records: list[dict[str, str]],
    area_authority_sha256: str,
    identity_authority_sha256: str,
) -> list[dict[str, Any]]:
    aliases = area_authority.get("aliases", {})
    qualifications = {
        (row.get("season", ""), row.get("canonical_farm", "")): row for row in qualification_rows
    }
    bindings: list[dict[str, Any]] = []
    for history in area_authority.get("history", []):
        season = str(history.get("season", ""))
        farm = str(history.get("farm", ""))
        if season not in SEASONS:
            continue
        if history.get("area_basis") != "BUSINESS_CONFIRMED":
            continue
        raw_labels = [farm]
        raw_labels.extend(alias for alias, target in aliases.items() if target == farm)
        base_matches: dict[str, dict[str, str]] = {}
        for label in raw_labels:
            for row in identity_index.get((season, label), []):
                if row.get("mapping_status") in ACCEPTED_IDENTITY_STATUSES and row.get(
                    "canonical_base_id"
                ):
                    base_matches[row["canonical_base_id"]] = row
        if len(base_matches) != 1:
            raise RecoveryError(f"AREA_IDENTITY_REBIND_NOT_UNIQUE:{season}:{farm}")
        base_id, identity = next(iter(base_matches.items()))
        qualification = qualifications.get((season, farm))
        if qualification is None:
            raise RecoveryError(f"AREA_QUALIFICATION_PROVENANCE_MISSING:{season}:{farm}")
        if (
            qualification.get("area_basis") != "BUSINESS_CONFIRMED"
            or qualification.get("source_hash") != history.get("source_hash")
            or qualification.get("productive_area_mu") != history.get("historical_area_mu")
            or qualification.get("area_bound", "").lower() != "true"
        ):
            raise RecoveryError(f"AREA_QUALIFICATION_PROVENANCE_MISMATCH:{season}:{farm}")
        source_matches = [
            row
            for row in source_records
            if row.get("source_kind") == "AREA_YIELD_AUTHORITY"
            and row.get("source_hash") == area_authority_sha256
            and row.get("season") == season
            and row.get("area_mu") == history.get("historical_area_mu")
            and row.get("area_semantics") == "ACTUAL_PRODUCTIVE_AREA"
            and row.get("mapped_base_id") == base_id
        ]
        if len(source_matches) != 1:
            raise RecoveryError(f"AREA_SOURCE_LEDGER_BINDING_NOT_UNIQUE:{season}:{farm}")
        bindings.append(
            {
                "base_id": base_id,
                "canonical_base_name": identity.get("canonical_base_name", ""),
                "season": season,
                "area_mu": str(history.get("historical_area_mu", "")),
                "area_basis": "BUSINESS_CONFIRMED",
                "source_record_id": source_matches[0].get("record_id", ""),
                "source_date": str(history.get("available_on", "")),
                "source_hash": area_authority_sha256,
                "raw_source_hash": str(history.get("source_hash", "")),
                "source_hashes": sorted(
                    {area_authority_sha256, str(history.get("source_hash", ""))}
                ),
                "identity_authority_id": "CROSS_SEASON_BASE_IDENTITY_AUTHORITY_R1",
                "identity_authority_sha256": identity_authority_sha256,
                "identity_evidence_id": str(identity.get("identity_revision_id", "")),
                "evidence": ";".join(
                    (
                        area_authority_sha256,
                        str(qualification.get("source_hash", "")),
                        str(identity.get("identity_revision_id", "")),
                    )
                ),
            }
        )
    return bindings


def build_source_recovery_ledger(
    *,
    source_records: list[dict[str, str]],
    identity_rows: list[dict[str, str]],
    direct_bindings: list[dict[str, Any]],
    area_authority_sha256: str,
) -> list[dict[str, Any]]:
    identity_index = _identity_index(identity_rows)
    direct_by_source_id = {str(row["source_record_id"]): row for row in direct_bindings}
    result: list[dict[str, Any]] = []
    for source in source_records:
        season = source.get("season", "")
        direct = direct_by_source_id.get(source.get("record_id", ""))
        labels = [source.get("source_original_name", ""), source.get("farm_identity", "")]
        if direct:
            base_id = str(direct["base_id"])
            base_name = str(direct["canonical_base_name"])
            identity_status = "BOUND_CURRENT_CANONICAL_IDENTITY"
        elif season in SEASONS:
            base_id, base_name, identity_status = _resolve_current_identity(
                season=season, labels=labels, identity_index=identity_index
            )
            if not base_id and (
                source.get("identity_mapping_status") in {"UNRESOLVED", "CONFLICTING"}
                or source.get("decision") == "UNRESOLVED_AREA_IDENTITY"
            ):
                identity_status = "AREA_SOURCE_FOUND_IDENTITY_UNRESOLVED"
        else:
            base_id, base_name = "", ""
            identity_status = (
                "AREA_SOURCE_FOUND_SEASON_UNRESOLVED" if source.get("area_mu") else "NOT_APPLICABLE"
            )

        if direct:
            authority_status = "BUSINESS_CONFIRMED_HISTORICAL_ACTUAL"
            reason = (
                "ALREADY_IN_V08_S1"
                if source.get("source_original_name") == "保山杨柳农场"
                else "OLD_AREA_AUTHORITY_NOT_REBOUND_TO_CANONICAL_BASE_SEASON"
            )
            conflict_status = "NONE"
            season_status = "EXACT_SEASON_AUTHORITY"
        else:
            authority_status = source.get("authority_eligibility", "")
            reason = _prior_failure_reason(source)
            conflict_status = (
                "CANDIDATE_CONFLICT_OR_REVIEW"
                if source.get("decision") == "BUSINESS_CONFIRMATION_REQUIRED"
                else "NONE"
            )
            if season in SEASONS:
                season_status = (
                    "SOURCE_SEASON_LABEL_PRESENT_NOT_AUTHORITY"
                    if source.get("area_semantics") != "ACTUAL_PRODUCTIVE_AREA"
                    else "SOURCE_SEASON_LABEL_PRESENT"
                )
            else:
                season_status = "SEASON_NOT_ESTABLISHED"
        evidence_data = {
            "inventory_record_id": source.get("record_id", ""),
            "source_layer": source.get("source_layer", ""),
            "source_kind": source.get("source_kind", ""),
            "source_row_original_wording": source.get("original_wording", ""),
            "source_area_basis": source.get("area_basis", ""),
            "source_grain": source.get("grain", ""),
            "source_mapping_status_before_rebind": source.get("identity_mapping_status", ""),
            "source_candidate_base_id_before_rebind": source.get("mapped_base_id", ""),
            "source_decision": source.get("decision", ""),
            "source_notes": source.get("notes", ""),
            "current_identity_authority_id": "CROSS_SEASON_BASE_IDENTITY_AUTHORITY_R1",
            "current_identity_binding_result": identity_status,
        }
        if direct:
            evidence_data.update(
                {
                    "area_authority_sha256": direct["source_hash"],
                    "raw_season_source_sha256": direct["raw_source_hash"],
                    "identity_authority_sha256": direct["identity_authority_sha256"],
                    "identity_revision_id": direct["identity_evidence_id"],
                }
            )
        evidence = json.dumps(
            evidence_data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        result.append(
            {
                "source_record_id": source.get("record_id", ""),
                "source_type": source.get("source_kind", ""),
                "source_path": source.get("source_file", ""),
                "source_sha256": source.get("source_hash", ""),
                "source_revision": f"{source.get('sheet', '')}:{source.get('source_row', '')}",
                "season_raw": season,
                "farm_label_raw": source.get("source_original_name", "")
                or source.get("farm_identity", ""),
                "subfarm_label_raw": "",
                "area_mu_raw": source.get("area_mu", ""),
                "area_unit_raw": "mu" if source.get("area_mu") else "",
                "area_semantics_raw": source.get("area_semantics", ""),
                "source_date": direct.get("source_date", "") if direct else "",
                "business_confirmation_status": source.get("area_basis", ""),
                "original_authority_status": source.get("authority_eligibility", ""),
                "current_canonical_base_id": base_id,
                "current_canonical_base_name": base_name,
                "identity_binding_status": identity_status,
                "season_binding_status": season_status,
                "area_authority_candidate_status": authority_status,
                "conflict_status": conflict_status,
                "conflict_detail": source.get("notes", "") if conflict_status != "NONE" else "",
                "prior_binding_failure_reason": reason,
                "evidence": evidence,
            }
        )
    return result


def _prior_failure_reason(source: dict[str, str]) -> str:
    semantics = source.get("area_semantics", "")
    if source.get("decision") == "UNRESOLVED_AREA_IDENTITY":
        return "IDENTITY_UNRESOLVED"
    if semantics in {"CURRENT_AREA"}:
        return "SOURCE_EXISTED_ONLY_AS_REFERENCE_AREA"
    if semantics == "PREVIOUS_SEASON_PROXY":
        return "SOURCE_EXISTED_ONLY_AS_PREVIOUS_SEASON_PROXY"
    if semantics in {"PROCESSING_FACTORY_STATISTICAL_AREA", "PLANNED_AREA", "PLANTED_AREA"}:
        return "SOURCE_EXISTED_ONLY_AS_REPORT_OR_PLAN_CANDIDATE"
    if source.get("season") in {"UNSPECIFIED", "CURRENT/UNSPECIFIED", "MULTI-SEASON_SCOPE"}:
        return "SEASON_BINDING_MISSING"
    if source.get("source_kind") == "AREA_YIELD_AUTHORITY":
        return "SOURCE_NOT_INCLUDED_IN_PRIOR_CANONICAL_AREA_AUTHORITY"
    return "AREA_SEMANTICS_NOT_HISTORICAL_ACTUAL"


def build_candidate_authority(
    *,
    quality_rows: list[dict[str, str]],
    source_ledger: list[dict[str, Any]],
    direct_bindings: list[dict[str, Any]],
    area_conflicts: list[dict[str, str]],
) -> list[dict[str, Any]]:
    direct_by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in direct_bindings:
        direct_by_key[(str(row["base_id"]), str(row["season"]))].append(row)
    ledger_by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in source_ledger:
        base_id = str(row.get("current_canonical_base_id", ""))
        season = str(row.get("season_raw", ""))
        if base_id and season in SEASONS:
            ledger_by_key[(base_id, season)].append(row)
    conflict_by_key = {
        (row.get("base_id", ""), row.get("season_id", "")): row
        for row in area_conflicts
        if row.get("current_decision") == "CONFLICTING_EVIDENCE"
    }
    result: list[dict[str, Any]] = []
    for quality in sorted(quality_rows, key=lambda row: (row["base_id"], row["season"])):
        key = (quality["base_id"], quality["season"])
        direct = direct_by_key.get(key, [])
        sources = ledger_by_key.get(key, [])
        conflict = conflict_by_key.get(key)
        values = sorted(
            {str(row.get("area_mu_raw", "")) for row in sources if row.get("area_mu_raw")}
        )
        if len(direct) > 1 and len({row["area_mu"] for row in direct}) > 1:
            status, basis, conflict_status = (
                "CONFLICTING_EVIDENCE",
                "BUSINESS_CONFIRMED_SOURCE_CONFLICT",
                "CONFLICTING_AREA_EVIDENCE",
            )
            area = ""
        elif direct:
            status, basis, conflict_status = (
                "BUSINESS_CONFIRMED_HISTORICAL_ACTUAL",
                "BUSINESS_CONFIRMED",
                "NONE",
            )
            area = direct[0]["area_mu"]
            values = sorted({str(row["area_mu"]) for row in direct})
        elif conflict:
            status, basis, conflict_status = (
                "CONFLICTING_EVIDENCE",
                "NON_AUTHORITY_PROXY_OR_REPORT_CONFLICT",
                "CONFLICTING_CANDIDATE_EVIDENCE",
            )
            area = ""
        elif sources:
            status, basis, conflict_status = (
                "REFERENCE_AREA_ONLY",
                "NON_HISTORICAL_OR_UNAUTHORIZED_CANDIDATES",
                "NONE",
            )
            area = ""
        else:
            status, basis, conflict_status = (
                "NOT_FOUND",
                "NO_SEASON_BOUND_HISTORICAL_AREA_AUTHORITY",
                "NONE",
            )
            area = ""
        is_train_area = bool(area and key[1] in TRAIN_SEASONS)
        result.append(
            {
                "base_id": quality["base_id"],
                "canonical_base_name": quality["canonical_base_name"],
                "season": quality["season"],
                "historical_actual_productive_area_mu": area,
                "area_status": status,
                "area_basis": basis,
                "source_record_count": len(direct) if direct else len(sources),
                "source_ids": [row["source_record_id"] for row in direct]
                if direct
                else [row["source_record_id"] for row in sources],
                "source_hashes": sorted(
                    {value for row in direct for value in row["source_hashes"]}
                    if direct
                    else {row["source_sha256"] for row in sources if row.get("source_sha256")}
                ),
                "identity_authority_id": "CROSS_SEASON_BASE_IDENTITY_AUTHORITY_R1"
                if direct
                else "",
                "identity_authority_sha256": direct[0]["identity_authority_sha256"]
                if direct
                else "",
                "season_binding": "EXACT_SEASON_AUTHORITY"
                if direct
                else "NOT_AUTHORIZED_FOR_HISTORICAL_SEASON_USE",
                "conflict_status": conflict_status,
                "candidate_area_values_mu": values,
                "training_area_eligible": is_train_area,
            }
        )
    if len(result) != 117 or len({(r["base_id"], r["season"]) for r in result}) != 117:
        raise RecoveryError("CANONICAL_BASE_SEASON_MATRIX_NOT_117_UNIQUE_ROWS")
    return result


def build_conflict_ledger(
    rows: list[dict[str, str]], source_ledger: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    ledger_index: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in source_ledger:
        if row.get("current_canonical_base_id"):
            ledger_index[(str(row["current_canonical_base_id"]), str(row["season_raw"]))].append(
                row
            )
    conflicts: list[dict[str, Any]] = []
    for row in rows:
        if row.get("current_decision") != "CONFLICTING_EVIDENCE":
            continue
        base_id, season = row.get("base_id", ""), row.get("season_id", "")
        sources = ledger_index.get((base_id, season), [])
        conflicts.append(
            {
                "base_id": base_id,
                "canonical_base_name": row.get("base_name", ""),
                "season": season,
                "conflict_status": "CONFLICTING_CANDIDATE_EVIDENCE",
                "candidate_area_values_mu": row.get("analysis_report_candidate_areas_mu", ""),
                "previous_season_proxy_area_mu": row.get("previous_season_proxy_area_mu", ""),
                "candidate_difference_mu": row.get("candidate_difference_mu", ""),
                "source_record_ids": [s["source_record_id"] for s in sources],
                "evidence": row.get("analysis_report_evidence_path_hash_row_reference", ""),
                "business_decision": "",
            }
        )
    return sorted(conflicts, key=lambda row: (row["season"], row["base_id"]))


def build_diff_and_eligibility(
    *, quality_rows: list[dict[str, str]], candidate_rows: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidate_index = {(r["base_id"], r["season"]): r for r in candidate_rows}
    diff_rows: list[dict[str, Any]] = []
    eligibility: list[dict[str, Any]] = []
    for old in sorted(quality_rows, key=lambda row: (row["base_id"], row["season"])):
        key = (old["base_id"], old["season"])
        new = candidate_index[key]
        quantity_ok = (
            old.get("business_total_coverage_status") == "BUSINESS_TOTAL_AUTHORITY_ELIGIBLE"
            and old.get("season_total_complete", "").lower() == "true"
        )
        area_ok = new["area_status"] == "BUSINESS_CONFIRMED_HISTORICAL_ACTUAL" and bool(
            new["historical_actual_productive_area_mu"]
        )
        season = old["season"]
        strict_train = area_ok and quantity_ok and season in TRAIN_SEASONS
        strict_oot = area_ok and quantity_ok and season in OOT_SEASONS
        diff_rows.append(
            {
                "base_id": old["base_id"],
                "canonical_base_name": old["canonical_base_name"],
                "season": season,
                "old_area_status": old.get("historical_actual_productive_area_status", ""),
                "old_historical_area_mu": old.get("historical_actual_productive_area_mu", ""),
                "new_area_status": new["area_status"],
                "new_historical_area_mu": new["historical_actual_productive_area_mu"],
                "change": "RECOVERED_NEW_BINDING"
                if area_ok and not old.get("historical_actual_productive_area_mu")
                else "UNCHANGED"
                if area_ok
                else "NO_AUTHORITY_GAIN",
            }
        )
        reason = (
            "ELIGIBLE"
            if strict_train or strict_oot
            else (
                "SEASON_NOT_IN_TRAIN_OR_OOT_SCOPE"
                if season not in TRAIN_SEASONS | OOT_SEASONS
                else "HISTORICAL_AREA_NOT_AUTHORIZED"
                if not area_ok
                else "COMPLETE_SEASON_TOTAL_AUTHORITY_MISSING"
            )
        )
        eligibility.append(
            {
                "base_id": old["base_id"],
                "canonical_base_name": old["canonical_base_name"],
                "season": season,
                "area_status": new["area_status"],
                "historical_actual_area_mu": new["historical_actual_productive_area_mu"],
                "business_total_coverage_status": old.get("business_total_coverage_status", ""),
                "season_total_complete": old.get("season_total_complete", ""),
                "strict_training_eligible_if_rebound_now": strict_train,
                "strict_oot_eligible_if_rebound_now": strict_oot,
                "exclusion_reason": reason,
            }
        )
    return diff_rows, eligibility


def _prior_failure_counts(source_ledger: list[dict[str, Any]]) -> dict[str, int]:
    return dict(
        sorted(Counter(str(row["prior_binding_failure_reason"]) for row in source_ledger).items())
    )


def build_artifacts(inputs: dict[str, Any]) -> dict[str, bytes]:
    source_records: list[dict[str, str]] = inputs["source_records"]
    identity_rows: list[dict[str, str]] = inputs["identity_rows"]
    quality_rows: list[dict[str, str]] = inputs["quality_rows"]
    direct_bindings = _direct_area_bindings(
        area_authority=inputs["area_authority"],
        qualification_rows=inputs["qualification_rows"],
        identity_index=_identity_index(identity_rows),
        source_records=source_records,
        area_authority_sha256=inputs["hashes"]["area_authority"],
        identity_authority_sha256=inputs["hashes"]["identity"],
    )
    source_ledger = build_source_recovery_ledger(
        source_records=source_records,
        identity_rows=identity_rows,
        direct_bindings=direct_bindings,
        area_authority_sha256=inputs["hashes"]["area_authority"],
    )
    conflict_ledger = build_conflict_ledger(inputs["area_confirmation_2024"], source_ledger)
    candidate_rows = build_candidate_authority(
        quality_rows=quality_rows,
        source_ledger=source_ledger,
        direct_bindings=direct_bindings,
        area_conflicts=inputs["area_confirmation_2024"],
    )
    diff_rows, eligibility_rows = build_diff_and_eligibility(
        quality_rows=quality_rows, candidate_rows=candidate_rows
    )
    source_reasons = _prior_failure_counts(source_ledger)
    candidate_counts = Counter(row["area_status"] for row in candidate_rows)
    source_semantics = Counter(row.get("area_semantics", "") for row in source_records)
    training_area_count = sum(
        row["area_status"] == "BUSINESS_CONFIRMED_HISTORICAL_ACTUAL"
        and row["season"] in TRAIN_SEASONS
        for row in candidate_rows
    )
    oot_area_count = sum(
        row["area_status"] == "BUSINESS_CONFIRMED_HISTORICAL_ACTUAL"
        and row["season"] in OOT_SEASONS
        for row in candidate_rows
    )
    strict_training_count = sum(
        row["strict_training_eligible_if_rebound_now"] for row in eligibility_rows
    )
    strict_oot_count = sum(row["strict_oot_eligible_if_rebound_now"] for row in eligibility_rows)
    existing_area_count = sum(
        row.get("historical_actual_productive_area_status")
        == "BUSINESS_CONFIRMED_SOURCE_LABEL_BOUND"
        for row in quality_rows
    )
    recovered_area_count = sum(row["change"] == "RECOVERED_NEW_BINDING" for row in diff_rows)
    summary = {
        "task_id": TASK_ID,
        "scope": "RECOVER_AND_REBIND_ONLY_NO_AUTHORITY_MUTATION_NO_MODEL_EXECUTION",
        "identity_authority_id": "CROSS_SEASON_BASE_IDENTITY_AUTHORITY_R1",
        "identity_authority_sha256": inputs["hashes"]["identity"],
        "canonical_quality_ledger_sha256": inputs["hashes"]["quality"],
        "source_inventory_sha256": inputs["hashes"]["source_inventory"],
        "source_inventory_manifest_sha256": inputs["hashes"]["source_manifest"],
        "area_authority_sha256": inputs["hashes"]["area_authority"],
        "r7b_artifact_manifest_sha256": inputs["hashes"]["r7b_manifest"],
        "r7b_qualification_sha256": inputs["hashes"]["r7b_qualification"],
        "area_source_record_count": len(source_records),
        "area_source_file_count_hash_verified": inputs["verified_source_file_count"],
        "canonical_base_count": len({row["base_id"] for row in quality_rows}),
        "season_count": len(SEASONS),
        "base_season_count": len(candidate_rows),
        "historical_actual_area_base_season_count_before": existing_area_count,
        "historical_actual_area_base_season_count_after": candidate_counts[
            "BUSINESS_CONFIRMED_HISTORICAL_ACTUAL"
        ],
        "area_authority_gain": recovered_area_count,
        "area_authorized_by_season": {
            season: sum(
                row["season"] == season
                and row["area_status"] == "BUSINESS_CONFIRMED_HISTORICAL_ACTUAL"
                for row in candidate_rows
            )
            for season in SEASONS
        },
        "area_base_count_with_at_least_one_historical_season": len(
            {
                row["base_id"]
                for row in candidate_rows
                if row["area_status"] == "BUSINESS_CONFIRMED_HISTORICAL_ACTUAL"
            }
        ),
        "area_conflict_count": len(conflict_ledger),
        "area_identity_unresolved_source_record_count": sum(
            row["identity_binding_status"] == "AREA_SOURCE_FOUND_IDENTITY_UNRESOLVED"
            and row["season_raw"] in SEASONS
            for row in source_ledger
        ),
        "area_season_unresolved_source_record_count": sum(
            row["season_binding_status"] == "SEASON_NOT_ESTABLISHED" for row in source_ledger
        ),
        "area_not_found_base_season_count": candidate_counts["NOT_FOUND"],
        "candidate_status_counts": dict(sorted(candidate_counts.items())),
        "source_semantics_counts": dict(sorted(source_semantics.items())),
        "prior_area_binding_failure_reasons": source_reasons,
        "historical_actual_area_base_season_count_train_seasons": training_area_count,
        "historical_actual_area_base_season_count_oot_season": oot_area_count,
        "strict_training_area_qualified_count": training_area_count,
        "strict_oot_area_qualified_count": oot_area_count,
        "strict_training_eligible_if_rebound_now": strict_training_count,
        "strict_oot_eligible_if_rebound_now": strict_oot_count,
        "quantity_total_authority_still_blocking": strict_training_count == 0,
        "no_area_estimation": True,
        "reference_area_promoted_automatically": False,
        "cross_season_area_propagation": False,
        "model_training_executed": False,
        "model_refit_executed": False,
        "backtest_executed": False,
        "forecast_replay_executed": False,
        "outputs_private": True,
    }
    return {
        "historical-area-source-recovery-ledger-r1.csv": csv_bytes(
            source_ledger, SOURCE_LEDGER_FIELDS
        ),
        "canonical-historical-area-authority-r1.csv": csv_bytes(candidate_rows, AUTHORITY_FIELDS),
        "area-conflict-ledger-r1.csv": csv_bytes(
            conflict_ledger,
            (
                "base_id",
                "canonical_base_name",
                "season",
                "conflict_status",
                "candidate_area_values_mu",
                "previous_season_proxy_area_mu",
                "candidate_difference_mu",
                "source_record_ids",
                "evidence",
                "business_decision",
            ),
        ),
        "old-vs-new-area-authority-diff-r1.csv": csv_bytes(
            diff_rows,
            (
                "base_id",
                "canonical_base_name",
                "season",
                "old_area_status",
                "old_historical_area_mu",
                "new_area_status",
                "new_historical_area_mu",
                "change",
            ),
        ),
        "area-training-eligibility-r1.csv": csv_bytes(
            eligibility_rows,
            (
                "base_id",
                "canonical_base_name",
                "season",
                "area_status",
                "historical_actual_area_mu",
                "business_total_coverage_status",
                "season_total_complete",
                "strict_training_eligible_if_rebound_now",
                "strict_oot_eligible_if_rebound_now",
                "exclusion_reason",
            ),
        ),
        "area-recovery-summary.json": canonical_json_bytes(summary),
    }


def load_inputs(args: argparse.Namespace, config: dict[str, Any]) -> dict[str, Any]:
    if config.get("identity_authority_id") != "CROSS_SEASON_BASE_IDENTITY_AUTHORITY_R1":
        raise RecoveryError("CONFIG_IDENTITY_AUTHORITY_MISMATCH")
    if tuple(config.get("seasons", ())) != SEASONS:
        raise RecoveryError("CONFIG_SEASON_SCOPE_MISMATCH")
    if frozenset(config.get("training_seasons", ())) != TRAIN_SEASONS:
        raise RecoveryError("CONFIG_TRAINING_SEASONS_MISMATCH")
    if frozenset(config.get("oot_seasons", ())) != OOT_SEASONS:
        raise RecoveryError("CONFIG_OOT_SEASONS_MISMATCH")
    if frozenset(config.get("accepted_identity_statuses", ())) != ACCEPTED_IDENTITY_STATUSES:
        raise RecoveryError("CONFIG_ACCEPTED_IDENTITY_STATUS_MISMATCH")
    path_keys = {
        "source_inventory": args.source_inventory,
        "source_manifest": args.source_manifest,
        "identity": args.identity,
        "quality": args.quality,
        "area_authority": args.area_authority,
        "r7b_manifest": args.r7b_manifest,
        "r7b_qualification": args.r7b_qualification,
        "area_confirmation_2023": args.area_confirmation_2023,
        "area_confirmation_2024": args.area_confirmation_2024,
    }
    hashes = {
        key: verify_pinned_file(Path(path), config["expected_sha256"][key], key)
        for key, path in path_keys.items()
    }
    source_manifest = json.loads(Path(args.source_manifest).read_text(encoding="utf-8"))
    source_records = read_csv(Path(args.source_inventory))
    if len(source_records) != source_manifest.get("raw_area_record_count"):
        raise RecoveryError("AREA_SOURCE_RECORD_COUNT_MISMATCH")
    source_paths = {row["source_file"]: row["source_hash"] for row in source_records}
    for path, expected in sorted(source_paths.items()):
        verify_pinned_file(Path(path), expected, "raw_area_source")
    r7b_manifest = json.loads(Path(args.r7b_manifest).read_text(encoding="utf-8"))
    r7b_dir = Path(args.r7b_manifest).parent
    for filename, expected in r7b_manifest.items():
        verify_pinned_file(r7b_dir / filename, expected, f"r7b:{filename}")
    hashes["r7b_manifest"] = sha256_file(Path(args.r7b_manifest))
    hashes["r7b_qualification"] = sha256_file(Path(args.r7b_qualification))
    area_authority = json.loads(Path(args.area_authority).read_text(encoding="utf-8"))
    quality_rows = read_csv(Path(args.quality))
    if len(quality_rows) != 117:
        raise RecoveryError("CANONICAL_QUALITY_LEDGER_NOT_117_ROWS")
    identity_rows = read_csv(Path(args.identity))
    if len({(row["base_id"], row["season"]) for row in quality_rows}) != 117:
        raise RecoveryError("CANONICAL_QUALITY_LEDGER_DUPLICATE_BASE_SEASON")
    for row in quality_rows:
        if row["season"] not in SEASONS:
            raise RecoveryError("UNEXPECTED_SEASON_IN_CANONICAL_QUALITY_LEDGER")
    return {
        "source_records": source_records,
        "identity_rows": identity_rows,
        "quality_rows": quality_rows,
        "area_authority": area_authority,
        "qualification_rows": read_csv(Path(args.r7b_qualification)),
        "area_confirmation_2023": read_csv(Path(args.area_confirmation_2023)),
        "area_confirmation_2024": read_csv(Path(args.area_confirmation_2024)),
        "hashes": hashes,
        "verified_source_file_count": len(source_paths),
    }


def write_private_outputs(
    output_dir: Path, artifacts: dict[str, bytes], input_hashes: dict[str, str]
) -> dict[str, str]:
    if output_dir.exists():
        raise RecoveryError("OUTPUT_DIRECTORY_MUST_NOT_EXIST")
    output_dir.mkdir(parents=True, mode=0o700)
    os.chmod(output_dir, 0o700)
    artifact_hashes: dict[str, str] = {}
    for filename, payload in sorted(artifacts.items()):
        path = output_dir / filename
        with path.open("xb") as stream:
            stream.write(payload)
        os.chmod(path, 0o600)
        artifact_hashes[filename] = sha256_bytes(payload)
    manifest = {
        "task_id": TASK_ID,
        "private": True,
        "input_sha256": dict(sorted(input_hashes.items())),
        "artifacts": artifact_hashes,
        "model_training_executed": False,
        "authority_modified": False,
    }
    payload = canonical_json_bytes(manifest)
    with (output_dir / "artifact-manifest.json").open("xb") as stream:
        stream.write(payload)
    os.chmod(output_dir / "artifact-manifest.json", 0o600)
    return {**artifact_hashes, "artifact-manifest.json": sha256_bytes(payload)}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--source-inventory", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--quality", type=Path, required=True)
    parser.add_argument("--area-authority", type=Path, required=True)
    parser.add_argument("--r7b-manifest", type=Path, required=True)
    parser.add_argument("--r7b-qualification", type=Path, required=True)
    parser.add_argument("--area-confirmation-2023", type=Path, required=True)
    parser.add_argument("--area-confirmation-2024", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if config.get("task_id") != TASK_ID:
        raise RecoveryError("CONFIG_TASK_ID_MISMATCH")
    inputs = load_inputs(args, config)
    artifacts = build_artifacts(inputs)
    hashes = write_private_outputs(args.output_dir, artifacts, inputs["hashes"])
    summary = json.loads(artifacts["area-recovery-summary.json"].decode("utf-8"))
    print(
        json.dumps(
            {"output_dir": str(args.output_dir), "summary": summary, "artifact_sha256": hashes},
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RecoveryError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
