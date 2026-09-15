"""Run the frozen S5 operational peak-window policy.

The runner accepts explicit, already-authorized registry and reference-profile
files.  It does not train or fit anything, and it never reads weather or
historical target labels.  Outputs are intended for local evidence/replay;
the input files remain outside Git when they are private authority artifacts.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from backend.app.forecast_quality.operational_peak import (
    OperationalPeakForecastRequest,
    forecast_operational_peak,
    load_frozen_reference_profile,
)

BOUNDARY_ORIGINS = {
    "2027-04-08": date(2027, 4, 8),
    "2027-04-10": date(2027, 4, 10),
    "2027-03-31": date(2027, 3, 31),
    "2027-04-01": date(2027, 4, 1),
}


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def run(registry_path: Path, profile_path: Path, base_id: str, origin: date) -> dict[str, Any]:
    registry = _read_json(registry_path)
    profile = load_frozen_reference_profile(_read_json(profile_path))
    request = OperationalPeakForecastRequest(base_id, "2026-2027", origin)
    result = forecast_operational_peak(request, registry, profile)
    boundary: dict[str, dict[str, Any]] = {}
    for label, boundary_origin in BOUNDARY_ORIGINS.items():
        boundary_result = forecast_operational_peak(
            OperationalPeakForecastRequest(base_id, "2026-2027", boundary_origin),
            registry,
            profile,
        )
        boundary[label] = {
            "w7_status": boundary_result.forecast_7d.status,
            "w15_status": boundary_result.forecast_15d.status,
            "remaining_status": boundary_result.remaining_business_window.status,
        }
    first_replay = forecast_operational_peak(request, registry, profile)
    second_replay = forecast_operational_peak(request, registry, profile)
    return {
        "task_id": "V0_5_S5_OPERATIONAL_7D_15D_PEAK_FORECAST_R1",
        "policy_version": result.policy_version,
        "selected_baseline_id": result.baseline_id,
        "weather_used": result.weather_used,
        "result": result.to_mapping(),
        "boundary_examples": boundary,
        "deterministic_replay": first_replay.to_mapping() == second_replay.to_mapping(),
        "result_hash_replay": first_replay.result_hash == second_replay.result_hash,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--reference-profile", type=Path, required=True)
    parser.add_argument("--base-id", required=True)
    parser.add_argument("--origin-date", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = run(args.registry, args.reference_profile, args.base_id, args.origin_date)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
