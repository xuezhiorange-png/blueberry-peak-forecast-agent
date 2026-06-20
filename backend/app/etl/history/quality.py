from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from backend.app.etl.history.fingerprint import business_fingerprint, source_row_fingerprint
from backend.app.etl.history.normalizer import normalize_factory, normalize_text, normalize_variety
from backend.app.etl.history.schemas import (
    FileReport,
    ImportConfig,
    ParsedRow,
    ProcessedRow,
    SheetReport,
    SourceSpec,
)


def _add_weight(target: dict[str, Decimal], key: str, weight: Decimal | None) -> None:
    if weight is not None:
        target[key] = target.get(key, Decimal("0")) + weight


def _add_count(target: dict[str, int], key: str) -> None:
    target[key] = target.get(key, 0) + 1


def _append_limited(target: list[dict[str, Any]], item: dict[str, Any], limit: int) -> None:
    if len(target) < limit:
        target.append(item)


def process_rows(
    *,
    rows: list[ParsedRow],
    source: SourceSpec,
    file_sha256: str,
    config: ImportConfig,
    factory_ids_by_name: dict[str, int],
    variety_ids_by_name: dict[str, int],
    grade_ids_by_code: dict[str, int],
    existing_business_rows: dict[str, list[dict[str, Any]]] | None = None,
) -> tuple[list[ProcessedRow], FileReport]:
    existing_business_rows = existing_business_rows or {}
    sheet_reports: dict[str, SheetReport] = defaultdict(lambda: SheetReport(sheet_name=""))
    processed: list[ProcessedRow] = []
    earliest: date | None = None
    latest: date | None = None
    warnings: list[str] = []
    file_excluded_row_counts: dict[str, int] = {}
    first_seen_in_file: dict[str, dict[str, Any]] = {}
    cross_sheet_duplicate_count = 0
    cross_file_duplicate_count = 0
    cross_sheet_duplicate_examples: list[dict[str, Any]] = []
    cross_file_duplicate_examples: list[dict[str, Any]] = []

    for row in rows:
        report = sheet_reports[row.source_sheet]
        report.sheet_name = row.source_sheet
        report.data_row_count += 1
        report.raw_savable_row_count += 1
        if row.receipt_date is None:
            if "empty_date" in row.parse_errors:
                report.empty_date_count += 1
            if "invalid_date" in row.parse_errors:
                report.invalid_date_count += 1
        else:
            report.date_valid_row_count += 1
            report.earliest_date = (
                row.receipt_date
                if report.earliest_date is None
                else min(report.earliest_date, row.receipt_date)
            )
            report.latest_date = (
                row.receipt_date
                if report.latest_date is None
                else max(report.latest_date, row.receipt_date)
            )
            earliest = row.receipt_date if earliest is None else min(earliest, row.receipt_date)
            latest = row.receipt_date if latest is None else max(latest, row.receipt_date)

        if normalize_text(row.factory_raw) is None:
            report.empty_factory_count += 1
        if normalize_text(row.farm_raw) is None:
            report.empty_farm_count += 1
        if normalize_text(row.subfarm_raw) is None:
            report.empty_subfarm_count += 1
        if normalize_text(row.variety_raw) is None:
            report.empty_variety_count += 1
        if row.weight_kg is None:
            if "empty_weight" in row.parse_errors:
                report.empty_weight_count += 1
            if "invalid_weight" in row.parse_errors:
                report.invalid_weight_count += 1
        else:
            report.raw_parseable_weight_kg += row.weight_kg
            if row.weight_kg < 0:
                report.negative_weight_count += 1
            if row.weight_kg == 0:
                report.zero_weight_count += 1
            if row.receipt_date is not None and row.receipt_date.month > 4:
                report.rows_after_april_count += 1
                report.rows_after_april_weight_kg += row.weight_kg

        factory_clean, factory_normalized = normalize_factory(
            row.factory_raw, config.factory_aliases
        )
        variety_clean, variety_normalized = normalize_variety(
            row.variety_raw, config.variety_aliases
        )
        farm_normalized = normalize_text(row.farm_raw)
        subfarm_normalized = normalize_text(row.subfarm_raw)
        factory_id = factory_ids_by_name.get(factory_normalized or "")
        variety_id = variety_ids_by_name.get(variety_normalized or "")
        grade_normalized = normalize_text(row.grade_raw)
        grade_id = grade_ids_by_code.get(grade_normalized or "")
        is_factory_known = factory_normalized is not None and factory_id is not None
        is_variety_known = variety_normalized is not None and variety_id is not None
        if factory_clean is not None and not is_factory_known:
            report.unknown_factory_count += 1
        if variety_clean is not None and not is_variety_known:
            report.unknown_variety_count += 1

        business_fp = business_fingerprint(
            season_code=source.season_code,
            receipt_date=row.receipt_date,
            factory_name=factory_normalized,
            farm_name=farm_normalized,
            subfarm_name=subfarm_normalized,
            variety_name=variety_normalized,
            grade_code=grade_normalized,
            weight_kg=row.weight_kg,
        )
        first_occurrence = first_seen_in_file.get(business_fp)
        is_later_in_file_duplicate = first_occurrence is not None
        if first_occurrence is None:
            first_seen_in_file[business_fp] = {
                "sheet_name": row.source_sheet,
                "row_number": row.source_row_number,
            }
        else:
            if first_occurrence["sheet_name"] != row.source_sheet:
                cross_sheet_duplicate_count += 1
                _append_limited(
                    cross_sheet_duplicate_examples,
                    {
                        "first_sheet": first_occurrence["sheet_name"],
                        "first_row_number": first_occurrence["row_number"],
                        "duplicate_sheet": row.source_sheet,
                        "duplicate_row_number": row.source_row_number,
                    },
                    config.rules.max_issue_examples,
                )

        existing_matches = existing_business_rows.get(business_fp, [])
        has_prior_file_match = bool(existing_matches)
        if existing_matches:
            cross_file_duplicate_count += 1
            _append_limited(
                cross_file_duplicate_examples,
                {
                    "current_sheet": row.source_sheet,
                    "current_row_number": row.source_row_number,
                    "existing_examples": existing_matches[:1],
                },
                config.rules.max_issue_examples,
            )
        is_duplicate = is_later_in_file_duplicate or has_prior_file_match
        if is_duplicate:
            report.suspected_duplicate_count += 1

        exclusion_reasons = list(row.parse_errors)
        if row.receipt_date is None:
            exclusion_reasons.append("date_invalid")
        elif row.receipt_date.month not in config.rules.valid_months:
            exclusion_reasons.append("month_out_of_scope")
        if grade_normalized in config.rules.excluded_grades:
            exclusion_reasons.append("grade_excluded")
        if factory_normalized in config.rules.excluded_factories:
            exclusion_reasons.append("factory_excluded")
        if factory_clean is None:
            exclusion_reasons.append("factory_empty")
        elif not is_factory_known and not config.rules.allow_unknown_factory_in_analysis:
            exclusion_reasons.append("factory_unknown")
        if variety_clean is None:
            exclusion_reasons.append("variety_empty")
        elif not is_variety_known and not config.rules.allow_unknown_variety_in_analysis:
            exclusion_reasons.append("variety_unknown")
        if row.weight_kg is None:
            exclusion_reasons.append("weight_invalid")
        elif row.weight_kg <= 0:
            exclusion_reasons.append("weight_not_positive")
        if is_duplicate and config.rules.deduplicate_suspected_business_rows_in_curated:
            exclusion_reasons.append("suspected_duplicate")
        if factory_clean is None and config.rules.allow_empty_factory_in_analysis:
            exclusion_reasons = [
                reason for reason in exclusion_reasons if reason != "factory_empty"
            ]
        if variety_clean is None and config.rules.allow_empty_variety_in_analysis:
            exclusion_reasons = [
                reason for reason in exclusion_reasons if reason != "variety_empty"
            ]
        exclusion_reasons = list(dict.fromkeys(exclusion_reasons))
        is_analysis_eligible = not exclusion_reasons
        if row.weight_kg is not None:
            if is_analysis_eligible:
                report.analysis_eligible_weight_kg += row.weight_kg
            else:
                report.excluded_weight_kg += row.weight_kg
                for reason in exclusion_reasons:
                    _add_weight(report.excluded_weight_by_reason_kg, reason, row.weight_kg)
                    _add_count(report.excluded_row_count_by_reason, reason)
                    _add_count(file_excluded_row_counts, reason)
        elif exclusion_reasons:
            for reason in exclusion_reasons:
                _add_count(report.excluded_row_count_by_reason, reason)
                _add_count(file_excluded_row_counts, reason)

        processed.append(
            ProcessedRow(
                parsed=row,
                factory_normalized=factory_normalized,
                variety_normalized=variety_normalized,
                factory_id=factory_id,
                variety_id=variety_id,
                grade_id=grade_id,
                is_factory_known=is_factory_known,
                is_variety_known=is_variety_known,
                is_suspected_duplicate=is_duplicate,
                is_analysis_eligible=is_analysis_eligible,
                exclusion_reasons=exclusion_reasons,
                source_row_fingerprint=source_row_fingerprint(
                    file_sha256, row.source_sheet, row.source_row_number
                ),
                business_fingerprint=business_fp,
            )
        )

    if earliest and not (
        source.season_code[:4] in str(earliest.year)
        or source.season_code[-4:] in str(latest.year if latest else earliest.year)
    ):
        latest_text = latest.isoformat() if latest else earliest.isoformat()
        warnings.append(
            f"Date range {earliest.isoformat()}..{latest_text} may not match "
            f"configured season {source.season_code}"
        )

    file_report = FileReport(
        source_path=str(source.path),
        file_name=source.path.name,
        file_sha256=file_sha256,
        source_name=source.source_name,
        season_code=source.season_code,
        sheet_count=len(sheet_reports),
        row_count=len(rows),
        inserted_row_count=0,
        suspected_duplicate_count=sum(
            report.suspected_duplicate_count for report in sheet_reports.values()
        ),
        actual_sheets=list(sheet_reports.keys()),
        sheet_reports=list(sheet_reports.values()),
        warnings=warnings,
        cross_sheet_duplicate_count=cross_sheet_duplicate_count,
        cross_file_duplicate_count=cross_file_duplicate_count,
        cross_sheet_duplicate_examples=cross_sheet_duplicate_examples,
        cross_file_duplicate_examples=cross_file_duplicate_examples,
        excluded_row_count_by_reason=file_excluded_row_counts,
    )
    return processed, file_report


def decimal_json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value.quantize(Decimal("0.000001")))
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        return [decimal_json(item) for item in value]
    if isinstance(value, dict):
        return {key: decimal_json(item) for key, item in value.items()}
    if hasattr(value, "__dict__"):
        return decimal_json(value.__dict__)
    return value
