from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.harvest_state import (
    HarvestStateDailyMemberRowModel,
    HarvestStateRun,
)
from backend.app.models.master_data import Season
from backend.app.models.maturity import (
    MaturityDailyPredictionModel,
    MaturityForecastRun,
    MaturityModelArtifact,
)


@dataclass(frozen=True)
class Task8DailyPredictionSource:
    prediction_date: date
    p50_kg: Decimal
    p80_kg: Decimal
    p90_kg: Decimal


@dataclass(frozen=True)
class Task8AuthoritySource:
    run_id: int
    model_run_id: int
    status: str
    prediction_start_date: date
    prediction_end_date: date
    artifact_id: int
    artifact_run_id: int | None
    artifact_hash: str | None
    daily_predictions: tuple[Task8DailyPredictionSource, ...]


@dataclass(frozen=True)
class Task9MemberSource:
    state_date: date
    forecast_quantile: str
    farm_id: int
    subfarm_id: int | None
    variety_id: int
    destination_factory_id: int
    natural_maturity_supply_kg: Decimal
    opening_mature_inventory_kg: Decimal
    available_mature_quantity_kg: Decimal
    mature_inventory_loss_quantity_kg: Decimal
    harvestable_mature_quantity_kg: Decimal
    allocated_harvest_capacity_kg: Decimal
    harvested_quantity_kg: Decimal
    closing_mature_inventory_kg: Decimal
    unharvested_backlog_kg: Decimal


@dataclass(frozen=True)
class Task9AuthoritySource:
    run_id: int
    status: str
    forecast_start_date: date
    forecast_end_date: date
    destination_factory_id: int
    forecast_season_id: int | None
    maturity_forecast_run_id: int | None
    maturity_model_artifact_hash: str | None
    result_hash: str
    member_rows: tuple[Task9MemberSource, ...]


@dataclass(frozen=True)
class SeasonSource:
    season_id: int
    code: str


class CoreForecastRepository(Protocol):
    async def load_task8_authority(self, run_id: int) -> Task8AuthoritySource | None: ...

    async def load_task9_authority(self, run_id: int) -> Task9AuthoritySource | None: ...

    async def load_season(self, season_id: int) -> SeasonSource | None: ...


class SqlAlchemyCoreForecastRepository:
    """Read-only loader for the existing Task 8 and Task 9 authority tables."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load_task8_authority(self, run_id: int) -> Task8AuthoritySource | None:
        run = await self._session.get(MaturityForecastRun, run_id)
        if run is None:
            return None
        artifact = await self._session.get(MaturityModelArtifact, run.artifact_id)
        predictions = await self._session.scalars(
            select(MaturityDailyPredictionModel)
            .where(MaturityDailyPredictionModel.forecast_run_id == run_id)
            .order_by(MaturityDailyPredictionModel.prediction_date.asc())
        )
        return Task8AuthoritySource(
            run_id=run.id,
            model_run_id=run.model_run_id,
            status=run.status,
            prediction_start_date=run.prediction_start_date,
            prediction_end_date=run.prediction_end_date,
            artifact_id=run.artifact_id,
            artifact_run_id=artifact.run_id if artifact is not None else None,
            artifact_hash=artifact.artifact_hash if artifact is not None else None,
            daily_predictions=tuple(
                Task8DailyPredictionSource(
                    prediction_date=row.prediction_date,
                    p50_kg=row.p50_kg,
                    p80_kg=row.p80_kg,
                    p90_kg=row.p90_kg,
                )
                for row in predictions
            ),
        )

    async def load_task9_authority(self, run_id: int) -> Task9AuthoritySource | None:
        run = await self._session.get(HarvestStateRun, run_id)
        if run is None:
            return None
        members = await self._session.scalars(
            select(HarvestStateDailyMemberRowModel)
            .where(HarvestStateDailyMemberRowModel.harvest_state_run_id == run_id)
            .order_by(
                HarvestStateDailyMemberRowModel.state_date.asc(),
                HarvestStateDailyMemberRowModel.forecast_quantile.asc(),
                HarvestStateDailyMemberRowModel.farm_id.asc(),
                HarvestStateDailyMemberRowModel.subfarm_id.asc(),
                HarvestStateDailyMemberRowModel.variety_id.asc(),
                HarvestStateDailyMemberRowModel.id.asc(),
            )
        )
        return Task9AuthoritySource(
            run_id=run.id,
            status=run.status,
            forecast_start_date=run.forecast_start_date,
            forecast_end_date=run.forecast_end_date,
            destination_factory_id=run.destination_factory_id,
            forecast_season_id=run.forecast_season_id,
            maturity_forecast_run_id=run.maturity_forecast_run_id,
            maturity_model_artifact_hash=run.maturity_model_artifact_hash,
            result_hash=run.result_hash,
            member_rows=tuple(
                Task9MemberSource(
                    state_date=row.state_date,
                    forecast_quantile=row.forecast_quantile,
                    farm_id=row.farm_id,
                    subfarm_id=row.subfarm_id,
                    variety_id=row.variety_id,
                    destination_factory_id=row.destination_factory_id,
                    natural_maturity_supply_kg=row.natural_maturity_supply_kg,
                    opening_mature_inventory_kg=row.opening_mature_inventory_kg,
                    available_mature_quantity_kg=row.available_mature_quantity_kg,
                    mature_inventory_loss_quantity_kg=row.mature_inventory_loss_quantity_kg,
                    harvestable_mature_quantity_kg=row.harvestable_mature_quantity_kg,
                    allocated_harvest_capacity_kg=row.allocated_harvest_capacity_kg,
                    harvested_quantity_kg=row.harvested_quantity_kg,
                    closing_mature_inventory_kg=row.closing_mature_inventory_kg,
                    unharvested_backlog_kg=row.unharvested_backlog_kg,
                )
                for row in members
            ),
        )

    async def load_season(self, season_id: int) -> SeasonSource | None:
        season = await self._session.get(Season, season_id)
        if season is None:
            return None
        return SeasonSource(season_id=season.id, code=season.code)
