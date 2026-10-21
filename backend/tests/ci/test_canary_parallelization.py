"""Partition, execution-proof and fail-closed gate tests; no business assertions changed."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.ci.canary_plan import SLOTS, digest, partition
from scripts.ci.verify_canary import verify

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def timing() -> dict[str, Any]:
    return {
        "file_duration_ms": {f"backend/tests/test_{i}.py": (i + 1) * 1000 for i in range(4)},
        "fallback_file_overhead_ms": 1000,
        "fallback_per_node_ms": 10,
        "allowed_skips": {},
    }


def proofs(comparison: bool = False) -> list[dict[str, Any]]:
    catalog = [f"backend/tests/test_{i}.py::test_{j}" for i in range(4) for j in range(3)]
    plan = partition(catalog, timing())
    result = []
    for slot in [*SLOTS, *(["serial"] if comparison else [])]:
        selected = [
            n for n in catalog if slot == "serial" or plan["owners"][n.split("::")[0]] == slot
        ]
        result.append(
            {
                "version": 1,
                "slot": slot,
                "catalog": catalog,
                "catalog_sha256": digest(catalog),
                "selected": selected,
                "plan": plan,
                "identity": {
                    "ci": True,
                    "python": "3.12.13",
                    "platform": "linux",
                    "run_id": "123",
                    "run_attempt": "1",
                    "source_head": "a" * 40,
                    "database": {
                        "name": "blueberry_peak_test_123_1_full-suite-canary-" + slot,
                        "server_version": 160013,
                    },
                },
                "phases": {
                    n: [
                        {"when": w, "outcome": "passed", "reason": "", "wasxfail": False}
                        for w in ("setup", "call", "teardown")
                    ]
                    for n in selected
                },
                "exitstatus": 0,
                "collection_problems": [],
                "duration_seconds": 1.0,
            }
        )
    return result


def test_whole_files_duration_balance_and_determinism() -> None:
    nodes = [f"backend/tests/test_{i}.py::test_{j}" for i in range(20) for j in range(i + 1)]
    t = timing()
    t["file_duration_ms"].update({f"backend/tests/test_{i}.py": 5000 for i in range(4, 20)})
    one = partition(nodes, t)
    assert one == partition(nodes, t)
    assert len(one["owners"]) == 20
    assert set(one["owners"].values()) == set(SLOTS)
    assert max(one["estimated_ms"].values()) - min(one["estimated_ms"].values()) <= 5000
    # A single heavy file is not split just to equalize test counts.
    t["file_duration_ms"]["backend/tests/test_0.py"] = 100000
    changed = partition(nodes, t)
    assert changed["owners"] != one["owners"]
    assert max(changed["estimated_ms"].values()) >= 100000


@pytest.mark.parametrize(
    "nodes", [[], ["a.py::test_a", "a.py::test_a"], ["../a.py::test_a"], ["/a.py::test_a"]]
)
def test_invalid_collections_rejected(nodes: list[str]) -> None:
    with pytest.raises(ValueError):
        partition(nodes, timing())


def test_exact_once_and_serial_parity() -> None:
    result = verify(
        proofs(True), comparison=True, timing=timing(), expected_context={"run_id": "123"}
    )
    assert result["collection_count"] == 12
    assert result["outcome_counts"] == {"passed": 12}
    assert result["unique_execution"] is True
    assert result["serial_comparison"] == "PASS"


@pytest.mark.parametrize(
    "defect",
    [
        "missing",
        "duplicate",
        "cancelled",
        "collection",
        "selection",
        "missing_call",
        "double_call",
        "skip",
        "xfail",
        "environment",
        "database",
        "python",
        "postgres",
        "reference",
    ],
)
def test_failure_missing_cancelled_or_false_green_rejected(defect: str) -> None:
    pp = deepcopy(proofs(True))
    first = pp[0]
    node = first["selected"][0]
    if defect == "missing":
        pp.pop()
    elif defect == "duplicate":
        pp[-1] = pp[0]
    elif defect == "cancelled":
        first["exitstatus"] = 2
    elif defect == "collection":
        first["catalog"] = first["catalog"][:-1]
    elif defect == "selection":
        first["selected"] = first["selected"][:-1]
    elif defect == "missing_call":
        first["phases"][node] = [r for r in first["phases"][node] if r["when"] != "call"]
    elif defect == "double_call":
        first["phases"][node].append(first["phases"][node][1])
    elif defect == "skip":
        first["phases"][node][1].update(outcome="skipped", reason="NEW_SKIP")
    elif defect == "xfail":
        first["phases"][node][1]["wasxfail"] = True
    elif defect == "environment":
        first["identity"]["source_head"] = "b" * 40
    elif defect == "database":
        first["identity"]["database"]["name"] = "blueberry_peak"
    elif defect == "python":
        first["identity"]["python"] = "3.13.1"
    elif defect == "postgres":
        first["identity"]["database"]["server_version"] = 150013
    else:
        pp[-1]["phases"][node][1].update(outcome="skipped", reason="EXISTING_SKIP")
        # A permitted skip must still agree across serial and parallel execution.
        t = timing()
        t["allowed_skips"][node] = "EXISTING_SKIP"
        with pytest.raises(ValueError, match="OUTCOME_DIFFERENCE"):
            verify(pp, comparison=True, timing=t, expected_context={})
        return
    with pytest.raises(ValueError):
        verify(pp, comparison=True, timing=timing(), expected_context={})


@pytest.mark.parametrize("result", ["failure", "cancelled", "skipped", ""])
def test_aggregate_never_accepts_non_success_matrix(tmp_path: Path, result: str) -> None:
    p = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.ci.verify_canary",
            "--directory",
            str(tmp_path),
            "--matrix-result",
            result,
            "--comparison",
            "false",
            "--output",
            str(tmp_path / "out.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert p.returncode != 0
    assert "MATRIX_FAILED_CANCELLED_OR_SKIPPED" in p.stderr
    assert not (tmp_path / "out.json").exists()


def test_workflow_keeps_full_gate_and_all_events() -> None:
    w = yaml.load(Path(".github/workflows/ci.yml").read_text(), Loader=yaml.BaseLoader)
    worker = w["jobs"]["full-suite-canary"]
    gate = w["jobs"]["full-suite-canary-gate"]
    assert gate["name"] == "full-suite-canary"
    assert "always()" in gate["if"]
    assert gate["needs"] == "full-suite-canary"
    assert worker["strategy"]["fail-fast"] == "false"
    assert "if" not in worker
    assert worker["services"]["postgres"]["image"] == "postgres:16"
    assert not w["on"]["pull_request"]
    assert w["on"]["push"]["branches"] == ["main"]


def test_real_pytest_subprocess_union_and_serial_control(tmp_path: Path) -> None:
    from scripts.ci.verify_canary import junit_results, merged_junit

    repo = Path.cwd()
    toy = tmp_path / "SYNTHETIC"
    toy.mkdir()
    for name in (
        ".github/workflows/ci.yml",
        "pyproject.toml",
        "uv.lock",
        "backend/constraints-ci.txt",
        "scripts/ci/canary_partition.py",
        "scripts/ci/canary_plan.py",
        "scripts/ci/verify_canary.py",
        "scripts/ci/canary-timings-r1.json",
    ):
        path = toy / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("" if name != "pyproject.toml" else "[tool.pytest.ini_options]\n")
    for i in range(6):
        (toy / f"test_{i}.py").write_text(f"def test_{i}():\n    assert {i} >= 0\n")
    subprocess.run(["git", "init", "--quiet"], cwd=toy, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=SYNTHETIC",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--allow-empty",
            "--quiet",
            "-m",
            "SYNTHETIC",
        ],
        cwd=toy,
        check=True,
        capture_output=True,
    )
    env = {**os.environ, "GITHUB_ACTIONS": "false", "PYTHONPATH": str(repo)}
    # No retries. All five processes must independently collect the same toy corpus.
    reports = []
    paths = []
    for slot in [*SLOTS, "serial"]:
        output = tmp_path / slot
        output.mkdir()
        proof, xml = output / "canary-proof.json", output / "full.xml"
        run = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-p",
                "scripts.ci.canary_partition",
                "--canary-slot",
                slot,
                "--canary-proof",
                str(proof),
                "--junitxml",
                str(xml),
            ],
            cwd=toy,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        assert run.returncode == 0, run.stdout + run.stderr
        report = json.loads(proof.read_bytes())
        assert set(junit_results(xml)) == set(report["selected"])
        reports.append(report)
        paths.append(proof)
    real_timing = json.loads((repo / "scripts/ci/canary-timings-r1.json").read_bytes())
    result = verify(
        reports, comparison=True, expected_context={}, timing=real_timing, require_ci=False
    )
    assert result["collection_count"] == 6
    assert result["outcome_counts"] == {"passed": 6}
    assert result["serial_comparison"] == "PASS"
    merged = tmp_path / "merged.xml"
    merged.write_bytes(merged_junit(reports, paths))
    assert len(junit_results(merged)) == 6  # The serial reference is NOT double-counted.


def test_junit_duplicate_missing_or_malformed_cannot_pass(tmp_path: Path) -> None:
    from scripts.ci.verify_canary import junit_results

    xml = tmp_path / "full.xml"
    for raw in (
        b"<testsuites/>",
        b"broken",
        b"<!DOCTYPE testsuites><testsuites/>",
        b'<testsuites><testcase classname="test_a" name="test_b"/>'
        b'<testcase classname="test_a" name="test_b"/></testsuites>',
    ):
        xml.write_bytes(raw)
        with pytest.raises((ValueError, ET.ParseError)):
            junit_results(xml)
