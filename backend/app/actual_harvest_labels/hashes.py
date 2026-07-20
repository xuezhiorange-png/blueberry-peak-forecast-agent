"""I7 label-snapshot hash helpers.

All hashes use SHA-256 lowercase hex over canonical JSON. The canonical
JSON serializer is shared with the rolling-backtest module and the I5
validation pipeline (contract §14: canonical JSON excludes
database-generated IDs, runtime hosts, processes, query order, temporary
paths, and nondeterministic iteration).

Frozen contract:
- docs/forecast-quality/q2a-i7-label-snapshot-and-revision-winner-contract.md §13-§14
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from typing import Any

from backend.app.rolling_backtest.canonical import canonical_json_dumps

SNAPSHOT_POLICY_VERSION = "actual-harvest-label-snapshot-policy-v1"
WINNER_POLICY_VERSION = "actual-harvest-label-winner-policy-v1"
AGGREGATION_POLICY_VERSION = "actual-harvest-label-aggregation-policy-v1"
REQUEST_HASH_POLICY_VERSION = "actual-harvest-label-request-hash-v1"
INSTANCE_HASH_POLICY_VERSION = "actual-harvest-label-instance-hash-v1"
SNAPSHOT_HASH_POLICY_VERSION = "actual-harvest-label-snapshot-hash-v1"


def _digest(payload: Mapping[str, Any]) -> str:
    return sha256(canonical_json_dumps(dict(payload)).encode("utf-8")).hexdigest()


def _datetime_to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def compute_snapshot_request_identity_hash(
    *,
    snapshot_idempotency_key: str,
    source_system: str,
    visibility_mode: str,
    label_observation_cutoff_at_or_null: datetime | None,
    harvest_date_start: Any,
    harvest_date_end: Any,
    season_business_keys: Iterable[str],
    farm_business_keys_or_empty_for_all: Iterable[str],
    variety_business_keys_or_empty_for_all: Iterable[str],
    snapshot_policy_version: str,
    winner_policy_version: str,
    aggregation_policy_version: str,
) -> str:
    """Bind the canonical request and policy versions (contract §14.1)."""

    return _digest(
        {
            "policy_version": REQUEST_HASH_POLICY_VERSION,
            "snapshot_idempotency_key": snapshot_idempotency_key,
            "source_system": source_system,
            "visibility_mode": visibility_mode,
            "label_observation_cutoff_at_or_null": _datetime_to_iso(
                label_observation_cutoff_at_or_null
            ),
            "harvest_date_start": str(harvest_date_start),
            "harvest_date_end": str(harvest_date_end),
            "season_business_keys": tuple(season_business_keys),
            "farm_business_keys_or_empty_for_all": tuple(farm_business_keys_or_empty_for_all),
            "variety_business_keys_or_empty_for_all": tuple(variety_business_keys_or_empty_for_all),
            "snapshot_policy_version": snapshot_policy_version,
            "winner_policy_version": winner_policy_version,
            "aggregation_policy_version": aggregation_policy_version,
        }
    )


def compute_source_commit_manifest_set_hash(
    manifests: Iterable[Mapping[str, Any]],
) -> str:
    """Bind the canonically ordered source manifest set (contract §14.2)."""

    ordered = sorted(
        manifests,
        key=lambda item: (
            item.get("source_system", ""),
            item.get("external_batch_id", ""),
            item.get("commit_manifest_hash", ""),
        ),
    )
    return _digest(
        {
            "policy_version": SNAPSHOT_POLICY_VERSION,
            "manifests": [
                {
                    "source_system": item.get("source_system", ""),
                    "external_batch_id": item.get("external_batch_id", ""),
                    "commit_manifest_hash": item.get("commit_manifest_hash", ""),
                    "validation_run_instance_identity_hash": item.get(
                        "validation_run_instance_identity_hash", ""
                    ),
                }
                for item in ordered
            ],
        }
    )


def compute_winner_manifest_hash(winners: Iterable[Mapping[str, Any]]) -> str:
    """Bind the canonically ordered winner row hashes (contract §12/§14)."""

    ordered = sorted(
        winners,
        key=lambda item: (
            item.get("source_system", ""),
            item.get("external_logical_record_id", ""),
            item.get("external_revision_id", ""),
        ),
    )
    return _digest(
        {
            "policy_version": WINNER_POLICY_VERSION,
            "winner_row_hashes": tuple(item.get("winner_row_hash", "") for item in ordered),
        }
    )


def compute_label_row_set_hash(label_rows: Iterable[Mapping[str, Any]]) -> str:
    """Bind the canonically ordered canonical-grain label rows."""

    ordered = sorted(
        label_rows,
        key=lambda item: (
            item.get("season_business_key", ""),
            item.get("farm_business_key", ""),
            item.get("subfarm_business_key", ""),
            item.get("variety_business_key", ""),
            str(item.get("harvest_business_date", "")),
            item.get("label_row_hash", ""),
        ),
    )
    return _digest(
        {
            "policy_version": AGGREGATION_POLICY_VERSION,
            "label_rows": [
                {
                    "label_row_hash": item.get("label_row_hash", ""),
                    "exact_decimal_quantity_sum_kg": str(
                        item.get("exact_decimal_quantity_sum_kg", "0")
                    ),
                    "contributing_winner_count": item.get("contributing_winner_count", 0),
                }
                for item in ordered
            ],
        }
    )


def compute_exclusion_manifest_hash(exclusions: Iterable[Mapping[str, Any]]) -> str:
    """Bind the canonically ordered exclusion row hashes (contract §16)."""

    ordered = sorted(
        exclusions,
        key=lambda item: (
            item.get("exclusion_category", ""),
            item.get("source_system", ""),
            item.get("external_logical_record_id_or_null") or "",
            item.get("external_revision_id_or_null") or "",
            str(item.get("harvest_business_date_or_null") or ""),
        ),
    )
    return _digest(
        {
            "policy_version": SNAPSHOT_POLICY_VERSION,
            "exclusion_row_hashes": tuple(item.get("exclusion_row_hash", "") for item in ordered),
        }
    )


def compute_snapshot_instance_identity_hash(
    *,
    request_identity_hash: str,
    source_commit_manifest_set_hash: str,
) -> str:
    """Bind instance identity (contract §14.3).

    The contract binds the request identity and the source-universe
    hash. The ``snapshot_executed_at`` wall-clock timestamp is
    persisted on the snapshot row for auditability, but it is
    intentionally NOT bound into the hash so that the same request
    and the same source universe reproduce the same hash
    regardless of when the snapshot is taken (contract §18).
    """

    return _digest(
        {
            "policy_version": INSTANCE_HASH_POLICY_VERSION,
            "request_identity_hash": request_identity_hash,
            "source_commit_manifest_set_hash": source_commit_manifest_set_hash,
        }
    )


def compute_label_snapshot_hash(
    *,
    instance_identity_hash: str,
    winner_manifest_hash: str,
    label_row_set_hash: str,
    exclusion_manifest_hash: str,
    winner_count: int,
    label_row_count: int,
    exclusion_row_count: int,
    snapshot_policy_version: str,
    winner_policy_version: str,
    aggregation_policy_version: str,
) -> str:
    """Bind the canonical final snapshot hash (contract §14.4)."""

    return _digest(
        {
            "policy_version": SNAPSHOT_HASH_POLICY_VERSION,
            "instance_identity_hash": instance_identity_hash,
            "winner_manifest_hash": winner_manifest_hash,
            "label_row_set_hash": label_row_set_hash,
            "exclusion_manifest_hash": exclusion_manifest_hash,
            "winner_count": winner_count,
            "label_row_count": label_row_count,
            "exclusion_row_count": exclusion_row_count,
            "snapshot_policy_version": snapshot_policy_version,
            "winner_policy_version": winner_policy_version,
            "aggregation_policy_version": aggregation_policy_version,
        }
    )


def compute_winner_row_hash(
    *,
    source_system: str,
    external_logical_record_id: str,
    external_revision_id: str,
    revision_number: int,
    canonical_record_hash: str,
    record_status: str,
    effective_status: str,
    finalized_at_or_null: datetime | None,
    source_recorded_at_or_null: datetime | None,
    source_recorded_at_authority_status: str,
    harvest_business_date: Any,
    actual_harvest_quantity_kg: Decimal,
    commit_manifest_hash: str,
    season_business_key: str,
    farm_business_key: str,
    subfarm_business_key: str,
    variety_business_key: str,
    mapping_registry_version: str,
    mapping_policy_version: str,
    season_resolver_version: str,
    mapping_registry_entry_hash: str | None,
    resolved_master_business_key: str,
    resolved_master_parent_business_key: str | None,
    resolved_master_record_hash: str,
    mapping_snapshot_hash: str,
    resolved_identity_snapshot_hash: str,
    registry_content_hash: str,
) -> str:
    """Bind a single winner row's canonical hash.

    The hash deliberately excludes the database PK so the same logical
    winner reproduces the same row hash across replay and re-snapshot
    (contract §11 + §18).
    """

    return _digest(
        {
            "policy_version": WINNER_POLICY_VERSION,
            "winner": {
                "source_system": source_system,
                "external_logical_record_id": external_logical_record_id,
                "external_revision_id": external_revision_id,
                "revision_number": revision_number,
                "canonical_record_hash": canonical_record_hash,
                "record_status": record_status,
                "effective_status": effective_status,
                "finalized_at_or_null": _datetime_to_iso(finalized_at_or_null),
                "source_recorded_at_or_null": _datetime_to_iso(source_recorded_at_or_null),
                "source_recorded_at_authority_status": source_recorded_at_authority_status,
                "harvest_business_date": str(harvest_business_date),
                "actual_harvest_quantity_kg": str(actual_harvest_quantity_kg),
                "commit_manifest_hash": commit_manifest_hash,
                "season_business_key": season_business_key,
                "farm_business_key": farm_business_key,
                "subfarm_business_key": subfarm_business_key,
                "variety_business_key": variety_business_key,
                "mapping_registry_version": mapping_registry_version,
                "mapping_policy_version": mapping_policy_version,
                "season_resolver_version": season_resolver_version,
                "mapping_registry_entry_hash": mapping_registry_entry_hash,
                "resolved_master_business_key": resolved_master_business_key,
                "resolved_master_parent_business_key": resolved_master_parent_business_key,
                "resolved_master_record_hash": resolved_master_record_hash,
                "mapping_snapshot_hash": mapping_snapshot_hash,
                "resolved_identity_snapshot_hash": resolved_identity_snapshot_hash,
                "registry_content_hash": registry_content_hash,
            },
        }
    )


def compute_label_row_hash(
    *,
    season_business_key: str,
    farm_business_key: str,
    subfarm_business_key: str,
    variety_business_key: str,
    harvest_business_date: Any,
    exact_decimal_quantity_sum_kg: Decimal,
    contributing_winner_hashes: Iterable[str],
) -> str:
    """Bind a canonical-grain label row's canonical hash."""

    return _digest(
        {
            "policy_version": AGGREGATION_POLICY_VERSION,
            "label_row": {
                "season_business_key": season_business_key,
                "farm_business_key": farm_business_key,
                "subfarm_business_key": subfarm_business_key,
                "variety_business_key": variety_business_key,
                "harvest_business_date": str(harvest_business_date),
                "exact_decimal_quantity_sum_kg": str(exact_decimal_quantity_sum_kg),
                "contributing_winner_hashes": tuple(contributing_winner_hashes),
            },
        }
    )


