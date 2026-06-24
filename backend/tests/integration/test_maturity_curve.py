from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from backend.app.db.session import AsyncSessionMaker
from backend.app.main import create_app
from backend.app.models.analytics import AnalyticsBuildRun, FactReceiptDaily
from backend.app.models.master_data import Factory, Farm, Holiday, Season, Variety
from backend.app.models.maturity import (
    MaturityDailyPredictionModel,
    MaturityForecastRun,
    MaturityModelArtifact,
    MaturityModelRun,
)
from backend.app.models.planning import AgroClimateZone, LocationReference
from backend.app.models.production_plan import FarmSeasonVarietyPlan
from backend.app.models.weather import (
    BaseTemperatureSearchRun,
    LocationWeatherMapping,
    WeatherDailyObservation,
    WeatherSourceLocation,
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


async def _seed_dimensions() -> dict[str, Any]:
    async with AsyncSessionMaker() as session:
        season_1 = Season(code="2024-2025", start_date=date(2025, 1, 1), end_date=date(2025, 4, 30))
        season_2 = Season(code="2025-2026", start_date=date(2026, 1, 1), end_date=date(2026, 4, 30))
        season_3 = Season(code="2026-2027", start_date=date(2027, 1, 1), end_date=date(2027, 4, 30))
        factory = Factory(name="Factory A")
        farm = Farm(
            name="Farm A",
            latitude=Decimal("24.100000"),
            longitude=Decimal("102.100000"),
            altitude_m=Decimal("1800.00"),
        )
        variety = Variety(code="DX", name="Dx")
        zone = AgroClimateZone(
            code="ZONE-A",
            name="Zone A",
            country="CN",
            province="Yunnan",
            prefecture="Honghe",
            county="Mile",
            centroid_latitude=Decimal("24.000000"),
            centroid_longitude=Decimal("102.000000"),
            min_altitude_m=Decimal("1700"),
            max_altitude_m=Decimal("1900"),
            zone_version="zone-v1",
            valid_from=date(2024, 1, 1),
            valid_to=None,
            source_name="synthetic",
            source_version="zone-v1",
        )
        session.add_all([season_1, season_2, season_3, factory, farm, variety, zone])
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
            latitude=Decimal("24.100000"),
            longitude=Decimal("102.100000"),
            altitude_m=Decimal("1800.00"),
            climate_zone_id=zone.id,
            location_source="synthetic",
            source_version="loc-v1",
            valid_from=date(2024, 1, 1),
            valid_to=None,
            source_row_hash="loc-a",
        )
        weather_source = WeatherSourceLocation(
            provider_code="synthetic_station",
            external_location_id="station-1",
            location_type="station",
            name="Station 1",
            latitude=Decimal("24.110000"),
            longitude=Decimal("102.110000"),
            altitude_m=Decimal("1810.00"),
            timezone_name="Asia/Shanghai",
            grid_resolution=None,
            source_version="dataset-v1",
            valid_from=date(2024, 1, 1),
            valid_to=None,
            row_hash="src-a",
        )
        session.add_all([location_reference, weather_source])
        await session.flush()
        holiday = Holiday(
            season_id=season_2.id,
            code="spring_festival",
            name="Spring Festival",
            start_date=date(2026, 2, 10),
            end_date=date(2026, 2, 12),
            region_name=None,
            active=True,
        )
        session.add(holiday)
        await session.commit()
        return {
            "season_ids": {
                season_1.code: season_1.id,
                season_2.code: season_2.id,
                season_3.code: season_3.id,
            },
            "factory_id": factory.id,
            "farm_id": farm.id,
            "variety_id": variety.id,
            "zone_id": zone.id,
            "location_reference_id": location_reference.id,
            "weather_source_location_id": weather_source.id,
        }


