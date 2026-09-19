"""Canonical payload and PIT input-snapshot hashing helpers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from hashlib import sha256
from typing import Any, cast

PIT_CANONICAL_HASH_POLICY = "V0_6_PIT_CANONICAL_JSON_V1"


def hash_payload(payload: object) -> str:
    """Return the repository's canonical SHA-256 for a JSON-compatible payload."""

    # Import lazily because the existing canonical module is imported while
    # the ORM model registry is being assembled.  Keeping this boundary lazy
    # preserves reuse of the repository canonicalizer without introducing a
    # models -> PIT -> rolling_backtest import cycle.
    from backend.app.rolling_backtest.canonical import sha256_payload

    return sha256_payload(payload)


def hash_raw_payload(raw_payload: str | bytes) -> str:
    """Hash provider/source bytes without normalizing or rewriting them."""

    raw = raw_payload.encode("utf-8") if isinstance(raw_payload, str) else raw_payload
    return sha256(raw).hexdigest()


def build_input_snapshot(
    *,
    request: Mapping[str, Any],
    base_identity: Mapping[str, Any],
    target_season: str,
    target_area: Mapping[str, Any],
    area_revision_id: str,
    prior_history: Mapping[str, Any],
    weather_snapshot_ids: Iterable[str],
    phenology_observation_ids: Iterable[str],
    model: Mapping[str, Any],
    forecast_mode: str,
    coverage: Mapping[str, Any],
    forecast_created_at: datetime | None = None,
    warnings: Iterable[str] = (),
) -> tuple[dict[str, Any], str]:
    """Build the complete, deterministic PIT input identity.

    The function intentionally keeps source identities and coverage metadata
    in the hashed payload.  A caller cannot change a source version, selected
    revision, or coverage warning without changing the resulting hash.
    """

    from backend.app.rolling_backtest.canonical import canonical_json_value

    snapshot: dict[str, Any] = {
        "schema_version": "V0_6_FORECAST_INPUT_SNAPSHOT_V1",
        "canonicalization_policy": PIT_CANONICAL_HASH_POLICY,
        "request": dict(request),
        "base_identity": dict(base_identity),
        "target_season": target_season,
        "target_area": dict(target_area),
        "area_revision_id": area_revision_id,
        "prior_history": dict(prior_history),
        "weather_snapshot_ids": sorted(weather_snapshot_ids),
        "phenology_observation_ids": sorted(phenology_observation_ids),
        "model": dict(model),
        "forecast_mode": forecast_mode,
        "coverage": dict(coverage),
        "warnings": sorted(set(warnings)),
    }
    if forecast_created_at is not None:
        snapshot["forecast_created_at"] = forecast_created_at
    canonical_snapshot = cast(dict[str, Any], canonical_json_value(snapshot))
    return canonical_snapshot, hash_payload(canonical_snapshot)


def canonical_payload_text(payload: object) -> str:
    """Expose the exact JSON bytes used by the shared canonical hash helper."""

    from backend.app.rolling_backtest.canonical import canonical_json_dumps

    return canonical_json_dumps(payload)
