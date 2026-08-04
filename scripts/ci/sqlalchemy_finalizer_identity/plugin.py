"""Pre-finalizer SQLAlchemy connection identity capture.

This pytest plugin is evidence-only. It wraps the SQLAlchemy 2.0.51
pool.base._finalize_fairy function and records the state that exists
immediately before SQLAlchemy emits its async garbage-collection warning.
The wrapper forwards the original arguments, return value, exceptions, and
cleanup behavior unchanged.

The plugin deliberately does not close, rollback, commit, check in, dispose,
or otherwise repair any object. It also does not install warning filters.
"""

from __future__ import annotations

import asyncio
import contextvars
import hashlib
import inspect
import json
import os
import re
import threading
import time
import traceback
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy.pool import base as pool_base

WARNING_TEXT = "The garbage collector is trying to clean up non-checked-in connection"

_CONTEXT: contextvars.ContextVar[dict[str, str | None] | None] = contextvars.ContextVar(
    "sqlalchemy_finalizer_identity_context", default=None
)
_ACTIVE: Collector | None = None


def _timestamp() -> str:
    return (
        time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
        + f".{time.time_ns() % 1_000_000_000:09d}+00:00"
    )


def _safe_value(value: object, depth: int = 0) -> object:
    """Make diagnostic values JSON-safe without invoking rich object reprs."""

    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if depth > 3:
        return {"type": type(value).__name__, "object_id": id(value)}
    if isinstance(value, dict):
        return {str(key): _safe_value(item, depth + 1) for key, item in list(value.items())[:64]}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_safe_value(item, depth + 1) for item in list(value)[:64]]
    return {"type": type(value).__name__, "object_id": id(value)}


def _safe_attr(obj: object, name: str) -> object:
    try:
        return _safe_value(getattr(obj, name))
    except Exception as exc:
        return {"unavailable": type(exc).__name__}


def _stack(skip: int = 0) -> list[str]:
    result: list[str] = []
    package_marker = "sqlalchemy_finalizer_identity"
    cwd = os.getcwd()
    for frame in traceback.extract_stack()[: -2 - skip]:
        filename = frame.filename.replace(cwd, "<repo>")
        if package_marker in filename:
            continue
        result.append(f"{filename}:{frame.lineno}:{frame.name}")
    return result[-24:]


def _runtime_identity(collector: Collector) -> dict[str, object]:
    loop: asyncio.AbstractEventLoop | None
    task: asyncio.Task[object] | None
    try:
        loop = asyncio.get_running_loop()
        task = asyncio.current_task(loop)
    except RuntimeError:
        loop = None
        task = None
    task_id = collector.task_id(task) if task is not None else None
    loop_id = collector.loop_id(loop) if loop is not None else None
    return {
        "asyncio_task_id": task_id,
        "event_loop_id": loop_id,
        "thread_id": threading.get_ident(),
        "process_id": os.getpid(),
        "asyncio_task_object_id": id(task) if task is not None else None,
        "event_loop_object_id": id(loop) if loop is not None else None,
    }


def _fingerprint(statement: object) -> dict[str, str]:
    preview = re.sub(r"\s+", " ", str(statement)).strip()[:240]
    return {
        "sha256": hashlib.sha256(preview.encode("utf-8")).hexdigest(),
        "normalized_preview": preview,
    }


