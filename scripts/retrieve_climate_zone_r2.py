"""Private, exclusive-write regional CDS intake for the S1 R2 study."""

import argparse
import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path

import cdsapi
import requests

from scripts.climate_source_r2 import available_months

DATASET = "reanalysis-era5-land-monthly-means"
VARIABLES = [
    "2m_temperature",
    "total_precipitation",
    "2m_dewpoint_temperature",
    "surface_solar_radiation_downwards",
]


def save(path: Path, value: object) -> None:
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")
    path.chmod(0o600)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.output
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    url = f"https://cds.climate.copernicus.eu/api/catalogue/v1/collections/{DATASET}"
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    catalogue = response.json()
    save(root / "catalogue.json", catalogue)
    constraints_url = next(
        link["href"] for link in catalogue["links"] if link["rel"] == "constraints"
    )
    response = requests.get(constraints_url, timeout=60)
    response.raise_for_status()
    constraints = response.json()
    save(root / "constraints.json", constraints)
    now = datetime.now(UTC)
    months = available_months(constraints, VARIABLES, 2026, now.year, now.month)
    registry_root = Path(
        "/Users/charles/Documents/blueberry-area-yield-artifacts/base-registry-s1-final"
    )
    evidence = json.loads(Path("docs/v0-5/s1/evidence.json").read_text())
    for name, expected in evidence["artifact_file_hashes"].items():
        if hashlib.sha256((registry_root / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Frozen S1 artifact mismatch")
    registry = json.loads((registry_root / "base-registry-v1.json").read_text())
    # Explicit geographic allowlist: never pass production fields to extraction.
    points = [
        (float(base["latitude"]), float(base["longitude"]))
        for base in registry["bases"]
        if base["region_scope"] == "YUNNAN_CORE"
    ]
    if len(points) != 38:
        raise ValueError("Unexpected study population")
    area = [
        math.ceil((max(p[0] for p in points) + 0.11) * 10) / 10,
        math.floor((min(p[1] for p in points) - 0.11) * 10) / 10,
        math.floor((min(p[0] for p in points) - 0.11) * 10) / 10,
        math.ceil((max(p[1] for p in points) + 0.11) * 10) / 10,
    ]
    plan = []
    for start, end in [(1991, 2000), (2001, 2010), (2011, 2020), (2021, 2025), (2026, 2026)]:
        plan.append(
            {
                "product_type": "monthly_averaged_reanalysis",
                "variable": VARIABLES,
                "year": [str(y) for y in range(start, end + 1)],
                "month": months if start == 2026 else [f"{m:02d}" for m in range(1, 13)],
                "time": "00:00",
                "area": area,
                "data_format": "netcdf",
                "download_format": "unarchived",
            }
        )
    save(
        root / "retrieval-plan.json",
        {"dataset": DATASET, "latest_month": f"2026-{months[-1]}", "requests": plan},
    )
    client = cdsapi.Client(quiet=True, debug=False)
    for index, request in enumerate(plan):
        save(root / f"request-{index}.json", request)
        print(f"Submitting regional request {index}", flush=True)
        result = client.retrieve(DATASET, request)
        target = root / f"regional-{index}.nc"
        result.download(str(target))
        target.chmod(0o400)
        save(
            root / f"receipt-{index}.json",
            {
                "dataset": DATASET,
                "request_id": getattr(result, "request_id", None),
                "retrieved_at": datetime.now(UTC).isoformat(),
                "file": target.name,
                "size": target.stat().st_size,
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            },
        )
        print(f"Regional request {index} downloaded", flush=True)


if __name__ == "__main__":
    main()
