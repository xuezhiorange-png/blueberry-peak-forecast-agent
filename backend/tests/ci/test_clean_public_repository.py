"""Local option-A construction and fail-closed negatives; synthetic data only."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from backend.app.core import clean_public_repository as clean

pytestmark = [pytest.mark.unit, pytest.mark.contract]


@pytest.fixture
def populated():
    with clean.owned_repository() as repo:
        clean.populate(repo)
        yield repo


def test_real_candidate_current_head_builds_only_one_new_root(populated):
    proof = clean.verify_objects(populated)
    assert proof["status"] == "PASS"
    assert proof["file_count"] == 18
    assert proof["parent_count"] == proof["remote_count"] == proof["tag_count"] == 0
    assert proof["known_historical_xls_blobs_present"] is False
    assert proof["original_commits_reachable"] is False
    assert proof["source_bytes_unchanged"] is True
    assert proof["publication_approved"] is False
    for commit in {row.commit for row in clean.history.catalog()}:
        assert clean.history._run(populated, "cat-file", "-t", commit).returncode != 0


def test_git_writes_never_target_the_original_or_an_arbitrary_repository(tmp_path):
    for root in (clean.ROOT, tmp_path):
        with pytest.raises(clean.CleanRepositoryError, match="OWNED_TEMPORARY"):
            clean._write_git(root, "init")
        with pytest.raises(clean.CleanRepositoryError, match="OWNED_TEMPORARY"):
            clean.populate(root)


@pytest.mark.parametrize(
    "path",
    [
        "data/raw/2024_2025_receipts.xls",
        "data/raw/2025_2026_receipts.xls",
        "configs/base_registry_s1.json",
        "configs/factory_aliases.yaml",
        "renamed.py",
        "backend/app/renamed_business.py",
        "unverified.content.gz",
        "docs/renamed-SYNTHETIC_ONLY.xlsx",
        "../secret",
        "--help",
        "/tmp/secret",
        "backend/app/../secret.py",
        "backend\\app\\secret.py",
        "backend/app/a.py:other",
    ],
)
def test_unknown_data_configs_renames_and_injection_fail_before_any_git_read(monkeypatch, path):
    monkeypatch.setattr(clean.history, "_git", lambda *a, **k: pytest.fail("no Git read permitted"))
    with pytest.raises(clean.CleanRepositoryError):
        clean.candidate_bytes(clean.ROOT, path)


def test_known_sensitive_blob_identity_at_allowed_path_is_refused_before_content(monkeypatch):
    original = clean.history._git
    path = "backend/app/etl/history/schemas.py"

    def metadata_only(repo, *args, **kwargs):
        if args[0] == "ls-tree":
            return f"100644 blob {next(iter(clean.BLOCKED_BLOBS))}\t{path}\0".encode()
        pytest.fail("known object body must not be read")

    monkeypatch.setattr(clean.history, "_git", metadata_only)
    with pytest.raises(clean.CleanRepositoryError, match="BLOCKED_SOURCE_OBJECT"):
        clean.candidate_bytes(clean.ROOT, path)
    monkeypatch.setattr(clean.history, "_git", original)


def test_synthetic_label_or_changed_generator_bytes_are_not_provenance(monkeypatch):
    path = "docs/tech-debt/td01c-synthetic-example/SYNTHETIC_ONLY_2039_2040.xlsx"
    original = clean.history._git

    def metadata_only(repo, *args, **kwargs):
        if args[0] == "cat-file":
            pytest.fail("unbound workbook body must not be read")
        return original(repo, *args, **kwargs)

    monkeypatch.setattr(clean.history, "_git", metadata_only)
    for raw in (None, b"SYNTHETIC_ONLY", b"independently generated but different content"):
        with pytest.raises(clean.CleanRepositoryError, match="FULL_CONTENT_BINDING"):
            clean.candidate_bytes(clean.ROOT, path, generated=raw)


def test_catalog_and_hash_cannot_be_tampered_together(tmp_path, monkeypatch):
    raw = json.loads(clean.CATALOG.read_bytes())
    raw["entries"][0]["sha256"] = "0" * 64
    raw["entries"][0]["git_blob_oid"] = "1" * 40
    raw["entries"][0]["publication_status"] = "APPROVED"
    target = tmp_path / "catalog.json"
    target.write_text(json.dumps(raw))
    monkeypatch.setattr(clean, "CATALOG", target)
    with pytest.raises(clean.CleanRepositoryError, match="CATALOG_SEAL_MISMATCH"):
        clean.candidates()


@pytest.mark.parametrize("kind", ["tag", "branch", "remote", "alternates", "graft"])
def test_copied_refs_remote_and_hidden_history_are_rejected(populated, kind):
    if kind in {"tag", "branch"}:
        root = clean.history._git(populated, "rev-parse", "HEAD").decode().strip()
        prefix = "refs/tags/" if kind == "tag" else "refs/heads/"
        clean._write_git(populated, "update-ref", prefix + "copied-old-reference", root)
    elif kind == "remote":
        clean._write_git(
            populated, "config", "remote.hidden.url", "https://invalid.example/no-fetch"
        )
    else:
        file = (
            populated
            / ".git"
            / ("objects/info/alternates" if kind == "alternates" else "info/grafts")
        )
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("SYNTHETIC_DO_NOT_FOLLOW\n")
    with pytest.raises(clean.CleanRepositoryError):
        clean.verify_objects(populated)


def test_unknown_dangling_blob_is_rejected_even_without_a_ref(populated):
    clean._write_git(populated, "hash-object", "-w", "--stdin", data=b"UNKNOWN_SYNTHETIC_BYTES")
    with pytest.raises(clean.CleanRepositoryError, match="UNREACHABLE_OBJECT"):
        clean.verify_objects(populated)


def test_unknown_working_file_or_changed_code_is_rejected(populated):
    file = populated / "backend/app/renamed_data.py"
    file.write_text("SYNTHETIC_ONLY = 'not provenance'\n")
    with pytest.raises(clean.CleanRepositoryError, match="UNALLOWLISTED_WORKING_FILE"):
        clean.verify_objects(populated)
    file.unlink()
    target = populated / "backend/research/v019_daily_curve.py"
    target.write_bytes(target.read_bytes() + b"\n# Changed version\n")
    with pytest.raises(clean.CleanRepositoryError, match="SOURCE_BYTES_CHANGED"):
        clean.verify_objects(populated)


def test_foreign_root_cannot_be_granted_ownership_by_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("TD01F_OWNED", str(tmp_path))
    with pytest.raises(clean.CleanRepositoryError, match="OWNED_TEMPORARY"):
        clean.verify_objects(tmp_path)


def test_two_independent_processes_build_identical_candidate_graph():
    code = """
