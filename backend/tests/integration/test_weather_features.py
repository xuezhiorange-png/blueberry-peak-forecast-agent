from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from backend.app.db.session import AsyncSessionMaker
from backend.app.main import create_app
from backend.app.models.master_data import Farm, Season, Variety
from backend.app.models.planning import AgroClimateZone, LocationReference
from backend.app.models.production_plan import FarmSeasonVarietyPlan
from backend.app.models.weather import (
    BaseTemperatureSearchRun,
    LocationWeatherMapping,
    WeatherDailyObservation,
    WeatherFeatureRun,
    WeatherSourceLocation,
)
from backend.app.planning.plan_config import ProductionPlanConfig, load_production_plan_config
from backend.app.weather.config import WeatherFeatureConfig, load_weather_feature_config
from backend.app.weather.repository import get_base_temperature_search_run, get_weather_feature_run
from backend.app.weather.schemas import (
    BaseTemperatureCandidateScore,
    BaseTemperatureTrainingSample,
    PhenologyTimeline,
    WeatherWindowFeature,
)
from backend.app.weather.service import (
    BaseTemperatureSearchUnavailableError,
    compute_weather_window_features,
    get_effective_weather_observations,
    import_weather_locations,
    import_weather_observations,
    resolve_weather_mapping,
    search_base_temperature,
)

pytestmark = pytest.mark.integration


def _require_postgres() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("set RUN_POSTGRES_INTEGRATION=1 when PostgreSQL is available")


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    _require_postgres()
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


def _weather_config() -> WeatherFeatureConfig:
    return load_weather_feature_config(Path("configs/weather_features.yaml"))


def _plan_config() -> ProductionPlanConfig:
    return load_production_plan_config(Path("configs/production_plan.yaml"))


def _write(path: Path, lines: list[str]) -> Path:
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


async def _seed_dimensions() -> dict[str, Any]:
    async with AsyncSessionMaker() as session:
        season_a = Season(code="2024-2025", start_date=date(2025, 1, 1), end_date=date(2025, 4, 30))
        season_b = Season(code="2025-2026", start_date=date(2026, 1, 1), end_date=date(2026, 4, 30))
        season_c = Season(code="2026-2027", start_date=date(2027, 1, 1), end_date=date(2027, 4, 30))
        farm = Farm(
            name="Farm A",
            latitude=Decimal("24.000000"),
            longitude=Decimal("102.000000"),
            altitude_m=Decimal("1800.00"),
        )
        variety = Variety(code="DX", name="Dx")
        session.add_all([season_a, season_b, season_c, farm, variety])
        await session.flush()
        zone = AgroClimateZone(
            code="ZONE-A",
            name="Zone A",
            country="CN",
            province="Yunnan",
            prefecture="Honghe",
            county="Mile",
            centroid_latitude=Decimal("24.010000"),
            centroid_longitude=Decimal("102.010000"),
            min_altitude_m=Decimal("1700"),
            max_altitude_m=Decimal("1900"),
            zone_version="zone-v1",
            valid_from=date(2024, 1, 1),
            valid_to=None,
            source_name="synthetic",
            source_version="zone-v1",
        )
        session.add(zone)
        await session.flush()
        location_reference = LocationReference(
            farm_id=farm.id,
            subfarm_id=None,
            farm_code="FARM-A",
            farm_name=farm.name,
            subfarm_name=None,
            address_raw="Farm A",
            address_normalized="farm a",
            province="Yunnan",
            prefecture="Honghe",
            county="Mile",
            township="Xisan",
            village=None,
            latitude=Decimal("24.000000"),
            longitude=Decimal("102.000000"),
            altitude_m=Decimal("1800.00"),
            climate_zone_id=zone.id,
            location_source="synthetic",
            source_version="loc-v1",
            valid_from=date(2024, 1, 1),
            valid_to=None,
            source_row_hash="loc-row-hash",
        )
        source_location = WeatherSourceLocation(
            provider_code="synthetic_station",
            external_location_id="station-001",
            location_type="station",
            name="Station 001",
            latitude=Decimal("24.020000"),
            longitude=Decimal("102.020000"),
            altitude_m=Decimal("1810.00"),
            timezone_name="Asia/Shanghai",
            grid_resolution=None,
            source_version="dataset-v1",
            valid_from=date(2024, 1, 1),
            valid_to=None,
            row_hash="src-row-hash",
        )
        session.add_all([location_reference, source_location])
        await session.commit()
        return {
            "season_ids": {
                season_a.code: season_a.id,
                season_b.code: season_b.id,
                season_c.code: season_c.id,
            },
            "farm_id": farm.id,
            "variety_id": variety.id,
            "zone_id": zone.id,
            "location_reference_id": location_reference.id,
            "weather_source_location_id": source_location.id,
        }