def compute_exclusion_row_hash(
    *,
    exclusion_category: str,
    source_system: str,
    external_logical_record_id_or_null: str | None,
    external_revision_id_or_null: str | None,
    harvest_business_date_or_null: Any,
    exclusion_details: Mapping[str, Any],
) -> str:
    """Bind a coverage-exclusion row's canonical hash."""

    return _digest(
        {
            "policy_version": SNAPSHOT_POLICY_VERSION,
            "exclusion": {
                "category": exclusion_category,
                "source_system": source_system,
                "external_logical_record_id_or_null": external_logical_record_id_or_null,
                "external_revision_id_or_null": external_revision_id_or_null,
                "harvest_business_date_or_null": (
                    None
                    if harvest_business_date_or_null is None
                    else str(harvest_business_date_or_null)
                ),
                "details": dict(exclusion_details),
            },
        }
    )


__all__ = [
    "AGGREGATION_POLICY_VERSION",
    "INSTANCE_HASH_POLICY_VERSION",
    "REQUEST_HASH_POLICY_VERSION",
    "SNAPSHOT_HASH_POLICY_VERSION",
    "SNAPSHOT_POLICY_VERSION",
    "WINNER_POLICY_VERSION",
    "compute_exclusion_manifest_hash",
    "compute_exclusion_row_hash",
    "compute_label_row_hash",
    "compute_label_row_set_hash",
    "compute_label_snapshot_hash",
    "compute_snapshot_instance_identity_hash",
    "compute_snapshot_request_identity_hash",
    "compute_source_commit_manifest_set_hash",
    "compute_winner_manifest_hash",
    "compute_winner_row_hash",
]
