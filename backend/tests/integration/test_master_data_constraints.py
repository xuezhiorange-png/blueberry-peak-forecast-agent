import os
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.app.db.session import AsyncSessionMaker

pytestmark = pytest.mark.integration


def _require_postgres() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("set RUN_POSTGRES_INTEGRATION=1 when PostgreSQL is available")


async def _expect_integrity_error(sql: str, params: dict[str, Any] | None = None) -> None:
    async with AsyncSessionMaker() as session:
        with pytest.raises(IntegrityError):
            await session.execute(text(sql), params or {})
            await session.commit()


@pytest.mark.asyncio
async def test_master_data_database_constraints_and_indexes_exist() -> None:
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
        assert {
            "uq_dim_season_code",
            "ck_dim_season_date_range",
            "uq_dim_factory_code",
            "uq_dim_factory_name",
            "ck_dim_factory_latitude_range",
            "ck_dim_factory_longitude_range",
            "uq_dim_farm_name",
            "ck_dim_farm_latitude_range",
            "ck_dim_farm_longitude_range",
            "uq_dim_subfarm_farm_id_name",
            "fk_dim_subfarm_farm_id_dim_farm",
            "uq_dim_variety_code",
            "uq_dim_grade_code",
            "uq_dim_holiday_season_id_code",
            "ck_dim_holiday_date_range",
            "fk_dim_holiday_season_id_dim_season",
        }.issubset(constraints)

        indexes = {
            row[0]
            for row in (
                await session.execute(
                    text(
                        """
                        select indexname
                        from pg_indexes
                        where schemaname = 'public'
                        and tablename in (
                            'dim_factory',
                            'dim_subfarm',
                            'dim_holiday'
                        )
                        """
                    )
                )
            ).all()
        }
        assert {
            "ix_dim_factory_active",
            "ix_dim_subfarm_farm_id",
            "ix_dim_holiday_season_id",
            "ix_dim_holiday_region_name",
            "ix_dim_holiday_active",
        }.issubset(indexes)


@pytest.mark.asyncio
async def test_unique_constraints_reject_duplicate_values() -> None:
    _require_postgres()
    async with AsyncSessionMaker() as session:
        await session.execute(
            text(
                """
                insert into dim_season (code, start_date, end_date)
                values ('season-a', '2026-01-01', '2026-04-30')
                """
            )
        )
        await session.execute(
            text(
                """
                insert into dim_factory (code, name)
                values ('factory-a', 'Factory A')
                """
            )
        )
        await session.execute(
            text(
                """
                insert into dim_farm (name)
                values ('Farm A')
                """
            )
        )
        farm_id = (
            await session.execute(
                text(
                    """
                    insert into dim_farm (name)
                    values ('Farm B')
                    returning id
                    """
                )
            )
        ).scalar_one()
        await session.execute(
            text(
                """
                insert into dim_subfarm (farm_id, name)
                values (:farm_id, 'Block A')
                """
            ),
            {"farm_id": farm_id},
        )
        await session.execute(
            text(
                """
                insert into dim_variety (code, name)
                values ('variety-a', 'Variety A')
                """
            )
        )
        await session.execute(
            text(
                """
                insert into dim_grade (code)
                values ('grade-a')
                """
            )
        )
        season_id = (
            await session.execute(
                text(
                    """
                    insert into dim_season (code, start_date, end_date)
                    values ('season-b', '2026-01-01', '2026-04-30')
                    returning id
                    """
                )
            )
        ).scalar_one()
        await session.execute(
            text(
                """
                insert into dim_holiday (season_id, code, name, start_date, end_date)
                values (:season_id, 'holiday-a', 'Holiday A', '2026-02-01', '2026-02-03')
                """
            ),
            {"season_id": season_id},
        )
        await session.commit()

    await _expect_integrity_error(
        """
        insert into dim_season (code, start_date, end_date)
        values ('season-a', '2026-01-01', '2026-04-30')
        """
    )
    await _expect_integrity_error(
        """
        insert into dim_factory (code, name)
        values ('factory-a', 'Factory B')
        """
    )
    await _expect_integrity_error(
        """
        insert into dim_factory (code, name)
        values ('factory-b', 'Factory A')
        """
    )
    await _expect_integrity_error("insert into dim_farm (name) values ('Farm A')")
    await _expect_integrity_error(
        """
        insert into dim_subfarm (farm_id, name)
        values (:farm_id, 'Block A')
        """,
        {"farm_id": farm_id},
    )
    await _expect_integrity_error(
        """
        insert into dim_variety (code, name)
        values ('variety-a', 'Variety B')
        """
    )
    await _expect_integrity_error("insert into dim_grade (code) values ('grade-a')")
    await _expect_integrity_error(
        """
        insert into dim_holiday (season_id, code, name, start_date, end_date)
        values (:season_id, 'holiday-a', 'Holiday B', '2026-02-05', '2026-02-06')
        """,
        {"season_id": season_id},
    )


@pytest.mark.asyncio
async def test_foreign_key_constraints_reject_missing_parents() -> None:
    _require_postgres()
    await _expect_integrity_error(
        """
        insert into dim_subfarm (farm_id, name)
        values (999999999, 'Missing Farm Block')
        """
    )
    await _expect_integrity_error(
        """
        insert into dim_holiday (season_id, code, name, start_date, end_date)
        values (999999999, 'holiday-missing', 'Missing Season', '2026-02-01', '2026-02-03')
        """
    )


@pytest.mark.asyncio
async def test_check_constraints_reject_invalid_dates_and_coordinates() -> None:
    _require_postgres()
    await _expect_integrity_error(
        """
        insert into dim_season (code, start_date, end_date)
        values ('bad-season', '2026-05-01', '2026-01-01')
        """
    )
    await _expect_integrity_error(
        """
        insert into dim_factory (code, name, latitude)
        values ('factory-bad-latitude', 'Factory Bad Latitude', 91)
        """
    )
    await _expect_integrity_error(
        """
        insert into dim_factory (code, name, longitude)
        values ('factory-bad-longitude', 'Factory Bad Longitude', 181)
        """
    )
    await _expect_integrity_error(
        """
        insert into dim_farm (name, latitude)
        values ('Farm Bad Latitude', -91)
        """
    )
    await _expect_integrity_error(
        """
        insert into dim_farm (name, longitude)
        values ('Farm Bad Longitude', -181)
        """
    )

    async with AsyncSessionMaker() as session:
        season_id = (
            await session.execute(
                text(
                    """
                    insert into dim_season (code, start_date, end_date)
                    values ('season-holiday-check', '2026-01-01', '2026-04-30')
                    returning id
                    """
                )
            )
        ).scalar_one()
        await session.commit()

    await _expect_integrity_error(
        """
        insert into dim_holiday (season_id, code, name, start_date, end_date)
        values (:season_id, 'bad-holiday', 'Bad Holiday', '2026-02-20', '2026-02-10')
        """,
        {"season_id": season_id},
    )
