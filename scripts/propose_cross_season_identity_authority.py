"""Capture confirmed business decisions and produce a non-authoritative proposal.

This program reuses the frozen cross-season source ledger and the existing S1
identity authorities. It never writes or edits an accepted mapping authority.
Full labels and row-level proposal artifacts are written only to a private
directory; repository evidence contains aggregate counts and hashes only.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import json
import os
import stat
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Protocol, cast

TASK_ID = "CROSS_SEASON_BUSINESS_IDENTITY_DECISION_CAPTURE_AND_AUTHORITY_CORRECTION_PROPOSAL_R1"
SEMANTIC_CORRECTION_TASK_ID = (
    "CROSS_SEASON_BUSINESS_IDENTITY_DECISION_CAPTURE_Q14_SEMANTICS_CORRECTION_R1"
)
DECISION_SOURCE = "USER_BUSINESS_CONFIRMATION_2026_09_23"
SEASONS = ("2023-2024", "2024-2025", "2025-2026")
ACCEPTED_STATUSES = {"EXACT", "AUTHORIZED_ALIAS", "HISTORICALLY_PROVEN_ALIAS"}
PROPOSAL_STATUSES = ACCEPTED_STATUSES | {"PROPOSED_MAPPED_NON_AUTHORITY"}

RAW_SOURCE_HASHES = {
    "2023-2024": "8fa003b4abdea0b0bd9c50a9fbd619ad15ea5c9a2e790faa5e5b3353a2a01d20",
    "2024-2025": "f4ffba4b10a3129c768871bc5f3dfa2845534bc0e7eb04e166ba97211fa92dd6",
    "2025-2026": "fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a",
}
AUDIT_MANIFEST_HASH = "04e540ffa019dcfd07d4140dc498800f4df11e74184ff6db853fd4f2d9deb17b"
BUSINESS_PACKAGE_MANIFEST_HASH = "bb38dbea3748948f0b72d7f5e192591805155eda79c46541c992b6a1d88cc0fd"
AUTHORITY_HASHES = {
    "historical_identity_mapping": (
        "8d17880141485c407d2e011d70c12d1f828b1966abba32a42b201c33bc4a5044"
    ),
    "base_member_mapping": "d40dbc3a1328d79e10670999ee613fcef8fa3ee32659db16dfe67db3e6b91b5b",
    "base_registry": "502c73fecdf68e91e4aa35982a2207d224204390597eaf59420ebd1101539904",
    "mapping_authority": "319d5adbd51aba71dbcdbcc05d1dfd3ff8e5602d621988230a45c5930c23c086",
    "combined_identity_authority": (
        "c46e198cda2e6c4296db184af5c2e1f3b200a944309aa43039fa3be42a0bbd0e"
    ),
}
DECISION_FIELDS = (
    "group_id",
    "question_number",
    "decision_2023_2024",
    "decision_2024_2025",
    "decision_2025_2026",
    "correct_base",
    "split_rule",
    "future_effective_rule",
    "business_comment",
    "confirmed_by",
    "confirmation_date",
    "decision_source",
    "confirmed_by_status",
)
PROPOSAL_FIELDS = (
    "season",
    "source_farm_label",
    "source_subfarm_label",
    "old_status",
    "old_base_id",
    "old_base_name",
    "old_candidate_base_id",
    "old_candidate_base_name",
    "proposed_status",
    "proposed_base_id",
    "proposed_base_name",
    "proposed_parent_source_farm_label",
    "decision_question",
    "business_decision",
    "quantity_kg",
    "business_window_quantity_kg",
    "change_type",
    "future_effective_rule",
    "proposal_authority_status",
)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"EXPECTED_JSON_OBJECT:{path.name}")
    return value


def _decimal(row: dict[str, str], field: str) -> Decimal:
    try:
        result = Decimal(row.get(field, "0") or "0")
    except InvalidOperation as error:
        raise ValueError(f"INVALID_DECIMAL:{field}") from error
    if not result.is_finite():
        raise ValueError(f"NON_FINITE_DECIMAL:{field}")
    return result


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _json_list(value: str) -> list[dict[str, str]]:
    parsed = json.loads(value or "[]")
    if not isinstance(parsed, list):
        raise ValueError("EXPECTED_JSON_LIST")
    result: list[dict[str, str]] = []
    for item in parsed:
        if (
            not isinstance(item, dict)
            or not item.get("season")
            or not item.get("source_farm_label")
        ):
            raise ValueError("INVALID_LABEL_KEY")
        result.append(
            {"season": str(item["season"]), "source_farm_label": str(item["source_farm_label"])}
        )
    return result


def _parse_ids(value: str) -> tuple[str, ...]:
    raw = (value or "").strip()
    if not raw:
        return ()
    if raw.startswith("["):
        parsed = json.loads(raw)
        if not isinstance(parsed, list) or any(not isinstance(item, str) for item in parsed):
            raise ValueError("INVALID_BASE_ID_LIST")
        return tuple(sorted({item.strip() for item in parsed if item.strip()}))
    return tuple(sorted({item.strip() for item in raw.split(";") if item.strip()}))


def _json_names(value: str) -> tuple[str, ...]:
    parsed = json.loads(value or "[]")
    if not isinstance(parsed, list):
        raise ValueError("EXPECTED_JSON_NAME_LIST")
    return tuple(sorted({str(item) for item in parsed if str(item)}))


def verify_decisions(
    decisions: list[dict[str, str]], priority_rows: list[dict[str, str]]
) -> dict[str, dict[str, str]]:
    expected = {row["question_number"]: row["group_id"] for row in priority_rows}
    if len(expected) != 40 or set(expected) != {f"Q{number:02d}" for number in range(1, 41)}:
        raise ValueError("FROZEN_PRIORITY_QUESTION_SET_INVALID")
    by_question: dict[str, dict[str, str]] = {}
    for row in decisions:
        question = row.get("question_number", "").strip()
        if question in by_question or question not in expected:
            raise ValueError(f"DECISION_QUESTION_DUPLICATE_OR_UNKNOWN:{question}")
        if row.get("group_id") != expected[question]:
            raise ValueError(f"DECISION_GROUP_BINDING_MISMATCH:{question}")
        if row.get("decision_source") != DECISION_SOURCE:
            raise ValueError(f"DECISION_SOURCE_MISMATCH:{question}")
        if row.get("confirmed_by", "").strip():
            raise ValueError(f"UNAUTHORIZED_CONFIRMED_BY_VALUE:{question}")
        if row.get("confirmed_by_status") != "NOT_CAPTURED":
            raise ValueError(f"CONFIRMER_STATUS_MISMATCH:{question}")
        by_question[question] = row
    if set(by_question) != set(expected):
        raise ValueError("BUSINESS_DECISION_COUNT_NOT_40")
    return by_question


def _group_scoped_keys(group: dict[str, str]) -> set[tuple[str, str]]:
    keys = _json_list(group.get("owned_label_keys", "[]"))
    keys += _json_list(group.get("reference_label_keys", "[]"))
    return {(item["season"], item["source_farm_label"]) for item in keys}


def _row_key(row: dict[str, str]) -> tuple[str, str, str]:
    return row["season"], row["source_farm_label"], row.get("source_subfarm_label", "")


def _add_override(
    overrides: dict[tuple[str, str, str], dict[str, Any]],
    key: tuple[str, str, str],
    value: dict[str, Any],
) -> None:
    previous = overrides.get(key)
    if previous is not None:
        for field in ("target_base_id", "proposed_parent_source_farm_label"):
            left, right = previous.get(field, ""), value.get(field, "")
            if left and right and left != right:
                raise ValueError(f"BUSINESS_DECISION_TARGET_CONFLICT:{key[0]}")
            if left and not right:
                value[field] = left
            if right and not left:
                previous[field] = right
        previous["questions"].update(value["questions"])
        previous["split_relation"] = previous["split_relation"] or value["split_relation"]
        previous["future_effective_rule"] = (
            previous["future_effective_rule"] or value["future_effective_rule"]
        )
        return
    overrides[key] = value


def build_proposal(
    identity_rows: list[dict[str, str]],
    priority_rows: list[dict[str, str]],
    decision_rows: list[dict[str, str]],
    base_names: dict[str, str],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Apply decisions to a simulation only; return a private proposed ledger."""
    decisions = verify_decisions(decision_rows, priority_rows)
    groups = {row["question_number"]: row for row in priority_rows}
    if len(identity_rows) != 466:
        raise ValueError("FROZEN_IDENTITY_LEDGER_ROW_COUNT_MISMATCH")
    keys = [_row_key(row) for row in identity_rows]
    if len(keys) != len(set(keys)):
        raise ValueError("FROZEN_IDENTITY_LEDGER_KEY_CONFLICT")
    overrides: dict[tuple[str, str, str], dict[str, Any]] = {}
    row_questions: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    row_decisions: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    q17_unhandled: set[tuple[str, str]] = set()

    def target_id(name: str, question: str) -> str:
        matches = [base_id for base_id, base_name in base_names.items() if base_name == name]
        if len(matches) != 1:
            raise ValueError(f"BUSINESS_TARGET_BASE_NOT_UNIQUE:{question}")
        return matches[0]

    for question in sorted(groups):
        group = groups[question]
        decision = decisions[question]
        scoped = _group_scoped_keys(group)
        relation_type = group.get("relation_type", "")
        subfarms = set(_json_names(group.get("subfarm_labels", "[]")))
        split_rule = json.loads(decision.get("split_rule", "") or "{}")
        if not isinstance(split_rule, dict):
            raise ValueError(f"SPLIT_RULE_NOT_OBJECT:{question}")

        for row in identity_rows:
            key = _row_key(row)
            season, farm, subfarm = key
            if (season, farm) not in scoped:
                continue
            if relation_type == "REUSED_SUBFARM_PARENT_REVIEW" and subfarm not in subfarms:
                continue
            row_questions[key].add(question)
            season_decision = decision.get(f"decision_{season.replace('-', '_')}", "").strip()
            if season_decision:
                row_decisions[key].append(f"{question}:{season_decision}")

            if question in {"Q07", "Q10"}:
                if not season_decision.startswith("CORRECT_PARENT:"):
                    raise ValueError(f"PARENT_DECISION_NOT_EXPLICIT:{question}:{season}")
                detail = split_rule.get(season, {})
                if not isinstance(detail, dict):
                    raise ValueError(f"PARENT_RULE_NOT_OBJECT:{question}:{season}")
                old_parent = detail.get("old_parent_source_farm_label", "")
                corrected_parent = detail.get("correct_parent_source_farm_label", "")
                exact_subfarm = detail.get("source_subfarm_label", "")
                if not old_parent or not corrected_parent or not exact_subfarm:
                    raise ValueError(f"PARENT_RULE_INCOMPLETE:{question}:{season}")
                if farm == old_parent and subfarm == exact_subfarm:
                    _add_override(
                        overrides,
                        key,
                        {
                            "target_base_id": "",
                            "proposed_parent_source_farm_label": corrected_parent,
                            "questions": {question},
                            "split_relation": False,
                            "future_effective_rule": "",
                        },
                    )
                continue

            if question == "Q17":
                season_rule = split_rule.get(season, {})
                if not isinstance(season_rule, dict):
                    raise ValueError(f"Q17_RULE_NOT_OBJECT:{season}")
                target_name = season_rule.get(farm)
                if not target_name:
                    q17_unhandled.add((season, farm))
                    continue
                _add_override(
                    overrides,
                    key,
                    {
                        "target_base_id": target_id(target_name, question),
                        "proposed_parent_source_farm_label": "",
                        "questions": {question},
                        "split_relation": True,
                        "future_effective_rule": "",
                    },
                )
                continue

            if season_decision in {"NO_CANDIDATE", "OUT_OF_SCOPE"}:
                continue
            if question == "Q26":
                if season_decision.startswith("CORRECT_BASE:"):
                    name = season_decision.removeprefix("CORRECT_BASE:").strip()
                elif season_decision == "YES_CANDIDATE":
                    name = decision.get("correct_base", "").strip()
                else:
                    continue
                if not name:
                    raise ValueError(f"Q26_TARGET_MISSING:{season}")
                _add_override(
                    overrides,
                    key,
                    {
                        "target_base_id": target_id(name, question),
                        "proposed_parent_source_farm_label": "",
                        "questions": {question},
                        "split_relation": False,
                        "future_effective_rule": decision.get("future_effective_rule", ""),
                    },
                )
                continue

            if season_decision.startswith("CORRECT_BASE:"):
                name = season_decision.removeprefix("CORRECT_BASE:").strip()
                _add_override(
                    overrides,
                    key,
                    {
                        "target_base_id": target_id(name, question),
                        "proposed_parent_source_farm_label": "",
                        "questions": {question},
                        "split_relation": False,
                        "future_effective_rule": "",
                    },
                )
                continue

            if season_decision == "YES_CANDIDATE":
                candidate_ids = _parse_ids(group.get("candidate_base_ids", ""))
                if len(candidate_ids) != 1:
                    raise ValueError(f"YES_CANDIDATE_NOT_UNIQUE:{question}:{season}")
                _add_override(
                    overrides,
                    key,
                    {
                        "target_base_id": candidate_ids[0],
                        "proposed_parent_source_farm_label": "",
                        "questions": {question},
                        "split_relation": False,
                        "future_effective_rule": "",
                    },
                )

    proposal: list[dict[str, str]] = []
    changed_base_keys: set[tuple[str, str, str]] = set()
    q17_target_keys: set[tuple[str, str, str]] = set()
    parent_correction_keys: set[tuple[str, str, str]] = set()
    for row in identity_rows:
        key = _row_key(row)
        season, farm, subfarm = key
        old_status = row["current_mapping_status"]
        old_ids = _parse_ids(row.get("current_candidate_base_id", ""))
        old_base_id = old_ids[0] if old_status in ACCEPTED_STATUSES and len(old_ids) == 1 else ""
        if old_status in ACCEPTED_STATUSES and not old_base_id:
            raise ValueError(f"ACCEPTED_MAPPING_IDENTITY_NOT_UNIQUE:{season}")
        old_base_name = base_names.get(old_base_id, "") if old_base_id else ""
        old_candidate_names = _json_names(
            json.dumps(row.get("current_canonical_base_name", "").split(";"))
        )
        override = overrides.get(key, {})
        proposed_parent = str(override.get("proposed_parent_source_farm_label", ""))
        target = str(override.get("target_base_id", ""))
        if target:
            if target not in base_names:
                raise ValueError("PROPOSED_BASE_NOT_IN_REGISTRY")
            proposed_base_id = target
            proposed_base_name = base_names[target]
            proposed_status = (
                old_status
                if old_status in ACCEPTED_STATUSES and old_base_id == target
                else "PROPOSED_MAPPED_NON_AUTHORITY"
            )
            if old_base_id != target or old_status not in ACCEPTED_STATUSES:
                changed_base_keys.add(key)
        else:
            proposed_base_id = old_base_id
            proposed_base_name = old_base_name
            proposed_status = old_status

        questions = sorted(row_questions.get(key, set()) | set(override.get("questions", set())))
        q17_applies = bool(override.get("split_relation"))
        if q17_applies:
            q17_target_keys.add(key)
        if proposed_parent:
            parent_correction_keys.add(key)

        if proposed_parent:
            change_type = "PARENT_CORRECTION"
        elif q17_applies:
            change_type = "SPLIT_RELATION"
        elif target and (old_status not in ACCEPTED_STATUSES or old_base_id != target):
            change_type = (
                "RESOLVE_UNRESOLVED"
                if old_status in {"UNRESOLVED", "CONFLICTING"}
                else "REASSIGN_EXISTING"
            )
        elif target or old_status in ACCEPTED_STATUSES:
            change_type = "KEEP_EXISTING"
        elif any(item.endswith(":NO_CANDIDATE") for item in row_decisions.get(key, [])):
            change_type = "REJECT_CANDIDATE_KEEP_UNRESOLVED"
        elif any(item.endswith(":OUT_OF_SCOPE") for item in row_decisions.get(key, [])):
            change_type = "OUT_OF_SCOPE"
        else:
            change_type = "NO_CHANGE"

        relevant_decisions = sorted(set(row_decisions.get(key, [])))
        future_rules = sorted(
            {
                str(override.get("future_effective_rule", "")),
                *(
                    decisions[q].get("future_effective_rule", "").strip()
                    for q in questions
                    if decisions[q].get("future_effective_rule", "").strip()
                ),
            }
            - {""}
        )
        proposal.append(
            {
                "season": season,
                "source_farm_label": farm,
                "source_subfarm_label": subfarm,
                "old_status": old_status,
                "old_base_id": old_base_id,
                "old_base_name": old_base_name,
                "old_candidate_base_id": ";".join(old_ids),
                "old_candidate_base_name": ";".join(old_candidate_names),
                "proposed_status": proposed_status,
                "proposed_base_id": proposed_base_id,
                "proposed_base_name": proposed_base_name,
                "proposed_parent_source_farm_label": proposed_parent,
                "decision_question": ";".join(questions),
                "business_decision": ";".join(relevant_decisions),
                "quantity_kg": row["quantity_kg"],
                "business_window_quantity_kg": row["business_window_quantity_kg"],
                "change_type": change_type,
                "future_effective_rule": ";".join(future_rules),
                "proposal_authority_status": "NON_AUTHORITATIVE_PROPOSAL_ONLY",
            }
        )

    return proposal, {
        "q17_unhandled_source_label_keys": [
            {"season": season, "source_farm_label": farm} for season, farm in sorted(q17_unhandled)
        ],
        "q17_target_row_count": len(q17_target_keys),
        "parent_correction_row_count": len(parent_correction_keys),
        "changed_base_assignment_row_count": len(changed_base_keys),
    }


