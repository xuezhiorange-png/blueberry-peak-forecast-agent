from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import AsyncSessionMaker
from backend.app.models.planning import (
    AgroClimateZone,
    ClimateZoneImportRun,
    LocationReference,
)
from backend.app.planning.config import load_parameter_inference_config
from backend.app.planning.importers import import_location_references_csv
from backend.app.planning.imports.climate_zone_importer import (
    import_agro_climate_zones_csv,
)
from backend.app.planning.location import resolve_location_input

pytestmark = pytest.mark.integration

CSV_HEADER = (
    "code,name,country,province,prefecture,county,centroid_latitude,"
    "centroid_longitude,min_altitude_m,max_altitude_m,zone_version,"
    "valid_from,valid_to,source_name,source_version\n"
)
LOCATION_HEADER = (
    "farm_code,farm_name,subfarm_name,address_raw,province,prefecture,county,"
    "township,village,latitude,longitude,altitude_m,climate_zone_code,"
    "location_source,source_version,valid_from,valid_to\n"
)


def _require_postgres() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("set RUN_POSTGRES_INTEGRATION=1 when PostgreSQL is available")


def _zone_row(
    *,
    code: str,
    name: str,
    province: str = "云南省",
    prefecture: str = "红河州",
    county: str = "弥勒市",
    latitude: str = "24.400000",
    longitude: str = "103.400000",
    min_altitude: str = "1700",
    max_altitude: str = "1900",
    zone_version: str = "zone-v1",
    valid_from: str = "2024-01-01",
    valid_to: str = "",
    source_name: str = "synthetic",
    source_version: str = "src-v1",
) -> str:
    return (
        ",".join(
            [
                code,
                name,
                "China",
                province,
                prefecture,
                county,
                latitude,
                longitude,
                min_altitude,
                max_altitude,
                zone_version,
                valid_from,
                valid_to,
                source_name,
                source_version,
            ]
        )
        + "\n"
    )


def _write_config(path: Path) -> None:
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


def _write_zone_csv(path: Path, rows: list[str]) -> None:
    path.write_text(CSV_HEADER + "".join(rows), encoding="utf-8")


