from __future__ import annotations

import csv
import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from backend.app.db.session import AsyncSessionMaker
from backend.app.main import create_app
from backend.app.models.master_data import Farm, Season, Variety
from backend.app.models.planning import (
    AgroClimateZone,
    LocationReference,
    MinimalForecastTask,
    ParameterInferenceResult,
    ParameterInferenceRun,
    ParameterLibraryVersion,
    ParameterObservation,
)
from backend.app.planning.config import load_parameter_inference_config
from backend.app.planning.importers import (
    import_location_references_csv,
    import_parameter_library_csv,
)
from backend.app.planning.imports.climate_zone_importer import (
    import_agro_climate_zones_csv,
    normalize_climate_zone_code,
)
from backend.app.planning.location import resolve_location_input
from backend.app.planning.service import _load_candidates, create_minimal_planning_task
from backend.app.planning.similarity import haversine_distance_km

pytestmark = pytest.mark.integration


def _require_postgres() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("set RUN_POSTGRES_INTEGRATION=1 when PostgreSQL is available")


@pytest.fixture
async def client() -> AsyncClient:
    _require_postgres()
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


def _write_parameter_config(path: Path) -> None:
    path.write_text(
        """
resolver_version: "task5-v1"
resolver:
  address_fuzzy_match_min_score: 0.75
  nearest_reference_distance_km: 20
  climate_zone_radius_km: 80
similarity:
  max_distance_km: 300
  max_altitude_difference_m: 800
  township_bonus: 0.30
  county_bonus: 0.20
  climate_zone_bonus: 0.25
  same_farm_bonus: 1.00
  distance_weight: 0.25
  altitude_weight: 0.20
  recency_weight: 0.10
  ambiguity_margin: 0.05
fallback:
  same_farm_variety:
    minimum_sample_count: 2
    minimum_season_count: 2
    maximum_historical_mape: 0.20
  same_township_altitude_variety:
    minimum_sample_count: 3
    minimum_season_count: 2
    maximum_historical_mape: 0.25
  same_county_climate_zone_variety:
    minimum_sample_count: 4
    minimum_season_count: 2
    maximum_historical_mape: 0.30
  same_province_variety:
    minimum_sample_count: 1
    minimum_season_count: 1
    maximum_historical_mape: 0.35
  literature_variety_prior:
    minimum_sample_count: 1
    minimum_season_count: 0
    maximum_historical_mape: null
uncertainty:
  widen_low_confidence_factor: 1.50
  widen_below_minimum_factor: 1.25
confidence:
  high_min_score: 0.80
  medium_min_score: 0.50
  same_farm_high_min_seasons: 2
  high_max_historical_mape: 0.20
  medium_max_historical_mape: 0.30
  missing_error_penalty: 0.15
  fallback_below_minimum_penalty: 0.20
  unresolved_location_penalty: 0.20
""",
        encoding="utf-8",
    )


async def _seed_master_data() -> tuple[int, int]:
    async with AsyncSessionMaker() as session:
        season = Season(code="2024-2025", start_date=date(2025, 1, 1), end_date=date(2025, 4, 30))
        variety = Variety(code="DX", name="Dx")
        farm = Farm(name="农场A")
        session.add_all([season, variety, farm])
        await session.commit()
        return season.id, variety.id


async def _set_library_effective_from(
    session: object,
    *,
    version_code: str,
    effective_from: date,
) -> None:
    library = await cast(Any, session).scalar(
        select(ParameterLibraryVersion).where(ParameterLibraryVersion.version_code == version_code)
    )
    assert library is not None
    library.effective_from = effective_from
    await cast(Any, session).commit()


def _write_location_csv(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "farm_code",
                "farm_name",
                "subfarm_name",
                "address_raw",
                "province",
                "prefecture",
                "county",
                "township",
                "village",
                "latitude",
                "longitude",
                "altitude_m",
                "climate_zone_code",
                "location_source",
                "source_version",
                "valid_from",
                "valid_to",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "farm_code": "farm-a",
                "farm_name": "农场A",
                "subfarm_name": "",
                "address_raw": "云南省 红河州 弥勒市 西三镇",
                "province": "云南省",
                "prefecture": "红河州",
                "county": "弥勒市",
                "township": "西三镇",
                "village": "",
                "latitude": "24.400000",
                "longitude": "103.400000",
                "altitude_m": "1800",
                "climate_zone_code": "zone-a",
                "location_source": "synthetic",
                "source_version": "loc-v1",
                "valid_from": "2024-01-01",
                "valid_to": "",
            }
        )


def _write_zone_csv(path: Path) -> None:
    path.write_text(
        (
            "code,name,country,province,prefecture,county,centroid_latitude,"
            "centroid_longitude,min_altitude_m,max_altitude_m,zone_version,"
            "valid_from,valid_to,source_name,source_version\n"
            "zone-a,Zone A,China,云南省,红河州,弥勒市,24.400000,103.400000,"
            "1700,1900,zone-v1,2024-01-01,,synthetic,src-v1\n"
        ),
        encoding="utf-8",
    )




def _write_ambiguous_location_csv(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "farm_code",
                "farm_name",
                "subfarm_name",
                "address_raw",
                "province",
                "prefecture",
                "county",
                "township",
                "village",
                "latitude",
                "longitude",
                "altitude_m",
                "climate_zone_code",
                "location_source",
                "source_version",
                "valid_from",
                "valid_to",
            ],
        )
        writer.writeheader()
        for index, latitude in enumerate(("24.400000", "24.410000"), start=1):
            writer.writerow(
                {
                    "farm_code": f"farm-{index}",
                    "farm_name": "",
                    "subfarm_name": "",
                    "address_raw": "云南省 红河州 弥勒市 西三镇",
                    "province": "云南省",
                    "prefecture": "红河州",
                    "county": "弥勒市",
                    "township": "西三镇",
                    "village": "",
                    "latitude": latitude,
                    "longitude": "103.400000",
                    "altitude_m": "1800",
                    "climate_zone_code": "zone-a",
                    "location_source": "synthetic",
                    "source_version": "loc-v1",
                    "valid_from": "2024-01-01",
                    "valid_to": "",
                }
            )

