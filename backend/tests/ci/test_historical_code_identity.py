"""Code-only integrity, using owned Git repositories and no business sources."""

import ast
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import replace

import pytest

from backend.app.core import historical_code_identity as identity

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def git(root, *args, data=None):
    return identity._git(root, *args, data=data)


@pytest.fixture
def synthetic(monkeypatch, tmp_path):
    with identity.isolated_code_repository() as repo:
        path = "backend/app/example.py"
        original = b'def example():\n    return "SYNTHETIC_CODE_ONLY"\n'
        oid = git(repo, "hash-object", "-w", "--stdin", data=original).decode().strip()
        git(repo, "update-index", "--add", "--cacheinfo", f"100644,{oid},{path}")
        tree = git(repo, "write-tree").decode().strip()
        commit = git(repo, "commit-tree", tree, data=b"SYNTHETIC_CODE_ONLY\n").decode().strip()
        row = {
            "original_commit_sha": commit,
            "repository_relative_path": path,
            "original_git_blob_oid": oid,
            "original_source_sha256": hashlib.sha256(original).hexdigest(),
            "source_class": "TEST_CODE",
            "verification_status": "VERIFIED_EXISTING_GIT_BLOB",
            "independent_authority": {
                "kind": "EXISTING_TEST_GIT_BLOB_PIN",
                "expected_git_blob_oid": oid,
            },
        }
        raw = (
            json.dumps(
                {"schema_version": "TD01E_CODE_IDENTITY_R1", "entries": [row]}, sort_keys=True
            )
            + "\n"
        ).encode()
        catalog = tmp_path / "synthetic-code-catalog.json"
        catalog.write_bytes(raw)
        # The fixture trust anchor is fixed BEFORE any negative mutation.
        monkeypatch.setattr(identity, "CATALOG_FILE", catalog)
        monkeypatch.setattr(identity, "CATALOG_SHA256", hashlib.sha256(raw).hexdigest())
        yield repo, row, original, catalog


def test_original_commit_path_blob_and_hash_are_all_verified(synthetic):
    repo, row, original, _ = synthetic
    assert (
        identity.read_code(row["original_commit_sha"], row["repository_relative_path"], repo=repo)
        == original
    )


def test_missing_commit_is_not_an_automatic_blob_fallback(synthetic):
    repo, row, _, _ = synthetic
    (
        repo / ".git/objects" / row["original_commit_sha"][:2] / row["original_commit_sha"][2:]
    ).unlink()
    with pytest.raises(identity.CodeIdentityError, match="HISTORICAL_COMMIT_UNAVAILABLE"):
        identity.read_code(row["original_commit_sha"], row["repository_relative_path"], repo=repo)


def test_clean_owned_graph_reads_exact_blob_without_old_commit(synthetic):
    repo, row, original, _ = synthetic
    (
        repo / ".git/objects" / row["original_commit_sha"][:2] / row["original_commit_sha"][2:]
    ).unlink()
    assert (
        identity.read_code(
            row["original_commit_sha"],
            row["repository_relative_path"],
            repo=repo,
            mode=identity.Mode.CLEAN_GRAPH_REHEARSAL,
        )
        == original
    )
    (
        repo / ".git/objects" / row["original_git_blob_oid"][:2] / row["original_git_blob_oid"][2:]
    ).unlink()
    with pytest.raises(identity.CodeIdentityError, match="CODE_BLOB_UNAVAILABLE"):
        identity.read_code(
            row["original_commit_sha"],
            row["repository_relative_path"],
            repo=repo,
            mode=identity.Mode.CLEAN_GRAPH_REHEARSAL,
        )


def test_real_repo_cannot_be_relabelled_as_a_clean_rehearsal():
    row = identity.catalog()[0]
    with pytest.raises(identity.CodeIdentityError, match="OWNED_REHEARSAL_REQUIRED"):
        identity.read_code(
            row.commit, row.path, repo=identity.ROOT, mode=identity.Mode.CLEAN_GRAPH_REHEARSAL
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("original_git_blob_oid", "0" * 40),
        ("original_source_sha256", "0" * 64),
        ("repository_relative_path", "backend/app/other.py"),
    ],
)
def test_mapping_mutation_cannot_change_the_trust_anchor(synthetic, field, value):
    _, _, _, file = synthetic
    payload = json.loads(file.read_bytes())
    payload["entries"][0][field] = value
    file.write_text(json.dumps(payload))
    with pytest.raises(identity.CodeIdentityError, match="CATALOG_TRUST_ANCHOR_MISMATCH"):
        identity.catalog()


