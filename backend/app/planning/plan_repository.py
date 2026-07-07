from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from typing import Any, cast

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.master_data import Farm, Season, Subfarm, Variety
from backend.app.models.production_plan import FarmSeasonVarietyPlan, ProductionPlanImportRun


def _now() -> datetime:
    return datetime.now(UTC)


def production_plan_business_lock_key(
    *,
    farm_id: int,
    subfarm_id: int | None,
    season_id: int,
    variety_id: int,
) -> int:
    subfarm_component = subfarm_id if subfarm_id is not None else -1
    payload = f"farm:{farm_id}|subfarm:{subfarm_component}|season:{season_id}|variety:{variety_id}"
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


async def acquire_production_plan_lock(
    session: AsyncSession,
    *,
    farm_id: int,
    subfarm_id: int | None,
    season_id: int,
    variety_id: int,
) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    await session.execute(
        select(
            func.pg_advisory_xact_lock(
                production_plan_business_lock_key(
                    farm_id=farm_id,
                    subfarm_id=subfarm_id,
                    season_id=season_id,
                    variety_id=variety_id,
                )
            )
        )
    )


async def get_farm(session: AsyncSession, *, farm_id: int) -> Farm | None:
    return await session.get(Farm, farm_id)


async def get_subfarm(session: AsyncSession, *, subfarm_id: int) -> Subfarm | None:
    return await session.get(Subfarm, subfarm_id)


async def get_season(session: AsyncSession, *, season_id: int) -> Season | None:
    return await session.get(Season, season_id)


async def get_variety(session: AsyncSession, *, variety_id: int) -> Variety | None:
    return await session.get(Variety, variety_id)


async def get_farm_by_name(session: AsyncSession, *, farm_name: str) -> Farm | None:
    return cast(
        Farm | None,
        await session.scalar(select(Farm).where(Farm.name == farm_name)),
    )


async def get_subfarm_by_name(
    session: AsyncSession,
    *,
    farm_id: int,
    subfarm_name: str,
) -> Subfarm | None:
    return cast(
        Subfarm | None,
        await session.scalar(
            select(Subfarm).where(
                Subfarm.farm_id == farm_id,
                Subfarm.name == subfarm_name,
            )
        ),
    )


async def get_season_by_code(session: AsyncSession, *, season_code: str) -> Season | None:
    return cast(
        Season | None,
        await session.scalar(select(Season).where(Season.code == season_code)),
    )


async def get_variety_by_code(session: AsyncSession, *, variety_code: str) -> Variety | None:
    return cast(
        Variety | None,
        await session.scalar(select(Variety).where(Variety.code == variety_code)),
    )


async def get_plan_by_id(
    session: AsyncSession,
    *,
    plan_id: int,
    for_update: bool = False,
) -> FarmSeasonVarietyPlan | None:
    statement = select(FarmSeasonVarietyPlan).where(FarmSeasonVarietyPlan.id == plan_id)
    if for_update and session.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update()
    return cast(FarmSeasonVarietyPlan | None, await session.scalar(statement))


async def get_plan_by_row_hash(
    session: AsyncSession,
    *,
    row_hash: str,
) -> FarmSeasonVarietyPlan | None:
    return cast(
        FarmSeasonVarietyPlan | None,
        await session.scalar(
            select(FarmSeasonVarietyPlan).where(FarmSeasonVarietyPlan.row_hash == row_hash)
        ),
    )


async def list_plan_versions_by_key(
    session: AsyncSession,
    *,
    farm_id: int,
    subfarm_id: int | None,
    season_id: int,
    variety_id: int,
    for_update: bool = False,
) -> list[FarmSeasonVarietyPlan]:
    statement = select(FarmSeasonVarietyPlan).where(
        FarmSeasonVarietyPlan.farm_id == farm_id,
        FarmSeasonVarietyPlan.season_id == season_id,
        FarmSeasonVarietyPlan.variety_id == variety_id,
    )
    if subfarm_id is None:
        statement = statement.where(FarmSeasonVarietyPlan.subfarm_id.is_(None))
    else:
        statement = statement.where(FarmSeasonVarietyPlan.subfarm_id == subfarm_id)
    statement = statement.order_by(
        FarmSeasonVarietyPlan.effective_from.asc(),
        FarmSeasonVarietyPlan.version.asc(),
        FarmSeasonVarietyPlan.id.asc(),
    )
    if for_update and session.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update()
    return list((await session.scalars(statement)).all())


async def create_plan(
    session: AsyncSession,
    *,
    plan: FarmSeasonVarietyPlan,
) -> FarmSeasonVarietyPlan:
    session.add(plan)
    await session.flush()
    return plan


async def create_replacement_plan(
    session: AsyncSession,
    *,
    current_plan_id: int,
    current_effective_to: date,
    new_plan: FarmSeasonVarietyPlan,
) -> FarmSeasonVarietyPlan:
    await session.execute(
        update(FarmSeasonVarietyPlan)
        .where(FarmSeasonVarietyPlan.id == current_plan_id)
        .values(
            effective_to=current_effective_to,
            updated_at=_now(),
        )
    )
    session.add(new_plan)
    await session.flush()
    return new_plan


async def create_import_run(
    session: AsyncSession,
    *,
    file_name: str,
    file_sha256: str,
    source_version: str | None,
    status: str,
    report_json: dict[str, Any],
) -> ProductionPlanImportRun:
    run = ProductionPlanImportRun(
        file_name=file_name,
        file_sha256=file_sha256,
        source_version=source_version,
        status=status,
        report_json=report_json,
    )
    session.add(run)
    await session.commit()
    return run


async def mark_import_run_completed(
    session: AsyncSession,
    *,
    run_id: int,
    row_count: int,
    inserted_count: int,
    skipped_count: int,
    rejected_count: int,
    duplicate_count: int,
    unknown_farm_count: int,
    unknown_subfarm_count: int,
    unknown_season_count: int,
    unknown_variety_count: int,
    invalid_date_count: int,
    invalid_numeric_count: int,
    overlap_conflict_count: int,
    version_conflict_count: int,
    report_json: dict[str, Any],
) -> None:
    await session.execute(
        update(ProductionPlanImportRun)
        .where(ProductionPlanImportRun.id == run_id)
        .values(
            status="completed",
            row_count=row_count,
            inserted_count=inserted_count,
            skipped_count=skipped_count,
            rejected_count=rejected_count,
            duplicate_count=duplicate_count,
            unknown_farm_count=unknown_farm_count,
            unknown_subfarm_count=unknown_subfarm_count,
            unknown_season_count=unknown_season_count,
            unknown_variety_count=unknown_variety_count,
            invalid_date_count=invalid_date_count,
            invalid_numeric_count=invalid_numeric_count,
            overlap_conflict_count=overlap_conflict_count,
            version_conflict_count=version_conflict_count,
            report_json=report_json,
            finished_at=_now(),
            error_message=None,
        )
    )
    await session.commit()


async def mark_import_run_failed(
    session: AsyncSession,
    *,
    run_id: int,
    report_json: dict[str, Any],
    error_message: str,
) -> None:
    await session.execute(
        update(ProductionPlanImportRun)
        .where(ProductionPlanImportRun.id == run_id)
        .values(
            status="failed",
            report_json=report_json,
            error_message=error_message,
            finished_at=_now(),
        )
    )
    await session.commit()
