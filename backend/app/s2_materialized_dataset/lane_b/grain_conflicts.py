"""Canonical-grain duplicate detection and fail-closed resolution (§4.5)."""

from __future__ import annotations

from backend.app.s2_materialized_dataset.lane_b.exclusion_ledger import is_row_excluded
from backend.app.s2_materialized_dataset.lane_b.quality import PreparedCleaningRow
from backend.app.s2_materialized_dataset.lane_b.schemas import ExclusionLedgerEntryRecord


class CleanedRowConflictError(ValueError):
    """Raised when duplicate grain keys or lineage conflicts appear."""


def duplicate_grain_groups(
    prepared_rows: tuple[PreparedCleaningRow, ...],
) -> dict[str, tuple[str, ...]]:
    groups: dict[str, list[str]] = {}
    for prepared in prepared_rows:
        grain_key = "|".join(
            (
                str(prepared.canonical_grain_key_payload["season_business_key"]),
                str(prepared.canonical_grain_key_payload["farm_business_key"]),
                str(prepared.canonical_grain_key_payload["subfarm_business_key"]),
                str(prepared.canonical_grain_key_payload["variety_business_key"]),
                str(prepared.canonical_grain_key_payload["harvest_business_date"]),
            )
        )
        groups.setdefault(grain_key, []).append(prepared.source_row_identity_hash)
    return {key: tuple(sorted(values)) for key, values in groups.items() if len(values) > 1}


def assert_duplicate_grains_resolved_or_fail(
    *,
    duplicate_groups: dict[str, tuple[str, ...]],
    exclusion_entries: tuple[ExclusionLedgerEntryRecord, ...],
) -> None:
    for grain_key, row_hashes in sorted(duplicate_groups.items()):
        active = tuple(
            source_row_identity_hash
            for source_row_identity_hash in row_hashes
            if not is_row_excluded(
                source_row_identity_hash=source_row_identity_hash,
                entries=exclusion_entries,
            )
        )
        if len(active) > 1:
            raise CleanedRowConflictError(
                f"duplicate canonical grain without versioned exclusion disposition: {grain_key}"
            )


def should_publish_cleaned_row(
    *,
    source_row_identity_hash: str,
    grain_key: str,
    duplicate_groups: dict[str, tuple[str, ...]],
    exclusion_entries: tuple[ExclusionLedgerEntryRecord, ...],
) -> bool:
    if grain_key not in duplicate_groups:
        return True
    return not is_row_excluded(
        source_row_identity_hash=source_row_identity_hash,
        entries=exclusion_entries,
    )