def _write_parameter_csv(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "parameter_type",
                "variety_code",
                "farm_code",
                "farm_name",
                "subfarm_name",
                "location_reference_id",
                "climate_zone_code",
                "season_code",
                "province",
                "prefecture",
                "county",
                "township",
                "altitude_m",
                "scalar_value",
                "unit",
                "sample_weight",
                "source_level",
                "source_name",
                "source_version",
                "historical_mape",
                "date_mae_days",
                "p90_coverage",
                "available_at",
                "valid_from",
                "valid_to",
            ],
        )
        writer.writeheader()
        rows = [
            ("yield_kg_per_mu", "1000", "kg_per_mu"),
            ("marketable_rate", "0.80", "ratio"),
            ("first_harvest_offset_days", "5", "days"),
            ("maturity_peak_offset_days", "15", "days"),
            ("maturity_width_days", "20", "days"),
            ("maturity_skewness", "0.10", "scalar"),
            ("harvest_realization_rate", "0.90", "ratio"),
        ]
        for parameter_type, scalar_value, unit in rows:
            writer.writerow(
                {
                    "parameter_type": parameter_type,
                    "variety_code": "DX",
                    "farm_code": "farm-a",
                    "farm_name": "农场A",
                    "subfarm_name": "",
                    "location_reference_id": "",
                    "climate_zone_code": "zone-a",
                    "season_code": "2024-2025",
                    "province": "云南省",
                    "prefecture": "红河州",
                    "county": "弥勒市",
                    "township": "西三镇",
                    "altitude_m": "1800",
                    "scalar_value": scalar_value,
                    "unit": unit,
                    "sample_weight": "1",
                    "source_level": "same_farm_variety",
                    "source_name": "synthetic",
                    "source_version": "param-v1",
                    "historical_mape": "0.10",
                    "date_mae_days": "2",
                    "p90_coverage": "0.85",
                    "available_at": "2025-05-01",
                    "valid_from": "2024-01-01",
                    "valid_to": "",
                }
            )


@pytest.mark.asyncio
async def test_location_reference_import_is_idempotent(tmp_path: Path) -> None:
    _require_postgres()
    location_csv = tmp_path / "farm_location_master.csv"
    config_path = tmp_path / "parameter_inference.yaml"
    _write_location_csv(location_csv)
    _write_parameter_config(config_path)

    async with AsyncSessionMaker() as session:
        first = await import_location_references_csv(
            session,
            file_path=location_csv,
            source_version="loc-v1",
            dry_run=False,
        )
        second = await import_location_references_csv(
            session,
            file_path=location_csv,
            source_version="loc-v1",
            dry_run=False,
        )
        count = int(await session.scalar(select(func.count()).select_from(LocationReference)) or 0)

    assert first.inserted_row_count == 1
    assert second.inserted_row_count == 0
    assert count == 1


@pytest.mark.asyncio
async def test_parameter_library_import_activate_switches_active_atomically(tmp_path: Path) -> None:
    _require_postgres()
    await _seed_master_data()
    parameter_csv = tmp_path / "parameter_observations.csv"
    _write_parameter_csv(parameter_csv)

    async with AsyncSessionMaker() as session:
        first = await import_parameter_library_csv(
            session,
            file_path=parameter_csv,
            version_code="lib-v1",
            activate=True,
            dry_run=False,
        )
        second = await import_parameter_library_csv(
            session,
            file_path=parameter_csv,
            version_code="lib-v2",
            activate=True,
            dry_run=False,
        )
        active_versions = (
            await session.scalars(
                select(ParameterLibraryVersion).where(ParameterLibraryVersion.status == "active")
            )
        ).all()

    assert first.status in {"draft", "active"}
    assert second.status == "active"
    assert len(active_versions) == 1
    assert active_versions[0].version_code == "lib-v2"


@pytest.mark.asyncio
async def test_create_minimal_planning_task_dry_run_is_zero_write_and_excludes_future_rows(
    tmp_path: Path,
) -> None:
    _require_postgres()
    await _seed_master_data()
    zone_csv = tmp_path / "agro_climate_zones.csv"
    location_csv = tmp_path / "farm_location_master.csv"
    parameter_csv = tmp_path / "parameter_observations.csv"
    config_path = tmp_path / "parameter_inference.yaml"
    _write_zone_csv(zone_csv)
    _write_location_csv(location_csv)
    _write_parameter_csv(parameter_csv)
    _write_parameter_config(config_path)
    config = load_parameter_inference_config(config_path)

    async with AsyncSessionMaker() as session:
        await import_agro_climate_zones_csv(
            session,
            file_path=zone_csv,
            dry_run=False,
        )
        await import_location_references_csv(
            session,
            file_path=location_csv,
            source_version="loc-v1",
            dry_run=False,
        )
        await import_parameter_library_csv(
            session,
            file_path=parameter_csv,
            version_code="lib-v1",
            activate=True,
            dry_run=False,
        )
        await _set_library_effective_from(
            session,
            version_code="lib-v1",
            effective_from=date(2024, 1, 1),
        )
        before_tasks = int(
            await session.scalar(
                select(func.count()).select_from(MinimalForecastTask)
            )
            or 0
        )
        result = await create_minimal_planning_task(
            session,
            payload={
                "location": {"address": "云南省 红河州 弥勒市 西三镇"},
                "varieties": [{"variety_code": "DX", "planted_area_mu": "700"}],
                "as_of_date": "2025-01-01",
            },
            config=config,
            dry_run=True,
        )
        after_tasks = int(
            await session.scalar(
                select(func.count()).select_from(MinimalForecastTask)
            )
            or 0
        )

    assert result.status == "dry_run"
    assert before_tasks == after_tasks == 0
    assert result.variety_parameters[0]["yield_kg_per_mu"]["status"] == "unavailable"