import json
from backend.app.core import clean_public_repository as c
with c.owned_repository() as repo:
    c.populate(repo)
    print(json.dumps(c.verify_objects(repo), sort_keys=True))
"""
    outputs = [
        subprocess.check_output([sys.executable, "-c", code], cwd=clean.ROOT) for _ in range(2)
    ]
    assert outputs[0] == outputs[1]
    assert len(hashlib.sha256(outputs[0]).hexdigest()) == 64


def test_existing_decisions_and_unresolved_dependencies_are_not_implicitly_approved():
    report = clean.dependency_coverage(clean.ROOT)
    assert report["original_candidate_count"] == 1658
    assert report["verified_historical_code_identities"] == 65
    assert report["non_code_dependencies_count"] == 222
    assert len(report["owner_priority_paths"]) == 16
    assert report["owner_scope"] == dict.fromkeys(("D02", "D03", "D06"), "OWNER_PENDING")
    assert report["public_increment_baseline"]["status"] == "BLOCKED_PENDING_OWNER_SCOPE"


def test_known_xls_identity_hidden_under_code_name_in_tree_is_blocked(populated):
    # Reference only the forbidden identity. Never import or reconstruct its Blob.
    oid = "3413dbbc284312e75a2df98992a6ab66cfa87dbd"
    clean._write_git(
        populated,
        "update-index",
        "--add",
        "--cacheinfo",
        f"100644,{oid},backend/app/renamed.py",
    )
    tree = clean._write_git(populated, "write-tree", "--missing-ok").decode().strip()
    root = clean._write_git(populated, "commit-tree", tree, data=b"SYNTHETIC NEGATIVE\n")
    clean._write_git(populated, "update-ref", "refs/heads/main", root.decode().strip())
    with pytest.raises(clean.CleanRepositoryError, match="BLOCKED_SOURCE_OBJECT"):
        clean.verify_objects(populated)
    assert clean.history._run(populated, "cat-file", "-e", oid).returncode != 0


def test_running_real_subset_retains_blocked_assertion_and_preserves_graph(populated):
    before = clean.verify_objects(populated)
    results = clean.run_subset(populated)
    assert clean.verify_objects(populated) == before
    for name in ("ruff", "format", "strict_mypy", "pure_daily_curve"):
        assert results[name]["status"] == "PASS"
    result = results["synthetic_publication_tests"]
    assert result["status"] == "BLOCKED"
    assert result["exit_code"] == 1
    assert result["passed"] == 24 and result["failed"] == 1
    assert result["blocked_tests"] == [
        "test_path_only_audit_registry_and_original_ref_inventory_are_bound"
    ]


def test_committed_rehearsal_reports_bind_actual_code_and_still_show_blockers():
    docs = clean.ROOT / "docs/tech-debt"
    receipt = json.loads((docs / "td01f-isolated-acceptance-r1.json").read_bytes())
    assert receipt["module_sha256"] == hashlib.sha256(Path(clean.__file__).read_bytes()).hexdigest()
    assert receipt["independent_process_count"] == 2
    for name, sha in receipt["report_sha256"].items():
        assert hashlib.sha256((docs / "td01f-rehearsal-r1" / name).read_bytes()).hexdigest() == sha
    report = json.loads(
        (docs / "td01f-rehearsal-r1/public-ci-compatibility-report.json").read_bytes()
    )
    assert report["isolated_checks"]["synthetic_publication_tests"]["failed"] == 1
    assert report["original_complete_ci"] == "BLOCKED_NOT_EXECUTED_IN_NEW_ROOT"
    assert report["original_test_assertions_changed"] is False
