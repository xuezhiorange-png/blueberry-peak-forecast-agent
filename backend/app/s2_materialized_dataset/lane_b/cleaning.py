"""Lane B cleaning projection and dataset-version builder (contract §4.4–§4.5)."""

from __future__ import annotations

from backend.app.s2_materialized_dataset.lane_b.correction_ledger import (
    build_correction_ledger_entries,
    correction_identities_for_row,
    effective_quantity_after_corrections,
)
from backend.app.s2_materialized_dataset.lane_b.exclusion_ledger import (
    build_exclusion_ledger_entries,
    exclusion_identities_for_row,
    is_row_excluded,
)
from backend.app.s2_materialized_dataset.lane_b.hashes import (
    compute_canonical_grain_key_payload,
    compute_cleaned_dataset_version_content_hash,
    compute_cleaned_dataset_version_identity_hash,
    compute_cleaned_row_content_hash,
    compute_cleaned_row_identity_hash,
    compute_quality_report_identity_hash,
    compute_synthetic_raw_import_batch_identity_hash,
    compute_synthetic_raw_source_artifact_identity_hash,
    compute_synthetic_source_row_identity_hash,
)
from backend.app.s2_materialized_dataset.lane_b.quality import (
    PreparedCleaningRow,
    evaluate_quality_findings,
    findings_for_source_row,
)
from backend.app.s2_materialized_dataset.lane_b.schemas import (
    CanonicalGrainKey,
    CleanedDatasetVersionRecord,
    CleanedRowRecord,
    CleaningBuildRequest,
    CleaningBuildResult,
    CorrectionLedgerEntryRecord,
    ExclusionLedgerEntryRecord,
    QuantityPresenceStatus,
    SyntheticSourceRowInput,
)

__all__ = [
    "CleanedDatasetVersionConflictError",
    "CleanedRowConflictError",
    "assert_replay_parity",
    "build_canonical_grain_key",
    "build_cleaned_dataset",
    "resolve_quantity_presence",
]


class CleanedDatasetVersionConflictError(ValueError):
    """Raised when the same version identity would carry different content."""


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


def resolve_quantity_presence(source_row: SyntheticSourceRowInput) -> QuantityPresenceStatus:
    if source_row.actual_harvest_quantity_kg is None:
        return QuantityPresenceStatus.UNKNOWN_NOT_ZERO
    return QuantityPresenceStatus.KNOWN


def build_canonical_grain_key(source_row: SyntheticSourceRowInput) -> CanonicalGrainKey:
    return CanonicalGrainKey(
        season_business_key=source_row.season_business_key,
        farm_business_key=source_row.farm_business_key,
        subfarm_business_key=source_row.subfarm_business_key,
        variety_business_key=source_row.variety_business_key,
        harvest_business_date=source_row.harvest_business_date,
    )


def _source_row_identity_hash(source_row: SyntheticSourceRowInput) -> str:
    identity = source_row.identity.model_dump(mode="python")
    return compute_synthetic_source_row_identity_hash(identity)


def _prepare_rows(request: CleaningBuildRequest) -> tuple[PreparedCleaningRow, ...]:
    prepared: list[PreparedCleaningRow] = []
    for source_row in request.source_rows:
        grain = build_canonical_grain_key(source_row)
        prepared.append(
            PreparedCleaningRow(
                source_row_identity_hash=_source_row_identity_hash(source_row),
                canonical_grain_key_payload=compute_canonical_grain_key_payload(
                    season_business_key=grain.season_business_key,
                    farm_business_key=grain.farm_business_key,
                    subfarm_business_key=grain.subfarm_business_key,
                    variety_business_key=grain.variety_business_key,
                    harvest_business_date=grain.harvest_business_date,
                ),
                source_row=source_row,
                quantity_presence_status=resolve_quantity_presence(source_row),
            )
        )
    return tuple(sorted(prepared, key=lambda item: item.source_row_identity_hash))


def _grain_key_text(grain: CanonicalGrainKey) -> str:
    return grain.canonical_grain_key


