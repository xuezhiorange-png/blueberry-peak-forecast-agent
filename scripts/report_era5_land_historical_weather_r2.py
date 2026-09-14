"""Offline receipt/raw verification. Partial or negative source data is never dataset PASS."""

import argparse
import json
import socket
from pathlib import Path
from typing import Any

from scripts.climate_source_r2 import digest, write_json
from scripts.era5_timeseries_source_r2 import validate_manifest
from scripts.normalize_era5_land_historical_weather_r1 import no_network
from scripts.normalize_era5_land_historical_weather_r2 import verified_source


def report(root: Path) -> dict[str, Any]:
    manifest = json.loads((root / "request-manifest.json").read_text())
    validate_manifest(manifest)
    audits = []
    missing = []
    projections = []
    for entry in manifest["requests"]:
        if not (root / f"{entry['request_hash']}.completed.json").exists():
            missing.append(entry["request_hash"])
            continue
        _, audit = verified_source(root, entry)
        audits.append(audit)
        for loc in manifest["locations"]:
            if loc["base_id"] in entry["base_ids"]:
                projections.append(
                    {
                        **loc,
                        "request_hash": entry["request_hash"],
                        "expected_selected_grid_latitude": entry["expected_selected_grid_latitude"],
                        "expected_selected_grid_longitude": entry[
                            "expected_selected_grid_longitude"
                        ],
                        **audit["points"][0],
                        "provider_grid_selection_parity": "PASS",
                    }
                )
    negatives = sum(a["provider_negative_value_count"] for a in audits)
    gaps = sum(a["missing_interval_count"] for a in audits)
    extra = sum(a["unexpected_interval_count"] for a in audits)
    blocker = (
        "PROVIDER_DEACCUMULATED_NEGATIVE_VALUE"
        if negatives
        else "HOURLY_COVERAGE_MISMATCH"
        if gaps or extra
        else "RAW_REQUEST_INCOMPLETE"
        if missing
        else None
    )
    raw = sorted(
        [{"request_hash": a["request_hash"], "raw_sha256": a["raw_sha256"]} for a in audits],
        key=lambda a: a["request_hash"],
    )
    return {
        "dataset_build_status": "BLOCKED" if blocker else "SOURCE_GATES_PASS",
        "blocker": blocker,
        "source_product": manifest["source_product"],
        "request_manifest_hash": manifest["manifest_hash"],
        "config_hash": manifest["config_hash"],
        "base_identity_set_hash": manifest["base_identity_set_hash"],
        "location_authority_hash": manifest["location_authority_hash"],
        "expected_base_count": 38,
        "planned_request_count": len(manifest["requests"]),
        "missing_request_count": len(missing),
        "missing_request_hashes": missing,
        "raw_artifact_count": len(raw),
        "raw_artifacts": raw,
        "raw_artifact_set_hash": digest(raw),
        "raw_hash_verification": "PASS",
        "provider_negative_value_count": negatives,
        "missing_interval_count": gaps,
        "unexpected_interval_count": extra,
        "duplicate_interval_count": 0,
        "coverage_count_scope": "DOWNLOADED_RAW_ONLY_NOT_UNRETRIEVED_REQUESTS",
        "provider_grid_selection_parity": "PASS_DOWNLOADED_ONLY" if audits else "NOT_VERIFIED",
        "base_grid_projections": projections,
        "raw_audits": audits,
        "complete_base_count": 0,
        "incomplete_base_count": 38,
        "hourly_row_count": 0,
        "daily_row_count": 0,
        "hourly_dataset_hash": None,
        "daily_dataset_hash": None,
        "normalized_dataset_replay": "BLOCKED" if blocker else "NOT_EXECUTED",
        "custom_deaccumulation": False,
        "custom_negative_clipping": False,
        "query_crs_assumption": "WGS84",
        "crs_verification_status": "NOT_ESTABLISHED",
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    socket.socket.connect = no_network  # type: ignore[method-assign]
    socket.socket.connect_ex = no_network  # type: ignore[method-assign]
    socket.create_connection = no_network
    result = report(args.root)
    write_json(args.output, result)
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "dataset_build_status",
                    "blocker",
                    "raw_artifact_count",
                    "raw_artifact_set_hash",
                    "provider_negative_value_count",
                    "missing_request_count",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