async def _seed_plan(
    *,
    season_id: int,
    farm_id: int,
    variety_id: int,
    version: int,
    flowering_start_date: date,
    first_pick_date: date,
) -> int:
    async with AsyncSessionMaker() as session:
        plan = FarmSeasonVarietyPlan(
            farm_id=farm_id,
            subfarm_id=None,
            season_id=season_id,
            variety_id=variety_id,
            planted_area_mu=Decimal("100"),
            expected_yield_kg_per_mu=Decimal("1000"),
            marketable_rate=Decimal("0.7"),
            tree_age_years=Decimal("3"),
            pruning_date=flowering_start_date - timedelta(days=20),
            flowering_start_date=flowering_start_date,
            flowering_peak_date=flowering_start_date + timedelta(days=5),
            flowering_end_date=flowering_start_date + timedelta(days=10),
            first_pick_date=first_pick_date,
            expected_total_marketable_kg=Decimal("70000"),
            version=version,
            effective_from=flowering_start_date - timedelta(days=10),
            effective_to=None,
            available_at=flowering_start_date - timedelta(days=15),
            source_type="manual",
            source_name="planner",
            source_version="v1",
            notes="synthetic",
            row_hash=f"plan-{season_id}-{version}",
        )
        session.add(plan)
        await session.commit()
        return plan.id


async def _seed_weather_days(
    *,
    weather_source_location_id: int,
    start_date: date,
    days: int,
    source_version: str,
    mean_c: Decimal = Decimal("10"),
) -> None:
    async with AsyncSessionMaker() as session:
        for offset in range(days):
            day = start_date + timedelta(days=offset)
            session.add(
                WeatherDailyObservation(
                    weather_source_location_id=weather_source_location_id,
                    observation_date=day,
                    temperature_min_c=mean_c - Decimal("5"),
                    temperature_max_c=mean_c + Decimal("5"),
                    temperature_mean_c=mean_c,
                    temperature_mean_source="provided",
                    precipitation_mm=Decimal("1") if offset % 3 == 0 else Decimal("0"),
                    solar_radiation_mj_m2=Decimal("12"),
                    provider_code="synthetic_station",
                    source_version=source_version,
                    available_at=day + timedelta(days=1),
                    quality_code="ok",
                    quality_flags=["ok"],
                    source_file_sha256=None,
                    source_row_number=None,
                    row_hash=f"obs-{source_version}-{day.isoformat()}",
                )
            )
        await session.commit()


async def _seed_weather_revision(
    *,
    weather_source_location_id: int,
    observation_date: date,
    source_version: str,
    available_at: date,
    mean_c: Decimal,
) -> int:
    async with AsyncSessionMaker() as session:
        row = WeatherDailyObservation(
            weather_source_location_id=weather_source_location_id,
            observation_date=observation_date,
            temperature_min_c=mean_c - Decimal("5"),
            temperature_max_c=mean_c + Decimal("5"),
            temperature_mean_c=mean_c,
            temperature_mean_source="provided",
            precipitation_mm=Decimal("0"),
            solar_radiation_mj_m2=Decimal("12"),
            provider_code="synthetic_station",
            source_version=source_version,
            available_at=available_at,
            quality_code="ok",
            quality_flags=["ok"],
            source_file_sha256=None,
            source_row_number=None,
            row_hash=f"obs-{source_version}-{observation_date.isoformat()}-{available_at.isoformat()}",
        )
        session.add(row)
        await session.commit()
        return row.id


async def _seed_base_temperature_search_run(
    *,
    variety_id: int,
    climate_zone_id: int,
    selected_base_temperature: Decimal | None = Decimal("5"),
    status: str = "completed",
    source_signature: str = "base-temp-signature",
    feature_version: str = "task7-v1",
    config_hash: str | None = None,
    error_message: str | None = None,
) -> int:
    config = _weather_config()
    async with AsyncSessionMaker() as session:
        run = BaseTemperatureSearchRun(
            scope_type="variety_zone",
            variety_id=variety_id,
            climate_zone_id=climate_zone_id,
            training_cutoff=date(2027, 5, 1),
            anchor_event="flowering_start_date",
            target_event="first_pick_date",
            candidate_temperatures=["0", "1", "2", "3", "4", "5", "6", "7"],
            selected_base_temperature=selected_base_temperature,
            scoring_method=config.rules.search.scoring_method,
            selected_score=Decimal("0.000000") if selected_base_temperature is not None else None,
            sample_count=3,
            distinct_season_count=3,
            training_sample_ids=[1, 2, 3],
            candidate_scores={
                "candidates": [
                    {
                        "base_temperature": "5",
                        "fold_count": 3,
                        "evaluated_sample_count": 3,
                        "mae_days": "0.000000",
                        "warnings": [],
                    }
                ]
            },
            config_hash=config_hash or config.config_hash,
            feature_version=feature_version,
            source_signature=source_signature,
            status=status,
            warnings=[],
            blockers=[],
            input_snapshot={
                "training_cutoff": "2027-05-01",
                "scope_type": "variety_zone",
                "variety_id": variety_id,
                "climate_zone_id": climate_zone_id,
                "samples": [],
            },
            finished_at=None if status == "running" else datetime.now(UTC),
            error_message=error_message,
        )
        session.add(run)
        await session.commit()
        return run.id