async def _seed_plan(
    *,
    season_id: int,
    farm_id: int,
    variety_id: int,
    version: int,
    available_at: date,
) -> int:
    async with AsyncSessionMaker() as session:
        season = await session.get(Season, season_id)
        assert season is not None
        pruning_date = season.start_date
        flowering_start_date = season.start_date + timedelta(days=31)
        flowering_peak_date = season.start_date + timedelta(days=36)
        flowering_end_date = season.start_date + timedelta(days=40)
        first_pick_date = season.start_date + timedelta(days=63)
        plan = FarmSeasonVarietyPlan(
            farm_id=farm_id,
            subfarm_id=None,
            season_id=season_id,
            variety_id=variety_id,
            planted_area_mu=Decimal("100"),
            expected_yield_kg_per_mu=Decimal("1200"),
            marketable_rate=Decimal("0.8"),
            tree_age_years=Decimal("3"),
            pruning_date=pruning_date,
            flowering_start_date=flowering_start_date,
            flowering_peak_date=flowering_peak_date,
            flowering_end_date=flowering_end_date,
            first_pick_date=first_pick_date,
            expected_total_marketable_kg=Decimal("96000"),
            version=version,
            effective_from=season.start_date,
            effective_to=None,
            available_at=available_at,
            source_type="manual",
            source_name="planner",
            source_version="v1",
            notes="synthetic",
            row_hash=f"plan-{season_id}-{version}",
        )
        session.add(plan)
        await session.commit()
        return plan.id


async def _seed_base_temperature_run(*, variety_id: int, climate_zone_id: int) -> int:
    async with AsyncSessionMaker() as session:
        run = BaseTemperatureSearchRun(
            scope_type="variety_zone",
            variety_id=variety_id,
            climate_zone_id=climate_zone_id,
            training_cutoff=date(2026, 4, 30),
            anchor_event="flowering_start_date",
            target_event="first_pick_date",
            candidate_temperatures=["3", "5"],
            selected_base_temperature=Decimal("5"),
            scoring_method="season_loso_mae_days",
            selected_score=Decimal("1.000000"),
            sample_count=3,
            distinct_season_count=3,
            training_sample_ids=[1, 2, 3],
            candidate_scores={"candidates": []},
            config_hash="weather-cfg",
            feature_version="task7-v1",
            source_signature="base-temp-sig",
            status="completed",
            warnings=[],
            blockers=[],
            input_snapshot={"samples": []},
        )
        session.add(run)
        await session.commit()
        return run.id


async def _seed_mapping(
    *,
    location_reference_id: int,
    weather_source_location_id: int,
) -> int:
    async with AsyncSessionMaker() as session:
        row = LocationWeatherMapping(
            location_reference_id=location_reference_id,
            weather_source_location_id=weather_source_location_id,
            mapping_method="explicit",
            distance_km=Decimal("1"),
            altitude_difference_m=Decimal("10"),
            mapping_score=Decimal("1"),
            confidence_level="high",
            mapping_version="map-v1",
            config_hash="weather-cfg",
            available_at=date(2026, 1, 1),
            valid_from=date(2026, 1, 1),
            valid_to=None,
            row_hash="mapping-a",
        )
        session.add(row)
        await session.commit()
        return row.id


async def _seed_analytics_sample(
    *,
    season_id: int,
    factory_id: int,
    variety_id: int,
    farm_key: str,
    subfarm_key: str,
    daily_weights: list[Decimal],
) -> int:
    async with AsyncSessionMaker() as session:
        season = await session.get(Season, season_id)
        assert season is not None
        build_run = AnalyticsBuildRun(
            season_id=season_id,
            aggregation_version="task3-v1",
            source_max_raw_id=100,
            config_hash="analytics-cfg",
            config_snapshot={"analysis_months": [1, 2, 3, 4]},
            status="completed",
            source_eligible_row_count=len(daily_weights),
            source_eligible_weight_kg=sum(daily_weights, Decimal("0")),
            daily_fact_row_count=len(daily_weights),
        )
        session.add(build_run)
        await session.flush()
        for index, weight in enumerate(daily_weights):
            session.add(
                FactReceiptDaily(
                    build_run_id=build_run.id,
                    season_id=season_id,
                    receipt_date=season.start_date + timedelta(days=index),
                    factory_id=factory_id,
                    farm_key=farm_key,
                    subfarm_key=subfarm_key,
                    variety_id=variety_id,
                    weight_kg=weight,
                    source_row_count=1,
                    holiday_codes=["spring_festival"] if index == 9 else [],
                    is_spring_festival=index == 9,
                )
            )
        await session.commit()
        return build_run.id


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
                    row_hash=f"maturity-obs-{source_version}-{day.isoformat()}",
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
            row_hash=(
                f"maturity-obs-{source_version}-"
                f"{observation_date.isoformat()}-{available_at.isoformat()}"
            ),
        )
        session.add(row)
        await session.commit()
        return row.id


