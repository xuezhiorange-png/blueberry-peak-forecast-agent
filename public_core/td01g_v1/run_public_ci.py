"""The same bounded command sequence used locally and by the public CI template."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import subprocess
import sys
import venv
from pathlib import Path

from tools.verify_public_core import verify

ROOT = Path(__file__).resolve().parents[1]


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def closure(root: Path) -> dict[str, object]:
    local = {}
    third_party = set()
    standard = set()
    runtime_third_party = set()
    for file in sorted(
        p for folder in ("backend", "tools", "tests") for p in (root / folder).rglob("*.py")
    ):
        imports = set()
        for node in ast.walk(ast.parse(file.read_bytes())):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.level:
                    raise AssertionError("UNRESOLVED_RELATIVE_IMPORT")
                imports.add(node.module)
                if node.module.split(".")[0] in {"backend", "tools"}:
                    for alias in node.names:
                        child = node.module + "." + alias.name
                        if (root / child.replace(".", "/")).with_suffix(".py").is_file():
                            imports.add(child)
        for name in imports:
            top = name.split(".")[0]
            if top in {"backend", "tools"}:
                path = root / name.replace(".", "/")
                if not path.with_suffix(".py").is_file() and not (path / "__init__.py").is_file():
                    raise AssertionError("UNREVIEWED_LOCAL_IMPORT")
            elif top in sys.stdlib_module_names:
                standard.add(top)
            else:
                third_party.add(top)
                if file.is_relative_to(root / "backend"):
                    runtime_third_party.add(top)
        local[str(file.relative_to(root))] = sorted(imports)
    if runtime_third_party != {"openpyxl", "xlrd"} or third_party != {"pytest", "openpyxl", "xlrd"}:
        raise AssertionError("UNDECLARED_RUNTIME_DEPENDENCY")
    return {
        "local_imports": local,
        "stdlib_roots": sorted(standard),
        "third_party_runtime": sorted(runtime_third_party),
        "third_party_test": ["pytest", "openpyxl"],
        "explicit_tools": ["pip", "setuptools", "wheel", "pytest", "mypy", "ruff"],
        "runtime_private_configuration_required": False,
        "historical_git_identity_required": False,
        "private_data_required": False,
        "entry_points": [
            "backend.app.public_core:generate",
            "backend.app.public_core:curve",
            "backend.app.public_core:execute",
        ],
        "tests_and_tools": "EXPLICIT_FILES_IN_PUBLIC_MANIFEST",
    }


def execute(output: Path) -> dict[str, object]:
    if sys.version_info[:2] != (3, 12):
        raise AssertionError("PYTHON_312_REQUIRED")
    if output.resolve().is_relative_to(ROOT.resolve()):
        raise AssertionError("EVIDENCE_MUST_BE_OUTSIDE_SOURCE_CHECKOUT")
    proof = verify(ROOT)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("PYTHON", "PYTEST", "PIP_", "GIT_"))
    }
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1", APP_ENV="test")
    results: dict[str, object] = {}
    summary: dict[str, object] = {
        "schema": "TD01G_PUBLIC_CI_V1",
        "status": "RUNNING",
        "actual_new_remote_github_actions": "NOT_RUN",
        "git_object_verification": proof,
        "commands": results,
    }

    def run(name: str, command: list[str], *, cwd: Path = ROOT) -> bytes:
        proc = subprocess.run(command, cwd=cwd, env=env, capture_output=True, check=False)
        for suffix, raw in (("stdout", proc.stdout), ("stderr", proc.stderr)):
            path = output / f"{name}.{suffix}.log"
            path.write_bytes(raw)
            path.chmod(0o600)
        results[name] = {
            "exit_code": proc.returncode,
            "stdout_sha256": hashlib.sha256(proc.stdout).hexdigest(),
            "stderr_sha256": hashlib.sha256(proc.stderr).hexdigest(),
        }
        if proc.returncode:
            raise RuntimeError("PUBLIC_CI_COMMAND_FAILED:" + name)
        return proc.stdout

    try:
        environment = output / "environment"
        venv.EnvBuilder(with_pip=True, system_site_packages=False, symlinks=True).create(
            environment
        )
        cfg = (environment / "pyvenv.cfg").read_text()
        if "include-system-site-packages = false" not in cfg:
            raise AssertionError("ISOLATED_ENVIRONMENT_REQUIRED")
        python = environment / "bin/python"
        summary["isolated_install"] = {
            "system_site_packages": False,
            "python": sys.version.split()[0],
        }
        run(
            "install-locked",
            [
                str(python),
                "-I",
                "-B",
                "-m",
                "pip",
                "--isolated",
                "install",
                "--no-cache-dir",
                "--require-hashes",
                "--only-binary=:all:",
                "--report",
                str(output / "installation.json"),
                "-r",
                str(ROOT / "requirements.lock"),
            ],
        )
        archive = output / "public-core.tar"
        archive.write_bytes(run("source-archive", ["git", "archive", "--format=tar", "HEAD"]))
        # Installing the archive makes pip build in its own temp directory,
        # rather than leaving egg-info/build products in the verified checkout.
        run(
            "install-project",
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
                str(archive),
            ],
        )
        run("pip-check", [str(python), "-I", "-B", "-m", "pip", "--isolated", "check"])
        probe = """import importlib.metadata as m,json,sys
