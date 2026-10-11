"""A transparent pytest plugin for SQLAlchemy async connection provenance.

This module is deliberately diagnostic-only.  It records pool, connection,
session, lifecycle-checkpoint, and targeted ``SAWarning`` evidence without
closing, rolling back, committing, or disposing anything until the final
diagnostic shutdown checkpoint.
"""

from __future__ import annotations

import asyncio
import contextvars
import gc
import hashlib
import inspect
import json
import os
import re
import threading
import time
import traceback
from collections.abc import Callable, Coroutine
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from typing import Any, TypeVar

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

_Context = dict[str, str | None]
_current_context: contextvars.ContextVar[_Context | None] = contextvars.ContextVar(
    "sqlalchemy_provenance_context", default=None
)
_controlled_gc: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "sqlalchemy_provenance_controlled_gc", default=False
)

_WarningEvent = TypeVar("_WarningEvent")


def _utc_timestamp() -> str:
    return (
        time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
        + f".{time.time_ns() % 1_000_000_000:09d}+00:00"
    )


def _safe_text(value: object, limit: int = 240) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _context_value() -> _Context:
    return _current_context.get() or {
        "nodeid": None,
        "phase": None,
        "session_id": None,
    }


def _stack(skip: int = 0) -> list[str]:
    frames: list[str] = []
    for frame in traceback.extract_stack()[: -2 - skip]:
        path = frame.filename.replace(os.getcwd(), "<repo>")
        if "sqlalchemy_connection_provenance" in path:
            continue
        frames.append(f"{path}:{frame.lineno}:{frame.name}")
    return frames[-16:]


def _task_identity(task: asyncio.Task[object] | None) -> tuple[str | None, str | None, int | None]:
    if task is None:
        return None, None, None
    collector = _ACTIVE_COLLECTOR
    if collector is None:
        return None, None, id(task)
    return collector.task_id(task), task.get_name(), id(task)


def _loop_identity(loop: asyncio.AbstractEventLoop | None) -> tuple[str | None, int | None]:
    if loop is None:
        return None, None
    collector = _ACTIVE_COLLECTOR
    if collector is None:
        return None, id(loop)
    return collector.loop_id(loop), id(loop)


def _runtime_context() -> dict[str, object]:
    task: asyncio.Task[object] | None
    loop: asyncio.AbstractEventLoop | None
    try:
        loop = asyncio.get_running_loop()
        task = asyncio.current_task(loop)
    except RuntimeError:
        loop = None
        task = None
    task_id, task_name, task_object_id = _task_identity(task)
    loop_id, loop_object_id = _loop_identity(loop)
    return {
        "task_id": task_id,
        "task_name": task_name,
        "task_object_id": task_object_id,
        "event_loop_id": loop_id,
        "event_loop_object_id": loop_object_id,
    }


def _sql_fingerprint(statement: object) -> tuple[str, str]:
    preview = _safe_text(statement, 180)
    normalized = re.sub(r"\s+", " ", preview).strip()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return digest, normalized


_ACTIVE_COLLECTOR: Collector | None = None


