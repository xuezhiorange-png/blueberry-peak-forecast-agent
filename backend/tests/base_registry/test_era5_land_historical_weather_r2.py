"""Official time-series adapter contracts, using only synthetic software fixtures."""

import json
import socket
import sys
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr

from scripts.build_era5_land_historical_weather_r2 import plan
from scripts.climate_source_r2 import digest, file_hash, write_json
from scripts.era5_timeseries_source_r2 import read_source, source_gate, validate_manifest
from scripts.normalize_era5_land_historical_weather_r1 import UNITS, no_network, validate_rows
from scripts.normalize_era5_land_historical_weather_r2 import local_day, replay, verified_source
from scripts.report_era5_land_historical_weather_r2 import report
from scripts.retrieve_era5_land_historical_weather_r2 import retrieve

pytestmark = pytest.mark.unit


def test_official_timeseries_contract_does_not_allow_custom_repairs():
    c = json.loads(Path("configs/era5_land_historical_weather_r2.json").read_text())
    assert c["source_product"] == "reanalysis-era5-land-timeseries"
    assert c["accumulated_variables"] == "PROVIDER_DEACCUMULATED_HOURLY"
    assert c["standard_path_status"] == "REJECTED_DIAGNOSTIC_SOURCE_PATH"
    for key in (
        "custom_deaccumulation",
        "custom_negative_clipping",
        "custom_accumulation_tolerance",
        "base_coordinate_authority_changed",
        "base_crs_authority_changed",
        "weather_model_training",
        "weather_feature_selection",
        "weather_incremental_value_scoring",
    ):
        assert c[key] is False


def synthetic_plan():
    cfg = json.loads(Path("configs/era5_land_historical_weather_r2.json").read_text())
    old = {
        "locations": [
            {
                "base_id": f"b{i:02d}",
                "canonical_base_name": f"SYNTHETIC{i}",
                "requested_latitude": "25.04",
                "requested_longitude": "102.04",
                "selected_grid_latitude": "25.0",
                "selected_grid_longitude": "102.0",
                "location_authority_hash": "0" * 64,
            }
            for i in range(38)
        ],
        "base_identity_set_hash": digest([f"b{i:02d}" for i in range(38)]),
        "config": {
            "date_windows": [["2024-01-02", "2024-01-02"]],
            "variables": json.loads(
                Path("configs/era5_land_historical_weather_r1.json").read_text()
            )["variables"],
            "registry_file_sha256": "0" * 64,
        },
    }
    old["manifest_hash"] = digest(old)
    cfg["r1_request_manifest_hash"] = old["manifest_hash"]
    return old, cfg


def write_raw(
    path, *, negative=None, duplicate=False, gap=False, bad_unit=False, lon=102.0, nonfinite=False
):
    times = np.arange(
        np.datetime64("2024-01-01T00"), np.datetime64("2024-01-03T00"), np.timedelta64(1, "h")
    )
    if duplicate:
        times[1] = times[0]
    if gap:
        times = times[1:]
    data = {}
    for var in UNITS:
        value = {"t2m": 280.0, "d2m": 277.0, "tp": 0.001, "ssrd": 100.0, "u10": 3.0, "v10": 4.0}[
            var
        ]
        values = np.full(len(times), value)
        if var == negative:
            values[20] = -1e-12
        if nonfinite and var == "t2m":
            values[20] = np.inf
        data[var] = (("valid_time",), values, {"units": "wrong" if bad_unit else UNITS[var][0]})
    xr.Dataset(data, coords={"valid_time": times, "latitude": 25.0, "longitude": lon}).to_netcdf(
        path, engine="h5netcdf"
    )


def source_fixture(tmp_path, **kwargs):
    old, cfg = synthetic_plan()
    m = plan(old, cfg)
    root = tmp_path / "raw"
    root.mkdir()
    write_json(root / "request-manifest.json", m)
    entry = m["requests"][0]
    key = entry["request_hash"]
    raw = root / f"{key}.raw"
    write_raw(raw, **kwargs)
    write_json(
        root / f"{key}.completed.json",
        {"request_hash": key, "filename": raw.name, "raw_sha256": file_hash(raw)},
    )
    return root, m, entry


