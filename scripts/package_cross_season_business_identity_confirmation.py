"""Build a deterministic, private business-review package from frozen audit outputs.

This utility reads the R1 audit artifacts and frozen V0.7 evidence. It does not
write mapping authority, model inputs, or private row data into the repository.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import os
import stat
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

TASK_ID = "CROSS_SEASON_BUSINESS_IDENTITY_CONFIRMATION_PACKAGE_R1"
SOURCE_TASK_ID = "CROSS_SEASON_DATA_MAPPING_AND_QUALITY_AUDIT_R1"
SEASONS = ("2023-2024", "2024-2025", "2025-2026")
ACCEPTED = {"EXACT", "AUTHORIZED_ALIAS", "HISTORICALLY_PROVEN_ALIAS"}
SOURCE_MANIFEST_SHA256 = "04e540ffa019dcfd07d4140dc498800f4df11e74184ff6db853fd4f2d9deb17b"
MANUAL_ISSUES_SHA256 = "4e4fc6b8bbbd81bb325f3327931a358cfca9927a5f10ced808a99bb16dc56856"
EXPECTED_AUTHORITY_HASHES = {
    "historical_identity_mapping": (
        "8d17880141485c407d2e011d70c12d1f828b1966abba32a42b201c33bc4a5044"
    ),
    "base_member_mapping": "d40dbc3a1328d79e10670999ee613fcef8fa3ee32659db16dfe67db3e6b91b5b",
}
S3_FROZEN_IDENTITY_MAPPING_SHA256 = (
    "850f89d0286825fc61c8165a6b0ef0e23e5fb50a323cfebcb956bc60dd0818b8"
)
S3_V05_MEMBER_MAPPING_SHA256 = "469d1b2f7f05a0e605bc58dda3b5e6bfeda3b23d23b766170dd618e8b360b344"
S1_COMBINED_IDENTITY_AUTHORITY_SHA256 = (
    "c46e198cda2e6c4296db184af5c2e1f3b200a944309aa43039fa3be42a0bbd0e"
)
SOURCE_FILES = (
    "manual_business_confirmation.csv",
    "cross-season-anomaly-ledger.csv",
    "cross-season-source-identity-ledger.csv",
    "cross-season-source-farm-label-ledger.csv",
    "cross-season-base-membership-matrix.csv",
    "cross-season-base-member-change-ledger.csv",
    "cross-season-base-season-quality.csv",
)
MANDATORY_GROUPS: dict[str, set[str]] = {
    "JIANSHUI_CHAKE_NANZHUANG": {
        "建水南庄基地",
        "建水南庄农场",
        "建水岔科基地",
        "建水岔科农场",
    },
    "YUANJIANG_GANZHUANG_YANGWU": {
        "元江甘庄基地",
        "元江甘庄农场",
        "甘庄农场",
        "新平扬武农场",
    },
    "TENGCHONG_DEHONG_YINGJIANG": {
        "腾冲德宏农场",
        "德宏盈江农场",
        "盈江联农带农",
    },
    "YANSHAN_HUILONG_CENTER_STATION": {
        "砚山回龙农场",
        "砚山回龙（中心实验站）",
        "砚山回龙(中心实验站)",
        "回龙中心实验站",
        "回龙中心试验站",
    },
}
GROUP_FIELDS = (
    "group_id",
    "mandatory_group_id",
    "relation_type",
    "priority_band",
    "impact_type",
    "question_number",
    "source_labels",
    "subfarm_labels",
    "seasons",
    "current_base_ids",
    "current_base_names",
    "candidate_base_ids",
    "candidate_base_names",
    "current_mapping_statuses",
    "current_mapping_types",
    "raw_kg_by_season",
    "business_window_kg_by_season",
    "mapped_kg_at_risk",
    "business_window_mapped_kg_at_risk",
    "unresolved_kg_potentially_recoverable",
    "business_window_unresolved_kg_potentially_recoverable",
    "explicitly_excluded_kg",
    "reference_raw_kg_by_season",
    "observed_days_by_season",
    "mapped_label_keys",
    "unresolved_label_keys",
    "owned_label_keys",
    "reference_label_keys",
    "covered_issue_ids",
    "manual_issue_count",
    "p1_issue_count",
    "p2_issue_count",
    "anomaly_issue_count",
    "member_change_flag",
    "extreme_yield_jump_flag",
    "low_coverage_flag",
    "reused_subfarm_flag",
    "affected_base_ids",
    "affected_seasons",
    "used_in_frozen_prior_history",
    "used_in_v07_validation_labels",
    "used_in_v07_ab_comparison",
    "model_impact_evidence_status",
    "quantity_ownership",
    "business_decision_prefilled",
    "supporting_evidence",
    "mapping_authorities",
    "mapping_evidence",
    "related_parent_group_ids",
)
PRIORITY_FIELDS = GROUP_FIELDS + (
    "decision_2023_2024",
    "decision_2024_2025",
    "decision_2025_2026",
    "correct_base_if_no",
    "effective_date_or_split_rule_if_partial",
    "business_comment",
    "confirmed_by",
    "confirmation_date",
)
DECISION_FIELDS = (
    "group_id",
    "question_number",
    "decision_2023_2024",
    "decision_2024_2025",
    "decision_2025_2026",
    "correct_base_if_no",
    "effective_date_or_split_rule_if_partial",
    "business_comment",
    "confirmed_by",
    "confirmation_date",
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


def decimal_text(value: Decimal | None) -> str:
    if value is None:
        return ""
    if value == 0:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path.name}")
    return value


def _amount(row: dict[str, str], field: str) -> Decimal:
    try:
        value = Decimal(row.get(field, "0") or "0")
    except InvalidOperation as error:
        raise ValueError(f"Invalid Decimal in field {field}") from error
    if not value.is_finite():
        raise ValueError(f"Non-finite Decimal in field {field}")
    return value


def _candidate_ids(value: str) -> tuple[str, ...]:
    return tuple(sorted({part.strip() for part in value.split(";") if part.strip()}))


def _candidate_names(value: str) -> tuple[str, ...]:
    return tuple(sorted({part.strip() for part in value.split(";") if part.strip()}))


def _exact_values(value: str) -> tuple[str, ...]:
    values = tuple(sorted({part.strip() for part in value.split(";") if part.strip()}))
    if not values:
        return ()
    raw_count = sum(bool(part.strip()) for part in value.split(";"))
    if len(values) != raw_count:
        raise ValueError("DUPLICATE_VALUE_IN_EXACT_RELATION_FIELD")
    return values


def _split_python_list(value: str) -> list[str]:
    text = (value or "").strip()
    if not text:
        return []
    try:
        parsed = ast.literal_eval(text)
    except (SyntaxError, ValueError):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as error:
            raise ValueError("Cannot parse frozen label-list field") from error
    if not isinstance(parsed, (list, tuple)):
        raise ValueError("Expected a list in frozen membership evidence")
    return sorted({str(item).strip() for item in parsed if str(item).strip()})


def verify_source_inputs(input_dir: Path) -> tuple[dict[str, list[dict[str, str]]], dict[str, Any]]:
    manifest_path = input_dir / "artifact-manifest.json"
    if sha256_file(manifest_path) != SOURCE_MANIFEST_SHA256:
        raise ValueError("SOURCE_AUDIT_MANIFEST_HASH_MISMATCH")
    if stat.S_IMODE(input_dir.stat().st_mode) != 0o700:
        raise ValueError("SOURCE_AUDIT_PRIVATE_DIRECTORY_MODE_MISMATCH")
    manifest = _read_json(manifest_path)
    file_manifest = manifest.get("files")
    if not isinstance(file_manifest, dict):
        raise ValueError("Source artifact manifest has no files object")

    for name, entry in file_manifest.items():
        path = input_dir / name
        if not path.is_file() or not isinstance(entry, dict):
            raise ValueError(f"SOURCE_AUDIT_MANIFEST_FILE_MISSING:{name}")
        if sha256_file(path) != entry.get("sha256"):
            raise ValueError(f"SOURCE_AUDIT_MANIFEST_FILE_HASH_MISMATCH:{name}")
        if stat.S_IMODE(path.stat().st_mode) != 0o600 or entry.get("mode") != "0600":
            raise ValueError(f"SOURCE_AUDIT_PRIVATE_FILE_MODE_MISMATCH:{name}")
        if path.suffix == ".csv" and len(_read_csv(path)) != entry.get("row_count"):
            raise ValueError(f"SOURCE_AUDIT_MANIFEST_ROW_COUNT_MISMATCH:{name}")
        if name == "audit-summary.json" and entry.get("row_count") != 1:
            raise ValueError("SOURCE_AUDIT_SUMMARY_ROW_COUNT_MISMATCH")

    loaded: dict[str, list[dict[str, str]]] = {}
    verified_hashes: dict[str, str] = {}
    for name in SOURCE_FILES:
        path = input_dir / name
        entry = file_manifest.get(name)
        if not path.is_file() or not isinstance(entry, dict):
            raise ValueError(f"SOURCE_AUDIT_INPUT_MISSING:{name}")
        actual_hash = sha256_file(path)
        if actual_hash != entry.get("sha256"):
            raise ValueError(f"SOURCE_AUDIT_INPUT_HASH_MISMATCH:{name}")
        rows = _read_csv(path)
        if len(rows) != entry.get("row_count"):
            raise ValueError(f"SOURCE_AUDIT_INPUT_ROW_COUNT_MISMATCH:{name}")
        loaded[name] = rows
        verified_hashes[name] = actual_hash

    if verified_hashes["manual_business_confirmation.csv"] != MANUAL_ISSUES_SHA256:
        raise ValueError("SOURCE_MANUAL_CONFIRMATION_HASH_MISMATCH")
    manual = loaded["manual_business_confirmation.csv"]
    if len(manual) != 263:
        raise ValueError("SOURCE_MANUAL_CONFIRMATION_COUNT_MISMATCH")
    issue_ids = [row.get("issue_id", "") for row in manual]
    if not all(issue_ids) or len(issue_ids) != len(set(issue_ids)):
        raise ValueError("SOURCE_MANUAL_CONFIRMATION_ISSUE_ID_CONFLICT")
    if any(row.get("business_decision", "").strip() for row in manual):
        raise ValueError("SOURCE_BUSINESS_DECISION_ALREADY_FILLED")
    manifest["verified_input_hashes"] = verified_hashes
    return loaded, manifest


def _new_group(key: tuple[Any, ...], mandatory_group_id: str = "") -> dict[str, Any]:
    identity = {"grouping_policy": "EXACT_RELATION_GROUP_R1", "key": list(key)}
    group_id = "BICG-" + hashlib.sha256(canonical_bytes(identity)).hexdigest()[:16]
    return {
        "group_id": group_id,
        "group_key": key,
        "mandatory_group_id": mandatory_group_id,
        "owned_label_keys": set(),
        "reference_label_keys": set(),
        "identity_label_rows": {},
        "reference_identity_label_rows": {},
        "source_labels": set(),
        "subfarm_labels": set(),
        "seasons": set(),
        "manual_issues": {},
        "anomaly_rows": [],
        "member_change_rows": [],
        "supporting_evidence": set(),
        "related_parent_group_ids": set(),
        "reused_subfarm_flag": False,
        "explicit_relation_flag": False,
        "member_change_flag": False,
        "extreme_yield_jump_flag": False,
        "low_coverage_flag": False,
    }


def _farm_group_key(row: dict[str, str], mandatory_by_label: dict[str, str]) -> tuple[Any, ...]:
    season = row["season"]
    label = row["source_farm_label"].strip()
    status = row["current_mapping_status"]
    candidates = _candidate_ids(row.get("current_candidate_base_id", ""))
    mandatory = mandatory_by_label.get(label)
    if mandatory:
        return ("MANDATORY", mandatory)
    if status in ACCEPTED:
        if len(candidates) != 1:
            raise ValueError(f"ACCEPTED_MAPPING_WITHOUT_SINGLE_BASE:{season}:{label}")
        return ("IDENTITY", label, candidates)
    if status == "UNRESOLVED":
        return (
            ("UNRESOLVED_CANDIDATE", label, candidates)
            if candidates
            else (
                "UNRESOLVED_LABEL_ONLY",
                label,
            )
        )
    if status == "EXCLUDED":
        return ("EXPLICIT_EXCLUSION", label)
    if status == "CONFLICTING":
        return ("CONFLICTING_IDENTITY", label, candidates)
    raise ValueError(f"UNKNOWN_FROZEN_MAPPING_STATUS:{status}:{season}:{label}")


def _is_member_change_problem(problem: str) -> bool:
    return "member evidence changed" in problem.lower() or "member" in problem.lower()


def _is_yield_jump_problem(problem: str) -> bool:
    return "reference-area yield ratio" in problem.lower()


def _is_low_coverage_problem(problem: str) -> bool:
    return "observed day" in problem.lower() and "season-total coverage" in problem.lower()


def _is_identity_issue(problem: str) -> bool:
    text = problem.lower()
    return any(
        token in text
        for token in (
            "no accepted season-scoped mapping",
            "out of the current base registry scope",
            "source-member evidence changed",
            "task-mandated high-risk review",
            "same subfarm text appears",
        )
    )


def build_business_relation_groups(
    manual_issues: list[dict[str, str]],
    farm_label_rows: list[dict[str, str]],
    identity_rows: list[dict[str, str]],
    anomaly_rows: list[dict[str, str]],
    member_change_rows: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Group exact identity relations while assigning every manual issue once."""

    mandatory_by_label: dict[str, str] = {}
    for mandatory_id, mandatory_labels in MANDATORY_GROUPS.items():
        for label in mandatory_labels:
            previous = mandatory_by_label.setdefault(label, mandatory_id)
            if previous != mandatory_id:
                raise ValueError(f"MANDATORY_LABEL_GROUP_COLLISION:{label}")

    farm_by_key: dict[tuple[str, str], dict[str, str]] = {}
    group_by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    group_for_label: dict[tuple[str, str], dict[str, Any]] = {}
    for row in sorted(
        farm_label_rows, key=lambda item: (item["season"], item["source_farm_label"])
    ):
        season = row["season"]
        label = row["source_farm_label"].strip()
        if not season or not label or (season, label) in farm_by_key:
            raise ValueError(f"SOURCE_FARM_LABEL_IDENTITY_CONFLICT:{season}:{label}")
        farm_by_key[(season, label)] = row
        group_key = _farm_group_key(row, mandatory_by_label)
        identity_group = group_by_key.setdefault(
            group_key, _new_group(group_key, mandatory_by_label.get(label, ""))
        )
        label_key = (season, label)
        identity_group["owned_label_keys"].add(label_key)
        identity_group["identity_label_rows"][label_key] = row
        identity_group["source_labels"].add(label)
        identity_group["seasons"].add(season)
        group_for_label[label_key] = identity_group

    mandatory_groups = {
        group["mandatory_group_id"]: group
        for group in group_by_key.values()
        if group.get("mandatory_group_id")
    }

    identity_by_label: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    identity_by_subfarm: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in identity_rows:
        season = row["season"]
        farm = row["source_farm_label"].strip()
        subfarm = row["source_subfarm_label"].strip()
        key = (season, farm)
        if key not in group_for_label:
            raise ValueError(f"IDENTITY_LEDGER_FARM_LABEL_NOT_FOUND:{season}:{farm}")
        identity_by_label[key].append(row)
        if subfarm:
            identity_by_subfarm[(season, subfarm)].append(row)
            group_for_label[key]["subfarm_labels"].add(subfarm)

    def ensure_reused_subfarm_group(season: str, subfarm: str) -> dict[str, Any]:
        parents = tuple(
            sorted(
                {
                    row["source_farm_label"].strip()
                    for row in identity_by_subfarm.get((season, subfarm), [])
                }
            )
        )
        if len(parents) < 2:
            raise ValueError(f"SUBFARM_REUSE_NOT_SUPPORTED_BY_IDENTITY_LEDGER:{season}:{subfarm}")
        key = ("REUSED_SUBFARM", season, subfarm, parents)
        reused_group = group_by_key.setdefault(key, _new_group(key))
        reused_group["reused_subfarm_flag"] = True
        reused_group["subfarm_labels"].add(subfarm)
        reused_group["seasons"].add(season)
        reused_group["source_labels"].update(parents)
        for parent in parents:
            label_key = (season, parent)
            if label_key not in farm_by_key:
                raise ValueError(f"SUBFARM_PARENT_LABEL_NOT_FOUND:{season}:{parent}")
            reused_group["reference_label_keys"].add(label_key)
            parent_group = group_for_label[label_key]
            reused_group["related_parent_group_ids"].add(parent_group["group_id"])
            reused_group["supporting_evidence"].add(
                f"同名分场“{subfarm}”在来源账本中出现在多个农场名下；需确认是同一业务分场还是同名不同地点。"
            )
        return reused_group

    issue_to_group: dict[str, str] = {}
    for issue in sorted(manual_issues, key=lambda item: item["issue_id"]):
        issue_id = issue.get("issue_id", "").strip()
        seasons = _exact_values(issue.get("season", ""))
        source_labels = _exact_values(issue.get("source_label", ""))
        source_subfarms = _exact_values(issue.get("source_subfarm", ""))
        if not issue_id or issue_id in issue_to_group:
            raise ValueError(f"MANUAL_ISSUE_ID_CONFLICT:{issue_id}")
        problem = issue.get("problem", "")
        mandatory_id = next((value for value in MANDATORY_GROUPS if value in problem), "")
        if mandatory_id:
            assigned_group = mandatory_groups.get(mandatory_id)
            if assigned_group is None:
                raise ValueError(f"MANDATORY_RELATION_NOT_PRESENT_IN_SOURCE:{mandatory_id}")
        elif len(seasons) > 1 or len(source_labels) > 1 or len(source_subfarms) > 1:
            if not seasons or (not source_labels and not source_subfarms):
                raise ValueError(f"MULTI_VALUE_ISSUE_WITHOUT_EXACT_RELATION:{issue_id}")
            current_bases = _exact_values(issue.get("current_base", ""))
            relation_key = (
                "EXPLICIT_MANUAL_RELATION",
                seasons,
                source_labels,
                source_subfarms,
                current_bases,
            )
            assigned_group = group_by_key.setdefault(relation_key, _new_group(relation_key))
            assigned_group["explicit_relation_flag"] = True
            assigned_group["source_labels"].update(source_labels)
            assigned_group["subfarm_labels"].update(source_subfarms)
            assigned_group["seasons"].update(seasons)
            exact_references = {
                (season, label)
                for season in seasons
                for label in source_labels
                if (season, label) in farm_by_key
            }
            if source_labels and not exact_references:
                raise ValueError(f"MANUAL_RELATION_HAS_NO_EXACT_LEDGER_MATCH:{issue_id}")
            for season, subfarm in (
                (season, subfarm) for season in seasons for subfarm in source_subfarms
            ):
                matches = identity_by_subfarm.get((season, subfarm), [])
                exact_references.update(
                    (season, row["source_farm_label"].strip()) for row in matches
                )
            assigned_group["reference_label_keys"].update(exact_references)
            assigned_group["reference_identity_label_rows"].update(
                {key: farm_by_key[key] for key in exact_references}
            )
        else:
            season = seasons[0] if seasons else ""
            label = source_labels[0] if source_labels else ""
            subfarm = source_subfarms[0] if source_subfarms else ""
            if label:
                assigned_group = group_for_label.get((season, label))
                if assigned_group is None:
                    raise ValueError(f"MANUAL_ISSUE_SOURCE_LABEL_NOT_FOUND:{season}:{label}")
            elif subfarm:
                assigned_group = ensure_reused_subfarm_group(season, subfarm)
            else:
                raise ValueError(f"MANUAL_ISSUE_WITHOUT_IDENTITY:{issue_id}")
        assigned_group["manual_issues"][issue_id] = issue
        assigned_group["supporting_evidence"].add(problem)
        assigned_group["member_change_flag"] |= _is_member_change_problem(problem)
        assigned_group["extreme_yield_jump_flag"] |= _is_yield_jump_problem(problem)
        assigned_group["low_coverage_flag"] |= _is_low_coverage_problem(problem)
        issue_to_group[issue_id] = assigned_group["group_id"]

    for anomaly in anomaly_rows:
        season = anomaly.get("season", "").strip()
        label = anomaly.get("source_label", "").strip()
        subfarm = anomaly.get("source_subfarm", "").strip()
        anomaly_group: dict[str, Any] | None = None
        if label and (season, label) in group_for_label:
            anomaly_group = group_for_label[(season, label)]
        elif subfarm and len(identity_by_subfarm.get((season, subfarm), [])) > 1:
            anomaly_group = ensure_reused_subfarm_group(season, subfarm)
        if anomaly_group is None:
            continue
        anomaly_group["anomaly_rows"].append(anomaly)
        problem = anomaly.get("problem", "")
        anomaly_group["supporting_evidence"].add(problem)
        anomaly_group["extreme_yield_jump_flag"] |= _is_yield_jump_problem(problem)
        anomaly_group["low_coverage_flag"] |= _is_low_coverage_problem(problem)

    for change in member_change_rows or []:
        from_season = change.get("from_season", "").strip()
        to_season = change.get("to_season", "").strip()
        member_change_labels: set[str] = set()
        for field in (
            "member_added",
            "member_removed",
            "member_unresolved_from",
            "member_unresolved_to",
        ):
            member_change_labels.update(_split_python_list(change.get(field, "")))
        for season in (from_season, to_season):
            for label in member_change_labels:
                member_group = group_for_label.get((season, label))
                if member_group is not None:
                    member_group["member_change_rows"].append(change)
                    member_group["member_change_flag"] = True
                    member_group["supporting_evidence"].add(
                        "冻结成员清单显示相邻产季的成员/候选名称集合发生变化；变化原因尚未由业务确认。"
                    )

    for group in group_by_key.values():
        _finalize_group(group, farm_by_key)

    all_owned_label_keys = [
        key for group in group_by_key.values() for key in group["owned_label_keys"]
    ]
    if len(all_owned_label_keys) != len(set(all_owned_label_keys)):
        raise ValueError("SOURCE_LABEL_QUANTITY_HAS_MULTIPLE_GROUP_OWNERS")
    if set(all_owned_label_keys) != set(farm_by_key):
        raise ValueError("SOURCE_LABEL_QUANTITY_GROUP_OWNERSHIP_INCOMPLETE")

    # Supporting-only groups preserve audit lineage but are not questions by themselves.
    groups = [
        group
        for group in group_by_key.values()
        if group["manual_issues"]
        or group["anomaly_rows"]
        or group["member_change_rows"]
        or group["mandatory_group_id"]
    ]
    covered = [issue_id for group in groups for issue_id in group["covered_issue_ids"]]
    if len(covered) != len(set(covered)) or set(covered) != set(issue_to_group):
        raise ValueError("MANUAL_ISSUE_GROUPING_NOT_ONE_TO_ONE")
    return sorted(groups, key=lambda group: group["group_id"])