def _write_location_csv(path: Path) -> None:
    path.write_text(
        LOCATION_HEADER
        + ",".join(
            [
                "farm-a",
                "农场A",
                "",
                "云南省 红河州 弥勒市 西三镇",
                "云南省",
                "红河州",
                "弥勒市",
                "西三镇",
                "",
                "24.400000",
                "103.400000",
                "1800",
                "ZONE-A",
                "synthetic",
                "loc-v1",
                "2024-01-01",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


async def _table_count(session: AsyncSession, model: object) -> int:
    return int(await session.scalar(select(func.count()).select_from(model)) or 0)


@pytest.mark.asyncio
async def test_climate_zone_import_is_idempotent_and_persists_audit(
    tmp_path: Path,
) -> None:
    _require_postgres()
    zone_csv = tmp_path / "agro_climate_zones.csv"
    _write_zone_csv(zone_csv, [_zone_row(code="zone-a", name="Zone A")])

    async with AsyncSessionMaker() as session:
        first = await import_agro_climate_zones_csv(
            session,
            file_path=zone_csv,
            dry_run=False,
        )
        second = await import_agro_climate_zones_csv(
            session,
            file_path=zone_csv,
            dry_run=False,
        )
        zone_count = await _table_count(session, AgroClimateZone)
        audit_count = await _table_count(session, ClimateZoneImportRun)

    assert first.status == "completed"
    assert second.status == "completed"
    assert second.inserted_rows == 0
    assert second.skipped_rows >= 1
    assert zone_count == 1
    assert audit_count == 2


@pytest.mark.asyncio
async def test_climate_zone_import_conflict_does_not_overwrite_existing_zone(
    tmp_path: Path,
) -> None:
    _require_postgres()
    first_csv = tmp_path / "zones_v1.csv"
    second_csv = tmp_path / "zones_conflict.csv"
    _write_zone_csv(first_csv, [_zone_row(code="zone-a", name="Zone A")])
    _write_zone_csv(
        second_csv,
        [_zone_row(code="zone-a", name="Zone A Updated")],
    )

    async with AsyncSessionMaker() as session:
        await import_agro_climate_zones_csv(session, file_path=first_csv, dry_run=False)
        conflict = await import_agro_climate_zones_csv(
            session,
            file_path=second_csv,
            dry_run=False,
        )
        zones = (
            await session.scalars(select(AgroClimateZone).order_by(AgroClimateZone.id.asc()))
        ).all()

    assert conflict.status == "failed"
    assert conflict.conflict_rows == 1
    assert len(zones) == 1
    assert zones[0].name == "Zone A"


@pytest.mark.asyncio
async def test_climate_zone_import_dry_run_is_zero_write(tmp_path: Path) -> None:
    _require_postgres()
    zone_csv = tmp_path / "agro_climate_zones.csv"
    _write_zone_csv(zone_csv, [_zone_row(code="zone-a", name="Zone A")])

    async with AsyncSessionMaker() as session:
        result = await import_agro_climate_zones_csv(
            session,
            file_path=zone_csv,
            dry_run=True,
        )
        zone_count = await _table_count(session, AgroClimateZone)
        audit_count = await _table_count(session, ClimateZoneImportRun)

    assert result.status == "dry_run"
    assert zone_count == 0
    assert audit_count == 0


@pytest.mark.asyncio
async def test_climate_zone_import_integrates_with_location_reference_and_resolver(
    tmp_path: Path,
) -> None:
    _require_postgres()
    zone_csv = tmp_path / "agro_climate_zones.csv"
    location_csv = tmp_path / "farm_location_master.csv"
    config_path = tmp_path / "parameter_inference.yaml"
    _write_zone_csv(zone_csv, [_zone_row(code="zone-a", name="Zone A")])
    _write_location_csv(location_csv)
    _write_config(config_path)
    config = load_parameter_inference_config(config_path)

    async with AsyncSessionMaker() as session:
        await import_agro_climate_zones_csv(session, file_path=zone_csv, dry_run=False)
        await import_location_references_csv(
            session,
            file_path=location_csv,
            source_version="loc-v1",
            dry_run=False,
        )
        location_reference = await session.scalar(select(LocationReference))
        assert location_reference is not None
        resolved = await resolve_location_input(
            session,
            location={"location_reference_id": location_reference.id},
            as_of_date=date(2025, 1, 1),
            rules=config.rules,
        )

    assert location_reference.climate_zone_id is not None
    assert resolved.status == "resolved"
    assert resolved.climate_zone_code == "ZONE-A"
    assert resolved.climate_zone_version == "zone-v1"


@pytest.mark.asyncio
async def test_climate_zone_resolver_reports_conflict_for_multiple_effective_versions(
    tmp_path: Path,
) -> None:
    _require_postgres()
    zone_csv = tmp_path / "agro_climate_zones.csv"
    config_path = tmp_path / "parameter_inference.yaml"
    _write_zone_csv(
        zone_csv,
        [
            _zone_row(code="zone-a", name="Zone A", zone_version="zone-v1"),
            _zone_row(
                code="zone-b",
                name="Zone B",
                latitude="24.450000",
                longitude="103.450000",
                zone_version="zone-v2",
                source_version="src-v2",
            ),
        ],
    )
    _write_config(config_path)
    config = load_parameter_inference_config(config_path)

    async with AsyncSessionMaker() as session:
        await import_agro_climate_zones_csv(session, file_path=zone_csv, dry_run=False)
        resolved = await resolve_location_input(
            session,
            location={
                "latitude": "24.400000",
                "longitude": "103.400000",
                "county": "弥勒市",
            },
            as_of_date=date(2025, 1, 1),
            rules=config.rules,
        )

    assert resolved.status == "unresolved"
    assert "climate_zone_conflict" in resolved.warnings
