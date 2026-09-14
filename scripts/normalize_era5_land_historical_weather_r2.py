"""Offline point-series normalization: provider hourly values, never adjacent differences."""

import argparse
import hashlib
import json
import math
import socket
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from scripts.build_era5_land_historical_weather_r1 import utc_bounds
from scripts.climate_source_r2 import digest, file_hash, write_json
from scripts.era5_timeseries_source_r2 import (
    PRODUCT,
    Native,
    read_source,
    source_gate,
    validate_manifest,
)
from scripts.normalize_era5_land_historical_weather_r1 import (
    UNITS,
    canonical_line,
    no_network,
    number,
    validate_rows,
)


def local_day(
    native: Native, start: datetime, source: str
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    hourly = []
    normalized: dict[str, list[Decimal]] = {v: [] for v in UNITS}
    date = start.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
    for hour in range(24):
        instant = start + timedelta(hours=hour)
        for var in sorted(UNITS):
            interval = var in {"tp", "ssrd"}
            valid = instant + timedelta(hours=1) if interval else instant
            if (var, valid) not in native:
                raise ValueError("HOURLY_GAP")
            value = native[var, valid]
            if not math.isfinite(value):
                raise ValueError("NONFINITE_NATIVE_VALUE")
            if interval and value < 0:
                raise ValueError("PROVIDER_DEACCUMULATED_NEGATIVE_VALUE")
            # Conversion only. The provider, not this program, deaccumulates tp/ssrd.
            converted = value - 273.15 if var in {"t2m", "d2m"} else value
            if var == "tp":
                converted *= 1000
            text = number(converted)
            normalized[var].append(Decimal(text))
            hourly.append(
                {
                    "valid_time_utc": valid.isoformat(),
                    "source_valid_time_utc": valid.isoformat(),
                    "support_start_utc": instant.isoformat(),
                    "support_end_utc": (instant + timedelta(hours=1)).isoformat(),
                    "local_date": date,
                    "temporal_semantics": "PROVIDER_DEACCUMULATED_HOURLY_INTERVAL_END"
                    if interval
                    else "INSTANT_AT_START",
                    "native_variable": var,
                    "native_value": number(value),
                    "native_value_exact_hex": value.hex(),
                    "native_unit": UNITS[var][0],
                    "normalized_variable": UNITS[var][1],
                    "normalized_value": text,
                    "normalized_unit": UNITS[var][2],
                    "source_dataset": PRODUCT,
                    "source_artifact_hash": source,
                    "processing_version": "ERA5_LAND_HOURLY_NORMALIZED_V1",
                    "source_processing_version": "CDS_POINT_TIMESERIES_R2",
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


def verified_source(root: Path, entry: dict[str, Any]) -> tuple[Native, dict[str, Any]]:
    key = entry["request_hash"]
    if digest(entry["request"]) != key:
        raise ValueError("REQUEST_HASH_MISMATCH")
    receipt = root / f"{key}.completed.json"
    if not receipt.exists():
        raise ValueError("RAW_REQUEST_INCOMPLETE")
    r = json.loads(receipt.read_text())
    raw = root / f"{key}.raw"
    if r["request_hash"] != key or r["filename"] != raw.name or file_hash(raw) != r["raw_sha256"]:
        raise ValueError("RAW_HASH_MISMATCH")
    return read_source(raw, entry)


def replay(root: Path, output: Path) -> dict[str, Any]:
    manifest = json.loads((root / "request-manifest.json").read_text())
    validate_manifest(manifest)
    audits = {}
    # All raw quality gates precede creation of any accepted row set.
    for entry in manifest["requests"]:
        _, audit = verified_source(root, entry)
        source_gate(audit)
        audits[entry["request_hash"]] = audit
    output.mkdir(parents=True, exist_ok=False)
    counts = {"hourly": 0, "daily": 0}
    hashes = {k: hashlib.sha256() for k in counts}
    with (output / "hourly.jsonl").open("xb") as hs, (output / "daily.jsonl").open("xb") as ds:
        for loc in sorted(manifest["locations"], key=lambda b: b["base_id"]):
            for entry in sorted(manifest["requests"], key=lambda r: r["business_start"]):
                if loc["base_id"] not in entry["base_ids"]:
                    continue
                native, audit = verified_source(root, entry)
                source_gate(audit)
                start, end = utc_bounds(entry["business_start"], entry["business_end"])
                while start < end:
                    hours, day = local_day(native, start, audit["raw_sha256"])
                    day_row = {
                        **day,
                        "base_id": loc["base_id"],
                        "local_date": hours[0]["local_date"],
                        "processing_version": "BASE_WEATHER_DAILY_V1",
                        "source_processing_version": "CDS_POINT_TIMESERIES_R2",
                        "hourly_sample_count": 24,
                        "source_artifact_hashes": [audit["raw_sha256"]],
                    }
                    for kind, stream, rows in (
                        ("hourly", hs, [{**loc, **r} for r in hours]),
                        ("daily", ds, [day_row]),
                    ):
                        for row in rows:
                            data = canonical_line({**row, "row_hash": digest(row)})
                            stream.write(data)
                            hashes[kind].update(data)
                            counts[kind] += 1
                    start += timedelta(days=1)
    result = {
        "request_manifest_hash": manifest["manifest_hash"],
        "raw_artifact_count": len(audits),
        "raw_artifact_set_hash": digest(
            [{"request_hash": k, "raw_sha256": a["raw_sha256"]} for k, a in sorted(audits.items())]
        ),
        **{f"{k}_row_count": v for k, v in counts.items()},
        **{f"{k}_dataset_hash": v.hexdigest() for k, v in hashes.items()},
        "complete_base_count": len(manifest["locations"]),
        "incomplete_base_count": 0,
        "missing_interval_count": 0,
        "duplicate_interval_count": 0,
    }
    for kind in counts:
        if validate_rows(output / f"{kind}.jsonl", result[f"{kind}_dataset_hash"]) != counts[kind]:
            raise ValueError("ROW_COUNT_MISMATCH")
        (output / f"{kind}.jsonl").chmod(0o400)
    write_json(output / "dataset-manifest.json", result)
    return result


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
