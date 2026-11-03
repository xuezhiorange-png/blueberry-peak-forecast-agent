"""The new Owner-approved cohort keeps exact old bytes and separate authority."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from backend.app.core import historical_code_identity as identity

ROOT = Path(__file__).resolve().parents[3]
RECORDS = ROOT / "docs/tech-debt/td01-final28-owner-approved-compatibility-r1"
ROWS = json.loads((RECORDS / "reviewed-set.json").read_bytes())["items"]
pytestmark = [pytest.mark.unit, pytest.mark.contract]


@pytest.mark.parametrize("row", ROWS, ids=lambda row: row["candidate_id"])
def test_owner_approved_exact_version_bytes(row):
    raw = identity.read_code(row["original_commit"], row["path"])
    assert len(raw) == row["byte_size"]
    assert hashlib.sha256(raw).hexdigest() == row["sha256"]
    assert (
        hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        == row["git_blob_oid"]
    )


def test_current_approval_preserves_the_pending_snapshot_and_old_catalogs():
    reviewed = json.loads(identity.OWNER_BASELINE_SET_FILE.read_bytes())
    decision = json.loads(identity.OWNER_DECISION_FILE.read_bytes())
    assert reviewed["owner_approval_status"] == "NEW_OWNER_APPROVAL_REQUIRED"
    assert decision["owner_status"] == "APPROVED"
    assert decision["source_authority_kind"] == "NEW_OWNER_APPROVED_CODE_BASELINE"
    assert decision["retrospective_approval_claimed"] is False
    assert len(identity.owner_approved_catalog()) == 28
    assert len(identity.catalog()) == 65
    assert len(identity.final_runtime_catalog()) == 14
    assert len(identity._technical_records()) == 3


def test_pending_owner_decision_does_not_admit_any_source(unapproved_owner_baseline, monkeypatch):
    monkeypatch.setattr(identity, "_git", lambda *a, **k: pytest.fail("no Git read permitted"))
    assert identity.owner_approved_catalog() == ()
    for row in ROWS:
        assert not identity.registered(row["original_commit"], row["path"])
        with pytest.raises(identity.CodeIdentityError, match="UNREGISTERED_CODE_IDENTITY"):
            identity.read_code(row["original_commit"], row["path"])


def test_unsealed_owner_record_cannot_grant_approval(tmp_path, monkeypatch):
    decision = json.loads(identity.OWNER_DECISION_FILE.read_bytes())
    decision["approved_identity_count"] = 29
    file = tmp_path / "forged-owner-decision.json"
    file.write_text(json.dumps(decision))
    monkeypatch.setattr(identity, "OWNER_DECISION_FILE", file)
    with pytest.raises(identity.CodeIdentityError, match="OWNER_BASELINE_TRUST_ANCHOR_MISMATCH"):
        identity.owner_approved_catalog()


def test_missing_owner_record_is_a_denial_without_git_reads(tmp_path, monkeypatch):
    monkeypatch.setattr(identity, "OWNER_DECISION_FILE", tmp_path / "missing-owner-record.json")
    monkeypatch.setattr(identity, "_git", lambda *a, **k: pytest.fail("no Git read permitted"))
    with pytest.raises(identity.CodeIdentityError, match="OWNER_BASELINE_RECORD_UNAVAILABLE"):
        identity.read_code(ROWS[0]["original_commit"], ROWS[0]["path"])


@pytest.mark.parametrize(
    "field,value",
    [
        ("owner_approved_set", "ANOTHER_SET"),
        ("approved_identity_count", 29),
        ("source_authority_kind", "EXISTING_FROZEN_SHA256_FIELD"),
        ("retrospective_approval_claimed", True),
    ],
)
def test_other_set_or_retroactive_authority_is_rejected(tmp_path, monkeypatch, field, value):
    decision = json.loads(identity.OWNER_DECISION_FILE.read_bytes())
    decision[field] = value
    file = tmp_path / "synthetic-owner-record.json"
    file.write_text(json.dumps(decision))
    monkeypatch.setattr(identity, "OWNER_DECISION_FILE", file)
    monkeypatch.setattr(
        identity, "OWNER_DECISION_SHA256", hashlib.sha256(file.read_bytes()).hexdigest()
    )
    with pytest.raises(identity.CodeIdentityError, match="OWNER_APPROVED_SET_BINDING_MISMATCH"):
        identity.owner_approved_catalog()


@pytest.mark.parametrize("field,value", [("sha256", "0" * 64), ("git_blob_oid", "0" * 40)])
def test_set_cannot_resign_its_own_modified_identity(tmp_path, monkeypatch, field, value):
    payload = json.loads(identity.OWNER_BASELINE_SET_FILE.read_bytes())
    payload["items"][0][field] = value
    file = tmp_path / "forged-set.json"
    file.write_text(json.dumps(payload))
    monkeypatch.setattr(identity, "OWNER_BASELINE_SET_FILE", file)
    with pytest.raises(identity.CodeIdentityError, match="OWNER_BASELINE_TRUST_ANCHOR_MISMATCH"):
        identity.owner_approved_catalog()
    # Even a caller's new integrity seal does not update the Owner's bound set.
    monkeypatch.setattr(
        identity, "OWNER_BASELINE_SET_SHA256", hashlib.sha256(file.read_bytes()).hexdigest()
    )
    with pytest.raises(identity.CodeIdentityError, match="OWNER_APPROVED_SET_BINDING_MISMATCH"):
        identity.owner_approved_catalog()


@pytest.mark.parametrize(
    "path",
    [
        "data/raw/2024_2025_receipts.xls",
        "data/raw/2025_2026_receipts.xls",
        "configs/base_registry_s1.json",
        "backend/tests/fixtures/s3_a2_official_s2_partitions/train.content.gz",
        "backend/tests/unapproved_other_source.py",
    ],
)
def test_approval_does_not_expand_to_data_or_an_extra_source(monkeypatch, path):
    monkeypatch.setattr(identity, "_git", lambda *a, **k: pytest.fail("no Git read permitted"))
    with pytest.raises(identity.CodeIdentityError):
        identity.read_code(ROWS[0]["original_commit"], path)


def test_current_file_or_another_version_cannot_replace_the_fixed_source(monkeypatch):
    monkeypatch.setattr(identity, "_git", lambda *a, **k: pytest.fail("no Git read permitted"))
    with pytest.raises(identity.CodeIdentityError, match="UNREGISTERED_CODE_IDENTITY"):
        identity.read_code("0124371b433d1b3c34e5e59a2a9a5e621a570f3b", ROWS[0]["path"])
    with pytest.raises(identity.CodeIdentityError, match="INVALID_FIXED_CODE_IDENTITY"):
        identity.read_code("HEAD", ROWS[0]["path"])


def test_original_blob_and_hash_failures_remain_errors(monkeypatch):
    row = identity.owner_approved_catalog()[0]
    original_git = identity._git

    def corrupted(repo, *args, data=None):
        if args == ("cat-file", "blob", row.blob):
            return b"SYNTHETIC_CORRUPTED_CODE_ONLY"
        return original_git(repo, *args, data=data)

    with monkeypatch.context() as patch:
        patch.setattr(identity, "_git", corrupted)
        with pytest.raises(identity.CodeIdentityError, match="CODE_BLOB_IDENTITY_MISMATCH"):
            identity.read_code(row.commit, row.path)
    monkeypatch.setattr(identity, "_owner_approved_entry", lambda *a: replace(row, sha256="0" * 64))
    with pytest.raises(identity.CodeIdentityError, match="ORIGINAL_SOURCE_SHA256_MISMATCH"):
        identity.read_code(row.commit, row.path)


def test_approved_bytes_in_a_foreign_graph_do_not_grant_a_history_fallback(tmp_path):
    row = ROWS[0]
    raw = identity.read_code(row["original_commit"], row["path"])
    identity._git(tmp_path, "init", "-q")
    identity._git(tmp_path, "hash-object", "-w", "--stdin", data=raw)
    (tmp_path / "owner-approved.json").write_text('{"owner_status":"APPROVED"}')
    with pytest.raises(identity.CodeIdentityError, match="HISTORICAL_COMMIT_UNAVAILABLE"):
        identity.read_code(row["original_commit"], row["path"], repo=tmp_path)
    with pytest.raises(identity.CodeIdentityError, match="OWNED_REHEARSAL_REQUIRED"):
        identity.read_code(
            row["original_commit"],
            row["path"],
            repo=tmp_path,
            mode=identity.Mode.CLEAN_GRAPH_REHEARSAL,
        )
