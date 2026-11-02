"""Trusted-base V2 runner. Gate first; baseline 38 and active-HEAD tests differ.

This file must be executed from the protected Base, never from proposed Head.
Remote review integration is not implemented. External synthetic authority is
accepted only by the explicit local rehearsal interface.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree

V1_ROOT = "04457546f5577d4e44effb808154a6aa08b45846"
DATA_PREFIX = "docs/tech-debt/td01c-synthetic-example/"


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def execute(args: argparse.Namespace) -> dict[str, object]:
    repo = Path(args.repository).resolve()
    output = Path(args.output_dir).absolute()
    gate = Path(args.gate_script).resolve()
    security = Path(args.security_test).resolve()
    if output.exists() or output.is_symlink() or output.resolve().is_relative_to(repo):
        raise ValueError("NEW_EXTERNAL_EVIDENCE_DIRECTORY_REQUIRED")
    output.mkdir(mode=0o700, parents=True)
    result: dict[str, object] = {
        "status": "RUNNING",
        "actual_new_remote_github_actions": "NOT_RUN",
        "executor_origin_base": args.executor_origin_base,
    }
    commands: dict[str, object] = {}
    result["commands"] = commands
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("GIT_", "PYTHON", "PYTEST", "PIP_", "TD01I_"))
        and not k.startswith(("POSTGRES_", "LOCAL_AUTH_", "BUSINESS_ACCESS_", "AWS_", "AZURE_"))
        and k != "DATABASE_URL"
        and not any(part in k.upper() for part in ("TOKEN", "PASSWORD", "SECRET", "COOKIE"))
    }
    env.update(
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONNOUSERSITE="1",
        APP_ENV="test",
        GIT_NO_LAZY_FETCH="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_NOSYSTEM="1",
        GIT_TERMINAL_PROMPT="0",
    )

    def run(
        name: str,
        command: list[str],
        cwd: Path,
        *,
        data: bytes | None = None,
        allow_review: bool = False,
    ) -> bytes:
        p = subprocess.run(command, cwd=cwd, env=env, input=data, capture_output=True, check=False)
        for suffix, raw in (("stdout", p.stdout), ("stderr", p.stderr)):
            f = output / f"{name}.{suffix}.log"
            f.write_bytes(raw)
            f.chmod(0o600)
        commands[name] = {
            "exit_code": p.returncode,
            "stdout_sha256": hashlib.sha256(p.stdout).hexdigest(),
            "stderr_sha256": hashlib.sha256(p.stderr).hexdigest(),
        }
        if p.returncode and not allow_review:
            raise ValueError("PUBLIC_V2_COMMAND_FAILED_" + name.upper())
        return p.stdout

    def git(name: str, root: Path, *parts: str, data: bytes | None = None) -> bytes:
        return run(
            name,
            ["git", "--no-replace-objects", "-c", "protocol.allow=never", *parts],
            root,
            data=data,
        )

    def verified_archive(name: str, revision: str) -> tuple[bytes, dict[str, bytes]]:
        entries = {}
        for row in git(name + "-tree", repo, "ls-tree", "-r", "-z", revision).split(b"\0"):
            if row:
                metadata, raw_path = row.split(b"\t", 1)
                mode, kind, identity = metadata.decode().split()
                if mode != "100644" or kind != "blob":
                    raise ValueError("INVALID_VERIFIED_ARCHIVE_MODE")
                entries[raw_path.decode()] = identity
        raw = git(name, repo, "archive", "--format=tar", revision)
        files = {}
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
            for member in archive.getmembers():
                path = PurePosixPath(member.name)
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError("INVALID_VERIFIED_ROOT_ARCHIVE")
                if member.isdir():
                    continue
                if not member.isfile() or member.size > 2 * 1024 * 1024 or member.name in files:
                    raise ValueError("INVALID_VERIFIED_ROOT_ARCHIVE")
                stream = archive.extractfile(member)
                if stream is None:
                    raise ValueError("INVALID_VERIFIED_ROOT_ARCHIVE")
                body = stream.read()
                identity = hashlib.sha1(
                    b"blob " + str(len(body)).encode() + b"\0" + body
                ).hexdigest()
                if entries.get(member.name) != identity:
                    raise ValueError("ARCHIVE_NOT_EXACT_GIT_TREE")
                files[member.name] = body
        if set(entries) != set(files):
            raise ValueError("ARCHIVE_NOT_EXACT_GIT_TREE")
        return raw, files

    try:
        if gate.is_relative_to(repo) or security.is_relative_to(repo):
            raise ValueError("PROPOSED_HEAD_IS_NOT_TRUSTED_EXECUTOR")
        if (
            hashlib.sha256(gate.read_bytes()).hexdigest() != args.gate_sha256
            or hashlib.sha256(security.read_bytes()).hexdigest() != args.security_test_sha256
        ):
            raise ValueError("TRUSTED_EXECUTOR_IDENTITY_MISMATCH")
        gate_command = [
            sys.executable,
            "-I",
            "-B",
            str(gate),
            "--repository",
            str(repo),
            "--context",
            str(args.context),
        ]
        if args.synthetic_review_authority:
            gate_command += [
                "--synthetic-review-authority",
                str(args.synthetic_review_authority),
                "--independent-authority-sha256",
                args.independent_authority_sha256 or "",
            ]
        report = json.loads(run("trusted-base-gate", gate_command, output, allow_review=True))
        result["gate"] = report
        if report["status"] != "PASS":
            result["status"] = report["status"]
            return result
        if args.executor_origin_base not in {report["trusted_base"], "SYNTHETIC_BOOTSTRAP_HOST"}:
            raise ValueError("TRUSTED_EXECUTOR_BASE_MISMATCH")
        if report["checkout"] not in {report["proposed_head"], report["test_merge"]}:
            raise ValueError("ACTIVE_CHECKOUT_IS_NOT_PROPOSED_HEAD_OR_TEST_MERGE")
        revision = str(report["checkout"])
        result["tested_checkout"] = revision
        # Only now may proposed code enter an interpreter/build backend.
        # Reconstruct precisely the original 28-file root, not a mirror/fetch.
        baseline = output / "v1-root"
        baseline.mkdir(mode=0o700)
        _, baseline_files = verified_archive("archive-v1", V1_ROOT)
        for name, body in baseline_files.items():
            destination = baseline / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(body)
            destination.chmod(0o600)
        if len(baseline_files) != 28:
            raise ValueError("V1_BASELINE_SCOPE_CHANGED")
        git(
            "init-baseline",
            baseline,
            "init",
            "-q",
            "--template=",
            "--object-format=sha1",
            "-b",
            "main",
        )
        git("index-baseline", baseline, "add", ".")
        git("tree-baseline", baseline, "write-tree")
        root_bytes = git("root-metadata", repo, "cat-file", "commit", V1_ROOT)
        written = (
            git(
                "root-baseline",
                baseline,
                "hash-object",
                "-w",
                "-t",
                "commit",
                "--stdin",
                data=root_bytes,
            )
            .decode()
            .strip()
        )
        if written != V1_ROOT:
            raise ValueError("V1_ROOT_IDENTITY_CHANGED")
        git("ref-baseline", baseline, "update-ref", "refs/heads/main", V1_ROOT)
        run(
            "v1-independent-ci",
            [
                sys.executable,
                "-I",
                "-B",
                str(baseline / "tools/run_public_ci.py"),
                "--output-dir",
                str(output / "v1-ci"),
            ],
            baseline,
        )
        original = json.loads((output / "v1-ci/summary.json").read_bytes())
        if original["status"] != "PASS" or original["isolated_install"]["system_site_packages"]:
            raise ValueError("V1_INDEPENDENT_INSTALL_FAILED")
        cases = list(
            ElementTree.parse(output / "v1-ci/public-contracts.xml").getroot().iter("testcase")
        )
        if len(cases) != 38 or any(
            c.find(k) is not None for c in cases for k in ("failure", "error", "skipped")
        ):
            raise ValueError("V1_38_CONTRACTS_CHANGED")
        result["v1_public_tests"] = 38
        result["v1_independent_ci"] = original
        python = output / "v1-ci/environment/bin/python"
        candidate_archive = output / "proposed-head.tar"
        archive, proposed_files = verified_archive("archive-proposed", revision)
        candidate_archive.write_bytes(archive)
        head_source = output / "pinned-head-source"
        head_source.mkdir(mode=0o700)
        for name, raw in proposed_files.items():
            destination = head_source / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
            destination.chmod(0o600)
        result["pinned_head_source_sha256"] = hashlib.sha256(
            canonical(
                {p: hashlib.sha256(raw).hexdigest() for p, raw in sorted(proposed_files.items())}
            )
        ).hexdigest()
        run(
            "install-active-head",
            [
                str(python),
                "-I",
                "-B",
                "-m",
                "pip",
                "--isolated",
                "install",
                "--no-deps",
                "--no-build-isolation",
                "--force-reinstall",
                str(candidate_archive),
            ],
            output,
        )
        run(
            "active-head-pip-check",
            [str(python), "-I", "-B", "-m", "pip", "--isolated", "check"],
            output,
        )
        expected_sources = output / "installed-source-identities.json"
        expected_sources.write_bytes(
            canonical(
                {
                    p: hashlib.sha256(raw).hexdigest()
                    for p, raw in proposed_files.items()
                    if p.startswith("backend/") and p.endswith(".py")
                }
            )
        )
        installed_probe = """import hashlib,importlib,importlib.metadata,json,sys
