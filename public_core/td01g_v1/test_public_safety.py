"""Exact-object negative tests in new synthetic roots; never restore business data."""

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from tools import verify_public_core as guard

ROOT = Path(__file__).resolve().parents[1]


def git(root, *args, data=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(
        GIT_NO_LAZY_FETCH="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_NOSYSTEM="1",
        GIT_AUTHOR_NAME="SYNTHETIC_ONLY",
        GIT_AUTHOR_EMAIL="synthetic@example.invalid",
        GIT_COMMITTER_NAME="SYNTHETIC_ONLY",
        GIT_COMMITTER_EMAIL="synthetic@example.invalid",
        GIT_AUTHOR_DATE="2040-01-01T00:00:00+00:00",
        GIT_COMMITTER_DATE="2040-01-01T00:00:00+00:00",
    )
    return subprocess.check_output(
        ["git", "-c", "protocol.allow=never", "-c", "commit.gpgsign=false", *args],
        cwd=root,
        env=env,
        input=data,
        stderr=subprocess.DEVNULL,
    )


@pytest.fixture
def candidate(tmp_path):
    guard.verify(ROOT)
    target = tmp_path / "SYNTHETIC_ONLY"
    target.mkdir(mode=0o700)
    manifest = json.loads((ROOT / guard.MANIFEST).read_bytes())
    for name in [guard.MANIFEST, *(r["path"] for r in manifest["files"])]:
        file = target / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes((ROOT / name).read_bytes())
    git(target, "init", "-q", "--template=", "-b", "main")
    git(target, "add", ".")
    git(target, "commit", "-qm", "SYNTHETIC ROOT ONLY")
    return target


def test_fresh_root_exact_allowlist(candidate):
    proof = guard.verify(candidate)
    assert proof["status"] == "PASS" and proof["parent_count"] == 0
    assert proof["remote_count"] == 0 and proof["tag_count"] == 0
    assert proof["publication_authorized"] is False


@pytest.mark.parametrize(
    "name", ["SYNTHETIC_ONLY.csv", "backend/app/renamed.py", "extra.json", "unknown.content.gz"]
)
def test_renaming_or_labels_do_not_admit_unknown_files(candidate, name):
    target = candidate / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('{"DATA_CLASS":"SYNTHETIC_ONLY","PUBLIC_CODE":true}\n')
    with pytest.raises(guard.PublicCoreViolation, match="UNKNOWN_WORKING_FILE"):
        guard.verify(candidate)


def test_known_business_identity_is_rejected_before_body_access(candidate):
    oid = "3413dbbc284312e75a2df98992a6ab66cfa87dbd"
    git(candidate, "update-index", "--add", "--cacheinfo", f"100644,{oid},renamed.py")
    tree = git(candidate, "write-tree", "--missing-ok").decode().strip()
    commit = git(candidate, "commit-tree", tree, data=b"SYNTHETIC NEGATIVE\n").decode().strip()
    git(candidate, "update-ref", "refs/heads/main", commit)
    with pytest.raises(guard.PublicCoreViolation, match="BLOCKED_BUSINESS_BLOB"):
        guard.verify(candidate)


def test_forged_manifest_and_labels_are_not_authority(candidate):
    file = candidate / guard.MANIFEST
    payload = json.loads(file.read_bytes())
    payload["DATA_CLASS"] = "SYNTHETIC_ONLY"
    payload["files"].append(
        {"path": "renamed.py", "sha256": hashlib.sha256(b"SYNTHETIC_ONLY").hexdigest()}
    )
    file.write_text(json.dumps(payload))
    with pytest.raises(guard.PublicCoreViolation, match="MANIFEST_SEAL_MISMATCH"):
        guard.verify(candidate)


def test_unreachable_object_cannot_hide_outside_the_tree(candidate):
    git(candidate, "hash-object", "-w", "--stdin", data=b"SYNTHETIC_UNREVIEWED_OBJECT")
    with pytest.raises(guard.PublicCoreViolation, match="DANGLING_OBJECT"):
        guard.verify(candidate)


@pytest.mark.parametrize("kind", ["tag", "alternates", "origin", "changed"])
def test_history_transport_and_source_tampering(candidate, kind):
    if kind == "tag":
        git(candidate, "tag", "SYNTHETIC_OLD_TAG")
    elif kind == "alternates":
        file = candidate / ".git/objects/info/alternates"
        file.write_text("SYNTHETIC_DO_NOT_FOLLOW\n")
    elif kind == "origin":
        git(
            candidate,
            "config",
            "remote.origin.url",
            "https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent",
        )
    else:
        file = candidate / "backend/app/public_core.py"
        file.write_bytes(file.read_bytes() + b"\nSYNTHETIC_UNREVIEWED = True\n")
    with pytest.raises(guard.PublicCoreViolation):
        guard.verify(candidate)


def test_readonly_checkout_shaped_refs_are_checked_without_network(candidate):
    root = git(candidate, "rev-parse", "HEAD").decode().strip()
    git(
        candidate, "config", "remote.origin.url", "https://github.com/SYNTHETIC_ONLY/SYNTHETIC_CORE"
    )
    git(candidate, "config", "remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*")
    git(candidate, "update-ref", "refs/remotes/origin/main", root)
    git(candidate, "checkout", "--detach", "-q", root)
    assert guard.verify(candidate)["remote_count"] == 1


def test_isolated_bootstrap_does_not_execute_an_unreviewed_shadow_module(candidate):
    file = candidate / "tools/json.py"
    file.write_text('raise RuntimeError("SYNTHETIC_SHADOW_EXECUTED")\n')
    import sys

    result = subprocess.run(
        [sys.executable, "-I", "-B", str(candidate / "tools/verify_public_core.py")],
        cwd=candidate,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "UNKNOWN_WORKING_FILE" in result.stderr
    assert "SYNTHETIC_SHADOW_EXECUTED" not in result.stderr