def _finalize_group(
    group: dict[str, Any], farm_by_key: dict[tuple[str, str], dict[str, str]]
) -> None:
    own_rows = [farm_by_key[key] for key in sorted(group["owned_label_keys"])]
    reference_rows = [farm_by_key[key] for key in sorted(group["reference_label_keys"])]
    impact_label_keys = group["owned_label_keys"] | group["reference_label_keys"]
    quantity_rows: dict[tuple[str, str], dict[str, str]] = {}
    for row in own_rows + reference_rows:
        key = (row["season"], row["source_farm_label"].strip())
        quantity_rows[key] = row

    raw_by_season: dict[str, Decimal] = defaultdict(Decimal)
    business_by_season: dict[str, Decimal] = defaultdict(Decimal)
    observed_days: dict[str, int] = defaultdict(int)
    mapped_keys: set[tuple[str, str]] = set()
    unresolved_keys: set[tuple[str, str]] = set()
    excluded_keys: set[tuple[str, str]] = set()
    current_base_ids: set[str] = set()
    current_base_names: set[str] = set()
    candidate_base_ids: set[str] = set()
    candidate_base_names: set[str] = set()
    statuses: set[str] = set()
    match_types: set[str] = set()
    authorities: set[str] = set()
    mapping_evidence: set[str] = set()

    for key, row in sorted(quantity_rows.items()):
        status = row["current_mapping_status"]
        raw_by_season[key[0]] += _amount(row, "quantity_kg")
        business_by_season[key[0]] += _amount(row, "business_window_quantity_kg")
        observed_days[key[0]] += int(row.get("business_window_observed_day_count", "0") or 0)
        statuses.add(status)
        match_types.add(row.get("current_match_type", ""))
        authorities.add(row.get("mapping_authority", ""))
        if row.get("mapping_evidence"):
            mapping_evidence.add(row["mapping_evidence"])
        candidates = _candidate_ids(row.get("current_candidate_base_id", ""))
        names = _candidate_names(row.get("current_canonical_base_name", ""))
        candidate_base_ids.update(candidates)
        candidate_base_names.update(names)
        if status in ACCEPTED:
            mapped_keys.add(key)
            if len(candidates) != 1:
                raise ValueError(f"ACCEPTED_MAPPING_NOT_SINGLE_BASE:{key}")
            current_base_ids.update(candidates)
            current_base_names.update(names)
        elif status == "UNRESOLVED":
            unresolved_keys.add(key)
        elif status == "EXCLUDED":
            excluded_keys.add(key)

    manual = list(group["manual_issues"].values())
    problems = [item.get("problem", "") for item in manual]
    identity_review = (
        bool(group["mandatory_group_id"])
        or group["member_change_flag"]
        or any(status in {"UNRESOLVED", "EXCLUDED", "CONFLICTING"} for status in statuses)
        or any(_is_identity_issue(problem) for problem in problems)
    )
    risk_label_keys = (
        impact_label_keys if identity_review and not group["reused_subfarm_flag"] else set()
    )
    risk_rows = [farm_by_key[key] for key in sorted(risk_label_keys)]
    if group["reused_subfarm_flag"]:
        relation_type = "REUSED_SUBFARM_PARENT_REVIEW"
    elif group["member_change_flag"]:
        relation_type = "CROSS_SEASON_MEMBERSHIP_CHANGE"
    elif any(status == "EXCLUDED" for status in statuses):
        relation_type = "EXPLICIT_SCOPE_EXCLUSION_REVIEW"
    elif any(status == "UNRESOLVED" for status in statuses) and candidate_base_ids:
        relation_type = "UNRESOLVED_WITH_CANDIDATE"
    elif any(status == "UNRESOLVED" for status in statuses):
        relation_type = "UNRESOLVED_WITHOUT_CANDIDATE"
    elif any(status in ACCEPTED for status in statuses) and identity_review:
        relation_type = "CURRENT_ACCEPTED_MAPPING_REVIEW"
    else:
        relation_type = "SUPPORTING_ONLY"

    mapped_kg = (
        sum(
            (
                _amount(row, "quantity_kg")
                for row in risk_rows
                if row["current_mapping_status"] in ACCEPTED
            ),
            Decimal(0),
        )
        if identity_review
        else Decimal(0)
    )
    business_mapped_kg = (
        sum(
            (
                _amount(row, "business_window_quantity_kg")
                for row in risk_rows
                if row["current_mapping_status"] in ACCEPTED
            ),
            Decimal(0),
        )
        if identity_review
        else Decimal(0)
    )
    unresolved_kg = (
        sum(
            (
                _amount(row, "quantity_kg")
                for row in risk_rows
                if row["current_mapping_status"] == "UNRESOLVED"
            ),
            Decimal(0),
        )
        if identity_review
        else Decimal(0)
    )
    business_unresolved_kg = (
        sum(
            (
                _amount(row, "business_window_quantity_kg")
                for row in risk_rows
                if row["current_mapping_status"] == "UNRESOLVED"
            ),
            Decimal(0),
        )
        if identity_review
        else Decimal(0)
    )
    excluded_kg = sum(
        (
            _amount(row, "quantity_kg")
            for row in own_rows
            if row["current_mapping_status"] == "EXCLUDED"
        ),
        Decimal(0),
    )

    if mapped_kg > 0:
        priority_band = "BAND_A_CURRENT_MAPPING_RISK"
    elif unresolved_kg > 0 and identity_review:
        priority_band = "BAND_B_UNRESOLVED_HIGH_VOLUME"
    elif identity_review or relation_type in {
        "CROSS_SEASON_MEMBERSHIP_CHANGE",
        "REUSED_SUBFARM_PARENT_REVIEW",
        "EXPLICIT_SCOPE_EXCLUSION_REVIEW",
    }:
        priority_band = "BAND_C_CROSS_SEASON_STRUCTURE"
    else:
        priority_band = "BAND_D_SUPPORTING_ONLY"

    if mapped_kg and unresolved_kg:
        impact_type = "MIXED_CURRENT_MAPPING_AND_RECOVERABLE_UNRESOLVED_KG"
    elif mapped_kg:
        impact_type = "CURRENTLY_MAPPED_KG_AT_RISK"
    elif unresolved_kg:
        impact_type = "UNRESOLVED_KG_RECOVERABLE"
    elif group["reused_subfarm_flag"]:
        impact_type = "STRUCTURAL_RELATION_ONLY_NON_ADDITIVE_QUANTITY"
    else:
        impact_type = "NO_DIRECT_IDENTITY_QUANTITY_IMPACT"

    raw_reference_total = (
        sum(raw_by_season.values(), Decimal(0)) if group["reference_label_keys"] else Decimal(0)
    )
    reference_identity_rows = {
        key: farm_by_key[key] for key in group["reference_label_keys"] if key in farm_by_key
    }
    group.update(
        {
            "relation_type": relation_type,
            "priority_band": priority_band,
            "impact_type": impact_type,
            "raw_kg_by_season": dict(sorted(raw_by_season.items())),
            "business_window_kg_by_season": dict(sorted(business_by_season.items())),
            "raw_total_kg": sum(raw_by_season.values(), Decimal(0)),
            "reference_raw_kg_by_season": {
                season: sum(
                    (
                        _amount(row, "quantity_kg")
                        for key, row in quantity_rows.items()
                        if key[0] == season and key in group["reference_label_keys"]
                    ),
                    Decimal(0),
                )
                for season in sorted({key[0] for key in group["reference_label_keys"]})
            },
            "mapped_kg_at_risk": mapped_kg,
            "business_window_mapped_kg_at_risk": business_mapped_kg,
            "unresolved_kg_potentially_recoverable": unresolved_kg,
            "business_window_unresolved_kg_potentially_recoverable": business_unresolved_kg,
            "explicitly_excluded_kg": excluded_kg,
            "reference_raw_kg": raw_reference_total,
            "reference_identity_label_rows": reference_identity_rows,
            "observed_days_by_season": dict(sorted(observed_days.items())),
            "mapped_label_keys": mapped_keys & risk_label_keys,
            "unresolved_label_keys": unresolved_keys & risk_label_keys,
            "current_base_ids": current_base_ids,
            "current_base_names": current_base_names,
            "candidate_base_ids": candidate_base_ids,
            "candidate_base_names": candidate_base_names,
            "current_mapping_statuses": statuses,
            "current_mapping_types": match_types,
            "mapping_authorities": authorities,
            "mapping_evidence": mapping_evidence,
            "source_labels": set(group["source_labels"]),
            "subfarm_labels": set(group["subfarm_labels"]),
            "seasons": set(group["seasons"]),
            "covered_issue_ids": set(group["manual_issues"]),
            "manual_issue_count": len(group["manual_issues"]),
            "p1_issue_count": sum(item.get("priority") == "P1_HIGH" for item in manual),
            "p2_issue_count": sum(item.get("priority") == "P2_REVIEW" for item in manual),
            "anomaly_issue_count": len(group["anomaly_rows"]),
            "supporting_evidence": set(group["supporting_evidence"]),
            "related_parent_group_ids": set(group["related_parent_group_ids"]),
            "quantity_ownership": (
                "SUPPORTING_REFERENCE_NON_ADDITIVE"
                if group["reference_label_keys"] and not group["owned_label_keys"]
                else "UNIQUE_SEASON_AND_SOURCE_FARM_LABEL_OWNER"
            ),
            "business_decision_prefilled": False,
            "affected_base_ids": set(current_base_ids) | set(candidate_base_ids),
            "affected_seasons": set(group["seasons"]),
            "model_impact_evidence_status": "AWAITING_FROZEN_SCOPE_BINDING",
        }
    )


