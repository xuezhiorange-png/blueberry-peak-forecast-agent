"""Execute the frozen SQLAlchemy finalizer identity matrix.

The matrix uses independent pytest processes for the seven reference nodeids,
then exercises the same nodeids in both orders, the complete orchestration
file, and the real FastAPI get_db_session request path.  The driver aggregates
only evidence; it never repairs or disposes a connection.
"""

from __future__ import annotations

import gzip
import hashlib
import inspect
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
FROZEN_BASE_SHA = "e60f48a4e76b7f3ae38d771cb1af36262960d002"
REFERENCE_NODEIDS = (
    "backend/tests/integration/test_rolling_backtest_orchestration.py::test_historical_resolution_task9_same_priority_conflict_blocks",
    "backend/tests/integration/test_rolling_backtest_orchestration.py::test_historical_resolution_task9_latest_visible_candidate_selected",
    "backend/tests/integration/test_rolling_backtest_orchestration.py::test_historical_resolution_task10_invisible_by_cutoff_blocks",
    "backend/tests/integration/test_rolling_backtest_orchestration.py::test_real_task10_prediction_completed_after_cutoff_blocks",
    "backend/tests/integration/test_rolling_backtest_orchestration.py::test_real_authority_exact_load_reuse_and_snapshot",
    "backend/tests/integration/test_rolling_backtest_orchestration.py::test_cross_season_task8_authority_blocks",
    "backend/tests/integration/test_rolling_backtest_orchestration.py::test_integrity_reload_failure_rolls_back_completed_execution",
)
API_NODEID = (
    "backend/tests/integration/test_health_ready_postgres.py::"
    "test_health_ready_uses_real_postgresql_connection"
)


def timestamp() -> str:
    return (
        time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
        + f".{time.time_ns() % 1_000_000_000:09d}+00:00"
    )


def json_dump(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_command(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )


def verify_nodeids(repo: Path) -> dict[str, Any]:
    command = [sys.executable, "-m", "pytest", "--collect-only", "-q", *REFERENCE_NODEIDS]
    result = run_command(command, cwd=repo)
    output = result.stdout + result.stderr
    resolved = [nodeid for nodeid in REFERENCE_NODEIDS if nodeid in output]
    return {
        "requested_nodeids": list(REFERENCE_NODEIDS),
        "resolved_nodeids": resolved,
        "all_resolved": len(resolved) == len(REFERENCE_NODEIDS),
        "collect_exit_code": result.returncode,
        "collect_output_sha256": hashlib.sha256(output.encode()).hexdigest(),
    }


def command_for(output_dir: Path, nodeids: list[str]) -> list[str]:
    return [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--tb=long",
        "-p",
        "scripts.ci.sqlalchemy_finalizer_identity.plugin",
        "--finalizer-output-dir",
        str(output_dir),
        f"--junitxml={output_dir / 'junit.xml'}",
        *nodeids,
    ]


def run_one(repo: Path, runs_root: Path, label: str, nodeids: list[str]) -> dict[str, Any]:
    output_dir = runs_root / label
    output_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["SQLALCHEMY_FINALIZER_OUTPUT_DIR"] = str(output_dir)
    env["SQLALCHEMY_FINALIZER_RUN_LABEL"] = label
    command = command_for(output_dir, nodeids)
    started = timestamp()
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
    completed = timestamp()
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
            "completed_at": completed,
            "exit_code": result.returncode,
        }
    )
    json_dump(summary_path, summary)
    return summary


def load_json(run_dirs: list[Path], filename: str) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for run_dir in run_dirs:
        path = run_dir / filename
        if path.exists():
            parsed = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(parsed, list):
                values.extend(parsed)
    return values


def load_jsonl(run_dirs: list[Path], filename: str) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for run_dir in run_dirs:
        path = run_dir / filename
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                values.append(json.loads(line))
    return values


