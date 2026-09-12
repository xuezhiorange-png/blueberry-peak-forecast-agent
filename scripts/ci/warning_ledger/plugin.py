"""Capture one JSON record for every pytest warning hook event.

This module is loaded only by the dedicated warning-ledger CI job.  It does
not alter warning filters, warning categories, test selection, or pytest
configuration.  Each process writes to its own file so parallel workers can
never interleave JSON objects in one stream.
"""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_HANDLE: Any = None
_LOCK = threading.Lock()
_SEQUENCE = 0
_FLUSH_INTERVAL = 1000


def _safe_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return token or "unknown"


def _ledger_dir() -> Path:
    path = Path(os.environ.get("WARNING_LEDGER_DIR", "reports/warning-ledger"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _worker_id(config: Any) -> str:
    worker_input = getattr(config, "workerinput", None)
    if isinstance(worker_input, dict):
        value = worker_input.get("workerid")
        if value:
            return _safe_token(str(value))
    return _safe_token(os.environ.get("PYTEST_XDIST_WORKER", "master"))


def pytest_configure(config: Any) -> None:
    """Open a process-local raw event stream before tests begin."""
    global _HANDLE
    worker = _worker_id(config)
    filename = f"warning-events.raw.{worker}.{os.getpid()}.jsonl"
    _HANDLE = (_ledger_dir() / filename).open("w", encoding="utf-8")


def pytest_unconfigure(config: Any) -> None:
    """Flush the process-local stream after pytest has finished."""
    del config
    global _HANDLE
    with _LOCK:
        if _HANDLE is not None:
            _HANDLE.flush()
            _HANDLE.close()
            _HANDLE = None


def pytest_warning_recorded(
    warning_message: Any,
    when: str,
    nodeid: str,
    location: tuple[str, int, str] | None,
) -> None:
    """Persist exactly one raw JSON record for one pytest hook event."""
    global _SEQUENCE
    if _HANDLE is None:
        return

    message = getattr(warning_message, "message", warning_message)
    category = getattr(warning_message, "category", type(message))
    filename = str(getattr(warning_message, "filename", ""))
    line_number = getattr(warning_message, "lineno", 0)
    try:
        line_number = int(line_number)
    except (TypeError, ValueError):
        line_number = 0

    location_filename = filename
    location_line = line_number
    location_function = ""
    if location:
        location_filename = str(location[0])
        try:
            location_line = int(location[1])
        except (TypeError, ValueError):
            location_line = line_number
        location_function = str(location[2])

    worker = _safe_token(os.environ.get("PYTEST_XDIST_WORKER", "master"))
    record = {
        "sequence": 0,
        "process_id": os.getpid(),
        "worker_id": worker,
        "warning_category": getattr(category, "__name__", str(category)),
        "raw_message": str(message),
        "source_filename": filename,
        "source_line": line_number,
        "nodeid": nodeid,
        "phase": when,
        "location": {
            "filename": location_filename,
            "line": location_line,
            "function": location_function,
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }
    with _LOCK:
        _SEQUENCE += 1
        record["sequence"] = _SEQUENCE
        _HANDLE.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        if _SEQUENCE % _FLUSH_INTERVAL == 0:
            _HANDLE.flush()
