import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.ci import check_public_increment as gate

pytestmark = [pytest.mark.unit, pytest.mark.contract]
ROOT = Path(__file__).resolve().parents[3]


def git(repo, *args, input=None, check=True):
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        input=input,
        capture_output=True,
        check=check,
        env={**os.environ, "GIT_NO_LAZY_FETCH": "1"},
    )


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.name", "SYNTHETIC_ONLY")
    git(tmp_path, "config", "user.email", "synthetic@example.invalid")
    git(tmp_path, "config", "commit.gpgsign", "false")
    (tmp_path / "old.json").write_text('{"unverified_historical_metadata":true}')
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "SYNTHETIC_ONLY baseline")
    base = git(tmp_path, "rev-parse", "HEAD").stdout.decode().strip()
    return tmp_path, base


def commit(repo, name, data):
    target = repo / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    git(repo, "add", "--", name)
    git(repo, "commit", "-qm", "SYNTHETIC_ONLY increment")


def test_unchanged_baseline_is_not_reclassified_as_approved(repo):
    root, base = repo
    result = gate.inspect(root, base)
    assert result["status"] == "PASS" and result["violations"] == []
    assert result["unchanged_history_publication_approved"] is False


@pytest.mark.parametrize("name", ["samples/data.csv", "samples/SYNTHETIC_ONLY.csv", "renamed.xlsx"])
def test_unverified_table_or_label_never_grants_publication(repo, name):
    root, base = repo
    commit(root, name, b"farm,weight_kg\nSYNTHETIC_LABEL_ONLY,42.123456\n")
    out = gate.inspect(root, base)
    assert out["status"] == "REVIEW_REQUIRED"
    assert out["violations"][0]["reason"] == "UNVERIFIED_DATA_ARTIFACT"
    assert "42.123456" not in json.dumps(out)


def test_real_quantity_json_renamed_to_code_is_rejected(repo):
    root, base = repo
    commit(
        root,
        "looks_like_code.py",
        b'DATA = [{"farm_name":"SYNTHETIC_LABEL_ONLY","weight_kg":42.123456}]\n',
    )
    assert gate.inspect(root, base)["status"] == "REVIEW_REQUIRED"


def test_normal_schema_types_code_and_metadata_do_not_confirm_leaks(repo):
    root, base = repo
    commit(
        root,
        "schema.py",
        b"def quantity(weight_kg: str, farm_name: str) -> str:\n    return weight_kg\n",
    )
    commit(
        root,
        "schema.json",
        b'{"type":"object","properties":{"weight_kg":{"type":"string"},"farm_name":{"type":"string"}}}',
    )
    assert gate.inspect(root, base)["status"] == "PASS"


def test_explicit_new_real_source_path_requires_review(repo):
    root, base = repo
    commit(root, "source.json", b'{"source_path":"/SYNTHETIC_PRIVATE/real.xlsx"}')
    out = gate.inspect(root, base)
    assert out["status"] == "REVIEW_REQUIRED"
    assert "SYNTHETIC_PRIVATE" not in json.dumps(out)


def test_registered_synthetic_exports_pass_even_when_renamed(repo):
    root, base = repo
    bundle = gate.synthetic_outputs()
    for index, (name, data) in enumerate(bundle.items()):
        commit(root, f"demo/renamed-{index}" + Path(name).suffix, data)
    assert gate.inspect(root, base)["status"] == "PASS"


def test_copied_weights_or_forged_synthetic_manifest_is_rejected(repo):
    root, base = repo
    data = next(v for k, v in gate.synthetic_outputs().items() if k.endswith(".csv"))
    commit(root, "SYNTHETIC_ONLY.csv", data + b"fictional,changed,not_generator_output\n")
    assert gate.inspect(root, base)["status"] == "REVIEW_REQUIRED"


