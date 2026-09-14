"""Offline-first, immutable ERA5-Land monthly source qualification."""

import argparse
import calendar
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr

VARIABLE_UNITS = {"t2m": "K", "tp": "m", "d2m": "K", "ssrd": "J m**-2"}
PERIODS = {
    "baseline_1991_2020": (1991, 2020, 12),
    "recent_1996_2025": (1996, 2025, 12),
    "drift_2021_2025": (2021, 2025, 12),
    "ytd_2026": (2026, 2026, 8),
}


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8") as stream:
        stream.write(
            json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
        )
    path.chmod(0o400)


def expected_months(first: int, last: int, final_month: int = 12) -> list[str]:
    return [
        f"{y}-{m:02d}"
        for y in range(first, last + 1)
        for m in range(1, (final_month if y == last else 12) + 1)
    ]


def verify_months(actual: list[str], expected: list[str]) -> None:
    if len(set(actual)) != len(actual) or actual != expected:
        raise ValueError("MONTH_COVERAGE_MISSING_DUPLICATE_OR_UNORDERED")


def available_months(
    constraints: list[dict[str, Any]],
    variables: list[str],
    year: int,
    current_year: int,
    current_month: int,
) -> list[str]:
    months = sorted(
        {
            m
            for item in constraints
            if str(year) in item.get("year", [])
            and "monthly_averaged_reanalysis" in item.get("product_type", [])
            and set(variables).issubset(item.get("variable", []))
            for m in item["month"]
            if year < current_year or year == current_year and int(m) < current_month
        }
    )
    if not months or months != [f"{m:02d}" for m in range(1, int(months[-1]) + 1)]:
        raise ValueError("NONCONTIGUOUS_OR_UNAVAILABLE_CURRENT_YEAR_MONTHS")
    return months


def converted_months(months: list[str], arrays: dict[str, Any]) -> dict[str, Any]:
    """moda: tp is mean daily accumulation; ssrd mean daily energy."""
    days = np.array([calendar.monthrange(int(m[:4]), int(m[5:]))[1] for m in months])
    return {
        "temperature_c": arrays["t2m"].astype(float) - 273.15,
        "dewpoint_c": arrays["d2m"].astype(float) - 273.15,
        "precipitation_mm": arrays["tp"].astype(float) * 1000 * days,
        "radiation_mj_m2": arrays["ssrd"].astype(float) * days / 1_000_000,
        "days": days,
    }


def inspect_source(root: Path) -> tuple[dict[str, Any], xr.Dataset]:
    plan = json.loads((root / "retrieval-plan.json").read_text())
    if plan["dataset"] != "reanalysis-era5-land-monthly-means" or len(plan["requests"]) != 5:
        raise ValueError("SOURCE_PLAN_MISMATCH")
    if plan["latest_month"] != "2026-08":
        raise ValueError("FROZEN_R2_CUTOFF_MISMATCH")
    files, datasets, all_months = [], [], []
    grid = None
    for i, request in enumerate(plan["requests"]):
        if json.loads((root / f"request-{i}.json").read_text()) != request:
            raise ValueError("REQUEST_PLAN_MISMATCH")
        if request["product_type"] != "monthly_averaged_reanalysis":
            raise ValueError("MONTHLY_ACCUMULATION_SEMANTICS_MISMATCH")
        path = root / f"regional-{i}.nc"
        sha = file_hash(path)
        receipt = json.loads((root / f"receipt-{i}.json").read_text())
        if receipt["sha256"] != sha or receipt["size"] != path.stat().st_size:
            raise ValueError("RAW_SOURCE_HASH_MISMATCH")
        with xr.open_dataset(path, engine="h5netcdf") as opened:
            ds = opened.load()
        months = [str(m)[:7] for m in ds.valid_time.values]
        expected = [f"{y}-{m}" for y in request["year"] for m in request["month"]]
        verify_months(months, expected)
        if any(str(t)[8:10] != "01" for t in ds.valid_time.values):
            raise ValueError("INVALID_MONTH_TIMESTAMP")
        coordinates = [ds.latitude.values.tolist(), ds.longitude.values.tolist()]
        if grid is not None and coordinates != grid:
            raise ValueError("GRID_CHANGED_BETWEEN_BATCHES")
        grid = coordinates
        metadata = {}
        for variable, unit in VARIABLE_UNITS.items():
            a = ds[variable]
            if a.dims != ("valid_time", "latitude", "longitude"):
                raise ValueError("UNEXPECTED_VARIABLE_DIMENSIONS")
            if a.attrs.get("units") != unit or not np.isfinite(a.values).all():
                raise ValueError("VARIABLE_UNIT_OR_COVERAGE_INVALID")
            if variable in ("tp", "ssrd") and (a.values < 0).any():
                raise ValueError("NEGATIVE_ACCUMULATION")
            metadata[variable] = {
                "units": unit,
                "long_name": a.attrs["long_name"],
                "month_count": len(months),
                "complete": True,
            }
        files.append(
            {
                "file": path.name,
                "sha256": sha,
                "size": path.stat().st_size,
                "request": request,
                "receipt": receipt,
                "dataset_attributes": {
                    k: v.item() if isinstance(v, np.generic) else v for k, v in ds.attrs.items()
                },
                "variables": metadata,
                "months": months,
            }
        )
        datasets.append(ds)
        all_months.extend(months)
    verify_months(all_months, expected_months(1991, 2026, 8))
    period_counts = {}
    for name, period in PERIODS.items():
        wanted = expected_months(*period)
        verify_months([m for m in all_months if m in set(wanted)], wanted)
        period_counts[name] = {v: len(wanted) for v in VARIABLE_UNITS}
    manifest = {
        "version": "ERA5_LAND_S1_R2_SOURCE_V1",
        "files": files,
        "metadata_hashes": {
            n: file_hash(root / n)
            for n in ("catalogue.json", "constraints.json", "retrieval-plan.json")
        },
        "period_month_counts": period_counts,
        "month_count": len(all_months),
        "missing_month_count": 0,
        "duplicate_month_count": 0,
        "all_variables_readable_finite": True,
        "grid": grid,
        "latest_month": plan["latest_month"],
        "unit_authority": "https://confluence.ecmwf.int/pages/viewpage.action?pageId=177471794",
        "conversions": {
            "t2m": "K-273.15",
            "d2m": "K-273.15",
            "tp": "moda daily m * 1000 * calendar days = monthly mm",
            "ssrd": "moda daily J/m2 * calendar days / 1e6 = monthly MJ/m2",
        },
    }
    manifest["hash"] = digest(manifest)
    return manifest, xr.concat(
        datasets, dim="valid_time", data_vars="minimal", coords="minimal", compat="equals"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    manifest, ds = inspect_source(args.source)
    ds.close()
    path = args.source / "climate-source-snapshot-manifest.json"
    if args.replay:
        if json.loads(path.read_text()) != manifest:
            raise ValueError("OFFLINE_SOURCE_REPLAY_MISMATCH")
        print("OFFLINE_SOURCE_REPLAY=PASS", manifest["hash"])
    else:
        write_json(path, manifest)
        print("SOURCE_GATE=PASS", manifest["hash"])


if __name__ == "__main__":
    main()
