"""Synthetic weather fixtures test software, never establish real source completeness."""

import json
import socket
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from scripts.build_era5_land_historical_weather_r1 import nearest, plan, utc_bounds
from scripts.climate_source_r2 import digest, file_hash
from scripts.normalize_era5_land_historical_weather_r1 import (
    UNITS,
    accumulation,
    audit_accumulations,
    canonical_line,
    local_day,
    no_network,
    number,
    read_native,
    replay,
    validate_rows,
)

pytestmark = pytest.mark.unit
CONFIG = Path("configs/era5_land_historical_weather_r1.json")


def test_crs_authorization_is_query_assumption_not_authority_upgrade():
    c = json.loads(CONFIG.read_text())
    assert c["location_crs_authorization"] == "GRANTED_WITH_WGS84_QUERY_ASSUMPTION"
    assert c["query_crs_assumption"] == "WGS84"
    assert c["crs_verification_status"] == "NOT_ESTABLISHED"
    assert c["source_coordinate_status"] == "RANGE_VALID_CRS_UNCONFIRMED"
    for key in (
        "base_coordinate_authority_changed",
        "base_crs_authority_changed",
        "crs_authority_upgrade_authorized",
        "climate_zone_authority_used",
        "weather_model_training",
        "weather_incremental_value_scoring",
        "weather_source_authority_frozen",
        "live_weather_forecast_authority_frozen",
    ):
        assert c[key] is False
    assert c["strict_operational_forecast_replay_blocked"] is True
    assert c["expected_base_count"] == 38
    assert len(c["variables"]) == 6


@pytest.mark.parametrize(
    "value,expected", [("22.45", "22.4"), ("99.85", "99.8"), ("23.46", "23.5")]
)
def test_nearest_tie_and_no_interpolation(value, expected):
    assert nearest(value) == expected


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "0"])
def test_coordinate_invalid(value):
    with pytest.raises(ValueError):
        nearest(value)


def registry_fixture(tmp_path):
    path = tmp_path / "registry.json"
    rows = [
        {
            "base_id": f"b{i:02d}",
            "canonical_base_name": f"SYNTHETIC{i}",
            "latitude": "25.0",
            "longitude": "102.0",
            "region_scope": "YUNNAN_CORE",
        }
        for i in range(38)
    ]
    path.write_text(json.dumps({"bases": rows}))
    cfg = json.loads(CONFIG.read_text())
    cfg["registry_file_sha256"] = file_hash(path)
    return path, rows, cfg


def test_38_base_plan_is_deterministic_and_reuses_cells(tmp_path):
    path, rows, cfg = registry_fixture(tmp_path)
    a = plan(path, cfg)
    assert a == plan(path, cfg)
    assert len(a["locations"]) == 38
    assert len(a["requests"]) == 33  # one grid cell, three padded seasons
    assert a["base_identity_set_hash"] == digest([r["base_id"] for r in rows])
    assert all(r["request"]["area"] == [25.0, 102.0, 25.0, 102.0] for r in a["requests"])
    assert a["config"]["query_crs_assumption"] == "WGS84"
    assert a["config"]["crs_authority_upgrade_authorized"] is False


@pytest.mark.parametrize(
    "field",
    ["climate_zone_authority_used", "weather_model_training", "crs_authority_upgrade_authorized"],
)
def test_forbidden_authority_and_training_flags_block(tmp_path, field):
    path, _, cfg = registry_fixture(tmp_path)
    cfg[field] = True
    with pytest.raises(ValueError, match="FROZEN_RESEARCH_CONTRACT"):
        plan(path, cfg)