def test_known_compressed_blob_is_blocked_by_metadata_before_any_read(repo, monkeypatch):
    root, base = repo
    blob = sorted(gate.COMPRESSED_BLOBS)[0]
    oldtree = git(root, "rev-parse", base + "^{tree}").stdout.decode().strip()
    entries = git(root, "ls-tree", oldtree).stdout + f"100644 blob {blob}\tinnocent.py\n".encode()
    tree = git(root, "mktree", "--missing", input=entries).stdout.decode().strip()

    def no_blob(*args, **kwargs):
        raise AssertionError("compressed content must not be opened")

    monkeypatch.setattr(gate, "read_public_text", no_blob)
    out = gate.inspect(root, base, tree)
    assert out["status"] == "REVIEW_REQUIRED"
    assert out["violations"][0]["reason"] == "COMPRESSED_SOURCE_IDENTITY_REQUIRES_OWNER"
    assert git(root, "cat-file", "-e", blob, check=False).returncode != 0


def test_cli_returns_nonzero_for_review_and_does_not_print_business_values(repo):
    root, base = repo
    commit(root, "new.csv", b"farm,weight_kg\nSYNTHETIC_LABEL_ONLY,42.123456\n")
    r = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/ci/check_public_increment.py"),
            "--repo",
            str(root),
            "--base",
            base,
        ],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 1 and "REVIEW_REQUIRED" in r.stdout
    assert "42.123456" not in r.stdout


def test_current_tree_increment_is_checked_by_existing_golden_and_full_canary():
    result = gate.inspect(ROOT, gate.BASELINE)
    assert result["status"] == "PASS", result


@pytest.mark.parametrize("verified", [True, False])
def test_workbooks_are_resolved_by_git_identity_without_opening(repo, monkeypatch, verified):
    root, base = repo
    data = (
        next(v for k, v in gate.synthetic_outputs().items() if k.endswith(".xlsx"))
        if verified
        else b"SYNTHETIC_ONLY_UNVERIFIED_XLSX"
    )
    commit(root, "renamed.xlsx", data)

    def no_blob(*args, **kwargs):
        raise AssertionError("unknown workbook body must not be opened")

    monkeypatch.setattr(gate, "read_public_text", no_blob)
    assert gate.inspect(root, base)["status"] == ("PASS" if verified else "REVIEW_REQUIRED")


def test_forged_synthetic_json_label_does_not_clear_business_records(repo):
    root, base = repo
    commit(
        root,
        "renamed.json",
        b'{"data_class":"SYNTHETIC_ONLY","rows":[{"farm_name":"SYNTHETIC_LABEL_ONLY","weight_kg":42.123456}]}',
    )
    assert gate.inspect(root, base)["status"] == "REVIEW_REQUIRED"


def test_pinned_baseline_removal_requires_review(repo):
    root, _ = repo
    path = "docs/tech-debt/td01c-public-derived-audit-summary.json"
    commit(root, path, b'{"SYNTHETIC_ONLY":"metadata baseline"}')
    base = git(root, "rev-parse", "HEAD").stdout.decode().strip()
    git(root, "rm", "--", path)
    git(root, "commit", "-qm", "SYNTHETIC_ONLY remove metadata")
    out = gate.inspect(root, base)
    assert out["status"] == "REVIEW_REQUIRED"
    assert out["violations"][0]["reason"] == "PINNED_REVIEW_BASELINE_CHANGED"


def test_new_python_source_assignment_needs_review_without_echoing_path(repo):
    root, base = repo
    commit(
        root,
        "source.py",
        b'from pathlib import Path\nSOURCE_PATH = Path("/SYNTHETIC_PRIVATE/original.xlsx")\n',
    )
    out = gate.inspect(root, base)
    assert out["status"] == "REVIEW_REQUIRED"
    assert out["violations"][0]["reason"] == "REAL_SOURCE_PATH_REVIEW_REQUIRED"
    assert "SYNTHETIC_PRIVATE" not in json.dumps(out)


def test_changed_producer_cannot_bless_its_own_forged_synthetic_output(repo, monkeypatch):
    root, base = repo
    commit(root, "SYNTHETIC_ONLY.csv", b"not_a_registered_generator_output")

    def unreviewed():
        raise ValueError("SYNTHETIC_PRODUCER_REVIEW_REQUIRED")

    monkeypatch.setattr(gate, "_trusted_producer", unreviewed)
    assert gate.inspect(root, base)["status"] == "REVIEW_REQUIRED"


