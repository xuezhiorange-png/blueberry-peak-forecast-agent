from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts.build_v0_8_area_source_inventory import (
    InventoryError,
    classify_candidates,
    compare_canonical_records,
    deduplicate_source_records,
    discover_area_candidates,
    duplicate_business_field_parity,
    duplicate_business_fields_consistent,
    enumerate_files,
    evaluate_completeness,
    file_differences,
    inspect_structured_area_schema,
    reconcile_old_source_paths,
    reconcile_prior_review_cohort,
    resolve_structured_scan_errors,
    review_required_count,
    verify_historical_prior_review_blobs,
)


def _scan(root: Path, output: Path) -> tuple[list[dict[str, Any]], int, list[str]]:
    roots = [{"path": root.as_posix(), "root_ids": ["fixture"], "root_type": "TEST_ROOT"}]
    return enumerate_files(roots, {".git", "__pycache__"}, output)


def test_enumerator_skips_only_explicit_generated_output_paths(tmp_path: Path) -> None:
    root = tmp_path / "sources"
    root.mkdir()
    retained = root / "input.csv"
    retained.write_text("data\n", encoding="utf-8")
    ignored = root / "generated-report.json"
    ignored.write_text("{}\n", encoding="utf-8")
    roots = [{"path": root.as_posix(), "root_ids": ["fixture"], "root_type": "TEST_ROOT"}]

    rows, enumerated_count, errors = enumerate_files(
        roots,
        set(),
        tmp_path / "output",
        ignored_file_paths={ignored.resolve().as_posix()},
    )

    assert enumerated_count == 1
    assert [row["file_path"] for row in rows] == [retained.resolve().as_posix()]
    assert errors == []


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
        review_required_candidate_count=0,
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
        review_required_candidate_count=1,
        scan_errors=[],
    )

    assert result["completeness_proven"] is False
    assert result["review_required_candidate_count"] == 1


def test_review_gate_counts_other_and_unclassified_together() -> None:
    categories = {"EXCLUDED_OTHER": 1, "UNCLASSIFIED_CANDIDATE": 1}

    assert review_required_count(categories) == 2
    result = evaluate_completeness(
        old_source_paths=set(),
        discovered_candidate_paths=set(),
        rebuilt_source_paths=set(),
        review_required_candidate_count=review_required_count(categories),
        scan_errors=[],
    )
    assert result["completeness_proven"] is False


def test_only_unclassified_candidates_still_block_completeness() -> None:
    categories = {"UNCLASSIFIED_CANDIDATE": 1}

    result = evaluate_completeness(
        old_source_paths=set(),
        discovered_candidate_paths=set(),
        rebuilt_source_paths=set(),
        review_required_candidate_count=review_required_count(categories),
        scan_errors=[],
    )

    assert result["completeness_proven"] is False


def _record(
    record_id: str, source_file: str, *, area_mu: str = "20", season: str = "2024-2025"
) -> dict[str, str]:
    return {
        "record_id": record_id,
        "source_file": source_file,
        "source_hash": "source-sha",
        "sheet": "Sheet1",
        "source_row": "2",
        "source_original_name": "Farm A",
        "farm_identity": "Farm A",
        "base_identity": "Base A",
        "season": season,
        "grain": "FARM",
        "area_mu": area_mu,
        "original_column_name": "亩数",
        "original_wording": "2024-2025",
        "area_semantics": "HISTORICAL_ACTUAL",
        "area_basis": "SOURCE_DOCUMENT",
        "identity_mapping_status": "EXACT",
        "mapped_farm": "Farm A",
        "mapped_base_id": "base-a",
        "mapped_base": "Base A",
        "authority_eligibility": "NO",
        "decision": "REVIEW_ONLY",
        "notes": "fixture",
    }


def test_old_and_new_raw_differ_but_same_canonical_rows_match() -> None:
    old = [
        _record("a1", "/source/a.xlsx"),
        _record("a2", "/source/a-copy.xlsx"),
        _record("b", "/source/b.xlsx", area_mu="30", season="2023-2024"),
    ]
    new = [
        _record("a", "/source/a.xlsx"),
        _record("b", "/source/b.xlsx", area_mu="30", season="2023-2024"),
    ]

    result = compare_canonical_records(old, new)

    assert result["old_raw_record_count"] == 3
    assert result["new_raw_record_count"] == 2
    assert result["old_canonical_record_count"] == result["new_canonical_record_count"] == 2
    assert result["old_duplicate_rows_removed"] == 1
    assert result["canonical_record_parity"] is True