async def test_weather_imports_are_idempotent_and_history_respects_as_of_date(
    tmp_path: Path,
) -> None:
    _require_postgres()
    location_csv = _write(
        tmp_path / "weather_source_locations.csv",
        [
            "provider_code,external_location_id,location_type,name,latitude,longitude,altitude_m,timezone_name,grid_resolution,valid_from,valid_to,source_version,quality_flags",
            (
                "ignored,station-001,station,Station 001,24.020000,102.020000,"
                "1810,Asia/Shanghai,,2024-01-01,,dataset-v1,ok"
            ),
        ],
    )
    observation_csv_v1 = _write(
        tmp_path / "weather_daily_observations_v1.csv",
        [
            "provider_code,external_location_id,observation_date,temperature_min_c,temperature_max_c,temperature_mean_c,precipitation_mm,solar_radiation_mj_m2,available_at,quality_code,quality_flags,source_version",
            "ignored,station-001,2026-02-01,8,18,13,0,12,2026-02-02,ok,ok,dataset-v1",
        ],
    )
    observation_csv_v2 = _write(
        tmp_path / "weather_daily_observations_v2.csv",
        [
            "provider_code,external_location_id,observation_date,temperature_min_c,temperature_max_c,temperature_mean_c,precipitation_mm,solar_radiation_mj_m2,available_at,quality_code,quality_flags,source_version",
            "ignored,station-001,2026-02-01,8,18,14,0,12,2026-02-05,ok,ok,dataset-v2",
        ],
    )

    async with AsyncSessionMaker() as session:
        first = await import_weather_locations(
            session,
            file_path=location_csv,
            provider_code="synthetic_station",
            dataset_version="dataset-v1",
            location_type="station",
            dry_run=False,
        )
        second = await import_weather_locations(
            session,
            file_path=location_csv,
            provider_code="synthetic_station",
            dataset_version="dataset-v1",
            location_type="station",
            dry_run=False,
        )
        assert first["status"] == "completed"
        assert first["inserted_count"] == 1
        assert second["skipped_count"] == 1

        imported_v1 = await import_weather_observations(
            session,
            file_path=observation_csv_v1,
            provider_code="synthetic_station",
            dataset_version="dataset-v1",
            location_type="station",
            dry_run=False,
        )
        imported_v2 = await import_weather_observations(
            session,
            file_path=observation_csv_v2,
            provider_code="synthetic_station",
            dataset_version="dataset-v2",
            location_type="station",
            dry_run=False,
        )
        assert imported_v1["inserted_count"] == 1
        assert imported_v2["inserted_count"] == 1

        source_location = await session.scalar(select(WeatherSourceLocation))
        assert source_location is not None

        old_visible = await get_effective_weather_observations(
            session,
            weather_source_location_id=source_location.id,
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 1),
            feature_date=date(2026, 2, 1),
            as_of_date=date(2026, 2, 3),
        )
        new_visible = await get_effective_weather_observations(
            session,
            weather_source_location_id=source_location.id,
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 1),
            feature_date=date(2026, 2, 1),
            as_of_date=date(2026, 2, 6),
        )

    assert old_visible[0].temperature_mean_c == Decimal("13")
    assert new_visible[0].temperature_mean_c == Decimal("14")


async def test_compute_weather_features_persists_and_skips_rehydrated_result() -> None:
    _require_postgres()
    ids = await _seed_dimensions()
    plan_id = await _seed_plan(
        season_id=ids["season_ids"]["2025-2026"],
        farm_id=ids["farm_id"],
        variety_id=ids["variety_id"],
        version=1,
        flowering_start_date=date(2026, 1, 5),
        first_pick_date=date(2026, 1, 20),
    )
    await _seed_weather_days(
        weather_source_location_id=ids["weather_source_location_id"],
        start_date=date(2026, 1, 1),
        days=21,
        source_version="dataset-v1",
    )
    base_temperature_run_id = await _seed_base_temperature_search_run(
        variety_id=ids["variety_id"],
        climate_zone_id=ids["zone_id"],
    )

    async with AsyncSessionMaker() as session:
        first = await compute_weather_window_features(
            session,
            farm_id=ids["farm_id"],
            subfarm_id=None,
            season_id=ids["season_ids"]["2025-2026"],
            variety_id=ids["variety_id"],
            as_of_date=date(2026, 1, 25),
            feature_date=date(2026, 1, 21),
            config=_weather_config(),
            production_plan_config=_plan_config(),
            base_temperature_search_run_id=base_temperature_run_id,
            anchor_event="flowering_start_date",
            dry_run=False,
        )
        second = await compute_weather_window_features(
            session,
            farm_id=ids["farm_id"],
            subfarm_id=None,
            season_id=ids["season_ids"]["2025-2026"],
            variety_id=ids["variety_id"],
            as_of_date=date(2026, 1, 25),
            feature_date=date(2026, 1, 21),
            config=_weather_config(),
            production_plan_config=_plan_config(),
            base_temperature_search_run_id=base_temperature_run_id,
            anchor_event="flowering_start_date",
            dry_run=False,
        )
        run = await get_weather_feature_run(session, run_id=first.run_id or 0)
        mapping_count = await session.scalar(select(func.count(LocationWeatherMapping.id)))

    assert plan_id > 0
    assert first.status == "completed"
    assert second.status == "skipped"
    assert isinstance(first.windows, tuple)
    assert isinstance(first.windows[0], WeatherWindowFeature)
    assert isinstance(first.timeline, PhenologyTimeline)
    assert first.windows[0].status == "available"
    assert isinstance(second.windows, tuple)
    assert isinstance(second.windows[0], WeatherWindowFeature)
    assert isinstance(second.timeline, PhenologyTimeline)
    assert len(first.windows) == 3
    assert second.windows == first.windows
    assert second.timeline == first.timeline
    assert type(first.windows[0]) is type(second.windows[0])
    assert type(first.timeline) is type(second.timeline)
    for first_window, second_window in zip(first.windows, second.windows, strict=True):
        assert first_window.window_days == second_window.window_days
        assert first_window.status == second_window.status
        assert first_window.coverage_ratio == second_window.coverage_ratio
        assert first_window.source_observation_ids == second_window.source_observation_ids
    assert first.timeline.plan_id == second.timeline.plan_id
    assert first.timeline.plan_version == second.timeline.plan_version
    assert (
        first.timeline.cumulative_effective_temperature
        == second.timeline.cumulative_effective_temperature
    )
    assert run is not None
    assert run.status == "completed"
    assert mapping_count == 1