def attach_model_impact(
    group: dict[str, Any],
    *,
    prior_history_keys: set[tuple[str, str]],
    validation_label_keys: set[tuple[str, str]],
    ab_comparison_keys: set[tuple[str, str]],
) -> None:
    all_identity_rows = {
        **group["identity_label_rows"],
        **group.get("reference_identity_label_rows", {}),
    }
    accepted_pairs = {
        (row.get("current_candidate_base_id", ""), row["season"])
        for row in all_identity_rows.values()
        if row.get("current_mapping_status") in ACCEPTED and row.get("current_candidate_base_id")
    }
    group["used_in_frozen_prior_history"] = bool(accepted_pairs & prior_history_keys)
    group["used_in_v07_validation_labels"] = bool(accepted_pairs & validation_label_keys)
    group["used_in_v07_ab_comparison"] = bool(accepted_pairs & ab_comparison_keys)
    group["affected_base_ids"] = set(group["current_base_ids"]) | set(group["candidate_base_ids"])
    group["model_impact_evidence_status"] = (
        "S1_R2_AUTHORITY_MATCH;S3_BASE_SEASON_SCOPE_ONLY_SOURCE_LABEL_MEMBERSHIP_NOT_PROVEN"
    )


def select_confirmation_groups(
    groups: list[dict[str, Any]], minimum: int = 20, maximum: int = 40
) -> list[dict[str, Any]]:
    if minimum < 0 or maximum < minimum:
        raise ValueError("Invalid shortlist bounds")
    mandatory = {
        group["mandatory_group_id"]: group for group in groups if group.get("mandatory_group_id")
    }
    missing_mandatory = set(MANDATORY_GROUPS) - set(mandatory)
    if missing_mandatory:
        raise ValueError("MANDATORY_HIGH_RISK_GROUP_MISSING:" + ",".join(sorted(missing_mandatory)))

    band_order = (
        "BAND_A_CURRENT_MAPPING_RISK",
        "BAND_B_UNRESOLVED_HIGH_VOLUME",
        "BAND_C_CROSS_SEASON_STRUCTURE",
    )

    def rank(group: dict[str, Any], amount_key: str) -> tuple[Any, ...]:
        amount = group.get(amount_key, Decimal(0))
        return (-amount, -len(group.get("seasons", [])), group["group_id"])

    band_groups: dict[str, list[dict[str, Any]]] = {
        "BAND_A_CURRENT_MAPPING_RISK": sorted(
            (g for g in groups if g["priority_band"] == band_order[0]),
            key=lambda g: rank(g, "mapped_kg_at_risk"),
        ),
        "BAND_B_UNRESOLVED_HIGH_VOLUME": sorted(
            (g for g in groups if g["priority_band"] == band_order[1]),
            key=lambda g: rank(g, "unresolved_kg_potentially_recoverable"),
        ),
        "BAND_C_CROSS_SEASON_STRUCTURE": sorted(
            (g for g in groups if g["priority_band"] == band_order[2]),
            key=lambda g: rank(
                g,
                "reference_raw_kg"
                if g["quantity_ownership"] == "SUPPORTING_REFERENCE_NON_ADDITIVE"
                else "raw_total_kg",
            ),
        ),
    }
    # Cross-season structure ranking uses the unique source labels touched, not anomaly rows.
    for group in band_groups[band_order[2]]:
        if "raw_total_kg" not in group:
            group["raw_total_kg"] = sum(group["raw_kg_by_season"].values(), Decimal(0))
    band_groups[band_order[2]].sort(key=lambda g: rank(g, "raw_total_kg"))

    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    for mandatory_id in MANDATORY_GROUPS:
        group = mandatory[mandatory_id]
        if group["group_id"] not in selected_ids:
            selected.append(group)
            selected_ids.add(group["group_id"])

    eligible_count = sum(len(rows) for rows in band_groups.values())
    target_count = min(maximum, max(minimum, min(eligible_count, maximum)))
    positions = {band: 0 for band in band_order}
    while len(selected) < target_count:
        added = False
        for band in band_order:
            candidates = band_groups[band]
            while (
                positions[band] < len(candidates)
                and candidates[positions[band]]["group_id"] in selected_ids
            ):
                positions[band] += 1
            if positions[band] >= len(candidates):
                continue
            group = candidates[positions[band]]
            positions[band] += 1
            selected.append(group)
            selected_ids.add(group["group_id"])
            added = True
            if len(selected) >= maximum:
                break
        if not added:
            break
    return selected


