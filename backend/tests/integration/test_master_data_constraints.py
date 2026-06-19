import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.app.db.session import AsyncSessionMaker

pytestmark = pytest.mark.integration


def _require_postgres() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("set RUN_POSTGRES_INTEGRATION=1 when PostgreSQL is available")


@pytest.mark.asyncio
async def test_master_data_database_constraints_exist_and_enforced() -> None:
    _require_postgres()
    async with AsyncSessionMaker() as session:
        table_names = {
            row[0]
            for row in (
                await session.execute(
                    text(
                        """
                        select tablename
                        from pg_tables
                        where schemaname = 'public'
                        and tablename like 'dim_%'
                        """
                    )
                )
            ).all()
        }
        assert {
            "dim_season",
            "dim_factory",
            "dim_farm",
            "dim_subfarm",
            "dim_variety",
            "dim_grade",
            "dim_holiday",
        }.issubset(table_names)

        constraints = {
            row[0]
            for row in (
                await session.execute(
                    text(
                        """
                        select conname
                        from pg_constraint
                        where conrelid::regclass::text in (
                            'dim_season',
                            'dim_factory',
                            'dim_farm',
                            'dim_subfarm',
                            'dim_variety',
                            'dim_grade',
                            'dim_holiday'
                        )
                        """
                    )
                )
            ).all()
        }
        assert "ck_dim_season_date_range" in constraints
        assert "ck_dim_holiday_date_range" in constraints
        assert "uq_dim_subfarm_farm_id_name" in constraints
        assert "fk_dim_subfarm_farm_id_dim_farm" in constraints
        assert "fk_dim_holiday_season_id_dim_season" in constraints


@pytest.mark.asyncio
async def test_master_data_database_constraints_are_enforced() -> None:
    _require_postgres()
    suffix = uuid4().hex[:12]
    async with AsyncSessionMaker() as session:
        await session.execute(
            text(
                """
                insert into dim_season (code, start_date, end_date)
                values (:code, '2026-01-01', '2026-04-30')
                """
            ),
            {"code": f"season-{suffix}"},
        )
        await session.flush()

        with pytest.raises(IntegrityError):
            await session.execute(
                text(
                    """
                    insert into dim_season (code, start_date, end_date)
                    values (:code, '2026-01-01', '2026-04-30')
                    """
                ),
                {"code": f"season-{suffix}"},
            )
            await session.flush()
        await session.rollback()

    async with AsyncSessionMaker() as session:
        with pytest.raises(IntegrityError):
            await session.execute(
                text(
                    """
                    insert into dim_season (code, start_date, end_date)
                    values (:code, '2026-05-01', '2026-01-01')
                    """
                ),
                {"code": f"bad-season-{suffix}"},
            )
            await session.flush()
        await session.rollback()

    async with AsyncSessionMaker() as session:
        farm_id = (
            await session.execute(
                text(
                    """
                    insert into dim_farm (name)
                    values (:name)
                    returning id
                    """
                ),
                {"name": f"Farm-{suffix}"},
            )
        ).scalar_one()
        await session.execute(
            text(
                """
                insert into dim_subfarm (farm_id, name)
                values (:farm_id, :name)
                """
            ),
            {"farm_id": farm_id, "name": f"Block-{suffix}"},
        )
        await session.flush()

        with pytest.raises(IntegrityError):
            await session.execute(
                text(
                    """
                    insert into dim_subfarm (farm_id, name)
                    values (:farm_id, :name)
                    """
                ),
                {"farm_id": farm_id, "name": f"Block-{suffix}"},
            )
            await session.flush()
        await session.rollback()

    async with AsyncSessionMaker() as session:
        with pytest.raises(IntegrityError):
            await session.execute(
                text(
                    """
                    insert into dim_subfarm (farm_id, name)
                    values (999999999, :name)
                    """
                ),
                {"name": f"MissingFarm-{suffix}"},
            )
            await session.flush()
        await session.rollback()

    async with AsyncSessionMaker() as session:
        season_id = (
            await session.execute(
                text(
                    """
                    insert into dim_season (code, start_date, end_date)
                    values (:code, '2026-01-01', '2026-04-30')
                    returning id
                    """
                ),
                {"code": f"holiday-season-{suffix}"},
            )
        ).scalar_one()
        with pytest.raises(IntegrityError):
            await session.execute(
                text(
                    """
                    insert into dim_holiday (season_id, code, name, start_date, end_date)
                    values (:season_id, :code, :name, '2026-02-20', '2026-02-10')
                    """
                ),
                {
                    "season_id": season_id,
                    "code": f"bad-holiday-{suffix}",
                    "name": "Bad holiday",
                },
            )
            await session.flush()
        await session.rollback()
