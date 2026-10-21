"""Fail-closed fan-in for exhaustive canary partitions and optional serial control."""

from __future__ import annotations

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any

from scripts.ci.canary_plan import (
    SLOTS,
    TIMINGS,
    canonical,
    digest,
    outcomes,
    partition,
    source_snapshot,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def junit_cases(path: Path) -> dict[str, ET.Element]:
    raw = path.read_bytes()
    require(len(raw) <= 25_000_000 and b"<!DOCTYPE" not in raw, "INVALID_JUNIT")
    cases = ET.fromstring(raw).iter("testcase")
    result = {}
    for case in cases:
        parts = case.get("classname", "").split(".")
        index = next((i for i, p in enumerate(parts) if p.startswith("test_")), None)
        require(index is not None, "UNRESOLVED_JUNIT_NODEID")
        assert index is not None
        node = (
            "/".join(parts[: index + 1])
            + ".py::"
            + "::".join([*parts[index + 1 :], case.attrib["name"]])
        )
        require(node not in result, "DUPLICATE_JUNIT_EXECUTION")
        result[node] = case
    require(bool(result), "EMPTY_JUNIT")
    return result


def junit_results(path: Path) -> dict[str, str]:
    result = {}
    for node, case in junit_cases(path).items():
        result[node] = (
            "failed"
            if any(case.find(n) is not None for n in ("failure", "error"))
            else ("skipped" if case.find("skipped") is not None else "passed")
        )
    return result


def merged_junit(proofs: list[dict[str, Any]], paths: list[Path]) -> bytes:
    """Preserve the historical full.xml artifact, excluding the optional control."""
    cases: dict[str, ET.Element] = {}
    for proof, path in zip(proofs, paths, strict=True):
        if proof["slot"] == "serial":
            continue
        for node, case in junit_cases(path.with_name("full.xml")).items():
            require(node not in cases, "DUPLICATE_MERGED_JUNIT")
            cases[node] = case
    root = ET.Element("testsuites")
    suite = ET.SubElement(
        root,
        "testsuite",
        name="pytest",
        tests=str(len(cases)),
        failures="0",
        errors="0",
        skipped=str(sum(c.find("skipped") is not None for c in cases.values())),
        time=str(sum(float(c.get("time", "0")) for c in cases.values())),
    )
    for node in proofs[0]["catalog"]:
        suite.append(cases[node])
    return bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True)) + b"\n"


def verify(
    proofs: list[dict[str, Any]],
    *,
    comparison: bool,
    expected_context: dict[str, Any],
    timing: dict[str, Any],
    require_ci: bool = True,
) -> dict[str, Any]:
    slots = [*SLOTS, "serial"] if comparison else list(SLOTS)
    require(
        len(proofs) == len(slots) and {p["slot"] for p in proofs} == set(slots),
        "MISSING_DUPLICATE_OR_UNEXPECTED_SHARD",
    )
    first = proofs[0]
    catalog = first["catalog"]
    plan = partition(catalog, timing)
    base_identity = {k: v for k, v in first["identity"].items() if k != "database"}
    observed: Counter[str] = Counter()
    all_results = {}
    reference = None
    databases = set()
    totals: Counter[str] = Counter()
    for proof in proofs:
        slot = proof["slot"]
        env = proof["identity"]
        require(
            type(proof["version"]) is int
            and proof["version"] == 1
            and type(proof["exitstatus"]) is int
            and proof["exitstatus"] == 0
            and not proof["collection_problems"],
            "FAILED_OR_INCOMPLETE_PYTEST",
        )
        require(
            proof["catalog"] == catalog
            and proof["catalog_sha256"] == digest(catalog)
            and proof["plan"] == plan,
            "COLLECTION_OR_ASSIGNMENT_DRIFT",
        )
        require(
            {k: v for k, v in env.items() if k != "database"} == base_identity,
            "SOURCE_OR_ENVIRONMENT_DRIFT",
        )
        require(
            all(env.get(k) == v for k, v in expected_context.items()),
            "WRONG_HEAD_RUN_ATTEMPT_OR_WORKFLOW",
        )
        if require_ci:
            db = env["database"]
            run_id, attempt = env["run_id"], env["run_attempt"]
            require(
                env["ci"] is True
                and env["python"].startswith("3.12.")
                and env["platform"] == "linux"
                and 160000 <= db["server_version"] < 170000
                and run_id.isdigit()
                and int(run_id) > 0
                and attempt.isdigit()
                and int(attempt) > 0
                and db["name"] == f"blueberry_peak_test_{run_id}_{attempt}_full-suite-canary-{slot}"
                and db["name"] not in databases,
                "ISOLATED_PY312_PG16_IDENTITY_REQUIRED",
            )
            databases.add(db["name"])
        selected = [
            n for n in catalog if slot == "serial" or plan["owners"][n.split("::", 1)[0]] == slot
        ]
        require(
            bool(selected)
            and sorted(proof["selected"]) == selected
            and set(proof["phases"]) == set(selected),
            "EXECUTION_COVERAGE_MISMATCH",
        )
        results = outcomes(proof["phases"])
        for node, r in results.items():
            require(r["status"] != "failed" and not r["wasxfail"], "FAILED_OR_XFAIL_TEST")
            if r["status"] == "skipped":
                require(timing["allowed_skips"].get(node) == r["reason"], "NEW_OR_CHANGED_SKIP")
        if slot == "serial":
            reference = results
        else:
            observed.update(selected)
            all_results.update(results)
            totals.update(r["status"] for r in results.values())
    require(
        set(observed) == set(catalog) and set(observed.values()) == {1},
        "FULL_CATALOG_NOT_EXECUTED_EXACTLY_ONCE",
    )
    if comparison:
        require(reference == all_results, "SERIAL_PARALLEL_OUTCOME_DIFFERENCE")
    return {
        "status": "PASS",
        "collection_count": len(catalog),
        "catalog_sha256": digest(catalog),
        "outcome_counts": dict(totals),
        "unique_execution": True,
        "serial_comparison": "PASS" if comparison else "NOT_REQUESTED",
        "estimated_ms": plan["estimated_ms"],
        "pytest_seconds_by_slot": {p["slot"]: p["duration_seconds"] for p in proofs},
        "source_identity": base_identity,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--comparison", choices=["true", "false"], required=True)
    parser.add_argument("--matrix-result", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        require(args.matrix_result == "success", "MATRIX_FAILED_CANCELLED_OR_SKIPPED")
        paths = sorted(args.directory.rglob("canary-proof.json"))
        proofs = []
        for path in paths:
            proof = json.loads(path.read_bytes())
            junit = junit_results(path.with_name("full.xml"))
            require(
                junit == {n: r["status"] for n, r in outcomes(proof["phases"]).items()},
                "JUNIT_AND_NODEID_PROOF_DIFFER",
            )
            proofs.append(proof)
        result = verify(
            proofs,
            comparison=args.comparison == "true",
            require_ci=True,
            expected_context={
                **source_snapshot(),
                "run_id": os.environ["GITHUB_RUN_ID"],
                "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
                "source_head": os.environ["CANARY_SOURCE_HEAD"],
                "event": os.environ["GITHUB_EVENT_NAME"],
            },
            timing=json.loads(TIMINGS.read_bytes()),
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.with_name("full.xml").write_bytes(merged_junit(proofs, paths))
        args.output.write_bytes(canonical(result) + b"\n")
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, KeyError, OSError, TypeError, ET.ParseError) as exc:
        print(f"CANARY_GATE_FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