@pytest.mark.parametrize("mutation", ["missing", "count", "duplicate", "range", "tamper"])
def test_registry_fails_closed_no_name_geocoding(tmp_path, monkeypatch, mutation):
    monkeypatch.setattr(socket, "create_connection", no_network)
    path, rows, cfg = registry_fixture(tmp_path)
    if mutation == "missing":
        rows[0]["latitude"] = None
    if mutation == "count":
        rows.pop()
    if mutation == "duplicate":
        rows[0]["base_id"] = rows[1]["base_id"]
    if mutation == "range":
        rows[0]["latitude"] = "0"
    path.write_text(json.dumps({"bases": rows}) + "\n")
    if mutation != "tamper":
        cfg["registry_file_sha256"] = file_hash(path)
    with pytest.raises(ValueError):
        plan(path, cfg)


def native_fixture(start):
    rows = {}
    for i in range(25):
        t = start + timedelta(hours=i)
        step = t.hour or 24
        for var in UNITS:
            value = {
                "tp": step * 0.001,
                "ssrd": step * 100.0,
                "t2m": 280.0,
                "d2m": 277.0,
                "u10": 3.0,
                "v10": 4.0,
            }[var]
            rows[(var, t)] = (value, "0" * 64)
    return rows


def test_local_full_day_and_accumulation_reset():
    a, z = utc_bounds("2024-02-29", "2024-02-29")
    assert a == datetime(2024, 2, 28, 16, tzinfo=UTC)
    assert z - a == timedelta(hours=24)
    rows, daily = local_day(native_fixture(a), a)
    assert len(rows) == 144
    assert {r["local_date"] for r in rows} == {"2024-02-29"}
    assert daily["local_day_precipitation_mm"] == "24.000000000000"
    assert daily["local_day_solar_energy_j_m2"] == "2400.000000000000"
    assert daily["local_day_mean_wind_speed_10m_m_s"] == "5.000000000000"
    assert daily["sampled_local_day_tmin_c"] == "6.850000000000"
    assert daily["sampled_local_day_tmax_c"] == "6.850000000000"
    assert not any(
        k in json.dumps(daily).lower() for k in ("gdd", "vpd", "et0", "relative_humidity")
    )


@pytest.mark.parametrize("hour", [0, 8, 24])
def test_missing_hour_or_local_boundary_fails(hour):
    a, _ = utc_bounds("2024-01-01", "2024-01-01")
    rows = native_fixture(a)
    del rows[("tp" if hour == 24 else "t2m", a + timedelta(hours=hour))]
    with pytest.raises(ValueError, match="HOURLY_GAP"):
        local_day(rows, a)


@pytest.mark.parametrize("var", ["tp", "ssrd"])
def test_accumulation_negative_and_predecessor_gap(var):
    t = datetime(2024, 1, 1, 0, tzinfo=UTC)
    with pytest.raises(ValueError, match="NEGATIVE_ACCUMULATION"):
        accumulation(1.0, 2.0, t)
    with pytest.raises(ValueError, match="MISSING_ACCUMULATION"):
        accumulation(1.0, None, t)
    assert accumulation(2.0, 999.0, t.replace(hour=1)) == 2.0
    with pytest.raises(ValueError):
        accumulation(float("nan"), 1.0, t)


def test_numeric_serialization_caller_context_independent():
    with localcontext() as c:
        c.prec = 4
        assert number(1.125) == "1.125000000000"
    assert number(Decimal("-0")) == "0.000000000000"


def write_native(path, duplicate=False, bad_unit=False):
    times = np.array(["2024-01-01T16", "2024-01-01T17"], dtype="datetime64[h]")
    if duplicate:
        times[1] = times[0]
    ds = xr.Dataset(
        {
            v: (
                ("valid_time", "latitude", "longitude"),
                np.ones((2, 1, 1)),
                {
                    "units": "wrong" if bad_unit else UNITS[v][0],
                    "GRIB_stepType": "accum" if v in {"tp", "ssrd"} else "instant",
                    "GRIB_stepUnits": 1,
                },
            )
            for v in UNITS
        },
        coords={"valid_time": times, "latitude": [25.0], "longitude": [102.0]},
    )
    ds.to_netcdf(path, engine="h5netcdf")