@pytest.mark.asyncio
async def test_create_minimal_planning_task_completed_then_skipped_and_api_loads_result(
    tmp_path: Path,
    client: AsyncClient,
) -> None:
    _require_postgres()
    await _seed_master_data()
    zone_csv = tmp_path / "agro_climate_zones.csv"
    location_csv = tmp_path / "farm_location_master.csv"
    parameter_csv = tmp_path / "parameter_observations.csv"
    config_path = tmp_path / "parameter_inference.yaml"
    _write_zone_csv(zone_csv)
    _write_location_csv(location_csv)
    _write_parameter_csv(parameter_csv)
    _write_parameter_config(config_path)
    config = load_parameter_inference_config(config_path)

    async with AsyncSessionMaker() as session:
        zone_result = await import_agro_climate_zones_csv(
            session,
            file_path=zone_csv,
            dry_run=False,
        )
        location_result = await import_location_references_csv(
            session,
            file_path=location_csv,
            source_version="loc-v1",
            dry_run=False,
        )
        parameter_result = await import_parameter_library_csv(
            session,
            file_path=parameter_csv,
            version_code="lib-v1",
            activate=True,
            dry_run=False,
        )
        await _set_library_effective_from(
            session,
            version_code="lib-v1",
            effective_from=date(2024, 1, 1),
        )
        normalized_zone_code = normalize_climate_zone_code("zone-a")
        zone = await session.scalar(
            select(AgroClimateZone).where(AgroClimateZone.code == normalized_zone_code)
        )
        location_reference = await session.scalar(select(LocationReference))
        parameter_observation = await session.scalar(select(ParameterObservation))
        assert zone_result.inserted_rows == 1
        assert location_result.inserted_row_count == 1
        assert parameter_result.status in {"draft", "active"}
        assert zone is not None
        assert location_reference is not None
        assert parameter_observation is not None
        assert location_reference.climate_zone_id == zone.id
        assert parameter_observation.climate_zone_id == zone.id
        first = await create_minimal_planning_task(
            session,
            payload={
                "location": {"address": "云南省 红河州 弥勒市 西三镇"},
                "varieties": [{"variety_code": "DX", "planted_area_mu": "700"}],
                "as_of_date": "2026-01-01",
            },
            config=config,
            dry_run=False,
        )
        second = await create_minimal_planning_task(
            session,
            payload={
                "location": {"address": "云南省 红河州 弥勒市 西三镇"},
                "varieties": [{"variety_code": "DX", "planted_area_mu": "700"}],
                "as_of_date": "2026-01-01",
            },
            config=config,
            dry_run=False,
        )
        task_count = int(
            await session.scalar(
                select(func.count()).select_from(MinimalForecastTask)
            )
            or 0
        )
        run_count = int(
            await session.scalar(
                select(func.count()).select_from(ParameterInferenceRun)
            )
            or 0
        )
        result_count = int(
            await session.scalar(
                select(func.count()).select_from(ParameterInferenceResult)
            )
            or 0
        )

    assert first.status == "completed"
    assert first.library_version == "lib-v1"
    assert second.status == "skipped"
    assert second.library_version == "lib-v1"
    assert first.resolved_location == second.resolved_location
    assert first.variety_parameters == second.variety_parameters
    assert task_count == 1
    assert run_count == 1
    assert result_count == 7
    assert location_reference is not None
    assert location_reference.climate_zone_id is not None

    yield_row = first.variety_parameters[0]["yield_kg_per_mu"]
    assert yield_row["source_version"] == "param-v1"
    assert yield_row["source_versions"] == ["param-v1"]
    assert yield_row["distance_range_km"] is not None
    assert yield_row["historical_mape"] == "0.1"
    assert yield_row["date_mae_days"] == "2"
    assert yield_row["p90_coverage"] == "0.85"
    assert first.resolved_location["climate_zone_mapping_method"] == "reference"
    assert first.resolved_location["climate_zone_score"] == "1"

    create_response = await client.post(
        "/planning/tasks",
        json={
            "location": {"address": "云南省 红河州 弥勒市 西三镇"},
            "varieties": [{"variety_code": "DX", "planted_area_mu": "700"}],
            "as_of_date": "2026-01-01",
        },
    )
    assert create_response.status_code == 200, create_response.text
    payload = create_response.json()
    assert payload["status"] in {"completed", "skipped"}
    assert payload["task_id"] == first.task_id
    assert payload["library_version"] == "lib-v1"
    assert payload["resolved_location"] == first.resolved_location
    assert payload["variety_parameters"] == first.variety_parameters

    get_response = await client.get(f"/planning/tasks/{first.task_id}")
    assert get_response.status_code == 200, get_response.text
    get_payload = get_response.json()
    assert get_payload["task_id"] == first.task_id
    assert get_payload["library_version"] == "lib-v1"
    assert get_payload["resolved_location"] == first.resolved_location
    assert get_payload["variety_parameters"] == first.variety_parameters



@pytest.mark.asyncio
async def test_create_minimal_planning_task_ambiguous_address_fails_without_run(
    tmp_path: Path,
    client: AsyncClient,
) -> None:
    _require_postgres()
    await _seed_master_data()
    location_csv = tmp_path / "farm_location_master.csv"
    parameter_csv = tmp_path / "parameter_observations.csv"
    config_path = tmp_path / "parameter_inference.yaml"
    _write_ambiguous_location_csv(location_csv)
    _write_parameter_csv(parameter_csv)
    _write_parameter_config(config_path)
    config = load_parameter_inference_config(config_path)

    async with AsyncSessionMaker() as session:
        await import_location_references_csv(
            session,
            file_path=location_csv,
            source_version="loc-v1",
            dry_run=False,
        )
        await import_parameter_library_csv(
            session,
            file_path=parameter_csv,
            version_code="lib-v1",
            activate=True,
            dry_run=False,
        )
        await _set_library_effective_from(
            session,
            version_code="lib-v1",
            effective_from=date(2024, 1, 1),
        )
        result = await create_minimal_planning_task(
            session,
            payload={
                "location": {"address": "云南省 红河州 弥勒市 西三镇"},
                "varieties": [{"variety_code": "DX", "planted_area_mu": "700"}],
                "as_of_date": "2026-01-01",
            },
            config=config,
            dry_run=False,
        )
        task_count = int(
            await session.scalar(select(func.count()).select_from(MinimalForecastTask)) or 0
        )
        run_count = int(
            await session.scalar(select(func.count()).select_from(ParameterInferenceRun)) or 0
        )
        result_count = int(
            await session.scalar(select(func.count()).select_from(ParameterInferenceResult)) or 0
        )

    assert result.status == "failed"
    assert result.run_id is None
    assert result.resolved_location["status"] == "ambiguous"
    assert task_count == 1
    assert run_count == 0
    assert result_count == 0

    create_response = await client.post(
        "/planning/tasks",
        json={
            "location": {"address": "云南省 红河州 弥勒市 西三镇"},
            "varieties": [{"variety_code": "DX", "planted_area_mu": "700"}],
            "as_of_date": "2026-01-01",
        },
    )
    assert create_response.status_code == 200, create_response.text
    payload = create_response.json()
    assert payload["status"] == "failed"
    assert payload["run_id"] is None
    assert payload["resolved_location"]["status"] == "ambiguous"

    task_id = payload["task_id"]
    assert task_id == result.task_id

    get_response = await client.get(f"/planning/tasks/{task_id}")
    assert get_response.status_code == 200, get_response.text
    get_payload = get_response.json()
    assert get_payload["status"] == "failed"
    assert get_payload["run_id"] is None
    assert get_payload["resolved_location"]["status"] == "ambiguous"