def aggregate_junit(artifact_dir: Path, run_dirs: list[Path]) -> dict[str, int]:
    root = ET.Element("testsuites")
    totals: Counter[str] = Counter()
    for run_dir in run_dirs:
        path = run_dir / "junit.xml"
        if not path.exists():
            continue
        try:
            parsed = ET.parse(path).getroot()
        except ET.ParseError:
            continue
        suites = list(parsed) if parsed.tag == "testsuites" else [parsed]
        for suite in suites:
            root.append(suite)
            for key in ("tests", "failures", "errors", "skipped"):
                totals[key] += int(suite.attrib.get(key, "0"))
    ET.ElementTree(root).write(artifact_dir / "junit.xml", encoding="utf-8", xml_declaration=True)
    return {key: int(totals[key]) for key in ("tests", "failures", "errors", "skipped")}


def gzip_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def gzip_text(path: Path, text: str) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write(text)


def lifecycle_gap(record: dict[str, Any]) -> str:
    close_seen = bool(record.get("explicit_close_seen"))
    checkin_seen = bool(record.get("checkin_seen"))
    if not close_seen and not checkin_seen:
        return "explicit_close_or_checkin"
    if not close_seen:
        return "explicit_close"
    if not checkin_seen:
        return "checkin"
    return "none_observed"


