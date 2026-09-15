"""Official ERA5-Land point time-series plan. R1 sources remain rejected diagnostics."""

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.build_era5_land_historical_weather_r1 import nearest, utc_bounds
from scripts.climate_source_r2 import digest, write_json

CONFIG = Path("configs/era5_land_historical_weather_r2.json")


def plan(old: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    if (
        old["manifest_hash"] != config["r1_request_manifest_hash"]
        or digest({k: v for k, v in old.items() if k != "manifest_hash"}) != old["manifest_hash"]
    ):
        raise ValueError("LOCATION_MANIFEST_HASH_MISMATCH")
    if len(old["locations"]) != 38 or len({b["base_id"] for b in old["locations"]}) != 38:
        raise ValueError("BASE_IDENTITY_SET_DRIFT")
    if config["source_product"] != "reanalysis-era5-land-timeseries":
        raise ValueError("SOURCE_PRODUCT_MISMATCH")
    if any(
        config[k]
        for k in (
            "custom_deaccumulation",
            "custom_negative_clipping",
            "custom_accumulation_tolerance",
        )
    ):
        raise ValueError("CUSTOM_REPAIR_FORBIDDEN")
    cells: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for b in old["locations"]:
        cell = nearest(b["requested_latitude"]), nearest(b["requested_longitude"])
        if cell != (b["selected_grid_latitude"], b["selected_grid_longitude"]):
            raise ValueError("LOCATION_SELECTION_DRIFT")
        cells.setdefault(cell, []).append(b)
    requests = []
    for (lat, lon), bases in sorted(cells.items()):
        for start, end in old["config"]["date_windows"]:
            first, last = utc_bounds(start, end)
            representative = sorted(bases, key=lambda b: b["base_id"])[0]
            request = {
                "variable": old["config"]["variables"],
                "location": {
                    "latitude": float(representative["requested_latitude"]),
                    "longitude": float(representative["requested_longitude"]),
                },
                "date": [f"{first.date().isoformat()}/{last.date().isoformat()}"],
                "data_format": "netcdf",
            }
            requests.append(
                {
                    "request_hash": digest(request),
                    "request": request,
                    "expected_selected_grid_latitude": lat,
                    "expected_selected_grid_longitude": lon,
                    "base_ids": sorted(b["base_id"] for b in bases),
                    "business_start": start,
                    "business_end": end,
                }
            )
    result = {
        "config": config,
        "config_hash": digest(config),
        "requests": requests,
        "locations": old["locations"],
        "base_identity_set_hash": old["base_identity_set_hash"],
        "location_authority_hash": old["config"]["registry_file_sha256"],
        "date_windows": old["config"]["date_windows"],
        "standard_source_disposition": "REJECTED_DIAGNOSTIC_SOURCE_PATH",
        "source_product": config["source_product"],
    }
    return {**result, "manifest_hash": digest(result)}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--r1-root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    result = plan(
        json.loads((args.r1_root / "request-manifest.json").read_text()),
        json.loads(CONFIG.read_text()),
    )
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output / "request-manifest.json", result)
    print(
        json.dumps(
            {"request_count": len(result["requests"]), "manifest_hash": result["manifest_hash"]}
        )
    )


if __name__ == "__main__":
    main()
