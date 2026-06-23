from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from backend.app.weather.provider import CsvWeatherProvider, WeatherValidationError


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_csv_provider_parses_location_rows(tmp_path: Path) -> None:
    provider = CsvWeatherProvider(
        file_path=_write(
            tmp_path / "locations.csv",
            "\n".join(
                [
                    "provider_code,external_location_id,location_type,name,latitude,longitude,altitude_m,timezone_name,grid_resolution,valid_from,valid_to,source_version,quality_flags",
                    (
                        "ignored,station-1,station,Station A,24.100000,102.200000,"
                        "1800,Asia/Shanghai,,2026-01-01,,dataset-v1,ok"
                    ),
                ]
            ),
        ),
        provider_code="synthetic_station",
        provider_version="provider-v1",
        dataset_version="dataset-v1",
        location_type="station",
    )

    rows = provider.parse_location_rows()

    assert len(rows) == 1
    row = rows[0]
    assert row.provider_code == "synthetic_station"
    assert row.provider_version == "provider-v1"
    assert row.dataset_version == "dataset-v1"
    assert row.external_location_id == "station-1"
    assert row.location_type == "station"
    assert row.latitude.as_tuple().exponent == -6
    assert row.valid_from == date(2026, 1, 1)
    assert row.valid_to is None
    assert row.quality_flags == ("ok",)


def test_csv_provider_derives_mean_temperature_when_missing(tmp_path: Path) -> None:
    provider = CsvWeatherProvider(
        file_path=_write(
            tmp_path / "observations.csv",
            "\n".join(
                [
                    "provider_code,external_location_id,observation_date,temperature_min_c,temperature_max_c,temperature_mean_c,precipitation_mm,solar_radiation_mj_m2,available_at,quality_code,quality_flags,source_version",
                    "ignored,station-1,2026-02-01,8,18,,3,14,2026-02-02,ok,ok,dataset-v1",
                ]
            ),
        ),
        provider_code="synthetic_station",
        provider_version="provider-v1",
        dataset_version="dataset-v1",
        location_type="station",
    )

    rows = provider.parse_observation_rows()

    assert len(rows) == 1
    row = rows[0]
    assert row.temperature_mean_source == "derived"
    assert str(row.temperature_mean_c) == "13"


def test_csv_provider_rejects_invalid_temperature_range(tmp_path: Path) -> None:
    provider = CsvWeatherProvider(
        file_path=_write(
            tmp_path / "observations.csv",
            "\n".join(
                [
                    "provider_code,external_location_id,observation_date,temperature_min_c,temperature_max_c,temperature_mean_c,precipitation_mm,solar_radiation_mj_m2,available_at,quality_code,quality_flags,source_version",
                    "ignored,station-1,2026-02-01,18,8,,3,14,2026-02-02,ok,ok,dataset-v1",
                ]
            ),
        ),
        provider_code="synthetic_station",
        provider_version="provider-v1",
        dataset_version="dataset-v1",
        location_type="station",
    )

    with pytest.raises(WeatherValidationError, match="temperature_max_c must be >="):
        provider.parse_observation_rows()


def test_csv_provider_rejects_negative_precipitation(tmp_path: Path) -> None:
    provider = CsvWeatherProvider(
        file_path=_write(
            tmp_path / "observations.csv",
            "\n".join(
                [
                    "provider_code,external_location_id,observation_date,temperature_min_c,temperature_max_c,temperature_mean_c,precipitation_mm,solar_radiation_mj_m2,available_at,quality_code,quality_flags,source_version",
                    "ignored,station-1,2026-02-01,8,18,13,-1,14,2026-02-02,ok,ok,dataset-v1",
                ]
            ),
        ),
        provider_code="synthetic_station",
        provider_version="provider-v1",
        dataset_version="dataset-v1",
        location_type="station",
    )

    with pytest.raises(WeatherValidationError, match="precipitation_mm must be non-negative"):
        provider.parse_observation_rows()
