"""Run the frozen SQLAlchemy provenance matrix and build evidence artifacts."""

from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any

REFERENCE_WARNING_COUNT = 12
REFERENCE_NODEIDS = (
    "backend/tests/rolling_backtest/test_historical_resolution.py::test_historical_resolution_task9_same_priority_conflict_blocks",
    "backend/tests/rolling_backtest/test_historical_resolution.py::test_historical_resolution_task9_latest_visible_candidate_selected",
    "backend/tests/rolling_backtest/test_historical_resolution.py::test_historical_resolution_task10_invisible_by_cutoff_blocks",
    "backend/tests/rolling_backtest/test_historical_resolution.py::test_real_task10_prediction_completed_after_cutoff_blocks",
    "backend/tests/rolling_backtest/test_historical_resolution.py::test_real_authority_exact_load_reuse_and_snapshot",
    "backend/tests/rolling_backtest/test_historical_resolution.py::test_cross_season_task8_authority_blocks",
    "backend/tests/integration/test_rolling_backtest_orchestration.py::test_integrity_reload_failure_rolls_back_completed_execution",
)
FUNCTION_NAMES = tuple(nodeid.split("::", 1)[1] for nodeid in REFERENCE_NODEIDS)
REFERENCE_LEDGER_NODEIDS = (
    "backend/tests/integration/test_rolling_backtest_orchestration.py::test_historical_resolution_task9_same_priority_conflict_blocks",
    "backend/tests/integration/test_rolling_backtest_orchestration.py::test_historical_resolution_task9_latest_visible_candidate_selected",
    "backend/tests/integration/test_rolling_backtest_orchestration.py::test_historical_resolution_task10_invisible_by_cutoff_blocks",
    "backend/tests/integration/test_rolling_backtest_orchestration.py::test_real_task10_prediction_completed_after_cutoff_blocks",
    "backend/tests/integration/test_rolling_backtest_orchestration.py::test_real_authority_exact_load_reuse_and_snapshot",
    "backend/tests/integration/test_rolling_backtest_orchestration.py::test_cross_season_task8_authority_blocks",
    "backend/tests/integration/test_rolling_backtest_orchestration.py::test_integrity_reload_failure_rolls_back_completed_execution",
)


def _utc_timestamp() -> str:
    return (
        time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
        + f".{time.time_ns() % 1_000_000_000:09d}+00:00"
    )


def _json_dump(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_collect_only(repo: Path) -> list[str]:
    target = repo / "backend/tests/integration/test_rolling_backtest_orchestration.py"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", str(target)],
        cwd=repo,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        check=False,
    )
    candidates: list[str] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if "::" in line and line.startswith("backend/"):
            candidates.append(line)
    if not candidates:
        for function_name in FUNCTION_NAMES:
            candidates.append(
                f"backend/tests/integration/test_rolling_backtest_orchestration.py::{function_name}"
            )
    return candidates


def _resolve_nodeids(repo: Path) -> tuple[list[str], dict[str, Any]]:
    collected = _run_collect_only(repo)
    by_function: dict[str, list[str]] = {}
    for nodeid in collected:
        by_function.setdefault(nodeid.rsplit("::", 1)[-1], []).append(nodeid)
    resolved: list[str] = []
    resolution: list[dict[str, Any]] = []
    for requested in REFERENCE_NODEIDS:
        function_name = requested.rsplit("::", 1)[-1]
        options = by_function.get(function_name, [])
        if len(options) == 1:
            actual = options[0]
        elif len(options) > 1:
            actual = sorted(options)[0]
        else:
            actual = ""
        if actual:
            resolved.append(actual)
        resolution.append(
            {
                "requested_nodeid": requested,
                "resolved_nodeid": actual or None,
                "resolution_status": "RESOLVED" if actual else "MISSING",
                "path_changed_from_requested": bool(actual and actual != requested),
            }
        )
    return resolved, {
        "reference_nodeids_from_task": list(REFERENCE_NODEIDS),
        "reference_nodeids_from_closed_ledger": list(REFERENCE_LEDGER_NODEIDS),
        "resolution": resolution,
        "collected_nodeid_count": len(collected),
    }


def _command_for(repo: Path, output_dir: Path, label: str, nodeids: list[str]) -> list[str]:
    junit = output_dir / "junit.xml"
    return [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--tb=long",
        "-p",
        "scripts.ci.sqlalchemy_connection_provenance.plugin",
        "--provenance-output-dir",
        str(output_dir),
        f"--junitxml={junit}",
        *nodeids,
    ]


