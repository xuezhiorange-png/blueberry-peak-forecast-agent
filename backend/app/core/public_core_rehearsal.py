"""TD01G assembler: exact approved bytes into an owned, parentless public root.

The original project is only the source of reviewed code and verified artificial
samples. Neither its environment nor its history is an input to the public core.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from backend.app.core import clean_public_repository as previous
from backend.app.core import historical_code_identity as history

ROOT = Path(__file__).resolve().parents[3]
CATALOG = ROOT / "docs/tech-debt/td01g-public-core-candidates-r1.json"
CATALOG_SHA256 = "b502c44d3ce4c166ed71fb04f3f1b66a788c6babe27d9a1aaa2506af4fe78ea1"


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def catalog() -> list[dict[str, str]]:
    raw = CATALOG.read_bytes()
    if hashlib.sha256(raw).hexdigest() != CATALOG_SHA256:
        raise AssertionError("TD01G_CATALOG_SEAL_MISMATCH")
    payload = json.loads(raw)
    seen = set()
    for row in payload["entries"]:
        for field in ("repository_relative_path", "public_path"):
            previous._safe_path(row[field])
        previous._oid(row["git_blob_oid"])
        if row["git_blob_oid"] in previous.BLOCKED_BLOBS:
            raise AssertionError("BLOCKED_BUSINESS_SOURCE_IDENTITY")
        if row["public_path"] in seen:
            raise AssertionError("DUPLICATE_PUBLIC_CORE_PATH")
        seen.add(row["public_path"])
        if row["class"] not in {
            "TD01F_VERIFIED_REUSE",
            "TD01G_REVIEWED_CODE",
            "TD01G_BUILD_METADATA",
            "TD01G_WORKFLOW_TEMPLATE",
        }:
            raise AssertionError("UNREVIEWED_PUBLIC_CORE_SOURCE")
    result: list[dict[str, str]] = payload["entries"]
    return result


def _read(source: Path, row: dict[str, str], generated: dict[str, bytes]) -> bytes:
    path = row["repository_relative_path"]
    if row["class"] == "TD01F_VERIFIED_REUSE":
        old = previous.candidates().get(path)
        if (
            old is None
            or old["git_blob_oid"] != row["git_blob_oid"]
            or old["sha256"] != row["sha256"]
        ):
            raise AssertionError("TD01F_REUSE_IDENTITY_CHANGED")
        return previous.candidate_bytes(source, path, generated=generated.get(Path(path).name))
    if path != "backend/app/public_core.py" and not path.startswith("public_core/td01g_v1/"):
        raise AssertionError("NEW_SOURCE_REQUIRES_EXPLICIT_REVIEW")
    oid, _ = previous._metadata(source, path)
    if oid != row["git_blob_oid"]:
        raise AssertionError("NEW_PUBLIC_SOURCE_HEAD_CHANGED")
    raw = history._git(source, "cat-file", "blob", oid)
    if history._blob_id(raw) != oid or hashlib.sha256(raw).hexdigest() != row["sha256"]:
        raise AssertionError("NEW_PUBLIC_SOURCE_BYTES_CHANGED")
    return raw


def materialize(repo: Path, source: Path = ROOT) -> dict[str, object]:
    previous._owned(repo)
    rows = catalog()
    # First verify the exact frozen producer closure, before importing it.
    for path, row in previous.candidates().items():
        if (
            row["role"] == "GENERIC_CODE"
            and path.startswith("backend/app/etl/")
            or path in {"backend/__init__.py", "backend/app/__init__.py"}
        ):
            raw = previous.candidate_bytes(source, path)
            if (source / path).read_bytes() != raw:
                raise AssertionError("UNVERIFIED_SYNTHETIC_PRODUCER")
    from backend.app.etl.history.synthetic_publication import export, generate

    with tempfile.TemporaryDirectory(prefix="TD01G_GENERATED_ONLY_") as directory:
        destination = Path(directory) / "generated"
        export(generate(41), destination)
        generated = {p.name: p.read_bytes() for p in destination.iterdir()}
    content = {r["public_path"]: _read(source, r, generated) for r in rows}
    manifest = {
        "schema": "TD01G_PUBLIC_CORE_V1",
        "DATA_CLASS": "SYNTHETIC_ONLY",
        "publication_authorized": False,
        "files": [
            {
                "path": r["public_path"],
                "sha256": r["sha256"],
                "git_blob_oid": r["git_blob_oid"],
                "normalization": "GUARD_MANIFEST_SEAL_LITERAL"
                if r["public_path"] == "tools/verify_public_core.py"
                else "EXACT_BYTES",
            }
            for r in rows
        ],
    }
    manifest_raw = canonical(manifest)
    seal = hashlib.sha256(manifest_raw).hexdigest()
    name = "tools/verify_public_core.py"
    marker = b'\nAPPROVED_MANIFEST_SHA256 = "__MANIFEST_SEAL__"\n'
    if content[name].count(marker) != 1:
        raise AssertionError("INVALID_REVIEWED_GUARD_TEMPLATE")
    content[name] = content[name].replace(
        marker, f'\nAPPROVED_MANIFEST_SHA256 = "{seal}"\n'.encode(), 1
    )
    content["PUBLIC-CORE-MANIFEST.json"] = manifest_raw
    for name, raw in content.items():
        file = repo / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(raw)
        file.chmod(0o600)
        oid = previous._write_git(repo, "hash-object", "-w", "--stdin", data=raw).decode().strip()
        previous._write_git(repo, "update-index", "--add", "--cacheinfo", f"100644,{oid},{name}")
    tree = previous._write_git(repo, "write-tree").decode().strip()
    commit = (
        previous._write_git(repo, "commit-tree", tree, data=b"TD01G SYNTHETIC PUBLIC CORE ROOT\n")
        .decode()
        .strip()
    )
    previous._write_git(repo, "update-ref", "refs/heads/main", commit)
    run = subprocess.run(
        [sys.executable, "-I", "-B", str(repo / "tools/verify_public_core.py")],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    proof = json.loads(run.stdout)
    return {
        "source_head": history._git(source, "rev-parse", "HEAD").decode().strip(),
        "catalog_sha256": CATALOG_SHA256,
        "public_manifest_sha256": seal,
        "root_commit": commit,
        "git_objects": proof,
        "historical_td01f_result_preserved": {
            "passed": 24,
            "blocked": 1,
            "test": "test_path_only_audit_registry_and_original_ref_inventory_are_bound",
            "status": "BLOCKED_HISTORICAL_AUDIT_SCOPE_UNCHANGED",
        },
        "new_scope": "TD01G_PUBLIC_CORE_V1_SEPARATE_ACCEPTANCE",
    }


def rehearse(output: Path) -> dict[str, object]:
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    result: dict[str, object] = {"status": "RUNNING"}
    try:
        with previous.owned_repository() as repo:
            result["assembly"] = materialize(repo)
            env = {
                k: v
                for k, v in os.environ.items()
                if not k.startswith(("GIT_", "PYTHON", "PYTEST", "PIP_"))
            }
            env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
            run = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "tools.run_public_ci",
                    "--output-dir",
                    str(output / "public-ci"),
                ],
                cwd=repo,
                env=env,
                capture_output=True,
                check=False,
            )
            (output / "runner.stdout.log").write_bytes(run.stdout)
            (output / "runner.stderr.log").write_bytes(run.stderr)
            result["runner_exit_code"] = run.returncode
            if run.returncode:
                raise RuntimeError("INDEPENDENT_PUBLIC_CORE_VALIDATION_FAILED")
            result["public_ci"] = json.loads((output / "public-ci/summary.json").read_bytes())
            result["status"] = "PASS"
    except BaseException:
        result["status"] = "FAIL"
        raise
    finally:
        file = output / "rehearsal.json"
        file.write_bytes(canonical(result))
        file.chmod(0o600)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = rehearse(args.output_dir.resolve())
    print(
        json.dumps(
            {
                "LOCAL_CI_EQUIVALENT": result["status"],
                "ACTUAL_NEW_REMOTE_GITHUB_ACTIONS": "NOT_RUN",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
