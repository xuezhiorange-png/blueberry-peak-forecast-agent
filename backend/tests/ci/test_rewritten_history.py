"""Synthetic graph regression; no filter-repo, workbook or original data reads."""

import hashlib
import json
from dataclasses import replace

import pytest
import yaml

from backend.app.core import historical_code_identity as identity
from backend.app.core import rewritten_history as locations

pytestmark = [pytest.mark.unit, pytest.mark.contract]


@pytest.fixture
def rewritten(monkeypatch, tmp_path):
    raw = b'def synthetic():\n    return "SYNTHETIC_ONLY_ORIGINAL"\n'
    path = "backend/app/synthetic.py"
    repos = []
    commits = []
    for label in ("original", "rewritten"):
        repo = tmp_path / label
        repo.mkdir()
        identity._git(repo, "init", "-q")
        blob = identity._git(repo, "hash-object", "-w", "--stdin", data=raw).decode().strip()
        identity._git(repo, "update-index", "--add", "--cacheinfo", f"100644,{blob},{path}")
        tree = identity._git(repo, "write-tree").decode().strip()
        commit = identity._git(repo, "commit-tree", tree, data=label.encode()).decode().strip()
        identity._git(repo, "update-ref", "HEAD", commit)
        repos.append(repo)
        commits.append(commit)
    old, new = commits
    payload = {
        "schema": "TD01_CLEAN_HISTORY_LOCATORS_R1",
        "clean_main": new,
        "original_root": old,
        "entries": {
            old: {
                "rewritten_commit": new,
                "original_tree": tree,
                "rewritten_tree": tree,
                "roles": ["SOURCE", "BASELINE"],
            }
        },
        "metadata_identities": [],
    }
    file = tmp_path / "SYNTHETIC_LOCATORS.json"
    data = json.dumps(payload).encode()
    file.write_bytes(data)
    monkeypatch.setattr(locations, "LOCATORS_FILE", file)
    monkeypatch.setattr(locations, "LOCATORS_SHA256", hashlib.sha256(data).hexdigest())
    entry = identity.Identity(old, path, blob, hashlib.sha256(raw).hexdigest(), "TEST_CODE")
    monkeypatch.setattr(identity, "catalog", lambda: (entry,))
    return repos[0], repos[1], entry, new, raw, file


def test_exact_original_and_declared_rewrite_keep_the_same_blob_and_hash(rewritten):
    original, clean, row, new, raw, _ = rewritten
    assert identity.read_code(row.commit, row.path, repo=original) == raw
    assert identity._type(clean, row.commit) is None
    assert identity.read_code(row.commit, row.path, repo=clean) == raw
    assert locations.resolve(clean, row.commit, role="BASELINE") == new


def test_missing_source_never_uses_current_worktree(rewritten):
    _, clean, row, _, _, _ = rewritten
    (clean / row.path).parent.mkdir(parents=True)
    (clean / row.path).write_text("CURRENT_VERSION_IS_NOT_AUTHORITY")
    (clean / ".git/objects" / row.blob[:2] / row.blob[2:]).unlink()
    with pytest.raises(identity.CodeIdentityError, match="CODE_BLOB_UNAVAILABLE"):
        identity.read_code(row.commit, row.path, repo=clean)


def test_old_commit_cannot_be_reintroduced_to_make_rewritten_reads_pass(rewritten):
    original, clean, row, _, _, _ = rewritten
    metadata = identity._git(original, "cat-file", "commit", row.commit)
    identity._git(clean, "hash-object", "-t", "commit", "-w", "--stdin", data=metadata)
    with pytest.raises(identity.CodeIdentityError, match="REWRITE_ORIGINAL_HISTORY_PRESENT"):
        identity.read_code(row.commit, row.path, repo=clean)


def test_locator_json_cannot_approve_its_own_replacement(rewritten):
    _, clean, row, _, _, file = rewritten
    value = json.loads(file.read_bytes())
    value["entries"][row.commit]["rewritten_commit"] = "f" * 40
    value["approved"] = True
    file.write_text(json.dumps(value))
    with pytest.raises(identity.CodeIdentityError, match="REWRITE_LOCATOR_TRUST_ANCHOR_MISMATCH"):
        identity.read_code(row.commit, row.path, repo=clean)


@pytest.mark.parametrize(
    "name", ["shallow", "info/grafts", "objects/info/alternates", "objects/pack/SYNTHETIC.promisor"]
)
def test_external_or_incomplete_history_is_rejected(rewritten, name):
    _, clean, row, _, _, _ = rewritten
    file = clean / ".git" / name
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text("")
    with pytest.raises(identity.CodeIdentityError, match="REWRITE_EXTERNAL_HISTORY_FORBIDDEN"):
        identity.read_code(row.commit, row.path, repo=clean)


def test_unknown_old_version_is_not_a_matching_content_search(rewritten, monkeypatch):
    _, clean, row, _, _, _ = rewritten
    unknown = replace(row, commit="f" * 40)
    monkeypatch.setattr(identity, "catalog", lambda: (unknown,))
    with pytest.raises(identity.CodeIdentityError, match="HISTORICAL_COMMIT_UNAVAILABLE"):
        identity.read_code(unknown.commit, row.path, repo=clean)


def test_unrelated_head_with_known_objects_is_not_the_declared_graph(rewritten):
    _, clean, row, _, _, _ = rewritten
    tree = identity._git(clean, "write-tree").decode().strip()
    unrelated = (
        identity._git(clean, "commit-tree", tree, data=b"UNRELATED_SYNTHETIC_ROOT").decode().strip()
    )
    identity._git(clean, "update-ref", "HEAD", unrelated)
    with pytest.raises(identity.CodeIdentityError, match="HISTORICAL_COMMIT_UNAVAILABLE"):
        identity.read_code(row.commit, row.path, repo=clean)