@pytest.mark.asyncio
async def test_location_reference_id_respects_as_of_date_validity(tmp_path: Path) -> None:
    _require_postgres()
    location_csv = tmp_path / "farm_location_master.csv"
    config_path = tmp_path / "parameter_inference.yaml"
    _write_location_csv(location_csv)
    _write_parameter_config(config_path)

    async with AsyncSessionMaker() as session:
        await import_location_references_csv(
            session,
            file_path=location_csv,
            source_version="loc-v1",
            dry_run=False,
        )
        reference_id = int(
            await session.scalar(select(LocationReference.id).order_by(LocationReference.id.asc()))
            or 0
        )

        active_result = await resolve_location_input(
            session,
            location={"location_reference_id": reference_id},
            as_of_date=date(2025, 1, 1),
            rules=load_parameter_inference_config(config_path).rules,
        )
        inactive_result = await resolve_location_input(
            session,
            location={"location_reference_id": reference_id},
            as_of_date=date(2023, 1, 1),
            rules=load_parameter_inference_config(config_path).rules,
        )

    assert active_result.status == "resolved"
    assert inactive_result.status == "unresolved"


@pytest.mark.asyncio
async def test_create_minimal_planning_task_uses_real_historical_sample_coordinates_for_distance(
    tmp_path: Path,
) -> None:
    _require_postgres()
    season_id, variety_id = await _seed_master_data()
    config_path = tmp_path / "parameter_inference.yaml"
    _write_parameter_config(config_path)
    config = load_parameter_inference_config(config_path)

    async with AsyncSessionMaker() as session:
        zone = AgroClimateZone(
            code="ZONE-A",
            name="Zone A",
            country="China",
            province="云南省",
            prefecture="红河州",
            county="弥勒市",
            centroid_latitude="24.400000",
            centroid_longitude="103.400000",
            min_altitude_m="1700",
            max_altitude_m="1900",
            zone_version="zone-v1",
            valid_from=date(2024, 1, 1),
            valid_to=None,
            source_name="synthetic",
            source_version="src-v1",
        )
        near_reference = LocationReference(
            farm_id=None,
            subfarm_id=None,
            farm_code="near",
            farm_name="近样本农场",
            subfarm_name=None,
            address_raw="云南省 红河州 弥勒市 西三镇 近样本",
            address_normalized="云南省 红河州 弥勒市 西三镇 近样本",
            province="云南省",
            prefecture="红河州",
            county="弥勒市",
            township="西三镇",
            village=None,
            latitude="24.401000",
            longitude="103.401000",
            altitude_m="1805",
            climate_zone_id=None,
            location_source="synthetic",
            source_version="loc-v1",
            valid_from=date(2024, 1, 1),
            valid_to=None,
            source_row_hash="near-row",
        )
        far_reference = LocationReference(
            farm_id=None,
            subfarm_id=None,
            farm_code="far",
            farm_name="远样本农场",
            subfarm_name=None,
            address_raw="云南省 红河州 弥勒市 西三镇 远样本",
            address_normalized="云南省 红河州 弥勒市 西三镇 远样本",
            province="云南省",
            prefecture="红河州",
            county="弥勒市",
            township="西三镇",
            village=None,
            latitude="24.470000",
            longitude="103.470000",
            altitude_m="1815",
            climate_zone_id=None,
            location_source="synthetic",
            source_version="loc-v1",
            valid_from=date(2024, 1, 1),
            valid_to=None,
            source_row_hash="far-row",
        )
        target_reference = LocationReference(
            farm_id=None,
            subfarm_id=None,
            farm_code="target",
            farm_name="目标农场",
            subfarm_name=None,
            address_raw="云南省 红河州 弥勒市 西三镇",
            address_normalized="云南省 红河州 弥勒市 西三镇",
            province="云南省",
            prefecture="红河州",
            county="弥勒市",
            township="西三镇",
            village=None,
            latitude="24.400000",
            longitude="103.400000",
            altitude_m="1800",
            climate_zone_id=None,
            location_source="synthetic",
            source_version="loc-v1",
            valid_from=date(2024, 1, 1),
            valid_to=None,
            source_row_hash="target-row",
        )
        session.add(zone)
        await session.flush()
        near_reference.climate_zone_id = zone.id
        far_reference.climate_zone_id = zone.id
        target_reference.climate_zone_id = zone.id
        session.add_all([near_reference, far_reference, target_reference])
        await session.flush()
        library = ParameterLibraryVersion(
            version_code="lib-v1",
            status="active",
            source_name="synthetic.csv",
            source_file_sha256="sha",
            config_hash="cfg",
            record_count=0,
            effective_from=date(2025, 1, 1),
        )
        session.add(library)
        await session.flush()
        near_observation = ParameterObservation(
            library_version_id=library.id,
            parameter_type="yield_kg_per_mu",
            variety_id=variety_id,
            farm_id=None,
            subfarm_id=None,
            location_reference_id=near_reference.id,
            climate_zone_id=zone.id,
            season_id=season_id,
            province="云南省",
            prefecture="红河州",
            county="弥勒市",
            township="西三镇",
            altitude_m="1805",
            scalar_value="1000",
            unit="kg_per_mu",
            sample_weight="1",
            source_level="same_province_variety",
            source_name="synthetic",
            source_version="near-v1",
            historical_mape="0.10",
            date_mae_days="2",
            p90_coverage="0.85",
            available_at=date(2025, 5, 1),
            valid_from=date(2024, 1, 1),
            valid_to=None,
            source_row_hash="near-obs",
        )
        far_observation = ParameterObservation(
            library_version_id=library.id,
            parameter_type="yield_kg_per_mu",
            variety_id=variety_id,
            farm_id=None,
            subfarm_id=None,
            location_reference_id=far_reference.id,
            climate_zone_id=zone.id,
            season_id=season_id,
            province="云南省",
            prefecture="红河州",
            county="弥勒市",
            township="西三镇",
            altitude_m="1815",
            scalar_value="1100",
            unit="kg_per_mu",
            sample_weight="1",
            source_level="same_province_variety",
            source_name="synthetic",
            source_version="far-v1",
            historical_mape="0.10",
            date_mae_days="2",
            p90_coverage="0.85",
            available_at=date(2025, 5, 1),
            valid_from=date(2024, 1, 1),
            valid_to=None,
            source_row_hash="far-obs",
        )
        missing_coordinate_observation = ParameterObservation(
            library_version_id=library.id,
            parameter_type="yield_kg_per_mu",
            variety_id=variety_id,
            farm_id=None,
            subfarm_id=None,
            location_reference_id=None,
            climate_zone_id=zone.id,
            season_id=season_id,
            province="云南省",
            prefecture="红河州",
            county="弥勒市",
            township="西三镇",
            altitude_m="1820",
            scalar_value="1200",
            unit="kg_per_mu",
            sample_weight="1",
            source_level="same_province_variety",
            source_name="synthetic",
            source_version="missing-coord-v1",
            historical_mape="0.10",
            date_mae_days="2",
            p90_coverage="0.85",
            available_at=date(2025, 5, 1),
            valid_from=date(2024, 1, 1),
            valid_to=None,
            source_row_hash="missing-obs",
        )
        session.add_all([near_observation, far_observation, missing_coordinate_observation])
        await session.flush()
        near_observation_id = near_observation.id
        far_observation_id = far_observation.id
        await session.commit()

        result = await create_minimal_planning_task(
            session,
            payload={
                "location": {"address": "云南省 红河州 弥勒市 西三镇"},
                "varieties": [{"variety_code": "DX", "planted_area_mu": "700"}],
                "as_of_date": "2026-01-01",
            },
            config=config,
            dry_run=False,
        )

    yield_row = result.variety_parameters[0]["yield_kg_per_mu"]
    expected_min_distance = haversine_distance_km(24.4, 103.4, 24.401, 103.401)
    expected_max_distance = haversine_distance_km(24.4, 103.4, 24.47, 103.47)
    assert result.status == "completed"
    assert yield_row["source_observation_ids"][0] == near_observation_id
    assert yield_row["source_observation_ids"][1] == far_observation_id
    assert yield_row["distance_range_km"] == {
        "min": str(expected_min_distance),
        "max": str(expected_max_distance),
    }
    assert "historical_coordinates" in yield_row["missing_evidence"]