async def test_compute_weather_features_requires_base_temperature_search_run() -> None:
    _require_postgres()
    ids = await _seed_dimensions()
    await _seed_plan(
        season_id=ids["season_ids"]["2025-2026"],
        farm_id=ids["farm_id"],
        variety_id=ids["variety_id"],
        version=1,
        flowering_start_date=date(2026, 1, 5),
        first_pick_date=date(2026, 1, 20),
    )
    await _seed_weather_days(
        weather_source_location_id=ids["weather_source_location_id"],
        start_date=date(2026, 1, 1),
        days=21,
        source_version="dataset-v1",
    )

    async with AsyncSessionMaker() as session:
        result = await compute_weather_window_features(
            session,
            farm_id=ids["farm_id"],
            subfarm_id=None,
            season_id=ids["season_ids"]["2025-2026"],
            variety_id=ids["variety_id"],
            as_of_date=date(2026, 1, 25),
            feature_date=date(2026, 1, 21),
            config=_weather_config(),
            production_plan_config=_plan_config(),
            base_temperature_search_run_id=None,
            anchor_event="flowering_start_date",
            dry_run=False,
        )
        run = await get_weather_feature_run(session, run_id=result.run_id or 0)

    assert result.status == "unavailable"
    assert result.run_id is not None
    assert "base_temperature_search_required" in result.blockers
    assert all(window.effective_temperature_sum is None for window in result.windows)
    assert result.timeline.cumulative_effective_temperature is None
    assert run is not None
    assert run.status == "unavailable"


async def test_compute_weather_features_rejects_incompatible_base_temperature_run() -> None:
    _require_postgres()
    ids = await _seed_dimensions()
    await _seed_plan(
        season_id=ids["season_ids"]["2025-2026"],
        farm_id=ids["farm_id"],
        variety_id=ids["variety_id"],
        version=1,
        flowering_start_date=date(2026, 1, 5),
        first_pick_date=date(2026, 1, 20),
    )
    await _seed_weather_days(
        weather_source_location_id=ids["weather_source_location_id"],
        start_date=date(2026, 1, 1),
        days=21,
        source_version="dataset-v1",
    )
    failed_run_id = await _seed_base_temperature_search_run(
        variety_id=ids["variety_id"],
        climate_zone_id=ids["zone_id"],
        status="failed",
        selected_base_temperature=None,
        source_signature="failed-search-run",
        error_message="search failed",
    )

    async with AsyncSessionMaker() as session:
        with pytest.raises(
            BaseTemperatureSearchUnavailableError,
            match="not completed: failed",
        ):
            await compute_weather_window_features(
                session,
                farm_id=ids["farm_id"],
                subfarm_id=None,
                season_id=ids["season_ids"]["2025-2026"],
                variety_id=ids["variety_id"],
                as_of_date=date(2026, 1, 25),
                feature_date=date(2026, 1, 21),
                config=_weather_config(),
                production_plan_config=_plan_config(),
                base_temperature_search_run_id=failed_run_id,
                anchor_event="flowering_start_date",
                dry_run=False,
            )


async def test_base_temperature_search_persists_result_and_is_idempotent() -> None:
    _require_postgres()
    ids = await _seed_dimensions()
    plan_ids = [
        await _seed_plan(
            season_id=ids["season_ids"]["2024-2025"],
            farm_id=ids["farm_id"],
            variety_id=ids["variety_id"],
            version=1,
            flowering_start_date=date(2025, 1, 5),
            first_pick_date=date(2025, 1, 10),
        ),
        await _seed_plan(
            season_id=ids["season_ids"]["2025-2026"],
            farm_id=ids["farm_id"],
            variety_id=ids["variety_id"],
            version=1,
            flowering_start_date=date(2026, 1, 5),
            first_pick_date=date(2026, 1, 10),
        ),
        await _seed_plan(
            season_id=ids["season_ids"]["2026-2027"],
            farm_id=ids["farm_id"],
            variety_id=ids["variety_id"],
            version=1,
            flowering_start_date=date(2027, 1, 5),
            first_pick_date=date(2027, 1, 10),
        ),
    ]
    await _seed_weather_days(
        weather_source_location_id=ids["weather_source_location_id"],
        start_date=date(2025, 1, 5),
        days=116,
        source_version="dataset-v1",
    )
    await _seed_weather_days(
        weather_source_location_id=ids["weather_source_location_id"],
        start_date=date(2026, 1, 5),
        days=116,
        source_version="dataset-v1-2026",
    )
    await _seed_weather_days(
        weather_source_location_id=ids["weather_source_location_id"],
        start_date=date(2027, 1, 5),
        days=116,
        source_version="dataset-v1-2027",
    )
    samples = [
        BaseTemperatureTrainingSample(
            plan_id=plan_id,
            anchor_event="flowering_start_date",
            target_event="first_pick_date",
            sample_weight=Decimal("1"),
            include=True,
            exclusion_reason=None,
        )
        for plan_id in plan_ids
    ]

    async with AsyncSessionMaker() as session:
        first = await search_base_temperature(
            session,
            training_cutoff=date(2027, 5, 1),
            samples=samples,
            config=_weather_config(),
            variety_id=ids["variety_id"],
            climate_zone_id=ids["zone_id"],
            scope_type="variety_zone",
            dry_run=False,
        )
        second = await search_base_temperature(
            session,
            training_cutoff=date(2027, 5, 1),
            samples=samples,
            config=_weather_config(),
            variety_id=ids["variety_id"],
            climate_zone_id=ids["zone_id"],
            scope_type="variety_zone",
            dry_run=False,
        )
        run = await get_base_temperature_search_run(session, run_id=first.run_id or 0)
        stored = await session.get(BaseTemperatureSearchRun, first.run_id)

    assert first.status == "completed"
    assert first.selected_base_temperature is not None
    assert len(first.candidate_scores) == 8
    assert first.run_id is not None
    assert isinstance(first.candidate_scores[0], BaseTemperatureCandidateScore)
    assert isinstance(first.candidate_scores[0].base_temperature, Decimal)
    assert second.status == "skipped"
    assert second.run_id == first.run_id
    assert second.selected_base_temperature == first.selected_base_temperature
    assert run is not None
    assert run.status == "completed"
    assert stored is not None
    assert isinstance(stored.candidate_scores["candidates"][0]["base_temperature"], str)
    assert isinstance(stored.candidate_scores["candidates"][0]["mae_days"], str)
    assert isinstance(second.candidate_scores[0], BaseTemperatureCandidateScore)
    assert isinstance(second.candidate_scores[0].base_temperature, Decimal)
    assert second.candidate_scores == first.candidate_scores
    assert second.selected_score == first.selected_score


