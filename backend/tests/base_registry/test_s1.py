from datetime import date
from decimal import Decimal, localcontext

import pytest

from backend.app.base_registry.business import audit_season, business_cutoff, map_farms
from backend.app.base_registry.registry import build_registry, parse_coordinate


def record(name="基地甲", members="农场甲", area="100", coordinate="103.00,24.00"):
    return [name, members, coordinate, area]


def registry(rows=None):
    return build_registry(rows or [record()], "a" * 64)


def source(rows, start="2024-07-01", end="2025-05-01"):
    return {
        "season": "2024-2025",
        "source_hash": "b" * 64,
        "coverage_start": start,
        "coverage_end": end,
        "complete_export": True,
        "ledger_zero_semantics_authorized": True,
        "rows": rows,
        "conflicted_farms": [],
    }


def day(d, farm="农场甲", kg="1"):
    return {"canonical_farm_id": farm, "date": d, "daily_harvest_kg": kg}


def test_39_rows_deterministic_registry():
    rows = [record(f"基地{i}", f"农场{i}") for i in range(39)]
    result = registry(rows)
    assert len(result["bases"]) == 39
    assert result == registry(rows)
    assert result["hash"] == registry(list(reversed(rows)))["hash"]
    assert len({b["base_id"] for b in result["bases"]}) == 39


def test_coordinate_order_and_invalid_flags():
    assert parse_coordinate("103.00,24.00") == ("103.00", "24.00", "RANGE_VALID_CRS_UNCONFIRMED")
    for value in ("NaN,24", "0,0", "24,103", "181,24", "bad"):
        assert parse_coordinate(value)[2] == "REQUIRES_REVIEW"
    special = registry([record("乡丰蓝莓基地", coordinate="113.81,23.34")])["bases"][0]
    assert special["region_scope"] == "OUT_OF_YUNNAN"


def test_duplicate_base_rejected_and_membership_ambiguous():
    with pytest.raises(ValueError, match="duplicate base"):
        registry([record(), record()])
    result = registry([record(), record("基地乙")])
    mapping = map_farms(result, {"农场甲"}, {})
    assert mapping[0]["match_status"] == "AMBIGUOUS"
    assert mapping[0]["matched_base_id"] is None


def test_exact_alias_unresolved_no_fuzzy():
    result = registry()
    mapping = map_farms(result, {"农场甲", "旧名", "甲农场"}, {"旧名": ("农场甲", "approval")})
    assert {r["historical_farm_identity"]: r["match_status"] for r in mapping} == {
        "农场甲": "EXACT",
        "旧名": "AUTHORIZED_ALIAS",
        "甲农场": "UNRESOLVED",
    }
    with pytest.raises(ValueError, match="alias evidence"):
        map_farms(result, {"旧名"}, {"旧名": ("农场甲", "")})


def test_april_boundary_tail_preserved_prior_autumn_and_unknowns():
    rows = [
        day(d, kg=v)
        for d, v in [
            ("2024-10-01", "1"),
            ("2024-11-01", "2"),
            ("2024-12-01", "3"),
            ("2025-04-15", "4"),
            ("2025-04-16", "9"),
        ]
    ]
    result = audit_season(registry(), source(rows), {})
    audit = result["audit"][0]
    assert business_cutoff("2024-2025") == date(2025, 4, 15)
    assert audit["pre_cutoff_total_kg"] == "10.000000"
    assert audit["post_cutoff_total_kg"] == "9.000000"
    assert audit["post_cutoff_peak_exceeds_business_peak"] is True
    assert audit["yield_kg_per_mu"] is None  # unknown interior days
    tail = next(r for r in result["daily"] if r["date"] == "2025-04-16")
    assert tail["scope"] == "OUT_OF_BUSINESS_SCOPE_TAIL_FRUIT"
    assert tail["recorded_harvest_kg"] == "9.000000"
    assert (
        next(r for r in result["daily"] if r["date"] == "2024-10-02")["recorded_harvest_kg"] is None
    )