def _season_date(value: str) -> str:
    day = date.fromisoformat(value[:10])
    if date(2023, 7, 1) <= day <= date(2024, 4, 15):
        return "2023-2024"
    if date(2024, 7, 1) <= day <= date(2025, 4, 15):
        return "2024-2025"
    if date(2025, 7, 22) <= day <= date(2026, 4, 15):
        return "2025-2026"
    raise ValueError(f"S3 training target date outside frozen business windows: {value}")


def load_frozen_model_scopes(
    farm_label_rows: list[dict[str, str]],
    s1_evidence_path: Path,
    s3_evidence_path: Path,
    s3_artifacts_dir: Path,
) -> tuple[dict[str, set[tuple[str, str]]], dict[str, Any]]:
    s1 = _read_json(s1_evidence_path)
    s3 = _read_json(s3_evidence_path)
    s1_authorities = s1.get("authorities", {})
    if (
        s1_authorities.get("historical_identity_mapping_sha256")
        != EXPECTED_AUTHORITY_HASHES["historical_identity_mapping"]
    ):
        raise ValueError("S1_IDENTITY_AUTHORITY_HASH_MISMATCH")
    if (
        s1_authorities.get("base_registry_member_mapping_sha256")
        != EXPECTED_AUTHORITY_HASHES["base_member_mapping"]
    ):
        raise ValueError("S1_MEMBER_AUTHORITY_HASH_MISMATCH")
    if (
        s1_authorities.get("combined_identity_authority_sha256")
        != S1_COMBINED_IDENTITY_AUTHORITY_SHA256
    ):
        raise ValueError("S1_COMBINED_IDENTITY_AUTHORITY_HASH_MISMATCH")
    accepted_by_season: dict[str, set[str]] = defaultdict(set)
    for row in farm_label_rows:
        if row.get("current_mapping_status") in ACCEPTED:
            accepted_by_season[row["season"]].add(row.get("current_candidate_base_id", ""))
    accepted_by_season = {season: ids - {""} for season, ids in accepted_by_season.items()}

    prior_history_keys: set[tuple[str, str]] = set()
    validation_label_keys: set[tuple[str, str]] = set()
    s1_scope_proof: dict[str, Any] = {}
    for fold_name in ("fold_a", "fold_b"):
        fold = s1["folds"][fold_name]
        prior = fold["required_prior_season"]
        accepted_prior = accepted_by_season.get(prior, set())
        eligible_count = int(fold["prediction_eligible_base_count"])
        if len(accepted_prior) != eligible_count:
            raise ValueError(f"S1_PRIOR_BASE_SCOPE_NOT_RECONCILED:{fold_name}")
        prior_history_keys.update((base_id, prior) for base_id in accepted_prior)
        validation_season = fold["validation_season"]
        validation_ids = accepted_prior & accepted_by_season.get(validation_season, set())
        reported_validation_count = int(fold["validation_actual_base_count"])
        if len(validation_ids) != reported_validation_count:
            raise ValueError(f"S1_VALIDATION_BASE_SCOPE_NOT_RECONCILED:{fold_name}")
        validation_label_keys.update((base_id, validation_season) for base_id in validation_ids)
        s1_scope_proof[fold_name] = {
            "prior_season": prior,
            "accepted_prior_base_count": len(accepted_prior),
            "reported_prediction_eligible_base_count": eligible_count,
            "validation_season": validation_season,
            "accepted_identity_intersection_base_count": len(validation_ids),
            "reported_validation_actual_base_count": reported_validation_count,
            "scope_match": True,
        }

    s3_authorities = s3.get("authorities", {})
    s3_identity_sources = s3_authorities.get("identity_mapping_sources", {})
    if (
        s3_identity_sources.get("historical_identity_mapping_sha256")
        != EXPECTED_AUTHORITY_HASHES["historical_identity_mapping"]
    ):
        raise ValueError("S3_HISTORICAL_IDENTITY_AUTHORITY_HASH_MISMATCH")
    if s3_authorities.get("identity_mapping_sha256") != S3_FROZEN_IDENTITY_MAPPING_SHA256:
        raise ValueError("S3_FROZEN_IDENTITY_MAPPING_HASH_MISMATCH")
    if (
        s3_identity_sources.get("base_registry_member_mapping_sha256")
        != S3_V05_MEMBER_MAPPING_SHA256
    ):
        raise ValueError("S3_FROZEN_MEMBER_MAPPING_HASH_MISMATCH")
    v05_evidence = _read_json(Path("docs/v0-5/s1/evidence.json"))
    if (
        v05_evidence.get("artifact_file_hashes", {}).get("member-farm-mapping.csv")
        != S3_V05_MEMBER_MAPPING_SHA256
    ):
        raise ValueError("S3_LEGACY_MEMBER_MAPPING_SOURCE_NOT_RECONCILED")

    s3_comparison_keys: set[tuple[str, str]] = set()
    s3_artifact_proof: dict[str, Any] = {}
    per_base = s3.get("per_base", [])
    for fold_name, fold_id in (("fold_a", "FOLD_A"), ("fold_b", "FOLD_B")):
        public_fold = s3["folds"][fold_name]
        private_fold = s3_artifacts_dir / fold_name
        artifacts: dict[str, dict[str, Any]] = {}
        for model_name in ("model_a", "model_b"):
            artifact = _read_json(private_fold / f"{model_name}_artifact.json")
            expected = public_fold[model_name].get("artifact_hash")
            if artifact.get("artifact_hash") != expected:
                raise ValueError(f"S3_MODEL_ARTIFACT_IDENTITY_MISMATCH:{fold_name}:{model_name}")
            artifacts[model_name] = artifact
        a_keys = list(artifacts["model_a"].get("training_row_keys", []))
        b_keys = list(artifacts["model_b"].get("training_row_keys", []))
        expected_count = int(public_fold["training_row_count"])
        if a_keys != b_keys or len(a_keys) != expected_count or len(a_keys) != len(set(a_keys)):
            raise ValueError(f"S3_MODEL_TRAINING_ROWS_NOT_PARITY:{fold_name}")
        if len(a_keys) != int(public_fold["model_a"].get("training_row_key_count", -1)):
            raise ValueError(f"S3_TRAINING_KEY_COUNT_MISMATCH:{fold_name}")
        training_pairs: set[tuple[str, str]] = set()
        for row_key in a_keys:
            pieces = row_key.split("+", 1)
            if len(pieces) != 2:
                raise ValueError(f"S3_TRAINING_ROW_KEY_MALFORMED:{fold_name}")
            base_id = pieces[0]
            target_date = row_key.rsplit("+", 1)[-1]
            training_pairs.add((base_id, _season_date(target_date)))
        expected_train_seasons = set(public_fold["train_seasons"])
        if {season for _, season in training_pairs} != expected_train_seasons:
            raise ValueError(f"S3_TRAINING_SEASON_SCOPE_MISMATCH:{fold_name}")

        validation_rows = [row for row in per_base if row.get("fold_id") == fold_id]
        validation_pairs = {(row["base_id"], row["season"]) for row in validation_rows}
        if len(validation_pairs) != int(public_fold["validation_base_count"]):
            raise ValueError(f"S3_VALIDATION_BASE_SCOPE_NOT_RECONCILED:{fold_name}")
        s3_comparison_keys.update(training_pairs)
        s3_comparison_keys.update(validation_pairs)
        s3_artifact_proof[fold_name] = {
            "model_a_artifact_hash": artifacts["model_a"]["artifact_hash"],
            "model_b_artifact_hash": artifacts["model_b"]["artifact_hash"],
            "training_row_key_count": len(a_keys),
            "training_base_season_count": len(training_pairs),
            "training_seasons": sorted(expected_train_seasons),
            "validation_base_season_count": len(validation_pairs),
            "validation_season": public_fold["validation_season"],
            "a_b_training_row_keys_equal": True,
        }

    scopes = {
        "prior_history_keys": prior_history_keys,
        "validation_label_keys": validation_label_keys,
        "ab_comparison_keys": s3_comparison_keys,
    }
    proof = {
        "current_source_audit_authorities": {
            "historical_identity_mapping_sha256": EXPECTED_AUTHORITY_HASHES[
                "historical_identity_mapping"
            ],
            "base_member_mapping_r2_sha256": EXPECTED_AUTHORITY_HASHES["base_member_mapping"],
            "combined_identity_authority_sha256": S1_COMBINED_IDENTITY_AUTHORITY_SHA256,
        },
        "s1_authority_hashes_match_source_audit": True,
        "s1_prior_and_validation_base_scopes": s1_scope_proof,
        "s3_frozen_authorities": {
            "identity_mapping_sha256": S3_FROZEN_IDENTITY_MAPPING_SHA256,
            "historical_identity_mapping_sha256": EXPECTED_AUTHORITY_HASHES[
                "historical_identity_mapping"
            ],
            "member_mapping_sha256": S3_V05_MEMBER_MAPPING_SHA256,
        },
        "s3_historical_identity_hash_matches_source_audit": True,
        "s3_member_mapping_hash_matches_current_r2": False,
        "s3_member_mapping_hash_matches_frozen_v05_evidence": True,
        "s3_source_label_level_membership_proven": False,
        "s3_impact_grain": "BASE_SEASON_SCOPE_OVERLAP_ONLY",
        "s3_frozen_artifact_scope": s3_artifact_proof,
        "impact_grain": ("S1_SOURCE_LABEL_TO_BASE_SEASON;S3_BASE_SEASON_COHORT_OVERLAP_ONLY"),
        "model_impact_flags_require_base_season_scope": True,
    }
    return scopes, proof


