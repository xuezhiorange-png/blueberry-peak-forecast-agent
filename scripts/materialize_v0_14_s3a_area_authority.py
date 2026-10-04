"""Owner-authorized area authority only; no weather, model or actual inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from backend.app.pit.canonical import hash_payload
from backend.app.pit.schemas import AreaRevisionInput

BASE_ID = "base_a96b297b126a8cab67c4755f"
BASE_NAME = "保山杨柳基地"
BASE_SHA = "3110f5bca30fe596e63c30a70dd20d19fbe76c2d"
SOURCE_PINS = {
    "docs/v0-5/evidence/area-forecast-productization-r10.json": (
        "d815721fe98fe0b85248a4315a1b4f13483ad6f5456093b040ee6fb69561f564"
    ),
    "configs/v0_5_area_forecast_experimental_prior_history_v1.json": (
        "8603026734d6ead0069e4bf560f8fd66175ab5144b8211150311d4920548dbad"
    ),
    "configs/v0_5_base_reference_registry_v1.json": (
        "0d382e644b271df4d9b8e7f31f8e4148816135faf70aa1e21a97ee2eb6374b85"
    ),
}


def revision_input() -> dict[str, Any]:
    return {
        "area_revision_id": "v014-s3a-yangliu-2026-2027-reference-r1",
        "base_id": BASE_ID,
        "season": "2026-2027",
        "area_mu": "394.000000",
        "area_type": "REFERENCE_AREA",
        "effective_from": "2026-07-01T00:00:00+08:00",
        "effective_to": None,
        "recorded_at": "2026-10-04T22:32:00+08:00",
        "known_at": "2026-10-04T22:32:00+08:00",
        "source": "COORDINATOR_EXPLICIT_BUSINESS_CONFIRMATION",
        "source_reference": "V0_14_S3A_OWNER_CONFIRMATION_2026-10-04T22:32:00+08:00",
        "basis": (
            "2026-2027 provisional forecast reference area explicitly confirmed "
            "equal to frozen 2025-2026 Yangliu area"
        ),
        "supersedes_revision_id": None,
    }


def build_revision(raw: dict[str, Any]) -> AreaRevisionInput:
    item = AreaRevisionInput.model_validate(raw)
    expected = AreaRevisionInput.model_validate(revision_input())
    if item.payload() != expected.payload():
        raise ValueError("OWNER_AUTHORITY_CONTRACT_MISMATCH")
    digest = item.computed_payload_hash()
    if item.payload_hash is not None and item.payload_hash != digest:
        raise ValueError("INVALID_PAYLOAD_HASH")
    return AreaRevisionInput.model_validate({**item.model_dump(), "payload_hash": digest})


def verify_public_sources(root: Path) -> dict[str, str]:
    sources = {}
    for name, expected in SOURCE_PINS.items():
        raw = (root / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("PUBLIC_SOURCE_DRIFT")
        sources[name] = json.loads(raw)
    product = sources[next(iter(SOURCE_PINS))]["real_forecast"]
    if (
        product["base_id"],
        product["base_name"],
        product["target_season"],
        product["target_area_mu"],
    ) != (BASE_ID, BASE_NAME, "2025-2026", "394.000000"):
        raise ValueError("PUBLIC_AREA_FACT_MISMATCH")
    history = sources["configs/v0_5_area_forecast_experimental_prior_history_v1.json"]
    matches = [b for b in history["bases"] if b["base_id"] == BASE_ID]
    if len(matches) != 1 or (
        matches[0]["base_name"],
        matches[0]["season"],
        matches[0]["reference_area_mu"],
    ) != (BASE_NAME, "2025-2026", "394.000000"):
        raise ValueError("PUBLIC_AREA_FACT_MISMATCH")
    registry = sources["configs/v0_5_base_reference_registry_v1.json"]
    matches = [b for b in registry["bases"] if b["base_id"] == BASE_ID]
    if len(matches) != 1 or (
        matches[0]["canonical_base_name"],
        matches[0]["productive_area_mu"],
    ) != (BASE_NAME, "394.000000"):
        raise ValueError("PUBLIC_BASE_IDENTITY_MISMATCH")
    return dict(SOURCE_PINS)


def check_existing(existing: list[AreaRevisionInput], expected: AreaRevisionInput) -> str:
    superseded = {r.supersedes_revision_id for r in existing if r.supersedes_revision_id}
    terminal = [
        r
        for r in existing
        if r.area_revision_id not in superseded
        and (r.base_id, r.season, r.area_type) == (BASE_ID, "2026-2027", "REFERENCE_AREA")
    ]
    for r in terminal:
        if r.payload() != expected.payload() or r.payload_hash != expected.payload_hash:
            raise ValueError("CONFLICTING_EXISTING_2026_2027_AREA_REVISION")
    return "REUSE_EXISTING_IDENTICAL_AUTHORITY" if terminal else "CREATE_FIRST_VERIFIED_AUTHORITY"


def immutable_write(path: Path, raw: bytes) -> None:
    if path.is_symlink():
        raise ValueError("AUTHORITY_CONFLICT")
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError("AUTHORITY_CONFLICT")
        return
    with path.open("xb") as stream:
        stream.write(raw)


def execution_gate(operation: str) -> None:
    if operation != "area_authority_materialization":
        raise ValueError("EXECUTION_FORBIDDEN")


def manifest_for(revision: AreaRevisionInput, raw: bytes, pins: dict[str, str]) -> dict[str, Any]:
    body = {
        "schema": "V0_14_CURRENT_SEASON_SCOPE_AUTHORITY_MANIFEST_V1",
        "area_revision_id": revision.area_revision_id,
        "payload_hash": revision.payload_hash,
        "base_id": revision.base_id,
        "season": revision.season,
        "area_type": revision.area_type,
        "source_public_fact_hashes": pins,
        "owner_confirmation_reference": revision.source_reference,
        "artifact_sha256": hashlib.sha256(raw).hexdigest(),
        "artifact_size": len(raw),
    }
    return {**body, "manifest_hash": hash_payload(body)}


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def materialize(root: Path, authority_root: Path, output: Path) -> dict[str, Any]:
    execution_gate("area_authority_materialization")
    pins = verify_public_sources(root)
    revision = build_revision(revision_input())
    existing = []
    # Only explicitly named area authority files: never inventory actual artifacts.
    for path in sorted(authority_root.rglob("area-revision.json")):
        if path.is_symlink():
            raise ValueError("AUTHORITY_CONFLICT")
        r = AreaRevisionInput.model_validate_json(path.read_bytes())
        if r.payload_hash != r.computed_payload_hash():
            raise ValueError("INVALID_EXISTING_PAYLOAD_HASH")
        existing.append(r)
    state = check_existing(existing, revision)
    raw = json_bytes(revision.model_dump(mode="json"))
    manifest = manifest_for(revision, raw, pins)
    # Check both outputs before any creation, preserving conflicting files.
    for name, data in [
        ("area-revision.json", raw),
        ("authority-manifest.json", json_bytes(manifest)),
    ]:
        path = output / name
        if path.is_symlink() or (path.exists() and path.read_bytes() != data):
            raise ValueError("AUTHORITY_CONFLICT")
    output.mkdir(parents=True, exist_ok=True)
    immutable_write(output / "area-revision.json", raw)
    immutable_write(output / "authority-manifest.json", json_bytes(manifest))
    return {"status": state, "manifest": manifest, "revision": revision.model_dump(mode="json")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authority-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = materialize(Path(__file__).resolve().parents[1], args.authority_root, args.output)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
