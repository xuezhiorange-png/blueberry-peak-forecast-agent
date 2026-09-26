"""Apply explicit business-confirmed area scope without mutating S1 authority."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal, InvalidOperation

from backend.app.area_yield.v08_s4_original_area_recovery import deterministic_csv_bytes

TASK_ID = "V0_8_S4_USER_CONFIRMED_THREE_SEASON_AREA_AUTHORITY_APPLICATION_R1"
AREA_AUTHORITY_ID = "V0_8_THREE_SEASON_HISTORICAL_AREA_AUTHORITY_R1"
BUSINESS_CONFIRMATION_ID = TASK_ID
IDENTITY_AUTHORITY_ID = "CROSS_SEASON_BASE_IDENTITY_AUTHORITY_R1"
SEASONS = ("2023-2024", "2024-2025", "2025-2026")
TRAINING_SEASONS = frozenset({"2023-2024", "2024-2025"})
OOT_SEASON = "2025-2026"
BASE_COUNT = 39
CONFIRMED_TOTAL_AREA_MU = Decimal("41335")
EXPECTED_AREA_SOURCE_SHA256 = "73329a1f7315f81ce7cf24d59dc7b3a49507520cd179a205b7267a5b430db7d7"
EXPECTED_IDENTITY_AUTHORITY_SHA256 = (
    "7054c4168fac8342022527ab3ba017eb8e0b2c57409eb0e6dba166e6f181c61b"
)
EXPECTED_QUANTITY_AUTHORITY_SHA256 = (
    "64a0a41afcde4ffe3c8713f62ca5cc03ee0f36599289bafd409e641df0a2f2fd"
)

AREA_AUTHORITY_FIELDS = (
    "area_authority_id",
    "base_id",
    "canonical_base_name",
    "season",
    "historical_actual_area_mu",
    "area_status",
    "area_basis",
    "original_area_source_id",
    "original_area_source_sha256",
    "original_season_scope",
    "resolved_season_scope",
    "season_binding_basis",
    "business_confirmation_id",
    "identity_authority_id",
    "identity_authority_sha256",
    "authority_eligible",
)

ELIGIBILITY_FIELDS = (
    "base_id",
    "canonical_base_name",
    "season",
    "area_mu",
    "area_authority_status",
    "area_eligible",
    "season_total_quantity_kg",
    "quantity_authority_status",
    "season_total_complete",
    "quantity_eligible",
    "strict_training_eligible",
    "strict_oot_eligible",
    "exclusion_reason",
)

LEGACY_RECONCILIATION_FIELDS = (
    "legacy_record_id",
    "base_id",
    "canonical_base_name",
    "season",
    "legacy_grain",
    "old_area_mu",
    "new_confirmed_base_area_mu",
    "legacy_source_id",
    "legacy_source_sha256",
    "referenced_workbook_sha256",
    "original_area_document_recovered",
    "reconciliation_status",
)


def parse_area_decimal(value: str) -> Decimal:
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("AREA_VALUE_INVALID") from exc
    if not result.is_finite() or result < 0:
        raise ValueError("AREA_VALUE_INVALID")
    return result


def _validate_confirmation(confirmation: Mapping[str, object] | None) -> None:
    if confirmation is None:
        raise ValueError("EXPLICIT_BUSINESS_CONFIRMATION_REQUIRED")
    seasons = confirmation.get("seasons")
    if not isinstance(seasons, (list, tuple)):
        raise ValueError("BUSINESS_CONFIRMATION_CONTRACT_MISMATCH")
    if (
        confirmation.get("decision") != "USE_RECOVERED_39_BASE_41335_MU_FOR_ALL_THREE_SEASONS"
        or confirmation.get("decision_type") != "EXPLICIT_BUSINESS_CONFIRMATION"
        or confirmation.get("base_count") != BASE_COUNT
        or str(confirmation.get("total_area_mu")) != str(CONFIRMED_TOTAL_AREA_MU)
        or tuple(str(season) for season in seasons) != SEASONS
        or confirmation.get("area_values_same_across_seasons") is not True
        or confirmation.get("area_estimation") is not False
        or confirmation.get("cross_season_inference") is not False
        or confirmation.get("confirmation_record_id") != BUSINESS_CONFIRMATION_ID
    ):
        raise ValueError("BUSINESS_CONFIRMATION_CONTRACT_MISMATCH")


def validate_area_snapshot(
    source_rows: Sequence[Mapping[str, str]],
    canonical_bases: Iterable[Mapping[str, str]],
) -> Decimal:
    """Validate the exact 39-Base source snapshot and current identity binding."""
    if len(source_rows) != BASE_COUNT:
        raise ValueError("CONFIRMED_BASE_COUNT_MISMATCH")

    canonical_by_id: dict[str, str] = {}
    canonical_names: set[str] = set()
    for base in canonical_bases:
        base_id = base.get("base_id", "")
        base_name = base.get("canonical_base_name", base.get("base_name", ""))
        if not base_id or not base_name:
            continue
        existing = canonical_by_id.get(base_id)
        if existing is not None and existing != base_name:
            raise ValueError("CANONICAL_BASE_ID_CONFLICT")
        canonical_by_id[base_id] = base_name
        canonical_names.add(base_name)

    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    seen_source_ids: set[str] = set()
    total = Decimal(0)
    for row in source_rows:
        base_id = row.get("base_id", "")
        base_name = row.get("base_name", row.get("canonical_base_name", ""))
        source_id = row.get("source_record_id", row.get("recovery_record_id", ""))
        source_hash = row.get("source_sha256", row.get("source_file_sha256", ""))
        original_scope = row.get("original_season_scope", row.get("season_or_time_scope", ""))
        if not base_id or not base_name or not source_id or not source_hash:
            raise ValueError("AREA_SOURCE_PROVENANCE_MISSING")
        if base_id in seen_ids or base_name in seen_names or source_id in seen_source_ids:
            raise ValueError("DUPLICATE_CONFIRMED_BASE_AREA")
        seen_ids.add(base_id)
        seen_names.add(base_name)
        seen_source_ids.add(source_id)
        if source_hash != EXPECTED_AREA_SOURCE_SHA256:
            raise ValueError("AREA_SOURCE_HASH_MISMATCH")
        if original_scope != "CURRENT/UNSPECIFIED":
            raise ValueError("ORIGINAL_AREA_SCOPE_CHANGED")
        canonical_name = canonical_by_id.get(base_id)
        if (
            canonical_name is None
            or canonical_name != base_name
            or base_name not in canonical_names
        ):
            raise ValueError("BASE_IDENTITY_UNRESOLVED")
        total += parse_area_decimal(row.get("area_mu", ""))

    if len(seen_ids) != BASE_COUNT or len(canonical_by_id) != BASE_COUNT:
        raise ValueError("BASE_IDENTITY_SET_INCOMPLETE")
    if total != CONFIRMED_TOTAL_AREA_MU:
        raise ValueError("CONFIRMED_AREA_TOTAL_MISMATCH")
    return total


def build_area_authority_rows(
    source_rows: Sequence[Mapping[str, str]],
    canonical_bases: Iterable[Mapping[str, str]],
    confirmation: Mapping[str, object] | None,
    *,
    identity_authority_id: str,
    identity_authority_sha256: str,
    business_confirmation_sha256: str | None = None,
) -> list[dict[str, str]]:
    _validate_confirmation(confirmation)
    if identity_authority_id != IDENTITY_AUTHORITY_ID:
        raise ValueError("IDENTITY_AUTHORITY_ID_MISMATCH")
    if identity_authority_sha256 != EXPECTED_IDENTITY_AUTHORITY_SHA256:
        raise ValueError("IDENTITY_AUTHORITY_HASH_MISMATCH")
    validate_area_snapshot(source_rows, canonical_bases)

    season_scope = ";".join(SEASONS)
    rows: list[dict[str, str]] = []
    for source in source_rows:
        source_id = source.get("source_record_id", source.get("recovery_record_id", ""))
        source_hash = source.get("source_sha256", source.get("source_file_sha256", ""))
        source_scope = source.get("original_season_scope", source.get("season_or_time_scope", ""))
        area_value = str(parse_area_decimal(source.get("area_mu", "")))
        if business_confirmation_sha256 is not None and not _valid_sha(
            business_confirmation_sha256
        ):
            raise ValueError("BUSINESS_CONFIRMATION_HASH_INVALID")
        if not _valid_sha(source_hash):
            raise ValueError("AREA_SOURCE_HASH_INVALID")
        for season in SEASONS:
            rows.append(
                {
                    "area_authority_id": AREA_AUTHORITY_ID,
                    "base_id": source["base_id"],
                    "canonical_base_name": source.get(
                        "base_name", source.get("canonical_base_name", "")
                    ),
                    "season": season,
                    "historical_actual_area_mu": area_value,
                    "area_status": "BUSINESS_CONFIRMED_HISTORICAL_ACTUAL",
                    "area_basis": "USER_CONFIRMED_THREE_SEASON_AREA_SNAPSHOT",
                    "original_area_source_id": source_id,
                    "original_area_source_sha256": source_hash,
                    "original_season_scope": source_scope,
                    "resolved_season_scope": season_scope,
                    "season_binding_basis": "EXPLICIT_BUSINESS_CONFIRMATION",
                    "business_confirmation_id": BUSINESS_CONFIRMATION_ID,
                    "business_confirmation_sha256": business_confirmation_sha256 or "",
                    "identity_authority_id": identity_authority_id,
                    "identity_authority_sha256": identity_authority_sha256,
                    "authority_eligible": "true",
                }
            )
    if len(rows) != BASE_COUNT * len(SEASONS):
        raise ValueError("BASE_SEASON_ROW_COUNT_MISMATCH")
    return rows


def build_quantity_eligibility_rows(
    area_rows: Sequence[Mapping[str, str]],
    quality_rows: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    area_index = {(row.get("base_id", ""), row.get("season", "")): row for row in area_rows}
    quantity_index = {(row.get("base_id", ""), row.get("season", "")): row for row in quality_rows}
    if (
        len(area_index) != len(area_rows)
        or len(quantity_index) != len(quality_rows)
        or set(area_index) != set(quantity_index)
        or len(area_index) != BASE_COUNT * len(SEASONS)
    ):
        raise ValueError("QUANTITY_AUTHORITY_KEYSET_MISMATCH")

    output: list[dict[str, str]] = []
    for key in sorted(area_index):
        area = area_index[key]
        quantity = quantity_index[key]
        if area.get("canonical_base_name") != quantity.get("canonical_base_name"):
            raise ValueError("AREA_QUANTITY_BASE_NAME_MISMATCH")
        area_eligible = (
            area.get("area_status") == "BUSINESS_CONFIRMED_HISTORICAL_ACTUAL"
            and area.get("authority_eligible") == "true"
        )
        q_status = quantity.get("business_total_coverage_status", "")
        total_complete = quantity.get("season_total_complete", "").lower() == "true"
        quantity_eligible = q_status == "BUSINESS_TOTAL_AUTHORITY_ELIGIBLE" and total_complete
        season = key[1]
        strict_training = area_eligible and quantity_eligible and season in TRAINING_SEASONS
        strict_oot = area_eligible and quantity_eligible and season == OOT_SEASON
        if not area_eligible:
            reason = "AREA_AUTHORITY_MISSING"
        elif not quantity_eligible:
            reason = "COMPLETE_SEASON_TOTAL_AUTHORITY_MISSING"
        elif season not in TRAINING_SEASONS:
            reason = "NOT_TRAINING_SEASON"
        else:
            reason = "ELIGIBLE"

        output.append(
            {
                "base_id": key[0],
                "canonical_base_name": area.get("canonical_base_name", ""),
                "season": season,
                "area_mu": area.get("historical_actual_area_mu", ""),
                "area_authority_status": area.get("area_status", ""),
                "area_eligible": str(area_eligible).lower(),
                "season_total_quantity_kg": (
                    quantity.get("business_window_mapped_quantity_kg", "")
                    if quantity_eligible
                    else ""
                ),
                "quantity_authority_status": q_status,
                "season_total_complete": str(total_complete).lower(),
                "quantity_eligible": str(quantity_eligible).lower(),
                "strict_training_eligible": str(strict_training).lower(),
                "strict_oot_eligible": str(strict_oot).lower(),
                "exclusion_reason": reason,
            }
        )
    return output


def reconcile_legacy_area_evidence(
    legacy_rows: Sequence[Mapping[str, str]],
    area_rows: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    area_index = {(row["base_id"], row["season"]): row for row in area_rows}
    output: list[dict[str, str]] = []
    for legacy in legacy_rows:
        base_id = legacy.get("base_id", "")
        season = legacy.get("season", "")
        authority = area_index.get((base_id, season))
        if authority is None:
            raise ValueError("LEGACY_AREA_BASE_SEASON_UNBOUND")
        old_value = parse_area_decimal(legacy.get("old_area_mu", ""))
        new_value = parse_area_decimal(authority["historical_actual_area_mu"])
        grain = legacy.get("grain", "").upper()
        if grain == "BASE":
            status = (
                "CONSISTENT_WITH_THREE_SEASON_BUSINESS_CONFIRMATION"
                if old_value == new_value
                else "LEGACY_AREA_EVIDENCE_SUPERSEDED_BY_EXPLICIT_BUSINESS_CONFIRMATION"
            )
        elif grain == "MEMBER":
            status = (
                "MEMBER_AREA_SUPPORTING_DETAIL"
                if old_value <= new_value
                else "MEMBER_AREA_EXCEEDS_CONFIRMED_BASE_AREA_BLOCKER"
            )
        else:
            raise ValueError("LEGACY_AREA_GRAIN_INVALID")
        output.append(
            {
                "legacy_record_id": legacy.get("legacy_record_id", ""),
                "base_id": base_id,
                "canonical_base_name": authority["canonical_base_name"],
                "season": season,
                "legacy_grain": grain,
                "old_area_mu": str(old_value),
                "new_confirmed_base_area_mu": str(new_value),
                "legacy_source_id": legacy.get("source_id", ""),
                "legacy_source_sha256": legacy.get("source_sha256", ""),
                "referenced_workbook_sha256": legacy.get("referenced_workbook_sha256", ""),
                "original_area_document_recovered": legacy.get(
                    "original_area_document_recovered", "false"
                ),
                "reconciliation_status": status,
            }
        )
    return sorted(output, key=lambda row: (row["base_id"], row["season"], row["legacy_grain"]))


def serialize_csv_rows(rows: Sequence[Mapping[str, str]], fields: Sequence[str]) -> bytes:
    normalized = [dict(row) for row in rows]
    return deterministic_csv_bytes(fields, normalized)


def _valid_sha(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)
