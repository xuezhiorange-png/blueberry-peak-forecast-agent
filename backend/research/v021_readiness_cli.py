"""V0_21 S4 offline CLI: explicit synthetic catalog to four new report files."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import Field

from backend.research import v021_cycle_features as cycle
from backend.research import v021_readiness_report as report

ROOT = Path(__file__).resolve().parents[2]
GIT = ["git", "-c", "protocol.allow=never"]
MODULES = (
    "backend/research/v021_cycle_features.py",
    "backend/research/v021_structure_scenarios.py",
    "backend/research/v021_evaluation_readiness.py",
    "backend/research/v021_readiness_report.py",
    "backend/research/v021_readiness_cli.py",
)
LEGACY_SOURCES = (
    "backend/research/v019_synthetic_validation.py",
    "backend/research/v019_research_evaluation.py",
)


class Reference(cycle.Contract):
    path: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


Role = Literal["package", "cycles", "structure", "protocol", "predictions", "labels"]


class Dataset(report.Case):
    inputs: dict[Role, Reference]


class Catalog(cycle.Contract):
    schema_version: Literal["V0_21_S4_CATALOG_R1"]
    data_class: Literal["SYNTHETIC_TEST_FIXTURE"]
    title: str = Field(max_length=1000)
    as_of: str
    datasets: list[Dataset] = Field(min_length=1, max_length=64)
    evidence: Reference | None


def _read_json(path: Path) -> tuple[report.Record, str]:
    """Hash and parse the same bounded bytes, never a second file read."""
    if path.is_symlink() or not path.is_file():
        raise ValueError("EXPLICIT_INPUT_PATH_OR_SIZE_INVALID")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as stream:
            raw = stream.read(cycle.MAX_BYTES + 1)
    except OSError as exc:
        raise ValueError("EXPLICIT_INPUT_PATH_OR_SIZE_INVALID") from exc
    if len(raw) > cycle.MAX_BYTES:
        raise ValueError("EXPLICIT_INPUT_PATH_OR_SIZE_INVALID")

    def pairs(items: list[tuple[str, Any]]) -> report.Record:
        result: report.Record = {}
        for key, value in items:
            if key in result:
                raise ValueError("DUPLICATE_JSON_KEY")
            result[key] = value
        return result

    def reject(_: str) -> None:
        raise ValueError("DECIMAL_STRING_REQUIRED")

    value = json.loads(raw, object_pairs_hook=pairs, parse_float=reject, parse_constant=reject)
    if not isinstance(value, dict):
        raise ValueError("JSON_OBJECT_REQUIRED")
    return value, hashlib.sha256(raw).hexdigest()


def _path(root: Path, relative: str) -> Path:
    value = PurePosixPath(relative)
    if value.is_absolute() or any(p in {".", ".."} for p in value.parts) or "\\" in relative:
        raise ValueError("EXPLICIT_CONTAINED_INPUT_REQUIRED")
    path = root
    for part in value.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("SYMLINK_INPUT_REJECTED")
    if not path.is_file() or path.stat().st_size > cycle.MAX_BYTES:
        raise ValueError("EXPLICIT_INPUT_PATH_OR_SIZE_INVALID")
    return path


def _verify_public_evidence(value: report.Record) -> None:
    if (
        value.get("schema_version") != "V0_21_S4_EVIDENCE_R1"
        or value.get("source_class") != "PUBLIC_REPOSITORY_METADATA"
    ):
        raise ValueError("PUBLIC_EVIDENCE_SCHEMA_REQUIRED")
    import re

    base = value.get("base_main_sha", "")
    if not re.fullmatch(r"[0-9a-f]{40}", base):
        raise ValueError("PINNED_GIT_IDENTITY_REQUIRED")
    refs = value.get("frozen_source_refs", [])
    required = set(MODULES[:3]) | {"docs/v0-21/evidence/v0.21-s0-scope.json"}
    if not required <= {r.get("path") for r in refs}:
        raise ValueError("FROZEN_STAGE_SOURCE_REFS_MISSING")
    stages = value.get("predecessors", [])
    if len(stages) != 4 or {s.get("stage") for s in stages} != {"S0", "S1", "S2", "S3"}:
        raise ValueError("PREDECESSOR_EVIDENCE_INCOMPLETE")
    for ref in value.get("frozen_source_refs", []):
        commit, path = ref["commit"], ref["path"]
        if (
            not re.fullmatch(r"[0-9a-f]{40}", commit)
            or (
                path not in LEGACY_SOURCES
                and not path.startswith(
                    (
                        "docs/v0-21/",
                        "backend/research/v021_",
                        "backend/tests/agronomic_history/v0_21_",
                    )
                )
            )
            or any(p in {".", ".."} for p in PurePosixPath(path).parts)
        ):
            raise ValueError("PINNED_PUBLIC_SOURCE_REQUIRED")
        try:
            raw = subprocess.check_output(
                [*GIT, "show", commit + ":" + path], cwd=ROOT, stderr=subprocess.DEVNULL
            )
            subprocess.run(
                [*GIT, "merge-base", "--is-ancestor", commit, base],
                cwd=ROOT,
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            raise ValueError("PINNED_SOURCE_NOT_AVAILABLE") from exc
        if hashlib.sha256(raw).hexdigest() != ref["sha256"]:
            raise ValueError("PINNED_SOURCE_HASH_MISMATCH")
        if (
            path in (*MODULES[:3], *LEGACY_SOURCES)
            and hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != ref["sha256"]
        ):
            raise ValueError("FROZEN_EXECUTION_CODE_MISMATCH")
    for stage in value.get("predecessors", []):
        if stage.get("stage") not in {"S0", "S1", "S2", "S3"} or not re.fullmatch(
            r"[0-9a-f]{40}", stage.get("merge_sha", "")
        ):
            raise ValueError("PREDECESSOR_IDENTITY_INVALID")
        try:
            subprocess.run(
                [*GIT, "merge-base", "--is-ancestor", stage["merge_sha"], base],
                cwd=ROOT,
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            raise ValueError("PREDECESSOR_NOT_IN_BASE_HISTORY") from exc


def run(catalog_path: Path, output_dir: Path) -> report.Record:
    if output_dir.exists() or output_dir.is_symlink():
        raise ValueError("OUTPUT_ALREADY_EXISTS")
    raw_catalog, catalog_hash = _read_json(catalog_path)
    if raw_catalog.get("data_class") != "SYNTHETIC_TEST_FIXTURE":
        raise ValueError("SYNTHETIC_ONLY")
    request = Catalog.model_validate(raw_catalog)
    cycle._aware(request.as_of)
    identities: dict[str, str] = {"catalog": catalog_hash}

    def read(ref: Reference, identity: str, *, synthetic: bool = True) -> report.Record:
        path = _path(catalog_path.parent, ref.path)
        value, actual_hash = _read_json(path)
        if actual_hash != ref.sha256:
            raise ValueError("EXPLICIT_INPUT_HASH_MISMATCH")
        identities[identity] = actual_hash
        if synthetic:
            report._synthetic(value)
        return value

    evidence = (
        read(request.evidence, "public_evidence", synthetic=False) if request.evidence else None
    )
    if evidence is not None:
        _verify_public_evidence(evidence)
    outputs = []
    ids = [d.dataset_id for d in request.datasets]
    if len(ids) != len(set(ids)):
        raise ValueError("DUPLICATE_DATASET_ID")
    for dataset in request.datasets:

        def load(role: Role, current: Dataset = dataset) -> report.Record | None:
            ref = current.inputs.get(role)
            return read(ref, current.dataset_id + ":" + role) if ref else None

        package, declarations = load("package"), load("cycles")
        if package is None or declarations is None:
            raise ValueError("EXPLICIT_PACKAGE_AND_CYCLE_INPUT_REQUIRED")
        spec = {k: v for k, v in dataset.model_dump().items() if k != "inputs"}
        prepared = report.prepare_case(
            spec, package, declarations, load("structure"), load("protocol")
        )
        if prepared.registration is not None and not prepared.rejection:
            prepared = report.seal_case(prepared, load("predictions"))
        # Label files are not opened until the existing S3 seal has succeeded.
        labels = load("labels") if prepared.seal is not None and not prepared.rejection else None
        outputs.append(report.finish_case(prepared, labels, as_of=request.as_of))
    result = report.build_report(outputs, evidence, title=request.title)
    files = {
        "research-readiness.json": cycle.canonical(result) + b"\n",
        "report.md": report.render_markdown(result).encode(),
        "report.html": report.render_html(result).encode(),
    }
    try:
        revision = subprocess.check_output([*GIT, "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        dirty = bool(subprocess.check_output([*GIT, "status", "--porcelain"], cwd=ROOT))
    except subprocess.CalledProcessError:
        revision, dirty = "NOT_PROVEN", True
    manifest = dict(
        schema_version="V0_21_S4_EXECUTION_MANIFEST_R1",
        data_class="SYNTHETIC_TEST_FIXTURE",
        executed_at_utc=datetime.now(UTC).isoformat(),
        python=platform.python_version(),
        platform=platform.system(),
        code_git_sha=revision,
        worktree_dirty=dirty,
        source_modules_sha256={
            p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in MODULES
        },
        explicit_input_file_sha256=identities,
        business_files_sha256={p: hashlib.sha256(raw).hexdigest() for p, raw in files.items()},
        business_result_sha256=result["result_sha256"],
        label_access="AFTER_S3_SEAL_ONLY",
        frozen_git_refs_verified=evidence is not None,
        real_data_read=False,
        model_training=False,
        strict_pit_validated=False,
    )
    files["manifest.json"] = cycle.canonical(manifest) + b"\n"
    output_dir.mkdir(mode=0o700)
    for name, raw in files.items():
        path = output_dir / name
        with path.open("xb") as stream:
            stream.write(raw)
        path.chmod(0o600)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = run(args.catalog, args.output)
    print(
        json.dumps(
            dict(
                dataset_count=len(value["datasets"]),
                result_sha256=value["result_sha256"],
                formal_complete=False,
                real_data_read=False,
            )
        )
    )


if __name__ == "__main__":
    main()