@pytest.mark.asyncio
async def test_create_minimal_planning_task_rejects_future_active_library_version(
    tmp_path: Path,
) -> None:
    _require_postgres()
    await _seed_master_data()
    zone_csv = tmp_path / "agro_climate_zones.csv"
    location_csv = tmp_path / "farm_location_master.csv"
    parameter_csv = tmp_path / "parameter_observations.csv"
    config_path = tmp_path / "parameter_inference.yaml"
    _write_zone_csv(zone_csv)
    _write_location_csv(location_csv)
    _write_parameter_csv(parameter_csv)
    _write_parameter_config(config_path)
    config = load_parameter_inference_config(config_path)

    async with AsyncSessionMaker() as session:
        await import_agro_climate_zones_csv(session, file_path=zone_csv, dry_run=False)
        await import_location_references_csv(
            session,
            file_path=location_csv,
            source_version="loc-v1",
            dry_run=False,
        )
        await import_parameter_library_csv(
            session,
            file_path=parameter_csv,
            version_code="lib-v1",
            activate=True,
            dry_run=False,
        )
        library = await session.scalar(
            select(ParameterLibraryVersion).where(ParameterLibraryVersion.version_code == "lib-v1")
        )
        assert library is not None
        library.effective_from = date(2026, 6, 1)
        await session.commit()

        with pytest.raises(ValueError):
            await create_minimal_planning_task(
                session,
                payload={
                    "location": {"address": "云南省 红河州 弥勒市 西三镇"},
                    "varieties": [{"variety_code": "DX", "planted_area_mu": "700"}],
                    "as_of_date": "2026-01-01",
                },
                config=config,
                dry_run=False,
            )


@pytest.mark.asyncio
async def test_create_minimal_planning_task_rejects_explicit_future_library_version(
    tmp_path: Path,
) -> None:
    _require_postgres()
    await _seed_master_data()
    zone_csv = tmp_path / "agro_climate_zones.csv"
    location_csv = tmp_path / "farm_location_master.csv"
    parameter_csv = tmp_path / "parameter_observations.csv"
    config_path = tmp_path / "parameter_inference.yaml"
    _write_zone_csv(zone_csv)
    _write_location_csv(location_csv)
    _write_parameter_csv(parameter_csv)
    _write_parameter_config(config_path)
    config = load_parameter_inference_config(config_path)

    async with AsyncSessionMaker() as session:
        await import_agro_climate_zones_csv(session, file_path=zone_csv, dry_run=False)
        await import_location_references_csv(
            session,
            file_path=location_csv,
            source_version="loc-v1",
            dry_run=False,
        )
        await import_parameter_library_csv(
            session,
            file_path=parameter_csv,
            version_code="lib-future",
            activate=True,
            dry_run=False,
        )
        await _set_library_effective_from(
            session,
            version_code="lib-future",
            effective_from=date(2026, 6, 1),
        )

        with pytest.raises(ValueError):
            await create_minimal_planning_task(
                session,
                payload={
                    "location": {"address": "云南省 红河州 弥勒市 西三镇"},
                    "varieties": [{"variety_code": "DX", "planted_area_mu": "700"}],
                    "as_of_date": "2026-01-01",
                },
                config=config,
                dry_run=False,
                library_version_code="lib-future",
            )


