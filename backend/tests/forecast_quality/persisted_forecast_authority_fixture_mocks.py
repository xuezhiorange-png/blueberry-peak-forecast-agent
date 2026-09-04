"""Monkeypatched integrity loaders for authority fixture async tests."""

from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import make_transient, object_session

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
from backend.tests.forecast_quality.authority_loader_fixture import (
    CODE_AUTHORITY_ID,
    CORE_RUN_ID,
    CUTOFF_AT,
    HASH_0,
    HASH_3,
    HASH_A,
    HASH_C,
    HASH_D,
    PREDICTION_RUN_ID,
    TASK9_RUN_ID,
    TRAINING_RUN_ID,
    seed_canonical_authority_fixture,
)

AUTHORITY_FIXTURE_TABLES = (
    CoreForecastCodeAuthorityModel.__table__,
    CoreForecastRunModel.__table__,
    CoreForecastDailyRowModel.__table__,
    HarvestStateRun.__table__,
    HarvestStateDailyMemberRowModel.__table__,
    ResidualModelTrainingRun.__table__,
    ResidualModelPredictionRun.__table__,
    ResidualModelPredictionRow.__table__,
)


def create_authority_fixture_async_engine() -> AsyncEngine:
    return create_async_engine("sqlite+aiosqlite:///:memory:")


def _create_authority_fixture_tables_sync(connection) -> None:
    for table in AUTHORITY_FIXTURE_TABLES:
        table.create(connection, checkfirst=True)