def _totals(rows: list[dict[str, str]], proposed: bool) -> dict[str, Any]:
    buckets: dict[str, dict[str, Decimal]] = {
        season: {
            "raw": Decimal(0),
            "mapped": Decimal(0),
            "unresolved": Decimal(0),
            "excluded": Decimal(0),
            "business_raw": Decimal(0),
            "business_mapped": Decimal(0),
            "business_unresolved": Decimal(0),
            "business_excluded": Decimal(0),
        }
        for season in SEASONS
    }
    for row in rows:
        season = row["season"]
        status = row["proposed_status"] if proposed else row["old_status"]
        quantity = _decimal(row, "quantity_kg")
        business_quantity = _decimal(row, "business_window_quantity_kg")
        bucket = buckets[season]
        bucket["raw"] += quantity
        bucket["business_raw"] += business_quantity
        if status in PROPOSAL_STATUSES:
            bucket["mapped"] += quantity
            bucket["business_mapped"] += business_quantity
        elif status == "EXCLUDED":
            bucket["excluded"] += quantity
            bucket["business_excluded"] += business_quantity
        else:
            bucket["unresolved"] += quantity
            bucket["business_unresolved"] += business_quantity
    for bucket in buckets.values():
        bucket["reconciliation_delta"] = (
            bucket["raw"] - bucket["mapped"] - bucket["unresolved"] - bucket["excluded"]
        )
        bucket["business_reconciliation_delta"] = (
            bucket["business_raw"]
            - bucket["business_mapped"]
            - bucket["business_unresolved"]
            - bucket["business_excluded"]
        )
    return buckets


