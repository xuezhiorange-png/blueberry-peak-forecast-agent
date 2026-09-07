"""Contract tests for prospective forecast-authority retention."""

from __future__ import annotations

import hashlib
import os
from collections.abc import AsyncGenerator
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import cast

import pytest
from sqlalchemy import Table, func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

import backend.app.forecast_authority.retention as retention
import backend.app.rolling_backtest.persisted_task10_authority_binding as task10_binding
from backend.app.forecast_authority.retention import (
    ForecastAuthorityConflictError,
    ForecastAuthorityDailySource,
    ForecastAuthorityInputError,
    ForecastAuthorityPostCutoffError,
    ForecastAuthoritySource,
    ForecastAuthorityTestFixtureError,
    capture_forecast_authority,
    capture_production_forecast_authority,
    load_pit_visible_forecast_authority,
)
from backend.app.models.forecast_authority import (
    ForecastAuthorityCaptureModel,
    ForecastAuthorityDailyModel,
)

_CUTOFF = datetime(2026, 2, 16, 0, 0, tzinfo=UTC)


def _hash(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _daily(*, offset: int = 0, p50: str = "10.125000") -> ForecastAuthorityDailySource:
    p50_value = Decimal(p50)
    return ForecastAuthorityDailySource(
        source_daily_prediction_id=100 + offset,
        forecast_run_id=200,
        prediction_date=date(2026, 2, 1) + timedelta(days=offset),
        phenology_coordinate_day=Decimal(30 + offset),
        p50_kg=p50_value,
        p80_kg=p50_value + Decimal("1.000000"),
        p90_kg=p50_value + Decimal("2.000000"),
        cumulative_p50_kg=p50_value,
        cumulative_p80_kg=p50_value + Decimal("1.000000"),
        cumulative_p90_kg=p50_value + Decimal("2.000000"),
        curve_share=Decimal("0.5000000000"),
        confidence_level="HIGH",
        quality_flags=("observed",),
        source_created_at=_CUTOFF - timedelta(days=2),
    )


def _source(
    *,
    identity: str = "forecast-a",
    daily: tuple[ForecastAuthorityDailySource, ...] = (_daily(offset=0), _daily(offset=1)),
    marker: str = "retained-production-owner",
) -> ForecastAuthoritySource:
    return ForecastAuthoritySource(
        forecast_identity=_hash(identity),
        forecast_cutoff_at=_CUTOFF,
        forecast_created_at=_CUTOFF - timedelta(days=3),
        forecast_available_at=_CUTOFF - timedelta(days=2),
        core_forecast_run_id=1,
        code_authority_id=2,
        code_authority_hash=_hash("code-authority"),
        code_authority_available_at=_CUTOFF - timedelta(days=5),
        forecast_season_id=3,
        destination_factory_id=4,
        business_grain_snapshot={
            "grain": "SEASON_X_FARM_X_SUBFARM_X_VARIETY",
            "season": {"id": 3, "code": "2026"},
            "factory": {"id": 4, "code": "factory-a"},
            "grains": [
                {"farm_id": 1, "subfarm_id": 2, "variety_id": 3},
            ],
            "records": [
                {"season": "2026", "farm": "farm-a", "subfarm": "block-a", "variety": "v-a"}
            ],
            "source": marker,
        },
        plan_id=5,
        plan_version=1,
        plan_row_hash=_hash("plan-row"),
        plan_snapshot={
            "id": 5,
            "farm_id": 1,
            "season_id": 3,
            "variety_id": 3,
            "version": 1,
            "row_hash": _hash("plan-row"),
            "source": marker,
        },
        location_reference_id=6,
        weather_mapping_id=7,
        base_temperature_search_run_id=8,
        weather_snapshot={
            "location_reference": {"id": 6},
            "weather_mapping": {"id": 7},
            "weather_source_location": {"id": 9},
            "mapping_id": 7,
            "base_temperature_run_id": 8,
            "source": marker,
        },
        task8_forecast_run_id=200,
        task8_model_run_id=9,
        task8_artifact_id=10,
        task8_model_version="maturity-v1",
        task8_config_hash=_hash("task8-config"),
        task8_artifact_hash=_hash("task8-artifact"),
        task8_snapshot={
            "forecast_run": {"id": 200},
            "model_run": {"id": 9},
            "artifact": {"id": 10},
            "daily_row_ids": [100, 101],
            "run_id": 200,
            "model_run_id": 9,
            "artifact_id": 10,
            "source": marker,
        },
        task9_run_id=11,
        task9_result_hash=_hash("task9-result"),
        task9_snapshot={
            "run": {"id": 11, "result_hash": _hash("task9-result")},
            "member_row_count": 1,
            "run_id": 11,
            "result_hash": _hash("task9-result"),
            "source": marker,
        },
        task10_training_run_id=12,
        task10_training_signature=_hash("task10-training"),
        task10_prediction_run_id=13,
        task10_prediction_input_signature=_hash("task10-input"),
        task10_prediction_hash=_hash("task10-prediction"),
        task10_binding_id=14,
        task10_binding_hash=_hash("task10-binding"),
        task10_snapshot={
            "binding": {"id": 14},
            "prediction_run": {"id": 13},
            "training_run": {"id": 12},
            "prediction_row_hashes": [_hash("prediction-row")],
            "training_run_id": 12,
            "prediction_run_id": 13,
            "binding_id": 14,
            "source": marker,
        },
        core_snapshot={
            "run": {"id": 1, "request_hash": _hash(identity)},
            "daily_row_hashes": [_hash("core-row")],
            "run_id": 1,
            "request_hash": _hash(identity),
            "source": marker,
        },
        governance_snapshot={
            "policy_version": "retention-v1",
            "model_identity": "maturity-v1",
            "parameter_identity": _hash("parameters"),
            "policy_identity": "policy-v1",
            "source_identity": marker,
        },
        daily_predictions=daily,
    )


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    capture_table = cast(Table, ForecastAuthorityCaptureModel.__table__)
    daily_table = cast(Table, ForecastAuthorityDailyModel.__table__)
    async with engine.begin() as connection:
        await connection.run_sync(capture_table.create)
        await connection.run_sync(daily_table.create)
    async with AsyncSession(engine, expire_on_commit=False) as db_session:
        yield db_session
    await engine.dispose()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_production_entrypoint_creates_durable_capture(session: AsyncSession) -> None:
    source = _source()
    original = retention.build_forecast_authority_source_from_persisted_lineage

    async def _source_builder(
        _session: AsyncSession, *, core_forecast_run_id: int
    ) -> ForecastAuthoritySource:
        assert core_forecast_run_id == 1
        return source

    retention.build_forecast_authority_source_from_persisted_lineage = _source_builder  # type: ignore[assignment]
    try:
        result = await capture_production_forecast_authority(session, core_forecast_run_id=1)
    finally:
        retention.build_forecast_authority_source_from_persisted_lineage = original
    assert result.reused_existing is False
    assert result.write_count == 3
    assert (
        await session.scalar(select(ForecastAuthorityCaptureModel.authority_scope)) == "PRODUCTION"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_task10_completion_boundary_captures_authority(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    bound = task10_binding.PersistedTask10AuthorityBindingWriteResult(
        outcome=task10_binding.PersistedTask10AuthorityBindingWriteOutcome.BOUND,
        core_forecast_run_id=1,
        task10_prediction_run_id=13,
        binding_id=14,
    )

    async def _bind(
        _session: AsyncSession, **_kwargs: object
    ) -> task10_binding.PersistedTask10AuthorityBindingWriteResult:
        return bound

    async def _capture(
        _session: AsyncSession, *, core_forecast_run_id: int
    ) -> retention.ForecastAuthorityCaptureResult:
        assert core_forecast_run_id == 1
        return retention.ForecastAuthorityCaptureResult(
            capture_id=22,
            authority_hash=_hash("authority"),
            reused_existing=False,
            write_count=3,
        )

    monkeypatch.setattr(
        task10_binding,
        "write_persisted_task10_authority_binding_from_pinned_lineage",
        _bind,
    )
    monkeypatch.setattr(retention, "capture_production_forecast_authority", _capture)

    result = await task10_binding.write_persisted_task10_authority_binding_and_capture(
        session,
        task10_prediction_run_id=13,
        task8_forecast_run_id=15,
        task9_harvest_state_run_id=16,
        task9_result_hash=_hash("task9"),
        forecast_effective_cutoff_at=_CUTOFF,
    )

    assert result.outcome == task10_binding.PersistedTask10AuthorityBindingWriteOutcome.BOUND
    assert result.forecast_authority_capture_id == 22
    assert result.forecast_authority_reused_existing is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_daily_quantiles_survive_fresh_session_readback(session: AsyncSession) -> None:
    source = _source()
    await capture_forecast_authority(session, source=source)
    await session.commit()
    engine = cast(AsyncEngine, session.bind)
    async with AsyncSession(engine, expire_on_commit=False) as fresh_session:
        loaded = await load_pit_visible_forecast_authority(
            fresh_session,
            forecast_identity=source.forecast_identity,
            cutoff_at=_CUTOFF,
        )
    assert [(row.p50_kg, row.p80_kg, row.p90_kg) for row in loaded.daily_predictions] == [
        (Decimal("10.125000"), Decimal("11.125000"), Decimal("12.125000")),
        (Decimal("10.125000"), Decimal("11.125000"), Decimal("12.125000")),
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cutoff_is_persisted_and_enforced(session: AsyncSession) -> None:
    source = _source()
    await capture_forecast_authority(session, source=source)
    await session.commit()
    with pytest.raises(ForecastAuthorityPostCutoffError):
        await load_pit_visible_forecast_authority(
            session,
            forecast_identity=source.forecast_identity,
            cutoff_at=_CUTOFF - timedelta(seconds=1),
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cross_owner_snapshot_identity_drift_fails_closed(session: AsyncSession) -> None:
    original = _source()
    source = replace(
        original,
        plan_snapshot={
            **original.plan_snapshot,
            "id": 999,
        },
    )
    with pytest.raises(retention.ForecastAuthorityIntegrityError):
        await capture_forecast_authority(session, source=source)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_all_lineage_snapshots_bind_to_one_capture(session: AsyncSession) -> None:
    source = _source()
    result = await capture_forecast_authority(session, source=source)
    row = await session.get(ForecastAuthorityCaptureModel, result.capture_id)
    assert row is not None
    assert row.core_forecast_run_id == source.core_forecast_run_id
    assert row.task8_forecast_run_id == source.task8_forecast_run_id
    assert row.task9_run_id == source.task9_run_id
    assert row.task10_prediction_run_id == source.task10_prediction_run_id
    assert row.task10_binding_id == source.task10_binding_id
    assert row.plan_id == source.plan_id
    assert row.location_reference_id == source.location_reference_id
    assert row.business_grain_snapshot["grain"] == "SEASON_X_FARM_X_SUBFARM_X_VARIETY"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_canonical_hash_replay_is_deterministic(session: AsyncSession) -> None:
    source = _source()
    first = await capture_forecast_authority(session, source=source)
    second = await capture_forecast_authority(session, source=source)
    assert first.authority_hash == second.authority_hash
    assert second.reused_existing is True
    assert second.write_count == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_exact_replay_is_zero_write(session: AsyncSession) -> None:
    source = _source()
    first = await capture_forecast_authority(session, source=source)
    await session.commit()
    before = await session.scalar(select(func.count(ForecastAuthorityCaptureModel.id)))
    replay = await capture_forecast_authority(session, source=source)
    after = await session.scalar(select(func.count(ForecastAuthorityCaptureModel.id)))
    assert first.write_count == 3
    assert replay.write_count == 0
    assert before == after == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_conflicting_replay_fails_closed(session: AsyncSession) -> None:
    source = _source()
    await capture_forecast_authority(session, source=source)
    conflicting = replace(
        source,
        daily_predictions=(
            replace(_daily(offset=0), source_daily_prediction_id=100, p50_kg=Decimal("9")),
            _daily(offset=1),
        ),
    )
    with pytest.raises(ForecastAuthorityConflictError):
        await capture_forecast_authority(session, source=conflicting)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_post_hoc_mutation_is_detected_by_readback(session: AsyncSession) -> None:
    source = _source()
    result = await capture_forecast_authority(session, source=source)
    await session.commit()
    await session.execute(
        update(ForecastAuthorityDailyModel)
        .where(ForecastAuthorityDailyModel.forecast_authority_capture_id == result.capture_id)
        .values(p50_kg=Decimal("9.000000"))
    )
    await session.commit()
    with pytest.raises(retention.ForecastAuthorityIntegrityError):
        await load_pit_visible_forecast_authority(
            session,
            forecast_identity=source.forecast_identity,
            cutoff_at=_CUTOFF,
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_missing_authority_fails_closed(session: AsyncSession) -> None:
    with pytest.raises(retention.ForecastAuthorityMissingError):
        await load_pit_visible_forecast_authority(
            session,
            forecast_identity=_hash("missing"),
            cutoff_at=_CUTOFF,
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ambiguous_authority_path_is_explicitly_guarded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _ambiguous(_session: AsyncSession, _identity: str) -> None:
        raise retention.ForecastAuthorityAmbiguousError()

    monkeypatch.setattr(retention, "_load_capture_by_identity", _ambiguous)
    with pytest.raises(retention.ForecastAuthorityAmbiguousError):
        await load_pit_visible_forecast_authority(
            object(),  # type: ignore[arg-type]
            forecast_identity=_hash("ambiguous"),
            cutoff_at=_CUTOFF,
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_post_cutoff_daily_source_fails_closed(session: AsyncSession) -> None:
    late = replace(_daily(offset=0), source_created_at=_CUTOFF + timedelta(seconds=1))
    with pytest.raises(ForecastAuthorityPostCutoffError):
        await capture_forecast_authority(session, source=_source(daily=(late, _daily(offset=1))))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_native_float_is_rejected(session: AsyncSession) -> None:
    float_row = replace(_daily(offset=0), p50_kg=cast(Decimal, 1.25))
    with pytest.raises(ForecastAuthorityInputError):
        await capture_forecast_authority(
            session, source=_source(daily=(float_row, _daily(offset=1)))
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_test_fixture_authority_cannot_be_promoted(session: AsyncSession) -> None:
    source = _source(marker="s2-fixture-authority")
    with pytest.raises(ForecastAuthorityTestFixtureError):
        await capture_forecast_authority(session, source=source)


@pytest.mark.postgres
@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgres_session_boundary_is_opt_in() -> None:
    """Exercise the same commit/readback contract when the PG profile is enabled."""
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("PostgreSQL integration profile is not enabled")
    from backend.app.core.config import get_settings

    engine = create_async_engine(get_settings().async_database_url)
    try:
        capture_table = cast(Table, ForecastAuthorityCaptureModel.__table__)
        daily_table = cast(Table, ForecastAuthorityDailyModel.__table__)
        async with engine.begin() as connection:
            await connection.run_sync(capture_table.create, checkfirst=True)
            await connection.run_sync(daily_table.create, checkfirst=True)
        source = _source(identity="postgres-boundary")
        async with AsyncSession(engine, expire_on_commit=False) as writer:
            await capture_forecast_authority(writer, source=source)
            await writer.commit()
        async with AsyncSession(engine, expire_on_commit=False) as reader:
            loaded = await load_pit_visible_forecast_authority(
                reader,
                forecast_identity=source.forecast_identity,
                cutoff_at=_CUTOFF,
            )
            assert loaded.authority_hash
    finally:
        await engine.dispose()
