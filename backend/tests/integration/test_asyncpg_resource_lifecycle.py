"""Real-driver ownership regressions; only the isolated synthetic PG profile."""

from __future__ import annotations

import asyncio
import inspect
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.core.config import get_settings
from backend.app.models.analytics import AnalyticsBuildRun
from backend.app.models.maturity import MaturityDailyPredictionModel
from backend.tests.db.profile import assert_safe_postgres_test_identity
from backend.tests.integration import test_rolling_backtest_orchestration as orchestration_fixture

pytestmark = [pytest.mark.integration, pytest.mark.postgres]


@dataclass
class ResourceExit:
    events: list[str] = field(default_factory=list)
    drivers: list = field(default_factory=list)
    sessions: list[AsyncSession] = field(default_factory=list)
    checkout: int = 0
    checkin: int = 0
    owner_loop: asyncio.AbstractEventLoop | None = None
    disposed: bool = False


@asynccontextmanager
async def owned_engine(probe: ResourceExit, *, fail_initialization: bool = False):
    import os

    assert os.environ.get("RUN_POSTGRES_INTEGRATION") == "1", "isolated PostgreSQL required"
    assert_safe_postgres_test_identity()
    probe.owner_loop = asyncio.get_running_loop()
    engine = create_async_engine(get_settings().async_database_url, hide_parameters=True)

    @event.listens_for(engine.sync_engine, "connect")
    def connect(dbapi, record):
        probe.drivers.append(dbapi.driver_connection)
        probe.events.append("driver_connected")

    @event.listens_for(engine.sync_engine, "checkout")
    def checkout(dbapi, record, proxy):
        probe.checkout += 1

    @event.listens_for(engine.sync_engine, "checkin")
    def checkin(dbapi, record):
        probe.checkin += 1

    @event.listens_for(engine.sync_engine, "rollback")
    def rollback(connection):
        probe.events.append("rollback")

    try:
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT 1")) == 1
        if fail_initialization:
            raise RuntimeError("synthetic initialization failure")
        yield engine
    finally:
        # Retaining the probe's sessions makes the pre-fix checkout failure
        # deterministic, instead of letting GC decide when a leak is noticed.
        # Assertions in the caller run BEFORE this safety cleanup.
        for session in probe.sessions:
            await session.close()
        assert asyncio.get_running_loop() is probe.owner_loop
        probe.events.append("dispose_start")
        await engine.dispose()
        probe.events.append("dispose_end")
        probe.disposed = True
        assert all(driver.is_closed() for driver in probe.drivers)


@pytest.mark.parametrize("outcome", ["normal", "exception", "cancel", "initialization"])
async def test_orchestration_fixture_returns_its_connections(monkeypatch, outcome):
    probe = ResourceExit()
    async with owned_engine(probe) as engine:
        original_pool = engine.pool

        class ObservedSession(AsyncSession):
            async def get(self, entity, ident, **kwargs):
                value = await super().get(entity, ident, **kwargs)
                if (
                    entity is MaturityDailyPredictionModel
                    and self.info.get("fixture_owner") == "_build_real_orchestration_command"
                ):
                    probe.events.append("daily_lookup")
                    if outcome == "exception":
                        raise RuntimeError("synthetic daily lookup failure")
                    if outcome == "cancel":
                        asyncio.current_task().cancel()
                        await asyncio.sleep(0)
                if (
                    entity is AnalyticsBuildRun
                    and outcome == "initialization"
                    and self.info.get("fixture_owner") == "_build_real_orchestration_command"
                ):
                    raise RuntimeError("synthetic seed initialization failure")
                return value

        maker = async_sessionmaker(engine, class_=ObservedSession, expire_on_commit=False)

        def factory():
            session = maker()
            session.info["fixture_owner"] = inspect.currentframe().f_back.f_code.co_name
            probe.sessions.append(session)
            return session

        monkeypatch.setattr(orchestration_fixture, "AsyncSessionMaker", factory)
        tasks_before = set(asyncio.all_tasks())
        task = asyncio.create_task(
            orchestration_fixture._build_real_orchestration_command(
                forecast_cutoff_at=datetime(2099, 3, 15, 4, tzinfo=UTC)
            )
        )
        if outcome == "normal":
            result = await task
            assert result.config.nodes
        elif outcome == "cancel":
            with pytest.raises(asyncio.CancelledError):
                await task
            assert task.cancelled()
        else:
            with pytest.raises(RuntimeError, match="synthetic"):
                await task
        # This fails on the old fixture, both after successful construction
        # and after the daily lookup raises or is cancelled.
        assert not any(session.in_transaction() for session in probe.sessions)
        assert engine.pool.checkedout() == 0
        assert probe.checkout == probe.checkin
        assert engine.pool is original_pool  # A borrower must not dispose it.
        assert "rollback" in probe.events
        assert not {t for t in asyncio.all_tasks() - tasks_before if not t.done()}
    assert probe.disposed
    assert probe.events[-2:] == ["dispose_start", "dispose_end"]