def test_baseline_must_keep_its_original_tree_even_with_an_explicit_locator(rewritten, monkeypatch):
    _, clean, row, _, _, file = rewritten
    value = json.loads(file.read_bytes())
    value["entries"][row.commit]["original_tree"] = "f" * 40
    raw = json.dumps(value).encode()
    file.write_bytes(raw)
    monkeypatch.setattr(locations, "LOCATORS_SHA256", hashlib.sha256(raw).hexdigest())
    with pytest.raises(locations.HistoryLocationError, match="BASELINE_TREE_IDENTITY_CHANGED"):
        locations.resolve(clean, row.commit, role="BASELINE")


def test_blocked_object_metadata_rejects_before_blob_bodies(rewritten, monkeypatch):
    _, clean, row, _, _, _ = rewritten
    original_type = locations._type
    monkeypatch.setattr(
        locations,
        "_type",
        lambda repo, oid: "blob" if oid in locations.BLOCKED_BLOBS else original_type(repo, oid),
    )
    original_git = identity._git

    def no_blob(repo, *args, **kwargs):
        assert args[:2] != ("cat-file", "blob"), "blocked before any body read"
        return original_git(repo, *args, **kwargs)

    monkeypatch.setattr(identity, "_git", no_blob)
    with pytest.raises(identity.CodeIdentityError, match="REWRITE_BLOCKED_BLOB_PRESENT"):
        identity.read_code(row.commit, row.path, repo=clean)


def test_current_fixture_copies_only_mapped_metadata_and_keeps_separate_capability(rewritten):
    _, clean, row, new, raw, _ = rewritten
    with identity.current_code_fixture(row.commit, row.path, source=clean) as fixture:
        assert identity._type(fixture, row.commit) is None
        assert identity._type(fixture, new) == "commit"
        assert identity.read_code(row.commit, row.path, repo=fixture) == raw
        with pytest.raises(identity.CodeIdentityError, match="OWNED_REHEARSAL_REQUIRED"):
            identity.read_code(
                row.commit, row.path, repo=fixture, mode=identity.Mode.CLEAN_GRAPH_REHEARSAL
            )


def test_mapped_history_metadata_also_contaminates_code_only_rehearsals(rewritten):
    _, clean, row, new, raw, _ = rewritten
    with identity.isolated_code_repository() as fixture:
        identity._git(fixture, "hash-object", "-w", "--stdin", data=raw)
        metadata = identity._git(clean, "cat-file", "commit", new)
        identity._git(fixture, "hash-object", "-t", "commit", "-w", "--stdin", data=metadata)
        with pytest.raises(identity.CodeIdentityError, match="REHEARSAL_OLD_COMMIT_PRESENT"):
            identity.read_code(
                row.commit, row.path, repo=fixture, mode=identity.Mode.CLEAN_GRAPH_REHEARSAL
            )


def test_ci_preflight_keeps_all_three_original_source_identity_checks():
    workflow = yaml.load(
        (identity.ROOT / ".github/workflows/ci.yml").read_text(), Loader=yaml.BaseLoader
    )
    for job in ("unit-contract-golden", "full-suite-canary", "frontend-unit"):
        steps = workflow["jobs"][job]["steps"]
        guard = next(
            i
            for i, step in enumerate(steps)
            if step.get("run") == "python -B -m backend.app.core.historical_code_identity preflight"
        )
        setup = next(
            i for i, step in enumerate(steps) if step.get("uses") == "actions/setup-python@v5"
        )
        assert setup < guard
        assert steps[guard].get("continue-on-error") is None
    result = identity.preflight()
    assert result["original_commit"] == "320f2046e3105b1b55da9cb037892571110b584a"
    assert set(result["verified_source_identities"]) == {
        "backend/app/main.py",
        "backend/app/api/forecast_intelligence_read.py",
        "backend/app/api/forecast_intelligence_decision.py",
    }
    assert result["original_blob_and_sha256_verified"] is True


def test_two_metadata_reads_keep_the_original_independent_hash_authorities(monkeypatch):
    read_bytes = type(identity.ROOT).read_bytes
    for row in locations.catalog()["metadata_identities"]:
        raw = identity.read_compatibility_metadata(row["original_commit"], row["path"])
        assert raw is not None and hashlib.sha256(raw).hexdigest() == row["sha256"]
        authority = identity.ROOT / row["authority_document"]
        payload = json.loads(read_bytes(authority))
        value = payload
        for field in row["authority_hash_field"][:-1]:
            value = value[field]
        value[row["authority_hash_field"][-1]] = "0" * 64
        with monkeypatch.context() as patch:
            patch.setattr(
                type(authority),
                "read_bytes",
                lambda path, frozen=payload, bound=authority: (
                    json.dumps(frozen).encode() if path == bound else read_bytes(path)
                ),
            )
            with pytest.raises(
                identity.CodeIdentityError, match="ORIGINAL_EXPECTED_SHA256_CHANGED"
            ):
                identity.read_compatibility_metadata(row["original_commit"], row["path"])


def test_unapproved_historical_test_does_not_gain_a_locator_or_metadata_clearance(
    unapproved_owner_baseline,
):
    original = "320f2046e3105b1b55da9cb037892571110b584a"
    path = "backend/tests/forecast_intelligence/test_v0_17_s2_decision_service.py"
    assert identity.registered(original, path) is False
    assert identity.technical_registered(original, path) is False
    assert identity.read_compatibility_metadata(original, path) is None
