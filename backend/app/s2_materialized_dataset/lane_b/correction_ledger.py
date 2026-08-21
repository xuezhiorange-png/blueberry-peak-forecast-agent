"""Lane B correction ledger (contract §4.7)."""

from __future__ import annotations

from decimal import Decimal

from backend.app.s2_materialized_dataset.lane_b.hashes import (
    compute_correction_ledger_entry_identity_hash,
    compute_value_digest,
)
from backend.app.s2_materialized_dataset.lane_b.schemas import (
    CorrectionLedgerEntryRecord,
    ManualCorrectionRequest,
)


class CorrectionLedgerConflictError(ValueError):
    """Raised when a correction would silently replace audited history."""


def build_correction_ledger_entries(
    *,
    cleaned_dataset_version_identity_hash: str,
    correction_policy_version: str,
    correction_schema_version: str,
    source_values_by_row: dict[str, Decimal | None],
    manual_corrections: tuple[ManualCorrectionRequest, ...],
) -> tuple[CorrectionLedgerEntryRecord, ...]:
    entries: list[CorrectionLedgerEntryRecord] = []
    seen_event_ids: dict[str, CorrectionLedgerEntryRecord] = {}

    for correction in manual_corrections:
        original_value = source_values_by_row.get(correction.source_row_identity_hash)
        original_digest = compute_value_digest(
            field_name=correction.field_name,
            value=original_value,
        )
        corrected_digest = compute_value_digest(
            field_name=correction.field_name,
            value=correction.corrected_value,
        )
        identity_hash = compute_correction_ledger_entry_identity_hash(
            correction_event_id=correction.correction_event_id,
            cleaned_dataset_version_identity_hash=cleaned_dataset_version_identity_hash,
            source_row_identity_hash=correction.source_row_identity_hash,
            field_name=correction.field_name,
            correction_policy_version=correction_policy_version,
            correction_schema_version=correction_schema_version,
            original_value_digest=original_digest,
            corrected_value_digest=corrected_digest,
            reason=correction.reason,
        )
        entry = CorrectionLedgerEntryRecord(
            correction_ledger_entry_identity_hash=identity_hash,
            cleaned_dataset_version_identity_hash=cleaned_dataset_version_identity_hash,
            source_row_identity_hash=correction.source_row_identity_hash,
            correction_event_id=correction.correction_event_id,
            field_name=correction.field_name,
            correction_policy_version=correction_policy_version,
            correction_schema_version=correction_schema_version,
            quality_finding_identity_hash=correction.quality_finding_identity_hash,
            original_value_digest=original_digest,
            corrected_value_digest=corrected_digest,
            reason=correction.reason,
            manual_actor_or_authority_reference=correction.manual_actor_or_authority_reference,
        )
        prior = seen_event_ids.get(correction.correction_event_id)
        if prior is not None and prior != entry:
            raise CorrectionLedgerConflictError(
                "duplicate correction event with different before/after digests or reason"
            )
        seen_event_ids[correction.correction_event_id] = entry
        entries.append(entry)

    return tuple(sorted(entries, key=lambda item: item.correction_ledger_entry_identity_hash))


def effective_quantity_after_corrections(
    *,
    source_row_identity_hash: str,
    source_quantity: Decimal | None,
    manual_corrections: tuple[ManualCorrectionRequest, ...],
) -> Decimal | None:
    effective = source_quantity
    for correction in manual_corrections:
        if correction.source_row_identity_hash != source_row_identity_hash:
            continue
        if correction.field_name != "actual_harvest_quantity_kg":
            continue
        effective = correction.corrected_value
    return effective


def correction_identities_for_row(
    entries: tuple[CorrectionLedgerEntryRecord, ...],
    *,
    source_row_identity_hash: str,
) -> tuple[str, ...]:
    return tuple(
        sorted(
            entry.correction_ledger_entry_identity_hash
            for entry in entries
            if entry.source_row_identity_hash == source_row_identity_hash
        )
    )
