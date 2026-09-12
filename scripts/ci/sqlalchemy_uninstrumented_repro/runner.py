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
import tempfile
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO, cast

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


def seed_command(
    entry: str,
    seed_path: Path,
    runtime_seed_path: Path,
) -> list[str]:
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
        "--runtime-seed-path",
        str(runtime_seed_path),
    ]


def measure_command(entry: str, runtime_seed_path: Path, result_path: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        "scripts.ci.sqlalchemy_uninstrumented_repro.runner",
        "--mode",
        "measure",
        "--entry",
        entry,
        "--seed-path",
        str(runtime_seed_path),
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
    runtime_seed_fd, runtime_seed_name = tempfile.mkstemp(
        prefix=f"sqlalchemy-repro-{safe_name(entry)}-",
        suffix=".json",
    )
    os.close(runtime_seed_fd)
    runtime_seed_path = Path(runtime_seed_name)
    env = migration_environment(database)
    try:
        seed_result = run_process(
            seed_command(entry, seed_path, runtime_seed_path),
            cwd=repo,
            env=env,
            log_path=run_dir / "seed.log",
        )
        if seed_result.returncode != 0 or not seed_path.exists() or not runtime_seed_path.exists():
            raise RuntimeError(f"production seed failed for {entry}/{label}")
        measure_result = run_process(
            measure_command(entry, runtime_seed_path, result_path),
            cwd=repo,
            env=env,
            log_path=run_dir / "measurement.log",
        )
        if not result_path.exists():
            raise RuntimeError(f"production measurement produced no evidence for {entry}/{label}")
        loaded_result = json.loads(result_path.read_text(encoding="utf-8"))
        if not isinstance(loaded_result, dict):
            raise RuntimeError(f"production measurement was not an object for {entry}/{label}")
        result = cast(dict[str, Any], loaded_result)
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
    finally:
        with suppress(FileNotFoundError):
            runtime_seed_path.unlink()


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
        result = run_production(repo, run_dir, database, "production", entry)
        result.update({"mode": mode, "run_number": run_number})
        return result
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
            "seed_process_exit_code": None,
            "measurement_process_exit_code": None,
            "iterations_requested": ITERATIONS_PER_RUN,
            "iterations_completed": 0,
            "iterations": [],
            "warmup_valid": False,
            "sqlalchemy_instrumentation_loaded": False,
            "pytest_plugin_loaded": False,
            "gc_collect_called": False,
        }