async def test_train_and_forecast_maturity_curve_are_idempotent(client: AsyncClient) -> None:
    dimensions = await _seed_dimensions()
    await _seed_mapping(
        location_reference_id=dimensions["location_reference_id"],
        weather_source_location_id=dimensions["weather_source_location_id"],
    )
    await _seed_weather_days(
        weather_source_location_id=dimensions["weather_source_location_id"],
        start_date=date(2026, 1, 1),
        days=61,
        source_version="weather-v1",
    )
    base_temp_run_id = await _seed_base_temperature_run(
        variety_id=dimensions["variety_id"],
        climate_zone_id=dimensions["zone_id"],
    )
    plan_a = await _seed_plan(
        season_id=dimensions["season_ids"]["2024-2025"],
        farm_id=dimensions["farm_id"],
        variety_id=dimensions["variety_id"],
        version=1,
        available_at=date(2024, 12, 15),
    )
    plan_b = await _seed_plan(
        season_id=dimensions["season_ids"]["2025-2026"],
        farm_id=dimensions["farm_id"],
        variety_id=dimensions["variety_id"],
        version=1,
        available_at=date(2025, 12, 15),
    )
    build_a = await _seed_analytics_sample(
        season_id=dimensions["season_ids"]["2024-2025"],
        factory_id=dimensions["factory_id"],
        variety_id=dimensions["variety_id"],
        farm_key="farm-a",
        subfarm_key="__UNKNOWN_SUBFARM__",
        daily_weights=[
            Decimal("10"),
            Decimal("100"),
            Decimal("200"),
            Decimal("400"),
            Decimal("600"),
            Decimal("900"),
            Decimal("700"),
            Decimal("500"),
            Decimal("300"),
            Decimal("100"),
        ],
    )
    build_b = await _seed_analytics_sample(
        season_id=dimensions["season_ids"]["2025-2026"],
        factory_id=dimensions["factory_id"],
        variety_id=dimensions["variety_id"],
        farm_key="farm-a",
        subfarm_key="__UNKNOWN_SUBFARM__",
        daily_weights=[
            Decimal("12"),
            Decimal("120"),
            Decimal("240"),
            Decimal("420"),
            Decimal("610"),
            Decimal("880"),
            Decimal("720"),
            Decimal("480"),
            Decimal("260"),
            Decimal("120"),
        ],
    )

    train_payload = {
        "training_cutoff": "2026-04-30",
        "manifest_rows": [
            {
                "season_id": dimensions["season_ids"]["2024-2025"],
                "analytics_build_run_id": build_a,
                "farm_key": "farm-a",
                "farm_id": dimensions["farm_id"],
                "subfarm_key": "__UNKNOWN_SUBFARM__",
                "subfarm_id": None,
                "variety_id": dimensions["variety_id"],
                "location_reference_id": dimensions["location_reference_id"],
                "production_plan_id": plan_a,
                "base_temperature_search_run_id": base_temp_run_id,
                "anchor_event": "flowering_start_date",
                "facility_type": "open_field",
                "include": True,
                "sample_weight": "1",
                "exclusion_reason": None,
            },
            {
                "season_id": dimensions["season_ids"]["2025-2026"],
                "analytics_build_run_id": build_b,
                "farm_key": "farm-a",
                "farm_id": dimensions["farm_id"],
                "subfarm_key": "__UNKNOWN_SUBFARM__",
                "subfarm_id": None,
                "variety_id": dimensions["variety_id"],
                "location_reference_id": dimensions["location_reference_id"],
                "production_plan_id": plan_b,
                "base_temperature_search_run_id": base_temp_run_id,
                "anchor_event": "flowering_start_date",
                "facility_type": "open_field",
                "include": True,
                "sample_weight": "1",
                "exclusion_reason": None,
            },
        ],
        "dry_run": False,
    }

    first_train = await client.post("/planning/maturity/models/train", json=train_payload)
    assert first_train.status_code == 200
    first_train_payload = first_train.json()["payload"]
    assert first_train_payload["status"] == "completed"
    run_id = first_train_payload["run_id"]
    assert run_id is not None

    second_train = await client.post("/planning/maturity/models/train", json=train_payload)
    assert second_train.status_code == 200
    second_train_payload = second_train.json()["payload"]
    assert second_train_payload["status"] == "skipped"
    assert second_train_payload["run_id"] == run_id

    forecast_payload = {
        "model_run_id": run_id,
        "farm_id": dimensions["farm_id"],
        "subfarm_id": None,
        "season_id": dimensions["season_ids"]["2025-2026"],
        "variety_id": dimensions["variety_id"],
        "as_of_date": "2026-03-01",
        "prediction_start_date": "2026-03-01",
        "prediction_end_date": "2026-03-07",
        "expected_marketable_total_kg": "96000",
        "facility_type": "open_field",
        "dry_run": False,
    }
    first_forecast = await client.post("/planning/maturity/forecasts", json=forecast_payload)
    assert first_forecast.status_code == 200
    first_forecast_payload = first_forecast.json()["payload"]
    assert first_forecast_payload["status"] == "completed"
    forecast_run_id = first_forecast_payload["run_id"]
    assert forecast_run_id is not None

    second_forecast = await client.post("/planning/maturity/forecasts", json=forecast_payload)
    assert second_forecast.status_code == 200
    second_forecast_payload = second_forecast.json()["payload"]
    assert second_forecast_payload["status"] == "skipped"
    assert second_forecast_payload["run_id"] == forecast_run_id

    async with AsyncSessionMaker() as session:
        assert await session.scalar(select(func.count()).select_from(MaturityModelRun)) == 1
        assert await session.scalar(select(func.count()).select_from(MaturityModelArtifact)) == 1
        assert await session.scalar(select(func.count()).select_from(MaturityForecastRun)) == 1
        daily_count = await session.scalar(
            select(func.count()).select_from(MaturityDailyPredictionModel)
        )
        assert daily_count == 7
        total_p50 = await session.scalar(
            select(func.sum(MaturityDailyPredictionModel.p50_kg)).where(
                MaturityDailyPredictionModel.forecast_run_id == forecast_run_id
            )
        )
        assert total_p50 == Decimal("96000.000000")


