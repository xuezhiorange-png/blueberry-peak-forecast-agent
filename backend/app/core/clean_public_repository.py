"""Bounded option-A rehearsal, never a publisher or a real-history cleaner.

Only exact reviewed current-HEAD candidates enter a newly owned object store.
The catalog seal is a review boundary, not a caller-supplied publication grant.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree

from backend.app.core import historical_code_identity as history

ROOT = Path(__file__).resolve().parents[3]
CATALOG = ROOT / "docs/tech-debt/td01f-public-code-candidates-r1.json"
CATALOG_SHA256 = "2a4386ee221bab46832c69f0a9be98836791df4db8bdc5db9e9f860f22466255"
# Identity metadata only. These objects are never opened, downloaded or copied.
BLOCKED_BLOBS = frozenset(
    {
        "3413dbbc284312e75a2df98992a6ab66cfa87dbd",
        "a045348c4c72507ae367b4e30f267fcf19c490c1",
        "176898e7d1924945389f0f9f9f6d42d5ed58878f",
        "d5116f568420aec3fb26e88b5336778ce0a1e011",
        "cf3a861302e30722396171ac739dc81ffdda6c6b",
        "4afa86882d862cb15ffb9f5c242d3e8baa93c4ab",
        "74eb1b2deb521f0b7646be57c20c65a0680ccc9a",
    }
)
_OWNED: set[Path] = set()
_SYNTHETIC_PREFIX = "docs/tech-debt/td01c-synthetic-example/"
CURVE_CHECK = """
import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
import backend
from backend.research.v019_daily_curve import (
    BASELINE_POLICY, CurveInput, DailyKg, generate_candidate, select_window,
)
assert Path(backend.__file__).resolve().is_relative_to(Path.cwd())
start = date(2040, 7, 1)
rows = tuple(DailyKg(start + timedelta(days=i), Decimal(v))
             for i, v in enumerate(['1']*7 + ['2']*7 + ['4']*7))
result = generate_candidate(CurveInput(
    season_start=start, support_start=start, support_end=rows[-1].day,
    baseline=rows, baseline_source_sha256='a'*64,
    baseline_policy=BASELINE_POLICY, timezone='Asia/Shanghai'))
assert sum(r.kg for r in result.rows) == Decimal('49')
assert all(b.baseline_micro_kg == b.candidate_micro_kg for b in result.bins)
h15 = select_window(result, origin=start, horizon=15)
assert select_window(result, origin=start, horizon=7) == h15[:7]
print(json.dumps({'data_class':'SYNTHETIC_ONLY', 'days':len(rows),
                  'bin_mass_conserved':True, 'h7_is_h15_prefix':True,
                  'result_sha256':result.result_sha256}, sort_keys=True))
