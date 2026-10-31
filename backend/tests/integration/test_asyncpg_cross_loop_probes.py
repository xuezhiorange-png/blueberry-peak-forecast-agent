"""Real PostgreSQL tests for synchronous probes and short-lived loop ownership."""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

import asyncpg
import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.core.config import get_settings
from backend.app.db import session as application_db
from backend.tests.db.profile import assert_safe_postgres_test_identity

pytestmark = [pytest.mark.integration, pytest.mark.postgres]


def record(event_name: str, **values: object) -> None:
    """Only lifecycle metadata, never SQL parameters, URLs or source rows."""
    destination = os.environ.get("TD03G_LIFECYCLE_TRACE")
    if destination:
        with Path(destination).open("a") as stream:
            stream.write(
                json.dumps({"event": event_name, "time_ns": time.monotonic_ns(), **values})
            )
            stream.write("\n")


ENTRIES = {
    "session_query": ("async_session_query", "queryable"),
    "bind": ("async_session_bind", "connected"),
    "session_connection": ("async_session_connection", "connected"),
    "bind_query": ("async_session_bind_query", "queryable"),
    "connection_query": ("async_session_connection_query", "queryable"),
    "run_sync_query": ("async_session_run_sync_query", "queryable"),
    "direct_engine": ("async_connection", "connected"),
}


