"""Synthetic Git trees and packages; no historical workbook is opened."""

from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path, PurePosixPath

import pytest
import yaml
from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[3]
NAMES = ("2024_2025_receipts.xls", "2025_2026_receipts.xls")
pytestmark = [pytest.mark.unit, pytest.mark.contract]


def _git(root, *args, input=None, check=True):
    return subprocess.run(
        ["git", *args],
        cwd=root,
        input=input,
        capture_output=True,
        check=check,
        env={**os.environ, "GIT_NO_LAZY_FETCH": "1"},
    )


def _repository(root):
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "SYNTHETIC_TEST")
    _git(root, "config", "user.email", "synthetic@example.invalid")
    _git(root, "config", "commit.gpgsign", "false")


def _files(root):
    # These are deliberately plain synthetic text, not business workbooks.
    paths = [
        "backend/__init__.py",
        "backend/SYNTHETIC/keep.py",
        "backend/SYNTHETIC/LEGAL_SYNTHETIC.xls",
        "backend/SYNTHETIC/LEGAL_SYNTHETIC.xlsx",
        *("data/raw/" + name for name in NAMES),
        *("backend/SYNTHETIC/" + name for name in NAMES),
    ]
    for name in paths:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("" if path.suffix == ".py" else "SYNTHETIC_ONLY_NOT_A_WORKBOOK\n")
    return paths


def _unsafe(names):
    return sorted(name for name in names if PurePosixPath(name).name in NAMES)


@pytest.mark.parametrize("protected", [True, False])
def test_real_git_source_archive_preserves_only_legal_synthetic_files(tmp_path, protected):
    root = tmp_path / "SYNTHETIC_REPOSITORY"
    _repository(root)
    paths = _files(root)
    attributes = ROOT / ".gitattributes"
    if protected and attributes.exists():
        (root / ".gitattributes").write_bytes(attributes.read_bytes())
        paths.append(".gitattributes")
    _git(root, "add", "--", *paths)
    _git(root, "commit", "-qm", "SYNTHETIC fixture")
    archive = tmp_path / "SYNTHETIC-source.tar"
    archive.write_bytes(_git(root, "archive", "--format=tar", "HEAD").stdout)
    with tarfile.open(archive) as stream:
        names = stream.getnames()  # archive metadata only
    assert "backend/SYNTHETIC/LEGAL_SYNTHETIC.xls" in names
    assert "backend/SYNTHETIC/LEGAL_SYNTHETIC.xlsx" in names
    assert (not _unsafe(names)) if protected else len(_unsafe(names)) == 4


@pytest.fixture(scope="module")
def build_backend(tmp_path_factory):
    # Reuse the declared PEP 517 backend. If CI has no runtime setuptools,
    # install only build-system requirements into an isolated fixture target.
    requirements = tomllib.loads((ROOT / "pyproject.toml").read_text())["build-system"]["requires"]
    try:
        installed = importlib.metadata.version("setuptools")
    except importlib.metadata.PackageNotFoundError:
        installed = "0"
    if installed in Requirement(requirements[0]).specifier:
        return None
    target = tmp_path_factory.mktemp("SYNTHETIC_BUILD_BACKEND")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--target", str(target), *requirements],
        check=True,
        capture_output=True,
    )
    return target


