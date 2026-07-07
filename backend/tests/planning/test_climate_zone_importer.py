from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app.planning.imports.climate_zone_importer import (
    ClimateZoneImportConflictError,
    build_climate_zone_file_sha256,
    build_climate_zone_row_hash,
    normalize_climate_zone_code,
    prepare_climate_zone_import,
)

CSV_HEADER = (
    "code,name,country,province,prefecture,county,centroid_latitude,"
    "centroid_longitude,min_altitude_m,max_altitude_m,zone_version,"
    "valid_from,valid_to,source_name,source_version\n"
)


def _zone_row(
    *,
    code: str = "zone-a",
    name: str = "Zone A",
    country: str = "China",
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
                country,
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


def _write_csv(path: Path, rows: list[str], *, encoding: str = "utf-8") -> None:
    path.write_text(CSV_HEADER + "".join(rows), encoding=encoding)


def test_normalize_climate_zone_code_uses_nfkc_trim_and_uppercase() -> None:
    assert normalize_climate_zone_code(" zone-a ") == "ZONE-A"


def test_build_climate_zone_row_hash_is_stable() -> None:
    payload = {
        "code": "ZONE-A",
        "name": "Zone A",
        "country": "China",
        "province": "云南省",
        "prefecture": "红河州",
        "county": "弥勒市",
        "centroid_latitude": Decimal("24.400000"),
        "centroid_longitude": Decimal("103.400000"),
        "min_altitude_m": Decimal("1700.00"),
        "max_altitude_m": Decimal("1900.00"),
        "zone_version": "zone-v1",
        "valid_from": date(2024, 1, 1),
        "valid_to": None,
        "source_name": "synthetic",
        "source_version": "src-v1",
    }

    assert build_climate_zone_row_hash(payload) == build_climate_zone_row_hash(payload)


def test_build_climate_zone_file_sha256_is_stable(tmp_path: Path) -> None:
    file_path = tmp_path / "agro_climate_zones.csv"
    _write_csv(file_path, [_zone_row()])

    assert build_climate_zone_file_sha256(file_path) == build_climate_zone_file_sha256(file_path)


def test_prepare_climate_zone_import_accepts_valid_csv(tmp_path: Path) -> None:
    file_path = tmp_path / "agro_climate_zones.csv"
    _write_csv(file_path, [_zone_row(name=" Zone A ")])

    prepared = prepare_climate_zone_import(file_path=file_path)

    assert prepared.total_rows == 1
    assert prepared.valid_rows == 1
    assert prepared.invalid_rows == 0
    assert prepared.zone_version == "zone-v1"
    assert prepared.rows[0].code == "ZONE-A"
    assert prepared.rows[0].province == "云南省"


def test_prepare_climate_zone_import_rejects_missing_required_field(tmp_path: Path) -> None:
    file_path = tmp_path / "agro_climate_zones.csv"
    _write_csv(file_path, [_zone_row(code="")])

    prepared = prepare_climate_zone_import(file_path=file_path)

    assert prepared.valid_rows == 0
    assert prepared.invalid_rows == 1
    assert prepared.error_rows[0].field == "code"


@pytest.mark.parametrize(
    ("latitude", "longitude", "field"),
    [
        ("91", "103.400000", "centroid_latitude"),
        ("24.400000", "181", "centroid_longitude"),
    ],
)
def test_prepare_climate_zone_import_rejects_coordinate_out_of_range(
    tmp_path: Path,
    latitude: str,
    longitude: str,
    field: str,
) -> None:
    file_path = tmp_path / "agro_climate_zones.csv"
    _write_csv(file_path, [_zone_row(latitude=latitude, longitude=longitude)])

    prepared = prepare_climate_zone_import(file_path=file_path)

    assert prepared.valid_rows == 0
    assert prepared.error_rows[0].field == field


def test_prepare_climate_zone_import_rejects_altitude_range(tmp_path: Path) -> None:
    file_path = tmp_path / "agro_climate_zones.csv"
    _write_csv(file_path, [_zone_row(min_altitude="1900", max_altitude="1700")])

    prepared = prepare_climate_zone_import(file_path=file_path)

    assert prepared.valid_rows == 0
    assert prepared.error_rows[0].field == "altitude_range"


def test_prepare_climate_zone_import_rejects_invalid_date_range(tmp_path: Path) -> None:
    file_path = tmp_path / "agro_climate_zones.csv"
    _write_csv(file_path, [_zone_row(valid_from="2024-01-02", valid_to="2024-01-01")])

    prepared = prepare_climate_zone_import(file_path=file_path)

    assert prepared.valid_rows == 0
    assert prepared.error_rows[0].field == "valid_to"


def test_prepare_climate_zone_import_marks_duplicate_identical_rows_as_skipped(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "agro_climate_zones.csv"
    row = _zone_row()
    _write_csv(file_path, [row, row])

    prepared = prepare_climate_zone_import(file_path=file_path)

    assert prepared.valid_rows == 2
    assert prepared.skipped_rows == 1
    assert prepared.rows_to_insert_count == 1


def test_prepare_climate_zone_import_rejects_conflicting_same_code_and_version(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "agro_climate_zones.csv"
    _write_csv(
        file_path,
        [
            _zone_row(),
            _zone_row(name="Zone A updated"),
        ],
    )

    with pytest.raises(ClimateZoneImportConflictError):
        prepare_climate_zone_import(file_path=file_path)


def test_prepare_climate_zone_import_result_is_json_serializable(tmp_path: Path) -> None:
    file_path = tmp_path / "agro_climate_zones.csv"
    _write_csv(file_path, [_zone_row()])

    prepared = prepare_climate_zone_import(file_path=file_path)
    payload = prepared.to_report_payload()

    assert payload["zone_version"] == "zone-v1"
    assert payload["rows"][0]["code"] == "ZONE-A"


def test_prepare_climate_zone_import_rejects_invalid_encoding(tmp_path: Path) -> None:
    file_path = tmp_path / "agro_climate_zones.csv"
    file_path.write_bytes("bad\xffcsv".encode("latin-1"))

    with pytest.raises(UnicodeDecodeError):
        prepare_climate_zone_import(file_path=file_path)
