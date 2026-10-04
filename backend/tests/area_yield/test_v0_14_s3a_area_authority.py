"""Synthetic and committed-public-only S3A authority contracts."""

import json
from pathlib import Path

import pytest

from scripts.materialize_v0_14_s3a_area_authority import (
    BASE_ID,
    SOURCE_PINS,
    build_revision,
    check_existing,
    execution_gate,
    immutable_write,
    manifest_for,
    revision_input,
    verify_public_sources,
)

ROOT = Path(__file__).resolve().parents[3]


def test_public_frozen_yangliu_fact_and_exact_identity():
    assert verify_public_sources(ROOT) == SOURCE_PINS
    revision = build_revision(revision_input())
    assert revision.base_id == BASE_ID
    assert str(revision.area_mu) == "394.000000"
    assert revision.season == "2026-2027"
    assert revision.area_type == "REFERENCE_AREA"
    assert revision.known_at.isoformat() == "2026-10-04T14:32:00+00:00"
    assert revision.effective_from.isoformat() == "2026-06-30T16:00:00+00:00"
    assert revision.payload_hash == revision.computed_payload_hash()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("area_mu", "393.4"),
        ("area_mu", "394.1"),
        ("base_id", "wrong"),
        ("season", "2025-2026"),
        ("area_type", "ACTUAL_PRODUCTIVE_AREA"),
        ("area_type", "PLANNED_AREA"),
        ("area_type", "PLANTED_AREA"),
        ("known_at", "2026-07-01T00:00:00+08:00"),
        ("recorded_at", "2026-07-01T00:00:00+08:00"),
        ("effective_from", "2026-10-04T22:32:00+08:00"),
        ("source", ""),
        ("basis", ""),
        ("source_reference", "wrong"),
        ("supersedes_revision_id", "guessed-parent"),
        ("payload_hash", "0" * 64),
    ],
)
def test_owner_contract_mutations_fail_closed(field, value):
    raw = revision_input()
    raw[field] = value
    with pytest.raises(ValueError):
        build_revision(raw)


def test_same_input_byte_equal_and_no_overwrite(tmp_path):
    r = build_revision(revision_input())
    raw = (json.dumps(r.model_dump(mode="json"), sort_keys=True) + "\n").encode()
    path = tmp_path / "area-revision.json"
    immutable_write(path, raw)
    immutable_write(path, raw)
    assert path.read_bytes() == raw
    with pytest.raises(ValueError, match="AUTHORITY_CONFLICT"):
        immutable_write(path, b"different")
    assert path.read_bytes() == raw


def test_existing_conflicting_terminal_revision_rejected():
    r = build_revision(revision_input())
    conflicting = r.model_copy(update={"area_mu": r.area_mu + 1})
    with pytest.raises(ValueError, match="CONFLICTING_EXISTING"):
        check_existing([conflicting], r)


def test_existing_identical_authority_reused_and_superseded_ignored():
    r = build_revision(revision_input())
    assert check_existing([r], r) == "REUSE_EXISTING_IDENTICAL_AUTHORITY"
    old = r.model_copy(update={"area_revision_id": "old", "area_mu": r.area_mu + 1})
    child = r.model_copy(update={"supersedes_revision_id": "old"})
    assert check_existing([old, child], child) == "REUSE_EXISTING_IDENTICAL_AUTHORITY"


@pytest.mark.parametrize("operation", ["weather_capture", "prediction", "actual_access"])
def test_execution_prohibited(operation):
    with pytest.raises(ValueError, match="EXECUTION_FORBIDDEN"):
        execution_gate(operation)


def test_manifest_has_no_private_path_and_direct_hash():
    r = build_revision(revision_input())
    m = manifest_for(r, b"synthetic", SOURCE_PINS)
    from backend.app.pit.canonical import hash_payload

    assert m["manifest_hash"] == hash_payload({k: v for k, v in m.items() if k != "manifest_hash"})
    assert "/Users/" not in json.dumps(m)


def test_source_drift_rejected(tmp_path):
    path = tmp_path / next(iter(SOURCE_PINS))
    path.parent.mkdir(parents=True)
    path.write_text("{}")
    with pytest.raises(ValueError, match="PUBLIC_SOURCE_DRIFT"):
        verify_public_sources(tmp_path)