@pytest.mark.parametrize("protected", [True, False])
def test_real_sdist_and_wheel_exclude_business_names_not_legal_fixtures(
    tmp_path, build_backend, protected
):
    root = tmp_path / "SYNTHETIC_PACKAGE"
    root.mkdir()
    _files(root)
    configuration = tomllib.loads((ROOT / "pyproject.toml").read_text())
    # Only the real package-selection/exclusion metadata is reused. No actual
    # project modules, dependencies, model parameters or data enter this build.
    package_selection = configuration["tool"]["setuptools"]["packages"]["find"]
    text = (
        '[build-system]\nrequires = ["setuptools>=80.0"]\n'
        'build-backend = "setuptools.build_meta"\n'
        '[project]\nname = "td01b-synthetic-fixture"\nversion = "0.0.0"\n'
        "[tool.setuptools.packages.find]\n"
    )
    text += "\n".join(
        json.dumps(key) + " = " + json.dumps(value) for key, value in package_selection.items()
    )
    text += "\n"
    (root / "pyproject.toml").write_text(text)
    manifest = "recursive-include backend *\nrecursive-include data/raw *\n"
    policy = ROOT / "MANIFEST.in"
    if protected and policy.exists():
        manifest += policy.read_text()
    (root / "MANIFEST.in").write_text(manifest)
    env = dict(os.environ)
    if build_backend is not None:
        env["PYTHONPATH"] = str(build_backend)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from setuptools.build_meta import build_sdist, build_wheel; "
            "build_sdist('dist'); build_wheel('dist')",
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    with tarfile.open(next((root / "dist").glob("*.tar.gz"))) as stream:
        source_names = stream.getnames()
    with zipfile.ZipFile(next((root / "dist").glob("*.whl"))) as stream:
        wheel_names = stream.namelist()
    for names in (source_names, wheel_names):
        assert any(name.endswith("LEGAL_SYNTHETIC.xls") for name in names)
        assert any(name.endswith("LEGAL_SYNTHETIC.xlsx") for name in names)
        assert (not _unsafe(names)) if protected else bool(_unsafe(names))


def test_current_tree_has_no_reserved_names_or_historical_blobs():
    from scripts.ci.check_workbook_distribution import tree_violations

    tree, violations = tree_violations(ROOT)
    assert len(tree) == 40
    assert violations == []


def test_guard_identities_match_audited_metadata_and_deterministic_ref_inventory():
    from scripts.ci.check_workbook_distribution import WORKBOOK_BLOBS, WORKBOOK_NAMES

    directory = ROOT / "docs/tech-debt"
    report = json.loads((directory / "td01b-historical-xls-exposure-r1.json").read_text())
    assert WORKBOOK_NAMES == set(NAMES)
    assert WORKBOOK_BLOBS == {row["git_blob_id"] for row in report["workbooks"]}
    assert report["total_workbook_bytes"] == sum(row["bytes"] for row in report["workbooks"])
    inventory = directory / report["ref_inventory"]["path"]
    assert hashlib.sha256(inventory.read_bytes()).hexdigest() == report["ref_inventory"]["sha256"]
    with inventory.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == report["ref_inventory"]["rows"]
    assert [row["ref"] for row in rows] == sorted({row["ref"] for row in rows})
    for kind, count in [("heads", "branch_count"), ("tags", "tag_count")]:
        assert (
            sum(row["ref"].startswith(f"refs/{kind}/") for row in rows) == report["counts"][count]
        )
    for row in rows:
        assert row["current_tree_exposed"] in {"true", "false"}
        actual = {row["2024_2025_blob"], row["2025_2026_blob"]} - {""}
        assert actual <= WORKBOOK_BLOBS
        assert bool(actual) == (row["current_tree_exposed"] == "true")
    assert report["raw_workbook_content_read"] is False
    assert report["historical_exposure_eliminated"] is False


@pytest.mark.parametrize("name", NAMES)
def test_existing_index_guard_rejects_synthetic_metadata_without_materializing_xls(
    tmp_path, monkeypatch, name
):
    from backend.tests import test_version_contract as existing

    root = tmp_path / "SYNTHETIC_INDEX"
    _repository(root)
    blob = _git(
        root, "hash-object", "-w", "--stdin", input=b"SYNTHETIC_NOT_A_WORKBOOK"
    ).stdout.strip()
    _git(
        root,
        "update-index",
        "--add",
        "--cacheinfo",
        "100644," + blob.decode() + ",data/raw/" + name,
    )
    monkeypatch.setattr(existing, "ROOT", root)
    assert not (root / "data/raw" / name).exists()
    with pytest.raises(AssertionError):
        existing.test_legacy_workbooks_remain_untracked(name.removesuffix("_receipts.xls"))