@pytest.mark.parametrize("entry", ENTRIES)
def test_real_sync_probe_two_closed_loops_return_and_close_resources(monkeypatch, entry):
    assert os.environ.get("RUN_POSTGRES_INTEGRATION") == "1"
    assert_safe_postgres_test_identity()
    source = create_async_engine(
        get_settings().async_database_url, pool_pre_ping=True, hide_parameters=True
    )
    original_pool = source.pool
    maker = async_sessionmaker(source, expire_on_commit=False, info={"fixture": "SYNTHETIC"})
    configured = dict(maker.kw)
    drivers = []
    wrong_loop_requests = []
    disposals = []
    loop_exits = []
    private_pool_disposals = []

    @event.listens_for(source.sync_engine, "connect")
    def connect(dbapi, connection_record):
        driver = dbapi.driver_connection
        drivers.append(driver)
        record(
            "driver_connect",
            entry=entry,
            driver=id(driver),
            loop=id(driver._loop),
            pid=driver.get_server_pid(),
        )

    @event.listens_for(source.sync_engine, "checkout")
    def checkout(dbapi, connection_record, proxy):
        driver = dbapi.driver_connection
        record(
            "checkout",
            entry=entry,
            driver=id(driver),
            loop=id(asyncio.get_running_loop()),
            owner_loop=id(driver._loop),
        )

    @event.listens_for(source.sync_engine, "checkin")
    def checkin(dbapi, connection_record):
        record("checkin", entry=entry, driver=id(dbapi.driver_connection) if dbapi else None)

    @event.listens_for(source.sync_engine, "engine_disposed")
    def disposed(engine):
        disposals.append(engine)
        record(
            "dispose",
            entry=entry,
            source=engine is source.sync_engine,
            loop=id(asyncio.get_running_loop()),
        )

    @event.listens_for(source.sync_engine, "handle_error")
    def native_error(context):
        record(
            "native_error", entry=entry, exception_type=type(context.original_exception).__name__
        )

    original_cancel = asyncpg.Connection._cancel_current_command
    original_driver_close = asyncpg.Connection.close
    original_loop_close = asyncio.BaseEventLoop.close
    original_pool_dispose = type(original_pool).dispose

    def pool_dispose(pool, *args, **kwargs):
        result = original_pool_dispose(pool, *args, **kwargs)
        if pool is not original_pool:
            private_pool_disposals.append(pool)
            assert pool.checkedout() == 0
        record(
            "pool_dispose",
            entry=entry,
            source_pool=pool is original_pool,
            loop=id(asyncio.get_running_loop()),
            checkedout=pool.checkedout(),
        )
        return result

    async def driver_close(driver, *args, **kwargs):
        try:
            await original_driver_close(driver, *args, **kwargs)
        finally:
            if driver in drivers:
                record(
                    "driver_close",
                    entry=entry,
                    driver=id(driver),
                    loop=id(asyncio.get_running_loop()),
                    owner_loop=id(driver._loop),
                    closed=driver.is_closed(),
                )

    def loop_close(loop):
        owned = [driver for driver in drivers if driver._loop is loop]
        if owned:
            state = {
                "drivers_closed": [driver.is_closed() for driver in owned],
                "pending_tasks": sum(not task.done() for task in asyncio.all_tasks(loop)),
            }
            loop_exits.append(state)
            record(
                "before_loop_close",
                entry=entry,
                loop=id(loop),
                **state,
            )
        return original_loop_close(loop)

    def cancel(driver, waiter):
        current = asyncio.get_running_loop()
        if current is not driver._loop:
            wrong_loop_requests.append(driver)
        record(
            "native_cancel",
            entry=entry,
            loop=id(current),
            owner_loop=id(driver._loop),
            owner_closed=driver._loop.is_closed(),
        )
        return original_cancel(driver, waiter)

    monkeypatch.setattr(asyncpg.Connection, "_cancel_current_command", cancel)
    monkeypatch.setattr(asyncpg.Connection, "close", driver_close)
    monkeypatch.setattr(asyncio.BaseEventLoop, "close", loop_close)
    monkeypatch.setattr(type(original_pool), "dispose", pool_dispose)
    monkeypatch.setattr(application_db, "engine", source)
    monkeypatch.setattr(application_db, "AsyncSessionMaker", maker)
    suffix, successful = ENTRIES[entry]
    module = importlib.import_module(
        "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_" + suffix
    )
    call = next(
        value
        for name, value in vars(module).items()
        if name.startswith(("probe_accepted_", "obtain_accepted_")) and callable(value)
    )
    try:
        first = call()
        first_drivers = tuple(drivers)
        # Do not fail before the second call: exercise the real unsafe reuse,
        # including dialect pre-ping, rather than an artificial boundary throw.
        assert first_drivers and all(driver._loop.is_closed() for driver in first_drivers)
        second = call()
        record(
            "probe_results",
            entry=entry,
            first=getattr(first, successful),
            second=getattr(second, successful),
            drivers_closed=[driver.is_closed() for driver in drivers],
        )
        assert getattr(first, successful) is True
        assert getattr(second, successful) is True
        assert first.model_dump(mode="json") == second.model_dump(mode="json")
        assert first.source_002_row_level_read is False
        assert second.source_002_row_level_read is False
        assert not wrong_loop_requests
        assert all(driver.is_closed() for driver in drivers)
        assert len(drivers) == 2
        assert len(loop_exits) == 2
        assert all(all(state["drivers_closed"]) for state in loop_exits)
        assert all(state["pending_tasks"] == 0 for state in loop_exits)
        assert len(private_pool_disposals) == 2
        assert source.pool is original_pool
        assert maker.kw == configured
        assert all(engine is not source.sync_engine for engine in disposals)
    finally:
        # The test owns this source engine. Before the fix its earlier drivers
        # can no longer cleanly close on their already-closed loops; native
        # errors/warnings remain visible. The independent pytest process then
        # exits, and the task-owned PG server is checked for leftover backends.
        asyncio.run(source.dispose())
        record(
            "test_owner_exit",
            entry=entry,
            drivers_closed=[driver.is_closed() for driver in drivers],
        )


@dataclass
class PoolExit:
    drivers: list = field(default_factory=list)
    checkout: int = 0
    checkin: int = 0
    disposed: list = field(default_factory=list)
    pools: list = field(default_factory=list)


