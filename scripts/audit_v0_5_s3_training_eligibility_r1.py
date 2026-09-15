"""Freeze V0.5-S3 label eligibility and evaluation design.

This runner audits only the already-authorized Base Registry and the reviewed
base daily ledger.  It does not fit a model, create weather features, or alter
the historical artifacts.  The input roots are explicit so a private
authority snapshot cannot be silently replaced by a repository fixture.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

SEASONS = ("2023-2024", "2024-2025", "2025-2026")
KNOWN_STATUS = "OBSERVED_OR_AUTHORIZED_LEDGER_ZERO"
UNKNOWN_STATUS = {
    "UNKNOWN_GLOBAL_NO_RECORD",
    "UNKNOWN_MEMBER_COVERAGE",
    "MISSING_BASE_DAY_RECORD",
    "SOURCE_NOT_COVERED",
}
BUSINESS_CUTOFF_MONTH_DAY = "04-15"
EXPECTED_BASE_COUNT = 39
EXPECTED_WEATHER_BASE_COUNT = 38
EXPECTED_WEATHER_DAYS = {
    "2023-2024": 290,
    "2024-2025": 289,
    "2025-2026": 289,
}
EXPECTED_INPUT_HASHES = {
    "registry_artifact_manifest": (
        "e2c57ae300b98a8048e8c8ef73a852d6495ee52a94600c62ed1951298896cd88"
    ),
    "registry": "502c73fecdf68e91e4aa35982a2207d224204390597eaf59420ebd1101539904",
    "ledger": "39a98f79e8be9022e25b4f093ff773e35fe40784122fcfc0612595945b61d3ef",
    "season_audit": "3996b3bbb23a206f71377c7f3bd656574066ab8535a97f965df2286852160795",
    "registry_source_manifest": "6bf1dede2ea9aacf9d1964aafaebbc68b6ce32868bc0cad04da1373a1840cd10",
    "registry_summary": "e659e444b48850ba246185bc44d034f6f425f2f7ceec26bb8f99a4863f23fe32",
    "weather_manifest": "708860fcc396552594ff6dc30c10fa758e94246f550e92a4567d4dc9ebf0b9a3",
    "weather_daily": "5ad49f11895c76e6aadd01d240ada3ba93d599d25138a2609887e527e58dad3b",
}


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_value_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    path.chmod(0o600)


def parse_season(season: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d{4})-(\d{4})", season)
    if match is None or int(match.group(2)) != int(match.group(1)) + 1:
        raise ValueError(f"season is not a consecutive year pair: {season}")
    return int(match.group(1)), int(match.group(2))


def season_window(season: str) -> tuple[date, date]:
    start_year, end_year = parse_season(season)
    return date(start_year, 7, 1), date(end_year, 4, 15)


def dates_between(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def checked_hash(path: Path, expected: str, role: str) -> str:
    actual = file_hash(path)
    if actual != expected:
        raise ValueError(f"{role} hash mismatch: expected {expected}, got {actual}")
    return actual


def source_specs(source_manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    specs: dict[str, dict[str, Any]] = {}
    for source in source_manifest.get("sources", []):
        season = {
            "23~24.xls": "2023-2024",
            "24~25.xls": "2024-2025",
            "原果入库汇总表.xls": "2025-2026",
        }.get(source.get("file_name"))
        if season is not None:
            specs[season] = source
    if set(specs) != set(SEASONS):
        raise ValueError("registry source manifest does not contain the three authorized seasons")
    return specs


def load_inputs(config: dict[str, Any], registry_root: Path, weather_root: Path) -> dict[str, Any]:
    required = {
        "registry_artifact_manifest": registry_root / "artifact-manifest.json",
        "registry": registry_root / "base-registry-v1.json",
        "ledger": registry_root / "base-daily-ledger.csv",
        "season_audit": registry_root / "business-season-boundary-audit.csv",
        "registry_source_manifest": registry_root / "source-manifest.json",
        "registry_summary": registry_root / "summary.json",
        "weather_manifest": weather_root / "dataset-manifest.json",
        "weather_daily": weather_root / "daily.jsonl",
    }
    for role, path in required.items():
        if not path.is_file():
            raise FileNotFoundError(f"missing authorized input {role}: {path.name}")
        checked_hash(path, EXPECTED_INPUT_HASHES[role], role)

    artifact_manifest = read_json(required["registry_artifact_manifest"])
    for name, expected in artifact_manifest.items():
        path = registry_root / name
        if not path.is_file() or file_hash(path) != expected:
            raise ValueError(f"registry artifact manifest mismatch: {name}")
    registry = read_json(required["registry"])
    if registry.get("hash") != config["registry"]["payload_hash"]:
        raise ValueError("Base Registry payload hash mismatch")
    bases = registry.get("bases")
    if not isinstance(bases, list) or len(bases) != config["registry"]["expected_count"]:
        raise ValueError("Base Registry count mismatch")
    if any(not base.get("active") for base in bases):
        raise ValueError("inactive base found in current active universe")
    base_ids = [str(base["base_id"]) for base in bases]
    if len(set(base_ids)) != len(base_ids):
        raise ValueError("duplicate base identity in active registry")

    ledger_rows = read_csv_rows(required["ledger"])
    ledger_by_key: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in ledger_rows:
        key = (row["season"], row["base_id"], row["date"])
        if key in ledger_by_key:
            raise ValueError(f"duplicate base-day ledger row: {key}")
        if row["base_id"] not in set(base_ids):
            raise ValueError(f"ledger row references unknown base: {row['base_id']}")
        if row["season"] not in SEASONS:
            raise ValueError(f"ledger row references unknown season: {row['season']}")
        if row["observation_status"] not in {KNOWN_STATUS} | UNKNOWN_STATUS:
            raise ValueError(f"unsupported observation status: {row['observation_status']}")
        if row["observation_status"] == KNOWN_STATUS:
            value = row["recorded_harvest_kg"]
            if not value:
                raise ValueError(f"known ledger row has no quantity: {key}")
            quantity = Decimal(value)
            if not quantity.is_finite() or quantity < 0:
                raise ValueError(f"known ledger quantity invalid: {key}")
        ledger_by_key[key] = row

    season_audit = read_csv_rows(required["season_audit"])
    audit_by_key: dict[tuple[str, str], dict[str, str]] = {}
    for row in season_audit:
        audit_key = (row["season"], row["base_id"])
        if audit_key in audit_by_key:
            raise ValueError(f"duplicate season audit row: {audit_key}")
        audit_by_key[audit_key] = row
    expected_keys = {(season, base_id) for season in SEASONS for base_id in base_ids}
    if set(audit_by_key) != expected_keys:
        raise ValueError("season audit does not cover exactly the active base universe")

    registry_source_manifest = read_json(required["registry_source_manifest"])
    specs = source_specs(registry_source_manifest)
    for season, spec in specs.items():
        if spec.get("sha256") != config["sources"][season]["source_hash"]:
            raise ValueError(f"historical source hash drift: {season}")
    if any(not source.get("arrival_equals_harvest") for source in specs.values()):
        raise ValueError("arrival-equals-harvest authority is not true for every source")
    if any(source.get("quantity_unit") != "KG" for source in specs.values()):
        raise ValueError("historical quantity unit drift")

    weather_manifest = read_json(required["weather_manifest"])
    if weather_manifest.get("daily_artifact_sha256") != EXPECTED_INPUT_HASHES["weather_daily"]:
        raise ValueError("weather daily artifact hash is not pinned")
    if weather_manifest.get("daily_dataset_hash") != config["weather"]["daily_dataset_hash"]:
        raise ValueError("weather daily dataset hash drift")
    if weather_manifest.get("complete_base_count") != EXPECTED_WEATHER_BASE_COUNT:
        raise ValueError("weather complete-base count drift")
    if weather_manifest.get("local_timezone") != "Asia/Shanghai":
        raise ValueError("weather timezone drift")

    return {
        "files": {role: file_hash(path) for role, path in required.items()},
        "registry": registry,
        "bases": bases,
        "base_ids": base_ids,
        "ledger_rows": ledger_rows,
        "ledger_by_key": ledger_by_key,
        "season_audit": season_audit,
        "audit_by_key": audit_by_key,
        "source_specs": specs,
        "weather_manifest": weather_manifest,
        "weather_root": weather_root,
        "registry_root": registry_root,
    }


def build_source_calendar(
    season: str,
    base_ids: list[str],
    ledger_by_key: dict[tuple[str, str, str], dict[str, str]],
    source_start: date,
    source_end: date,
) -> list[dict[str, Any]]:
    business_start, business_end = season_window(season)
    rows: list[dict[str, Any]] = []
    for day in dates_between(business_start, business_end):
        day_text = day.isoformat()
        covered = source_start <= day <= source_end
        day_rows = [
            ledger_by_key[(season, base_id, day_text)]
            for base_id in base_ids
            if (season, base_id, day_text) in ledger_by_key
        ]
        all_rows_are_global_unknown = bool(day_rows) and all(
            row["observation_status"] == "UNKNOWN_GLOBAL_NO_RECORD" for row in day_rows
        )
        source_active = covered and bool(day_rows) and not all_rows_are_global_unknown
        global_unknown = covered and (not day_rows or all_rows_are_global_unknown)
        status_counts = Counter(row["observation_status"] for row in day_rows)
        rows.append(
            {
                "season": season,
                "date": day_text,
                "source_start": source_start.isoformat(),
                "source_end": source_end.isoformat(),
                "source_covered": covered,
                "source_active_day": source_active,
                "global_no_record_day": global_unknown,
                "base_row_count": len(day_rows),
                "known_row_count": status_counts[KNOWN_STATUS],
                "unknown_member_row_count": status_counts["UNKNOWN_MEMBER_COVERAGE"],
                "unknown_global_row_count": (
                    len(base_ids) if global_unknown else status_counts["UNKNOWN_GLOBAL_NO_RECORD"]
                ),
            }
        )
    return rows


def build_daily_eligibility(
    season: str,
    bases: list[dict[str, Any]],
    ledger_by_key: dict[tuple[str, str, str], dict[str, str]],
    source_calendar: list[dict[str, Any]],
    source_start: date,
    source_end: date,
) -> list[dict[str, Any]]:
    calendar_by_date = {row["date"]: row for row in source_calendar}
    business_start, business_end = season_window(season)
    rows: list[dict[str, Any]] = []
    for base in bases:
        base_id = str(base["base_id"])
        for day in dates_between(business_start, business_end):
            day_text = day.isoformat()
            calendar_row = calendar_by_date[day_text]
            ledger = ledger_by_key.get((season, base_id, day_text))
            if not source_start <= day <= source_end:
                state = "SOURCE_NOT_COVERED"
            elif calendar_row["global_no_record_day"]:
                state = "UNKNOWN_GLOBAL_NO_RECORD"
            elif ledger is None:
                state = "MISSING_BASE_DAY_RECORD"
            else:
                state = ledger["observation_status"]
            known = state == KNOWN_STATUS
            value = ledger["recorded_harvest_kg"] if known and ledger is not None else ""
            rows.append(
                {
                    "base_id": base_id,
                    "canonical_base_name": base["canonical_base_name"],
                    "season": season,
                    "date": day_text,
                    "source_active_day": calendar_row["source_active_day"],
                    "global_no_record_day": calendar_row["global_no_record_day"],
                    "label_state": state,
                    "label_known": known,
                    "observed_harvest_kg": value,
                }
            )
    return rows


def _member_complete(audit: dict[str, str]) -> bool:
    return (
        audit["unresolved_member_farm_count"] == "0"
        and audit["resolved_member_farm_count"] == audit["member_farm_count"]
    )


def _area_valid(base: dict[str, Any]) -> bool:
    value = base.get("productive_area_mu")
    status = base.get("area_review_status")
    if value is None or status not in {
        "USER_AUTHORIZED_PRODUCTIVE_AREA",
        "BUSINESS_CONFIRMED",
        "AUTHORIZED_CALIBRATION",
        "MEASURED",
        "BUSINESS_REPORTED",
    }:
        return False
    area = Decimal(str(value))
    return area.is_finite() and area > 0


def build_peak_rows(
    daily_rows: list[dict[str, Any]],
    bases: list[dict[str, Any]],
    season: str,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in daily_rows:
        grouped[row["base_id"]].append(row)
    output: list[dict[str, Any]] = []
    for base in bases:
        rows = grouped[str(base["base_id"])]
        unknown = [row for row in rows if not row["label_known"]]
        known = [row for row in rows if row["label_known"]]
        status = "EXACT_COMPUTABLE" if not unknown else "NOT_COMPUTABLE_INCOMPLETE_LABEL_DOMAIN"
        peak_date = ""
        peak_kg = ""
        if not unknown and known:
            peak = min(
                known,
                key=lambda row: (
                    -Decimal(row["observed_harvest_kg"]),
                    row["date"],
                ),
            )
            peak_date, peak_kg = peak["date"], peak["observed_harvest_kg"]
        output.append(
            {
                "base_id": base["base_id"],
                "canonical_base_name": base["canonical_base_name"],
                "season": season,
                "peak_evaluation_status": status,
                "actual_peak_date": peak_date,
                "actual_peak_kg": peak_kg,
                "unknown_label_day_count": len(unknown),
                "known_label_day_count": len(known),
                "tie_break": "EARLIEST_DATE",
            }
        )
    return output


def build_window_rows(
    daily_rows: list[dict[str, Any]], season: str, window_days: int
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in daily_rows:
        grouped[row["base_id"]].append(row)
    output: list[dict[str, Any]] = []
    for base_id, rows in sorted(grouped.items()):
        rows.sort(key=lambda row: row["date"])
        for index in range(len(rows) - window_days):
            origin = rows[index]
            window = rows[index + 1 : index + 1 + window_days]
            complete = all(row["label_known"] for row in window)
            total = ""
            if complete:
                total = format(
                    sum((Decimal(row["observed_harvest_kg"]) for row in window), Decimal(0)),
                    "f",
                )
            output.append(
                {
                    "base_id": base_id,
                    "season": season,
                    "origin_date": origin["date"],
                    "window_days": window_days,
                    "window_start": window[0]["date"],
                    "window_end": window[-1]["date"],
                    "window_evaluation_status": (
                        "EXACT_COMPUTABLE" if complete else "NOT_COMPUTABLE_INCOMPLETE_LABEL_DOMAIN"
                    ),
                    "no_cross_season": True,
                    "window_total_kg": total,
                }
            )
    return output


def _support_identity_counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    base_ids = sorted({str(row["base_id"]) for row in rows})
    base_season_pairs = sorted({f"{row['base_id']}|{row['season']}" for row in rows})
    return {
        "row_or_origin_count": len(rows),
        "unique_base_count": len(base_ids),
        "unique_base_season_count": len(base_season_pairs),
        "base_season_ids_hash": canonical_value_hash(base_season_pairs),
    }


def build_support_count_evidence(
    daily_by_season: dict[str, list[dict[str, Any]]],
    window_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Report support counts without treating overlapping origins as samples."""

    by_season: dict[str, Any] = {}
    for season in SEASONS:
        known_daily = [row for row in daily_by_season[season] if row["label_known"]]
        season_windows = [row for row in window_rows if row["season"] == season]
        by_season[season] = {
            "daily_known_support": _support_identity_counts(known_daily),
            "W7": _support_identity_counts(
                [
                    row
                    for row in season_windows
                    if row["window_days"] == 7
                    and row["window_evaluation_status"] == "EXACT_COMPUTABLE"
                ]
            ),
            "W15": _support_identity_counts(
                [
                    row
                    for row in season_windows
                    if row["window_days"] == 15
                    and row["window_evaluation_status"] == "EXACT_COMPUTABLE"
                ]
            ),
        }
    return {
        "contract": {
            "daily_support_unit": "KNOWN_SUPPORT_DAILY_ROW",
            "W7_support_unit": "COMPLETE_W7_FORWARD_ORIGIN",
            "W15_support_unit": "COMPLETE_W15_FORWARD_ORIGIN",
            "overlapping_origins_are_not_independent_base_samples": True,
            "counts_are_reported_by_season": True,
        },
        "by_season": by_season,
    }