async def test_owned_engine_initialization_failure_disposes_real_driver():
    probe = ResourceExit()
    with pytest.raises(RuntimeError, match="synthetic initialization failure"):
        async with owned_engine(probe, fail_initialization=True):
            pytest.fail("failed initialization must not yield an engine")
    assert probe.disposed
    assert probe.drivers and all(driver.is_closed() for driver in probe.drivers)
    assert probe.checkout == probe.checkin


async def test_session_does_not_close_callers_connection_or_transaction():
    probe = ResourceExit()
    async with owned_engine(probe) as engine:
        original_pool = engine.pool
        async with engine.connect() as connection:
            outer = await connection.begin()
            maker = async_sessionmaker(bind=connection, join_transaction_mode="create_savepoint")
            async with maker() as session:
                assert await session.scalar(text("SELECT 1")) == 1
            assert not connection.closed
            assert outer.is_active
            assert engine.pool is original_pool
            assert await connection.scalar(text("SELECT 1")) == 1
            await outer.rollback()
        assert engine.pool.checkedout() == 0
    assert probe.disposed


async def test_real_query_cancellation_drains_driver_tasks():
    probe = ResourceExit()
    async with owned_engine(probe) as engine:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            connection = await session.connection()
            raw = await connection.get_raw_connection()
            driver = raw.driver_connection
            backend_pid = driver.get_server_pid()
            pending_before = set(asyncio.all_tasks())
            query = asyncio.create_task(session.execute(text("SELECT pg_sleep(30)")))
            # Synchronize with the real server, not a speculative sleep. Only
            # PID/state/wait-event are read; no SQL text or parameters are logged.
            async with engine.connect() as observer:
                await observer.execution_options(isolation_level="AUTOCOMMIT")
                async with asyncio.timeout(5):
                    while True:
                        waiting = await observer.scalar(
                            text("SELECT wait_event FROM pg_stat_activity WHERE pid = :pid"),
                            {"pid": backend_pid},
                        )
                        if waiting == "PgSleep":
                            break
                        await asyncio.sleep(0.01)
            query.cancel()
            with pytest.raises(asyncio.CancelledError):
                await query
            await session.rollback()
            assert not session.in_transaction()
            assert not {task for task in asyncio.all_tasks() - pending_before if not task.done()}
        assert engine.pool.checkedout() == 0
        assert probe.checkout == probe.checkin
    assert probe.disposed


def test_controlled_default_probe_cross_loop_diagnostic(monkeypatch):
    """CONTROLLED_TOPOLOGY_DIAGNOSTIC with a real, warmed PostgreSQL pool.

    Stop at the unsafe I/O boundary; do not corrupt a driver to manufacture a
    warning. Unmodified real-driver failure/cancellation evidence is retained
    separately in the pre-fix suite trace. This diagnostic is not a fix.
    """
    import os

    from backend.app.db import session as application_db
    from backend.app.s3_daily_rowset import (
        accepted_s2_train_val_source_002_row_level_read_live_async_session_query as query,
    )

    assert os.environ.get("RUN_POSTGRES_INTEGRATION") == "1"
    assert_safe_postgres_test_identity()
    drivers = []
    attempts = []
    engine = create_async_engine(get_settings().async_database_url, hide_parameters=True)

    @event.listens_for(engine.sync_engine, "connect")
    def connect(dbapi, record):
        drivers.append(dbapi.driver_connection)

    class GuardedSession(AsyncSession):
        async def scalar(self, *args, **kwargs):
            attempts.append((asyncio.get_running_loop(), drivers[0]._loop, self.bind))
            raise RuntimeError("CONTROLLED_CROSS_LOOP_ATTEMPT_STOPPED_BEFORE_WIRE_IO")

    maker = async_sessionmaker(engine, class_=GuardedSession, expire_on_commit=False)
    monkeypatch.setattr(application_db, "AsyncSessionMaker", maker)

    async def warm():
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT 1")) == 1

    with asyncio.Runner() as owner:
        try:
            owner.run(warm())
            assert drivers and drivers[0]._loop is owner.get_loop()
            result = (
                query.probe_accepted_s2_train_val_already_obtained_live_async_session_queryability()
            )
            assert result.queryable is False
            assert result.source_002_row_level_read is False
            assert result.official_hashes_attested_from_a_live_read is False
            assert attempts and all(caller is not driver for caller, driver, _ in attempts)
            assert all(bind is engine for _, _, bind in attempts)
        finally:
            owner.run(engine.dispose())
        assert all(driver.is_closed() for driver in drivers)
