"""Read exact reviewed code and scoped technical identities; never recover data.

CURRENT_HISTORY verifies original Commit+Path or its sealed, reviewed rewrite
locator. The Blob-only mode remains restricted to this process's repositories.
The catalog seal is a code-review trust root, not a caller-supplied approval.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
CATALOG_FILE = ROOT / "docs/tech-debt/td01e-code-identities-r1.json"
CATALOG_SHA256 = "80c60fe1b35204a8f3a819e3b84dd1ca3f2c469b7a71811b282c45ca3cbd6193"
TECHNICAL_CATALOG_FILE = ROOT / "docs/tech-debt/td01-technical-identities-r1.json"
TECHNICAL_CATALOG_SHA256 = "26287f3e643ff370404f1f587845dec5c2e98e50326db23b0399439a065d7a48"
_TECHNICAL_PAIRS = frozenset(
    {
        ("e9812e82067dceae444ff0707ceeb2f560c1018e", ".github/workflows/ci.yml"),
        ("320f2046e3105b1b55da9cb037892571110b584a", "pyproject.toml"),
        ("320f2046e3105b1b55da9cb037892571110b584a", "uv.lock"),
    }
)
_CONTROLLED: dict[Path, str] = {}
_CURRENT_REVISIONS: dict[Path, dict[tuple[str, str], str]] = {}
_CODE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".css", ".sh"}


class CodeIdentityError(AssertionError):
    """Stable fail-closed reason, without source bytes or private paths."""


class Mode(StrEnum):
    CURRENT_HISTORY = "CURRENT_HISTORY"
    CLEAN_GRAPH_REHEARSAL = "CLEAN_GRAPH_REHEARSAL"


@dataclass(frozen=True)
class Identity:
    commit: str
    path: str
    blob: str
    sha256: str
    source_class: str


def _check_path(path: str, *, code: bool = True) -> None:
    p = PurePosixPath(path)
    if (
        not path
        or p.is_absolute()
        or str(p) != path
        or any(part in {"..", "."} or part.startswith("-") for part in p.parts)
        or any(char in path for char in "\\:\x00\r\n,")
    ):
        raise CodeIdentityError("INVALID_CODE_PATH")
    if code and (
        p.suffix not in _CODE_SUFFIXES
        or not path.startswith(("backend/app/", "backend/tests/", "frontend/", "scripts/"))
    ):
        raise CodeIdentityError("NON_CODE_PATH_NOT_ADMITTED")


def _sha(value: str, length: int) -> None:
    if re.fullmatch(r"[0-9a-f]{" + str(length) + "}", value) is None:
        raise CodeIdentityError("INVALID_FIXED_CODE_IDENTITY")


def _sealed_records(file: Path, seal: str, schema: str) -> list[dict[str, object]]:
    raw = file.read_bytes()
    if hashlib.sha256(raw).hexdigest() != seal:
        raise CodeIdentityError("CATALOG_TRUST_ANCHOR_MISMATCH")
    payload: object = json.loads(raw)
    if not isinstance(payload, dict) or payload.get("schema_version") != schema:
        raise CodeIdentityError("INVALID_CODE_CATALOG")
    entries = payload.get("entries")
    if not isinstance(entries, list) or not all(isinstance(row, dict) for row in entries):
        raise CodeIdentityError("INVALID_CODE_CATALOG")
    return [{str(k): v for k, v in row.items()} for row in entries]


def _records() -> list[dict[str, object]]:
    return _sealed_records(CATALOG_FILE, CATALOG_SHA256, "TD01E_CODE_IDENTITY_R1")


def _field(row: dict[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str):
        raise CodeIdentityError("INVALID_CODE_CATALOG_FIELD")
    return value


def catalog() -> tuple[Identity, ...]:
    entries = []
    seen = set()
    for row in _records():
        commit, path = _field(row, "original_commit_sha"), _field(row, "repository_relative_path")
        oid, sha = _field(row, "original_git_blob_oid"), _field(row, "original_source_sha256")
        _sha(commit, 40)
        _sha(oid, 40)
        _sha(sha, 64)
        _check_path(path)
        source_class = _field(row, "source_class")
        if source_class not in {"APPLICATION_CODE", "TEST_CODE"} or row.get(
            "verification_status"
        ) not in {"VERIFIED_EXISTING_SHA256", "VERIFIED_EXISTING_GIT_BLOB"}:
            raise CodeIdentityError("UNVERIFIED_CODE_NOT_ADMITTED")
        if (commit, path) in seen:
            raise CodeIdentityError("DUPLICATE_CODE_IDENTITY")
        seen.add((commit, path))
        entries.append(Identity(commit, path, oid, sha, source_class))
    return tuple(entries)


def registered(commit: str, path: str) -> bool:
    return any(row.commit == commit and row.path == path for row in catalog())


def _technical_records() -> list[dict[str, object]]:
    rows = _sealed_records(
        TECHNICAL_CATALOG_FILE, TECHNICAL_CATALOG_SHA256, "TD01_TECHNICAL_IDENTITY_R1"
    )
    pairs = []
    for row in rows:
        pair = (_field(row, "original_commit_sha"), _field(row, "repository_relative_path"))
        if (
            pair not in _TECHNICAL_PAIRS
            or row.get("source_class") != "TECHNICAL_FILE"
            or row.get("verification_status") != "VERIFIED_EXISTING_SHA256"
        ):
            raise CodeIdentityError("UNREGISTERED_TECHNICAL_IDENTITY")
        _sha(_field(row, "original_git_blob_oid"), 40)
        _sha(_field(row, "original_source_sha256"), 64)
        pairs.append(pair)
    if len(pairs) != len(_TECHNICAL_PAIRS) or set(pairs) != _TECHNICAL_PAIRS:
        raise CodeIdentityError("INVALID_TECHNICAL_CATALOG")
    return rows


def technical_registered(commit: str, path: str) -> bool:
    if (commit, path) not in _TECHNICAL_PAIRS:
        return False
    _technical_records()
    return True


def _run(repo: Path, *args: str, data: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(
        GIT_NO_LAZY_FETCH="1",
        GIT_NO_REPLACE_OBJECTS="1",
        GIT_OPTIONAL_LOCKS="0",
        GIT_TERMINAL_PROMPT="0",
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_AUTHOR_NAME="SYNTHETIC_CODE_ONLY",
        GIT_AUTHOR_EMAIL="synthetic@example.invalid",
        GIT_COMMITTER_NAME="SYNTHETIC_CODE_ONLY",
        GIT_COMMITTER_EMAIL="synthetic@example.invalid",
        GIT_AUTHOR_DATE="2040-01-01T00:00:00+00:00",
        GIT_COMMITTER_DATE="2040-01-01T00:00:00+00:00",
    )
    return subprocess.run(
        [
            "git",
            "-c",
            "protocol.allow=never",
            "-c",
            "core.hooksPath=" + os.devnull,
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=repo,
        input=data,
        capture_output=True,
        env=env,
        check=False,
    )


def _git(repo: Path, *args: str, data: bytes | None = None) -> bytes:
    result = _run(repo, *args, data=data)
    if result.returncode:
        raise CodeIdentityError("CODE_GIT_OPERATION_FAILED")
    return result.stdout


def _type(repo: Path, oid: str) -> str | None:
    result = _run(repo, "cat-file", "-t", oid)
    return result.stdout.decode().strip() if result.returncode == 0 else None


def _blob_id(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def read_code(
    commit: str,
    path: str,
    *,
    repo: Path = ROOT,
    mode: Mode = Mode.CURRENT_HISTORY,
) -> bytes:
    _sha(commit, 40)
    _check_path(path)
    if not isinstance(mode, Mode):
        raise CodeIdentityError("INVALID_CODE_READ_MODE")
    if mode == Mode.CLEAN_GRAPH_REHEARSAL and _CONTROLLED.get(repo.resolve()) != "REHEARSAL":
        raise CodeIdentityError("OWNED_REHEARSAL_REQUIRED")
    entry = next((r for r in catalog() if r.commit == commit and r.path == path), None)
    if entry is None:
        raise CodeIdentityError("UNREGISTERED_CODE_IDENTITY")
    return _read_identity(entry, repo=repo, mode=mode)


def _read_identity(
    entry: Identity, *, repo: Path, mode: Mode, technical: bool = False, role: str = "SOURCE"
) -> bytes:
    from backend.app.core import rewritten_history

    commit, path = entry.commit, entry.path
    kind = _type(repo, commit)
    if mode == Mode.CURRENT_HISTORY:
        if role == "METADATA":
            try:
                commit = rewritten_history.resolve(repo, commit, role=role)
            except rewritten_history.HistoryLocationError as error:
                raise CodeIdentityError(str(error)) from error
        else:
            commit = historical_revision(commit, path, repo=repo)
        tree = _git(repo, "ls-tree", "-z", commit, "--", path).split(b"\0")
        records = [item.split(b"\t", 1) for item in tree if item]
        if len(records) != 1 or records[0][1].decode() != path:
            raise CodeIdentityError("CODE_PATH_UNAVAILABLE")
        metadata = records[0][0].decode().split()
        allowed = (["100644", "blob"],) if technical else (["100644", "blob"], ["100755", "blob"])
        if metadata[:2] not in allowed:
            raise CodeIdentityError("CODE_OBJECT_TYPE_MISMATCH")
        if metadata[2] != entry.blob:
            raise CodeIdentityError("CODE_PATH_BLOB_MISMATCH")
    elif kind is not None or (
        (mapped := rewritten_history.mapped_revision(commit)) is not None
        and _type(repo, mapped) is not None
    ):
        raise CodeIdentityError("REHEARSAL_OLD_COMMIT_PRESENT")
    if _type(repo, entry.blob) != "blob":
        raise CodeIdentityError("CODE_BLOB_UNAVAILABLE")
    raw = _git(repo, "cat-file", "blob", entry.blob)
    if _blob_id(raw) != entry.blob:
        raise CodeIdentityError("CODE_BLOB_IDENTITY_MISMATCH")
    if hashlib.sha256(raw).hexdigest() != entry.sha256:
        raise CodeIdentityError("ORIGINAL_SOURCE_SHA256_MISMATCH")
    return raw


def historical_revision(commit: str, path: str, *, repo: Path = ROOT) -> str:
    """Locate an exact approved source; fixture capabilities cannot be self-minted."""
    from backend.app.core import rewritten_history

    if _CONTROLLED.get(repo.resolve()) == "CURRENT_FIXTURE":
        revision = _CURRENT_REVISIONS.get(repo.resolve(), {}).get((commit, path))
        if revision is not None:
            return revision
    try:
        return rewritten_history.resolve(repo, commit)
    except rewritten_history.HistoryLocationError as error:
        raise CodeIdentityError(str(error)) from error


def read_compatibility_metadata(commit: str, path: str, *, repo: Path = ROOT) -> bytes | None:
    """Two exact technical records, each bound by an unchanged frozen Hash field."""
    from backend.app.core import rewritten_history

    row = rewritten_history.metadata_identity(commit, path)
    if row is None:
        return None
    authority: Any = json.loads((ROOT / row["authority_document"]).read_bytes())
    expected: Any = authority
    bound_commit: Any = authority
    for field in row["authority_hash_field"]:
        expected = expected[field]
    for field in row["authority_commit_field"]:
        bound_commit = bound_commit[field]
    if expected != row["sha256"] or bound_commit != commit:
        raise CodeIdentityError("ORIGINAL_EXPECTED_SHA256_CHANGED")
    # Reuse the exact existing Blob/type/SHA chain; no repository is relabelled.
    entry = Identity(commit, path, row["blob"], row["sha256"], "TECHNICAL_METADATA")
    return _read_identity(
        entry, repo=repo, mode=Mode.CURRENT_HISTORY, technical=True, role="METADATA"
    )


def read_technical(
    commit: str,
    path: str,
    *,
    repo: Path = ROOT,
    mode: Mode = Mode.CURRENT_HISTORY,
) -> bytes:
    """Read only three exact technical identities with existing independent Hashes."""
    _sha(commit, 40)
    _check_path(path, code=False)
    if (commit, path) not in _TECHNICAL_PAIRS:
        raise CodeIdentityError("UNREGISTERED_TECHNICAL_IDENTITY")
    if not isinstance(mode, Mode):
        raise CodeIdentityError("INVALID_CODE_READ_MODE")
    if mode == Mode.CLEAN_GRAPH_REHEARSAL and _CONTROLLED.get(repo.resolve()) != "REHEARSAL":
        raise CodeIdentityError("OWNED_REHEARSAL_REQUIRED")
    row = next(
        r
        for r in _technical_records()
        if (r["original_commit_sha"], r["repository_relative_path"]) == (commit, path)
    )
    authority = row.get("independent_authority")
    if not isinstance(authority, dict) or authority.get("kind") != "EXISTING_FROZEN_SHA256_FIELD":
        raise CodeIdentityError("INDEPENDENT_AUTHORITY_REQUIRED")
    document = authority.get("document")
    if not isinstance(document, str):
        raise CodeIdentityError("INDEPENDENT_AUTHORITY_REQUIRED")
    _check_path(document, code=False)
    if document not in {
        "docs/v0-18/s1/local-auth-runtime-r1.json",
        "docs/v0-18/evidence/s1-identity-and-grant-preflight-r1.json",
    } or authority.get("field") != ["source_evidence_sha256", path]:
        raise CodeIdentityError("UNAPPROVED_HASH_METADATA")
    value: object = json.loads((ROOT / document).read_bytes())
    for field in ("source_evidence_sha256", path):
        if not isinstance(value, dict):
            raise CodeIdentityError("INVALID_HASH_FIELD_REFERENCE")
        value = value.get(field)
    sha256 = _field(row, "original_source_sha256")
    if value != sha256 or authority.get("expected_sha256") != sha256:
        raise CodeIdentityError("ORIGINAL_EXPECTED_SHA256_CHANGED")
    entry = Identity(commit, path, _field(row, "original_git_blob_oid"), sha256, "TECHNICAL_FILE")
    return _read_identity(entry, repo=repo, mode=mode, technical=True)


def read_technical_history(commit: str, path: str, *, repo: Path = ROOT) -> bytes:
    # Only process-owned graphs may select Blob-only mode. Ordinary rewritten
    # history must satisfy the separate sealed exact-Commit locator contract.
    mode = (
        Mode.CLEAN_GRAPH_REHEARSAL
        if _CONTROLLED.get(repo.resolve()) == "REHEARSAL"
        else Mode.CURRENT_HISTORY
    )
    return read_technical(commit, path, repo=repo, mode=mode)


@contextmanager
def isolated_code_repository() -> Iterator[Path]:
    """Own a new standalone Git object database, never an existing repository."""
    with tempfile.TemporaryDirectory(prefix="TD01E_SYNTHETIC_CODE_ONLY_") as name:
        repo = Path(name).resolve()
        repo.chmod(0o700)
        _git(repo, "init", "-q", "--object-format=sha1")
        _CONTROLLED[repo] = "REHEARSAL"
        try:
            yield repo
        finally:
            _CONTROLLED.pop(repo, None)


@contextmanager
def current_code_fixture(commit: str, path: str, *, source: Path = ROOT) -> Iterator[Path]:
    """Seed only authorized code plus its resolved Commit/Tree METADATA.

    Replaces a full-history local fetch in the old test fixture. Unrelated
    referenced data Blobs and parent commits are never copied or downloaded.
    A rewritten source copies mapped metadata, never restoring an old Commit.
    This incomplete CURRENT_HISTORY fixture is not the clean graph rehearsal.
    """
    raw = read_code(commit, path, repo=source)
    revision = historical_revision(commit, path, repo=source)
    with isolated_code_repository() as repo:
        _CONTROLLED[repo] = "CURRENT_FIXTURE"
        commit_raw = _git(source, "cat-file", "commit", revision)
        tree = commit_raw.splitlines()[0].decode().removeprefix("tree ")
        _sha(tree, 40)
        for part in (*PurePosixPath(path).parts[:-1], None):
            tree_raw = _git(source, "cat-file", "tree", tree)
            assert (
                _git(repo, "hash-object", "-t", "tree", "-w", "--stdin", data=tree_raw)
                .decode()
                .strip()
                == tree
            )
            if part is not None:
                row = _git(source, "ls-tree", tree, "--", part).decode().split()
                if len(row) != 4 or row[1] != "tree":
                    raise CodeIdentityError("CODE_TREE_METADATA_UNAVAILABLE")
                tree = row[2]
        _git(repo, "hash-object", "-w", "--stdin", data=raw)
        assert (
            _git(repo, "hash-object", "-t", "commit", "-w", "--stdin", data=commit_raw)
            .decode()
            .strip()
            == revision
        )
        _CURRENT_REVISIONS[repo] = {(commit, path): revision}
        try:
            yield repo
        finally:
            _CURRENT_REVISIONS.pop(repo, None)


def _verify_independent_authorities() -> None:
    for row in _records():
        authority = row.get("independent_authority")
        if not isinstance(authority, dict):
            raise CodeIdentityError("INDEPENDENT_AUTHORITY_REQUIRED")
        document = authority.get("document")
        if not isinstance(document, str):
            raise CodeIdentityError("INDEPENDENT_AUTHORITY_REQUIRED")
        _check_path(document, code=False)
        if authority.get("kind") == "EXISTING_FROZEN_SHA256_FIELD":
            if not document.startswith(("docs/v0-17/", "docs/v0-18/")) or not document.endswith(
                ".json"
            ):
                raise CodeIdentityError("UNAPPROVED_HASH_METADATA")
            value: object = json.loads((ROOT / document).read_bytes())
            route = authority.get("field")
            if not isinstance(route, list):
                raise CodeIdentityError("INVALID_HASH_FIELD_REFERENCE")
            for field in route:
                if not isinstance(field, str) or not isinstance(value, dict):
                    raise CodeIdentityError("INVALID_HASH_FIELD_REFERENCE")
                value = value.get(field)
            if value != row["original_source_sha256"] or value != authority.get("expected_sha256"):
                raise CodeIdentityError("ORIGINAL_EXPECTED_SHA256_CHANGED")
        elif authority.get("kind") == "EXISTING_TEST_GIT_BLOB_PIN":
            if document != "backend/tests/td03g_historical_source.py":
                raise CodeIdentityError("UNAPPROVED_BLOB_AUTHORITY")
            nodes = ast.parse((ROOT / document).read_bytes()).body
            assignments = {
                n.targets[0].id: n.value
                for n in nodes
                if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
            }
            constants = {k: ast.literal_eval(assignments[k]) for k in ("OBTAIN", "QUERY")}
            literal = assignments["EXPECTED_BLOBS"]
            if not isinstance(literal, ast.Dict):
                raise CodeIdentityError("INVALID_BLOB_AUTHORITY")
            pins = {}
            for key, item in zip(literal.keys, literal.values, strict=True):
                if key is None:
                    raise CodeIdentityError("INVALID_BLOB_AUTHORITY")
                pins[constants[key.id] if isinstance(key, ast.Name) else ast.literal_eval(key)] = (
                    ast.literal_eval(item)
                )
            pins.update(
                {
                    "backend/tests/s3_daily_rowset/" + name: oid
                    for name, oid in ast.literal_eval(assignments["_TRANSITIVE_TEST_BLOBS"])
                }
            )
            if (
                pins.get(row["repository_relative_path"]) != row["original_git_blob_oid"]
                or authority.get("expected_git_blob_oid") != row["original_git_blob_oid"]
            ):
                raise CodeIdentityError("ORIGINAL_EXPECTED_BLOB_CHANGED")
        else:
            raise CodeIdentityError("INDEPENDENT_AUTHORITY_REQUIRED")


def _result(mode: Mode) -> dict[str, object]:
    value: dict[str, object] = {
        "mode": mode.value,
        "catalog_sha256": CATALOG_SHA256,
        "identity_count": len(catalog()),
        "original_code_bytes_unchanged": True,
        "original_expected_sha256_unchanged": True,
        "verified_git_blob_identity": True,
        "arbitrary_fallback_allowed": False,
        "real_history_rewrite_ready": False,
        "data_or_publication_authority_granted": False,
    }
    return value


def verify_current(*, repo: Path = ROOT) -> dict[str, object]:
    _verify_independent_authorities()
    for entry in catalog():
        read_code(entry.commit, entry.path, repo=repo)
    value = _result(Mode.CURRENT_HISTORY)
    value["result_sha256"] = hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
    return value


def rehearse(*, source: Path = ROOT) -> dict[str, object]:
    _verify_independent_authorities()
    entries = catalog()
    verified = [(row, read_code(row.commit, row.path, repo=source)) for row in entries]
    with isolated_code_repository() as repo:
        for row, raw in verified:
            oid = _git(repo, "hash-object", "-w", "--stdin", data=raw).decode().strip()
            if oid != row.blob:
                raise CodeIdentityError("REHEARSAL_CODE_BLOB_MISMATCH")
            archive = "code/" + row.commit + "/" + row.path
            _git(repo, "update-index", "--add", "--cacheinfo", "100644," + oid + "," + archive)
        tree = _git(repo, "write-tree").decode().strip()
        head = (
            _git(repo, "commit-tree", tree, data=b"SYNTHETIC_CODE_ONLY_CLEAN_GRAPH_REHEARSAL\n")
            .decode()
            .strip()
        )
        _git(repo, "update-ref", "refs/heads/synthetic-code-only", head)
        assert not (repo / ".git/objects/info/alternates").exists()
        assert _git(repo, "remote").strip() == b""
        objects = _git(repo, "ls-tree", "-r", tree).decode().splitlines()
        if {line.split()[2] for line in objects} != {row.blob for row in entries}:
            raise CodeIdentityError("UNREGISTERED_REHEARSAL_OBJECT")
        # Inspect object TYPES/IDs only, including dangling objects. The clean
        # rehearsal must not retain an old commit or any unrelated data Blob.
        for line in (
            _git(
                repo, "cat-file", "--batch-all-objects", "--batch-check=%(objectname) %(objecttype)"
            )
            .decode()
            .splitlines()
        ):
            oid, kind = line.split()
            if (
                (kind == "blob" and oid not in {row.blob for row in entries})
                or (kind == "commit" and oid != head)
                or kind not in {"blob", "tree", "commit"}
            ):
                raise CodeIdentityError("UNREGISTERED_REHEARSAL_OBJECT")
        for row in entries:
            read_code(row.commit, row.path, repo=repo, mode=Mode.CLEAN_GRAPH_REHEARSAL)
        value = _result(Mode.CLEAN_GRAPH_REHEARSAL)
        value.update(
            old_commits_present=0,
            registered_code_blobs_only=True,
            synthetic_git_tree=tree,
            synthetic_git_commit=head,
        )
        value["result_sha256"] = hashlib.sha256(
            json.dumps(value, sort_keys=True).encode()
        ).hexdigest()
        return value


def preflight(*, repo: Path = ROOT) -> dict[str, object]:
    """The unchanged original source identities, not old-Commit existence."""
    _verify_independent_authorities()
    commit = "320f2046e3105b1b55da9cb037892571110b584a"
    paths = (
        "backend/app/main.py",
        "backend/app/api/forecast_intelligence_read.py",
        "backend/app/api/forecast_intelligence_decision.py",
    )
    for path in paths:
        read_code(commit, path, repo=repo)
    return {
        "status": "PASS",
        "original_commit": commit,
        "verified_source_identities": list(paths),
        "original_blob_and_sha256_verified": True,
        "expected_hashes_changed": False,
        "data_or_publication_authority_granted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("verify", "rehearse", "read", "preflight"))
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--commit")
    parser.add_argument("--path")
    args = parser.parse_args()
    try:
        if args.operation == "read":
            if args.commit is None or args.path is None:
                raise CodeIdentityError("EXPLICIT_CODE_IDENTITY_REQUIRED")
            sys.stdout.buffer.write(read_code(args.commit, args.path, repo=args.repo))
        elif args.operation == "preflight":
            print(json.dumps(preflight(repo=args.repo), sort_keys=True, indent=2))
        else:
            result = (
                verify_current(repo=args.repo)
                if args.operation == "verify"
                else rehearse(source=args.repo)
            )
            print(json.dumps(result, sort_keys=True, indent=2))
        return 0
    except (CodeIdentityError, OSError, ValueError, KeyError):
        print("HISTORICAL_CODE_IDENTITY_VERIFICATION_FAILED", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
