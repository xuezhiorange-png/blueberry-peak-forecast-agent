"""P0-5F: PostgreSQL integration tests for Task 7 resolver adapters.

Tests the real resolver adapter functions against PostgreSQL — verifying
WeatherFeatureRun status/cutoff filtering, named timezone date conversion,
and WeatherDailyObservation window boundaries.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from backend.app.db.session import AsyncSessionMaker
from backend.app.models.master_data import Farm, Season, Variety
from backend.app.models.planning import LocationReference
from backend.app.models.production_plan import FarmSeasonVarietyPlan
from backend.app.models.weather import (
    BaseTemperatureSearchRun,
    LocationWeatherMapping,
    WeatherDailyObservation,
    WeatherFeatureRun,
    WeatherSourceLocation,
)
from backend.app.rolling_backtest.enums import (
    AvailabilitySourceType,
    DefaultNodeKey,
    ExecutionMode,
    Task10ModelPolicy,
    UpstreamSelectionMode,
)
from backend.app.rolling_backtest.resolution import (
    _build_identity_payload,
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


# ══════════════════════════════════════════════════════════════════════════════
# Helper: build a minimal RollingNodeDefinition for tests
# ══════════════════════════════════════════════════════════════════════════════


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
        node_key=DefaultNodeKey.MARCH_15,
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
# Helper: create FK parent records (isolated per test by conftest truncation)
# ══════════════════════════════════════════════════════════════════════════════


class _ParentIds:
    """Holds IDs of FK parent records created by ``_seed_parents``."""

    __slots__ = (
        "location_reference_id",
        "weather_source_location_id",
        "plan_id",
        "base_temperature_search_run_id",
        "weather_mapping_id",
    )

    def __init__(
        self,
        *,
        location_reference_id: int,
        weather_source_location_id: int,
        plan_id: int,
        base_temperature_search_run_id: int,
        weather_mapping_id: int,
    ) -> None:
        self.location_reference_id = location_reference_id
        self.weather_source_location_id = weather_source_location_id
        self.plan_id = plan_id
        self.base_temperature_search_run_id = base_temperature_search_run_id
        self.weather_mapping_id = weather_mapping_id


async def _seed_parents() -> _ParentIds:
    """Create all FK parent records needed by the three Task 7 models.

    The ``isolate_master_data_tables`` fixture truncates all tables before each
    test, so this function is safe to call at the start of every test.
    """
    async with AsyncSessionMaker() as session:
        # ── master data ──────────────────────────────────────────────────
        season = Season(
            code="2026-t7",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        farm = Farm(name="farm-t7-resolver")
        variety = Variety(code="blueberry-t7", name="Blueberry T7")
        session.add_all([season, farm, variety])
        await session.flush()

        # ── location reference (nullable FKs — no dim_farm/dim_zone needed) ──
        location_ref = LocationReference(
            farm_id=None,
            subfarm_id=None,
            farm_code="FARM-T7",
            farm_name="farm-t7-resolver",
            subfarm_name=None,
            address_raw="Test Address T7",
            address_normalized="test address t7",
            province="Yunnan",
            prefecture="Honghe",
            county="Mile",
            township=None,
            village=None,
            latitude=Decimal("24.100000"),
            longitude=Decimal("102.100000"),
            altitude_m=Decimal("1800.00"),
            climate_zone_id=None,
            location_source="synthetic",
            source_version="loc-t7-v1",
            valid_from=date(2024, 1, 1),
            valid_to=None,
            source_row_hash="loc-t7-resolver-hash",
        )
        session.add(location_ref)
        await session.flush()

        # ── weather source location ──────────────────────────────────────
        weather_src = WeatherSourceLocation(
            provider_code="synthetic_t7",
            external_location_id="station-t7-resolver",
            location_type="station",
            name="Station T7 Resolver",
            latitude=Decimal("24.110000"),
            longitude=Decimal("102.110000"),
            altitude_m=Decimal("1810.00"),
            timezone_name="Asia/Shanghai",
            grid_resolution=None,
            source_version="dataset-t7-v1",
            valid_from=date(2024, 1, 1),
            valid_to=None,
            row_hash="src-t7-resolver-hash",
        )
        session.add(weather_src)
        await session.flush()

        # ── farm season variety plan (needs season + farm + variety) ─────
        plan = FarmSeasonVarietyPlan(
            farm_id=farm.id,
            subfarm_id=None,
            season_id=season.id,
            variety_id=variety.id,
            planted_area_mu=Decimal("100"),
            expected_yield_kg_per_mu=Decimal("1200"),
            marketable_rate=Decimal("0.8"),
            tree_age_years=Decimal("3"),
            pruning_date=date(2026, 1, 15),
            flowering_start_date=date(2026, 2, 1),
            flowering_peak_date=date(2026, 2, 6),
            flowering_end_date=date(2026, 2, 10),
            first_pick_date=date(2026, 3, 5),
            expected_total_marketable_kg=Decimal("96000"),
            version=1,
            effective_from=date(2026, 1, 1),
            effective_to=None,
            available_at=date(2026, 1, 1),
            source_type="manual",
            source_name="planner-t7",
            source_version="v1",
            notes="synthetic t7 resolver",
            row_hash="plan-t7-resolver-hash",
        )
        session.add(plan)
        await session.flush()

        # ── base temperature search run (nullable FKs) ───────────────────
        base_temp_run = BaseTemperatureSearchRun(
            scope_type="variety_zone",
            variety_id=None,
            climate_zone_id=None,
            training_cutoff=date(2026, 3, 1),
            anchor_event="flowering",
            target_event="first_pick",
            candidate_temperatures=["5.0", "6.0", "7.0"],
            selected_base_temperature=Decimal("6.0"),
            scoring_method="correlation",
            selected_score=Decimal("0.85"),
            training_sample_ids=[],
            candidate_scores={},
            config_hash="btr-cfg-t7",
            feature_version="v1",
            source_signature="btr-sig-t7-resolver",
            status="completed",
            warnings=[],
            blockers=[],
            input_snapshot={},
        )
        session.add(base_temp_run)
        await session.flush()

        # ── location weather mapping (FK parent for WeatherFeatureRun) ───
        # Use an EXPIRED validity window so the resolver never picks this up:
        #   valid_to=2000-12-31 < as_of_local_date=2026-03-15 → excluded.
        mapping = LocationWeatherMapping(
            location_reference_id=location_ref.id,
            weather_source_location_id=weather_src.id,
            mapping_method="nearest_station",
            distance_km=Decimal("1.500000"),
            altitude_difference_m=Decimal("10.000000"),
            mapping_score=Decimal("0.950000"),
            confidence_level="high",
            mapping_version="v1",
            config_hash="mapping-parent-cfg",
            available_at=date(2000, 1, 1),
            valid_from=date(2000, 1, 1),
            valid_to=date(2000, 12, 31),
            row_hash="mapping-parent-t7",
        )
        session.add(mapping)
        await session.flush()

        await session.commit()

        return _ParentIds(
            location_reference_id=location_ref.id,
            weather_source_location_id=weather_src.id,
            plan_id=plan.id,
            base_temperature_search_run_id=base_temp_run.id,
            weather_mapping_id=mapping.id,
        )


# ══════════════════════════════════════════════════════════════════════════════
# Helpers: create test data using real FK parent IDs
# ══════════════════════════════════════════════════════════════════════════════


async def _seed_weather_feature_run(
    session,
    *,
    parents: _ParentIds,
    status: str = "completed",
    finished_at: datetime | None = None,
    feature_version: str = "v1",
    source_signature: str = "a" * 64,
    config_hash: str = "b" * 64,
) -> WeatherFeatureRun:
    """Seed a WeatherFeatureRun row with all required fields."""
    run = WeatherFeatureRun(
        feature_version=feature_version,
        config_hash=config_hash,
        mapping_version="v1",
        weather_source_version="v1",
        base_temperature_search_run_id=parents.base_temperature_search_run_id,
        plan_id=parents.plan_id,
        location_reference_id=parents.location_reference_id,
        location_weather_mapping_id=parents.weather_mapping_id,
        weather_source_location_id=parents.weather_source_location_id,
        as_of_date=date(2026, 3, 15),
        feature_date=date(2026, 3, 15),
        source_signature=source_signature,
        status=status,
        input_snapshot={},
        window_features={},
        timeline_payload={},
        weather_observation_ids=[],
        warnings=[],
        blockers=[],
        finished_at=finished_at,
    )
    session.add(run)
    await session.flush()
    return run


async def _seed_location_weather_mapping(
    session,
    *,
    parents: _ParentIds,
    available_at: date,
    valid_from: date | None = None,
    valid_to: date | None = None,
) -> LocationWeatherMapping:
    """Seed a LocationWeatherMapping row with all required fields.

    ``valid_from`` defaults to 2024-01-01 (well before the test
    ``as_of_local_date`` of 2026-03-15) so the temporal-validity filter
    never excludes the row on that basis alone.
    """
    mapping = LocationWeatherMapping(
        location_reference_id=parents.location_reference_id,
        weather_source_location_id=parents.weather_source_location_id,
        mapping_method="nearest_station",
        distance_km=Decimal("1.500000"),
        altitude_difference_m=Decimal("10.000000"),
        mapping_score=Decimal("0.950000"),
        confidence_level="high",
        mapping_version="v1",
        config_hash="d" * 64,
        available_at=available_at,
        valid_from=valid_from or date(2024, 1, 1),
        valid_to=valid_to,
        row_hash=hashlib.sha256(f"mapping-{available_at.isoformat()}-t7".encode()).hexdigest(),
    )
    session.add(mapping)
    await session.flush()
    return mapping


async def _seed_weather_daily_observation(
    session,
    *,
    parents: _ParentIds,
    available_at: date,
    observation_date: date,
) -> WeatherDailyObservation:
    """Seed a WeatherDailyObservation row with all required fields."""
    obs = WeatherDailyObservation(
        weather_source_location_id=parents.weather_source_location_id,
        observation_date=observation_date,
        temperature_min_c=Decimal("5.000000"),
        temperature_max_c=Decimal("15.000000"),
        temperature_mean_c=Decimal("10.000000"),
        temperature_mean_source="provided",
        precipitation_mm=Decimal("0.000000"),
        solar_radiation_mj_m2=Decimal("12.000000"),
        provider_code="test",
        source_version="v1",
        available_at=available_at,
        quality_code=None,
        quality_flags=[],
        row_hash=hashlib.sha256(
            f"obs-{available_at.isoformat()}-{observation_date.isoformat()}-t7".encode()
        ).hexdigest(),
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
        parents = await _seed_parents()
        cutoff = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
        node = _make_node(forecast_cutoff_at=cutoff)

        async with AsyncSessionMaker() as session:
            run = await _seed_weather_feature_run(
                session,
                parents=parents,
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
        parents = await _seed_parents()
        cutoff = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
        node = _make_node(forecast_cutoff_at=cutoff)

        async with AsyncSessionMaker() as session:
            run = await _seed_weather_feature_run(
                session,
                parents=parents,
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
        parents = await _seed_parents()
        cutoff = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
        node = _make_node(forecast_cutoff_at=cutoff)

        async with AsyncSessionMaker() as session:
            after = datetime(2026, 3, 15, 12, 0, 0, 1, tzinfo=UTC)
            await _seed_weather_feature_run(
                session,
                parents=parents,
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
        parents = await _seed_parents()
        cutoff = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
        node = _make_node(forecast_cutoff_at=cutoff)

        async with AsyncSessionMaker() as session:
            await _seed_weather_feature_run(
                session,
                parents=parents,
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
        parents = await _seed_parents()
        cutoff = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
        node = _make_node(forecast_cutoff_at=cutoff)

        async with AsyncSessionMaker() as session:
            run = await _seed_weather_feature_run(
                session,
                parents=parents,
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
        parents = await _seed_parents()
        cutoff = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
        node = _make_node(forecast_cutoff_at=cutoff)

        async with AsyncSessionMaker() as session:
            await _seed_weather_feature_run(
                session,
                parents=parents,
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
        parents = await _seed_parents()
        cutoff = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
        node = _make_node(forecast_cutoff_at=cutoff)

        async with AsyncSessionMaker() as session:
            await _seed_weather_feature_run(
                session,
                parents=parents,
                status="failed",
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
        parents = await _seed_parents()
        cutoff = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
        node = _make_node(forecast_cutoff_at=cutoff)

        async with AsyncSessionMaker() as session:
            await _seed_weather_feature_run(
                session,
                parents=parents,
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
        parents = await _seed_parents()
        # UTC 2026-03-15T16:30 → Asia/Shanghai 2026-03-16T00:30 → local date 2026-03-16
        cutoff = datetime(2026, 3, 15, 16, 30, 0, tzinfo=UTC)
        node = _make_node(forecast_cutoff_at=cutoff, node_timezone="Asia/Shanghai")

        async with AsyncSessionMaker() as session:
            mapping = await _seed_location_weather_mapping(
                session,
                parents=parents,
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
        parents = await _seed_parents()
        cutoff = datetime(2026, 3, 15, 16, 30, 0, tzinfo=UTC)
        node = _make_node(forecast_cutoff_at=cutoff, node_timezone="Asia/Shanghai")

        async with AsyncSessionMaker() as session:
            await _seed_location_weather_mapping(
                session,
                parents=parents,
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
        parents = await _seed_parents()
        cutoff = datetime(2026, 3, 16, 2, 0, tzinfo=UTC)  # LA 2026-03-15 19:00
        node = _make_node(
            forecast_cutoff_at=cutoff,
            node_timezone="America/Los_Angeles",
        )

        async with AsyncSessionMaker() as session:
            mapping_15 = await _seed_location_weather_mapping(
                session,
                parents=parents,
                available_at=date(2026, 3, 15),
            )
            await _seed_location_weather_mapping(
                session,
                parents=parents,
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
        parents = await _seed_parents()
        cutoff = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
        node = _make_node(
            forecast_cutoff_at=cutoff,
            forecast_start=date(2026, 3, 16),
            forecast_end=date(2026, 3, 31),
        )

        async with AsyncSessionMaker() as session:
            obs = await _seed_weather_daily_observation(
                session,
                parents=parents,
                available_at=date(2026, 3, 1),
                observation_date=date(2026, 3, 16),
            )
            await session.commit()

            candidates = await _query_task7_weather_daily_observation_candidates(
                session, node, ExecutionMode.HISTORICAL_OBSERVED
            )
            ids = [c.persistent_reference.reference_value for c in candidates]
            assert obs.id in ids

            candidate = next(
                item for item in candidates if item.persistent_reference.reference_value == obs.id
            )
            semantic = candidate.semantic_identity.semantic
            payload = _build_identity_payload(candidate.semantic_identity)

            assert candidate.source_type == AvailabilitySourceType.TASK7_WEATHER_OBSERVATION
            assert candidate.source_role == "task7_weather_observation"
            assert semantic.semantic_payload_hash == obs.row_hash
            assert semantic.canonical_payload_hash == obs.row_hash
            assert semantic.config_hash is None
            assert semantic.business_version == obs.source_version
            assert candidate.canonical_payload_hash == obs.row_hash
            assert candidate.business_version == obs.source_version
            assert candidate.persistent_reference.reference_type == "database_run_id"
            assert candidate.persistent_reference.reference_value == obs.id
            assert payload["semantic_payload_hash"] == obs.row_hash
            assert payload["canonical_payload_hash"] == obs.row_hash
            assert "config_hash" not in payload

    @pytest.mark.asyncio
    async def test_observation_at_forecast_end_included(self) -> None:
        """observation_date == forecast_end → included."""
        parents = await _seed_parents()
        cutoff = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
        node = _make_node(
            forecast_cutoff_at=cutoff,
            forecast_start=date(2026, 3, 16),
            forecast_end=date(2026, 3, 31),
        )

        async with AsyncSessionMaker() as session:
            obs = await _seed_weather_daily_observation(
                session,
                parents=parents,
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
        parents = await _seed_parents()
        cutoff = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
        node = _make_node(
            forecast_cutoff_at=cutoff,
            forecast_start=date(2026, 3, 16),
            forecast_end=date(2026, 3, 31),
        )

        async with AsyncSessionMaker() as session:
            await _seed_weather_daily_observation(
                session,
                parents=parents,
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
        parents = await _seed_parents()
        cutoff = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
        node = _make_node(
            forecast_cutoff_at=cutoff,
            forecast_start=date(2026, 3, 16),
            forecast_end=date(2026, 3, 31),
        )

        async with AsyncSessionMaker() as session:
            await _seed_weather_daily_observation(
                session,
                parents=parents,
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
        parents = await _seed_parents()
        cutoff = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
        node = _make_node(
            forecast_cutoff_at=cutoff,
            forecast_start=date(2026, 3, 16),
            forecast_end=date(2026, 3, 31),
        )

        async with AsyncSessionMaker() as session:
            await _seed_weather_daily_observation(
                session,
                parents=parents,
                available_at=date(2026, 3, 20),
                observation_date=date(2026, 3, 16),
            )
            await session.commit()

            candidates = await _query_task7_weather_daily_observation_candidates(
                session, node, ExecutionMode.HISTORICAL_OBSERVED
            )
            assert len(candidates) == 0