def test_mapping_and_expected_hash_tampered_together_are_not_authority(synthetic):
    _, row, _, file = synthetic
    payload = json.loads(file.read_bytes())
    payload["entries"][0]["original_source_sha256"] = "a" * 64
    payload["entries"][0]["independent_authority"]["expected_git_blob_oid"] = "b" * 40
    payload["entries"][0]["original_git_blob_oid"] = "b" * 40
    payload["entries"][0]["verification_status"] = "OWNER_APPROVED"
    file.write_text(json.dumps(payload))
    with pytest.raises(identity.CodeIdentityError, match="CATALOG_TRUST_ANCHOR_MISMATCH"):
        identity.read_code(row["original_commit_sha"], row["repository_relative_path"])


def test_wrong_version_and_altered_code_do_not_use_current_file(synthetic, monkeypatch):
    repo, row, _, _ = synthetic
    changed = b'def example():\n    return "OTHER_VERSION"\n'
    oid = git(repo, "hash-object", "-w", "--stdin", data=changed).decode().strip()
    git(repo, "update-index", "--cacheinfo", f"100644,{oid},{row['repository_relative_path']}")
    tree = git(repo, "write-tree").decode().strip()
    newer = git(repo, "commit-tree", tree, data=b"SYNTHETIC_CHANGED_VERSION\n").decode().strip()
    with pytest.raises(identity.CodeIdentityError, match="UNREGISTERED_CODE_IDENTITY"):
        identity.read_code(newer, row["repository_relative_path"], repo=repo)
    original_git = identity._git

    def altered(root, *args, **kwargs):
        if args == ("cat-file", "blob", row["original_git_blob_oid"]):
            return changed
        return original_git(root, *args, **kwargs)

    monkeypatch.setattr(identity, "_git", altered)
    with pytest.raises(identity.CodeIdentityError, match="CODE_BLOB_IDENTITY_MISMATCH"):
        identity.read_code(row["original_commit_sha"], row["repository_relative_path"], repo=repo)


@pytest.mark.parametrize(
    "path",
    [
        "data/raw/2024_2025_receipts.xls",
        "data/raw/2025_2026_receipts.xls",
        "docs/frozen.json",
        "configs/source.py",
        "partitions/train.content.gz",
        "../secret.py",
        "/secret.py",
        "backend/app/../secret.py",
        "backend/app//main.py",
        "backend\\app\\main.py",
        "--help.py",
        "backend/app/main.py:other",
    ],
)
def test_data_noncode_and_unsafe_paths_fail_before_git(synthetic, monkeypatch, path):
    repo, row, _, _ = synthetic
    monkeypatch.setattr(identity, "_git", lambda *a, **k: pytest.fail("data/Git access forbidden"))
    with pytest.raises(identity.CodeIdentityError):
        identity.read_code(row["original_commit_sha"], path, repo=repo)


@pytest.mark.parametrize("commit", ["HEAD", "a" * 40 + "~1", "--all", "../main", "0" * 39])
def test_git_argument_injection_fails_before_git(synthetic, monkeypatch, commit):
    repo, row, _, _ = synthetic
    monkeypatch.setattr(identity, "_git", lambda *a, **k: pytest.fail("Git must not run"))
    with pytest.raises(identity.CodeIdentityError):
        identity.read_code(commit, row["repository_relative_path"], repo=repo)


def test_verified_real_catalog_matches_unchanged_independent_pins_and_current_git():
    report = identity.verify_current()
    assert report["identity_count"] == 65
    assert report["original_code_bytes_unchanged"] is True
    assert report["original_expected_sha256_unchanged"] is True
    assert report["verified_git_blob_identity"] is True


def test_real_code_rehearsal_has_no_old_commits_data_objects_or_alternates():
    report = identity.rehearse()
    assert report["identity_count"] == 65
    assert report["old_commits_present"] == 0
    assert report["registered_code_blobs_only"] is True
    assert report["arbitrary_fallback_allowed"] is False


