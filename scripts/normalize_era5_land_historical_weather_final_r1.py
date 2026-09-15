"""Build the accepted ERA5-Land facts from one characterized raw artifact set.

The legacy R3 envelope remains available for historical diagnostics.  This
module is a separate, hash-pinned acceptance path: only the exact source
manifest, raw artifact set, characterization, and provider product named by
the final policy may apply negative-to-zero normalization to ``tp`` and
``ssrd``.
"""

import argparse
import gzip
import hashlib
import json
import math
import socket
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

from scripts.build_era5_land_historical_weather_r1 import utc_bounds
from scripts.climate_source_r2 import digest, file_hash, write_json
from scripts.era5_historical_dataset_r3 import load
from scripts.era5_timeseries_source_r2 import Native
from scripts.normalize_era5_land_historical_weather_r1 import (
    UNITS,
    canonical_line,
    no_network,
    number,
    validate_rows,
)
from scripts.normalize_era5_land_historical_weather_r2 import verified_source

CONFIG = Path("configs/era5_land_historical_weather_final_r1.json")
POLICY_VERSION = "ERA5_LAND_TIMESERIES_CHARACTERIZED_SET_NEGATIVE_TO_ZERO_V1"
SOURCE_PRODUCT = "reanalysis-era5-land-timeseries"
SOURCE_MANIFEST_HASH = "2bd5f909945f0ba677d9818c9cb23a3eb80119cb9e03407707cbbe83880bddb1"
RAW_ARTIFACT_SET_HASH = "6df5a8e909447384a3b33414facf6e768d1fb31c52b89ebec59bec37e3f358d8"
CHARACTERIZATION_HASH = "9994f4290bc5c2de144ae792813715aac84acd7b42f634ee69f866fa0bb568a2"
CORRECTION_REASON = "CHARACTERIZED_SOURCE_ARTIFACT_NEGATIVE_TO_ZERO"
CORRECTION_VARIABLES = frozenset({"tp", "ssrd"})
PROCESSING_VERSION = "ERA5_LAND_HOURLY_NORMALIZED_V1"
SOURCE_PROCESSING_VERSION = "CDS_POINT_TIMESERIES_R2"
DAILY_PROCESSING_VERSION = "BASE_WEATHER_DAILY_V1"


def load_final_config(path: Path = CONFIG) -> dict[str, Any]:
    config = cast(dict[str, Any], json.loads(path.read_text()))
    expected = {
        "source_artifact_policy_version": POLICY_VERSION,
        "source_product": SOURCE_PRODUCT,
        "source_product_kind": "CDS_OFFICIAL_POINT_TIMESERIES",
        "source_manifest_hash": SOURCE_MANIFEST_HASH,
        "raw_artifact_set_hash": RAW_ARTIFACT_SET_HASH,
        "characterization_hash": CHARACTERIZATION_HASH,
        "expected_raw_artifact_count": 105,
        "expected_base_count": 38,
        "expected_unique_grid_cell_count": 35,
        "expected_season_count": 3,
        "negative_to_zero_variables": ["ssrd", "tp"],
        "tp_negative_numeric_envelope": None,
        "ssrd_negative_numeric_envelope": None,
        "positive_tp_thresholding": False,
        "positive_ssrd_thresholding": False,
        "other_variable_correction": False,
        "custom_deaccumulation": False,
        "provider_deaccumulation": True,
        "interpolation": "NONE",
        "dem_downscaling": False,
        "spatial_extraction_policy": "CDS_0P1_NEAREST_GRID_CELL_V1",
        "local_timezone": "Asia/Shanghai",
        "query_crs_assumption": "WGS84",
        "crs_verification_status": "NOT_ESTABLISHED",
        "weather_source_authority_frozen": False,
        "live_weather_forecast_authority_frozen": False,
        "historical_as_issued_pit_status": "PIT_NOT_ESTABLISHED",
        "strict_operational_forecast_replay_blocked": True,
        "weather_model_training": False,
        "weather_feature_selection": False,
        "weather_incremental_value_scoring": False,
        "gdd_generated": False,
        "vpd_generated": False,
        "et0_generated": False,
    }
    if any(config.get(key) != value for key, value in expected.items()):
        raise ValueError("FINAL_SOURCE_ARTIFACT_POLICY_CONFIG_MISMATCH")
    return config


def _characterization_body(characterization: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in characterization.items() if key != "characterization_hash"}


