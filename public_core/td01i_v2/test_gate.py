"""Public-only security cases; no original audit files or private Git history."""

import hashlib
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

CODE = b'"""Synthetic pure code."""\nVALUE = 1\n'
PATH = "backend/app/synthetic_public_test.py"


def git(repo, *args, data=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_NO_LAZY_FETCH="1")
    return subprocess.check_output(
        ["git", "-c", "protocol.allow=never", *args],
        cwd=repo,
        env=env,
        input=data,
        stderr=subprocess.DEVNULL,
    )


@pytest.fixture
def guard():
    source = Path(os.environ["TD01I_TRUSTED_GATE"])
    assert (
        hashlib.sha256(source.read_bytes()).hexdigest() == os.environ["TD01I_TRUSTED_GATE_SHA256"]
    )
    spec = importlib.util.spec_from_file_location("trusted_gate_v2", source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def repository(tmp_path, guard):
    base = Path(os.environ["TD01I_V1_FIXTURE"])
    root = tmp_path / "SYNTHETIC_ONLY"
    root.mkdir(mode=0o700)
    paths = git(base, "ls-tree", "-r", "--name-only", guard.V1_ROOT).decode().splitlines()
    assert len(paths) == 28
    for path in paths:
        file = root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(git(base, "show", guard.V1_ROOT + ":" + path))
    git(root, "init", "-q", "--template=", "-b", "main")
    git(root, "add", ".")
    git(root, "write-tree")
    raw = git(base, "cat-file", "commit", guard.V1_ROOT)
    assert (
        git(root, "hash-object", "-w", "-t", "commit", "--stdin", data=raw).decode().strip()
        == guard.V1_ROOT
    )
    git(root, "update-ref", "refs/heads/main", guard.V1_ROOT)
    return root


def context(guard, head=None):
    return guard.Context(
        guard.V1_ROOT,
        head or guard.V1_ROOT,
        head or guard.V1_ROOT,
        (("refs/heads/main", head or guard.V1_ROOT),),
    )


def commit(repo, path, raw, parent, *, delete=False):
    if delete:
        (repo / path).unlink()
        git(repo, "update-index", "--force-remove", "--", path)
    else:
        file = repo / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(raw)
        blob = git(repo, "hash-object", "-w", "--stdin", data=raw).decode().strip()
        git(repo, "update-index", "--add", "--cacheinfo", f"100644,{blob},{path}")
    tree = git(repo, "write-tree").decode().strip()
    # Exact synthetic metadata, avoiding any user identity or ambient Git config.
    body = (
        f"tree {tree}\nparent {parent}\n"
        "author SYNTHETIC_ONLY <synthetic@example.invalid> 2208988800 +0000\n"
        "committer SYNTHETIC_ONLY <synthetic@example.invalid> 2208988800 +0000\n"
        "\nSYNTHETIC_PROPOSAL\n"
    ).encode()
    head = git(repo, "hash-object", "-w", "-t", "commit", "--stdin", data=body).decode().strip()
    git(repo, "update-ref", "refs/heads/main", head)
    return head, tree


def test_root_and_unapproved_increment_are_distinct(repository, guard):
    assert guard.verify(repository, context(guard))["status"] == "PASS"
    head, _ = commit(repository, PATH, CODE, guard.V1_ROOT)
    assert guard.verify(repository, context(guard, head))["status"] == "REVIEW_REQUIRED"


def test_external_exact_review_can_admit_known_synthetic_code(repository, guard):
    head, tree = commit(repository, PATH, CODE, guard.V1_ROOT)
    grant = guard.FileGrant(PATH, guard.blob_id(CODE), guard.digest(CODE), "CODE")
    review = guard.Review(head, tree, (guard.V1_ROOT,), (grant,))
    authority = guard.Authority(guard.V1_ROOT, (review,))
    assert guard.verify(repository, context(guard, head), authority)["status"] == "PASS"


def test_deleted_intermediate_data_is_not_hidden(repository, guard):
    path = "data/SYNTHETIC_UNPROVEN.csv"
    first, _ = commit(repository, path, b"SYNTHETIC_ONLY\n", guard.V1_ROOT)
    head, _ = commit(repository, path, b"", first, delete=True)
    assert guard.verify(repository, context(guard, head))["status"] == "BLOCKED"


@pytest.mark.parametrize("kind", ["self_policy", "binary", "lfs", "dependency", "fake_synthetic"])
def test_proposed_labels_or_content_never_self_authorize(repository, guard, kind):
    path, raw = {
        "self_policy": ("tools/verify_public_core.py", b'print("PASS")\n'),
        "binary": ("SYNTHETIC_ONLY.py", b"\x00SYNTHETIC_ONLY"),
        "lfs": ("SYNTHETIC_ONLY.py", b"version https://git-lfs.github.com/spec/v1\n"),
        "dependency": (PATH, b"import SYNTHETIC_UNREGISTERED\n"),
        "fake_synthetic": ("approved.json", b'{"APPROVED":true,"SYNTHETIC_ONLY":true}\n'),
    }[kind]
    head, _ = commit(repository, path, raw, guard.V1_ROOT)
    report = guard.verify(repository, context(guard, head))
    assert report["status"] == "BLOCKED"
    assert raw.decode(errors="ignore") not in str(report)


@pytest.mark.parametrize("kind", ["dangling", "tag", "hidden_remote"])
def test_object_set_and_refs_are_not_just_the_head_tree(repository, guard, kind):
    if kind == "dangling":
        git(repository, "hash-object", "-w", "--stdin", data=b"SYNTHETIC_HIDDEN")
    elif kind == "tag":
        git(repository, "tag", "SYNTHETIC_EXTRA")
    else:
        git(
            repository, "config", "remote.origin.url", "https://github.com/SYNTHETIC_ONLY/UNTRUSTED"
        )
    assert guard.verify(repository, context(guard))["status"] == "BLOCKED"


def test_head_file_is_not_independent_authority(repository, guard):
    file = repository / "self-review.json"
    file.write_text('{"APPROVED":true}\n')
    with pytest.raises(guard.Violation, match="PROPOSED_HEAD_IS_NOT_AUTHORITY"):
        guard.read_authority(file, hashlib.sha256(file.read_bytes()).hexdigest(), repository)
