"""Build the server-owned S6 authority from already approved private inputs.

This command writes only to an operator-selected private artifact directory. It
does not copy business authority into the repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from backend.app.area_yield.data import digest
from backend.app.forecast_quality.operational_peak import BASELINE_ID, POLICY_VERSION
from backend.app.forecast_quality.operational_peak_authority import (
    AUTHORITY_VERSION,
    REFERENCE_PROFILE_FILE_SHA256,
    REFERENCE_PROFILE_FOLD,
    REGISTRY_FILE_SHA256,
    REGISTRY_PAYLOAD_HASH,
)


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def build(registry_path: Path, profile_path: Path) -> dict[str, Any]:
    registry = _read_object(registry_path)
    profile = _read_object(profile_path)
    if registry.get("hash") != REGISTRY_PAYLOAD_HASH:
        raise ValueError("registry payload hash is not the approved S1 hash")
    payload: dict[str, Any] = {
        "authority_version": AUTHORITY_VERSION,
        "policy_version": POLICY_VERSION,
        "baseline_id": BASELINE_ID,
        "base_registry_payload_hash": REGISTRY_PAYLOAD_HASH,
        "base_registry_file_sha256": REGISTRY_FILE_SHA256,
        "base_registry_payload": registry,
        "bases": registry["bases"],
        "reference_profile_fold": REFERENCE_PROFILE_FOLD,
        "reference_profile_file_sha256": REFERENCE_PROFILE_FILE_SHA256,
        "reference_profile_payload": profile,
        "weather_used": False,
    }
    payload["authority_hash"] = digest(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build(args.registry, args.profile)
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(raw)
    print(
        json.dumps(
            {
                "authority_hash": payload["authority_hash"],
                "file_sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
