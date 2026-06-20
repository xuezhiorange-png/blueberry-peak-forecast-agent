from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

from backend.app.etl.history.fingerprint import (
    business_fingerprint,
    normalize_decimal_for_fingerprint,
    source_row_fingerprint,
)
from backend.app.etl.history.normalizer import normalize_factory, normalize_text, normalize_variety
from backend.app.etl.history.quality import process_rows
from backend.app.etl.history.schemas import (
    AliasConfig,
    FatalQualityThresholds,
    ImportConfig,
    ImportRules,
    ParsedRow,
    SourceSpec,
)


def test_source_row_fingerprint_is_stable_and_source_specific() -> None:
    first = source_row_fingerprint("abc", "Sheet1", 2)
    assert first == source_row_fingerprint("abc", "Sheet1", 2)
    assert first != source_row_fingerprint("abc", "Sheet2", 2)
    assert first != source_row_fingerprint("abc", "Sheet1", 3)


def test_business_fingerprint_uses_decimal_six_place_normalization() -> None:
    kwargs = {
        "season_code": "2025-2026",
        "receipt_date": date(2026, 1, 2),
        "factory_name": "工厂A",
        "farm_name": "农场A",
        "subfarm_name": "分场A",
        "variety_name": "Dx",
        "grade_code": "优果",
    }
    assert normalize_decimal_for_fingerprint(Decimal("1.2")) == "1.200000"
    assert business_fingerprint(weight_kg=Decimal("1.2"), **kwargs) == business_fingerprint(
        weight_kg=Decimal("1.2000001"), **kwargs
    )


def test_unicode_whitespace_and_variety_prefix_normalization() -> None:
    aliases = AliasConfig(version="test", aliases={"Dx": "DX"}, remove_prefixes=["蓝莓原果"])
    assert normalize_text(" Ｄｘ   A ") == "Dx A"
    assert normalize_variety(" 蓝莓原果Dx ", aliases) == ("Dx", "DX")


def test_business_fingerprint_uses_normalized_business_values() -> None:
    factory_aliases = AliasConfig(version="test", aliases={"新哨厂": "新哨加工厂"})
    variety_aliases = AliasConfig(
        version="test",
        aliases={"Dx": "Dx"},
        remove_prefixes=["蓝莓原果"],
    )
    base_kwargs = {
        "season_code": "2025-2026",
        "receipt_date": date(2026, 1, 2),
        "farm_name": normalize_text(" 农场A "),
        "subfarm_name": normalize_text(" 分场A "),
        "grade_code": normalize_text(" 优果 "),
        "weight_kg": Decimal("1.000000"),
    }

    assert business_fingerprint(
        factory_name=normalize_factory("新哨厂", factory_aliases)[1],
        variety_name=normalize_variety("蓝莓原果Dx", variety_aliases)[1],
        **base_kwargs,
    ) == business_fingerprint(
        factory_name=normalize_factory("新哨加工厂", factory_aliases)[1],
        variety_name=normalize_variety("Dx", variety_aliases)[1],
        **base_kwargs,
    )
    assert business_fingerprint(
        factory_name="工厂A",
        variety_name="Dx",
        **base_kwargs,
    ) == business_fingerprint(
        factory_name="工厂A",
        variety_name="Dx",
        **base_kwargs,
    )
    assert business_fingerprint(
        factory_name="工厂A",
        variety_name="Dx",
        **base_kwargs,
    ) != business_fingerprint(
        factory_name="工厂B",
        variety_name="Dx",
        **base_kwargs,
    )
    assert business_fingerprint(
        factory_name="工厂A",
        variety_name="Dx",
        **base_kwargs,
    ) != business_fingerprint(
        factory_name="工厂A",
        variety_name="Dy",
        **base_kwargs,
    )


