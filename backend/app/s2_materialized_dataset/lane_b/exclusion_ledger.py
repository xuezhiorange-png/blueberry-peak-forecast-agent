"""Lane B exclusion ledger (contract §4.8)."""

from __future__ import annotations

from backend.app.s2_materialized_dataset.lane_b.hashes import (
    compute_exclusion_ledger_entry_identity_hash,
)
from backend.app.s2_materialized_dataset.lane_b.schemas import (
    ExclusionLedgerEntryRecord,
    ManualExclusionRequest,
)


class ExclusionLedgerConflictError(ValueError):
    """Raised when inclusion/exclusion decisions contradict."""


def build_exclusion_ledger_entries(
    *,
    cleaned_dataset_version_identity_hash: str,
    exclusion_policy_version: str,
    exclusion_schema_version: str,
    manual_exclusions: tuple[ManualExclusionRequest, ...],
) -> tuple[ExclusionLedgerEntryRecord, ...]:
    entries: list[ExclusionLedgerEntryRecord] = []
    seen_event_ids: dict[str, ExclusionLedgerEntryRecord] = {}
    excluded_rows: set[str] = set()

    for exclusion in manual_exclusions:
        identity_hash = compute_exclusion_ledger_entry_identity_hash(
            exclusion_event_id=exclusion.exclusion_event_id,
            cleaned_dataset_version_identity_hash=cleaned_dataset_version_identity_hash,
            source_row_identity_hash=exclusion.source_row_identity_hash,
            exclusion_code=exclusion.exclusion_code.value,
            exclusion_policy_version=exclusion_policy_version,
            exclusion_schema_version=exclusion_schema_version,
            exclusion_reason_reference=exclusion.exclusion_reason_reference,
        )
        entry = ExclusionLedgerEntryRecord(
            exclusion_ledger_entry_identity_hash=identity_hash,
            cleaned_dataset_version_identity_hash=cleaned_dataset_version_identity_hash,
            source_row_identity_hash=exclusion.source_row_identity_hash,
            exclusion_event_id=exclusion.exclusion_event_id,
            exclusion_code=exclusion.exclusion_code,
            exclusion_policy_version=exclusion_policy_version,
            exclusion_schema_version=exclusion_schema_version,
            quality_finding_identity_hash=exclusion.quality_finding_identity_hash,
            exclusion_reason_reference=exclusion.exclusion_reason_reference,
            decision_authority_reference=exclusion.decision_authority_reference,
        )
        prior = seen_event_ids.get(exclusion.exclusion_event_id)
        if prior is not None and prior != entry:
            raise ExclusionLedgerConflictError(
                "duplicate exclusion event with different code, reason, or policy"
            )
        seen_event_ids[exclusion.exclusion_event_id] = entry
        if exclusion.source_row_identity_hash in excluded_rows:
            raise ExclusionLedgerConflictError(
                "contradictory exclusion entries for the same version and row"
            )
        excluded_rows.add(exclusion.source_row_identity_hash)
        entries.append(entry)

    return tuple(sorted(entries, key=lambda item: item.exclusion_ledger_entry_identity_hash))


def is_row_excluded(
    *,
    source_row_identity_hash: str,
    entries: tuple[ExclusionLedgerEntryRecord, ...],
) -> bool:
    return any(entry.source_row_identity_hash == source_row_identity_hash for entry in entries)


def exclusion_identities_for_row(
    entries: tuple[ExclusionLedgerEntryRecord, ...],
    *,
    source_row_identity_hash: str,
) -> tuple[str, ...]:
    return tuple(
        sorted(
            entry.exclusion_ledger_entry_identity_hash
            for entry in entries
            if entry.source_row_identity_hash == source_row_identity_hash
        )
    )
