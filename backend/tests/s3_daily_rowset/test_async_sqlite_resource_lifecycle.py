"""Owned synthetic SQLite resources must close before their query loop closes."""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from backend.tests.s3_daily_rowset.owned_sqlite_session import owned_sqlite_session_maker

pytestmark = [pytest.mark.unit, pytest.mark.contract]

_PREFIX = "backend.tests.s3_daily_rowset.test_accepted_s2_train_val_source_002_row_level_read_"
_CASES = (
    ("live_async_session_run_sync_query", "queryable"),
    ("live_async_session_query", "queryable"),
    ("live_async_session_connection_query", "queryable"),
    ("live_async_session_bind_query", "queryable"),
    ("live_async_session_connection", "connected"),
    ("live_async_session_bind", "connected"),
    ("live_async_obtain", "obtained"),
    ("live_async_session_connection_obtain", "obtained"),
    ("live_async_session_bind_obtain", "obtained"),
)


class _Resources:
    def __init__(self) -> None:
        self.engines: list[AsyncEngine] = []
        self.drivers: list[Any] = []
        self.events: list[tuple[str, int, asyncio.AbstractEventLoop]] = []

    def record(self, kind: str, engine: AsyncEngine) -> None:
        loop = asyncio.get_running_loop()
        assert not loop.is_closed()
        self.events.append((kind, id(engine), loop))

    def assert_released(self) -> None:
        assert self.engines, "synthetic test did not create its expected engine"
        assert self.drivers, "synthetic test did not exercise a real aiosqlite connection"
        for driver in self.drivers:
            # Wait for this exact owned thread's exit, not GC or a retry of the test.
            driver._thread.join(timeout=1)
            assert not driver._thread.is_alive(), "aiosqlite worker outlived the query loop"
            assert driver._connection is None, "SQLite connection was not explicitly closed"
        for engine in self.engines:
            events = [(kind, loop) for kind, ident, loop in self.events if ident == id(engine)]
            connects = [loop for kind, loop in events if kind == "CONNECT"]
            disposed = [loop for kind, loop in events if kind == "DISPOSE_END"]
            assert connects and disposed, "test-owned engine was never disposed"
            assert set(connects) == set(disposed), "engine crossed query/dispose event loops"
            assert all(loop.is_closed() for loop in connects), "test loop has not exited"
            kinds = [kind for kind, _ in events]
            assert kinds.count("CHECKOUT") == kinds.count("CHECKIN")
            assert max(i for i, kind in enumerate(kinds) if kind == "SESSION_CLOSE_END") < (
                kinds.index("DISPOSE_BEGIN")
            )
            assert kinds.index("CLOSE") < kinds.index("DISPOSE_END")