from pathlib import Path
root=Path(sys.prefix)
import backend.app.public_core
assert Path(backend.app.public_core.__file__).resolve().is_relative_to(root)
package_root=Path(importlib.import_module('backend').__file__).resolve().parents[1]
expected=json.loads(Path(sys.argv[1]).read_bytes())
for relative,sha in expected.items():
    source=(package_root/relative).resolve()
    assert source.is_relative_to(root) and hashlib.sha256(source.read_bytes()).hexdigest()==sha
packages={d.metadata['Name']:d.version for d in importlib.metadata.distributions()}
print(json.dumps({'installed_inside_owned_venv':True,'packages':packages,
                  'exact_head_sources':len(expected)},sort_keys=True))"""
        installed = json.loads(
            run(
                "active-head-installed-imports",
                [str(python), "-I", "-B", "-c", installed_probe, str(expected_sources)],
                output,
            )
        )
        if installed["packages"] != original["installed_imports"]["packages"]:
            raise ValueError("ACTIVE_HEAD_DEPENDENCY_CLOSURE_CHANGED")
        result["active_head_installed_imports"] = installed
        for name, command in (
            ("head-ruff", ["ruff", "check", "--no-cache", "backend", "tests", "tools"]),
            (
                "head-format",
                ["ruff", "format", "--check", "--no-cache", "backend", "tests", "tools"],
            ),
            (
                "head-strict-mypy",
                [
                    "mypy",
                    "--cache-dir",
                    str(output / "head-mypy-cache"),
                    "backend/app",
                    "backend/research",
                    "tools",
                ],
            ),
        ):
            run(name, [str(python), "-I", "-B", "-m", *command], head_source)
        # Original functional assertions execute against the installed Head.
        # The unchanged V1 safety tests above retain their single-root semantics.
        fixture = output / "active-head-contracts"
        tests = fixture / "tests"
        tests.mkdir(parents=True)
        (tests / "test_public_contract.py").write_bytes(
            (baseline / "tests/test_public_contract.py").read_bytes()
        )
        ini = fixture / "pytest.ini"
        ini.write_text("[pytest]\n")
        for file in (baseline / DATA_PREFIX).iterdir():
            destination = fixture / DATA_PREFIX / file.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(proposed_files[DATA_PREFIX + file.name])
        run(
            "active-head-functional-contracts",
            [
                str(python),
                "-I",
                "-B",
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                "-c",
                str(ini),
                "--junitxml=" + str(output / "active-head-functional.xml"),
                str(tests / "test_public_contract.py"),
            ],
            fixture,
        )
        cases = list(
            ElementTree.parse(output / "active-head-functional.xml").getroot().iter("testcase")
        )
        if len(cases) != 24 or any(
            c.find(k) is not None for c in cases for k in ("failure", "error", "skipped")
        ):
            raise ValueError("ACTIVE_HEAD_FUNCTIONAL_CONTRACT_FAILED")
        result["active_head_functional_tests"] = 24
        security_fixture = tests / "test_v2_security.py"
        security_fixture.write_bytes(security.read_bytes())
        env.update(
            TD01I_TRUSTED_GATE=str(gate),
            TD01I_TRUSTED_GATE_SHA256=args.gate_sha256,
            TD01I_V1_FIXTURE=str(baseline),
        )
        run(
            "v2-security-contracts",
            [
                str(python),
                "-I",
                "-B",
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                "-c",
                str(ini),
                "--junitxml=" + str(output / "v2-security.xml"),
                str(security_fixture),
            ],
            fixture,
        )
        cases = list(ElementTree.parse(output / "v2-security.xml").getroot().iter("testcase"))
        if len(cases) != 15 or any(
            c.find(k) is not None for c in cases for k in ("failure", "error", "skipped")
        ):
            raise ValueError("V2_SECURITY_CONTRACT_FAILED")
        result["v2_security_tests"] = len(cases)
        # Also run reviewed Head tests. Their conftest/edits cannot replace the
        # separate, already executed fixed functional and trusted safety suites.
        head_tests = output / "reviewed-head-tests"
        head_tests.mkdir()
        selected = {
            path: raw
            for path, raw in proposed_files.items()
            if path.startswith("tests/")
            and path.endswith(".py")
            and path not in {"tests/test_public_contract.py", "tests/test_public_safety.py"}
        }
        for path, raw in selected.items():
            destination = head_tests / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
        if not selected:
            raise ValueError("REVIEWED_HEAD_TESTS_REQUIRED")
        active_gate = head_source / "tools/public_core_incremental_gate.py"
        if active_gate.is_file():
            env.update(
                TD01I_TRUSTED_GATE=str(active_gate),
                TD01I_TRUSTED_GATE_SHA256=hashlib.sha256(active_gate.read_bytes()).hexdigest(),
            )
        run(
            "reviewed-head-tests",
            [
                str(python),
                "-I",
                "-B",
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                "-c",
                str(ini),
                "--junitxml=" + str(output / "reviewed-head-tests.xml"),
                str(head_tests),
            ],
            head_tests,
        )
        cases = list(
            ElementTree.parse(output / "reviewed-head-tests.xml").getroot().iter("testcase")
        )
        if not cases or any(
            c.find(k) is not None for c in cases for k in ("failure", "error", "skipped")
        ):
            raise ValueError("REVIEWED_HEAD_TESTS_FAILED")
        result["reviewed_head_tests"] = len(cases)
        final = json.loads(run("gate-after-tests", gate_command, output))
        if final != report:
            raise ValueError("PROPOSED_GRAPH_CHANGED_DURING_CI")
        result["gate_after_tests"] = final
        result["status"] = "PASS"
        return result
    except BaseException:
        result["status"] = "FAIL"
        raise
    finally:
        file = output / "summary.json"
        file.write_bytes(canonical(result))
        file.chmod(0o600)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--gate-script", type=Path, required=True)
    parser.add_argument("--gate-sha256", required=True)
    parser.add_argument("--security-test", type=Path, required=True)
    parser.add_argument("--security-test-sha256", required=True)
    parser.add_argument("--synthetic-review-authority", type=Path)
    parser.add_argument("--independent-authority-sha256")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--executor-origin-base", required=True)
    try:
        report = execute(parser.parse_args())
    except Exception as error:
        reason = str(error) if isinstance(error, ValueError) else "V2_CI_EXECUTION_FAILED"
        if not reason or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789-" for c in reason):
            reason = "V2_CI_EXECUTION_FAILED"
        print(canonical({"status": "FAIL", "reason": reason}).decode(), end="")
        raise SystemExit(2) from None
    print(
        canonical(
            {"status": report["status"], "actual_new_remote_github_actions": "NOT_RUN"}
        ).decode(),
        end="",
    )
    raise SystemExit(
        0 if report["status"] == "PASS" else 3 if report["status"] == "REVIEW_REQUIRED" else 2
    )


if __name__ == "__main__":
    main()
