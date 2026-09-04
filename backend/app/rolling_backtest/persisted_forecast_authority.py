"""Shared canonical persisted S2 forecast authority validation.

Production semantics are sourced from ``resolve_s2_persisted_authorities`` in
``orchestration.py``. Both rolling-backtest S2 and the S3-B live pairing
adapter must use these helpers rather than weaker local definitions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Literal, Protocol, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.app.core_forecast.repository import Task9AuthoritySource, Task9MemberSource
from backend.app.models.core_forecast import (
    CoreForecastCodeAuthorityModel,
    CoreForecastDailyRowModel,
    CoreForecastRunModel,
)
from backend.app.models.harvest_state import HarvestStateDailyMemberRowModel, HarvestStateRun
from backend.app.models.residual_model import (
    ResidualModelPredictionRow,
    ResidualModelPredictionRun,
    ResidualModelTrainingRun,
)
from backend.app.rolling_backtest.orchestration import _task9_member_identity_hash
from backend.app.rolling_backtest.schemas import S2ForecastAuthorityBundle

ForecastQuantile = Literal["P50", "P80", "P90"]

MATERIAL_S2_FORECAST_AUTHORITY_BUNDLE_FIELDS: tuple[str, ...] = (
    "forecast_run_identity_hash",
    "daily_row_identity_hash",
    "task9_authority_identity_hash",
    "task9_member_identity_hash",
    "task10_authority_identity_hash",
    "task10_model_identity_hash",
    "task10_replay_identity_hash",
    "task10_prediction_row_identity_hash",
    "historical_code_authority_id",
    "forecast_code_identity",
    "historical_code_identity",
    "build_artifact_hash",
    "config_bundle_hash",
    "model_identity",
    "parameter_identity",
    "data_identity",
    "available_at",
    "task10_model_available_at",
    "historical_code_available_at",
)


class _CodeAuthorityLike(Protocol):
    authority_id: int
    authority_hash: str
    source_commit_sha: str
    build_artifact_hash: str
    config_bundle_hash: str
    available_at: datetime


def _code_authority_record_id(code_authority: Any) -> int:
    authority_id = getattr(code_authority, "authority_id", None)
    if authority_id is not None:
        return int(authority_id)
    return int(code_authority.id)


@dataclass(frozen=True, slots=True)
class _Task10RowBinding:
    destination_factory_id: int


@dataclass(frozen=True, slots=True)
class CanonicalPersistedForecastAuthorityResolution:
    core_run: CoreForecastRunModel
    core_row: CoreForecastDailyRowModel
    code_authority: CoreForecastCodeAuthorityModel
    task9_run: HarvestStateRun
    task9_member: HarvestStateDailyMemberRowModel
    task9_member_identity_hash: str
    prediction_run: ResidualModelPredictionRun
    prediction_row: ResidualModelPredictionRow
    training_run: ResidualModelTrainingRun
    task10_model_identity_hash: str


def _as_utc_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _cutoff_matches(left: datetime | None, right: datetime) -> bool:
    if left is None:
        return False
    return _as_utc_aware(left) == _as_utc_aware(right)


def _visible_at_or_before(value: datetime | None, cutoff_at: datetime) -> bool:
    if value is None:
        return False
    return _as_utc_aware(value) <= _as_utc_aware(cutoff_at)


def _member_source_from_row(row: HarvestStateDailyMemberRowModel) -> Task9MemberSource:
    return Task9MemberSource(
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


def load_task9_authority_sync(session: Session, run_id: int) -> Task9AuthoritySource | None:
    task9_run = session.get(HarvestStateRun, run_id)
    if task9_run is None:
        return None
    members = tuple(
        session.scalars(
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
        ).all()
    )
    return Task9AuthoritySource(
        run_id=task9_run.id,
        status=task9_run.status,
        forecast_start_date=task9_run.forecast_start_date,
        forecast_end_date=task9_run.forecast_end_date,
        destination_factory_id=task9_run.destination_factory_id,
        forecast_season_id=task9_run.forecast_season_id,
        maturity_forecast_run_id=task9_run.maturity_forecast_run_id,
        maturity_model_artifact_hash=task9_run.maturity_model_artifact_hash,
        result_hash=task9_run.result_hash,
        member_rows=tuple(_member_source_from_row(row) for row in members),
        forecast_effective_cutoff_at=task9_run.forecast_effective_cutoff_at,
    )


def build_canonical_s2_forecast_authority_bundle(
    resolution: CanonicalPersistedForecastAuthorityResolution,
) -> S2ForecastAuthorityBundle:
    code_authority = resolution.code_authority
    core_run = resolution.core_run
    core_row = resolution.core_row
    task9_run = resolution.task9_run
    prediction_run = resolution.prediction_run
    prediction_row = resolution.prediction_row
    training_run = resolution.training_run
    available_at = task9_run.forecast_effective_cutoff_at or core_run.forecast_effective_cutoff_at
    if available_at is None:
        raise ValueError("forecast authority cutoff is missing")
    if training_run.finished_at is None:
        raise ValueError("Task 10 model authority is incomplete or identity-drifted")
    return S2ForecastAuthorityBundle(
        forecast_run_identity_hash=core_run.result_hash,
        daily_row_identity_hash=core_row.row_hash,
        task9_authority_identity_hash=task9_run.result_hash,
        task9_member_identity_hash=resolution.task9_member_identity_hash,
        task10_authority_identity_hash=prediction_run.prediction_hash,
        task10_model_identity_hash=resolution.task10_model_identity_hash,
        task10_replay_identity_hash=prediction_run.prediction_input_signature,
        task10_prediction_row_identity_hash=prediction_row.prediction_row_hash,
        historical_code_authority_id=code_authority.id,
        forecast_code_identity=code_authority.authority_hash,
        historical_code_identity=code_authority.source_commit_sha,
        build_artifact_hash=code_authority.build_artifact_hash,
        config_bundle_hash=code_authority.config_bundle_hash,
        model_identity=core_run.task8_artifact_hash,
        parameter_identity=core_row.marketable_policy_hash,
        data_identity=core_run.forecast_input_hash,
        available_at=_as_utc_aware(available_at),
        task10_model_available_at=_as_utc_aware(training_run.finished_at),
        historical_code_available_at=_as_utc_aware(code_authority.available_at),
    )


def assert_full_s2_forecast_authority_bundle_equivalence(
    left: S2ForecastAuthorityBundle,
    right: S2ForecastAuthorityBundle,
) -> None:
    for field_name in MATERIAL_S2_FORECAST_AUTHORITY_BUNDLE_FIELDS:
        if getattr(left, field_name) != getattr(right, field_name):
            raise ValueError(f"forecast authority bundle field mismatch: {field_name}")


def validate_canonical_code_authority(
    *,
    code_authority: Any,
    core_run: CoreForecastRunModel,
    forecast_cutoff_at: datetime,
) -> None:
    if core_run.code_authority_id != _code_authority_record_id(code_authority):
        raise ValueError("core forecast code authority id does not match persisted reference")
    if core_run.code_authority_hash != code_authority.authority_hash:
        raise ValueError("core forecast code authority hash does not match persisted reference")
    if not _visible_at_or_before(code_authority.available_at, forecast_cutoff_at):
        raise ValueError("historical code authority is visible after the forecast cutoff")


def validate_canonical_core_forecast_chain(
    *,
    core_run: CoreForecastRunModel,
    core_row: CoreForecastDailyRowModel,
    forecast_cutoff_at: datetime,
    target_date: date,
) -> None:
    if core_run.status != "completed":
        raise ValueError("core forecast run must be completed")
    if not _cutoff_matches(core_run.forecast_effective_cutoff_at, forecast_cutoff_at):
        raise ValueError("core forecast cutoff does not match requested forecast cutoff")
    if not _visible_at_or_before(core_run.completed_at, forecast_cutoff_at):
        raise ValueError("core forecast run is visible after the forecast cutoff")
    if core_row.core_forecast_run_id != core_run.id:
        raise ValueError("forecast daily row does not belong to requested core run")
    if core_row.date != target_date:
        raise ValueError("forecast daily row does not belong to requested target date")
    if core_row.task8_forecast_run_id != core_run.task8_forecast_run_id:
        raise ValueError("persisted forecast authority chain is inconsistent")
    if core_row.task9_harvest_state_run_id != core_run.task9_harvest_state_run_id:
        raise ValueError("persisted forecast authority chain is inconsistent")
    if core_row.task9_result_hash != core_run.task9_result_hash:
        raise ValueError("persisted forecast authority chain is inconsistent")


def validate_canonical_task9_replay_run(
    *,
    task9_run: HarvestStateRun,
    core_run: CoreForecastRunModel,
    forecast_cutoff_at: datetime,
) -> None:
    if task9_run.status != "completed":
        raise ValueError("forecast and Task 9 authorities must be completed")
    if task9_run.id != core_run.task9_harvest_state_run_id:
        raise ValueError("Task 9 authority is not bound to the core forecast run")
    if task9_run.result_hash != core_run.task9_result_hash:
        raise ValueError("persisted forecast authority chain is inconsistent")
    if task9_run.is_replay is not True:
        raise ValueError("Task 9 historical replay identity is incomplete or cutoff-drifted")
    if not _cutoff_matches(task9_run.forecast_effective_cutoff_at, forecast_cutoff_at):
        raise ValueError("Task 9 historical replay identity is incomplete or cutoff-drifted")
    if task9_run.replay_executed_at is None:
        raise ValueError("Task 9 historical replay identity is incomplete or cutoff-drifted")
    if not task9_run.replay_code_version:
        raise ValueError("Task 9 historical replay identity is incomplete or cutoff-drifted")
    if not task9_run.replay_run_correlation_id:
        raise ValueError("Task 9 historical replay identity is incomplete or cutoff-drifted")
    if task9_run.forecast_effective_cutoff_at is not None and _as_utc_aware(
        task9_run.forecast_effective_cutoff_at
    ) > _as_utc_aware(forecast_cutoff_at):
        raise ValueError("forecast authority is visible after the forecast cutoff")


def resolve_exact_task9_member(
    task9_authority: Task9AuthoritySource,
    *,
    core_row: CoreForecastDailyRowModel,
) -> Task9MemberSource:
    matching_members = tuple(
        member
        for member in task9_authority.member_rows
        if (
            member.state_date == core_row.date
            and member.forecast_quantile == core_row.forecast_quantile
            and member.farm_id == core_row.farm_id
            and member.subfarm_id == core_row.subfarm_id
            and member.variety_id == core_row.variety_id
            and member.destination_factory_id == core_row.destination_factory_id
        )
    )
    if not matching_members:
        raise ValueError("exact persisted Task 9 member authority is missing")
    if len(matching_members) != 1:
        raise ValueError("ambiguous persisted Task 9 member authority")
    return matching_members[0]


def validate_canonical_task10_model_and_prediction(
    *,
    prediction_run: ResidualModelPredictionRun,
    prediction_row: ResidualModelPredictionRow,
    training_run: ResidualModelTrainingRun,
    task9_run: HarvestStateRun,
    core_row: CoreForecastDailyRowModel | _Task10RowBinding,
    forecast_cutoff_at: datetime,
    target_date: date,
    horizon_days: int,
) -> str:
    if prediction_run.execution_status != "completed":
        raise ValueError("Task 10 authority is not exactly bound to Task 9")
    if prediction_run.task9_run_id != task9_run.id:
        raise ValueError("Task 10 authority is not exactly bound to Task 9")
    if prediction_run.task9_result_hash != task9_run.result_hash:
        raise ValueError("persisted forecast authority chain is inconsistent")
    if prediction_run.training_run_id is None:
        raise ValueError("Task 10 prediction does not bind an exact persisted model")
    if prediction_run.training_run_id != training_run.id:
        raise ValueError("Task 10 model authority is incomplete or identity-drifted")
    if training_run.execution_status != "completed":
        raise ValueError("Task 10 model authority is incomplete or identity-drifted")
    if training_run.eligibility_status != "eligible":
        raise ValueError("Task 10 model authority is incomplete or identity-drifted")
    if training_run.finished_at is None:
        raise ValueError("Task 10 model authority is incomplete or identity-drifted")
    if not _visible_at_or_before(training_run.finished_at, forecast_cutoff_at):
        raise ValueError("Task 10 model authority is visible after the forecast cutoff")
    training_signature = training_run.training_signature
    if training_signature != prediction_run.input_snapshot.get("training_signature"):
        raise ValueError("Task 10 model authority is incomplete or identity-drifted")
    if prediction_row.prediction_run_id != prediction_run.id:
        raise ValueError("exact persisted Task 10 prediction row authority is missing")
    if prediction_row.task9_run_id != task9_run.id:
        raise ValueError("persisted forecast authority chain is inconsistent")
    if prediction_row.task9_result_hash != task9_run.result_hash:
        raise ValueError("persisted forecast authority chain is inconsistent")
    if prediction_row.arrival_local_date != target_date:
        raise ValueError("exact persisted Task 10 prediction row authority is missing")
    if prediction_row.forecast_horizon_days != horizon_days:
        raise ValueError("exact persisted Task 10 prediction row authority is missing")
    if prediction_row.destination_factory_id != core_row.destination_factory_id:
        raise ValueError("exact persisted Task 10 prediction row authority is missing")
    return training_signature


def assert_candidate_forecast_authority_matches_resolution(
    *,
    forecast_authority: S2ForecastAuthorityBundle,
    resolution: CanonicalPersistedForecastAuthorityResolution,
) -> None:
    expected = build_canonical_s2_forecast_authority_bundle(resolution)
    assert_full_s2_forecast_authority_bundle_equivalence(forecast_authority, expected)


def validate_canonical_persisted_forecast_authority_resolution(
    resolution: CanonicalPersistedForecastAuthorityResolution,
    *,
    forecast_cutoff_at: datetime,
    target_date: date,
    horizon_days: int,
    forecast_authority: S2ForecastAuthorityBundle | None = None,
) -> None:
    validate_canonical_code_authority(
        code_authority=resolution.code_authority,
        core_run=resolution.core_run,
        forecast_cutoff_at=forecast_cutoff_at,
    )
    validate_canonical_core_forecast_chain(
        core_run=resolution.core_run,
        core_row=resolution.core_row,
        forecast_cutoff_at=forecast_cutoff_at,
        target_date=target_date,
    )
    validate_canonical_task9_replay_run(
        task9_run=resolution.task9_run,
        core_run=resolution.core_run,
        forecast_cutoff_at=forecast_cutoff_at,
    )
    validate_canonical_task10_model_and_prediction(
        prediction_run=resolution.prediction_run,
        prediction_row=resolution.prediction_row,
        training_run=resolution.training_run,
        task9_run=resolution.task9_run,
        core_row=resolution.core_row,
        forecast_cutoff_at=forecast_cutoff_at,
        target_date=target_date,
        horizon_days=horizon_days,
    )
    if forecast_authority is not None:
        assert_candidate_forecast_authority_matches_resolution(
            forecast_authority=forecast_authority,
            resolution=resolution,
        )


def _resolve_core_forecast_run_sync(
    session: Session,
    *,
    forecast_cutoff_at: datetime,
    task8_forecast_run_id: int,
) -> CoreForecastRunModel | None:
    core_runs = list(
        session.scalars(
            select(CoreForecastRunModel).where(
                CoreForecastRunModel.status == "completed",
                CoreForecastRunModel.task8_forecast_run_id == task8_forecast_run_id,
            )
        ).all()
    )
    core_runs = [
        run
        for run in core_runs
        if _cutoff_matches(run.forecast_effective_cutoff_at, forecast_cutoff_at)
        and _visible_at_or_before(run.completed_at, forecast_cutoff_at)
    ]
    if len(core_runs) != 1:
        return None
    core_run = core_runs[0]
    if (
        core_run.code_authority_id is None
        or core_run.code_authority_hash is None
        or core_run.forecast_effective_cutoff_at is None
    ):
        return None
    return core_run


def _resolve_exact_core_daily_row_sync(
    session: Session,
    *,
    core_run: CoreForecastRunModel,
    target_date: date,
    forecast_quantile: ForecastQuantile,
    farm_id: int,
    subfarm_id: int,
    variety_id: int,
) -> CoreForecastDailyRowModel | None:
    matching_rows = list(
        session.scalars(
            select(CoreForecastDailyRowModel).where(
                CoreForecastDailyRowModel.core_forecast_run_id == core_run.id,
                CoreForecastDailyRowModel.date == target_date,
                CoreForecastDailyRowModel.forecast_quantile == forecast_quantile,
                CoreForecastDailyRowModel.farm_id == farm_id,
                CoreForecastDailyRowModel.subfarm_id == subfarm_id,
                CoreForecastDailyRowModel.variety_id == variety_id,
                CoreForecastDailyRowModel.destination_factory_id == core_run.destination_factory_id,
            )
        ).all()
    )
    if len(matching_rows) != 1:
        return None
    return matching_rows[0]


def _resolve_exact_task9_member_row_sync(
    session: Session,
    *,
    task9_run_id: int,
    core_row: CoreForecastDailyRowModel,
) -> HarvestStateDailyMemberRowModel | None:
    matching_members = list(
        session.scalars(
            select(HarvestStateDailyMemberRowModel).where(
                HarvestStateDailyMemberRowModel.harvest_state_run_id == task9_run_id,
                HarvestStateDailyMemberRowModel.state_date == core_row.date,
                HarvestStateDailyMemberRowModel.forecast_quantile == core_row.forecast_quantile,
                HarvestStateDailyMemberRowModel.farm_id == core_row.farm_id,
                HarvestStateDailyMemberRowModel.subfarm_id == core_row.subfarm_id,
                HarvestStateDailyMemberRowModel.variety_id == core_row.variety_id,
                HarvestStateDailyMemberRowModel.destination_factory_id
                == core_row.destination_factory_id,
            )
        ).all()
    )
    if len(matching_members) != 1:
        return None
    return matching_members[0]


def resolve_canonical_persisted_forecast_authority_sync(
    session: Session,
    *,
    forecast_cutoff_at: datetime,
    task8_forecast_run_id: int,
    target_date: date,
    forecast_quantile: ForecastQuantile,
    horizon_days: int,
    farm_id: int,
    subfarm_id: int,
    variety_id: int,
) -> CanonicalPersistedForecastAuthorityResolution | None:
    """Resolve and validate one canonical persisted forecast authority binding."""
    core_run = _resolve_core_forecast_run_sync(
        session,
        forecast_cutoff_at=forecast_cutoff_at,
        task8_forecast_run_id=task8_forecast_run_id,
    )
    if core_run is None:
        return None
    core_row = _resolve_exact_core_daily_row_sync(
        session,
        core_run=core_run,
        target_date=target_date,
        forecast_quantile=forecast_quantile,
        farm_id=farm_id,
        subfarm_id=subfarm_id,
        variety_id=variety_id,
    )
    if core_row is None:
        return None
    code_authority = session.get(CoreForecastCodeAuthorityModel, core_run.code_authority_id)
    task9_run = session.get(HarvestStateRun, core_run.task9_harvest_state_run_id)
    if code_authority is None or task9_run is None:
        return None
    try:
        validate_canonical_code_authority(
            code_authority=code_authority,
            core_run=core_run,
            forecast_cutoff_at=forecast_cutoff_at,
        )
        validate_canonical_core_forecast_chain(
            core_run=core_run,
            core_row=core_row,
            forecast_cutoff_at=forecast_cutoff_at,
            target_date=target_date,
        )
        validate_canonical_task9_replay_run(
            task9_run=task9_run,
            core_run=core_run,
            forecast_cutoff_at=forecast_cutoff_at,
        )
    except ValueError:
        return None

    task9_authority = load_task9_authority_sync(session, task9_run.id)
    if task9_authority is None or task9_authority.status != "completed":
        return None
    try:
        task9_member_source = resolve_exact_task9_member(task9_authority, core_row=core_row)
    except ValueError:
        return None
    task9_member_row = _resolve_exact_task9_member_row_sync(
        session,
        task9_run_id=task9_run.id,
        core_row=core_row,
    )
    if task9_member_row is None:
        return None
    task9_member_hash = _task9_member_identity_hash(task9_member_source)
    if task9_member_hash != _task9_member_identity_hash(task9_member_row):
        return None

    prediction_runs = list(
        session.scalars(
            select(ResidualModelPredictionRun).where(
                ResidualModelPredictionRun.task9_run_id == task9_run.id,
                ResidualModelPredictionRun.execution_status == "completed",
                ResidualModelPredictionRun.completed_at.is_not(None),
                ResidualModelPredictionRun.completed_at <= forecast_cutoff_at,
            )
        ).all()
    )
    canonical_matches: list[
        tuple[ResidualModelPredictionRun, ResidualModelPredictionRow, ResidualModelTrainingRun]
    ] = []
    for prediction_run in prediction_runs:
        if prediction_run.training_run_id is None:
            continue
        training_run = session.get(ResidualModelTrainingRun, prediction_run.training_run_id)
        if training_run is None:
            continue
        prediction_rows = list(
            session.scalars(
                select(ResidualModelPredictionRow).where(
                    ResidualModelPredictionRow.prediction_run_id == prediction_run.id,
                    ResidualModelPredictionRow.arrival_local_date == target_date,
                    ResidualModelPredictionRow.forecast_horizon_days == horizon_days,
                    ResidualModelPredictionRow.destination_factory_id
                    == core_row.destination_factory_id,
                )
            ).all()
        )
        if len(prediction_rows) != 1:
            continue
        try:
            task10_model_identity_hash = validate_canonical_task10_model_and_prediction(
                prediction_run=prediction_run,
                prediction_row=prediction_rows[0],
                training_run=training_run,
                task9_run=task9_run,
                core_row=core_row,
                forecast_cutoff_at=forecast_cutoff_at,
                target_date=target_date,
                horizon_days=horizon_days,
            )
        except ValueError:
            continue
        canonical_matches.append((prediction_run, prediction_rows[0], training_run))
    if len(canonical_matches) != 1:
        return None
    prediction_run, prediction_row, training_run = canonical_matches[0]
    task10_model_identity_hash = validate_canonical_task10_model_and_prediction(
        prediction_run=prediction_run,
        prediction_row=prediction_row,
        training_run=training_run,
        task9_run=task9_run,
        core_row=core_row,
        forecast_cutoff_at=forecast_cutoff_at,
        target_date=target_date,
        horizon_days=horizon_days,
    )
    return CanonicalPersistedForecastAuthorityResolution(
        core_run=core_run,
        core_row=core_row,
        code_authority=code_authority,
        task9_run=task9_run,
        task9_member=task9_member_row,
        task9_member_identity_hash=task9_member_hash,
        prediction_run=prediction_run,
        prediction_row=prediction_row,
        training_run=training_run,
        task10_model_identity_hash=task10_model_identity_hash,
    )


def resolve_exact_task10_prediction_sync(
    session: Session,
    *,
    task9_run_id: int,
    forecast_cutoff_at: datetime,
    target_date: date,
    horizon_days: int,
    destination_factory_id: int,
) -> tuple[ResidualModelPredictionRun, ResidualModelPredictionRow, ResidualModelTrainingRun] | None:
    """Resolve exactly one canonical Task 10 prediction binding or fail closed."""
    task9_run = session.get(HarvestStateRun, task9_run_id)
    if task9_run is None:
        return None
    prediction_runs = list(
        session.scalars(
            select(ResidualModelPredictionRun).where(
                ResidualModelPredictionRun.task9_run_id == task9_run_id,
                ResidualModelPredictionRun.execution_status == "completed",
                ResidualModelPredictionRun.completed_at.is_not(None),
                ResidualModelPredictionRun.completed_at <= forecast_cutoff_at,
            )
        ).all()
    )
    canonical_matches: list[
        tuple[ResidualModelPredictionRun, ResidualModelPredictionRow, ResidualModelTrainingRun]
    ] = []
    for prediction_run in prediction_runs:
        if prediction_run.training_run_id is None:
            continue
        training_run = session.get(ResidualModelTrainingRun, prediction_run.training_run_id)
        if training_run is None:
            continue
        prediction_rows = list(
            session.scalars(
                select(ResidualModelPredictionRow).where(
                    ResidualModelPredictionRow.prediction_run_id == prediction_run.id,
                    ResidualModelPredictionRow.arrival_local_date == target_date,
                    ResidualModelPredictionRow.forecast_horizon_days == horizon_days,
                    ResidualModelPredictionRow.destination_factory_id == destination_factory_id,
                )
            ).all()
        )
        if len(prediction_rows) != 1:
            continue
        try:
            validate_canonical_task10_model_and_prediction(
                prediction_run=prediction_run,
                prediction_row=prediction_rows[0],
                training_run=training_run,
                task9_run=task9_run,
                core_row=_Task10RowBinding(destination_factory_id=destination_factory_id),
                forecast_cutoff_at=forecast_cutoff_at,
                target_date=target_date,
                horizon_days=horizon_days,
            )
        except ValueError:
            continue
        canonical_matches.append((prediction_run, prediction_rows[0], training_run))
    if len(canonical_matches) != 1:
        return None
    return canonical_matches[0]


async def validate_canonical_persisted_forecast_authority_for_candidate(
    session: AsyncSession,
    *,
    forecast_cutoff_at: datetime,
    target_date: date,
    horizon_days: int,
    forecast_authority: S2ForecastAuthorityBundle,
    core_forecast_run_id: int,
    core_forecast_daily_row_id: int,
    task9_run_id: int,
    task10_prediction_run_id: int,
) -> CanonicalPersistedForecastAuthorityResolution:
    """Validate a candidate forecast authority against canonical persisted semantics."""
    from backend.app.core_forecast.persistence import CoreForecastRunRepository
    from backend.app.core_forecast.repository import SqlAlchemyCoreForecastRepository
    from backend.app.harvest_state.persistence import load_harvest_state_output_by_id
    from backend.app.residual_model.persistence import (
        load_residual_prediction_run_by_id,
        load_residual_training_run_by_id,
    )
    from backend.app.rolling_backtest.enums import Task10ModelPolicy
    from backend.app.rolling_backtest.orchestration import (
        ResolvedInputOutcome,
        _PinnedTask10PredictionInput,
    )
    from backend.app.rolling_backtest.replay_pipeline import ReplayPipelineOutcome
    from backend.app.rolling_backtest.replay_task10_binding import (
        build_replay_task9_binding_context,
        evaluate_replay_task10_binding,
    )
    from backend.app.rolling_backtest.schemas import PersistentUpstreamReference

    core_run = await session.get(CoreForecastRunModel, core_forecast_run_id)
    core_row = await session.get(CoreForecastDailyRowModel, core_forecast_daily_row_id)
    task9 = await session.get(HarvestStateRun, task9_run_id)
    if core_run is None or core_row is None or task9 is None:
        raise ValueError("required persisted S2 authority is missing")

    core_persistence = CoreForecastRunRepository(session)
    persisted_core_run = await core_persistence.load_complete_run(core_forecast_run_id)
    if persisted_core_run is None:
        raise ValueError("required persisted core forecast authority is missing")
    code_authority = persisted_core_run.code_authority
    if code_authority is None:
        raise ValueError("legacy core forecast run has no persisted historical code authority")
    validate_canonical_code_authority(
        code_authority=code_authority,
        core_run=core_run,
        forecast_cutoff_at=forecast_cutoff_at,
    )
    matching_core_rows = tuple(
        row for row in persisted_core_run.daily_curve.rows if row.row_hash == core_row.row_hash
    )
    if (
        persisted_core_run.run.run_id != core_run.id
        or persisted_core_run.run.result_hash != core_run.result_hash
        or len(matching_core_rows) != 1
    ):
        raise ValueError("core forecast run/daily row failed canonical persisted-authority binding")
    validate_canonical_core_forecast_chain(
        core_run=core_run,
        core_row=core_row,
        forecast_cutoff_at=forecast_cutoff_at,
        target_date=target_date,
    )

    repository = SqlAlchemyCoreForecastRepository(session)
    task9_authority = await repository.load_task9_authority(task9_run_id)
    task9_output = await load_harvest_state_output_by_id(session, run_id=task9_run_id)
    if task9_authority is None or task9_output is None:
        raise ValueError("required persisted Task 9 authority is missing")
    task9_member_source = resolve_exact_task9_member(task9_authority, core_row=core_row)
    matching_loaded_members = tuple(
        member
        for member in getattr(task9_output, "daily_member_state_rows", ())
        if (
            member.state_date == core_row.date
            and member.forecast_quantile == core_row.forecast_quantile
            and member.farm_id == core_row.farm_id
            and member.subfarm_id == core_row.subfarm_id
            and member.variety_id == core_row.variety_id
            and member.destination_factory_id == core_row.destination_factory_id
        )
    )
    if len(matching_loaded_members) != 1:
        raise ValueError("dedicated Task 9 integrity loader did not resolve one exact member")
    task9_member_hash = _task9_member_identity_hash(task9_member_source)
    if task9_member_hash != _task9_member_identity_hash(matching_loaded_members[0]):
        raise ValueError("Task 9 repository member does not match integrity-loaded member")
    validate_canonical_task9_replay_run(
        task9_run=task9,
        core_run=core_run,
        forecast_cutoff_at=forecast_cutoff_at,
    )

    task10_output = await load_residual_prediction_run_by_id(
        session,
        run_id=task10_prediction_run_id,
    )
    if task10_output is None:
        raise ValueError("required persisted Task 10 prediction authority is missing")
    if task10_output.model_run_id is None:
        raise ValueError("Task 10 prediction does not bind an exact persisted model")
    task10_training_output = await load_residual_training_run_by_id(
        session,
        run_id=task10_output.model_run_id,
    )
    task10_training_row = await session.get(ResidualModelTrainingRun, task10_output.model_run_id)
    if task10_training_output is None or task10_training_row is None:
        raise ValueError("required persisted Task 10 model authority is missing")
    if task10_training_output.training_signature != task10_training_row.training_signature:
        raise ValueError("Task 10 model authority is incomplete or identity-drifted")

    replay_outcome = ReplayPipelineOutcome(
        task9_run_id=task9.id,
        audit_row_count=task9.member_row_count,
        replay_executed_at=cast(datetime, task9.replay_executed_at),
        replay_correlation_id=cast(str, task9.replay_run_correlation_id),
        code_version=cast(str, task9.replay_code_version),
    )
    task9_binding = await build_replay_task9_binding_context(
        session,
        replay_outcome=replay_outcome,
    )
    pinned_prediction = cast(
        ResolvedInputOutcome,
        _PinnedTask10PredictionInput(
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=task10_prediction_run_id,
            )
        ),
    )
    task10_binding = await evaluate_replay_task10_binding(
        session,
        binding_context=task9_binding,
        prediction_input=pinned_prediction,
        requested_policy=Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL,
    )
    if task10_binding is None or task10_binding.prediction_run_id != task10_prediction_run_id:
        raise ValueError("Task 10 replay binding did not resolve the exact prediction run")

    matching_predictions = tuple(
        row
        for row in task10_output.rows
        if (
            row.arrival_local_date == target_date
            and row.forecast_horizon_days == horizon_days
            and row.destination_factory_id == core_row.destination_factory_id
        )
    )
    if not matching_predictions:
        raise ValueError("exact persisted Task 10 prediction row authority is missing")
    if len(matching_predictions) != 1:
        raise ValueError("ambiguous persisted Task 10 prediction row authority")
    task10_prediction_row_output = matching_predictions[0]
    prediction_run = await session.get(ResidualModelPredictionRun, task10_prediction_run_id)
    if prediction_run is None:
        raise ValueError("required persisted Task 10 prediction authority is missing")
    prediction_rows = list(
        await session.scalars(
            select(ResidualModelPredictionRow).where(
                ResidualModelPredictionRow.prediction_run_id == task10_prediction_run_id,
                ResidualModelPredictionRow.arrival_local_date == target_date,
                ResidualModelPredictionRow.forecast_horizon_days == horizon_days,
                ResidualModelPredictionRow.destination_factory_id
                == core_row.destination_factory_id,
                ResidualModelPredictionRow.prediction_row_hash
                == task10_prediction_row_output.prediction_hash,
            )
        )
    )
    if len(prediction_rows) != 1:
        raise ValueError("exact persisted Task 10 prediction row authority is missing")
    task10_model_identity_hash = validate_canonical_task10_model_and_prediction(
        prediction_run=prediction_run,
        prediction_row=prediction_rows[0],
        training_run=task10_training_row,
        task9_run=task9,
        core_row=core_row,
        forecast_cutoff_at=forecast_cutoff_at,
        target_date=target_date,
        horizon_days=horizon_days,
    )

    task9_member_rows = list(
        await session.scalars(
            select(HarvestStateDailyMemberRowModel).where(
                HarvestStateDailyMemberRowModel.harvest_state_run_id == task9.id,
                HarvestStateDailyMemberRowModel.state_date == core_row.date,
                HarvestStateDailyMemberRowModel.forecast_quantile == core_row.forecast_quantile,
                HarvestStateDailyMemberRowModel.farm_id == core_row.farm_id,
                HarvestStateDailyMemberRowModel.subfarm_id == core_row.subfarm_id,
                HarvestStateDailyMemberRowModel.variety_id == core_row.variety_id,
                HarvestStateDailyMemberRowModel.destination_factory_id
                == core_row.destination_factory_id,
            )
        )
    )
    if len(task9_member_rows) != 1:
        raise ValueError("exact persisted Task 9 member authority is missing")

    code_authority_model = await session.get(
        CoreForecastCodeAuthorityModel,
        core_run.code_authority_id,
    )
    if code_authority_model is None:
        raise ValueError("legacy core forecast run has no persisted historical code authority")

    resolution = CanonicalPersistedForecastAuthorityResolution(
        core_run=core_run,
        core_row=core_row,
        code_authority=code_authority_model,
        task9_run=task9,
        task9_member=task9_member_rows[0],
        task9_member_identity_hash=task9_member_hash,
        prediction_run=prediction_run,
        prediction_row=prediction_rows[0],
        training_run=task10_training_row,
        task10_model_identity_hash=task10_model_identity_hash,
    )
    validate_canonical_persisted_forecast_authority_resolution(
        resolution,
        forecast_cutoff_at=forecast_cutoff_at,
        target_date=target_date,
        horizon_days=horizon_days,
        forecast_authority=forecast_authority,
    )
    return resolution