def _build_cleaned_row_record(
    *,
    prepared: PreparedCleaningRow,
    request: CleaningBuildRequest,
    version_identity_hash: str,
    exclusion_entries: tuple[ExclusionLedgerEntryRecord, ...],
    correction_entries: tuple[CorrectionLedgerEntryRecord, ...],
    quality_finding_hashes: tuple[str, ...],
) -> CleanedRowRecord:
    grain = build_canonical_grain_key(prepared.source_row)
    excluded = is_row_excluded(
        source_row_identity_hash=prepared.source_row_identity_hash,
        entries=exclusion_entries,
    )
    source_quantity = prepared.source_row.actual_harvest_quantity_kg
    effective_quantity = effective_quantity_after_corrections(
        source_row_identity_hash=prepared.source_row_identity_hash,
        source_quantity=source_quantity,
        manual_corrections=request.manual_corrections,
    )
    if excluded:
        effective_quantity = None

    correction_hashes = correction_identities_for_row(
        correction_entries,
        source_row_identity_hash=prepared.source_row_identity_hash,
    )
    exclusion_hashes = exclusion_identities_for_row(
        exclusion_entries,
        source_row_identity_hash=prepared.source_row_identity_hash,
    )

    content_hash = compute_cleaned_row_content_hash(
        source_row_identity_hash=prepared.source_row_identity_hash,
        canonical_grain_key=prepared.canonical_grain_key_payload,
        cleaning_projection_version=request.cleaning_projection_version,
        cleaned_row_schema_version=request.cleaned_schema_version,
        cleaning_policy_version=request.cleaning_policy_version,
        correction_policy_version=request.correction_policy_version,
        exclusion_policy_version=request.exclusion_policy_version,
        source_actual_harvest_quantity_kg=source_quantity,
        effective_actual_harvest_quantity_kg=effective_quantity,
        quantity_presence_status=prepared.quantity_presence_status.value,
        is_excluded=excluded,
        quality_finding_identity_hashes=quality_finding_hashes,
        correction_ledger_entry_identity_hashes=correction_hashes,
        exclusion_ledger_entry_identity_hashes=exclusion_hashes,
    )
    row_identity_hash = compute_cleaned_row_identity_hash(
        cleaned_dataset_version_identity_hash=version_identity_hash,
        source_row_identity_hash=prepared.source_row_identity_hash,
        canonical_grain_key=prepared.canonical_grain_key_payload,
        cleaning_projection_version=request.cleaning_projection_version,
        cleaned_row_schema_version=request.cleaned_schema_version,
        cleaning_policy_version=request.cleaning_policy_version,
        correction_policy_version=request.correction_policy_version,
        exclusion_policy_version=request.exclusion_policy_version,
        cleaned_row_content_hash=content_hash,
    )
    return CleanedRowRecord(
        cleaned_row_identity_hash=row_identity_hash,
        cleaned_row_content_hash=content_hash,
        cleaned_dataset_version_identity_hash=version_identity_hash,
        source_row_identity_hash=prepared.source_row_identity_hash,
        canonical_grain_key=grain,
        cleaning_projection_version=request.cleaning_projection_version,
        cleaned_row_schema_version=request.cleaned_schema_version,
        cleaning_policy_version=request.cleaning_policy_version,
        correction_policy_version=request.correction_policy_version,
        exclusion_policy_version=request.exclusion_policy_version,
        source_actual_harvest_quantity_kg=source_quantity,
        effective_actual_harvest_quantity_kg=effective_quantity,
        quantity_presence_status=prepared.quantity_presence_status,
        is_excluded=excluded,
        quality_finding_identity_hashes=quality_finding_hashes,
        correction_ledger_entry_identity_hashes=correction_hashes,
        exclusion_ledger_entry_identity_hashes=exclusion_hashes,
    )


