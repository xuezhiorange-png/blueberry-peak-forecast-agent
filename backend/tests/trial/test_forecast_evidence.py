from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.actual_harvest_import.models import ActualHarvestImportBatchModel
from backend.app.models.core_forecast import CoreForecastRunModel
from backend.app.models.trial import TrialForecastEvidenceModel, TrialResourceBindingModel
from backend.app.repositories.trial_forecast_evidence import (
    TrialForecastEvidenceConflictError,
    TrialForecastEvidenceInputError,
    TrialForecastEvidenceIntegrityError,
    TrialForecastEvidenceNotFoundError,
    authorize_and_load_forecast_evidence,
    canonical_trial_forecast_evidence_payload,
    compute_trial_business_scope_hash,
    compute_trial_forecast_evidence_hash,
    create_forecast_evidence_and_binding_in_result_boundary,
    load_forecast_evidence_by_public_id,
)

FORECAST_ID = "a" * 64
AUTHORITY_HASH = "b" * 64
PLAN_HASH = "c" * 64
CORE_RESULT_HASH = "d" * 64
CORE_INPUT_HASH = "e" * 64
CORE_POLICY_HASH = "f" * 64
CORE_CURVE_HASH = "1" * 64
CORE_METRICS_HASH = "2" * 64
CORE_TASK8_HASH = "3" * 64
CORE_TASK9_HASH = "4" * 64
OWNER = "actor:one"
OTHER_OWNER = "actor:two"
NOW = datetime(2026, 7, 31, 8, 0, tzinfo=UTC)


@pytest.fixture
async def sqlite_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(ActualHarvestImportBatchModel.__table__.create)
        await connection.run_sync(CoreForecastRunModel.__table__.create)
        await connection.run_sync(TrialResourceBindingModel.__table__.create)
        await connection.run_sync(TrialForecastEvidenceModel.__table__.create)
    session = AsyncSession(engine, expire_on_commit=False)
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


def _core_run(*, public_forecast_id: str = FORECAST_ID) -> CoreForecastRunModel:
    return CoreForecastRunModel(
        status="completed",
        run_schema_version="v0.1-core-forecast-run-v1",
        request_schema_version="v0.1-core-forecast-request-v1",
        date_basis="HARVEST_BUSINESS_DATE",
        forecast_input_hash=CORE_INPUT_HASH,
        request_hash=public_forecast_id,
        result_hash=CORE_RESULT_HASH,
        retention_policy_snapshot_hash=CORE_POLICY_HASH,
        curve_hash=CORE_CURVE_HASH,
        metrics_hash=CORE_METRICS_HASH,
        code_authority_id=None,
        code_authority_hash=None,
        code_authority_available_at=None,
        forecast_effective_cutoff_at=None,
        request_snapshot={},
        forecast_season_id=1,
        forecast_season_code="season-2026",
        forecast_start_date=NOW.date(),
        forecast_end_date=NOW.date(),
        destination_factory_id=1,
        task8_forecast_run_id=1,
        task8_artifact_hash=CORE_TASK8_HASH,
        task9_harvest_state_run_id=1,
        task9_result_hash=CORE_TASK9_HASH,
        rerun_of_run_id=None,
        daily_row_count=1,
        metric_row_count=3,
        created_at=NOW,
        completed_at=NOW,
    )


def _evidence_kwargs(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "public_forecast_id": FORECAST_ID,
        "owner_identity": OWNER,
        "forecast_input_authority_hash": AUTHORITY_HASH,
        "authority_available_at": NOW,
        "farm_business_key": "farm-1",
        "subfarm_business_key_or_null": "subfarm-1",
        "season_business_key": "season-2026",
        "variety_business_key": "variety-blue",
        "destination_factory_business_key": "factory-main",
        "plan_version": "plan-v1",
        "plan_row_hash": PLAN_HASH,
        "planting_area_mu": Decimal("12.340000"),
    }
    values.update(overrides)
    return values


async def _seed_core(session: AsyncSession) -> None:
    session.add(_core_run())
    await session.flush()


async def _create_evidence(session: AsyncSession, **overrides: object):
    return await create_forecast_evidence_and_binding_in_result_boundary(
        session,
        **_evidence_kwargs(**overrides),
    )


def test_business_scope_hash_is_pure_and_stable() -> None:
    kwargs = {
        "farm_business_key": "farm-1",
        "subfarm_business_key_or_null": "subfarm-1",
        "season_business_key": "season-2026",
        "variety_business_key": "variety-blue",
        "destination_factory_business_key": "factory-main",
    }
    scope_hash = compute_trial_business_scope_hash(**kwargs)
    assert scope_hash == compute_trial_business_scope_hash(**kwargs)
    assert scope_hash != compute_trial_business_scope_hash(
        **{**kwargs, "farm_business_key": "farm-2"}
    )
    assert scope_hash != compute_trial_business_scope_hash(
        **{**kwargs, "subfarm_business_key_or_null": None}
    )


