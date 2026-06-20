import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text

from backend.app.db.session import AsyncSessionMaker

_MASTER_DATA_TABLES = (
    "dim_holiday",
    "dim_subfarm",
    "dim_grade",
    "dim_variety",
    "dim_farm",
    "dim_factory",
    "dim_season",
)


async def _truncate_master_data() -> None:
    async with AsyncSessionMaker() as session:
        await session.execute(
            text(f"TRUNCATE {', '.join(_MASTER_DATA_TABLES)} RESTART IDENTITY CASCADE")
        )
        await session.commit()


@pytest.fixture(autouse=True)
async def isolate_master_data_tables() -> AsyncIterator[None]:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        yield
        return

    await _truncate_master_data()
    try:
        yield
    finally:
        await _truncate_master_data()
