"""Private, point-only ERA5-Land retrieval planning; no harvest labels or zone authority."""

import argparse
import json
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_DOWN, Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from scripts.climate_source_r2 import digest, file_hash, write_json

CONFIG = Path("configs/era5_land_historical_weather_r1.json")


def nearest(value: str) -> str:
    """Positive Yunnan coordinates; exact half-cell ties choose lower coordinate."""
    d = Decimal(value)
    if not d.is_finite() or d <= 0:
        raise ValueError("BLOCKED_CRS_OR_COORDINATE_REVIEW_REQUIRED")
    return str(d.quantize(Decimal("0.1"), rounding=ROUND_HALF_DOWN))


def utc_bounds(start: str, end: str) -> tuple[datetime, datetime]:
    first = datetime.combine(date.fromisoformat(start), time(), ZoneInfo("Asia/Shanghai"))
    last = datetime.combine(date.fromisoformat(end) + timedelta(days=1), time(), first.tzinfo)
    if last <= first:
        raise ValueError("INVALID_DATE_WINDOW")
    return first.astimezone(UTC), last.astimezone(UTC)


def plan(registry: Path, config: dict[str, Any]) -> dict[str, Any]:
    if file_hash(registry) != config["registry_file_sha256"]:
        raise ValueError("REGISTRY_FILE_HASH_MISMATCH")
    payload = json.loads(registry.read_text())
    bases = sorted(
        (b for b in payload["bases"] if b["region_scope"] == "YUNNAN_CORE"),
        key=lambda b: b["base_id"],
    )
    if len(bases) != 38 or len({b["base_id"] for b in bases}) != 38:
        raise ValueError("BASE_IDENTITY_SET_DRIFT")
    locations = []
    for b in bases:
        lat, lon = b.get("latitude"), b.get("longitude")
        if lat is None or lon is None:
            raise ValueError("BLOCKED_CRS_OR_COORDINATE_REVIEW_REQUIRED")
        # Range screening only, not geocoding or geographic authority creation.
        if not (Decimal("20") <= Decimal(lat) <= Decimal("30")) or not (
            Decimal("96") <= Decimal(lon) <= Decimal("108")
        ):
            raise ValueError("BLOCKED_CRS_OR_COORDINATE_REVIEW_REQUIRED")
        y, x = nearest(lat), nearest(lon)
        locations.append(
            {
                "base_id": b["base_id"],
                "canonical_base_name": b["canonical_base_name"],
                "requested_latitude": lat,
                "requested_longitude": lon,
                "selected_grid_latitude": y,
                "selected_grid_longitude": x,
                "coordinate_offset_degrees": {
                    "latitude": str(Decimal(y) - Decimal(lat)),
                    "longitude": str(Decimal(x) - Decimal(lon)),
                },
                "grid_resolution": "0.1 degree",
                "selection_method": config["spatial_extraction_policy"],
                "location_authority_hash": config["registry_file_sha256"],
            }
        )
    requests = []
    cells = sorted({(b["selected_grid_latitude"], b["selected_grid_longitude"]) for b in locations})
    for y, x in cells:
        for start, end in config["date_windows"]:
            a, z = utc_bounds(start, end)
            days: dict[str, list[str]] = {}
            d = a.date()
            while d <= z.date():
                days.setdefault(d.strftime("%Y-%m"), []).append(d.strftime("%d"))
                d += timedelta(days=1)
            for month, day in sorted(days.items()):
                request = {
                    "variable": config["variables"],
                    "year": month[:4],
                    "month": month[5:],
                    "day": day,
                    "time": [f"{h:02d}:00" for h in range(24)],
                    "area": [float(y), float(x), float(y), float(x)],
                    "data_format": "netcdf",
                    "download_format": "unarchived",
                }
                requests.append({"request_id": digest(request), "request": request})
    result = {
        "config": config,
        "config_hash": digest(config),
        "locations": locations,
        "base_identity_set_hash": digest([b["base_id"] for b in bases]),
        "requests": requests,
        "dataset": config["dataset"],
        "utc_padding_policy": "Full UTC dates enclosing local days; extra hours excluded from output",
    }
    return {**result, "manifest_hash": digest(result)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = plan(args.registry, json.loads(CONFIG.read_text()))
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output / "request-manifest.json", manifest)
    print(
        json.dumps(
            {"request_count": len(manifest["requests"]), "manifest_hash": manifest["manifest_hash"]}
        )
    )


if __name__ == "__main__":
    main()