@pytest.mark.parametrize(
    "duplicate,bad_unit,lat", [(True, False, "25"), (False, True, "25"), (False, False, "26")]
)
def test_raw_duplicate_unit_grid_rejected(tmp_path, duplicate, bad_unit, lat):
    path = tmp_path / "raw.nc"
    write_native(path, duplicate, bad_unit)
    with pytest.raises(ValueError):
        read_native(path, lat, "102")


def test_row_and_set_hash_tamper(tmp_path):
    p = tmp_path / "hourly.jsonl"
    row = {"value": "1.000000000000"}
    p.write_bytes(canonical_line({**row, "row_hash": digest(row)}))
    h = file_hash(p)
    assert validate_rows(p, h) == 1
    p.write_text(p.read_text().replace("1.000", "2.000"))
    with pytest.raises(ValueError, match="ROW_SET_HASH"):
        validate_rows(p, h)
    with pytest.raises(ValueError, match="NORMALIZED_ROW_HASH"):
        validate_rows(p, file_hash(p))


def test_two_offline_raw_replays_and_raw_tamper(tmp_path, monkeypatch):
    root = tmp_path / "raw"
    root.mkdir()
    a, _ = utc_bounds("2024-01-02", "2024-01-02")
    times = np.array(
        [(a + timedelta(hours=i)).replace(tzinfo=None) for i in range(25)], dtype="datetime64[ns]"
    )
    values = native_fixture(a)
    request = {"area": [25.0, 102.0, 25.0, 102.0]}
    key = digest(request)
    path = root / f"{key}.raw"
    xr.Dataset(
        {
            v: (
                ("valid_time", "latitude", "longitude"),
                np.array([values[(v, a + timedelta(hours=i))][0] for i in range(25)]).reshape(
                    25, 1, 1
                ),
                {
                    "units": UNITS[v][0],
                    "GRIB_stepType": "accum" if v in {"tp", "ssrd"} else "instant",
                    "GRIB_stepUnits": 1,
                },
            )
            for v in UNITS
        },
        coords={"valid_time": times, "latitude": [25.0], "longitude": [102.0]},
    ).to_netcdf(path, engine="h5netcdf")
    manifest = {
        "requests": [{"request_id": key, "request": request}],
        "locations": [
            {
                "base_id": "SYNTHETIC",
                "selected_grid_latitude": "25",
                "selected_grid_longitude": "102",
            }
        ],
        "config": {"date_windows": [["2024-01-02", "2024-01-02"]]},
    }
    (root / "request-manifest.json").write_text(
        json.dumps({**manifest, "manifest_hash": digest(manifest)})
    )
    (root / f"{key}.completed.json").write_text(
        json.dumps({"request_hash": key, "raw_sha256": file_hash(path)})
    )
    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    x = replay(root, tmp_path / "replay1")
    y = replay(root, tmp_path / "replay2")
    assert x == y
    assert x["hourly_row_count"] == 144 and x["daily_row_count"] == 1
    path.write_bytes(path.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="RAW_HASH"):
        replay(root, tmp_path / "bad")


def test_small_real_style_negative_is_reported_not_clipped():
    t = datetime(2023, 6, 30, 18, tzinfo=UTC)
    rows = {("tp", t - timedelta(hours=1)): 0.0010000001, ("tp", t): 0.001}
    before = dict(rows)
    errors = audit_accumulations(rows)
    assert len(errors) == 1
    assert errors[0]["clipped"] is False
    assert errors[0]["local_date"] == "2023-07-01"
    assert Decimal(errors[0]["native_difference"]) < 0
    assert rows == before


def test_reanalysis_still_fails_existing_pit_gate():
    from backend.tests.base_registry.test_weather_source_authority_r1 import sample
    from scripts.audit_weather_source_r1 import qualify

    result = qualify(
        sample().model_copy(
            update={
                "role": "HISTORICAL_ACTUAL_WEATHER",
                "generation_mode": "REANALYSIS",
            }
        )
    )
    assert result["pit_status"] == "PIT_NOT_ESTABLISHED"
    assert result["w7_pit_status"] == result["w15_pit_status"] == "BLOCKED"
