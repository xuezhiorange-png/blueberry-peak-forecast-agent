"""The exact pre-TD03G runtimes must keep their independently frozen bytes."""

import hashlib
import json
from pathlib import Path

import pytest

from backend.app.core import historical_code_identity as identity
from backend.tests.historical_source import historical_bytes

ROOT = Path(__file__).resolve().parents[3]
BASE = "0124371b433d1b3c34e5e59a2a9a5e621a570f3b"
AUTHORITY = "docs/v0-18/evidence/v0.18.0-version-closeout-r1.json"
BLOCKED = json.loads(
    (
        ROOT / "docs/tech-debt/td01-clean-history-compatibility-r1/blocked-identities.json"
    ).read_bytes()
)["entries"]
RUNTIMES = [r["path"] for r in BLOCKED if r["consumer_group"] == "runtime_ast_sources"]


@pytest.mark.parametrize("relative", RUNTIMES)
def test_runtime_keeps_its_existing_frozen_closeout_identity(relative):
    expected = json.loads((ROOT / AUTHORITY).read_bytes())["frozen_model_and_math_sha256"][relative]
    raw = historical_bytes(relative, BASE)
    assert hashlib.sha256(raw).hexdigest() == expected


def test_missing_authority_never_admits_the_other_28_sources():
    unadmitted = [r for r in BLOCKED if r["path"] not in RUNTIMES]
    assert len(unadmitted) == 28
    for row in unadmitted:
        assert not identity.registered(row["original_commit"], row["path"])
        with pytest.raises(identity.CodeIdentityError, match="UNREGISTERED_CODE_IDENTITY"):
            identity.read_code(row["original_commit"], row["path"])


def test_new_catalog_cannot_rewrite_the_original_65_identities():
    assert len(identity.catalog()) == 65
    original = {(row.commit, row.path) for row in identity.catalog()}
    assert len(identity.final_runtime_catalog()) == 14
    assert all((row.commit, row.path) not in original for row in identity.final_runtime_catalog())


def test_catalog_tampering_cannot_grant_an_identity(tmp_path, monkeypatch):
    payload = json.loads(identity.FINAL_RUNTIME_CATALOG_FILE.read_bytes())
    payload["entries"][0]["original_git_blob_oid"] = "0" * 40
    file = tmp_path / "catalog.json"
    file.write_text(json.dumps(payload))
    monkeypatch.setattr(identity, "FINAL_RUNTIME_CATALOG_FILE", file)
    with pytest.raises(identity.CodeIdentityError, match="CATALOG_TRUST_ANCHOR_MISMATCH"):
        identity.final_runtime_catalog()


def test_resealed_catalog_cannot_create_its_own_hash_authority(tmp_path, monkeypatch):
    payload = json.loads(identity.FINAL_RUNTIME_CATALOG_FILE.read_bytes())
    row = payload["entries"][0]
    row["original_source_sha256"] = "0" * 64
    row["independent_authority"]["expected_sha256"] = "0" * 64
    file = tmp_path / "catalog.json"
    file.write_text(json.dumps(payload))
    monkeypatch.setattr(identity, "FINAL_RUNTIME_CATALOG_FILE", file)
    monkeypatch.setattr(
        identity, "FINAL_RUNTIME_CATALOG_SHA256", hashlib.sha256(file.read_bytes()).hexdigest()
    )
    with pytest.raises(identity.CodeIdentityError, match="ORIGINAL_EXPECTED_SHA256_CHANGED"):
        identity.final_runtime_catalog()


def test_modified_closeout_is_not_independent_authority(tmp_path, monkeypatch):
    payload = json.loads(identity.FINAL_RUNTIME_AUTHORITY_FILE.read_bytes())
    payload["frozen_model_and_math_sha256"][RUNTIMES[0]] = "0" * 64
    file = tmp_path / "closeout.json"
    file.write_text(json.dumps(payload))
    monkeypatch.setattr(identity, "FINAL_RUNTIME_AUTHORITY_FILE", file)
    with pytest.raises(identity.CodeIdentityError, match="FINAL_RUNTIME_AUTHORITY_CHANGED"):
        identity.final_runtime_catalog()


def test_same_path_at_a_different_revision_is_still_unregistered():
    with pytest.raises(identity.CodeIdentityError, match="UNREGISTERED_CODE_IDENTITY"):
        identity.read_code("320f2046e3105b1b55da9cb037892571110b584a", RUNTIMES[0])


def test_new_identity_still_checks_original_blob_bytes(monkeypatch):
    row = identity.final_runtime_catalog()[0]
    original_git = identity._git

    def tampered_git(repo, *args, data=None):
        if args == ("cat-file", "blob", row.blob):
            return b"tampered synthetic bytes"
        return original_git(repo, *args, data=data)

    monkeypatch.setattr(identity, "_git", tampered_git)
    with pytest.raises(identity.CodeIdentityError, match="CODE_BLOB_IDENTITY_MISMATCH"):
        identity.read_code(row.commit, row.path)