def _json_amounts(values: dict[str, Decimal]) -> str:
    return json_text({key: decimal_text(value) for key, value in sorted(values.items())})


def _label_key_text(values: set[tuple[str, str]]) -> str:
    return json_text(
        [{"season": season, "source_farm_label": label} for season, label in sorted(values)]
    )


def _group_public_row(group: dict[str, Any], question_number: str = "") -> dict[str, Any]:
    raw_total = sum(group["raw_kg_by_season"].values(), Decimal(0))
    mapped_label_keys = group["mapped_label_keys"]
    unresolved_label_keys = group["unresolved_label_keys"]
    base_model_impact = {
        "used_in_frozen_prior_history": group.get("used_in_frozen_prior_history", False),
        "used_in_v07_validation_labels": group.get("used_in_v07_validation_labels", False),
        "used_in_v07_ab_comparison": group.get("used_in_v07_ab_comparison", False),
    }
    return {
        "group_id": group["group_id"],
        "mandatory_group_id": group.get("mandatory_group_id", ""),
        "relation_type": group["relation_type"],
        "priority_band": group["priority_band"],
        "impact_type": group["impact_type"],
        "question_number": question_number,
        "source_labels": json_text(sorted(group["source_labels"])),
        "subfarm_labels": json_text(sorted(group["subfarm_labels"])),
        "seasons": json_text(sorted(group["seasons"])),
        "current_base_ids": json_text(sorted(group["current_base_ids"])),
        "current_base_names": json_text(sorted(group["current_base_names"])),
        "candidate_base_ids": json_text(sorted(group["candidate_base_ids"])),
        "candidate_base_names": json_text(sorted(group["candidate_base_names"])),
        "current_mapping_statuses": json_text(sorted(group["current_mapping_statuses"])),
        "current_mapping_types": json_text(
            sorted(value for value in group["current_mapping_types"] if value)
        ),
        "raw_kg_by_season": _json_amounts(group["raw_kg_by_season"]),
        "business_window_kg_by_season": _json_amounts(group["business_window_kg_by_season"]),
        "mapped_kg_at_risk": decimal_text(group["mapped_kg_at_risk"]),
        "business_window_mapped_kg_at_risk": decimal_text(
            group["business_window_mapped_kg_at_risk"]
        ),
        "unresolved_kg_potentially_recoverable": decimal_text(
            group["unresolved_kg_potentially_recoverable"]
        ),
        "business_window_unresolved_kg_potentially_recoverable": decimal_text(
            group["business_window_unresolved_kg_potentially_recoverable"]
        ),
        "explicitly_excluded_kg": decimal_text(group["explicitly_excluded_kg"]),
        "reference_raw_kg_by_season": _json_amounts(group["reference_raw_kg_by_season"]),
        "observed_days_by_season": json_text(
            dict(sorted(group["observed_days_by_season"].items()))
        ),
        "mapped_label_keys": _label_key_text(mapped_label_keys),
        "unresolved_label_keys": _label_key_text(unresolved_label_keys),
        "owned_label_keys": _label_key_text(group["owned_label_keys"]),
        "reference_label_keys": _label_key_text(group["reference_label_keys"]),
        "covered_issue_ids": json_text(sorted(group["covered_issue_ids"])),
        "manual_issue_count": group["manual_issue_count"],
        "p1_issue_count": group["p1_issue_count"],
        "p2_issue_count": group["p2_issue_count"],
        "anomaly_issue_count": group["anomaly_issue_count"],
        "member_change_flag": str(bool(group["member_change_flag"])).lower(),
        "extreme_yield_jump_flag": str(bool(group["extreme_yield_jump_flag"])).lower(),
        "low_coverage_flag": str(bool(group["low_coverage_flag"])).lower(),
        "reused_subfarm_flag": str(bool(group["reused_subfarm_flag"])).lower(),
        "affected_base_ids": json_text(sorted(group["affected_base_ids"])),
        "affected_seasons": json_text(sorted(group["affected_seasons"])),
        "used_in_frozen_prior_history": str(
            base_model_impact["used_in_frozen_prior_history"]
        ).lower(),
        "used_in_v07_validation_labels": str(
            base_model_impact["used_in_v07_validation_labels"]
        ).lower(),
        "used_in_v07_ab_comparison": str(base_model_impact["used_in_v07_ab_comparison"]).lower(),
        "model_impact_evidence_status": group["model_impact_evidence_status"],
        "quantity_ownership": group["quantity_ownership"],
        "business_decision_prefilled": "false",
        "supporting_evidence": json_text(sorted(group["supporting_evidence"])),
        "mapping_authorities": json_text(
            sorted(value for value in group["mapping_authorities"] if value)
        ),
        "mapping_evidence": json_text(sorted(group["mapping_evidence"])),
        "related_parent_group_ids": json_text(sorted(group["related_parent_group_ids"])),
        "_raw_total_kg": raw_total,
    }


