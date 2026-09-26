"""Apply the explicitly confirmed no-harvest-row-is-zero rule to frozen S1 rows.

This is a non-destructive overlay. A zero is applied only when the frozen
season source is verified, the canonical Base has an accepted and complete
identity set for that season, and no mapped source row exists for the day.
Unresolved source identities, source gaps, and missing source bindings remain
unknown. Missing accepted members on an otherwise identity-complete partial
day contribute zero under the same explicit business rule.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from backend.app.area_yield.v08_s2_model_comparison import daily_quantity_eligibility

ZERO_BASIS = "EXPLICIT_BUSINESS_RULE_NO_HARVEST_RECORD_MEANS_ZERO"
AUTHORIZED_ZERO_STATUS = "AUTHORIZED_ZERO"
IDENTITY_CONFIRMED = "IDENTITY_CONFIRMED"
IDENTITY_WITH_UNRESOLVED = "IDENTITY_CONFIRMED_WITH_UNRESOLVED_CANDIDATES"
IDENTITY_UNRESOLVED = "IDENTITY_UNRESOLVED"
NO_ACCEPTED_IDENTITY = "NO_ACCEPTED_SOURCE_ROWS"


class NoRecordZeroSemanticsError(ValueError):
    """Raised when a frozen input cannot support a safe semantic overlay."""


def _decimal(value: Any, *, field: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise NoRecordZeroSemanticsError(f"INVALID_DECIMAL:{field}") from exc
    if not number.is_finite():
        raise NoRecordZeroSemanticsError(f"NONFINITE_DECIMAL:{field}")
    return number


def _json_labels(value: Any, *, field: str) -> list[str]:
    try:
        parsed = json.loads(str(value or "[]"))
    except (TypeError, json.JSONDecodeError) as exc:
        raise NoRecordZeroSemanticsError(f"INVALID_JSON_LIST:{field}") from exc
    if not isinstance(parsed, list) or any(not isinstance(item, str) for item in parsed):
        raise NoRecordZeroSemanticsError(f"INVALID_JSON_LIST:{field}")
    return parsed


def _as_bool(value: Any) -> bool:
    return str(value).strip().lower() == "true"


def _as_int(value: Any, *, field: str) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError) as exc:
        raise NoRecordZeroSemanticsError(f"INVALID_INTEGER:{field}") from exc
    if parsed < 0:
        raise NoRecordZeroSemanticsError(f"NEGATIVE_INTEGER:{field}")
    return parsed


def _date(value: Any) -> date:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise NoRecordZeroSemanticsError("INVALID_DAILY_DATE") from exc


def _is_null(value: Any) -> bool:
    return value is None or str(value).strip() in {"", "null", "None"}


def apply_no_record_zero_semantics(
    *,
    daily_rows: Sequence[Mapping[str, Any]],
    quality_rows: Sequence[Mapping[str, Any]],
    boundaries: Mapping[str, tuple[date, date]],
    source_hashes: Mapping[str, str],
    expected_base_count: int = 39,
) -> dict[str, Any]:
    """Create S6 private-overlay rows without changing any frozen source rows."""

    quality_by_key: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in quality_rows:
        quality_key = (str(row.get("base_id", "")), str(row.get("season", "")))
        if not all(quality_key):
            raise NoRecordZeroSemanticsError("QUALITY_IDENTITY_MISSING")
        if quality_key in quality_by_key:
            raise NoRecordZeroSemanticsError("DUPLICATE_QUALITY_IDENTITY")
        quality_by_key[quality_key] = row

    bases = {base_id for base_id, _season in quality_by_key}
    if len(bases) != expected_base_count:
        raise NoRecordZeroSemanticsError("CANONICAL_BASE_COUNT_MISMATCH")
    if {season for _base_id, season in quality_by_key} != set(boundaries):
        raise NoRecordZeroSemanticsError("QUALITY_SEASON_SCOPE_MISMATCH")

    daily_by_key: dict[tuple[str, str, date], Mapping[str, Any]] = {}
    for row in daily_rows:
        base_id = str(row.get("base_id", ""))
        season = str(row.get("season", ""))
        day = _date(row.get("date"))
        daily_key = (base_id, season, day)
        if not base_id or (base_id, season) not in quality_by_key:
            raise NoRecordZeroSemanticsError("DAILY_IDENTITY_OUTSIDE_QUALITY_SCOPE")
        if daily_key in daily_by_key:
            raise NoRecordZeroSemanticsError("DUPLICATE_CANONICAL_DAILY_ROW")
        if season not in boundaries:
            raise NoRecordZeroSemanticsError("DAILY_SEASON_BOUNDARY_MISSING")
        start, end = boundaries[season]
        if not start <= day <= end:
            raise NoRecordZeroSemanticsError("DAILY_ROW_OUTSIDE_FROZEN_WINDOW")
        expected_hash = source_hashes.get(season, "")
        if not expected_hash or str(row.get("source_sha256", "")) != expected_hash:
            raise NoRecordZeroSemanticsError("DAILY_SOURCE_HASH_MISMATCH")
        daily_by_key[daily_key] = row

    expected_keys: set[tuple[str, str, date]] = set()
    for (base_id, season), _quality in quality_by_key.items():
        start, end = boundaries[season]
        day = start
        while day <= end:
            expected_keys.add((base_id, season, day))
            day += timedelta(days=1)
    if not set(daily_by_key).issubset(expected_keys):
        raise NoRecordZeroSemanticsError("DAILY_ROW_OUTSIDE_EXPECTED_BASE_DAY_UNIVERSE")

    converted_no_record = 0
    partial_resolved = 0
    unknown_categories: Counter[str] = Counter()
    partial_categories: Counter[str] = Counter()
    season_counts: dict[str, Counter[str]] = {season: Counter() for season in boundaries}
    overlay_rows: list[dict[str, str]] = []
    unknown_rows: list[dict[str, str]] = []
    partial_rows: list[dict[str, str]] = []
    transformed_daily_rows: list[dict[str, str]] = []

    for base_day_key in sorted(expected_keys, key=lambda item: (item[1], item[0], item[2])):
        base_id, season, day = base_day_key
        quality = quality_by_key[(base_id, season)]
        source_row = daily_by_key.get(base_day_key)
        start, end = boundaries[season]
        accepted_labels = _json_labels(
            quality.get("accepted_source_labels"), field="accepted_source_labels"
        )
        unresolved_labels = _json_labels(
            quality.get("unresolved_candidate_source_labels"),
            field="unresolved_candidate_source_labels",
        )
        identity_status = str(quality.get("source_identity_status", ""))
        accepted_count = _as_int(
            quality.get("accepted_source_label_count", "0"),
            field="accepted_source_label_count",
        )
        if len(accepted_labels) != accepted_count or len(set(accepted_labels)) != len(
            accepted_labels
        ):
            raise NoRecordZeroSemanticsError("ACCEPTED_MEMBER_UNIVERSE_INVALID")
        identity_resolved = (
            identity_status == IDENTITY_CONFIRMED and accepted_count > 0 and not unresolved_labels
        )

        if source_row is None:
            source_row = {
                "base_id": base_id,
                "canonical_base_name": str(quality.get("canonical_base_name", "")),
                "season": season,
                "source_sha256": source_hashes.get(season, ""),
                "date": day.isoformat(),
                "scope": "BUSINESS_WINDOW",
                "quantity_status": "UNKNOWN",
                "mapped_observed_subtotal_kg": "",
                "quantity_completeness_status": "UNKNOWN_NOT_ZERO_FILLED",
                "unknown_component_possible": "true",
                "source_row_count": "0",
                "contributing_source_label_count": "0",
                "confirmed_zero_basis": "",
                "identity_authority_id": str(quality.get("identity_authority_id", "")),
                "identity_authority_sha256": str(quality.get("identity_authority_sha256", "")),
            }
            canonical_row_exists = False
        else:
            source_row = {
                str(name): str(value) if value is not None else ""
                for name, value in source_row.items()
            }
            canonical_row_exists = True

        old_status = str(source_row.get("quantity_status", ""))
        old_completeness = str(source_row.get("quantity_completeness_status", ""))
        old_quantity = source_row.get("mapped_observed_subtotal_kg", "")
        source_count = _as_int(source_row.get("source_row_count", "0"), field="source_row_count")
        contributing_count = _as_int(
            source_row.get("contributing_source_label_count", "0"),
            field="contributing_source_label_count",
        )
        if contributing_count > accepted_count or (source_count == 0 and contributing_count > 0):
            raise NoRecordZeroSemanticsError("DAILY_MEMBER_ROW_COUNTS_INCONSISTENT")
        if source_count > 0 and contributing_count == 0:
            raise NoRecordZeroSemanticsError("SOURCE_ROWS_WITHOUT_CONTRIBUTING_IDENTITY")

        new_status = old_status
        new_completeness = old_completeness
        new_quantity = old_quantity
        zero_applied = False
        partial_was_resolved = False
        reason = "UNCHANGED_EXISTING_AUTHORITY"
        conflict = bool(unresolved_labels) or identity_status in {
            IDENTITY_WITH_UNRESOLVED,
            IDENTITY_UNRESOLVED,
        }

        if old_status == "UNKNOWN":
            if not _is_null(old_quantity) or old_completeness != "UNKNOWN_NOT_ZERO_FILLED":
                raise NoRecordZeroSemanticsError("UNKNOWN_ROW_QUANTITY_OR_COMPLETENESS_INVALID")
            if not canonical_row_exists:
                category = "SOURCE_DATE_NOT_COVERED"
                reason = "CANONICAL_DAILY_ROW_MISSING"
            elif source_count > 0:
                category = "SOURCE_ROW_PRESENT_BUT_PARTIAL"
                reason = "UNKNOWN_WITH_SOURCE_ROWS"
            elif not identity_resolved and conflict:
                category = "IDENTITY_UNRESOLVED"
                reason = "UNRESOLVED_SOURCE_IDENTITY_MAY_CONFLICT_WITH_BASE_DAY"
            elif not identity_resolved and identity_status == NO_ACCEPTED_IDENTITY:
                category = "OTHER_TRUE_UNKNOWN"
                reason = "NO_ACCEPTED_SOURCE_IDENTITY_FOR_BASE_SEASON"
            elif not identity_resolved:
                category = "OTHER_TRUE_UNKNOWN"
                reason = "BASE_SEASON_IDENTITY_NOT_COMPLETE"
            else:
                category = "NO_HARVEST_RECORD"
                reason = "VERIFIED_SEASON_SOURCE_HAS_NO_BASE_DAY_HARVEST_ROW"
                new_status = "CONFIRMED_ZERO"
                new_completeness = AUTHORIZED_ZERO_STATUS
                new_quantity = "0"
                zero_applied = True
                converted_no_record += 1
            unknown_categories[category] += 1
            season_counts[season][f"unknown_{category.lower()}"] += 1
            unknown_rows.append(
                {
                    "base_id": base_id,
                    "base_name": str(quality.get("canonical_base_name", "")),
                    "season": season,
                    "date": day.isoformat(),
                    "old_quantity_status": old_status
                    if canonical_row_exists
                    else "NO_CANONICAL_DAILY_ROW",
                    "old_completeness_status": old_completeness
                    if canonical_row_exists
                    else "NO_ROW",
                    "source_row_exists": str(source_count > 0).lower(),
                    "source_quantity_row_count": str(source_count),
                    "identity_resolved": str(identity_resolved).lower(),
                    "member_coverage_status": (
                        "NO_MEMBER_ROWS" if source_count == 0 else "SOURCE_ROWS_PRESENT"
                    ),
                    "source_coverage_status": (
                        "VERIFIED_SEASON_SOURCE_HASH"
                        if canonical_row_exists
                        else "CANONICAL_ROW_MISSING"
                    ),
                    "unknown_reason_before": reason,
                    "eligible_for_no_record_zero": str(zero_applied).lower(),
                    "new_quantity_status": new_status,
                    "new_completeness_status": new_completeness,
                    "new_quantity_kg": new_quantity or "null",
                    "evidence": (
                        f"s1_source_sha256={source_row.get('source_sha256', '')};"
                        f"identity_status={identity_status};accepted_member_count={accepted_count};"
                        f"unresolved_candidate_count={len(unresolved_labels)}"
                    ),
                }
            )
        elif old_status == "KNOWN_MAPPED_SUBTOTAL":
            quantity = _decimal(old_quantity, field="mapped_observed_subtotal_kg")
            if quantity < 0:
                raise NoRecordZeroSemanticsError("NEGATIVE_DAILY_QUANTITY")
            if old_completeness == "PARTIAL_KNOWN_SUBTOTAL":
                if identity_resolved and source_count > 0 and contributing_count > 0:
                    missing_count = accepted_count - contributing_count
                    if missing_count <= 0:
                        raise NoRecordZeroSemanticsError("PARTIAL_ROW_HAS_NO_MISSING_MEMBERS")
                    new_completeness = "COMPLETE_MAPPED_MEMBERS"
                    new_status = "KNOWN_MAPPED_SUBTOTAL"
                    source_row["unknown_component_possible"] = "false"
                    partial_was_resolved = True
                    partial_resolved += 1
                    reason = "KNOWN_MISSING_MEMBERS_HAVE_NO_HARVEST_ROWS"
                    partial_categories["RESOLVED_BY_NO_RECORD_ZERO"] += 1
                elif conflict:
                    reason = "UNRESOLVED_SOURCE_IDENTITY_MAY_CONFLICT_WITH_MISSING_MEMBER"
                    partial_categories["IDENTITY_UNRESOLVED"] += 1
                else:
                    reason = "PARTIAL_MEMBER_OR_SOURCE_COVERAGE_NOT_PROVEN"
                    partial_categories["SOURCE_COVERAGE_INCOMPLETE"] += 1
                partial_rows.append(
                    {
                        "base_id": base_id,
                        "base_name": str(quality.get("canonical_base_name", "")),
                        "season": season,
                        "date": day.isoformat(),
                        "known_quantity_kg": format(quantity, "f"),
                        "accepted_member_count": str(accepted_count),
                        "contributing_member_count": str(contributing_count),
                        "missing_member_count": str(max(accepted_count - contributing_count, 0)),
                        "identity_resolved": str(identity_resolved).lower(),
                        "identity_unresolved_conflict": str(conflict).lower(),
                        "source_row_count": str(source_count),
                        "old_completeness_status": old_completeness,
                        "new_completeness_status": new_completeness,
                        "resolution_status": (
                            "COMPLETE_MAPPED_MEMBERS"
                            if partial_was_resolved
                            else "RETAINED_PARTIAL"
                        ),
                        "resolution_reason": reason,
                    }
                )
        elif old_status == "CONFIRMED_ZERO":
            eligibility, _reason = daily_quantity_eligibility(
                status=old_status,
                completeness_status=old_completeness,
                raw_quantity=old_quantity,
            )
            if eligibility != "SCORED_COMPLETE":
                raise NoRecordZeroSemanticsError("EXISTING_CONFIRMED_ZERO_NOT_AUTHORIZED")
        elif old_status == "EXCLUDED":
            reason = "EXCLUDED_RECORD_PRESERVED_NOT_ZEROED"
        else:
            raise NoRecordZeroSemanticsError(f"UNSUPPORTED_DAILY_QUANTITY_STATUS:{old_status}")

        if zero_applied:
            source_row["confirmed_zero_basis"] = ZERO_BASIS
        source_row["quantity_status"] = new_status
        source_row["quantity_completeness_status"] = new_completeness
        source_row["mapped_observed_subtotal_kg"] = (
            "" if _is_null(new_quantity) else str(new_quantity)
        )
        source_row["unknown_component_possible"] = (
            "false"
            if zero_applied or partial_was_resolved
            else source_row.get("unknown_component_possible", "true")
        )
        try:
            day_eligibility, _day_reason = daily_quantity_eligibility(
                status=new_status,
                completeness_status=new_completeness,
                raw_quantity=source_row.get("mapped_observed_subtotal_kg"),
            )
        except ValueError:
            day_eligibility = "EXCLUDED_UNKNOWN"
        daily_authorized = (
            day_eligibility == "SCORED_COMPLETE" and identity_resolved and not conflict
        )
        transformed_daily_rows.append(source_row)
        overlay_rows.append(
            {
                "base_id": base_id,
                "base_name": str(quality.get("canonical_base_name", "")),
                "season": season,
                "date": day.isoformat(),
                "old_quantity_status": old_status
                if canonical_row_exists
                else "NO_CANONICAL_DAILY_ROW",
                "old_completeness_status": old_completeness if canonical_row_exists else "NO_ROW",
                "old_quantity_kg": old_quantity if not _is_null(old_quantity) else "null",
                "new_quantity_status": new_status,
                "new_completeness_status": new_completeness,
                "new_quantity_kg": source_row.get("mapped_observed_subtotal_kg") or "null",
                "zero_applied": str(zero_applied).lower(),
                "zero_basis": ZERO_BASIS if zero_applied else "",
                "partial_resolved": str(partial_was_resolved).lower(),
                "source_row_count": str(source_count),
                "member_expected_count": str(accepted_count),
                "member_observed_count": str(contributing_count),
                "identity_unresolved_conflict": str(conflict).lower(),
                "authority_eligible_daily": str(daily_authorized).lower(),
                "source_coverage_status": "VERIFIED_SEASON_SOURCE_HASH"
                if canonical_row_exists
                else "CANONICAL_ROW_MISSING",
                "resolution_reason": reason,
            }
        )

    if len(overlay_rows) != len(expected_keys):
        raise NoRecordZeroSemanticsError("EXPECTED_BASE_DAY_UNIVERSE_NOT_MATERIALIZED")
    if len(transformed_daily_rows) != len(expected_keys):
        raise NoRecordZeroSemanticsError("TRANSFORMED_DAILY_SCOPE_COUNT_MISMATCH")

    before_counts = Counter(str(row.get("quantity_status", "")) for row in daily_rows)
    after_counts = Counter(str(row.get("quantity_status", "")) for row in transformed_daily_rows)
    counts = {
        "expected_base_day_count": len(expected_keys),
        "unknown_day_count_before": before_counts["UNKNOWN"],
        "missing_canonical_daily_row_count_before": len(expected_keys) - len(daily_by_key),
        "unknown_no_record_day_count": unknown_categories["NO_HARVEST_RECORD"],
        "unknown_identity_unresolved_day_count": unknown_categories["IDENTITY_UNRESOLVED"],
        "unknown_source_row_present_partial_day_count": unknown_categories[
            "SOURCE_ROW_PRESENT_BUT_PARTIAL"
        ],
        "unknown_source_date_not_covered_day_count": unknown_categories["SOURCE_DATE_NOT_COVERED"],
        "unknown_source_unavailable_day_count": unknown_categories["SOURCE_UNAVAILABLE"],
        "unknown_other_day_count": unknown_categories["OTHER_TRUE_UNKNOWN"],
        "zero_converted_from_no_record_count": converted_no_record,
        "unknown_day_count_after": after_counts["UNKNOWN"],
        "confirmed_zero_day_count_before": before_counts["CONFIRMED_ZERO"],
        "confirmed_zero_day_count_after": after_counts["CONFIRMED_ZERO"],
        "partial_day_count_before": sum(
            row.get("quantity_status") == "KNOWN_MAPPED_SUBTOTAL"
            and row.get("quantity_completeness_status") == "PARTIAL_KNOWN_SUBTOTAL"
            for row in daily_rows
        ),
        "partial_resolved_by_zero_count": partial_resolved,
        "partial_still_identity_unresolved_count": partial_categories["IDENTITY_UNRESOLVED"],
        "partial_still_source_coverage_incomplete_count": partial_categories[
            "SOURCE_COVERAGE_INCOMPLETE"
        ],
        "partial_day_count_after": sum(
            row.get("quantity_status") == "KNOWN_MAPPED_SUBTOTAL"
            and row.get("quantity_completeness_status") == "PARTIAL_KNOWN_SUBTOTAL"
            for row in transformed_daily_rows
        ),
        "per_season": {
            season: dict(sorted(season_counts[season].items())) for season in sorted(boundaries)
        },
    }
    if counts["unknown_day_count_before"] + counts["missing_canonical_daily_row_count_before"] != (
        counts["zero_converted_from_no_record_count"] + counts["unknown_day_count_after"]
    ):
        raise NoRecordZeroSemanticsError("UNKNOWN_RECLASSIFICATION_CONSERVATION_FAILED")
    if counts["partial_day_count_before"] != (
        counts["partial_resolved_by_zero_count"] + counts["partial_day_count_after"]
    ):
        raise NoRecordZeroSemanticsError("PARTIAL_RECLASSIFICATION_CONSERVATION_FAILED")
    return {
        "overlay_rows": overlay_rows,
        "unknown_decomposition_rows": unknown_rows,
        "partial_resolution_rows": partial_rows,
        "transformed_daily_rows": transformed_daily_rows,
        "counts": counts,
    }


def apply_s6_season_total_authority(
    *,
    quantity_outputs: dict[str, Any],
    quality_rows: Sequence[Mapping[str, Any]],
    area_rows: Sequence[Mapping[str, Any]],
    training_seasons: frozenset[str],
    oot_season: str,
) -> dict[str, Any]:
    """Close season totals after S6 has authorized zero for absent members.

    S5's unchanged member counter sees that no raw member row exists and thus
    leaves a resolved partial-day season ineligible. This S6-only overlay
    recognizes that specific case only when every expected day is now complete,
    identity is confirmed with no unresolved candidates, the frozen boundary is
    complete, and the daily total reconciles exactly to the S1 Base-season
    mapped quantity. It does not alter S5 or S1 artifacts.
    """

    quality_by_key = {
        (str(row.get("base_id", "")), str(row.get("season", ""))): row for row in quality_rows
    }
    area_by_key = {
        (str(row.get("base_id", "")), str(row.get("season", ""))): row for row in area_rows
    }
    completeness_rows = quantity_outputs["completeness_rows"]
    eligibility_rows = quantity_outputs["eligibility_rows"]
    overlays = quantity_outputs["quantity_overlay_rows"]
    if not (len(completeness_rows) == len(eligibility_rows) == len(overlays)):
        raise NoRecordZeroSemanticsError("S6_SEASON_TOTAL_SCOPE_COUNT_MISMATCH")
    completeness_by_key = {(row["base_id"], row["season"]): row for row in completeness_rows}
    if len(completeness_by_key) != len(completeness_rows):
        raise NoRecordZeroSemanticsError("DUPLICATE_S6_BASE_SEASON_COMPLETENESS")

    for row in completeness_rows:
        key = (row["base_id"], row["season"])
        quality = quality_by_key.get(key)
        if quality is None or key not in area_by_key:
            raise NoRecordZeroSemanticsError("S6_BASE_SEASON_AUTHORITY_MISSING")
        identity_confirmed = (
            quality.get("source_identity_status") == IDENTITY_CONFIRMED
            and not _json_labels(
                quality.get("unresolved_candidate_source_labels"),
                field="unresolved_candidate_source_labels",
            )
            and _as_int(
                quality.get("accepted_source_label_count", "0"),
                field="accepted_source_label_count",
            )
            > 0
        )
        daily_reconciles = (
            _decimal(row.get("daily_mapped_sum_delta_kg", "0"), field="daily_mapped_sum_delta_kg")
            == 0
        )
        safe_complete_daily = (
            identity_confirmed
            and row.get("daily_coverage_complete") == "true"
            and row.get("season_boundary_complete") == "true"
            and daily_reconciles
        )
        if safe_complete_daily:
            row["member_coverage_complete"] = "true"
            row["daily_curve_evaluation_eligible"] = "true"
            if row.get("quantity_authority_status") == "NO_COMPLETE_SEASON_TOTAL_AUTHORITY":
                row["complete_season_total_quantity_kg"] = row["complete_daily_sum_kg"]
                row["quantity_authority_status"] = "COMPLETE_DAILY_WINDOW_SUM_AUTHORITY"
                row["quantity_authority_basis"] = "S6_EXPLICIT_NO_RECORD_ZERO_COMPLETE_DAILY_LEDGER"
                row["business_total_reconciliation_status"] = (
                    "NO_BUSINESS_TOTAL_DAILY_WINDOW_COMPLETE"
                )
                row["season_total_reconcilable"] = "true"
                row["season_total_training_eligible"] = "true"
                row["strict_quantity_eligible"] = "true"
                blockers = set(filter(None, row.get("blocker_codes", "").split("|")))
                blockers.difference_update(
                    {
                        "MEMBER_COVERAGE_INCOMPLETE",
                        "BUSINESS_TOTAL_AUTHORITY_MISSING",
                    }
                )
                row["blocker_codes"] = "|".join(sorted(blockers))

    for row in overlays:
        key = (row["base_id"], row["season"])
        completeness = completeness_by_key[key]
        row["season_total_quantity_kg"] = completeness["complete_season_total_quantity_kg"]
        row["quantity_authority_status"] = completeness["quantity_authority_status"]
        row["quantity_authority_basis"] = completeness["quantity_authority_basis"]
        row["daily_curve_evaluation_eligible"] = completeness["daily_curve_evaluation_eligible"]
        row["business_total_reconciliation_status"] = completeness[
            "business_total_reconciliation_status"
        ]
        row["blocker_codes"] = completeness["blocker_codes"]

    for row in eligibility_rows:
        key = (row["base_id"], row["season"])
        completeness = completeness_by_key[key]
        area = area_by_key[key]
        total_eligible = completeness["season_total_training_eligible"] == "true"
        area_eligible = _as_bool(area.get("authority_eligible"))
        strict_training = area_eligible and row["season"] in training_seasons and total_eligible
        strict_oot = area_eligible and row["season"] == oot_season and total_eligible
        row["season_total_quantity_kg"] = (
            completeness["complete_season_total_quantity_kg"] if total_eligible else ""
        )
        row["season_total_quantity_authority"] = completeness["quantity_authority_status"]
        row["season_total_training_eligible"] = str(total_eligible).lower()
        row["daily_curve_evaluation_eligible"] = completeness["daily_curve_evaluation_eligible"]
        row["strict_training_eligible"] = str(strict_training).lower()
        row["strict_oot_eligible"] = str(strict_oot).lower()
        exclusion_reasons: list[str] = []
        if not area_eligible:
            exclusion_reasons.append("AREA_AUTHORITY_MISSING")
        if not total_eligible:
            exclusion_reasons.extend(filter(None, completeness.get("blocker_codes", "").split("|")))
        if row["season"] not in training_seasons:
            exclusion_reasons.append("NOT_TRAINING_SEASON")
        if row["season"] == oot_season and not strict_oot:
            exclusion_reasons.append("NOT_STRICT_OOT_ELIGIBLE")
        row["exclusion_reason"] = "|".join(sorted(set(exclusion_reasons))) or "ELIGIBLE"

    blocker_counts: Counter[tuple[str, str]] = Counter()
    for row in completeness_rows:
        for blocker in filter(None, row.get("blocker_codes", "").split("|")):
            blocker_counts[(row["season"], blocker)] += 1
    blocker_codes = sorted({blocker for _season, blocker in blocker_counts})
    quantity_outputs["blocker_impact_rows"] = [
        {
            "blocker_code": blocker,
            "training_base_season_count": sum(
                blocker_counts[(season, blocker)] for season in sorted(training_seasons)
            ),
            "oot_base_season_count": blocker_counts[(oot_season, blocker)],
            "all_base_season_count": sum(
                blocker_counts[(season, blocker)]
                for season in sorted({row["season"] for row in completeness_rows})
            ),
        }
        for blocker in blocker_codes
    ]
    quantity_outputs["blocker_impact_rows"].sort(
        key=lambda row: (-int(row["training_base_season_count"]), row["blocker_code"])
    )
    return quantity_outputs
