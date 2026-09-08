"""Canonical serialization and hash helpers for the S4 event ledger."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, cast

from backend.app.rolling_backtest.canonical import canonical_json_dumps, sha256_payload

GENESIS_EVENT_HASH = "0" * 64


def canonical_event_body(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return the repository-canonical JSON object stored in ``event_payload``."""

    # Round-tripping through the existing canonical serializer rejects native
    # floats and normalizes datetimes/Decimals exactly as the rest of the
    # repository does.  The DB payload is therefore the same object used by
    # the hash function, never a reconstruction from typed projections.
    return cast(dict[str, Any], json.loads(canonical_json_dumps(dict(payload))))


def validation_event_hash(
    *,
    event_type: str,
    event_payload: Mapping[str, Any],
    previous_event_hash: str,
) -> str:
    """Hash the frozen event preimage using the stored canonical body."""

    return sha256_payload(
        {
            "event_type": event_type,
            "canonical_event_body": canonical_event_body(event_payload),
            "previous_event_hash": previous_event_hash,
        }
    )


__all__ = [
    "GENESIS_EVENT_HASH",
    "canonical_event_body",
    "validation_event_hash",
]