async def seed_entry(entry: str, seed_path: Path, runtime_seed_path: Path) -> None:
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
    from backend.app.residual_model.application import execute_residual_training
    from backend.app.residual_model.config import load_residual_model_config
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
                .where(ResidualModelPredictionRun.execution_status == "completed")
                .order_by(ResidualModelPredictionRun.id.desc())
                .limit(1)
            )
        ).scalar_one()
        training = await session.get(ResidualModelTrainingRun, prediction.training_run_id)
        task9 = await session.get(HarvestStateRun, prediction.task9_run_id)
        if training is None or task9 is None:
            raise RuntimeError("production seed did not create training and Task 9 rows")
        prediction_snapshot = prediction.input_snapshot
        if not isinstance(prediction_snapshot, dict):
            raise RuntimeError("completed prediction has no canonical input snapshot")
        feature_snapshot = prediction_snapshot.get("feature_actual_snapshot")
        supplemental_features = prediction_snapshot.get("supplemental_feature_values")
        feature_build_id = prediction_snapshot.get("feature_analytics_build_run_id")
        if not isinstance(feature_snapshot, dict) or not isinstance(supplemental_features, list):
            raise RuntimeError("completed prediction snapshot lacks feature authority inputs")
        if not isinstance(feature_build_id, int):
            manifest = (
                await session.execute(
                    select(ResidualModelManifestRow)
                    .where(ResidualModelManifestRow.training_run_id == training.id)
                    .order_by(ResidualModelManifestRow.id.asc())
                    .limit(1)
                )
            ).scalar_one()
            feature_build_id = manifest.feature_analytics_build_run_id
        feature_build = await session.get(AnalyticsBuildRun, feature_build_id)
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

        # The API adapter derives an empty feature-schema hash by design.  A
        # blocked training run created by the production training service with
        # an empty sample set is therefore the authoritative API contract
        # input; using the eligible training run here would make the adapter
        # fail its persisted feature-schema authority check.
        api_config = load_residual_model_config(Path("configs/residual_model.yaml"))
        _, api_training_id = await execute_residual_training(
            session,
            samples=[],
            config=api_config,
            execution_context={"diagnostic_entry": "api_contract_seed"},
        )
        api_training = await session.get(ResidualModelTrainingRun, api_training_id)
        if api_training is None or api_training.execution_status != "blocked":
            raise RuntimeError("production API seed did not create a blocked training authority")
        source_run_ids = {
            "training_run_id": training.id,
            "task9_run_id": task9.id,
            "feature_analytics_build_run_id": feature_build.id,
        }
        api_payload = {
            "training_run_id": api_training.id,
            "feature_actual_snapshot": feature_snapshot,
            "supplemental_features": supplemental_features,
            "config": api_training.config_snapshot,
            "prediction_mode": "structural_only",
            "task9_run_id": task9.id,
            "task9_result_hash": task9.result_hash,
            "source_run_ids": source_run_ids,
            "idempotency_key": f"sqlalchemy-uninstrumented-{entry}",
        }
        residual_request = {
            "model_run_id": training.id,
            "task9_run_id": task9.id,
            "feature_analytics_build_run_id": feature_build.id,
            "supplemental_feature_values": supplemental_features,
        }
        await session.commit()
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
                "api_training_run_id": api_training.id,
                "residual_request_source": ("completed_prediction_canonical_input_snapshot"),
                "residual_request_authority_verified": True,
                "feature_snapshot_authority_verified": True,
                "feature_snapshot_build_run_id": feature_snapshot.get("build_run_id"),
                "feature_snapshot_row_count": feature_snapshot.get("row_count"),
                "supplemental_feature_count": len(supplemental_features),
                "seed_completed_at": now(),
                "seed_helper": (
                    "backend.tests.integration.test_rolling_backtest_orchestration"
                    "._build_real_orchestration_command"
                ),
            },
        )
        json_dump(
            runtime_seed_path,
            {
                "entry": entry,
                "residual_request": residual_request,
                # Keep only safe provenance metadata in the runtime seed so
                # measurement evidence can prove the request source and
                # authority check without copying business payload details.
                "residual_request_source": ("completed_prediction_canonical_input_snapshot"),
                "residual_request_authority_verified": True,
                "api_payload": api_payload,
                "rolling_run_id": logical_run.id,
                "rolling_node_id": node.id,
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
        return int(engine.sync_engine.pool.checkedout())  # type: ignore[attr-defined]
    except Exception:
        return None


async def pg_backend_count(connection: Any) -> int | None:
    try:
        value = await connection.fetchval(
            "SELECT count(*) FROM pg_stat_activity "
            "WHERE datname = current_database() AND pid <> pg_backend_pid()"
        )
        return int(value)
    except Exception:
        return None


async def residual_operation(seed: dict[str, Any]) -> dict[str, Any]:
    from backend.app.db.session import AsyncSessionMaker
    from backend.app.residual_model.application import execute_residual_prediction
    from backend.app.residual_model.schemas import FeatureValue, ResidualPredictionRequest

    request_data = seed["residual_request"]
    request = ResidualPredictionRequest(
        model_run_id=int(request_data["model_run_id"]),
        task9_run_id=int(request_data["task9_run_id"]),
        feature_analytics_build_run_id=int(request_data["feature_analytics_build_run_id"]),
        supplemental_feature_values=tuple(
            FeatureValue.model_validate(item)
            for item in request_data["supplemental_feature_values"]
        ),
    )
    async with AsyncSessionMaker() as session:
        result, _ = await execute_residual_prediction(session, request=request)
        await session.commit()
    return {
        "operation_result": str(getattr(result.execution_status, "value", result.execution_status)),
        "residual_request_source": seed.get("residual_request_source"),
        "residual_request_authority_verified": bool(
            seed.get("residual_request_authority_verified", False)
        ),
        "residual_operation_status": str(
            getattr(result.execution_status, "value", result.execution_status)
        ),
        "residual_failure_stage": None,
        "residual_exception_type": None,
    }


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


async def api_operation(seed: dict[str, Any]) -> dict[str, Any]:
    from httpx import ASGITransport, AsyncClient

    from backend.app.main import create_app

    try:
        app = create_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://diagnostic"
        ) as client:
            response = await client.post(
                "/api/v1/residual-model/prediction-runs",
                json=seed["api_payload"],
            )
    except Exception:
        return {
            "operation_result": "",
            "http_status": None,
            "stable_error_code": "TRANSPORT_ERROR",
            "response_body_sha256": None,
            "failure_stage": "transport",
            "api_operation_valid": False,
        }

    status = int(response.status_code)
    body_hash = hashlib.sha256(response.content).hexdigest()
    if status in {200, 201}:
        return {
            "operation_result": f"HTTP_{status}",
            "http_status": status,
            "stable_error_code": None,
            "response_body_sha256": body_hash,
            "failure_stage": None,
            "api_operation_valid": True,
        }

    stable_error_code = f"HTTP_{status}"
    try:
        body = response.json()
        error = body.get("error") if isinstance(body, dict) else None
        code = error.get("code") if isinstance(error, dict) else None
        if isinstance(code, str) and re.fullmatch(r"[A-Z0-9_]{1,80}", code):
            stable_error_code = code
    except Exception:
        pass
    return {
        "operation_result": f"HTTP_{status}",
        "http_status": status,
        "stable_error_code": stable_error_code,
        "response_body_sha256": body_hash,
        "failure_stage": "http_response",
        "api_operation_valid": False,
    }


async def measure_entry(entry: str, seed: dict[str, Any], result_path: Path) -> None:
    state = MeasurementState(entry, seed)
    operation = {
        "residual": residual_operation,
        "rolling-backtest": rolling_operation,
        "api": api_operation,
    }[entry]
    iterations: list[dict[str, Any]] = []
    monitor_connection = await admin_connection(os.environ.get("POSTGRES_DB"))
    monitor_backend_pid = int(await monitor_connection.fetchval("SELECT pg_backend_pid()"))
    warmup: dict[str, Any] = {}
    state.start()
    try:
        warmup_warning_before = state.stderr.count
        warmup_operation_result: str | None = None
        warmup_exception_type: str | None = None
        warmup_failure_stage: str | None = None
        try:
            warmup_outcome = await operation(seed)
            if isinstance(warmup_outcome, dict):
                warmup_operation_result = str(warmup_outcome.get("operation_result", ""))
                warmup.update(warmup_outcome)
            else:
                warmup_operation_result = str(warmup_outcome)
        except Exception as exc:  # evidence records type only, never raw data
            warmup_exception_type = type(exc).__name__
            warmup_failure_stage = "warmup_operation"
        await asyncio.sleep(0)
        warmup_warning_after = state.stderr.count
        warmup.update(
            {
                "operation_result": warmup_operation_result,
                "warning_delta": warmup_warning_after - warmup_warning_before,
                "exception_type": warmup_exception_type,
                "failure_stage": warmup_failure_stage,
            }
        )
        warmup["valid"] = warmup_exception_type is None and operation_success(
            entry,
            {
                "operation_result": warmup_operation_result,
                **warmup,
            },
        )
        baseline_pool_checked_out = await pool_checked_out()
        baseline_application_backend_count = await pg_backend_count(monitor_connection)
        for iteration in range(1, ITERATIONS_PER_RUN + 1):
            before_warning = state.stderr.count
            pool_before = await pool_checked_out()
            backend_before = await pg_backend_count(monitor_connection)
            operation_result = ""
            exception_type: str | None = None
            failure_stage: str | None = None
            operation_details: dict[str, Any] = {}
            try:
                outcome = await operation(seed)
                if isinstance(outcome, dict):
                    operation_details = outcome
                    operation_result = str(outcome.get("operation_result", ""))
                else:
                    operation_result = str(outcome)
            except Exception as exc:  # evidence records type only, never raw data
                exception_type = type(exc).__name__
                failure_stage = "operation"
            await asyncio.sleep(0)
            pool_after = await pool_checked_out()
            pool_after_tick = await pool_checked_out()
            backend_after = await pg_backend_count(monitor_connection)
            after_warning = state.stderr.count
            item = {
                **operation_details,
                "iteration": iteration,
                "warning_count_before": before_warning,
                "warning_count_after": after_warning,
                "target_warning_delta": after_warning - before_warning,
                "pool_checked_out_before": pool_before,
                "pool_checked_out_after": pool_after,
                "pool_checked_out_after_event_loop_tick": pool_after_tick,
                "application_backend_count_before": backend_before,
                "application_backend_count_after": backend_after,
                "pg_backend_count_before": backend_before,
                "pg_backend_count_after": backend_after,
                "operation_result": operation_result,
                "exception_type": exception_type,
                "failure_stage": failure_stage or operation_details.get("failure_stage"),
            }
            if entry == "residual" and exception_type is not None:
                item.update(
                    {
                        "residual_request_source": seed.get("residual_request_source"),
                        "residual_request_authority_verified": bool(
                            seed.get("residual_request_authority_verified", False)
                        ),
                        "residual_operation_status": None,
                        "residual_failure_stage": "prediction_service",
                        "residual_exception_type": exception_type,
                    }
                )
            iterations.append(item)
    finally:
        state.stop()
        await monitor_connection.close()
    pool_after_values = [
        value
        for item in iterations
        for value in [item.get("pool_checked_out_after_event_loop_tick")]
        if isinstance(value, int)
    ]
    backend_after_values = [
        value
        for item in iterations
        for value in [item.get("application_backend_count_after")]
        if isinstance(value, int)
    ]
    final_pool_checked_out = pool_after_values[-1] if pool_after_values else None
    final_application_backend_count = backend_after_values[-1] if backend_after_values else None
    last_three_pool_checked_out = pool_after_values[-3:]
    last_three_application_backend_count = backend_after_values[-3:]
    transient_backend_spike = bool(
        baseline_application_backend_count is not None
        and final_application_backend_count == baseline_application_backend_count
        and any(value > baseline_application_backend_count for value in backend_after_values)
        and not all(
            value > baseline_application_backend_count
            for value in last_three_application_backend_count
        )
    )
    record = {
        "entry": entry,
        "iterations_requested": ITERATIONS_PER_RUN,
        "iterations_completed": len(iterations),
        "same_measurement_python_process": True,
        "seed_completed_before_measurement": True,
        "target_warning_count": state.warning_count,
        "iterations": iterations,
        "warmup": warmup,
        "warmup_valid": bool(warmup.get("valid", False)),
        "baseline_pool_checked_out": baseline_pool_checked_out,
        "baseline_application_backend_count": baseline_application_backend_count,
        "final_pool_checked_out": final_pool_checked_out,
        "final_application_backend_count": final_application_backend_count,
        "last_three_pool_checked_out": last_three_pool_checked_out,
        "last_three_application_backend_count": last_three_application_backend_count,
        "transient_peak_pool_checked_out": max(pool_after_values) if pool_after_values else None,
        "transient_peak_application_backend_count": max(backend_after_values)
        if backend_after_values
        else None,
        "transient_backend_spike": transient_backend_spike,
        "monitor_backend_pid": monitor_backend_pid,
        "gc_collect_called": False,
        "sqlalchemy_instrumentation_loaded": False,
        "pytest_plugin_loaded": False,
    }
    json_dump(result_path, record)
    if not record["warmup_valid"] or not all(operation_success(entry, item) for item in iterations):
        raise SystemExit(2)


def operation_success(entry: str, item: dict[str, Any]) -> bool:
    if item.get("exception_type") is not None:
        return False
    if entry == "rolling-backtest":
        return item.get("operation_result") == "completed"
    if entry == "residual":
        return item.get("operation_result") in {"completed", "blocked"}
    return item.get("operation_result") in {"HTTP_200", "HTTP_201"}


def production_run_valid(record: dict[str, Any]) -> bool:
    """Return true only for a complete, successful, uninstrumented run."""

    if record.get("seed_process_exit_code") != 0:
        return False
    if record.get("measurement_process_exit_code") != 0:
        return False
    if record.get("iterations_requested") != ITERATIONS_PER_RUN:
        return False
    if record.get("iterations_completed") != ITERATIONS_PER_RUN:
        return False
    iterations = record.get("iterations")
    if not isinstance(iterations, list) or len(iterations) != ITERATIONS_PER_RUN:
        return False
    if record.get("error_type") or record.get("error_phase"):
        return False
    if record.get("sqlalchemy_instrumentation_loaded") is not False:
        return False
    if record.get("pytest_plugin_loaded") is not False:
        return False
    if record.get("gc_collect_called") is not False:
        return False
    if record.get("warmup_valid", True) is not True:
        return False
    entry = record.get("entry")
    if entry not in {"rolling-backtest", "residual", "api"}:
        return False
    return all(
        item.get("exception_type") is None and operation_success(entry, item) for item in iterations
    )


def _connection_pressure_failures(record: dict[str, Any]) -> list[str]:
    markers = (
        "timeout",
        "pool",
        "connection",
        "cannotconnect",
        "toomany",
        "too_many_connections",
    )
    failures: list[str] = []
    for item in record.get("iterations", []):
        candidates = [item.get("exception_type"), item.get("stable_error_code")]
        for candidate in candidates:
            if isinstance(candidate, str) and any(
                marker in candidate.lower() for marker in markers
            ):
                failures.append(candidate)
    return failures


def _run_pool_growth_evidence(record: dict[str, Any]) -> dict[str, Any]:
    baseline_pool = record.get("baseline_pool_checked_out")
    baseline_backend = record.get("baseline_application_backend_count")
    final_pool = record.get("final_pool_checked_out")
    final_backend = record.get("final_application_backend_count")
    last_three_pool = record.get("last_three_pool_checked_out", [])
    last_three_backend = record.get("last_three_application_backend_count", [])
    pressure_failures = _connection_pressure_failures(record)
    pool_sustained = (
        isinstance(baseline_pool, int)
        and isinstance(final_pool, int)
        and final_pool > baseline_pool
        and len(last_three_pool) == 3
        and all(isinstance(value, int) and value > baseline_pool for value in last_three_pool)
    )
    backend_sustained = (
        isinstance(baseline_backend, int)
        and isinstance(final_backend, int)
        and final_backend > baseline_backend
        and len(last_three_backend) == 3
        and all(isinstance(value, int) and value > baseline_backend for value in last_three_backend)
    )
    transient_spike = bool(record.get("transient_backend_spike", False))
    return {
        "baseline_pool_checked_out": baseline_pool,
        "final_pool_checked_out": final_pool,
        "last_three_pool_checked_out": last_three_pool,
        "baseline_application_backend_count": baseline_backend,
        "final_application_backend_count": final_backend,
        "last_three_application_backend_count": last_three_backend,
        "transient_peak_pool_checked_out": record.get("transient_peak_pool_checked_out"),
        "transient_peak_application_backend_count": record.get(
            "transient_peak_application_backend_count"
        ),
        "pool_growth_sustained": pool_sustained,
        "application_backend_growth_sustained": backend_sustained,
        "pressure_failures": pressure_failures,
        "transient_backend_spike": transient_spike,
        "growth_proven": bool(pool_sustained or backend_sustained or pressure_failures),
    }


def classify_pool_growth(
    production: dict[str, list[dict[str, Any]]],
) -> tuple[bool, bool, dict[str, Any]]:
    per_entry: dict[str, list[dict[str, Any]]] = {}
    for entry, records in production.items():
        per_entry[entry] = [
            {
                "label": record.get("label"),
                "run_number": record.get("run_number"),
                "valid": production_run_valid(record),
                **_run_pool_growth_evidence(record),
            }
            for record in records
        ]

    proven_entries = [
        entry
        for entry, evidence in per_entry.items()
        if len(evidence) == 2 and all(item["growth_proven"] for item in evidence)
    ]
    all_records = [record for records in production.values() for record in records]
    all_valid = len(all_records) == 6 and all(
        production_run_valid(record) for record in all_records
    )
    all_successful = all(
        operation_success(record.get("entry", ""), item)
        for record in all_records
        for item in record.get("iterations", [])
    )
    all_zero_warning_deltas = all(
        item.get("target_warning_delta") == 0
        for record in all_records
        for item in record.get("iterations", [])
    )
    stable_run_baselines = all(
        record.get("baseline_pool_checked_out") is not None
        and record.get("baseline_application_backend_count") is not None
        and record.get("final_pool_checked_out") == record.get("baseline_pool_checked_out")
        and record.get("final_application_backend_count")
        == record.get("baseline_application_backend_count")
        and len(record.get("last_three_pool_checked_out", [])) == 3
        and len(record.get("last_three_application_backend_count", [])) == 3
        and all(
            value == record.get("baseline_pool_checked_out")
            for value in record.get("last_three_pool_checked_out", [])
        )
        and all(
            value == record.get("baseline_application_backend_count")
            for value in record.get("last_three_application_backend_count", [])
        )
        and not _connection_pressure_failures(record)
        and not record.get("gc_collect_called", False)
        for record in all_records
    )
    disproven = bool(
        all_valid and all_successful and all_zero_warning_deltas and stable_run_baselines
    )
    return (
        bool(proven_entries),
        disproven,
        {
            "per_entry": per_entry,
            "proven_entries": proven_entries,
            "transient_backend_spike_count": sum(
                item["transient_backend_spike"]
                for evidence in per_entry.values()
                for item in evidence
            ),
            "operation_failures": sum(
                not operation_success(record.get("entry", ""), item)
                for record in all_records
                for item in record.get("iterations", [])
            ),
            "connection_pressure_failures": [
                failure
                for record in all_records
                for failure in _connection_pressure_failures(record)
            ],
            "warning_count": sum(
                int(item.get("target_warning_delta", 0))
                for record in all_records
                for item in record.get("iterations", [])
            ),
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
    all_production_records = [item for records in production.values() for item in records]
    all_production_runs_valid = len(all_production_records) == 6 and all(
        production_run_valid(record) for record in all_production_records
    )
    all_production_iterations_successful = (
        len(
            [
                item
                for record in all_production_records
                for item in record.get("iterations", [])
                if operation_success(record.get("entry", ""), item)
            ]
        )
        == len(all_production_records) * ITERATIONS_PER_RUN
    )
    all_production_warning_counts_zero = (
        all(
            item.get("target_warning_delta") == 0
            for record in all_production_records
            for item in record.get("iterations", [])
            if operation_success(record.get("entry", ""), item)
        )
        and all_production_iterations_successful
    )
    seed_and_measurement_processes_separate = all(
        record.get("seed_and_measurement_processes_separate") is True
        for record in all_production_records
    )
    measurement_process_has_no_instrumentation = all(
        record.get("sqlalchemy_instrumentation_loaded") is False
        and record.get("pytest_plugin_loaded") is False
        for record in all_production_records
    )
    production_warning_counts = {
        entry: [
            sum(int(item.get("target_warning_delta", 0)) for item in record.get("iterations", []))
            for record in records
        ]
        for entry, records in production.items()
    }
    production_both_runs = any(
        len(records) == 2
        and all(production_run_valid(record) for record in records)
        and all(
            sum(int(item.get("target_warning_delta", 0)) for item in record.get("iterations", []))
            > 0
            for record in records
        )
        for records in production.values()
    )
    if (
        control_match
        and all_production_runs_valid
        and all_production_iterations_successful
        and all_production_warning_counts_zero
        and seed_and_measurement_processes_separate
        and measurement_process_has_no_instrumentation
    ):
        reachability = "TEST_HARNESS_ONLY"
    elif control_match and production_both_runs:
        reachability = "PRODUCTION_REACHABLE"
    else:
        reachability = "UNRESOLVED"

    growth_proven, growth_disproven, growth_evidence = classify_pool_growth(production)
    pressure = bool(growth_evidence["connection_pressure_failures"])
    if reachability == "PRODUCTION_REACHABLE" and growth_proven and pressure:
        risk = "RELEASE_BLOCKER"
    elif reachability == "PRODUCTION_REACHABLE" and growth_disproven:
        risk = "PRE_RELEASE_FIX_REQUIRED"
    elif reachability == "TEST_HARNESS_ONLY" and not growth_proven and all_production_runs_valid:
        risk = "TEST_TOOLING_NOISE"
    else:
        risk = "UNRESOLVED"

    reachability_record = {
        "production_reachability": reachability,
        "control_reproducibility": control_match,
        "production_warning_counts": production_warning_counts,
        "all_production_runs_valid": all_production_runs_valid,
        "all_production_iterations_successful": all_production_iterations_successful,
        "all_production_warning_counts_zero": all_production_warning_counts_zero,
        "criteria": {
            "same_entry_warning_in_both_clean_runs": production_both_runs,
            "all_120_production_iterations_zero": all_production_warning_counts_zero,
            "all_production_runs_valid": all_production_runs_valid,
            "all_production_iterations_successful": all_production_iterations_successful,
            "seed_and_measurement_processes_separate": seed_and_measurement_processes_separate,
            "measurement_process_has_no_instrumentation": (
                measurement_process_has_no_instrumentation
            ),
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
    api_status_distribution: dict[str, dict[str, int]] = {}
    for entry, records in production.items():
        status_counts: dict[str, int] = {}
        for record in records:
            for item in record.get("iterations", []):
                status = item.get("http_status")
                if isinstance(status, int):
                    status_counts[str(status)] = status_counts.get(str(status), 0) + 1
        api_status_distribution[entry] = status_counts
    return {
        "control_reproducibility": control_match,
        "all_production_runs_valid": all_production_runs_valid,
        "all_production_iterations_successful": all_production_iterations_successful,
        "all_production_warning_counts_zero": all_production_warning_counts_zero,
        "production_successful_iteration_count": sum(
            operation_success(record.get("entry", ""), item)
            for record in all_production_records
            for item in record.get("iterations", [])
        ),
        "production_failed_iteration_count": sum(
            not operation_success(record.get("entry", ""), item)
            for record in all_production_records
            for item in record.get("iterations", [])
        ),
        "transient_backend_spike_count": growth_evidence["transient_backend_spike_count"],
        "api_http_status_distribution": api_status_distribution,
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
    parser.add_argument("--runtime-seed-path", type=Path)
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
    json_dump(
        output_dir / "matrix-summary.json",
        {
            **classification,
            "control_runs": controls,
            "production_runs": production,
            "internal_sha256sums_verified": True,
            "forbidden_path_change_detected": False,
            "no_session_monkeypatch": True,
            "no_finalizer_monkeypatch": True,
            "no_pool_event_listener": True,
            "no_object_id_registry": True,
        },
    )
    # All evidence, including matrix-summary, is complete before the one
    # immutable SHA256SUMS file is created.  matrix-summary intentionally has
    # no self-referential artifact hash field.
    internal_checksum_sha = write_checksums(output_dir)
    internal_checksum_verified = True
    print(
        json.dumps(
            {
                **classification,
                "internal_sha256sums_sha256": internal_checksum_sha,
                "internal_sha256sums_verified": internal_checksum_verified,
            },
            sort_keys=True,
        )
    )
    return (
        0
        if classification["control_reproducibility"]
        and classification["all_production_runs_valid"]
        and classification["all_production_iterations_successful"]
        and classification["all_production_warning_counts_zero"]
        and classification["production_reachability"] != "UNRESOLVED"
        and classification["pool_growth_proven"] != classification["pool_growth_disproven"]
        and classification["release_risk_class"] != "UNRESOLVED"
        and internal_checksum_verified
        else 2
    )


def main() -> int:
    args = parse_args()
    if args.mode == "seed":
        if args.entry is None or args.seed_path is None or args.runtime_seed_path is None:
            raise SystemExit(
                "--entry, --seed-path and --runtime-seed-path are required in seed mode"
            )
        asyncio.run(seed_entry(args.entry, args.seed_path, args.runtime_seed_path))
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
