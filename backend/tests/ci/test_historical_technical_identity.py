"""Three approved technical identities only; no business source fixtures."""

import hashlib
import json
from copy import deepcopy

import pytest

from backend.app.core import historical_code_identity as identity
from backend.tests import historical_source

pytestmark = [pytest.mark.unit, pytest.mark.contract]

CASES = (
    (
        "e9812e82067dceae444ff0707ceeb2f560c1018e",
        ".github/workflows/ci.yml",
        "docs/v0-18/s1/local-auth-runtime-r1.json",
    ),
    (
        "320f2046e3105b1b55da9cb037892571110b584a",
        "pyproject.toml",
        "docs/v0-18/evidence/s1-identity-and-grant-preflight-r1.json",
    ),
    (
        "320f2046e3105b1b55da9cb037892571110b584a",
        "uv.lock",
        "docs/v0-18/evidence/s1-identity-and-grant-preflight-r1.json",
    ),
)


@pytest.fixture
def technical_graph():
    # Independent, preexisting expected Hashes are checked before copying bytes.
    originals = {}
    for commit, path, authority in CASES:
        expected = json.loads((identity.ROOT / authority).read_bytes())["source_evidence_sha256"][
            path
        ]
        raw = identity._git(identity.ROOT, "show", commit + ":" + path)
        assert hashlib.sha256(raw).hexdigest() == expected
        originals[commit, path] = raw
    with identity.isolated_code_repository() as repo:
        for (_, path), raw in originals.items():
            oid = identity._git(repo, "hash-object", "-w", "--stdin", data=raw).decode().strip()
            identity._git(repo, "update-index", "--add", "--cacheinfo", f"100644,{oid},{path}")
        tree = identity._git(repo, "write-tree").decode().strip()
        head = (
            identity._git(repo, "commit-tree", tree, data=b"SYNTHETIC_TECHNICAL_IDENTITY_TEST\n")
            .decode()
            .strip()
        )
        identity._git(repo, "update-ref", "refs/heads/technical-test", head)
        yield repo, originals, head


@pytest.mark.parametrize("commit,path,authority", CASES)
def test_existing_consumer_reads_independently_verified_technical_bytes_without_old_commit(
    technical_graph, commit, path, authority
):
    repo, originals, _ = technical_graph
    assert identity._type(repo, commit) is None
    assert historical_source.historical_bytes(path, commit, root=repo) == originals[commit, path]


@pytest.mark.parametrize("commit,path,authority", CASES)
def test_current_history_keeps_exact_independent_hash_and_consumer_semantics(
    commit, path, authority
):
    expected = json.loads((identity.ROOT / authority).read_bytes())["source_evidence_sha256"][path]
    raw = identity.read_technical(commit, path)
    assert hashlib.sha256(raw).hexdigest() == expected
    assert historical_source.historical_bytes(path, commit) == raw
    if path in {"pyproject.toml", "uv.lock"}:
        assert historical_source.verified_source(path, expected) == raw


def test_owned_graph_contains_only_three_technical_blobs_and_no_old_history(technical_graph):
    repo, originals, head = technical_graph
    blobs = {identity._blob_id(raw) for raw in originals.values()}
    for line in (
        identity._git(
            repo, "cat-file", "--batch-all-objects", "--batch-check=%(objectname) %(objecttype)"
        )
        .decode()
        .splitlines()
    ):
        oid, kind = line.split()
        assert kind in {"blob", "tree", "commit"}
        assert kind != "blob" or oid in blobs
        assert kind != "commit" or oid == head
    assert not identity._git(repo, "remote").strip()
    assert not (repo / ".git/objects/info/alternates").exists()
    assert not (repo / ".git/info/grafts").exists()


def test_old_commit_contamination_is_not_silently_accepted(technical_graph):
    repo, _, _ = technical_graph
    commit, path, _ = CASES[0]
    metadata = identity._git(identity.ROOT, "cat-file", "commit", commit)
    identity._git(repo, "hash-object", "-t", "commit", "-w", "--stdin", data=metadata)
    with pytest.raises(identity.CodeIdentityError, match="REHEARSAL_OLD_COMMIT_PRESENT"):
        historical_source.historical_bytes(path, commit, root=repo)


@pytest.mark.parametrize("commit,path,authority", CASES)
def test_ordinary_repository_missing_commit_cannot_select_blob_fallback(
    tmp_path, technical_graph, commit, path, authority
):
    owned, _, _ = technical_graph
    # Reopen the same verified bytes in a non-owned repo: no automatic fallback.
    identity._git(tmp_path, "init", "-q")
    raw = identity.read_technical(commit, path)
    identity._git(tmp_path, "hash-object", "-w", "--stdin", data=raw)
    (tmp_path / "SYNTHETIC.json").write_text('{"approved":true,"mode":"CLEAN_GRAPH_REHEARSAL"}')
    with pytest.raises(identity.CodeIdentityError, match="HISTORICAL_COMMIT_UNAVAILABLE"):
        historical_source.historical_bytes(path, commit, root=tmp_path)
    with pytest.raises(identity.CodeIdentityError, match="OWNED_REHEARSAL_REQUIRED"):
        identity.read_technical(
            commit, path, repo=tmp_path, mode=identity.Mode.CLEAN_GRAPH_REHEARSAL
        )
    assert identity._type(owned, commit) is None