def test_evidence_hash_excludes_owner_and_binds_public_forecast() -> None:
    kwargs = _evidence_kwargs()
    kwargs.pop("owner_identity")
    first = compute_trial_forecast_evidence_hash(**kwargs)
    second = compute_trial_forecast_evidence_hash(
        **{**kwargs, "authority_available_at": datetime(2026, 8, 1, tzinfo=UTC)}
    )
    other_forecast = compute_trial_forecast_evidence_hash(
        **{**kwargs, "public_forecast_id": "5" * 64}
    )
    assert first != second
    assert first != other_forecast
    assert canonical_trial_forecast_evidence_payload(**kwargs)["public_forecast_id"] == FORECAST_ID


@pytest.mark.parametrize(
    "overrides",
    [
        {"planting_area_mu": 12.34},
        {"authority_available_at": datetime(2026, 7, 31, 8, 0)},
        {"plan_row_hash": "A" * 64},
        {"planting_area_mu": Decimal("1.0000001")},
    ],
)
def test_evidence_rejects_non_canonical_inputs(overrides: dict[str, object]) -> None:
    kwargs = _evidence_kwargs()
    kwargs.pop("owner_identity")
    kwargs.update(overrides)
    with pytest.raises(TrialForecastEvidenceInputError):
        compute_trial_forecast_evidence_hash(**kwargs)


async def test_create_exact_replay_and_conflict_are_immutable(
    sqlite_session: AsyncSession,
) -> None:
    await _seed_core(sqlite_session)
    first = await _create_evidence(sqlite_session)
    replay = await _create_evidence(sqlite_session)
    assert replay == first
    assert (
        await sqlite_session.scalar(select(func.count()).select_from(TrialForecastEvidenceModel))
    ) == 1
    assert (
        await sqlite_session.scalar(select(func.count()).select_from(TrialResourceBindingModel))
    ) == 1
    with pytest.raises(TrialForecastEvidenceConflictError):
        await _create_evidence(sqlite_session, owner_identity=OTHER_OWNER)
    with pytest.raises(TrialForecastEvidenceConflictError):
        await _create_evidence(sqlite_session, plan_row_hash="5" * 64)


async def test_create_requires_core_request_and_rolls_back_with_caller(
    sqlite_session: AsyncSession,
) -> None:
    with pytest.raises(TrialForecastEvidenceNotFoundError):
        await _create_evidence(sqlite_session)
    await _seed_core(sqlite_session)
    await _create_evidence(sqlite_session)
    await sqlite_session.rollback()
    assert (
        await sqlite_session.scalar(select(func.count()).select_from(CoreForecastRunModel))
    ) == 0
    assert (
        await sqlite_session.scalar(select(func.count()).select_from(TrialForecastEvidenceModel))
    ) == 0
    assert (
        await sqlite_session.scalar(select(func.count()).select_from(TrialResourceBindingModel))
    ) == 0


async def test_authorized_readback_is_persisted_and_wrong_owner_is_concealed(
    sqlite_session: AsyncSession,
) -> None:
    await _seed_core(sqlite_session)
    created = await _create_evidence(sqlite_session)
    loaded = await authorize_and_load_forecast_evidence(
        sqlite_session,
        public_forecast_id=FORECAST_ID,
        owner_identity=OWNER,
    )
    assert loaded == created
    with pytest.raises(TrialForecastEvidenceNotFoundError):
        await authorize_and_load_forecast_evidence(
            sqlite_session,
            public_forecast_id=FORECAST_ID,
            owner_identity=OTHER_OWNER,
        )
    assert loaded.subfarm_business_key_or_null == "subfarm-1"
    assert loaded.planting_area_mu == Decimal("12.340000")


async def test_null_subfarm_round_trips_without_guessing(
    sqlite_session: AsyncSession,
) -> None:
    await _seed_core(sqlite_session)
    evidence = await _create_evidence(sqlite_session, subfarm_business_key_or_null=None)
    loaded = await load_forecast_evidence_by_public_id(
        sqlite_session,
        public_forecast_id=FORECAST_ID,
    )
    assert loaded == evidence
    assert loaded.subfarm_business_key_or_null is None