"""


class CleanRepositoryError(AssertionError):
    """Stable failure without business content or local paths."""


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def _safe_path(value: str) -> None:
    path = PurePosixPath(value)
    if (
        not value
        or str(path) != value
        or path.is_absolute()
        or any(part in {".", "..", ".git"} or part.startswith("-") for part in path.parts)
        or any(char in value for char in "\\:\x00\n\r")
    ):
        raise CleanRepositoryError("INVALID_CANDIDATE_PATH")


def _oid(value: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise CleanRepositoryError("INVALID_OBJECT_IDENTITY")


def candidates() -> dict[str, dict[str, str]]:
    raw = CATALOG.read_bytes()
    if _digest(raw) != CATALOG_SHA256:
        raise CleanRepositoryError("CANDIDATE_CATALOG_SEAL_MISMATCH")
    payload = json.loads(raw)
    entries: dict[str, dict[str, str]] = {}
    for row in payload["entries"]:
        path = row["repository_relative_path"]
        _safe_path(path)
        _oid(row["git_blob_oid"])
        if row["git_blob_oid"] in BLOCKED_BLOBS:
            raise CleanRepositoryError("BLOCKED_SOURCE_OBJECT")
        if path in entries or row["publication_status"] != "REHEARSAL_CANDIDATE_ONLY":
            raise CleanRepositoryError("INVALID_CANDIDATE_RECORD")
        if row["role"] == "TD01C_VERIFIED_SYNTHETIC":
            if not path.startswith(_SYNTHETIC_PREFIX):
                raise CleanRepositoryError("UNREGISTERED_SYNTHETIC_PATH")
        elif not (
            path == "pyproject.toml"
            or path.endswith(".py")
            and path.startswith(("backend/app/", "backend/research/"))
            or path in {"backend/__init__.py", "backend/tests/etl/test_synthetic_publication.py"}
        ):
            raise CleanRepositoryError("OWNER_REVIEW_REQUIRED")
        entries[path] = row
    return entries


def _metadata(repo: Path, path: str) -> tuple[str, str]:
    rows = history._git(repo, "ls-tree", "-z", "HEAD", "--", path).split(b"\0")
    rows = [row for row in rows if row]
    if len(rows) != 1:
        raise CleanRepositoryError("CURRENT_HEAD_CANDIDATE_MISSING")
    metadata, actual_path = rows[0].split(b"\t", 1)
    mode, kind, oid = metadata.decode().split()
    if actual_path.decode() != path or mode != "100644" or kind != "blob":
        raise CleanRepositoryError("CANDIDATE_TYPE_MISMATCH")
    if oid in BLOCKED_BLOBS:
        raise CleanRepositoryError("BLOCKED_SOURCE_OBJECT")
    return oid, mode


def candidate_bytes(repo: Path, path: str, *, generated: bytes | None = None) -> bytes:
    _safe_path(path)
    row = candidates().get(path)
    if row is None:
        raise CleanRepositoryError("OWNER_REVIEW_REQUIRED")
    oid, _ = _metadata(repo, path)
    if oid != row["git_blob_oid"]:
        raise CleanRepositoryError("CURRENT_HEAD_IDENTITY_CHANGED")
    if row["role"] == "TD01C_VERIFIED_SYNTHETIC":
        # Authenticate regenerated complete bytes BEFORE opening an archive Blob.
        if generated is None or history._blob_id(generated) != oid:
            raise CleanRepositoryError("SYNTHETIC_FULL_CONTENT_BINDING_REQUIRED")
    raw = history._git(repo, "cat-file", "blob", oid)
    if history._blob_id(raw) != oid or _digest(raw) != row["sha256"]:
        raise CleanRepositoryError("CANDIDATE_CONTENT_CHANGED")
    if generated is not None and raw != generated:
        raise CleanRepositoryError("SYNTHETIC_FULL_CONTENT_BINDING_REQUIRED")
    return raw


@contextmanager
def owned_repository() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="TD01F_CLEAN_CODE_ONLY_") as folder:
        repo = Path(folder).resolve()
        repo.chmod(0o700)
        history._git(repo, "init", "-q", "--object-format=sha1", "--template=", "-b", "main")
        _OWNED.add(repo)
        try:
            yield repo
        finally:
            _OWNED.remove(repo)


def _owned(repo: Path) -> None:
    if (
        repo.resolve() not in _OWNED
        or repo.is_symlink()
        or (repo / ".git").is_symlink()
        or (repo / ".git/objects").is_symlink()
    ):
        raise CleanRepositoryError("OWNED_TEMPORARY_REPOSITORY_REQUIRED")


def _write_git(repo: Path, *args: str, data: bytes | None = None) -> bytes:
    _owned(repo)
    return history._git(repo, *args, data=data)


def populate(repo: Path, source: Path = ROOT) -> dict[str, dict[str, str]]:
    _owned(repo)
    rows = candidates()
    # Import only after matching every reviewed producer/parent dependency.
    for path, row in rows.items():
        if row["role"] != "TD01C_VERIFIED_SYNTHETIC":
            raw = candidate_bytes(source, path)
            if (source / path).read_bytes() != raw:
                raise CleanRepositoryError("REVIEWED_PRODUCER_WORKTREE_CHANGED")
    from backend.app.etl.history.synthetic_publication import export, generate

    with tempfile.TemporaryDirectory(prefix="TD01F_GENERATED_ONLY_") as folder:
        target = Path(folder) / "generated"
        export(generate(41), target)
        generated = {file.name: file.read_bytes() for file in target.iterdir()}
    for path, row in rows.items():
        raw = candidate_bytes(
            source,
            path,
            generated=generated[PurePosixPath(path).name]
            if row["role"] == "TD01C_VERIFIED_SYNTHETIC"
            else None,
        )
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        target.chmod(0o600)
        oid = _write_git(repo, "hash-object", "-w", "--stdin", data=raw).decode().strip()
        _write_git(repo, "update-index", "--add", "--cacheinfo", f"100644,{oid},{path}")
    tree = _write_git(repo, "write-tree").decode().strip()
    commit = _write_git(repo, "commit-tree", tree, data=b"TD01F LOCAL CANDIDATE ROOT ONLY\n")
    _write_git(repo, "update-ref", "refs/heads/main", commit.decode().strip())
    return rows


def verify_objects(repo: Path) -> dict[str, object]:
    _owned(repo)
    gitdir = repo / ".git"
    if not gitdir.is_dir() or gitdir.is_symlink():
        raise CleanRepositoryError("NONLOCAL_OBJECT_DATABASE")
    if any(
        (gitdir / p).exists() or (gitdir / p).is_symlink()
        for p in (
            "objects/info/alternates",
            "objects/info/http-alternates",
            "commondir",
            "shallow",
            "info/grafts",
            "modules",
        )
    ):
        raise CleanRepositoryError("HIDDEN_HISTORY_OR_ALTERNATES")
    config = history._git(repo, "config", "--local", "--name-only", "--list").decode().splitlines()
    if any(
        key
        not in {
            "core.repositoryformatversion",
            "core.filemode",
            "core.bare",
            "core.logallrefupdates",
            "core.ignorecase",
            "core.precomposeunicode",
        }
        for key in config
    ):
        raise CleanRepositoryError("UNEXPECTED_GIT_CONFIGURATION")
    refs = history._git(repo, "for-each-ref", "--format=%(refname)").decode().splitlines()
    if refs != ["refs/heads/main"]:
        raise CleanRepositoryError("UNEXPECTED_REF_OR_TAG")
    # Inspect Tree metadata before traversing possibly missing forbidden objects.
    for metadata_row in history._git(repo, "ls-tree", "-r", "-z", "HEAD").split(b"\0"):
        if metadata_row and metadata_row.split(b"\t", 1)[0].decode().split()[2] in BLOCKED_BLOBS:
            raise CleanRepositoryError("BLOCKED_SOURCE_OBJECT")
    objects = dict(
        line.split()
        for line in history._git(
            repo, "cat-file", "--batch-all-objects", "--batch-check=%(objectname) %(objecttype)"
        )
        .decode()
        .splitlines()
    )
    if BLOCKED_BLOBS.intersection(objects):
        raise CleanRepositoryError("BLOCKED_SOURCE_OBJECT")
    reachable = {
        line.split()[0]
        for line in history._git(repo, "rev-list", "--objects", "--all").decode().splitlines()
    }
    if set(objects) != reachable:
        raise CleanRepositoryError("UNEXPECTED_UNREACHABLE_OBJECT")
    commits = [oid for oid, kind in objects.items() if kind == "commit"]
    if len(commits) != 1 or any(
        line.startswith(b"parent ")
        for line in history._git(repo, "cat-file", "commit", commits[0]).splitlines()
    ):
        raise CleanRepositoryError("ORIGINAL_HISTORY_OR_PARENT_PRESENT")
    expected = candidates()
    actual: dict[str, str] = {}
    for line in history._git(repo, "ls-tree", "-r", "-z", "HEAD").split(b"\0"):
        if line:
            meta, raw_path = line.split(b"\t", 1)
            mode, kind, oid = meta.decode().split()
            name = raw_path.decode()
            if (
                mode != "100644"
                or kind != "blob"
                or name not in expected
                or oid != expected[name]["git_blob_oid"]
            ):
                raise CleanRepositoryError("UNALLOWLISTED_TREE_ENTRY")
            actual[name] = oid
    if actual != {path: row["git_blob_oid"] for path, row in expected.items()}:
        raise CleanRepositoryError("CANDIDATE_TREE_MISMATCH")
    if {oid for oid, kind in objects.items() if kind == "blob"} != set(actual.values()):
        raise CleanRepositoryError("UNALLOWLISTED_BLOB")
    for path, row in expected.items():
        target = repo / path
        if (
            target.is_symlink()
            or not target.is_file()
            or _digest(target.read_bytes()) != row["sha256"]
        ):
            raise CleanRepositoryError("EXPORTED_SOURCE_BYTES_CHANGED")
    working = {
        str(p.relative_to(repo))
        for p in repo.rglob("*")
        if p.is_file() and ".git" not in p.relative_to(repo).parts
    }
    if working != set(expected):
        raise CleanRepositoryError("UNALLOWLISTED_WORKING_FILE")
    history._git(repo, "fsck", "--full", "--strict", "--no-reflogs")
    # There is only our independently authored root; no original Commit was copied.
    return {
        "status": "PASS",
        "root_commit": commits[0],
        "object_count": len(objects),
        "git_fsck": "PASS",
        "git_objects": [{"oid": oid, "type": kind} for oid, kind in sorted(objects.items())],
        "file_count": len(actual),
        "parent_count": 0,
        "remote_count": 0,
        "tag_count": 0,
        "alternates_present": False,
        "all_objects_reachable": True,
        "known_historical_xls_blobs_present": False,
        "blocked_compressed_assets_present": False,
        "original_commits_reachable": False,
        "original_tags_copied": False,
        "source_bytes_unchanged": True,
        "publication_approved": False,
    }


def run_subset(repo: Path) -> dict[str, object]:
    _owned(repo)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "PYTHON", "PYTEST"))}
    env.update(PYTHONPATH=str(repo), PYTHONDONTWRITEBYTECODE="1", APP_ENV="test")
    checks = {
        "ruff": [sys.executable, "-m", "ruff", "check", "--no-cache", "backend"],
        "format": [sys.executable, "-m", "ruff", "format", "--check", "--no-cache", "backend"],
        "strict_mypy": [
            sys.executable,
            "-m",
            "mypy",
            "--cache-dir=/dev/null",
            "backend/app",
            "backend/research",
        ],
        "synthetic_publication_tests": [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "backend/tests/etl/test_synthetic_publication.py",
        ],
        "pure_daily_curve": [sys.executable, "-c", CURVE_CHECK],
    }
    results: dict[str, object] = {}
    for name, command in checks.items():
        with tempfile.TemporaryDirectory(prefix="TD01F_TEST_EVIDENCE_") as folder:
            junit = Path(folder) / "junit.xml"
            if name == "synthetic_publication_tests":
                command = [*command, "--junitxml=" + str(junit)]
            run = subprocess.run(command, cwd=repo, env=env, capture_output=True, check=False)
            junit_raw = junit.read_bytes() if junit.exists() else None
        text = run.stdout.decode(errors="replace")
        summary = next((line.strip() for line in reversed(text.splitlines()) if line.strip()), "")
        # No paths, models, records or temporary directory identities in public output.
        if name == "pure_daily_curve" and run.returncode == 0:
            summary = "SYNTHETIC_ONLY_BIN_MASS_AND_H7_PREFIX_VERIFIED"
        results[name] = {
            "status": "PASS" if run.returncode == 0 else "FAIL",
            "exit_code": run.returncode,
            "summary": re.sub(r" in [0-9.]+s.*$", "", summary)
            if str(repo) not in summary
            else "SEE_PRIVATE_EXECUTION_LOG",
        }
        if junit_raw is not None:
            _JUNIT_LOGS[name] = junit_raw
            cases = list(ElementTree.fromstring(junit_raw).iter("testcase"))
            failures = [
                case
                for case in cases
                if case.find("failure") is not None or case.find("error") is not None
            ]
            blocked = (
                len(failures) == 1
                and run.returncode == 1
                and failures[0].get("name")
                == "test_path_only_audit_registry_and_original_ref_inventory_are_bound"
                and "FileNotFoundError" in ElementTree.tostring(failures[0], encoding="unicode")
                and "td01c-public-derived-audit-summary.json"
                in ElementTree.tostring(failures[0], encoding="unicode")
            )
            results[name] = {
                "status": "BLOCKED" if blocked else "PASS" if run.returncode == 0 else "FAIL",
                "exit_code": run.returncode,
                "case_count": len(cases),
                "passed": len(cases) - len(failures),
                "failed": len(failures),
                "blocked_tests": [case.get("name") for case in failures] if blocked else [],
                "reason": "UNEXPORTED_HISTORICAL_AUDIT_METADATA" if blocked else None,
                "failure_not_suppressed": True,
            }
        # Evidence persists outside the owned repository before its cleanup.
        _EXECUTION_LOGS[name] = (run.stdout, run.stderr)
    return results


_EXECUTION_LOGS: dict[str, tuple[bytes, bytes]] = {}
_JUNIT_LOGS: dict[str, bytes] = {}


def dependency_coverage(source: Path) -> dict[str, object]:
    docs = source / "docs/tech-debt"
    unresolved = json.loads(
        (docs / "td01e-unresolved-historical-dependencies-r1.json").read_bytes()
    )
    consumers = json.loads((docs / "td01e-historical-consumers-r1.json").read_bytes())
    owner = json.loads((docs / "td01d-classification-summary.json").read_bytes())
    return {
        "inventory_reused_not_rescanned": True,
        "original_candidate_count": owner["candidate_count"],
        "owner_decisions_reused": owner["owner_decision_items"],
        "owner_priority_paths": [
            {
                "repository_relative_path": r["PATH"],
                "decision": r["DECISION_GROUP"],
                "review_state": "OWNER_REVIEW_REQUIRED",
                "evidence_strength": r["EVIDENCE_STRENGTH"],
                "original_classification": r["CLASSIFICATION"],
            }
            for r in owner["priority"]
        ],
        "verified_historical_code_identities": len(history.catalog()),
        "historical_code_relocated_in_clean_candidate": False,
        "historical_code_compatibility": "TD01E_OWNED_REHEARSAL_ONLY_NOT_ACTIVATED_HERE",
        "non_code_dependencies_count": len(unresolved["non_code_dependencies"]),
        "non_code_dependencies": unresolved["non_code_dependencies"],
        "unadmitted_identities": unresolved["explicit_unadmitted_identities"],
        "fixed_identity_consumers": [
            {
                "repository_relative_path": r["consumer_path"],
                "class": r["consumer_class"],
                "isolated_status": "BLOCKED_ORIGINAL_HISTORY_OR_EVIDENCE_NOT_EXPORTED"
                if r["consumer_class"] == "HISTORICAL_SOURCE_CONSUMER"
                else "NOT_VERIFIED_IN_SUBSET",
            }
            for r in consumers["consumers"]
        ],
        "public_increment_baseline": unresolved["public_increment_baseline"],
        "source_002_read": False,
        "owner_scope": {"D02": "OWNER_PENDING", "D03": "OWNER_PENDING", "D06": "OWNER_PENDING"},
        "public_code_clearance": "EXPLICIT_LIMITED_CANDIDATES_ONLY",
        "capabilities": [
            {
                "module": "etl.history normalization/schema/fingerprint/synthetic_publication",
                "status": "EXECUTED_WITH_INDEPENDENT_SYNTHETIC_DATA",
                "limit": "24_PASSED_ONE_HISTORICAL_AUDIT_ASSERTION_BLOCKED",
            },
            {
                "module": "research.v019_daily_curve",
                "status": "EXECUTED_PURE_SYNTHETIC_MASS_AND_H7_PREFIX_CHECK",
                "limit": "ORIGINAL_FULL_RESEARCH_CONTRACT_NOT_EXPORTED",
            },
            {
                "module": "rolling_forecast",
                "status": "NOT_EXPORTED_NOT_VERIFIED",
                "limit": "REAL_FROZEN_FIT_PRIVATE_MODEL_AND_AUTHORIZED_SOURCE_REQUIRED",
            },
            {
                "module": "research.v021_cycle_features/structure_scenarios/evaluation_readiness",
                "status": "NOT_EXPORTED_NOT_VERIFIED",
                "limit": "SYNTHETIC_PACKAGE_AND_FROZEN_CONTRACT_CLEARANCE_NOT_COMPLETED",
            },
            {
                "module": "local_auth/MCP/forecast historical contracts",
                "status": "BLOCKED_ORIGINAL_COMMIT_AND_NON_CODE_DEPENDENCIES",
                "limit": "NO_NEW_GRAPH_FALLBACK_ACTIVATED",
            },
            {
                "module": "PostgreSQL migrations/application persistence",
                "status": "NOT_EXPORTED_NOT_RUN",
                "limit": "DATABASE_SCHEMA_CONFIG_AND_TEST_PROFILE_NOT_IN_CANDIDATE",
            },
            {
                "module": "frontend/Dashboard",
                "status": "NOT_EXPORTED_NOT_RUN",
                "limit": "PUBLIC_LITERAL_REVIEW_AND_HISTORICAL_EVIDENCE_NOT_CLEARED",
            },
        ],
    }


def rehearse(source: Path = ROOT) -> dict[str, object]:
    head = history._git(source, "rev-parse", "--verify", "HEAD^{commit}").decode().strip()
    rows = candidates()
    with owned_repository() as repo:
        populate(repo, source)
        proof = verify_objects(repo)
        checks = run_subset(repo)
        # Tools are not permitted to leave extra objects, refs, files or a changed source.
        proof_after = verify_objects(repo)
        if proof != proof_after:
            raise CleanRepositoryError("ISOLATED_TEST_CHANGED_REPOSITORY")
        historical = {}
        for commit in (
            "320f2046e3105b1b55da9cb037892571110b584a",
            "e9812e82067dceae444ff0707ceeb2f560c1018e",
            "0124371b433d1b3c34e5e59a2a9a5e621a570f3b",
        ):
            status = history._run(repo, "cat-file", "-e", commit + "^{commit}").returncode
            historical[commit] = {"exit_code": status, "status": "BLOCKED_ORIGINAL_COMMIT_ABSENT"}
    return {
        "clean-repository-manifest.json": {
            "schema": "TD01F_LOCAL_REHEARSAL_R1",
            "actual_source_head": head,
            "candidate_count": len(rows),
            "catalog_sha256": CATALOG_SHA256,
            "entries": list(rows.values()),
            "original_history_copied": False,
            "public_repository_created": False,
            "owner_publication_approval": False,
        },
        "clean-repository-object-verification.json": proof,
        "public-code-dependency-coverage.json": dependency_coverage(source),
        "public-ci-compatibility-report.json": {
            "isolated_checks": checks,
            "original_ci_prechecks": historical,
            "original_complete_ci": "BLOCKED_NOT_EXECUTED_IN_NEW_ROOT",
            "original_test_assertions_changed": False,
            "original_skips_changed": False,
            "postgres": "NOT_RUN_NO_DATABASE_INPUTS_OR_SERVICE_IN_CANDIDATE",
            "frontend": "NOT_RUN_OWNER_SCOPE_AND_DEPENDENCIES_NOT_CLEARED",
            "runtime_application": "NOT_VALIDATED_AS_WHOLE_APPLICATION",
            "public_increment_baseline": "BLOCKED_PENDING_OWNER_SCOPE_D02_D03_D06",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    reports = rehearse()
    args.output_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name, payload in reports.items():
        file = args.output_dir / name
        file.write_bytes(_canonical(payload))
        file.chmod(0o600)
    for name, (out, err) in _EXECUTION_LOGS.items():
        for suffix, raw in (("stdout", out), ("stderr", err)):
            file = args.output_dir / f"{name}.{suffix}.log"
            file.write_bytes(raw)
            file.chmod(0o600)
    for name, raw in _JUNIT_LOGS.items():
        file = args.output_dir / f"{name}.junit.xml"
        file.write_bytes(raw)
        file.chmod(0o600)
    print(
        json.dumps(
            {name: _digest(_canonical(payload)) for name, payload in reports.items()},
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
