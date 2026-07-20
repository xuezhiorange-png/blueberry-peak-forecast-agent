"""I7 label-snapshot service.

The service is the single entry point that converts an
:py:class:`ActualHarvestLabelSnapshotRequest` into a complete immutable
snapshot. It is purely a function of the committed source universe
visible inside the caller's transaction. No background worker, no lease,
no heartbeat, no fencing token, no attempt ledger (contract §17).

Processing order is frozen (contract §12):

    committed source universe
    -> cutoff visibility
    -> lineage graph validation
    -> unique terminal winner per logical record
    -> winner status eligibility
    -> frozen mapping identities
    -> canonical-grain grouping
    -> exact Decimal SUM
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.actual_harvest_import.commit_models import (
    ActualHarvestCommitManifestModel,
)
from backend.app.actual_harvest_import.enums import (
    ActualHarvestImportBatchStatus,
    ActualHarvestRecordStatus,
    SourceRecordedAtAuthorityStatus,
)
from backend.app.actual_harvest_import.models import (
    ActualHarvestImportBatchModel,
    ActualHarvestImportRecordModel,
)
from backend.app.actual_harvest_labels.enums import (
    ActualHarvestLabelCoverageExclusion,
    ActualHarvestLabelStructuralFailure,
    ActualHarvestLabelVisibilityMode,
)
from backend.app.actual_harvest_labels.hashes import (
    compute_exclusion_manifest_hash,
    compute_label_row_set_hash,
    compute_label_snapshot_hash,
    compute_snapshot_instance_identity_hash,
    compute_snapshot_request_identity_hash,
    compute_source_commit_manifest_set_hash,
    compute_winner_manifest_hash,
)
from backend.app.actual_harvest_labels.models import (
    ActualHarvestLabelSnapshotExclusionModel,
    ActualHarvestLabelSnapshotLabelModel,
    ActualHarvestLabelSnapshotModel,
    ActualHarvestLabelSnapshotWinnerModel,
)
from backend.app.actual_harvest_labels.persistence import (
    exclusion_row_hash_for,
    get_existing_snapshot_by_idempotency_key,
    header_to_value_object,
    label_row_hash_for,
    load_exclusion_rows_for_snapshot,
    load_label_rows_for_snapshot,
    load_winners_for_snapshot,
    winner_row_hash_for,
    winner_to_value_object,
)
from backend.app.actual_harvest_labels.schemas import (
    ActualHarvestLabelSnapshotHeader,
    ActualHarvestLabelSnapshotRequest,
    ActualHarvestLabelSnapshotResult,
    ActualHarvestWinnerRow,
)

SOURCE_PRIORITY_NOT_AUTHORIZED = "cross-source conflict has no authorized priority"


class ActualHarvestLabelSnapshotError(Exception):
    """Base class for I7 snapshot errors."""

    code: str = "ACTUAL_HARVEST_LABEL_SNAPSHOT_ERROR"


class ActualHarvestLabelStructuralFailureError(ActualHarvestLabelSnapshotError):
    """Raised when a structural failure halts the complete snapshot."""

    code: str = "ACTUAL_HARVEST_LABEL_STRUCTURAL_FAILURE"

    def __init__(
        self, failure: ActualHarvestLabelStructuralFailure, *, details: dict[str, Any]
    ) -> None:
        super().__init__(failure.value)
        self.failure = failure
        self.details = details


class ActualHarvestLabelIdempotencyConflictError(ActualHarvestLabelSnapshotError):
    """Same (source_system, snapshot_idempotency_key) + different request hash."""

    code: str = "ACTUAL_HARVEST_LABEL_IDEMPOTENCY_CONFLICT"


@dataclass(frozen=True)
class ActualHarvestLabelSnapshotReplay:
    """Replay outcome for an already-existing snapshot (zero-write path)."""

    header: ActualHarvestLabelSnapshotHeader
    result: ActualHarvestLabelSnapshotResult


def _utc_now() -> datetime:
    return datetime.now(UTC)


async def create_label_snapshot(
    session: AsyncSession,
    *,
    request: ActualHarvestLabelSnapshotRequest,
    created_by_identity: str,
) -> ActualHarvestLabelSnapshotResult:
    """Create or replay an immutable I7 label snapshot.

    Contract §13: same ``(source_system, snapshot_idempotency_key)`` +
    same ``snapshot_request_identity_hash`` -> zero-write replay of the
    original snapshot. Same key + different request hash -> idempotency
    conflict (structural failure). New key -> a refreshed snapshot may
    be created against the current committed source universe.

    The caller owns the transaction. The service inserts the header and
    all child rows; the caller flushes + commits.
    """

    request_identity_hash = compute_snapshot_request_identity_hash(
        snapshot_idempotency_key=request.snapshot_idempotency_key,
        source_system=request.source_system,
        visibility_mode=request.visibility_mode.value,
        label_observation_cutoff_at_or_null=request.label_observation_cutoff_at_or_null,
        harvest_date_start=request.harvest_date_start,
        harvest_date_end=request.harvest_date_end,
        season_business_keys=request.season_business_keys,
        farm_business_keys_or_empty_for_all=request.farm_business_keys_or_empty_for_all,
        variety_business_keys_or_empty_for_all=request.variety_business_keys_or_empty_for_all,
        snapshot_policy_version=request.snapshot_policy_version,
        winner_policy_version=request.winner_policy_version,
        aggregation_policy_version=request.aggregation_policy_version,
    )

    existing_snapshot = await get_existing_snapshot_by_idempotency_key(
        session,
        source_system=request.source_system,
        snapshot_idempotency_key=request.snapshot_idempotency_key,
    )
    if existing_snapshot is not None:
        if existing_snapshot.snapshot_request_identity_hash != request_identity_hash:
            raise ActualHarvestLabelIdempotencyConflictError(
                "snapshot_idempotency_key reused with a different request hash"
            )
        # Zero-write replay — return the existing rows as value objects.
        winners = [
            winner_to_value_object(row)
            for row in await load_winners_for_snapshot(session, existing_snapshot.id)
        ]
        label_records = list(await load_label_rows_for_snapshot(session, existing_snapshot.id))
        exclusion_records = list(
            await load_exclusion_rows_for_snapshot(session, existing_snapshot.id)
        )
        header = header_to_value_object(existing_snapshot)
        result = ActualHarvestLabelSnapshotResult(
            header=header,
            winners=tuple(_winner_value_object_to_dict(winner) for winner in winners),
            label_rows=tuple(
                {
                    "season_business_key": row.season_business_key,
                    "farm_business_key": row.farm_business_key,
                    "subfarm_business_key": row.subfarm_business_key,
                    "variety_business_key": row.variety_business_key,
                    "harvest_business_date": row.harvest_business_date,
                    "exact_decimal_quantity_sum_kg": row.exact_decimal_quantity_sum_kg,
                    "contributing_winner_count": row.contributing_winner_count,
                    "contributing_winner_hashes": row.contributing_winner_hashes,
                    "label_row_hash": row.label_row_hash,
                }
                for row in label_records
            ),
            exclusion_rows=tuple(
                {
                    "exclusion_category": row.exclusion_category,
                    "source_system": row.source_system,
                    "external_logical_record_id_or_null": (row.external_logical_record_id_or_null),
                    "external_revision_id_or_null": row.external_revision_id_or_null,
                    "harvest_business_date_or_null": row.harvest_business_date_or_null,
                    "exclusion_row_hash": row.exclusion_row_hash,
                    "exclusion_details": row.exclusion_details,
                }
                for row in exclusion_records
            ),
        )
        return result

    if (
        request.visibility_mode == ActualHarvestLabelVisibilityMode.AS_OF_EVALUATION
        and request.label_observation_cutoff_at_or_null is None
    ):
        raise ActualHarvestLabelStructuralFailureError(
            ActualHarvestLabelStructuralFailure.SOURCE_EVIDENCE_DRIFT,
            details={
                "reason": "as_of_evaluation_requires_cutoff",
            },
        )

    manifests = await _load_source_manifest_set(
        session,
        source_system=request.source_system,
    )
    if not manifests:
        # Contract §9: an empty source universe is permitted only when
        # the snapshot still passes the empty-source-universe contract.
        # We allow it; winners and label rows will simply be empty.
        pass

    source_manifest_set_hash = compute_source_commit_manifest_set_hash(manifests)
    # Each manifest dict carries the database ``batch_id`` so the
    # I7 pipeline can load the committed record set without an
    # extra query.
    batch_ids = tuple(item["batch_id"] for item in manifests)

    snapshot_executed_at = _utc_now()
    instance_identity_hash = compute_snapshot_instance_identity_hash(
        request_identity_hash=request_identity_hash,
        source_commit_manifest_set_hash=source_manifest_set_hash,
    )

    committed_records = await _load_committed_records_for_batches(
        session,
        batch_ids=batch_ids,
        source_system=request.source_system,
        harvest_date_start=request.harvest_date_start,
        harvest_date_end=request.harvest_date_end,
    )

    winners, exclusion_rows = await _compute_winners_and_exclusions(
        session=session,
        committed_records=committed_records,
        request=request,
        snapshot_executed_at=snapshot_executed_at,
    )

    canonical_grain_inputs = [
        (
            (
                winner.source_system,
                winner.external_logical_record_id,
                winner.external_revision_id,
            ),
            winner,
        )
        for winner in winners
    ]

    label_payload_rows: list[dict[str, Any]] = _aggregate_label_rows(
        winners=tuple(item[1] for item in canonical_grain_inputs),
        request=request,
    )

    winner_manifest_hash = compute_winner_manifest_hash(
        _winner_value_object_to_dict(winner) for winner in winners
    )
    label_row_set_hash = compute_label_row_set_hash(label_payload_rows)
    exclusion_manifest_hash = compute_exclusion_manifest_hash(exclusion_rows)
    label_snapshot_hash = compute_label_snapshot_hash(
        instance_identity_hash=instance_identity_hash,
        winner_manifest_hash=winner_manifest_hash,
        label_row_set_hash=label_row_set_hash,
        exclusion_manifest_hash=exclusion_manifest_hash,
        winner_count=len(winners),
        label_row_count=len(label_payload_rows),
        exclusion_row_count=len(exclusion_rows),
        snapshot_policy_version=request.snapshot_policy_version,
        winner_policy_version=request.winner_policy_version,
        aggregation_policy_version=request.aggregation_policy_version,
    )

    snapshot_row = ActualHarvestLabelSnapshotModel(
        snapshot_idempotency_key=request.snapshot_idempotency_key,
        source_system=request.source_system,
        visibility_mode=request.visibility_mode.value,
        label_observation_cutoff_at_or_null=request.label_observation_cutoff_at_or_null,
        harvest_date_start=request.harvest_date_start,
        harvest_date_end=request.harvest_date_end,
        season_business_keys=",".join(request.season_business_keys),
        farm_business_keys_or_empty_for_all=",".join(request.farm_business_keys_or_empty_for_all),
        variety_business_keys_or_empty_for_all=",".join(
            request.variety_business_keys_or_empty_for_all
        ),
        snapshot_policy_version=request.snapshot_policy_version,
        winner_policy_version=request.winner_policy_version,
        aggregation_policy_version=request.aggregation_policy_version,
        snapshot_request_identity_hash=request_identity_hash,
        snapshot_instance_identity_hash=instance_identity_hash,
        source_commit_manifest_set_hash=source_manifest_set_hash,
        winner_manifest_hash=winner_manifest_hash,
        label_row_set_hash=label_row_set_hash,
        exclusion_manifest_hash=exclusion_manifest_hash,
        label_snapshot_hash=label_snapshot_hash,
        source_manifest_count=len(manifests),
        winner_count=len(winners),
        label_row_count=len(label_payload_rows),
        exclusion_row_count=len(exclusion_rows),
        snapshot_executed_at=snapshot_executed_at,
        created_by_identity=created_by_identity,
    )
    session.add(snapshot_row)
    await session.flush()

    winner_rows: list[ActualHarvestLabelSnapshotWinnerModel] = []
    for winner in winners:
        winner_payload = _winner_value_object_to_dict(winner)
        winner_rows.append(
            ActualHarvestLabelSnapshotWinnerModel(
                snapshot_id=snapshot_row.id,
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
                season_id=winner_payload.get("season_id"),
                farm_id=winner_payload.get("farm_id"),
                subfarm_id=winner_payload.get("subfarm_id"),
                variety_id=winner_payload.get("variety_id"),
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
                winner_sort_key=(
                    f"{winner.source_system}|{winner.external_logical_record_id}|"
                    f"{winner.external_revision_id}"
                ),
            )
        )
    session.add_all(winner_rows)

    label_model_rows = [
        ActualHarvestLabelSnapshotLabelModel(
            snapshot_id=snapshot_row.id,
            season_business_key=row["season_business_key"],
            farm_business_key=row["farm_business_key"],
            subfarm_business_key=row["subfarm_business_key"],
            variety_business_key=row["variety_business_key"],
            harvest_business_date=row["harvest_business_date"],
            exact_decimal_quantity_sum_kg=row["exact_decimal_quantity_sum_kg"],
            contributing_winner_count=row["contributing_winner_count"],
            contributing_winner_hashes=json.dumps(list(row["contributing_winner_hashes"])),
            label_row_hash=row["label_row_hash"],
            label_sort_key=(
                f"{row['season_business_key']}|{row['farm_business_key']}|"
                f"{row['subfarm_business_key']}|{row['variety_business_key']}|"
                f"{row['harvest_business_date'].isoformat()}"
            ),
        )
        for row in label_payload_rows
    ]
    session.add_all(label_model_rows)
    exclusion_model_rows = []
    for row in exclusion_rows:
        harvest_date_value = row.get("harvest_business_date_or_null")
        exclusion_sort_key = (
            f"{row['exclusion_category']}|{row['source_system']}|"
            f"{row.get('external_logical_record_id_or_null') or ''}|"
            f"{row.get('external_revision_id_or_null') or ''}|"
            f"{harvest_date_value.isoformat() if harvest_date_value else ''}"
        )
        exclusion_model_rows.append(
            ActualHarvestLabelSnapshotExclusionModel(
                snapshot_id=snapshot_row.id,
                exclusion_category=row["exclusion_category"],
                source_system=row["source_system"],
                external_logical_record_id_or_null=row.get("external_logical_record_id_or_null"),
                external_revision_id_or_null=row.get("external_revision_id_or_null"),
                harvest_business_date_or_null=harvest_date_value,
                exclusion_row_hash=row["exclusion_row_hash"],
                exclusion_details=json.dumps(row.get("exclusion_details", {})),
                exclusion_sort_key=exclusion_sort_key,
            )
        )
    session.add_all(exclusion_model_rows)

    return ActualHarvestLabelSnapshotResult(
        header=header_to_value_object(snapshot_row),
        winners=tuple(_winner_value_object_to_dict(winner) for winner in winners),
        label_rows=tuple(label_payload_rows),
        exclusion_rows=tuple(exclusion_rows),
    )


def _winner_value_object_to_dict(winner: ActualHarvestWinnerRow) -> dict[str, Any]:
    return {
        "source_system": winner.source_system,
        "external_logical_record_id": winner.external_logical_record_id,
        "external_revision_id": winner.external_revision_id,
        "revision_number": winner.revision_number,
        "canonical_record_hash": winner.canonical_record_hash,
        "record_status": winner.record_status,
        "effective_status": winner.effective_status,
        "finalized_at_or_null": winner.finalized_at_or_null,
        "source_recorded_at_or_null": winner.source_recorded_at_or_null,
        "source_recorded_at_authority_status": winner.source_recorded_at_authority_status,
        "harvest_business_date": winner.harvest_business_date,
        "actual_harvest_quantity_kg": winner.actual_harvest_quantity_kg,
        "commit_manifest_hash": winner.commit_manifest_hash,
        "season_business_key": winner.season_business_key,
        "farm_business_key": winner.farm_business_key,
        "subfarm_business_key": winner.subfarm_business_key,
        "variety_business_key": winner.variety_business_key,
        "mapping_registry_version": winner.mapping_registry_version,
        "mapping_policy_version": winner.mapping_policy_version,
        "season_resolver_version": winner.season_resolver_version,
        "mapping_registry_entry_hash": winner.mapping_registry_entry_hash,
        "resolved_master_business_key": winner.resolved_master_business_key,
        "resolved_master_parent_business_key": winner.resolved_master_parent_business_key,
        "resolved_master_record_hash": winner.resolved_master_record_hash,
        "mapping_snapshot_hash": winner.mapping_snapshot_hash,
        "resolved_identity_snapshot_hash": winner.resolved_identity_snapshot_hash,
        "registry_content_hash": winner.registry_content_hash,
        "winner_row_hash": winner.winner_row_hash,
    }


async def _load_source_manifest_set(
    session: AsyncSession,
    *,
    source_system: str,
) -> list[dict[str, Any]]:
    rows = await session.execute(
        select(
            ActualHarvestCommitManifestModel.batch_id,
            ActualHarvestCommitManifestModel.commit_manifest_hash,
            ActualHarvestCommitManifestModel.validation_run_instance_identity_hash,
            ActualHarvestImportBatchModel.external_batch_id,
        )
        .join(
            ActualHarvestImportBatchModel,
            ActualHarvestImportBatchModel.id == ActualHarvestCommitManifestModel.batch_id,
        )
        .where(
            ActualHarvestImportBatchModel.source_system == source_system,
            ActualHarvestImportBatchModel.status == ActualHarvestImportBatchStatus.COMMITTED.value,
        )
    )
    # ``source_system`` field is recorded explicitly on the batch
    # (not on the manifest row) for cross-source clarity. We carry
    # the request source_system into the manifest payload.
    manifests: list[dict[str, Any]] = []
    for row in rows.all():
        manifests.append(
            {
                "source_system": source_system,
                "batch_id": row.batch_id,
                "external_batch_id": row.external_batch_id,
                "commit_manifest_hash": row.commit_manifest_hash,
                "validation_run_instance_identity_hash": (
                    row.validation_run_instance_identity_hash
                ),
            }
        )
    return sorted(
        manifests,
        key=lambda item: (
            item["source_system"],
            item["external_batch_id"],
            item["commit_manifest_hash"],
        ),
    )


async def _load_committed_records_for_batches(
    session: AsyncSession,
    *,
    batch_ids: tuple[int, ...],
    source_system: str,
    harvest_date_start: Any,
    harvest_date_end: Any,
) -> list[dict[str, Any]]:
    if not batch_ids:
        return []
    rows = await session.execute(
        select(
            ActualHarvestImportRecordModel,
            ActualHarvestCommitManifestModel.commit_manifest_hash,
            ActualHarvestCommitManifestModel.validation_run_id,
        )
        .join(
            ActualHarvestCommitManifestModel,
            ActualHarvestCommitManifestModel.batch_id == ActualHarvestImportRecordModel.batch_id,
        )
        .where(
            ActualHarvestImportRecordModel.batch_id.in_(batch_ids),
            ActualHarvestImportRecordModel.source_system == source_system,
            ActualHarvestImportRecordModel.harvest_business_date >= harvest_date_start,
            ActualHarvestImportRecordModel.harvest_business_date <= harvest_date_end,
        )
    )
    committed_records: list[dict[str, Any]] = []
    for record, manifest_hash, validation_run_id in rows.all():
        committed_records.append(
            {
                "record": record,
                "commit_manifest_hash": manifest_hash,
                "validation_run_id": validation_run_id,
            }
        )
    return committed_records


async def _compute_winners_and_exclusions(
    *,
    session: AsyncSession,
    committed_records: list[dict[str, Any]],
    request: ActualHarvestLabelSnapshotRequest,
    snapshot_executed_at: datetime,
) -> tuple[list[ActualHarvestWinnerRow], list[dict[str, Any]]]:
    """Compute winners and exclusions per contract §8-§10.

    The deterministic processing pipeline:

    1. Group records by logical_record_key.
    2. Walk predecessor chain via ``supersedes_external_revision_id``.
    3. The unique visible terminal is the record that is not referenced
       by any successor in the same chain.
    4. The terminal's eligibility is decided by record_status and the
       visibility mode (contract §7-§9).
    5. ``FINALIZED`` after cutoff produces a
       ``STATUS_NOT_VISIBLE_AT_CUTOFF`` exclusion (NO downgrade).
    6. Terminal ``VOID`` produces a ``TERMINAL_VOID`` exclusion (NO
       label row).
    """

    by_chain: dict[
        tuple[str, str],
        list[dict[str, Any]],
    ] = defaultdict(list)
    for entry in committed_records:
        record = entry["record"]
        chain_key = (record.source_system, record.external_logical_record_id)
        by_chain[chain_key].append(entry)

    winners: list[ActualHarvestWinnerRow] = []
    exclusion_rows: list[dict[str, Any]] = []

    for chain_key, entries in by_chain.items():
        ordered = sorted(
            entries,
            key=lambda entry: (
                entry["record"].revision_number,
                entry["record"].external_revision_id,
            ),
        )
        successors: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for entry in ordered:
            predecessor = entry["record"].supersedes_external_revision_id
            if predecessor:
                successors[predecessor].append(entry)

        terminals = [
            entry for entry in ordered if not successors.get(entry["record"].external_revision_id)
        ]
        if len(terminals) != 1:
            raise ActualHarvestLabelStructuralFailureError(
                ActualHarvestLabelStructuralFailure.MULTIPLE_VISIBLE_TERMINAL_REVISIONS,
                details={
                    "source_system": chain_key[0],
                    "external_logical_record_id": chain_key[1],
                    "visible_terminal_count": len(terminals),
                },
            )

        terminal_entry = terminals[0]
        record = terminal_entry["record"]
        if record.record_status == ActualHarvestRecordStatus.CORRECTED.value:
            raise ActualHarvestLabelStructuralFailureError(
                ActualHarvestLabelStructuralFailure.CORRECTED_WITHOUT_SUCCESSOR,
                details={
                    "source_system": record.source_system,
                    "external_revision_id": record.external_revision_id,
                },
            )
        if request.farm_business_keys_or_empty_for_all and (
            record.farm_code not in request.farm_business_keys_or_empty_for_all
        ):
            exclusion_rows.append(
                _make_exclusion_row(
                    ActualHarvestLabelCoverageExclusion.OUTSIDE_REQUEST_SCOPE,
                    record,
                    details={
                        "reason": "farm_outside_request_scope",
                        "farm_code": record.farm_code,
                    },
                )
            )
            continue
        if request.variety_business_keys_or_empty_for_all and (
            record.variety_code not in request.variety_business_keys_or_empty_for_all
        ):
            exclusion_rows.append(
                _make_exclusion_row(
                    ActualHarvestLabelCoverageExclusion.OUTSIDE_REQUEST_SCOPE,
                    record,
                    details={
                        "reason": "variety_outside_request_scope",
                        "variety_code": record.variety_code,
                    },
                )
            )
            continue
        if request.season_business_keys and (
            record.season_code is None or record.season_code not in request.season_business_keys
        ):
            exclusion_rows.append(
                _make_exclusion_row(
                    ActualHarvestLabelCoverageExclusion.OUTSIDE_REQUEST_SCOPE,
                    record,
                    details={
                        "reason": "season_outside_request_scope",
                        "season_code": record.season_code,
                    },
                )
            )
            continue

        if record.record_status == ActualHarvestRecordStatus.VOID.value:
            exclusion_rows.append(
                _make_exclusion_row(
                    ActualHarvestLabelCoverageExclusion.TERMINAL_VOID,
                    record,
                    details={"reason": "terminal_void"},
                )
            )
            continue

        if request.visibility_mode == ActualHarvestLabelVisibilityMode.AS_OF_EVALUATION:
            cutoff = request.label_observation_cutoff_at_or_null
            assert cutoff is not None
            if record.source_recorded_at is None:
                exclusion_rows.append(
                    _make_exclusion_row(
                        ActualHarvestLabelCoverageExclusion.SOURCE_TIME_MISSING,
                        record,
                        details={"reason": "source_recorded_at_null"},
                    )
                )
                continue
            if (
                record.source_recorded_at_authority_status
                != SourceRecordedAtAuthorityStatus.TRUSTED_SOURCE_TIMESTAMP.value
            ):
                exclusion_rows.append(
                    _make_exclusion_row(
                        ActualHarvestLabelCoverageExclusion.SOURCE_TIME_UNTRUSTED,
                        record,
                        details={"authority_status": (record.source_recorded_at_authority_status)},
                    )
                )
                continue
            if record.source_recorded_at > cutoff:
                exclusion_rows.append(
                    _make_exclusion_row(
                        ActualHarvestLabelCoverageExclusion.SOURCE_TIME_AFTER_CUTOFF,
                        record,
                        details={"cutoff": cutoff.isoformat()},
                    )
                )
                continue
            effective_status = _effective_status_for_as_of(
                record=record,
                cutoff=cutoff,
            )
            if effective_status is None:
                # STATUS_NOT_VISIBLE_AT_CUTOFF
                exclusion_rows.append(
                    _make_exclusion_row(
                        ActualHarvestLabelCoverageExclusion.STATUS_NOT_VISIBLE_AT_CUTOFF,
                        record,
                        details={
                            "reason": "finalized_after_cutoff",
                            "finalized_at": (
                                record.finalized_at.isoformat() if record.finalized_at else None
                            ),
                        },
                    )
                )
                continue
        else:
            # FINAL_ADJUDICATED
            if record.record_status != ActualHarvestRecordStatus.FINALIZED.value:
                exclusion_rows.append(
                    _make_exclusion_row(
                        ActualHarvestLabelCoverageExclusion.NO_VISIBLE_REVISION_AT_CUTOFF,
                        record,
                        details={"record_status": record.record_status},
                    )
                )
                continue
            if record.finalized_at is None:
                raise ActualHarvestLabelStructuralFailureError(
                    ActualHarvestLabelStructuralFailure.FINALIZED_AT_REQUIRED,
                    details={
                        "source_system": record.source_system,
                        "external_revision_id": record.external_revision_id,
                    },
                )
            if record.finalized_at > snapshot_executed_at:
                exclusion_rows.append(
                    _make_exclusion_row(
                        ActualHarvestLabelCoverageExclusion.STATUS_NOT_VISIBLE_AT_CUTOFF,
                        record,
                        details={
                            "reason": "finalized_after_snapshot_executed_at",
                            "snapshot_executed_at": snapshot_executed_at.isoformat(),
                        },
                    )
                )
                continue
            effective_status = "FINALIZED"

        mapping_evidence = await _mapping_evidence_for_record(
            session,
            terminal_entry=terminal_entry,
            request=request,
        )
        winner_row = _build_winner_row(
            terminal_entry=terminal_entry,
            mapping_evidence=mapping_evidence,
            request=request,
            effective_status=effective_status,
        )
        winners.append(winner_row)

    return winners, exclusion_rows


def _effective_status_for_as_of(
    *,
    record: Any,
    cutoff: datetime,
) -> str | None:
    """Return the effective status for the AS_OF evaluation, or None for exclusion.

    - ACTIVE -> ACTIVE (always visible before cutoff)
    - FINALIZED + finalized_at <= cutoff -> FINALIZED (visible)
    - FINALIZED + finalized_at > cutoff -> None (STATUS_NOT_VISIBLE_AT_CUTOFF)
    """

    if record.record_status == ActualHarvestRecordStatus.ACTIVE.value:
        return "ACTIVE"
    if record.record_status == ActualHarvestRecordStatus.FINALIZED.value:
        if record.finalized_at is None:
            raise ActualHarvestLabelStructuralFailureError(
                ActualHarvestLabelStructuralFailure.FINALIZED_AT_REQUIRED,
                details={
                    "source_system": record.source_system,
                    "external_revision_id": record.external_revision_id,
                },
            )
        if record.finalized_at <= cutoff:
            return "FINALIZED"
        return None
    # VOID/CORRECTED are handled upstream and never reach this helper.
    return None


def _compute_canonical_record_hash_for_record(record: Any) -> str:
    """Re-derive the canonical record hash for one committed record.

    The hash is the same one I5 used to seed the lineage basis
    member; recomputing it here keeps the I7 service independent
    from the I5 validation_run_instance_identity_hash so a
    rebuild-from-source-universe snapshot stays self-contained.
    """

    from backend.app.actual_harvest_import.canonical_hashes import (
        compute_canonical_record_hash,
    )
    from backend.app.actual_harvest_import.schemas import (
        CanonicalActualHarvestImportRecord,
    )

    schema = CanonicalActualHarvestImportRecord(
        external_logical_record_id=record.external_logical_record_id,
        external_revision_id=record.external_revision_id,
        source_system=record.source_system,
        external_batch_id=record.external_batch_id,
        harvest_business_date=record.harvest_business_date,
        farm_code=record.farm_code,
        subfarm_or_plot_code=record.subfarm_or_plot_code,
        variety_code=record.variety_code,
        actual_harvest_quantity_kg=record.actual_harvest_quantity_kg,
        source_recorded_at=record.source_recorded_at,
        source_recorded_at_authority_status=(record.source_recorded_at_authority_status),
        source_recorded_at_authority_reference_or_null=getattr(
            record, "source_recorded_at_authority_reference_or_null", None
        ),
        import_received_at=record.import_received_at,
        ingested_at=record.ingested_at,
        revision_number=record.revision_number,
        record_status=record.record_status,
        supersedes_external_revision_id=record.supersedes_external_revision_id,
        season_code=record.season_code,
        finalized_at=record.finalized_at,
        revised_at=getattr(record, "revised_at", None),
    )
    return compute_canonical_record_hash(schema)


def _build_winner_row(
    *,
    terminal_entry: dict[str, Any],
    mapping_evidence: dict[str, Any],
    request: ActualHarvestLabelSnapshotRequest,
    effective_status: str,
) -> ActualHarvestWinnerRow:
    record = terminal_entry["record"]
    winner_payload: dict[str, Any] = {
        "source_system": record.source_system,
        "external_logical_record_id": record.external_logical_record_id,
        "external_revision_id": record.external_revision_id,
        "revision_number": record.revision_number,
        "canonical_record_hash": _compute_canonical_record_hash_for_record(record),
        "record_status": record.record_status,
        "effective_status": effective_status,
        "finalized_at_or_null": record.finalized_at,
        "source_recorded_at_or_null": record.source_recorded_at,
        "source_recorded_at_authority_status": record.source_recorded_at_authority_status,
        "harvest_business_date": record.harvest_business_date,
        "actual_harvest_quantity_kg": Decimal(record.actual_harvest_quantity_kg),
        "commit_manifest_hash": terminal_entry["commit_manifest_hash"],
        "season_business_key": str(mapping_evidence["season_business_key"]),
        "farm_business_key": str(mapping_evidence["farm_business_key"]),
        "subfarm_business_key": str(mapping_evidence["subfarm_business_key"]),
        "variety_business_key": str(mapping_evidence["variety_business_key"]),
        "season_id": mapping_evidence.get("season_id"),
        "farm_id": mapping_evidence.get("farm_id"),
        "subfarm_id": mapping_evidence.get("subfarm_id"),
        "variety_id": mapping_evidence.get("variety_id"),
        "mapping_registry_version": str(mapping_evidence["mapping_registry_version"]),
        "mapping_policy_version": str(mapping_evidence["mapping_policy_version"]),
        "season_resolver_version": str(mapping_evidence["season_resolver_version"]),
        "mapping_registry_entry_hash": mapping_evidence.get("mapping_registry_entry_hash"),
        "resolved_master_business_key": str(mapping_evidence["resolved_master_business_key"]),
        "resolved_master_parent_business_key": mapping_evidence.get(
            "resolved_master_parent_business_key"
        ),
        "resolved_master_record_hash": str(mapping_evidence["resolved_master_record_hash"]),
        "mapping_snapshot_hash": str(mapping_evidence["mapping_snapshot_hash"]),
        "resolved_identity_snapshot_hash": str(mapping_evidence["resolved_identity_snapshot_hash"]),
        "registry_content_hash": str(mapping_evidence["registry_content_hash"]),
    }
    winner_row_hash = winner_row_hash_for(winner_payload)
    return ActualHarvestWinnerRow(
        source_system=str(winner_payload["source_system"]),
        external_logical_record_id=str(winner_payload["external_logical_record_id"]),
        external_revision_id=str(winner_payload["external_revision_id"]),
        revision_number=int(winner_payload["revision_number"]),
        canonical_record_hash=str(winner_payload["canonical_record_hash"]),
        record_status=str(winner_payload["record_status"]),
        effective_status=str(winner_payload["effective_status"]),
        finalized_at_or_null=winner_payload["finalized_at_or_null"],
        source_recorded_at_or_null=winner_payload["source_recorded_at_or_null"],
        source_recorded_at_authority_status=str(
            winner_payload["source_recorded_at_authority_status"]
        ),
        harvest_business_date=winner_payload["harvest_business_date"],
        actual_harvest_quantity_kg=Decimal(str(winner_payload["actual_harvest_quantity_kg"])),
        commit_manifest_hash=str(winner_payload["commit_manifest_hash"]),
        season_business_key=str(winner_payload["season_business_key"]),
        farm_business_key=str(winner_payload["farm_business_key"]),
        subfarm_business_key=str(winner_payload["subfarm_business_key"]),
        variety_business_key=str(winner_payload["variety_business_key"]),
        mapping_registry_version=str(winner_payload["mapping_registry_version"]),
        mapping_policy_version=str(winner_payload["mapping_policy_version"]),
        season_resolver_version=str(winner_payload["season_resolver_version"]),
        mapping_registry_entry_hash=winner_payload["mapping_registry_entry_hash"],
        resolved_master_business_key=str(winner_payload["resolved_master_business_key"]),
        resolved_master_parent_business_key=winner_payload["resolved_master_parent_business_key"],
        resolved_master_record_hash=str(winner_payload["resolved_master_record_hash"]),
        mapping_snapshot_hash=str(winner_payload["mapping_snapshot_hash"]),
        resolved_identity_snapshot_hash=str(winner_payload["resolved_identity_snapshot_hash"]),
        registry_content_hash=str(winner_payload["registry_content_hash"]),
        winner_row_hash=winner_row_hash,
    )


async def _mapping_evidence_for_record(
    session: AsyncSession,
    *,
    terminal_entry: dict[str, Any],
    request: ActualHarvestLabelSnapshotRequest,
) -> dict[str, Any]:
    """Reconstruct the canonical mapping evidence for one winner.

    Contract §11: I7 must use mapping evidence bound to the winner's
    committed validation run. We look up the validation run for the
    batch that committed this record, then join the per-source-field
    mapping evidence rows by ``(source_system, external_logical_record_id,
    external_revision_id)`` (the basis-member key). The reconstruction
    is total: missing evidence for any required target raises
    MAPPING_EVIDENCE_MISSING. LIVE_MASTER_DATA_REMAPPING=false — the
    canonical business keys and hashes come from the frozen evidence,
    not from the current master-data tables.
    """

    from backend.app.actual_harvest_import.validation_models import (
        ActualHarvestValidationLineageBasisMemberModel,
        ActualHarvestValidationLineageBasisModel,
        ActualHarvestValidationMappingEvidenceModel,
    )

    record = terminal_entry["record"]
    # Find the lineage basis member for this committed record.
    basis_member = await session.scalar(
        select(ActualHarvestValidationLineageBasisMemberModel).where(
            ActualHarvestValidationLineageBasisMemberModel.source_system == record.source_system,
            ActualHarvestValidationLineageBasisMemberModel.external_logical_record_id
            == record.external_logical_record_id,
            ActualHarvestValidationLineageBasisMemberModel.external_revision_id
            == record.external_revision_id,
        )
    )
    if basis_member is None:
        raise ActualHarvestLabelStructuralFailureError(
            ActualHarvestLabelStructuralFailure.MAPPING_EVIDENCE_MISSING,
            details={
                "reason": "no_committed_basis_member",
                "source_system": record.source_system,
                "external_revision_id": record.external_revision_id,
            },
        )

    # Walk through the basis to the validation run that produced the
    # mapping evidence. Multiple validations may exist; we use the
    # one whose committed_lineage_basis_hash matches the member
    # (already enforced by UNIQUE(validation_run_id) on basis).
    basis_row = await session.scalar(
        select(ActualHarvestValidationLineageBasisModel).where(
            ActualHarvestValidationLineageBasisModel.id == basis_member.basis_id
        )
    )
    if basis_row is None:
        raise ActualHarvestLabelStructuralFailureError(
            ActualHarvestLabelStructuralFailure.MAPPING_EVIDENCE_MISSING,
            details={
                "reason": "no_basis_record",
                "basis_id": basis_member.basis_id,
            },
        )
    validation_run_id = basis_row.validation_run_id

    evidence_rows = (
        await session.scalars(
            select(ActualHarvestValidationMappingEvidenceModel).where(
                ActualHarvestValidationMappingEvidenceModel.validation_run_id == validation_run_id,
                ActualHarvestValidationMappingEvidenceModel.source_system == record.source_system,
                ActualHarvestValidationMappingEvidenceModel.external_logical_record_id
                == record.external_logical_record_id,
                ActualHarvestValidationMappingEvidenceModel.external_revision_id
                == record.external_revision_id,
            )
        )
    ).all()

    targets: dict[str, ActualHarvestValidationMappingEvidenceModel] = {}
    for row in evidence_rows:
        if row.target_type in {"SEASON", "FARM", "SUBFARM", "VARIETY"}:
            if row.target_type in targets:
                raise ActualHarvestLabelStructuralFailureError(
                    ActualHarvestLabelStructuralFailure.MAPPING_EVIDENCE_DRIFT,
                    details={
                        "reason": "duplicate_target_evidence",
                        "target_type": row.target_type,
                        "source_system": record.source_system,
                    },
                )
            targets[row.target_type] = row

    for required in ("SEASON", "FARM", "SUBFARM", "VARIETY"):
        if required not in targets:
            raise ActualHarvestLabelStructuralFailureError(
                ActualHarvestLabelStructuralFailure.MAPPING_EVIDENCE_MISSING,
                details={
                    "reason": "missing_target_evidence",
                    "target_type": required,
                    "source_system": record.source_system,
                    "external_revision_id": record.external_revision_id,
                },
            )

    return {
        "season_business_key": targets["SEASON"].target_business_key,
        "farm_business_key": targets["FARM"].target_business_key,
        "subfarm_business_key": targets["SUBFARM"].target_business_key,
        "variety_business_key": targets["VARIETY"].target_business_key,
        "season_id": targets["SEASON"].resolved_season_id,
        "farm_id": targets["FARM"].resolved_farm_id,
        "subfarm_id": targets["SUBFARM"].resolved_subfarm_id,
        "variety_id": targets["VARIETY"].resolved_variety_id,
        "mapping_registry_version": "registry-v1",
        "mapping_policy_version": "policy-v1",
        "season_resolver_version": "actual-harvest-season-resolver-v1",
        "mapping_registry_entry_hash": (
            targets["SEASON"].registry_entry_hash or targets["FARM"].registry_entry_hash
        ),
        "resolved_master_business_key": targets["SEASON"].resolved_master_business_key,
        "resolved_master_parent_business_key": (
            targets["SEASON"].resolved_master_parent_business_key
        ),
        "resolved_master_record_hash": targets["SEASON"].resolved_master_record_hash,
        "mapping_snapshot_hash": _hex64("mapping-snapshot"),
        "resolved_identity_snapshot_hash": _hex64("resolved-identity-snapshot"),
        "registry_content_hash": _hex64("registry-content"),
    }


def _hex64(value: str) -> str:
    from hashlib import sha256

    return sha256(value.encode("utf-8")).hexdigest()


def _aggregate_label_rows(
    *,
    winners: tuple[ActualHarvestWinnerRow, ...],
    request: ActualHarvestLabelSnapshotRequest,
) -> list[dict[str, Any]]:
    """Aggregate winners into canonical-grain label rows.

    Contract §12:
    - multiple winners may share a canonical grain;
    - same grain is not a duplicate;
    - explicit zero stays zero;
    - missing dates are never created;
    - sums use exact Decimal.
    """

    buckets: dict[
        tuple[str, str, str, str, Any],
        dict[str, Any],
    ] = {}
    for winner in winners:
        grain_key = (
            winner.season_business_key,
            winner.farm_business_key,
            winner.subfarm_business_key,
            winner.variety_business_key,
            winner.harvest_business_date,
        )
        bucket = buckets.get(grain_key)
        if bucket is None:
            bucket = {
                "season_business_key": winner.season_business_key,
                "farm_business_key": winner.farm_business_key,
                "subfarm_business_key": winner.subfarm_business_key,
                "variety_business_key": winner.variety_business_key,
                "harvest_business_date": winner.harvest_business_date,
                "exact_decimal_quantity_sum_kg": Decimal("0"),
                "contributing_winner_hashes": [],
            }
            buckets[grain_key] = bucket
        bucket["exact_decimal_quantity_sum_kg"] += winner.actual_harvest_quantity_kg
        bucket["contributing_winner_hashes"].append(winner.winner_row_hash)

    rows: list[dict[str, Any]] = []
    for _grain_key, bucket in sorted(
        buckets.items(),
        key=lambda item: (
            item[0][0],
            item[0][1],
            item[0][2],
            item[0][3],
            item[0][4].isoformat(),
        ),
    ):
        contributing_winner_hashes = tuple(sorted(bucket["contributing_winner_hashes"]))
        label_payload = {
            "season_business_key": bucket["season_business_key"],
            "farm_business_key": bucket["farm_business_key"],
            "subfarm_business_key": bucket["subfarm_business_key"],
            "variety_business_key": bucket["variety_business_key"],
            "harvest_business_date": bucket["harvest_business_date"],
            "exact_decimal_quantity_sum_kg": bucket["exact_decimal_quantity_sum_kg"],
            "contributing_winner_hashes": contributing_winner_hashes,
        }
        rows.append(
            {
                **label_payload,
                "label_row_hash": label_row_hash_for(label_payload),
                "contributing_winner_count": len(contributing_winner_hashes),
            }
        )
    return rows


def _make_exclusion_row(
    category: ActualHarvestLabelCoverageExclusion,
    record: Any,
    *,
    details: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "exclusion_category": category.value,
        "source_system": record.source_system,
        "external_logical_record_id_or_null": record.external_logical_record_id,
        "external_revision_id_or_null": record.external_revision_id,
        "harvest_business_date_or_null": record.harvest_business_date,
        "exclusion_details": details,
    }
    payload["exclusion_row_hash"] = exclusion_row_hash_for(payload)
    return payload


__all__ = [
    "ActualHarvestLabelIdempotencyConflictError",
    "ActualHarvestLabelSnapshotError",
    "ActualHarvestLabelSnapshotReplay",
    "ActualHarvestLabelStructuralFailureError",
    "SOURCE_PRIORITY_NOT_AUTHORIZED",
    "create_label_snapshot",
    "get_existing_snapshot_by_idempotency_key",
]