def test_quality_rules_preserve_raw_but_record_all_exclusion_reasons() -> None:
    rules = ImportRules(
        version="test",
        valid_months={1, 2, 3, 4},
        excluded_grades={"普鲜", "普青", "普冻", "废果"},
        excluded_factories={"巴松加工厂"},
        deduplicate_suspected_business_rows_in_curated=True,
        date_formats=["%Y-%m-%d"],
        variety_prefixes_to_remove=["蓝莓原果"],
        empty_strings={""},
        max_issue_examples=50,
        allow_unknown_factory_in_analysis=False,
        allow_unknown_variety_in_analysis=False,
        allow_empty_factory_in_analysis=False,
        allow_empty_variety_in_analysis=False,
        fatal_quality_thresholds=FatalQualityThresholds(),
    )
    config = ImportConfig(
        sources=[],
        rules=rules,
        factory_aliases=AliasConfig(version="test", aliases={"巴松加工厂": "巴松加工厂"}),
        variety_aliases=AliasConfig(version="test", aliases={}, remove_prefixes=["蓝莓原果"]),
        config_hash="hash",
        snapshot={},
    )
    source = SourceSpec(path=Path("fixture.xls"), source_name="test", season_code="2025-2026")
    rows = [
        ParsedRow(
            source_sheet="Sheet1",
            source_row_number=2,
            raw_payload={},
            receipt_date_raw="2026-05-01",
            link_name_raw=None,
            farm_raw="农场",
            subfarm_raw="分场",
            variety_raw="蓝莓原果Dx",
            grade_raw="普鲜",
            weight_kg_raw="0",
            factory_raw="巴松加工厂",
            receipt_date=date(2026, 5, 1),
            weight_kg=Decimal("0"),
            parse_errors=[],
        ),
        ParsedRow(
            source_sheet="Sheet1",
            source_row_number=3,
            raw_payload={},
            receipt_date_raw="2026-03-01",
            link_name_raw=None,
            farm_raw="农场",
            subfarm_raw="分场",
            variety_raw="未知",
            grade_raw="优果",
            weight_kg_raw="-1",
            factory_raw="未知厂",
            receipt_date=date(2026, 3, 1),
            weight_kg=Decimal("-1"),
            parse_errors=[],
        ),
    ]

    processed, report = process_rows(
        rows=rows,
        source=source,
        file_sha256="abc",
        config=config,
        factory_ids_by_name={"巴松加工厂": 1},
        variety_ids_by_name={"Dx": 1},
        grade_ids_by_code={"普鲜": 1, "优果": 2},
    )

    assert len(processed) == 2
    assert processed[0].is_analysis_eligible is False
    assert set(processed[0].exclusion_reasons) >= {
        "month_out_of_scope",
        "grade_excluded",
        "factory_excluded",
        "weight_not_positive",
    }
    assert processed[1].is_analysis_eligible is False
    assert "weight_not_positive" in processed[1].exclusion_reasons
    assert "factory_unknown" in processed[1].exclusion_reasons
    assert "variety_unknown" in processed[1].exclusion_reasons
    assert report.sheet_reports[0].rows_after_april_count == 1
    assert report.sheet_reports[0].negative_weight_count == 1
    assert report.sheet_reports[0].zero_weight_count == 1


def test_duplicate_handling_preserves_first_row_and_marks_later_rows_only() -> None:
    rules = ImportRules(
        version="test",
        valid_months={1, 2, 3, 4},
        excluded_grades=set(),
        excluded_factories=set(),
        deduplicate_suspected_business_rows_in_curated=True,
        date_formats=["%Y-%m-%d"],
        variety_prefixes_to_remove=[],
        empty_strings={""},
        max_issue_examples=10,
        allow_unknown_factory_in_analysis=False,
        allow_unknown_variety_in_analysis=False,
        allow_empty_factory_in_analysis=False,
        allow_empty_variety_in_analysis=False,
        fatal_quality_thresholds=FatalQualityThresholds(),
    )
    config = ImportConfig(
        sources=[],
        rules=rules,
        factory_aliases=AliasConfig(version="test", aliases={"工厂A": "工厂A"}),
        variety_aliases=AliasConfig(version="test", aliases={"Dx": "Dx"}),
        config_hash="hash",
        snapshot={},
    )
    source = SourceSpec(path=Path("fixture.xls"), source_name="test", season_code="2025-2026")
    rows = [
        ParsedRow(
            source_sheet="Sheet1",
            source_row_number=2,
            raw_payload={},
            receipt_date_raw="2026-01-01",
            link_name_raw=None,
            farm_raw="农场A",
            subfarm_raw="分场A",
            variety_raw="Dx",
            grade_raw="优果",
            weight_kg_raw="1",
            factory_raw="工厂A",
            receipt_date=date(2026, 1, 1),
            weight_kg=Decimal("1"),
            parse_errors=[],
        ),
        ParsedRow(
            source_sheet="Sheet1",
            source_row_number=3,
            raw_payload={},
            receipt_date_raw="2026-01-01",
            link_name_raw=None,
            farm_raw="农场A",
            subfarm_raw="分场A",
            variety_raw="Dx",
            grade_raw="优果",
            weight_kg_raw="1",
            factory_raw="工厂A",
            receipt_date=date(2026, 1, 1),
            weight_kg=Decimal("1"),
            parse_errors=[],
        ),
        ParsedRow(
            source_sheet="Sheet2",
            source_row_number=2,
            raw_payload={},
            receipt_date_raw="2026-01-01",
            link_name_raw=None,
            farm_raw="农场A",
            subfarm_raw="分场A",
            variety_raw="Dx",
            grade_raw="优果",
            weight_kg_raw="1",
            factory_raw="工厂A",
            receipt_date=date(2026, 1, 1),
            weight_kg=Decimal("1"),
            parse_errors=[],
        ),
    ]

    processed, report = process_rows(
        rows=rows,
        source=source,
        file_sha256="abc",
        config=config,
        factory_ids_by_name={"工厂A": 1},
        variety_ids_by_name={"Dx": 1},
        grade_ids_by_code={"优果": 1},
    )

    assert processed[0].is_suspected_duplicate is False
    assert processed[0].is_analysis_eligible is True
    assert processed[1].is_suspected_duplicate is True
    assert "suspected_duplicate" in processed[1].exclusion_reasons
    assert processed[2].is_suspected_duplicate is True
    assert report.cross_sheet_duplicate_count == 1
    assert report.cross_sheet_duplicate_examples