@asynccontextmanager
async def tracked_source(*, require_owned_closed=True):
    assert os.environ.get("RUN_POSTGRES_INTEGRATION") == "1"
    assert_safe_postgres_test_identity()
    source = create_async_engine(
        get_settings().async_database_url,
        hide_parameters=True,
        pool_pre_ping=True,
        execution_options={"isolation_level": "SERIALIZABLE"},
        connect_args={"server_settings": {"application_name": "SYNTHETIC_TD03G"}},
    )
    original_pool = source.pool
    state = PoolExit()

    @event.listens_for(source.sync_engine, "connect")
    def connect(dbapi, connection_record):
        driver = dbapi.driver_connection
        state.drivers.append(driver)
        state.pools.append(connection_record._ConnectionRecord__pool)
        record(
            "driver_connect", driver=id(driver), loop=id(driver._loop), pid=driver.get_server_pid()
        )

    @event.listens_for(source.sync_engine, "checkout")
    def checkout(dbapi, connection_record, proxy):
        driver = dbapi.driver_connection
        assert driver._loop is asyncio.get_running_loop()
        state.checkout += 1
        record("checkout", driver=id(driver), loop=id(driver._loop))

    @event.listens_for(source.sync_engine, "checkin")
    def checkin(dbapi, connection_record):
        state.checkin += 1
        record("checkin", driver=id(dbapi.driver_connection) if dbapi else None)

    @event.listens_for(source.sync_engine, "engine_disposed")
    def disposed(engine):
        state.disposed.append(engine)
        record("dispose", source=engine is source.sync_engine, loop=id(asyncio.get_running_loop()))

    try:
        yield source, state
        assert source.pool is original_pool
        assert not any(engine is source.sync_engine for engine in state.disposed)
        assert original_pool.checkedout() == 0
        assert state.checkout == state.checkin
        if require_owned_closed:
            assert all(driver.is_closed() for driver in state.drivers)
        record("verified_scope_exit", checkouts=state.checkout, checkins=state.checkin)
    finally:
        await source.dispose()
        assert all(driver.is_closed() for driver in state.drivers)


async def test_same_loop_factory_configuration_and_database_identity_are_retained():
    from backend.app.db.loop_resources import loop_owned_session

    seen = []

    class ConfiguredSession(AsyncSession):
        def __init__(self, **kwargs):
            seen.append(kwargs.copy())
            super().__init__(**kwargs)

    async with tracked_source() as (source, state):
        maker = async_sessionmaker(
            source,
            class_=ConfiguredSession,
            expire_on_commit=False,
            autoflush=False,
            info={"source": "SYNTHETIC"},
        )
        configured = maker.kw.copy()
        before = set(asyncio.all_tasks())
        async with loop_owned_session(maker) as session:
            local = session.bind
            assert local.engine is source
            assert local.sync_connection.engine is source.sync_engine
            assert type(state.pools[0]) is type(source.pool)
            assert state.pools[0] is not source.pool
            assert state.pools[0]._creator is source.pool._creator
            assert (
                local.sync_connection.get_execution_options()
                == source.sync_engine.get_execution_options()
            )
            assert session.info == {"source": "SYNTHETIC"}
            assert session.autoflush is False
            assert session.sync_session.expire_on_commit is False
            for _ in range(2):
                assert await session.scalar(text("SELECT 42")) == 42
            row = (
                await session.execute(
                    text(
                        "SELECT current_database(), current_user, "
                        "current_setting('application_name'), "
                        "current_setting('transaction_isolation')"
                    )
                )
            ).one()
            assert row == (
                get_settings().postgres_db,
                get_settings().postgres_user,
                "SYNTHETIC_TD03G",
                "serializable",
            )
        assert state.checkout == state.checkin == 1
        assert maker.kw == configured and maker.class_ is ConfiguredSession
        assert len(seen) == 1 and seen[0]["bind"] is source
        assert not {t for t in asyncio.all_tasks() - before if not t.done()}


@pytest.mark.parametrize("outcome", ["query_error", "rollback", "initialization"])
async def test_owned_scope_exception_rollback_and_initialization_cleanup(outcome):
    from backend.app.db.loop_resources import loop_owned_session

    async with tracked_source() as (source, state):
        before = set(asyncio.all_tasks())
        if outcome == "initialization":

            class FailedSession(AsyncSession):
                def __init__(self, **kwargs):
                    super().__init__(**kwargs)
                    raise RuntimeError("synthetic session initialization failure")

            maker = async_sessionmaker(source, class_=FailedSession)
            with pytest.raises(RuntimeError, match="synthetic session initialization"):
                async with loop_owned_session(maker):
                    pytest.fail("failed setup cannot yield")
            assert not state.drivers and not state.disposed
        else:
            maker = async_sessionmaker(source, expire_on_commit=False)
            if outcome == "query_error":
                with pytest.raises(DBAPIError):
                    async with loop_owned_session(maker) as session:
                        await session.execute(text("SELECT 1 / 0"))
            else:
                async with loop_owned_session(maker) as session:
                    assert await session.scalar(text("SELECT 1")) == 1
                    await session.rollback()
                    assert not session.in_transaction()
                    assert await session.scalar(text("SELECT 2")) == 2
            assert state.drivers and all(d.is_closed() for d in state.drivers)
        assert not {t for t in asyncio.all_tasks() - before if not t.done()}