def simulate_mapping(
    identity_rows: list[dict[str, str]], proposal_rows: list[dict[str, str]]
) -> dict[str, Any]:
    current = _totals(
        [
            {**row, "old_status": row["current_mapping_status"], "quantity_kg": row["quantity_kg"]}
            for row in identity_rows
        ],
        proposed=False,
    )
    proposed = _totals(proposal_rows, proposed=True)
    for season in SEASONS:
        if current[season]["raw"] != proposed[season]["raw"]:
            raise ValueError(f"RAW_TOTAL_CHANGED:{season}")
        if proposed[season]["reconciliation_delta"] != 0:
            raise ValueError(f"PROPOSED_QUANTITY_NOT_CONSERVED:{season}")
        if proposed[season]["business_reconciliation_delta"] != 0:
            raise ValueError(f"PROPOSED_BUSINESS_QUANTITY_NOT_CONSERVED:{season}")
    return {"current": current, "proposed": proposed}


def _verify_manifest(directory: Path, expected_manifest_hash: str | None = None) -> dict[str, Any]:
    manifest_path = directory / "artifact-manifest.json"
    if expected_manifest_hash and sha256_file(manifest_path) != expected_manifest_hash:
        raise ValueError(f"ARTIFACT_MANIFEST_HASH_MISMATCH:{directory.name}")
    manifest = _read_json(manifest_path)
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ValueError(f"ARTIFACT_MANIFEST_FILES_MISSING:{directory.name}")
    for name, entry in files.items():
        path = directory / name
        if not path.is_file() or sha256_file(path) != entry.get("sha256"):
            raise ValueError(f"ARTIFACT_FILE_HASH_MISMATCH:{directory.name}:{name}")
        if path.suffix == ".csv" and len(_read_csv(path)) != entry.get("row_count"):
            raise ValueError(f"ARTIFACT_FILE_ROW_COUNT_MISMATCH:{directory.name}:{name}")
    return manifest


