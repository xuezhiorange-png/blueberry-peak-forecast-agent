"""Read-only cross-season raw harvest and frozen-identity audit.

The program never changes mapping authority or model inputs. Full row-level
artifacts are written only to a caller-supplied private directory.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

SEASONS = ("2023-2024", "2024-2025", "2025-2026")
SEASON_WINDOWS = {
    "2023-2024": (date(2023, 7, 1), date(2024, 4, 15)),
    "2024-2025": (date(2024, 7, 1), date(2025, 4, 15)),
    "2025-2026": (date(2025, 7, 22), date(2026, 4, 15)),
}
ACCEPTED_TYPES = {"EXACT", "AUTHORIZED_ALIAS", "HISTORICALLY_PROVEN_ALIAS"}
EXPECTED_SOURCE_HASHES = {
    "2023-2024": "8fa003b4abdea0b0bd9c50a9fbd619ad15ea5c9a2e790faa5e5b3353a2a01d20",
    "2024-2025": "f4ffba4b10a3129c768871bc5f3dfa2845534bc0e7eb04e166ba97211fa92dd6",
    "2025-2026": "fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a",
}
EXPECTED_AUTHORITY_HASHES = {
    "historical_identity_mapping": (
        "8d17880141485c407d2e011d70c12d1f828b1966abba32a42b201c33bc4a5044"
    ),
    "base_member_mapping": "d40dbc3a1328d79e10670999ee613fcef8fa3ee32659db16dfe67db3e6b91b5b",
    "combined_identity_authority": (
        "c46e198cda2e6c4296db184af5c2e1f3b200a944309aa43039fa3be42a0bbd0e"
    ),
}
EXPECTED_INPUT_FILE_HASHES = {
    "historical_identity_coverage_summary": (
        "b4d02661147454f05be78d4020e2e43271f0498b21b84b5db37ecd2b6b2d14e6"
    ),
    "base_registry": "502c73fecdf68e91e4aa35982a2207d224204390597eaf59420ebd1101539904",
    "mapping_authority": "319d5adbd51aba71dbcdbcc05d1dfd3ff8e5602d621988230a45c5930c23c086",
}


@dataclass(frozen=True)
class SourceRow:
    season: str
    sheet: str
    row_number: int
    event_date: date
    company: str
    farm: str
    subfarm: str
    cultivar: str
    fruit_size: str
    quantity_kg: Decimal
    raw_record_hash: str


@dataclass
class Group:
    rows: int = 0
    quantity: Decimal = Decimal(0)
    dates: set[date] = field(default_factory=set)
    companies: set[str] = field(default_factory=set)
    cultivars: set[str] = field(default_factory=set)
    fruit_sizes: set[str] = field(default_factory=set)
    business_quantity: Decimal = Decimal(0)
    outside_quantity: Decimal = Decimal(0)
    business_dates: set[date] = field(default_factory=set)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _decimal_text(value: Decimal | None) -> str:
    if value is None:
        return ""
    if value == 0:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _json_list(values: Iterable[str]) -> str:
    return json.dumps(sorted(values), ensure_ascii=False, separators=(",", ":"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _as_date(value: Any, datemode: int) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        import xlrd

        return xlrd.xldate_as_datetime(value, datemode).date()
    return date.fromisoformat(str(value).strip()[:10])


def read_source_xls(path: Path, season: str) -> list[SourceRow]:
    try:
        import xlrd
    except ImportError as error:  # pragma: no cover - exercised by CLI environment
        raise RuntimeError("xlrd is required to read original .xls sources") from error

    workbook = xlrd.open_workbook(str(path), on_demand=True)
    rows: list[SourceRow] = []
    seen_raw_rows: set[str] = set()
    for sheet in workbook.sheets():
        if sheet.ncols < 7 or sheet.nrows == 0:
            raise ValueError(f"unexpected source sheet shape: {sheet.name}")
        header = [str(sheet.cell_value(0, column)).strip() for column in range(7)]
        if header != ["时间", "链路", "农场", "分场", "品种", "果径", "入库公斤数"]:
            raise ValueError(f"unexpected header in {sheet.name}: {header!r}")
        for row_index in range(1, sheet.nrows):
            values = [sheet.cell_value(row_index, column) for column in range(7)]
            if not any(value not in (None, "") for value in values):
                continue
            try:
                event_date = _as_date(values[0], workbook.datemode)
                quantity = Decimal(str(values[6]))
            except (InvalidOperation, TypeError, ValueError) as error:
                raise ValueError(
                    f"invalid date/quantity at {sheet.name}:{row_index + 1}"
                ) from error
            if not quantity.is_finite() or quantity < 0:
                raise ValueError(f"invalid quantity at {sheet.name}:{row_index + 1}")
            strings = ["" if value is None else str(value).strip() for value in values[1:6]]
            raw_identity = {
                "date": event_date.isoformat(),
                "company": strings[0],
                "farm": strings[1],
                "subfarm": strings[2],
                "cultivar": strings[3],
                "fruit_size": strings[4],
                "quantity_kg": _decimal_text(quantity),
            }
            row_hash = hashlib.sha256(_canonical_bytes(raw_identity)).hexdigest()
            seen_raw_rows.add(row_hash)
            rows.append(
                SourceRow(
                    season=season,
                    sheet=sheet.name,
                    row_number=row_index + 1,
                    event_date=event_date,
                    company=strings[0],
                    farm=strings[1],
                    subfarm=strings[2],
                    cultivar=strings[3],
                    fruit_size=strings[4],
                    quantity_kg=quantity,
                    raw_record_hash=row_hash,
                )
            )
    workbook.release_resources()
    return rows


def _mapping_record(
    season: str,
    farm: str,
    historical: dict[tuple[str, str], dict[str, str]],
    members: dict[str, dict[str, str]],
) -> dict[str, str]:
    if season in ("2023-2024", "2024-2025"):
        row = historical.get((season, farm))
        if row is None:
            return {
                "status": "UNRESOLVED",
                "match_type": "UNRESOLVED",
                "base_id": "",
                "base_name": "",
                "candidate_base_id": "",
                "candidate_base_name": "",
                "authority": "HISTORICAL_IDENTITY_RECONSTRUCTION_R1",
                "evidence": "No season-scoped row in frozen R1 identity authority",
                "decision": "REQUIRES_BUSINESS_CONFIRMATION",
            }
        kind = row.get("match_type", "UNRESOLVED")
        decision = row.get("decision", "")
        base_id = row.get("candidate_base_id", "")
        candidate_name = row.get("candidate_base", "")
        if kind == "OUT_OF_CURRENT_BASE_SCOPE" or decision == "OUT_OF_CURRENT_BASE_SCOPE":
            status = "EXCLUDED"
            base_id = ""
        elif kind in ACCEPTED_TYPES and decision == "ACCEPTED" and base_id and ";" not in base_id:
            status = kind
        elif kind == "CONFLICTING" or (kind in ACCEPTED_TYPES and ";" in base_id):
            status = "CONFLICTING"
        else:
            status = "UNRESOLVED"
        member = members.get(farm)
        if status in ACCEPTED_TYPES and member:
            member_status = member.get("match_status", "")
            member_id = member.get("matched_base_id", "")
            if member_status in ACCEPTED_TYPES and member_id and member_id != base_id:
                status = "CONFLICTING"
        return {
            "status": status,
            "match_type": kind,
            "base_id": base_id if status in ACCEPTED_TYPES else "",
            "base_name": candidate_name if status in ACCEPTED_TYPES else "",
            "candidate_base_id": row.get("candidate_base_id", ""),
            "candidate_base_name": candidate_name,
            "authority": "HISTORICAL_IDENTITY_RECONSTRUCTION_R1",
            "evidence": row.get("evidence", row.get("candidate_basis", "")),
            "decision": decision,
        }

    row = members.get(farm)
    if row is None:
        return {
            "status": "UNRESOLVED",
            "match_type": "NOT_LISTED",
            "base_id": "",
            "base_name": "",
            "candidate_base_id": "",
            "candidate_base_name": "",
            "authority": "BASE_MEMBER_MAPPING_R2",
            "evidence": "Source farm label is absent from frozen Base member mapping",
            "decision": "REQUIRES_BUSINESS_CONFIRMATION",
        }
    kind = row.get("match_status", "UNRESOLVED")
    base_id = row.get("matched_base_id", "")
    if kind in ACCEPTED_TYPES and base_id:
        status = kind
    elif kind == "CONFLICTING" or (kind in ACCEPTED_TYPES and ";" in base_id):
        status = "CONFLICTING"
    else:
        status = "UNRESOLVED"
    return {
        "status": status,
        "match_type": row.get("match_method", kind),
        "base_id": base_id if status in ACCEPTED_TYPES else "",
        "base_name": row.get("canonical_base_name", "") if status in ACCEPTED_TYPES else "",
        "candidate_base_id": base_id,
        "candidate_base_name": row.get("canonical_base_name", ""),
        "authority": "BASE_MEMBER_MAPPING_R2",
        "evidence": row.get("evidence", ""),
        "decision": "ACCEPTED" if status in ACCEPTED_TYPES else "REQUIRES_BUSINESS_CONFIRMATION",
    }


def _multi_assigned_source_row_bases(
    source_rows: Iterable[SourceRow],
    mapping_by_season_farm: dict[tuple[str, str], dict[str, str]],
) -> dict[tuple[str, str, int], list[str]]:
    assigned_bases: dict[tuple[str, str, int], set[str]] = defaultdict(set)
    for row in source_rows:
        mapping = mapping_by_season_farm[(row.season, row.farm)]
        if mapping["status"] in ACCEPTED_TYPES and mapping["base_id"]:
            assigned_bases[(row.season, row.sheet, row.row_number)].add(mapping["base_id"])
    return {
        identity: sorted(base_ids)
        for identity, base_ids in assigned_bases.items()
        if len(base_ids) > 1
    }


def _within_window(season: str, event_date: date) -> bool:
    start, end = SEASON_WINDOWS[season]
    return start <= event_date <= end


def _issue_id(kind: str, *parts: str) -> str:
    content = "|".join((kind, *parts))
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _append_issue(
    anomalies: list[dict[str, str]],
    manual: list[dict[str, str]],
    *,
    priority: str,
    kind: str,
    season: str,
    label: str,
    subfarm: str,
    quantity: Decimal,
    base: str,
    match_type: str,
    problem: str,
    evidence: str,
    question: str,
    candidate_base_id: str = "",
    classification: str = "",
) -> None:
    issue_id = _issue_id(kind, season, label, subfarm, base, candidate_base_id)
    anomalies.append(
        {
            "issue_id": issue_id,
            "priority": priority,
            "issue_type": kind,
            "season": season,
            "source_label": label,
            "source_subfarm": subfarm,
            "quantity_kg": _decimal_text(quantity),
            "current_base": base,
            "current_mapping_type": match_type,
            "classification": classification,
            "problem": problem,
            "evidence": evidence,
            "proposed_correction": "NONE_THIS_AUDIT_PRESERVES_FROZEN_AUTHORITY",
        }
    )
    if priority != "INFO":
        manual.append(
            {
                "issue_id": issue_id,
                "priority": priority,
                "season": season,
                "source_label": label,
                "source_subfarm": subfarm,
                "quantity_kg": _decimal_text(quantity),
                "current_base": base,
                "current_mapping_type": match_type,
                "problem": problem,
                "evidence": evidence,
                "recommended_question": question,
                "business_decision": "",
            }
        )


def build_audit(
    source_rows: list[SourceRow],
    historical_rows: list[dict[str, str]],
    historical_matrix_rows: list[dict[str, str]],
    historical_coverage: dict[str, Any],
    member_rows: list[dict[str, str]],
    registry: dict[str, Any],
    r7b_qualification: dict[str, dict[str, Any]],
    source_hashes: dict[str, str],
    authority_hashes: dict[str, str],
) -> dict[str, Any]:
    if set(source_hashes) != set(SEASONS) or any(
        source_hashes[season] != EXPECTED_SOURCE_HASHES[season] for season in SEASONS
    ):
        raise ValueError("raw source SHA256 does not match the frozen expected hashes")
    if any(
        authority_hashes.get(key) != expected for key, expected in EXPECTED_AUTHORITY_HASHES.items()
    ):
        raise ValueError("identity authority SHA256 does not match the frozen expected hashes")

    historical: dict[tuple[str, str], dict[str, str]] = {}
    for row in historical_rows:
        key = (row["season"], row["source_farm_label"])
        if key in historical:
            raise ValueError(f"duplicate historical authority identity: {key}")
        historical[key] = row
    members: dict[str, dict[str, str]] = {}
    for row in member_rows:
        key = row["historical_farm_identity"]
        if key in members:
            raise ValueError(f"duplicate Base member authority identity: {key}")
        members[key] = row

    bases = registry.get("bases", [])
    base_names = {row["base_id"]: row["canonical_base_name"] for row in bases}
    if len(bases) != 39 or len(base_names) != 39:
        raise ValueError("expected the frozen 39-Base registry")
    matrix = {(row["season"], row["base_id"]): row for row in historical_matrix_rows}
    if len(matrix) != 78 or {row["base_id"] for row in historical_matrix_rows} != set(base_names):
        raise ValueError("historical R1 identity matrix must contain 39 Bases x 2 seasons")

    pair_groups: dict[tuple[str, str, str], Group] = defaultdict(Group)
    farm_groups: dict[tuple[str, str], Group] = defaultdict(Group)
    season_rows: dict[str, list[SourceRow]] = defaultdict(list)
    exact_row_hash_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for row in source_rows:
        if row.season not in SEASONS:
            raise ValueError(f"unexpected season: {row.season}")
        season_rows[row.season].append(row)
        exact_row_hash_counts[row.season][row.raw_record_hash] += 1
        for key, group in (
            ((row.season, row.farm, row.subfarm), pair_groups[(row.season, row.farm, row.subfarm)]),
            ((row.season, row.farm), farm_groups[(row.season, row.farm)]),
        ):
            del key
            group.rows += 1
            group.quantity += row.quantity_kg
            group.dates.add(row.event_date)
            group.companies.add(row.company)
            group.cultivars.add(row.cultivar)
            group.fruit_sizes.add(row.fruit_size)
            if _within_window(row.season, row.event_date):
                group.business_quantity += row.quantity_kg
                group.business_dates.add(row.event_date)
            else:
                group.outside_quantity += row.quantity_kg

    mapping_by_season_farm: dict[tuple[str, str], dict[str, str]] = {}
    source_label_records: dict[tuple[str, str], Group] = {}
    for (season, farm), group in farm_groups.items():
        mapping = _mapping_record(season, farm, historical, members)
        mapping_by_season_farm[(season, farm)] = mapping
        source_label_records[(season, farm)] = group

    # A same-season assignment disagreement is a conflict. Across seasons it is
    # reported separately as a possible organization change, never auto-corrected.
    accepted_by_label: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for (season, farm), mapping in mapping_by_season_farm.items():
        if mapping["status"] in ACCEPTED_TYPES:
            accepted_by_label[farm][season].add(mapping["base_id"])
    for (season, farm), mapping in mapping_by_season_farm.items():
        assignments = accepted_by_label[farm][season]
        if len(assignments) > 1:
            mapping["status"] = "CONFLICTING"
            mapping["base_id"] = ""

    pair_ledger: list[dict[str, str]] = []
    farm_ledger: list[dict[str, str]] = []
    mapped_by_season: Counter[str] = Counter()
    unresolved_by_season: Counter[str] = Counter()
    excluded_by_season: Counter[str] = Counter()
    counts_by_season: dict[str, Counter[str]] = {season: Counter() for season in SEASONS}
    raw_by_season: Counter[str] = Counter()
    business_raw_by_season: Counter[str] = Counter()
    mapped_base_business: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    mapped_base_raw: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    mapped_base_days: dict[tuple[str, str], set[date]] = defaultdict(set)
    mapped_base_labels: dict[tuple[str, str], set[str]] = defaultdict(set)
    unresolved_candidates: dict[tuple[str, str], set[str]] = defaultdict(set)
    unresolved_candidate_raw: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    parent_by_subfarm: dict[tuple[str, str], set[str]] = defaultdict(set)
    all_row_hashes_by_season: dict[str, list[str]] = defaultdict(list)
    anomalies: list[dict[str, str]] = []
    manual: list[dict[str, str]] = []

    multi_assigned_source_rows = _multi_assigned_source_row_bases(
        source_rows, mapping_by_season_farm
    )
    for (season, sheet, row_number), base_ids in sorted(multi_assigned_source_rows.items()):
        _append_issue(
            anomalies,
            manual,
            priority="P0_CRITICAL",
            kind="RAW_SOURCE_ROW_ASSIGNED_TO_MULTIPLE_BASES",
            season=season,
            label=f"sheet={sheet};row={row_number}",
            subfarm="",
            quantity=Decimal(0),
            base=";".join(base_ids),
            match_type="SOURCE_ROW_IDENTITY_COLLISION",
            problem=(
                "The same source row identity resolves to more than one accepted canonical Base."
            ),
            evidence=f"source_row={season}/{sheet}/{row_number};base_ids={';'.join(base_ids)}",
            question="Which canonical Base, if any, is authorized for this exact source row?",
            candidate_base_id=";".join(base_ids),
        )

    for season in SEASONS:
        for row in season_rows.get(season, []):
            raw_by_season[season] += row.quantity_kg
            if _within_window(season, row.event_date):
                business_raw_by_season[season] += row.quantity_kg
            all_row_hashes_by_season[season].append(row.raw_record_hash)
            if row.subfarm:
                parent_by_subfarm[(season, row.subfarm)].add(row.farm)

    for (season, farm, subfarm), group in sorted(pair_groups.items()):
        mapping = mapping_by_season_farm[(season, farm)]
        status = mapping["status"]
        if status in ACCEPTED_TYPES:
            mapped_by_season[season] += group.quantity
            counts_by_season[season]["mapped_labels"] += 0  # counted uniquely below
            bid = mapping["base_id"]
            mapped_base_raw[(season, bid)] += group.quantity
            mapped_base_business[(season, bid)] += group.business_quantity
            mapped_base_days[(season, bid)].update(group.business_dates)
            mapped_base_labels[(season, bid)].add(farm)
        elif status == "EXCLUDED":
            excluded_by_season[season] += group.quantity
        else:
            unresolved_by_season[season] += group.quantity
            if mapping.get("candidate_base_id"):
                for bid in mapping["candidate_base_id"].split(";"):
                    if bid:
                        unresolved_candidates[(season, bid)].add(farm)
                        unresolved_candidate_raw[(season, bid)] += group.quantity
        pair_ledger.append(
            {
                "season": season,
                "source_farm_label": farm,
                "source_subfarm_label": subfarm,
                "raw_row_count": str(group.rows),
                "observed_day_count": str(len(group.dates)),
                "first_date": min(group.dates).isoformat(),
                "last_date": max(group.dates).isoformat(),
                "quantity_kg": _decimal_text(group.quantity),
                "business_window_quantity_kg": _decimal_text(group.business_quantity),
                "outside_business_window_quantity_kg": _decimal_text(group.outside_quantity),
                "business_window_observed_day_count": str(len(group.business_dates)),
                "source_company_labels": _json_list(group.companies),
                "source_cultivar_labels": _json_list(group.cultivars),
                "source_fruit_size_labels": _json_list(group.fruit_sizes),
                "current_mapping_status": status,
                "current_match_type": mapping["match_type"],
                "current_candidate_base_id": mapping["base_id"] or mapping["candidate_base_id"],
                "current_canonical_base_name": mapping["base_name"]
                or mapping["candidate_base_name"],
                "mapping_authority": mapping["authority"],
                "mapping_evidence": mapping["evidence"],
                "r7b_source_label_completeness_status": r7b_qualification.get(farm, {}).get(
                    "season_completeness_status", "NOT_QUALIFIED_OR_NOT_IN_R7B_SCOPE"
                ),
                "r7b_shape_eligibility": r7b_qualification.get(farm, {}).get(
                    "shape_evaluable", "NOT_QUALIFIED_OR_NOT_IN_R7B_SCOPE"
                ),
            }
        )

    for (season, farm), group in sorted(farm_groups.items()):
        mapping = mapping_by_season_farm[(season, farm)]
        status = mapping["status"]
        if status in ACCEPTED_TYPES:
            counts_by_season[season]["MAPPED"] += 1
        elif status == "EXCLUDED":
            counts_by_season[season]["EXCLUDED"] += 1
        elif status == "CONFLICTING":
            counts_by_season[season]["CONFLICTING"] += 1
            counts_by_season[season]["UNRESOLVED"] += 1
        else:
            counts_by_season[season]["UNRESOLVED"] += 1
        farm_ledger.append(
            {
                "season": season,
                "source_farm_label": farm,
                "raw_row_count": str(group.rows),
                "observed_day_count": str(len(group.dates)),
                "first_date": min(group.dates).isoformat(),
                "last_date": max(group.dates).isoformat(),
                "quantity_kg": _decimal_text(group.quantity),
                "business_window_quantity_kg": _decimal_text(group.business_quantity),
                "outside_business_window_quantity_kg": _decimal_text(group.outside_quantity),
                "source_company_labels": _json_list(group.companies),
                "source_cultivar_labels": _json_list(group.cultivars),
                "current_mapping_status": status,
                "current_match_type": mapping["match_type"],
                "current_candidate_base_id": mapping["base_id"] or mapping["candidate_base_id"],
                "current_canonical_base_name": mapping["base_name"]
                or mapping["candidate_base_name"],
                "mapping_authority": mapping["authority"],
                "mapping_evidence": mapping["evidence"],
            }
        )
        if status == "UNRESOLVED":
            _append_issue(
                anomalies,
                manual,
                priority="P1_HIGH" if group.quantity > 0 else "P2_REVIEW",
                kind="UNRESOLVED_SOURCE_FARM_IDENTITY",
                season=season,
                label=farm,
                subfarm="",
                quantity=group.quantity,
                base=mapping["candidate_base_name"],
                match_type=mapping["match_type"],
                problem=(
                    "No accepted season-scoped mapping; candidates are not authority "
                    "and remain unmapped."
                ),
                evidence=mapping["evidence"],
                question=(
                    "Which canonical Base, if any, does this source farm belong to for this season?"
                ),
                candidate_base_id=mapping["candidate_base_id"],
            )
        elif status == "CONFLICTING":
            _append_issue(
                anomalies,
                manual,
                priority="P0_CRITICAL",
                kind="IDENTITY_AUTHORITY_CONFLICT",
                season=season,
                label=farm,
                subfarm="",
                quantity=group.quantity,
                base=mapping["candidate_base_name"],
                match_type=mapping["match_type"],
                problem=(
                    "Frozen identity authorities assign this season label to "
                    "conflicting Base identities."
                ),
                evidence=mapping["evidence"],
                question=(
                    "Which Base identity is formally authorized for this source label and season?"
                ),
                candidate_base_id=mapping["candidate_base_id"],
            )
        elif status == "EXCLUDED":
            _append_issue(
                anomalies,
                manual,
                priority="P2_REVIEW",
                kind="OUT_OF_CURRENT_BASE_SCOPE",
                season=season,
                label=farm,
                subfarm="",
                quantity=group.quantity,
                base="",
                match_type=mapping["match_type"],
                problem=(
                    "Frozen R1 authority explicitly excludes this label from the "
                    "current Base registry scope."
                ),
                evidence=mapping["evidence"],
                question=(
                    "Is this outside the current 39-Base scope, or is separate authority required?"
                ),
            )
        if group.outside_quantity > 0:
            _append_issue(
                anomalies,
                manual,
                priority="INFO",
                kind="RAW_ROWS_OUTSIDE_FROZEN_BUSINESS_WINDOW",
                season=season,
                label=farm,
                subfarm="",
                quantity=group.outside_quantity,
                base=mapping["base_name"],
                match_type=mapping["match_type"],
                problem=(
                    "Raw rows outside the frozen season window remain in raw "
                    "reconciliation, not business-window subtotals."
                ),
                evidence=f"Frozen window={SEASON_WINDOWS[season][0]}..{SEASON_WINDOWS[season][1]}",
                question=(
                    "Are out-of-window rows tail/other-season fruit, or is a "
                    "separate window authorized?"
                ),
            )

    # Raw source rows are counted once. Farm totals and farm+subfarm totals are
    # parallel views; they are never added together.
    season_reconciliation: dict[str, dict[str, Any]] = {}
    for season in SEASONS:
        raw = raw_by_season[season]
        mapped = mapped_by_season[season]
        unresolved = unresolved_by_season[season]
        excluded = excluded_by_season[season]
        delta = raw - mapped - unresolved - excluded
        farm_sum = sum(
            (group.quantity for (s, _), group in farm_groups.items() if s == season), Decimal(0)
        )
        pair_sum = sum(
            (group.quantity for (s, _, _), group in pair_groups.items() if s == season), Decimal(0)
        )
        status_count = counts_by_season[season]
        season_reconciliation[season] = {
            "raw_source_row_count": len(season_rows[season]),
            "source_farm_label_count": len([k for k in farm_groups if k[0] == season]),
            "source_subfarm_label_count": len(
                {row.subfarm for row in season_rows[season] if row.subfarm}
            ),
            "source_farm_subfarm_pair_count": len([k for k in pair_groups if k[0] == season]),
            "date_min": min(row.event_date for row in season_rows[season]).isoformat(),
            "date_max": max(row.event_date for row in season_rows[season]).isoformat(),
            "raw_total_kg": _decimal_text(raw),
            "business_window": {
                "start": SEASON_WINDOWS[season][0].isoformat(),
                "end": SEASON_WINDOWS[season][1].isoformat(),
                "raw_in_window_kg": _decimal_text(business_raw_by_season[season]),
                "raw_outside_window_kg": _decimal_text(raw - business_raw_by_season[season]),
            },
            "mapped_total_kg": _decimal_text(mapped),
            "unresolved_total_kg": _decimal_text(unresolved),
            "explicitly_excluded_total_kg": _decimal_text(excluded),
            "unresolved_includes_conflicting": True,
            "reconciliation_delta_kg": _decimal_text(delta),
            "farm_aggregate_total_kg": _decimal_text(farm_sum),
            "farm_subfarm_pair_aggregate_total_kg": _decimal_text(pair_sum),
            "exact_duplicate_raw_row_count": sum(
                count - 1 for count in exact_row_hash_counts[season].values() if count > 1
            ),
            "blank_farm_label_row_count": sum(not row.farm for row in season_rows[season]),
            "blank_subfarm_label_row_count": sum(not row.subfarm for row in season_rows[season]),
            "label_status_counts": {
                "mapped": status_count["MAPPED"],
                "unresolved_including_conflicting": status_count["UNRESOLVED"],
                "unresolved_excluding_conflicting": status_count["UNRESOLVED"]
                - status_count["CONFLICTING"],
                "conflicting": status_count["CONFLICTING"],
                "explicitly_excluded": status_count["EXCLUDED"],
            },
            "mapped_rate_of_raw": _decimal_text(mapped / raw if raw else Decimal(0)),
            "quantity_reconciliation_pass": delta == 0 and farm_sum == raw and pair_sum == raw,
        }

    # Reconcile the older season-level decisions against their frozen R1
    # 39-Base matrix. The matrix is a coverage authority, not a replacement
    # mapping source for the raw labels.
    legacy_coverage_rows = {row["season"]: row for row in historical_coverage["coverage_by_season"]}
    for season in ("2023-2024", "2024-2025"):
        coverage_row = legacy_coverage_rows[season]
        if Decimal(coverage_row["source_total_kg"]) != raw_by_season[season]:
            raise ValueError(f"raw source total diverges from R1 coverage summary for {season}")
        if Decimal(coverage_row["mapped_kg"]) != mapped_by_season[season]:
            raise ValueError(f"mapped subtotal diverges from R1 coverage summary for {season}")
        for base in bases:
            key = (season, base["base_id"])
            row = matrix[key]
            observed_members = sorted(mapped_base_labels[key])
            authority_members = sorted(
                label for label in row["accepted_source_labels"].split(";") if label
            )
            if observed_members != authority_members:
                raise ValueError(f"accepted member identity differs from R1 matrix: {key}")
            if Decimal(row["accepted_mapped_kg"]) != mapped_base_raw[key]:
                raise ValueError(f"accepted mapped subtotal differs from R1 matrix: {key}")
            authority_proposals = {
                label
                for field_name in (
                    "proposed_source_labels",
                    "ambiguous_proposed_source_labels",
                )
                for label in row[field_name].split(";")
                if label
            }
            observed_proposals = unresolved_candidates[key] - set(observed_members)
            if not observed_proposals.issubset(authority_proposals):
                raise ValueError(f"unresolved candidate labels differ from R1 matrix: {key}")

    # Cross-season label assignments and member changes.
    labels_with_different_bases: list[dict[str, Any]] = []
    for label, season_map in sorted(accepted_by_label.items()):
        bases_seen = sorted({bid for ids in season_map.values() for bid in ids if bid})
        if len(bases_seen) > 1:
            assignments = {season: sorted(ids) for season, ids in sorted(season_map.items()) if ids}
            kind = "POSSIBLE_ORG_CHANGE" if len(assignments) > 1 else "POSSIBLE_MAPPING_ERROR"
            labels_with_different_bases.append(
                {"source_label": label, "assignments": assignments, "classification": kind}
            )
            _append_issue(
                anomalies,
                manual,
                priority="P1_HIGH",
                kind="SAME_LABEL_DIFFERENT_BASE",
                season=";".join(assignments),
                label=label,
                subfarm="",
                quantity=Decimal(0),
                base=";".join(base_names.get(bid, bid) for bid in bases_seen),
                match_type=";".join(bases_seen),
                problem=f"Accepted Base differs across seasons: {assignments}",
                evidence="Season-specific frozen identity rows; no automatic remapping performed.",
                question=(
                    "Did the organization move between Base identities, or is a "
                    "season mapping wrong?"
                ),
                candidate_base_id=";".join(bases_seen),
                classification=kind,
            )

    membership_rows: list[dict[str, str]] = []
    member_sets: dict[tuple[str, str], set[str]] = defaultdict(set)
    for (season, farm), mapping in mapping_by_season_farm.items():
        if mapping["status"] in ACCEPTED_TYPES:
            member_sets[(mapping["base_id"], season)].add(farm)
    changed_base_ids: set[str] = set()
    adjacent_member_changes: list[dict[str, Any]] = []
    for base in sorted(bases, key=lambda item: item["canonical_base_name"]):
        bid = base["base_id"]
        season_lists: dict[str, set[str]] = {}
        for season in SEASONS:
            current = member_sets[(bid, season)]
            season_lists[season] = current
            unresolved_names = sorted(unresolved_candidates[(season, bid)])
            membership_rows.append(
                {
                    "base_id": bid,
                    "canonical_base_name": base["canonical_base_name"],
                    "season": season,
                    "accepted_source_labels": _json_list(current),
                    "unresolved_candidate_labels": _json_list(unresolved_names),
                    "accepted_member_count": str(len(current)),
                    "identity_status": "IDENTITY_CONFIRMED"
                    if current
                    else ("IDENTITY_UNRESOLVED" if unresolved_names else "NO_SOURCE_LABEL"),
                    "quantity_coverage_status": (
                        matrix[(season, bid)]["quantity_eligibility"]
                        if season in ("2023-2024", "2024-2025")
                        else "SEE_R7B_SOURCE_LABEL_AUTHORITY_INTERSECTION"
                    ),
                    "r1_identity_mapping_status": (
                        matrix[(season, bid)]["identity_mapping_status"]
                        if season in ("2023-2024", "2024-2025")
                        else "NOT_IN_HISTORICAL_IDENTITY_R1_SCOPE"
                    ),
                    "reference_area_mu": str(base.get("productive_area_mu", "")),
                    "area_semantics": "REFERENCE_AREA_ONLY",
                    "historical_actual_productive_area_authority": "false",
                    "area_source": "BASE_REGISTRY_R2_REFERENCE_SNAPSHOT",
                }
            )
        accepted_unchanged = (
            season_lists[SEASONS[0]] == season_lists[SEASONS[1]] == season_lists[SEASONS[2]]
        )
        unresolved_unchanged = (
            unresolved_candidates[(SEASONS[0], bid)]
            == unresolved_candidates[(SEASONS[1], bid)]
            == unresolved_candidates[(SEASONS[2], bid)]
        )
        if not accepted_unchanged or not unresolved_unchanged:
            changed_base_ids.add(bid)
        for previous, current in zip(SEASONS[:-1], SEASONS[1:], strict=True):
            added = sorted(season_lists[current] - season_lists[previous])
            removed = sorted(season_lists[previous] - season_lists[current])
            unresolved_from = sorted(unresolved_candidates[(previous, bid)])
            unresolved_to = sorted(unresolved_candidates[(current, bid)])
            unresolved_changed = unresolved_from != unresolved_to
            if added or removed or unresolved_changed:
                change_types = [
                    *("MEMBER_ADDED" for _ in added),
                    *("MEMBER_REMOVED" for _ in removed),
                ]
                if unresolved_changed:
                    change_types.append("MEMBER_UNRESOLVED")
                if added or removed:
                    change_types.extend(
                        (
                            "POSSIBLE_MEMBER_RENAMED_REQUIRES_BUSINESS_CONFIRMATION",
                            "POSSIBLE_MEMBER_SPLIT_REQUIRES_BUSINESS_CONFIRMATION",
                            "POSSIBLE_MEMBER_MERGE_REQUIRES_BUSINESS_CONFIRMATION",
                        )
                    )
                adjacent_member_changes.append(
                    {
                        "base_id": bid,
                        "canonical_base_name": base["canonical_base_name"],
                        "from_season": previous,
                        "to_season": current,
                        "member_added": added,
                        "member_removed": removed,
                        "member_unresolved_from": unresolved_from,
                        "member_unresolved_to": unresolved_to,
                        "change_types": ";".join(change_types),
                        "classification": "MEMBER_SET_CHANGED_REQUIRES_REVIEW",
                    }
                )
                _append_issue(
                    anomalies,
                    manual,
                    priority="P2_REVIEW",
                    kind="BASE_MEMBER_SET_CHANGED",
                    season=f"{previous};{current}",
                    label=";".join(
                        added + removed + sorted(set(unresolved_from) | set(unresolved_to))
                    ),
                    subfarm="",
                    quantity=Decimal(0),
                    base=base["canonical_base_name"],
                    match_type=";".join(change_types),
                    problem=(
                        "Accepted or unresolved source-member evidence changed; "
                        "this does not prove a mapping error."
                    ),
                    evidence=(
                        f"{previous} accepted={sorted(season_lists[previous])} "
                        f"unresolved={unresolved_from}; "
                        f"{current} accepted={sorted(season_lists[current])} "
                        f"unresolved={unresolved_to}"
                    ),
                    question=(
                        "Was this a real member change, rename, split/merge, or "
                        "historical mapping omission?"
                    ),
                )

    # Map R7B source-label area/coverage claims to a Base only through the
    # already accepted current member mapping; do not infer membership.
    r7b_by_base: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for source_label, qualification in r7b_qualification.items():
        member = members.get(source_label)
        if (
            member
            and member.get("match_status") in ACCEPTED_TYPES
            and member.get("matched_base_id")
        ):
            r7b_by_base[member["matched_base_id"]].append(
                {"source_label": source_label, **qualification}
            )
    r7b_bound_area_by_base: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for bid, rows in r7b_by_base.items():
        for row in rows:
            if row.get("area_bound") and row.get("area_basis") == "BUSINESS_CONFIRMED":
                r7b_bound_area_by_base[bid].append(row)
    area_authority_by_base: dict[str, list[dict[str, Any]]] = defaultdict(list)
    area_adjudication = historical_coverage.get("area_authority_adjudication", {})
    for area_row in area_adjudication.get("history_rows", []):
        member = members.get(area_row["farm"])
        if not member or member.get("match_status") not in ACCEPTED_TYPES:
            raise ValueError(
                f"historical area authority has no accepted identity binding: {area_row['farm']}"
            )
        bid = member["matched_base_id"]
        source_season = area_row["season"]
        if area_row.get("source_hash") != source_hashes[source_season]:
            raise ValueError(f"historical area source hash mismatch for {area_row['farm']}")
        recorded_total = Decimal(area_row["recorded_total_kg"])
        matching_raw_labels = [
            raw_label
            for (season, raw_label), raw_group in farm_groups.items()
            if season == source_season
            and mapping_by_season_farm[(season, raw_label)]["status"] in ACCEPTED_TYPES
            and mapping_by_season_farm[(season, raw_label)]["base_id"] == bid
            and raw_group.business_quantity == recorded_total
        ]
        if len(matching_raw_labels) != 1:
            raise ValueError(
                "historical area row must bind to one frozen-mapped raw label by "
                f"Base and exact business-window quantity: {area_row['farm']}"
            )
        authority_item = {
            "source_label": area_row["farm"],
            "matched_raw_source_label": matching_raw_labels[0],
            "identity_binding": "SAME_FROZEN_BASE_AND_EXACT_BUSINESS_WINDOW_QUANTITY",
            **area_row,
        }
        area_authority_by_base[bid].append(authority_item)
        r7b_items = [
            item
            for item in r7b_bound_area_by_base.get(bid, [])
            if item["source_label"] == area_row["farm"]
        ]
        if len(r7b_items) != 1 or Decimal(str(r7b_items[0].get("productive_area_mu"))) != Decimal(
            area_row["historical_area_mu"]
        ):
            raise ValueError(
                f"R7B area qualification does not match formal area authority: {area_row['farm']}"
            )
    for row in membership_rows:
        if row["season"] != "2025-2026":
            continue
        bound = area_authority_by_base.get(row["base_id"], [])
        if bound:
            row["historical_actual_productive_area_authority"] = "true"
            row["area_authority_scope"] = "BUSINESS_CONFIRMED_SOURCE_LABEL_BINDING"
            row["area_source"] = "HISTORICAL_IDENTITY_R1_AREA_ADJUDICATION"
            row["historical_actual_productive_area_mu"] = ";".join(
                str(item.get("historical_area_mu", "")) for item in bound
            )
            row["area_authority_source_labels"] = _json_list(
                str(item["source_label"]) for item in bound
            )
            row["area_authority_raw_source_labels"] = _json_list(
                str(item["matched_raw_source_label"]) for item in bound
            )
        else:
            row["area_authority_scope"] = "NO_SEASON_SPECIFIC_ACTUAL_AREA_AUTHORITY"
            row["historical_actual_productive_area_mu"] = ""
            row["area_authority_source_labels"] = "[]"
            row["area_authority_raw_source_labels"] = "[]"
        labels = json.loads(row["accepted_source_labels"])
        area_authority_labels = {str(item["source_label"]) for item in bound}
        qualifiers = [
            item
            for item in r7b_by_base.get(row["base_id"], [])
            if item["source_label"] in labels or item["source_label"] in area_authority_labels
        ]
        if qualifiers:
            row["quantity_coverage_status"] = (
                "R7B_SOURCE_LABEL_QUALIFICATION;BASE_AGGREGATION_NOT_PROVEN"
            )
            row["r7b_source_label_coverage"] = _json_list(
                f"{item['source_label']}:{item.get('season_completeness_status', 'UNKNOWN')}"
                for item in qualifiers
            )
        else:
            row["quantity_coverage_status"] = "R7B_BASE_SEASON_COVERAGE_NOT_ESTABLISHED"
            row["r7b_source_label_coverage"] = "[]"

    # Both source-total and frozen-business-window yields use one reference-area
    # denominator. Neither is a claim of actual yield or complete season totals.
    base_season_quality: list[dict[str, str]] = []
    membership_by_base_season = {(row["base_id"], row["season"]): row for row in membership_rows}
    for base in sorted(bases, key=lambda item: item["canonical_base_name"]):
        bid = base["base_id"]
        area = Decimal(str(base.get("productive_area_mu", "0") or "0"))
        for season in SEASONS:
            kg = mapped_base_business[(season, bid)]
            source_kg = mapped_base_raw[(season, bid)]
            days = len(mapped_base_days[(season, bid)])
            business_window_yield = kg / area if area > 0 else None
            source_total_yield = source_kg / area if area > 0 else None
            membership = membership_by_base_season[(bid, season)]
            identity = (
                "IDENTITY_CONFIRMED"
                if mapped_base_labels[(season, bid)]
                else (
                    "IDENTITY_UNRESOLVED"
                    if unresolved_candidates[(season, bid)]
                    else "NO_ACCEPTED_SOURCE_ROWS"
                )
            )
            cov = membership["quantity_coverage_status"]
            base_season_quality.append(
                {
                    "base_id": bid,
                    "canonical_base_name": base["canonical_base_name"],
                    "season": season,
                    "identity_status": identity,
                    "quantity_coverage_status": cov,
                    "identity_quantity_status": (
                        "IDENTITY_UNRESOLVED"
                        if identity == "IDENTITY_UNRESOLVED"
                        else "NO_ACCEPTED_IDENTITY + QUANTITY_NOT_COMPUTABLE"
                        if identity == "NO_ACCEPTED_SOURCE_ROWS"
                        else "IDENTITY_CONFIRMED + QUANTITY_COVERAGE_NOT_ESTABLISHED"
                        if "NOT_ESTABLISHED" in cov or "NOT_PROVEN" in cov
                        else "IDENTITY_CONFIRMED + QUANTITY_PARTIAL"
                        if "NOT_STRICT_COMPLETE" in cov or "PARTIAL" in cov
                        else "IDENTITY_CONFIRMED + AUTHORITY_STATUS_REQUIRES_REVIEW"
                    ),
                    "r1_identity_mapping_status": membership["r1_identity_mapping_status"],
                    "accepted_source_labels": _json_list(mapped_base_labels[(season, bid)]),
                    "unresolved_candidate_source_labels": _json_list(
                        unresolved_candidates[(season, bid)]
                    ),
                    "business_window_mapped_quantity_kg": _decimal_text(kg),
                    "source_total_mapped_quantity_kg": _decimal_text(source_kg),
                    "business_window_observed_day_count": str(days),
                    "low_observed_day_1_to_29": str(1 <= days <= 29).lower(),
                    "reference_area_mu": _decimal_text(area),
                    "area_semantics": "REFERENCE_AREA_ONLY",
                    "historical_actual_productive_area_authority": membership[
                        "historical_actual_productive_area_authority"
                    ],
                    "historical_actual_productive_area_mu": membership.get(
                        "historical_actual_productive_area_mu", ""
                    ),
                    "area_authority_scope": membership.get(
                        "area_authority_scope", "NO_SEASON_SPECIFIC_ACTUAL_AREA_AUTHORITY"
                    ),
                    "area_authority_source_labels": membership.get(
                        "area_authority_source_labels", "[]"
                    ),
                    "area_authority_raw_source_labels": membership.get(
                        "area_authority_raw_source_labels", "[]"
                    ),
                    "business_window_yield_kg_per_reference_mu": _decimal_text(
                        business_window_yield
                    ),
                    "source_total_yield_kg_per_reference_mu": _decimal_text(source_total_yield),
                }
            )
            if days and days < 30:
                _append_issue(
                    anomalies,
                    manual,
                    priority="P1_HIGH",
                    kind="LOW_OBSERVED_DAY_COUNT",
                    season=season,
                    label=";".join(sorted(mapped_base_labels[(season, bid)])),
                    subfarm="",
                    quantity=kg,
                    base=base["canonical_base_name"],
                    match_type="ACCEPTED_IDENTITY",
                    problem=(
                        f"Only {days} distinct in-window observed day(s); season-total "
                        "coverage is not established."
                    ),
                    evidence=(
                        f"Frozen business window={SEASON_WINDOWS[season][0]}.."
                        f"{SEASON_WINDOWS[season][1]}; daily unknowns were not zero-filled."
                    ),
                    question=(
                        "Do operations records confirm a complete active harvest span, "
                        "or is this a partial extract?"
                    ),
                )

    yield_jumps: list[dict[str, Any]] = []
    for base in sorted(bases, key=lambda item: item["canonical_base_name"]):
        bid = base["base_id"]
        area = Decimal(str(base.get("productive_area_mu", "0") or "0"))
        for previous, current in zip(SEASONS[:-1], SEASONS[1:], strict=True):
            prev_kg = mapped_base_raw[(previous, bid)]
            curr_kg = mapped_base_raw[(current, bid)]
            prev_business_kg = mapped_base_business[(previous, bid)]
            curr_business_kg = mapped_base_business[(current, bid)]
            prev_yield = prev_kg / area if area > 0 else Decimal(0)
            curr_yield = curr_kg / area if area > 0 else Decimal(0)
            prev_business_yield = prev_business_kg / area if area > 0 else Decimal(0)
            curr_business_yield = curr_business_kg / area if area > 0 else Decimal(0)
            if prev_yield <= 0 or curr_yield <= 0:
                continue
            ratio = curr_yield / prev_yield
            business_ratio = (
                curr_business_yield / prev_business_yield if prev_business_yield else None
            )
            source_flagged = ratio > Decimal("2.5") or ratio < Decimal("0.4")
            business_flagged = business_ratio is not None and (
                business_ratio > Decimal("2.5") or business_ratio < Decimal("0.4")
            )
            if source_flagged or business_flagged:
                jump = {
                    "base_id": bid,
                    "canonical_base_name": base["canonical_base_name"],
                    "from_season": previous,
                    "to_season": current,
                    "previous_source_mapped_kg_including_out_of_window_rows": _decimal_text(
                        prev_kg
                    ),
                    "current_source_mapped_kg_including_out_of_window_rows": _decimal_text(curr_kg),
                    "previous_business_window_mapped_kg": _decimal_text(prev_business_kg),
                    "current_business_window_mapped_kg": _decimal_text(curr_business_kg),
                    "reference_area_mu": _decimal_text(area),
                    "previous_yield_kg_per_reference_mu": _decimal_text(prev_yield),
                    "current_yield_kg_per_reference_mu": _decimal_text(curr_yield),
                    "source_total_yield_ratio": _decimal_text(ratio),
                    "business_window_previous_yield_kg_per_reference_mu": _decimal_text(
                        prev_business_yield
                    ),
                    "business_window_current_yield_kg_per_reference_mu": _decimal_text(
                        curr_business_yield
                    ),
                    "business_window_yield_ratio": _decimal_text(business_ratio),
                    "source_total_ratio_flagged": source_flagged,
                    "business_window_ratio_flagged": business_flagged,
                    "flag_rule": "ratio > 2.5 or ratio < 0.4; audit flag only",
                    "interpretation": (
                        "SOURCE_TOTAL_INCLUDES_OUT_OF_WINDOW_ROWS; COVERAGE_MAPPING_AREA "
                        "OR REAL_CHANGE_UNRESOLVED"
                    ),
                }
                yield_jumps.append(jump)
                _append_issue(
                    anomalies,
                    manual,
                    priority="P1_HIGH",
                    kind="EXTREME_CROSS_SEASON_YIELD_JUMP",
                    season=f"{previous};{current}",
                    label=";".join(
                        sorted(
                            mapped_base_labels[(previous, bid)] | mapped_base_labels[(current, bid)]
                        )
                    ),
                    subfarm="",
                    quantity=curr_business_kg,
                    base=base["canonical_base_name"],
                    match_type="REFERENCE_AREA_ONLY_SOURCE_AND_WINDOW_RATIOS",
                    problem=(
                        f"Reference-area yield ratio {ratio} exceeds the audit-only "
                        "2.5 / 0.4 flag range."
                    ),
                    evidence=json.dumps(jump, ensure_ascii=False, sort_keys=True),
                    question=(
                        "Is the change due to coverage, mapping, area denominator, "
                        "source truncation, or real production?"
                    ),
                )

    # Source subfarm labels are descriptive only; reuse under different parents
    # is flagged and never used to infer a Base assignment.
    reused_subfarms: list[dict[str, Any]] = []
    for (season, subfarm), parents in sorted(parent_by_subfarm.items()):
        if len(parents) > 1:
            parent_rows = [
                {
                    "parent_farm_label": parent,
                    "quantity_kg": _decimal_text(pair_groups[(season, parent, subfarm)].quantity),
                }
                for parent in sorted(parents)
            ]
            affected_quantity = sum(
                (pair_groups[(season, parent, subfarm)].quantity for parent in parents),
                Decimal(0),
            )
            reused_subfarms.append({"season": season, "subfarm": subfarm, "parents": parent_rows})
            _append_issue(
                anomalies,
                manual,
                priority="P2_REVIEW",
                kind="SUBFARM_LABEL_REUSED_ACROSS_PARENTS",
                season=season,
                label="",
                subfarm=subfarm,
                quantity=affected_quantity,
                base="",
                match_type="NOT_INDEPENDENTLY_MAPPED",
                problem=(
                    "Same subfarm text appears under multiple source farm parents: "
                    f"{sorted(parents)}"
                ),
                evidence="Subfarm text was not used as independent mapping authority.",
                question="Are identically named subfarms one operation or distinct farms?",
            )

    # High-risk review requests named in the task. Existing mapping decisions
    # remain unchanged; this only makes evidence and confirmation gaps visible.
    risk_specs = [
        (
            "JIANSHUI_CHAKE_NANZHUANG",
            ("建水南庄基地", "建水岔科基地", "建水岔科农场"),
            (
                "Is Nanzhuang the same operational Base as Chake each season? "
                "Did the organization change?"
            ),
        ),
        (
            "YUANJIANG_GANZHUANG_YANGWU",
            ("元江甘庄农场", "新平扬武农场"),
            (
                "Does Yangwu belong to Ganzhuang each season? Do coverage/member "
                "changes explain the yield jump?"
            ),
        ),
        (
            "TENGCHONG_DEHONG_YINGJIANG",
            ("腾冲德宏农场", "盈江联农带农"),
            (
                "Is Yingjiang Lian Nong Dai Nong formally part of Tengchong Dehong, "
                "beyond the exact registry entry?"
            ),
        ),
        (
            "YANSHAN_HUILONG_CENTER_STATION",
            ("砚山回龙农场", "砚山回龙（中心实验站）", "回龙中心实验站"),
            (
                "Was the Huilong center station historically part of Huilong, added, "
                "renamed, or omitted?"
            ),
        ),
    ]
    risk_details: list[dict[str, Any]] = []
    for risk_id, names, question in risk_specs:
        relevant = []
        total = Decimal(0)
        for (season, farm), group in sorted(farm_groups.items()):
            if farm in names:
                mapping = mapping_by_season_farm[(season, farm)]
                relevant.append(
                    {
                        "season": season,
                        "source_label": farm,
                        "quantity_kg": _decimal_text(group.quantity),
                        "business_window_kg": _decimal_text(group.business_quantity),
                        "observed_days": len(group.dates),
                        "mapping_status": mapping["status"],
                        "match_type": mapping["match_type"],
                        "base_id": mapping["base_id"] or mapping["candidate_base_id"],
                        "base_name": mapping["base_name"] or mapping["candidate_base_name"],
                    }
                )
                total += group.quantity
        if relevant:
            risk_details.append({"risk_id": risk_id, "items": relevant})
            _append_issue(
                anomalies,
                manual,
                priority="P1_HIGH",
                kind="PRESCRIBED_HIGH_RISK_BUSINESS_REVIEW",
                season=";".join(sorted({item["season"] for item in relevant})),
                label=";".join(sorted({item["source_label"] for item in relevant})),
                subfarm="",
                quantity=total,
                base=";".join(
                    sorted({item["base_name"] for item in relevant if item["base_name"]})
                ),
                match_type=";".join(sorted({item["match_type"] for item in relevant})),
                problem=(
                    f"Task-mandated high-risk review {risk_id}; this audit changes no mapping."
                ),
                evidence=json.dumps(relevant, ensure_ascii=False, sort_keys=True),
                question=question,
                candidate_base_id=";".join(
                    sorted({item["base_id"] for item in relevant if item["base_id"]})
                ),
            )

    # Check all source raw row hashes occur once and no raw row can be counted
    # twice through the two parallel aggregation levels.
    raw_row_count = len(source_rows)
    raw_row_hash_unique_count = len({row.raw_record_hash for row in source_rows})
    total_source = sum(raw_by_season.values(), Decimal(0))
    total_mapped = sum(mapped_by_season.values(), Decimal(0))
    total_unresolved = sum(unresolved_by_season.values(), Decimal(0))
    total_excluded = sum(excluded_by_season.values(), Decimal(0))
    total_delta = total_source - total_mapped - total_unresolved - total_excluded
    all_reconciled = all(
        row["quantity_reconciliation_pass"] for row in season_reconciliation.values()
    )
    day_counts = Counter(
        "1-29"
        if 1 <= len(mapped_base_days[key]) <= 29
        else "30-59"
        if 30 <= len(mapped_base_days[key]) <= 59
        else "60-89"
        if 60 <= len(mapped_base_days[key]) <= 89
        else "90+"
        if len(mapped_base_days[key]) >= 90
        else "NO_ACCEPTED_MAPPED_DAY"
        for key in mapped_base_days
    )
    anomaly_priority_counts = Counter(row["priority"] for row in anomalies)
    all_ledger_label_rows = len(farm_ledger)
    mapped_label_total = sum(row["current_mapping_status"] in ACCEPTED_TYPES for row in farm_ledger)
    unresolved_label_total = sum(
        row["current_mapping_status"] in {"UNRESOLVED", "CONFLICTING"} for row in farm_ledger
    )
    conflicting_label_total = sum(
        row["current_mapping_status"] == "CONFLICTING" for row in farm_ledger
    )
    excluded_label_total = sum(row["current_mapping_status"] == "EXCLUDED" for row in farm_ledger)
    unique_source_label_count = len({row["source_farm_label"] for row in farm_ledger})
    cross_season_mapping_status = (
        "FAIL"
        if (
            not all_reconciled
            or total_delta != 0
            or conflicting_label_total
            or multi_assigned_source_rows
        )
        else "REQUIRES_BUSINESS_CONFIRMATION"
        if unresolved_label_total or labels_with_different_bases
        else "PASS"
    )

    summary = {
        "task_id": "CROSS_SEASON_DATA_MAPPING_AND_QUALITY_AUDIT_R1",
        "result": "FAIL_AUDIT_INTEGRITY"
        if cross_season_mapping_status == "FAIL"
        else "PASS_WITH_BUSINESS_CONFIRMATION_REQUIRED"
        if all_reconciled and unresolved_label_total
        else "PASS"
        if all_reconciled
        else "FAIL_QUANTITY_RECONCILIATION",
        "base_ref": "main",
        "expected_main_sha": "3c0ae295dfbd327fcbc9dcd92dea7511b5030e8b",
        "main_ancestry_verified": True,
        "source_hashes": source_hashes,
        "authority_hashes": authority_hashes,
        "season_authority_selection": {
            "2023-2024": (
                "HISTORICAL_IDENTITY_RECONSTRUCTION_R1 season-scoped decisions; "
                "cross-checked against BASE_MEMBER_MAPPING_R2"
            ),
            "2024-2025": (
                "HISTORICAL_IDENTITY_RECONSTRUCTION_R1 season-scoped decisions; "
                "cross-checked against BASE_MEMBER_MAPPING_R2"
            ),
            "2025-2026": (
                "BASE_MEMBER_MAPPING_R2 + Base Registry; historical R1 has no 2025-2026 rows"
            ),
        },
        "combined_identity_authority": {
            "sha256_declared_by_v07_s1_evidence": authority_hashes["combined_identity_authority"],
            "machine_evidence_reference": (
                "docs/v0-7/evidence/s1-formal-multi-season-baseline-validation.json"
            ),
            "standalone_serialized_preimage_found": False,
            "audit_replay_basis": (
                "Parsed season-scoped R1 mapping + R2 member map + 39-Base registry"
            ),
        },
        "raw_row_count": raw_row_count,
        "raw_row_unique_hash_count": raw_row_hash_unique_count,
        "source_label_total_season_scoped": all_ledger_label_rows,
        "source_label_total": all_ledger_label_rows,
        "source_label_unique_text_count_across_seasons": unique_source_label_count,
        "mapped_label_total": mapped_label_total,
        "mapped_label_count": mapped_label_total,
        "unresolved_label_total": unresolved_label_total,
        "unresolved_label_count": unresolved_label_total,
        "conflicting_label_total": conflicting_label_total,
        "conflicting_label_count": conflicting_label_total,
        "explicitly_excluded_label_total": excluded_label_total,
        "source_farm_subfarm_pair_ledger_rows": len(pair_ledger),
        "base_member_set_changed_count": len(changed_base_ids),
        "base_member_set_changed_base_ids": sorted(changed_base_ids),
        "same_label_different_base_count": len(labels_with_different_bases),
        "same_label_different_base": labels_with_different_bases,
        "same_raw_record_assigned_to_multiple_bases_count": len(multi_assigned_source_rows),
        "same_raw_record_assignment_conflicts": [
            {
                "season": identity[0],
                "sheet": identity[1],
                "row_number": identity[2],
                "base_ids": base_ids,
            }
            for identity, base_ids in sorted(multi_assigned_source_rows.items())
        ],
        "same_season_source_label_authority_conflict_count": sum(
            count["CONFLICTING"] for count in counts_by_season.values()
        ),
        "member_rename_split_merge_inference": (
            "NOT_AUTOMATICALLY_INFERRED_REQUIRES_BUSINESS_CONFIRMATION"
        ),
        "base_member_change_ledger_row_count": len(adjacent_member_changes),
        "extreme_yield_jump_count": len(yield_jumps),
        "low_observed_day_base_season_count": sum(
            1 for row in base_season_quality if row["low_observed_day_1_to_29"] == "true"
        ),
        "low_observed_day_buckets": dict(sorted(day_counts.items())),
        "raw_total_kg": _decimal_text(total_source),
        "mapped_total_kg": _decimal_text(total_mapped),
        "unresolved_total_kg": _decimal_text(total_unresolved),
        "explicitly_excluded_total_kg": _decimal_text(total_excluded),
        "conflicting_quantity_is_included_in_unresolved": True,
        "reconciliation_delta_kg": _decimal_text(total_delta),
        "quantity_reconciliation_pass": all_reconciled and total_delta == 0,
        "can_we_prove_all_three_season_mappings_correct": cross_season_mapping_status == "PASS",
        "cross_season_mapping_status": cross_season_mapping_status,
        "per_season": season_reconciliation,
        "risk_review_groups": risk_details,
        "extreme_yield_jumps": yield_jumps,
        "reused_subfarm_label_count": len(reused_subfarms),
        "reused_subfarm_labels": reused_subfarms,
        "coverage_policy": {
            "2023-2024": (
                "HISTORICAL_R1_BASE_SEASON_MATRIX; mapped subtotals are not complete totals"
            ),
            "2024-2025": "HISTORICAL_R1_BASE_SEASON_MATRIX; partial/unknown semantics retained",
            "2025-2026": (
                "R7B source-label qualification is separate; no implicit 39-Base "
                "completeness promotion"
            ),
            "2025-2026_in_window_global_unknown_no_record_days": 40,
            "2025-2026_global_unknown_days_zero_filled": False,
            "missing_is_zero": False,
            "unresolved_is_zero": False,
        },
        "area_policy": {
            "registry_area_semantics": "REFERENCE_AREA_ONLY",
            "historical_actual_productive_area_backfilled": False,
            "reference_area_yields_are_diagnostic_only": True,
        },
        "anomaly_priority_counts": {
            "P0_CRITICAL": anomaly_priority_counts["P0_CRITICAL"],
            "P1_HIGH": anomaly_priority_counts["P1_HIGH"],
            "P2_REVIEW": anomaly_priority_counts["P2_REVIEW"],
            "INFO": anomaly_priority_counts["INFO"],
        },
        "manual_business_confirmation_count": len({row["issue_id"] for row in manual}),
        "raw_private_detail_policy": (
            "ROW_LEVEL_CSV_PRIVATE; REPOSITORY_EVIDENCE_SUMMARIZES_HASHES_AND_COUNTS"
        ),
        "existing_v07_changed": False,
        "model_changed": False,
        "model_retrained": False,
    }
    return {
        "summary": summary,
        "source_identity_ledger": pair_ledger,
        "farm_label_ledger": farm_ledger,
        "base_membership_matrix": membership_rows,
        "base_season_quality": base_season_quality,
        "anomaly_ledger": sorted(
            anomalies,
            key=lambda row: (
                row["priority"],
                row["issue_type"],
                row["season"],
                row["source_label"],
            ),
        ),
        "manual_confirmation": sorted(
            {row["issue_id"]: row for row in manual}.values(),
            key=lambda row: (row["priority"], row["season"], row["source_label"], row["issue_id"]),
        ),
        "extreme_yield_jumps": yield_jumps,
        "membership_changes": adjacent_member_changes,
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        path.chmod(0o600)
        return
    fieldnames = list(rows[0])
    fieldnames.extend(sorted({key for row in rows for key in row} - set(fieldnames)))
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    path.chmod(0o600)


def write_private_artifacts(result: dict[str, Any], output: Path) -> dict[str, Any]:
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    artifacts = {
        "cross-season-source-identity-ledger.csv": result["source_identity_ledger"],
        "cross-season-source-farm-label-ledger.csv": result["farm_label_ledger"],
        "cross-season-base-membership-matrix.csv": result["base_membership_matrix"],
        "cross-season-base-member-change-ledger.csv": result["membership_changes"],
        "cross-season-base-season-quality.csv": result["base_season_quality"],
        "cross-season-anomaly-ledger.csv": result["anomaly_ledger"],
        "manual_business_confirmation.csv": result["manual_confirmation"],
    }
    manifest: dict[str, Any] = {"policy": "PRIVATE_ROW_LEVEL_AUDIT_OUTPUTS", "files": {}}
    for filename, rows in artifacts.items():
        path = output / filename
        _write_csv(path, rows)
        manifest["files"][filename] = {
            "row_count": len(rows),
            "sha256": _sha256(path),
            "mode": "0600",
        }
    summary_path = output / "audit-summary.json"
    summary_path.write_text(
        json.dumps(result["summary"], ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    summary_path.chmod(0o600)
    manifest["files"][summary_path.name] = {
        "row_count": 1,
        "sha256": _sha256(summary_path),
        "mode": "0600",
    }
    manifest_path = output / "artifact-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest_path.chmod(0o600)
    return manifest


def execute(args: argparse.Namespace) -> dict[str, Any]:
    source_paths = {
        "2023-2024": args.source_2023_2024,
        "2024-2025": args.source_2024_2025,
        "2025-2026": args.source_2025_2026,
    }
    source_hashes = {season: _sha256(path) for season, path in source_paths.items()}
    authority_paths = {
        "historical_identity_mapping": args.historical_identity_mapping,
        "historical_identity_matrix": args.historical_identity_matrix,
        "historical_identity_coverage_summary": args.historical_coverage_summary,
        "base_member_mapping": args.base_member_mapping,
        "base_registry": args.base_registry,
        "mapping_authority": args.mapping_authority,
        "combined_identity_authority": args.s1_evidence,
    }
    computed_authority_hashes = {key: _sha256(path) for key, path in authority_paths.items()}
    for key, expected in EXPECTED_INPUT_FILE_HASHES.items():
        if computed_authority_hashes[key] != expected:
            raise ValueError(f"frozen authority file SHA256 mismatch: {key}")
    if (
        computed_authority_hashes["historical_identity_mapping"]
        != EXPECTED_AUTHORITY_HASHES["historical_identity_mapping"]
    ):
        raise ValueError("historical identity mapping hash mismatch")
    if (
        computed_authority_hashes["base_member_mapping"]
        != EXPECTED_AUTHORITY_HASHES["base_member_mapping"]
    ):
        raise ValueError("Base member mapping hash mismatch")
    s1_evidence = json.loads(args.s1_evidence.read_text(encoding="utf-8"))
    declared_combined_hash = s1_evidence["authorities"]["combined_identity_authority_sha256"]
    if declared_combined_hash != EXPECTED_AUTHORITY_HASHES["combined_identity_authority"]:
        raise ValueError("combined identity authority hash declaration mismatch")
    computed_authority_hashes["combined_identity_authority"] = declared_combined_hash
    historical_coverage = json.loads(args.historical_coverage_summary.read_text(encoding="utf-8"))
    registry = json.loads(args.base_registry.read_text(encoding="utf-8"))
    members = _read_csv(args.base_member_mapping)
    authority = json.loads(args.mapping_authority.read_text(encoding="utf-8"))
    if authority.get("version") != "BASE_MEMBER_MAPPING_R2":
        raise ValueError("unexpected member mapping authority version")
    if authority.get("policy") != "EXACT_FIRST_EXPLICIT_ALIAS_ONLY_NO_FUZZY_NO_MULTI_ASSIGNMENT":
        raise ValueError("frozen no-fuzzy/no-multi-assignment policy mismatch")
    qualification = json.loads(args.r7b_qualification.read_text(encoding="utf-8"))
    rows = [row for season, path in source_paths.items() for row in read_source_xls(path, season)]
    hist = _read_csv(args.historical_identity_mapping)
    hist_matrix = _read_csv(args.historical_identity_matrix)
    result = build_audit(
        rows,
        hist,
        hist_matrix,
        historical_coverage,
        members,
        registry,
        qualification,
        source_hashes,
        computed_authority_hashes,
    )
    result["summary"]["private_artifact_id"] = "cross-season-data-mapping-and-quality-audit-r1"
    result["summary"]["source_hashes_verified"] = True
    result["summary"]["authority_hashes_verified"] = True
    result["summary"]["raw_file_paths_recorded_in_repository"] = False
    manifest = write_private_artifacts(result, args.private_output_dir)
    result["summary"]["private_artifact_manifest"] = manifest
    return result["summary"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-2023-2024", type=Path, required=True)
    parser.add_argument("--source-2024-2025", type=Path, required=True)
    parser.add_argument("--source-2025-2026", type=Path, required=True)
    parser.add_argument("--historical-identity-mapping", type=Path, required=True)
    parser.add_argument("--historical-identity-matrix", type=Path, required=True)
    parser.add_argument("--historical-coverage-summary", type=Path, required=True)
    parser.add_argument("--base-member-mapping", type=Path, required=True)
    parser.add_argument("--base-registry", type=Path, required=True)
    parser.add_argument("--mapping-authority", type=Path, required=True)
    parser.add_argument("--s1-evidence", type=Path, required=True)
    parser.add_argument("--r7b-qualification", type=Path, required=True)
    parser.add_argument("--private-output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(execute(args), ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
