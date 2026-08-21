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
    QuantityPresenceStatus,
    SyntheticSourceRowInput,
)


class CleanedDatasetVersionConflictError(ValueError):
    """Raised when the same version identity would carry different content."""


class CleanedRowConflictError(ValueError):
    """Raised when duplicate grain keys or lineage conflicts appear."""


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
    return tuple(
        sorted(prepared, key=lambda item: item.source_row_identity_hash)
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

    quality_findings = evaluate_quality_findings(
        cleaned_dataset_version_identity_hash=version_identity_hash,
        quality_policy_version=request.quality_policy_version,
        quality_schema_version=request.quality_schema_version,
        prepared_rows=prepared_rows,
    )
    quality_report_identity_hash = compute_quality_report_identity_hash(
        cleaned_dataset_version_identity_hash=version_identity_hash,
        quality_policy_version=request.quality_policy_version,
        finding_identity_hashes=(
            finding.quality_finding_identity_hash for finding in quality_findings
        ),
    )

    cleaned_rows: list[CleanedRowRecord] = []
    seen_grain_keys: dict[str, str] = {}
    for prepared in prepared_rows:
        grain = build_canonical_grain_key(prepared.source_row)
        grain_key_text = grain.canonical_grain_key
        if grain_key_text in seen_grain_keys:
            continue
        seen_grain_keys[grain_key_text] = prepared.source_row_identity_hash

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

        finding_hashes = findings_for_source_row(
            quality_findings,
            source_row_identity_hash=prepared.source_row_identity_hash,
        )
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
            quality_finding_identity_hashes=finding_hashes,
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
        cleaned_rows.append(
            CleanedRowRecord(
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
                quality_finding_identity_hashes=finding_hashes,
                correction_ledger_entry_identity_hashes=correction_hashes,
                exclusion_ledger_entry_identity_hashes=exclusion_hashes,
            )
        )

    cleaned_rows_tuple = tuple(
        sorted(cleaned_rows, key=lambda item: item.cleaned_row_identity_hash)
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
        cleaned_row_content_hashes=(
            row.cleaned_row_content_hash for row in cleaned_rows_tuple
        ),
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