async def test_half_state_and_persisted_drift_fail_closed(
    sqlite_session: AsyncSession,
) -> None:
    await _seed_core(sqlite_session)
    await _create_evidence(sqlite_session)
    binding = await sqlite_session.scalar(select(TrialResourceBindingModel))
    assert binding is not None
    await sqlite_session.delete(binding)
    await sqlite_session.flush()
    with pytest.raises(TrialForecastEvidenceIntegrityError):
        await _create_evidence(sqlite_session)

    await sqlite_session.rollback()
    sqlite_session.expunge_all()
    await _seed_core(sqlite_session)
    await _create_evidence(sqlite_session)
    evidence_row = await sqlite_session.scalar(select(TrialForecastEvidenceModel))
    assert evidence_row is not None
    await sqlite_session.delete(evidence_row)
    await sqlite_session.flush()
    with pytest.raises(TrialForecastEvidenceIntegrityError):
        await authorize_and_load_forecast_evidence(
            sqlite_session,
            public_forecast_id=FORECAST_ID,
            owner_identity=OWNER,
        )

    await sqlite_session.rollback()
    sqlite_session.expunge_all()
    await _seed_core(sqlite_session)
    await _create_evidence(sqlite_session)
    row = await sqlite_session.scalar(select(TrialForecastEvidenceModel))
    assert row is not None
    row.canonical_payload = {**row.canonical_payload, "plan_version": "tampered"}
    with pytest.raises(TrialForecastEvidenceIntegrityError):
        await load_forecast_evidence_by_public_id(
            sqlite_session,
            public_forecast_id=FORECAST_ID,
        )


def test_sqlite_migration_installs_immutable_guards_and_round_trips() -> None:
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "0027_s5_a2_forecast_evidence_persistence.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0027", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        CoreForecastRunModel.__table__.create(connection)
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        core = _core_run()
        connection.execute(
            CoreForecastRunModel.__table__.insert().values(
                {
                    column.name: getattr(core, column.name)
                    for column in CoreForecastRunModel.__table__.columns
                    if column.name != "id"
                }
            )
        )
        payload = canonical_trial_forecast_evidence_payload(
            public_forecast_id=FORECAST_ID,
            forecast_input_authority_hash=AUTHORITY_HASH,
            authority_available_at=NOW,
            farm_business_key="farm-1",
            subfarm_business_key_or_null="subfarm-1",
            season_business_key="season-2026",
            variety_business_key="variety-blue",
            destination_factory_business_key="factory-main",
            plan_version="plan-v1",
            plan_row_hash=PLAN_HASH,
            planting_area_mu=Decimal("12.340000"),
        )
        connection.execute(
            text(
                "INSERT INTO trial_forecast_evidence ("
                "evidence_schema_version, public_forecast_id, "
                "forecast_input_authority_hash, authority_available_at, "
                "farm_business_key, subfarm_business_key_or_null, season_business_key, "
                "variety_business_key, destination_factory_business_key, plan_version, "
                "plan_row_hash, planting_area_mu, business_scope_hash, canonical_payload, "
                "forecast_evidence_hash, created_at"
                ") VALUES (:schema_version, :public_id, :authority_hash, :available_at, "
                ":farm, :subfarm, :season, :variety, :factory, :plan_version, "
                ":plan_hash, :area, :scope_hash, :payload, :evidence_hash, :created_at)"
            ),
            {
                "schema_version": "v0.2-trial-forecast-evidence-v1",
                "public_id": FORECAST_ID,
                "authority_hash": AUTHORITY_HASH,
                "available_at": NOW,
                "farm": "farm-1",
                "subfarm": "subfarm-1",
                "season": "season-2026",
                "variety": "variety-blue",
                "factory": "factory-main",
                "plan_version": "plan-v1",
                "plan_hash": PLAN_HASH,
                "area": "12.340000",
                "scope_hash": payload["business_scope_hash"],
                "payload": json.dumps(payload, separators=(",", ":")),
                "evidence_hash": compute_trial_forecast_evidence_hash(
                    public_forecast_id=FORECAST_ID,
                    forecast_input_authority_hash=AUTHORITY_HASH,
                    authority_available_at=NOW,
                    farm_business_key="farm-1",
                    subfarm_business_key_or_null="subfarm-1",
                    season_business_key="season-2026",
                    variety_business_key="variety-blue",
                    destination_factory_business_key="factory-main",
                    plan_version="plan-v1",
                    plan_row_hash=PLAN_HASH,
                    planting_area_mu=Decimal("12.340000"),
                ),
                "created_at": NOW,
            },
        )
        for statement in (
            "UPDATE trial_forecast_evidence SET plan_version = 'tampered'",
            "DELETE FROM trial_forecast_evidence",
        ):
            with pytest.raises(DBAPIError, match="trial forecast evidence is immutable"):
                connection.execute(text(statement))
        assert inspect(connection).has_table("trial_forecast_evidence")
        migration.downgrade()
        assert inspect(connection).has_table("core_forecast_run")
        assert not inspect(connection).has_table("trial_forecast_evidence")
        migration.upgrade()
        trigger_names = {
            row[0]
            for row in connection.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type = 'trigger' "
                    "AND name LIKE 'trial_forecast_evidence_immutable_%'"
                )
            )
        }
        assert trigger_names == {
            "trial_forecast_evidence_immutable_update",
            "trial_forecast_evidence_immutable_delete",
        }
    engine.dispose()