from pathlib import Path
import backend.app.public_core, openpyxl, xlrd
for package in (openpyxl, xlrd):
    assert Path(package.__file__).resolve().is_relative_to(Path(sys.prefix))
local={n:str(Path(v.__file__).resolve().is_relative_to(Path(sys.prefix)))
       for n,v in sys.modules.items() if n.startswith("backend") and getattr(v,"__file__",None)}
assert local and all(v=="True" for v in local.values())
print(json.dumps({"local_modules":sorted(local),"all_local_modules_installed_in_owned_venv":True,
                  "packages":{d.metadata["Name"]:d.version
                              for d in m.distributions()}},sort_keys=True))"""
        runtime = json.loads(
            run("installed-imports", [str(python), "-I", "-B", "-c", probe], cwd=output)
        )
        summary["installed_imports"] = runtime
        summary["import_closure"] = closure(ROOT)
        run(
            "ruff",
            [
                str(python),
                "-I",
                "-B",
                "-m",
                "ruff",
                "check",
                "--no-cache",
                "backend",
                "tests",
                "tools",
            ],
        )
        run(
            "format",
            [
                str(python),
                "-I",
                "-B",
                "-m",
                "ruff",
                "format",
                "--check",
                "--no-cache",
                "backend",
                "tests",
                "tools",
            ],
        )
        run(
            "strict-mypy",
            [
                str(python),
                "-I",
                "-B",
                "-m",
                "mypy",
                "--cache-dir",
                str(output / "mypy-cache"),
                "backend/app",
                "backend/research",
                "tools",
            ],
        )
        run(
            "public-contracts",
            [
                str(python),
                "-I",
                "-B",
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                "--junitxml=" + str(output / "public-contracts.xml"),
                "tests",
            ],
        )
        for n in (1, 2):
            run(
                "installed-demo-" + str(n),
                [
                    str(python),
                    "-I",
                    "-B",
                    "-m",
                    "backend.app.public_core",
                    "demo",
                    "--seed",
                    "41",
                    "--output-dir",
                    str(output / f"demo-{n}"),
                ],
                cwd=output,
            )
        hashes = []
        for n in (1, 2):
            hashes.append(
                {
                    p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in (output / f"demo-{n}").iterdir()
                }
            )
        if hashes[0] != hashes[1]:
            raise AssertionError("INDEPENDENT_PROCESS_OUTPUT_MISMATCH")
        summary["deterministic_report_sha256"] = hashes[0]
        summary["git_object_verification_after"] = verify(ROOT)
        summary["status"] = "PASS"
    except BaseException:
        summary["status"] = "FAIL"
        raise
    finally:
        (output / "summary.json").write_bytes(canonical(summary))
        (output / "summary.json").chmod(0o600)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = execute(args.output_dir.resolve())
    print(
        json.dumps(
            {
                "LOCAL_CI_EQUIVALENT": report["status"],
                "ACTUAL_NEW_REMOTE_GITHUB_ACTIONS": "NOT_RUN",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
