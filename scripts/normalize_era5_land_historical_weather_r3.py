"""Offline R3 projections with raw values retained and per-base correction provenance."""

import argparse
import gzip
import hashlib
import json
import socket
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from scripts.build_era5_land_historical_weather_r1 import utc_bounds
from scripts.climate_source_r2 import digest, file_hash, write_json
from scripts.era5_historical_dataset_r3 import load
from scripts.era5_source_artifact_correction_r3 import REASON, VERSION, correct_value, gate, qualify
from scripts.era5_timeseries_source_r2 import Native
from scripts.normalize_era5_land_historical_weather_r1 import (
    canonical_line,
    no_network,
    number,
    validate_rows,
)
from scripts.normalize_era5_land_historical_weather_r2 import local_day, verified_source


def corrected_day(
    native: Native, corrected: Native, start: datetime, source: str
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    hours, day = local_day(corrected, start, source)
    for row in hours:
        var = row["native_variable"]
        stamp = datetime.fromisoformat(row["valid_time_utc"])
        raw = native[var, stamp]
        row["native_value"] = number(raw)
        row["native_value_exact_hex"] = raw.hex()
        row["source_corrected_native_value"] = format(
            Decimal.from_float(corrected[var, stamp]), "f"
        )
        row["source_corrected_value_exact_hex"] = corrected[var, stamp].hex()
        row["source_artifact_correction_applied"] = var in {"tp", "ssrd"} and raw < 0
        row["source_artifact_correction_version"] = VERSION
        row["source_processing_version"] = "CDS_POINT_TIMESERIES_R3"
    return hours, day


def replay(root: Path, output: Path) -> dict[str, Any]:
    m, policy = load(root)
    audits = {}
    for entry in m["requests"]:
        _, raw_audit = verified_source(root, entry)
        audit = qualify(raw_audit)
        gate(audit)
        audits[entry["request_hash"]] = audit
    output.mkdir(parents=True, exist_ok=False)
    counts = {"hourly": 0, "daily": 0, "corrections": 0}
    hashes = {k: hashlib.sha256() for k in counts}
    corrected_counts = {"tp": 0, "ssrd": 0}
    with (
        (output / "hourly.jsonl.gz").open("xb") as compressed,
        gzip.GzipFile(filename="", mode="wb", fileobj=compressed, mtime=0) as hs,
        (output / "daily.jsonl").open("xb") as ds,
        (output / "corrections.jsonl").open("xb") as cs,
    ):
        for loc in sorted(m["locations"], key=lambda b: b["base_id"]):
            for entry in sorted(m["requests"], key=lambda e: e["business_start"]):
                if loc["base_id"] not in entry["base_ids"]:
                    continue
                native, audit_raw = verified_source(root, entry)
                gate(qualify(audit_raw))
                corrected = {k: correct_value(k[0], v) for k, v in native.items()}
                start, end = utc_bounds(entry["business_start"], entry["business_end"])
                while start < end:
                    hours, day = corrected_day(native, corrected, start, audit_raw["raw_sha256"])
                    corrections = []
                    for row in hours:
                        if row["source_artifact_correction_applied"]:
                            var = row["native_variable"]
                            corrected_counts[var] += 1
                            corrections.append(
                                {
                                    "base_id": loc["base_id"],
                                    "selected_grid_latitude": loc["selected_grid_latitude"],
                                    "selected_grid_longitude": loc["selected_grid_longitude"],
                                    "timestamp": row["source_valid_time_utc"],
                                    "variable": var,
                                    "raw_negative_value": format(
                                        float.fromhex(row["native_value_exact_hex"]), ".17g"
                                    ),
                                    "raw_negative_value_exact_hex": row["native_value_exact_hex"],
                                    "native_unit": row["native_unit"],
                                    "corrected_value": "0",
                                    "correction_reason": REASON,
                                    "correction_version": VERSION,
                                    "raw_artifact_sha256": row["source_artifact_hash"],
                                }
                            )
                    day_row = {
                        **day,
                        "base_id": loc["base_id"],
                        "local_date": hours[0]["local_date"],
                        "temperature_unit": "degC",
                        "hourly_sample_count": 24,
                        "processing_version": "BASE_WEATHER_DAILY_V1",
                        "source_artifact_correction_version": VERSION,
                        "source_artifact_hashes": [audit_raw["raw_sha256"]],
                    }
                    for kind, stream, rows in (
                        (
                            "hourly",
                            hs,
                            [
                                {
                                    **loc,
                                    **r,
                                    "query_coordinate": entry["request"]["location"],
                                    "query_mode": entry.get("query_mode", "ORIGINAL_COORDINATE"),
                                }
                                for r in hours
                            ],
                        ),
                        ("daily", ds, [day_row]),
                        ("corrections", cs, corrections),
                    ):
                        for row in rows:
                            data = canonical_line({**row, "row_hash": digest(row)})
                            stream.write(data)
                            hashes[kind].update(data)
                            counts[kind] += 1
                    start += timedelta(days=1)
    summary: dict[str, Any] = {
        "correction_policy_hash": digest(policy),
        "source_artifact_correction_version": VERSION,
        "raw_artifact_count": len(audits),
        "raw_artifact_set_hash": digest(
            [{"request_hash": k, "raw_sha256": a["raw_sha256"]} for k, a in sorted(audits.items())]
        ),
        **{f"{k}_row_count": v for k, v in counts.items()},
        **{f"{k}_dataset_hash": v.hexdigest() for k, v in hashes.items()},
        "corrected_tp_count": corrected_counts["tp"],
        "corrected_ssrd_count": corrected_counts["ssrd"],
        "corrected_count_scope": "BASE_BUSINESS_HOURLY_PROJECTIONS",
        "complete_base_count": len(m["locations"]),
        "incomplete_base_count": 0,
        "missing_interval_count": 0,
        "duplicate_interval_count": 0,
        "outside_envelope_negative_count": 0,
        "provider_grid_selection_parity": "PASS_ALL_REQUESTS",
    }
    for kind in counts:
        path = output / ("hourly.jsonl.gz" if kind == "hourly" else f"{kind}.jsonl")
        if kind == "hourly":
            verify_hourly(path, summary["hourly_dataset_hash"], counts["hourly"])
        elif validate_rows(path, summary[f"{kind}_dataset_hash"]) != counts[kind]:
            raise ValueError("ROW_COUNT_MISMATCH")
        summary[f"{kind}_artifact_sha256"] = file_hash(path)
        path.chmod(0o400)
    write_json(output / "dataset-manifest.json", summary)
    return summary


def verify_hourly(path: Path, expected_hash: str, expected_count: int) -> None:
    actual = hashlib.sha256()
    count = 0
    with gzip.open(path, "rb") as source:
        for line in source:
            actual.update(line)
            row = json.loads(line)
            row_hash = row.pop("row_hash")
            if digest(row) != row_hash:
                raise ValueError("NORMALIZED_ROW_HASH_MISMATCH")
            count += 1
    if actual.hexdigest() != expected_hash or count != expected_count:
        raise ValueError("ROW_SET_HASH_OR_COUNT_MISMATCH")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    socket.socket.connect = no_network  # type: ignore[method-assign]
    socket.socket.connect_ex = no_network  # type: ignore[method-assign]
    socket.create_connection = no_network
    print(json.dumps(replay(a.root, a.output), sort_keys=True))


if __name__ == "__main__":
    main()
