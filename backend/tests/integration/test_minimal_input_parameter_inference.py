from __future__ import annotations

import csv
import os
from datetime import date
from pathlib import Path

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
from backend.app.planning.service import create_minimal_planning_task

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
        normalized_zone_code = normalize_climate_zone_code("zone-a")
        zone = await session.scalar(
            select(AgroClimateZone).where(AgroClimateZone.code == normalized_zone_code)
        )
        location_reference = await session.scalar(select(LocationReference))
        assert zone_result.inserted_rows == 1
        assert location_result.inserted_row_count == 1
        assert parameter_result.status in {"draft", "active"}
        assert zone is not None
        assert location_reference is not None
        assert location_reference.climate_zone_id == zone.id
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
