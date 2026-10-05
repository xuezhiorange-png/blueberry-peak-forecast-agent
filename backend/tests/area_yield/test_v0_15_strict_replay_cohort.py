"""Synthetic admission tests: no private inputs, labels, network or database."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.audit_v0_15_s0_existing_assets import validate_public
from scripts.audit_v0_15_strict_replay_cohort import (
    classify_label,
    encoded,
    generate,
    intersect,
    sha,
)


def complete() -> dict:
    return {
        "target_start_date": "2025-07-22",
        "target_end_date": "2026-04-15",
        "logical_record_count": 268,
        "unknown_count": 0,
        "partial_subtotal_count": 0,
        "missing_count": 0,
        "conflict_count": 0,
        "invalid_count": 0,
    }


def test_complete_label_is_not_pit_admission() -> None:
    assert classify_label(complete()) == "LABEL_COMPLETE"
    ready, reasons = intersect("C", "ACCEPTED_RETROSPECTIVE_PIT_UNPROVEN", "LABEL_COMPLETE")
    assert not ready
    assert reasons == ["AREA_PIT_UNPROVEN", "IDENTITY_PIT_UNPROVEN"]


@pytest.mark.parametrize("field", ["unknown_count", "partial_subtotal_count", "missing_count"])
def test_unknown_partial_missing_not_complete(field: str) -> None:
    row = complete()
    row[field] = 1
    assert classify_label(row) == "LABEL_PARTIAL"


@pytest.mark.parametrize("field", ["conflict_count", "invalid_count"])
def test_conflicting_invalid_not_peak_usable(field: str) -> None:
    row = complete()
    row[field] = 1
    assert classify_label(row) == "LABEL_UNUSABLE_FOR_PEAK_SCORING"


def test_count_does_not_prove_complete_if_short() -> None:
    row = complete()
    row["logical_record_count"] -= 1
    assert classify_label(row) == "LABEL_PARTIAL"


def test_duplicate_aggregate_count_fails_closed() -> None:
    row = complete()
    row["logical_record_count"] += 1
    assert classify_label(row) == "LABEL_UNUSABLE_FOR_PEAK_SCORING"


def test_no_label_values_required_or_mutated() -> None:
    row = complete()
    before = deepcopy(row)
    classify_label(row)
    assert row == before


@pytest.mark.parametrize("area", ["A", "B"])
@pytest.mark.parametrize("identity", ["STRICT", "ASSUMED_FROZEN"])
def test_proven_or_explicitly_frozen_evidence_only(area: str, identity: str) -> None:
    assert intersect(area, identity, "LABEL_COMPLETE") == (True, [])


@pytest.mark.parametrize("identity", ["FUZZY", "UNRESOLVED", "ACCEPTED_RETROSPECTIVE"])
def test_no_retrospective_or_fuzzy_upgrade(identity: str) -> None:
    assert not intersect("A", identity, "LABEL_COMPLETE")[0]


def test_complete_input_not_blanket_unknown_zero() -> None:
    row = complete()
    row["unknown_count"] = -1
    with pytest.raises(ValueError, match="INVALID_STATE_COUNT"):
        classify_label(row)


def test_partial_label_never_admitted() -> None:
    assert not intersect("A", "STRICT", "LABEL_PARTIAL")[0]


def test_committed_report_hashes_and_immutable_output(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[3]
    first = repo / "docs/v0-15/evidence/strict-pit-replay-cohort-closure-r1"
    for path in first.iterdir():
        validate_public(json.loads(path.read_bytes()))
    manifest = json.loads((first / "manifest.json").read_bytes())
    expected = manifest.pop("manifest_hash")
    assert sha(encoded(manifest)) == expected
    for member in manifest["members"]:
        assert sha((first / member["name"]).read_bytes()) == member["sha256"]
    cohort = json.loads((first / "strict-replay-cohort.json").read_bytes())
    assert len(cohort["rows"]) == 39
    assert cohort["eligible_members"] == []
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "existing.json").write_text("{}")
    with pytest.raises(ValueError, match="IMMUTABLE_OUTPUT_EXISTS"):
        generate(repo, occupied)


@pytest.mark.parametrize("value", [{"private_path": "x"}, {"coordinates": []}])
def test_private_fields_rejected(value: dict) -> None:
    with pytest.raises(ValueError, match="PUBLIC_PRIVATE_FIELD"):
        validate_public(value)