def test_business_field_difference_prevents_duplicate_collapse() -> None:
    first = _record("a1", "/source/a.xlsx", area_mu="20")
    changed = _record("a2", "/source/a-copy.xlsx", area_mu="21")
    rows = [first, changed]

    assert duplicate_business_fields_consistent(rows) is True
    result = compare_canonical_records(rows, rows)
    assert result["old_canonical_record_count"] == 2
    assert result["old_duplicate_rows_removed"] == 0


def test_duplicate_business_field_parity_is_explicitly_audited() -> None:
    first = _record("a1", "/source/a.xlsx")
    byte_copy = _record("a2", "/source/a-copy.xlsx")

    parity_rows = duplicate_business_field_parity([first, byte_copy])

    assert len(parity_rows) == 1
    assert parity_rows[0]["duplicate_row_count"] == 2
    assert parity_rows[0]["duplicate_rows_removed"] == 1
    assert parity_rows[0]["business_field_parity"] is True
    assert parity_rows[0]["differing_business_fields"] == ""


def test_old_path_with_matching_sha_is_redirected_not_logically_missing(tmp_path: Path) -> None:
    root = tmp_path / "search"
    root.mkdir()
    old_path = root / "old-name.xlsx"
    new_path = root / "renamed.xlsx"
    new_path.write_bytes(b"same source bytes")
    digest = hashlib.sha256(new_path.read_bytes()).hexdigest()
    discovered = [
        {
            "file_path": new_path.resolve().as_posix(),
            "file_sha256": digest,
            "scan_status": "CONTENT_SCANNED",
            "candidate_reason": "KEYWORD_MATCH:area",
        }
    ]

    rows = reconcile_old_source_paths(
        old_source_paths={old_path.as_posix()},
        old_path_to_digest={old_path.resolve().as_posix(): digest},
        discovered_rows=discovered,
        legacy_parser_paths=set(),
        search_roots=[{"path": root.as_posix()}],
        prior_discovery_paths=set(),
        prior_search_keywords=["area"],
    )

    assert rows[0]["path_status"] == "OLD_PATH_NOT_REDISCOVERED_BUT_CONTENT_PRESENT"
    assert rows[0]["rediscovered_path"] == new_path.resolve().as_posix()


def test_reconciliation_explains_structural_discovery_missed_by_r1(tmp_path: Path) -> None:
    source = tmp_path / "old-name.xlsx"
    source.write_bytes(b"fixture workbook bytes")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    path = source.resolve().as_posix()
    discovered = [
        {
            "file_path": path,
            "file_sha256": digest,
            "scan_status": "STRUCTURE_SCANNED",
            "candidate_reason": "STRUCTURAL_AREA_SCHEMA",
        }
    ]

    rows = reconcile_old_source_paths(
        old_source_paths={path},
        old_path_to_digest={path: digest},
        discovered_rows=discovered,
        legacy_parser_paths=set(),
        search_roots=[{"path": tmp_path.resolve().as_posix()}],
        prior_discovery_paths=set(),
        prior_search_keywords=[],
    )

    assert rows[0]["path_status"] == "OLD_PATH_REDISCOVERED"
    assert "R1 scan found neither filename nor content keyword" in rows[0]["why_not_discovered"]


def test_pdf_cad_creator_is_a_deterministic_engineering_exclusion() -> None:
    candidate = {
        "file_path": "/source/facility/undated-layout.pdf",
        "file_sha256": "cad-pdf-hash",
        "source_category": "UNCLASSIFIED_CANDIDATE",
        "candidate_reason": "CONTENT_SCAN_FAILED",
        "included_in_inventory": False,
        "exclusion_reason": "",
        "logical_source_identity": "CONTENT_SHA256:cad-pdf-hash",
        "scan_status": "CONTENT_SCAN_LIMIT_EXCEEDED",
        "pdf_metadata": {"creator": "Gcad"},
    }

    classified = classify_candidates([candidate], set(), set(), {})[0]

    assert classified["source_category"] == "EXCLUDED_ENGINEERING_AREA"
    assert classified["classification_rule_id"] == "R2-014"
    assert classified["classification_reason"] == "ENGINEERING_OR_FACILITY_DOCUMENT"
    assert classified["classification_evidence"] == "PDF creator metadata=gcad"
    assert classified["review_required"] is False


