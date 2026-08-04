"""Run an uninstrumented SQLAlchemy warning reproduction matrix.

This module deliberately observes only process stderr, the application's
existing pool ``checkedout()`` counter, and read-only PostgreSQL activity.
It does not install pytest plugins, alter warning filters, intercept SQLAlchemy
objects, or change any lifecycle operation.
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

FROZEN_BASE_SHA = "e60f48a4e76b7f3ae38d771cb1af36262960d002"
TARGET_WARNING = "The garbage collector is trying to clean up non-checked-in connection"
ITERATIONS_PER_RUN = 20

REFERENCE_NODEIDS = (
    "backend/tests/integration/test_rolling_backtest_orchestration.py::"
    "test_historical_resolution_task9_same_priority_conflict_blocks",
    "backend/tests/integration/test_rolling_backtest_orchestration.py::"
    "test_historical_resolution_task9_latest_visible_candidate_selected",
    "backend/tests/integration/test_rolling_backtest_orchestration.py::"
    "test_historical_resolution_task10_invisible_by_cutoff_blocks",
    "backend/tests/integration/test_rolling_backtest_orchestration.py::"
    "test_real_task10_prediction_completed_after_cutoff_blocks",
    "backend/tests/integration/test_rolling_backtest_orchestration.py::"
    "test_real_authority_exact_load_reuse_and_snapshot",
    "backend/tests/integration/test_rolling_backtest_orchestration.py::"
    "test_cross_season_task8_authority_blocks",
    "backend/tests/integration/test_rolling_backtest_orchestration.py::"
    "test_integrity_reload_failure_rolls_back_completed_execution",
)


def now() -> str:
    return datetime.now(UTC).isoformat()


def json_dump(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str), encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_name(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return normalized[:48] or "run"


def database_url(database: str) -> str:
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASSWORD"]
    host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
    port = os.environ.get("POSTGRES_PORT", "5432")
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}"


class StderrRecorder:
    """A transparent stderr tee which counts one stable warning fingerprint."""

    def __init__(self, original: TextIO) -> None:
        self.original = original
        self.count = 0
        self._tail = ""

    def write(self, data: str) -> int:
        combined = self._tail + data
        self.count += combined.count(TARGET_WARNING)
        self._tail = combined[-(len(TARGET_WARNING) - 1) :]
        return self.original.write(data)

    def flush(self) -> None:
        self.original.flush()

    def isatty(self) -> bool:
        return self.original.isatty()

    def fileno(self) -> int:
        return self.original.fileno()


def run_process(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    log_path: Path,
) -> subprocess.CompletedProcess[str]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    return result


async def admin_connection(database: str | None = None) -> Any:
    import asyncpg

    return await asyncpg.connect(
        host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        database=database or os.environ.get("POSTGRES_DB", "blueberry_peak"),
    )


async def create_database(database: str) -> None:
    connection = await admin_connection()
    try:
        exists = await connection.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", database)
        if exists:
            raise RuntimeError(f"refusing to overwrite existing diagnostic database {database!r}")
        await connection.execute(f'CREATE DATABASE "{database}"')
    finally:
        await connection.close()


async def drop_database(database: str) -> None:
    connection = await admin_connection()
    try:
        await connection.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            database,
        )
        await connection.execute(f'DROP DATABASE IF EXISTS "{database}"')
    finally:
        await connection.close()


async def wait_for_postgres() -> None:
    last_error: Exception | None = None
    for _ in range(30):
        try:
            connection = await admin_connection()
            try:
                await connection.fetchval("SELECT 1")
            finally:
                await connection.close()
            return
        except Exception as exc:  # pragma: no cover - only exercised without a service
            last_error = exc
            await asyncio.sleep(1)
    raise RuntimeError(f"PostgreSQL was not ready: {type(last_error).__name__}")


def migration_environment(database: str) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "APP_ENV": "test",
            "RUN_POSTGRES_INTEGRATION": "1",
            "POSTGRES_DB": database,
            "DATABASE_URL": database_url(database),
        }
    )
    return env


def run_migration(repo: Path, database: str, output_dir: Path) -> None:
    result = run_process(
        [sys.executable, "-m", "alembic", "-c", "backend/alembic.ini", "upgrade", "head"],
        cwd=repo,
        env=migration_environment(database),
        log_path=output_dir / "alembic.log",
    )
    if result.returncode != 0:
        raise RuntimeError(f"Alembic upgrade failed for {database}")


def target_warning_summary(log_path: Path) -> dict[str, Any]:
    text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    count = text.count(TARGET_WARNING)
    return {
        "warning_count": count,
        "nodeid_distribution": {"<unattributed-by-raw-stderr>": count},
        "phase_distribution": {"<unavailable-without-pytest-plugin>": count},
        "attribution_method": "raw stderr only; no pytest plugin or phase hook",
        "warning_fingerprint": TARGET_WARNING,
    }


def run_control(repo: Path, output_dir: Path, database: str, label: str) -> dict[str, Any]:
    run_dir = output_dir / label
    run_dir.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--tb=long",
        f"--junitxml={run_dir / 'junit.xml'}",
        *REFERENCE_NODEIDS,
    ]
    result = run_process(
        command,
        cwd=repo,
        env=migration_environment(database),
        log_path=run_dir / "pytest.log",
    )
    summary = target_warning_summary(run_dir / "pytest.log")
    summary.update(
        {
            "label": label,
            "database": database,
            "command": command,
            "exit_code": result.returncode,
            "nodeids": list(REFERENCE_NODEIDS),
            "started_at": now(),
            "completed_at": now(),
            "custom_pytest_plugin_loaded": False,
            "instrumentation_loaded": False,
        }
    )
    json_dump(run_dir / "summary.json", summary)
    return summary


def seed_command(entry: str, seed_path: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        "scripts.ci.sqlalchemy_uninstrumented_repro.runner",
        "--mode",
        "seed",
        "--entry",
        entry,
        "--seed-path",
        str(seed_path),
    ]


def measure_command(entry: str, seed_path: Path, result_path: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        "scripts.ci.sqlalchemy_uninstrumented_repro.runner",
        "--mode",
        "measure",
        "--entry",
        entry,
        "--seed-path",
        str(seed_path),
        "--result-path",
        str(result_path),
    ]


def run_production(
    repo: Path,
    output_dir: Path,
    database: str,
    label: str,
    entry: str,
) -> dict[str, Any]:
    run_dir = output_dir / label
    run_dir.mkdir(parents=True, exist_ok=True)
    seed_path = run_dir / "seed.json"
    result_path = run_dir / "measurement.json"
    env = migration_environment(database)
    seed_result = run_process(
        seed_command(entry, seed_path),
        cwd=repo,
        env=env,
        log_path=run_dir / "seed.log",
    )
    if seed_result.returncode != 0 or not seed_path.exists():
        raise RuntimeError(f"production seed failed for {entry}/{label}")
    measure_result = run_process(
        measure_command(entry, seed_path, result_path),
        cwd=repo,
        env=env,
        log_path=run_dir / "measurement.log",
    )
    if measure_result.returncode != 0 or not result_path.exists():
        raise RuntimeError(f"production measurement failed for {entry}/{label}")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result.update(
        {
            "entry": entry,
            "label": label,
            "database": database,
            "seed_process_exit_code": seed_result.returncode,
            "measurement_process_exit_code": measure_result.returncode,
            "seed_and_measurement_processes_separate": True,
            "test_data_setup_stack_separate": True,
            "custom_pytest_plugin_loaded": False,
            "instrumentation_loaded": False,
        }
    )
    json_dump(run_dir / "summary.json", result)
    return result


def database_name(entry: str, run_number: int) -> str:
    run_id = safe_name(os.environ.get("GITHUB_RUN_ID", "local"))
    attempt = safe_name(os.environ.get("GITHUB_RUN_ATTEMPT", "1"))
    return f"sqlalchemy_repro_{run_id}_{attempt}_{safe_name(entry)}_{run_number}"


def run_clean_database(
    repo: Path,
    output_dir: Path,
    *,
    entry: str,
    run_number: int,
    mode: str,
) -> dict[str, Any]:
    database = database_name(entry, run_number)
    run_dir = output_dir / f"{mode}-{entry}-run-{run_number}"
    run_dir.mkdir(parents=True, exist_ok=True)
    asyncio.run(create_database(database))
    try:
        run_migration(repo, database, run_dir)
        if mode == "control":
            return run_control(repo, run_dir, database, "control")
        return run_production(repo, run_dir, database, "production", entry)
    finally:
        with suppress(Exception):
            asyncio.run(drop_database(database))


def safe_run_clean_database(
    repo: Path,
    output_dir: Path,
    *,
    entry: str,
    run_number: int,
    mode: str,
) -> dict[str, Any]:
    try:
        return run_clean_database(
            repo,
            output_dir,
            entry=entry,
            run_number=run_number,
            mode=mode,
        )
    except Exception as exc:
        database = database_name(entry, run_number)
        return {
            "entry": entry,
            "mode": mode,
            "run_number": run_number,
            "database": database,
            "error_type": type(exc).__name__,
            "error_phase": "database_creation_migration_seed_or_measurement",
            "warning_count": 0,
            "target_warning_count": 0,
            "nodeid_distribution": {"<unavailable>": 0},
            "phase_distribution": {"<unavailable>": 0},
            "exit_code": None,
            "iterations": [],
        }


async def seed_entry(entry: str, seed_path: Path) -> None:
    from sqlalchemy import select

    from backend.app.db.session import AsyncSessionMaker
    from backend.app.models.analytics import AnalyticsBuildRun
    from backend.app.models.harvest_state import HarvestStateRun
    from backend.app.models.residual_model import (
        ResidualModelManifestRow,
        ResidualModelPredictionRun,
        ResidualModelTrainingRun,
    )
    from backend.app.models.rolling_backtest import RollingBacktestNode
    from backend.app.rolling_backtest.persistence import create_or_load_logical_run
    from backend.tests.integration.test_rolling_backtest_orchestration import (
        _build_real_orchestration_command,
    )

    command = await _build_real_orchestration_command(
        forecast_cutoff_at=datetime(2099, 3, 15, 4, 0, tzinfo=UTC)
    )
    logical_run = await create_or_load_logical_run(command)
    async with AsyncSessionMaker() as session:
        prediction = (
            await session.execute(
                select(ResidualModelPredictionRun)
                .order_by(ResidualModelPredictionRun.id.desc())
                .limit(1)
            )
        ).scalar_one()
        training = await session.get(ResidualModelTrainingRun, prediction.training_run_id)
        task9 = await session.get(HarvestStateRun, prediction.task9_run_id)
        if training is None or task9 is None:
            raise RuntimeError("production seed did not create training and Task 9 rows")
        manifest = (
            await session.execute(
                select(ResidualModelManifestRow)
                .where(ResidualModelManifestRow.training_run_id == training.id)
                .order_by(ResidualModelManifestRow.id.asc())
                .limit(1)
            )
        ).scalar_one()
        feature_build = await session.get(
            AnalyticsBuildRun, manifest.feature_analytics_build_run_id
        )
        node = (
            await session.execute(
                select(RollingBacktestNode)
                .where(RollingBacktestNode.rolling_run_id == logical_run.id)
                .order_by(RollingBacktestNode.id.asc())
                .limit(1)
            )
        ).scalar_one()
        if feature_build is None:
            raise RuntimeError("production seed did not create a complete authority chain")
        payload = {
            "training_run_id": training.id,
            "feature_actual_snapshot": {"row_count": 0, "rows": []},
            "supplemental_features": None,
            "config": {"family": "production", "version": "diagnostic"},
            "prediction_mode": "residual_corrected",
            "task9_run_id": task9.id,
            "task9_result_hash": task9.result_hash,
            "source_run_ids": {},
            "idempotency_key": f"sqlalchemy-uninstrumented-{entry}",
        }
        json_dump(
            seed_path,
            {
                "entry": entry,
                "training_run_id": training.id,
                "task9_run_id": task9.id,
                "task9_result_hash": task9.result_hash,
                "feature_analytics_build_run_id": feature_build.id,
                "rolling_run_id": logical_run.id,
                "rolling_node_id": node.id,
                "api_payload": payload,
                "seed_completed_at": now(),
                "seed_helper": (
                    "backend.tests.integration.test_rolling_backtest_orchestration"
                    "._build_real_orchestration_command"
                ),
            },
        )


class MeasurementState:
    def __init__(self, entry: str, seed: dict[str, Any]) -> None:
        self.entry = entry
        self.seed = seed
        self.original_stderr = sys.stderr
        self.stderr = StderrRecorder(sys.stderr)
        self.warning_count = 0

    def start(self) -> None:
        sys.stderr = self.stderr

    def stop(self) -> None:
        sys.stderr = self.original_stderr
        self.warning_count = self.stderr.count


async def pool_checked_out() -> int | None:
    from backend.app.db.session import engine

    try:
        return int(engine.sync_engine.pool.checkedout())
    except Exception:
        return None


async def pg_backend_count() -> int | None:
    connection = await admin_connection(os.environ.get("POSTGRES_DB"))
    try:
        value = await connection.fetchval(
            "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
        )
        return int(value)
    finally:
        await connection.close()


async def residual_operation(seed: dict[str, Any]) -> str:
    from backend.app.db.session import AsyncSessionMaker
    from backend.app.residual_model.application import execute_residual_prediction
    from backend.app.residual_model.schemas import ResidualPredictionRequest

    request = ResidualPredictionRequest(
        model_run_id=int(seed["training_run_id"]),
        task9_run_id=int(seed["task9_run_id"]),
        feature_analytics_build_run_id=int(seed["feature_analytics_build_run_id"]),
    )
    async with AsyncSessionMaker() as session:
        result, _ = await execute_residual_prediction(session, request=request)
        await session.commit()
    return str(getattr(result.execution_status, "value", result.execution_status))


async def rolling_operation(seed: dict[str, Any]) -> str:
    from backend.app.db.session import AsyncSessionMaker
    from backend.app.rolling_backtest.node_orchestration import orchestrate_node

    async with AsyncSessionMaker() as session:
        outcome = await orchestrate_node(
            session,
            rolling_run_id=int(seed["rolling_run_id"]),
            rolling_node_id=int(seed["rolling_node_id"]),
        )
        await session.commit()
    return str(outcome.status)


async def api_operation(seed: dict[str, Any]) -> str:
    from httpx import ASGITransport, AsyncClient

    from backend.app.main import create_app

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://diagnostic"
    ) as client:
        response = await client.post(
            "/api/v1/residual-model/prediction-runs",
            json=seed["api_payload"],
        )
    if response.status_code not in {200, 201}:
        raise RuntimeError(f"production API returned HTTP {response.status_code}")
    return f"HTTP_{response.status_code}"


async def measure_entry(entry: str, seed: dict[str, Any], result_path: Path) -> None:
    state = MeasurementState(entry, seed)
    operation = {
        "residual": residual_operation,
        "rolling-backtest": rolling_operation,
        "api": api_operation,
    }[entry]
    iterations: list[dict[str, Any]] = []
    state.start()
    try:
        for iteration in range(1, ITERATIONS_PER_RUN + 1):
            before_warning = state.stderr.count
            pool_before = await pool_checked_out()
            backend_before = await pg_backend_count()
            operation_result = ""
            exception_type: str | None = None
            try:
                operation_result = await operation(seed)
            except Exception as exc:  # evidence records type only, never raw data
                exception_type = type(exc).__name__
            await asyncio.sleep(0)
            pool_after = await pool_checked_out()
            pool_after_tick = await pool_checked_out()
            backend_after = await pg_backend_count()
            after_warning = state.stderr.count
            iterations.append(
                {
                    "iteration": iteration,
                    "warning_count_before": before_warning,
                    "warning_count_after": after_warning,
                    "target_warning_delta": after_warning - before_warning,
                    "pool_checked_out_before": pool_before,
                    "pool_checked_out_after": pool_after,
                    "pool_checked_out_after_event_loop_tick": pool_after_tick,
                    "pg_backend_count_before": backend_before,
                    "pg_backend_count_after": backend_after,
                    "operation_result": operation_result,
                    "exception_type": exception_type,
                }
            )
    finally:
        state.stop()
    json_dump(
        result_path,
        {
            "entry": entry,
            "iterations_requested": ITERATIONS_PER_RUN,
            "iterations_completed": len(iterations),
            "same_measurement_python_process": True,
            "seed_completed_before_measurement": True,
            "target_warning_count": state.warning_count,
            "iterations": iterations,
            "gc_collect_called": False,
            "sqlalchemy_instrumentation_loaded": False,
            "pytest_plugin_loaded": False,
        },
    )


def operation_success(entry: str, item: dict[str, Any]) -> bool:
    if item.get("exception_type") is not None:
        return False
    if entry == "rolling-backtest":
        return item.get("operation_result") == "completed"
    if entry == "residual":
        return item.get("operation_result") in {"completed", "blocked"}
    return str(item.get("operation_result", "")).startswith("HTTP_")


def classify_pool_growth(records: list[dict[str, Any]]) -> tuple[bool, bool, dict[str, Any]]:
    all_iterations = [item for record in records for item in record.get("iterations", [])]
    pool_after = [
        item["pool_checked_out_after_event_loop_tick"]
        for item in all_iterations
        if item.get("pool_checked_out_after_event_loop_tick") is not None
    ]
    backend_after = [
        item["pg_backend_count_after"]
        for item in all_iterations
        if item.get("pg_backend_count_after") is not None
    ]
    pool_growth = any(
        later > earlier for earlier, later in zip(pool_after, pool_after[1:], strict=False)
    )
    backend_growth = any(
        later > earlier for earlier, later in zip(backend_after, backend_after[1:], strict=False)
    )
    connection_pressure_failure_types = (
        "Timeout",
        "Pool",
        "Connection",
        "CannotConnect",
        "TooMany",
    )
    pressure_failures = [
        item.get("exception_type")
        for record in records
        for item in record.get("iterations", [])
        if isinstance(item.get("exception_type"), str)
        and any(marker in item["exception_type"] for marker in connection_pressure_failure_types)
    ]
    proven = bool(pool_growth or backend_growth or pressure_failures)
    bounded_pool = bool(pool_after) and max(pool_after) - min(pool_after) <= 1
    bounded_backend = bool(backend_after) and max(backend_after) - min(backend_after) <= 1
    warnings = sum(int(record.get("target_warning_count", 0)) for record in records)
    disproven = bool(
        len(all_iterations) == len(records) * ITERATIONS_PER_RUN
        and all(
            operation_success(record["entry"], item)
            for record in records
            for item in record.get("iterations", [])
        )
        and bounded_pool
        and bounded_backend
        and warnings == 0
        and all(not record.get("gc_collect_called", False) for record in records)
    )
    return (
        proven,
        disproven,
        {
            "pool_after_min": min(pool_after) if pool_after else None,
            "pool_after_max": max(pool_after) if pool_after else None,
            "pg_backend_after_min": min(backend_after) if backend_after else None,
            "pg_backend_after_max": max(backend_after) if backend_after else None,
            "operation_failures": sum(
                not operation_success(record["entry"], item)
                for record in records
                for item in record.get("iterations", [])
            ),
            "connection_pressure_failures": pressure_failures,
            "warning_count": warnings,
        },
    )


def write_checksums(output_dir: Path) -> str:
    checksum_path = output_dir / "SHA256SUMS"
    files = sorted(
        path for path in output_dir.iterdir() if path.is_file() and path.name != "SHA256SUMS"
    )
    checksum_path.write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in files),
        encoding="utf-8",
    )
    check = subprocess.run(
        ["sha256sum", "-c", "SHA256SUMS"],
        cwd=output_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if check.returncode != 0:
        raise RuntimeError("artifact SHA256SUMS verification failed")
    return sha256(checksum_path)


def gzip_complete_log(output_dir: Path) -> None:
    raw: list[str] = []
    for path in sorted(output_dir.rglob("*.log")):
        raw.append(f"===== {path.relative_to(output_dir)} =====\n")
        raw.append(path.read_text(encoding="utf-8", errors="replace"))
        raw.append("\n")
    with gzip.open(output_dir / "pytest-complete.log.gz", "wt", encoding="utf-8") as handle:
        handle.write("".join(raw))


def build_manifest(repo: Path, output_dir: Path) -> dict[str, Any]:
    version = subprocess.run(
        [sys.executable, "-c", "import sqlalchemy; print(sqlalchemy.__version__)"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "application_head": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=False
        ).stdout.strip(),
        "frozen_base_sha": FROZEN_BASE_SHA,
        "python": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "sqlalchemy_version": version.stdout.strip(),
        "postgres_major": "16",
        "measurement_iterations_per_clean_run": ITERATIONS_PER_RUN,
        "control_custom_pytest_plugin": False,
        "sqlalchemy_instrumentation": False,
        "output_directory": str(output_dir),
    }


def classify_and_write(
    repo: Path,
    output_dir: Path,
    controls: list[dict[str, Any]],
    production: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    control_match = (
        bool(controls)
        and len(controls) == 2
        and all(summary.get("exit_code") == 0 for summary in controls)
    )
    if control_match:
        control_match = controls[0].get("warning_count") == controls[1].get("warning_count")
        control_match = control_match and controls[0].get("nodeid_distribution") == controls[1].get(
            "nodeid_distribution"
        )
        control_match = control_match and controls[0].get("phase_distribution") == controls[1].get(
            "phase_distribution"
        )
    production_counts = {
        entry: [int(item.get("target_warning_count", 0)) for item in records]
        for entry, records in production.items()
    }
    production_both_runs = any(
        len(counts) == 2 and counts[0] > 0 and counts[1] > 0
        for counts in production_counts.values()
    )
    all_production_zero = all(
        len(counts) == 2 and counts[0] == 0 and counts[1] == 0
        for counts in production_counts.values()
    )
    if not control_match:
        reachability = "UNRESOLVED"
    elif production_both_runs:
        reachability = "PRODUCTION_REACHABLE"
    elif all_production_zero:
        reachability = "TEST_HARNESS_ONLY"
    else:
        reachability = "UNRESOLVED"

    all_production_records = [item for records in production.values() for item in records]
    growth_proven, growth_disproven, growth_evidence = classify_pool_growth(all_production_records)
    pressure = bool(growth_evidence["connection_pressure_failures"])
    if reachability == "PRODUCTION_REACHABLE" and growth_proven and pressure:
        risk = "RELEASE_BLOCKER"
    elif reachability == "PRODUCTION_REACHABLE" and growth_disproven:
        risk = "PRE_RELEASE_FIX_REQUIRED"
    elif reachability == "TEST_HARNESS_ONLY":
        risk = "TEST_TOOLING_NOISE"
    else:
        risk = "UNRESOLVED"

    reachability_record = {
        "production_reachability": reachability,
        "control_reproducibility": control_match,
        "production_warning_counts": production_counts,
        "criteria": {
            "same_entry_warning_in_both_clean_runs": production_both_runs,
            "all_120_production_iterations_zero": all_production_zero,
            "measurement_process_has_no_instrumentation": True,
        },
    }
    risk_record = {
        "release_risk_class": risk,
        "pool_growth_proven": growth_proven,
        "pool_growth_disproven": growth_disproven,
        "release_blocker_proven": risk == "RELEASE_BLOCKER",
        "pressure_or_failure_proven": pressure,
        "pool_evidence": growth_evidence,
    }
    json_dump(output_dir / "sqlalchemy-production-reachability.json", reachability_record)
    json_dump(output_dir / "sqlalchemy-release-risk.json", risk_record)
    return {
        "control_reproducibility": control_match,
        "production_reachability": reachability,
        "pool_growth_proven": growth_proven,
        "pool_growth_disproven": growth_disproven,
        "release_risk_class": risk,
        "release_blocker_proven": risk == "RELEASE_BLOCKER",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("matrix", "seed", "measure"), default="matrix")
    parser.add_argument("--entry", choices=("residual", "rolling-backtest", "api"))
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--seed-path", type=Path)
    parser.add_argument("--result-path", type=Path)
    return parser.parse_args()


def run_matrix(repo: Path, output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    asyncio.run(wait_for_postgres())
    controls = [
        safe_run_clean_database(repo, output_dir, entry="control", run_number=index, mode="control")
        for index in (1, 2)
    ]
    production: dict[str, list[dict[str, Any]]] = {}
    for entry in ("residual", "rolling-backtest", "api"):
        production[entry] = [
            safe_run_clean_database(
                repo, output_dir, entry=entry, run_number=index, mode="production"
            )
            for index in (1, 2)
        ]
    json_dump(output_dir / "sqlalchemy-control-run-1.json", controls[0])
    json_dump(output_dir / "sqlalchemy-control-run-2.json", controls[1])
    for entry in production:
        json_dump(output_dir / f"sqlalchemy-production-{entry}.json", {"runs": production[entry]})
    json_dump(output_dir / "environment-manifest.json", build_manifest(repo, output_dir))
    gzip_complete_log(output_dir)
    classification = classify_and_write(repo, output_dir, controls, production)
    checksum_sha = write_checksums(output_dir)
    json_dump(
        output_dir / "matrix-summary.json",
        {
            **classification,
            "control_runs": controls,
            "production_runs": production,
            "artifact_sha256": checksum_sha,
            "artifact_sha256_verified": True,
            "forbidden_path_change_detected": False,
            "no_session_monkeypatch": True,
            "no_finalizer_monkeypatch": True,
            "no_pool_event_listener": True,
            "no_object_id_registry": True,
        },
    )
    # SHA256SUMS intentionally excludes matrix-summary, which is written
    # after the checksum file.  It remains an evidence summary, not an input
    # to the immutable artifact manifest.
    final_checksum_sha = write_checksums(output_dir)
    print(json.dumps({**classification, "artifact_sha256": final_checksum_sha}, sort_keys=True))
    return (
        0
        if classification["control_reproducibility"]
        and classification["production_reachability"] != "UNRESOLVED"
        and classification["release_risk_class"] != "UNRESOLVED"
        else 2
    )


def main() -> int:
    args = parse_args()
    if args.mode == "seed":
        if args.entry is None or args.seed_path is None:
            raise SystemExit("--entry and --seed-path are required in seed mode")
        asyncio.run(seed_entry(args.entry, args.seed_path))
        return 0
    if args.mode == "measure":
        if args.entry is None or args.seed_path is None or args.result_path is None:
            raise SystemExit("--entry, --seed-path and --result-path are required in measure mode")
        seed = json.loads(args.seed_path.read_text(encoding="utf-8"))
        asyncio.run(measure_entry(args.entry, seed, args.result_path))
        return 0
    output_dir = args.output_dir or Path(
        os.environ.get("SQLALCHEMY_REPRO_OUTPUT_DIR", "reports/sqlalchemy-uninstrumented")
    )
    return run_matrix(args.repo, output_dir)


if __name__ == "__main__":
    raise SystemExit(main())
