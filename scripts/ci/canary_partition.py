"""Duration-balanced whole-file pytest partitioning, with per-node execution proof.

Inactive unless --canary-slot is explicitly supplied. No marker changes, test
assertion changes, retries or skipped tests are introduced by this plugin.
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import json
import os
import platform
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pytest

from scripts.ci.canary_plan import SLOTS, TIMINGS, canonical, digest, partition, source_snapshot


def identity() -> dict[str, Any]:
    ci = os.environ.get("GITHUB_ACTIONS") == "true"
    db: dict[str, Any] = {"name": None, "server_version": None}
    if ci:
        from backend.tests.db.profile import assert_safe_postgres_test_identity

        assert_safe_postgres_test_identity(env=None)

        async def check() -> None:
            asyncpg = importlib.import_module("asyncpg")

            conn = await asyncpg.connect(
                host=os.environ["POSTGRES_HOST"],
                port=int(os.environ["POSTGRES_PORT"]),
                user=os.environ["POSTGRES_USER"],
                password=os.environ["POSTGRES_PASSWORD"],
                database=os.environ["POSTGRES_DB"],
            )
            try:
                db["name"] = await conn.fetchval("SELECT current_database()")
                db["server_version"] = int(await conn.fetchval("SHOW server_version_num"))
            finally:
                await conn.close()

        asyncio.run(check())
    deps = sorted(
        (d.metadata["Name"].lower(), d.version) for d in importlib.metadata.distributions()
    )
    return {
        "ci": ci,
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "source_head": os.environ.get("CANARY_SOURCE_HEAD"),
        "event": os.environ.get("GITHUB_EVENT_NAME"),
        **source_snapshot(),
        "python": platform.python_version(),
        "platform": sys.platform,
        "machine": platform.machine(),
        "dependencies_sha256": digest(deps),
        "database": db,
    }


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("full-canary")
    group.addoption("--canary-slot", choices=[*SLOTS, "serial"])
    group.addoption("--canary-proof", type=Path)


def pytest_configure(config: pytest.Config) -> None:
    slot = config.getoption("--canary-slot")
    if slot is not None:
        if config.getoption("--canary-proof") is None:
            raise pytest.UsageError("CANARY_PROOF_PATH_REQUIRED")
        config.pluginmanager.register(Recorder(config, slot), "canary-execution-recorder")


class Recorder:
    def __init__(self, config: pytest.Config, slot: str) -> None:
        self.config, self.slot = config, slot
        self.started = time.monotonic()
        self.catalog: list[str] = []
        self.selected: list[str] = []
        self.phases: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.collection_problems: list[dict[str, str]] = []
        self.plan: dict[str, Any] = {}
        self.environment: dict[str, Any] = {}

    def pytest_sessionstart(self) -> None:
        self.environment = identity()

    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def pytest_collection_modifyitems(self, items: list[pytest.Item]) -> Any:
        original = [item.nodeid for item in items]
        yield
        current = [item.nodeid for item in items]
        if Counter(original) != Counter(current):
            raise pytest.UsageError("FULL_CANARY_COLLECTION_WAS_FILTERED")
        # Keep pytest's normal fixture-based ordering; only filtering is forbidden.
        self.catalog = sorted(current)
        self.plan = partition(current, json.loads(TIMINGS.read_bytes()))
        keep: list[pytest.Item] = []
        discard: list[pytest.Item] = []
        for item in items:
            owner = self.plan["owners"][item.nodeid.split("::", 1)[0]]
            (keep if self.slot == "serial" or owner == self.slot else discard).append(item)
        if not keep:
            raise pytest.UsageError("EMPTY_CANARY_SHARD")
        items[:] = keep
        self.selected = [i.nodeid for i in keep]
        self.config.hook.pytest_deselected(items=discard)

    def pytest_collectreport(self, report: pytest.CollectReport) -> None:
        if report.outcome != "passed":
            self.collection_problems.append({"nodeid": report.nodeid, "outcome": report.outcome})

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        reason = ""
        if report.skipped:
            raw = report.longrepr
            reason = str(raw[2] if isinstance(raw, tuple) else raw)
            if reason.startswith("Skipped: "):
                reason = reason[len("Skipped: ") :]
        self.phases[report.nodeid].append(
            {
                "when": report.when,
                "outcome": report.outcome,
                "wasxfail": bool(getattr(report, "wasxfail", False)),
                "reason": reason,
            }
        )

    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int) -> None:
        body = {
            "version": 1,
            "slot": self.slot,
            "identity": self.environment,
            "catalog": self.catalog,
            "catalog_sha256": digest(self.catalog),
            "selected": self.selected,
            "plan": self.plan,
            "phases": dict(self.phases),
            "collection_problems": self.collection_problems,
            "exitstatus": int(exitstatus),
            "duration_seconds": time.monotonic() - self.started,
            "counts": dict(Counter(r["outcome"] for rr in self.phases.values() for r in rr)),
        }
        # The proof is mandatory output, never an excuse to replace pytest's exit status.
        path: Path = self.config.getoption("--canary-proof")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical(body) + b"\n")