def validate_characterization(path: Path) -> dict[str, Any]:
    characterization = cast(dict[str, Any], json.loads(path.read_text()))
    if digest(_characterization_body(characterization)) != characterization.get(
        "characterization_hash"
    ):
        raise ValueError("CHARACTERIZATION_HASH_MISMATCH")
    expected = {
        "characterization_hash": CHARACTERIZATION_HASH,
        "source_product": SOURCE_PRODUCT,
        "source_product_kind": "CDS_OFFICIAL_POINT_TIMESERIES",
        "request_manifest_hash": SOURCE_MANIFEST_HASH,
        "raw_artifact_set_hash": RAW_ARTIFACT_SET_HASH,
        "raw_artifact_count": 105,
        "characterized_request_count": 105,
        "failed_request_count": 0,
        "normalization_generated": False,
        "custom_deaccumulation": False,
        "positive_value_thresholding": False,
        "positive_value_correction": False,
    }
    if any(characterization.get(key) != value for key, value in expected.items()):
        raise ValueError("CHARACTERIZATION_SCOPE_MISMATCH")
    integrity = characterization.get("integrity", {})
    if integrity != {
        "duplicate_interval_count": 0,
        "missing_interval_count": 0,
        "nonfinite_value_count": 0,
        "provider_grid_selection_parity": "PASS_ALL_CHARACTERIZED_REQUESTS",
    }:
        raise ValueError("CHARACTERIZATION_INTEGRITY_MISMATCH")
    return characterization


def apply_source_correction(variable: str, value: float) -> tuple[float, bool]:
    """Apply only the final policy to a provider value, never a numeric envelope."""
    if not math.isfinite(value):
        raise ValueError("NONFINITE_NATIVE_VALUE")
    if variable in CORRECTION_VARIABLES and value < 0:
        return 0.0, True
    return value, False


def raw_artifact_set_hash(audits: dict[str, dict[str, Any]]) -> str:
    return cast(
        str,
        digest(
            [
                {"request_hash": key, "raw_sha256": audits[key]["raw_sha256"]}
                for key in sorted(audits)
            ]
        ),
    )


def _audit_sources(
    root: Path, manifest: dict[str, Any]
) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    if manifest.get("manifest_hash") != SOURCE_MANIFEST_HASH:
        raise ValueError("UNCHARACTERIZED_SOURCE_ARTIFACT_SET_REQUIRES_REVIEW")
    if manifest.get("source_product") != SOURCE_PRODUCT or len(manifest["requests"]) != 105:
        raise ValueError("UNCHARACTERIZED_SOURCE_ARTIFACT_SET_REQUIRES_REVIEW")
    audits: dict[str, dict[str, Any]] = {}
    negative_counts = {"tp": 0, "ssrd": 0}
    for entry in manifest["requests"]:
        _, audit = verified_source(root, entry)
        if (
            audit["source_product"] != SOURCE_PRODUCT
            or audit["provider_grid_selection_parity"] != "PASS"
            or audit["missing_interval_count"]
            or audit["unexpected_interval_count"]
            or audit["duplicate_interval_count"]
        ):
            raise ValueError("SOURCE_ARTIFACT_QUALITY_GATE_FAILED")
        audits[entry["request_hash"]] = audit
        for item in audit["negative_values"]:
            if item["variable"] in negative_counts:
                negative_counts[item["variable"]] += 1
    if len(audits) != 105 or raw_artifact_set_hash(audits) != RAW_ARTIFACT_SET_HASH:
        raise ValueError("UNCHARACTERIZED_SOURCE_ARTIFACT_SET_REQUIRES_REVIEW")
    return audits, negative_counts


