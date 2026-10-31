import csv
import io
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from backend.app.etl.history import privacy_boundary as boundary

pytestmark = [pytest.mark.unit, pytest.mark.contract]
ROOT = Path(__file__).resolve().parents[3]


def test_all_original_identities_are_preserved_without_publication_clearance():
    report = boundary.classify(ROOT)
    with (ROOT / boundary.INPUT_PATHS[0]).open() as f:
        original = list(csv.DictReader(f))
    assert len(report.rows) == 1658
    assert [r["PATH"] for r in report.rows] == [r["PATH"] for r in original]
    for before, after in zip(original, report.rows, strict=True):
        assert all(after[k] == v for k, v in before.items())
        assert after["REVIEW_STATE"] == "UNVERIFIED"
        assert after["PUBLICATION_PERMISSION"] == "NOT_ESTABLISHED"
        assert after["CLASSIFICATION"] in boundary.CLASSES
    assert Counter(r["ASSET_CLASS"] for r in report.rows) == boundary.EXPECTED_COUNTS
    assert len(report.decisions) == 9
    assert len(report.priority) <= 20


def test_schema_role_is_not_confirmed_sensitive_and_synthetic_label_is_not_proof():
    row = {
        "PATH": "backend/app/SYNTHETIC_ONLY.py",
        "ASSET_CLASS": "CODE_SCHEMA_OR_POSSIBLE_LITERAL",
        "DISCLOSURE_CATEGORY": "QUANTITY_AREA_OR_COMMERCIAL_STATISTIC",
        "HISTORICAL_CONTRACT_DEPENDENCY": "NOT_PROVEN",
    }
    out = boundary.classify_row(row)
    assert out["CLASSIFICATION"] == "PUBLIC_CODE"
    assert out["REVIEW_STATE"] == "UNVERIFIED"
    row["ASSET_CLASS"] = "FROZEN_REPORT_OR_EVIDENCE"
    assert boundary.classify_row(row)["CLASSIFICATION"] == "FROZEN_HISTORICAL_EVIDENCE"
    row["ASSET_CLASS"] = "COMPRESSED_FIXTURE_METADATA_ONLY"
    assert boundary.classify_row(row)["CLASSIFICATION"] == "COMPRESSED_CONTENT_NOT_INSPECTED"


def test_priority_is_deterministic_and_not_error_or_production_performance_selection():
    a = boundary.classify(ROOT)
    b = boundary.classify(ROOT)
    assert a == b
    paths = [r["PATH"] for r in a.priority]
    assert "configs/factory_aliases.yaml" in paths
    assert "configs/base_registry_s1.json" in paths
    assert "configs/v0_5_base_reference_registry_v1.json" in paths
    assert len(set(paths)) == len(paths)
    assert all(r["EVIDENCE_STRENGTH"] != "CONFIRMED_LEAK" for r in a.rows)


def test_inputs_cannot_be_changed_into_a_new_publication_baseline(tmp_path):
    for name in boundary.INPUT_PATHS:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    (tmp_path / boundary.INPUT_PATHS[0]).write_text("PATH,ASSET_CLASS\nSYNTHETIC_ONLY,APPROVED\n")
    with pytest.raises(ValueError, match="PINNED_INPUT_CHANGED"):
        boundary.classify(tmp_path)


def test_output_registry_contains_metadata_only_and_ref_inventory_is_reused():
    report = boundary.classify(ROOT)
    rows = list(csv.DictReader(io.StringIO(report.csv_text())))
    assert len(rows) == 1658
    assert len(report.ref_rows) == 742
    assert len([r for r in report.ref_rows if r["ref"].startswith("refs/tags/")]) == 23
    assert all("deletion_authorized" not in r for r in rows)
    assert "business_value" not in json.dumps(report.summary())


def test_committed_review_outputs_are_reproducible_and_compressed_objects_are_metadata_only():
    for name, content in boundary.outputs(ROOT).items():
        assert (ROOT / "docs/tech-debt" / name).read_bytes() == content
    report = boundary.classify(ROOT)
    assert len(report.compressed_metadata) == 5
    assert all(
        r["evidence"] == "GIT_TREE_METADATA_ONLY_CONTENT_NOT_OPENED"
        for r in report.compressed_metadata
    )


def test_cli_outputs_match_across_independent_processes_without_time_or_directory_drift(tmp_path):
    destinations = [tmp_path / "first", tmp_path / "second"]
    for destination in destinations:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "backend.app.etl.history.privacy_boundary",
                "--repo",
                str(ROOT),
                "--output-dir",
                str(destination),
            ],
            cwd=ROOT,
            env={**os.environ, "GIT_NO_LAZY_FETCH": "1"},
            capture_output=True,
            text=True,
            check=True,
        )
        assert json.loads(completed.stdout)["public_authorization_granted"] is False
    for name, content in boundary.outputs(ROOT).items():
        assert (
            (destinations[0] / name).read_bytes()
            == (destinations[1] / name).read_bytes()
            == content
        )
