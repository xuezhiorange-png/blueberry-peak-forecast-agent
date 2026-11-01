"""Read-only TD01I graph gate; proposed Git content is never review authority.

The only implemented independent-review transport is an external, caller-pinned
SYNTHETIC rehearsal document. Real GitHub approval is deliberately unconfigured.
No network, source execution, publication, history editing or database access.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

V1_ROOT = "04457546f5577d4e44effb808154a6aa08b45846"
V1_MANIFEST_SHA256 = "4fa783f4bbccab468f7de6ac8a8b4cd2807503f206e1ea510e435ed296f82cc0"
MANIFEST = "PUBLIC-CORE-MANIFEST.json"
AUTHORITY_KIND = "TD01I_INDEPENDENT_SYNTHETIC_REVIEW_R1"
# Metadata only: never read, recover or manufacture these real source objects.
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
_POLICY = (
    MANIFEST,
    "PUBLIC-CORE-V2-EXECUTORS.json",
    "tools/",
    ".github/",
    ".gitignore",
    ".gitattributes",
)
_DEPENDENCY = ("pyproject.toml", "requirements-direct.txt", "requirements-lock.txt")
_ROOT_DATA = "docs/tech-debt/td01c-synthetic-example/"


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + "\n").encode()


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def blob_id(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


class Violation(Exception):
    """Only stable reason codes; subprocess stderr is never public output."""


def oid(value: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise Violation("INVALID_OBJECT_ID")
    return value


def safe_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or str(path) != value
        or path.is_absolute()
        or any(p in {".", "..", ".git"} or p.startswith("-") for p in path.parts)
        or any(c in value for c in "\\:\x00\r\n\t")
        or any(ord(c) < 32 or ord(c) == 127 for c in value)
    ):
        raise Violation("UNSAFE_PATH")
    return value


@dataclass(frozen=True)
class FileGrant:
    path: str
    blob: str
    sha256: str
    kind: str


@dataclass(frozen=True)
class Review:
    commit: str
    tree: str
    parents: tuple[str, ...]
    files: tuple[FileGrant, ...]
    deletions: tuple[str, ...] = ()
    authority_id: str = AUTHORITY_KIND


@dataclass(frozen=True)
class SyntheticBundle:
    producer_root: str
    producer_closure_sha256: str
    seed: int
    files: tuple[FileGrant, ...]


@dataclass(frozen=True)
class Authority:
    scope_base: str
    reviews: tuple[Review, ...] = ()
    bundles: tuple[SyntheticBundle, ...] = ()
    kind: str = AUTHORITY_KIND


@dataclass(frozen=True)
class Context:
    base: str
    head: str
    checkout: str
    refs: tuple[tuple[str, str], ...]
    origin: str | None = None
    test_merge: str | None = None


class Git:
    def __init__(self, root: Path):
        self.root = root

    def read(self, *arguments: str) -> bytes:
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env.update(
            GIT_NO_LAZY_FETCH="1",
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_CONFIG_NOSYSTEM="1",
            GIT_OPTIONAL_LOCKS="0",
            GIT_TERMINAL_PROMPT="0",
        )
        result = subprocess.run(
            [
                "git",
                "--no-replace-objects",
                "--literal-pathspecs",
                "-c",
                "protocol.allow=never",
                "-c",
                "core.hooksPath=" + os.devnull,
                *arguments,
            ],
            cwd=self.root,
            env=env,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            raise Violation("GIT_METADATA_OR_OBJECT_UNAVAILABLE")
        return result.stdout

    def text(self, *arguments: str) -> str:
        return self.read(*arguments).decode("utf-8").strip()

    def tree(self, commit: str) -> dict[str, str]:
        rows = {}
        for raw in self.read("ls-tree", "-r", "-z", oid(commit)).split(b"\0"):
            if not raw:
                continue
            meta, name = raw.split(b"\t", 1)
            mode, kind, identity = meta.decode().split()
            if identity in BLOCKED_BLOBS:
                raise Violation("BLOCKED_BUSINESS_BLOB")
            path = safe_path(name.decode("utf-8"))
            if mode != "100644" or kind != "blob":
                raise Violation("SYMLINK_SUBMODULE_OR_SPECIAL_MODE")
            if path in rows:
                raise Violation("DUPLICATE_TREE_PATH")
            rows[path] = oid(identity)
        return rows


def producer_closure(files: dict[str, FileGrant]) -> str:
    return digest(
        canonical({p: f.sha256 for p, f in sorted(files.items()) if p.startswith("backend/")})
    )


def _repository(git: Git, context: Context) -> None:
    root = git.root
    gd = root / ".git"
    if root.is_symlink() or not gd.is_dir() or gd.is_symlink():
        raise Violation("STANDALONE_OBJECT_DATABASE_REQUIRED")
    for name in (
        "commondir",
        "shallow",
        "info/grafts",
        "objects/info/alternates",
        "objects/info/http-alternates",
        "modules",
        "worktrees",
        "config.worktree",
        "info/attributes",
    ):
        p = gd / name
        if p.exists() or p.is_symlink():
            raise Violation("EXTERNAL_HISTORY_OR_SHALLOW")
    if any(p.is_symlink() for p in gd.rglob("*")):
        raise Violation("SYMLINKED_GIT_STORAGE")
    allowed_config = {
        "core.repositoryformatversion",
        "core.filemode",
        "core.bare",
        "core.logallrefupdates",
        "core.ignorecase",
        "core.precomposeunicode",
        "gc.auto",
        "remote.origin.url",
        "remote.origin.fetch",
        "remote.origin.tagopt",
    }
    # Inspect this bounded local metadata BEFORE asking Git to load a config;
    # an include/includeIf must never make Git open an external private file.
    config_file = gd / "config"
    if not stat.S_ISREG(config_file.stat().st_mode) or config_file.stat().st_size > 65536:
        raise Violation("UNREVIEWED_GIT_CONFIGURATION")
    section = ""
    for line in config_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("["):
            sections = {"[core]": "core", "[gc]": "gc", '[remote "origin"]': "remote.origin"}
            if line not in sections:
                raise Violation("UNREVIEWED_GIT_CONFIGURATION")
            section = sections[line]
        else:
            match = re.fullmatch(r"([A-Za-z][A-Za-z0-9]*)\s*=.*", line)
            if (
                match is None
                or line.endswith("\\")
                or section + "." + match[1].lower() not in allowed_config
            ):
                raise Violation("UNREVIEWED_GIT_CONFIGURATION")
    names = git.text("config", "--local", "--no-includes", "--name-only", "--list").splitlines()
    if set(names) - allowed_config:
        raise Violation("UNREVIEWED_GIT_CONFIGURATION")
    if git.text("rev-parse", "--show-object-format") != "sha1":
        raise Violation("UNSUPPORTED_OBJECT_FORMAT")
    remotes = git.text("remote").splitlines()
    if context.origin is None:
        if remotes:
            raise Violation("UNTRUSTED_ORIGIN")
    else:
        if (
            remotes != ["origin"]
            or not re.fullmatch(
                r"https://github[.]com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:[.]git)?", context.origin
            )
            or context.origin.removesuffix(".git").endswith(
                "/xuezhiorange-png/blueberry-peak-forecast-agent"
            )
            or git.text("remote", "get-url", "origin") != context.origin
        ):
            raise Violation("UNTRUSTED_ORIGIN")
    expected = dict(context.refs)
    if len(expected) != len(context.refs) or not expected:
        raise Violation("INVALID_REF_CONTEXT")
    for ref, target in expected.items():
        if not re.fullmatch(r"refs/(?:heads|remotes/origin)/[A-Za-z0-9_./-]+", ref) or ".." in ref:
            raise Violation("UNTRUSTED_REF_OR_TAG")
        oid(target)
    actual = dict(
        row.split()
        for row in git.text("for-each-ref", "--format=%(refname) %(objectname)").splitlines()
    )
    if actual != expected:
        raise Violation("UNTRUSTED_REF_OR_TAG")
    if git.text("rev-parse", "--verify", "HEAD") != context.checkout:
        raise Violation("CHECKOUT_IDENTITY_MISMATCH")
    if context.checkout not in {context.base, context.head, context.test_merge}:
        raise Violation("CHECKOUT_ROLE_MISMATCH")
    # Unknown loose/pack files cannot hide outside Git's object enumerator.
    for file in (gd / "objects").rglob("*"):
        if not file.is_file():
            continue
        rel = file.relative_to(gd / "objects").as_posix()
        if not (
            re.fullmatch(r"[0-9a-f]{2}/[0-9a-f]{38}", rel)
            or re.fullmatch(r"pack/pack-[0-9a-f]{40}[.](?:pack|idx|rev|bitmap)", rel)
            or rel in {"info/packs", "info/commit-graph", "pack/multi-pack-index"}
        ):
            raise Violation("UNKNOWN_OBJECT_STORAGE_FILE")


def _bootstrap(git: Git) -> dict[str, FileGrant]:
    tree = git.tree(V1_ROOT)
    if len(tree) != 28 or MANIFEST not in tree:
        raise Violation("V1_BOOTSTRAP_TREE_MISMATCH")
    raw = git.read("cat-file", "blob", tree[MANIFEST])
    if digest(raw) != V1_MANIFEST_SHA256:
        raise Violation("V1_MANIFEST_SEAL_MISMATCH")
    payload = json.loads(raw)
    expected = {row["path"]: row for row in payload["files"]}
    if len(expected) != 27 or set(tree) != {*expected, MANIFEST}:
        raise Violation("V1_BOOTSTRAP_TREE_MISMATCH")
    result = {MANIFEST: FileGrant(MANIFEST, tree[MANIFEST], digest(raw), "POLICY")}
    for path, row in sorted(expected.items()):
        safe_path(path)
        body = git.read("cat-file", "blob", tree[path])
        normalized = body
        if path == "tools/verify_public_core.py":
            old = f'APPROVED_MANIFEST_SHA256 = "{V1_MANIFEST_SHA256}"'.encode()
            if body.count(old) != 1:
                raise Violation("V1_BOOTSTRAP_GUARD_MISMATCH")
            normalized = body.replace(old, b'APPROVED_MANIFEST_SHA256 = "__MANIFEST_SEAL__"', 1)
        elif tree[path] != row["git_blob_oid"]:
            raise Violation("V1_BOOTSTRAP_BLOB_MISMATCH")
        if digest(normalized) != row["sha256"] or blob_id(body) != tree[path]:
            raise Violation("V1_BOOTSTRAP_SOURCE_MISMATCH")
        result[path] = FileGrant(path, tree[path], digest(body), "FROZEN_V1")
    return result


@dataclass
class Audit:
    context: Context
    issues: list[dict[str, str]] = field(default_factory=list)
    commits: list[dict[str, object]] = field(default_factory=list)
    diff: list[dict[str, object]] = field(default_factory=list)
    objects: dict[str, str] = field(default_factory=dict)
    merge_base: str | None = None
    proposed_diff: list[dict[str, object]] = field(default_factory=list)
    authority_kind: str = "UNCONFIGURED"

    def issue(self, code: str, *, path: str = "", identity: str = "", review: bool = False) -> None:
        row = {"code": code, "severity": "REVIEW_REQUIRED" if review else "BLOCKED"}
        if path:
            row["path"] = safe_path(path)
        if identity:
            row["object"] = oid(identity)
        if row not in self.issues:
            self.issues.append(row)

    def report(self) -> dict[str, object]:
        status = (
            "BLOCKED"
            if any(r["severity"] == "BLOCKED" for r in self.issues)
            else "REVIEW_REQUIRED"
            if self.issues
            else "PASS"
        )
        result: dict[str, object] = {
            "schema": "TD01I_PUBLIC_CORE_V2_R1",
            "status": status,
            "trusted_root": V1_ROOT,
            "trusted_base": self.context.base,
            "proposed_head": self.context.head,
            "checkout": self.context.checkout,
            "test_merge": self.context.test_merge,
            "merge_base": self.merge_base,
            "proposed_diff": self.proposed_diff,
            "independent_review_authority": self.authority_kind,
            "reasons": sorted(
                self.issues,
                key=lambda r: (r["severity"], r["code"], r.get("path", ""), r.get("object", "")),
            ),
            "commits": sorted(self.commits, key=lambda r: str(r["commit"])),
            "diff": sorted(
                self.diff, key=lambda r: (str(r["commit"]), str(r["parent"]), str(r["path"]))
            ),
            "objects": [{"oid": k, "type": v} for k, v in sorted(self.objects.items())],
            "commit_count": len(self.commits),
            "object_count": len(self.objects),
            "real_remote_review_authority": "UNVERIFIED",
            "publication_authorized": False,
            "real_forecast_validated": False,
            "strict_real_pit_validated": False,
            "production_model_admitted": False,
        }
        result["result_sha256"] = digest(canonical(result))
        return result


def _forbidden(path: str) -> bool:
    return (
        path.startswith(("data/", "configs/", "docs/v0-", "sources/"))
        or any(
            part.lower() in {"source_002", "factory_aliases.yaml", "base_registry_s1.json"}
            for part in PurePosixPath(path).parts
        )
        or PurePosixPath(path).suffix.lower() in {".xls", ".gz", ".zip", ".7z", ".parquet", ".dump"}
    )


def _python(raw: bytes, path: str, tree: dict[str, str]) -> None:
    if (
        len(raw) > 1024 * 1024
        or b"\0" in raw
        or raw.startswith(b"version https://git-lfs.github.com/spec/")
    ):
        raise Violation("BINARY_OR_LFS_POINTER")
    try:
        parsed = ast.parse(raw.decode("utf-8"))
    except (ValueError, SyntaxError, UnicodeError) as error:
        raise Violation("NON_CODE_PAYLOAD") from error
    for node in ast.walk(parsed):
        names = (
            [alias.name for alias in node.names]
            if isinstance(node, ast.Import)
            else [node.module]
            if isinstance(node, ast.ImportFrom) and node.module
            else []
        )
        if isinstance(node, ast.ImportFrom) and node.level:
            raise Violation("UNRESOLVED_RELATIVE_IMPORT")
        for name in names:
            top = name.split(".")[0]
            if top not in {
                *sys.stdlib_module_names,
                "backend",
                "tools",
                "openpyxl",
                "xlrd",
                "pytest",
            }:
                raise Violation("UNREGISTERED_DEPENDENCY")
            if top in {"backend", "tools"}:
                local = name.replace(".", "/")
                if local + ".py" not in tree and local + "/__init__.py" not in tree:
                    raise Violation("UNRESOLVED_LOCAL_IMPORT")


def _changed(tree: dict[str, str], before: dict[str, str]) -> dict[str, str | None]:
    return {
        p: tree.get(p) for p in sorted(tree.keys() | before.keys()) if tree.get(p) != before.get(p)
    }


def _review_files(
    git: Git,
    audit: Audit,
    commit: str,
    tree: dict[str, str],
    before: dict[str, str],
    review: Review | None,
    bundles: tuple[SyntheticBundle, ...],
    root: dict[str, FileGrant],
) -> None:
    changes = _changed(tree, before)
    grants = {f.path: f for f in review.files} if review else {}
    if review and (
        len(grants) != len(review.files)
        or set(grants) != {p for p, value in changes.items() if value is not None}
        or set(review.deletions) != {p for p, value in changes.items() if value is None}
    ):
        raise Violation("REVIEW_CHANGESET_MISMATCH")
    synthetic = {}
    for bundle in bundles:
        names = {PurePosixPath(f.path).name for f in bundle.files}
        expected_names = {PurePosixPath(p).name for p in root if p.startswith(_ROOT_DATA)}
        if (
            bundle.producer_root != V1_ROOT
            or bundle.producer_closure_sha256 != producer_closure(root)
            or type(bundle.seed) is not int
            or not 0 <= bundle.seed < 2**31
            or names != expected_names
            or len(bundle.files) != len(expected_names)
        ):
            raise Violation("SYNTHETIC_PRODUCER_OR_BUNDLE_MISMATCH")
        if any(f.kind != "SYNTHETIC" for f in bundle.files):
            raise Violation("SYNTHETIC_PRODUCER_OR_BUNDLE_MISMATCH")
        for f in bundle.files:
            if f.path in synthetic:
                raise Violation("DUPLICATE_SYNTHETIC_IDENTITY")
            synthetic[f.path] = f
        if all(tree.get(f.path) == f.blob for f in bundle.files):
            manifest = next(
                f for f in bundle.files if f.path.endswith("/SYNTHETIC_ONLY-manifest.json")
            )
            body = git.read("cat-file", "blob", manifest.blob)
            if digest(body) != manifest.sha256:
                raise Violation("SYNTHETIC_FULL_BYTE_BINDING_MISMATCH")
            declaration = _dict(json.loads(body))
            expected_exports = {
                PurePosixPath(f.path).name: f.sha256 for f in bundle.files if f != manifest
            }
            if (
                declaration.get("seed") != bundle.seed
                or declaration.get("data_class") != "SYNTHETIC_ONLY"
                or declaration.get("source_identity") != "TD01C_INDEPENDENT_GENERATOR_V1"
                or declaration.get("formal_source_admitted") is not False
                or declaration.get("exports_sha256") != expected_exports
            ):
                raise Violation("SYNTHETIC_PRODUCER_OR_BUNDLE_MISMATCH")
    for path, identity in changes.items():
        safe_path(path)
        if identity is None:
            if review is None:
                audit.issue("DELETION_REVIEW_REQUIRED", path=path, review=True)
            continue
        if identity in BLOCKED_BLOBS:
            raise Violation("BLOCKED_BUSINESS_BLOB")
        if _forbidden(path):
            audit.issue("UNREGISTERED_DATA_OR_BINARY", path=path, identity=identity)
            continue
        grant = grants.get(path)
        if path in _DEPENDENCY and root.get(path, FileGrant("", "", "", "")).blob != identity:
            # R1 preserves the original locked environment. A new lock closure
            # needs an independently versioned installation contract, not a label.
            audit.issue(
                "DEPENDENCY_CLOSURE_REVIEW_REQUIRED", path=path, identity=identity, review=True
            )
            continue
        if path.startswith(_POLICY) or path in _POLICY:
            if grant is None or grant.kind != "POLICY":
                audit.issue("UNTRUSTED_POLICY_CHANGE", path=path, identity=identity)
                continue
        elif path in synthetic:
            if grant != synthetic[path] or any(
                tree.get(f.path) != f.blob
                for b in bundles
                if any(x.path == path for x in b.files)
                for f in b.files
            ):
                audit.issue("SYNTHETIC_FULL_BYTE_BINDING_MISMATCH", path=path, identity=identity)
                continue
        elif path.endswith(".py"):
            if grant is not None and grant.kind != "CODE":
                raise Violation("REVIEW_CLASS_MISMATCH")
        elif path.startswith("schemas/") and path.endswith(".json"):
            if grant is None:
                audit.issue("SCHEMA_REVIEW_REQUIRED", path=path, identity=identity, review=True)
                continue
            if grant.kind != "SCHEMA":
                raise Violation("REVIEW_CLASS_MISMATCH")
        elif path.endswith(".md"):
            if grant is not None and grant.kind != "PUBLIC_TEXT":
                raise Violation("REVIEW_CLASS_MISMATCH")
        else:
            audit.issue("UNREGISTERED_DATA_OR_BINARY", path=path, identity=identity)
            continue
        if grant and (grant.blob != identity or not re.fullmatch(r"[0-9a-f]{64}", grant.sha256)):
            raise Violation("REVIEW_IDENTITY_MISMATCH")
        raw = git.read("cat-file", "blob", identity)
        if blob_id(raw) != identity or grant and digest(raw) != grant.sha256:
            raise Violation("REVIEW_IDENTITY_MISMATCH")
        if raw.startswith(b"version https://git-lfs.github.com/spec/"):
            raise Violation("BINARY_OR_LFS_POINTER")
        if path.endswith(".py"):
            _python(raw, path, tree)
        elif path not in synthetic:
            try:
                raw.decode("utf-8")
            except UnicodeError as error:
                raise Violation("UNREGISTERED_DATA_OR_BINARY") from error
            if path.startswith("schemas/") and path.endswith(".json"):
                _dict(json.loads(raw))
        if grant is None:
            audit.issue("FILE_REVIEW_REQUIRED", path=path, identity=identity, review=True)


def _working_tree(git: Git, context: Context, tree: dict[str, str]) -> None:
    seen = set()
    for folder, directories, files in os.walk(git.root, followlinks=False):
        if Path(folder) == git.root:
            directories[:] = [p for p in directories if p != ".git"]
        for name in [*directories, *files]:
            path = Path(folder) / name
            if path.is_symlink():
                raise Violation("SYMLINK_WORKTREE")
        for name in files:
            path = Path(folder) / name
            relative = safe_path(path.relative_to(git.root).as_posix())
            if (
                not stat.S_ISREG(path.stat().st_mode)
                or path.stat().st_mode & 0o111
                or relative not in tree
            ):
                raise Violation("UNKNOWN_WORKTREE_FILE")
            if blob_id(path.read_bytes()) != tree[relative]:
                raise Violation("WORKTREE_IDENTITY_MISMATCH")
            seen.add(relative)
    if seen != set(tree):
        raise Violation("INCOMPLETE_WORKTREE")


def verify(repo: Path, context: Context, authority: Authority | None = None) -> dict[str, object]:
    audit = Audit(context)
    try:
        _verify(Git(repo), audit, authority)
    except (Violation, UnicodeError, ValueError, KeyError, OSError) as error:
        audit.issue(str(error) if isinstance(error, Violation) else "INVALID_INPUT_OR_OBJECT")
    return audit.report()


def _verify(git: Git, audit: Audit, authority: Authority | None) -> None:
    context = audit.context
    for value in (context.base, context.head, context.checkout):
        oid(value)
    if context.test_merge:
        oid(context.test_merge)
    _repository(git, context)
    inventory = [
        row.split()
        for row in git.text(
            "cat-file",
            "--batch-all-objects",
            "--batch-check=%(objectname) %(objecttype) %(objectsize)",
        ).splitlines()
    ]
    audit.objects = {identity: kind for identity, kind, _ in inventory}
    if BLOCKED_BLOBS.intersection(audit.objects):
        raise Violation("BLOCKED_BUSINESS_BLOB")
    if len(inventory) > 20000 or any(
        kind == "blob" and int(size) > 2 * 1024 * 1024 for _, kind, size in inventory
    ):
        raise Violation("REHEARSAL_OBJECT_BUDGET_EXCEEDED")
    tips = [context.base, context.head, *([context.test_merge] if context.test_merge else [])]
    for target in [*tips, *dict(context.refs).values()]:
        if audit.objects.get(target) != "commit":
            raise Violation("MISSING_OR_NONCOMMIT_TIP")
    # Tree metadata precedes any Blob read, including metadata-only blocked OIDs.
    commits = [k for k, v in audit.objects.items() if v == "commit"]
    trees = {c: git.tree(c) for c in sorted(commits)}
    reachable = set(git.text("rev-list", "--objects", "--no-object-names", *tips).splitlines())
    if set(audit.objects) != reachable:
        raise Violation("UNKNOWN_OR_DANGLING_OBJECT")
    graph = {}
    for commit in sorted(commits):
        raw = git.read("cat-file", "commit", commit)
        header = raw.split(b"\n\n", 1)[0].splitlines()
        parents = tuple(oid(row[7:].decode()) for row in header if row.startswith(b"parent "))
        tree_id = next(oid(row[5:].decode()) for row in header if row.startswith(b"tree "))
        graph[commit] = (tree_id, parents)
        audit.commits.append({"commit": commit, "tree": tree_id, "parents": list(parents)})
    if {c for c, (_, parents) in graph.items() if not parents} != {V1_ROOT}:
        raise Violation("FOREIGN_ROOT_OR_ORIGINAL_HISTORY")
    if any(len(parents) > 2 for _, parents in graph.values()):
        raise Violation("UNREVIEWED_OCTOPUS_MERGE")
    root = _bootstrap(git)
    bases = git.text("merge-base", "--all", context.base, context.head).splitlines()
    if len(bases) != 1:
        raise Violation("AMBIGUOUS_MERGE_BASE")
    audit.merge_base = bases[0]
    for path, new_identity in _changed(trees[context.head], trees[context.base]).items():
        old_identity = trees[context.base].get(path)
        audit.proposed_diff.append(
            {
                "path": path,
                "old_blob": old_identity,
                "new_blob": new_identity,
                "change": "ADD"
                if old_identity is None
                else "DELETE"
                if new_identity is None
                else "MODIFY",
            }
        )
    # Exact-object renames are explanatory metadata. Modified renames remain an
    # explicit DELETE + ADD; no similarity heuristic reads unapproved data.
    additions = {r["new_blob"]: r["path"] for r in audit.proposed_diff if r["change"] == "ADD"}
    for row in audit.proposed_diff:
        if row["change"] == "DELETE" and row["old_blob"] in additions:
            row["exact_blob_rename_to"] = additions[row["old_blob"]]
    if context.test_merge and graph[context.test_merge][1] != (context.base, context.head):
        raise Violation("TEST_MERGE_PARENT_MISMATCH")
    if authority and (authority.kind != AUTHORITY_KIND or authority.scope_base != context.base):
        raise Violation("INDEPENDENT_AUTHORITY_SCOPE_MISMATCH")
    if authority:
        audit.authority_kind = authority.kind
    reviews = {r.commit: r for r in authority.reviews} if authority else {}
    if authority and len(reviews) != len(authority.reviews):
        raise Violation("DUPLICATE_REVIEW_IDENTITY")
    if set(reviews) - set(graph):
        raise Violation("REVIEW_OBJECT_NOT_IN_GRAPH")
    base_ancestors = set(git.text("rev-list", context.base).splitlines())
    if base_ancestors - {V1_ROOT} - set(reviews):
        raise Violation("UNTRUSTED_BASE_HISTORY")
    for commit, (tree_id, parents) in sorted(graph.items()):
        if commit == V1_ROOT:
            continue
        review = reviews.get(commit)
        if review:
            if (
                review.authority_id != AUTHORITY_KIND
                or review.tree != tree_id
                or review.parents != parents
            ):
                raise Violation("REVIEW_IDENTITY_MISMATCH")
        else:
            audit.issue("COMMIT_REVIEW_REQUIRED", identity=commit, review=True)
        # An independently reviewed merge binds the complete first-parent diff;
        # every other parent and all intermediate Trees are also inspected.
        before = trees[parents[0]]
        for parent in parents:
            for path, new_identity in _changed(trees[commit], trees[parent]).items():
                old = trees[parent].get(path)
                audit.diff.append(
                    {
                        "commit": commit,
                        "parent": parent,
                        "path": path,
                        "change": "ADD"
                        if old is None
                        else "DELETE"
                        if new_identity is None
                        else "MODIFY",
                        "old_blob": old,
                        "new_blob": new_identity,
                    }
                )
        _review_files(
            git,
            audit,
            commit,
            trees[commit],
            before,
            review,
            authority.bundles if authority else (),
            root,
        )
    if not any(row["severity"] == "BLOCKED" for row in audit.issues):
        _working_tree(git, context, trees[context.checkout])
        git.read("fsck", "--full", "--strict", "--no-reflogs")


def context_payload(context: Context) -> dict[str, object]:
    return {
        "base": context.base,
        "head": context.head,
        "checkout": context.checkout,
        "refs": [list(r) for r in context.refs],
        "origin": context.origin,
        "test_merge": context.test_merge,
    }


def authority_payload(authority: Authority) -> dict[str, object]:
    def file(f: FileGrant) -> dict[str, str]:
        return {"path": f.path, "blob": f.blob, "sha256": f.sha256, "kind": f.kind}

    return {
        "kind": authority.kind,
        "scope_base": authority.scope_base,
        "reviews": [
            {
                "commit": r.commit,
                "tree": r.tree,
                "parents": list(r.parents),
                "files": [file(f) for f in r.files],
                "deletions": list(r.deletions),
                "authority_id": r.authority_id,
            }
            for r in authority.reviews
        ],
        "bundles": [
            {
                "producer_root": b.producer_root,
                "producer_closure_sha256": b.producer_closure_sha256,
                "seed": b.seed,
                "files": [file(f) for f in b.files],
            }
            for b in authority.bundles
        ],
    }


def _dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(k, str) for k in value):
        raise Violation("INVALID_TRUST_DOCUMENT")
    return {str(k): v for k, v in value.items()}


def _list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise Violation("INVALID_TRUST_DOCUMENT")
    return list(value)


def _str(value: object) -> str:
    if not isinstance(value, str):
        raise Violation("INVALID_TRUST_DOCUMENT")
    return value


def read_context(path: Path) -> Context:
    d = _dict(json.loads(path.read_bytes()))
    pairs = [_list(v) for v in _list(d["refs"])]
    if any(len(v) != 2 for v in pairs):
        raise Violation("INVALID_REF_CONTEXT")
    return Context(
        _str(d["base"]),
        _str(d["head"]),
        _str(d["checkout"]),
        tuple((_str(v[0]), _str(v[1])) for v in pairs),
        _str(d["origin"]) if d.get("origin") is not None else None,
        _str(d["test_merge"]) if d.get("test_merge") is not None else None,
    )


def read_authority(path: Path, seal: str, repo: Path) -> Authority:
    if (
        path.is_symlink()
        or path.absolute().is_relative_to(repo.absolute())
        or path.resolve().is_relative_to(repo.resolve())
    ):
        raise Violation("PROPOSED_HEAD_IS_NOT_AUTHORITY")
    info = path.stat()
    if info.st_uid != os.getuid() or info.st_mode & 0o022 or info.st_nlink != 1:
        raise Violation("UNCONTROLLED_REVIEW_DOCUMENT")
    raw = path.read_bytes()
    if not re.fullmatch(r"[0-9a-f]{64}", seal) or digest(raw) != seal:
        raise Violation("INDEPENDENT_REVIEW_SEAL_MISMATCH")
    d = _dict(json.loads(raw))

    def files(value: object) -> tuple[FileGrant, ...]:
        result = []
        for item in _list(value):
            f = _dict(item)
            result.append(FileGrant(*(_str(f[k]) for k in ("path", "blob", "sha256", "kind"))))
        return tuple(result)

    reviews = []
    for item in _list(d["reviews"]):
        r = _dict(item)
        reviews.append(
            Review(
                _str(r["commit"]),
                _str(r["tree"]),
                tuple(_str(v) for v in _list(r["parents"])),
                files(r["files"]),
                tuple(_str(v) for v in _list(r["deletions"])),
                _str(r["authority_id"]),
            )
        )
    bundles = []
    for item in _list(d["bundles"]):
        b = _dict(item)
        seed = b["seed"]
        if type(seed) is not int:
            raise Violation("INVALID_SYNTHETIC_SEED")
        bundles.append(
            SyntheticBundle(
                _str(b["producer_root"]),
                _str(b["producer_closure_sha256"]),
                seed,
                files(b["files"]),
            )
        )
    return Authority(_str(d["scope_base"]), tuple(reviews), tuple(bundles), _str(d["kind"]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--synthetic-review-authority", type=Path)
    parser.add_argument("--independent-authority-sha256")
    args = parser.parse_args()
    try:
        context = read_context(args.context)
        authority = None
        if args.synthetic_review_authority:
            authority = read_authority(
                args.synthetic_review_authority,
                args.independent_authority_sha256 or "",
                args.repository,
            )
        elif args.independent_authority_sha256:
            raise Violation("INDEPENDENT_AUTHORITY_REQUIRED")
        report = verify(args.repository, context, authority)
    except (Violation, OSError, ValueError, KeyError) as error:
        report = {
            "status": "BLOCKED",
            "reasons": [
                {"code": str(error) if isinstance(error, Violation) else "INVALID_TRUST_DOCUMENT"}
            ],
            "publication_authorized": False,
        }
    print(canonical(report).decode(), end="")
    raise SystemExit({"PASS": 0, "REVIEW_REQUIRED": 3, "BLOCKED": 2}[str(report["status"])])


if __name__ == "__main__":
    main()