async def test_cancelled_real_query_drains_cancellation_and_owned_drivers():
    from backend.app.db.loop_resources import loop_owned_connection, loop_owned_session

    async with tracked_source() as (source, state):
        maker = async_sessionmaker(source, expire_on_commit=False)
        began = asyncio.Future()
        before = set(asyncio.all_tasks())

        async def query():
            async with loop_owned_session(maker) as session:
                connection = await session.connection()
                raw = await connection.get_raw_connection()
                began.set_result(raw.driver_connection.get_server_pid())
                await session.execute(text("SELECT pg_sleep(30)"))

        task = asyncio.create_task(query())
        pid = await began
        async with loop_owned_connection(source) as observer:
            await observer.execution_options(isolation_level="AUTOCOMMIT")
            async with asyncio.timeout(5):
                while True:
                    wait_event = await observer.scalar(
                        text("SELECT wait_event FROM pg_stat_activity WHERE pid = :pid"),
                        {"pid": pid},
                    )
                    if wait_event == "PgSleep":
                        break
                    await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert task.cancelled()
        assert not {t for t in asyncio.all_tasks() - before if not t.done()}
        assert state.drivers and all(d.is_closed() for d in state.drivers)


async def test_borrowed_connection_keeps_its_identity_and_outer_transaction():
    from backend.app.db.loop_resources import loop_owned_session

    async with tracked_source(require_owned_closed=False) as (source, state):
        async with source.connect() as connection:
            outer = await connection.begin()
            maker = async_sessionmaker(connection, join_transaction_mode="create_savepoint")
            configured = maker.kw.copy()
            async with loop_owned_session(maker) as session:
                assert session.bind is connection
                assert await session.scalar(text("SELECT 1")) == 1
            assert not connection.closed and outer.is_active
            assert maker.kw == configured
            assert not state.disposed
            await outer.rollback()
        assert all(not d.is_closed() for d in state.drivers)
    assert state.drivers and all(d.is_closed() for d in state.drivers)


async def test_owned_scope_cleanup_errors_are_not_suppressed(monkeypatch):
    from backend.app.db.loop_resources import loop_owned_session

    async with tracked_source() as (source, state):
        pool_type = type(source.pool)
        original = pool_type.dispose

        def failing_cleanup(pool, *args, **kwargs):
            original(pool, *args, **kwargs)
            if pool is not source.pool:
                raise RuntimeError("synthetic cleanup failure after actual close")

        monkeypatch.setattr(pool_type, "dispose", failing_cleanup)
        with pytest.raises(RuntimeError, match="synthetic cleanup failure"):
            async with loop_owned_session(async_sessionmaker(source)) as session:
                assert await session.scalar(text("SELECT 1")) == 1
        assert state.drivers and all(d.is_closed() for d in state.drivers)


