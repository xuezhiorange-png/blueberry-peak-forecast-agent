"""Close V0.8-S5 complete-season quantity authority from frozen daily facts.

This module does not read source workbooks or mutate S1/S2 authority. It reuses
the S2 daily completeness classifier and creates a separate, deterministic
overlay. A season total is eligible only from an existing frozen business
total or from every date in a frozen business window being complete and
identity-bound.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from backend.app.area_yield.v08_s2_model_comparison import daily_quantity_eligibility

SEASONS = ("2023-2024", "2024-2025", "2025-2026")
TRAINING_SEASONS = frozenset({"2023-2024", "2024-2025"})
OOT_SEASON = "2025-2026"
BUSINESS_TOTAL_STATUS = "BUSINESS_TOTAL_AUTHORITY_ELIGIBLE"
BUSINESS_TOTAL_POLICY = "S1_BUSINESS_TOTAL_AUTHORITY_AND_SEASON_TOTAL_COMPLETE"
DAILY_DERIVED_POLICY = "FROZEN_WINDOW_ALL_DAYS_COMPLETE_IDENTITY_BOUND_DAILY_SUM"
POLICY_VERSION = "V0_8_S5_QUANTITY_COMPLETENESS_R1"


class QuantityAuthorityError(ValueError):
    """Raised when frozen quantity inputs cannot be reconciled safely."""


@dataclass(frozen=True)
class SeasonBoundary:
    season: str
    start: date
    end: date
    authority_id: str
    authority_sha256: str

    @property
    def expected_day_count(self) -> int:
        return (self.end - self.start).days + 1


def decimal_value(value: Any, *, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise QuantityAuthorityError(f"INVALID_DECIMAL:{field}") from exc
    if not result.is_finite():
        raise QuantityAuthorityError(f"NONFINITE_DECIMAL:{field}")
    return result


def decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise QuantityAuthorityError("NONFINITE_OUTPUT_DECIMAL")
    return format(value, "f")


def _bool(value: Any) -> bool:
    return str(value).strip().lower() == "true"


def _list_json(value: Any, *, field: str) -> list[str]:
    try:
        parsed = json.loads(str(value or "[]"))
    except (TypeError, json.JSONDecodeError) as exc:
        raise QuantityAuthorityError(f"INVALID_JSON_LIST:{field}") from exc
    if not isinstance(parsed, list) or any(not isinstance(item, str) for item in parsed):
        raise QuantityAuthorityError(f"INVALID_JSON_LIST:{field}")
    return parsed


def _date(value: Any, *, field: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise QuantityAuthorityError(f"INVALID_DATE:{field}") from exc


def _index_unique(
    rows: Sequence[Mapping[str, Any]], *, key_fields: tuple[str, str], label: str
) -> dict[tuple[str, str], Mapping[str, Any]]:
    indexed: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in rows:
        key = (str(row.get(key_fields[0], "")), str(row.get(key_fields[1], "")))
        if any(not part for part in key):
            raise QuantityAuthorityError(f"{label}_IDENTITY_MISSING")
        if key in indexed:
            raise QuantityAuthorityError(f"DUPLICATE_{label}_IDENTITY")
        indexed[key] = row
    return indexed


def _day_codes(
    *,
    eligibility: str,
    source_row_count: int,
    missing_member_count: int,
    unresolved_labels: Sequence[str],
    boundary_known: bool,
    missing_ledger_row: bool = False,
) -> tuple[list[str], str, str]:
    codes: list[str] = []
    partial_reason = ""
    unknown_reason = ""
    if missing_ledger_row:
        codes.append("SOURCE_ROW_MISSING")
        unknown_reason = "NO_CANONICAL_DAILY_ROW"
    elif eligibility == "EXCLUDED_PARTIAL":
        codes.extend(("PARTIAL_KNOWN_SUBTOTAL_DAYS_PRESENT", "PARTIAL_SOURCE_COVERAGE"))
        partial_reason = "MAPPED_MEMBERS_NOT_ALL_OBSERVED_OR_UNRESOLVED_MEMBER_PRESENT"
    elif eligibility == "EXCLUDED_UNKNOWN":
        codes.append("UNKNOWN_DAYS_PRESENT")
        if source_row_count == 0:
            codes.append("SOURCE_ROW_MISSING")
            unknown_reason = "NO_SOURCE_ROW_ZERO_NOT_AUTHORIZED"
        else:
            unknown_reason = "SOURCE_QUANTITY_UNKNOWN"
    if unresolved_labels:
        codes.extend(("IDENTITY_UNRESOLVED", "UNRESOLVED_MEMBER_COVERAGE"))
        if not unknown_reason:
            unknown_reason = "UNRESOLVED_MEMBER_IDENTITY"
    if missing_member_count > 0:
        codes.append("MEMBER_NOT_MAPPED")
        if not unknown_reason:
            partial_reason = partial_reason or "ACCEPTED_MEMBER_NOT_PRESENT_IN_DAILY_SOURCE"
    if not boundary_known:
        codes.append("SEASON_WINDOW_UNKNOWN")
        unknown_reason = unknown_reason or "SEASON_BOUNDARY_NOT_ESTABLISHED"
    return sorted(set(codes)), partial_reason, unknown_reason


def build_quantity_authority_outputs(
    *,
    daily_rows: Sequence[Mapping[str, Any]],
    quality_rows: Sequence[Mapping[str, Any]],
    area_rows: Sequence[Mapping[str, Any]],
    boundaries: Mapping[str, SeasonBoundary],
    season_totals: Mapping[str, Mapping[str, Any]],
    unresolved_identity_rows: Sequence[Mapping[str, Any]],
    expected_season_base_count: int = 39,
) -> dict[str, Any]:
    """Build private row-level closure outputs from already-frozen authorities."""

    quality_by_key = _index_unique(quality_rows, key_fields=("base_id", "season"), label="QUALITY")
    area_by_key = _index_unique(area_rows, key_fields=("base_id", "season"), label="AREA")
    if set(quality_by_key) != set(area_by_key):
        raise QuantityAuthorityError("AREA_QUANTITY_BASE_SEASON_SCOPE_MISMATCH")
    if len({key[0] for key in area_by_key}) != expected_season_base_count:
        raise QuantityAuthorityError("CANONICAL_BASE_COUNT_MISMATCH")
    if {key[1] for key in area_by_key} != set(SEASONS):
        raise QuantityAuthorityError("SEASON_SCOPE_MISMATCH")
    for key, area in area_by_key.items():
        if (
            not _bool(area.get("authority_eligible"))
            or area.get("area_status") != "BUSINESS_CONFIRMED_HISTORICAL_ACTUAL"
            or area.get("identity_authority_id") != "CROSS_SEASON_BASE_IDENTITY_AUTHORITY_R1"
        ):
            raise QuantityAuthorityError(f"AREA_AUTHORITY_NOT_ELIGIBLE:{key[0]}:{key[1]}")

    daily_by_key: dict[tuple[str, str, date], Mapping[str, Any]] = {}
    for row in daily_rows:
        daily_key = (
            str(row.get("base_id", "")),
            str(row.get("season", "")),
            _date(row.get("date"), field="daily.date"),
        )
        if not daily_key[0] or daily_key[1] not in SEASONS:
            raise QuantityAuthorityError("DAILY_ROW_IDENTITY_INVALID")
        if daily_key in daily_by_key:
            raise QuantityAuthorityError("DUPLICATE_CANONICAL_DAILY_ROW")
        daily_by_key[daily_key] = row

    daily_groups: dict[tuple[str, str], list[tuple[date, Mapping[str, Any]]]] = defaultdict(list)
    for (base_id, season, day), row in daily_by_key.items():
        daily_groups[(base_id, season)].append((day, row))
    if not set(daily_groups).issubset(set(quality_by_key)):
        raise QuantityAuthorityError("DAILY_ROW_WITHOUT_QUALITY_AUTHORITY")

    completeness_rows: list[dict[str, Any]] = []
    gap_rows: list[dict[str, Any]] = []
    gap_analysis_rows: list[dict[str, Any]] = []
    quantity_overlay_rows: list[dict[str, Any]] = []
    eligibility_rows: list[dict[str, Any]] = []
    blocker_counts: Counter[tuple[str, str]] = Counter()
    season_observed: dict[str, dict[str, Any]] = {season: defaultdict(int) for season in SEASONS}
    season_daily_known_sum: dict[str, Decimal] = {season: Decimal(0) for season in SEASONS}
    season_daily_partial_sum: dict[str, Decimal] = {season: Decimal(0) for season in SEASONS}
    business_total_record_count = 0
    business_total_reconciled_count = 0
    business_total_mismatch_count = 0

    for key in sorted(quality_by_key, key=lambda item: (item[0], item[1])):
        base_id, season = key
        quality = quality_by_key[key]
        area = area_by_key[key]
        boundary = boundaries.get(season)
        observed_rows = daily_groups.get(key, [])
        by_day = {day: row for day, row in observed_rows}
        if boundary is None:
            expected_dates: list[date] = []
            expected_day_count: int | None = None
            boundary_complete = False
        else:
            expected_dates = [
                boundary.start + timedelta(days=offset)
                for offset in range(boundary.expected_day_count)
            ]
            expected_day_count = boundary.expected_day_count
            boundary_complete = (
                int(quality.get("business_window_calendar_day_count", "-1"))
                == boundary.expected_day_count
            )
            if any(day < boundary.start or day > boundary.end for day, _ in observed_rows):
                raise QuantityAuthorityError("DAILY_ROW_OUTSIDE_FROZEN_SEASON_BOUNDARY")

        accepted_labels = _list_json(
            quality.get("accepted_source_labels"), field="accepted_source_labels"
        )
        unresolved_labels = _list_json(
            quality.get("unresolved_candidate_source_labels"),
            field="unresolved_candidate_source_labels",
        )
        identity_status = str(quality.get("source_identity_status", ""))
        identity_complete = identity_status == "IDENTITY_CONFIRMED" and not unresolved_labels
        expected_member_count = int(quality.get("accepted_source_label_count", "0"))
        if len(accepted_labels) != expected_member_count or len(set(accepted_labels)) != len(
            accepted_labels
        ):
            raise QuantityAuthorityError("ACCEPTED_SOURCE_LABEL_COUNT_MISMATCH")
        complete_mapped_days = 0
        partial_days = 0
        unknown_days = 0
        confirmed_zero_days = 0
        excluded_days = 0
        observed_or_authorized_days = 0
        mapped_quantity = Decimal(0)
        partial_quantity = Decimal(0)
        complete_daily_quantity = Decimal(0)
        first_quantity_date: date | None = None
        missing_expected_rows = 0
        mapped_member_day_missing_count = 0

        for day in expected_dates:
            daily = by_day.get(day)
            if daily is None:
                missing_expected_rows += 1
                unknown_days += 1
                codes, partial_reason, unknown_reason = _day_codes(
                    eligibility="EXCLUDED_UNKNOWN",
                    source_row_count=0,
                    missing_member_count=expected_member_count,
                    unresolved_labels=unresolved_labels,
                    boundary_known=boundary_complete,
                    missing_ledger_row=True,
                )
                gap_rows.append(
                    {
                        "base_id": base_id,
                        "base_name": quality.get("canonical_base_name", ""),
                        "season": season,
                        "date": day.isoformat(),
                        "daily_quantity_status": "NO_CANONICAL_DAILY_ROW",
                        "daily_completeness_status": "NO_ROW",
                        "known_quantity_kg_or_null": "null",
                        "missing_member_count": expected_member_count,
                        "unresolved_member_labels": json.dumps(
                            unresolved_labels, ensure_ascii=False, separators=(",", ":")
                        ),
                        "partial_reason": partial_reason,
                        "unknown_reason": unknown_reason,
                        "source_refs": "[]",
                        "blocker_code": "|".join(codes),
                    }
                )
                continue

            quantity_status = str(daily.get("quantity_status", ""))
            completeness_status = str(daily.get("quantity_completeness_status", ""))
            raw_quantity = daily.get("mapped_observed_subtotal_kg")
            eligibility, _ = daily_quantity_eligibility(
                status=quantity_status,
                completeness_status=completeness_status,
                raw_quantity=raw_quantity,
            )
            source_row_count = int(daily.get("source_row_count", "0"))
            contributing_count = int(daily.get("contributing_source_label_count", "0"))
            missing_member_count = (
                0
                if quantity_status == "CONFIRMED_ZERO" and eligibility == "SCORED_COMPLETE"
                else max(expected_member_count - contributing_count, 0)
            )
            if quantity_status == "KNOWN_MAPPED_SUBTOTAL":
                amount = decimal_value(raw_quantity, field="mapped_observed_subtotal_kg")
                mapped_quantity += amount
                season_daily_known_sum[season] += amount
                if first_quantity_date is None:
                    first_quantity_date = day
                if eligibility == "SCORED_COMPLETE":
                    complete_mapped_days += 1
                    observed_or_authorized_days += 1
                    complete_daily_quantity += amount
                else:
                    partial_days += 1
                    partial_quantity += amount
                    season_daily_partial_sum[season] += amount
            elif quantity_status == "CONFIRMED_ZERO":
                if eligibility != "SCORED_COMPLETE":
                    raise QuantityAuthorityError("CONFIRMED_ZERO_NOT_AUTHORIZED")
                confirmed_zero_days += 1
                observed_or_authorized_days += 1
            elif quantity_status == "UNKNOWN":
                unknown_days += 1
            elif quantity_status == "EXCLUDED":
                excluded_days += 1
            else:
                raise QuantityAuthorityError(f"UNSUPPORTED_DAILY_QUANTITY_STATUS:{quantity_status}")

            if missing_member_count > 0:
                mapped_member_day_missing_count += 1
            if eligibility in {"EXCLUDED_PARTIAL", "EXCLUDED_UNKNOWN"}:
                codes, partial_reason, unknown_reason = _day_codes(
                    eligibility=eligibility,
                    source_row_count=source_row_count,
                    missing_member_count=missing_member_count,
                    unresolved_labels=unresolved_labels,
                    boundary_known=boundary_complete,
                )
                source_refs = {
                    "source_sha256": daily.get("source_sha256", ""),
                    "identity_authority_id": daily.get("identity_authority_id", ""),
                    "identity_authority_sha256": daily.get("identity_authority_sha256", ""),
                }
                gap_rows.append(
                    {
                        "base_id": base_id,
                        "base_name": quality.get("canonical_base_name", ""),
                        "season": season,
                        "date": day.isoformat(),
                        "daily_quantity_status": quantity_status,
                        "daily_completeness_status": completeness_status,
                        "known_quantity_kg_or_null": (
                            decimal_text(decimal_value(raw_quantity, field="daily.quantity"))
                            if quantity_status == "KNOWN_MAPPED_SUBTOTAL"
                            else "null"
                        ),
                        "missing_member_count": missing_member_count,
                        "unresolved_member_labels": json.dumps(
                            unresolved_labels, ensure_ascii=False, separators=(",", ":")
                        ),
                        "partial_reason": partial_reason,
                        "unknown_reason": unknown_reason,
                        "source_refs": json.dumps(
                            source_refs, sort_keys=True, ensure_ascii=False, separators=(",", ":")
                        ),
                        "blocker_code": "|".join(codes),
                    }
                )

        expected_set = set(expected_dates)
        extra_dates = sorted(set(by_day) - expected_set) if boundary else []
        if extra_dates:
            raise QuantityAuthorityError("DAILY_ROW_OUTSIDE_FROZEN_SEASON_BOUNDARY")
        if boundary is None:
            observed_or_authorized_days = 0
            complete_mapped_days = 0
            partial_days = sum(
                row.get("quantity_status") == "KNOWN_MAPPED_SUBTOTAL"
                and row.get("quantity_completeness_status") == "PARTIAL_KNOWN_SUBTOTAL"
                for _, row in observed_rows
            )
            unknown_days = len(observed_rows)
        daily_coverage_complete = (
            boundary_complete
            and expected_day_count is not None
            and missing_expected_rows == 0
            and unknown_days == 0
            and partial_days == 0
            and excluded_days == 0
            and observed_or_authorized_days == expected_day_count
            and identity_complete
        )
        member_coverage_complete = daily_coverage_complete and mapped_member_day_missing_count == 0

        quality_mapped = decimal_value(
            quality.get("business_window_mapped_quantity_kg", "0"),
            field="business_window_mapped_quantity_kg",
        )
        daily_mapped_delta = quality_mapped - mapped_quantity
        business_total_authorized = quality.get(
            "business_total_coverage_status"
        ) == BUSINESS_TOTAL_STATUS and _bool(quality.get("season_total_complete"))
        business_total: Decimal | None = None
        if business_total_authorized:
            business_total_record_count += 1
            business_total = quality_mapped

        blockers: set[str] = set()
        if not boundary_complete:
            blockers.add("SEASON_BOUNDARY_NOT_ESTABLISHED")
        if unknown_days:
            blockers.add("UNKNOWN_DAYS_PRESENT")
        if partial_days:
            blockers.add("PARTIAL_KNOWN_SUBTOTAL_DAYS_PRESENT")
        if unresolved_labels or identity_status in {
            "IDENTITY_UNRESOLVED",
            "IDENTITY_CONFIRMED_WITH_UNRESOLVED_CANDIDATES",
        }:
            blockers.add("IDENTITY_UNRESOLVED")
            blockers.add("UNRESOLVED_MEMBER_COVERAGE")
        if not identity_complete or mapped_member_day_missing_count:
            blockers.add("MEMBER_COVERAGE_INCOMPLETE")
        if not daily_coverage_complete:
            blockers.add("SOURCE_COVERAGE_INCOMPLETE")
        if daily_coverage_complete and daily_mapped_delta != 0:
            blockers.add("DAILY_SUM_NOT_RECONCILED")

        total_quantity: Decimal | None = None
        quantity_authority_status = "NO_COMPLETE_SEASON_TOTAL_AUTHORITY"
        quantity_authority_basis = ""
        business_total_reconciliation_status = "NOT_APPLICABLE_NO_BUSINESS_TOTAL"
        season_total_reconcilable = False
        if business_total_authorized and business_total is not None:
            if not boundary_complete:
                blockers.add("BUSINESS_TOTAL_AUTHORITY_MISSING")
            elif daily_coverage_complete:
                if daily_mapped_delta != 0 or business_total != complete_daily_quantity:
                    quantity_authority_status = "BUSINESS_TOTAL_DAILY_SUM_MISMATCH"
                    business_total_reconciliation_status = "BUSINESS_TOTAL_DAILY_SUM_MISMATCH"
                    blockers.update({"BUSINESS_TOTAL_MISMATCH", "DAILY_SUM_NOT_RECONCILED"})
                    business_total_mismatch_count += 1
                else:
                    quantity_authority_status = "BUSINESS_TOTAL_RECONCILED_WITH_DAILY_SUM"
                    business_total_reconciliation_status = (
                        "BUSINESS_TOTAL_RECONCILED_WITH_DAILY_SUM"
                    )
                    business_total_reconciled_count += 1
                    total_quantity = business_total
                    quantity_authority_basis = BUSINESS_TOTAL_POLICY
                    season_total_reconcilable = True
            else:
                quantity_authority_status = (
                    "BUSINESS_TOTAL_AUTHORITY_PRESENT_DAILY_COVERAGE_INCOMPLETE"
                )
                business_total_reconciliation_status = (
                    "BUSINESS_TOTAL_AUTHORITY_PRESENT_DAILY_COVERAGE_INCOMPLETE"
                )
                total_quantity = business_total
                quantity_authority_basis = BUSINESS_TOTAL_POLICY
                season_total_reconcilable = True
        elif (
            daily_coverage_complete
            and member_coverage_complete
            and boundary_complete
            and daily_mapped_delta == 0
        ):
            quantity_authority_status = "COMPLETE_DAILY_WINDOW_SUM_AUTHORITY"
            business_total_reconciliation_status = "NO_BUSINESS_TOTAL_DAILY_WINDOW_COMPLETE"
            total_quantity = complete_daily_quantity
            quantity_authority_basis = DAILY_DERIVED_POLICY
            season_total_reconcilable = True
        else:
            blockers.add("BUSINESS_TOTAL_AUTHORITY_MISSING")

        if quantity_authority_status == "BUSINESS_TOTAL_DAILY_SUM_MISMATCH":
            blockers.add("BUSINESS_TOTAL_MISMATCH")
        season_total_eligible = total_quantity is not None and season_total_reconcilable
        if not season_total_eligible:
            quantity_authority_status = (
                quantity_authority_status
                if quantity_authority_status == "BUSINESS_TOTAL_DAILY_SUM_MISMATCH"
                else "NO_COMPLETE_SEASON_TOTAL_AUTHORITY"
            )

        for code in blockers:
            blocker_counts[(season, code)] += 1
        for day_row in observed_rows:
            row = day_row[1]
            status = str(row.get("quantity_status", ""))
            completeness = str(row.get("quantity_completeness_status", ""))
            if status == "UNKNOWN":
                season_observed[season]["unknown_day_count"] += 1
            elif status == "KNOWN_MAPPED_SUBTOTAL" and completeness == "PARTIAL_KNOWN_SUBTOTAL":
                season_observed[season]["partial_day_count"] += 1
                season_observed[season]["partial_known_quantity_kg"] += decimal_value(
                    row.get("mapped_observed_subtotal_kg"), field="daily.quantity"
                )
            elif status == "CONFIRMED_ZERO":
                season_observed[season]["confirmed_zero_day_count"] += 1
            elif status == "KNOWN_MAPPED_SUBTOTAL" and completeness == "COMPLETE_MAPPED_MEMBERS":
                season_observed[season]["complete_mapped_member_day_count"] += 1
        season_observed[season]["base_season_count"] += 1
        if season_total_eligible:
            season_observed[season]["season_total_eligible_count"] += 1
        if daily_coverage_complete and member_coverage_complete:
            season_observed[season]["daily_curve_evaluation_eligible_count"] += 1

        boundary_start = boundary.start.isoformat() if boundary else ""
        boundary_end = boundary.end.isoformat() if boundary else ""
        actual_start_dates = [
            day.isoformat()
            for day, row in observed_rows
            if row.get("quantity_status") == "KNOWN_MAPPED_SUBTOTAL"
        ]
        total_value = decimal_text(total_quantity) if total_quantity is not None else ""
        blockers_text = "|".join(sorted(blockers))
        completeness_row = {
            "base_id": base_id,
            "base_name": quality.get("canonical_base_name", ""),
            "season": season,
            "season_start_date": boundary_start,
            "season_end_date": boundary_end,
            "season_boundary_authority": boundary.authority_id if boundary else "NOT_ESTABLISHED",
            "season_boundary_authority_sha256": boundary.authority_sha256 if boundary else "",
            "expected_calendar_day_count": (
                expected_day_count if expected_day_count is not None else ""
            ),
            "observed_or_authorized_day_count": observed_or_authorized_days,
            "complete_mapped_member_day_count": complete_mapped_days,
            "partial_known_subtotal_day_count": partial_days,
            "unknown_day_count": unknown_days,
            "confirmed_zero_day_count": confirmed_zero_days,
            "excluded_day_count": excluded_days,
            "missing_canonical_daily_row_count": missing_expected_rows,
            "first_quantity_date": min(actual_start_dates) if actual_start_dates else "",
            "last_quantity_date": max(actual_start_dates) if actual_start_dates else "",
            "mapped_quantity_kg": decimal_text(mapped_quantity),
            "complete_daily_sum_kg": decimal_text(complete_daily_quantity),
            "partial_known_quantity_kg": decimal_text(partial_quantity),
            "unknown_quantity_kg_or_null": "null",
            "business_total_quantity_kg_or_null": (
                decimal_text(business_total) if business_total is not None else "null"
            ),
            "daily_coverage_complete": str(daily_coverage_complete).lower(),
            "member_coverage_complete": str(member_coverage_complete).lower(),
            "season_boundary_complete": str(boundary_complete).lower(),
            "quality_ledger_mapped_quantity_kg": decimal_text(quality_mapped),
            "daily_mapped_sum_delta_kg": decimal_text(daily_mapped_delta),
            "season_total_reconcilable": str(season_total_reconcilable).lower(),
            "complete_season_total_quantity_kg": total_value,
            "quantity_authority_status": quantity_authority_status,
            "quantity_authority_basis": quantity_authority_basis,
            "existing_business_total_status": quality.get("business_total_coverage_status", ""),
            "season_total_complete": str(_bool(quality.get("season_total_complete"))).lower(),
            "business_total_reconciliation_status": business_total_reconciliation_status,
            "source_identity_status": identity_status,
            "accepted_source_label_count": expected_member_count,
            "unresolved_member_label_count": len(unresolved_labels),
            "daily_curve_evaluation_eligible": str(
                daily_coverage_complete and member_coverage_complete
            ).lower(),
            "season_total_training_eligible": str(season_total_eligible).lower(),
            "strict_quantity_eligible": str(season_total_eligible).lower(),
            "blocker_codes": blockers_text,
        }
        completeness_rows.append(completeness_row)

        gate_reason = (
            "BUSINESS_TOTAL_PRESENT"
            if business_total_authorized
            else "DAILY_WINDOW_DERIVED_TOTAL"
            if quantity_authority_status == "COMPLETE_DAILY_WINDOW_SUM_AUTHORITY"
            else "NO_BUSINESS_TOTAL_AND_DAILY_WINDOW_INCOMPLETE"
        )
        gap_analysis_rows.append(
            {
                "base_id": base_id,
                "base_name": quality.get("canonical_base_name", ""),
                "season": season,
                "business_total_coverage_status": quality.get("business_total_coverage_status", ""),
                "season_total_complete": str(_bool(quality.get("season_total_complete"))).lower(),
                "business_total_authority_present": str(business_total_authorized).lower(),
                "business_total_quantity_kg_or_null": (
                    decimal_text(business_total) if business_total is not None else "null"
                ),
                "daily_mapped_quantity_kg": decimal_text(mapped_quantity),
                "daily_complete_sum_kg": decimal_text(complete_daily_quantity),
                "daily_coverage_complete": str(daily_coverage_complete).lower(),
                "daily_curve_evaluation_eligible": str(
                    daily_coverage_complete and member_coverage_complete
                ).lower(),
                "quantity_authority_status": quantity_authority_status,
                "quantity_authority_basis": quantity_authority_basis,
                "prior_gate_gap_classification": gate_reason,
                "blocker_codes": blockers_text,
            }
        )
        quantity_overlay_rows.append(
            {
                "base_id": base_id,
                "base_name": quality.get("canonical_base_name", ""),
                "season": season,
                "season_total_quantity_kg": total_value,
                "quantity_authority_status": quantity_authority_status,
                "quantity_authority_basis": quantity_authority_basis,
                "daily_curve_evaluation_eligible": str(
                    daily_coverage_complete and member_coverage_complete
                ).lower(),
                "business_total_reconciliation_status": business_total_reconciliation_status,
                "blocker_codes": blockers_text,
                "quantity_authority_id": "V0_8_COMPLETE_SEASON_QUANTITY_AUTHORITY_OVERLAY_R1",
                "s1_identity_authority_id": "CROSS_SEASON_BASE_IDENTITY_AUTHORITY_R1",
            }
        )

        area_mu = decimal_value(area.get("historical_actual_area_mu"), field="area_mu")
        area_eligible = area_mu > 0 and _bool(area.get("authority_eligible"))
        strict_training = area_eligible and season in TRAINING_SEASONS and season_total_eligible
        strict_oot = area_eligible and season == OOT_SEASON and season_total_eligible
        exclusion_reasons: list[str] = []
        if not area_eligible:
            exclusion_reasons.append("AREA_AUTHORITY_MISSING")
        if not season_total_eligible:
            exclusion_reasons.extend(sorted(blockers))
        if season not in TRAINING_SEASONS:
            exclusion_reasons.append("NOT_TRAINING_SEASON")
        if season == OOT_SEASON and not strict_oot:
            exclusion_reasons.append("NOT_STRICT_OOT_ELIGIBLE")
        eligibility_rows.append(
            {
                "base_id": base_id,
                "base_name": quality.get("canonical_base_name", ""),
                "season": season,
                "area_mu": decimal_text(area_mu),
                "area_eligible": str(area_eligible).lower(),
                "season_total_quantity_kg": total_value,
                "season_total_quantity_authority": quantity_authority_status,
                "season_total_training_eligible": str(season_total_eligible).lower(),
                "daily_curve_evaluation_eligible": str(
                    daily_coverage_complete and member_coverage_complete
                ).lower(),
                "strict_training_eligible": str(strict_training).lower(),
                "strict_oot_eligible": str(strict_oot).lower(),
                "exclusion_reason": "|".join(sorted(set(exclusion_reasons))) or "ELIGIBLE",
            }
        )

    if len(completeness_rows) != len(quality_rows):
        raise QuantityAuthorityError("BASE_SEASON_COMPLETENESS_ROW_COUNT_MISMATCH")
    gap_rows.sort(key=lambda row: (row["season"], row["base_id"], row["date"]))
    completeness_rows.sort(key=lambda row: (row["season"], row["base_id"]))
    gap_analysis_rows.sort(key=lambda row: (row["season"], row["base_id"]))
    quantity_overlay_rows.sort(key=lambda row: (row["season"], row["base_id"]))
    eligibility_rows.sort(key=lambda row: (row["season"], row["base_id"]))

    conservation_rows: list[dict[str, Any]] = []
    unresolved_by_season: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in unresolved_identity_rows:
        season = str(row.get("season", ""))
        if season in SEASONS:
            unresolved_by_season[season].append(row)
    for season in SEASONS:
        totals = season_totals.get(season)
        if not totals:
            raise QuantityAuthorityError(f"SEASON_SOURCE_TOTALS_MISSING:{season}")
        raw = decimal_value(totals.get("raw_source_kg"), field="raw_source_kg")
        mapped = decimal_value(totals.get("mapped_kg"), field="mapped_kg")
        unresolved = decimal_value(totals.get("unresolved_kg"), field="unresolved_kg")
        excluded = decimal_value(totals.get("explicitly_excluded_kg"), field="excluded_kg")
        delta = raw - mapped - unresolved - excluded
        business_window = decimal_value(
            totals.get("business_window_mapped_kg"), field="business_window_mapped_kg"
        )
        daily_delta = business_window - season_daily_known_sum[season]
        unresolved_rows = unresolved_by_season.get(season, [])
        unresolved_raw_from_labels = sum(
            (
                decimal_value(row.get("raw_source_quantity_kg"), field="unresolved.raw_kg")
                for row in unresolved_rows
            ),
            Decimal(0),
        )
        if unresolved_raw_from_labels != unresolved:
            raise QuantityAuthorityError(f"UNRESOLVED_LEDGER_TOTAL_MISMATCH:{season}")
        source_labels = {str(row.get("source_farm_label", "")) for row in unresolved_rows}
        candidate_ids: set[str] = set()
        for row in unresolved_rows:
            candidate_ids.update(
                _list_json(row.get("candidate_base_ids"), field="candidate_base_ids")
            )
        conservation_rows.append(
            {
                "season": season,
                "raw_source_quantity_kg": decimal_text(raw),
                "mapped_source_quantity_kg": decimal_text(mapped),
                "unresolved_source_quantity_kg": decimal_text(unresolved),
                "explicitly_excluded_quantity_kg": decimal_text(excluded),
                "raw_conservation_delta_kg": decimal_text(delta),
                "raw_conservation_pass": str(delta == 0).lower(),
                "business_window_mapped_quantity_kg_authority": decimal_text(business_window),
                "canonical_daily_mapped_sum_kg": decimal_text(season_daily_known_sum[season]),
                "daily_mapped_sum_delta_kg": decimal_text(daily_delta),
                "daily_sum_reconciliation_pass": str(daily_delta == 0).lower(),
                "partial_known_quantity_kg": decimal_text(season_daily_partial_sum[season]),
                "unresolved_source_farm_label_count": len(source_labels),
                "unresolved_ledger_row_count": len(unresolved_rows),
                "affected_candidate_base_count": len(candidate_ids),
                "affected_candidate_base_ids_sha256": _hash_lines(candidate_ids),
            }
        )

    blocker_impact_rows: list[dict[str, Any]] = []
    all_blockers = sorted({code for _, code in blocker_counts})
    for code in all_blockers:
        blocker_impact_rows.append(
            {
                "blocker_code": code,
                "training_base_season_count": sum(
                    blocker_counts[(season, code)] for season in sorted(TRAINING_SEASONS)
                ),
                "oot_base_season_count": blocker_counts[(OOT_SEASON, code)],
                "all_base_season_count": sum(blocker_counts[(season, code)] for season in SEASONS),
            }
        )
    blocker_impact_rows.sort(
        key=lambda row: (-int(row["training_base_season_count"]), row["blocker_code"])
    )

    return {
        "completeness_rows": completeness_rows,
        "gap_rows": gap_rows,
        "gap_analysis_rows": gap_analysis_rows,
        "quantity_overlay_rows": quantity_overlay_rows,
        "eligibility_rows": eligibility_rows,
        "conservation_rows": conservation_rows,
        "blocker_impact_rows": blocker_impact_rows,
        "season_observed": {
            season: {
                key: (decimal_text(Decimal(value)) if key == "partial_known_quantity_kg" else value)
                for key, value in sorted(values.items())
            }
            for season, values in season_observed.items()
        },
        "business_total_record_count": business_total_record_count,
        "business_total_reconciled_count": business_total_reconciled_count,
        "business_total_mismatch_count": business_total_mismatch_count,
    }


def _hash_lines(values: Sequence[str] | set[str]) -> str:
    import hashlib

    return hashlib.sha256("\n".join(sorted(values)).encode("utf-8")).hexdigest()