def corrected_day(
    native: Native,
    corrected: Native,
    start: datetime,
    source: str,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Normalize one local day while retaining both raw and corrected values."""
    hourly: list[dict[str, Any]] = []
    normalized: dict[str, list[Decimal]] = {variable: [] for variable in UNITS}
    local_date = start.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
    for hour in range(24):
        instant = start + timedelta(hours=hour)
        for variable in sorted(UNITS):
            interval = variable in CORRECTION_VARIABLES
            valid = instant + timedelta(hours=1) if interval else instant
            key = variable, valid
            if key not in corrected:
                raise ValueError("HOURLY_GAP")
            raw = native[key]
            value = corrected[key]
            if not math.isfinite(raw) or not math.isfinite(value):
                raise ValueError("NONFINITE_NATIVE_VALUE")
            converted = value - 273.15 if variable in {"t2m", "d2m"} else value
            if variable == "tp":
                converted *= 1000
            text = number(converted)
            normalized[variable].append(Decimal(text))
            hourly.append(
                {
                    "valid_time_utc": valid.isoformat(),
                    "source_valid_time_utc": valid.isoformat(),
                    "support_start_utc": instant.isoformat(),
                    "support_end_utc": (instant + timedelta(hours=1)).isoformat(),
                    "local_date": local_date,
                    "temporal_semantics": (
                        "PROVIDER_DEACCUMULATED_HOURLY_INTERVAL_END"
                        if interval
                        else "INSTANT_AT_START"
                    ),
                    "native_variable": variable,
                    "native_value": number(raw),
                    "native_value_exact_hex": raw.hex(),
                    "native_unit": UNITS[variable][0],
                    "normalized_variable": UNITS[variable][1],
                    "normalized_value": text,
                    "normalized_unit": UNITS[variable][2],
                    "source_dataset": SOURCE_PRODUCT,
                    "source_artifact_hash": source,
                    "processing_version": PROCESSING_VERSION,
                    "source_processing_version": SOURCE_PROCESSING_VERSION,
                    "source_corrected_native_value": number(value),
                    "source_corrected_value_exact_hex": value.hex(),
                    "source_artifact_correction_applied": (
                        variable in CORRECTION_VARIABLES and raw < 0
                    ),
                    "source_artifact_correction_version": POLICY_VERSION,
                }
            )
    with localcontext() as context:
        context.prec = 50
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


def _write_rows(
    root: Path,
    output: Path,
    manifest: dict[str, Any],
    audits: dict[str, dict[str, Any]],
) -> tuple[dict[str, int], dict[str, str], dict[str, int]]:
    counts = {"hourly": 0, "daily": 0, "corrections": 0}
    hashes = {kind: hashlib.sha256() for kind in counts}
    corrected_counts = {"tp": 0, "ssrd": 0}
    locations = {item["base_id"]: item for item in manifest["locations"]}
    with (
        (output / "hourly.jsonl.gz").open("xb") as compressed,
        gzip.GzipFile(filename="", mode="wb", fileobj=compressed, mtime=0) as hourly_stream,
        (output / "daily.jsonl").open("xb") as daily_stream,
        (output / "corrections.jsonl").open("xb") as correction_stream,
    ):
        entries = sorted(
            manifest["requests"],
            key=lambda item: (item["business_start"], item["request_hash"]),
        )
        for entry in entries:
            key = entry["request_hash"]
            native, audit = verified_source(root, entry)
            if audit["raw_sha256"] != audits[key]["raw_sha256"]:
                raise ValueError("SOURCE_AUDIT_REPLAY_MISMATCH")
            corrected = {}
            for native_key, value in native.items():
                corrected[native_key], _ = apply_source_correction(native_key[0], value)
            start, end = utc_bounds(entry["business_start"], entry["business_end"])
            while start < end:
                hours, day = corrected_day(native, corrected, start, audit["raw_sha256"])
                correction_rows_by_base: dict[str, list[dict[str, Any]]] = {
                    base_id: [] for base_id in entry["base_ids"]
                }
                for row in hours:
                    if not row["source_artifact_correction_applied"]:
                        continue
                    variable = row["native_variable"]
                    corrected_counts[variable] += len(entry["base_ids"])
                    for base_id in sorted(entry["base_ids"]):
                        location = locations[base_id]
                        correction_rows_by_base[base_id].append(
                            {
                                "base_id": base_id,
                                "selected_grid_latitude": location["selected_grid_latitude"],
                                "selected_grid_longitude": location["selected_grid_longitude"],
                                "timestamp": row["source_valid_time_utc"],
                                "variable": variable,
                                "provider_raw_value": format(
                                    float.fromhex(row["native_value_exact_hex"]), ".17g"
                                ),
                                "provider_raw_value_exact_hex": row["native_value_exact_hex"],
                                "raw_negative_value": format(
                                    float.fromhex(row["native_value_exact_hex"]), ".17g"
                                ),
                                "raw_negative_value_exact_hex": row["native_value_exact_hex"],
                                "native_unit": row["native_unit"],
                                "normalized_value": "0",
                                "corrected_value": "0",
                                "correction_reason": CORRECTION_REASON,
                                "source_artifact_policy_version": POLICY_VERSION,
                                "correction_version": POLICY_VERSION,
                                "raw_artifact_sha256": audit["raw_sha256"],
                            }
                        )
                for base_id in sorted(entry["base_ids"]):
                    location = locations[base_id]
                    day_row = {
                        **day,
                        "base_id": base_id,
                        "local_date": hours[0]["local_date"],
                        "processing_version": DAILY_PROCESSING_VERSION,
                        "source_artifact_correction_version": POLICY_VERSION,
                        "source_artifact_hashes": [audit["raw_sha256"]],
                    }
                    rows = [
                        (
                            "hourly",
                            hourly_stream,
                            [
                                {
                                    **location,
                                    **row,
                                    "query_coordinate": entry["request"]["location"],
                                    "query_mode": entry.get("query_mode", "ORIGINAL_COORDINATE"),
                                }
                                for row in hours
                            ],
                        ),
                        ("daily", daily_stream, [{**day_row, "hourly_sample_count": 24}]),
                        (
                            "corrections",
                            correction_stream,
                            correction_rows_by_base[base_id],
                        ),
                    ]
                    for kind, stream, output_rows in rows:
                        for row in output_rows:
                            data = canonical_line({**row, "row_hash": digest(row)})
                            stream.write(data)
                            hashes[kind].update(data)
                            counts[kind] += 1
                start += timedelta(days=1)
    return counts, {kind: value.hexdigest() for kind, value in hashes.items()}, corrected_counts


def _validate_hourly(path: Path, expected_hash: str, expected_count: int) -> None:
    actual = hashlib.sha256()
    count = 0
    with gzip.open(path, "rb") as stream:
        for line in stream:
            actual.update(line)
            row = json.loads(line)
            row_hash = row.pop("row_hash")
            if digest(row) != row_hash:
                raise ValueError("NORMALIZED_ROW_HASH_MISMATCH")
            count += 1
    if actual.hexdigest() != expected_hash or count != expected_count:
        raise ValueError("ROW_SET_HASH_OR_COUNT_MISMATCH")


def replay(
    root: Path,
    output: Path,
    characterization_path: Path,
    config_path: Path = CONFIG,
) -> dict[str, Any]:
    config = load_final_config(config_path)
    manifest, _ = load(root)
    characterization = validate_characterization(characterization_path)
    if (
        config["source_manifest_hash"] != manifest["manifest_hash"]
        or characterization["request_manifest_hash"] != manifest["manifest_hash"]
        or characterization["raw_artifact_set_hash"] != config["raw_artifact_set_hash"]
        or manifest["source_product"] != config["source_product"]
    ):
        raise ValueError("UNCHARACTERIZED_SOURCE_ARTIFACT_SET_REQUIRES_REVIEW")
    audits, negative_counts = _audit_sources(root, manifest)
    output.mkdir(parents=True, exist_ok=False)
    counts, dataset_hashes, corrected_counts = _write_rows(root, output, manifest, audits)
    for kind in counts:
        path = output / ("hourly.jsonl.gz" if kind == "hourly" else f"{kind}.jsonl")
        if kind == "hourly":
            _validate_hourly(path, dataset_hashes[f"{kind}"], counts[kind])
        elif validate_rows(path, dataset_hashes[kind]) != counts[kind]:
            raise ValueError("ROW_COUNT_MISMATCH")
        path.chmod(0o400)
    summary: dict[str, Any] = {
        "task_id": "V0_5_S2_ERA5_LAND_HISTORICAL_WEATHER_DATASET_FINAL_R1",
        "source_artifact_policy_version": POLICY_VERSION,
        "source_product": SOURCE_PRODUCT,
        "source_product_kind": "CDS_OFFICIAL_POINT_TIMESERIES",
        "source_manifest_hash": manifest["manifest_hash"],
        "source_manifest_hash_match": True,
        "raw_artifact_count": len(audits),
        "raw_artifact_set_hash": raw_artifact_set_hash(audits),
        "raw_artifact_set_hash_match": True,
        "characterization_hash": characterization["characterization_hash"],
        "characterization_hash_match": True,
        "hourly_row_count": counts["hourly"],
        "hourly_dataset_hash": dataset_hashes["hourly"],
        "daily_row_count": counts["daily"],
        "daily_dataset_hash": dataset_hashes["daily"],
        "correction_record_count": counts["corrections"],
        "correction_record_hash": dataset_hashes["corrections"],
        "tp_negative_raw_count": negative_counts["tp"],
        "ssrd_negative_raw_count": negative_counts["ssrd"],
        "tp_corrected_to_zero_count": negative_counts["tp"],
        "ssrd_corrected_to_zero_count": negative_counts["ssrd"],
        "tp_projected_correction_record_count": corrected_counts["tp"],
        "ssrd_projected_correction_record_count": corrected_counts["ssrd"],
        "positive_values_modified_count": 0,
        "other_variable_correction_count": 0,
        "correction_count_scope": "RAW_PROVIDER_OBSERVATIONS",
        "projected_correction_count_scope": "BASE_BUSINESS_HOURLY_PROJECTIONS",
        "missing_interval_count": 0,
        "duplicate_interval_count": 0,
        "nonfinite_value_count": 0,
        "complete_base_count": len(manifest["locations"]),
        "incomplete_base_count": 0,
        "unique_grid_cell_count": len(
            {
                (item["expected_selected_grid_latitude"], item["expected_selected_grid_longitude"])
                for item in manifest["requests"]
            }
        ),
        "provider_grid_selection_parity": "PASS_ALL_REQUESTS",
        "provider_deaccumulation_used": True,
        "custom_deaccumulation_used": False,
        "custom_negative_clipping_used": False,
        "positive_tp_thresholding": False,
        "positive_ssrd_thresholding": False,
        "other_variables_corrected": False,
        "local_timezone": "Asia/Shanghai",
        "weather_model_training": False,
        "weather_incremental_value_scoring": False,
        "historical_as_issued_pit_status": "PIT_NOT_ESTABLISHED",
        "weather_source_authority_frozen": False,
        "live_weather_forecast_authority_frozen": False,
        "offline_network_used": False,
    }
    for kind in counts:
        path = output / ("hourly.jsonl.gz" if kind == "hourly" else f"{kind}.jsonl")
        summary[f"{kind}_artifact_sha256"] = file_hash(path)
    summary["config_hash"] = digest(config)
    write_json(output / "dataset-manifest.json", summary)
    return summary


def compare_replays(first: Path, second: Path) -> dict[str, Any]:
    names = ("hourly.jsonl.gz", "daily.jsonl", "corrections.jsonl", "dataset-manifest.json")
    file_equal = {
        name: (first / name).read_bytes() == (second / name).read_bytes() for name in names
    }
    one = json.loads((first / "dataset-manifest.json").read_text())
    two = json.loads((second / "dataset-manifest.json").read_text())
    fields = (
        "hourly_row_count",
        "hourly_dataset_hash",
        "daily_row_count",
        "daily_dataset_hash",
        "correction_record_count",
        "correction_record_hash",
    )
    return {
        "raw_artifact_hash_replay": one["raw_artifact_set_hash"] == two["raw_artifact_set_hash"],
        "hourly_row_count_equal": one["hourly_row_count"] == two["hourly_row_count"],
        "hourly_dataset_hash_equal": one["hourly_dataset_hash"] == two["hourly_dataset_hash"],
        "daily_row_count_equal": one["daily_row_count"] == two["daily_row_count"],
        "daily_dataset_hash_equal": one["daily_dataset_hash"] == two["daily_dataset_hash"],
        "correction_record_count_equal": one["correction_record_count"]
        == two["correction_record_count"],
        "correction_record_hash_equal": one["correction_record_hash"]
        == two["correction_record_hash"],
        "summary_fields_equal": all(one[field] == two[field] for field in fields),
        "byte_equal": file_equal,
        "deterministic_replay": all(file_equal.values()) and one == two,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("replay", "compare"))
    parser.add_argument("--root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--second", type=Path)
    parser.add_argument("--characterization", type=Path)
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--comparison-output", type=Path)
    args = parser.parse_args()
    if args.action == "replay":
        if args.root is None or args.output is None or args.characterization is None:
            parser.error("replay requires --root, --output, and --characterization")
        socket.socket.connect = no_network  # type: ignore[method-assign]
        socket.socket.connect_ex = no_network  # type: ignore[method-assign]
        socket.create_connection = no_network
        result = replay(args.root, args.output, args.characterization, args.config)
    else:
        if args.output is None or args.second is None:
            parser.error("compare requires --output and --second")
        result = compare_replays(args.output, args.second)
        if args.comparison_output is not None:
            write_json(args.comparison_output, result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