@pytest.mark.asyncio
async def test_create_minimal_planning_task_auto_selects_latest_effective_library_version(
    tmp_path: Path,
) -> None:
    _require_postgres()
    season_id, variety_id = await _seed_master_data()
    config_path = tmp_path / "parameter_inference.yaml"
    _write_parameter_config(config_path)
    config = load_parameter_inference_config(config_path)

    async with AsyncSessionMaker() as session:
        zone = AgroClimateZone(
            code="ZONE-A",
            name="Zone A",
            country="China",
            province="云南省",
            prefecture="红河州",
            county="弥勒市",
            centroid_latitude="24.400000",
            centroid_longitude="103.400000",
            min_altitude_m="1700",
            max_altitude_m="1900",
            zone_version="zone-v1",
            valid_from=date(2024, 1, 1),
            valid_to=None,
            source_name="synthetic",
            source_version="src-v1",
        )
        reference = LocationReference(
            farm_id=None,
            subfarm_id=None,
            farm_code="target",
            farm_name="目标农场",
            subfarm_name=None,
            address_raw="云南省 红河州 弥勒市 西三镇",
            address_normalized="云南省 红河州 弥勒市 西三镇",
            province="云南省",
            prefecture="红河州",
            county="弥勒市",
            township="西三镇",
            village=None,
            latitude="24.400000",
            longitude="103.400000",
            altitude_m="1800",
            climate_zone_id=None,
            location_source="synthetic",
            source_version="loc-v1",
            valid_from=date(2024, 1, 1),
            valid_to=None,
            source_row_hash="target-row",
        )
        session.add(zone)
        await session.flush()
        reference.climate_zone_id = zone.id
        session.add(reference)
        await session.flush()
        retired_library = ParameterLibraryVersion(
            version_code="lib-old",
            status="retired",
            source_name="synthetic.csv",
            source_file_sha256="sha-old",
            config_hash="cfg-old",
            record_count=0,
            effective_from=date(2024, 1, 1),
        )
        active_future_library = ParameterLibraryVersion(
            version_code="lib-new",
            status="active",
            source_name="synthetic.csv",
            source_file_sha256="sha-new",
            config_hash="cfg-new",
            record_count=0,
            effective_from=date(2026, 6, 1),
        )
        session.add_all([retired_library, active_future_library])
        await session.flush()
        session.add(
            ParameterObservation(
                library_version_id=retired_library.id,
                parameter_type="yield_kg_per_mu",
                variety_id=variety_id,
                farm_id=None,
                subfarm_id=None,
                location_reference_id=reference.id,
                climate_zone_id=zone.id,
                season_id=season_id,
                province="云南省",
                prefecture="红河州",
                county="弥勒市",
                township="西三镇",
                altitude_m="1800",
                scalar_value="900",
                unit="kg_per_mu",
                sample_weight="1",
                source_level="same_province_variety",
                source_name="synthetic",
                source_version="old-v1",
                historical_mape="0.10",
                date_mae_days="2",
                p90_coverage="0.85",
                available_at=date(2025, 5, 1),
                valid_from=date(2024, 1, 1),
                valid_to=None,
                source_row_hash="old-obs",
            )
        )
        await session.commit()

        result = await create_minimal_planning_task(
            session,
            payload={
                "location": {"address": "云南省 红河州 弥勒市 西三镇"},
                "varieties": [{"variety_code": "DX", "planted_area_mu": "700"}],
                "as_of_date": "2026-01-01",
            },
            config=config,
            dry_run=False,
        )

    assert result.status == "completed"
    assert result.library_version == "lib-old"


@pytest.mark.asyncio
async def test_minimal_planning_task_fails_without_reference_zone_and_no_run(
    tmp_path: Path,
) -> None:
    _require_postgres()
    await _seed_master_data()
    location_csv = tmp_path / "farm_location_master.csv"
    parameter_csv = tmp_path / "parameter_observations.csv"
    config_path = tmp_path / "parameter_inference.yaml"
    _write_location_csv(location_csv)
    _write_parameter_csv(parameter_csv)
    _write_parameter_config(config_path)
    config = load_parameter_inference_config(config_path)

    async with AsyncSessionMaker() as session:
        await import_location_references_csv(
            session,
            file_path=location_csv,
            source_version="loc-v1",
            dry_run=False,
        )
        await import_parameter_library_csv(
            session,
            file_path=parameter_csv,
            version_code="lib-v1",
            activate=True,
            dry_run=False,
        )
        await _set_library_effective_from(
            session,
            version_code="lib-v1",
            effective_from=date(2024, 1, 1),
        )
        reference = await session.scalar(select(LocationReference))
        assert reference is not None
        reference.climate_zone_id = None
        await session.commit()

        result = await create_minimal_planning_task(
            session,
            payload={
                "location": {"address": "云南省 红河州 弥勒市 西三镇"},
                "varieties": [{"variety_code": "DX", "planted_area_mu": "700"}],
                "as_of_date": "2026-01-01",
            },
            config=config,
            dry_run=False,
        )
        run_count = int(
            await session.scalar(select(func.count()).select_from(ParameterInferenceRun)) or 0
        )

    assert result.status == "failed"
    assert result.run_id is None
    assert result.resolved_location["status"] == "unresolved"
    assert "climate_zone_unresolved" in result.resolved_location["warnings"]
    assert run_count == 0