async def test_forecast_source_signature_changes_for_total_facility_and_visible_weather(
    client: AsyncClient,
) -> None:
    dimensions = await _seed_dimensions()
    await _seed_mapping(
        location_reference_id=dimensions["location_reference_id"],
        weather_source_location_id=dimensions["weather_source_location_id"],
    )
    await _seed_weather_days(
        weather_source_location_id=dimensions["weather_source_location_id"],
        start_date=date(2026, 1, 1),
        days=61,
        source_version="weather-v1",
    )
    base_temp_run_id = await _seed_base_temperature_run(
        variety_id=dimensions["variety_id"],
        climate_zone_id=dimensions["zone_id"],
    )
    plan_a = await _seed_plan(
        season_id=dimensions["season_ids"]["2024-2025"],
        farm_id=dimensions["farm_id"],
        variety_id=dimensions["variety_id"],
        version=1,
        available_at=date(2024, 12, 15),
    )
    plan_b = await _seed_plan(
        season_id=dimensions["season_ids"]["2025-2026"],
        farm_id=dimensions["farm_id"],
        variety_id=dimensions["variety_id"],
        version=1,
        available_at=date(2025, 12, 15),
    )
    build_a = await _seed_analytics_sample(
        season_id=dimensions["season_ids"]["2024-2025"],
        factory_id=dimensions["factory_id"],
        variety_id=dimensions["variety_id"],
        farm_key="farm-a",
        subfarm_key="__UNKNOWN_SUBFARM__",
        daily_weights=[Decimal("100")] * 10,
    )
    build_b = await _seed_analytics_sample(
        season_id=dimensions["season_ids"]["2025-2026"],
        factory_id=dimensions["factory_id"],
        variety_id=dimensions["variety_id"],
        farm_key="farm-a",
        subfarm_key="__UNKNOWN_SUBFARM__",
        daily_weights=[Decimal("120")] * 10,
    )
    train_payload = {
        "training_cutoff": "2026-04-30",
        "manifest_rows": [
            {
                "season_id": dimensions["season_ids"]["2024-2025"],
                "analytics_build_run_id": build_a,
                "farm_key": "farm-a",
                "farm_id": dimensions["farm_id"],
                "subfarm_key": "__UNKNOWN_SUBFARM__",
                "subfarm_id": None,
                "variety_id": dimensions["variety_id"],
                "location_reference_id": dimensions["location_reference_id"],
                "production_plan_id": plan_a,
                "base_temperature_search_run_id": base_temp_run_id,
                "anchor_event": "flowering_start_date",
                "facility_type": "open_field",
                "include": True,
                "sample_weight": "1",
                "exclusion_reason": None,
            },
            {
                "season_id": dimensions["season_ids"]["2025-2026"],
                "analytics_build_run_id": build_b,
                "farm_key": "farm-a",
                "farm_id": dimensions["farm_id"],
                "subfarm_key": "__UNKNOWN_SUBFARM__",
                "subfarm_id": None,
                "variety_id": dimensions["variety_id"],
                "location_reference_id": dimensions["location_reference_id"],
                "production_plan_id": plan_b,
                "base_temperature_search_run_id": base_temp_run_id,
                "anchor_event": "flowering_start_date",
                "facility_type": "open_field",
                "include": True,
                "sample_weight": "1",
                "exclusion_reason": None,
            },
        ],
        "dry_run": False,
    }
    train_response = await client.post("/planning/maturity/models/train", json=train_payload)
    assert train_response.status_code == 200, train_response.text
    model_run_id = train_response.json()["payload"]["run_id"]
    assert model_run_id is not None

    base_forecast = {
        "model_run_id": model_run_id,
        "farm_id": dimensions["farm_id"],
        "subfarm_id": None,
        "season_id": dimensions["season_ids"]["2025-2026"],
        "variety_id": dimensions["variety_id"],
        "as_of_date": "2026-03-01",
        "prediction_start_date": "2026-03-01",
        "prediction_end_date": "2026-03-07",
        "expected_marketable_total_kg": "96000",
        "facility_type": "open_field",
        "dry_run": False,
    }
    first = await client.post("/planning/maturity/forecasts", json=base_forecast)
    assert first.status_code == 200, first.text
    first_payload = first.json()["payload"]
    assert first_payload["status"] == "completed"
    first_run_id = first_payload["run_id"]
    assert first_run_id is not None

    second = await client.post("/planning/maturity/forecasts", json=base_forecast)
    assert second.status_code == 200, second.text
    assert second.json()["payload"]["status"] == "skipped"
    assert second.json()["payload"]["run_id"] == first_run_id

    changed_total = await client.post(
        "/planning/maturity/forecasts",
        json={**base_forecast, "expected_marketable_total_kg": "97000"},
    )
    assert changed_total.status_code == 200, changed_total.text
    total_payload = changed_total.json()["payload"]
    assert total_payload["status"] == "completed"
    assert total_payload["run_id"] != first_run_id
    assert total_payload["source_signature"] != first_payload["source_signature"]

    changed_facility = await client.post(
        "/planning/maturity/forecasts",
        json={**base_forecast, "facility_type": "tunnel"},
    )
    assert changed_facility.status_code == 200, changed_facility.text
    facility_payload = changed_facility.json()["payload"]
    assert facility_payload["status"] == "completed"
    assert facility_payload["run_id"] not in {None, first_run_id, total_payload["run_id"]}

    await _seed_weather_revision(
        weather_source_location_id=dimensions["weather_source_location_id"],
        observation_date=date(2026, 2, 28),
        source_version="weather-v2",
        available_at=date(2026, 3, 1),
        mean_c=Decimal("18"),
    )
    revised_visible = await client.post("/planning/maturity/forecasts", json=base_forecast)
    assert revised_visible.status_code == 200, revised_visible.text
    revised_visible_payload = revised_visible.json()["payload"]
    assert revised_visible_payload["status"] == "completed"
    assert revised_visible_payload["source_signature"] != first_payload["source_signature"]
    assert revised_visible_payload["run_id"] not in {
        first_run_id,
        total_payload["run_id"],
        facility_payload["run_id"],
    }

    await _seed_weather_revision(
        weather_source_location_id=dimensions["weather_source_location_id"],
        observation_date=date(2026, 3, 1),
        source_version="weather-v3",
        available_at=date(2026, 3, 5),
        mean_c=Decimal("21"),
    )
    future_invisible = await client.post("/planning/maturity/forecasts", json=base_forecast)
    assert future_invisible.status_code == 200, future_invisible.text
    future_payload = future_invisible.json()["payload"]
    assert future_payload["status"] == "skipped"
    assert future_payload["run_id"] == revised_visible_payload["run_id"]