def _verify_raw_source_parity(
    root: Path, audit_identity_rows: list[dict[str, str]]
) -> dict[str, str]:
    class SourceRecord(Protocol):
        farm: str
        subfarm: str
        quantity_kg: Decimal
        event_date: date

    audit_module = importlib.import_module("scripts.audit_cross_season_data_mapping")
    season_windows = cast(dict[str, tuple[date, date]], audit_module.SEASON_WINDOWS)
    read_source_xls = cast(
        Any,
        audit_module.read_source_xls,
    )

    source_paths = {
        "2023-2024": root / "historical-primary-source-replay-r1" / "23~24.xls",
        "2024-2025": root / "historical-primary-source-replay-r1" / "24~25.xls",
        "2025-2026": root / "source-25-26-r7" / "原果入库汇总表.xls",
    }
    verified: dict[str, str] = {}
    ledger_by_key = {_row_key(row): row for row in audit_identity_rows}
    raw_groups: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(
        lambda: {"rows": 0, "kg": Decimal(0), "business_kg": Decimal(0), "dates": set()}
    )
    for season in SEASONS:
        path = source_paths[season]
        if not path.is_file():
            raise FileNotFoundError(f"RAW_SOURCE_MISSING:{season}:{path}")
        digest = sha256_file(path)
        if digest != RAW_SOURCE_HASHES[season]:
            raise ValueError(f"RAW_SOURCE_HASH_MISMATCH:{season}")
        verified[season] = digest
        start, end = season_windows[season]
        source_rows = cast(list[SourceRecord], read_source_xls(path, season))
        for source in source_rows:
            key = (season, source.farm, source.subfarm)
            item = raw_groups[key]
            item["rows"] += 1
            item["kg"] += source.quantity_kg
            if start <= source.event_date <= end:
                item["business_kg"] += source.quantity_kg
            item["dates"].add(source.event_date)
    if set(raw_groups) != set(ledger_by_key):
        raise ValueError("RAW_SOURCE_IDENTITY_LEDGER_KEY_SET_MISMATCH")
    for key, group in raw_groups.items():
        row = ledger_by_key[key]
        if int(row["raw_row_count"]) != group["rows"]:
            raise ValueError(f"RAW_SOURCE_IDENTITY_ROW_COUNT_MISMATCH:{key[0]}")
        if Decimal(row["quantity_kg"]) != group["kg"]:
            raise ValueError(f"RAW_SOURCE_IDENTITY_QUANTITY_MISMATCH:{key[0]}")
        if Decimal(row["business_window_quantity_kg"]) != group["business_kg"]:
            raise ValueError(f"RAW_SOURCE_BUSINESS_WINDOW_QUANTITY_MISMATCH:{key[0]}")
        if len(group["dates"]) != int(row["observed_day_count"]):
            raise ValueError(f"RAW_SOURCE_IDENTITY_DAY_COUNT_MISMATCH:{key[0]}")
        if min(group["dates"]).isoformat() != row["first_date"]:
            raise ValueError(f"RAW_SOURCE_IDENTITY_FIRST_DATE_MISMATCH:{key[0]}")
        if max(group["dates"]).isoformat() != row["last_date"]:
            raise ValueError(f"RAW_SOURCE_IDENTITY_LAST_DATE_MISMATCH:{key[0]}")
    return verified