async def test_weather_feature_signature_tracks_visible_weather_revisions() -> None:
    _require_postgres()
    ids = await _seed_dimensions()
    await _seed_plan(
        season_id=ids["season_ids"]["2025-2026"],
        farm_id=ids["farm_id"],
        variety_id=ids["variety_id"],
        version=1,
        flowering_start_date=date(2026, 1, 5),
        first_pick_date=date(2026, 1, 20),
    )
    await _seed_weather_days(
        weather_source_location_id=ids["weather_source_location_id"],
        start_date=date(2026, 1, 1),
        days=21,
        source_version="dataset-v1",
        mean_c=Decimal("10"),
    )
    base_temperature_run_id = await _seed_base_temperature_search_run(
        variety_id=ids["variety_id"],
        climate_zone_id=ids["zone_id"],
        source_signature="bt-source-v1",
    )

    async with AsyncSessionMaker() as session:
        first = await compute_weather_window_features(
            session,
            farm_id=ids["farm_id"],
            subfarm_id=None,
            season_id=ids["season_ids"]["2025-2026"],
            variety_id=ids["variety_id"],
            as_of_date=date(2026, 1, 25),
            feature_date=date(2026, 1, 21),
            config=_weather_config(),
            production_plan_config=_plan_config(),
            base_temperature_search_run_id=base_temperature_run_id,
            anchor_event="flowering_start_date",
            dry_run=False,
        )

    revised_visible_id = await _seed_weather_revision(
        weather_source_location_id=ids["weather_source_location_id"],
        observation_date=date(2026, 1, 21),
        source_version="dataset-v2",
        available_at=date(2026, 1, 24),
        mean_c=Decimal("14"),
    )

    async with AsyncSessionMaker() as session:
        second = await compute_weather_window_features(
            session,
            farm_id=ids["farm_id"],
            subfarm_id=None,
            season_id=ids["season_ids"]["2025-2026"],
            variety_id=ids["variety_id"],
            as_of_date=date(2026, 1, 25),
            feature_date=date(2026, 1, 21),
            config=_weather_config(),
            production_plan_config=_plan_config(),
            base_temperature_search_run_id=base_temperature_run_id,
            anchor_event="flowering_start_date",
            dry_run=False,
        )
        first_run = await session.get(WeatherFeatureRun, first.run_id)
        second_run = await session.get(WeatherFeatureRun, second.run_id)

    assert first.status == "completed"
    assert second.status == "completed"
    assert first.run_id != second.run_id
    assert first.source_signature != second.source_signature
    assert revised_visible_id in second.weather_observation_ids
    assert second.windows[0].effective_temperature_sum != first.windows[0].effective_temperature_sum
    assert first_run is not None
    assert second_run is not None
    assert first_run.source_signature == first.source_signature
    assert second_run.source_signature == second.source_signature

    await _seed_weather_revision(
        weather_source_location_id=ids["weather_source_location_id"],
        observation_date=date(2026, 1, 21),
        source_version="dataset-v3",
        available_at=date(2026, 1, 30),
        mean_c=Decimal("18"),
    )

    async with AsyncSessionMaker() as session:
        third = await compute_weather_window_features(
            session,
            farm_id=ids["farm_id"],
            subfarm_id=None,
            season_id=ids["season_ids"]["2025-2026"],
            variety_id=ids["variety_id"],
            as_of_date=date(2026, 1, 25),
            feature_date=date(2026, 1, 21),
            config=_weather_config(),
            production_plan_config=_plan_config(),
            base_temperature_search_run_id=base_temperature_run_id,
            anchor_event="flowering_start_date",
            dry_run=False,
        )

    assert third.status == "skipped"
    assert third.run_id == second.run_id
    assert third.source_signature == second.source_signature
    assert third.windows == second.windows


