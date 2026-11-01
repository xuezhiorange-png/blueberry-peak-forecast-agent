"""Read-only sealed public-core check. Labels and caller hashes grant nothing."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path, PurePosixPath

APPROVED_MANIFEST_SHA256 = "__MANIFEST_SEAL__"
MANIFEST = "PUBLIC-CORE-MANIFEST.json"
ROOT = Path(__file__).resolve().parents[1]
BLOCKED = frozenset(
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


class PublicCoreViolation(AssertionError):
    """Fail closed; never include file contents or private paths."""


def git(root: Path, *args: str) -> bytes:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(
        GIT_NO_LAZY_FETCH="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_NOSYSTEM="1",
        GIT_OPTIONAL_LOCKS="0",
        GIT_TERMINAL_PROMPT="0",
    )
    run = subprocess.run(
        ["git", "-c", "protocol.allow=never", *args],
        cwd=root,
        env=env,
        capture_output=True,
        check=False,
    )
    if run.returncode:
        raise PublicCoreViolation("PUBLIC_GIT_METADATA_UNAVAILABLE")
    return run.stdout


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def verify(root: Path = ROOT) -> dict[str, object]:
    gitdir = root / ".git"
    if not gitdir.is_dir() or gitdir.is_symlink() or (gitdir / "objects").is_symlink():
        raise PublicCoreViolation("STANDALONE_OBJECT_DATABASE_REQUIRED")
    for name in (
        "objects/info/alternates",
        "objects/info/http-alternates",
        "commondir",
        "shallow",
        "info/grafts",
    ):
        if (gitdir / name).exists() or (gitdir / name).is_symlink():
            raise PublicCoreViolation("EXTERNAL_HISTORY_NOT_ALLOWED")
    names = git(root, "config", "--local", "--name-only", "--list").decode().splitlines()
    permitted = {
        "core.repositoryformatversion",
        "core.filemode",
        "core.bare",
        "core.logallrefupdates",
        "core.ignorecase",
        "core.precomposeunicode",
        "gc.auto",
        "remote.origin.url",
        "remote.origin.fetch",
    }
    if set(names) - permitted:
        raise PublicCoreViolation("UNREVIEWED_GIT_CONFIG")
    remotes = git(root, "remote").decode().splitlines()
    if remotes not in ([], ["origin"]):
        raise PublicCoreViolation("UNREVIEWED_REMOTE")
    if remotes:
        url = git(root, "remote", "get-url", "origin").decode().strip()
        if not re.fullmatch(
            r"https://github[.]com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:[.]git)?", url
        ):
            raise PublicCoreViolation("UNREVIEWED_REMOTE")
        if url.removesuffix(".git").endswith("/xuezhiorange-png/blueberry-peak-forecast-agent"):
            raise PublicCoreViolation("ORIGINAL_REMOTE_NOT_ALLOWED")
    refs = git(root, "for-each-ref", "--format=%(refname) %(objectname)").decode().splitlines()
    allowed_refs = {"refs/heads/main", "refs/remotes/origin/main", "refs/remotes/origin/HEAD"}
    if not refs or any(line.split()[0] not in allowed_refs for line in refs):
        raise PublicCoreViolation("UNREVIEWED_REF")
    raw_manifest = (root / MANIFEST).read_bytes()
    if digest(raw_manifest) != APPROVED_MANIFEST_SHA256:
        raise PublicCoreViolation("PUBLIC_MANIFEST_SEAL_MISMATCH")
    manifest = json.loads(raw_manifest)
    expected = {r["path"]: r for r in manifest["files"]}
    if len(expected) != len(manifest["files"]):
        raise PublicCoreViolation("DUPLICATE_ALLOWLIST_PATH")
    for name in expected:
        p = PurePosixPath(name)
        if p.is_absolute() or str(p) != name or ".." in p.parts or ".git" in p.parts:
            raise PublicCoreViolation("UNSAFE_ALLOWLIST_PATH")
    tree = {}
    for row in git(root, "ls-tree", "-r", "-z", "HEAD").split(b"\0"):
        if row:
            meta, raw_path = row.split(b"\t", 1)
            mode, kind, oid = meta.decode().split()
            path = raw_path.decode()
            if oid in BLOCKED:
                raise PublicCoreViolation("BLOCKED_BUSINESS_BLOB")
            if mode != "100644" or kind != "blob" or path not in {*expected, MANIFEST}:
                raise PublicCoreViolation("UNKNOWN_PUBLIC_FILE")
            if (
                path not in {MANIFEST, "tools/verify_public_core.py"}
                and oid != expected[path]["git_blob_oid"]
            ):
                raise PublicCoreViolation("PUBLIC_HEAD_IDENTITY_MISMATCH")
            tree[path] = oid
    if set(tree) != {*expected, MANIFEST} or tree[MANIFEST] != blob(raw_manifest):
        raise PublicCoreViolation("PUBLIC_TREE_MISMATCH")
    for name, row in expected.items():
        raw = (root / name).read_bytes()
        if (root / name).is_symlink() or tree[name] != blob(raw):
            raise PublicCoreViolation("SOURCE_WORKTREE_CHANGED")
        if name == "tools/verify_public_core.py":
            old = ('APPROVED_MANIFEST_SHA256 = "' + APPROVED_MANIFEST_SHA256 + '"').encode()
            new = b'APPROVED_MANIFEST_SHA256 = "__MANIFEST_SEAL__"'
            if raw.count(old) != 1:
                raise PublicCoreViolation("GUARD_TEMPLATE_CHANGED")
            raw = raw.replace(old, new, 1)
        if digest(raw) != row["sha256"]:
            raise PublicCoreViolation("PUBLIC_FILE_IDENTITY_MISMATCH")
    working = {
        str(p.relative_to(root))
        for p in root.rglob("*")
        if p.is_file() and ".git" not in p.relative_to(root).parts
    }
    if working != {*expected, MANIFEST}:
        raise PublicCoreViolation("UNKNOWN_WORKING_FILE")
    objects = dict(
        line.split()
        for line in git(
            root, "cat-file", "--batch-all-objects", "--batch-check=%(objectname) %(objecttype)"
        )
        .decode()
        .splitlines()
    )
    if BLOCKED.intersection(objects):
        raise PublicCoreViolation("BLOCKED_BUSINESS_BLOB")
    commits = [oid for oid, kind in objects.items() if kind == "commit"]
    if len(commits) != 1 or any(
        line.startswith(b"parent ")
        for line in git(root, "cat-file", "commit", commits[0]).splitlines()
    ):
        raise PublicCoreViolation("ROOT_REHEARSAL_HISTORY_ONLY")
    if any(line.split()[1] != commits[0] for line in refs):
        raise PublicCoreViolation("UNREVIEWED_REF_TARGET")
    reachable = {
        line.split()[0]
        for line in git(root, "rev-list", "--all", "--objects").decode().splitlines()
    }
    if set(objects) != reachable or {oid for oid, kind in objects.items() if kind == "blob"} != set(
        tree.values()
    ):
        raise PublicCoreViolation("UNKNOWN_OR_DANGLING_OBJECT")
    git(root, "fsck", "--full", "--strict", "--no-reflogs")
    return {
        "status": "PASS",
        "contract": "TD01G_PUBLIC_CORE_V1",
        "file_count": len(tree),
        "object_count": len(objects),
        "commit_count": 1,
        "parent_count": 0,
        "remote_count": len(remotes),
        "tag_count": 0,
        "alternates_present": False,
        "known_business_blobs_present": False,
        "original_history_copied": False,
        "publication_authorized": False,
    }


if __name__ == "__main__":
    print(json.dumps(verify(), sort_keys=True))