def test_sync_probe_does_not_dispose_or_rebind_a_warm_borrowed_engine(monkeypatch):
    assert os.environ.get("RUN_POSTGRES_INTEGRATION") == "1"
    assert_safe_postgres_test_identity()
    source = create_async_engine(
        get_settings().async_database_url, pool_pre_ping=True, hide_parameters=True
    )
    pool = source.pool
    maker = async_sessionmaker(source, expire_on_commit=False)
    configuration = maker.kw.copy()
    drivers = []

    @event.listens_for(source.sync_engine, "connect")
    def connect(dbapi, connection_record):
        drivers.append(dbapi.driver_connection)

    async def read():
        async with source.connect() as connection:
            assert await connection.scalar(text("SELECT 7")) == 7

    module = importlib.import_module(
        "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_async_session_query"
    )
    probe = module.probe_accepted_s2_train_val_already_obtained_live_async_session_queryability
    monkeypatch.setattr(application_db, "AsyncSessionMaker", maker)
    with asyncio.Runner() as owner:
        try:
            owner.run(read())
            borrowed_driver = drivers[0]
            for _ in range(3):
                result = probe()
                assert result.queryable is True
                assert result.source_002_row_level_read is False
                assert not borrowed_driver.is_closed()
                assert source.pool is pool and maker.kw == configuration
                assert all(driver.is_closed() for driver in drivers[1:])
            owner.run(read())
            assert pool.checkedin() == 1 and pool.checkedout() == 0
        finally:
            owner.run(source.dispose())
        assert all(driver.is_closed() for driver in drivers)


def test_foreign_borrowed_connection_is_rejected_without_touching_its_transaction():
    from backend.app.db.loop_resources import loop_owned_session

    assert os.environ.get("RUN_POSTGRES_INTEGRATION") == "1"
    assert_safe_postgres_test_identity()
    source = create_async_engine(get_settings().async_database_url, hide_parameters=True)

    async def connect():
        connection = await source.connect()
        transaction = await connection.begin()
        return connection, transaction

    async def read(maker):
        async with loop_owned_session(maker) as session:
            await session.scalar(text("SELECT 1"))

    with asyncio.Runner() as owner:
        connection, transaction = owner.run(connect())
        try:
            maker = async_sessionmaker(connection, join_transaction_mode="create_savepoint")
            with pytest.raises(RuntimeError, match="different loop"):
                asyncio.run(read(maker))
            assert not connection.closed and transaction.is_active
            assert maker.kw["bind"] is connection
        finally:
            owner.run(transaction.rollback())
            owner.run(connection.close())
            owner.run(source.dispose())


async def test_native_connection_initialization_error_closes_driver():
    from backend.app.db.loop_resources import LoopResourceUnavailable, loop_owned_session

    async with tracked_source() as (source, state):

        @event.listens_for(source.sync_engine, "engine_connect")
        def fail_initialization(connection):
            connection.exec_driver_sql("SELECT 1 / 0")

        with pytest.raises(LoopResourceUnavailable) as failure:
            async with loop_owned_session(async_sessionmaker(source)) as session:
                await session.scalar(text("SELECT 1"))
        assert isinstance(failure.value.__cause__, DBAPIError)
        assert state.drivers and all(driver.is_closed() for driver in state.drivers)


async def test_multiple_binds_do_not_create_an_unproven_replacement_source():
    from backend.app.db.loop_resources import loop_owned_session

    async with tracked_source() as (source, state):
        maker = async_sessionmaker(source, binds={AsyncSession: source})
        with pytest.raises(RuntimeError, match="Multiple configured binds"):
            loop_owned_session(maker)
        assert not state.drivers and not state.disposed


@pytest.mark.parametrize("phase", ["session_close", "pool_dispose"])
async def test_cancellation_during_cleanup_waits_for_one_real_close(monkeypatch, phase):
    from backend.app.db.loop_resources import loop_owned_session

    async with tracked_source() as (source, state):
        started = asyncio.Event()
        release = asyncio.Event()
        close_calls = []
        before = set(asyncio.all_tasks())

        class PausedSession(AsyncSession):
            async def close(self):
                close_calls.append("session_close")
                if phase == "session_close":
                    started.set()
                    await release.wait()
                await super().close()

        original = asyncpg.Connection.close

        async def paused_driver_close(driver, *args, **kwargs):
            if phase == "pool_dispose" and driver in state.drivers:
                close_calls.append("driver_close")
                started.set()
                await release.wait()
            await original(driver, *args, **kwargs)

        monkeypatch.setattr(asyncpg.Connection, "close", paused_driver_close)
        maker = async_sessionmaker(source, class_=PausedSession)

        async def run():
            async with loop_owned_session(maker) as session:
                assert await session.scalar(text("SELECT 1")) == 1

        task = asyncio.create_task(run())
        async with asyncio.timeout(5):
            await started.wait()
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert task.cancelled()
        assert close_calls.count("session_close") == 1
        if phase == "pool_dispose":
            assert close_calls.count("driver_close") == 1
        assert not {t for t in asyncio.all_tasks() - before if not t.done()}
        assert state.drivers and all(d.is_closed() for d in state.drivers)


