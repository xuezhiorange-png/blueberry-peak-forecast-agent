from __future__ import annotations

from pathlib import Path

from scripts.build_v0_8_area_source_inventory import (
    deduplicate_source_records,
    discover_area_candidates,
    enumerate_files,
    evaluate_completeness,
    file_differences,
)


def _scan(root: Path, output: Path) -> tuple[list[dict], int, list[str]]:
    roots = [{"path": root.as_posix(), "root_ids": ["fixture"], "root_type": "TEST_ROOT"}]
    return enumerate_files(roots, {".git", "__pycache__"}, output)


def test_same_search_roots_and_files_produce_identical_discovery_rows(tmp_path: Path) -> None:
    root = tmp_path / "sources"
    root.mkdir()
    (root / "historical_area.csv").write_text(
        "farm,season,area_mu\nA,2023-2024,12\n", encoding="utf-8"
    )
    output = tmp_path / "private-output"

    first_files, first_count, first_errors = _scan(root, output)
    first = discover_area_candidates(first_files, {".csv"}, ["area", "亩"])
    second_files, second_count, second_errors = _scan(root, output)
    second = discover_area_candidates(second_files, {".csv"}, ["area", "亩"])

    assert first_count == second_count == 1
    assert first_errors == second_errors == []
    assert first == second


def test_new_area_source_file_is_discovered(tmp_path: Path) -> None:
    root = tmp_path / "sources"
    root.mkdir()
    new_source = root / "season_area.csv"
    new_source.write_text("farm,season,productive_area_mu\nA,2024-2025,20\n", encoding="utf-8")

    files, _, errors = _scan(root, tmp_path / "output")
    candidates = discover_area_candidates(files, {".csv"}, ["productive_area_mu", "亩"])

    assert errors == []
    assert [row["file_path"] for row in candidates] == [new_source.resolve().as_posix()]


def test_removed_old_source_is_explicitly_reported(tmp_path: Path) -> None:
    missing = (tmp_path / "removed_area.xlsx").as_posix()

    diff = file_differences({missing}, set(), set(), {})

    assert diff == [
        {
            "diff_status": "OLD_FILE_NOT_REDISCOVERED",
            "file_path": missing,
            "file_sha256": "",
            "record_count": 0,
            "detail": "source_file_path_membership",
        }
    ]


def test_identical_source_copy_keeps_one_logical_record(tmp_path: Path) -> None:
    first = tmp_path / "area.xlsx"
    duplicate = tmp_path / "area_copy.xlsx"
    first.write_bytes(b"same workbook bytes")
    duplicate.write_bytes(first.read_bytes())
    digest = "sha256-of-identical-source"
    rows = [
        {
            "record_id": "row-a",
            "source_file": first.as_posix(),
            "source_hash": digest,
            "sheet": "Sheet1",
            "source_row": "2",
            "source_original_name": "Farm A",
            "season": "2024-2025",
            "area_mu": "20",
            "area_semantics": "PLANNED_AREA",
        },
        {
            "record_id": "row-copy",
            "source_file": duplicate.as_posix(),
            "source_hash": digest,
            "sheet": "Sheet1",
            "source_row": "2",
            "source_original_name": "Farm A",
            "season": "2024-2025",
            "area_mu": "20",
            "area_semantics": "PLANNED_AREA",
        },
    ]

    rebuilt = deduplicate_source_records(rows)

    assert len(rebuilt) == 1
    assert rebuilt[0]["source_file"] == first.as_posix()


def test_current_and_planned_semantics_remain_inventory_rows_not_authority(tmp_path: Path) -> None:
    rows = [
        {
            "record_id": "current",
            "source_file": (tmp_path / "current.csv").as_posix(),
            "source_hash": "hash-current",
            "source_row": "2",
            "season": "CURRENT/UNSPECIFIED",
            "area_mu": "30",
            "area_semantics": "CURRENT_AREA",
            "authority_eligibility": "NO",
        },
        {
            "record_id": "planned",
            "source_file": (tmp_path / "planned.csv").as_posix(),
            "source_hash": "hash-planned",
            "source_row": "3",
            "season": "2025-2026",
            "area_mu": "40",
            "area_semantics": "PLANNED_AREA",
            "authority_eligibility": "NO",
        },
    ]

    rebuilt = deduplicate_source_records(rows)

    assert {row["area_semantics"] for row in rebuilt} == {"CURRENT_AREA", "PLANNED_AREA"}
    assert all(row["authority_eligibility"] == "NO" for row in rebuilt)


def test_files_outside_explicit_roots_are_not_enumerated(tmp_path: Path) -> None:
    root = tmp_path / "in-scope"
    outside = tmp_path / "out-of-scope"
    root.mkdir()
    outside.mkdir()
    (root / "in_scope_area.csv").write_text("area_mu\n1\n", encoding="utf-8")
    (outside / "outside_area.csv").write_text("area_mu\n999\n", encoding="utf-8")

    files, count, errors = _scan(root, tmp_path / "output")
    candidates = discover_area_candidates(files, {".csv"}, ["area_mu"])

    assert count == 1
    assert errors == []
    assert len(candidates) == 1
    assert candidates[0]["file_path"].endswith("in_scope_area.csv")


def test_rebuild_difference_cannot_be_reported_as_completeness_pass(tmp_path: Path) -> None:
    old_file = (tmp_path / "old.csv").as_posix()
    newly_parsed = (tmp_path / "new.csv").as_posix()

    result = evaluate_completeness(
        old_source_paths={old_file},
        discovered_candidate_paths={old_file, newly_parsed},
        rebuilt_source_paths={old_file, newly_parsed},
        unclassified_candidate_count=0,
        scan_errors=[],
    )

    assert result["completeness_proven"] is False
    assert result["new_source_files_not_in_old"] == [newly_parsed]
    file_diff = file_differences({old_file}, {old_file, newly_parsed}, {old_file, newly_parsed}, {})
    assert any(
        row["file_path"] == newly_parsed and row["diff_status"] == "NEW_FILE_NOT_IN_OLD"
        for row in file_diff
    )


def test_unclassified_candidate_blocks_completeness(tmp_path: Path) -> None:
    path = (tmp_path / "unclassified.xls").as_posix()

    result = evaluate_completeness(
        old_source_paths=set(),
        discovered_candidate_paths={path},
        rebuilt_source_paths=set(),
        unclassified_candidate_count=1,
        scan_errors=[],
    )

    assert result["completeness_proven"] is False
    assert result["unclassified_candidate_count"] == 1
