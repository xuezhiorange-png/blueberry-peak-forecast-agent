"""Offline retrieval coverage report; never promotes partial retrieval to dataset PASS."""

import argparse
import json
import socket
from pathlib import Path
from typing import Any

from scripts.climate_source_r2 import digest, file_hash, write_json
from scripts.normalize_era5_land_historical_weather_r1 import (
    audit_accumulations,
    no_network,
    read_native,
)


def report(root: Path) -> dict[str, Any]:
    manifest = json.loads((root / "request-manifest.json").read_text())
    if (
        digest({k: v for k, v in manifest.items() if k != "manifest_hash"})
        != manifest["manifest_hash"]
    ):
        raise ValueError("MANIFEST_HASH_MISMATCH")
    raw = []
    missing = []
    defects = []
    affected_bases: set[str] = set()
    for entry in manifest["requests"]:
        key = entry["request_id"]
        receipt = root / f"{key}.completed.json"
        if not receipt.exists():
            missing.append(key)
            continue
        r = json.loads(receipt.read_text())
        if file_hash(root / f"{key}.raw") != r["raw_sha256"]:
            raise ValueError("RAW_HASH_MISMATCH")
        raw.append({"request_hash": key, "raw_sha256": r["raw_sha256"]})
        lat, lon = entry["request"]["area"][:2]
        errors = audit_accumulations(read_native(root / f"{key}.raw", str(lat), str(lon)))
        base_ids = [
            b["base_id"]
            for b in manifest["locations"]
            if [float(b["selected_grid_latitude"]), float(b["selected_grid_longitude"])]
            == [lat, lon]
        ]
        for error in errors:
            defects.append(
                {**error, "request_hash": key, "raw_sha256": r["raw_sha256"], "base_ids": base_ids}
            )
        if errors:
            affected_bases.update(base_ids)
    return {
        "dataset_build_status": "BLOCKED"
        if defects
        else ("RETRIEVAL_IN_PROGRESS" if missing else "RAW_RETRIEVAL_COMPLETE"),
        "blocker": "NATIVE_ACCUMULATION_NEGATIVE_DIFFERENCE" if defects else None,
        "native_accumulation_defect_count": len(defects),
        "native_accumulation_defects": defects,
        "per_base_completeness": {
            b["base_id"]: (
                "BLOCKED_NATIVE_ACCUMULATION"
                if b["base_id"] in affected_bases
                else "NOT_YET_VERIFIED"
            )
            for b in manifest["locations"]
        },
        "request_manifest_hash": manifest["manifest_hash"],
        "processing_config_hash": manifest["config_hash"],
        "base_identity_set_hash": manifest["base_identity_set_hash"],
        "location_authority_hash": manifest["config"]["registry_file_sha256"],
        "query_crs_assumption": manifest["config"]["query_crs_assumption"],
        "crs_verification_status": "NOT_ESTABLISHED",
        "base_crs_authority_changed": False,
        "qualified_location_base_count": len(manifest["locations"]),
        "expected_request_count": len(manifest["requests"]),
        "raw_artifact_count": len(raw),
        "raw_artifact_set_hash": digest(raw),
        "missing_request_count": len(missing),
        "missing_request_hashes": missing,
        "hourly_dataset_hash": None,
        "daily_dataset_hash": None,
        "offline_replay": "NOT_EXECUTED",
        "raw_artifacts": raw,
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
                    "native_accumulation_defect_count",
                    "missing_request_count",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
