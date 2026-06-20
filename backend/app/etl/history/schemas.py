from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

EXPECTED_HEADERS = (
    "时间",
    "链路",
    "农场",
    "分场",
    "品种",
    "果径",
    "入库公斤数",
    "加工厂",
)


@dataclass(frozen=True)
class SourceSpec:
    path: Path
    source_name: str
    season_code: str
    enabled: bool = True
    expected_sheets: list[str] = field(default_factory=list)
    expected_sheets_behavior: str = "warning"
    header_aliases: dict[str, str] = field(default_factory=dict)
    header_row: int | None = None
    description: str = ""


@dataclass(frozen=True)
class FatalQualityThresholds:
    max_invalid_date_count: int | None = None
    max_invalid_date_ratio: Decimal | None = None
    max_invalid_weight_count: int | None = None
    max_invalid_weight_ratio: Decimal | None = None


@dataclass(frozen=True)
class ImportRules:
    version: str
    valid_months: set[int]
    excluded_grades: set[str]
    excluded_factories: set[str]
    deduplicate_suspected_business_rows_in_curated: bool
    date_formats: list[str]
    variety_prefixes_to_remove: list[str]
    empty_strings: set[str]
    max_issue_examples: int
    allow_unknown_factory_in_analysis: bool
    allow_unknown_variety_in_analysis: bool
    allow_empty_factory_in_analysis: bool
    allow_empty_variety_in_analysis: bool
    fatal_quality_thresholds: FatalQualityThresholds


@dataclass(frozen=True)
class AliasConfig:
    version: str
    aliases: dict[str, str]
    remove_prefixes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ImportConfig:
    sources: list[SourceSpec]
    rules: ImportRules
    factory_aliases: AliasConfig
    variety_aliases: AliasConfig
    config_hash: str
    snapshot: dict[str, Any]


@dataclass(frozen=True)
class ParsedRow:
    source_sheet: str
    source_row_number: int
    raw_payload: dict[str, Any]
    receipt_date_raw: str | None
    link_name_raw: str | None
    farm_raw: str | None
    subfarm_raw: str | None
    variety_raw: str | None
    grade_raw: str | None
    weight_kg_raw: str | None
    factory_raw: str | None
    receipt_date: date | None
    weight_kg: Decimal | None
    parse_errors: list[str]


@dataclass
class ProcessedRow:
    parsed: ParsedRow
    factory_normalized: str | None
    variety_normalized: str | None
    factory_id: int | None
    variety_id: int | None
    grade_id: int | None
    is_factory_known: bool
    is_variety_known: bool
    is_suspected_duplicate: bool
    is_analysis_eligible: bool
    exclusion_reasons: list[str]
    source_row_fingerprint: str
    business_fingerprint: str


@dataclass
class SheetReport:
    sheet_name: str
    physical_row_count: int = 0
    blank_row_count: int = 0
    data_row_count: int = 0
    raw_savable_row_count: int = 0
    date_valid_row_count: int = 0
    empty_date_count: int = 0
    invalid_date_count: int = 0
    empty_factory_count: int = 0
    empty_farm_count: int = 0
    empty_subfarm_count: int = 0
    empty_variety_count: int = 0
    unknown_factory_count: int = 0
    unknown_variety_count: int = 0
    empty_weight_count: int = 0
    invalid_weight_count: int = 0
    negative_weight_count: int = 0
    zero_weight_count: int = 0
    suspected_duplicate_count: int = 0
    raw_parseable_weight_kg: Decimal = Decimal("0")
    analysis_eligible_weight_kg: Decimal = Decimal("0")
    excluded_weight_kg: Decimal = Decimal("0")
    excluded_weight_by_reason_kg: dict[str, Decimal] = field(default_factory=dict)
    earliest_date: date | None = None
    latest_date: date | None = None
    rows_after_april_count: int = 0
    rows_after_april_weight_kg: Decimal = Decimal("0")
    excluded_row_count_by_reason: dict[str, int] = field(default_factory=dict)


@dataclass
class FileReport:
    source_path: str
    file_name: str
    file_sha256: str
    source_name: str
    season_code: str
    sheet_count: int = 0
    row_count: int = 0
    inserted_row_count: int = 0
    suspected_duplicate_count: int = 0
    actual_sheets: list[str] = field(default_factory=list)
    missing_expected_sheets: list[str] = field(default_factory=list)
    unexpected_sheets: list[str] = field(default_factory=list)
    sheet_reports: list[SheetReport] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    cross_sheet_duplicate_count: int = 0
    cross_file_duplicate_count: int = 0
    cross_sheet_duplicate_examples: list[dict[str, Any]] = field(default_factory=list)
    cross_file_duplicate_examples: list[dict[str, Any]] = field(default_factory=list)
    excluded_row_count_by_reason: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class ImportResult:
    source_path: str
    file_sha256: str
    status: str
    inserted_row_count: int
    report: FileReport
