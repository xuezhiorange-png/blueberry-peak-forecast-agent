"""Explicit saved runs are separate from stateless product forecasts."""

import hashlib
import json
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from backend.app.area_yield import run_application
from backend.app.area_yield.data import digest
from backend.app.area_yield.product import AreaDrivenForecastRequest
from backend.app.area_yield.product_authority import forecast_area_product
from backend.app.area_yield.run_application import execute_area_forecast_run
from backend.app.area_yield.run_persistence import (
    AreaForecastPersistenceConflictError,
    AreaForecastPersistenceIntegrityError,
    AreaForecastRunRepository,
    AreaForecastWriteFailure,
)
from backend.app.models.area_forecast import AreaForecastDailyRow, AreaForecastRun
from backend.tests.area_yield.test_product_p1 import bundle, request


def bounded(**changes):
    return AreaDrivenForecastRequest.model_validate(
        {
            **request().model_dump(mode="json"),
            "season_start": "2026-10-15",
            "season_end": "2027-05-09",
            **changes,
        }
    )


@pytest.fixture
def authority(tmp_path, monkeypatch):
    path = tmp_path / "authority.json"
    raw = json.dumps(bundle()).encode()
    path.write_bytes(raw)
    monkeypatch.setenv("AREA_YIELD_AUTHORITY_PATH", str(path))
    monkeypatch.setenv("AREA_YIELD_AUTHORITY_SHA256", hashlib.sha256(raw).hexdigest())


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://", connect_args={"autocommit": False})
    async with engine.begin() as conn:
        await conn.run_sync(AreaForecastRun.__table__.create)
        await conn.run_sync(AreaForecastDailyRow.__table__.create)
    async with AsyncSession(engine, expire_on_commit=False) as s:
        yield s
    await engine.dispose()


async def test_roundtrip_idempotency(session, authority):
    first = await execute_area_forecast_run(session, bounded())
    again = await execute_area_forecast_run(session, bounded())
    assert again.run.run_id == first.run.run_id
    assert again.reused_existing_run and not first.reused_existing_run
    loaded = await AreaForecastRunRepository(session).get(first.run.run_id)
    assert loaded.result == first.result
    assert first.result == forecast_area_product(bounded())
    assert len(first.result.daily_forecast) == 207
    assert await session.scalar(select(func.count()).select_from(AreaForecastDailyRow)) == 207


@pytest.mark.parametrize(
    "corruption",
    ["missing", "quantity", "hash", "total", "snapshot", "index", "share", "mass", "source"],
)
async def test_corruption_fail_closed(session, authority, corruption):
    saved = await execute_area_forecast_run(session, bounded())
    rid = saved.run.run_id
    if corruption == "missing":
        await session.execute(
            delete(AreaForecastDailyRow).where(AreaForecastDailyRow.row_index == 3)
        )
    elif corruption in {"quantity", "index", "share"}:
        values = {
            "quantity": {"predicted_kg": Decimal("999")},
            "index": {"row_index": 900},
            "share": {"share": Decimal("0.9")},
        }[corruption]
        await session.execute(
            update(AreaForecastDailyRow).where(AreaForecastDailyRow.row_index == 3).values(**values)
        )
    else:
        row = await session.get(AreaForecastRun, rid)
        if corruption == "hash":
            row.result_hash = "0" * 64
        elif corruption == "total":
            row.predicted_total_kg = Decimal("999")
        elif corruption == "snapshot":
            row.request_snapshot = {"invalid": True}
        else:
            meta = dict(row.result_metadata)
            if corruption == "mass":
                meta["mass_balance"] = {**meta["mass_balance"], "pass": False}
            else:
                meta["source_hashes"] = ["bad"]
            row.result_metadata = meta
        await session.flush()
    with pytest.raises(AreaForecastPersistenceIntegrityError):
        await AreaForecastRunRepository(session).get(rid)


@pytest.mark.parametrize("duplicate", ["date", "row_index"])
async def test_daily_unique_constraints(session, authority, duplicate):
    saved = await execute_area_forecast_run(session, bounded())
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            session.add(
                AreaForecastDailyRow(
                    run_id=saved.run.run_id,
                    row_index=999 if duplicate == "date" else 0,
                    date=date(2026, 10, 15) if duplicate == "date" else date(2030, 1, 1),
                    predicted_kg=Decimal(1),
                    share=Decimal(0),
                    share_text="0",
                )
            )
            await session.flush()