async def ensure_authority_fixture_tables(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(_create_authority_fixture_tables_sync)


def all_fixture_rows_from_sync_session(
    sync_session,
    *,
    fixture: dict[str, object] | None = None,
) -> tuple[object, ...]:
    if fixture is None:
        return tuple(sync_session.identity_map.values())
    rows: list[object] = [
        sync_session.get(CoreForecastCodeAuthorityModel, CODE_AUTHORITY_ID),
        sync_session.get(CoreForecastRunModel, CORE_RUN_ID),
        sync_session.get(HarvestStateRun, TASK9_RUN_ID),
        sync_session.get(ResidualModelTrainingRun, TRAINING_RUN_ID),
        sync_session.get(ResidualModelPredictionRun, PREDICTION_RUN_ID),
    ]
    for key in (
        "core_row_p50_a",
        "core_row_p80_a",
        "core_row_p50_b",
        "member_p50_a",
        "member_p80_a",
        "member_p50_b",
        "pred_row_h7_a",
        "pred_row_h14_b",
    ):
        rows.append(fixture[key])
    explicit_rows = tuple(row for row in rows if row is not None)
    merged: dict[tuple[type[object], object], object] = {}
    for row in (*explicit_rows, *sync_session.identity_map.values()):
        merged[(type(row), getattr(row, "id", id(row)))] = row
    return tuple(merged.values())


async def copy_fixture_rows_to_async_session(
    sync_session,
    async_session,
    *,
    fixture: dict[str, object] | None = None,
) -> None:
    for row in all_fixture_rows_from_sync_session(sync_session, fixture=fixture):
        if object_session(row) is sync_session:
            sync_session.expunge(row)
        make_transient(row)
        async_session.add(row)
    await async_session.commit()


def install_authority_fixture_mock_loaders(
    monkeypatch,
    *,
    session_rows: dict[tuple[str, int], object],
    core_row: object,
    task9_member: object,
    prediction_row: object,
    training_finished_at: object = CUTOFF_AT,
    replay_binding_prediction_run_id: int = PREDICTION_RUN_ID,
) -> None:
    code_authority = SimpleNamespace(
        authority_id=CODE_AUTHORITY_ID,
        authority_hash=HASH_3,
        source_commit_sha="a" * 40,
        build_artifact_hash=HASH_0,
        config_bundle_hash=HASH_0,
        available_at=CUTOFF_AT,
    )
    core_run = session_rows.get(("CoreForecastRunModel", CORE_RUN_ID))
    task9 = session_rows.get(("HarvestStateRun", TASK9_RUN_ID))
    task9_member_source = Task9MemberSource(
        state_date=task9_member.state_date,
        forecast_quantile=task9_member.forecast_quantile,
        farm_id=task9_member.farm_id,
        subfarm_id=task9_member.subfarm_id,
        variety_id=task9_member.variety_id,
        destination_factory_id=task9_member.destination_factory_id,
        natural_maturity_supply_kg=task9_member.natural_maturity_supply_kg,
        opening_mature_inventory_kg=task9_member.opening_mature_inventory_kg,
        available_mature_quantity_kg=task9_member.available_mature_quantity_kg,
        mature_inventory_loss_quantity_kg=task9_member.mature_inventory_loss_quantity_kg,
        harvestable_mature_quantity_kg=task9_member.harvestable_mature_quantity_kg,
        allocated_harvest_capacity_kg=task9_member.allocated_harvest_capacity_kg,
        harvested_quantity_kg=task9_member.harvested_quantity_kg,
        closing_mature_inventory_kg=task9_member.closing_mature_inventory_kg,
        unharvested_backlog_kg=task9_member.unharvested_backlog_kg,
    )
    task9_authority = Task9AuthoritySource(
        run_id=TASK9_RUN_ID,
        status="completed",
        forecast_start_date=task9.forecast_start_date,
        forecast_end_date=task9.forecast_end_date,
        destination_factory_id=task9.destination_factory_id,
        forecast_season_id=task9.forecast_season_id,
        maturity_forecast_run_id=task9.maturity_forecast_run_id,
        maturity_model_artifact_hash=task9.maturity_model_artifact_hash,
        result_hash=HASH_C,
        member_rows=(task9_member_source,),
        forecast_effective_cutoff_at=CUTOFF_AT,
    )
    task10_output = SimpleNamespace(
        model_run_id=TRAINING_RUN_ID,
        prediction_hash=HASH_D,
        prediction_input_signature=HASH_0,
        input_snapshot={"training_signature": HASH_0},
        execution_status="completed",
        task9_run_id=TASK9_RUN_ID,
        task9_result_hash=HASH_C,
        rows=(
            SimpleNamespace(
                arrival_local_date=prediction_row.arrival_local_date,
                forecast_horizon_days=prediction_row.forecast_horizon_days,
                destination_factory_id=prediction_row.destination_factory_id,
                prediction_hash=prediction_row.prediction_row_hash,
                task9_run_id=TASK9_RUN_ID,
                task9_result_hash=HASH_C,
            ),
        ),
    )

    class _Repository:
        def __init__(self, _session: object) -> None:
            pass

        async def load_task9_authority(self, run_id: int) -> Task9AuthoritySource | None:
            return task9_authority if run_id == TASK9_RUN_ID else None

    class _CorePersistence:
        def __init__(self, _session: object) -> None:
            pass

        async def load_complete_run(self, run_id: int) -> object | None:
            if run_id != CORE_RUN_ID or core_run is None:
                return None
            return SimpleNamespace(
                run=SimpleNamespace(run_id=CORE_RUN_ID, result_hash=HASH_A),
                daily_curve=SimpleNamespace(rows=(SimpleNamespace(row_hash=core_row.row_hash),)),
                code_authority=code_authority,
            )

    async def _load_task9(_session: object, *, run_id: int) -> object | None:
        if run_id != TASK9_RUN_ID:
            return None
        return SimpleNamespace(
            result_hash=HASH_C,
            status="completed",
            daily_member_state_rows=(task9_member,),
        )

    async def _load_task10(_session: object, *, run_id: int) -> object | None:
        return task10_output if run_id == PREDICTION_RUN_ID else None

    async def _load_task10_training(_session: object, *, run_id: int) -> object | None:
        return SimpleNamespace(training_signature=HASH_0) if run_id == TRAINING_RUN_ID else None

    async def _build_task9_binding(_session: object, *, replay_outcome: object) -> object:
        return SimpleNamespace(
            task9_run_id=TASK9_RUN_ID,
            task9_result_hash=HASH_C,
            replay_outcome=replay_outcome,
        )

    async def _evaluate_task10(
        _session: object,
        *,
        binding_context: object,
        prediction_input: object,
        requested_policy: object,
    ) -> object:
        return SimpleNamespace(
            prediction_run_id=replay_binding_prediction_run_id,
            binding_context=binding_context,
            prediction_input=prediction_input,
            requested_policy=requested_policy,
        )

    monkeypatch.setattr(
        "backend.app.core_forecast.repository.SqlAlchemyCoreForecastRepository",
        _Repository,
    )
    monkeypatch.setattr(
        "backend.app.core_forecast.persistence.CoreForecastRunRepository",
        _CorePersistence,
    )
    monkeypatch.setattr(
        "backend.app.harvest_state.persistence.load_harvest_state_output_by_id",
        _load_task9,
    )
    monkeypatch.setattr(
        "backend.app.residual_model.persistence.load_residual_prediction_run_by_id",
        _load_task10,
    )
    monkeypatch.setattr(
        "backend.app.residual_model.persistence.load_residual_training_run_by_id",
        _load_task10_training,
    )
    monkeypatch.setattr(
        "backend.app.rolling_backtest.replay_task10_binding.build_replay_task9_binding_context",
        _build_task9_binding,
    )
    monkeypatch.setattr(
        "backend.app.rolling_backtest.replay_task10_binding.evaluate_replay_task10_binding",
        _evaluate_task10,
    )


def session_rows_from_sync_fixture(
    sync_session,
    *,
    fixture: dict[str, object] | None = None,
) -> dict[tuple[str, int], object]:
    if fixture is None:
        fixture = seed_canonical_authority_fixture(sync_session)
    core_row = fixture["core_row_p50_a"]
    return {
        ("CoreForecastRunModel", CORE_RUN_ID): sync_session.get(CoreForecastRunModel, CORE_RUN_ID),
        ("CoreForecastDailyRowModel", core_row.id): core_row,
        ("HarvestStateRun", TASK9_RUN_ID): sync_session.get(HarvestStateRun, TASK9_RUN_ID),
        ("CoreForecastCodeAuthorityModel", CODE_AUTHORITY_ID): sync_session.get(
            CoreForecastCodeAuthorityModel, CODE_AUTHORITY_ID
        ),
        ("ResidualModelPredictionRun", PREDICTION_RUN_ID): sync_session.get(
            ResidualModelPredictionRun, PREDICTION_RUN_ID
        ),
        ("ResidualModelTrainingRun", TRAINING_RUN_ID): sync_session.get(
            ResidualModelTrainingRun, TRAINING_RUN_ID
        ),
    }
