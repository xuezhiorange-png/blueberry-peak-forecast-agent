from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core_forecast.persistence import (
    CoreForecastPersistenceConflictError,
    CoreForecastPersistenceIntegrityError,
    CoreForecastRunRepository,
    _daily_schema,
    _row_model,
)
from backend.app.core_forecast.schemas import RegisterCoreForecastCodeAuthority
from backend.app.models.core_forecast import (
    CoreForecastCodeAuthorityModel,
    CoreForecastDailyRowModel,
    CoreForecastMetricModel,
    CoreForecastRunModel,
)
from backend.app.rolling_backtest.canonical import canonical_json_dumps
from backend.tests.core_forecast.s4_test_helpers import fixture_request_and_outputs


async def _persist_fixture(session: AsyncSession):
    (
        request,
        curve,
        metrics,
        policy_hash,
        input_hash,
        request_hash,
        result_hash,
    ) = await fixture_request_and_outputs()
    repository = CoreForecastRunRepository(session)
    persisted = await repository.save_completed_run(
        request=request,
        forecast_input_hash=input_hash,
        request_hash=request_hash,
        result_hash=result_hash,
        retention_policy_snapshot_hash=policy_hash,
        curve=curve,
        metrics=metrics,
        rerun_of_run_id=None,
    )
    return repository, persisted


async def _ensure_code_authority_table(session: AsyncSession) -> None:
    connection = await session.connection()
    await connection.run_sync(
        lambda sync_connection: CoreForecastCodeAuthorityModel.__table__.create(
            sync_connection,
            checkfirst=True,
        )
    )


@pytest.mark.unit
async def test_full_fixture_save_load_and_query_order(sqlite_session: AsyncSession) -> None:
    (
        request,
        curve,
        metrics,
        policy_hash,
        input_hash,
        request_hash,
        result_hash,
    ) = await fixture_request_and_outputs()
    repository = CoreForecastRunRepository(sqlite_session)
    persisted = await repository.save_completed_run(
        request=request,
        forecast_input_hash=input_hash,
        request_hash=request_hash,
        result_hash=result_hash,
        retention_policy_snapshot_hash=policy_hash,
        curve=curve,
        metrics=metrics,
        rerun_of_run_id=None,
    )
    loaded = await repository.get_run_by_id(persisted.run.run_id)
    assert loaded is not None
    assert loaded.run.result_hash == result_hash
    assert len(await repository.list_daily_rows(persisted.run.run_id)) == 1080
    assert tuple(
        item.forecast_quantile for item in await repository.list_metrics(persisted.run.run_id)
    ) == (
        "P50",
        "P80",
        "P90",
    )
    assert await sqlite_session.scalar(select(CoreForecastDailyRowModel.id)) is not None
    assert loaded.code_authority is None
    assert loaded.run.run_schema_version == "v0.1-core-forecast-run-v1"
    assert loaded.run.request_schema_version == "v0.1-core-forecast-request-v1"


@pytest.mark.unit
async def test_code_authority_registration_round_trips_and_is_idempotent(
    sqlite_session: AsyncSession,
) -> None:
    await _ensure_code_authority_table(sqlite_session)
    repository = CoreForecastRunRepository(sqlite_session)
    registration = RegisterCoreForecastCodeAuthority(
        source_commit_sha="a" * 40,
        engine_code_hash="e" * 64,
        build_artifact_hash="b" * 64,
        config_bundle_hash="c" * 64,
        available_at=datetime(2026, 2, 28, 4, 0, tzinfo=UTC),
    )
    first = await repository.register_code_authority(registration)
    second = await repository.register_code_authority(registration)
    loaded = await repository.get_code_authority_by_id(first.authority_id)
    assert loaded == first
    assert second == first
    assert first.authority_schema_version == "v0.1-core-forecast-code-authority-v1"
    assert await sqlite_session.scalar(select(func.count(CoreForecastCodeAuthorityModel.id))) == 1


@pytest.mark.unit
async def test_code_authority_identity_changes_for_build_config_or_availability(
    sqlite_session: AsyncSession,
) -> None:
    await _ensure_code_authority_table(sqlite_session)
    repository = CoreForecastRunRepository(sqlite_session)
    base = RegisterCoreForecastCodeAuthority(
        source_commit_sha="a" * 40,
        engine_code_hash="e" * 64,
        build_artifact_hash="b" * 64,
        config_bundle_hash="c" * 64,
        available_at=datetime(2026, 2, 28, 4, 0, tzinfo=UTC),
    )
    authorities = [
        await repository.register_code_authority(base),
        await repository.register_code_authority(
            base.model_copy(update={"build_artifact_hash": "d" * 64})
        ),
        await repository.register_code_authority(
            base.model_copy(update={"config_bundle_hash": "e" * 64})
        ),
        await repository.register_code_authority(
            base.model_copy(update={"available_at": base.available_at + timedelta(seconds=1)})
        ),
    ]
    assert len({authority.authority_hash for authority in authorities}) == 4