def test_independent_processes_produce_identical_rehearsal_results():
    command = [sys.executable, "-m", "backend.app.core.historical_code_identity", "rehearse"]
    values = [subprocess.check_output(command, cwd=identity.ROOT) for _ in range(2)]
    assert values[0] == values[1]
    assert json.loads(values[0])["old_commits_present"] == 0


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("blob", "0" * 40, "CODE_PATH_BLOB_MISMATCH"),
        ("sha256", "0" * 64, "ORIGINAL_SOURCE_SHA256_MISMATCH"),
    ],
)
def test_source_checks_reject_inconsistent_pretrusted_fixture_identity(
    synthetic, monkeypatch, field, value, error
):
    repo, row, _, _ = synthetic
    entry = identity.catalog()[0]
    monkeypatch.setattr(identity, "catalog", lambda: (replace(entry, **{field: value}),))
    with pytest.raises(identity.CodeIdentityError, match=error):
        identity.read_code(row["original_commit_sha"], row["repository_relative_path"], repo=repo)


def test_current_fixture_does_not_copy_raw_workbook_blobs_or_enable_clean_mode():
    commit = "320f2046e3105b1b55da9cb037892571110b584a"
    path = "backend/app/main.py"
    with identity.current_code_fixture(commit, path) as repo:
        assert identity.read_code(commit, path, repo=repo) == identity.read_code(commit, path)
        for oid in (
            "3413dbbc284312e75a2df98992a6ab66cfa87dbd",
            "a045348c4c72507ae367b4e30f267fcf19c490c1",
        ):
            assert identity._type(repo, oid) is None
        with pytest.raises(identity.CodeIdentityError, match="OWNED_REHEARSAL_REQUIRED"):
            identity.read_code(commit, path, repo=repo, mode=identity.Mode.CLEAN_GRAPH_REHEARSAL)


def test_json_marker_cannot_admit_an_existing_repository(tmp_path):
    (tmp_path / "SYNTHETIC.json").write_text('{"mode":"CLEAN_GRAPH_REHEARSAL","authorized":true}')
    row = identity.catalog()[0]
    with pytest.raises(identity.CodeIdentityError, match="OWNED_REHEARSAL_REQUIRED"):
        identity.read_code(
            row.commit, row.path, repo=tmp_path, mode=identity.Mode.CLEAN_GRAPH_REHEARSAL
        )


def test_original_assertions_test_identities_and_hash_literals_are_unchanged():
    proof = json.loads(
        (identity.ROOT / "docs/tech-debt/td01e-original-assertions-r1.json").read_bytes()
    )
    for path, pins in proof["code"].items():
        text = (identity.ROOT / path).read_text()
        tree = ast.parse(text)
        assertions = [
            ast.dump(n, include_attributes=False)
            for n in sorted(ast.walk(tree), key=lambda node: getattr(node, "lineno", -1))
            if isinstance(n, ast.Assert)
        ]
        signatures = [
            (
                n.name,
                ast.dump(n.args, include_attributes=False),
                [ast.dump(x, include_attributes=False) for x in n.decorator_list],
            )
            for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        assert len(assertions) == pins["assertion_count"]
        assert (
            hashlib.sha256(json.dumps(assertions, sort_keys=True).encode()).hexdigest()
            == pins["assertions_sha256"]
        )
        assert (
            hashlib.sha256(json.dumps(signatures, sort_keys=True).encode()).hexdigest()
            == pins["test_signatures_sha256"]
        )
        assert (
            sorted(set(re.findall(r"(?<![0-9a-f])(?:[0-9a-f]{40}|[0-9a-f]{64})(?![0-9a-f])", text)))
            == pins["original_sha_literals"]
        )


def test_ci_still_requires_original_commit_and_baseline_scope_is_not_replaced():
    ci = (identity.ROOT / ".github/workflows/ci.yml").read_text()
    assert ci.count("git cat-file -e 320f2046e3105b1b55da9cb037892571110b584a^{commit}") == 3
    from scripts.ci.check_public_increment import BASELINE

    assert BASELINE == "e2d0ffa233483821e4fed3d429e317510dfcfcc1"
