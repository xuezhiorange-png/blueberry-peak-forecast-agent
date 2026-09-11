"""Synthetic-only application fixtures; no business/validation dataset loader."""

from datetime import date
from decimal import Decimal

import pytest

from backend.app.harvest_state.canonical import make_season_record_hash, sha256_hex
from backend.app.harvest_state.service import run_harvest_state_model
from backend.app.planning.empirical_authority import verify_authority
from backend.app.planning.empirical_forecast import build_empirical_task9_request
from backend.app.planning.empirical_maturity import build_empirical_curve


def authority():
    curve = build_empirical_curve(
        {date(2024, 10, 15): Decimal("10"), date(2024, 10, 22): Decimal("20")},
        source_hash="a" * 64,
        area_mu=Decimal("736"),
        as_of=date(2026, 9, 11),
    )
    season = dict(
        season_id=1, season_code="synthetic-season", start_date="2026-10-15", end_date="2026-10-22"
    )
    season["season_record_hash"] = make_season_record_hash(
        season_id=1,
        season_code=season["season_code"],
        start_date=date(2026, 10, 15),
        end_date=date(2026, 10, 22),
    )
    return dict(
        curve=curve,
        season=season,
        scope=dict(farm_id=1, variety_id=1, factory_id=1),
        operational_policy={"authority_type": "BASELINE_POLICY"},
    )


def test_empirical_task9_accepts_distinct_authority_and_preserves_mass_balance():
    payload = authority()
    request = build_empirical_task9_request(payload)
    assert not request.task8_daily_predictions
    assert len(request.empirical_daily_predictions) == 24
    output = run_harvest_state_model(request)
    assert output.status == "completed", output
    assert all(
        r.mass_balance_passed and r.capacity_constraint_passed for r in output.daily_pool_state_rows
    )
    assert all(
        r.arrival_quantity_kg == r.harvested_quantity_kg for r in output.daily_pool_state_rows
    )
    assert all(r.closing_mature_inventory_kg == 0 for r in output.daily_pool_state_rows)


def test_empirical_authority_replays_without_task5_maturity_scalars():
    payload = authority()
    verify_authority(payload, sha256_hex(payload))
    assert all(
        name not in str(payload)
        for name in ("maturity_width_days", "maturity_skewness", "maturity_peak_offset_days")
    )
    payload["curve"]["days"][0]["supply_kg"] = "100"
    with pytest.raises(ValueError, match="replay mismatch"):
        verify_authority(payload, sha256_hex(payload))


@pytest.mark.asyncio
async def test_empirical_forecast_persisted_fresh_session_round_trip():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from backend.app.models.empirical_forecast import (
        EmpiricalForecastRun,
        EmpiricalMaturityAuthority,
    )
    from backend.app.models.master_data import Season
    from backend.app.planning.empirical_authority import (
        persist_empirical_authority,
        verify_empirical_task9_request,
    )
    from backend.app.planning.empirical_forecast import (
        EmpiricalForecastCreateRequest,
        create_empirical_forecast,
        read_empirical_forecast,
    )
    from backend.tests.harvest_state.conftest import HARVEST_STATE_TABLES

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda c: Season.metadata.create_all(
                c,
                tables=[
                    *HARVEST_STATE_TABLES,
                    EmpiricalMaturityAuthority.__table__,
                    EmpiricalForecastRun.__table__,
                ],
            )
        )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        session.add(
            Season(
                id=1,
                code="synthetic-season",
                start_date=date(2026, 10, 15),
                end_date=date(2026, 10, 22),
            )
        )
        h = await persist_empirical_authority(session, authority())
        tampered = build_empirical_task9_request(authority())
        tampered.daily_capacity_inputs[0].labor_availability_ratio = Decimal("0.5")
        with pytest.raises(ValueError, match="operational policy binding"):
            await verify_empirical_task9_request(session, tampered)
        result = await create_empirical_forecast(
            session,
            EmpiricalForecastCreateRequest(
                maturity_authority_type="HISTORICAL_CALIBRATION", authority_hash=h
            ),
            actor_identity="synthetic-unit-actor",
        )
        await session.commit()
    async with sessions() as fresh:
        replay = await read_empirical_forecast(fresh, result.run_id)
        assert replay == result
        assert len(replay.payload["daily_rows"]) == 8
        assert all(
            r["arrival_quantity_kg"] == r["harvested_quantity_kg"]
            for r in replay.payload["daily_rows"]
        )
    await engine.dispose()


def test_empirical_migration_creates_immutable_separate_authority():
    import importlib

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import IntegrityError

    migration = importlib.import_module(
        "backend.alembic.versions.0033_empirical_maturity_authority"
    )
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            connection.execute(
                text(
                    "INSERT INTO empirical_maturity_authority(authority_hash,payload) "
                    "VALUES (:h,'{}')"
                ),
                {"h": "a" * 64},
            )
            with pytest.raises(IntegrityError, match="immutable"):
                connection.execute(text("UPDATE empirical_maturity_authority SET payload='{}'"))
            with pytest.raises(IntegrityError, match="immutable"):
                connection.execute(text("DELETE FROM empirical_maturity_authority"))
            migration.downgrade()
    engine.dispose()