def build_cleaned_dataset(request: CleaningBuildRequest) -> CleaningBuildResult:
    artifact_hashes = tuple(
        sorted(
            compute_synthetic_raw_source_artifact_identity_hash(artifact.model_dump(mode="python"))
            for artifact in request.raw_source_artifacts
        )
    )
    batch_hashes = tuple(
        sorted(
            compute_synthetic_raw_import_batch_identity_hash(batch.model_dump(mode="python"))
            for batch in request.raw_import_batches
        )
    )
    prepared_rows = _prepare_rows(request)
    source_row_hashes = tuple(item.source_row_identity_hash for item in prepared_rows)
    duplicate_groups = duplicate_grain_groups(prepared_rows)

    version_identity_hash = compute_cleaned_dataset_version_identity_hash(
        source_cohort_id=request.source_cohort_id,
        raw_import_batch_identity_hashes=batch_hashes,
        cleaning_policy_version=request.cleaning_policy_version,
        quality_policy_version=request.quality_policy_version,
        correction_policy_version=request.correction_policy_version,
        exclusion_policy_version=request.exclusion_policy_version,
        mapping_registry_hash=request.mapping_registry_hash,
        cleaned_schema_version=request.cleaned_schema_version,
    )

    source_values_by_row = {
        prepared.source_row_identity_hash: prepared.source_row.actual_harvest_quantity_kg
        for prepared in prepared_rows
    }
    correction_entries = build_correction_ledger_entries(
        cleaned_dataset_version_identity_hash=version_identity_hash,
        correction_policy_version=request.correction_policy_version,
        correction_schema_version=request.correction_schema_version,
        source_values_by_row=source_values_by_row,
        manual_corrections=request.manual_corrections,
    )
    exclusion_entries = build_exclusion_ledger_entries(
        cleaned_dataset_version_identity_hash=version_identity_hash,
        exclusion_policy_version=request.exclusion_policy_version,
        exclusion_schema_version=request.exclusion_schema_version,
        manual_exclusions=request.manual_exclusions,
    )

    assert_duplicate_grains_resolved_or_fail(
        duplicate_groups=duplicate_groups,
        exclusion_entries=exclusion_entries,
    )

    publishable_rows = tuple(
        prepared
        for prepared in prepared_rows
        if should_publish_cleaned_row(
            source_row_identity_hash=prepared.source_row_identity_hash,
            grain_key=_grain_key_text(build_canonical_grain_key(prepared.source_row)),
            duplicate_groups=duplicate_groups,
            exclusion_entries=exclusion_entries,
        )
    )

    draft_rows = tuple(
        _build_cleaned_row_record(
            prepared=prepared,
            request=request,
            version_identity_hash=version_identity_hash,
            exclusion_entries=exclusion_entries,
            correction_entries=correction_entries,
            quality_finding_hashes=(),
        )
        for prepared in publishable_rows
    )
    cleaned_row_identity_by_source = {
        row.source_row_identity_hash: row.cleaned_row_identity_hash for row in draft_rows
    }

    quality_findings = evaluate_quality_findings(
        cleaned_dataset_version_identity_hash=version_identity_hash,
        quality_policy_version=request.quality_policy_version,
        quality_schema_version=request.quality_schema_version,
        prepared_rows=prepared_rows,
        cleaned_row_identity_by_source=cleaned_row_identity_by_source,
        duplicate_groups=duplicate_groups,
        exclusion_entries=exclusion_entries,
    )

    cleaned_rows_tuple = tuple(
        sorted(
            (
                _build_cleaned_row_record(
                    prepared=prepared,
                    request=request,
                    version_identity_hash=version_identity_hash,
                    exclusion_entries=exclusion_entries,
                    correction_entries=correction_entries,
                    quality_finding_hashes=findings_for_source_row(
                        quality_findings,
                        source_row_identity_hash=prepared.source_row_identity_hash,
                    ),
                )
                for prepared in publishable_rows
            ),
            key=lambda item: item.cleaned_row_identity_hash,
        )
    )

    final_cleaned_row_identity_by_source = {
        row.source_row_identity_hash: row.cleaned_row_identity_hash for row in cleaned_rows_tuple
    }
    quality_findings = tuple(
        sorted(
            (
                finding.model_copy(
                    update={
                        "cleaned_row_identity_hash": final_cleaned_row_identity_by_source.get(
                            finding.source_row_identity_hash
                        )
                    }
                )
                for finding in quality_findings
            ),
            key=lambda item: item.quality_finding_identity_hash,
        )
    )

    quality_report_identity_hash = compute_quality_report_identity_hash(
        cleaned_dataset_version_identity_hash=version_identity_hash,
        quality_policy_version=request.quality_policy_version,
        finding_identity_hashes=(
            finding.quality_finding_identity_hash for finding in quality_findings
        ),
    )

    content_hash = compute_cleaned_dataset_version_content_hash(
        cleaned_dataset_version_identity_hash=version_identity_hash,
        raw_source_artifact_identity_hashes=artifact_hashes,
        raw_import_batch_identity_hashes=batch_hashes,
        source_row_identity_hashes=source_row_hashes,
        quality_report_identity_hash=quality_report_identity_hash,
        correction_ledger_identity_hashes=(
            entry.correction_ledger_entry_identity_hash for entry in correction_entries
        ),
        exclusion_ledger_identity_hashes=(
            entry.exclusion_ledger_entry_identity_hash for entry in exclusion_entries
        ),
        cleaned_row_content_hashes=(row.cleaned_row_content_hash for row in cleaned_rows_tuple),
    )

    version = CleanedDatasetVersionRecord(
        cleaned_dataset_version_identity_hash=version_identity_hash,
        cleaned_dataset_version_content_hash=content_hash,
        source_cohort_id=request.source_cohort_id,
        mapping_registry_hash=request.mapping_registry_hash,
        cleaning_policy_version=request.cleaning_policy_version,
        quality_policy_version=request.quality_policy_version,
        correction_policy_version=request.correction_policy_version,
        exclusion_policy_version=request.exclusion_policy_version,
        cleaned_schema_version=request.cleaned_schema_version,
        raw_source_artifact_identity_hashes=artifact_hashes,
        raw_import_batch_identity_hashes=batch_hashes,
        source_row_identity_hashes=source_row_hashes,
        quality_report_identity_hash=quality_report_identity_hash,
        correction_ledger_identity_hashes=tuple(
            entry.correction_ledger_entry_identity_hash for entry in correction_entries
        ),
        exclusion_ledger_identity_hashes=tuple(
            entry.exclusion_ledger_entry_identity_hash for entry in exclusion_entries
        ),
        cleaned_row_identity_hashes=tuple(
            row.cleaned_row_identity_hash for row in cleaned_rows_tuple
        ),
        cleaned_row_content_hashes=tuple(
            row.cleaned_row_content_hash for row in cleaned_rows_tuple
        ),
        row_count=len(cleaned_rows_tuple),
        excluded_row_count=sum(1 for row in cleaned_rows_tuple if row.is_excluded),
        unknown_quantity_row_count=sum(
            1
            for row in cleaned_rows_tuple
            if row.quantity_presence_status == QuantityPresenceStatus.UNKNOWN_NOT_ZERO
        ),
    )

    return CleaningBuildResult(
        version=version,
        cleaned_rows=cleaned_rows_tuple,
        quality_findings=quality_findings,
        correction_ledger_entries=correction_entries,
        exclusion_ledger_entries=exclusion_entries,
    )


def assert_replay_parity(left: CleaningBuildResult, right: CleaningBuildResult) -> None:
    if left.version != right.version:
        raise CleanedDatasetVersionConflictError(
            "same inputs must reproduce identical cleaned dataset version hashes"
        )
    if left.cleaned_rows != right.cleaned_rows:
        raise CleanedDatasetVersionConflictError("cleaned row replay mismatch")
    if left.quality_findings != right.quality_findings:
        raise CleanedDatasetVersionConflictError("quality finding replay mismatch")
    if left.correction_ledger_entries != right.correction_ledger_entries:
        raise CleanedDatasetVersionConflictError("correction ledger replay mismatch")
    if left.exclusion_ledger_entries != right.exclusion_ledger_entries:
        raise CleanedDatasetVersionConflictError("exclusion ledger replay mismatch")