def test_shared_grid_keeps_38_distinct_projections():
    old, cfg = synthetic_plan()
    m = plan(old, cfg)
    assert m == plan(old, cfg)
    validate_manifest(m)
    assert len(m["requests"]) == 1
    assert len(m["requests"][0]["base_ids"]) == len(m["locations"]) == 38
    assert m["requests"][0]["request"]["location"] == {"latitude": 25.04, "longitude": 102.04}
    assert m["requests"][0]["request"]["date"] == ["2024-01-01/2024-01-02"]


@pytest.mark.parametrize(
    "key", ["custom_deaccumulation", "custom_negative_clipping", "custom_accumulation_tolerance"]
)
def test_custom_repairs_cannot_be_enabled(key):
    old, cfg = synthetic_plan()
    cfg[key] = True
    with pytest.raises(ValueError, match="CUSTOM_REPAIR_FORBIDDEN"):
        plan(old, cfg)


@pytest.mark.parametrize("mutation", ["hash", "missing_coordinate", "grid", "duplicate_base"])
def test_location_manifest_cannot_drift(mutation):
    old, cfg = synthetic_plan()
    if mutation == "hash":
        old["locations"][0]["canonical_base_name"] = "changed"
    else:
        if mutation == "missing_coordinate":
            old["locations"][0]["requested_latitude"] = "NaN"
        elif mutation == "grid":
            old["locations"][0]["selected_grid_latitude"] = "26.0"
        else:
            old["locations"][0]["base_id"] = "b01"
        old["manifest_hash"] = digest({k: v for k, v in old.items() if k != "manifest_hash"})
        cfg["r1_request_manifest_hash"] = old["manifest_hash"]
    with pytest.raises(ValueError):
        plan(old, cfg)


def test_provider_hourly_values_never_redifferenced(tmp_path, monkeypatch):
    import scripts.normalize_era5_land_historical_weather_r1 as legacy

    monkeypatch.setattr(legacy, "accumulation", lambda *a: pytest.fail("CUSTOM_DEACCUMULATION"))
    root, _, entry = source_fixture(tmp_path)
    native, audit = verified_source(root, entry)
    source_gate(audit)
    rows, day = local_day(native, datetime(2024, 1, 1, 16, tzinfo=UTC), audit["raw_sha256"])
    assert len(rows) == 144
    assert {r["local_date"] for r in rows} == {"2024-01-02"}
    assert day["local_day_precipitation_mm"] == "24.000000000000"
    assert day["local_day_solar_energy_j_m2"] == "2400.000000000000"
    assert day["local_day_mean_wind_speed_10m_m_s"] == "5.000000000000"
    assert all(r["source_dataset"] == "reanalysis-era5-land-timeseries" for r in rows)
    assert not any(k in json.dumps(day).lower() for k in ("gdd", "vpd", "et0", "chilling", "frost"))


@pytest.mark.parametrize("var", ["tp", "ssrd"])
def test_even_tiny_provider_negative_blocks_before_dataset(tmp_path, var):
    root, _, entry = source_fixture(tmp_path, negative=var)
    native, audit = verified_source(root, entry)
    assert audit["provider_negative_value_count"] == 1
    with pytest.raises(ValueError, match="PROVIDER_DEACCUMULATED_NEGATIVE_VALUE"):
        source_gate(audit)
    with pytest.raises(ValueError, match="PROVIDER_DEACCUMULATED_NEGATIVE_VALUE"):
        local_day(native, datetime(2024, 1, 1, 16, tzinfo=UTC), "0" * 64)
    with pytest.raises(ValueError, match="PROVIDER_DEACCUMULATED_NEGATIVE_VALUE"):
        replay(root, tmp_path / "accepted")
    assert not (tmp_path / "accepted").exists()
    assert report(root)["blocker"] == "PROVIDER_DEACCUMULATED_NEGATIVE_VALUE"


@pytest.mark.parametrize(
    "kwargs,reason",
    [
        ({"duplicate": True}, "DUPLICATE_NATIVE_TIMESTAMP"),
        ({"bad_unit": True}, "NATIVE_UNIT_MISMATCH"),
        ({"lon": 102.1}, "BLOCKED_PROVIDER_GRID_SELECTION_MISMATCH"),
        ({"nonfinite": True}, "NONFINITE_NATIVE_VALUE"),
    ],
)
def test_native_quality_gates(tmp_path, kwargs, reason):
    root, _, entry = source_fixture(tmp_path, **kwargs)
    with pytest.raises(ValueError, match=reason):
        verified_source(root, entry)