def _forward_support_population(
    kind: str,
    seasons: Sequence[str],
    daily_by_season: dict[str, list[dict[str, Any]]],
    window_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if kind == "daily_known_support":
        return [row for season in seasons for row in daily_by_season[season] if row["label_known"]]
    window_days = {"W7": 7, "W15": 15}[kind]
    return [
        row
        for row in window_rows
        if row["season"] in seasons
        and row["window_days"] == window_days
        and row["window_evaluation_status"] == "EXACT_COMPUTABLE"
    ]


def _forward_fold_metric(
    kind: str,
    train_seasons: Sequence[str],
    validation_seasons: Sequence[str],
    daily_by_season: dict[str, list[dict[str, Any]]],
    window_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    train_rows = _forward_support_population(kind, train_seasons, daily_by_season, window_rows)
    validation_rows = _forward_support_population(
        kind, validation_seasons, daily_by_season, window_rows
    )
    train_bases = {str(row["base_id"]) for row in train_rows}
    validation_bases = {str(row["base_id"]) for row in validation_rows}
    train_pairs = {f"{row['base_id']}|{row['season']}" for row in train_rows}
    validation_pairs = {f"{row['base_id']}|{row['season']}" for row in validation_rows}
    intersection = sorted(train_bases & validation_bases)
    is_daily = kind == "daily_known_support"
    return {
        "support_unit": (
            "KNOWN_SUPPORT_DAILY_ROW" if is_daily else f"COMPLETE_{kind}_FORWARD_ORIGIN"
        ),
        "train_seasons": train_seasons,
        "validation_seasons": validation_seasons,
        "train_origin_or_row_count": len(train_rows),
        "validation_origin_or_row_count": len(validation_rows),
        "train_row_count": len(train_rows) if is_daily else None,
        "validation_row_count": len(validation_rows) if is_daily else None,
        "train_origin_count": len(train_rows) if not is_daily else None,
        "validation_origin_count": len(validation_rows) if not is_daily else None,
        "train_unique_base_count": len(train_bases),
        "validation_unique_base_count": len(validation_bases),
        "train_unique_base_season_count": len(train_pairs),
        "validation_unique_base_season_count": len(validation_pairs),
        "train_validation_base_intersection_count": len(intersection),
        "train_validation_base_intersection_ids_hash": canonical_value_hash(intersection),
    }


def build_forward_fold_support(
    daily_by_season: dict[str, list[dict[str, Any]]],
    window_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    folds = [
        {
            "fold_id": "A",
            "train_seasons": ["2023-2024"],
            "validation_seasons": ["2024-2025"],
        },
        {
            "fold_id": "B",
            "train_seasons": ["2023-2024", "2024-2025"],
            "validation_seasons": ["2025-2026"],
        },
    ]
    output: list[dict[str, Any]] = []
    for fold in folds:
        train_seasons = fold["train_seasons"]
        validation_seasons = fold["validation_seasons"]
        output.append(
            {
                **fold,
                "metrics": {
                    kind: _forward_fold_metric(
                        kind,
                        train_seasons,
                        validation_seasons,
                        daily_by_season,
                        window_rows,
                    )
                    for kind in ("daily_known_support", "W7", "W15")
                },
            }
        )
    return {
        "contract": {
            "split_direction": "EARLIER_SEASON_TO_LATER_SEASON",
            "fold_selection_before_validation": True,
            "validation_labels_not_used_for_training_or_selection": True,
            "overlapping_origins_are_not_independent_base_samples": True,
        },
        "folds": output,
    }


def build_qualifications(
    inputs: dict[str, Any],
    source_calendars: dict[str, list[dict[str, Any]]],
    daily_by_season: dict[str, list[dict[str, Any]]],
    window_rows: list[dict[str, Any]],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    bases_by_id = {str(base["base_id"]): base for base in inputs["bases"]}
    audit_by_key: dict[tuple[str, str], dict[str, str]] = inputs["audit_by_key"]
    output: list[dict[str, Any]] = []
    for season in SEASONS:
        rows_by_base: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in daily_by_season[season]:
            rows_by_base[row["base_id"]].append(row)
        source_spec = inputs["source_specs"][season]
        source_start = date.fromisoformat(source_spec["date_min"])
        source_end = date.fromisoformat(source_spec["date_max"])
        for base_id in inputs["base_ids"]:
            base = bases_by_id[base_id]
            audit = audit_by_key[(season, base_id)]
            rows = rows_by_base[base_id]
            known = [row for row in rows if row["label_known"]]
            positive = [row for row in known if Decimal(row["observed_harvest_kg"]) > 0]
            unknown = [row for row in rows if not row["label_known"]]
            if positive:
                first_positive = positive[0]["date"]
                last_positive = positive[-1]["date"]
                active_start = date.fromisoformat(first_positive)
                active_end = date.fromisoformat(last_positive)
                active_unknown = sum(
                    row["label_state"] == "UNKNOWN_GLOBAL_NO_RECORD"
                    for row in rows
                    if active_start <= date.fromisoformat(row["date"]) <= active_end
                )
            else:
                first_positive = last_positive = ""
                active_unknown = 0
            source_margin_days = sum(
                not source_start <= date.fromisoformat(row["date"]) <= source_end for row in rows
            )
            global_unknown_days = sum(
                row["global_no_record_day"] for row in source_calendars[season]
            )
            all_labels_known = not unknown
            membership_complete = _member_complete(audit)
            area_valid = _area_valid(base)
            strict = (
                bool(config["sources"][season]["source_complete"])
                and bool(config["sources"][season]["ledger_zero_semantics_authorized"])
                and all_labels_known
                and membership_complete
                and area_valid
                and not global_unknown_days
                and not source_margin_days
            )
            tier = "COMPLETE" if strict else audit["coverage_status"]
            if tier not in {"COMPLETE", "PARTIAL", "BLOCKED"}:
                raise ValueError(f"unsupported coverage status: {tier}")
            if strict:
                completeness_status = "STRICT_ELIGIBLE"
            elif global_unknown_days or source_margin_days:
                completeness_status = "GLOBAL_UNKNOWN_BLOCKED"
            elif not area_valid:
                completeness_status = "AREA_MISSING"
            elif not membership_complete:
                completeness_status = "NOT_ELIGIBLE_OTHER"
            else:
                completeness_status = "NOT_ELIGIBLE_OTHER"
            windows = [
                row for row in window_rows if row["base_id"] == base_id and row["season"] == season
            ]
            w7_count = sum(
                row["window_evaluation_status"] == "EXACT_COMPUTABLE"
                for row in windows
                if row["window_days"] == 7
            )
            w15_count = sum(
                row["window_evaluation_status"] == "EXACT_COMPUTABLE"
                for row in windows
                if row["window_days"] == 15
            )
            reasons: list[str] = []
            if source_margin_days:
                reasons.append("SOURCE_NOT_COVERED_AT_BUSINESS_WINDOW_START")
            if global_unknown_days:
                reasons.append("GLOBAL_UNKNOWN_IN_BUSINESS_WINDOW")
            if not membership_complete:
                reasons.append("UNRESOLVED_MEMBER_FARMS")
            if not area_valid:
                reasons.append("AREA_AUTHORITY_INVALID_OR_MISSING")
            if not positive:
                reasons.append("NO_POSITIVE_KNOWN_BASE_LABEL")
            output.append(
                {
                    "base_id": base_id,
                    "canonical_base_name": base["canonical_base_name"],
                    "season": season,
                    "source_hash": source_spec["sha256"],
                    "coverage_start": season_window(season)[0].isoformat(),
                    "coverage_end": season_window(season)[1].isoformat(),
                    "source_coverage_start": source_spec["date_min"],
                    "source_coverage_end": source_spec["date_max"],
                    "source_complete": bool(config["sources"][season]["source_complete"]),
                    "active_span_first_positive_date": first_positive,
                    "active_span_last_positive_date": last_positive,
                    "active_span_global_unknown_days": active_unknown,
                    "global_unknown_days": global_unknown_days,
                    "source_margin_days": source_margin_days,
                    "ledger_zero_semantics_authorized": bool(
                        config["sources"][season]["ledger_zero_semantics_authorized"]
                    ),
                    "membership_complete": membership_complete,
                    "area_bound": area_valid,
                    "productive_area_mu": str(base["productive_area_mu"]),
                    "area_basis": base["area_review_status"],
                    "known_support_day_count": len(known),
                    "unknown_day_count": len(unknown),
                    "known_positive_day_count": len(positive),
                    "season_completeness_tier": tier,
                    "season_completeness_status": completeness_status,
                    "total_label_evaluable": strict,
                    "yield_label_evaluable": strict,
                    "daily_known_support_research_eligible": bool(known),
                    "peak_label_evaluable": strict,
                    "peak_evaluation_status": (
                        "EXACT_COMPUTABLE" if strict else "NOT_COMPUTABLE_INCOMPLETE_LABEL_DOMAIN"
                    ),
                    "w7_eligible_origin_count": w7_count,
                    "w15_eligible_origin_count": w15_count,
                    "shape_full_curve_evaluable": strict,
                    "exclusion_reasons": reasons,
                }
            )
    return output


def weather_join_audit(
    inputs: dict[str, Any], config: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    weather_ids: set[str] = set()
    date_sets: dict[str, set[str]] = defaultdict(set)
    weather_row_count = 0
    daily_path = inputs["weather_root"] / "daily.jsonl"
    with daily_path.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            base_id = str(row["base_id"])
            date_text = str(row["local_date"])
            if date_text in date_sets[base_id]:
                raise ValueError(f"duplicate weather base-day row: {base_id} {date_text}")
            weather_ids.add(base_id)
            date_sets[base_id].add(date_text)
            weather_row_count += 1
    registry_by_id = {str(base["base_id"]): base for base in inputs["bases"]}
    expected_ids = {
        base_id
        for base_id, base in registry_by_id.items()
        if base.get("region_scope") == "YUNNAN_CORE"
    }
    if weather_ids != expected_ids or weather_row_count != 32984:
        raise ValueError("weather base IDs do not equal the 38-base YUNNAN_CORE scope")
    rows: list[dict[str, Any]] = []
    for base_id in sorted(registry_by_id):
        base = registry_by_id[base_id]
        expected_dates = {
            day.isoformat() for season in SEASONS for day in dates_between(*season_window(season))
        }
        actual_dates = date_sets.get(base_id, set())
        in_scope = base.get("region_scope") == "YUNNAN_CORE"
        rows.append(
            {
                "base_id": base_id,
                "canonical_base_name": base["canonical_base_name"],
                "registry_region_scope": base.get("region_scope"),
                "weather_scope": "YUNNAN_CORE_38" if in_scope else "OUT_OF_SCOPE",
                "weather_base_id_present": base_id in weather_ids,
                "expected_daily_row_count": len(expected_dates) if in_scope else 0,
                "actual_daily_row_count": len(actual_dates),
                "date_coverage_status": (
                    "PASS"
                    if in_scope and actual_dates == expected_dates
                    else "OUT_OF_SCOPE_OR_MISMATCH"
                ),
                "join_status": (
                    "PASS_YUNNAN_CORE"
                    if in_scope and actual_dates == expected_dates
                    else "EXPLICIT_OUT_OF_WEATHER_SCOPE"
                    if not in_scope
                    else "BLOCKED"
                ),
            }
        )
    report = {
        "weather_data_join_feasible": True,
        "weather_base_id_parity": "PASS_38_YUNNAN_CORE_EXACT_IDS",
        "weather_business_date_coverage": "PASS_38_BASES_3_SEASONS_868_DAYS",
        "registry_bases_outside_weather_scope": [
            row["canonical_base_name"]
            for row in rows
            if row["join_status"] == "EXPLICIT_OUT_OF_WEATHER_SCOPE"
        ],
        "weather_daily_dataset_hash": config["weather"]["daily_dataset_hash"],
    }
    return rows, report


def build_outputs(config: dict[str, Any], inputs: dict[str, Any], output: Path) -> dict[str, Any]:
    if output.exists():
        raise ValueError("output directory must be new and append-only")
    source_calendars: dict[str, list[dict[str, Any]]] = {}
    daily_by_season: dict[str, list[dict[str, Any]]] = {}
    all_window_rows: list[dict[str, Any]] = []
    for season in SEASONS:
        source = inputs["source_specs"][season]
        source_start = date.fromisoformat(source["date_min"])
        source_end = date.fromisoformat(source["date_max"])
        calendar_rows = build_source_calendar(
            season, inputs["base_ids"], inputs["ledger_by_key"], source_start, source_end
        )
        source_calendars[season] = calendar_rows
        daily_by_season[season] = build_daily_eligibility(
            season,
            inputs["bases"],
            inputs["ledger_by_key"],
            calendar_rows,
            source_start,
            source_end,
        )
        all_window_rows.extend(build_window_rows(daily_by_season[season], season, 7))
        all_window_rows.extend(build_window_rows(daily_by_season[season], season, 15))

    qualifications = build_qualifications(
        inputs, source_calendars, daily_by_season, all_window_rows, config
    )
    peaks = [
        row
        for season in SEASONS
        for row in build_peak_rows(daily_by_season[season], inputs["bases"], season)
    ]
    weather_rows, weather_report = weather_join_audit(inputs, config)
    output.mkdir(parents=True, mode=0o700)

    source_manifest = {
        "task_id": config["task_id"],
        "evidence_revision": config.get("evidence_revision", "R1"),
        "input_authority": "CURRENT_ACTIVE_BASE_REGISTRY_AND_REVIEWED_BASE_DAILY_LEDGER",
        "input_files": inputs["files"],
        "registry_payload_hash": inputs["registry"]["hash"],
        "registry_source_hash": inputs["registry"]["source_hash"],
        "active_base_count": len(inputs["bases"]),
        "authorized_seasons": [
            {
                "season": season,
                "source_file_name": inputs["source_specs"][season]["file_name"],
                "source_hash": inputs["source_specs"][season]["sha256"],
                "source_date_min": inputs["source_specs"][season]["date_min"],
                "source_date_max": inputs["source_specs"][season]["date_max"],
                "source_complete": config["sources"][season]["source_complete"],
                "ledger_zero_semantics_authorized": config["sources"][season][
                    "ledger_zero_semantics_authorized"
                ],
            }
            for season in SEASONS
        ],
        "weather_join": weather_report,
        "weather_used_to_upgrade_label_eligibility": False,
        "raw_xls_rewritten": False,
    }
    write_json(output / "source-manifest.json", source_manifest)

    active_base_rows = []
    for base in inputs["bases"]:
        active_base_rows.append(
            {
                "base_id": base["base_id"],
                "canonical_base_name": base["canonical_base_name"],
                "covered_farms": "|".join(base.get("covered_farms", [])),
                "province": base.get("province") or "",
                "prefecture": base.get("prefecture") or "",
                "county": base.get("county") or "",
                "township": base.get("township") or "",
                "latitude": base.get("latitude") or "",
                "longitude": base.get("longitude") or "",
                "elevation_m": base.get("elevation_m") or "",
                "productive_area_mu": base.get("productive_area_mu") or "",
                "area_review_status": base.get("area_review_status") or "",
                "historical_seasons": "|".join(base.get("historical_seasons", [])),
                "historical_season_count": base.get("historical_season_count") or 0,
                "data_completeness_level": base.get("data_completeness_level") or "",
                "applicability_level": base.get("applicability_level") or "",
                "region_scope": base.get("region_scope") or "",
                "climate_zone_id": base.get("climate_zone_id") or "",
                "climate_zone_version": base.get("climate_zone_version") or "",
                "coordinate_review_status": base.get("coordinate_review_status") or "",
                "active": base.get("active"),
            }
        )
    write_csv(
        output / "active-base-universe.csv",
        active_base_rows,
        list(active_base_rows[0]),
    )

    qualification_fields = list(qualifications[0])
    write_csv(output / "qualification-matrix.csv", qualifications, qualification_fields)
    daily_rows = [row for season in SEASONS for row in daily_by_season[season]]
    write_csv(output / "daily-label-eligibility.csv", daily_rows, list(daily_rows[0]))
    write_csv(output / "peak-label-eligibility.csv", peaks, list(peaks[0]))
    write_csv(output / "window-label-eligibility.csv", all_window_rows, list(all_window_rows[0]))
    for season, rows in source_calendars.items():
        write_csv(output / f"source-active-calendar-{season}.csv", rows, list(rows[0]))
    write_csv(output / "weather-join-audit.csv", weather_rows, list(weather_rows[0]))

    support_counts = build_support_count_evidence(daily_by_season, all_window_rows)
    forward_fold_support = build_forward_fold_support(daily_by_season, all_window_rows)
    support_counts["evidence_revision"] = config.get("evidence_revision", "R1")
    forward_fold_support["evidence_revision"] = config.get("evidence_revision", "R1")
    write_json(output / "support-counts-by-season.json", support_counts)
    write_json(output / "forward-fold-support.json", forward_fold_support)

    missing_rows: list[dict[str, Any]] = []
    for row in qualifications:
        for reason in row["exclusion_reasons"]:
            missing_rows.append(
                {
                    "base_id": row["base_id"],
                    "canonical_base_name": row["canonical_base_name"],
                    "season": row["season"],
                    "evidence_code": reason,
                    "detail": "strict full-season eligibility remains false; no label was imputed",
                }
            )
    missing_rows.append(
        {
            "base_id": "base_36bc109841061a7798ed99a3",
            "canonical_base_name": "乡丰蓝莓基地",
            "season": "ALL",
            "evidence_code": "WEATHER_SCOPE_EXPLICIT_OUT_OF_YUNNAN",
            "detail": (
                "retained in 39-base Registry; excluded from 38-base YUNNAN_CORE weather join"
            ),
        }
    )
    write_csv(output / "missing-evidence.csv", missing_rows, list(missing_rows[0]))

    split_design = {
        "time_ordered_origin_split": {
            "defined": True,
            "origins": [
                {"train_seasons": ["2023-2024"], "validation_season": "2024-2025"},
                {"train_seasons": ["2023-2024", "2024-2025"], "validation_season": "2025-2026"},
            ],
            "selection_before_holdout": True,
            "overlapping_origins_are_not_independent_samples": True,
            "support_counts_file": "forward-fold-support.json",
        },
        "out_of_base_split": {
            "defined": True,
            "unit": "whole canonical base",
            "no_base_day_randomization": True,
        },
        "out_of_season_split": {
            "defined": True,
            "direction": "earlier_season_to_later_season",
        },
        "random_adjacent_day_split": {"defined": False, "allowed": False},
        "common_comparable_set": {
            "defined": True,
            "model_independent": True,
            "requires_same_label_domain_for_all_compared_models": True,
        },
        "extended_coverage_set": {
            "defined": True,
            "research_only": True,
            "known_support_is_not_full_season": True,
            "no_weather_extended_scope_max_base_count": EXPECTED_BASE_COUNT,
            "weather_common_comparable_scope_max_base_count": EXPECTED_WEATHER_BASE_COUNT,
        },
    }
    write_json(output / "split-design.json", split_design)
    metrics_contract = {
        "defined": True,
        "primary_aggregation": "base_equal_macro",
        "secondary_diagnostic": "kg_weighted_WAPE",
        "zero_denominator": "NOT_COMPUTABLE",
        "peak_tie_break": "earliest_date",
        "window_semantics": {"W7": "D+1..D+7", "W15": "D+1..D+15"},
        "business_cutoff": "04-15_inclusive;_04-16+_tail_out_of_scope",
        "metrics": [
            "yield_MAE_kg_per_mu",
            "yield_WAPE",
            "total_absolute_and_relative_error",
            "daily_MAE_kg",
            "daily_WAPE",
            "peak_date_and_quantity_error",
            "W7_date_and_quantity_error",
            "W15_date_and_quantity_error",
        ],
        "thresholds": "none_approved_in_this_freeze",
    }
    write_json(output / "metrics-contract.json", metrics_contract)

    tier_counts = Counter(row["season_completeness_tier"] for row in qualifications)
    status_counts = Counter(row["season_completeness_status"] for row in qualifications)
    daily_known = sum(row["label_known"] for row in daily_rows)
    daily_unknown = len(daily_rows) - daily_known
    global_unknown_by_season = {
        season: sum(row["global_no_record_day"] for row in source_calendars[season])
        for season in SEASONS
    }
    source_margin_by_season = {
        season: sum(
            not inputs["source_specs"][season]["date_min"]
            <= row["date"]
            <= inputs["source_specs"][season]["date_max"]
            for row in source_calendars[season]
        )
        for season in SEASONS
    }
    all_known_daily = [
        row for season in SEASONS for row in daily_by_season[season] if row["label_known"]
    ]
    all_w7_origins = [
        row
        for row in all_window_rows
        if row["window_days"] == 7 and row["window_evaluation_status"] == "EXACT_COMPUTABLE"
    ]
    all_w15_origins = [
        row
        for row in all_window_rows
        if row["window_days"] == 15 and row["window_evaluation_status"] == "EXACT_COMPUTABLE"
    ]
    daily_support = _support_identity_counts(all_known_daily)
    w7_support = _support_identity_counts(all_w7_origins)
    w15_support = _support_identity_counts(all_w15_origins)
    summary = {
        "task_id": config["task_id"],
        "evidence_revision": config.get("evidence_revision", "R1"),
        "current_active_base_count": len(inputs["bases"]),
        "current_base_registry_hash": inputs["registry"]["hash"],
        "active_base_universe_row_count": len(inputs["bases"]),
        "legacy_audit_base_count": config["legacy_audit_base_count"],
        "base_season_candidate_count": len(qualifications),
        "full_season_complete_count": tier_counts["COMPLETE"],
        "full_season_partial_count": tier_counts["PARTIAL"],
        "full_season_blocked_count": tier_counts["BLOCKED"],
        "full_season_total_label_eligible_count": sum(
            row["total_label_evaluable"] for row in qualifications
        ),
        "full_season_yield_label_eligible_count": sum(
            row["yield_label_evaluable"] for row in qualifications
        ),
        "daily_known_support_row_count": daily_known,
        "daily_unknown_row_count": daily_unknown,
        "daily_known_support_research_eligible": daily_known > 0,
        "daily_known_support_unique_base_count": daily_support["unique_base_count"],
        "daily_known_support_base_season_count": daily_support["unique_base_season_count"],
        "season_peak_label_eligible_count": sum(
            row["peak_label_evaluable"] for row in qualifications
        ),
        "W7_eligible_origin_count": sum(
            row["window_evaluation_status"] == "EXACT_COMPUTABLE"
            for row in all_window_rows
            if row["window_days"] == 7
        ),
        "W15_eligible_origin_count": sum(
            row["window_evaluation_status"] == "EXACT_COMPUTABLE"
            for row in all_window_rows
            if row["window_days"] == 15
        ),
        "full_season_total_eligible_unique_base_count": len(
            {row["base_id"] for row in qualifications if row["total_label_evaluable"]}
        ),
        "full_season_total_eligible_base_season_count": sum(
            row["total_label_evaluable"] for row in qualifications
        ),
        "W7_eligible_unique_base_count": w7_support["unique_base_count"],
        "W7_eligible_base_season_count": w7_support["unique_base_season_count"],
        "W15_eligible_unique_base_count": w15_support["unique_base_count"],
        "W15_eligible_base_season_count": w15_support["unique_base_season_count"],
        "support_counts_by_season_file": "support-counts-by-season.json",
        "forward_fold_support_file": "forward-fold-support.json",
        "no_weather_extended_scope_max_base_count": EXPECTED_BASE_COUNT,
        "weather_common_comparable_scope_max_base_count": EXPECTED_WEATHER_BASE_COUNT,
        "global_no_record_day_count_by_season": global_unknown_by_season,
        "source_not_covered_business_day_count_by_season": source_margin_by_season,
        "season_completeness_status_counts": dict(status_counts),
        "base_universe_reconciliation": (
            "PASS_39_ACTIVE_REGISTRY_EQUALS_LEGACY_AUDIT;_38_YUNNAN_CORE_WEATHER_SCOPE_"
            "EXPLICITLY_EXCLUDES_1_OUT_OF_YUNNAN_BASE"
        ),
        "weather_data_join_feasible": weather_report["weather_data_join_feasible"],
        "weather_base_id_parity": weather_report["weather_base_id_parity"],
        "weather_business_date_coverage": weather_report["weather_business_date_coverage"],
        "weather_used_to_upgrade_label_eligibility": False,
        "common_comparable_set_defined": True,
        "extended_coverage_set_defined": True,
        "out_of_base_split_defined": True,
        "out_of_season_split_defined": True,
        "time_ordered_origin_split_defined": True,
        "climate_zone_mapping_frozen": False,
        "S3_zone_baseline_training_authorized": False,
        "S3_total_yield_model_training_authorized": False,
        "S3_daily_model_training_authorized": False,
        "S4_weather_ablation_authorized": False,
        "model_training": False,
        "weather_features_generated": False,
        "legacy_test_accessed": False,
        "arrival_equals_harvest": True,
        "historical_data_only": True,
        "business_cutoff": "04-15_inclusive",
        "timezone": "Asia/Shanghai",
        "input_file_hashes": inputs["files"],
    }
    write_json(output / "summary.json", summary)
    artifact_hashes = {
        path.name: file_hash(path) for path in sorted(output.iterdir()) if path.is_file()
    }
    write_json(output / "artifact-manifest.json", artifact_hashes)
    return summary


def run(config_path: Path, registry_root: Path, weather_root: Path, output: Path) -> dict[str, Any]:
    config = read_json(config_path)
    if config.get("task_id") != "V0_5_S3_TRAINING_ELIGIBILITY_AND_EVALUATION_FREEZE_R1":
        raise ValueError("wrong S3 task configuration")
    inputs = load_inputs(config, registry_root, weather_root)
    return build_outputs(config, inputs, output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=Path("configs/v0_5_s3_training_eligibility_r1.json")
    )
    parser.add_argument("--registry-root", type=Path, required=True)
    parser.add_argument("--weather-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            run(args.config, args.registry_root, args.weather_root, args.output),
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
