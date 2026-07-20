"""I7 label-snapshot persistence helpers.

Pure helpers that translate ORM rows into the value objects in
``schemas.py``. They do NOT call ``session.commit()`` or
``session.rollback()`` — transaction ownership stays with the caller
(contract §17: SINGLE_TRANSACTION_CREATION + CALLER_OWNED_TRANSACTION).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.actual_harvest_labels.hashes import (
    compute_exclusion_row_hash,
    compute_label_row_hash,
    compute_winner_row_hash,
)
from backend.app.actual_harvest_labels.models import (
    ActualHarvestLabelSnapshotExclusionModel,
    ActualHarvestLabelSnapshotLabelModel,
    ActualHarvestLabelSnapshotModel,
    ActualHarvestLabelSnapshotWinnerModel,
)
from backend.app.actual_harvest_labels.schemas import (
    ActualHarvestExclusionRow,
    ActualHarvestLabelRow,
    ActualHarvestLabelSnapshotHeader,
    ActualHarvestWinnerRow,
)


def header_to_value_object(
    snapshot: ActualHarvestLabelSnapshotModel,
) -> ActualHarvestLabelSnapshotHeader:
    return ActualHarvestLabelSnapshotHeader(
        snapshot_id=snapshot.id,
        snapshot_idempotency_key=snapshot.snapshot_idempotency_key,
        source_system=snapshot.source_system,
        visibility_mode=snapshot.visibility_mode,
        label_observation_cutoff_at_or_null=snapshot.label_observation_cutoff_at_or_null,
        harvest_date_start=snapshot.harvest_date_start,
        harvest_date_end=snapshot.harvest_date_end,
        snapshot_policy_version=snapshot.snapshot_policy_version,
        winner_policy_version=snapshot.winner_policy_version,
        aggregation_policy_version=snapshot.aggregation_policy_version,
        snapshot_executed_at=snapshot.snapshot_executed_at,
        snapshot_request_identity_hash=snapshot.snapshot_request_identity_hash,
        snapshot_instance_identity_hash=snapshot.snapshot_instance_identity_hash,
        source_commit_manifest_set_hash=snapshot.source_commit_manifest_set_hash,
        winner_manifest_hash=snapshot.winner_manifest_hash,
        label_row_set_hash=snapshot.label_row_set_hash,
        exclusion_manifest_hash=snapshot.exclusion_manifest_hash,
        label_snapshot_hash=snapshot.label_snapshot_hash,
        source_manifest_count=snapshot.source_manifest_count,
        winner_count=snapshot.winner_count,
        label_row_count=snapshot.label_row_count,
        exclusion_row_count=snapshot.exclusion_row_count,
        created_by_identity=snapshot.created_by_identity,
    )


def winner_to_value_object(
    winner: ActualHarvestLabelSnapshotWinnerModel,
) -> ActualHarvestWinnerRow:
    return ActualHarvestWinnerRow(
        source_system=winner.source_system,
        external_logical_record_id=winner.external_logical_record_id,
        external_revision_id=winner.external_revision_id,
        revision_number=winner.revision_number,
        canonical_record_hash=winner.canonical_record_hash,
        record_status=winner.record_status,
        effective_status=winner.effective_status,
        finalized_at_or_null=winner.finalized_at_or_null,
        source_recorded_at_or_null=winner.source_recorded_at_or_null,
        source_recorded_at_authority_status=winner.source_recorded_at_authority_status,
        harvest_business_date=winner.harvest_business_date,
        actual_harvest_quantity_kg=winner.actual_harvest_quantity_kg,
        commit_manifest_hash=winner.commit_manifest_hash,
        season_business_key=winner.season_business_key,
        farm_business_key=winner.farm_business_key,
        subfarm_business_key=winner.subfarm_business_key,
        variety_business_key=winner.variety_business_key,
        mapping_registry_version=winner.mapping_registry_version,
        mapping_policy_version=winner.mapping_policy_version,
        season_resolver_version=winner.season_resolver_version,
        mapping_registry_entry_hash=winner.mapping_registry_entry_hash,
        resolved_master_business_key=winner.resolved_master_business_key,
        resolved_master_parent_business_key=winner.resolved_master_parent_business_key,
        resolved_master_record_hash=winner.resolved_master_record_hash,
        mapping_snapshot_hash=winner.mapping_snapshot_hash,
        resolved_identity_snapshot_hash=winner.resolved_identity_snapshot_hash,
        registry_content_hash=winner.registry_content_hash,
        winner_row_hash=winner.winner_row_hash,
    )


def label_row_to_value_object(
    row: ActualHarvestLabelSnapshotLabelModel,
) -> ActualHarvestLabelRow:
    return ActualHarvestLabelRow(
        season_business_key=row.season_business_key,
        farm_business_key=row.farm_business_key,
        subfarm_business_key=row.subfarm_business_key,
        variety_business_key=row.variety_business_key,
        harvest_business_date=row.harvest_business_date,
        exact_decimal_quantity_sum_kg=row.exact_decimal_quantity_sum_kg,
        contributing_winner_count=row.contributing_winner_count,
        contributing_winner_hashes=tuple(_decode_hash_list(row.contributing_winner_hashes)),
        label_row_hash=row.label_row_hash,
    )


def exclusion_row_to_value_object(
    row: ActualHarvestLabelSnapshotExclusionModel,
) -> ActualHarvestExclusionRow:
    return ActualHarvestExclusionRow(
        exclusion_category=row.exclusion_category,
        source_system=row.source_system,
        external_logical_record_id_or_null=row.external_logical_record_id_or_null,
        external_revision_id_or_null=row.external_revision_id_or_null,
        harvest_business_date_or_null=row.harvest_business_date_or_null,
        exclusion_row_hash=row.exclusion_row_hash,
        exclusion_details=_decode_json(row.exclusion_details),
    )


def winner_row_hash_for(winner_payload: dict[str, Any]) -> str:
    return compute_winner_row_hash(
        source_system=str(winner_payload["source_system"]),
        external_logical_record_id=str(winner_payload["external_logical_record_id"]),
        external_revision_id=str(winner_payload["external_revision_id"]),
        revision_number=int(winner_payload["revision_number"]),
        canonical_record_hash=str(winner_payload["canonical_record_hash"]),
        record_status=str(winner_payload["record_status"]),
        effective_status=str(winner_payload["effective_status"]),
        finalized_at_or_null=winner_payload.get("finalized_at_or_null"),
        source_recorded_at_or_null=winner_payload.get("source_recorded_at_or_null"),
        source_recorded_at_authority_status=str(
            winner_payload["source_recorded_at_authority_status"]
        ),
        harvest_business_date=_coerce_date(winner_payload["harvest_business_date"]),
        actual_harvest_quantity_kg=Decimal(str(winner_payload["actual_harvest_quantity_kg"])),
        commit_manifest_hash=str(winner_payload["commit_manifest_hash"]),
        season_business_key=str(winner_payload["season_business_key"]),
        farm_business_key=str(winner_payload["farm_business_key"]),
        subfarm_business_key=str(winner_payload["subfarm_business_key"]),
        variety_business_key=str(winner_payload["variety_business_key"]),
        mapping_registry_version=str(winner_payload["mapping_registry_version"]),
        mapping_policy_version=str(winner_payload["mapping_policy_version"]),
        season_resolver_version=str(winner_payload["season_resolver_version"]),
        mapping_registry_entry_hash=winner_payload.get("mapping_registry_entry_hash"),
        resolved_master_business_key=str(winner_payload["resolved_master_business_key"]),
        resolved_master_parent_business_key=winner_payload.get(
            "resolved_master_parent_business_key"
        ),
        resolved_master_record_hash=str(winner_payload["resolved_master_record_hash"]),
        mapping_snapshot_hash=str(winner_payload["mapping_snapshot_hash"]),
        resolved_identity_snapshot_hash=str(winner_payload["resolved_identity_snapshot_hash"]),
        registry_content_hash=str(winner_payload["registry_content_hash"]),
    )


def label_row_hash_for(label_payload: dict[str, Any]) -> str:
    return compute_label_row_hash(
        season_business_key=str(label_payload["season_business_key"]),
        farm_business_key=str(label_payload["farm_business_key"]),
        subfarm_business_key=str(label_payload["subfarm_business_key"]),
        variety_business_key=str(label_payload["variety_business_key"]),
        harvest_business_date=_coerce_date(label_payload["harvest_business_date"]),
        exact_decimal_quantity_sum_kg=Decimal(str(label_payload["exact_decimal_quantity_sum_kg"])),
        contributing_winner_hashes=tuple(label_payload["contributing_winner_hashes"]),
    )


def exclusion_row_hash_for(exclusion_payload: dict[str, Any]) -> str:
    return compute_exclusion_row_hash(
        exclusion_category=str(exclusion_payload["exclusion_category"]),
        source_system=str(exclusion_payload["source_system"]),
        external_logical_record_id_or_null=exclusion_payload.get(
            "external_logical_record_id_or_null"
        ),
        external_revision_id_or_null=exclusion_payload.get("external_revision_id_or_null"),
        harvest_business_date_or_null=(
            None
            if exclusion_payload.get("harvest_business_date_or_null") is None
            else _coerce_date(exclusion_payload["harvest_business_date_or_null"])
        ),
        exclusion_details=exclusion_payload.get("exclusion_details", {}),
    )


async def get_existing_snapshot_by_idempotency_key(
    session: AsyncSession,
    *,
    source_system: str,
    snapshot_idempotency_key: str,
) -> ActualHarvestLabelSnapshotModel | None:
    """Look up an existing snapshot row by its (source_system, key) tuple.

    Returns ``None`` when no snapshot exists yet. The caller decides
    whether the persisted ``snapshot_request_identity_hash`` matches the
    current request — the helper only fetches the row.
    """

    result = await session.scalar(
        select(ActualHarvestLabelSnapshotModel).where(
            ActualHarvestLabelSnapshotModel.source_system == source_system,
            ActualHarvestLabelSnapshotModel.snapshot_idempotency_key == snapshot_idempotency_key,
        )
    )
    if result is None:
        return None
    return result


async def load_winners_for_snapshot(
    session: AsyncSession,
    snapshot_id: int,
) -> Sequence[ActualHarvestLabelSnapshotWinnerModel]:
    return (
        await session.scalars(
            select(ActualHarvestLabelSnapshotWinnerModel)
            .where(ActualHarvestLabelSnapshotWinnerModel.snapshot_id == snapshot_id)
            .order_by(ActualHarvestLabelSnapshotWinnerModel.winner_sort_key)
        )
    ).all()


async def load_label_rows_for_snapshot(
    session: AsyncSession,
    snapshot_id: int,
) -> Sequence[ActualHarvestLabelSnapshotLabelModel]:
    return (
        await session.scalars(
            select(ActualHarvestLabelSnapshotLabelModel)
            .where(ActualHarvestLabelSnapshotLabelModel.snapshot_id == snapshot_id)
            .order_by(ActualHarvestLabelSnapshotLabelModel.label_sort_key)
        )
    ).all()


async def load_exclusion_rows_for_snapshot(
    session: AsyncSession,
    snapshot_id: int,
) -> Sequence[ActualHarvestLabelSnapshotExclusionModel]:
    return (
        await session.scalars(
            select(ActualHarvestLabelSnapshotExclusionModel)
            .where(ActualHarvestLabelSnapshotExclusionModel.snapshot_id == snapshot_id)
            .order_by(ActualHarvestLabelSnapshotExclusionModel.exclusion_sort_key)
        )
    ).all()


def _decode_hash_list(payload: str) -> list[str]:
    import json

    raw = json.loads(payload)
    if not isinstance(raw, list):
        raise ValueError("contributing_winner_hashes must be encoded as a JSON list")
    return [str(item) for item in raw]


def _decode_json(payload: str) -> dict[str, Any]:
    import json

    raw = json.loads(payload)
    if not isinstance(raw, dict):
        raise ValueError("exclusion_details must be encoded as a JSON object")
    return raw


def _coerce_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise TypeError(f"unsupported date value: {value!r}")


__all__ = [
    "exclusion_row_hash_for",
    "exclusion_row_to_value_object",
    "get_existing_snapshot_by_idempotency_key",
    "header_to_value_object",
    "label_row_hash_for",
    "label_row_to_value_object",
    "load_exclusion_rows_for_snapshot",
    "load_label_rows_for_snapshot",
    "load_winners_for_snapshot",
    "winner_row_hash_for",
    "winner_to_value_object",
]