def _run_one(repo: Path, runs_root: Path, label: str, nodeids: list[str]) -> dict[str, Any]:
    output_dir = runs_root / label
    output_dir.mkdir(parents=True, exist_ok=True)
    command = _command_for(repo, output_dir, label, nodeids)
    env = os.environ.copy()
    env["PROVENANCE_OUTPUT_DIR"] = str(output_dir)
    env["PROVENANCE_RUN_LABEL"] = label
    started = _utc_timestamp()
    with (output_dir / "pytest.log").open("w", encoding="utf-8") as log:
        result = subprocess.run(
            command,
            cwd=repo,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    finished = _utc_timestamp()
    summary_path = output_dir / "run-summary.json"
    summary: dict[str, Any] = {}
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary.update(
        {
            "label": label,
            "nodeids": nodeids,
            "command": command,
            "started_at": started,
            "completed_at": finished,
            "exit_code": result.returncode,
        }
    )
    _json_dump(output_dir / "run-summary.json", summary)
    return summary


def _iter_jsonl(run_dirs: list[Path], filename: str):
    for run_dir in run_dirs:
        path = run_dir / filename
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    yield json.loads(line)


def _write_gzip_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _load_run_json(run_dirs: list[Path], filename: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for run_dir in run_dirs:
        path = run_dir / filename
        if path.exists():
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, list):
                records.extend(value)
    return records


def _aggregate_junit(artifact_dir: Path, run_dirs: list[Path]) -> dict[str, int]:
    suites = ET.Element("testsuites")
    totals = Counter()
    for run_dir in run_dirs:
        path = run_dir / "junit.xml"
        if not path.exists():
            continue
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError:
            continue
        if root.tag == "testsuites":
            children = list(root)
        else:
            children = [root]
        for suite in children:
            suites.append(suite)
            for key in ("tests", "failures", "errors", "skipped"):
                totals[key] += int(suite.attrib.get(key, "0"))
    ET.ElementTree(suites).write(artifact_dir / "junit.xml", encoding="utf-8", xml_declaration=True)
    return dict(totals)


async def _postgres_version() -> str:
    try:
        import asyncpg

        connection = await asyncpg.connect(
            host=os.environ.get("POSTGRES_HOST", "localhost"),
            port=int(os.environ.get("POSTGRES_PORT", "5432")),
            database=os.environ["POSTGRES_DB"],
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
        )
        try:
            return str(await connection.fetchval("SHOW server_version"))
        finally:
            await connection.close()
    except Exception as exc:
        return f"unavailable:{type(exc).__name__}"


def _connection_correlations(
    warnings: list[dict[str, Any]],
    connections: list[dict[str, Any]],
    sessions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    connections_by_id = {record.get("diagnostic_connection_id"): record for record in connections}
    sessions_by_id = {record.get("diagnostic_session_id"): record for record in sessions}
    correlations: list[dict[str, Any]] = []
    for warning in warnings:
        candidate_ids = warning.get("currently_checked_out_connection_ids", [])
        candidate_sessions = warning.get("candidate_session_ids", [])
        correlations.append(
            {
                "warning_sequence": warning.get("warning_sequence"),
                "pytest_nodeid": warning.get("pytest_nodeid"),
                "pytest_phase": warning.get("pytest_phase"),
                "source_filename": warning.get("source_filename"),
                "source_line": warning.get("source_line"),
                "connection_record_ids": candidate_ids,
                "candidate_session_ids": candidate_sessions,
                "connection_records": [
                    connections_by_id[x] for x in candidate_ids if x in connections_by_id
                ],
                "candidate_sessions": [
                    sessions_by_id[x] for x in candidate_sessions if x in sessions_by_id
                ],
                "unique_connection_owner": len(candidate_ids) == 1,
                "unique_session_owner": len(candidate_sessions) == 1,
                "owner_attribution_status": (
                    "UNIQUE"
                    if len(candidate_ids) == 1 and len(candidate_sessions) == 1
                    else "UNRESOLVED"
                ),
                "missing_lifecycle_operation": "UNRESOLVED",
                "evidence_limitations": [
                    "GC warning source is not a connection creation stack",
                    "candidate identity may be absent after teardown",
                ],
            }
        )
    return correlations


def _reachability_and_risk(
    warnings: list[dict[str, Any]],
    correlations: list[dict[str, Any]],
    checkpoints: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    unresolved_owner = any(c["owner_attribution_status"] != "UNIQUE" for c in correlations)
    integration_nodes = [w.get("pytest_nodeid", "") for w in warnings]
    only_test_nodes = bool(integration_nodes) and all(
        str(x).startswith("backend/tests/") for x in integration_nodes
    )
    pool_growth = False
    pool_counts = [
        c.get("pool_checked_out") for c in checkpoints if isinstance(c.get("pool_checked_out"), int)
    ]
    if pool_counts:
        pool_growth = pool_counts[-1] > pool_counts[0]
    if unresolved_owner:
        reachability = "UNRESOLVED"
        risk = "UNRESOLVED"
        reason = "connection owner/session/lifecycle cannot be uniquely attributed"
    elif only_test_nodes and not pool_growth:
        reachability = "TEST_FIXTURE_ONLY"
        risk = "TEST_TOOLING_NOISE"
        reason = "all observed warnings are test-node scoped and pool growth is not shown"
    else:
        reachability = "UNRESOLVED"
        risk = "UNRESOLVED"
        reason = "production call-chain and post-call pool recovery are not proven"
    return (
        {
            "production_reachability": reachability,
            "reason": reason,
            "warning_count": len(warnings),
            "warnings_with_unique_owner": sum(
                1 for c in correlations if c["owner_attribution_status"] == "UNIQUE"
            ),
            "warnings_with_unresolved_owner": sum(
                1 for c in correlations if c["owner_attribution_status"] != "UNIQUE"
            ),
            "pool_growth_proven": pool_growth,
            "nodeids_observed": sorted(set(integration_nodes)),
        },
        {
            "release_risk_class": risk,
            "release_blocker_proven": False,
            "reason": reason,
            "required_release_blocker_evidence_present": False,
        },
    )


def _write_summary_log(path: Path, summaries: list[dict[str, Any]], junit: dict[str, int]) -> None:
    lines = [
        "SQLAlchemy connection provenance diagnostic matrix",
        f"reference_warning_count={REFERENCE_WARNING_COUNT}",
        f"run_count={len(summaries)}",
        f"junit={json.dumps(junit, sort_keys=True)}",
    ]
    for summary in summaries:
        lines.append(
            " | ".join(
                [
                    f"label={summary['label']}",
                    f"exit_code={summary['exit_code']}",
                    f"natural_warning_count={summary.get('natural_warning_count', 0)}",
                    f"controlled_gc_warning_count={summary.get('controlled_gc_warning_count', 0)}",
                    f"connection_record_count={summary.get('connection_record_count', 0)}",
                    f"session_record_count={summary.get('session_record_count', 0)}",
                ]
            )
        )
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def main() -> int:
    repo = Path.cwd()
    artifact_dir = Path(os.environ.get("PROVENANCE_ARTIFACT_DIR", "reports/sqlalchemy-provenance"))
    artifact_dir.mkdir(parents=True, exist_ok=True)
    runs_root = artifact_dir / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    resolved, matrix = _resolve_nodeids(repo)
    _json_dump(
        artifact_dir / "sqlalchemy-nodeid-matrix.json", {**matrix, "resolved_nodeids": resolved}
    )
    if len(resolved) != len(REFERENCE_NODEIDS):
        print("unable to resolve the frozen SQLAlchemy warning nodeid matrix", file=sys.stderr)
        return 2

    commands: list[tuple[str, list[str]]] = []
    for index, nodeid in enumerate(resolved, start=1):
        commands.append((f"single-{index:02d}", [nodeid]))
    commands.append(("group-original-order", resolved))
    commands.append(("group-reverse-order", list(reversed(resolved))))
    health_node = (
        "backend/tests/integration/test_health_ready_postgres.py::"
        "test_health_ready_uses_real_postgresql_connection"
    )
    commands.append(("api-dependency-get-db-session", [health_node]))
    commands.append(
        (
            "rolling-backtest-orchestration-file",
            ["backend/tests/integration/test_rolling_backtest_orchestration.py"],
        )
    )

    summaries: list[dict[str, Any]] = []
    for label, nodeids in commands:
        summaries.append(_run_one(repo, runs_root, label, nodeids))

    run_dirs = [runs_root / summary["label"] for summary in summaries]
    pool_events = list(_iter_jsonl(run_dirs, "sqlalchemy-pool-events.jsonl"))
    session_events = list(_iter_jsonl(run_dirs, "sqlalchemy-session-events.jsonl"))
    warning_events = list(_iter_jsonl(run_dirs, "sqlalchemy-warning-events.jsonl"))
    checkpoints = list(_iter_jsonl(run_dirs, "sqlalchemy-checkpoints.jsonl"))
    connections = _load_run_json(run_dirs, "connection-records.json")
    sessions = _load_run_json(run_dirs, "session-records.json")
    _write_gzip_jsonl(artifact_dir / "sqlalchemy-pool-events.jsonl.gz", pool_events)
    _write_gzip_jsonl(artifact_dir / "sqlalchemy-session-events.jsonl.gz", session_events)
    _write_gzip_jsonl(artifact_dir / "sqlalchemy-warning-events.jsonl.gz", warning_events)
    _write_gzip_jsonl(artifact_dir / "sqlalchemy-checkpoints.jsonl.gz", checkpoints)

    correlations = _connection_correlations(warning_events, connections, sessions)
    reachability, risk = _reachability_and_risk(warning_events, correlations, checkpoints)
    _json_dump(artifact_dir / "sqlalchemy-warning-correlations.json", correlations)
    _json_dump(
        artifact_dir / "sqlalchemy-production-reachability.json",
        {
            **reachability,
            "reference_warning_count": REFERENCE_WARNING_COUNT,
            "diagnostic_warning_count": len(warning_events),
            "strict_release_rule": (
                "PRODUCTION_REACHABLE requires unique owner, lifecycle action, "
                "stable reproduction, and pool pressure evidence"
            ),
        },
    )
    _json_dump(
        artifact_dir / "sqlalchemy-release-risk.json",
        {**risk, "production_reachability": reachability["production_reachability"]},
    )
    junit = _aggregate_junit(artifact_dir, run_dirs)
    _write_summary_log(artifact_dir / "pytest-complete.log.gz", summaries, junit)

    natural_warning_count = sum(
        int(summary.get("natural_warning_count", 0)) for summary in summaries
    )
    controlled_warning_count = sum(
        int(summary.get("controlled_gc_warning_count", 0)) for summary in summaries
    )
    manifest: dict[str, Any] = {
        "base_sha": os.environ.get("FROZEN_BASE_SHA", "unknown"),
        "head_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID", "local"),
        "workflow_job_id": os.environ.get("GITHUB_JOB", "local"),
        "pytest_commands": [summary["command"] for summary in summaries],
        "python_version": sys.version,
        "platform": platform.platform(),
        "postgresql_version": asyncio.run(_postgres_version()),
        "installed_dependency_freeze": subprocess.check_output(
            [sys.executable, "-m", "pip", "freeze"], text=True
        ).splitlines(),
        "diagnostic_plugin_configuration": {
            "xdist": False,
            "warning_filters_changed": False,
            "pool_parameters_changed": False,
            "production_code_monkeypatched": False,
            "test_code_monkeypatched": False,
            "controlled_gc": True,
            "transparent_async_session_wrappers": True,
            "wrapper_behavior": "signature-await-exception-return-preserving",
        },
        "reference_warning_count": REFERENCE_WARNING_COUNT,
        "natural_warning_count": natural_warning_count,
        "controlled_gc_warning_count": controlled_warning_count,
        "connection_record_count": len(connections),
        "session_record_count": len(sessions),
        "junit": junit,
        "artifact_sha256": {},
        "generated_at": _utc_timestamp(),
    }
    data_files = [
        path
        for path in sorted(artifact_dir.iterdir())
        if path.is_file() and path.name not in {"environment-manifest.json", "SHA256SUMS"}
    ]
    manifest["artifact_sha256"] = {path.name: _sha256(path) for path in data_files}
    _json_dump(artifact_dir / "environment-manifest.json", manifest)
    checksum_paths = [
        path
        for path in sorted(artifact_dir.iterdir())
        if path.is_file() and path.name != "SHA256SUMS"
    ]
    (artifact_dir / "SHA256SUMS").write_text(
        "".join(f"{_sha256(path)}  {path.name}\n" for path in checksum_paths),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "run_count": len(summaries),
                "failed_run_count": sum(1 for summary in summaries if summary["exit_code"] != 0),
                "natural_warning_count": natural_warning_count,
                "controlled_gc_warning_count": controlled_warning_count,
                "connection_record_count": len(connections),
                "session_record_count": len(sessions),
                "production_reachability": reachability["production_reachability"],
                "release_risk_class": risk["release_risk_class"],
                "artifact_dir": str(artifact_dir),
            },
            sort_keys=True,
        )
    )
    return 0 if all(summary["exit_code"] == 0 for summary in summaries) else 1


if __name__ == "__main__":
    raise SystemExit(main())