def test_session_only_probe_remains_lazy_and_is_not_source_read_authority(monkeypatch):
    assert os.environ.get("RUN_POSTGRES_INTEGRATION") == "1"
    assert_safe_postgres_test_identity()
    source = create_async_engine(get_settings().async_database_url, hide_parameters=True)
    connects = []

    @event.listens_for(source.sync_engine, "connect")
    def connect(dbapi, connection_record):
        connects.append(dbapi)

    maker = async_sessionmaker(source)
    monkeypatch.setattr(application_db, "AsyncSessionMaker", maker)
    module = importlib.import_module(
        "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_async_session"
    )
    probe = next(
        v for k, v in vars(module).items() if k.startswith("obtain_accepted_") and callable(v)
    )
    try:
        for _ in range(2):
            result = probe()
            assert result.obtained is True
            assert result.source_002_row_level_read is False
        assert not connects
    finally:
        asyncio.run(source.dispose())


@pytest.mark.parametrize(
    ("entry", "failure"),
    [
        (entry, failure)
        for entry in ENTRIES
        for failure in ("connection_setup", "session_constructor", "session_enter")
        if entry != "direct_engine" or failure == "connection_setup"
    ],
)
def test_existing_failure_reasons_and_source_gates_are_preserved(monkeypatch, entry, failure):
    import sys
    import types

    from backend.tests.historical_source import historical_bytes
    from backend.tests.td03g_historical_source import BASE

    assert os.environ.get("RUN_POSTGRES_INTEGRATION") == "1"
    assert_safe_postgres_test_identity()
    suffix, successful = ENTRIES[entry]
    path = (
        "backend/app/s3_daily_rowset/"
        "accepted_s2_train_val_source_002_row_level_read_live_" + suffix + ".py"
    )
    name = "backend.tests.td03g_original_" + suffix
    historical = types.ModuleType(name)
    historical.__file__ = BASE + ":" + path
    monkeypatch.setitem(sys.modules, name, historical)
    exec(compile(historical_bytes(path, BASE), historical.__file__, "exec"), historical.__dict__)
    current = importlib.import_module(path.removesuffix(".py").replace("/", "."))

    class FailedConstructor(AsyncSession):
        def __init__(self, **kwargs):
            raise RuntimeError("synthetic constructor failure")

    class FailedEnter(AsyncSession):
        async def __aenter__(self):
            raise RuntimeError("synthetic enter failure")

    values = []
    for module in (historical, current):
        # Reject an invalid server setting on the same guarded synthetic DB;
        # never try a guessed URL, alternate server or business database.
        arguments = (
            {"server_settings": {"td03g_unknown_setting": "reject"}}
            if failure == "connection_setup"
            else {}
        )
        source = create_async_engine(
            get_settings().async_database_url, hide_parameters=True, connect_args=arguments
        )
        session_type = {
            "connection_setup": AsyncSession,
            "session_constructor": FailedConstructor,
            "session_enter": FailedEnter,
        }[failure]
        maker = async_sessionmaker(source, class_=session_type)
        monkeypatch.setattr(application_db, "engine", source)
        monkeypatch.setattr(application_db, "AsyncSessionMaker", maker)
        call = next(
            value
            for key, value in vars(module).items()
            if key.startswith(("probe_accepted_", "obtain_accepted_")) and callable(value)
        )
        try:
            value = call()
            values.append(value.model_dump(mode="json"))
            assert value.source_002_row_level_read is False
            assert value.official_hashes_attested_from_a_live_read is False
            # Direct-engine probes intentionally do not instantiate a Session.
            if entry != "direct_engine" or failure == "connection_setup":
                assert getattr(value, successful) is False
        finally:
            # Only setup/Session failures run against old code here; successful
            # real wire reuse is exercised separately by the RED/GREEN test.
            asyncio.run(source.dispose())
    assert values[0] == values[1]