async def test_base_temperature_search_signature_tracks_manifest_and_visible_weather() -> None:
    _require_postgres()
    ids = await _seed_dimensions()
    base_plans = [
        await _seed_plan(
            season_id=ids["season_ids"]["2024-2025"],
            farm_id=ids["farm_id"],
            variety_id=ids["variety_id"],
            version=1,
            flowering_start_date=date(2025, 1, 5),
            first_pick_date=date(2025, 1, 10),
        ),
        await _seed_plan(
            season_id=ids["season_ids"]["2025-2026"],
            farm_id=ids["farm_id"],
            variety_id=ids["variety_id"],
            version=1,
            flowering_start_date=date(2026, 1, 5),
            first_pick_date=date(2026, 1, 10),
        ),
        await _seed_plan(
            season_id=ids["season_ids"]["2026-2027"],
            farm_id=ids["farm_id"],
            variety_id=ids["variety_id"],
            version=1,
            flowering_start_date=date(2027, 1, 5),
            first_pick_date=date(2027, 1, 10),
        ),
    ]
    await _seed_weather_days(
        weather_source_location_id=ids["weather_source_location_id"],
        start_date=date(2025, 1, 5),
        days=116,
        source_version="dataset-v1",
    )
    await _seed_weather_days(
        weather_source_location_id=ids["weather_source_location_id"],
        start_date=date(2026, 1, 5),
        days=116,
        source_version="dataset-v1-2026",
    )
    await _seed_weather_days(
        weather_source_location_id=ids["weather_source_location_id"],
        start_date=date(2027, 1, 5),
        days=116,
        source_version="dataset-v1-2027",
    )

    def base_samples() -> list[BaseTemperatureTrainingSample]:
        return [
            BaseTemperatureTrainingSample(
                plan_id=plan_id,
                anchor_event="flowering_start_date",
                target_event="first_pick_date",
                sample_weight=Decimal("1"),
                include=True,
                exclusion_reason=None,
            )
            for plan_id in base_plans
        ]

    async with AsyncSessionMaker() as session:
        first = await search_base_temperature(
            session,
            training_cutoff=date(2027, 5, 1),
            samples=base_samples(),
            config=_weather_config(),
            variety_id=ids["variety_id"],
            climate_zone_id=ids["zone_id"],
            scope_type="variety_zone",
            dry_run=False,
        )
        second = await search_base_temperature(
            session,
            training_cutoff=date(2027, 5, 1),
            samples=base_samples(),
            config=_weather_config(),
            variety_id=ids["variety_id"],
            climate_zone_id=ids["zone_id"],
            scope_type="variety_zone",
            dry_run=False,
        )

    assert second.status == "skipped"
    assert second.run_id == first.run_id

    weighted_samples = base_samples()
    weighted_samples[0] = BaseTemperatureTrainingSample(
        plan_id=weighted_samples[0].plan_id,
        anchor_event=weighted_samples[0].anchor_event,
        target_event=weighted_samples[0].target_event,
        sample_weight=Decimal("2"),
        include=True,
        exclusion_reason=None,
    )
    async with AsyncSessionMaker() as session:
        weighted = await search_base_temperature(
            session,
            training_cutoff=date(2027, 5, 1),
            samples=weighted_samples,
            config=_weather_config(),
            variety_id=ids["variety_id"],
            climate_zone_id=ids["zone_id"],
            scope_type="variety_zone",
            dry_run=False,
        )
    assert weighted.status == "completed"
    assert weighted.run_id != first.run_id
    assert weighted.source_signature != first.source_signature

    anchor_changed = base_samples()
    anchor_changed[0] = BaseTemperatureTrainingSample(
        plan_id=anchor_changed[0].plan_id,
        anchor_event="flowering_peak_date",
        target_event=anchor_changed[0].target_event,
        sample_weight=Decimal("1"),
        include=True,
        exclusion_reason=None,
    )
    async with AsyncSessionMaker() as session:
        changed_anchor = await search_base_temperature(
            session,
            training_cutoff=date(2027, 5, 1),
            samples=anchor_changed,
            config=_weather_config(),
            variety_id=ids["variety_id"],
            climate_zone_id=ids["zone_id"],
            scope_type="variety_zone",
            dry_run=False,
        )
    assert changed_anchor.run_id != first.run_id
    assert changed_anchor.source_signature != first.source_signature

    target_changed = base_samples()
    target_changed[0] = BaseTemperatureTrainingSample(
        plan_id=target_changed[0].plan_id,
        anchor_event=target_changed[0].anchor_event,
        target_event="flowering_end_date",
        sample_weight=Decimal("1"),
        include=True,
        exclusion_reason=None,
    )
    async with AsyncSessionMaker() as session:
        changed_target = await search_base_temperature(
            session,
            training_cutoff=date(2027, 5, 1),
            samples=target_changed,
            config=_weather_config(),
            variety_id=ids["variety_id"],
            climate_zone_id=ids["zone_id"],
            scope_type="variety_zone",
            dry_run=False,
        )
    assert changed_target.run_id != first.run_id
    assert changed_target.source_signature != first.source_signature

    include_changed = base_samples()
    include_changed[0] = BaseTemperatureTrainingSample(
        plan_id=include_changed[0].plan_id,
        anchor_event=include_changed[0].anchor_event,
        target_event=include_changed[0].target_event,
        sample_weight=Decimal("1"),
        include=False,
        exclusion_reason="manual_exclude",
    )
    async with AsyncSessionMaker() as session:
        changed_include = await search_base_temperature(
            session,
            training_cutoff=date(2027, 5, 1),
            samples=include_changed,
            config=_weather_config(),
            variety_id=ids["variety_id"],
            climate_zone_id=ids["zone_id"],
            scope_type="variety_zone",
            dry_run=False,
        )
    assert changed_include.run_id != first.run_id
    assert changed_include.source_signature != first.source_signature

    await _seed_weather_revision(
        weather_source_location_id=ids["weather_source_location_id"],
        observation_date=date(2027, 1, 9),
        source_version="dataset-v2-2027",
        available_at=date(2027, 1, 10),
        mean_c=Decimal("15"),
    )
    async with AsyncSessionMaker() as session:
        revised_weather = await search_base_temperature(
            session,
            training_cutoff=date(2027, 5, 1),
            samples=base_samples(),
            config=_weather_config(),
            variety_id=ids["variety_id"],
            climate_zone_id=ids["zone_id"],
            scope_type="variety_zone",
            dry_run=False,
        )
    assert revised_weather.run_id != first.run_id
    assert revised_weather.source_signature != first.source_signature

    replacement_plan_id = await _seed_plan(
        season_id=ids["season_ids"]["2026-2027"],
        farm_id=ids["farm_id"],
        variety_id=ids["variety_id"],
        version=2,
        flowering_start_date=date(2027, 1, 6),
        first_pick_date=date(2027, 1, 11),
    )
    changed_plan = base_samples()
    changed_plan[2] = BaseTemperatureTrainingSample(
        plan_id=replacement_plan_id,
        anchor_event="flowering_start_date",
        target_event="first_pick_date",
        sample_weight=Decimal("1"),
        include=True,
        exclusion_reason=None,
    )
    async with AsyncSessionMaker() as session:
        replaced_plan = await search_base_temperature(
            session,
            training_cutoff=date(2027, 5, 1),
            samples=changed_plan,
            config=_weather_config(),
            variety_id=ids["variety_id"],
            climate_zone_id=ids["zone_id"],
            scope_type="variety_zone",
            dry_run=False,
        )
    assert replaced_plan.run_id != first.run_id
    assert replaced_plan.source_signature != first.source_signature


