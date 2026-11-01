"""Owned synthetic PR experiments, separate from real review authorization."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

from backend.app.core import clean_public_repository as previous
from backend.app.core import historical_code_identity as history
from backend.app.core import public_core_incremental_gate as gate
from backend.app.core import public_core_rehearsal as v1

ROOT = Path(__file__).resolve().parents[3]
BASE_MAIN = "fe494971c92f1d951f5acfeb6a70b85a4aff23ac"
CODE_PATH = "backend/app/synthetic_extension.py"
CODE = (
    b'"""Independent synthetic extension."""\n\n\n'
    b"def amount(value: int) -> int:\n    return value + 1\n"
)
CODE2 = CODE.replace(b"value + 1", b"value + 2")
NEGATIVES = (
    "ref_rollback",
    "tag",
    "extra_ref",
    "alternate",
    "graft",
    "shallow",
    "remote",
    "dangling",
    "old_commit",
    "symlink",
    "submodule",
    "lfs",
    "binary",
    "missing",
    "wrong_base",
    "wrong_review",
    "dependency",
    "path",
)


def tree_identity(files: Mapping[str, str]) -> str:
    """Independent Tree identity from predeclared expected bytes, not PR hashes."""
    direct = {p: value for p, value in files.items() if "/" not in p}
    folders = {p.split("/", 1)[0] for p in files if "/" in p}
    entries = [(p, "100644", value, p.encode()) for p, value in direct.items()]
    for folder in folders:
        children = {
            p[len(folder) + 1 :]: value for p, value in files.items() if p.startswith(folder + "/")
        }
        entries.append((folder, "40000", tree_identity(children), (folder + "/").encode()))
    raw = b"".join(
        mode.encode() + b" " + name.encode() + b"\0" + bytes.fromhex(value)
        for name, mode, value, _ in sorted(entries, key=lambda r: r[3])
    )
    return hashlib.sha1(b"tree " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


class Graph:
    def __init__(self, repo: Path):
        self.repo = repo
        self.base = self.head = gate.V1_ROOT
        self.refs = {"refs/heads/main": self.base}
        self.branch: str | None = None
        self.pr_number = 0
        self.reviews: list[gate.Review] = []
        self.bundles: list[gate.SyntheticBundle] = []
        self.origin: str | None = None
        self.test_merge: str | None = None
        self.checked_out = self.head
        self.expected_trees = {gate.V1_ROOT: gate.Git(repo).tree(gate.V1_ROOT)}

    def write_git(self, *args: str, data: bytes | None = None) -> bytes:
        return previous._write_git(self.repo, *args, data=data)

    def _proposal(self) -> None:
        if self.branch is None:
            self.pr_number += 1
            self.branch = f"refs/heads/pr-{self.pr_number}"
            self.write_git("update-ref", self.branch, self.head)
            self.refs[self.branch] = self.head
            self.write_git("symbolic-ref", "HEAD", self.branch)

    def commit(self, changes: Mapping[str, bytes | None]) -> str:
        self._proposal()
        for path, raw in changes.items():
            gate.safe_path(path)
            target = self.repo / path
            if raw is None:
                target.unlink()
                self.write_git("update-index", "--force-remove", "--", path)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
                target.chmod(0o600)
                blob = self.write_git("hash-object", "-w", "--stdin", data=raw).decode().strip()
                self.write_git("update-index", "--add", "--cacheinfo", f"100644,{blob},{path}")
        tree = self.write_git("write-tree").decode().strip()
        return self._commit_tree(tree)

    def _commit_tree(self, tree: str, *, extra_parent: str | None = None) -> str:
        arguments = ["commit-tree", tree, "-p", self.head]
        if extra_parent:
            arguments.extend(("-p", extra_parent))
        commit = (
            self.write_git(*arguments, data=b"SYNTHETIC_ONLY_PROPOSED_COMMIT\n").decode().strip()
        )
        assert self.branch is not None
        self.write_git("update-ref", self.branch, commit)
        self.head = self.checked_out = commit
        self.refs[self.branch] = commit
        return commit

    def review(
        self,
        expected_changes: Mapping[str, bytes | None],
        *,
        kinds: Mapping[str, str] | None = None,
    ) -> None:
        """Harness-only independent intent. PR files never supply these bytes."""
        git = gate.Git(self.repo)
        header = git.read("cat-file", "commit", self.head).split(b"\n\n", 1)[0].splitlines()
        parents = tuple(v[7:].decode() for v in header if v.startswith(b"parent "))
        actual_tree = next(v[5:].decode() for v in header if v.startswith(b"tree "))
        assert parents and parents[0] in self.expected_trees, "INDEPENDENT_REVIEW_PARENT_REQUIRED"
        expected = dict(self.expected_trees[parents[0]])
        grants = []
        deletions = []
        for path, raw in expected_changes.items():
            if raw is None:
                expected.pop(path)
                deletions.append(path)
            else:
                identity = gate.blob_id(raw)
                expected[path] = identity
                kind = (kinds or {}).get(
                    path,
                    "POLICY"
                    if path.startswith(("tools/", ".github/"))
                    or path in {gate.MANIFEST, "PUBLIC-CORE-V2-EXECUTORS.json"}
                    else "CODE"
                    if path.endswith(".py")
                    else "PUBLIC_TEXT",
                )
                grants.append(gate.FileGrant(path, identity, gate.digest(raw), kind))
        assert tree_identity(expected) == actual_tree, "INDEPENDENT_REVIEW_INPUT_MISMATCH"
        assert git.tree(self.head) == expected, "INDEPENDENT_REVIEW_INPUT_MISMATCH"
        self.reviews.append(
            gate.Review(self.head, actual_tree, parents, tuple(grants), tuple(deletions))
        )
        self.expected_trees[self.head] = expected

    def authority(self) -> gate.Authority:
        return gate.Authority(self.base, tuple(self.reviews), tuple(self.bundles))

    def context(self) -> gate.Context:
        return gate.Context(
            self.base,
            self.head,
            self.checked_out,
            tuple(sorted(self.refs.items())),
            self.origin,
            self.test_merge,
        )

    def check(self) -> dict[str, object]:
        return gate.verify(self.repo, self.context(), self.authority())

    def merge(self, expected_changes: Mapping[str, bytes | None]) -> dict[str, object]:
        assert self.branch is not None and self.check()["status"] == "PASS"
        branch = self.branch
        self.write_git("checkout", "-q", "main")
        self.write_git(
            "merge", "--no-ff", "-m", "SYNTHETIC_ONLY_INDEPENDENTLY_REVIEWED_MERGE", branch
        )
        self.head = self.checked_out = self.write_git("rev-parse", "HEAD").decode().strip()
        self.refs["refs/heads/main"] = self.head
        self.review(expected_changes)
        assert self.check()["status"] == "PASS"
        self.base = self.head
        self.branch = None
        return self.check()

    def inject_missing_blob(self, identity: str) -> None:
        self._proposal()
        self.write_git("update-index", "--add", "--cacheinfo", f"100644,{identity},renamed.py")
        tree = self.write_git("write-tree", "--missing-ok").decode().strip()
        self._commit_tree(tree)


@contextmanager
def graph() -> Iterator[Graph]:
    with previous.owned_repository() as repo:
        original = v1.materialize(repo)
        assert original["root_commit"] == gate.V1_ROOT
        yield Graph(repo)


def reasons(report: dict[str, object]) -> set[str]:
    raw = report["reasons"]
    assert isinstance(raw, list)
    return {str(row["code"]) for row in raw}


def lifecycle() -> dict[str, object]:
    with graph() as g:
        g.commit({CODE_PATH: CODE})
        unreviewed = g.check()
        g.review({CODE_PATH: CODE})
        # A second normal feature commit is reviewed independently as well.
        note = {"backend/app/second_synthetic_extension.py": b'"""Synthetic code."""\nVALUE = 2\n'}
        g.commit(note)
        g.review(note)
        first = g.check()
        merged = g.merge({CODE_PATH: CODE, **note})
        g.commit({CODE_PATH: CODE2})
        g.review({CODE_PATH: CODE2})
        second = g.check()
        final = g.merge({CODE_PATH: CODE2})
        return {
            "first_unreviewed": unreviewed,
            "first_reviewed": first,
            "first_merged": merged,
            "second_reviewed": second,
            "second_merged": final,
            "actual_remote_authorization": "UNVERIFIED",
        }


def negative(kind: str) -> dict[str, object]:
    with graph() as g:
        if kind == "ref_rollback":
            g.commit({"data/SYNTHETIC_UNPROVEN.csv": b"SYNTHETIC_ONLY\n"})
            assert g.branch is not None
            g.write_git("update-ref", g.branch, gate.V1_ROOT)
            g.write_git("read-tree", "--reset", "-u", gate.V1_ROOT)
            g.head = g.checked_out = gate.V1_ROOT
            g.refs[g.branch] = gate.V1_ROOT
        elif kind == "tag":
            g.write_git("tag", "SYNTHETIC_EXTRA_TAG")
        elif kind == "extra_ref":
            g.write_git("update-ref", "refs/heads/unknown", gate.V1_ROOT)
        elif kind in {"alternate", "graft", "shallow"}:
            name = {
                "alternate": "objects/info/alternates",
                "graft": "info/grafts",
                "shallow": "shallow",
            }[kind]
            file = g.repo / ".git" / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text("SYNTHETIC_UNTRUSTED_METADATA\n")
        elif kind == "remote":
            g.write_git(
                "config",
                "remote.origin.url",
                "https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent",
            )
        elif kind == "dangling":
            g.write_git(
                "hash-object", "-w", "--stdin", data=b"SYNTHETIC_PRIVATE_LITERAL_MUST_NOT_APPEAR"
            )
        elif kind == "old_commit":
            g._proposal()
            tree = g.write_git("rev-parse", "HEAD^{tree}").decode().strip()
            foreign = (
                g.write_git(
                    "commit-tree", tree, data=b"SYNTHETIC_FOREIGN_HISTORY_NOT_REAL_OLD_COMMIT\n"
                )
                .decode()
                .strip()
            )
            g._commit_tree(tree, extra_parent=foreign)
        elif kind in {"symlink", "submodule"}:
            g._proposal()
            identity = (
                gate.V1_ROOT
                if kind == "submodule"
                else g.write_git("hash-object", "-w", "--stdin", data=b"SYNTHETIC_TARGET")
                .decode()
                .strip()
            )
            mode = "160000" if kind == "submodule" else "120000"
            g.write_git(
                "update-index", "--add", "--cacheinfo", f"{mode},{identity},SYNTHETIC_SPECIAL"
            )
            g._commit_tree(g.write_git("write-tree").decode().strip())
        elif kind == "lfs":
            g.commit(
                {
                    CODE_PATH: b"version https://git-lfs.github.com/spec/v1\noid sha256:"
                    + b"0" * 64
                    + b"\nsize 12\n"
                }
            )
        elif kind == "binary":
            g.commit({"SYNTHETIC_ONLY.bin": b"\x00SYNTHETIC_PRIVATE_LITERAL_MUST_NOT_APPEAR"})
        elif kind == "missing":
            g.inject_missing_blob("f" * 40)
        elif kind == "wrong_base":
            return gate.verify(g.repo, replace(g.context(), base="0" * 40), g.authority())
        elif kind == "wrong_review":
            g.commit({CODE_PATH: CODE})
            g.review({CODE_PATH: CODE})
            return gate.verify(g.repo, g.context(), replace(g.authority(), kind="SELF_APPROVED"))
        elif kind == "dependency":
            g.commit({CODE_PATH: b"import SYNTHETIC_UNREGISTERED_PACKAGE\n"})
        elif kind == "path":
            g._proposal()
            identity = g.write_git("hash-object", "-w", "--stdin", data=CODE).decode().strip()
            tree = (
                g.write_git(
                    "hash-object",
                    "-w",
                    "--literally",
                    "-t",
                    "tree",
                    "--stdin",
                    data=b"100644 ../SYNTHETIC_BAD.py\0" + bytes.fromhex(identity),
                )
                .decode()
                .strip()
            )
            g._commit_tree(tree)
        else:
            raise AssertionError("UNKNOWN_SYNTHETIC_SCENARIO")
        return g.check()


def synthetic_bundle_case() -> dict[str, object]:
    with graph() as g, tempfile.TemporaryDirectory(prefix="TD01I_SYNTHETIC_ONLY_") as folder:
        # The root producer/parent closure is verified before this import.
        root = gate._bootstrap(gate.Git(g.repo))
        from backend.app.etl.history.synthetic_publication import export, generate

        target = Path(folder) / "generated"
        export(generate(43), target)
        raw = {"examples/SYNTHETIC-seed43/" + p.name: p.read_bytes() for p in target.iterdir()}
        kinds = {p: "SYNTHETIC" for p in raw}
        g.commit(raw)
        g.review(raw, kinds=kinds)
        grants = g.reviews[-1].files
        bundle = gate.SyntheticBundle(gate.V1_ROOT, gate.producer_closure(root), 43, grants)
        g.bundles.append(bundle)
        valid = g.check()
        wrong = gate.verify(
            g.repo,
            g.context(),
            replace(g.authority(), bundles=(replace(bundle, producer_closure_sha256="0" * 64),)),
        )
        path = next(p for p in raw if p.endswith(".csv"))
        g.commit({path: raw[path] + b"SYNTHETIC_UNVERIFIED\n"})
        g.review({path: raw[path] + b"SYNTHETIC_UNVERIFIED\n"}, kinds=kinds)
        changed = g.check()
        return {"valid": valid, "changed_bytes": changed, "wrong_producer": wrong}


def counterfeit_bundle_case(*, xlsx_container_only: bool = False) -> dict[str, object]:
    """Five internally consistent files, reviewed exactly, but for the wrong seed."""
    with graph() as g:
        git = gate.Git(g.repo)
        root = gate._bootstrap(git)
        raw = {
            "examples/SYNTHETIC-seed43/" + Path(path).name: git.read("cat-file", "blob", f.blob)
            for path, f in root.items()
            if path.startswith("docs/tech-debt/td01c-synthetic-example/")
        }
        manifest = next(p for p in raw if p.endswith("/SYNTHETIC_ONLY-manifest.json"))
        declaration = gate._dict(json.loads(raw[manifest]))
        assert declaration["seed"] == 41
        seed = 41 if xlsx_container_only else 43
        declaration["seed"] = seed
        if xlsx_container_only:
            path = next(p for p in raw if p.endswith(".xlsx"))
            stream = io.BytesIO(raw[path])
            with zipfile.ZipFile(stream, "a") as archive:
                archive.comment = b"SYNTHETIC_ONLY_NON_GENERATOR_CONTAINER"
            raw[path] = stream.getvalue()
            exports = gate._dict(declaration["exports_sha256"])
            exports[Path(path).name] = gate.digest(raw[path])
            declaration["exports_sha256"] = exports
        raw[manifest] = (
            json.dumps(declaration, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        ).encode()
        expected_exports = {
            Path(p).name: gate.digest(body) for p, body in raw.items() if p != manifest
        }
        assert declaration["exports_sha256"] == expected_exports and len(raw) == 5
        assert declaration["source_identity"] == "TD01C_INDEPENDENT_GENERATOR_V1"
        g.commit(raw)
        g.review(raw, kinds={p: "SYNTHETIC" for p in raw})
        grants = g.reviews[-1].files
        assert all(f.blob == gate.blob_id(raw[f.path]) for f in grants)
        assert all(f.sha256 == gate.digest(raw[f.path]) for f in grants)
        g.bundles.append(
            gate.SyntheticBundle(gate.V1_ROOT, gate.producer_closure(root), seed, grants)
        )
        return {
            "file_count": len(raw),
            "declared_seed": seed,
            "actual_generation_seed": 41,
            "xlsx_container_only": xlsx_container_only,
            "manifest_self_consistent": True,
            "independent_review_matches_all_blobs_and_sha256": True,
            "gate": g.check(),
        }


def checkout_case() -> dict[str, object]:
    with graph() as g:
        g.commit({CODE_PATH: CODE})
        g.review({CODE_PATH: CODE})
        head = g.head
        base = g.base
        tree = g.write_git("rev-parse", head + "^{tree}").decode().strip()
        merge = (
            g.write_git(
                "commit-tree", tree, "-p", base, "-p", head, data=b"SYNTHETIC_GITHUB_TEST_MERGE\n"
            )
            .decode()
            .strip()
        )
        g.reviews.append(gate.Review(merge, tree, (base, head), g.reviews[-1].files))
        g.test_merge = merge
        g.write_git("checkout", "-q", "--detach", merge)
        g.checked_out = merge
        g.origin = "https://github.com/SYNTHETIC_ONLY/SYNTHETIC_PUBLIC_CORE"
        g.write_git("config", "remote.origin.url", g.origin)
        g.write_git("update-ref", "refs/remotes/origin/main", base)
        g.refs["refs/remotes/origin/main"] = base
        valid = g.check()
        wrong = gate.verify(g.repo, replace(g.context(), checkout=head), g.authority())
        g.write_git("config", "remote.origin.url", "https://github.com/SYNTHETIC_ONLY/OTHER")
        untrusted = g.check()
        return {"valid": valid, "wrong_checkout": wrong, "untrusted_origin": untrusted}


def independent_processes(output: Path) -> dict[str, object]:
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    with graph() as g:
        g.commit({CODE_PATH: CODE})
        g.review({CODE_PATH: CODE})
        context = output / "context.json"
        authority = output / "authority.json"
        context.write_bytes(gate.canonical(gate.context_payload(g.context())))
        raw = gate.canonical(gate.authority_payload(g.authority()))
        authority.write_bytes(raw)
        authority.chmod(0o600)
        command = [
            sys.executable,
            "-I",
            "-B",
            str(ROOT / "backend/app/core/public_core_incremental_gate.py"),
            "--repository",
            str(g.repo),
            "--context",
            str(context),
            "--synthetic-review-authority",
            str(authority),
            "--independent-authority-sha256",
            gate.digest(raw),
        ]
        runs = [subprocess.run(command, capture_output=True, check=False) for _ in range(2)]
        for number, run in enumerate(runs):
            (output / f"process-{number}.json").write_bytes(run.stdout)
            (output / f"process-{number}.stderr").write_bytes(run.stderr)
        complete = [
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "backend.app.core.public_core_incremental_rehearsal",
                    "--graph-only",
                ],
                cwd=ROOT,
                capture_output=True,
                check=False,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            for _ in range(2)
        ]
        for number, run in enumerate(complete):
            (output / f"independent-graph-{number}.json").write_bytes(run.stdout)
            (output / f"independent-graph-{number}.stderr").write_bytes(run.stderr)
        return {
            "equal": runs[0].stdout == runs[1].stdout and all(r.returncode == 0 for r in runs),
            "process_count": 2,
            "exit_codes": [r.returncode for r in runs],
            "result_sha256": gate.digest(runs[0].stdout),
            "independent_graph_process_count": 2,
            "independent_graph_exit_codes": [r.returncode for r in complete],
            "independent_graph_results_equal": complete[0].stdout == complete[1].stdout
            and all(r.returncode == 0 for r in complete),
            "independent_graph_result_sha256": gate.digest(complete[0].stdout),
        }


def verify_v1_preserved() -> None:
    paths = [row["repository_relative_path"] for row in v1.catalog()]
    paths += [
        "backend/app/core/public_core_rehearsal.py",
        "backend/tests/ci/test_public_core_rehearsal.py",
        ".github/workflows/ci.yml",
    ]
    paths += [
        p.relative_to(ROOT).as_posix()
        for p in (ROOT / "docs/tech-debt/td01g-public-core-r1").glob("*.json")
    ]
    paths += [
        p.relative_to(ROOT).as_posix()
        for p in (ROOT / "docs/tech-debt/td01f-rehearsal-r1").glob("*.json")
    ]
    paths += ["docs/tech-debt/td01f-public-code-candidates-r1.json"]
    for path in paths:
        before = history._git(ROOT, "ls-tree", BASE_MAIN, "--", path)
        after = history._git(ROOT, "ls-tree", "HEAD", "--", path)
        assert before == after, "V1_FROZEN_IDENTITY_CHANGED"
        row = after.split()
        if row:
            assert gate.blob_id((ROOT / path).read_bytes()) == row[2].decode(), (
                "V1_WORKTREE_CHANGED"
            )


def ci_equivalent(output: Path) -> dict[str, object]:
    from backend.app.core import public_core_incremental_ci as ci

    with (
        graph() as g,
        tempfile.TemporaryDirectory(prefix="TD01I_TRUSTED_BASE_EXECUTORS_") as folder,
    ):
        changes = {
            CODE_PATH: CODE,
            "tools/public_core_incremental_gate.py": (
                ROOT / "backend/app/core/public_core_incremental_gate.py"
            ).read_bytes(),
            "tools/run_public_ci_v2.py": (
                ROOT / "public_core/td01i_v2/run_public_ci.py"
            ).read_bytes(),
            "tools/public_core_v2_context.py": (
                ROOT / "public_core/td01i_v2/workflow_context.py"
            ).read_bytes(),
            "tests/test_public_gate_v2.py": (
                ROOT / "public_core/td01i_v2/test_gate.py"
            ).read_bytes(),
            ".github/workflows/public-core-v2.yml": (
                ROOT / "public_core/td01i_v2/workflow.yml"
            ).read_bytes(),
        }
        executor_files = {
            p: raw
            for p, raw in changes.items()
            if p.startswith("tools/") or p == "tests/test_public_gate_v2.py"
        }
        manifest = {
            "schema": "TD01I_V2_EXECUTOR_IDENTITIES_R1",
            "review_authority": "NOT_CONFIGURED_SOURCE_IDENTITIES_ONLY",
            "publication_authorized": False,
            "files": [
                {"path": p, "sha256": gate.digest(raw), "git_blob_oid": gate.blob_id(raw)}
                for p, raw in sorted(executor_files.items())
            ],
        }
        changes["PUBLIC-CORE-V2-EXECUTORS.json"] = gate.canonical(manifest)
        g.commit(changes)
        g.review(changes)
        g.merge(changes)
        g.commit({CODE_PATH: CODE2})
        g.review({CODE_PATH: CODE2})
        assert g.check()["status"] == "PASS"
        snapshot = Path(folder)
        snapshot.chmod(0o700)
        for path, expected in executor_files.items():
            identity = g.expected_trees[g.base][path]
            actual = gate.Git(g.repo).read("cat-file", "blob", identity)
            assert actual == expected and gate.blob_id(expected) == identity
            file = snapshot / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(actual)
            file.chmod(0o600)
        report = ci.execute(g.repo, g.context(), g.authority(), output, trusted_executors=snapshot)
        report["trusted_base_executor_identities"] = manifest
        return report


def rehearse(output: Path) -> dict[str, object]:
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    verify_v1_preserved()
    life = lifecycle()
    negatives = {kind: negative(kind) for kind in NEGATIVES}
    for identity in sorted(gate.BLOCKED_BLOBS):
        with graph() as g:
            g.inject_missing_blob(identity)
            negatives["forbidden_object_" + identity] = g.check()
    with graph() as g:
        g.inject_missing_blob(sorted(gate.BLOCKED_BLOBS)[0])
        (g.repo / "renamed.py").write_bytes(b"SYNTHETIC_PLACEHOLDER_NOT_A_SOURCE_FILE\n")
        g.commit({"renamed.py": None})
        negatives["deleted_forbidden_identity"] = g.check()
    with graph() as g:
        g.commit({"data/SYNTHETIC_ONLY.csv": b"SYNTHETIC_UNPROVEN\n"})
        g.commit({"data/SYNTHETIC_ONLY.csv": None})
        negatives["deleted_intermediate_data"] = g.check()
    with graph() as g:
        changes = {
            gate.MANIFEST: b'{"APPROVED":true}\n',
            "tools/verify_public_core.py": b'print("PASS")\n',
            ".github/workflows/self.yml": b"permissions: write-all\n",
            CODE_PATH: CODE,
        }
        g.commit(changes)
        negatives["self_approval"] = g.check()
    bundle = synthetic_bundle_case()
    checkout = checkout_case()
    independent = independent_processes(output / "processes")
    ci = ci_equivalent(output / "ci")
    reports = {
        "public-core-v2-trust-boundary.json": {
            "trusted_root": gate.V1_ROOT,
            "trusted_v1_manifest_sha256": gate.V1_MANIFEST_SHA256,
            "authority_kind": gate.AUTHORITY_KIND,
            "trust_origin": "EXTERNAL_TO_PROPOSED_REPOSITORY_CALLER_PINNED_SYNTHETIC_INTENT",
            "real_remote_authorization": "UNVERIFIED",
            "publication_authorized": False,
            "v1_preserved": True,
        },
        "public-core-v2-commit-graph-validation.json": life,
        "public-core-v2-pr-review-matrix.json": {
            "lifecycle": life,
            "synthetic_bundle": bundle,
            "checkout": checkout,
        },
        "public-core-v2-negative-tests.json": {
            "cases": negatives,
            "independent_processes": independent,
        },
        "public-core-v2-ci-equivalence.json": ci,
    }
    for name, report in reports.items():
        file = output / name
        file.write_bytes(gate.canonical(report))
        file.chmod(0o600)
    success = (
        all(r["status"] == "BLOCKED" for r in negatives.values())
        and all(
            gate._dict(life[k])["status"] == "PASS"
            for k in ("first_reviewed", "first_merged", "second_reviewed", "second_merged")
        )
        and independent["equal"]
        and independent["independent_graph_results_equal"]
        and gate._dict(life["first_unreviewed"])["status"] == "REVIEW_REQUIRED"
        and gate._dict(bundle["valid"])["status"] == "PASS"
        and gate._dict(bundle["changed_bytes"])["status"] == "BLOCKED"
        and gate._dict(bundle["wrong_producer"])["status"] == "BLOCKED"
        and gate._dict(checkout["valid"])["status"] == "PASS"
        and gate._dict(checkout["wrong_checkout"])["status"] == "BLOCKED"
        and gate._dict(checkout["untrusted_origin"])["status"] == "BLOCKED"
        and ci["status"] == "PASS"
    )
    return {
        "status": "PASS" if success else "FAIL",
        "scenario_count": len(negatives),
        "actual_new_remote_github_actions": "NOT_RUN",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--graph-only", action="store_true")
    args = parser.parse_args()
    if args.graph_only:
        print(gate.canonical(lifecycle()).decode(), end="")
        return
    if args.output_dir is None:
        parser.error("--output-dir is required")
    result = rehearse(args.output_dir)
    print(gate.canonical(result).decode(), end="")
    raise SystemExit(0 if result["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