@pytest.fixture
def resources(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Resources]:
    observed = _Resources()
    original_init = AsyncEngine.__init__
    original_close = AsyncSession.close
    original_dispose = AsyncEngine.dispose

    def engine_init(self: AsyncEngine, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        if self.url.drivername != "sqlite+aiosqlite":
            return
        observed.engines.append(self)

        @event.listens_for(self.sync_engine, "connect")
        def connected(dbapi: Any, record: Any) -> None:
            observed.drivers.append(dbapi.driver_connection)
            observed.record("CONNECT", self)

        for name in ("checkout", "checkin", "close"):

            def received(*args: Any, _kind: str = name.upper()) -> None:
                observed.record(_kind, self)

            event.listen(self.sync_engine, name, received)

    async def session_close(self: AsyncSession) -> None:
        engine = self.bind
        if engine in observed.engines:
            observed.record("SESSION_CLOSE_BEGIN", engine)
        await original_close(self)
        if engine in observed.engines:
            observed.record("SESSION_CLOSE_END", engine)

    async def engine_dispose(self: AsyncEngine, *args: Any, **kwargs: Any) -> None:
        tracked = self in observed.engines
        if tracked:
            observed.record("DISPOSE_BEGIN", self)
        await original_dispose(self, *args, **kwargs)
        if tracked:
            observed.record("DISPOSE_END", self)

    monkeypatch.setattr(AsyncEngine, "__init__", engine_init)
    monkeypatch.setattr(AsyncSession, "close", session_close)
    monkeypatch.setattr(AsyncEngine, "dispose", engine_dispose)
    try:
        yield observed
    finally:
        # A deliberately red regression on the old helper must not leak its workers.
        # This rescue is after the assertions; it cannot make a failed test pass.
        if any(driver._thread.is_alive() for driver in observed.drivers):

            async def rescue_failed_test() -> None:
                for engine in observed.engines:
                    await engine.dispose()

            asyncio.run(rescue_failed_test())
        for driver in observed.drivers:
            driver._thread.join(timeout=1)
            assert not driver._thread.is_alive(), "failed-test cleanup stranded an owned worker"


@pytest.mark.parametrize(("suffix", "outcome"), _CASES)
def test_existing_synthetic_probe_releases_its_sqlite_resources(
    suffix: str, outcome: str, resources: _Resources
) -> None:
    module = importlib.import_module(_PREFIX + suffix)
    test = getattr(module, f"test_synthetic_sqlite_aiosqlite_{outcome}_is_not_official_{suffix}")
    test()  # Includes the original business and not-SOURCE_002 assertions unchanged.
    resources.assert_released()


class _SyntheticFailure(Exception):
    pass


def test_owned_session_closes_on_body_failure(resources: _Resources) -> None:
    async def run() -> None:
        async with owned_sqlite_session_maker()() as session:
            assert await session.scalar(select(1)) == 1
            raise _SyntheticFailure("synthetic body failure")

    with pytest.raises(_SyntheticFailure, match="synthetic body failure"):
        asyncio.run(run())
    resources.assert_released()


def test_owned_session_closes_on_task_cancellation(resources: _Resources) -> None:
    async def run() -> None:
        async with owned_sqlite_session_maker()() as session:
            assert await session.scalar(select(1)) == 1
            task = asyncio.current_task()
            assert task is not None
            task.cancel()
            await asyncio.sleep(0)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(run())
    resources.assert_released()


def test_owned_session_closes_on_failed_setup(resources: _Resources) -> None:
    async def prepare(engine: AsyncEngine) -> None:
        async with engine.connect() as connection:
            assert await connection.scalar(select(1)) == 1
        raise _SyntheticFailure("synthetic setup failure")

    async def run() -> None:
        async with owned_sqlite_session_maker(prepare)():
            pytest.fail("failed setup must not enter the test body")

    with pytest.raises(_SyntheticFailure, match="synthetic setup failure"):
        asyncio.run(run())
    resources.assert_released()


def test_query_failure_keeps_fail_closed_and_closes_resources(
    resources: _Resources, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def prepare(engine: AsyncEngine) -> None:
        async with engine.connect() as connection:
            assert await connection.scalar(select(1)) == 1

    s3 = importlib.import_module(_PREFIX + "live_async_session_run_sync_query")
    monkeypatch.setattr(
        "backend.app.db.session.AsyncSessionMaker", owned_sqlite_session_maker(prepare)
    )
    monkeypatch.setattr(
        AsyncSession, "run_sync", AsyncMock(side_effect=RuntimeError("synthetic query failure"))
    )
    probe = s3.probe_accepted_s2_train_val_already_obtained_live_async_session_run_sync_queryability
    envelope = probe()
    assert envelope.queryable is False
    assert envelope.reason_code == (
        s3.LiveAsyncSessionRunSyncQueryReasonCode.FAIL_CLOSED_ASYNC_SESSION_NOT_SYNCHRONOUSLY_QUERYABLE_VIA_RUN_SYNC
    )
    s3._assert_not_source_002(envelope)
    resources.assert_released()


def test_reusing_maker_on_separate_loops_never_reuses_an_engine(resources: _Resources) -> None:
    maker = owned_sqlite_session_maker()

    async def run() -> None:
        async with maker() as session:
            assert await session.scalar(select(1)) == 1

    asyncio.run(run())
    asyncio.run(run())
    assert len(resources.engines) == len(resources.drivers) == 2
    assert resources.engines[0] is not resources.engines[1]
    assert resources.drivers[0]._thread is not resources.drivers[1]._thread
    resources.assert_released()


def test_fixture_cannot_take_ownership_of_an_external_bind(resources: _Resources) -> None:
    with pytest.raises(ValueError, match="external bind is forbidden"):
        owned_sqlite_session_maker()(bind=object())
    assert not resources.engines and not resources.drivers