def test_zero_vs_missing_no_double_count():
    bases = registry([record(), record("基地乙", "农场乙")])
    result = audit_season(bases, source([day("2024-10-01", kg="5")]), {})
    on_date = [r for r in result["daily"] if r["date"] == "2024-10-01"]
    assert sum(Decimal(r["recorded_harvest_kg"] or "0") for r in on_date) == 5
    # Unresolved member identities never acquire an invented zero.
    assert (
        next(r for r in on_date if r["canonical_base_name"] == "基地乙")["recorded_harvest_kg"]
        is None
    )
    duplicate = registry([record(), record("基地乙")])
    audit = audit_season(duplicate, source([day("2024-10-01", kg="5")]), {})
    assert audit["excluded_total_kg"] == "5.000000"
    assert all(r["pre_cutoff_total_kg"] == "0.000000" for r in audit["audit"])


def test_complete_yield_and_missing_area():
    from datetime import timedelta

    start, end = date(2024, 7, 1), date(2025, 5, 1)
    rows = [day(str(start + timedelta(days=i)), kg="0") for i in range((end - start).days + 1)]
    next(r for r in rows if r["date"] == "2024-10-01")["daily_harvest_kg"] = "100"
    result = audit_season(registry(), source(rows), {})
    assert result["audit"][0]["yield_kg_per_mu"] == "1.000000"
    assert result["audit"][0]["coverage_status"] == "COMPLETE"
    invalid = audit_season(registry([record(area="")]), source(rows), {})
    assert invalid["audit"][0]["yield_kg_per_mu"] is None
    assert "AREA_INVALID" in invalid["audit"][0]["exclusion_reasons"]
    with localcontext() as ctx:
        ctx.prec = 6
        assert result == audit_season(registry(), source(rows), {})


def test_zero_denominator_and_duplicates():
    result = audit_season(registry(), source([day("2024-10-01", kg="0")]), {})
    assert result["audit"][0]["post_cutoff_ratio"] is None
    assert result["audit"][0]["pre_cutoff_peak_date"] is None
    with pytest.raises(ValueError, match="duplicate"):
        audit_season(registry(), source([day("2024-10-01"), day("2024-10-01")]), {})


def test_incomplete_export_cannot_zero_fill_or_yield():
    spec = source([day("2024-10-01"), day("2024-10-02", "other")])
    spec["complete_export"] = False
    result = audit_season(registry(), spec, {})
    row = next(r for r in result["daily"] if r["date"] == "2024-10-02")
    assert row["recorded_harvest_kg"] is None
    assert result["audit"][0]["yield_kg_per_mu"] is None


def test_tail_absence_not_zero_filled():
    rows = [day("2025-04-15"), day("2025-04-16", farm="other")]
    result = audit_season(registry(), source(rows), {})
    assert not any(r["date"] == "2025-04-16" for r in result["daily"])


@pytest.mark.parametrize("value", ["-1", "0", "NaN", "Infinity", "=SUM(A1:A2)"])
def test_invalid_area_not_substituted(value):
    assert registry([record(area=value)])["bases"][0]["productive_area_mu"] is None


def test_literal_formula_and_preserved_provenance():
    b = registry([record(area="=1099+391")])["bases"][0]
    assert b["productive_area_mu"] == "1490.000000"
    assert b["raw_area"] == "=1099+391"
    assert b["raw_coordinate"] == "103.00,24.00"
    assert b["coordinate_reference_system"] == "NOT_ESTABLISHED"


def test_xlsx_import_39_rows_and_source_hash(tmp_path):
    import openpyxl

    from backend.app.area_yield.experiment import file_hash
    from backend.app.base_registry.intake import import_workbook

    path = tmp_path / "synthetic.xlsx"
    book = openpyxl.Workbook()
    book.active.append(["基地名称", "覆盖农场", "经纬度", "亩数"])
    for i in range(39):
        book.active.append(record(f"synthetic-{i}", f"member-{i}"))
    book.save(path)
    book.close()
    result = import_workbook(path, file_hash(path))
    assert len(result["bases"]) == 39
    with pytest.raises(ValueError, match="hash mismatch"):
        import_workbook(path, "a" * 64)
    with pytest.raises(ValueError, match="count mismatch"):
        import_workbook(path, file_hash(path), 38)