class Collector:
    def __init__(self, config: pytest.Config) -> None:
        output_root = os.environ.get("PROVENANCE_OUTPUT_DIR")
        if not output_root:
            raise RuntimeError("PROVENANCE_OUTPUT_DIR is required")
        self.output_root = Path(output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.run_label = os.environ.get("PROVENANCE_RUN_LABEL", "unknown")
        self.lock = threading.RLock()
        self.sequence = 0
        self.connection_sequence = 0
        self.session_sequence = 0
        self.task_sequences: dict[int, str] = {}
        self.loop_sequences: dict[int, str] = {}
        self.connections: dict[str, dict[str, Any]] = {}
        self.record_by_object_id: dict[int, str] = {}
        self.dbapi_to_connection: dict[int, str] = {}
        self.sessions: dict[str, dict[str, Any]] = {}
        self.session_by_object_id: dict[int, str] = {}
        self.checked_out: set[str] = set()
        self.pool_events: list[dict[str, Any]] = []
        self.session_events: list[dict[str, Any]] = []
        self.warning_events: list[dict[str, Any]] = []
        self.checkpoints: list[dict[str, Any]] = []
        self.test_results: list[dict[str, Any]] = []
        self._event_targets: list[tuple[object, str, Callable[..., Any]]] = []
        self._original_async_session_methods: dict[str, object] = {}
        self.engine: Any = None
        self.pool: Any = None
        self.config = config
        self.controlled_gc_warning_count = 0
        self.natural_warning_count = 0
        self.instrumentation_errors: list[str] = []
        self.started = False

    def _write_jsonl(self, filename: str, record: dict[str, Any]) -> None:
        path = self.output_root / filename
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    def _next_sequence(self) -> int:
        with self.lock:
            self.sequence += 1
            return self.sequence

    def task_id(self, task: asyncio.Task[object]) -> str:
        object_id = id(task)
        with self.lock:
            value = self.task_sequences.get(object_id)
            if value is None:
                value = f"task-{len(self.task_sequences) + 1:06d}"
                self.task_sequences[object_id] = value
            return value

    def loop_id(self, loop: asyncio.AbstractEventLoop) -> str:
        object_id = id(loop)
        with self.lock:
            value = self.loop_sequences.get(object_id)
            if value is None:
                value = f"loop-{len(self.loop_sequences) + 1:04d}"
                self.loop_sequences[object_id] = value
            return value

    def _context_record(self) -> dict[str, Any]:
        context = _context_value()
        value: dict[str, Any] = {
            "pytest_nodeid": context.get("nodeid"),
            "pytest_phase": context.get("phase"),
            **_runtime_context(),
        }
        session_id = context.get("session_id")
        if session_id:
            value["session_id"] = session_id
        return value

    def _pool_state(self) -> dict[str, Any]:
        pool = self.pool
        values: dict[str, Any] = {
            "pool_checked_out": len(self.checked_out),
            "pool_checked_in": None,
            "pool_size": None,
            "pool_overflow": None,
        }
        if pool is None:
            return values
        for key, method in (
            ("pool_checked_out", "checkedout"),
            ("pool_checked_in", "checkedin"),
            ("pool_size", "size"),
            ("pool_overflow", "overflow"),
        ):
            try:
                callable_value = getattr(pool, method, None)
                if callable(callable_value):
                    values[key] = callable_value()
            except Exception as exc:  # diagnostic must never alter the test
                values[f"{key}_error"] = type(exc).__name__
        return values

    def _checkpoint(self, name: str, *, nodeid: str | None = None) -> None:
        pending_tasks = 0
        event_loop_state = "not-running"
        try:
            loop = asyncio.get_running_loop()
            pending_tasks = len(asyncio.all_tasks(loop))
            event_loop_state = "running"
        except RuntimeError:
            pass
        active_sessions = [
            record for record in self.sessions.values() if record.get("final_state") != "closed"
        ]
        unclosed_sessions = [record for record in active_sessions if not record.get("close_called")]
        value: dict[str, Any] = {
            "sequence": self._next_sequence(),
            "timestamp": _utc_timestamp(),
            "run_label": self.run_label,
            "checkpoint": name,
            "pytest_nodeid": nodeid or _context_value().get("nodeid"),
            "active_session_count": len(active_sessions),
            "unclosed_session_count": len(unclosed_sessions),
            "active_connection_records": sorted(self.checked_out),
            "connection_records_without_checkin": sorted(self.checked_out),
            "pending_asyncio_tasks": pending_tasks,
            "event_loop_state": event_loop_state,
            **self._pool_state(),
        }
        self.checkpoints.append(value)
        self._write_jsonl("sqlalchemy-checkpoints.jsonl", value)

    def _connection_record_id(self, connection_record: Any) -> str:
        object_id = id(connection_record)
        with self.lock:
            existing = self.record_by_object_id.get(object_id)
            if existing:
                return existing
            self.connection_sequence += 1
            value = f"{self.run_label}-connection-{self.connection_sequence:06d}"
            self.record_by_object_id[object_id] = value
            self.connections[value] = {
                "run_label": self.run_label,
                "diagnostic_connection_id": value,
                "connection_record_object_id": object_id,
                "connection_record_id": f"record-{self.connection_sequence:06d}",
                "dbapi_connection_ids": [],
                "connection_record_info": {},
                "associated_session_ids": [],
                "checkout_count": 0,
                "checkin_count": 0,
                "first_connect_stack": [],
                "last_checkout_stack": [],
                "last_database_operation": None,
                "last_checkout_nodeid": None,
                "last_checkout_phase": None,
                "last_checkout_task": None,
                "last_checkout_loop": None,
                "last_checkin_timestamp": None,
                "first_event_timestamp": None,
                "last_event_timestamp": None,
            }
            return value

    def _connection_record_for_sync_connection(self, connection: Any) -> str | None:
        try:
            fairy = connection.connection
            record = getattr(fairy, "_connection_record", None)
            if record is None:
                record = getattr(fairy, "connection_record", None)
            if record is None:
                return None
            return self._connection_record_id(record)
        except Exception:
            return None

    def _ensure_record_info(self, connection_record: Any, connection_id: str) -> None:
        try:
            info = connection_record.info
            info.setdefault("diagnostic_connection_id", connection_id)
            info.setdefault("first_connect_stack", _stack())
            self.connections[connection_id]["connection_record_info"] = {
                str(key): _safe_text(value, 500) for key, value in info.items()
            }
            self.connections[connection_id]["first_connect_stack"] = info.get(
                "first_connect_stack", []
            )
        except Exception as exc:
            self.instrumentation_errors.append(f"record_info:{type(exc).__name__}")

    def _pool_event(
        self, event_name: str, connection_record: Any = None, dbapi: Any = None
    ) -> None:
        connection_id = None
        if connection_record is not None:
            connection_id = self._connection_record_id(connection_record)
            self._ensure_record_info(connection_record, connection_id)
        elif dbapi is not None:
            connection_id = self.dbapi_to_connection.get(id(dbapi))
        if connection_id is not None and dbapi is not None:
            dbapi_id = id(dbapi)
            if dbapi_id not in self.connections[connection_id]["dbapi_connection_ids"]:
                self.connections[connection_id]["dbapi_connection_ids"].append(dbapi_id)
            self.dbapi_to_connection[dbapi_id] = connection_id
        context = self._context_record()
        record = self.connections.get(connection_id) if connection_id else None
        session_id = context.get("session_id")
        if record is not None and session_id:
            if session_id not in record["associated_session_ids"]:
                record["associated_session_ids"].append(session_id)
            session = self.sessions.get(session_id)
            if session is not None and connection_id not in session["associated_connection_ids"]:
                session["associated_connection_ids"].append(connection_id)
        timestamp = _utc_timestamp()
        if record is not None:
            record["first_event_timestamp"] = record["first_event_timestamp"] or timestamp
            record["last_event_timestamp"] = timestamp
        if event_name == "checkout" and connection_id:
            self.checked_out.add(connection_id)
            if record is not None:
                record["checkout_count"] += 1
                record["last_checkout_stack"] = _stack()
                record["last_checkout_nodeid"] = context.get("pytest_nodeid")
                record["last_checkout_phase"] = context.get("pytest_phase")
                record["last_checkout_task"] = context.get("task_id")
                record["last_checkout_loop"] = context.get("event_loop_id")
        elif event_name == "checkin" and connection_id:
            self.checked_out.discard(connection_id)
            if record is not None:
                record["checkin_count"] += 1
                record["last_checkin_timestamp"] = timestamp
        elif event_name in {"close", "invalidate", "soft_invalidate", "detach", "close_detached"}:
            if connection_id and event_name != "soft_invalidate":
                self.checked_out.discard(connection_id)
        event = {
            "sequence": self._next_sequence(),
            "timestamp": timestamp,
            "run_label": self.run_label,
            "event_name": event_name,
            "engine_id": id(self.engine) if self.engine is not None else None,
            "pool_id": id(self.pool) if self.pool is not None else None,
            "connection_record_id": connection_id,
            "dbapi_connection_id": id(dbapi) if dbapi is not None else None,
            "connection_record_info": record.get("connection_record_info", {}) if record else {},
            "filtered_stack": _stack(),
            **context,
            **self._pool_state(),
        }
        self.pool_events.append(event)
        self._write_jsonl("sqlalchemy-pool-events.jsonl", event)

    def _database_operation(self, connection: Any, statement: Any) -> None:
        connection_id = self._connection_record_for_sync_connection(connection)
        if connection_id is None:
            return
        digest, preview = _sql_fingerprint(statement)
        operation = {
            "timestamp": _utc_timestamp(),
            "statement_sha256": digest,
            "statement_preview": preview,
            **self._context_record(),
        }
        record = self.connections[connection_id]
        record["last_database_operation"] = operation
        self._write_jsonl(
            "sqlalchemy-session-events.jsonl",
            {
                "sequence": self._next_sequence(),
                "event_type": "database_operation",
                "connection_record_id": connection_id,
                **operation,
            },
        )

    def _new_session(self, session: AsyncSession) -> str:
        object_id = id(session)
        existing = self.session_by_object_id.get(object_id)
        if existing:
            return existing
        self.session_sequence += 1
        session_id = f"{self.run_label}-session-{self.session_sequence:06d}"
        context = self._context_record()
        creation_stack = _stack(1)
        self.session_by_object_id[object_id] = session_id
        self.sessions[session_id] = {
            "run_label": self.run_label,
            "diagnostic_session_id": session_id,
            "session_object_id": object_id,
            "creation_timestamp": _utc_timestamp(),
            "creation_nodeid": context.get("pytest_nodeid"),
            "creation_phase": context.get("pytest_phase"),
            "creation_task": context.get("task_id"),
            "creation_loop": context.get("event_loop_id"),
            "creation_stack": creation_stack,
            "creation_owner_classification": self._classify_session_creation(creation_stack),
            "bound_engine_id": id(self.engine) if self.engine is not None else None,
            "associated_connection_ids": [],
            "transaction_state": None,
            "in_transaction": None,
            "in_nested_transaction": None,
            "last_operation": None,
            "last_operation_timestamp": None,
            "last_operation_nodeid": None,
            "last_operation_stack": [],
            "close_called": False,
            "exit_called": False,
            "commit_called": False,
            "rollback_called": False,
            "final_state": "created",
        }
        return session_id

    @staticmethod
    def _classify_session_creation(stack: list[str]) -> str:
        joined = "\n".join(stack)
        if "backend/app/db/session.py" in joined and "get_db_session" in joined:
            return "FASTAPI_GET_DB_SESSION_DEPENDENCY"
        if "backend/tests/" in joined:
            return "TEST_OR_FIXTURE"
        if "backend/app/" in joined:
            return "PRODUCTION_SERVICE_OR_APPLICATION"
        return "UNCLASSIFIED"

    def _refresh_session_state(self, session: AsyncSession, session_id: str) -> None:
        record = self.sessions[session_id]
        try:
            in_transaction = bool(session.in_transaction())
            in_nested_transaction = bool(session.in_nested_transaction())
            record["in_transaction"] = in_transaction
            record["in_nested_transaction"] = in_nested_transaction
            record["transaction_state"] = (
                "nested" if in_nested_transaction else "active" if in_transaction else "idle"
            )
        except Exception as exc:
            record["transaction_state_error"] = type(exc).__name__

    def _session_event(self, session: AsyncSession, event_name: str) -> str:
        session_id = self._new_session(session)
        record = self.sessions[session_id]
        timestamp = _utc_timestamp()
        record["last_operation"] = event_name
        record["last_operation_timestamp"] = timestamp
        context = self._context_record()
        record["last_operation_nodeid"] = context.get("pytest_nodeid")
        record["last_operation_stack"] = _stack(1)
        if event_name == "close":
            record["close_called"] = True
            record["final_state"] = "closed"
        elif event_name == "__aexit__":
            record["exit_called"] = True
        elif event_name == "commit":
            record["commit_called"] = True
        elif event_name == "rollback":
            record["rollback_called"] = True
        event_record = {
            "sequence": self._next_sequence(),
            "event_type": "session_lifecycle",
            "timestamp": timestamp,
            "run_label": self.run_label,
            "diagnostic_session_id": session_id,
            "session_object_id": id(session),
            "event_name": event_name,
            "filtered_stack": record["last_operation_stack"],
            **context,
        }
        self.session_events.append(event_record)
        self._write_jsonl("sqlalchemy-session-events.jsonl", event_record)
        return session_id

    @contextmanager
    def _session_context(self, session_id: str):
        token = _current_context.set({**_context_value(), "session_id": session_id})
        try:
            yield
        finally:
            _current_context.reset(token)

    def _wrap_async_session_methods(self) -> None:
        methods = (
            "__init__",
            "__aenter__",
            "__aexit__",
            "execute",
            "scalar",
            "scalars",
            "stream",
            "stream_scalars",
            "flush",
            "commit",
            "rollback",
            "close",
            "connection",
            "begin",
            "begin_nested",
        )
        for name in methods:
            original = getattr(AsyncSession, name, None)
            if original is None:
                continue
            self._original_async_session_methods[name] = original
            if inspect.iscoroutinefunction(original):

                async def async_wrapper(
                    session: AsyncSession,
                    *args: Any,
                    __original: Callable[..., Coroutine[Any, Any, Any]] = original,
                    __name: str = name,
                    **kwargs: Any,
                ) -> Any:
                    active = _ACTIVE_COLLECTOR
                    if active is None:
                        return await __original(session, *args, **kwargs)
                    session_id = active._session_event(session, __name)
                    with active._session_context(session_id):
                        result = await __original(session, *args, **kwargs)
                    active._refresh_session_state(session, session_id)
                    return result

                setattr(AsyncSession, name, wraps(original)(async_wrapper))
            else:

                def sync_wrapper(
                    session: AsyncSession,
                    *args: Any,
                    __original: Callable[..., Any] = original,
                    __name: str = name,
                    **kwargs: Any,
                ) -> Any:
                    active = _ACTIVE_COLLECTOR
                    if active is None:
                        return __original(session, *args, **kwargs)
                    session_id = active._session_event(session, __name)
                    with active._session_context(session_id):
                        result = __original(session, *args, **kwargs)
                    active._refresh_session_state(session, session_id)
                    return result

                setattr(AsyncSession, name, wraps(original)(sync_wrapper))

    def _restore_async_session_methods(self) -> None:
        for name, original in self._original_async_session_methods.items():
            setattr(AsyncSession, name, original)
        self._original_async_session_methods.clear()

    def _listen(self, target: object, name: str, listener: Callable[..., Any]) -> None:
        event.listen(target, name, listener)
        self._event_targets.append((target, name, listener))

    def start(self) -> None:
        global _ACTIVE_COLLECTOR
        if self.started:
            return
        from backend.app.db import session as db_session

        self.engine = db_session.engine
        self.pool = self.engine.sync_engine.pool
        _ACTIVE_COLLECTOR = self

        pool = self.pool

        def pool_listener(event_name: str):
            def listener(*args: Any, **kwargs: Any) -> None:
                connection_record = kwargs.get("connection_record")
                dbapi_connection = kwargs.get("dbapi_connection")
                if (
                    connection_record is None
                    and len(args) >= 2
                    and event_name not in {"close_detached"}
                ):
                    connection_record = args[1]
                if dbapi_connection is None and args:
                    dbapi_connection = args[0]
                self._pool_event(event_name, connection_record, dbapi_connection)

            return listener

        for name in (
            "connect",
            "first_connect",
            "checkout",
            "checkin",
            "reset",
            "close",
            "invalidate",
            "soft_invalidate",
            "detach",
            "close_detached",
        ):
            try:
                self._listen(pool, name, pool_listener(name))
            except Exception as exc:
                self.instrumentation_errors.append(f"pool_event:{name}:{type(exc).__name__}")

        try:
            self._listen(
                self.engine.sync_engine,
                "before_cursor_execute",
                lambda conn, cursor, statement, parameters, context, executemany: (
                    self._database_operation(conn, statement)
                ),
            )
        except Exception as exc:
            self.instrumentation_errors.append(f"engine_event:{type(exc).__name__}")

        self._wrap_async_session_methods()
        self.started = True
        self._checkpoint("PROCESS_START")

    def stop(self) -> None:
        global _ACTIVE_COLLECTOR
        if not self.started:
            return
        for target, name, listener in reversed(self._event_targets):
            try:
                event.remove(target, name, listener)
            except Exception as exc:
                self.instrumentation_errors.append(f"remove_event:{name}:{type(exc).__name__}")
        self._event_targets.clear()
        self._restore_async_session_methods()
        _ACTIVE_COLLECTOR = None
        self.started = False

    def warning_recorded(self, warning_message: Any, when: str, nodeid: str) -> None:
        message = str(warning_message.message)
        if "The garbage collector is trying to clean up non-checked-in connection" not in message:
            return
        controlled = _controlled_gc.get()
        if controlled:
            self.controlled_gc_warning_count += 1
        else:
            self.natural_warning_count += 1
        active_records = sorted(self.checked_out)
        candidates = sorted(
            {
                session_id
                for connection_id in active_records
                for session_id in self.connections.get(connection_id, {}).get(
                    "associated_session_ids", []
                )
            }
        )
        nearest_checkout = None
        nearest_operation = None
        for connection_id in active_records:
            record = self.connections.get(connection_id, {})
            if record.get("last_checkout_stack"):
                nearest_checkout = connection_id
            if record.get("last_database_operation"):
                nearest_operation = connection_id
        location = getattr(warning_message, "filename", None) or ""
        lineno = getattr(warning_message, "lineno", None)
        event_record = {
            "warning_sequence": self._next_sequence(),
            "timestamp": _utc_timestamp(),
            "run_label": self.run_label,
            "raw_message": message,
            "source_filename": str(location),
            "source_line": lineno,
            "pytest_nodeid": nodeid,
            "pytest_phase": when,
            "controlled_gc": controlled,
            "currently_checked_out_connection_ids": active_records,
            "candidate_session_ids": candidates,
            "nearest_checkout_before_warning": nearest_checkout,
            "nearest_database_operation_before_warning": nearest_operation,
            "pool_state_before_warning": self._pool_state(),
            **_runtime_context(),
            "filtered_stack": _stack(),
        }
        self.warning_events.append(event_record)
        self._write_jsonl("sqlalchemy-warning-events.jsonl", event_record)

    def run_checkpoint(self, name: str, nodeid: str | None = None) -> None:
        self._checkpoint(name, nodeid=nodeid)

    def controlled_shutdown(self) -> None:
        self._checkpoint("PYTEST_SESSION_FINISH")
        self._checkpoint("BEFORE_CONTROLLED_GC")
        token = _controlled_gc.set(True)
        try:
            gc.collect()
        finally:
            _controlled_gc.reset(token)
        self._checkpoint("AFTER_CONTROLLED_GC")
        self._checkpoint("BEFORE_ENGINE_DISPOSE")
        if self.engine is not None:
            try:
                asyncio.run(self.engine.dispose())
            except RuntimeError as exc:
                self.instrumentation_errors.append(f"engine_dispose:{type(exc).__name__}")
            except Exception as exc:
                self.instrumentation_errors.append(f"engine_dispose:{type(exc).__name__}")
        self._checkpoint("AFTER_ENGINE_DISPOSE")
        self._checkpoint("PROCESS_EXIT")

    def final_summary(self, exitstatus: int) -> dict[str, Any]:
        return {
            "run_label": self.run_label,
            "exitstatus": exitstatus,
            "natural_warning_count": self.natural_warning_count,
            "controlled_gc_warning_count": self.controlled_gc_warning_count,
            "connection_record_count": len(self.connections),
            "checkout_event_count": sum(
                1 for e in self.pool_events if e["event_name"] == "checkout"
            ),
            "checkin_event_count": sum(1 for e in self.pool_events if e["event_name"] == "checkin"),
            "unreturned_connection_record_ids": sorted(self.checked_out),
            "session_record_count": len(self.sessions),
            "instrumentation_errors": self.instrumentation_errors,
        }


def _collector(config: pytest.Config) -> Collector:
    value = getattr(config, "_sqlalchemy_provenance_collector", None)
    if not isinstance(value, Collector):
        raise RuntimeError("SQLAlchemy provenance collector is not configured")
    return value


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("sqlalchemy-connection-provenance")
    group.addoption(
        "--provenance-output-dir",
        action="store",
        default=None,
        help="output directory for diagnostic provenance records",
    )


def pytest_configure(config: pytest.Config) -> None:
    output_dir = config.getoption("--provenance-output-dir")
    if output_dir:
        os.environ["PROVENANCE_OUTPUT_DIR"] = output_dir
    collector = Collector(config)
    config._sqlalchemy_provenance_collector = collector  # type: ignore[attr-defined]
    collector.start()


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_setup(item: pytest.Item):
    collector = _collector(item.config)
    token = _current_context.set({"nodeid": item.nodeid, "phase": "setup", "session_id": None})
    collector.run_checkpoint("TEST_SETUP_START", item.nodeid)
    outcome = yield
    collector.run_checkpoint("TEST_SETUP_END", item.nodeid)
    _current_context.reset(token)
    outcome.get_result()


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_call(item: pytest.Item):
    collector = _collector(item.config)
    token = _current_context.set({"nodeid": item.nodeid, "phase": "call", "session_id": None})
    collector.run_checkpoint("TEST_CALL_START", item.nodeid)
    outcome = yield
    collector.run_checkpoint("TEST_CALL_END", item.nodeid)
    _current_context.reset(token)
    outcome.get_result()


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_teardown(item: pytest.Item):
    collector = _collector(item.config)
    token = _current_context.set({"nodeid": item.nodeid, "phase": "teardown", "session_id": None})
    collector.run_checkpoint("TEST_TEARDOWN_START", item.nodeid)
    outcome = yield
    collector.run_checkpoint("TEST_TEARDOWN_END", item.nodeid)
    collector.run_checkpoint("AFTER_FIXTURE_FINALIZERS", item.nodeid)
    _current_context.reset(token)
    outcome.get_result()


def pytest_warning_recorded(
    warning_message: Any,
    when: str,
    nodeid: str,
    location: tuple[str, int, str] | None,
) -> None:
    collector = _ACTIVE_COLLECTOR
    if collector is not None:
        collector.warning_recorded(warning_message, when, nodeid)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    collector = _collector(session.config)
    collector.controlled_shutdown()
    (collector.output_root / "connection-records.json").write_text(
        json.dumps(list(collector.connections.values()), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (collector.output_root / "session-records.json").write_text(
        json.dumps(list(collector.sessions.values()), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (collector.output_root / "run-summary.json").write_text(
        json.dumps(collector.final_summary(exitstatus), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def pytest_unconfigure(config: pytest.Config) -> None:
    collector = getattr(config, "_sqlalchemy_provenance_collector", None)
    if isinstance(collector, Collector):
        collector.stop()