def _question_text(group: dict[str, Any], question_number: str) -> str:
    seasons = sorted(group["seasons"])
    identity_rows = {
        **group["identity_label_rows"],
        **group.get("reference_identity_label_rows", {}),
    }
    rows = list(identity_rows.values())
    current_pairs = sorted(
        {
            (row["season"], row.get("current_canonical_base_name", ""))
            for row in rows
            if row.get("current_mapping_status") in ACCEPTED
        }
    )
    candidate_names = sorted(group["candidate_base_names"])
    source_labels = sorted(group["source_labels"])
    subfarms = sorted(group["subfarm_labels"])
    raw = _json_amounts(group["raw_kg_by_season"])
    business = _json_amounts(group["business_window_kg_by_season"])

    lines = [
        f"## 问题 {question_number}",
        "",
        f"涉及产季：{'、'.join(seasons) or '未能从来源行确定'}",
    ]
    if group["reused_subfarm_flag"]:
        lines.extend(
            [
                f"分场名称：{'、'.join(subfarms)}",
                f"涉及农场名称：{'、'.join(source_labels)}",
                "请确认：这些农场名下的同名分场，是否确实是同一个业务分场？如果不是，请分别说明正确归属。",
                f"父级农场原始数量仅作关系参考：`{raw}` kg；"
                "这笔数量不归因给分场，也不加入可回收/撤回总量。",
            ]
        )
    else:
        lines.append(f"原始农场/基地名称：{'、'.join(source_labels)}")
        if current_pairs:
            current_text = "；".join(
                f"{season} 当前归入 {base}" for season, base in current_pairs if base
            )
            lines.append(f"当前已接受的归属：{current_text}")
        if candidate_names:
            lines.append(f"现有候选（仅供核对，不代表已确认）：{'、'.join(candidate_names)}")
        if group["unresolved_kg_potentially_recoverable"] > 0:
            lines.append(
                "当前仍有未归属的采收记录，请按产季确认正确基地；没有候选时请填写基地名称或选择不属于当前基地范围。"
            )
        else:
            lines.append(
                "请确认这些来源名称在对应产季是否属于所列的同一业务基地；如有变更，请按产季分别说明。"
            )

    if not group["reused_subfarm_flag"]:
        lines.extend(
            [
                f"原始源数量（按产季 + 农场名称去重）：`{raw}` kg",
                f"业务窗口内数量：`{business}` kg",
                f"当前已映射、需要复核：{decimal_text(group['mapped_kg_at_risk'])} kg",
                "当前未映射、确认后可能纳入："
                f"{decimal_text(group['unresolved_kg_potentially_recoverable'])} kg",
                "",
                "为什么需要确认：",
            ]
        )
    else:
        lines.extend(
            [
                "父级农场的实际映射/未映射数量无法据此归因到同名分场。",
                "为什么需要确认：",
            ]
        )
    for item in sorted(group["supporting_evidence"]):
        text = item.lower()
        if "no accepted season-scoped mapping" in text:
            reason = "来源账本中有该名称，但当前没有正式确认的基地归属。"
        elif "source-member evidence changed" in text or "member" in text:
            reason = (
                "相邻产季的来源成员或名称集合发生变化，尚不能判断是组织调整、改名还是历史漏映。"
            )
        elif "same subfarm text appears" in text:
            reason = "同一分场文字出现在多个农场名称下，需要确认是否为同一业务实体。"
        elif "observed day" in text:
            reason = "部分产季只记录了少量采收日，数量覆盖有限，不能据此视为完整产季。"
        elif "reference-area yield ratio" in text:
            reason = "参考面积口径下出现亩产跳变提示；面积仅为参考面积，不能证明实际产量变化。"
        elif "task-mandated high-risk review" in text:
            reason = "该关系被列入本次重点人工复核清单；该标记本身不代表映射错误。"
        else:
            reason = "审计记录保留了一项相关来源差异，需要业务解释。"
        if reason not in lines:
            lines.append(f"- {reason}")
    if not any("- " in line for line in lines):
        lines.append("- 来源名称、当前归属或成员集合存在需要核实的差异。")

    lines.extend(["", "确认后可能产生的后续影响（本确认包不执行变更）："])
    if group["mapped_kg_at_risk"] > 0:
        lines.append(
            "- 若确认属于当前基地：后续可保留现有归属；"
            "若确认不属于：需另行授权撤回或重新归属已映射数量。"
        )
    if group["unresolved_kg_potentially_recoverable"] > 0:
        lines.append(
            "- 若确认属于某基地：后续可另开 authority correction 评估纳入；"
            "若不属于：继续保持排除/未映射。"
        )
    if group["reused_subfarm_flag"]:
        lines.append("- 若只有部分日期或成员属于：后续必须按明确日期/成员拆分，不能整季全量归属。")
    if "UNRESOLVED" in group["current_mapping_statuses"]:
        if len(group["candidate_base_ids"]) == 1:
            answer_options = (
                "可选回答：`YES_CANDIDATE`、`NO_CANDIDATE`、`PARTIAL`、`OUT_OF_SCOPE`、`UNKNOWN`。"
            )
        elif group["candidate_base_ids"]:
            answer_options = (
                "可选回答：填写正确 Base、`PARTIAL`、`OUT_OF_SCOPE` 或 `UNKNOWN`；"
                "候选不唯一时请勿勉强选择。"
            )
        else:
            answer_options = "可选回答：填写 `CORRECT_BASE=...`、`OUT_OF_SCOPE` 或 `UNKNOWN`。"
    else:
        answer_options = (
            "可选回答：`YES_ALL`（整季/全部成员均属于）、`NO`、`PARTIAL`、"
            "`OUT_OF_SCOPE`、`UNKNOWN`。"
        )
    lines.extend(
        [
            "",
            answer_options,
            "确认字段留空供业务人员填写；跨季关系请按产季分别回答。",
            "",
            "| 产季 | 业务决定（留空填写） | 补充说明 |",
            "|---|---|---|",
        ]
    )
    for season in SEASONS:
        status = "需确认" if season in seasons else "N/A"
        lines.append(f"| {season}（{status}） |  |  |")
    return "\n".join(lines)


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    with path.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=fields, extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    os.chmod(path, 0o600)


def _write_json(path: Path, value: Any) -> None:
    path.write_bytes(canonical_bytes(value) + b"\n")
    os.chmod(path, 0o600)


def _aggregate_selected(
    selected: list[dict[str, Any]],
    all_groups: list[dict[str, Any]],
    farm_rows: dict[tuple[str, str], dict[str, str]],
) -> dict[str, Any]:
    # Only owning identity groups contribute to rollup; reused-subfarm groups are references.
    selected_owned_keys = set().union(*(group["owned_label_keys"] for group in selected))
    selected_owned_sequence = [key for group in selected for key in group["owned_label_keys"]]
    if len(selected_owned_sequence) != len(set(selected_owned_sequence)):
        raise ValueError("SELECTED_QUANTITY_OWNERSHIP_DOUBLE_COUNT")
    selected_issue_ids = set().union(*(group["covered_issue_ids"] for group in selected))
    mapped_total = Decimal(0)
    unresolved_total = Decimal(0)
    all_mapped_total = Decimal(0)
    selected_mapped_keys = set().union(*(group["mapped_label_keys"] for group in selected))
    all_mapped_keys = set().union(
        *(
            group["mapped_label_keys"]
            for group in all_groups
            if group["priority_band"] == "BAND_A_CURRENT_MAPPING_RISK"
        )
    )
    selected_unresolved_keys = set().union(*(group["unresolved_label_keys"] for group in selected))
    for key in selected_mapped_keys:
        mapped_total += _amount(farm_rows[key], "quantity_kg")
    for key in selected_unresolved_keys:
        unresolved_total += _amount(farm_rows[key], "quantity_kg")
    for key in all_mapped_keys:
        all_mapped_total += _amount(farm_rows[key], "quantity_kg")

    source_unresolved_total = sum(
        (
            _amount(row, "quantity_kg")
            for row in farm_rows.values()
            if row["current_mapping_status"] == "UNRESOLVED"
        ),
        Decimal(0),
    )
    if source_unresolved_total != Decimal("28634123.590"):
        raise ValueError("SOURCE_WIDE_UNRESOLVED_QUANTITY_NOT_RECONCILED")

    return {
        "selected_owned_label_keys": selected_owned_keys,
        "selected_issue_ids": selected_issue_ids,
        "selected_manual_issue_count_covered": len(selected_issue_ids),
        "selected_manual_issue_share": Decimal(len(selected_issue_ids)) / Decimal(263),
        "selected_mapped_kg_at_risk": mapped_total,
        "total_mapped_kg_at_risk": all_mapped_total,
        "selected_share_of_mapped_kg_at_risk": (
            mapped_total / all_mapped_total if all_mapped_total else Decimal(0)
        ),
        "selected_unresolved_kg": unresolved_total,
        "total_unresolved_kg": source_unresolved_total,
        "selected_share_of_total_unresolved_kg": unresolved_total / source_unresolved_total,
        "all_manual_issue_count_in_selected_groups": len(selected_issue_ids),
    }


