"""Offline normalization of pinned native ERA5-Land files; all missing data fail closed."""

import argparse
import hashlib
import json
import math
import socket
import tempfile
import zipfile
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import xarray as xr

from scripts.build_era5_land_historical_weather_r1 import utc_bounds
from scripts.climate_source_r2 import digest, file_hash, write_json

UNITS = {
    "t2m": ("K", "temperature_2m_c", "degC"),
    "d2m": ("K", "dewpoint_2m_c", "degC"),
    "tp": ("m", "hourly_precipitation_mm", "mm"),
    "ssrd": ("J m**-2", "hourly_solar_energy_j_m2", "J m-2"),
    "u10": ("m s**-1", "wind_u_10m_m_s", "m s-1"),
    "v10": ("m s**-1", "wind_v_10m_m_s", "m s-1"),
}


def number(value: float | Decimal) -> str:
    d = value if isinstance(value, Decimal) else Decimal.from_float(value)
    if not d.is_finite():
        raise ValueError("NONFINITE_NATIVE_VALUE")
    with localcontext() as ctx:
        ctx.prec = 50
        d = d.quantize(Decimal("0.000000000001"), rounding=ROUND_HALF_EVEN)
        return format(abs(d) if not d else d, ".12f")


def accumulation(value: float, previous: float | None, valid: datetime) -> float:
    """CDS valid 01 is step1; 00 is previous initialization's step24."""
    if not math.isfinite(value) or value < 0:
        raise ValueError("INVALID_ACCUMULATION")
    if valid.hour == 1:
        result = value
    else:
        if previous is None or not math.isfinite(previous) or previous < 0:
            raise ValueError("MISSING_ACCUMULATION_PREDECESSOR")
        result = value - previous
    if result < 0:
        raise ValueError("NEGATIVE_ACCUMULATION_DIFFERENCE_NO_CLIPPING")
    return result


