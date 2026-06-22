from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import Any


def _canonical_json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        return [_canonical_json(item) for item in value]
    if isinstance(value, tuple):
        return [_canonical_json(item) for item in value]
    if isinstance(value, dict):
        return {key: _canonical_json(value[key]) for key in sorted(value)}
    return value


def _stable_json(value: Any) -> str:
    return json.dumps(
        _canonical_json(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def input_hash(payload: dict[str, Any], *, as_of_date: date) -> str:
    normalized = dict(payload)
    normalized["as_of_date"] = as_of_date
    return hashlib.sha256(_stable_json(normalized).encode("utf-8")).hexdigest()


def source_signature(
    *,
    input_hash_value: str,
    resolver_version: str,
    library_version: str,
    config_hash: str,
    eligible_observation_ids: list[int],
    selected_location_version: str,
) -> str:
    payload = {
        "input_hash": input_hash_value,
        "resolver_version": resolver_version,
        "library_version": library_version,
        "config_hash": config_hash,
        "eligible_observation_ids": sorted(eligible_observation_ids),
        "selected_location_version": selected_location_version,
    }
    return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()
