from __future__ import annotations

from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.harvest_state import (
    HarvestStateCohortTransitionRowModel,
    HarvestStateDailyMemberRowModel,
    HarvestStateDailyPoolRowModel,
    HarvestStateFutureArrivalRowModel,
    HarvestStateRun,
)


async def get_harvest_state_run(
    session: AsyncSession,
    *,
    run_id: int,
) -> HarvestStateRun | None:
    return await session.get(HarvestStateRun, run_id)


async def get_harvest_state_run_by_result_hash(
    session: AsyncSession,
    *,
    result_hash: str,
) -> HarvestStateRun | None:
    return cast(
        HarvestStateRun | None,
        await session.scalar(
            select(HarvestStateRun).where(HarvestStateRun.result_hash == result_hash)
        ),
    )


async def list_harvest_state_daily_pool_rows(
    session: AsyncSession,
    *,
    run_id: int,
) -> list[HarvestStateDailyPoolRowModel]:
    statement = (
        select(HarvestStateDailyPoolRowModel)
        .where(HarvestStateDailyPoolRowModel.harvest_state_run_id == run_id)
        .order_by(
            HarvestStateDailyPoolRowModel.state_date.asc(),
            HarvestStateDailyPoolRowModel.capacity_pool_id.asc(),
            HarvestStateDailyPoolRowModel.forecast_quantile.asc(),
        )
    )
    return list((await session.scalars(statement)).all())


async def list_harvest_state_daily_member_rows(
    session: AsyncSession,
    *,
    run_id: int,
) -> list[HarvestStateDailyMemberRowModel]:
    statement = (
        select(HarvestStateDailyMemberRowModel)
        .where(HarvestStateDailyMemberRowModel.harvest_state_run_id == run_id)
        .order_by(
            HarvestStateDailyMemberRowModel.state_date.asc(),
            HarvestStateDailyMemberRowModel.capacity_pool_id.asc(),
            HarvestStateDailyMemberRowModel.farm_id.asc(),
            HarvestStateDailyMemberRowModel.subfarm_id.asc().nullsfirst(),
            HarvestStateDailyMemberRowModel.variety_id.asc(),
            HarvestStateDailyMemberRowModel.forecast_quantile.asc(),
        )
    )
    return list((await session.scalars(statement)).all())


async def list_harvest_state_cohort_transition_rows(
    session: AsyncSession,
    *,
    run_id: int,
) -> list[HarvestStateCohortTransitionRowModel]:
    statement = (
        select(HarvestStateCohortTransitionRowModel)
        .where(HarvestStateCohortTransitionRowModel.harvest_state_run_id == run_id)
        .order_by(
            HarvestStateCohortTransitionRowModel.state_date.asc(),
            HarvestStateCohortTransitionRowModel.capacity_pool_id.asc(),
            HarvestStateCohortTransitionRowModel.cohort_date.asc(),
            HarvestStateCohortTransitionRowModel.variety_id.asc(),
            HarvestStateCohortTransitionRowModel.subfarm_id.asc().nullsfirst(),
            HarvestStateCohortTransitionRowModel.stable_cohort_key.asc(),
        )
    )
    return list((await session.scalars(statement)).all())


async def list_harvest_state_future_arrival_rows(
    session: AsyncSession,
    *,
    run_id: int,
) -> list[HarvestStateFutureArrivalRowModel]:
    statement = (
        select(HarvestStateFutureArrivalRowModel)
        .where(HarvestStateFutureArrivalRowModel.harvest_state_run_id == run_id)
        .order_by(
            HarvestStateFutureArrivalRowModel.destination_factory_id.asc(),
            HarvestStateFutureArrivalRowModel.arrival_local_date.asc(),
            HarvestStateFutureArrivalRowModel.variety_id.asc(),
            HarvestStateFutureArrivalRowModel.forecast_quantile.asc(),
            HarvestStateFutureArrivalRowModel.capacity_pool_id.asc(),
            HarvestStateFutureArrivalRowModel.farm_id.asc(),
            HarvestStateFutureArrivalRowModel.subfarm_id.asc().nullsfirst(),
        )
    )
    return list((await session.scalars(statement)).all())
