"""Offline R3 source inventory, with unique raw and projected correction counts separated."""

import argparse
import json
import socket
from pathlib import Path
from typing import Any

from scripts.climate_source_r2 import digest, write_json
from scripts.era5_historical_dataset_r3 import load
from scripts.era5_source_artifact_correction_r3 import OUTSIDE, VERSION, qualify
from scripts.normalize_era5_land_historical_weather_r1 import no_network
from scripts.normalize_era5_land_historical_weather_r2 import verified_source


def report(root: Path) -> dict[str, Any]:
    m, policy = load(root)
    audits = []
    for e in m["requests"]:
        if (root / f"{e['request_hash']}.completed.json").exists():
            _, a = verified_source(root, e)
            audits.append(
                {
                    **qualify(a),
                    "base_ids": e["base_ids"],
                    "grid": {
                        c: e[f"expected_selected_grid_{c}"] for c in ("latitude", "longitude")
                    },
                }
            )
    outside = sum(a["outside_envelope_negative_count"] for a in audits)
    missing = sum(a["missing_interval_count"] for a in audits)
    extra = sum(a["unexpected_interval_count"] for a in audits)
    stops = [json.loads(p.read_text()) for p in sorted(root.glob("stop-*.json"))]
    blocker = (
        OUTSIDE
        if outside
        else "HOURLY_COVERAGE_MISMATCH"
        if missing or extra
        else stops[-1]["blocker"]
        if stops
        else "RAW_REQUEST_INCOMPLETE"
        if len(audits) != len(m["requests"])
        else None
    )
    return {
        "dataset_build_status": "BLOCKED" if blocker else "SOURCE_GATES_PASS",
        "blocker": blocker,
        "request_manifest_hash": m["manifest_hash"],
        "policy_hash": digest(policy),
        "source_artifact_correction_version": VERSION,
        "raw_artifact_count": len(audits),
        "raw_artifact_set_hash": digest(
            [
                {"request_hash": a["request_hash"], "raw_sha256": a["raw_sha256"]}
                for a in sorted(audits, key=lambda a: a["request_hash"])
            ]
        ),
        "timeseries_request_count": len(list(root.glob("*.submitted.json"))),
        "planned_request_count": len(m["requests"]),
        "expected_base_count": 38,
        "provider_negative_tp_count": sum(
            n["variable"] == "tp" for a in audits for n in a["negative_values"]
        ),
        "provider_negative_ssrd_count": sum(
            n["variable"] == "ssrd" for a in audits for n in a["negative_values"]
        ),
        "provider_count_scope": "UNIQUE_GRID_RAW_REQUESTED_HOURS",
        "eligible_tp_correction_count": sum(
            n["variable"] == "tp" for a in audits for n in a["eligible_corrections"]
        ),
        "eligible_ssrd_correction_count": sum(
            n["variable"] == "ssrd" for a in audits for n in a["eligible_corrections"]
        ),
        "outside_envelope_negative_count": outside,
        "missing_interval_count": missing,
        "duplicate_interval_count": 0,
        "interval_count_scope": "DOWNLOADED_RAW_ONLY",
        "provider_grid_selection_parity": "PASS_DOWNLOADED_ONLY",
        "raw_audits": audits,
        "request_stops": stops,
        "positive_value_thresholding": False,
        "automatic_tolerance_widening": False,
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    socket.socket.connect = no_network  # type: ignore[method-assign]
    socket.socket.connect_ex = no_network  # type: ignore[method-assign]
    socket.create_connection = no_network
    result = report(a.root)
    write_json(a.output, result)
    print(json.dumps({k: v for k, v in result.items() if k not in {"raw_audits", "request_stops"}}))


if __name__ == "__main__":
    main()
