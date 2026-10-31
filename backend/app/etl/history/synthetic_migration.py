"""A three-commit clean-room rehearsal, never a real-repository migration tool."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path


def require_owned(repo: Path, owned: Path) -> None:
    if (
        repo.parent != owned
        or not owned.name.startswith("SYNTHETIC_ONLY_TD01C_")
        or repo.name not in {"source", "clean"}
        or repo.is_symlink()
    ):
        raise ValueError("SYNTHETIC_REPOSITORY_REQUIRED")


def verify_code_binding(content: bytes, original_hash: str, mapped_hash: str) -> None:
    if mapped_hash != original_hash or hashlib.sha256(content).hexdigest() != original_hash:
        raise ValueError("ORIGINAL_CODE_HASH_MISMATCH")


def simulate() -> dict[str, object]:
    # There is intentionally no caller-supplied repository, remote, or commit.
    with tempfile.TemporaryDirectory(prefix="SYNTHETIC_ONLY_TD01C_") as temporary:
        owned = Path(temporary)
        environment = {
            key: value for key, value in os.environ.items() if not key.startswith("GIT_")
        }
        environment.update(
            {
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_AUTHOR_NAME": "SYNTHETIC_ONLY",
                "GIT_COMMITTER_NAME": "SYNTHETIC_ONLY",
                "GIT_AUTHOR_EMAIL": "synthetic@example.invalid",
                "GIT_COMMITTER_EMAIL": "synthetic@example.invalid",
                "GIT_AUTHOR_DATE": "2000-01-01T00:00:00Z",
                "GIT_COMMITTER_DATE": "2000-01-01T00:00:00Z",
                "GIT_NO_LAZY_FETCH": "1",
                "GIT_TERMINAL_PROMPT": "0",
            }
        )

        def git(repo: Path, *args: str, data: bytes | None = None, check: bool = True) -> bytes:
            require_owned(repo, owned)
            if args[0] not in {
                "init",
                "hash-object",
                "mktree",
                "commit-tree",
                "update-ref",
                "tag",
                "rev-parse",
                "cat-file",
                "ls-tree",
                "remote",
            }:
                raise ValueError("SYNTHETIC_COMMAND_NOT_ALLOWED")
            result = subprocess.run(
                ["git", "-c", "commit.gpgsign=false", "-c", "tag.gpgSign=false", *args],
                cwd=repo,
                env=environment,
                input=data,
                check=check,
                capture_output=True,
            )
            return result.stdout

        source, clean = owned / "source", owned / "clean"
        for repo in (source, clean):
            repo.mkdir()
            git(repo, "init", "--initial-branch=main", "--object-format=sha1", "-q")
            assert git(repo, "remote") == b""
        code = [
            b"# SYNTHETIC_ONLY\nVALUE = 1\n",
            b"# SYNTHETIC_ONLY\nVALUE = 2\n",
            b"# SYNTHETIC_ONLY\nVALUE = 2\n",
        ]
        private_blob = (
            git(
                source,
                "hash-object",
                "-w",
                "--stdin",
                data=b"SYNTHETIC_ONLY_FAKE_PRIVATE_RECORD,7.123456\n",
            )
            .decode()
            .strip()
        )
        mappings: list[dict[str, object]] = []
        old_parent, new_parent = "", ""
        for index, content in enumerate(code):
            message = f"SYNTHETIC_ONLY_STEP_{index + 1}\n".encode()
            trees = []
            blobs = []
            commits = []
            for repo, parent in ((source, old_parent), (clean, new_parent)):
                blob = git(repo, "hash-object", "-w", "--stdin", data=content).decode().strip()
                entries = f"100644 blob {blob}\tengine.py\n"
                if repo == source and index < 2:
                    entries += f"100644 blob {private_blob}\tSYNTHETIC_ONLY_PRIVATE.csv\n"
                tree = git(repo, "mktree", data=entries.encode()).decode().strip()
                args = ["commit-tree", tree]
                if parent:
                    args.extend(["-p", parent])
                commit = git(repo, *args, data=message).decode().strip()
                trees.append(tree)
                blobs.append(blob)
                commits.append(commit)
            old_parent, new_parent = commits
            expected = hashlib.sha256(content).hexdigest()
            actual = git(clean, "cat-file", "blob", new_parent + ":engine.py")
            verify_code_binding(actual, expected, expected)
            mappings.append(
                {
                    "old_commit": old_parent,
                    "new_commit": new_parent,
                    "old_tree": trees[0],
                    "new_tree": trees[1],
                    "expected_content_sha256": expected,
                    "old_code_blob": blobs[0],
                    "new_code_blob": blobs[1],
                    "content_sha256_unchanged": blobs[0] == blobs[1],
                }
            )
        for repo, key in ((source, "old_commit"), (clean, "new_commit")):
            git(repo, "update-ref", "refs/heads/main", str(mappings[2][key]))
            git(repo, "update-ref", "refs/heads/feature", str(mappings[1][key]))
        tags = []
        for index in (0, 1):
            tag = f"SYNTHETIC_ONLY_V{index + 1}"
            objects = []
            for repo, key in ((source, "old_commit"), (clean, "new_commit")):
                git(repo, "tag", "-a", tag, str(mappings[index][key]), "-m", "SYNTHETIC_ONLY")
                objects.append(git(repo, "rev-parse", "refs/tags/" + tag).decode().strip())
            tags.append({"tag": tag, "old_object": objects[0], "new_object": objects[1]})
        old_commit = str(mappings[0]["old_commit"])
        old_resolves = bool(git(clean, "cat-file", "-t", old_commit, check=False))
        has_blob = bool(git(clean, "cat-file", "-t", private_blob, check=False))
        # A wrong but otherwise real locator must not change the expected Hash.
        wrong = git(clean, "cat-file", "blob", str(mappings[1]["new_commit"]) + ":engine.py")
        wrong_rejected = False
        try:
            verify_code_binding(
                wrong,
                str(mappings[0]["expected_content_sha256"]),
                hashlib.sha256(wrong).hexdigest(),
            )
        except ValueError as exc:
            if str(exc) != "ORIGINAL_CODE_HASH_MISMATCH":
                raise
            wrong_rejected = True
        assert not old_resolves and not has_blob and wrong_rejected
        final_tree = git(source, "ls-tree", "-r", "HEAD").decode()
        first_tree = git(source, "ls-tree", "-r", old_commit).decode()
        return {
            "data_class": "SYNTHETIC_ONLY",
            "commit_mapping": mappings,
            "tag_mapping": tags,
            "old_main_tree_has_private_path": "SYNTHETIC_ONLY_PRIVATE.csv" in final_tree,
            "old_history_reaches_private_blob": private_blob in first_tree,
            "clean_repository_has_private_blob": has_blob,
            "old_commit_locator_resolves_in_clean": old_resolves,
            "correct_mapping_verified": True,
            "wrong_mapping_rejected": wrong_rejected,
            "real_repository_history_rewritten": False,
            "real_migration_authorized": False,
            "mapping_status": "SYNTHETIC_REHEARSAL_ONLY_NOT_A_REAL_AUTHORITY",
        }


if __name__ == "__main__":
    print(json.dumps(simulate(), sort_keys=True, indent=2))