async def test_weather_feature_api_round_trip(client: AsyncClient) -> None:
    ids = await _seed_dimensions()
    await _seed_plan(
        season_id=ids["season_ids"]["2025-2026"],
        farm_id=ids["farm_id"],
        variety_id=ids["variety_id"],
        version=1,
        flowering_start_date=date(2026, 1, 5),
        first_pick_date=date(2026, 1, 20),
    )
    await _seed_weather_days(
        weather_source_location_id=ids["weather_source_location_id"],
        start_date=date(2026, 1, 1),
        days=21,
        source_version="dataset-v1",
    )
    base_temperature_run_id = await _seed_base_temperature_search_run(
        variety_id=ids["variety_id"],
        climate_zone_id=ids["zone_id"],
    )

    response = await client.post(
        "/planning/weather/features",
        json={
            "farm_id": ids["farm_id"],
            "season_id": ids["season_ids"]["2025-2026"],
            "variety_id": ids["variety_id"],
            "as_of_date": "2026-01-25",
            "feature_date": "2026-01-21",
            "base_temperature_search_run_id": base_temperature_run_id,
            "anchor_event": "flowering_start_date",
            "dry_run": False,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "completed"
    run_id = body["payload"]["run_id"]

    get_response = await client.get(f"/planning/weather/features/{run_id}")
    assert get_response.status_code == 200
    assert (
        get_response.json()["payload"]["timeline"]["plan_id"]
        == body["payload"]["timeline"]["plan_id"]
    )

    history_response = await client.post(
        "/planning/weather/history",
        json={
            "location_reference_id": ids["location_reference_id"],
            "as_of_date": "2026-01-25",
            "start_date": "2026-01-01",
            "end_date": "2026-01-07",
        },
    )
    assert history_response.status_code == 200
    assert len(history_response.json()["payload"]["payload"]["observations"]) == 7

    source_locations_response = await client.get(
        "/planning/weather/source-locations",
        params={"as_of_date": "2026-01-25", "provider_code": "synthetic_station"},
    )
    assert source_locations_response.status_code == 200
    assert len(source_locations_response.json()["payload"]["payload"]["items"]) == 1


async def test_weather_history_unavailable_mapping_does_not_create_feature_run() -> None:
    _require_postgres()
    async with AsyncSessionMaker() as session:
        farm = Farm(name="No Weather Farm")
        variety = Variety(code="D12", name="D12")
        season = Season(code="2028-2029", start_date=date(2028, 1, 1), end_date=date(2028, 4, 30))
        session.add_all([farm, variety, season])
        await session.flush()
        location_reference = LocationReference(
            farm_id=farm.id,
            subfarm_id=None,
            farm_code="FARM-B",
            farm_name=farm.name,
            subfarm_name=None,
            address_raw="Farm B",
            address_normalized="farm b",
            province="Yunnan",
            prefecture="Honghe",
            county="Mile",
            township="Xisan",
            village=None,
            latitude=Decimal("24.100000"),
            longitude=Decimal("102.100000"),
            altitude_m=Decimal("1800.00"),
            climate_zone_id=None,
            location_source="synthetic",
            source_version="loc-v1",
            valid_from=date(2028, 1, 1),
            valid_to=None,
            source_row_hash="loc-row-hash-b",
        )
        plan = FarmSeasonVarietyPlan(
            farm_id=farm.id,
            subfarm_id=None,
            season_id=season.id,
            variety_id=variety.id,
            planted_area_mu=Decimal("100"),
            expected_yield_kg_per_mu=Decimal("1000"),
            marketable_rate=Decimal("0.7"),
            tree_age_years=Decimal("3"),
            pruning_date=date(2027, 12, 20),
            flowering_start_date=date(2028, 1, 5),
            flowering_peak_date=date(2028, 1, 10),
            flowering_end_date=date(2028, 1, 15),
            first_pick_date=date(2028, 1, 20),
            expected_total_marketable_kg=Decimal("70000"),
            version=1,
            effective_from=date(2028, 1, 1),
            effective_to=None,
            available_at=date(2027, 12, 1),
            source_type="manual",
            source_name="planner",
            source_version="v1",
            notes="synthetic",
            row_hash="plan-no-weather",
        )
        session.add_all([location_reference, plan])
        await session.commit()

    async with AsyncSessionMaker() as session:
        result = await compute_weather_window_features(
            session,
            farm_id=farm.id,
            subfarm_id=None,
            season_id=season.id,
            variety_id=variety.id,
            as_of_date=date(2028, 1, 25),
            feature_date=date(2028, 1, 21),
            config=_weather_config(),
            production_plan_config=_plan_config(),
            base_temperature_search_run_id=None,
            anchor_event="flowering_start_date",
            dry_run=False,
        )
        run_count = await session.scalar(select(func.count(WeatherFeatureRun.id)))
    assert result.status == "unavailable"
    assert run_count == 0


async def test_failed_run_api_reports_failed_status(client: AsyncClient) -> None:
    _require_postgres()
    ids = await _seed_dimensions()
    plan_id = await _seed_plan(
        season_id=ids["season_ids"]["2025-2026"],
        farm_id=ids["farm_id"],
        variety_id=ids["variety_id"],
        version=1,
        flowering_start_date=date(2026, 1, 5),
        first_pick_date=date(2026, 1, 20),
    )
    base_temperature_run_id = await _seed_base_temperature_search_run(
        variety_id=ids["variety_id"],
        climate_zone_id=ids["zone_id"],
        status="failed",
        selected_base_temperature=None,
        source_signature="failed-base-temp-run",
        error_message="search failed",
    )

    async with AsyncSessionMaker() as session:
        mapping = await resolve_weather_mapping(
            session,
            location_reference_id=ids["location_reference_id"],
            as_of_date=date(2026, 1, 25),
            config=_weather_config(),
            persist=True,
        )
        assert mapping.mapping_id is not None
        feature_run = WeatherFeatureRun(
            feature_version=_weather_config().rules.features.version,
            config_hash=_weather_config().config_hash,
            mapping_version=mapping.mapping_version,
            weather_source_version="dataset-v1",
            base_temperature_search_run_id=base_temperature_run_id,
            plan_id=plan_id,
            location_reference_id=ids["location_reference_id"],
            location_weather_mapping_id=mapping.mapping_id,
            weather_source_location_id=ids["weather_source_location_id"],
            as_of_date=date(2026, 1, 25),
            feature_date=date(2026, 1, 21),
            source_signature="failed-weather-run",
            status="failed",
            input_snapshot={
                "farm_id": ids["farm_id"],
                "season_id": ids["season_ids"]["2025-2026"],
                "variety_id": ids["variety_id"],
            },
            window_features={"windows": []},
            timeline_payload={
                "plan_id": plan_id,
                "plan_version": 1,
                "pruning_date": None,
                "flowering_start_date": None,
                "flowering_peak_date": None,
                "flowering_end_date": None,
                "first_pick_date": None,
                "days_since_pruning": None,
                "days_since_flowering_start": None,
                "days_since_flowering_peak": None,
                "days_since_flowering_end": None,
                "days_until_first_pick": None,
                "anchor_event": None,
                "anchor_date": None,
                "cumulative_effective_temperature": None,
                "cumulative_expected_day_count": 0,
                "cumulative_observed_day_count": 0,
                "cumulative_coverage_ratio": None,
                "cumulative_missing_dates": [],
                "selected_weather_mapping_id": mapping.mapping_id,
                "weather_feature_version": _weather_config().rules.features.version,
                "warnings": [],
            },
            weather_observation_ids=[],
            warnings=[],
            blockers=["base_temperature_search_required"],
            finished_at=datetime.now(UTC),
            error_message="feature failed",
        )
        session.add(feature_run)
        await session.commit()
        feature_run_id = feature_run.id

    feature_response = await client.get(f"/planning/weather/features/{feature_run_id}")
    assert feature_response.status_code == 200, feature_response.text
    feature_body = feature_response.json()
    assert feature_body["status"] == "failed"
    assert feature_body["payload"]["status"] == "failed"
    assert feature_body["payload"]["error_message"] == "feature failed"

    base_response = await client.get(
        f"/planning/weather/base-temperature-searches/{base_temperature_run_id}"
    )
    assert base_response.status_code == 200, base_response.text
    base_body = base_response.json()
    assert base_body["status"] == "failed"
    assert base_body["payload"]["status"] == "failed"
    assert base_body["payload"]["error_message"] == "search failed"