@pytest.mark.asyncio
async def test_minimal_planning_task_fails_for_bad_reference_zones_and_no_run(
    tmp_path: Path,
) -> None:
    _require_postgres()
    _, variety_id = await _seed_master_data()
    config_path = tmp_path / "parameter_inference.yaml"
    _write_parameter_config(config_path)
    config = load_parameter_inference_config(config_path)

    async with AsyncSessionMaker() as session:
        active_library = ParameterLibraryVersion(
            version_code="lib-v1",
            status="active",
            source_name="synthetic.csv",
            source_file_sha256="sha",
            config_hash="cfg",
            record_count=0,
            effective_from=date(2024, 1, 1),
        )
        expired_zone = AgroClimateZone(
            code="ZONE-EXPIRED",
            name="Expired Zone",
            country="China",
            province="云南省",
            prefecture="红河州",
            county="弥勒市",
            centroid_latitude="24.400000",
            centroid_longitude="103.400000",
            min_altitude_m="1700",
            max_altitude_m="1900",
            zone_version="zone-v1",
            valid_from=date(2024, 1, 1),
            valid_to=date(2025, 12, 31),
            source_name="synthetic",
            source_version="src-v1",
        )
        conflict_zone_a = AgroClimateZone(
            code="ZONE-CONFLICT",
            name="Conflict Zone A",
            country="China",
            province="云南省",
            prefecture="红河州",
            county="弥勒市",
            centroid_latitude="24.410000",
            centroid_longitude="103.410000",
            min_altitude_m="1700",
            max_altitude_m="1900",
            zone_version="zone-v1",
            valid_from=date(2024, 1, 1),
            valid_to=None,
            source_name="synthetic",
            source_version="src-v1",
        )
        conflict_zone_b = AgroClimateZone(
            code="ZONE-CONFLICT",
            name="Conflict Zone B",
            country="China",
            province="云南省",
            prefecture="红河州",
            county="弥勒市",
            centroid_latitude="24.420000",
            centroid_longitude="103.420000",
            min_altitude_m="1700",
            max_altitude_m="1900",
            zone_version="zone-v2",
            valid_from=date(2024, 1, 1),
            valid_to=None,
            source_name="synthetic",
            source_version="src-v2",
        )
        session.add_all([active_library, expired_zone, conflict_zone_a, conflict_zone_b])
        await session.flush()
        references = {
            "missing": LocationReference(
                farm_id=None,
                subfarm_id=None,
                farm_code="missing-zone",
                farm_name="无气候区农场",
                subfarm_name=None,
                address_raw="云南省 红河州 弥勒市 西三镇 缺失",
                address_normalized="云南省 红河州 弥勒市 西三镇 缺失",
                province="云南省",
                prefecture="红河州",
                county="弥勒市",
                township="西三镇",
                village=None,
                latitude="24.400000",
                longitude="103.400000",
                altitude_m="1800",
                climate_zone_id=None,
                location_source="synthetic",
                source_version="loc-v1",
                valid_from=date(2024, 1, 1),
                valid_to=None,
                source_row_hash="missing-zone",
            ),
            "invalid": LocationReference(
                farm_id=None,
                subfarm_id=None,
                farm_code="invalid-zone",
                farm_name="无效气候区农场",
                subfarm_name=None,
                address_raw="云南省 红河州 弥勒市 西三镇 无效",
                address_normalized="云南省 红河州 弥勒市 西三镇 无效",
                province="云南省",
                prefecture="红河州",
                county="弥勒市",
                township="西三镇",
                village=None,
                latitude="24.401000",
                longitude="103.401000",
                altitude_m="1800",
                climate_zone_id=999999,
                location_source="synthetic",
                source_version="loc-v1",
                valid_from=date(2024, 1, 1),
                valid_to=None,
                source_row_hash="invalid-zone",
            ),
            "expired": LocationReference(
                farm_id=None,
                subfarm_id=None,
                farm_code="expired-zone",
                farm_name="过期气候区农场",
                subfarm_name=None,
                address_raw="云南省 红河州 弥勒市 西三镇 过期",
                address_normalized="云南省 红河州 弥勒市 西三镇 过期",
                province="云南省",
                prefecture="红河州",
                county="弥勒市",
                township="西三镇",
                village=None,
                latitude="24.402000",
                longitude="103.402000",
                altitude_m="1800",
                climate_zone_id=expired_zone.id,
                location_source="synthetic",
                source_version="loc-v1",
                valid_from=date(2024, 1, 1),
                valid_to=None,
                source_row_hash="expired-zone",
            ),
            "conflict": LocationReference(
                farm_id=None,
                subfarm_id=None,
                farm_code="conflict-zone",
                farm_name="冲突气候区农场",
                subfarm_name=None,
                address_raw="云南省 红河州 弥勒市 西三镇 冲突",
                address_normalized="云南省 红河州 弥勒市 西三镇 冲突",
                province="云南省",
                prefecture="红河州",
                county="弥勒市",
                township="西三镇",
                village=None,
                latitude="24.403000",
                longitude="103.403000",
                altitude_m="1800",
                climate_zone_id=conflict_zone_a.id,
                location_source="synthetic",
                source_version="loc-v1",
                valid_from=date(2024, 1, 1),
                valid_to=None,
                source_row_hash="conflict-zone",
            ),
        }
        session.add_all(references.values())
        await session.commit()

        for reference_id, warning in (
            (references["missing"].id, "climate_zone_unresolved"),
            (references["invalid"].id, "climate_zone_not_valid_as_of_date"),
            (references["expired"].id, "climate_zone_not_valid_as_of_date"),
            (references["conflict"].id, "climate_zone_conflict"),
        ):
            result = await create_minimal_planning_task(
                session,
                payload={
                    "location": {"location_reference_id": reference_id},
                    "varieties": [{"variety_id": variety_id, "planted_area_mu": "700"}],
                    "as_of_date": "2026-01-01",
                },
                config=config,
                dry_run=False,
            )
            run_count = int(
                await session.scalar(
                    select(func.count()).select_from(ParameterInferenceRun)
                )
                or 0
            )
            assert result.status == "failed"
            assert result.run_id is None
            assert result.resolved_location["status"] == "unresolved"
            assert warning in result.resolved_location["warnings"]
            assert run_count == 0


@pytest.mark.asyncio
async def test_create_minimal_planning_task_coordinate_without_zone_candidates_does_not_create_run(
    tmp_path: Path,
) -> None:
    _require_postgres()
    _, variety_id = await _seed_master_data()
    config_path = tmp_path / "parameter_inference.yaml"
    _write_parameter_config(config_path)
    config = load_parameter_inference_config(config_path)

    async with AsyncSessionMaker() as session:
        session.add(
            ParameterLibraryVersion(
                version_code="lib-v1",
                status="active",
                source_name="synthetic.csv",
                source_file_sha256="sha",
                config_hash="cfg",
                record_count=0,
                effective_from=date(2024, 1, 1),
            )
        )
        await session.commit()

        result = await create_minimal_planning_task(
            session,
            payload={
                "location": {"latitude": "24.400000", "longitude": "103.400000"},
                "varieties": [{"variety_id": variety_id, "planted_area_mu": "700"}],
                "as_of_date": "2026-01-01",
            },
            config=config,
            dry_run=False,
        )
        run_count = int(
            await session.scalar(select(func.count()).select_from(ParameterInferenceRun)) or 0
        )

    assert result.status == "failed"
    assert result.run_id is None
    assert result.resolved_location["status"] == "unresolved"
    assert "climate_zone_unresolved" in result.resolved_location["warnings"]
    assert run_count == 0


