"""Read official point-series values without local accumulation differences or repairs."""

import math
import tempfile
import zipfile
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import xarray as xr

from scripts.build_era5_land_historical_weather_r1 import nearest, utc_bounds
from scripts.climate_source_r2 import digest, file_hash
from scripts.normalize_era5_land_historical_weather_r1 import UNITS

PRODUCT = "reanalysis-era5-land-timeseries"
Native = dict[tuple[str, datetime], float]


def validate_manifest(m: dict[str, Any]) -> None:
    if digest({k: v for k, v in m.items() if k != "manifest_hash"}) != m["manifest_hash"]:
        raise ValueError("MANIFEST_HASH_MISMATCH")
    if m["source_product"] != PRODUCT or m["config"]["source_product"] != PRODUCT:
        raise ValueError("REJECTED_SOURCE_PRODUCT")
    if digest(m["config"]) != m["config_hash"]:
        raise ValueError("CONFIG_HASH_MISMATCH")
    if any(
        m["config"][k]
        for k in (
            "custom_deaccumulation",
            "custom_negative_clipping",
            "custom_accumulation_tolerance",
        )
    ):
        raise ValueError("CUSTOM_REPAIR_FORBIDDEN")
    required = {
        "weather_role": "REANALYSIS_REFERENCE",
        "query_crs_assumption": "WGS84",
        "crs_verification_status": "NOT_ESTABLISHED",
        "source_coordinate_status": "RANGE_VALID_CRS_UNCONFIRMED",
        "accumulated_variables": "PROVIDER_DEACCUMULATED_HOURLY",
        "base_coordinate_authority_changed": False,
        "base_crs_authority_changed": False,
        "weather_model_training": False,
        "weather_feature_selection": False,
        "weather_incremental_value_scoring": False,
        "climate_zone_authority_used": False,
        "historical_as_issued_forecast_implementation": False,
        "live_forecast_implementation": False,
        "weather_source_authority_frozen": False,
        "live_weather_forecast_authority_frozen": False,
    }
    if any(m["config"].get(k) != value for k, value in required.items()):
        raise ValueError("FROZEN_RESEARCH_CONTRACT_MISMATCH")
    if len(m["locations"]) != 38 or len({b["base_id"] for b in m["locations"]}) != 38:
        raise ValueError("BASE_IDENTITY_SET_DRIFT")
    if digest(sorted(b["base_id"] for b in m["locations"])) != m["base_identity_set_hash"]:
        raise ValueError("BASE_IDENTITY_HASH_MISMATCH")
    variables = {
        "2m_temperature",
        "2m_dewpoint_temperature",
        "total_precipitation",
        "surface_solar_radiation_downwards",
        "10m_u_component_of_wind",
        "10m_v_component_of_wind",
    }
    locations = {b["base_id"]: b for b in m["locations"]}
    covered: set[tuple[str, str, str]] = set()
    hashes = set()
    for entry in m["requests"]:
        request = entry["request"]
        if digest(request) != entry["request_hash"] or entry["request_hash"] in hashes:
            raise ValueError("REQUEST_HASH_MISMATCH_OR_DUPLICATE")
        hashes.add(entry["request_hash"])
        first, last = utc_bounds(entry["business_start"], entry["business_end"])
        if (
            set(request) != {"variable", "location", "date", "data_format"}
            or set(request["variable"]) != variables
            or len(request["variable"]) != 6
            or request["data_format"] != "netcdf"
            or request["date"] != [f"{first.date().isoformat()}/{last.date().isoformat()}"]
        ):
            raise ValueError("POINT_REQUEST_CONTRACT_MISMATCH")
        for base in entry["base_ids"]:
            key = base, entry["business_start"], entry["business_end"]
            if base not in locations or key in covered:
                raise ValueError("BASE_PROJECTION_DRIFT")
            covered.add(key)
            for coord in ("latitude", "longitude"):
                expected = entry[f"expected_selected_grid_{coord}"]
                if (
                    nearest(locations[base][f"requested_{coord}"]) != expected
                    or nearest(str(request["location"][coord])) != expected
                ):
                    raise ValueError("LOCATION_SELECTION_DRIFT")
    if covered != {(b, start, end) for b in locations for start, end in m["date_windows"]}:
        raise ValueError("BASE_SEASON_COVERAGE_DRIFT")


def point_text(value: float) -> str:
    """Only coordinate storage representation (six decimals), never weather tolerances."""
    if not math.isfinite(value):
        raise ValueError("NONFINITE_COORDINATE")
    return format(Decimal(str(value)).quantize(Decimal("0.000001")), "f")


