"""Execute the candidate study only after immutable offline source replay passes."""

import argparse
import csv
import importlib.metadata
import json
from pathlib import Path
from typing import Any

from threadpoolctl import threadpool_limits

from scripts.climate_source_r2 import digest, file_hash, inspect_source, write_json
from scripts.climate_study_r2 import extract, geography, study


def csv_file(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    names = fields or sorted({k for row in rows for k in row})
    with path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=names)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    k: json.dumps(v, ensure_ascii=False, sort_keys=True)
                    if isinstance(v, (list, dict))
                    else v
                    for k, v in row.items()
                }
            )
    path.chmod(0o400)


def run(source: Path, registry_root: Path, output: Path, config_path: Path) -> None:
    frozen = json.loads((source / "climate-source-snapshot-manifest.json").read_text())
    verified, ds = inspect_source(source)
    if frozen != verified:
        raise ValueError("FROZEN_SOURCE_REPLAY_REQUIRED")
    evidence = json.loads(Path("docs/v0-5/s1/evidence.json").read_text())
    for name, sha in evidence["artifact_file_hashes"].items():
        if file_hash(registry_root / name) != sha:
            raise ValueError("S1_FROZEN_INPUT_MISMATCH")
    registry = json.loads((registry_root / "base-registry-v1.json").read_text())
    bases = geography(registry)
    config = json.loads(config_path.read_text())
    if config["climate_zone_mapping_frozen"] or config["climate_zone_profile_authority_frozen"]:
        raise ValueError("AUTOMATIC_AUTHORITY_FREEZE_FORBIDDEN")
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    write_json(output / "study-config.json", config)
    profiles = []
    for base in bases:
        p = dict(base) | extract(ds, base)
        p.update(
            {
                "version": "BASE_CLIMATE_PROFILE_V1_CANDIDATE",
                "source_snapshot_hash": frozen["hash"],
                "climate_source_id": "reanalysis-era5-land-monthly-means",
                "climate_source_version": "CDS_SNAPSHOT_" + frozen["hash"],
                "extract_version": "NEAREST_GRID_R2_V1",
                "coordinate_crs_status": "SOURCE_CRS_UNCONFIRMED_WGS84_QUERY_ASSUMPTION",
                "missing_features": {
                    "vpd": "DEFERRED_NONLINEAR_MONTHLY_PROXY_NOT_USED",
                    "gdd_chilling_frost_heat_et0": "DEFERRED",
                },
            }
        )
        p["profile_hash"] = digest(p)
        profiles.append(p)
    perturbations = []
    for dx in config["coordinate_offsets_degrees"]:
        for dy in config["coordinate_offsets_degrees"]:
            if dx or dy:
                perturbations.append([dict(b) | extract(ds, b, dx, dy) for b in bases])
    ds.close()
    with threadpool_limits(limits=1):
        result = study(profiles, perturbations, config)
    write_json(output / "base-climate-profile-v1.json", profiles)
    write_json(output / "candidate-study.json", result)
    write_json(output / "climate-source-snapshot-manifest.json", frozen)
    flat = []
    for i, p in enumerate(profiles):
        row = {k: p[k] for k in ("base_id", "canonical_base_name", "elevation_m", "profile_hash")}
        for namespace in ("baseline", "recent"):
            row.update(
                {f"{namespace}_{k}": v for k, v in p[namespace].items() if not isinstance(v, list)}
            )
        row.update(
            {
                "baseline_zone": result.get("baseline_labels", [None] * 38)[i],
                "recent_zone": result.get("recent_labels", [None] * 38)[i],
                "temperature_30y_shift_c": p["recent"]["annual_mean_temperature_c"]
                - p["baseline"]["annual_mean_temperature_c"],
                "precipitation_30y_shift_mm": p["recent"]["annual_precipitation_mm"]
                - p["baseline"]["annual_precipitation_mm"],
                "drift_temperature_c": p["drift"]["temperature_c"],
                "drift_precipitation_mm": p["drift"]["precipitation_mm"],
                "ytd_temperature_c": p["ytd"]["same_month_anomalies"]["temperature_c"],
                "ytd_precipitation_mm": p["ytd"]["same_month_anomalies"]["precipitation_mm"],
                "coordinate_status": result.get(
                    "coordinate_sensitivity", [{"status": "NOT_EVALUATED_NO_STABLE_CANDIDATE"}] * 38
                )[i]["status"],
            }
        )
        row["zone_temporal_stability"] = (
            "COORDINATE_SENSITIVE"
            if row["coordinate_status"].endswith("REVIEW_REQUIRED")
            else "STABLE"
            if row["baseline_zone"] == row["recent_zone"] and row["baseline_zone"] is not None
            else "RECENT_SHIFT"
        )
        flat.append(row)
    csv_file(output / "base-climate-profile-v1.csv", flat)
    csv_file(output / "candidate-zone-evaluation.csv", result["scores"])
    mappings = [
        {
            "base_id": p["base_id"],
            "canonical_base_name": p["canonical_base_name"],
            "candidate": name,
            "zone": lab[i],
        }
        for name, lab in result["mappings"].items()
        for i, p in enumerate(profiles)
    ]
    csv_file(output / "candidate-zone-mapping.csv", mappings)
    csv_file(
        output / "coordinate-sensitivity.csv",
        result.get("coordinate_sensitivity", []),
        ["base_id", "grid_changed", "maximum_standardized_profile_delta", "zone_changed", "status"],
    )
    csv_file(
        output / "recent-30y-zone-sensitivity.csv",
        [
            {
                k: r[k]
                for k in (
                    "base_id",
                    "canonical_base_name",
                    "baseline_zone",
                    "recent_zone",
                    "temperature_30y_shift_c",
                    "precipitation_30y_shift_mm",
                    "zone_temporal_stability",
                )
            }
            for r in flat
        ],
    )
    csv_file(
        output / "recent-climate-drift-2021-2025.csv",
        [
            {
                "base_id": p["base_id"],
                "canonical_base_name": p["canonical_base_name"],
                "severity": p["drift_severity"],
            }
            | p["drift"]
            for p in profiles
        ],
    )
    csv_file(
        output / "current-year-2026-ytd.csv",
        [
            {
                "base_id": p["base_id"],
                "canonical_base_name": p["canonical_base_name"],
                "cutoff": "2026-08",
                "month_count": 8,
            }
            | p["ytd"]["same_month_anomalies"]
            for p in profiles
        ],
    )
    zones = []
    if result["selected"]:
        for zone in range(result["selected"]["k"]):
            members = [
                p
                for p, label in zip(profiles, result["baseline_labels"], strict=True)
                if label == zone
            ]
            import numpy as np

            features = {
                f: [
                    float(p["elevation_m"]) if f == "elevation_m" else p["baseline"][f]
                    for p in members
                ]
                for f in (
                    "elevation_m",
                    "annual_mean_temperature_c",
                    "coldest_month_mean_temperature_c",
                    "warmest_month_mean_temperature_c",
                    "annual_temperature_range_c",
                    "annual_precipitation_mm",
                    "precipitation_seasonality",
                    "monsoon_fraction",
                    "dewpoint_depression_c",
                    "annual_radiation_mj_m2",
                )
            }
            summary = {
                f: {"min": min(v), "median": float(np.median(v)), "max": max(v)}
                for f, v in features.items()
            }
            names = [p["canonical_base_name"] for p in members]
            zones.append(
                {
                    "zone": zone,
                    "base_count": len(members),
                    "members": names,
                    "representative_bases": sorted(
                        members,
                        key=lambda p: abs(
                            p["baseline"]["annual_mean_temperature_c"]
                            - summary["annual_mean_temperature_c"]["median"]
                        ),
                    )[:3],
                    "geography": {
                        c: [min(float(p[c]) for p in members), max(float(p[c]) for p in members)]
                        for c in ("latitude", "longitude")
                    },
                    "climate": summary,
                    "descriptive_label": (
                        f"温度中位{summary['annual_mean_temperature_c']['median']:.1f}°C / "
                        f"年降水中位{summary['annual_precipitation_mm']['median']:.0f}mm / "
                        f"海拔中位{summary['elevation_m']['median']:.0f}m"
                    ),
                }
            )
    write_json(output / "candidate-zone-profile.json", zones)
    write_json(
        output / "excluded-population.json",
        [
            {
                "base_id": b["base_id"],
                "canonical_base_name": b["canonical_base_name"],
                "status": "OUT_OF_YUNNAN_NOT_IN_YUNNAN_ZONE_FIT",
            }
            for b in registry["bases"]
            if b["region_scope"] != "YUNNAN_CORE"
        ],
    )
    manifest = {
        "task_id": config["task_id"],
        "source_hash": frozen["hash"],
        "registry_hash": registry["hash"],
        "config_hash": digest(config),
        "dependencies": {
            n: importlib.metadata.version(n)
            for n in ("numpy", "scipy", "scikit-learn", "xarray", "h5py", "h5netcdf")
        },
        "file_hashes": {p.name: file_hash(p) for p in sorted(output.iterdir()) if p.is_file()},
    }
    manifest["hash"] = digest(manifest)
    write_json(output / "artifact-manifest.json", manifest)
    print(
        json.dumps(
            {
                "recommendation": result["selected"],
                "status": result["recommendation_status"],
                "source_hash": frozen["hash"],
                "artifact_hash": manifest["hash"],
            },
            ensure_ascii=False,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("configs/climate_zone_r2.json"))
    args = parser.parse_args()
    run(args.source, args.registry, args.output, args.config)


if __name__ == "__main__":
    main()
