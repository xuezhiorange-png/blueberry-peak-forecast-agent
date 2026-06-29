"""P0-5F: PostgreSQL integration tests for Task 7 resolver adapters.

Tests the real resolver adapter functions against PostgreSQL — verifying
WeatherFeatureRun status/cutoff filtering, named timezone date conversion,
and WeatherDailyObservation window boundaries.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from backend.app.db.session import AsyncSessionMaker
from backend.app.models.weather import (
    LocationWeatherMapping,
    WeatherDailyObservation,
    WeatherFeatureRun,
)
from backend.app.rolling_backtest.enums import (
    ExecutionMode,
    Task10ModelPolicy,
    UpstreamSelectionMode,
)
from backend.app.rolling_backtest.resolution import (
    _query_task7_location_weather_mapping_candidates,
    _query_task7_weather_daily_observation_candidates,
    _query_task7_weather_feature_run_candidates,
)
from backend.app.rolling_backtest.schemas import (
    HistoricalAvailableModelIdentity,
    RollingNodeDefinition,
    RollingNodeScope,
)

pytestmark = pytest.mark.integration


def _make_node(
    *,
    forecast_cutoff_at: datetime,
    node_timezone: str = "Asia/Shanghai",
    as_of_local_date: date | None = None,
    forecast_start: date | None = None,
    forecast_end: date | None = None,
) -> RollingNodeDefinition:
    """Build a minimal test node with configurable cutoff and timezone."""
    from backend.app.rolling_backtest.enums import ScopeMode
    from backend.app.rolling_backtest.schemas import ScopeSelector

    as_of = as_of_local_date or date(2026, 3, 15)
    return RollingNodeDefinition(
        season_id=2026,
        node_key="test_node",
        as_of_local_date=as_of,
        forecast_cutoff_at=forecast_cutoff_at,
        forecast_start_local_date=forecast_start or date(2026, 3, 16),
        forecast_end_local_date=forecast_end or date(2026, 3, 31),
        scope=RollingNodeScope(
            destination_factory_ids=ScopeSelector(mode=ScopeMode.INCLUDE_IDS, ids=(1,)),
            farm_ids=ScopeSelector(mode=ScopeMode.ALL),
            variety_ids=ScopeSelector(mode=ScopeMode.ALL),
        ),
        upstream_selection_mode=UpstreamSelectionMode.HISTORICAL_RESOLUTION,
        forecast_horizon_policy_version="test-v1",
        timezone=node_timezone,
        task10_model_policy=HistoricalAvailableModelIdentity(
            policy=Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL,
            training_run_semantic_identity="1" * 64,
            artifact_semantic_identities=("2" * 64,),
            authority_visibility_identity="3" * 64,
        ),
        resolved_upstream_semantic_identities=(),
    )


# ══════════════════════════════════════════════════════════════════════════════
# Helpers: create test data
# ══════════════════════════════════════════════════════════════════════════════


async def _seed_weather_feature_run(
    session,
    *,
    status: str = "completed",
    finished_at: datetime | None = None,
    plan_id: int = 1,
    location_reference_id: int = 1,
    weather_mapping_id: int = 1,
    base_temperature_search_run_id: int = 1,
    feature_version: str = "v1",
    source_signature: str = "a" * 64,
    config_hash: str = "b" * 64,
) -> WeatherFeatureRun:
    """Seed a WeatherFeatureRun row."""
    run = WeatherFeatureRun(
        status=status,
        finished_at=finished_at,
        plan_id=plan_id,
        location_reference_id=location_reference_id,
        location_weather_mapping_id=weather_mapping_id,
        base_temperature_search_run_id=base_temperature_search_run_id,
        feature_version=feature_version,
        source_signature=source_signature,
        config_hash=config_hash,
    )
    session.add(run)
    await session.flush()
    return run


async def _seed_location_weather_mapping(
    session,
    *,
    available_at: date,
    valid_from: date | None = None,
    valid_to: date | None = None,
    location_reference_id: int = 1,
    weather_source_location_id: int = 1,
    mapping_version: str = "v1",
    row_hash: str = "c" * 64,
    config_hash: str = "d" * 64,
) -> LocationWeatherMapping:
    """Seed a LocationWeatherMapping row."""
    mapping = LocationWeatherMapping(
        available_at=available_at,
        valid_from=valid_from or available_at,
        valid_to=valid_to,
        location_reference_id=location_reference_id,
        weather_source_location_id=weather_source_location_id,
        mapping_version=mapping_version,
        row_hash=row_hash,
        config_hash=config_hash,
    )
    session.add(mapping)
    await session.flush()
    return mapping


async def _seed_weather_daily_observation(
    session,
    *,
    available_at: date,
    observation_date: date,
    weather_source_location_id: int = 1,
    provider_code: str = "test",
    source_version: str = "v1",
    row_hash: str = "e" * 64,
) -> WeatherDailyObservation:
    """Seed a WeatherDailyObservation row."""
    obs = WeatherDailyObservation(
        available_at=available_at,
        observation_date=observation_date,
        weather_source_location_id=weather_source_location_id,
        provider_code=provider_code,
        source_version=source_version,
        row_hash=row_hash,
    )
    session.add(obs)
    await session.flush()
    return obs


# ══════════════════════════════════════════════════════════════════════════════
# WeatherFeatureRun: datetime cutoff + status filtering
# ══════════════════════════════════════════════════════════════════════════════


class TestWeatherFeatureRunCutoffBoundaries:
    """Verify finished_at cutoff filtering in the production resolver."""

    @pytest.mark.asyncio
    async def test_finished_at_before_cutoff_returned(self) -> None:
        """finished_at < cutoff → candidate returned."""
        cutoff = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
        node = _make_node(forecast_cutoff_at=cutoff)

        async with AsyncSessionMaker() as session:
            run = await _seed_weather_feature_run(
                session,
                status="completed",
                finished_at=datetime(2026, 3, 15, 10, 0, tzinfo=UTC),
            )
            await session.commit()

            candidates = await _query_task7_weather_feature_run_candidates(
                session, node, ExecutionMode.HISTORICAL_OBSERVED
            )
            ids = [c.persistent_reference.reference_value for c in candidates]
            assert run.id in ids

    @pytest.mark.asyncio
    async def test_finished_at_equals_cutoff_returned(self) -> None:
        """finished_at == cutoff → candidate returned."""
        cutoff = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
        node = _make_node(forecast_cutoff_at=cutoff)

        async with AsyncSessionMaker() as session:
            run = await _seed_weather_feature_run(
                session,
                status="completed",
                finished_at=cutoff,
            )
            await session.commit()

            candidates = await _query_task7_weather_feature_run_candidates(
                session, node, ExecutionMode.HISTORICAL_OBSERVED
            )
            ids = [c.persistent_reference.reference_value for c in candidates]
            assert run.id in ids

    @pytest.mark.asyncio
    async def test_finished_at_after_cutoff_excluded(self) -> None:
        """finished_at > cutoff (by 1 microsecond) → excluded."""
        cutoff = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
        node = _make_node(forecast_cutoff_at=cutoff)

        async with AsyncSessionMaker() as session:
            after = datetime(2026, 3, 15, 12, 0, 0, 1, tzinfo=UTC)
            await _seed_weather_feature_run(
                session,
                status="completed",
                finished_at=after,
            )
            await session.commit()

            candidates = await _query_task7_weather_feature_run_candidates(
                session, node, ExecutionMode.HISTORICAL_OBSERVED
            )
            assert len(candidates) == 0

    @pytest.mark.asyncio
    async def test_finished_at_null_excluded(self) -> None:
        """finished_at IS NULL → excluded."""
        cutoff = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
        node = _make_node(forecast_cutoff_at=cutoff)

        async with AsyncSessionMaker() as session:
            await _seed_weather_feature_run(
                session,
                status="completed",
                finished_at=None,
            )
            await session.commit()

            candidates = await _query_task7_weather_feature_run_candidates(
                session, node, ExecutionMode.HISTORICAL_OBSERVED
            )
            assert len(candidates) == 0

    @pytest.mark.asyncio
    async def test_completed_visible_returned(self) -> None:
        """status == 'completed' + finished_at <= cutoff → returned."""
        cutoff = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
        node = _make_node(forecast_cutoff_at=cutoff)

        async with AsyncSessionMaker() as session:
            run = await _seed_weather_feature_run(
                session,
                status="completed",
                finished_at=datetime(2026, 3, 15, 10, 0, tzinfo=UTC),
            )
            await session.commit()

            candidates = await _query_task7_weather_feature_run_candidates(
                session, node, ExecutionMode.HISTORICAL_OBSERVED
            )
            ids = [c.persistent_reference.reference_value for c in candidates]
            assert run.id in ids

    @pytest.mark.asyncio
    async def test_unavailable_excluded(self) -> None:
        """status == 'unavailable' → excluded from resolver."""
        cutoff = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
        node = _make_node(forecast_cutoff_at=cutoff)

        async with AsyncSessionMaker() as session:
            await _seed_weather_feature_run(
                session,
                status="unavailable",
                finished_at=datetime(2026, 3, 15, 10, 0, tzinfo=UTC),
            )
            await session.commit()

            candidates = await _query_task7_weather_feature_run_candidates(
                session, node, ExecutionMode.HISTORICAL_OBSERVED
            )
            assert len(candidates) == 0

    @pytest.mark.asyncio
    async def test_failed_excluded(self) -> None:
        """status == 'failed' → excluded."""
        cutoff = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
        node = _make_node(forecast_cutoff_at=cutoff)

        async with AsyncSessionMaker() as session:
            await _seed_weather_feature_run(
                session,
                status="failed",
                finished_at=datetime(2026, 3, 15, 10, 0, tzinfo=UTC),
            )
            await session.commit()

            candidates = await _query_task7_weather_feature_run_candidates(
                session, node, ExecutionMode.HISTORICAL_OBSERVED
            )
            assert len(candidates) == 0

    @pytest.mark.asyncio
    async def test_cancelled_excluded(self) -> None:
        """status == 'cancelled' → excluded."""
        cutoff = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
        node = _make_node(forecast_cutoff_at=cutoff)

        async with AsyncSessionMaker() as session:
            await _seed_weather_feature_run(
                session,
                status="cancelled",
                finished_at=datetime(2026, 3, 15, 10, 0, tzinfo=UTC),
            )
            await session.commit()

            candidates = await _query_task7_weather_feature_run_candidates(
                session, node, ExecutionMode.HISTORICAL_OBSERVED
            )
            assert len(candidates) == 0

    @pytest.mark.asyncio
    async def test_running_excluded(self) -> None:
        """status == 'running' → excluded."""
        cutoff = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
        node = _make_node(forecast_cutoff_at=cutoff)

        async with AsyncSessionMaker() as session:
            await _seed_weather_feature_run(
                session,
                status="running",
                finished_at=datetime(2026, 3, 15, 10, 0, tzinfo=UTC),
            )
            await session.commit()

            candidates = await _query_task7_weather_feature_run_candidates(
                session, node, ExecutionMode.HISTORICAL_OBSERVED
            )
            assert len(candidates) == 0


# ══════════════════════════════════════════════════════════════════════════════
# LocationWeatherMapping: positive timezone rollover
# ══════════════════════════════════════════════════════════════════════════════


class TestMappingPositiveTimezoneRollover:
    """Verify date cutoff uses named timezone, not UTC .date()."""

    @pytest.mark.asyncio
    async def test_available_at_same_local_date_included(self) -> None:
        """UTC evening rolls to next local day → same local date included."""
        # UTC 2026-03-15T16:30 → Asia/Shanghai 2026-03-16T00:30 → local date 2026-03-16
        cutoff = datetime(2026, 3, 15, 16, 30, 0, tzinfo=UTC)
        node = _make_node(forecast_cutoff_at=cutoff, node_timezone="Asia/Shanghai")

        async with AsyncSessionMaker() as session:
            mapping = await _seed_location_weather_mapping(
                session,
                available_at=date(2026, 3, 16),  # same as local date → included
            )
            await session.commit()

            candidates = await _query_task7_location_weather_mapping_candidates(
                session, node, ExecutionMode.HISTORICAL_OBSERVED
            )
            ids = [c.persistent_reference.reference_value for c in candidates]
            assert mapping.id in ids

    @pytest.mark.asyncio
    async def test_available_at_next_local_date_excluded(self) -> None:
        """One day after local cutoff → excluded."""
        cutoff = datetime(2026, 3, 15, 16, 30, 0, tzinfo=UTC)
        node = _make_node(forecast_cutoff_at=cutoff, node_timezone="Asia/Shanghai")

        async with AsyncSessionMaker() as session:
            await _seed_location_weather_mapping(
                session,
                available_at=date(2026, 3, 17),  # after local date 2026-03-16 → excluded
            )
            await session.commit()

            candidates = await _query_task7_location_weather_mapping_candidates(
                session, node, ExecutionMode.HISTORICAL_OBSERVED
            )
            assert len(candidates) == 0


# ══════════════════════════════════════════════════════════════════════════════
# LocationWeatherMapping: negative timezone rollover
# ══════════════════════════════════════════════════════════════════════════════


class TestMappingNegativeTimezoneRollover:
    """Verify named timezone for America/Los_Angeles (UTC-7/-8)."""

    @pytest.mark.asyncio
    async def test_utc_next_day_local_still_previous_day(self) -> None:
        """UTC date is next day, but local date is previous.

        UTC 2026-03-16T02:00 = LA 2026-03-15T19:00 (PDT, UTC-7)
        available_at=2026-03-15 → same as local date → included.
        available_at=2026-03-16 → after local date → excluded.
        """
        cutoff = datetime(2026, 3, 16, 2, 0, tzinfo=UTC)  # LA 2026-03-15 19:00
        node = _make_node(
            forecast_cutoff_at=cutoff,
            node_timezone="America/Los_Angeles",
        )

        async with AsyncSessionMaker() as session:
            mapping_15 = await _seed_location_weather_mapping(
                session,
                available_at=date(2026, 3, 15),
            )
            await _seed_location_weather_mapping(
                session,
                available_at=date(2026, 3, 16),
            )
            await session.commit()

            candidates = await _query_task7_location_weather_mapping_candidates(
                session, node, ExecutionMode.HISTORICAL_OBSERVED
            )
            ids = [c.persistent_reference.reference_value for c in candidates]
            # 2026-03-15 is at or before local date → included
            assert mapping_15.id in ids
            # 2026-03-16 > local date 2026-03-15 → excluded
            assert len(candidates) == 1


# ══════════════════════════════════════════════════════════════════════════════
# WeatherDailyObservation: observation_date window
# ══════════════════════════════════════════════════════════════════════════════


class TestObservationWindow:
    """Verify observation_date and available_at filtering."""

    @pytest.mark.asyncio
    async def test_observation_at_forecast_start_included(self) -> None:
        """observation_date == forecast_start → included."""
        cutoff = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
        node = _make_node(
            forecast_cutoff_at=cutoff,
            forecast_start=date(2026, 3, 16),
            forecast_end=date(2026, 3, 31),
        )

        async with AsyncSessionMaker() as session:
            obs = await _seed_weather_daily_observation(
                session,
                available_at=date(2026, 3, 1),
                observation_date=date(2026, 3, 16),
            )
            await session.commit()

            candidates = await _query_task7_weather_daily_observation_candidates(
                session, node, ExecutionMode.HISTORICAL_OBSERVED
            )
            ids = [c.persistent_reference.reference_value for c in candidates]
            assert obs.id in ids

    @pytest.mark.asyncio
    async def test_observation_at_forecast_end_included(self) -> None:
        """observation_date == forecast_end → included."""
        cutoff = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
        node = _make_node(
            forecast_cutoff_at=cutoff,
            forecast_start=date(2026, 3, 16),
            forecast_end=date(2026, 3, 31),
        )

        async with AsyncSessionMaker() as session:
            obs = await _seed_weather_daily_observation(
                session,
                available_at=date(2026, 3, 1),
                observation_date=date(2026, 3, 31),
            )
            await session.commit()

            candidates = await _query_task7_weather_daily_observation_candidates(
                session, node, ExecutionMode.HISTORICAL_OBSERVED
            )
            ids = [c.persistent_reference.reference_value for c in candidates]
            assert obs.id in ids

    @pytest.mark.asyncio
    async def test_observation_before_forecast_start_excluded(self) -> None:
        """observation_date < forecast_start → excluded."""
        cutoff = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
        node = _make_node(
            forecast_cutoff_at=cutoff,
            forecast_start=date(2026, 3, 16),
            forecast_end=date(2026, 3, 31),
        )

        async with AsyncSessionMaker() as session:
            await _seed_weather_daily_observation(
                session,
                available_at=date(2026, 3, 1),
                observation_date=date(2026, 3, 15),
            )
            await session.commit()

            candidates = await _query_task7_weather_daily_observation_candidates(
                session, node, ExecutionMode.HISTORICAL_OBSERVED
            )
            assert len(candidates) == 0

    @pytest.mark.asyncio
    async def test_observation_after_forecast_end_excluded(self) -> None:
        """observation_date > forecast_end → excluded."""
        cutoff = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
        node = _make_node(
            forecast_cutoff_at=cutoff,
            forecast_start=date(2026, 3, 16),
            forecast_end=date(2026, 3, 31),
        )

        async with AsyncSessionMaker() as session:
            await _seed_weather_daily_observation(
                session,
                available_at=date(2026, 3, 1),
                observation_date=date(2026, 4, 1),
            )
            await session.commit()

            candidates = await _query_task7_weather_daily_observation_candidates(
                session, node, ExecutionMode.HISTORICAL_OBSERVED
            )
            assert len(candidates) == 0

    @pytest.mark.asyncio
    async def test_available_at_after_cutoff_local_date_excluded(self) -> None:
        """available_at > cutoff_local_date → excluded even if observation in window."""
        cutoff = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
        node = _make_node(
            forecast_cutoff_at=cutoff,
            forecast_start=date(2026, 3, 16),
            forecast_end=date(2026, 3, 31),
        )

        async with AsyncSessionMaker() as session:
            await _seed_weather_daily_observation(
                session,
                available_at=date(2026, 3, 20),
                observation_date=date(2026, 3, 16),
            )
            await session.commit()

            candidates = await _query_task7_weather_daily_observation_candidates(
                session, node, ExecutionMode.HISTORICAL_OBSERVED
            )
            assert len(candidates) == 0