def test_structured_decoder_error_needs_independent_exclusion_evidence() -> None:
    source_path = "/source/maintenance/点检表.xls"
    error = (
        "STRUCTURED_SCAN_UNAVAILABLE:"
        + source_path
        + ":STRUCTURE_SCAN_UNAVAILABLE:UnicodeDecodeError"
    )
    report_candidate = {
        "file_path": source_path,
        "classification_rule_id": "R2-010",
        "classification_reason": "REPORT_OR_TRAINING_DOCUMENT_NOT_SOURCE_ROWS",
        "classification_evidence": "maintenance checklist filename/path",
    }
    uncertain_candidate = {
        **report_candidate,
        "classification_rule_id": "R2-012",
    }

    resolved, unresolved = resolve_structured_scan_errors([error], [report_candidate])
    assert len(resolved) == 1
    assert resolved[0]["scan_status"] == "UnicodeDecodeError"
    assert unresolved == []

    resolved, unresolved = resolve_structured_scan_errors([error], [uncertain_candidate])
    assert resolved == []
    assert unresolved == [error]


def test_model_timing_diagnostic_is_not_reclassified_as_raw_area_source(tmp_path: Path) -> None:
    source = tmp_path / "phenology-anchored-temporal-model-r6" / "per_base_timing_r6.csv"
    source.parent.mkdir()
    source.write_text("base,area_mu,timing\nA,25,2025-09-01\n", encoding="utf-8")
    candidate = {
        "file_path": source.as_posix(),
        "file_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "source_category": "UNCLASSIFIED_CANDIDATE",
        "candidate_reason": "KEYWORD_MATCH:area",
        "included_in_inventory": False,
        "exclusion_reason": "",
        "logical_source_identity": "CONTENT_SHA256:test",
        "scan_status": "CONTENT_SCANNED",
    }

    classified = classify_candidates([candidate], set(), set(), {})[0]

    assert classified["source_category"] == "EXCLUDED_GENERATED_DERIVATIVE"
    assert classified["classification_rule_id"] == "R2-004"
    assert classified["review_required"] is False


def test_review_required_candidate_blocks_completeness() -> None:
    result = evaluate_completeness(
        old_source_paths=set(),
        discovered_candidate_paths={"candidate.xlsx"},
        rebuilt_source_paths=set(),
        review_required_candidate_count=1,
        scan_errors=[],
    )

    assert result["completeness_proven"] is False


def test_unreconciled_prior_review_candidate_blocks_completeness() -> None:
    result = evaluate_completeness(
        old_source_paths=set(),
        discovered_candidate_paths=set(),
        rebuilt_source_paths=set(),
        review_required_candidate_count=0,
        scan_errors=[],
        prior_review_cohort_unreconciled_count=1,
    )

    assert result["completeness_proven"] is False


def _prior_review_row(path: str, digest: str) -> dict[str, str]:
    return {
        "file_path": path,
        "file_sha256": digest,
        "source_category": "EXCLUDED_OTHER",
    }


def _classified_candidate(path: str, digest: str) -> dict[str, str]:
    return {
        "file_path": path,
        "file_sha256": digest,
        "source_category": "EXCLUDED_GENERATED_DERIVATIVE",
        "classification_rule_id": "R2-004",
        "classification_reason": "GENERATED_MODEL_OR_EVIDENCE_ARTIFACT",
        "classification_evidence": "structured report/evidence artifact classification",
        "scan_status": "CONTENT_SCANNED",
    }


def test_prior_review_exact_and_historical_same_path_candidates_reconcile() -> None:
    exact_path = "/repo/docs/generated/one.json"
    changed_path = "/repo/docs/evidence/two.json"
    prior_manifest = {
        "files": [
            _prior_review_row(exact_path, "same-sha"),
            _prior_review_row(changed_path, "old-sha"),
        ]
    }
    historical = {
        changed_path: {
            "sha256": "old-sha",
            "git_revision": "frozen-revision",
            "classification_rule_id": "R2-004",
            "classification_reason": "HISTORICAL_GENERATED_EVIDENCE_JSON",
            "classification_evidence": "verified historical evidence JSON",
        }
    }

    rows, stats = reconcile_prior_review_cohort(
        prior_manifest,
        [
            _classified_candidate(exact_path, "same-sha"),
            _classified_candidate(changed_path, "new-sha"),
        ],
        historical,
    )

    assert stats["prior_review_cohort_count"] == 2
    assert stats["exact_path_hash_reclassified_count"] == 1
    assert stats["same_path_bytes_changed_reclassified_count"] == 1
    assert stats["historical_prior_git_blob_verified_count"] == 1
    assert stats["unresolved_count"] == 0
    changed_row = next(row for row in rows if row["r1_source_sha256"] == "old-sha")
    assert (
        changed_row["reconciliation_status"] == "SAME_PATH_BYTES_CHANGED_HISTORICAL_BLOB_VERIFIED"
    )


