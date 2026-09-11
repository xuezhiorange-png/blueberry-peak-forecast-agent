"""Register the pinned, explicitly authorized acceptance curve; never forecasts.

Database binding comes from normal externalized application configuration.
Only the pre-TEST 2024/25 ledger is read. No raw business rows are printed.
"""

import asyncio
import json
from datetime import date
from decimal import Decimal

from sqlalchemy import select, text

from backend.app.db.session import AsyncSessionMaker, engine
from backend.app.harvest_state.canonical import make_season_record_hash
from backend.app.models.master_data import Factory, Farm, Season, Variety
from backend.app.planning.empirical_authority import persist_empirical_authority
from backend.app.planning.empirical_maturity import build_empirical_curve
from backend.app.services.master_data import create_master_data
from scripts.probe_banna_harvest_baseline_r4 import SOURCE_HASH, load_verified_facts


async def main() -> None:
    daily: dict[date, Decimal] = {}
    for fact in load_verified_facts():
        daily[fact.harvest_date] = (
            daily.get(fact.harvest_date, Decimal(0)) + fact.arrival_quantity_kg
        )
    curve = build_empirical_curve(
        daily, source_hash=SOURCE_HASH, area_mu=Decimal("736.000000"), as_of=date(2026, 9, 11)
    )
    if (len(daily), len(curve["days"]), curve["historical_total_kg"], curve["yield_kg_per_mu"]) != (
        181,
        207,
        "968113.233000",
        "1315.371240",
    ):
        raise ValueError("pinned acceptance source aggregate mismatch")
    async with AsyncSessionMaker() as session:
        farm = (await session.scalars(select(Farm).where(Farm.name == "版纳勐旺农场"))).one()
        factory = (
            await session.scalars(
                select(Factory).where(Factory.name == "勐旺加工厂", Factory.active.is_(True))
            )
        ).one()
        variety = (await session.scalars(select(Variety).where(Variety.code == "Dx"))).one()
        # This narrow baseline registration cannot replace existing operational authority.
        absence = {}
        for table in (
            "task9_daily_capacity_authority",
            "task9_weather_rule_config_version",
            "task9_initial_inventory_snapshot",
            "task9_mature_inventory_loss_authority",
        ):
            count = await session.scalar(text("SELECT count(*) FROM " + table))
            absence[table] = count
            if count != 0:
                raise ValueError("existing operational authority requires normal resolution")
        code = "BANNA_EMPIRICAL_ACCEPTANCE_2026_2027"
        season = await session.scalar(select(Season).where(Season.code == code))
        start, end = (
            date.fromisoformat(curve["forecast_start"]),
            date.fromisoformat(curve["forecast_end"]),
        )
        if season is None:
            season = await create_master_data(
                session, Season, dict(code=code, start_date=start, end_date=end)
            )
        if (season.start_date, season.end_date) != (start, end):
            raise ValueError("acceptance season identity conflict")
        payload = dict(
            curve=curve,
            scope=dict(
                farm_id=farm.id,
                factory_id=factory.id,
                variety_id=variety.id,
                subfarm_id=None,
                farm_name=farm.name,
                factory_name=factory.name,
                variety_code=variety.code,
                acceptance_scope_id="BANNA_MENGWANG_DX_736MU_R1",
            ),
            season=dict(
                season_id=season.id,
                season_code=code,
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                season_record_hash=make_season_record_hash(
                    season_id=season.id, season_code=code, start_date=start, end_date=end
                ),
            ),
            operational_policy=dict(
                authority_type="BASELINE_POLICY",
                authorization="COORDINATOR_R5",
                existing_authority_row_counts=absence,
                labor_multiplier="1.000000",
                weather_multiplier="1.000000",
                operational_multiplier="1.000000",
                opening_inventory_kg="0.000",
                mature_loss_kg="0.000",
                note=(
                    "No observed operational rows; empty initial baseline, no extra loss/discount. "
                    "Not observed operational truth."
                ),
            ),
        )
        authority_hash = await persist_empirical_authority(session, payload)
        await session.commit()
        print(
            json.dumps(
                dict(
                    authority_hash=authority_hash,
                    curve_hash=curve["curve_hash"],
                    season_id=season.id,
                    day_count=len(curve["days"]),
                    source_hash=SOURCE_HASH,
                ),
                ensure_ascii=False,
            )
        )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
