from __future__ import annotations

import re
from typing import Any, cast

from backend.app.harvest_state.canonical import canonical_json_value, make_source_ref_hash
from backend.app.harvest_state.enums import BlockerCode
from backend.app.harvest_state.schemas import SourceRef, SourceRefCatalogEntry

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def source_ref_payload(source_ref: SourceRef) -> dict[str, Any]:
    payload = source_ref.model_dump(mode="python")
    # Legacy/non-replay Task 9 requests may not carry the newly introduced
    # exact Task 8 availability evidence.  Do not change their historical
    # source-ref hashes; when populated, the persisted timestamp remains in
    # the canonical payload and therefore in the hash.
    if payload.get("source_ref_type") == "TASK8_DAILY_PREDICTION":
        availability = payload.get("maturity_daily_prediction_available_at")
        if availability is None:
            payload.pop("maturity_daily_prediction_available_at", None)
        else:
            # Keep the nested catalog payload in the same canonical JSON form
            # used by persistence.  Otherwise mode="json" stores this
            # datetime as a ``Z`` string while the in-memory result hash sees
            # ``+00:00``, making a persisted Task 9 run fail on reload.
            payload["maturity_daily_prediction_available_at"] = canonical_json_value(availability)
    # Persisted source-ref catalog payloads are JSON documents.  Normalize the
    # complete payload before hashing and storing it so Decimal scale and enum
    # representation cannot diverge between in-memory output and JSON reload.
    return cast(dict[str, Any], canonical_json_value(payload))


def source_ref_hash(source_ref: SourceRef) -> str:
    return make_source_ref_hash(source_ref_payload(source_ref))


def build_source_ref_catalog(
    source_refs: list[SourceRef],
    referenced_hashes: set[str] | None = None,
) -> tuple[list[SourceRefCatalogEntry], list[str]]:
    blockers: list[str] = []
    entries_by_hash: dict[str, SourceRefCatalogEntry] = {}
    payload_by_hash: dict[str, dict[str, Any]] = {}
    for source_ref in source_refs:
        payload = source_ref_payload(source_ref)
        ref_hash = make_source_ref_hash(payload)
        if not _SHA256_RE.fullmatch(ref_hash):
            blockers.append(f"{BlockerCode.SOURCE_REF_HASH_MISMATCH}:{ref_hash}")
            continue
        existing = payload_by_hash.get(ref_hash)
        if existing is not None and canonical_json_value(existing) != canonical_json_value(payload):
            blockers.append(f"{BlockerCode.SOURCE_REF_HASH_COLLISION}:{ref_hash}")
            continue
        payload_by_hash[ref_hash] = payload
        entries_by_hash[ref_hash] = SourceRefCatalogEntry(
            source_ref_hash=ref_hash,
            source_ref_type=source_ref.source_ref_type,
            source_ref_schema_version=source_ref.source_ref_schema_version,
            source_ref_payload=payload,
        )
    if referenced_hashes is not None:
        for ref_hash in sorted(referenced_hashes):
            if not _SHA256_RE.fullmatch(ref_hash):
                blockers.append(f"{BlockerCode.SOURCE_REF_HASH_MISMATCH}:{ref_hash}")
            elif ref_hash not in entries_by_hash:
                blockers.append(f"{BlockerCode.UNRESOLVED_SOURCE_REF}:{ref_hash}")
        for ref_hash in sorted(entries_by_hash):
            if ref_hash not in referenced_hashes:
                blockers.append(f"{BlockerCode.ORPHAN_SOURCE_REF}:{ref_hash}")
    return [entries_by_hash[key] for key in sorted(entries_by_hash)], sorted(blockers)