@pytest.mark.parametrize("known_blob", [False, True])
def test_real_cli_rejects_synthetic_tree_by_name_or_missing_blob_metadata(tmp_path, known_blob):
    from scripts.ci.check_workbook_distribution import WORKBOOK_BLOBS

    root = tmp_path / "SYNTHETIC_TREE"
    _repository(root)
    if known_blob:
        # Only a public object identifier is used; its bytes do not exist in
        # this repository, which has no remote and cannot fetch the workbook.
        blob = sorted(WORKBOOK_BLOBS)[0]
        name = "SYNTHETIC_ALIAS.bin"
        assert _git(root, "cat-file", "-e", blob, check=False).returncode != 0
    else:
        blob = (
            _git(root, "hash-object", "-w", "--stdin", input=b"SYNTHETIC_ONLY")
            .stdout.decode()
            .strip()
        )
        name = NAMES[0]
    tree = _git(root, "mktree", "--missing", input=f"100644 blob {blob}\t{name}\n".encode())
    tree = tree.stdout.decode().strip()
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/ci/check_workbook_distribution.py"),
            "--repo",
            str(root),
            "--tree",
            tree,
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["status"] == "FAIL" and report["workbook_content_read"] is False
    assert report["violations"] == [
        {
            "path": name,
            "blob_id": blob,
            "reason": "KNOWN_HISTORICAL_WORKBOOK_BLOB"
            if known_blob
            else "RESERVED_BUSINESS_WORKBOOK_NAME",
        }
    ]
    assert not (root / name).exists()
    if known_blob:
        assert _git(root, "cat-file", "-e", blob, check=False).returncode != 0


def test_tree_inspection_never_requests_blob_bytes_or_lazy_fetch(tmp_path, monkeypatch):
    from scripts.ci import check_workbook_distribution as guard

    root = tmp_path / "SYNTHETIC_METADATA"
    _repository(root)
    blob = (
        _git(root, "hash-object", "-w", "--stdin", input=b"SYNTHETIC_ONLY").stdout.decode().strip()
    )
    tree = _git(root, "mktree", input=f"100644 blob {blob}\tLEGAL_SYNTHETIC.xls\n".encode())
    original = guard.subprocess.check_output
    commands = []

    def metadata_only(command, **kwargs):
        commands.append(command)
        assert command[1] in {"rev-parse", "ls-tree"}
        assert kwargs["env"]["GIT_NO_LAZY_FETCH"] == "1"
        return original(command, **kwargs)

    monkeypatch.setattr(guard.subprocess, "check_output", metadata_only)
    _, violations = guard.tree_violations(root, tree.stdout.decode().strip())
    assert violations == [] and len(commands) == 2


def test_ci_keeps_guards_and_real_synthetic_docker_probe_fail_closed():
    workflow = yaml.load((ROOT / ".github/workflows/ci.yml").read_text(), Loader=yaml.BaseLoader)
    for job_name, step_name in [
        ("static", "Reject historical business workbook metadata"),
        ("compose-smoke", "Verify synthetic workbook context exclusions"),
    ]:
        job = workflow["jobs"][job_name]
        assert job.get("continue-on-error", "false") == "false"
        step = next(step for step in job["steps"] if step.get("name") == step_name)
        assert "if" not in step and step.get("continue-on-error", "false") == "false"
        assert "--repo . --tree HEAD" in step["run"] and "||" not in step["run"]
        if job_name == "compose-smoke":
            assert "--docker-synthetic-probe" in step["run"]
            assert "reports/security/workbook-distribution.json" in step["run"]


@pytest.mark.parametrize("tree", ["--help", "HEAD~1", "", "../data", "abc"])
def test_guard_requires_explicit_current_head_or_full_object_identity(tree):
    from scripts.ci.check_workbook_distribution import tree_violations

    with pytest.raises(ValueError, match="EXPLICIT_HEAD_OR_FULL_OBJECT_ID_REQUIRED"):
        tree_violations(ROOT, tree)