def test_changed_prior_review_path_without_historical_hash_proof_stays_unresolved() -> None:
    path = "/repo/docs/evidence/changed.json"
    rows, stats = reconcile_prior_review_cohort(
        {"files": [_prior_review_row(path, "old-sha")]},
        [_classified_candidate(path, "new-sha")],
    )

    assert rows[0]["reconciliation_status"] == "PRIOR_REVIEW_ITEM_UNRESOLVED"
    assert stats["unresolved_count"] == 1


def test_missing_prior_review_path_and_hash_stay_unresolved() -> None:
    rows, stats = reconcile_prior_review_cohort(
        {"files": [_prior_review_row("/repo/missing.xlsx", "missing-sha")]},
        [],
    )

    assert rows[0]["reconciliation_status"] == "PRIOR_REVIEW_ITEM_UNRESOLVED"
    assert stats["unresolved_count"] == 1


def test_prior_review_git_blob_verifier_pins_hash_and_json_evidence(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "audit@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Audit Test"], cwd=repo, check=True)
    relative = Path("docs/evidence/report.json")
    source = repo / relative
    source.parent.mkdir(parents=True)
    contents = json.dumps(
        {"task_id": "REPORT_TASK", "result": {}, "recovery": {}, "private_artifacts": {}},
        sort_keys=True,
    ).encode("utf-8")
    source.write_bytes(contents)
    subprocess.run(["git", "add", relative.as_posix()], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "add evidence"], cwd=repo, check=True)
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    path = source.resolve().as_posix()
    digest = hashlib.sha256(contents).hexdigest()
    prior_manifest = {"files": [_prior_review_row(path, digest)]}
    spec: dict[str, Any] = {
        "repo_relative_path": relative.as_posix(),
        "expected_sha256": digest,
        "git_revision": revision,
        "expected_task_id": "REPORT_TASK",
        "required_top_level_keys": ["task_id", "result", "recovery", "private_artifacts"],
        "classification_rule_id": "R2-004",
    }

    verified = verify_historical_prior_review_blobs(
        repo_root=repo,
        prior_discovery_manifest=prior_manifest,
        specifications=[spec],
    )

    assert verified[path]["sha256"] == digest
    assert verified[path]["classification_rule_id"] == "R2-004"

    with pytest.raises(InventoryError, match="PRIOR_REVIEW_GIT_BLOB_HASH_MISMATCH"):
        verify_historical_prior_review_blobs(
            repo_root=repo,
            prior_discovery_manifest={"files": [_prior_review_row(path, "0" * 64)]},
            specifications=[{**spec, "expected_sha256": "0" * 64}],
        )


def test_unreadable_area_candidate_remains_review_required() -> None:
    candidate = {
        "file_path": "/source/legacy/unknown.xls",
        "file_sha256": "unreadable-hash",
        "source_category": "UNCLASSIFIED_CANDIDATE",
        "candidate_reason": "CONTENT_SCAN_FAILED",
        "included_in_inventory": False,
        "exclusion_reason": "",
        "logical_source_identity": "CONTENT_SHA256:unreadable-hash",
        "scan_status": "CONTENT_SCAN_LIMIT_EXCEEDED",
    }

    classified = classify_candidates([candidate], set(), set(), {})[0]

    assert classified["source_category"] == "REVIEW_REQUIRED"
    assert classified["classification_rule_id"] == "R2-012"
    assert classified["review_required"] is True