@pytest.mark.unit
async def test_tampered_code_authority_payload_fails_integrity(
    sqlite_session: AsyncSession,
) -> None:
    await _ensure_code_authority_table(sqlite_session)
    repository = CoreForecastRunRepository(sqlite_session)
    authority = await repository.register_code_authority(
        RegisterCoreForecastCodeAuthority(
            source_commit_sha="a" * 40,
            engine_code_hash="e" * 64,
            build_artifact_hash="b" * 64,
            config_bundle_hash="c" * 64,
            available_at=datetime(2026, 2, 28, 4, 0, tzinfo=UTC),
        )
    )
    await sqlite_session.execute(
        update(CoreForecastCodeAuthorityModel)
        .where(CoreForecastCodeAuthorityModel.id == authority.authority_id)
        .values(canonical_payload={"schema_version": "not-code-authority"})
    )
    with pytest.raises(CoreForecastPersistenceIntegrityError):
        await repository.get_code_authority_by_id(authority.authority_id)


@pytest.mark.unit
async def test_same_request_reuses_identical_run(sqlite_session: AsyncSession) -> None:
    (
        request,
        curve,
        metrics,
        policy_hash,
        input_hash,
        request_hash,
        result_hash,
    ) = await fixture_request_and_outputs()
    repository = CoreForecastRunRepository(sqlite_session)
    first = await repository.save_completed_run(
        request=request,
        forecast_input_hash=input_hash,
        request_hash=request_hash,
        result_hash=result_hash,
        retention_policy_snapshot_hash=policy_hash,
        curve=curve,
        metrics=metrics,
        rerun_of_run_id=None,
    )
    second = await repository.save_completed_run(
        request=request,
        forecast_input_hash=input_hash,
        request_hash=request_hash,
        result_hash=result_hash,
        retention_policy_snapshot_hash=policy_hash,
        curve=curve,
        metrics=metrics,
        rerun_of_run_id=None,
    )
    assert second.run.run_id == first.run.run_id


@pytest.mark.unit
async def test_same_request_hash_different_result_is_conflict(sqlite_session: AsyncSession) -> None:
    (
        request,
        curve,
        metrics,
        policy_hash,
        input_hash,
        request_hash,
        result_hash,
    ) = await fixture_request_and_outputs()
    repository = CoreForecastRunRepository(sqlite_session)
    await repository.save_completed_run(
        request=request,
        forecast_input_hash=input_hash,
        request_hash=request_hash,
        result_hash=result_hash,
        retention_policy_snapshot_hash=policy_hash,
        curve=curve,
        metrics=metrics,
        rerun_of_run_id=None,
    )
    with pytest.raises(CoreForecastPersistenceConflictError):
        await repository.save_completed_run(
            request=request,
            forecast_input_hash=input_hash,
            request_hash=request_hash,
            result_hash="c" * 64,
            retention_policy_snapshot_hash=policy_hash,
            curve=curve,
            metrics=metrics,
            rerun_of_run_id=None,
        )


@pytest.mark.unit
async def test_tampered_daily_row_fails_integrity_gate(sqlite_session: AsyncSession) -> None:
    (
        request,
        curve,
        metrics,
        policy_hash,
        input_hash,
        request_hash,
        result_hash,
    ) = await fixture_request_and_outputs()
    repository = CoreForecastRunRepository(sqlite_session)
    persisted = await repository.save_completed_run(
        request=request,
        forecast_input_hash=input_hash,
        request_hash=request_hash,
        result_hash=result_hash,
        retention_policy_snapshot_hash=policy_hash,
        curve=curve,
        metrics=metrics,
        rerun_of_run_id=None,
    )
    await sqlite_session.execute(
        update(CoreForecastDailyRowModel)
        .where(CoreForecastDailyRowModel.core_forecast_run_id == persisted.run.run_id)
        .values(effective_marketable_quantity_kg=999)
    )
    with pytest.raises(CoreForecastPersistenceIntegrityError):
        await repository.load_complete_run(persisted.run.run_id)


@pytest.mark.unit
async def test_tampered_daily_row_hash_fails_integrity_gate(
    sqlite_session: AsyncSession,
) -> None:
    repository, persisted = await _persist_fixture(sqlite_session)
    row_id = await sqlite_session.scalar(
        select(CoreForecastDailyRowModel.id)
        .where(CoreForecastDailyRowModel.core_forecast_run_id == persisted.run.run_id)
        .limit(1)
    )
    assert row_id is not None
    await sqlite_session.execute(
        update(CoreForecastDailyRowModel)
        .where(CoreForecastDailyRowModel.id == row_id)
        .values(row_hash="f" * 64)
    )
    with pytest.raises(CoreForecastPersistenceIntegrityError):
        await repository.load_complete_run(persisted.run.run_id)