def _public_evidence(
    *,
    base_sha: str,
    input_hashes: dict[str, str],
    source_manifest_sha: str,
    group_rows: list[dict[str, Any]],
    selected_rows: list[dict[str, Any]],
    model_scope_proof: dict[str, Any],
    output_manifest: dict[str, Any],
    output_manifest_sha: str,
    private_dir_mode: str,
) -> dict[str, Any]:
    selected = [row for row in selected_rows]
    bands = {
        band: sum(row["priority_band"] == band for row in selected)
        for band in (
            "BAND_A_CURRENT_MAPPING_RISK",
            "BAND_B_UNRESOLVED_HIGH_VOLUME",
            "BAND_C_CROSS_SEASON_STRUCTURE",
        )
    }
    counts = {
        "original_manual_confirmation_count": 263,
        "grouped_business_relation_count": len(group_rows),
        "selected_confirmation_group_count": len(selected),
        "selected_group_count_min": 20,
        "selected_group_count_max": 40,
        "selected_band_counts": bands,
        "selected_manual_issue_count_covered": selected_rows[0].get("_selected_issue_count", 0)
        if selected_rows
        else 0,
        "all_263_issues_accounted_for": True,
    }
    mandatory = {row.get("mandatory_group_id") for row in selected}
    return {
        "task_id": TASK_ID,
        "result": "PASS",
        "repository": "xuezhiorange-png/blueberry-peak-forecast-agent",
        "base_sha": base_sha,
        "source_audit": {
            "task_id": SOURCE_TASK_ID,
            "merge_sha": base_sha,
            "status": "REQUIRES_BUSINESS_CONFIRMATION",
            "source_audit_manifest_sha256": source_manifest_sha,
            "manual_confirmation_sha256": input_hashes["manual_business_confirmation.csv"],
            "all_required_input_artifacts_hash_verified": True,
            "input_artifact_sha256": input_hashes,
        },
        "grouping_policy": {
            "version": "EXACT_RELATION_GROUP_R1",
            "fuzzy_or_similarity_clustering": False,
            "label_group_key": "EXACT_SOURCE_FARM_LABEL+CANONICAL_OR_CANDIDATE_BASE_ID_SET",
            "no_candidate_group_key": "EXACT_SOURCE_FARM_LABEL",
            "reused_subfarm_group_key": "SEASON+EXACT_SUBFARM_LABEL+SORTED_EXACT_PARENT_LABELS",
            "mandatory_group_ids": list(MANDATORY_GROUPS),
            "quantity_identity": "UNIQUE_SEASON+SOURCE_FARM_LABEL",
            "cross_group_selection_rollup": (
                "SET_UNION_OF_OWNED_LABEL_KEYS;SECONDARY_REUSE_GROUPS_NON_ADDITIVE"
            ),
            "shortlist_selection": (
                "MANDATORY_GROUPS_THEN_ROUND_ROBIN_BAND_A_B_C_BY_FROZEN_SORT_KEYS_TO_MAX_40"
            ),
            "no_subjective_composite_score": True,
        },
        "model_impact_scope": model_scope_proof,
        "counts": counts,
        "impact": {},
        "mandatory_high_risk_groups_included": set(MANDATORY_GROUPS).issubset(mandatory),
        "decision_fields_prefilled": False,
        "existing_mapping_authority_changed": False,
        "base_registry_changed": False,
        "model_changed": False,
        "model_retrained": False,
        "backtest_executed": False,
        "v0_7_changed": False,
        "private_row_data_committed": False,
        "private_output": {
            "directory_mode": private_dir_mode,
            "files": output_manifest["files"],
            "artifact_manifest_sha256": output_manifest_sha,
            "policy": "PRIVATE_ROW_LEVEL_BUSINESS_CONFIRMATION_PACKAGE",
        },
        "acceptance": {
            "source_audit_manifest_hash_pass": True,
            "source_manual_confirmation_hash_pass": True,
            "all_263_issues_accounted_for": True,
            "grouping_deterministic": True,
            "mandatory_high_risk_groups_included": set(MANDATORY_GROUPS).issubset(mandatory),
            "selected_group_count_within_20_40": 20 <= len(selected) <= 40,
            "no_duplicate_kg_in_group_impact": True,
            "business_decision_prefilled": False,
            "existing_mapping_authority_changed": False,
            "model_changed": False,
            "model_retrained": False,
            "backtest_executed": False,
            "private_row_data_committed": False,
            "deterministic_replay": "PENDING_SECOND_RUN",
        },
    }


def _public_report(evidence: dict[str, Any]) -> str:
    counts = evidence["counts"]
    impact = evidence["impact"]
    bands = counts["selected_band_counts"]
    lines = [
        "# Cross-season Business Identity Confirmation Package R1",
        "",
        f"Task: `{TASK_ID}`",
        f"Base: `{evidence['base_sha']}`",
        "",
        "## Purpose and boundary",
        "",
        (
            "This package turns the frozen audit's 263 manual issues into exact, "
            "evidence-linked relation groups and a prioritized set of business "
            "questions. It does not decide any mapping."
        ),
        "",
        (
            "The private question pack keeps source names, per-group quantities, "
            "issue IDs, mapping evidence, and decision fields. The repository "
            "contains only aggregate counts, hashes, policy, and sanitized examples."
        ),
        "",
        "## Grouping and selection",
        "",
        f"- Full relation groups: {counts['grouped_business_relation_count']}",
        f"- Selected business questions: {counts['selected_confirmation_group_count']}",
        (
            f"- Selected-band counts: A={bands['BAND_A_CURRENT_MAPPING_RISK']}, "
            f"B={bands['BAND_B_UNRESOLVED_HIGH_VOLUME']}, "
            f"C={bands['BAND_C_CROSS_SEASON_STRUCTURE']}"
        ),
        (
            "- Four required high-risk composite groups are included; exact labels "
            "and answers remain in the private package."
        ),
        (
            "- Grouping uses exact source labels and frozen canonical/candidate "
            "Base identity. No fuzzy matching, name-similarity acceptance, or "
            "subjective score is used."
        ),
        (
            "- Quantities are rolled up by unique (season, source farm label). "
            "Reused-subfarm parent links are non-additive; selected totals use a set union."
        ),
        "",
        "## Coverage and impact",
        "",
        (
            f"- Original issues accounted for: "
            f"{counts['original_manual_confirmation_count']} / "
            f"{counts['original_manual_confirmation_count']}."
        ),
        (
            f"- Selected issues covered: {impact['selected_manual_issue_count_covered']} "
            f"({impact['selected_manual_issue_share']} of the issue list)."
        ),
        (
            f"- Current mapped quantity under review: {impact['selected_mapped_kg_at_risk']} kg "
            f"of {impact['total_mapped_kg_at_risk']} kg identified as reviewable."
        ),
        (
            f"- Unresolved quantity in selected questions: {impact['selected_unresolved_kg']} kg "
            f"({impact['selected_share_of_total_unresolved_kg']} of source-wide unresolved "
            f"quantity {impact['total_unresolved_kg']} kg)."
        ),
        (
            "- Coverage quantities use full-source kg; each selected relation also "
            "shows the separately bounded business-window kg in the private pack."
        ),
        "",
        (
            "The amount summaries are mechanical descriptions of the frozen audit. "
            "They do not imply a mapping is wrong or that unresolved quantity should be assigned."
        ),
        "",
        "## Frozen model-impact check",
        "",
        (
            "For accepted source identities, group-level impact flags are bound at "
            "Base-season grain to the published V0.7 S1 scopes and preserved S3 "
            "Model A/B training and comparison scopes. Unresolved labels are not "
            "represented as if they had entered the models. "
            "Relation names and Base IDs remain private."
        ),
        (
            "S3 used a frozen V0.5 member-mapping hash that differs from the current "
            "R2 authority. Therefore S3 impact flags mean Base-season cohort overlap "
            "only; exact source-label membership in S3 rows is not proven."
        ),
        f"- Replay verification: {evidence['deterministic_replay']['status']}.",
        "",
        "## Example question shape (sanitized)",
        "",
        (
            "> Across two seasons, a source name is accepted in one season, "
            "unresolved in another, and a related member-set change is recorded. "
            "The business question asks whether names refer to the same operation "
            "in each season; it does not recommend an answer."
        ),
        "",
        "## Decision and authority status",
        "",
        (
            "All business decision cells are blank. A YES, NO, PARTIAL, OUT_OF_SCOPE, "
            "or UNKNOWN answer must be applied only by a separately authorized "
            "data-authority correction. This package changes no mapping authority, "
            "Base registry, model, V0.7 evidence, or release artifact."
        ),
        "",
        (
            "Private package manifest SHA256: "
            f"`{evidence['private_output']['artifact_manifest_sha256']}`"
        ),
        "",
    ]
    return "\n".join(lines)


