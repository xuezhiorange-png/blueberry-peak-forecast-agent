"""Closed locators for the already verified two-XLS rewrite, never data approval.

Source readers must still verify their original Blob and independent SHA256.
These locators do not search by content or admit an arbitrary missing revision.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
LOCATORS_FILE = ROOT / "docs/tech-debt/td01-clean-history-compatibility-r1/identity-locators.json"
LOCATORS_SHA256 = "cd0528930cc1a2bd75ecc9db37b5432582428eef32cae74d27844a449f654fdd"
BLOCKED_BLOBS = (
    "3413dbbc284312e75a2df98992a6ab66cfa87dbd",
    "a045348c4c72507ae367b4e30f267fcf19c490c1",
)


class HistoryLocationError(AssertionError):
    """Stable fail-closed location error, without file bodies or local paths."""


def catalog() -> dict[str, Any]:
    raw = LOCATORS_FILE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != LOCATORS_SHA256:
        raise HistoryLocationError("REWRITE_LOCATOR_TRUST_ANCHOR_MISMATCH")
    value = json.loads(raw)
    if not isinstance(value, dict) or value.get("schema") != "TD01_CLEAN_HISTORY_LOCATORS_R1":
        raise HistoryLocationError("INVALID_REWRITE_LOCATORS")
    return value


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(
        GIT_NO_LAZY_FETCH="1",
        GIT_NO_REPLACE_OBJECTS="1",
        GIT_OPTIONAL_LOCKS="0",
        GIT_TERMINAL_PROMPT="0",
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
    )
    return subprocess.run(
        ["git", "-c", "protocol.allow=never", "-c", "core.hooksPath=" + os.devnull, *args],
        cwd=repo,
        env=env,
        capture_output=True,
        check=False,
    )


def _type(repo: Path, oid: str) -> str | None:
    result = _run(repo, "cat-file", "-t", oid)
    return result.stdout.decode().strip() if result.returncode == 0 else None


def mapped_revision(original: str) -> str | None:
    row = catalog()["entries"].get(original)
    return str(row["rewritten_commit"]) if row is not None else None


def resolve(repo: Path, original: str, *, role: str = "SOURCE") -> str:
    if re.fullmatch(r"[0-9a-f]{40}", original) is None:
        raise HistoryLocationError("EXPLICIT_HISTORICAL_IDENTITY_REQUIRED")
    policy = catalog()
    row = policy["entries"].get(original)
    anchor = policy["clean_main"]
    clean = (
        _type(repo, anchor) == "commit"
        and _run(repo, "merge-base", "--is-ancestor", anchor, "HEAD").returncode == 0
    )
    if clean:
        common = _run(repo, "rev-parse", "--git-common-dir")
        if common.returncode:
            raise HistoryLocationError("REWRITE_REPOSITORY_UNAVAILABLE")
        git_dir = (repo / common.stdout.decode().strip()).resolve()
        if any(
            (git_dir / name).exists()
            for name in ("shallow", "info/grafts", "objects/info/alternates")
        ) or any((git_dir / "objects/pack").glob("*.promisor")):
            raise HistoryLocationError("REWRITE_EXTERNAL_HISTORY_FORBIDDEN")
        if _run(repo, "for-each-ref", "--format=%(refname)", "refs/replace/").stdout.strip():
            raise HistoryLocationError("REWRITE_REPLACE_REFS_FORBIDDEN")
        if _type(repo, policy["original_root"]) is not None or _type(repo, original) is not None:
            raise HistoryLocationError("REWRITE_ORIGINAL_HISTORY_PRESENT")
        if any(_type(repo, oid) is not None for oid in BLOCKED_BLOBS):
            raise HistoryLocationError("REWRITE_BLOCKED_BLOB_PRESENT")
        if row is None or role not in row["roles"]:
            raise HistoryLocationError("HISTORICAL_COMMIT_UNAVAILABLE")
        revision, expected_tree = row["rewritten_commit"], row["rewritten_tree"]
    else:
        if _type(repo, original) != "commit":
            raise HistoryLocationError("HISTORICAL_COMMIT_UNAVAILABLE")
        if row is None:
            # Existing unregistered synthetic/current-history callers retain
            # their original exact Commit behavior, with no missing-ref fallback.
            return original
        if role not in row["roles"]:
            raise HistoryLocationError("UNREGISTERED_HISTORY_ROLE")
        revision, expected_tree = original, row["original_tree"]
    if role == "BASELINE" and row["original_tree"] != row["rewritten_tree"]:
        raise HistoryLocationError("BASELINE_TREE_IDENTITY_CHANGED")
    tree = _run(repo, "rev-parse", "--verify", revision + "^{tree}")
    if tree.returncode or tree.stdout.decode().strip() != expected_tree:
        raise HistoryLocationError("HISTORICAL_TREE_IDENTITY_MISMATCH")
    return str(revision)


def metadata_identity(original: str, path: str) -> dict[str, Any] | None:
    return next(
        (
            row
            for row in catalog()["metadata_identities"]
            if (row["original_commit"], row["path"]) == (original, path)
        ),
        None,
    )