def canonical_line(row: dict[str, Any]) -> bytes:
    return (
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode()


def validate_rows(path: Path, expected: str) -> int:
    if file_hash(path) != expected:
        raise ValueError("ROW_SET_HASH_MISMATCH")
    count = 0
    with path.open() as stream:
        for line in stream:
            row = json.loads(line)
            rh = row.pop("row_hash")
            if digest(row) != rh:
                raise ValueError("NORMALIZED_ROW_HASH_MISMATCH")
            count += 1
    return count


def read_native(path: Path, latitude: str, longitude: str) -> dict[tuple[str, datetime], float]:
    rows: dict[tuple[str, datetime], float] = {}
    with tempfile.TemporaryDirectory(prefix="era5-read-") as tmp:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
                if any(Path(n).name != n or not n.endswith(".nc") for n in names):
                    raise ValueError("UNEXPECTED_RAW_ARCHIVE_MEMBERS")
                archive.extractall(tmp)
                files = [Path(tmp) / n for n in names]
        else:
            files = [path]
        for item in files:
            with xr.open_dataset(item, engine="h5netcdf") as ds:
                for coord, value in (("latitude", latitude), ("longitude", longitude)):
                    if (
                        ds[coord].size != 1
                        or abs(float(ds[coord].values.item()) - float(value)) > 1e-5
                    ):
                        raise ValueError("GRID_SELECTION_MISMATCH")
                for var in sorted(UNITS):
                    if var not in ds.data_vars:
                        continue
                    if ds[var].attrs.get("units") != UNITS[var][0]:
                        raise ValueError("NATIVE_UNIT_MISMATCH")
                    expected_step = "accum" if var in {"tp", "ssrd"} else "instant"
                    if ds[var].attrs.get("GRIB_stepType") != expected_step:
                        raise ValueError("NATIVE_STEP_SEMANTICS_MISMATCH")
                    if ds[var].attrs.get("GRIB_stepUnits") != 1:
                        raise ValueError("NATIVE_STEP_UNIT_MISMATCH")
                    array = ds[var].squeeze(drop=True)
                    if array.dims != ("valid_time",):
                        raise ValueError("UNEXPECTED_NATIVE_DIMENSIONS")
                    for stamp, value in zip(ds.valid_time.values, array.values, strict=True):
                        valid = datetime.fromisoformat(str(stamp).split(".")[0]).replace(tzinfo=UTC)
                        if valid.minute or valid.second:
                            raise ValueError("NON_HOURLY_TIMESTAMP")
                        key = (var, valid)
                        if key in rows:
                            raise ValueError("DUPLICATE_NATIVE_TIMESTAMP")
                        scalar = float(value)
                        if not math.isfinite(scalar):
                            raise ValueError("NONFINITE_NATIVE_VALUE")
                        rows[key] = scalar
    if {v for v, _ in rows} != set(UNITS):
        raise ValueError("NATIVE_VARIABLE_SET_MISMATCH")
    return rows


def local_day(
    native: dict[tuple[str, datetime], tuple[float, str]],
    start: datetime,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    hourly = []
    normalized: dict[str, list[Decimal]] = {v: [] for v in UNITS}
    for hour in range(24):
        instant = start + timedelta(hours=hour)
        for var in sorted(UNITS):
            valid = instant + timedelta(hours=1) if var in {"tp", "ssrd"} else instant
            if (var, valid) not in native:
                raise ValueError("HOURLY_GAP")
            value, source = native[(var, valid)]
            converted = value
            predecessor_hash = None
            if var in {"tp", "ssrd"}:
                prior = native.get((var, valid - timedelta(hours=1)))
                converted = accumulation(value, prior[0] if prior else None, valid)
                predecessor_hash = prior[1] if prior and valid.hour != 1 else None
            if var in {"t2m", "d2m"}:
                converted -= 273.15
            elif var == "tp":
                converted *= 1000
            text = number(converted)
            normalized[var].append(Decimal(text))
            hourly.append(
                {
                    "valid_time_utc": valid.isoformat(),
                    "source_valid_time_utc": valid.isoformat(),
                    "support_start_utc": instant.isoformat(),
                    "support_end_utc": (instant + timedelta(hours=1)).isoformat(),
                    "temporal_semantics": "INTERVAL_END"
                    if var in {"tp", "ssrd"}
                    else "INSTANT_AT_START",
                    "local_date": start.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat(),
                    "native_variable": var,
                    "native_value": number(value),
                    "native_unit": UNITS[var][0],
                    "normalized_variable": UNITS[var][1],
                    "normalized_value": text,
                    "normalized_unit": UNITS[var][2],
                    "source_dataset": "reanalysis-era5-land",
                    "source_artifact_hash": source,
                    "accumulation_predecessor_artifact_hash": predecessor_hash,
                    "accumulation_initialization_utc": (
                        (valid - timedelta(hours=valid.hour or 24)).isoformat()
                        if var in {"tp", "ssrd"}
                        else None
                    ),
                    "accumulation_step_hours": (valid.hour or 24)
                    if var in {"tp", "ssrd"}
                    else None,
                    "processing_version": "ERA5_LAND_HOURLY_NORMALIZED_V1",
                }
            )
    with localcontext() as ctx:
        ctx.prec = 50
        temperatures = normalized["t2m"]
        daily = {
            "sampled_local_day_tmin_c": number(min(temperatures)),
            "sampled_local_day_tmax_c": number(max(temperatures)),
            "local_day_mean_temperature_c": number(sum(temperatures) / Decimal(24)),
            "local_day_precipitation_mm": number(sum(normalized["tp"])),
            "local_day_solar_energy_j_m2": number(sum(normalized["ssrd"])),
            "local_day_mean_wind_speed_10m_m_s": number(
                sum(
                    (u * u + v * v).sqrt()
                    for u, v in zip(normalized["u10"], normalized["v10"], strict=True)
                )
                / Decimal(24)
            ),
        }
    return hourly, daily


def audit_accumulations(
    rows: dict[tuple[str, datetime], float],
) -> list[dict[str, Any]]:
    """Report raw within-file defects without modifying labels or inventing edge values."""
    errors = []
    for (var, valid), value in sorted(rows.items()):
        if var not in {"tp", "ssrd"}:
            continue
        previous = rows.get((var, valid - timedelta(hours=1)))
        # File boundaries require a different pinned file, checked during full replay.
        if previous is None and valid.hour != 1:
            continue
        try:
            accumulation(value, previous, valid)
        except ValueError as exc:
            errors.append(
                {
                    "native_variable": var,
                    "valid_time_utc": valid.isoformat(),
                    "local_date": (valid - timedelta(hours=1))
                    .astimezone(ZoneInfo("Asia/Shanghai"))
                    .date()
                    .isoformat(),
                    "native_unit": UNITS[var][0],
                    "native_value_exact_hex": value.hex(),
                    "previous_value_exact_hex": previous.hex() if previous is not None else None,
                    "native_difference": format(value - previous, ".17g")
                    if previous is not None
                    else None,
                    "reason": str(exc),
                    "clipped": False,
                }
            )
    return errors


def replay(root: Path, output: Path) -> dict[str, Any]:
    manifest = json.loads((root / "request-manifest.json").read_text())
    if (
        digest({k: v for k, v in manifest.items() if k != "manifest_hash"})
        != manifest["manifest_hash"]
    ):
        raise ValueError("MANIFEST_HASH_MISMATCH")
    receipts = {}
    for entry in manifest["requests"]:
        key = entry["request_id"]
        if digest(entry["request"]) != key:
            raise ValueError("REQUEST_HASH_MISMATCH")
        receipt = json.loads((root / f"{key}.completed.json").read_text())
        raw = root / f"{key}.raw"
        if receipt["request_hash"] != key or file_hash(raw) != receipt["raw_sha256"]:
            raise ValueError("RAW_HASH_MISMATCH")
        lat, lon = entry["request"]["area"][:2]
        if audit_accumulations(read_native(raw, str(lat), str(lon))):
            raise ValueError("NATIVE_ACCUMULATION_NEGATIVE_DIFFERENCE_REVIEW_REQUIRED")
        receipts[key] = receipt
    output.mkdir(parents=True, exist_ok=False)
    counts = {"hourly": 0, "daily": 0}
    hashes = {"hourly": hashlib.sha256(), "daily": hashlib.sha256()}
    with (output / "hourly.jsonl").open("xb") as hs, (output / "daily.jsonl").open("xb") as ds:
        for loc in manifest["locations"]:
            native: dict[tuple[str, datetime], tuple[float, str]] = {}
            for entry in manifest["requests"]:
                r = entry["request"]
                if r["area"][:2] != [
                    float(loc["selected_grid_latitude"]),
                    float(loc["selected_grid_longitude"]),
                ]:
                    continue
                key = entry["request_id"]
                rows = read_native(
                    root / f"{key}.raw",
                    loc["selected_grid_latitude"],
                    loc["selected_grid_longitude"],
                )
                for stamp, value in rows.items():
                    if stamp in native:
                        raise ValueError("DUPLICATE_NATIVE_TIMESTAMP")
                    native[stamp] = (value, receipts[key]["raw_sha256"])
            for first, last in manifest["config"]["date_windows"]:
                start, end = utc_bounds(first, last)
                while start < end:
                    hour_rows, day = local_day(native, start)
                    day_row = {
                        **day,
                        "base_id": loc["base_id"],
                        "local_date": start.astimezone(ZoneInfo("Asia/Shanghai"))
                        .date()
                        .isoformat(),
                        "processing_version": "BASE_WEATHER_DAILY_V1",
                        "hourly_sample_count": 24,
                        "source_artifact_hashes": sorted(
                            {r["source_artifact_hash"] for r in hour_rows}
                        ),
                    }
                    for kind, stream, rows_to_write in (
                        ("hourly", hs, [{**loc, **r} for r in hour_rows]),
                        ("daily", ds, [day_row]),
                    ):
                        for row in rows_to_write:
                            data = canonical_line({**row, "row_hash": digest(row)})
                            stream.write(data)
                            hashes[kind].update(data)
                            counts[kind] += 1
                    start += timedelta(days=1)
    summary = {
        "request_manifest_hash": manifest["manifest_hash"],
        "raw_artifact_count": len(receipts),
        "raw_artifact_set_hash": digest(
            [{"request_hash": k, "raw_sha256": r["raw_sha256"]} for k, r in receipts.items()]
        ),
        "hourly_row_count": counts["hourly"],
        "daily_row_count": counts["daily"],
        "hourly_dataset_hash": hashes["hourly"].hexdigest(),
        "daily_dataset_hash": hashes["daily"].hexdigest(),
        "complete_base_count": len(manifest["locations"]),
        "incomplete_base_count": 0,
        "missing_interval_count": 0,
        "duplicate_interval_count": 0,
        "per_base_completeness": {b["base_id"]: "COMPLETE" for b in manifest["locations"]},
    }
    for kind in counts:
        if validate_rows(output / f"{kind}.jsonl", summary[f"{kind}_dataset_hash"]) != counts[kind]:
            raise ValueError("ROW_COUNT_MISMATCH")
        (output / f"{kind}.jsonl").chmod(0o400)
    write_json(output / "dataset-manifest.json", summary)
    return summary


def no_network(*args: Any, **kwargs: Any) -> Any:
    raise RuntimeError("OFFLINE_REPLAY_NETWORK_FORBIDDEN")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    socket.socket.connect = no_network  # type: ignore[method-assign]
    socket.socket.connect_ex = no_network  # type: ignore[method-assign]
    socket.create_connection = no_network
    print(json.dumps(replay(args.root, args.output), sort_keys=True))


if __name__ == "__main__":
    main()