@pytest.mark.unit
async def test_repository_does_not_commit_and_caller_rollback_removes_all_rows(
    sqlite_session: AsyncSession,
) -> None:
    (
        request,
        curve,
        metrics,
        policy_hash,
        input_hash,
        request_hash,
        result_hash,
    ) = await fixture_request_and_outputs()
    repository = CoreForecastRunRepository(sqlite_session)
    connection = await sqlite_session.connection()
    await connection.exec_driver_sql("BEGIN")
    await repository.save_completed_run(
        request=request,
        forecast_input_hash=input_hash,
        request_hash=request_hash,
        result_hash=result_hash,
        retention_policy_snapshot_hash=policy_hash,
        curve=curve,
        metrics=metrics,
        rerun_of_run_id=None,
    )
    assert await sqlite_session.scalar(select(func.count(CoreForecastRunModel.id))) == 1
    await sqlite_session.rollback()
    assert await sqlite_session.scalar(select(func.count(CoreForecastRunModel.id))) == 0
    assert await sqlite_session.scalar(select(func.count(CoreForecastDailyRowModel.id))) == 0


@pytest.mark.unit
async def test_query_by_id_request_hash_result_hash_and_recent_order(
    sqlite_session: AsyncSession,
) -> None:
    repository, persisted = await _persist_fixture(sqlite_session)

    assert (await repository.get_run_by_id(persisted.run.run_id)).run.run_id == persisted.run.run_id  # type: ignore[union-attr]
    assert (
        await repository.get_run_by_request_hash(persisted.run.request_hash)  # type: ignore[union-attr]
    ).run.run_id == persisted.run.run_id  # type: ignore[union-attr]
    assert (
        await repository.get_run_by_result_hash(persisted.run.result_hash)  # type: ignore[union-attr]
    ).run.run_id == persisted.run.run_id  # type: ignore[union-attr]
    recent = await repository.list_recent_runs(limit=1)
    assert tuple(item.run_id for item in recent) == (persisted.run.run_id,)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("result_hash", "e" * 64),
        ("curve_hash", "e" * 64),
        ("retention_policy_snapshot_hash", "e" * 64),
        ("task8_forecast_run_id", 810002),
        ("request_snapshot", {"invalid": True}),
    ],
)
async def test_run_tampering_fails_integrity_gate(
    sqlite_session: AsyncSession,
    field: str,
    value: object,
) -> None:
    repository, persisted = await _persist_fixture(sqlite_session)
    await sqlite_session.execute(
        update(CoreForecastRunModel)
        .where(CoreForecastRunModel.id == persisted.run.run_id)
        .values(**{field: value})
    )
    with pytest.raises(CoreForecastPersistenceIntegrityError):
        await repository.load_complete_run(persisted.run.run_id)


@pytest.mark.unit
async def test_metric_tampering_fails_integrity_gate(sqlite_session: AsyncSession) -> None:
    repository, persisted = await _persist_fixture(sqlite_session)
    await sqlite_session.execute(
        update(CoreForecastMetricModel)
        .where(CoreForecastMetricModel.core_forecast_run_id == persisted.run.run_id)
        .where(CoreForecastMetricModel.forecast_quantile == "P50")
        .values(single_day_peak_quantity_kg=0)
    )
    with pytest.raises(CoreForecastPersistenceIntegrityError):
        await repository.load_complete_run(persisted.run.run_id)


@pytest.mark.unit
async def test_missing_daily_row_fails_integrity_gate(sqlite_session: AsyncSession) -> None:
    repository, persisted = await _persist_fixture(sqlite_session)
    row_id = await sqlite_session.scalar(
        select(CoreForecastDailyRowModel.id)
        .where(CoreForecastDailyRowModel.core_forecast_run_id == persisted.run.run_id)
        .limit(1)
    )
    assert row_id is not None
    await sqlite_session.execute(
        delete(CoreForecastDailyRowModel).where(CoreForecastDailyRowModel.id == row_id)
    )
    with pytest.raises(CoreForecastPersistenceIntegrityError):
        await repository.load_complete_run(persisted.run.run_id)


@pytest.mark.unit
async def test_extra_daily_row_fails_business_integrity_gate(sqlite_session: AsyncSession) -> None:
    repository, persisted = await _persist_fixture(sqlite_session)
    existing = await sqlite_session.scalar(
        select(CoreForecastDailyRowModel)
        .where(CoreForecastDailyRowModel.core_forecast_run_id == persisted.run.run_id)
        .limit(1)
    )
    assert existing is not None
    extra = _daily_schema(existing).model_copy(update={"farm_id": 999})
    payload = extra.model_dump(mode="json", exclude={"row_hash"})
    row_hash = hashlib.sha256(canonical_json_dumps(payload).encode("utf-8")).hexdigest()
    extra = extra.model_copy(update={"row_hash": row_hash})
    sqlite_session.add(_row_model(persisted.run.run_id, extra))
    await sqlite_session.flush()
    with pytest.raises(CoreForecastPersistenceIntegrityError):
        await repository.load_complete_run(persisted.run.run_id)
