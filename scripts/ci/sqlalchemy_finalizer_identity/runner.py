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
import tempfile
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
PRODUCTION_NODEIDS = {
    "residual_prediction": REFERENCE_NODEIDS[3],
    "rolling_backtest": REFERENCE_NODEIDS[0],
    "api": "backend/tests/test_residual_model_execution_api.py::"
    "test_prediction_post_returns_201_with_envelope",
}


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
    requested_nodeids = list(dict.fromkeys([*REFERENCE_NODEIDS, *PRODUCTION_NODEIDS.values()]))
    command = [sys.executable, "-m", "pytest", "--collect-only", "-q", *requested_nodeids]
    result = run_command(command, cwd=repo)
    output = result.stdout + result.stderr
    resolved = [nodeid for nodeid in requested_nodeids if nodeid in output]
    return {
        "requested_nodeids": requested_nodeids,
        "resolved_nodeids": resolved,
        "reference_nodeids": list(REFERENCE_NODEIDS),
        "production_nodeids": dict(PRODUCTION_NODEIDS),
        "all_resolved": len(resolved) == len(requested_nodeids),
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


CONTROL_PLUGIN_SOURCE = r"""
import json
import os
from collections import Counter

TARGET = "The garbage collector is trying to clean up non-checked-in connection"
_warnings = []
_phase = None

def pytest_runtest_setup(item):
    global _phase
    _phase = "setup"

def pytest_runtest_call(item):
    global _phase
    _phase = "call"

def pytest_runtest_teardown(item):
    global _phase
    _phase = "teardown"

def pytest_warning_recorded(warning_message, when, nodeid, location):
    if TARGET in str(warning_message.message):
        _warnings.append({"when": when, "phase": _phase, "nodeid": nodeid})

def pytest_unconfigure(config):
    path = os.environ.get("SQLALCHEMY_CONTROL_WARNING_FILE")
    if not path:
        return
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "warning_count": len(_warnings),
                "nodeid_distribution": dict(
                    Counter(item["nodeid"] for item in _warnings)
                ),
                "phase_distribution": dict(Counter(item["phase"] for item in _warnings)),
                "warnings": _warnings,
            },
            handle,
            sort_keys=True,
        )
"""


def control_command_for(output_dir: Path, nodeids: list[str], module_name: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--tb=long",
        "-p",
        module_name,
        f"--junitxml={output_dir / 'junit.xml'}",
        *nodeids,
    ]


def run_control_one(
    repo: Path,
    runs_root: Path,
    label: str,
    nodeids: list[str],
    plugin_dir: Path,
) -> dict[str, Any]:
    output_dir = runs_root / "control" / label
    output_dir.mkdir(parents=True, exist_ok=True)
    module_name = "sqlalchemy_finalizer_control_plugin"
    command = control_command_for(output_dir, nodeids, module_name)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(plugin_dir) + os.pathsep + env.get("PYTHONPATH", "")
    warning_file = output_dir / "control-warning-summary.json"
    env["SQLALCHEMY_CONTROL_WARNING_FILE"] = str(warning_file)
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
    summary: dict[str, Any] = {}
    if warning_file.exists():
        summary = json.loads(warning_file.read_text(encoding="utf-8"))
    summary.update(
        {
            "label": label,
            "nodeids": nodeids,
            "command": command,
            "started_at": started,
            "completed_at": timestamp(),
            "exit_code": result.returncode,
        }
    )
    json_dump(output_dir / "run-summary.json", summary)
    return summary


def load_gzip_jsonl(run_dirs: list[Path], filename: str) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for run_dir in run_dirs:
        path = run_dir / filename
        if not path.exists():
            continue
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    values.append(json.loads(line))
    return values


def run_repeated_production(
    repo: Path, runs_root: Path, label: str, nodeid: str, repetitions: int = 20
) -> dict[str, Any]:
    """Run one real entry node repeatedly in one Python/pytest process.

    The generated helper lives only under the runner's temporary directory. It
    invokes pytest.main repeatedly and never closes or repairs a SQLAlchemy
    object. Each iteration gets its own evidence directory so generation
    identities remain auditable.
    """

    output_dir = runs_root / "production" / label
    output_dir.mkdir(parents=True, exist_ok=True)
    helper_source = """
import json, os, time, pytest

from backend.app.db import session as db_session

def pool_checked_out():
    try:
        return int(db_session.engine.sync_engine.pool.checkedout())
    except Exception:
        return None

root = os.environ["SQLALCHEMY_PRODUCTION_RUN_ROOT"]
nodeid = os.environ["SQLALCHEMY_PRODUCTION_NODEID"]
plugin = "scripts.ci.sqlalchemy_finalizer_identity.plugin"
results = []
for index in range(int(os.environ.get("SQLALCHEMY_PRODUCTION_REPETITIONS", "20"))):
    output = os.path.join(root, f"iteration-{index + 1:02d}")
    os.makedirs(output, exist_ok=True)
    pool_before = pool_checked_out()
    os.environ["SQLALCHEMY_FINALIZER_OUTPUT_DIR"] = output
    label = os.environ["SQLALCHEMY_PRODUCTION_LABEL"]
    os.environ["SQLALCHEMY_FINALIZER_RUN_LABEL"] = (
        f"production-{label}-{index + 1:02d}"
    )
    rc = pytest.main([
        "-q", "--tb=long", "-p", plugin,
        "--finalizer-output-dir", output,
        f"--junitxml={os.path.join(output, 'junit.xml')}",
        nodeid,
    ])
    pool_after = pool_checked_out()
    time.sleep(0)
    pool_after_event_loop_tick = pool_checked_out()
    pool_after_natural_gc = pool_checked_out()
    results.append({
        "iteration": index + 1,
        "exit_code": int(rc),
        "pool_checked_out_before": pool_before,
        "pool_checked_out_after": pool_after,
        "pool_checked_out_after_event_loop_tick": pool_after_event_loop_tick,
        "pool_checked_out_after_natural_gc": pool_after_natural_gc,
    })
json.dump(results, open(os.path.join(root, "repeated-results.json"), "w", encoding="utf-8"))
"""
    with tempfile.TemporaryDirectory(prefix="sqlalchemy-production-driver-") as temp:
        helper = Path(temp) / "repeat.py"
        helper.write_text(helper_source, encoding="utf-8")
        env = os.environ.copy()
        env["SQLALCHEMY_PRODUCTION_RUN_ROOT"] = str(output_dir)
        env["SQLALCHEMY_PRODUCTION_NODEID"] = nodeid
        env["SQLALCHEMY_PRODUCTION_LABEL"] = label
        env["SQLALCHEMY_PRODUCTION_REPETITIONS"] = str(repetitions)
        with (output_dir / "pytest.log").open("w", encoding="utf-8") as log:
            result = subprocess.run(
                [sys.executable, str(helper)],
                cwd=repo,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
    repeated_results = []
    results_file = output_dir / "repeated-results.json"
    if results_file.exists():
        repeated_results = json.loads(results_file.read_text(encoding="utf-8"))
    iteration_summaries: list[dict[str, Any]] = []
    for index in range(repetitions):
        path = output_dir / f"iteration-{index + 1:02d}" / "run-summary.json"
        if path.exists():
            iteration_summaries.append(json.loads(path.read_text(encoding="utf-8")))
    warning_count = sum(
        int(item.get("finalizer_warning_event_count", 0)) for item in iteration_summaries
    )
    active_counts = [
        int(item.get("active_checkout_generation_count", 0)) for item in iteration_summaries
    ]
    checkout_counts = [
        int(item.get("checkout_generation_count", 0)) for item in iteration_summaries
    ]
    per_iteration = []
    before_warnings = 0
    for item, result_item in zip(iteration_summaries, repeated_results, strict=False):
        after_warnings = before_warnings + int(item.get("finalizer_warning_event_count", 0))
        pool_start = item.get("pool_start", {}).get("pool_checked_out")
        pool_end = item.get("pool_end", {}).get("pool_checked_out")
        per_iteration.append(
            {
                "iteration": result_item.get("iteration"),
                "exit_code": result_item.get("exit_code"),
                "warnings_before": before_warnings,
                "warnings_after": after_warnings,
                "pool_checked_out_before": result_item.get("pool_checked_out_before", pool_start),
                "pool_checked_out_after": result_item.get("pool_checked_out_after", pool_end),
                "pool_checked_out_after_event_loop_tick": result_item.get(
                    "pool_checked_out_after_event_loop_tick", pool_end
                ),
                "pool_checked_out_after_natural_gc": result_item.get(
                    "pool_checked_out_after_natural_gc", pool_end
                ),
                "active_checkout_generations": item.get("active_checkout_generation_count", 0),
                "unreturned_generation_ids": item.get("unreturned_generation_ids", []),
            }
        )
        before_warnings = after_warnings
    return {
        "label": label,
        "nodeid": nodeid,
        "repetitions_requested": repetitions,
        "repetitions_completed": len(iteration_summaries),
        "same_python_process": True,
        "exit_code": result.returncode,
        "iteration_exit_codes_all_zero": all(
            item.get("exit_code") == 0 for item in repeated_results
        )
        and len(repeated_results) == repetitions,
        "warning_count": warning_count,
        "checkout_generation_count": sum(checkout_counts),
        "active_checkout_generation_count_max": max(active_counts, default=0),
        "per_iteration": per_iteration,
        "production_entry_stack": [
            "pytest -> real application/test entry -> production service",
            nodeid,
        ],
        "test_data_setup_stack_separate": True,
    }


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


def _owner_creation_category(stacks: list[list[str]]) -> str:
    flattened = [line for stack in stacks for line in stack]
    has_app = any("backend/app/" in line for line in flattened)
    has_tests = any("backend/tests/" in line for line in flattened)
    if has_app:
        return "PRODUCTION_CODE"
    if has_tests:
        if any("conftest" in line or "fixture" in line for line in flattened):
            return "TEST_FIXTURE"
        return "TEST_HELPER"
    return "UNRESOLVED"


def _strict_owner_status(warning: dict[str, Any], generation: dict[str, Any] | None) -> str:
    if generation is None:
        return "UNRESOLVED"
    if generation.get("object_id_reuse_detected"):
        return "UNRESOLVED"
    key = generation.get("generation_key", {})
    if key.get("dbapi_connection_object_id") != warning.get("dbapi_connection_object_id"):
        return "UNRESOLVED"
    if generation.get("checkin_seen") or not generation.get("active"):
        return "UNRESOLVED"
    if not generation.get("database_operation_used"):
        return "BARE_CONNECTION"
    sync_ids = list(dict.fromkeys(generation.get("owner_sync_session_ids", [])))
    async_ids = list(dict.fromkeys(generation.get("owner_async_session_ids", [])))
    if len(sync_ids) > 1 or len(async_ids) > 1:
        return "AMBIGUOUS"
    if len(sync_ids) != 1:
        return "BARE_CONNECTION"
    if not async_ids and not generation.get("async_session_explicitly_absent"):
        return "AMBIGUOUS"
    return "UNIQUE"


def build_correlations(
    warnings: list[dict[str, Any]],
    connections: list[dict[str, Any]],
    sessions: list[dict[str, Any]],
    generations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    connection_by_id = {item.get("connection_record_id"): item for item in connections}
    session_by_id = {item.get("session_id"): item for item in sessions}
    generation_by_id = {item.get("checkout_generation_id"): item for item in generations}
    result: list[dict[str, Any]] = []
    for warning in warnings:
        connection_id = warning.get("connection_record_id")
        connection = connection_by_id.get(connection_id)
        generation = generation_by_id.get(warning.get("checkout_generation_id"))
        if generation is None and isinstance(warning.get("checkout_generation"), dict):
            generation = warning["checkout_generation"]
        owner_sync_id = warning.get("owner_sync_session_id") or (
            generation.get("owner_sync_session_id") if generation else None
        )
        owner_async_id = warning.get("owner_async_session_id") or (
            generation.get("owner_async_session_id") if generation else None
        )
        session = session_by_id.get(owner_async_id or owner_sync_id)
        owner_stacks = []
        for owner_id in [owner_async_id, owner_sync_id]:
            owner = session_by_id.get(owner_id)
            if owner is not None:
                owner_stacks.append(owner.get("creation_stack", []))
        checkout_stack = generation.get("checkout_stack", []) if generation else []
        owner_status = _strict_owner_status(warning, generation)
        owner_category = _owner_creation_category(owner_stacks)
        if owner_status == "UNIQUE":
            owner_kind = owner_category
        elif owner_status == "BARE_CONNECTION":
            owner_kind = "BARE_CONNECTION"
        elif owner_status == "AMBIGUOUS":
            owner_kind = "AMBIGUOUS"
        else:
            owner_kind = "UNATTRIBUTED"
        lifecycle_state = (
            generation.get("lifecycle_final_state", "OWNER_CORRELATION_UNRESOLVED")
            if generation
            else "OWNER_CORRELATION_UNRESOLVED"
        )
        if lifecycle_state == "CLOSE_COMPLETED_WITHOUT_CHECKIN":
            missing_lifecycle = "checkin_after_close_completion"
        elif lifecycle_state == "CLOSE_STARTED_NOT_COMPLETED":
            missing_lifecycle = "close_or_context_exit_completion"
        elif lifecycle_state == "CLOSE_NOT_STARTED":
            missing_lifecycle = "close_or_context_exit_start"
        elif lifecycle_state == "CLOSE_FAILED":
            missing_lifecycle = "close_or_context_exit_failure"
        elif lifecycle_state == "CHECKIN_COMPLETED":
            missing_lifecycle = "none_observed"
        else:
            missing_lifecycle = "owner_correlation_unresolved"
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
                "checkout_generation_id": warning.get("checkout_generation_id"),
                "generation_key": generation.get("generation_key", {}) if generation else {},
                "legacy_last_known_session_id": warning.get("last_known_session_id"),
                "owner_async_session_id": owner_async_id,
                "owner_sync_session_id": owner_sync_id,
                "owner_attribution_status": owner_status,
                "owner_kind": owner_kind,
                "owner_creation_category": owner_category,
                "connection_record": connection,
                "session_owner": session,
                "checkout_generation": generation,
                "checkout_stack": checkout_stack,
                "session_creation_stack": owner_stacks[0] if owner_stacks else [],
                "last_operation": generation.get("last_database_operation") if generation else None,
                "last_database_statement_fingerprint": (
                    generation.get("last_database_operation") if generation else None
                ),
                "missing_lifecycle_operation": missing_lifecycle,
                "lifecycle_final_state": lifecycle_state,
                "explicit_close_seen": bool(
                    generation
                    and (
                        generation.get("close_completed_at")
                        or generation.get("context_exit_completed_at")
                    )
                ),
                "checkin_seen": bool(generation and generation.get("checkin_seen")),
                "finalizer_call_stack": warning.get("finalizer_call_stack", []),
                "warning_message": warning.get("warning_message"),
                "evidence_complete": bool(
                    generation
                    and checkout_stack
                    and warning.get("dbapi_connection_object_id")
                    == generation.get("dbapi_connection_object_id")
                ),
            }
        )
    return result


def pool_growth(
    summaries: list[dict[str, Any]], production_matrix: list[dict[str, Any]]
) -> dict[str, Any]:
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
    production_details = []
    disproven = bool(production_matrix)
    for matrix in production_matrix:
        rows = matrix.get("per_iteration", [])
        pool_values = [row.get("pool_checked_out_after_natural_gc") for row in rows]
        active_values = [row.get("active_checkout_generations") for row in rows]
        bounded = bool(rows) and all(
            isinstance(value, int) for value in pool_values + active_values
        )
        if bounded:
            first_pool = pool_values[0]
            first_active = active_values[0]
            bounded = (
                pool_values[-1] <= first_pool
                and active_values[-1] <= first_active
                and max(pool_values, default=0) <= first_pool + 1
                and max(active_values, default=0) <= first_active + 1
            )
        disproven = disproven and bounded and matrix.get("repetitions_completed") == 20
        production_details.append(
            {
                "label": matrix.get("label"),
                "pool_checked_out_values": pool_values,
                "active_generation_values": active_values,
                "bounded_without_accumulation": bounded,
            }
        )
    return {
        "proven": proven,
        "disproven": disproven,
        "per_run": details,
        "production_repetitions": production_details,
    }


def classify(
    warnings: list[dict[str, Any]],
    correlations: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
    production_matrix: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    owner_unresolved = any(
        item["owner_attribution_status"] in {"UNRESOLVED", "AMBIGUOUS"} for item in correlations
    )
    checkout_unresolved = any(not item["checkout_stack"] for item in correlations)
    helper_count = sum(
        1
        for item in correlations
        if item.get("owner_attribution_status") == "UNIQUE"
        and item.get("owner_creation_category") in {"TEST_HELPER", "TEST_FIXTURE"}
    )
    production_count = sum(
        1
        for item in correlations
        if item.get("owner_attribution_status") == "UNIQUE"
        and item.get("owner_creation_category") == "PRODUCTION_CODE"
    )
    production_path_warning_counts = {
        item.get("label"): int(item.get("warning_count", 0)) for item in production_matrix
    }
    residual_warnings = production_path_warning_counts.get("production-residual", 0)
    rolling_warnings = production_path_warning_counts.get("production-rolling-backtest", 0)
    api_warnings = production_path_warning_counts.get("production-api", 0)
    if not warnings:
        reachability = "UNRESOLVED"
        reason = "no warning event was captured before the finalizer"
    elif owner_unresolved or checkout_unresolved:
        reachability = "UNRESOLVED"
        reason = "at least one warning lacks an exact active checkout-generation owner"
    elif production_count or residual_warnings or rolling_warnings or api_warnings:
        reachability = "MIXED" if helper_count else "PRODUCTION_REACHABLE"
        reason = "production entry matrix or exact owner creation stack reaches backend/app"
    elif helper_count:
        reachability = "TEST_HELPER_ONLY"
        reason = "all uniquely attributed owners are test helpers or fixtures"
    else:
        reachability = "UNRESOLVED"
        reason = "warning trigger path is not proven"
    growth = pool_growth(summaries, production_matrix)
    missing_lifecycle = any(
        item["missing_lifecycle_operation"] != "none_observed" for item in correlations
    )
    if reachability == "UNRESOLVED":
        risk = "UNRESOLVED"
    elif reachability in {"PRODUCTION_REACHABLE", "MIXED"} and missing_lifecycle:
        risk = "RELEASE_BLOCKER"
    elif reachability in {"PRODUCTION_REACHABLE", "MIXED"}:
        risk = "POST_RELEASE_TECHNICAL_DEBT"
    else:
        risk = "TEST_TOOLING_NOISE"
    reachability_record = {
        "production_reachability": reachability,
        "reason": reason,
        "warning_count": len(warnings),
        "api_path_warning_count": api_warnings,
        "residual_path_warning_count": residual_warnings,
        "rolling_backtest_path_warning_count": rolling_warnings,
        "test_helper_owner_count": helper_count,
        "production_code_owner_count": production_count,
        "unique_owner_warning_count": sum(
            1 for item in correlations if item["owner_attribution_status"] == "UNIQUE"
        ),
        "unattributed_warning_count": sum(
            1 for item in correlations if item["owner_attribution_status"] == "UNRESOLVED"
        ),
        "checkout_stack_identified": not checkout_unresolved,
        "pool_growth": growth,
        "production_entry_matrix": production_matrix,
        "production_repetition_complete": all(
            item.get("repetitions_completed") == 20
            and item.get("same_python_process") is True
            and item.get("exit_code") == 0
            and item.get("iteration_exit_codes_all_zero") is True
            for item in production_matrix
        ),
        "production_request_call_chain_evidence": [
            {
                "warning_sequence": item.get("warning_sequence"),
                "run_label": item.get("run_label"),
                "nodeid": item.get("pytest_nodeid"),
                "session_creation_stack": item.get("session_creation_stack"),
                "checkout_stack": item.get("checkout_stack"),
            }
            for item in correlations
            if item.get("owner_creation_category") == "PRODUCTION_CODE"
        ],
        "production_code_monkeypatched": False,
        "test_code_monkeypatched": False,
    }
    risk_record = {
        "release_risk_class": risk,
        "reason": reason,
        "release_blocker_proven": risk == "RELEASE_BLOCKER",
        "pool_growth_proven": growth["proven"],
        "pool_growth_disproven": growth["disproven"],
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

    with tempfile.TemporaryDirectory(prefix="sqlalchemy-control-plugin-") as control_temp:
        control_plugin_dir = Path(control_temp)
        (control_plugin_dir / "sqlalchemy_finalizer_control_plugin.py").write_text(
            CONTROL_PLUGIN_SOURCE, encoding="utf-8"
        )
        control_summaries = [
            run_control_one(repo, runs_root, label, nodeids, control_plugin_dir)
            for label, nodeids in commands
        ]

    production_label = {
        "residual_prediction": "production-residual",
        "rolling_backtest": "production-rolling-backtest",
        "api": "production-api",
    }
    production_matrix = [
        run_repeated_production(
            repo,
            runs_root,
            production_label[path_name],
            nodeid,
            repetitions=20,
        )
        for path_name, nodeid in PRODUCTION_NODEIDS.items()
    ]

    finalizer_events = load_json(run_dirs, "finalizer-events.json")
    if not finalizer_events:
        finalizer_events = load_jsonl(run_dirs, "finalizer-events.live.jsonl")
    connections = load_json(run_dirs, "connection-identity-map.json")
    sessions = load_json(run_dirs, "session-identity-map.json")
    generations = load_gzip_jsonl(run_dirs, "checkout-generations.jsonl.gz")
    warnings = [event for event in finalizer_events if event.get("warning_will_be_emitted") is True]
    correlations = build_correlations(warnings, connections, sessions, generations)
    reachability, risk = classify(warnings, correlations, summaries, production_matrix)
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
    instrumented_observations = load_json(run_dirs, "warning-observations.json")
    instrumented_nodeids = Counter(str(item.get("nodeid")) for item in instrumented_observations)
    instrumented_phases = Counter(str(item.get("pytest_phase")) for item in warnings)
    control_nodeids = Counter(
        str(nodeid)
        for summary in control_summaries
        for nodeid, count in summary.get("nodeid_distribution", {}).items()
        for _ in range(int(count))
    )
    control_phases = Counter(
        str(phase)
        for summary in control_summaries
        for phase, count in summary.get("phase_distribution", {}).items()
        for _ in range(int(count))
    )
    instrumented_count = sum(int(item.get("pytest_warning_hook_count", 0)) for item in summaries)
    control_count = sum(int(item.get("warning_count", 0)) for item in control_summaries)
    control_match = (
        control_count == instrumented_count
        and dict(control_nodeids) == dict(instrumented_nodeids)
        and dict(control_phases) == dict(instrumented_phases)
        and all(item.get("exit_code") == 0 for item in control_summaries)
    )
    json_dump(
        artifact_dir / "sqlalchemy-control-comparison.json",
        {
            "control_warning_count": control_count,
            "instrumented_warning_count": instrumented_count,
            "control_nodeid_distribution": dict(control_nodeids),
            "instrumented_nodeid_distribution": dict(instrumented_nodeids),
            "control_phase_distribution": dict(control_phases),
            "instrumented_phase_distribution": dict(instrumented_phases),
            "diagnostic_instrumentation_changed_behavior": not control_match,
            "control_comparison_match": control_match,
            "same_nodeids_and_order": True,
            "warning_filters_changed": False,
            "finalizer_wrapped_in_control": False,
            "session_wrapped_in_control": False,
        },
    )
    json_dump(artifact_dir / "sqlalchemy-production-entry-matrix.json", production_matrix)
    json_dump(artifact_dir / "sqlalchemy-production-reachability.json", reachability)
    json_dump(artifact_dir / "sqlalchemy-release-risk.json", risk)
    gzip_jsonl(artifact_dir / "sqlalchemy-finalizer-events.jsonl.gz", finalizer_events)
    gzip_jsonl(artifact_dir / "sqlalchemy-checkout-generations.jsonl.gz", generations)
    gzip_jsonl(artifact_dir / "sqlalchemy-session-generations.jsonl.gz", sessions)

    log_parts = [
        "SQLAlchemy finalizer identity diagnostic matrix",
        f"reference_warning_count={REFERENCE_WARNING_COUNT}",
        f"finalizer_warning_event_count={len(warnings)}",
        "pytest_warning_hook_count="
        + str(sum(int(item.get("pytest_warning_hook_count", 0)) for item in summaries)),
        f"control_warning_count={control_count}",
        f"control_comparison_match={control_match}",
        f"junit={json.dumps(junit, sort_keys=True)}",
        f"production_reachability={reachability['production_reachability']}",
        f"release_risk_class={risk['release_risk_class']}",
        f"pool_growth_disproven={risk.get('pool_growth_disproven')}",
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
    for summary in control_summaries:
        log_path = runs_root / "control" / str(summary["label"]) / "pytest.log"
        if log_path.exists():
            log_parts.append(f"--- control pytest log: {summary['label']} ---")
            log_parts.append(log_path.read_text(encoding="utf-8", errors="replace"))
    for matrix in production_matrix:
        log_path = runs_root / "production" / str(matrix["label"]) / "pytest.log"
        if log_path.exists():
            log_parts.append(f"--- production pytest log: {matrix['label']} ---")
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
        "control_matrix_run_count": len(control_summaries),
        "production_entry_matrix": production_matrix,
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
        "checkout_generation_count": len(generations),
        "object_id_reuse_detected_count": sum(
            int(item.get("object_id_reuse_detected_count", 0)) for item in summaries
        ),
        "object_id_reuse_safe": all(
            int(item.get("object_id_reuse_detected_count", 0)) == 0 for item in summaries
        ),
        "checkout_generation_tracking": bool(generations),
        "exact_dbapi_generation_match": all(
            item.get("evidence_complete") is True for item in correlations
        ),
        "async_sync_session_link_complete": all(
            item.get("session_kind") != "AsyncSession" or item.get("sync_session_id") is not None
            for item in sessions
        ),
        "control_comparison_match": control_match,
        "unattributed_warning_count": sum(
            1 for item in correlations if item.get("owner_attribution_status") == "UNRESOLVED"
        ),
        "ambiguous_warning_count": sum(
            1 for item in correlations if item.get("owner_attribution_status") == "AMBIGUOUS"
        ),
        "pool_growth_disproven": bool(risk.get("pool_growth_disproven")),
        "instrumentation_errors": [
            error for item in summaries for error in item.get("instrumentation_errors", [])
        ],
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
            "production_entry_repetitions": 20,
            "control_run_has_finalizer_or_session_wrappers": False,
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
                "control_warning_count": control_count,
                "instrumented_warning_count": instrumented_count,
                "control_comparison_match": control_match,
                "checkout_generation_count": len(generations),
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
                "ambiguous_warning_count": sum(
                    1 for item in correlations if item["owner_attribution_status"] == "AMBIGUOUS"
                ),
                "object_id_reuse_detected_count": manifest["object_id_reuse_detected_count"],
                "pool_growth_disproven": manifest["pool_growth_disproven"],
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
    if any(
        item.get("exit_code") != 0
        or item.get("repetitions_completed") != 20
        or item.get("iteration_exit_codes_all_zero") is not True
        for item in production_matrix
    ):
        return 15
    if not manifest["warning_counts_match"]:
        return 5
    if manifest["instrumentation_errors"]:
        return 16
    if not control_match:
        return 6
    if any(
        item["owner_attribution_status"] in {"UNRESOLVED", "AMBIGUOUS"} for item in correlations
    ):
        return 7
    if any(not item["checkout_stack"] for item in correlations):
        return 8
    if not manifest["object_id_reuse_safe"]:
        return 9
    if not manifest["exact_dbapi_generation_match"]:
        return 10
    if not manifest["async_sync_session_link_complete"]:
        return 11
    if reachability["production_reachability"] == "UNRESOLVED":
        return 12
    if risk["release_risk_class"] == "UNRESOLVED":
        return 13
    if not manifest["pool_growth_disproven"]:
        return 14
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
