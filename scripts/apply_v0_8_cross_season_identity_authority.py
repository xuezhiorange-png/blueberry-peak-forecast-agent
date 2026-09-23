"""Apply the frozen, season-scoped business identity decisions to raw history.

The script rebuilds row-level authority and a daily canonical ledger from the
verified original XLS sources. It deliberately does not invoke any model,
forecast, fitting, or backtest path. Detailed outputs are private artifacts.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import json
import os
import stat
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
from pathlib import Path
from typing import Any

TASK_ID = "V0_8_S1_CROSS_SEASON_IDENTITY_AUTHORITY_APPLICATION_AND_CANONICAL_DATASET_REBUILD_R1"
AUTHORITY_ID = "CROSS_SEASON_BASE_IDENTITY_AUTHORITY_R1"
VERSION = "0.8.0"
SEASONS = ("2023-2024", "2024-2025", "2025-2026")
SEASON_WINDOWS = {
    "2023-2024": (date(2023, 7, 1), date(2024, 4, 15)),
    "2024-2025": (date(2024, 7, 1), date(2025, 4, 15)),
    "2025-2026": (date(2025, 7, 22), date(2026, 4, 15)),
}
RAW_SOURCE_HASHES = {
    "2023-2024": "8fa003b4abdea0b0bd9c50a9fbd619ad15ea5c9a2e790faa5e5b3353a2a01d20",
    "2024-2025": "f4ffba4b10a3129c768871bc5f3dfa2845534bc0e7eb04e166ba97211fa92dd6",
    "2025-2026": "fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a",
}
DECISIONS_SHA256 = "8730b4f3be9a33b86db4f057c31259ec0302d525d8a635aa4f98893558101089"
PROPOSAL_SHA256 = "69ee6067ae6c70ee0691abf85a6346b8a569257a407cebe09a3ef3ed81725424"
INPUT_MANIFEST_SHA256 = "d4414c70bdb1ad92cd2c9d54f63485579979686344c59047619e8348a364f327"
AUDIT_MANIFEST_SHA256 = "04e540ffa019dcfd07d4140dc498800f4df11e74184ff6db853fd4f2d9deb17b"
BUSINESS_PACKAGE_MANIFEST_SHA256 = (
    "bb38dbea3748948f0b72d7f5e192591805155eda79c46541c992b6a1d88cc0fd"
)
BUSINESS_DECISIONS_BY_QUESTION_SHA256 = (
    "8d5424f048a111d33d9644d247cce59b9cde3ff18df9840af3ffc965d831b402"
)
R7B_MANIFEST_SHA256 = "611507ab99c697ab72921bc478c598cee3315ca4ec103632d6ea158d320efbea"
HISTORICAL_AREA_AUTHORITY_SHA256 = (
    "231e769ebd004f02267eb4d2402f5745a8cb690ac873bb871f3db0bdb311eed2"
)
EXPECTED_TOTALS = {
    "2023-2024": {
        "raw": Decimal("30148211.706"),
        "mapped": Decimal("23551840.401"),
        "unresolved": Decimal("4957687.840"),
        "excluded": Decimal("1638683.465"),
        "business_mapped": Decimal("15135214.482"),
    },
    "2024-2025": {
        "raw": Decimal("42440018.628"),
        "mapped": Decimal("36755290.292"),
        "unresolved": Decimal("3924806.056"),
        "excluded": Decimal("1759922.280"),
        "business_mapped": Decimal("23758908.160"),
    },
    "2025-2026": {
        "raw": Decimal("50394920.579"),
        "mapped": Decimal("48703484.659"),
        "unresolved": Decimal("1691435.920"),
        "excluded": Decimal("0"),
        "business_mapped": Decimal("48070902.334"),
    },
}
EXPECTED_ALL_SEASONS = {
    "raw": Decimal("122983150.913"),
    "mapped": Decimal("109010615.352"),
    "unresolved": Decimal("10573929.816"),
    "excluded": Decimal("3398605.745"),
    "current_mapped": Decimal("90950421.578"),
    "mapped_gain": Decimal("18060193.774"),
}
PRIVATE_FILENAMES = (
    "cross-season-base-identity-authority-r1.csv",
    "cross-season-subfarm-parent-authority-r1.csv",
    "canonical-base-daily-ledger-r1.csv",
    "canonical-base-season-quality-r1.csv",
    "old-vs-new-identity-diff-r1.csv",
    "unresolved-identity-ledger-r1.csv",
)
AUTHORITY_FIELDS = (
    "identity_revision_id",
    "season",
    "source_farm_label",
    "mapping_status",
    "match_type",
    "canonical_base_id",
    "canonical_base_name",
    "candidate_base_ids",
    "candidate_base_names",
    "previous_mapping_status",
    "previous_base_id",
    "previous_base_name",
    "previous_authority",
    "mapping_authority",
    "decision_questions",
    "business_decisions",
    "decision_source",
    "decision_capture_sha256",
    "raw_source_sha256",
    "source_identity_sha256",
    "source_row_count",
    "source_quantity_kg",
    "business_window_quantity_kg",
    "effective_scope",
    "cross_season_propagation",
    "mapping_evidence",
)
SUBFARM_FIELDS = (
    "relation_revision_id",
    "season",
    "source_farm_label",
    "source_subfarm_label",
    "effective_parent_source_farm_label",
    "parent_relation_status",
    "decision_questions",
    "canonical_base_id_from_farm_identity",
    "canonical_base_name_from_farm_identity",
    "quantity_assignment_source_farm_label",
    "quantity_assignment_base_id",
    "quantity_reallocation_from_parent_correction",
    "raw_source_sha256",
    "source_row_count",
    "source_quantity_kg",
    "business_window_quantity_kg",
)
DAILY_FIELDS = (
    "base_id",
    "canonical_base_name",
    "season",
    "source_sha256",
    "date",
    "scope",
    "quantity_status",
    "mapped_observed_subtotal_kg",
    "quantity_completeness_status",
    "unknown_component_possible",
    "source_row_count",
    "contributing_source_label_count",
    "confirmed_zero_basis",
    "identity_authority_id",
    "identity_authority_sha256",
)
QUALITY_FIELDS = (
    "base_id",
    "canonical_base_name",
    "season",
    "reference_area_mu",
    "area_semantics",
    "historical_actual_productive_area_mu",
    "historical_actual_productive_area_status",
    "historical_area_source_sha256",
    "source_identity_status",
    "accepted_source_label_count",
    "accepted_source_labels",
    "unresolved_candidate_source_labels",
    "raw_mapped_quantity_kg",
    "business_window_mapped_quantity_kg",
    "business_window_observed_day_count",
    "first_observed_date",
    "last_observed_date",
    "business_window_calendar_day_count",
    "known_mapped_subtotal_day_count",
    "confirmed_zero_day_count",
    "unknown_day_count",
    "known_but_incomplete_day_count",
    "quantity_coverage_status",
    "business_total_coverage_status",
    "single_day_peak_coverage_status",
    "rolling_7day_coverage_status",
    "r7b_source_label_qualification_status",
    "r7b_base_aggregation_proven",
    "season_total_complete",
    "single_day_peak_complete",
    "rolling_7day_complete",
    "left_truncation_status",
    "right_truncation_status",
    "model_training_eligibility_evaluated",
)
OLD_NEW_FIELDS = (
    "season",
    "source_farm_label",
    "old_mapping_status",
    "old_base_id",
    "old_base_name",
    "new_mapping_status",
    "new_base_id",
    "new_base_name",
    "raw_source_quantity_kg",
    "business_window_quantity_kg",
    "old_mapped_quantity_kg",
    "new_mapped_quantity_kg",
    "mapped_quantity_delta_kg",
    "old_base_member_labels",
    "new_base_member_labels",
    "decision_questions",
)
UNRESOLVED_FIELDS = (
    "season",
    "source_farm_label",
    "source_subfarm_label",
    "mapping_status",
    "candidate_base_ids",
    "candidate_base_names",
    "decision_questions",
    "source_row_count",
    "raw_source_quantity_kg",
    "business_window_quantity_kg",
    "source_sha256",
)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decimal_text(value: Decimal | None) -> str:
    if value is None:
        return ""
    if value == 0:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def csv_bytes(rows: list[dict[str, Any]], fields: tuple[str, ...]) -> bytes:
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n", extrasaction="raise")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in fields})
    return b"\xef\xbb\xbf" + stream.getvalue().encode("utf-8")


def applied_mapping(proposal_row: dict[str, str]) -> dict[str, str]:
    """Convert the verified decision proposal to the new versioned authority status."""
    proposed_id = proposal_row.get("proposed_base_id", "").strip()
    proposed_status = proposal_row.get("proposed_status", "").strip()
    old_status = proposal_row.get("old_status", "").strip()
    old_id = proposal_row.get("old_base_id", "").strip()
    if proposed_id:
        if proposed_status not in {
            "EXACT",
            "AUTHORIZED_ALIAS",
            "HISTORICALLY_PROVEN_ALIAS",
            "PROPOSED_MAPPED_NON_AUTHORITY",
        }:
            raise ValueError("PROPOSED_BASE_WITH_UNSUPPORTED_STATUS")
        if old_status in {"EXACT", "AUTHORIZED_ALIAS", "HISTORICALLY_PROVEN_ALIAS"}:
            status = old_status if old_id == proposed_id else "BUSINESS_CONFIRMED_REASSIGNMENT"
        else:
            status = "BUSINESS_CONFIRMED_MAPPING"
        return {"status": status, "base_id": proposed_id}
    if proposed_status == "EXCLUDED" or old_status == "EXCLUDED":
        return {"status": "EXCLUDED", "base_id": ""}
    if old_status == "CONFLICTING":
        return {"status": "CONFLICTING", "base_id": ""}
    return {"status": "UNRESOLVED", "base_id": ""}


def _validate_business_decision_application(
    decision_rows: list[dict[str, str]],
    proposal_rows: list[dict[str, str]],
    build_info: dict[str, Any],
    audit_rows: list[dict[str, str]],
) -> dict[str, Any]:
    questions = {row["question_number"]: row for row in decision_rows}
    if not {"Q07", "Q10", "Q14", "Q17", "Q26"}.issubset(questions):
        raise ValueError("REQUIRED_BUSINESS_QUESTION_MISSING")
    q14_prior = [
        row
        for row in proposal_rows
        if row["season"] == "2024-2025"
        and "Q14" in row.get("decision_question", "").split(";")
        and "Q14:NO_CANDIDATE" in row.get("business_decision", "").split(";")
    ]
    q14_target = [
        row
        for row in proposal_rows
        if row["season"] == "2025-2026"
        and "Q14" in row.get("decision_question", "").split(";")
        and "Q14:YES_CANDIDATE" in row.get("business_decision", "").split(";")
    ]
    if (
        questions["Q14"].get("decision_2024_2025") != "NO_CANDIDATE"
        or questions["Q14"].get("decision_2025_2026") != "YES_CANDIDATE"
        or not q14_prior
        or not q14_target
        or not all(
            row.get("proposed_status") == "UNRESOLVED"
            and not row.get("proposed_base_id")
            and row.get("change_type") != "OUT_OF_SCOPE"
            for row in q14_prior
        )
        or not all(row.get("proposed_base_id") for row in q14_target)
    ):
        raise ValueError("Q14_SEASON_SCOPED_DECISION_APPLICATION_INVALID")

    q17_target_rows = [
        row
        for row in proposal_rows
        if "Q17" in row.get("decision_question", "").split(";")
        and row.get("change_type") == "SPLIT_RELATION"
    ]
    if len(q17_target_rows) != build_info.get("q17_target_row_count"):
        raise ValueError("Q17_SPLIT_ROWS_DO_NOT_MATCH_FROZEN_RULE_COUNT")
    unhandled = set(tuple(key) for key in build_info.get("q17_unhandled_source_label_keys", []))
    for row in proposal_rows:
        farm_key = (row["season"], row["source_farm_label"])
        if farm_key in unhandled and row.get("proposed_base_id"):
            raise ValueError("Q17_UNLISTED_SOURCE_LABEL_WAS_MAPPED")
        if farm_key in unhandled and row.get("proposed_status") not in {
            "UNRESOLVED",
            "CONFLICTING",
        }:
            raise ValueError("Q17_UNLISTED_SOURCE_LABEL_STATUS_NOT_UNRESOLVED")

    parent_rows = [row for row in proposal_rows if row.get("change_type") == "PARENT_CORRECTION"]
    if len(parent_rows) != build_info.get("parent_correction_row_count"):
        raise ValueError("PARENT_CORRECTION_ROWS_DO_NOT_MATCH_FROZEN_RULE_COUNT")
    for row in parent_rows:
        question_set = set(row.get("decision_question", "").split(";"))
        if not question_set.intersection({"Q07", "Q10"}):
            raise ValueError("UNAUTHORIZED_PARENT_CORRECTION_QUESTION")
        if row.get("old_base_id", "") != row.get("proposed_base_id", ""):
            raise ValueError("PARENT_CORRECTION_CHANGED_QUANTITY_ASSIGNMENT")

    audit_by_pair = {
        (row["season"], row["source_farm_label"], row["source_subfarm_label"]): row
        for row in audit_rows
    }
    for row in proposal_rows:
        pair_key = (row["season"], row["source_farm_label"], row["source_subfarm_label"])
        source = audit_by_pair.get(pair_key)
        if (
            source is None
            or row.get("quantity_kg") != source.get("quantity_kg")
            or row.get("business_window_quantity_kg") != source.get("business_window_quantity_kg")
        ):
            raise ValueError("BUSINESS_DECISION_CHANGED_SOURCE_QUANTITY")

    for row in proposal_rows:
        decisions = row.get("business_decision", "").split(";")
        for decision in decisions:
            question, _, _value = decision.partition(":")
            if question == "Q26" and not questions["Q26"].get(
                f"decision_{row['season'].replace('-', '_')}"
            ):
                raise ValueError("Q26_RULE_PROPAGATED_OUTSIDE_EXPLICIT_SEASON")

    return {
        "q14_prior_no_candidate_rows_remain_unresolved": len(q14_prior),
        "q14_target_season_rows_with_candidate": len(q14_target),
        "q17_split_relation_rows": len(q17_target_rows),
        "q17_unhandled_source_label_count": len(unhandled),
        "q07_q10_parent_correction_rows": len(parent_rows),
        "q07_q10_parent_corrections_reallocate_quantity": False,
        "q26_decisions_are_season_scoped": True,
        "all_decisions_exact_identity_and_season_scoped": True,
    }


def daily_quantity_status(
    *,
    source_rows_present: bool,
    mapped_quantity: Decimal,
    all_mapped_members_observed: bool,
    unresolved_candidate: bool,
    prior_confirmed_zero: bool,
    r7b_confirmed_zero: bool,
) -> tuple[str, str, bool, str]:
    """Return daily status without converting an unknown or partial subtotal to zero."""
    complete_observation = all_mapped_members_observed and not unresolved_candidate
    if source_rows_present:
        if mapped_quantity == 0 and complete_observation:
            return "CONFIRMED_ZERO", "COMPLETE_SOURCE_ROWS_ZERO", False, "RAW_SOURCE_EXPLICIT_ZERO"
        return (
            "KNOWN_MAPPED_SUBTOTAL",
            "COMPLETE_MAPPED_MEMBERS" if complete_observation else "PARTIAL_KNOWN_SUBTOTAL",
            not complete_observation,
            "RAW_SOURCE_MAPPED_ROWS",
        )
    if not unresolved_candidate and (prior_confirmed_zero or r7b_confirmed_zero):
        basis = (
            "REUSED_UNCHANGED_MEMBERSHIP_ZERO"
            if prior_confirmed_zero
            else "R7B_SOURCE_ZERO_SEMANTICS"
        )
        return "CONFIRMED_ZERO", "AUTHORIZED_ZERO", False, basis
    return "UNKNOWN", "UNKNOWN_NOT_ZERO_FILLED", True, ""


def validate_conservation(
    raw: Decimal, mapped: Decimal, unresolved: Decimal, excluded: Decimal
) -> Decimal:
    delta = raw - mapped - unresolved - excluded
    if delta != 0:
        raise ValueError(f"QUANTITY_RECONCILIATION_FAILED:{decimal_text(delta)}")
    return delta


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"EXPECTED_JSON_OBJECT:{path.name}")
    return value


def _verify_flat_hash_manifest(
    directory: Path, filename: str, expected_sha256: str
) -> dict[str, Any]:
    manifest_path = directory / filename
    if sha256_file(manifest_path) != expected_sha256:
        raise ValueError(f"FROZEN_MANIFEST_HASH_MISMATCH:{filename}")
    manifest = _read_json(manifest_path)
    if not manifest:
        raise ValueError(f"EMPTY_HASH_MANIFEST:{filename}")
    for relative_name, expected_digest in manifest.items():
        if not isinstance(expected_digest, str):
            raise ValueError(f"INVALID_HASH_MANIFEST_ENTRY:{filename}")
        artifact_path = directory / relative_name
        if not artifact_path.is_file() or sha256_file(artifact_path) != expected_digest:
            raise ValueError(f"HASH_MANIFEST_ARTIFACT_MISMATCH:{filename}:{relative_name}")
    return manifest


def _bool(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"true", "1", "yes"}


def _empty_unknown_day_list(value: str) -> bool:
    normalized = (value or "").strip()
    return normalized in {"()", "[]"}


def _parse_ids(value: str) -> list[str]:
    raw = (value or "").strip()
    if not raw:
        return []
    if raw.startswith("["):
        parsed = json.loads(raw)
        if not isinstance(parsed, list) or any(not isinstance(item, str) for item in parsed):
            raise ValueError("INVALID_BASE_ID_LIST")
        return sorted({item.strip() for item in parsed if item.strip()})
    return sorted({item.strip() for item in raw.split(";") if item.strip()})


def _source_path_map(root: Path) -> dict[str, Path]:
    return {
        "2023-2024": root / "historical-primary-source-replay-r1" / "23~24.xls",
        "2024-2025": root / "historical-primary-source-replay-r1" / "24~25.xls",
        "2025-2026": root / "source-25-26-r7" / "原果入库汇总表.xls",
    }


def _load_and_verify_inputs(root: Path, repository_root: Path) -> dict[str, Any]:
    proposal_module = importlib.import_module("scripts.propose_cross_season_identity_authority")
    audit_module = importlib.import_module("scripts.audit_cross_season_data_mapping")
    frozen = proposal_module.verify_frozen_inputs(root, repository_root)
    capture_dir = root / "cross-season-business-identity-decision-capture-r1"
    input_manifest = proposal_module._verify_manifest(capture_dir, INPUT_MANIFEST_SHA256)
    decision_path = capture_dir / "business-identity-confirmation-decisions-r1.csv"
    proposal_path = capture_dir / "proposed-cross-season-identity-authority-r1.csv"
    if proposal_module.sha256_file(decision_path) != DECISIONS_SHA256:
        raise ValueError("BUSINESS_DECISION_FILE_HASH_MISMATCH")
    if proposal_module.sha256_file(proposal_path) != PROPOSAL_SHA256:
        raise ValueError("FROZEN_PROPOSAL_FILE_HASH_MISMATCH")

    priority_rows = proposal_module._read_csv(
        frozen["package_dir"] / "business-identity-confirmation-priority.csv"
    )
    decision_rows = proposal_module._read_csv(decision_path)
    proposal_module.verify_decisions(decision_rows, priority_rows)
    computed_proposal, build_info = proposal_module.build_proposal(
        frozen["audit_rows"],
        priority_rows,
        decision_rows,
        frozen["base_names"],
    )
    decision_application = _validate_business_decision_application(
        decision_rows, computed_proposal, build_info, frozen["audit_rows"]
    )
    saved_proposal = proposal_module._read_csv(proposal_path)
    if computed_proposal != saved_proposal:
        raise ValueError("REGENERATED_PROPOSAL_BYTES_DO_NOT_MATCH_FROZEN_INPUT")
    decision_projection = {
        row["question_number"]: {
            key: row[key]
            for key in (
                "decision_2023_2024",
                "decision_2024_2025",
                "decision_2025_2026",
                "correct_base",
                "split_rule",
                "future_effective_rule",
            )
        }
        for row in decision_rows
    }
    if sha256_bytes(canonical_bytes(decision_projection)) != BUSINESS_DECISIONS_BY_QUESTION_SHA256:
        raise ValueError("BUSINESS_DECISION_PROJECTION_HASH_MISMATCH")

    source_rows: list[Any] = []
    source_hashes: dict[str, str] = {}
    for season, path in _source_path_map(root).items():
        digest = proposal_module.sha256_file(path)
        if digest != RAW_SOURCE_HASHES[season]:
            raise ValueError(f"RAW_SOURCE_HASH_MISMATCH:{season}")
        source_hashes[season] = digest
        source_rows.extend(audit_module.read_source_xls(path, season))

    registry_dir = root / "base-registry-s1-r2"
    registry_path = registry_dir / "base-registry-v1.json"
    member_path = registry_dir / "member-farm-mapping.csv"
    daily_path = registry_dir / "base-daily-ledger.csv"
    registry_manifest_path = registry_dir / "artifact-manifest.json"
    registry_manifest = _read_json(registry_manifest_path)
    registry_entries = registry_manifest
    for path in (registry_path, member_path, daily_path):
        entry = registry_entries.get(path.name)
        if not isinstance(entry, str) or proposal_module.sha256_file(path) != entry:
            raise ValueError(f"BASE_REGISTRY_ARTIFACT_HASH_MISMATCH:{path.name}")

    r7b_dir = root / "three-season-r7b"
    r7b_manifest = _verify_flat_hash_manifest(
        r7b_dir, "artifact_manifest.json", R7B_MANIFEST_SHA256
    )
    area_path = root / "product-integration-p1" / "authority.json"
    area_sha = proposal_module.sha256_file(area_path)
    if area_sha != HISTORICAL_AREA_AUTHORITY_SHA256:
        raise ValueError("HISTORICAL_AREA_AUTHORITY_HASH_MISMATCH")
    verified_input_hashes = {
        "raw_sources": source_hashes,
        "business_decisions": DECISIONS_SHA256,
        "business_decision_capture_manifest": INPUT_MANIFEST_SHA256,
        "frozen_proposal": PROPOSAL_SHA256,
        "source_audit_manifest": AUDIT_MANIFEST_SHA256,
        "business_confirmation_package_manifest": BUSINESS_PACKAGE_MANIFEST_SHA256,
        "previous_identity_authorities": frozen["authority_hashes"],
        "base_registry_artifact_manifest": proposal_module.sha256_file(registry_manifest_path),
        "base_daily_ledger": proposal_module.sha256_file(daily_path),
        "r7b_artifact_manifest": proposal_module.sha256_file(r7b_dir / "artifact_manifest.json"),
        "r7b_boundary_authority": proposal_module.sha256_file(r7b_dir / "boundary_authority.json"),
        "historical_area_authority": area_sha,
    }
    return {
        **frozen,
        "audit_module": audit_module,
        "proposal_module": proposal_module,
        "build_info": build_info,
        "decision_application": decision_application,
        "proposal_rows": computed_proposal,
        "decision_rows": decision_rows,
        "decision_sha256": DECISIONS_SHA256,
        "verified_input_hashes": verified_input_hashes,
        "decision_projection_sha256": BUSINESS_DECISIONS_BY_QUESTION_SHA256,
        "proposal_sha256": PROPOSAL_SHA256,
        "input_manifest_sha256": INPUT_MANIFEST_SHA256,
        "input_manifest": input_manifest,
        "source_rows": source_rows,
        "source_hashes": source_hashes,
        "base_registry": _read_json(registry_path),
        "base_registry_sha256": proposal_module.sha256_file(registry_path),
        "base_member_mapping_sha256": proposal_module.sha256_file(member_path),
        "base_daily_ledger": _read_csv(daily_path),
        "base_daily_ledger_sha256": proposal_module.sha256_file(daily_path),
        "base_registry_manifest_sha256": proposal_module.sha256_file(registry_manifest_path),
        "r7b_qualification": _read_csv(r7b_dir / "qualification_r7b.csv"),
        "r7b_qualification_sha256": proposal_module.sha256_file(r7b_dir / "qualification_r7b.csv"),
        "r7b_manifest_sha256": proposal_module.sha256_file(r7b_dir / "artifact_manifest.json"),
        "r7b_manifest": r7b_manifest,
        "r7b_boundary_authority": _read_json(r7b_dir / "boundary_authority.json"),
        "r7b_boundary_authority_sha256": proposal_module.sha256_file(
            r7b_dir / "boundary_authority.json"
        ),
        "historical_area_authority": _read_json(area_path),
        "historical_area_authority_sha256": area_sha,
    }


def _aggregate_source_rows(
    source_rows: list[Any],
) -> tuple[dict[Any, dict[str, Any]], dict[Any, dict[str, Any]]]:
    pair: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "rows": 0,
            "kg": Decimal(0),
            "business_kg": Decimal(0),
            "dates": set(),
            "business_dates": set(),
            "row_hashes": [],
        }
    )
    farm: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "rows": 0,
            "kg": Decimal(0),
            "business_kg": Decimal(0),
            "dates": set(),
            "business_dates": set(),
            "row_hashes": [],
        }
    )
    for row in source_rows:
        if row.season not in SEASONS:
            raise ValueError("UNEXPECTED_RAW_SOURCE_SEASON")
        if row.row_number < 2 or not row.raw_record_hash:
            raise ValueError("INVALID_RAW_SOURCE_ROW_IDENTITY")
        start, end = SEASON_WINDOWS[row.season]
        in_business = start <= row.event_date <= end
        for key, bucket in (
            ((row.season, row.farm, row.subfarm), pair[(row.season, row.farm, row.subfarm)]),
            ((row.season, row.farm), farm[(row.season, row.farm)]),
        ):
            del key
            bucket["rows"] += 1
            bucket["kg"] += row.quantity_kg
            bucket["dates"].add(row.event_date)
            bucket["row_hashes"].append(row.raw_record_hash)
            if in_business:
                bucket["business_kg"] += row.quantity_kg
                bucket["business_dates"].add(row.event_date)
    return pair, farm


def _mapping_rows(
    proposal_rows: list[dict[str, str]], audit_rows: list[dict[str, str]]
) -> tuple[
    dict[tuple[str, str, str], dict[str, str]],
    dict[tuple[str, str], dict[str, Any]],
]:
    audit_by_pair = {
        (row["season"], row["source_farm_label"], row["source_subfarm_label"]): row
        for row in audit_rows
    }
    proposal_by_pair: dict[tuple[str, str, str], dict[str, str]] = {}
    farm_map: dict[tuple[str, str], dict[str, Any]] = {}
    for row in proposal_rows:
        key = (row["season"], row["source_farm_label"], row["source_subfarm_label"])
        if key in proposal_by_pair or key not in audit_by_pair:
            raise ValueError("PROPOSAL_PAIR_KEY_MISMATCH")
        proposal_by_pair[key] = row
        mapping = applied_mapping(row)
        farm_key = key[:2]
        candidate = {
            **mapping,
            "proposal": row,
            "audit": audit_by_pair[key],
        }
        existing = farm_map.get(farm_key)
        if existing is not None and (existing["status"], existing["base_id"]) != (
            candidate["status"],
            candidate["base_id"],
        ):
            raise ValueError("SAME_SEASON_FARM_LABEL_HAS_MULTIPLE_APPLIED_BASES")
        farm_map[farm_key] = candidate
    if set(proposal_by_pair) != set(audit_by_pair):
        raise ValueError("PROPOSAL_DOES_NOT_COVER_ALL_RAW_IDENTITY_PAIRS")
    return proposal_by_pair, farm_map


def _make_identity_rows(
    source_farm_groups: dict[tuple[str, str], dict[str, Any]],
    farm_map: dict[tuple[str, str], dict[str, Any]],
    base_names: dict[str, str],
    source_hashes: dict[str, str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in sorted(source_farm_groups):
        season, farm = key
        source = source_farm_groups[key]
        resolved = farm_map[key]
        proposal = resolved["proposal"]
        audit = resolved["audit"]
        base_id = resolved["base_id"]
        if base_id and base_id not in base_names:
            raise ValueError("APPLIED_BASE_NOT_IN_FROZEN_REGISTRY")
        decision = proposal.get("business_decision", "")
        candidate_ids = []
        if resolved["status"] in {"UNRESOLVED", "CONFLICTING"} and "NO_CANDIDATE" not in decision:
            candidate_ids = _parse_ids(proposal.get("old_candidate_base_id", ""))
        candidate_names = [base_names[item] for item in candidate_ids if item in base_names]
        identity_hash = sha256_bytes(
            canonical_bytes(
                {
                    "season": season,
                    "source_farm_label": farm,
                    "source_hash": source_hashes[season],
                    "raw_row_hashes": sorted(source["row_hashes"]),
                }
            )
        )
        revision_id = sha256_bytes(
            canonical_bytes(
                {
                    "authority": AUTHORITY_ID,
                    "season": season,
                    "farm": farm,
                    "status": resolved["status"],
                    "base_id": base_id,
                    "decision": decision,
                }
            )
        )
        rows.append(
            {
                "identity_revision_id": revision_id,
                "season": season,
                "source_farm_label": farm,
                "mapping_status": resolved["status"],
                "match_type": (
                    "BUSINESS_CONFIRMED_DECISION"
                    if resolved["status"].startswith("BUSINESS_CONFIRMED")
                    else audit.get("current_match_type", "")
                ),
                "canonical_base_id": base_id,
                "canonical_base_name": base_names.get(base_id, "") if base_id else "",
                "candidate_base_ids": json_text(candidate_ids),
                "candidate_base_names": json_text(candidate_names),
                "previous_mapping_status": proposal.get("old_status", ""),
                "previous_base_id": proposal.get("old_base_id", ""),
                "previous_base_name": proposal.get("old_base_name", ""),
                "previous_authority": (
                    "HISTORICAL_IDENTITY_RECONSTRUCTION_R1"
                    if season in {"2023-2024", "2024-2025"}
                    else "BASE_MEMBER_MAPPING_R2"
                ),
                "mapping_authority": AUTHORITY_ID,
                "decision_questions": proposal.get("decision_question", ""),
                "business_decisions": decision,
                "decision_source": "USER_BUSINESS_CONFIRMATION_2026_09_23",
                "decision_capture_sha256": DECISIONS_SHA256,
                "raw_source_sha256": source_hashes[season],
                "source_identity_sha256": identity_hash,
                "source_row_count": str(source["rows"]),
                "source_quantity_kg": decimal_text(source["kg"]),
                "business_window_quantity_kg": decimal_text(source["business_kg"]),
                "effective_scope": "EXACT_SEASON_AND_SOURCE_FARM_LABEL_ONLY",
                "cross_season_propagation": "PROHIBITED",
                "mapping_evidence": audit.get("mapping_evidence", ""),
            }
        )
    return rows


def _make_subfarm_rows(
    pair_groups: dict[tuple[str, str, str], dict[str, Any]],
    proposal_by_pair: dict[tuple[str, str, str], dict[str, str]],
    farm_map: dict[tuple[str, str], dict[str, Any]],
    base_names: dict[str, str],
    source_hashes: dict[str, str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in sorted(pair_groups):
        season, farm, subfarm = key
        group = pair_groups[key]
        proposal = proposal_by_pair[key]
        mapping = farm_map[(season, farm)]
        corrected_parent = proposal.get("proposed_parent_source_farm_label", "").strip()
        parent = corrected_parent or farm
        relation_status = (
            "BUSINESS_CONFIRMED_PARENT_CORRECTION" if corrected_parent else "SOURCE_REPORTED_PARENT"
        )
        relation_id = sha256_bytes(
            canonical_bytes(
                {
                    "authority": AUTHORITY_ID,
                    "season": season,
                    "farm": farm,
                    "subfarm": subfarm,
                    "effective_parent": parent,
                }
            )
        )
        rows.append(
            {
                "relation_revision_id": relation_id,
                "season": season,
                "source_farm_label": farm,
                "source_subfarm_label": subfarm,
                "effective_parent_source_farm_label": parent,
                "parent_relation_status": relation_status,
                "decision_questions": proposal.get("decision_question", ""),
                "canonical_base_id_from_farm_identity": mapping["base_id"],
                "canonical_base_name_from_farm_identity": base_names.get(mapping["base_id"], "")
                if mapping["base_id"]
                else "",
                "quantity_assignment_source_farm_label": farm,
                "quantity_assignment_base_id": mapping["base_id"],
                "quantity_reallocation_from_parent_correction": "false",
                "raw_source_sha256": source_hashes[season],
                "source_row_count": str(group["rows"]),
                "source_quantity_kg": decimal_text(group["kg"]),
                "business_window_quantity_kg": decimal_text(group["business_kg"]),
            }
        )
    return rows


def _load_r7b_by_farm(qualification_rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for row in qualification_rows:
        label = row.get("canonical_farm", "")
        if not label or row.get("season") != "2025-2026" or label in result:
            raise ValueError("R7B_QUALIFICATION_IDENTITY_INVALID")
        result[label] = row
    return result


def _r7b_rows_for_base_season(
    season: str, member_labels: list[str], r7b_by_farm: dict[str, dict[str, str]]
) -> list[dict[str, str]]:
    """Bind R7B qualification only to its authorized 2025-2026 season."""
    if season != "2025-2026":
        return []
    return [r7b_by_farm[label] for label in member_labels if label in r7b_by_farm]


def _make_canonical_rows(
    source_rows: list[Any],
    farm_map: dict[tuple[str, str], dict[str, Any]],
    base_registry: dict[str, Any],
    old_daily_rows: list[dict[str, str]],
    r7b_by_farm: dict[str, dict[str, str]],
    source_hashes: dict[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    bases = base_registry.get("bases", [])
    if len(bases) != 39 or len({item.get("base_id") for item in bases}) != 39:
        raise ValueError("CURRENT_BASE_REGISTRY_MUST_HAVE_39_UNIQUE_BASES")
    base_names = {item["base_id"]: item["canonical_base_name"] for item in bases}
    base_records = {item["base_id"]: item for item in bases}
    source_rows_by_base_day: dict[tuple[str, str, date], list[Any]] = defaultdict(list)
    source_labels_by_base_season: dict[tuple[str, str], set[str]] = defaultdict(set)
    mapped_all_kg: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    mapped_business_kg: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    mapped_all_days: dict[tuple[str, str], set[date]] = defaultdict(set)
    mapped_business_days: dict[tuple[str, str], set[date]] = defaultdict(set)
    unresolved_labels_by_base: dict[tuple[str, str], set[str]] = defaultdict(set)

    for (season, farm), mapping in farm_map.items():
        if mapping["status"] in {"UNRESOLVED", "CONFLICTING"}:
            proposal = mapping["proposal"]
            decision = proposal.get("business_decision", "")
            if "NO_CANDIDATE" not in decision:
                for candidate_id in _parse_ids(proposal.get("old_candidate_base_id", "")):
                    if candidate_id in base_names:
                        unresolved_labels_by_base[(season, candidate_id)].add(farm)

    seen_source_rows: set[tuple[str, str, int]] = set()
    season_amounts: dict[str, dict[str, Decimal]] = {
        season: {
            metric_name: Decimal(0)
            for metric_name in ("raw", "mapped", "unresolved", "excluded", "business_mapped")
        }
        for season in SEASONS
    }
    conflicting_kg: dict[str, Decimal] = {season: Decimal(0) for season in SEASONS}
    for row in source_rows:
        row_identity = (row.season, row.sheet, row.row_number)
        if row_identity in seen_source_rows:
            raise ValueError("RAW_SOURCE_ROW_IDENTITY_DUPLICATED")
        seen_source_rows.add(row_identity)
        mapping = farm_map[(row.season, row.farm)]
        season_amounts[row.season]["raw"] += row.quantity_kg
        if mapping["status"] in {
            "EXACT",
            "AUTHORIZED_ALIAS",
            "HISTORICALLY_PROVEN_ALIAS",
            "BUSINESS_CONFIRMED_MAPPING",
            "BUSINESS_CONFIRMED_REASSIGNMENT",
        }:
            base_id = mapping["base_id"]
            if base_id not in base_names:
                raise ValueError("ACCEPTED_SOURCE_ROW_HAS_NO_CANONICAL_BASE")
            key = (row.season, base_id)
            season_amounts[row.season]["mapped"] += row.quantity_kg
            mapped_all_kg[key] += row.quantity_kg
            source_labels_by_base_season[key].add(row.farm)
            mapped_all_days[key].add(row.event_date)
            start, end = SEASON_WINDOWS[row.season]
            if start <= row.event_date <= end:
                season_amounts[row.season]["business_mapped"] += row.quantity_kg
                mapped_business_kg[key] += row.quantity_kg
                mapped_business_days[key].add(row.event_date)
                source_rows_by_base_day[(row.season, base_id, row.event_date)].append(row)
        elif mapping["status"] == "EXCLUDED":
            season_amounts[row.season]["excluded"] += row.quantity_kg
        else:
            season_amounts[row.season]["unresolved"] += row.quantity_kg
            if mapping["status"] == "CONFLICTING":
                conflicting_kg[row.season] += row.quantity_kg

    for season in SEASONS:
        validate_conservation(
            season_amounts[season]["raw"],
            season_amounts[season]["mapped"],
            season_amounts[season]["unresolved"],
            season_amounts[season]["excluded"],
        )
        for metric_name, expected in EXPECTED_TOTALS[season].items():
            if season_amounts[season][metric_name] != expected:
                raise ValueError(
                    f"FROZEN_EXPECTED_TOTAL_MISMATCH:{season}:{metric_name}:"
                    f"{decimal_text(season_amounts[season][metric_name])}"
                )

    old_member_labels: dict[tuple[str, str], set[str]] = defaultdict(set)
    new_member_labels = source_labels_by_base_season
    for (season, farm), mapping in farm_map.items():
        proposal = mapping["proposal"]
        old_id = proposal.get("old_base_id", "")
        if (
            proposal.get("old_status") in {"EXACT", "AUTHORIZED_ALIAS", "HISTORICALLY_PROVEN_ALIAS"}
            and old_id
        ):
            old_member_labels[(season, old_id)].add(farm)

    prior_zero_days: dict[tuple[str, str], set[date]] = defaultdict(set)
    for row in old_daily_rows:
        if (
            row.get("observation_status") == "OBSERVED_OR_AUTHORIZED_LEDGER_ZERO"
            and Decimal(row.get("recorded_harvest_kg") or "0") == 0
            and row.get("scope") == "BUSINESS_SCOPE"
            and row.get("source_hash") == source_hashes.get(row.get("season", ""))
        ):
            prior_zero_days[(row["base_id"], row["season"])].add(date.fromisoformat(row["date"]))

    r7b_zero_qualified = {
        farm
        for farm, row in r7b_by_farm.items()
        if _bool(row.get("source_complete"))
        and _bool(row.get("ledger_zero_semantics_authorized"))
        and row.get("season_completeness_status") == "STRICT_ELIGIBLE"
        and _empty_unknown_day_list(row.get("active_span_global_unknown_days", ""))
        and row.get("source_hash") == source_hashes["2025-2026"]
    }
    daily_rows: list[dict[str, Any]] = []
    daily_status: dict[tuple[str, str, date], dict[str, Any]] = {}
    for season in SEASONS:
        start, end = SEASON_WINDOWS[season]
        for base_id in sorted(base_names):
            members = new_member_labels.get((season, base_id), set())
            has_unresolved_candidate = bool(unresolved_labels_by_base.get((season, base_id)))
            old_members_unchanged = bool(members) and members == old_member_labels.get(
                (season, base_id), set()
            )
            r7b_zero_scope = (
                season == "2025-2026"
                and bool(members)
                and members.issubset(r7b_zero_qualified)
                and not has_unresolved_candidate
            )
            for offset in range((end - start).days + 1):
                day = start + timedelta(days=offset)
                raw_for_base_day = source_rows_by_base_day.get((season, base_id, day), [])
                quantity = sum((row.quantity_kg for row in raw_for_base_day), Decimal(0))
                contributing_labels = {row.farm for row in raw_for_base_day}
                all_members_observed = bool(members) and contributing_labels == members
                old_zero = (
                    day in prior_zero_days.get((base_id, season), set()) and old_members_unchanged
                )
                r7b_zero = r7b_zero_scope and not raw_for_base_day
                status, completeness, unknown_possible, zero_basis = daily_quantity_status(
                    source_rows_present=bool(raw_for_base_day),
                    mapped_quantity=quantity,
                    all_mapped_members_observed=all_members_observed,
                    unresolved_candidate=has_unresolved_candidate,
                    prior_confirmed_zero=old_zero,
                    r7b_confirmed_zero=r7b_zero,
                )
                value = None if status == "UNKNOWN" else quantity
                row_obj = {
                    "base_id": base_id,
                    "canonical_base_name": base_names[base_id],
                    "season": season,
                    "source_sha256": source_hashes[season],
                    "date": day.isoformat(),
                    "scope": "BUSINESS_WINDOW",
                    "quantity_status": status,
                    "mapped_observed_subtotal_kg": decimal_text(value),
                    "quantity_completeness_status": completeness,
                    "unknown_component_possible": str(unknown_possible).lower(),
                    "source_row_count": str(len(raw_for_base_day)),
                    "contributing_source_label_count": str(len(contributing_labels)),
                    "confirmed_zero_basis": zero_basis,
                    "identity_authority_id": AUTHORITY_ID,
                    "identity_authority_sha256": "PENDING_AUTHORITY_HASH",
                }
                daily_rows.append(row_obj)
                daily_status[(season, base_id, day)] = row_obj

    # Apply actual-area authority only when the exact source label resolves to one
    # Base and that Base has no additional accepted source-label member.
    # The caller binds verified area rows after canonical mapping; keep this
    # function independent from filesystem paths.
    quality_rows: list[dict[str, Any]] = []
    for season in SEASONS:
        start, end = SEASON_WINDOWS[season]
        business_days = (end - start).days + 1
        for base_id in sorted(base_names):
            key = (season, base_id)
            member_labels = sorted(new_member_labels.get(key, set()))
            unresolved_labels = sorted(unresolved_labels_by_base.get(key, set()))
            status_counts = Counter(
                daily_status[(season, base_id, start + timedelta(days=i))]["quantity_status"]
                for i in range(business_days)
            )
            partial_days = sum(
                daily_status[(season, base_id, start + timedelta(days=i))][
                    "quantity_completeness_status"
                ]
                == "PARTIAL_KNOWN_SUBTOTAL"
                for i in range(business_days)
            )
            base_r7b_rows = _r7b_rows_for_base_season(season, member_labels, r7b_by_farm)
            r7b_aggregation_proven = (
                season == "2025-2026"
                and bool(member_labels)
                and len(base_r7b_rows) == len(member_labels)
                and not unresolved_labels
                and all(
                    row.get("coverage_start") == start.isoformat()
                    and row.get("coverage_end") == end.isoformat()
                    and row.get("source_hash") == source_hashes[season]
                    and _bool(row.get("source_complete"))
                    and _bool(row.get("ledger_zero_semantics_authorized"))
                    and row.get("season_completeness_status") == "STRICT_ELIGIBLE"
                    for row in base_r7b_rows
                )
            )
            r7b_total_eligible = r7b_aggregation_proven and all(
                _bool(row.get("total_evaluable")) for row in base_r7b_rows
            )
            r7b_shape_eligible = r7b_aggregation_proven and all(
                _bool(row.get("shape_evaluable")) for row in base_r7b_rows
            )
            # Preserve the frozen R7B metric-specific authority. Unknown daily
            # support is reported separately and must not override its explicit
            # business-total / shape computability decisions.
            total_complete = r7b_total_eligible
            peak_complete = r7b_shape_eligible and all(
                row.get("peak_evaluation_status") in {"COMPUTABLE", "PASS"} for row in base_r7b_rows
            )
            rolling_complete = r7b_shape_eligible and all(
                row.get("seven_day_evaluation_status") in {"COMPUTABLE", "PASS"}
                for row in base_r7b_rows
            )
            daily_coverage_status = (
                "KNOWN_SUPPORT_PARTIAL_OR_UNKNOWN"
                if status_counts["UNKNOWN"] or partial_days
                else "KNOWN_SUPPORT_NO_UNKNOWN_DAYS"
            )
            business_total_status = (
                "BUSINESS_TOTAL_AUTHORITY_ELIGIBLE"
                if r7b_total_eligible
                else "NOT_COMPUTABLE_FROZEN_AUTHORITY_OR_BASE_SCOPE"
                if season == "2025-2026"
                else "NOT_ESTABLISHED_NO_FROZEN_TOTAL_AUTHORITY"
            )
            peak_coverage_status = (
                "PEAK_AUTHORITY_ELIGIBLE"
                if peak_complete
                else "NOT_COMPUTABLE_FROZEN_AUTHORITY_OR_BASE_SCOPE"
            )
            rolling_coverage_status = (
                "ROLLING7_AUTHORITY_ELIGIBLE"
                if rolling_complete
                else "NOT_COMPUTABLE_FROZEN_AUTHORITY_OR_BASE_SCOPE"
            )
            reference_area = base_records[base_id].get("productive_area_mu", "")
            quality_rows.append(
                {
                    "base_id": base_id,
                    "canonical_base_name": base_names[base_id],
                    "season": season,
                    "reference_area_mu": reference_area,
                    "area_semantics": "REFERENCE_AREA_ONLY",
                    "historical_actual_productive_area_mu": "",
                    "historical_actual_productive_area_status": "NOT_ESTABLISHED",
                    "historical_area_source_sha256": "",
                    "source_identity_status": (
                        "IDENTITY_CONFIRMED_WITH_UNRESOLVED_CANDIDATES"
                        if member_labels and unresolved_labels
                        else "IDENTITY_CONFIRMED"
                        if member_labels
                        else "IDENTITY_UNRESOLVED"
                        if unresolved_labels
                        else "NO_ACCEPTED_SOURCE_ROWS"
                    ),
                    "accepted_source_label_count": str(len(member_labels)),
                    "accepted_source_labels": json_text(member_labels),
                    "unresolved_candidate_source_labels": json_text(unresolved_labels),
                    "raw_mapped_quantity_kg": decimal_text(mapped_all_kg[key]),
                    "business_window_mapped_quantity_kg": decimal_text(mapped_business_kg[key]),
                    "business_window_observed_day_count": str(len(mapped_business_days[key])),
                    "first_observed_date": min(mapped_business_days[key]).isoformat()
                    if mapped_business_days[key]
                    else "",
                    "last_observed_date": max(mapped_business_days[key]).isoformat()
                    if mapped_business_days[key]
                    else "",
                    "business_window_calendar_day_count": str(business_days),
                    "known_mapped_subtotal_day_count": str(status_counts["KNOWN_MAPPED_SUBTOTAL"]),
                    "confirmed_zero_day_count": str(status_counts["CONFIRMED_ZERO"]),
                    "unknown_day_count": str(status_counts["UNKNOWN"]),
                    "known_but_incomplete_day_count": str(partial_days),
                    "quantity_coverage_status": daily_coverage_status,
                    "business_total_coverage_status": business_total_status,
                    "single_day_peak_coverage_status": peak_coverage_status,
                    "rolling_7day_coverage_status": rolling_coverage_status,
                    "r7b_source_label_qualification_status": (
                        "QUALIFIED_SOURCE_LABELS"
                        if len(base_r7b_rows) == len(member_labels) and base_r7b_rows
                        else "NOT_QUALIFIED_OR_NOT_APPLICABLE"
                    ),
                    "r7b_base_aggregation_proven": str(r7b_aggregation_proven).lower(),
                    "season_total_complete": str(total_complete).lower(),
                    "single_day_peak_complete": str(peak_complete).lower(),
                    "rolling_7day_complete": str(rolling_complete).lower(),
                    "left_truncation_status": (
                        "NOT_ESTABLISHED" if season != "2025-2026" else "NO_LEFT_TRUNCATION_PER_R7B"
                    ),
                    "right_truncation_status": (
                        "NOT_ESTABLISHED"
                        if season != "2025-2026"
                        else "NO_RIGHT_TRUNCATION_PER_R7B"
                    ),
                    "model_training_eligibility_evaluated": "false",
                }
            )

    summary = {
        "season_amounts": {
            season: {key: value for key, value in season_amounts[season].items()}
            for season in SEASONS
        },
        "conflicting_kg": dict(conflicting_kg),
        "old_member_labels": old_member_labels,
        "new_member_labels": new_member_labels,
        "daily_status": daily_status,
        "daily_row_count": len(daily_rows),
        "quality_row_count": len(quality_rows),
        "source_rows_seen": len(seen_source_rows),
    }
    return daily_rows, quality_rows, summary


def _bind_area_authority(
    quality_rows: list[dict[str, Any]],
    area_authority: dict[str, Any],
    area_sha256: str,
    farm_map: dict[tuple[str, str], dict[str, Any]],
    member_labels: dict[tuple[str, str], set[str]],
) -> None:
    names_by_key = farm_map
    for area in area_authority.get("history", []):
        season = area.get("season", "")
        farm = area.get("farm", "")
        if (
            area.get("area_basis") != "BUSINESS_CONFIRMED"
            or area.get("completeness") != "STRICT_ELIGIBLE"
        ):
            continue
        mapped = names_by_key.get((season, farm))
        if not mapped or not mapped["base_id"]:
            continue
        base_id = mapped["base_id"]
        labels = member_labels.get((season, base_id), set())
        if labels != {farm}:
            continue
        quality = next(
            row for row in quality_rows if row["season"] == season and row["base_id"] == base_id
        )
        quality["historical_actual_productive_area_mu"] = area.get("historical_area_mu", "")
        quality["historical_actual_productive_area_status"] = (
            "BUSINESS_CONFIRMED_SOURCE_LABEL_BOUND"
        )
        quality["historical_area_source_sha256"] = area_sha256


def build_artifacts(inputs: dict[str, Any]) -> dict[str, Any]:
    pair_groups, farm_groups = _aggregate_source_rows(inputs["source_rows"])
    if len(pair_groups) != 466 or len(farm_groups) != 228:
        raise ValueError("RAW_SOURCE_IDENTITY_INVENTORY_COUNT_MISMATCH")
    raw_identity_rows = inputs["audit_rows"]
    proposal_by_pair, farm_map = _mapping_rows(inputs["proposal_rows"], raw_identity_rows)
    # Direct raw pair aggregates must agree with the frozen audit ledger and proposal.
    audit_by_pair = {
        (row["season"], row["source_farm_label"], row["source_subfarm_label"]): row
        for row in raw_identity_rows
    }
    for key, grouped in pair_groups.items():
        audit = audit_by_pair[key]
        proposal = proposal_by_pair[key]
        if (
            grouped["rows"] != int(audit["raw_row_count"])
            or grouped["kg"] != Decimal(audit["quantity_kg"])
            or grouped["business_kg"] != Decimal(audit["business_window_quantity_kg"])
            or grouped["kg"] != Decimal(proposal["quantity_kg"])
            or grouped["business_kg"] != Decimal(proposal["business_window_quantity_kg"])
        ):
            raise ValueError("RAW_SOURCE_TO_FROZEN_IDENTITY_LEDGER_PARITY_FAILURE")

    base_names = inputs["base_names"]
    identity_rows = _make_identity_rows(farm_groups, farm_map, base_names, inputs["source_hashes"])
    subfarm_rows = _make_subfarm_rows(
        pair_groups, proposal_by_pair, farm_map, base_names, inputs["source_hashes"]
    )
    r7b_by_farm = _load_r7b_by_farm(inputs["r7b_qualification"])
    daily_rows, quality_rows, dataset_summary = _make_canonical_rows(
        inputs["source_rows"],
        farm_map,
        inputs["base_registry"],
        inputs["base_daily_ledger"],
        r7b_by_farm,
        inputs["source_hashes"],
    )
    _bind_area_authority(
        quality_rows,
        inputs["historical_area_authority"],
        inputs["historical_area_authority_sha256"],
        farm_map,
        dataset_summary["new_member_labels"],
    )
    identity_bytes = csv_bytes(identity_rows, AUTHORITY_FIELDS)
    identity_sha256 = sha256_bytes(identity_bytes)
    for row in daily_rows:
        row["identity_authority_sha256"] = identity_sha256
    # Re-render after hash binding; the authority hash is over exact canonical CSV bytes.
    identity_bytes = csv_bytes(identity_rows, AUTHORITY_FIELDS)
    if sha256_bytes(identity_bytes) != identity_sha256:
        raise ValueError("IDENTITY_AUTHORITY_HASH_NOT_STABLE")
    daily_bytes = csv_bytes(daily_rows, DAILY_FIELDS)
    quality_bytes = csv_bytes(quality_rows, QUALITY_FIELDS)

    old_member_json = {
        f"{season}|{base}": sorted(labels)
        for (season, base), labels in dataset_summary["old_member_labels"].items()
    }
    new_member_json = {
        f"{season}|{base}": sorted(labels)
        for (season, base), labels in dataset_summary["new_member_labels"].items()
    }
    identity_by_key = {(row["season"], row["source_farm_label"]): row for row in identity_rows}
    diff_rows: list[dict[str, Any]] = []
    unresolved_rows: list[dict[str, Any]] = []
    for key in sorted(farm_groups):
        season, farm = key
        group = farm_groups[key]
        applied = identity_by_key[key]
        old_id = applied["previous_base_id"]
        new_id = applied["canonical_base_id"]
        old_qty = group["kg"] if old_id else Decimal(0)
        new_qty = group["kg"] if new_id else Decimal(0)
        old_members = (
            sorted(dataset_summary["old_member_labels"].get((season, old_id), set()))
            if old_id
            else []
        )
        new_members = (
            sorted(dataset_summary["new_member_labels"].get((season, new_id), set()))
            if new_id
            else []
        )
        diff_rows.append(
            {
                "season": season,
                "source_farm_label": farm,
                "old_mapping_status": applied["previous_mapping_status"],
                "old_base_id": old_id,
                "old_base_name": applied["previous_base_name"],
                "new_mapping_status": applied["mapping_status"],
                "new_base_id": new_id,
                "new_base_name": applied["canonical_base_name"],
                "raw_source_quantity_kg": decimal_text(group["kg"]),
                "business_window_quantity_kg": decimal_text(group["business_kg"]),
                "old_mapped_quantity_kg": decimal_text(old_qty),
                "new_mapped_quantity_kg": decimal_text(new_qty),
                "mapped_quantity_delta_kg": decimal_text(new_qty - old_qty),
                "old_base_member_labels": json_text(old_members),
                "new_base_member_labels": json_text(new_members),
                "decision_questions": applied["decision_questions"],
            }
        )
        if applied["mapping_status"] in {"UNRESOLVED", "CONFLICTING"}:
            candidate_ids = json.loads(applied["candidate_base_ids"] or "[]")
            candidate_names = json.loads(applied["candidate_base_names"] or "[]")
            for pair_key in sorted(key for key in proposal_by_pair if key[:2] == (season, farm)):
                proposal = proposal_by_pair[pair_key]
                group_pair = pair_groups[pair_key]
                unresolved_rows.append(
                    {
                        "season": season,
                        "source_farm_label": farm,
                        "source_subfarm_label": pair_key[2],
                        "mapping_status": applied["mapping_status"],
                        "candidate_base_ids": json_text(candidate_ids),
                        "candidate_base_names": json_text(candidate_names),
                        "decision_questions": proposal.get("decision_question", ""),
                        "source_row_count": str(group_pair["rows"]),
                        "raw_source_quantity_kg": decimal_text(group_pair["kg"]),
                        "business_window_quantity_kg": decimal_text(group_pair["business_kg"]),
                        "source_sha256": inputs["source_hashes"][season],
                    }
                )

    output_bytes = {
        "cross-season-base-identity-authority-r1.csv": identity_bytes,
        "cross-season-subfarm-parent-authority-r1.csv": csv_bytes(subfarm_rows, SUBFARM_FIELDS),
        "canonical-base-daily-ledger-r1.csv": daily_bytes,
        "canonical-base-season-quality-r1.csv": quality_bytes,
        "old-vs-new-identity-diff-r1.csv": csv_bytes(diff_rows, OLD_NEW_FIELDS),
        "unresolved-identity-ledger-r1.csv": csv_bytes(unresolved_rows, UNRESOLVED_FIELDS),
    }
    if tuple(output_bytes) != PRIVATE_FILENAMES:
        raise ValueError("PRIVATE_ARTIFACT_SET_INVALID")
    if len(quality_rows) != 117:
        raise ValueError("BASE_SEASON_QUALITY_MUST_BE_39_BY_3")
    if (
        sum(dataset_summary["season_amounts"][s]["raw"] for s in SEASONS)
        != EXPECTED_ALL_SEASONS["raw"]
    ):
        raise ValueError("ALL_SEASON_RAW_TOTAL_MISMATCH")
    all_mapped = sum(dataset_summary["season_amounts"][s]["mapped"] for s in SEASONS)
    all_unresolved = sum(dataset_summary["season_amounts"][s]["unresolved"] for s in SEASONS)
    all_excluded = sum(dataset_summary["season_amounts"][s]["excluded"] for s in SEASONS)
    validate_conservation(EXPECTED_ALL_SEASONS["raw"], all_mapped, all_unresolved, all_excluded)
    for key in ("mapped", "unresolved", "excluded"):
        if locals()[f"all_{key}"] != EXPECTED_ALL_SEASONS[key]:
            raise ValueError(f"ALL_SEASON_{key.upper()}_TOTAL_MISMATCH")
    current_mapped = sum(
        (
            Decimal(str(row["quantity_kg"]))
            for row in inputs["audit_rows"]
            if row["current_mapping_status"]
            in {"EXACT", "AUTHORIZED_ALIAS", "HISTORICALLY_PROVEN_ALIAS"}
        ),
        Decimal(0),
    )
    if current_mapped != EXPECTED_ALL_SEASONS["current_mapped"]:
        raise ValueError("CURRENT_MAPPING_TOTAL_MISMATCH")
    if all_mapped - current_mapped != EXPECTED_ALL_SEASONS["mapped_gain"]:
        raise ValueError("MAPPED_GAIN_TOTAL_MISMATCH")
    business_total = sum(
        (dataset_summary["season_amounts"][s]["business_mapped"] for s in SEASONS),
        Decimal(0),
    )
    expected_business_total = sum(
        (EXPECTED_TOTALS[s]["business_mapped"] for s in SEASONS), Decimal(0)
    )
    if business_total != expected_business_total:
        raise ValueError("BUSINESS_WINDOW_AGGREGATE_INTERNAL_ERROR")
    return {
        "output_bytes": output_bytes,
        "identity_rows": identity_rows,
        "subfarm_rows": subfarm_rows,
        "daily_rows": daily_rows,
        "quality_rows": quality_rows,
        "diff_rows": diff_rows,
        "unresolved_rows": unresolved_rows,
        "dataset_summary": dataset_summary,
        "identity_authority_sha256": identity_sha256,
        "daily_sha256": sha256_bytes(daily_bytes),
        "quality_sha256": sha256_bytes(quality_bytes),
        "raw_label_count": len(farm_groups),
        "pair_identity_count": len(pair_groups),
        "mapped_label_count": sum(
            row["mapping_status"] not in {"UNRESOLVED", "CONFLICTING", "EXCLUDED"}
            for row in identity_rows
        ),
        "unresolved_label_count": sum(
            row["mapping_status"] == "UNRESOLVED" for row in identity_rows
        ),
        "conflicting_label_count": sum(
            row["mapping_status"] == "CONFLICTING" for row in identity_rows
        ),
        "excluded_label_count": sum(row["mapping_status"] == "EXCLUDED" for row in identity_rows),
        "business_decision_build_info": inputs["build_info"],
    }


def _public_evidence(
    inputs: dict[str, Any], artifacts: dict[str, Any], base_sha: str
) -> dict[str, Any]:
    amounts = artifacts["dataset_summary"]["season_amounts"]
    per_season: dict[str, Any] = {}
    per_season_quality: dict[str, Any] = {}
    for season in SEASONS:
        bucket = amounts[season]
        quality = [row for row in artifacts["quality_rows"] if row["season"] == season]
        daily = [row for row in artifacts["daily_rows"] if row["season"] == season]
        per_season[season] = {
            "raw_source_kg": decimal_text(bucket["raw"]),
            "mapped_kg": decimal_text(bucket["mapped"]),
            "unresolved_kg": decimal_text(bucket["unresolved"]),
            "conflicting_subset_kg": decimal_text(
                artifacts["dataset_summary"]["conflicting_kg"].get(season, Decimal(0))
            ),
            "explicitly_excluded_kg": decimal_text(bucket["excluded"]),
            "mapped_rate": decimal_text(bucket["mapped"] / bucket["raw"]),
            "business_window_mapped_kg": decimal_text(bucket["business_mapped"]),
            "business_start": SEASON_WINDOWS[season][0].isoformat(),
            "business_end": SEASON_WINDOWS[season][1].isoformat(),
            "business_boundary_authority": (
                "USER_CONFIRMED_2526_BUSINESS_WINDOW_R7B"
                if season == "2025-2026"
                else "FROZEN_CROSS_SEASON_AUDIT_WINDOW_R1"
            ),
        }
        per_season_quality[season] = {
            "base_season_rows": len(quality),
            "daily_rows": len(daily),
            "daily_quantity_coverage_status_counts": dict(
                sorted(Counter(row["quantity_coverage_status"] for row in quality).items())
            ),
            "business_total_coverage_status_counts": dict(
                sorted(Counter(row["business_total_coverage_status"] for row in quality).items())
            ),
            "single_day_peak_coverage_status_counts": dict(
                sorted(Counter(row["single_day_peak_coverage_status"] for row in quality).items())
            ),
            "rolling_7day_coverage_status_counts": dict(
                sorted(Counter(row["rolling_7day_coverage_status"] for row in quality).items())
            ),
            "business_total_evaluable_base_season_count": sum(
                row["season_total_complete"] == "true" for row in quality
            ),
            "single_day_peak_evaluable_base_season_count": sum(
                row["single_day_peak_complete"] == "true" for row in quality
            ),
            "rolling_7day_evaluable_base_season_count": sum(
                row["rolling_7day_complete"] == "true" for row in quality
            ),
            "reference_area_only_base_season_count": sum(
                row["area_semantics"] == "REFERENCE_AREA_ONLY" for row in quality
            ),
            "business_confirmed_historical_area_base_season_count": sum(
                row["historical_actual_productive_area_status"]
                == "BUSINESS_CONFIRMED_SOURCE_LABEL_BOUND"
                for row in quality
            ),
        }
    return {
        "task_id": TASK_ID,
        "version": VERSION,
        "authority_id": AUTHORITY_ID,
        "base_sha": base_sha,
        "source_hashes": inputs["source_hashes"],
        "verified_input_hashes": inputs["verified_input_hashes"],
        "previous_authority_hashes": inputs["authority_hashes"],
        "business_decisions_sha256": inputs["decision_sha256"],
        "business_decisions_by_question_sha256": inputs["decision_projection_sha256"],
        "business_decision_capture_manifest_sha256": inputs["input_manifest_sha256"],
        "source_audit_manifest_sha256": AUDIT_MANIFEST_SHA256,
        "confirmation_package_manifest_sha256": BUSINESS_PACKAGE_MANIFEST_SHA256,
        "private_authority_sha256": artifacts["identity_authority_sha256"],
        "private_canonical_daily_ledger_sha256": artifacts["daily_sha256"],
        "private_quality_ledger_sha256": artifacts["quality_sha256"],
        "private_artifact_file_sha256": {
            name: sha256_bytes(content) for name, content in artifacts["output_bytes"].items()
        },
        "private_artifact_row_counts": {
            name: max(0, len(content.decode("utf-8-sig").splitlines()) - 1)
            for name, content in artifacts["output_bytes"].items()
        },
        "historical_area_authority_sha256": inputs["historical_area_authority_sha256"],
        "base_daily_ledger_authority_sha256": inputs["base_daily_ledger_sha256"],
        "r7b_qualification_sha256": inputs["r7b_qualification_sha256"],
        "r7b_boundary_authority_sha256": inputs["r7b_boundary_authority_sha256"],
        "counts": {
            "canonical_base_count": 39,
            "season_count": 3,
            "base_season_quality_rows": 117,
            "season_source_farm_labels": artifacts["raw_label_count"],
            "season_farm_subfarm_pairs": artifacts["pair_identity_count"],
            "mapped_source_farm_labels": artifacts["mapped_label_count"],
            "unresolved_source_farm_labels": artifacts["unresolved_label_count"],
            "conflicting_source_farm_labels": artifacts["conflicting_label_count"],
            "excluded_source_farm_labels": artifacts["excluded_label_count"],
            "canonical_daily_rows": len(artifacts["daily_rows"]),
            "identity_mapping_status_counts": dict(
                sorted(Counter(row["mapping_status"] for row in artifacts["identity_rows"]).items())
            ),
            "unresolved_or_conflicting_source_farm_labels_remaining": (
                artifacts["unresolved_label_count"] + artifacts["conflicting_label_count"]
            ),
        },
        "season_totals": per_season,
        "base_season_quality_summary": per_season_quality,
        "all_season_totals_kg": {
            "raw": decimal_text(sum((amounts[s]["raw"] for s in SEASONS), Decimal(0))),
            "mapped": decimal_text(sum((amounts[s]["mapped"] for s in SEASONS), Decimal(0))),
            "unresolved": decimal_text(
                sum((amounts[s]["unresolved"] for s in SEASONS), Decimal(0))
            ),
            "excluded": decimal_text(sum((amounts[s]["excluded"] for s in SEASONS), Decimal(0))),
            "reconciliation_delta": "0",
            "current_mapping_mapped": decimal_text(EXPECTED_ALL_SEASONS["current_mapped"]),
            "mapped_gain": decimal_text(EXPECTED_ALL_SEASONS["mapped_gain"]),
        },
        "business_decision_application": {
            "question_count": len(inputs["decision_rows"]),
            **inputs["decision_application"],
            "changed_base_assignment_rows": inputs["build_info"][
                "changed_base_assignment_row_count"
            ],
            "overlapping_question_scope_deduplicated_by_exact_identity": True,
        },
        "semantics": {
            "unknown_is_not_zero": True,
            "confirmed_zero_requires_authority": True,
            "unresolved_is_not_zero": True,
            "reference_area_only": True,
            "historical_actual_area_only_when_business_confirmed_and_identity_bound": True,
            "model_training_eligibility_evaluated": False,
            "model_replay_executed": False,
            "model_training_executed": False,
            "model_refit_executed": False,
            "backtest_executed": False,
            "weather_experiment_executed": False,
            "v0_7_artifacts_modified": False,
        },
        "determinism": {
            "authority_bytes_deterministic": True,
            "canonical_daily_bytes_deterministic": True,
            "quality_ledger_bytes_deterministic": True,
            "manifest_deterministic": True,
        },
        "result": "PASS_DATA_AUTHORITY_REBUILT_MODEL_NOT_REPLAYED",
    }


def _write_private_artifacts(
    output: Path, artifacts: dict[str, Any], inputs: dict[str, Any]
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    os.chmod(output, 0o700)
    entries: dict[str, Any] = {}
    for filename, content in artifacts["output_bytes"].items():
        path = output / filename
        with path.open("xb") as stream:
            stream.write(content)
        os.chmod(path, 0o600)
        entries[filename] = {
            "sha256": sha256_bytes(content),
            "row_count": max(0, len(content.decode("utf-8-sig").splitlines()) - 1),
            "mode": "0600",
        }
    manifest = {
        "task_id": TASK_ID,
        "authority_id": AUTHORITY_ID,
        "policy": "PRIVATE_ROW_LEVEL_IDENTITY_AND_CANONICAL_HISTORY_ARTIFACTS",
        "directory_mode": "0700",
        "inputs": {
            "verified_input_hashes": inputs["verified_input_hashes"],
        },
        "files": entries,
    }
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    with (output / "artifact-manifest.json").open("xb") as stream:
        stream.write(manifest_bytes)
    os.chmod(output / "artifact-manifest.json", 0o600)
    return manifest


def report_text(evidence: dict[str, Any]) -> str:
    totals = evidence["all_season_totals_kg"]
    decisions = evidence["business_decision_application"]
    lines = [
        "# V0.8-S1 Cross-Season Identity Authority and Canonical Dataset Rebuild",
        "",
        f"- Task: `{TASK_ID}`",
        f"- New authority: `{AUTHORITY_ID}`",
        f"- Input main baseline: `{evidence['base_sha']}`",
        (
            "- Result: authority and ledger rebuilt from exact-hash source workbooks; "
            "no model, refit, backtest, or weather experiment was run."
        ),
        (
            "- Identity scope: exact source-farm label + season; no fuzzy mapping "
            "or cross-season propagation."
        ),
        "- Subfarm parent corrections change relationships only; they do not reallocate quantity.",
        (
            "- Unknown and unresolved quantities are never zero-filled. Confirmed zero "
            "requires authorized semantics."
        ),
        (
            "- Registry area remains `REFERENCE_AREA`. Historical actual area requires "
            "a business-confirmed, unique source-identity binding."
        ),
        (
            "- The 2025-2026 R7B business window is 2025-07-22 through 2026-04-15; "
            "in-window unknown dates remain unknown."
        ),
    ]
    lines.extend(
        ["", "## Frozen input identities", "", "Original workbook SHA-256 identities:", ""]
    )
    for season, digest in evidence["source_hashes"].items():
        lines.append(f"- `{season}`: `{digest}`")
    lines.extend(
        [
            "",
            (
                "Previous identity authorities, R7B coverage evidence, and decision-input "
                "manifests were hash-verified and left unchanged."
            ),
            "",
            "## Applied decision contract",
            "",
            f"- Confirmed business questions: {decisions['question_count']}",
            f"- Changed Base assignments: {decisions['changed_base_assignment_rows']}",
            (
                "- Q14 prior-season rows kept unresolved: "
                f"{decisions['q14_prior_no_candidate_rows_remain_unresolved']}"
            ),
            (
                "- Q14 target-season candidate rows applied: "
                f"{decisions['q14_target_season_rows_with_candidate']}"
            ),
            f"- Q17 exact split relation rows: {decisions['q17_split_relation_rows']}",
            (
                "- Q17 unlisted source-label keys left unresolved: "
                f"{decisions['q17_unhandled_source_label_count']}"
            ),
            (
                "- Q07/Q10 relationship-only parent corrections: "
                f"{decisions['q07_q10_parent_correction_rows']}"
            ),
            (
                "- Rules are exact-identity and season-scoped; parent corrections do not "
                "reassign quantity."
            ),
            "",
            "## Reconciliation",
            "",
            f"- Raw total: {totals['raw']} kg",
            f"- Mapped total: {totals['mapped']} kg",
            f"- Unresolved total (including conflicting subset): {totals['unresolved']} kg",
            f"- Explicitly excluded total: {totals['excluded']} kg",
            f"- Reconciliation delta: {totals['reconciliation_delta']} kg",
            f"- Mapped gain over prior accepted authority: {totals['mapped_gain']} kg",
            "",
            "## Season totals",
            "",
            (
                "| Season | Raw kg | Mapped kg | Unresolved kg | Excluded kg | "
                "Mapped rate | Business-window mapped kg |"
            ),
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for season, item in evidence["season_totals"].items():
        lines.append(
            "| "
            f"{season} | {item['raw_source_kg']} | {item['mapped_kg']} | "
            f"{item['unresolved_kg']} | {item['explicitly_excluded_kg']} | "
            f"{item['mapped_rate']} | {item['business_window_mapped_kg']} |"
        )
    lines.extend(
        [
            "",
            "## Base-season coverage and area semantics",
            "",
            (
                "The private quality ledger contains all 39 registered Bases for all three "
                "seasons (117 Base-season rows). Identity acceptance is distinct from "
                "quantity coverage; unknown dates remain unknown."
            ),
            "",
            (
                "| Season | Daily rows | Total-evaluable | Peak-evaluable | Rolling-7 evaluable | "
                "Reference-area rows | Confirmed historical-area rows |"
            ),
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for season, item in evidence["base_season_quality_summary"].items():
        lines.append(
            f"| {season} | {item['daily_rows']} | "
            f"{item['business_total_evaluable_base_season_count']} | "
            f"{item['single_day_peak_evaluable_base_season_count']} | "
            f"{item['rolling_7day_evaluable_base_season_count']} | "
            f"{item['reference_area_only_base_season_count']} | "
            f"{item['business_confirmed_historical_area_base_season_count']} |"
        )
    lines.extend(
        [
            "",
            (
                "Business-total, daily known-support, single-day peak, and rolling-7-day "
                "coverage are separate. A computable business total does not imply complete "
                "daily-shape or peak authority; frozen R7B metric-specific eligibility "
                "is preserved."
            ),
            "",
            "## Authority and privacy",
            "",
            (
                "Row-level labels, mappings, daily values, and identity diffs are restricted "
                "to the private artifact directory. Repository evidence contains hashes, "
                "counts, policy semantics, and aggregate reconciliation only."
            ),
            (
                "Previous mapping authorities and V0.7 evidence remain unchanged. "
                "This dataset does not grant model-training eligibility."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.artifacts_root)
    repository_root = Path(args.repository_root).resolve()
    output = Path(args.private_output_dir)
    if output.exists():
        raise FileExistsError(f"PRIVATE_OUTPUT_PATH_ALREADY_EXISTS:{output}")
    evidence_path = Path(args.public_evidence)
    config_path = Path(args.public_config)
    report_path = Path(args.public_report)
    for path in (evidence_path, config_path, report_path):
        if path.exists():
            raise FileExistsError(f"PUBLIC_OUTPUT_PATH_ALREADY_EXISTS:{path}")
    inputs = _load_and_verify_inputs(root, repository_root)
    artifacts = build_artifacts(inputs)
    evidence = _public_evidence(inputs, artifacts, args.base_sha)
    manifest = _write_private_artifacts(output, artifacts, inputs)
    evidence["private_artifact_manifest_sha256"] = sha256_bytes(
        (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    )
    evidence["private_artifact_directory_mode"] = f"{stat.S_IMODE(output.stat().st_mode):04o}"
    for path in (evidence_path, config_path, report_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    evidence_bytes = (
        json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    config_bytes = (
        json.dumps(
            {
                "version": VERSION,
                "authority_id": AUTHORITY_ID,
                "task_id": TASK_ID,
                "source_hashes": evidence["source_hashes"],
                "business_decisions_sha256": evidence["business_decisions_sha256"],
                "private_artifact_manifest_sha256": evidence["private_artifact_manifest_sha256"],
                "counts": evidence["counts"],
                "all_season_totals_kg": evidence["all_season_totals_kg"],
                "policy": {
                    "exact_identity_only": True,
                    "season_scoped": True,
                    "cross_season_propagation": False,
                    "unknown_is_not_zero": True,
                    "reference_area_only": True,
                    "model_eligibility_automatic": False,
                },
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")
    for path, content in ((evidence_path, evidence_bytes), (config_path, config_bytes)):
        with path.open("xb") as stream:
            stream.write(content)
    with report_path.open("xb") as stream:
        stream.write(report_text(evidence).encode("utf-8"))
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts-root", required=True)
    parser.add_argument("--repository-root", default=".")
    parser.add_argument("--private-output-dir", required=True)
    parser.add_argument("--public-evidence", required=True)
    parser.add_argument("--public-config", required=True)
    parser.add_argument("--public-report", required=True)
    parser.add_argument("--base-sha", required=True)
    args = parser.parse_args()
    evidence = run(args)
    print(
        json.dumps(
            {
                "task_id": TASK_ID,
                "result": evidence["result"],
                "counts": evidence["counts"],
                "all_season_totals_kg": evidence["all_season_totals_kg"],
                "identity_authority_sha256": evidence["private_authority_sha256"],
                "canonical_daily_ledger_sha256": evidence["private_canonical_daily_ledger_sha256"],
                "private_artifact_manifest_sha256": evidence["private_artifact_manifest_sha256"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