def test_pinned_legacy_non_source_exclusions_use_category_specific_rules() -> None:
    no_area_path = "/source/harvest-only.csv"
    unsupported_path = "/source/non-text-planning.pdf"
    candidates = [
        {
            "file_path": no_area_path,
            "file_sha256": "no-area-hash",
            "source_category": "UNCLASSIFIED_CANDIDATE",
            "candidate_reason": "LEGACY_EXCLUSION",
            "included_in_inventory": False,
            "exclusion_reason": "",
            "logical_source_identity": "CONTENT_SHA256:no-area-hash",
            "scan_status": "CONTENT_SCANNED",
        },
        {
            "file_path": unsupported_path,
            "file_sha256": "unsupported-hash",
            "source_category": "UNCLASSIFIED_CANDIDATE",
            "candidate_reason": "LEGACY_EXCLUSION",
            "included_in_inventory": False,
            "exclusion_reason": "",
            "logical_source_identity": "CONTENT_SHA256:unsupported-hash",
            "scan_status": "CONTENT_SCAN_LIMIT_EXCEEDED",
        },
    ]

    classified = classify_candidates(
        candidates,
        set(),
        set(),
        {
            no_area_path: "HARVEST_ONLY_NO_AREA_COLUMNS",
            unsupported_path: "NON_TEXT_PLANNING_PDF",
        },
    )

    assert classified[0]["source_category"] == "EXCLUDED_NO_AREA_FIELD"
    assert classified[0]["classification_rule_id"] == "R2-015"
    assert classified[1]["source_category"] == "EXCLUDED_UNSUPPORTED_FORMAT"
    assert classified[1]["classification_rule_id"] == "R2-016"
    assert all(
        row["classification_evidence"] == "pinned legacy exclusion manifest" for row in classified
    )


def test_template_and_fixture_categories_match_their_registered_rules() -> None:
    template_path = "/source/templates/area-confirmation-template.csv"
    fixture_path = "/source/backend/tests/area_yield/area_fixture.csv"
    candidates = [
        {
            "file_path": template_path,
            "file_sha256": "template-hash",
            "source_category": "UNCLASSIFIED_CANDIDATE",
            "candidate_reason": "KEYWORD_MATCH:area",
            "included_in_inventory": False,
            "exclusion_reason": "",
            "logical_source_identity": "CONTENT_SHA256:template-hash",
            "scan_status": "CONTENT_SCANNED",
        },
        {
            "file_path": fixture_path,
            "file_sha256": "fixture-hash",
            "source_category": "UNCLASSIFIED_CANDIDATE",
            "candidate_reason": "KEYWORD_MATCH:area",
            "included_in_inventory": False,
            "exclusion_reason": "",
            "logical_source_identity": "CONTENT_SHA256:fixture-hash",
            "scan_status": "CONTENT_SCANNED",
        },
    ]

    classified = classify_candidates(candidates, set(), set(), {})
    by_path = {row["file_path"]: row for row in classified}

    assert by_path[template_path]["source_category"] == "EXCLUDED_TEMPLATE"
    assert by_path[template_path]["classification_rule_id"] == "R2-017"
    assert by_path[fixture_path]["source_category"] == "EXCLUDED_TEST_FIXTURE"
    assert by_path[fixture_path]["classification_rule_id"] == "R2-003"


def test_zero_review_and_logical_record_parity_can_pass() -> None:
    result = evaluate_completeness(
        old_source_paths={"source.xlsx"},
        discovered_candidate_paths={"source.xlsx"},
        rebuilt_source_paths={"source.xlsx"},
        review_required_candidate_count=0,
        scan_errors=[],
        canonical_record_parity=True,
    )

    assert result["completeness_proven"] is True


def test_new_farm_area_source_requires_s3_rebuild_before_completeness_pass() -> None:
    result = evaluate_completeness(
        old_source_paths=set(),
        discovered_candidate_paths={"new-farm-area.xlsx"},
        rebuilt_source_paths=set(),
        review_required_candidate_count=0,
        scan_errors=[],
        canonical_record_parity=True,
        new_area_source_found=True,
    )

    assert result["completeness_proven"] is False


def test_structural_workbook_detection_finds_legacy_factory_area_without_keywords(
    tmp_path: Path,
) -> None:
    from openpyxl import Workbook

    path = tmp_path / "season-report.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["加工厂", "亩数"])
    sheet.append(["Factory A", 25])
    workbook.save(path)

    result = inspect_structured_area_schema(path)

    assert result["scan_status"] == "STRUCTURE_SCANNED"
    assert result["findings"][0]["grain"] == "PROCESSING_FACTORY"
    assert result["findings"][0]["area_unit_class"] == "MU_OR_AREA_MU_FIELD"