def test_elevation_failure_and_region_geometry(monkeypatch):
    from backend.app.base_registry import intake

    def unavailable(*args, **kwargs):
        raise OSError("not available")

    monkeypatch.setattr(intake, "urlopen", unavailable)
    result = intake.fetch_elevation(registry())
    assert result["rows"][0]["elevation_m"] is None
    assert result["rows"][0]["status"] == "NOT_ESTABLISHED"
    geometry = {
        "type": "Polygon",
        "coordinates": [
            [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
            [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]],
        ],
    }
    assert intake.point_in_geometry(1, 1, geometry)
    assert not intake.point_in_geometry(5, 5, geometry)
    assert not intake.point_in_geometry(11, 11, geometry)


def test_duplicate_coordinates_and_member_tokens_preserved():
    result = registry([record(), record("基地乙", "farm B、farm C")])
    assert all(b["duplicate_coordinate"] for b in result["bases"])
    b = next(b for b in result["bases"] if b["canonical_base_name"] == "基地乙")
    assert b["covered_farms"] == ["farm B", "farm C"]


def test_shuffle_rows_and_multi_member_aggregation():
    bases = registry([record(members="农场甲、农场乙")])
    rows = [day("2024-10-01", kg="1.000001"), day("2024-10-01", "农场乙", "2.000002")]
    result = audit_season(bases, source(rows), {})
    assert result == audit_season(bases, source(list(reversed(rows))), {})
    assert result["audit"][0]["pre_cutoff_total_kg"] == "3.000003"


def test_source_margin_and_cutoff_missing_do_not_create_complete_yield():
    spec = source([day("2024-10-01")], start="2024-09-01", end="2025-04-14")
    audit = audit_season(registry(), spec, {})["audit"][0]
    assert "SOURCE_START_AFTER_SEASON_START" in audit["exclusion_reasons"]
    assert "SOURCE_END_BEFORE_CUTOFF" in audit["exclusion_reasons"]
    assert audit["yield_kg_per_mu"] is None


def test_business_confirmed_dehong_alias_exact_direction_and_single_assignment():
    import json
    from pathlib import Path

    config = json.loads(Path("configs/base_registry_s1.json").read_text())
    aliases = {k: tuple(v) for k, v in config["aliases"].items()}
    assert aliases["德宏盈江农场"] == ("腾冲德宏农场", "USER_EXPLICIT_CONFIRMATION_2026-09-14")
    assert aliases["建水南庄基地"][0] == "建水南庄农场"
    bases = registry(
        [
            record("腾冲德宏基地", "腾冲德宏农场"),
            record("其他基地", "其他农场"),
        ]
    )
    mapping = map_farms(bases, {"德宏盈江农场", "德宏盈江一场", "德宏盈江农场 "}, aliases)
    accepted = [r for r in mapping if r["matched_base_id"] is not None]
    assert len(accepted) == 1
    assert accepted[0]["historical_farm_identity"] == "德宏盈江农场"
    assert accepted[0]["normalized_identity"] == "腾冲德宏农场"
    assert accepted[0]["canonical_base_name"] == "腾冲德宏基地"
    assert accepted[0]["match_status"] == "AUTHORIZED_ALIAS"
    assert all(r["match_status"] == "UNRESOLVED" for r in mapping if r not in accepted)
    with pytest.raises(ValueError, match="alias evidence"):
        map_farms(bases, {"德宏盈江农场"}, {"德宏盈江农场": ("腾冲德宏农场", "")})
    result = audit_season(bases, source([day("2024-10-01", "德宏盈江农场", "12.5")]), aliases)
    assert result["excluded_total_kg"] == "0.000000"
    assert sum(Decimal(r["pre_cutoff_total_kg"]) for r in result["audit"]) == Decimal("12.5")
    assert (
        next(r for r in result["audit"] if r["canonical_base_name"] == "腾冲德宏基地")[
            "resolved_member_farm_count"
        ]
        == 1
    )