def test_gap_is_not_filled(tmp_path):
    root, _, entry = source_fixture(tmp_path, gap=True)
    _, audit = verified_source(root, entry)
    assert audit["missing_interval_count"] == 6
    with pytest.raises(ValueError, match="HOURLY_COVERAGE_MISMATCH"):
        source_gate(audit)


@pytest.mark.parametrize("offset,var", [(0, "t2m"), (8, "t2m"), (24, "tp")])
def test_full_local_day_edges_required(tmp_path, offset, var):
    root, _, entry = source_fixture(tmp_path)
    rows, _ = verified_source(root, entry)
    start = datetime(2024, 1, 1, 16, tzinfo=UTC)
    del rows[var, start + timedelta(hours=offset)]
    with pytest.raises(ValueError, match="HOURLY_GAP"):
        local_day(rows, start, "0" * 64)


def test_offline_replays_hashes_base_projection_and_raw_immutability(tmp_path, monkeypatch):
    root, _, entry = source_fixture(tmp_path)
    before = {p.name: file_hash(p) for p in root.iterdir()}
    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket.socket, "connect_ex", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    a = replay(root, tmp_path / "one")
    b = replay(root, tmp_path / "two")
    assert a == b
    assert a["hourly_row_count"] == 38 * 24 * 6
    assert a["daily_row_count"] == a["complete_base_count"] == 38
    assert {p.name: file_hash(p) for p in root.iterdir()} == before
    hourly = tmp_path / "one" / "hourly.jsonl"
    assert validate_rows(hourly, a["hourly_dataset_hash"]) == 38 * 144
    text = hourly.read_text()
    hourly.chmod(0o600)
    hourly.write_text(
        text.replace(
            '"normalized_value":"6.850000000000"', '"normalized_value":"7.850000000000"', 1
        )
    )
    with pytest.raises(ValueError, match="ROW_SET_HASH_MISMATCH"):
        validate_rows(hourly, a["hourly_dataset_hash"])
    with pytest.raises(ValueError, match="NORMALIZED_ROW_HASH_MISMATCH"):
        validate_rows(hourly, file_hash(hourly))
    raw = root / f"{entry['request_hash']}.raw"
    raw.write_bytes(raw.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="RAW_HASH_MISMATCH"):
        verified_source(root, entry)


def test_standard_product_cannot_enter_accepted_replay(tmp_path):
    root, m, _ = source_fixture(tmp_path)
    m["source_product"] = "reanalysis-era5-land"
    m["manifest_hash"] = digest({k: v for k, v in m.items() if k != "manifest_hash"})
    with pytest.raises(ValueError, match="REJECTED_SOURCE_PRODUCT"):
        validate_manifest(m)


def test_official_zip_member_hashes_and_grid_float_representation(tmp_path):
    root, _, entry = source_fixture(tmp_path, lon=102.0000000000009)
    raw = root / f"{entry['request_hash']}.raw"
    zipped = tmp_path / "official.zip"
    with zipfile.ZipFile(zipped, "w") as z:
        z.write(raw, "point.nc")
    rows, audit = read_source(zipped, entry)
    assert len(rows) == 48 * 6
    assert audit["members"] == [{"name": "point.nc", "sha256": file_hash(raw)}]
    assert audit["provider_grid_selection_parity"] == "PASS"


def test_downloader_does_not_submit_more_after_negative_download(tmp_path, monkeypatch):
    root, _, _ = source_fixture(tmp_path, negative="tp")

    class ForbiddenClient:
        def check_authentication(self):
            return None

        def submit(self, *args):
            pytest.fail("NEGATIVE_SOURCE_MUST_STOP_RETRIEVAL")

    monkeypatch.setitem(
        sys.modules,
        "cdsapi",
        SimpleNamespace(Client=lambda **kwargs: SimpleNamespace(client=ForbiddenClient())),
    )
    with pytest.raises(ValueError, match="PROVIDER_DEACCUMULATED_NEGATIVE_VALUE"):
        retrieve(root, 2)
    assert len(list(root.glob("*.audit.json"))) == 1


@pytest.mark.parametrize(
    "field",
    [
        "weather_model_training",
        "weather_incremental_value_scoring",
        "climate_zone_authority_used",
        "weather_source_authority_frozen",
    ],
)
def test_reanalysis_cannot_upgrade_authority_or_trigger_model_work(field):
    old, cfg = synthetic_plan()
    cfg[field] = True
    m = plan(old, cfg)
    with pytest.raises(ValueError, match="FROZEN_RESEARCH_CONTRACT_MISMATCH"):
        validate_manifest(m)