class Collector:
    def __init__(self, config: pytest.Config) -> None:
        output = config.getoption("--finalizer-output-dir") or os.environ.get(
            "SQLALCHEMY_FINALIZER_OUTPUT_DIR"
        )
        if not output:
            raise RuntimeError("SQLALCHEMY_FINALIZER_OUTPUT_DIR is required")
        self.output_root = Path(output)
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.run_label = os.environ.get("SQLALCHEMY_FINALIZER_RUN_LABEL", "unknown")
        self.lock = threading.RLock()
        self.sequence = 0
        self.connection_sequence = 0
        self.session_sequence = 0
        self.task_sequences: dict[int, str] = {}
        self.loop_sequences: dict[int, str] = {}
        self.connections: dict[str, dict[str, Any]] = {}
        self.connection_by_object_id: dict[int, str] = {}
        self.dbapi_to_connection: dict[int, str] = {}
        self.sessions: dict[str, dict[str, Any]] = {}
        self.session_by_object_id: dict[int, str] = {}
        self.sync_session_to_async: dict[int, str] = {}
        self.pool_events: list[dict[str, Any]] = []
        self.session_events: list[dict[str, Any]] = []
        self.finalizer_events: list[dict[str, Any]] = []
        self.warning_events: list[dict[str, Any]] = []
        self.warning_observations: list[dict[str, Any]] = []
        self._event_targets: list[tuple[object, str, Callable[..., Any]]] = []
        self._original_finalizer: Callable[..., Any] | None = None
        self._original_async_methods: dict[str, object] = {}
        self._original_sync_methods: dict[str, object] = {}
        self._original_async_init: object | None = None
        self._original_sync_init: object | None = None
        self.engine: Any = None
        self.pool: Any = None
        self.started = False
        self.persisted = False
        self.exitstatus = 0
        self.instrumentation_errors: list[str] = []
        self.warning_hook_count = 0
        self._live_handle = (self.output_root / "finalizer-events.live.jsonl").open(
            "a", encoding="utf-8"
        )
        self._last_context: dict[str, str | None] = {
            "pytest_nodeid": None,
            "pytest_phase": None,
            "session_id": None,
        }
        self.pool_start = self._empty_pool_state()
        self.pool_end = self._empty_pool_state()
        self.pool_max_checked_out = 0

    def next_sequence(self) -> int:
        with self.lock:
            self.sequence += 1
            return self.sequence

    def task_id(self, task: asyncio.Task[object] | None) -> str | None:
        if task is None:
            return None
        object_id = id(task)
        with self.lock:
            if object_id not in self.task_sequences:
                self.task_sequences[object_id] = f"task-{len(self.task_sequences) + 1:06d}"
            return self.task_sequences[object_id]

    def loop_id(self, loop: asyncio.AbstractEventLoop | None) -> str | None:
        if loop is None:
            return None
        object_id = id(loop)
        with self.lock:
            if object_id not in self.loop_sequences:
                self.loop_sequences[object_id] = f"loop-{len(self.loop_sequences) + 1:04d}"
            return self.loop_sequences[object_id]

    def context(self) -> dict[str, str | None]:
        value = dict(self._last_context)
        current = _CONTEXT.get()
        if current is not None:
            value.update(current)
        return value

    def set_context(self, nodeid: str | None, phase: str | None) -> None:
        self._last_context = {
            "pytest_nodeid": nodeid,
            "pytest_phase": phase,
            "session_id": None,
        }

    def _empty_pool_state(self) -> dict[str, object]:
        return {
            "pool_object_id": id(self.pool) if self.pool is not None else None,
            "pool_checked_out": None,
            "pool_checked_in": None,
            "pool_overflow": None,
        }

    def pool_state(self, pool: object | None = None) -> dict[str, object]:
        target = pool or self.pool
        state: dict[str, object] = {
            "pool_object_id": id(target) if target is not None else None,
            "pool_checked_out": None,
            "pool_checked_in": None,
            "pool_overflow": None,
        }
        if target is None:
            return state
        for field, method in (
            ("pool_checked_out", "checkedout"),
            ("pool_checked_in", "checkedin"),
            ("pool_overflow", "overflow"),
        ):
            try:
                value = getattr(target, method)
                state[field] = value() if callable(value) else value
            except Exception as exc:
                state[f"{field}_error"] = type(exc).__name__
        return state

    def _write_live(self, value: dict[str, Any]) -> None:
        line = json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"
        with self.lock:
            self._live_handle.write(line)
            self._live_handle.flush()

    def _connection_id(self, record: object) -> str:
        object_id = id(record)
        existing = self.connection_by_object_id.get(object_id)
        if existing is not None:
            return existing
        self.connection_sequence += 1
        value = f"{self.run_label}-connection-{self.connection_sequence:06d}"
        self.connection_by_object_id[object_id] = value
        self.connections[value] = {
            "connection_record_id": value,
            "connection_record_object_id": object_id,
            "run_label": self.run_label,
            "dbapi_connection_object_ids": [],
            "driver_connection_object_ids": [],
            "connection_record_info": {},
            "connection_record_in_use": None,
            "connection_record_fresh": None,
            "connection_record_starttime": None,
            "checkout_stack": [],
            "checkout_count": 0,
            "checkin_count": 0,
            "current_session_ids": [],
            "last_known_session_id": None,
            "last_session_operation": None,
            "last_database_statement_fingerprint": None,
            "explicit_close_seen": False,
            "checkin_seen": False,
            "first_connect_timestamp": None,
            "last_checkout_timestamp": None,
            "last_checkin_timestamp": None,
            "last_event_timestamp": None,
        }
        return value

    def _driver_id(self, dbapi: object | None) -> int | None:
        if dbapi is None:
            return None
        for name in ("driver_connection", "_connection", "connection"):
            try:
                value = getattr(dbapi, name)
            except Exception:
                continue
            if value is not None and value is not dbapi:
                return id(value)
        return None

    def _record_snapshot(self, record: object, connection_id: str) -> None:
        value = self.connections[connection_id]
        value["connection_record_info"] = _safe_value(getattr(record, "info", {}))
        value["connection_record_in_use"] = _safe_attr(record, "in_use")
        value["connection_record_fresh"] = _safe_attr(record, "fresh")
        value["connection_record_starttime"] = _safe_attr(record, "starttime")

    def _session_for_context(self) -> str | None:
        return self.context().get("session_id")

    def _associate(self, connection_id: str, session_id: str | None) -> None:
        if session_id is None:
            return
        record = self.connections[connection_id]
        if session_id not in record["current_session_ids"]:
            record["current_session_ids"].append(session_id)
        record["last_known_session_id"] = session_id
        session = self.sessions.get(session_id)
        if session is not None and connection_id not in session["connection_record_ids"]:
            session["connection_record_ids"].append(connection_id)

    def pool_event(
        self, name: str, record: object | None, dbapi: object | None, args: tuple[Any, ...]
    ) -> None:
        connection_id: str | None = None
        if record is not None:
            connection_id = self._connection_id(record)
            self._record_snapshot(record, connection_id)
        if dbapi is not None:
            dbapi_id = id(dbapi)
            if connection_id is None:
                connection_id = self.dbapi_to_connection.get(dbapi_id)
            if connection_id is not None:
                self.dbapi_to_connection[dbapi_id] = connection_id
                target = self.connections[connection_id]
                if dbapi_id not in target["dbapi_connection_object_ids"]:
                    target["dbapi_connection_object_ids"].append(dbapi_id)
                driver_id = self._driver_id(dbapi)
                if (
                    driver_id is not None
                    and driver_id not in target["driver_connection_object_ids"]
                ):
                    target["driver_connection_object_ids"].append(driver_id)
        context = self.context()
        session_id = context.get("session_id")
        if connection_id is not None:
            self._associate(connection_id, session_id)
            target = self.connections[connection_id]
            now = _timestamp()
            target["last_event_timestamp"] = now
            if name == "connect":
                target["first_connect_timestamp"] = target["first_connect_timestamp"] or now
            elif name == "checkout":
                target["checkout_count"] += 1
                target["last_checkout_timestamp"] = now
                target["checkout_stack"] = _stack(1)
                target["checkin_seen"] = False
            elif name == "checkin":
                target["checkin_count"] += 1
                target["last_checkin_timestamp"] = now
                target["checkin_seen"] = True
            elif name in {"close", "close_detached"}:
                target["explicit_close_seen"] = True
        state = self.pool_state()
        checked_out = state.get("pool_checked_out")
        if isinstance(checked_out, int):
            self.pool_max_checked_out = max(self.pool_max_checked_out, checked_out)
        self.pool_events.append(
            {
                "sequence": self.next_sequence(),
                "timestamp": _timestamp(),
                "event_name": name,
                "connection_record_id": connection_id,
                "dbapi_connection_object_id": id(dbapi) if dbapi is not None else None,
                "driver_connection_object_id": self._driver_id(dbapi),
                "pytest_nodeid": context.get("pytest_nodeid"),
                "pytest_phase": context.get("pytest_phase"),
                "session_id": session_id,
                "pool_state": state,
                "argument_count": len(args),
            }
        )

    def _record_from_sync_connection(self, connection: object) -> str | None:
        try:
            fairy = connection.connection  # type: ignore[attr-defined]
            record = getattr(fairy, "_connection_record", None)
            if record is None:
                record = getattr(fairy, "connection_record", None)
            return self._connection_id(record) if record is not None else None
        except Exception:
            return None

    def database_operation(self, connection: object, statement: object) -> None:
        connection_id = self._record_from_sync_connection(connection)
        if connection_id is None:
            return
        operation = _fingerprint(statement)
        operation["timestamp"] = _timestamp()
        operation["pytest_nodeid"] = self.context().get("pytest_nodeid")
        operation["pytest_phase"] = self.context().get("pytest_phase")
        session_id = self._session_for_context()
        self._associate(connection_id, session_id)
        record = self.connections[connection_id]
        record["last_database_statement_fingerprint"] = operation
        if session_id in self.sessions:
            session = self.sessions[session_id]
            session["last_database_statement_fingerprint"] = operation
            session["last_operation"] = "database_operation"
            session["last_operation_timestamp"] = operation["timestamp"]

    def register_session(self, session: object, kind: str) -> str:
        object_id = id(session)
        existing = self.session_by_object_id.get(object_id)
        if existing is not None:
            return existing
        self.session_sequence += 1
        value = f"{self.run_label}-session-{self.session_sequence:06d}"
        context = self.context()
        self.session_by_object_id[object_id] = value
        self.sessions[value] = {
            "session_id": value,
            "session_object_id": object_id,
            "session_kind": kind,
            "run_label": self.run_label,
            "creation_timestamp": _timestamp(),
            "creation_nodeid": context.get("pytest_nodeid"),
            "creation_phase": context.get("pytest_phase"),
            "creation_stack": _stack(1),
            "connection_record_ids": [],
            "last_operation": None,
            "last_operation_timestamp": None,
            "last_database_statement_fingerprint": None,
            "close_seen": False,
            "exit_seen": False,
            "rollback_seen": False,
            "commit_seen": False,
        }
        if kind == "AsyncSession":
            try:
                sync_session = session.sync_session  # type: ignore[attr-defined]
                self.sync_session_to_async[id(sync_session)] = value
            except Exception:
                pass
        return value

    def session_event(self, session: object, name: str) -> str:
        session_id = self.register_session(
            session, "AsyncSession" if isinstance(session, AsyncSession) else "Session"
        )
        record = self.sessions[session_id]
        now = _timestamp()
        record["last_operation"] = name
        record["last_operation_timestamp"] = now
        if name == "close":
            record["close_seen"] = True
        elif name == "__aexit__":
            record["exit_seen"] = True
        elif name == "rollback":
            record["rollback_seen"] = True
        elif name == "commit":
            record["commit_seen"] = True
        for connection_id in record["connection_record_ids"]:
            connection = self.connections.get(connection_id)
            if connection is None:
                continue
            connection["last_known_session_id"] = session_id
            connection["last_session_operation"] = name
            if name in {"close", "__aexit__"}:
                connection["explicit_close_seen"] = True
        self.session_events.append(
            {
                "sequence": self.next_sequence(),
                "timestamp": now,
                "event_name": name,
                "session_id": session_id,
                "session_object_id": id(session),
                "pytest_nodeid": self.context().get("pytest_nodeid"),
                "pytest_phase": self.context().get("pytest_phase"),
                "creation_stack": record["creation_stack"],
            }
        )
        return session_id

    def push_session_context(self, session_id: str) -> contextvars.Token:
        current = self.context()
        current["session_id"] = session_id
        return _CONTEXT.set(current)

    def _wrap_async_sessions(self) -> None:
        self._original_async_init = AsyncSession.__init__
        original_init = self._original_async_init

        def init_wrapper(session: AsyncSession, *args: Any, **kwargs: Any) -> Any:
            result = original_init(session, *args, **kwargs)  # type: ignore[misc]
            active = _ACTIVE
            if active is not None:
                active.register_session(session, "AsyncSession")
            return result

        AsyncSession.__init__ = wraps(original_init)(init_wrapper)
        method_names = (
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
        for name in method_names:
            original = getattr(AsyncSession, name, None)
            if original is None:
                continue
            self._original_async_methods[name] = original
            if inspect.iscoroutinefunction(original):

                async def async_wrapper(
                    session: AsyncSession,
                    *args: Any,
                    __original: Callable[..., Any] = original,
                    __name: str = name,
                    **kwargs: Any,
                ) -> Any:
                    active = _ACTIVE
                    if active is None:
                        return await __original(session, *args, **kwargs)
                    session_id = active.session_event(session, __name)
                    token = active.push_session_context(session_id)
                    try:
                        return await __original(session, *args, **kwargs)
                    finally:
                        _CONTEXT.reset(token)

                setattr(AsyncSession, name, wraps(original)(async_wrapper))
            else:

                def sync_wrapper(
                    session: AsyncSession,
                    *args: Any,
                    __original: Callable[..., Any] = original,
                    __name: str = name,
                    **kwargs: Any,
                ) -> Any:
                    active = _ACTIVE
                    if active is None:
                        return __original(session, *args, **kwargs)
                    session_id = active.session_event(session, __name)
                    token = active.push_session_context(session_id)
                    try:
                        return __original(session, *args, **kwargs)
                    finally:
                        _CONTEXT.reset(token)

                setattr(AsyncSession, name, wraps(original)(sync_wrapper))

    def _wrap_sync_sessions(self) -> None:
        self._original_sync_init = Session.__init__
        original_init = self._original_sync_init

        def init_wrapper(session: Session, *args: Any, **kwargs: Any) -> Any:
            result = original_init(session, *args, **kwargs)  # type: ignore[misc]
            active = _ACTIVE
            if active is not None:
                active.register_session(session, "Session")
            return result

        Session.__init__ = wraps(original_init)(init_wrapper)
        for name in ("execute", "scalar", "scalars", "flush", "commit", "rollback", "close"):
            original = getattr(Session, name, None)
            if original is None:
                continue
            self._original_sync_methods[name] = original

            def sync_wrapper(
                session: Session,
                *args: Any,
                __original: Callable[..., Any] = original,
                __name: str = name,
                **kwargs: Any,
            ) -> Any:
                active = _ACTIVE
                if active is None:
                    return __original(session, *args, **kwargs)
                session_id = active.session_event(session, __name)
                token = active.push_session_context(session_id)
                try:
                    return __original(session, *args, **kwargs)
                finally:
                    _CONTEXT.reset(token)

            setattr(Session, name, wraps(original)(sync_wrapper))

    def _warning_message(self, dbapi: object, pool: object) -> str:
        dialect = pool._dialect
        has_terminate = bool(getattr(dialect, "has_terminate", False))
        action = "terminated" if has_terminate else "dropped, as it cannot be safely terminated"
        return (
            "The garbage collector is trying to clean up "
            f"non-checked-in connection {dbapi!r}, which will be {action}.  "
            "Please ensure that SQLAlchemy pooled connections are returned to "
            "the pool explicitly, either by calling " + chr(96) * 2 + "close()" + chr(96) * 2 + " "
            "or by using appropriate context managers to manage their lifecycle."
        )

    def capture_finalizer(self, arguments: dict[str, Any]) -> None:
        record = arguments.get("connection_record")
        pool = arguments.get("pool")
        ref = arguments.get("ref")
        fairy = arguments.get("fairy")
        initial_dbapi = arguments.get("dbapi_connection")
        is_gc_cleanup = ref is not None
        is_async = False
        try:
            is_async = bool(pool._dialect.is_async)
        except Exception:
            self.instrumentation_errors.append("finalizer:dialect")
        actual_dbapi = initial_dbapi
        if is_gc_cleanup and record is not None:
            try:
                if record.fairy_ref is not ref:
                    return
                actual_dbapi = record.dbapi_connection
            except Exception:
                actual_dbapi = initial_dbapi
        warning = bool(
            is_gc_cleanup and is_async and record is not None and actual_dbapi is not None
        )
        connection_id = self._connection_id(record) if record is not None else None
        if connection_id is not None:
            self._record_snapshot(record, connection_id)
        connection = self.connections.get(connection_id) if connection_id else None
        last_session_id = connection.get("last_known_session_id") if connection else None
        session = self.sessions.get(last_session_id) if last_session_id else None
        weak_target = None
        if fairy is not None:
            fairy_object_id = id(fairy)
        elif ref is not None:
            try:
                weak_target = ref()
                fairy_object_id = id(weak_target) if weak_target is not None else None
            except Exception:
                fairy_object_id = None
        else:
            fairy_object_id = None
        if weak_target is not None:
            del weak_target
        detach = (record is None or is_gc_cleanup) if is_async else record is None
        event_record: dict[str, Any] = {
            "finalizer_sequence": self.next_sequence(),
            "timestamp": _timestamp(),
            "run_label": self.run_label,
            "pytest_nodeid": self.context().get("pytest_nodeid"),
            "pytest_phase": self.context().get("pytest_phase"),
            **_runtime_identity(self),
            "fairy_object_id": fairy_object_id,
            "connection_record_id": connection_id,
            "connection_record_object_id": id(record) if record is not None else None,
            "dbapi_connection_object_id": id(actual_dbapi) if actual_dbapi is not None else None,
            "driver_connection_object_id": self._driver_id(actual_dbapi),
            "connection_record_info": (
                connection.get("connection_record_info") if connection else {}
            ),
            "connection_record_in_use": (
                connection.get("connection_record_in_use") if connection else None
            ),
            "connection_record_fresh": (
                connection.get("connection_record_fresh") if connection else None
            ),
            "connection_record_starttime": (
                connection.get("connection_record_starttime") if connection else None
            ),
            **self.pool_state(pool),
            "transaction_was_reset": bool(arguments.get("transaction_was_reset", False)),
            "asyncio_safe": not is_gc_cleanup if is_async else True,
            "detach_state": "GC_CLEANUP" if is_gc_cleanup else "EXPLICIT_FINALIZE",
            "terminate_only": detach,
            "explicit_close_seen": (
                bool(connection.get("explicit_close_seen")) if connection else False
            ),
            "checkin_seen": bool(connection.get("checkin_seen")) if connection else False,
            "checkout_stack": connection.get("checkout_stack", []) if connection else [],
            "session_creation_stack": session.get("creation_stack", []) if session else [],
            "last_session_operation": (
                session.get("last_operation")
                if session
                else connection.get("last_session_operation")
                if connection
                else None
            ),
            "last_database_statement_fingerprint": (
                session.get("last_database_statement_fingerprint")
                if session and session.get("last_database_statement_fingerprint") is not None
                else connection.get("last_database_statement_fingerprint")
                if connection
                else None
            ),
            "last_known_session_id": last_session_id,
            "finalizer_call_stack": _stack(0),
            "warning_will_be_emitted": warning,
            "warning_message": self._warning_message(actual_dbapi, pool)
            if warning and pool is not None
            else None,
        }
        self.finalizer_events.append(event_record)
        if warning:
            self.warning_events.append(event_record)
        # This is intentionally before the call to the real finalizer. The
        # real implementation removes the weakref mapping and may detach the
        # record before pytest observes the warning.
        self._write_live(event_record)

    def _install_finalizer(self) -> None:
        original = pool_base._finalize_fairy
        self._original_finalizer = original

        @wraps(original)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            try:
                bound = inspect.signature(original).bind_partial(*args, **kwargs)
                self.capture_finalizer(dict(bound.arguments))
            except Exception as exc:
                self.instrumentation_errors.append(f"finalizer_capture:{type(exc).__name__}")
            return original(*args, **kwargs)

        pool_base._finalize_fairy = wrapped  # type: ignore[assignment]

    def start(self) -> None:
        global _ACTIVE
        if self.started:
            return
        self._install_finalizer()
        from backend.app.db import session as db_session

        self.engine = db_session.engine
        self.pool = self.engine.sync_engine.pool
        self.pool_start = self.pool_state()
        _ACTIVE = self

        def listener_factory(name: str) -> Callable[..., None]:
            def listener(*args: Any, **kwargs: Any) -> None:
                record = kwargs.get("connection_record")
                dbapi = kwargs.get("dbapi_connection")
                if dbapi is None and args:
                    dbapi = args[0]
                if record is None and len(args) >= 2 and name != "close_detached":
                    record = args[1]
                self.pool_event(name, record, dbapi, args)

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
            listener = listener_factory(name)
            try:
                event.listen(self.pool, name, listener)
                self._event_targets.append((self.pool, name, listener))
            except Exception as exc:
                self.instrumentation_errors.append(f"pool_listener:{name}:{type(exc).__name__}")

        try:

            def before_cursor_execute(
                connection: Any,
                cursor: Any,
                statement: Any,
                parameters: Any,
                context: Any,
                executemany: Any,
            ) -> None:
                self.database_operation(connection, statement)

            event.listen(self.engine.sync_engine, "before_cursor_execute", before_cursor_execute)
            self._event_targets.append(
                (self.engine.sync_engine, "before_cursor_execute", before_cursor_execute)
            )
        except Exception as exc:
            self.instrumentation_errors.append(f"engine_listener:{type(exc).__name__}")

        self._wrap_async_sessions()
        self._wrap_sync_sessions()
        self.started = True

    def warning_recorded(
        self, warning_message: Any, when: str, nodeid: str, location: object
    ) -> None:
        message = str(warning_message.message)
        if WARNING_TEXT not in message:
            return
        self.warning_hook_count += 1
        observed = {
            "warning_observation_sequence": self.next_sequence(),
            "timestamp": _timestamp(),
            "message": message,
            "when": when,
            "nodeid": nodeid,
            "filename": str(getattr(warning_message, "filename", "")),
            "line": getattr(warning_message, "lineno", None),
        }
        unobserved = [
            event for event in self.warning_events if event.get("warning_observed_at") is None
        ]
        if unobserved:
            event = unobserved[0]
            event["warning_observed_at"] = observed["timestamp"]
            event["warning_source_filename"] = observed["filename"]
            event["warning_source_line"] = observed["line"]
            event["warning_observed_when"] = when
            event["warning_observed_nodeid"] = nodeid
            observed["finalizer_sequence"] = event.get("finalizer_sequence")
        else:
            observed["finalizer_sequence"] = None
        self.warning_observations.append(observed)

    def persist(self, exitstatus: int) -> None:
        if self.persisted:
            return
        self.persisted = True
        self.pool_end = self.pool_state()
        (self.output_root / "finalizer-events.json").write_text(
            json.dumps(self.finalizer_events, indent=2, sort_keys=True), encoding="utf-8"
        )
        (self.output_root / "connection-identity-map.json").write_text(
            json.dumps(list(self.connections.values()), indent=2, sort_keys=True), encoding="utf-8"
        )
        (self.output_root / "session-identity-map.json").write_text(
            json.dumps(list(self.sessions.values()), indent=2, sort_keys=True), encoding="utf-8"
        )
        (self.output_root / "warning-observations.json").write_text(
            json.dumps(self.warning_observations, indent=2, sort_keys=True), encoding="utf-8"
        )
        (self.output_root / "run-summary.json").write_text(
            json.dumps(
                {
                    "run_label": self.run_label,
                    "exitstatus": exitstatus,
                    "finalizer_event_count": len(self.finalizer_events),
                    "finalizer_warning_event_count": len(self.warning_events),
                    "pytest_warning_hook_count": self.warning_hook_count,
                    "connection_record_count": len(self.connections),
                    "dbapi_connection_count": len(
                        {
                            item
                            for record in self.connections.values()
                            for item in record["dbapi_connection_object_ids"]
                        }
                    ),
                    "session_record_count": len(self.sessions),
                    "pool_start": self.pool_start,
                    "pool_end": self.pool_end,
                    "pool_max_checked_out": self.pool_max_checked_out,
                    "instrumentation_errors": self.instrumentation_errors,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    def stop(self) -> None:
        global _ACTIVE
        if not self.started:
            return
        for target, name, listener in reversed(self._event_targets):
            try:
                event.remove(target, name, listener)
            except Exception as exc:
                self.instrumentation_errors.append(f"remove_listener:{name}:{type(exc).__name__}")
        self._event_targets.clear()
        if self._original_finalizer is not None:
            pool_base._finalize_fairy = self._original_finalizer  # type: ignore[assignment]
        for name, original in self._original_async_methods.items():
            setattr(AsyncSession, name, original)
        if self._original_async_init is not None:
            AsyncSession.__init__ = self._original_async_init
        for name, original in self._original_sync_methods.items():
            setattr(Session, name, original)
        if self._original_sync_init is not None:
            Session.__init__ = self._original_sync_init
        self._original_async_methods.clear()
        self._original_sync_methods.clear()
        _ACTIVE = None
        self.started = False
        self._live_handle.flush()
        self._live_handle.close()


def _collector(config: pytest.Config) -> Collector:
    value = getattr(config, "_sqlalchemy_finalizer_collector", None)
    if not isinstance(value, Collector):
        raise RuntimeError("SQLAlchemy finalizer collector is unavailable")
    return value


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("sqlalchemy-finalizer-identity")
    group.addoption(
        "--finalizer-output-dir",
        action="store",
        default=None,
        help="directory for pre-finalizer identity evidence",
    )


def pytest_configure(config: pytest.Config) -> None:
    collector = Collector(config)
    config._sqlalchemy_finalizer_collector = collector  # type: ignore[attr-defined]
    collector.start()


def _phase(item: pytest.Item, phase: str):
    collector = _collector(item.config)
    token = _CONTEXT.set({"pytest_nodeid": item.nodeid, "pytest_phase": phase, "session_id": None})
    collector.set_context(item.nodeid, phase)
    try:
        yield
    finally:
        _CONTEXT.reset(token)


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_setup(item: pytest.Item):
    yield from _phase(item, "setup")


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_call(item: pytest.Item):
    yield from _phase(item, "call")


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_teardown(item: pytest.Item):
    yield from _phase(item, "teardown")


def pytest_warning_recorded(
    warning_message: Any,
    when: str,
    nodeid: str,
    location: tuple[str, int, str] | None,
) -> None:
    active = _ACTIVE
    if active is not None:
        active.warning_recorded(warning_message, when, nodeid, location)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    collector = _collector(session.config)
    # Keep the finalizer wrapper and live evidence stream active through
    # pytest's remaining unconfigure/teardown phase. No GC or dispose is
    # initiated here.
    collector.exitstatus = exitstatus


def pytest_unconfigure(config: pytest.Config) -> None:
    collector = getattr(config, "_sqlalchemy_finalizer_collector", None)
    if isinstance(collector, Collector):
        if not collector.persisted:
            collector.persist(collector.exitstatus)
        collector.stop()