def verify_frozen_inputs(root: Path, repository_root: Path) -> dict[str, Any]:
    audit_dir = root / "cross-season-data-mapping-and-quality-audit-r1-final-f"
    package_dir = root / "cross-season-business-identity-confirmation-package-r1-final-f"
    audit_manifest = _verify_manifest(audit_dir, AUDIT_MANIFEST_HASH)
    package_manifest = _verify_manifest(package_dir, BUSINESS_PACKAGE_MANIFEST_HASH)
    audit_rows = _read_csv(audit_dir / "cross-season-source-identity-ledger.csv")
    if len(audit_rows) != 466:
        raise ValueError("AUDIT_IDENTITY_LEDGER_ROW_COUNT_MISMATCH")
    source_hashes = _verify_raw_source_parity(root, audit_rows)

    history_path = (
        root / "historical-identity-reconstruction-r1" / "historical_farm_identity_mapping.csv"
    )
    registry_dir = root / "base-registry-s1-r2"
    authority_paths = {
        "historical_identity_mapping": history_path,
        "base_member_mapping": registry_dir / "member-farm-mapping.csv",
        "base_registry": registry_dir / "base-registry-v1.json",
        "mapping_authority": registry_dir / "mapping-authority.json",
    }
    actual_authority_hashes = {key: sha256_file(path) for key, path in authority_paths.items()}
    for key, digest in actual_authority_hashes.items():
        if digest != AUTHORITY_HASHES[key]:
            raise ValueError(f"CURRENT_AUTHORITY_HASH_MISMATCH:{key}")
    s1_path = repository_root / "docs/v0-7/evidence/s1-formal-multi-season-baseline-validation.json"
    s1 = _read_json(s1_path)
    s1_combined_hash = s1.get("authorities", {}).get("combined_identity_authority_sha256")
    if s1_combined_hash != AUTHORITY_HASHES["combined_identity_authority"]:
        raise ValueError("S1_COMBINED_IDENTITY_AUTHORITY_HASH_MISMATCH")
    summary = _read_json(audit_dir / "audit-summary.json")
    if summary.get("authority_hashes", {}).get("combined_identity_authority") != s1_combined_hash:
        raise ValueError("AUDIT_S1_AUTHORITY_BINDING_MISMATCH")
    s3_path = (
        repository_root / "docs/v0-7/evidence/s3-weather-aware-model-training-and-oot-backtest.json"
    )
    s3 = _read_json(s3_path)
    if s3.get("task_id") != "V0_7_S3_WEATHER_AWARE_MODEL_TRAINING_AND_OOT_BACKTEST_R1":
        raise ValueError("S3_EVIDENCE_TASK_ID_MISMATCH")
    s3_identity_sources = s3.get("authorities", {}).get("identity_mapping_sources", {})
    if (
        s3_identity_sources.get("historical_identity_mapping_sha256")
        != AUTHORITY_HASHES["historical_identity_mapping"]
    ):
        raise ValueError("S3_IDENTITY_AUTHORITY_HASH_MISMATCH")
    registry = _read_json(authority_paths["base_registry"])
    bases = registry.get("bases")
    if not isinstance(bases, list):
        raise ValueError("BASE_REGISTRY_BASES_MISSING")
    base_names: dict[str, str] = {}
    for base in bases:
        base_id, name = base.get("base_id"), base.get("canonical_base_name")
        if not base_id or not name or base_id in base_names:
            raise ValueError("BASE_REGISTRY_IDENTITY_INVALID")
        base_names[str(base_id)] = str(name)
    return {
        "audit_dir": audit_dir,
        "package_dir": package_dir,
        "audit_manifest": audit_manifest,
        "package_manifest": package_manifest,
        "audit_rows": audit_rows,
        "raw_source_hashes": source_hashes,
        "authority_hashes": {
            **actual_authority_hashes,
            "combined_identity_authority": s1_combined_hash,
        },
        "base_names": base_names,
        "audit_summary": summary,
        "s3_evidence": s3,
        "s3_evidence_sha256": sha256_file(s3_path),
        "s1_evidence_sha256": sha256_file(s1_path),
    }