def build_package(
    *,
    input_dir: Path,
    output_dir: Path,
    public_evidence_path: Path,
    public_report_path: Path,
    s1_evidence_path: Path,
    s3_evidence_path: Path,
    s3_artifacts_dir: Path,
    base_sha: str,
    expected_replay_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[1]
    output_resolved = output_dir.resolve()
    if output_resolved == repo_root or repo_root in output_resolved.parents:
        raise ValueError("PRIVATE_OUTPUT_MUST_BE_OUTSIDE_REPOSITORY")
    if output_resolved.exists():
        raise FileExistsError("PRIVATE_OUTPUT_DIRECTORY_ALREADY_EXISTS")
    if expected_replay_manifest_sha256 and (
        len(expected_replay_manifest_sha256) != 64
        or any(character not in "0123456789abcdef" for character in expected_replay_manifest_sha256)
    ):
        raise ValueError("INVALID_EXPECTED_REPLAY_MANIFEST_SHA256")

    loaded, input_manifest = verify_source_inputs(input_dir)
    manual = loaded["manual_business_confirmation.csv"]
    farm_rows = loaded["cross-season-source-farm-label-ledger.csv"]
    identity_rows = loaded["cross-season-source-identity-ledger.csv"]
    anomaly_rows = loaded["cross-season-anomaly-ledger.csv"]
    member_rows = loaded["cross-season-base-member-change-ledger.csv"]
    groups = build_business_relation_groups(
        manual, farm_rows, identity_rows, anomaly_rows, member_rows
    )
    scopes, scope_proof = load_frozen_model_scopes(
        farm_rows, s1_evidence_path, s3_evidence_path, s3_artifacts_dir
    )
    for group in groups:
        attach_model_impact(
            group,
            prior_history_keys=scopes["prior_history_keys"],
            validation_label_keys=scopes["validation_label_keys"],
            ab_comparison_keys=scopes["ab_comparison_keys"],
        )

    farm_by_key = {(row["season"], row["source_farm_label"].strip()): row for row in farm_rows}
    for group in groups:
        group["raw_total_kg"] = sum(group["raw_kg_by_season"].values(), Decimal(0))
        group["reference_raw_kg_by_season"] = {
            season: sum(
                (
                    _amount(farm_by_key[key], "quantity_kg")
                    for key in group["reference_label_keys"]
                    if key[0] == season
                ),
                Decimal(0),
            )
            for season in sorted({key[0] for key in group["reference_label_keys"]})
        }
    selected = select_confirmation_groups(groups)
    if len(selected) > 40 or (
        len(selected) < 20
        and sum(
            g["priority_band"].startswith("BAND_")
            and g["priority_band"] != "BAND_D_SUPPORTING_ONLY"
            for g in groups
        )
        >= 20
    ):
        raise ValueError("SHORTLIST_SIZE_POLICY_VIOLATION")
    aggregate = _aggregate_selected(selected, groups, farm_by_key)
    group_question_number = {
        group["group_id"]: f"Q{index:02d}" for index, group in enumerate(selected, start=1)
    }

    output_resolved.mkdir(mode=0o700, parents=True)
    os.chmod(output_resolved, 0o700)
    group_rows = [
        _group_public_row(group, group_question_number.get(group["group_id"], ""))
        for group in groups
    ]
    selected_rows = [
        _group_public_row(group, group_question_number[group["group_id"]]) for group in selected
    ]
    _write_csv(
        output_resolved / "business-identity-confirmation-grouped.csv", GROUP_FIELDS, group_rows
    )
    _write_csv(
        output_resolved / "business-identity-confirmation-priority.csv",
        PRIORITY_FIELDS,
        selected_rows,
    )
    decision_rows = [
        {
            "group_id": group["group_id"],
            "question_number": group_question_number[group["group_id"]],
            "decision_2023_2024": "",
            "decision_2024_2025": "",
            "decision_2025_2026": "",
            "correct_base_if_no": "",
            "effective_date_or_split_rule_if_partial": "",
            "business_comment": "",
            "confirmed_by": "",
            "confirmation_date": "",
        }
        for group in selected
    ]
    _write_csv(
        output_resolved / "business-identity-confirmation-decision-template.csv",
        DECISION_FIELDS,
        decision_rows,
    )
    question_sections = [
        "# 跨产季基地身份业务确认问题",
        "",
        (
            "本文件只用于业务确认，不会自动更改历史映射。请按产季分别回答；无法确认可填 UNKNOWN。"
            "公斤数按农场名称唯一去重，分场复用关系的父级数量仅作参考，不加入确认包总量。"
        ),
        "",
    ]
    question_sections.extend(
        _question_text(group, group_question_number[group["group_id"]]) for group in selected
    )
    questions_path = output_resolved / "business-identity-confirmation-questions.md"
    with questions_path.open("x", encoding="utf-8") as stream:
        stream.write("\n\n".join(question_sections) + "\n")
    os.chmod(questions_path, 0o600)

    generated_files = [
        "business-identity-confirmation-grouped.csv",
        "business-identity-confirmation-priority.csv",
        "business-identity-confirmation-questions.md",
        "business-identity-confirmation-decision-template.csv",
    ]
    file_entries: dict[str, Any] = {}
    for name in generated_files:
        path = output_resolved / name
        rows = (
            sum(1 for _ in path.open(encoding="utf-8-sig")) - 1
            if path.suffix == ".csv"
            else len(selected)
        )
        file_entries[name] = {
            "sha256": sha256_file(path),
            "row_count": rows,
            "mode": stat.S_IMODE(path.stat().st_mode).__format__("04o"),
        }
    output_manifest = {
        "policy": "PRIVATE_ROW_LEVEL_BUSINESS_CONFIRMATION_PACKAGE",
        "directory_mode": stat.S_IMODE(output_resolved.stat().st_mode).__format__("04o"),
        "files": file_entries,
    }
    private_manifest_path = output_resolved / "artifact-manifest.json"
    _write_json(private_manifest_path, output_manifest)
    output_manifest_sha = sha256_file(private_manifest_path)
    if (
        expected_replay_manifest_sha256 is not None
        and output_manifest_sha != expected_replay_manifest_sha256
    ):
        raise ValueError("DETERMINISTIC_REPLAY_MANIFEST_HASH_MISMATCH")
    public_input_hashes = input_manifest["verified_input_hashes"]
    public = _public_evidence(
        base_sha=base_sha,
        input_hashes=public_input_hashes,
        source_manifest_sha=SOURCE_MANIFEST_SHA256,
        group_rows=groups,
        selected_rows=selected,
        model_scope_proof=scope_proof,
        output_manifest=output_manifest,
        output_manifest_sha=output_manifest_sha,
        private_dir_mode="0700",
    )
    public["counts"]["selected_manual_issue_count_covered"] = aggregate[
        "selected_manual_issue_count_covered"
    ]
    public["counts"]["all_263_issues_accounted_for"] = (
        len(set().union(*(g["covered_issue_ids"] for g in groups))) == 263
    )
    public["impact"] = {
        "total_mapped_kg_at_risk": decimal_text(aggregate["total_mapped_kg_at_risk"]),
        "selected_mapped_kg_at_risk": decimal_text(aggregate["selected_mapped_kg_at_risk"]),
        "selected_share_of_mapped_kg_at_risk": decimal_text(
            aggregate["selected_share_of_mapped_kg_at_risk"]
        ),
        "total_unresolved_kg": decimal_text(aggregate["total_unresolved_kg"]),
        "selected_unresolved_kg": decimal_text(aggregate["selected_unresolved_kg"]),
        "selected_share_of_total_unresolved_kg": decimal_text(
            aggregate["selected_share_of_total_unresolved_kg"]
        ),
        "selected_manual_issue_share": decimal_text(aggregate["selected_manual_issue_share"]),
        "selected_manual_issue_count_covered": aggregate["selected_manual_issue_count_covered"],
        "coverage_kg_basis": "FULL_SOURCE_QUANTITY;BUSINESS_WINDOW_QUANTITY_IS_SEPARATELY_REPORTED",
    }
    public["acceptance"]["all_263_issues_accounted_for"] = public["counts"][
        "all_263_issues_accounted_for"
    ]
    public["acceptance"]["selected_group_count_within_20_40"] = 20 <= len(selected) <= 40
    if expected_replay_manifest_sha256 is None:
        public["deterministic_replay"] = {
            "status": "PENDING_SECOND_RUN",
            "first_run_artifact_manifest_sha256": output_manifest_sha,
        }
    else:
        public["acceptance"]["deterministic_replay"] = "PASS"
        public["deterministic_replay"] = {
            "status": "PASS",
            "first_run_artifact_manifest_sha256": expected_replay_manifest_sha256,
            "replay_artifact_manifest_sha256": output_manifest_sha,
            "artifact_manifest_hash_equal": True,
        }
    band_sorted = {
        "BAND_A_CURRENT_MAPPING_RISK": sorted(
            (group for group in groups if group["priority_band"] == "BAND_A_CURRENT_MAPPING_RISK"),
            key=lambda group: (
                -group["mapped_kg_at_risk"],
                -len(group["seasons"]),
                group["group_id"],
            ),
        ),
        "BAND_B_UNRESOLVED_HIGH_VOLUME": sorted(
            (
                group
                for group in groups
                if group["priority_band"] == "BAND_B_UNRESOLVED_HIGH_VOLUME"
            ),
            key=lambda group: (
                -group["unresolved_kg_potentially_recoverable"],
                -len(group["seasons"]),
                group["group_id"],
            ),
        ),
    }
    selected_group_ids = {group["group_id"] for group in selected}
    public["selection"] = {
        "selected_issue_count": aggregate["selected_manual_issue_count_covered"],
        "selected_issue_share": decimal_text(aggregate["selected_manual_issue_share"]),
        "selected_band_counts": public["counts"]["selected_band_counts"],
        "top_unresolved_group_captured": bool(band_sorted["BAND_B_UNRESOLVED_HIGH_VOLUME"])
        and band_sorted["BAND_B_UNRESOLVED_HIGH_VOLUME"][0]["group_id"] in selected_group_ids,
        "top_current_mapping_risk_group_captured": bool(band_sorted["BAND_A_CURRENT_MAPPING_RISK"])
        and band_sorted["BAND_A_CURRENT_MAPPING_RISK"][0]["group_id"] in selected_group_ids,
    }
    public_evidence_path.parent.mkdir(parents=True, exist_ok=True)
    public_report_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(public_evidence_path, public)
    os.chmod(public_evidence_path, 0o644)
    public_report_path.write_text(_public_report(public), encoding="utf-8")
    return public


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--s1-evidence",
        type=Path,
        default=Path("docs/v0-7/evidence/s1-formal-multi-season-baseline-validation.json"),
    )
    parser.add_argument(
        "--s3-evidence",
        type=Path,
        default=Path("docs/v0-7/evidence/s3-weather-aware-model-training-and-oot-backtest.json"),
    )
    parser.add_argument("--s3-artifacts-dir", type=Path, required=True)
    parser.add_argument(
        "--public-evidence",
        type=Path,
        default=Path(
            "docs/data-audit/evidence/cross-season-business-identity-confirmation-package-r1.json"
        ),
    )
    parser.add_argument(
        "--public-report",
        type=Path,
        default=Path("docs/data-audit/cross-season-business-identity-confirmation-package-r1.md"),
    )
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--expected-replay-manifest-sha256")
    args = parser.parse_args()
    evidence = build_package(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        public_evidence_path=args.public_evidence,
        public_report_path=args.public_report,
        s1_evidence_path=args.s1_evidence,
        s3_evidence_path=args.s3_evidence,
        s3_artifacts_dir=args.s3_artifacts_dir,
        base_sha=args.base_sha,
        expected_replay_manifest_sha256=args.expected_replay_manifest_sha256,
    )
    print(
        json.dumps(
            {
                "task_id": evidence["task_id"],
                "group_count": evidence["counts"]["grouped_business_relation_count"],
                "selected_count": evidence["counts"]["selected_confirmation_group_count"],
                "selected_issue_count": evidence["counts"]["selected_manual_issue_count_covered"],
                "artifact_manifest_sha256": evidence["private_output"]["artifact_manifest_sha256"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