def test_other_seed_requires_complete_independently_regenerated_manifest(repo):
    root, base = repo
    for index, (name, data) in enumerate(gate.synthetic_outputs(42).items()):
        commit(root, f"demo/new-seed-{index}" + Path(name).suffix, data)
    assert gate.inspect(root, base)["status"] == "PASS"


def test_forged_seed_label_alone_does_not_register_a_source(repo):
    root, base = repo
    commit(root, "claim.json", b'{"data_class":"SYNTHETIC_ONLY","seed":42}')
    out = gate.inspect(root, base)
    assert out["status"] == "REVIEW_REQUIRED"
    assert out["violations"][0]["reason"] == "UNVERIFIED_SYNTHETIC_CLAIM"


@pytest.mark.parametrize("suffix", [".json", ".txt", ".md", ".py"])
def test_renaming_structured_business_records_does_not_grant_clearance(repo, suffix):
    root, base = repo
    commit(root, "renamed" + suffix, b'{"farm_name":"SYNTHETIC_LABEL_ONLY","weight_kg":42.123456}')
    assert gate.inspect(root, base)["status"] == "REVIEW_REQUIRED"


def test_removing_frozen_candidate_does_not_become_an_approved_cleanup(repo):
    root, _ = repo
    path = "configs/factory_aliases.yaml"
    commit(root, path, b"SYNTHETIC_ONLY: metadata")
    base = git(root, "rev-parse", "HEAD").stdout.decode().strip()
    git(root, "rm", "--", path)
    git(root, "commit", "-qm", "SYNTHETIC_ONLY remove")
    out = gate.inspect(root, base)
    assert out["status"] == "REVIEW_REQUIRED"
    assert out["violations"][0]["reason"] == "HISTORICAL_CANDIDATE_REMOVED_REVIEW_REQUIRED"


def test_normal_changes_to_existing_code_role_are_not_automatically_private(repo):
    root, _ = repo
    path = "backend/app/etl/history/normalizer.py"
    commit(root, path, b"def calculate(value: str) -> str:\n    return value\n")
    base = git(root, "rev-parse", "HEAD").stdout.decode().strip()
    commit(root, path, b"def calculate(value: str) -> str:\n    return value.strip()\n")
    assert gate.inspect(root, base)["status"] == "PASS"


@pytest.mark.parametrize("quantity", ['"42.123456"', "42.123456"])
def test_exact_quantity_strings_and_numbers_both_require_review(repo, quantity):
    root, base = repo
    commit(root, "amount.json", ('{"quantity_kg":' + quantity + "}").encode())
    out = gate.inspect(root, base)
    assert out["status"] == "REVIEW_REQUIRED"
    assert "42.123456" not in json.dumps(out)


def test_known_legacy_blob_rename_is_rejected_without_opening(repo, monkeypatch):
    from scripts.ci.check_workbook_distribution import WORKBOOK_BLOBS

    root, base = repo
    blob = sorted(WORKBOOK_BLOBS)[0]
    oldtree = git(root, "rev-parse", base + "^{tree}").stdout.decode().strip()
    entries = (
        git(root, "ls-tree", oldtree).stdout + f"100644 blob {blob}\tlooks_public.py\n".encode()
    )
    tree = git(root, "mktree", "--missing", input=entries).stdout.decode().strip()

    def no_blob(*args, **kwargs):
        raise AssertionError("legacy workbook must not be opened")

    monkeypatch.setattr(gate, "read_public_text", no_blob)
    out = gate.inspect(root, base, tree)
    assert out["status"] == "REVIEW_REQUIRED"
    assert out["violations"][0]["reason"] == "HISTORICAL_WORKBOOK_REINTRODUCTION"
    assert git(root, "cat-file", "-e", blob, check=False).returncode != 0