async def test_collision(session, authority):
    saved = await execute_area_forecast_run(session, bounded())
    await session.execute(update(AreaForecastRun).values(request_snapshot={"changed": True}))
    with pytest.raises(AreaForecastPersistenceConflictError):
        await execute_area_forecast_run(session, bounded())
    assert saved.run.run_id


async def test_caller_transaction(session, authority, monkeypatch):
    commit, rollback = AsyncMock(), AsyncMock()
    with monkeypatch.context() as m:
        m.setattr(session, "commit", commit)
        m.setattr(session, "rollback", rollback)
        await execute_area_forecast_run(session, bounded())
    commit.assert_not_called()
    rollback.assert_not_called()
    await session.rollback()
    assert await session.scalar(select(func.count()).select_from(AreaForecastRun)) == 0


async def test_atomic_failure(session, authority, monkeypatch):
    original = session.flush
    count = 0

    async def failing(*args, **kwargs):
        nonlocal count
        await original(*args, **kwargs)
        count += 1
        if count == 2:
            raise SQLAlchemyError("injected private database error")

    monkeypatch.setattr(session, "flush", failing)
    with pytest.raises(AreaForecastWriteFailure):
        await execute_area_forecast_run(session, bounded())
    assert await session.scalar(select(func.count()).select_from(AreaForecastRun)) == 0
    assert await session.scalar(select(func.count()).select_from(AreaForecastDailyRow)) == 0


async def test_rerun_lineage_and_read_without_authority(session, authority, monkeypatch):
    first = await execute_area_forecast_run(session, bounded())
    same = await execute_area_forecast_run(session, bounded(), rerun_of_run_id=first.run.run_id)
    assert same.run.run_id == first.run.run_id and same.reused_existing_run
    second = await execute_area_forecast_run(
        session, bounded(productive_area_mu="500"), rerun_of_run_id=first.run.run_id
    )
    assert second.run.rerun_of_run_id == first.run.run_id
    monkeypatch.delenv("AREA_YIELD_AUTHORITY_PATH")
    assert (await AreaForecastRunRepository(session).get(first.run.run_id)).result == first.result


async def test_one_snapshot_no_toctou(session, authority, monkeypatch):
    load = run_application.load_authority
    calls = []

    def once():
        calls.append(1)
        value = load()
        monkeypatch.setenv("AREA_YIELD_AUTHORITY_SHA256", "bad")
        return value

    monkeypatch.setattr(run_application, "load_authority", once)
    saved = await execute_area_forecast_run(session, bounded())
    assert len(calls) == 1 and saved.result.authority_hash == bundle()["hash"]


async def test_new_authority_new_execution(session, authority, monkeypatch):
    first = await execute_area_forecast_run(session, bounded())
    value = bundle()
    value["model_version"] = "changed-version"
    value["hash"] = digest({k: v for k, v in value.items() if k != "hash"})
    monkeypatch.setattr(run_application, "load_authority", lambda: value)
    second = await execute_area_forecast_run(session, bounded(), rerun_of_run_id=first.run.run_id)
    assert (
        second.run.run_id != first.run.run_id and second.run.request_hash != first.run.request_hash
    )


async def test_equal_result_hash_not_execution_key(session, authority, monkeypatch):
    value = bundle()
    value["aliases"] = {"alias": "known"}
    value["hash"] = digest({k: v for k, v in value.items() if k != "hash"})
    monkeypatch.setattr(run_application, "load_authority", lambda: value)
    one = await execute_area_forecast_run(session, bounded())
    two = await execute_area_forecast_run(session, bounded(farm="alias"))
    assert one.result.result_hash == two.result.result_hash and one.run.run_id != two.run.run_id


async def test_history_filters_pagination(session, authority):
    ids = []
    for area in ("100", "500", "1000"):
        ids.append(
            (await execute_area_forecast_run(session, bounded(productive_area_mu=area))).run.run_id
        )
    repo = AreaForecastRunRepository(session)
    first = await repo.history(canonical_farm="known", target_season="2026-2027", limit=2)
    last = await repo.history(limit=2, cursor=first.next_cursor)
    assert [r.run_id for r in first.items + last.items] == ids[::-1]
    assert last.next_cursor is None
    assert not (await repo.history(target_season="1900-1901")).items
    assert not (await repo.history(canonical_farm="other")).items
    assert "daily_forecast" not in first.model_dump_json()