@pytest.mark.asyncio
async def test_load_candidates_applies_township_altitude_and_county_matching_rules(
    tmp_path: Path,
) -> None:
    _require_postgres()
    season_id, variety_id = await _seed_master_data()
    config_path = tmp_path / "parameter_inference.yaml"
    _write_parameter_config(config_path)
    config = load_parameter_inference_config(config_path)

    async with AsyncSessionMaker() as session:
        library = ParameterLibraryVersion(
            version_code="lib-v1",
            status="active",
            source_name="synthetic.csv",
            source_file_sha256="sha",
            config_hash="cfg",
            record_count=0,
            effective_from=date(2024, 1, 1),
        )
        session.add(library)
        await session.flush()
        session.add_all(
            [
                ParameterObservation(
                    library_version_id=library.id,
                    parameter_type="yield_kg_per_mu",
                    variety_id=variety_id,
                    farm_id=None,
                    subfarm_id=None,
                    location_reference_id=None,
                    climate_zone_id=10,
                    season_id=season_id,
                    province="云南省",
                    prefecture="红河州",
                    county="弥勒市",
                    township="西三镇",
                    altitude_m="2605",
                    scalar_value="1000",
                    unit="kg_per_mu",
                    sample_weight="1",
                    source_level="same_province_variety",
                    source_name="synthetic",
                    source_version="obs-high-alt",
                    historical_mape="0.10",
                    date_mae_days="2",
                    p90_coverage="0.85",
                    available_at=date(2025, 5, 1),
                    valid_from=date(2024, 1, 1),
                    valid_to=None,
                    source_row_hash="obs-high-alt",
                ),
                ParameterObservation(
                    library_version_id=library.id,
                    parameter_type="yield_kg_per_mu",
                    variety_id=variety_id,
                    farm_id=None,
                    subfarm_id=None,
                    location_reference_id=None,
                    climate_zone_id=10,
                    season_id=season_id,
                    province="四川省",
                    prefecture="红河州",
                    county="弥勒市",
                    township="其他镇",
                    altitude_m="1800",
                    scalar_value="1100",
                    unit="kg_per_mu",
                    sample_weight="1",
                    source_level="same_province_variety",
                    source_name="synthetic",
                    source_version="obs-cross-province",
                    historical_mape="0.10",
                    date_mae_days="2",
                    p90_coverage="0.85",
                    available_at=date(2025, 5, 1),
                    valid_from=date(2024, 1, 1),
                    valid_to=None,
                    source_row_hash="obs-cross-province",
                ),
                ParameterObservation(
                    library_version_id=library.id,
                    parameter_type="yield_kg_per_mu",
                    variety_id=variety_id,
                    farm_id=None,
                    subfarm_id=None,
                    location_reference_id=None,
                    climate_zone_id=10,
                    season_id=season_id,
                    province="云南省",
                    prefecture="红河州",
                    county="弥勒市",
                    township="西三镇",
                    altitude_m="1810",
                    scalar_value="1200",
                    unit="kg_per_mu",
                    sample_weight="1",
                    source_level="same_province_variety",
                    source_name="synthetic",
                    source_version="obs-good-alt",
                    historical_mape="0.10",
                    date_mae_days="2",
                    p90_coverage="0.85",
                    available_at=date(2025, 5, 1),
                    valid_from=date(2024, 1, 1),
                    valid_to=None,
                    source_row_hash="obs-good-alt",
                ),
                ParameterObservation(
                    library_version_id=library.id,
                    parameter_type="yield_kg_per_mu",
                    variety_id=variety_id,
                    farm_id=None,
                    subfarm_id=None,
                    location_reference_id=None,
                    climate_zone_id=10,
                    season_id=season_id,
                    province="云南省",
                    prefecture="曲靖市",
                    county="弥勒市",
                    township="其他镇",
                    altitude_m="1800",
                    scalar_value="1300",
                    unit="kg_per_mu",
                    sample_weight="1",
                    source_level="same_province_variety",
                    source_name="synthetic",
                    source_version="obs-cross-prefecture",
                    historical_mape="0.10",
                    date_mae_days="2",
                    p90_coverage="0.85",
                    available_at=date(2025, 5, 1),
                    valid_from=date(2024, 1, 1),
                    valid_to=None,
                    source_row_hash="obs-cross-prefecture",
                ),
                ParameterObservation(
                    library_version_id=library.id,
                    parameter_type="yield_kg_per_mu",
                    variety_id=variety_id,
                    farm_id=None,
                    subfarm_id=None,
                    location_reference_id=None,
                    climate_zone_id=10,
                    season_id=season_id,
                    province="云南省",
                    prefecture="红河州",
                    county="弥勒市",
                    township="西三镇",
                    altitude_m=None,
                    scalar_value="1400",
                    unit="kg_per_mu",
                    sample_weight="1",
                    source_level="same_province_variety",
                    source_name="synthetic",
                    source_version="obs-missing-alt",
                    historical_mape="0.10",
                    date_mae_days="2",
                    p90_coverage="0.85",
                    available_at=date(2025, 5, 1),
                    valid_from=date(2024, 1, 1),
                    valid_to=None,
                    source_row_hash="obs-missing-alt",
                ),
            ]
        )
        await session.commit()

        candidates = await _load_candidates(
            session,
            library_version_id=library.id,
            variety_id=variety_id,
            as_of_date=date(2026, 1, 1),
            resolved_location={
                "province": "云南省",
                "prefecture": "红河州",
                "county": "弥勒市",
                "township": "西三镇",
                "farm_name": None,
                "climate_zone_id": 10,
                "altitude_m": Decimal("1800"),
                "latitude": Decimal("24.400000"),
                "longitude": Decimal("103.400000"),
            },
            rules=config,
        )

    by_version = {candidate.source_version: candidate.source_level for candidate in candidates}
    assert by_version["obs-high-alt"] == "same_province_variety"
    assert by_version["obs-cross-province"] == "literature_variety_prior"
    assert by_version["obs-good-alt"] == "same_township_altitude_variety"
    assert by_version["obs-cross-prefecture"] == "same_province_variety"
    assert by_version["obs-missing-alt"] == "same_county_climate_zone_variety"