def build_correlations(
    warnings: list[dict[str, Any]],
    connections: list[dict[str, Any]],
    sessions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    connection_by_id = {item.get("connection_record_id"): item for item in connections}
    session_by_id = {item.get("session_id"): item for item in sessions}
    result: list[dict[str, Any]] = []
    for warning in warnings:
        connection_id = warning.get("connection_record_id")
        connection = connection_by_id.get(connection_id)
        session_id = warning.get("last_known_session_id")
        session = session_by_id.get(session_id)
        checkout_stack = warning.get("checkout_stack") or (
            connection.get("checkout_stack", []) if connection else []
        )
        if connection is None:
            owner_status = "UNRESOLVED"
            owner_kind = "UNATTRIBUTED"
        elif session_id is not None and session is not None:
            owner_status = "UNIQUE"
            owner_kind = "SESSION"
        elif session_id is None:
            owner_status = "BARE_CONNECTION"
            owner_kind = "BARE_CONNECTION"
        else:
            owner_status = "UNRESOLVED"
            owner_kind = "UNATTRIBUTED"
        result.append(
            {
                "warning_sequence": warning.get("finalizer_sequence"),
                "run_label": warning.get("run_label"),
                "pytest_nodeid": warning.get("pytest_nodeid"),
                "pytest_phase": warning.get("pytest_phase"),
                "source_filename": warning.get("warning_source_filename"),
                "source_line": warning.get("warning_source_line"),
                "connection_record_id": connection_id,
                "dbapi_connection_object_id": warning.get("dbapi_connection_object_id"),
                "driver_connection_object_id": warning.get("driver_connection_object_id"),
                "session_id": session_id,
                "owner_attribution_status": owner_status,
                "owner_kind": owner_kind,
                "connection_record": connection,
                "session_owner": session,
                "checkout_stack": checkout_stack,
                "session_creation_stack": warning.get("session_creation_stack")
                or (session.get("creation_stack", []) if session else []),
                "last_operation": warning.get("last_session_operation")
                or (session.get("last_operation") if session else None),
                "last_database_statement_fingerprint": warning.get(
                    "last_database_statement_fingerprint"
                ),
                "missing_lifecycle_operation": lifecycle_gap(
                    {
                        "explicit_close_seen": warning.get("explicit_close_seen"),
                        "checkin_seen": warning.get("checkin_seen"),
                    }
                ),
                "explicit_close_seen": warning.get("explicit_close_seen"),
                "checkin_seen": warning.get("checkin_seen"),
                "finalizer_call_stack": warning.get("finalizer_call_stack", []),
                "warning_message": warning.get("warning_message"),
                "evidence_complete": bool(connection is not None and checkout_stack),
            }
        )
    return result


def pool_growth(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    details: list[dict[str, Any]] = []
    proven = False
    for summary in summaries:
        start = summary.get("pool_start", {}).get("pool_checked_out")
        end = summary.get("pool_end", {}).get("pool_checked_out")
        peak = summary.get("pool_max_checked_out")
        if isinstance(start, int) and isinstance(end, int) and end > start:
            proven = True
        details.append(
            {
                "label": summary.get("label"),
                "start_checked_out": start,
                "end_checked_out": end,
                "peak_checked_out": peak,
                "end_greater_than_start": isinstance(start, int)
                and isinstance(end, int)
                and end > start,
            }
        )
    return {"proven": proven, "per_run": details}


def classify(
    warnings: list[dict[str, Any]],
    correlations: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    owner_unresolved = any(
        item["owner_attribution_status"] == "UNRESOLVED" for item in correlations
    )
    checkout_unresolved = any(not item["checkout_stack"] for item in correlations)
    api_path_warnings = [
        item
        for item in correlations
        if item.get("run_label") == "api-dependency-get-db-session"
        or "get_db_session"
        in "\n".join(item.get("session_creation_stack", []) + item.get("checkout_stack", []))
    ]
    nodeids = [str(item.get("pytest_nodeid") or "") for item in warnings]
    test_only = bool(nodeids) and all(nodeid.startswith("backend/tests/") for nodeid in nodeids)
    if not warnings:
        reachability = "UNRESOLVED"
        reason = "no warning event was captured before the finalizer"
    elif owner_unresolved or checkout_unresolved:
        reachability = "UNRESOLVED"
        reason = "at least one warning lacks a persistent owner or checkout stack"
    elif api_path_warnings:
        reachability = "PRODUCTION_REACHABLE"
        reason = "a warning is correlated with the real FastAPI get_db_session path"
    elif test_only:
        reachability = "TEST_ONLY"
        reason = "all warnings are tied to test nodeids and no production request path"
    else:
        reachability = "UNRESOLVED"
        reason = "warning trigger path is not proven"
    growth = pool_growth(summaries)
    missing_lifecycle = any(
        item["missing_lifecycle_operation"] != "none_observed" for item in correlations
    )
    if reachability == "UNRESOLVED":
        risk = "UNRESOLVED"
    elif reachability == "PRODUCTION_REACHABLE" and missing_lifecycle:
        risk = "RELEASE_BLOCKER"
    elif reachability == "PRODUCTION_REACHABLE":
        risk = "POST_RELEASE_TECHNICAL_DEBT"
    else:
        risk = "TEST_TOOLING_NOISE"
    reachability_record = {
        "production_reachability": reachability,
        "reason": reason,
        "warning_count": len(warnings),
        "api_path_warning_count": len(api_path_warnings),
        "test_only_warning_count": sum(
            1
            for item in correlations
            if str(item.get("pytest_nodeid", "")).startswith("backend/tests/")
        ),
        "unique_owner_warning_count": sum(
            1
            for item in correlations
            if item["owner_attribution_status"] in {"UNIQUE", "BARE_CONNECTION"}
        ),
        "unattributed_warning_count": sum(
            1 for item in correlations if item["owner_attribution_status"] == "UNRESOLVED"
        ),
        "checkout_stack_identified": not checkout_unresolved,
        "pool_growth": growth,
        "production_request_call_chain_evidence": [
            {
                "warning_sequence": item.get("warning_sequence"),
                "run_label": item.get("run_label"),
                "nodeid": item.get("pytest_nodeid"),
                "session_creation_stack": item.get("session_creation_stack"),
                "checkout_stack": item.get("checkout_stack"),
            }
            for item in api_path_warnings
        ],
        "production_code_monkeypatched": False,
        "test_code_monkeypatched": False,
    }
    risk_record = {
        "release_risk_class": risk,
        "reason": reason,
        "release_blocker_proven": risk == "RELEASE_BLOCKER",
        "pool_growth_proven": growth["proven"],
        "missing_lifecycle_operation_present": missing_lifecycle,
        "warning_count": len(warnings),
        "production_reachability": reachability,
    }
    return reachability_record, risk_record


def postgresql_version() -> str:
    script = (
        "import asyncio, os, asyncpg\n"
        "async def main():\n"
        " c=await asyncpg.connect(host=os.environ['POSTGRES_HOST'],"
        " port=int(os.environ['POSTGRES_PORT']),database=os.environ['POSTGRES_DB'],"
        " user=os.environ['POSTGRES_USER'],password=os.environ['POSTGRES_PASSWORD'])\n"
        " try: print(await c.fetchval('SHOW server_version'))\n"
        " finally: await c.close()\n"
        "asyncio.run(main())\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else f"unavailable:{result.returncode}"


def source_manifest() -> dict[str, Any]:
    from sqlalchemy.pool import base as pool_base

    source_path = inspect.getsourcefile(pool_base._finalize_fairy)
    source = inspect.getsource(pool_base._finalize_fairy)
    return {
        "sqlalchemy_version": __import__("sqlalchemy").__version__,
        "finalizer_source_path": source_path,
        "finalizer_signature": str(inspect.signature(pool_base._finalize_fairy)),
        "finalizer_source_sha256": hashlib.sha256(source.encode()).hexdigest(),
    }


def write_checksums(artifact_dir: Path) -> None:
    files = sorted(
        path for path in artifact_dir.rglob("*") if path.is_file() and path.name != "SHA256SUMS"
    )
    lines = [f"{sha256(path)}  {path.relative_to(artifact_dir).as_posix()}\n" for path in files]
    (artifact_dir / "SHA256SUMS").write_text("".join(lines), encoding="utf-8")


def main() -> int:
    repo = Path.cwd()
    artifact_dir = Path(
        os.environ.get(
            "SQLALCHEMY_FINALIZER_ARTIFACT_DIR",
            "reports/sqlalchemy-finalizer-identity",
        )
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)
    runs_root = artifact_dir / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)

    nodeid_manifest = verify_nodeids(repo)
    json_dump(artifact_dir / "nodeid-matrix.json", nodeid_manifest)
    if not nodeid_manifest["all_resolved"]:
        print(json.dumps(nodeid_manifest, sort_keys=True), file=sys.stderr)
        return 2

    commands: list[tuple[str, list[str]]] = [
        (f"single-{index:02d}", [nodeid]) for index, nodeid in enumerate(REFERENCE_NODEIDS, start=1)
    ]
    commands.extend(
        [
            ("group-original-order", list(REFERENCE_NODEIDS)),
            ("group-reverse-order", list(reversed(REFERENCE_NODEIDS))),
            ("rolling-backtest-orchestration-file", [REFERENCE_NODEIDS[0].split("::", 1)[0]]),
            ("api-dependency-get-db-session", [API_NODEID]),
        ]
    )

    summaries: list[dict[str, Any]] = []
    for label, nodeids in commands:
        summaries.append(run_one(repo, runs_root, label, nodeids))
    run_dirs = [runs_root / item["label"] for item in summaries]

    finalizer_events = load_json(run_dirs, "finalizer-events.json")
    if not finalizer_events:
        finalizer_events = load_jsonl(run_dirs, "finalizer-events.live.jsonl")
    connections = load_json(run_dirs, "connection-identity-map.json")
    sessions = load_json(run_dirs, "session-identity-map.json")
    warnings = [event for event in finalizer_events if event.get("warning_will_be_emitted") is True]
    correlations = build_correlations(warnings, connections, sessions)
    reachability, risk = classify(warnings, correlations, summaries)
    junit = aggregate_junit(artifact_dir, run_dirs)
    json_dump(
        artifact_dir / "sqlalchemy-connection-identity-map.json",
        {
            "record_count": len(connections),
            "records": connections,
        },
    )
    json_dump(
        artifact_dir / "sqlalchemy-session-identity-map.json",
        {
            "session_count": len(sessions),
            "sessions": sessions,
        },
    )
    json_dump(
        artifact_dir / "sqlalchemy-warning-owner-correlations.json",
        {
            "warning_count": len(correlations),
            "correlations": correlations,
        },
    )
    json_dump(artifact_dir / "sqlalchemy-production-reachability.json", reachability)
    json_dump(artifact_dir / "sqlalchemy-release-risk.json", risk)
    gzip_jsonl(artifact_dir / "sqlalchemy-finalizer-events.jsonl.gz", finalizer_events)

    log_parts = [
        "SQLAlchemy finalizer identity diagnostic matrix",
        f"reference_warning_count={REFERENCE_WARNING_COUNT}",
        f"finalizer_warning_event_count={len(warnings)}",
        "pytest_warning_hook_count="
        + str(sum(int(item.get("pytest_warning_hook_count", 0)) for item in summaries)),
        f"junit={json.dumps(junit, sort_keys=True)}",
        f"production_reachability={reachability['production_reachability']}",
        f"release_risk_class={risk['release_risk_class']}",
    ]
    for summary in summaries:
        log_parts.append(
            " | ".join(
                [
                    f"label={summary.get('label')}",
                    f"exit_code={summary.get('exit_code')}",
                    "finalizer_warning_event_count="
                    + str(summary.get("finalizer_warning_event_count", 0)),
                    f"pytest_warning_hook_count={summary.get('pytest_warning_hook_count', 0)}",
                    f"connection_record_count={summary.get('connection_record_count', 0)}",
                    f"session_record_count={summary.get('session_record_count', 0)}",
                ]
            )
        )
        log_path = runs_root / str(summary["label"]) / "pytest.log"
        if log_path.exists():
            log_parts.append(f"--- pytest log: {summary['label']} ---")
            log_parts.append(log_path.read_text(encoding="utf-8", errors="replace"))
    gzip_text(artifact_dir / "pytest-complete.log.gz", "\n".join(log_parts) + "\n")

    manifest = {
        "frozen_base_sha": FROZEN_BASE_SHA,
        "head_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID", "local"),
        "workflow_job_id": os.environ.get("GITHUB_JOB", "local"),
        "generated_at": timestamp(),
        "python_version": sys.version,
        "platform": platform.platform(),
        "postgresql_version": postgresql_version(),
        "sqlalchemy_source": source_manifest(),
        "matrix_commands": [item["command"] for item in summaries],
        "matrix_run_count": len(summaries),
        "reference_warning_count": REFERENCE_WARNING_COUNT,
        "diagnostic_warning_count": len(warnings),
        "finalizer_warning_event_count": len(warnings),
        "pytest_warning_hook_count": sum(
            int(item.get("pytest_warning_hook_count", 0)) for item in summaries
        ),
        "warning_counts_match": len(warnings)
        == sum(int(item.get("pytest_warning_hook_count", 0)) for item in summaries),
        "connection_record_count": len(connections),
        "dbapi_connection_count": len(
            {
                object_id
                for item in connections
                for object_id in item.get("dbapi_connection_object_ids", [])
            }
        ),
        "session_owner_count": len(sessions),
        "junit": junit,
        "diagnostic_configuration": {
            "finalizer_wrapped_before_original_call": True,
            "persistent_connect_checkout_mapping": True,
            "persistent_session_creation_mapping": True,
            "production_code_changed": False,
            "test_code_changed": False,
            "warning_filters_changed": False,
            "pool_parameters_changed": False,
            "connection_fix_performed": False,
            "engine_dispose_performed": False,
            "close_rollback_commit_checkin_performed_by_plugin": False,
        },
    }
    json_dump(artifact_dir / "environment-manifest.json", manifest)
    write_checksums(artifact_dir)

    checksum = subprocess.run(
        ["sha256sum", "-c", "SHA256SUMS"],
        cwd=artifact_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    print(
        json.dumps(
            {
                "diagnostic_warning_count": len(warnings),
                "warning_counts_match": manifest["warning_counts_match"],
                "unique_connection_record_count": len(
                    {item.get("connection_record_id") for item in warnings} - {None}
                ),
                "unique_session_owner_count": sum(
                    1 for item in correlations if item["owner_attribution_status"] == "UNIQUE"
                ),
                "bare_connection_owner_count": sum(
                    1
                    for item in correlations
                    if item["owner_attribution_status"] == "BARE_CONNECTION"
                ),
                "unattributed_warning_count": sum(
                    1 for item in correlations if item["owner_attribution_status"] == "UNRESOLVED"
                ),
                "production_reachability": reachability["production_reachability"],
                "release_risk_class": risk["release_risk_class"],
                "artifact_sha256_verified": checksum.returncode == 0,
            },
            sort_keys=True,
        )
    )
    if checksum.returncode != 0:
        return 3
    if any(item.get("exit_code") != 0 for item in summaries):
        return 4
    if not manifest["warning_counts_match"]:
        return 5
    if any(item["owner_attribution_status"] == "UNRESOLVED" for item in correlations):
        return 6
    if any(not item["checkout_stack"] for item in correlations):
        return 7
    if reachability["production_reachability"] == "UNRESOLVED":
        return 8
    if risk["release_risk_class"] == "UNRESOLVED":
        return 9
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