def build_public_evidence(
    *,
    base_sha: str,
    source_hashes: dict[str, str],
    authority_hashes: dict[str, str],
    package_manifest_hash: str,
    decisions_hash: str,
    proposal_rows: list[dict[str, str]],
    decision_rows: list[dict[str, str]],
    build_info: dict[str, Any],
    reconciliation: dict[str, Any],
    s1_evidence: dict[str, Any],
    s1_evidence_sha256: str,
    s3_evidence: dict[str, Any],
    s3_evidence_sha256: str,
) -> dict[str, Any]:
    current, proposed = reconciliation["current"], reconciliation["proposed"]
    questions = {row["question_number"]: row for row in decision_rows}
    q14_prior_rows = [
        row
        for row in proposal_rows
        if row["season"] == "2024-2025"
        and "Q14" in row["decision_question"].split(";")
        and "Q14:NO_CANDIDATE" in row["business_decision"].split(";")
    ]
    if not q14_prior_rows:
        raise ValueError("Q14_PRIOR_SEASON_REJECTION_ROW_MISSING")
    q14_candidate_rejected = all(bool(row["old_candidate_base_id"]) for row in q14_prior_rows)
    q14_remains_unresolved = all(
        row["proposed_status"] == "UNRESOLVED"
        and not row["proposed_base_id"]
        and not row["proposed_base_name"]
        for row in q14_prior_rows
    )
    q14_is_out_of_scope = any(row["change_type"] == "OUT_OF_SCOPE" for row in q14_prior_rows)
    if not q14_candidate_rejected or not q14_remains_unresolved or q14_is_out_of_scope:
        raise ValueError("Q14_PRIOR_SEASON_SEMANTICS_INVALID")
    mapping_changes = [
        row
        for row in proposal_rows
        if row["old_base_id"] != row["proposed_base_id"]
        or (row["old_status"] not in ACCEPTED_STATUSES and row["proposed_base_id"])
    ]
    identity_changes = [
        row
        for row in proposal_rows
        if row in mapping_changes or row["change_type"] == "PARENT_CORRECTION"
    ]
    affected_base_seasons: set[tuple[str, str]] = set()
    for row in identity_changes:
        if row["old_base_id"]:
            affected_base_seasons.add((row["season"], row["old_base_id"]))
        if row["proposed_base_id"]:
            affected_base_seasons.add((row["season"], row["proposed_base_id"]))

    prior_season_rows = sum(row["season"] in {"2023-2024", "2024-2025"} for row in identity_changes)
    validation_season_rows = sum(
        row["season"] in {"2024-2025", "2025-2026"} for row in identity_changes
    )
    s3_per_base = s3_evidence.get("per_base", [])
    if not isinstance(s3_per_base, list):
        raise ValueError("S3_PER_BASE_EVIDENCE_MISSING")
    fold_a_bases = {
        str(row["base_id"])
        for row in s3_per_base
        if row.get("fold_id") == "FOLD_A" and row.get("season") == "2024-2025"
    }
    fold_b_bases = {
        str(row["base_id"])
        for row in s3_per_base
        if row.get("fold_id") == "FOLD_B" and row.get("season") == "2025-2026"
    }
    if not fold_a_bases or not fold_b_bases:
        raise ValueError("S3_VALIDATION_BASE_SCOPE_MISSING")
    s3_validation_scope = {
        *(("2024-2025", base_id) for base_id in fold_a_bases),
        *(("2025-2026", base_id) for base_id in fold_b_bases),
    }
    s3_candidate_pairs = {
        (row["season"], row["proposed_base_id"])
        for row in identity_changes
        if (row["season"], row["proposed_base_id"]) in s3_validation_scope
    }
    s3_scope_overlap = {
        "fold_a_candidate_identity_row_count": sum(
            row["season"] == "2024-2025" and row["proposed_base_id"] in fold_a_bases
            for row in identity_changes
        ),
        "fold_b_candidate_identity_row_count": sum(
            row["season"] == "2025-2026" and row["proposed_base_id"] in fold_b_bases
            for row in identity_changes
        ),
        "status": "BASE_SEASON_SCOPE_ONLY_SOURCE_LABEL_LINEAGE_NOT_PROVEN",
        "candidate_base_season_count": len(s3_candidate_pairs),
        "candidate_base_count": len({base_id for _, base_id in s3_candidate_pairs}),
    }
    per_season: dict[str, Any] = {}
    for season in SEASONS:
        c = current[season]
        p = proposed[season]
        per_season[season] = {
            "raw_kg": str(c["raw"]),
            "current_mapped_kg": str(c["mapped"]),
            "current_unresolved_kg": str(c["unresolved"]),
            "current_excluded_kg": str(c["excluded"]),
            "proposed_mapped_kg": str(p["mapped"]),
            "proposed_unresolved_kg": str(p["unresolved"]),
            "proposed_excluded_kg": str(p["excluded"]),
            "current_mapping_rate": str(c["mapped"] / c["raw"]),
            "proposed_mapping_rate": str(p["mapped"] / p["raw"]),
            "business_window_raw_kg": str(c["business_raw"]),
            "proposed_business_window_mapped_kg": str(p["business_mapped"]),
            "proposed_business_window_unresolved_kg": str(p["business_unresolved"]),
            "reconciliation_delta_kg": str(p["reconciliation_delta"]),
            "business_window_reconciliation_delta_kg": str(p["business_reconciliation_delta"]),
        }
    total_current_mapped = sum((current[s]["mapped"] for s in SEASONS), Decimal(0))
    total_proposed_mapped = sum((proposed[s]["mapped"] for s in SEASONS), Decimal(0))
    total_current_unresolved = sum((current[s]["unresolved"] for s in SEASONS), Decimal(0))
    total_proposed_unresolved = sum((proposed[s]["unresolved"] for s in SEASONS), Decimal(0))
    return {
        "task_id": TASK_ID,
        "semantic_correction_task_id": SEMANTIC_CORRECTION_TASK_ID,
        "result": "PARTIAL_BUSINESS_SCOPE_REQUIRES_CONFIRMATION"
        if build_info["q17_unhandled_source_label_keys"]
        else "PASS",
        "base_sha": base_sha,
        "source_hashes": source_hashes,
        "identity_authority_hashes": authority_hashes,
        "source_audit_manifest_sha256": AUDIT_MANIFEST_HASH,
        "business_confirmation_package_manifest_sha256": package_manifest_hash,
        "s1_evidence_sha256": s1_evidence_sha256,
        "s3_evidence_sha256": s3_evidence_sha256,
        "business_decisions_private_sha256": decisions_hash,
        "business_decision_count": len(decision_rows),
        "business_decisions_by_question_sha256": hashlib.sha256(
            canonical_bytes(
                {
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
            )
        ).hexdigest(),
        "business_confirmation_source": DECISION_SOURCE,
        "confirmed_by_status": "NOT_CAPTURED",
        "all_40_business_questions_captured": len(decision_rows) == 40,
        "no_business_decision_inferred": True,
        "question_specific_rules": {
            "no_candidate_is_out_of_scope": False,
            "q14_season_specific_rule_preserved": (
                questions["Q14"]["decision_2024_2025"] == "NO_CANDIDATE"
                and questions["Q14"]["decision_2025_2026"] == "YES_CANDIDATE"
            ),
            "q14_2024_2025_candidate_rejected": q14_candidate_rejected,
            "q14_2024_2025_remains_unresolved": q14_remains_unresolved,
            "q14_2024_2025_out_of_scope": q14_is_out_of_scope,
            "q14_out_of_current_39_base_scope": False,
            "q14_out_of_scope_not_established": True,
            "q17_split_mapping_rule_preserved": bool(questions["Q17"].get("split_rule")),
            "q17_unhandled_label_count": len(build_info["q17_unhandled_source_label_keys"]),
            "q07_parent_correction_preserved": any(
                row["decision_question"].find("Q07") >= 0
                and row["change_type"] == "PARENT_CORRECTION"
                for row in proposal_rows
            ),
            "q10_parent_correction_preserved": any(
                row["decision_question"].find("Q10") >= 0
                and row["change_type"] == "PARENT_CORRECTION"
                for row in proposal_rows
            ),
            "q26_effective_season_rule_preserved": bool(
                questions["Q26"].get("future_effective_rule")
            ),
            "q06_q09_exact_identity_deduplication": True,
        },
        "proposal_is_non_authoritative": True,
        "mapping_authority_applied": False,
        "raw_private_rows_committed": False,
        "decision_rows_private": True,
        "proposal_rows_private": True,
        "quantity_reconciliation_pass": all(
            proposed[s]["reconciliation_delta"] == 0
            and proposed[s]["business_reconciliation_delta"] == 0
            for s in SEASONS
        ),
        "global_totals_kg": {
            "current_mapped": str(total_current_mapped),
            "proposed_mapped": str(total_proposed_mapped),
            "mapped_gain": str(total_proposed_mapped - total_current_mapped),
            "current_unresolved": str(total_current_unresolved),
            "proposed_unresolved": str(total_proposed_unresolved),
            "unresolved_reduction": str(total_current_unresolved - total_proposed_unresolved),
            "excluded_kg": str(sum((proposed[s]["excluded"] for s in SEASONS), Decimal(0))),
            "raw_kg": str(sum((proposed[s]["raw"] for s in SEASONS), Decimal(0))),
        },
        "per_season": per_season,
        "impact_analysis": {
            "affected_base_season_count": len(affected_base_seasons),
            "affected_prior_history_source_identity_row_count": prior_season_rows,
            "affected_validation_label_source_identity_row_count": validation_season_rows,
            "affected_s3_cohort_overlap": s3_scope_overlap,
            "s3_source_label_lineage_proven": False,
            "v0_7_recomputation_required": bool(identity_changes),
            "model_a_replay_required": bool(identity_changes),
            "model_b_replay_required": bool(identity_changes),
            "replay_executed": False,
        },
        "private_proposal_row_count": len(proposal_rows),
        "private_changed_base_assignment_row_count": build_info[
            "changed_base_assignment_row_count"
        ],
        "private_parent_correction_row_count": build_info["parent_correction_row_count"],
        "private_identity_change_row_count": len(identity_changes),
        "q17_scope_incomplete": bool(build_info["q17_unhandled_source_label_keys"]),
        "proposed_quantity_reconciliation_policy": (
            "RAW=MAPPED+UNRESOLVED+EXPLICITLY_EXCLUDED;CONFLICTING_COUNTS_AS_UNRESOLVED"
        ),
        "v07_changed": False,
        "model_changed": False,
        "model_retrained": False,
        "backtest_executed": False,
        "authority_modification_authorized": False,
        "ready_authorized": False,
        "merge_authorized": False,
    }


def render_report(evidence: dict[str, Any]) -> str:
    totals = evidence["global_totals_kg"]
    impact = evidence["impact_analysis"]
    season_lines = [
        (
            "| Season | Raw kg | Current mapped kg | Current mapping rate | "
            "Proposed mapped kg | Proposed unresolved kg | Proposed mapping rate | "
            "Reconciliation delta kg |"
        ),
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for season, values in evidence["per_season"].items():
        season_lines.append(
            f"| {season} | {values['raw_kg']} | {values['current_mapped_kg']} | "
            f"{values['current_mapping_rate']} | "
            f"{values['proposed_mapped_kg']} | {values['proposed_unresolved_kg']} | "
            f"{values['proposed_mapping_rate']} | {values['reconciliation_delta_kg']} |"
        )
    sections = [
        "# Cross-season business identity decisions and authority correction proposal",
        "",
        f"Task: `{TASK_ID}`",
        f"Semantic correction: `{SEMANTIC_CORRECTION_TASK_ID}`",
        f"Audit baseline: `{evidence['base_sha']}`",
        "",
        "## Decision capture",
        "",
        f"- Business questions recorded: {evidence['business_decision_count']} (Q01-Q40).",
        (
            "- Decisions are bound to the private confirmation package and decision CSV hashes "
            "in the machine evidence."
        ),
        "- Confirming identity was not captured; no person was inferred.",
        "- The report omits source labels, Base names, and private row-level quantities.",
        "",
        "## Non-authoritative simulation",
        "",
        (
            "The private proposal is a simulation only. Existing mapping authority, Base Registry, "
            "V0.7 evidence, model configuration, and released artifacts were not modified. The "
            "proposal CSV remains outside Git in a mode-0600 private artifact directory."
        ),
        "",
        f"- Current mapped quantity: {totals['current_mapped']} kg.",
        f"- Proposed mapped quantity: {totals['proposed_mapped']} kg.",
        f"- Simulated mapped gain: {totals['mapped_gain']} kg.",
        f"- Current unresolved quantity: {totals['current_unresolved']} kg.",
        f"- Proposed unresolved quantity: {totals['proposed_unresolved']} kg.",
        f"- Simulated unresolved reduction: {totals['unresolved_reduction']} kg.",
        (
            f"- Total source quantity: {totals['raw_kg']} kg; exact per-season reconciliation: "
            f"{evidence['quantity_reconciliation_pass']}."
        ),
        "",
        *season_lines,
        "",
        "## Decision-specific safeguards",
        "",
        (
            "- Q14 remains season-scoped: the 2024-2025 candidate is rejected; the row remains "
            "UNRESOLVED with no proposed Base, while the 2025-2026 candidate is accepted only "
            "for that season."
        ),
        (
            "- NO_CANDIDATE_IS_OUT_OF_SCOPE=false. Q14_2024_2025_OUT_OF_SCOPE=false; "
            "OUT_OF_CURRENT_39_BASE_SCOPE=false and OUT_OF_SCOPE_NOT_ESTABLISHED=true. The "
            "rejection does not establish whether the row belongs to another current Base or is "
            "outside the 39-Base scope."
        ),
        (
            "- Q17 uses exact label split rules. Any unlisted label remains unresolved and makes "
            "the result partial."
        ),
        "- Q26 is season-scoped; 2024-2025 is not rewritten as a later-season Base.",
        (
            "- Q07/Q10 correct only the confirmed parent relation for the exact subfarm row. "
            "Parent totals are not copied into subfarm quantities."
        ),
        "- Duplicate question scopes are de-duplicated by exact source identity.",
        "- Q17 unhandled source-label count: "
        f"{evidence['question_specific_rules']['q17_unhandled_label_count']}.",
        "",
        "## V0.7 impact and limits",
        "",
        f"- Affected Base-season scopes (simulation): {impact['affected_base_season_count']}.",
        "- Affected prior-history identity rows: "
        f"{impact['affected_prior_history_source_identity_row_count']}.",
        "- Affected validation-label identity rows: "
        f"{impact['affected_validation_label_source_identity_row_count']}.",
        "- Candidate S3 cohort overlap: "
        f"{impact['affected_s3_cohort_overlap']['candidate_base_season_count']} "
        "Base-season scope candidates; source-label lineage is not proven.",
        (
            "- V0.7 S3 impact is reported at Base-season scope only; exact source-label lineage "
            "to frozen S3 rows is not proven."
        ),
        (
            "- If a later task authorizes applying a correction, V0.7 recomputation and Model A/B "
            "replay are required; none was executed here."
        ),
        "",
        "## Authority and release boundary",
        "",
        (
            "`MAPPING_AUTHORITY_APPLIED=false`; `MODEL_CHANGED=false`; "
            "`MODEL_RETRAINED=false`; `BACKTEST_EXECUTED=false`; `V0_7_CHANGED=false`."
        ),
        (
            "This Draft PR records decisions and a proposed correction only. It does not authorize "
            "applying the proposal or changing released V0.7 artifacts."
        ),
        "",
        (
            "See the adjacent machine-readable evidence for input hashes, aggregate "
            "reconciliation, affected-scope counts, and authorization flags."
        ),
        "",
    ]
    return "\n".join(sections)


def _write_private_csv(path: Path, rows: list[dict[str, str]], fields: tuple[str, ...]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    os.chmod(path, 0o600)


def _write_private_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            default=_json_default,
        )
        + "\n",
        encoding="utf-8",
    )
    os.chmod(path, 0o600)


def _json_default(value: object) -> str:
    if isinstance(value, Decimal):
        return _decimal_text(value)
    raise TypeError(f"NON_CANONICAL_JSON_VALUE:{type(value).__name__}")


def _write_public(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.artifacts_root)
    repo = Path(args.repository_root)
    private_dir = Path(args.private_output_dir)
    private_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(private_dir, 0o700)
    source = verify_frozen_inputs(root, repo)
    package_dir = source["package_dir"]
    priority_path = package_dir / "business-identity-confirmation-priority.csv"
    decision_path = Path(args.decisions)
    priority_rows = _read_csv(priority_path)
    decision_rows = _read_csv(decision_path)
    verify_decisions(decision_rows, priority_rows)
    proposal_rows, build_info = build_proposal(
        source["audit_rows"], priority_rows, decision_rows, source["base_names"]
    )
    reconciliation = simulate_mapping(source["audit_rows"], proposal_rows)
    decisions_sha = sha256_file(decision_path)
    s1_evidence_path = repo / "docs/v0-7/evidence/s1-formal-multi-season-baseline-validation.json"
    evidence = build_public_evidence(
        base_sha=args.base_sha,
        source_hashes=source["raw_source_hashes"],
        authority_hashes=source["authority_hashes"],
        package_manifest_hash=BUSINESS_PACKAGE_MANIFEST_HASH,
        decisions_hash=decisions_sha,
        proposal_rows=proposal_rows,
        decision_rows=decision_rows,
        build_info=build_info,
        reconciliation=reconciliation,
        s1_evidence=_read_json(s1_evidence_path),
        s1_evidence_sha256=source["s1_evidence_sha256"],
        s3_evidence=source["s3_evidence"],
        s3_evidence_sha256=source["s3_evidence_sha256"],
    )

    dest_decisions = private_dir / "business-identity-confirmation-decisions-r1.csv"
    if decision_path.resolve() != dest_decisions.resolve():
        _write_private_csv(dest_decisions, decision_rows, DECISION_FIELDS)
    else:
        os.chmod(dest_decisions, 0o600)
    proposal_path = private_dir / "proposed-cross-season-identity-authority-r1.csv"
    _write_private_csv(proposal_path, proposal_rows, PROPOSAL_FIELDS)
    summary_path = private_dir / "proposal-simulation-summary.json"
    _write_private_json(summary_path, {"reconciliation": reconciliation, "build_info": build_info})
    files = {}
    for path, count in (
        (dest_decisions, len(decision_rows)),
        (proposal_path, len(proposal_rows)),
        (summary_path, 1),
    ):
        files[path.name] = {
            "sha256": sha256_file(path),
            "row_count": count,
            "mode": f"{stat.S_IMODE(path.stat().st_mode):04o}",
        }
    manifest = {
        "task_id": TASK_ID,
        "directory_mode": f"{stat.S_IMODE(private_dir.stat().st_mode):04o}",
        "policy": "PRIVATE_BUSINESS_DECISIONS_AND_NON_AUTHORITATIVE_PROPOSAL",
        "files": files,
    }
    manifest_path = private_dir / "artifact-manifest.json"
    _write_private_json(manifest_path, manifest)
    evidence["private_output_manifest_sha256"] = sha256_file(manifest_path)
    _write_public(
        Path(args.public_evidence),
        json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    )
    _write_public(Path(args.public_report), render_report(evidence))
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts-root", required=True)
    parser.add_argument("--repository-root", default=".")
    parser.add_argument("--private-output-dir", required=True)
    parser.add_argument("--decisions", required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--public-evidence", required=True)
    parser.add_argument("--public-report", required=True)
    args = parser.parse_args()
    evidence = run(args)
    print(
        json.dumps(
            {
                "result": evidence["result"],
                "business_decision_count": evidence["business_decision_count"],
                "quantity_reconciliation_pass": evidence["quantity_reconciliation_pass"],
                "mapped_gain_kg": evidence["global_totals_kg"]["mapped_gain"],
                "affected_base_season_count": evidence["impact_analysis"][
                    "affected_base_season_count"
                ],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