def read_source(path: Path, entry: dict[str, Any]) -> tuple[Native, dict[str, Any]]:
    rows: Native = {}
    members = []
    points = []
    with tempfile.TemporaryDirectory(prefix="era5-timeseries-read-") as tmp:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
                if len(names) != len(set(names)) or any(
                    Path(n).name != n or not n.endswith(".nc") for n in names
                ):
                    raise ValueError("UNEXPECTED_RAW_ARCHIVE_MEMBERS")
                archive.extractall(tmp)
                files = [Path(tmp) / n for n in sorted(names)]
        else:
            files = [path]
        for item in files:
            members.append({"name": item.name, "sha256": file_hash(item)})
            with xr.open_dataset(item, engine="h5netcdf") as ds:
                point = {}
                for coord in ("latitude", "longitude"):
                    if coord not in ds or ds[coord].size != 1:
                        raise ValueError("BLOCKED_PROVIDER_GRID_SELECTION_MISMATCH")
                    returned = float(ds[coord].values.item())
                    point[f"provider_returned_{coord}"] = str(returned)
                    if point_text(returned) != point_text(
                        float(entry[f"expected_selected_grid_{coord}"])
                    ):
                        raise ValueError("BLOCKED_PROVIDER_GRID_SELECTION_MISMATCH")
                points.append(point)
                time_names = [n for n in ("time", "valid_time") if n in ds.coords]
                if len(time_names) != 1:
                    raise ValueError("TIMESERIES_TIME_COORDINATE_REQUIRED")
                time_name = time_names[0]
                for var in sorted(UNITS):
                    if var not in ds.data_vars:
                        continue
                    if ds[var].attrs.get("units") != UNITS[var][0]:
                        raise ValueError("NATIVE_UNIT_MISMATCH")
                    array = ds[var]
                    for dim in array.dims:
                        if dim != time_name and array.sizes[dim] == 1:
                            array = array.isel({dim: 0}, drop=True)
                    if array.dims != (time_name,):
                        raise ValueError("UNEXPECTED_NATIVE_DIMENSIONS")
                    for stamp, value in zip(ds[time_name].values, array.values, strict=True):
                        valid = datetime.fromisoformat(str(stamp)).replace(tzinfo=UTC)
                        if valid.minute or valid.second or valid.microsecond:
                            raise ValueError("NON_HOURLY_TIMESTAMP")
                        key = var, valid
                        if key in rows:
                            raise ValueError("DUPLICATE_NATIVE_TIMESTAMP")
                        scalar = float(value)
                        if not math.isfinite(scalar):
                            raise ValueError("NONFINITE_NATIVE_VALUE")
                        rows[key] = scalar
    if {v for v, _ in rows} != set(UNITS):
        raise ValueError("NATIVE_VARIABLE_SET_MISMATCH")
    negative = [
        {
            "variable": var,
            "valid_time_utc": stamp.isoformat(),
            "value_exact_hex": value.hex(),
            "value_decimal": format(value, ".17g"),
            "unit": UNITS[var][0],
        }
        for (var, stamp), value in sorted(rows.items())
        if var in {"tp", "ssrd"} and value < 0
    ]
    start, end = entry["request"]["date"][0].split("/")
    first = datetime.fromisoformat(start).replace(tzinfo=UTC)
    last = datetime.fromisoformat(end).replace(tzinfo=UTC) + timedelta(days=1)
    expected = {
        first + timedelta(hours=i) for i in range(int((last - first).total_seconds() / 3600))
    }
    gaps = sum(len(expected - {t for v, t in rows if v == var}) for var in UNITS)
    excess = sum(len({t for v, t in rows if v == var} - expected) for var in UNITS)
    audit = {
        "source_product": PRODUCT,
        "request_hash": entry["request_hash"],
        "raw_sha256": file_hash(path),
        "members": members,
        "points": points,
        "provider_grid_selection_parity": "PASS",
        "native_row_count": len(rows),
        "missing_interval_count": gaps,
        "unexpected_interval_count": excess,
        "duplicate_interval_count": 0,
        "provider_negative_value_count": len(negative),
        "negative_values": negative,
        "provider_deaccumulation": True,
        "custom_deaccumulation": False,
        "custom_negative_clipping": False,
    }
    return rows, audit


def source_gate(audit: dict[str, Any]) -> None:
    if audit["provider_negative_value_count"]:
        raise ValueError("PROVIDER_DEACCUMULATED_NEGATIVE_VALUE")
    if audit["missing_interval_count"] or audit["unexpected_interval_count"]:
        raise ValueError("HOURLY_COVERAGE_MISMATCH")