async def test_training_cutoff_blocks_future_visible_dependencies(client: AsyncClient) -> None:
    dimensions = await _seed_dimensions()
    await _seed_mapping(
        location_reference_id=dimensions["location_reference_id"],
        weather_source_location_id=dimensions["weather_source_location_id"],
    )
    await _seed_weather_days(
        weather_source_location_id=dimensions["weather_source_location_id"],
        start_date=date(2025, 1, 1),
        days=30,
        source_version="weather-v1",
    )
    future_base_temp_run_id = await _seed_base_temperature_run(
        variety_id=dimensions["variety_id"],
        climate_zone_id=dimensions["zone_id"],
    )
    async with AsyncSessionMaker() as session:
        run = await session.get(BaseTemperatureSearchRun, future_base_temp_run_id)
        assert run is not None
        run.training_cutoff = date(2026, 5, 1)
        await session.commit()

    plan_id = await _seed_plan(
        season_id=dimensions["season_ids"]["2024-2025"],
        farm_id=dimensions["farm_id"],
        variety_id=dimensions["variety_id"],
        version=1,
        available_at=date(2024, 12, 15),
    )
    build_run_id = await _seed_analytics_sample(
        season_id=dimensions["season_ids"]["2024-2025"],
        factory_id=dimensions["factory_id"],
        variety_id=dimensions["variety_id"],
        farm_key="farm-a",
        subfarm_key="__UNKNOWN_SUBFARM__",
        daily_weights=[Decimal("100")] * 10,
    )
    async with AsyncSessionMaker() as session:
        build_run = await session.get(AnalyticsBuildRun, build_run_id)
        assert build_run is not None
        build_run.finished_at = datetime(2026, 5, 1, tzinfo=UTC)
        await session.commit()

    response = await client.post(
        "/planning/maturity/models/train",
        json={
            "training_cutoff": "2026-04-30",
            "manifest_rows": [
                {
                    "season_id": dimensions["season_ids"]["2024-2025"],
                    "analytics_build_run_id": build_run_id,
                    "farm_key": "farm-a",
                    "farm_id": dimensions["farm_id"],
                    "subfarm_key": "__UNKNOWN_SUBFARM__",
                    "subfarm_id": None,
                    "variety_id": dimensions["variety_id"],
                    "location_reference_id": dimensions["location_reference_id"],
                    "production_plan_id": plan_id,
                    "base_temperature_search_run_id": future_base_temp_run_id,
                    "anchor_event": "flowering_start_date",
                    "facility_type": "open_field",
                    "include": True,
                    "sample_weight": "1",
                    "exclusion_reason": None,
                }
            ],
            "dry_run": False,
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()["payload"]
    assert payload["status"] == "unavailable"
    manifest_row = payload["input_snapshot"]["manifest_rows"][0]
    assert manifest_row["resolved_exclusion_reason"] == "analytics_build_run_not_visible_at_cutoff"


async def test_training_cutoff_blocks_future_base_temperature_run(client: AsyncClient) -> None:
    dimensions = await _seed_dimensions()
    await _seed_mapping(
        location_reference_id=dimensions["location_reference_id"],
        weather_source_location_id=dimensions["weather_source_location_id"],
    )
    await _seed_weather_days(
        weather_source_location_id=dimensions["weather_source_location_id"],
        start_date=date(2025, 1, 1),
        days=30,
        source_version="weather-v1",
    )
    base_temp_run_id = await _seed_base_temperature_run(
        variety_id=dimensions["variety_id"],
        climate_zone_id=dimensions["zone_id"],
    )
    async with AsyncSessionMaker() as session:
        run = await session.get(BaseTemperatureSearchRun, base_temp_run_id)
        assert run is not None
        run.training_cutoff = date(2026, 5, 1)
        await session.commit()

    plan_id = await _seed_plan(
        season_id=dimensions["season_ids"]["2024-2025"],
        farm_id=dimensions["farm_id"],
        variety_id=dimensions["variety_id"],
        version=1,
        available_at=date(2024, 12, 15),
    )
    build_run_id = await _seed_analytics_sample(
        season_id=dimensions["season_ids"]["2024-2025"],
        factory_id=dimensions["factory_id"],
        variety_id=dimensions["variety_id"],
        farm_key="farm-a",
        subfarm_key="__UNKNOWN_SUBFARM__",
        daily_weights=[Decimal("100")] * 10,
    )
    async with AsyncSessionMaker() as session:
        build_run = await session.get(AnalyticsBuildRun, build_run_id)
        assert build_run is not None
        build_run.finished_at = datetime(2026, 4, 30, tzinfo=UTC)
        await session.commit()

    response = await client.post(
        "/planning/maturity/models/train",
        json={
            "training_cutoff": "2026-04-30",
            "manifest_rows": [
                {
                    "season_id": dimensions["season_ids"]["2024-2025"],
                    "analytics_build_run_id": build_run_id,
                    "farm_key": "farm-a",
                    "farm_id": dimensions["farm_id"],
                    "subfarm_key": "__UNKNOWN_SUBFARM__",
                    "subfarm_id": None,
                    "variety_id": dimensions["variety_id"],
                    "location_reference_id": dimensions["location_reference_id"],
                    "production_plan_id": plan_id,
                    "base_temperature_search_run_id": base_temp_run_id,
                    "anchor_event": "flowering_start_date",
                    "facility_type": "open_field",
                    "include": True,
                    "sample_weight": "1",
                    "exclusion_reason": None,
                }
            ],
            "dry_run": False,
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()["payload"]
    assert payload["status"] == "unavailable"
    manifest_row = payload["input_snapshot"]["manifest_rows"][0]
    assert manifest_row["resolved_exclusion_reason"] == "base_temperature_run_not_visible_at_cutoff"


async def test_failed_model_and_forecast_api_preserve_failed_status(
    client: AsyncClient,
) -> None:
    dimensions = await _seed_dimensions()
    mapping_id = await _seed_mapping(
        location_reference_id=dimensions["location_reference_id"],
        weather_source_location_id=dimensions["weather_source_location_id"],
    )
    plan_id = await _seed_plan(
        season_id=dimensions["season_ids"]["2025-2026"],
        farm_id=dimensions["farm_id"],
        variety_id=dimensions["variety_id"],
        version=1,
        available_at=date(2025, 12, 15),
    )
    base_temp_run_id = await _seed_base_temperature_run(
        variety_id=dimensions["variety_id"],
        climate_zone_id=dimensions["zone_id"],
    )

    async with AsyncSessionMaker() as session:
        model_run = MaturityModelRun(
            model_version="task8-v1",
            config_hash="cfg",
            config_snapshot={"version": "task8-v1"},
            training_cutoff=date(2026, 4, 30),
            source_signature="failed-model-sig",
            status="failed",
            random_seed=20260624,
            model_family="shared_spline_partial_pooling",
            scope="task8",
            sample_count=0,
            distinct_season_count=0,
            distinct_farm_count=0,
            distinct_subfarm_count=0,
            training_metrics={},
            calibration_metrics={},
            warnings=[],
            blockers=["training_failed"],
            input_snapshot={},
            finished_at=datetime.now(UTC),
            error_message="model failed",
        )
        session.add(model_run)
        await session.flush()
        artifact = MaturityModelArtifact(
            run_id=model_run.id,
            artifact_hash="failed-artifact-hash",
            support_min_day=-30,
            support_max_day=90,
            artifact_payload={
                "support_days": [0, 1],
                "anchor_event": "flowering_start_date",
                "group_models": {},
                "shift_model": {
                    "enabled": False,
                    "intercept_days": "0",
                    "coefficients": {},
                    "category_vocabulary": {"facility_type": ["unknown"]},
                    "reference_categories": {"facility_type": "unknown"},
                    "feature_order": [],
                    "scaler_center": {},
                    "scaler_scale": {},
                    "feature_units": {},
                    "missing_value_rules": {},
                    "bounds": ["-21", "21"],
                    "warnings": [],
                },
                "calibration": {},
                "base_temperature_context": {},
            },
        )
        session.add(artifact)
        await session.flush()
        forecast_run = MaturityForecastRun(
            model_run_id=model_run.id,
            artifact_id=artifact.id,
            plan_id=plan_id,
            location_reference_id=dimensions["location_reference_id"],
            weather_mapping_id=mapping_id,
            base_temperature_search_run_id=base_temp_run_id,
            as_of_date=date(2026, 3, 1),
            prediction_start_date=date(2026, 3, 1),
            prediction_end_date=date(2026, 3, 7),
            expected_marketable_total_kg=Decimal("96000"),
            expected_total_source="explicit",
            axis_mode="calendar_proxy_axis",
            source_signature="failed-forecast-sig",
            status="failed",
            warnings=[],
            blockers=["forecast_failed"],
            input_snapshot={},
            finished_at=datetime.now(UTC),
            error_message="forecast failed",
        )
        session.add(forecast_run)
        await session.commit()
        model_run_id = model_run.id
        forecast_run_id = forecast_run.id

    model_response = await client.get(f"/planning/maturity/models/{model_run_id}")
    assert model_response.status_code == 200, model_response.text
    model_payload = model_response.json()
    assert model_payload["status"] == "failed"
    assert model_payload["payload"]["status"] == "failed"
    assert model_payload["payload"]["error_message"] == "model failed"

    forecast_response = await client.get(f"/planning/maturity/forecasts/{forecast_run_id}")
    assert forecast_response.status_code == 200, forecast_response.text
    forecast_payload = forecast_response.json()
    assert forecast_payload["status"] == "failed"
    assert forecast_payload["payload"]["status"] == "failed"
    assert forecast_payload["payload"]["error_message"] == "forecast failed"
