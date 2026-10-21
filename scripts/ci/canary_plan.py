"""Pure partition and outcome contracts shared by worker and stdlib-only gate."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

TIMINGS = Path(__file__).with_name("canary-timings-r1.json")
SLOTS = ("0", "1", "2", "3")


def source_snapshot() -> dict[str, Any]:
    def git(ref: str) -> str:
        return subprocess.check_output(["git", "rev-parse", ref], text=True).strip()

    return {
        "checkout_sha": git("HEAD"),
        "tree_sha": git("HEAD^{tree}"),
        "input_sha256": {
            p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
            for p in (
                ".github/workflows/ci.yml",
                "pyproject.toml",
                "uv.lock",
                "backend/constraints-ci.txt",
                "scripts/ci/canary_partition.py",
                "scripts/ci/canary_plan.py",
                "scripts/ci/verify_canary.py",
                "scripts/ci/canary-timings-r1.json",
            )
        },
    }


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def partition(nodeids: list[str], timing: dict[str, Any]) -> dict[str, Any]:
    if not nodeids or len(set(nodeids)) != len(nodeids):
        raise ValueError("EMPTY_OR_DUPLICATE_COLLECTION")
    files: dict[str, list[str]] = defaultdict(list)
    for node in nodeids:
        path = node.split("::", 1)[0]
        if Path(path).is_absolute() or ".." in Path(path).parts or not path.endswith(".py"):
            raise ValueError("INVALID_NODEID_PATH")
        files[path].append(node)
    costs = {}
    for path, nodes in files.items():
        cost = timing["file_duration_ms"].get(
            path, timing["fallback_file_overhead_ms"] + len(nodes) * timing["fallback_per_node_ms"]
        )
        if type(cost) is not int or cost < 0:
            raise ValueError("INVALID_DURATION")
        costs[path] = max(1, cost)
    loads = dict.fromkeys(SLOTS, 0)
    owners = {}
    # Longest-processing-time first. Entire files retain fixture/order locality.
    for path in sorted(files, key=lambda p: (-costs[p], p)):
        slot = min(SLOTS, key=lambda s: (loads[s], s))
        owners[path] = slot
        loads[slot] += costs[path]
    return {"owners": dict(sorted(owners.items())), "estimated_ms": loads}


def outcomes(phases: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    result = {}
    for node, reports in phases.items():
        if not all(
            r["when"] in {"setup", "call", "teardown"}
            and r["outcome"] in {"passed", "failed", "skipped"}
            and type(r["wasxfail"]) is bool
            and type(r["reason"]) is str
            for r in reports
        ):
            raise ValueError("INVALID_TEST_REPORT_PHASE")
        stages = {r["when"]: r for r in reports}
        if len(stages) != len(reports) or not {"setup", "teardown"} <= set(stages):
            raise ValueError("DUPLICATE_OR_INCOMPLETE_EXECUTION")
        failed = any(r["outcome"] == "failed" for r in reports)
        skipped = [r for r in reports if r["outcome"] == "skipped"]
        if failed:
            status = "failed"
        elif skipped:
            status = "skipped"
        elif set(stages) == {"setup", "call", "teardown"} and all(
            r["outcome"] == "passed" for r in reports
        ):
            status = "passed"
        else:
            raise ValueError("MISSING_TEST_CALL")
        result[node] = {
            "status": status,
            "reason": skipped[0]["reason"] if skipped else "",
            "wasxfail": any(r["wasxfail"] for r in reports),
        }
    return result