def test_duplicate_exclusion_can_be_disabled_and_cross_file_duplicates_are_counted() -> None:
    rules = ImportRules(
        version="test",
        valid_months={1, 2, 3, 4},
        excluded_grades=set(),
        excluded_factories=set(),
        deduplicate_suspected_business_rows_in_curated=False,
        date_formats=["%Y-%m-%d"],
        variety_prefixes_to_remove=[],
        empty_strings={""},
        max_issue_examples=10,
        allow_unknown_factory_in_analysis=False,
        allow_unknown_variety_in_analysis=False,
        allow_empty_factory_in_analysis=False,
        allow_empty_variety_in_analysis=False,
        fatal_quality_thresholds=FatalQualityThresholds(),
    )
    config = ImportConfig(
        sources=[],
        rules=rules,
        factory_aliases=AliasConfig(version="test", aliases={"工厂A": "工厂A"}),
        variety_aliases=AliasConfig(version="test", aliases={"Dx": "Dx"}),
        config_hash="hash",
        snapshot={},
    )
    source = SourceSpec(path=Path("fixture.xls"), source_name="test", season_code="2025-2026")
    row = ParsedRow(
        source_sheet="Sheet1",
        source_row_number=2,
        raw_payload={},
        receipt_date_raw="2026-01-01",
        link_name_raw=None,
        farm_raw="农场A",
        subfarm_raw="分场A",
        variety_raw="Dx",
        grade_raw="优果",
        weight_kg_raw="1",
        factory_raw="工厂A",
        receipt_date=date(2026, 1, 1),
        weight_kg=Decimal("1"),
        parse_errors=[],
    )

    processed, report = process_rows(
        rows=[row, replace(row, source_row_number=3)],
        source=source,
        file_sha256="abc",
        config=config,
        factory_ids_by_name={"工厂A": 1},
        variety_ids_by_name={"Dx": 1},
        grade_ids_by_code={"优果": 1},
        existing_business_rows={
            business_fingerprint(
                season_code="2025-2026",
                receipt_date=date(2026, 1, 1),
                factory_name="工厂A",
                farm_name="农场A",
                subfarm_name="分场A",
                variety_name="Dx",
                grade_code="优果",
                weight_kg=Decimal("1"),
            ): [{"ingest_file_id": 9, "source_sheet": "History", "source_row_number": 7}]
        },
    )

    assert processed[0].is_suspected_duplicate is True
    assert processed[0].is_analysis_eligible is True
    assert "suspected_duplicate" not in processed[0].exclusion_reasons
    assert processed[1].is_suspected_duplicate is True
    assert processed[1].is_analysis_eligible is True
    assert report.cross_file_duplicate_count == 2
    assert report.cross_file_duplicate_examples