@pytest.mark.parametrize(
    "path",
    [
        "configs/base_registry_s1.json",
        "configs/production_plan.yaml",
        "data/raw/2024_2025_receipts.xls",
        "data/raw/2025_2026_receipts.xls",
        "backend/tests/fixtures/s3_a2_official_s2_partitions/train.content.gz",
        "docs/frozen.json",
        "backend/tests/forecast_intelligence/test_v0_17_s2_decision_service.py",
        "frontend/package.json",
    ],
)
def test_unadmitted_paths_are_rejected_before_any_git_read(monkeypatch, path):
    monkeypatch.setattr(identity, "_git", lambda *a, **k: pytest.fail("no Git read permitted"))
    with pytest.raises(identity.CodeIdentityError, match="UNREGISTERED_TECHNICAL_IDENTITY"):
        identity.read_technical(CASES[1][0], path)


@pytest.mark.parametrize("revision", ["HEAD", CASES[1][0] + "~1", "0" * 40])
def test_wrong_commit_is_not_a_matching_content_search(monkeypatch, revision):
    monkeypatch.setattr(identity, "_git", lambda *a, **k: pytest.fail("no Git read permitted"))
    with pytest.raises(identity.CodeIdentityError):
        identity.read_technical(revision, "pyproject.toml")


@pytest.mark.parametrize("field", ["original_git_blob_oid", "original_source_sha256"])
def test_catalog_tampering_cannot_approve_its_own_hash(tmp_path, monkeypatch, field):
    payload = json.loads(identity.TECHNICAL_CATALOG_FILE.read_bytes())
    payload["entries"][0][field] = "0" * (40 if field.endswith("oid") else 64)
    payload["entries"][0]["independent_authority"]["expected_sha256"] = "0" * 64
    file = tmp_path / "forged.json"
    file.write_text(json.dumps(payload))
    monkeypatch.setattr(identity, "TECHNICAL_CATALOG_FILE", file)
    with pytest.raises(identity.CodeIdentityError, match="CATALOG_TRUST_ANCHOR_MISMATCH"):
        identity.read_technical(CASES[0][0], CASES[0][1])


def test_changed_independent_authority_fails_before_git(tmp_path, monkeypatch):
    commit, path, document = CASES[0]
    authority = tmp_path / document
    authority.parent.mkdir(parents=True)
    authority.write_text(json.dumps({"source_evidence_sha256": {path: "0" * 64}}))
    monkeypatch.setattr(identity, "ROOT", tmp_path)
    monkeypatch.setattr(identity, "_git", lambda *a, **k: pytest.fail("no Git read permitted"))
    with pytest.raises(identity.CodeIdentityError, match="ORIGINAL_EXPECTED_SHA256_CHANGED"):
        identity.read_technical(commit, path)


def test_inconsistent_blob_pin_and_corrupt_bytes_remain_errors(monkeypatch):
    rows = deepcopy(identity._technical_records())
    rows[0]["original_git_blob_oid"] = "0" * 40
    with monkeypatch.context() as patch:
        patch.setattr(identity, "_technical_records", lambda: rows)
        with pytest.raises(identity.CodeIdentityError, match="CODE_PATH_BLOB_MISMATCH"):
            identity.read_technical(CASES[0][0], CASES[0][1])
    original = identity._git

    def corrupt(repo, *args, **kwargs):
        return (
            b"SYNTHETIC_CORRUPTED"
            if args[:2] == ("cat-file", "blob")
            else original(repo, *args, **kwargs)
        )

    monkeypatch.setattr(identity, "_git", corrupt)
    with pytest.raises(identity.CodeIdentityError, match="CODE_BLOB_IDENTITY_MISMATCH"):
        identity.read_technical(CASES[0][0], CASES[0][1])


def test_original_code_only_reader_still_excludes_technical_files():
    with pytest.raises(identity.CodeIdentityError, match="NON_CODE_PATH_NOT_ADMITTED"):
        identity.read_code(CASES[1][0], "pyproject.toml")


def test_unverified_historical_test_stays_blocked_in_the_original_consumer(technical_graph):
    repo, _, _ = technical_graph
    path = "backend/tests/forecast_intelligence/test_v0_17_s2_decision_service.py"
    assert identity.technical_registered(CASES[1][0], path) is False
    with pytest.raises(AssertionError, match="Required historical commit unavailable"):
        historical_source.historical_bytes(path, CASES[1][0], root=repo)
